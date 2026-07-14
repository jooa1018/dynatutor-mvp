# Phase 48 invariant draft audit notes

Final target paths:

- `loader.py` -> `backend/engine/capabilities/loader.py`
- `invariants.py` -> `backend/engine/verification/invariants.py`
- `test_phase48_invariants.py` -> `backend/tests/test_phase48_invariants.py`

Integration points:

- `evaluate_invariants` accepts the centralized `TolerancePolicy` and optional
  `engine_id`; every residual threshold comes from `policy.tolerance(...)`.
- Tolerance categories are `residual` for governing-equation checks,
  `conservation` for collision/work-energy, and `constraint` for kinematic,
  unilateral-contact, friction, and no-slip checks.
- The governing-equation adapter preserves the legacy
  `ResidualCheck.describe()` message so existing UI/tests continue to see the
  `역대입: ... ✓/✗` contract.
- Raw legacy answer-pool values for `T`, `f`, `omega`, and `ω` are always
  removed. They are rebuilt only from semantically typed `AnswerItem`s when the
  active model determines their meaning (for example, vibration `T=period`
  versus pulley `T=tension`).
- `CapabilityMatrix.for_problem(system_type, subtype)` is the fallback for
  service/direct verification calls where no concrete solver ID was supplied.
  Its default JSON remains adjacent to `engine/capabilities/loader.py`.
- The suite should convert each `InvariantCheck` to the central
  `VerificationCheck` contract, mapping `not_applicable` and `inconclusive` to
  structured applicability/status without demoting an otherwise valid answer.
- `ResidualCheck.passed` must be migrated to the same central policy before
  integration; otherwise its legacy glyph could disagree with the typed status
  at a tolerance boundary.
- Capability JSON validator names must use the short IDs exported by
  `INVARIANT_VALIDATOR_IDS`.

Validation note: this agent could not invoke local Python because the shared
Windows shell is unavailable (`CreateProcessAsUserW: access denied`). The root
agent must run compile/tests in GitHub Actions after integrating the drafts.
