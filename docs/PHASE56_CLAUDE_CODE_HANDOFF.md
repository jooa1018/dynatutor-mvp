# Phase 56 Claude Code Continuation Handoff

## Current remote-accepted Wave E checkpoint — 2026-07-23 Asia/Seoul

Wave E Entries 20–22 (`spring_energy_speed`, `flat_curve_friction`, and
`banked_curve_no_friction`) are accepted Generic typed migrations. The
authoritative in-scope progress is now **21/25**, with **4/25** Wave F
entries remaining. Deferred Entries 19, 23, 24, and 28 remain deferred;
Entry 26 remains in scope.

- Wave E code-containing checkpoint: `d3c4d27f6f4558242f1151f35eb16e6ae430c43c`
- Exact Wave E release head: `114b11d26ee1aa1e4107aa8eea9c66de9ea009af`
- DynaTutor release run #443 / `29979533898`: **SUCCESS**
- Phase 55 parser run #95 / `29979533893`: **SUCCESS**
- Focused Wave E evidence: **46 passed** — **36 fast**, **10 slow**
- Backend fast: **2,938 passed, 1 skipped** across four shards
- Backend slow: **138 passed** across **19** file shards
- Benchmark: **147 passed**; audit: **111 passed**; frontend marker: **15 passed**
- Frontend: **44/44**, typecheck, and static build: **PASS**
- Warm latency mean/p95/max: **11.940567 / 39.479565 / 52.174770 ms**
  against the **60/120 ms** budgets
- Cold import: **765.574531 ms**; RSS: **90.820 MB** against the
  **5000 ms / 512 MB** budgets
- Four-round pooled performance comparison: **PASS**, regressions **0**;
  largest positive p95 change **1.724%** against the **15%** limit
- Fresh same-model read-only audit: **PASS**, blocking findings **0**.
  This is accurately classified as same-model, not an independent Checker.

The Wave E product files on the release head have the same Git blob hashes
as the locally validated candidate. No test selection, assertion, timeout,
or performance threshold was relaxed. Legacy output remains diagnostics-only
and has no Generic routing, equation, candidate, verification, selection,
repair, or fallback authority.

PR #17 remains Draft, open, and unmerged on Draft PR #16. No merge, rebase,
reset, force-push, main update, production change, Live API/model call,
secret access, sealed-corpus access, or textbook-PDF access occurred.

The next exact Stage 5 work is Wave F: Entries 25, 26, 27, and 29.



## Current remote-accepted checkpoint — 2026-07-23 Asia/Seoul

This supersedes the archive-local candidate status below while retaining it as
historical evidence.

- Entries 11–18 are accepted; in-scope progress is **18/25** with **7/25**
  remaining. Deferred scope remains exactly the existing four entries.
- Wave C exact release head `67f46e9c84a658d1d5a50b9dfcdce81f78f20d8d`, run
  #439 / `29944965150`: **SUCCESS**.
- Wave D exact release head `34208235fabed97cc7a500668c13f5a4cf5a109d`, run
  #440 / `29947470482`: **SUCCESS**.
- Final local focused result: **184 passed** (136 fast, 48 slow); connected
  Phase 56 regression selection: **1,019 passed, 1 skipped**.
- Separate read-only Checker: **PASS**, blocking findings **0**. The only
  nonblocking note is the job timeout increase from 20 to 30 minutes, with all
  test and performance thresholds unchanged.
- PR #17 remains Draft, open, and unmerged on Draft PR #16. Do not merge,
  rebase, force-push, change `main`, deploy, or access sealed corpus/PDF data.


## Local Entries 11–18 candidate checkpoint — 2026-07-22

> This section records work completed from the user-supplied source archive. It
> is local candidate evidence, not a pushed GitHub exact-head release, and it
> supersedes the older Entry 11 resume instruction only inside this packaged
> artifact. Historical accepted evidence and exact-SHA attribution below remain
> unchanged.

- Source archive snapshot:
  `202912edb5a4db0781d4f40abad345441fc5cf71`; the archive contained no `.git`
  directory.
- Local product commit: `c0909da336b4723012199f53d6be04bb0e19f8ce`.
- Entries 11–18 focused same-fixture evidence: **184 passed** — **136 fast** and
  **48 slow**.
- Connected backend evidence: **960 passed, 1 skipped**; backend
  `frontend`-marker selection: **15 passed**.
- Combined recorded backend candidate evidence: **1,159 passed, 1 skipped**.
- Changed-file compilation, whitespace validation, authority audit, warm/cold
  performance, and same-model read-only audit: **PASS**; blocking findings **0**.
- Frontend repository metadata: **PASS**. Frontend dependency installation was
  blocked by package-gateway HTTP 503; 36 dependency-available tests passed, but
  full tests, typecheck, and build are **NOT RUN / FRONTEND_DEPENDENCY_BLOCKED**.
- Disposition: `LOCAL_CANDIDATE_VALIDATED / REMOTE_RELEASE_PENDING`.
- Official accepted count remains **10/25** until the patch is applied to the
  real branch and exact-head Wave C/Wave D CI plus an independent Checker pass.
- Complete local evidence and exact remote continuation commands are in
  `docs/PHASE56_LOCAL_ENTRIES11_18_VALIDATION.md`.
- `FINAL_LOCAL_DOCUMENTATION_HEAD = branch head containing this section`.

This is the execution-oriented, device-independent handoff for continuing Phase
56 without access to the preceding Codex conversation, its local work ledger, or
its temporary tooling. Read this document completely before changing code. The
cumulative evidence record remains in `docs/PHASE56_PAUSE_HANDOFF.md`.

## A. Identity

- Repository: `jooa1018/dynatutor-mvp`
- Working branch: `codex/phase56-generic-mechanics-engine`
- Phase 55 stacked base / PR #16 head:
  `4762727e8f9191604e2531b9982a5ae72ed73db9`
- PR #16: open, Draft, unmerged; base `main`
- PR #17: open, Draft, unmerged; Phase 56 stacked on PR #16
- Main SHA at handoff audit:
  `00b3a60de6e13756d089655879a02e4094122047`
- `LATEST_PRODUCT_CODE_SHA = a31018bfd13df4a87eb1b198881bb63a2b79c9a1`
- `LATEST_PRODUCT_TREE_SHA = e4a6f9d28fcbee93dd065d6fb2697383fe332833`
- `LATEST_TESTED_PRODUCT_CODE_SHA = a31018bfd13df4a87eb1b198881bb63a2b79c9a1`
  with status `PARTIALLY_TESTED`; only the evidence explicitly listed in section I
  belongs to this checkpoint.
- `LATEST_ACCEPTED_PRODUCT_CODE_SHA = dba0016ec9878d40e1ed6edf60106491848b3956`
  (Entry 10, `vertical_circle`).
- Latest accepted integrated release head:
  `305c68d6e7173740d478fd41c11b4ae78a245469`, Wave B run
  `29879344293`, `SUCCESS`.
- `FINAL_HANDOFF_HEAD = branch head containing this document`
- Handoff prepared: `2026-07-22 11:01:10 +09:00`, `Asia/Seoul`

The latest product SHA is newer than the latest accepted product SHA because
Entry 11 is deliberately preserved as WIP. The final handoff head is newer than
the product SHA because the handoff is committed separately with `[skip ci]`.
Never attribute Wave B release evidence to either newer checkpoint.

## B. Project objective

Phase 56 migrates DynaTutor from calculation routing by
`system_type -> dedicated legacy solver` to a reusable Generic Mechanics Engine:

```text
problem text / optional image
  -> one AI Mechanics model
  -> validated Generic Mechanics IR
  -> typed reusable laws and constraints
  -> Equation Graph
  -> graph-structure solve plan
  -> deterministic symbolic/numeric candidates
  -> independent verification
  -> exactly one verified answer or a fail-closed terminal
```

The AI may model source evidence into typed data, but it does not execute
mathematics or decide an answer. Deterministic code validates authority,
constructs the graph, retains candidate roots, verifies them independently, and
selects only when exactly one candidate is verified.

## C. Non-negotiable authority boundaries

These are design constraints, not implementation suggestions:

- `system_type` has no calculation, compilation, law-selection, or routing
  authority.
- A subtype has no calculation authority.
- Raw problem text is not read by compilation, solving, verification, or root
  selection.
- Regex, keyword, label, filename, or family-name Generic-solver selection is
  forbidden.
- Entry numbers are migration-ledger identifiers only and must never become
  runtime routing keys.
- Corpus case IDs, family IDs, gold labels, and expected answers are forbidden at
  runtime.
- AI output has no equation-execution, root-selection, verification, or final
  answer authority.
- Only a validated typed safe math AST may reach solver backends. Executable
  expression strings are forbidden.
- Preserve every mathematical candidate root until deterministic independent
  verification has evaluated it.
- Automatic selection requires exactly one verified candidate. Zero or multiple
  verified candidates must fail closed.
- A legacy result is a diagnostics-only oracle for migration comparison. It may
  not verify, select, repair, override, or supply a Generic answer.
- Silent legacy fallback is forbidden. Deferred entries permit only explicit
  off-mode rollback as specified in section E.
- Preserve all Phase 55 evidence/provenance, correction, ambiguity, and
  fail-closed contracts.
- The Beer textbook PDF is a human/reference-only coverage source. It is not a
  runtime, routing, equation, gold-answer, or exact-answer oracle.

## D. Exact progress

### Stage status

| Stage | Status | Boundary |
| --- | --- | --- |
| 0 | `ACCEPTED` | Repository/PR audit, architecture boundary, stacked Draft controls |
| 1 | `ACCEPTED` | Frozen validated IR and safe typed AST |
| 2 | `ACCEPTED` | Bounded one-call Mechanics modeler, repair/cache/privacy/cost controls |
| 3 | `ACCEPTED` | Typed law catalog, deterministic graph compiler, closure/authority gates |
| 4 | `ACCEPTED` | Graph-driven planning, candidates, solving, independent verification |
| 5 | `IN_PROGRESS` | 10/25 in-scope entries accepted; Entry 11 is local WIP |
| 6 | `NOT_STARTED` | Figure/text one-call modeling and API/UI work |
| 7 | `NOT_RUN` | Sealed corpus and offline evaluation |
| 8 | `NOT_STARTED` | Final exact-head CI, Checker, performance/regression |
| 9 | `NOT_RUN` | Bounded Live evaluation, authority-dependent |

Do not repeat or redesign accepted Stages 0-4.

### Stage 5 entry status

| Entry | Registry name | Current status |
| ---: | --- | --- |
| 1 | `single_particle_newton` | `RELEASE_ACCEPTED` within accepted history |
| 2 | `incline_no_friction` | `RELEASE_ACCEPTED` within accepted history |
| 3 | `incline_with_friction` | `RELEASE_ACCEPTED` within accepted history |
| 4 | `pulley_atwood` | `RELEASE_ACCEPTED` within accepted history |
| 5 | `pulley_table_hanging` | `RELEASE_ACCEPTED`, Wave A |
| 6 | `pulley_incline_hanging` | `RELEASE_ACCEPTED`, Wave A |
| 7 | `massive_pulley_atwood` | `RELEASE_ACCEPTED`, Wave A |
| 8 | `pure_rolling_energy` | `RELEASE_ACCEPTED`, Wave B |
| 9 | `rolling_energy_general` | `RELEASE_ACCEPTED`, Wave B |
| 10 | `vertical_circle` | `RELEASE_ACCEPTED`, Wave B |
| 11 | `collision_1d` | `LOCAL_WIP / PARTIALLY_TESTED`; **not accepted** |
| 12 | `constant_acceleration_1d` | `NOT_STARTED` |
| 13 | `projectile_motion` | `NOT_STARTED` |
| 14 | `constant_force_work` | `NOT_STARTED` |
| 15 | `fixed_axis_rotation` | `NOT_STARTED` |
| 16 | `horizontal_friction_force` | `NOT_STARTED` |
| 17 | `impulse_momentum` | `NOT_STARTED` |
| 18 | `work_energy_speed` | `NOT_STARTED` |
| 19 | `spring_mass_vibration` | `DEFERRED` |
| 20 | `spring_energy_speed` | `NOT_STARTED` |
| 21 | `flat_curve_friction` | `NOT_STARTED` |
| 22 | `banked_curve_no_friction` | `NOT_STARTED` |
| 23 | `relative_acceleration_translation` | `DEFERRED` |
| 24 | `coriolis_relative_motion` | `DEFERRED` |
| 25 | `plane_rigid_body_acceleration` | `NOT_STARTED` |
| 26 | `polar_kinematics` | `NOT_STARTED`; explicitly in scope |
| 27 | `instant_center_velocity` | `NOT_STARTED` |
| 28 | `slot_pin_relative_motion` | `DEFERRED` |
| 29 | `plane_rigid_body_velocity` | `NOT_STARTED` |

Official accepted in-scope count remains `10/25`; remaining in-scope count
remains `15/25`. Entry 11 WIP does not increase the accepted count.

## E. Authoritative course scope

- Registry inventory: `29/29 classified`.
- Phase 56 course-scoped migration: `25` in-scope entries.
- Deferred: exactly `4/4`:
  - Entry 19 `spring_mass_vibration`
  - Entry 23 `relative_acceleration_translation`
  - Entry 24 `coriolis_relative_motion`
  - Entry 28 `slot_pin_relative_motion`
- Entry 26 `polar_kinematics` is in scope.

For every deferred entry, preserve this exact policy:

- inventory: `PRESENT`
- scope: `DEFERRED_OUT_OF_CURRENT_COURSE_SCOPE`
- migration: `DEFERRED`
- same-fixture parity: `NOT_PLANNED_IN_PHASE56`
- Generic answer authority: `NONE`
- Generic behavior: precise verified unsupported
- legacy authority: `OFF_MODE_ROLLBACK_ONLY`
- silent fallback: `FORBIDDEN`
- future typed extension: `PRESERVED`

Never add accepted and deferred counts together and never claim `29/29 Generic
migration` completion.

## F. Waves

- Wave A, Entries 5-7: `RELEASE_ACCEPTED` at
  `8f18c710fc6d5d730fcceccfb30e3175c2613902`, run `29865756663`.
- Wave B, Entries 8-10: `RELEASE_ACCEPTED` at
  `305c68d6e7173740d478fd41c11b4ae78a245469`, run `29879344293`.
- Wave C, Entries 11-13: `IN_PROGRESS` because Entry 11 is WIP.
  - `collision_1d` — resume and complete the existing atomic unit
  - `constant_acceleration_1d` — not started
  - `projectile_motion` — not started
- Wave D, Entries 14-18: `NOT_STARTED`.
  - `constant_force_work`
  - `fixed_axis_rotation`
  - `horizontal_friction_force`
  - `impulse_momentum`
  - `work_energy_speed`
- Wave E, Entries 20-22: `NOT_STARTED`; skip deferred Entry 19.
  - `spring_energy_speed`
  - `flat_curve_friction`
  - `banked_curve_no_friction`
- Wave F, Entries 25, 26, 27, 29: `NOT_STARTED`; skip deferred Entries 23,
  24, and 28.
  - `plane_rigid_body_acceleration`
  - `polar_kinematics`
  - `instant_center_velocity`
  - `plane_rigid_body_velocity`

Run focused evidence for each entry. Run one independent read-only Checker and
one release CI only after a complete wave, not after each entry.

## G. Exact pause boundary

### What Codex was doing

- Last Wave: Wave C.
- Last Entry: Entry 11, `collision_1d`.
- Partial implementation exists: **YES**. Recover it from product commit
  `a31018bfd13df4a87eb1b198881bb63a2b79c9a1`; do not discard or recreate it.
- Safe last atomic unit: the coherent five-file WIP was compiled, narrowly
  regressed, committed as `wip(phase56): checkpoint Wave C for Claude Code
  handoff`, and pushed by non-forced fast-forward.
- Latest code status: `PARTIALLY_TESTED`, not accepted and not known-failing.

### Last functions and files changed

- `backend/engine/mechanics/compiler/compiler.py`
  - added `_Collision1DProfile`
  - added `_collision_1d_candidate(...)`
  - added `_collision_1d_contract(...)`
  - connected the contract in `compile_mechanics_problem(...)`
- `backend/engine/mechanics/laws/core.py`
  - changed `_momentum_emissions(...)` for signed boundary velocities,
    system-scoped external-impulse authority, and structural/assumption evidence
- `backend/engine/mechanics/solver/contracts.py`
  - added `_is_static_collision_boundary_graph(...)`
  - added `_graph_plan_event_ids(...)`
  - retained raw event provenance while deriving a narrow event-free plan only
    for the exact static collision graph
- `backend/engine/mechanics/solver/planner.py`
  - changed `plan_equation_graph(...)` to use `_graph_plan_event_ids(...)`
- `backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py`
  - added the Entry 11 focused package (`47` fast and `12` slow tests collected)

### Implemented WIP contract

The compiler recognizes a query-independent, evidence-bound profile containing
exactly one system with two child particles; one world-origin positive-x
Cartesian 1D frame; one interval; untimed `collision_start` and `collision_end`
boundaries; one collision interaction; two positive masses; two signed known
pre-impact velocities; two inferred post-impact velocities; one explicit
coefficient of restitution in `[0, 1]`; an exact post-velocity query; and one
externally approved, evidenced, system-scoped
`external_impulse_negligible` assumption. Extra or malformed authority fails
closed, including invalid output units.

Core laws emit signed momentum conservation and restitution equations with
system/particle topology and evidence provenance. Solver planning retains the
raw graph event IDs but suppresses timed-event planning only when the complete
compiler-generated static-collision signature passes strict symbol, domain,
scope, incidence, equation, provenance, cost, and AST checks. Ordinary event
graphs remain fail-closed.

### Test gap and historical failure

- Known failing test on the committed checkpoint: `NONE`.
- Historical slow command initially reached all generic and direct-legacy
  numerical comparisons, then all 12 cases failed at the final status assertion
  because the test referenced nonexistent `DifferentialStatus.parity`.
- Confirmed exception: enum-member lookup failure at that assertion
  (`DifferentialStatus.parity` does not exist).
- Applied correction: the assertion now uses
  `DifferentialStatus.full_parity` at the committed checkpoint.
- A final slow rerun was started after that correction, but its terminal output
  was not captured before the emergency stop. Its result is `UNKNOWN`, not PASS
  and not a known product failure.
- Unconfirmed speculation: none. Do not infer the missing result.

### First action and first code-change rule

After checking out the exact final handoff head and installing dependencies, run
the complete 12-case Entry 11 slow file first:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD/backend:$PWD/backend/tests" \
python -m pytest -q -o addopts= -m slow \
backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
```

PowerShell equivalent:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = "$PWD\backend;$PWD\backend\tests"
python -m pytest -q -o addopts= -m slow backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
```

First code-change candidate: **none until that command is rerun**. If it fails,
change only what the exact failure proves necessary. If it passes, run the
Entry 11 fast selection and directly connected compiler/solver/planner/
verification regressions, then complete the Entry 11 Checker/acceptance record.
Do not begin Entry 12 until Entry 11 is a cohesive accepted atomic unit.

### First files to read, in order

1. `docs/PHASE56_CLAUDE_CODE_HANDOFF.md`
2. `docs/PHASE56_PAUSE_HANDOFF.md`
3. `backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py`
4. `backend/engine/mechanics/compiler/compiler.py` at
   `_collision_1d_candidate`, `_collision_1d_contract`, and its compile hook
5. `backend/engine/mechanics/laws/core.py` at `_momentum_emissions`
6. `backend/engine/mechanics/solver/contracts.py` at
   `_is_static_collision_boundary_graph` and `_graph_plan_event_ids`
7. `backend/engine/mechanics/solver/planner.py` at `plan_equation_graph`
8. `docs/ADR_PHASE56_GENERIC_MECHANICS_ENGINE.md`
9. `docs/GENERIC_MECHANICS_IR.md`
10. `docs/MECHANICS_SECURITY.md`
11. `docs/MECHANICS_LEGACY_MIGRATION.md`

Do not redo accepted Entries 1-10, accepted Stages 0-4, Wave A/B Checkers, or
Wave A/B release runs. Do not replace the existing Entry 11 WIP with a dedicated
route or formula keyed by `collision_1d`. Any older current-state sentence in
`docs/MECHANICS_LEGACY_MIGRATION.md` saying that Entry 11 is merely “next” is a
historical Wave B boundary and is superseded by this handoff; its accepted
classification and evidence remain authoritative.

## H. Changed files

### Since latest accepted integrated release head `305c68d...`

Product code in WIP commit `a31018b...`:

- `backend/engine/mechanics/compiler/compiler.py` — exact typed collision profile
  and fail-closed compiler gate.
- `backend/engine/mechanics/laws/core.py` — signed system-scoped collision laws
  and provenance.
- `backend/engine/mechanics/solver/contracts.py` — strict static-collision plan
  event derivation while retaining raw graph provenance.
- `backend/engine/mechanics/solver/planner.py` — consume derived plan events.

Test code:

- `backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py` — new
  focused Entry 11 fast/slow package.

Previously prepared Wave B documentation, included in the later fast-forward but
not release-validated at its documentation commit:

- `docs/MECHANICS_LEGACY_MIGRATION.md` — cumulative Wave B release record.
- `docs/PHASE56_PAUSE_HANDOFF.md` — cumulative Wave B pause evidence, now
  superseded at the top by the emergency checkpoint.

Emergency handoff documentation:

- `docs/PHASE56_CLAUDE_CODE_HANDOFF.md` — this execution-oriented handoff.
- `docs/PHASE56_PAUSE_HANDOFF.md` — updated cumulative checkpoint pointer/state.

### Exact categories at finalization

- Latest accepted checkpoint to latest tested checkpoint: four product files and
  one focused test file listed above.
- Latest tested product checkpoint to final handoff head: documentation only.
- Local WIP after final handoff commit: none expected.
- CI/workflow changes for Entry 11 or emergency handoff: none.
- Deleted files: none.
- Untracked files: none expected after final handoff commit.

## I. Test and CI evidence

Only actually observed evidence is recorded.

### Latest WIP product checkpoint

Exact product SHA:
`a31018bfd13df4a87eb1b198881bb63a2b79c9a1`.

1. Changed-file compile:

   ```text
   python -m py_compile \
     backend/engine/mechanics/compiler/compiler.py \
     backend/engine/mechanics/laws/core.py \
     backend/engine/mechanics/solver/contracts.py \
     backend/engine/mechanics/solver/planner.py \
     backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
   ```

   Result: `PASS`, exit `0`. Duration was not captured. This validates syntax and
   imports only for the listed files.

2. Narrow direct compiler regression:

   ```text
   python -m pytest -q -o addopts= \
     backend/tests/test_phase56_mechanics_compiler.py \
     -k "collision_template_requires_one_reciprocal_event_pair_and_preserves_both_events or collision_conservation_requires_external_assumption_id_authority"
   ```

   Result: `PASS`; `2 passed, 55 deselected, 28 warnings in 0.33s`.

3. Whitespace/diff validation:

   ```text
   git diff --check
   ```

   Result: `PASS`, exit `0` on the exact tree later committed as `a31018b...`.

4. Focused Entry 11 fast working-tree evidence:

   ```text
   python -m pytest -q -o addopts= -m "not slow" \
     backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
   ```

   Result: `47 passed, 12 deselected` in `81.16s`. The four product files were
   identical to `a31018b...`; afterward the test file received only the slow-only
   enum assertion correction described in section G. Therefore this is useful
   targeted evidence but is not falsely labeled exact-commit full-file evidence.

5. Historical slow attempt:

   ```text
   python -m pytest -q -o addopts= -m slow \
     backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
   ```

   Initial result: `12 failed` only at the obsolete
   `DifferentialStatus.parity` assertion after numeric comparisons ran. The
   assertion was corrected. The final post-correction rerun result was not
   captured and is `UNKNOWN`; rerun it first.

   Exact interrupted-host rerun command (recorded as evidence, not as a portable
   dependency):

   ```powershell
   $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
   $env:PYTHONPATH='C:\Users\eccto\Documents\Codex\2026-07-21\d\work;C:\Users\eccto\Documents\Codex\2026-07-21\d\work\dynatutor-mvp\backend;C:\Users\eccto\Documents\Codex\2026-07-21\d\work\dynatutor-mvp\backend\tests'
   & 'C:\Users\eccto\Documents\Codex\2026-07-21\d\work\.venv-phase56\Scripts\python.exe' -m pytest -q -p pytest_phase56_budget_plugin -m slow backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
   ```

   `pytest_phase56_budget_plugin.py` was a local, uncommitted startup-budget shim
   outside the repository. It is not required product state and must not be
   copied into the repository. Use the portable command in section G first.

Current latest-code classification: `PARTIALLY_TESTED`.

### Accepted Wave A release evidence

- Exact head: `8f18c710fc6d5d730fcceccfb30e3175c2613902`
- Run: `29865756663` (run #433)
- Status: `SUCCESS`
- Independent Checker: `PASS`, blocking findings `0`
- Attribution: integrated Wave A only; do not attribute it to newer code.

### Accepted Wave B release evidence

- Exact head: `305c68d6e7173740d478fd41c11b4ae78a245469`
- Tree: `dd63dd58c2ec10730ecb1f9781536ab78d3d6d30`
- Run: `29879344293` (run #434)
- Status: `SUCCESS`
- Independent Checker: `PASS`, blocking findings `0`, nonblocking findings `0`
- Reported release evidence: backend fast `2766 passed, 1 skipped, 347
  deselected`; slow `80 passed` across eight file shards; benchmark `147`; audit
  `111`; frontend-marker `15`; metadata, warm/cold performance budgets,
  frontend `44/44`, typecheck, build, and four-round pooled performance all
  passed.
- Attribution: this validates only `305c68d...` / `dd63dd58...`. It does not
  validate Entry 11, product commit `a31018b...`, or the final docs commit.

No new full CI, release CI, or independent large Checker was started for the
emergency handoff.

## J. Environment and commands

### Clone, fetch, and checkout

```bash
git clone https://github.com/jooa1018/dynatutor-mvp.git
cd dynatutor-mvp
git fetch --prune origin
git switch --track origin/codex/phase56-generic-mechanics-engine
git status --short --branch
git rev-parse HEAD
```

If the branch already exists locally, use `git switch
codex/phase56-generic-mechanics-engine` followed by `git pull --ff-only`. Never
reset, rebase, or force the branch to a remembered SHA. Confirm that HEAD equals
the remote final handoff head reported with this handoff.

### Python setup

Linux/macOS, preferably Python 3.11 to match release CI:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-lock.txt
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements-lock.txt
```

Release CI uses Python 3.11. The interrupted Codex session used a local Python
3.12 venv plus a temporary out-of-repository pytest budget plugin. That plugin is
not required repository state and must not be treated as missing product data.

### Frontend setup

Node `>=20 <21` and npm `>=10 <11`:

```bash
cd frontend
npm ci
cd ..
```

The same commands work in PowerShell.

### Focused Entry 11 commands

Portable first rerun from repository root:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD/backend:$PWD/backend/tests" \
python -m pytest -q -o addopts= -m slow \
backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
```

Then, only if the slow rerun is understood:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD/backend:$PWD/backend/tests" \
python -m pytest -q -o addopts= -m "not slow" \
backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
```

PowerShell uses `;` between PYTHONPATH entries:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = "$PWD\backend;$PWD\backend\tests"
python -m pytest -q -o addopts= -m slow backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
```

### Official repository wrappers

Run these only at the prescribed wave/final gates, not immediately on resume:

```bash
bash scripts/check_backend_fast.sh
bash scripts/check_backend_slow.sh
bash scripts/check_backend_benchmark.sh
bash scripts/check_backend_audit.sh
```

On Windows use Git Bash or WSL for these exact wrappers. The slow wrapper
discovers marked tests and executes one file shard at a time with a default
240-second per-file watchdog. The fast/benchmark/audit defaults are 420/240/180
seconds.

### Frontend gates

```bash
cd frontend
npm test
npm run typecheck
npm run build
cd ..
```

These commands are the same in PowerShell.

### Compile and diff checks

```bash
python -m py_compile \
  backend/engine/mechanics/compiler/compiler.py \
  backend/engine/mechanics/laws/core.py \
  backend/engine/mechanics/solver/contracts.py \
  backend/engine/mechanics/solver/planner.py \
  backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
git diff --check
```

PowerShell may place the file arguments on one line. Do not run Live APIs: no API
secret was accessed or authorized. Keep the corpus sealed and the PDF outside the
repository.

## K. Code map

- `backend/engine/mechanics/contracts.py` — frozen Generic Mechanics IR entities,
  frames, events, quantities, assumptions, queries, and evidence contracts.
- `backend/engine/mechanics/math_ast.py` — non-executable typed safe math AST.
- `backend/engine/mechanics/normalization.py` — unit/direction normalization and
  validated IR construction boundary.
- `backend/engine/mechanics/compiler/` — authority validation, relevant-subgraph
  construction, Equation Graph contracts, closure/rank/fail-closed issues.
- `backend/engine/mechanics/laws/` — reusable mechanics law emission; Entry 11
  extends the common collision branch of `_momentum_emissions`.
- `backend/engine/mechanics/solver/` — graph-derived planning, deterministic
  symbolic/numeric candidates, budgets, execution, and diagnostics.
- `backend/engine/mechanics/verification/` — independent candidate constraints,
  residual/domain checks, and exactly-one selection.
- `backend/engine/mechanics/migration/` — registry, same-fixture harness, legacy
  observation, differential/invariance reports; legacy is diagnostic only.
- `backend/engine/mechanics/runtime/` — rollout modes and one-call orchestration
  with exact IR authorization and fail-closed terminals.
- `docs/ADR_PHASE56_GENERIC_MECHANICS_ENGINE.md` — accepted architecture and
  authority decisions.
- `docs/GENERIC_MECHANICS_IR.md` — typed IR semantics and provenance rules.
- `docs/MECHANICS_SECURITY.md` — trust boundaries and security invariants.
- `docs/MECHANICS_LEGACY_MIGRATION.md` — authoritative 29-entry classification,
  waves, parity, and rollback policy.
- `docs/PHASE56_PAUSE_HANDOFF.md` — cumulative accepted history and official
  checkpoint record.

Entry 11-specific landmarks are the five files listed in section G. The focused
test builds real typed fixtures, freezes the Generic result before a direct
legacy diagnostic observation, verifies independent residuals, and includes
structure/authority/evidence/domain/invariance negatives.

## L. Implementation discipline for Claude Code

1. Do not reimplement accepted Stages 0-4 or accepted Entries 1-10.
2. Resume from the missing Entry 11 slow result and the existing atomic WIP.
3. Preserve focused same-fixture parity for every entry.
4. Run full/release CI only once at the end of a complete wave.
5. Reuse family-common typed laws; do not create entry-specific formula routes.
6. Never hardcode formulas behind Entry IDs, `system_type`, subtype, text, or
   corpus metadata.
7. Never adjust a Generic answer by observing a legacy result.
8. Fail closed on structural or authority ambiguity.
9. Treat any new authority-boundary change as requiring Checker-level independent
   self-audit before acceptance.
10. Split work into cohesive product, test/evidence, and documentation commits as
    appropriate.
11. Record exact commit SHA and exact test/CI attribution after each atomic unit.
12. Do not change `main`, PR readiness, production, deployment, environment
    values, secrets, corpus, or textbook assets.

## M. Work after Stage 5

Stage 5 completion is not Phase 56 completion.

- Stage 6: real text+image one-call modeling; typed `FigureObservationV1`;
  text/figure evidence conflict handling; user correction; API and UI V2
  integration; synthetic figure coverage.
- Stage 7: sealed public-corpus evaluation; adversarial tests; compositional 12;
  synthetic figure 30; metamorphic and hard-safety checks; precise deferred
  unsupported evaluation. Gold/case/family metadata is input-harness-only and
  forbidden at runtime.
- Stage 8: final exact-head backend/frontend wrappers, typecheck/build,
  performance/regression, and one final independent read-only Checker. Any
  blocking finding prevents PASS.
- Stage 9: bounded Live evaluation only with explicit secret and budget authority
  after all offline gates pass; otherwise honestly remain `NOT_RUN`.

## N. Protections

Claude Code must not:

- merge PR #16 or PR #17;
- mark either PR ready for review;
- push `main`;
- force-push, rebase, reset away WIP, or rewrite history;
- deploy or change production/environment configuration;
- retrieve, print, or probe API keys;
- commit the textbook PDF;
- commit the public-corpus ZIP, gold labels, private data, or held-out assets;
- generate a private held-out set without new explicit authority;
- silently fall back for a deferred entry;
- weaken thresholds, timeouts, safety gates, or verification rules to obtain a
  pass;
- falsely attribute accepted tests or CI to an untested SHA;
- claim `29/29 Generic migration` completion.

At the emergency checkpoint, corpus state was `SEALED / UNOPENED`, PDF state was
`REFERENCE_ONLY / UNOPENED / UNCOMMITTED`, Live was `NOT_RUN`, cost incurred was
`$0.00`, and no secret was accessed.

## O. Claude Code Resume Prompt

```text
Claude Code Resume Prompt

Continue Phase 56 in repository jooa1018/dynatutor-mvp.

Branch: codex/phase56-generic-mechanics-engine
PR #16: Phase 55, open Draft, unmerged; do not merge or mark ready
PR #17: Phase 56 stacked Draft, open and unmerged; do not merge or mark ready
Main baseline: 00b3a60de6e13756d089655879a02e4094122047
Phase 55 base: 4762727e8f9191604e2531b9982a5ae72ed73db9
Exact final handoff head: branch head containing docs/PHASE56_CLAUDE_CODE_HANDOFF.md; resolve from the remote branch and the accompanying final handoff response
Latest product SHA: a31018bfd13df4a87eb1b198881bb63a2b79c9a1
Latest tested product SHA: a31018bfd13df4a87eb1b198881bb63a2b79c9a1, PARTIALLY_TESTED
Latest accepted product SHA: dba0016ec9878d40e1ed6edf60106491848b3956
Latest accepted integrated release head: 305c68d6e7173740d478fd41c11b4ae78a245469

Current stage: Stage 5 IN_PROGRESS
Current wave: Wave C IN_PROGRESS
Current entry: Entry 11 collision_1d, LOCAL_WIP / PARTIALLY_TESTED, not accepted
Accepted count: 10/25 in scope
Remaining in-scope count: 15/25

Read in order:
1. docs/PHASE56_CLAUDE_CODE_HANDOFF.md
2. docs/PHASE56_PAUSE_HANDOFF.md
3. backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py
4. backend/engine/mechanics/compiler/compiler.py at _collision_1d_candidate and _collision_1d_contract
5. backend/engine/mechanics/laws/core.py at _momentum_emissions
6. backend/engine/mechanics/solver/contracts.py at _is_static_collision_boundary_graph and _graph_plan_event_ids
7. backend/engine/mechanics/solver/planner.py at plan_equation_graph
8. docs/ADR_PHASE56_GENERIC_MECHANICS_ENGINE.md
9. docs/GENERIC_MECHANICS_IR.md
10. docs/MECHANICS_SECURITY.md
11. docs/MECHANICS_LEGACY_MIGRATION.md

First exact task: recover the missing post-fix result by running the entire 12-case slow selection for the existing Entry 11 focused file. Do not edit code before seeing that result. If it fails, fix only the proven failure. If it passes, run the focused fast selection and directly connected regressions, then complete Entry 11 acceptance evidence. Do not start Entry 12 until Entry 11 is cohesive.

First focused command on Linux/macOS from repository root after dependency setup:
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD/backend:$PWD/backend/tests" python -m pytest -q -o addopts= -m slow backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py

PowerShell equivalent:
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; $env:PYTHONPATH="$PWD\backend;$PWD\backend\tests"; python -m pytest -q -o addopts= -m slow backend/tests/test_phase56_mechanics_collision_1d_same_fixture_parity.py

Accepted entries 1-10: single_particle_newton, incline_no_friction, incline_with_friction, pulley_atwood, pulley_table_hanging, pulley_incline_hanging, massive_pulley_atwood, pure_rolling_energy, rolling_energy_general, vertical_circle. Do not redo them.

Remaining waves:
- Wave C: collision_1d (existing WIP), constant_acceleration_1d, projectile_motion
- Wave D: constant_force_work, fixed_axis_rotation, horizontal_friction_force, impulse_momentum, work_energy_speed
- Wave E: spring_energy_speed, flat_curve_friction, banked_curve_no_friction
- Wave F: plane_rigid_body_acceleration, polar_kinematics, instant_center_velocity, plane_rigid_body_velocity

Deferred exactly four: Entry 19 spring_mass_vibration, Entry 23 relative_acceleration_translation, Entry 24 coriolis_relative_motion, Entry 28 slot_pin_relative_motion. Their Generic answer authority is NONE, behavior is precise verified unsupported, legacy is OFF_MODE_ROLLBACK_ONLY, silent fallback is forbidden, and future extension is preserved. Entry 26 polar_kinematics is in scope. Never claim 29/29 Generic migration.

Authority boundaries: system_type/subtype/Entry IDs/raw text/regex/corpus metadata/expected answers carry no runtime calculation or routing authority. AI does not execute equations, choose roots, verify candidates, or supply the final answer. Only validated typed safe AST reaches deterministic solver backends. Preserve all roots; auto-select only exactly one independently verified candidate. Legacy is diagnostics-only and never Generic answer authority. Preserve Phase 55 evidence and fail-closed contracts. Fail closed on ambiguity.

Run focused parity per Entry. Run one independent read-only Checker and full release CI only at the end of a complete Wave. Keep both PRs Draft/unmerged. Do not push main, force-push, rebase, rewrite history, deploy, alter production, access secrets, or weaken thresholds. Keep the public corpus sealed until Stage 7. Keep the textbook PDF outside the repository and use it only as a permitted human reference, never an answer/runtime oracle.

Continue without intermediate confirmation unless there is a genuine hard blocker, a destructive action, a secret/cost or production action, or a material scope/authority decision requiring new user approval.
```
