from django.core.management.base import BaseCommand
from processing.services.lifecycle import maintain_datasets


class Command(BaseCommand):
    help = 'Expire opted-in derived datasets and purge eligible Trash after seven days; retain originals by default.'

    def handle(self, *args, **options):
        self.stdout.write(str(maintain_datasets()))
