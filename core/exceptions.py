# core/exceptions.py

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    """
    Custom exception handler for consistent error responses
    
    Standard error format:
    {
        "success": false,
        "error": {
            "message": "Error description",
            "details": {...}
        },
        "status_code": 400
    }
    """
    # Django REST framework ko default handler call gara
    response = exception_handler(exc, context)
    
    if response is not None:
        # Custom error format
        custom_response = {
            'success': False,
            'error': {
                'message': get_error_message(exc),
                'details': response.data
            },
            'status_code': response.status_code
        }
        response.data = custom_response
    
    return response


def get_error_message(exc):
    """
    Exception bata user-friendly message nikala
    """
    if hasattr(exc, 'detail'):
        if isinstance(exc.detail, dict):
            # Dictionary error ko first message return gara
            return str(list(exc.detail.values())[0][0]) if exc.detail else str(exc)
        return str(exc.detail)
    return str(exc)


# Custom exceptions (specific cases ko lagi)
from rest_framework.exceptions import APIException

class ImageUploadError(APIException):
    """
    Image upload fail bhayo bhane yo error throw gara
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Image upload failed. Please check file format and size.'
    default_code = 'image_upload_error'


class SkinAnalysisError(APIException):
    """
    CNN model le analysis garna sakena
    """
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'Skin analysis failed. Please try again with a clearer image.'
    default_code = 'skin_analysis_error'


class ProductNotAvailable(APIException):
    """
    Product stock ma chaina
    """
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'This product is currently out of stock.'
    default_code = 'product_not_available'


class InsufficientStock(APIException):
    """
    Order quantity bhandaa kam stock cha
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Insufficient stock available for this product.'
    default_code = 'insufficient_stock'