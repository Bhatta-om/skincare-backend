# apps/payments/views.py

import requests
import logging
import base64
import json
import hashlib
import hmac

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.conf import settings

from apps.orders.models import Order
from .models import Payment
from .serializers import (
    PaymentSerializer,
    KhaltiInitiateSerializer,
    KhaltiVerifySerializer,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# INITIATE KHALTI PAYMENT
# ════════════════════════════════════════════════════════════

class KhaltiInitiateView(APIView):
    """
    POST /api/payments/khalti/initiate/
    Khalti payment initiate garcha.
    Login required.

    Request:
    {
        "order_id": 4,
        "return_url": "http://localhost:3000/payment/success"
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = KhaltiInitiateSerializer(data=request.data)

        if not serializer.is_valid():
            return Response({
                'success': False,
                'error':   serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        order_id = serializer.validated_data['order_id']

        try:
            order = Order.objects.get(id=order_id, user=request.user)

            if order.payment_status == 'paid':
                return Response({
                    'success': False,
                    'error':   'Order already paid!'
                }, status=status.HTTP_400_BAD_REQUEST)

            amount_in_paisa = int(order.total_amount * 100)

            return_url = serializer.validated_data.get(
                'return_url',
                settings.KHALTI_RETURN_URL
            )

            khalti_payload = {
                "return_url":          return_url,
                "website_url":         settings.KHALTI_WEBSITE_URL,
                "amount":              amount_in_paisa,
                "purchase_order_id":   str(order.order_number),
                "purchase_order_name": f"Order #{order.order_number}",
                "customer_info": {
                    "name":  order.full_name,
                    "email": order.email,
                    "phone": order.phone,
                }
            }

            khalti_headers = {
                "Authorization": f"Key {settings.KHALTI_SECRET_KEY}",
                "Content-Type":  "application/json",
            }

            response = requests.post(
                "https://a.khalti.com/api/v2/epayment/initiate/",
                json=khalti_payload,
                headers=khalti_headers
            )
            response_data = response.json()

            if response.status_code == 200:
                pidx        = response_data.get('pidx')
                payment_url = response_data.get('payment_url')

                payment, _ = Payment.objects.update_or_create(
                    order=order,
                    defaults={
                        'payment_method': 'khalti',
                        'amount':         order.total_amount,
                        'status':         'initiated',
                        'khalti_idx':     pidx,
                    }
                )

                return Response({
                    'success':      True,
                    'message':      'Khalti payment initiated!',
                    'payment_id':   payment.id,
                    'pidx':         pidx,
                    'payment_url':  payment_url,
                    'amount':       amount_in_paisa,
                    'order_number': order.order_number,
                }, status=status.HTTP_200_OK)

            else:
                return Response({
                    'success': False,
                    'error':   response_data.get('detail', 'Khalti initiation failed!')
                }, status=status.HTTP_400_BAD_REQUEST)

        except Order.DoesNotExist:
            return Response({
                'success': False,
                'error':   'Order not found!'
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error("Khalti initiate error: %s", str(e))
            return Response({
                'success': False,
                'error':   f'Payment initiation failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ════════════════════════════════════════════════════════════
# VERIFY KHALTI PAYMENT
# ════════════════════════════════════════════════════════════

class KhaltiVerifyView(APIView):
    """
    POST /api/payments/khalti/verify/
    Khalti payment verify garcha.
    Login required.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = KhaltiVerifySerializer(data=request.data)

        if not serializer.is_valid():
            return Response({
                'success': False,
                'error':   serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        pidx     = serializer.validated_data['pidx']
        order_id = serializer.validated_data['order_id']

        try:
            order = Order.objects.get(id=order_id, user=request.user)

            if order.payment_status == 'paid':
                return Response({
                    'success': False,
                    'error':   'Order already paid!'
                }, status=status.HTTP_400_BAD_REQUEST)

            khalti_headers = {
                "Authorization": f"Key {settings.KHALTI_SECRET_KEY}",
                "Content-Type":  "application/json",
            }

            response = requests.post(
                "https://a.khalti.com/api/v2/epayment/lookup/",
                json={"pidx": pidx},
                headers=khalti_headers
            )
            response_data = response.json()

            if response.status_code == 200:
                payment_status = response_data.get('status')

                if payment_status == 'Completed':
                    transaction_id = response_data.get('transaction_id')

                    try:
                        payment = Payment.objects.get(order=order)
                    except Payment.DoesNotExist:
                        payment = Payment.objects.create(
                            order          = order,
                            payment_method = 'khalti',
                            amount         = order.total_amount,
                            status         = 'initiated',
                        )

                    payment.mark_as_completed(
                        transaction_id=transaction_id,
                        response_data=response_data
                    )

                    return Response({
                        'success':      True,
                        'message':      'Payment verified successfully!',
                        'payment':      PaymentSerializer(payment).data,
                        'order_number': order.order_number,
                        'order_status': order.status,
                    }, status=status.HTTP_200_OK)

                elif payment_status == 'Pending':
                    return Response({
                        'success': False,
                        'error':   'Payment is still pending.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                else:
                    return Response({
                        'success': False,
                        'error':   f'Payment {payment_status}. Please try again.'
                    }, status=status.HTTP_400_BAD_REQUEST)

            else:
                return Response({
                    'success': False,
                    'error':   response_data.get('detail', 'Payment verification failed!')
                }, status=status.HTTP_400_BAD_REQUEST)

        except Order.DoesNotExist:
            return Response({
                'success': False,
                'error':   'Order not found!'
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error("Khalti verify error: %s", str(e))
            return Response({
                'success': False,
                'error':   f'Verification failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ════════════════════════════════════════════════════════════
# PAYMENT STATUS
# ════════════════════════════════════════════════════════════

class PaymentStatusView(APIView):
    """
    GET /api/payments/<pk>/status/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            payment = Payment.objects.get(pk=pk, order__user=request.user)
            return Response({
                'success': True,
                'payment': PaymentSerializer(payment).data
            })

        except Payment.DoesNotExist:
            return Response({
                'success': False,
                'error':   'Payment not found!'
            }, status=status.HTTP_404_NOT_FOUND)


# ════════════════════════════════════════════════════════════
# ESEWA INITIATE PAYMENT
# ════════════════════════════════════════════════════════════

class EsewaInitiateView(APIView):
    """
    POST /api/payments/esewa/initiate/
    eSewa payment initiate garcha.
    Login required.

    Request:
    {
        "order_id": 5
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get('order_id')

        if not order_id:
            return Response({
                'success': False,
                'error':   'order_id required!'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = Order.objects.get(id=order_id, user=request.user)

            if order.payment_status == 'paid':
                return Response({
                    'success': False,
                    'error':   'Order already paid!'
                }, status=status.HTTP_400_BAD_REQUEST)

            product_code     = settings.ESEWA_PRODUCT_CODE
            secret_key       = settings.ESEWA_SECRET_KEY
            esewa_url        = settings.ESEWA_PAYMENT_URL
            success_url      = settings.ESEWA_SUCCESS_URL
            failure_url      = settings.ESEWA_FAILURE_URL

            amount           = str(order.total_amount)
            total_amount     = amount
            transaction_uuid = f"{order.order_number}-{order.id}"

            # ── HMAC Signature ─────────────────────────────────────────────────
            # Initiate: total_amount,transaction_uuid,product_code
            message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"

            h = hmac.new(
                key=secret_key.encode('utf-8'),
                msg=message.encode('utf-8'),
                digestmod=hashlib.sha256
            )
            signature = base64.b64encode(h.digest()).decode('utf-8')
            # ──────────────────────────────────────────────────────────────────

            form_data = {
                "amount":                  amount,
                "tax_amount":              "0",
                "total_amount":            total_amount,
                "transaction_uuid":        transaction_uuid,
                "product_code":            product_code,
                "product_service_charge":  "0",
                "product_delivery_charge": "0",
                "success_url":             success_url,
                "failure_url":             failure_url,
                "signed_field_names":      "total_amount,transaction_uuid,product_code",
                "signature":               signature,
            }

            payment, _ = Payment.objects.update_or_create(
                order=order,
                defaults={
                    'payment_method':         'esewa',
                    'amount':                 order.total_amount,
                    'status':                 'initiated',
                    'esewa_transaction_uuid': transaction_uuid,
                }
            )

            logger.info("eSewa initiated for order %s", order.order_number)

            return Response({
                'success':      True,
                'message':      'eSewa payment initiated!',
                'payment_id':   payment.id,
                'form_data':    form_data,
                'esewa_url':    esewa_url,
                'order_number': order.order_number,
            }, status=status.HTTP_200_OK)

        except Order.DoesNotExist:
            return Response({
                'success': False,
                'error':   'Order not found!'
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error("eSewa initiate error: %s", str(e))
            return Response({
                'success': False,
                'error':   str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ════════════════════════════════════════════════════════════
# ESEWA VERIFY PAYMENT
# ════════════════════════════════════════════════════════════

class EsewaVerifyView(APIView):
    """
    POST /api/payments/esewa/verify/
    eSewa payment verify garcha.
    Login required.

    Request:
    {
        "data": "base64_encoded_response_from_esewa",
        "order_id": 5
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        encoded_data = request.data.get('data')
        order_id     = request.data.get('order_id')

        if not encoded_data or not order_id:
            return Response({
                'success': False,
                'error':   'data and order_id required!'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = Order.objects.get(id=order_id, user=request.user)

            if order.payment_status == 'paid':
                return Response({
                    'success': False,
                    'error':   'Order already paid!'
                }, status=status.HTTP_400_BAD_REQUEST)

            # ── Decode eSewa response ──────────────────────────────────────────
            try:
                clean_data = encoded_data.strip()
                missing_padding = len(clean_data) % 4
                if missing_padding:
                    clean_data += '=' * (4 - missing_padding)

                decoded_data  = base64.b64decode(clean_data).decode('utf-8')
                response_data = json.loads(decoded_data)
                logger.info("eSewa decoded response: %s", json.dumps(response_data))

            except Exception as e:
                logger.error("eSewa decode error: %s", str(e))
                return Response({
                    'success': False,
                    'error':   f'Invalid response data from eSewa! {str(e)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            # ──────────────────────────────────────────────────────────────────

            # ── Verify Signature ───────────────────────────────────────────────
            # ✅ KEY FIX: eSewa le signed_field_names bata signature banaucha
            # hamle pani tei fields use garnu parcha!
            secret_key         = settings.ESEWA_SECRET_KEY
            received_signature = response_data.get('signature', '')
            signed_field_names = response_data.get('signed_field_names', '')
            payment_status     = response_data.get('status', '')
            transaction_uuid   = response_data.get('transaction_uuid', '')
            transaction_code   = response_data.get('transaction_code', '')

            # signed_field_names bata message build garnus
            # e.g. "transaction_uuid=X,product=Y,total_amount=Z,status=W,transaction_code=V"
            signed_fields = signed_field_names.split(',')
            message = ','.join([
                f"{field}={response_data.get(field, '')}"
                for field in signed_fields
            ])

            logger.info("eSewa signature message: %s", message)

            h = hmac.new(
                key=secret_key.encode('utf-8'),
                msg=message.encode('utf-8'),
                digestmod=hashlib.sha256
            )
            expected_signature = base64.b64encode(h.digest()).decode('utf-8')

            logger.info("eSewa received_sig: %s | expected_sig: %s",
                        received_signature, expected_signature)

            if received_signature != expected_signature:
                return Response({
                    'success': False,
                    'error':   'Invalid signature! Payment verification failed.'
                }, status=status.HTTP_400_BAD_REQUEST)
            # ──────────────────────────────────────────────────────────────────

            if payment_status == 'COMPLETE':
                try:
                    payment = Payment.objects.get(order=order)
                except Payment.DoesNotExist:
                    payment = Payment.objects.create(
                        order          = order,
                        payment_method = 'esewa',
                        amount         = order.total_amount,
                        status         = 'initiated',
                    )

                payment.mark_esewa_completed(
                    transaction_uuid = transaction_uuid,
                    transaction_code = transaction_code,
                    response_data    = response_data,
                )

                logger.info("eSewa payment completed for order %s", order.order_number)

                return Response({
                    'success':          True,
                    'message':          'eSewa payment verified successfully!',
                    'payment':          PaymentSerializer(payment).data,
                    'order_number':     order.order_number,
                    'order_status':     order.status,
                    'transaction_code': transaction_code,
                }, status=status.HTTP_200_OK)

            else:
                return Response({
                    'success': False,
                    'error':   f'Payment status: {payment_status}. Please try again.'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Order.DoesNotExist:
            return Response({
                'success': False,
                'error':   'Order not found!'
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error("eSewa verify error: %s", str(e))
            return Response({
                'success': False,
                'error':   str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)