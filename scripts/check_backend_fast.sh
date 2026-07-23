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

SHARD_FILES=()
SHARD_FILE_COUNTS=()
SELECTED_TEST_COUNT=0
while IFS= read -r collection_line; do
  case "$collection_line" in
    ""|"[run_with_timeout] "*)
      continue
      ;;
  esac

  if [[ ! "$collection_line" =~ ^(.+\.py):[[:space:]]+([1-9][0-9]*)$ ]]; then
    echo "[backend_fast] unexpected collection output: $collection_line" >&2
    exit 1
  fi

  shard_file="${BASH_REMATCH[1]}"
  shard_test_count="${BASH_REMATCH[2]}"
  if [[ ! -f "$ROOT_DIR/backend/$shard_file" ]]; then
    echo "[backend_fast] collected shard does not exist: $shard_file" >&2
    exit 1
  fi
  SHARD_FILES+=("$shard_file")
  SHARD_FILE_COUNTS+=("$shard_test_count")
  SELECTED_TEST_COUNT=$(( SELECTED_TEST_COUNT + shard_test_count ))
done <<< "$COLLECTION_OUTPUT"

if (( ${#SHARD_FILES[@]} == 0 || SELECTED_TEST_COUNT == 0 )); then
  echo "[backend_fast] collection produced no fast-only test files" >&2
  exit 1
fi

if (( SHARD_COUNT > ${#SHARD_FILES[@]} )); then
  SHARD_COUNT=${#SHARD_FILES[@]}
fi

echo "[backend_fast] collected $SELECTED_TEST_COUNT tests across $SHARD_COUNT contiguous shards"
current_shard=1
completed_count=0
current_target=$(( current_shard * SELECTED_TEST_COUNT / SHARD_COUNT - completed_count ))
current_count=0
current_files=()
for (( file_index = 0; file_index < ${#SHARD_FILES[@]}; file_index++ )); do
  current_files+=("${SHARD_FILES[file_index]}")
  current_count=$(( current_count + SHARD_FILE_COUNTS[file_index] ))

  if (( current_shard < SHARD_COUNT && current_count >= current_target )); then
    echo "[backend_fast] pytest fast-only shard $current_shard/$SHARD_COUNT: $current_count tests"
    DYNATUTOR_RUN_CWD="$ROOT_DIR/backend" python scripts/run_with_timeout.py "$TIMEOUT_SECONDS" -- \
      pytest -q -o addopts='' -m "$FAST_MARKER_EXPRESSION" "${current_files[@]}"
    completed_count=$(( completed_count + current_count ))
    current_shard=$(( current_shard + 1 ))
    current_target=$(( current_shard * SELECTED_TEST_COUNT / SHARD_COUNT - completed_count ))
    current_count=0
    current_files=()
  fi
done

echo "[backend_fast] pytest fast-only shard $current_shard/$SHARD_COUNT: $current_count tests"
DYNATUTOR_RUN_CWD="$ROOT_DIR/backend" python scripts/run_with_timeout.py "$TIMEOUT_SECONDS" -- \
  pytest -q -o addopts='' -m "$FAST_MARKER_EXPRESSION" "${current_files[@]}"
