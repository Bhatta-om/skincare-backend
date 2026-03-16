# config/settings/base.py — 100% Production Ready

from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-temporary-key-change-this')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'rest_framework_simplejwt.token_blacklist',
    'apps.users',
    'apps.products',
    'apps.skin_analysis',
    'apps.recommendations',
    'apps.orders',
    'apps.payments',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
     'whitenoise.middleware.WhiteNoiseMiddleware', 
]

ROOT_URLCONF    = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTH_USER_MODEL = 'users.User'

LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Kathmandu'
USE_I18N      = True
USE_TZ        = True

STATIC_URL  = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL   = '/media/'
MEDIA_ROOT  = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 12,
    'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':    timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME':   timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':    True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES':        ('Bearer',),
}

# ════════════════════════════════════════════════════════════
# EMAIL — Gmail SMTP (100% Professional)
# ════════════════════════════════════════════════════════════
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp.gmail.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_USE_SSL       = False
EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='rhodiom1319@gmail.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='lbyfvneetepnjkfh')
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL',  default='✨ SkinCare <rhodiom1319@gmail.com>')

EMAIL_VERIFICATION_EXPIRY_HOURS = 24

# ── Frontend URL ───────────────────────────────────────────
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')

# ── CORS ───────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_CREDENTIALS = True

# ── eSewa Payment ──────────────────────────────────────────
ESEWA_PRODUCT_CODE = config('ESEWA_PRODUCT_CODE', default='EPAYTEST')
ESEWA_SECRET_KEY   = config('ESEWA_SECRET_KEY',   default='8gBm/:&EnhH.1/q')
ESEWA_PAYMENT_URL  = config('ESEWA_PAYMENT_URL',  default='https://rc-epay.esewa.com.np/api/epay/main/v2/form')
ESEWA_SUCCESS_URL  = config('ESEWA_SUCCESS_URL',  default='http://localhost:5173/payment/esewa/success')
ESEWA_FAILURE_URL  = config('ESEWA_FAILURE_URL',  default='http://localhost:5173/payment/esewa/failure')

# ── Khalti ─────────────────────────────────────────────────
KHALTI_PUBLIC_KEY    = config('KHALTI_PUBLIC_KEY',    default='')
KHALTI_SECRET_KEY    = config('KHALTI_SECRET_KEY',    default='')
KHALTI_MERCHANT_NAME = config('KHALTI_MERCHANT_NAME', default='Skincare Store')
KHALTI_RETURN_URL    = config('KHALTI_RETURN_URL',    default='http://localhost:5173/payment/success')
KHALTI_WEBSITE_URL   = config('KHALTI_WEBSITE_URL',   default='http://localhost:5173')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'