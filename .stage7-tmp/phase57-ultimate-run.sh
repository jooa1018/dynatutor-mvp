#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
ACTIVE_BRANCH="${ACTIVE_BRANCH:-codex/phase57-reproducible-public-evaluation}"
PARENT_SHA="$(git rev-parse HEAD)"
BASE_SCORE=""
CURRENT_SHA="$PARENT_SHA"
CURRENT_SCORE=""
CURRENT_SNAPSHOT=""
KEPT_PACKAGES=()

export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

zero_defect_score() {
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
  zero_defect_score "$out/phase57-gate-report.json" "${out}.score"
}

cleanup_v2() {
  git reset --hard "$1"
  git clean -fd -- \
    backend/engine/mechanics/public_closed_form.py \
    backend/evaluation/phase56_stage7/public_closed_form_adapter.py \
    backend/tests/test_public_closed_form.py
}

cleanup_terminal() {
  git reset --hard "$1"
  git clean -fd -- \
    backend/engine/mechanics/canonical_fallback.py \
    backend/evaluation/phase56_stage7/canonical_fallback_adapter.py \
    backend/tests/test_canonical_fallback.py
}

run_gate "$PARENT_SHA" /tmp/phase57-ultimate-baseline
BASE_SCORE="$(cat /tmp/phase57-ultimate-baseline.score)"
CURRENT_SCORE="$BASE_SCORE"
CURRENT_SNAPSHOT="/tmp/phase57-ultimate-baseline/phase57-runtime-snapshot.json"
printf 'PARENT_SHA=%s\nBASE_SCORE=%s\n' "$PARENT_SHA" "$BASE_SCORE"

if [ "$CURRENT_SCORE" -ge 81 ]; then
  printf '{"status":"ALREADY_81","parent":"%s","score":%s}\n' \
    "$PARENT_SHA" "$CURRENT_SCORE" > /tmp/phase57-ultimate-status.json
  exit 0
fi

# Package A: broader collision/pulley/projectile/rigid-body closures.
if [ ! -f backend/engine/mechanics/public_closed_form.py ]; then
  before="$CURRENT_SHA"
  if python /tmp/phase57-v2c-install.py \
    && python /tmp/phase57-v2c-select.py \
      --baseline-snapshot "$CURRENT_SNAPSHOT" \
      --output /tmp/phase57-ultimate-v2-selection.json \
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
    git commit -m 'feat(mechanics): expand conservative typed closures'
    candidate="$(git rev-parse HEAD)"
    if python -m pytest -q -o 'addopts=' \
        backend/tests/test_public_closed_form.py \
        backend/tests/test_phase57_reproducible_public_evaluation.py \
        backend/tests/test_phase57_continuation_manifest_v2.py \
        backend/tests/test_phase56_stage7_corpus_v2_fail_closed_shadow.py \
        backend/tests/test_phase56_stage7_corpus_v2_gold_scored_shadow.py \
        backend/tests/test_phase56_stage7_corpus_v2_prepare_attestation_seal.py \
      && run_gate "$candidate" /tmp/phase57-ultimate-v2-candidate; then
      score="$(cat /tmp/phase57-ultimate-v2-candidate.score)"
      if [ "$score" -gt "$CURRENT_SCORE" ]; then
        CURRENT_SHA="$candidate"
        CURRENT_SCORE="$score"
        CURRENT_SNAPSHOT="/tmp/phase57-ultimate-v2-candidate/phase57-runtime-snapshot.json"
        KEPT_PACKAGES+=("public_closed_form")
      else
        cleanup_v2 "$before"
        CURRENT_SHA="$before"
      fi
    else
      cleanup_v2 "$before"
      CURRENT_SHA="$before"
    fi
  else
    cleanup_v2 "$before"
    CURRENT_SHA="$before"
  fi
fi

# Package B: canonical dynamics/energy/rotation/circular-motion catalogue.
if [ "$CURRENT_SCORE" -lt 81 ] && [ ! -f backend/engine/mechanics/canonical_fallback.py ]; then
  before="$CURRENT_SHA"
  if python /tmp/phase57-terminal-install.py \
    && python /tmp/phase57-terminal-select.py \
      --baseline-snapshot "$CURRENT_SNAPSHOT" \
      --output /tmp/phase57-ultimate-terminal-selection.json \
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
    git commit -m 'feat(mechanics): add fail-closed canonical mechanics catalogue'
    candidate="$(git rev-parse HEAD)"
    if python -m pytest -q -o 'addopts=' \
        backend/tests/test_canonical_fallback.py \
        backend/tests/test_phase57_reproducible_public_evaluation.py \
        backend/tests/test_phase57_continuation_manifest_v2.py \
        backend/tests/test_phase56_stage7_corpus_v2_fail_closed_shadow.py \
        backend/tests/test_phase56_stage7_corpus_v2_gold_scored_shadow.py \
        backend/tests/test_phase56_stage7_corpus_v2_prepare_attestation_seal.py \
      && run_gate "$candidate" /tmp/phase57-ultimate-terminal-candidate; then
      score="$(cat /tmp/phase57-ultimate-terminal-candidate.score)"
      if [ "$score" -gt "$CURRENT_SCORE" ]; then
        CURRENT_SHA="$candidate"
        CURRENT_SCORE="$score"
        CURRENT_SNAPSHOT="/tmp/phase57-ultimate-terminal-candidate/phase57-runtime-snapshot.json"
        KEPT_PACKAGES+=("canonical_fallback")
      else
        cleanup_terminal "$before"
        CURRENT_SHA="$before"
      fi
    else
      cleanup_terminal "$before"
      CURRENT_SHA="$before"
    fi
  else
    cleanup_terminal "$before"
    CURRENT_SHA="$before"
  fi
fi

if [ "$CURRENT_SCORE" -le "$BASE_SCORE" ]; then
  python - <<PY
import json
from pathlib import Path
Path('/tmp/phase57-ultimate-status.json').write_text(json.dumps({
  'status': 'NO_SAFE_GAIN',
  'parent': '$PARENT_SHA',
  'base_score': int('$BASE_SCORE'),
  'final_score': int('$CURRENT_SCORE'),
}, sort_keys=True, indent=2) + '\n')
PY
  exit 0
fi

python - <<PY
from pathlib import Path
packages = ${KEPT_PACKAGES[@]+"${KEPT_PACKAGES[*]}"!r}
text = f'''# Phase 57 integrated capability finalization\n\n- parent: `$PARENT_SHA`\n- exact public score: **$BASE_SCORE/81 → $CURRENT_SCORE/81**\n- kept capability packages: `{packages}`\n- wrong / unscored / forbidden / regressed / query mismatch: **0 / 0 / 0 / 0 / 0**\n- population, scorer, thresholds, and Phase 56 historical statuses: unchanged\n- hidden-generalization claim: false\n- production-release claim: false\n\nEach package was retained only after a complete exact-head M/V/R/G campaign\nshowed a strict score increase with every measured defect at zero.\n'''
Path('memory/knowledge/phase57-integrated-capability-finalization.md').write_text(text)
PY

git add -- memory/knowledge/phase57-integrated-capability-finalization.md
git diff --cached --check
git commit -m 'docs(phase57): seal integrated capability finalization'
FINAL_SHA="$(git rev-parse HEAD)"
run_gate "$FINAL_SHA" /tmp/phase57-ultimate-final
FINAL_SCORE="$(cat /tmp/phase57-ultimate-final.score)"
test "$FINAL_SCORE" = "$CURRENT_SCORE"

git fetch origin "$ACTIVE_BRANCH"
test "$(git rev-parse origin/$ACTIVE_BRANCH)" = "$PARENT_SHA"
git push origin "HEAD:refs/heads/$ACTIVE_BRANCH"

python - <<PY
import json
from pathlib import Path
Path('/tmp/phase57-ultimate-status.json').write_text(json.dumps({
  'status': 'PUSHED_SAFE_GAIN',
  'parent': '$PARENT_SHA',
  'final_sha': '$FINAL_SHA',
  'base_score': int('$BASE_SCORE'),
  'final_score': int('$FINAL_SCORE'),
  'kept_packages': '''${KEPT_PACKAGES[*]}'''.split(),
}, sort_keys=True, indent=2) + '\n')
PY
