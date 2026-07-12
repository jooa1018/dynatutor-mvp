#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

WITH_BENCHMARK=0
WITH_AUDIT=0
WITH_FRONTEND_BUILD=0

for arg in "$@"; do
  case "$arg" in
    --with-benchmark)
      WITH_BENCHMARK=1
      ;;
    --with-audit)
      WITH_AUDIT=1
      ;;
    --with-frontend-build)
      WITH_FRONTEND_BUILD=1
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Usage: ./scripts/check_all.sh [--with-benchmark] [--with-audit] [--with-frontend-build]"
      exit 2
      ;;
  esac
done

echo "[check_all] frontend metadata"
bash ./scripts/check_frontend_metadata.sh

echo "[check_all] backend fast"
bash ./scripts/check_backend_fast.sh

if [ "$WITH_BENCHMARK" = "1" ]; then
  echo "[check_all] backend benchmark (optional convenience check; official validation also supports running this script separately)"
  bash ./scripts/check_backend_benchmark.sh
fi

if [ "$WITH_AUDIT" = "1" ]; then
  echo "[check_all] backend audit (optional convenience check; official validation also supports running this script separately)"
  bash ./scripts/check_backend_audit.sh
fi

if [ "$WITH_FRONTEND_BUILD" = "1" ]; then
  echo "[check_all] frontend build"
  bash ./scripts/check_frontend_build.sh
fi

echo "[check_all] completed"
