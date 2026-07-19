#!/usr/bin/env bash
# Full deploy on EC2 when GitHub Actions SSH fails.
# Usage (on EC2):  cd ~/apps/DigitalLottery && bash scripts/rebuild_frontend.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "ERROR: venv missing at $VENV_PY"
  exit 1
fi

echo "Pulling latest code..."
git fetch origin
if git show-ref --quiet refs/remotes/origin/master; then
  git reset --hard origin/master
elif git show-ref --quiet refs/remotes/origin/main; then
  git reset --hard origin/main
else
  echo "WARN: could not detect main/master — using current checkout"
fi
# Drop untracked migration leftovers (e.g. local 0047_merge_*) that conflict with git
git clean -fd -- backend/api/migrations
git log -1 --oneline

echo "Installing Python deps..."
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$VENV_PY" -r requirements.txt
else
  "$VENV_PY" -m pip install -r requirements.txt
fi

echo "Cleaning old frontend builds..."
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

echo "Running migrations..."
cd backend
"$VENV_PY" manage.py migrate --noinput
"$VENV_PY" manage.py collectstatic --noinput
cd "$ROOT"

# Restart ONLY Digital Lottery (never carlottery-*)
sudo systemctl restart digitallottery-gunicorn
sudo systemctl restart digitallottery-telegram-bot || true

echo "Fix media permissions..."
mkdir -p "$ROOT/backend/media/lottery/cars" "$ROOT/backend/media/lottery/receipts"
chmod -R a+rX "$ROOT/backend/media" || true
echo "Done. Hard-refresh admin (Ctrl+Shift+R) and reopen the Telegram mini-app."
echo "If media still 403: install nginx/nginx.conf as sites-available/digitallottery, then:"
echo "  sudo nginx -t && sudo systemctl reload nginx"
