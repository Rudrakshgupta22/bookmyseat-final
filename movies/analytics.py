from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce, ExtractHour
from django.utils import timezone

from .models import Booking, BookingBatch, Theater


ANALYTICS_CACHE_KEY = 'movies_admin_dashboard_analytics_v1'


def get_admin_dashboard_analytics(force_refresh=False):
    if not force_refresh:
        cached_value = cache.get(ANALYTICS_CACHE_KEY)
        if cached_value is not None:
            return cached_value

    now = timezone.now()
    day_start = now - timezone.timedelta(days=1)
    week_start = now - timezone.timedelta(days=7)
    month_start = now - timezone.timedelta(days=30)

    confirmed_batches = BookingBatch.objects.filter(status=BookingBatch.STATUS_CONFIRMED)
    revenue_aggregate = confirmed_batches.aggregate(
        daily=Coalesce(Sum('amount_total', filter=Q(finalized_at__gte=day_start)), 0),
        weekly=Coalesce(Sum('amount_total', filter=Q(finalized_at__gte=week_start)), 0),
        monthly=Coalesce(Sum('amount_total', filter=Q(finalized_at__gte=month_start)), 0),
        lifetime=Coalesce(Sum('amount_total'), 0),
    )

    popular_movies = list(
        Booking.objects.values('movie__name')
        .annotate(total_bookings=Count('id'))
        .order_by('-total_bookings', 'movie__name')[:5]
    )

    busiest_theaters = list(
        Theater.objects.annotate(
            total_seats=Count('seats', distinct=True),
            booked_seats=Count('seats', filter=Q(seats__is_booked=True), distinct=True),
        )
        .annotate(
            occupancy_rate=Case(
                When(total_seats=0, then=Value(Decimal('0.00'))),
                default=ExpressionWrapper(
                    F('booked_seats') * Decimal('100.0') / F('total_seats'),
                    output_field=DecimalField(max_digits=5, decimal_places=2),
                ),
                output_field=DecimalField(max_digits=5, decimal_places=2),
            )
        )
        .values('name', 'movie__name', 'booked_seats', 'total_seats', 'occupancy_rate')
        .order_by('-occupancy_rate', '-booked_seats', 'name')[:5]
    )

    peak_booking_hours = list(
        Booking.objects.annotate(hour=ExtractHour('booked_at'))
        .values('hour')
        .annotate(total_bookings=Count('id'))
        .order_by('-total_bookings', 'hour')[:5]
    )

    batch_attempts = BookingBatch.objects.aggregate(
        total_attempts=Count('id'),
        cancelled_attempts=Count(
            'id',
            filter=Q(
                status__in=[
                    BookingBatch.STATUS_CANCELLED,
                    BookingBatch.STATUS_PAYMENT_FAILED,
                    BookingBatch.STATUS_EXPIRED,
                ]
            ),
        ),
    )
    total_attempts = batch_attempts['total_attempts'] or 0
    cancelled_attempts = batch_attempts['cancelled_attempts'] or 0
    cancellation_rate = round((cancelled_attempts / total_attempts) * 100, 2) if total_attempts else 0

    analytics = {
        'revenue': {
            'daily': revenue_aggregate['daily'],
            'weekly': revenue_aggregate['weekly'],
            'monthly': revenue_aggregate['monthly'],
            'lifetime': revenue_aggregate['lifetime'],
        },
        'popular_movies': popular_movies,
        'busiest_theaters': busiest_theaters,
        'peak_booking_hours': peak_booking_hours,
        'cancellation': {
            'total_attempts': total_attempts,
            'cancelled_attempts': cancelled_attempts,
            'rate_percent': cancellation_rate,
        },
        'generated_at': now,
        'refresh_interval_seconds': getattr(settings, 'ANALYTICS_REFRESH_INTERVAL_SECONDS', 30),
        'cache_backend': getattr(settings, 'ANALYTICS_CACHE_BACKEND', 'locmem'),
    }

    cache.set(
        ANALYTICS_CACHE_KEY,
        analytics,
        timeout=getattr(settings, 'ANALYTICS_CACHE_TIMEOUT_SECONDS', 60),
    )
    return analytics


def invalidate_admin_dashboard_cache():
    cache.delete(ANALYTICS_CACHE_KEY)
