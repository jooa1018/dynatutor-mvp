import math
from engine.models import Quantity
from engine.physics_core.units import Q_, magnitude_si, assert_dimension
from engine.physics_core.vectors import Vec2, rigid_body_velocity, rigid_body_acceleration
from engine.physics_core.friction import decide_static_or_motion
from engine.services import solve_problem, diagnose_problem


def test_pint_unit_conversions():
    assert math.isclose(Q_(500, "g").to("kg").magnitude, 0.5)
    assert math.isclose(Q_(36, "km/hour").to("m/s").magnitude, 10.0)
    assert math.isclose((Q_(10, "newton") * Q_(3, "meter")).to("joule").magnitude, 30.0)
    assert math.isclose(magnitude_si(Quantity("m", 500, "g"), "kg"), 0.5)
    assert assert_dimension(Q_(1, "m/s^2"), "acceleration")


def test_vector_rigid_body_kinematics():
    vB = rigid_body_velocity(Vec2(3, 0), 4, Vec2(0, 0.5))
    assert math.isclose(vB.x, 1.0, abs_tol=1e-9)
    assert math.isclose(vB.y, 0.0, abs_tol=1e-9)
    aB = rigid_body_acceleration(Vec2(0, 0), 3, 4, Vec2(0.6, 0))
    assert math.isclose(aB.x, -9.6, abs_tol=1e-9)
    assert math.isclose(aB.y, 1.8, abs_tol=1e-9)


def test_static_friction_holds_incline():
    # Direct utility-level friction decision.
    driving = 2.0
    max_static = 3.0
    assert decide_static_or_motion(driving, max_static) == "static_hold"


def test_pulley_topologies():
    assert diagnose_problem("m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도는?").canonical.pulley_topology == "atwood"
    assert diagnose_problem("수평면 위 m1=3kg와 매달린 m2=2kg가 도르래로 연결되어 있다. 가속도는?").canonical.pulley_topology == "table_hanging"
    assert diagnose_problem("경사면 위 m1=3kg와 매달린 m2=2kg가 도르래로 연결되어 있다. 경사각 30도, 가속도는?").canonical.pulley_topology == "incline_hanging"


def test_projectile_horizontal_from_cliff_range():
    out = solve_problem("높이 20m에서 수평으로 10m/s로 던졌다. 사거리는?")
    assert out.ok
    assert out.diagnosis.selected_solver == "projectile_motion"
    assert math.isclose(out.answer.numeric, 10 * math.sqrt(2 * 20 / 9.81), rel_tol=1e-3)


def test_rolling_shapes_beta_order():
    sphere = solve_problem("정지 상태에서 속이 찬 구가 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?")
    disk = solve_problem("정지 상태에서 원판이 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?")
    hoop = solve_problem("정지 상태에서 고리가 미끄러지지 않고 높이 1m 굴러 내려온다. 속도는?")
    assert sphere.ok and disk.ok and hoop.ok
    assert sphere.answer.numeric > disk.answer.numeric > hoop.answer.numeric
