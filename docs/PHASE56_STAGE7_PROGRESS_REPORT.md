# Phase 56 Stage 7 progress report

Disposition: **`STAGE_7_IN_PROGRESS / NOT_ACCEPTED`**

Stage 7 is **not** accepted. Stage 8 has **not** been started. PR #16 and PR #17
remain open, Draft, and unmerged, and `main` is unchanged at
`00b3a60de6e13756d089655879a02e4094122047`.

## B15/B16 acceptance and B17 disposition session (2026-07-30, later) — read this first

This session continued Stage 7 from the measured 40/81 baseline
(documentation head `52b237d`) and closed two structure packages forward-only;
no reset, rebase, amend, squash, force-push, or history rewrite; every
pre-session commit is preserved byte-identical.

| Item | Value |
|---|---|
| B15 `TABLE_PULLEY_TWO_BODY` | **ACCEPTED** — code `9084091`, +3 public solves |
| B16 `PARTICLE_ON_INCLINE_KINETIC_FRICTION` | **ACCEPTED** — code `3baa29d`, +3 public solves |
| Projection owner fix | `a97e794` — body-stated constitutive parameters keep their source owner |
| B17 `SPRING_ENERGY_ENDPOINT_SPEED` | **INCOMPLETE** — no code; see below |
| Final code head | `a97e794b6f2b0a4b4521c280a03d62d03b9a361b` |
| `OBSERVED_PUBLIC_SCORE` | **46/81** (measured at the final code head) |
| `AUTHORITY_ACCEPTED_SCORE` | **46/81** (observed = accepted; no unmeasured claims) |
| Supported wrong / solved-but-unscored / downgraded | **0 / 0 / 0** |
| Deferred | 12/12; needs_figure 2/2; needs_confirmation 2/2; insufficient 1/1 |
| Terminal mapping | 63/100 (was 57/100) |
| Hard safety | 23/23 measured, 0 unbound, 0 nonzero |
| Lanes C/D/E, compositional 12, synthetic 38, metamorphic, physics-changing, redaction | all PASS |
| External model calls / private access / measured cost | 0 / 0 / $0 |
| Strict report SHA-256 | `ff2d4b108f613e0eb3466f3232e443009cdedcdcac9ef4d60bb112e6900c75df` |
| Corpus archive SHA-256 | `cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef` |

`PUBLIC_EVALUATION_INFORMED_FIX: YES` — the packages were selected and
verified by running the authorised public corpus and reading privacy-safe
aggregates.  No private-corpus generalization is claimed.  Stage 7 remains
`IN_PROGRESS / NOT_ACCEPTED`; Stage 8 is `NOT_STARTED`.

### B15 — table-pulley two-body (`9084091`)

A body on a frictionless horizontal table tied over a fixed ideal pulley to a
hanging body; aggregate acceleration-magnitude query.  The projection's
fixed-pulley closure admits the typed `surface` support variant alongside the
incline variant; the new `table_pulley_two_body` profile is disjoint from
`incline_hanging_pulley` by the source's own support primitive (never an
invented zero angle).  The transaction derives only the world frame,
weight/contact/rope interactions, contact and rope states, and value-free
unknown components; the pre-built horizontal-contact law recognizer and
compiler contract were widened to the free-body primitives the corpus
projection actually produces, an optional system entity, and the authorized
server-default gravity policy record.  All solving stays with the existing
`particle_weight`, `particle_newton_second`, `rope_massless_tension`,
`rope_fixed_pulley_motion`, `fixed_contact_no_penetration`, and
`contact_normal_bound` laws.  The vertical two-body (Atwood) transaction now
refuses a support primitive with no typed support relation instead of
treating it as an inert bystander (the B10 lesson applied forward).
31 focused tests.

### B16 — kinetic incline slide (`3baa29d`)

One body in a source-declared kinetic slide down one incline with a
source-valued angle and friction coefficient; tangential-acceleration query,
down-slope positive.  The corpus states no mass, so the existing force-based
incline laws cannot close the shape; instead the projection derives a
`gravity_driven_downslope_sliding` authority by closed policy only when
gravity is the entire typed driving system (one body, one incline support, a
`sliding_on_incline` segment, no stated velocity, force, rope, rest boundary,
extra body, or extra proposal) — the same model-completeness footing as the
B14 impact-isolation policy.  A friction coefficient stated on the support
surface takes the sliding body as its typed owner under the existing
interaction-owned constitutive convention.  The new registered
`incline_sliding_kinetic_acceleration` law — the sliding twin of the existing
sticking law — emits the per-mass slope closure plus the authority's own
nonnegative-drive inequality, so a declared slide gravity cannot drive
refuses instead of answering.  The rolling-energy candidate no longer claims
a declared sliding regime, and the active-incline-friction compiler gate
accepts exactly the mass-free downslope-authorised shape while every
force-bearing mixture keeps failing closed.  The adversarial
ambiguous-friction case remains `needs_confirmation`.  25 focused tests.

### B17 — spring energy endpoint speed — INCOMPLETE, stated honestly

The corpus's typed event structure does not preserve the natural-length
endpoint: the end event's kind is the generic `finish`, and the
natural-length wording exists only in raw-text evidence quotes, which the
engine must never read as authority.  Without a typed carrier for "final
spring deformation is zero", the final-speed query of an attached-spring
release is genuinely underdetermined (the deformation at `finish` is
unstated), and any server default for it would be exactly the silent-solve
hazard the B12 revocation removed.  B17 is recorded INCOMPLETE with no code;
the three affected public cases remain ordinary non-solves (wrong 0, blocked
numeric 0).

### Regression, environment, and audit notes

- Full Stage 7 focused suite at the final code head: **1,245 passed**;
  backend collection 4,095 tests, 0 errors.
- One projection defect found by the suite (a body-stated coefficient was
  rejected as owner-ambiguous) was repaired forward at `a97e794`.
- The first strict run of this session was executed against unpinned
  dependencies and mis-measured Lane D (FastAPI 0.141 route registration);
  the official report was produced under `requirements-lock.txt` versions,
  where Lane D passes.  No code changed between the two runs.
- Exact-head CI at `a97e794` (all with verified exact checkout): push runs
  `30560360254` (parser), `30560359932` (Stage 6: frontend, focused,
  regression shards 0–7, partition audit, gate), `30560360115` (Stage 7:
  B7 slow, offline evaluation incl. full backend regression and collection,
  frontend, Stage 7 gate), `30560360250` (release: fast shards 0–3, slow
  shards 0–15, both partition audits, quality, performance, frontend,
  release gate); PR runs `30560366152`, `30560365767`, `30560365734`,
  `30560365696`.  **8/8 SUCCESS.**
- A **SAME_MODEL_READ_ONLY_CHECKER** (same Fable model as the author; not
  represented as an independent Checker) audited `52b237d..a97e794` across
  twelve scope areas (table/incline separation, kinetic/static separation,
  B10/B12 revoke preservation, routing, generated values, event/interval
  scope, near-miss coverage, compiler gate widenings, thresholds, gold
  isolation, strict attribution): **PASS — blocking 0**, with eight
  non-blocking notes recorded in the session evidence (among them: the
  downslope compiler predicate could also check the approved-id set like its
  sibling; the `a97e794` owner fix deserves its own pinned control; B15
  inherits B8's tolerance of stray unused source quantities rather than
  B16's exact-count style; and the B16 authority's physical premise — no
  up-slope slide without stated prior motion — should stay documented
  wherever the profile is).  A fresh independent Checker remains a
  prerequisite for any Stage 7 acceptance claim.

## B10/B12 authority repair session (2026-07-30)

An independent review found that two sealed packages produced public-correct
answers **without sufficient typed authority**, and this session repaired both
forward (no history rewrite) and landed one new package:

| Item | Commit | Disposition |
|---|---|---|
| B10 common-centre repair | `3411e8eb2e5f920512fcfacc51af11a90d16ea9d` | **B10 INCOMPLETE / revoked** — the profile now requires the source's own typed rotation centre (one `rotates_about` → `coincident` record binding the body to a third, otherwise-inert centre point).  The pre-repair public shape (general plane motion, floating centre entity, no typed relation) is pinned refusing, whatever the ratio computes. |
| B12 limiting-contact repair | `58ae586cbeb8783632d6b09eb2f4a14703858f26` | **B12 INCOMPLETE / revoked** — `minimum_speed` now projects a typed `QueryObjective` the planner enforces globally (no exact-value profile may read an objective-bearing draft), and the `v² = g·r` boundary needs the full typed limiting authority: an `inward` `ContactSide` on the contact, a `contact`/`touching` state over the interval, and a `boundary`/`active` state at the top instant.  The corpus schema cannot state the orientation or the boundary states, so the public vertical-circle cases now fail closed. |
| Frame-reference audit follow-up | `a837719e86be0117126b003eb00e01a3dcc7e1d0` | Classifies the two additive enum fields in the observer-frame audit registry (they are enums, never references); repairs the CI failure at `58ae586`. |
| **B14 1D restitution impact** | `53a169d1ed46fd200e453e5a47784550e2215a13` | **Implemented and tested** (35 focused tests, full stage-7 suite 1,189 passed locally).  New closed-policy projection derivation `external_impulse_negligible` per body from typed model completeness; exact-shape profile + transaction; the pre-existing collision static-boundary recognizer gains the Lane B closure shape as a second exact form, and its own [0, 1] coefficient domain fail-closes unphysical restitution.  **Public yield unmeasured — see the blocker below.** |

**Accounting — measured and reconciled (strict gate re-run after the archive
was supplied mid-session).** `OBSERVED_PUBLIC_SCORE` = `AUTHORITY_ACCEPTED_SCORE`
= **40/81, wrong 0** at `exact_head_sha d719def` (code `53a169d`): the six
revoked B10/B12 solves are gone exactly as designed (both profiles measure
97/100 `not_applicable`, 0 complete — no wrong solve, no downgrade, no blocked
numeric answer, no silent solve), and **B14 adds +2** (collision_restitution:
4 applicable, 2 `verified_solve_reachable`, 1 `profile_plan_not_formable`,
1 `solver_rejected` with no numeric output).  Deferred 12/12; needs_figure
2/2; needs_confirmation 2/2; insufficient_information 1/1; unsupported_other
0/2; terminal mapping 57/100; hard safety 23/23 measured, 0 unbound,
0 nonzero, PASS; lanes C/D/E, compositional 12, synthetic 38, metamorphic,
physics-changing controls, redaction all PASS; exit 2 on Lane B yield gates
only.  Strict report: `/root/stage7_external/stage7_strict_report_d719def.json`,
SHA-256 `fc562bb7dc091894dd6e363a367a1a8305e648df6bc1e26e8646182be3f5fe01`,
corpus SHA-256 verified `cc8d8b27…`, evaluator `phase56-stage7-evaluator-v3`,
contract v1, schema `dynatutor.phase56_stage7.offline_gate` 1.0.  **B14 is
therefore ACCEPTED** (additional supported correct +2, wrong 0, exact-head CI
8/8 SUCCESS at `53a169d`).  The next two restitution contexts (one
plan-not-formable, one solver-rejected, both numberless) are the family's
remaining shape candidates.

The earlier revision of this section, preserved below for the session record,
was written while the archive was absent:

**Corpus-unavailable blocker (this session).** The authorised public archive
(SHA-256 `cc8d8b27…`) is supplied out-of-tree per session and was not present
in this session's container.  No strict public-corpus gate could run; every
public-100 number in this report below this line is the previous session's
measurement at its own head.  The next session with the archive must first
re-run the strict gate at `53a169d` (or later) and reconcile observed =
authority-accepted before any new package.

**Next exact implementation task (measured diagnosis, this session).** The
strongest next family is the **table-pulley two-body** closure (~3 contexts by
the in-tree matrix; the same contexts appear as `fixed_pulley`'s
`authority_fixed_pulley: missing` and `incline_hanging_pulley`'s
`quantity_angle: missing` rows).  A projected table shape reaches validation
`needs_confirmation` because no closure consumes its value-bearing frictionless
approvals; the `_derive_fixed_pulley_assumptions` chain refuses it twice over
(the `lies_on` support must be an *incline* primitive, and two `frictionless`
approvals — pulley and table — break the one-match-per-kind rule); and the
incline profile demands the angle a horizontal table never has.  The package is
a B8-scale table-variant closure (profile + transaction + a horizontal-support
branch of the law profile).  The translating-frame family must **not** be
attempted as yield: its three clean contexts are expected-deferred (the
measured `supported_downgraded_to_unsupported = 0` proves it), so solving them
would create deferred silent solves.

## Supersession note

Earlier revisions of this report described the corpus-preflight checkpoint
(`LANE_B_NOT_STARTED`) and, before that, a corpus-unavailable blocker. Both
states are superseded: the authorised public archive has since been supplied,
its integrity re-verified, and the public 100 **executed end-to-end through the
engine**. The evidence below replaces the preflight-only claims. Historical
package heads remain listed for provenance; their CI evidence still belongs to
them and must not be re-attributed.

## Exact heads

| Role | SHA |
|---|---|
| Main baseline (unchanged) | `00b3a60de6e13756d089655879a02e4094122047` |
| Session base (remote head at session start) | `bc5e0be81ba66c2551f0ef47fa05511167949624` |
| Evaluator v3 package | `1954d14a58bf1b3135d3d42057354958de8a24e4` |
| **CODE_CANDIDATE_HEAD (this session)** | `803b40c37389315a96d2819b4350cad2c00f892b` |
| **STRICT_GATE_TESTED_HEAD** | `803b40c37389315a96d2819b4350cad2c00f892b` |
| **FULL_REGRESSION_TESTED_HEAD** | `1954d14a58bf1b3135d3d42057354958de8a24e4` |
| DOCUMENTATION_HEAD | this commit |

`FULL_REGRESSION_TESTED_HEAD` is deliberately named separately and is **not**
re-attributed to the code candidate. The 4,478-test local regression ran at
`1954d14`; the only later change, `803b40c`, removes tests and adds none (86 → 15
in one file, by collapsing parametrisation into loops). The whole backend is
re-run independently at `803b40c` by CI — `backend fast`, `backend slow`,
`backend quality`, `backend performance` and the release gate all SUCCESS.

The candidate was reflected onto `codex/phase56-generic-mechanics-engine` by a
verified-ancestor **fast-forward push only**
(`7963de0 → 9918d47 → 47b99d2 → 9a6e4b9 → bc5e0be → 1954d14 → 803b40c`). No reset,
rebase, amend, squash, force-push, or history rewrite occurred anywhere in the
session. Every pre-session commit is preserved byte-identical; every change landed as a
new atomic commit on top of them.

## Session packages (`d33c70b..b88a9ea`, 10 atomic commits)

| Package | Commit | Content |
|---|---|---|
| A — event source authority | `a677547` (+`15255a5`) | An event kind licenses a numeric boundary equation only when its gold-declared `evidence_quote` binds to an exact, unique span of the problem text and flows through `source_evidence` into `Event.evidence_refs`. Missing, unfound, or ambiguous quotes fail closed as typed `event_authority_gaps`; unproven events are preserved but never license emission. No raw-text keyword or regex routing. Shared eligibility contract in `engine/mechanics/laws/event_boundary.py`, consumed identically by the law layer and the Stage 7 derivation. |
| B — typed occurrence scope | `a3b9b43` (+`fc4ec64`) | `Event.occurs_in_interval_ids` types segment-interior occupancy separately from boundary authority; `MotionInterval.start/end_event_id` stays the sole boundary authority. Forged interiority (an occupied event that is actually an endpoint) and foreign-subject occupancy are rejected at validation; the compiler enforces inverse reciprocity and applies occurrence reach at every scope site. |
| C — elapsed-duration query binding | `0083fd9` | A time query rebinds to a typed segment duration only when the segment's both boundaries are set, distinct, and the query's event role is terminal — proven from typed fields, with no epoch invention and no role smuggling. Unprovable time queries decline rather than misbind. |
| D — structural angle refusal | `c616151` | The magnitude-with-angle launch refusal is pinned to what an equation structurally touches (consumed angle quantities, folded trig literals, signed launch components, sign machinery) instead of `law_id` substrings, so it is rename-proof. Frozen refusal behaviour unchanged. |
| E — profile-isolated feasibility | `223c070` | `profile_feasibility.py` rewritten: each (profile, context) pair is measured by an independent selected-profile run; 14-status taxonomy; unimplemented profiles report `profile_not_implemented` = **not measured**, never a definitional zero; `precise_unsupported` only via exact typed compiler codes; declaration-order invariance proven by permutation. |
| Solver waiver | `84d1cb6` | Exact static-graph recognizer admits the evidenced-extremum boundary family ({event_vertical_extremum_velocity, particle_constant_acceleration_velocity, uniform_gravity_acceleration}); gravity emission now cites its `constant_gravity` authorization; the verifier's `source_evidence` check accepts assumption citations as provenance while still failing when both evidence and citations are empty. First end-to-end applied-profile verified solve achieved (synthetic apex time `t = v0/g`, all checks passed). |
| Gate aggregation | `1770ea1` | The offline gate now measures every Stage 7 lane honestly: Lane C/D suites in fresh interpreters, compositional 12, synthetic 38, metamorphic, physics-changing controls, gold-scored answer scoring (pint, SI), counts-only hard-safety aggregate, redaction stamp, `--require-full-stage7` strict keys. |
| Gate CI parity | `b88a9ea` | Lane E runs exactly the workflow's steps (pinned eslint toolchain, tests/lint/typecheck/build); hard-safety aggregate no longer inherits the Lane B yield gate — safety and yield are independent verdicts. |

## Measured Lane B public-100 result (executed at `803b40c`)

The full public corpus (SHA-256 `cc8d8b27…` verified, 84 dev / 16 adversarial)
was executed through the complete pipeline: projection → authority →
closure → validation → normalization → authorization → compiler → solver →
independent verification → frozen snapshot → gold scoring.

| Terminal | Count |
|---|---:|
| `solved` | **6** |
| `verified_unsupported` (deferred) | 6 |
| `needs_figure` | 2 |
| `needs_confirmation` | 2 |
| `insufficient_information` | 1 |
| `compiler_failure` (underdetermined) | 67 |
| `compiler_unsupported` (typed precise codes) | 16 |
| Total | 100 |

- **Case-level scoring against the frozen distribution** (evaluator v3, scored
  strictly after the runtime snapshot is frozen): supported **6/81 correct, 0
  wrong, 75 unscored**; deferred **6/12**; unsupported-other **0/2**;
  needs_figure **2/2**; needs_confirmation **2/2**;
  insufficient_information **1/1**. Terminal mapping **0.17**; the six metrics
  all **0.074** (6 / 81).

  The denominator is the 81 supported cases the contract declares, not the six
  that happened to solve, so partial progress reads as partial. An earlier
  revision of this report said "6 scored, 6 correct, 0 unscored", which counted
  only what the engine produced and made a 7 %-complete lane read as complete.
- **Wrong solves: 0** — the hard requirement holds. Every solved value was
  converted to SI with `pint` and matched its gold reference inside the corpus's
  own declared tolerance.
- All 6 solved candidates passed all six verification checks
  (`equation_residual`, `nonnegative_time`, `query_binding`,
  `source_evidence`, `unit_consistency`, `constraint`), and each carries every
  kind its own graph and candidate obliged — now required by the scorer rather
  than assumed.
- The lane distribution is **byte-identical to the session base** `bc5e0be`.
  Evaluator v3 changed how the run is *judged*, not what the engine does, and the
  three scorer changes were each measured before and after to confirm no count
  moved. That is the intended result of contract-hardening work.

**Frozen target comparison.** The frozen Lane B target is
`81 solved / 12 verified deferred / 2 / 2 / 2 / 1, wrong 0`. The measured
result is `6 solved` — the target is **not met**, and this is the single
honest gap that keeps Stage 7 `NOT_ACCEPTED`. The target was not lowered,
reinterpreted, or re-scoped.

### Typed remaining walls (why 6, not 81)

Every non-solved executed case terminates with a typed compiler code, not a
silent failure:

| Typed code | Path | Count |
|---|---|---:|
| `underdetermined` | `equations` | 67 |
| `requires_specialized_model` | `geometry.*` | 12 |
| `requires_specialized_model` | `interactions.*` | 4 |
| `nonlinear_verification_deferred` | `equations` | 6 |
| `free_linear_vibration_readout_deferred` | `queries.*.target.role` | 3 |
| `translating_frame_relative_acceleration_deferred` | `queries.*.target.frame_id` | 3 |

The dominant wall (`underdetermined`, 67) is a real modelling gap: the
projected drafts do not yet carry enough typed structure for the compiler to
close the equation systems the corpus questions need. The profile-by-profile
route to closing it is recorded in
`docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md` §6a, measured by the corrected
profile-isolated instrument (below).

## Profile-isolated feasibility (corrected instrument)

The superseded first-wins census overstated `rigid_fixed_axis`; the rewritten
instrument measures each implemented profile in an **independent
selected-profile run** per applicable context:

- `free_flight_gravity` — 8 applicable: 2 `compiler_no_equation`,
  6 `profile_plan_not_formable`. After the solver waiver this profile has a
  proven end-to-end verified-solve path (synthetic apex-time control), making
  it the **first qualifying profile** under the measured-yield rule.
- `impulse_momentum` — 4 applicable: 4 `profile_plan_not_formable`.
- `relative_translating_frame` — 9 applicable: 3 verified-deferred,
  6 `profile_plan_not_formable`.
- 10 unimplemented profiles — reported `profile_not_implemented` =
  **not measured**. No definitional zeros.

## Full strict gate result at the code candidate `803b40c`

```
cd backend
STAGE7_PUBLIC_CORPUS_PATH=/abs/external/dynatutor_beer12_ko_corpus_v1_public.zip \
OPENAI_API_KEY="" ANTHROPIC_API_KEY="" OPENAI_BASE_URL="" ANTHROPIC_BASE_URL="" \
MECHANICS_MODELER_BASE_URL="" MECHANICS_FIGURE_BASE_URL="" \
python tools/run_phase56_stage7_offline_gate.py \
  --require-public-corpus --require-full-stage7 --output /abs/external/report.json
```

`STAGE7_RUN_SCOPE=STRICT_PUBLIC_CORPUS_GATE`, **exit 2** — expected: Lane B has
not met the frozen distribution. `exact_head_sha` in the report is
`803b40c37389315a96d2819b4350cad2c00f892b`, the code candidate itself, so no
documentation head is stamped with the candidate's evidence.

- Report SHA-256: `be45b67ea163f0b376b94e880059b98fc612aaf5c705d644738bd82395742d46`
- Evaluator `phase56-stage7-evaluator-v3`; contract `phase56-stage7-evaluation-contract-v1`
- Archive SHA-256 matched; `public_dev` 84 / `public_adversarial` 16 / total 100
- External model calls **0**; private held-out accesses **0**; measured cost **$0**

39 strict gates, **11 failing** — every one of them Lane B yield, and nothing else:

| Strict gate | Result |
|---|---|
| corpus supplied / SHA / 84 / 16 / 100 | PASS |
| `strict_lane_b_executed` / `_100_executed` / `_scored` | PASS |
| **`strict_supported_81_solved`** | **FAIL — 6 correct of 81** |
| **`strict_deferred_12_verified_unsupported`** | **FAIL — 6 of 12** |
| **`strict_unsupported_other_2`** | **FAIL — 0 of 2** |
| `strict_needs_figure_2` | PASS |
| `strict_needs_confirmation_2` | PASS |
| `strict_insufficient_information_1` | PASS |
| **`strict_terminal_mapping_100_percent`** | **FAIL — 0.17** |
| **six metric gates** (answer, unit/dimension, query binding, direction/sign, candidate coverage, residual verification) | **FAIL — 0.074 each (6/81)** |
| **`strict_unscored_zero`** | **FAIL — 75** |
| `strict_wrong_solve_zero` | **PASS — 0** |
| `strict_solved_but_unscored_zero` | PASS — 0 |
| `strict_deferred_silent_solve_zero` | PASS — 0 |
| `strict_blocked_silent_solve_zero` | PASS — 0 |
| `strict_blocked_numeric_answer_zero` | PASS — 0 |
| `strict_lane_c_pass` / `strict_lane_d_pass` / `strict_lane_e_pass` | PASS |
| `strict_compositional_12_pass` / `strict_synthetic_38_pass` | PASS |
| `strict_metamorphic_pass` / `strict_physics_changing_controls_pass` | PASS |
| `strict_redaction_pass` | PASS |
| `strict_hard_safety_pass` | PASS |
| **`strict_hard_safety_all_signals_measured`** | **PASS — 23 of 23** |
| **`strict_hard_safety_unbound_zero`** | **PASS — 0** |
| **`strict_hard_safety_nonzero_zero`** | **PASS — 0** |

The last three gates are new in evaluator v3 and are the reason the hard-safety
section now means something: `per_signal_instrument_registry: IMPLEMENTED`,
`signal_count` 23, `measured_signal_count` 23, `unbound_signal_count` 0,
`nonzero_signal_count` 0. Previously the catalog reported `all_zero` while 17 of
its 23 signals had no instrument at all.

Lane C remains contract/integration evidence over the deterministic recorded
modeler only; **actual model quality is `NOT_RUN / N/A`** — no external model
call was made and measured cost is $0.

## Regression evidence

| Suite | Head | Result |
|---|---|---|
| Full backend regression (local) | `1954d14` | **4478 passed, 1 skipped, 0 failed** (43:05) |
| Stage 7 offline gate runner | `803b40c` | 50 passed |
| Hard-safety instrument attacks | `803b40c` | 15 passed |
| Gold isolation + Lane B runner | `803b40c` | 49 passed |
| Preflight + corpus integrity contracts | `803b40c` | 128 passed |

The full local regression is attributed to `1954d14` and **not** re-attributed to
the code candidate. `803b40c` changes exactly one test file, removing 71 tests by
collapsing parametrisation into loops and adding none; the entire backend is
re-executed at `803b40c` by CI below.

No test was deleted, no assertion weakened, no threshold relaxed, no shard budget
widened, no legacy fallback or case-specific patch introduced.

## Exact-head CI evidence for the code candidate `803b40c`

All six workflows executed at the exact candidate head on
`codex/phase56-generic-mechanics-engine`:

| Workflow | Event | Run | Result |
|---|---|---:|---|
| Phase 56 Stage 7 offline evaluation | push | `30271934503` | **SUCCESS** |
| Phase 56 Stage 7 offline evaluation | pull_request | `30271937974` | **SUCCESS** |
| Phase 56 Stage 6 multimodal | push | `30271936141` | **SUCCESS** |
| Phase 56 Stage 6 multimodal | pull_request | `30271937930` | **SUCCESS** |
| DynaTutor release tests | pull_request | `30271938042` | **SUCCESS** |
| Phase 55 textbook parser | pull_request | `30271937988` | **SUCCESS** (`live-openai-smoke` skipped — no Live call approved) |

Within `DynaTutor release tests`: `backend fast`, `backend slow`,
`backend quality`, `backend performance`, `frontend` and `release gate` all
SUCCESS.

This evidence belongs to `803b40c` and must not be re-attributed to the
documentation-only head that follows it.

### A shard-budget failure at the preceding candidate, and why it was not a test failure

The first evaluator-v3 candidate, `1954d14`, failed `backend fast` — with **zero
failing tests**. `scripts/check_backend_fast.sh` splits the suite into four
contiguous shards **by test count** and gives each a 420 s wall clock; the 89
tests the hard-safety attacks added moved every shard boundary, so shard 2
inherited more of the same-fixture parity suites than before and was terminated
at 78 % by `[run_with_timeout] timed out after 420s`.

The repair was to make the new tests cheap, never to widen the budget. Sixteen
parametrised correction attacks each built their own FastAPI application and
seeded their own revision to exercise one recursive guard; they are now two loops
inside two tests. Three denylist sweeps contributed 52 more cases to assert a
pure function over a frozenset; they are now loops. The four attacks that must
drive a real application through the real endpoint are marked `slow` — what the
marker exists for, and what parity suites of the same shape already do — so they
run under `backend slow`, while the strict gate still runs them by exact node ID
with `-o addopts=`, which clears the marker filter. All 37 registry-bound node
IDs still resolve, and the file went from 86 tests / 85 s to 15 tests / 20 s.

No threshold was raised, no budget widened, no assertion weakened and no attack
removed: every key, denylist entry and guard attacked before is still attacked.

## Read-only audit (same-model, not an independent Checker)

A same-model read-only audit covered all 10 commits of `d33c70b..b88a9ea`:
**blocking findings 0**. Spot-runs re-executed 50 + 188 + 237 + 23 tests with
no failure. Identity-routing grep over every added line found zero forbidden
tokens; the evidence-quote binding was confirmed to be exact literal span
matching, not regex routing; the verifier's both-empty provenance refusal was
confirmed by negative control.

Non-blocking observations recorded for a future session (deliberately **not**
patched here, to keep the CI-attributed code head exact):

1. The gate module docstring still says the gate "never contacts an external
   endpoint"; the opt-in strict Lane E step runs `npm install` for the pinned
   lint toolchain, so the wording needs a qualifier.
2. The answer-scoring tolerance floor `1e-6·max(1,|expected|)` can override a
   tighter corpus-declared tolerance; a `1e-9` floor would be safer for the
   wrong-solve signal.
3. `hard_safety.all_zero` does not consider the `unscored` bucket (currently
   0); gate it explicitly.
4. `_score_solved_outputs` is invoked outside the runtime `try/except`; a
   scorer crash aborts the gate instead of degrading to a typed FAIL.
5. The verifier accepts any non-empty assumption citation; it could be
   tightened to accept citations only for equations binding assumption-sourced
   quantities (trust is currently compiler-side, symmetric with the evidence
   path).
6. ~400 gate-runner lines (suite subprocess plumbing, Lane E steps) have no
   direct unit tests; `__import__("re")` style in the summary parser.

## Hard-safety and privacy status

| Signal | Status |
|---|---|
| Catalog signals | 23 |
| **Individually measured this run** | **23** |
| **Unbound (NOT_MEASURED)** | **0** |
| **Nonzero** | **0** |
| Per-signal instrument registry | `IMPLEMENTED` (`phase56-stage7-hard-safety-registry-v1`) |
| External model calls | 0 |
| Measured cost | $0 |
| Private held-out access | 0 |
| Textbook PDF access | 0 |
| Raw corpus committed | no (path-supplied archive only) |
| Gold leakage in runtime material | 0 (enforced by import guard **and** a syntax-aware source guard, both tested in each direction) |
| Case-ID / family / filename / raw-text routing | 0 (enforced and tested) |
| Wrong solves (gold-scored) | **0** |
| Actual model quality | `NOT_RUN / N/A` |

Six signals rest on scorer/runtime counters; the other seventeen on 37 exact
attack node IDs the gate runs each strict run. A signal whose instrument does not
run reports `NOT_MEASURED` and fails strict mode — it never inherits a zero.

## Next exact task — B1, an implementation package

The next session's first action is the **B1 cohesive implementation package**
(slot-pin `radial_transverse` frame), not another audit, census or diagnostic.
The measurement phase is complete: six independent read-only audits and the
evaluator v3 package are done, and the ranked plan is recorded in
`docs/PHASE56_CLAUDE_CODE_HANDOFF.md` with its evidence in
`docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md` §6b-4 … §6b-7.

B1 creates exactly one `IRReferenceFrame` with `frame_type = radial_transverse`
and rebinds the query quantity's `frame_id` to it, inside a transaction following
the working `_DEFERRAL_ONLY_PROFILES` pattern. Every other conjunct of
`_slot_pin_relative_motion_issue` already holds 3/3; the frame is the only missing
one, and its identity is read from the corpus's own `moves_in_slot` relation.
Expected measured outcome: deferred **6/12 → 9/12**, supported unchanged, wrong
solves 0, `supported_downgraded_to_unsupported` 0.

Stated honestly: B1 raises the *deferred* class, not the supported count. The
first package that can raise **supported** is the co-required bundle B5+B6+B7,
because a frame alone unlocks zero laws (`frame_alone_unlocks = 0`, §6b-4).

Stage 8 must not start.
