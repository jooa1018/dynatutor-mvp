# Phase 53 ExplanationTrace v1

Phase 53 adds deterministic, machine-verifiable explanation provenance without changing the established answer, candidate-selection, verification, or result-gate contracts. The accepted Phase 52 base is `ef15012209955ab0e0f89d0143b2d61cf6fab496`.

## Public contract

`SolverResult.explanation_evidence` is optional immutable solver evidence. `SolveResponse.explanation_trace` is the single optional API addition. Both default to `None`, so existing constructors and clients remain compatible.

ExplanationTrace v1 contains:

- schema, version, grounding status, selected solver, and route reason;
- the resolved calculation coordinate frame with source and status;
- separate explicit semantic facts and assumptions;
- typed equations with source/provenance and fact/output links;
- typed substitutions with equation/fact/output links;
- selected-candidate and validation summaries;
- one exact derivation link per delivered answer item;
- preserved warnings and deterministic student steps.

Machine IDs are retained where auditability needs them. They are not rendered in `steps`, `teacher_summary`, `concept_summary`, `common_mistakes`, or `equation_sheet`.

## One-pass ordering

The solve pipeline remains parse → model/route → solve/select → verify → answer consistency → result gate. `apply_result_gate` remains the only answer-removal/demotion operation and is called once on the solved path. ExplanationTrace is finalized afterward from the delivered response, then all physics-bearing student projections are replaced from that trace.

The builder never parses, routes, solves, selects, verifies, calls an LLM, or changes an answer. A builder exception leaves the product answer intact and attaches a neutral withheld trace.

## Grounding policy

`fully_grounded` requires structured solver evidence, a resolved non-default calculation frame, provenance for every equation, linked substitutions, a selected candidate, and exact signed numeric/unit/output-key agreement for every delivered item. Symbol and role must also agree when supplied. Missing, duplicate, unlinked, ambiguous, or mismatched evidence produces partial/withheld output with no definitive derivation.

Canonical facts include normalized known quantities and allowlisted semantic facts only. Raw problem text, quantity source text, and student text are never copied into the trace. Assumptions remain separate. A solver branch condition must be explicitly classified and linked.

The builder enforces code-owned fact namespaces, source/provenance enums, bounded branch/assumption keys and values, normalized known-quantity keys, and typed scalar values. Every string fact value is checked against its enum/namespace contract and forbidden raw/source/student/problem categories. Free-form canonical assumptions are omitted with a grounding warning and cannot produce a fully grounded trace.

The subtype contract is system-specific and mirrors the checked-in Phase 52 capability registry: `particle_on_incline` accepts `no_friction`/`with_friction`; `projectile_motion` accepts `general`/`same_level`; `pure_rolling_energy` and `rolling_energy_general` accept `rolling_on_incline`; and `vertical_circle` accepts `top`/`bottom`. No other normalized subtype token is evidence. Flags alone accept booleans. Known quantities alone accept arbitrary finite numeric values and must still match the canonical quantity exactly. Branches and assumptions accept only the enum values declared for their named key; booleans and numbers cannot bypass those enums. The only semantic numeric keys are launch/landing height (metres, bounded to ±1e9 for representation safety) and launch angle (degrees, bounded to ±360). These are representation/privacy bounds, not solver tolerances.

Fact and delivered-output units use one central code-owned vocabulary derived from `engine.physics_core.units._UNIT_ALIASES`, plus the existing spring-vibration `Hz` output and explicit `1`/`dimensionless` tokens. It includes the repository's metre/second, acceleration, mass, force, energy, stiffness, inertia, impulse, angle, angular-rate, and common alias spellings. `None` and the empty string remain the canonical policy for ununitized knowns; flags, branches, enum assumptions, and nonnumeric semantic facts require `None`. Semantic height and angle facts require `m` and `deg` respectively. A syntactically plausible technical token, control-containing string, or oversized unit is not evidence and prevents full grounding.

Calculation coordinates use explicit source, coordinate-system, axis, positive-direction, and unit token sets. These sets include normal physics notation such as `+x`, `-y`, `x/y`, and `rad/s`, while rejecting free sentences, control/source text, oversized values, and default or generic frames.

Each delivered output owns a unique output ID and exactly one output link. Its direct substitutions must all produce that output, use exactly the linked equations, and every linked equation must declare the same output. Cross-wired or reused identities withhold all derivations.

Legacy `used_equations` and `StepCard.math` may appear only as partial machine equations. They cannot create substitutions or a fully grounded trace.

Ambiguous, unsupported, contradictory, partial, and withheld traces render neutral status/required-input guidance. Rejected candidate values are never projected as answers.

Before projection, Wave 1 clears legacy FBDs, hints, coordinate/equation guides, cautions, questions, and both physical-model payloads. A fully grounded response rebuilds only the coordinate and applicable-equation views represented by the trace; every other state leaves those views empty.

## Wave 2 boundary

Wave 1 defines and integrates the contract. Existing solver files are unchanged, so legacy solver results are expected to produce partial traces. Wave 2 must populate `SolverExplanationEvidence` for each migrated solver path, including exact output/candidate links and the calculation coordinate frame; it must not loosen the Wave 1 grounding checks.
