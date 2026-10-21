from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ..models import Dataset, Job, LLMTransformation, RegexRule
from .execution import cleanup_outputs, discard_staging
from .jobs import dispatch
from .retry_policy import retry_problem


def recover_jobs():
    """Reconcile a bounded batch. Tokens fence out old processes before cleanup."""
    now = timezone.now()
    cutoff = now - timedelta(seconds=settings.JOB_STALE_SECONDS)
    expired = Q(heartbeat_at__lt=cutoff) | Q(heartbeat_at__isnull=True, started_at__lt=cutoff)
    ids = list(Job.objects.filter(expired, status=Job.Status.RUNNING).values_list('pk', flat=True)[:100])
    stats = {'requeued': 0, 'exhausted': 0, 'republished': 0, 'queue_failed': 0}
    for job_id in ids:
        should_dispatch = False
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job_id)
            heartbeat = job.heartbeat_at or job.started_at
            if job.status != Job.Status.RUNNING or not heartbeat or heartbeat >= cutoff:
                continue
            if job.recovery_count >= settings.JOB_MAX_RECOVERIES:
                cleanup_outputs(job)
                job.status = Job.Status.FAILED
                job.error_code = 'RECOVERY_EXHAUSTED'
                job.error_message = 'The worker stopped repeatedly. Check service resources and retry as a new task.'
                job.stage = 'Failed after worker recovery limit'
                job.finished_at = now
                stats['exhausted'] += 1
            else:
                # Cleanup while holding the same row lock used by artifact publication.
                # Old attempts cannot rename an artifact after this token is revoked.
                if job.kind == Job.Kind.EXPORT_CSV:
                    from .exports import discard_export
                    discard_export(job)
                if job.kind != Job.Kind.EXPORT_CSV and job.dataset_id and Dataset.objects.filter(pk=job.dataset_id).exclude(status='READY').exists():
                    from .datasets import discard_artifact
                    discard_artifact(job.dataset_id)
                    Dataset.objects.filter(pk=job.dataset_id).exclude(status='READY').update(status='PENDING')
                if job.kind == Job.Kind.GENERATE_RULE and job.rule_id:
                    RegexRule.objects.filter(pk=job.rule_id).exclude(status='READY').update(status='PENDING')
                if job.kind == Job.Kind.PREVIEW_TRANSFORM and job.transformation_id:
                    LLMTransformation.objects.filter(pk=job.transformation_id).exclude(status='READY').update(status='PENDING')
                discard_staging(job)
                job.attempt_token = None
                job.status = Job.Status.QUEUED
                job.progress = 0
                job.stage = 'Worker interrupted; recovering task'
                job.recovery_count += 1
                job.last_dispatched_at = now
                should_dispatch = True
                stats['requeued'] += 1
            job.save()
        if should_dispatch and not dispatch(job):
            cleanup_outputs(job)
            stats['queue_failed'] += 1
    # Repair crash-between-persist-and-publish and missing queued deliveries. A
    # healthy long queue is republished periodically, never failed for waiting.
    queued_cutoff = now - timedelta(seconds=settings.JOB_QUEUE_REPUBLISH_SECONDS)
    queued = Q(last_dispatched_at__lt=queued_cutoff) | Q(last_dispatched_at__isnull=True, created_at__lt=queued_cutoff)
    for job_id in list(Job.objects.filter(queued, status=Job.Status.QUEUED).values_list('pk', flat=True)[:100]):
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job_id)
            stamp = job.last_dispatched_at or job.created_at
            if job.status != Job.Status.QUEUED or stamp >= queued_cutoff:
                continue
            job.last_dispatched_at = now
            job.save(update_fields=['last_dispatched_at'])
        if dispatch(job):
            stats['republished'] += 1
        else:
            cleanup_outputs(job)
            stats['queue_failed'] += 1
    # A process killed after cancellation may not have run its finally block.
    cancelled_expired = (Q(heartbeat_at__lt=cutoff)
                         | Q(heartbeat_at__isnull=True, finished_at__lt=cutoff))
    for job in Job.objects.filter(cancelled_expired, status=Job.Status.CANCELLED,
                                  cleanup_completed_at__isnull=True).order_by('finished_at', 'pk')[:100]:
        cleanup_outputs(job, cancelled=True)
    return stats


def retry_job(previous):
    """Create a new auditable attempt/result, retaining the failed/cancelled record."""
    with transaction.atomic():
        references=[previous.dataset,previous.rule.dataset if previous.rule_id else None,
                    previous.transformation.dataset if previous.transformation_id else None]
        ids={d.pk for d in references if d}|{d.parent_id for d in references if d and d.parent_id}
        locked={d.pk:d for d in Dataset.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
        for dataset in locked.values():
            if dataset.parent_id and dataset.parent_id in locked:
                dataset.parent = locked[dataset.parent_id]
        if previous.dataset_id:previous.dataset=locked[previous.dataset_id]
        if previous.rule_id:previous.rule.dataset=locked[previous.rule.dataset_id]
        if previous.transformation_id:previous.transformation.dataset=locked[previous.transformation.dataset_id]
        problem = retry_problem(previous)
        if problem:
            raise ValueError(problem)
        fields = {'owner_session': previous.owner_session, 'kind': previous.kind, 'parameters': previous.parameters,
                  'connection': previous.connection, 'rule': previous.rule, 'transformation': previous.transformation}
        if previous.dataset_id:
            old = previous.dataset
            if previous.kind == Job.Kind.EXPORT_CSV:
                fields['dataset'] = old
            if previous.kind != Job.Kind.EXPORT_CSV:
                fields['dataset'] = Dataset.objects.create(owner_session=old.owner_session, connection=old.connection,
                    parent=old.parent, source_key=old.source_key, source_format=old.source_format, sheet_name=old.sheet_name)
        if previous.kind == Job.Kind.GENERATE_RULE:
            old = previous.rule
            fields['rule'] = RegexRule.objects.create(owner_session=old.owner_session, dataset=old.dataset,
                                                     column=old.column, columns=old.target_columns, instruction=old.instruction)
        if previous.kind == Job.Kind.PREVIEW_TRANSFORM:
            old = previous.transformation
            fields['transformation'] = LLMTransformation.objects.create(owner_session=old.owner_session, dataset=old.dataset,
                kind=old.kind, column=old.column, instruction=old.instruction, options=old.options, model=old.model)
        return Job.objects.create(**fields)
