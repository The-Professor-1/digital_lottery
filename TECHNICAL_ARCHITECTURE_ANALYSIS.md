# Technical Architecture Analysis - Markos Bingo

## 1. Deployment & Environment

### How many Fly.io machines are running?
**Answer: 4 machines (minimum 2 running)**
- `min_machines_running = 2` configured in `fly.toml`
- Currently shows 4 machines in deployment logs: `e82270eae4e508`, `e2863744f03468`, `48ed59eb022d68`, `7849694ce43368`
- Auto-scaling enabled: `auto_stop_machines = true`, `auto_start_machines = true`

### What is the VM size?
**Answer: shared-cpu-2x**
- Configured in `fly.toml`: `size = "shared-cpu-2x"`
- This provides: 512MB RAM, 2 shared CPUs

### Does the Fly.io machine use autoscaling?
**Answer: Yes, automatic scaling**
- `auto_stop_machines = true` - machines can sleep when idle
- `auto_start_machines = true` - machines wake up on demand
- `min_machines_running = 2` - keeps at least 2 machines running for redundancy

### How much RAM and CPU does the app actually use under load?
**Answer: Not measured yet, but configured for:**
- RAM: 512MB per machine (shared-cpu-2x)
- CPU: 2 shared CPUs per machine
- **Recommendation**: Monitor via Fly.io dashboard during load testing

---

## 2. Django Backend Architecture

### How are game events handled?
**Answer: Primary: WebSockets, Fallback: HTTP Polling**
- **Primary**: Django Channels WebSockets via `GameConsumer` (async WebSocket consumer)
- **Fallback**: HTTP polling every 2 seconds if WebSocket not connected
- Events: `number_called`, `card_selected`, `game_started`, `winner_declared`, `admin_message`

### Is there any background worker handling timers or game round calculations?
**Answer: Yes, Celery workers**
- Celery worker process: `celery -A bingo worker --loglevel=info --concurrency=2`
- Handles:
  - `task_auto_call_numbers` - Automatically calls numbers every 3 seconds
  - `task_check_bingo_for_all_cards` - Checks all cards for bingo after each number call
  - `task_process_bingo_winners` - Processes multiple winners after 1-second window
  - `task_generate_and_create_card` - Generates bingo cards in background

### How often does each player send requests during gameplay?
**Answer:**
- **Manual Mode**: 
  - Only when user clicks to mark numbers (user-initiated)
  - HTTP polling fallback: Every 2 seconds if WebSocket disconnected
- **Automatic Mode**:
  - Marks numbers automatically when called (via WebSocket events)
  - No continuous polling/requests
- **WebSocket**: Maintains persistent connection, no repeated HTTP requests

### Are there heavy DB operations on each request?
**Answer: Moderate operations with caching**
- Card data cached for 2 seconds: `cache.set(cache_key, card_data, 2)`
- Game data cached: `cache.get('game:current')` with 300s timeout
- Database operations:
  - Card queries use indexes: `['game', 'user']`, `['game', 'card_number']`
  - `select_related('user')` used to reduce queries
  - JSON fields used for `card_layout` and `selected_numbers` (stored in DB, no joins needed)

### Is the game round generated server-side or client-side?
**Answer: Server-side**
- Cards generated in backend: `generate_bingo_card()` in `game_logic.py`
- Card layout stored in database as JSON: `card_layout = models.JSONField(default=dict)`
- Game numbers called server-side via Celery task

### Is caching implemented?
**Answer: Yes, Redis caching**
- **Cache Backend**: Redis via `django.core.cache.backends.redis.RedisCache`
- **Cached Data**:
  - Game current state: `cache.get('game:current')` - 300s timeout
  - Card data: `cache.get(f'card:{game.id}:{user.id}')` - 2s timeout
  - Called numbers: `cache.get(f'called_numbers:{game.id}')` - 10s timeout
- **Redis also used for**:
  - Django Channels (WebSocket layer)
  - Celery broker and result backend
  - Bingo winner window locks (1-second window)
  - Card selection locks

### Are views async or sync?
**Answer: Mixed**
- **HTTP Views**: Synchronous (standard Django REST Framework views)
- **WebSocket Consumers**: Async (`AsyncWebsocketConsumer`)
- **ASGI Application**: Uses Daphne (async server)
- **Celery Tasks**: Synchronous (run in separate worker process)

---

## 3. Database (PostgreSQL/Neon)

### What is the Neon plan?
**Answer: Not explicitly configured in code**
- Database URL parsed from `DATABASE_URL` environment variable
- Connection pooling: `conn_max_age=300` (5 minutes)
- Connection timeout: 10 seconds

### How many reads/writes happen during one round of the game?
**Answer:**
- **Per Number Call**:
  - 1 write: Insert `CalledNumber`
  - 1 write: Update `Game.current_call_count`
  - N reads: Check all cards (via `task_check_bingo_for_all_cards`)
  - N writes: Update card `selected_numbers` (if marked automatically)
- **Per Card Selection**:
  - 1 read: Check if card exists
  - 1 write: Create `GameCard`
  - 1 write: Update `User.balance`
  - 1 write: Update `Game.derash_amount`
  - 1 write: Create `Transaction`
- **Per Bingo Claim**:
  - 1 read: Get game and card
  - 1 write: Update `GameCard.is_winner`
  - N reads: Get all winners from Redis
  - N writes: Update winner balances
  - N writes: Create transactions

### Do you store each player's bet in a separate row?
**Answer: Yes**
- Each card purchase creates a `Transaction` row with `transaction_type='bet'`
- Each `GameCard` is a separate row (one per user per game)

### Are queries using indexing?
**Answer: Yes, multiple indexes**
- `GameCard`: `['game', 'user']`, `['game', 'card_number']`
- `CalledNumber`: `['game', 'called_at']`
- `Transaction`: `['user', 'created_at']`, `['transaction_type', 'created_at']`
- `Deposit`: `['status', 'created_at']`, `['user', 'status']`

### Is there any locking or long-running transactions?
**Answer: Redis-based locking**
- Card selection: Redis `SETNX` lock with 5-second TTL
- Bingo winner window: Redis `SETNX` lock with 1-second TTL
- No database-level locking observed

### Does the game use transactions for each round?
**Answer: Not explicitly**
- Each operation (bet, win, deposit) creates a `Transaction` record
- Database transactions handled by Django ORM automatically
- No explicit `transaction.atomic()` blocks observed in game logic

---

## 4. Game Logic: Manual + Automatic Mode

### Does automatic mode hit the server continuously?
**Answer: No, uses WebSocket events**
- Automatic mode listens to WebSocket `number_called` events
- Marks numbers locally in UI (optimistic update)
- Sends `POST /api/cards/{id}/mark_number/` only once per number
- No continuous polling loop

### How often does automatic mode send bet requests?
**Answer: N/A for bets**
- Bet happens once when card is selected (not per number)
- Marking numbers: Only when a new number is called (via WebSocket)
- Frequency: ~every 3 seconds (when admin/auto-task calls next number)

### Does manual mode use the same endpoints as automatic mode?
**Answer: Yes**
- Both use: `POST /api/cards/{id}/mark_number/`
- Both use: `POST /api/cards/{id}/claim_bingo/`
- Difference: Automatic mode triggers these via WebSocket events, manual mode via user clicks

### Does each bet cause a database write?
**Answer: Yes**
- Creates `Transaction` row
- Updates `GameCard` row
- Updates `Game.derash_amount`
- Updates `User.balance`

### Does each round cause database reads for all active players?
**Answer: Yes, via Celery task**
- `task_check_bingo_for_all_cards` reads all cards for a game: `GameCard.objects.filter(game=game, is_winner=False)`
- Runs after each number is called
- Uses indexes on `game` field for efficiency

---

## 5. Frontend (Vue.js)

### How often does the frontend poll the API for updates?
**Answer:**
- **Primary**: WebSocket connection (real-time, no polling)
- **Fallback Polling**:
  - ActiveGameView: Every 2 seconds (`setInterval(this.loadGame, 2000)`)
  - CardSelectionView: Every 1 second (`setInterval(this.loadGame, 1000)`)
  - WaitingView: Every 3 seconds (`setInterval(this.loadGame, 3000)`)
- Polling stops when WebSocket connects

### Does the frontend subscribe to a live endpoint?
**Answer: Yes, WebSocket**
- WebSocket connection: `/ws/game/{game_id}/`
- Subscribes to events: `number_called`, `card_selected`, `game_started`, `winner_declared`

### Does the frontend send unnecessary repeated requests?
**Answer: Minimized**
- Optimistic updates reduce API calls
- Debouncing on mark number: 500ms cooldown
- Duplicate call tracking: `processedCalls` Set prevents duplicate WebSocket message processing
- Polling only active when WebSocket disconnected

---

## 6. Performance Characteristics

### What is the average response time of the 3 most frequent API endpoints?
**Answer: Not measured, but here are the endpoints:**
1. `GET /api/games/current/` - Cached, should be <100ms
2. `GET /api/games/{id}/my_card/` - Cached (2s), should be <100ms
3. `POST /api/cards/{id}/mark_number/` - Single DB write, should be <200ms

### What is the CPU usage when 50 players are connected?
**Answer: Not measured**
- **Recommendation**: Monitor via Fly.io dashboard
- Each machine: 2 shared CPUs, 512MB RAM
- With 4 machines: 8 total CPUs, 2GB total RAM

### What is the Django worker count?
**Answer: Not using Gunicorn - using Daphne (ASGI)**
- Server: `daphne -b 0.0.0.0 -p 8000 bingo.asgi:application`
- Daphne handles async connections natively
- Celery workers: `--concurrency=2` per machine

### Does the app use synchronous blocking I/O?
**Answer: Mixed**
- HTTP views: Synchronous (blocking)
- WebSocket consumers: Async (non-blocking)
- Celery tasks: Synchronous (run in separate process)
- Database queries: Synchronous (but cached)

---

## 7. Concurrency & Scaling

### Does Django use async views for WebSockets or SSE?
**Answer: Yes, async WebSocket consumers**
- `GameConsumer` is `AsyncWebsocketConsumer`
- Uses `database_sync_to_async` for DB operations
- Channels layer uses Redis for message passing

### If using HTTP polling, what is the frequency?
**Answer:**
- ActiveGameView: 2 seconds
- CardSelectionView: 1 second  
- WaitingView: 3 seconds
- Only used as fallback when WebSocket disconnected

### Is there any rate limiting?
**Answer: No explicit rate limiting configured**
- **Recommendation**: Add rate limiting for production

### Are DB connections pooled or created per request?
**Answer: Connection pooling**
- `CONN_MAX_AGE = 300` (5 minutes)
- Django connection pooling enabled
- Each request reuses existing connection if available

---

## 8. Potential Bottlenecks

### Which endpoints are called most frequently?
**Answer:**
1. `GET /api/games/current/` - Polled every 2 seconds (fallback)
2. `GET /api/games/{id}/my_card/` - Polled every 2 seconds (fallback)
3. `POST /api/cards/{id}/mark_number/` - Each number marked
4. WebSocket `/ws/game/{id}/` - Persistent connection

### Does the game logic block the event loop or request threads?
**Answer: Partially**
- HTTP views: Block request threads (but cached)
- WebSocket handlers: Non-blocking (async)
- Celery tasks: Run in separate worker (don't block)

### Are there any loops or heavy calculations per request?
**Answer:**
- `task_check_bingo_for_all_cards`: Loops through all cards (N cards)
- Pattern checking is in-memory (uses JSON field, no DB queries)
- Card generation: Random number generation (lightweight)

### Does each game round require scanning the entire table?
**Answer: No**
- Uses indexed queries: `GameCard.objects.filter(game=game, is_winner=False)`
- Index on `['game', 'user']` makes queries fast
- Only scans cards for the current game, not all games

---

## 9. Stress Test Behavior

### When simulating 100 users, what happens to CPU/Memory/Request latency?
**Answer: Not tested yet**
- **Recommendation**: Run load tests with:
  - 10, 50, 100, 200 concurrent users
  - Monitor CPU, memory, response times
  - Test with both WebSocket and polling fallback

### Does the system throw DB connection limit errors?
**Answer: Not observed, but potential risk**
- Connection pooling with 5-minute max age
- Multiple machines = multiple connection pools
- **Recommendation**: Monitor DB connection count

### Does the system throw timeouts?
**Answer: Not observed**
- Connection timeout: 10 seconds configured
- Celery task timeout: 30 minutes hard limit, 25 minutes soft limit

### Does the system throw 500 errors?
**Answer: Not commonly observed**
- Error handling in place
- Try-catch blocks around critical operations
- **Recommendation**: Monitor error logs

### How many simultaneous DB connections does the app open?
**Answer:**
- Per machine: Django connection pool (typically 1-5 connections)
- With 4 machines: ~4-20 connections
- Plus Celery workers: Additional connections
- **Total estimate**: 10-30 connections depending on load

---

## Summary & Recommendations

### Current Architecture Strengths:
1. ✅ WebSocket for real-time updates (reduces polling)
2. ✅ Redis caching for frequently accessed data
3. ✅ Celery for background tasks (offloads work)
4. ✅ Database indexes on frequently queried fields
5. ✅ Connection pooling configured
6. ✅ Multiple machines for redundancy

### Potential Improvements:
1. ⚠️ **Rate Limiting**: Add rate limiting to prevent abuse
2. ⚠️ **Monitoring**: Set up APM/monitoring for CPU, memory, response times
3. ⚠️ **Database Connection Monitoring**: Track connection count
4. ⚠️ **Load Testing**: Test with 100+ concurrent users
5. ⚠️ **Query Optimization**: Review N+1 query patterns
6. ⚠️ **Caching Strategy**: Consider longer cache TTLs for game data
7. ⚠️ **Async Views**: Consider converting more views to async

### Critical Metrics to Monitor:
- Response times for top 5 endpoints
- WebSocket connection count
- Database connection pool usage
- Celery task queue length
- Redis memory usage
- CPU and memory per machine

