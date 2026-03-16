# apps/users/serializers.py — FULL FILE (replace गर्नुस्)

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


# ════════════════════════════════════════════════════════════
# USER SERIALIZER
# ════════════════════════════════════════════════════════════

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'full_name', 'phone', 'is_verified', 'is_staff', 'is_superuser', 'created_at',
        ]
        read_only_fields = ['id', 'is_verified', 'is_staff', 'is_superuser', 'created_at']


# ════════════════════════════════════════════════════════════
# REGISTRATION SERIALIZER
# ════════════════════════════════════════════════════════════

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True,
        validators=[validate_password], style={'input_type': 'password'}
    )
    confirm_password = serializers.CharField(
        write_only=True, required=True, style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['email', 'password', 'confirm_password', 'first_name', 'last_name', 'phone']
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name':  {'required': True},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords didn't match!"})
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(**validated_data)
        # ✅ Save initial password to history
        from .models import PasswordHistory
        PasswordHistory.add(user, hashed_password=user.password)
        return user


# ════════════════════════════════════════════════════════════
# LOGIN SERIALIZER
# ════════════════════════════════════════════════════════════

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})


# ════════════════════════════════════════════════════════════
# CHANGE PASSWORD SERIALIZER  ✅ FULL INDUSTRY STANDARD
# ════════════════════════════════════════════════════════════

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        required=True, write_only=True,
        validators=[validate_password], style={'input_type': 'password'}
    )
    confirm_new_password = serializers.CharField(
        required=True, write_only=True, style={'input_type': 'password'}
    )

    def validate_old_password(self, value):
        """✅ Current password correct छ कि छैन"""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect!")
        return value

    def validate(self, attrs):
        # ✅ New passwords must match
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({
                "confirm_new_password": "New passwords do not match!"
            })

        # ✅ New password must differ from current password
        if attrs['new_password'] == attrs['old_password']:
            raise serializers.ValidationError({
                "new_password": "New password cannot be the same as your current password!"
            })

        # ✅ INDUSTRY STANDARD: Password history check (last 3)
        from .models import PasswordHistory
        user = self.context['request'].user
        if PasswordHistory.is_reused(user, attrs['new_password'], limit=3):
            raise serializers.ValidationError({
                "new_password": "You cannot reuse any of your last 3 passwords. Please choose a different password."
            })

        return attrs


# ════════════════════════════════════════════════════════════
# PROFILE UPDATE SERIALIZER
# ════════════════════════════════════════════════════════════

class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'phone']

    def validate_phone(self, value):
        if value and not value.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits!")
        if value and (len(value) < 10 or len(value) > 15):
            raise serializers.ValidationError("Phone number must be 10-15 digits!")
        return value