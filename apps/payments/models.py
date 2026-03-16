# apps/payments/models.py
from django.db import models
from apps.orders.models import Order

class Payment(models.Model):
    
    PAYMENT_METHOD_CHOICES = (
        ('khalti', 'Khalti'),
        ('esewa', 'eSewa'),
        ('cod', 'Cash on Delivery'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('initiated', 'Initiated'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    order          = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    
    # Khalti fields
    khalti_token          = models.CharField(max_length=255, blank=True)
    khalti_transaction_id = models.CharField(max_length=255, blank=True, unique=True, null=True)
    khalti_idx            = models.CharField(max_length=255, blank=True)
    
    # ── eSewa fields ──────────────────────────────────────────────────────────
    esewa_transaction_uuid = models.CharField(max_length=255, blank=True)
    esewa_transaction_code = models.CharField(max_length=255, blank=True)
    # ─────────────────────────────────────────────────────────────────────────
    
    payment_response = models.JSONField(default=dict, blank=True)
    initiated_at     = models.DateTimeField(auto_now_add=True)
    completed_at     = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name        = 'Payment'
        verbose_name_plural = 'Payments'
        ordering            = ['-initiated_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['khalti_transaction_id']),
        ]
    
    def __str__(self):
        return f"Payment #{self.id} - {self.order.order_number} - {self.status}"
    
    def mark_as_completed(self, transaction_id, response_data):
        from django.utils import timezone
        self.status               = 'completed'
        self.khalti_transaction_id = transaction_id
        self.payment_response     = response_data
        self.completed_at         = timezone.now()
        self.save()
        self.order.mark_as_paid(payment_id=transaction_id)
    
    # ── eSewa complete ────────────────────────────────────────────────────────
    def mark_esewa_completed(self, transaction_uuid, transaction_code, response_data):
        from django.utils import timezone
        self.status                = 'completed'
        self.esewa_transaction_uuid = transaction_uuid
        self.esewa_transaction_code = transaction_code
        self.payment_response      = response_data
        self.completed_at          = timezone.now()
        self.save()
        self.order.mark_as_paid(payment_id=transaction_uuid)
    # ─────────────────────────────────────────────────────────────────────────
    
    def mark_as_failed(self, reason=''):
        self.status = 'failed'
        self.payment_response['error'] = reason
        self.save()