# apps/orders/views.py — FULL FILE with Order Confirmation Email

from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from decimal import Decimal
import logging

from .models import Cart, CartItem, Order, OrderItem
from .emails import send_order_confirmation_email          # ✅ NEW
from .serializers import (
    CartSerializer,
    AddToCartSerializer,
    UpdateCartItemSerializer,
    OrderListSerializer,
    OrderDetailSerializer,
    CreateOrderSerializer,
    BuyNowSerializer,
    CheckoutSelectedSerializer,
)
from apps.products.models import Product

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# CART VIEWS
# ════════════════════════════════════════════════════════════

class MyCartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart, created = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart)
        return Response({'success': True, 'cart': serializer.data})


class AddToCartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=400)

        product_id = serializer.validated_data['product_id']
        quantity   = serializer.validated_data['quantity']

        try:
            product = Product.objects.get(id=product_id, is_available=True)

            if quantity > product.stock:
                return Response({'success': False, 'error': f'Only {product.stock} units available!'}, status=400)

            cart, _ = Cart.objects.get_or_create(user=request.user)
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart, product=product, defaults={'quantity': quantity}
            )

            if not created:
                new_quantity = cart_item.quantity + quantity
                if new_quantity > product.stock:
                    return Response({'success': False, 'error': f'Cannot add more. Only {product.stock} units available!'}, status=400)
                cart_item.quantity = new_quantity
                cart_item.save(update_fields=['quantity'])

            logger.info("Product %s added to cart of %s", product.name, request.user.email)
            return Response({'success': True, 'message': f'"{product.name}" added to cart!', 'cart': CartSerializer(cart).data})

        except Product.DoesNotExist:
            return Response({'success': False, 'error': 'Product not found!'}, status=404)


class UpdateCartItemView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        serializer = UpdateCartItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=400)

        try:
            cart_item    = CartItem.objects.get(pk=pk, cart__user=request.user)
            new_quantity = serializer.validated_data['quantity']

            if new_quantity > cart_item.product.stock:
                return Response({'success': False, 'error': f'Only {cart_item.product.stock} units available!'}, status=400)

            cart_item.quantity = new_quantity
            cart_item.save(update_fields=['quantity'])
            return Response({'success': True, 'message': 'Cart updated!', 'cart': CartSerializer(cart_item.cart).data})

        except CartItem.DoesNotExist:
            return Response({'success': False, 'error': 'Cart item not found!'}, status=404)


class RemoveFromCartView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            cart_item    = CartItem.objects.get(pk=pk, cart__user=request.user)
            product_name = cart_item.product.name
            cart         = cart_item.cart
            cart_item.delete()
            logger.info("Product %s removed from cart of %s", product_name, request.user.email)
            return Response({'success': True, 'message': f'"{product_name}" removed from cart!', 'cart': CartSerializer(cart).data})

        except CartItem.DoesNotExist:
            return Response({'success': False, 'error': 'Cart item not found!'}, status=404)


class ClearCartView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        try:
            cart = Cart.objects.get(user=request.user)
            cart.clear()
        except Cart.DoesNotExist:
            pass
        return Response({'success': True, 'message': 'Cart cleared!'})


# ════════════════════════════════════════════════════════════
# ORDER VIEWS
# ════════════════════════════════════════════════════════════

class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=400)

        try:
            cart = Cart.objects.get(user=request.user)

            if not cart.items.exists():
                return Response({'success': False, 'error': 'Cart is empty! Please add products first.'}, status=400)

            subtotal      = cart.subtotal
            shipping_cost = Decimal('0')
            tax           = Decimal('0')
            discount      = Decimal('0')
            total         = subtotal + shipping_cost + tax - discount

            payment_method = serializer.validated_data['payment_method']

            order = Order.objects.create(
                user           = request.user,
                full_name      = serializer.validated_data['full_name'],
                phone          = serializer.validated_data['phone'],
                email          = serializer.validated_data['email'],
                address_line1  = serializer.validated_data['address_line1'],
                address_line2  = serializer.validated_data.get('address_line2', ''),
                city           = serializer.validated_data['city'],
                state          = serializer.validated_data.get('state', ''),
                postal_code    = serializer.validated_data.get('postal_code', ''),
                subtotal       = subtotal,
                shipping_cost  = shipping_cost,
                tax            = tax,
                discount       = discount,
                total_amount   = total,
                payment_method = payment_method,
                notes          = serializer.validated_data.get('notes', ''),
            )

            for cart_item in cart.items.select_related('product').all():
                if cart_item.quantity > cart_item.product.stock:
                    raise Exception(f'"{cart_item.product.name}" stock kam cha! Only {cart_item.product.stock} available.')

                OrderItem.objects.create(
                    order         = order,
                    product       = cart_item.product,
                    product_name  = cart_item.product.name,
                    product_brand = cart_item.product.brand,
                    product_image = cart_item.product.image,
                    quantity      = cart_item.quantity,
                    unit_price    = cart_item.unit_price,
                    total_price   = cart_item.unit_price * cart_item.quantity,
                )
                cart_item.product.stock -= cart_item.quantity
                cart_item.product.save(update_fields=['stock'])

            cart.clear()
            logger.info("Order %s created by %s", order.order_number, request.user.email)

            # ✅ COD — place भएपछि तुरुन्त confirmation email
            if payment_method == 'cod':
                send_order_confirmation_email(
                    order          = order,
                    payment_method = 'cod',
                    payment_status = 'pending',
                )

            return Response({
                'success': True,
                'message': 'Order placed successfully!',
                'order':   OrderDetailSerializer(order).data
            }, status=201)

        except Cart.DoesNotExist:
            return Response({'success': False, 'error': 'Cart not found! Please add products first.'}, status=404)
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=400)


class MyOrdersView(generics.ListAPIView):
    serializer_class   = OrderListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset   = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({'success': True, 'count': queryset.count(), 'orders': serializer.data})


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class   = OrderDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance   = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({'success': True, 'order': serializer.data})


class CancelOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, user=request.user)

            if order.status not in ['pending', 'confirmed']:
                return Response({
                    'success': False,
                    'error': f'Cannot cancel order with status: {order.status}. Only pending/confirmed orders can be cancelled.'
                }, status=400)

            order.status = 'cancelled'
            order.save(update_fields=['status'])

            for item in order.items.select_related('product').all():
                if item.product:
                    item.product.stock += item.quantity
                    item.product.save(update_fields=['stock'])

            logger.info("Order %s cancelled by %s", order.order_number, request.user.email)
            return Response({'success': True, 'message': f'Order {order.order_number} cancelled successfully!'})

        except Order.DoesNotExist:
            return Response({'success': False, 'error': 'Order not found!'}, status=404)


# ════════════════════════════════════════════════════════════
# BUY NOW
# ════════════════════════════════════════════════════════════

class BuyNowView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = BuyNowSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=400)

        product_id     = serializer.validated_data['product_id']
        quantity       = serializer.validated_data['quantity']
        payment_method = serializer.validated_data['payment_method']

        try:
            product = Product.objects.get(id=product_id, is_available=True)

            if quantity > product.stock:
                return Response({'success': False, 'error': f'Only {product.stock} units available!'}, status=400)

            unit_price    = product.discounted_price
            subtotal      = unit_price * quantity
            shipping_cost = Decimal('0')
            total         = Decimal(str(subtotal)) + shipping_cost

            order = Order.objects.create(
                user           = request.user,
                full_name      = serializer.validated_data['full_name'],
                phone          = serializer.validated_data['phone'],
                email          = serializer.validated_data['email'],
                address_line1  = serializer.validated_data['address_line1'],
                address_line2  = serializer.validated_data.get('address_line2', ''),
                city           = serializer.validated_data['city'],
                state          = serializer.validated_data.get('state', ''),
                postal_code    = serializer.validated_data.get('postal_code', ''),
                subtotal       = subtotal,
                shipping_cost  = shipping_cost,
                tax            = Decimal('0'),
                discount       = Decimal('0'),
                total_amount   = total,
                payment_method = payment_method,
                notes          = serializer.validated_data.get('notes', ''),
            )

            OrderItem.objects.create(
                order         = order,
                product       = product,
                product_name  = product.name,
                product_brand = product.brand,
                product_image = product.image,
                quantity      = quantity,
                unit_price    = unit_price,
                total_price   = unit_price * quantity,
            )

            product.stock -= quantity
            product.save(update_fields=['stock'])

            logger.info("Buy Now order %s created by %s", order.order_number, request.user.email)

            # ✅ COD — place भएपछि तुरुन्त confirmation email
            if payment_method == 'cod':
                send_order_confirmation_email(
                    order          = order,
                    payment_method = 'cod',
                    payment_status = 'pending',
                )

            return Response({
                'success': True,
                'message': 'Order placed successfully!',
                'order':   OrderDetailSerializer(order).data
            }, status=201)

        except Product.DoesNotExist:
            return Response({'success': False, 'error': 'Product not found!'}, status=404)
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=400)


# ════════════════════════════════════════════════════════════
# CHECKOUT SELECTED
# ════════════════════════════════════════════════════════════

class CheckoutSelectedView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = CheckoutSelectedSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'error': serializer.errors}, status=400)

        cart_item_ids  = serializer.validated_data['cart_item_ids']
        payment_method = serializer.validated_data['payment_method']

        try:
            cart           = Cart.objects.get(user=request.user)
            selected_items = CartItem.objects.filter(id__in=cart_item_ids, cart=cart).select_related('product')

            if not selected_items.exists():
                return Response({'success': False, 'error': 'No valid items selected!'}, status=400)

            for item in selected_items:
                if item.quantity > item.product.stock:
                    return Response({'success': False, 'error': f'"{item.product.name}" — only {item.product.stock} available!'}, status=400)

            subtotal      = Decimal(str(sum(item.total_price for item in selected_items)))
            shipping_cost = Decimal('0')
            total         = subtotal + shipping_cost

            order = Order.objects.create(
                user           = request.user,
                full_name      = serializer.validated_data['full_name'],
                phone          = serializer.validated_data['phone'],
                email          = serializer.validated_data['email'],
                address_line1  = serializer.validated_data['address_line1'],
                address_line2  = serializer.validated_data.get('address_line2', ''),
                city           = serializer.validated_data['city'],
                state          = serializer.validated_data.get('state', ''),
                postal_code    = serializer.validated_data.get('postal_code', ''),
                subtotal       = subtotal,
                shipping_cost  = shipping_cost,
                tax            = Decimal('0'),
                discount       = Decimal('0'),
                total_amount   = total,
                payment_method = payment_method,
                notes          = serializer.validated_data.get('notes', ''),
            )

            for item in selected_items:
                OrderItem.objects.create(
                    order         = order,
                    product       = item.product,
                    product_name  = item.product.name,
                    product_brand = item.product.brand,
                    product_image = item.product.image,
                    quantity      = item.quantity,
                    unit_price    = item.unit_price,
                    total_price   = item.unit_price * item.quantity,
                )
                item.product.stock -= item.quantity
                item.product.save(update_fields=['stock'])
                item.delete()

            logger.info("Checkout selected order %s created by %s", order.order_number, request.user.email)

            # ✅ COD — place भएपछि तुरुन्त confirmation email
            if payment_method == 'cod':
                send_order_confirmation_email(
                    order          = order,
                    payment_method = 'cod',
                    payment_status = 'pending',
                )

            return Response({
                'success': True,
                'message': 'Order placed successfully!',
                'order':   OrderDetailSerializer(order).data
            }, status=201)

        except Cart.DoesNotExist:
            return Response({'success': False, 'error': 'Cart is empty!'}, status=404)
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=400)


# ════════════════════════════════════════════════════════════
# ESEWA PAYMENT VERIFY — ✅ Email trigger यहाँ हुन्छ
# ════════════════════════════════════════════════════════════

class EsewaVerifyView(APIView):
    """
    POST /api/orders/esewa/verify/
    eSewa payment verify भएपछि order confirm + email send.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import base64, json
        from django.conf import settings
        import hmac, hashlib

        encoded_data = request.data.get('data', '')
        if not encoded_data:
            return Response({'success': False, 'error': 'No payment data received.'}, status=400)

        try:
            decoded     = base64.b64decode(encoded_data).decode('utf-8')
            parsed      = json.loads(decoded)
            order_id    = parsed.get('transaction_uuid', '').split('-')[0]
            status_code = parsed.get('status', '')
            signature   = parsed.get('signature', '')

            # Verify signature
            secret_key = getattr(settings, 'ESEWA_SECRET_KEY', '8gBm/:&EnhH.1/q')
            msg        = f"transaction_code={parsed.get('transaction_code','')},status={status_code},total_amount={parsed.get('total_amount','')},transaction_uuid={parsed.get('transaction_uuid','')},product_code={parsed.get('product_code','')},signed_field_names={parsed.get('signed_field_names','')}"
            expected   = base64.b64encode(
                hmac.new(secret_key.encode(), msg.encode(), hashlib.sha256).digest()
            ).decode()

            if signature != expected:
                return Response({'success': False, 'error': 'Invalid payment signature.'}, status=400)

            if status_code != 'COMPLETE':
                return Response({'success': False, 'error': f'Payment not complete: {status_code}'}, status=400)

            order = Order.objects.get(id=order_id, user=request.user)

            if order.payment_status == 'paid':
                return Response({'success': True, 'message': 'Already verified.', 'order': OrderDetailSerializer(order).data})

            # ── Mark as paid ──
            order.payment_status = 'paid'
            order.status         = 'confirmed'
            order.save(update_fields=['payment_status', 'status'])

            logger.info("eSewa payment verified for order #%s", order.id)

            # ✅ eSewa — payment verify भएपछि confirmation email
            send_order_confirmation_email(
                order          = order,
                payment_method = 'esewa',
                payment_status = 'paid',
            )

            return Response({
                'success': True,
                'message': 'Payment verified! Order confirmed.',
                'order':   OrderDetailSerializer(order).data,
            })

        except Order.DoesNotExist:
            return Response({'success': False, 'error': 'Order not found.'}, status=404)
        except Exception as e:
            logger.error("eSewa verify error: %s", str(e))
            return Response({'success': False, 'error': str(e)}, status=400)