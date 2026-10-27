from datetime import timedelta
import json
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from celery.exceptions import Retry
from django.utils import timezone
from openai import RateLimitError
import pytest

from processing.models import Dataset, Job, RegexRule
from processing.services.provider_errors import rate_limit_details, retry_delay
from processing.services.recovery import recover_jobs
from processing.services.rules import RuleProblem, request_rule
from processing.tasks import run_job


def error(headers=None, body=None):
    response = httpx.Response(429, headers=headers or {}, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
    return RateLimitError('PRIVATE PROVIDER BODY', response=response, body=body or {})


@pytest.mark.parametrize('headers,expected', [
    ({'retry-after': '125'}, 125), ({'retry-after-ms': '1500'}, 2),
    ({'retry-after': 'NaN'}, None), ({'retry-after': '-2'}, None),
    ({'x-ratelimit-remaining-tokens': '0', 'x-ratelimit-reset-tokens': '1m2.5s'}, 63),
    ({'x-ratelimit-remaining-tokens': '100', 'x-ratelimit-reset-tokens': '1h'}, None),
])
def test_rate_limit_headers_are_honored(headers, expected):
    code, message, transient, delay = rate_limit_details(error(headers))
    assert (code, transient, delay) == ('LLM_RATE_LIMIT', True, expected)
    assert 'PRIVATE' not in message
    problem = RuleProblem(code, message, transient, delay)
    assert retry_delay(problem, 0) >= max(expected or 0, 60)
    assert retry_delay(problem, 1) >= max(expected or 0, 120)


def test_quota_and_long_cooldown_do_not_retry_early():
    assert rate_limit_details(error(body={'error': {'type': 'insufficient_quota'}}))[::2] == ('LLM_QUOTA', False)
    assert rate_limit_details(error({'retry-after': '3600'}))[2:] == (False, 3600)


def test_http_date_retry_after():
    future = format_datetime(timezone.now() + timedelta(seconds=180))
    assert 179 <= rate_limit_details(error({'retry-after': future}))[3] <= 180


def test_csv_field_limit_reports_the_actual_problem(tmp_path, settings):
    from processing.services.datasets import DatasetProblem, parse_source
    settings.MAX_CELL_CHARACTERS = 20
    source = tmp_path / 'large-cell.csv'
    source.write_text('Notes\n' + 'x' * 21 + '\n')
    with pytest.raises(DatasetProblem) as caught:
        parse_source(source, '.csv', '', tmp_path / 'normalized.jsonl', lambda *args: None)
    assert caught.value.code == 'CELL_TOO_LARGE'


@pytest.mark.django_db
def test_delayed_retry_cannot_be_claimed_or_republished_early():
    source = Dataset.objects.create(owner_session='cooldown', status='READY')
    rule = RegexRule.objects.create(owner_session='cooldown', dataset=source, column='c0', instruction='Mask emails')
    job = Job.objects.create(owner_session='cooldown', kind='GENERATE_RULE', rule=rule)
    with patch('processing.tasks.generate_rule', side_effect=RuleProblem('LLM_RATE_LIMIT', 'Wait', True, 600)), \
         patch.object(run_job, 'retry', side_effect=Retry()) as retry:
        with pytest.raises(Retry):
            run_job.run(str(job.pk))
    assert 600 <= retry.call_args.kwargs['countdown'] <= 605
    job.refresh_from_db()
    assert job.retry_not_before > timezone.now() and 'rate limited' in job.stage
    assert run_job.run(str(job.pk))['skipped']
    Job.objects.filter(pk=job.pk).update(last_dispatched_at=timezone.now()-timedelta(minutes=10))
    with patch('processing.services.recovery.dispatch') as dispatch:
        assert recover_jobs()['republished'] == 0
        dispatch.assert_not_called()
    Job.objects.filter(pk=job.pk).update(retry_not_before=timezone.now()-timedelta(seconds=1))
    with patch('processing.services.recovery.dispatch', return_value=True) as dispatch:
        assert recover_jobs()['republished'] == 1


VALID = {'supported': True, 'pattern': r'\bORD-[0-9]{6}\b', 'replacement': 'ORDER',
         'ignore_case': False, 'explanation': 'Replace complete order identifiers.',
         'positive_examples': ['ORD-123456'], 'negative_examples': ['ORD-1234567']}


def reply(data):
    return SimpleNamespace(status='completed', output_text=json.dumps(data),
                           usage=SimpleNamespace(input_tokens=20, output_tokens=30))


@patch('processing.services.rules.OpenAI')
def test_one_repair_preserves_validation_and_combines_usage(client, settings):
    settings.OPENAI_API_KEY = 'test-only'
    create = client.return_value.__enter__.return_value.responses.create
    create.side_effect = [reply({**VALID, 'pattern': r'ORD-[0-9]{6}'}), reply(VALID)]
    output, usage = request_rule('Replace order codes with exactly six digits')
    assert output == VALID and usage == {'input_tokens': 40, 'output_tokens': 60}
    assert create.call_count == 2
    assert len(create.call_args_list[0].kwargs['input']) == 1
    assert 'RULE_EXAMPLES_FAILED' in create.call_args.kwargs['input'][-1]['content']


@patch('processing.services.rules.OpenAI')
def test_invalid_repair_is_rejected_after_two_calls(client, settings):
    settings.OPENAI_API_KEY = 'test-only'
    create = client.return_value.__enter__.return_value.responses.create
    create.return_value = reply({**VALID, 'pattern': r'ORD-[0-9]{6}'})
    with pytest.raises(RuleProblem) as caught:
        request_rule('Replace order codes with exactly six digits')
    assert caught.value.code == 'RULE_EXAMPLES_FAILED' and create.call_count == 2


@patch('processing.services.rules.OpenAI')
def test_unsupported_request_is_not_reinterpreted(client, settings):
    settings.OPENAI_API_KEY = 'test-only'
    create = client.return_value.__enter__.return_value.responses.create
    create.return_value = reply({**VALID, 'supported': False})
    with pytest.raises(RuleProblem) as caught:
        request_rule('Extract and reorder columns')
    assert caught.value.code == 'RULE_UNSUPPORTED' and create.call_count == 1
