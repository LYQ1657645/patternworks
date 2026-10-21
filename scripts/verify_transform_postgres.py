#!/usr/bin/env python3
"""Destructive TEST DATABASE ONLY: real migration/row-lock budget acceptance.

DATABASE_URL must name a fresh isolated patternworks_acceptance* database.
Never use the application/public database. No provider or S3 requests are made.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from threading import Barrier
from urllib.parse import urlparse
from unittest.mock import patch

database=urlparse(os.environ.get('DATABASE_URL',''))
if database.scheme not in {'postgresql','postgres'} or not database.path.lstrip('/').startswith('patternworks_acceptance'):
    raise SystemExit('Requires an explicitly isolated PostgreSQL acceptance database.')
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings',DJANGO_DEBUG='true',OPENAI_API_KEY='')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import django
django.setup()
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from processing.models import Dataset, Job, LLMTransformation
from processing.services.rules import RuleProblem
from processing.services.transform_store import reserve_request
from rest_framework.test import APIClient

if connection.introspection.table_names():
    raise SystemExit('Acceptance database must be fresh, with no application tables.')
executor=MigrationExecutor(connection)
old=[('processing','0011_alter_job_kind')]
executor.migrate(old)
apps=executor.loader.project_state(old).apps
Source=apps.get_model('processing','Dataset');Transform=apps.get_model('processing','LLMTransformation')
source=Source.objects.create(owner_session='test-only',source_key='test.csv',source_format='csv',status='READY')
legacy=Transform.objects.create(owner_session='test-only',dataset=source,column='c0',kind='DATE',model='mock-only',
    usage={'model_calls':2,'input_tokens':30,'output_tokens':20})
Source.objects.create(owner_session='test-only',parent=source,source_key='test.csv',source_format='csv',status='READY',
    metadata={'transformation_id':str(legacy.pk),'llm_usage':{'model_calls':3,'input_tokens':40,'output_tokens':10}})
executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
legacy=LLMTransformation.objects.get(pk=legacy.pk)
assert (legacy.requests_used,legacy.requests_completed,legacy.input_tokens,legacy.output_tokens)==(5,5,70,30)

record=LLMTransformation.objects.create(owner_session='test-only',dataset_id=source.pk,column='c0',kind='CATEGORY',
    options={'labels':['A','B'],'fallback':'B'},model='mock-only',status='READY',request_budget=1)
barrier=Barrier(2)
def reserve(_):
    connections.close_all()
    try:
        item=LLMTransformation.objects.get(pk=record.pk);barrier.wait(timeout=10)
        try:reserve_request(item,lambda *args:None);return 'reserved'
        except RuleProblem as exc:return exc.code
    finally:connections.close_all()
with ThreadPoolExecutor(max_workers=2) as pool:outcomes=sorted(pool.map(reserve,range(2)))
record.refresh_from_db()
assert outcomes==['TRANSFORM_BUDGET','reserved'] and record.requests_used==1

client=APIClient(enforce_csrf_checks=True)
csrf=client.get('/api/session/',HTTP_HOST='localhost').data['csrf_token']
Dataset.objects.filter(pk=source.pk).update(owner_session=client.session.session_key,
    columns=[{'key':'c0','name':'Value','type':'string'}])
LLMTransformation.objects.filter(pk=record.pk).update(owner_session=client.session.session_key)
barrier=Barrier(2)
def apply(budget):
    connections.close_all()
    try:
        browser=APIClient(enforce_csrf_checks=True);browser.cookies=client.cookies.copy()
        barrier.wait(timeout=10)
        response=browser.post(f'/api/transformations/{record.pk}/apply/',
            {'allow_send_values':True,'request_budget':budget},format='json',HTTP_HOST='localhost',HTTP_X_CSRFTOKEN=csrf)
        return response.status_code,response.data['id']
    finally:connections.close_all()
with patch('processing.views.dispatch',return_value=True),ThreadPoolExecutor(max_workers=2) as pool:
    replies=list(pool.map(apply,[20,30]))
assert all(code==202 for code,_ in replies) and len({str(key) for _,key in replies})==1
assert Job.objects.filter(transformation=record,kind='APPLY_TRANSFORM').count()==1
print(json.dumps({'postgresql_migration':'passed','known_usage_preserved':True,
    'concurrent_budget_reservations':'one accepted, one refused','concurrent_apply':'one durable job','paid_api_calls':0}))
