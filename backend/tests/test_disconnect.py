from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from processing.models import S3Connection, Job, Dataset


def connection(owner):
    return S3Connection.objects.create(owner_session=owner, bucket='test-bucket', encrypted_credentials=b'encrypted', status='READY', expires_at=timezone.now()+timedelta(hours=1))


@pytest.mark.django_db
def test_disconnect_revokes_all_owned_credentials_not_data_or_other_sessions():
    client=APIClient(); client.get('/api/session/')
    own=[connection(client.session.session_key) for _ in range(2)]
    other=connection('another-session')
    data=Dataset.objects.create(owner_session=client.session.session_key, source_key='original.csv', source_format='csv')
    old=Job.objects.create(owner_session=client.session.session_key, connection=own[0], kind='CONNECT_S3', status='SUCCESS')
    assert client.post('/api/connections/disconnect/', {}, format='json').status_code==200
    assert client.get('/api/connections/').data['connections']==[]
    for row in own:
        row.refresh_from_db()
        assert not row.encrypted_credentials and row.expires_at<=timezone.now()
        assert client.get(f'/api/connections/{row.pk}/files/').status_code==410
    other.refresh_from_db(); assert other.encrypted_credentials
    assert Dataset.objects.filter(pk=data.pk).exists() and Job.objects.filter(pk=old.pk).exists()
    assert client.post('/api/connections/disconnect/', {}, format='json').status_code==200


@pytest.mark.django_db
def test_disconnect_waits_for_active_s3_task():
    client=APIClient(); client.get('/api/session/')
    row=connection(client.session.session_key)
    Job.objects.create(owner_session=client.session.session_key,connection=row,kind='LIST_WORKSHEETS')
    assert client.post('/api/connections/disconnect/', {}, format='json').status_code==409
    row.refresh_from_db(); assert row.encrypted_credentials


@pytest.mark.django_db
def test_disconnect_requires_csrf():
    client=APIClient(enforce_csrf_checks=True);client.get('/api/session/')
    row=connection(client.session.session_key)
    assert client.post('/api/connections/disconnect/', {}, format='json').status_code==403
    row.refresh_from_db(); assert row.encrypted_credentials
