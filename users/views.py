import logging

from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required

from .forms import UserRegisterForm, UserUpdateForm
from movies.models import Booking, BookingBatch, Movie
from movies.payments import cleanup_expired_payment_holds

logger = logging.getLogger(__name__)

def home(request):
    """
    Homepage must never crash if the DB is empty/unavailable.
    Vercel/serverless + SQLite can throw transient OperationalError on cold starts.
    """
    try:
        # Evaluate immediately so template rendering can't trigger DB work.
        movies = list(Movie.objects.order_by('-id')[:8])
    except Exception:
        logger.exception("Homepage movie query failed.")
        movies = []

    try:
        return render(request, 'home.html', {'movies': movies})
    except Exception:
        # Last-resort: don't take down "/" due to a template issue.
        logger.exception("Homepage template render failed.")
        return render(request, 'home.html', {'movies': []})
def register(request):
    if request.method == 'POST':
        form=UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            username=form.cleaned_data.get('username')
            password=form.cleaned_data.get('password1')
            user=authenticate(username=username,password=password)
            login(request,user)
            return redirect('profile')
    else:
        form=UserRegisterForm()
    return render(request,'users/register.html',{'form':form})

def login_view(request):
    if request.method == 'POST':
        form=AuthenticationForm(request,data=request.POST)
        if form.is_valid():
            user=form.get_user()
            login(request,user)
            return redirect('/')
    else:
        form=AuthenticationForm()
    return render(request,'users/login.html',{'form':form})

@login_required
def profile(request):
    cleanup_expired_payment_holds()
    bookings = Booking.objects.filter(user=request.user).select_related('movie', 'theater', 'seat', 'booking_batch')
    payment_batches = BookingBatch.objects.filter(
        user=request.user,
        status__in=[
            BookingBatch.STATUS_CONFIRMED,
            BookingBatch.STATUS_PENDING_PAYMENT,
            BookingBatch.STATUS_PAYMENT_PROCESSING,
        ]
    ).select_related('movie', 'theater').order_by('-created_at')
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        if u_form.is_valid():
            u_form.save()
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)

    return render(request, 'users/profile.html', {'u_form': u_form,'bookings':bookings, 'payment_batches': payment_batches})

@login_required
def reset_password(request):
    if request.method == 'POST':
        form=PasswordChangeForm(user=request.user,data=request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form=PasswordChangeForm(user=request.user)
    return render(request,'users/reset_password.html',{'form':form})
