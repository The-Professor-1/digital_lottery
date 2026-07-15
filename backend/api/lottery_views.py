import hashlib
import json
import os
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .auth_utils import get_user_from_token
from .models import LotterySettings, LotteryPurchase


def _is_admin(request):
    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False):
        return True
    if request.session.get('second_admin_authenticated'):
        return True
    return False


def _bearer_user(request):
    auth = request.META.get('HTTP_AUTHORIZATION') or ''
    if auth.lower().startswith('bearer '):
        return get_user_from_token(auth[7:].strip())
    token = request.GET.get('token') or request.POST.get('token')
    if token:
        return get_user_from_token(token)
    return None


def _file_sha256(uploaded):
    h = hashlib.sha256()
    for chunk in uploaded.chunks():
        h.update(chunk)
    uploaded.seek(0)
    return h.hexdigest()


def _period_filter(qs, period):
    now = timezone.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'today':
        return qs.filter(created_at__gte=today)
    if period == 'week':
        return qs.filter(created_at__gte=today - timedelta(days=7))
    if period == 'month':
        return qs.filter(created_at__gte=today - timedelta(days=30))
    return qs


@ensure_csrf_cookie
@require_http_methods(['GET'])
def lottery_admin_bootstrap(request):
    """Set csrftoken cookie for the Vue admin SPA (session auth)."""
    return JsonResponse({
        'ok': True,
        'authenticated': _is_admin(request),
    })


@require_http_methods(['GET'])
def lottery_settings_public(request):
    settings_obj = LotterySettings.get_settings()
    return JsonResponse(settings_obj.to_public_dict(request))


@require_http_methods(['GET'])
def lottery_me(request):
    user = _bearer_user(request)
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    return JsonResponse({
        'user_id': user.id,
        'telegram_id': user.telegram_id,
        'phone': user.phone_number or '',
        'first_name': user.first_name or '',
        'username': user.username or '',
        'preferred_language': (user.preferred_language or 'am')[:5],
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_set_language(request):
    user = _bearer_user(request)
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    lang = (body.get('language') or body.get('preferred_language') or '').strip().lower()
    if lang not in ('am', 'en', 'om'):
        return JsonResponse({'error': 'Invalid language'}, status=400)
    user.preferred_language = lang
    user.save(update_fields=['preferred_language'])
    return JsonResponse({'success': True, 'preferred_language': lang})


@require_http_methods(['GET'])
def lottery_tickets(request):
    phone = (request.GET.get('phone') or '').strip()
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 9:
        return JsonResponse({'tickets': [], 'active': 0, 'pending': 0, 'total': 0})

    qs = LotteryPurchase.objects.filter(
        Q(phone__icontains=digits[-9:]) | Q(phone__icontains=digits)
    ).exclude(status='rejected')
    tickets = [p.to_dict(request) for p in qs[:100]]
    active = sum(1 for t in tickets if t['status'] == 'verified')
    pending = sum(1 for t in tickets if t['status'] == 'pending')
    return JsonResponse({
        'tickets': tickets,
        'active': active,
        'pending': pending,
        'total': len(tickets),
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_submit_purchase(request):
    user = _bearer_user(request)

    full_name = (request.POST.get('full_name') or '').strip()
    phone = (request.POST.get('phone') or '').strip()
    paid_from = (request.POST.get('paid_from_account') or '').strip()
    bank_name = (request.POST.get('bank_name') or '').strip()
    bank_holder = (request.POST.get('bank_holder') or '').strip()
    bank_account = (request.POST.get('bank_account') or '').strip()

    try:
        numbers = json.loads(request.POST.get('numbers') or '[]')
    except (json.JSONDecodeError, TypeError):
        numbers = []
    numbers = [int(n) for n in numbers if str(n).isdigit() or isinstance(n, int)]

    if not full_name or not phone:
        return JsonResponse({'error': 'Name and phone are required'}, status=400)
    if not numbers:
        return JsonResponse({'error': 'Select at least one number'}, status=400)

    receipt = request.FILES.get('receipt') or request.FILES.get('receipt_image')
    if not receipt:
        return JsonResponse({'error': 'Payment receipt image is required'}, status=400)

    settings_obj = LotterySettings.get_settings()
    taken = settings_obj.taken_numbers_set()
    conflict = [n for n in numbers if n in taken]
    if conflict:
        return JsonResponse({
            'error': 'Some numbers are no longer available',
            'taken': conflict,
        }, status=409)

    receipt_hash = _file_sha256(receipt)
    if LotteryPurchase.objects.filter(receipt_hash=receipt_hash).exists():
        return JsonResponse({
            'error': 'This receipt image was already submitted. Use a different receipt for another ticket.',
        }, status=409)

    amount = Decimal(settings_obj.ticket_price) * len(numbers)
    if user and user.phone_number and not phone:
        phone = user.phone_number

    if not user:
        from .models import User
        digits = ''.join(c for c in phone if c.isdigit())
        if digits:
            user = User.objects.filter(phone_number__icontains=digits[-9:]).order_by('-id').first()

    purchase = LotteryPurchase.objects.create(
        user=user,
        full_name=full_name,
        phone=phone,
        numbers=numbers,
        quantity=len(numbers),
        amount=amount,
        bank_name=bank_name,
        bank_holder=bank_holder,
        bank_account=bank_account,
        paid_from_account=paid_from,
        receipt_image=receipt,
        receipt_hash=receipt_hash,
        status='pending',
    )
    return JsonResponse({
        'success': True,
        'message_key': 'receiptPendingHint',
        'message': '',
        'purchase': purchase.to_dict(request),
    })


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def lottery_settings_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    settings_obj = LotterySettings.get_settings()

    if request.method == 'GET':
        data = settings_obj.to_public_dict(request)
        data['car_image_url_raw'] = settings_obj.car_image_url or ''
        data['admin_blocked_numbers'] = settings_obj.admin_blocked_numbers or []
        return JsonResponse(data)

    try:
        content_type = (request.content_type or '').lower()
        if 'multipart/form-data' in content_type:
            data = request.POST.dict()
            accounts_raw = data.get('payment_accounts')
            blocked_raw = data.get('admin_blocked_numbers')
        else:
            try:
                data = json.loads(request.body) if request.body else {}
            except (json.JSONDecodeError, ValueError):
                data = {}
            accounts_raw = data.get('payment_accounts')
            blocked_raw = data.get('admin_blocked_numbers')

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
                    setattr(settings_obj, field, max(0, int(float(data[field]))))
                except (TypeError, ValueError):
                    pass

        timer_touched = old_timer != (
            settings_obj.countdown_days,
            settings_obj.countdown_hours,
            settings_obj.countdown_minutes,
            settings_obj.countdown_seconds,
        )

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

        if blocked_raw is not None:
            if isinstance(blocked_raw, str):
                try:
                    blocked_raw = json.loads(blocked_raw)
                except (json.JSONDecodeError, ValueError):
                    blocked_raw = []
            if isinstance(blocked_raw, list):
                nums = []
                for n in blocked_raw:
                    try:
                        nums.append(int(n))
                    except (TypeError, ValueError):
                        pass
                settings_obj.admin_blocked_numbers = sorted(set(nums))

        if request.FILES.get('car_image'):
            settings_obj.car_image = request.FILES['car_image']
        elif str(data.get('clear_car_image', '')).lower() in ('1', 'true', 'yes'):
            if settings_obj.car_image:
                settings_obj.car_image.delete(save=False)
            settings_obj.car_image = None

        force_reset = str(data.get('reset_timer', '')).lower() in ('1', 'true', 'yes', 'on')
        settings_obj.save(reset_timer=timer_touched or force_reset)

        # Ensure uploaded media files are world-readable (nginx/alias safety)
        try:
            from django.conf import settings as dj_settings
            root = getattr(dj_settings, 'MEDIA_ROOT', None)
            if root and os.path.isdir(root):
                for dirpath, _dirnames, filenames in os.walk(root):
                    try:
                        os.chmod(dirpath, 0o755)
                    except OSError:
                        pass
                    for name in filenames:
                        try:
                            os.chmod(os.path.join(dirpath, name), 0o644)
                        except OSError:
                            pass
        except Exception:
            pass

        out = settings_obj.to_public_dict(request)
        out['car_image_url_raw'] = settings_obj.car_image_url or ''
        out['admin_blocked_numbers'] = settings_obj.admin_blocked_numbers or []
        return JsonResponse({'success': True, 'settings': out})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e) or 'Could not save settings'}, status=500)


@csrf_exempt
@require_http_methods(['GET'])
def lottery_purchases_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    status = (request.GET.get('status') or 'pending').strip()
    period = (request.GET.get('period') or 'all').strip()
    qs = LotteryPurchase.objects.all().select_related('user')
    if status in ('pending', 'verified', 'rejected'):
        qs = qs.filter(status=status)
    qs = _period_filter(qs, period)

    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    verified_today = LotteryPurchase.objects.filter(status='verified', verified_at__gte=today)
    revenue_today = verified_today.aggregate(total=Sum('amount'))['total'] or 0

    return JsonResponse({
        'purchases': [p.to_dict(request) for p in qs[:200]],
        'revenue_today': float(revenue_today),
        'verified_today_count': verified_today.count(),
        'pending_count': LotteryPurchase.objects.filter(status='pending').count(),
        'verified_count': LotteryPurchase.objects.filter(status='verified').count(),
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_purchase_action(request, purchase_id):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}

    action = (body.get('action') or '').strip()
    note = (body.get('note') or '').strip()

    try:
        purchase = LotteryPurchase.objects.select_related('user').get(id=purchase_id)
    except LotteryPurchase.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if action == 'verify':
        if purchase.status == 'verified':
            return JsonResponse({'error': 'Already verified'}, status=400)
        settings_obj = LotterySettings.get_settings()
        others = set()
        for n in settings_obj.admin_blocked_numbers or []:
            try:
                others.add(int(n))
            except (TypeError, ValueError):
                pass
        for p in LotteryPurchase.objects.filter(status='verified').exclude(id=purchase.id):
            for n in p.numbers or []:
                try:
                    others.add(int(n))
                except (TypeError, ValueError):
                    pass
        conflict = [n for n in (purchase.numbers or []) if int(n) in others]
        if conflict:
            return JsonResponse({'error': f'Numbers already taken: {conflict}'}, status=409)

        purchase.status = 'verified'
        purchase.verified_at = timezone.now()
        purchase.admin_note = note
        if getattr(request.user, 'is_authenticated', False) and request.user.is_authenticated:
            purchase.verified_by = request.user
        purchase.save()

        if purchase.user_id and purchase.user and purchase.user.telegram_id:
            nums = ', '.join(str(n).zfill(3) for n in (purchase.numbers or []))
            msg = (
                f'✅ Receipt verified!\n\n'
                f'Your lottery numbers: {nums}\n'
                f'Amount: {purchase.amount} Birr\n\n'
                f'Open the app → Tickets to view them.'
            )
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(purchase.user.telegram_id, msg)
            except Exception:
                pass

        return JsonResponse({'success': True, 'purchase': purchase.to_dict(request)})

    if action == 'reject':
        purchase.status = 'rejected'
        purchase.admin_note = note
        purchase.save()
        if purchase.user_id and purchase.user and purchase.user.telegram_id:
            msg = '❌ Your payment receipt was not approved. Please contact support or submit again with a clearer receipt.'
            if note:
                msg += f'\n\nNote: {note}'
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(purchase.user.telegram_id, msg)
            except Exception:
                pass
        return JsonResponse({'success': True, 'purchase': purchase.to_dict(request)})

    if action == 'delete':
        # Allow deleting verified/rejected/pending to free numbers after test purchases
        if purchase.status not in ('verified', 'rejected', 'pending'):
            return JsonResponse({'error': 'Cannot delete this status'}, status=400)
        deleted_id = purchase.id
        try:
            if purchase.receipt_image:
                purchase.receipt_image.delete(save=False)
        except Exception:
            pass
        purchase.delete()
        return JsonResponse({'success': True, 'deleted': deleted_id})

    return JsonResponse({'error': 'Unknown action'}, status=400)


@csrf_exempt
@require_http_methods(['GET'])
def lottery_users_admin(request):
    """List registered lottery users with current-round ticket holdings."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    q = (request.GET.get('q') or '').strip()

    # Users who registered via Telegram OR submitted a purchase
    from .models import User
    user_qs = User.objects.filter(
        Q(telegram_id__isnull=False) | Q(lottery_purchases__isnull=False)
    ).distinct().order_by('-id')

    if q:
        user_qs = user_qs.filter(
            Q(phone_number__icontains=q)
            | Q(first_name__icontains=q)
            | Q(username__icontains=q)
            | Q(telegram_id__icontains=q if q.isdigit() else '___none___')
        )

    users_out = []
    for u in user_qs[:300]:
        purchases = list(
            LotteryPurchase.objects.filter(user=u).order_by('-created_at')[:50]
        )
        # Also match by phone if user not linked on older rows
        phone = (u.phone_number or '').strip()
        if phone:
            digits = ''.join(c for c in phone if c.isdigit())
            if len(digits) >= 9:
                extra = LotteryPurchase.objects.filter(
                    Q(phone__icontains=digits[-9:]) | Q(phone__icontains=digits)
                ).exclude(user=u).order_by('-created_at')[:50]
                purchases = purchases + list(extra)

        verified_nums = []
        pending_nums = []
        verified_count = 0
        pending_count = 0
        total_spent = 0.0
        for p in purchases:
            nums = [int(n) for n in (p.numbers or []) if str(n).isdigit() or isinstance(n, int)]
            if p.status == 'verified':
                verified_nums.extend(nums)
                verified_count += 1
                total_spent += float(p.amount or 0)
            elif p.status == 'pending':
                pending_nums.extend(nums)
                pending_count += 1

        users_out.append({
            'id': u.id,
            'telegram_id': u.telegram_id,
            'phone': u.phone_number or '',
            'first_name': u.first_name or '',
            'username': u.username or '',
            'preferred_language': u.preferred_language or '',
            'verified_numbers': sorted(set(verified_nums)),
            'pending_numbers': sorted(set(pending_nums)),
            'verified_purchases': verified_count,
            'pending_purchases': pending_count,
            'total_spent_verified': total_spent,
            'date_joined': u.date_joined.isoformat() if getattr(u, 'date_joined', None) else None,
        })

    # Guests: purchases with no user link
    guest_qs = LotteryPurchase.objects.filter(user__isnull=True).order_by('-created_at')
    guests = {}
    for p in guest_qs[:200]:
        key = (p.phone or '').strip() or f'guest-{p.id}'
        bucket = guests.setdefault(key, {
            'id': None,
            'telegram_id': None,
            'phone': p.phone,
            'first_name': p.full_name,
            'username': '',
            'preferred_language': '',
            'verified_numbers': [],
            'pending_numbers': [],
            'verified_purchases': 0,
            'pending_purchases': 0,
            'total_spent_verified': 0.0,
            'date_joined': None,
            'is_guest': True,
        })
        nums = [int(n) for n in (p.numbers or []) if str(n).isdigit() or isinstance(n, int)]
        if p.status == 'verified':
            bucket['verified_numbers'].extend(nums)
            bucket['verified_purchases'] += 1
            bucket['total_spent_verified'] += float(p.amount or 0)
        elif p.status == 'pending':
            bucket['pending_numbers'].extend(nums)
            bucket['pending_purchases'] += 1

    for g in guests.values():
        g['verified_numbers'] = sorted(set(g['verified_numbers']))
        g['pending_numbers'] = sorted(set(g['pending_numbers']))
        users_out.append(g)

    return JsonResponse({
        'users': users_out,
        'count': len(users_out),
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_announce_winner(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}

    winner_number = str(body.get('winner_number') or '').strip()
    message = (body.get('message') or '').strip()
    if not winner_number:
        return JsonResponse({'error': 'Winner number is required'}, status=400)

    settings_obj = LotterySettings.get_settings()
    settings_obj.winner_number = winner_number
    settings_obj.winner_message = message
    settings_obj.winner_announced_at = timezone.now()
    settings_obj.save(reset_timer=False)

    announce = message or f'🎉 Winner announced! Winning number: {winner_number}'
    full_msg = f'{announce}\n\nWinning number: {str(winner_number).zfill(3)}'

    notified = 0
    try:
        from telegram_bot.notifications import send_notification_sync
        try:
            win_int = int(winner_number)
        except ValueError:
            win_int = None
        for p in LotteryPurchase.objects.filter(status='verified').select_related('user'):
            if not (p.user and p.user.telegram_id):
                continue
            nums = []
            for n in p.numbers or []:
                try:
                    nums.append(int(n))
                except (TypeError, ValueError):
                    pass
            if win_int is not None and win_int in nums:
                send_notification_sync(p.user.telegram_id, f'🏆 Congratulations!\n\n{full_msg}')
            else:
                send_notification_sync(p.user.telegram_id, full_msg)
            notified += 1
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'winner_number': winner_number,
        'notified': notified,
        'settings': settings_obj.to_public_dict(request),
    })
