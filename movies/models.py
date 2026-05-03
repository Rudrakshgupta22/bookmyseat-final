import uuid
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Genre(models.Model):
    """Genre model for categorizing movies"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['name']),
        ]
        verbose_name_plural = "Genres"
    
    def __str__(self):
        return self.name


class Language(models.Model):
    """Language model for movie languages"""
    name = models.CharField(max_length=50, unique=True)  # e.g., English, Hindi, Tamil
    code = models.CharField(max_length=5, unique=True)  # e.g., en, hi, ta
    
    class Meta:
        indexes = [
            models.Index(fields=['code']),
        ]
        verbose_name_plural = "Languages"
    
    def __str__(self):
        return self.name


class Movie(models.Model):
    """Movie model with genre and language support"""
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to="movies/", blank=True, null=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()
    description = models.TextField(blank=True, null=True)
    
    # New fields for filtering
    genres = models.ManyToManyField(Genre, related_name='movies', blank=True)
    languages = models.ManyToManyField(Language, related_name='movies', blank=True)
    release_date = models.DateField(blank=True, null=True)
    duration = models.IntegerField(help_text="Duration in minutes", null=True, blank=True)
    trailer_url = models.URLField(blank=True, null=True)
    
    class Meta:
        # Database indexes for optimal query performance
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['rating']),
            models.Index(fields=['release_date']),
        ]
    
    def __str__(self):
        return self.name

    @staticmethod
    def extract_youtube_video_id(trailer_url):
        if not trailer_url:
            return None

        parsed_url = urlparse(trailer_url)
        hostname = (parsed_url.hostname or '').lower()

        if hostname in {'youtu.be', 'www.youtu.be'}:
            video_id = parsed_url.path.strip('/')
        elif hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
            if parsed_url.path == '/watch':
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
            elif parsed_url.path.startswith('/embed/'):
                video_id = parsed_url.path.split('/embed/', 1)[1].split('/', 1)[0]
            elif parsed_url.path.startswith('/shorts/'):
                video_id = parsed_url.path.split('/shorts/', 1)[1].split('/', 1)[0]
            else:
                video_id = None
        else:
            video_id = None

        if not video_id:
            return None

        normalized_video_id = video_id.strip()
        if len(normalized_video_id) != 11:
            return None

        allowed_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
        if not all(char in allowed_chars for char in normalized_video_id):
            return None

        return normalized_video_id

    @property
    def trailer_video_id(self):
        return self.extract_youtube_video_id(self.trailer_url)

    @property
    def has_valid_trailer(self):
        return bool(self.trailer_video_id)

    @property
    def safe_trailer_embed_url(self):
        video_id = self.trailer_video_id
        if not video_id:
            return ''
        return f'https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1'

    @property
    def safe_trailer_watch_url(self):
        video_id = self.trailer_video_id
        if not video_id:
            return ''
        return f'https://www.youtube.com/watch?v={video_id}'

    @property
    def safe_trailer_thumbnail_url(self):
        video_id = self.trailer_video_id
        if not video_id:
            return ''
        return f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'

    def clean(self):
        super().clean()
        if self.trailer_url and not self.extract_youtube_video_id(self.trailer_url):
            raise ValidationError({
                'trailer_url': 'Enter a valid YouTube watch, share, shorts, or embed URL.',
            })
    


class Theater(models.Model):
    name = models.CharField(max_length=255)
    movie = models.ForeignKey(Movie,on_delete=models.CASCADE,related_name='theaters')
    time= models.DateTimeField()

    def __str__(self):
        return f'{self.name} - {self.movie.name} at {self.time}'

class Seat(models.Model):
    theater = models.ForeignKey(Theater,on_delete=models.CASCADE,related_name='seats')
    seat_number = models.CharField(max_length=10)
    is_booked=models.BooleanField(default=False)

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'


class BookingBatch(models.Model):
    STATUS_PENDING_PAYMENT = 'pending_payment'
    STATUS_PAYMENT_PROCESSING = 'payment_processing'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_PAYMENT_FAILED = 'payment_failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_EXPIRED = 'expired'

    STATUS_CHOICES = [
        (STATUS_PENDING_PAYMENT, 'Pending Payment'),
        (STATUS_PAYMENT_PROCESSING, 'Payment Processing'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_PAYMENT_FAILED, 'Payment Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='booking_batches')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='booking_batches')
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='booking_batches')
    booking_reference = models.CharField(max_length=36, unique=True, editable=False)
    payment_id = models.CharField(max_length=36, unique=True, editable=False)
    recipient_email = models.EmailField()
    total_tickets = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING_PAYMENT)
    currency = models.CharField(max_length=8, default='inr')
    amount_total = models.PositiveIntegerField(default=0, help_text='Stored in the smallest currency unit.')
    hold_expires_at = models.DateTimeField(blank=True, null=True)
    finalized_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['booking_reference']),
            models.Index(fields=['payment_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status', 'finalized_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            self.booking_reference = f"BMS-{uuid.uuid4().hex[:12].upper()}"
        if not self.payment_id:
            self.payment_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)

    @property
    def seat_numbers(self):
        return [booking.seat.seat_number for booking in self.bookings.select_related('seat').order_by('seat__seat_number')]

    def __str__(self):
        return f'{self.booking_reference} - {self.movie.name}'


class Booking(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    booking_batch = models.ForeignKey(
        BookingBatch,
        on_delete=models.CASCADE,
        related_name='bookings',
        null=True,
        blank=True,
    )
    seat=models.OneToOneField(Seat,on_delete=models.CASCADE)
    movie=models.ForeignKey(Movie,on_delete=models.CASCADE)
    theater=models.ForeignKey(Theater,on_delete=models.CASCADE)
    booked_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-booked_at']
        indexes = [
            models.Index(fields=['booked_at']),
            models.Index(fields=['movie', 'booked_at']),
            models.Index(fields=['theater', 'booked_at']),
        ]

    def __str__(self):
        return f'Booking by{self.user.username} for {self.seat.seat_number} at {self.theater.name}'


class SeatHold(models.Model):
    booking_batch = models.ForeignKey(BookingBatch, on_delete=models.CASCADE, related_name='seat_holds')
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE, related_name='active_hold')
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seat__seat_number']
        indexes = [
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f'Hold for {self.seat.seat_number} until {self.expires_at}'


class PaymentTransaction(models.Model):
    PROVIDER_STRIPE = 'stripe'

    PROVIDER_CHOICES = [
        (PROVIDER_STRIPE, 'Stripe'),
    ]

    STATUS_INITIATED = 'initiated'
    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_EXPIRED = 'expired'

    STATUS_CHOICES = [
        (STATUS_INITIATED, 'Initiated'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    booking_batch = models.OneToOneField(BookingBatch, on_delete=models.CASCADE, related_name='payment_transaction')
    provider = models.CharField(max_length=16, choices=PROVIDER_CHOICES, default=PROVIDER_STRIPE)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_INITIATED)
    amount = models.PositiveIntegerField(help_text='Stored in the smallest currency unit.')
    currency = models.CharField(max_length=8, default='inr')
    idempotency_key = models.CharField(max_length=64, unique=True)
    gateway_checkout_session_id = models.CharField(max_length=1000, blank=True, null=True, unique=True)
    gateway_payment_intent_id = models.CharField(max_length=1000, blank=True, null=True, unique=True)
    gateway_checkout_url = models.URLField(blank=True, null=True)
    verification_reference = models.CharField(max_length=1000, blank=True)
    last_error = models.TextField(blank=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f'{self.booking_batch.booking_reference} - {self.status}'


class PaymentWebhookEvent(models.Model):
    STATUS_RECEIVED = 'received'
    STATUS_PROCESSED = 'processed'
    STATUS_DUPLICATE = 'duplicate'
    STATUS_REJECTED = 'rejected'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_RECEIVED, 'Received'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_DUPLICATE, 'Duplicate'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_FAILED, 'Failed'),
    ]

    provider = models.CharField(max_length=16, default=PaymentTransaction.PROVIDER_STRIPE)
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=255)
    signature_valid = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_RECEIVED)
    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.SET_NULL,
        related_name='webhook_events',
        null=True,
        blank=True,
    )
    payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', 'event_type']),
        ]

    def __str__(self):
        return f'{self.provider}:{self.event_id}'


class EmailNotification(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    ]

    booking_batch = models.OneToOneField(
        BookingBatch,
        on_delete=models.CASCADE,
        related_name='email_notification'
    )
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    last_attempt_at = models.DateTimeField(blank=True, null=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_attempt_at', 'created_at']
        indexes = [
            models.Index(fields=['status', 'next_attempt_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.recipient_email} - {self.status}'
