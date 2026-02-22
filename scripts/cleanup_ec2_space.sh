#!/bin/bash
#
# EC2 space cleanup: clear old logs and prune DB (keep last 20 records).
# Run every 20 minutes via cron: */20 * * * * /home/ubuntu/markos-bingo/scripts/cleanup_ec2_space.sh >> /var/log/cleanup_ec2.log 2>&1
#
# Does NOT delete: users, transactions, or any user data. Only prunes:
#   games (keeps last 20 + all active/waiting), transfers, withdraw_requests,
#   deposit_requests, broadcast_messages.
#

set -e

# Project root (backend parent). Set on EC2 to your app path, e.g. /home/ubuntu/markos-bingo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
LOG_DIR="${CLEANUP_LOG_DIR:-$PROJECT_ROOT/logs}"

# Optional: max age for log files (days). Delete logs older than this.
LOG_MAX_AGE_DAYS="${CLEANUP_LOG_MAX_DAYS:-7}"

cd "$PROJECT_ROOT"

# 1) Remove old application log files (frees disk)
if [ -d "$LOG_DIR" ]; then
  find "$LOG_DIR" -type f \( -name "*.log" -o -name "*.log.*" \) -mtime +"$LOG_MAX_AGE_DAYS" -delete 2>/dev/null || true
fi
# Common log locations
[ -d "$BACKEND_DIR/logs" ] && find "$BACKEND_DIR/logs" -type f -name "*.log" -mtime +"$LOG_MAX_AGE_DAYS" -delete 2>/dev/null || true
[ -d "/var/log/celery" ]   && find /var/log/celery -type f -name "*.log" -mtime +"$LOG_MAX_AGE_DAYS" -delete 2>/dev/null || true

# 2) Django: prune old DB records (keep last 20 per table). Never touches users or transactions.
if [ -d "$BACKEND_DIR" ] && [ -f "$BACKEND_DIR/manage.py" ]; then
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-bingo.settings}"
  cd "$BACKEND_DIR"
  # Use venv if present (common on EC2)
  if [ -d "$PROJECT_ROOT/venv/bin" ]; then
    . "$PROJECT_ROOT/venv/bin/activate"
  elif [ -d "$BACKEND_DIR/venv/bin" ]; then
    . "$BACKEND_DIR/venv/bin/activate"
  fi
  python3 manage.py prune_old_data --keep 20
  cd "$PROJECT_ROOT"
fi

# 3) Optional: clear pip/apt caches (uncomment if you need more space)
# apt-get clean 2>/dev/null || true
# rm -rf /var/cache/apt/archives/*.deb 2>/dev/null || true

exit 0
