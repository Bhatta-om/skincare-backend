# apps/users/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model

# ── Custom Admin Title ─────────────────────────────────────
admin.site.site_header = 'Skincare App Administration'
admin.site.site_title  = 'Skincare Admin'
admin.site.index_title = 'Dashboard Overview'

User = get_user_model()

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom User Admin"""
    
    list_display = [
        'email',
        'username',
        'first_name',
        'last_name',
        'phone',
        'is_verified',
        'is_staff',
        'created_at',
    ]
    
    list_filter = [
        'is_staff',
        'is_superuser',
        'is_active',
        'is_verified',
        'created_at',
    ]
    
    search_fields = ['email', 'username', 'first_name', 'last_name', 'phone']
    
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_superuser'),
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at', 'last_login']