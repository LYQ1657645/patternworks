#!/usr/bin/env python3
"""Isolated XLSX/high-cardinality acceptance; real Spark/Redis, simulated provider.

No S3/OpenAI requests. --queue uses a separate real Celery worker; otherwise the
worker entrypoint executes synchronously, including its persisted continuations.
Uses a NEW local SQLite database and Redis port, never an existing workspace DB.
"""
import argparse
from contextlib import ExitStack, closing
import csv
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.dev_local import local_runtime_environment


def configure(directory, port):
    os.environ.update(local_runtime_environment())
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', DJANGO_DEBUG='true', OPENAI_API_KEY='',
        DATABASE_URL='sqlite:///'+str(directory/'acceptance.sqlite3'), DATASET_ROOT=str(directory/'data'),
        CELERY_BROKER_URL=f'redis://127.0.0.1:{port}/0', CELERY_RESULT_BACKEND=f'redis://127.0.0.1:{port}/1',
        CACHE_URL=f'redis://127.0.0.1:{port+1}/0', TRANSFORM_REQUESTS_PER_SLICE='25')
    sys.path.insert(0,str(ROOT/'backend'))
    import django
    django.setup()


def fake_provider(record, values):
    from processing.services.date_policy import expected_date
    outputs=[]
    for value in values:
        if record.kind=='DATE':
            result,status=expected_date(value,record.options['date_order'])
        else:
            result,status=('Even' if int(value.removeprefix('item-'))%2==0 else 'Odd'),'classified'
        outputs.append({'value':result,'status':status})
    return outputs, {'input_tokens':0,'output_tokens':0}


def fake_download(connection,key,target,report):
    source=Path(os.environ['ACCEPTANCE_XLSX'])
    shutil.copyfile(source,target)
    return {'source_bytes':source.stat().st_size,'transport':'synthetic local XLSX fixture'}


def guards():
    stack=ExitStack()
    stack.enter_context(patch('processing.services.datasets.download_source',fake_download))
    stack.enter_context(patch('processing.services.transformations.request_batch',fake_provider))
    stack.enter_context(patch('processing.services.transformations.OpenAI',side_effect=AssertionError('No paid API calls allowed')))
    stack.enter_context(patch('processing.services.rules.OpenAI',side_effect=AssertionError('No paid API calls allowed')))
    stack.enter_context(patch('boto3.client',side_effect=AssertionError('No S3 calls allowed')))
    return stack


def original(row, distinct):
    day=date(2000,1,1)+timedelta(days=(row-1)%10001)
    value=(day.isoformat(),day.strftime('%Y/%m/%d'),day.strftime('%d %b %Y'))[(row-1)%3]
    return [str(row),value,f'item-{(row-1)%distinct:07d}']


def workbook(path, rows, distinct):
    # Streaming, standards-compliant inline-string workbook; no giant cell list.
    with ZipFile(path,'w',ZIP_DEFLATED,compresslevel=1) as archive:
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Scale" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        with archive.open('xl/worksheets/sheet1.xml','w') as stream:
            stream.write(f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:C{rows+1}"/><sheetData>'.encode())
            for index in range(rows+1):
                cells=['ID','Date','Category'] if index==0 else original(index,distinct)
                xml=''.join(f'<c r="{col}{index+1}" t="inlineStr"><is><t>{value}</t></is></c>' for col,value in zip('ABC',cells))
                stream.write(f'<row r="{index+1}">{xml}</row>'.encode())
            stream.write(b'</sheetData></worksheet>')


def verify(dataset, rows, distinct, stage):
    from processing.services.datasets import artifact_directory
    digest=hashlib.sha256();count=0
    with closing(sqlite3.connect(artifact_directory(dataset.pk)/'rows.sqlite3')) as db:
        for number,raw in db.execute('SELECT row_id,cells FROM rows ORDER BY row_id'):
            count+=1
            expected=original(count,distinct)
            if stage>=1:expected += [(date(2000,1,1)+timedelta(days=(count-1)%10001)).isoformat(),'normalized']
            if stage>=2:expected += ['Even' if ((count-1)%distinct)%2==0 else 'Odd','classified']
            assert number==count and json.loads(raw)==expected,f'Cell mismatch at row {count}, stage {stage}'
            digest.update((raw+'\n').encode())
    assert count==rows==dataset.row_count
    return {'exact_rows_checked':count,'exact_cells_checked':count*len(dataset.columns),'ordered_sha256':digest.hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--rows',type=int,default=1_000_000)
    parser.add_argument('--distinct',type=int,default=1_000_000)
    parser.add_argument('--port',type=int,default=6393)
    parser.add_argument('--queue',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args();directory=args.directory.resolve()
    if args.worker:
        configure(directory,args.port)
        from config.celery import app
        with guards():app.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=WARNING','--without-gossip','--without-mingle'])
        return
    assert args.output and 1<=args.distinct<=args.rows<=1_048_575
    if directory.exists():raise SystemExit('Use a NEW acceptance directory to avoid overwriting data.')
    for port in [args.port,args.port+1]:
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))==0:raise SystemExit('Choose two unused Redis ports.')
    directory.mkdir(parents=True);configure(directory,args.port)
    from django.conf import settings
    from django.core.management import call_command
    from django.utils import timezone
    from processing.models import Dataset, Job, LLMTransformation, S3Connection
    from processing.services.datasets import read_page
    from processing.services.exports import export_path
    from processing.services.jobs import dispatch
    from processing.tasks import run_job
    call_command('migrate',verbosity=0)
    source=directory/'million.xlsx';os.environ['ACCEPTANCE_XLSX']=str(source)
    workbook(source,args.rows,args.distinct)
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    print(json.dumps({'event':'fixture_ready','rows':args.rows,'distinct_categories':args.distinct,'bytes':source.stat().st_size}),flush=True)
    redis_bin=shutil.which('redis-server') or str(ROOT/'.tools/redis-7.4.2/src/redis-server')
    result={'rows':args.rows,'distinct_categories':args.distinct,'provider':'deterministic mock, no paid API calls',
        'transport':'local synthetic XLSX, no S3 calls','database':'isolated local SQLite',
        'execution':'real Celery/Redis worker' if args.queue else 'synchronous worker entrypoint with durable continuation slices',
        'spark_master':settings.SPARK_MASTER,'partitions':settings.SPARK_PARTITIONS,'fixture_bytes':source.stat().st_size,
        'redis_policy':'separate noeviction broker and 256 MiB allkeys-lru cache',
        'fixture_sha256':source_hash,'stages':[],'complete':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():args.output.write_text(json.dumps(result,indent=2)+'\n')
    save()
    worker=None;redis=None;cache_process=None
    with (directory/'redis.log').open('w') as redis_log,(directory/'worker.log').open('w') as worker_log:
        try:
            redis=subprocess.Popen([redis_bin,'--bind','127.0.0.1','--port',str(args.port),'--save','','--appendonly','no',
                '--maxmemory','256mb','--maxmemory-policy','noeviction'],stdout=redis_log,stderr=subprocess.STDOUT)
            cache_process=subprocess.Popen([redis_bin,'--bind','127.0.0.1','--port',str(args.port+1),'--save','','--appendonly','no',
                '--maxmemory','256mb','--maxmemory-policy','allkeys-lru'],stdout=redis_log,stderr=subprocess.STDOUT)
            import redis as redis_module
            client=redis_module.Redis(port=args.port)
            deadline=time.monotonic()+10
            while True:
                try:
                    if client.ping():break
                except redis_module.ConnectionError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.1)
            if args.queue:
                worker=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--directory',str(directory),'--port',str(args.port),'--worker'],
                    env=os.environ.copy(),stdout=worker_log,stderr=subprocess.STDOUT)
            connection=S3Connection.objects.create(owner_session='scale-acceptance',bucket='local-fixture',encrypted_credentials=b'',
                status='READY',expires_at=timezone.now()+timedelta(hours=12))
            parent=None
            with guards(),patch('processing.services.jobs.dispatch',wraps=dispatch if args.queue else lambda job:True):
                for stage,kind in enumerate(['IMPORT_DATASET','APPLY_TRANSFORM','APPLY_TRANSFORM','EXPORT_CSV']):
                    record=None
                    dataset=parent if stage==3 else Dataset.objects.create(owner_session='scale-acceptance',parent=parent,
                        connection=connection,source_key='million.xlsx',source_format='xlsx',sheet_name='Scale')
                    if stage in (1,2):
                        record=LLMTransformation.objects.create(owner_session='scale-acceptance',dataset=parent,
                            kind='DATE' if stage==1 else 'CATEGORY',column='c1' if stage==1 else 'c2',status='READY',model='mock-only',
                            options={'date_order':'REJECT'} if stage==1 else {'labels':['Even','Odd'],'fallback':'Odd'},request_budget=1_000_000)
                    job=Job.objects.create(owner_session='scale-acceptance',dataset=dataset,connection=connection,kind=kind,transformation=record)
                    started=time.monotonic()
                    if args.queue:assert dispatch(job)
                    last_print=started
                    while True:
                        if not args.queue:run_job.run(str(job.pk))
                        job.refresh_from_db()
                        if job.status in {'SUCCESS','FAILED','CANCELLED'}:break
                        if time.monotonic()-last_print>20:
                            print(json.dumps({'event':'progress','stage':stage,'attempts':job.attempt_count,'progress':job.progress,'status':job.status}),flush=True)
                            last_print=time.monotonic()
                        if time.monotonic()-started>7200:raise AssertionError('Acceptance time limit reached')
                        if args.queue:
                            assert worker.poll() is None,'Worker exited'
                            time.sleep(.2)
                    assert job.status=='SUCCESS',f'{stage}: {job.error_code} {job.error_message}'
                    elapsed=round(time.monotonic()-started,3);dataset.refresh_from_db()
                    checked=verify(dataset,args.rows,args.distinct,min(stage,2))
                    if stage==3:
                        with export_path(job).open(encoding='utf-8-sig',newline='') as stream:
                            reader=csv.reader(stream);assert next(reader)==[c['name'] for c in dataset.columns]
                            count=0
                            for count,row in enumerate(reader,1):
                                expected=original(count,args.distinct)+[(date(2000,1,1)+timedelta(days=(count-1)%10001)).isoformat(),'normalized',
                                    'Even' if ((count-1)%args.distinct)%2==0 else 'Odd','classified']
                                assert row==expected,f'Export mismatch at {count}'
                            assert count==args.rows
                        checked['csv_exact_cells_checked']=count*len(dataset.columns)
                    entry={'stage':['xlsx_import','date_normalization','classification','csv_export'][stage],
                        'elapsed_seconds':elapsed,'attempts':job.attempt_count,'metadata':dataset.metadata,**checked}
                    if record:
                        record.refresh_from_db()
                        entry.update(simulated_requests=record.requests_used,plan=record.plan)
                    result['stages'].append(entry);save()
                    print(json.dumps({'event':'stage_verified',**{k:v for k,v in entry.items() if k!='metadata'}}),flush=True)
                    parent=dataset
                original_dataset=Dataset.objects.filter(parent__isnull=True).get()
                assert verify(original_dataset,args.rows,args.distinct,0)['ordered_sha256']==result['stages'][0]['ordered_sha256']
                for after in [0,args.rows//2,max(0,args.rows-25)]:
                    page=read_page(parent,after=after,limit=25)
                    assert [row['row_number'] for row in page['rows']]==list(range(after+1,min(args.rows,after+25)+1))
                assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
                result.update(complete=True,source_preserved=True,pagination_exact=True,
                    cache_evictions=redis_module.Redis(port=args.port+1).info('stats')['evicted_keys']);save()
                print(json.dumps({'event':'complete','report':str(args.output)}),flush=True)
        finally:
            for process in [worker,redis,cache_process]:
                if process and process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
