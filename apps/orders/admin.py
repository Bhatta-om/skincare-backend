# apps/orders/admin.py

from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import csv
from .models import Cart, CartItem, Order, OrderItem

# ════════════════════════════════════════════════════════════
# CART ADMIN
# ════════════════════════════════════════════════════════════

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ['product', 'quantity', 'unit_price', 'total_price']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_items', 'subtotal', 'updated_at']
    inlines = [CartItemInline]
    readonly_fields = ['user', 'created_at', 'updated_at']


# ════════════════════════════════════════════════════════════
# ORDER ADMIN
# ════════════════════════════════════════════════════════════

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [
        'product',
        'product_name',
        'product_brand',
        'quantity',
        'unit_price',
        'total_price',
    ]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number',
        'user',
        'full_name',
        'total_amount',
        'payment_status',
        'status',
        'created_at',
    ]

    list_filter = [
        'status',
        'payment_status',
        'payment_method',
        'created_at',
    ]

    search_fields = [
        'order_number',
        'user__email',
        'full_name',
        'phone',
        'email',
    ]

    readonly_fields = [
        'order_number',
        'user',
        'created_at',
        'updated_at',
        'confirmed_at',
        'shipped_at',
        'delivered_at',
        'paid_at',
    ]

    fieldsets = (
        ('Order Info', {
            'fields': ('order_number', 'user', 'status', 'created_at')
        }),
        ('Customer Details', {
            'fields': (
                'full_name', 'phone', 'email',
                'address_line1', 'address_line2',
                'city', 'state', 'postal_code', 'country',
            )
        }),
        ('Pricing', {
            'fields': ('subtotal', 'shipping_cost', 'tax', 'discount', 'total_amount')
        }),
        ('Payment', {
            'fields': ('payment_method', 'payment_status', 'payment_id', 'paid_at')
        }),
        ('Notes', {
            'fields': ('notes', 'admin_notes')
        }),
        ('Timestamps', {
            'fields': ('confirmed_at', 'shipped_at', 'delivered_at', 'updated_at')
        }),
    )

    inlines = [OrderItemInline]

    # ── Actions ────────────────────────────────────────────────────────────────
    actions = [
        'mark_as_confirmed',
        'mark_as_shipped',
        'mark_as_delivered',
        'export_orders_csv',      # ← NEW: Export to CSV
    ]

    # ── Mark as Confirmed + Email ──────────────────────────────────────────────
    def mark_as_confirmed(self, request, queryset):
        for order in queryset:
            if order.status == 'pending':
                order.status = 'confirmed'
                order.confirmed_at = timezone.now()
                order.save(update_fields=['status', 'confirmed_at'])

                # ── Email notification ─────────────────────────────────────────
                try:
                    send_mail(
                        subject=f'Order {order.order_number} Confirmed!',
                        message=f'''
Namaste {order.full_name}!

Tapaaiko order confirm bhayo!

Order Number: {order.order_number}
Total Amount: Rs. {order.total_amount}
Status: Confirmed

Chado nai deliver hunchha.

Regards,
Skincare App Team
                        ''',
                        from_email=settings.EMAIL_HOST_USER,
                        recipient_list=[order.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
                # ──────────────────────────────────────────────────────────────

        self.message_user(request, f'{queryset.count()} orders confirmed and emails sent!')
    mark_as_confirmed.short_description = "Mark as Confirmed + Send Email"

    # ── Mark as Shipped + Email ────────────────────────────────────────────────
    def mark_as_shipped(self, request, queryset):
        for order in queryset:
            if order.status == 'confirmed':
                order.status = 'shipped'
                order.shipped_at = timezone.now()
                order.save(update_fields=['status', 'shipped_at'])

                try:
                    send_mail(
                        subject=f'Order {order.order_number} Shipped!',
                        message=f'''
Namaste {order.full_name}!

Tapaaiko order ship bhayo!

Order Number: {order.order_number}
Total Amount: Rs. {order.total_amount}
Status: Shipped

Chado nai pugchha!

Regards,
Skincare App Team
                        ''',
                        from_email=settings.EMAIL_HOST_USER,
                        recipient_list=[order.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

        self.message_user(request, f'{queryset.count()} orders shipped and emails sent!')
    mark_as_shipped.short_description = "Mark as Shipped + Send Email"

    # ── Mark as Delivered + Email ──────────────────────────────────────────────
    def mark_as_delivered(self, request, queryset):
        for order in queryset:
            if order.status == 'shipped':
                order.status = 'delivered'
                order.delivered_at = timezone.now()
                order.save(update_fields=['status', 'delivered_at'])

                try:
                    send_mail(
                        subject=f'Order {order.order_number} Delivered!',
                        message=f'''
Namaste {order.full_name}!

Tapaaiko order deliver bhayo!

Order Number: {order.order_number}
Total Amount: Rs. {order.total_amount}
Status: Delivered

Review dinus please!

Regards,
Skincare App Team
                        ''',
                        from_email=settings.EMAIL_HOST_USER,
                        recipient_list=[order.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

        self.message_user(request, f'{queryset.count()} orders delivered and emails sent!')
    mark_as_delivered.short_description = "Mark as Delivered + Send Email"

    # ── Export CSV ─────────────────────────────────────────────────────────────
    def export_orders_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="orders.csv"'

        writer = csv.writer(response)

        # Header row
        writer.writerow([
            'Order Number', 'Customer Name', 'Email', 'Phone',
            'City', 'Total Amount', 'Payment Method', 'Payment Status',
            'Order Status', 'Created At',
        ])

        # Data rows
        for order in queryset:
            writer.writerow([
                order.order_number,
                order.full_name,
                order.email,
                order.phone,
                order.city,
                order.total_amount,
                order.payment_method,
                order.payment_status,
                order.status,
                order.created_at.strftime('%Y-%m-%d %H:%M'),
            ])

        return response
    export_orders_csv.short_description = "Export Selected Orders to CSV"