# config/settings/development.py
# ═══════════════════════════════════════════════════════════════════════════════
# FIX — CORS_ALLOW_ALL_ORIGINS and CORS_ALLOW_CREDENTIALS cannot both be True.
#
# Django CORS headers explicitly rejects this combination because allowing
# all origins with credentials is a security violation of the CORS spec.
# When both are True, the corsheaders library ignores CORS_ALLOW_ALL_ORIGINS
# and falls back to CORS_ALLOWED_ORIGINS from base.py — silently, with no
# error. This means your local frontend at http://localhost:5173 works fine
# (it's in CORS_ALLOWED_ORIGINS), but you might think all origins are allowed
# when they are not.
#
# Fix: Remove CORS_ALLOW_ALL_ORIGINS. In development, just extend
# CORS_ALLOWED_ORIGINS to include any extra local origins you need.
# CORS_ALLOW_CREDENTIALS = True is kept from base.py.
# ═══════════════════════════════════════════════════════════════════════════════

from .base import *
from decouple import config

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# ── Database — local PostgreSQL ────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     config('DB_NAME',     default='skincare_db'),
        'USER':     config('DB_USER',     default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='postgres'),
        'HOST':     config('DB_HOST',     default='localhost'),
        'PORT':     config('DB_PORT',     default='5432'),
    }
}

# ── CORS ───────────────────────────────────────────────────────────────────────
# FIX: CORS_ALLOW_ALL_ORIGINS + CORS_ALLOW_CREDENTIALS=True is rejected by
# the CORS spec and silently ignored by django-cors-headers.
# Add any extra local origins here instead.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",    # in case you run React on port 3000
    "http://127.0.0.1:3000",
]
# CORS_ALLOW_CREDENTIALS = True is already set in base.py