#!/usr/bin/env python3
"""Explicit container-only scale harness; local fixture transport and seeded LLM cache.

Run with the existing backend image and this script mounted read-only. It uses the
real PostgreSQL, Redis, CSV parser, Spark transformations and persisted artifacts.
It invokes the worker entrypoint synchronously; broker/recovery tests are separate.
No S3 or OpenAI request is permitted. Benchmark records use a dedicated owner.
"""
import argparse
from contextlib import closing
import csv
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import threading
import time
from unittest.mock import patch
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, str(Path('/app/backend') if Path('/app/backend').is_dir() else Path(__file__).resolve().parents[1] / 'backend'))
import django
django.setup()
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from processing.models import Dataset, Job, LLMTransformation, RegexRule, S3Connection
from processing.services.datasets import artifact_directory, read_page
from processing.services.transformations import validate_item, value_cache_key
from processing.tasks import run_job

EXPECTED_NOTES = ['Contact [EMAIL] for a demo.', 'A second email: [EMAIL]', 'No email in this note.',
    'Missing email is intentional.', 'Two emails: [EMAIL] and [EMAIL]', 'Invalid email text is intentional.',
    'A note, with a comma, to exercise CSV quoting.', 'All records are synthetic test data.']
COUNTRIES = ['USA', 'USA', 'USA', 'Australia', 'Australia', 'Australia', 'USA', 'Australia']


def cgroup_value(name):
    path = Path('/sys/fs/cgroup') / name
    return path.read_text().strip() if path.is_file() else None


def cpu_seconds():
    values = dict(line.split() for line in (cgroup_value('cpu.stat') or '').splitlines())
    return int(values.get('usage_usec', 0)) / 1e6


def tree_rss():
    total = 0
    for path in Path('/proc').glob('[0-9]*/status'):
        try:
            for line in path.read_text().splitlines():
                if line.startswith('VmRSS:'):
                    total += int(line.split()[1]) * 1024
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return total


def verify(dataset, prototypes, rows, stage):
    digest = hashlib.sha256()
    started = time.monotonic()
    count = 0
    with closing(sqlite3.connect(artifact_directory(dataset.pk) / 'rows.sqlite3')) as db:
        for row_id, payload in db.execute('SELECT row_id,cells FROM rows ORDER BY row_id'):
            count += 1
            index = (count - 1) % 8
            expected = [f'{count:09d}', f'Example {count}', *prototypes[index][2:]]
            expected = [cell if cell else None for cell in expected]
            if stage >= 1:
                expected[5] = EXPECTED_NOTES[index]
            if stage >= 2:
                expected += [f'2026-10-{index + 1:02d}', 'normalized']
            if stage >= 3:
                expected += [COUNTRIES[index], 'classified']
            actual = json.loads(payload)
            assert row_id == count and actual == expected, f'Incorrect row {count} in stage {stage}'
            digest.update((json.dumps([row_id, actual], ensure_ascii=False) + '\n').encode())
    assert count == rows == dataset.row_count
    parts = list((artifact_directory(dataset.pk) / 'parquet').glob('part-*.parquet'))
    assert len(parts) == settings.SPARK_PARTITIONS
    return {'checked_rows': count, 'exact_cell_equality': True, 'ordered_digest_sha256': digest.hexdigest(),
        'verification_seconds': round(time.monotonic() - started, 3), 'parquet_partitions': len(parts),
        'artifact_bytes': sum(path.stat().st_size for path in artifact_directory(dataset.pk).rglob('*') if path.is_file())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=1_000_000)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert args.rows >= 8 and args.rows % 8 == 0
    owner = f'bench-{uuid.uuid4().hex}'
    work = settings.DATASET_ROOT / f'.{owner}'
    work.mkdir(parents=True)
    source_file = work / 'million.csv'
    with Path('/app/samples/contacts.csv').open(newline='', encoding='utf-8') as stream:
        source = list(csv.reader(stream))
    header, prototypes = source[0], source[1:]
    with source_file.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for row in range(1, args.rows + 1):
            writer.writerow([f'{row:09d}', f'Example {row}', *prototypes[(row - 1) % 8][2:]])
    source_hash = hashlib.file_digest(source_file.open('rb'), 'sha256').hexdigest()
    print(json.dumps({'event': 'fixture_ready', 'rows': args.rows, 'bytes': source_file.stat().st_size}), flush=True)
    connection = S3Connection.objects.create(owner_session=owner, bucket='benchmark-local-fixture',
        encrypted_credentials=b'', status='READY', expires_at=timezone.now() + timedelta(hours=1))
    result = {'rows': args.rows, 'fixture_bytes': source_file.stat().st_size, 'fixture_sha256': source_hash,
        'mode': 'synchronous worker pipeline, local CSV transport, preseeded validated LLM fixture cache; no S3/model calls',
        'spark_master': settings.SPARK_MASTER, 'spark_partitions': settings.SPARK_PARTITIONS,
        'environment': {'container_memory_limit': cgroup_value('memory.max'), 'cpu_max': cgroup_value('cpu.max'),
                        'machine': os.uname().machine}, 'stages': []}
    parent = None
    for stage, kind, name in [(0, 'IMPORT_DATASET', 'csv_import'), (1, 'APPLY_RULE', 'regex_replace'),
                               (2, 'APPLY_TRANSFORM', 'date_normalize_cached'), (3, 'APPLY_TRANSFORM', 'categorize_cached')]:
        dataset = Dataset.objects.create(owner_session=owner, parent=parent, connection=connection,
                                          source_key='million.csv', source_format='csv')
        job = Job.objects.create(owner_session=owner, kind=kind, dataset=dataset, connection=connection)
        if stage == 1:
            job.rule = RegexRule.objects.create(owner_session=owner, dataset=parent, column='c5', instruction='Mask emails',
                status='READY', pattern=r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', replacement='[EMAIL]', ignore_case=True)
            job.save(update_fields=['rule'])
        if stage in (2, 3):
            record = LLMTransformation.objects.create(owner_session=owner, dataset=parent, column='c3' if stage == 2 else 'c4',
                kind='DATE' if stage == 2 else 'CATEGORY', status='READY', model=settings.OPENAI_MODEL,
                options={'date_order': 'REJECT'} if stage == 2 else {'labels': ['USA', 'Australia', 'Other'], 'fallback': 'Other'})
            mappings = {}
            for index, row in enumerate(prototypes):
                value = row[3 if stage == 2 else 4]
                item = {'value': f'2026-10-{index + 1:02d}' if stage == 2 else COUNTRIES[index],
                        'status': 'normalized' if stage == 2 else 'classified'}
                mappings[value_cache_key(record, value)] = validate_item(item, value, record)
            cache.set_many(mappings, timeout=3600)
            job.transformation = record
            job.save(update_fields=['transformation'])
        def download(conn, key, target, report):
            import shutil
            shutil.copyfile(source_file, target)
            return {'source_bytes': source_file.stat().st_size, 'transport': 'local benchmark fixture'}
        stop = threading.Event()
        peaks = {'container_bytes': 0, 'process_rss_bytes': 0}
        def sample():
            while not stop.is_set():
                peaks['container_bytes'] = max(peaks['container_bytes'], int(cgroup_value('memory.current') or 0))
                peaks['process_rss_bytes'] = max(peaks['process_rss_bytes'], tree_rss())
                stop.wait(0.25)
        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
        started, cpu_start = time.monotonic(), cpu_seconds()
        try:
            with patch('processing.services.datasets.download_source', side_effect=download), \
                 patch('processing.services.transformations.request_batch', side_effect=AssertionError('Scale harness forbids provider calls')):
                run_job.run(str(job.pk))
        finally:
            elapsed, cpu_elapsed = time.monotonic() - started, cpu_seconds() - cpu_start
            stop.set(); monitor.join()
        job.refresh_from_db(); dataset.refresh_from_db()
        assert job.status == 'SUCCESS', f'{name}: {job.error_code}'
        checked = verify(dataset, prototypes, args.rows, stage)
        if stage == 1:
            assert dataset.metadata['matched_rows'] == args.rows * 3 // 8
            assert dataset.metadata['match_count'] == args.rows // 2
        if stage in (2, 3):
            assert dataset.metadata['llm_usage']['model_calls'] == 0
        entry = {'name': name, 'job_id': str(job.pk), 'dataset_id': str(dataset.pk),
            'elapsed_seconds': round(elapsed, 3), 'rows_per_second': round(args.rows / elapsed),
            'container_cpu_seconds': round(cpu_elapsed, 3),
            'peak_container_mib': round(peaks['container_bytes'] / 1048576, 1),
            'peak_process_rss_sum_mib': round(peaks['process_rss_bytes'] / 1048576, 1),
            'columns': len(dataset.columns), 'metadata': dataset.metadata, **checked}
        result['stages'].append(entry)
        Path(args.output).write_text(json.dumps(result, indent=2))
        print(json.dumps({'event': 'stage_verified', **entry}), flush=True)
        parent = dataset
    timings = []
    for index in range(100):
        after = (index * 9973) % (args.rows - 25)
        started = time.perf_counter()
        page = read_page(parent, after=after, limit=25)
        timings.append((time.perf_counter() - started) * 1000)
        assert [row['row_number'] for row in page['rows']] == list(range(after + 1, after + 26))
    result['pagination'] = {'requests': 100, 'rows_per_page': 25,
        'median_ms': round(statistics.median(timings), 3), 'p95_ms': round(sorted(timings)[94], 3),
        'max_ms': round(max(timings), 3), 'exact_rows': True, 'measurement': 'direct persisted-page service, not HTTP'}
    # Verify the original artifact is untouched after the full chain.
    original = Dataset.objects.get(pk=result['stages'][0]['dataset_id'])
    final_check = verify(original, prototypes, args.rows, 0)
    assert final_check['ordered_digest_sha256'] == result['stages'][0]['ordered_digest_sha256']
    result['source_preserved_after_chain'] = True
    result['complete'] = True
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(json.dumps({'event': 'benchmark_complete', 'report': args.output, 'pagination': result['pagination']}), flush=True)


if __name__ == '__main__':
    main()
