#!/usr/bin/env bash
# Install nginx site config for Digital Lottery (port 8001).
# Does NOT replace the carlottery / markosgo.online site.
#
# Usage:
#   1) Edit nginx/nginx.conf — replace YOUR_DOMAIN with your real domain
#   2) Get a cert: sudo certbot certonly --nginx -d your.domain.com
#   3) bash scripts/install_nginx.sh your.domain.com
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/nginx/nginx.conf"
DEST=/etc/nginx/sites-available/digitallottery
DOMAIN="${1:-}"

if [ -z "$DOMAIN" ]; then
  echo "Usage: bash scripts/install_nginx.sh your.domain.com"
  echo "Also ensure nginx/nginx.conf has YOUR_DOMAIN replaced with that domain."
  exit 1
fi

if [ ! -f "$SRC" ]; then
  echo "Missing $SRC"
  exit 1
fi

CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

# live/ is root-only — must use sudo to probe cert files
if ! sudo test -f "$CERT_DIR/fullchain.pem" || ! sudo test -f "$CERT_DIR/privkey.pem"; then
  echo "ERROR: certificate files missing under $CERT_DIR"
  echo "Run: sudo certbot certonly --nginx -d $DOMAIN"
  sudo ls -la /etc/letsencrypt/live/ || true
  exit 1
fi

# Substitute YOUR_DOMAIN in a temp copy so the repo template stays generic
TMP="$(mktemp)"
sed "s/YOUR_DOMAIN/$DOMAIN/g" "$SRC" > "$TMP"

sudo cp "$TMP" "$DEST"
rm -f "$TMP"
sudo ln -sf "$DEST" /etc/nginx/sites-enabled/digitallottery
# Do NOT remove carlottery site
sudo nginx -t
sudo systemctl reload nginx
echo "Nginx reloaded: $DOMAIN → 127.0.0.1:8001 (DigitalLottery)"
echo "CarLottery site left unchanged."
