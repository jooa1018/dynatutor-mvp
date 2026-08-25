# Phase 56 Stage 7 gold-isolation boundary

Status: **frozen before public corpus problem text is opened**

## Two physical trust domains

Stage 7 separates execution and scoring in code and data flow.

```text
public scorer metadata/gold
        │  (never sent to runtime)
        ├─ generic evaluator adapter emits source-grounded typed input only
        ▼
runtime/input domain
  opaque random token
  problem text OR validated typed Draft input
  optional bounded synthetic image bytes
  user-like mode/options
        │
        ▼
Generic normalization → authorization → laws/compiler → Equation Graph
→ plan → all candidates → independent verification → immutable snapshot
        │
        └─ only after freeze: scorer reconnects token to gold
```

Implementation boundaries:

- `runtime_domain.py` defines the only evaluator-to-runtime input and immutable
  runtime snapshot;
- `gold_domain.py` defines case identity, family, expected terminal, expected
  answer/tolerance, and gold semantic projection;
- `runtime_domain.py` cannot import `gold_domain.py`;
- production `backend/app` and `backend/engine` cannot import the evaluator or
  public fixture directory;
- production Docker copies only `app` and `engine`, not `evaluation`, `tests`, or
  fixtures.

## Runtime allowlist

Runtime input may contain only:

- an opaque 128-bit hexadecimal execution token;
- problem text, or one validated `MechanicsProblemDraftV1`-shaped JSON payload;
- up to four bounded image byte objects with verified SHA-256;
- a closed set of user-like mechanics options.

The token is correlation-only and is excluded from cache identity.  Runtime
cache material is canonical JSON over actual user/typed input, image hashes and
bytes, and options.  It contains no scorer metadata.

Typed input receives a recursive, bounded JSON audit.  It rejects snake-case,
camel-case, kebab-case, or spaced aliases of forbidden fields, including:

- case/problem ID, split, family;
- expected system type or terminal;
- gold/gold graph;
- expected/reference/final answer and tolerance;
- chapter, section, tags, difficulty, failure label;
- reference expression;
- selected solver/root/result or verification/grading authority;
- filename/path routing metadata;
- private/full-corpus markers.

No model or corpus string is executed.  The evaluator does not evaluate a
reference expression.

## Immutable snapshot before scoring

Runtime output is frozen as `RuntimeDomainSnapshotV1` before the scorer receives
it.  The snapshot binds:

- opaque token and runtime cache SHA;
- neutral runtime terminal;
- optional solved answer only for exactly one verified candidate;
- runtime-produced semantic role projection;
- calculation, graph, plan, candidate-set, and verification fingerprints;
- candidate/verified counts;
- bounded sanitized diagnostics and execution-call counters.

A non-solved snapshot cannot carry an answer.  A solved snapshot requires one
verified candidate.  The scorer cannot mutate the snapshot or rerun runtime with
expected data.

Tests prove that changing case ID, family, split, expected terminal, expected
answer, unit, or tolerance does not alter runtime input, cache material, or a
deterministic runtime result.

## Gold/scoring domain

Only the scorer may read:

- case ID and public split;
- evaluator family for aggregation;
- scope-adjusted expected terminal;
- finite expected answer/unit/direction/tolerance for accepted cases;
- semantic gold graph projection;
- failure labels for triage.

The scorer uses semantic roles and Counters.  Model-chosen IDs and array order
have no scoring authority, while repeated equal facts keep multiplicity.

Lane B may use a generic gold-structure-to-Draft adapter to test deterministic
engine behavior.  That adapter must project only source-grounded entities,
facts, relations, events, queries, and authorized assumptions.  It cannot branch
on case ID/family, copy expected answers into the Draft, execute reference
expressions, or claim AI parser quality.

## Report redaction

CI artifacts may contain aggregate metrics, capability aggregates, terminal
confusion counts, failure taxonomy counts, bounded mismatch signatures,
privacy-safe hashes, exact code/evaluator/corpus hashes, and run IDs.

Artifacts reject raw problem text, full gold graphs, expected answers/tolerances,
reference expressions, raw provider output, raw image/base64, prompt content,
private manifest material, credentials, and secret-like markers.  Public JSONL
fixtures may exist only in the approved test fixture directory; they are not
copied into result artifacts or the production image.

## Offline/network boundary

Stage 7 evaluation requires empty `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` plus
empty provider base-URL overrides.  Dependency installation occurs before the
evaluation guard.  During evaluation, socket creation and connection attempts
fail immediately.  Fake/recorded providers are in-process deterministic test
doubles; actual model calls remain zero.
