import logging
import uuid

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache
from django.db import transaction
from django.db.models import Case, F, When, Value
from django.utils import timezone

from .models import Dataset, Job, RegexRule, S3Connection, LLMTransformation
from .services.credentials import CredentialsUnavailable
from .services.jobs import fail
from .services.s3 import S3Problem, check_bucket
from .services.datasets import DatasetCancelled, DatasetProblem, prepare_dataset
from .services.execution import JobAttempt, cleanup_outputs, owns_attempt
from .services.rules import RuleProblem, generate_rule
from .services.transformations import preview_transformation
from .services.exports import prepare_csv
from .services.worksheets import list_worksheets
from .services.transform_store import TransformYield

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def run_job(self, job_id):
    token = uuid.uuid4()
    claimed = Job.objects.filter(pk=job_id, status=Job.Status.QUEUED).update(
        status=Job.Status.RUNNING, started_at=timezone.now(), heartbeat_at=timezone.now(),
        attempt_token=token, attempt_count=F('attempt_count') + 1,
        progress=Case(When(stage='Progress saved; continuing next batch', then=F('progress')), default=Value(10)),
        stage='Worker started', error_code='', error_message='',
    )
    if not claimed:
        return {'job_id': job_id, 'skipped': True}
    job = Job.objects.select_related('connection').get(pk=job_id)
    report = JobAttempt(job)
    report.start()
    dataset_info = rule_info = transformation_info = None
    try:
        inputs=[job.dataset,job.dataset.parent if job.dataset_id and job.dataset.parent_id else None,
                job.rule.dataset if job.rule_id else None,job.transformation.dataset if job.transformation_id else None]
        if any(d.lifecycle!='ACTIVE' for d in inputs if d):
            raise DatasetProblem('DATASET_UNAVAILABLE','Restore the source dataset from Trash before using it.')
        if job.kind == Job.Kind.DIAGNOSTIC:
            report('Checking shared cache', 50)
            key = f'diagnostic:{job_id}'
            cache.set(key, 'ok', timeout=30)
            if cache.get(key) != 'ok':
                raise RuntimeError('Cache check failed')
            cache.delete(key)
            result = {'message': 'API → queue → worker → database/cache completed.', 'cache': 'ok'}
        elif job.kind == Job.Kind.CONNECT_S3:
            if not job.connection:
                raise CredentialsUnavailable('Connection is unavailable. Please reconnect.')
            report('Checking access to your S3 bucket', 40)
            check_bucket(job.connection)
            report('Bucket access checked', 90)
            result = {'connection_id': str(job.connection_id), 'bucket': job.connection.bucket}
        elif job.kind == Job.Kind.LIST_WORKSHEETS:
            if not job.connection or job.connection.status != S3Connection.Status.READY:
                raise CredentialsUnavailable('Connection is unavailable.')
            result = list_worksheets(job.connection, job.parameters['key'], report, job=job)
        elif job.kind == Job.Kind.GENERATE_RULE:
            rule_info = generate_rule(job.rule, report, replacement=job.parameters.get('replacement'))
            result = {'rule_id': str(job.rule_id), 'source_dataset_id': str(job.rule.dataset_id),
                      'cache_hit': rule_info['cache_hit'], 'model': rule_info['model']}
        elif job.kind == Job.Kind.PREVIEW_TRANSFORM:
            transformation_info = preview_transformation(job.transformation, report)
            result = {'transformation_id': str(job.transformation_id), 'source_dataset_id': str(job.transformation.dataset_id)}
        elif job.kind == Job.Kind.EXPORT_CSV:
            result = prepare_csv(job, report)
        elif job.kind in {Job.Kind.IMPORT_DATASET, Job.Kind.REPLACE_TEXT, Job.Kind.APPLY_RULE, Job.Kind.APPLY_TRANSFORM}:
            dataset_info = prepare_dataset(job, report)
            result = {'dataset_id': str(job.dataset_id), 'row_count': dataset_info['row_count'],
                      'column_count': len(dataset_info['columns'])}
        else:
            raise ValueError('Unsupported job type')
        with transaction.atomic():
            current = Job.objects.select_for_update().get(pk=job_id)
            if current.status != Job.Status.RUNNING or not owns_attempt(job, current):
                cleanup_outputs(job, cancelled=current.status == Job.Status.CANCELLED)
                return {'job_id': job_id, 'skipped': True}
            if dataset_info:
                Dataset.objects.filter(pk=job.dataset_id).update(status=Dataset.Status.READY, **dataset_info)
            if rule_info:
                RegexRule.objects.filter(pk=job.rule_id).update(status=RegexRule.Status.READY, **rule_info)
            if transformation_info:
                LLMTransformation.objects.filter(pk=job.transformation_id).update(status=Dataset.Status.READY, **transformation_info)
            if job.kind == Job.Kind.CONNECT_S3:
                S3Connection.objects.filter(pk=job.connection_id, status=S3Connection.Status.PENDING).update(status=S3Connection.Status.READY)
            Job.objects.filter(pk=job_id).update(
                status=Job.Status.SUCCESS, progress=100, stage='Completed', result=result, finished_at=timezone.now(),
            )
    except TransformYield:
        # A continuation is not a failure/retry and must not erase saved values.
        changed = Job.objects.filter(pk=job_id, status=Job.Status.RUNNING, attempt_token=token).update(
            status=Job.Status.QUEUED, stage='Progress saved; continuing next batch',
            heartbeat_at=timezone.now(), last_dispatched_at=timezone.now())
        if changed:
            from .services.jobs import dispatch
            if not dispatch(job):
                cleanup_outputs(job)
    except DatasetCancelled:
        cleanup_outputs(job, cancelled=True)
    except (RuleProblem, S3Problem) as exc:
        if exc.transient and self.request.retries < self.max_retries:
            changed = Job.objects.filter(pk=job_id, status=Job.Status.RUNNING, attempt_token=token).update(
                status=Job.Status.QUEUED, stage='Temporary service error; retrying', progress=0,
                last_dispatched_at=timezone.now(),
            )
            if changed:
                raise self.retry(countdown=2 ** (self.request.retries + 1))
        cleanup_outputs(job)
        fail(job_id, exc.code, exc.message, token)
    except DatasetProblem as exc:
        cleanup_outputs(job)
        fail(job_id, exc.code, exc.message, token)
    except CredentialsUnavailable:
        cleanup_outputs(job)
        fail(job_id, 'CONNECTION_EXPIRED', 'Connection expired or is unavailable. Please reconnect.', token)
    except SoftTimeLimitExceeded:
        cleanup_outputs(job)
        fail(job_id, 'TIMEOUT', 'The task exceeded its time limit. Please retry.', token)
    except Exception as exc:
        if report.cancelled.is_set():
            cleanup_outputs(job, cancelled=True)
        else:
            logger.error('Task failed: job_id=%s kind=%s error_type=%s', job_id, job.kind, type(exc).__name__)
            cleanup_outputs(job)
            fail(job_id, 'TASK_FAILED', 'The task failed. Check service availability and retry.', token)
    finally:
        report.stop()
    return {'job_id': job_id}
