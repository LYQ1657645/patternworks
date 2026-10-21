"""Deletion/retention: source safety, dependency checks, recovery and erasure."""
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch
import uuid

from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset,Job,RegexRule,LLMTransformation
from processing.services.datasets import artifact_directory
from processing.services.exports import export_path
from processing.services.lifecycle import (LifecycleProblem,maintain_datasets,review,trash_dataset,restore_dataset,set_retention)
from processing.services.recovery import retry_job

pytestmark=pytest.mark.django_db


@pytest.fixture
def tree(settings,tmp_path):
    settings.DATASET_ROOT=tmp_path/'datasets'
    client=APIClient(enforce_csrf_checks=True);client.credentials(HTTP_X_CSRFTOKEN=client.get('/api/session/').data['csrf_token'])
    source=Dataset.objects.create(owner_session=client.session.session_key,status='READY',source_key='original.csv',source_format='csv',columns=[{'key':'c0','name':'Value'}],row_count=1)
    child=Dataset.objects.create(owner_session=source.owner_session,parent=source,status='READY',source_key='result.csv',source_format='csv',columns=source.columns,row_count=1)
    for d in [source,child]:
        path=artifact_directory(d.pk);path.mkdir(parents=True);(path/'full-data').write_text('COMPLETE SOURCE VALUE')
    return client,source,child


def trash(d,original=False):
    return trash_dataset(d.pk,d.owner_session,str(d.pk),review(Dataset.objects.get(pk=d.pk))['review_token'],original)


def expire_trash(d):
    Dataset.objects.filter(pk=d.pk).update(trashed_at=timezone.now()-timedelta(days=8),purge_after=timezone.now()-timedelta(days=1))


def test_default_keep_no_cascade_and_parent_requires_children_first(tree):
    client,source,child=tree
    assert maintain_datasets()=={'trashed':0,'purged':0,'errors':0}
    data=client.get(f'/api/datasets/{source.pk}/lifecycle/').data
    assert data['is_original'] and data['active_children_count']==1 and not data['can_trash']
    with pytest.raises(LifecycleProblem):trash(source,True)
    assert source.retention_days==child.retention_days==0
    assert artifact_directory(source.pk).joinpath('full-data').read_text()=='COMPLETE SOURCE VALUE'
    child=trash(child);source=trash(source,True)
    with pytest.raises(LifecycleProblem,match='parent'):restore_dataset(child.pk,child.owner_session)
    restore_dataset(source.pk,source.owner_session);restore_dataset(child.pk,child.owner_session)
    assert Dataset.objects.filter(lifecycle='ACTIVE').count()==2


@pytest.mark.parametrize('confirmation,original', [('wrong',True),('',True)])
def test_full_id_confirmation_is_required(tree,confirmation,original):
    _,source,child=tree
    with pytest.raises(LifecycleProblem):trash_dataset(child.pk,child.owner_session,confirmation,review(child)['review_token'],original)
    child.refresh_from_db();assert child.lifecycle=='ACTIVE'


def test_original_requires_extra_confirmation_and_never_auto_expires(tree):
    _,source,child=tree;trash(child)
    with pytest.raises(LifecycleProblem,match='original'):trash(source)
    with pytest.raises(LifecycleProblem,match='Original'):set_retention(source.pk,source.owner_session,7,True)
    Dataset.objects.filter(pk=source.pk).update(expires_at=timezone.now()-timedelta(days=100))
    maintain_datasets();source.refresh_from_db();assert source.lifecycle=='ACTIVE'
    assert artifact_directory(source.pk).exists()


@pytest.mark.parametrize('kind,status', [('EXPORT_CSV','QUEUED'),('EXPORT_CSV','RUNNING'),('GENERATE_RULE','RUNNING'),('PREVIEW_TRANSFORM','QUEUED'),('EXPORT_CSV','CANCELLED')])
def test_all_active_reference_types_and_unclean_cancel_block_delete(tree,kind,status):
    _,source,child=tree
    args={'dataset':child}
    if kind=='GENERATE_RULE':args={'rule':RegexRule.objects.create(owner_session=child.owner_session,dataset=child,column='c0')}
    if kind=='PREVIEW_TRANSFORM':args={'transformation':LLMTransformation.objects.create(owner_session=child.owner_session,dataset=child,kind='DATE',column='c0',model='test')}
    job=Job.objects.create(owner_session=child.owner_session,kind=kind,status=status,**args)
    assert review(child)['active_jobs_count']==1
    with pytest.raises(LifecycleProblem):trash(child)
    job.status='CANCELLED';job.cleanup_completed_at=timezone.now();job.save()
    assert trash(child).lifecycle=='TRASH'


def test_stale_tampered_expired_or_foreign_reviews_rejected(tree):
    _,source,child=tree;token=review(child)['review_token']
    set_retention(child.pk,child.owner_session,30,True)
    for bad in [token,token+'x',review(source)['review_token']]:
        with pytest.raises(LifecycleProblem):trash_dataset(child.pk,child.owner_session,str(child.pk),bad)
    child.refresh_from_db();token=review(child)['review_token']
    with patch('django.core.signing.time.time',return_value=timezone.now().timestamp()+301):
        with pytest.raises(LifecycleProblem):trash_dataset(child.pk,child.owner_session,str(child.pk),token)


@pytest.mark.parametrize('new_reference',['child','task'])
def test_new_dependency_after_review_blocks_stale_confirmation(tree,new_reference):
    _,source,child=tree;token=review(child)['review_token']
    if new_reference=='child':Dataset.objects.create(owner_session=child.owner_session,parent=child,status='READY')
    else:Job.objects.create(owner_session=child.owner_session,dataset=child,kind='EXPORT_CSV')
    with pytest.raises(LifecycleProblem):trash_dataset(child.pk,child.owner_session,str(child.pk),token)
    child.refresh_from_db();assert child.lifecycle=='ACTIVE' and artifact_directory(child.pk).exists()


def test_retention_opt_in_restore_keep_and_blocked_parent_postponement(tree):
    _,source,child=tree
    with pytest.raises(LifecycleProblem):set_retention(child.pk,child.owner_session,7,False)
    grandchild=Dataset.objects.create(owner_session=child.owner_session,parent=child,status='READY',source_key='last.csv')
    set_retention(child.pk,child.owner_session,7,True)
    Dataset.objects.filter(pk=child.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    assert maintain_datasets()['trashed']==0
    trash(grandchild)
    assert maintain_datasets()['trashed']==1
    child.refresh_from_db();assert child.trash_reason=='retention' and child.purge_after>timezone.now()+timedelta(days=6)
    restored=restore_dataset(child.pk,child.owner_session)
    assert restored.retention_days==0 and restored.expires_at is None
    assert maintain_datasets()['trashed']==0


def test_purge_removes_files_exports_stored_previews_and_parameters_retains_audit(tree):
    client,source,child=tree
    rule=RegexRule.objects.create(owner_session=child.owner_session,dataset=child,column='c0',status='READY',preview={'before':'PRIVATE'},instruction='PRIVATE')
    transform=LLMTransformation.objects.create(owner_session=child.owner_session,dataset=child,column='c0',kind='DATE',model='test',preview={'before':'PRIVATE'})
    job=Job.objects.create(owner_session=child.owner_session,dataset=child,kind='EXPORT_CSV',status='SUCCESS',attempt_token=uuid.uuid4(),parameters={'private':'VALUE'})
    path=export_path(job);path.parent.mkdir(parents=True);path.write_text('PRIVATE CSV')
    temp=artifact_directory(child.pk).parent/f'.import-{job.pk}-old-attempt';temp.mkdir();(temp/'partial').write_text('PRIVATE')
    trash(child);expire_trash(child)
    with pytest.raises(LifecycleProblem):restore_dataset(child.pk,child.owner_session)
    assert maintain_datasets()['purged']==1
    child.refresh_from_db();rule.refresh_from_db();transform.refresh_from_db();job.refresh_from_db()
    assert child.lifecycle=='PURGED' and child.columns==[] and child.metadata=={} and child.purged_at
    assert not artifact_directory(child.pk).exists() and not path.parent.exists() and not temp.exists()
    assert rule.preview==transform.preview=={} and rule.instruction=='' and job.parameters=={}
    assert job.status=='SUCCESS' and artifact_directory(source.pk).exists()
    assert client.get(f'/api/jobs/{job.pk}/download/').status_code==410
    assert client.get(f'/api/jobs/{job.pk}/').data['dataset_available'] is False


def test_purge_failure_stays_purging_retries_and_never_allows_restore(tree):
    _,source,child=tree;trash(child);expire_trash(child)
    with patch('processing.services.lifecycle._remove_directory',side_effect=OSError('disk problem')):
        assert maintain_datasets()=={'trashed':0,'purged':0,'errors':1}
    child.refresh_from_db();assert child.lifecycle=='PURGING'
    with pytest.raises(LifecycleProblem):restore_dataset(child.pk,child.owner_session)
    assert maintain_datasets()['purged']==1
    assert maintain_datasets()['purged']==0


def test_children_purge_before_parent_and_restore_window_preserved(tree):
    _,source,child=tree;trash(child);trash(source,True);expire_trash(source)
    assert maintain_datasets()['purged']==0  # Child's recovery window protects the whole lineage.
    expire_trash(child)
    assert maintain_datasets()['purged']==1
    source.refresh_from_db();assert source.lifecycle=='TRASH'
    assert maintain_datasets()['purged']==1
    assert Dataset.objects.filter(lifecycle='PURGED').count()==2


def test_blocked_rows_cannot_starve_eligible_expiry_batch(tree):
    _,source,child=tree
    for i in range(101):
        blocked=Dataset.objects.create(owner_session=source.owner_session,parent=source,status='READY',expires_at=timezone.now()-timedelta(days=2))
        Dataset.objects.create(owner_session=source.owner_session,parent=blocked,status='READY')
    Dataset.objects.filter(pk=child.pk).update(expires_at=timezone.now()-timedelta(days=1),retention_days=7)
    assert maintain_datasets()['trashed']==1
    child.refresh_from_db();assert child.lifecycle=='TRASH'


def test_session_csrf_and_list_locations_and_parent_filter(tree):
    client,source,child=tree;url=f'/api/datasets/{child.pk}'
    other=APIClient()
    for suffix in ['/lifecycle/','/trash/','/restore/','/retention/']:
        assert (other.get(url+suffix) if suffix=='/lifecycle/' else other.post(url+suffix,{},format='json')).status_code==404
    token=client.get(url+'/lifecycle/').data['review_token']
    body={'confirm_id':str(child.pk),'review_token':token}
    client.credentials();assert client.post(url+'/trash/',body,format='json').status_code==403
    client.credentials(HTTP_X_CSRFTOKEN=client.get('/api/session/').data['csrf_token'])
    assert client.post(url+'/trash/',body,format='json').status_code==200
    assert [d['id'] for d in client.get('/api/datasets/').data['datasets']]==[str(source.pk)]
    assert [d['id'] for d in client.get('/api/datasets/',{'scope':'TRASH'}).data['datasets']]==[str(child.pk)]
    assert client.get('/api/datasets/',{'scope':'ALL','parent_id':str(source.pk)}).data['datasets'][0]['id']==str(child.pk)
    assert client.post(url+'/restore/',{},format='json').status_code==200


@pytest.mark.parametrize('route,body', [('',None),('/rows/',None),('/rules/',None),('/transformations/',None),('/export/',None),
    ('/replace/',{'column':'c0','find':'x','replacement':''}),('/rules/',{'column':'c0','instruction':'Mask'}),
    ('/export/',{}),('/transformations/',{})])
def test_trash_blocks_reads_and_new_jobs(tree,route,body):
    client,_,child=tree;trash(child)
    route=route or '/'
    url=f'/api/datasets/{child.pk}{route}'
    response=client.get(url) if body is None else client.post(url,body,format='json')
    assert response.status_code==409
    assert not Job.objects.exists()


def test_trash_blocks_rule_transform_apply_previews_retry_and_download(tree):
    client,source,child=tree
    rule=RegexRule.objects.create(owner_session=child.owner_session,dataset=child,column='c0',status='READY')
    transform=LLMTransformation.objects.create(owner_session=child.owner_session,dataset=child,column='c0',kind='DATE',status='READY')
    job=Job.objects.create(owner_session=child.owner_session,dataset=child,kind='EXPORT_CSV',status='FAILED')
    trash(child)
    for route in [f'/api/rules/{rule.pk}/',f'/api/transformations/{transform.pk}/']:
        assert client.get(route).status_code==409
        assert client.post(route+'apply/',{},format='json').status_code==409
    assert not client.get(f'/api/jobs/{job.pk}/').data['retry_allowed']
    assert client.post(f'/api/jobs/{job.pk}/retry/',{},format='json').status_code==409
    with pytest.raises(ValueError):retry_job(job)


@pytest.mark.parametrize('body', [{'days':1},{'days':-1},{'days':365},{'days':'bad'},{}])
def test_invalid_retention_does_not_change_dataset(tree,body):
    client,_,child=tree
    assert client.post(f'/api/datasets/{child.pk}/retention/',body,format='json').status_code==400
    child.refresh_from_db();assert child.retention_days==0 and child.expires_at is None
