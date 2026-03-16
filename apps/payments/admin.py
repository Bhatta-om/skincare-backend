# apps/payments/admin.py

from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'order',
        'payment_method',
        'amount',
        'status',
        'khalti_transaction_id',
        'initiated_at',
    ]
    
    list_filter = [
        'payment_method',
        'status',
        'initiated_at',
    ]
    
    search_fields = [
        'order__order_number',
        'khalti_transaction_id',
    ]
    
    readonly_fields = [
        'order',
        'amount',
        'khalti_token',
        'khalti_transaction_id',
        'khalti_idx',
        'payment_response',
        'initiated_at',
        'completed_at',
    ]
    
    fieldsets = (
        ('Order Info', {
            'fields': ('order', 'amount')
        }),
        ('Payment Details', {
            'fields': (
                'payment_method',
                'status',
                'khalti_token',
                'khalti_transaction_id',
                'khalti_idx',
            )
        }),
        ('Response Data', {
            'fields': ('payment_response',)
        }),
        ('Timestamps', {
            'fields': ('initiated_at', 'completed_at')
        }),
    )
    
    def has_add_permission(self, request):
        return False