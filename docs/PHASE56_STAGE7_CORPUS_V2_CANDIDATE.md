# Phase 56 Stage 7 — public corpus v2 candidate contract

Disposition: **`V2_CANDIDATE_INCOMPLETE`**

This document records a *candidate* contract and an *experimental* measurement.
The frozen v1 public corpus is unchanged, the v1 acceptance target is unchanged,
`STAGE_7_IN_PROGRESS / NOT_ACCEPTED` stands, and Stage 8 has not been started.

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
