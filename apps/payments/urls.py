# apps/payments/urls.py

from django.urls import path
from .views import (
    KhaltiInitiateView,
    KhaltiVerifyView,
    EsewaInitiateView,
    EsewaVerifyView,
    PaymentStatusView,
)

app_name = 'payments'

urlpatterns = [
    # Khalti
    path('khalti/initiate/', KhaltiInitiateView.as_view(), name='khalti_initiate'),
    path('khalti/verify/',   KhaltiVerifyView.as_view(),   name='khalti_verify'),

    # eSewa
    path('esewa/initiate/',  EsewaInitiateView.as_view(),  name='esewa_initiate'),
    path('esewa/verify/',    EsewaVerifyView.as_view(),     name='esewa_verify'),

    # Status
    path('<int:pk>/status/', PaymentStatusView.as_view(),  name='payment_status'),
]