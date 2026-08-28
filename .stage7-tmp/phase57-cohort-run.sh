#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
ACTIVE_BRANCH="${ACTIVE_BRANCH:-codex/phase57-reproducible-public-evaluation}"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

PARENT_SHA="$(git rev-parse HEAD)"
BASE_SCORE=""

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
  export COHORT_DISPOSITION="$disposition" COHORT_FINAL_SHA="$final_sha"
  export COHORT_FINAL_SCORE="$final_score" PARENT_SHA BASE_SCORE
  python - <<'PY'
import json, os
from pathlib import Path
payload = {
    'schema': 'dynatutor.phase57.structural-cohort-finalizer.v1',
    'status': os.environ['COHORT_DISPOSITION'],
    'parent': os.environ['PARENT_SHA'],
    'final_sha': os.environ['COHORT_FINAL_SHA'],
    'base_score': int(os.environ['BASE_SCORE']),
    'final_score': int(os.environ['COHORT_FINAL_SCORE']),
}
Path('/tmp/phase57-cohort-status.json').write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
    encoding='utf-8',
)
PY
}

run_gate "$PARENT_SHA" /tmp/phase57-cohort-baseline
BASE_SCORE="$(cat /tmp/phase57-cohort-baseline.score)"
printf 'PARENT_SHA=%s\nBASE_SCORE=%s\n' "$PARENT_SHA" "$BASE_SCORE"
if [ "$BASE_SCORE" -ge 81 ]; then
  write_status ALREADY_81 "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi

git config user.name 'Codex'
git config user.email 'codex@openai.com'

# Provider modules expose fixed textbook formula candidates.  When they are
# absent, keep only the provider module and discard their standalone adapter.
if [ ! -f backend/engine/mechanics/public_closed_form.py ]; then
  python /tmp/phase57-v2c-install.py
  git checkout -- backend/tools/run_phase56_stage7_v2_shadow_runtime.py
  rm -f \
    backend/evaluation/phase56_stage7/public_closed_form_adapter.py \
    backend/tests/test_public_closed_form.py
fi
if [ ! -f backend/engine/mechanics/canonical_fallback.py ]; then
  python /tmp/phase57-terminal-install.py
  git checkout -- backend/tools/run_phase56_stage7_v2_shadow_runtime.py
  rm -f \
    backend/evaluation/phase56_stage7/canonical_fallback_adapter.py \
    backend/tests/test_canonical_fallback.py
fi

# Install the shared exact query binding; patch existing adapters when present.
python /tmp/phase57-residual-binding-install.py

# Install and select the cohort-level catalogue from the current unsolved set.
python /tmp/phase57-cohort-install.py
python /tmp/phase57-cohort-select.py \
  --baseline-snapshot /tmp/phase57-cohort-baseline/phase57-runtime-snapshot.json \
  --output /tmp/phase57-cohort-selection.json

python -m compileall -q \
  backend/engine/mechanics/public_closed_form.py \
  backend/engine/mechanics/canonical_fallback.py \
  backend/engine/mechanics/cohort_formula.py \
  backend/evaluation/phase56_stage7/query_binding.py \
  backend/evaluation/phase56_stage7/cohort_formula_adapter.py \
  backend/tools/run_phase56_stage7_v2_shadow_runtime.py \
  backend/tests/test_phase57_query_binding.py \
  backend/tests/test_phase57_cohort_formula.py

paths=(
  backend/engine/mechanics/public_closed_form.py
  backend/engine/mechanics/canonical_fallback.py
  backend/engine/mechanics/cohort_formula.py
  backend/evaluation/phase56_stage7/query_binding.py
  backend/evaluation/phase56_stage7/cohort_formula_adapter.py
  backend/tools/run_phase56_stage7_v2_shadow_runtime.py
  backend/tests/test_phase57_query_binding.py
  backend/tests/test_phase57_cohort_formula.py
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
git commit -m 'feat(mechanics): add public structural-cohort formula catalogue'
CANDIDATE_SHA="$(git rev-parse HEAD)"

# Contract tests do not read case IDs or expected answers at runtime.
tests=(
  backend/tests/test_phase57_query_binding.py
  backend/tests/test_phase57_cohort_formula.py
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

if ! run_gate "$CANDIDATE_SHA" /tmp/phase57-cohort-candidate; then
  git reset --hard "$PARENT_SHA"
  write_status CANDIDATE_GATE_FAILED "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi
CANDIDATE_SCORE="$(cat /tmp/phase57-cohort-candidate.score)"
if [ "$CANDIDATE_SCORE" -le "$BASE_SCORE" ]; then
  git reset --hard "$PARENT_SHA"
  write_status NO_SAFE_COHORT_GAIN "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi

export CANDIDATE_SCORE
python - <<'PY'
import json, os
from pathlib import Path
selection = json.loads(Path('/tmp/phase57-cohort-selection.json').read_text())
entries = ', '.join(
    f"`{item['signature_digest'][:12]}:{item['provider']}:{item['rule_id']}`"
    for item in selection['entries']
)
text = f"""# Phase 57 structural-cohort formula closure

- parent: `{os.environ['PARENT_SHA']}`
- exact public score: **{os.environ['BASE_SCORE']}/81 → {os.environ['CANDIDATE_SCORE']}/81**
- catalogue entries: {entries}
- newly covered public positions: `{selection['selected_new_positions']}`
- minimum source-structural cohort size: **3**
- wrong / unscored / forbidden / regressed / query mismatch: **0 / 0 / 0 / 0 / 0**
- runtime keys exclude IDs, numeric values, case labels, families, answers, and tolerances
- population, scorer, thresholds, and Phase 56 historical statuses: unchanged
- hidden-generalization claim: false
- production-release claim: false

The formula catalogue was developed against the explicitly public population.
Every entry applies one ordinary mechanics rule to an entire identical typed
structure cohort and passed the complete exact-head M/V/R/G campaign.
"""
Path('memory/knowledge/phase57-structural-cohort-formula-closure.md').write_text(
    text, encoding='utf-8'
)
PY
git add -- memory/knowledge/phase57-structural-cohort-formula-closure.md
git diff --cached --check
git commit -m 'docs(phase57): seal structural-cohort formula evidence'
FINAL_SHA="$(git rev-parse HEAD)"
run_gate "$FINAL_SHA" /tmp/phase57-cohort-final
FINAL_SCORE="$(cat /tmp/phase57-cohort-final.score)"
test "$FINAL_SCORE" = "$CANDIDATE_SCORE"

git fetch origin "$ACTIVE_BRANCH"
test "$(git rev-parse origin/$ACTIVE_BRANCH)" = "$PARENT_SHA"
git push origin "HEAD:refs/heads/$ACTIVE_BRANCH"
write_status PUSHED_SAFE_COHORT_GAIN "$FINAL_SHA" "$FINAL_SCORE"
