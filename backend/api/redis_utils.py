"""
Redis utility functions for Bingo game
Handles multiple winner support, card locking, and cleanup
"""
import redis
import os
from django.conf import settings


def get_redis_client():
    """Get Redis client instance"""
    try:
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_password = os.getenv('REDIS_PASSWORD', None)
        
        # Create Redis client
        if redis_password:
            r = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
        else:
            r = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
        
        # Test connection
        r.ping()
        return r
    except Exception as e:
        print(f"Redis connection error: {e}")
        return None


def get_bingo_window_key(game_id):
    """Get Redis key for bingo window lock"""
    return f"game:{game_id}:bingo_window"


def get_bingo_winners_key(game_id):
    """Get Redis key for bingo winners set"""
    return f"game:{game_id}:bingo_winners"


def get_card_lock_key(card_number):
    """Get Redis key for card lock"""
    return f"card:{card_number}:lock"


def try_acquire_bingo_window(game_id):
    """
    Try to acquire bingo window lock using SETNX
    Returns (success, is_first_winner)
    """
    r = get_redis_client()
    if not r:
        return (False, False)
    
    try:
        window_key = get_bingo_window_key(game_id)
        
        # Try to set the window lock (SETNX - only sets if not exists)
        is_first = r.setnx(window_key, "1")
        
        if is_first:
            # First winner - set 1 second expiry
            r.expire(window_key, 1)
            return (True, True)
        else:
            # Not first, but check if window is still valid (within 1 second)
            ttl = r.ttl(window_key)
            if ttl > 0:
                return (True, False)
            else:
                # Window expired, reject
                return (False, False)
    except Exception as e:
        print(f"Error acquiring bingo window: {e}")
        return (False, False)


def add_bingo_winner(game_id, card_id, user_id):
    """Add winner to Redis set"""
    r = get_redis_client()
    if not r:
        return False
    
    try:
        winners_key = get_bingo_winners_key(game_id)
        # Store as card_id:user_id for later retrieval
        r.sadd(winners_key, f"{card_id}:{user_id}")
        # Set expiry on the set (2 seconds to be safe)
        r.expire(winners_key, 2)
        return True
    except Exception as e:
        print(f"Error adding bingo winner: {e}")
        return False


def get_bingo_winners(game_id):
    """Get all winners from Redis set"""
    r = get_redis_client()
    if not r:
        return []
    
    try:
        winners_key = get_bingo_winners_key(game_id)
        winners = r.smembers(winners_key)
        result = []
        for winner_str in winners:
            parts = winner_str.split(':')
            if len(parts) == 2:
                result.append({
                    'card_id': int(parts[0]),
                    'user_id': int(parts[1])
                })
        return result
    except Exception as e:
        print(f"Error getting bingo winners: {e}")
        return []


def lock_card_selection(card_number, user_id, timeout=2):
    """
    Try to lock a card for selection using SETNX
    Returns (success, locked_by_user_id)
    """
    r = get_redis_client()
    if not r:
        # If Redis unavailable, allow (fallback to DB check)
        return (True, None)
    
    try:
        lock_key = get_card_lock_key(card_number)
        
        # Try to acquire lock
        acquired = r.setnx(lock_key, str(user_id))
        
        if acquired:
            # Lock acquired, set timeout
            r.expire(lock_key, timeout)
            return (True, None)
        else:
            # Lock exists, check who has it
            locked_by = r.get(lock_key)
            if locked_by and locked_by == str(user_id):
                # Same user already has lock (for reselection)
                return (True, None)
            else:
                # Locked by different user
                return (False, locked_by)
    except Exception as e:
        print(f"Error locking card: {e}")
        # On error, allow (fallback to DB check)
        return (True, None)


def release_card_lock(card_number):
    """Release card selection lock"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        lock_key = get_card_lock_key(card_number)
        r.delete(lock_key)
    except Exception as e:
        print(f"Error releasing card lock: {e}")


def cleanup_game_redis_keys(game_id):
    """Clean up all Redis keys for a game after it ends"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        keys_to_delete = [
            get_bingo_window_key(game_id),
            get_bingo_winners_key(game_id),
        ]
        
        # Also clean up any card locks that might still exist (optional, they expire anyway)
        # This is more aggressive cleanup
        
        for key in keys_to_delete:
            r.delete(key)
    except Exception as e:
        print(f"Error cleaning up Redis keys for game {game_id}: {e}")

