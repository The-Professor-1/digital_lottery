#!/usr/bin/env bash
# Install nginx site config for markosgo.online (media via gunicorn proxy).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/nginx/nginx.conf"
DEST=/etc/nginx/sites-available/carlottery
CERT_DIR=/etc/letsencrypt/live/markosgo.online

if [ ! -f "$SRC" ]; then
  echo "Missing $SRC"
  exit 1
fi

# live/ is root-only — must use sudo to probe cert files
if ! sudo test -f "$CERT_DIR/fullchain.pem" || ! sudo test -f "$CERT_DIR/privkey.pem"; then
  echo "ERROR: certificate files missing under $CERT_DIR"
  echo "List what you have:"
  sudo ls -la /etc/letsencrypt/live/ || true
  sudo ls -la "$CERT_DIR" 2>/dev/null || true
  exit 1
fi

sudo cp "$SRC" "$DEST"
sudo ln -sf "$DEST" /etc/nginx/sites-enabled/carlottery
# Drop broken default site if it conflicts
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
echo "Nginx reloaded with markosgo.online + /media/ → gunicorn"
