"""Reversible trash, opt-in retention and resumable, dependency-safe purge."""
from datetime import timedelta
import hashlib
import json
import logging
import shutil

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework.exceptions import APIException

from ..models import Dataset, Job, RegexRule, LLMTransformation
from .datasets import artifact_directory

logger = logging.getLogger(__name__)
TRASH_DAYS = 7


class LifecycleProblem(APIException):
    status_code = 409
    default_code = 'DATASET_LIFECYCLE'


def require_active(dataset):
    if dataset.lifecycle != Dataset.Lifecycle.ACTIVE:
        raise LifecycleProblem('This dataset is in Trash or has been purged. Restore it before using it.')


def active_references(dataset_id):
    return Job.objects.filter(
        Q(status__in=['QUEUED', 'RUNNING']) | Q(status='CANCELLED', cleanup_completed_at__isnull=True)
    ).filter(Q(dataset_id=dataset_id) | Q(dataset__parent_id=dataset_id)
             | Q(rule__dataset_id=dataset_id) | Q(transformation__dataset_id=dataset_id))


def dependencies(dataset):
    children = Dataset.objects.filter(parent=dataset).exclude(lifecycle='PURGED')
    parent = dataset.parent
    active_jobs = active_references(dataset.pk).count()
    active_children = children.filter(lifecycle='ACTIVE').count()
    blockers = []
    if dataset.status == 'PENDING': blockers.append('This dataset is still pending processing.')
    if active_children: blockers.append(f'{active_children} dependent dataset(s) must be moved to Trash first. No cascade deletion is performed.')
    if active_jobs: blockers.append(f'{active_jobs} task(s) are active or awaiting cancellation cleanup.')
    exports = Job.objects.filter(dataset=dataset, kind='EXPORT_CSV', status='SUCCESS').count()
    values = {'id':str(dataset.pk), 'is_original':not dataset.parent_id, 'lifecycle':dataset.lifecycle,
              'retention_days':dataset.retention_days, 'expires_at':dataset.expires_at,
              'trashed_at':dataset.trashed_at, 'purge_after':dataset.purge_after, 'purged_at':dataset.purged_at,
              'trash_reason':dataset.trash_reason,
              'parent':{'id':str(parent.pk),'source_key':parent.source_key,'lifecycle':parent.lifecycle} if parent else None,
              'children_count':children.count(),'active_children_count':active_children,
              'children':list(children.order_by('-created_at','-pk').values('id','source_key','lifecycle')[:10]),
              'active_jobs_count':active_jobs, 'export_count':exports,'blockers':blockers,
              'can_trash':dataset.lifecycle=='ACTIVE' and not blockers,
              'can_restore':dataset.lifecycle=='TRASH' and dataset.purge_after>timezone.now() and (not parent or parent.lifecycle=='ACTIVE')}
    return values


def review(dataset):
    data=dependencies(dataset)
    fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()
    salt='dataset-trash-v1:'+hashlib.sha256(dataset.owner_session.encode()).hexdigest()
    data['review_token']=signing.dumps([str(dataset.pk),fingerprint],salt=salt)
    return data


def _trash(dataset, reason):
    now=timezone.now()
    dataset.lifecycle='TRASH';dataset.trashed_at=now;dataset.purge_after=now+timedelta(days=TRASH_DAYS)
    dataset.trash_reason=reason
    dataset.save(update_fields=['lifecycle','trashed_at','purge_after','trash_reason'])


def trash_dataset(dataset_id, owner, confirmation, token, confirm_original=False):
    with transaction.atomic():
        dataset=Dataset.objects.select_for_update().get(pk=dataset_id,owner_session=owner)
        if confirmation!=str(dataset.pk):raise LifecycleProblem('Type the complete dataset ID to confirm.')
        if not dataset.parent_id and not confirm_original:raise LifecycleProblem('Confirm explicitly that this is an original imported dataset.')
        current=review(dataset)
        salt='dataset-trash-v1:'+hashlib.sha256(owner.encode()).hexdigest()
        try:
            expected=signing.loads(current['review_token'],salt=salt)
            supplied=signing.loads(token,salt=salt,max_age=300)
            if supplied!=expected:raise ValueError()
        except (signing.BadSignature,TypeError,ValueError):
            raise LifecycleProblem('The dependency review expired or changed. Review it again before deleting.') from None
        if not current['can_trash']:raise LifecycleProblem(' '.join(current['blockers']) or 'This dataset is not active.')
        _trash(dataset,'manual')
        return dataset


def restore_dataset(dataset_id, owner):
    # All multi-dataset operations use UUID lock order, including retries.
    initial=Dataset.objects.get(pk=dataset_id,owner_session=owner)
    ids=[initial.pk]+([initial.parent_id] if initial.parent_id else [])
    with transaction.atomic():
        locked={d.pk:d for d in Dataset.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
        dataset=locked[initial.pk]
        if dataset.lifecycle!='TRASH' or dataset.purge_after<=timezone.now():
            raise LifecycleProblem('The restore window has ended or this dataset is not in Trash.')
        if dataset.parent_id and locked[dataset.parent_id].lifecycle!='ACTIVE':
            raise LifecycleProblem('Restore the parent dataset first.')
        dataset.lifecycle='ACTIVE';dataset.trashed_at=None;dataset.purge_after=None;dataset.trash_reason=''
        # Restore never immediately re-expires the same data.
        dataset.retention_days=0;dataset.expires_at=None
        dataset.save(update_fields=['lifecycle','trashed_at','purge_after','trash_reason','retention_days','expires_at'])
        return dataset


def set_retention(dataset_id,owner,days,confirmed):
    if days not in [0,7,30,90]:raise LifecycleProblem('Choose Keep, 7, 30 or 90 days.')
    with transaction.atomic():
        dataset=Dataset.objects.select_for_update().get(pk=dataset_id,owner_session=owner)
        require_active(dataset)
        if not dataset.parent_id and days:raise LifecycleProblem('Original imported datasets never expire automatically.')
        if days and not confirmed:raise LifecycleProblem('Confirm automatic expiry and the seven-day Trash recovery window.')
        dataset.retention_days=days;dataset.expires_at=timezone.now()+timedelta(days=days) if days else None
        dataset.save(update_fields=['retention_days','expires_at'])
        return dataset


def _remove_directory(path):
    if path.is_symlink():path.unlink()
    elif path.exists():shutil.rmtree(path)  # Fail visibly; retry instead of claiming success.


def _purge(dataset_id):
    with transaction.atomic():
        dataset=Dataset.objects.select_for_update().get(pk=dataset_id)
        if dataset.lifecycle not in ['TRASH','PURGING'] or dataset.purge_after>timezone.now():return False
        if Dataset.objects.filter(parent=dataset).exclude(lifecycle='PURGED').exists() or active_references(dataset.pk).exists():return False
        dataset.lifecycle='PURGING';dataset.save(update_fields=['lifecycle'])
        # Tombstones/IDs and task audit states remain; stored row samples do not.
        RegexRule.objects.filter(dataset=dataset).update(preview={},instruction='',pattern='',replacement='',explanation='')
        LLMTransformation.objects.filter(dataset=dataset).update(preview={},instruction='',options={})
        Job.objects.filter(Q(dataset=dataset)|Q(rule__dataset=dataset)|Q(transformation__dataset=dataset)).update(parameters={})
        dataset.columns=[];dataset.metadata={};dataset.save(update_fields=['columns','metadata'])
    _remove_directory(artifact_directory(dataset.pk))
    for job_id in Job.objects.filter(dataset=dataset,kind='EXPORT_CSV').values_list('pk',flat=True).iterator():
        _remove_directory(settings.DATASET_ROOT/'exports'/str(job_id))
    for job_id in Job.objects.filter(dataset=dataset).values_list('pk',flat=True).iterator():
        for path in settings.DATASET_ROOT.glob(f'.import-{job_id}-*'):_remove_directory(path)
    Dataset.objects.filter(pk=dataset.pk,lifecycle='PURGING').update(lifecycle='PURGED',purged_at=timezone.now())
    return True


def maintain_datasets():
    now=timezone.now();stats={'trashed':0,'purged':0,'errors':0}
    children=Dataset.objects.filter(parent_id=OuterRef('pk'))
    jobs=active_references(OuterRef('pk'))
    # Exclude blockers before slicing so old blocked rows cannot starve leaves.
    due=Dataset.objects.filter(lifecycle='ACTIVE',expires_at__lte=now,parent__isnull=False).exclude(status='PENDING')
    due=due.annotate(blocked_child=Exists(children.filter(lifecycle='ACTIVE')),blocked_job=Exists(jobs)).filter(blocked_child=False,blocked_job=False)
    for dataset_id in list(due.order_by('expires_at','pk').values_list('pk',flat=True)[:100]):
        with transaction.atomic():
            dataset=Dataset.objects.select_for_update().get(pk=dataset_id)
            if (dataset.lifecycle=='ACTIVE' and dataset.expires_at and dataset.expires_at<=now and dataset.parent_id
                    and not dependencies(dataset)['blockers']):
                _trash(dataset,'retention');stats['trashed']+=1
    purge=Dataset.objects.filter(lifecycle__in=['TRASH','PURGING'],purge_after__lte=now)
    purge=purge.annotate(blocked_child=Exists(children.exclude(lifecycle='PURGED')),blocked_job=Exists(jobs)).filter(blocked_child=False,blocked_job=False)
    for dataset_id in list(purge.order_by('purge_after','pk').values_list('pk',flat=True)[:100]):
        try:stats['purged']+=int(_purge(dataset_id))
        except OSError:
            stats['errors']+=1;logger.warning('Dataset purge will retry: dataset_id=%s',dataset_id)
    return stats
