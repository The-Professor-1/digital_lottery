from django.http import JsonResponse


def _wants_json(request):
    path = request.path or ''
    if path.startswith('/api/'):
        return True
    if path.startswith('/admin-dashboard/'):
        return True
    accept = request.headers.get('Accept', '')
    if 'application/json' in accept:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return False


def json_404(request, exception=None):
    if _wants_json(request):
        hint = ''
        if 'lottery-' in request.path:
            hint = ' Server may need git pull, migrate, and gunicorn restart.'
        return JsonResponse(
            {'error': f'Not found: {request.path}.{hint}'},
            status=404,
        )
    from django.views.defaults import page_not_found
    return page_not_found(request, exception)
