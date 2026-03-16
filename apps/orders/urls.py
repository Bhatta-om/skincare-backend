# apps/orders/urls.py

from django.urls import path
from .views import (
    MyCartView,
    AddToCartView,
    UpdateCartItemView,
    RemoveFromCartView,
    ClearCartView,
    CreateOrderView,
    MyOrdersView,
    OrderDetailView,
    CancelOrderView,
    BuyNowView,
    CheckoutSelectedView,
)

app_name = 'orders'

urlpatterns = [
    # Cart
    path('cart/',                       MyCartView.as_view(),          name='my_cart'),
    path('cart/add/',                   AddToCartView.as_view(),        name='add_to_cart'),
    path('cart/items/<int:pk>/',        UpdateCartItemView.as_view(),   name='update_cart_item'),
    path('cart/items/<int:pk>/remove/', RemoveFromCartView.as_view(),   name='remove_from_cart'),
    path('cart/clear/',                 ClearCartView.as_view(),        name='clear_cart'),

    # Orders
    path('create/',              CreateOrderView.as_view(),      name='create_order'),
    path('buy-now/',             BuyNowView.as_view(),           name='buy_now'),
    path('checkout-selected/',   CheckoutSelectedView.as_view(), name='checkout_selected'),
    path('my-orders/',           MyOrdersView.as_view(),         name='my_orders'),
    path('<int:pk>/',            OrderDetailView.as_view(),       name='order_detail'),
    path('<int:pk>/cancel/',     CancelOrderView.as_view(),       name='cancel_order'),
]