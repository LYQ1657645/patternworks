from django.core.management.base import BaseCommand
from processing.services.recovery import recover_jobs


class Command(BaseCommand):
    help = 'Recover stale worker attempts and repair queued deliveries without touching READY data.'

    def handle(self, *args, **options):
        self.stdout.write(str(recover_jobs()))
