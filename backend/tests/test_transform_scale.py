"""High-cardinality correctness, durable recovery and spending controls (no API calls)."""
from collections import Counter
from datetime import date, timedelta
import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from processing.models import Dataset, Job, LLMTransformation
from processing.services.datasets import artifact_directory, build_page_index, DatasetCancelled
from processing.services.rules import RuleProblem
from processing.services.transform_store import prepare, store, TransformYield
from processing.tasks import run_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def fixture(settings, tmp_path):
    settings.DATASET_ROOT = tmp_path / 'data'
    cache.clear()
    def make(values, kind='CATEGORY', budget=200, owner='owner'):
        source = Dataset.objects.create(owner_session=owner, source_key='fixture.csv', source_format='csv', status='READY',
            row_count=len(values), columns=[{'key':'c0', 'name':'Value', 'type':'string'}])
        root = artifact_directory(source.pk); root.mkdir(parents=True)
        parts = tmp_path / str(source.pk); parts.mkdir()
        (parts / 'part-00000.json').write_text('\n'.join(json.dumps({'_row_id':i,'c0':v}) for i,v in enumerate(values,1)))
        build_page_index(parts, root/'rows.sqlite3', source.columns, lambda *args: None)
        record = LLMTransformation.objects.create(owner_session=owner, dataset=source, kind=kind, column='c0',
            model='mock-only', options={'date_order':'REJECT'} if kind=='DATE' else {'labels':['A','B'],'fallback':'B'},
            request_budget=budget, status='READY')
        return source,record
    return make


def model(record, batch):
    return [{'value':v if record.kind=='DATE' else 'A','status':'normalized' if record.kind=='DATE' else 'classified'} for v in batch], {'input_tokens':1,'output_tokens':2}


def finish(record, report=lambda *args: None):
    slices=0
    while True:
        try:
            prepare(record, report)
            return slices+1
        except TransformYield:
            slices+=1
            assert slices < 100


def test_1201_uncached_values_continue_across_slices_and_survive_redis_expiry(fixture):
    values=[f'item-{i:05}' for i in range(1201)]
    source,record=fixture(values+values+[None,''])
    with patch('processing.services.transformations.request_batch',side_effect=model) as api:
        with pytest.raises(TransformYield):prepare(record,lambda *args:None)
        record.refresh_from_db();assert record.requests_used==25
        with store(record) as (db,_):assert db.execute('SELECT count(*) FROM values_map WHERE result IS NOT NULL').fetchone()[0]==301
        cache.clear()
        finish(record)
    sent=[v for call in api.call_args_list for v in call.args[1]]
    assert Counter(sent)==Counter(values)
    assert all(len(call.args[1])<=12 for call in api.call_args_list)
    record.refresh_from_db()
    assert record.requests_used==record.requests_completed==101
    assert record.input_tokens==101 and record.output_tokens==202
    assert record.plan['pending_values']==0 and record.plan['distinct_values']==1202
    with store(record) as (db,_):
        assert db.execute('SELECT count(*) FROM values_map WHERE result IS NULL').fetchone()[0]==0
    assert source.status=='READY'


def test_1001_distinct_valid_dates_have_no_cardinality_rejection(fixture):
    values=[(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(1001)]
    _,record=fixture(values,kind='DATE')
    with patch('processing.services.transformations.request_batch',side_effect=model):finish(record)
    with store(record) as (db,_):
        assert {v:json.loads(raw)['value'] for v,raw in db.execute('SELECT value,result FROM values_map')}==dict(zip(values,values))


def test_full_plan_budget_refuses_before_any_paid_apply_and_can_be_increased(fixture):
    _,record=fixture([f'item {i}' for i in range(501)],budget=2)
    with patch('processing.services.transformations.request_batch',side_effect=model) as api:
        with pytest.raises(RuleProblem) as caught:prepare(record,lambda *args:None)
        assert caught.value.code=='TRANSFORM_BUDGET';api.assert_not_called()
        record.refresh_from_db();assert record.plan['estimated_new_requests']==42 and record.requests_used==0
        record.request_budget=42;record.save(update_fields=['request_budget'])
        finish(record)
    record.refresh_from_db();assert record.requests_used==42


def test_unknown_provider_outcome_is_still_reserved_across_retries(fixture):
    _,record=fixture(['one'],budget=1)
    with patch('processing.services.transformations.request_batch',side_effect=RuleProblem('LLM_TEMPORARY','Unknown response',True)):
        with pytest.raises(RuleProblem):prepare(record,lambda *args:None)
    record.refresh_from_db();assert record.requests_used==1 and record.requests_completed==0
    with patch('processing.services.transformations.request_batch') as api:
        with pytest.raises(RuleProblem) as caught:prepare(record,lambda *args:None)
        assert caught.value.code=='TRANSFORM_BUDGET';api.assert_not_called()
    record.request_budget=2;record.save(update_fields=['request_budget'])
    with patch('processing.services.transformations.request_batch',side_effect=model):finish(record)
    record.refresh_from_db();assert record.requests_used==2 and record.requests_completed==1


def test_long_value_after_preview_rows_stops_before_model_calls(fixture):
    _,record=fixture([f'item {i}' for i in range(501)]+['x'*65537])
    with patch('processing.services.transformations.request_batch') as api:
        with pytest.raises(RuleProblem) as caught:prepare(record,lambda *args:None)
        assert caught.value.code=='ARTIFACT_UNAVAILABLE';api.assert_not_called()


def test_cancellation_after_response_never_publishes_a_partial_mapping(fixture):
    _,record=fixture(['one'])
    def report(stage,value):
        if stage=='Saving validated batch progress':raise DatasetCancelled()
    with patch('processing.services.transformations.request_batch',side_effect=model):
        with pytest.raises(DatasetCancelled):prepare(record,report)
    with store(record) as (db,_):assert db.execute('SELECT result FROM values_map').fetchone()[0] is None
    record.refresh_from_db();assert record.requests_used==record.requests_completed==1


def test_bad_model_output_never_marks_values_complete(fixture):
    _,record=fixture(['one'])
    with patch('processing.services.transformations.request_batch',return_value=([{'value':'invented','status':'classified'}],{})):
        with pytest.raises(RuleProblem):prepare(record,lambda *args:None)
    with store(record) as (db,_):assert db.execute('SELECT result FROM values_map').fetchone()[0] is None


def test_long_text_batches_use_payload_size_and_preview_receives_complete_values(fixture):
    from processing.services.transformations import batches, preview_transformation
    values=[str(i)+'x'*30000 for i in range(5)]
    assert [len(b) for b in batches(values)]==[2,2,1]
    _,record=fixture(['short'])
    # Provide the full canonical value, not the shortened display-cell value.
    with store(record) as (db,_):
        from processing.services.transform_store import fill_values, save_plan
        fill_values(db,values,record,lambda *args:None)
        assert save_plan(db,record)['estimated_new_requests']==3
    from contextlib import contextmanager
    @contextmanager
    def samples(*args):yield [(1,[values[0]])]
    with patch('processing.services.datasets.column_samples',samples),patch('processing.services.transformations.request_batch',side_effect=model) as api:
        preview_transformation(record,lambda *args:None)
        assert api.call_args.args[1]==[values[0]]
        cache.clear()
        preview_transformation(record,lambda *args:None)
        assert api.call_count==1


def test_preview_retry_keeps_budget_ledger_and_checkpoint(fixture):
    from processing.services.recovery import retry_job
    source,record=fixture(['one'],budget=1)
    record.requests_used=1;record.status='FAILED';record.save()
    previous=Job.objects.create(owner_session=source.owner_session,kind='PREVIEW_TRANSFORM',transformation=record,
        status='FAILED',error_code='LLM_TEMPORARY')
    retried=retry_job(previous)
    assert retried.pk!=previous.pk and retried.transformation_id==record.pk
    record.refresh_from_db()
    assert record.requests_used==record.request_budget==1 and record.status=='PENDING'
    with patch('processing.services.transformations.request_batch') as api:
        with pytest.raises(RuleProblem) as caught:prepare(record,lambda *args:None)
        assert caught.value.code=='TRANSFORM_BUDGET';api.assert_not_called()


def test_redis_failure_after_paid_batch_keeps_durable_progress(fixture):
    _,record=fixture(['one','two'])
    with patch('processing.services.transformations.request_batch',side_effect=model) as api:
        with patch('processing.services.transform_store.cache.set_many',side_effect=ConnectionError):
            with pytest.raises(RuleProblem):prepare(record,lambda *args:None)
        cache.clear()
        finish(record)
        assert api.call_count==1
    record.refresh_from_db();assert record.requests_used==1 and record.plan['pending_values']==0


def test_migration_carries_forward_known_preview_and_apply_usage(fixture):
    from importlib import import_module
    from django.apps import apps
    from django.db import connection
    from types import SimpleNamespace
    source,record=fixture(['one'])
    record.usage={'model_calls':2,'input_tokens':30,'output_tokens':20};record.save()
    Dataset.objects.create(owner_session=source.owner_session,parent=source,source_key='fixture.csv',source_format='csv',
        metadata={'transformation_id':str(record.pk),'llm_usage':{'model_calls':3,'input_tokens':40,'output_tokens':10}})
    migration=import_module('processing.migrations.0012_llmtransformation_input_tokens_and_more')
    migration.preserve_known_usage(apps,SimpleNamespace(connection=connection))
    record.refresh_from_db()
    assert record.requests_used==record.requests_completed==5
    assert record.input_tokens==70 and record.output_tokens==30


def test_celery_continuation_preserves_job_identity_and_pending_dataset(fixture):
    source,record=fixture(['one'])
    output=Dataset.objects.create(owner_session=source.owner_session,parent=source,source_key='fixture.csv',source_format='csv')
    job=Job.objects.create(owner_session=source.owner_session,kind='APPLY_TRANSFORM',dataset=output,transformation=record,
        progress=55,stage='Progress saved; continuing next batch')
    def continuing(job,report):
        report('Reserving one model request',45)
        raise TransformYield()
    with patch('processing.tasks.prepare_dataset',side_effect=continuing),patch('processing.services.jobs.dispatch',return_value=True) as dispatch:
        run_job.run(str(job.pk))
    job.refresh_from_db();output.refresh_from_db()
    assert job.status=='QUEUED' and output.status=='PENDING' and job.attempt_count==1 and job.progress==55
    dispatch.assert_called_once()
    info={'row_count':1,'columns':source.columns,'metadata':{}}
    with patch('processing.tasks.prepare_dataset',return_value=info):run_job.run(str(job.pk))
    job.refresh_from_db();assert job.status=='SUCCESS' and job.attempt_count==2


def test_apply_api_changes_budget_and_coalesces_duplicate_requests(fixture):
    client=APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_X_CSRFTOKEN=client.get('/api/session/').data['csrf_token'])
    _,record=fixture(['one'],owner=client.session.session_key)
    url=f'/api/transformations/{record.pk}/apply/'
    with patch('processing.views.dispatch',return_value=True):
        first=client.post(url,{'allow_send_values':True,'request_budget':250},format='json')
        second=client.post(url,{'allow_send_values':True,'request_budget':300},format='json')
    assert first.status_code==second.status_code==202 and first.data['id']==second.data['id']
    record.refresh_from_db();assert record.request_budget==250
    for bad in [0,-1,1000001,'invalid']:
        assert client.post(url,{'allow_send_values':True,'request_budget':bad},format='json').status_code==400


@pytest.mark.spark
def test_distributed_join_more_than_500_values_preserves_rows_and_originals(settings,fixture):
    from processing.services.datasets import create_spark
    from processing.services.transformations import apply_transformation
    values=[f'item-{i:04}' for i in range(1201)]+[None,'','item-0000']
    source,record=fixture(values)
    output=Dataset.objects.create(owner_session=source.owner_session,parent=source,source_key='fixture.csv',source_format='csv')
    with patch('processing.services.transformations.request_batch',side_effect=model):finish(record)
    spark=create_spark('high-cardinality-join')
    try:
        frame=spark.createDataFrame([(i+1,v) for i,v in enumerate(values)],'_row_id long, c0 string')
        with patch('processing.services.transformations.request_batch') as api:
            result,metadata=apply_transformation(frame,output,record,lambda *args:None)
            actual=result.orderBy('_row_id').collect()
        api.assert_not_called()
        assert [(r['_row_id'],r['c0']) for r in actual]==[(i+1,v) for i,v in enumerate(values)]
        assert [(r['c1'],r['c2']) for r in actual]==[(None,'missing') if v is None or not v.strip() else ('A','classified') for v in values]
        assert metadata['status_counts']=={'classified':1202,'missing':2}
        assert metadata['llm_usage']['unique_values']==1202
    finally:spark.stop()


@pytest.mark.spark
def test_full_parquet_values_are_used_instead_of_truncated_display_index(fixture):
    from processing.services.datasets import create_spark
    from processing.services.transformations import preview_transformation
    values=['a'*5000,'b'*65536,'文'*40000]
    source,record=fixture(values)
    spark=create_spark('long-full-value-source')
    try:
        spark.createDataFrame([(i+1,v) for i,v in enumerate(values)],'_row_id long, c0 string').write.parquet(
            str(artifact_directory(source.pk)/'parquet'))
    finally:spark.stop()
    with patch('processing.services.transformations.request_batch',side_effect=model) as api:
        result=preview_transformation(record,lambda *args:None)
        assert [e['before'] for e in result['preview']['examples']]==values
        assert [v for call in api.call_args_list for v in call.args[1]]==values
        assert all(len(call.args[1])==1 for call in api.call_args_list)
        cache.clear()
        finish(record)
        assert api.call_count==3
