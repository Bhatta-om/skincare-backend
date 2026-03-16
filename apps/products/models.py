# apps/products/models.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.utils import generate_unique_filename

class Category(models.Model):
    """
    Product Categories
    Examples: Moisturizer, Sunscreen, Serum, Cleanser, Toner
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to='categories/',
        blank=True,
        null=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-generate slug from name
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """
    Skincare Products
    
    AI Recommendation ko lagi important fields:
    - suitable_skin_type
    - min_age / max_age
    - gender
    - skin_concern
    """
    
    # ════════════════════════════════════════════════════════════
    # CHOICES
    # ════════════════════════════════════════════════════════════
    
    SKIN_TYPES = (
        ('normal', 'Normal'),
        ('dry', 'Dry'),
        ('oily', 'Oily'),
        ('combination', 'Combination'),
        ('sensitive', 'Sensitive'),
        ('all', 'All Skin Types'),
    )
    
    GENDER_CHOICES = (
        ('male', 'Male'),
        ('female', 'Female'),
        ('unisex', 'Unisex'),
    )
    
    CONCERN_CHOICES = (
        ('acne', 'Acne & Blemishes'),
        ('aging', 'Anti-Aging & Wrinkles'),
        ('brightening', 'Brightening & Glow'),
        ('hydration', 'Hydration & Moisture'),
        ('pigmentation', 'Dark Spots & Pigmentation'),
        ('sensitivity', 'Redness & Sensitivity'),
        ('general', 'General Skincare'),
    )
    
    # ════════════════════════════════════════════════════════════
    # BASIC INFO
    # ════════════════════════════════════════════════════════════
    
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True)
    brand = models.CharField(max_length=255, db_index=True)
    
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    
    description = models.TextField()
    ingredients = models.TextField(
        blank=True,
        help_text='Comma-separated list of ingredients'
    )
    
    # ════════════════════════════════════════════════════════════
    # PRICING
    # ════════════════════════════════════════════════════════════
    
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Discount percentage (0-100)'
    )
    
    # ════════════════════════════════════════════════════════════
    # AI MATCHING FIELDS (CRITICAL!)
    # ════════════════════════════════════════════════════════════
    
    suitable_skin_type = models.CharField(
        max_length=20,
        choices=SKIN_TYPES,
        db_index=True,
        help_text='AI le yesबाट match garcha'
    )
    
    skin_concern = models.CharField(
        max_length=20,
        choices=CONCERN_CHOICES,
        default='general',
        db_index=True
    )
    
    min_age = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text='Minimum recommended age'
    )
    
    max_age = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text='Maximum recommended age'
    )
    
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        default='unisex',
        db_index=True
    )
    
    # ════════════════════════════════════════════════════════════
    # IMAGES
    # ════════════════════════════════════════════════════════════
    
    image = models.ImageField(
        upload_to=generate_unique_filename,
        help_text='Main product image'
    )
    
    image_2 = models.ImageField(
        upload_to=generate_unique_filename,
        blank=True,
        null=True
    )
    
    image_3 = models.ImageField(
        upload_to=generate_unique_filename,
        blank=True,
        null=True
    )
    
    # ════════════════════════════════════════════════════════════
    # INVENTORY
    # ════════════════════════════════════════════════════════════
    
    stock = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True, db_index=True)
    low_stock_threshold = models.PositiveIntegerField(
        default=10,
        help_text='Stock yo bhandaa kam bhayo bhane alert'
    )
    
    # ════════════════════════════════════════════════════════════
    # METADATA
    # ════════════════════════════════════════════════════════════
    
    is_featured = models.BooleanField(
        default=False,
        help_text='Homepage ma featured product'
    )
    
    views_count = models.PositiveIntegerField(
        default=0,
        help_text='Kati jana le heryo'
    )
    
    # ════════════════════════════════════════════════════════════
    # TIMESTAMPS
    # ════════════════════════════════════════════════════════════
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ════════════════════════════════════════════════════════════
    # META & METHODS
    # ════════════════════════════════════════════════════════════
    
    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['-created_at']
        
        indexes = [
            models.Index(fields=['suitable_skin_type']),
            models.Index(fields=['gender']),
            models.Index(fields=['skin_concern']),
            models.Index(fields=['min_age', 'max_age']),
            models.Index(fields=['is_available']),
            models.Index(fields=['brand']),
            models.Index(fields=['price']),
        ]
    
    def __str__(self):
        return f"{self.brand} - {self.name}"
    
    def save(self, *args, **kwargs):
        # Auto-generate slug
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(f"{self.brand}-{self.name}")
            self.slug = base_slug
            
            # Ensure unique slug
            counter = 1
            while Product.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        
        # Auto update is_available
        if self.stock == 0:
            self.is_available = False
        elif self.stock > 0 and not self.is_available:
            self.is_available = True
        
        super().save(*args, **kwargs)
    
    @property
    def discounted_price(self):
        """Discount lagayeko price"""
        if self.discount_percent > 0:
            discount_amount = self.price * (self.discount_percent / 100)
            return self.price - discount_amount
        return self.price
    
    @property
    def is_low_stock(self):
        """Stock kam cha ki nai"""
        return 0 < self.stock <= self.low_stock_threshold
    
    @property
    def stock_status(self):
        """Human-readable stock status"""
        if self.stock == 0:
            return 'Out of Stock'
        elif self.is_low_stock:
            return f'Low Stock ({self.stock} left)'
        else:
            return 'In Stock'
    
    def increment_views(self):
        """View count badhau"""
        self.views_count += 1
        self.save(update_fields=['views_count'])
        
class Review(models.Model):
    """Product Reviews & Ratings"""
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user       = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='reviews')
    rating     = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'user')  # One review per user per product
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.product.name} ({self.rating}★)"
    

class Wishlist(models.Model):
    """
    User Wishlist — Industry Standard
    - One wishlist per user
    - Many products per wishlist
    - unique_together ensures no duplicates
    """
    user    = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='wishlist_items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='wishlisted_by'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')  # No duplicates
        ordering        = ['-added_at']

    def __str__(self):
        return f"{self.user.email} → {self.product.name}"