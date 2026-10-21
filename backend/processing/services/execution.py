"""Attempt fencing, liveness heartbeats and in-process Spark cancellation."""
import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections, connections, transaction
from django.utils import timezone

from ..models import Dataset, Job, LLMTransformation, RegexRule, S3Connection
from .datasets import DatasetCancelled, artifact_directory, discard_artifact
from .jobs import progress

logger = logging.getLogger(__name__)


class JobAttempt:
    def __init__(self, job):
        self.job = job
        self.stopped = threading.Event()
        self.cancelled = threading.Event()
        self.spark = None
        self.thread = None
        self.last_heartbeat = 0
        self.last_row_report = 0

    def __call__(self, stage, value):
        if self.cancelled.is_set():
            raise DatasetCancelled()
        if self.job.kind == Job.Kind.APPLY_TRANSFORM:
            # Profiling, model slices and the final Spark pass share one job.
            # Stage-local percentages must not make its progress jump backwards.
            value = max(self.job.progress, value)
            self.job.progress = value
        # Million-row parsing/indexing can emit thousands of identical-percent
        # updates. Heartbeats and cancellation checks run independently.
        if stage.startswith(('Parsing source rows (', 'Indexing preview (', 'Exporting CSV (')):
            now = time.monotonic()
            if now - self.last_row_report < 0.5:
                return
            self.last_row_report = now
        if not progress(self.job.pk, stage, value, self.job.attempt_token):
            self.cancelled.set()
            raise DatasetCancelled()

    def bind_spark(self, spark):
        self.spark = spark

    def tick(self):
        current = Job.objects.filter(pk=self.job.pk).values('status', 'attempt_token').first()
        if not current or current['status'] != Job.Status.RUNNING or current['attempt_token'] != self.job.attempt_token:
            self.cancelled.set()
        elif time.monotonic() - self.last_heartbeat >= settings.JOB_HEARTBEAT_SECONDS:
            Job.objects.filter(pk=self.job.pk, status=Job.Status.RUNNING, attempt_token=self.job.attempt_token).update(heartbeat_at=timezone.now())
            self.last_heartbeat = time.monotonic()
        if self.cancelled.is_set() and self.spark is not None:
            # Repeat while cancellation is active to cover an action submitted at the boundary.
            try:
                self.spark.sparkContext.cancelJobGroup(str(self.job.pk))
            except Exception:
                pass  # A context already stopping is expected during cancellation.

    def _watch(self):
        close_old_connections()
        try:
            while not self.stopped.wait(settings.JOB_POLL_SECONDS):
                try:
                    self.tick()
                except Exception as exc:
                    # Loss of DB access cannot extend a lease. The reaper can fence it
                    # out; publication still requires the same token in PostgreSQL.
                    logger.warning('Job watchdog unavailable: job_id=%s error_type=%s', self.job.pk, type(exc).__name__)
                    close_old_connections()
        finally:
            connections.close_all()

    def start(self):
        if settings.JOB_WATCHDOG_ENABLED:
            self.thread = threading.Thread(target=self._watch, daemon=True, name='job-watchdog')
            self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=3)


def owns_attempt(job, current):
    return current.attempt_token == job.attempt_token


def discard_staging(job):
    if not job.attempt_token:
        return
    for path in settings.DATASET_ROOT.glob(f'.import-{job.pk}-{job.attempt_token}-*'):
        import shutil
        shutil.rmtree(path, ignore_errors=True)


def cleanup_outputs(job, cancelled=False):
    """A superseded process must never remove or fail a newer attempt's output."""
    with transaction.atomic():
        current = Job.objects.select_for_update().get(pk=job.pk)
        if not owns_attempt(job, current):
            return
        is_cancelled = cancelled or current.status == Job.Status.CANCELLED
        status = Dataset.Status.CANCELLED if is_cancelled else Dataset.Status.FAILED
        if job.kind == Job.Kind.EXPORT_CSV:
            from .exports import discard_export
            if current.status != Job.Status.SUCCESS:
                discard_export(job)
        if job.kind != Job.Kind.EXPORT_CSV and job.dataset_id and Dataset.objects.filter(pk=job.dataset_id, status__in=[Dataset.Status.PENDING, Dataset.Status.CANCELLED]).exists():
            discard_artifact(job.dataset_id)
            Dataset.objects.filter(pk=job.dataset_id).update(status=status)
        if job.kind == Job.Kind.GENERATE_RULE and job.rule_id:
            RegexRule.objects.filter(pk=job.rule_id, status=RegexRule.Status.PENDING).update(status=status)
        if job.kind == Job.Kind.PREVIEW_TRANSFORM and job.transformation_id:
            LLMTransformation.objects.filter(pk=job.transformation_id, status=Dataset.Status.PENDING).update(status=status)
        if job.kind == Job.Kind.CONNECT_S3 and job.connection_id:
            S3Connection.objects.filter(pk=job.connection_id, status=S3Connection.Status.PENDING).update(status='FAILED', encrypted_credentials=b'')
        discard_staging(job)
        if current.status == Job.Status.CANCELLED:
            Job.objects.filter(pk=job.pk, attempt_token=job.attempt_token).update(cleanup_completed_at=timezone.now())


def publish_artifact(job, staging):
    with transaction.atomic():
        current = Job.objects.select_for_update().get(pk=job.pk)
        if current.status != Job.Status.RUNNING or not owns_attempt(job, current):
            raise DatasetCancelled()
        staging.rename(artifact_directory(job.dataset_id))
