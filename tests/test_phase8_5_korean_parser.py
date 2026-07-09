import math

from engine.extraction.normalizer import normalize
from engine.services import solve_problem, diagnose_problem


def test_korean_si_normalizer_converts_common_units():
    text = normalize("질량 500g, 반지름 30cm, 속도 72 km/h, 시간 2분")
    assert "0.5 kg" in text
    assert "0.3 m" in text
    assert "20 m/s" in text
    assert "120 s" in text


def test_korean_rest_start_final_velocity_no_missing_false_positive():
    out = solve_problem("정지 상태에서 출발한 물체가 가속도 2m/s²로 5초 동안 직선 운동한다. 최종속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "constant_acceleration_1d"
    assert math.isclose(out.answer.numeric, 10.0, rel_tol=1e-5)
    assert out.diagnosis.canonical.missing_info == []


def test_korean_stop_condition_requests_time_not_distance():
    out = solve_problem("최종적으로 정지할 때까지 가속도 -2m/s^2로 움직인다. 초속도 10m/s일 때 걸리는 시간은?")
    assert out.ok
    assert out.diagnosis.selected_solver == "constant_acceleration_1d"
    assert out.answer.unit == "s"
    assert math.isclose(out.answer.numeric, 5.0, rel_tol=1e-5)


def test_korean_projectile_with_kmh_speed():
    out = solve_problem("발사속도 72 km/h, 발사각 30도인 포물선 운동에서 같은 높이에 착지할 때 사거리를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "projectile_motion"
    assert 35.0 < out.answer.numeric < 35.6


def test_korean_spring_period_with_grams():
    out = solve_problem("스프링 상수 200N/m, 질량 500g인 스프링-질량계의 주기를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "spring_mass_vibration"
    assert out.answer.unit == "s"
    assert math.isclose(out.answer.numeric, 2 * math.pi / math.sqrt(200 / 0.5), rel_tol=1e-4)


def test_korean_work_with_centimeter_distance_after_quantity():
    out = solve_problem("힘 10N이 물체를 30cm 이동시켰다. 한 일을 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "constant_force_work"
    assert math.isclose(out.answer.numeric, 3.0, rel_tol=1e-5)


def test_korean_frictionless_incline_variants():
    out = solve_problem("질량 500g인 블록이 마찰이 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "incline_no_friction"
    assert math.isclose(out.answer.numeric, 4.905, rel_tol=1e-4)

    out2 = solve_problem("마찰을 무시할 수 있는 30도 경사면에서 블록의 가속도를 구하라.")
    assert out2.ok
    assert out2.diagnosis.selected_solver == "incline_no_friction"


def test_korean_massive_pulley_with_centimeter_radius():
    out = solve_problem("도르래 관성모멘트 I=0.12 kgm^2, 도르래 반지름 30cm, m1=2kg, m2=5kg인 질량 있는 도르래에서 가속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "massive_pulley_atwood"
    expected = (5 - 2) * 9.81 / (2 + 5 + 0.12 / 0.3**2)
    assert math.isclose(out.answer.numeric, expected, rel_tol=1e-5)


def test_korean_vertical_circle_centimeter_radius():
    out = solve_problem("반지름 200cm인 수직 원운동 최고점에서 최소속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "vertical_circle"
    assert math.isclose(out.answer.numeric, math.sqrt(9.81 * 2), rel_tol=1e-4)


def test_korean_flat_curve_large_centimeter_radius():
    out = solve_problem("평평한 커브 반지름 5,000cm, 마찰계수 0.4일 때 최대속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "flat_curve_friction"
    assert math.isclose(out.answer.numeric, math.sqrt(0.4 * 9.81 * 50), rel_tol=1e-4)


def test_korean_polar_units_and_components():
    out = solve_problem("극좌표에서 r=200cm, r_dot=0.5m/s, r_ddot=0.1m/s^2, theta_dot=3rad/s, theta_ddot=0.2rad/s^2 일 때 가속도 성분을 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "polar_kinematics"
    assert "a_r" in out.answer.display
    assert math.isclose(out.answer.numeric, math.hypot(-17.9, 3.4), rel_tol=1e-4)


def test_korean_spring_energy_with_centimeters_and_grams():
    out = solve_problem("스프링 상수 300N/m인 스프링이 압축량 20cm만큼 압축되어 질량 1500g 물체를 밀어낸다. 속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "spring_energy_speed"
    assert math.isclose(out.answer.numeric, 0.2 * math.sqrt(300 / 1.5), rel_tol=1e-4)


def test_korean_diagnosis_source_text_preserves_converted_values():
    d = diagnose_problem("질량 500g인 블록이 마찰 없음 30도 경사면에서 미끄러진다. 가속도?")
    assert d.canonical.knowns["m"].value == 0.5
    assert d.canonical.knowns["theta"].value == 30
    assert d.canonical.system_type == "particle_on_incline"
