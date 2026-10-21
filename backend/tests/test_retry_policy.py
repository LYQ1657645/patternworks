from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job, S3Connection

pytestmark = pytest.mark.django_db


@pytest.fixture
def imported():
    client = APIClient(enforce_csrf_checks=True)
    response = client.get('/api/session/')
    client.credentials(HTTP_X_CSRFTOKEN=response.data['csrf_token'])
    owner = client.session.session_key
    connection = S3Connection.objects.create(owner_session=owner, bucket='test-bucket', status='READY',
        encrypted_credentials=b'fake-never-decrypted', expires_at=timezone.now() + timedelta(hours=1))
    dataset = Dataset.objects.create(owner_session=owner, connection=connection, source_key='test.csv', status='FAILED')
    job = Job.objects.create(owner_session=owner, connection=connection, dataset=dataset,
        kind='IMPORT_DATASET', status='FAILED', error_code='S3_TEMPORARY')
    return client, connection, dataset, job


@pytest.mark.parametrize('unavailable', ['expired', 'erased', 'failed', 'missing'])
def test_import_retry_hint_and_endpoint_agree(imported, unavailable):
    client, connection, _, job = imported
    if unavailable == 'expired': connection.expires_at = timezone.now() - timedelta(seconds=1)
    elif unavailable == 'erased': connection.encrypted_credentials = b''
    elif unavailable == 'failed': connection.status = 'FAILED'
    else: job.connection = None; job.save()
    connection.save()
    hint = client.get(f'/api/jobs/{job.pk}/').data
    assert hint['retry_allowed'] is False and 'Reconnect' in hint['retry_unavailable_reason']
    with patch('processing.views.dispatch') as dispatch:
        response = client.post(f'/api/jobs/{job.pk}/retry/', {}, format='json')
    assert response.status_code == 409 and response.data['detail'] == hint['retry_unavailable_reason']
    dispatch.assert_not_called()
    assert Job.objects.count() == 1 and Dataset.objects.count() == 1


def test_valid_import_retry_remains_available_and_rechecks_after_expiry(imported):
    client, connection, dataset, job = imported
    hint = client.get(f'/api/jobs/{job.pk}/').data
    assert hint['retry_allowed'] is True and hint['retry_unavailable_reason'] == ''
    with patch('processing.views.dispatch', return_value=True):
        response = client.post(f'/api/jobs/{job.pk}/retry/', {}, format='json')
    assert response.status_code == 202 and str(response.data['dataset_id']) != str(dataset.pk)
    connection.expires_at = timezone.now() - timedelta(seconds=1); connection.save()
    assert client.post(f'/api/jobs/{job.pk}/retry/', {}, format='json').status_code == 409
    assert Job.objects.count() == 2


@pytest.mark.parametrize('kind', ['EXPORT_CSV', 'REPLACE_TEXT', 'GENERATE_RULE'])
def test_non_s3_retry_is_not_blocked_by_old_import_credentials(imported, kind):
    from processing.models import RegexRule
    client, connection, source, _ = imported
    source.status = 'READY'; source.save()
    connection.expires_at = timezone.now() - timedelta(days=1); connection.save()
    args = {'dataset': source}
    if kind == 'REPLACE_TEXT':
        args['dataset'] = Dataset.objects.create(owner_session=source.owner_session, parent=source, status='FAILED')
    if kind == 'GENERATE_RULE':
        args = {'rule': RegexRule.objects.create(owner_session=source.owner_session, dataset=source, column='c0')}
    job = Job.objects.create(owner_session=source.owner_session, connection=connection, kind=kind, status='FAILED', **args)
    assert client.get(f'/api/jobs/{job.pk}/').data['retry_allowed'] is True
    with patch('processing.views.dispatch', return_value=True):
        assert client.post(f'/api/jobs/{job.pk}/retry/', {}, format='json').status_code == 202
