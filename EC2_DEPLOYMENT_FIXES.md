# EC2 Deployment Fixes for Markos Bingo (Django + Vue.js)

## Critical Issues Identified

1. **Admin Dashboard Not Opening** - Nginx routing issue or static files not served
2. **Numbers Called in Background but UI Stuck** - WebSocket connection failure or message batching
3. **Numbers Increasing by 4-5 at Once** - WebSocket messages batched/delayed in Redis channel layer
4. **Winner Banner Not Broadcasting** - WebSocket broadcast not reaching all clients
5. **Players Stuck on Card Selection** - WebSocket reconnection issues or game state not updating

## Root Causes

### 1. Nginx Configuration Missing Proper WebSocket Support
The nginx config has `/ws/` location but may be missing proper timeout/buffering settings.

### 2. Daphne/ASGI Server Not Running or Misconfigured
Django Channels requires Daphne (ASGI server) instead of Gunicorn for WebSocket support.

### 3. Redis Channel Layer Configuration
Redis channel layer might be batching messages or have capacity issues.

### 4. WebSocket Connection Timeout
Long-running WebSocket connections might be timing out.

### 5. Celery Workers Not Processing Tasks
Celery workers might not be running or not processing tasks correctly.

## Fixes

### Fix 1: Update Nginx Configuration for Django Channels WebSocket

**CRITICAL**: Update `/etc/nginx/sites-available/goodbingo`:

```nginx
# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name goodbingo.shop www.goodbingo.shop;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    return 301 https://$host$request_uri;
}

# HTTPS main server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name goodbingo.shop www.goodbingo.shop;

    ssl_certificate /etc/letsencrypt/live/goodbingo.shop/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/goodbingo.shop/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    access_log /var/log/nginx/goodbingo_access.log;
    error_log /var/log/nginx/goodbingo_error.log;

    client_max_body_size 10M;

    # Frontend static files (Vue.js build)
    location / {
        alias /home/ubuntu/apps/good-bingo/arif_bingo/backend/staticfiles/;
        try_files $uri $uri/ /index.html;
        index index.html;
    }

    # CRITICAL: Django Channels WebSocket support
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        
        # WebSocket upgrade headers (CRITICAL)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CRITICAL: Long timeouts for WebSocket (24 hours)
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_connect_timeout 60s;
        
        # Disable buffering for real-time communication
        proxy_buffering off;
        proxy_cache off;
        
        # CRITICAL: Don't close connection on timeout
        proxy_ignore_client_abort on;
    }

    # Backend API (Django)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
    }

    # Admin dashboard
    location /admin {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files
    location /static/ {
        alias /home/ubuntu/apps/good-bingo/arif_bingo/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

After updating:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Fix 2: Ensure Daphne is Running for WebSocket Support

**CRITICAL**: Django Channels requires Daphne (ASGI server), not just Gunicorn.

Check if Daphne is running:
```bash
ps aux | grep daphne
```

If not running, create systemd service `/etc/systemd/system/bingo-daphne.service`:

```ini
[Unit]
Description=Bingo Daphne ASGI Server
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/apps/good-bingo/arif_bingo/backend
Environment="PATH=/home/ubuntu/apps/good-bingo/venv/bin"
ExecStart=/home/ubuntu/apps/good-bingo/venv/bin/daphne -b 127.0.0.1 -p 8000 bingo.asgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

Start Daphne:
```bash
sudo systemctl daemon-reload
sudo systemctl enable bingo-daphne
sudo systemctl start bingo-daphne
sudo systemctl status bingo-daphne
```

**IMPORTANT**: You need BOTH Gunicorn (for HTTP) and Daphne (for WebSocket):
- Gunicorn: Handles regular HTTP requests
- Daphne: Handles WebSocket connections

Or use Daphne for everything (recommended for simplicity):
```bash
# Stop Gunicorn
sudo systemctl stop gunicorn

# Update nginx to proxy all traffic to Daphne on port 8000
# (Already configured above)
```

### Fix 3: Verify Redis Connection and Channel Layer

Check Redis is running:
```bash
redis-cli ping
# Should return: PONG
```

Test Redis channel layer:
```bash
cd /home/ubuntu/apps/good-bingo/arif_bingo/backend
source /home/ubuntu/apps/good-bingo/venv/bin/activate
python manage.py shell
```

In Django shell:
```python
from channels.layers import get_channel_layer
channel_layer = get_channel_layer()
# Test sending a message
channel_layer.send('test_channel', {'type': 'test_message', 'text': 'test'})
```

Check Redis keys:
```bash
redis-cli KEYS "asgi:*"
redis-cli KEYS "game:*"
```

### Fix 4: Fix Redis Channel Layer Message Batching

The issue where numbers increase by 4-5 at once is likely due to Redis channel layer batching messages.

Update `backend/bingo/settings.py`:

```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [REDIS_URL],
            "capacity": 1500,
            "expiry": 10,
            # CRITICAL: Disable message grouping to prevent batching
            "group_expiry": 60,  # Group messages expire after 60 seconds
            "channel_capacity": {
                "http.request": 200,
                "http.response!*": 10,
                "websocket.send!*": 10,  # Limit WebSocket message queue
            },
            # CRITICAL: Send messages immediately, don't batch
            "symmetric_encryption_keys": [SECRET_KEY[:32].encode()] if SECRET_KEY else None,
        },
    },
}
```

### Fix 5: Verify Celery Workers are Running

Check Celery workers:
```bash
ps aux | grep celery
# Should see celery worker processes

# Check Celery status
cd /home/ubuntu/apps/good-bingo/arif_bingo/backend
source /home/ubuntu/apps/good-bingo/venv/bin/activate
celery -A bingo inspect active
```

If not running, start Celery:
```bash
# Check systemd service
sudo systemctl status celery

# Or start manually
cd /home/ubuntu/apps/good-bingo/arif_bingo/backend
source /home/ubuntu/apps/good-bingo/venv/bin/activate
celery -A bingo worker --loglevel=info --queues=gameplay,registration --concurrency=2
```

### Fix 6: Fix Number Calling Sequential Display

The issue is likely in `backend/api/tasks.py` - ensure messages are sent immediately:

Check `task_auto_call_numbers` - after calling a number, ensure WebSocket message is sent immediately:

```python
# After calling number, broadcast immediately
async_to_sync(channel_layer.group_send)(
    f'game_{game_id}',
    {
        'type': 'number_called',
        'data': {
            'number': called_number.number,
            'letter': called_number.letter,
            'call_count': game.current_call_count
        }
    }
)
```

### Fix 7: Fix Winner Banner Broadcasting

Ensure `backend/api/game_logic.py` in `claim_bingo_unified` broadcasts to all clients:

```python
# Broadcast winner immediately
async_to_sync(channel_layer.group_send)(
    f'game_{game.id}',
    {
        'type': 'winner_declared',
        'data': winner_data
    }
)
```

Verify the consumer in `backend/api/consumers.py` has the `winner_declared` handler (already present).

### Fix 8: Admin Dashboard Access

The admin dashboard should be at `https://goodbingo.shop/admin/` (Django admin).

Check:
1. Django admin is enabled in `INSTALLED_APPS`
2. Superuser exists: `python manage.py createsuperuser`
3. Nginx is proxying `/admin` to Django (already configured above)
4. Static files are collected: `python manage.py collectstatic --noinput`

## Deployment Checklist

1. ✅ Update nginx configuration with proper WebSocket support for `/ws/`
2. ✅ Ensure Daphne is running (ASGI server for WebSocket)
3. ✅ Verify Redis connection and channel layer
4. ✅ Update Redis channel layer configuration to prevent batching
5. ✅ Verify Celery workers are running
6. ✅ Restart all services:
   ```bash
   sudo systemctl reload nginx
   sudo systemctl restart bingo-daphne
   sudo systemctl restart celery
   sudo systemctl restart gunicorn  # If still using Gunicorn for HTTP
   ```
7. ✅ Test WebSocket connection:
   - Open browser console on `https://goodbingo.shop`
   - Check for WebSocket connection errors
   - Verify connection to `wss://goodbingo.shop/ws/game/{game_id}/`
   - Check network tab for WebSocket frames
8. ✅ Test number calling:
   - Start a game
   - Verify numbers appear sequentially in UI (not batched)
   - Check backend logs: `sudo journalctl -u bingo-daphne -f`
   - Check Celery logs: `sudo journalctl -u celery -f`
9. ✅ Test winner broadcasting:
   - Have multiple players in game
   - Verify all see winner banner when someone wins
   - Check WebSocket messages in browser console
10. ✅ Test admin dashboard:
    - Access `https://goodbingo.shop/admin/`
    - Verify it loads correctly

## Debugging Commands

```bash
# Check nginx error logs
sudo tail -f /var/log/nginx/goodbingo_error.log

# Check Daphne logs (WebSocket server)
sudo journalctl -u bingo-daphne -f

# Check Gunicorn logs (HTTP server)
sudo journalctl -u gunicorn -f

# Check Celery logs
sudo journalctl -u celery -f

# Check Redis connection
redis-cli ping
redis-cli KEYS "asgi:*"
redis-cli KEYS "game:*"

# Check if port 8000 is listening (Daphne/Gunicorn)
sudo netstat -tlnp | grep 8000

# Check WebSocket connections
sudo netstat -an | grep :8000 | grep ESTABLISHED

# Test WebSocket endpoint
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: test" https://goodbingo.shop/ws/game/1/

# Check Django channels
cd /home/ubuntu/apps/good-bingo/arif_bingo/backend
source /home/ubuntu/apps/good-bingo/venv/bin/activate
python manage.py shell
# Then in shell:
# from channels.layers import get_channel_layer
# channel_layer = get_channel_layer()
# print(channel_layer)
```

## Common Issues and Solutions

### Issue: WebSocket connection fails with 404
**Solution**: 
- Ensure nginx `/ws/` location block is configured correctly
- Verify Daphne is running on port 8000
- Check `ALLOWED_HOSTS` in Django settings includes your domain

### Issue: Numbers called but UI not updating
**Solution**: 
- Check browser console for WebSocket errors
- Verify WebSocket connects to `wss://goodbingo.shop/ws/game/{game_id}/`
- Check Redis channel layer is working: `redis-cli KEYS "asgi:*"`
- Verify Celery workers are processing tasks

### Issue: Numbers increasing by 4-5 at once
**Solution**: 
- This is Redis channel layer batching messages
- Update `CHANNEL_LAYERS` config to reduce batching
- Check Celery worker concurrency - might be processing multiple tasks simultaneously
- Verify Redis lock is working in `task_auto_call_numbers`

### Issue: Winner banner only shows on winner's phone
**Solution**: 
- Ensure `channel_layer.group_send()` is called with correct group name `f'game_{game.id}'`
- Verify all clients are in the same channel group
- Check consumer `winner_declared` handler is working
- Check browser console for WebSocket messages on non-winner devices

### Issue: Players stuck on card selection
**Solution**: 
- Check WebSocket reconnection logic in `frontend/src/services/websocket.js`
- Verify game state is being updated via WebSocket
- Check if `game_started` event is being received
- Verify Celery tasks are running and updating game state

### Issue: Admin dashboard returns 404
**Solution**: 
- Verify Django admin is enabled: `INSTALLED_APPS` includes `'django.contrib.admin'`
- Check nginx is proxying `/admin` to Django
- Ensure static files are collected: `python manage.py collectstatic --noinput`
- Check superuser exists: `python manage.py createsuperuser`

### Issue: Celery tasks not running
**Solution**:
- Check Celery service is running: `sudo systemctl status celery`
- Verify Redis is accessible: `redis-cli ping`
- Check Celery logs: `sudo journalctl -u celery -f`
- Verify queues are correct: `celery -A bingo inspect active_queues`

