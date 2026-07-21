# Phase 56 Cross-Device Resume Handoff

This is the authoritative cross-device handoff for the Phase 56 branch. It was
updated on `2026-07-21T17:39:54+09:00` (`Asia/Seoul`). It is a pause record, not
an `IMPLEMENTATION COMPLETE` claim.

## A. Checkpoint identity

- Repository: `jooa1018/dynatutor-mvp`
- Working branch: `codex/phase56-generic-mechanics-engine`
- Phase 55 baseline/head: `4762727e8f9191604e2531b9982a5ae72ed73db9`
- Previous pause handoff checkpoint: `bab40bf11222b3a77fb6f5d7c736b0de831737a8`
- Previous final full-CI product checkpoint: `0de62d95357de36c4a2d5a6aff01810bdf98d776`
- Latest accepted targeted-test product checkpoint: `c19624181aaae4cd73dc3d2247b4988f5a540247`
- Latest accepted W0 product checkpoint: `7a401642bc3c8a1acfe9805af3ada8f4eeb6045a`
- Latest exact-head release-CI checkpoint: `758d30046f22d2471e5a8f4b196d8cee35f1214b`
- `HANDOFF_COMMIT_SHA = branch head containing this file`
- `HANDOFF_COMMIT_SHA` is expected to be a documentation-only child of the
  release-CI checkpoint; no CI result is attributed to that later SHA.
- PR #17 base: `codex/phase55-gpt-first-textbook-parser` at
  `4762727e8f9191604e2531b9982a5ae72ed73db9`
- PR #17 head observed before this handoff-only commit:
  `758d30046f22d2471e5a8f4b196d8cee35f1214b`
- PR #17 authoritative head after a successful checkpoint push:
  `HANDOFF_COMMIT_SHA`
- Main SHA: `00b3a60de6e13756d089655879a02e4094122047`

Remote state was read through the GitHub app immediately before checkpointing:

- PR #16: **open, Draft, unmerged**, head
  `4762727e8f9191604e2531b9982a5ae72ed73db9`, base `main`.
- PR #17: **open, Draft, unmerged**, stacked on PR #16.
- PR #16 unresolved review threads: `0`.
- PR #17 unresolved review threads: `0`.
- Main remained unchanged. No merge, undraft, rebase, force-push, production
  change, or environment-variable change was performed.

The exact final handoff SHA and whether the remote branch accepted it must be
read from the final pause response or re-queried from GitHub.

## B. Master instruction

The complete governing instruction for the new session is:

`dynatutor_phase56_ultra_master_instruction_v2.md`

That file is not stored in this repository. The user may need to attach it again
in the laptop session. This handoff summarizes state; it does not replace the
master instruction.

## C. Exact Stage 0-9 progress

### Stage 0 — ACCEPTED

- Implemented: repository/PR audit, architecture boundary, stacked Draft PR #17,
  cost/safety/stage controls.
- Incomplete: none for the Stage 0 gate.
- Accepted contract: Generic Mechanics is the calculation direction; Phase 55
  remains the evidence/fail-closed baseline; PR #17 remains stacked and Draft.
- Current failure/blocker: none.
- Next gate: none; do not repeat Stage 0.

### Stage 1 — ACCEPTED

- Implemented: frozen Draft/IR contracts, recursively immutable
  `MechanicsProblemIRV1`, safe typed math AST, Phase 55 compatibility adapter,
  evidence/correction/assumption preservation, SI normalization, and calculation
  fingerprinting.
- Incomplete: none for the Stage 1 gate.
- Accepted contract: model output is untrusted; only validated typed IR crosses
  the authority boundary; executable expression strings are forbidden.
- Current failure/blocker: none.
- Next gate: none; do not repeat Stage 1.

### Stage 2 — ACCEPTED

- Implemented: bounded one-call Mechanics modeler, validation/repair, cache,
  telemetry, privacy and conservative cost authorization.
- Incomplete: product entrypoint rollout is intentionally later work.
- Accepted contract: one modeling result per runtime execution, at most one
  bounded repair, no answer/root/verification authority, fail closed.
- Current failure/blocker: none for the Stage 2 gate.
- Next gate: none; do not repeat Stage 2.

### Stage 3 — ACCEPTED

- Implemented: typed core mechanics law catalog, deterministic relevant-subgraph
  compiler, provenance-bound Equation Graph, rank/closure analysis, exact IR
  authorization, domain/initial-condition and resource-limit gates.
- Incomplete: named advanced-law gaps are Stage 5 work, not a reopened Stage 3.
- Accepted contract: compiler uses typed IR only and emits bounded safe AST graph
  records; diagnostic labels are not calculation authority.
- Current failure/blocker: none for the Stage 3 gate.
- Next gate: none; do not repeat Stage 3.

### Stage 4 — ACCEPTED

- Checkpoint: `c19624181aaae4cd73dc3d2247b4988f5a540247`
  (`feat(mechanics): add graph-only solver and verification`).
- Implemented: frozen planner/solver/verifier contracts; backend routing from
  Equation Graph structure only; typed-AST translation; bounded symbolic and
  numeric execution; isolated JSON-only numeric work; all-candidate retention;
  independent verification; unique verified selection; V2 evidence and additive
  legacy projections.
- Incomplete: no Stage 4 work remains. Product API wiring belongs to Stage 5.
- Accepted contract: raw text, `system_type`, corpus metadata, expected answers,
  model-selected solver names, and untrusted callables cannot select a backend or
  candidate. Every generated root is retained; only exactly one independently
  verified candidate can be selected.
- Current failure/blocker: none. The later exact-head release run recorded in
  section F includes all accepted Stage 4 tests.
- Next gate: none; do not redesign or repeat Stage 4.

### Stage 5 — IN_PROGRESS

- Accepted W0 product checkpoint: `7a401642bc3c8a1acfe9805af3ada8f4eeb6045a`.
- Exact-head release-CI checkpoint: `758d30046f22d2471e5a8f4b196d8cee35f1214b`.
- Accepted implementation:
  - exact 29-solver migration matrix in
    `docs/MECHANICS_LEGACY_MIGRATION.md`;
  - diagnostics-only legacy observation/differential/invariance contracts;
  - internal one-call runtime coordinator for off/shadow/confirm/auto/required,
    exact IR authorization, compilation, graph solving, confirmation gating,
    retained execution, sanitized failures, and safe summaries.
  - W0 offline IR-built migration probe and invariance comparison. Diagnostic
    variants retain identical accepted evidence and calculation-authoritative
    structure while varying only source-identity metadata; a physical force
    change remains a negative control and changes the result.
- Accepted Stage 5 decisions:
  - legacy parity is diagnostic only and can never verify, select, repair, or
    provide a generic fallback answer;
  - `off` preserves rollback; `shadow` preserves the legacy visible result;
    `confirm/auto/required` never expose conflicting legacy route/equation/FBD
    artifacts after an authoritative generic block/failure;
  - the Phase 55 AI parser and Mechanics modeler must never form a two-model
    chain in one request;
  - `required` plus disabled Mechanics must remain distinguishable and fail
    closed at product integration;
  - no legacy solver is demoted before independent per-solver parity evidence;
  - evidence quote/span/occurrence changes remain provenance-sensitive and are
    not treated as raw-text-only invariance;
  - variant labels carry no calculation or comparison authority, and every W0
    variant is independently compiled and solved.
- Still incomplete:
  - actual IR -> compile -> solve -> legacy diagnostic parity for every registered
    solver: current count `0/29` same-fixture end-to-end cases;
  - Wave 1 native cases, Wave 2 coverage gates, Wave 3 typed laws for translating
    frame, Coriolis, polar, and slot-pin motion;
  - product `/solve` and `/diagnose` integration, required-disabled config edge,
    dual-model exclusion, API schema/route tests, and vector-answer projection.
- Current failure/blocker: none at the W0 boundary. Exact-head release CI and
  fresh independent W0/CI Checkers passed with zero blocking findings.
- Next gate: add the first same-fixture offline IR -> compile -> solve -> legacy
  diagnostic parity case for canonical registry entry `single_particle_newton`,
  then continue the 29-entry sequence without family/case-ID routing.

### Stage 6 — NOT_STARTED

- Implemented: no Phase 56 figure merge/correction or UI V2 work.
- Incomplete: one-call text+real-image modeling, `FigureObservationV1`, evidence
  confirmation/conflict handling, API and frontend integration, synthetic figure
  coverage.
- Accepted contract: the PDF is reference-only; figure facts require evidence and
  cannot be invented.
- Current failure/blocker: Stage 5 gate is incomplete.
- Next gate: only after Stage 5 acceptance.

### Stage 7 — NOT_RUN

- Implemented: no evaluation result.
- Incomplete: sealed public 100, adversarial, compositional 12, synthetic figure
  30, metamorphic, hard-safety, and unchanged-threshold evaluation.
- Accepted contract: input-only harness; gold/case/family metadata cannot enter
  runtime or routing.
- Current failure/blocker: stage ordering; corpus remains sealed.
- Next gate: only after Stage 6 acceptance.

### Stage 8 — NOT_STARTED

- Implemented: no final exact-head release gate for the completed Phase 56 work.
- Incomplete: backend/frontend/wrapper/typecheck/build/performance CI and final
  independent read-only Checker at one exact head.
- Accepted contract: any blocking finding prevents PASS.
- Current failure/blocker: Stages 5-7 incomplete.
- Next gate: exact-head final CI after Stage 7.

### Stage 9 — NOT_RUN

- Implemented: no Live Stage A or Stage B result.
- Incomplete: bounded Live evaluation, only if all offline gates pass and an
  authorized secret/budget path exists.
- Accepted contract: no secret access; no Live call without prior gates; failed or
  unavailable conditions remain honest `NOT RUN`.
- Current failure/blocker: offline gates incomplete.
- Next gate: none until Stage 8 PASS.

## D. Exact work at the pause boundary

- Work immediately before this update: accepted `S5-W0-BASE`, followed by a
  coverage-preserving repair of the release workflow's duplicated fast suite.
- W0 production compiler/harness code changed: **NO**. The smallest correction
  was fixture-only in
  `backend/tests/test_phase56_mechanics_migration_harness.py`, plus the precise
  raw-text/evidence distinction in `docs/GENERIC_MECHANICS_IR.md`.
- CI-only files changed after W0 acceptance:
  - `.github/workflows/backend-tests.yml`
  - `scripts/check_backend_fast.sh`
  - `docs/KNOWN_LIMITATIONS.md`
  - `docs/RELEASE_CHECKLIST.md`
- Safe last product unit: `7a401642bc3c8a1acfe9805af3ada8f4eeb6045a`.
- Safe last exact-head release-CI unit:
  `758d30046f22d2471e5a8f4b196d8cee35f1214b`, run `29814688877`, `SUCCESS`.
- Exact open W0 failure: **NONE**. The formerly failing diagnostic-invariance
  test and all 23 W0 harness tests pass on the authoritative Ubuntu CI runner.
- Immediate next task: create the first independent same-fixture parity package
  for registry entry `single_particle_newton`: one typed IR fixture must compile
  and solve generically, while the legacy result is captured only as a
  diagnostic oracle. Prove residual/parity and invariance without passing raw
  text, `system_type`, corpus labels, expected answers, or legacy output into the
  generic calculation path.

Read in this order on the laptop:

1. `docs/PHASE56_PAUSE_HANDOFF.md`
2. reattached `dynatutor_phase56_ultra_master_instruction_v2.md`
3. `docs/ADR_PHASE56_GENERIC_MECHANICS_ENGINE.md`
4. `docs/GENERIC_MECHANICS_IR.md`
5. `docs/MECHANICS_SECURITY.md`
6. `docs/MECHANICS_LEGACY_MIGRATION.md`
7. `backend/engine/mechanics/migration/contracts.py`
8. `backend/engine/mechanics/migration/parity.py`
9. `backend/engine/mechanics/migration/harness.py`
10. `backend/tests/test_phase56_mechanics_migration_harness.py`
11. `backend/engine/mechanics/runtime/contracts.py`
12. `backend/engine/mechanics/runtime/orchestrator.py`

The old local-only work ledger is helpful but not required. Its absence on the
new laptop is not a blocker.

## E. Changed files

### Last accepted checkpoint after the previous pause

The accepted Stage 4 commit changes these 26 files from `d3b57fe...`:

```text
M backend/engine/mechanics/__init__.py
M backend/engine/mechanics/compiler/contracts.py
M backend/engine/mechanics/math_ast.py
A backend/engine/mechanics/pipeline.py
A backend/engine/mechanics/solver/__init__.py
A backend/engine/mechanics/solver/_audit.py
A backend/engine/mechanics/solver/backends.py
A backend/engine/mechanics/solver/contracts.py
A backend/engine/mechanics/solver/engine.py
A backend/engine/mechanics/solver/isolation.py
A backend/engine/mechanics/solver/planner.py
A backend/engine/mechanics/solver/translation.py
A backend/engine/mechanics/verification/__init__.py
A backend/engine/mechanics/verification/adapters.py
A backend/engine/mechanics/verification/contracts.py
A backend/engine/mechanics/verification/evaluator.py
A backend/engine/mechanics/verification/verifier.py
A backend/tests/test_phase56_mechanics_evidence_adapters.py
A backend/tests/test_phase56_mechanics_numeric_strictness.py
A backend/tests/test_phase56_mechanics_solver_contract.py
A backend/tests/test_phase56_mechanics_solver_execution.py
A backend/tests/test_phase56_mechanics_solver_planner.py
A backend/tests/test_phase56_mechanics_solver_verification_integration.py
A backend/tests/test_phase56_mechanics_verification_contract.py
A backend/tests/test_phase56_mechanics_verifier.py
M docs/MECHANICS_SECURITY.md
```

### Current Stage 5 implementation after the accepted Stage 4 checkpoint

Modified:

```text
M backend/engine/mechanics/__init__.py
```

New:

```text
A backend/engine/mechanics/migration/__init__.py
A backend/engine/mechanics/migration/contracts.py
A backend/engine/mechanics/migration/harness.py
A backend/engine/mechanics/migration/parity.py
A backend/engine/mechanics/runtime/__init__.py
A backend/engine/mechanics/runtime/contracts.py
A backend/engine/mechanics/runtime/orchestrator.py
A backend/tests/test_phase56_mechanics_legacy_parity.py
A backend/tests/test_phase56_mechanics_migration_harness.py
A backend/tests/test_phase56_mechanics_runtime.py
A backend/tests/test_phase56_mechanics_runtime_contract.py
A backend/tests/test_phase56_mechanics_runtime_static.py
A docs/MECHANICS_LEGACY_MIGRATION.md
```

W0 acceptance additionally modified:

```text
M backend/tests/test_phase56_mechanics_migration_harness.py
M docs/GENERIC_MECHANICS_IR.md
```

The exact-head release-CI repair modified:

```text
M .github/workflows/backend-tests.yml
M docs/KNOWN_LIMITATIONS.md
M docs/RELEASE_CHECKLIST.md
M scripts/check_backend_fast.sh
```

Deleted: `NONE`.

Document-only files in the current Stage 5 delta:

- `docs/MECHANICS_LEGACY_MIGRATION.md`
- this handoff document is updated by the final documentation commit.

Test files in the current Stage 5 delta:

- `backend/tests/test_phase56_mechanics_legacy_parity.py`
- `backend/tests/test_phase56_mechanics_migration_harness.py`
- `backend/tests/test_phase56_mechanics_runtime.py`
- `backend/tests/test_phase56_mechanics_runtime_contract.py`
- `backend/tests/test_phase56_mechanics_runtime_static.py`

### Complete Phase 56 branch file set relative to Phase 55

At exact-head release-CI checkpoint `758d300...` there are exactly `73` changed
files:

```text
M .github/workflows/backend-tests.yml
A backend/engine/mechanics/__init__.py
A backend/engine/mechanics/compiler/__init__.py
A backend/engine/mechanics/compiler/compiler.py
A backend/engine/mechanics/compiler/contracts.py
A backend/engine/mechanics/contracts.py
A backend/engine/mechanics/errors.py
A backend/engine/mechanics/laws/__init__.py
A backend/engine/mechanics/laws/base.py
A backend/engine/mechanics/laws/core.py
A backend/engine/mechanics/math_ast.py
A backend/engine/mechanics/migration/__init__.py
A backend/engine/mechanics/migration/contracts.py
A backend/engine/mechanics/migration/harness.py
A backend/engine/mechanics/migration/parity.py
A backend/engine/mechanics/modeler.py
A backend/engine/mechanics/modeler_cache.py
A backend/engine/mechanics/modeler_client.py
A backend/engine/mechanics/modeler_config.py
A backend/engine/mechanics/modeler_errors.py
A backend/engine/mechanics/modeler_inputs.py
A backend/engine/mechanics/modeler_prompt.py
A backend/engine/mechanics/modeler_repair.py
A backend/engine/mechanics/modeler_telemetry.py
A backend/engine/mechanics/normalization.py
A backend/engine/mechanics/phase55_adapter.py
A backend/engine/mechanics/pipeline.py
A backend/engine/mechanics/runtime/__init__.py
A backend/engine/mechanics/runtime/contracts.py
A backend/engine/mechanics/runtime/orchestrator.py
A backend/engine/mechanics/solver/__init__.py
A backend/engine/mechanics/solver/_audit.py
A backend/engine/mechanics/solver/backends.py
A backend/engine/mechanics/solver/contracts.py
A backend/engine/mechanics/solver/engine.py
A backend/engine/mechanics/solver/isolation.py
A backend/engine/mechanics/solver/planner.py
A backend/engine/mechanics/solver/translation.py
A backend/engine/mechanics/units.py
A backend/engine/mechanics/validation.py
A backend/engine/mechanics/verification/__init__.py
A backend/engine/mechanics/verification/adapters.py
A backend/engine/mechanics/verification/contracts.py
A backend/engine/mechanics/verification/evaluator.py
A backend/engine/mechanics/verification/verifier.py
A backend/tests/test_phase56_mechanics_compiler.py
A backend/tests/test_phase56_mechanics_contract.py
A backend/tests/test_phase56_mechanics_evidence_adapters.py
A backend/tests/test_phase56_mechanics_legacy_parity.py
A backend/tests/test_phase56_mechanics_migration_harness.py
A backend/tests/test_phase56_mechanics_modeler.py
A backend/tests/test_phase56_mechanics_normalization.py
A backend/tests/test_phase56_mechanics_numeric_strictness.py
A backend/tests/test_phase56_mechanics_runtime.py
A backend/tests/test_phase56_mechanics_runtime_contract.py
A backend/tests/test_phase56_mechanics_runtime_static.py
A backend/tests/test_phase56_mechanics_solver_contract.py
A backend/tests/test_phase56_mechanics_solver_execution.py
A backend/tests/test_phase56_mechanics_solver_planner.py
A backend/tests/test_phase56_mechanics_solver_verification_integration.py
A backend/tests/test_phase56_mechanics_validation.py
A backend/tests/test_phase56_mechanics_verification_contract.py
A backend/tests/test_phase56_mechanics_verifier.py
A backend/tests/test_phase56_phase55_adapter.py
M backend/tools/_pint_shim.py
A docs/ADR_PHASE56_GENERIC_MECHANICS_ENGINE.md
A docs/GENERIC_MECHANICS_IR.md
M docs/KNOWN_LIMITATIONS.md
A docs/MECHANICS_LEGACY_MIGRATION.md
A docs/MECHANICS_SECURITY.md
A docs/PHASE56_PAUSE_HANDOFF.md
M docs/RELEASE_CHECKLIST.md
M scripts/check_backend_fast.sh
```

## F. Tests and CI evidence

Only actually executed evidence is listed.

### Previous raw default/complete full-CI checkpoint

- Exact SHA: `0de62d95357de36c4a2d5a6aff01810bdf98d776`
- GitHub Actions release run: `29690536932` — `SUCCESS`.
- Backend default: `1706 passed, 1 skipped, 267 deselected`.
- Complete backend: `1973 passed, 1 skipped`.
- Benchmark selection: `147 passed`.
- Audit selection: `111 passed`.
- Fast and aggregate wrappers: `PASS`.
- Frontend tests, typecheck, and build: `PASS`.
- Performance: `PASS`; warm 43 cases/86 samples, mean 12.653 ms,
  p95 47.607 ms, max 55.838 ms; cold import 810.484 ms; max RSS
  92.801 MB; four-round pooled comparison had zero regressions.

### Accepted Stage 4 targeted evidence

- Exact checkpoint: `c19624181aaae4cd73dc3d2247b4988f5a540247`.
- Contract R4: `131 passed`; connected Stage 3 regression: `234 passed`.
- Solver execution/integration evidence: `28` execution tests, `3` integration
  tests, and final `5` IPC boundary tests passed.
- Upstream numeric strictness: `135 passed`.
- Verifier adapter final regression: `15 passed`.
- Final pipeline/document integration: `3 passed`.
- Independent Checkers: Stage 4 contract, solver, verifier, upstream numeric, and
  final integration all returned `PASS` with zero blocking findings.
- GitHub Actions on `c196241...`: `NOT RUN` because the checkpoint was not yet
  pushed.

### Stage 5 accepted subpackage evidence

- Migration matrix: independent `PASS`, exact `29/29` registered order, nine
  fields per row, blocking `0`, nonblocking `0`.
- Diagnostics-only parity contracts: final independent `PASS`; `33` focused
  tests; all five forged terminal/status reports rejected; seven generic
  non-solved terminals across three observation branches produced `21` valid
  round trips; compile/schema/import/export/static/diff checks passed.
- Runtime coordinator: independent `PASS`, blocking `0`, nonblocking `0`;
  `114` focused tests and `7` exact regressions passed; eight solve terminals
  across four active modes `32/32`; overdetermined graph identity across four
  modes `4/4`; compile/import/schema/export/diff/whitespace checks passed.

### Accepted W0 evidence

- Product checkpoint: `7a401642bc3c8a1acfe9805af3ada8f4eeb6045a`.
- `py_compile`: `PASS`.
- Accepted compiler boundary tests: `2 passed`; full compiler regression:
  `57 passed`; runtime: `114 passed`; legacy parity: `30 passed`.
- W0 harness: `23 passed` with the Windows-only worker-startup allowance used
  solely for local evidence. The unchanged default 5-second symbolic budget was
  not claimed green on Windows/Python 3.12.
- Fresh independent W0 Checker: `PASS`, blocking findings `0`. It confirmed
  independent compile/solve execution, full result/signature comparison,
  evidence provenance sensitivity, physical-change detection, label
  non-authority, and no corpus/PDF/family special case.

### Latest exact-head release CI

- Exact SHA: `758d30046f22d2471e5a8f4b196d8cee35f1214b`.
- GitHub Actions release run: `29814688877` (run #421) — `SUCCESS`.
- The PR checkout merge commit was `2ae67dee9034f401c64d55ceec6609ad356c75e3`;
  its tree `7925928cb4e83aab008a7355971f565ff366e082` exactly matched the PR head
  tree, so the tested content was the exact frozen head content.
- Fast wrapper: `2221 passed, 1 skipped, 267 deselected` in `228.55s` under the
  bounded 420-second watchdog.
- Benchmark wrapper: `147 passed` in `41.96s`.
- Audit wrapper: `111 passed` in `27.14s`.
- Backend frontend-marker group: `15 passed` in `2.36s`.
- The four marker groups' collected-nodeid union equals the complete backend
  collection: `2489/2489`, uncovered `0`; slow-only uncovered tests `0`.
- Frontend unit tests, typecheck, build, and repository metadata: `PASS`.
- Warm latency: 43 cases/86 samples, mean `9.648245 ms`, p95 `32.204848 ms`,
  max `41.610153 ms`; limits remain 60/120 ms.
- Cold import: `629.619939 ms`; max RSS: `90.801 MB`; limits remain
  5000 ms/512 MB.
- Four-round pooled performance comparison: `PASS`, regressions `0`; the worst
  pooled p95 change was `+0.599%`, below the unchanged `15%` limit.
- Fresh independent CI-fix Checker: `PASS`, blocking findings `0`.
- Preceding run `29811759354` had already passed the raw default
  (`2221 passed, 1 skipped`) and complete (`2488 passed, 1 skipped`) suites; it
  failed only when the identical fast selection was run again under the stale
  120-second wrapper. The accepted CI repair removes raw/aggregate duplication,
  retains complete marker-union coverage, and changes no physics tolerance.

### Still not run

- Stage 5 same-fixture per-solver parity: `0/29`.
- Stage 6 figure/UI tests: `NOT RUN`.
- Stage 7 corpus/compositional/synthetic tests: `NOT RUN`.
- Stage 8 final exact-head CI/Checker for completed Stages 5-7: `NOT RUN`.
- Stage 9 Live: `NOT RUN`.

`W0_ACCEPTED_AT_EXACT_HEAD`: the latest code/CI checkpoint contains the accepted
Stage 5 matrix/parity/runtime packages and accepted W0 boundary. It is not a
Phase 56 completion claim because same-fixture migration remains `0/29` and
Stages 6-9 remain incomplete.

## G. Architecture invariants

- `system_type` has no calculation authority: **ACCEPTED** inside the generic
  IR/compiler/graph pipeline; **PENDING** for complete product-path migration
  because the existing legacy rollback path still routes by labels.
- Raw text is not read in the generic solve stage: **ACCEPTED**. Removal from all
  legacy product calculation paths is **PENDING** Stage 5 migration.
- Corpus metadata is not read by runtime: **ACCEPTED**; the public corpus remains
  sealed.
- AI has no equation execution, root selection, verification, or final-answer
  authority: **ACCEPTED** in Stages 1-4 and the internal Stage 5 runtime.
- Only typed AST reaches calculation backends: **ACCEPTED**.
- All generated candidate roots are preserved: **ACCEPTED**.
- Only one uniquely verified candidate can be selected automatically:
  **ACCEPTED**.
- Phase 55 evidence and fail-closed contracts are preserved: **ACCEPTED**.
- Legacy solver is not hidden answer authority on the generic path:
  **ACCEPTED** for internal generic execution/parity; **PENDING** for product API
  integration. Legacy remains the explicit `off` rollback and `shadow` visible
  path until migration gates pass.

## H. Corpus and PDF state

- Public corpus ZIP: **not opened for evaluation; sealed**.
- Stage used: `NONE` in this resumed Stage 4/5 work.
- Runtime leakage: `NONE FOUND`; runtime has no corpus family/case/gold lookup.
- Private held-out: **not provided; NOT RUN**.
- Beer combined-edition PDF: previously used only as a structural reference for
  Dynamics Chapters 11-19. It is not a runtime, routing, expected-answer, or test
  oracle. No page, problem text, numeric value, image, or exact mapping is
  committed.
- Actual user target edition, Dynamics-only, SI, Korean exact-match evaluation:
  **NOT RUN**.

## I. Known risks and unresolved decisions

- Per-solver migration evidence is `0/29`; compiler unit fixtures do not count as
  same-IR end-to-end parity.
- Advanced typed-law gaps remain for translating-frame acceleration, Coriolis,
  polar kinematics, and slot-pin relative motion; full rigid acceleration and
  event-root coverage remain partial.
- Product integration is absent. `/solve` and `/diagnose` still need one serial
  owner to prevent legacy route/FBD/equation leakage on generic blocked states.
- `MechanicsModelerConfig.from_env()` currently collapses disabled requested modes
  to `off`; required-disabled fail-closed behavior must be repaired at integration.
- Phase 55 parser plus Mechanics modeler dual-call exclusion is designed but not
  wired.
- Generic vector-answer projection into the existing product response is not
  decided; it must never silently fall back to a legacy scalar answer.
- Marker-union coverage is exact at `758d300...`; a future slow-only test must
  add a dedicated CI group, as documented in `docs/KNOWN_LIMITATIONS.md`.
- Figure/UI, public-corpus evaluation, final CI, and bounded Live are untouched.
- Local `gh` is not installed. The GitHub app published exact verified Git
  objects with a non-forced fast-forward; a public fetch confirmed the remote
  tree and clean diff.
- No secret was accessed. No security policy, deployment, cost cap, or production
  setting was changed.

## J. First actions in the laptop session

1. Clone/fetch `jooa1018/dynatutor-mvp` and verify PR #16/#17 remote state,
   Draft status, base/head, main SHA, and unresolved threads.
2. Check out `codex/phase56-generic-mechanics-engine` at the final handoff head.
3. Read this handoff completely.
4. Read the reattached Master Instruction v2 completely.
5. Confirm exact-head release-CI checkpoint `758d300...`, run `29814688877`,
   remains successful; do not repeat its accepted W0/CI investigation.
6. Do not repeat Stages 0-4 or the accepted Stage 5 matrix/parity/runtime/W0
   reviews.
7. Start canonical registry entry 1, `single_particle_newton`, as the first
   same-fixture IR -> compile -> solve -> legacy diagnostic parity case.
8. Run only the focused fixture/harness and connected accepted regressions, then
   use a fresh independent Checker before accepting that migration unit.
9. Keep the corpus sealed until Stage 7 and the PDF reference-only until its
   permitted coverage/figure use.
10. Continue without intermediate user confirmation unless a hard blocker,
    destructive action, secret/cost authorization, production action, or material
    scope decision is required.

## K. Laptop New Session Resume Prompt

```text
Resume Phase 56 for repository jooa1018/dynatutor-mvp.

Branch: codex/phase56-generic-mechanics-engine
PR #16: Phase 55, open Draft, unmerged, head 4762727e8f9191604e2531b9982a5ae72ed73db9
PR #17: Phase 56 stacked Draft on PR #16; keep Draft and unmerged
Current handoff SHA: branch head containing docs/PHASE56_PAUSE_HANDOFF.md (verify exact remote SHA first)
Latest accepted W0 product SHA: 7a401642bc3c8a1acfe9805af3ada8f4eeb6045a
Latest accepted targeted-test product SHA: c19624181aaae4cd73dc3d2247b4988f5a540247
Latest exact-head release-CI SHA: 758d30046f22d2471e5a8f4b196d8cee35f1214b
Latest exact-head release run: 29814688877, SUCCESS
Resume Stage: Stage 5 IN_PROGRESS, S5-W0-BASE accepted, same-fixture parity 0/29

First read, in order:
1) docs/PHASE56_PAUSE_HANDOFF.md
2) the user-attached dynatutor_phase56_ultra_master_instruction_v2.md
3) docs/ADR_PHASE56_GENERIC_MECHANICS_ENGINE.md
4) docs/GENERIC_MECHANICS_IR.md
5) docs/MECHANICS_SECURITY.md
6) docs/MECHANICS_LEGACY_MIGRATION.md
7) backend/engine/mechanics/migration/contracts.py
8) backend/engine/mechanics/migration/parity.py
9) backend/engine/mechanics/migration/harness.py
10) backend/tests/test_phase56_mechanics_migration_harness.py

The old laptop-local work ledger may be absent. Do not treat that as a blocker;
this handoff is authoritative. Follow Master Instruction v2 and the user's
Sol-Terra-Luna operating rules. Do not repeat accepted Stages 0-4 or accepted
Stage 5 matrix/parity/runtime/W0 packages.

Next exact task: implement the first same-fixture offline parity package for
canonical registry entry `single_particle_newton`. Build a typed accepted IR,
compile and solve it through the generic path, collect the legacy result only as
a diagnostic oracle, and prove residual/parity plus diagnostic invariance. Raw
text, `system_type`, corpus/family/case metadata, expected answers, and legacy
output must not enter generic compilation, solving, verification, or selection.
Run focused tests and connected regressions, then use a fresh independent
Checker before accepting entry 1/29.

Keep the public corpus sealed until Stage 7. The Beer PDF is reference-only for
Dynamics Chapters 11-19 structure and permitted later figure/coverage work; it is
never a runtime or exact-answer oracle. Private held-out and actual Korean/SI
exact-match evaluation remain NOT RUN.

Do not merge PR #16/#17, undraft, push main, force-push, rebase, deploy, change
production/environment values, access API keys, incur Live cost, or commit corpus,
private, or textbook assets. Apart from a hard blocker or an action requiring new
authority, continue without intermediate confirmation.
```
