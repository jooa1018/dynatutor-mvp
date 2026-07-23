# Phase 56 Entries 11–18 Local Validation Candidate

## Remote integration result — 2026-07-23 Asia/Seoul

The local candidate was applied to the real branch and is now accepted for
Entries 11–18. Wave C passed at exact release head
`67f46e9c84a658d1d5a50b9dfcdce81f78f20d8d` in run #439 (`29944965150`);
Wave D passed at exact release head
`34208235fabed97cc7a500668c13f5a4cf5a109d` in run #440 (`29947470482`).
Accordingly, the authoritative in-scope count is **18/25**, not the
candidate-only 10/25 stated below.

The Wave D release completed every required gate: fast **2,902 passed, 1
skipped**; slow **128 passed** across 16 shards; benchmark **147 passed**;
audit **111 passed**; backend `frontend` marker **15 passed**; and frontend
tests/typecheck/build passed. The four-round pooled performance comparison
passed with no regression. A separate read-only Checker reported zero blocking
findings; its only nonblocking note is the 20-to-30-minute job timeout change
needed to complete the existing gates without changing any test or performance
threshold.

## Disposition

`LOCAL_CANDIDATE_VALIDATED / REMOTE_RELEASE_PENDING`

This report records validation performed on the user-supplied source archive for
`codex/phase56-generic-mechanics-engine`. It is **not** GitHub exact-head release
evidence and it does not advance the authoritative accepted count by itself.
The official accepted state remains Entry 10 / `10 of 25` until these changes are
applied to the real branch and pass the prescribed remote Wave C and Wave D
release gates.

The source archive had no `.git` directory. Its archive metadata identifies
source snapshot `202912edb5a4db0781d4f40abad345441fc5cf71`; the local synthetic
baseline commit is `7982ddfe1c13e484eca6ed9a7a8df8c15a7a6876`.
The local product commit after Entry 18 is:

```text
c0909da336b4723012199f53d6be04bb0e19f8ce
feat(phase56): migrate impulse momentum and work energy speed
```

Earlier local commits on top of the supplied snapshot are:

```text
13b2dbb  Entry 13 projectile_motion
1716c67  Entry 14 constant_force_work
70f3d52  Entry 15 fixed_axis_rotation
23d5548  Entry 16 horizontal_friction_force
c0909da  Entries 17–18 impulse_momentum / work_energy_speed
```

Entries 11 and 12 were already present in the supplied snapshot and were
revalidated rather than recreated.

## Focused same-fixture evidence

| Entry | Registry ID | Fast | Slow | Local result |
| ---: | --- | ---: | ---: | --- |
| 11 | `collision_1d` | 47 passed | 12 passed | PASS |
| 12 | `constant_acceleration_1d` | 15 passed | 6 passed | PASS |
| 13 | `projectile_motion` | 15 passed | 4 passed | PASS |
| 14 | `constant_force_work` | 12 passed | 5 passed | PASS |
| 15 | `fixed_axis_rotation` | 12 passed | 5 passed | PASS |
| 16 | `horizontal_friction_force` | 10 passed | 6 passed | PASS |
| 17 | `impulse_momentum` | 12 passed | 5 passed | PASS |
| 18 | `work_energy_speed` | 13 passed | 5 passed | PASS |
| **Total** |  | **136 passed** | **48 passed** | **184 passed** |

The Entry 11 12-case slow file exceeded the local aggregate command window when
run as one process. Every parameterized case was then executed in an isolated
process; all 12 passed. This is an execution-window/sharding observation, not an
assertion failure.

## Connected backend regression evidence

The following connected selections passed on the local product tree:

| Area | Result |
| --- | ---: |
| Compiler | 57 passed |
| Normalization and numeric strictness | 189 passed, 1 skipped |
| Mechanics IR contracts | 76 passed |
| IR validation | 101 passed |
| Evidence adapters | 15 passed |
| Solver contracts | 78 passed |
| Solver execution | 31 passed |
| Solver planning and verification integration | 9 passed |
| Verification contracts | 53 passed |
| Verifier | 27 passed |
| Migration harness and migration scope | 42 passed |
| Legacy differential parity | 30 passed |
| Deferred-scope contracts | 138 passed |
| Runtime contracts and static checks | 25 passed |
| Runtime orchestration | 89 passed |
| **Connected subtotal** | **960 passed, 1 skipped** |

Backend tests marked `frontend` also passed: **15 passed**, with 3,283 tests
deselected by the marker selection.

Combined focused and connected backend evidence recorded here is therefore:

```text
1,159 passed, 1 skipped
```

This count intentionally excludes partial or concurrently interrupted wrapper
runs and does not claim a complete repository release suite.

## Complete backend fast selection

The repository fast wrapper selected exactly 2,903 tests. Its single aggregate
process reached 69 percent without an assertion failure but hit the unchanged
420-second watchdog, so that aggregate run is recorded as `TIMEOUT`, not PASS.
The identical collected node set was then partitioned only at the execution
boundary, retaining the same marker expression and the same 420-second limit per
shard:

```text
Shard 1: 725 passed, 1 skipped
Shard 2: 727 passed
Shard 3: 724 passed, 1 skipped
Shard 4: 725 passed
Total:   2,901 passed, 2 skipped, 0 failed
```

Shard 4 was also rerun from the beginning as four smaller process groups after
an unrelated long-lived background process received SIGTERM; those groups
passed 180, 180, 183, and 182 tests. No failed node was omitted or converted to
a deselection.

## Slow-suite boundary

All 48 slow cases newly relevant to Entries 11–18 passed. An attempted repeat of
the complete repository slow suite, including previously accepted Wave A/B
files, was interrupted by the local execution environment sending SIGTERM to a
long-lived background process. This report therefore does **not** claim a full
repository slow-wrapper PASS and does not replace the historical exact-head Wave
A/B release evidence.

## Entry 17 contract summary

Entry 17 uses typed equation-graph laws:

```text
J = F * duration
J = m * (v_final - v_initial)
duration > 0
```

The event IDs remain in the immutable graph as before/after provenance. A narrow
exact graph predicate removes them only from timed-event planning when the full
compiler-produced law set, AST, scope, source quantities, assumptions,
applications, rank, and domains match. Synthetic near-miss graphs retain the
ordinary fail-closed event behavior.

Focused evidence covers impulse, final velocity, initial velocity, mass,
average force, duration, signed reversal, zero impulse, mixed units,
nonpositive mass/duration, malformed interval/query binding, metadata
invariance, graph spoof rejection, and diagnostics-only legacy comparison.

## Entry 18 contract summary

Entry 18 uses the existing typed particle work-energy law and adds an explicit
semantic speed domain predicate:

```text
W = 0.5 * m * (v_final^2 - v_initial^2)
v_final >= 0       # only when the typed role is scalar speed
```

The symbolic solver preserves both algebraic roots before verification. The
nonnegative predicate selects the physical scalar-speed root only after
candidate generation. A signed `velocity` query does not silently receive this
speed predicate or the endpoint-event waiver. An impossible negative radicand
fails closed; there is no clamp, absolute value, hidden rest default, or legacy
answer substitution.

Focused evidence covers rest and nonzero initial speed, positive/negative/zero
work, mixed units, candidate preservation, negative-radicand failure, missing
initial state, speed-versus-velocity semantics, mass/speed domains, internal
query leakage, wrong binding/unit/event rejection, metadata invariance, graph
spoof rejection, and diagnostics-only legacy comparison.

## Unit safety amendment

The compiler now validates scalar query output units against both the declared
query dimension and the target quantity dimension. The finite whitelist was
extended only with trusted expressions required by existing contracts:

- `ms`
- `1/s`
- `kg*m^2/s` (normalized whitelist spelling `kg*m2/s`)
- `W`

No unrestricted unit parser, `eval`, or untrusted expression path was opened.
Compiler regressions initially exposed missing whitelist coverage for `1/s` and
`kg*m^2/s`; the whitelist was corrected and the complete 57-test compiler file
then passed.

## Static and authority audit

- Changed-file `py_compile`: PASS.
- `git diff --check`: PASS.
- New production-code additions contain no raw problem text, `system_type`,
  subtype, corpus ID, expected answer, regex, dynamic `eval`, or unrestricted
  `sympify` calculation authority.
- Legacy results remain diagnostics-only in slow differential tests.
- Graph event waivers are based on exact typed graph structure, not registry
  family labels or entry numbers.
- Same-model read-only audit: PASS, blocking findings 0.
- This was not an independent-agent Checker and must not be presented as one.

## Performance evidence

Local environment: Linux, CPython 3.13.5. Release CI remains expected to use
Python 3.11.

```text
Warm solve latency (final rerun):
  cases: 43
  samples: 86
  mean: 7.929143 ms
  p95: 31.313116 ms
  max: 33.322398 ms
  budgets: mean <= 60 ms, p95 <= 120 ms
  result: PASS

Cold import / RSS (final rerun):
  engine.services import: 381.002115 ms
  max RSS: 148.582 MB
  budgets: import <= 5000 ms, RSS <= 512 MB
  result: PASS
```

Frontend repository metadata: PASS.

## Frontend limitation

The source ZIP did not contain `frontend/node_modules`. `npm ci` could not
complete because the configured package gateway returned HTTP 503 for required
packages. The dependency-free portions of `npm test` produced 36 passing tests;
one test file could not start because `esbuild` was unavailable. Typecheck and
build were therefore not run. This is recorded as `FRONTEND_DEPENDENCY_BLOCKED`,
not as a frontend product PASS and not as a demonstrated product assertion
failure.

The available Node version was 22.16.0, while the repository declares
`>=20 <21`; the official frontend gate must be rerun with Node 20 after a
successful `npm ci`.

## Gates not claimed

The following were not performed or are not attributable to this local tree:

- push to `codex/phase56-generic-mechanics-engine`
- GitHub Actions exact-head Wave C release run
- GitHub Actions exact-head Wave D release run
- independent read-only Checker
- PR #17 body update
- Draft transition or merge
- main update
- production deployment or environment change
- Live API/model evaluation
- sealed corpus evaluation

## Required remote continuation

1. Apply the supplied patch to a clean checkout of the actual Phase 56 branch.
2. Confirm the real base/head and preserve any newer legitimate remote commits.
3. Run Entry 11–18 focused selections with Python 3.11.
4. Run the official backend fast/slow/benchmark/audit/frontend-marker wrappers.
5. Run frontend `npm ci`, tests, typecheck, and build with Node 20.
6. Run a fresh independent read-only Checker.
7. Run exactly one Wave C and one Wave D release CI according to the repository
   gate policy, recording exact product/release SHAs and run IDs.
8. Only after those gates pass, update the authoritative accepted count from
   `10/25` to `18/25` and update PR #17. Keep both PRs Draft and unmerged.
