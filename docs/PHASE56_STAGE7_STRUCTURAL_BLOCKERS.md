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
| Causal ownership diagnosis | `evaluation/phase56_stage7/query_readout_ownership.py` | `test_phase56_stage7_query_readout_ownership.py` (19) |

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
For each such context it adds **only** a typed query-readout binding — the source
Draft is not modified, no entity primitive is rewritten, nothing is added to the
free-body set — and asks the real `apply_core_laws` whether the queried unknown
is now written about. When it is not, the frame rung of the blocked-law ladder is
added on top.

| Outcome | `system` | `point` | `joint` |
|---|---:|---:|---:|
| binding alone unlocks | 0 | 0 | 0 |
| binding plus profile required | 0 | 0 | 0 |
| binding does not close | 0 | 12 | 3 |
| binding not formable | 12 | 0 | 0 |
| law not semantically applicable | 0 | 0 | 3 |

**`causally_blocked_on_ownership = 0`.** Building an aggregate, point, or joint
ownership capability would unlock **nothing** as the corpus stands.

**The zeros are load-bearing only because the instrument is shown to detect an
unlock when there is one.** `backend/tests/test_phase56_stage7_query_readout_ownership.py`
carries a positive control per primitive: a context complete in every respect
except that its readout sits on a `point`, a `joint`, or a `system`, each of
which classifies as `*_binding_alone_unlocks`. The same three shapes were also
reproduced against real projected contexts before the zeros were accepted.

### What each group is really blocked on

- **`system` (12) — `binding_not_formable`.** No typed record names the system
  alongside a body: `aggregate_contexts_with_membership_relation` is **0 of 12**.
  This is a property of the corpus, not of the projection — over the 13
  system-subject public cases, **0** have any `gold.relations` entry whose
  `participant_roles` include the system entity. What exists instead is
  co-scoping: all 12 share a motion interval with their bodies, and sharing an
  interval says the records describe the same stretch of motion, not that the
  aggregate is made of them.

  Whether co-scoping should count as membership is a contract question, and it
  was answered with a measurement rather than an argument:
  `aggregate_co_subject_route_unique_carrier` is **0 of 12**. Every one of these
  is a two-body system, so even if an interval's subject list were accepted as
  membership, the route names two carriers and cannot form a binding either.
  `aggregate_co_subject_route_unlocks` is **0**. **The contract question does not
  need to be settled**, because deciding it either way buys nothing.
- **`point` (12) — `binding_does_not_close`.** Here the binding *is* formable: each
  has exactly one carrier via a `lies_on` relation. It was formed, and neither it
  nor it-plus-a-frame produced a law that writes about the queried readout.
  Ownership is not the wall for these. Note also
  `contexts_with_typed_point_record = 0`: the projection produces no `IRPoint` at
  all, so the rigid-point laws have no point to be about.
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
`system`-owned readout is `binding_not_formable`, not a capability waiting to be
built. Nothing in the source states that the system is made of its two bodies.

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

## 5. `CORPUS_CONTRACT_MISMATCH`: magnitude questions and signed axes

63 of 97 questions ask for a `magnitude`. The closure applier deliberately
refuses to rebind a magnitude query onto a signed axis
(`_query_axis_conflicts`), because a question about a magnitude is a different
question from one about a signed component, and silently converting one into the
other hands the solver a sign the source never gave — a hazard already closed by
a regression test in the closure layer.

The engine does carry the bridge laws — `planar_acceleration_magnitude` and
`acceleration_magnitude_nonnegative` — and the diagnosis shows both blocked on
43 contexts each, with `missing_frame` on 21 of them. So the magnitude route is
not closed in principle; it is blocked behind the same missing frame as
everything else, and behind the aggregate-owner blocker of §4 where the two
overlap.

## 6. What is left, and in what order

Ranked by **measured** yield. Ownership has been removed from this list because
the measurement in §4 put its yield at zero.

1. **A frame-and-binding derivation shared across profiles** — every one of the
   97 contexts lacks a frame, and `frame_alone_unlocks = 0` says it only pays off
   bundled with the rest of a profile's structure. This is the only item with a
   measured population covering the whole corpus.
2. **Interactions** — 75 of 97 contexts carry none, so every free-body law has
   no force to sum whatever else is supplied. Like the frame, this is a
   per-profile transactional creation, not a standalone fix.
3. **Enabling the profiles whose plans already say `complete`** — 8 contexts
   across `free_flight_gravity` (2), `fixed_pulley` (3), and
   `incline_hanging_pulley` (3), each behind item 1 or 2 or both.
4. **The 39 contexts whose plans report `unsupported`** — these name declared
   engine capability gaps (`_catalogue_has_no_capability`,
   `_event_scoped_solve_plan`, `_relative_acceleration_capability`) and are
   solver- or compiler-contract changes.
5. **The remaining 37 `insufficient_information` contexts** — for each, decide
   whether the prerequisite is genuinely absent from the source or is derivable
   from a closed vocabulary the planner does not yet read.

**Not on this list: query-readout ownership.** It is measured at zero unlocks and
is not built. If items 1 and 2 land, re-run the ownership diagnostic before
reconsidering it — the `point` group's `binding_does_not_close` verdict was
reached against an engine with no frames and no typed points, and that verdict
could change once those exist.

## 7. What this document is not

It is not a reason to lower the target, and the target has not been lowered. It
is not a claim that 81 solved is unreachable — it is a statement of which
contract changes reaching it requires, each of which needs its own review rather
than being made silently inside a closure transaction.

No structure was fabricated to make any number better. No test was deleted, no
assertion weakened, no threshold relaxed. The public 100 distribution is
unchanged by the work this document accompanies.
