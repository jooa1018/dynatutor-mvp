# Phase 56 Stage 7 — public corpus v2 candidate contract

Disposition: **`V2_CANDIDATE_CORRECTED — first pilot cohort closed in shadow`**

This document records a *candidate* contract and an *experimental* measurement.
The frozen v1 public corpus is unchanged, the v1 acceptance target is unchanged,
`STAGE_7_IN_PROGRESS / NOT_ACCEPTED` stands, and Stage 8 has not been started.

---

## 0. The corrected checkpoint (2026-08-01) — supersedes §2, §6 and §7 below

An independent audit found three blocking defects in the first candidate, and
this session corrected them forward-only.  The sections below are kept as
written; where this section contradicts them, this section is the record.

### 0.1 The three defects, corrected

**C1 — the audit misclassified the query objective** (`fix(stage7): trace
source-stated query objectives correctly`).  §2's table says seven engine
carriers have no source field and lists `query_objective` among them.  That was
wrong: the B12 repair already maps the controlled v1 output key
`minimum_speed` onto the Draft's typed `Query.objective = minimum`, and the
official projection has consumed that mapping all along.  The mapping now
lives in one canonical table (`query_objective_sources.py`) consumed by both
the projection and the audit; lookup is exact membership in the closed
vocabulary — no substring reading, no problem-text search, and no `maximum`
member because the v1 vocabulary has no admissible-set-maximum key
(`max_height` is an exact apex readout).  The machine-measured source-contract
omission count is **6**, not the hand-written seven, and the B12 revocation's
remaining blockers — the contact side and the boundary states — are recorded
separately from the objective.

**C2 — augmentation could overwrite v1 meaning** (`fix(stage7): make v2
augmentation fill-only and conflict-safe`).  The first projection wrote a v2
objective, frame binding, direction, or contact side over whatever the v1
Draft already held.  One canonical merge contract (`corpus_v2/merge.py`) now
governs migration and projection alike, decided against the original payload
before anything merges: an empty field may be filled; a semantically identical
restatement is a deterministic no-op that keeps the original record; a
differing restatement fails closed with a closed reason code
(`objective/contact_side/frame_binding/direction/motion_scope/endpoint/
constraint/scalar_encoding _conflicts_with_source`,
`augmentation_would_overwrite_source`); and a narrower or wider scope is a
conflict, never a merge — an event-scoped fact cannot widen to an interval and
an interval fact cannot silently narrow.  A conflicting manifest entry now
fails the migration itself (`augmentation_conflicts_with_source`) before any
candidate archive exists.

**C3 — the frame projection produced shapes the engine never licensed**
(`fix(stage7): project v2 frames as typed axis bindings`).  The first
projection anchored every frame — the world frame included — on a pseudo
entity, emitted `kind=semantic` axis directions, and collapsed opposite senses
onto one value with the sign lost.  Corrected to the engine's own contract: a
stated world frame projects `origin.kind = world` (the v2 record gains an
additive `origin_kind` vocabulary with validation — world origins carry no
point, only the world frame may claim the world anchor, and a world frame may
not have a parent); every v2 axis carries a typed `axis(frame, name, sign)`
binding projected as the engine's `AxisDirection`, with `AxisSense` demoted to
descriptive vocabulary — an incomplete binding is refused
(`axis_binding_missing`), never inferred from spelling; and parity tests pin
the projection to the fully-authored B15 horizontal-support, B16 slope, world
Cartesian and tangential-normal fixtures — equal canonical semantics, with
only generated identifier spelling free to differ.

### 0.2 The compiler hypothesis was measured false — no C4 package

§7 below predicted "a compiler that reads a stated reference frame as
authority to proceed" as the missing piece, from the observation that stated
frames moved three solved contexts to `compiler_unsupported ::
requires_specialized_model`.  Measured against the *corrected* projection,
the compiler needs no change: a correctly projected static world/support frame
pair flows through it without ever raising `requires_specialized_model`
(pinned by `test_phase56_stage7_corpus_v2_static_frame_admission.py`).  The
three regressions were the malformed projection, not a compiler gate.  The
frame-needing horizontal-contact cohort's exact blocker is `compiler_failure
:: underdetermined` — its free-body system lacks normal and friction force
records, which no v2 carrier may state without inventing physics — so what
that family needs is a complete-profile engine package of its own, not a frame
admission change.

### 0.3 Source-quote evidence, and the first closed cohort

The v1 projection materialises evidence records only for quotes the corpus
attached to facts, events and assumptions, so a carrier whose statement lives
elsewhere in the problem text had nothing honest to cite.  The v2 contract
gains `SourceQuoteEvidenceV2`: an authored verbatim quote of the source's own
problem text, aligned at its exact stated occurrence by the projection (or
refused, `evidence_quote_not_in_source`) and re-verified by the engine's own
draft validation.  This is the opposite of the B15 defect — the evidence is
the source text itself, never a minted record.

With it, the **vertical-circle limiting-contact cohort closed** (`engine
(stage7): close the vertical-circle limiting-contact cohort in v2 shadow`).
The source states every authority the B12 revocation found missing: "moves
along the **inside** of the track" (typed contact side, track-relative, no
invented frame), "the least speed that **just maintains contact**" (a
`contact_maintained` interval constraint plus the new
`EndpointCondition.contact_limit` — the boundary/active statement at the
highest-point instant, distinct from `contact_loss`), and the highest point
itself.  The C1-corrected objective arrives from v1.  The existing
`vertical_circle_top_speed` profile and `vertical_circle_top_minimum_speed`
law close it — no new physics, no relaxation, and every ablation (any
authority removed, an outside track, a tampered quote) stays fail-closed.

### 0.4 The corrected shadow checkpoint, measured

All prior out-of-tree artifacts were regenerated at the exact code head; no
prior hash is reused.  Manifest digest
`0e5a8d1162adff6f5b73cd5edc568ff6e4b3afd481134de0be5fc4668fd18534` (3 entries,
authored from source words only) · candidate archive SHA-256
`06bf23a220d3be67cd96027cd9e79e9553dd2195217a0c21cda515c20bbc355e` · shadow
report file SHA-256
`c314b189af73e40bbeeba9106bf1eccd1a1b43e09fd54369120f1b5e297858d7` · scorecard
digest `9618779ccb60071ce446c00ab71765ee19853e604f294d9919d00fcf634ffd1b`.

| Figure | First candidate (§6) | Corrected checkpoint |
|---|---:|---:|
| Contexts evaluated | 97 | 97 |
| Augmented contexts | 22 | 3 |
| Newly solved | 0 | **3** |
| Shadow wrong | 0 | **0** |
| Regressed | 3 | **0** |
| Cohort yield | 0 | **1** |

The regression guard ran in its fail-closed default — no
`--record-regressions` — and two independent rebuilds produced byte-identical
archives and reports.  An empty augmentation still projects to a byte-equal
Draft, unaugmented contexts moved nowhere, and the official v1 score is
unchanged at 41/81 with wrong 0.

The shadow scorecard's `newly_solved` is deliberately answer-blind: the
migration and shadow pipeline never open the gold block, so the three new
solves are verified engine closures whose scalar equals the boundary equality
`sqrt(g r)` on the synthetic pilot fixture, not gold-compared numbers.
`shadow_wrong` is 0 because nothing solved wrongly, and nothing was scored
against an answer at all.

---

## 1. The two scores are different objects

| | Official v1 | Experimental v2 shadow |
|---|---|---|
| Class | `OFFICIAL_V1` | `EXPERIMENTAL_V2_SHADOW` |
| Archive | frozen public corpus, SHA-256 `cc8d8b27…1a1bef` | candidate archive, SHA-256 `2e8ca69f…991c1ff6` |
| Score | supported **41/81**, wrong **0** | newly solved **0**, wrong **0** |
| Status | the project's score | **not** the project's score |

The separation is structural, not editorial. `ShadowScorecardV1` has no field
named like an official metric — no `supported`, no `observed_public_score`, no
`terminal_mapping` — so a shadow number has no official field to be added to.
Every shadow report carries `score_class` and `is_official_score: false`, and
`assert_scores_are_separated` refuses a payload that mixes the two before either
artifact is written.

## 2. Why a v2 contract exists

The executable semantic-preservation audit (B22) measured, over 97 projected
contexts, that **seven engine carriers have no source field anywhere in the v1
corpus contract**:

| Carrier | Contexts that need it | Source fields that could state it |
|---|---:|---|
| `reference_frame` | 34 | none |
| `angle_reference_datum` | 13 | none |
| `frame_axis_direction` | — | none |
| `motion_sense` | — | none |
| `contact_side` | — | none |
| `query_objective` | — | none |
| `quantity_frame_binding` | — | none |

The engine's own `MechanicsProblemDraftV1` has held frames, axis directions,
contact sides and query objectives all along. The gap is in what a case is
allowed to *say*.

The same audit found projection loss of **1 field category across 3 contexts**
and normalization loss of **0**, so the earlier "the projection drops nothing"
is very nearly true and not exactly true — and the residual is three occurrences
of a fact-to-segment binding, not a carrier.

## 3. What the contract adds

Version `dynatutor-ko-corpus-v2.0-candidate`, additive and separate. The v1
loader, schema and strict scoring are untouched; there is no automatic upgrade,
and a v1 record becomes a v2 record only through an explicit migration driven by
a human-authored manifest.

Carriers: reference frames with per-axis direction, angle datums, motion senses,
contact sides, endpoint conditions, constraint authorities, interaction targets,
query objectives, and signed-scalar encodings.

Three rules, each from a revoked closure:

- **Evidence.** `evidence_refs` is non-empty and must point into the source's own
  evidence. B15 minted a binding and then read it back as evidence.
- **Scope.** Every carrier names a subject and either an interval or an event,
  never both. B16 promoted an instant to a whole interval.
- **No defaults.** No default orientation, contact side, endpoint or motion
  sense. A missing carrier is refused.

## 4. What the validator refuses

Twenty-eight typed, privacy-safe rejection reasons. The load-bearing ones:

| Attack | Reason |
|---|---|
| duplicate frame identifier | `duplicate_frame_id` |
| dangling frame parent | `dangling_frame_parent` |
| angle measured from an axis its frame lacks | `angle_datum_axis_unknown` |
| two datums for one angle | `ambiguous_angle_datum` |
| sense with no frame / no such axis | `motion_sense_frame_unknown` / `_axis_unknown` |
| instant sense also stated interval-wide | `event_scoped_sense_used_interval_wide` |
| contact with no normal frame or axis | `contact_side_frame_unknown` / `_axis_unknown` |
| two sides for one contact | `conflicting_contact_sides` |
| endpoint on no event; two endpoints on one boundary | `endpoint_without_event`, `duplicate_endpoint` |
| constraint naming a participant the source lacks | `constraint_without_participants` |
| system-force query with no interaction | `interaction_target_without_interaction` |
| two objectives for one query | `duplicate_query_objective` |
| contradictory double sign | `contradictory_scalar_encoding` |
| carrier scoped to both an instant and a span | `scope_is_both_interval_and_event` |
| authored identifier shadowing a source one | `generated_id_collides_with_authored_id` |

## 5. Migration invariants, measured

- The original v1 record is carried byte-identical and fingerprinted separately
  from its additions.
- Rollback to v1 is total and deterministic.
- A manifest naming any answer-bearing field — expected answer, terminal,
  failure code, reference expression, tolerance, sign convention, solver output —
  is refused by a structural scan at any depth and under any spelling.
- A record with no manifest entry is **not** upgraded; it stays unresolved.
- **Rebuild determinism verified against the public archive**: two independent
  runs produced byte-identical candidate archives and byte-identical shadow
  reports.

## 6. Shadow evaluation result

Manifest SHA-256 `ffdb6312…c05dc893` · candidate archive SHA-256
`2e8ca69f…991c1ff6` · shadow report digest `2e4f9131…257fe4448`.

| Figure | Value |
|---|---:|
| Contexts evaluated | 97 |
| Augmented contexts | 22 |
| Unresolved augmentations | 78 |
| Carrier categories exercised | **5** |
| — `reference_frame` | 16 |
| — `angle_datum` | 13 |
| — `contact_side` | 6 |
| — `endpoint_condition` | 6 |
| — `constraint_authority` | 6 |
| Newly solved | **0** |
| Shadow wrong | **0** |
| Cohort yield | **0** |
| Regressed | **3** |

**No pilot closed, and one carrier is actively unsafe.** Supplying a stated
reference frame — or the angle datum alone — moves three contexts that currently
reach a verified answer to `compiler_unsupported :: requires_specialized_model`.
The compiler treats the presence of a stated frame as a signal that a
specialized model is required, which is the opposite of what the v2 hypothesis
predicted. The regression guard is fail-closed by default; the measurement run
used `--record-regressions` so the evidence exists rather than the run aborting.

`contact_side` and `endpoint_condition` project cleanly, regress nothing, and
unlock nothing on their own.

## 7. What this means

The v2 contract can *state* the seven missing carriers, and the validator refuses
every way of stating them wrongly. That much is done and tested.

What is **not** done is the engine side. A stated frame currently makes the
compiler refuse rather than proceed, so before any of these carriers can yield a
closure the compiler's frame handling has to be the subject of its own package.
That is a Stage 7 engine question, not a corpus question, and this session did
not open it.

Recorded exactly, and not fabricated: the missing piece is a compiler that reads
a stated reference frame as authority to proceed rather than as evidence that a
specialized model is needed.

## 8. What must not be concluded

- The official v1 public score is **41/81** and did not change.
- No v2 number is an official number.
- `PUBLIC_CORPUS_V2_OFFICIAL` is **not** declared; the frozen v1 corpus SHA
  remains the official one and the candidate SHA is experimental.
- `V1_TARGET_REPLACED` is **not** declared.
- `STAGE_7_ACCEPTED` and `STAGE_8_READY_TO_START` are **not** declared.

## 9. Reproducing

```
# official v1, under the dependency lock
backend/tools/run_phase56_stage7_locked_strict.py \
  --commit <exact head> --corpus-archive <archive.zip> --reports <out-of-tree dir>

# the executable census and the semantic audit
backend/tools/run_phase56_stage7_authority_census.py --corpus-archive … --output …
backend/tools/run_phase56_stage7_semantic_preservation.py --corpus-archive … --output …

# the v2 candidate archive and its shadow evaluation
backend/tools/run_phase56_stage7_v2_shadow.py \
  --corpus-archive … --manifest … --candidate-archive … --shadow-report …
```

All artifacts stay out of the repository. The corpus, the manifest, the candidate
archive and both reports are never committed.
