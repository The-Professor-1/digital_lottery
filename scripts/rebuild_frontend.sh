#!/usr/bin/env bash
# Compatibility wrapper: deployment now uses the frontend pre-built on the dev
# machine and committed to backend/frontend_dist. No node/npm on the server.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$ROOT/scripts/deploy.sh"
