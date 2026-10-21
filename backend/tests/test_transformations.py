from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from celery.exceptions import Retry
from django.core.cache import cache
from django.utils import timezone
import httpx
from openai import AuthenticationError, RateLimitError
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job, LLMTransformation, S3Connection
from processing.services.credentials import encrypt_credentials
from processing.services.date_policy import expected_date
from processing.services.datasets import artifact_directory, build_page_index, read_page
from processing.services.rules import RuleProblem
from processing.services.transformations import (apply_transformation, preview_transformation, request_batch,
    transform_values, validate_config, validate_item, value_cache_key)
from processing.tasks import run_job

pytestmark = pytest.mark.django_db
DATE_OPTIONS = {'date_order': 'REJECT'}
CATEGORY_OPTIONS = {'labels': ['USA', 'Australia', 'Other'], 'fallback': 'Other'}
VALUES = ['2024/02/29', '03/04/2026', '2025-02-29', None, '3 October 2026', '2024/02/29']
EXPECTED = {'2024/02/29': {'value': '2024-02-29', 'status': 'normalized'},
    '03/04/2026': {'value': None, 'status': 'ambiguous'},
    '2025-02-29': {'value': None, 'status': 'invalid'},
    '3 October 2026': {'value': '2026-10-03', 'status': 'normalized'}}


@pytest.fixture(autouse=True)
def isolated_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def browser(settings):
    settings.DEBUG = True
    browser = APIClient(enforce_csrf_checks=True)
    browser.credentials(HTTP_X_CSRFTOKEN=browser.get('/api/session/').data['csrf_token'])
    return browser


@pytest.fixture
def source(settings, tmp_path, browser):
    settings.DATASET_ROOT = tmp_path / 'artifacts'
    record = Dataset.objects.create(owner_session=browser.session.session_key, status='READY',
        source_key='dates.csv', source_format='csv', row_count=len(VALUES),
        columns=[{'key': 'c0', 'name': 'Date', 'type': 'string'}])
    target = artifact_directory(record.pk)
    target.mkdir(parents=True)
    parts = tmp_path / 'parts'
    parts.mkdir()
    (parts / 'part-00000.json').write_text('\n'.join(json.dumps({'_row_id': i, 'c0': value}) for i, value in enumerate(VALUES, 1)))
    build_page_index(parts, target / 'rows.sqlite3', record.columns, lambda *args: None)
    return record


def new_record(source, **overrides):
    fields = {'owner_session': source.owner_session, 'dataset': source, 'kind': 'DATE', 'column': 'c0',
        'options': DATE_OPTIONS, 'model': 'gpt-4.1-mini'}
    return LLMTransformation.objects.create(**{**fields, **overrides})


def fake_dates(record, values):
    return [EXPECTED[value] for value in values], {'input_tokens': 30, 'output_tokens': 40}


@pytest.mark.parametrize('value,order,answer,status', [
    ('2024/2/29', 'REJECT', '2024-02-29', 'normalized'),
    ('2025-02-29', 'REJECT', None, 'invalid'),
    ('2026年10月3日', 'REJECT', '2026-10-03', 'normalized'),
    ('3rd October 2026', 'REJECT', '2026-10-03', 'normalized'),
    ('Oct 3, 2026', 'REJECT', '2026-10-03', 'normalized'),
    ('03/04/2026', 'REJECT', None, 'ambiguous'),
    ('03/04/2026', 'DAY_FIRST', '2026-04-03', 'normalized'),
    ('03/04/2026', 'MONTH_FIRST', '2026-03-04', 'normalized'),
    ('13/04/2026', 'MONTH_FIRST', '2026-04-13', 'normalized'),
    ('04/13/2026', 'DAY_FIRST', '2026-04-13', 'normalized'),
    ('04/04/2026', 'REJECT', '2026-04-04', 'normalized'),
    ('31/04/2026', 'DAY_FIRST', None, 'invalid'),
    ('00/04/2026', 'REJECT', None, 'invalid'), ('04/00/2026', 'REJECT', None, 'invalid'),
    ('03/04/0000', 'REJECT', None, 'invalid'),
    ('tomorrow', 'REJECT', None, 'invalid'), ('01/02/26', 'DAY_FIRST', None, 'invalid'),
    ('2026-10-03T12:00:00Z', 'REJECT', None, 'invalid'), ('45933', 'REJECT', None, 'invalid'),
    ('', 'REJECT', None, 'missing'), (None, 'REJECT', None, 'missing'),
])
def test_date_calendar_and_ambiguity_policy(value, order, answer, status):
    assert expected_date(value, order) == (answer, status)


@pytest.mark.parametrize('kind,options', [('DATE', {'date_order': []}), ('DATE', {}), ('DATE', {'date_order': 'GUESS'}),
    ('DATE', []), ('CATEGORY', {'labels': ['A', 'A'], 'fallback': 'A'}),
    ('CATEGORY', {'labels': ['A', 'B'], 'fallback': 'C'}), ('CATEGORY', {'labels': ['A'], 'fallback': 'A'}),
    ('CATEGORY', {'labels': ['A', ' B'], 'fallback': 'A'}), ('CODE', {})])
def test_configuration_limits(kind, options):
    with pytest.raises(RuleProblem):
        validate_config(kind, options)


def test_hallucinated_or_calendar_invalid_dates_are_rejected(source):
    record = new_record(source)
    for before, after in [('2025-02-29', '2025-03-01'), ('2024/02/29', '2024-03-01'), ('tomorrow', '2026-10-18')]:
        with pytest.raises(RuleProblem):
            validate_item({'value': after, 'status': 'normalized'}, before, record)


def test_labels_fallback_and_empty_values_are_validated(source):
    record = new_record(source, kind='CATEGORY', options=CATEGORY_OPTIONS)
    for item in [{'value': 'invented', 'status': 'classified'}, {'value': 'USA', 'status': 'fallback'},
                 {'value': 'USA', 'status': []}, {'value': None, 'status': 'classified'}]:
        with pytest.raises(RuleProblem):
            validate_item(item, 'business text', record)
    assert validate_item({'value': 'Other', 'status': 'fallback'}, 'unclear', record)['value'] == 'Other'
    assert validate_item({'value': None, 'status': 'missing'}, ' ', record)['status'] == 'missing'


@patch('processing.services.transformations.OpenAI')
def test_batch_request_is_structured_and_only_sends_selected_values(client, source, settings):
    settings.OPENAI_API_KEY = 'fake-key-only'
    record = new_record(source)
    create = client.return_value.__enter__.return_value.responses.create
    create.return_value = SimpleNamespace(status='completed', output_text=json.dumps({'items': [
        {'id': 0, **EXPECTED['2024/02/29']}]}), usage=SimpleNamespace(input_tokens=20, output_tokens=10))
    outputs, usage = request_batch(record, ['2024/02/29'])
    args = create.call_args.kwargs
    assert args['store'] is False and args['max_output_tokens'] == 1800
    assert args['model'] == record.model and args['text']['format']['strict'] is True
    payload = json.loads(args['input'][0]['content'])
    assert payload['values'] == [{'id': 0, 'text': '2024/02/29'}]
    assert not any(secret in str(args) for secret in ['fake-key-only', 'dates.csv', source.owner_session, str(source.pk)])
    assert outputs[0]['value'] == '2024-02-29' and usage['output_tokens'] == 10


@pytest.mark.parametrize('items', [[], [{'id': True, **EXPECTED['2024/02/29']}],
    [{'id': 2, **EXPECTED['2024/02/29']}], [{'id': 0, **EXPECTED['2024/02/29'], 'extra': 1}],
    [{'id': 0, **EXPECTED['2024/02/29']}, {'id': 0, **EXPECTED['2024/02/29']}]])
@patch('processing.services.transformations.OpenAI')
def test_missing_duplicate_extra_and_wrong_ids_rejected(client, items, source, settings):
    settings.OPENAI_API_KEY = 'fake-key-only'
    client.return_value.__enter__.return_value.responses.create.return_value = SimpleNamespace(
        status='completed', output_text=json.dumps({'items': items}))
    with pytest.raises(RuleProblem) as caught:
        request_batch(new_record(source), ['2024/02/29'])
    assert caught.value.code == 'LLM_INVALID_OUTPUT'


@patch('processing.services.transformations.request_batch', side_effect=fake_dates)
def test_distinct_value_caching_preview_and_usage(request, source):
    record = new_record(source)
    first = preview_transformation(record, lambda *args: None)
    second = preview_transformation(record, lambda *args: None)
    assert first['preview']['counts'] == {'normalized': 3, 'ambiguous': 1, 'invalid': 1, 'missing': 1}
    assert first['usage']['unique_values'] == 4 and first['usage']['model_calls'] == 1
    assert second['preview'] == first['preview']
    assert second['usage']['cached_values'] == 4 and second['usage']['model_calls'] == 0
    assert second['usage']['input_tokens'] == second['usage']['output_tokens'] == 0
    request.assert_called_once()


def test_cache_key_scopes_owner_kind_options_instruction_and_model(source):
    record = new_record(source)
    original = value_cache_key(record, '2024/02/29')
    assert '2024' not in original and record.owner_session not in original
    for field, value in [('owner_session', 'different'), ('model', 'other-model'), ('instruction', 'new instruction'),
                         ('options', {'date_order': 'MONTH_FIRST'}), ('kind', 'CATEGORY')]:
        previous = getattr(record, field)
        setattr(record, field, value)
        assert value_cache_key(record, '2024/02/29') != original
        setattr(record, field, previous)
    assert value_cache_key(record, '2024/03/01') != original


@patch('processing.services.transformations.request_batch', side_effect=fake_dates)
def test_corrupt_cache_is_validated_before_reuse(request, source):
    record = new_record(source)
    cache.set(value_cache_key(record, '2024/02/29'), {'value': '2099-01-01', 'status': 'normalized'})
    result, usage = transform_values(record, ['2024/02/29'], lambda *args: None)
    assert result['2024/02/29']['value'] == '2024-02-29' and usage['model_calls'] == 1


def test_preflight_limits_and_cache_failure_never_make_paid_requests(source):
    record = new_record(source)
    with patch('processing.services.transformations.request_batch') as model:
        for values, code in [(['x' * 1025], 'TRANSFORM_VALUE_TOO_LONG'),
                             ([str(i) for i in range(501)], 'TRANSFORM_TOO_MANY_VALUES')]:
            with pytest.raises(RuleProblem) as caught:
                transform_values(record, values, lambda *args: None)
            assert caught.value.code == code
        with patch('processing.services.transformations.cache.get_many', side_effect=ConnectionError()):
            with pytest.raises(RuleProblem):
                transform_values(record, ['2024/02/29'], lambda *args: None)
        model.assert_not_called()


@pytest.mark.parametrize('quota', [False, True])
@patch('processing.services.transformations.OpenAI')
def test_provider_access_and_quota_failures_are_sanitized(client, quota, source, settings):
    settings.OPENAI_API_KEY = 'fake-key-only'
    response = httpx.Response(429 if quota else 401, request=httpx.Request('POST', 'https://api.openai.com/v1/responses'))
    error = (RateLimitError('PRIVATE VALUE', response=response, body={'code': 'insufficient_quota'}) if quota
             else AuthenticationError('PRIVATE VALUE', response=response, body={}))
    client.return_value.__enter__.return_value.responses.create.side_effect = error
    with pytest.raises(RuleProblem) as caught:
        request_batch(new_record(source), ['2024/02/29'])
    assert caught.value.code == ('LLM_QUOTA' if quota else 'LLM_ACCESS_DENIED')
    assert caught.value.transient is False and 'PRIVATE VALUE' not in str(caught.value)


def test_transform_transient_failure_retries_then_marks_preview_failed(source):
    record = new_record(source)
    job = Job.objects.create(owner_session=source.owner_session, kind='PREVIEW_TRANSFORM', transformation=record)
    with patch('processing.tasks.preview_transformation', side_effect=RuleProblem('LLM_TEMPORARY', 'Retry.', True)):
        with patch.object(run_job, 'retry', side_effect=Retry()) as retry:
            with pytest.raises(Retry):
                run_job.run(str(job.pk))
    retry.assert_called_once_with(countdown=2)
    job.refresh_from_db(); record.refresh_from_db()
    assert job.status == 'QUEUED' and record.status == 'PENDING'
    run_job.push_request(retries=2)
    try:
        with patch('processing.tasks.preview_transformation', side_effect=RuleProblem('LLM_TEMPORARY', 'Retry.', True)):
            run_job.run(str(job.pk))
    finally:
        run_job.pop_request()
    job.refresh_from_db(); record.refresh_from_db()
    assert job.status == 'FAILED' and record.status == 'FAILED'


def test_batches_are_bounded_deduplicated_and_partially_cached_on_retry(source):
    record = new_record(source, kind='CATEGORY', options=CATEGORY_OPTIONS)
    values = [f'Note {i}' for i in range(25)]
    def output(record, batch):
        return [{'value': 'Other', 'status': 'fallback'} for value in batch], {'input_tokens': 1, 'output_tokens': 2}
    with patch('processing.services.transformations.request_batch', side_effect=output) as model:
        results, usage = transform_values(record, values + values, lambda *args: None)
    assert [len(call.args[1]) for call in model.call_args_list] == [12, 12, 1]
    assert len(results) == 25 and usage['model_calls'] == 3 and usage['input_tokens'] == 3
    # Retry may see an already cached prefix and must only pay for the missing value.
    cache.delete(value_cache_key(record, values[-1]))
    with patch('processing.services.transformations.request_batch', side_effect=output) as model:
        _, usage = transform_values(record, values, lambda *args: None)
    assert model.call_args.args[1] == [values[-1]] and usage['cached_values'] == 24


@patch('processing.views.dispatch', return_value=True)
def test_preview_api_requires_consent_column_and_csrf_returns_202_without_llm(dispatch, browser, source):
    payload = {'kind': 'DATE', 'column': 'c0', 'options': DATE_OPTIONS, 'allow_send_values': True}
    url = f'/api/datasets/{source.pk}/transformations/'
    assert APIClient(enforce_csrf_checks=True).post(url, payload, format='json').status_code == 403
    assert browser.post(url, {**payload, 'allow_send_values': False}, format='json').status_code == 400
    assert browser.post(url, {**payload, 'column': 'c9'}, format='json').status_code == 400
    with patch('processing.services.transformations.request_batch') as model:
        response = browser.post(url, payload, format='json')
    assert response.status_code == 202 and response.data['kind'] == 'PREVIEW_TRANSFORM'
    assert response.data['dataset_id'] is None and response.data['transformation_id']
    model.assert_not_called()
    dispatch.assert_called_once()


@patch('processing.services.transformations.request_batch', side_effect=fake_dates)
def test_preview_task_persists_and_cannot_be_read_by_other_owner(request, browser, source):
    record = new_record(source)
    job = Job.objects.create(owner_session=source.owner_session, kind='PREVIEW_TRANSFORM', transformation=record)
    run_job.run(str(job.pk))
    record.refresh_from_db(); job.refresh_from_db()
    assert record.status == 'READY' and job.status == 'SUCCESS' and job.dataset_id is None
    assert job.result['source_dataset_id'] == str(source.pk)
    other = APIClient()
    assert other.get(f'/api/transformations/{record.pk}/').status_code == 404
    assert other.get(f'/api/datasets/{source.pk}/transformations/').status_code == 404
    assert other.post(f'/api/transformations/{record.pk}/apply/', {'allow_send_values': True}, format='json').status_code == 404
    assert browser.get(f'/api/transformations/{record.pk}/').data['preview']['sampled_rows'] == 6


def test_cancel_during_batch_preserves_source_and_does_not_publish_cache(browser, source):
    record = new_record(source)
    job = Job.objects.create(owner_session=source.owner_session, kind='PREVIEW_TRANSFORM', transformation=record)
    def cancelled(record, values):
        browser.post(f'/api/jobs/{job.pk}/cancel/', {}, format='json')
        return fake_dates(record, values)
    with patch('processing.services.transformations.request_batch', side_effect=cancelled):
        run_job.run(str(job.pk))
    job.refresh_from_db(); record.refresh_from_db()
    assert job.status == 'CANCELLED' and record.status == 'CANCELLED'
    assert cache.get(value_cache_key(record, '2024/02/29')) is None
    assert read_page(source)['rows'][0]['cells'][0] == '2024/02/29'


@patch('processing.views.dispatch', return_value=True)
def test_apply_requires_ready_and_consent_and_creates_new_dataset(dispatch, browser, source):
    record = new_record(source)
    url = f'/api/transformations/{record.pk}/apply/'
    assert browser.post(url, {'allow_send_values': True}, format='json').status_code == 409
    record.status = 'READY'; record.save()
    assert browser.post(url, {}, format='json').status_code == 400
    response = browser.post(url, {'allow_send_values': True}, format='json')
    assert response.status_code == 202 and response.data['kind'] == 'APPLY_TRANSFORM'
    output = Dataset.objects.get(pk=response.data['dataset_id'])
    assert output.parent_id == source.pk and output.pk != source.pk


def test_preview_failure_and_apply_failure_keep_source_and_ready_plan(source):
    record = new_record(source)
    job = Job.objects.create(owner_session=source.owner_session, kind='PREVIEW_TRANSFORM', transformation=record)
    with patch('processing.tasks.preview_transformation', side_effect=RuleProblem('LLM_INVALID_LABEL', 'Invalid label.')):
        run_job.run(str(job.pk))
    record.refresh_from_db(); job.refresh_from_db()
    assert record.status == 'FAILED' and job.error_code == 'LLM_INVALID_LABEL'
    record.status = 'READY'; record.save()
    output = Dataset.objects.create(owner_session=source.owner_session, parent=source, source_key='dates.csv', source_format='csv')
    applied = Job.objects.create(owner_session=source.owner_session, kind='APPLY_TRANSFORM', transformation=record, dataset=output)
    with patch('processing.tasks.prepare_dataset', side_effect=RuleProblem('TRANSFORM_TOO_MANY_VALUES', 'Limit.')):
        run_job.run(str(applied.pk))
    record.refresh_from_db(); output.refresh_from_db()
    assert record.status == 'READY' and output.status == 'FAILED'
    assert not artifact_directory(output.pk).exists() and read_page(source)['total_rows'] == 6


@pytest.mark.spark
def test_real_spark_date_then_category_chain_preserves_all_source_cells(settings, tmp_path):
    settings.DATASET_ROOT = tmp_path / 'spark-artifacts'
    connection = S3Connection.objects.create(owner_session='owner', bucket='test-fixtures',
        encrypted_credentials=encrypt_credentials({'access_key_id': 'FAKE', 'secret_access_key': 'FAKE'}),
        expires_at=timezone.now() + timedelta(hours=1), status='READY')
    source = Dataset.objects.create(owner_session='owner', connection=connection, source_key='contacts.csv', source_format='csv')
    imported = Job.objects.create(owner_session='owner', kind='IMPORT_DATASET', dataset=source, connection=connection)
    def fixture_download(conn, key, target, report):
        import shutil
        path = Path(__file__).resolve().parents[2] / 'samples' / 'contacts.csv'
        shutil.copyfile(path, target)
        return {'source_bytes': path.stat().st_size}
    with patch('processing.services.datasets.download_source', side_effect=fixture_download):
        run_job.run(str(imported.pk))
    source.refresh_from_db()
    before = read_page(source)['rows']
    # Explicit fixture expectations, independent of the date parser and the model.
    dates = dict(zip([row['cells'][3] for row in before], [f'2026-10-{i:02}' for i in range(1, 9)]))
    countries = {'USA': 'USA', 'U.S.': 'USA', 'United States': 'USA', 'Australia': 'Australia', 'AU': 'Australia', 'AUS': 'Australia'}
    parent = source
    for kind, column, options in [('DATE', 'c3', DATE_OPTIONS), ('CATEGORY', 'c4', CATEGORY_OPTIONS)]:
        record = new_record(parent, kind=kind, column=column, options=options, status='READY')
        output = Dataset.objects.create(owner_session='owner', parent=parent, source_key='contacts.csv', source_format='csv')
        job = Job.objects.create(owner_session='owner', kind='APPLY_TRANSFORM', transformation=record, dataset=output)
        def response(record, values):
            lookup = dates if record.kind == 'DATE' else countries
            return [{'value': lookup[value], 'status': 'normalized' if record.kind == 'DATE' else 'classified'} for value in values], {}
        with patch('processing.services.transformations.request_batch', side_effect=response):
            run_job.run(str(job.pk))
        job.refresh_from_db(); output.refresh_from_db()
        assert job.status == 'SUCCESS', job.error_code
        after = read_page(output)['rows']
        assert len(output.columns) == len(parent.columns) + 2
        assert output.metadata['status_counts'] == {'normalized' if kind == 'DATE' else 'classified': 8}
        assert output.metadata['partition_count'] == 4
        for old, row in zip(read_page(parent)['rows'], after):
            assert row['row_number'] == old['row_number'] and row['cells'][:-2] == old['cells']
            assert row['cells'][-2] == (dates[old['cells'][3]] if kind == 'DATE' else countries[old['cells'][4]])
        assert read_page(source)['rows'] == before
        parent = output
    assert len(parent.columns) == 10


@pytest.mark.spark
def test_real_spark_full_column_preflight_empty_null_and_unseen_values(settings, tmp_path):
    from processing.services.datasets import create_spark
    from pyspark.sql.types import LongType, StringType, StructField, StructType
    settings.DATASET_ROOT = tmp_path
    source = Dataset.objects.create(owner_session='owner', status='READY', source_key='dates.csv', source_format='csv',
        columns=[{'key': 'c0', 'name': 'Date', 'type': 'string'}])
    output = Dataset.objects.create(owner_session='owner', parent=source, source_key='dates.csv', source_format='csv')
    record = new_record(source, status='READY')
    spark = create_spark('day4-preflight-test')
    schema = StructType([StructField('_row_id', LongType(), False), StructField('c0', StringType(), True)])
    try:
        with patch('processing.services.transformations.request_batch') as model:
            for rows, expected in [([(1, 'x' * 1025)], 'TRANSFORM_VALUE_TOO_LONG'),
                                   ([(i + 1, str(i)) for i in range(501)], 'TRANSFORM_TOO_MANY_VALUES')]:
                with pytest.raises(RuleProblem) as caught:
                    apply_transformation(spark.createDataFrame(rows, schema), output, record, lambda *args: None)
                assert caught.value.code == expected
            model.assert_not_called()
        for rows, count in [([], 0), ([(1, None), (2, '')], 2)]:
            with patch('processing.services.transformations.request_batch') as model:
                frame, metadata = apply_transformation(spark.createDataFrame(rows, schema), output, record, lambda *args: None)
                assert frame.count() == count and metadata['llm_usage']['model_calls'] == 0
                if count:
                    assert metadata['status_counts'] == {'missing': 2}
                model.assert_not_called()
        cache.set(value_cache_key(record, '2024/02/29'), EXPECTED['2024/02/29'])
        with patch('processing.services.transformations.request_batch', side_effect=fake_dates) as model:
            _, metadata = apply_transformation(spark.createDataFrame([(1, '2024/02/29'), (2, '3 October 2026')], schema),
                                                output, record, lambda *args: None)
            assert metadata['llm_usage']['cached_values'] == 1 and model.call_args.args[1] == ['3 October 2026']
    finally:
        spark.stop()
