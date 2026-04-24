import logging
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailNotification


logger = logging.getLogger(__name__)

_worker_lock = threading.Lock()
_worker_thread = None


def get_retry_delay(attempt_number):
    base_delay = getattr(settings, 'BOOKING_EMAIL_RETRY_DELAY_SECONDS', 30)
    return timedelta(seconds=base_delay * max(1, attempt_number))


def enqueue_email_notification(notification_id):
    logger.info("Queued booking confirmation email", extra={'notification_id': notification_id})
    start_email_worker()


def start_email_worker():
    global _worker_thread

    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return False

        _worker_thread = threading.Thread(
            target=run_email_worker,
            name='booking-email-worker',
            daemon=True,
        )
        _worker_thread.start()
        return True


def recover_stale_notifications():
    timeout_seconds = getattr(settings, 'BOOKING_EMAIL_PROCESSING_TIMEOUT_SECONDS', 300)
    stale_before = timezone.now() - timedelta(seconds=timeout_seconds)

    stale_count = EmailNotification.objects.filter(
        status=EmailNotification.STATUS_PROCESSING,
        last_attempt_at__lt=stale_before,
        sent_at__isnull=True,
    ).update(
        status=EmailNotification.STATUS_PENDING,
        next_attempt_at=timezone.now(),
        last_error='Recovered from stale processing state.',
    )

    if stale_count:
        logger.warning("Recovered stale email notifications", extra={'count': stale_count})


def run_email_worker():
    poll_interval = getattr(settings, 'BOOKING_EMAIL_QUEUE_POLL_INTERVAL_SECONDS', 5)
    logger.info("Booking email worker started")

    while True:
        recover_stale_notifications()

        processed = process_next_due_email()
        if processed:
            continue

        unfinished_exists = EmailNotification.objects.filter(
            status__in=[EmailNotification.STATUS_PENDING, EmailNotification.STATUS_PROCESSING],
            sent_at__isnull=True,
        ).exists()

        if not unfinished_exists:
            logger.info("Booking email worker stopped")
            return

        time.sleep(poll_interval)


def process_next_due_email():
    notification = claim_next_notification()
    if notification is None:
        return False

    try:
        send_booking_confirmation_email(notification)
    except Exception as exc:
        handle_email_failure(notification.id, exc)

    return True


def claim_next_notification():
    with transaction.atomic():
        notification = (
            EmailNotification.objects.select_for_update()
            .filter(
                status=EmailNotification.STATUS_PENDING,
                next_attempt_at__lte=timezone.now(),
                sent_at__isnull=True,
            )
            .select_related(
                'booking_batch',
                'booking_batch__movie',
                'booking_batch__theater',
                'booking_batch__user',
            )
            .first()
        )

        if notification is None:
            return None

        notification.status = EmailNotification.STATUS_PROCESSING
        notification.attempts += 1
        notification.last_attempt_at = timezone.now()
        notification.last_error = ''
        notification.save(update_fields=['status', 'attempts', 'last_attempt_at', 'last_error', 'updated_at'])
        return notification


def send_booking_confirmation_email(notification):
    batch = notification.booking_batch
    bookings = list(batch.bookings.select_related('seat').order_by('seat__seat_number'))

    if not notification.recipient_email:
        raise ValueError('Recipient email is missing for this booking confirmation.')

    context = {
        'booking_batch': batch,
        'bookings': bookings,
        'seat_numbers': [booking.seat.seat_number for booking in bookings],
        'show_time': batch.theater.time,
    }

    text_body = render_to_string('emails/booking_confirmation.txt', context)
    html_body = render_to_string('emails/booking_confirmation.html', context)

    email = EmailMultiAlternatives(
        subject=notification.subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[notification.recipient_email],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)

    notification.status = EmailNotification.STATUS_SENT
    notification.sent_at = timezone.now()
    notification.last_error = ''
    notification.save(update_fields=['status', 'sent_at', 'last_error', 'updated_at'])

    logger.info(
        "Booking confirmation email sent",
        extra={'notification_id': notification.id, 'booking_reference': batch.booking_reference},
    )


def handle_email_failure(notification_id, exc):
    notification = EmailNotification.objects.select_related('booking_batch').get(id=notification_id)
    notification.last_error = str(exc)

    if notification.attempts >= notification.max_attempts:
        notification.status = EmailNotification.STATUS_FAILED
        logger.error(
            "Booking confirmation email failed permanently",
            extra={'notification_id': notification.id, 'booking_reference': notification.booking_batch.booking_reference},
        )
    else:
        notification.status = EmailNotification.STATUS_PENDING
        notification.next_attempt_at = timezone.now() + get_retry_delay(notification.attempts)
        logger.warning(
            "Booking confirmation email will be retried",
            extra={
                'notification_id': notification.id,
                'booking_reference': notification.booking_batch.booking_reference,
                'attempts': notification.attempts,
            },
        )

    notification.save(update_fields=['status', 'next_attempt_at', 'last_error', 'updated_at'])


def queue_booking_confirmation(notification):
    transaction.on_commit(lambda: enqueue_email_notification(notification.id))
