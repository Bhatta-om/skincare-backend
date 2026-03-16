# apps/users/views.py — FULL CLEAN FILE

import logging
from rest_framework import status, generics, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model, authenticate

from .models import OTP, SearchHistory
from .emails import send_otp_email, send_welcome_email
from .serializers import (
    RegisterSerializer,
    UserSerializer,
    ChangePasswordSerializer,
    ProfileUpdateSerializer,
)

logger = logging.getLogger(__name__)
User   = get_user_model()


# ════════════════════════════════════════════════════════════
# REGISTRATION
# ════════════════════════════════════════════════════════════

class RegisterView(generics.CreateAPIView):
    serializer_class       = RegisterSerializer
    authentication_classes = []
    permission_classes     = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        otp  = OTP.generate_for_user(user)
        if not send_otp_email(user, otp.code):
            logger.error("OTP email failed for %s", user.email)
        return Response({
            'success': True,
            'message': 'Registration successful! Please check your email for the OTP.',
            'email':   user.email,
        }, status=201)


# ════════════════════════════════════════════════════════════
# OTP VERIFY
# ════════════════════════════════════════════════════════════

class VerifyOTPView(APIView):
    authentication_classes = []
    permission_classes     = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        code  = request.data.get('otp', '').strip()

        if not email or not code:
            return Response({'success': False, 'error': 'Email and OTP are required.'}, status=400)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)

        if user.is_verified:
            return Response({'success': False, 'error': 'Email already verified. Please login.'}, status=400)

        otp = OTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
        if not otp:
            return Response({'success': False, 'error': 'No OTP found. Please request a new one.'}, status=400)
        if otp.is_expired:
            return Response({'success': False, 'error': 'OTP has expired. Please request a new one.'}, status=400)

        otp.attempts += 1
        otp.save()

        if otp.attempts > 3:
            return Response({'success': False, 'error': 'Too many attempts. Please request a new OTP.'}, status=400)
        if otp.code != code:
            remaining = 3 - otp.attempts
            return Response({'success': False, 'error': f'Invalid OTP. {remaining} attempts remaining.'}, status=400)

        otp.is_used = True
        otp.save()
        user.is_verified = True
        user.save(update_fields=['is_verified'])
        send_welcome_email(user)

        refresh = RefreshToken.for_user(user)
        logger.info("Email verified for %s", user.email)
        return Response({
            'success': True,
            'message': 'Email verified successfully!',
            'user':    UserSerializer(user).data,
            'tokens':  {'access': str(refresh.access_token), 'refresh': str(refresh)},
        })


# ════════════════════════════════════════════════════════════
# RESEND OTP
# ════════════════════════════════════════════════════════════

class ResendOTPView(APIView):
    authentication_classes = []
    permission_classes     = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'success': False, 'error': 'Email is required.'}, status=400)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)
        if user.is_verified:
            return Response({'success': False, 'error': 'Email already verified.'}, status=400)
        otp = OTP.generate_for_user(user)
        send_otp_email(user, otp.code)
        return Response({'success': True, 'message': 'New OTP sent! Please check your email.'})


# ════════════════════════════════════════════════════════════
# LOGIN  ✅ Rate Limited
# ════════════════════════════════════════════════════════════

class LoginView(APIView):
    authentication_classes = []
    permission_classes     = [permissions.AllowAny]

    def post(self, request):
        from django.core.cache import cache
        ip       = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')
        key      = f'login_attempts_{ip}'
        attempts = cache.get(key, 0)

        if attempts >= 10:
            return Response({
                'success': False,
                'error':   'Too many login attempts. Please try again after 5 minutes.'
            }, status=429)

        email    = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response({'success': False, 'error': 'Email and password are required.'}, status=400)

        user = authenticate(request, username=email, password=password)

        if user is None:
            cache.set(key, attempts + 1, timeout=300)
            remaining = 10 - (attempts + 1)
            return Response({
                'success': False,
                'error':   f'Invalid email or password. {remaining} attempts remaining.'
            }, status=401)

        cache.delete(key)

        if not user.is_active:
            return Response({'success': False, 'error': 'Your account has been disabled.'}, status=403)
        if not user.is_verified:
            return Response({
                'success': False,
                'error':   'email_not_verified',
                'message': 'Please verify your email before logging in.',
                'email':   email,
            }, status=403)

        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Login successful!',
            'user':    UserSerializer(user).data,
            'tokens':  {'access': str(refresh.access_token), 'refresh': str(refresh)},
        })


# ════════════════════════════════════════════════════════════
# PROFILE
# ════════════════════════════════════════════════════════════

class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class   = ProfileUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        return Response(UserSerializer(request.user).data)

    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        instance   = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'success': True,
            'message': 'Profile updated successfully!',
            'user':    UserSerializer(instance).data,
        })


# ════════════════════════════════════════════════════════════
# CHANGE PASSWORD  ✅ Rate Limited + History + JWT Blacklist
# ════════════════════════════════════════════════════════════

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.core.cache import cache
        key      = f'change_password_{request.user.id}'
        attempts = cache.get(key, 0)

        if attempts >= 5:
            return Response({
                'success': False,
                'error':   'Too many password change attempts. Please try again after 1 hour.'
            }, status=429)

        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            cache.set(key, attempts + 1, timeout=3600)
            errors    = serializer.errors
            first_val = next(iter(errors.values()))
            msg = first_val[0] if isinstance(first_val, list) else str(first_val)
            return Response({'success': False, 'error': msg}, status=400)

        user = request.user

        from .models import PasswordHistory
        PasswordHistory.add(user, hashed_password=user.password)

        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        cache.delete(key)

        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            for token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            pass

        ip = (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', 'Unknown')
        )
        ua = request.META.get('HTTP_USER_AGENT', '')
        if 'Mobile' in ua:    device = 'Mobile Browser'
        elif 'Windows' in ua: device = 'Windows PC'
        elif 'Mac' in ua:     device = 'Mac / MacBook'
        elif 'Linux' in ua:   device = 'Linux PC'
        else:                 device = 'Unknown Device'

        from .emails import send_password_changed_email
        send_password_changed_email(user, ip_address=ip, device=device)
        logger.info("Password changed for %s from IP %s", user.email, ip)

        return Response({
            'success': True,
            'message': 'Password changed successfully! Please login again.',
        })


# ════════════════════════════════════════════════════════════
# LOGOUT
# ════════════════════════════════════════════════════════════

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'success': False, 'error': 'Refresh token is required.'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({'success': False, 'error': 'Invalid or already expired token.'}, status=400)
        return Response({'success': True, 'message': 'Logout successful!'})


# ════════════════════════════════════════════════════════════
# FORGOT PASSWORD — Step 1: Send OTP
# ════════════════════════════════════════════════════════════

class ForgotPasswordView(APIView):
    authentication_classes = []
    permission_classes     = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'success': False, 'error': 'Email is required.'}, status=400)
        try:
            user = User.objects.get(email=email)
            otp  = OTP.generate_for_user(user)
            send_otp_email(user, otp.code)
            logger.info("Password reset OTP sent to %s", email)
        except User.DoesNotExist:
            pass  # Security: don't reveal if email exists
        return Response({'success': True, 'message': 'If this email exists, an OTP has been sent.'})


# ════════════════════════════════════════════════════════════
# FORGOT PASSWORD — Step 2: Verify OTP
# ════════════════════════════════════════════════════════════

class VerifyForgotPasswordOTPView(APIView):
    authentication_classes = []
    permission_classes     = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        code  = request.data.get('otp', '').strip()

        if not email or not code:
            return Response({'success': False, 'error': 'Email and OTP are required.'}, status=400)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'User not found.'}, status=404)

        otp = OTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
        if not otp:
            return Response({'success': False, 'error': 'No OTP found. Please request a new one.'}, status=400)
        if otp.is_expired:
            return Response({'success': False, 'error': 'OTP has expired. Please request a new one.'}, status=400)

        otp.attempts += 1
        otp.save()

        if otp.attempts > 3:
            return Response({'success': False, 'error': 'Too many attempts. Please request a new OTP.'}, status=400)
        if otp.code != code:
            remaining = 3 - otp.attempts
            return Response({'success': False, 'error': f'Invalid OTP. {remaining} attempts remaining.'}, status=400)

        otp.is_used = True
        otp.save()

        from rest_framework_simplejwt.tokens import AccessToken
        from datetime import timedelta
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=timedelta(minutes=15))

        return Response({
            'success':     True,
            'message':     'OTP verified! You can now reset your password.',
            'reset_token': str(token),
        })


# ════════════════════════════════════════════════════════════
# FORGOT PASSWORD — Step 3: Reset Password
# ════════════════════════════════════════════════════════════

class ResetPasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_password     = request.data.get('new_password', '')
        confirm_password = request.data.get('confirm_password', '')

        if not new_password or not confirm_password:
            return Response({'success': False, 'error': 'Both password fields are required.'}, status=400)
        if new_password != confirm_password:
            return Response({'success': False, 'error': 'Passwords do not match.'}, status=400)
        if len(new_password) < 8:
            return Response({'success': False, 'error': 'Password must be at least 8 characters.'}, status=400)

        user = request.user
        user.set_password(new_password)
        user.save(update_fields=['password'])
        logger.info("Password reset successful for %s", user.email)

        return Response({
            'success': True,
            'message': 'Password reset successfully! Please login with your new password.',
        })


# ════════════════════════════════════════════════════════════
# SEARCH HISTORY  ✅ Backend-persisted
# ════════════════════════════════════════════════════════════

class SearchHistoryView(APIView):
    """
    GET    /api/users/search-history/        — last 10 searches
    POST   /api/users/search-history/        — save a search
    DELETE /api/users/search-history/        — clear all
    DELETE /api/users/search-history/?q=wow  — remove one
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        history = (
            SearchHistory.objects
            .filter(user=request.user)
            .values_list('query', flat=True)
            .distinct()[:10]
        )
        return Response({'history': list(history)})

    def post(self, request):
        query = request.data.get('query', '').strip()
        if not query or len(query) < 3:
            return Response({'success': False, 'error': 'Query too short.'}, status=400)

        # Remove duplicate then re-insert at top
        SearchHistory.objects.filter(user=request.user, query__iexact=query).delete()
        SearchHistory.objects.create(user=request.user, query=query)

        # Keep only last 10
        ids_to_keep = list(
            SearchHistory.objects
            .filter(user=request.user)
            .order_by('-created_at')
            .values_list('id', flat=True)[:10]
        )
        SearchHistory.objects.filter(user=request.user).exclude(id__in=ids_to_keep).delete()

        return Response({'success': True})

    def delete(self, request):
        query = request.query_params.get('q', '').strip()
        if query:
            SearchHistory.objects.filter(user=request.user, query__iexact=query).delete()
            return Response({'success': True, 'message': f'Removed "{query}" from history.'})
        SearchHistory.objects.filter(user=request.user).delete()
        return Response({'success': True, 'message': 'Search history cleared.'})