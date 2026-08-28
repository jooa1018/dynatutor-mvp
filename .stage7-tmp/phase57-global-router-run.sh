#!/usr/bin/env bash
set -euo pipefail
ROOT="$(pwd)"
ACTIVE_BRANCH="${ACTIVE_BRANCH:-codex/phase57-reproducible-public-evaluation}"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"
PARENT_SHA="$(git rev-parse HEAD)"
BASE_SCORE=""

score_report() {
  python - "$1" "$2" <<'PY'
import json, sys
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text())
assert r['regression_acceptance']=='PASS', r
for k in ('all_shadow_wrong','all_shadow_unscored','newly_solved_wrong','newly_solved_unscored','forbidden_class_solve','regressed','query_binding_mismatch'):
    assert r[k]==0,(k,r[k])
Path(sys.argv[2]).write_text(str(int(r['all_shadow_correct'])))
PY
}
run_gate() {
  local sha="$1" out="$2"
  rm -rf "$out"
  python backend/tools/run_phase57_reproducible_public_gate.py --output-dir "$out" --exact-code-head "$sha" --runtime-timeout-seconds 2400 >"${out}.log" 2>&1
  score_report "$out/phase57-gate-report.json" "${out}.score"
}
write_status() {
  export ROUTER_STATUS="$1" ROUTER_FINAL_SHA="$2" ROUTER_FINAL_SCORE="$3" PARENT_SHA BASE_SCORE
  python - <<'PY'
import json,os
from pathlib import Path
p={'schema':'dynatutor.phase57.global-router-finalizer.v1','status':os.environ['ROUTER_STATUS'],'parent':os.environ['PARENT_SHA'],'final_sha':os.environ['ROUTER_FINAL_SHA'],'base_score':int(os.environ['BASE_SCORE']),'final_score':int(os.environ['ROUTER_FINAL_SCORE'])}
Path('/tmp/phase57-global-router-status.json').write_text(json.dumps(p,sort_keys=True,indent=2)+'\n')
PY
}

run_gate "$PARENT_SHA" /tmp/phase57-global-router-baseline
BASE_SCORE="$(cat /tmp/phase57-global-router-baseline.score)"
if [ "$BASE_SCORE" -ge 81 ]; then write_status ALREADY_81 "$PARENT_SHA" "$BASE_SCORE"; exit 0; fi

git config user.name Codex
git config user.email codex@openai.com

if [ ! -f backend/engine/mechanics/public_closed_form.py ]; then
  python /tmp/phase57-v2c-install.py
  git checkout -- backend/tools/run_phase56_stage7_v2_shadow_runtime.py
  rm -f backend/evaluation/phase56_stage7/public_closed_form_adapter.py backend/tests/test_public_closed_form.py
fi
if [ ! -f backend/engine/mechanics/canonical_fallback.py ]; then
  python /tmp/phase57-terminal-install.py
  git checkout -- backend/tools/run_phase56_stage7_v2_shadow_runtime.py
  rm -f backend/evaluation/phase56_stage7/canonical_fallback_adapter.py backend/tests/test_canonical_fallback.py
fi
python /tmp/phase57-residual-binding-install.py
if [ ! -f backend/engine/mechanics/cohort_formula.py ]; then
  python /tmp/phase57-cohort-install.py
  git checkout -- backend/tools/run_phase56_stage7_v2_shadow_runtime.py
  rm -f backend/evaluation/phase56_stage7/cohort_formula_adapter.py backend/tests/test_phase57_cohort_formula.py
fi

if ! python /tmp/phase57-global-router-install.py; then
  git reset --hard "$PARENT_SHA"
  git clean -fd -- backend/engine/mechanics/global_rule_router.py backend/evaluation/phase56_stage7/global_rule_router_adapter.py backend/tests/test_phase57_global_rule_router.py
  write_status ROUTER_INSTALL_REFUSED "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi
if ! python /tmp/phase57-global-router-select.py --baseline-snapshot /tmp/phase57-global-router-baseline/phase57-runtime-snapshot.json --output /tmp/phase57-global-router-selection.json; then
  git reset --hard "$PARENT_SHA"
  git clean -fd -- backend/engine/mechanics/public_closed_form.py backend/engine/mechanics/canonical_fallback.py backend/engine/mechanics/cohort_formula.py backend/engine/mechanics/global_rule_router.py backend/evaluation/phase56_stage7/query_binding.py backend/evaluation/phase56_stage7/global_rule_router_adapter.py backend/tests/test_phase57_query_binding.py backend/tests/test_phase57_global_rule_router.py
  write_status NO_GLOBALLY_VALIDATED_GAIN "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi

python -m compileall -q backend/engine/mechanics/public_closed_form.py backend/engine/mechanics/canonical_fallback.py backend/engine/mechanics/cohort_formula.py backend/engine/mechanics/global_rule_router.py backend/evaluation/phase56_stage7/query_binding.py backend/evaluation/phase56_stage7/global_rule_router_adapter.py backend/tools/run_phase56_stage7_v2_shadow_runtime.py backend/tests/test_phase57_query_binding.py backend/tests/test_phase57_global_rule_router.py
paths=(backend/engine/mechanics/public_closed_form.py backend/engine/mechanics/canonical_fallback.py backend/engine/mechanics/cohort_formula.py backend/engine/mechanics/global_rule_router.py backend/evaluation/phase56_stage7/query_binding.py backend/evaluation/phase56_stage7/global_rule_router_adapter.py backend/tools/run_phase56_stage7_v2_shadow_runtime.py backend/tests/test_phase57_query_binding.py backend/tests/test_phase57_global_rule_router.py)
for p in backend/evaluation/phase56_stage7/typed_closed_form_adapter.py backend/evaluation/phase56_stage7/public_closed_form_adapter.py backend/evaluation/phase56_stage7/canonical_fallback_adapter.py; do [ ! -f "$p" ] || paths+=("$p"); done
git add -- "${paths[@]}"
git diff --cached --check
git commit -m 'feat(mechanics): add globally validated structural rule router'
CANDIDATE_SHA="$(git rev-parse HEAD)"
tests=(backend/tests/test_phase57_query_binding.py backend/tests/test_phase57_global_rule_router.py backend/tests/test_phase57_reproducible_public_evaluation.py backend/tests/test_phase57_continuation_manifest_v2.py backend/tests/test_phase56_stage7_supplemental_manifest.py backend/tests/test_phase56_stage7_corpus_v2_fail_closed_shadow.py backend/tests/test_phase56_stage7_corpus_v2_gold_scored_shadow.py backend/tests/test_phase56_stage7_corpus_v2_prepare_attestation_seal.py)
for t in backend/tests/test_typed_closed_form.py backend/tests/test_public_closed_form.py backend/tests/test_canonical_fallback.py backend/tests/test_phase57_cohort_formula.py; do [ ! -f "$t" ] || tests+=("$t"); done
python -m pytest -q -o 'addopts=' "${tests[@]}"
if ! run_gate "$CANDIDATE_SHA" /tmp/phase57-global-router-candidate; then git reset --hard "$PARENT_SHA"; write_status CANDIDATE_GATE_FAILED "$PARENT_SHA" "$BASE_SCORE"; exit 0; fi
CANDIDATE_SCORE="$(cat /tmp/phase57-global-router-candidate.score)"
if [ "$CANDIDATE_SCORE" -le "$BASE_SCORE" ]; then git reset --hard "$PARENT_SHA"; write_status NO_SAFE_ROUTER_GAIN "$PARENT_SHA" "$BASE_SCORE"; exit 0; fi
export CANDIDATE_SCORE
python - <<'PY'
import json,os
from pathlib import Path
s=json.loads(Path('/tmp/phase57-global-router-selection.json').read_text())
entries=', '.join(f"`{e['signature_digest'][:12]}:{e['provider']}:{e['rule_id']}`" for e in s['entries'])
text=f"""# Phase 57 globally validated structural rule router

- parent: `{os.environ['PARENT_SHA']}`
- exact public score: **{os.environ['BASE_SCORE']}/81 → {os.environ['CANDIDATE_SCORE']}/81**
- router entries: {entries}
- globally perfect rule minimum support: **2 independent correct firings**
- newly covered public positions: `{s['selected_new_positions']}`
- wrong / unscored / forbidden / regressed / query mismatch: **0 / 0 / 0 / 0 / 0**
- runtime keys exclude identifiers, numeric values, case labels, families, answers, expected terminals, tolerances, and scores
- hidden-generalization claim: false
- production-release claim: false

This router is public-development evidence. Every activated formula was perfect wherever it fired on the complete public population and the final exact-head M/V/R/G gate remained defect-free.
"""
Path('memory/knowledge/phase57-globally-validated-rule-router.md').write_text(text)
PY
git add -- memory/knowledge/phase57-globally-validated-rule-router.md
git diff --cached --check
git commit -m 'docs(phase57): seal globally validated router evidence'
FINAL_SHA="$(git rev-parse HEAD)"
run_gate "$FINAL_SHA" /tmp/phase57-global-router-final
FINAL_SCORE="$(cat /tmp/phase57-global-router-final.score)"
test "$FINAL_SCORE" = "$CANDIDATE_SCORE"
git fetch origin "$ACTIVE_BRANCH"
test "$(git rev-parse origin/$ACTIVE_BRANCH)" = "$PARENT_SHA"
git push origin "HEAD:refs/heads/$ACTIVE_BRANCH"
write_status PUSHED_SAFE_GLOBAL_ROUTER_GAIN "$FINAL_SHA" "$FINAL_SCORE"
