from __future__ import annotations

import json

import pytest
import sympy as sp

from app.schemas.solution import SelectionDecisionModel
from engine.models import Answer, AnswerItem, CanonicalProblem, Quantity, SolverResult
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.validators import (
    ValidationContext,
    candidate_from_mapping,
    validate_and_select,
)
from engine.verification.conditioning import (
    diagnose_boundary_proximity,
    diagnose_local_perturbation,
    diagnose_near_cancellation,
)
from engine.verification.policy import (
    CANDIDATE_ENGINE_ID,
    DEFAULT_TOLERANCE_POLICY,
)
from engine.verification.suite import verify_result


def _status(check: dict) -> str:
    return str(check["status"])


def _diagnostic(decision, suffix: str) -> dict:
    return next(
        check
        for check in decision.diagnostics
        if str(check["check_id"]).endswith(suffix)
    )


def test_candidate_defaults_come_from_shared_policy_and_overrides_remain_exact():
    effective = DEFAULT_TOLERANCE_POLICY.for_engine(CANDIDATE_ENGINE_ID)
    context = ValidationContext()

    assert context.numerical_tolerance == effective.abs_tol
    assert context.relative_tolerance == effective.rel_tol
    assert context.residual_tolerance == effective.residual_tol
    assert context.policy_version == DEFAULT_TOLERANCE_POLICY.policy_version

    x = sp.symbols("x")
    override = ValidationContext(
        numerical_tolerance=2e-6,
        relative_tolerance=3e-6,
        residual_tolerance=4e-6,
        policy_version="compatibility-override-v1",
    )
    decision = validate_and_select(
        [candidate_from_mapping({x: 1.0}, candidate_id="only")],
        override,
    )

    assert decision.status == "selected"
    assert decision.tolerances == {
        "absolute": 2e-6,
        "relative": 3e-6,
        "residual": 4e-6,
    }
    assert decision.policy_version == "compatibility-override-v1"


def test_close_roots_are_reported_before_explicit_selection_without_choosing():
    x = sp.symbols("x")
    separation = DEFAULT_TOLERANCE_POLICY.root_separation_tol * 0.5
    candidates = [
        candidate_from_mapping({x: 1.0}, candidate_id="first"),
        candidate_from_mapping({x: 1.0 + separation}, candidate_id="second"),
    ]
    decision = validate_and_select(
        candidates,
        ValidationContext(preferred_candidate_id="first"),
    )

    assert decision.status == "selected"
    assert decision.selected_candidate.candidate_id == "first"
    check = _diagnostic(decision, "root_separation")
    assert _status(check) == "passed_with_warning"
    assert check["metadata"]["close_roots"] is True
    assert check["metadata"]["engine_id"] == CANDIDATE_ENGINE_ID


def test_actual_singular_equation_jacobian_is_warning_only_and_json_safe():
    x = sp.symbols("x")
    decision = EquationSystem([sp.Eq(x**2, 0)], [x]).solve_candidates()

    assert decision.status == "selected"
    jacobian = _diagnostic(decision, "jacobian_condition")
    perturbation = _diagnostic(decision, "local_perturbation")
    assert _status(jacobian) == "passed_with_warning"
    assert jacobian["metadata"]["singular"] is True
    assert _status(perturbation) == "passed_with_warning"

    payload = SelectionDecisionModel(**decision.to_dict()).model_dump(mode="json")
    json.dumps(payload, allow_nan=False)


def test_actual_ill_conditioned_linear_system_records_condition_estimate():
    x, y = sp.symbols("x y")
    decision = EquationSystem(
        [
            sp.Eq(sp.Float("1e-12") * x + y, 1),
            sp.Eq(y, 1),
        ],
        [x, y],
    ).solve_candidates()

    assert decision.status == "selected"
    check = _diagnostic(decision, "jacobian_condition")
    assert _status(check) == "passed_with_warning"
    assert check["metadata"]["near_singular"] is True
    assert check["observed"]["condition_number"] >= (
        DEFAULT_TOLERANCE_POLICY.condition_warning_threshold
    )


def test_candidate_mutation_still_blocks_despite_nonblocking_diagnostics():
    x = sp.symbols("x")
    decision = validate_and_select(
        [candidate_from_mapping({x: 2.0}, candidate_id="mutated")],
        ValidationContext(equations=[sp.Eq(x, 1.0)]),
    )

    assert decision.status == "no_valid_solution"
    assert any(
        check.check_id == "residual:equation-0"
        and check.status == "failed"
        for rejected in decision.rejected_candidates
        for check in rejected.checks
    )


def test_cancellation_perturbation_and_boundary_diagnostics_are_typed_nonblocking():
    cancellation = diagnose_near_cancellation(
        0.0,
        scale=2e12,
        signed_terms=[1e12, -1e12],
    )
    perturbation = diagnose_local_perturbation(
        [[1.0, 1.0], [2.0, 2.0]],
        solution_values=[1.0, 1.0],
    )
    boundary = diagnose_boundary_proximity(
        1e-10,
        0.0,
        boundary_kind="contact",
    )

    assert cancellation.status.value == "passed_with_warning"
    assert cancellation.metadata["near_cancellation"] is True
    assert perturbation.status.value == "passed_with_warning"
    assert perturbation.metadata["singular"] is True
    assert boundary.status.value == "passed_with_warning"
    assert boundary.metadata["near_boundary"] is True
    for check in (cancellation, perturbation, boundary):
        assert check.metadata["policy_version"] == (
            DEFAULT_TOLERANCE_POLICY.policy_version
        )
        json.dumps(check.to_dict(), allow_nan=False)


def test_missing_friction_boundary_state_is_explicitly_inconclusive():
    check = diagnose_boundary_proximity(
        None,
        None,
        boundary_kind="static_to_kinetic_friction",
        applicable=True,
    )

    assert check.status.value == "inconclusive"
    assert check.applicability.value == "undetermined"


def test_selection_diagnostics_reach_shared_verification_report():
    x = sp.symbols("x")
    separation = DEFAULT_TOLERANCE_POLICY.root_separation_tol * 0.5
    decision = validate_and_select(
        [
            candidate_from_mapping({x: 2.0}, candidate_id="selected"),
            candidate_from_mapping(
                {x: 2.0 + separation},
                candidate_id="alternative",
            ),
        ],
        ValidationContext(preferred_candidate_id="selected"),
    )
    canonical = CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns={
            "v0": Quantity("v0", 0.0, "m/s"),
            "a": Quantity("a", 1.0, "m/s^2"),
            "t": Quantity("t", 2.0, "s"),
        },
        requested_outputs=["final_velocity"],
    )
    result = SolverResult(
        ok=True,
        answer=Answer(numeric=2.0, unit="m/s", display="vf = 2 m/s"),
        answers=[
            AnswerItem(
                "최종속도",
                "vf",
                2.0,
                "m/s",
                "vf = 2 m/s",
                "primary",
                output_key="final_velocity",
            )
        ],
        selection_decision=decision,
    )

    report = verify_result(
        canonical,
        result,
        solver_id="constant_acceleration_1d",
    )

    assert report.passed
    root_checks = [
        check
        for check in report.structured_checks
        if check["check_id"] == "candidate:root_separation"
    ]
    assert root_checks
    assert root_checks[0]["status"] == "passed_with_warning"


def test_scale_proxy_alone_never_claims_near_cancellation():
    check = diagnose_near_cancellation(0.0, scale=1e12)

    assert check.status.value == "inconclusive"
    assert check.metadata["scale_proxy_rejected"] is True


def test_candidate_tolerance_outcome_flip_is_warning_only():
    x = sp.symbols("x")
    tolerance = DEFAULT_TOLERANCE_POLICY.for_engine(
        CANDIDATE_ENGINE_ID
    ).tolerance("residual", scale=1.0)
    decision = validate_and_select(
        [
            candidate_from_mapping(
                {x: 1.0 + 0.75 * tolerance},
                candidate_id="near-boundary",
            )
        ],
        ValidationContext(equations=[sp.Eq(x, 1.0)]),
    )

    assert decision.status == "selected"
    check = _diagnostic(decision, "sensitivity")
    assert check["status"] == "passed_with_warning"
    assert check["metadata"]["outcome_flip"] is True


def test_underdetermined_full_row_rank_jacobian_is_nonunique():
    check = diagnose_local_perturbation(
        [[1.0, 0.0]],
        solution_values=[1.0, 0.0],
    )

    assert check.status.value == "passed_with_warning"
    assert check.metadata["singular"] is True


def test_equation_system_cancellation_uses_evaluated_signed_terms():
    x = sp.symbols("x")
    decision = EquationSystem(
        [sp.Eq(x + sp.Integer(10) ** 12, sp.Integer(10) ** 12)],
        [x],
    ).solve_candidates()

    assert decision.status == "selected"
    check = _diagnostic(decision, "near_cancellation")
    assert check["status"] == "passed_with_warning"
    assert check["metadata"]["term_evidence_count"] == 2
    assert check["evidence"] == ["evaluated_signed_equation_terms"]
