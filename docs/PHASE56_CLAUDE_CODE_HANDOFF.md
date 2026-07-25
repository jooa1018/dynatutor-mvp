# Phase 56 Claude Code Continuation Handoff

## Current authoritative state

- Disposition: `STAGE_7_IN_PROGRESS / BLOCKED_ON_PUBLIC_CORPUS_AVAILABILITY`
- Stage 6 code candidate: `58589ad49982871e7d617489b525e9b67428548a`
- Stage 7 preflight checkpoint: `2512c6631acd691b2ad5033f86d8b9cc2c1088dd`
- Latest Stage 7 product head: `a4995799c097e0b36d5c60d671c40b1765b1993d`
- Branch: `codex/phase56-generic-mechanics-engine`
- PR #17: open, Draft, unmerged; stacked on Draft PR #16
- Main: `00b3a60de6e13756d089655879a02e4094122047`
- Stage 7: **IN PROGRESS** — see `docs/PHASE56_STAGE7_PROGRESS_REPORT.md`
- Stage 8: **NOT STARTED**
- Public corpus: **NOT SUPPLIED to the evaluator environment**; public 100
  **NOT EXECUTED**
- Live/external model calls: **NOT RUN**
- Textbook PDF: **UNTOUCHED**

### Stage 7 packages completed and pushed

| Package | SHA | Focused tests |
|---|---|---|
| Corpus integrity + safe extraction | `612634bc25b120c25903580d4f26b82f1de94250` | 80 passed |
| Gold/runtime isolation crossing | `e1c79af201747168b609eb6283305abf1cc2e296` | 44 passed |
| Permanent offline workflow + gate runner | `a4995799c097e0b36d5c60d671c40b1765b1993d` | 19 passed |

Stage 7 focused total: **181 passed**. Corpus-dependent lanes remain `NOT_RUN`
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

- Do not start Stage 7 automatically from this handoff.
- Do not open the public corpus until a separate Stage 7 instruction.
- Do not use corpus family, case ID, expected answer, filename, raw text regex, system type, or model confidence as answer authority.
- Do not add a second AI call, legacy answer fallback, direct graph/answer patch, or production deployment.
- Preserve PR #16/#17 as Draft and unmerged; preserve main.

## Next exact task

Supply the authorised public archive to a runner as
`STAGE7_PUBLIC_CORPUS_PATH=/path/to/dynatutor_beer12_ko_corpus_v1_public.zip`,
then run:

```bash
python backend/tools/run_phase56_stage7_offline_gate.py \
  --output "$RUNNER_TEMP/stage7_offline_gate_report.json"
```

The gate confirms the archive SHA-256, the exact 84/16/100 splits, and the
derived `81/12/2/2/2/1` scope-adjusted distribution before any execution. Only
after it passes may Lane B execution, the compositional 12, the synthetic 38,
metamorphic controls, the API/runtime lane, and the frontend lane proceed.

Do not commit the archive or any raw split, do not store it in a GitHub secret,
and do not report an unexecuted lane as passing. Keep Live evaluation disabled
until its later bounded gate, and do not start Stage 8.
