from django.http import JsonResponse, HttpResponse

def csrf_failure(request, reason=""):
    """Custom CSRF failure handler that returns JSON for AJAX requests"""
    # Check if this is an API request (starts with /api/)
    is_api_request = request.path.startswith('/api/')
    
    # Check if this is an AJAX/JSON request
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('Content-Type', '').startswith('application/json') or
        request.headers.get('Accept', '').startswith('application/json') or
        is_api_request  # All /api/ requests should return JSON
    )
    
    if is_ajax:
        return JsonResponse({
            'error': 'CSRF verification failed. Please refresh the page and try again.',
            'detail': str(reason)
        }, status=403)
    
    # For non-AJAX requests, return a simple HTML error page
    return HttpResponse(
        '<html><body><h1>403 Forbidden</h1><p>CSRF verification failed. Please refresh the page and try again.</p></body></html>',
        status=403
    )

