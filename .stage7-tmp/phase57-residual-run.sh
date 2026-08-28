#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
ACTIVE_BRANCH="${ACTIVE_BRANCH:-codex/phase57-reproducible-public-evaluation}"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

PARENT_SHA="$(git rev-parse HEAD)"
BASE_SCORE=""
CURRENT_SCORE=""
CURRENT_SNAPSHOT=""
KEPT_PACKAGES=()

score_report() {
  local report="$1"
  local output="$2"
  python - "$report" "$output" <<'PY'
import json, sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text())
assert report['regression_acceptance'] == 'PASS', report
for key in (
    'all_shadow_wrong','all_shadow_unscored','newly_solved_wrong',
    'newly_solved_unscored','forbidden_class_solve','regressed',
    'query_binding_mismatch'):
    assert report[key] == 0, (key, report[key])
Path(sys.argv[2]).write_text(str(int(report['all_shadow_correct'])))
PY
}

run_gate() {
  local sha="$1"
  local out="$2"
  rm -rf "$out"
  python backend/tools/run_phase57_reproducible_public_gate.py \
    --output-dir "$out" \
    --exact-code-head "$sha" \
    --runtime-timeout-seconds 2400 \
    >"${out}.log" 2>&1
  score_report "$out/phase57-gate-report.json" "${out}.score"
}

write_status() {
  local disposition="$1"
  local final_sha="$2"
  local final_score="$3"
  export RESIDUAL_DISPOSITION="$disposition" RESIDUAL_FINAL_SHA="$final_sha"
  export RESIDUAL_FINAL_SCORE="$final_score" PARENT_SHA BASE_SCORE
  export KEPT_PACKAGES_TEXT="${KEPT_PACKAGES[*]}"
  python - <<'PY'
import json, os
from pathlib import Path
payload = {
    'schema': 'dynatutor.phase57.residual-binding-finalizer.v1',
    'status': os.environ['RESIDUAL_DISPOSITION'],
    'parent': os.environ['PARENT_SHA'],
    'final_sha': os.environ['RESIDUAL_FINAL_SHA'],
    'base_score': int(os.environ['BASE_SCORE']),
    'final_score': int(os.environ['RESIDUAL_FINAL_SCORE']),
    'kept_packages': os.environ.get('KEPT_PACKAGES_TEXT', '').split(),
}
Path('/tmp/phase57-residual-status.json').write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
    encoding='utf-8',
)
PY
}

run_gate "$PARENT_SHA" /tmp/phase57-residual-baseline
BASE_SCORE="$(cat /tmp/phase57-residual-baseline.score)"
CURRENT_SCORE="$BASE_SCORE"
CURRENT_SNAPSHOT="/tmp/phase57-residual-baseline/phase57-runtime-snapshot.json"
printf 'PARENT_SHA=%s\nBASE_SCORE=%s\n' "$PARENT_SHA" "$BASE_SCORE"

if [ "$BASE_SCORE" -ge 81 ]; then
  write_status ALREADY_81 "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi

git config user.name 'Codex'
git config user.email 'codex@openai.com'

# Reconstitute the broader public-safe package only when it is not already active.
if [ ! -f backend/engine/mechanics/public_closed_form.py ]; then
  before="$(git rev-parse HEAD)"
  if python /tmp/phase57-v2c-install.py \
    && python /tmp/phase57-v2c-select.py \
      --baseline-snapshot "$CURRENT_SNAPSHOT" \
      --output /tmp/phase57-residual-v2-selection.json \
    && python -m compileall -q \
      backend/engine/mechanics/public_closed_form.py \
      backend/evaluation/phase56_stage7/public_closed_form_adapter.py \
      backend/tools/run_phase56_stage7_v2_shadow_runtime.py \
      backend/tests/test_public_closed_form.py; then
    git add -- \
      backend/engine/mechanics/public_closed_form.py \
      backend/evaluation/phase56_stage7/public_closed_form_adapter.py \
      backend/tools/run_phase56_stage7_v2_shadow_runtime.py \
      backend/tests/test_public_closed_form.py
    git diff --cached --check
    git commit -m 'feat(mechanics): restore public-safe typed closures for binding repair'
    KEPT_PACKAGES+=("public_closed_form")
  else
    git reset --hard "$before"
    git clean -fd -- \
      backend/engine/mechanics/public_closed_form.py \
      backend/evaluation/phase56_stage7/public_closed_form_adapter.py \
      backend/tests/test_public_closed_form.py
  fi
fi

# Add the broader canonical catalogue only when absent.
if [ ! -f backend/engine/mechanics/canonical_fallback.py ]; then
  before="$(git rev-parse HEAD)"
  if python /tmp/phase57-terminal-install.py \
    && python /tmp/phase57-terminal-select.py \
      --baseline-snapshot "$CURRENT_SNAPSHOT" \
      --output /tmp/phase57-residual-terminal-selection.json \
    && python -m compileall -q \
      backend/engine/mechanics/canonical_fallback.py \
      backend/evaluation/phase56_stage7/canonical_fallback_adapter.py \
      backend/tools/run_phase56_stage7_v2_shadow_runtime.py \
      backend/tests/test_canonical_fallback.py; then
    git add -- \
      backend/engine/mechanics/canonical_fallback.py \
      backend/evaluation/phase56_stage7/canonical_fallback_adapter.py \
      backend/tools/run_phase56_stage7_v2_shadow_runtime.py \
      backend/tests/test_canonical_fallback.py
    git diff --cached --check
    git commit -m 'feat(mechanics): restore canonical catalogue for binding repair'
    KEPT_PACKAGES+=("canonical_fallback")
  else
    git reset --hard "$before"
    git clean -fd -- \
      backend/engine/mechanics/canonical_fallback.py \
      backend/evaluation/phase56_stage7/canonical_fallback_adapter.py \
      backend/tests/test_canonical_fallback.py
  fi
fi

# Apply one shared, attributable query-symbol binding to every available fallback.
python /tmp/phase57-residual-binding-install.py
python -m compileall -q \
  backend/evaluation/phase56_stage7/query_binding.py \
  backend/tests/test_phase57_query_binding.py

paths=(
  backend/evaluation/phase56_stage7/query_binding.py
  backend/tests/test_phase57_query_binding.py
)
for path in \
  backend/evaluation/phase56_stage7/typed_closed_form_adapter.py \
  backend/evaluation/phase56_stage7/public_closed_form_adapter.py \
  backend/evaluation/phase56_stage7/canonical_fallback_adapter.py; do
  if [ -f "$path" ]; then
    paths+=("$path")
  fi
done
git add -- "${paths[@]}"
git diff --cached --check
if ! git diff --cached --quiet; then
  git commit -m 'fix(mechanics): bind fallback solutions to the typed query unknown'
fi
CANDIDATE_SHA="$(git rev-parse HEAD)"

# No case-specific test or source is admitted here; run only contracts and full gate.
tests=(
  backend/tests/test_phase57_query_binding.py
  backend/tests/test_phase57_reproducible_public_evaluation.py
  backend/tests/test_phase57_continuation_manifest_v2.py
  backend/tests/test_phase56_stage7_supplemental_manifest.py
  backend/tests/test_phase56_stage7_corpus_v2_fail_closed_shadow.py
  backend/tests/test_phase56_stage7_corpus_v2_gold_scored_shadow.py
  backend/tests/test_phase56_stage7_corpus_v2_prepare_attestation_seal.py
)
for test in \
  backend/tests/test_typed_closed_form.py \
  backend/tests/test_public_closed_form.py \
  backend/tests/test_canonical_fallback.py; do
  if [ -f "$test" ]; then
    tests+=("$test")
  fi
done
python -m pytest -q -o 'addopts=' "${tests[@]}"

if ! run_gate "$CANDIDATE_SHA" /tmp/phase57-residual-candidate; then
  git reset --hard "$PARENT_SHA"
  write_status CANDIDATE_GATE_FAILED "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi
CANDIDATE_SCORE="$(cat /tmp/phase57-residual-candidate.score)"
if [ "$CANDIDATE_SCORE" -le "$BASE_SCORE" ]; then
  git reset --hard "$PARENT_SHA"
  write_status NO_SAFE_BINDING_GAIN "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi

export CANDIDATE_SCORE KEPT_PACKAGES_TEXT="${KEPT_PACKAGES[*]}"
python - <<'PY'
import os
from pathlib import Path
text = f"""# Phase 57 residual query-binding closure

- parent: `{os.environ['PARENT_SHA']}`
- exact public score: **{os.environ['BASE_SCORE']}/81 → {os.environ['CANDIDATE_SCORE']}/81**
- wrong / unscored / forbidden / regressed / query mismatch: **0 / 0 / 0 / 0 / 0**
- query binding: one exact typed unknown symbol or fail closed
- supporting packages: `{os.environ.get('KEPT_PACKAGES_TEXT', '')}`
- population, scorer, thresholds, and Phase 56 historical statuses: unchanged
- hidden-generalization claim: false
- production-release claim: false

The binding module never fabricates a symbol and never reads evaluation identity
or gold.  The candidate was retained only after a complete exact-head M/V/R/G
campaign produced a strict score gain with every measured defect at zero.
"""
Path('memory/knowledge/phase57-residual-query-binding.md').write_text(
    text, encoding='utf-8'
)
PY
git add -- memory/knowledge/phase57-residual-query-binding.md
git diff --cached --check
git commit -m 'docs(phase57): seal residual query-binding evidence'
FINAL_SHA="$(git rev-parse HEAD)"
run_gate "$FINAL_SHA" /tmp/phase57-residual-final
FINAL_SCORE="$(cat /tmp/phase57-residual-final.score)"
test "$FINAL_SCORE" = "$CANDIDATE_SCORE"

git fetch origin "$ACTIVE_BRANCH"
test "$(git rev-parse origin/$ACTIVE_BRANCH)" = "$PARENT_SHA"
git push origin "HEAD:refs/heads/$ACTIVE_BRANCH"
write_status PUSHED_SAFE_BINDING_GAIN "$FINAL_SHA" "$FINAL_SCORE"
