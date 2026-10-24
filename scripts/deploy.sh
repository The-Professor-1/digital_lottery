#!/usr/bin/env bash
# Server-side deploy (no containers, no node/npm): pull code, install Python
# deps, migrate SQLite, collect static, restart DigitalLottery services.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  echo "Creating Python venv at $ROOT/venv ..."
  python3 -m venv "$ROOT/venv"
  VENV_PY="$ROOT/venv/bin/python"
fi

if git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Pulling latest code..."
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  git pull --ff-only origin "$BRANCH" || true
  git log -1 --oneline
fi

echo "Installing Python deps..."
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$VENV_PY" -r requirements.txt
else
  "$VENV_PY" -m pip install -r requirements.txt
fi

if [ ! -f backend/frontend_dist/index.html ]; then
  echo "ERROR: backend/frontend_dist/index.html missing."
  echo "Build the frontend locally (scripts/build_frontend.sh) and commit it."
  exit 1
fi

echo "Running migrations (SQLite)..."
cd backend
"$VENV_PY" manage.py migrate --noinput
"$VENV_PY" manage.py collectstatic --noinput
cd "$ROOT"

echo "Fix media/cache permissions..."
mkdir -p "$ROOT/backend/media/lottery/cars" "$ROOT/backend/media/lottery/receipts" "$ROOT/backend/media/lottery/items" "$ROOT/backend/media/lottery/prizes" "$ROOT/backend/cache"
chmod -R a+rX "$ROOT/backend/media" || true
chmod -R u+rwX "$ROOT/backend/cache" || true

if command -v systemctl >/dev/null 2>&1; then
  if ! sudo -n true >/dev/null 2>&1; then
    echo "ERROR: passwordless sudo is required to install/restart the services."
    echo "Add a sudoers rule for the deploy user (see DEPLOY.md)."
    exit 1
  fi

  if ! systemctl cat digitallottery-gunicorn.service >/dev/null 2>&1; then
    echo "First run: installing systemd units for $(id -un)..."
    TMP_UNITS="$(mktemp -d)"
    for unit in digitallottery-gunicorn.service digitallottery-telegram-bot.service; do
      sed -e "s/^User=.*/User=$(id -un)/" \
          -e "s/^Group=.*/Group=$(id -gn)/" \
          "systemd/$unit" > "$TMP_UNITS/$unit"
    done
    sudo -n cp "$TMP_UNITS"/*.service /etc/systemd/system/
    rm -rf "$TMP_UNITS"
    sudo -n systemctl daemon-reload
    sudo -n systemctl enable digitallottery-gunicorn digitallottery-telegram-bot
  fi

  echo "Restarting services..."
  sudo -n systemctl daemon-reload || true
  sudo -n systemctl restart digitallottery-gunicorn
  sudo -n systemctl restart digitallottery-telegram-bot || true
else
  echo "systemd is not available - restart the app manually."
fi

echo "Done. Hard-refresh admin (Ctrl+Shift+R) and reopen the Telegram mini-app."
