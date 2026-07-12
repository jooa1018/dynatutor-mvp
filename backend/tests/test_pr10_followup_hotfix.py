from __future__ import annotations

import logging
import math

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routes import records as records_route
from app.routes import solve as solve_route
from app.schemas.problem import ProblemRequest
from app.schemas.records import RecordCreate
from engine.canonical.adapter import attach_canonical_v2
from engine.errors import PhysicsDomainError
from engine.extraction.extractor import extract_problem
from engine.models import AnswerItem, CanonicalProblem, Quantity
from engine.physics_core.answer_validators import validate_answer_consistency
from engine.physics_core.coordinate_parser import parse_coordinate_data_from_text
from engine.routing.clarify import (
    ClarifyPatchError,
    apply_clarify_patch,
    build_clarification,
    validate_clarify_patch,
)
from engine.services import _answer_item_model, _route_decision_model, solve_problem
from engine.solvers.registry import SolverRegistry
from engine.solvers.rigid_body_2d.acceleration import PlaneRigidBodyAccelerationSolver
from engine.verification.residuals import _projectile
from engine.storage import notebook


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def _mixed_problem(*, primary: str, requested: str) -> CanonicalProblem:
    subtype = "no_friction" if primary == "particle_on_incline" else None
    problem = CanonicalProblem(
        system_type=primary,
        subtype=subtype,
        raw_text=(
            "30도 경사면 위 질량 2kg 블록이 용수철 상수 100N/m인 "
            "스프링을 0.1m 압축했다."
        ),
        knowns={
            "theta": q("theta", 30.0, "deg"),
            "m": q("m", 2.0, "kg"),
            "k": q("k", 100.0, "N/m"),
            "x": q("x", 0.1, "m"),
            "g": q("g", 9.81, "m/s^2"),
        },
        flags={"spring": True, "incline": True, "no_friction": True},
        requested_outputs=[requested],
        unknowns=[requested],
    )
    attach_canonical_v2(problem)
    return problem


def test_user_confirmed_interpretation_is_promoted():
    problem = _mixed_problem(
        primary="particle_on_incline",
        requested="final_velocity",
    )
    apply_clarify_patch(problem, {"system_type": "spring_energy"})

    decision = SolverRegistry().route(problem)
    confirmed = next(
        candidate
        for candidate in decision.candidates
        if candidate.source_system_type == "spring_energy"
    )

    assert confirmed.selection_eligible is True
    assert confirmed.interpretation_score == 1.0
    assert confirmed.interpretation_provenance == "user_confirmed"
    assert "user_confirmed" in confirmed.risk_flags
    assert "user-confirmed interpretation" in confirmed.evidence


def test_user_confirmed_spring_choice_beats_incline_candidate():
    problem = _mixed_problem(
        primary="particle_on_incline",
        requested="final_velocity",
    )
    apply_clarify_patch(problem, {"system_type": "spring_energy"})

    decision = SolverRegistry().route(problem)

    assert decision.status == "select"
    assert decision.selected_solver_id == "spring_energy_speed"
    assert all(
        not candidate.selection_eligible
        for candidate in decision.candidates
        if candidate.source_system_type == "particle_on_incline"
    )


def test_user_confirmed_incline_choice_beats_spring_candidate():
    problem = _mixed_problem(primary="spring_energy", requested="acceleration")
    apply_clarify_patch(
        problem,
        {"system_type": "particle_on_incline", "subtype": "no_friction"},
    )

    decision = SolverRegistry().route(problem)

    assert decision.status == "select"
    assert decision.selected_solver_id == "incline_no_friction"
    assert all(
        not candidate.selection_eligible
        for candidate in decision.candidates
        if candidate.source_system_type == "spring_energy"
    )


def test_user_confirmed_model_with_missing_inputs_returns_clarify():
    problem = _mixed_problem(
        primary="particle_on_incline",
        requested="final_velocity",
    )
    problem.knowns.pop("m")
    problem.knowns.pop("x")
    apply_clarify_patch(problem, {"system_type": "spring_energy"})

    decision = SolverRegistry().route(problem)

    assert decision.status == "clarify"
    assert decision.selected_solver_id is None
    assert any(
        candidate.selection_eligible and candidate.missing_requirements
        for candidate in decision.candidates
    )


def test_user_confirmed_unsupported_model_does_not_fallback():
    problem = _mixed_problem(primary="spring_energy", requested="final_velocity")
    problem.system_type = "rigid_body_3d"
    problem.subtype = None
    problem.flags["_clarify_model_chosen"] = True

    decision = SolverRegistry().route(problem)

    assert decision.status == "unsupported"
    assert decision.selected_solver_id is None
    assert all(not candidate.selection_eligible for candidate in decision.candidates)


def test_route_decision_exposes_user_confirmation_evidence():
    problem = _mixed_problem(
        primary="particle_on_incline",
        requested="final_velocity",
    )
    apply_clarify_patch(problem, {"system_type": "spring_energy"})

    model = _route_decision_model(SolverRegistry().route(problem))
    confirmed = next(
        candidate
        for candidate in model.candidates
        if candidate.source_system_type == "spring_energy"
    )

    assert confirmed.interpretation_provenance == "user_confirmed"
    assert confirmed.selection_eligible is True
    assert "user-confirmed interpretation" in confirmed.evidence


def _rigid_missing_reference(system_type: str) -> CanonicalProblem:
    velocity = system_type.endswith("velocity")
    knowns = {
        "omega": q("omega", 2.0, "rad/s"),
    }
    if not velocity:
        knowns["alpha"] = q("alpha", 1.0, "rad/s^2")
    return CanonicalProblem(
        system_type=system_type,
        raw_text="평면 강체에서 B점은 A점으로부터 오른쪽 1m에 있다.",
        knowns=knowns,
        coordinate_data={
            "rBAx": 1.0,
            "rBAy": 0.0,
            "omega_sign": 1.0,
            "alpha_sign": 1.0,
        },
        requested_outputs=["final_velocity" if velocity else "acceleration"],
    )


def _vector_option(problem: CanonicalProblem):
    clarification = build_clarification(problem)
    assert clarification is not None
    return next(option for option in clarification.options if option.input_fields)


def test_rigid_velocity_vector_clarification_schema():
    option = _vector_option(_rigid_missing_reference("plane_rigid_body_velocity"))

    assert option.patch == {"input_contract": "rigid_vA_vector"}
    assert [field.symbol for field in option.input_fields] == ["vAx", "vAy"]
    assert [field.unit for field in option.input_fields] == ["m/s", "m/s"]
    assert option.needs_value is None


def test_rigid_acceleration_vector_clarification_schema():
    option = _vector_option(
        _rigid_missing_reference("plane_rigid_body_acceleration")
    )

    assert option.patch == {"input_contract": "rigid_aA_vector"}
    assert [field.symbol for field in option.input_fields] == ["aAx", "aAy"]
    assert [field.unit for field in option.input_fields] == ["m/s^2", "m/s^2"]


def test_multi_value_clarify_patch_accepts_two_finite_values():
    problem = _rigid_missing_reference("plane_rigid_body_velocity")
    patch = {
        "input_contract": "rigid_vA_vector",
        "set_knowns": [
            {"symbol": "vAx", "value": 3.0, "unit": "m/s"},
            {"symbol": "vAy", "value": -2.0, "unit": "m/s"},
        ],
    }

    validate_clarify_patch(problem, patch)


def test_multi_value_clarify_patch_rejects_missing_component():
    problem = _rigid_missing_reference("plane_rigid_body_velocity")
    patch = {
        "input_contract": "rigid_vA_vector",
        "set_knowns": [
            {"symbol": "vAx", "value": 3.0, "unit": "m/s"},
        ],
    }

    with pytest.raises(ClarifyPatchError):
        validate_clarify_patch(problem, patch)


def test_multi_value_clarify_patch_rejects_invalid_unit():
    problem = _rigid_missing_reference("plane_rigid_body_acceleration")
    patch = {
        "input_contract": "rigid_aA_vector",
        "set_knowns": [
            {"symbol": "aAx", "value": 1.0, "unit": "m/s"},
            {"symbol": "aAy", "value": 2.0, "unit": "m/s^2"},
        ],
    }

    with pytest.raises(ClarifyPatchError):
        validate_clarify_patch(problem, patch)


def test_multi_value_clarify_patch_updates_canonical_knowns():
    problem = _rigid_missing_reference("plane_rigid_body_velocity")
    patch = {
        "input_contract": "rigid_vA_vector",
        "set_knowns": [
            {"symbol": "vAx", "value": 3.0, "unit": "m/s"},
            {"symbol": "vAy", "value": -2.0, "unit": "m/s"},
        ],
    }

    apply_clarify_patch(problem, patch)

    assert problem.knowns["vAx"].value == 3.0
    assert problem.knowns["vAy"].value == -2.0
    assert problem.knowns["vAx"].provenance_hint == "user_confirmation"


def _projectile_problem() -> CanonicalProblem:
    return CanonicalProblem(
        system_type="projectile_motion",
        raw_text=(
            "지면에서 초속도 20m/s, 발사각 120도로 발사해 "
            "같은 높이에 착지한다. 사거리는?"
        ),
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


def test_rightward_projectile_range_passes_full_gate():
    response = solve_problem(
        "지면에서 초속도 20m/s, 발사각 60도로 발사해 "
        "같은 높이에 착지한다. 사거리는?"
    )

    assert response.ok is True
    assert response.verification.passed is True
    assert response.answer is not None
    assert response.answers


def test_leftward_projectile_range_passes_full_gate():
    response = solve_problem(_projectile_problem().raw_text)

    assert response.ok is True
    assert response.verification.passed is True
    assert response.answer is not None
    assert response.answers


def test_leftward_projectile_range_is_positive():
    response = solve_problem(_projectile_problem().raw_text)
    range_item = next(item for item in response.answers if item.symbol == "R")

    assert range_item.numeric is not None and range_item.numeric > 0
    assert "왼쪽" in range_item.display


def test_leftward_projectile_signed_displacement_is_negative():
    response = solve_problem(_projectile_problem().raw_text)
    displacement = next(
        item for item in response.answers if item.symbol == "delta_x"
    )

    assert displacement.numeric is not None and displacement.numeric < 0


def test_projectile_range_residual_uses_magnitude():
    problem = _projectile_problem()
    t = 2 * 20 * math.sin(math.radians(120)) / 9.81
    vx = 20 * math.cos(math.radians(120))
    checks = _projectile(
        problem,
        {"t": t, "R": abs(vx * t), "delta_x": vx * t},
    )

    range_check = next(check for check in checks if "사거리 크기" in check.name)
    assert range_check.passed


def test_projectile_delta_x_residual_preserves_sign():
    problem = _projectile_problem()
    t = 2 * 20 * math.sin(math.radians(120)) / 9.81
    vx = 20 * math.cos(math.radians(120))
    checks = _projectile(problem, {"t": t, "delta_x": vx * t})

    displacement_check = next(
        check for check in checks if "수평 변위" in check.name
    )
    assert displacement_check.passed


def test_range_does_not_infer_time_from_unsigned_distance():
    checks = _projectile(_projectile_problem(), {"R": 10.0})

    assert not any("y(t)" in check.name for check in checks)


def test_omega_clockwise_alpha_counterclockwise():
    parsed = parse_coordinate_data_from_text(
        "omega는 시계방향이고 alpha는 반시계방향이다."
    )

    assert parsed.values["omega_sign"] == -1.0
    assert parsed.values["alpha_sign"] == 1.0


def test_omega_counterclockwise_alpha_clockwise():
    parsed = parse_coordinate_data_from_text(
        "ω는 반시계방향이며 α는 시계방향이다."
    )

    assert parsed.values["omega_sign"] == 1.0
    assert parsed.values["alpha_sign"] == -1.0


def test_direction_before_angular_quantity():
    parsed = parse_coordinate_data_from_text("시계방향 각속도 omega=2rad/s")

    assert parsed.values["omega_sign"] == -1.0


def test_direction_after_angular_quantity():
    parsed = parse_coordinate_data_from_text("각가속도 α=2rad/s²는 반시계방향")

    assert parsed.values["alpha_sign"] == 1.0


def test_clause_boundary_prevents_direction_leakage():
    parsed = parse_coordinate_data_from_text(
        "omega는 시계방향이고 alpha=2rad/s²이다."
    )

    assert parsed.values["omega_sign"] == -1.0
    assert "alpha_sign" not in parsed.values


def test_english_omega_alpha_opposite_directions():
    parsed = parse_coordinate_data_from_text(
        "omega is clockwise and alpha is counterclockwise"
    )

    assert parsed.values["omega_sign"] == -1.0
    assert parsed.values["alpha_sign"] == 1.0


def test_ambiguous_same_clause_does_not_guess():
    parsed = parse_coordinate_data_from_text(
        "omega may be clockwise or counterclockwise"
    )

    assert "omega_sign" not in parsed.values
    assert "angular_sign" not in parsed.values


def test_rigid_body_components_use_independent_omega_alpha_signs():
    problem = CanonicalProblem(
        system_type="plane_rigid_body_acceleration",
        raw_text="omega는 시계방향이고 alpha는 반시계방향이다.",
        knowns={
            "omega": q("omega", 2.0, "rad/s"),
            "alpha": q("alpha", 1.0, "rad/s^2"),
        },
        coordinate_data={
            "rBAx": 1.0,
            "rBAy": 0.0,
            "aAx": 0.0,
            "aAy": 0.0,
            "omega_sign": -1.0,
            "alpha_sign": 1.0,
        },
        requested_outputs=["acceleration"],
    )

    result = PlaneRigidBodyAccelerationSolver().solve(problem)
    by_symbol = {item.symbol: item.numeric for item in result.answers}

    assert result.ok
    assert math.isclose(by_symbol["a_Bx"], -4.0)
    assert math.isclose(by_symbol["a_By"], 1.0)


def _answer(label: str, symbol: str, output_key: str | None) -> AnswerItem:
    return AnswerItem(
        label=label,
        symbol=symbol,
        numeric=1.0,
        unit="s" if output_key == "period" else "N",
        display=f"{symbol} = 1",
        output_key=output_key,
    )


def _report(requested: str, item: AnswerItem):
    return validate_answer_consistency(
        ok=True,
        answer=None,
        answers=[item],
        requested_outputs=[requested],
    )


def test_period_is_not_satisfied_by_tension_symbol():
    assert not _report("period", _answer("장력", "T", "tension")).passed


def test_tension_is_not_satisfied_by_period_symbol():
    assert not _report("tension", _answer("주기", "T", "period")).passed


def test_frequency_is_not_satisfied_by_friction_symbol():
    assert not _report(
        "frequency",
        _answer("마찰력", "f", "friction_force"),
    ).passed


def test_friction_is_not_satisfied_by_frequency_symbol():
    assert not _report(
        "friction_force",
        _answer("진동수", "f", "frequency"),
    ).passed


def test_matching_output_key_passes():
    assert _report("period", _answer("주기", "T", "period")).passed


def test_missing_output_key_fails_closed_for_ambiguous_symbol():
    assert not _report("period", _answer("주기", "T", None)).passed


def test_legacy_unambiguous_symbol_remains_compatible():
    item = AnswerItem("알짜힘", "F", 1.0, "N", "F = 1 N")

    assert item.output_key == "force"
    assert _report("force", item).passed


def test_answer_item_output_key_serializes_in_api():
    model = _answer_item_model(_answer("장력", "T", "tension"))

    assert model.output_key == "tension"
    assert model.model_dump()["output_key"] == "tension"


def _verified_raw(display: str = "v = 3.000 m/s") -> dict:
    return {
        "ok": True,
        "verification": {"passed": True},
        "answer": {"display": display},
        "answers": [{"display": display}],
    }


def test_engine_record_requires_raw_result():
    with pytest.raises(HTTPException):
        records_route.create_record(
            RecordCreate(problem_text="테스트 문제", source="engine")
        )


def test_engine_record_requires_ok_true():
    with pytest.raises(HTTPException):
        records_route.create_record(
            RecordCreate(
                problem_text="테스트 문제",
                source="engine",
                raw_result={"ok": False, "verification": {"passed": True}},
            )
        )


def test_engine_record_requires_verification_passed():
    with pytest.raises(HTTPException):
        records_route.create_record(
            RecordCreate(
                problem_text="테스트 문제",
                source="engine",
                raw_result={"ok": True, "verification": {"passed": False}},
            )
        )


def test_manual_record_can_be_saved_without_raw_result(monkeypatch, tmp_path):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")

    record = records_route.create_record(
        RecordCreate(
            problem_text="사용자가 직접 적은 문제",
            answer_display="직접 계산: 3 m/s",
            source="manual",
        )
    )

    assert record.source == "manual"
    assert record.verified is False


def test_manual_record_is_marked_unverified(monkeypatch, tmp_path):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")

    record = notebook.add_record(
        {
            "problem_text": "수동 기록",
            "source": "manual",
            "verified": True,
        }
    )

    assert record["verified"] is False


def test_imported_record_cannot_forge_verified_status(monkeypatch, tmp_path):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")

    notebook.import_records(
        {
            "records": [
                {
                    "problem_text": "과거 데이터",
                    "source": "engine",
                    "verified": True,
                    "raw_result": _verified_raw(),
                }
            ]
        }
    )
    record = notebook.list_records()[0]

    assert record["source"] == "import"
    assert record["verified"] is False


def test_verified_engine_record_is_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(notebook, "DB_PATH", tmp_path / "records.sqlite")
    raw = _verified_raw()

    record = records_route.create_record(
        RecordCreate(
            problem_text="검증된 엔진 문제",
            source="engine",
            raw_result=raw,
            answer_display="v = 3.000 m/s",
        )
    )

    assert record.source == "engine"
    assert record.verified is True


def _solve_client() -> TestClient:
    app = FastAPI()
    app.include_router(solve_route.router, prefix="/solve")
    return TestClient(app)


def test_explicit_physics_input_error_returns_422(monkeypatch):
    def fail(*args, **kwargs):
        raise PhysicsDomainError("질량은 0보다 커야 합니다.")

    monkeypatch.setattr(solve_route, "solve_problem", fail)
    response = _solve_client().post("/solve", json={"problem_text": "질량 오류"})

    assert response.status_code == 422
    assert "질량" in response.json()["detail"]


def test_invalid_clarify_patch_returns_400_or_422_as_contract(monkeypatch):
    def fail(*args, **kwargs):
        raise ClarifyPatchError("잘못된 clarification patch")

    monkeypatch.setattr(solve_route, "solve_problem", fail)
    response = _solve_client().post("/solve", json={"problem_text": "패치 오류"})

    assert response.status_code == 400


def test_unexpected_value_error_returns_500_with_trace_id(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("secret-internal-value")

    monkeypatch.setattr(solve_route, "solve_problem", fail)
    response = _solve_client().post("/solve", json={"problem_text": "내부 오류"})

    assert response.status_code == 500
    assert "trace_id=" in response.json()["detail"]
    assert "secret-internal-value" not in response.text


def test_unexpected_index_error_returns_500_with_trace_id(monkeypatch):
    def fail(*args, **kwargs):
        raise IndexError("secret-internal-index")

    monkeypatch.setattr(solve_route, "solve_problem", fail)
    response = _solve_client().post("/solve", json={"problem_text": "내부 오류"})

    assert response.status_code == 500
    assert "trace_id=" in response.json()["detail"]
    assert "secret-internal-index" not in response.text


def test_internal_error_is_logged(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise RuntimeError("logged sentinel")

    monkeypatch.setattr(solve_route, "solve_problem", fail)
    with caplog.at_level(logging.ERROR):
        response = _solve_client().post(
            "/solve",
            json={"problem_text": "로그 오류"},
        )

    assert response.status_code == 500
    assert "unexpected solve failure trace_id=" in caplog.text
    assert "logged sentinel" in caplog.text


def test_traceback_is_not_exposed_to_client(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("private traceback sentinel")

    monkeypatch.setattr(solve_route, "solve_problem", fail)
    response = _solve_client().post("/solve", json={"problem_text": "보안 오류"})

    assert response.status_code == 500
    assert "Traceback" not in response.text
    assert "private traceback sentinel" not in response.text


def test_ambiguous_clarify_patch_reroutes_to_user_choice():
    text = "도르래에 연결된 m1=2kg, m2=3kg 두 물체의 가속도는?"
    initial = solve_problem(text)

    assert initial.clarification is not None
    assert initial.route_decision is not None
    assert initial.route_decision.status == "clarify"

    response = solve_problem(
        text,
        clarify_patch={"system_type": "pulley_atwood"},
    )

    assert response.route_decision is not None
    assert response.route_decision.selected_solver_id == "pulley_atwood"
    assert response.diagnosis.selected_solver == "pulley_atwood"
    assert response.ok is True
    assert response.verification.passed is True


def test_rigid_vector_clarification_round_trip_solves():
    text = (
        "평면 강체에서 rBA=(1,0)m이다. "
        "omega=2rad/s이며 반시계방향이다. B점 속도를 구하라."
    )
    initial = solve_problem(text)
    assert initial.clarification is not None
    option = next(
        option for option in initial.clarification.options if option.input_fields
    )
    patch = {
        **option.patch,
        "set_knowns": [
            {"symbol": "vAx", "value": 0.0, "unit": "m/s"},
            {"symbol": "vAy", "value": 0.0, "unit": "m/s"},
        ],
    }

    response = solve_problem(text, clarify_patch=patch)

    assert response.ok is True, response.model_dump_json()
    assert response.verification.passed is True, response.model_dump_json()
    assert response.diagnosis.selected_solver == "plane_rigid_body_velocity"
    assert response.answers
