"""CSV authorization, exact full values, bounded download and attempt safety."""
import csv
from datetime import timedelta
import io
import json
from pathlib import Path
import uuid
from unittest.mock import MagicMock, patch

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job
from processing.services.datasets import DatasetCancelled, DatasetProblem, artifact_directory, create_spark
from processing.services.execution import cleanup_outputs
from processing.services.exports import export_path, prepare_csv
from processing.services.jobs import fail
from processing.services.recovery import recover_jobs, retry_job
from processing.tasks import run_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(settings, tmp_path):
    settings.DATASET_ROOT = tmp_path / 'artifacts'
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_X_CSRFTOKEN=client.get('/api/session/').data['csrf_token'])
    dataset = Dataset.objects.create(owner_session=client.session.session_key, status='READY', source_key='source.xlsx',
        source_format='xlsx', row_count=3, columns=[{'key': 'c0', 'name': 'Identifier'}, {'key': 'c1', 'name': 'Notes, "中文"'}])
    directory = artifact_directory(dataset.pk); directory.mkdir(parents=True)
    (directory / 'source-marker').write_bytes(b'original')
    return client, dataset


def ready_file(dataset, status='SUCCESS'):
    job = Job.objects.create(owner_session=dataset.owner_session, dataset=dataset, kind='EXPORT_CSV',
                             status=status, attempt_token=uuid.uuid4())
    path = export_path(job); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'\xef\xbb\xbfA,B\r\n1,2\r\n')
    return job, path


def test_submit_deduplicates_active_and_finished_exports_without_new_datasets(source):
    client, dataset = source
    url = f'/api/datasets/{dataset.pk}/export/'
    with patch('processing.views.dispatch', return_value=True) as dispatch:
        first = client.post(url, {}, format='json'); second = client.post(url, {}, format='json')
    assert first.status_code == second.status_code == 202 and first.data['id'] == second.data['id']
    assert dispatch.call_count == 1 and Dataset.objects.count() == 1
    job = Job.objects.get(pk=first.data['id']); job.status = 'SUCCESS'; job.attempt_token = uuid.uuid4(); job.save()
    path = export_path(job); path.parent.mkdir(parents=True); path.write_bytes(b'csv')
    assert client.post(url, {}, format='json').status_code == 200
    assert client.get(url).data['download_available']
    path.unlink()
    assert not client.get(url).data['download_available']
    with patch('processing.views.dispatch', return_value=True):
        regenerated = client.post(url, {}, format='json')
    assert regenerated.status_code == 202 and regenerated.data['id'] != first.data['id']


@pytest.mark.parametrize('status', ['PENDING', 'FAILED', 'CANCELLED'])
def test_nonready_dataset_is_rejected_before_queueing(source, status):
    client, dataset = source; dataset.status = status; dataset.save()
    with patch('processing.views.dispatch') as dispatch:
        assert client.post(f'/api/datasets/{dataset.pk}/export/', {}, format='json').status_code == 409
    dispatch.assert_not_called(); assert not Job.objects.exists()


def test_download_is_session_scoped_attachment_with_length_and_no_cache(source):
    client, dataset = source; job, path = ready_file(dataset)
    response = client.get(f'/api/jobs/{job.pk}/download/')
    assert response.status_code == 200 and response.streaming
    assert response['Content-Type'] == 'text/csv; charset=utf-8'
    assert response['Content-Length'] == str(path.stat().st_size)
    assert response['Cache-Control'] == 'no-store'
    assert response['Content-Disposition'] == f'attachment; filename="patternworks-{dataset.pk}.csv"'
    assert b''.join(response.streaming_content) == path.read_bytes()
    response.close()
    other = APIClient()
    for url in [f'/api/jobs/{job.pk}/download/', f'/api/datasets/{dataset.pk}/export/']:
        assert other.get(url).status_code == 404
    assert other.post(f'/api/datasets/{dataset.pk}/export/', {}, format='json').status_code == 404
    path.unlink()
    assert client.get(f'/api/jobs/{job.pk}/download/').status_code == 410


def test_download_requires_export_success_and_post_requires_csrf(source):
    client, dataset = source; job, path = ready_file(dataset, 'RUNNING')
    assert client.get(f'/api/jobs/{job.pk}/download/').status_code == 409
    job.kind = 'APPLY_RULE'; job.save()
    assert client.get(f'/api/jobs/{job.pk}/download/').status_code == 404
    client.credentials()
    assert client.post(f'/api/datasets/{dataset.pk}/export/', {}, format='json').status_code == 403


def test_queue_failure_and_cancel_cleanup_do_not_modify_source(source):
    client, dataset = source
    def broken_dispatch(job):
        fail(job.pk, 'QUEUE_UNAVAILABLE', 'The task queue is unavailable.')
        return False
    with patch('processing.views.dispatch', side_effect=broken_dispatch):
        assert client.post(f'/api/datasets/{dataset.pk}/export/', {}, format='json').status_code == 503
    job, path = ready_file(dataset, 'RUNNING')
    assert client.post(f'/api/jobs/{job.pk}/cancel/', {}, format='json').data['status'] == 'CANCELLED'
    cleanup_outputs(job, cancelled=True)
    assert not path.exists()
    dataset.refresh_from_db(); assert dataset.status == 'READY'
    assert (artifact_directory(dataset.pk) / 'source-marker').read_bytes() == b'original'
    retried = retry_job(Job.objects.get(pk=job.pk))
    assert retried.dataset_id == dataset.pk and retried.pk != job.pk and Dataset.objects.count() == 1


def test_recovery_removes_old_export_fences_old_attempt_and_retains_source(source):
    _, dataset = source; job, old_path = ready_file(dataset, 'RUNNING')
    Job.objects.filter(pk=job.pk).update(heartbeat_at=timezone.now()-timedelta(hours=1))
    with patch('processing.services.recovery.dispatch', return_value=True):
        assert recover_jobs()['requeued'] == 1
    assert not old_path.exists()
    current = Job.objects.get(pk=job.pk); current.attempt_token = uuid.uuid4(); current.status='RUNNING'; current.save()
    new_path = export_path(current); new_path.parent.mkdir(exist_ok=True, parents=True); new_path.write_bytes(b'new attempt')
    cleanup_outputs(job)
    assert new_path.read_bytes() == b'new attempt'
    dataset.refresh_from_db(); assert dataset.status == 'READY'


@pytest.mark.spark
@pytest.mark.parametrize('empty', [False, True], ids=['full-values', 'header-only'])
def test_real_spark_export_exact_order_long_values_unicode_quoting_and_empty(source, empty):
    client, dataset = source
    values = [] if empty else [['000001', 'a,"b"\r\n中文\n$1\\  '], ['000002', 'x'*5000 + 'TAIL'], ['=1+1', None]]
    dataset.row_count = len(values); dataset.save()
    spark = create_spark('export-fixture')
    try:
        from pyspark.sql.types import StructType, StructField, StringType, LongType
        schema = StructType([StructField('_row_id', LongType(), False), StructField('c0', StringType()), StructField('c1', StringType())])
        rows = [(i, *v) for i,v in reversed(list(enumerate(values,1)))]
        spark.createDataFrame(rows, schema).repartition(4).write.parquet(str(artifact_directory(dataset.pk)/'parquet'))
    finally:
        spark.stop()
    # Deliberately no preview SQLite file: export must read persisted full data.
    job = Job.objects.create(owner_session=dataset.owner_session, dataset=dataset, kind='EXPORT_CSV')
    run_job.run(str(job.pk)); job.refresh_from_db(); dataset.refresh_from_db()
    assert job.status == 'SUCCESS', job.error_code
    response = client.get(f'/api/jobs/{job.pk}/download/'); raw = b''.join(response.streaming_content); response.close()
    assert raw.startswith(b'\xef\xbb\xbf') and int(response['Content-Length']) == len(raw)
    parsed = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
    assert parsed == [['Identifier', 'Notes, "中文"']] + [[v if v is not None else '' for v in row] for row in values]
    assert job.result['row_count'] == len(values) and job.result['bytes'] == len(raw)
    assert dataset.status == 'READY' and Dataset.objects.count() == 1


def test_missing_full_artifact_fails_cleanly_and_retry_uses_same_source(source):
    _, dataset = source
    job = Job.objects.create(owner_session=dataset.owner_session, dataset=dataset, kind='EXPORT_CSV')
    run_job.run(str(job.pk)); job.refresh_from_db()
    assert job.status == 'FAILED' and job.error_code == 'ARTIFACT_UNAVAILABLE'
    assert retry_job(job).dataset_id == dataset.pk
    dataset.refresh_from_db(); assert dataset.status == 'READY'


@pytest.mark.parametrize('case,code', [('out-of-order','EXPORT_ORDER'), ('missing-row','EXPORT_ROWS'), ('late-cancel',None)])
def test_invalid_or_cancelled_export_never_publishes_partial_file(source, case, code):
    _, dataset = source
    (artifact_directory(dataset.pk)/'parquet').mkdir()
    job = Job.objects.create(owner_session=dataset.owner_session, dataset=dataset, kind='EXPORT_CSV',
                             status='RUNNING', attempt_token=uuid.uuid4())
    rows = [{'_row_id': i, 'c0':str(i), 'c1':'complete'} for i in ([2,1,3] if case=='out-of-order' else [1,2] if case=='missing-row' else [1,2,3])]
    spark = MagicMock()
    def write_parts(target):
        Path(target).mkdir()
        (Path(target)/'part-000.json').write_text('\n'.join(json.dumps(row) for row in rows))
    spark.read.parquet.return_value.select.return_value.orderBy.return_value.write.json.side_effect = write_parts
    def report(stage, progress):
        if case=='late-cancel' and progress==95:
            Job.objects.filter(pk=job.pk).update(status='CANCELLED')
    with patch('processing.services.exports.create_spark', return_value=spark):
        with pytest.raises(DatasetProblem if code else DatasetCancelled) as error:
            prepare_csv(job, report)
    if code: assert error.value.code==code
    assert not export_path(job).exists()
    assert not list(artifact_directory(dataset.pk).parent.glob('.import-*'))
    dataset.refresh_from_db(); assert dataset.status=='READY'
    spark.stop.assert_called_once()
