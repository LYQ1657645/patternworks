from datetime import timedelta
from unittest.mock import patch

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Job, S3Connection
from processing.services.credentials import CredentialsUnavailable, decrypt_credentials, encrypt_credentials
from processing.services.jobs import dispatch
from processing.services.s3 import S3Problem, check_bucket, list_files
from processing.tasks import run_job

pytestmark = pytest.mark.django_db

FAKE_CREDENTIALS = {'access_key_id': 'TEST_ACCESS_KEY', 'secret_access_key': 'dummy-secret-for-tests-only', 'session_token': ''}


@pytest.fixture
def browser(settings):
    settings.DEBUG = True
    client = APIClient(enforce_csrf_checks=True)
    response = client.get('/api/session/')
    assert response.status_code == 200
    client.credentials(HTTP_X_CSRFTOKEN=response.data['csrf_token'])
    return client


def new_connection(owner='test-session'):
    return S3Connection.objects.create(
        owner_session=owner, bucket='test-data-bucket', region='ap-southeast-2',
        encrypted_credentials=encrypt_credentials(FAKE_CREDENTIALS),
        expires_at=timezone.now() + timedelta(hours=1),
    )


def test_encrypt_roundtrip_and_no_plaintext_in_database():
    record = new_connection()
    assert FAKE_CREDENTIALS['secret_access_key'].encode() not in bytes(record.encrypted_credentials)
    assert FAKE_CREDENTIALS['access_key_id'].encode() not in bytes(record.encrypted_credentials)
    assert decrypt_credentials(record) == FAKE_CREDENTIALS


def test_expired_connection_is_not_decrypted():
    record = new_connection()
    record.expires_at = timezone.now() - timedelta(seconds=1)
    with pytest.raises(CredentialsUnavailable):
        decrypt_credentials(record)


def test_tampered_connection_is_not_decrypted():
    record = new_connection()
    record.encrypted_credentials = b'invalid-ciphertext'
    with pytest.raises(CredentialsUnavailable):
        decrypt_credentials(record)


def test_rotated_key_requires_reconnect(settings):
    record = new_connection()
    settings.CONNECTION_ENCRYPTION_KEY = Fernet.generate_key().decode()
    with pytest.raises(CredentialsUnavailable):
        decrypt_credentials(record)


def test_csrf_is_required_for_mutations():
    client = APIClient(enforce_csrf_checks=True)
    assert client.post('/api/diagnostics/', {}, format='json').status_code == 403


@patch('processing.views.dispatch', return_value=True)
def test_connection_returns_queued_job_without_calling_s3(enqueue, browser):
    with patch('processing.services.s3.check_bucket') as head:
        response = browser.post('/api/connections/', {**FAKE_CREDENTIALS, 'bucket': 'test-data-bucket'}, format='json')
    assert response.status_code == 202
    assert response.data['status'] == 'QUEUED'
    assert response.data['connection_id']
    head.assert_not_called()
    enqueue.assert_called_once()
    serialized = str(response.data)
    assert FAKE_CREDENTIALS['secret_access_key'] not in serialized
    assert FAKE_CREDENTIALS['access_key_id'] not in serialized
    assert 'encrypted_credentials' not in serialized


@pytest.mark.parametrize('bucket', ['bad/bucket', 'ab', 'UPPERCASE', '192.168.1.1', 'bad..bucket'])
def test_invalid_bucket_rejected(browser, bucket):
    response = browser.post('/api/connections/', {**FAKE_CREDENTIALS, 'bucket': bucket}, format='json')
    assert response.status_code == 400
    assert not S3Connection.objects.exists()


def test_other_session_cannot_read_or_cancel_job(browser):
    job = Job.objects.create(owner_session='another-session', kind=Job.Kind.DIAGNOSTIC)
    assert browser.get(f'/api/jobs/{job.id}/').status_code == 404
    assert browser.post(f'/api/jobs/{job.id}/cancel/', {}, format='json').status_code == 404


def test_other_session_cannot_browse_bucket(browser):
    record = new_connection('another-session')
    assert browser.get(f'/api/connections/{record.id}/files/').status_code == 404


@patch('processing.tasks.run_job.apply_async')
def test_queue_messages_only_contain_job_id(enqueue):
    record = new_connection()
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.CONNECT_S3, connection=record)
    assert dispatch(job)
    enqueue.assert_called_once_with(args=[str(job.pk)], task_id=str(job.pk))


def test_broker_failure_is_persisted():
    from kombu.exceptions import OperationalError
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.DIAGNOSTIC)
    with patch('processing.tasks.run_job.apply_async', side_effect=OperationalError('offline')):
        assert not dispatch(job)
    job.refresh_from_db()
    assert job.status == Job.Status.FAILED
    assert job.error_code == 'QUEUE_UNAVAILABLE'


def test_diagnostic_task_updates_database_and_cache():
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.DIAGNOSTIC)
    run_job.run(str(job.id))
    job.refresh_from_db()
    assert job.status == Job.Status.SUCCESS
    assert job.progress == 100
    assert job.started_at and job.finished_at
    assert job.result['cache'] == 'ok'


def test_s3_task_success_marks_connection_ready():
    record = new_connection()
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.CONNECT_S3, connection=record)
    with patch('processing.tasks.check_bucket') as check:
        run_job.run(str(job.id))
    check.assert_called_once()
    record.refresh_from_db()
    job.refresh_from_db()
    assert record.status == S3Connection.Status.READY
    assert job.status == Job.Status.SUCCESS


def test_s3_task_failure_has_safe_error_and_erases_credentials():
    record = new_connection()
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.CONNECT_S3, connection=record)
    with patch('processing.tasks.check_bucket', side_effect=S3Problem('S3_ACCESS_DENIED', 'AWS denied access.')):
        run_job.run(str(job.id))
    record.refresh_from_db()
    job.refresh_from_db()
    assert job.status == Job.Status.FAILED
    assert job.error_code == 'S3_ACCESS_DENIED'
    assert bytes(record.encrypted_credentials) == b''


def test_transient_s3_error_requeues_with_bounded_backoff():
    from celery.exceptions import Retry
    record = new_connection()
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.CONNECT_S3, connection=record)
    with patch('processing.tasks.check_bucket', side_effect=S3Problem('S3_TEMPORARY', 'Try again.', True)):
        with patch.object(run_job, 'retry', side_effect=Retry()) as retry:
            with pytest.raises(Retry):
                run_job.run(str(job.id))
    retry.assert_called_once_with(countdown=2)
    job.refresh_from_db()
    assert job.status == Job.Status.QUEUED


def test_transient_s3_error_fails_after_retry_limit():
    record = new_connection()
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.CONNECT_S3, connection=record)
    run_job.push_request(retries=2)
    try:
        with patch('processing.tasks.check_bucket', side_effect=S3Problem('S3_TEMPORARY', 'Try again.', True)):
            with patch.object(run_job, 'retry') as retry:
                run_job.run(str(job.id))
    finally:
        run_job.pop_request()
    retry.assert_not_called()
    job.refresh_from_db()
    assert job.status == Job.Status.FAILED


def test_cancellation_endpoint_wipes_connection_credentials(browser):
    record = new_connection(browser.session.session_key)
    job = Job.objects.create(owner_session=browser.session.session_key, kind=Job.Kind.CONNECT_S3, connection=record)
    response = browser.post(f'/api/jobs/{job.id}/cancel/', {}, format='json')
    assert response.status_code == 200
    assert response.data['status'] == Job.Status.CANCELLED
    record.refresh_from_db()
    assert bytes(record.encrypted_credentials) == b''


def test_cancelled_task_does_not_run_or_become_successful():
    record = new_connection()
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.CONNECT_S3, connection=record, status=Job.Status.CANCELLED)
    with patch('processing.tasks.check_bucket') as check:
        run_job.run(str(job.id))
    check.assert_not_called()
    job.refresh_from_db()
    assert job.status == Job.Status.CANCELLED


def test_duplicate_delivery_does_not_run_again():
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.DIAGNOSTIC, status=Job.Status.SUCCESS)
    assert run_job.run(str(job.id))['skipped'] is True


def test_cancellation_during_network_call_preserves_cancelled():
    record = new_connection()
    job = Job.objects.create(owner_session='test-session', kind=Job.Kind.CONNECT_S3, connection=record)
    def cancel_during_request(_):
        Job.objects.filter(pk=job.pk).update(status=Job.Status.CANCELLED)
    with patch('processing.tasks.check_bucket', side_effect=cancel_during_request):
        run_job.run(str(job.id))
    job.refresh_from_db()
    record.refresh_from_db()
    assert job.status == Job.Status.CANCELLED
    assert record.status != S3Connection.Status.READY


def test_expired_credentials_cleanup():
    record = new_connection()
    S3Connection.objects.filter(pk=record.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    call_command('purge_expired_connections')
    record.refresh_from_db()
    assert bytes(record.encrypted_credentials) == b''


def test_production_rejects_credentials_over_http(settings, browser):
    settings.DEBUG = False
    response = browser.post('/api/connections/', {**FAKE_CREDENTIALS, 'bucket': 'test-data-bucket'}, format='json')
    assert response.status_code == 400
    assert not S3Connection.objects.exists()


def stub_client():
    return boto3.client('s3', region_name='ap-southeast-2', aws_access_key_id='testing', aws_secret_access_key='testing')


def test_s3_pagination_preserves_cursor_even_for_empty_supported_page():
    record = new_connection()
    client = stub_client()
    with Stubber(client) as stub:
        stub.add_response('list_objects_v2', {
            'Contents': [{'Key': 'notes.txt', 'Size': 2, 'LastModified': timezone.now()}],
            'IsTruncated': True, 'NextContinuationToken': 'next-page',
        }, {'Bucket': record.bucket, 'Prefix': '', 'MaxKeys': 100})
        with patch('processing.services.s3.make_client', return_value=client):
            result = list_files(record)
    assert result['files'] == []
    assert result['next_cursor'] == 'next-page'


def test_s3_file_filter_and_continuation_token():
    record = new_connection()
    client = stub_client()
    with Stubber(client) as stub:
        stub.add_response('list_objects_v2', {
            'Contents': [{'Key': key, 'Size': 100, 'LastModified': timezone.now()} for key in ['data/A.CSV', 'data/b.xlsx', 'data/c.xls', 'data/d.pdf']],
            'IsTruncated': False,
        }, {'Bucket': record.bucket, 'Prefix': 'data/', 'MaxKeys': 100, 'ContinuationToken': 'cursor'})
        with patch('processing.services.s3.make_client', return_value=client):
            result = list_files(record, prefix='data/', cursor='cursor')
    assert [f['format'] for f in result['files']] == ['csv', 'xlsx', 'xls']
    assert result['next_cursor'] is None


@pytest.mark.parametrize('aws_code,expected', [('403', 'S3_ACCESS_DENIED'), ('InvalidAccessKeyId', 'S3_CREDENTIALS'), ('404', 'S3_NOT_FOUND')])
def test_aws_exception_details_are_not_returned(aws_code, expected):
    record = new_connection()
    exc = ClientError({'Error': {'Code': aws_code, 'Message': FAKE_CREDENTIALS['secret_access_key']}}, 'HeadBucket')
    with patch('processing.services.s3.make_client') as client:
        client.return_value.head_bucket.side_effect = exc
        with pytest.raises(S3Problem) as caught:
            check_bucket(record)
    assert caught.value.code == expected
    assert FAKE_CREDENTIALS['secret_access_key'] not in caught.value.message
