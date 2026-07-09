from engine.services import diagnose_problem, solve_problem
from engine.visualization.fbd import build_fbd_annotations
from engine.extraction.extractor import extract_problem


def test_phase7_incline_fbd_has_axes_components_and_annotations():
    out = diagnose_problem("질량 5kg인 블록이 마찰 있는 30도 경사면에서 미끄러진다. 마찰계수 0.2, 가속도를 구하라.")
    svg = out.fbd_diagram_svg or ""
    assert "경사면 위 블록" in svg
    assert "+x" in svg and "+y" in svg
    assert "mg sinθ" in svg
    assert "mg cosθ" in svg
    assert "범례" in svg
    assert out.fbd_annotations
    assert any("마찰력" in note or "마찰" in note for note in out.fbd_annotations)


def test_phase7_pulley_fbd_shows_two_bodies_acceleration_and_tension():
    out = diagnose_problem("수평면 위 m1=4 kg 블록과 매달린 m2=2 kg 블록이 도르래로 연결되어 있다. 가속도를 구하라.")
    svg = out.fbd_diagram_svg or ""
    assert "수평면-도르래" in svg
    assert "m₁g" in svg
    assert "m₂g" in svg
    assert "T" in svg
    assert "a" in svg
    assert any("가속도" in note for note in out.fbd_annotations)


def test_phase7_curve_and_polar_diagram_notes_are_specific():
    curve = diagnose_problem("평평한 커브 반지름 R=50 m, 마찰계수 0.4일 때 최대속도를 구하라.")
    assert "마찰이 구심력" in (curve.fbd_diagram_svg or "")
    assert any("정지마찰" in note for note in curve.fbd_annotations)

    polar = diagnose_problem("극좌표에서 r=2 m, r_dot=0.5 m/s, r_ddot=0.1 m/s^2, theta_dot=3 rad/s, theta_ddot=0.2 rad/s^2 일 때 가속도 성분을 구하라.")
    assert "e_r" in (polar.fbd_diagram_svg or "")
    assert "e_θ" in (polar.fbd_diagram_svg or "")
    assert any("e_r" in note for note in polar.fbd_annotations)


def test_phase7_solve_response_carries_fbd_annotations():
    out = solve_problem("스프링 상수 k=200 N/m, 질량 2 kg인 스프링-질량계의 고유진동수를 구하라.")
    assert out.ok
    assert out.diagnosis.fbd_annotations
    assert any("복원력" in note or "스프링" in note for note in out.diagnosis.fbd_annotations)


def test_phase7_unknown_has_safe_annotation():
    c = extract_problem("그림과 같은 시스템에서 구하라")
    notes = build_fbd_annotations(c)
    assert notes
    assert "개념도" in notes[0]
