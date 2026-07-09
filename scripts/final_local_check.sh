#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Backend tests =="
cd backend
pytest -q

echo "== Benchmark audit =="
PYTHONPATH=. python tools/run_phase20_benchmark_audit.py

echo "== Chrono validation harness =="
PYTHONPATH=. python tools/chrono_validation/run_all_validations.py --strict

echo "== Release candidate audit =="
PYTHONPATH=. python tools/run_release_candidate_audit.py

cd ..

echo "== Frontend build check =="
if ./scripts/check_frontend_build.sh; then
  echo "Frontend build passed."
else
  code=$?
  if [ "$code" = "2" ]; then
    echo "Frontend build check skipped because dependencies are not installed."
    echo "Run: cd frontend && npm install && npm run build"
  else
    exit "$code"
  fi
fi
