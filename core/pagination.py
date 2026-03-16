# core/pagination.py

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class StandardPagination(PageNumberPagination):
    """
    Default pagination for all APIs
    
    URL: /api/products/?page=2&page_size=20
    
    Response format:
    {
        "count": 100,
        "next": "http://localhost:8000/api/products/?page=3",
        "previous": "http://localhost:8000/api/products/?page=1",
        "results": [...]
    }
    """
    page_size = 12  # Default 12 items per page
    page_size_query_param = 'page_size'  # User le customize garna milcha
    max_page_size = 100  # Maximum limit
    
    def get_paginated_response(self, data):
        """
        Custom response format with extra metadata
        """
        return Response({
            'success': True,
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })


class LargeResultsPagination(PageNumberPagination):
    """
    Admin panel ko lagi — dherai items chahine bela
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class SmallResultsPagination(PageNumberPagination):
    """
    Mobile app ko lagi — thodai items
    """
    page_size = 6
    page_size_query_param = 'page_size'
    max_page_size = 20