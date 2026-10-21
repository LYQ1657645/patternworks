from django.core.management.base import BaseCommand
from django.utils import timezone
from processing.models import S3Connection


class Command(BaseCommand):
    help = 'Wipe expired encrypted AWS credentials; retain non-secret task history.'

    def handle(self, *args, **options):
        count = S3Connection.objects.filter(expires_at__lte=timezone.now()).exclude(encrypted_credentials=b'').update(
            encrypted_credentials=b'', status=S3Connection.Status.FAILED,
        )
        self.stdout.write(f'Cleared credentials from {count} expired connections.')
