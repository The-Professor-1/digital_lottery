#!/bin/bash
# EC2 Deployment Script for Markos Bingo (Django + Vue.js)
# This script fixes all WebSocket and deployment issues

set -e

echo "🚀 Starting EC2 Deployment Fixes..."

# 1. Update Nginx Configuration
echo "📝 Updating Nginx configuration..."
sudo tee /etc/nginx/sites-available/goodbingo > /dev/null <<'EOF'
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
EOF

# Enable site if not already enabled
if [ ! -L /etc/nginx/sites-enabled/goodbingo ]; then
    sudo ln -s /etc/nginx/sites-available/goodbingo /etc/nginx/sites-enabled/
fi

# Test and reload nginx
sudo nginx -t
sudo systemctl reload nginx
echo "✅ Nginx configuration updated"

# 2. Create/Update Daphne systemd service
echo "📝 Creating Daphne systemd service..."
sudo tee /etc/systemd/system/bingo-daphne.service > /dev/null <<'EOF'
[Unit]
Description=Bingo Daphne ASGI Server (WebSocket Support)
After=network.target redis.service postgresql.service

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/apps/good-bingo/arif_bingo/backend
Environment="PATH=/home/ubuntu/apps/good-bingo/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=bingo.settings"
ExecStart=/home/ubuntu/apps/good-bingo/venv/bin/daphne -b 127.0.0.1 -p 8000 bingo.asgi:application
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bingo-daphne
sudo systemctl restart bingo-daphne
echo "✅ Daphne service created and started"

# 3. Verify Redis is running
echo "🔍 Verifying Redis connection..."
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis is running"
else
    echo "❌ Redis is not running. Starting Redis..."
    sudo systemctl start redis-server
    sudo systemctl enable redis-server
fi

# 4. Verify Celery workers are running
echo "🔍 Checking Celery workers..."
if systemctl is-active --quiet celery; then
    echo "✅ Celery service is running"
    sudo systemctl restart celery
else
    echo "⚠️ Celery service not found. Please check celery.service configuration."
fi

# 5. Collect static files
echo "📦 Collecting static files..."
cd /home/ubuntu/apps/good-bingo/arif_bingo/backend
source /home/ubuntu/apps/good-bingo/venv/bin/activate
python manage.py collectstatic --noinput
echo "✅ Static files collected"

# 6. Restart all services
echo "🔄 Restarting all services..."
sudo systemctl restart bingo-daphne
sudo systemctl restart celery
# Keep Gunicorn running for HTTP if needed, or stop it if using Daphne for everything
# sudo systemctl stop gunicorn  # Uncomment if using Daphne for everything

echo "✅ All services restarted"

# 7. Show status
echo ""
echo "📊 Service Status:"
echo "=================="
sudo systemctl status bingo-daphne --no-pager -l | head -10
echo ""
sudo systemctl status celery --no-pager -l | head -10
echo ""
echo "🔍 Checking ports:"
sudo netstat -tlnp | grep -E ":(8000|6379)" || echo "Ports not found"

echo ""
echo "✅ Deployment fixes completed!"
echo ""
echo "📝 Next steps:"
echo "1. Check WebSocket connection: Open browser console and verify connection to wss://goodbingo.shop/ws/game/{game_id}/"
echo "2. Test number calling: Start a game and verify numbers appear sequentially"
echo "3. Test winner broadcasting: Have multiple players and verify all see winner banner"
echo "4. Check logs: sudo journalctl -u bingo-daphne -f"

