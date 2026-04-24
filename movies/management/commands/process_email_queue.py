import time

from django.core.management.base import BaseCommand

from movies.email_queue import process_next_due_email, recover_stale_notifications
from movies.models import EmailNotification


class Command(BaseCommand):
    help = 'Process queued booking confirmation emails.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Keep polling for queued emails.')
        parser.add_argument('--sleep', type=int, default=5, help='Polling interval in seconds when using --loop.')

    def handle(self, *args, **options):
        loop = options['loop']
        sleep_seconds = options['sleep']

        while True:
            recover_stale_notifications()
            processed = process_next_due_email()

            if not loop:
                if processed:
                    self.stdout.write(self.style.SUCCESS('Processed one email notification.'))
                else:
                    self.stdout.write('No due email notifications found.')
                return

            pending_exists = EmailNotification.objects.filter(
                status__in=[EmailNotification.STATUS_PENDING, EmailNotification.STATUS_PROCESSING],
                sent_at__isnull=True,
            ).exists()

            if not processed and not pending_exists:
                self.stdout.write('Email queue is empty.')
                return

            time.sleep(sleep_seconds)
