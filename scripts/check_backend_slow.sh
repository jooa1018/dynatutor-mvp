#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}"
TIMEOUT_SECONDS="${DYNATUTOR_BACKEND_SLOW_TIMEOUT:-240}"
SLOW_MARKER_EXPRESSION="slow and not benchmark and not audit and not frontend"

echo "[backend_slow] discover slow-only file shards"
if ! COLLECTION_OUTPUT="$(
  DYNATUTOR_RUN_CWD="$ROOT_DIR/backend" python scripts/run_with_timeout.py "$TIMEOUT_SECONDS" -- \
    pytest -qq --disable-warnings --collect-only -o addopts='' -m "$SLOW_MARKER_EXPRESSION"
)"; then
  printf '%s\n' "$COLLECTION_OUTPUT"
  echo "[backend_slow] slow-only collection failed" >&2
  exit 1
fi
printf '%s\n' "$COLLECTION_OUTPUT"

SHARD_FILES=()
SELECTED_TEST_COUNT=0
while IFS= read -r collection_line; do
  case "$collection_line" in
    ""|"[run_with_timeout] "*)
      continue
      ;;
  esac

  if [[ ! "$collection_line" =~ ^(.+\.py):[[:space:]]+([1-9][0-9]*)$ ]]; then
    echo "[backend_slow] unexpected collection output: $collection_line" >&2
    exit 1
  fi

  shard_file="${BASH_REMATCH[1]}"
  shard_test_count="${BASH_REMATCH[2]}"
  if [[ ! -f "$ROOT_DIR/backend/$shard_file" ]]; then
    echo "[backend_slow] collected shard does not exist: $shard_file" >&2
    exit 1
  fi
  for existing_shard_file in "${SHARD_FILES[@]}"; do
    if [[ "$existing_shard_file" == "$shard_file" ]]; then
      echo "[backend_slow] duplicate collected shard: $shard_file" >&2
      exit 1
    fi
  done

  SHARD_FILES+=("$shard_file")
  SELECTED_TEST_COUNT=$((SELECTED_TEST_COUNT + shard_test_count))
done <<< "$COLLECTION_OUTPUT"

if (( ${#SHARD_FILES[@]} == 0 || SELECTED_TEST_COUNT == 0 )); then
  echo "[backend_slow] collection produced no slow-only tests" >&2
  exit 1
fi

echo "[backend_slow] collected $SELECTED_TEST_COUNT tests across ${#SHARD_FILES[@]} file shards"
for shard_file in "${SHARD_FILES[@]}"; do
  echo "[backend_slow] pytest slow-only shard: $shard_file"
  DYNATUTOR_RUN_CWD="$ROOT_DIR/backend" python scripts/run_with_timeout.py "$TIMEOUT_SECONDS" -- \
    pytest -q -o addopts='' -m "$SLOW_MARKER_EXPRESSION" "$shard_file"
done
