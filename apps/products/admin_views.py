# apps/products/admin_views.py

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from .models import Product
from .serializers import ProductListSerializer

logger = logging.getLogger(__name__)


class IsAdminPermission(IsAdminUser):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


# ════════════════════════════════════════════════════════════
# PRODUCT STATS + LOW STOCK
# ════════════════════════════════════════════════════════════

class AdminProductStatsView(APIView):
    """
    GET /api/admin/products/stats/
    Product stats + low stock + out of stock alerts.
    Admin only.
    """
    permission_classes = [IsAuthenticated, IsAdminPermission]

    def get(self, request):
        low_stock    = Product.objects.filter(stock__lte=10, is_available=True).order_by('stock')
        out_of_stock = Product.objects.filter(stock=0)
        featured     = Product.objects.filter(is_featured=True).count()
        unavailable  = Product.objects.filter(is_available=False).count()

        return Response({
            'success': True,
            'stats': {
                'total':        Product.objects.count(),
                'low_stock':    low_stock.count(),
                'out_of_stock': out_of_stock.count(),
                'featured':     featured,
                'unavailable':  unavailable,
            },
            'low_stock_products':    ProductListSerializer(low_stock, many=True).data,
            'out_of_stock_products': ProductListSerializer(out_of_stock, many=True).data,
        })