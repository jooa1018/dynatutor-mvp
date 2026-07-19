# Generic Mechanics IR v1

## Purpose and authority boundary

The Generic Mechanics IR is the calculation-authoritative, edition-independent
description of a mechanics problem.  It records bodies, points, frames, motion
intervals, events, quantities, geometry, interactions, constraints, state, and
queries without choosing a problem family or a specialized solver.

The wire contract and the verified contract are deliberately separate:

```text
one MechanicsModeler Structured Outputs response
    -> MechanicsProblemDraftV1
    -> deterministic evidence and authority validation
    -> deterministic SI normalization
    -> MechanicsProblemIRV1
```

Only `MechanicsProblemIRV1` may enter the law compiler.  Model output is never
an equation, root-selection, verification, grading, or final-answer authority.
`metadata.system_type`, `metadata.subtype`, confidence, and `principle_hints`
are diagnostics or search-order hints.  Removing or changing them must not
change compiler applicability or a solved result.

The contract constants are defined in
`backend/engine/mechanics/contracts.py`:

- draft schema: `dynatutor.mechanics_problem_draft`, version `1.0`
- verified schema: `dynatutor.mechanics_problem_ir`, version `1.0`
- safe math AST: `mechanics-math-ast-v1`
- normalization and validation policy versions are stored in every accepted IR

## Top-level model

Both draft and verified forms contain these bounded collections:

| Area | Purpose |
| --- | --- |
| `metadata` | Language, correction revision, model/prompt/source identities, and diagnostic labels |
| `source_assets`, `source_evidence` | Hash-addressed source assets and exact text or bounded figure evidence |
| `entities`, `points` | Generic physical primitives and named/material/geometric points |
| `reference_frames` | Origin, axes, sign conventions, and frame relationships |
| `motion_intervals`, `events` | Piecewise motion scopes and shared boundary events |
| `symbols`, `quantities` | Typed symbols and physical values with bindings and dimensions |
| `geometry` | Topology and geometric relations, optionally expressed as safe AST |
| `interactions` | Physical contacts, fields, forces, springs, damping, joints, and collisions |
| `constraints` | Typed kinematic, geometric, dynamic, constitutive, contact, rolling, rope, or joint relations |
| `state_conditions` | Initial, boundary, contact, friction, rope, rolling, motion, and regime state |
| `queries` | Exact target, scope, component, shape, dimension, and requested output unit |
| `principle_hints` | Non-authoritative model hints |
| `assumptions` | Visible proposals and externally authorized assumptions |
| `ambiguities`, `figure_dependency`, `unsupported_features` | Reasons to confirm, require a figure, or stop safely |

Identifiers are explicit.  References are validated across the complete graph,
including entity/point/frame, interval/event, quantity/symbol, constraint, and
evidence links.  A model may not rely on list position as identity.

## Draft and verified quantity semantics

A draft quantity carries its semantic role, subject and optional
point/frame/interval/event bindings, scalar/vector/tensor shape, seven-base-SI
dimension, provenance, evidence, and an optional raw value/unit pair.  Raw
values and units must be present together.

Normalization produces an `IRQuantity` with an additional SI value/unit pair.
The raw and SI pairs are both absent for unknowns and both present for known
values.  Scalar, vector, and tensor shapes are checked against the stored SI
value.  Numeric parsing uses the Phase 55 complete-token grammar and a finite
unit alias table; no arbitrary unit expression reaches the unit backend.

The seven base dimensions are mass, length, time, electric current,
temperature, amount of substance, and luminous intensity.  Angle is
dimensionless in the unit backend but uses explicit angle unit aliases where a
quantity requires them.  The current raw-value normalizer accepts scalar and
bounded vector input.  Although IR can represent a bounded tensor SI value,
untrusted raw tensor syntax is rejected until it has a separately trusted typed
input path.

## Evidence and provenance

Every calculation-authoritative explicit value or explicit source relation
must be supported by validated evidence.

Text evidence includes an exact quote, source span, optional quantity span, and
occurrence index.  The server reconstructs the quote from the supplied source
text and binds a physical numeric token to the claimed quantity occurrence.
The same occurrence cannot be silently reused for a different explicit fact.

Figure evidence includes the content-addressed asset, optional page ancestry,
a normalized bounding box or polygon, a recognized label or visual relation,
and confidence.  Figure-derived physical values require the configured
confirmation/authorization path.  Image coordinates are evidence locations,
not physical coordinates.

Quantity provenance is one of:

- `explicit_source`: validated text or figure evidence;
- `user_correction`: an exact immutable correction authorization;
- `server_default`: an exact immutable server assumption authorization;
- `inferred`: not an explicit source fact and not a model-provided final value;
- `unknown`: an unknown for deterministic compilation and solving.

An assumption written by the model cannot authorize itself.  An approved
assumption must match an externally supplied authorization ID and immutable
identity/value fields.  User corrections similarly retain their correction ID,
revision, binding, value, and provenance through normalization.

## Safe mathematical relationships

Relationships are Pydantic discriminated unions, never executable strings.
The allowed AST includes literals, symbol references, bounded vectors,
arithmetic, dot/cross products, trigonometry, square root, derivative,
integral, norm, piecewise expressions, equality, and inequality.

Every node is frozen.  Child collections are tuples.  Validation enforces:

- an operator whitelist and schema-valid discriminators;
- bounded depth, node count, vector length, branch count, and calculus order;
- a closed symbol table;
- scalar/vector shape rules;
- seven-base-SI dimension inference;
- aggregate expression limits across a problem.

Raw Python, SymPy, function-call, import, or expression text is not part of the
IR and must not be interpreted by the compiler.

## Acceptance lifecycle

The server validates a draft against the original trusted inputs and external
authorizations.  Outcomes are terminal and fail closed:

- accepted: all authority, graph, evidence, figure, numeric, unit, and AST
  checks pass;
- needs confirmation, needs figure, or insufficient information: return a
  neutral blocked diagnosis without equations, FBD claims, or a guessed route;
- invalid/unsupported: return the bounded reason and no IR.

Normalization is atomic.  A conversion or construction failure returns no
partial IR and no calculation fingerprint.  An accepted IR is recursively
immutable: the root, nested models, and their collections cannot be changed
after validation.  A correction therefore creates a fresh draft and a fresh
accepted IR rather than mutating calculation authority in place.

## Calculation fingerprint and cache identity

The calculation fingerprint is a canonical SHA-256 projection of the verified
physical graph.  It retains normalized values, dimensions, bindings,
provenance, linked assumption-policy and correction identity, queries, and
relationships.  Unlinked or rejected assumption diagnostics are excluded.
It deliberately excludes schema and policy versions; those belong to the
broader cache identity.  It canonicalizes top-level and set-like ordering while
preserving ordered mathematical components and frame axes.  Identifiers remain
part of this v1 projection, so a consistent graph-ID rename changes this hash
even when deterministic compilation later proves the physical result invariant.

Raw formatting, quotes, labels, model confidence, figure coordinates, and
diagnostic labels do not change a physically equivalent fingerprint.  The
required mechanics cache identity must additionally include text/image hashes,
model and prompt hashes, schema and
validation/normalization/law/compiler/solver/verification versions, and
correction revision.  A cached result must never remain valid across an
authority or policy change.

## Compatibility adapter

`phase55_adapter.py` is deterministic.  It requires and freshly revalidates the
strict `TextbookProblemParseV1` compatibility instance (whose data model extends
the V2 contract), projects only bounded effective Phase 55 authority, and
builds a DraftV1 with namespaced identifiers.  It preserves exact quantity
spans, intervals and shared boundary events, entity/relation closure, and
server assumption authorization.  Phase 55 `system_type` and subtype remain
diagnostics; they are not copied as compiler authority.

The adapter is a rollback and migration boundary, not a second AI call and not
the default architecture for new modeling.

## Synthetic example

A synthetic cart on a track may be represented by a `rigid_body` entity, a
mass-center point, a Cartesian frame, one motion interval, an explicit mass and
applied-force quantity, a contact interaction, a no-penetration constraint,
an initial velocity state, and a velocity query at the interval end.  No
`cart_problem` type is created.  The same primitives can be composed with a
rope, pulley, spring, or a later impact event without changing the IR contract.

## Evolution rules

Changes are additive within a compatible schema version.  A change that alters
calculation authority, accepted operators, normalization, evidence semantics,
or fingerprint projection requires a corresponding version increment and cache
invalidation.  Runtime code must never import evaluation case IDs, corpus
families, expected answers, or public gold graphs.  Reference textbooks and
evaluation corpora are not schema inputs or runtime dependencies.
