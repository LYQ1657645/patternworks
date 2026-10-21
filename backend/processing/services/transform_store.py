"""Disk-backed distinct values and validated mappings, scoped to an immutable plan.

The row index handles short input. Possibly shortened values trigger a streaming
read of canonical Parquet before model work. No input is silently truncated.
State belongs to the source artifact, so lifecycle purge removes it as well.
"""
from contextlib import contextmanager, closing
import fcntl
import json
import math
from pathlib import Path
import sqlite3
import time

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import F

from ..models import Job, LLMTransformation
from .datasets import artifact_directory, DatasetCancelled
from .rules import RuleProblem


class TransformYield(Exception):
    """A durable plan has more work; release the worker for the next time slice."""


@contextmanager
def store(record):
    directory = artifact_directory(record.dataset_id) / '.transformations' / str(record.pk)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuleProblem('TRANSFORM_BUSY', 'This transformation is already processing. Wait and retry.', True) from None
        with closing(sqlite3.connect(directory / 'state.sqlite3', timeout=20)) as database:
            database.execute('PRAGMA journal_mode=WAL')
            database.execute('CREATE TABLE IF NOT EXISTS values_map (value TEXT PRIMARY KEY, result TEXT, origin TEXT)')
            database.execute('CREATE INDEX IF NOT EXISTS pending_values ON values_map(result, value)')
            database.execute('CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value TEXT)')
            database.commit()
            yield database, directory


def fill_values(database, values, record, report):
    from .transformations import MAX_VALUE
    batch, last = [], time.monotonic()
    for value in values:
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > MAX_VALUE:
            raise RuleProblem('TRANSFORM_VALUE_TOO_LONG', f'A selected value exceeds {MAX_VALUE} characters. Nothing was truncated.')
        item = json.dumps({'value': None, 'status': 'missing'}) if not value.strip() else None
        batch.append((value, item, 'local' if item else None))
        if len(batch) == 512:
            database.executemany('INSERT OR IGNORE INTO values_map VALUES (?, ?, ?)', batch)
            database.commit()
            batch.clear()
            if time.monotonic() - last > .5:
                report('Counting distinct values for the full column', 25)
                last = time.monotonic()
    database.executemany('INSERT OR IGNORE INTO values_map VALUES (?, ?, ?)', batch)
    database.execute("INSERT OR REPLACE INTO state VALUES ('profiled', 'yes')")
    database.commit()


def profile_index(database, record, report):
    if database.execute("SELECT 1 FROM state WHERE name='profiled'").fetchone():
        return
    source = artifact_directory(record.dataset_id) / 'rows.sqlite3'
    if not source.is_file():
        raise RuleProblem('ARTIFACT_UNAVAILABLE', 'The full-column index is unavailable. Import the file again.')
    position = next((i for i, c in enumerate(record.dataset.columns) if c['key'] == record.column), None)
    if position is None:
        raise RuleProblem('TRANSFORM_COLUMN', 'The selected column is unavailable.')
    class NeedFullValues(Exception):
        pass
    def short_values(rows):
        for (value,) in rows:
            if isinstance(value, str) and len(value) >= settings.PREVIEW_CELL_CHARACTERS:
                raise NeedFullValues()
            yield value
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as index:
            rows = index.execute('SELECT json_extract(cells, ?) FROM rows ORDER BY row_id', [f'$[{position}]'])
            fill_values(database, short_values(rows), record, report)
    except NeedFullValues:
        from .datasets import create_spark
        from pyspark.sql import functions as f
        parquet = artifact_directory(record.dataset_id) / 'parquet'
        if not parquet.is_dir():
            raise RuleProblem('ARTIFACT_UNAVAILABLE', 'Complete source values are unavailable. Import the file again.') from None
        spark = create_spark(getattr(getattr(report, 'job', None), 'pk', record.pk))
        try:
            if hasattr(report, 'bind_spark'):
                report.bind_spark(spark)
            frame = spark.read.parquet(str(parquet))
            values = frame.select(record.column).where(f.col(record.column).isNotNull()).distinct().repartition(64).toLocalIterator()
            fill_values(database, (row[0] for row in values), record, report)
        finally:
            spark.stop()


def hydrate(database, record, report):
    from .transformations import value_cache_key, validate_item
    if database.execute("SELECT 1 FROM state WHERE name='cache_checked'").fetchone():
        return
    rows = database.execute('SELECT value FROM values_map WHERE result IS NULL ORDER BY value')
    last = time.monotonic()
    while batch := rows.fetchmany(256):
        keys = {value: value_cache_key(record, value) for (value,) in batch}
        try:
            cached = cache.get_many(list(keys.values()))
        except Exception:
            raise RuleProblem('TRANSFORM_CACHE_UNAVAILABLE', 'Redis is unavailable. No uncached model request was made.') from None
        restored = []
        for value, key in keys.items():
            try:
                if key in cached:
                    restored.append((json.dumps(validate_item(cached[key], value, record)), 'cache', value))
            except RuleProblem:
                pass
        database.executemany('UPDATE values_map SET result=?, origin=? WHERE value=?', restored)
        database.commit()
        if time.monotonic() - last > .5:
            report('Checking cached values and saved progress', 30)
            last = time.monotonic()
    database.execute("INSERT OR REPLACE INTO state VALUES ('cache_checked', 'yes')")
    database.commit()


def save_plan(database, record):
    from .transformations import BATCH_SIZE, MAX_BATCH_BYTES, batches
    total, pending = database.execute('SELECT count(*), count(*)-count(result) FROM values_map').fetchone()
    record.refresh_from_db(fields=['request_budget', 'requests_used', 'requests_completed', 'input_tokens', 'output_tokens'])
    # Values are immutable after profiling. Avoid rescanning every long-running
    # plan merely to decide whether the fixed-count fast estimate is safe.
    saved = database.execute("SELECT value FROM state WHERE name='max_value_bytes'").fetchone()
    maximum = int(saved[0]) if saved else (database.execute('SELECT max(length(CAST(value AS BLOB))) FROM values_map').fetchone()[0] or 0)
    if not saved:
        database.execute("INSERT INTO state VALUES ('max_value_bytes', ?)", [str(maximum)])
        database.commit()
    requests = (math.ceil(pending / BATCH_SIZE) if (maximum + 64) * BATCH_SIZE <= MAX_BATCH_BYTES else
                sum(1 for _ in batches(row[0] for row in database.execute('SELECT value FROM values_map WHERE result IS NULL ORDER BY value'))))
    plan = {'distinct_values': total, 'pending_values': pending,
            'estimated_new_requests': requests,
            'remaining_requests': max(0, record.request_budget - record.requests_used)}
    LLMTransformation.objects.filter(pk=record.pk).update(plan=plan)
    record.plan = plan
    return plan


def reserve_request(record, report):
    """Charge the request budget BEFORE transmission, including unknown outcomes."""
    report('Reserving one model request', 45)
    with transaction.atomic():
        job = getattr(report, 'job', None)
        if job:
            current = Job.objects.select_for_update().get(pk=job.pk)
            if current.status != 'RUNNING' or current.attempt_token != job.attempt_token:
                raise DatasetCancelled()
        current = LLMTransformation.objects.select_for_update().get(pk=record.pk)
        if current.requests_used >= current.request_budget:
            raise RuleProblem('TRANSFORM_BUDGET', 'Model request budget reached. Increase the budget in Transform, then Apply to resume.')
        LLMTransformation.objects.filter(pk=record.pk).update(requests_used=F('requests_used') + 1)


def record_usage(record, usage):
    LLMTransformation.objects.filter(pk=record.pk).update(
        requests_completed=F('requests_completed') + 1,
        input_tokens=F('input_tokens') + max(0, int(usage.get('input_tokens', 0))),
        output_tokens=F('output_tokens') + max(0, int(usage.get('output_tokens', 0))))


def process(database, record, report):
    from .transformations import BATCH_SIZE, batches, request_batch, validate_item, value_cache_key
    plan = save_plan(database, record)
    if plan['estimated_new_requests'] > plan['remaining_requests']:
        raise RuleProblem('TRANSFORM_BUDGET',
            f"Full column needs up to {plan['estimated_new_requests']:,} new requests; {plan['remaining_requests']:,} remain. Increase the request budget and Apply again. Saved progress is kept.")
    calls = 0
    pending = plan['pending_values']
    while batch := [r[0] for r in database.execute('SELECT value FROM values_map WHERE result IS NULL ORDER BY value LIMIT ?', [BATCH_SIZE])]:
        batch = next(batches(batch))
        if calls >= settings.TRANSFORM_REQUESTS_PER_SLICE:
            save_plan(database, record)
            raise TransformYield()
        reserve_request(record, report)
        outputs, usage = request_batch(record, batch)
        record_usage(record, usage)
        if len(outputs) != len(batch):
            raise RuleProblem('LLM_INVALID_OUTPUT', 'The model returned an incomplete batch.')
        validated = [(value, validate_item(item, value, record)) for value, item in zip(batch, outputs)]
        report('Saving validated batch progress', 50)
        # Save the durable result before Redis; Redis expiry/outage cannot erase paid progress.
        database.executemany('UPDATE values_map SET result=?, origin=? WHERE value=?',
            [(json.dumps(item), 'model', value) for value, item in validated])
        database.commit()
        try:
            cache.set_many({value_cache_key(record, value): item for value, item in validated}, timeout=settings.RULE_CACHE_TTL_SECONDS)
        except Exception:
            raise RuleProblem('TRANSFORM_CACHE_UNAVAILABLE', 'Batch progress is saved. Redis is unavailable; retry when it recovers.') from None
        calls += 1
        pending -= len(batch)
        report(f'Processed {plan["distinct_values"] - pending:,} of {plan["distinct_values"]:,} distinct values',
               45 + int(13 * (plan['distinct_values'] - pending) / max(1, plan['distinct_values'])))
    save_plan(database, record)


def prepare(record, report):
    with store(record) as (database, directory):
        profile_index(database, record, report)
        hydrate(database, record, report)
        process(database, record, report)


def export_mapping(database, directory, output_key, status_key):
    output = directory / 'mapping.jsonl'
    with output.open('w', encoding='utf-8') as stream:
        for value, raw in database.execute('SELECT value, result FROM values_map ORDER BY value'):
            if raw is None:
                raise RuleProblem('TRANSFORM_INCOMPLETE', 'Some values have not been processed. Resume the transformation first.')
            item = json.loads(raw)
            stream.write(json.dumps({'_value_key': value, output_key: item['value'], status_key: item['status']}, ensure_ascii=False) + '\n')
    return output
