#!/usr/bin/env bash
# Build the Vue app on a dev machine. Output is committed so the server only
# needs Python.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
npm ci
npm run build
