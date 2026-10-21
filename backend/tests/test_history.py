"""Stable, bounded history paging, literal search and session isolation."""
from datetime import timedelta
from unittest.mock import patch
import uuid

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job

pytestmark = pytest.mark.django_db


@pytest.fixture
def browser():
    client = APIClient()
    client.get('/api/session/')
    return client


def fixtures(client, model, count=53):
    records=[]
    for i in range(count):
        values={'owner_session':client.session.session_key, 'id':uuid.UUID(int=i+1)}
        values.update({'kind':'DIAGNOSTIC', 'status':'SUCCESS'} if model is Job else
                      {'source_key':f'folder/File-{i:03}.csv','source_format':'csv', 'status':'READY', 'sheet_name':'Contacts'})
        records.append(model(**values))
    model.objects.bulk_create(records)
    # Tie boundaries intentionally cover many consecutive pages.
    model.objects.filter(owner_session=client.session.session_key).update(created_at=timezone.now()-timedelta(days=1))
    return [str(r.pk) for r in reversed(records)]


@pytest.mark.parametrize('model,resource', [(Job,'jobs'),(Dataset,'datasets')])
def test_all_history_beyond_old_limits_ties_insertions_and_page_replay(browser, model, resource):
    expected=fixtures(browser,model)
    outsider=APIClient();outsider.get('/api/session/')
    model.objects.create(owner_session=outsider.session.session_key, **({'kind':'DIAGNOSTIC'} if model is Job else {'source_key':'hidden.csv','source_format':'csv'}))
    path=f'/api/{resource}/'
    response=browser.get(path,{'limit':7});assert response.status_code==200
    assert len(response.data[resource])==7 and response['Cache-Control']=='no-store'
    seen=[x['id'] for x in response.data[resource]]
    cursor=response.data['next_cursor'];first_cursor=cursor
    assert cursor and browser.session.session_key not in cursor
    inserted=model.objects.create(owner_session=browser.session.session_key,**({'kind':'DIAGNOSTIC'} if model is Job else {'source_key':'new.csv','source_format':'csv'}))
    while cursor:
        response=browser.get(path,{'limit':7,'cursor':cursor});assert response.status_code==200
        seen.extend(x['id'] for x in response.data[resource]);cursor=response.data['next_cursor']
    assert seen==expected and len(set(seen))==53 and str(inserted.pk) not in seen
    assert browser.get(path,{'limit':7,'cursor':first_cursor}).data[resource][0]['id']==expected[7]
    assert browser.get(path,{'limit':7}).data[resource][0]['id']==str(inserted.pk)
    assert outsider.get(path,{'limit':7,'cursor':first_cursor}).status_code==400
    assert len(outsider.get(path).data[resource])==1


@pytest.mark.parametrize('resource', ['jobs','datasets'])
@pytest.mark.parametrize('query', [{'limit':0},{'limit':101},{'limit':'bad'},{'cursor':'bad'}, {'status':'unknown'}, {'cursor':'x'*2049}])
def test_invalid_list_query_is_rejected(browser, resource, query):
    assert browser.get(f'/api/{resource}/',query).status_code==400


@pytest.mark.parametrize('resource,model', [('jobs',Job),('datasets',Dataset)])
def test_cursor_bound_to_filters_size_resource_and_expiry(browser, resource, model):
    fixtures(browser,model,4)
    query={'limit':1, 'status':'SUCCESS' if model is Job else 'READY'}
    if model is Job: query['kind']='DIAGNOSTIC'
    else: query['q']='File'
    url=f'/api/{resource}/';cursor=browser.get(url,query).data['next_cursor'];assert cursor
    for change in [{'limit':2},{'status':''},{'kind':''} if model is Job else {'q':'Other'}]:
        assert browser.get(url,{**query,**change,'cursor':cursor}).status_code==400
    assert browser.get(url,{**query,'cursor':cursor[:-1]+('A' if cursor[-1]!='A' else 'B')}).status_code==400
    other='datasets' if resource=='jobs' else 'jobs'
    assert browser.get(f'/api/{other}/',{'limit':1,'cursor':cursor}).status_code==400
    with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+86401):
        assert browser.get(url,{**query,'cursor':cursor}).status_code==400


def test_dataset_search_name_sheet_uuid_unicode_literal_wildcards_and_status(browser):
    fixtures(browser,Dataset,30)
    owner=browser.session.session_key
    target=Dataset.objects.create(owner_session=owner,source_key='Archive/REPORT_100%.xlsx',source_format='xlsx',sheet_name='客户资料',status='FAILED')
    Dataset.objects.create(owner_session=owner,source_key='Archive/REPORTx100X.xlsx',source_format='xlsx',status='READY')
    url='/api/datasets/'
    for query in ['report_100%', '客户资料', str(target.pk)]:
        result=browser.get(url,{'q':query})
        assert result.status_code==200 and [d['id'] for d in result.data['datasets']]==[str(target.pk)]
    assert browser.get(url,{'q':'report_100%','status':'READY'}).data['datasets']==[]
    assert browser.get(url,{'q':'not-found'}).data=={'datasets':[],'next_cursor':None}
    assert browser.get(url,{'q':'File-000'}).data['datasets'][0]['source_key']=='folder/File-000.csv'
    assert browser.get(url,{'q':'x'*257}).status_code==400
    assert browser.get('/api/jobs/',{'kind':'UNKNOWN'}).status_code==400


def test_history_job_filters_and_no_credential_fields(browser):
    owner=browser.session.session_key
    for kind,status in [('DIAGNOSTIC','SUCCESS'),('EXPORT_CSV','FAILED'),('EXPORT_CSV','CANCELLED')]:
        Job.objects.create(owner_session=owner,kind=kind,status=status,parameters={'secret_access_key':'NEVER_RETURN'})
    result=browser.get('/api/jobs/',{'status':'FAILED','kind':'EXPORT_CSV'})
    assert len(result.data['jobs'])==1 and result.data['jobs'][0]['status']=='FAILED'
    assert 'NEVER_RETURN' not in result.content.decode() and 'owner_session' not in result.content.decode()
    assert browser.get('/api/jobs/',{'status':'QUEUED'}).data=={'jobs':[],'next_cursor':None}


def test_latest_imports_group_before_paging_without_hiding_outputs_or_other_sources(browser):
    from processing.models import S3Connection
    owner = browser.session.session_key
    def connection(bucket):
        return S3Connection.objects.create(owner_session=owner, bucket=bucket,
            encrypted_credentials=b'', expires_at=timezone.now()+timedelta(hours=1))
    first, reconnected, other = connection('one'), connection('one'), connection('two')
    def dataset(conn, **kwargs):
        return Dataset.objects.create(owner_session=owner, connection=conn, source_key='contacts.xlsx',
            source_format='xlsx', status='READY', **kwargs)
    old = dataset(first, sheet_name='Contacts')
    latest = dataset(reconnected, sheet_name='Contacts')
    second_sheet = dataset(first, sheet_name='Other')
    second_bucket = dataset(other, sheet_name='Contacts')
    output = dataset(first, parent=old, sheet_name='Contacts')
    params = {'latest_imports': 'true', 'limit': 2}
    seen = []
    while True:
        result = browser.get('/api/datasets/', params)
        assert result.status_code == 200
        seen.extend(row['id'] for row in result.data['datasets'])
        if not result.data['next_cursor']: break
        params['cursor'] = result.data['next_cursor']
    assert set(seen) == {str(d.pk) for d in [latest, second_sheet, second_bucket, output]}
    assert len(seen) == 4
    # History and dependency references keep the original dataset available.
    assert browser.get(f'/api/datasets/{old.pk}/').status_code == 200
    assert len(browser.get('/api/datasets/').data['datasets']) == 5
    old.lifecycle = 'TRASH'; old.save()
    assert browser.get('/api/datasets/', {'latest_imports':'true', 'scope':'TRASH'}).data['datasets'][0]['id'] == str(old.pk)
