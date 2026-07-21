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

Stages 0-3 are implemented and accepted.  They provide the repository/security
audit and ADR; frozen Draft/IR contracts and bounded math AST; validation, SI
normalization, recursive accepted-IR immutability, calculation fingerprint,
and the strict Phase 55 compatibility adapter; the bounded one-call modeler;
and the deterministic law compiler and immutable `EquationGraph`.

Stage 4 implements the mechanics-local planner, safe typed-AST translation,
bounded symbolic and numeric candidate generation, spawned-process timeout and
resource isolation, a separate plan-only completeness audit, independent
all-candidate verification, terminal selection, and solved-only evidence
adaptation.  The graph-only `solve_verified_equation_graph` pipeline connects
those boundaries without accepting raw text, family labels, expected answers,
legacy solver output, or caller-selected backends.  Event and initial-condition
execution remains explicitly unsupported until its backend semantics are
implemented.  Mechanics cache/orchestrator and rollout integration remain
later-stage work.

## Trust boundaries

```text
untrusted text/image
  -> one bounded Structured Outputs model response (untrusted DraftV1)
  -> server evidence, authority, graph, unit, and AST validation
  -> recursively immutable verified IRV1
  -> deterministic laws and constraints
  -> immutable bounded EquationGraph + graph fingerprint
  -> graph-bound plan + safe typed-AST translation
  -> isolated bounded candidate generation + independent plan-only audit
  -> independent verification of every retained candidate + terminal selection
  -> solved-only evidence adapter
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

The frozen `SolverBudget` centrally bounds equation, unknown, candidate, AST,
operation, symbolic/numeric/verification time, timeout-termination grace,
numeric-start, iteration, and tolerance resources.  The termination grace is
finite and positive, defaults to 0.5 seconds, is capped at 5 seconds, and is
part of the canonical plan fingerprint.  Resource counts, indices, multiplicities, degrees, and
ordinals use strict integers (booleans and numeric strings are rejected), and
semantic flags use strict booleans.  Finite floating-point fields may accept a
JSON integer but reject booleans, NaN, and infinities.  Typed AST literals and
Equation Graph SI values apply the same Boolean rejection, and tensor rows are
finite, bounded, and rectangular.  Hard timeouts cannot be achieved by elapsed-time checks
in the same unrestricted process: backend and completeness-audit execution run
in separate spawned processes that can be terminated, killed, and reaped.  `SolverTimeout`
is diagnostic data recording the exact phase, backend, limit, and elapsed time;
it never authorizes a partial answer.  Timeout, non-finite output, dimension
disagreement, rank failure, or backend error is terminal and produces no
selected candidate.

## Deterministic compiler, planner, solver, and verification boundary

Implemented law rules generate equations from generic entities, frames,
quantities, interactions, constraints, and state.  A law records its scope,
source facts, assumptions, constraints, and generated unknowns.  The compiler
uses stable ordering and bounded search, and diagnoses underdetermined,
conflicting, resource-limited, or unsupported graphs instead of selecting a
family-specific escape route.

The immutable `EquationGraph` is embedded in every `SolvePlan` and is the only
solve authority.  The public graph fingerprint is derived from that
object.  Omitting it computes it; an explicitly supplied value is accepted
only when it is the exact derived value, so normal Python and JSON dumps are
valid constructor inputs while `null`, zero, stale, or competing values fail.
Query, selected equality, inequality, constraint, initial-condition, event,
source-evidence, known-symbol, unknown-symbol, and bounded structure fields
must exactly equal deterministic graph-derived values.  Event authority is the
sorted unique union of equation, constraint, initial-condition, and law-application
scope events plus symbol event bindings; both the plan event IDs and
`has_event_condition` reflect that complete union.  The canonical plan
fingerprint includes the complete graph, exact graph fingerprint, policy,
budget, backend, and all plan fields.  It follows the same omit-to-compute or
explicit-exact-to-restore rule.  Replacing the graph therefore changes plan
identity, and `model_dump`/`model_validate` and their JSON equivalents round
trip without weakening fingerprint validation.

Backend selection is one closed deterministic function of graph structure:
piecewise syntax has first priority, then derivatives select `ode_ivp`.
Integral and vector-only syntax (`VectorNode`, `Dot`, `Cross`, or `Norm`) is
never certified from an inner scalar degree and conservatively selects
`nonlinear_symbolic`.  Otherwise, a certified polynomial degree at most one
selects `linear_symbolic`, a higher certified degree selects
`polynomial_symbolic`, and an uncertified/non-polynomial structure selects
`nonlinear_symbolic`.  Only `nonlinear_symbolic` has the exact
`numeric_root` fallback.  `event_root` and `constrained_optimization` are
reserved until `EquationGraph` gains explicit corresponding structural
features; an event ID alone does not authorize either backend.  A plan also
requires explicit backend semantics before event or initial-condition authority
can participate in solving; current event/initial-condition plans close as
`unsupported` rather than claiming exhaustive algebraic coverage.  A plan also
requires non-conflicting, non-underdetermined rank, sufficient structural rank,
enough selected equalities, and selected-incidence coverage of every unknown.
AI
output, `system_type`, subtype, raw text, regex matches, corpus metadata,
expected answers, model-chosen solver names, and untrusted callables or
expressions have zero authority.  An unsupported graph/backend is an explicit
`unsupported` terminal, never a silent family-specific or numeric fallback. A
numeric fallback is graph-derived in the plan before execution and is limited
by the same central budget; a caller cannot opt into one.

Safe typed-AST-to-backend translation is the sole execution boundary.
No backend may receive unrestricted strings, callables, SymPy objects, or
opaque payloads, and production code must never use unrestricted `sympify`,
`eval`, `lambdify`, or equivalent dynamic execution.  Numeric residuals use a
finite real-only operator whitelist; complex intermediate values and domain
violations close the candidate.  Worker and audit IPC uses bounded UTF-8 JSON
bytes only, with bounded structural preflight and streaming encoding before the
finite response cap.  Every generated root remains in the
immutable `CandidateSet`; bounded-numeric or incomplete coverage cannot
authorize automatic selection.

Candidate retention is loss-detecting at the contract boundary.  Candidate IDs
are `candidate_` plus a bounded prefix of the canonical SHA-256 over every
authoritative candidate field except that self-derived ID.  The required
immutable generation manifest binds every retained candidate's global index,
canonical ID, backend, per-backend/per-branch root index, branch IDs, and full
authoritative SHA-256.  Global indices are exactly `0..n-1`; root indices are
exactly `0..group_n-1` in retained order for each `(backend, branch_ids)` group;
manifest, count, order, candidates, and hashes must agree exactly.  Root
multiplicity remains part of the hashed candidate authority.  Only
generation-complete `exhaustive_symbolic`
coverage containing exclusively exact symbolic candidates is auto-selectable.
Approximate numeric-root, IVP, event-root, and constrained-optimization
candidates use `bounded_numeric` coverage and can only produce a complete
`needs_confirmation` result.  `incomplete` coverage is also never
auto-selectable.  Every retained candidate is bound exactly to its plan's query
symbol, unknown-symbol set, selected equality set, and authorized primary
backend or predeclared numeric fallback.

The manifest closes accidental deletion, renaming, reordering, slot gaps, and
candidate/record drift at this data boundary.  A symbolic worker's self-reported
completion is still insufficient: before exhaustive coverage is accepted, a
second spawned audit receives only the immutable plan and independently checks
linear rank, univariate real-root count and multiplicity, or a conservative
multivariate signature.  Missing, timed-out, stale, mismatched, singular, or
uncertifiable audits close without automatic selection.  Numeric searches remain
bounded and non-auto-selectable regardless of their completion certificate.

The verifier checks each retained candidate independently.  Every
answer verdict requires unique check kinds for equation residual, unit
consistency, and query binding, with exact unknown-symbol provenance for the
unit check and the exact query symbol for query binding, plus source evidence
when graph evidence exists.
Graph inequalities, constraints, events, initial conditions, alternative closed
sets, and an ODE backend respectively require inequality, constraint,
event-order, initial/boundary-condition, independent-equation-set, and numerical
integration-residual checks with exact graph-derived provenance.  Initial
boundary checks name the exact condition IDs, boundary events, involved
symbols, and evidence.  Time/duration symbols (including known facts) require a
nonnegative-time check; mass/radius/length symbols require a positive-parameter
check.  Contact, friction, rope, tension, slack, or rolling law/constraint
tokens require an exact physical-regime check, and explicit momentum,
work-energy, or conservation applications require a conserved-quantity check
over their exact equations.  Optional check kinds are accepted only when they
are applicable and carry the same exact graph-derived provenance.  Failed or
inconclusive checks each have one or more canonical rejections, passing checks
have none, and top-level rejections are the exact candidate-order aggregate.
Rejection reasons are deterministically bound to check kind; every inconclusive
check maps to `verification_inconclusive`.  Automatic answering is `solved`
only for exactly one verified candidate under auto-selectable exact symbolic
coverage; the same coverage with two or more verified candidates is
`ambiguity`.  Non-auto coverage with at least one verified candidate is
`needs_confirmation`, and zero verified candidates is
`insufficient_conditions`.  Timeout, resource limit, unsupported structure,
and backend failure select nothing, contain no verified candidate and no
passing outcome, but may retain failed/inconclusive records for inspection.

Verification must not simply repeat the same algebraic path.  Where applicable
it uses an independent residual, conserved quantity, alternative closed
equation set, or physical-domain check.  `EvidenceAdapterV2` is immutable data
only and embeds the complete concrete `MechanicsSolveResult`.  It can be built
only for a `solved` result with exactly one selected matching verified outcome.
Its graph and plan fingerprints use the same round-trippable explicit-exact
rule as `SolvePlan`.  Its candidate, query, substitutions, output, checks, used-equation union, and
source-evidence union must exactly match that selection and its graph
provenance.  The output SI unit is rendered deterministically from the query
symbol's dimension in `kg,m,s,A,K,mol,cd` order (`1` for dimensionless, compact
signed exponents otherwise); arbitrary unit text is rejected.  Ambiguity and confirmation results cannot produce selected-answer
evidence.  The adapter constructs additive legacy `VerificationReport` and
`SolverExplanationEvidence` projections only from canonical checks and exact
equation/application/constraint provenance.  Vector results close legacy scalar
projection atomically while retaining V2 evidence; the adapter embeds and
executes neither legacy dataclasses nor solver objects.

Diagnostic codes have fixed severities: backend selection is informational;
numeric fallback and incomplete generation are warnings; candidate limits,
timeouts, resource limits, unsupported backends, and backend failures are
errors.  Every diagnostic, attempt, and timeout backend must be authorized by
the plan.  Timeout details/code/terminal and failure code/terminal mappings are
bidirectional, attempts are contiguous from zero, and contradictory or duplicate
failure closure codes are rejected.  Solver and independent-audit attempts are
recorded explicitly.  Diagnostic entries are ordered by fixed
phase order, backend value, diagnostic-code order, then referenced ID.  Each
non-timeout attempt must stay within the exact symbolic, numeric, or
verification limit selected by its phase/backend, and numeric-family attempts
cannot exceed the plan's numeric-start count.  A timeout has exactly one
incomplete attempt matching `(phase, backend)`; it is the final attempt and has
elapsed time exactly equal to the timeout record.  Every earlier attempt is
complete, including any earlier retry with the same phase and backend.  Its
limit is the exact phase/backend plan limit, while its elapsed time is bounded
from that limit through the plan-fingerprinted termination grace; it also
cannot exceed total diagnostic time.  Candidate-limit exhaustion closes as
`resource_limit`.
An incomplete marker may accompany a primary failure; a pre-verification
failure cannot claim complete candidate generation, while a verification-phase
failure may retain an already complete candidate set.  Without a primary
failure, incomplete generation closes as `needs_confirmation` when at least one
retained candidate verifies, and as `insufficient_conditions` when none does;
neither state can be `solved`.

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
