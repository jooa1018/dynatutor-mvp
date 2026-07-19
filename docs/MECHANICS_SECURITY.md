# Generic Mechanics Engine Security Model

## Security objective

The mechanics engine treats model output, textbook text, uploaded images, and
user-supplied corrections as untrusted data.  Only server-validated Generic
Mechanics IR, deterministic law applications, deterministic solver candidates,
and independent verification may contribute calculation authority.

The primary failures to prevent are invented explicit facts, source-number
swaps, hidden assumptions, answer-authority injection, arbitrary expression
execution, ambiguous root selection, unsafe legacy fallback, corpus leakage,
and stale cached calculations.

## Implementation boundary

The Stage 1 mechanics package currently implements the Draft/IR contracts,
bounded math AST, validation, SI normalization, recursive accepted-IR
immutability, calculation fingerprint, and the strict Phase 55 compatibility
adapter.  The law compiler, equation graph, solver, independent verification,
mechanics cache/orchestrator, rollout integration, and figure correction UI are
required controls for later stages.  Sections that describe those components
state their security contract; they are not claims that the components or
their tests already exist.

## Trust boundaries

```text
untrusted text/image
  -> one bounded Structured Outputs model response (untrusted DraftV1)
  -> server evidence, authority, graph, unit, and AST validation
  -> recursively immutable verified IRV1
  -> [required downstream] deterministic laws and constraints
  -> [required downstream] bounded equation graph and math backend
  -> [required downstream] candidate verification
  -> [required downstream] student-visible result
```

The optional repair is one fresh full modeling call for repairable structural
errors.  It does not create a classifier/parser/equation-selection AI chain.
An optional explanation call occurs after deterministic solving and receives no
authority to change a value or verification verdict.

## Answer-authority prohibition

Draft pre-validation rejects answer, expected-answer, selected-equation,
solver-result, grading, verification-result, and equivalent authority fields at
any bounded depth.  The scan rejects cycles, non-string mapping keys, excessive
depth/nodes/field length/hit count, and traversal failure.

Model confidence and `principle_hints` may not bypass law applicability, graph
closure, domain filtering, or verification.  `system_type` and subtype are
diagnostic labels only.  The compiler and solver must be invariant when those
labels are absent or wrong.

## Source and numeric integrity

For text facts the server verifies exact quote reconstruction, source and
quantity spans, complete numeric-token grammar, occurrence identity, and the
value/unit claimed by the quantity.  It rejects context numbers reused as
physical facts and values derived by the model but presented as explicit.

For figure facts the implemented Stage 1 validator verifies content-addressed
asset identity, page ancestry, region bounds, bounded label/relation tokens,
numeric occurrence reuse, and required confirmation.  Cross-modality semantic
value conflict detection and explicit figure-scale evidence are required Stage
6 controls; until they exist, a figure-derived value cannot bypass the existing
confirmation/authorization gate.  Figure pixels and normalized coordinates are
not themselves physical lengths or angles.

Server defaults and user corrections use externally supplied immutable
authorization records.  Authorization ID, role, subject and interval/event
scope, and value/unit must match exactly.  A model-authored `approved`
disposition is not authorization.  Correction revision is separately managed
metadata; the current `CorrectionAuthorization` record does not itself carry a
revision field.

## Expression and unit safety

The runtime must not call `eval`, unrestricted `sympify`, execute Python, or
interpret raw equation strings.  Math relationships use the discriminated,
frozen AST in `backend/engine/mechanics/math_ast.py`.  The validator enforces
operator, symbol, shape, dimension, depth, node, branch, vector, calculus, and
aggregate-expression bounds before compilation.

Raw numeric input uses a complete-token parser with Unicode normalization,
bounded decimal exponent and magnitude, nonzero-underflow detection, and
finite scalar or bounded-vector values.  Tensor-shaped SI data is
contract-representable only through a separately trusted typed path; untrusted
raw tensor syntax is rejected.  Only a finite alias table maps units into Pint
or the internal shim; untrusted unit syntax never reaches either parser.

Solvers require separate time, equation, unknown, branch, symbolic, and numeric
resource limits.  Timeout, non-finite output, dimension disagreement, rank
failure, or backend error is terminal and produces no partial answer.

## Deterministic compiler and solver boundary

The required downstream law rules generate equations from generic entities, frames, quantities,
interactions, constraints, and state.  A law records its scope, source facts,
assumptions, constraints, and generated unknowns.  The compiler uses stable
ordering and bounded search, and diagnoses underdetermined, conflicting, or
unsupported graphs instead of selecting a family-specific escape route.

The downstream solver must check all candidate roots independently for equation residuals, units,
query binding, declared inequalities, event order, nonnegative time, positive
physical parameters, and applicable friction/contact/rope regimes.  Automatic
answering is permitted only when exactly one candidate remains physically
valid.  Multiple valid candidates require confirmation or a multi-answer query
contract; zero valid candidates stop.

Downstream verification must not simply repeat the same algebraic path.  Where applicable
it uses an independent residual, conserved quantity, alternative closed
equation set, or physical-domain check.  Verification results are additive to,
not replacements for, the Phase 55 `VerificationReport` and
`ExplanationTrace` contracts.

## Corrections, cache, and observability

Accepted IR is recursively immutable.  The correction workflow is required to
manage and increment revision externally, revalidate the complete draft with
fresh external authority, and renormalize all values.  A physical, binding, or
authority change produces a new calculation fingerprint; a revision-only
change may retain that physical hash but must change cache identity.  No
in-place mutation may retain an old fingerprint or cached solve.

The required mechanics cache identity includes source text/image content hashes; model and prompt
hashes; schema/IR, validation, normalization, law, compiler, solver, and
verification versions; and correction revision.  A mismatch fails closed.

Telemetry may contain bounded counts, timings, token usage, cost, version
identities, terminal status, and content hashes.  It must not contain raw
problem text, raw model output, uploaded textbook pages, API keys, private
corpus text, or student corrections.  Uploaded assets are MIME/size/page
bounded and temporary.

## Prompt and evaluation isolation

Instructions embedded in problem text or an image are textbook content, not
system instructions.  The model prompt and server validator do not allow that
content to alter schemas, tools, retry limits, storage policy, or answer
authority.

Production code under `backend/engine/**` must not import or read public corpus
fixtures, case IDs, family labels, expected system types, expected answers, or
gold graphs.  The evaluation harness exposes only problem text and an optional
independent synthetic-figure reference until a result is frozen; gold is opened
only by the evaluator.  Private corpus text is supplied by an environment path,
never committed or logged, and absence is reported as `NOT RUN`.

The combined Beer 12th-edition PDF is a development reference for Dynamics
Chapters 11-19 structure only.  It is not a runtime dependency, prompt fixture,
or exact-match oracle.  No page, problem text, number set, diagram, page/problem
identifier, or edition mapping may be copied into code, tests, logs, artifacts,
or routing logic.

## Legacy and rollout controls

Required rollout modes are `off`, `shadow`, `confirm`, `auto`, and `required`.  `off` preserves
the Phase 55/legacy rollback.  `shadow` cannot alter the user result.  `confirm`
requires review of the physical model.  `auto` is allowed only after every
generic gate passes.  `required` never falls back around a blocked generic
gate.

Later runtime integration must ensure legacy adapters consume the same fresh validated authority and cannot
inject raw text, `system_type`, equations, or a specialized answer after a
generic safety failure.  A blocked response is neutral: it must not expose a
conflicting route, equation, free-body diagram, or guessed value.

Production mode/env changes, deployment, merge, and Draft removal require
separate operator authorization and are outside Phase 56 implementation.

## Adversarial review checklist

- Change or remove `system_type`; compiler output and answer stay invariant.
- Rename IDs and reorder set-like collections; deterministic physical meaning
  and final result stay invariant while vector components and frame axes retain
  order.  The v1 calculation fingerprint is intentionally ID-sensitive.
- Replace, duplicate, or move a number in text; explicit fact validation fails.
- Supply a derived or context number as explicit; acceptance fails.
- Submit answer, selected equations, verification, or grading fields; schema
  pre-scan fails closed.
- Submit an unknown operator, forged model instance, excessive AST, cycle,
  non-finite literal, or dimension overflow; validation fails.
- Mutate an accepted root, nested model, AST, or collection; mutation is
  rejected and its fingerprint cannot become stale.
- Forge an assumption/correction ID or change any authorized binding/value;
  acceptance fails.
- Use a figure region outside the asset or wrong page ancestry; Stage 1
  validation stops.  Missing scale, ambiguous arrows, and text/figure conflicts
  must stop once the Stage 6 observation/conflict gates are connected.
- Produce zero, multiple, negative, wrong-regime, or high-residual roots; no
  confident single answer is emitted.
- Force legacy fallback after a generic block; neutral blocked status remains.
- Search runtime for corpus case/family/gold or textbook-specific strings; none
  are present.
- Run without private data or live credentials; status is `NOT RUN`, never
  fabricated PASS.

Before rollout, these controls must be verified by targeted schema, validation,
normalization, anti-leak, metamorphic, physics, figure, integration, and final
read-only Checker tests.  Documentation alone is not evidence that any test ran.
