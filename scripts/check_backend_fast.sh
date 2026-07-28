#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}"
TIMEOUT_SECONDS="${DYNATUTOR_BACKEND_FAST_TIMEOUT:-420}"
SHARD_COUNT="${DYNATUTOR_BACKEND_FAST_SHARD_COUNT:-4}"
SHARD_INDEX="${DYNATUTOR_BACKEND_FAST_SHARD_INDEX:-}"
FAST_MARKER_EXPRESSION="not benchmark and not audit and not frontend and not slow"
EXCLUDE_GLOB="${DYNATUTOR_BACKEND_FAST_EXCLUDE_GLOB:-}"
VERIFY_ONLY="${DYNATUTOR_BACKEND_FAST_VERIFY_ONLY:-0}"
MANIFEST_OUTPUT="${DYNATUTOR_BACKEND_FAST_MANIFEST_OUTPUT:-$ROOT_DIR/backend-fast-shard-manifest.json}"
FAILURE_SUMMARY_BASE="${DYNATUTOR_BACKEND_FAST_FAILURE_SUMMARY:-$ROOT_DIR/backend-fast-failure-summary.txt}"

if ! [[ "$SHARD_COUNT" =~ ^[1-9][0-9]*$ ]]; then
  echo "[backend_fast] DYNATUTOR_BACKEND_FAST_SHARD_COUNT must be a positive integer" >&2
  exit 1
fi
if [[ -n "$SHARD_INDEX" ]] && ! [[ "$SHARD_INDEX" =~ ^[0-9]+$ ]]; then
  echo "[backend_fast] DYNATUTOR_BACKEND_FAST_SHARD_INDEX must be a non-negative integer" >&2
  exit 1
fi

run_shard() {
  local index="$1"
  local failure_summary="$FAILURE_SUMMARY_BASE"
  if [[ -z "${DYNATUTOR_BACKEND_FAST_FAILURE_SUMMARY:-}" && -z "$SHARD_INDEX" ]]; then
    failure_summary="$ROOT_DIR/backend-fast-failure-summary-shard-${index}.txt"
  fi
  local args=(
    python backend/scripts/pytest_file_shards.py
    --marker "$FAST_MARKER_EXPRESSION"
    --shard-count "$SHARD_COUNT"
    --shard-index "$index"
    --timeout-seconds "$TIMEOUT_SECONDS"
    --manifest-output "$MANIFEST_OUTPUT"
    --failure-summary "$failure_summary"
  )
  if [[ -n "$EXCLUDE_GLOB" ]]; then
    args+=(--exclude-glob "$EXCLUDE_GLOB")
  fi
  if [[ "$VERIFY_ONLY" == "1" ]]; then
    args+=(--verify-only)
  fi
  "${args[@]}"
}

if [[ -n "$SHARD_INDEX" ]]; then
  run_shard "$SHARD_INDEX"
else
  for (( index = 0; index < SHARD_COUNT; index++ )); do
    run_shard "$index"
  done
fi
