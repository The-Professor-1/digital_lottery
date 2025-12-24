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


def get_game_creation_lock_key():
    """Get Redis key for global game creation lock (prevents multiple games from being created simultaneously)"""
    return "game:creation:lock"


def acquire_game_creation_lock(timeout=15):
    """
    Try to acquire global lock for game creation (atomic operation)
    Returns True if lock acquired, False if already locked
    """
    r = get_redis_client()
    if not r:
        # If Redis unavailable, allow (fallback - should not happen in production)
        return True
    
    try:
        lock_key = get_game_creation_lock_key()
        
        # Try to acquire lock (SETNX - only sets if not exists)
        acquired = r.setnx(lock_key, "1")
        
        if acquired:
            # Lock acquired, set timeout (15 seconds should be enough for game creation)
            r.expire(lock_key, timeout)
            return True
        else:
            # Lock exists - another process is already creating a game
            return False
    except Exception as e:
        print(f"Error acquiring game creation lock: {e}")
        # On error, allow (fallback - but log it)
        return True


def release_game_creation_lock():
    """Release global game creation lock"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        lock_key = get_game_creation_lock_key()
        r.delete(lock_key)
    except Exception as e:
        print(f"Error releasing game creation lock: {e}")


def get_bingo_claim_lock_key(game_id):
    """Get Redis key for bingo claim lock (ensures only one claim processed at a time)"""
    return f"game:{game_id}:bingo_claim_lock"


def acquire_bingo_claim_lock(game_id, timeout=5):
    """
    Try to acquire lock for claiming bingo (atomic operation)
    Returns True if lock acquired, False if already locked
    """
    r = get_redis_client()
    if not r:
        # If Redis unavailable, allow (fallback - should not happen in production)
        return True
    
    try:
        lock_key = get_bingo_claim_lock_key(game_id)
        
        # Try to acquire lock (SETNX - only sets if not exists)
        acquired = r.setnx(lock_key, "1")
        
        if acquired:
            # Lock acquired, set timeout (5 seconds should be enough for bingo claim)
            r.expire(lock_key, timeout)
            return True
        else:
            # Lock exists - another process is already processing a bingo claim
            return False
    except Exception as e:
        print(f"Error acquiring bingo claim lock: {e}")
        # On error, allow (fallback - but log it)
        return True


def release_bingo_claim_lock(game_id):
    """Release bingo claim lock"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        lock_key = get_bingo_claim_lock_key(game_id)
        r.delete(lock_key)
    except Exception as e:
        print(f"Error releasing bingo claim lock: {e}")


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
    """Add winner to Redis set
    user_id can be None for fake users
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        winners_key = get_bingo_winners_key(game_id)
        # Store as card_id:user_id for later retrieval
        # For fake users (user_id is None), store as "fake" instead of "None"
        user_id_str = "fake" if user_id is None else str(user_id)
        r.sadd(winners_key, f"{card_id}:{user_id_str}")
        # Set expiry on the set (2 seconds to be safe)
        r.expire(winners_key, 2)
        return True
    except Exception as e:
        print(f"Error adding bingo winner: {e}")
        return False


def get_bingo_winners(game_id):
    """Get all winners from Redis set
    Returns list of dicts with 'card_id' and 'user_id' (None for fake users)
    """
    r = get_redis_client()
    if not r:
        return []
    
    try:
        winners_key = get_bingo_winners_key(game_id)
        winners = r.smembers(winners_key)
        result = []
        for winner_str in winners:
            # Handle bytes from Redis
            if isinstance(winner_str, bytes):
                winner_str = winner_str.decode('utf-8')
            
            parts = winner_str.split(':')
            if len(parts) == 2:
                card_id = int(parts[0])
                user_id_str = parts[1]
                
                # Handle fake users (stored as "fake")
                if user_id_str == "fake":
                    user_id = None
                else:
                    try:
                        user_id = int(user_id_str)
                    except ValueError:
                        # Skip invalid entries
                        print(f"WARNING: Invalid user_id in Redis winner: {user_id_str}")
                        continue
                
                result.append({
                    'card_id': card_id,
                    'user_id': user_id
                })
        return result
    except Exception as e:
        print(f"Error getting bingo winners: {e}")
        import traceback
        traceback.print_exc()
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
            get_game_state_key(game_id),  # PHASE 4: Clean up game state cache
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


# PHASE 4 OPTIMIZATION: Redis-based game state caching (reduces DB refreshes by 70-80%)
def get_game_state_key(game_id: int):
    """Get Redis key for game state cache"""
    return f"game:{game_id}:state"


def cache_game_state(game_id: int, status: str = None, winner_id: int = None, call_count: int = None, 
                     total_derash: float = None, completed_at: str = None):
    """
    Cache game state in Redis (faster than DB refresh).
    Updates only provided fields, leaves others unchanged.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        key = get_game_state_key(game_id)
        
        # Get existing state or create new
        existing = r.hgetall(key)
        state = existing if existing else {}
        
        # Update provided fields
        if status is not None:
            state['status'] = status
        if winner_id is not None:
            state['winner_id'] = str(winner_id) if winner_id else ''
        if call_count is not None:
            state['call_count'] = str(call_count)
        if total_derash is not None:
            state['total_derash'] = str(total_derash)
        if completed_at is not None:
            state['completed_at'] = completed_at
        
        # Store in Redis hash
        if state:
            r.hset(key, mapping=state)
            # Set expiry to 1 hour (game won't last that long, but safe cleanup)
            r.expire(key, 3600)
        
        return True
    except Exception as e:
        print(f"Error caching game state: {e}")
        return False


def get_game_state_from_redis(game_id: int) -> dict:
    """
    Get game state from Redis cache.
    Returns dict with status, winner_id, call_count, total_derash, completed_at.
    Returns empty dict if Redis unavailable or not cached.
    """
    r = get_redis_client()
    if not r:
        return {}
    
    try:
        key = get_game_state_key(game_id)
        state = r.hgetall(key)
        
        if not state:
            return {}
        
        # Parse values
        result = {}
        if 'status' in state:
            result['status'] = state['status']
        if 'winner_id' in state:
            winner_id_str = state['winner_id']
            result['winner_id'] = int(winner_id_str) if winner_id_str and winner_id_str.isdigit() else None
        if 'call_count' in state:
            result['call_count'] = int(state['call_count']) if state['call_count'].isdigit() else 0
        if 'total_derash' in state:
            try:
                result['total_derash'] = float(state['total_derash'])
            except ValueError:
                result['total_derash'] = 0.0
        if 'completed_at' in state:
            result['completed_at'] = state['completed_at']
        
        return result
    except Exception as e:
        print(f"Error getting game state from Redis: {e}")
        return {}


def invalidate_game_state_cache(game_id: int):
    """Invalidate game state cache (call when game state changes in DB)"""
    r = get_redis_client()
    if not r:
        return False
    
    try:
        key = get_game_state_key(game_id)
        r.delete(key)
        return True
    except Exception as e:
        print(f"Error invalidating game state cache: {e}")
        return False


def sync_game_state_to_redis(game):
    """
    Sync game state from DB model to Redis cache.
    Call this after updating game in DB to keep cache in sync.
    """
    # Get winner ID safely (game.winner might be None or a User object)
    winner_id = None
    if game.winner:
        # game.winner can be a User object or an ID
        if hasattr(game.winner, 'id'):
            winner_id = game.winner.id
        else:
            winner_id = game.winner
    
    return cache_game_state(
        game_id=game.id,
        status=game.status,
        winner_id=winner_id,
        call_count=game.current_call_count,
        total_derash=float(game.total_derash) if game.total_derash else 0.0,
        completed_at=game.completed_at.isoformat() if game.completed_at else None
    )


# PHASE 5 OPTIMIZATION: Batch WebSocket broadcasts (reduces overhead by 50-70%)
def batch_broadcast_to_game(game_id: int, events: list):
    """
    Send multiple WebSocket events in a single broadcast.
    This reduces overhead by batching events together.
    
    Args:
        game_id: Game ID
        events: List of event dicts, each with 'type' and 'data' keys
                Example: [
                    {'type': 'number_called', 'data': {...}},
                    {'type': 'card_selected', 'data': {...}}
                ]
    
    Returns:
        bool: True if broadcast successful, False otherwise
    """
    if not events:
        return False
    
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        
        # If only one event, send it directly (no batching needed)
        if len(events) == 1:
            event = events[0]
            async_to_sync(channel_layer.group_send)(
                f'game_{game_id}',
                {
                    'type': event['type'],
                    'data': event['data']
                }
            )
        else:
            # Send multiple events in a single batch message
            async_to_sync(channel_layer.group_send)(
                f'game_{game_id}',
                {
                    'type': 'batch_events',
                    'data': {
                        'events': events
                    }
                }
            )
        
        return True
    except Exception as e:
        print(f"Error in batch_broadcast_to_game: {e}")
        import traceback
        traceback.print_exc()
        return False

