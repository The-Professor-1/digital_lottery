#!/usr/bin/env bash
# Quick diagnostics for Digital Lottery (SQLite, no Redis/Celery).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Services =="
sudo systemctl status digitallottery-gunicorn --no-pager -l | head -25 || true
sudo systemctl status digitallottery-telegram-bot --no-pager -l | head -25 || true

echo
echo "== Recent gunicorn errors =="
sudo journalctl -u digitallottery-gunicorn -n 80 --no-pager | grep -Ei "error|traceback|exception" || echo "No recent errors."

echo
echo "== Python / migrations =="
if [ -x venv/bin/python ]; then
  venv/bin/python --version
  (cd backend && ../venv/bin/python manage.py showmigrations api | tail -12)
  (cd backend && ../venv/bin/python manage.py check)
else
  echo "venv missing at $ROOT/venv"
fi

echo
echo "== Database / cache / media =="
ls -lh backend/db.sqlite3 2>/dev/null || echo "SQLite DB missing"
ls -ld backend/cache backend/media 2>/dev/null || true

echo
echo "== Frontend build =="
ls -lh backend/frontend_dist/index.html 2>/dev/null || echo "frontend_dist missing"

echo
echo "== Nginx =="
sudo nginx -t || true
curl -s -o /dev/null -w "local app HTTP: %{http_code}\n" http://127.0.0.1:8001/ || true
