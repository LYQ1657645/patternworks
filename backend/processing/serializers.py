from rest_framework import serializers

from .models import Dataset, Job, RegexRule, LLMTransformation
from .services.retry_policy import retry_problem


class ConnectSerializer(serializers.Serializer):
    access_key_id = serializers.CharField(max_length=128, write_only=True, trim_whitespace=True)
    secret_access_key = serializers.CharField(max_length=256, write_only=True, trim_whitespace=True)
    session_token = serializers.CharField(max_length=8192, write_only=True, required=False, allow_blank=True)
    bucket = serializers.RegexField(r'^(?!.*\.\.)(?!\d+\.\d+\.\d+\.\d+$)[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$')
    region = serializers.RegexField(r'^[a-z0-9-]*$', max_length=63, required=False, allow_blank=True)


class FileQuerySerializer(serializers.Serializer):
    prefix = serializers.CharField(max_length=1024, required=False, default='', allow_blank=True, trim_whitespace=False)
    cursor = serializers.CharField(max_length=4096, required=False, default='', allow_blank=True)


class JobSerializer(serializers.ModelSerializer):
    connection_id = serializers.UUIDField(read_only=True, allow_null=True)
    retry_allowed = serializers.SerializerMethodField()
    retry_unavailable_reason = serializers.SerializerMethodField()
    dataset_available = serializers.SerializerMethodField()

    def get_dataset_available(self,job):
        dataset=job.dataset or (job.rule.dataset if job.rule_id else job.transformation.dataset if job.transformation_id else None)
        return bool(dataset and dataset.lifecycle=='ACTIVE' and dataset.status=='READY')

    def get_retry_allowed(self, job):
        return not retry_problem(job)

    def get_retry_unavailable_reason(self, job):
        return retry_problem(job) if job.status in {Job.Status.FAILED, Job.Status.CANCELLED} else ''

    class Meta:
        model = Job
        fields = ['id', 'kind', 'connection_id', 'dataset_id', 'rule_id', 'transformation_id', 'status', 'progress', 'stage', 'error_code',
                  'error_message', 'result', 'created_at', 'started_at', 'finished_at',
                  'attempt_count', 'recovery_count', 'heartbeat_at', 'retry_allowed', 'retry_unavailable_reason', 'dataset_available']
        read_only_fields = fields


class ImportSerializer(serializers.Serializer):
    connection_id = serializers.UUIDField()
    key = serializers.CharField(max_length=1024, trim_whitespace=False)
    sheet_name = serializers.CharField(max_length=128, required=False, default='', allow_blank=True, trim_whitespace=False)

    def validate_key(self, value):
        from pathlib import PurePosixPath
        if PurePosixPath(value).suffix.lower() not in {'.csv', '.xlsx', '.xls'}:
            raise serializers.ValidationError('Choose a CSV, XLSX or XLS file.')
        return value


class RowsQuerySerializer(serializers.Serializer):
    after = serializers.IntegerField(min_value=0, max_value=9223372036854775807, default=0)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=25)


class HistoryQuerySerializer(serializers.Serializer):
    cursor = serializers.CharField(max_length=2048, required=False, default='', allow_blank=True)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=10)
    status = serializers.ChoiceField(choices=Job.Status.choices, required=False, default='', allow_blank=True)
    kind = serializers.ChoiceField(choices=Job.Kind.choices, required=False, default='', allow_blank=True)


class DatasetListQuerySerializer(serializers.Serializer):
    latest_imports = serializers.BooleanField(default=False)
    cursor = serializers.CharField(max_length=2048, required=False, default='', allow_blank=True)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=25)
    status = serializers.ChoiceField(choices=Dataset.Status.choices, required=False, default='', allow_blank=True)
    q = serializers.CharField(max_length=256, required=False, default='', allow_blank=True)
    scope = serializers.ChoiceField(choices=['ACTIVE','TRASH','ALL'],default='ACTIVE')
    parent_id = serializers.UUIDField(required=False,allow_null=True,default=None)

    def to_internal_value(self,data):
        data=data.copy()
        if data.get('parent_id')=='':data['parent_id']=None
        return super().to_internal_value(data)


class TrashDatasetSerializer(serializers.Serializer):
    confirm_id = serializers.CharField(max_length=36,trim_whitespace=False)
    review_token = serializers.CharField(max_length=2048)
    confirm_original = serializers.BooleanField(default=False)


class RetentionSerializer(serializers.Serializer):
    days = serializers.ChoiceField(choices=[0,7,30,90])
    confirm_expiry = serializers.BooleanField(default=False)


class ReplaceTextSerializer(serializers.Serializer):
    column = serializers.RegexField(r'^c\d+$', max_length=16)
    find = serializers.CharField(max_length=256, trim_whitespace=False)
    replacement = serializers.CharField(max_length=256, allow_blank=True, trim_whitespace=False)


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = ['id', 'parent_id', 'source_key', 'source_format', 'sheet_name', 'status',
                  'row_count', 'columns', 'metadata', 'created_at','lifecycle','retention_days','expires_at',
                  'trashed_at','purge_after','purged_at','trash_reason']
        read_only_fields = fields


class GenerateRuleSerializer(serializers.Serializer):
    column = serializers.RegexField(r'^c\d+$', max_length=16, required=False)
    columns = serializers.ListField(child=serializers.RegexField(r'^c\d+$', max_length=16),
                                    min_length=1, max_length=256, required=False)
    instruction = serializers.CharField(max_length=2000)
    replacement = serializers.CharField(max_length=256, required=False, allow_blank=True, trim_whitespace=False)

    def validate(self, values):
        if ('column' in values) == ('columns' in values):
            raise serializers.ValidationError('Provide either column or columns, with at least one target column.')
        columns = values.get('columns', [values.get('column')])
        if len(set(columns)) != len(columns):
            raise serializers.ValidationError('Choose each target column only once.')
        values['columns'] = columns
        values['column'] = columns[0]
        return values


class RegexRuleSerializer(serializers.ModelSerializer):
    columns = serializers.SerializerMethodField()

    def get_columns(self, rule):
        return rule.target_columns

    class Meta:
        model = RegexRule
        fields = ['id', 'dataset_id', 'column', 'columns', 'instruction', 'status', 'pattern', 'replacement', 'ignore_case',
                  'explanation', 'model', 'policy_version', 'cache_hit', 'preview', 'usage', 'created_at']
        read_only_fields = fields


class TransformRequestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=LLMTransformation.Kind.choices)
    column = serializers.RegexField(r'^c\d+$', max_length=16)
    instruction = serializers.CharField(max_length=1000, required=False, default='', allow_blank=True)
    options = serializers.JSONField()
    allow_send_values = serializers.BooleanField()

    def validate(self, values):
        from .services.transformations import validate_config
        from .services.rules import RuleProblem
        if values.pop('allow_send_values') is not True:
            raise serializers.ValidationError('Confirm sending selected-column values to OpenAI before previewing.')
        if not isinstance(values['options'], dict):
            raise serializers.ValidationError('Options must be an object.')
        try:
            validate_config(values['kind'], values['options'])
        except RuleProblem as exc:
            raise serializers.ValidationError(exc.message) from None
        return values


class LLMTransformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLMTransformation
        fields = ['id', 'dataset_id', 'kind', 'column', 'instruction', 'options', 'status', 'model', 'preview', 'usage', 'created_at']
        read_only_fields = fields
