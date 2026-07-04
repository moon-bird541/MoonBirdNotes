from django.core.management.base import BaseCommand

from notes.services.trash import purge_expired_trash_notes


class Command(BaseCommand):
    help = 'Permanently delete notes that have stayed in trash past the retention window.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Trash retention days before permanent deletion.',
        )

    def handle(self, *args, **options):
        retention_days = options['days']
        if retention_days < 1:
            self.stderr.write(self.style.ERROR('--days must be greater than 0.'))
            return

        deleted_count = purge_expired_trash_notes(retention_days=retention_days)
        self.stdout.write(self.style.SUCCESS(f'Purged {deleted_count} expired trash note(s).'))
