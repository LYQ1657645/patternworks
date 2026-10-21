import uuid

from django.db import models


class S3Connection(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING'
        READY = 'READY'
        FAILED = 'FAILED'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_session = models.CharField(max_length=40, db_index=True)
    bucket = models.CharField(max_length=63)
    region = models.CharField(max_length=63, blank=True)
    encrypted_credentials = models.BinaryField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)


class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'QUEUED'
        RUNNING = 'RUNNING'
        SUCCESS = 'SUCCESS'
        FAILED = 'FAILED'
        CANCELLED = 'CANCELLED'

    class Kind(models.TextChoices):
        DIAGNOSTIC = 'DIAGNOSTIC'
        CONNECT_S3 = 'CONNECT_S3'
        LIST_WORKSHEETS = 'LIST_WORKSHEETS'
        IMPORT_DATASET = 'IMPORT_DATASET'
        REPLACE_TEXT = 'REPLACE_TEXT'
        GENERATE_RULE = 'GENERATE_RULE'
        APPLY_RULE = 'APPLY_RULE'
        PREVIEW_TRANSFORM = 'PREVIEW_TRANSFORM'
        APPLY_TRANSFORM = 'APPLY_TRANSFORM'
        EXPORT_CSV = 'EXPORT_CSV'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_session = models.CharField(max_length=40, db_index=True)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    connection = models.ForeignKey(S3Connection, null=True, blank=True, on_delete=models.SET_NULL)
    dataset = models.ForeignKey('Dataset', null=True, blank=True, on_delete=models.SET_NULL)
    parameters = models.JSONField(default=dict)
    rule = models.ForeignKey('RegexRule', null=True, blank=True, on_delete=models.SET_NULL)
    transformation = models.ForeignKey('LLMTransformation', null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    stage = models.CharField(max_length=100, default='Waiting for a worker')
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempt_token = models.UUIDField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    recovery_count = models.PositiveSmallIntegerField(default=0)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_dispatched_at = models.DateTimeField(null=True, blank=True)
    cleanup_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['owner_session', '-created_at', '-id'], name='job_owner_history_idx'),
                   models.Index(fields=['status', 'heartbeat_at'])]


class Dataset(models.Model):
    class Lifecycle(models.TextChoices):
        ACTIVE = 'ACTIVE'
        TRASH = 'TRASH'
        PURGING = 'PURGING'
        PURGED = 'PURGED'

    class Status(models.TextChoices):
        PENDING = 'PENDING'
        READY = 'READY'
        FAILED = 'FAILED'
        CANCELLED = 'CANCELLED'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_session = models.CharField(max_length=40, db_index=True)
    connection = models.ForeignKey(S3Connection, null=True, blank=True, on_delete=models.SET_NULL)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    source_key = models.CharField(max_length=1024)
    source_format = models.CharField(max_length=8)
    sheet_name = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    row_count = models.PositiveBigIntegerField(default=0)
    columns = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    lifecycle = models.CharField(max_length=8, choices=Lifecycle.choices, default=Lifecycle.ACTIVE,db_default='ACTIVE')
    retention_days = models.PositiveSmallIntegerField(default=0,db_default=0)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    trashed_at = models.DateTimeField(null=True, blank=True)
    purge_after = models.DateTimeField(null=True, blank=True, db_index=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    trash_reason = models.CharField(max_length=16, blank=True,db_default='')

    class Meta:
        indexes = [models.Index(fields=['owner_session', '-created_at', '-id'], name='dataset_owner_history_idx')]


class RegexRule(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING'
        READY = 'READY'
        FAILED = 'FAILED'
        CANCELLED = 'CANCELLED'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_session = models.CharField(max_length=40, db_index=True)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    column = models.CharField(max_length=16)
    columns = models.JSONField(default=list)
    instruction = models.CharField(max_length=2000)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    pattern = models.CharField(max_length=512, blank=True)
    replacement = models.CharField(max_length=256, blank=True)
    ignore_case = models.BooleanField(default=False)
    explanation = models.CharField(max_length=600, blank=True)
    model = models.CharField(max_length=120, blank=True)
    policy_version = models.CharField(max_length=30, blank=True)
    cache_hit = models.BooleanField(default=False)
    preview = models.JSONField(default=dict)
    usage = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def target_columns(self):
        # Existing rules retain their primary column without a data rewrite.
        return self.columns or [self.column]


class LLMTransformation(models.Model):
    class Kind(models.TextChoices):
        DATE = 'DATE'
        CATEGORY = 'CATEGORY'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_session = models.CharField(max_length=40, db_index=True)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    column = models.CharField(max_length=16)
    instruction = models.CharField(max_length=1000, blank=True)
    options = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=Dataset.Status.choices, default=Dataset.Status.PENDING)
    model = models.CharField(max_length=120)
    preview = models.JSONField(default=dict)
    usage = models.JSONField(default=dict)
    request_budget = models.PositiveIntegerField(default=100)
    requests_used = models.PositiveIntegerField(default=0)
    requests_completed = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveBigIntegerField(default=0)
    output_tokens = models.PositiveBigIntegerField(default=0)
    plan = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
