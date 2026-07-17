from __future__ import annotations

import math

import pytest

from engine.models import Answer, AnswerItem, CanonicalProblem, Quantity, SolverResult
from engine.services import solve_problem
from engine.solvers.collision import Collision1DSolver
from engine.solvers.energy_vibration import WorkEnergySpeedSolver
from engine.solvers.pulley import MassivePulleyAtwoodSolver
from engine.solvers.rigid_body_2d import (
    PlaneRigidBodyAccelerationSolver,
    PlaneRigidBodyVelocitySolver,
)
from engine.solvers.vertical_circle import VerticalCircleSolver
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY
from engine.verification.residuals import ResidualCheck
from engine.verification.suite import verify_result


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def _field(check, name: str):
    return check[name] if isinstance(check, dict) else getattr(check, name)


def _status(check) -> str:
    value = _field(check, "status")
    return str(getattr(value, "value", value))


def _assert_no_blocking_checks(report) -> None:
    blocking = [
        check
        for check in report.structured_checks
        if _status(check) in {"failed", "error"}
    ]
    assert not blocking, [
        (_field(check, "check_id"), _field(check, "message"))
        for check in blocking
    ]


def test_residual_check_uses_versioned_central_policy():
    check = ResidualCheck("boundary", residual=1.5e-4, scale=2.0)

    assert check.policy is DEFAULT_TOLERANCE_POLICY
    assert check.tolerance == DEFAULT_TOLERANCE_POLICY.tolerance(
        "residual", scale=2.0
    )
    typed = check.to_verification_check()
    assert typed.tolerance == check.tolerance
    assert typed.message == check.describe()


def _constant_acceleration_result(value: float) -> tuple[CanonicalProblem, SolverResult]:
    canonical = CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns={
            "v0": q("v0", 0.0, "m/s"),
            "a": q("a", 1.0, "m/s^2"),
            "t": q("t", 2.0, "s"),
        },
        requested_outputs=["final_velocity"],
    )
    result = SolverResult(
        ok=True,
        answer=Answer(numeric=value, unit="m/s", display=f"vf = {value} m/s"),
        answers=[
            AnswerItem(
                "최종속도",
                "vf",
                value,
                "m/s",
                f"vf = {value} m/s",
                "primary",
                output_key="final_velocity",
            )
        ],
    )
    return canonical, result


def test_verify_result_records_policy_and_typed_governing_residual():
    canonical, result = _constant_acceleration_result(2.0)

    report = verify_result(
        canonical, result, solver_id="constant_acceleration_1d"
    )

    assert report.passed
    assert report.policy_version == DEFAULT_TOLERANCE_POLICY.policy_version
    residuals = [
        check
        for check in report.structured_checks
        if _field(check, "category") == "equation_residual"
    ]
    assert residuals
    assert all(_status(check) == "passed" for check in residuals)
    assert all(_field(check, "applicability") for check in residuals)
    assert any(message.startswith("역대입:") for message in report.checks)


def test_mutated_governing_answer_is_blocked():
    canonical, result = _constant_acceleration_result(2.5)

    report = verify_result(
        canonical, result, solver_id="constant_acceleration_1d"
    )

    assert not report.passed
    assert any(
        _field(check, "category") == "equation_residual"
        and _status(check) == "failed"
        for check in report.structured_checks
    )


def test_near_boundary_residual_gets_nonblocking_sensitivity_evidence():
    threshold = DEFAULT_TOLERANCE_POLICY.tolerance("residual", scale=2.0)
    canonical, result = _constant_acceleration_result(2.0 + 0.9 * threshold)

    report = verify_result(
        canonical, result, solver_id="constant_acceleration_1d"
    )

    assert report.passed
    sensitivity = [
        check
        for check in report.structured_checks
        if _field(check, "check_id").endswith(":sensitivity")
    ]
    assert sensitivity
    assert all(_status(check) not in {"failed", "error"} for check in sensitivity)


def test_optional_family_fallback_is_deterministic():
    canonical, result = _constant_acceleration_result(2.0)

    report = verify_result(canonical, result)

    assert report.passed
    assert not any(
        _field(check, "check_id") == "capability:missing"
        for check in report.structured_checks
    )


def test_named_missing_capability_fails_closed():
    canonical, result = _constant_acceleration_result(2.0)

    report = verify_result(canonical, result, solver_id="does_not_exist")

    assert not report.passed
    assert any(
        _field(check, "check_id") == "capability:missing"
        and _status(check) == "failed"
        for check in report.structured_checks
    )


def _valid_solver_cases():
    collision = CanonicalProblem(
        system_type="collision_1d",
        raw_text="반발계수 e=0.5인 비탄성 충돌",
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 3.0, "kg"),
            "v1": q("v1", 4.0, "m/s"),
            "v2": q("v2", 0.0, "m/s"),
            "e": q("e", 0.5, ""),
        },
        requested_outputs=["v1_after", "v2_after"],
    )
    work_energy = CanonicalProblem(
        system_type="work_energy_speed",
        raw_text="v0=1m/s인 2kg 물체에 알짜일 30J가 작용한다.",
        knowns={
            "m": q("m", 2.0, "kg"),
            "v0": q("v0", 1.0, "m/s"),
            "W": q("W", 30.0, "J"),
        },
        requested_outputs=["final_velocity"],
    )
    massive_pulley = CanonicalProblem(
        system_type="massive_pulley_atwood",
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 5.0, "kg"),
            "I": q("I", 0.12, "kg*m^2"),
            "R": q("R", 0.3, "m"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration", "angular_acceleration", "tension"],
    )
    rigid_velocity = CanonicalProblem(
        system_type="plane_rigid_body_velocity",
        raw_text="A점 속도와 r_B/A 벡터가 주어지고 omega는 반시계방향이다.",
        knowns={"omega": q("omega", 2.0, "rad/s")},
        coordinate_data={
            "vAx": 1.0,
            "vAy": -1.0,
            "rBAx": 3.0,
            "rBAy": 4.0,
            "omega_sign": 1,
        },
        requested_outputs=["final_velocity"],
    )
    rigid_acceleration = CanonicalProblem(
        system_type="plane_rigid_body_acceleration",
        raw_text="A점 가속도와 r_B/A 벡터, omega와 alpha 방향이 주어졌다.",
        knowns={
            "omega": q("omega", 2.0, "rad/s"),
            "alpha": q("alpha", 3.0, "rad/s^2"),
        },
        coordinate_data={
            "aAx": 0.5,
            "aAy": -0.5,
            "rBAx": 2.0,
            "rBAy": 1.0,
            "omega_sign": -1,
            "alpha_sign": 1,
        },
        requested_outputs=["acceleration"],
    )
    vertical_circle = CanonicalProblem(
        system_type="vertical_circle",
        subtype="top",
        knowns={
            "m": q("m", 1.0, "kg"),
            "R": q("R", 2.0, "m"),
            "v": q("v", 5.0, "m/s"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["tension"],
    )
    return [
        (Collision1DSolver(), collision),
        (WorkEnergySpeedSolver(), work_energy),
        (MassivePulleyAtwoodSolver(), massive_pulley),
        (PlaneRigidBodyVelocitySolver(), rigid_velocity),
        (PlaneRigidBodyAccelerationSolver(), rigid_acceleration),
        (VerticalCircleSolver(), vertical_circle),
    ]


@pytest.mark.parametrize("solver,canonical", _valid_solver_cases())
def test_valid_major_solver_is_not_falsely_rejected(solver, canonical):
    result = solver.solve(canonical)
    assert result.ok, result.verification.errors

    report = verify_result(canonical, result, solver_id=solver.name)

    assert report.passed, report.errors
    assert report.policy_version == DEFAULT_TOLERANCE_POLICY.policy_version
    _assert_no_blocking_checks(report)


def test_service_serializes_complete_typed_verification_contract():
    response = solve_problem(
        "지면에서 초속도 20m/s, 발사각 60도로 던져 같은 높이에 착지한다. 사거리는?"
    )

    assert response.ok
    assert response.verification.passed
    payload = response.verification.model_dump()
    assert payload["policy_version"] == DEFAULT_TOLERANCE_POLICY.policy_version
    assert payload["structured_checks"]
    required = {
        "check_id",
        "category",
        "status",
        "applicability",
        "observed",
        "expected",
        "absolute_error",
        "relative_error",
        "tolerance",
        "message",
        "evidence",
        "source_equation_ids",
    }
    assert required <= payload["structured_checks"][0].keys()

