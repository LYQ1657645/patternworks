"""Multi-column rules: request compatibility, complete previews, atomic Spark output."""
from datetime import timedelta
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job, RegexRule, S3Connection
from processing.serializers import RegexRuleSerializer
from processing.services.credentials import encrypt_credentials
from processing.services.datasets import artifact_directory, build_page_index, column_samples, create_spark
from processing.services.recovery import retry_job
from processing.services.rules import generate_rule
from processing.tasks import run_job

pytestmark = pytest.mark.django_db
PATTERN = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}'
OUTPUT = {'supported': True, 'pattern': PATTERN, 'replacement': 'MASK', 'ignore_case': False,
          'explanation': 'Mask email addresses.', 'positive_examples': ['a@example.com'], 'negative_examples': ['no email']}
VALUES = [
    ['a@example.com', 'a@example.com and b@example.com', 'keep@example.com'],
    [None, 'only c@example.com', 'keep@example.com'],
    ['not email', 'a' * 300, 'keep@example.com'],
    ['d@example.com', None, 'keep@example.com'],
    ['x' * 4100 + ' e@example.com', 'f@example.com', 'keep@example.com'],
    [None, None, 'keep@example.com'],
]


def quiet(*args):
    pass


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def browser():
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_X_CSRFTOKEN=client.get('/api/session/').data['csrf_token'])
    return client


@pytest.fixture
def source(settings, tmp_path, browser):
    settings.DATASET_ROOT = tmp_path / 'artifacts'
    record = Dataset.objects.create(owner_session=browser.session.session_key, source_key='multi.csv', source_format='csv',
        status='READY', row_count=len(VALUES), columns=[{'key': f'c{i}', 'name': name, 'type': 'string'}
                                                     for i, name in enumerate(['Email', 'Notes', 'Keep'])])
    directory = artifact_directory(record.pk); directory.mkdir(parents=True)
    parts = tmp_path / 'parts'; parts.mkdir()
    (parts / 'part-000.json').write_text('\n'.join(json.dumps({'_row_id': i, **dict(zip(['c0', 'c1', 'c2'], row))})
                                                 for i, row in enumerate(VALUES, 1)))
    build_page_index(parts, directory / 'rows.sqlite3', record.columns, quiet)
    return record


@pytest.mark.parametrize('body', [
    {}, {'columns': []}, {'columns': ['c0', 'c0']}, {'columns': ['c99']},
    {'columns': ['c0', 'c99']}, {'columns': None}, {'columns': 'c0'},
    {'columns': ['c0'], 'column': 'c0'}, {'columns': ['c0'] * 257}, {'columns': ['not-a-key']},
])
def test_invalid_targets_never_queue_or_create_rule(source, browser, body):
    with patch('processing.views.dispatch') as dispatch:
        response = browser.post(f'/api/datasets/{source.pk}/rules/', {**body, 'instruction': 'Mask emails'}, format='json')
    assert response.status_code == 400
    assert not RegexRule.objects.exists() and not Job.objects.exists()
    dispatch.assert_not_called()


@pytest.mark.parametrize('body,columns', [({'column': 'c0'}, ['c0']), ({'columns': ['c1', 'c0']}, ['c1', 'c0'])])
def test_legacy_and_multi_requests_persist_targets_before_queue(source, browser, body, columns):
    with patch('processing.views.dispatch', return_value=True):
        response = browser.post(f'/api/datasets/{source.pk}/rules/',
            {**body, 'instruction': 'Mask emails', 'replacement': '$1\\中文  '}, format='json')
    assert response.status_code == 202
    job = Job.objects.get(pk=response.data['id'])
    assert job.rule.columns == columns and job.rule.column == columns[0]
    assert job.parameters == {'replacement': '$1\\中文  '}
    # Selection survives failure/retry without mutating the old audit record.
    job.status = 'FAILED'; job.save(update_fields=['status'])
    retried = retry_job(job)
    assert retried.pk != job.pk and retried.rule_id != job.rule_id
    assert retried.rule.target_columns == columns and retried.parameters == job.parameters


def test_legacy_rule_serialization_and_session_isolation(source, browser):
    rule = RegexRule.objects.create(owner_session=source.owner_session, dataset=source, column='c1', instruction='Mask')
    assert RegexRuleSerializer(rule).data['columns'] == ['c1']
    stranger = APIClient()
    assert stranger.get(f'/api/rules/{rule.pk}/').status_code == 404
    assert stranger.get(f'/api/datasets/{source.pk}/rules/').status_code == 404


def test_preview_has_per_column_counts_union_rows_and_one_shared_cache(source):
    rule = RegexRule.objects.create(owner_session=source.owner_session, dataset=source,
        column='c0', columns=['c0', 'c1'], instruction='Find email addresses')
    with patch('processing.services.rules.request_rule', return_value=(OUTPUT, {})) as model:
        first = generate_rule(rule, quiet, replacement='MASK')
        second = generate_rule(rule, quiet, replacement='')
        other = RegexRule.objects.create(owner_session=source.owner_session, dataset=source,
            column='c2', columns=['c2', 'c1'], instruction=rule.instruction)
        third = generate_rule(other, quiet, replacement='X')
    assert model.call_count == 1 and second['cache_hit'] and third['cache_hit']
    preview = first['preview']
    assert (preview['matched_rows'], preview['matched_cells'], preview['match_count'], preview['changed_rows']) == (4, 6, 7, 4)
    assert [(p['column'], p['matched_rows'], p['match_count']) for p in preview['column_previews']] == [('c0', 3, 3), ('c1', 3, 4)]
    assert preview['column_previews'][0]['examples'][4]['before_truncated']
    assert preview['column_previews'][0]['examples'][4]['matched']  # match occurs after the display boundary
    assert second['preview']['column_previews'][0]['examples'][0]['after'] == ''
    assert third['preview']['column_previews'][0]['examples'][0]['after'] == 'X'


def test_very_wide_preview_remains_bounded(settings, tmp_path):
    settings.DATASET_ROOT = tmp_path / 'artifacts'
    columns = [{'key': f'c{i}', 'name': f'Column {i}', 'type': 'string'} for i in range(256)]
    source = Dataset.objects.create(owner_session='wide', source_key='wide.csv', source_format='csv', status='READY', row_count=1, columns=columns)
    target = artifact_directory(source.pk); target.mkdir(parents=True)
    parts = tmp_path / 'parts'; parts.mkdir()
    (parts / 'part-0.json').write_text(json.dumps({'_row_id': 1, **{c['key']: '界' * 3000 + ' a@example.com' for c in columns}}))
    build_page_index(parts, target / 'rows.sqlite3', columns, quiet)
    rule = RegexRule.objects.create(owner_session='wide', dataset=source, column='c0', columns=[c['key'] for c in columns], instruction='Find emails')
    with patch('processing.services.rules.request_rule', return_value=(OUTPUT, {})) as model:
        preview = generate_rule(rule, quiet, replacement='MASK')['preview']
    assert model.call_count == 1 and preview['matched_rows'] == 1 and preview['matched_cells'] == 256
    assert len(preview['column_previews']) == 256
    assert len(json.dumps(preview, ensure_ascii=False).encode()) < 1024 * 1024


@pytest.mark.spark
def test_real_multi_spark_atomic_apply_stats_retry_and_legacy_sample(settings, tmp_path):
    settings.DATASET_ROOT = tmp_path / 'artifacts'
    connection = S3Connection.objects.create(owner_session='multi', bucket='synthetic-fixtures', status='READY',
        encrypted_credentials=encrypt_credentials({'access_key_id': 'FAKE', 'secret_access_key': 'FAKE'}),
        expires_at=timezone.now() + timedelta(hours=1))
    fixture = tmp_path / 'multi.csv'
    with fixture.open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(['Email', 'Notes', 'Keep']); writer.writerows(VALUES)
    source = Dataset.objects.create(owner_session='multi', connection=connection, source_key='multi.csv', source_format='csv')
    imported = Job.objects.create(owner_session='multi', connection=connection, dataset=source, kind='IMPORT_DATASET')
    def download(conn, key, target, report):
        import shutil
        shutil.copyfile(fixture, target)
        return {'source_bytes': fixture.stat().st_size}
    with patch('processing.services.datasets.download_source', side_effect=download):
        run_job.run(str(imported.pk))
    source.refresh_from_db(); assert source.status == 'READY'
    source_files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (artifact_directory(source.pk) / 'parquet').glob('part-*')}
    with sqlite3.connect(artifact_directory(source.pk) / 'rows.sqlite3') as db:
        db.execute('DROP TABLE full_samples')
    rule = RegexRule.objects.create(owner_session='multi', dataset=source, column='c0', columns=['c0', 'c1'], instruction='Find emails')
    generated = Job.objects.create(owner_session='multi', kind='GENERATE_RULE', rule=rule, parameters={'replacement': '$1\\中文  '})
    with patch('processing.services.rules.request_rule', return_value=(OUTPUT, {})), patch('processing.services.datasets.create_spark', wraps=create_spark) as starter:
        run_job.run(str(generated.pk))
        assert starter.call_count == 1  # one bounded legacy read for all targets
    rule.refresh_from_db(); assert rule.preview['matched_cells'] == 6
    result = Dataset.objects.create(owner_session='multi', parent=source, source_key='multi.csv', source_format='csv')
    applied = Job.objects.create(owner_session='multi', dataset=result, rule=rule, kind='APPLY_RULE')
    run_job.run(str(applied.pk)); applied.refresh_from_db(); result.refresh_from_db()
    assert applied.status == 'SUCCESS', applied.error_code
    assert result.metadata['columns'] == ['c0', 'c1']
    assert {k: result.metadata[k] for k in ['matched_rows', 'matched_cells', 'match_count', 'changed_rows', 'changed_cells']} == {
        'matched_rows': 4, 'matched_cells': 6, 'match_count': 7, 'changed_rows': 4, 'changed_cells': 6}
    assert result.metadata['column_stats'] == {'c0': {'matched_rows': 3, 'match_count': 3, 'changed_rows': 3},
                                               'c1': {'matched_rows': 3, 'match_count': 4, 'changed_rows': 3}}
    marker = '$1\\中文  '
    expected = [[marker, marker + ' and ' + marker, 'keep@example.com'],
                [None, 'only ' + marker, 'keep@example.com'], ['not email', 'a' * 300, 'keep@example.com'],
                [marker, None, 'keep@example.com'], ['x' * 4100 + ' ' + marker, marker, 'keep@example.com'],
                [None, None, 'keep@example.com']]
    with column_samples(result, ['c0', 'c1', 'c2'], quiet) as rows:
        assert list(rows) == list(enumerate(expected, 1))
    # A failure in one column publishes no partially changed dataset.
    growing = RegexRule.objects.create(owner_session='multi', dataset=source, column='c0', columns=['c0', 'c1'],
        instruction='Replace a', status='READY', pattern='a', replacement='r' * 256)
    failed_result = Dataset.objects.create(owner_session='multi', parent=source, source_key='multi.csv', source_format='csv')
    failed = Job.objects.create(owner_session='multi', dataset=failed_result, rule=growing, kind='APPLY_RULE')
    run_job.run(str(failed.pk)); failed.refresh_from_db()
    assert failed.status == 'FAILED' and failed.error_code == 'OUTPUT_TOO_LARGE'
    assert not artifact_directory(failed_result.pk).exists()
    growing.replacement = 'Q'; growing.save(update_fields=['replacement'])
    retried = retry_job(failed)
    run_job.run(str(retried.pk)); retried.refresh_from_db(); retried.dataset.refresh_from_db()
    assert retried.status == 'SUCCESS' and retried.dataset_id != failed_result.pk
    with column_samples(retried.dataset, ['c1', 'c2'], quiet) as rows:
        assert list(rows)[2][1] == ['Q' * 300, 'keep@example.com']
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (artifact_directory(source.pk) / 'parquet').glob('part-*')} == source_files


@pytest.mark.spark
@pytest.mark.parametrize('values', [[], [[None, None]]], ids=['empty', 'nulls'])
def test_empty_and_null_multi_column_spark_output(settings, tmp_path, values):
    settings.DATASET_ROOT = tmp_path / 'artifacts'
    spark = create_spark('empty-multi')
    try:
        from pyspark.sql.types import StructType, StructField, StringType, LongType
        source = Dataset.objects.create(owner_session='empty', source_key='empty.csv', source_format='csv', status='READY',
            row_count=len(values), columns=[{'key': f'c{i}', 'name': str(i), 'type': 'string'} for i in range(2)])
        target = artifact_directory(source.pk); target.mkdir(parents=True)
        schema = StructType([StructField('_row_id', LongType())] + [StructField(f'c{i}', StringType()) for i in range(2)])
        frame = spark.createDataFrame([(i, *row) for i, row in enumerate(values, 1)], schema)
        frame.write.parquet(str(target / 'parquet'))
    finally:
        spark.stop()
    rule = RegexRule.objects.create(owner_session='empty', dataset=source, column='c0', columns=['c0', 'c1'], status='READY', pattern='x', replacement='Y')
    result = Dataset.objects.create(owner_session='empty', parent=source, source_key='empty.csv', source_format='csv')
    job = Job.objects.create(owner_session='empty', dataset=result, rule=rule, kind='APPLY_RULE')
    run_job.run(str(job.pk)); job.refresh_from_db(); result.refresh_from_db()
    assert job.status == 'SUCCESS' and result.row_count == len(values)
    assert all(result.metadata[key] == 0 for key in ['matched_rows', 'matched_cells', 'match_count', 'changed_rows', 'changed_cells'])


@pytest.mark.spark
def test_maximum_256_selected_columns_apply_in_one_spark_job(settings, tmp_path):
    settings.DATASET_ROOT = tmp_path / 'artifacts'
    count = 256
    source = Dataset.objects.create(owner_session='maximum', source_key='wide.csv', source_format='csv', status='READY', row_count=1,
        columns=[{'key': f'c{i}', 'name': f'Column {i}', 'type': 'string'} for i in range(count)])
    target = artifact_directory(source.pk); target.mkdir(parents=True)
    spark = create_spark('maximum-targets')
    try:
        frame = spark.createDataFrame([(1, *(['a@example.com'] * count))], ['_row_id'] + [f'c{i}' for i in range(count)])
        frame.write.parquet(str(target / 'parquet'))
    finally:
        spark.stop()
    rule = RegexRule.objects.create(owner_session='maximum', dataset=source, column='c0', columns=[f'c{i}' for i in range(count)],
        status='READY', pattern=PATTERN, replacement='$1\\中文')
    result = Dataset.objects.create(owner_session='maximum', parent=source, source_key='wide.csv', source_format='csv')
    job = Job.objects.create(owner_session='maximum', dataset=result, rule=rule, kind='APPLY_RULE')
    run_job.run(str(job.pk)); job.refresh_from_db(); result.refresh_from_db()
    assert job.status == 'SUCCESS', job.error_code
    assert result.metadata['matched_rows'] == result.metadata['changed_rows'] == 1
    assert result.metadata['matched_cells'] == result.metadata['match_count'] == result.metadata['changed_cells'] == count
    assert len(result.metadata['column_stats']) == count
    with column_samples(result, rule.columns, quiet) as rows:
        assert list(rows) == [(1, ['$1\\中文'] * count)]
