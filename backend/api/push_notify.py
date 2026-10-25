"""Web Push support for the Digital Lottery admin dashboards.

Admins subscribe through the browser Push API. A new pending receipt triggers
a notification to every subscribed admin. If pywebpush or VAPID keys are not
available the helpers fail quietly so the app keeps working.
"""
import json
import os
import tempfile
import threading

from django.conf import settings
from django.utils import timezone

_VAPID_FILE_LOCK = threading.Lock()
_VAPID_FILE_NAME = 'vapid_keys.json'

_ROLE_PANEL_URL = {
    'main': '/admin-dashboard?tab=receipts',
    'view': '/admin-view?tab=receipts',
}


def _vapid_file_path():
    return os.path.join(settings.BASE_DIR, 'cache', _VAPID_FILE_NAME)


def _valid_vapid_keys(keys):
    return bool(
        isinstance(keys, dict)
        and str(keys.get('publicKey') or '').strip()
        and str(keys.get('privateKey') or '').strip()
    )


def _read_vapid_file():
    try:
        with open(_vapid_file_path(), 'r', encoding='utf-8') as fh:
            keys = json.load(fh)
        return keys if _valid_vapid_keys(keys) else None
    except (OSError, ValueError):
        return None


def _write_vapid_file(keys):
    path = _vapid_file_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='.vapid-', dir=directory, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(keys, fh)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _generate_vapid_keys():
    try:
        import base64
        import py_vapid
        from cryptography.hazmat.primitives import serialization as _ser

        vv = py_vapid.Vapid()
        vv.generate_keys()
        priv_pem = vv.private_pem()
        raw_public = vv.public_key.public_bytes(
            _ser.Encoding.X962, _ser.PublicFormat.UncompressedPoint
        )
        priv_body = b''.join(priv_pem.splitlines()[1:-1])
        priv_b64 = base64.urlsafe_b64encode(base64.b64decode(priv_body)).rstrip(b'=').decode('ascii')
        pub_b64 = base64.urlsafe_b64encode(raw_public).rstrip(b'=').decode('ascii')
        return {'publicKey': pub_b64, 'privateKey': priv_b64}
    except Exception:
        return {'publicKey': '', 'privateKey': ''}


def _load_or_create_vapid_keys():
    path = _vapid_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock_path = f'{path}.lock'
    try:
        import fcntl
    except ImportError:
        fcntl = None

    with _VAPID_FILE_LOCK:
        with open(lock_path, 'a+', encoding='utf-8') as lock_fh:
            if fcntl is not None:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            try:
                keys = _read_vapid_file()
                if keys:
                    return keys
                keys = _generate_vapid_keys()
                if _valid_vapid_keys(keys):
                    _write_vapid_file(keys)
                return keys
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def _vapid_keys():
    from api.models import _push_vapid_cache
    pub = (getattr(settings, 'PUSH_VAPID_PUBLIC_KEY', '') or '').strip()
    priv = (getattr(settings, 'PUSH_VAPID_PRIVATE_KEY', '') or '').strip()
    if pub and priv:
        return {'publicKey': pub, 'privateKey': priv}
    if _push_vapid_cache.get('keys'):
        return _push_vapid_cache['keys']
    keys = _load_or_create_vapid_keys()
    if _valid_vapid_keys(keys):
        _push_vapid_cache['keys'] = keys
    return keys or {'publicKey': '', 'privateKey': ''}


def vapid_public_key():
    return _vapid_keys().get('publicKey') or ''


def _send_one(reg, title, body, url, tag):
    try:
        from pywebpush import WebPushException, webpush
    except Exception:
        return
    try:
        webpush(
            subscription_info={
                'endpoint': reg.endpoint,
                'keys': {'p256dh': reg.p256dh, 'auth': reg.auth},
            },
            data=json.dumps({'title': title, 'body': body, 'url': url, 'tag': tag}),
            vapid_private_key=_vapid_keys().get('privateKey'),
            vapid_claims={'sub': getattr(settings, 'PUSH_VAPID_SUBJECT', 'mailto:admin@example.com')},
            timeout=10,
        )
        reg.last_used_at = timezone.now()
        reg.save(update_fields=['last_used_at', 'updated_at'])
    except WebPushException as exc:
        resp = getattr(exc, 'response', None)
        if resp is not None and getattr(resp, 'status_code', None) in (404, 410):
            try:
                reg.delete()
            except Exception:
                pass
    except Exception:
        pass


def _dispatch_push(regs, title, body, url, tag):
    for reg in regs:
        threading.Thread(target=_send_one, args=(reg, title, body, url, tag), daemon=True).start()


def notify_admins_new_pending(purchase):
    from api.models import WebPushSubscription
    regs = list(WebPushSubscription.objects.all())
    if not regs:
        return False

    name = (purchase.full_name or '').strip() or (
        purchase.user.username if purchase.user_id and purchase.user else ''
    )
    phone = (purchase.phone or '').strip()
    item_name = (getattr(purchase, 'lottery_item_name_snapshot', '') or '').strip()
    if not item_name and purchase.lottery_item_id and purchase.lottery_item:
        item_name = purchase.lottery_item.name or ''
    round_name = (getattr(purchase, 'lottery_round_snapshot', '') or '').strip()
    if not round_name and purchase.lottery_item_id and purchase.lottery_item:
        round_name = purchase.lottery_item.hero_title or purchase.lottery_item.name or ''
    amount = float(purchase.amount or 0)

    parts = ['New pending receipt']
    if name:
        parts.append(name)
    if phone:
        parts.append(phone)
    if item_name:
        parts.append(item_name)
    if round_name:
        parts.append(f'Round: {round_name}')
    if amount:
        parts.append(f'{amount:,.0f} Birr')
    body = ' · '.join(parts)

    for role, url in _ROLE_PANEL_URL.items():
        role_regs = [r for r in regs if r.role == role]
        if role_regs:
            _dispatch_push(role_regs, 'New pending receipt', body, url, 'new-pending-receipt')
    return True
