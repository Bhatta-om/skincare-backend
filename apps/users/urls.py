# apps/users/urls.py

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .google_auth import GoogleSignInView
from .views import (
    RegisterView,
    LoginView,
    ProfileView,
    ChangePasswordView,
    LogoutView,
    VerifyOTPView,
    ResendOTPView,
    ForgotPasswordView,
    VerifyForgotPasswordOTPView,
    ResetPasswordView,
    SearchHistoryView,
)

app_name = 'users'

urlpatterns = [
    # Auth
    path('register/',        RegisterView.as_view(),       name='register'),
    path('login/',           LoginView.as_view(),          name='login'),
    path('token/refresh/',   TokenRefreshView.as_view(),   name='token_refresh'),
    path('logout/',          LogoutView.as_view(),         name='logout'),
    path('google/',          GoogleSignInView.as_view(),   name='google_signin'),

    # Profile
    path('profile/',         ProfileView.as_view(),        name='profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),

    # OTP
    path('verify-otp/',      VerifyOTPView.as_view(),      name='verify_otp'),
    path('resend-otp/',      ResendOTPView.as_view(),      name='resend_otp'),

    # Forgot Password
    path('forgot-password/',            ForgotPasswordView.as_view(),          name='forgot_password'),
    path('forgot-password/verify-otp/', VerifyForgotPasswordOTPView.as_view(), name='forgot_password_verify'),
    path('reset-password/',             ResetPasswordView.as_view(),           name='reset_password'),

    # ✅ Search History
    path('search-history/', SearchHistoryView.as_view(), name='search_history'),
]