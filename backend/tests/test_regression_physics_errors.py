import math
from engine.services import solve_problem


def test_atwood_not_table_hanging():
    out = solve_problem("m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_atwood"
    assert math.isclose(out.answer.numeric, 1.962, rel_tol=2e-3)


def test_table_hanging_with_friction():
    out = solve_problem("수평면 위 m1=3kg와 매달린 m2=2kg가 도르래와 줄로 연결되어 있고 수평면 마찰계수는 0.2이다. 가속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "pulley_table_hanging"
    assert math.isclose(out.answer.numeric, 2.7468, rel_tol=2e-3)


def test_friction_work_negative():
    out = solve_problem("마찰력 10N이 이동 방향 반대로 3m 작용했다. 한 일은?")
    assert out.ok
    assert out.diagnosis.selected_solver == "constant_force_work"
    assert math.isclose(out.answer.numeric, -30.0, rel_tol=1e-5)


def test_force_at_angle_work():
    out = solve_problem("힘 10N이 이동 방향과 60도로 3m 작용했다. 한 일은?")
    assert out.ok
    assert math.isclose(out.answer.numeric, 15.0, rel_tol=1e-5)


def test_perpendicular_work_zero():
    out = solve_problem("힘 10N이 이동 방향에 수직으로 3m 작용했다. 한 일은?")
    assert out.ok
    assert abs(out.answer.numeric) < 1e-9


def test_solid_sphere_rolling_not_disk():
    out = solve_problem("정지 상태에서 속이 찬 구가 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?")
    assert out.ok
    assert out.diagnosis.selected_solver in {"pure_rolling_energy", "rolling_energy_general"}
    expected = math.sqrt(2 * 9.81 * 1 / (1 + 2/5))
    assert math.isclose(out.answer.numeric, expected, rel_tol=1e-5)


def test_projectile_from_cliff():
    out = solve_problem("높이 20m 절벽에서 초속도 10m/s, 발사각 30도로 던졌다. 지면까지 걸리는 시간은?")
    assert out.ok
    assert out.diagnosis.selected_solver == "projectile_motion"
    # 20 + 5t - 4.905t^2 = 0
    expected = (5 + math.sqrt(25 + 4 * 4.905 * 20)) / (2 * 4.905)
    assert math.isclose(out.answer.numeric, expected, rel_tol=1e-3)



def test_vertical_circle_bottom_speed_is_current_state():
    out = solve_problem(
        "질량 1kg 물체가 수직 원운동 최저점에서 반지름 2m, "
        "속도 8m/s로 움직일 때 줄의 장력을 구하라."
    )
    assert out.ok
    assert out.diagnosis.selected_solver == "vertical_circle"
    assert "v" in out.diagnosis.canonical.knowns
    assert "v0" not in out.diagnosis.canonical.knowns
    assert math.isclose(out.answer.numeric, 41.81, rel_tol=1e-5)
