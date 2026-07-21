# Phase 56 Cross-Device Resume Handoff

This is the authoritative cross-device handoff for the Phase 56 branch. It was
updated on `2026-07-22` (`Asia/Seoul`) after Entry 5 acceptance and the separate
authoritative typed scope/runtime amendment child. It is a pause record, not an
`IMPLEMENTATION COMPLETE` claim.

## A. Checkpoint identity

- Repository: `jooa1018/dynatutor-mvp`
- Working branch: `codex/phase56-generic-mechanics-engine`
- Phase 55 baseline/head: `4762727e8f9191604e2531b9982a5ae72ed73db9`
- Previous pause handoff checkpoint: `bab40bf11222b3a77fb6f5d7c736b0de831737a8`
- Previous final full-CI product checkpoint: `0de62d95357de36c4a2d5a6aff01810bdf98d776`
- Previous accepted Stage-4 targeted-test checkpoint: `c19624181aaae4cd73dc3d2247b4988f5a540247`
- Latest accepted W0 product checkpoint: `7a401642bc3c8a1acfe9805af3ada8f4eeb6045a`
- Previous documentation handoff checkpoint: `bd5afe32958ba1ca4efdc5ecc4c22a0ba22fefdd`
- Latest accepted entry-3 product code commit:
  `d58e2c9bcd8c04c8fa380699e19df6a6c43e7296` (tree
  `72301ea20e43e5310a269dac943fc7d56f01f689`, parent documentation handoff
  `6c53e0fdbbf70854bfec3078d73fb48371fc9a12`).
- Latest accepted entry-4 product/same-fixture migration checkpoint:
  `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9` (tree
  `dc0e90d954b16a342c16073f2c3021f65da875bf`, parent documentation handoff
  `bd5afe32958ba1ca4efdc5ecc4c22a0ba22fefdd`, commit
  `feat(mechanics): migrate Atwood pulley solver`).
- Latest Entry-5 product/same-fixture migration checkpoint:
  `7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e`.
- Current branch head: the separate typed scope/runtime amendment child of
  Entry-5 product `7fff1b83...`; verify its exact SHA from the branch.
- Latest release-validated migration tree (Entry 4):
  `dc0e90d954b16a342c16073f2c3021f65da875bf`.
- Latest exact-head release-CI checkpoint: `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9`
- `HANDOFF_COMMIT_SHA = branch head containing this file`
- `HANDOFF_COMMIT_SHA` is the typed scope/runtime amendment child of Entry-5
  product `7fff1b83...`; no release-CI result is attributed to either later SHA.
- PR #17 base: `codex/phase55-gpt-first-textbook-parser` at
  `4762727e8f9191604e2531b9982a5ae72ed73db9`
- PR #17 product head before the typed scope/runtime amendment child:
  `7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e`
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
- Exact-head release-CI checkpoint: `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9`.
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
  - canonical registry entry 1, `single_particle_newton`, as a same-fixture
    Draft -> normalization -> accepted IR -> compile -> generic solve package.
    Baseline and signed multi-force cases have complete value/unit/terminal/
    candidate/residual parity against a diagnostics-only direct legacy call;
    ambiguous force direction fails closed, and diagnostic labels/source digest
    changes do not affect the generic result.
  - canonical registry entry 2, `incline_no_friction`, at exact product/CI
    checkpoint `5e49f2f267c4c8d75aec6e99e3714fc36f700257` (tree
    `9ffbd6cc9bd60e1153891c2b2b7053e2d801a35c`, parent documentation handoff
    `8711b8a328b7334b0545d62f8a2bba6c8317f0b6`, commit
    `feat(mechanics): migrate frictionless incline solver`). Typed incline-angle
    gravity projections, evidenced frictionless touching contact/fixed-surface
    no penetration, and the inclusive `0 <= theta <= pi/2` domain now emit and
    validate generically. The package proves 0/90-degree and interior signed
    cases, diagnostic-only legacy parity, residuals, authority negatives, and
    metadata invariance without family/case-ID routing.
  - canonical registry entry 3, `incline_with_friction`, with product code commit
    `d58e2c9bcd8c04c8fa380699e19df6a6c43e7296` (tree
    `72301ea20e43e5310a269dac943fc7d56f01f689`, parent documentation handoff
    `6c53e0fdbbf70854bfec3078d73fb48371fc9a12`, commit
    `feat(mechanics): migrate friction incline solver`) and exact successful
    product/CI checkpoint `c134664cd863d33b50c7e5ae794af2ad61ed6524`
    (tree `987cb4ec8b7cbcc321d713313c179e8ca4bcd553`, remediation commit
    `ci: split slow mechanics parity checks`). The exact evidenced incline/contact
    topology emits tangent/normal gravity projection, fixed-contact
    no-penetration, the normal bound, and two particle-Newton equations. Typed
    sticking adds a zero-tangential-acceleration law and two-sided static-friction
    bounds with an inclusive hold/slip boundary; typed sliding instead binds
    kinetic friction opposite an evidenced positive tangential motion carrier.
    Query direction remains an independent signed projection, and `mu=0` reduces
    naturally to the frictionless result. Missing or contradictory regime,
    motion, contact, axis-cardinality, entity, or interval authority fails closed
    before any legacy call.
  - canonical registry entry 4, `pulley_atwood`, at exact product/CI checkpoint
    `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9` (tree
    `dc0e90d954b16a342c16073f2c3021f65da875bf`, parent documentation handoff
    `bd5afe32958ba1ca4efdc5ecc4c22a0ba22fefdd`, commit
    `feat(mechanics): migrate Atwood pulley solver`). The compiler admits only
    the exact evidenced two-particle/one-rope/one-fixed-ideal-pulley/gravity
    topology, including wrap and two body attachments, taut/fixed state, and
    approved evidenced massless, inextensible, fixed, and ideal assumptions.
    The resulting graph contains exactly two weight, two particle-Newton, one
    massless-rope tension, and one fixed-pulley motion equation. Baseline and
    B-up acceleration signs, a direct tension query, equal-mass zero
    acceleration, mass-swap sign reversal with invariant tension, independent
    residuals, exhaustive candidates, and metadata invariance all pass. The
    generic result is frozen before direct legacy diagnostics. Invalid
    structure, scope, evidence, assumptions, ambiguity, mass, or gravity fails
    closed without a legacy call. Authority inputs are bounded and snapshotted
    once per invariance comparison before any variant runs; massive-pulley
    Newton-Euler/unequal-tension graphs and rigid-body fixed-pulley rope laws are
    preserved by connected regressions.
  - canonical registry entry 5, `pulley_table_hanging`, at accepted product
    checkpoint `7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e`. The typed graph binds
    the table/hanging pair, horizontal contact, rope/fixed-pulley topology, and
    explicit no-friction, sliding, or sticking regime. The accepted package
    proves the static threshold, `mu=0` reduction, signed acceleration and
    tension queries, independent Newton/contact/rope residuals, metadata
    invariance, and fail-closed authority/structure/evidence negatives. Targeted
    evidence is fast `45 passed, 9 deselected`, slow `9 passed, 45 deselected`,
    compiler regression `57 passed`, and a fresh Entry-5 Checker `PASS` with
    blocking findings `0`. Wave A release CI is pending until entries 6 and 7.
- Accepted Stage 5 decisions:
  - legacy parity is diagnostic only and can never verify, select, repair, or
    provide a generic fallback answer;
  - for the staged in-scope rollout, `off` preserves rollback and `shadow`
    preserves the legacy visible result; deferred entries are restricted to
    off-mode rollback only and never receive a silent or shadow fallback answer;
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
  - the exact inventory is `29/29` classified: `25` in scope and four deferred;
    accepted in-scope evidence is `5/25`, with `20/25` pending;
  - Waves A-F remain active under the superseding typed scope plan; Wave A entry
    5 is accepted, entries 6-7 and the Wave A family Checker/release CI remain;
  - product `/solve` and `/diagnose` integration, required-disabled config edge,
    dual-model exclusion, API schema/route tests, and vector-answer projection.
- Current failure/blocker: none at the accepted `5/25` in-scope boundary. Entry
  5 targeted evidence and its fresh Checker passed; the latest exact release CI
  remains Entry 4 at `dedb4c7...`, run `29841110152` (run #429, `SUCCESS`).
- Next gate: canonical registry entry 6, `pulley_incline_hanging`, followed by
  entry 7, `massive_pulley_atwood`; then run the Wave A family Checker and
  release CI once for the complete 5-7 family.

#### Superseding Stage 5 typed scope and exact waves

The exact `29/29` registry inventory remains in canonical order. The active
classification is `25` in scope and four deferred, exactly entries 19
`spring_mass_vibration`, 23 `relative_acceleration_translation`, 24
`coriolis_relative_motion`, and 28 `slot_pin_relative_motion`. Entry 26
`polar_kinematics` is explicitly in scope. This supersedes every older Wave
1/2/3 grouping.

- **Wave A, entries 5-7:** `pulley_table_hanging`,
  `pulley_incline_hanging`, `massive_pulley_atwood`.
- **Wave B, entries 8-10:** `pure_rolling_energy`,
  `rolling_energy_general`, `vertical_circle`.
- **Wave C, entries 11-13:** `collision_1d`,
  `constant_acceleration_1d`, `projectile_motion`.
- **Wave D, entries 14-18:** `constant_force_work`, `fixed_axis_rotation`,
  `horizontal_friction_force`, `impulse_momentum`, `work_energy_speed`.
- **Wave E, entries 20-22:** `spring_energy_speed`, `flat_curve_friction`,
  `banked_curve_no_friction`; deferred entry 19 is skipped.
- **Wave F, entries 25, 26, 27, and 29:**
  `plane_rigid_body_acceleration`, `polar_kinematics`,
  `instant_center_velocity`, `plane_rigid_body_velocity`; deferred entries 23,
  24, and 28 are skipped.

Run focused parity evidence and connected targeted tests for each entry. Run one
fresh independent read-only Checker and release CI only at the end of a complete
wave. Entry 5 retains its historical accepted Checker evidence, but it is not a
Wave A release-CI checkpoint; entries 6 and 7 come next.

For each deferred entry, generic behavior is precise structured unsupported;
generic answer authority is **none** and legacy answer authority is **off-mode
rollback only**. No silent fallback is allowed. Future typed extension remains
preserved without counting any deferred entry as a parity pass or generic
migration. Thus `5/25 accepted + 4 deferred` must never be reported as `9/29`.

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

- Work immediately before this update: accepted `pulley_table_hanging` as
  canonical registry entry 5 at product `7fff1b83...`, then recorded the
  separate authoritative typed scope/runtime amendment child. Entries 1-5 are
  accepted in-scope evidence (`5/25`); this is not a full-wave release claim.
- The typed scope/runtime amendment changes these product paths:
  - `backend/engine/mechanics/__init__.py`
  - `backend/engine/mechanics/compiler/__init__.py`
  - `backend/engine/mechanics/compiler/compiler.py`
  - `backend/engine/mechanics/compiler/contracts.py`
  - `backend/engine/mechanics/migration/__init__.py`
  - `backend/engine/mechanics/migration/contracts.py`
  - `backend/engine/mechanics/migration/parity.py`
  - `backend/engine/mechanics/runtime/__init__.py`
  - `backend/engine/mechanics/runtime/contracts.py`
  - `backend/engine/mechanics/runtime/orchestrator.py`
- It changes these scope-focused test paths:
  - `backend/tests/test_phase56_mechanics_compiler.py`
  - `backend/tests/test_phase56_mechanics_deferred_scope.py`
  - `backend/tests/test_phase56_mechanics_migration_scope.py`
- It changes these authoritative documentation paths:
  - `docs/MECHANICS_LEGACY_MIGRATION.md`
  - `docs/PHASE56_PAUSE_HANDOFF.md`
  The amendment establishes exact typed `29/25/4` accounting, dedicated
  compiler issue codes for all four deferred capabilities, active-mode
  no-delivery runtime enforcement, off-mode-only rollback, adversarial contract
  tests, and the superseding Waves A-F. Its final independent read-only scope
  Checker returned `PASS`, blocking findings `0`, new nonblocking findings `0`.
  The Checker evidence is `236 passed` for the focused compiler/scope/deferred
  runtime/runtime-contract/runtime-static set and `26 passed` for the migration
  harness, with changed-Python `py_compile` and `git diff --check` both clean.
  No release-CI result is attributed to this child.
- W0 production compiler/harness code changed: **NO**. The smallest correction
  was fixture-only in
  `backend/tests/test_phase56_mechanics_migration_harness.py`, plus the precise
  raw-text/evidence distinction in `docs/GENERIC_MECHANICS_IR.md`.
- CI-only files changed after W0 acceptance:
  - `.github/workflows/backend-tests.yml`
  - `scripts/check_backend_fast.sh`
  - `docs/KNOWN_LIMITATIONS.md`
  - `docs/RELEASE_CHECKLIST.md`
- Entry-1 product/test files changed after W0 acceptance:
  - `backend/engine/mechanics/laws/core.py`
  - `backend/tests/test_phase56_mechanics_same_fixture_parity.py`
- Entry-2 product/test files changed after the entry-1 documentation handoff:
  - `backend/engine/mechanics/compiler/compiler.py`
  - `backend/engine/mechanics/laws/core.py`
  - `backend/tests/test_phase56_mechanics_incline_same_fixture_parity.py`
- Entry-3 product/test files changed after the entry-2 documentation handoff:
  - `backend/engine/mechanics/compiler/compiler.py`
  - `backend/engine/mechanics/laws/core.py`
  - `backend/tests/test_phase56_mechanics_incline_friction_same_fixture_parity.py`
- Entry-3 CI remediation touched seven paths total: the entry-3 test path already
  named above plus these six additional paths:
  - `.github/workflows/backend-tests.yml`
  - `docs/KNOWN_LIMITATIONS.md`
  - `docs/RELEASE_CHECKLIST.md`
  - `scripts/check_all.sh`
  - `scripts/check_backend_slow.sh`
  - `scripts/final_local_check.sh`
- Entry-4 product/test work changed exactly these six paths:
  - `backend/engine/mechanics/compiler/compiler.py`
  - `backend/engine/mechanics/laws/core.py`
  - `backend/engine/mechanics/migration/harness.py`
  - `backend/tests/test_phase56_mechanics_atwood_same_fixture_parity.py`
  - `backend/tests/test_phase56_mechanics_compiler.py`
  - `backend/tests/test_phase56_mechanics_migration_harness.py`
- Safe latest accepted product migration unit:
  `7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e` (Entry 5 targeted evidence).
- Safe last exact-head release-CI unit:
  `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9`, run `29841110152` (run #429),
  `SUCCESS`.
- Exact open W0 failure: **NONE**. The formerly failing diagnostic-invariance
  test and all 23 W0 harness tests pass on the authoritative Ubuntu CI runner.
- Immediate next task: create the independent same-fixture parity package for
  canonical registry entry 6, `pulley_incline_hanging`, then entry 7,
  `massive_pulley_atwood`. After both are accepted, run the Wave A family
  Checker and release CI for entries 5-7. Raw text, `system_type`, corpus labels,
  expected answers, and legacy output must not enter the generic calculation
  path.

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

Entry 3 then changed these product/test paths:

```text
M backend/engine/mechanics/compiler/compiler.py
M backend/engine/mechanics/laws/core.py
A backend/tests/test_phase56_mechanics_incline_friction_same_fixture_parity.py
```

The entry-3 CI-remediation child changed seven paths total: the entry-3 test path
already listed above plus these six additional paths:

```text
M .github/workflows/backend-tests.yml
M docs/KNOWN_LIMITATIONS.md
M docs/RELEASE_CHECKLIST.md
M scripts/check_all.sh
A scripts/check_backend_slow.sh
M scripts/final_local_check.sh
```

Entry 4 then changed exactly these product/test paths:

```text
M backend/engine/mechanics/compiler/compiler.py
M backend/engine/mechanics/laws/core.py
M backend/engine/mechanics/migration/harness.py
A backend/tests/test_phase56_mechanics_atwood_same_fixture_parity.py
M backend/tests/test_phase56_mechanics_compiler.py
M backend/tests/test_phase56_mechanics_migration_harness.py
```

Deleted: `NONE`.

Document-only files in the current Stage 5 delta:

- `docs/MECHANICS_LEGACY_MIGRATION.md`
- this handoff document is updated by the final documentation commit.

Test files in the current Stage 5 delta:

- `backend/tests/test_phase56_mechanics_atwood_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_legacy_parity.py`
- `backend/tests/test_phase56_mechanics_migration_harness.py`
- `backend/tests/test_phase56_mechanics_runtime.py`
- `backend/tests/test_phase56_mechanics_runtime_contract.py`
- `backend/tests/test_phase56_mechanics_runtime_static.py`
- `backend/tests/test_phase56_mechanics_incline_friction_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_incline_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_same_fixture_parity.py`

### Complete Phase 56 branch file set relative to Phase 55

At exact-head release-CI checkpoint `dedb4c7...` there are exactly `80` changed
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
A backend/tests/test_phase56_mechanics_atwood_same_fixture_parity.py
A backend/tests/test_phase56_mechanics_incline_friction_same_fixture_parity.py
A backend/tests/test_phase56_mechanics_incline_same_fixture_parity.py
A backend/tests/test_phase56_mechanics_legacy_parity.py
A backend/tests/test_phase56_mechanics_migration_harness.py
A backend/tests/test_phase56_mechanics_modeler.py
A backend/tests/test_phase56_mechanics_normalization.py
A backend/tests/test_phase56_mechanics_numeric_strictness.py
A backend/tests/test_phase56_mechanics_runtime.py
A backend/tests/test_phase56_mechanics_runtime_contract.py
A backend/tests/test_phase56_mechanics_runtime_static.py
A backend/tests/test_phase56_mechanics_same_fixture_parity.py
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
M scripts/check_all.sh
M scripts/check_backend_fast.sh
A scripts/check_backend_slow.sh
M scripts/final_local_check.sh
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
- Typed scope/runtime amendment: independent final `PASS`, blocking `0`, new
  nonblocking `0`; focused compiler/scope/deferred runtime/runtime-contract/
  runtime-static set `236 passed`; migration harness `26 passed`; changed-Python
  `py_compile` and `git diff --check` passed. AST comparison against the parent
  found zero changes to existing compiler/runtime/migration contract fields and
  zero changes to existing version/schema/policy constants. The ordinary
  runtime suite separately reported `87 passed, 2 failed`; both failures were
  the documented Windows default five-second worker-startup timeout, not a
  scope/contract assertion. No release CI is claimed for the amendment.
- Same-fixture registry entry 1, `single_particle_newton`: exact checkpoint
  `8b7c5c4a6f1f972d479323f5a7179b4f177d3800`; `3` focused cases passed. The
  accepted fixture package covers baseline `m,F -> a`, signed multi-force
  balance, ambiguous-direction fail-closed behavior, and diagnostic-label/source
  digest invariance. Generic execution completes before a direct legacy-solver
  observation is constructed; the legacy output has diagnostic authority only.
  Fresh independent final Checker: `PASS`, blocking findings `0`.
- Same-fixture registry entry 2, `incline_no_friction`: exact product/CI checkpoint
  `5e49f2f267c4c8d75aec6e99e3714fc36f700257`, tree
  `9ffbd6cc9bd60e1153891c2b2b7053e2d801a35c`, parent documentation handoff
  `8711b8a328b7334b0545d62f8a2bba6c8317f0b6`, commit
  `feat(mechanics): migrate frictionless incline solver`. The accepted package
  covers typed tangent/normal gravity projection, evidenced frictionless
  touching contact and fixed-surface no penetration, the inclusive incline
  angle domain, 0/90-degree limits, interior down-/up-slope signs, independent
  residuals, angle-domain and gravity-authority negatives, manual typed-payload
  negatives, and diagnostic metadata invariance. Focused: `15 passed`; connected compiler plus
  entry-1 regression: `60 passed`; additional Sol-connected entry-1, migration,
  and legacy runs: `3`, `23`, and `30 passed`. Fresh independent final Checker:
  `PASS`, blocking findings `0`, nonblocking findings `0`.
- Same-fixture registry entry 3, `incline_with_friction`: product code commit
  `d58e2c9bcd8c04c8fa380699e19df6a6c43e7296`, tree
  `72301ea20e43e5310a269dac943fc7d56f01f689`, parent documentation handoff
  `6c53e0fdbbf70854bfec3078d73fb48371fc9a12`, commit
  `feat(mechanics): migrate friction incline solver`; exact successful product/CI
  checkpoint `c134664cd863d33b50c7e5ae794af2ad61ed6524`, tree
  `987cb4ec8b7cbcc321d713313c179e8ca4bcd553`, remediation commit
  `ci: split slow mechanics parity checks`. The common typed graph contains
  tangent/normal gravity projections, fixed-contact no penetration, one normal
  bound, and two particle-Newton equations. Sticking adds two-sided friction
  bounds and zero tangential acceleration with an inclusive hold/slip boundary;
  sliding adds kinetic friction exactly opposite an evidenced positive motion
  carrier. The package proves static hold/boundary and below-boundary rejection,
  sliding/query signs, `mu=0` reduction, exact generic-versus-diagnostic parity,
  independent residuals, metadata invariance, and fail-closed authority,
  structure, evidence, domain, and ambiguity negatives. Focused: `21 passed`;
  entry-2 regression: `15 passed`; connected compiler plus entry-1 regression:
  `60 passed`. Fresh independent entry-3 Checker: `PASS`, blocking findings `0`,
  nonblocking findings `0`. Independent CI-remediation Checker: `PASS`, blocking
  findings `0`, nonblocking findings `0`.
- Same-fixture registry entry 4, `pulley_atwood`: exact product/CI checkpoint
  `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9`, tree
  `dc0e90d954b16a342c16073f2c3021f65da875bf`, parent documentation handoff
  `bd5afe32958ba1ca4efdc5ecc4c22a0ba22fefdd`, commit
  `feat(mechanics): migrate Atwood pulley solver`. The exact evidenced topology
  contains two particles, one rope, one fixed ideal pulley and one gravity
  environment, with two gravity interactions, one wrap, two body attachments,
  taut/fixed state and approved evidenced massless/inextensible/fixed/ideal
  assumptions. The graph law multiset is exactly two `particle_weight`, two
  `particle_newton_second`, one `rope_massless_tension`, and one
  `rope_fixed_pulley_motion`. The package proves baseline B-down and independent
  B-up acceleration signs, direct tension-query parity, equal-mass zero
  acceleration, mass-swap sign reversal with unchanged tension, independent
  Newton/rope residuals, exhaustive symbolic candidates, and diagnostic
  metadata invariance; it freezes the generic result before direct legacy
  diagnostics. Authority inputs are snapshotted once, bounded, and reused for
  all variants; oversized/unstable inputs fail before execution. Structural,
  scope, evidence, assumption, ambiguity, and mass/gravity-domain negatives
  fail closed without a legacy call. Direct core-law tests prove that missing
  ideal authority suppresses fixed-pulley emission. Connected compiler tests
  preserve massive-pulley Newton-Euler/unequal-tension behavior and rigid-body
  fixed-pulley rope laws. Fresh independent final Checker: `PASS`, blocking
  findings `0`.
- Same-fixture registry entry 5, `pulley_table_hanging`: accepted product
  checkpoint `7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e`. The package covers
  explicit no-friction, sliding, sticking, exact static-boundary, `mu=0`, signed
  acceleration, and tension-query cases over the typed table/contact/rope/fixed-
  pulley topology; independent Newton/contact/rope residuals and metadata
  invariance pass, while malformed or missing authority fails closed. Targeted
  fast selection: `45 passed, 9 deselected`; targeted slow selection: `9 passed,
  45 deselected`; compiler regression: `57 passed`. Fresh Entry-5 Checker:
  `PASS`, blocking findings `0`. No release-CI result is attributed to
  `7fff1b83...`; Wave A family release CI waits for entries 6 and 7.
- The local Windows full runs above used only the 20-second worker-startup shim.
  They do not establish that the unchanged default 5-second symbolic and
  verification budgets are green on Windows/Python 3.12; the authoritative
  Ubuntu release run is below.

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

- Exact SHA: `dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9`.
- GitHub Actions release run: `29841110152` (run #429) — `SUCCESS`; its recorded
  head SHA is the exact product checkpoint above, and both backend and frontend
  jobs succeeded.
- Fast wrapper: `2293 passed, 1 skipped, 279 deselected` in `401.95s` under the
  bounded 420-second watchdog.
- Slow-only wrapper: `12 passed, 2561 deselected` in `89.92s` under its bounded
  240-second watchdog; it is disjoint from the fast selection.
- Benchmark wrapper: `147 passed, 2426 deselected` in `63.09s`.
- Audit wrapper: `111 passed, 2462 deselected` in `40.82s`.
- Backend frontend-marker group: `15 passed, 2558 deselected` in `3.46s`.
- The five marker groups have an exact union over the complete `2573`-node
  backend collection. The slow-only selection is disjoint from fast; arithmetic
  addition of all selected counts is not a coverage proof because the existing
  benchmark/audit/frontend markers overlap.
- Frontend unit tests, typecheck, build, and repository metadata: `PASS`.
- Warm latency: mean `13.519858 ms`, p95 `45.878835 ms`, max `60.672493 ms`;
  limits remain 60/120 ms.
- Cold import: `877.46519 ms`; max RSS: `92.656 MB`; limits remain
  5000 ms/512 MB.
- Four-round pooled performance comparison: `PASS`, regressions `0`.
- Entry-4 fresh independent Checker: `PASS`, blocking findings `0`.

### Previous accepted entry-3 release CI

- Exact SHA: `c134664cd863d33b50c7e5ae794af2ad61ed6524`.
- GitHub Actions release run: `29832358480` (run #427) — `SUCCESS`; its recorded
  head SHA is the exact checkpoint above, and both backend and frontend jobs
  succeeded.
- Fast wrapper: `2254 passed, 1 skipped, 273 deselected` in `237.00s` under the
  bounded 420-second watchdog.
- Slow-only wrapper: `6 passed, 2522 deselected` in `35.77s` under its bounded
  240-second watchdog; it is disjoint from the fast selection.
- Benchmark wrapper: `147 passed, 2381 deselected` in `32.31s`.
- Audit wrapper: `111 passed, 2417 deselected` in `22.15s`.
- Backend frontend-marker group: `15 passed, 2513 deselected` in `1.89s`.
- The five marker groups have an exact union over the complete `2528`-node
  backend collection. The slow-only selection is disjoint from fast; arithmetic
  addition of all reported selected counts is not a coverage proof because
  pre-existing benchmark/audit/frontend markers overlap.
- Frontend `44` unit tests, typecheck, build, and repository metadata: `PASS`.
- Warm latency: mean `7.252728 ms`, p95 `29.05428 ms`, max `39.570724 ms`;
  limits remain 60/120 ms.
- Cold import: `491.279975 ms`; max RSS: `90.863 MB`; limits remain
  5000 ms/512 MB.
- Four-round pooled performance comparison: `PASS`, regressions `0`. Registry
  construction reported `+24.678%` but only `+0.00044 ms` and was classified as
  a non-regression; the meaningful positive comparisons were rigid-body
  construction at `+5.731%` and solve at `+5.082%`, both below the unchanged
  `15%` limit.
- The immediately preceding product-code run `29829411846` (run #426) at
  `d58e2c9...` failed only when the 420-second fast watchdog reached 82% progress;
  it reported no assertion failure. The remediation split six marked slow tests
  into the bounded 240-second slow lane without changing the 420-second fast
  watchdog or test semantics.
- Entry-3 fresh independent Checker: `PASS`, blocking findings `0`, nonblocking
  findings `0`. CI-remediation Checker: `PASS`, blocking findings `0`,
  nonblocking findings `0`.

### Still not run

- Stage 5 in-scope same-fixture parity: `5/25` accepted; `20/25` pending.
  Deferred scope is exactly `4/4` classified and does not count as parity.
- Stage 6 figure/UI tests: `NOT RUN`.
- Stage 7 corpus/compositional/synthetic tests: `NOT RUN`.
- Stage 8 final exact-head CI/Checker for completed Stages 5-7: `NOT RUN`.
- Stage 9 Live: `NOT RUN`.

`STAGE5_ENTRY_5_TARGETED_ACCEPTED_SCOPE_AMENDED`: product `7fff1b83...`
contains accepted same-fixture entries 1-5, and the branch head adds the separate
typed scope/runtime amendment child. This is `5/25` accepted in-scope evidence,
with `20/25` pending and four explicitly deferred. It is not `9/29`, not a
`29/29` generic-migrated claim, not a Wave A family release-CI checkpoint, and
not a Phase 56 completion claim. Stages 6-9 and Stage 5 product integration
remain incomplete.

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
  integration. For pending in-scope entries, legacy remains the explicit `off`
  rollback and `shadow` visible path until migration gates pass. Deferred entries
  are narrower: structured unsupported generically and off-mode rollback only,
  never silent fallback or generic answer authority.

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

- Per-solver accepted evidence is `5/25` in scope; compiler unit fixtures do not
  count as same-fixture end-to-end parity for the pending `20/25`. The four
  deferred entries are classified, not accepted.
- Entry 6, `pulley_incline_hanging`, is next, followed by Entry 7,
  `massive_pulley_atwood`; Wave A family Checker/release CI runs only after both.
- The deferred set is exactly `spring_mass_vibration`,
  `relative_acceleration_translation`, `coriolis_relative_motion`, and
  `slot_pin_relative_motion`. Their current generic result must remain precise
  structured unsupported, with no generic answer authority, off-mode legacy
  rollback only, and no silent fallback. Future extension remains possible.
- `polar_kinematics` is in-scope Wave F, not deferred. Its typed graph law, full
  rigid acceleration, and event-root coverage remain active coverage risks.
- Product integration is absent. `/solve` and `/diagnose` still need one serial
  owner to prevent legacy route/FBD/equation leakage on generic blocked states.
- `MechanicsModelerConfig.from_env()` currently collapses disabled requested modes
  to `off`; required-disabled fail-closed behavior must be repaired at integration.
- Phase 55 parser plus Mechanics modeler dual-call exclusion is designed but not
  wired.
- Generic vector-answer projection into the existing product response is not
  decided; it must never silently fall back to a legacy scalar answer.
- Five-group marker-union coverage is exact at `dedb4c7...`; the dedicated
  bounded slow-only group is present and disjoint from the fast selection, as
  documented in `docs/KNOWN_LIMITATIONS.md`.
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
5. Confirm exact-head release-CI checkpoint `dedb4c7...`, run `29841110152`
   (run #429), remains successful. Separately confirm Entry-5 product
   `7fff1b83...` and the later typed scope/runtime amendment child; do not attribute release CI
   to either later SHA.
6. Do not repeat Stages 0-4 or the accepted Stage 5 matrix/parity/runtime/W0/
   accepted entries 1-5 reviews.
7. Start canonical registry entry 6, `pulley_incline_hanging`, then Entry 7,
   `massive_pulley_atwood`, following their matrix rows and typed authority
   boundaries.
8. Run only focused fixture/harness and connected accepted regressions for each
   entry, then run one fresh independent read-only Wave A Checker and release CI
   once entries 5-7 are complete.
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
Previous accepted Stage-4 targeted-test SHA: c19624181aaae4cd73dc3d2247b4988f5a540247
Latest entry-3 product code SHA: d58e2c9bcd8c04c8fa380699e19df6a6c43e7296
Latest entry-3 product tree: 72301ea20e43e5310a269dac943fc7d56f01f689
Latest entry-4 product SHA: dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9
Latest entry-4 product tree: dc0e90d954b16a342c16073f2c3021f65da875bf
Latest entry-5 product/same-fixture SHA: 7fff1b83f42ed5f1ddf6046f456b2c9f924cb54e
Current branch head: separate typed scope/runtime amendment child of 7fff1b83... (verify exact SHA)
Latest release-validated migration tree: dc0e90d954b16a342c16073f2c3021f65da875bf
Latest exact-head release-CI SHA: dedb4c7c773bf24bc27038b0d5d5f658e5d28ba9
Latest exact-head release run: 29841110152 (run #429), SUCCESS
Resume Stage: Stage 5 IN_PROGRESS, inventory 29/29 classified, in-scope parity 5/25 accepted and 20/25 pending, deferred 4/4 explicit

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
11) backend/engine/mechanics/compiler/contracts.py
12) backend/engine/mechanics/compiler/compiler.py
13) backend/engine/mechanics/runtime/contracts.py
14) backend/engine/mechanics/runtime/orchestrator.py
15) backend/tests/test_phase56_mechanics_migration_scope.py
16) backend/tests/test_phase56_mechanics_deferred_scope.py

The old laptop-local work ledger may be absent. Do not treat that as a blocker;
this handoff is authoritative. Follow Master Instruction v2 and the user's
Sol-Terra-Luna operating rules. Do not repeat accepted Stages 0-4 or accepted
Stage 5 matrix/parity/runtime/W0 packages.

Entry 5 `pulley_table_hanging` is accepted at product `7fff1b83...` with targeted
fast `45 passed / 9 deselected`, slow `9 passed / 45 deselected`, compiler
evidence `57 passed`, and Checker blocking findings `0`. It has no new release-CI
claim.

Next exact task: implement canonical registry entry 6
`pulley_incline_hanging`, then Entry 7 `massive_pulley_atwood`. Run their focused
parity evidence and connected targeted tests, then one fresh independent
read-only Wave A Checker and release CI once entries 5-7 are complete.
Raw text, `system_type`, corpus/family/case metadata, expected answers, and legacy
output must not enter generic compilation, solving, verification, or selection.

Authoritative scope: 25 in scope; deferred exact entries 19
`spring_mass_vibration`, 23 `relative_acceleration_translation`, 24
`coriolis_relative_motion`, and 28 `slot_pin_relative_motion`; Entry 26
`polar_kinematics` is in scope. Deferred means structured unsupported, no generic
answer authority, off-mode rollback only, and no silent fallback. Never report
the state as 9/29 or 29/29 generic migrated.

Keep the public corpus sealed until Stage 7. The Beer PDF is reference-only for
Dynamics Chapters 11-19 structure and permitted later figure/coverage work; it is
never a runtime or exact-answer oracle. Private held-out and actual Korean/SI
exact-match evaluation remain NOT RUN.

Do not merge PR #16/#17, undraft, push main, force-push, rebase, deploy, change
production/environment values, access API keys, incur Live cost, or commit corpus,
private, or textbook assets. Apart from a hard blocker or an action requiring new
authority, continue without intermediate confirmation.
```
