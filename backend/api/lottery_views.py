import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import LotterySettings


def _is_admin(request):
    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False):
        return True
    if request.session.get('second_admin_authenticated'):
        return True
    return False


@require_http_methods(['GET'])
def lottery_settings_public(request):
    """Public settings for the mini-app (no auth)."""
    settings_obj = LotterySettings.get_settings()
    return JsonResponse(settings_obj.to_public_dict(request))


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def lottery_settings_admin(request):
    """Admin GET/POST for lottery settings. Staff or second-admin session."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    settings_obj = LotterySettings.get_settings()

    if request.method == 'GET':
        data = settings_obj.to_public_dict(request)
        data['car_image_url_raw'] = settings_obj.car_image_url or ''
        return JsonResponse(data)

    # POST — JSON and/or multipart (image upload)
    content_type = (request.content_type or '').lower()
    if 'multipart/form-data' in content_type:
        data = request.POST.dict()
        accounts_raw = data.get('payment_accounts')
    else:
        try:
            data = json.loads(request.body) if request.body else {}
        except (json.JSONDecodeError, ValueError):
            data = {}
        accounts_raw = data.get('payment_accounts')

    str_fields = ['brand_name', 'car_name', 'car_color', 'car_image_url', 'display_name']
    int_fields = [
        'ticket_price', 'total_tickets', 'sold_count',
        'countdown_days', 'countdown_hours', 'countdown_minutes', 'countdown_seconds',
    ]

    old_timer = (
        settings_obj.countdown_days,
        settings_obj.countdown_hours,
        settings_obj.countdown_minutes,
        settings_obj.countdown_seconds,
    )

    for field in str_fields:
        if field in data and data[field] is not None:
            setattr(settings_obj, field, str(data[field]).strip())

    for field in int_fields:
        if field in data and data[field] is not None and data[field] != '':
            try:
                setattr(settings_obj, field, max(0, int(data[field])))
            except (TypeError, ValueError):
                pass

    new_timer = (
        settings_obj.countdown_days,
        settings_obj.countdown_hours,
        settings_obj.countdown_minutes,
        settings_obj.countdown_seconds,
    )
    timer_touched = old_timer != new_timer

    if accounts_raw is not None:
        if isinstance(accounts_raw, str):
            try:
                accounts_raw = json.loads(accounts_raw)
            except (json.JSONDecodeError, ValueError):
                accounts_raw = None
        if isinstance(accounts_raw, list):
            cleaned = []
            for i, acc in enumerate(accounts_raw):
                if not isinstance(acc, dict):
                    continue
                cleaned.append({
                    'id': str(acc.get('id') or f'acc-{i+1}'),
                    'name': str(acc.get('name') or '').strip(),
                    'holder': str(acc.get('holder') or '').strip(),
                    'account': str(acc.get('account') or '').strip(),
                })
            settings_obj.payment_accounts = cleaned

    if request.FILES.get('car_image'):
        settings_obj.car_image = request.FILES['car_image']

    force_reset = str(data.get('reset_timer', '')).lower() in ('1', 'true', 'yes', 'on')
    settings_obj.save(reset_timer=timer_touched or force_reset)

    return JsonResponse({
        'success': True,
        'settings': settings_obj.to_public_dict(request),
    })
