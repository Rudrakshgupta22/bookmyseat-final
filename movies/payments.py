import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .analytics import invalidate_admin_dashboard_cache
from .email_queue import queue_booking_confirmation
from .models import Booking, BookingBatch, EmailNotification, PaymentTransaction, Seat, SeatHold


logger = logging.getLogger(__name__)

STRIPE_MIN_CHECKOUT_MINUTES = 30


class PaymentGatewayError(Exception):
    pass


def ticket_price_minor():
    return int(getattr(settings, 'PAYMENT_TICKET_PRICE_MINOR', 25000))


def hold_duration():
    configured_minutes = int(getattr(settings, 'SEAT_RESERVATION_TIMEOUT_MINUTES', 2))
    return timedelta(minutes=max(configured_minutes, 1))


def stripe_checkout_duration():
    configured_minutes = int(getattr(settings, 'PAYMENT_HOLD_DURATION_MINUTES', STRIPE_MIN_CHECKOUT_MINUTES))
    return timedelta(minutes=max(configured_minutes, STRIPE_MIN_CHECKOUT_MINUTES))


def batch_total_amount(seat_count):
    return ticket_price_minor() * seat_count


def cleanup_expired_payment_holds():
    now = timezone.now()
    expired_batches = BookingBatch.objects.filter(
        status__in=[
            BookingBatch.STATUS_PENDING_PAYMENT,
            BookingBatch.STATUS_PAYMENT_PROCESSING,
            BookingBatch.STATUS_CANCELLED,
        ],
        hold_expires_at__isnull=False,
        hold_expires_at__lte=now,
    ).distinct()

    for batch in expired_batches:
        expire_booking_batch(batch, reason='Payment session timed out before confirmation.')


def create_pending_booking_batch(user, theater, seats):
    expires_at = timezone.now() + hold_duration()
    amount_total = batch_total_amount(len(seats))

    booking_batch = BookingBatch.objects.create(
        user=user,
        movie=theater.movie,
        theater=theater,
        recipient_email=user.email,
        total_tickets=len(seats),
        status=BookingBatch.STATUS_PENDING_PAYMENT,
        currency=getattr(settings, 'PAYMENT_CURRENCY', 'inr'),
        amount_total=amount_total,
        hold_expires_at=expires_at,
    )

    SeatHold.objects.bulk_create([
        SeatHold(booking_batch=booking_batch, seat=seat, expires_at=expires_at)
        for seat in seats
    ])

    payment_transaction = PaymentTransaction.objects.create(
        booking_batch=booking_batch,
        status=PaymentTransaction.STATUS_INITIATED,
        amount=amount_total,
        currency=booking_batch.currency,
        idempotency_key=uuid4().hex,
    )

    return booking_batch, payment_transaction


def validate_and_lock_available_seats(theater, selected_seat_ids):
    cleanup_expired_payment_holds()

    seats = list(
        Seat.objects.select_for_update()
        .filter(theater=theater, id__in=selected_seat_ids)
        .order_by('seat_number')
    )

    if len(seats) != len(selected_seat_ids):
        return None, 'One or more selected seats are invalid.'

    already_booked = [seat.seat_number for seat in seats if seat.is_booked]
    if already_booked:
        return None, f"The following seats are already booked: {', '.join(already_booked)}"

    active_holds = SeatHold.objects.select_related('booking_batch').filter(
        seat__in=seats,
        expires_at__gt=timezone.now(),
    )

    blocked_seats = [seat_hold.seat.seat_number for seat_hold in active_holds]
    if blocked_seats:
        return None, f"The following seats are temporarily reserved: {', '.join(blocked_seats)}"

    SeatHold.objects.filter(seat__in=seats, expires_at__lte=timezone.now()).delete()
    return seats, ''


def build_basic_auth_header(secret_key):
    token = base64.b64encode(f'{secret_key}:'.encode('utf-8')).decode('ascii')
    return f'Basic {token}'


def stripe_api_request(method, path, data=None, idempotency_key=None):
    secret_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    if not secret_key:
        raise PaymentGatewayError('Stripe secret key is not configured.')

    base_url = getattr(settings, 'STRIPE_API_BASE', 'https://api.stripe.com')
    headers = {
        'Authorization': build_basic_auth_header(secret_key),
    }
    payload = None

    if data is not None:
        payload = urllib.parse.urlencode(data).encode('utf-8')
        headers['Content-Type'] = 'application/x-www-form-urlencoded'

    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key

    request = urllib.request.Request(
        url=f'{base_url}{path}',
        data=payload,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode('utf-8', errors='replace')
        raise PaymentGatewayError(f'Stripe API error {exc.code}: {response_body}')
    except urllib.error.URLError as exc:
        raise PaymentGatewayError(f'Stripe API connection error: {exc.reason}')


def retrieve_stripe_checkout_session(session_id):
    if not session_id:
        raise PaymentGatewayError('Stripe Checkout Session ID is missing.')

    query = urllib.parse.urlencode({
        'expand[]': ['payment_intent'],
    }, doseq=True)
    return stripe_api_request('GET', f'/v1/checkout/sessions/{session_id}?{query}')


def verify_payment_transaction_with_stripe(payment_transaction):
    session = retrieve_stripe_checkout_session(payment_transaction.gateway_checkout_session_id)
    payment_status = session.get('payment_status')
    session_status = session.get('status')
    payment_intent = session.get('payment_intent') or {}
    payment_intent_id = payment_intent.get('id', '')

    if payment_status == 'paid':
        finalize_successful_payment(
            payment_transaction,
            gateway_payment_intent_id=payment_intent_id,
            verification_reference=session.get('id', ''),
        )
        return 'paid'

    if session_status == 'expired':
        expire_booking_batch(payment_transaction.booking_batch, reason='Stripe Checkout Session expired before completion.')
        return 'expired'

    if payment_status == 'unpaid' and payment_intent.get('status') in {'canceled', 'requires_payment_method'}:
        mark_payment_failed(payment_transaction, 'Stripe reports that the payment is not complete.')
        return 'failed'

    return 'processing'


def build_checkout_session_payload(request, payment_transaction):
    booking_batch = payment_transaction.booking_batch
    unit_amount = ticket_price_minor()
    checkout_expires_at = timezone.now() + stripe_checkout_duration()
    success_url = request.build_absolute_uri(
        f"/movies/payments/{booking_batch.booking_reference}/success/?session_id={{CHECKOUT_SESSION_ID}}"
    )
    cancel_url = request.build_absolute_uri(
        f"/movies/payments/{booking_batch.booking_reference}/cancel/"
    )

    payload = {
        'mode': 'payment',
        'success_url': success_url,
        'cancel_url': cancel_url,
        'client_reference_id': booking_batch.booking_reference,
        'customer_email': booking_batch.recipient_email,
        'metadata[booking_reference]': booking_batch.booking_reference,
        'metadata[payment_transaction_id]': str(payment_transaction.id),
        'metadata[theater_id]': str(booking_batch.theater_id),
        'line_items[0][price_data][currency]': booking_batch.currency,
        'line_items[0][price_data][product_data][name]': f'{booking_batch.movie.name} Tickets',
        'line_items[0][price_data][product_data][description]': f'{booking_batch.theater.name} | {booking_batch.total_tickets} seat(s)',
        'line_items[0][price_data][unit_amount]': str(unit_amount),
        'line_items[0][quantity]': str(booking_batch.total_tickets),
        'expires_at': str(int(checkout_expires_at.timestamp())),
    }
    return payload


def create_stripe_checkout_session(request, payment_transaction):
    payload = build_checkout_session_payload(request, payment_transaction)
    response = stripe_api_request(
        'POST',
        '/v1/checkout/sessions',
        data=payload,
        idempotency_key=payment_transaction.idempotency_key,
    )

    payment_transaction.gateway_checkout_session_id = response.get('id', '')
    payment_transaction.gateway_checkout_url = response.get('url', '')
    payment_transaction.status = PaymentTransaction.STATUS_PENDING
    payment_transaction.last_error = ''
    payment_transaction.save(
        update_fields=[
            'gateway_checkout_session_id',
            'gateway_checkout_url',
            'status',
            'last_error',
            'updated_at',
        ]
    )

    payment_transaction.booking_batch.status = BookingBatch.STATUS_PAYMENT_PROCESSING
    payment_transaction.booking_batch.save(update_fields=['status'])
    logger.info(
        "Stripe Checkout Session created",
        extra={
            'booking_reference': payment_transaction.booking_batch.booking_reference,
            'checkout_session_id': payment_transaction.gateway_checkout_session_id,
        }
    )
    return response


def expire_stripe_checkout_session(payment_transaction):
    session_id = payment_transaction.gateway_checkout_session_id
    if not session_id:
        return None
    return stripe_api_request('POST', f'/v1/checkout/sessions/{session_id}/expire')


def release_seat_holds(booking_batch):
    SeatHold.objects.filter(booking_batch=booking_batch).delete()


def mark_transaction_failed(payment_transaction, status, error_message):
    payment_transaction.status = status
    payment_transaction.last_error = error_message
    payment_transaction.save(update_fields=['status', 'last_error', 'updated_at'])


def expire_booking_batch(booking_batch, reason='Payment window expired.'):
    with transaction.atomic():
        locked_batch = BookingBatch.objects.select_for_update().get(id=booking_batch.id)
        if locked_batch.status == BookingBatch.STATUS_CONFIRMED:
            return locked_batch

        locked_batch.status = BookingBatch.STATUS_EXPIRED
        locked_batch.save(update_fields=['status'])

        if hasattr(locked_batch, 'payment_transaction'):
            payment_transaction = locked_batch.payment_transaction
            payment_transaction.status = PaymentTransaction.STATUS_EXPIRED
            payment_transaction.last_error = reason
            payment_transaction.save(update_fields=['status', 'last_error', 'updated_at'])

        release_seat_holds(locked_batch)
        invalidate_admin_dashboard_cache()
        return locked_batch


def cancel_booking_batch(booking_batch, reason='Payment was cancelled by the customer.'):
    with transaction.atomic():
        locked_batch = BookingBatch.objects.select_for_update().get(id=booking_batch.id)
        if locked_batch.status == BookingBatch.STATUS_CONFIRMED:
            return locked_batch

        locked_batch.status = BookingBatch.STATUS_CANCELLED
        locked_batch.save(update_fields=['status'])

        if hasattr(locked_batch, 'payment_transaction'):
            payment_transaction = locked_batch.payment_transaction
            payment_transaction.status = PaymentTransaction.STATUS_CANCELLED
            payment_transaction.last_error = reason
            payment_transaction.save(update_fields=['status', 'last_error', 'updated_at'])

        release_seat_holds(locked_batch)
        invalidate_admin_dashboard_cache()
        return locked_batch


def finalize_successful_payment(payment_transaction, gateway_payment_intent_id='', verification_reference=''):
    with transaction.atomic():
        locked_transaction = PaymentTransaction.objects.select_for_update().select_related(
            'booking_batch',
            'booking_batch__movie',
            'booking_batch__theater',
            'booking_batch__user',
        ).get(id=payment_transaction.id)
        booking_batch = locked_transaction.booking_batch

        if booking_batch.status == BookingBatch.STATUS_CONFIRMED:
            return booking_batch

        seat_holds = list(
            SeatHold.objects.select_for_update()
            .select_related('seat')
            .filter(booking_batch=booking_batch)
            .order_by('seat__seat_number')
        )

        if not seat_holds:
            raise PaymentGatewayError('Cannot finalize payment because the held seats are missing.')

        seats_to_book = []
        for seat_hold in seat_holds:
            seat = seat_hold.seat
            if seat.is_booked:
                raise PaymentGatewayError(f'Seat {seat.seat_number} is already booked.')
            seat.is_booked = True
            seats_to_book.append(seat)

        Seat.objects.bulk_update(seats_to_book, ['is_booked'])

        existing_booking_ids = set(Booking.objects.filter(booking_batch=booking_batch).values_list('seat_id', flat=True))
        bookings_to_create = [
            Booking(
                user=booking_batch.user,
                booking_batch=booking_batch,
                seat=seat,
                movie=booking_batch.movie,
                theater=booking_batch.theater,
            )
            for seat in seats_to_book
            if seat.id not in existing_booking_ids
        ]
        if bookings_to_create:
            Booking.objects.bulk_create(bookings_to_create)

        booking_batch.status = BookingBatch.STATUS_CONFIRMED
        booking_batch.finalized_at = timezone.now()
        booking_batch.save(update_fields=['status', 'finalized_at'])

        locked_transaction.status = PaymentTransaction.STATUS_PAID
        locked_transaction.gateway_payment_intent_id = gateway_payment_intent_id or locked_transaction.gateway_payment_intent_id
        locked_transaction.verification_reference = verification_reference
        locked_transaction.verified_at = timezone.now()
        locked_transaction.completed_at = timezone.now()
        locked_transaction.last_error = ''
        locked_transaction.save(
            update_fields=[
                'status',
                'gateway_payment_intent_id',
                'verification_reference',
                'verified_at',
                'completed_at',
                'last_error',
                'updated_at',
            ]
        )

        release_seat_holds(booking_batch)

        notification, _ = EmailNotification.objects.get_or_create(
            booking_batch=booking_batch,
            defaults={
                'recipient_email': booking_batch.recipient_email,
                'subject': f"Booking Confirmed: {booking_batch.movie.name} ({booking_batch.booking_reference})",
                'max_attempts': getattr(settings, 'BOOKING_EMAIL_MAX_RETRIES', 3),
            },
        )
        queue_booking_confirmation(notification)
        invalidate_admin_dashboard_cache()
        return booking_batch


def mark_payment_failed(payment_transaction, error_message):
    with transaction.atomic():
        locked_transaction = PaymentTransaction.objects.select_for_update().select_related('booking_batch').get(id=payment_transaction.id)
        if locked_transaction.booking_batch.status == BookingBatch.STATUS_CONFIRMED:
            return locked_transaction.booking_batch

        locked_transaction.status = PaymentTransaction.STATUS_FAILED
        locked_transaction.last_error = error_message
        locked_transaction.save(update_fields=['status', 'last_error', 'updated_at'])

        locked_transaction.booking_batch.status = BookingBatch.STATUS_PAYMENT_FAILED
        locked_transaction.booking_batch.save(update_fields=['status'])
        release_seat_holds(locked_transaction.booking_batch)
        invalidate_admin_dashboard_cache()
        return locked_transaction.booking_batch


def verify_stripe_webhook_signature(payload, signature_header):
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    tolerance = int(getattr(settings, 'STRIPE_WEBHOOK_TOLERANCE_SECONDS', 300))

    if not webhook_secret:
        raise PaymentGatewayError('Stripe webhook secret is not configured.')
    if not signature_header:
        raise PaymentGatewayError('Missing Stripe-Signature header.')

    components = {}
    for item in signature_header.split(','):
        if '=' not in item:
            continue
        key, value = item.split('=', 1)
        components.setdefault(key, []).append(value)

    timestamp = components.get('t', [None])[0]
    signatures = components.get('v1', [])
    if not timestamp or not signatures:
        raise PaymentGatewayError('Invalid Stripe signature header.')

    signed_payload = f'{timestamp}.{payload.decode("utf-8")}'.encode('utf-8')
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not any(hmac.compare_digest(expected_signature, candidate) for candidate in signatures):
        raise PaymentGatewayError('Stripe webhook signature verification failed.')

    if abs(timezone.now().timestamp() - int(timestamp)) > tolerance:
        raise PaymentGatewayError('Stripe webhook timestamp is outside the allowed tolerance window.')

    return json.loads(payload.decode('utf-8'))
