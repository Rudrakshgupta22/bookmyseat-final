from django.core.management.base import BaseCommand

from movies.payments import cleanup_expired_payment_holds


class Command(BaseCommand):
    help = 'Release expired seat holds and mark timed-out payments as expired.'

    def handle(self, *args, **options):
        cleanup_expired_payment_holds()
        self.stdout.write(self.style.SUCCESS('Expired payment holds cleaned up.'))
