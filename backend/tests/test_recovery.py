from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import uuid

from django.core.cache import cache
from django.db.models import F
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from processing.models import Dataset, Job, LLMTransformation, RegexRule
from processing.services.datasets import DatasetCancelled, artifact_directory
from processing.services.execution import JobAttempt, cleanup_outputs, publish_artifact
from processing.services.jobs import dispatch, fail, progress
from processing.services.recovery import recover_jobs, retry_job
from processing.tasks import run_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def browser(settings, tmp_path):
    settings.DEBUG = True
    settings.DATASET_ROOT = tmp_path
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_X_CSRFTOKEN=client.get('/api/session/').data['csrf_token'])
    return client


def running(owner='owner', **overrides):
    fields = {'owner_session': owner, 'kind': 'DIAGNOSTIC', 'status': 'RUNNING', 'attempt_token': uuid.uuid4(),
        'attempt_count': 1, 'started_at': timezone.now() - timedelta(seconds=200),
        'heartbeat_at': timezone.now() - timedelta(seconds=200)}
    return Job.objects.create(**{**fields, **overrides})


def source_and_job(browser, kind='APPLY_RULE'):
    source = Dataset.objects.create(owner_session=browser.session.session_key, source_key='fixture.csv', source_format='csv', status='READY')
    output = Dataset.objects.create(owner_session=source.owner_session, parent=source, source_key=source.source_key, source_format='csv')
    job = running(owner=source.owner_session, kind=kind, dataset=output)
    return source, output, job


def test_attempt_claims_once_and_counts_real_executions():
    job = Job.objects.create(owner_session='owner', kind='DIAGNOSTIC')
    run_job.run(str(job.pk))
    job.refresh_from_db()
    assert job.status == 'SUCCESS' and job.attempt_count == 1 and job.attempt_token and job.heartbeat_at
    assert run_job.run(str(job.pk))['skipped'] is True
    job.refresh_from_db()
    assert job.attempt_count == 1


@pytest.mark.parametrize('completed', [False, True])
def test_uncertain_publish_ack_never_overwrites_claimed_or_completed_task(completed):
    from kombu.exceptions import OperationalError
    job = Job.objects.create(owner_session='owner', kind='DIAGNOSTIC')
    def accepted_but_lost_reply(**kwargs):
        if completed:
            run_job.run(str(job.pk))
        else:
            Job.objects.filter(pk=job.pk).update(status='RUNNING', attempt_token=uuid.uuid4(), started_at=timezone.now())
        raise OperationalError('Producer did not receive broker confirmation')
    with patch('processing.tasks.run_job.apply_async', side_effect=accepted_but_lost_reply):
        assert dispatch(job)
    job.refresh_from_db()
    assert job.status == ('SUCCESS' if completed else 'RUNNING') and not job.error_code


def test_watchdog_heartbeats_and_requests_real_spark_group_cancellation():
    job = running(heartbeat_at=timezone.now())
    report = JobAttempt(job)
    spark = Mock()
    report.bind_spark(spark)
    report.tick()
    assert not report.cancelled.is_set()
    spark.sparkContext.cancelJobGroup.assert_not_called()
    Job.objects.filter(pk=job.pk).update(status='CANCELLED')
    report.tick()
    assert report.cancelled.is_set()
    spark.sparkContext.cancelJobGroup.assert_called_once_with(str(job.pk))
    with pytest.raises(DatasetCancelled):
        report('Must not continue', 90)


def test_revoked_token_stops_progress_failure_and_watchdog():
    job = running()
    old_token = job.attempt_token
    Job.objects.filter(pk=job.pk).update(attempt_token=uuid.uuid4(), progress=60)
    assert progress(job.pk, 'old progress', 99, old_token) == 0
    fail(job.pk, 'OLD_FAILURE', 'old failure', old_token)
    report = JobAttempt(job)
    report.tick()
    assert report.cancelled.is_set()
    job.refresh_from_db()
    assert job.status == 'RUNNING' and job.progress == 60 and not job.error_code


def test_large_row_progress_is_throttled_without_skipping_terminal_fence():
    job = running(heartbeat_at=timezone.now())
    report = JobAttempt(job)
    with patch('processing.services.execution.progress', return_value=1) as update:
        for row in range(1000):
            report(f'Indexing preview ({row * 500} rows)', 85)
        assert update.call_count == 1
        report('Publishing dataset', 95)
        assert update.call_count == 2
    report.cancelled.set()
    with pytest.raises(DatasetCancelled):
        report('Indexing preview (500001 rows)', 85)


@pytest.mark.parametrize('status', ['PENDING', 'READY'])
def test_stale_attempt_cannot_delete_new_artifact_or_fail_new_dataset(browser, status):
    source, output, job = source_and_job(browser)
    target = artifact_directory(output.pk)
    target.mkdir(); (target / 'new-result').write_text('new worker data')
    Dataset.objects.filter(pk=output.pk).update(status=status)
    Job.objects.filter(pk=job.pk).update(attempt_token=uuid.uuid4())
    cleanup_outputs(job, cancelled=True)
    assert (target / 'new-result').read_text() == 'new worker data'
    output.refresh_from_db()
    assert output.status == status


def test_publication_requires_running_owned_attempt(browser, tmp_path):
    source, output, job = source_and_job(browser)
    staging = tmp_path / 'stage'
    staging.mkdir(); (staging / 'data').write_text('old')
    Job.objects.filter(pk=job.pk).update(attempt_token=uuid.uuid4())
    with pytest.raises(DatasetCancelled):
        publish_artifact(job, staging)
    assert staging.is_dir() and not artifact_directory(output.pk).exists()


@patch('processing.services.recovery.dispatch', return_value=True)
def test_stale_recovery_cleans_only_attempt_output_and_fences_old_worker(dispatch, browser):
    source, output, job = source_and_job(browser)
    source_path, target = artifact_directory(source.pk), artifact_directory(output.pk)
    source_path.mkdir(); (source_path / 'keep').write_text('source')
    target.mkdir(); (target / 'partial').write_text('partial')
    stage = source_path.parent / f'.import-{job.pk}-{job.attempt_token}-dead'
    stage.mkdir()
    stats = recover_jobs()
    job.refresh_from_db(); output.refresh_from_db()
    assert stats['requeued'] == 1 and job.status == 'QUEUED' and job.recovery_count == 1 and job.attempt_token is None
    assert output.status == 'PENDING' and not target.exists() and not stage.exists()
    assert (source_path / 'keep').is_file()
    dispatch.assert_called_once()


@patch('processing.services.recovery.dispatch', return_value=True)
def test_fresh_heartbeat_protects_long_running_jobs(dispatch):
    job = running(heartbeat_at=timezone.now())
    assert recover_jobs()['requeued'] == 0
    job.refresh_from_db()
    assert job.status == 'RUNNING'
    dispatch.assert_not_called()


def test_recovery_budget_exhaustion_preserves_ready_source(browser):
    source, output, job = source_and_job(browser)
    Job.objects.filter(pk=job.pk).update(recovery_count=2)
    stats = recover_jobs()
    job.refresh_from_db(); source.refresh_from_db(); output.refresh_from_db()
    assert stats['exhausted'] == 1 and job.status == 'FAILED' and job.error_code == 'RECOVERY_EXHAUSTED'
    assert source.status == 'READY' and output.status == 'FAILED'


@pytest.mark.parametrize('kind', ['GENERATE_RULE', 'PREVIEW_TRANSFORM'])
@patch('processing.services.recovery.dispatch', return_value=True)
def test_failed_child_from_interrupted_failure_handler_is_reset_on_recovery(dispatch, browser, kind):
    source = Dataset.objects.create(owner_session=browser.session.session_key, source_key='fixture.csv', source_format='csv', status='READY')
    if kind == 'GENERATE_RULE':
        child = RegexRule.objects.create(owner_session=source.owner_session, dataset=source, column='c0', instruction='Mask', status='FAILED')
        job = running(kind=kind, rule=child)
    else:
        child = LLMTransformation.objects.create(owner_session=source.owner_session, dataset=source, column='c0', kind='DATE',
            model='gpt-4.1-mini', options={'date_order': 'REJECT'}, status='FAILED')
        job = running(kind=kind, transformation=child)
    recover_jobs()
    child.refresh_from_db(); job.refresh_from_db()
    assert child.status == 'PENDING' and job.status == 'QUEUED'


@patch('processing.services.recovery.dispatch', return_value=True)
def test_unpublished_or_stuck_queued_jobs_republish_without_failure(dispatch):
    old = Job.objects.create(owner_session='owner', kind='DIAGNOSTIC')
    Job.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(seconds=400))
    fresh = Job.objects.create(owner_session='owner', kind='DIAGNOSTIC')
    assert recover_jobs()['republished'] == 1
    assert recover_jobs()['republished'] == 0
    old.refresh_from_db(); fresh.refresh_from_db()
    assert old.status == fresh.status == 'QUEUED' and old.recovery_count == 0
    dispatch.assert_called_once()


def test_recovered_job_executes_with_new_token_and_success():
    job = running()
    old_token = job.attempt_token
    with patch('processing.services.recovery.dispatch', return_value=True):
        recover_jobs()
    run_job.run(str(job.pk))
    job.refresh_from_db()
    assert job.status == 'SUCCESS' and job.attempt_count == 2 and job.attempt_token != old_token and job.recovery_count == 1


def test_manual_retry_preserves_original_and_creates_new_output(browser):
    source, output, previous = source_and_job(browser)
    previous.status = 'FAILED'; previous.save()
    new = retry_job(previous)
    assert new.pk != previous.pk and new.dataset_id != output.pk and new.dataset.parent_id == source.pk
    previous.refresh_from_db()
    assert previous.status == 'FAILED' and new.status == 'QUEUED' and new.attempt_count == 0


@patch('processing.views.dispatch', return_value=True)
def test_retry_api_is_owned_csrf_protected_and_never_runs_work_in_request(dispatch, browser):
    job = Job.objects.create(owner_session=browser.session.session_key, kind='DIAGNOSTIC', status='FAILED')
    path = f'/api/jobs/{job.pk}/retry/'
    assert APIClient(enforce_csrf_checks=True).post(path, {}, format='json').status_code == 403
    assert APIClient().post(path, {}, format='json').status_code == 404
    response = browser.post(path, {}, format='json')
    assert response.status_code == 202 and response.data['status'] == 'QUEUED' and str(response.data['id']) != str(job.pk)
    assert browser.get(f'/api/jobs/{job.pk}/').data['retry_allowed'] is True
    assert browser.post(f'/api/jobs/{response.data["id"]}/retry/', {}, format='json').status_code == 409
    job.refresh_from_db()
    assert job.status == 'FAILED'
    dispatch.assert_called_once()


def test_connection_retry_requires_new_credentials(browser):
    job = Job.objects.create(owner_session=browser.session.session_key, kind='CONNECT_S3', status='FAILED')
    assert browser.get(f'/api/jobs/{job.pk}/').data['retry_allowed'] is False
    assert browser.post(f'/api/jobs/{job.pk}/retry/', {}, format='json').status_code == 409


def test_cancelled_failure_cleanup_cannot_turn_cancelled_dataset_into_failed(browser):
    source, output, job = source_and_job(browser)
    Job.objects.filter(pk=job.pk).update(status='CANCELLED')
    Dataset.objects.filter(pk=output.pk).update(status='CANCELLED')
    cleanup_outputs(job)
    output.refresh_from_db()
    assert output.status == 'CANCELLED'


def test_stale_worker_final_callback_cannot_publish_over_recovered_attempt(browser):
    source, output, previous = source_and_job(browser)
    Job.objects.filter(pk=previous.pk).update(status='QUEUED', attempt_token=None)
    target = artifact_directory(output.pk)
    target.mkdir()
    new_token = uuid.uuid4()
    def stale_return(job, report):
        Job.objects.filter(pk=job.pk).update(attempt_token=new_token, status='RUNNING', progress=60)
        (target / 'new').write_text('new attempt')
        return {'row_count': 999, 'columns': [], 'sheet_name': '', 'metadata': {'wrong': True}}
    with patch('processing.tasks.prepare_dataset', side_effect=stale_return):
        result = run_job.run(str(previous.pk))
    previous.refresh_from_db(); output.refresh_from_db()
    assert result['skipped'] is True and previous.status == 'RUNNING' and previous.attempt_token == new_token
    assert previous.progress == 60 and output.status == 'PENDING' and (target / 'new').is_file()
