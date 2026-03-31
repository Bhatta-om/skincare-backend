# config/settings/production.py
# ═══════════════════════════════════════════════════════════════════════════════
# FIXES:
#
#   FIX 1 — conn_max_age set to 60 instead of 0.
#            conn_max_age=0 means Django opens and closes a NEW database
#            connection on every single request. On Neon PostgreSQL (serverless),
#            this causes a cold connection overhead on every API call and can
#            exhaust the connection pool under load. Setting it to 60 seconds
#            keeps connections alive and reuses them across requests, which
#            is the standard Django production recommendation.
#
#   FIX 2 — SECURE_SSL_REDIRECT changed from False to True.
#            The comment said "Render handles SSL" — but that is only true
#            for the public-facing HTTPS termination. Inside Render's network,
#            requests arrive at Django over HTTP. SECURE_SSL_REDIRECT=True
#            would redirect those internal HTTP requests and cause redirect
#            loops on Render.
#            The correct fix is to keep SECURE_SSL_REDIRECT=False but add
#            SECURE_PROXY_SSL_HEADER so Django trusts Render's X-Forwarded-Proto
#            header and correctly identifies requests as HTTPS. Without this,
#            Django does not know the original request was HTTPS, which breaks
#            SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE enforcement.
#
#   Everything else is correct — no other changes made.
# ═══════════════════════════════════════════════════════════════════════════════

from .base import *
from decouple import config
import dj_database_url

DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost').split(',')

# ── Database — Neon PostgreSQL ─────────────────────────────────────────────────
# FIX 1: conn_max_age=60 reuses DB connections across requests.
# conn_max_age=0 (original) opened a new connection on every request,
# causing unnecessary overhead and connection pool exhaustion under load.
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default='sqlite:///db.sqlite3'),
        conn_max_age=60,
        ssl_require=True,
    )
}

# ── CORS ───────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://skincare-frontend-mu.vercel.app",
]
CORS_ALLOW_CREDENTIALS = True

# ── Security ───────────────────────────────────────────────────────────────────
# FIX 2: SECURE_PROXY_SSL_HEADER added.
# Render terminates SSL at the proxy level and forwards requests to Django
# over HTTP with the X-Forwarded-Proto: https header.
# Without this setting, Django thinks all requests are plain HTTP and
# SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE have no effect.
SECURE_PROXY_SSL_HEADER    = ('HTTP_X_FORWARDED_PROTO', 'https')

# Keep False — Render handles the HTTP→HTTPS redirect at the proxy level.
# Setting True here would cause an infinite redirect loop on Render.
SECURE_SSL_REDIRECT         = False

SESSION_COOKIE_SECURE       = True
CSRF_COOKIE_SECURE          = True
SECURE_BROWSER_XSS_FILTER   = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS             = 'DENY'
SECURE_HSTS_SECONDS         = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD         = True

# ── Logging ────────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}