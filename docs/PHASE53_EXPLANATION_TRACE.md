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

A successful solver enters this strict projection only when it supplies non-`None` `SolverExplanationEvidence`. A successful unmigrated solver keeps the pre-Phase53 steps, FBD/annotations, coordinate and equation guides, cautions, questions, physical-model payloads, summaries, tips, and equation sheet; its `explanation_trace` remains `None`. This absence is an explicit migration marker, not a claim that legacy prose is trace-grounded. Failed, ambiguous, unsupported, contradictory, and result-gate-demoted responses never use the compatibility path.

## Grounding policy

`fully_grounded` requires structured solver evidence, a resolved non-default calculation frame, provenance for every equation, linked substitutions, a selected candidate, and exact signed numeric/unit/output-key agreement for every delivered item. Symbol and role must also agree when supplied. Missing, duplicate, unlinked, ambiguous, or mismatched evidence produces partial/withheld output with no definitive derivation.

### Raw selection and delivery authority

The solver's selected candidate remains the authority for physics, branch choice, and Phase 52 observability. It also remains the public selection metadata when both raw and delivery decisions select. The service separately creates one stable, code-owned `delivery:<solver>:solve-response` candidate from the actual `SolverResult` answer items and validates only that fresh candidate once. This validation cannot mutate the raw candidate batch. If delivery validation rejects a raw-selected result, the established product policy still publishes the delivery failure decision and diagnostics and demotes through the existing result gate; the raw decision is retained only for strict internal trace checking. Direct/legacy solvers without a raw selection use the delivery candidate as their public identity candidate; their only permitted transform is exact identity.

Each internal `OutputEvidenceLink` names both authorities: the exact raw candidate ID/key/signed numeric and the exact delivery candidate ID/key/signed numeric. Candidate-ID spelling or equality is never used to infer their relationship; direct identity is allowed only when the service supplied the same authority decision object. Its transform is either `identity` with no decimal count or Python's built-in `round(raw, n)`. A central policy-ID table binds solver, raw key, output meaning, transform, and the one permitted `n`; arbitrary transforms and arbitrary `ndigits` are rejected. Round policies exist only for service paths that actually expose a separate raw selection: constant-acceleration outputs at 6 decimals, general-projectile selected `t`/`R`/`delta_x` outputs at 6, incline-no-friction acceleration at 5, and the moving incline-with-friction acceleration at 5. Static incline, no-initial-speed projectile, rolling, vertical-circle, collision, work-energy, and horizontal-friction paths are direct/legacy identity authorities and cannot claim a policy ID.

Candidate-key meaning is also code-owned (`t→time`, `a→acceleration`, `v→final_velocity`, `f_s→friction_force`, and so on), so equal numbers cannot cross-wire different quantities. The delivery candidate mapping must contain exactly the answer symbols/output keys and no extras. Repeated output keys, such as actual and maximum static friction, must use nonempty, globally unique symbol keys within that group. Signed zero, non-finite values, booleans, missing/rejected decisions, duplicate links, and any raw/delivery ID, key, value, unit, equation, or substitution mismatch prevent `fully_grounded`.

When both legacy `answer` and typed `answers` are present, `answers` remains the public multi-output delivery list and produces no duplicate derivation. The top-level answer must match the first primary delivered item with signed-exact finite numeric and exact unit. A non-`None` top-level output key must have code-owned semantic compatibility with the primary output key. A legacy `None` key is accepted only when the first primary item supplies one registered key that is unique among primary items; display and label text are never used to infer it.

Canonical facts include normalized known quantities and allowlisted semantic facts only. Raw problem text, quantity source text, and student text are never copied into the trace. Assumptions remain separate. A solver branch condition must be explicitly classified and linked.

The builder enforces code-owned fact namespaces, source/provenance enums, bounded branch/assumption keys and values, normalized known-quantity keys, and typed scalar values. Every string fact value is checked against its enum/namespace contract and forbidden raw/source/student/problem categories. Free-form canonical assumptions are omitted with a grounding warning and cannot produce a fully grounded trace.

The subtype contract is system-specific and mirrors the checked-in Phase 52 capability registry: `particle_on_incline` accepts `no_friction`/`with_friction`; `projectile_motion` accepts `general`/`same_level`; `pure_rolling_energy` and `rolling_energy_general` accept `rolling_on_incline`; and `vertical_circle` accepts `top`/`bottom`. No other normalized subtype token is evidence. Flags alone accept booleans. Known quantities alone accept arbitrary finite numeric values and must still match the canonical quantity exactly. Branches and assumptions accept only the enum values declared for their named key; booleans and numbers cannot bypass those enums. The only semantic numeric keys are launch/landing height (metres, bounded to ±1e9 for representation safety) and launch angle (degrees, bounded to ±360). These are representation/privacy bounds, not solver tolerances.

Fact and delivered-output units use one central code-owned vocabulary derived from `engine.physics_core.units._UNIT_ALIASES`, plus the existing spring-vibration `Hz` output and explicit `1`/`dimensionless` tokens. It includes the repository's metre/second, acceleration, mass, force, energy, stiffness, inertia, impulse, angle, angular-rate, and common alias spellings. `None` and the empty string remain the canonical policy for ununitized knowns; flags, branches, enum assumptions, and nonnumeric semantic facts require `None`. Semantic height and angle facts require `m` and `deg` respectively. A syntactically plausible technical token, control-containing string, or oversized unit is not evidence and prevents full grounding.

Calculation coordinates use explicit source, coordinate-system, axis, positive-direction, and unit token sets. These sets include normal physics notation such as `+x`, `-y`, `x/y`, and `rad/s`, while rejecting free sentences, control/source text, oversized values, and default or generic frames.

Each delivered output owns a unique output ID and exactly one output link. Its direct substitutions must all produce that output, use exactly the linked equations, and every linked equation must declare the same output. Cross-wired or reused identities withhold all derivations.

Legacy `used_equations` and `StepCard.math` cannot create substitutions or a fully grounded trace. On a successful unmigrated solver they remain in the unchanged legacy product projection and no trace is attached. If structured evidence is present but malformed, these legacy fields cannot rescue or augment it.

Ambiguous, unsupported, contradictory, partial, and withheld traces render neutral status/required-input guidance. Rejected candidate values are never projected as answers.

On the strict path, projection clears legacy FBDs, hints, coordinate/equation guides, cautions, questions, and both physical-model payloads. A fully grounded response rebuilds only the coordinate and applicable-equation views represented by the trace; malformed/partial/withheld structured evidence and all terminal states leave those views empty. The successful unmigrated compatibility path does not call this scrubber.

## Wave 2 boundary

Wave 1 defines and integrates the contract. Existing solver files are unchanged, so successful legacy solver results preserve their established response and leave `explanation_trace=None`. Wave 2 must populate `SolverExplanationEvidence` for each migrated solver path, including exact output/candidate links and the calculation coordinate frame; it must not loosen the Wave 1 grounding checks. Once a solver supplies evidence, malformed or incomplete evidence stays on the strict neutral/scrubbed path instead of silently falling back to legacy prose.
