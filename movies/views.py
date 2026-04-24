from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Booking,
    BookingBatch,
    Genre,
    Language,
    Movie,
    PaymentTransaction,
    PaymentWebhookEvent,
    Seat,
    Theater,
)
from django.db import IntegrityError
from .query_optimizer import MovieQueryOptimizer, PaginationHelper, build_filter_url_params
from .payments import (
    PaymentGatewayError,
    cancel_booking_batch,
    cleanup_expired_payment_holds,
    create_pending_booking_batch,
    create_stripe_checkout_session,
    expire_booking_batch,
    expire_stripe_checkout_session,
    finalize_successful_payment,
    hold_duration,
    mark_payment_failed,
    validate_and_lock_available_seats,
    verify_payment_transaction_with_stripe,
    verify_stripe_webhook_signature,
)


def movie_list(request):
    """
    Optimized movie listing with advanced filtering, pagination, and sorting
    
    Features:
    - Multi-select genre filtering
    - Multi-select language filtering
    - Full-text search on movie name and description
    - Pagination with 12 movies per page
    - Dynamic sorting (name, rating, release_date)
    - Live filter counts showing available options
    
    Query optimization:
    - Uses prefetch_related() to avoid N+1 queries on genres/languages
    - Uses distinct() with ManyToMany filters to avoid duplicate rows
    - Database indexes on name, rating, release_date for fast sorting/searching
    - Counts are calculated efficiently using separate aggregation queries
    """
    # Get filter parameters from request
    search_query = request.GET.get('search', '').strip()
    selected_genres = request.GET.getlist('genres')
    selected_languages = request.GET.getlist('languages')
    sort_by = request.GET.get('sort', 'name')
    page_number = request.GET.get('page', 1)
    
    # Convert string IDs to integers for filtering
    selected_genres = [int(g) for g in selected_genres if g.isdigit()]
    selected_languages = [int(l) for l in selected_languages if l.isdigit()]
    
    # Get optimized queryset with filters applied
    movies_queryset = MovieQueryOptimizer.get_optimized_queryset(
        search_query=search_query,
        selected_genres=selected_genres,
        selected_languages=selected_languages,
        sort_by=sort_by
    )
    
    # Get dynamic filter counts
    filter_counts = MovieQueryOptimizer.get_filter_counts(
        search_query=search_query,
        selected_genres=selected_genres,
        selected_languages=selected_languages
    )
    
    # Paginate results
    pagination_data = PaginationHelper.paginate_queryset(
        movies_queryset,
        page_number=page_number,
        per_page=12
    )
    
    # Get all genres and languages for filter UI
    all_genres = Genre.objects.all()
    all_languages = Language.objects.all()
    
    context = {
        'movies': pagination_data['movies'],
        'page_obj': pagination_data['page_obj'],
        'paginator': pagination_data['paginator'],
        'total_count': pagination_data['total_count'],
        'search_query': search_query,
        'selected_genres': selected_genres,
        'selected_languages': selected_languages,
        'sort_by': sort_by,
        'all_genres': all_genres,
        'all_languages': all_languages,
        'filter_counts': filter_counts,
        'build_filter_url': build_filter_url_params
    }
    
    return render(request, 'movies/movie_list.html', context)



def theater_list(request, movie_id):
    """
    Display theaters showing a specific movie
    
    Optimization:
    - Uses select_related() for efficient movie fetching
    - Only fetches theaters with pending/future dates
    """
    movie = get_object_or_404(Movie.objects.prefetch_related('genres', 'languages'), id=movie_id)
    theaters = Theater.objects.filter(movie=movie).select_related('movie').order_by('time')
    
    return render(request, 'movies/theater_list.html', {
        'movie': movie,
        'theaters': theaters,
        'total_theaters': theaters.count()
    })


def movie_detail(request, movie_id):
    cleanup_expired_payment_holds()
    movie = get_object_or_404(
        Movie.objects.prefetch_related('genres', 'languages'),
        id=movie_id
    )
    theaters = Theater.objects.filter(movie=movie).select_related('movie').order_by('time')

    return render(request, 'movies/movie_detail.html', {
        'movie': movie,
        'theaters': theaters,
        'total_theaters': theaters.count(),
    })


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    """
    Book seats for a specific theater showing
    
    Optimization:
    - Uses select_related() for efficient theater/movie fetching
    - Uses select_related() for efficient seat status checking
    - Validates seat availability atomically
    """
    cleanup_expired_payment_holds()

    theater = get_object_or_404(
        Theater.objects.select_related('movie'),
        id=theater_id
    )
    
    # Optimized seat fetching with select_related
    seats = Seat.objects.filter(theater=theater).select_related('theater')
    
    if request.method == 'POST':
        selected_seats = [seat_id for seat_id in request.POST.getlist('seats') if seat_id.isdigit()]
        
        if not selected_seats:
            return render(
                request,
                "movies/seat_selection.html",
                {
                    'theater': theater,
                    'seats': seats,
                    'error': "No seat selected"
                }
            )

        if not request.user.email:
            return render(
                request,
                "movies/seat_selection.html",
                {
                    'theater': theater,
                    'seats': seats,
                    'error': "Please add an email address to your profile before making a payment."
                }
            )

        try:
            with transaction.atomic():
                locked_seats, validation_error = validate_and_lock_available_seats(theater, selected_seats)
                if validation_error:
                    return render(
                        request,
                        'movies/seat_selection.html',
                        {
                            'theater': theater,
                            'seats': seats,
                            'error': validation_error
                        }
                    )

                booking_batch, payment_transaction = create_pending_booking_batch(request.user, theater, locked_seats)
        except IntegrityError:
            error_message = "Some seats were booked by another user. Please refresh and try again."
            return render(
                request,
                'movies/seat_selection.html',
                {
                    'theater': theater,
                    'seats': seats,
                    'error': error_message
                }
            )

        try:
            checkout_session = create_stripe_checkout_session(request, payment_transaction)
        except PaymentGatewayError as exc:
            mark_payment_failed(payment_transaction, str(exc))
            error_message = 'Unable to start the payment session right now. No seats were booked.'
            if settings.DEBUG:
                error_message = f'{error_message} Details: {exc}'
            return render(
                request,
                'movies/seat_selection.html',
                {
                    'theater': theater,
                    'seats': Seat.objects.filter(theater=theater).select_related('theater'),
                    'error': error_message,
                }
            )

        return redirect(checkout_session['url'])
    
    return render(
        request,
        'movies/seat_selection.html',
        {
            'theater': theater,
            'seats': seats,
            'total_seats': seats.count(),
            'ticket_price_minor': getattr(settings, 'PAYMENT_TICKET_PRICE_MINOR', 25000),
            'ticket_price_display': getattr(settings, 'PAYMENT_TICKET_PRICE_MINOR', 25000) / 100,
            'hold_minutes': max(1, int(hold_duration().total_seconds() // 60)),
        }
    )


@login_required(login_url='/login/')
def payment_success(request, booking_reference):
    cleanup_expired_payment_holds()
    booking_batch = get_object_or_404(
        BookingBatch.objects.select_related('payment_transaction', 'movie', 'theater'),
        booking_reference=booking_reference,
        user=request.user,
    )
    verification_error = ''
    payment_transaction = getattr(booking_batch, 'payment_transaction', None)

    if payment_transaction and booking_batch.status not in [
        BookingBatch.STATUS_CONFIRMED,
        BookingBatch.STATUS_PAYMENT_FAILED,
        BookingBatch.STATUS_CANCELLED,
        BookingBatch.STATUS_EXPIRED,
    ]:
        session_id = request.GET.get('session_id', '').strip()
        if session_id and not payment_transaction.gateway_checkout_session_id:
            payment_transaction.gateway_checkout_session_id = session_id
            payment_transaction.save(update_fields=['gateway_checkout_session_id', 'updated_at'])
        elif not session_id:
            session_id = payment_transaction.gateway_checkout_session_id or ''

        if session_id:
            try:
                verify_payment_transaction_with_stripe(payment_transaction)
                booking_batch.refresh_from_db()
            except PaymentGatewayError as exc:
                verification_error = str(exc)
                booking_batch.refresh_from_db()

    status_title = 'Payment verification in progress'
    status_copy = 'We are verifying the payment server-side before confirming your tickets.'
    if booking_batch.status == BookingBatch.STATUS_CONFIRMED:
        status_title = 'Payment confirmed'
        status_copy = 'Your payment has been verified and your tickets are booked.'
    elif booking_batch.status in [BookingBatch.STATUS_PAYMENT_FAILED, BookingBatch.STATUS_CANCELLED, BookingBatch.STATUS_EXPIRED]:
        status_title = 'Payment not completed'
        status_copy = 'This payment attempt did not complete successfully. You can start a fresh booking flow.'

    return render(request, 'movies/payment_status.html', {
        'booking_batch': booking_batch,
        'status_title': status_title,
        'status_copy': status_copy,
        'verification_error': verification_error if settings.DEBUG else '',
    })


@login_required(login_url='/login/')
def payment_cancel(request, booking_reference):
    cleanup_expired_payment_holds()
    booking_batch = get_object_or_404(
        BookingBatch.objects.select_related('payment_transaction'),
        booking_reference=booking_reference,
        user=request.user,
    )

    payment_transaction = getattr(booking_batch, 'payment_transaction', None)
    if payment_transaction and payment_transaction.status not in [PaymentTransaction.STATUS_PAID, PaymentTransaction.STATUS_EXPIRED]:
        try:
            expire_stripe_checkout_session(payment_transaction)
        except PaymentGatewayError:
            pass
        booking_batch = cancel_booking_batch(booking_batch)

    return render(request, 'movies/payment_status.html', {
        'booking_batch': booking_batch,
        'status_title': 'Payment cancelled',
        'status_copy': 'The payment session was cancelled and the seat hold has been released.',
    })


@csrf_exempt
def stripe_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)

    payload = request.body
    signature_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = verify_stripe_webhook_signature(payload, signature_header)
    except PaymentGatewayError as exc:
        PaymentWebhookEvent.objects.create(
            provider=PaymentTransaction.PROVIDER_STRIPE,
            event_id=f'invalid-{timezone.now().timestamp()}',
            event_type='signature_verification_failed',
            signature_valid=False,
            status=PaymentWebhookEvent.STATUS_REJECTED,
            error_message=str(exc),
            payload={},
        )
        return HttpResponse(status=400)

    event_id = event.get('id', '')
    event_type = event.get('type', '')

    webhook_event, created = PaymentWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            'provider': PaymentTransaction.PROVIDER_STRIPE,
            'event_type': event_type,
            'signature_valid': True,
            'status': PaymentWebhookEvent.STATUS_RECEIVED,
            'payload': event,
        }
    )

    if not created:
        return JsonResponse({'received': True, 'duplicate': True})

    data_object = event.get('data', {}).get('object', {})
    booking_reference = data_object.get('client_reference_id') or data_object.get('metadata', {}).get('booking_reference')
    payment_transaction_id = data_object.get('metadata', {}).get('payment_transaction_id')

    try:
        if payment_transaction_id:
            payment_transaction = PaymentTransaction.objects.select_related('booking_batch').get(id=payment_transaction_id)
        elif booking_reference:
            payment_transaction = PaymentTransaction.objects.select_related('booking_batch').get(
                booking_batch__booking_reference=booking_reference
            )
        else:
            raise PaymentGatewayError('Unable to map webhook to a payment transaction.')

        webhook_event.payment_transaction = payment_transaction

        if event_type == 'checkout.session.completed':
            finalize_successful_payment(
                payment_transaction,
                gateway_payment_intent_id=data_object.get('payment_intent', ''),
                verification_reference=event_id,
            )
        elif event_type in ['payment_intent.payment_failed', 'checkout.session.async_payment_failed']:
            mark_payment_failed(payment_transaction, 'Stripe reported that the payment failed.')
        elif event_type == 'checkout.session.expired':
            expire_booking_batch(payment_transaction.booking_batch, reason='Stripe expired the Checkout Session.')
        else:
            webhook_event.status = PaymentWebhookEvent.STATUS_PROCESSED
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=['payment_transaction', 'status', 'processed_at'])
            return JsonResponse({'received': True, 'ignored': True})

        webhook_event.status = PaymentWebhookEvent.STATUS_PROCESSED
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=['payment_transaction', 'status', 'processed_at'])
    except Exception as exc:
        webhook_event.status = PaymentWebhookEvent.STATUS_FAILED
        webhook_event.error_message = str(exc)
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=['payment_transaction', 'status', 'error_message', 'processed_at'])
        return HttpResponse(status=500)

    return JsonResponse({'received': True})
