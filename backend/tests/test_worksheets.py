from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import io

from botocore.response import StreamingBody
from django.utils import timezone
from openpyxl import Workbook
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job, S3Connection
from processing.services.worksheets import list_worksheets
from processing.services.datasets import DatasetProblem


def workbook_bytes():
    book = Workbook()
    book.active.title = 'Contacts'
    book.create_sheet('客户 数据')
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def stub_source(content):
    def download(connection, key, target, report):
        Path(target).write_bytes(content)
    return download


def test_tabs_keep_order_and_unicode_without_importing_cells():
    with patch('processing.services.worksheets.download_source', side_effect=stub_source(workbook_bytes())):
        assert list_worksheets(None, 'folder/book.XLSX')['sheet_names'] == ['Contacts', '客户 数据']


def test_legacy_xls_tabs():
    with patch('processing.services.worksheets.download_source', side_effect=stub_source(b'xls')), patch('xlrd.open_workbook') as load:
        load.return_value.sheet_names.return_value = ['First', 'Second']
        assert list_worksheets(None, 'book.xls')['sheet_names'] == ['First', 'Second']
        load.return_value.release_resources.assert_called_once()


@pytest.mark.parametrize('content,code', [(b'not Excel', 'EXCEL_INVALID')])
def test_bad_workbook_is_actionable(content, code):
    with patch('processing.services.worksheets.download_source', side_effect=stub_source(content)), pytest.raises(DatasetProblem) as exc:
        list_worksheets(None, 'book.xlsx')
    assert exc.value.code == code


def test_expanded_limit_applies_before_reading_xml(settings):
    settings.MAX_EXCEL_EXPANDED_BYTES = 1
    with patch('processing.services.worksheets.download_source', side_effect=stub_source(workbook_bytes())), pytest.raises(DatasetProblem) as exc:
        list_worksheets(None, 'book.xlsx')
    assert exc.value.code == 'EXCEL_TOO_LARGE'


@pytest.mark.django_db
def test_endpoint_queues_without_s3_and_reuses_pending_job():
    client = APIClient()
    client.get('/api/session/')
    connection = S3Connection.objects.create(owner_session=client.session.session_key, bucket='test-bucket',
        encrypted_credentials=b'fake', status='READY', expires_at=timezone.now() + timedelta(hours=1))
    url = f'/api/connections/{connection.pk}/worksheets/'
    with patch('processing.views.dispatch', return_value=True) as dispatch, patch('processing.services.worksheets.download_source') as download:
        response = client.post(url, {'key': 'book.xlsx'}, format='json')
        assert response.status_code == 202 and response.data['kind'] == 'LIST_WORKSHEETS'
        again = client.post(url, {'key': 'book.xlsx'}, format='json')
        assert again.data['id'] == response.data['id']
        assert client.get(url, {'key': 'book.xlsx'}).status_code == 405
        assert client.post(url, {'key': 'book.csv'}, format='json').status_code == 400
        assert client.post(url, {'key': ''}, format='json').status_code == 400
        assert APIClient().post(url, {'key': 'book.xlsx'}, format='json').status_code == 404
        connection.expires_at = timezone.now() - timedelta(seconds=1)
        connection.save()
        assert client.post(url, {'key': 'book.xlsx'}, format='json').status_code == 410
        download.assert_not_called()
        dispatch.assert_called_once()
    assert Dataset.objects.count() == 0 and Job.objects.count() == 1


@pytest.mark.django_db
def test_wrong_sheet_retry_does_not_create_another_failure():
    client = APIClient()
    client.get('/api/session/')
    job = Job.objects.create(owner_session=client.session.session_key, kind='IMPORT_DATASET', status='FAILED', error_code='SHEET_NOT_FOUND')
    hint = client.get(f'/api/jobs/{job.pk}/').data
    assert not hint['retry_allowed']
    assert 'worksheet selection' in hint['retry_unavailable_reason']
    assert client.post(f'/api/jobs/{job.pk}/retry/', {}, format='json').status_code == 409
    assert Job.objects.count() == 1


@pytest.fixture
def worksheet_job(settings, tmp_path):
    settings.DATASET_ROOT = tmp_path
    connection = S3Connection.objects.create(owner_session='test', bucket='test-bucket',
        encrypted_credentials=b'fake', status='READY', expires_at=timezone.now() + timedelta(hours=1))
    return Job.objects.create(owner_session='test', connection=connection, kind='LIST_WORKSHEETS', parameters={'key': 'book.xlsx'})


@pytest.mark.django_db
def test_worker_reads_persists_and_removes_attempt_staging(worksheet_job, settings):
    from processing.tasks import run_job
    with patch('processing.services.worksheets.download_source', side_effect=stub_source(workbook_bytes())):
        run_job.run(str(worksheet_job.pk))
    worksheet_job.refresh_from_db()
    assert worksheet_job.status == 'SUCCESS'
    assert worksheet_job.result == {'sheet_names': ['Contacts', '客户 数据'], 'source_key': 'book.xlsx'}
    assert not list(settings.DATASET_ROOT.glob('.import-*'))
    assert Dataset.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize('action', ['cancel', 'fence'])
def test_cancel_and_fencing_never_publish_tabs(worksheet_job, settings, action):
    import uuid
    from processing.tasks import run_job
    def interrupted(connection, key, target, report):
        Path(target).write_bytes(workbook_bytes())
        if action == 'cancel': Job.objects.filter(pk=worksheet_job.pk).update(status='CANCELLED')
        else: Job.objects.filter(pk=worksheet_job.pk).update(attempt_token=uuid.uuid4(), status='QUEUED')
        report('Downloading source from S3', 25)
    with patch('processing.services.worksheets.download_source', side_effect=interrupted):
        run_job.run(str(worksheet_job.pk))
    worksheet_job.refresh_from_db()
    assert worksheet_job.status == ('CANCELLED' if action == 'cancel' else 'QUEUED')
    assert worksheet_job.result == {}
    assert not list(settings.DATASET_ROOT.glob('.import-*'))


@pytest.mark.django_db
def test_retry_and_worker_recovery_keep_key_without_creating_dataset(worksheet_job, settings):
    from processing.services.recovery import retry_job, recover_jobs
    from processing.services.retry_policy import retry_problem
    import uuid
    worksheet_job.status = 'FAILED'; worksheet_job.save()
    retried = retry_job(worksheet_job)
    assert retried.parameters == {'key': 'book.xlsx'} and retried.dataset_id is None
    token = uuid.uuid4()
    retried.status = 'RUNNING'; retried.attempt_token = token
    retried.heartbeat_at = timezone.now() - timedelta(hours=1); retried.save()
    staging = settings.DATASET_ROOT / f'.import-{retried.pk}-{token}-test'
    staging.mkdir(); (staging / 'partial.xlsx').write_bytes(b'partial')
    with patch('processing.services.recovery.dispatch', return_value=True):
        assert recover_jobs()['requeued'] == 1
    assert not staging.exists()
    retried.refresh_from_db(); assert retried.parameters == worksheet_job.parameters
    worksheet_job.connection.expires_at = timezone.now() - timedelta(seconds=1); worksheet_job.connection.save()
    assert 'Reconnect' in retry_problem(worksheet_job)
    assert Dataset.objects.count() == 0


@pytest.mark.django_db
def test_bad_workbook_fails_job_without_dataset(worksheet_job):
    from processing.tasks import run_job
    with patch('processing.services.worksheets.download_source', side_effect=stub_source(b'bad')):
        run_job.run(str(worksheet_job.pk))
    worksheet_job.refresh_from_db()
    assert worksheet_job.status == 'FAILED' and worksheet_job.error_code == 'EXCEL_INVALID'
    assert worksheet_job.result == {} and Dataset.objects.count() == 0

@pytest.mark.django_db
def test_worksheet_endpoint_rejects_missing_csrf_before_dispatch():
    client = APIClient(enforce_csrf_checks=True)
    client.get('/api/session/')
    connection = S3Connection.objects.create(owner_session=client.session.session_key, bucket='test-bucket', encrypted_credentials=b'fake', status='READY', expires_at=timezone.now()+timedelta(hours=1))
    with patch('processing.views.dispatch') as dispatch:
        assert client.post(f'/api/connections/{connection.pk}/worksheets/', {'key':'book.xlsx'}, format='json').status_code == 403
        dispatch.assert_not_called()


@pytest.mark.django_db
def test_expired_credentials_fail_in_worker_before_s3(worksheet_job):
    from processing.tasks import run_job
    worksheet_job.connection.expires_at=timezone.now()-timedelta(seconds=1)
    worksheet_job.connection.save()
    with patch('processing.services.s3.boto3.client') as s3:
        run_job.run(str(worksheet_job.pk))
        s3.assert_not_called()
    worksheet_job.refresh_from_db()
    assert worksheet_job.status=='FAILED' and worksheet_job.error_code=='CONNECTION_EXPIRED'
