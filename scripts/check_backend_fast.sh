#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}"
TIMEOUT_SECONDS="${DYNATUTOR_BACKEND_FAST_TIMEOUT:-420}"
SHARD_COUNT="${DYNATUTOR_BACKEND_FAST_SHARDS:-4}"
FAST_MARKER_EXPRESSION="not benchmark and not audit and not frontend and not slow"

if ! [[ "$SHARD_COUNT" =~ ^[1-9][0-9]*$ ]]; then
  echo "[backend_fast] DYNATUTOR_BACKEND_FAST_SHARDS must be a positive integer" >&2
  exit 1
fi

echo "[backend_fast] discover fast-only test nodes"
if ! COLLECTION_OUTPUT="$(
  DYNATUTOR_RUN_CWD="$ROOT_DIR/backend" python scripts/run_with_timeout.py "$TIMEOUT_SECONDS" -- \
    pytest -qq --disable-warnings --collect-only -o addopts='' -m "$FAST_MARKER_EXPRESSION"
)"; then
  printf '%s\n' "$COLLECTION_OUTPUT"
  echo "[backend_fast] fast-only collection failed" >&2
  exit 1
fi
printf '%s\n' "$COLLECTION_OUTPUT"

mapfile -t NODE_IDS < <(printf '%s\n' "$COLLECTION_OUTPUT" | awk '/::/ { print }')
if (( ${#NODE_IDS[@]} == 0 )); then
  echo "[backend_fast] collection produced no fast-only test nodes" >&2
  exit 1
fi

if (( SHARD_COUNT > ${#NODE_IDS[@]} )); then
  SHARD_COUNT=${#NODE_IDS[@]}
fi

echo "[backend_fast] collected ${#NODE_IDS[@]} tests across $SHARD_COUNT contiguous shards"
for (( shard_index = 0; shard_index < SHARD_COUNT; shard_index++ )); do
  start_index=$(( shard_index * ${#NODE_IDS[@]} / SHARD_COUNT ))
  end_index=$(( (shard_index + 1) * ${#NODE_IDS[@]} / SHARD_COUNT ))
  shard_count=$(( end_index - start_index ))
  echo "[backend_fast] pytest fast-only shard $((shard_index + 1))/$SHARD_COUNT: $shard_count tests"
  DYNATUTOR_RUN_CWD="$ROOT_DIR/backend" python scripts/run_with_timeout.py "$TIMEOUT_SECONDS" -- \
    pytest -q -o addopts='' "${NODE_IDS[@]:start_index:shard_count}"
done
