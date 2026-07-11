from __future__ import annotations

import math

from engine.canonical.adapter import attach_canonical_v2
from engine.models import Answer, AnswerItem, CanonicalProblem, Quantity
from engine.physics_core.answer_validators import validate_answer_consistency
from engine.services import _route_decision_model
from engine.solvers.energy_vibration import WorkEnergySpeedSolver
from engine.solvers.kinematics import ConstantAcceleration1DSolver
from engine.solvers.pulley.table_hanging import TableHangingPulleySolver
from engine.solvers.registry import SolverRegistry
from engine.solvers.rigid_body_2d.acceleration import PlaneRigidBodyAccelerationSolver
from engine.solvers.rigid_body_2d.velocity import PlaneRigidBodyVelocitySolver
from engine.solvers.vertical_circle import VerticalCircleSolver
from engine.verification.residuals import _collision, _work_energy


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def test_clarify_route_never_falls_back_to_first_solver():
    problem = CanonicalProblem(
        system_type="ambiguous_pulley",
        raw_text="두 질량 2 kg, 3 kg이 도르래와 줄로 연결되어 있다. 가속도는?",
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 3.0, "kg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration"],
        unknowns=["acceleration"],
        confidence="낮음",
    )
    attach_canonical_v2(problem)
    registry = SolverRegistry()

    decision = registry.route(problem)

    assert decision.status == "clarify"
    assert decision.selected_solver_id is None
    assert registry.select(problem, decision=decision) is None
    assert len(decision.candidates) >= 2


def test_route_decision_is_serializable_for_the_api():
    problem = CanonicalProblem(
        system_type="ambiguous_pulley",
        raw_text="두 물체와 도르래가 있다. 구조는 명시되지 않았다.",
        knowns={
            "m1": q("m1", 1.0, "kg"),
            "m2": q("m2", 1.0, "kg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration"],
    )
    attach_canonical_v2(problem)
    decision = SolverRegistry().route(problem)

    model = _route_decision_model(decision)

    assert model is not None
    assert model.status == decision.status
    assert len(model.candidates) == len(decision.candidates)


def test_capability_contract_covers_every_registered_solver():
    registry = SolverRegistry()

    assert len(registry.solvers) == 29
    assert set(registry._capabilities) == {solver.name for solver in registry.solvers}


def test_horizontal_drop_time_only_does_not_require_initial_speed():
    problem = CanonicalProblem(
        system_type="projectile_motion",
        subtype="general",
        raw_text="높이 20 m에서 물체를 수평으로 놓았다. 지면까지 비행시간은?",
        knowns={
            "h": q("h", 20.0, "m"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["time"],
        unknowns=["time"],
        launch_height=20.0,
        landing_height=0.0,
        launch_angle_deg=0.0,
        confidence="높음",
    )
    attach_canonical_v2(problem)
    registry = SolverRegistry()

    decision = registry.route(problem)

    assert decision.status == "select"
    assert decision.selected_solver_id == "projectile_motion"


def test_work_energy_requires_direction_and_initial_state():
    problem = CanonicalProblem(
        system_type="work_energy_speed",
        raw_text="2 kg 물체에 10 N 힘을 가해 5 m 이동했다. 최종속도는?",
        knowns={
            "m": q("m", 2.0, "kg"),
            "F": q("F", 10.0, "N"),
            "s": q("s", 5.0, "m"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["final_velocity"],
        unknowns=["final_velocity"],
        confidence="높음",
    )
    attach_canonical_v2(problem)
    registry = SolverRegistry()

    decision = registry.route(problem)

    assert decision.status == "clarify"
    assert registry.select(problem, decision=decision) is None
    missing = decision.candidates[0].missing_requirements
    assert any("initial velocity" in item for item in missing)
    assert any("direction" in item for item in missing)


def test_work_energy_accepts_explicit_rest_and_uses_force_angle():
    problem = CanonicalProblem(
        system_type="work_energy_speed",
        raw_text="정지 상태에서 2 kg 물체에 10 N 힘을 이동방향과 60도로 가해 5 m 이동했다.",
        knowns={
            "m": q("m", 2.0, "kg"),
            "F": q("F", 10.0, "N"),
            "s": q("s", 5.0, "m"),
            "theta": q("theta", 60.0, "deg"),
        },
        requested_outputs=["final_velocity"],
    )

    result = WorkEnergySpeedSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 5.0, rel_tol=1e-6)


def test_inconsistent_overdetermined_kinematics_is_rejected():
    problem = CanonicalProblem(
        system_type="constant_acceleration_1d",
        raw_text="v0=0, a=1, t=2, s=100일 때 최종속도는?",
        knowns={
            "v0": q("v0", 0.0, "m/s"),
            "a": q("a", 1.0, "m/s^2"),
            "t": q("t", 2.0, "s"),
            "s": q("s", 100.0, "m"),
        },
        requested_outputs=["final_velocity"],
    )

    result = ConstantAcceleration1DSolver().solve(problem)

    assert not result.ok
    assert any("모순" in error for error in result.verification.errors)


def test_multiple_physical_kinematic_roots_require_clarification():
    problem = CanonicalProblem(
        system_type="constant_acceleration_1d",
        raw_text="v0=10 m/s, a=-1 m/s²에서 변위가 다시 0일 때 시간은?",
        knowns={
            "v0": q("v0", 10.0, "m/s"),
            "a": q("a", -1.0, "m/s^2"),
            "s": q("s", 0.0, "m"),
        },
        requested_outputs=["time"],
    )

    result = ConstantAcceleration1DSolver().solve(problem)

    assert not result.ok
    assert result.unsupported_reason is not None
    assert "어떤 해" in result.unsupported_reason


def test_static_table_pulley_without_mu_s_returns_error_not_exception():
    problem = CanonicalProblem(
        system_type="pulley_table_hanging",
        friction_type="static",
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 1.0, "kg"),
            "g": q("g", 9.81, "m/s^2"),
        },
    )

    result = TableHangingPulleySolver().solve(problem)

    assert not result.ok
    assert any("μ_s" in error for error in result.verification.errors)


def test_static_slip_requires_separate_kinetic_coefficient():
    problem = CanonicalProblem(
        system_type="pulley_table_hanging",
        friction_type="static",
        knowns={
            "m1": q("m1", 1.0, "kg"),
            "m2": q("m2", 10.0, "kg"),
            "mu_s": q("mu_s", 0.1, ""),
            "g": q("g", 9.81, "m/s^2"),
        },
    )

    result = TableHangingPulleySolver().solve(problem)

    assert not result.ok
    assert any("μ_k" in error for error in result.verification.errors)


def test_kinetic_table_pulley_reports_friction_force():
    problem = CanonicalProblem(
        system_type="pulley_table_hanging",
        friction_type="kinetic",
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 1.0, "kg"),
            "mu_k": q("mu_k", 0.2, ""),
            "g": q("g", 9.81, "m/s^2"),
        },
    )

    result = TableHangingPulleySolver().solve(problem)

    assert result.ok
    by_symbol = {item.symbol: item for item in result.answers}
    assert "f_k" in by_symbol
    assert math.isclose(by_symbol["f_k"].numeric, 3.924, rel_tol=1e-6)


def test_vertical_circle_force_requires_mass():
    problem = CanonicalProblem(
        system_type="vertical_circle",
        subtype="top",
        knowns={
            "R": q("R", 1.0, "m"),
            "v": q("v", 4.0, "m/s"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["tension"],
    )

    result = VerticalCircleSolver().solve(problem)

    assert not result.ok
    assert any("질량" in error for error in result.verification.errors)


def test_vertical_circle_negative_tension_is_contact_loss():
    problem = CanonicalProblem(
        system_type="vertical_circle",
        subtype="top",
        knowns={
            "m": q("m", 1.0, "kg"),
            "R": q("R", 1.0, "m"),
            "v": q("v", 1.0, "m/s"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["tension"],
    )

    result = VerticalCircleSolver().solve(problem)

    assert not result.ok
    assert result.unsupported_reason is not None
    assert "이탈" in result.unsupported_reason or "느슨" in result.unsupported_reason


def test_rigid_velocity_rejects_nonzero_scalar_reference_direction():
    problem = CanonicalProblem(
        system_type="plane_rigid_body_velocity",
        knowns={
            "vA": q("vA", 2.0, "m/s"),
            "r": q("r", 3.0, "m"),
            "omega": q("omega", 4.0, "rad/s"),
        },
    )

    result = PlaneRigidBodyVelocitySolver().solve(problem)

    assert not result.ok
    assert any("벡터" in error for error in result.verification.errors)


def test_fixed_rigid_velocity_allows_magnitude_only():
    problem = CanonicalProblem(
        system_type="plane_rigid_body_velocity",
        knowns={
            "vA": q("vA", 0.0, "m/s"),
            "r": q("r", 2.0, "m"),
            "omega": q("omega", 3.0, "rad/s"),
        },
    )

    result = PlaneRigidBodyVelocitySolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 6.0)
    assert {item.symbol for item in result.answers} == {"v_B"}


def test_rigid_acceleration_never_assumes_aA_zero():
    problem = CanonicalProblem(
        system_type="plane_rigid_body_acceleration",
        knowns={
            "rBAx": q("rBAx", 2.0, "m"),
            "rBAy": q("rBAy", 0.0, "m"),
            "omega": q("omega", 3.0, "rad/s"),
            "alpha": q("alpha", 1.0, "rad/s^2"),
        },
    )

    result = PlaneRigidBodyAccelerationSolver().solve(problem)

    assert not result.ok
    assert any("A점 가속도" in error for error in result.verification.errors)


def test_fixed_rigid_acceleration_allows_magnitude_only():
    problem = CanonicalProblem(
        system_type="plane_rigid_body_acceleration",
        knowns={
            "aA": q("aA", 0.0, "m/s^2"),
            "r": q("r", 2.0, "m"),
            "omega": q("omega", 3.0, "rad/s"),
            "alpha": q("alpha", 4.0, "rad/s^2"),
        },
    )

    result = PlaneRigidBodyAccelerationSolver().solve(problem)

    expected = math.hypot(8.0, 18.0)
    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, expected, rel_tol=1e-6)
    assert "a_Bx" not in {item.symbol for item in result.answers}


def test_zero_collision_answer_is_not_treated_as_missing():
    problem = CanonicalProblem(
        system_type="collision_1d",
        raw_text="완전비탄성 충돌",
        knowns={
            "m1": q("m1", 1.0, "kg"),
            "m2": q("m2", 1.0, "kg"),
            "v1": q("v1", 1.0, "m/s"),
            "v2": q("v2", -1.0, "m/s"),
        },
    )

    checks = _collision(problem, {"v_f": 0.0})

    assert len(checks) == 1
    assert checks[0].passed


def test_work_energy_residual_includes_cosine_angle():
    problem = CanonicalProblem(
        system_type="work_energy_speed",
        raw_text="정지 상태에서 힘을 60도로 가한다.",
        knowns={
            "m": q("m", 2.0, "kg"),
            "F": q("F", 10.0, "N"),
            "s": q("s", 3.0, "m"),
            "theta": q("theta", 60.0, "deg"),
            "v0": q("v0", 0.0, "m/s"),
        },
    )

    checks = _work_energy(problem, {"v_f": math.sqrt(15.0)})

    assert len(checks) == 1
    assert checks[0].passed


def test_answer_validator_knows_extended_output_symbols():
    answer = Answer(numeric=2.0, unit="N", display="f_k = 2.000 N")
    answers = [
        AnswerItem("운동마찰력", "f_k", 2.0, "N", "f_k = 2.000 N", "primary"),
        AnswerItem("탄성 퍼텐셜 에너지", "E", 3.0, "J", "E = 3.000 J", "primary"),
        AnswerItem("주기", "T", 4.0, "s", "T = 4.000 s", "primary"),
        AnswerItem("충격량", "J", 5.0, "N*s", "J = 5.000 N*s", "primary"),
    ]

    report = validate_answer_consistency(
        ok=True,
        answer=answer,
        answers=answers,
        requested_outputs=["friction_force", "elastic_energy", "period", "impulse"],
    )

    assert report.passed, report.errors
