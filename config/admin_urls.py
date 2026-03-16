# config/admin_urls.py

from django.urls import path
from apps.users.admin_views import (
    AdminDashboardStatsView,
    AdminUserListView,
    AdminUserUpdateView,
)
from apps.orders.admin_views import (
    AdminOrderListView,
    AdminOrderUpdateView,
)
from apps.products.admin_views import (
    AdminProductStatsView,
)

urlpatterns = [
    # ── Dashboard ──────────────────────────────────────────
    path('stats/',                   AdminDashboardStatsView.as_view(), name='admin_stats'),

    # ── Users ──────────────────────────────────────────────
    path('users/',                   AdminUserListView.as_view(),       name='admin_users'),
    path('users/<int:pk>/',          AdminUserUpdateView.as_view(),     name='admin_user_update'),

    # ── Orders ─────────────────────────────────────────────
    path('orders/',                  AdminOrderListView.as_view(),      name='admin_orders'),
    path('orders/<int:pk>/status/',  AdminOrderUpdateView.as_view(),    name='admin_order_status'),

    # ── Products ───────────────────────────────────────────
    path('products/stats/',          AdminProductStatsView.as_view(),   name='admin_product_stats'),
]