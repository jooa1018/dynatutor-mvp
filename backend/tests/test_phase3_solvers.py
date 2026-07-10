from engine.services import solve_problem


def test_work_energy_speed_from_given_work():
    out = solve_problem("질량 2 kg 물체에 일 W=16 J가 작용하고 처음 속도 v0=0 m/s 이다. 최종 속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "work_energy_speed"
    assert abs(out.answer.numeric - 4.0) < 1e-6
    assert out.verification.dimension_summary


def test_spring_mass_vibration_frequency():
    out = solve_problem("스프링 상수 k=200 N/m, 질량 2 kg인 스프링-질량계의 고유진동수를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "spring_mass_vibration"
    assert abs(out.answer.numeric - 10.0) < 1e-6
    assert out.answer.unit == "rad/s"
    assert out.diagnosis.fbd_diagram_svg is not None


def test_spring_energy_speed():
    out = solve_problem("스프링 상수 k=300 N/m인 스프링이 압축량 x=0.2 m만큼 압축되어 질량 1.5 kg 물체를 밀어낸다. 속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "spring_energy_speed"
    assert abs(out.answer.numeric - 2.82843) < 1e-4


def test_flat_curve_friction_max_speed():
    out = solve_problem("평평한 커브 반지름 R=50 m, 마찰계수 0.4일 때 미끄러지지 않는 최대속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "flat_curve_friction"
    assert abs(out.answer.numeric - 14.00714) < 1e-4


def test_banked_curve_no_friction_design_speed():
    out = solve_problem("마찰 없는 경사진 커브 반지름 R=80 m, 뱅크각 20도일 때 설계속도를 구하라.")
    assert out.ok
    assert out.diagnosis.selected_solver == "banked_curve_no_friction"
    assert out.answer.unit == "m/s"


def test_incline_has_fbd_svg_and_summary():
    out = solve_problem("질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.")
    assert out.ok
    assert out.diagnosis.fbd_diagram_svg is not None
    assert out.teacher_summary
