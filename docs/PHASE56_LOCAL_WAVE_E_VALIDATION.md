# Phase 56 Wave E Local Validation Candidate

## Remote integration result — 2026-07-23 Asia/Seoul

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

The local candidate disposition below is retained only as historical provenance.



## Disposition

`LOCAL_CANDIDATE_VALIDATED / REMOTE_RELEASE_PENDING`

This document records a local Wave E candidate prepared from the source tree whose
core product blobs matched remote branch
`codex/phase56-generic-mechanics-engine` at
`a2354ac37faeb18f920f3a4407cb650f0205cb24`.

It is not an exact-head GitHub release record. Until the patch is applied to the
real branch and the Python 3.11 release workflow plus a fresh read-only Checker
pass, the authoritative accepted count remains **18/25**. A successful remote
Wave E gate would raise it to **21/25**, leaving the four Wave F entries in scope
and the existing four deferred entries unchanged.

## Scope

Wave E contains exactly:

20. `spring_energy_speed`
21. `flat_curve_friction`
22. `banked_curve_no_friction`

Deferred Entry 19 `spring_mass_vibration` was not migrated, reclassified, or
redesigned. Its existing vibration ODE path remains ready and its deferred
migration policy remains unchanged.

## Implementation

### Entry 20 — spring energy speed

The Generic path emits reusable energy equations rather than calling the legacy
spring-energy solver:

- two spring-potential equations, `U = 1/2 k x^2`
- two translational kinetic-energy equations, `K = 1/2 m v^2`
- one mechanical-energy conservation equation, `K0 + U0 = K1 + U1`
- one nonnegative scalar-speed domain constraint

The exact typed profile requires one particle, one spring, one world-origin
Cartesian 1D frame, one event-free interval, exact initial/final body and spring
states, source-grounded mass/stiffness/displacements/initial speed, and approved
`linear_spring`, `kinetic_energy`, and `no_energy_loss` authority.

Both algebraic speed roots are retained until verification. Negative scalar-speed
roots are rejected by the independent domain check. Negative spring displacement
is not rejected because spring energy depends on displacement squared. Impossible
negative final-energy domains fail closed without a clamp or absolute-value
repair.

### Entry 21 — flat curve friction

The Generic path uses typed contact and circular-motion equations:

- `N = m g`
- `f = m a_n`
- limiting static friction `f = mu N`
- circular kinematics `a_n = v^2 / R`
- nonnegative contact force and scalar-speed domains

For the exact `mu = 0` boundary, the same typed equations imply `f = a_n = v = 0`.
The local symbolic backend does not certify the repeated zero root of the
quadratic form reliably, so the compiler emits the algebraically equivalent
linear boundary `a_n = v sqrt(g/R)` only for that exact typed zero-friction
limit. Force, contact, and circular residuals are still independently checked.
No raw text, family label, or legacy answer selects this boundary.

### Entry 22 — banked curve without friction

The Generic path combines:

- `a_n = v^2 / R`
- vertical balance `N cos(theta) = m g`
- inward balance `N sin(theta) = m a_n`
- nonnegative contact force and scalar-speed domains

The bank angle is a normalized, source-grounded typed quantity. Deterministic
code derives finite sine and cosine literals while retaining angle evidence in
every law application. The result is mass-independent, preserves both algebraic
speed roots until verification, and fails closed for malformed friction,
geometry, actor, angle, radius, gravity, query, or unit structure.

## Candidate-boundary regressions found and fixed

Two existing accepted structures share partial radius/contact signals with curve
motion. The first draft therefore over-recognized:

- Entry 8 `pure_rolling_energy`
- Entry 10 `vertical_circle` surface-contact cases

The candidate boundary was narrowed using typed structure only:

- at least one particle actor
- a scalar speed query
- an explicit normal-acceleration quantity
- the exact particle/road/environment inventory

After the fix, pure rolling, general rolling, and vertical-circle focused fast
suites all returned to green. No `system_type`, subtype, raw text, regex,
fixture name, entry number, expected answer, or legacy output participates in
the decision.

## Focused evidence

| Entry | Fast | Slow | Total |
| --- | ---: | ---: | ---: |
| 20 `spring_energy_speed` | 13 | 3 | 16 |
| 21 `flat_curve_friction` | 12 | 4 | 16 |
| 22 `banked_curve_no_friction` | 11 | 3 | 14 |
| **Wave E** | **36** | **10** | **46** |

All 46 focused tests passed. The three new fast invariance tests prove that
consistent identifier renaming and reversed record order preserve the graph
fingerprint, selected equation IDs, and law multiset.

Slow tests execute the complete Generic solve first, freeze the result, and only
then call the legacy solver for same-fixture differential comparison. Legacy
output has no Generic routing, equation, candidate, verification, selection,
repair, or fallback authority.

## Connected regression evidence

Observed local results after the final candidate-boundary fix include:

- compiler: **57 passed**
- mechanics contract + solver contract + planner: **160 passed**
- deferred scope + migration scope: **154 passed**
- selected migration authority/fail-closed audit: **4 passed**
- `pure_rolling_energy` fast: **40 passed**
- `rolling_energy_general` fast: **60 passed**
- `vertical_circle` fast: **67 passed**
- selected accepted work/friction/work-energy solve and metadata checks:
  **6 passed**
- backend benchmark marker: **147 passed** in four exact-node shards
- backend audit marker: **111 passed** in four exact-node shards
- backend frontend marker: **15 passed**
- frontend repository metadata: **PASS**
- changed-file `py_compile`: **PASS**
- mechanics `compileall`: **PASS**
- `git diff --check`: **PASS**

Earlier in the same local work session, before the final narrowing-only compiler
change, the complete connected solver execution, verification, validation,
numeric strictness, runtime contract/static, runtime, and evidence-adapter
selections also completed without assertion failure. The final compiler change
only narrows Wave E candidate recognition; the high-risk rolling and
vertical-circle suites plus the compiler/deferred/contract gates were rerun
afterward.

## Local performance

Python 3.13.5 local measurements:

- warm solve mean: **8.562296 ms**
- warm solve p95: **28.458017 ms**
- warm solve max: **39.179434 ms**
- budgets: mean **60 ms**, p95 **120 ms**
- cold `engine.services` import: **380.333627 ms**
- maximum RSS: **148.543 MB**
- budgets: import **5000 ms**, RSS **512 MB**

All local performance budgets passed.

## Read-only authority audit

A separate same-model read-only pass over the staged five-file product/test diff
found no blocking issue. Added production lines contain no use of:

- `system_type`, subtype, raw/problem text, regex, family/case ID, or Entry number
  as calculation authority
- legacy solver imports or legacy answer use
- expected-answer lookup
- `eval`, unrestricted `sympify`, or executable expression strings
- test deletion, deselection manipulation, threshold relaxation, or timeout
  relaxation

This is a **same-model read-only audit**, not an independent Checker.

## Local limitations and required remote gate

The local environment provides Python 3.13.5 and Node 22, while the release
workflow uses Python 3.11 and Node 20. The aggregate benchmark command and some
multiprocessing-heavy pytest files completed their assertions but remained alive
in local worker shutdown long enough for the outer tool to send SIGTERM. Exact
node sharding was therefore used for the recorded benchmark, audit, and focused
results. No timeout or test threshold was changed.

Full frontend tests/typecheck/build were not rerun because the supplied source
archive has no `node_modules`, the current Node version is outside the repository
contract, and Wave E changes no frontend file.

Required remote actions:

1. Apply the Wave E patch to exact remote head
   `a2354ac37faeb18f920f3a4407cb650f0205cb24`, unless a newer normal commit is
   present and has first been reconciled.
2. Run Entry 20, 21, and 22 focused fast/slow tests.
3. Run the official backend fast, slow, benchmark, audit, frontend-marker, and
   performance gates on Python 3.11.
4. Run frontend `npm ci`, tests, typecheck, and build on Node 20.
5. Run a fresh read-only Checker on the exact product head.
6. Record the exact Wave E product SHA, release SHA, Actions run ID, and Checker
   result in the Phase 56 handoff/migration documents and PR #17 body.
7. Keep PR #16 and PR #17 Draft, open, and unmerged; do not change `main` or
   production.

## Local commit

Product/test commit:

`d704945462f8aae8a30008f53f69ef3901ddea8f`

The final local documentation head is the commit containing this document.
