# core/permissions.py

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrReadOnly(BasePermission):
    """
    Admin users → Full access (GET, POST, PUT, DELETE)
    Normal users → Read-only (GET)
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class IsOwnerOrAdmin(BasePermission):
    """
    Object ko owner OR admin matra edit garna sakcha
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        return obj.user == request.user


class IsAuthenticatedOrCreateOnly(BasePermission):
    """
    POST (registration) → anyone
    Other methods → authenticated only
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            return True
        return request.user and request.user.is_authenticated