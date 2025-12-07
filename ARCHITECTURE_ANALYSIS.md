# Bingo Game Architecture & Performance Analysis

## 1. Deployment & Environment

### How many Fly.io machines are running?
**Answer: 2 machines minimum (with auto-scaling)**
- `fly.toml` shows: `min_machines_running = 2`
- `auto_stop_machines = true` and `auto_start_machines = true` (machines can sleep when idle)
- Currently running 2 machines based on deployment logs

### What is the VM size?
**Answer: Not explicitly specified (defaults to shared-cpu-1x)**
- No `vm_size` specified in `fly.toml`
- Fly.io defaults to `shared-cpu-1x` (256MB RAM, shared CPU) when not specified
- **Recommendation**: Should be explicitly set for production

### Does the Fly.io machine use autoscaling?
**Answer: Yes, with auto-stop/start**
- `auto_stop_machines = true` - machines sleep when idle
- `auto_start_machines = true` - machines wake on traffic
- `min_machines_running = 2` - keeps 2 machines always running
- No explicit max machines limit set

### How much RAM and CPU does the app actually use under load?
**Answer: Unknown (needs monitoring)**
- Default VM: 256MB RAM, shared CPU
- Running: Django ASGI (Daphne) + Telegram Bot + Redis connections
- **Needs monitoring** to determine actual usage

---

## 2. Django Backend Architecture

### How are game events handled?
**Answer: WebSockets (Django Channels) + HTTP Polling (fallback)**
- **Primary**: WebSockets via Django Channels for real-time updates
- **Fallback**: HTTP polling every 2 seconds (`setInterval(this.loadGame, 2000)`)
- Uses Redis as channel layer backend
- WebSocket events: `number_called`, `game_started`, `game_ended`, `bingo_claimed`

### Is there any background worker (Celery/RQ)?
**Answer: No**
- No Celery, RQ, or background task queue
- All operations are synchronous within request handlers
- Telegram bot runs in same process (background thread via `start-app.sh`)

### How often does each player send requests during gameplay?
**Answer:**
- **Active Game View**: Polls every 2 seconds (`setInterval(this.loadGame, 2000)`)
- **Card Selection**: Polls every 1 second (`setInterval(this.loadGame, 1000)`)
- **First number detection**: Polls every 500ms temporarily
- **Automatic mode**: Marks numbers via API calls (frequency depends on number call rate)
- **Manual mode**: User clicks trigger API calls

### Are there heavy DB operations on each request?
**Answer: Yes, multiple queries per request**
- `getCurrentGame()`: Fetches game + related gamecards + called_numbers
- `getMyCard()`: Fetches user's card with layout
- `markNumber()`: Updates card + checks bingo pattern (scans all cards)
- Each request typically does 3-5 database queries

### Is the game round generated server-side or client-side?
**Answer: Server-side**
- Cards generated in `generate_bingo_card()` (Python)
- Numbers called server-side via `call_number()` function
- Client only displays and marks numbers

### Is caching implemented (Redis, Django cache)?
**Answer: Redis for Channels only, NO Django cache**
- Redis used ONLY for Django Channels (WebSocket layer)
- **NO Django cache framework** configured
- `CACHES` setting not found in `settings.py`
- **Recommendation**: Add caching for `GameSettings.get_settings()` and frequent queries

### Are views async or sync?
**Answer: Mostly sync, with async WebSocket support**
- HTTP views: **Synchronous** (Django REST Framework)
- WebSocket consumers: **Async** (Django Channels)
- Telegram bot: **Async** (python-telegram-bot)
- Database operations: **Sync** (using `sync_to_async` wrapper in bot)

---

## 3. Database (Neon Free Tier)

### What is the Neon plan (compute size, IOPS limits)?
**Answer: Unknown from codebase (needs environment check)**
- Database URL configured via `DATABASE_URL` environment variable
- Connection pooling: `conn_max_age=300` (5 minutes)
- **Needs verification** of actual Neon plan limits

### How many reads/writes happen during one round of the game?
**Answer:**
- **Per number call**: 
  - 1 write (CalledNumber.create)
  - 1 write (Game.update)
  - N reads (all GameCards for bingo check) - **POTENTIAL BOTTLENECK**
  - WebSocket broadcast (no DB)
- **Per player marking number**:
  - 1 read (get card)
  - 1 write (update card)
  - 1 read (check bingo pattern - scans all cards)
- **Per game round (75 numbers, 50 players)**:
  - ~75 number calls × (2 writes + 50 reads) = **150 writes + 3,750 reads**
  - ~50 players × 75 marks × 3 queries = **11,250 additional queries**
  - **Total: ~15,000+ queries per game**

### Do you store each player's bet in a separate row?
**Answer: Yes**
- Each bet creates:
  - 1 `GameCard` row
  - 1 `Transaction` row (type='bet')
- Both stored separately

### Are queries using indexing?
**Answer: Yes, but could be improved**
- **Indexed fields**:
  - `GameCard`: `(game, user)`, `(game, card_number)`
  - `CalledNumber`: `(game, called_at)`
  - `Transaction`: `(user, created_at)`, `(transaction_type, created_at)`
  - `DepositRequest`: `(status, created_at)`, `(user, status)`
- **Missing indexes**:
  - `Game.status` (frequently queried)
  - `GameCard.is_winner` (bingo check scans all cards)
  - `GameCard.game` alone (already covered by composite)

### Is there any locking or long-running transactions?
**Answer: No explicit locking**
- No `select_for_update()` found
- No transaction decorators with isolation levels
- **Potential race condition**: Multiple players claiming bingo simultaneously

### Does the game use transactions for each round?
**Answer: No explicit transactions**
- Each operation saves individually
- No `@transaction.atomic` decorators found
- **Risk**: Partial updates if errors occur

---

## 4. Game Logic: Manual + Automatic Mode

### Does automatic mode hit the server continuously (loop requests)?
**Answer: Yes, but triggered by number calls**
- Automatic mode marks numbers via API when new numbers are called
- Not a continuous loop - responds to WebSocket events or polling
- Each mark triggers: `markNumber()` API call → DB write

### How often does automatic mode send bet requests?
**Answer: Not applicable (no "bet requests" in automatic mode)**
- Automatic mode marks numbers, doesn't place bets
- Bet happens once when selecting card (before game starts)
- Marking frequency: Every time a number is called (every 3 seconds by default)

### Does manual mode use the same endpoints as automatic mode?
**Answer: Yes**
- Both use `/api/games/{game_id}/cards/{card_id}/mark-number/`
- Difference: Manual = user click, Automatic = automatic API call

### Does each bet cause a database write?
**Answer: Yes, multiple writes**
- 1 write: `GameCard.create()`
- 1 write: `User.balance` update
- 1 write: `Game.derash_amount` update
- 1 write: `Transaction.create()`
- **Total: 4 writes per bet**

### Does each round cause database reads for all active players?
**Answer: Yes, on every number call**
- `check_bingo_pattern()` scans ALL GameCards for the game
- Query: `GameCard.objects.filter(game=game, is_winner=False)`
- **BOTTLENECK**: With 50 players = 50 card reads per number call
- 75 numbers × 50 reads = **3,750 reads per game** just for bingo checks

---

## 5. Frontend (Vue.js)

### How often does the frontend poll the API for updates?
**Answer:**
- **Active Game**: Every 2 seconds (`setInterval(this.loadGame, 2000)`)
- **Card Selection**: Every 1 second
- **Waiting View**: Every 3 seconds
- **Game Completed**: Every 3 seconds
- **First number detection**: Every 500ms temporarily

### Does the frontend subscribe to a live endpoint?
**Answer: Yes, WebSockets**
- Uses `WebSocketService` to connect to Django Channels
- Subscribes to `game_{game_id}` group
- Receives: `number_called`, `game_started`, `game_ended`, `bingo_claimed`
- **Fallback**: If WebSocket fails, falls back to polling

### Does the frontend send unnecessary repeated requests?
**Answer: Yes, potential issues**
- Polling continues even when WebSocket is active (redundant)
- Multiple components may poll simultaneously
- No request deduplication visible
- **Recommendation**: Disable polling when WebSocket is connected

---

## 6. Performance Characteristics

### What is the average response time of the 3 most frequent API endpoints?
**Answer: Unknown (needs monitoring)**
- Most frequent endpoints:
  1. `GET /api/games/current/` (polled every 2s)
  2. `GET /api/games/{id}/cards/my/` (polled every 2s)
  3. `POST /api/games/{id}/cards/{id}/mark-number/` (on each number call)
- **Needs APM/monitoring** to measure actual response times

### What is the CPU usage when 50 players are connected?
**Answer: Unknown (needs monitoring)**
- Factors:
  - 50 players × 2s polling = 25 requests/second
  - WebSocket connections: 50
  - Database queries: ~15,000+ per game
- **Needs load testing**

### What is the Django worker count (gunicorn workers)?
**Answer: Not using Gunicorn - using Daphne (ASGI)**
- Server: **Daphne** (ASGI server for Channels)
- No worker configuration found
- Daphne runs single-threaded async (handles concurrency via async/await)
- **Recommendation**: Consider multiple Daphne processes for CPU-bound tasks

### Does the app use synchronous blocking I/O?
**Answer: Yes, for database operations**
- All Django ORM queries are synchronous
- Database I/O blocks the event loop
- Telegram bot uses `sync_to_async` wrapper (adds overhead)

---

## 7. Concurrency & Scaling

### Does Django use async views for WebSockets or SSE?
**Answer: Yes, for WebSockets only**
- WebSocket consumers: Async (Django Channels)
- HTTP views: Synchronous (Django REST Framework)
- No Server-Sent Events (SSE)

### If using HTTP polling, what is the frequency?
**Answer:**
- Active game: **2 seconds**
- Card selection: **1 second**
- Other views: **3 seconds**

### Is there any rate limiting?
**Answer: No**
- No rate limiting middleware found
- No throttling in REST Framework settings
- **Risk**: DDoS or spam requests

### Are DB connections pooled or created per request?
**Answer: Pooled (with 5-minute max age)**
- `conn_max_age=300` (5 minutes)
- Connections reused across requests
- **Potential issue**: Stale connections after machine wake-up

---

## 8. Potential Bottlenecks

### Which endpoints are called most frequently?
**Answer:**
1. `GET /api/games/current/` - Every 2s per player
2. `GET /api/games/{id}/cards/my/` - Every 2s per player
3. `POST /api/games/{id}/cards/{id}/mark-number/` - On each number call

### Does the game logic block the event loop or request threads?
**Answer: Yes**
- Database queries are synchronous (blocking)
- `check_bingo_pattern()` scans all cards (CPU + DB intensive)
- No async database driver (using sync psycopg2)

### Are there any loops or heavy calculations per request?
**Answer: Yes**
- `check_bingo_pattern()`: Loops through ALL game cards
- `generate_bingo_card()`: Random sampling (lightweight)
- Bingo pattern matching: Checks 12 patterns per card

### Does each game round require scanning the entire table?
**Answer: Yes, on every number call**
- `check_bingo_pattern()` queries: `GameCard.objects.filter(game=game, is_winner=False)`
- Scans ALL cards for the game
- **Major bottleneck** with many players

---

## 9. Stress Test Behavior

### When you simulate 100 users, what happens to:

#### CPU usage
**Answer: Unknown (needs testing)**
- Estimated: High (100 × 0.5 req/s = 50 req/s)
- Database queries: ~30,000+ per game
- **Prediction**: CPU will spike during bingo checks

#### Memory usage
**Answer: Unknown (needs testing)**
- Each WebSocket connection: ~1-2KB
- 100 connections: ~200KB
- Django process: ~50-100MB baseline
- **Prediction**: Should be manageable (<256MB)

#### Request latency
**Answer: Unknown (needs testing)**
- Factors:
  - Database query time (scales with players)
  - Network latency to Neon
  - Concurrent request handling
- **Prediction**: Latency will increase with player count

### Does the system ever throw:

#### DB connection limit errors
**Answer: Possible**
- Neon Free Tier: Limited connections (typically 10-20)
- 2 machines × multiple connections = potential limit
- `conn_max_age=300` helps but may not be enough

#### Timeouts
**Answer: Possible**
- Long-running bingo checks with many players
- Database query timeouts (10s connect timeout set)
- **Risk**: High with 100+ players

#### 500 errors
**Answer: Possible**
- Race conditions in bingo claiming
- Database connection exhaustion
- Memory issues under heavy load

### How many simultaneous DB connections does the app open?
**Answer:**
- Per machine: ~5-10 connections (Daphne + bot + pooling)
- 2 machines: ~10-20 connections
- **Risk**: Exceeds Neon Free Tier limits (typically 10-20 max)

---

## Critical Recommendations

1. **Add explicit VM size** in `fly.toml` (e.g., `vm_size = "shared-cpu-2x"` for 512MB RAM)
2. **Implement Django caching** for `GameSettings` and frequent queries
3. **Optimize bingo checking**: Use database-level pattern matching or cache results
4. **Add database indexes**: `Game.status`, `GameCard.is_winner`
5. **Implement rate limiting** to prevent abuse
6. **Add monitoring**: APM tool to track CPU, memory, latency
7. **Optimize polling**: Disable when WebSocket is active
8. **Consider connection pooling**: Use PgBouncer or similar
9. **Add transaction management**: Use `@transaction.atomic` for critical operations
10. **Load test**: Simulate 100+ concurrent users to identify bottlenecks

