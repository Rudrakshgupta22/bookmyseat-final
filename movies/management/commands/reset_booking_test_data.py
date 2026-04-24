from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from movies.models import (
    Booking,
    BookingBatch,
    EmailNotification,
    PaymentTransaction,
    PaymentWebhookEvent,
    Seat,
    SeatHold,
    Theater,
)


class Command(BaseCommand):
    help = (
        "Ensure each showtime has at least N seats, reset all seats to available, "
        "clear temporary holds, and clean development booking/payment data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-seats',
            type=int,
            default=10,
            help='Minimum number of seats to ensure per showtime. Default: 10',
        )
        parser.add_argument(
            '--row-prefix',
            default='A',
            help='Seat row prefix to use when creating missing seats. Default: A',
        )
        parser.add_argument(
            '--delete-related',
            action='store_true',
            help=(
                'Delete BookingBatch, PaymentTransaction, EmailNotification, and '
                'PaymentWebhookEvent rows instead of marking them expired/failed.'
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        min_seats = max(1, options['min_seats'])
        row_prefix = (options['row_prefix'] or 'A').strip() or 'A'
        delete_related = options['delete_related']

        created_seats = 0
        reset_seats = 0
        cleared_holds = 0
        deleted_bookings = 0
        cleaned_batches = 0
        cleaned_transactions = 0
        deleted_notifications = 0
        deleted_webhooks = 0

        target_seat_numbers = [f'{row_prefix}{index}' for index in range(1, min_seats + 1)]

        for theater in Theater.objects.all():
            existing_numbers = set(
                Seat.objects.filter(theater=theater).values_list('seat_number', flat=True)
            )
            seats_to_create = [
                Seat(theater=theater, seat_number=seat_number, is_booked=False)
                for seat_number in target_seat_numbers
                if seat_number not in existing_numbers
            ]
            if seats_to_create:
                Seat.objects.bulk_create(seats_to_create)
                created_seats += len(seats_to_create)

        deleted_bookings, _ = Booking.objects.all().delete()
        cleared_holds, _ = SeatHold.objects.all().delete()

        reset_seats = Seat.objects.filter(is_booked=True).update(is_booked=False)

        if delete_related:
            deleted_notifications, _ = EmailNotification.objects.all().delete()
            deleted_webhooks, _ = PaymentWebhookEvent.objects.all().delete()
            cleaned_transactions, _ = PaymentTransaction.objects.all().delete()
            cleaned_batches, _ = BookingBatch.objects.all().delete()
        else:
            deleted_notifications, _ = EmailNotification.objects.all().delete()
            deleted_webhooks, _ = PaymentWebhookEvent.objects.all().delete()

            cleaned_transactions = PaymentTransaction.objects.exclude(
                status=PaymentTransaction.STATUS_EXPIRED
            ).update(
                status=PaymentTransaction.STATUS_EXPIRED,
                last_error='Reset by reset_booking_test_data management command.',
                completed_at=None,
                verified_at=None,
            )

            cleaned_batches = BookingBatch.objects.exclude(
                status=BookingBatch.STATUS_EXPIRED
            ).update(
                status=BookingBatch.STATUS_EXPIRED,
                hold_expires_at=timezone.now(),
                finalized_at=None,
            )

        self.stdout.write(self.style.SUCCESS('Booking test data reset complete.'))
        self.stdout.write(f'Created {created_seats} seats')
        self.stdout.write(f'Reset {reset_seats} seats')
        self.stdout.write(f'Cleared {cleared_holds} temporary seat holds')
        self.stdout.write(f'Deleted {deleted_bookings} bookings')
        if delete_related:
            self.stdout.write(f'Deleted {cleaned_batches} booking batches')
            self.stdout.write(f'Deleted {cleaned_transactions} payment transactions')
        else:
            self.stdout.write(f'Cleared {cleaned_batches} booking batches')
            self.stdout.write(f'Cleared {cleaned_transactions} payment transactions')
        self.stdout.write(f'Deleted {deleted_notifications} email notifications')
        self.stdout.write(f'Deleted {deleted_webhooks} webhook events')
