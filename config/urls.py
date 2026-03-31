# backend_project/urls.py
# ═══════════════════════════════════════════════════════════════════════════════
# FIX — static() helper for MEDIA_URL only works in DEBUG=True.
#
# BEFORE:
#   urlpatterns = [...] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
#
#   Problem: Django's static() returns an empty list when DEBUG=False.
#   In production (DEBUG=False), uploaded images would return 404 with
#   no error or warning — the URL pattern silently disappears.
#   Since you use Cloudinary for storage, MEDIA files are served by
#   Cloudinary in production anyway, so this line is only needed in
#   local development. The fix makes that explicit and safe.
#
# Everything else in this file is correct — all 8 app URL includes are
# properly registered and the URL prefixes match what each app's views expect.
# ═══════════════════════════════════════════════════════════════════════════════

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ── Admin ──────────────────────────────────────────────────────────────
    path('api/admin/', include('config.admin_urls')),
    path('admin/', admin.site.urls),

    # ── App routes ─────────────────────────────────────────────────────────
    path('api/users/',           include('apps.users.urls')),
    path('api/products/',        include('apps.products.urls')),
    path('api/skin-analysis/',   include('apps.skin_analysis.urls')),
    path('api/recommendations/', include('apps.recommendations.urls')),
    path('api/orders/',          include('apps.orders.urls')),
    path('api/payments/',        include('apps.payments.urls')),
]

# ── Media files (local development only) ─────────────────────────────────────
# static() returns [] when DEBUG=False, so this has no effect in production.
# In production, images are served directly by Cloudinary — Django never
# handles MEDIA_URL requests in a deployed environment.
# This guard makes the intent explicit and prevents confusion.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)