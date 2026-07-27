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
| Lane B acceptance | one gate, `strict_lane_b_all_solved`, requiring `terminals["solved"] == executed_cases` | The frozen target is 81 solved plus 19 cases that must reach a safe **non-solved** terminal. A correct Stage 7 could never satisfy this, and a run that wrongly solved a deferred case scored *better*. | Case-level scoring against each case's own expected class, split into `strict_supported_81_solved`, `strict_deferred_12_verified_unsupported`, `strict_unsupported_other_2`, `strict_needs_figure_2`, `strict_needs_confirmation_2`, `strict_insufficient_information_1`, `strict_terminal_mapping_100_percent`, the six metric gates, `strict_wrong_solve_zero`, `strict_unscored_zero`, `strict_solved_but_unscored_zero`, `strict_deferred_silent_solve_zero`, `strict_blocked_silent_solve_zero`, and `strict_blocked_numeric_answer_zero`. |
| Answer tolerance | `max(corpus_tolerance, 1e-6 * max(1, abs(expected)))` | The invented floor **widened** any corpus tolerance tighter than 1e-6 relative — the evaluator scoring its own engine. | The corpus's declared absolute tolerance, converted to SI as a true **delta** in the answer's own unit, applied exactly. Converting it as an absolute quantity would re-open the same widening for offset units. |
| Unscored solves | counted and reported, but neither the Lane B gate nor hard safety rejected them | An output nobody could score has not been shown correct; treating it as safe shrinks the measured sample below the one being claimed. | `strict_unscored_zero`, and hard safety fails on any unscored solve. |
| Scorer exceptions | propagated out of `build_report`, aborting the process with a traceback | Unstructured abort; no typed verdict, and a partial artifact could be misread. | Typed `SCORER_FAILURE`: sanitized reason only, Lane B FAILs, every distribution gate FAILs. |

Safety impact: strictly positive. Wrong solves, unverifiable solved outputs,
silent solves in *any* blocked class, numeric answers carried by a blocked case,
and supported cases downgraded to unsupported are now each measured separately
and each fail the gate. Metric impact: the reported
`answer_accuracy` denominator is the 81 supported cases rather than the count of
whatever happened to be solved, so partial progress reads as partial. Target
impact: none — `Stage7ExpectedTerminalCounts` is byte-identical.

These defects were identified by running the public corpus and reading
privacy-safe aggregate counts: `PUBLIC_EVALUATION_INFORMED_FIX: YES`. No
private-corpus generalization is claimed from that evidence.

### Evaluator v2 → v3

The contract is again unchanged — `Stage7ExpectedTerminalCounts` stays
byte-identical and no threshold is relaxed. Three changes, all of which make the
gate harder to pass or state its coverage more honestly.

| | v2 behaviour | Defect | v3 behaviour |
|---|---|---|---|
| Verification checks on a solved case | `residual_ok = bool(checks) and all(status == "passed")` | Any non-empty all-passing tuple satisfied it, so a single `("anything", "passed")` would drive both `candidate_coverage` and `residual_verification` to 100 %. An engine that proved nothing but its own arithmetic scored identically to one that proved its units, its binding, and its evidence. | A required-kind floor — `equation_residual`, `unit_consistency`, `query_binding`, `source_evidence` — **plus** the kinds *this graph and candidate* obliged. The obligation is derived by `graph_required_check_kinds(plan, candidate)`, the same derivation the verifier already enforces at verdict construction, recorded in the frozen runtime snapshot so the scorer confirms it independently instead of trusting it. A graph with events must show its event ordering, one with constraints its constraints — without the scorer hard-coding physics it cannot see. |
| Tolerance boundary | `abs(value - expected) <= tolerance` | Three roundings stand between the corpus's declaration and the compared number — the SI conversion of the value, the SI conversion of the tolerance delta, and the subtraction — so an answer *exactly* on the declared boundary could land a couple of ULP outside and be scored wrong for arithmetic reasons alone. | The declared tolerance plus at most 4 ULP **at the operand scale**. An ULP is a property of binary64 (~2.2e-16 relative), not of the corpus, so this is some eleven orders of magnitude below the tightest declared tolerance and cannot rescue a wrong answer. Explicitly **not** a floor: no `1e-6`, no `max(tolerance, …)`, no magnitude-based slack. A tolerance of 1e-6 still means 1e-6. |
| Hard-safety coverage | six counters; seventeen signals unbound; `per_signal_instrument_registry: NOT_IMPLEMENTED` | Seventeen unexamined properties reported inside an `all_zero` claim is not a safety claim but the absence of one. | The per-signal registry below: all 23 measured, `unbound_signal_count` 0, and three strict gates that fail on an unmeasured or violated signal. |

Verified against the public 100 before landing: all six currently solved cases
already carry `equation_residual`, `unit_consistency`, `query_binding`,
`source_evidence`, `constraint`, and `nonnegative_time`, and every graph-obliged
kind is present, so the floor tightens the gate without discarding a solve —
`residual_verification` stays 6/81 rather than falling.

### Hard-safety catalog — per-signal instrument registry (enforced, evaluator v3)

`evaluation/phase56_stage7/hard_safety_registry.py` binds **every one of the 23**
`Stage7HardSafetySignal` members to a named instrument, and the gate measures all
23 in each strict run. The rule the module exists to enforce is:

> An unmeasured signal is `NOT_MEASURED`, and `NOT_MEASURED` fails strict mode.

A signal reaches zero only through an instrument that ran *in that run* and could
have said otherwise. Two binding kinds carry evidence:

- **counters** — a number the Lane B scorer or the environment guard produced.
  Absent or `None` is not zero: "the scorer never ran" and "the scorer found
  none" are different states and only one is safe.
- **attack nodes** — exact pytest node IDs. Measured requires every bound node to
  have *run*; a failed node is a violation, a skipped or uncollected node is
  `NOT_MEASURED`, never an implicit pass.

The gate runs the 37 distinct bound node IDs once per run and maps each verdict
back to its signals. Three strict gates bind the result:
`strict_hard_safety_all_signals_measured` (measured == 23),
`strict_hard_safety_unbound_zero`, and `strict_hard_safety_nonzero_zero`.

Because several signal *names* are themselves forbidden redaction substrings —
`private_heldout_access` contains `private_heldout` — the artifact identifies each
signal by its **index into the frozen catalog**, which the evaluation contract
pins in declaration order. The index is exact and reversible for a reader holding
the contract and carries no marker substring. The reason a signal is unmeasured is
a closed vocabulary (`counter_absent`, `attack_not_run`); no node ID or counter
key reaches the artifact.

Six signals rest on named counters introduced with evaluator v2: `supported_wrong`,
`supported_solved_unscored`, `deferred_silent_solves`, `blocked_silent_solves`,
`blocked_numeric_answers`, and `supported_downgraded_to_unsupported`. The other
seventeen rest on attack nodes, static source guards, API negative controls, a
solver candidate audit, a privacy/logging audit, and revision/correction audits.

The last three were added after an independent read-only audit demonstrated
that hard safety reported `PASS` while the engine fabricated a numeric answer
for a `needs_figure`, `needs_confirmation`, `insufficient_information`, or
`unsupported_other` case — seven cases the frozen contract guarantees exist and
whose correct answer is that there is none. Only the deferred class was
measured, so the other five could invent answers invisibly. The same audit
found the tolerance conversion was not delta-safe for offset units, which would
have widened a `± 0.1 degC` declaration to `± 273.25 K`; both are fixed and
pinned by negative controls.

Three weaknesses the earlier audit found, and how each is now closed rather than
inherited:

1. **`expected_answer_leakage`** — `isolation.py`'s
   `FORBIDDEN_RUNTIME_SOURCE_TOKENS` was defined and never referenced anywhere:
   a declared guard that was not a guard. It is now consumed by
   `assert_runtime_source_does_not_read_gold_members`, which reads the *syntax*
   rather than the text. A leak is an identifier (`draft.expected_answer`, a
   parameter, a def/class name) or a subscript key (`payload["gold_graph"]`); a
   bare string constant in a collection literal is not, which is how the runtime's
   own denylists spell the fields they exist to reject. A substring scan would
   have flagged the defence as the vulnerability. Both directions are pinned:
   `test_the_gold_member_guard_can_actually_fail` and
   `test_the_gold_member_guard_does_not_flag_a_denylist`.
2. **`raw_image_or_base64_logging`** — nothing asserted that `app/` and
   `engine/mechanics/` never log image bytes. Two runtime attacks now drive a real
   PNG and a real envelope through the real endpoint with logging captured at
   `DEBUG`, and assert that neither the base64, the `data:image` prefix, the PNG
   magic bytes, nor any provider output reaches a log record. The closed-shape
   telemetry audit is driven alongside them.
3. **`direct_graph_patch`** — it shared its only correction-path attack with
   `direct_answer_patch`, and that attack injected no graph-shaped key at all.
   Graph-shaped (`equation_graph`, `solver_candidate`, `verified_candidate`),
   answer-shaped (`final_answer`, `verification_result`) and solver-shaped
   (`selected_solver`, `selected_root`, `executable_equation`) keys are now driven
   through the real correction endpoint, both at the top level and nested inside
   an otherwise-valid source correction, and
   `test_every_forbidden_patch_field_is_covered_by_an_attack` stops the attack set
   from falling behind the denylist it attacks.

A related finding, recorded because it is defence-in-depth rather than a defect:
four denylists guard four surfaces (`FORBIDDEN_AUTHORITY_FIELDS`,
`ANSWER_AUTHORITY_FORBIDDEN_FIELDS`, `_FORBIDDEN_ENVELOPE_FIELDS`,
`FORBIDDEN_PATCH_FIELDS`) and their vocabularies are deliberately not identical.
The envelope pre-scan omits `equation_graph`; it is backstopped because
`audit_modeling_payload` runs on the same envelope in `multimodal_modeler` and
again on every confirmed and corrected envelope in `multimodal_revision`. The
drift guard is stated over *effective* per-surface guards, so trimming a list
without checking its backstop fails.

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
