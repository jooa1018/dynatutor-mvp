# Phase 48 integration notes

This document describes the integrated product call paths at the Phase 48 Maker
WIP checkpoint. It is not an acceptance verdict.

## Shared contracts

- `backend/engine/verification/policy.py` is the single versioned tolerance
  source (`phase48-tolerance-policy-v1`). Candidate validation derives its
  default absolute, relative, residual, and policy-version values from the
  `candidate` engine view; explicit legacy constructor overrides remain exact.
- `VerificationReport.structured_checks` stores JSON-safe dictionaries that
  conform to the shared `VerificationCheck` schema. `checks`, `warnings`,
  and `errors` remain student-facing compatibility views.
- Every Phase 48 structured diagnostic records the policy version, and an
  authoritative solver/engine ID when one is available.

## Actual call paths

1. `engine.services.solve_problem` preserves Phase 47 candidate selection.
   Only a selected candidate reaches
   `verification.suite.verify_result(..., solver_id=solver.name)`.
2. `verify_result` resolves the solver capability, runs configured residual
   and invariant validators, adds non-blocking diagnostics, and merges their
   typed evidence into the existing report. It never changes an answer value.
3. `ValidationContext` uses the shared candidate-policy defaults.
   `select_solution` evaluates close-root and candidate-boundary sensitivity
   evidence before returning a selection decision. Diagnostics do not rank or
   select roots.
4. `EquationSystem.solve_candidates` evaluates the actual symbolic residual
   Jacobian at each candidate. It records rank/condition estimates, a
   deterministic linearized right-hand-side perturbation estimate, and
   signed-term cancellation evidence before the unchanged validation and
   selection call.
5. Contact-normal and static-friction validators retain the actual boundary
   value and limit. The suite records boundary proximity without changing the
   invariant result.

## Diagnostic applicability

- Jacobian condition and local perturbation are applicable only when an actual
  equation system and candidate point exist. Direct-formula solvers do not get
  a fabricated Jacobian.
- Root separation currently applies to scalar candidates with one common
  numeric output. Multi-output candidate distance is reported as not
  applicable rather than guessed.
- Near-cancellation requires evaluated opposing signed terms. A residual
  `scale` proxy by itself is explicitly inconclusive and cannot emit a false
  warning.
- Static-to-kinetic proximity is measurable when a static-friction force and
  its `mu_s*N` limit are available. A kinetic result without transition-state
  evidence is explicitly inconclusive.
- Missing NumPy is distinguished as `skipped`; malformed or unresolved
  numerical evidence is `inconclusive`. Diagnostic statuses are never
  blocking.
- Singular/non-unique systems use column-rank uniqueness, including
  underdetermined full-row-rank Jacobians. Infinite condition/amplification
  values remain string evidence; typed numeric error fields stay JSON-safe.

## Focused evidence

Focused coverage is in:

- `backend/tests/test_phase48_policy_conditioning.py`
- `backend/tests/test_phase48_invariants.py`
- `backend/tests/test_phase48_suite.py`
- `backend/tests/test_phase48_numerical_connections.py`
- `backend/tests/test_phase47_candidate_validation.py`

The numerical-connection tests cover shared policy defaults and compatibility
overrides, close roots, singular and ill-conditioned Jacobians, real local
perturbation evidence, tolerance outcome flips, signed-term cancellation,
contact/friction boundary applicability, mutation blocking, report propagation,
and JSON-safe API serialization.
