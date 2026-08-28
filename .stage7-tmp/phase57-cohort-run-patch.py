from pathlib import Path

path = Path('/tmp/phase57-cohort-run.sh')
body = path.read_text(encoding='utf-8')
old = '''# Install and select the cohort-level catalogue from the current unsolved set.
python /tmp/phase57-cohort-install.py
python /tmp/phase57-cohort-select.py \\
  --baseline-snapshot /tmp/phase57-cohort-baseline/phase57-runtime-snapshot.json \\
  --output /tmp/phase57-cohort-selection.json
'''
new = '''# Install and select the cohort-level catalogue from the current unsolved set.
if ! python /tmp/phase57-cohort-install.py; then
  git reset --hard "$PARENT_SHA"
  git clean -fd -- \\
    backend/engine/mechanics/public_closed_form.py \\
    backend/engine/mechanics/canonical_fallback.py \\
    backend/engine/mechanics/cohort_formula.py \\
    backend/evaluation/phase56_stage7/query_binding.py \\
    backend/evaluation/phase56_stage7/cohort_formula_adapter.py \\
    backend/tests/test_phase57_query_binding.py \\
    backend/tests/test_phase57_cohort_formula.py
  write_status COHORT_INSTALL_REFUSED "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi
if ! python /tmp/phase57-cohort-select.py \\
  --baseline-snapshot /tmp/phase57-cohort-baseline/phase57-runtime-snapshot.json \\
  --output /tmp/phase57-cohort-selection.json; then
  git reset --hard "$PARENT_SHA"
  git clean -fd -- \\
    backend/engine/mechanics/public_closed_form.py \\
    backend/engine/mechanics/canonical_fallback.py \\
    backend/engine/mechanics/cohort_formula.py \\
    backend/evaluation/phase56_stage7/query_binding.py \\
    backend/evaluation/phase56_stage7/cohort_formula_adapter.py \\
    backend/tests/test_phase57_query_binding.py \\
    backend/tests/test_phase57_cohort_formula.py
  write_status NO_SAFE_COHORT_FORMULA "$PARENT_SHA" "$BASE_SCORE"
  exit 0
fi
'''
if old not in body:
    raise SystemExit('cohort_selection_block_anchor_missing')
path.write_text(body.replace(old, new, 1), encoding='utf-8')
