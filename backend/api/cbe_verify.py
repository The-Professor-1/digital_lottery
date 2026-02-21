"""
CBE (Commercial Bank of Ethiopia) receipt text parser and verification API client.
Used for automatic deposit verification when user sends full CBE SMS text.
"""
import re
import logging
from decimal import Decimal
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Sample: "Dear Nigus, You have transfered ETB 6,625.00 to Jibril Shikuri on 17/02/2026..."
# Link: https://apps.cbe.com.et:100/?id=FT26048WBS7024627387
# From id we get reference = id[:-8] (FT26048WBS70), accountSuffix = id[-8:] (24627387)
# Amount to credit = transfer amount from text (first ETB X,XXX.XX), not API total (includes fees)

_CBE_ID_RE = re.compile(r'[?&]id=(FT[A-Z0-9]+)', re.IGNORECASE)
_CBE_AMOUNT_RE = re.compile(r'\bETB\s+([0-9,]+(?:\.[0-9]{1,2})?)\b', re.IGNORECASE)
_REQUIRED_MARKERS = ['transfered', 'ETB', 'CBE']


def parse_cbe_receipt_text(text: str) -> Optional[dict]:
    """
    Parse full CBE receipt SMS text.
    Extracts: transaction id from link (?id=FT...) -> reference, account_suffix;
    first ETB amount in text (transfer amount, not fees) -> amount.
    Returns dict with reference, account_suffix, amount, or None if invalid.
    """
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    if len(text) < 80:
        return None

    text_lower = text.lower()
    for marker in _REQUIRED_MARKERS:
        if marker.lower() not in text_lower:
            return None

    match = _CBE_ID_RE.search(text)
    if not match:
        return None
    full_id = match.group(1).strip().upper()
    if len(full_id) < 9:
        return None
    reference = full_id[:-8]
    account_suffix = full_id[-8:]

    amount_match = _CBE_AMOUNT_RE.search(text)
    if not amount_match:
        return None
    amount_str = amount_match.group(1).replace(',', '')
    try:
        amount = Decimal(amount_str)
    except Exception:
        return None
    if amount <= 0:
        return None

    return {
        'reference': reference,
        'account_suffix': account_suffix,
        'amount': amount,
    }


def verify_cbe_receipt(reference: str, account_suffix: str, api_key: str) -> dict:
    """
    Call verifyapi.leulzenebe.pro to verify a CBE receipt.
    Returns dict: success, data (payer, receiver, receiverAccount, amount, date, reference), error.
    """
    if not api_key or not reference or not account_suffix:
        return {'success': False, 'data': None, 'error': 'Missing API key, reference or accountSuffix'}

    url = 'https://verifyapi.leulzenebe.pro/verify-cbe'
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key,
    }
    payload = {'reference': reference, 'accountSuffix': account_suffix}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        body = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
    except requests.RequestException as e:
        logger.exception("CBE verify API request failed: %s", e)
        return {'success': False, 'data': None, 'error': str(e)}
    except ValueError as e:
        logger.exception("CBE verify API invalid JSON: %s", e)
        return {'success': False, 'data': None, 'error': 'Invalid response'}

    if not resp.ok:
        return {
            'success': False,
            'data': body.get('data') if isinstance(body, dict) else None,
            'error': body.get('error', body.get('message', resp.reason)) if isinstance(body, dict) else resp.reason,
        }

    if not (isinstance(body, dict) and body.get('success')):
        return {
            'success': False,
            'data': body.get('data') if isinstance(body, dict) else None,
            'error': body.get('error') or body.get('message', 'Verification failed') if isinstance(body, dict) else 'Verification failed',
        }

    return {
        'success': True,
        'data': body.get('data'),
        'error': None,
    }


def _first_name(full_name: str) -> str:
    if not full_name:
        return ''
    return (full_name.strip().split() or [''])[0].lower()


def _last4_digits(value: str) -> str:
    digits = re.sub(r'\D', '', str(value or ''))
    return digits[-4:] if len(digits) >= 4 else digits


def cbe_receiver_matches(
    api_receiver_name: str,
    api_receiver_account: str,
    expected_holder_name: str,
    expected_account_number: str,
) -> bool:
    """True if receiver first name and receiver account last 4 digits match our CBE settings."""
    expected_name = (expected_holder_name or '').strip()
    expected_number = (expected_account_number or '').strip()
    receiver_name = (api_receiver_name or '').strip()
    receiver_account = (api_receiver_account or '').strip()

    if expected_name and _first_name(receiver_name) != _first_name(expected_name):
        return False
    if expected_number and receiver_account:
        if _last4_digits(expected_number) != _last4_digits(receiver_account):
            return False
    if not expected_name and not expected_number:
        return False
    return True
