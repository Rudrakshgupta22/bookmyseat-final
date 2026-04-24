"""
Django settings for bookmyseat project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url  # <-- ADDED FOR VERCEL DATABASE

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-local-placeholder')

load_dotenv()

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
IS_VERCEL = os.getenv('VERCEL') == '1'

allowed_hosts_env = os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost,.vercel.app')
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_env.split(',') if host.strip()]
if IS_VERCEL and not any(host.endswith('.vercel.app') or host == '.vercel.app' for host in ALLOWED_HOSTS):
    ALLOWED_HOSTS.append('.vercel.app')

csrf_origins_env = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_origins_env.split(',') if origin.strip()]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'cloudinary_storage',         # <-- ADDED FOR CLOUDINARY
    'django.contrib.staticfiles',
    'cloudinary',                 # <-- ADDED FOR CLOUDINARY
    'users',
    'movies',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

EMAIL_QUEUE_AUTOSTART = os.getenv('EMAIL_QUEUE_AUTOSTART', 'True').lower() == 'true'
BOOKING_EMAIL_MAX_RETRIES = int(os.getenv('BOOKING_EMAIL_MAX_RETRIES', '3'))
BOOKING_EMAIL_RETRY_DELAY_SECONDS = int(os.getenv('BOOKING_EMAIL_RETRY_DELAY_SECONDS', '30'))
BOOKING_EMAIL_QUEUE_POLL_INTERVAL_SECONDS = int(os.getenv('BOOKING_EMAIL_QUEUE_POLL_INTERVAL_SECONDS', '5'))
BOOKING_EMAIL_PROCESSING_TIMEOUT_SECONDS = int(os.getenv('BOOKING_EMAIL_PROCESSING_TIMEOUT_SECONDS', '300'))

PAYMENT_GATEWAY_PROVIDER = os.getenv('PAYMENT_GATEWAY_PROVIDER', 'stripe')
PAYMENT_CURRENCY = os.getenv('PAYMENT_CURRENCY', 'inr')
PAYMENT_TICKET_PRICE_MINOR = int(os.getenv('PAYMENT_TICKET_PRICE_MINOR', '25000'))
PAYMENT_HOLD_DURATION_MINUTES = int(os.getenv('PAYMENT_HOLD_DURATION_MINUTES', '2'))
SEAT_RESERVATION_TIMEOUT_MINUTES = int(os.getenv('SEAT_RESERVATION_TIMEOUT_MINUTES', '2'))
SEAT_RESERVATION_CLEANUP_INTERVAL_SECONDS = int(os.getenv('SEAT_RESERVATION_CLEANUP_INTERVAL_SECONDS', '5'))
SEAT_RESERVATION_AUTOSTART = os.getenv('SEAT_RESERVATION_AUTOSTART', 'True').lower() == 'true'
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')
STRIPE_API_BASE = os.getenv('STRIPE_API_BASE', 'https://api.stripe.com')
STRIPE_WEBHOOK_TOLERANCE_SECONDS = int(os.getenv('STRIPE_WEBHOOK_TOLERANCE_SECONDS', '300'))

ROOT_URLCONF = 'bookmyseat.urls'
LOGIN_URL='/login/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'bookmyseat.wsgi.application'

# --- DATABASE FIX FOR VERCEL / RENDER ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

database_url = os.getenv('DATABASE_URL')
if database_url:
    DATABASES['default'] = dj_database_url.config(
        default=database_url,
        conn_max_age=600,
        ssl_require=True
    )

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # <-- ADDED FOR VERCEL TO NOT CRASH

STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# --- CLOUDINARY MEDIA SETTINGS ---
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
}
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# Caching & Analytics
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'bookmyseat-analytics-cache',
        'TIMEOUT': 60,
    }
}

ANALYTICS_CACHE_TIMEOUT_SECONDS = int(os.getenv('ANALYTICS_CACHE_TIMEOUT_SECONDS', '60'))

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        'movies.email_queue': {'handlers': ['console'], 'level': 'INFO', 'propagate': False,},
        'movies.payments': {'handlers': ['console'], 'level': 'INFO', 'propagate': False,},
        'movies.reservation_worker': {'handlers': ['console'], 'level': 'INFO', 'propagate': False,},
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'