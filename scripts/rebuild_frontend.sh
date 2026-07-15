#!/usr/bin/env bash
# Rebuild frontend on EC2 and make gunicorn serve the new files.
# Usage (from repo root on EC2):  bash scripts/rebuild_frontend.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Cleaning old builds..."
rm -rf frontend_dist backend/frontend_dist

echo "Building Vue app → backend/frontend_dist ..."
cd frontend
npm ci
npm run build
cd "$ROOT"

if [ ! -f backend/frontend_dist/index.html ]; then
  echo "ERROR: build failed — backend/frontend_dist/index.html missing"
  exit 1
fi

echo "collectstatic + restart gunicorn..."
cd backend
if [ -x ../venv/bin/python ]; then
  ../venv/bin/python manage.py collectstatic --noinput
else
  python3 manage.py collectstatic --noinput || true
fi
cd "$ROOT"

sudo systemctl restart carlottery-gunicorn
echo "Done. Hard-refresh admin (Ctrl+Shift+R) and reopen the Telegram mini-app."
