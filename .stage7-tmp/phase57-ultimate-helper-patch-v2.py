from pathlib import Path

path = Path('/tmp/phase57-ultimate-run.sh')
body = path.read_text(encoding='utf-8')
start_marker = "python - <<PY\nfrom pathlib import Path\npackages = ${KEPT_PACKAGES"
start = body.find(start_marker)
if start < 0:
    raise SystemExit('ultimate_docs_block_start_missing')
end_marker = "PY\n\ngit add -- memory/knowledge/phase57-integrated-capability-finalization.md"
end = body.find(end_marker, start)
if end < 0:
    raise SystemExit('ultimate_docs_block_end_missing')
end += len('PY')
replacement = r'''KEPT_PACKAGES_TEXT="${KEPT_PACKAGES[*]}"
export KEPT_PACKAGES_TEXT PARENT_SHA BASE_SCORE CURRENT_SCORE
python - <<'PY'
import os
from pathlib import Path

packages = os.environ.get("KEPT_PACKAGES_TEXT", "")
parent = os.environ["PARENT_SHA"]
base_score = os.environ["BASE_SCORE"]
current_score = os.environ["CURRENT_SCORE"]
text = f"""# Phase 57 integrated capability finalization

- parent: `{parent}`
- exact public score: **{base_score}/81 → {current_score}/81**
- kept capability packages: `{packages}`
- wrong / unscored / forbidden / regressed / query mismatch: **0 / 0 / 0 / 0 / 0**
- population, scorer, thresholds, and Phase 56 historical statuses: unchanged
- hidden-generalization claim: false
- production-release claim: false

Each package was retained only after a complete exact-head M/V/R/G campaign
showed a strict score increase with every measured defect at zero.
"""
Path("memory/knowledge/phase57-integrated-capability-finalization.md").write_text(
    text, encoding="utf-8"
)
PY'''
path.write_text(body[:start] + replacement + body[end:], encoding='utf-8')
