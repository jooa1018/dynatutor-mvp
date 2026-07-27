# Phase 56 Stage 7 — measured structural blockers on the Lane B distribution

Status: **`STAGE_7_IN_PROGRESS`**. Stage 7 is not accepted, Lane B has not
reached the frozen distribution, and Stage 8 has not started. This document
records what the remaining gap *is*, measured rather than estimated, so the next
package is chosen from evidence.

Every number below is reproduced by
`backend/tools/run_phase56_stage7_offline_gate.py` against the authorised public
archive, in the `structural_blockers`, `query_readout_ownership`,
`complete_profile_census`, `blocked_law_diagnosis`, and `lane_b` sections of the
redacted artifact.

| Measurement | Module | Tests |
|---|---|---|
| Structural blocker census | `evaluation/phase56_stage7/lane_b_structural_blockers.py` | `test_phase56_stage7_structural_blockers.py` (15) |
| Causal ownership diagnosis | `evaluation/phase56_stage7/query_readout_ownership.py` | `test_phase56_stage7_query_readout_ownership.py` (46) |

**A count is not a cause.** The census counts properties of contexts; the
diagnosis tests whether a property is what actually stops the answer. §4 is the
worked example of the difference, and of the correction it forced.

## 1. Where the distribution stands

| Terminal | Measured | Frozen target |
|---|---:|---:|
| solved | 6 | 81 |
| verified_unsupported (deferred capability) | 6 | 12 |
| needs_confirmation | 2 | 2 |
| needs_figure | 2 | 2 |
| insufficient_information | 1 | 1 |
| compiler underdetermined | 67 | 0 |
| compiler unsupported | 16 | 2 |

The neutral terminals are already exact. The gap is entirely the 83 contexts
that reach `underdetermined` or `unsupported`.

**The target is not arbitrary and was not lowered.** The corpus's own
`gold.future_expected_terminal` over the public 100 is 93 `accepted`, 2
`solver_gap`, 2 `needs_figure`, 2 `needs_confirmation`, 1
`insufficient_information`; 93 accepted is exactly 81 solved plus 12 verified
deferred. The frozen distribution is the corpus's expectation restated.

## 2. What the engine is actually doing

From `blocked_law_diagnosis` over 95 diagnosable contexts:

| Signal | Measured |
|---|---:|
| Emitter families that fire at least once | 2 of 22 |
| Emitter families that never fire | 20 |
| Contexts that emit nothing at all | 82 |
| Contexts unlocked by supplying a frame alone | **0** |
| Blocked-law counterfactuals: frame does not close the law | 150 |
| Blocked-law counterfactuals: law not semantically applicable | 162 |

Only `_constant_acceleration_emissions` (6 contexts) and
`_topology_constraint_emissions` (13) fire. Across the whole public 100 the
graph contains exactly two law IDs: `particle_constant_acceleration_position`
and `state_at_rest`.

`frame_alone_unlocks = 0` is the load-bearing measurement. It says the gap is
not one missing field per law — a law needs its frame, its axis, every component
binding, and its interaction quantities *together*, which is why closure has to
be transactional and why no incremental fix moves the count.

## 3. What the sources do not state

Over all 97 projected contexts:

| Absent structure | Contexts |
|---|---:|
| No reference frame | **97 of 97** |
| No interaction of any kind | 75 of 97 |
| Queried unknown owned by a non-free-body entity | 30 of 97 |
| Query asks for a `magnitude` | 63 of 97 |

The first row is the root cause of the second column of §2. The corpus schema
(`schema.json` in the authorised archive) has no reference-frame concept at all:
`gold` carries `entities`, `motion_segments`, `events`, `explicit_facts`,
`relations`, `assumption_proposals`, `queries`, and `answers`, and nothing else.
A source therefore *cannot* state a frame, an axis, or a per-quantity component
binding, however complete it otherwise is. The projection is faithful in
emitting `reference_frames: []`; it is not dropping structure.

What the corpus does state, in closed vocabularies the server may derive from:
11 relation kinds, 13 motion models, 9 assumption kinds, 12 fact directions,
6 query components, and 19 entity kinds.

## 4. The queried unknown's owner — a count, and what it turned out to mean

**30 of 97 contexts ask for a quantity owned by an entity no free-body law will
ever write an equation for.**

`free_body_primitive_names()` in `engine/mechanics/laws/core.py` is
`{particle, rigid_body, mass_center, body_component}`. `_newton_emissions`
skips any acceleration whose subject is outside that set, before completeness is
even considered.

| Queried unknown's owner | Contexts | A free body? |
|---|---:|---|
| `rigid_body` | 48 | yes |
| `particle` | 19 | yes |
| `point` | 12 | **no** |
| `system` | 12 | **no** |
| `joint` | 6 | **no** |

### That count is not a cause, and measuring it as one refuted it

An earlier revision of this document read the 30 as "up to 30 contexts an
ownership capability would unlock", and ranked that capability first. **That was
wrong.** A context can carry a non-free-body query subject and be blocked several
layers earlier, in which case binding the readout to a carrier changes nothing.

`evaluation/phase56_stage7/query_readout_ownership.py` settles it by experiment.
For each such context it adds a typed query-readout binding appropriate to the
subject's primitive — the source Draft is not modified, no entity primitive is
rewritten, nothing is added to the free-body set — and asks the real
`apply_core_laws` whether the queried unknown is now written about. Three rungs
are measured separately, each reported under its own name:

1. the binding alone;
2. the binding plus a frame;
3. the binding plus a **minimal force profile** — frame, axes, component
   topology, **and** a gravity interaction owning a force on each free body,
   because 75 of 97 contexts carry no interaction and a frame alone can never
   reach a free-body law. This rung measures **law emission only** and is named
   `binding_plus_minimal_force_profile_emits` for exactly that reason: nothing
   on it is validated, normalized, authorized, compiled, solved, or verified,
   so it must never be quoted as a solved or verified unlock. (An earlier
   revision named this rung `binding_plus_complete_profile_unlocks`, which
   overclaimed a pipeline it never ran; the rename is the correction.)

Each primitive gets the binding its readout actually needs. A point keeps its
identity and gains an owner plus a `point_id` and a typed point record; a joint
is bound only for the readout its role names; and an aggregate is bound to a
**proven member set**, never by picking a member.

The aggregate proof is scoped to the query, because a proof assembled from
someone else's structure proves someone else's aggregate. Only rope-topology
relations in the query's interval participate; they must form exactly one
member-bearing connected component unless the topology names the query system
itself; the component must carry rope evidence (a rope participant or a
`wraps`), because a bare `topology_connects` also projects from
`moves_relative_to`, which shares no magnitude; at most one `wraps` is
accepted, and its wrapped intermediary must be provably inert — not a free
body, not a rope endpoint, not attached to or resting on any free body, with
no motion readout in scope — so a movable pulley or any mechanical-advantage
assembly refuses; the approved `inextensible_rope` authority must belong to
this rope or to the query system itself, never to another rope, another
system, or a body; and the queried role must be one an inextensible rope
actually equates (displacement, velocity, speed, acceleration — never a
force). Every refusal is a code from the closed `AGGREGATE_REFUSAL_CODES`
vocabulary.

| Outcome | `system` | `point` | `joint` |
|---|---:|---:|---:|
| single-carrier binding alone unlocks | 0 | 0 | 0 |
| aggregate multi-carrier binding unlocks | 0 | — | — |
| point-scoped binding unlocks | — | 0 | — |
| joint-scoped binding unlocks | — | — | 0 |
| binding plus frame unlocks | 0 | 0 | 0 |
| binding plus minimal force profile emits | 0 | 0 | 0 |
| binding does not close | 11 | 12 | 3 |
| binding not formable | 1 | 0 | 0 |
| binding ambiguous | 0 | 0 | 0 |
| law not semantically applicable | 0 | 0 | 3 |

**`causally_blocked_on_ownership = 0`** across all three rungs.

### A correction to the previous revision of this section

An earlier revision reported `system` as **12 `binding_not_formable`** and said
no membership was provable. That was an artefact of a weaker instrument, and it
is wrong in an interesting way.

The aggregate proof does hold on eleven of the twelve: `topology_connects` and
`wraps` form one component naming both bodies together, and an approved
`inextensible_rope` authority whose subject is the query system covers the
interval, so the member set is `{member, member}` with one common magnitude.
What was missing was that the members carry no readout of the queried role for
the aggregate to be the common magnitude *of* — `aggregate_refusal_counts`
records `member_readout_missing` on **11 of 12**. Supplying those readouts as
unknowns, which is exactly what a profile does, forms the binding on all
eleven.

The twelfth is refused as **`role_not_rope_kinematic`**: its system question
asks for a **tension**, and inextensibility equates rates of motion, never
forces — a common tension needs a massless rope over an ideal pulley, a
different authority the proof does not hold. The earlier instrument formed
that binding anyway, which was unsound; the scoped proof refuses it, and the
refusal is the correction.

So the aggregate binding **is formable** where the physics says it is, is
formed, and still does not close. That is a stronger result than the previous
one, reached with a stronger instrument, and it says nothing was hiding behind
the earlier refusal.

**The zeros are load-bearing only because the instrument is shown to detect an
unlock when there is one.** `backend/tests/test_phase56_stage7_query_readout_ownership.py`
(46 tests) carries a positive control per binding shape, not merely per
primitive, and an attack suite that proves the aggregate proof is scoped: an
unrelated second rope topology, two independent rope systems, an inextensible
authority naming another rope, another system, or a body, a moving pulley in
three typed shapes, a pulley anchored to the environment (which must still
pass), a two-wraps and a rope-ends-on-pulley mechanical-advantage assembly,
cross-interval topology, relative-motion coupling without rope evidence, a
force-role system query, and renamed-ID variants of the attacks all decide
exactly as their structure demands:

- a **multi-member aggregate**: two bodies on one inextensible rope over a
  pulley, moving in opposite directions with one common magnitude, and a system
  question about that magnitude — which classifies as
  `aggregate_multi_carrier_binding_unlocks`, with negative controls proving that
  unconstrained members, members without a rope topology, a member missing the
  queried readout, an unrelated co-subject, and a **signed** system query all
  fail closed, and that renaming every entity changes nothing;
- a **point-scoped** binding that keeps the point entity, its primitive, and its
  geometry, and adds an owner, a `point_id`, and a typed point record;
- a **joint-scoped** binding that separates the pin's own kinematics — one
  motion whichever body you read it from, so two connected bodies are *not*
  ambiguous — from a one-sided reaction, which is ambiguous without a stated
  side.

The three primitive shapes were also reproduced against real projected contexts
before any zero was accepted.

### What each group is really blocked on

- **`system` (12) — 11 `binding_does_not_close`, 1 `binding_not_formable`.**
  The aggregate binding is formable on the eleven kinematic questions once
  member readouts exist, and forming it changes nothing at any rung. The
  twelfth asks for a tension, which inextensibility does not equate, so no
  common-magnitude binding exists to be formed (`role_not_rope_kinematic`).
  Note what is *not* the blocker here: no `gold.relations` entry names the
  system entity directly (0 of 13 system-subject public cases), but membership
  does not have to come from such a record — the rope topology names the
  members together, and that is what the common-magnitude proof rests on. The
  separate question of whether interval co-scoping should count as membership
  therefore never arises, and its own measurement confirms it would buy
  nothing: `aggregate_co_subject_route_unique_carrier` is **0 of 12**, because
  every one is a two-body system and that route names two carriers.
- **`point` (12) — `binding_does_not_close`.** Each has exactly one owner via a
  `lies_on` relation. The scoped binding was formed — owner, `point_id`, and a
  typed point record, with the point entity and its geometry left intact — and
  neither it, nor it plus a frame, nor it plus a minimal force profile produced a law
  that writes about the queried readout. Note also
  `contexts_with_typed_point_record = 0` in the source: the projection produces
  no `IRPoint` at all, so the rigid-point laws have no point to be about until
  something creates one.
- **`joint` (6).** Three are `binding_does_not_close` and three are
  `law_not_semantically_applicable` — for the latter the source declares no
  free-body entity anywhere, so no law in the catalogue is about them.

### Consequences for the contract audit

An ownership capability stays **unbuilt**, and `system`, `point`, and `joint`
stay **out** of the free-body set. No entity primitive is rewritten anywhere.

The audit asked whether a `QueryReadoutBindingV1` contract would be needed to
express these bindings, or whether the existing `Query.target`,
`target_quantity_id`, `point_id`, constraints, `lies_on` geometry, interactions,
and state conditions already suffice. **No new contract is introduced**, for a
reason that makes the expressiveness question moot: the capability such a
contract would serve has a measured yield of zero. Adding typed vocabulary for a
capability nothing needs would be structure with no consumer, which is the same
mistake the reference-frame package was already ruled out for.

For the record, where a binding *was* formable the existing contracts did
express it — the `point` group's carrier was resolved entirely from `lies_on`
geometry the source already states, with no new field.

Should the frame and interaction blockers below be closed, this diagnostic must
be re-run before ownership is ranked again: it measures the engine as it is, not
as it will be.

### Worked instance: the fixed-pulley contexts

The fixed-pulley walls below are still real, but note which one they are: the
`system`-owned acceleration readout **forms** an aggregate binding — the rope
topology names the members together and the approved authority covers the
interval — and the formed binding still `binding_does_not_close`. The wall is
that no law writes about the bound readout at any measured rung, not that
membership is unprovable. (An earlier revision reported `binding_not_formable`
here; that was the weaker instrument.)

`fixed_pulley` is the census's highest-yield profile — 3 of its 6 applicable
contexts plan `complete`. It is still not enabled, and the measurement says why.

A complete fixed-pulley Draft carries entities `system`, two `rigid_body`, a
`pulley`, and a `rope`; geometry `topology_connects` and `wraps`; approved
`massless_rope`, `inextensible_rope`, `massless_pulley`, `frictionless`, and
`constant_gravity`; two stated masses; three events; and one unknown — an
acceleration **owned by the `system` entity**, asked for as a `magnitude`.

Two independent walls:

1. **The generic path.** The queried acceleration belongs to `system`, so
   `_newton_emissions` never considers it (§4). Writing Newton for the two
   `rigid_body` members instead would produce equations about quantities the
   question does not ask for, with no typed law relating them to the system
   quantity that it does.
2. **The closed path.** `_massive_pulley_atwood_profile` is the engine's only
   Atwood recogniser. It requires exactly five entities as
   2×`particle` + `rope` + `pulley` + `environment`, a single `cartesian_3d`
   world frame, two `contact` points owned by the pulley, and
   `not context.events`. The corpus states `rigid_body` and `system` rather than
   `particle` and `environment`, and states three events. Reaching the
   recogniser would mean rewriting both — again, fabricating structure.

Note that `contexts_with_events = 97 of 97`: the `not context.events` condition
alone puts this recogniser out of reach for *every* context in the corpus, not
only the pulley ones.

## 4b. What the profiles planning `complete` are actually worth

The census reports 8 contexts planning `complete` across three profiles. That is
again a count, and again it is not the reachable population:

| Profile | complete | Query subject | Reachable? |
|---|---:|---|---|
| `free_flight_gravity` | 2 | `particle` | **built** — applied 2, solved 0 (below) |
| `fixed_pulley` | 3 | `system` | no — binding forms, does not close (§4) |
| `incline_hanging_pulley` | 3 | `system` | no — binding forms, does not close (§4) |

**The free-flight transaction is built and measured.** Both reachable
contexts close as one transaction — world frame, vertical binding, gravity
interaction, the authorized `server_default` gravity magnitude, and the
unknown vertical acceleration — and both pass validation, normalization,
authorization, and the compiler's provenance wall.  `uniform_gravity_acceleration`
now emits on both (their emission count was zero before), and both then stop
at a typed `underdetermined`: the graph does not determine the queried
unknown.  The two walls that remain are stated by the sources themselves —
one question's boundary event names a condition the source gives no value
for, and the other's launch is stated as a magnitude with an angle, which
needs a vector decomposition no closed rule currently derives.  Each is a
separate contract decision, measured here rather than assumed, and neither is
touched by this transaction.  **Measured full-pipeline yield: 0 solved of 2
applied**, public distribution unchanged, wrong solve 0.

### The event semantic package, and what it measured

The projection used to collapse the corpus's typed `highest_point` and
`lowest_point` event kinds onto a generic `reaches_condition`, which loses
boundary physics the source typed: at a smooth trajectory's vertical
extremum the **vertical velocity component** is zero — never the speed,
never the horizontal component.  That is closed now, end to end:

- `EventKind` gains `highest_point` and `lowest_point` (append-only), and
  the Stage 7 projection preserves the typed kinds (projection v2).
- Three engine boundary laws emit zeros **from typed event kinds alone** —
  `event_vertical_extremum_velocity` (v_y = 0 at a proven-vertical smooth
  extremum), `event_turnaround_axis_velocity` (the single proven motion
  axis's signed component), and `event_comes_to_rest_velocity` (the
  magnitude, plus — as a theorem, `|v| = 0` implies every component — the
  one proven axis component).  Fail-closed guards: the event must be a
  declared interval boundary (a segment-internal event is never promoted),
  the vertical must be proven by the subject's own gravity interaction and
  frame, impulsive structure (collisions, contact changes, rope snap)
  refuses the smooth zeros, an `at_rest` state condition keeps ownership of
  its instant, and any ambiguity — several candidates, several frames, an
  unproven axis — emits nothing.
- An evaluator event-boundary derivation stage (between closure and
  validation, transactional, full-Draft ID collision domain) creates the
  boundary unknowns those laws write about — existence only, never values —
  mirroring the laws' own conditions exactly so no dead unknown ever widens
  a graph.

**Measured on the public 100 (counts only): the distribution is unchanged**,
and the package engages exactly where the typed structure licenses it —
2 contexts derive boundary unknowns at `comes_to_rest` end boundaries
(a stated-deceleration time question and an impulse-to-stop question), and
`event_comes_to_rest_velocity` emits on both.  The free-flight pair is
**not** an event-semantics case after all, which this measurement is the
first to establish precisely:

- The time-question context's end boundary is typed `reaches_condition` —
  the corpus did not type it as an extremum — and no source fact values the
  condition, so the wall recorded above stands exactly as stated.  Its
  query-side gap — the question projecting as a `time`-role unknown while
  the algebraic endpoint laws consume a `duration`-role quantity — is
  **RESOLVED** by the elapsed-duration query binding (see the
  session-candidate hardening below); the context's remaining walls are the
  boundary-value gap above plus the typed records below.
- The angle context's `highest_point` event **is** typed — and is
  segment-internal (the interval runs launch → landing; the apex is
  mid-interval, and the question asks the height at that internal instant).
  The sub-interval contract decision has since been **made** — typed
  occurrence scope, below — so this context's remaining wall is exactly the
  §5 magnitude-with-angle decomposition, nothing else.

### The session-candidate hardening on top (Packages A–C, measured)

Three packages landed after the free-flight measurement, each verified
against the public 100 with a byte-identical distribution
(6 solved / 6 deferred / 2 + 2 + 1 blocked / 67 underdetermined /
16 unsupported, wrong solve 0) — pure contract hardening with no measured
regression and no reinterpreted target:

- **Event semantic authority (projection v3).**  A numeric-licensing event
  kind (`highest_point`, `lowest_point`, `turnaround`, `comes_to_rest`) no
  longer licenses its zero on the corpus label alone.  The corpus event's
  own `evidence_quote` is resolved to the exact, unique span of the problem
  text, recorded as `source_evidence`, and linked through
  `Event.evidence_refs`; missing, unresolvable, or ambiguous quotes fail
  closed (event preserved, licence withheld, gap reported per event over a
  closed vocabulary).  The engine law and the evaluator derivation now
  consume one shared eligibility contract
  (`engine/mechanics/laws/event_boundary.py`) instead of two hand-held
  copies, plus a bounded candidate-iff-consumption equivalence matrix.
  All ten licensing events in the public corpus carry exact unique quotes,
  so the gate costs zero measured engagement.
- **Typed occurrence scope (projection v4, the sub-interval decision).**
  `Event.occurs_in_interval_ids` (append-only) states that an instant lies
  strictly inside an interval; bounded and occupied are disjoint by
  contract validator, the Draft validator refuses forged interiority and
  foreign-subject occupancy, and the compiler holds the inverse
  reciprocity while its scope checks accept boundary-or-occupancy as an
  event's reach — 63 facts and 25 query targets regain their interval
  scope.  The physics unlocked is interior-extremum-only (Fermat), gated on
  Package A authority, a closed non-degenerate span, no impulsive
  structure, a unique *inertial* gravity frame, and exactly one candidate
  unknown.  The production Phase 55 adapter's segment-membership-as-
  boundary conflation is closed by the same package.
- **Elapsed-duration query binding (projection v5).**  A `time` question
  whose segment's interval declares both boundaries, distinct, and whose
  `event_role` is either absent or exactly that interval's own end, is the
  interval's elapsed duration — the same relational object the
  constant-acceleration laws multiply and the same rule the fact side
  already applied.  The rebind changes role/unit/dimension/event-scope
  only; start-event questions, interior instants, one-sided or degenerate
  spans, foreign intervals, and every `period` question decline and keep
  the plain `time` binding.  No epoch exists anywhere in the contract, so
  no `t0` can be invented.

The remaining typed gaps for the two public time contexts, recorded
exactly:

- `CORPUS_CONTRACT_MISMATCH` — **no query-side temporal role.**  The corpus
  query record carries no `temporal_role`, so an absolute-instant time
  question is unstatable and distinguishable from an elapsed one only
  through `event_role`.  Sufficient for the public 100; an explicit
  `queries[].temporal_role` mirroring `explicit_facts[].temporal_role`
  would make the proof direct instead of inferred from absence.
- `CORPUS_CONTRACT_MISMATCH` — **no root-selection authority.**  The
  flight-time question's gold is the positive root; the engine can only
  exclude the launch root via `elapsed_time_positive`, which is gated on a
  `strictly_positive_duration` authority the corpus assumption vocabulary
  cannot express.
- `ENGINE_CONTRACT` gap (**RESOLVED**) — **the solver waiver for the
  evidenced-extremum constant-acceleration shape.**  First measured live on
  a synthetic fixture: the duration binding closed the graph
  (`event_vertical_extremum_velocity` +
  `particle_constant_acceleration_velocity` +
  `uniform_gravity_acceleration`, 3 equations) and the solver's
  static-boundary waiver vocabulary refused the event-scoped plan.  The
  waiver has since landed as its own reviewed solver-contract decision
  (`_is_static_extremum_boundary_constant_acceleration_graph`, exact in
  the same way as its siblings, with nine structural near-miss controls),
  together with two provenance completions it surfaced: the uniform-gravity
  emission now cites the approved `constant_gravity` authorization that
  licensed its server value, and the independent verifier's
  provenance-presence rule accepts an approved-assumption citation exactly
  where a source span cannot exist (an equation citing neither still
  fails).  The synthetic fixture now solves end to end — one candidate,
  independently verified, `t = v0/g` — and the public 100 is byte-identical
  before and after, which is the honest shape of a capability the corpus
  cannot yet reach: the two public free-flight contexts stay behind their
  own recorded walls above.

25 positive/negative controls in
`test_phase56_stage7_event_boundary_semantics.py` hold the package: the
speed is never zeroed at an extremum, the stated initial velocity is never
touched, another subject's or another interval's event licenses nothing,
unproven frames and axes fail closed, unrelated `reaches_condition` events
emit nothing, ID/order/gold-metadata tampering changes nothing, and the
production path never imports the derivation module.

Six of the eight ask for a readout owned by an aggregate, and the formed aggregate
binding does not close at any measured rung — no law writes about the bound
readout even with a frame and a minimal force profile supplied — so no
transaction can deliver them regardless of how the profile recogniser is
generalised. Generalising the Atwood recogniser — over a query-relevant connected
subgraph, tolerating unrelated events, accepting a `rigid_body` as a
translational body — was audited against these six and would move none of them,
because the wall is what emission does with the readout and not the
recogniser's shape.

### `ENGINE_CONTRACT_BLOCKER` (RESOLVED): `server_default` provenance was unreachable from Lane B

A prototype `free_flight_gravity` closure was built and run against the two
reachable contexts to measure the profile rather than assume it. Both were
rejected at validation, with one issue:

```
provenance_violation  quantities.N
server_default requires both explicit approval and one exact immutable
assumption authorization
```

The profile's gravitational field strength is the closed server default its
approved `constant_gravity` authority already carries — the assumption states
`proposed_role: gravity`, `proposed_value: "9.81"`, `proposed_unit: "m/s^2"`,
with a matching subject and interval, so no value would be invented. But a
`server_default` quantity additionally requires an `AssumptionAuthorization`
entry in the `authorized_assumptions` map passed *into* `validate_draft`, and
that map is out-of-band: `normalize_draft` only forwards whatever it is handed,
and the only callers that build one are `modeler.py`, `phase55_adapter.py`, and
`compiler.py`. **Lane B passes none**, so no evaluator-only Draft transaction can
introduce a `server_default` quantity at all.

Two ways out, and both are contract decisions that need their own review rather
than a silent choice inside a closure transaction:

1. Let the evaluator derive an `AssumptionAuthorization` from an approved
   assumption's own `proposed_role` / `proposed_value` / `proposed_unit`. Nothing
   is invented — the authority states all three — but it moves who may author an
   authorization, which is the boundary the closure layer exists to respect.
2. Leave the boundary alone, in which case `free_flight_gravity` cannot supply
   gravity and its reachable population is 0 rather than 2.

**RESOLVED — option 1, as its own reviewed stage, not a choice inside a
transaction.** `evaluation/phase56_stage7/lane_b_authority.py` adds an
evaluator-only authority stage between projection and validation.  It builds
one immutable `LaneBAuthorityBundleV1` per projected Draft — the approved IDs,
an `AssumptionAuthorization` per approved assumption of a closed value policy
(today exactly `constant_gravity` at `gravity / 9.81 / m/s^2`), a fingerprint
of the source Draft, and a fingerprint of the bundle itself.  Authorization
restates the approved record's own proposal, to the character, and invents
nothing; anything else — wrong role, value, unit, subject, or interval,
unapproved dispositions, duplicates, competitors, a stated fact for the same
role — fails closed under a bounded refusal vocabulary.  The bundle verifies
against exactly its own Draft revision, so replaying it against another case,
another revision, or a mutated Draft refuses.  `run_lane_b_case` verifies the
bundle before validation and hands the **same immutable map** to both
`validate_draft` and `normalize_draft`.  26 bundle/attack regressions in
`test_phase56_stage7_lane_b_authority.py` and the runner tests hold the
boundary.  The closure layer still cannot mint authority — it can only consume
what this stage issued.

The free-flight transaction now spends this authority (see §4b): the two
reachable contexts close, carry a real `server_default` gravity quantity, and
pass the validator's and the compiler's two-key walls with the same immutable
map.  The public distribution is still unchanged — the measured full-pipeline
yield of the profile is zero solved, for reasons §4b records — and that is
the honest outcome of running the real path rather than predicting it.

### Residual safety audit of the two stages above (closed)

Two residual gaps were audited in the authority stage and the transaction
layer after they landed, and both are closed:

1. **The bundle's competing-stated-fact check was role-global.**  A stated
   gravity fact for *any* subject anywhere in the Draft refused the
   `constant_gravity` authorization for every subject.  The check is now
   scoped to the physical identity of the value policy's role — same subject,
   overlapping interval or event scope — with event reach proven from the
   typed structure (`Event.interval_ids` plus the interval's own boundary
   declarations).  A stated fact for another subject, another interval, or an
   event provably attached only elsewhere refuses nothing; an unscoped stated
   fact, a dangling event reference, or an attachment-free event still fails
   closed.  Component and frame deliberately do not separate competitors for
   the gravity policy, whose role is a magnitude invariant.  The public
   distribution is unchanged by this scoping — no reachable context was
   waiting on it — which is the measured result, not an assumption.

2. **The transaction ID collision domain covered four namespaces.**  The
   free-flight precheck collided generated IDs against quantities, symbols,
   interactions, and frames only; a generated ID equal to an authored entity,
   event, constraint, assumption, or any of the other Draft namespaces would
   have spliced the created records into the existing reference space.  All
   three enabled transactions now collide their generated IDs against every
   ID-bearing namespace of the Draft contract — 18 namespaces, one domain —
   before anything is built, and a hit abandons the transaction whole with
   the caller keeping the exact Draft it passed in.

Both closures are attack-covered in `test_phase56_stage7_lane_b_authority.py`
(identity scoping, order/rename invariance, fail-closed event scopes) and
`test_phase56_stage7_free_flight_closure.py` /
`test_phase56_stage7_profile_application.py` (per-namespace collisions,
multi-namespace collisions, byte-identical refusal end to end).

## 5. `CORPUS_CONTRACT_MISMATCH`: magnitude questions and signed axes

63 of 97 questions ask for a `magnitude`. The closure applier deliberately
refuses to rebind a magnitude query onto a signed axis
(`_query_axis_conflicts`), because a question about a magnitude is a different
question from one about a signed component, and silently converting one into the
other hands the solver a sign the source never gave — a hazard already closed by
a regression test in the closure layer.

### 5a. `CORPUS_CONTRACT_MISMATCH` (AUDITED, NOT IMPLEMENTED): the magnitude-with-angle launch

The remaining free-flight context states its launch as a speed magnitude and
an angle, and the causal audit ran **before** any implementation, as
required.  Measured on the real projected context (counts and typed shapes
only):

- exactly one stated velocity magnitude and exactly one stated angle, same
  subject, same interval, same launch event — the uniqueness and scope
  prerequisites hold;
- the angle's unit is `°` — degrees are unambiguous;
- the angle quantity carries **no typed reference axis**: component
  `unspecified`, no direction binding, no frame, no geometry relation
  referencing it (the context's geometry is empty), and no principle hint;
- the corpus's own closed vocabulary has no construct that could state the
  reference: the semantic key is the bare `angle`, and no relation kind in
  the corpus contract names an axis, a horizontal, or an angle-between
  construct the projection could type.

Whether `theta` is measured from the horizontal or the vertical is therefore
not provable from source structure, and the rule is absolute: without that
proof, `v_x = v·cos(theta)` / `v_y = v·sin(theta)` may not be built — the
wrong choice silently swaps sine and cosine and produces a confident wrong
answer, which is exactly the hazard the hard-safety gate forbids.

**Verdict: `CORPUS_CONTRACT_MISMATCH` — no closed decomposition rule is
implementable against the current corpus contract, and none was
implemented.**  Closing this wall requires a corpus-contract extension (a
typed angle reference — for example an `angle_from_axis` relation naming the
axis entity or frame axis, with orientation), which is an upstream contract
decision, not an evaluator or engine patch.

The refused state is pinned by 17 controls in
`test_phase56_stage7_angle_decomposition_refusal.py`, and the hard gate is
**structural**, not nominal: a scan over the emission and compiled-equation
surfaces (`evaluation/phase56_stage7/angle_reference_axis_controls.py`)
flags any equation that touches the axisless angle at all, combines it with
the launch magnitude, carries the angle's exact numeric trig fingerprint as
a folded literal (the engine's own idiom, invisible to symbol scans and —
when provenance is dropped — to provenance scans), or wields sign machinery
near the magnitude.  No law ID is read, so a renamed decomposition changes
nothing; positive controls prove detection of a renamed rule on three
surfaces — a hand-built emission, the real `apply_core_laws` aggregation,
and the compiled `EquationNode` shape.  The old name-marker check survives
as an auxiliary tripwire only.  The rest of the pin is unchanged: the
unproven shape emits no component equation under the original form or the
attack variants (another subject's angle; answer removal and answer
tampering change nothing), two competing angles at one physical identity
fail closed at projection (`duplicate_canonical_symbol`), the full lane
stays a typed blocked terminal with no stage exception, the launch pair
keeps its directionless identity across Draft and IR, no signed launch
component ever appears, and the closed quantity registry is pinned to
exactly the authored set — no negative magnitude, no invented sign, no
quadrant choice anywhere.

Also measured while auditing: the same context's `highest_point` event is
typed but **segment-internal** (see §4b), so its apex instant additionally
needs a sub-interval contract decision before any endpoint law could use it.
The two free-flight walls therefore both end at the corpus contract, and the
free-flight residual work inside the current contract is complete.

The engine does carry the bridge laws — `planar_acceleration_magnitude` and
`acceleration_magnitude_nonnegative` — and the diagnosis shows both blocked on
43 contexts each, with `missing_frame` on 21 of them. So the magnitude route is
not closed in principle; it is blocked behind the same missing frame as
everything else, and behind the aggregate-owner blocker of §4 where the two
overlap.

## 6. What is left, and in what order

Ranked by **measured** yield. Ownership has been removed from this list because
the measurement in §4 put its yield at zero.

### 6a. The profile-isolated feasibility matrix (measured, counts only)

**Superseded instrument note.**  This section's previous revision ran the
first-wins closure once per context, credited the declaration-order winner,
and stamped every other applicable profile
`profile_transaction_not_formable` — so an unbuilt profile's "verified
yield 0" was a definition, and the claim "every class is proven producible
by positive controls" rested on hand-constructed LaneBResult objects, not
on pipeline paths.  Both statements are retracted.  Two corrections to the
old prose while retracting it: `compiler_underdetermined` (equations > 0)
had never actually been observed — every underdetermined component carried
0 equations — and the lane does reach 6 verified solves, all in contexts
with **no** applicable profile, which the old table never said.

The corrected instrument (`profile_feasibility.py` v2-isolated) plans and
applies **each selected profile independently against the pristine
projected Draft** and runs the full lane from there
(`run_lane_b_case_with_selected_profile`); declaration order enters
nowhere, first-wins enters nowhere, and an unimplemented profile is
`profile_not_implemented` — *not measured* — never a yield zero it never
earned.  `compiler_unsupported_reachable` requires an exact typed compiler
issue code from the closed precise whitelist
(`requires_specialized_model`, `consistency_inconclusive`); everything
unnameable lands in an explicit `harness_unclassified` residual.

Measured at this head over the 97 projected contexts:

| Profile | implemented | applicable | measured | isolated statuses |
|---|---|---:|---:|---|
| `free_flight_gravity` | yes | 8 | 8 | `compiler_no_equation` ×2, `profile_plan_not_formable` ×6 |
| `impulse_momentum` | yes | 4 | 4 | `profile_plan_not_formable` ×4 |
| `relative_translating_frame` | yes | 9 | 9 | `verified_deferred_reachable` ×3, `profile_plan_not_formable` ×6 |
| `rigid_fixed_axis` | no | 13 | 0 | `profile_not_implemented` ×13 (not measured) |
| `horizontal_contact` | no | 10 | 0 | `profile_not_implemented` ×10 (not measured) |
| `explicit_resultant_force` | no | 9 | 0 | `profile_not_implemented` ×9 (not measured) |
| `fixed_pulley` | no | 6 | 0 | `profile_not_implemented` ×6 (not measured) |
| `incline_hanging_pulley` | no | 6 | 0 | `profile_not_implemented` ×6 (not measured) |
| `work_energy` | no | 6 | 0 | `profile_not_implemented` ×6 (not measured) |
| `rolling_energy` | no | 6 | 0 | `profile_not_implemented` ×6 (not measured) |
| `collision_restitution` | no | 4 | 0 | `profile_not_implemented` ×4 (not measured) |
| `incline_contact` | no | 3 | 0 | `profile_not_implemented` ×3 (not measured) |
| `spring_vibration_deferred` | no | 3 | 0 | `profile_not_implemented` ×3 (not measured) |

Positive controls are real end-to-end selected-profile paths for every
status an implemented profile can reach at this head:
`verified_deferred_reachable`, `compiler_no_equation`, `solver_rejected`
(the synthetic apex-time fixture: applied free flight, 3 equations, the
solver's static-boundary waiver gap), `profile_transaction_rejected`,
`profile_plan_not_formable`, and the `profile_not_implemented` distinction
inside one context (a pulley-overlap fixture where free flight measures
and fixed-pulley is honestly unmeasured).  Declaration-order permutation,
enum-order permutation, case-order reversal, and identity tampering all
leave the matrix byte-identical; a fixture where the closure applies
nothing still measures each profile's own verdict.

`verified_solve_reachable` has since gained its real producer: the solver
waiver identified above landed (see §4b), and the evidenced-extremum
fixture now demonstrates the full chain — selected free-flight transaction
applied, three compiler equations, deterministic single-root solve,
independent verification with every check passed, wrong solve 0 — with the
public 100 byte-identical before and after.  `free_flight_gravity` is
therefore the first profile to qualify under the measured-yield rule, and
its measured corpus yield remains exactly its two recorded source-stated
walls.

Four statuses still have **no** applied-profile end-to-end producer at
this head, with the reasons themselves measured rather than assumed:
`solver_rejected` (the extremum waiver closed the one shape that used to
stop at the solver's door, and no implemented profile produces another
solver-reaching graph), `verification_rejected` (no admitted shape yields
a candidate the verifier then refuses), `compiler_underdetermined`
(every current law chain emits whole or not at all, so a pruned component
is closed or empty), and `compiler_unsupported_reachable` (no implemented
profile's exact shape coexists with a specialized-model refusal).  They
are unit-covered at the classifier and stay honestly unproduced.
`rigid_fixed_axis`'s 13-context population remains a census count, not a
measured claim of any kind.

1. **A frame-and-binding derivation shared across profiles** — every one of the
   97 contexts lacks a frame, and `frame_alone_unlocks = 0` says it only pays off
   bundled with the rest of a profile's structure. This is the only item with a
   measured population covering the whole corpus.
2. **Interactions** — 75 of 97 contexts carry none, so every free-body law has
   no force to sum whatever else is supplied. Like the frame, this is a
   per-profile transactional creation, not a standalone fix.
3. **Enabling the profiles whose plans already say `complete`** — **done for
   the measured population.** The reachable population was 2, not 8 (§4b);
   the authorization decision is resolved and the free-flight transaction is
   built, applied to both, and measured at 0 solved of 2 — their remaining
   walls are the two source-stated gaps §4b records (an endpoint boundary the
   source values nowhere, and a magnitude-with-angle launch with no closed
   decomposition rule). The six pulley contexts stay behind §4's
   binding-does-not-close wall.
4. **The 39 contexts whose plans report `unsupported`** — these name declared
   engine capability gaps (`_catalogue_has_no_capability`,
   `_event_scoped_solve_plan`, `_relative_acceleration_capability`) and are
   solver- or compiler-contract changes.
5. **The remaining 37 `insufficient_information` contexts** — for each, decide
   whether the prerequisite is genuinely absent from the source or is derivable
   from a closed vocabulary the planner does not yet read.

**Not on this list: query-readout ownership.** It is measured at zero unlocks
across all three rungs — binding alone, binding plus frame, and binding plus a
minimal force profile — with multi-carrier aggregate, point-scoped, and
joint-scoped bindings all exercised by passing positive controls. It is not
built. If items 1 and 2 land, re-run the diagnostic before reconsidering it: the
verdicts were reached against an engine whose contexts have no frames, no
interactions, and no typed points, and the minimal force profile measured here
is a law-emission counterfactual, not a pipeline run — nothing on that rung was
validated, normalized, authorized, compiled, solved, or verified.

## 6b. The exact blocking prerequisite of every profile, measured

§6's ordering was derived from plan-formability. Planning every profile against
every projected Draft and recording each prerequisite's own disposition gives
the blocker directly. Only `missing`, `ambiguous`, and `unsupported` are
failures; `explicit_source`, `server_derivable`, and `generated_unknown` are all
satisfied.

| Profile | Applicable | Closes | Blocking prerequisite(s) |
|---|---:|---:|---|
| `free_flight_gravity` | 8 | 2 | `authority_constant_acceleration: missing` ×6 |
| `impulse_momentum` | 4 | 0 | `capability_event_scoped_solve_plan: unsupported` ×4 |
| `relative_translating_frame` | 9 | 0 | `capability_relative_acceleration_readout: unsupported` ×9; also `axis_signed`/`component_binding: missing` ×6 |
| `explicit_resultant_force` | 9 | 0 | `authority_force_is_resultant: missing` ×9 |
| `rigid_fixed_axis` | 13 | 0 | `capability_rigid_point_authority` + `capability_body_fixed_frame: unsupported` ×13; `geometry_attached: missing` ×13; `quantity_radius: missing` ×7 |
| `horizontal_contact` | 10 | 0 | `capability_horizontal_surface_profile: unsupported` ×10; contact/gravity/friction/frame/point/regime `missing` ×7 |
| `work_energy` | 6 | 0 | `quantity_displacement` + `authority_constant_force: missing` ×6; mass/force `missing` ×3 |
| `rolling_energy` | 6 | 0 | `quantity_gravity: missing` ×6 |
| `collision_restitution` | 4 | 0 | `authority_external_impulse_negligible: missing` ×4 |
| `fixed_pulley` | 6 | 3 | `authority_fixed_pulley` + `point_contact: missing` ×3 |
| `incline_hanging_pulley` | 6 | 3 | `quantity_angle: missing` ×3 |
| `incline_contact` | 3 | 0 | `quantity_mass`, `quantity_gravity`, `state_contact_regime: missing` ×3 |
| `spring_vibration_deferred` | 3 | 0 | `capability_period_readout: unsupported` ×3 — correct; this profile is *meant* to defer |

Two blocker families dominate: an **`authority_*` the source never states**
(22 contexts) and a **declared `capability_*` the engine does not have**
(39 contexts).

### 6b-1. The §6 first-priority item does not survive measurement

§6 named `free_flight_gravity`'s six `profile_plan_not_formable` contexts as the
next package. A counterfactual settles it: grant those six the
`constant_acceleration` authority they lack — the *only* prerequisite any of
them fails — and run the real lane.

```
contexts blocked ONLY on authority_constant_acceleration
  baseline terminals: {'compiler_unsupported': 6}
  counterfactual    : {'compiler_unsupported': 6}
  compiler codes    : {'requires_specialized_model': 6}
```

**Measured yield: zero additional solves.** Granting the authority is not what
unblocks these contexts.

The counterfactual was then instrumented a second time, to check *why* — and
the second reading is the one that matters, because the first would have been
misread as "a closed free flight yields nothing":

```
ctx1  plan=complete  applied=None                 rejected: profile_shape_not_closable
ctx2  plan=complete  applied=None                 rejected: profile_shape_not_closable
ctx3  plan=complete  applied=None                 rejected: profile_shape_not_closable
ctx4  plan=complete  applied=None                 rejected: profile_shape_not_closable
ctx5  plan=complete  applied=free_flight_gravity  frames 0->1  interactions 0->1  quantities 3->5
ctx6  plan=complete  applied=None                 rejected: profile_shape_not_closable
```

Three separate facts, and they must not be collapsed:

1. The authority genuinely was the only *plan* blocker — all six plans become
   `complete` once it is granted.
2. **The transaction then refuses five of the six** on its own narrowness
   guards. `_free_flight_gravity_transaction` returns `None` — and so
   `profile_shape_not_closable` — for a Draft that already carries a gravity
   quantity, a gravity interaction, or an acceleration for this subject and
   interval, or whose stated directions bind a horizontal axis. A complete plan
   is therefore not a closable shape, and the two are measured separately.
3. The one context that *did* close — a real closure: a frame, an interaction,
   and two quantities created — still ended at
   `compiler_unsupported :: requires_specialized_model`.

So the honest conclusion is narrower than "free flight is worthless" and
stronger than "free flight is next". It is: **the missing authority is not the
binding constraint**, the transaction's shape guard is the next wall for five of
these six, and for the one that clears both walls the compiler still declares a
specialized model. Building the authority alone moves plan dispositions and not
one terminal.

This is the same lesson §4 records, one layer further in: a count is not a
cause, and a *plan verdict* is not a cause either. The rule in the master
instruction — rank by measured full-pipeline verified yield, not by structure
counts — is what caught it, and the ranking in §6 is superseded to that extent.
An earlier draft of this section read the first measurement alone and concluded
that a closed free flight yields zero; instrumenting whether closure had
actually run refuted it. The instrument, not the number, is the finding.

Note also that the corpus never proposes `constant_acceleration` anywhere: its
assumption vocabulary over the public 100 is `constant_gravity` 38,
`frictionless` 18, `starts_from_rest` 13, `massless_rope` 12,
`inextensible_rope` 12, `massless_pulley` 9, `pure_rolling` 6,
`no_air_resistance` 5, `ends_at_rest` 2. The kind reaches a Draft only through
`_MOTION_MODEL_ASSUMPTIONS`, from a source-declared
`constant_acceleration_1d`/`projectile_free_flight` motion model. A prerequisite
demanding it of a context whose model is `unknown` can never be satisfied from
the source — but, per the counterfactual above, satisfying it changes nothing.

### 6b-2. What the engine actually emits over the whole corpus

| Signal | Measured over 100 |
|---|---:|
| Distinct laws that fire at all | **2** (`particle_constant_acceleration_position`, `state_at_rest`) |
| Total equations produced | **12** |
| Candidates generated / verified | 6 / 6 |
| Rejected candidates | 0 |

Twelve equations across ninety-seven executed contexts. Set against a backend
regression of 3,941 passing tests, twelve passing compositional structures, and
same-fixture parity suites for Atwood, inclines, pulleys, rolling, collisions,
vertical circles, fixed-axis rotation, plane rigid bodies and polar kinematics,
the conclusion is not that the engine lacks the physics. **The engine's laws are
never made eligible.** The projected Drafts carry no reference frames, no typed
axes, no interactions, and no contact points, and the complete-profile closure
that exists to supply exactly that structure is built for 3 of 13 profiles.

The remaining 75 supported solves are therefore blocked on profile
*transactions*, not on new physics: each unbuilt profile must create, as one
all-or-nothing transaction, the typed structure its already-implemented laws
require. That is bounded, and the table above names the specific prerequisite
each one must resolve — but it is thirteen transactions plus the two
`capability_*` families, each needing its own positive control, near-miss
negatives, authority attack, and physics-changing control before it may count.

And per §6b-1, each one has **three** walls to clear, not one: the plan must
form, the transaction must accept the shape, and the compiler must then have a
law rather than a specialized-model declaration. A package that clears only the
first two moves no terminal. Every future package on this list should be
measured the way §6b-1 measures it — plan disposition, application outcome, and
lane terminal reported separately — because any single one of the three read
alone gives the wrong answer.

### 6b-3. The blocked classes fail for the same reason, not their own

The 19 non-supported cases were measured individually against what the runtime
actually produces for them:

| Expected class | Count | Reached |
|---|---:|---|
| `needs_figure` | 2 | `needs_figure` — exact |
| `needs_confirmation` | 2 | `needs_confirmation` — exact |
| `insufficient_information` | 1 | `insufficient_information` — exact |
| `deferred_unsupported` | 3 | `verified_unsupported :: translating_frame_relative_acceleration_deferred` — exact |
| `deferred_unsupported` | 3 | `verified_unsupported :: free_linear_vibration_readout_deferred` — exact |
| `deferred_unsupported` | **6** | `compiler_failure :: underdetermined` |
| `unsupported_other` | **2** | `compiler_failure :: underdetermined` |

The eight failures are *not* a deferral-detection gap. The compiler carries
`rotating_frame_relative_acceleration_deferred` and
`slot_pin_relative_motion_deferred` already, and both detectors are written and
exact. They never fire because they require a rotating frame with a
`rotating_about_point_id`, radial/transverse component bindings, and matched
angular-velocity carriers — none of which any projected Draft has, for the same
reason §3 gives: the corpus schema cannot state a frame, and no transaction
supplies one for these shapes. The graph is underdetermined before the deferral
question is ever asked.

So a single root cause explains the whole remaining gap — 75 supported, 6
deferred, and 2 unsupported-other alike. Closing it is one body of work, not
three, and it is the closure layer rather than the compiler, the solver, or the
verifier.

**Consequence for sequencing:** the deferred and unsupported-other classes must
not be chased separately or early. Emitting a deferral for those eight from
anything less than the same typed structure would be a shortcut to the target
distribution — and the scorer added in `phase56-stage7-evaluator-v2` is
specifically built to catch it, since a deferred case must carry an exact
`COURSE_SCOPE_DEFERRED_ISSUE_CODES` proof and an unsupported-other case must not
carry one.

## 6c. Known non-blocking evaluator issues, carried forward

An independent read-only Checker audited the evaluator changes of this session
and returned two blocking findings, both fixed (hard safety blind to five
blocked classes; a tolerance conversion that was not delta-safe for offset
units). Four non-blocking observations are recorded here rather than fixed,
because each would need its own code candidate, CI cycle and strict re-run, and
none is reachable through the real pipeline today.

1. **`residual_verification` and `candidate_coverage` add no independent
   evidence.** `_score_supported` accepts any single non-empty, all-passing
   check tuple; it never names the kinds a solved candidate must carry. A
   fabricated record whose only check is `("anything_at_all", "passed")` passes
   `strict_residual_verification_100_percent`. Unreachable in practice —
   `engine/mechanics/verification/contracts.py` refuses an answer verdict
   missing graph-required check kinds, and all six real solved cases carry
   `equation_residual`, `unit_consistency`, `query_binding`, `source_evidence`,
   `constraint` and `nonnegative_time`, all passed. **Fix:** require at minimum
   `equation_residual`, `unit_consistency`, `query_binding` and
   `source_evidence`, which §6.2 of the acceptance criteria already mandates;
   leave `constraint` and `nonnegative_time` graph-dependent.
2. **No float slack on the tolerance comparison.** `2.0 + 1e-4` scores *wrong*
   against a declared `1e-4`, because `(a+t)-a > t` in binary floating point.
   This errs strict and is documented by its test, but "applied exactly" is
   very slightly overstated.
3. **`_distribution_matched` never pins 81/12/2/2/2/1** — it checks internal
   consistency only. The frozen counts are pinned in `_strict_requirements`
   under `require_full`, and `verify_corpus_semantics` fails closed on
   `scope_terminal_count_mismatch`, so it is not exploitable.
4. **Three gaps in pre-existing hard-safety evidence**, listed in
   `PHASE56_STAGE7_EVALUATION_CONTRACT.md`: an unreferenced
   `FORBIDDEN_RUNTIME_SOURCE_TOKENS`, no static guard against logging image
   bytes, and a correction-path attack test that never injects a graph-shaped
   key. These belong to the per-signal instrument registry, which is not built.

## 7. What this document is not

It is not a reason to lower the target, and the target has not been lowered. It
is not a claim that 81 solved is unreachable — it is a statement of which
contract changes reaching it requires, each of which needs its own review rather
than being made silently inside a closure transaction.

No structure was fabricated to make any number better. No test was deleted, no
assertion weakened, no threshold relaxed. The public 100 distribution is
unchanged by the work this document accompanies.
