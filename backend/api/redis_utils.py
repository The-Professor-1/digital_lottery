"""Rate-limit helpers backed by Django's file cache (no Redis server)."""
from django.core.cache import cache


def get_rate_limit_key(action: str, identifier: str):
    return f'ratelimit:{action}:{identifier}'


def check_rate_limit(action: str, identifier: str, limit: int, window_seconds: int) -> tuple:
    """Return (allowed, remaining_attempts) using the configured Django cache."""
    try:
        key = get_rate_limit_key(action, identifier)
        current = int(cache.get(key, 0) or 0)
        if current >= limit:
            return False, 0
        cache.set(key, current + 1, timeout=window_seconds)
        return True, max(0, limit - (current + 1))
    except Exception:
        # Never block registration because the cache backend is unavailable.
        return True, limit
