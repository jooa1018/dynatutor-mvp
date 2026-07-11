import math
from engine.services import solve_problem, diagnose_problem


def test_polar_acceleration_components():
    out = solve_problem("극좌표에서 r=2 m, r_dot=0.5 m/s, r_ddot=0.1 m/s^2, theta_dot=3 rad/s, theta_ddot=0.2 rad/s^2 일 때 가속도 성분을 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "polar_kinematics"
    assert "a_r" in out.answer.display
    assert abs(out.answer.numeric - math.hypot(0.1 - 2*9, 2*0.2 + 2*0.5*3)) < 1e-4
    assert out.diagnosis.fbd_diagram_svg is not None


def test_instant_center_velocity():
    out = solve_problem("순간중심 IC에서 점 P까지 거리 r=0.8 m, 각속도 omega=5 rad/s 이다. 점 P의 속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "instant_center_velocity"
    assert abs(out.answer.numeric - 4.0) < 1e-6
    assert "v =" in out.answer.display


def test_instant_center_omega_from_speed():
    out = solve_problem("순간중심에서 점까지 거리 r=2 m이고 속도 v=6 m/s 이다. 각속도를 구하라.")
    assert out.ok
    assert out.answer.unit == "rad/s"
    assert abs(out.answer.numeric - 3.0) < 1e-6


def test_slot_pin_relative_motion():
    out = solve_problem("회전 슬롯 안의 핀이 r=0.4 m 위치에서 r_dot=0.3 m/s로 미끄러지고, 슬롯 각속도 omega=6 rad/s 이다. 핀의 절대속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "slot_pin_relative_motion"
    assert abs(out.answer.numeric - math.hypot(0.3, 2.4)) < 1e-6


def test_plane_rigid_body_velocity_basic():
    out = solve_problem("평면강체에서 A점은 오른쪽으로 vA=3 m/s이고 B점은 A에서 오른쪽으로 r=0.5 m 떨어져 있다. 강체가 반시계방향 omega=4 rad/s로 회전할 때 B점 속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "plane_rigid_body_velocity"
    assert abs(out.answer.numeric - math.hypot(3, 2)) < 1e-6


def test_phase4_diagnosis_cards():
    d = diagnose_problem("극좌표 운동에서 r=1 m, theta_dot=2 rad/s 일 때 가속도 성분을 구하라.")
    assert d.canonical.system_type == "polar_kinematics"
    assert any("e_r" in x for x in d.fbd)
    assert any("a_r" in x for x in d.applicable_equations)
