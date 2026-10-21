from django.utils import timezone
from kombu.exceptions import OperationalError

from ..models import Job


def dispatch(job):
    from ..tasks import run_job

    try:
        Job.objects.filter(pk=job.pk, status=Job.Status.QUEUED).update(last_dispatched_at=timezone.now())
        # Only an opaque job ID goes to Redis / Flower, never AWS credentials.
        run_job.apply_async(args=[str(job.pk)], task_id=str(job.pk))
    except (OperationalError, OSError):
        # A broker can accept a message even when the producer loses its reply.
        # Only an unclaimed job may be failed here; never clobber worker progress.
        changed = Job.objects.filter(pk=job.pk, status=Job.Status.QUEUED).update(
            status=Job.Status.FAILED, stage='Failed', error_code='QUEUE_UNAVAILABLE',
            error_message='The task queue is unavailable. Please try again.', finished_at=timezone.now(),
        )
        return not changed and Job.objects.filter(pk=job.pk, status__in=[Job.Status.RUNNING, Job.Status.SUCCESS]).exists()
    return True


def fail(job_id, code, message, attempt_token=None):
    query = Job.objects.filter(pk=job_id, status__in=[Job.Status.QUEUED, Job.Status.RUNNING])
    if attempt_token is not None:
        query = query.filter(attempt_token=attempt_token)
    query.update(
        status=Job.Status.FAILED, stage='Failed', error_code=code, error_message=message,
        finished_at=timezone.now(),
    )


def progress(job_id, stage, value, attempt_token=None):
    query = Job.objects.filter(pk=job_id, status=Job.Status.RUNNING)
    if attempt_token is not None:
        query = query.filter(attempt_token=attempt_token)
    return query.update(stage=stage, progress=value)
