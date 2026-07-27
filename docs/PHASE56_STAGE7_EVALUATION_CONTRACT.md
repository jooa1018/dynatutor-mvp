# Phase 56 Stage 7 offline evaluation contract

Status: **frozen before public corpus problem text is opened**

Authoritative implementation:

- `backend/evaluation/phase56_stage7/contracts.py`
- contract version: `phase56-stage7-evaluation-contract-v1`
- evaluator version: `phase56-stage7-evaluator-v2`
- report schema: `dynatutor.phase56_stage7.report` version `1.0`

### Evaluator v1 → v2

The **contract** — the frozen target distribution, the metric catalog, the
hard-safety catalog, the failure taxonomy, the corpus SHA — is unchanged. What
changed is how the evaluator *scores* against it. The target was never
reinterpreted and no threshold was relaxed; three of the four changes make the
gate strictly harder to pass.

| | Previous behaviour (v1) | Defect | v2 behaviour |
|---|---|---|---|
| Lane B acceptance | one gate, `strict_lane_b_all_solved`, requiring `terminals["solved"] == executed_cases` | The frozen target is 81 solved plus 19 cases that must reach a safe **non-solved** terminal. A correct Stage 7 could never satisfy this, and a run that wrongly solved a deferred case scored *better*. | Case-level scoring against each case's own expected class, split into `strict_supported_81_solved`, `strict_deferred_12_verified_unsupported`, `strict_unsupported_other_2`, `strict_needs_figure_2`, `strict_needs_confirmation_2`, `strict_insufficient_information_1`, `strict_terminal_mapping_100_percent`, the six metric gates, `strict_wrong_solve_zero`, `strict_unscored_zero`, and `strict_deferred_silent_solve_zero`. |
| Answer tolerance | `max(corpus_tolerance, 1e-6 * max(1, abs(expected)))` | The invented floor **widened** any corpus tolerance tighter than 1e-6 relative — the evaluator scoring its own engine. | The corpus's declared absolute tolerance, converted to SI in the answer's own unit, applied exactly. |
| Unscored solves | counted and reported, but neither the Lane B gate nor hard safety rejected them | An output nobody could score has not been shown correct; treating it as safe shrinks the measured sample below the one being claimed. | `strict_unscored_zero`, and hard safety fails on any unscored solve. |
| Scorer exceptions | propagated out of `build_report`, aborting the process with a traceback | Unstructured abort; no typed verdict, and a partial artifact could be misread. | Typed `SCORER_FAILURE`: sanitized reason only, Lane B FAILs, every distribution gate FAILs. |

Safety impact: strictly positive. Wrong solves, unscored solves, silent solves
of deferred cases, and supported cases downgraded to unsupported are now each
measured separately and each fail the gate. Metric impact: the reported
`answer_accuracy` denominator is the 81 supported cases rather than the count of
whatever happened to be solved, so partial progress reads as partial. Target
impact: none — `Stage7ExpectedTerminalCounts` is byte-identical.

These defects were identified by running the public corpus and reading
privacy-safe aggregate counts: `PUBLIC_EVALUATION_INFORMED_FIX: YES`. No
private-corpus generalization is claimed from that evidence.

The commit that first introduces this contract is the `STAGE7_PREFLIGHT_HEAD`.
Its exact SHA is recorded in the Stage 7 evidence report after the commit is
pushed.  Public corpus problem text and gold fields must remain unopened until
that push is confirmed.

## Purpose

Stage 7 is an offline evaluation of the accepted Generic Mechanics architecture.
It is not a Live model-quality run and it is not permission to tune against
individual public cases.  The evaluation must distinguish five lanes:

1. corpus and evaluator integrity;
2. deterministic gold-structure-to-IR engine evaluation;
3. recorded/fake modeler contract evaluation;
4. product API/runtime evaluation;
5. frontend interaction evaluation.

Actual OpenAI or Anthropic model quality is `NOT_RUN / N/A` in Stage 7.  No
Stage 7 result may be described as a GPT parser/modeler generalization pass.

## Frozen public input contract

The only authorized archive has SHA-256:

`cc8d8b272e305a7de4ea79a880a6c643e7d501e23e326d94ea3a90ac591a1bef`

Expected public splits are exactly:

| split | count |
|---|---:|
| `public_dev.jsonl` | 84 |
| `public_adversarial.jsonl` | 16 |
| total | 100 |

After archive integrity succeeds, the repository may contain only these
public-evaluation fixture files:

- `public_dev.jsonl`
- `public_adversarial.jsonl`
- `schema.json`
- a newly generated count/hash-only `sanitized_manifest.json`
- a short independent provenance `README.md`

The ZIP, `public_all.jsonl`, any private manifest, any full-corpus material,
private held-out text, textbook PDFs, and textbook figures are forbidden from
the repository.  A private-without-text manifest, if present, receives only a
keys-only absence check for raw text/gold/answers/quotes and is then quarantined.
Its IDs, families, or hashes cannot inform implementation, routing, prompts, or
metrics.

## Current Phase 56 scope override

The current course scope supersedes any older future terminal in the corpus.
The exact four deferred families are:

- `spring_mass_vibration`
- `relative_acceleration_translation`
- `coriolis_relative_motion`
- `slot_pin_relative_motion`

For these families, runtime answer authority is absent.  The required terminal
is precise verified unsupported, with no silent legacy fallback and no numeric
answer.  They do not count as accepted.

Evaluator-only aliases are aggregation rules, never runtime routes:

- `particle_on_incline` is represented by typed contact/friction structure;
- `spring_energy` aggregates with `spring_energy_speed` capability.

The scope-adjusted terminal counts are frozen before evaluation:

| expected class | count |
|---|---:|
| supported solved/accepted | 81 |
| deferred precise unsupported | 12 |
| unsupported other | 2 |
| needs figure | 2 |
| needs confirmation | 2 |
| insufficient information | 1 |
| total | 100 |

Any mismatch is a structured harness failure before runtime, compiler, solver,
or provider execution.

## Terminal taxonomy

Runtime emits only the following Stage 7 scoring terminals:

- `solved`
- `verified_unsupported`
- `needs_figure`
- `needs_confirmation`
- `insufficient_information`
- `runtime_failure`

Gold distinguishes deferred unsupported from unsupported-other for scoring, but
both map to the same neutral runtime terminal `verified_unsupported`.  Gold may
never select a solver, equation, root, answer, or verification result.

## Deterministic quality gates

Lane B requires exactly 100 percent for:

- all 81 supported expected terminals and finite answers;
- answer unit/dimension;
- query subject, segment, and event binding;
- direction/sign;
- candidate coverage;
- verification residual;
- all 12 deferred terminals;
- both unsupported-other terminals;
- both needs-figure terminals;
- both needs-confirmation terminals;
- the insufficient-information terminal;
- diagnostic-only metamorphic invariance;
- physics-changing negative-control detection;
- synthetic-figure source-region validity.

These thresholds, tolerance meaning, scope mapping, leakage definition, candidate
verification rule, and confident-wrong definition cannot be lowered after public
cases are seen.  A genuine evaluator defect requires a new contract version and
a written migration describing old behavior, new behavior, affected metrics,
and safety effect.

## Metrics

Metrics are semantic-role based and ID/order independent:

- entity, segment, event, fact, and relation precision/recall;
- query and unit accuracy;
- entity, segment, event, temporal, and direction binding;
- assumption precision;
- route/terminal and deterministic-answer accuracy;
- candidate coverage and residual verification;
- safe abstention, figure dependency, conflict, and correction replay.

Repeated equal facts retain multiset cardinality.  A graph mismatch is not an
invented fact.  Invention means a source-absent explicit value/fact entered a
runtime-authoritative structure.

## Hard-safety gate

Every signal defined by `Stage7HardSafetySignal` must be zero, including:
confident wrong solve, invented explicit number, answer/model/root authority,
expected-answer or gold leakage, case/family routing, unsafe legacy fallback,
deferred silent solve, conflict/correction/revision bypass, direct graph/answer
patch, raw image/provider logging, prompt-injection authority, unbounded repair,
early discarded roots, and private held-out access.

One nonzero hard-safety signal fails Stage 7.

## Failure taxonomy

All failures use the closed `Stage7FailureKind` enum.  Results are triaged as
harness, corpus integrity, gold isolation, evaluator adapter, corpus reference,
modeling/evidence/normalization/authorization/compiler/law/solver/root/
verification/projection, API, frontend, expected-terminal mismatch, or security
authority failure.

A public-evaluation-informed repair is allowed only for a general IR, law,
compiler, solver, verifier, evidence, API, frontend, or evaluator defect.  It
must add the original reproduction, an independent same-structure regression,
a physics-changing negative control, an authority negative, and related-family
plus Stage 5/6 regression.  Case-ID branches, family routes, exact sentence
matches, expected-answer use, tolerance expansion, test deletion, and legacy
answer correction are prohibited.
