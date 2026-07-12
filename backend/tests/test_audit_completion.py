from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routes import records as records_route
from app.schemas.problem import ProblemRequest
from app.schemas.records import RecordCreate
from engine.extraction.extractor import extract_problem
from engine.models import Answer, AnswerItem, CanonicalProblem, Quantity
from engine.physics_core import symbols as S
from engine.physics_core.answer_validators import validate_answer_consistency
from engine.solvers.advanced_dynamics import CoriolisRelativeMotionSolver
from engine.solvers.advanced_motion import PolarKinematicsSolver
from engine.solvers.collision import Collision1DSolver
from engine.solvers.incline import InclineWithFrictionSolver
from engine.solvers.newton.single_particle import SingleParticleNewtonSolver
from engine.solvers.projectile import ProjectileMotionSolver
from engine.solvers.pulley.atwood import AtwoodPulleySolver
from engine.solvers.rigid_body_2d.relative_motion import RelativeAccelerationTranslationSolver
from engine.solvers.rolling.rolling_energy import PureRollingEnergySolver
from engine.verification.dimensions import check_answer_dimension
from engine.verification.gate import apply_result_gate
from engine.verification.plausibility import check_knowns
from engine.verification.residuals import _collision, run_residual_checks


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def test_newton_honors_requested_force_before_given_acceleration_phrase():
    problem = CanonicalProblem(
        system_type="single_particle_newton",
        raw_text="가속도는 2 m/s²이고 질량은 3 kg이다. 필요한 힘을 구하라.",
        knowns={"a": q("a", 2.0, "m/s^2"), "m": q("m", 3.0, "kg")},
        requested_outputs=["force"],
        unknowns=["force"],
    )

    result = SingleParticleNewtonSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 6.0)


def test_newton_rejects_nonpositive_computed_mass():
    problem = CanonicalProblem(
        system_type="single_particle_newton",
        raw_text="알짜힘 -10 N, 가속도 2 m/s²일 때 질량은?",
        knowns={"F": q("F", -10.0, "N"), "a": q("a", 2.0, "m/s^2")},
        requested_outputs=["mass"],
        unknowns=["mass"],
    )

    result = SingleParticleNewtonSolver().solve(problem)

    assert not result.ok
    assert any("질량" in error for error in result.verification.errors)


def test_acceleration_symbol_is_real_not_positive():
    assert S.a.is_real is True
    assert S.a.is_positive is not True


def test_atwood_preserves_signed_coordinate_component():
    problem = CanonicalProblem(
        system_type="pulley_atwood",
        raw_text="m1=5kg, m2=2kg인 Atwood 계. 가속도와 장력은?",
        knowns={
            "m1": q("m1", 5.0, "kg"),
            "m2": q("m2", 2.0, "kg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration", "tension"],
    )

    result = AtwoodPulleySolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert result.answer.numeric < 0
    assert math.isclose(result.answer.numeric, -3 * 9.81 / 7, rel_tol=1e-5)


def test_incline_allows_negative_downslope_acceleration_component():
    problem = CanonicalProblem(
        system_type="particle_on_incline",
        subtype="with_friction",
        friction_type="kinetic",
        raw_text="10도 경사면 아래로 움직이는 1kg 블록, 운동마찰계수 0.5. 가속도는?",
        knowns={
            "m": q("m", 1.0, "kg"),
            "theta": q("theta", 10.0, "deg"),
            "mu_k": q("mu_k", 0.5, ""),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration"],
    )

    result = InclineWithFrictionSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert result.answer.numeric < 0


def _collision_problem(v1: float = 4.0, v2: float = 0.0, *, e: float | None = 0.5, elastic: bool = False):
    knowns = {
        "m1": q("m1", 2.0, "kg"),
        "m2": q("m2", 3.0, "kg"),
        "v1": q("v1", v1, "m/s"),
        "v2": q("v2", v2, "m/s"),
    }
    if e is not None:
        knowns["e"] = q("e", e, "")
    return CanonicalProblem(
        system_type="collision_1d",
        raw_text="완전탄성 충돌" if elastic else "비탄성 충돌",
        knowns=knowns,
        flags={"elastic": elastic},
        requested_outputs=["post_collision_velocity"],
    )


def test_inelastic_word_does_not_enable_elastic_energy_residual():
    problem = _collision_problem()
    checks = _collision(problem, {"v1'": 1.0, "v2'": 2.0})

    assert len(checks) == 1
    assert "운동량" in checks[0].name


def test_elastic_narrative_conflicting_with_explicit_e_is_rejected():
    result = Collision1DSolver().solve(_collision_problem(e=0.5, elastic=True))

    assert not result.ok
    assert any("모순" in error for error in result.verification.errors)


def test_receding_bodies_are_not_solved_as_collision():
    result = Collision1DSolver().solve(_collision_problem(v1=0.0, v2=4.0))

    assert not result.ok
    assert any("접근" in error for error in result.verification.errors)


def _projectile_text(prefix: str) -> str:
    return f"지면에서 초속도 20m/s, 발사각 60도로 던졌다. {prefix} 10m 높이에 도달하는 시간은?"


def test_projectile_target_height_is_not_launch_height_and_first_root_is_used():
    problem = extract_problem(_projectile_text("처음으로"))

    assert math.isclose(problem.launch_height or 0.0, 0.0)
    assert math.isclose(problem.landing_height or -1.0, 10.0)
    result = ProjectileMotionSolver().solve(problem)
    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 0.727, rel_tol=2e-3)


def test_projectile_multiple_target_events_require_event_choice():
    problem = extract_problem(_projectile_text(""))

    result = ProjectileMotionSolver().solve(problem)

    assert not result.ok
    assert result.unsupported_reason is not None
    assert "처음" in result.unsupported_reason and "다시" in result.unsupported_reason


def test_projectile_range_is_magnitude_with_left_direction():
    problem = CanonicalProblem(
        system_type="projectile_motion",
        raw_text="지면에서 초속도 20m/s, 발사각 120도로 발사해 같은 높이에 착지한다. 사거리는?",
        knowns={
            "v0": q("v0", 20.0, "m/s"),
            "theta": q("theta", 120.0, "deg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        launch_height=0.0,
        landing_height=0.0,
        launch_angle_deg=120.0,
        requested_outputs=["range"],
    )

    result = ProjectileMotionSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert result.answer.numeric >= 0
    assert "왼쪽" in (result.answer.display or "")


def _rolling_problem(raw_text: str, v0: float | None):
    knowns = {
        "h": q("h", 1.0, "m"),
        "g": q("g", 9.81, "m/s^2"),
    }
    if v0 is not None:
        knowns["v0"] = q("v0", v0, "m/s")
    return CanonicalProblem(
        system_type="pure_rolling_energy",
        raw_text=raw_text,
        knowns=knowns,
        body_shape="solid_sphere",
        requested_outputs=["final_velocity"],
    )


def test_rolling_preserves_nonzero_initial_speed():
    result = PureRollingEnergySolver().solve(_rolling_problem("속이 찬 구가 5m/s로 시작해 1m 내려온다.", 5.0))

    assert result.ok
    assert result.answer is not None
    expected = math.sqrt(25.0 + 2 * 9.81 / 1.4)
    assert math.isclose(result.answer.numeric, expected, rel_tol=1e-5)


def test_rolling_requires_initial_speed_or_explicit_rest():
    result = PureRollingEnergySolver().solve(_rolling_problem("속이 찬 구가 1m 내려온다.", None))

    assert not result.ok
    assert any("초기속도" in error for error in result.verification.errors)


def test_polar_acceleration_does_not_default_missing_derivatives_to_zero():
    problem = CanonicalProblem(
        system_type="polar_kinematics",
        raw_text="극좌표에서 r=2m, omega=3rad/s. 가속도는?",
        knowns={"r": q("r", 2.0, "m"), "omega": q("omega", 3.0, "rad/s")},
        requested_outputs=["acceleration"],
        unknowns=["acceleration"],
    )

    result = PolarKinematicsSolver().solve(problem)

    assert not result.ok
    assert any("일정 조건" in error for error in result.verification.errors)


def test_polar_accepts_explicit_constant_radius_and_angular_speed():
    problem = CanonicalProblem(
        system_type="polar_kinematics",
        raw_text="반지름과 각속도가 일정한 원운동에서 r=2m, omega=3rad/s. 가속도는?",
        knowns={"r": q("r", 2.0, "m"), "omega": q("omega", 3.0, "rad/s")},
        requested_outputs=["acceleration"],
        unknowns=["acceleration"],
    )

    result = PolarKinematicsSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 18.0)


def test_coriolis_term_needs_only_omega_and_relative_velocity():
    problem = CanonicalProblem(
        system_type="coriolis_relative_motion",
        raw_text="omega=3rad/s인 회전계에서 v_rel=2m/s이다. 코리올리 가속도는?",
        knowns={"omega": q("omega", 3.0, "rad/s"), "vrel": q("vrel", 2.0, "m/s")},
        requested_outputs=["acceleration"],
    )

    result = CoriolisRelativeMotionSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 12.0)


def test_full_rotating_frame_acceleration_does_not_default_missing_terms():
    problem = CanonicalProblem(
        system_type="coriolis_relative_motion",
        raw_text="omega=3rad/s, v_rel=2m/s인 회전계의 전체 가속도는?",
        knowns={"omega": q("omega", 3.0, "rad/s"), "vrel": q("vrel", 2.0, "m/s")},
        requested_outputs=["acceleration"],
    )

    result = CoriolisRelativeMotionSolver().solve(problem)

    assert not result.ok
    assert result.unsupported_reason is not None


def test_relative_acceleration_requires_direction():
    problem = CanonicalProblem(
        system_type="relative_acceleration_translation",
        raw_text="aA=1m/s², a_rel=2m/s²일 때 aB는?",
        knowns={"aA": q("aA", 1.0, "m/s^2"), "arel": q("arel", 2.0, "m/s^2")},
        requested_outputs=["acceleration"],
    )

    result = RelativeAccelerationTranslationSolver().solve(problem)

    assert not result.ok
    assert any("방향" in error for error in result.verification.errors)


def test_relative_acceleration_accepts_explicit_same_direction():
    problem = CanonicalProblem(
        system_type="relative_acceleration_translation",
        raw_text="aA=1m/s²가 오른쪽이고 a_rel=2m/s²도 오른쪽일 때 aB는?",
        knowns={"aA": q("aA", 1.0, "m/s^2"), "arel": q("arel", 2.0, "m/s^2")},
        requested_outputs=["acceleration"],
    )

    result = RelativeAccelerationTranslationSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 3.0)


@pytest.mark.parametrize(
    ("knowns", "system_type"),
    [
        ({"m": q("m", 0.0, "kg")}, "single_particle_newton"),
        ({"I": q("I", 0.0, "kg*m^2")}, "fixed_axis_rotation"),
        ({"e": q("e", 1.2, "")}, "collision_1d"),
        ({"mu": q("mu", -0.1, "")}, "flat_curve_friction"),
        ({"R": q("R", -2.0, "m")}, "vertical_circle"),
        ({"t": q("t", -1.0, "s")}, "impulse_momentum"),
        ({"g": q("g", 0.0, "m/s^2")}, "projectile_motion"),
        ({"theta": q("theta", 90.0, "deg")}, "banked_curve_no_friction"),
    ],
)
def test_central_domain_validator_rejects_invalid_inputs(knowns, system_type):
    issues = check_knowns(knowns, system_type=system_type)

    assert any(issue.kind == "error" for issue in issues)


def test_gate_scrubs_answers_when_verification_demotes():
    response = SimpleNamespace(
        ok=True,
        answer=Answer(numeric=42.0, unit="m/s", display="v=42"),
        answers=[AnswerItem("속도", "v", 42.0, "m/s", "v=42", "primary")],
        verification=SimpleNamespace(errors=["bad residual"], passed=True),
        unsupported_reason=None,
    )

    apply_result_gate(response)

    assert response.ok is False
    assert response.answer is None
    assert response.answers == []


def test_problem_request_has_bounded_text_fields():
    with pytest.raises(ValidationError):
        ProblemRequest(problem_text="x" * 10_001)
    with pytest.raises(ValidationError):
        ProblemRequest(problem_text="ok", student_solution="x" * 10_001)


def test_unverified_raw_result_cannot_be_saved():
    request = RecordCreate(
        problem_text="테스트 문제",
        answer_display="v=42",
        raw_result={"ok": False, "verification": {"passed": False}},
    )

    with pytest.raises(HTTPException) as caught:
        records_route.create_record(request)

    assert caught.value.status_code == 422


def test_unknown_dimension_symbol_fails_closed():
    issue, passed = check_answer_dimension("mystery", "m/s")

    assert issue is not None
    assert issue.kind == "error"
    assert passed is None


def test_unknown_requested_output_fails_closed():
    report = validate_answer_consistency(
        ok=True,
        answer=Answer(numeric=1.0, unit="m/s", display="v=1"),
        answers=[AnswerItem("속도", "v", 1.0, "m/s", "v=1", "primary")],
        requested_outputs=["unregistered_output"],
    )

    assert not report.passed
    assert any("미등록 출력" in error for error in report.errors)


@pytest.mark.parametrize(
    "problem,pool",
    [
        (
            CanonicalProblem(
                system_type="single_particle_newton",
                knowns={"m": q("m", 2.0, "kg"), "F": q("F", 6.0, "N")},
            ),
            {"a": 3.0},
        ),
        (
            CanonicalProblem(
                system_type="massive_pulley_atwood",
                knowns={
                    "m1": q("m1", 2.0, "kg"),
                    "m2": q("m2", 5.0, "kg"),
                    "I": q("I", 0.12, "kg*m^2"),
                    "R": q("R", 0.3, "m"),
                    "g": q("g", 9.81, "m/s^2"),
                },
            ),
            {"a": (5 - 2) * 9.81 / (2 + 5 + 0.12 / 0.3**2)},
        ),
        (
            CanonicalProblem(
                system_type="vertical_circle",
                subtype="top",
                knowns={"R": q("R", 1.0, "m"), "g": q("g", 9.81, "m/s^2")},
            ),
            {"v_min": math.sqrt(9.81)},
        ),
        (
            CanonicalProblem(
                system_type="instant_center_velocity",
                knowns={"r": q("r", 2.0, "m"), "omega": q("omega", 3.0, "rad/s")},
            ),
            {"v": 6.0},
        ),
    ],
)
def test_previously_missing_residual_families_are_supported(problem, pool):
    checks, supported = run_residual_checks(problem, pool)

    assert supported
    assert checks
    assert all(check.passed for check in checks)


def test_frontend_hides_and_cannot_save_unverified_answers():
    root = Path(__file__).resolve().parents[2]
    answer_card = (root / "frontend" / "components" / "AnswerCard.tsx").read_text(encoding="utf-8")
    home = (root / "frontend" / "components" / "HomeClient.tsx").read_text(encoding="utf-8")

    assert "if (!isVerified)" in answer_card
    assert "isVerified ? <button" in answer_card
    assert "if (!data.ok || !data.verification?.passed)" in home
