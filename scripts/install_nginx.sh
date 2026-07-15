#!/usr/bin/env bash
# Install nginx site config for markosgo.online (media via gunicorn proxy).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/nginx/nginx.conf"
DEST=/etc/nginx/sites-available/carlottery

if [ ! -f "$SRC" ]; then
  echo "Missing $SRC"
  exit 1
fi

# Sanity: live cert must exist
if [ ! -f /etc/letsencrypt/live/markosgo.online/fullchain.pem ]; then
  echo "ERROR: certificate not found at /etc/letsencrypt/live/markosgo.online/"
  echo "List what you have:"
  sudo ls -la /etc/letsencrypt/live/ || true
  exit 1
fi

sudo cp "$SRC" "$DEST"
sudo ln -sf "$DEST" /etc/nginx/sites-enabled/carlottery
sudo nginx -t
sudo systemctl reload nginx
echo "Nginx reloaded with markosgo.online + /media/ → gunicorn"
