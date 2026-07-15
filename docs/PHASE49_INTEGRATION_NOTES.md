# Phase 49 Integration Notes

## State and scope

Phase 49 implements an offline consistency harness. The focused suite and
runner executed in Actions, and the committed deterministic report has
`status: passed` and `passed: true`. Those fields record actual runtime
evidence; they are not a pass inferred from static inspection.

The offline harness is not imported by the normal student solve/API path. It
never overwrites a student answer, product numeric output, or independent
oracle; only offline verification/selection evidence is attached to its
product result. The harness does not alter the Phase 48 API schema or routing.
The only production-path implementation change in this atomic commit is the
bounded projectile algebraic-root cache; it preserves root order and exact
expressions while rebuilding candidate and selection evidence per solve.

## Immutable evidence and versions

- Oracle schema: 2
- Oracle: `phase49-oracle-v1`
- Benchmark: `phase49-benchmark-v1`
- Metamorphic relations: `phase49-metamorphic-v1`
- Report schema: 2
- Report: `phase49-solver-consistency-report-v2`
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
→ preserve the lower-level solver/generator selection summary
→ Phase 47 output validation from actual `Answer.output_key` /
  `AnswerItem.output_key` provenance
→ Phase 48 `verify_result`
→ typed `observation_from_solver_result`

The lower-level decision summary and output-validation decision are retained
as separate evidence. A present lower-level decision must already be
`selected`, and the output-validation decision must also be `selected`; neither
failure can be promoted by the other. The output-validation decision is
installed as the semantic `SolverResult.selection_decision` before the
consistency core reads roots, so the core still checks every selected root
against the typed `Answer`/`AnswerItem` value. The report records both statuses,
the preserved solver/generator summary, and
`semantic_selection_evidence_source=p47_output_validation`.
Where the central `REQUESTED_OUTPUT_SYMBOLS` contract declares an unambiguous
symbol-to-semantic alias within the requested output set, the runner also
requires the lower-level selected value to agree with the output-validation
value under the Phase 48 tolerance policy. It does not infer aliases from
symbolic/display text or accept an undeclared numeric coincidence.

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

`build_implemented_not_executed_report` remains the deterministic
pre-execution fallback built only from immutable fixtures and capability
roles. The committed JSON and Markdown files are instead exact deterministic
renders of the successful `run_suite` / `write_reports` execution. Running
the suite again with unchanged fixtures and code produces byte-identical
reports.

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
(`CreateProcessAsUserW failed: access denied`), so runtime results were
obtained from Actions. The report-generation run produced the committed passed
artifacts, and the release workflow independently covers backend, frontend,
wrapper, warm/cold runtime, and fixed-baseline performance gates.
