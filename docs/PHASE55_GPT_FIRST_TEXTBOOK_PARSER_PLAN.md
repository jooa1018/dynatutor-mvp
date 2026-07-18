# Phase 55 — GPT-first textbook problem parser plan

Status: independent Planning Checker PASS; implementation authorized  
Author / Maker ID: `codex-root-019f7308`  
Planning Checker ID: `phase55-planning-checker-019f7308` (first review: FAIL; revised-plan re-review: PASS; valid findings: 0)  
Authoritative base: `main@00b3a60de6e13756d089655879a02e4094122047`  
Work branch: `codex/phase55-gpt-first-textbook-parser`  

## Goal and authority boundary

Every general text problem enters a GPT-5.4 mini Structured Outputs parser before any automatic textbook-parser solve. GPT may identify entities, motion segments, events, explicit facts, relations, queries, ambiguities, figure dependency, and assumption proposals. It may not contain or determine an answer, calculated value, equation solution, solver result, candidate selection, verification decision, or grade.

Only server validators may accept source evidence, normalize units, score interpretations, apply the assumption policy, approve a solver capability, and project a parse to the compatibility `CanonicalProblem`. Existing deterministic solvers, candidate selection, verification/result gate, ExplanationTrace, and VisualizationScene remain authoritative.

## Stage A audit

### Current call path

`POST /solve` → `engine.services.solve_problem` → `_solve_problem_impl` → rule-based `extract_problem` → `CanonicalProblem`/`CanonicalProblemV2` → physical model → `SolverRegistry.route/select` → deterministic solver → candidate validation → verification suite/result gate → ExplanationTrace → VisualizationScene.

The primary integration seam is `_solve_problem_impl`'s parse stage, but it is not the only text entry point. A shared `parse_textbook_problem_gateway` will own parser-mode selection, validation, and projection for `/solve`, `/diagnose`, `/feedback`, and explanation paths that invoke solve. All general-text entry points must reuse the same validated graph or explicit rule-only rollback mode. The parser orchestration result must be terminal or projected before model building and routing; parser errors must be classified and must never surface as an HTTP 500.

### Current OpenAI client

`backend/engine/llm/client.py` is an explanation-only `urllib` Responses client that returns free-form text. Phase 55 will not reuse it. The parser gets a separate official `openai` Python SDK client and configuration. Official documentation confirms `client.responses.parse(..., text_format=PydanticModel)`, `response.output_parsed`, explicit refusal content, `store`, `reasoning`, `tools`, and per-request timeout support. The requested snapshot `gpt-5.4-mini-2026-03-17` supports Responses and Structured Outputs.

### Raw-text dependency findings

The rule extractor and canonical adapter legitimately inspect raw text for evidence. After canonicalization, important physics decisions still inspect raw text in:

- `engine/solvers/kinematics.py`: starts/ends at rest, event-root choice, requested-output fallback.
- `engine/equation_generators/energy_momentum.py`: rest, force/displacement angle, force-motion relation.
- `engine/solvers/projectile.py`: launch direction and requested output.
- `engine/solvers/newton/single_particle.py`: force mentions and net-force classification.
- `engine/solvers/energy_vibration.py`, `advanced_motion.py`, `advanced_dynamics.py`, pulley and rigid-body solvers.
- verification residuals, registry evidence, rolling visualization, and feedback helpers.

Phase 55 will migrate the constant-acceleration branch exercised by the golden fixture to typed canonical inputs. The required invariant is identical canonical data plus different raw text producing the same constant-acceleration result. A versioned capability flag, `textbook_parser_safe`, blocks `auto` and `required` projection for every family that has not passed an equivalent raw-text invariance audit. Such parses end as `solver_gap` (or remain diagnostic in shadow mode); GPT structure is never handed to a solver that can silently reinterpret its bindings from raw text. Other production dependencies remain recorded as follow-up debt and cannot become auto-authoritative until migrated and tested.

### Benchmark baseline

The repository currently contains 975 countable JSON benchmark cases across generated, derived, negative, Korean NLP, blind-textbook, and oracle corpora, plus a non-flat metamorphic corpus. These are regression evidence, not a Phase 55 gold parse corpus. The athlete report is absent and the current rules do not bind its `35 m` and `5.4 s` to a target motion segment or infer the visible start-rest assumption, so it routes as unknown/no solver as reported in the goal.

## Architecture

```text
problem text
  -> parser mode policy (off/shadow/confirm/auto/required)
  -> OpenAI Responses parse or recorded structured fixture
  -> strict TextbookProblemParseV1
  -> evidence/numeric/unit/reference/graph/contradiction/safety validators
  -> server assumption policy and capability gate
  -> parse decision
  -> CanonicalProjection (accepted states only)
  -> existing physical model / registry / solver / verification / trace / scene
```

The rule parser remains available for evidence cross-checking, shadow comparison, explicit limited fallback, and `off` rollback. It never short-circuits GPT in enabled general-text modes.

## Contracts

`TextbookProblemParseV1` uses Pydantic v2 with `extra="forbid"`, bounded arrays, explicit enums, and fixed schema/version literals. The schema intentionally has no answer, calculation, equation solution, solver-result, verification, candidate-selection, or grading field.

It contains:

- entities with evidence and stable IDs;
- ordered motion segments bound to actors and optional start/end events;
- events bound to subjects and segments;
- explicit facts preserving raw value and raw unit, with quote and occurrence index;
- explicit relations with source evidence;
- queries bound to subject/segment/event and synchronized output keys;
- assumption proposals evaluated only by the server policy;
- up to three interpretation candidates;
- ambiguities, figure dependency, and unsupported features.

Validated wrappers keep source spans, validation issues, accepted/rejected assumptions, a server-recomputed interpretation score, usage, model/prompt/schema versions, and the terminal decision. The public response exposes only a safe additive summary.

All strings and arrays are bounded, not only top-level collections. Entity labels/IDs/aliases, evidence quotes, reasons, ambiguity text, and unsupported-feature text have explicit maximum lengths. The existing 10,000-character request cap remains the absolute input limit; the parser applies a smaller documented token/output budget and returns a safe terminal status when exceeded.

## Validation invariants

1. Every referenced entity, segment, event, fact, query, relation, and assumption ID exists and is unique.
2. Segment order is unique; actor/event links are valid; target segments are query-linked.
3. Event subject and segment links are valid, and declared start/before/after order is physically coherent.
4. Every explicit numerical fact has an exact source quote. The server derives spans using quote plus occurrence index.
5. The raw numeric token and unit must occur in the quote and must match the fact. Any invented explicit numeric fact is rejected before projection.
6. GPT raw values are never treated as converted SI values; deterministic unit normalization happens during projection.
7. Dangerous or unsupported assumptions are rejected or require confirmation. GPT confidence is diagnostic only.
8. Figure-required problems never project missing geometry or connectivity.
9. Prompt-injection text in the problem is data. No tools, web search, code interpreter, or function calls are enabled.
10. Parser output cannot overwrite deterministic answer, verification, selection, explanation, or visualization authority.

## Interpretation decision policy

Candidate selection uses a versioned deterministic policy with required vetoes before scoring. Invalid evidence, invented numeric facts, broken bindings, figure-required state, dangerous assumptions, unsupported output keys, and missing capability inputs are hard vetoes. Remaining candidates receive documented weights for evidence coverage, binding completeness, query match, safe assumptions, capability completeness, and rule-extractor agreement. GPT confidence is retained only as non-authoritative diagnostics and never breaks a tie. Multiple solver families, critical conflicts, or a score gap below the versioned tie margin produce `needs_confirmation`. Every decision records policy version, factor scores, veto/error codes, and a server reason code.

## Parser orchestration and failure policy

The official SDK client is configured with the parser snapshot, `reasoning={"effort": "low"}`, `store=False`, `tools=[]`, an application retry budget of at most one repair, SDK retries disabled, a 20-second default timeout, and an explicit `max_output_tokens` budget sized below the 1,500-token complex-case diagnostic target. Parser calls have a separate bounded concurrency semaphore, rate budget, and estimated-request cost guard. Budget or concurrency exhaustion maps to a safe terminal status without rule fallback in `required` mode.

The runtime and lock files pin the verified SDK exactly as `openai==2.45.0`. Dependency-consistency tests assert the pin and a fake-client contract asserts the supported `responses.parse`, `text_format`, `reasoning`, `store`, `tools`, timeout, refusal, and usage surfaces without a network call.

Repair is allowed only for schema errors, invalid references, evidence mismatch, or required structural omission. It receives the original problem and validator error codes, uses the same schema, and runs once at most.

Modes:

- `off`: rule-only rollback; no GPT call.
- `shadow`: GPT parses every general text problem but rule behavior remains user-authoritative.
- `confirm`: validated structure is shown before solve.
- `auto`: accepted parses solve; risky parses stop for templated confirmation.
- `required`: parser failure stops safely; rule fallback only through an explicit limited-mode choice.

Code defaults to `off` to preserve offline CI and existing response behavior. Deployment handoff recommends `confirm`; this PR changes no production variables.

## Prompt artifact

`backend/engine/textbook_parser/prompts/textbook_parser_v1.txt` is versioned as `textbook-parser-v1`; its content hash participates in cache identity and tests. A stable prefix contains the parser-only authority boundary, enums, injection isolation, and five no-calculation few-shots: single constant acceleration, the multi-segment athlete, two-body collision, friction-direction confirmation, and a figure-required rigid-body problem. The untrusted problem text is delimited and appended last for prompt caching. Snapshot tests forbid answer/calculation instructions and verify that every explicit fact requires an exact quote.

## Canonical projection and golden fixture

Projection selects only validated solver-input/constraint facts from the chosen interpretation, applies accepted assumptions, normalizes units deterministically, fills compatibility knowns/flags/coordinate metadata/requested outputs, records provenance, and preserves the whole validated parse graph on the internal canonical object.

For the athlete golden fixture, projection must create `s=35 m`, `t=5.4 s`, the visible accepted `v0=0 m/s` assumption, `constant_acceleration_1d`, and query `acceleration` for segment 1. Segment 2 remains context only. The unchanged deterministic solver must compute approximately `2.40055 m/s²`, displayed as `2.40 m/s²` by product formatting.

## Cache, telemetry, and privacy

The cache key is SHA256 of normalized problem text plus model snapshot, prompt, schema, ontology, normalizer, validator, assumption, capability, projection, and decision-policy versions. L1 is bounded process LRU; L2 is SQLite with corruption fail-open deletion of only the invalid entry. Every hit is revalidated against the current schema/version envelope before use. Render SQLite ephemerality is documented.

Stored cache data is the minimum validated graph/evidence needed for safe reuse, validation summary, versions, usage, and creation time. The cache has an explicit TTL, row/byte cap, LRU eviction, namespace separation, and restrictive best-effort file permissions. API keys, raw model responses, secrets, and unnecessary raw student/problem text are forbidden. Production telemetry stores a normalized text hash, mode/model/versions, outcomes, latency stages, retries, token buckets, estimated cost, cache state, and failure code. Pricing is versioned configuration, not correctness logic.

## Benchmark and test plan

Add a safe paraphrased seed corpus of at least 160 cases with a gold schema, private-corpus manifest/import contract, evaluator, metric calculator, metamorphic transforms, and adversarial cases. It is explicitly not a real-textbook held-out corpus. Metrics include entity/fact/unit/binding/event/query/assumption/route accuracy, solve success, safe abstention, confident wrong solve, and invented explicit numerical fact rate.

The evaluator always reports the source-of-truth release targets: numerical fact precision ≥99%, fact/unit recall ≥97%, query ≥99%, entity binding ≥97%, segment binding ≥95%, supported route ≥95%, supported end-to-end ≥92%, unsupported/insufficient safe abstention ≥98%, wrong critical assumption <1%, confident wrong solve <0.5%, and invented explicit numerical facts exactly 0. Threshold failure blocks Phase completion for the recorded offline corpus. Live-model results are reported in a separate table and, when unavailable, production readiness remains explicitly unproven; recorded fixtures are validator/orchestration evidence, not a claim about live parser quality.

Offline CI uses recorded structured outputs and fakes; no API key is required. Focused tests cover contracts, evidence/numeric/unit validation, graph references, assumption policy, capability gate, projection, all modes, refusal/retry/failure classification, cache, telemetry/cost, prompt injection, athlete golden solve, metamorphic invariance/counterexamples, and typed-solver raw-text invariance.

Acceptance also runs the existing default/full backend suites, fast/benchmark/audit/aggregate wrappers, Phase 51–54 targeted contracts, frontend tests/typecheck/build, and exact-HEAD GitHub checks. Live API smoke is separate, manual/nightly, key-gated, capped to 20–30 cases and $0.25; if unavailable it is reported as not run, never passed.

## API and frontend

`POST /solve` remains compatible. `SolveResponse.textbook_parse` is additive and optional. It contains the terminal status, safe graph summary, evidence, assumption decisions, queries, warnings, usage summary, parse fingerprint, and source-text hash, but no raw model response, prompt, key, or answer authority.

Confirm mode uses a typed approval/correction request bound to the normalized source hash, parse fingerprint, model snapshot, prompt/schema/ontology/validator/assumption/capability/projection-policy versions, and a short expiry. Stale, expired, wrong-text, or wrong-version approvals are rejected. Every correction—numeric or structural—re-runs schema, evidence, reference, contradiction, assumption, capability, and decision gates before projection. Structural operations cover entity kind/name, fact entity/segment/event binding, segment order, event, relation, direction, initial conditions, friction state, and query subject/segment/event. Large structural changes trigger a reparse or a fully validated typed patch; no free-form GPT confirmation question is accepted.

The Understanding UI adds an accessible problem-understanding card with entities, segment timeline, explicit/context facts, evidence, inferred assumptions, query target, figure/unsupported state, and server-templated confirmation. Simple numeric/unit corrections use a validated whitelist patch without a new model call; typed structural corrections follow the revision-bound contract above. Tests cover mobile viewport layout, keyboard-only focus order, semantic headings/ARIA labels, screen-reader status announcements, confirmation persistence, and stale approval recovery. Existing answer, verification, ExplanationTrace, and VisualizationScene components remain unchanged.

## Delivery and rollback

Meaningful stages are committed and pushed to the work branch with checkpoint comments. No direct `main` push, merge, environment mutation, or deployment occurs. Final handoff documents `confirm` rollout and immediate `TEXTBOOK_PARSER_MODE=off` rollback.

Because the current desktop environment cannot spawn local shell processes, GitHub Actions is the authoritative executable test environment for this run. Local source setup and edits are still isolated to the Phase 55 work directory, and GitHub connector commits are built from an explicit changed-file manifest. This limitation must remain visible in every checkpoint and final report.

## Independent review gates

The Planning Checker is read-only and must have a different ID from the Maker. It returned PASS after all first-review findings were incorporated. A different Final Checker reviews answer authority, invented facts, evidence bypass, bindings, assumptions, figure safety, injection, failures, retry bounds, cache/privacy, raw-text branches, regressions, frontend UX, benchmark claims, and cost. Phase 55 is not complete while any valid finding remains.
