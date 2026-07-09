#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
echo "[frontend_build] npm ci"
cd frontend
npm ci
cd "$ROOT_DIR"
echo "[frontend_build] npm run build with Python timeout wrapper"
exec python scripts/check_frontend_build.py
