from datetime import timedelta

from django.conf import settings
from django.db import connection as database
from django.db import transaction
from django.db.models import Q, Exists, OuterRef
from uuid import UUID
from django.middleware.csrf import get_token
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from redis import Redis
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Dataset, Job, RegexRule, S3Connection, LLMTransformation
from .serializers import (ConnectSerializer, DatasetSerializer, FileQuerySerializer, ImportSerializer,
                          JobSerializer, ReplaceTextSerializer, RowsQuerySerializer,
                          GenerateRuleSerializer, RegexRuleSerializer, TransformRequestSerializer, LLMTransformationSerializer,
                          DatasetListQuerySerializer, HistoryQuerySerializer, TrashDatasetSerializer, RetentionSerializer,
                          TransformApplySerializer)
from .services.credentials import CredentialsUnavailable, encrypt_credentials
from .services.jobs import dispatch
from .services.s3 import S3Problem, list_files
from .services.datasets import DatasetProblem, read_page
from .services.recovery import retry_job
from .services.execution import cleanup_outputs
from .services.exports import export_path
from .services.history import history_page
from .services.lifecycle import require_active, review, trash_dataset, restore_dataset, set_retention, LifecycleProblem


@method_decorator(csrf_protect, name='dispatch')
class SessionAPIView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response

    def owner(self, request):
        # session_key alone trusts the cookie without loading the DB session.
        # Access the public mapping API first so expiry/deletion is enforced,
        # including valid sessions whose stored data is empty.
        request.session.keys()
        if not request.session.session_key:
            request.session.create()
        return request.session.session_key


class SessionView(SessionAPIView):
    def get(self, request):
        self.owner(request)
        return Response({'csrf_token': get_token(request), 'connection_ttl_seconds': settings.CONNECTION_TTL_SECONDS})


class HealthView(APIView):
    def get(self, request):
        checks = {}
        try:
            database.ensure_connection()
            checks['database'] = 'ok'
        except Exception:
            checks['database'] = 'unavailable'
        try:
            Redis.from_url(settings.CACHE_URL, socket_connect_timeout=1, socket_timeout=1).ping()
            checks['redis'] = 'ok'
        except Exception:
            checks['redis'] = 'unavailable'
        ready = all(v == 'ok' for v in checks.values())
        return Response({'status': 'ok' if ready else 'degraded', 'checks': checks,
                         'openai_configured': bool(settings.OPENAI_API_KEY),
                         'phase': 'Data preparation'}, status=200 if ready else 503)


class DiagnosticView(SessionAPIView):
    def post(self, request):
        job = Job.objects.create(owner_session=self.owner(request), kind=Job.Kind.DIAGNOSTIC)
        if not dispatch(job):
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


@method_decorator(sensitive_post_parameters('access_key_id', 'secret_access_key', 'session_token'), name='dispatch')
class ConnectionView(SessionAPIView):
    def get(self, request):
        records = S3Connection.objects.filter(owner_session=self.owner(request),
            status=S3Connection.Status.READY, expires_at__gt=timezone.now()).exclude(encrypted_credentials=b'')
        return Response({'connections': list(records.order_by('-created_at').values('id', 'bucket', 'region', 'expires_at')[:5])})

    @sensitive_variables()
    def post(self, request):
        if not settings.DEBUG and not request.is_secure():
            return Response({'detail': 'HTTPS is required when submitting credentials.'}, status=400)
        serializer = ConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        owner = self.owner(request)
        record = S3Connection.objects.create(
            owner_session=owner, bucket=values['bucket'], region=values.get('region', ''),
            encrypted_credentials=encrypt_credentials({
                'access_key_id': values['access_key_id'], 'secret_access_key': values['secret_access_key'],
                'session_token': values.get('session_token', ''),
            }),
            expires_at=timezone.now() + timedelta(seconds=settings.CONNECTION_TTL_SECONDS),
        )
        job = Job.objects.create(owner_session=owner, kind=Job.Kind.CONNECT_S3, connection=record)
        if not dispatch(job):
            S3Connection.objects.filter(pk=record.pk).update(status=S3Connection.Status.FAILED, encrypted_credentials=b'')
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class DisconnectConnectionsView(SessionAPIView):
    def post(self, request):
        owner = self.owner(request)
        with transaction.atomic():
            records = S3Connection.objects.select_for_update().filter(owner_session=owner)
            ids = list(records.values_list('pk', flat=True))
            if Job.objects.filter(connection_id__in=ids, status__in=['QUEUED', 'RUNNING']).exists():
                return Response({'detail': 'Wait for the S3 task to finish or cancel it before disconnecting.'}, status=409)
            records.update(encrypted_credentials=b'', status=S3Connection.Status.FAILED, expires_at=timezone.now())
        return Response({'disconnected': True})


class FileListView(SessionAPIView):
    def get(self, request, connection_id):
        record = get_object_or_404(S3Connection, pk=connection_id, owner_session=self.owner(request))
        if record.expires_at <= timezone.now():
            S3Connection.objects.filter(pk=record.pk).update(encrypted_credentials=b'', status=S3Connection.Status.FAILED)
            return Response({'detail': 'Connection expired. Please reconnect.'}, status=410)
        if record.status != S3Connection.Status.READY:
            return Response({'detail': 'The connection is not ready. Please reconnect or wait.'}, status=409)
        serializer = FileQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(list_files(record, **serializer.validated_data))
        except CredentialsUnavailable:
            return Response({'detail': 'Connection expired. Please reconnect.'}, status=410)
        except S3Problem as exc:
            return Response({'detail': exc.message, 'code': exc.code}, status=503 if exc.transient else 400)


class WorksheetListView(SessionAPIView):
    def post(self, request, connection_id):
        owner = self.owner(request)
        serializer = ImportSerializer(data={'connection_id': str(connection_id), 'key': request.data.get('key', '')})
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data['key']
        if not key.lower().endswith(('.xlsx', '.xls')):
            return Response({'detail': 'Choose an Excel file to list worksheets.'}, status=400)
        with transaction.atomic():
            record = get_object_or_404(S3Connection.objects.select_for_update(), pk=connection_id, owner_session=owner)
            if record.expires_at <= timezone.now() or not record.encrypted_credentials:
                return Response({'detail': 'Connection expired. Please reconnect.'}, status=410)
            if record.status != S3Connection.Status.READY:
                return Response({'detail': 'The connection is not ready. Please reconnect or wait.'}, status=409)
            # A repeated submission after a lost response resumes the in-flight task.
            job = Job.objects.filter(owner_session=owner, connection=record, kind=Job.Kind.LIST_WORKSHEETS,
                                     parameters__key=key, status__in=['QUEUED', 'RUNNING']).first()
            if job:
                return Response(JobSerializer(job).data, status=202)
            job = Job.objects.create(owner_session=owner, connection=record, kind=Job.Kind.LIST_WORKSHEETS,
                                     parameters={'key': key})
        if not dispatch(job):
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class JobView(SessionAPIView):
    def get(self, request, job_id):
        job = get_object_or_404(Job, pk=job_id, owner_session=self.owner(request))
        return Response(JobSerializer(job).data)


class CancelJobView(SessionAPIView):
    def post(self, request, job_id):
        job = get_object_or_404(Job, pk=job_id, owner_session=self.owner(request))
        Job.objects.filter(pk=job.pk, status__in=[Job.Status.QUEUED, Job.Status.RUNNING]).update(
            status=Job.Status.CANCELLED, stage='Cancelled', finished_at=timezone.now(),
        )
        job.refresh_from_db()
        if job.status == Job.Status.CANCELLED and job.connection_id and job.kind == Job.Kind.CONNECT_S3:
            S3Connection.objects.filter(pk=job.connection_id).update(
                status=S3Connection.Status.FAILED, encrypted_credentials=b'',
            )
        if job.status == Job.Status.CANCELLED and job.dataset_id and job.kind != Job.Kind.EXPORT_CSV:
            Dataset.objects.filter(pk=job.dataset_id, status=Dataset.Status.PENDING).update(status=Dataset.Status.CANCELLED)
        if job.status == Job.Status.CANCELLED and job.rule_id and job.kind == Job.Kind.GENERATE_RULE:
            RegexRule.objects.filter(pk=job.rule_id, status=RegexRule.Status.PENDING).update(status=RegexRule.Status.CANCELLED)
        if job.status == Job.Status.CANCELLED and job.transformation_id and job.kind == Job.Kind.PREVIEW_TRANSFORM:
            LLMTransformation.objects.filter(pk=job.transformation_id, status=Dataset.Status.PENDING).update(status=Dataset.Status.CANCELLED)
        # The attempt watchdog interrupts the active Spark job group. In-flight
        # provider calls may finish; publication is fenced by the DB row/token.
        return Response(JobSerializer(job).data)


class RetryJobView(SessionAPIView):
    def post(self, request, job_id):
        previous = get_object_or_404(Job, pk=job_id, owner_session=self.owner(request))
        try:
            job = retry_job(previous)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=409)
        if not dispatch(job):
            cleanup_outputs(job)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


def _submit_dataset(dataset, kind, parameters=None):
    job = Job.objects.create(owner_session=dataset.owner_session, kind=kind, connection=dataset.connection,
                             dataset=dataset, parameters=parameters or {})
    return job


class DatasetListView(SessionAPIView):
    def get(self, request):
        query = DatasetListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        options, owner = query.validated_data, self.owner(request)
        records = Dataset.objects.filter(owner_session=owner)
        if options['scope']=='ACTIVE':records=records.filter(lifecycle='ACTIVE')
        elif options['scope']=='TRASH':records=records.filter(lifecycle__in=['TRASH','PURGING'])
        else:records=records.exclude(lifecycle='PURGED')
        if options['parent_id']:records=records.filter(parent_id=options['parent_id'])
        if options['status']:
            records = records.filter(status=options['status'])
        if options['q']:
            search = Q(source_key__icontains=options['q']) | Q(sheet_name__icontains=options['q'])
            try:
                search |= Q(pk=UUID(options['q']))
            except ValueError:
                pass
            records = records.filter(search)
        # Group original imports before pagination, across refreshed S3 connections.
        # Keep transformation outputs and trash/dependency views individually accessible.
        if options['latest_imports'] and options['scope'] == 'ACTIVE' and not options['parent_id']:
            newer = records.filter(
                parent_id__isnull=True, connection__bucket=OuterRef('connection__bucket'),
                source_key=OuterRef('source_key'), sheet_name=OuterRef('sheet_name'),
            ).filter(Q(created_at__gt=OuterRef('created_at')) |
                     Q(created_at=OuterRef('created_at'), pk__gt=OuterRef('pk')))
            records = records.annotate(newer_import=Exists(newer)).filter(
                Q(parent_id__isnull=False) | Q(connection_id__isnull=True) | Q(newer_import=False))
        entries, cursor = history_page(records, owner, 'datasets', options)
        return Response({'datasets': DatasetSerializer(entries, many=True).data, 'next_cursor': cursor})

    def post(self, request):
        serializer = ImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        owner = self.owner(request)
        record = get_object_or_404(S3Connection, pk=values['connection_id'], owner_session=owner)
        if record.expires_at <= timezone.now() or not record.encrypted_credentials:
            return Response({'detail': 'Connection expired. Please reconnect.'}, status=410)
        if record.status != S3Connection.Status.READY:
            return Response({'detail': 'The connection is not ready.'}, status=409)
        from pathlib import PurePosixPath
        with transaction.atomic():
            dataset = Dataset.objects.create(owner_session=owner, connection=record, source_key=values['key'],
                                              source_format=PurePosixPath(values['key']).suffix.lower()[1:],
                                              sheet_name=values['sheet_name'])
            job = _submit_dataset(dataset, Job.Kind.IMPORT_DATASET)
        if not dispatch(job):
            Dataset.objects.filter(pk=dataset.pk).update(status=Dataset.Status.FAILED)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class DatasetGalaxyView(SessionAPIView):
    def get(self, request):
        query = DatasetListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        options, owner = query.validated_data, self.owner(request)
        records = Dataset.objects.filter(owner_session=owner).select_related('connection')
        if options['scope'] == 'ACTIVE': records = records.filter(lifecycle='ACTIVE')
        elif options['scope'] == 'TRASH': records = records.filter(lifecycle__in=['TRASH', 'PURGING'])
        else: records = records.exclude(lifecycle='PURGED')
        if options['status']: records = records.filter(status=options['status'])
        if options['parent_id']: records = records.filter(parent_id=options['parent_id'])
        if options['q']:
            search = Q(source_key__icontains=options['q']) | Q(sheet_name__icontains=options['q'])
            try: search |= Q(pk=UUID(options['q']))
            except ValueError: pass
            records = records.filter(search)
        entries, cursor = history_page(records, owner, 'dataset-galaxy', options)
        from .services.lineage import library_graph
        result = library_graph(entries, owner)
        result.update(next_cursor=cursor, limit=options['limit'])
        return Response(result)


class DatasetLineageView(SessionAPIView):
    def get(self, request, dataset_id):
        owner = self.owner(request)
        anchor = get_object_or_404(Dataset.objects.select_related('connection'), pk=dataset_id, owner_session=owner)
        from .services.lineage import version_graph
        from rest_framework.exceptions import ValidationError
        try:
            limit = int(request.query_params.get('limit', 200))
        except (ValueError, TypeError):
            raise ValidationError({'limit': 'Choose a limit from 50 to 500.'})
        if not 50 <= limit <= 500:
            raise ValidationError({'limit': 'Choose a limit from 50 to 500.'})
        return Response(version_graph(anchor, owner, limit))


class DatasetView(SessionAPIView):
    def get(self, request, dataset_id):
        dataset = get_object_or_404(Dataset, pk=dataset_id, owner_session=self.owner(request))
        require_active(dataset)
        return Response(DatasetSerializer(dataset).data)


class DatasetLifecycleView(SessionAPIView):
    def get(self,request,dataset_id):
        dataset=get_object_or_404(Dataset,pk=dataset_id,owner_session=self.owner(request))
        return Response(review(dataset))


class TrashDatasetView(SessionAPIView):
    def post(self,request,dataset_id):
        owner=self.owner(request)
        get_object_or_404(Dataset,pk=dataset_id,owner_session=owner)
        serializer=TrashDatasetSerializer(data=request.data);serializer.is_valid(raise_exception=True)
        values=serializer.validated_data
        dataset=trash_dataset(dataset_id,owner,values['confirm_id'],values['review_token'],values['confirm_original'])
        return Response(DatasetSerializer(dataset).data)


class RestoreDatasetView(SessionAPIView):
    def post(self,request,dataset_id):
        owner=self.owner(request);get_object_or_404(Dataset,pk=dataset_id,owner_session=owner)
        return Response(DatasetSerializer(restore_dataset(dataset_id,owner)).data)


class DatasetRetentionView(SessionAPIView):
    def post(self,request,dataset_id):
        owner=self.owner(request);get_object_or_404(Dataset,pk=dataset_id,owner_session=owner)
        serializer=RetentionSerializer(data=request.data);serializer.is_valid(raise_exception=True)
        values=serializer.validated_data
        return Response(DatasetSerializer(set_retention(dataset_id,owner,values['days'],values['confirm_expiry'])).data)


class DatasetExportView(SessionAPIView):
    def get(self, request, dataset_id):
        source = get_object_or_404(Dataset, pk=dataset_id, owner_session=self.owner(request))
        require_active(source)
        job = Job.objects.filter(dataset=source, kind=Job.Kind.EXPORT_CSV).first()
        available = bool(job and job.status == Job.Status.SUCCESS and job.attempt_token and export_path(job).is_file())
        return Response({'job': JobSerializer(job).data if job else None, 'download_available': available})

    def post(self, request, dataset_id):
        # Serialize duplicate clicks/tabs for a dataset; reuse active/finished
        # exports without re-running Spark or creating duplicate files.
        with transaction.atomic():
            source = get_object_or_404(Dataset.objects.select_for_update(), pk=dataset_id, owner_session=self.owner(request))
            require_active(source)
            if source.status != Dataset.Status.READY:
                return Response({'detail': 'The dataset is not ready.'}, status=409)
            job = Job.objects.filter(dataset=source, kind=Job.Kind.EXPORT_CSV,
                                     status__in=[Job.Status.QUEUED, Job.Status.RUNNING, Job.Status.SUCCESS]).first()
            if job and job.status in [Job.Status.QUEUED, Job.Status.RUNNING]:
                return Response(JobSerializer(job).data, status=202)
            if job and job.attempt_token and export_path(job).is_file():
                return Response(JobSerializer(job).data)
            job = Job.objects.create(owner_session=source.owner_session, dataset=source, kind=Job.Kind.EXPORT_CSV)
        if not dispatch(job):
            cleanup_outputs(job)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class ExportDownloadView(SessionAPIView):
    def get(self, request, job_id):
        job = get_object_or_404(Job, pk=job_id, owner_session=self.owner(request), kind=Job.Kind.EXPORT_CSV)
        if job.status != Job.Status.SUCCESS:
            return Response({'detail': 'The CSV export is not ready.'}, status=409)
        if not job.dataset_id or job.dataset.lifecycle!='ACTIVE':
            return Response({'detail':'The source dataset is in Trash or has been purged.'},status=410)
        try:
            stream = export_path(job).open('rb') if job.attempt_token else None
        except FileNotFoundError:
            stream = None
        if stream is None:
            return Response({'detail': 'The CSV file is unavailable. Generate the export again.'}, status=410)
        return FileResponse(stream, as_attachment=True, filename=f'patternworks-{job.dataset_id}.csv',
                            content_type='text/csv; charset=utf-8')


class DatasetRowsView(SessionAPIView):
    def get(self, request, dataset_id):
        dataset = get_object_or_404(Dataset, pk=dataset_id, owner_session=self.owner(request))
        require_active(dataset)
        if dataset.status != Dataset.Status.READY:
            return Response({'detail': 'The dataset is not ready.'}, status=409)
        serializer = RowsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(read_page(dataset, **serializer.validated_data))
        except DatasetProblem as exc:
            return Response({'detail': exc.message, 'code': exc.code}, status=410)


class ReplaceTextView(SessionAPIView):
    def post(self, request, dataset_id):
        with transaction.atomic():
            parent = get_object_or_404(Dataset.objects.select_for_update(), pk=dataset_id, owner_session=self.owner(request))
            require_active(parent)
            if parent.status != Dataset.Status.READY:
                return Response({'detail': 'The dataset is not ready.'}, status=409)
            serializer = ReplaceTextSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            if values['column'] not in {column['key'] for column in parent.columns}:
                return Response({'detail': 'Choose an existing column.'}, status=400)
            dataset = Dataset.objects.create(owner_session=parent.owner_session, parent=parent,
                source_key=parent.source_key, source_format=parent.source_format, sheet_name=parent.sheet_name)
            job = _submit_dataset(dataset, Job.Kind.REPLACE_TEXT, values)
        if not dispatch(job):
            Dataset.objects.filter(pk=dataset.pk).update(status=Dataset.Status.FAILED)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class JobListView(SessionAPIView):
    def get(self, request):
        query = HistoryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        options, owner = query.validated_data, self.owner(request)
        records = Job.objects.filter(owner_session=owner).select_related('connection','dataset__parent','rule__dataset__parent','transformation__dataset__parent')
        for field in ['status', 'kind']:
            if options[field]:
                records = records.filter(**{field: options[field]})
        entries, cursor = history_page(records, owner, 'jobs', options)
        return Response({'jobs': JobSerializer(entries, many=True).data, 'next_cursor': cursor})


class DatasetRulesView(SessionAPIView):
    def get(self, request, dataset_id):
        dataset = get_object_or_404(Dataset, pk=dataset_id, owner_session=self.owner(request))
        require_active(dataset)
        rules = RegexRule.objects.filter(dataset=dataset, owner_session=dataset.owner_session).order_by('-created_at')[:10]
        return Response({'rules': RegexRuleSerializer(rules, many=True).data})

    def post(self, request, dataset_id):
        with transaction.atomic():
            dataset = get_object_or_404(Dataset.objects.select_for_update(), pk=dataset_id, owner_session=self.owner(request))
            require_active(dataset)
            if dataset.status != Dataset.Status.READY:
                return Response({'detail': 'The dataset is not ready.'}, status=409)
            serializer = GenerateRuleSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            if not set(values['columns']).issubset({column['key'] for column in dataset.columns}):
                return Response({'detail': 'Choose existing target columns.'}, status=400)
            parameters = {'replacement': values.pop('replacement')} if 'replacement' in values else {}
            rule = RegexRule.objects.create(owner_session=dataset.owner_session, dataset=dataset, **values)
            # Generation never targets an output dataset: cancellation cannot erase the source.
            job = Job.objects.create(owner_session=dataset.owner_session, kind=Job.Kind.GENERATE_RULE,
                                     rule=rule, parameters=parameters)
        if not dispatch(job):
            RegexRule.objects.filter(pk=rule.pk).update(status=RegexRule.Status.FAILED)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class RuleView(SessionAPIView):
    def get(self, request, rule_id):
        rule = get_object_or_404(RegexRule, pk=rule_id, owner_session=self.owner(request))
        require_active(rule.dataset)
        return Response(RegexRuleSerializer(rule).data)


class ApplyRuleView(SessionAPIView):
    def post(self, request, rule_id):
        rule = get_object_or_404(RegexRule.objects.select_related('dataset'), pk=rule_id, owner_session=self.owner(request))
        with transaction.atomic():
            source = get_object_or_404(Dataset.objects.select_for_update(),pk=rule.dataset_id,owner_session=self.owner(request))
            require_active(source)
            if rule.status != RegexRule.Status.READY or source.status != Dataset.Status.READY:
                return Response({'detail': 'The rule or source dataset is not ready.'}, status=409)
            dataset = Dataset.objects.create(owner_session=rule.owner_session, parent=source,
                source_key=source.source_key, source_format=source.source_format, sheet_name=source.sheet_name)
            job = Job.objects.create(owner_session=rule.owner_session, kind=Job.Kind.APPLY_RULE, dataset=dataset, rule=rule)
        if not dispatch(job):
            Dataset.objects.filter(pk=dataset.pk).update(status=Dataset.Status.FAILED)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class DatasetTransformationsView(SessionAPIView):
    def get(self, request, dataset_id):
        source = get_object_or_404(Dataset, pk=dataset_id, owner_session=self.owner(request))
        require_active(source)
        records = LLMTransformation.objects.filter(dataset=source, owner_session=source.owner_session).order_by('-created_at')[:10]
        return Response({'transformations': LLMTransformationSerializer(records, many=True).data})

    def post(self, request, dataset_id):
        with transaction.atomic():
            source = get_object_or_404(Dataset.objects.select_for_update(), pk=dataset_id, owner_session=self.owner(request))
            require_active(source)
            if source.status != Dataset.Status.READY:
                return Response({'detail': 'The dataset is not ready.'}, status=409)
            serializer = TransformRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            values = serializer.validated_data
            if values['column'] not in {column['key'] for column in source.columns}:
                return Response({'detail': 'Choose an existing column.'}, status=400)
            if len(source.columns) + 2 > settings.MAX_DATASET_COLUMNS:
                return Response({'detail': 'This transformation needs space for two additional columns.'}, status=400)
            record = LLMTransformation.objects.create(owner_session=source.owner_session, dataset=source,
                                                       model=settings.OPENAI_MODEL, **values)
            job = Job.objects.create(owner_session=source.owner_session, kind=Job.Kind.PREVIEW_TRANSFORM, transformation=record)
        if not dispatch(job):
            LLMTransformation.objects.filter(pk=record.pk).update(status=Dataset.Status.FAILED)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)


class TransformationView(SessionAPIView):
    def get(self, request, transformation_id):
        record = get_object_or_404(LLMTransformation, pk=transformation_id, owner_session=self.owner(request))
        require_active(record.dataset)
        return Response(LLMTransformationSerializer(record).data)


class ApplyTransformationView(SessionAPIView):
    def post(self, request, transformation_id):
        record = get_object_or_404(LLMTransformation.objects.select_related('dataset'), pk=transformation_id, owner_session=self.owner(request))
        with transaction.atomic():
            source = get_object_or_404(Dataset.objects.select_for_update(),pk=record.dataset_id,owner_session=self.owner(request))
            require_active(source)
            if record.status != Dataset.Status.READY or source.status != Dataset.Status.READY:
                return Response({'detail': 'The transformation or source dataset is not ready.'}, status=409)
            serializer = TransformApplySerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            active = Job.objects.filter(transformation=record, kind=Job.Kind.APPLY_TRANSFORM,
                                        status__in=[Job.Status.QUEUED, Job.Status.RUNNING]).first()
            if active:
                return Response(JobSerializer(active).data, status=202)
            if 'request_budget' in serializer.validated_data:
                budget = serializer.validated_data['request_budget']
                if budget < record.requests_used:
                    return Response({'detail': 'Budget cannot be lower than requests already used.'}, status=400)
                LLMTransformation.objects.filter(pk=record.pk).update(request_budget=budget)
            dataset = Dataset.objects.create(owner_session=record.owner_session, parent=source,
                source_key=source.source_key, source_format=source.source_format, sheet_name=source.sheet_name)
            job = Job.objects.create(owner_session=record.owner_session, kind=Job.Kind.APPLY_TRANSFORM,
                                     dataset=dataset, transformation=record)
        if not dispatch(job):
            Dataset.objects.filter(pk=dataset.pk).update(status=Dataset.Status.FAILED)
            job.refresh_from_db()
            return Response(JobSerializer(job).data, status=503)
        return Response(JobSerializer(job).data, status=202)
