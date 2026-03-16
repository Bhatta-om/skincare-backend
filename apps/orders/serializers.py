# apps/orders/serializers.py

from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderItem
from apps.products.serializers import ProductListSerializer

# ════════════════════════════════════════════════════════════
# CART SERIALIZERS
# ════════════════════════════════════════════════════════════

class CartItemSerializer(serializers.ModelSerializer):
    """Single cart item"""
    
    product = ProductListSerializer(read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = CartItem
        fields = [
            'id',
            'product',
            'quantity',
            'unit_price',
            'total_price',
            'added_at',
        ]


class AddToCartSerializer(serializers.Serializer):
    """Add product to cart"""
    
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    
    def validate_product_id(self, value):
        from apps.products.models import Product
        try:
            product = Product.objects.get(id=value, is_available=True)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or unavailable!")


class UpdateCartItemSerializer(serializers.Serializer):
    """Update cart item quantity"""
    
    quantity = serializers.IntegerField(min_value=1)


class CartSerializer(serializers.ModelSerializer):
    """Full cart with items"""
    
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Cart
        fields = [
            'user',
            'items',
            'total_items',
            'subtotal',
            'created_at',
            'updated_at',
        ]


# ════════════════════════════════════════════════════════════
# ORDER SERIALIZERS
# ════════════════════════════════════════════════════════════

class OrderItemSerializer(serializers.ModelSerializer):
    """Order item detail"""
    
    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product_name',
            'product_brand',
            'product_image',
            'quantity',
            'unit_price',
            'total_price',
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Order list (summary)"""
    
    total_items = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'total_items',
            'total_amount',
            'status',
            'payment_status',
            'created_at',
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    """Order detail (full info)"""
    
    items = OrderItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'user_email',
            'full_name',
            'phone',
            'email',
            'address_line1',
            'address_line2',
            'city',
            'state',
            'postal_code',
            'country',
            'subtotal',
            'shipping_cost',
            'tax',
            'discount',
            'total_amount',
            'payment_method',
            'payment_status',
            'payment_id',
            'paid_at',
            'status',
            'notes',
            'items',
            'total_items',
            'created_at',
            'confirmed_at',
            'shipped_at',
            'delivered_at',
        ]


class CreateOrderSerializer(serializers.Serializer):
    """Create order from cart"""
    
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=15)
    email = serializers.EmailField()
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=['cod', 'esewa', 'khalti', 'bank'],
        default='cod'
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    
class BuyNowSerializer(serializers.Serializer):
    """Buy Now — direct single product order"""

    product_id    = serializers.IntegerField()
    quantity      = serializers.IntegerField(min_value=1, default=1)
    full_name     = serializers.CharField(max_length=255)
    phone         = serializers.CharField(max_length=15)
    email         = serializers.EmailField()
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city          = serializers.CharField(max_length=100)
    state         = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code   = serializers.CharField(max_length=20, required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=['cod', 'esewa', 'khalti', 'bank'],
        default='cod'
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_product_id(self, value):
        from apps.products.models import Product
        try:
            Product.objects.get(id=value, is_available=True)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or unavailable!")


class CheckoutSelectedSerializer(serializers.Serializer):
    """Checkout selected cart items"""

    # ── cart_item_ids — frontend le selected item IDs pathaucha ──────────────
    cart_item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        error_messages={'min_length': 'Please select at least 1 item!'}
    )
    full_name     = serializers.CharField(max_length=255)
    phone         = serializers.CharField(max_length=15)
    email         = serializers.EmailField()
    address_line1 = serializers.CharField(max_length=255)
    address_line2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city          = serializers.CharField(max_length=100)
    state         = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code   = serializers.CharField(max_length=20, required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=['cod', 'esewa', 'khalti', 'bank'],
        default='cod'
    )
    notes = serializers.CharField(required=False, allow_blank=True)