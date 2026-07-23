#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Backend fast =="
./scripts/check_backend_fast.sh

echo "== Backend slow-only =="
./scripts/check_backend_slow.sh

echo "== Backend benchmark =="
./scripts/check_backend_benchmark.sh

echo "== Backend audit =="
./scripts/check_backend_audit.sh

echo "== Frontend static build =="
./scripts/check_frontend_build.sh

if [[ "${DYNATUTOR_DEEP_AUDIT:-0}" == "1" ]]; then
  echo "== Optional deep audit =="
  (
    cd backend
    PYTHONPATH=. python tools/run_phase20_benchmark_audit.py
    PYTHONPATH=. python tools/chrono_validation/run_all_validations.py --strict
    PYTHONPATH=. python tools/run_release_candidate_audit.py
  )
else
  echo "== Optional deep audit skipped =="
  echo "Run with DYNATUTOR_DEEP_AUDIT=1 to include benchmark audit, Chrono strict, and release-candidate audit."
fi

echo "All required Phase 41 local checks passed."
