"""Redis helpers used by the lottery app (rate limiting). Bingo game Redis helpers removed."""
import os

import redis


def get_redis_client():
    """Get Redis client instance, or None if unavailable."""
    try:
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD', None)

        kwargs = {
            'host': redis_host,
            'port': redis_port,
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
        }
        if redis_password:
            kwargs['password'] = redis_password
        r = redis.Redis(**kwargs)
        r.ping()
        return r
    except Exception as e:
        print(f'Redis connection error: {e}')
        return None


def get_rate_limit_key(action: str, identifier: str):
    return f'ratelimit:{action}:{identifier}'


def check_rate_limit(action: str, identifier: str, limit: int, window_seconds: int) -> tuple:
    """
    Check if action is within rate limit.
    Returns (is_allowed, remaining_attempts).
    """
    r = get_redis_client()
    if not r:
        return True, limit

    try:
        key = get_rate_limit_key(action, identifier)
        current = r.get(key)

        if current is None:
            r.setex(key, window_seconds, 1)
            return True, limit - 1

        current_count = int(current)
        if current_count >= limit:
            return False, 0

        new_count = r.incr(key)
        if new_count == 1:
            r.expire(key, window_seconds)
        remaining = max(0, limit - new_count)
        return True, remaining
    except Exception as e:
        print(f'Error checking rate limit: {e}')
        return True, limit
