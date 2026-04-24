from django.contrib import admin
from .models import (
    Booking,
    BookingBatch,
    EmailNotification,
    Genre,
    Language,
    Movie,
    PaymentTransaction,
    PaymentWebhookEvent,
    Seat,
    SeatHold,
    Theater,
)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ['name', 'code']
    search_fields = ['name', 'code']
    ordering = ['name']


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['name', 'rating', 'release_date', 'trailer_url']
    search_fields = ['name', 'description', 'trailer_url']
    filter_horizontal = ['genres', 'languages']  # Better UI for ManyToMany
    list_filter = ['rating', 'release_date', 'genres', 'languages']
    ordering = ['-release_date', '-rating']
    
    # Show genres and languages in inline
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'image', 'rating', 'cast', 'description')
        }),
        ('Content Details', {
            'fields': ('release_date', 'duration', 'trailer_url', 'genres', 'languages')
        }),
    )


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name', 'movie', 'time']
    search_fields = ['name', 'movie__name']
    list_filter = ['time', 'movie']
    ordering = ['-time']


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['theater', 'seat_number', 'is_booked']
    search_fields = ['theater__name', 'seat_number']
    list_filter = ['is_booked', 'theater']
    ordering = ['theater', 'seat_number']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user', 'seat', 'movie', 'theater', 'booking_batch', 'booked_at']
    search_fields = ['user__username', 'movie__name', 'theater__name', 'booking_batch__booking_reference']
    list_filter = ['booked_at', 'movie', 'theater']
    readonly_fields = ['booked_at']
    ordering = ['-booked_at']


@admin.register(BookingBatch)
class BookingBatchAdmin(admin.ModelAdmin):
    list_display = ['booking_reference', 'payment_id', 'status', 'user', 'movie', 'theater', 'total_tickets', 'created_at']
    search_fields = ['booking_reference', 'payment_id', 'user__username', 'movie__name', 'theater__name']
    list_filter = ['status', 'created_at', 'movie', 'theater']
    readonly_fields = ['booking_reference', 'payment_id', 'created_at', 'finalized_at']
    ordering = ['-created_at']


@admin.register(EmailNotification)
class EmailNotificationAdmin(admin.ModelAdmin):
    list_display = ['booking_batch', 'recipient_email', 'status', 'attempts', 'max_attempts', 'next_attempt_at', 'sent_at']
    search_fields = ['booking_batch__booking_reference', 'recipient_email', 'booking_batch__payment_id']
    list_filter = ['status', 'created_at', 'sent_at']
    readonly_fields = ['created_at', 'updated_at', 'last_attempt_at', 'sent_at', 'last_error']
    ordering = ['status', 'next_attempt_at']


@admin.register(SeatHold)
class SeatHoldAdmin(admin.ModelAdmin):
    list_display = ['booking_batch', 'seat', 'expires_at', 'created_at']
    search_fields = ['booking_batch__booking_reference', 'seat__seat_number', 'booking_batch__user__username']
    list_filter = ['expires_at', 'created_at']
    ordering = ['expires_at']


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ['booking_batch', 'provider', 'status', 'amount', 'currency', 'gateway_checkout_session_id', 'created_at']
    search_fields = ['booking_batch__booking_reference', 'idempotency_key', 'gateway_checkout_session_id', 'gateway_payment_intent_id']
    list_filter = ['provider', 'status', 'created_at']
    readonly_fields = ['idempotency_key', 'verified_at', 'completed_at', 'created_at', 'updated_at', 'last_error']
    ordering = ['-created_at']


@admin.register(PaymentWebhookEvent)
class PaymentWebhookEventAdmin(admin.ModelAdmin):
    list_display = ['event_id', 'provider', 'event_type', 'signature_valid', 'status', 'payment_transaction', 'created_at']
    search_fields = ['event_id', 'event_type', 'payment_transaction__booking_batch__booking_reference']
    list_filter = ['provider', 'signature_valid', 'status', 'event_type']
    readonly_fields = ['payload', 'error_message', 'processed_at', 'created_at']
    ordering = ['-created_at']
