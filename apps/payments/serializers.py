# apps/payments/serializers.py

from rest_framework import serializers
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    """Payment details"""

    order_number = serializers.CharField(source='order.order_number', read_only=True)
    total_amount = serializers.DecimalField(
        source='order.total_amount', max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model  = Payment
        fields = [
            'id',
            'order',
            'order_number',
            'total_amount',
            'payment_method',
            'amount',
            'status',
            'khalti_transaction_id',
            'initiated_at',
            'completed_at',
        ]
        read_only_fields = [
            'id', 'status', 'khalti_transaction_id',
            'initiated_at', 'completed_at',
        ]


class KhaltiInitiateSerializer(serializers.Serializer):
    """Initiate Khalti payment"""

    order_id   = serializers.IntegerField()
    return_url = serializers.URLField(required=False)

    def validate_order_id(self, value):
        from apps.orders.models import Order
        try:
            order = Order.objects.get(id=value)
            if order.payment_status == 'paid':
                raise serializers.ValidationError("Order already paid!")
            return value
        except Order.DoesNotExist:
            raise serializers.ValidationError("Order not found!")


# ── UPDATED: token → pidx (Khalti new API uses pidx) ─────────────────────────
class KhaltiVerifySerializer(serializers.Serializer):
    """
    Verify Khalti payment

    Khalti new API (v2) le token hoina pidx use garcha.
    Frontend bata pidx aaucha payment success bhayepachi.
    """
    pidx      = serializers.CharField()
    order_id  = serializers.IntegerField()
# ─────────────────────────────────────────────────────────────────────────────