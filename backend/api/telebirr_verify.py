"""
Telebirr receipt text parser and verification API client.
Used for automatic deposit verification when user sends full Telebirr SMS text.
"""
import re
import logging
from decimal import Decimal
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Full format example:
# "Dear Negus You have transferred ETB 1.00 to Selomon Yimer (2519****1212) on 20/02/2026 05:27:51.
#  Your transaction number is DBK10S886V. The service fee is  ETB 0.87 ... Thank you for using telebirr Ethio telecom"

# Patterns to extract: amount (ETB X.XX), recipient "to Name (number)", transaction number "is XXXXX"
_AMOUNT_RE = re.compile(r'\bETB\s+([0-9]+(?:\.[0-9]{1,2})?)\b', re.IGNORECASE)
_TRANSACTION_NUMBER_RE = re.compile(
    r'(?:transaction\s+number|receipt\s+no\.?)\s+is\s+([A-Z0-9]+)',
    re.IGNORECASE
)
# "to Name (2519****1212)" or "to Name (number)"
_TO_RECIPIENT_RE = re.compile(r'\bto\s+([^(]+?)\s*\([0-9*]+\s*\)', re.IGNORECASE)

# Must contain these to consider text "full"
_REQUIRED_MARKERS = [
    'transferred',
    'ETB',
    'transaction number',
    'telebirr',
]


def parse_telebirr_receipt_text(text: str) -> Optional[dict]:
    """
    Parse full Telebirr receipt SMS text.
    Returns dict with keys: amount (Decimal), reference (transaction number), recipient_name (str),
    or None if format is invalid/incomplete.
    """
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    if len(text) < 100:
        return None

    text_lower = text.lower()
    for marker in _REQUIRED_MARKERS:
        if marker.lower() not in text_lower:
            return None

    amount_match = _AMOUNT_RE.search(text)
    # Prefer the first "ETB X.XX" which is usually the transfer amount (second can be service fee/balance)
    amount_str = amount_match.group(1) if amount_match else None
    if not amount_str:
        return None

    ref_match = _TRANSACTION_NUMBER_RE.search(text)
    reference = ref_match.group(1).strip() if ref_match else None
    if not reference:
        return None

    recipient_match = _TO_RECIPIENT_RE.search(text)
    recipient_name = (recipient_match.group(1).strip() if recipient_match else '').strip()

    try:
        amount = Decimal(amount_str)
    except Exception:
        return None

    return {
        'amount': amount,
        'reference': reference,
        'recipient_name': recipient_name,
    }


def verify_telebirr_receipt(reference: str, api_key: str) -> dict:
    """
    Call verifyapi.leulzenebe.pro to verify a Telebirr receipt by reference (transaction number).
    Returns dict:
      - success: bool
      - data: None or dict with payerName, creditedPartyName, totalPaidAmount, receiptNo, paymentDate, transactionStatus, etc.
      - error: str or None
    """
    if not api_key or not reference:
        return {'success': False, 'data': None, 'error': 'Missing API key or reference'}

    url = 'https://verifyapi.leulzenebe.pro/verify-telebirr'
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key,
    }
    payload = {'reference': reference}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        body = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
    except requests.RequestException as e:
        logger.exception("Telebirr verify API request failed: %s", e)
        return {'success': False, 'data': None, 'error': str(e)}
    except ValueError as e:
        logger.exception("Telebirr verify API invalid JSON: %s", e)
        return {'success': False, 'data': None, 'error': 'Invalid response'}

    if not resp.ok:
        err = body.get('error') or body.get('message') or resp.reason or f'HTTP {resp.status_code}'
        logger.warning("Telebirr verify API HTTP %s for ref %s: %s", resp.status_code, reference, err)
        return {
            'success': False,
            'data': body.get('data'),
            'error': err,
        }

    if not body.get('success'):
        err = body.get('error') or body.get('message') or 'Verification failed'
        logger.warning("Telebirr verify API success=false for ref %s: %s", reference, err)
        return {
            'success': False,
            'data': body.get('data'),
            'error': err,
        }

    return {
        'success': True,
        'data': body.get('data'),
        'error': None,
    }


def normalize_credited_party_for_comparison(name: str) -> str:
    """Normalize name for comparison: strip, lower, collapse spaces."""
    if not name:
        return ''
    return ' '.join(str(name).strip().lower().split())


def amount_from_api_total(total_paid_str: str) -> Optional[Decimal]:
    """Parse '101.00 Birr' or '101.00' from API totalPaidAmount."""
    if not total_paid_str:
        return None
    s = str(total_paid_str).replace('Birr', '').replace('birr', '').strip()
    try:
        return Decimal(s)
    except Exception:
        return None


def _first_name(full_name: str) -> str:
    """Extract first name (first word) for comparison."""
    if not full_name:
        return ''
    return (full_name.strip().split() or [''])[0].lower()


def _last4_digits(value: str) -> str:
    """Extract last 4 digits from phone/account string."""
    digits = re.sub(r'\D', '', str(value or ''))
    return digits[-4:] if len(digits) >= 4 else digits


def credited_party_matches(
    api_credited_name: str,
    api_credited_account_no: str,
    expected_holder_name: str,
    expected_account_number: str,
) -> bool:
    """
    Return True if the API credited party (receiver) matches our Telebirr account in settings.
    Match rules: (1) first name of credited party equals first name of our account holder,
    (2) last 4 digits of credited party account number equal last 4 digits of our account number.
    Both must match when both are provided in settings.
    """
    credited_name = (api_credited_name or '').strip()
    credited_account = (api_credited_account_no or '').strip()
    expected_name = (expected_holder_name or '').strip()
    expected_number = (expected_account_number or '').strip()

    # First name match (credited party = our account holder)
    if expected_name:
        if _first_name(credited_name) != _first_name(expected_name):
            return False
    # Last 4 digits of phone/account number match
    if expected_number and credited_account:
        if _last4_digits(expected_number) != _last4_digits(credited_account):
            return False
    # If we have no expected name but have number, we already checked number; if we have no number but have name, we already checked name
    if not expected_name and not expected_number:
        return False
    return True
