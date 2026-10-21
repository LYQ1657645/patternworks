"""Worker-generated full-value CSV; the API only streams a finished file."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from django.conf import settings
from django.db import transaction

from ..models import Dataset, Job
from .datasets import DatasetCancelled, DatasetProblem, artifact_directory, create_spark


def export_path(job):
    # Only server-owned UUIDs become filesystem paths; never accept client paths.
    return settings.DATASET_ROOT / 'exports' / str(UUID(str(job.pk))) / f'{UUID(str(job.attempt_token))}.csv'


def discard_export(job):
    if job.attempt_token:
        path = export_path(job)
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass


def prepare_csv(job, report):
    source = job.dataset
    if not source or source.status != Dataset.Status.READY:
        raise DatasetProblem('SOURCE_UNAVAILABLE', 'The source dataset is not ready.')
    parquet = artifact_directory(source.pk) / 'parquet'
    if not parquet.is_dir():
        raise DatasetProblem('ARTIFACT_UNAVAILABLE', 'The full dataset is unavailable. Import it again.')
    spark = None
    settings.DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix=f'.import-{job.pk}-{job.attempt_token}-', dir=settings.DATASET_ROOT) as directory:
            work = Path(directory)
            report('Reading complete data for CSV export', 15)
            spark = create_spark(job.pk)
            if hasattr(report, 'bind_spark'):
                report.bind_spark(spark)
            # Spark spills/sorts on disk. Read the ordered part files line by
            # line, avoiding collect()/toLocalIterator() partition-sized memory.
            parts = work / 'ordered-json'
            keys = [column['key'] for column in source.columns]
            (spark.read.parquet(str(parquet)).select('_row_id', *keys)
             .orderBy('_row_id').write.json(str(parts)))
            report('Writing CSV with complete values', 60)
            csv_path = work / 'result.csv'
            count = 0
            with csv_path.open('w', encoding='utf-8-sig', newline='') as output:
                writer = csv.writer(output, lineterminator='\r\n')
                writer.writerow([column['name'] for column in source.columns])
                for part in sorted(parts.glob('part-*.json')):
                    with part.open(encoding='utf-8') as stream:
                        for line in stream:
                            record = json.loads(line)
                            count += 1
                            if record['_row_id'] != count:
                                raise DatasetProblem('EXPORT_ORDER', 'Cannot export the dataset in its original row order.')
                            writer.writerow([record.get(key) for key in keys])
                            if count % 1000 == 0:
                                report(f'Exporting CSV ({count:,} rows)', 60 + min(30, int(30 * count / max(source.row_count, 1))))
            if count != source.row_count:
                raise DatasetProblem('EXPORT_ROWS', 'The exported row count does not match the dataset.')
            size = csv_path.stat().st_size
            report('Publishing completed CSV', 95)
            with transaction.atomic():
                current = Job.objects.select_for_update().get(pk=job.pk)
                if current.status != Job.Status.RUNNING or current.attempt_token != job.attempt_token:
                    raise DatasetCancelled()
                target = export_path(job)
                target.parent.mkdir(parents=True, exist_ok=True)
                csv_path.rename(target)
            return {'dataset_id': str(source.pk), 'row_count': count, 'column_count': len(keys),
                    'bytes': size, 'filename': f'patternworks-{source.pk}.csv',
                    'download_url': f'/api/jobs/{job.pk}/download/'}
    finally:
        if spark:
            spark.stop()
