#!/usr/bin/env python3
"""Explicit local fault-injection acceptance against the running Compose stack.

Creates a dedicated session + synthetic fixture records. Kills/restarts only the
local worker and briefly stops/restarts Redis. Never reads credentials, calls S3
or calls OpenAI. Do not run against a public/production installation.
"""
import http.cookiejar
import json
import os
import shutil
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DOCKER = os.environ.get('DOCKER_BIN') or shutil.which('docker') or '/Applications/Docker.app/Contents/Resources/bin/docker'
COMPOSE = [DOCKER, 'compose', '--env-file', '.env.local']
env = {**os.environ, 'PATH': f'{Path(DOCKER).parent}:{os.environ.get("PATH", "")}'}
jar = http.cookiejar.CookieJar()
http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
csrf = ''


def command(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, **kwargs)


def db(code):
    result = command(COMPOSE + ['exec', '-T', 'backend', 'python', 'manage.py', 'shell'], input=code, timeout=45)
    if result.returncode:
        raise RuntimeError(f'Fixture operation failed (exit {result.returncode}).')
    return json.loads(result.stdout.strip().splitlines()[-1])


def call(path, body=None, expected=200):
    request = urllib.request.Request('http://127.0.0.1:5173/api' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf})
    try:
        response = http.open(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        result = json.load(response)
        assert response.code == expected, f'Unexpected HTTP {response.code} at {path}'
        return result


def wait(job_id, predicate, timeout=180):
    deadline, previous = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        job = call(f'/jobs/{job_id}/')
        current = (job['status'], job['stage'].split(' (')[0], job['attempt_count'])
        if current != previous:
            print(json.dumps({'event': 'job_progress', 'job_id': job_id, 'status': current[0], 'stage': current[1], 'attempt': current[2]}), flush=True)
            previous = current
        if predicate(job):
            return job
        if job['status'] in {'FAILED', 'CANCELLED', 'SUCCESS'}:
            raise AssertionError(f'Unexpected terminal state {job["status"]}: {job["error_code"]}')
        time.sleep(0.5)
    raise TimeoutError('Timed out waiting for task recovery.')


def main():
    global csrf
    csrf = call('/session/')['csrf_token']
    owner = next(cookie.value for cookie in jar if cookie.name == 'sessionid')
    baseline = json.loads((ROOT / 'docs/day5-million-baseline.json').read_text())
    original = baseline['stages'][0]['dataset_id']
    fixture = db(f"""
import json, os, shutil
from processing.models import Dataset, RegexRule
from processing.services.datasets import artifact_directory
source = Dataset.objects.get(pk={original!r})
copy = Dataset.objects.create(owner_session={owner!r}, source_key='million-fault-fixture.csv', source_format='csv', status='READY', row_count=source.row_count, columns=source.columns, metadata=source.metadata)
shutil.copytree(artifact_directory(source.pk), artifact_directory(copy.pk), copy_function=os.link)
rule = RegexRule.objects.create(owner_session=copy.owner_session, dataset=copy, column='c5', instruction='Synthetic email-mask fault fixture', status='READY', pattern=r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}', replacement='[EMAIL]', ignore_case=True)
print(json.dumps({{'source_id': str(copy.pk), 'rule_id': str(rule.pk)}}))
""")
    evidence = {'fixture_rows': 1_000_000, 'source_dataset_id': fixture['source_id'], 'checks': []}
    worker_down = redis_down = False
    try:
        cancelled = call(f'/rules/{fixture["rule_id"]}/apply/', {}, 202)
        wait(cancelled['id'], lambda job: job['progress'] == 50 and job['status'] == 'RUNNING')
        time.sleep(1)  # Allow the just-reported Spark RE2 action to start.
        started = time.monotonic()
        assert call(f'/jobs/{cancelled["id"]}/cancel/', {})['status'] == 'CANCELLED'
        probe = call('/diagnostics/', {}, 202)
        wait(probe['id'], lambda job: job['status'] == 'SUCCESS', timeout=30)
        freed_seconds = time.monotonic() - started
        checked = db(f"""
import json
from processing.models import Dataset, Job
from processing.services.datasets import artifact_directory
job = Job.objects.get(pk={cancelled['id']!r})
print(json.dumps({{'job_status': job.status, 'dataset_status': job.dataset.status, 'output_exists': artifact_directory(job.dataset_id).exists(), 'source_ready': Dataset.objects.get(pk={fixture['source_id']!r}).status == 'READY'}}))
""")
        assert checked == {'job_status': 'CANCELLED', 'dataset_status': 'CANCELLED', 'output_exists': False, 'source_ready': True}
        evidence['checks'].append({'name': 'cancel_during_million_row_spark_re2_stage', 'job_id': cancelled['id'],
            'worker_available_seconds': round(freed_seconds, 3), **checked})
        print(json.dumps({'event': 'cancellation_verified', 'seconds': freed_seconds}), flush=True)

        crashed = call(f'/datasets/{fixture["source_id"]}/replace/', {'column': 'c4', 'find': 'USA', 'replacement': 'United States'}, 202)
        wait(crashed['id'], lambda job: job['progress'] == 60 and job['status'] == 'RUNNING')
        worker_down = True
        assert command(COMPOSE + ['kill', '-s', 'SIGKILL', 'worker'], timeout=30).returncode == 0
        started = time.monotonic()
        assert command(COMPOSE + ['up', '-d', '--no-deps', 'worker'], timeout=45).returncode == 0
        worker_down = False
        recovered = wait(crashed['id'], lambda job: job['status'] == 'SUCCESS', timeout=210)
        assert recovered['attempt_count'] == 2 and recovered['recovery_count'] == 1
        evidence['checks'].append({'name': 'hard_worker_container_crash_and_automatic_recovery', 'job_id': crashed['id'],
            'seconds_from_kill_to_success': round(time.monotonic() - started, 3),
            'attempt_count': recovered['attempt_count'], 'recovery_count': recovered['recovery_count']})

        bad = db(f"""
import json
from processing.models import Dataset, RegexRule
source = Dataset.objects.get(pk={fixture['source_id']!r})
rule = RegexRule.objects.create(owner_session=source.owner_session, dataset=source, column='c4', instruction='Controlled invalid-rule fixture', status='READY', pattern='[', replacement='United States')
print(json.dumps({{'rule_id': str(rule.pk)}}))
""")
        failed = call(f'/rules/{bad["rule_id"]}/apply/', {}, 202)
        failed = wait(failed['id'], lambda job: job['status'] == 'FAILED', timeout=60)
        assert failed['error_code'] == 'REGEX_INVALID'
        db(f"""
import json
from processing.models import RegexRule
RegexRule.objects.filter(pk={bad['rule_id']!r}).update(pattern='^USA$')
print(json.dumps({{'corrected_synthetic_rule': True}}))
""")
        retried = call(f'/jobs/{failed["id"]}/retry/', {}, 202)
        done = wait(retried['id'], lambda job: job['status'] == 'SUCCESS')
        assert done['dataset_id'] != failed['dataset_id'] and done['id'] != failed['id']
        assert call(f'/jobs/{failed["id"]}/')['status'] == 'FAILED'
        evidence['checks'].append({'name': 'permanent_failure_then_manual_new_job_retry', 'failed_job_id': failed['id'],
            'retry_job_id': done['id'], 'failed_record_preserved': True, 'separate_output_dataset': True})

        # Both successful fault-test outputs are checked over every row, separately
        # from the Spark/RE2 implementation. Existing original source stays intact.
        check = db(f"""
import json, sqlite3
from contextlib import closing
from processing.models import Dataset
from processing.services.datasets import artifact_directory
source = Dataset.objects.get(pk={fixture['source_id']!r})
counts = []
for output_id in [{recovered['dataset_id']!r}, {done['dataset_id']!r}]:
    output = Dataset.objects.get(pk=output_id)
    count = 0
    with closing(sqlite3.connect(artifact_directory(source.pk) / 'rows.sqlite3')) as a, closing(sqlite3.connect(artifact_directory(output.pk) / 'rows.sqlite3')) as b:
        expected_rows = a.execute('SELECT row_id,cells FROM rows ORDER BY row_id')
        for old, new in zip(expected_rows, b.execute('SELECT row_id,cells FROM rows ORDER BY row_id'), strict=True):
            count += 1
            expected = json.loads(old[1]); actual = json.loads(new[1])
            if expected[4] == 'USA': expected[4] = 'United States'
            assert old[0] == new[0] == count and actual == expected
    assert count == output.row_count == source.row_count == 1000000
    counts.append(count)
print(json.dumps({{'source_ready': source.status == 'READY', 'exact_rows_per_result': counts}}))
""")
        assert check['source_ready'] and check['exact_rows_per_result'] == [1_000_000, 1_000_000]
        evidence['result_checks'] = check

        redis_down = True
        assert command(COMPOSE + ['stop', '-t', '5', 'redis'], timeout=30).returncode == 0
        unavailable = call('/diagnostics/', {}, expected=503)
        assert unavailable['status'] == 'FAILED' and unavailable['error_code'] == 'QUEUE_UNAVAILABLE'
        assert command(COMPOSE + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '30', 'redis'], timeout=45).returncode == 0
        redis_down = False
        replay = call(f'/jobs/{unavailable["id"]}/retry/', {}, 202)
        wait(replay['id'], lambda job: job['status'] == 'SUCCESS', timeout=90)
        evidence['checks'].append({'name': 'real_broker_outage_and_manual_recovery', 'failed_job_id': unavailable['id'],
            'retry_job_id': replay['id'], 'http_status_on_outage': 503, 'final_status': 'SUCCESS'})
        evidence['complete'] = True
        (ROOT / 'docs/day5-fault-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps({'event': 'fault_acceptance_complete', **evidence}), flush=True)
    finally:
        if redis_down:
            command(COMPOSE + ['up', '-d', '--no-deps', 'redis'], timeout=45)
        if worker_down:
            command(COMPOSE + ['up', '-d', '--no-deps', 'worker'], timeout=45)


if __name__ == '__main__':
    main()
