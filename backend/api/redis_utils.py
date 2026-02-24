"""
Redis utility functions for Bingo game
Handles multiple winner support, card locking, and cleanup
"""
import redis
import os
from django.conf import settings
from django.utils import timezone


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


def acquire_number_calling_lock(game_id, timeout=30):
    """
    Try to acquire lock for calling numbers in a game
    Returns True if lock acquired, False if already locked
    CRITICAL FIX: Increased timeout from 10s to 30s to prevent lock expiration during task execution
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
            # Lock acquired, set timeout (30 seconds should be enough for one number call + safety margin)
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


def try_acquire_bingo_window(game_id, first_claim_is_fake=False):
    """
    Try to acquire bingo window for multiple-winner tie.
    - First winner (real): 1 second window for co-winners.
    - First winner (fake): 3 second window so real players can claim and share.
    Returns (success, is_first_winner).
    """
    r = get_redis_client()
    if not r:
        return (False, False)
    
    try:
        window_key = get_bingo_window_key(game_id)
        is_first = r.setnx(window_key, "1")
        if is_first:
            window_seconds = 3 if first_claim_is_fake else 1
            r.expire(window_key, window_seconds)
            return (True, True)
        # Co-winner: allow while window key exists and TTL >= 0.
        # Redis TTL returns integer seconds; in the last fraction of a second it returns 0.
        # Rejecting only ttl > 0 was causing the second claim to fail when it ran in that boundary.
        ttl = r.ttl(window_key)
        if ttl >= 0:
            return (True, False)
        # Key expired or missing (-2)
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
        # Expiry must cover window (1 or 3 sec) + task delay; use 10s so task always sees all winners
        r.expire(winners_key, 10)
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
    """Clean up all Redis keys for a game after it ends (see docs/REDIS_KEYS.md)."""
    r = get_redis_client()
    if not r:
        return
    
    try:
        keys_to_delete = [
            get_bingo_window_key(game_id),
            get_bingo_winners_key(game_id),
            get_bingo_claim_lock_key(game_id),
            get_number_calling_lock_key(game_id),
            get_called_numbers_key(game_id),
            get_game_state_key(game_id),
        ]
        for key in keys_to_delete:
            r.delete(key)
    except Exception as e:
        print(f"Error cleaning up Redis keys for game {game_id}: {e}")


# --- Bot new registration limit (24h rolling window) ---
# Counter increments when a new user completes registration (contact). When count >= limit,
# /start and /register do not respond at all (no server load). Window resets 24h after it started.
BOT_NEW_STARTS_WINDOW_END_KEY = "bot:new_starts:window_end"  # Unix timestamp when current window ends
BOT_NEW_STARTS_COUNT_KEY = "bot:new_starts:count"
WINDOW_SECONDS = 24 * 3600  # 24h rolling window
DEFAULT_DAILY_NEW_START_LIMIT = 100

# Lua: check if new starts are blocked (count >= limit in current window). Returns 1=blocked, 0=allow.
# KEYS: none. ARGV[1]=limit, ARGV[2]=now (Unix)
LUA_IS_NEW_START_BLOCKED = """
local limit = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
if limit == nil or limit <= 0 then return 0 end
local we = redis.call("GET", "bot:new_starts:window_end")
local count = tonumber(redis.call("GET", "bot:new_starts:count") or "0")
if we == nil or now > tonumber(we) then return 0 end
if count >= limit then return 1 end
return 0
"""

# Lua: acquire a slot (increment count). Reset window if expired. Returns 1=acquired, 0=over limit.
# KEYS: none. ARGV[1]=limit, ARGV[2]=now (Unix), ARGV[3]=window_sec
LUA_ACQUIRE_NEW_START_SLOT = """
local limit = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local window_sec = tonumber(ARGV[3])
if limit == nil or limit <= 0 then return 1 end
local we = redis.call("GET", "bot:new_starts:window_end")
local count = tonumber(redis.call("GET", "bot:new_starts:count") or "0")
if we == nil or now > tonumber(we) then
  redis.call("SET", "bot:new_starts:window_end", now + window_sec)
  redis.call("SET", "bot:new_starts:count", "0")
  count = 0
end
if count >= limit then return 0 end
redis.call("INCR", "bot:new_starts:count")
return 1
"""


def _get_daily_new_start_limit():
    """Read limit from GameSettings; 0 or None means no limit (allow all)."""
    try:
        from .models import GameSettings
        settings = GameSettings.get_settings()
        limit = getattr(settings, 'daily_new_start_limit', None)
        if limit is None:
            return DEFAULT_DAILY_NEW_START_LIMIT
        limit = int(limit)
        return limit if limit > 0 else None  # 0 = no limit
    except Exception:
        return DEFAULT_DAILY_NEW_START_LIMIT


def is_new_start_blocked():
    """
    Returns True if new /start and new registration should be disabled (no response at all).
    Uses 24h rolling window; when count >= limit in current window, returns True.
    Call at the very start of /start (new user) and handle_contact to avoid any server load when over limit.
    """
    limit = _get_daily_new_start_limit()
    if limit is None:
        return False  # 0 = no limit
    r = get_redis_client()
    if not r:
        return False  # No Redis: allow (fail open)
    try:
        import time
        now = int(time.time())
        result = r.eval(LUA_IS_NEW_START_BLOCKED, 0, limit, now)
        return result == 1
    except Exception as e:
        print(f"Error in is_new_start_blocked: {e}")
        return False  # Fail open


def try_acquire_daily_start_slot():
    """
    Call only when a new user completes registration (sends contact for the first time).
    Atomically: if window expired, reset window and count; if count >= limit return False;
    else increment count and return True. Uses 24h rolling window so increasing the limit
    in admin takes effect immediately for the current window.
    """
    limit = _get_daily_new_start_limit()
    if limit is None:
        return True  # 0 = no limit
    r = get_redis_client()
    if not r:
        return True  # No Redis: allow (fail open)
    try:
        import time
        now = int(time.time())
        result = r.eval(LUA_ACQUIRE_NEW_START_SLOT, 0, limit, now, WINDOW_SECONDS)
        return result == 1
    except Exception as e:
        print(f"Error in try_acquire_daily_start_slot: {e}")
        return True  # Fail open


def get_new_starts_window_count():
    """
    Return current registration count in the 24h window (for admin display).
    Returns dict: { 'count': int, 'window_end_ts': int or None }.
    Returns the stored Redis count even when the window has expired, so the dashboard
    shows the last known value (bot increments on first-time contact share).
    """
    r = get_redis_client()
    if not r:
        return {'count': 0, 'window_end_ts': None}
    try:
        import time
        now = int(time.time())
        we = r.get(BOT_NEW_STARTS_WINDOW_END_KEY)
        count = int(r.get(BOT_NEW_STARTS_COUNT_KEY) or 0)
        window_end_ts = int(we) if we else None
        # When window expired or never set, still return stored count so admin sees last value
        if window_end_ts is not None and now <= window_end_ts:
            return {'count': count, 'window_end_ts': window_end_ts}
        return {'count': count, 'window_end_ts': None}
    except Exception as e:
        print(f"Error in get_new_starts_window_count: {e}")
        return {'count': 0, 'window_end_ts': None}


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
# Uses room separation: game_{id}_players + game_{id}_watchers + legacy game_{id}
def batch_broadcast_to_game(game_id: int, events: list, rooms: str = "both"):
    """
    Send multiple WebSocket events to game rooms (players + watchers).
    See docs/ARCHITECTURE.md and api/channels.py.

    Args:
        game_id: Game ID
        events: List of event dicts, each with 'type' and 'data' keys
        rooms: 'both' | 'players' | 'watchers'

    Returns:
        bool: True if broadcast successful, False otherwise
    """
    from api.channels import batch_broadcast_to_game_rooms
    return batch_broadcast_to_game_rooms(game_id, events, rooms=rooms, use_legacy=True)


# ============================================================================
# REGISTRATION LOCKS & RATE LIMITING (PROMO-SAFE)
# ============================================================================

def get_registration_lock_key(telegram_id: int):
    """Get Redis key for registration lock"""
    return f"register:lock:{telegram_id}"


def acquire_registration_lock(telegram_id: int, timeout: int = 60) -> bool:
    """
    Acquire lock for registration to prevent concurrent registrations
    Returns True if lock acquired, False if already locked
    """
    r = get_redis_client()
    if not r:
        # If Redis unavailable, allow (fallback - should not happen in production)
        return True
    
    try:
        lock_key = get_registration_lock_key(telegram_id)
        # Try to acquire lock (SETNX - only sets if not exists)
        acquired = r.setnx(lock_key, "1")
        
        if acquired:
            # Lock acquired, set timeout
            r.expire(lock_key, timeout)
            return True
        else:
            # Lock exists - another process is already processing registration
            return False
    except Exception as e:
        print(f"Error acquiring registration lock: {e}")
        # On error, allow (fallback - but log it)
        return True


def release_registration_lock(telegram_id: int):
    """Release registration lock"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        lock_key = get_registration_lock_key(telegram_id)
        r.delete(lock_key)
    except Exception as e:
        print(f"Error releasing registration lock: {e}")


def get_reward_lock_key(user_id: int):
    """Get Redis key for reward lock (prevents duplicate rewards)"""
    return f"reward:lock:{user_id}"


def acquire_reward_lock(user_id: int, timeout: int = 30) -> bool:
    """
    Acquire lock for reward processing to prevent duplicate rewards
    Returns True if lock acquired, False if already locked
    """
    r = get_redis_client()
    if not r:
        return True
    
    try:
        lock_key = get_reward_lock_key(user_id)
        acquired = r.setnx(lock_key, "1")
        
        if acquired:
            r.expire(lock_key, timeout)
            return True
        return False
    except Exception as e:
        print(f"Error acquiring reward lock: {e}")
        return True


def release_reward_lock(user_id: int):
    """Release reward lock"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        lock_key = get_reward_lock_key(user_id)
        r.delete(lock_key)
    except Exception as e:
        print(f"Error releasing reward lock: {e}")


def get_referral_lock_key(referrer_id: int):
    """Get Redis key for referral reward lock (prevents spam payouts)"""
    return f"referral:lock:{referrer_id}"


def acquire_referral_lock(referrer_id: int, timeout: int = 60) -> bool:
    """
    Acquire lock for referral reward processing
    Returns True if lock acquired, False if already locked
    """
    r = get_redis_client()
    if not r:
        return True
    
    try:
        lock_key = get_referral_lock_key(referrer_id)
        acquired = r.setnx(lock_key, "1")
        
        if acquired:
            r.expire(lock_key, timeout)
            return True
        return False
    except Exception as e:
        print(f"Error acquiring referral lock: {e}")
        return True


def release_referral_lock(referrer_id: int):
    """Release referral lock"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        lock_key = get_referral_lock_key(referrer_id)
        r.delete(lock_key)
    except Exception as e:
        print(f"Error releasing referral lock: {e}")


# ============================================================================
# RATE LIMITING (REDIS-BASED)
# ============================================================================

def get_rate_limit_key(action: str, identifier: str):
    """Get Redis key for rate limiting"""
    return f"ratelimit:{action}:{identifier}"


def check_rate_limit(action: str, identifier: str, limit: int, window_seconds: int) -> tuple:
    """
    Check if action is within rate limit
    Returns (is_allowed, remaining_attempts)
    
    Args:
        action: Action name (e.g., 'register', 'reward')
        identifier: Unique identifier (IP, telegram_id, etc.)
        limit: Maximum number of attempts
        window_seconds: Time window in seconds
    """
    r = get_redis_client()
    if not r:
        # If Redis unavailable, allow (fallback - should not happen in production)
        return True, limit
    
    try:
        key = get_rate_limit_key(action, identifier)
        current = r.get(key)
        
        if current is None:
            # First attempt - set counter with expiration
            r.setex(key, window_seconds, 1)
            return True, limit - 1
        else:
            current_count = int(current)
            if current_count >= limit:
                # Rate limit exceeded
                ttl = r.ttl(key)
                return False, 0
            else:
                # Increment counter
                new_count = r.incr(key)
                if new_count == 1:
                    # Set expiration on first increment
                    r.expire(key, window_seconds)
                remaining = max(0, limit - new_count)
                return True, remaining
    except Exception as e:
        print(f"Error checking rate limit: {e}")
        # On error, allow (fallback - but log it)
        return True, limit


def reset_rate_limit(action: str, identifier: str):
    """Reset rate limit for an identifier"""
    r = get_redis_client()
    if not r:
        return
    
    try:
        key = get_rate_limit_key(action, identifier)
        r.delete(key)
    except Exception as e:
        print(f"Error resetting rate limit: {e}")


# ============================================================================
# EVENT-DRIVEN GAME STATE (REDIS-FIRST ARCHITECTURE)
# ============================================================================
# These functions treat Redis as the source of truth during gameplay.
# Database is only written at game end (finalize_game task).

def get_game_live_state_key(game_id: int):
    """Get Redis key for live game state (source of truth during gameplay)"""
    return f"game:{game_id}:live"


def initialize_game_live_state(game_id: int, status: str = "active", call_interval: int = 3):
    """
    Initialize live game state in Redis.
    This is called when game starts - Redis becomes source of truth.
    CRITICAL: Cleans up any existing state first to ensure fresh start.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        # CRITICAL: Clean up any existing state first
        # This ensures we start fresh even if previous game didn't clean up
        cleanup_game_live_state(game_id)
        
        key = get_game_live_state_key(game_id)
        
        # CRITICAL FIX: Use hset instead of deprecated hmset (Redis 4.0+)
        # hmset is deprecated and may fail silently
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Use hset with mapping (Redis 4.0+ compatible)
            # Fallback to individual hset calls if mapping not supported
            try:
                r.hset(key, mapping={
                    "status": status,
                    "current_index": "0",  # Index in called_numbers list
                    "winner_card_id": "",  # Empty = no winner yet
                    "winner_user_id": "",  # Empty = no winner yet
                    "call_interval": str(call_interval),
                    "started_at": str(timezone.now().isoformat())
                })
            except TypeError:
                # Fallback for older Redis versions that don't support mapping parameter
                r.hset(key, "status", status)
                r.hset(key, "current_index", "0")
                r.hset(key, "winner_card_id", "")
                r.hset(key, "winner_user_id", "")
                r.hset(key, "call_interval", str(call_interval))
                r.hset(key, "started_at", str(timezone.now().isoformat()))
            
            r.expire(key, 3600)  # 1 hour expiry
            
            # Verify state was set correctly
            verify_state = r.hgetall(key)
            logger.info(f"✅ [INIT] Game {game_id}: Redis state initialized: {verify_state}")
            print(f"✅ [INIT] Game {game_id}: Redis state initialized: {verify_state}")
            
            if not verify_state or len(verify_state) == 0:
                logger.error(f"❌ [INIT] Game {game_id}: Redis state initialization failed - state is empty!")
                print(f"❌ [INIT] Game {game_id}: Redis state initialization failed!")
                return False
        except Exception as e:
            logger.error(f"❌ [INIT] Game {game_id}: Error initializing Redis state: {e}")
            print(f"❌ [INIT] Game {game_id}: Error initializing Redis state: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Initialize called numbers list (ensure it's empty)
        called_numbers_key = get_called_numbers_key(game_id)
        r.delete(called_numbers_key)  # Clear any old data
        
        print(f"✅ Initialized fresh Redis live state for game {game_id}")
        return True
    except Exception as e:
        print(f"Error initializing game live state: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_game_live_state(game_id: int) -> dict:
    """
    Get live game state from Redis (source of truth during gameplay).
    Returns empty dict if game not found or Redis unavailable.
    """
    r = get_redis_client()
    if not r:
        return {}
    
    try:
        key = get_game_live_state_key(game_id)
        state = r.hgetall(key)
        
        if not state:
            return {}
        
        # Parse values safely
        result = {
            "status": state.get("status", "unknown"),
            "current_index": 0,
            "winner_card_id": None,
            "winner_user_id": None,
            "call_interval": 3,
            "started_at": state.get("started_at", "")
        }
        
        # Parse current_index
        try:
            result["current_index"] = int(state.get("current_index", 0))
        except (ValueError, TypeError):
            result["current_index"] = 0
        
        # Parse winner_card_id (allow negative sentinel e.g. -1 for system winner)
        winner_card_id_str = state.get("winner_card_id", "")
        if winner_card_id_str:
            try:
                result["winner_card_id"] = int(winner_card_id_str)
            except ValueError:
                pass
        # Parse winner_user_id
        winner_user_id_str = state.get("winner_user_id", "")
        if winner_user_id_str:
            try:
                result["winner_user_id"] = int(winner_user_id_str)
            except ValueError:
                pass
        
        # Parse call_interval
        try:
            result["call_interval"] = int(state.get("call_interval", 3))
        except (ValueError, TypeError):
            result["call_interval"] = 3
        
        return result
    except Exception as e:
        print(f"Error getting game live state: {e}")
        return {}


def set_game_winner(game_id: int, card_id: int, user_id: int = None) -> bool:
    """
    Set game winner atomically using Redis Lua script.
    Returns True if winner was set (first to claim), False if already has winner.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🏆 [SET WINNER] Game {game_id}: Attempting to set winner - card_id={card_id}, user_id={user_id}")
    print(f"🏆 [SET WINNER] Game {game_id}: Attempting to set winner - card_id={card_id}, user_id={user_id}")
    
    r = get_redis_client()
    if not r:
        logger.error(f"❌ [SET WINNER] Game {game_id}: Redis client not available")
        print(f"❌ [SET WINNER] Game {game_id}: Redis client not available")
        return False
    
    try:
        key = get_game_live_state_key(game_id)
        logger.info(f"🏆 [SET WINNER] Game {game_id}: Using Redis key: {key}")
        
        # Check current state before setting
        current_state = r.hgetall(key)
        logger.info(f"🏆 [SET WINNER] Game {game_id}: Current Redis state: {current_state}")
        print(f"🏆 [SET WINNER] Game {game_id}: Current Redis state: {current_state}")
        
        # Lua script for atomic winner setting
        lua_script = """
        local key = KEYS[1]
        local card_id = ARGV[1]
        local user_id = ARGV[2]
        
        -- Check if winner already exists
        local winner = redis.call('HGET', key, 'winner_card_id')
        if winner and winner ~= '' then
            return 0  -- Already has winner
        end
        
        -- Set winner atomically
        redis.call('HSET', key, 'winner_card_id', card_id)
        if user_id and user_id ~= '' then
            redis.call('HSET', key, 'winner_user_id', user_id)
        end
        redis.call('HSET', key, 'status', 'completed')
        
        return 1  -- Winner set successfully
        """
        
        result = r.eval(lua_script, 1, key, str(card_id), str(user_id) if user_id else "")
        success = bool(result)
        
        if success:
            logger.info(f"✅ [SET WINNER] Game {game_id}: Winner set successfully! card_id={card_id}, user_id={user_id}")
            print(f"✅ [SET WINNER] Game {game_id}: Winner set successfully! card_id={card_id}, user_id={user_id}")
            
            # Verify the state was set correctly
            final_state = r.hgetall(key)
            logger.info(f"✅ [SET WINNER] Game {game_id}: Final Redis state after setting winner: {final_state}")
            print(f"✅ [SET WINNER] Game {game_id}: Final Redis state: {final_state}")
        else:
            logger.warning(f"⚠️ [SET WINNER] Game {game_id}: Winner already exists or failed to set")
            print(f"⚠️ [SET WINNER] Game {game_id}: Winner already exists or failed to set")
        
        return success
    except Exception as e:
        logger.error(f"❌ [SET WINNER] Game {game_id}: Error setting winner: {e}")
        print(f"❌ [SET WINNER] Game {game_id}: Error setting winner: {e}")
        import traceback
        traceback.print_exc()
        return False


# Sentinel card_id for "Redis-only system player won" (stops number calling, no DB card)
SYSTEM_WINNER_CARD_ID = -1


def set_game_winner_system_sentinel(game_id: int) -> bool:
    """
    Set game winner to "system" sentinel so number calling stops.
    Use when a Redis-only system player wins (no DB card, no payout).
    """
    return set_game_winner(game_id, SYSTEM_WINNER_CARD_ID, None)


def add_called_number_live(game_id: int, number: int) -> int:
    """
    Add called number to Redis list and return new call count.
    Returns the new count (index + 1).
    """
    r = get_redis_client()
    if not r:
        return 0
    
    try:
        # Add to called numbers list
        called_numbers_key = get_called_numbers_key(game_id)
        r.lpush(called_numbers_key, str(number))
        r.expire(called_numbers_key, 3600)
        
        # Update current_index in live state
        state_key = get_game_live_state_key(game_id)
        new_index = r.hincrby(state_key, "current_index", 1)
        
        return new_index
    except Exception as e:
        print(f"Error adding called number: {e}")
        return 0


def get_card_marked_numbers_key_live(game_id: int, card_id: int):
    """Get Redis key for card marked numbers (live gameplay)"""
    return f"game:{game_id}:card:{card_id}:marked"


def mark_number_on_card_live(game_id: int, card_id: int, number: int) -> bool:
    """
    Mark number on card in Redis (for live gameplay).
    Returns True if number was added (new), False if already marked.
    """
    r = get_redis_client()
    if not r:
        return False
    
    try:
        key = get_card_marked_numbers_key_live(game_id, card_id)
        added = r.sadd(key, str(number))
        r.expire(key, 3600)
        return bool(added)  # True if number was new, False if already in set
    except Exception as e:
        print(f"Error marking number on card: {e}")
        return False


def get_card_marked_numbers_live(game_id: int, card_id: int) -> set:
    """Get marked numbers for a card from Redis (live gameplay)"""
    r = get_redis_client()
    if not r:
        return set()
    
    try:
        key = get_card_marked_numbers_key_live(game_id, card_id)
        numbers = r.smembers(key)
        return {int(n) for n in numbers if n.isdigit()}
    except Exception as e:
        print(f"Error getting card marked numbers: {e}")
        return set()


# =============================================================================
# SYSTEM PLAYERS (Redis-only, no DB – see docs/ARCHITECTURE.md)
# =============================================================================

def get_system_players_key(game_id: int):
    """Redis key for system players in this game. Hash: card_number -> JSON {name, card_number, card_layout}."""
    return f"game:{game_id}:system_players"


def get_system_card_marked_key(game_id: int, card_number: int):
    """Redis key for marked numbers on a system player's card."""
    return f"game:{game_id}:system_card:{card_number}:marked"


def system_player_add(game_id: int, card_number: int, name: str, card_layout: list) -> bool:
    """
    Add a system player to the game (Redis only, no DB).
    card_layout: list of rows, each row list of cells {number, letter, ...}.
    """
    import json
    r = get_redis_client()
    if not r:
        return False
    try:
        key = get_system_players_key(game_id)
        payload = {"name": name, "card_number": card_number, "card_layout": card_layout}
        r.hset(key, str(card_number), json.dumps(payload))
        r.expire(key, 3600)
        marked_key = get_system_card_marked_key(game_id, card_number)
        r.delete(marked_key)  # start empty
        r.expire(marked_key, 3600)
        return True
    except Exception as e:
        print(f"Error adding system player: {e}")
        return False


def system_player_get(game_id: int, card_number: int) -> dict:
    """Get one system player by card_number. Returns {} if not found."""
    import json
    r = get_redis_client()
    if not r:
        return {}
    try:
        key = get_system_players_key(game_id)
        raw = r.hget(key, str(card_number))
        if not raw:
            return {}
        return json.loads(raw)
    except Exception as e:
        print(f"Error getting system player: {e}")
        return {}


def system_player_get_all(game_id: int) -> list:
    """Get all system players for the game. Returns list of {name, card_number, card_layout}."""
    import json
    r = get_redis_client()
    if not r:
        return []
    try:
        key = get_system_players_key(game_id)
        data = r.hgetall(key)
        if not data:
            return []
        out = []
        for _cn, raw in data.items():
            try:
                out.append(json.loads(raw))
            except (TypeError, ValueError):
                continue
        return out
    except Exception as e:
        print(f"Error getting system players: {e}")
        return []


def system_player_remove(game_id: int, card_number: int) -> bool:
    """Remove a system player and their marked set."""
    r = get_redis_client()
    if not r:
        return False
    try:
        key = get_system_players_key(game_id)
        r.hdel(key, str(card_number))
        marked_key = get_system_card_marked_key(game_id, card_number)
        r.delete(marked_key)
        return True
    except Exception as e:
        print(f"Error removing system player: {e}")
        return False


def get_system_card_marked_numbers(game_id: int, card_number: int) -> set:
    """Get marked numbers for a system player's card."""
    r = get_redis_client()
    if not r:
        return set()
    try:
        key = get_system_card_marked_key(game_id, card_number)
        numbers = r.smembers(key)
        return {int(n) for n in numbers if n.isdigit()}
    except Exception as e:
        print(f"Error getting system card marked numbers: {e}")
        return set()


def add_system_card_marked_number(game_id: int, card_number: int, number: int) -> bool:
    """
    Mark a number on a system player's card. Returns True if number was new.
    Only call if the number is on the card (caller checks layout).
    """
    r = get_redis_client()
    if not r:
        return False
    try:
        key = get_system_card_marked_key(game_id, card_number)
        added = r.sadd(key, str(number))
        r.expire(key, 3600)
        return bool(added)
    except Exception as e:
        print(f"Error marking system card: {e}")
        return False


def cleanup_game_live_state(game_id: int):
    """
    Clean up ALL game-related Redis keys (called after game finalization).
    CRITICAL: This must delete EVERYTHING to prevent stale state blocking next game.
    """
    r = get_redis_client()
    if not r:
        return
    
    try:
        # Get all keys matching game patterns
        patterns = [
            f"game:{game_id}:live",  # Live state
            f"game:{game_id}:called_numbers",  # Called numbers list
            f"game:{game_id}:card:*:marked",  # Card marked numbers
            f"game:{game_id}:state",  # Old cache state (if exists)
            f"game:{game_id}:number_calling_lock",  # Lock (if exists)
            f"game:{game_id}:bingo_window",  # Bingo window (if exists)
            f"game:{game_id}:bingo_winners",  # Bingo winners (if exists)
            f"game:{game_id}:bingo_claim_lock",  # Claim lock (if exists)
        ]
        
        # Delete specific keys
        specific_keys = [
            f"game:{game_id}:live",
            f"game:{game_id}:called_numbers",
            f"game:{game_id}:state",
            f"game:{game_id}:number_calling_lock",
            f"game:{game_id}:bingo_window",
            f"game:{game_id}:bingo_winners",
            f"game:{game_id}:bingo_claim_lock",
        ]
        
        # Delete specific keys
        for key in specific_keys:
            r.delete(key)
        
        # Delete pattern-matched keys (card marked numbers)
        card_pattern = f"game:{game_id}:card:*:marked"
        card_keys = r.keys(card_pattern)
        if card_keys:
            r.delete(*card_keys)
        
        # System players (Redis-only)
        r.delete(get_system_players_key(game_id))
        system_card_pattern = f"game:{game_id}:system_card:*:marked"
        system_card_keys = r.keys(system_card_pattern)
        if system_card_keys:
            r.delete(*system_card_keys)
        
        # Also delete any card marked count keys
        count_pattern = f"card:*:marked_count"
        count_keys = r.keys(count_pattern)
        if count_keys:
            # Filter to only this game's cards (if we can identify them)
            # For safety, we'll be more aggressive and clean up old card keys
            pass  # Card count keys are per-card, not per-game, so we leave them
        
        print(f"✅ Cleaned up all Redis keys for game {game_id}")
    except Exception as e:
        print(f"Error cleaning up game live state: {e}")
        import traceback
        traceback.print_exc()

