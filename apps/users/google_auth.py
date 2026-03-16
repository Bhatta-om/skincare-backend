# apps/users/google_auth.py

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db import IntegrityError
import requests as http_requests

logger = logging.getLogger(__name__)
User = get_user_model()


class GoogleSignInView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token      = request.data.get('token')
        email      = request.data.get('email', '').strip().lower()
        first_name = request.data.get('first_name', '')
        last_name  = request.data.get('last_name', '')

        if not token:
            return Response({
                'success': False,
                'error': 'Google token is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ If email not provided, fetch from Google using access_token
        if not email:
            try:
                user_info = self._get_google_user_info(token)
                email      = user_info.get('email', '').strip().lower()
                first_name = user_info.get('given_name', '')
                last_name  = user_info.get('family_name', '')
            except Exception as e:
                logger.warning("Failed to get Google user info: %s", str(e))
                return Response({
                    'success': False,
                    'error': 'Invalid or expired Google token.'
                }, status=status.HTTP_400_BAD_REQUEST)

        if not email:
            return Response({
                'success': False,
                'error': 'Email not available in Google account.'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user, is_new_user = self._get_or_create_user(email, first_name, last_name)
        except Exception as e:
            logger.error("User creation failed for %s: %s", email, str(e))
            return Response({
                'success': False,
                'error': 'Failed to authenticate. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not is_new_user:
            self._update_existing_user(user, first_name, last_name)

        refresh = RefreshToken.for_user(user)

        return Response({
            'success': True,
            'message': 'Account created successfully!' if is_new_user else 'Login successful!',
            'is_new_user': is_new_user,
            'user': {
                'id':         user.id,
                'email':      user.email,
                'first_name': user.first_name,
                'last_name':  user.last_name,
                'is_verified': user.is_verified,
            },
            'tokens': {
                'access':  str(refresh.access_token),
                'refresh': str(refresh),
            },
        }, status=status.HTTP_200_OK)

    def _get_google_user_info(self, access_token: str) -> dict:
        """Fetch user info from Google using access_token"""
        response = http_requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    def _get_or_create_user(self, email, first_name, last_name):
        defaults = {
            'first_name':  first_name,
            'last_name':   last_name,
            'is_verified': True,
        }
        try:
            user, created = User.objects.get_or_create(email=email, defaults=defaults)
        except IntegrityError:
            user    = User.objects.get(email=email)
            created = False
        return user, created

    def _update_existing_user(self, user, first_name, last_name):
        updated_fields = []
        if not user.first_name and first_name:
            user.first_name = first_name
            updated_fields.append('first_name')
        if not user.last_name and last_name:
            user.last_name = last_name
            updated_fields.append('last_name')
        if not user.is_verified:
            user.is_verified = True
            updated_fields.append('is_verified')
        if updated_fields:
            user.save(update_fields=updated_fields)