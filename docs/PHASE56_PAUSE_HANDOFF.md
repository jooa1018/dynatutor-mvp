# Phase 56 Cross-Device Resume Handoff

## Remote integration acceptance — 2026-07-23 Asia/Seoul

This is the current authoritative checkpoint. The local archive-candidate
checkpoint below is preserved as historical provenance only.

- Branch / PR: `codex/phase56-generic-mechanics-engine`, PR #17 is **Draft,
  open, and unmerged**, stacked on Draft PR #16.
- Entries 11–18 are accepted as generic same-fixture migrations. The
  authoritative in-scope count is **18/25**; **7/25** remain. The four deferred
  entries and their policy remain unchanged.
- Wave C exact release head: `67f46e9c84a658d1d5a50b9dfcdce81f78f20d8d`;
  GitHub Actions run #439 (`29944965150`): **SUCCESS**.
- Wave D exact release head: `34208235fabed97cc7a500668c13f5a4cf5a109d`;
  GitHub Actions run #440 (`29947470482`): **SUCCESS**.
- Local focused evidence for Entries 11–18: **136 fast + 48 slow = 184
  passed**. The final connected Phase 56 selection: **1,019 passed, 1
  skipped**.
- Wave D release evidence: fast **2,902 passed, 1 skipped**; slow **128
  passed** across 16 file shards; benchmark **147 passed**; audit **111
  passed**; backend `frontend` marker **15 passed**; frontend **44/44**,
  typecheck, and build all passed.
- Release budgets passed: warm solve mean/p95/max **12.244836 / 40.609637 /
  55.325761 ms** (budgets 60/120 ms); cold import **790.399726 ms** (budget
  5000 ms); RSS **92.711 MB** (budget 512 MB). Four-round pooled comparison
  passed with zero regressions (largest p95 change 1.048%, limit 15%).
- A separate read-only Checker found **0 blocking** findings. Its nonblocking
  note is that the release-job timeout was raised from 20 to 30 minutes so the
  existing full slow and four-round performance gates can finish; no test
  selection, assertion, or performance threshold was relaxed.


## Local Entries 11–18 candidate checkpoint — 2026-07-22 Asia/Seoul

This packaged checkpoint was produced from source archive snapshot
`202912edb5a4db0781d4f40abad345441fc5cf71`, which did not include Git
metadata. It therefore records local
candidate validation only and does not replace GitHub exact-head release
evidence.

- Local product commit: `c0909da336b4723012199f53d6be04bb0e19f8ce`.
- Entry 11 through Entry 18 focused evidence: **184 passed**
  (**136 fast**, **48 slow**).
- Connected backend evidence: **960 passed, 1 skipped**; backend
  `frontend`-marker evidence: **15 passed**.
- Static authority audit, `py_compile`, `git diff --check`, warm/cold performance,
  and same-model read-only audit passed with blocking findings **0**.
- Frontend dependency installation was blocked by package-gateway HTTP 503; the
  result is `FRONTEND_DEPENDENCY_BLOCKED`, not a frontend product failure and not
  a frontend PASS.
- Local disposition: `LOCAL_CANDIDATE_VALIDATED / REMOTE_RELEASE_PENDING`.
- The authoritative accepted count remains **10/25**. It may advance to **18/25**
  only after application to the real branch, Python 3.11/Node 20 gates, exact-head
  Wave C and Wave D release CI, and a fresh independent read-only Checker.
- Detailed evidence: `docs/PHASE56_LOCAL_ENTRIES11_18_VALIDATION.md`.
- The older emergency Entry 11 resume text below remains preserved as historical
  remote-handoff evidence; it is superseded only for this local packaged tree.

This is the cumulative authoritative cross-device handoff for the Phase 56
branch. The emergency checkpoint below is the newest state and supersedes older
current-state wording later in this document while preserving all historical
evidence and exact attribution.

## Emergency Claude Code checkpoint — 2026-07-22 Asia/Seoul

- Repository/branch: `jooa1018/dynatutor-mvp`,
  `codex/phase56-generic-mechanics-engine`.
- Current stage: Stage 5 `IN_PROGRESS`.
- Current wave/entry: Wave C / Entry 11 `collision_1d`,
  `LOCAL_WIP / PARTIALLY_TESTED`; Entry 11 is **not accepted**.
- Latest product code SHA:
  `a31018bfd13df4a87eb1b198881bb63a2b79c9a1` (tree
  `e4a6f9d28fcbee93dd065d6fb2697383fe332833`), commit
  `wip(phase56): checkpoint Wave C for Claude Code handoff`.
- Latest tested product code SHA:
  `a31018bfd13df4a87eb1b198881bb63a2b79c9a1`, status
  `PARTIALLY_TESTED`. Changed-file `py_compile`, two direct collision compiler
  regressions, and `git diff --check` passed on the committed tree. Focused fast
  evidence was `47 passed, 12 deselected` in `81.16s` on the same product code;
  the test file subsequently received only a slow-only enum assertion fix.
- Latest accepted product code SHA:
  `dba0016ec9878d40e1ed6edf60106491848b3956` (Entry 10,
  `vertical_circle`).
- Latest accepted integrated release head remains
  `305c68d6e7173740d478fd41c11b4ae78a245469` (tree
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`), Wave B GitHub Actions run
  `29879344293` (run #434), `SUCCESS`; independent Checker `PASS`, blocking `0`,
  nonblocking `0`. This evidence does not apply to Entry 11 or later docs.
- Accepted in-scope count remains `10/25`; remaining in-scope count remains
  `15/25`. The registry remains `29/29 classified`, with exactly `4/4` deferred:
  Entry 19 `spring_mass_vibration`, Entry 23
  `relative_acceleration_translation`, Entry 24
  `coriolis_relative_motion`, and Entry 28 `slot_pin_relative_motion`. Entry 26
  `polar_kinematics` remains in scope.
- Partial implementation exists in four product files plus one new focused test:
  `backend/engine/mechanics/compiler/compiler.py`,
  `backend/engine/mechanics/laws/core.py`,
  `backend/engine/mechanics/solver/contracts.py`,
  `backend/engine/mechanics/solver/planner.py`, and
  `backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py`.
- Known current failure: `NONE`. Verification gap: the first 12-case slow run
  failed only at a test assertion using nonexistent `DifferentialStatus.parity`;
  the committed file corrects it to `DifferentialStatus.full_parity`, but the
  final post-fix slow rerun result was not captured and is `UNKNOWN`.
- Next exact task: on the final handoff checkout, rerun the entire 12-case slow
  selection for
  `backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py`.
  Do not edit first; if it passes, run focused fast/direct regressions and finish
  Entry 11 acceptance evidence. Do not start Entry 12 before Entry 11 is a
  cohesive accepted atomic unit.
- Claude Code execution handoff:
  `docs/PHASE56_CLAUDE_CODE_HANDOFF.md`.
- `FINAL_HANDOFF_HEAD = branch head containing the two emergency handoff
  documents`; the exact SHA is reported in the final handoff response and must be
  verified against the remote branch.
- PR body finalization occurs only after the handoff commit is pushed. If the PR
  does not contain the emergency checkpoint summary, treat it as
  `PR_BODY_UPDATE_NOT_RUN` and rely on the two repository handoff documents.
- No new Entry, Wave, feature, full CI, release CI, Live evaluation, corpus
  evaluation, or large independent Checker was started after the stop order.

The remaining sections retain the cumulative Stage 0-9 history. Any later text
saying that Wave C has not started or that Entry 11 is merely “next” is historical
and is superseded by this emergency checkpoint. The same applies to older
current-state wording in `docs/MECHANICS_LEGACY_MIGRATION.md`; its accepted
classification/evidence is preserved. This remains a pause record, not an
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
- Latest Entry-6 product/same-fixture migration checkpoint:
  `f3e747b4480f98223c113170181698c8b4822e84`.
- Latest Entry-7 product/same-fixture migration checkpoint:
  `26434fc5edc25d617724c8352d1643a40b555f13`.
- Latest locally accepted Entry-7 documentation checkpoint before this handoff
  remediation: `bb890ea82a9271ceae23491472ea55a9c8ba2fdf`.
- Accepted Wave-A release checkpoint:
  `8f18c710fc6d5d730fcceccfb30e3175c2613902` (tree
  `5770597d55158d9634d90101451977ebc226d83c`, GitHub Actions run
  `29865756663`, run #433, `SUCCESS`).
- Latest accepted Entry-8 product/same-fixture migration checkpoint:
  `af4b83ff6bde1d577b76ece3191e5b0e5b60d8af` (tree
  `c60ab8ab918dc1078e3faed2ca5d44212e5b85bb`, parent
  `8f18c710fc6d5d730fcceccfb30e3175c2613902`).
- Latest accepted Entry-9 product/same-fixture migration checkpoint:
  `2a870ec4808b6301e39bb99f446b457abc5458a5` (tree
  `9430a179e8e79322b1d49d2b53ed3b68a57f4a64`, parent Entry-8 documentation
  checkpoint `dbad228948c82809e854b0f9cf0f97bef9b998ea`).
- Latest accepted Entry-10 product/same-fixture migration checkpoint:
  `dba0016ec9878d40e1ed6edf60106491848b3956` (tree
  `7d02c784030e32e9d4fc08b22f76ecd8e93fbc1f`, parent Entry-9 documentation
  checkpoint `97545c02b53eea82e2951a8f1c81ebe2f3518cf8`, commit
  `feat(mechanics): migrate vertical circle solver`).
- Accepted integrated Wave-B release checkpoint:
  `305c68d6e7173740d478fd41c11b4ae78a245469` (tree
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`, GitHub Actions run
  `29879344293`, run #434, `SUCCESS`).
- Exact release-validated branch head before this documentation-only handoff:
  `305c68d6e7173740d478fd41c11b4ae78a245469`.
- Latest release-validated migration tree:
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`.
- Latest exact-head release-CI checkpoint:
  `305c68d6e7173740d478fd41c11b4ae78a245469`.
- `HANDOFF_COMMIT_SHA = branch head containing this file`
- Run #434 validates only the integrated `305c68d...` / `dd63dd58...` release
  object. It is not attributed to Entry 8 at `af4b83ff...`, Entry 9 at
  `2a870ec...`, Entry 10 at `dba0016e...`, or the later documentation-only
  handoff commit containing this update.
- PR #17 base: `codex/phase55-gpt-first-textbook-parser` at
  `4762727e8f9191604e2531b9982a5ae72ed73db9`
- PR #17 exact release-validated remote head:
  `305c68d6e7173740d478fd41c11b4ae78a245469`; re-query before relying on any
  later remote state. The individual Entry-8/9/10 product commits are not the
  run #434 release head.
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
- Latest exact-head Wave-B release-CI checkpoint:
  `305c68d6e7173740d478fd41c11b4ae78a245469` (tree
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`, run `29879344293`, run #434,
  `SUCCESS`).
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
    blocking findings `0`. This remains the historical Entry-5 checkpoint; no
    Wave A release-CI result is attributed to it.
  - canonical registry entry 6, `pulley_incline_hanging`, at accepted product
    checkpoint `f3e747b4480f98223c113170181698c8b4822e84`. Its exact typed
    incline/contact/rope topology covers frictionless, sticking, sliding,
    direction, static-boundary, acceleration, and tension cases without using
    metadata, raw text, or legacy output as authority. Focused evidence is fast
    `39 passed, 16 deselected`, complete slow `16 passed`, compiler `57 passed`,
    and an independent Checker with blocking findings `0`.
  - canonical registry entry 7, `massive_pulley_atwood`, at accepted product
    checkpoint `26434fc5edc25d617724c8352d1643a40b555f13`. Its global exact
    typed inventory emits ten equations with unequal segment tensions,
    no-slip acceleration, and Newton-Euler rotation; ideal equal-tension and
    generic fixed-pulley emissions are suppressed. Focused evidence is fast
    `68 passed, 9 deselected`, complete slow `9 passed`, compiler `57 passed`,
    and an independent Entry-7 Checker with blocking and nonblocking findings
    both `0`.
  - canonical registry entry 8, `pure_rolling_energy`, at accepted product
    checkpoint `af4b83ff6bde1d577b76ece3191e5b0e5b60d8af` (tree
    `c60ab8ab918dc1078e3faed2ca5d44212e5b85bb`, parent Wave-A release head
    `8f18c710fc6d5d730fcceccfb30e3175c2613902`). Its exact typed contract binds
    a rigid body, fixed incline, center-of-mass/contact geometry, gravity/contact
    interactions, initial/final rolling states, no slip, no energy loss, and one
    approved/evidenced shape assumption. The six admitted shapes derive inertia
    from `I=beta*m*R^2`; source inertia and non-final-speed queries fail closed.
    Final local evidence is fast `40 passed, 12 deselected`, slow `12 passed,
    40 deselected` in `148.68s`, compiler/solver/planner/verification regression
    `144 passed`, and connected Entries 4-7 fast regression `188 passed,
    40 deselected`. The independent integrated Entry-8 Checker returned `PASS`,
    blocking findings `0`, nonblocking findings `0`. No release CI is attributed
    to this Entry-8 product checkpoint.
  - canonical registry entry 9, `rolling_energy_general`, at accepted product
    checkpoint `2a870ec4808b6301e39bb99f446b457abc5458a5` (tree
    `9430a179e8e79322b1d49d2b53ed3b68a57f4a64`, parent Entry-8 documentation
    checkpoint `dbad228948c82809e854b0f9cf0f97bef9b998ea`). Its exact typed
    contract binds one rigid body, one fixed incline, center-of-mass/contact
    geometry, gravity/contact interactions, initial/final rolling states, no
    slip, no energy loss, and an explicit positive finite center-of-mass inertia.
    It emits the principal result `vf=sqrt(v0^2+2*m*g*h/(m+I/R^2))`; only final
    nonnegative center-of-mass scalar speed is a valid query. Shape authority,
    source-inertia/shape conflicts, malformed topology, unsupported internal
    queries, missing authority, and invalid domains fail closed. Damaging the
    rigid-body primitive fails closed for final-speed, mass, and source-inertia
    queries rather than escaping to a broad path. Final core fast evidence is
    `294 passed, 22 deselected`; the complete Entry-9 slow matrix is `10 passed,
    60 deselected` in `84.11s`. Two independent Checkers returned `PASS`, each
    with blocking findings `0` and nonblocking findings `0`; `py_compile` and
    `git diff --check` passed, and the Entry-8 fingerprint remained unchanged.
    No release CI is attributed to this Entry-9 product checkpoint.
  - canonical registry entry 10, `vertical_circle`, at accepted product
    checkpoint `dba0016ec9878d40e1ed6edf60106491848b3956` (tree
    `7d02c784030e32e9d4fc08b22f76ecd8e93fbc1f`, parent Entry-9 documentation
    checkpoint `97545c02b53eea82e2951a8f1c81ebe2f3518cf8`, commit
    `feat(mechanics): migrate vertical circle solver`). Its narrow typed contract
    recognizes the exact particle/circular-path/radial-frame topology
    independently of the query, with an evidenced top or bottom state and either
    a rope or touching contact. It emits top/bottom rope tension or contact normal
    `C=m(v^2/R∓g)` and the top minimum-speed result `v_min=sqrt(gR)`. Contact
    loss fails closed, the exact zero boundary uses a relative epsilon, and
    derived overflow, underflow, and subnormal values are fenced. It introduces
    no hidden gravity default or clamp. The direct legacy call is diagnostic only;
    contact parity is numeric-only. The focused file collects `79` tests (`67`
    fast, `12` slow). Root's final connected fast selection reports `361 passed,
    34 deselected`; the final slow matrix reports `12 passed` in `105.20s`. Two
    independent Entry-10 Checkers returned `PASS`, each with blocking findings
    `0` and nonblocking findings `0`; `py_compile`, diff, and whitespace checks
    passed. No release CI is attributed to this Entry-10 product checkpoint.
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
    accepted in-scope evidence is `10/25`, with `15/25` pending;
  - Waves A-F remain active under the superseding typed scope plan; Wave A is
    release-accepted, and Wave B Entries 8-10 plus their integrated wave gate are
    release-accepted at `305c68d...`, run #434; Wave C has not started;
  - product `/solve` and `/diagnose` integration, required-disabled config edge,
    dual-model exclusion, API schema/route tests, and vector-answer projection.
- Current failure/blocker: none at the accepted `10/25` in-scope boundary. Wave B
  passed its independent Checker (`PASS`, blocking `0`, nonblocking `0`) and
  exact-head release CI at `305c68d...`, run `29879344293` (run #434,
  `SUCCESS`).
- Next gate: implement focused same-fixture migration evidence for Entry 11,
  `collision_1d`, the first Wave C entry.

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
wave. Wave A passed that gate at `8f18c710...`, run #433. Wave B Entries 8-10
passed that gate at `305c68d6e7173740d478fd41c11b4ae78a245469` (tree
`dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`), run `29879344293` (run #434,
`SUCCESS`), after the Wave-B Checker returned `PASS`, blocking `0`, nonblocking
`0`. Wave C begins with Entry 11, `collision_1d`.

For each deferred entry, generic behavior is precise structured unsupported;
generic answer authority is **none** and legacy answer authority is **off-mode
rollback only**. No silent fallback is allowed. Future typed extension remains
preserved without counting any deferred entry as a parity pass or generic
migration. Accepted and deferred counts must never be added or reported as a
generic-migration total.

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

- Work immediately before this update: accepted the integrated Wave-B release
  gate at exact head `305c68d6e7173740d478fd41c11b4ae78a245469`, tree
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`, run `29879344293` (run #434,
  `SUCCESS`), after the independent Wave-B Checker returned `PASS`, blocking
  findings `0`, nonblocking findings `0`. Entries 1-10 are accepted in-scope
  evidence (`10/25`). The release result belongs only to the integrated exact
  head, not to the individual Entry-8/9/10 product commits.
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
- The accepted Wave-A release remediation changed only
  `scripts/check_backend_slow.sh`, sharding the unchanged slow selection by its
  five discovered test files under the unchanged per-file 240-second bound.
- Entry-8 product/test work changed exactly these five paths:
  - `backend/engine/mechanics/compiler/compiler.py`
  - `backend/engine/mechanics/laws/core.py`
  - `backend/engine/mechanics/solver/_audit.py`
  - `backend/engine/mechanics/solver/contracts.py`
  - `backend/tests/test_phase56_mechanics_pure_rolling_same_fixture_parity.py`
- Entry-9 product/test work changed exactly these three paths:
  - `backend/engine/mechanics/compiler/compiler.py`
  - `backend/engine/mechanics/laws/core.py`
  - `backend/tests/test_phase56_mechanics_rolling_general_same_fixture_parity.py`
- Entry-10 product/test work changed exactly these three paths:
  - `backend/engine/mechanics/compiler/compiler.py`
  - `backend/engine/mechanics/laws/core.py`
  - `backend/tests/test_phase56_mechanics_vertical_circle_same_fixture_parity.py`
- Safe latest individual product migration unit:
  `dba0016ec9878d40e1ed6edf60106491848b3956` (Entry 10 targeted evidence only).
- Safe latest integrated exact-head release-CI unit:
  `305c68d6e7173740d478fd41c11b4ae78a245469`, tree
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`, run `29879344293` (run #434),
  `SUCCESS`. No release result is attributed to `af4b83ff...`, `2a870ec...`,
  `dba0016e...`, or the later docs-only handoff commit.
- Exact open W0 failure: **NONE**. The formerly failing diagnostic-invariance
  test and all 23 W0 harness tests pass on the authoritative Ubuntu CI runner.
- Immediate next task: implement Entry 11, `collision_1d`, as the first Wave C
  same-fixture migration package. Raw text,
  `system_type`, corpus labels, expected answers, and legacy output must not
  enter the generic calculation path.

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

### Initial Stage 5 implementation after the accepted Stage 4 checkpoint

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
- `backend/tests/test_phase56_mechanics_table_hanging_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_incline_hanging_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_massive_pulley_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_pure_rolling_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_rolling_general_same_fixture_parity.py`
- `backend/tests/test_phase56_mechanics_vertical_circle_same_fixture_parity.py`

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
  `7fff1b83...`; this is historical Entry-5 evidence. At that checkpoint Entries
  6-7 and the combined Wave-A gate were still pending; they later passed.
- Complete Wave A, Entries 5-7: independent family Checker `PASS`, blocking
  findings `0`. Exact release checkpoint
  `8f18c710fc6d5d730fcceccfb30e3175c2613902` (tree
  `5770597d55158d9634d90101451977ebc226d83c`), GitHub Actions run
  `29865756663` (run #433), `SUCCESS`. Backend fast reported `2599 passed,
  1 skipped, 313 deselected`; the 46 slow tests ran in five file shards of
  `6/6/16/9/9`, each under 240 seconds. Benchmark `147`, audit `111`, backend
  frontend-marker `15`, compile/metadata/warm/cold budgets, frontend tests,
  typecheck, and build all passed. The four-round pooled comparison passed with
  no regressions.
- Same-fixture registry entry 8, `pure_rolling_energy`: accepted product
  checkpoint `af4b83ff6bde1d577b76ece3191e5b0e5b60d8af`, tree
  `c60ab8ab918dc1078e3faed2ca5d44212e5b85bb`, parent `8f18c710...`.
  Final focused selection: fast `40 passed, 12 deselected`; slow `12 passed,
  40 deselected` in `148.68s`. Compiler/solver/planner/verification regressions
  reported `144 passed`; connected Entries 4-7 fast regressions reported
  `188 passed, 40 deselected`. Fresh integrated Checker: `PASS`, blocking
  findings `0`, nonblocking findings `0`. This is local Entry-8 evidence, not a
  release-CI result.
- Same-fixture registry entry 9, `rolling_energy_general`: accepted product
  checkpoint `2a870ec4808b6301e39bb99f446b457abc5458a5`, tree
  `9430a179e8e79322b1d49d2b53ed3b68a57f4a64`, parent `dbad228...`.
  Final core fast regression selection reported `294 passed, 22 deselected`; the
  complete Entry-9 slow matrix reported `10 passed, 60 deselected` in `84.11s`.
  Two independent Checkers returned `PASS`, each with blocking findings `0` and
  nonblocking findings `0`. Damaged rigid-body primitive cases for final-speed,
  mass, and source-inertia queries all fail closed; the Entry-8 fingerprint is
  unchanged. `py_compile` and `git diff --check` passed. This is local Entry-9
  evidence, not a release-CI result.
- Same-fixture registry entry 10, `vertical_circle`: accepted product checkpoint
  `dba0016ec9878d40e1ed6edf60106491848b3956`, tree
  `7d02c784030e32e9d4fc08b22f76ecd8e93fbc1f`, parent `97545c02...`. The
  focused file collects `79` tests (`67` fast, `12` slow). Root's final connected
  fast selection reported `361 passed, 34 deselected`; the final Entry-10 slow
  matrix reported `12 passed` in `105.20s`. Two independent Entry-10 Checkers
  returned `PASS`, each with blocking findings `0` and nonblocking findings `0`.
  Query-independent exact topology, contact-loss fail-closed behavior, the
  relative-epsilon exact-zero boundary, derived numeric fences, no hidden gravity
  default/clamp, diagnostic-only direct legacy use, and numeric-only contact
  parity were verified. `py_compile`, `git diff --check`, and whitespace checks
  passed. This is local Entry-10 evidence, not a release-CI result.
- Complete Wave B, Entries 8-10: independent Wave-B Checker `PASS`, blocking
  findings `0`, nonblocking findings `0`. Exact integrated release checkpoint
  `305c68d6e7173740d478fd41c11b4ae78a245469` (tree
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`), GitHub Actions run
  `29879344293` (run #434), `SUCCESS`. The exact backend, frontend, metadata, and
  performance evidence is recorded below. This gate validates only that
  integrated head/tree, not the three individual Entry product commits or the
  later documentation-only handoff commit.
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

- Exact SHA: `305c68d6e7173740d478fd41c11b4ae78a245469` (tree
  `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`).
- Formal PR GitHub Actions release run: `29879344293` (run #434) — `SUCCESS`;
  its recorded head SHA is exact, and both backend and frontend jobs succeeded.
- Compile: `SUCCESS`.
- Fast wrapper: `2766 passed, 1 skipped, 347 deselected` in `400.86s`.
- Slow wrapper: `80 passed` across eight file shards, all under the unchanged
  240-second per-file bound:
  - Atwood: `6 passed, 36 deselected` in `30.44s`;
  - incline friction: `6 passed, 15 deselected` in `57.67s`;
  - incline hanging: `16 passed, 39 deselected` in `209.20s`;
  - massive pulley: `9 passed, 68 deselected` in `44.83s`;
  - pure rolling: `12 passed, 40 deselected` in `44.08s`;
  - rolling general: `10 passed, 60 deselected` in `36.94s`;
  - table hanging: `9 passed, 45 deselected` in `41.37s`;
  - vertical circle: `12 passed, 67 deselected` in `44.01s`.
- Benchmark wrapper: `147 passed, 2967 deselected` in `62.61s`.
- Audit wrapper: `111 passed, 3003 deselected` in `40.22s`.
- Backend frontend-marker group: `15 passed, 3099 deselected` in `3.40s`.
- Repository metadata: `PASS`.
- Warm latency: mean `13.220340 ms`, p95 `44.802869 ms`, max `59.695984 ms`;
  the unchanged mean/p95 budgets are `60/120 ms`, so this passed.
- Cold import: `853.722429 ms`; max RSS: `92.723 MB`; the unchanged limits are
  `5000 ms/512 MB`, so this passed.
- Frontend unit tests: `44/44`; typecheck and build: `PASS`.
- Four-round pooled performance comparison: 60 repeats per revision per round,
  240 samples per metric per revision; `passed=true`, regressions `0`.
- Independent Wave-B Checker: `PASS`, blocking findings `0`, nonblocking
  findings `0`.
- Exact attribution guard: run #434 validates only SHA `305c68d...` and tree
  `dd63dd58...`. It is not attributed to the individual Entry-8
  `af4b83ff...`, Entry-9 `2a870ec...`, or Entry-10 `dba0016e...` product commits,
  and it does not validate the later documentation-only handoff commit.

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

- Stage 5 in-scope same-fixture parity: `10/25` accepted; `15/25` pending.
  Deferred scope is exactly `4/4` classified and does not count as parity.
- Stage 6 figure/UI tests: `NOT RUN`.
- Stage 7 corpus/compositional/synthetic tests: `NOT RUN`.
- Stage 8 final exact-head CI/Checker for completed Stages 5-7: `NOT RUN`.
- Stage 9 Live: `NOT RUN`.

`STAGE5_WAVE_B_RELEASE_ACCEPTED_WAVE_C_ENTRY11_NEXT`: integrated release head
`305c68d6e7173740d478fd41c11b4ae78a245469` (tree
`dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`) contains accepted same-fixture
entries 1-10 and passed run `29879344293` (run #434, `SUCCESS`) plus the
independent Wave-B Checker (`PASS`, blocking `0`, nonblocking `0`). This remains
`10/25` accepted in-scope evidence, with `15/25` pending and four explicitly
deferred. Run #434 is attributed only to the integrated release head, not the
individual Entry-8/9/10 commits or this later docs-only handoff. The next exact
task is Entry 11, `collision_1d`, beginning Wave C. This is not a `29/29`
generic-migrated claim or a Phase 56 completion claim. Stages 6-9 and Stage 5
product integration remain incomplete.

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

- Per-solver accepted evidence is `10/25` in scope; compiler unit fixtures do not
  count as same-fixture end-to-end parity for the pending `15/25`. The four
  deferred entries are classified, not accepted.
- Wave A entries 5-7 and their exact-head release gate are accepted at
  `8f18c710...`, run #433. Wave B Entries 8-10 and their integrated gate are
  release-accepted at `305c68d...` / `dd63dd58...`, run #434; the Wave-B Checker
  passed with blocking and nonblocking findings both `0`. Entry 11,
  `collision_1d`, has not started and is next as the first Wave C task.
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
- The latest release gate at `305c68d...` passed compile; backend fast
  (`2766 passed, 1 skipped, 347 deselected` in `400.86s`); all `80` slow tests
  sharded by eight files under the 240-second per-file bound; benchmark, audit,
  frontend-marker, metadata, warm/cold budgets; frontend `44/44`, typecheck and
  build; and the four-round pooled comparison with regressions `0`.
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
5. Confirm exact integrated Wave-B release checkpoint `305c68d...`, tree
   `dd63dd58...`, run `29879344293` (run #434), remains successful. Separately
   confirm the Entry-8, Entry-9, and Entry-10 products `af4b83ff...`,
   `2a870ec...`, and `dba0016e...`; do not attribute run #434 to those individual
   commits or to the later documentation-only handoff commit.
6. Do not repeat Stages 0-4 or the accepted Stage 5 matrix/parity/runtime/W0/
   accepted entries 1-10 reviews.
7. Confirm the independent Wave-B Checker verdict is `PASS`, blocking findings
   `0`, nonblocking findings `0`; do not repeat that accepted gate.
8. Begin Entry 11, `collision_1d`, as the first Wave C focused same-fixture
   migration package.
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
Latest entry-6 product/same-fixture SHA: f3e747b4480f98223c113170181698c8b4822e84
Latest entry-7 product/same-fixture SHA: 26434fc5edc25d617724c8352d1643a40b555f13
Latest Entry-7 documentation checkpoint before Checker remediation: bb890ea82a9271ceae23491472ea55a9c8ba2fdf
Accepted Wave-A release SHA: 8f18c710fc6d5d730fcceccfb30e3175c2613902
Accepted Wave-A release tree: 5770597d55158d9634d90101451977ebc226d83c
Accepted integrated Wave-B release SHA: 305c68d6e7173740d478fd41c11b4ae78a245469
Accepted integrated Wave-B release tree: dd63dd58c2ec10730ecb1f9781536ab78d3d6d30
Latest Entry-8 product/same-fixture SHA: af4b83ff6bde1d577b76ece3191e5b0e5b60d8af
Latest Entry-8 product tree: c60ab8ab918dc1078e3faed2ca5d44212e5b85bb
Latest Entry-9 product/same-fixture SHA: 2a870ec4808b6301e39bb99f446b457abc5458a5
Latest Entry-9 product tree: 9430a179e8e79322b1d49d2b53ed3b68a57f4a64
Latest Entry-10 product/same-fixture SHA: dba0016ec9878d40e1ed6edf60106491848b3956
Latest Entry-10 product tree: 7d02c784030e32e9d4fc08b22f76ecd8e93fbc1f
Exact release-validated branch head before this docs-only handoff: 305c68d6e7173740d478fd41c11b4ae78a245469
Latest release-validated migration tree: dd63dd58c2ec10730ecb1f9781536ab78d3d6d30
Latest exact-head release-CI SHA: 305c68d6e7173740d478fd41c11b4ae78a245469
Latest exact-head release run: 29879344293 (run #434), SUCCESS
Wave-B Checker: PASS, blocking findings 0, nonblocking findings 0
Resume Stage: Stage 5 IN_PROGRESS, inventory 29/29 classified, in-scope parity 10/25 accepted and 15/25 pending, deferred 4/4 explicit; Wave B release gate accepted; Entry 11 collision_1d / Wave C next

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
Stage 5 matrix/parity/runtime/W0/Entries 1-10 packages.

Wave A entries 5-7 and their release gate are accepted at `8f18c710...`, run
`29865756663` (run #433), `SUCCESS`. Wave B Entries 8-10 and their integrated
gate are release-accepted at `305c68d6e7173740d478fd41c11b4ae78a245469`, tree
`dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`, run `29879344293` (run #434),
`SUCCESS`; the Wave-B Checker is `PASS`, blocking `0`, nonblocking `0`. This
release result validates only that integrated exact head/tree, not the individual
Entry-8 `af4b83ff...`, Entry-9 `2a870ec...`, or Entry-10 `dba0016e...` product
commits and not the later documentation-only handoff commit.

Next exact task: implement Entry 11, `collision_1d`, as the first Wave C focused
same-fixture migration package.
Raw text, `system_type`, corpus/family/case metadata, expected answers, and legacy
output must not enter generic compilation, solving, verification, or selection.

Authoritative scope: 25 in scope; deferred exact entries 19
`spring_mass_vibration`, 23 `relative_acceleration_translation`, 24
`coriolis_relative_motion`, and 28 `slot_pin_relative_motion`; Entry 26
`polar_kinematics` is in scope. Deferred means structured unsupported, no generic
answer authority, off-mode rollback only, and no silent fallback. Never add
deferred entries to the accepted count or report a `29/29` generic migration.

Keep the public corpus sealed until Stage 7. The Beer PDF is reference-only for
Dynamics Chapters 11-19 structure and permitted later figure/coverage work; it is
never a runtime or exact-answer oracle. Private held-out and actual Korean/SI
exact-match evaluation remain NOT RUN.

Do not merge PR #16/#17, undraft, push main, force-push, rebase, deploy, change
production/environment values, access API keys, incur Live cost, or commit corpus,
private, or textbook assets. Apart from a hard blocker or an action requiring new
authority, continue without intermediate confirmation.
```
