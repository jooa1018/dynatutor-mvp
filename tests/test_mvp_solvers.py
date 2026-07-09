import math
from engine.services import solve_problem, diagnose_problem, feedback_on_solution


def test_frictionless_incline_korean():
    res = solve_problem("질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.")
    assert res.ok
    assert res.diagnosis.selected_solver == "incline_no_friction"
    assert abs(res.answer.numeric - 4.905) < 1e-3
    assert any("f = μN" in x for x in res.diagnosis.not_applicable_equations)


def test_friction_incline():
    res = solve_problem("마찰계수 0.2인 거친 30도 경사면에서 블록의 가속도를 구하라.")
    assert res.ok
    assert res.diagnosis.selected_solver == "incline_with_friction"
    expected = 9.81 * (math.sin(math.radians(30)) - 0.2 * math.cos(math.radians(30)))
    assert abs(res.answer.numeric - expected) < 1e-3


def test_pulley():
    res = solve_problem("마찰 없는 수평면 위 블록 m1=3 kg와 매달린 블록 m2=2 kg가 도르래와 줄로 연결되어 있다. 가속도를 구하라.")
    assert res.ok
    assert res.diagnosis.selected_solver == "pulley_table_hanging"
    assert abs(res.answer.numeric - 3.924) < 1e-3


def test_rolling_energy():
    res = solve_problem("원판이 미끄러지지 않고 경사면을 높이 1.5 m만큼 굴러 내려간다. 속도를 구하라.")
    assert res.ok
    assert res.diagnosis.selected_solver == "pure_rolling_energy"
    assert res.answer.unit == "m/s"
    assert any("v_G = ωR" in x for x in res.diagnosis.applicable_equations)


def test_vertical_circle_top_min_speed():
    res = solve_problem("반지름 2 m인 수직 원운동 최고점에서 최소속도를 구하라.")
    assert res.ok
    assert res.diagnosis.selected_solver == "vertical_circle"
    assert abs(res.answer.numeric - math.sqrt(9.81 * 2)) < 1e-3


def test_missing_info_is_not_forced():
    res = solve_problem("블록이 경사면에서 움직인다. 가속도를 구하라.")
    assert not res.ok
    assert "필수 조건" in ";".join(res.verification.errors) or res.unsupported_reason


def test_feedback_incline_wrong_mg_ma():
    fb = feedback_on_solution("마찰 없는 30도 경사면에서 블록의 가속도를 구하라.", "mg=ma 이므로 a=g")
    assert any("분해" in x for x in fb.missing_points)
