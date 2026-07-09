import math

from engine.extraction.extractor import extract_problem
from engine.physics_core.coordinate_parser import (
    direction_to_angle_deg,
    parse_coordinate_data_from_text,
    signed_angular_direction,
)
from engine.services import diagnose_problem, solve_problem


def test_direction_parser_cardinal_and_angular_sign():
    assert direction_to_angle_deg("오른쪽") == 0.0
    assert direction_to_angle_deg("위쪽") == 90.0
    assert signed_angular_direction("반시계방향 4rad/s") == 1
    assert signed_angular_direction("시계방향 4rad/s") == -1


def test_parse_rba_from_korean_direction_phrase():
    parsed = parse_coordinate_data_from_text("B는 A에서 오른쪽으로 0.5m 떨어져 있다.").to_dict()
    assert math.isclose(parsed["rBAx"], 0.5, abs_tol=1e-9)
    assert math.isclose(parsed["rBAy"], 0.0, abs_tol=1e-9)


def test_fixed_point_counterclockwise_velocity_vector():
    out = solve_problem("평면강체에서 A점은 고정되어 있고 B는 A에서 오른쪽으로 0.5m 떨어져 있다. 각속도는 반시계방향 4rad/s이다. B점 속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "plane_rigid_body_velocity"
    assert "v_B = (0.000, 2.000)" in out.answer.display
    assert math.isclose(out.answer.numeric, 2.0, rel_tol=1e-9)


def test_fixed_point_clockwise_velocity_vector_sign():
    out = solve_problem("평면강체에서 A점은 고정되어 있고 B는 A에서 오른쪽으로 0.5m 떨어져 있다. 각속도는 시계방향 4rad/s이다. B점 속도는?")
    assert out.ok
    assert "v_B = (0.000, -2.000)" in out.answer.display


def test_vA_direction_and_rBA_direction_are_not_mixed():
    out = solve_problem("평면강체에서 A점 속도는 오른쪽 3m/s이고 B는 A에서 위쪽으로 0.5m 떨어져 있다. 각속도는 반시계방향 4rad/s이다. B점 속도는?")
    assert out.ok
    # v_A=(3,0), omega x r=( -2, 0 ), so v_B=(1,0)
    assert "v_B = (1.000, 0.000)" in out.answer.display
    assert math.isclose(out.answer.numeric, 1.0, rel_tol=1e-9)


def test_rigid_body_acceleration_uses_vector_components_and_sign():
    out = solve_problem("평면강체 가속도 문제에서 A점 가속도는 오른쪽 1m/s2이고 B는 A에서 오른쪽으로 0.6m 떨어져 있다. 각속도는 반시계방향 4rad/s, 각가속도는 반시계방향 3rad/s2이다. B점 가속도는?")
    assert out.ok
    # a_A=(1,0), alpha×r=(0,1.8), omega×omega×r=(-9.6,0)
    assert "a_B = (-8.600, 1.800)" in out.answer.display
    assert math.isclose(out.answer.numeric, math.hypot(-8.6, 1.8), rel_tol=1e-3)


def test_rigid_body_without_fixed_point_or_vA_still_unsupported():
    out = solve_problem("평면강체에서 A와 B 사이 거리는 1m, 각속도는 2rad/s이다. B점 속도는?")
    assert not out.ok
    assert "A점 속도" in (out.unsupported_reason or "") or any("A점 속도" in e for e in out.verification.errors + out.diagnosis.canonical.missing_info)


def test_diagnosis_coordinate_notes_exposed():
    d = diagnose_problem("평면강체에서 A점은 고정되어 있고 B는 A에서 오른쪽으로 0.5m 떨어져 있다. 각속도는 시계방향 4rad/s이다. B점 속도는?")
    notes = d.physical_model["coordinates"]["notes"]
    assert any("r_B/A=(0.5, 0)" in n for n in notes)
    assert d.canonical.coordinate_data["angular_sign"] == -1.0
