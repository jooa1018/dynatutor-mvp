import math

from engine.extraction.extractor import extract_problem
from engine.model_builder import build_physical_model
from engine.physics_core.friction import (
    decide_incline_static,
    decide_incline_hanging_static,
    decide_table_hanging_static,
)
from engine.physics_core.string_topology import topology_for_system
from engine.services import diagnose_problem, solve_problem


def test_incline_static_friction_holds_before_newton_solve():
    out = solve_problem("정지마찰계수 0.8인 30도 경사면 위 블록이 있다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "incline_with_friction"
    assert out.answer.numeric == 0
    assert "a = 0.000" in out.answer.display
    assert any("정지마찰 판정" in step.title for step in out.steps)


def test_table_hanging_static_friction_holds():
    out = solve_problem("수평면 위 m1=5kg와 매달린 m2=1kg가 도르래와 줄로 연결되어 있고 정지마찰계수는 0.3이다. 가속도는?")
    assert out.ok
    assert out.answer.numeric == 0
    assert "f_s" in out.answer.display
    assert any("먼저 움직이는지 확인" in step.title for step in out.steps)


def test_incline_hanging_static_friction_holds():
    out = solve_problem("경사면 위 m1=5kg와 매달린 m2=2kg가 도르래와 줄로 연결되어 있다. 경사각 30도, 정지마찰계수는 0.2이다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_incline_hanging"
    assert out.answer.numeric == 0
    assert "T =" in out.answer.display


def test_static_friction_decision_utilities():
    incline = decide_incline_static(math.radians(30), 0.8, g=9.81)
    assert incline.holds_static
    table = decide_table_hanging_static(5, 1, 0.3)
    assert table.holds_static
    incline_hanging = decide_incline_hanging_static(5, 2, math.radians(30), 0.2)
    assert incline_hanging.holds_static


def test_string_topology_for_atwood_and_massive_pulley():
    atwood = topology_for_system("pulley_atwood")
    assert atwood is not None
    assert atwood.kind == "fixed_massless_atwood"
    assert "T_left = T_right = T" in atwood.tension_constraints

    massive = topology_for_system("massive_pulley_atwood")
    assert massive is not None
    assert "T1 != T2 generally" in massive.tension_constraints
    assert "a = alpha*R" in massive.rotation_constraints


def test_physical_model_exposes_phase16_friction_and_topology():
    c = extract_problem("수평면 위 m1=5kg와 매달린 m2=1kg가 도르래와 줄로 연결되어 있고 정지마찰계수는 0.3이다. 가속도는?")
    model = build_physical_model(c)
    assert model.string_topology is not None
    assert model.string_topology["kind"] == "fixed_massless_table_hanging"
    assert model.friction_decisions
    assert model.friction_decisions[0]["status"] == "static_hold"

    d = diagnose_problem(c.raw_text)
    assert d.physical_model["friction_decisions"][0]["status"] == "static_hold"
    assert d.physical_model["string_topology"]["kind"] == "fixed_massless_table_hanging"


def test_static_friction_slips_then_uses_kinetic_motion_path():
    out = solve_problem("정지마찰계수 0.2, 운동마찰계수 0.1인 30도 경사면 위 블록의 가속도는?")
    assert out.ok
    expected = 9.81 * (math.sin(math.radians(30)) - 0.1 * math.cos(math.radians(30)))
    assert math.isclose(out.answer.numeric, expected, rel_tol=1e-4)
