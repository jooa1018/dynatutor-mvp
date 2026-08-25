# ADR: Phase 56 Generic Mechanics Engine

Status: Accepted for Phase 56 implementation

Baseline: `4762727e8f9191604e2531b9982a5ae72ed73db9`

## Context

The Phase 55 path provides strict source evidence, graph validation, correction
fingerprints, fail-closed parser terminals, answer-authority separation, and
legacy solver integration. Calculation still depends on a diagnostic
`system_type` label, specialized solver matching, and in several places a fresh
interpretation of `raw_text`. That routing model cannot safely express novel
compositions of ordinary mechanics primitives.

Phase 56 replaces the default calculation authority with a versioned mechanics
contract and deterministic physics compilation. The Phase 55 path remains an
explicitly gated compatibility and rollback path until parity evidence exists.

## Decision

### 1. One model-facing contract, one verified contract

One `MechanicsModeler` Structured Outputs request produces a complete
`MechanicsProblemDraftV1` from text and optional images. A deterministic server
normalizer validates evidence, references, dimensions, limits, provenance, and
well-posedness before producing `MechanicsProblemIRV1`.

```text
MechanicsProblemDraftV1
  -> source/evidence and graph validation
  -> deterministic normalization and unit conversion
  -> MechanicsProblemIRV1
```

The model never emits a verified flag, selected equation set, candidate
selection, verification result, or final answer. Repair is a fresh full-draft
request and is allowed at most once for repairable structural failures.

### 2. Stable module boundaries

Phase 56 code is rooted at `backend/engine/mechanics/`:

- `contracts.py`: model-facing and verified Pydantic contracts.
- `math_ast.py`: closed, resource-bounded expression AST.
- `normalization.py`: evidence-preserving draft-to-IR conversion.
- `validation.py`: graph, provenance, dimension, and well-posedness gates.
- `phase55_adapter.py`: deterministic `TextbookProblemParseV2` compatibility.
- `modeler.py`: the sole pre-calculation AI request boundary.
- `laws/`: reusable `LawRule` definitions and applicability predicates.
- `compiler/`: deterministic relevant-subgraph extraction and Equation Graph.
- `solver/`: equation-structure planner and symbolic/numeric backends.
- `verification/`: independent residual, domain, branch, and physics checks.

The Pydantic schema and enums are the source of truth. Documentation and cache
versions must reference the same exported version constants.

### 3. Generic IR identity and bindings

The IR contains metadata, source assets/evidence, entities, points, reference
frames, motion intervals, events, quantities, geometry, interactions,
constraints, state conditions, queries, principle hints, ambiguities, figure
dependency, and unsupported features.

Every calculable quantity is bound to its subject, optional point, frame,
interval/event, semantic role, shape, direction/component, provenance,
dimension, and source evidence. Every query has an explicit target and output
unit. IDs are opaque graph identifiers; array order and ID spelling cannot
change the compiled physics.

`system_type` is optional diagnostic metadata only. It is excluded from IR
fingerprints used by compiler, planner, solver, and verification. `raw_text` is
available only to the modeler and evidence validator; it is not passed to those
calculation layers.

### 4. Evidence and provenance

Text evidence stores an exact quote, source span, optional quantity span, and
occurrence index. Figure evidence stores asset/page identity, normalized region,
recognized label/relation, and confidence. Explicit source quantities require
server-confirmed evidence. Derived model values cannot be normalized as
explicit facts.

Allowed provenance is explicit source, user correction, inferred, approved
server assumption, or unknown. Only explicit source and separately recorded
user corrections may supply unqualified calculable facts. Corrections receive a
new revision fingerprint and the whole draft is revalidated.

The Phase 55 evidence validator remains authoritative for compatibility-adapter
text facts; Phase 56 extends rather than bypasses its quote, occurrence, unit,
reference, assumption, and answer-authority checks.

All modeler, IR, compiler, solver, and verification cache keys include text and
image hashes, model and prompt hashes, schema/IR and component versions, and the
`correction_revision`. A correction re-keys or invalidates every dependent
artifact. Phase 55 token, cost, latency, retry, and cache telemetry is preserved,
but raw problem text and raw model responses are never stored in observability,
logs, or artifacts.

### 5. Safe expression language

All equations and constraints use a discriminated AST with a fixed operator
whitelist. Symbol references must resolve through a symbol table. Literal nodes
hold finite numbers and optional dimension metadata. Node count, depth, vector
size, power, piecewise branch, derivative/integral order, and graph limits are
validated before conversion to a math backend.

No model or user string is evaluated. `eval`, `exec`, unrestricted `sympify`,
arbitrary functions, attributes, calls, imports, code generation, and backend
parser fallbacks are prohibited.

### 6. Deterministic laws, compiler, and planner

Reusable `LawRule` objects match typed IR patterns and emit typed equations with
law, entity, frame, interval, source-fact, assumption, constraint, unknown, and
dimension provenance. Hints may influence stable search priority but never
applicability.

The compiler performs bounded deterministic search, closure/rank analysis, and
stable minimal closed-set selection. Alternative closed sets are retained for
independent cross-checking. Backend selection depends only on equation graph
structure: linear/nonlinear algebra, symbolic calculus, ODE IVP, event/root,
optimization, or piecewise solve.

Every candidate is checked for dimensions, residuals, initial/boundary and
constraint satisfaction, domains, event order, contact/friction/rope regimes,
and query binding. A result is auto-selected only when exactly one candidate is
physically valid.

### 7. Compatibility and rollout

`/solve` and `/diagnose` remain backward compatible and gain additive fields.
The generic path is controlled by `off`, `shadow`, `confirm`, `auto`, or
`required`. Production configuration is unchanged by this PR.

- `off` uses the Phase 55 rollback path.
- `shadow` evaluates the generic path but preserves the legacy user result.
- `confirm` requires user confirmation of the verified IR before solving.
- `auto` solves only after every generic gate succeeds.
- `required` requires the generic modeler and never silently falls back.

For every blocked or unverified IR terminal, `/solve` and `/diagnose` return a
neutral fail-closed result. No legacy route, selected equation, FBD, or
answer-bearing artifact may be exposed when it conflicts with or bypasses the
IR gate.

Legacy solver kernels may be wrapped only when selected by an IR/equation
pattern. No adapter may be selected by `system_type`, subtype, case ID, corpus
family, expected answer, problem number, PDF identity, or raw-text regex. Once
generic parity is proven, a legacy implementation becomes a differential oracle
or a gated deprecated fallback.

### 8. Evaluation isolation

Production engine modules cannot import public/private corpus fixtures or read
case IDs, family labels, expected system types, expected answers, or gold graphs.
Public input-only data is opened only after the architecture and offline gates
are in place; gold is evaluator-only. Private input is optional and
environment-path based, with no raw text in git, logs, or artifacts.

The Beer combined-edition PDF is reference-only for Dynamics Chapters 11-19
structure. It is not a runtime dependency, routing key, fixture source, or
exact-match oracle. No textbook page or image is committed or retained in PR
content, logs, artifacts, telemetry, or test fixtures.

## Consequences

- Phase 56 adds contracts before switching calculation authority.
- Existing APIs and rollback behavior remain available during staged rollout.
- Unsupported or underdetermined inputs fail closed with precise terminals.
- The generic path requires more explicit bindings and validation but makes new
  combinations possible without family-specific routes.
- Final acceptance requires public 100/100 terminals and accepted answers,
  compositional and synthetic-figure suites, full regression CI, and an
  independent exact-head Checker.

## Non-goals

- Statics Chapters 1-10.
- Edition/problem-number mapping or textbook asset reproduction.
- Production rollout, secret changes, merge, undraft, or main push.
- Claiming private held-out or the user's Dynamics-only/SI/Korean edition passed
  without those exact materials.
