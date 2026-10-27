#!/usr/bin/env python3
"""Isolated CSV import -> Generate -> Apply -> export acceptance, no paid calls.

Uses real CSV/Spark/RE2/artifacts and worker entrypoints, isolated SQLite/locmem
instead of PostgreSQL/Redis/broker, local transport instead of S3, simulated SDK
responses instead of OpenAI. Checks every exported cell against an independent
expectation. Does not read or modify existing workspace data.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from dev_local import local_runtime_environment
os.environ.update(local_runtime_environment())
os.environ['PYTHONPATH'] = str(ROOT / 'backend') + os.pathsep + os.environ.get('PYTHONPATH', '')
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.test_settings'
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from processing.models import Dataset, Job, RegexRule, S3Connection
from processing.services.datasets import artifact_directory, prepare_dataset, read_page
from processing.services.exports import export_path
from processing.tasks import run_job

HEADER = ['ID', 'Email', 'Notes', 'Empty', 'Unicode', 'Amount', 'JoinDate',
          'Country', 'Code', 'Department', 'Label', 'Quantity', 'URL', 'Quoted', 'Tail', 'Status']
PATTERN = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}'
MODEL_RULE = {'supported': True, 'pattern': PATTERN, 'replacement': '[EMAIL]',
              'ignore_case': False, 'explanation': 'Replace email addresses.',
              'positive_examples': ['one@example.com'], 'negative_examples': ['not an email']}


def fixture_row(i):
    email = f'user{i}@example.com' if i % 13 else ''
    # Many unique values, embedded commas/quotes/newlines, occasional 5K values,
    # nulls, literal replacement metacharacters and preserved leading zeros.
    notes = f'Record {i}, contact {email}; backup backup{i}@example.org.\nSecond line "quoted". ' + 'detail ' * (700 if i % 997 == 0 else 18)
    return [f'{i:010d}', email, notes, '', f'客户 café {i}', f'{i % 100000}.07',
            f'2026-10-{i % 28 + 1:02d}', ['US', 'AU', '英国'][i % 3], f'ORD-{i:09d}',
            f'Team {i % 101}', f'unique-label-{i}', str(i % 700), f'https://example.org/items/{i}',
            'a,"b"\r\n$1\\literal', f'END-{i}', 'active' if i % 7 else '']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=1_000_000)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    assert args.rows > 0
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    settings.DATASET_ROOT = work / 'artifacts'
    settings.OPENAI_API_KEY = 'offline-sdk-fixture-only'
    call_command('migrate', verbosity=0)
    source_file = work / 'realistic.csv'
    with source_file.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADER)
        for i in range(1, args.rows + 1):
            writer.writerow(fixture_row(i))
    with source_file.open('rb') as stream:
        original_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'rows': args.rows, 'columns': len(HEADER), 'source_bytes': source_file.stat().st_size,
              'source_sha256': original_hash,
              'mode': __doc__, 'spark_master': settings.SPARK_MASTER, 'stages': []}
    print(json.dumps({'event': 'fixture_ready', **{k: result[k] for k in ('rows','columns','source_bytes')}}), flush=True)
    owner = 'isolated-csv-acceptance'
    connection = S3Connection.objects.create(owner_session=owner, bucket='offline-fixture', encrypted_credentials=b'',
        status='READY', expires_at=timezone.now()+timedelta(hours=1))
    source = Dataset.objects.create(owner_session=owner, connection=connection, source_key='realistic.csv', source_format='csv')

    def execute(job):
        start = time.monotonic()
        def diagnosed_prepare(*args, **kwargs):
            try:
                return prepare_dataset(*args, **kwargs)
            except Exception:
                # Safe only in this synthetic, credential-free harness. Production
                # logs deliberately omit provider bodies and customer cell values.
                traceback.print_exc()
                raise
        with patch('processing.tasks.prepare_dataset', side_effect=diagnosed_prepare):
            run_job.run(str(job.pk))
        job.refresh_from_db()
        stage = {'kind': job.kind, 'status': job.status, 'seconds': round(time.monotonic()-start, 3)}
        result['stages'].append(stage)
        print(json.dumps(stage), flush=True)
        assert job.status == 'SUCCESS', (job.error_code, job.error_message)

    def local_download(connection, key, path, report):
        shutil.copyfile(source_file, path)
        return {'source_bytes': source_file.stat().st_size, 'source_etag': 'offline-fixture'}

    with patch('processing.services.datasets.download_source', side_effect=local_download):
        execute(Job.objects.create(owner_session=owner, dataset=source, connection=connection, kind='IMPORT_DATASET'))
    source.refresh_from_db()
    assert source.row_count == args.rows
    rule = RegexRule.objects.create(owner_session=owner, dataset=source, column='c1', columns=['c1','c2'],
                                   instruction='Mask every email address')
    def reply(data):
        return SimpleNamespace(status='completed', output_text=json.dumps(data),
                               usage=SimpleNamespace(input_tokens=20, output_tokens=30))
    with patch('processing.services.rules.OpenAI') as sdk:
        create = sdk.return_value.__enter__.return_value.responses.create
        create.side_effect = [reply({**MODEL_RULE, 'negative_examples': ['one@example.com']}), reply(MODEL_RULE)]
        execute(Job.objects.create(owner_session=owner, kind='GENERATE_RULE', rule=rule))
        assert create.call_count == 2
        assert len(create.call_args_list[0].kwargs['input']) == 1
        assert create.call_args_list[0].kwargs['input'][0]['content'] == rule.instruction
        assert 'Record 1,' not in str(create.call_args_list)
        result['simulated_model_requests'] = create.call_count
    rule.refresh_from_db()
    target = Dataset.objects.create(owner_session=owner, parent=source, source_key=source.source_key, source_format='csv')
    execute(Job.objects.create(owner_session=owner, dataset=target, rule=rule, kind='APPLY_RULE'))
    target.refresh_from_db()
    assert target.metadata['changed_rows'] == args.rows
    assert target.metadata['matched_cells'] == 2 * args.rows - args.rows // 13
    assert target.metadata['match_count'] == 3 * args.rows - 2 * (args.rows // 13)
    export = Job.objects.create(owner_session=owner, dataset=target, kind='EXPORT_CSV')
    execute(export)
    count = 0
    with export_path(export).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream)
        assert next(reader) == HEADER
        for i, actual in enumerate(reader, 1):
            expected = fixture_row(i)
            for index in (1, 2):
                expected[index] = re.sub(PATTERN, '[EMAIL]', expected[index])
            assert actual == expected, f'Cell mismatch in row {i}'
            count += 1
    assert count == args.rows == target.row_count
    with source_file.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == original_hash
    result.update(checked_cells=count*len(HEADER), exact_export=True, original_unchanged=True,
                  partitions=len(list((artifact_directory(target.pk)/'parquet').glob('part-*.parquet'))),
                  export_bytes=export_path(export).stat().st_size,
                  last_page_rows=len(read_page(target, after=max(0,args.rows-100), limit=100)['rows']))
    (work/'report.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
