"""
Middleware to ensure API requests always return JSON errors instead of HTML
"""
import json
import traceback
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class JsonErrorMiddleware(MiddlewareMixin):
    """
    Middleware that catches exceptions and returns JSON responses for API requests
    """
    
    def process_exception(self, request, exception):
        path = request.path or ''
        if not (path.startswith('/api/') or path.startswith('/admin-dashboard/')):
            return None
        
        # Return JSON error response for API requests
        error_data = {
            'error': str(exception),
            'type': type(exception).__name__,
        }
        
        # Include traceback in debug mode
        from django.conf import settings
        if settings.DEBUG:
            error_data['traceback'] = traceback.format_exc()
        
        # Determine status code
        status_code = 500
        if hasattr(exception, 'status_code'):
            status_code = exception.status_code
        elif hasattr(exception, 'code'):
            status_code = exception.code
        
        return JsonResponse(error_data, status=status_code)

