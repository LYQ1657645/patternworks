"""Backfill legacy artifacts once, outside web requests; never change data or jobs."""
from django.core.management.base import BaseCommand
from processing.models import Dataset
from processing.services.content_identity import content_digest, row_digest
from processing.services.datasets import artifact_directory, create_spark


class Command(BaseCommand):
    help = 'Compute full-content identities for saved legacy datasets.'

    def handle(self, *args, **options):
        spark = None
        updated = 0
        try:
            for dataset in Dataset.objects.filter(status='READY', lifecycle__in=['ACTIVE', 'TRASH']).iterator():
                if dataset.metadata.get('content_hash'):
                    continue
                path = artifact_directory(dataset.pk) / 'parquet'
                if not path.is_dir():
                    continue
                if spark is None:
                    spark = create_spark('content-identity-maintenance')
                keys = [column['key'] for column in dataset.columns]
                rows = spark.read.parquet(str(path)).select('_row_id', *keys).orderBy('_row_id').toLocalIterator()
                signature = content_digest(dataset.columns, (row_digest(row[0], list(row[1:])) for row in rows))
                # Re-read metadata so another maintenance update is not overwritten.
                dataset.refresh_from_db(fields=['metadata'])
                dataset.metadata = {**dataset.metadata, 'content_hash': signature}
                dataset.save(update_fields=['metadata'])
                updated += 1
        finally:
            if spark is not None:
                spark.stop()
        self.stdout.write(f'Indexed content identity for {updated} datasets.')
