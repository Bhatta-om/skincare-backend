# apps/users/managers.py

from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

class CustomUserManager(BaseUserManager):
    """
    Custom User Manager for email-based authentication
    """
    
    def email_validator(self, email):
        """Email validation"""
        try:
            validate_email(email)
        except ValidationError:
            raise ValueError("Invalid email address!")
    
    def create_user(self, email, password=None, **extra_fields):
        """
        Normal user create garcha
        
        Usage:
        User.objects.create_user(
            email='user@example.com',
            password='password123',
            first_name='John'
        )
        """
        if not email:
            raise ValueError("Email address is required!")
        
        # Validate email
        self.email_validator(email)
        
        # Normalize email (lowercase domain)
        email = self.normalize_email(email)
        
        # Create user instance
        user = self.model(email=email, **extra_fields)
        
        # Set password (hashed)
        user.set_password(password)
        
        # Save to database
        user.save(using=self._db)
        
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """
        Admin user create garcha
        
        Usage:
        python manage.py createsuperuser
        """
        # Set admin flags
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        
        # Validation
        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True")
        
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True")
        
        # Create user
        return self.create_user(email, password, **extra_fields)