# Phase 56 Claude Code Continuation Handoff

## Current authoritative state

- Disposition: `STAGE_7_IN_PROGRESS / CORPUS_PREFLIGHT_PASSED / LANE_B_NOT_STARTED`
- Stage 6 code candidate: `58589ad49982871e7d617489b525e9b67428548a`
- Stage 7 preflight checkpoint: `2512c6631acd691b2ad5033f86d8b9cc2c1088dd`
- Latest Stage 7 product head: `93c2aacf934903b4b666d1e5f9ed2c49aa12f5f5`
- Branch: `codex/phase56-generic-mechanics-engine`
- PR #17: open, Draft, unmerged; stacked on Draft PR #16
- Main: `00b3a60de6e13756d089655879a02e4094122047`
- Stage 7: **IN PROGRESS** — see `docs/PHASE56_STAGE7_PROGRESS_REPORT.md`
- Stage 8: **NOT STARTED**
- Public corpus: **SUPPLIED and integrity-verified**; public 100 still
  **NOT EXECUTED** through the engine
- Live/external model calls: **NOT RUN**
- Textbook PDF: **UNTOUCHED**

### Stage 7 packages completed and pushed

| Package | SHA | Focused tests |
|---|---|---|
| Corpus integrity + safe extraction | `612634bc25b120c25903580d4f26b82f1de94250` | 80 passed |
| Gold/runtime isolation crossing | `e1c79af201747168b609eb6283305abf1cc2e296` | 44 passed |
| Permanent offline workflow + gate runner | `a4995799c097e0b36d5c60d671c40b1765b1993d` | 19 passed |
| Real-schema corpus binding | `93c2aacf934903b4b666d1e5f9ed2c49aa12f5f5` | 191 passed (total) |

Stage 7 focused total: **191 passed**. Corpus-dependent lanes remain `NOT_RUN`
and must never be reported as passing.

## Exact-head evidence

| Gate | Run | Result |
|---|---:|---|
| DynaTutor release tests | `30045176722` | SUCCESS |
| Phase 55 textbook parser | `30045176496` | SUCCESS |
| Phase 56 Stage 6 multimodal | `30045176628` | SUCCESS |
| Same-model read-only Checker | `stage6-final-same-model-readonly` | PASS — blocking 0 |

Do not attribute these runs to the later documentation-only head. The SHA above is the authoritative code candidate.

## Stage 6 implementation map

- `backend/app/main.py`: authoritative router registration and protected middleware ordering.
- `backend/app/mechanics_multimodal_router.py`: multipart/JSON ingress and revision APIs.
- `backend/engine/mechanics/image_security.py`: bounded metadata-free RGB PNG sanitization.
- `backend/engine/mechanics/multimodal_provider.py`: explicit one-call structured provider boundary, `store=False`, no implicit secret probing.
- `backend/engine/mechanics/multimodal_modeler.py`: one envelope and at most one sanitized repair.
- `backend/engine/mechanics/evidence_reconciliation.py`: deterministic conflict/confirmation policy; confidence has no authority.
- `backend/engine/mechanics/multimodal_revision.py`: bounded immutable revision and source-only correction logic.
- `backend/engine/mechanics/multimodal_idempotency.py`: request-fingerprint binding and collision-safe replay.
- `backend/engine/mechanics/multimodal_runtime.py`: normalization → authorization → compiler → solve → verification.
- `frontend/components/HomeClient.tsx`: official student solve-screen integration.
- `frontend/components/mechanics/**`: picker, evidence overlay, conflict choices, correction UI, revision and verified-result display.

## Non-negotiable boundaries for the next session

- Stage 7 is authorised and in progress; Stage 8 is not, and must not be started.
- The public corpus is authorised for the evaluator only. Read it from a path
  outside the repository; never commit the archive or a raw split, and never
  store it in a GitHub secret. The full/private corpus and the textbook PDF
  remain out of bounds.
- Do not use corpus family, case ID, expected answer, filename, raw text regex, system type, or model confidence as answer authority.
- Do not add a second AI call, legacy answer fallback, direct graph/answer patch, or production deployment.
- Preserve PR #16/#17 as Draft and unmerged; preserve main.

## Next exact task

Corpus integrity already passes against the authorised archive. Re-confirm it,
then implement Lane B.

```bash
STAGE7_PUBLIC_CORPUS_PATH=/abs/path/dynatutor_beer12_ko_corpus_v1_public.zip \
OPENAI_API_KEY="" ANTHROPIC_API_KEY="" \
OPENAI_BASE_URL="" ANTHROPIC_BASE_URL="" \
MECHANICS_MODELER_BASE_URL="" MECHANICS_FIGURE_BASE_URL="" \
python backend/tools/run_phase56_stage7_offline_gate.py \
  --output "$TMPDIR/stage7_public_preflight_report.json"
```

Expected: exit `0`, SHA `cc8d8b27…`, `84/16/100`, distribution
`81/12/2/2/2/1`, all execution counters `0`.

Lane B route, validated by inspection but **not yet implemented**:

```text
corpus gold → TextbookProblemParseV1 → validate_parse
            → adapt_validated_phase55 → MechanicsProblemDraftV1
            → normalize_draft → authorize → compile → solve
```

Blocking design rule for that adapter: `TextbookProblemParseV1` requires an
`InterpretationCandidate` carrying a `ParserSystemType`. Derive it structurally
from the query output key and relation kinds. Do **not** copy
`gold.expected_system_type` into it — that is gold metadata and may not enter
the runtime domain, and system type has no routing, law, or solver authority.

Then continue with Lane C, Lane D, Lane E, compositional 12, synthetic 38,
metamorphic invariance, physics-changing controls, the all-zero hard-safety
aggregate, the privacy-safe final report, exact-head CI, a fresh read-only
audit, and the PR #17 body update.

Do not commit the archive or any raw split, do not store it in a GitHub secret,
and do not report an unexecuted lane as passing. Keep Live evaluation disabled,
keep PR #16/#17 open, Draft, and unmerged, leave main unchanged, and do not
start Stage 8.
