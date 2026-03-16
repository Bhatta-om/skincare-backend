# apps/products/urls.py — search suggestion path थप्नुस्
# EXISTING urls.py मा यो line थप्नुस् (wishlist paths पछि, router भन्दा अगाडि)

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, WishlistViewSet, SearchSuggestionsView

app_name = 'products'

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'', ProductViewSet, basename='product')

urlpatterns = [
    # Wishlist — manual paths FIRST
    path('wishlist/',        WishlistViewSet.as_view({'get': 'list'}),     name='wishlist-list'),
    path('wishlist/toggle/', WishlistViewSet.as_view({'post': 'toggle'}),  name='wishlist-toggle'),
    path('wishlist/ids/',    WishlistViewSet.as_view({'get': 'ids'}),      name='wishlist-ids'),
    path('wishlist/clear/',  WishlistViewSet.as_view({'delete': 'clear'}), name='wishlist-clear'),

    # ✅ Search Suggestions
    path('search/suggestions/', SearchSuggestionsView.as_view(), name='search-suggestions'),

    # Router LAST
    path('', include(router.urls)),
]