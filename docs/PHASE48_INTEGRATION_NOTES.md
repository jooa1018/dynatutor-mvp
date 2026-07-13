# Phase 48 suite integration notes

These are Maker P48-E drafts. They do not modify the product tree.

- `residuals.py` is the Phase 47 file with only tolerance/typed-check changes:
  pass/fail and near-zero decisions use the versioned central policy, while
  `describe()` and the compatibility constants remain stable.
- `suite.py` resolves validators from the capability matrix, accepts an
  authoritative optional `solver_id`, falls back deterministically for direct
  family-level calls, records typed checks while retaining legacy strings, and
  adds non-blocking tolerance-sensitivity evidence for governing residuals.
- `test_phase48_suite.py` includes policy/serialization/mutation/boundary
  coverage plus a false-positive harness for collision, work-energy, massive
  pulley, rigid-body velocity/acceleration, and vertical-circle solvers.

Integration assumptions:

1. `VerificationReport` declares `structured_checks` and `policy_version`.
2. `checks.record_verification_check` mirrors a typed check to the legacy
   message lists without treating warning/inconclusive/not-applicable as
   blocking.
3. `CapabilityMatrix.for_problem(system_type, subtype)` is preferred, though
   the suite contains a deterministic compatibility fallback.
4. `evaluate_invariants(..., policy=...)` accepts the shared policy and returns
   either the invariant draft type or the shared `VerificationCheck`; the
   adapter handles both.
5. The capability JSON validator IDs match `INVARIANT_EVALUATORS`.

Risk to verify after integration: the old residual tolerance was
`abs_tol + rel_tol*scale`; the central policy intentionally uses its own
versioned `max(floor, relative)` rule. Boundary tests should assert the policy,
not the old arithmetic.

