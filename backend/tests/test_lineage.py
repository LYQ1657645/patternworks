"""Version graphs show persisted lineage without leaking sessions or inventing results."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from processing.models import Dataset, Job, S3Connection, RegexRule, LLMTransformation
from processing.services.lineage import version_graph

pytestmark = pytest.mark.django_db

@pytest.fixture
def client():
    c = APIClient(); c.get('/api/session/'); return c

def source(client, bucket='example', **kwargs):
    owner = client.session.session_key
    conn = S3Connection.objects.create(owner_session=owner, bucket=bucket,
        encrypted_credentials=b'private', expires_at=timezone.now()+timedelta(hours=1))
    return Dataset.objects.create(owner_session=owner, connection=conn,
        source_key='contacts.xlsx', sheet_name='Contacts', source_format='xlsx',
        status='READY', columns=[{'key':'c0','name':'Email'}, {'key':'c1','name':'Notes'}], **kwargs)

def child(parent, **kwargs):
    return Dataset.objects.create(owner_session=parent.owner_session, parent=parent,
        source_key=parent.source_key, source_format=parent.source_format,
        sheet_name=parent.sheet_name, columns=parent.columns, **{'status':'READY', **kwargs})

def test_branches_reimports_and_generate_are_not_invented_edges(client):
    root = source(client); reimport = source(client)
    first = child(root); sibling = child(root); next_version = child(first)
    child(root, status='FAILED'); child(root, status='CANCELLED'); child(root, status='PENDING')
    rule = RegexRule.objects.create(owner_session=root.owner_session, dataset=root, column='c0',
        columns=['c0','c1'], instruction='Find emails', pattern='email', replacement='[EMAIL]', status='READY')
    Job.objects.create(owner_session=root.owner_session, dataset=root, rule=rule, kind='GENERATE_RULE',status='SUCCESS')
    Job.objects.create(owner_session=root.owner_session, dataset=first, rule=rule, kind='APPLY_RULE',status='SUCCESS')
    first.metadata={'operation':'regex_replace','column_stats':{'c0':{'changed_rows':3},'c1':{'changed_rows':2}}};first.save()
    graph=client.get(f'/api/datasets/{next_version.pk}/lineage/')
    assert graph.status_code==200 and graph['Cache-Control']=='no-store'
    assert {n['id'] for n in graph.data['nodes']}=={str(x.pk) for x in [root,reimport,first,sibling,next_version]}
    assert {(e['source'],e['target']) for e in graph.data['edges']}=={(str(a.pk),str(b.pk)) for a,b in [(root,first),(root,sibling),(first,next_version)]}
    edge=next(e for e in graph.data['edges'] if e['target']==str(first.pk))
    assert edge['columns']==['Email','Notes'] and edge['details']['pattern']=='email'
    assert edge['column_stats']==[{'column':'Email','changed_rows':3},{'column':'Notes','changed_rows':2}]
    assert not graph.data['truncated']
    assert b'private' not in graph.content and b'owner_session' not in graph.content

def test_other_sessions_buckets_sheets_and_unproven_sources_are_separate(client):
    root=source(client); source(client,bucket='other')
    other_sheet=source(client);other_sheet.sheet_name='Other';other_sheet.save()
    outsider=APIClient();outsider.get('/api/session/');foreign=source(outsider)
    missing=Dataset.objects.create(owner_session=root.owner_session,source_key=root.source_key,
        source_format='xlsx',sheet_name='Contacts',status='READY')
    assert client.get(f'/api/datasets/{foreign.pk}/lineage/').status_code==404
    assert [n['id'] for n in version_graph(root,root.owner_session)['nodes']]==[str(root.pk)]
    assert [n['id'] for n in version_graph(missing,root.owner_session)['nodes']]==[str(missing.pk)]

def test_unavailable_ancestors_keep_provenance_and_dates_label(client):
    root=source(client); result=child(root)
    t=LLMTransformation.objects.create(owner_session=root.owner_session,dataset=root,
        column='c0',kind='DATE',options={'date_order':'DMY'},status='READY',model='test')
    Job.objects.create(owner_session=root.owner_session,dataset=result,transformation=t,kind='APPLY_TRANSFORM',status='SUCCESS')
    for lifecycle in ['TRASH','PURGED']:
        root.lifecycle=lifecycle;root.save()
        graph=client.get(f'/api/datasets/{result.pk}/lineage/').data
        assert graph['nodes'][0]['available'] is False
        assert graph['edges'][0]['label']=='Date normalization'
        assert graph['edges'][0]['details']['options']=={'date_order':'DMY'}

def test_limits_preserve_selected_ancestry_and_report_truncation(client):
    root=source(client); leaf=child(root)
    for _ in range(55): child(root)
    response=client.get(f'/api/datasets/{leaf.pk}/lineage/',{'limit':50})
    assert response.status_code==200 and len(response.data['nodes'])==50 and response.data['truncated']
    assert {str(root.pk),str(leaf.pk)} <= {n['id'] for n in response.data['nodes']}
    for value in ['bad',0,49,501]:
        assert client.get(f'/api/datasets/{leaf.pk}/lineage/',{'limit':value}).status_code==400

def test_cycle_is_bounded_and_text_operation_is_readable(client):
    root=source(client); result=child(root)
    Job.objects.create(owner_session=root.owner_session,dataset=result,kind='REPLACE_TEXT',status='SUCCESS',
        parameters={'column':'c0','find':'USA','replacement':'US','secret_access_key':'NEVER'})
    graph=version_graph(result,root.owner_session)
    assert graph['edges'][0]['details']=={'find':'USA','replacement':'US'}
    root.parent=result;root.save()
    graph=version_graph(result,root.owner_session)
    assert len(graph['nodes'])==2


def test_library_contains_multiple_files_and_groups_reimports_with_their_outputs(client):
    root=source(client); again=source(client); output=child(root)
    other=source(client,bucket='another-bucket')
    excel=source(client);excel.source_key='orders.xlsx';excel.save()
    sheet=source(client);sheet.sheet_name='Another sheet';sheet.save()
    cancelled=child(root,status='CANCELLED')
    graph=client.get('/api/datasets/galaxy/',{'limit':100}).data
    assert len(graph['nodes'])==7 and len(graph['groups'])==4
    nodes={n['id']:n for n in graph['nodes']}
    assert len({nodes[str(d.pk)]['group_id'] for d in [root,again,output,cancelled]})==1
    assert nodes[str(other.pk)]['group_id']!=nodes[str(root.pk)]['group_id']
    assert nodes[str(cancelled.pk)]['status']=='CANCELLED' and not nodes[str(cancelled.pk)]['available']
    assert all(e['target']!=str(cancelled.pk) for e in graph['edges'])
    assert len(graph['edges'])==1
    assert client.get('/api/datasets/galaxy/',{'q':'orders'}).data['nodes'][0]['name']=='orders.xlsx'
    assert client.get('/api/datasets/galaxy/',{'status':'CANCELLED'}).data['nodes'][0]['id']==str(cancelled.pk)


def test_library_trash_dependencies_paging_and_session_isolation(client):
    root=source(client); first=child(root); second=child(root)
    first.lifecycle='TRASH';first.save()
    outsider=APIClient();outsider.get('/api/session/');source(outsider)
    url='/api/datasets/galaxy/'
    assert len(client.get(url).data['nodes'])==2
    trash=client.get(url,{'scope':'TRASH'}).data
    assert [n['id'] for n in trash['nodes']]==[str(first.pk)] and not trash['nodes'][0]['available']
    assert len(client.get(url,{'parent_id':root.pk,'scope':'ALL'}).data['nodes'])==2
    response=client.get(url,{'limit':1,'scope':'ALL'});cursor=response.data['next_cursor'];assert cursor
    assert response.data['nodes'][0]['parent_outside_view']
    assert response.data['edges']==[]  # no fictitious edge to an unloaded parent
    ids=[response.data['nodes'][0]['id']]
    while cursor:
        response=client.get(url,{'limit':1,'scope':'ALL','cursor':cursor})
        ids.extend(n['id'] for n in response.data['nodes']);cursor=response.data['next_cursor']
    assert set(ids)=={str(d.pk) for d in [root,first,second]} and len(ids)==3
    cursor=client.get(url,{'limit':1,'scope':'ALL'}).data['next_cursor']
    assert outsider.get(url,{'limit':1,'scope':'ALL','cursor':cursor}).status_code==400
    assert client.get(url,{'limit':1,'scope':'ACTIVE','cursor':cursor}).status_code==400
    assert client.get('/api/datasets/',{'limit':1,'scope':'ALL','cursor':cursor}).status_code==400
    first.lifecycle='PURGED';first.save()
    assert str(first.pk) not in {n['id'] for n in client.get(url,{'scope':'ALL'}).data['nodes']}
