#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}"
TIMEOUT_SECONDS="${DYNATUTOR_BACKEND_FAST_TIMEOUT:-420}"
echo "[backend_fast] pytest fast tests"
DYNATUTOR_RUN_CWD="$ROOT_DIR/backend" python scripts/run_with_timeout.py "$TIMEOUT_SECONDS" -- \
  pytest -q -o addopts='' -m "not benchmark and not audit and not frontend and not slow"
