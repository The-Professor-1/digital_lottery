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
from .models import LotterySettings, LotteryPurchase, LotteryFailedDeposit, DeletedLotteryReceipt, DeletedLotteryUser


def _is_admin(request):
    if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False):
        return True
    if request.session.get('second_admin_authenticated'):
        return True
    return False


def _is_main_admin(request):
    return bool(
        getattr(request.user, 'is_authenticated', False)
        and request.user.is_authenticated
        and (request.user.is_staff or request.user.is_superuser)
    )


def _is_second_admin_only(request):
    """Admin View session without staff/superuser Django login."""
    if _is_main_admin(request):
        return False
    return bool(request.session.get('second_admin_authenticated'))


def _should_archive_admin_view(request, body=None):
    """
    Archive when action comes from Admin View.

    Important: main admin + Admin View often share one browser cookie jar.
    If staff is still logged in, `_is_second_admin_only` would be False and
    deletes would not be archived. Prefer explicit `from_admin_view` from SPA.
    """
    body = body or {}
    if body.get('from_admin_view'):
        return _is_admin(request)
    return _is_second_admin_only(request)


def _second_admin_label(request):
    return (request.session.get('second_admin_username') or 'admin-view').strip() or 'admin-view'


def _archive_purchase_for_second_admin(purchase, action, request):
    """Persist receipt snapshot before Admin View removes it from live tables."""
    telegram_id = None
    if purchase.user_id and purchase.user:
        telegram_id = purchase.user.telegram_id
    DeletedLotteryReceipt.objects.create(
        original_purchase_id=purchase.id,
        action=action,
        prior_status=purchase.status or '',
        full_name=purchase.full_name or '',
        phone=purchase.phone or '',
        numbers=list(purchase.numbers or []),
        quantity=purchase.quantity or 1,
        amount=purchase.amount or 0,
        bank_name=purchase.bank_name or '',
        bank_holder=purchase.bank_holder or '',
        bank_account=purchase.bank_account or '',
        paid_from_account=purchase.paid_from_account or '',
        receipt_hash=purchase.receipt_hash or '',
        admin_note=purchase.admin_note or '',
        telegram_id=telegram_id,
        original_created_at=purchase.created_at,
        removed_by=_second_admin_label(request),
    )


def _hard_delete_purchase(purchase):
    try:
        if purchase.receipt_image:
            purchase.receipt_image.delete(save=False)
    except Exception:
        pass
    purchase.delete()


def _archive_user_for_second_admin(user, purchases, request, is_guest=False, guest_phone='', guest_name=''):
    verified_numbers = []
    pending_numbers = []
    total_spent = Decimal('0')
    for p in purchases:
        nums = [int(n) for n in (p.numbers or []) if str(n).isdigit() or isinstance(n, int)]
        if p.status == 'verified':
            verified_numbers.extend(nums)
            total_spent += Decimal(str(p.amount or 0))
        elif p.status == 'pending':
            pending_numbers.extend(nums)

    DeletedLotteryUser.objects.create(
        original_user_id=getattr(user, 'id', None),
        telegram_id=getattr(user, 'telegram_id', None) if user else None,
        phone=(getattr(user, 'phone_number', None) or guest_phone or ''),
        first_name=(getattr(user, 'first_name', None) or guest_name or ''),
        username=(getattr(user, 'username', None) or ''),
        preferred_language=(getattr(user, 'preferred_language', None) or ''),
        is_guest=bool(is_guest),
        purchase_count=len(purchases),
        verified_numbers=sorted(set(verified_numbers)),
        pending_numbers=sorted(set(pending_numbers)),
        total_spent_verified=total_spent,
        date_joined=getattr(user, 'date_joined', None) if user else None,
        removed_by=_second_admin_label(request),
    )


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


def _calendar_periods(now=None):
    """Exact calendar windows in Africa/Addis_Ababa (not rolling hours/days). Weeks = Monday–Sunday."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo('Africa/Addis_Ababa')
    except Exception:
        tz = timezone.get_current_timezone()

    now = (now or timezone.now()).astimezone(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_start

    days_since_monday = now.weekday()  # Mon=0 … Sun=6
    week_start = today_start - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=7)

    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start

    month_start = today_start.replace(day=1)
    if now.month == 12:
        month_end = today_start.replace(year=now.year + 1, month=1, day=1)
    else:
        month_end = today_start.replace(month=now.month + 1, day=1)

    if now.month == 1:
        last_month_start = today_start.replace(year=now.year - 1, month=12, day=1)
    else:
        last_month_start = today_start.replace(month=now.month - 1, day=1)
    last_month_end = month_start

    return {
        'today': (today_start, today_end),
        'yesterday': (yesterday_start, yesterday_end),
        'this_week': (week_start, week_end),
        'last_week': (last_week_start, last_week_end),
        'this_month': (month_start, month_end),
        'last_month': (last_month_start, last_month_end),
        # legacy aliases
        'week': (week_start, week_end),
        'month': (month_start, month_end),
    }


def _period_filter(qs, period, field='created_at'):
    """Filter by calendar period on `field`. `all` / unknown = no filter."""
    if not period or period == 'all':
        return qs
    bounds = _calendar_periods().get(period)
    if not bounds:
        return qs
    start, end = bounds
    return qs.filter(**{f'{field}__gte': start, f'{field}__lt': end})


def _verified_revenue(period='today'):
    """Sum verified amounts in a calendar window (by verified_at)."""
    qs = LotteryPurchase.objects.filter(status='verified')
    qs = _period_filter(qs, period, field='verified_at')
    total = qs.aggregate(total=Sum('amount'))['total'] or 0
    return float(total), qs.count()


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


def _detect_payment_provider(bank_id='', bank_name=''):
    s = f'{bank_id} {bank_name}'.lower()
    if 'tele' in s or 'ቴሌ' in s:
        return 'telebirr'
    if 'cbe' in s or 'commercial' in s:
        return 'cbe'
    return ''


def _available_numbers(settings_obj, count=24, exclude=None):
    """Return up to `count` free numbers for conflict UI."""
    taken = settings_obj.taken_numbers_set()
    exclude = set(exclude or [])
    available = []
    total = int(settings_obj.total_tickets or 0)
    for n in range(1, total + 1):
        if n in taken or n in exclude:
            continue
        available.append(n)
        if len(available) >= count:
            break
    return available


def _transaction_already_used(provider, reference, account_suffix=''):
    """Check Telebirr/CBE receipt tables and lottery purchases for prior use."""
    from .models import TelebirrReceipt, CbeReceipt

    ref = (reference or '').strip().upper()
    if not ref:
        return False
    if LotteryPurchase.objects.filter(transaction_ref__iexact=ref).exclude(status='rejected').exists():
        return True
    if provider == 'telebirr':
        return TelebirrReceipt.objects.filter(reference__iexact=ref).exists()
    if provider == 'cbe':
        suffix = (account_suffix or '').strip()
        qs = CbeReceipt.objects.filter(reference__iexact=ref)
        if suffix:
            qs = qs.filter(account_suffix=suffix)
        return qs.exists()
    return False


def _mark_receipt_used(provider, reference, account_suffix, user, amount):
    from .models import TelebirrReceipt, CbeReceipt

    ref = (reference or '').strip().upper()
    if not ref:
        return
    if provider == 'telebirr':
        TelebirrReceipt.objects.get_or_create(
            reference=ref,
            defaults={'user': user, 'amount': amount or 0},
        )
    elif provider == 'cbe':
        suffix = (account_suffix or '').strip()
        CbeReceipt.objects.get_or_create(
            reference=ref,
            account_suffix=suffix,
            defaults={'user': user, 'amount': amount or 0},
        )


@csrf_exempt
@require_http_methods(['POST'])
def lottery_submit_purchase(request):
    """
    Submit lottery ticket purchase with SMS receipt text.
    Flow: parse SMS → dedup transaction → verify via Telebirr/CBE API →
    verified purchase on success, pending (manual review) if API fails.
    """
    user = _bearer_user(request)

    content_type = (request.content_type or '').lower()
    if 'application/json' in content_type:
        try:
            body = json.loads(request.body) if request.body else {}
        except (json.JSONDecodeError, ValueError):
            body = {}
        full_name = (body.get('full_name') or '').strip()
        phone = (body.get('phone') or '').strip()
        paid_from = (body.get('paid_from_account') or '').strip()
        bank_id = (body.get('bank_id') or '').strip()
        bank_name = (body.get('bank_name') or '').strip()
        bank_holder = (body.get('bank_holder') or '').strip()
        bank_account = (body.get('bank_account') or '').strip()
        receipt_sms = (body.get('receipt_sms') or body.get('sms') or '').strip()
        numbers_raw = body.get('numbers') or []
    else:
        full_name = (request.POST.get('full_name') or '').strip()
        phone = (request.POST.get('phone') or '').strip()
        paid_from = (request.POST.get('paid_from_account') or '').strip()
        bank_id = (request.POST.get('bank_id') or '').strip()
        bank_name = (request.POST.get('bank_name') or '').strip()
        bank_holder = (request.POST.get('bank_holder') or '').strip()
        bank_account = (request.POST.get('bank_account') or '').strip()
        receipt_sms = (request.POST.get('receipt_sms') or request.POST.get('sms') or '').strip()
        try:
            numbers_raw = json.loads(request.POST.get('numbers') or '[]')
        except (json.JSONDecodeError, TypeError):
            numbers_raw = []

    if isinstance(numbers_raw, str):
        try:
            numbers_raw = json.loads(numbers_raw)
        except (json.JSONDecodeError, TypeError):
            numbers_raw = []
    numbers = [int(n) for n in numbers_raw if str(n).isdigit() or isinstance(n, int)]

    if not full_name or not phone:
        return JsonResponse({'error': 'Name and phone are required', 'error_code': 'missing_fields'}, status=400)
    if not numbers:
        return JsonResponse({'error': 'Select at least one number', 'error_code': 'missing_numbers'}, status=400)

    provider = _detect_payment_provider(bank_id, bank_name)
    provider_label = 'telebirr' if provider == 'telebirr' else ('CBE' if provider == 'cbe' else 'telebirr or CBE')

    if not provider:
        return JsonResponse({
            'error': 'Please choose a Telebirr or CBE payment account',
            'error_code': 'missing_provider',
        }, status=400)

    if not receipt_sms:
        return JsonResponse({
            'error': f'Please enter the full sms you received from {provider_label}',
            'error_code': 'incomplete_sms',
            'provider': provider,
        }, status=400)

    settings_obj = LotterySettings.get_settings()
    taken = settings_obj.taken_numbers_set()
    conflict = sorted({n for n in numbers if n in taken})
    if conflict:
        conflict_str = ', '.join(str(n).zfill(3) for n in conflict)
        available = _available_numbers(settings_obj, count=max(24, len(numbers) * 4), exclude=numbers)
        return JsonResponse({
            'error': (
                f'This number {conflict_str} is taken by another user '
                f'please choose different number from these'
            ),
            'error_code': 'numbers_taken',
            'taken': conflict,
            'available': available,
        }, status=409)

    from .telebirr_verify import (
        parse_telebirr_receipt_text,
        verify_telebirr_receipt,
        credited_party_matches,
        amount_from_api_total,
    )
    from .cbe_verify import parse_cbe_receipt_text, verify_cbe_receipt
    from .models import GameSettings

    parsed = None
    account_suffix = ''
    if provider == 'telebirr':
        parsed = parse_telebirr_receipt_text(receipt_sms)
    else:
        parsed = parse_cbe_receipt_text(receipt_sms)
        if parsed:
            account_suffix = parsed.get('account_suffix') or ''

    if not parsed or not parsed.get('reference'):
        return JsonResponse({
            'error': f'Please enter the full sms you received from {provider_label}',
            'error_code': 'incomplete_sms',
            'provider': provider,
        }, status=400)

    reference = str(parsed['reference']).strip().upper()
    sms_amount = parsed.get('amount') or Decimal('0')

    if _transaction_already_used(provider, reference, account_suffix):
        return JsonResponse({
            'error': 'This receipt was checked before, try again with genuine receipt',
            'error_code': 'already_verified',
            'reference': reference,
        }, status=409)

    amount = Decimal(settings_obj.ticket_price) * len(numbers)
    if user and user.phone_number and not phone:
        phone = user.phone_number

    if not user:
        from .models import User
        digits = ''.join(c for c in phone if c.isdigit())
        if digits:
            user = User.objects.filter(phone_number__icontains=digits[-9:]).order_by('-id').first()

    receipt_hash = hashlib.sha256(
        f'{provider}:{reference}:{account_suffix}:{receipt_sms[:200]}'.encode('utf-8')
    ).hexdigest()
    if LotteryPurchase.objects.filter(receipt_hash=receipt_hash).exists():
        return JsonResponse({
            'error': 'This receipt was checked before, try again with genuine receipt',
            'error_code': 'already_verified',
            'reference': reference,
        }, status=409)

    def _save_failed(reason, credited=None):
        return LotteryFailedDeposit.objects.create(
            user=user,
            full_name=full_name,
            phone=phone,
            numbers=numbers,
            quantity=len(numbers),
            expected_amount=amount,
            credited_amount=credited,
            payment_provider=provider,
            bank_name=bank_name,
            bank_holder=bank_holder,
            bank_account=bank_account,
            transaction_ref=reference,
            account_suffix=account_suffix or '',
            receipt_sms=receipt_sms[:4000],
            failure_reason=(reason or '')[:255],
            status='pending',
        )

    api_key = settings_obj.resolved_verify_api_key()
    verify_ok = False
    verify_error = ''
    credited_amount = None
    api_data = None

    if not api_key:
        verify_error = 'verify_api_key_not_configured'
        failed = _save_failed(verify_error)
        return JsonResponse({
            'success': True,
            'verified': False,
            'manual_review': True,
            'message': 'Due to system problem your request is sent to manual review please wait moment',
            'message_key': 'manualReview',
            'failed_id': failed.id,
        })

    try:
        if provider == 'telebirr':
            result = verify_telebirr_receipt(reference, api_key)
            if result.get('success') and result.get('data'):
                api_data = result['data']
                if bank_holder or bank_account:
                    credited_name = (api_data.get('creditedPartyName') or '').strip()
                    credited_account_no = (api_data.get('creditedPartyAccountNo') or '').strip()
                    _ = credited_party_matches(credited_name, credited_account_no, bank_holder, bank_account)
                credited_amount = amount_from_api_total(api_data.get('totalPaidAmount') or '')
                if credited_amount is None:
                    credited_amount = sms_amount
                verify_ok = True
            else:
                verify_error = result.get('error') or 'verification_failed'
        else:
            gs = GameSettings.get_settings()
            use_fallback = bool(getattr(gs, 'cbe_use_fallback_proxy', False))
            result = verify_cbe_receipt(reference, account_suffix, api_key, use_fallback_proxy=use_fallback)
            if result.get('success') and result.get('data'):
                api_data = result['data']
                raw_amt = api_data.get('amount') or api_data.get('totalPaidAmount') or api_data.get('paidAmount')
                if raw_amt is not None:
                    try:
                        credited_amount = Decimal(str(raw_amt).replace(',', '').replace('ETB', '').replace('Birr', '').strip())
                    except Exception:
                        credited_amount = sms_amount
                else:
                    credited_amount = sms_amount
                verify_ok = True
            else:
                verify_error = result.get('error') or 'verification_failed'
    except Exception as e:
        verify_error = str(e) or 'api_exception'

    if not verify_ok:
        failed = _save_failed(verify_error or 'verification_failed', credited_amount)
        return JsonResponse({
            'success': True,
            'verified': False,
            'manual_review': True,
            'message': 'Due to system problem your request is sent to manual review please wait moment',
            'message_key': 'manualReview',
            'failed_id': failed.id,
        })

    # Require credited/SMS amount to match ticket total (quantity × ticket price)
    check_amount = credited_amount if credited_amount is not None else sms_amount
    if check_amount is None or abs(Decimal(check_amount) - amount) > Decimal('0.01'):
        reason = (
            f'amount_mismatch: expected {amount} Birr '
            f'(got {check_amount if check_amount is not None else "unknown"})'
        )
        failed = _save_failed(reason, check_amount)
        return JsonResponse({
            'error': (
                f'Payment amount ({check_amount} Birr) does not match required ticket total '
                f'({amount} Birr = {len(numbers)} × {settings_obj.ticket_price}). '
                f'Your request was saved for manual review.'
            ),
            'error_code': 'amount_mismatch',
            'expected_amount': float(amount),
            'credited_amount': float(check_amount) if check_amount is not None else None,
            'failed_id': failed.id,
            'manual_review': True,
        }, status=400)

    taken = settings_obj.taken_numbers_set()
    conflict = sorted({n for n in numbers if n in taken})
    if conflict:
        conflict_str = ', '.join(str(n).zfill(3) for n in conflict)
        available = _available_numbers(settings_obj, count=max(24, len(numbers) * 4), exclude=numbers)
        return JsonResponse({
            'error': (
                f'This number {conflict_str} is taken by another user '
                f'please choose different number from these'
            ),
            'error_code': 'numbers_taken',
            'taken': conflict,
            'available': available,
        }, status=409)

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
        receipt_sms=receipt_sms[:4000],
        payment_provider=provider,
        transaction_ref=reference,
        receipt_hash=receipt_hash,
        status='verified',
        verified_at=timezone.now(),
    )
    try:
        _mark_receipt_used(provider, reference, account_suffix, user, amount)
    except Exception:
        pass
    return JsonResponse({
        'success': True,
        'verified': True,
        'message': 'Payment verified successfully!',
        'message_key': 'paymentVerified',
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
        data['verify_api_key'] = settings_obj.verify_api_key or ''
        data['has_verify_api_key'] = bool((settings_obj.verify_api_key or '').strip())
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

        str_fields = [
            'brand_name', 'car_name', 'car_color', 'car_image_url', 'display_name',
            'hero_title', 'verify_api_key',
        ]
        int_fields = [
            'ticket_price', 'total_tickets', 'sold_count',
            'countdown_days', 'countdown_hours', 'countdown_minutes', 'countdown_seconds',
            'prize_1st', 'prize_2nd', 'prize_3rd', 'next_round_minutes',
            'winner_reveal_seconds',
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

        if getattr(settings_obj, 'next_round_minutes', 0) < 1:
            settings_obj.next_round_minutes = 10
        if getattr(settings_obj, 'winner_reveal_seconds', 0) < 2:
            settings_obj.winner_reveal_seconds = 6
        elif int(settings_obj.winner_reveal_seconds or 0) > 60:
            settings_obj.winner_reveal_seconds = 60

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

        if 'verify_api_key' in data and data.get('verify_api_key') is not None:
            try:
                from .models import GameSettings
                gs = GameSettings.get_settings()
                gs.telebirr_verify_api_key = str(data.get('verify_api_key') or '').strip()
                gs.save(update_fields=['telebirr_verify_api_key'])
            except Exception:
                pass

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
        out['verify_api_key'] = settings_obj.verify_api_key or ''
        out['has_verify_api_key'] = bool((settings_obj.verify_api_key or '').strip())
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
    revenue_period = (request.GET.get('revenue_period') or 'today').strip()

    qs = LotteryPurchase.objects.all().select_related('user')
    if status in ('pending', 'verified', 'rejected'):
        qs = qs.filter(status=status)
    qs = _period_filter(qs, period, field='created_at')

    revenue_amount, revenue_count = _verified_revenue(revenue_period)
    # Keep today keys for older UI; also return selected period revenue
    revenue_today, verified_today_count = _verified_revenue('today')

    return JsonResponse({
        'purchases': [p.to_dict(request) for p in qs[:200]],
        'revenue_today': revenue_today,
        'verified_today_count': verified_today_count,
        'revenue_period': revenue_period,
        'revenue_amount': revenue_amount,
        'revenue_count': revenue_count,
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

        # Prevent SMS reuse after manual verify
        if purchase.transaction_ref:
            try:
                suffix = ''
                provider = (purchase.payment_provider or '').strip().lower()
                if provider == 'cbe' and purchase.receipt_sms:
                    from .cbe_verify import parse_cbe_receipt_text
                    parsed = parse_cbe_receipt_text(purchase.receipt_sms)
                    if parsed:
                        suffix = parsed.get('account_suffix') or ''
                _mark_receipt_used(
                    provider,
                    purchase.transaction_ref,
                    suffix,
                    purchase.user,
                    purchase.amount,
                )
            except Exception:
                pass

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
        if purchase.user_id and purchase.user and purchase.user.telegram_id:
            msg = '❌ Your payment receipt was not approved. Please contact support or submit again with a clearer receipt.'
            if note:
                msg += f'\n\nNote: {note}'
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(purchase.user.telegram_id, msg)
            except Exception:
                pass

        # Admin View: archive + hard-remove so no personal info remains in their list
        if _should_archive_admin_view(request, body):
            purchase.admin_note = note
            _archive_purchase_for_second_admin(purchase, 'reject', request)
            deleted_id = purchase.id
            _hard_delete_purchase(purchase)
            return JsonResponse({'success': True, 'deleted': deleted_id, 'archived': True, 'action': 'reject'})

        purchase.status = 'rejected'
        purchase.admin_note = note
        purchase.save()
        return JsonResponse({'success': True, 'purchase': purchase.to_dict(request)})

    if action == 'delete':
        # Allow deleting verified/rejected/pending to free numbers after test purchases
        if purchase.status not in ('verified', 'rejected', 'pending'):
            return JsonResponse({'error': 'Cannot delete this status'}, status=400)
        deleted_id = purchase.id
        archive = _should_archive_admin_view(request, body)
        if archive:
            _archive_purchase_for_second_admin(purchase, 'delete', request)
        _hard_delete_purchase(purchase)
        return JsonResponse({
            'success': True,
            'deleted': deleted_id,
            'archived': archive,
        })

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
def lottery_user_delete(request):
    """Delete a registered user (and their lottery purchases) or guest purchases by phone."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}

    user_id = body.get('user_id')
    phone = (body.get('phone') or '').strip()

    from .models import User

    deleted_purchases = 0
    deleted_user = False

    if user_id:
        try:
            u = User.objects.get(id=int(user_id))
        except (User.DoesNotExist, TypeError, ValueError):
            return JsonResponse({'error': 'User not found'}, status=404)
        # Free numbers: remove purchases tied to this user / phone
        phone_digits = ''.join(c for c in (u.phone_number or '') if c.isdigit())
        qs = LotteryPurchase.objects.filter(user=u)
        if len(phone_digits) >= 9:
            qs = LotteryPurchase.objects.filter(
                Q(user=u) | Q(phone__icontains=phone_digits[-9:])
            )
        purchases = list(qs)
        archive = _should_archive_admin_view(request, body)
        if archive:
            _archive_user_for_second_admin(u, purchases, request, is_guest=False)
            for p in purchases:
                _archive_purchase_for_second_admin(p, 'delete', request)
        for p in purchases:
            try:
                if p.receipt_image:
                    p.receipt_image.delete(save=False)
            except Exception:
                pass
        deleted_purchases = len(purchases)
        qs.delete()
        u.delete()
        deleted_user = True
        return JsonResponse({
            'success': True,
            'deleted_user': deleted_user,
            'deleted_purchases': deleted_purchases,
            'archived': archive,
        })

    if phone:
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) < 9:
            return JsonResponse({'error': 'Phone too short'}, status=400)
        qs = LotteryPurchase.objects.filter(
            Q(phone__icontains=digits[-9:]) | Q(phone__icontains=digits)
        )
        purchases = list(qs)
        archive = _should_archive_admin_view(request, body)
        if archive:
            guest_name = (purchases[0].full_name if purchases else '') or ''
            _archive_user_for_second_admin(
                None, purchases, request,
                is_guest=True, guest_phone=phone, guest_name=guest_name,
            )
            for p in purchases:
                _archive_purchase_for_second_admin(p, 'delete', request)
        for p in purchases:
            try:
                if p.receipt_image:
                    p.receipt_image.delete(save=False)
            except Exception:
                pass
        deleted_purchases = len(purchases)
        qs.delete()
        return JsonResponse({
            'success': True,
            'deleted_user': False,
            'deleted_purchases': deleted_purchases,
            'archived': archive,
        })

    return JsonResponse({'error': 'user_id or phone required'}, status=400)


@csrf_exempt
@require_http_methods(['GET'])
def lottery_deleted_admin(request):
    """Main admin only: full archived snapshots from Admin View removals."""
    if not _is_main_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    receipts = [r.to_admin_dict() for r in DeletedLotteryReceipt.objects.all()[:300]]
    users = [u.to_admin_dict() for u in DeletedLotteryUser.objects.all()[:300]]
    return JsonResponse({
        'deleted_receipts': receipts,
        'deleted_users': users,
        'receipt_count': len(receipts),
        'user_count': len(users),
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


@csrf_exempt
@require_http_methods(['POST'])
def lottery_send_message(request):
    """
    Admin broadcast / multicast Telegram messages.
    target:
      - all: every bot user with telegram_id
      - ticket_buyers: users with verified or pending lottery purchases
      - pending_deposits: users with pending (unprocessed) lottery purchases
      - user_ids: specific user IDs in body.user_ids
    """
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    message = (body.get('message') or '').strip()
    target = (body.get('target') or 'all').strip().lower()
    user_ids = body.get('user_ids') or []

    if not message:
        return JsonResponse({'error': 'Message is required'}, status=400)

    from .models import User, BroadcastMessage, BroadcastMessageRecipient
    from telegram_bot.notifications import send_notification_sync

    base = User.objects.filter(telegram_id__isnull=False)

    if target in ('all', 'broadcast'):
        users = base
    elif target in ('ticket_buyers', 'purchasers', 'ticket'):
        ids = LotteryPurchase.objects.filter(
            status__in=['pending', 'verified']
        ).exclude(user_id__isnull=True).values_list('user_id', flat=True).distinct()
        users = base.filter(id__in=ids)
    elif target in ('pending_deposits', 'pending', 'deposit_issues'):
        ids = LotteryPurchase.objects.filter(status='pending').exclude(
            user_id__isnull=True
        ).values_list('user_id', flat=True).distinct()
        users = base.filter(id__in=ids)
    elif target in ('selected', 'user_ids', 'users'):
        try:
            ids = [int(x) for x in user_ids]
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid user_ids'}, status=400)
        if not ids:
            return JsonResponse({'error': 'Select at least one user'}, status=400)
        users = base.filter(id__in=ids)
    else:
        return JsonResponse({
            'error': 'Invalid target. Use all, ticket_buyers, pending_deposits, or selected',
        }, status=400)

    broadcast = BroadcastMessage.objects.create(
        message_text=message,
        amount_added=None,
        sent_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
    )

    sent_count = 0
    for user in users.iterator():
        try:
            success, message_id = send_notification_sync(user.telegram_id, message)
            if success:
                sent_count += 1
                if message_id:
                    BroadcastMessageRecipient.objects.create(
                        broadcast=broadcast,
                        user=user,
                        telegram_id=user.telegram_id,
                        message_id=message_id,
                    )
        except Exception as e:
            print(f'lottery_send_message error user={user.id}: {e}')
            continue

    return JsonResponse({
        'success': True,
        'sent_count': sent_count,
        'broadcast_id': broadcast.id,
        'message': f'Message sent to {sent_count} user(s)',
    })


@csrf_exempt
@require_http_methods(['GET'])
def lottery_failed_deposits_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    status = (request.GET.get('status') or 'pending').strip()
    qs = LotteryFailedDeposit.objects.all().select_related('user')
    if status in ('pending', 'approved', 'rejected'):
        qs = qs.filter(status=status)
    items = [f.to_admin_dict() for f in qs[:300]]
    return JsonResponse({
        'failed_deposits': items,
        'pending_count': LotteryFailedDeposit.objects.filter(status='pending').count(),
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_failed_deposit_action(request, failed_id):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    action = (body.get('action') or '').strip().lower()
    txn_no = (body.get('transaction_ref') or body.get('txn_no') or '').strip().upper()

    try:
        failed = LotteryFailedDeposit.objects.select_related('user').get(id=failed_id)
    except LotteryFailedDeposit.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if action == 'reject':
        failed.status = 'rejected'
        failed.resolved_at = timezone.now()
        if getattr(request.user, 'is_authenticated', False) and request.user.is_authenticated:
            failed.resolved_by = request.user
        failed.save()
        return JsonResponse({'success': True, 'failed_deposit': failed.to_admin_dict()})

    if action != 'approve':
        return JsonResponse({'error': 'Unknown action'}, status=400)

    if failed.status == 'approved':
        return JsonResponse({'error': 'Already approved'}, status=400)
    if not txn_no:
        return JsonResponse({'error': 'Transaction number is required to approve'}, status=400)

    provider = (failed.payment_provider or '').strip().lower()
    suffix = (failed.account_suffix or '').strip()
    if _transaction_already_used(provider, txn_no, suffix):
        return JsonResponse({
            'error': 'This transaction number was already used. Enter a genuine unused txn no.',
        }, status=409)

    settings_obj = LotterySettings.get_settings()
    numbers = []
    for n in failed.numbers or []:
        try:
            numbers.append(int(n))
        except (TypeError, ValueError):
            pass
    taken = settings_obj.taken_numbers_set()
    conflict = [n for n in numbers if n in taken]
    if conflict:
        return JsonResponse({'error': f'Numbers already taken: {conflict}'}, status=409)

    amount = failed.expected_amount or (Decimal(settings_obj.ticket_price) * max(1, len(numbers)))
    receipt_hash = hashlib.sha256(
        f'manual:{provider}:{txn_no}:{failed.id}:{timezone.now().timestamp()}'.encode('utf-8')
    ).hexdigest()

    purchase = LotteryPurchase.objects.create(
        user=failed.user,
        full_name=failed.full_name,
        phone=failed.phone,
        numbers=numbers,
        quantity=len(numbers) or failed.quantity or 1,
        amount=amount,
        bank_name=failed.bank_name,
        bank_holder=failed.bank_holder,
        bank_account=failed.bank_account,
        receipt_sms=failed.receipt_sms,
        payment_provider=provider,
        transaction_ref=txn_no,
        receipt_hash=receipt_hash,
        status='verified',
        admin_note=f'Approved from failed deposit #{failed.id}',
        verified_at=timezone.now(),
        verified_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
    )
    try:
        _mark_receipt_used(provider, txn_no, suffix, failed.user, amount)
    except Exception:
        pass

    failed.status = 'approved'
    failed.admin_txn_no = txn_no
    failed.transaction_ref = txn_no or failed.transaction_ref
    failed.resolved_at = timezone.now()
    if getattr(request.user, 'is_authenticated', False) and request.user.is_authenticated:
        failed.resolved_by = request.user
    failed.save()

    if failed.user_id and failed.user and failed.user.telegram_id:
        nums = ', '.join(str(n).zfill(3) for n in numbers)
        try:
            from telegram_bot.notifications import send_notification_sync
            send_notification_sync(
                failed.user.telegram_id,
                f'✅ Payment approved!\n\nYour lottery numbers: {nums}\nAmount: {amount} Birr',
            )
        except Exception:
            pass

    return JsonResponse({
        'success': True,
        'failed_deposit': failed.to_admin_dict(),
        'purchase': purchase.to_dict(request),
    })


def _draw_response(settings_obj, notified=0, already_drawn=False):
    return {
        'success': True,
        'already_drawn': already_drawn,
        'winner_1st': settings_obj.winner_1st,
        'winner_2nd': settings_obj.winner_2nd,
        'winner_3rd': settings_obj.winner_3rd,
        'prize_1st': int(settings_obj.prize_1st or 0),
        'prize_2nd': int(settings_obj.prize_2nd or 0),
        'prize_3rd': int(settings_obj.prize_3rd or 0),
        'taken_numbers': settings_obj.verified_taken_numbers(),
        'next_round_at': settings_obj.next_round_at.isoformat() if settings_obj.next_round_at else None,
        'next_round_at_ms': int(settings_obj.next_round_at.timestamp() * 1000) if settings_obj.next_round_at else None,
        'next_round_minutes': int(settings_obj.next_round_minutes or 10),
        'winner_reveal_seconds': max(2, int(settings_obj.winner_reveal_seconds or 6)),
        'winners_notified': bool(settings_obj.winners_notified),
        'notified': notified,
    }


def _send_winner_dms(settings_obj):
    """Send Telegram DMs to holders of winning numbers. Returns count notified."""
    prizes = [
        (1, settings_obj.winner_1st, int(settings_obj.prize_1st or 0), '1ኛ እጣ'),
        (2, settings_obj.winner_2nd, int(settings_obj.prize_2nd or 0), '2ኛ እጣ'),
        (3, settings_obj.winner_3rd, int(settings_obj.prize_3rd or 0), '3ኛ እጣ'),
    ]
    notified = 0
    try:
        from telegram_bot.notifications import send_notification_sync
        for place, win_num, prize_amt, place_label in prizes:
            if not win_num:
                continue
            holders = LotteryPurchase.objects.filter(status='verified').select_related('user')
            for purchase in holders:
                nums = []
                for n in purchase.numbers or []:
                    try:
                        nums.append(int(n))
                    except (TypeError, ValueError):
                        pass
                if win_num not in nums:
                    continue
                if not (purchase.user and purchase.user.telegram_id):
                    continue
                msg = (
                    f'🏆 Congratulations!\n\n'
                    f'You won {place_label} (place #{place})!\n'
                    f'Winning number: {str(win_num).zfill(3)}\n'
                    f'Prize amount: {prize_amt:,} ብር\n\n'
                    f'Please contact support to claim your prize.'
                )
                ok, _ = send_notification_sync(purchase.user.telegram_id, msg)
                if ok:
                    notified += 1
    except Exception as e:
        print(f'_send_winner_dms error: {e}')
    return notified


@csrf_exempt
@require_http_methods(['POST', 'GET'])
def lottery_run_draw(request):
    """
    Run prize draw when countdown has ended (or return existing winners).
    Saves winners only — Telegram DMs are sent later via lottery_notify_winners
    after the live on-screen announce finishes.
    """
    import random

    settings_obj = LotterySettings.get_settings()
    now = timezone.now()
    ends = settings_obj.ends_at or settings_obj.compute_ends_at()

    # Allow draw when timer finished, or within last 5s (client race)
    if ends and now < ends - timedelta(seconds=5):
        remaining = int((ends - now).total_seconds())
        return JsonResponse({
            'error': 'Draw not ready yet',
            'error_code': 'too_early',
            'remaining_seconds': remaining,
            'draw_completed': bool(settings_obj.draw_completed),
            'taken_numbers': settings_obj.verified_taken_numbers(),
        }, status=400)

    if settings_obj.draw_completed and settings_obj.winner_1st:
        return JsonResponse(_draw_response(settings_obj, already_drawn=True))

    pool = settings_obj.verified_taken_numbers()
    if not pool:
        return JsonResponse({
            'error': 'No verified tickets to draw from',
            'error_code': 'no_tickets',
            'taken_numbers': [],
        }, status=400)

    random.shuffle(pool)
    winners = pool[: min(3, len(pool))]
    w1 = winners[0] if len(winners) > 0 else None
    w2 = winners[1] if len(winners) > 1 else None
    w3 = winners[2] if len(winners) > 2 else None

    settings_obj.winner_1st = w1
    settings_obj.winner_2nd = w2
    settings_obj.winner_3rd = w3
    settings_obj.winner_number = str(w1) if w1 else ''
    settings_obj.draw_completed = True
    settings_obj.winner_announced_at = now
    settings_obj.winners_notified = False
    # Next-round timer starts after live announce + notify, not at draw time
    settings_obj.next_round_at = None
    settings_obj.save(reset_timer=False)

    return JsonResponse(_draw_response(settings_obj, notified=0, already_drawn=False))


@csrf_exempt
@require_http_methods(['POST'])
def lottery_notify_winners(request):
    """
    Called after the live UI has finished announcing 1st/2nd/3rd.
    Sends Telegram DMs once and starts the next-round countdown.
    Guards against early calls so DMs are not sent before the live announce window ends.
    """
    settings_obj = LotterySettings.get_settings()
    now = timezone.now()

    if not settings_obj.draw_completed or not settings_obj.winner_1st:
        return JsonResponse({'error': 'No winners to notify', 'error_code': 'no_draw'}, status=400)

    # Wait until each place has had its on-screen interval (admin-configured)
    if not settings_obj.winners_notified and settings_obj.winner_announced_at:
        reveal_s = max(2, int(settings_obj.winner_reveal_seconds or 6))
        places = sum(
            1 for w in (settings_obj.winner_1st, settings_obj.winner_2nd, settings_obj.winner_3rd) if w
        )
        earliest = settings_obj.winner_announced_at + timedelta(seconds=reveal_s * max(1, places))
        if now < earliest - timedelta(seconds=1):
            remaining = int((earliest - now).total_seconds())
            return JsonResponse({
                'error': 'Live announce still in progress',
                'error_code': 'announce_in_progress',
                'remaining_seconds': max(1, remaining),
                **_draw_response(settings_obj, notified=0, already_drawn=True),
            }, status=400)

    notified = 0
    if not settings_obj.winners_notified:
        notified = _send_winner_dms(settings_obj)
        settings_obj.winners_notified = True

    if not settings_obj.next_round_at:
        mins = max(1, int(settings_obj.next_round_minutes or 10))
        settings_obj.next_round_at = now + timedelta(minutes=mins)

    settings_obj.save(reset_timer=False)

    return JsonResponse({
        **_draw_response(settings_obj, notified=notified, already_drawn=True),
        'message': 'Winners notified' if notified else 'Already notified',
    })

@csrf_exempt
@require_http_methods(['POST'])
def lottery_start_next_round(request):
    """
    Clear ticket purchases and winners, start a fresh countdown round.
    Allowed when next_round_at has passed (or draw completed and timer due).
    """
    settings_obj = LotterySettings.get_settings()
    now = timezone.now()

    if not settings_obj.draw_completed:
        return JsonResponse({'error': 'No completed draw to reset', 'error_code': 'no_draw'}, status=400)

    if settings_obj.next_round_at and now < settings_obj.next_round_at - timedelta(seconds=3):
        remaining = int((settings_obj.next_round_at - now).total_seconds())
        return JsonResponse({
            'error': 'Next round not ready yet',
            'error_code': 'too_early',
            'remaining_seconds': remaining,
        }, status=400)

    # Clear all live ticket records for a fresh round
    LotteryPurchase.objects.filter(status__in=['pending', 'verified', 'rejected']).delete()

    settings_obj.winner_1st = None
    settings_obj.winner_2nd = None
    settings_obj.winner_3rd = None
    settings_obj.winner_number = ''
    settings_obj.winner_message = ''
    settings_obj.winner_announced_at = None
    settings_obj.draw_completed = False
    settings_obj.winners_notified = False
    settings_obj.next_round_at = None
    settings_obj.save(reset_timer=True)

    return JsonResponse({
        'success': True,
        'message': 'New round started',
        'settings': settings_obj.to_public_dict(request),
    })
