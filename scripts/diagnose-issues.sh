#!/bin/bash
# Diagnostic script for admin dashboard and registration reward issues

echo "=========================================="
echo "Diagnostic Script for Production Issues"
echo "=========================================="
echo ""

echo "1. Checking Celery service status..."
echo "-----------------------------------"
sudo systemctl status celery.service --no-pager -l | head -20
echo ""

echo "2. Checking Celery worker processes..."
echo "-----------------------------------"
ps aux | grep celery | grep -v grep || echo "No Celery processes found"
echo ""

echo "3. Checking Celery logs (last 50 lines)..."
echo "-----------------------------------"
if systemctl list-units --type=service --all | grep -q "celery.service"; then
    sudo journalctl -u celery.service -n 50 --no-pager | grep -E "registration|reward|error|ERROR|WARNING" || echo "No relevant logs found"
else
    echo "Celery service not found"
fi
echo ""

echo "4. Checking Redis connection..."
echo "-----------------------------------"
cd /home/ubuntu/apps/good-bingo/arif_bingo/backend
source /home/ubuntu/apps/good-bingo/venv/bin/activate
python -c "
import redis
from django.conf import settings
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
import django
django.setup()

try:
    r = redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)
    r.ping()
    print('✅ Redis connection successful')
except Exception as e:
    print(f'❌ Redis connection failed: {e}')
"
echo ""

echo "5. Checking recent registration reward tasks..."
echo "-----------------------------------"
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
import django
django.setup()

from api.models import Transaction, User
from datetime import datetime, timedelta

# Check transactions from last 24 hours
recent = Transaction.objects.filter(
    transaction_type='deposit',
    description='Registration gift',
    created_at__gte=datetime.now() - timedelta(days=1)
).order_by('-created_at')[:10]

if recent:
    print(f'Found {recent.count()} registration gifts in last 24 hours:')
    for t in recent:
        print(f'  User {t.user.telegram_id}: {t.amount} at {t.created_at}')
else:
    print('❌ No registration gifts found in last 24 hours')
"
echo ""

echo "6. Checking users with zero balance who should have registration gift..."
echo "-----------------------------------"
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
import django
django.setup()

from api.models import User, Transaction
from datetime import datetime, timedelta

# Find users registered in last 24 hours with zero balance
recent_users = User.objects.filter(
    created_at__gte=datetime.now() - timedelta(days=1),
    balance=0,
    phone_number__isnull=False
).exclude(phone_number='')[:10]

if recent_users:
    print(f'Found {recent_users.count()} recent users with zero balance:')
    for u in recent_users:
        has_gift = Transaction.objects.filter(
            user=u,
            transaction_type='deposit',
            description='Registration gift'
        ).exists()
        print(f'  User {u.telegram_id} ({u.phone_number}): balance={u.balance}, has_gift={has_gift}')
else:
    print('✅ No recent users with zero balance found')
"
echo ""

echo "7. Testing admin dashboard access..."
echo "-----------------------------------"
echo "To test admin dashboard:"
echo "  1. Go to: https://www.goodbingo.shop/admin/"
echo "  2. Login with Django superuser credentials"
echo "  3. Then go to: https://www.goodbingo.shop/admin-dashboard/"
echo ""

echo "8. Checking Gunicorn service status..."
echo "-----------------------------------"
sudo systemctl status gunicorn --no-pager -l | head -30
echo ""

echo "9. Checking recent Gunicorn errors..."
echo "-----------------------------------"
sudo journalctl -u gunicorn -n 50 --no-pager | grep -iE "error|exception|traceback" | tail -20 || echo "No errors found"
echo ""

echo "=========================================="
echo "Diagnostic complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. If Celery is not running: sudo systemctl start celery"
echo "  2. If Celery is running but not processing: check Redis connection"
echo "  3. For admin dashboard: ensure you're logged in at /admin/ first"
echo "  4. Check Celery logs: sudo journalctl -u celery -f"

