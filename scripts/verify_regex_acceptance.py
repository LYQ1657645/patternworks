"""Explicit live small-fixture acceptance: synthetic prompts only, three distinct prompts (existing bounded provider retries apply).
Run inside a worker container. Uses isolated session-owned records and retains evidence.
Real Spark applications and Redis cache checks; import transport is a local fixture.
"""
import csv
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

sys.path.insert(0, '/app/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from processing.models import Dataset, Job, RegexRule, S3Connection
from django.utils import timezone
from datetime import timedelta
from processing.services.datasets import read_page
from processing.services.regex_engine import apply_cell, validate_pattern, RuleValidationError
from processing.tasks import run_job


def execute(job):
    run_job.run(str(job.pk))
    job.refresh_from_db()
    assert job.status == 'SUCCESS', (job.kind, job.error_code)
    return job


def main():
    owner = 'regex-accept-' + uuid.uuid4().hex[:24]
    connection = S3Connection.objects.create(owner_session=owner, bucket='local-synthetic-fixture', encrypted_credentials=b'', status='READY', expires_at=timezone.now()+timedelta(hours=1))
    source = Dataset.objects.create(owner_session=owner, source_key='synthetic-regex-acceptance.csv', source_format='csv')
    def download(connection, key, target, report):
        import shutil
        shutil.copyfile('/app/samples/contacts.csv', target)
        return {'source_bytes': Path(target).stat().st_size}
    with patch('processing.services.datasets.download_source', side_effect=download):
        execute(Job.objects.create(owner_session=owner, kind='IMPORT_DATASET', dataset=source, connection=connection))
    source.refresh_from_db()
    original = read_page(source)['rows']
    prompts = ['Find every email address anywhere in the text, including multiple addresses in a cell.',
               'Match email addresses embedded in sentences; leave surrounding text untouched.',
               '找出文本中所有电子邮箱地址，同一单元格中的多个邮箱都要匹配。']
    records = []
    for prompt in prompts:
        rule = RegexRule.objects.create(owner_session=owner, dataset=source, column='c2', columns=['c2', 'c5'], instruction=prompt)
        execute(Job.objects.create(owner_session=owner, kind='GENERATE_RULE', rule=rule, parameters={'replacement': '[EMAIL]'}))
        rule.refresh_from_db()
        assert not rule.cache_hit
        for before, after in [('a@example.com', '[EMAIL]'), ('Two: first@example.com and second@example.net', 'Two: [EMAIL] and [EMAIL]'),
                              ('no email', 'no email'), ('not-an-email', 'not-an-email'), (None, None)]:
            assert apply_cell(before, pattern=rule.pattern, replacement='[EMAIL]', ignore_case=rule.ignore_case)[0] == after
        records.append({'rule_id': str(rule.pk), 'instruction': prompt, 'pattern': rule.pattern, 'usage': rule.usage})
    cached = RegexRule.objects.create(owner_session=owner, dataset=source, column='c2', columns=['c2','c5'], instruction=prompts[0])
    with patch('processing.services.rules.request_rule', side_effect=AssertionError('Cache miss must not call model')):
        execute(Job.objects.create(owner_session=owner, kind='GENERATE_RULE', rule=cached, parameters={'replacement':'[EMAIL]'}))
    cached.refresh_from_db(); assert cached.cache_hit
    output = Dataset.objects.create(owner_session=owner, parent=source, source_key=source.source_key, source_format='csv')
    execute(Job.objects.create(owner_session=owner, dataset=output, kind='APPLY_RULE', rule=cached))
    output.refresh_from_db()
    expected = json.loads(json.dumps(original))
    for row in expected:
        if row['row_number'] not in (4,6): row['cells'][2] = '[EMAIL]'
    notes={1:'Contact [EMAIL] for a demo.',2:'A second email: [EMAIL]',5:'Two emails: [EMAIL] and [EMAIL]'}
    for row in expected:
        if row['row_number'] in notes: row['cells'][5]=notes[row['row_number']]
    assert read_page(output)['rows'] == expected
    assert read_page(source)['rows'] == original
    no_match = RegexRule.objects.create(owner_session=owner, dataset=source, column='c2', status='READY', pattern='ZZZ_NO_MATCH_731', replacement='x')
    unchanged = Dataset.objects.create(owner_session=owner,parent=source,source_key=source.source_key,source_format='csv')
    execute(Job.objects.create(owner_session=owner, dataset=unchanged, kind='APPLY_RULE', rule=no_match))
    unchanged.refresh_from_db(); assert read_page(unchanged)['rows']==original
    rejected=[]
    for pattern in ['[', '(a+)+$', r'(a)\1', r'(?=x)']:
        try: validate_pattern(pattern)
        except RuleValidationError: rejected.append(pattern)
        else: raise AssertionError('Unsafe pattern accepted')
    rows=[]; cursor=0
    while True:
        page=read_page(output, after=cursor, limit=3); rows.extend(page['rows'])
        cursor=page['next_cursor']
        if cursor is None: break
    assert rows == expected
    evidence={'mode':'3 live synthetic model prompts, real Redis cache and Spark; local fixture import transport',
              'model':settings.OPENAI_MODEL,'prompts':records,'cache_hit':cached.cache_hit,
              'multicolumn_exact':True,'source_preserved':True,'no_match_preserved':True,
              'pagination_exact':True,'invalid_patterns_rejected':rejected,'source_id':str(source.pk),'result_id':str(output.pk)}
    Path(sys.argv[1]).write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'passed':True,'live_prompts':3,'cache_hit':True,'rows':8}))

if __name__ == '__main__': main()
