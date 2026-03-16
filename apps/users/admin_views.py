# apps/users/admin_views.py — AdminDashboardStatsView को get() method replace गर्नुस्
# (पूरै file replace गर्नुस्)

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)
User = get_user_model()


class IsAdminPermission(IsAdminUser):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class AdminDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]

    def get(self, request):
        from apps.orders.models import Order
        from apps.products.models import Product
        from apps.skin_analysis.models import SkinAnalysis
        from django.db.models import Sum, Count
        from django.db.models.functions import TruncDate, TruncMonth

        now        = timezone.now()
        this_month = now - timedelta(days=30)
        last_7days = now - timedelta(days=7)

        # ── Basic Stats ────────────────────────────────────
        total_users    = User.objects.count()
        verified_users = User.objects.filter(is_verified=True).count()
        new_users      = User.objects.filter(created_at__gte=this_month).count()

        total_orders    = Order.objects.count()
        pending_orders  = Order.objects.filter(status='pending').count()
        revenue         = Order.objects.filter(payment_status='paid').aggregate(total=Sum('total_amount'))['total'] or 0
        monthly_revenue = Order.objects.filter(payment_status='paid', created_at__gte=this_month).aggregate(total=Sum('total_amount'))['total'] or 0

        total_products = Product.objects.count()
        low_stock      = Product.objects.filter(stock__lte=10, is_available=True).count()
        out_of_stock   = Product.objects.filter(stock=0).count()
        total_analyses = SkinAnalysis.objects.count()

        # ── Recent Orders ──────────────────────────────────
        recent_orders = list(Order.objects.order_by('-created_at')[:5].values(
            'id', 'order_number', 'full_name',
            'total_amount', 'status', 'payment_status', 'created_at'
        ))

        # ── Order by Status ────────────────────────────────
        order_stats = list(Order.objects.values('status').annotate(count=Count('id')))

        # ── Revenue Last 7 Days (Line Chart) ───────────────
        revenue_7days = list(
            Order.objects.filter(
                payment_status='paid',
                created_at__gte=last_7days
            )
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(revenue=Sum('total_amount'), orders=Count('id'))
            .order_by('date')
        )
        # Fill missing days
        revenue_chart = []
        for i in range(7):
            day = (now - timedelta(days=6-i)).date()
            found = next((r for r in revenue_7days if r['date'] == day), None)
            revenue_chart.append({
                'date':    day.strftime('%b %d'),
                'revenue': float(found['revenue']) if found else 0,
                'orders':  found['orders'] if found else 0,
            })

        # ── Monthly Revenue Last 6 Months (Bar Chart) ──────
        monthly_data = list(
            Order.objects.filter(
                payment_status='paid',
                created_at__gte=now - timedelta(days=180)
            )
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(revenue=Sum('total_amount'), orders=Count('id'))
            .order_by('month')
        )
        monthly_chart = [{
            'month':   m['month'].strftime('%b %Y'),
            'revenue': float(m['revenue']),
            'orders':  m['orders'],
        } for m in monthly_data]

        # ── Orders by Payment Method (Pie Chart) ──────────
        payment_chart = list(
            Order.objects.values('payment_method')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # ── Top Products by Orders ─────────────────────────
        from apps.orders.models import OrderItem
        top_products = list(
            OrderItem.objects.values('product__name', 'product__brand')
            .annotate(total_sold=Sum('quantity'), total_revenue=Sum('total_price'))
            .order_by('-total_sold')[:5]
        )

        # ── New Users Last 7 Days ──────────────────────────
        users_7days = list(
            User.objects.filter(created_at__gte=last_7days)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )
        users_chart = []
        for i in range(7):
            day = (now - timedelta(days=6-i)).date()
            found = next((u for u in users_7days if u['date'] == day), None)
            users_chart.append({
                'date':  day.strftime('%b %d'),
                'users': found['count'] if found else 0,
            })

        # ── Skin Type Distribution ─────────────────────────
        skin_chart = list(
            SkinAnalysis.objects.values('skin_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        ) if total_analyses > 0 else []

        return Response({
            'success': True,
            'stats': {
                'users':    { 'total': total_users, 'verified': verified_users, 'new_this_month': new_users },
                'orders':   { 'total': total_orders, 'pending': pending_orders, 'total_revenue': float(revenue), 'monthly_revenue': float(monthly_revenue), 'by_status': order_stats },
                'products': { 'total': total_products, 'low_stock': low_stock, 'out_of_stock': out_of_stock },
                'analyses': { 'total': total_analyses },
            },
            'recent_orders':  recent_orders,
            'charts': {
                'revenue_7days':   revenue_chart,
                'monthly_revenue': monthly_chart,
                'payment_methods': payment_chart,
                'top_products':    top_products,
                'users_7days':     users_chart,
                'skin_types':      skin_chart,
            }
        })


# ════════════════════════════════════════════════════════════
# USER LIST
# ════════════════════════════════════════════════════════════

class AdminUserListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]

    def get(self, request):
        users = User.objects.all().order_by('-date_joined')

        search      = request.query_params.get('search', '')
        is_verified = request.query_params.get('is_verified', '')
        is_staff    = request.query_params.get('is_staff', '')

        if search:
            from django.db.models import Q
            users = users.filter(
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        if is_verified in ('true', 'false'):
            users = users.filter(is_verified=(is_verified == 'true'))
        if is_staff in ('true', 'false'):
            users = users.filter(is_staff=(is_staff == 'true'))

        data = [{
            'id': u.id, 'email': u.email, 'first_name': u.first_name,
            'last_name': u.last_name, 'phone': getattr(u, 'phone', ''),
            'is_verified': u.is_verified, 'is_staff': u.is_staff,
            'is_active': u.is_active, 'date_joined': u.date_joined,
        } for u in users]

        return Response({'success': True, 'count': len(data), 'users': data})


# ════════════════════════════════════════════════════════════
# USER UPDATE
# ════════════════════════════════════════════════════════════

class AdminUserUpdateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminPermission]

    def patch(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)

        allowed = ['is_verified', 'is_active', 'is_staff']
        updated = [f for f in allowed if f in request.data]
        for field in updated:
            setattr(user, field, request.data[field])
        if updated:
            user.save(update_fields=updated)

        return Response({
            'success': True,
            'message': f'Updated: {", ".join(updated)}',
            'user': { 'id': user.id, 'email': user.email, 'is_verified': user.is_verified, 'is_active': user.is_active, 'is_staff': user.is_staff }
        })