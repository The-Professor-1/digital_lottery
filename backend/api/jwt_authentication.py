"""
JWT Authentication for Django REST Framework
"""
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from .auth_utils import get_user_from_token


class JWTAuthentication(authentication.BaseAuthentication):
    """
    JWT token authentication for DRF
    Expects token in Authorization header as: Bearer <token>
    """
    
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header:
            return None
        
        # Check if it's a Bearer token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None
        
        token = parts[1]
        
        # Get user from token
        user = get_user_from_token(token)
        if not user:
            raise AuthenticationFailed('Invalid or expired token')
        
        # Don't refresh here - let individual endpoints refresh when needed
        # This prevents issues with stale data in request.user
        
        # Return (user, token) tuple
        return (user, token)

