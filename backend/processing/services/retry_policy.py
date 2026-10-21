"""One retry eligibility policy for API hints and locked retry creation."""
from django.utils import timezone

from ..models import Dataset, Job


def retry_problem(job):
    if job.status not in {Job.Status.FAILED, Job.Status.CANCELLED}:
        return 'Only a failed or cancelled task can be retried.'
    if job.kind == Job.Kind.CONNECT_S3:
        return 'Enter the S3 credentials again to reconnect.'
    if job.error_code == 'TRANSFORM_BUDGET':
        return 'Increase the model request budget in Transform, then Apply to resume saved progress.'
    sources = [job.dataset, job.rule.dataset if job.rule_id else None,
               job.transformation.dataset if job.transformation_id else None]
    if any(d.lifecycle != 'ACTIVE' or (d.parent_id and d.parent.lifecycle != 'ACTIVE') for d in sources if d):
        return 'Restore the source/output dataset from Trash before retrying. Purged datasets cannot be retried.'
    if job.kind in {Job.Kind.IMPORT_DATASET, Job.Kind.LIST_WORKSHEETS}:
        if job.status == Job.Status.FAILED and job.error_code in {'SHEET_NOT_FOUND', 'CSV_SHEET', 'EXCEL_FORMULA', 'CSV_INVALID', 'EXCEL_INVALID'}:
            return 'Correct the file or worksheet selection in Data sources, then import again. Retrying would reuse the same inputs.'
        connection = job.connection
        if (not connection or connection.status != 'READY' or not connection.encrypted_credentials
                or connection.expires_at <= timezone.now()):
            return 'The source connection expired or is unavailable. Reconnect and import the file again.'
        if job.kind == Job.Kind.IMPORT_DATASET and not job.dataset_id:
            return 'The source import is unavailable. Import the file again.'
    elif job.kind == Job.Kind.EXPORT_CSV:
        if not job.dataset_id or job.dataset.status != Dataset.Status.READY:
            return 'The source dataset is unavailable.'
    elif job.kind in {Job.Kind.REPLACE_TEXT, Job.Kind.APPLY_RULE, Job.Kind.APPLY_TRANSFORM}:
        if not job.dataset_id or not job.dataset.parent_id or job.dataset.parent.status != Dataset.Status.READY:
            return 'The source dataset is unavailable. Import it again.'
    elif job.kind == Job.Kind.GENERATE_RULE:
        if not job.rule_id or job.rule.dataset.status != Dataset.Status.READY:
            return 'The source rule dataset is unavailable.'
    elif job.kind == Job.Kind.PREVIEW_TRANSFORM:
        if not job.transformation_id or job.transformation.dataset.status != Dataset.Status.READY:
            return 'The source transformation dataset is unavailable.'
    return ''
