import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .analytics import ANALYTICS_CACHE_KEY, get_admin_dashboard_analytics, invalidate_admin_dashboard_cache
from .email_queue import process_next_due_email
from .models import (
    Booking,
    BookingBatch,
    EmailNotification,
    Movie,
    PaymentTransaction,
    PaymentWebhookEvent,
    Seat,
    SeatHold,
    Theater,
)
from .payments import build_checkout_session_payload, cleanup_expired_payment_holds


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_QUEUE_AUTOSTART=False,
    SEAT_RESERVATION_AUTOSTART=False,
    PAYMENT_TICKET_PRICE_MINOR=25000,
    PAYMENT_HOLD_DURATION_MINUTES=2,
    SEAT_RESERVATION_TIMEOUT_MINUTES=2,
    STRIPE_WEBHOOK_SECRET='whsec_test_secret',
)
class PaymentLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='demo',
            email='demo@example.com',
            password='secret123',
        )
        self.second_user = User.objects.create_user(
            username='other',
            email='other@example.com',
            password='secret123',
        )
        self.movie = Movie.objects.create(
            name='Interstellar',
            image='movies/test.jpg',
            rating='8.8',
            cast='Matthew McConaughey',
            description='Space travel adventure',
            duration=169,
        )
        self.theater = Theater.objects.create(
            name='PVR Cinemas',
            movie=self.movie,
            time=timezone.now() + timedelta(days=1),
        )
        self.seat_1 = Seat.objects.create(theater=self.theater, seat_number='A1')
        self.seat_2 = Seat.objects.create(theater=self.theater, seat_number='A2')

    def sign_stripe_payload(self, payload):
        timestamp = str(int(timezone.now().timestamp()))
        expected = hmac.new(
            b'whsec_test_secret',
            f'{timestamp}.{payload.decode("utf-8")}'.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        return f't={timestamp},v1={expected}'

    @patch('movies.views.create_stripe_checkout_session')
    def test_booking_redirects_to_gateway_and_creates_pending_hold(self, mocked_create_checkout_session):
        mocked_create_checkout_session.return_value = {
            'id': 'cs_test_123',
            'url': 'https://checkout.stripe.test/session/cs_test_123',
        }
        self.client.login(username='demo', password='secret123')

        response = self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            {'seats': [str(self.seat_1.id), str(self.seat_2.id)]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://checkout.stripe.test/session/cs_test_123')
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(BookingBatch.objects.count(), 1)
        self.assertEqual(SeatHold.objects.count(), 2)
        self.assertEqual(PaymentTransaction.objects.count(), 1)

        batch = BookingBatch.objects.get()
        transaction = PaymentTransaction.objects.get()

        self.assertEqual(batch.status, BookingBatch.STATUS_PENDING_PAYMENT)
        self.assertEqual(batch.amount_total, 50000)
        self.assertEqual(transaction.status, PaymentTransaction.STATUS_INITIATED)
        self.assertLessEqual(batch.hold_expires_at, timezone.now() + timedelta(minutes=2, seconds=5))

    @patch('movies.views.create_stripe_checkout_session')
    def test_active_hold_blocks_second_checkout_attempt(self, mocked_create_checkout_session):
        mocked_create_checkout_session.return_value = {
            'id': 'cs_test_123',
            'url': 'https://checkout.stripe.test/session/cs_test_123',
        }

        self.client.login(username='demo', password='secret123')
        self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            {'seats': [str(self.seat_1.id)]},
        )

        self.client.logout()
        self.client.login(username='other', password='secret123')
        response = self.client.post(
            reverse('book_seats', args=[self.theater.id]),
            {'seats': [str(self.seat_1.id)]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'temporarily reserved')
        self.assertEqual(SeatHold.objects.count(), 1)

    def test_completed_webhook_is_idempotent_and_confirms_booking_once(self):
        batch = BookingBatch.objects.create(
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            recipient_email=self.user.email,
            total_tickets=2,
            currency='inr',
            amount_total=50000,
            status=BookingBatch.STATUS_PAYMENT_PROCESSING,
            hold_expires_at=timezone.now() + timedelta(minutes=10),
        )
        SeatHold.objects.create(booking_batch=batch, seat=self.seat_1, expires_at=batch.hold_expires_at)
        SeatHold.objects.create(booking_batch=batch, seat=self.seat_2, expires_at=batch.hold_expires_at)
        transaction = PaymentTransaction.objects.create(
            booking_batch=batch,
            provider=PaymentTransaction.PROVIDER_STRIPE,
            status=PaymentTransaction.STATUS_PENDING,
            amount=50000,
            currency='inr',
            idempotency_key='idem_123',
            gateway_checkout_session_id='cs_test_123',
        )

        payload = json.dumps({
            'id': 'evt_test_123',
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_123',
                    'client_reference_id': batch.booking_reference,
                    'payment_intent': 'pi_test_123',
                    'metadata': {
                        'payment_transaction_id': str(transaction.id),
                        'booking_reference': batch.booking_reference,
                    },
                }
            }
        }).encode('utf-8')
        signature = self.sign_stripe_payload(payload)

        first_response = self.client.post(
            reverse('stripe_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE=signature,
        )
        second_response = self.client.post(
            reverse('stripe_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE=signature,
        )

        batch.refresh_from_db()
        transaction.refresh_from_db()
        self.seat_1.refresh_from_db()
        self.seat_2.refresh_from_db()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(batch.status, BookingBatch.STATUS_CONFIRMED)
        self.assertEqual(transaction.status, PaymentTransaction.STATUS_PAID)
        self.assertTrue(self.seat_1.is_booked)
        self.assertTrue(self.seat_2.is_booked)
        self.assertEqual(Booking.objects.filter(booking_batch=batch).count(), 2)
        self.assertEqual(EmailNotification.objects.filter(booking_batch=batch).count(), 1)
        self.assertEqual(PaymentWebhookEvent.objects.filter(event_id='evt_test_123').count(), 1)

    def test_invalid_webhook_signature_is_rejected(self):
        payload = json.dumps({
            'id': 'evt_invalid',
            'type': 'checkout.session.completed',
            'data': {'object': {}},
        }).encode('utf-8')

        response = self.client.post(
            reverse('stripe_webhook'),
            data=payload,
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=invalid',
        )

        self.assertEqual(response.status_code, 400)

    def test_expired_holds_are_released(self):
        batch = BookingBatch.objects.create(
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            recipient_email=self.user.email,
            total_tickets=1,
            currency='inr',
            amount_total=25000,
            status=BookingBatch.STATUS_PAYMENT_PROCESSING,
            hold_expires_at=timezone.now() - timedelta(minutes=1),
        )
        SeatHold.objects.create(booking_batch=batch, seat=self.seat_1, expires_at=timezone.now() - timedelta(minutes=1))
        transaction = PaymentTransaction.objects.create(
            booking_batch=batch,
            provider=PaymentTransaction.PROVIDER_STRIPE,
            status=PaymentTransaction.STATUS_PENDING,
            amount=25000,
            currency='inr',
            idempotency_key='idem_timeout',
        )

        cleanup_expired_payment_holds()

        batch.refresh_from_db()
        transaction.refresh_from_db()
        self.assertEqual(batch.status, BookingBatch.STATUS_EXPIRED)
        self.assertEqual(transaction.status, PaymentTransaction.STATUS_EXPIRED)
        self.assertEqual(SeatHold.objects.filter(booking_batch=batch).count(), 0)

    @patch('movies.views.create_stripe_checkout_session')
    def test_seat_selection_page_shows_two_minute_hold_window(self, mocked_create_checkout_session):
        mocked_create_checkout_session.return_value = {
            'id': 'cs_test_123',
            'url': 'https://checkout.stripe.test/session/cs_test_123',
        }
        self.client.login(username='demo', password='secret123')

        response = self.client.get(reverse('book_seats', args=[self.theater.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tickets are reserved for 2 minutes')

    def test_stripe_checkout_expiry_stays_valid_while_local_hold_is_two_minutes(self):
        batch = BookingBatch.objects.create(
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            recipient_email=self.user.email,
            total_tickets=1,
            currency='inr',
            amount_total=25000,
            status=BookingBatch.STATUS_PENDING_PAYMENT,
            hold_expires_at=timezone.now() + timedelta(minutes=2),
        )
        transaction = PaymentTransaction.objects.create(
            booking_batch=batch,
            provider=PaymentTransaction.PROVIDER_STRIPE,
            status=PaymentTransaction.STATUS_INITIATED,
            amount=25000,
            currency='inr',
            idempotency_key='idem_payload_test',
        )

        class DummyRequest:
            def build_absolute_uri(self, path):
                return f'http://testserver{path}'

        payload = build_checkout_session_payload(DummyRequest(), transaction)
        checkout_expires_at = int(payload['expires_at'])
        minimum_expected = int((timezone.now() + timedelta(minutes=30)).timestamp()) - 5

        self.assertGreaterEqual(checkout_expires_at, minimum_expected)

    def test_process_next_due_email_sends_confirmation(self):
        batch = BookingBatch.objects.create(
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            recipient_email=self.user.email,
            total_tickets=1,
            currency='inr',
            amount_total=25000,
            status=BookingBatch.STATUS_CONFIRMED,
        )
        Booking.objects.create(
            user=self.user,
            booking_batch=batch,
            seat=self.seat_1,
            movie=self.movie,
            theater=self.theater,
        )
        notification = EmailNotification.objects.create(
            booking_batch=batch,
            recipient_email=self.user.email,
            subject='Booking confirmed',
        )

        processed = process_next_due_email()

        notification.refresh_from_db()
        self.assertTrue(processed)
        self.assertEqual(notification.status, EmailNotification.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(batch.payment_id, mail.outbox[0].body)

    def test_failed_email_is_requeued_with_error_details(self):
        batch = BookingBatch.objects.create(
            user=self.user,
            movie=self.movie,
            theater=self.theater,
            recipient_email=self.user.email,
            total_tickets=1,
            currency='inr',
            amount_total=25000,
            status=BookingBatch.STATUS_CONFIRMED,
        )
        Booking.objects.create(
            user=self.user,
            booking_batch=batch,
            seat=self.seat_1,
            movie=self.movie,
            theater=self.theater,
        )
        notification = EmailNotification.objects.create(
            booking_batch=batch,
            recipient_email=self.user.email,
            subject='Booking confirmed',
            max_attempts=3,
        )

        with patch('movies.email_queue.EmailMultiAlternatives.send', side_effect=RuntimeError('SMTP unavailable')):
            processed = process_next_due_email()

        notification.refresh_from_db()
        self.assertTrue(processed)
        self.assertEqual(notification.status, EmailNotification.STATUS_PENDING)
        self.assertEqual(notification.attempts, 1)
        self.assertIn('SMTP unavailable', notification.last_error)
        self.assertGreater(notification.next_attempt_at, timezone.now())


class MovieTrailerSecurityTests(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(
            name='Secure Trailer Movie',
            image='movies/test.jpg',
            rating='8.2',
            cast='Sample Cast',
            description='Movie with trailer support',
            duration=120,
        )

    def test_accepts_supported_youtube_watch_url(self):
        self.movie.trailer_url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        self.movie.full_clean()

        self.assertEqual(self.movie.trailer_video_id, 'dQw4w9WgXcQ')
        self.assertIn('youtube-nocookie.com/embed/dQw4w9WgXcQ', self.movie.safe_trailer_embed_url)
        self.assertEqual(self.movie.safe_trailer_watch_url, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    def test_rejects_non_youtube_or_script_payload_url(self):
        self.movie.trailer_url = 'javascript:alert(1)'
        with self.assertRaises(ValidationError):
            self.movie.full_clean()

        self.movie.trailer_url = 'https://example.com/watch?v=dQw4w9WgXcQ'
        with self.assertRaises(ValidationError):
            self.movie.full_clean()

    def test_movie_detail_shows_lazy_loaded_trailer_shell(self):
        self.movie.trailer_url = 'https://youtu.be/dQw4w9WgXcQ'
        self.movie.save()

        response = self.client.get(reverse('movie_detail', args=[self.movie.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-video-id="dQw4w9WgXcQ"', html=False)
        self.assertContains(response, 'loading="lazy"', count=1, html=False)
        self.assertContains(response, 'youtube-nocookie.com/embed/', html=False)
        self.assertNotContains(response, 'javascript:alert(1)', html=False)

    def test_movie_detail_shows_fallback_when_trailer_missing(self):
        response = self.client.get(reverse('movie_detail', args=[self.movie.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trailer unavailable right now.')


@override_settings(
    EMAIL_QUEUE_AUTOSTART=False,
    SEAT_RESERVATION_AUTOSTART=False,
    ANALYTICS_CACHE_TIMEOUT_SECONDS=60,
)
class AdminAnalyticsDashboardTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='adminpass123',
            is_staff=True,
            is_superuser=True,
        )
        self.normal_user = User.objects.create_user(
            username='normaluser',
            email='normal@example.com',
            password='normalpass123',
        )
        self.movie = Movie.objects.create(
            name='Analytics Movie',
            image='movies/test.jpg',
            rating='9.0',
            cast='Cast',
            description='Analytics',
            duration=110,
        )
        self.theater = Theater.objects.create(
            name='Analytics Theater',
            movie=self.movie,
            time=timezone.now() + timedelta(days=1),
        )
        self.seat = Seat.objects.create(theater=self.theater, seat_number='A1', is_booked=True)
        self.batch = BookingBatch.objects.create(
            user=self.admin_user,
            movie=self.movie,
            theater=self.theater,
            recipient_email=self.admin_user.email,
            total_tickets=1,
            currency='inr',
            amount_total=25000,
            status=BookingBatch.STATUS_CONFIRMED,
            finalized_at=timezone.now(),
        )
        Booking.objects.create(
            user=self.admin_user,
            booking_batch=self.batch,
            seat=self.seat,
            movie=self.movie,
            theater=self.theater,
        )

    def tearDown(self):
        invalidate_admin_dashboard_cache()

    def test_admin_dashboard_requires_staff_access(self):
        response = self.client.get(reverse('admin_analytics_dashboard'))
        self.assertEqual(response.status_code, 302)

        self.client.login(username='normaluser', password='normalpass123')
        response = self.client.get(reverse('admin_analytics_dashboard'))
        self.assertEqual(response.status_code, 302)

        self.client.logout()
        self.client.login(username='adminuser', password='adminpass123')
        response = self.client.get(reverse('admin_analytics_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Analytics Dashboard')

    def test_dashboard_analytics_uses_aggregation_and_cache(self):
        invalidate_admin_dashboard_cache()
        cache.delete(ANALYTICS_CACHE_KEY)

        analytics = get_admin_dashboard_analytics()

        self.assertEqual(analytics['revenue']['lifetime'], 25000)
        self.assertEqual(analytics['popular_movies'][0]['movie__name'], 'Analytics Movie')
        self.assertEqual(analytics['popular_movies'][0]['total_bookings'], 1)
        self.assertEqual(analytics['cancellation']['total_attempts'], 1)
        self.assertIsNotNone(cache.get(ANALYTICS_CACHE_KEY))
