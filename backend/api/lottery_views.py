import hashlib
import json
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .auth_utils import get_user_from_token, generate_guest_jwt_token
from .models import (
    LotterySettings, LotteryPurchase, LotteryFailedDeposit, DeletedLotteryReceipt,
    DeletedLotteryUser, LotteryItem, LotteryHeldNumber, LotteryWinner, WebPushSubscription,
)


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
    """Submit a lottery purchase with a receipt screenshot for admin approval.

    The old SMS/API auto-verification path is disabled below; screenshots are
    stored as pending and an admin verifies them in the dashboard.
    """
    # Screenshot flow: admin approves the receipt, no automatic SMS/API check.
    if request.FILES.get('receipt') or request.FILES.get('receipt_image'):
        return _submit_screenshot_purchase(request)

    # Automatic SMS/API verification is intentionally disabled. The mini-app
    # now uploads a screenshot and an admin verifies it in the Receipts tab.
    return JsonResponse({
        'error': 'Please upload a payment screenshot. SMS verification is disabled.',
        'error_code': 'screenshot_required',
    }, status=400)

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
            'error': f'እባክዎ ከ {provider_label} የተቀበሉትን ሙሉ SMS አስገብተው እንደገና ይሞክሩ፡፡',
            'error_code': 'incomplete_sms',
            'provider': provider,
        }, status=400)

    settings_obj = LotterySettings.get_settings()
    taken = settings_obj.taken_numbers_set()
    conflict = sorted({n for n in numbers if n in taken})
    if conflict:
        kept = [n for n in numbers if n not in set(conflict)]
        conflict_str = ', '.join(str(n).zfill(3) for n in conflict)
        available = _available_numbers(
            settings_obj, count=max(24, len(conflict) * 6), exclude=kept
        )
        return JsonResponse({
            'error': (
                f'ይህ {conflict_str} ቁጥር በሌላ ሰው ተይዟል፡፡ '
                f'እባክዎ {len(conflict)} ተጨማሪ ቁጥር ከነዚህ ውስጥ ይምረጡ፡፡'
            ),
            'error_code': 'numbers_taken',
            'taken': conflict,
            'kept': kept,
            'need': len(conflict),
            'available': available,
        }, status=409)

    from .telebirr_verify import (
        parse_telebirr_receipt_text,
        verify_telebirr_receipt,
        credited_party_matches,
        _last4_digits,
    )
    from .cbe_verify import parse_cbe_receipt_text, verify_cbe_receipt, cbe_receiver_matches
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
            'error': f'እባክዎ ከ {provider_label} የተቀበሉትን ሙሉ SMS አስገብተው እንደገና ይሞክሩ፡፡',
            'error_code': 'incomplete_sms',
            'provider': provider,
        }, status=400)

    reference = str(parsed['reference']).strip().upper()
    sms_amount = parsed.get('amount') or Decimal('0')

    if _transaction_already_used(provider, reference, account_suffix):
        return JsonResponse({
            'error': 'ይህ ደረሰኝ ከዚህ በፊት አገልግሎት ላይ ውሏል እባክዎ አዲስ ያስገቡ፡፡ ',
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
            'error': 'ይህ ደረሰኝ ከዚህ በፊት አገልግሎት ላይ ውሏል እባክዎ አዲስ ያስገቡ፡፡ ',
            'error_code': 'already_verified',
            'reference': reference,
        }, status=409)

    def _save_failed(reason, credited=None, status='pending'):
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
            status=status,
        )

    def _amount_matches(expected, got):
        if got is None:
            return False
        try:
            return abs(Decimal(got) - Decimal(expected)) <= Decimal('0.01')
        except Exception:
            return False

    def _parse_money(raw):
        if raw is None or raw == '':
            return None
        try:
            s = (
                str(raw)
                .replace(',', '')
                .replace('ETB', '')
                .replace('Birr', '')
                .replace('birr', '')
                .strip()
            )
            return Decimal(s) if s else None
        except Exception:
            return None

    def _credited_amount_without_fee(api_payload, sms_amt):
        """Prefer transfer/settled amount; avoid fee-inclusive totals."""
        if not api_payload:
            return sms_amt if sms_amt and sms_amt > 0 else None
        for key in ('settledAmount', 'amount', 'transferredAmount', 'paidAmount', 'creditAmount'):
            parsed_amt = _parse_money(api_payload.get(key))
            if parsed_amt is not None and parsed_amt > 0:
                return parsed_amt
        total_paid = _parse_money(api_payload.get('totalPaidAmount'))
        fee = _parse_money(
            api_payload.get('serviceFee')
            or api_payload.get('fee')
            or api_payload.get('transactionFee')
        )
        if total_paid is not None and fee is not None and total_paid > fee:
            return total_paid - fee
        if sms_amt and sms_amt > 0:
            return sms_amt
        return total_paid

    def _sms_party_ok():
        if provider == 'telebirr':
            return credited_party_matches(
                (parsed.get('recipient_name') or '').strip(),
                '',
                bank_holder,
                bank_account,
            )
        expected_digits = ''.join(c for c in str(bank_account or '') if c.isdigit())
        if account_suffix and expected_digits:
            if expected_digits.endswith(account_suffix) or _last4_digits(expected_digits) == account_suffix[-4:]:
                return True
        return False

    def _reject(error, error_code, credited=None, **extra):
        # Auto-reject: keep audit row but do NOT enqueue for manual review
        failed = _save_failed(f'{error_code}: {error}'[:255], credited, status='rejected')
        payload = {
            'error': error,
            'error_code': error_code,
            'failed_id': failed.id,
            'manual_review': False,
        }
        payload.update(extra)
        if credited is not None:
            try:
                payload['credited_amount'] = float(credited)
            except Exception:
                payload['credited_amount'] = None
        return JsonResponse(payload, status=400)

    def _manual_review(reason, credited=None):
        failed = _save_failed(reason, credited)
        return JsonResponse({
            'success': True,
            'verified': False,
            'manual_review': True,
            'message': ' በሲስተም ችግር ምክንያት ጥያቄዎ ለተጨማሪ ማረጋገጫ ተልኳል እባክዎ ይጠብቁ፡፡ ',
            'message_key': 'manualReview',
            'failed_id': failed.id,
        })

    api_key = settings_obj.resolved_verify_api_key()
    verify_ok = False
    verify_error = ''
    credited_amount = None
    api_data = None
    party_ok = False

    if not api_key:
        amount_ok = _amount_matches(amount, sms_amount)
        party_ok = _sms_party_ok()
        if party_ok and amount_ok:
            return _manual_review('verify_api_key_not_configured', sms_amount)
        if not party_ok:
            return _reject(
                'የተላከበት አካውንት/ስም ከተመረጠው የባንክ አካውንት ጋር አይዛመድም፡፡',
                'party_mismatch',
                credited=sms_amount,
            )
        return _reject(
            (
                f'በቴክስቱ ያለው ገንዘብ ({sms_amount} Birr) ልክ አይደለም '
                f'({amount} Birr = {len(numbers)} × {settings_obj.ticket_price})፡፡'
            ),
            'amount_mismatch',
            credited=sms_amount,
            expected_amount=float(amount),
        )

    try:
        if provider == 'telebirr':
            result = verify_telebirr_receipt(reference, api_key)
            if result.get('success') and result.get('data'):
                api_data = result['data']
                credited_name = (api_data.get('creditedPartyName') or '').strip()
                credited_account_no = (api_data.get('creditedPartyAccountNo') or '').strip()
                party_ok = credited_party_matches(
                    credited_name, credited_account_no, bank_holder, bank_account
                )
                credited_amount = _credited_amount_without_fee(api_data, sms_amount)
                verify_ok = True
            else:
                verify_error = result.get('error') or 'verification_failed'
        else:
            gs = GameSettings.get_settings()
            use_fallback = bool(getattr(gs, 'cbe_use_fallback_proxy', False))
            result = verify_cbe_receipt(reference, account_suffix, api_key, use_fallback_proxy=use_fallback)
            if result.get('success') and result.get('data'):
                api_data = result['data']
                party_ok = cbe_receiver_matches(
                    api_data.get('receiver') or api_data.get('receiverName') or '',
                    api_data.get('receiverAccount') or api_data.get('creditedPartyAccountNo') or '',
                    bank_holder,
                    bank_account,
                )
                credited_amount = _credited_amount_without_fee(api_data, sms_amount)
                verify_ok = True
            else:
                verify_error = result.get('error') or 'verification_failed'
    except Exception as e:
        verify_error = str(e) or 'api_exception'

    if not verify_ok:
        amount_ok = _amount_matches(amount, sms_amount)
        party_ok = _sms_party_ok()
        if party_ok and amount_ok:
            return _manual_review(verify_error or 'verification_failed', sms_amount)
        if not party_ok:
            return _reject(
                'የተላከበት አካውንት/ስም ከተመረጠው የባንክ አካውንት ጋር አይዛመድም፡፡',
                'party_mismatch',
                credited=sms_amount,
            )
        return _reject(
            (
                f'በቴክስቱ ያለው ገንዘብ ({sms_amount} Birr) ልክ አይደለም '
                f'({amount} Birr = {len(numbers)} × {settings_obj.ticket_price})፡፡'
            ),
            'amount_mismatch',
            credited=sms_amount,
            expected_amount=float(amount),
        )

    check_amount = credited_amount if credited_amount is not None else sms_amount
    amount_ok = _amount_matches(amount, check_amount)

    if not party_ok:
        return _reject(
            'የተላከበት አካውንት/ስም ከተመረጠው የባንክ አካውንት ጋር አይዛመድም፡፡',
            'party_mismatch',
            credited=check_amount,
        )
    if not amount_ok:
        return _reject(
            (
                f'በቴክስቱ ያለው ገንዘብ ({check_amount} Birr) ልክ አይደለም '
                f'({amount} Birr = {len(numbers)} × {settings_obj.ticket_price})፡፡'
            ),
            'amount_mismatch',
            credited=check_amount,
            expected_amount=float(amount),
        )

    taken = settings_obj.taken_numbers_set()
    conflict = sorted({n for n in numbers if n in taken})
    if conflict:
        kept = [n for n in numbers if n not in set(conflict)]
        conflict_str = ', '.join(str(n).zfill(3) for n in conflict)
        available = _available_numbers(
            settings_obj, count=max(24, len(conflict) * 6), exclude=kept
        )
        return JsonResponse({
            'error': (
                f'ይህ {conflict_str} ቁጥር በሌላ ሰው ተይዟል፡፡ '
                f'እባክዎ {len(conflict)} ተጨማሪ ቁጥር ከነዚህ ውስጥ ይምረጡ፡፡'
            ),
            'error_code': 'numbers_taken',
            'taken': conflict,
            'kept': kept,
            'need': len(conflict),
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
        'message': 'ክፍያው ልክ መሆኑ ተረጋግጧል!',
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
            'hero_title', 'verify_api_key', 'bot_description', 'bot_short_description',
        ]
        int_fields = [
            'ticket_price', 'total_tickets', 'sold_count',
            'countdown_days', 'countdown_hours', 'countdown_minutes', 'countdown_seconds',
            'prize_1st', 'prize_2nd', 'prize_3rd', 'next_round_minutes',
            'winner_reveal_seconds', 'draw_timer_seconds',
        ]

        old_timer = (
            settings_obj.countdown_days,
            settings_obj.countdown_hours,
            settings_obj.countdown_minutes,
            settings_obj.countdown_seconds,
        )
        old_mode = settings_obj.draw_mode or LotterySettings.DRAW_MODE_DATE

        for field in str_fields:
            if field in data and data[field] is not None:
                setattr(settings_obj, field, str(data[field]).strip())

        for field in int_fields:
            if field in data and data[field] is not None and data[field] != '':
                try:
                    setattr(settings_obj, field, max(0, int(float(data[field]))))
                except (TypeError, ValueError):
                    pass

        if 'draw_mode' in data and data.get('draw_mode') is not None:
            mode = str(data.get('draw_mode') or '').strip().lower()
            if mode in (
                LotterySettings.DRAW_MODE_DATE,
                LotterySettings.DRAW_MODE_SOLD_OUT,
                LotterySettings.DRAW_MODE_MANUAL,
            ):
                settings_obj.draw_mode = mode

        if getattr(settings_obj, 'next_round_minutes', 0) < 1:
            settings_obj.next_round_minutes = 10
        if getattr(settings_obj, 'winner_reveal_seconds', 0) < 2:
            settings_obj.winner_reveal_seconds = 6
        elif int(settings_obj.winner_reveal_seconds or 0) > 60:
            settings_obj.winner_reveal_seconds = 60
        if getattr(settings_obj, 'draw_timer_seconds', 0) < 5:
            settings_obj.draw_timer_seconds = 60
        elif int(settings_obj.draw_timer_seconds or 0) > 600:
            settings_obj.draw_timer_seconds = 600

        if 'automatic_announcement' in data and data.get('automatic_announcement') is not None:
            raw = data.get('automatic_announcement')
            if isinstance(raw, bool):
                settings_obj.automatic_announcement = raw
            else:
                settings_obj.automatic_announcement = str(raw).lower() in (
                    '1', 'true', 'yes', 'on',
                )

        timer_touched = old_timer != (
            settings_obj.countdown_days,
            settings_obj.countdown_hours,
            settings_obj.countdown_minutes,
            settings_obj.countdown_seconds,
        )
        mode_changed = old_mode != (settings_obj.draw_mode or LotterySettings.DRAW_MODE_DATE)

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
        # Changing away from / to date mode should clear or set the public deadline correctly
        if mode_changed and not settings_obj.uses_date_deadline():
            settings_obj.save(clear_timer=True)
        else:
            settings_obj.save(
                reset_timer=timer_touched or force_reset or (
                    mode_changed and settings_obj.uses_date_deadline()
                )
            )

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

        # Push bot profile text to Telegram so owners don't need a bot restart
        try:
            _sync_telegram_bot_profile(settings_obj)
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


def _sync_telegram_bot_profile(settings_obj):
    """Update Telegram bot description / short description from LotterySettings."""
    from django.conf import settings as dj_settings
    import urllib.request
    import urllib.parse

    token = (getattr(dj_settings, 'TELEGRAM_BOT_TOKEN', '') or '').strip()
    if not token:
        return

    short = (settings_obj.bot_short_description or settings_obj.brand_name or 'Digital Lottery').strip()[:120]
    long_desc = (settings_obj.bot_description or '').strip()
    if not long_desc:
        brand = (settings_obj.brand_name or 'Digital Lottery').strip()
        long_desc = f'{brand}\n\nእንኳን ደህና መጡ።'

    for method, payload in (
        ('setMyDescription', {'description': long_desc}),
        ('setMyShortDescription', {'short_description': short}),
    ):
        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/{method}',
            data=data,
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp.read()
        except Exception as e:
            print(f'_sync_telegram_bot_profile {method}: {e}')


@csrf_exempt
@require_http_methods(['GET'])
def lottery_purchases_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    status = (request.GET.get('status') or 'pending').strip()
    period = (request.GET.get('period') or 'all').strip()
    revenue_period = (request.GET.get('revenue_period') or 'today').strip()

    qs = LotteryPurchase.objects.all().select_related('user', 'lottery_item')
    if status in ('pending', 'verified', 'rejected'):
        qs = qs.filter(status=status)
    item_id = request.GET.get('lottery_item_id')
    if item_id:
        try:
            qs = qs.filter(lottery_item_id=int(item_id))
        except (TypeError, ValueError):
            pass
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
        if purchase.lottery_item_id and purchase.lottery_item:
            scope_item = purchase.lottery_item
            others = set()
            for n in LotteryHeldNumber.objects.filter(lottery_item=scope_item).values_list('number', flat=True):
                try:
                    others.add(int(n))
                except (TypeError, ValueError):
                    pass
            for p in LotteryPurchase.objects.filter(status='verified', lottery_item=scope_item).exclude(id=purchase.id):
                for n in p.numbers or []:
                    try:
                        others.add(int(n))
                    except (TypeError, ValueError):
                        pass
        else:
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
                f'ክፍያው ልክ መሆኑ ተረጋግጧል!\n\n'
                f'የእጣ ቁጥርዎች: {nums}\n'
            )
            try:
                from telegram_bot.notifications import send_notification_sync
                send_notification_sync(purchase.user.telegram_id, msg)
            except Exception:
                pass

        return JsonResponse({'success': True, 'purchase': purchase.to_dict(request)})

    if action == 'reject':
        if purchase.user_id and purchase.user and purchase.user.telegram_id:
            msg = '❌ የክፍያ ጥያቄዎ ተቀባይነት አላገኘም እባክዎ እንደገና በትክክል ይሞክሩ.'
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


def _parse_ticket_numbers(raw, total_tickets):
    """Parse ints from list/string; validate against ticket range. Returns (nums, error)."""
    if raw is None:
        raw = []
    if isinstance(raw, str):
        parts = [p for p in raw.replace(';', ',').replace(' ', ',').split(',') if p.strip()]
        raw = parts
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    nums = []
    for item in raw:
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if n < 1 or (total_tickets and n > int(total_tickets)):
            return None, f'Number {n} is out of range (1–{total_tickets})'
        nums.append(n)
    nums = sorted(set(nums))
    if not nums:
        return None, 'Enter at least one valid number'
    return nums, None


@csrf_exempt
@require_http_methods(['POST'])
def lottery_admin_hold_ticket(request):
    """
    Walk-in / offline sale: admin reserves numbers for a person (name + phone).
    Creates a verified purchase so numbers appear taken in the picker.
    """
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}

    full_name = (body.get('full_name') or body.get('name') or '').strip()
    phone = (body.get('phone') or '').strip()
    settings_obj = LotterySettings.get_settings()
    numbers, err = _parse_ticket_numbers(
        body.get('numbers') if body.get('numbers') is not None else body.get('number'),
        settings_obj.total_tickets,
    )
    if not full_name:
        return JsonResponse({'error': 'Name is required', 'error_code': 'missing_name'}, status=400)
    if not phone:
        return JsonResponse({'error': 'Phone is required', 'error_code': 'missing_phone'}, status=400)
    if err:
        return JsonResponse({'error': err, 'error_code': 'invalid_numbers'}, status=400)

    taken = settings_obj.taken_numbers_set()
    conflict = sorted(n for n in numbers if n in taken)
    if conflict:
        conflict_str = ', '.join(str(n).zfill(3) for n in conflict)
        return JsonResponse({
            'error': f'These numbers are already taken: {conflict_str}',
            'error_code': 'numbers_taken',
            'taken': conflict,
        }, status=409)

    from .models import User
    user = None
    digits = ''.join(c for c in phone if c.isdigit())
    if digits:
        user = User.objects.filter(phone_number__icontains=digits[-9:]).order_by('-id').first()

    amount = Decimal(settings_obj.ticket_price) * len(numbers)
    receipt_hash = hashlib.sha256(
        f'admin-hold:{timezone.now().isoformat()}:{phone}:{numbers}'.encode('utf-8')
    ).hexdigest()

    purchase = LotteryPurchase.objects.create(
        user=user,
        full_name=full_name,
        phone=phone,
        numbers=numbers,
        quantity=len(numbers),
        amount=amount,
        bank_name='Admin hold',
        bank_holder=full_name,
        bank_account='',
        paid_from_account='',
        receipt_sms='',
        payment_provider='admin',
        transaction_ref=f'ADMIN-{timezone.now().strftime("%Y%m%d%H%M%S")}',
        receipt_hash=receipt_hash,
        status='verified',
        verified_at=timezone.now(),
        admin_note='Walk-in / admin held ticket',
    )
    settings_obj.sold_count = len(settings_obj.taken_numbers_set())
    settings_obj.save(reset_timer=False)

    settings_payload = settings_obj.to_public_dict(request)
    settings_payload['admin_blocked_numbers'] = settings_obj.admin_blocked_numbers or []

    return JsonResponse({
        'success': True,
        'message': f'Held {len(numbers)} number(s) for {full_name}',
        'purchase': purchase.to_dict(request),
        'taken_numbers': sorted(settings_obj.taken_numbers_set()),
        'settings': settings_payload,
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_set_manual_winners(request):
    """
    Admin enters 1st/2nd/3rd after an offline/manual draw, then DMs holders.
    Used when draw_mode is manual or automatic announcement is off.
    """
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}

    settings_obj = LotterySettings.get_settings()
    if settings_obj.automatic_announcement and settings_obj.draw_mode != LotterySettings.DRAW_MODE_MANUAL:
        return JsonResponse({
            'error': 'Manual winner entry is only for manual draw mode (or when automatic announcement is off)',
            'error_code': 'auto_mode',
        }, status=400)

    def _one(key):
        raw = body.get(key)
        if raw is None or str(raw).strip() == '':
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    w1, w2, w3 = _one('winner_1st'), _one('winner_2nd'), _one('winner_3rd')
    if not w1:
        return JsonResponse({'error': '1st place number is required', 'error_code': 'missing_1st'}, status=400)

    total = int(settings_obj.total_tickets or 0)
    for label, n in (('1st', w1), ('2nd', w2), ('3rd', w3)):
        if n is None:
            continue
        if n < 1 or (total and n > total):
            return JsonResponse({
                'error': f'{label} place number {n} is out of range (1–{total})',
                'error_code': 'invalid_number',
            }, status=400)

    entered = [n for n in (w1, w2, w3) if n is not None]
    if len(entered) != len(set(entered)):
        return JsonResponse({
            'error': 'Winning numbers must be unique',
            'error_code': 'duplicate_winners',
        }, status=400)

    pool = set(settings_obj.verified_taken_numbers())
    missing = [n for n in entered if n not in pool]
    if missing:
        miss = ', '.join(str(n).zfill(3) for n in missing)
        return JsonResponse({
            'error': f'These numbers are not on any verified ticket: {miss}',
            'error_code': 'not_taken',
            'missing': missing,
        }, status=400)

    now = timezone.now()
    settings_obj.winner_1st = w1
    settings_obj.winner_2nd = w2
    settings_obj.winner_3rd = w3
    settings_obj.winner_number = str(w1)
    settings_obj.draw_completed = True
    settings_obj.winner_announced_at = now
    settings_obj.winners_notified = False
    settings_obj.next_round_at = None
    settings_obj.save(reset_timer=False)

    notified = _send_winner_dms(settings_obj)
    settings_obj.winners_notified = True
    if settings_obj.uses_date_deadline():
        mins = max(1, int(settings_obj.next_round_minutes or 10))
        settings_obj.next_round_at = now + timedelta(minutes=mins)
    settings_obj.save(reset_timer=False)

    settings_payload = settings_obj.to_public_dict(request)
    settings_payload['admin_blocked_numbers'] = settings_obj.admin_blocked_numbers or []

    return JsonResponse({
        'success': True,
        'message': f'Winners saved. Telegram DMs sent to {notified} holder(s).',
        'notified': notified,
        **_draw_response(settings_obj, notified=notified, already_drawn=False),
        'settings': settings_payload,
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

    announce = message or f'🎉 አሸናፊዎች ታውቀዋል! አሸናፊ ቁጥር: {winner_number}'
    full_msg = f'{announce}\n\nአሸናፊ ቁጥር: {str(winner_number).zfill(3)}'

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
                send_notification_sync(p.user.telegram_id, f'🏆 እንኳን ደስ አለዎት!\n\n{full_msg}')
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
                f'✅ ክፍያው ልክ መሆኑ ተረጋግጧል!\n\nየእጣ ቁጥርዎች: {nums}',
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
                    f'🏆 እንኳን ደስ አለዎት!\n\n'
                    f'{place}ኛ እጣ አሸንፈዋል!\n'
                    f'አሸናፊ ቁጥር: {str(win_num).zfill(3)}\n'
                    f'ገንዘብ: {prize_amt:,} ብር\n\n'
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
    ends = settings_obj.ends_at
    if ends is None and settings_obj.uses_date_deadline():
        ends = settings_obj.compute_ends_at()

    if not settings_obj.automatic_announcement:
        return JsonResponse({
            'error': 'Automatic announcement is off — winners are announced manually',
            'error_code': 'manual_announcement',
            'automatic_announcement': False,
        }, status=400)

    if ends is None:
        return JsonResponse({
            'error': 'Draw has not been started yet',
            'error_code': 'not_started',
            'draw_completed': bool(settings_obj.draw_completed),
            'taken_numbers': settings_obj.verified_taken_numbers(),
        }, status=400)

    # Allow draw when timer finished, or within last 5s (client race)
    if now < ends - timedelta(seconds=5):
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

    # Date mode auto-starts next round; sold_out / manual wait for admin Restart
    if settings_obj.uses_date_deadline() and not settings_obj.next_round_at:
        mins = max(1, int(settings_obj.next_round_minutes or 10))
        settings_obj.next_round_at = now + timedelta(minutes=mins)

    settings_obj.save(reset_timer=False)

    return JsonResponse({
        **_draw_response(settings_obj, notified=notified, already_drawn=True),
        'message': 'Winners notified' if notified else 'Already notified',
    })

def _clear_round_state(settings_obj, clear_tickets=True):
    """Clear winners / draw flags and optionally all ticket purchases."""
    if clear_tickets:
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

    _clear_round_state(settings_obj, clear_tickets=True)
    if settings_obj.uses_date_deadline():
        settings_obj.save(reset_timer=True)
    else:
        settings_obj.save(clear_timer=True)

    return JsonResponse({
        'success': True,
        'message': 'New round started',
        'settings': settings_obj.to_public_dict(request),
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_force_restart_round(request):
    """
    Admin emergency restart: apply countdown values, clear draw/winners/tickets,
    and start a fresh timer immediately. Use when the app is stuck (e.g. no tickets at draw).
    """
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    settings_obj = LotterySettings.get_settings()
    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    for field in (
        'countdown_days', 'countdown_hours', 'countdown_minutes', 'countdown_seconds',
    ):
        if field in data and data[field] is not None and data[field] != '':
            try:
                setattr(settings_obj, field, max(0, int(float(data[field]))))
            except (TypeError, ValueError):
                pass

    # Keep the admin's selected mode — never force back to date deadline
    if 'draw_mode' in data and data.get('draw_mode') is not None:
        mode = str(data.get('draw_mode') or '').strip().lower()
        if mode in (
            LotterySettings.DRAW_MODE_DATE,
            LotterySettings.DRAW_MODE_SOLD_OUT,
            LotterySettings.DRAW_MODE_MANUAL,
        ):
            settings_obj.draw_mode = mode
    # If client omitted draw_mode, leave the stored mode unchanged

    clear_tickets = str(data.get('clear_tickets', 'true')).lower() in ('1', 'true', 'yes', 'on')
    _clear_round_state(settings_obj, clear_tickets=clear_tickets)
    mode = settings_obj.draw_mode or LotterySettings.DRAW_MODE_DATE
    if mode == LotterySettings.DRAW_MODE_DATE:
        settings_obj.save(reset_timer=True)
        msg = 'Round restarted with a fresh countdown (date deadline mode)'
    else:
        settings_obj.save(clear_timer=True)
        msg = f'Round restarted in {mode} mode. Use Start Draw when ready.'

    out = settings_obj.to_public_dict(request)
    out['car_image_url_raw'] = settings_obj.car_image_url or ''
    out['admin_blocked_numbers'] = settings_obj.admin_blocked_numbers or []
    out['verify_api_key'] = settings_obj.verify_api_key or ''
    out['has_verify_api_key'] = bool((settings_obj.verify_api_key or '').strip())
    out['draw_mode'] = mode

    return JsonResponse({
        'success': True,
        'message': msg,
        'settings': out,
    })


@csrf_exempt
@require_http_methods(['POST'])
def lottery_start_draw(request):
    """
    Admin starts the pre-draw countdown UI (big timer), then automatic or manual
    announce runs when the timer hits zero — same as the final minute of date mode.
    """
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    settings_obj = LotterySettings.get_settings()
    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    if settings_obj.draw_completed:
        return JsonResponse({
            'error': 'Draw already completed. Restart the round first.',
            'error_code': 'draw_completed',
        }, status=400)

    try:
        seconds = int(float(data.get('timer_seconds', settings_obj.draw_timer_seconds or 60)))
    except (TypeError, ValueError):
        seconds = int(settings_obj.draw_timer_seconds or 60)
    seconds = max(5, min(600, seconds))

    if settings_obj.draw_mode == LotterySettings.DRAW_MODE_SOLD_OUT:
        taken = settings_obj.taken_numbers_set()
        total = max(1, int(settings_obj.total_tickets or 1))
        if len(taken) < total:
            # Allow override if admin forces it
            if str(data.get('force', '')).lower() not in ('1', 'true', 'yes', 'on'):
                return JsonResponse({
                    'error': f'Not sold out yet ({len(taken)}/{total}). Pass force=true to start anyway.',
                    'error_code': 'not_sold_out',
                    'sold_count': len(taken),
                    'total_tickets': total,
                }, status=400)

    settings_obj.draw_timer_seconds = seconds
    settings_obj.ends_at = timezone.now() + timedelta(seconds=seconds)
    settings_obj.save(reset_timer=False)

    out = settings_obj.to_public_dict(request)
    out['car_image_url_raw'] = settings_obj.car_image_url or ''
    out['admin_blocked_numbers'] = settings_obj.admin_blocked_numbers or []
    out['verify_api_key'] = settings_obj.verify_api_key or ''
    out['has_verify_api_key'] = bool((settings_obj.verify_api_key or '').strip())

    return JsonResponse({
        'success': True,
        'message': f'Draw started — {seconds}s countdown live for users',
        'settings': out,
    })

def _push_role(request):
    if _is_main_admin(request):
        return 'main'
    if request.session.get('second_admin_authenticated'):
        return 'view'
    return ''


@csrf_exempt
@require_http_methods(['GET'])
def lottery_push_vapid_key_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    from .push_notify import vapid_public_key
    return JsonResponse({'public_key': vapid_public_key() or ''})


@csrf_exempt
@require_http_methods(['POST'])
def lottery_push_subscribe_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    role = _push_role(request)
    if not role:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    sub = body.get('subscription') or {}
    endpoint = str(sub.get('endpoint') or '').strip()
    keys = sub.get('keys') or {}
    p256dh = str(keys.get('p256dh') or '').strip()
    auth = str(keys.get('auth') or '').strip()
    if not endpoint or not p256dh or not auth:
        return JsonResponse({'error': 'Invalid subscription'}, status=400)
    WebPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'role': role,
            'user': request.user if getattr(request.user, 'is_authenticated', False) else None,
            'p256dh': p256dh,
            'auth': auth,
        },
    )
    return JsonResponse({'success': True, 'role': role})


@csrf_exempt
@require_http_methods(['POST'])
def lottery_push_unsubscribe_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    endpoint = str(body.get('endpoint') or '').strip()
    if endpoint:
        WebPushSubscription.objects.filter(endpoint=endpoint).delete()
    return JsonResponse({'success': True})

def _json_body(request):
    try:
        return json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _normalize_prizes(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except (json.JSONDecodeError, ValueError):
            raw = []
    if not isinstance(raw, list):
        return []
    out = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        out.append({
            'place': str(entry.get('place') or f'{i + 1}'),
            'title': str(entry.get('title') or entry.get('description') or ''),
            'description': str(entry.get('description') or ''),
            'amount': int(float(entry.get('amount') or 0)),
            'image_url': str(entry.get('image_url') or '').strip(),
        })
    return out


def _api_file_url(request, file_field):
    if not file_field:
        return ''
    try:
        return request.build_absolute_uri(file_field.url)
    except Exception:
        return ''


@csrf_exempt
@require_http_methods(['GET'])
def lottery_items_public(request):
    """Landing page: active lottery items and latest winner announcements."""
    settings_obj = LotterySettings.get_settings()
    items = LotteryItem.objects.filter(is_active=True).order_by('sort_order', 'id')
    winners = LotteryWinner.objects.select_related('lottery_item').order_by('-announced_at', '-id')[:30]
    return JsonResponse({
        'brand_name': settings_obj.brand_name,
        'display_name': settings_obj.display_name,
        'payment_accounts': settings_obj.payment_accounts or [],
        'items': [it.to_public_dict(request) for it in items],
        'winners': [w.to_dict() for w in winners],
    })


@require_http_methods(['GET'])
def lottery_item_detail_public(request, item_id):
    item = LotteryItem.objects.filter(id=item_id, is_active=True).first()
    if item is None:
        return JsonResponse({'error': 'Lottery not found'}, status=404)
    settings_obj = LotterySettings.get_settings()
    data = item.to_public_dict(request, include_taken=True)
    data['brand_name'] = settings_obj.brand_name
    data['display_name'] = settings_obj.display_name
    data['payment_accounts'] = settings_obj.payment_accounts or []
    data['winners'] = [
        w.to_dict()
        for w in item.winners.select_related('lottery_item').order_by('-announced_at', '-id')[:30]
    ]
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def lottery_items_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    if request.method == 'GET':
        items = []
        for it in LotteryItem.objects.all().order_by('sort_order', 'id'):
            d = it.to_public_dict(request, include_taken=True)
            d['held_count'] = LotteryHeldNumber.objects.filter(lottery_item=it).count()
            d['winners_count'] = LotteryWinner.objects.filter(lottery_item=it).count()
            items.append(d)
        return JsonResponse({'items': items})

    data = request.POST.dict() if 'multipart/form-data' in (request.content_type or '').lower() else _json_body(request)
    action = (data.get('action') or '').strip().lower()
    item_id = data.get('id') or data.get('item_id')
    item = None
    if item_id:
        try:
            item = LotteryItem.objects.filter(id=int(item_id)).first()
        except (TypeError, ValueError):
            item = None
        if item is None:
            return JsonResponse({'error': 'Lottery not found'}, status=404)

    if action == 'delete':
        if item is None:
            return JsonResponse({'error': 'Lottery not found'}, status=404)
        item.delete()
        return JsonResponse({'success': True, 'deleted': item_id})

    if item is None:
        item = LotteryItem()

    for field in ('name', 'description', 'image_url', 'hero_title', 'draw_mode'):
        if field in data and data.get(field) is not None:
            setattr(item, field, str(data.get(field) or '').strip())
    if not item.name:
        item.name = 'Digital Lottery'
    for field, default in (('ticket_price', 3000), ('total_tickets', 3500), ('sort_order', 0),
                           ('draw_timer_seconds', 60), ('winner_reveal_seconds', 6),
                           ('next_round_minutes', 10), ('countdown_days', 12),
                           ('countdown_hours', 10), ('countdown_minutes', 24),
                           ('countdown_seconds', 45)):
        if field in data and data.get(field) not in (None, ''):
            try:
                setattr(item, field, max(0, int(float(data.get(field)))))
            except (TypeError, ValueError):
                pass
    if 'is_active' in data:
        item.is_active = _as_bool(data.get('is_active'), True)
    if 'automatic_announcement' in data:
        item.automatic_announcement = _as_bool(data.get('automatic_announcement'), True)
    if 'prizes' in data:
        item.prizes = _normalize_prizes(data.get('prizes'))
    elif item.pk is None:
        fallback = []
        for place, key in (('1st', 'prize_1st'), ('2nd', 'prize_2nd'), ('3rd', 'prize_3rd')):
            try:
                amount = int(float(data.get(key) or 0))
            except (TypeError, ValueError):
                amount = 0
            if amount:
                fallback.append({'place': place, 'title': f'{place} Prize',
                                 'description': '', 'amount': amount, 'image_url': ''})
        item.prizes = fallback
    image = request.FILES.get('image')
    if image:
        item.image = image
    reset_timer = _as_bool(data.get('reset_timer'), False)
    item.save(reset_timer=reset_timer)
    return JsonResponse({'success': True, 'item': item.to_public_dict(request, include_taken=True)})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def lottery_held_numbers_admin(request):
    """List/add/remove admin-held numbers, each with the owner's phone."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    if request.method == 'GET':
        raw_item = request.GET.get('lottery_item_id') or request.GET.get('item_id')
        item = None
        if raw_item:
            try:
                item = LotteryItem.objects.filter(id=int(raw_item)).first()
            except (TypeError, ValueError):
                item = None
        qs = LotteryHeldNumber.objects.all()
        qs = qs.filter(lottery_item=item) if item else qs.filter(lottery_item__isnull=True)
        rows = [{
            'id': h.id,
            'lottery_item_id': h.lottery_item_id,
            'number': h.number,
            'phone': h.phone,
            'name': h.name,
            'note': h.note,
            'created_at': h.created_at.isoformat() if h.created_at else None,
        } for h in qs.order_by('number')]
        return JsonResponse({'held_numbers': rows, 'item_id': item.id if item else None})

    body = _json_body(request)
    action = (body.get('action') or 'add').strip().lower()
    raw_item = body.get('lottery_item_id') or body.get('item_id')
    item = None
    if raw_item:
        try:
            item = LotteryItem.objects.filter(id=int(raw_item)).first()
        except (TypeError, ValueError):
            item = None
        if item is None:
            return JsonResponse({'error': 'Lottery not found'}, status=404)

    if action == 'delete':
        held_id = body.get('id')
        LotteryHeldNumber.objects.filter(id=held_id).delete()
        return JsonResponse({'success': True})

    phone = ''.join(c for c in str(body.get('phone') or '') if c.isdigit())
    name = str(body.get('name') or '').strip()
    note = str(body.get('note') or '').strip()

    def _add_one(number):
        try:
            number = int(number)
        except (TypeError, ValueError):
            return False
        if number < 1:
            return False
        existing = LotteryHeldNumber.objects.filter(lottery_item=item, number=number).first()
        if existing is not None:
            existing.phone = phone
            existing.name = name
            existing.note = note
            existing.save(update_fields=['phone', 'name', 'note'])
            return True
        if item is not None:
            if number in item.taken_numbers_set():
                return False
        else:
            if number in LotterySettings.get_settings().taken_numbers_set():
                return False
        LotteryHeldNumber.objects.create(
            lottery_item=item,
            number=number,
            phone=phone,
            name=name,
            note=note,
        )
        return True

    if action == 'bulk':
        numbers = body.get('numbers') or []
        if isinstance(numbers, str):
            numbers = [x for x in re.split(r'[^0-9]+', numbers) if x]
        added = 0
        skipped = []
        for n in numbers:
            if _add_one(n):
                added += 1
            else:
                skipped.append(n)
        return JsonResponse({'success': True, 'added': added, 'skipped': skipped})

    if _add_one(body.get('number')):
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Number is already taken or invalid'}, status=409)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def lottery_winners_admin(request):
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    if request.method == 'GET':
        qs = LotteryWinner.objects.select_related('lottery_item').order_by('-announced_at', '-id')
        item_id = request.GET.get('lottery_item_id')
        if item_id:
            try:
                qs = qs.filter(lottery_item_id=int(item_id))
            except (TypeError, ValueError):
                qs = qs.none()
        return JsonResponse({'winners': [w.to_dict() for w in qs[:200]]})
    body = _json_body(request)
    if (body.get('action') or '').strip().lower() == 'delete':
        LotteryWinner.objects.filter(id=body.get('id')).delete()
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Unknown action'}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def lottery_announce_item_winner(request):
    """Create an in-app winner entry and optionally DM all verified item buyers."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    body = _json_body(request)
    item_id = body.get('lottery_item_id') or body.get('item_id')
    item = None
    if item_id:
        try:
            item = LotteryItem.objects.filter(id=int(item_id)).first()
        except (TypeError, ValueError):
            item = None
        if item is None:
            return JsonResponse({'error': 'Lottery not found'}, status=404)

    number = str(body.get('winning_ticket') or body.get('winner_number') or '').strip()
    if not number:
        return JsonResponse({'error': 'Winning ticket is required'}, status=400)
    name = str(body.get('name') or '').strip()
    phone = ''.join(c for c in str(body.get('phone') or '') if c.isdigit())
    lottery_label = str(body.get('lottery_label') or '').strip()[:160]
    prize_name = str(body.get('prize_name') or '').strip()[:160]
    message = str(body.get('message') or '').strip()
    notify_users = _as_bool(body.get('notify_users'), True)

    pool = LotteryPurchase.objects.filter(status='verified').select_related('user')
    if item is not None:
        pool = pool.filter(lottery_item=item)
    else:
        pool = pool.filter(lottery_item__isnull=True)
    try:
        number_int = int(number)
    except (TypeError, ValueError):
        number_int = None
    winner_purchase = None
    if number_int is not None:
        for candidate in pool.order_by('-verified_at', '-id').iterator(chunk_size=200):
            try:
                if number_int in [int(n) for n in (candidate.numbers or [])]:
                    winner_purchase = candidate
                    break
            except (TypeError, ValueError):
                continue
    if winner_purchase is None and (item is not None or notify_users):
        winner_purchase = pool.order_by('-verified_at', '-id').first()

    if not name and winner_purchase:
        name = (winner_purchase.full_name or '')
    if not phone and winner_purchase:
        phone = winner_purchase.phone or ''
    if not lottery_label:
        lottery_label = item.name if item else (LotterySettings.get_settings().display_name or 'Lottery')
    if not prize_name:
        if item and item.normalized_prizes():
            prize_name = item.normalized_prizes()[0].get('title') or item.name
        else:
            prize_name = item.name if item else (LotterySettings.get_settings().display_name or '')

    winner = LotteryWinner.objects.create(
        lottery_item=item,
        winner_number=number,
        name=name,
        phone=phone,
        lottery_label=lottery_label,
        prize_name=prize_name,
        message=message,
        user=winner_purchase.user if winner_purchase and winner_purchase.user_id else None,
        announced_at=timezone.now(),
    )
    if item is not None:
        item.winner_announced_at = timezone.now()
        item.save(update_fields=['winner_announced_at'])
    settings_obj = LotterySettings.get_settings()
    settings_obj.winner_number = number
    settings_obj.winner_message = message
    settings_obj.winner_announced_at = timezone.now()
    settings_obj.save(update_fields=['winner_number', 'winner_message', 'winner_announced_at'])

    notified = 0
    if notify_users:
        try:
            from telegram_bot.notifications import send_notification_sync
            seen = set()
            for purchase in pool:
                if not (purchase.user and purchase.user.telegram_id):
                    continue
                tid = purchase.user.telegram_id
                if tid in seen:
                    continue
                seen.add(tid)
                text = (
                    '🏆 Winner announced!\n\n'
                    f'Lottery: {lottery_label}\n'
                    f'Name: {name}\n'
                    f'Phone: {phone}\n'
                    f'Winning ticket: #{str(number).zfill(3)}\n'
                    f'Prize: {prize_name}'
                )
                if message:
                    text += f'\n\n{message}'
                send_notification_sync(tid, text)
                notified += 1
        except Exception:
            pass
    return JsonResponse({
        'success': True,
        'winner': winner.to_dict(),
        'notified': notified,
    })


def _compress_receipt(uploaded, max_dimension=1280, quality=80):
    from io import BytesIO
    from PIL import Image, ImageOps, UnidentifiedImageError
    from django.core.files.base import ContentFile
    try:
        uploaded.seek(0)
        img = Image.open(uploaded)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True, progressive=True)
        return ContentFile(buffer.getvalue())
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    finally:
        try:
            uploaded.seek(0)
        except Exception:
            pass


def _get_or_create_guest(phone, full_name):
    from .models import User
    digits = ''.join(c for c in phone if c.isdigit())
    user = User.objects.filter(phone_number__icontains=digits[-9:]).order_by('-id').first() if digits else None
    if user:
        return user
    base = f'guest_{digits[-9:]}' if digits else 'guest'
    username = base
    n = 1
    while User.objects.filter(username=username).exists():
        username = f'{base}_{n}'
        n += 1
    return User.objects.create(username=username, first_name=(full_name or 'Guest')[:150], phone_number=digits)


def _submit_screenshot_purchase(request):
    full_name = (request.POST.get('full_name') or '').strip()
    phone = ''.join(c for c in (request.POST.get('phone') or '') if c.isdigit())
    try:
        numbers = json.loads(request.POST.get('numbers') or '[]')
    except (json.JSONDecodeError, ValueError):
        numbers = []
    numbers = [int(n) for n in numbers if str(n).isdigit() or isinstance(n, int)]
    receipt = request.FILES.get('receipt') or request.FILES.get('receipt_image')
    if not full_name or not phone:
        return JsonResponse({'error': 'Name and phone are required', 'error_code': 'missing_fields'}, status=400)
    if not numbers:
        return JsonResponse({'error': 'Select at least one number', 'error_code': 'missing_numbers'}, status=400)
    if not receipt:
        return JsonResponse({'error': 'Payment receipt image is required', 'error_code': 'missing_receipt'}, status=400)

    item = None
    item_id = request.POST.get('lottery_item_id')
    if item_id:
        try:
            item = LotteryItem.objects.filter(id=int(item_id), is_active=True).first()
        except (TypeError, ValueError):
            item = None
        if item is None:
            return JsonResponse({'error': 'Lottery not found'}, status=404)

    settings_obj = LotterySettings.get_settings()
    taken = item.taken_numbers_set() if item is not None else settings_obj.taken_numbers_set()
    conflict = sorted({n for n in numbers if n in taken})
    if conflict:
        return JsonResponse({
            'error': 'Some numbers are no longer available: ' + ', '.join(str(n).zfill(3) for n in conflict),
            'error_code': 'numbers_taken',
            'taken': conflict,
        }, status=409)

    receipt_hash = _file_sha256(receipt)
    if LotteryPurchase.objects.filter(receipt_hash=receipt_hash).exists():
        return JsonResponse({
            'error': 'This receipt image was already submitted. Use a different receipt.',
            'error_code': 'duplicate_receipt',
        }, status=409)

    compressed = _compress_receipt(receipt)
    if compressed:
        base = os.path.basename(receipt.name or '')
        stem, _dot, _ext = base.rpartition('.')
        receipt = compressed
        receipt.name = f'{stem or "receipt"}.jpg'

    price = item.ticket_price if item is not None else settings_obj.ticket_price
    amount = Decimal(price) * len(numbers)
    user = _get_or_create_guest(phone, full_name)
    bank_id = (request.POST.get('bank_id') or '').strip()
    bank_name = (request.POST.get('bank_name') or '').strip()
    bank_holder = (request.POST.get('bank_holder') or '').strip()
    bank_account = (request.POST.get('bank_account') or '').strip()
    item_name = (
        (item.name or '') if item is not None
        else (settings_obj.display_name or settings_obj.brand_name or '')
    )
    round_name = (
        (item.hero_title or item.name or '') if item is not None
        else (settings_obj.hero_title or settings_obj.display_name or settings_obj.brand_name or '')
    )
    purchase = LotteryPurchase.objects.create(
        user=user,
        lottery_item=item,
        lottery_item_name_snapshot=item_name,
        lottery_round_snapshot=round_name,
        full_name=full_name,
        phone=phone,
        numbers=numbers,
        quantity=len(numbers),
        amount=amount,
        bank_name=bank_name,
        bank_holder=bank_holder,
        bank_account=bank_account,
        paid_from_account=(request.POST.get('paid_from_account') or '').strip(),
        receipt_image=receipt,
        receipt_hash=receipt_hash,
        payment_provider=_detect_payment_provider(bank_id, bank_name),
        transaction_ref='',
        receipt_sms='',
        status='pending',
    )
    guest_token = generate_guest_jwt_token(user)
    if user.telegram_id:
        try:
            from telegram_bot.notifications import send_notification_sync
            nums = ', '.join(str(n).zfill(3) for n in numbers)
            lines = ['📥 Receipt received. Waiting for admin approval.', f'Lottery: {item_name or "—"}']
            if round_name:
                lines.append(f'Round: {round_name}')
            lines.append(f'Tickets: {nums}')
            send_notification_sync(user.telegram_id, '\n'.join(lines))
        except Exception:
            pass
    return JsonResponse({
        'success': True,
        'verified': False,
        'manual_review': True,
        'message_key': 'receiptPendingHint',
        'message': 'Receipt received. An admin will verify it shortly.',
        'guest_token': guest_token,
        'guest_phone': phone,
        'guest_name': full_name,
        'purchase': purchase.to_dict(request),
    })

@csrf_exempt
@require_http_methods(['POST'])
def lottery_prize_image_upload(request):
    """Upload one prize image and return a URL for the prize row."""
    if not _is_admin(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    image = request.FILES.get('image')
    if not image:
        return JsonResponse({'error': 'Image is required'}, status=400)
    from django.core.files.storage import default_storage
    from django.utils.text import get_valid_filename
    import uuid
    ext = os.path.splitext(get_valid_filename(image.name or ''))[1].lower() or '.jpg'
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
        ext = '.jpg'
    path = default_storage.save(f'lottery/prizes/{uuid.uuid4().hex}{ext}', image)
    return JsonResponse({'success': True, 'url': request.build_absolute_uri(default_storage.url(path))})
