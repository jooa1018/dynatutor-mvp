# Phase 49 Integration Notes

## State and scope

Phase 49 implements an offline consistency harness. Runtime acceptance remains
pending until the focused tests and runner execute in Actions. The committed
report therefore has status `implemented_not_executed`; it does not claim a
pass from static inspection.

The harness is not imported by the normal student solve/API path. It never
overwrites a student answer, a product `SolverResult`, or an independent
oracle. No Phase 48 API schema or production call path changes are part of this
phase.

## Immutable evidence and versions

- Oracle schema: 2
- Oracle: `phase49-oracle-v1`
- Benchmark: `phase49-benchmark-v1`
- Metamorphic relations: `phase49-metamorphic-v1`
- Report: `phase49-solver-consistency-report-v1`
- Tolerance policy: `phase48-tolerance-policy-v1`
- Oracle raw SHA-256:
  `9d9d26ecf70340cd7345b06c5e92ceb39d8fde429494368054e57883e6822484`
- Metamorphic raw SHA-256:
  `f141686129eb888207fdb8d947e1388fa07293333f63f9cf82221f49e55f6591`

The two fixture files are independent, reviewed inputs. The runner verifies
their raw-byte hashes before execution and never regenerates them from current
engine output.

Configured coverage is exactly 60 unique oracle cases (10 for each of incline,
pulley, collision, rolling, work-energy, and fixed-axis rotation), 70 primary
scalar expectations, 21 unique relation IDs and kinds with 21 distinct
transforms, and four unique mutation controls.

## Fixed-case execution and evidence

Every fixed case executes this actual product path:

`CanonicalProblem`
→ declared `SolverRegistry` solver
→ `solve_candidates`
→ Phase 47 candidate validation/selection
→ Phase 48 `verify_result`
→ typed `observation_from_solver_result`

The Phase 48 result is retained as the prerequisite `product_verified`
evidence. The same canonical inputs then execute
`evaluate_secondary_analytic` independently.

The runner calls and retains all three pairwise legs:

1. oracle ↔ product;
2. oracle ↔ secondary;
3. product ↔ secondary.

It also calls `compare_three_way`, whose strict result is retained separately.
The report exposes five independent 60-case counts: the Phase 48 prerequisite,
the three legs, and the aggregate. Full structured-check statuses and
leg-attributed disagreements remain in each case record. An inconclusive or
failed direct leg cannot be converted to a pass by the two oracle legs.

Collision product observations derive equation roles only from actual Phase 48
momentum and restitution evidence. Missing, unrelated, or inconclusive
evidence fails closed.

## Metamorphic execution

Each of the 21 relations performs four required typed calls:

- base product;
- transformed product;
- base secondary;
- transformed secondary.

Both product and secondary actual values are evaluated against the declared
base-to-transformed relation, in addition to their fixed oracle anchors. The
record retains the base and transformed direct legs and strict three-way
reports.

Coordinate-sign covariance intentionally changes the product coordinate
direction while the raw secondary adapter retains its declared direction. Its
`positive_direction` direct disagreement is preserved and matched against the
explicit coordinate-transform expectation; the underlying failed leg is not
rewritten. Any extra disagreement fails the relation.

The end-to-end paraphrase relation also executes two actual
`solve_problem` text calls, for six total calls in that record. It verifies
routing, typed numeric output, and the actual base-to-transformed equality.
No display text is parsed as numerical evidence.

## Mutation controls

The sign, coefficient, unit, and constraint/equation controls mutate only a
copy of an actual passing observation. Product path identity remains unchanged
so a mutation cannot be killed by an artificial identity failure.

Numeric mutants update the copied numeric value and complete root evidence
together. Unit- and equation-only mutants retain their original roots. Every
record proves that the source observation, product result, and oracle stayed
unchanged, and rejects unrelated path, solver, policy, applicability, or
semantic-output failures.

## Deterministic reports

`build_implemented_not_executed_report` constructs the committed pending
report solely from immutable fixtures and capability roles. The JSON and
Markdown files are exact deterministic renders of that object. After actual
runtime execution, `run_suite` and `write_reports` deterministically replace
them with passed or failed evidence without changing fixture data.

## Commands

From `backend`:

    pytest -q -o addopts='' tests/test_phase49_solver_consistency.py
    pytest -q -o addopts='' tests/test_phase49_oracles_metamorphic.py
    pytest -q -o addopts='' tests/test_phase49_mutation_audit.py
    python tools/run_phase49_consistency.py

Repository wrappers remain:

    bash scripts/check_backend_fast.sh
    bash scripts/check_backend_benchmark.sh
    bash scripts/check_backend_audit.sh
    bash scripts/check_all.sh

Local process creation is unavailable in the recovery environment
(`CreateProcessAsUserW failed: access denied`), so runtime results must come
from Actions. Until then, no Phase 49 PASS is asserted.
