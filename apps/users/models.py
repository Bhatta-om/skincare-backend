# apps/users/models.py
import uuid
import random
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta
from .managers import CustomUserManager
from django.conf import settings



class User(AbstractUser):
    """
    Custom User Model
    - Email as primary login identifier
    - Username auto-generated, optional
    - Phone, verification status, timestamps
    """
    email = models.EmailField(
        unique=True,
        verbose_name='Email Address',
    )
    username = models.CharField(
        max_length=150,
        unique=True,
        blank=True,
        null=True,
    )
    phone = models.CharField(
        max_length=15,
        blank=True,
        verbose_name='Phone Number',
    )
    is_verified = models.BooleanField(
        default=False,
        help_text='Has the user verified their email?'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_verified']),
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if not self.username:
            base = self.email.split('@')[0]
            candidate = base
            qs = User.objects.exclude(pk=self.pk)
            counter = 1
            while qs.filter(username=candidate).exists():
                candidate = f"{base}_{uuid.uuid4().hex[:6]}"
                counter += 1
            self.username = candidate
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]


# ════════════════════════════════════════════════════════════
# OTP MODEL
# ════════════════════════════════════════════════════════════

class OTP(models.Model):
    """
    6-digit OTP for email verification
    - Expires in 10 minutes
    - Max 3 attempts
    - Auto-deleted after use
    """
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used    = models.BooleanField(default=False)
    attempts   = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'OTP'
        verbose_name_plural = 'OTPs'
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.user.email} — {self.code}"

    def save(self, *args, **kwargs):
        # Auto-generate 6 digit OTP
        if not self.code:
            self.code = str(random.randint(100000, 999999))
        # Set expiry to 10 minutes from now
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired and self.attempts < 3

    @classmethod
    def generate_for_user(cls, user):
        """Delete old OTPs and create new one"""
        cls.objects.filter(user=user, is_used=False).delete()
        return cls.objects.create(user=user)

class PasswordHistory(models.Model):
    """
    Stores hashed history of last N passwords per user.
    Prevents reuse of recent passwords — industry standard.
    """
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_history'
    )
    password   = models.CharField(max_length=255, help_text='Hashed password')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — {self.created_at:%Y-%m-%d}"

    @classmethod
    def add(cls, user, raw_password=None, hashed_password=None):
        """Save current password to history, keep last 5 only."""
        from django.contrib.auth.hashers import make_password
        pwd = hashed_password or make_password(raw_password)
        cls.objects.create(user=user, password=pwd)
        # Keep only last 5
        old_ids = cls.objects.filter(user=user).order_by('-created_at').values_list('id', flat=True)[5:]
        cls.objects.filter(id__in=list(old_ids)).delete()

    @classmethod
    def is_reused(cls, user, raw_password, limit=3):
        """Check if raw_password matches any of last `limit` passwords."""
        from django.contrib.auth.hashers import check_password
        recent = cls.objects.filter(user=user).order_by('-created_at')[:limit]
        return any(check_password(raw_password, h.password) for h in recent)
    
class SearchHistory(models.Model):
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='search_history')
    query      = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Search Histories'

    def __str__(self):
        return f"{self.user.email} → {self.query}"