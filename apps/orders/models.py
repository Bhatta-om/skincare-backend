# apps/orders/models.py

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.products.models import Product
from decimal import Decimal

# ════════════════════════════════════════════════════════════
# CART MODELS
# ════════════════════════════════════════════════════════════

class Cart(models.Model):
    """
    Shopping Cart
    
    One cart per user (logged in)
    Guest users use session-based cart (not in DB) 
    """
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart',
        primary_key=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'
    
    def __str__(self):
        return f"Cart of {self.user.email}"
    
    @property
    def total_items(self):
        """Cart ma kati items chan"""
        return self.items.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0
    
    @property
    def subtotal(self):
        """Total price (before tax/shipping)"""
        total = sum(item.total_price for item in self.items.all())
        return Decimal(total)
    
    def clear(self):
        """Cart khali gara"""
        self.items.all().delete()


class CartItem(models.Model):
    """
    Individual item in cart
    """
    
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )
    
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = [['cart', 'product']]  # Same product twice nai
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name}"
    
    @property
    def unit_price(self):
        """Per item price (discounted)"""
        return self.product.discounted_price
    
    @property
    def total_price(self):
        """Total for this item"""
        return self.unit_price * self.quantity
    
    def save(self, *args, **kwargs):
        # Stock validation
        if self.quantity > self.product.stock:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                f"Only {self.product.stock} units available!"
            )
        super().save(*args, **kwargs)


# ════════════════════════════════════════════════════════════
# ORDER MODELS
# ════════════════════════════════════════════════════════════

class Order(models.Model):
    """
    Customer Order
    """
    
    # ════════════════════════════════════════════════════════════
    # ORDER STATUS
    # ════════════════════════════════════════════════════════════
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    )
    
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    PAYMENT_METHOD_CHOICES = (
        ('cod', 'Cash on Delivery'),
        ('esewa', 'eSewa'),
        ('khalti', 'Khalti'),
        ('bank', 'Bank Transfer'),
    )
    
    # ════════════════════════════════════════════════════════════
    # BASIC INFO
    # ════════════════════════════════════════════════════════════
    
    order_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text='Auto-generated order number'
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='orders'
    )
    
    # ════════════════════════════════════════════════════════════
    # DELIVERY ADDRESS
    # ════════════════════════════════════════════════════════════
    
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='Nepal')
    
    # ════════════════════════════════════════════════════════════
    # PRICING
    # ════════════════════════════════════════════════════════════
    
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Products total'
    )
    
    shipping_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    tax = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Coupon discount'
    )
    
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Final amount to pay'
    )
    
    # ════════════════════════════════════════════════════════════
    # PAYMENT
    # ════════════════════════════════════════════════════════════
    
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cod'
    )
    
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    payment_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='Transaction ID from payment gateway'
    )
    
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # ════════════════════════════════════════════════════════════
    # ORDER STATUS
    # ════════════════════════════════════════════════════════════
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    
    notes = models.TextField(
        blank=True,
        help_text='Customer notes'
    )
    
    admin_notes = models.TextField(
        blank=True,
        help_text='Internal admin notes'
    )
    
    # ════════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ════════════════════════════════════════════════════════════
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # ════════════════════════════════════════════════════════════
    # META
    # ════════════════════════════════════════════════════════════
    
    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']
        
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['order_number']),
        ]
    
    def __str__(self):
        return f"Order {self.order_number}"
    
    def save(self, *args, **kwargs):
        # Auto-generate order number
        if not self.order_number:
            import random
            import string
            from django.utils import timezone
            
            # Format: ORD-YYYYMMDD-XXXX
            date_str = timezone.now().strftime('%Y%m%d')
            random_str = ''.join(random.choices(string.digits, k=4))
            self.order_number = f"ORD-{date_str}-{random_str}"
            
            # Ensure unique
            while Order.objects.filter(order_number=self.order_number).exists():
                random_str = ''.join(random.choices(string.digits, k=4))
                self.order_number = f"ORD-{date_str}-{random_str}"
        
        super().save(*args, **kwargs)
    
    @property
    def total_items(self):
        """Total items in order"""
        return self.items.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0
    
    def mark_as_paid(self, payment_id=None):
        """Mark order as paid"""
        from django.utils import timezone
        self.payment_status = 'paid'
        self.paid_at = timezone.now()
        if payment_id:
            self.payment_id = payment_id
        self.save(update_fields=['payment_status', 'paid_at', 'payment_id'])


class OrderItem(models.Model):
    """
    Individual product in order
    """
    
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        help_text='Null if product deleted'
    )
    
    # Snapshot of product at time of order
    product_name = models.CharField(max_length=255)
    product_brand = models.CharField(max_length=255)
    product_image = models.ImageField(upload_to='order_items/', blank=True)
    
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Price at time of order'
    )
    
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='unit_price * quantity'
    )
    
    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'
    
    def __str__(self):
        return f"{self.quantity}x {self.product_name}"
    
    def save(self, *args, **kwargs):
        # Calculate total
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)