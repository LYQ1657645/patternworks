from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job, S3Connection

pytestmark = pytest.mark.django_db


@pytest.fixture
def owned():
    client = APIClient(enforce_csrf_checks=True)
    response = client.get('/api/session/')
    client.credentials(HTTP_X_CSRFTOKEN=response.data['csrf_token'])
    owner = client.cookies[settings.SESSION_COOKIE_NAME].value
    dataset = Dataset.objects.create(owner_session=owner, status='READY', source_key='private.csv', source_format='csv')
    job = Job.objects.create(owner_session=owner, dataset=dataset, kind='EXPORT_CSV', status='SUCCESS')
    connection = S3Connection.objects.create(owner_session=owner, bucket='private-bucket', status='READY',
        encrypted_credentials=b'not-decrypted-in-this-test', expires_at=timezone.now() + timedelta(hours=1))
    return client, owner, dataset, job, connection


@pytest.mark.parametrize('revocation', ['expired', 'deleted'])
def test_revoked_cookie_cannot_read_or_mutate_old_resources(owned, revocation):
    client, owner, dataset, job, connection = owned
    if revocation == 'expired':
        Session.objects.filter(session_key=owner).update(expire_date=timezone.now() - timedelta(seconds=1))
    else:
        Session.objects.filter(session_key=owner).delete()
    # Replay from an independent client so no request-local session cache can help.
    replay = APIClient(enforce_csrf_checks=True)
    replay.cookies[settings.SESSION_COOKIE_NAME] = owner
    replay.cookies[settings.CSRF_COOKIE_NAME] = client.cookies[settings.CSRF_COOKIE_NAME].value
    replay.credentials(HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
    assert replay.get('/api/datasets/').data['datasets'] == []
    assert replay.cookies[settings.SESSION_COOKIE_NAME].value != owner
    assert replay.get('/api/jobs/').data['jobs'] == []
    assert replay.get('/api/connections/').data['connections'] == []
    for path in [f'/api/datasets/{dataset.pk}/', f'/api/datasets/{dataset.pk}/rows/',
                 f'/api/datasets/{dataset.pk}/lifecycle/', f'/api/datasets/{dataset.pk}/export/',
                 f'/api/jobs/{job.pk}/', f'/api/jobs/{job.pk}/download/',
                 f'/api/connections/{connection.pk}/files/']:
        replay.cookies[settings.SESSION_COOKIE_NAME] = owner
        assert replay.get(path).status_code == 404, path
    for path in [f'/api/datasets/{dataset.pk}/restore/', f'/api/datasets/{dataset.pk}/retention/',
                 f'/api/jobs/{job.pk}/cancel/', f'/api/jobs/{job.pk}/retry/']:
        replay.cookies[settings.SESSION_COOKIE_NAME] = owner
        assert replay.post(path, {}, format='json').status_code == 404, path
    dataset.refresh_from_db()
    assert dataset.owner_session == owner and dataset.lifecycle == 'ACTIVE'


@pytest.mark.parametrize('revocation', ['expired', 'deleted'])
def test_revoked_cookie_submit_never_uses_old_owner(owned, revocation):
    client, owner, _, _, _ = owned
    if revocation == 'expired':
        Session.objects.filter(session_key=owner).update(expire_date=timezone.now() - timedelta(seconds=1))
    else:
        Session.objects.filter(session_key=owner).delete()
    with patch('processing.views.dispatch', return_value=True):
        response = client.post('/api/diagnostics/', {}, format='json')
    assert response.status_code == 202
    new_owner = client.cookies[settings.SESSION_COOKIE_NAME].value
    assert new_owner != owner and Session.objects.filter(session_key=new_owner).exists()
    assert Job.objects.get(pk=response.data['id']).owner_session == new_owner


def test_empty_valid_session_keeps_its_owner_and_existing_data(owned):
    client, owner, dataset, job, _ = owned
    assert client.session.items() == {}.items()
    for _ in range(2):
        assert client.get('/api/session/').status_code == 200
        assert client.get(f'/api/datasets/{dataset.pk}/').status_code == 200
        assert client.get(f'/api/jobs/{job.pk}/').status_code == 200
        assert client.cookies[settings.SESSION_COOKIE_NAME].value == owner


@pytest.mark.parametrize('cookie', ['not-a-real-session-key-12345678901', 'short', ''])
def test_unknown_or_malformed_cookie_is_replaced(cookie):
    client = APIClient()
    client.cookies[settings.SESSION_COOKIE_NAME] = cookie
    response = client.get('/api/session/')
    assert response.status_code == 200
    key = client.cookies[settings.SESSION_COOKIE_NAME].value
    assert key != cookie and Session.objects.filter(session_key=key).exists()


def test_revocation_does_not_bypass_csrf_or_remove_data(owned):
    client, owner, dataset, _, _ = owned
    Session.objects.filter(session_key=owner).delete()
    client.credentials()
    assert client.post('/api/diagnostics/', {}, format='json').status_code == 403
    assert client.get('/api/session/').status_code == 200
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
    with patch('processing.views.dispatch', return_value=True):
        assert client.post('/api/diagnostics/', {}, format='json').status_code == 202
    assert Dataset.objects.filter(pk=dataset.pk, owner_session=owner).exists()
