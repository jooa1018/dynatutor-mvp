# Phase 49 Integration Notes

## Scope

Phase 49 adds an offline consistency harness. It does not change the normal
student solve path and it never overwrites an analytic answer.

The harness compares three independently sourced views:

1. the actual registry solver after Phase 47 candidate selection and Phase 48
   verification;
2. a fixed, hand-derived versioned oracle fixture;
3. the independent analytic adapter selected by the Phase 49 capability role.

All numerical decisions reuse
phase48-tolerance-policy-v1 and all disagreements use the existing structured
VerificationCheck and VerificationReport contracts.

## Versions and coverage

- Oracle schema: 2
- Oracle: phase49-oracle-v1
- Benchmark: phase49-benchmark-v1
- Metamorphic relations: phase49-metamorphic-v1
- Report: phase49-solver-consistency-report-v1
- Fixed oracle cases: 60, exactly 10 in each required family
- Primary scalar expectations: 70; every valid case explicitly records solved/applicable and one root value
- Distinct metamorphic relation IDs and kinds: 21
- Mutation positive controls: sign, coefficient, unit, constraint/equation

The six families are incline, pulley, collision, rolling, work-energy, and
fixed-axis rotation. Primary output keys and stable equation roles come from
the central Phase 49 core contracts, not from runner-selected fixture subsets.

## Actual offline call path

For each fixed case:

CanonicalProblem builder
-> declared SolverRegistry solver
-> solve_candidates
-> Phase 47 output candidate validation and selection
-> Phase 48 verify_result
-> observation_from_solver_result
-> compare_oracle_observation

The same fixed case is separately evaluated by evaluate_secondary_analytic.
The runner imports no production equation generator and never generates
fixture expectations from a current engine result.

Collision observations are adapted only after Phase 48 momentum and
restitution checks have attached passed or warning structured equation
evidence. Missing, unrelated, or inconclusive evidence fails closed.

## Metamorphic coverage

Each relation executes and oracle-anchors the actual base and transformed
product paths, then repeats the base and transformed comparison against the
independent analytic adapter. Coverage includes unit representation,
coordinate/sign covariance, label symmetry, mass cancellation, homogeneous
scaling, limiting cases, Galilean covariance, conservation-budget invariance,
and an actual Korean extraction-routing-solver paraphrase pair.

## Mutation controls

Mutation controls copy an actual passing observation and mutate only that
copy. The independent oracle is unchanged.

- sign: negates a collision output;
- coefficient: substitutes a deliberately wrong incline coefficient result;
- unit: changes only the typed rolling unit;
- constraint/equation: substitutes the ideal-pulley result and wrong equation
  role for a massive-pulley observation.

The product SolverResult and student answer are never modified.

## Commands

From backend:

    pytest -q -o addopts='' tests/test_phase49_solver_consistency.py
    pytest -q -o addopts='' tests/test_phase49_oracles_metamorphic.py
    pytest -q -o addopts='' tests/test_phase49_mutation_audit.py
    python tools/run_phase49_consistency.py

Repository wrappers remain:

    bash scripts/check_backend_fast.sh
    bash scripts/check_backend_benchmark.sh
    bash scripts/check_backend_audit.sh
    bash scripts/check_all.sh

The committed WIP report records implemented_not_executed until the runner is
executed in a usable Python environment. An unexecuted item is never reported
as passed.
