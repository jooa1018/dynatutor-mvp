# Phase 56 Stage 7 — complete-profile closure: layer audit and measurement

Status: **STAGE_7_IN_PROGRESS**. Stage 7 is not accepted, Lane B is not passed,
and Stage 8 has not started. This document records what was audited, what was
built, and what the measurement actually says — including the places where the
measurement contradicted the plan and the plan was corrected rather than the
measurement.

## 1. Which layer closure belongs to

The question was whether a reusable, product-generic closure planner could be
added append-only, or whether closure must stay evaluator-only.

Evidence gathered by reading the code, not by assumption:

| Finding | Location |
|---|---|
| The Stage 6 modeler authors and repairs graph structure: `reference_frames`, `points`, `interactions`, `constraints`, `state_conditions` are all structural roots a model may write | `backend/engine/mechanics/modeler_repair.py` `_STRUCTURAL_ROOTS` |
| A multimodal revision may add or replace a reference frame outright | `backend/engine/mechanics/multimodal_revision.py:271` |
| The compiler synthesises **no** IR record; its only generated artifact is the query symbol | `backend/engine/mechanics/compiler/compiler.py` `_query_symbol_definition` |
| The Phase 55 parser adapter also hands over `reference_frames=[]`, `points=[]`, `constraints=[]` | `backend/engine/mechanics/phase55_adapter.py:555` |

The Draft is therefore the modeler's output contract, and graph structure is the
modeler's authority end to end. A **runtime** closure stage that created frames,
points, or interactions would move that authority from the modeler to the
server. That is the boundary change the Stage 7 instruction forbids making
silently.

**Decision: closure is evaluator-only.** It runs on the evaluator's own
projected Draft, where the corpus's typed gold structure plays the role the
modeler plays in production. The compiler, the law catalogue's emission
contracts, and the Stage 6 modeler contracts are unchanged by it.

### Product-path limitation

Nothing in `complete_profile_application.py` runs in the product path. A
production Draft that arrives without the frame and axis a law needs is still
blocked exactly as it was before. Closing that gap requires either the Stage 6
modeler to supply the full profile, or an explicit, separately reviewed decision
to move the authority boundary. This work does not make that decision.

## 2. The plan contract

`CompleteProfilePlanV1` (`backend/evaluation/phase56_stage7/complete_profile.py`)
is cleared before anything is built. It classifies every prerequisite as
`explicit_source`, `server_derivable`, `generated_unknown`, `missing`,
`ambiguous`, or `unsupported`, and carries exactly one verdict: `complete`,
`needs_confirmation`, `insufficient_information`, `unsupported`, or
`not_applicable`. The least recoverable failure wins, so a deferred capability
is never reported as a mere gap.

- **Planning does not mutate.** The plan records the fingerprint of the Draft it
  read; the offline gate re-fingerprints afterwards and fails the section if the
  digest moved.
- **A generated unknown asserts existence only.** Its value stays unknown and is
  decided by the solver.
- **Nothing reads identity.** No case ID, family, split, chapter, difficulty,
  tag, expected system type, expected terminal, expected answer, gold graph, or
  filename participates in any decision.

## 3. Transactional application

`apply_complete_profile` builds a whole new Draft and swaps it in only once it
validates. On any failure the caller keeps the exact Draft it passed in. No
intermediate Draft exists, so no half-built free body is ever runtime-visible.
A plan computed against a different Draft is refused rather than re-planned.

Only a profile whose partial-attachment hazards already have engine-level
negative controls may be enabled. Today that is one profile.

## 4. Engine-level partial-free-body controls

`backend/tests/test_phase56_mechanics_partial_free_body.py` was written **before**
any profile creates a force, and it found a real latent hazard: on a properly
evidenced IR, the engine emitted `particle_newton_second` over a half-built free
body in every one of these shapes, with status `ready`:

- contact plus a gravity force only — a block on a table accelerating at *g*;
- contact plus a normal only;
- gravity plus contact with an unstated friction regime;
- a rope pulling on one side only;
- a lone force on a constrained body, treated as the resultant.

`_free_body_is_complete` in `backend/engine/mechanics/laws/core.py` now withholds
the equation until the free body is closed, decided from typed structure alone:
a constraint that names the body must model a force on it; a contact's regime
must be stated by a typed state condition; a rope must name a force on each
body-like participant; and a single summed force against a constrained body
needs either a typed `resultant_force` authority or a stated friction regime.

The guard only ever *withholds* an emission. Two positive controls pin what must
still emit, including one accepted Stage 6 contract:

> A free particle's single stated force **is** its resultant. Nothing constrains
> it — no contact, rope, joint, spring, damper, or gear names it — so the
> resultant authority is required only where something else is acting on the
> body. This is narrower than the literal instruction ("a single force may be
> treated as a resultant only when a typed authority proves it"), and the
> difference is deliberate: applying the literal rule broke
> `test_single_particle_newton_same_fixture_full_parity_and_invariance`, an
> accepted Stage 6 contract that is physically correct. The accepted contract
> was kept and the guard was narrowed to the constrained case; no test was
> deleted and no threshold was relaxed.

## 5. The census

Measured over the authorised public corpus, 97 reachable contexts. Counts only —
the census records have no field that could hold a case ID, family, split,
problem text, expected terminal, expected answer, or gold graph.

| Profile | complete (source) | complete (server-derived) | needs_confirmation | insufficient | unsupported | n/a |
|---|---:|---:|---:|---:|---:|---:|
| free_flight_gravity | 0 | 2 | 0 | 6 | 0 | 89 |
| explicit_resultant_force | 0 | 0 | 0 | 9 | 0 | 88 |
| collision_restitution | 0 | 0 | 0 | 4 | 0 | 93 |
| fixed_pulley | 0 | 3 | 0 | 3 | 0 | 91 |
| incline_hanging_pulley | 0 | 3 | 0 | 3 | 0 | 91 |
| rolling_energy | 0 | 0 | 0 | 6 | 0 | 91 |
| work_energy | 0 | 0 | 0 | 6 | 0 | 91 |
| impulse_momentum | 0 | 0 | 0 | 0 | 4 | 93 |
| horizontal_contact | 0 | 0 | 0 | 0 | 10 | 87 |
| incline_contact | 0 | 0 | 0 | 3 | 0 | 94 |
| rigid_fixed_axis | 0 | 0 | 0 | 0 | 13 | 84 |
| relative_translating_frame | 0 | 0 | 0 | 0 | 9 | 88 |
| spring_vibration_deferred | 0 | 0 | 0 | 0 | 3 | 94 |

Highest-yield profile with a nonzero complete population: **`fixed_pulley`** (3).

The census corrected the plan three times, which is what it is for:

1. `impulse_momentum` first planned as source-grounded-complete. The emitter
   pairs its four quantities by component, so a source stating `left`/`right`
   does not reach it until a frame, an axis, and every component binding exist.
   That is one indivisible step — and it is why frame-only counterfactual
   unlocks measure zero.
2. `free_flight_gravity` first reported its gravitational field strength as
   missing when the approved authority already carries it as a closed server
   default.
3. `impulse_momentum` then planned as complete, and the transaction really did
   build the frame and reach `linear_impulse_momentum` — see below.

A thirteenth profile, `relative_translating_frame`, was added after the first
census round because the measurement showed the relative-motion cases stuck on a
missing observer frame rather than on a missing law.

## 6. Corpus/contract expectation issue: event-scoped impulse plans

The `impulse_momentum` transaction was implemented, applied cleanly, and the
compiler reached `ready` with `linear_impulse_momentum` emitted, rank 1, exactly
one unknown. The **solver** then refused the plan.

`run_backend` rejects any plan carrying event IDs unless the graph matches an
exact static-boundary waiver. The impulse waiver
(`_is_static_impulse_momentum_boundary_graph`) recognises only the three-law
shape — `linear_impulse`, `linear_impulse_momentum`, and `elapsed_time_positive`
together, two equalities plus one inequality, two unknowns, rank 2 — which needs
a force, a duration, and the authorities that license both.

A source that states the impulse outright and asks for the velocity after it is a
two-known, one-unknown algebraic problem. It cannot reach that shape, and
manufacturing a force and a duration to satisfy the waiver would be inventing
structure the source never states.

**This is reported as a contract expectation issue, not worked around.** The
planner now classifies `capability_event_scoped_solve_plan` as `unsupported` for
this shape, so the profile reports `unsupported` rather than claiming a
completeness it cannot deliver. Extending the waiver to the one-equation
endpoint shape is a solver-contract change that needs its own review; the
expected terminal was not rewritten and no structure was invented.

## 7. A deferral-only transaction

A profile can be fully modelled and still be one the engine declines. Building
its structure anyway is safe **because** it cannot produce an answer: it turns an
undifferentiated `underdetermined` graph into the precise refusal the engine
already knows how to make.

`relative_translating_frame` is exactly that case. The corpus states an observer
as an entity of primitive `reference_frame` and states one body's motion relative
to it. The compiler recognises that situation only as a typed frame *pair* — a
world frame, and a `translating` frame parented to it and carried by the observer
entity — and then defers with
`translating_frame_relative_acceleration_deferred`. Neither frame alone reaches
that recognition, so both frames, the axis, and every component binding are
created in one transaction. It creates no force and no interaction, so it cannot
assemble a partial free body.

`CompleteProfilePlanV1.structurally_complete` is what separates "the model is
complete" from "the engine will answer", and only a profile on the
deferral-only list may be built on the strength of it.

Three of the nine applicable contexts are structurally complete and are built;
they move from an undifferentiated compiler refusal to `verified_unsupported`
with a precise code, no answer, and no candidate. The other six — Coriolis and
slot–pin relative motion — state their directions as `radial`, `transverse`, and
`counterclockwise`, which name no closed spatial axis, so nothing is built and
they stay exactly as they were.

## 8. Public-100 at this head

| Terminal | Count |
|---|---:|
| solved | 6 |
| verified_unsupported (deferred capability) | 6 |
| needs_confirmation | 2 |
| needs_figure | 2 |
| insufficient_information | 1 |
| compiler underdetermined | 67 |
| compiler unsupported | 16 |

Against the frozen target of 81 / 12 / 2 / 2 / 2 / 1, the neutral terminals now
stand at 6 of 12 deferred, 2 of 2 needs_confirmation, 2 of 2 needs_figure, and
1 of 1 insufficient_information. Solved is unchanged at 6 and no case regressed.
The target was not lowered.

## 9. Read-only audit (same-model, not an independent Checker)

A fresh read-only pass over the whole diff found **0 blocking findings** and
three non-blocking hazards, all of which were then closed rather than recorded:

1. A declared `spring_oscillation` handed every Draft of that motion model an
   approved `angular_natural_frequency`, whatever the source asked for. With the
   stiffness re-owning that landed alongside it, that newly satisfied the
   precondition of `vibration_natural_frequency` — an emitter that writes
   ω² = k/m — for any query outside the compiler's period/frequency deferral
   guard. The authority now travels only with the readout it licenses.
2. The impulse transaction would have restamped a source-stated *magnitude* onto
   `+x`, handing the solver a sign the source never gave.
3. Both transactions rewrote the query's component unconditionally, so a
   magnitude question could silently become a signed-component one.

Each has a regression test. Closing all three moved no public-100 terminal.

Audited and found clean: case-ID/family/split routing, expected-answer and gold
leakage, raw-text keyword routing, direction and geometry preservation,
unsupported silent solve, needs-confirmation auto-selection, answer/graph
patching, root early discard, legacy fallback, report privacy, threshold
relaxation, test deletion, workflow mutation, network or provider imports, and
raw corpus commits. The free-body guard was confirmed to be purely withholding:
its single call site's entire effect is `continue`, so it can remove an emission
but never add one.

This was a same-model read-only audit. It is not represented as an independent
Checker.

## 10. Exact-head CI

All four workflows were dispatched against `eb595bef1ada2f8c00cfaf88ef3e400550621dbe`,
whose `backend/`, `.github/`, `scripts/`, and `frontend/` trees are byte-identical
to the code candidate `4cfd07b`; the only difference is this document.

| Workflow | Run | Result |
|---|---:|---|
| Phase 56 Stage 7 offline evaluation | `30190433296` | **SUCCESS** |
| Phase 56 Stage 6 multimodal | `30190434064` | **SUCCESS** |
| DynaTutor release tests | `30190436946` | **SUCCESS** |
| Phase 55 textbook parser | `30190437749` | **SUCCESS** |

### The release failure on the earlier head, and why it was a flake

An earlier dispatch against `d58b6c0` — before the audit fixes landed — reported
`DynaTutor release tests` as **FAILURE**. It was not an assertion failure:
`backend fast`, `backend quality`, `backend performance`, and `frontend` all
succeeded, and the failing step reported
`[run_with_timeout] timed out after 240s` on
`test_phase56_mechanics_incline_hanging_same_fixture_parity.py`.

Measured back to back on an idle machine, that shard runs **211.2 s** at this
head against **215.9 s** at the `6ed46e8` checkpoint, so the free-body
completeness check costs nothing measurable. The shard already consumed about
90% of its 240 s budget before this branch existed, and two shards run
concurrently on one runner. The re-run at `eb595be` passed, which confirms the
diagnosis: runner-load flakiness against a budget that is too tight for that
shard, not a regression introduced here.

The fragility is real and is left recorded rather than papered over: a shard at
90% of its timeout will fail again under load. Widening that budget, or splitting
the shard, is a separate change and was not made here.

## 11. What is not done

- Lane B is **IN_PROGRESS**, not passed.
- 6 of the 12 deferred cases reach `verified_unsupported`. The remaining 6 —
  Coriolis and slot–pin relative motion — need a rotating-frame profile whose
  angular directions (`radial`, `transverse`, `counterclockwise`) have no closed
  axis derivation yet.
- 81 solved is not reached: 6 solved. No profile in the census has a complete
  population that the solver will also accept.
- Lanes C, D, and E, the compositional 12, the synthetic 38, the metamorphic
  controls, and the hard-safety aggregate have not run in this session.
- No profile transaction is enabled on a real corpus context, because no
  measured plan reaches `complete` once the solver capability is accounted for.

`PUBLIC_EVALUATION_INFORMED_FIX` applies to every change recorded here: the
authorised public corpus was used to measure and to choose. No claim is made
about private generalization.
