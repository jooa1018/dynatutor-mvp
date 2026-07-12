import math
from engine.services import solve_problem, diagnose_problem


def test_relative_acceleration_translation_solver():
    out = solve_problem("A점 가속도 aA=1.2 m/s^2가 오른쪽이고 A에 대한 B의 상대가속도 a_rel=0.8 m/s^2도 오른쪽이다. B점 가속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "relative_acceleration_translation"
    assert abs(out.answer.numeric - 2.0) < 1e-6
    assert "a_B" in out.answer.display
    assert out.diagnosis.fbd_diagram_svg is not None


def test_coriolis_relative_motion_solver():
    out = solve_problem("회전좌표계에서 r=0.5 m, 상대속도 v_rel=0.4 m/s, 상대가속도 a_rel=0.1 m/s^2, 각속도 omega=6 rad/s, 각가속도 alpha=2 rad/s^2 이다. 코리올리 가속도와 절대가속도 성분을 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "coriolis_relative_motion"
    ac = 2 * 6 * 0.4
    ar = 0.1 - 0.5 * 6**2
    at = 0.5 * 2 + ac
    assert abs(out.answer.numeric - math.hypot(ar, at)) < 1e-6
    assert "a_C" in out.answer.display
    assert any("2ω" in eq for eq in out.equation_sheet)


def test_plane_rigid_body_acceleration_solver():
    out = solve_problem("평면강체에서 A점은 고정되어 있고 B는 A에서 오른쪽으로 r=0.6 m 떨어져 있다. 각속도 omega=4 rad/s와 각가속도 alpha=3 rad/s^2는 모두 반시계방향이다. B점의 A에 대한 가속도 성분을 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "plane_rigid_body_acceleration"
    assert abs(out.answer.numeric - math.hypot(1.8, 9.6)) < 1e-6
    assert "a_t" in out.answer.display
    assert "a_n" in out.answer.display


def test_massive_pulley_atwood_solver():
    out = solve_problem("질량 있는 도르래에 m1=2 kg, m2=5 kg가 줄로 연결되어 있다. 도르래 관성모멘트 I=0.12 kgm^2, 도르래 반지름 R=0.3 m 일 때 가속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "massive_pulley_atwood"
    expected = (5 - 2) * 9.81 / (2 + 5 + 0.12 / 0.3**2)
    assert abs(out.answer.numeric - expected) < 1e-6
    assert "T1" in out.answer.display and "T2" in out.answer.display
    assert any("T1 = T2" in eq for eq in out.diagnosis.not_applicable_equations)


def test_general_rolling_energy_solver():
    out = solve_problem("정지 상태에서 질량 3 kg, 반지름 R=0.4 m, 관성모멘트 I=0.18 kgm^2 인 강체가 미끄러지지 않고 경사면을 높이 h=1.2 m만큼 굴러 내려간다. 속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "rolling_energy_general"
    expected = math.sqrt(2 * 3 * 9.81 * 1.2 / (3 + 0.18 / 0.4**2))
    assert abs(out.answer.numeric - expected) < 1e-6
    assert "ω" in out.answer.display


def test_phase8_examples_stats_grew():
    from engine.examples.library import example_stats
    stats = example_stats()
    assert stats["total"] >= 17
    assert stats["difficulties"]["상급"] >= 7


def test_phase8_diagnosis_contains_advanced_cards():
    d = diagnose_problem("회전좌표계에서 상대속도 v_rel=0.4 m/s, 각속도 omega=6 rad/s 이다. 코리올리 가속도를 구하라.")
    assert d.canonical.system_type == "coriolis_relative_motion"
    assert any("코리올리" in x or "2ω" in x for x in d.applicable_equations)
    assert d.fbd_diagram_svg is not None
