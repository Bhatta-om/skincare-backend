# apps/orders/admin_views.py

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.utils import timezone

from .models import Order

logger = logging.getLogger(__name__)


class IsAdminPermission(IsAdminUser):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


# ════════════════════════════════════════════════════════════
# ORDER LIST
# ════════════════════════════════════════════════════════════

class AdminOrderListView(APIView):
    """
    GET /api/admin/orders/
    List all orders with filters.
    Admin only.
    """
    permission_classes = [IsAuthenticated, IsAdminPermission]

    def get(self, request):
        orders = Order.objects.all().order_by('-created_at')

        status_filter  = request.query_params.get('status', '')
        payment_filter = request.query_params.get('payment_status', '')
        search         = request.query_params.get('search', '')

        if status_filter:
            orders = orders.filter(status=status_filter)
        if payment_filter:
            orders = orders.filter(payment_status=payment_filter)
        if search:
            from django.db.models import Q
            orders = orders.filter(
                Q(order_number__icontains=search) |
                Q(full_name__icontains=search) |
                Q(email__icontains=search)
            )

        data = [{
            'id':             o.id,
            'order_number':   o.order_number,
            'full_name':      o.full_name,
            'email':          o.email,
            'phone':          o.phone,
            'city':           o.city,
            'total_amount':   str(o.total_amount),
            'status':         o.status,
            'payment_status': o.payment_status,
            'payment_method': o.payment_method,
            'created_at':     o.created_at,
            'items_count':    o.items.count(),
        } for o in orders]

        return Response({'success': True, 'count': len(data), 'orders': data})


# ════════════════════════════════════════════════════════════
# ORDER STATUS UPDATE
# ════════════════════════════════════════════════════════════

class AdminOrderUpdateView(APIView):
    """
    PATCH /api/admin/orders/<pk>/status/
    Update order status + send email.
    Admin only.
    """
    permission_classes = [IsAuthenticated, IsAdminPermission]

    def patch(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response({'success': False, 'error': 'Order not found.'}, status=404)

        new_status = request.data.get('status', '')
        admin_note = request.data.get('admin_notes', '')

        valid = ['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled']
        if new_status and new_status not in valid:
            return Response({
                'success': False,
                'error': f'Invalid status. Choose: {", ".join(valid)}'
            }, status=400)

        updated = []

        if new_status:
            order.status = new_status
            updated.append('status')
            if new_status == 'confirmed':
                order.confirmed_at = timezone.now(); updated.append('confirmed_at')
            elif new_status == 'shipped':
                order.shipped_at = timezone.now(); updated.append('shipped_at')
            elif new_status == 'delivered':
                order.delivered_at = timezone.now(); updated.append('delivered_at')
            self._send_email(order, new_status)

        if admin_note:
            order.admin_notes = admin_note
            updated.append('admin_notes')

        if updated:
            order.save(update_fields=updated)

        return Response({
            'success': True,
            'message': f'Order {order.order_number} updated!',
            'order': {
                'id':           order.id,
                'order_number': order.order_number,
                'status':       order.status,
            }
        })

    def _send_email(self, order, new_status):
        from django.core.mail import send_mail
        from django.conf import settings

        templates = {
            'confirmed': ('Order Confirmed ✅', f'Namaste {order.full_name}!\n\nOrder {order.order_number} confirm bhayo!\nTotal: Rs. {order.total_amount}\n\nSkinCare Team'),
            'shipped':   ('Order Shipped 🚚',   f'Namaste {order.full_name}!\n\nOrder {order.order_number} ship bhayo!\nChado nai pugchha!\n\nSkinCare Team'),
            'delivered': ('Order Delivered 📦', f'Namaste {order.full_name}!\n\nOrder {order.order_number} deliver bhayo!\nDhanyabad!\n\nSkinCare Team'),
            'cancelled': ('Order Cancelled ❌', f'Namaste {order.full_name}!\n\nOrder {order.order_number} cancel bhayo.\n\nSkinCare Team'),
        }
        if new_status in templates:
            subject, message = templates[new_status]
            try:
                send_mail(subject, message, settings.EMAIL_HOST_USER, [order.email], fail_silently=True)
            except Exception as e:
                logger.warning("Email failed: %s", str(e))