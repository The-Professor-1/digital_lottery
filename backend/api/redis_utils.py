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


def get_number_calling_lock_key(game_id):
    """Get Redis key for number calling lock"""
    return f"game:{game_id}:number_calling_lock"


def acquire_number_calling_lock(game_id, timeout=10):
    """
    Try to acquire lock for calling numbers in a game
    Returns True if lock acquired, False if already locked
    """
    r = get_redis_client()
    if not r:
        # If Redis unavailable, allow (fallback - should not happen in production)
        return True
    
    try:
        lock_key = get_number_calling_lock_key(game_id)
        
        # Try to acquire lock (SETNX - only sets if not exists)
        acquired = r.setnx(lock_key, "1")
        
        if acquired:
            # Lock acquired, set timeout (10 seconds should be enough for one number call)
            r.expire(lock_key, timeout)
            return True
        else:
            # Lock exists - another instance is already calling a number
            return False
    except Exception as e:
        print(f"Error acquiring number calling lock: {e}")
        # On error, allow (fallback - but log it)
        return True


def release_number_calling_lock(game_id):
    """Release number calling lock"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        lock_key = get_number_calling_lock_key(game_id)
        r.delete(lock_key)
    except Exception as e:
        print(f"Error releasing number calling lock: {e}")


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
            get_number_calling_lock_key(game_id),
            get_called_numbers_key(game_id),  # Also clean up called numbers cache
        ]
        
        # Also clean up any card locks that might still exist (optional, they expire anyway)
        # This is more aggressive cleanup
        
        for key in keys_to_delete:
            r.delete(key)
    except Exception as e:
        print(f"Error cleaning up Redis keys for game {game_id}: {e}")


# PHASE 2 OPTIMIZATION: Redis-based called numbers caching
def get_called_numbers_key(game_id):
    """Get Redis key for called numbers list"""
    return f"game:{game_id}:called_numbers"


def get_called_numbers_from_redis(game_id: int) -> set:
    """
    Get called numbers from Redis (faster than database query).
    Returns set of called numbers, or empty set if Redis unavailable.
    Falls back to database query if Redis fails.
    """
    r = get_redis_client()
    if not r:
        # Fallback to database
        from .models import CalledNumber
        return set(CalledNumber.objects.filter(game_id=game_id).values_list('number', flat=True))
    
    try:
        key = get_called_numbers_key(game_id)
        numbers = r.lrange(key, 0, -1)
        return {int(n) for n in numbers if n.isdigit()}
    except Exception as e:
        print(f"Error getting called numbers from Redis: {e}")
        # Fallback to database
        from .models import CalledNumber
        return set(CalledNumber.objects.filter(game_id=game_id).values_list('number', flat=True))


def add_called_number_to_redis(game_id: int, number: int):
    """
    Add called number to Redis list.
    This is much faster than querying the database.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        key = get_called_numbers_key(game_id)
        r.lpush(key, str(number))
        # Set expiry to 1 hour (game won't last that long, but safe cleanup)
        r.expire(key, 3600)
        return True
    except Exception as e:
        print(f"Error adding called number to Redis: {e}")
        return False


def get_called_numbers_list_from_redis(game_id: int) -> list:
    """
    Get called numbers as ordered list from Redis (for display purposes).
    Returns list of numbers in order called, or empty list if Redis unavailable.
    """
    r = get_redis_client()
    if not r:
        # Fallback to database
        from .models import CalledNumber
        return list(CalledNumber.objects.filter(game_id=game_id).order_by('called_at').values_list('number', flat=True))
    
    try:
        key = get_called_numbers_key(game_id)
        numbers = r.lrange(key, 0, -1)
        # Reverse to get chronological order (lpush adds to front, so reverse for oldest first)
        return [int(n) for n in reversed(numbers) if n.isdigit()]
    except Exception as e:
        print(f"Error getting called numbers list from Redis: {e}")
        # Fallback to database
        from .models import CalledNumber
        return list(CalledNumber.objects.filter(game_id=game_id).order_by('called_at').values_list('number', flat=True))


# PHASE 3 OPTIMIZATION: Redis-based card marked numbers tracking for faster bingo checking
def get_card_marked_numbers_key(card_id: int):
    """Get Redis key for card marked numbers set"""
    return f"card:{card_id}:marked_numbers"


def get_card_marked_count_key(card_id: int):
    """Get Redis key for card marked count (for early exit optimization)"""
    return f"card:{card_id}:marked_count"


def mark_number_on_card_redis(card_id: int, number: int):
    """
    Mark a number on a card in Redis (for faster bingo checking).
    This is called when a number is marked on a card.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        # Add number to marked numbers set
        marked_key = get_card_marked_numbers_key(card_id)
        r.sadd(marked_key, str(number))
        
        # Update marked count
        count_key = get_card_marked_count_key(card_id)
        count = r.incr(count_key)
        
        # Set expiry to 1 hour (game won't last that long, but safe cleanup)
        r.expire(marked_key, 3600)
        r.expire(count_key, 3600)
        
        return True
    except Exception as e:
        print(f"Error marking number on card in Redis: {e}")
        return False


def get_card_marked_count_redis(card_id: int) -> int:
    """
    Get the count of marked numbers on a card from Redis.
    Returns 0 if Redis unavailable or card not found.
    Used for early exit optimization (skip cards with < 5 marked numbers).
    """
    r = get_redis_client()
    if not r:
        return 0
    
    try:
        count_key = get_card_marked_count_key(card_id)
        count = r.get(count_key)
        return int(count) if count else 0
    except Exception as e:
        print(f"Error getting card marked count from Redis: {e}")
        return 0


def get_card_marked_numbers_redis(card_id: int) -> set:
    """
    Get all marked numbers for a card from Redis.
    Returns empty set if Redis unavailable or card not found.
    """
    r = get_redis_client()
    if not r:
        return set()
    
    try:
        marked_key = get_card_marked_numbers_key(card_id)
        numbers = r.smembers(marked_key)
        return {int(n) for n in numbers if n.isdigit()}
    except Exception as e:
        print(f"Error getting card marked numbers from Redis: {e}")
        return set()


def initialize_card_redis(card_id: int, selected_numbers: list = None):
    """
    Initialize Redis tracking for a card.
    Call this when a card is created or when loading card data.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        marked_key = get_card_marked_numbers_key(card_id)
        count_key = get_card_marked_count_key(card_id)
        
        if selected_numbers:
            # Initialize with existing marked numbers
            if selected_numbers:
                r.sadd(marked_key, *[str(n) for n in selected_numbers])
                r.set(count_key, len(selected_numbers))
        else:
            # Initialize empty
            r.set(count_key, 0)
        
        # Set expiry to 1 hour
        r.expire(marked_key, 3600)
        r.expire(count_key, 3600)
        
        return True
    except Exception as e:
        print(f"Error initializing card in Redis: {e}")
        return False


def cleanup_card_redis(card_id: int):
    """Clean up Redis keys for a card (called when card is deleted or game ends)"""
    r = get_redis_client()
    if not r:
        return False
    
    try:
        marked_key = get_card_marked_numbers_key(card_id)
        count_key = get_card_marked_count_key(card_id)
        r.delete(marked_key, count_key)
        return True
    except Exception as e:
        print(f"Error cleaning up card Redis keys: {e}")
        return False

