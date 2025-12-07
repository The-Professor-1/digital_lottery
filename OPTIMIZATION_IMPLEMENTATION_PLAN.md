# Performance Optimization Implementation Plan

## Overview
Implement 4 critical optimizations to improve system capacity by 3x:
1. Disable polling when WebSocket connected (removes 70% server load)
2. Increase Fly.io VM size (quick infrastructure fix)
3. Implement Redis caching for game data (reduces DB reads by 90%)
4. Optimize bingo checking (eliminates full table scans)

---

## Phase 1: Disable Polling When WebSocket Connected

**Time Estimate:** 30 minutes  
**Files to modify:**
- `frontend/src/views/ActiveGameView.vue`
- `frontend/src/services/websocket.js`

### Changes:

1. **In `frontend/src/services/websocket.js`:**
   - Add `isConnected()` method that returns `this.ws && this.ws.readyState === WebSocket.OPEN`
   - Add getter property `connected` for easy access

2. **In `frontend/src/views/ActiveGameView.vue`:**
   - Add `wsConnected: false` to data properties
   - Modify `setupWebSocket()`:
     - Set `this.wsConnected = true` on 'connected' event
     - Set `this.wsConnected = false` on 'disconnected' event
   - Modify `mounted()`:
     - Only start polling interval if `!this.wsConnected`
     - Create helper method `startPolling()` and `stopPolling()`
   - Add watcher or event handler to toggle polling based on `wsConnected` state
   - Keep fallback: if WebSocket disconnects, restart polling

### Implementation Details:
```javascript
// In setupWebSocket():
this.ws.on('connected', () => {
  this.wsConnected = true
  this.stopPolling() // Stop polling when WS connects
})

this.ws.on('disconnected', () => {
  this.wsConnected = false
  this.startPolling() // Resume polling when WS disconnects
})

// Helper methods:
startPolling() {
  if (!this.interval && !this.wsConnected) {
    this.interval = setInterval(this.loadGame, 2000)
  }
}

stopPolling() {
  if (this.interval) {
    clearInterval(this.interval)
    this.interval = null
  }
}
```

---

## Phase 2: Increase Fly.io VM Size

**Time Estimate:** 2 minutes  
**Files to modify:**
- `fly.toml`

### Changes:

Add VM configuration to `fly.toml`:
```toml
[vm]
  size = "shared-cpu-2x"
```

**Alternative (more explicit):**
```toml
[[vm]]
  cpu_kind = "shared"
  cpus = 2
  memory_mb = 512
```

**Note:** This is configuration-only, no code changes needed.

---

## Phase 3: Implement Redis Caching

**Time Estimate:** 2-3 hours  
**Files to modify:**
- `backend/bingo/settings.py`
- `backend/api/views.py`
- `backend/api/game_logic.py`
- `backend/api/models.py` (GameSettings)

### Changes:

1. **Add Django Cache Configuration** in `backend/bingo/settings.py`:
```python
# Add after CHANNEL_LAYERS configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'bingo',
        'TIMEOUT': 300,  # Default 5 minutes
    }
}
```

**Note:** May need to install `django-redis` package if not already installed.

2. **Cache `getCurrentGame()` endpoint** in `backend/api/views.py`:
   - Location: `GameViewSet.current()` method
   - Cache key: `game:current:{game_id}`
   - Cache timeout: 5 seconds
   - Invalidate on: game status change, number called

3. **Cache `getMyCard()` endpoint** in `backend/api/views.py`:
   - Location: `GameViewSet.my_card()` method
   - Cache key: `card:{game_id}:{user_id}`
   - Cache timeout: 2 seconds
   - Invalidate on: card update (mark number)

4. **Cache called numbers** in `backend/api/game_logic.py`:
   - Location: `check_bingo()` and `claim_bingo()` functions
   - Cache key: `called_numbers:{game_id}`
   - Cache timeout: 10 seconds
   - Invalidate on: new number called

5. **Cache GameSettings** in `backend/api/models.py`:
   - Location: `GameSettings.get_settings()` classmethod
   - Cache key: `game_settings`
   - Cache timeout: 60 seconds
   - Invalidate on: settings save

### Implementation Pattern:
```python
from django.core.cache import cache

# Get from cache or DB
def get_cached_game(game_id):
    cache_key = f'game:current:{game_id}'
    game_data = cache.get(cache_key)
    if game_data is None:
        # Fetch from DB and cache
        game = Game.objects.get(id=game_id)
        game_data = serialize_game(game)
        cache.set(cache_key, game_data, 5)  # 5 second TTL
    return game_data

# Invalidate on update
def call_number(game, number):
    # ... existing code ...
    # Invalidate cache
    cache.delete(f'called_numbers:{game.id}')
    cache.delete(f'game:current:{game.id}')
```

---

## Phase 4: Optimize Bingo Checking

**Time Estimate:** 4-6 hours  
**Files to modify:**
- `backend/api/game_logic.py`
- `backend/api/views.py` (mark_number endpoint)

### Changes:

1. **Optimize `check_bingo()` function** in `backend/api/game_logic.py`:
   - Current: `CalledNumber.objects.filter(game=game).values_list('number', flat=True)`
   - Change: Use cached called numbers from Phase 3
   - Pattern checking logic stays the same (already efficient)

2. **Optimize `claim_bingo()` function** in `backend/api/game_logic.py`:
   - Current: Queries all called numbers
   - Change: Use cached called numbers
   - Keep simultaneous winner query (needed for split logic)

3. **Add early exit optimization**:
   - Before checking patterns, verify card has enough marked numbers
   - If `len(card.selected_numbers) < 5`, return `(False, None)` immediately
   - This avoids pattern checking for cards that can't possibly have bingo

4. **Optional: In-memory progress tracking** (for very high player counts):
   - Track marked count per card in Redis
   - Key: `bingo_progress:{game_id}:{card_id}`
   - Update on each `mark_number_on_card()` call
   - Only check bingo when count >= 5

### Implementation Details:
```python
def check_bingo(card: GameCard, game: Game) -> Tuple[bool, str]:
    """Optimized bingo check using cached data"""
    # Early exit: not enough numbers marked
    if len(card.selected_numbers) < 5:
        return (False, None)
    
    # Use cached called numbers (from Phase 3)
    cache_key = f'called_numbers:{game.id}'
    called_numbers = cache.get(cache_key)
    if called_numbers is None:
        called_numbers = list(CalledNumber.objects.filter(game=game).values_list('number', flat=True))
        cache.set(cache_key, called_numbers, 10)
    
    # Rest of pattern checking logic (unchanged)
    layout = card.card_layout
    # ... existing pattern checking code ...
```

---

## Testing Strategy

### Phase 1 Testing:
- [ ] Verify polling stops when WebSocket connects
- [ ] Verify polling resumes when WebSocket disconnects
- [ ] Test with network interruptions
- [ ] Verify no duplicate data loading

### Phase 2 Testing:
- [ ] Deploy and verify VM size change in Fly.io dashboard
- [ ] Monitor memory usage after deployment

### Phase 3 Testing:
- [ ] Verify cache hits in application logs
- [ ] Test cache invalidation on game updates
- [ ] Monitor Redis memory usage
- [ ] Load test: compare DB query count before/after

### Phase 4 Testing:
- [ ] Load test with 50+ concurrent players
- [ ] Verify bingo detection still works correctly
- [ ] Monitor query count reduction
- [ ] Test edge cases (simultaneous winners, etc.)

---

## Deployment Order

1. **Phase 1** (Frontend only) - Deploy first, no backend changes
2. **Phase 2** (Config only) - Quick infrastructure change
3. **Phase 3** (Caching) - Backend changes, test thoroughly before Phase 4
4. **Phase 4** (Bingo optimization) - Depends on Phase 3 cache implementation

---

## Expected Performance Improvements

- **Phase 1**: 70% reduction in HTTP requests (polling eliminated when WS active)
- **Phase 2**: Better handling of concurrent connections, more memory headroom
- **Phase 3**: 90% reduction in database reads for frequently accessed data
- **Phase 4**: Eliminates O(n) table scans, reduces CPU usage dramatically

**Combined Result**: System capacity should increase by 3x as stated in requirements.

---

## Risk Mitigation

1. **Cache invalidation bugs**: Test thoroughly, add logging for cache operations
2. **WebSocket connection issues**: Keep polling as fallback (already implemented)
3. **Redis memory**: Monitor usage, set appropriate TTLs
4. **Bingo detection accuracy**: Maintain existing logic, only optimize data fetching

---

## Rollback Plan

Each phase can be rolled back independently:
- Phase 1: Revert frontend changes
- Phase 2: Remove VM config from fly.toml
- Phase 3: Remove cache.get/set calls, use direct DB queries
- Phase 4: Revert to original check_bingo implementation

