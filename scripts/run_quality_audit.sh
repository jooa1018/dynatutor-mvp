#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
python tools_run_korean_quality_audit.py
pytest -q tests/test_phase10_korean_quality_benchmark.py
