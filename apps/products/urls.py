from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, ProductViewSet,
    WishlistViewSet, SearchSuggestionsView,
    BulkImportView
)

app_name = 'products'
router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'', ProductViewSet, basename='product')

urlpatterns = [
    path('wishlist/',         WishlistViewSet.as_view({'get': 'list'}),     name='wishlist-list'),
    path('wishlist/toggle/',  WishlistViewSet.as_view({'post': 'toggle'}),  name='wishlist-toggle'),
    path('wishlist/ids/',     WishlistViewSet.as_view({'get': 'ids'}),      name='wishlist-ids'),
    path('wishlist/clear/',   WishlistViewSet.as_view({'delete': 'clear'}), name='wishlist-clear'),
    path('search/suggestions/', SearchSuggestionsView.as_view(),            name='search-suggestions'),
    path('bulk-import/',      BulkImportView.as_view(),                     name='bulk-import'),
    path('', include(router.urls)),
]