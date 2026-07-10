from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.extraction.extractor import extract_problem
from engine.physics_core.answer_validators import validate_answer_consistency, validate_solve_response


@pytest.mark.unit
def test_requested_outputs_does_not_treat_when_phrase_as_work():
    problem = "m1=10kg가 30도 경사면 위에 있고 m2=1kg가 도르래에 매달려 있다. 운동마찰계수 0.5일 때 가속도는?"
    cp = extract_problem(problem)
    assert "acceleration" in cp.requested_outputs
    assert "work" not in cp.requested_outputs


@pytest.mark.unit
def test_requested_outputs_work_positive_case():
    problem = "마찰력 10N이 이동 방향 반대로 3m 작용했다. 마찰력이 한 일은?"
    cp = extract_problem(problem)
    assert "work" in cp.requested_outputs


@pytest.mark.unit
def test_requested_outputs_does_not_treat_constant_as_work():
    problem = "일정한 가속도 2m/s²로 5초 동안 움직였다. 최종속도는?"
    cp = extract_problem(problem)
    assert "work" not in cp.requested_outputs


@pytest.mark.unit
def test_requested_outputs_does_not_treat_given_time_or_work_as_requested():
    cp = extract_problem("힘 10N이 시간 2s 동안 작용한다. 충격량을 구하라.")
    assert "time" not in cp.requested_outputs
    cp2 = extract_problem("질량 2kg 물체에 알짜일 16J가 작용한다. 최종속도를 구하라.")
    assert "work" not in cp2.requested_outputs
    assert "final_velocity" in cp2.requested_outputs


@pytest.mark.regression
def test_answer_and_answers_are_consistent_for_projectile():
    from engine.services import solve_problem
    result = solve_problem(
        "높이 20 m인 절벽 위에서 공을 수평 방향으로 36 km/h의 속력으로 던졌다. "
        "공기저항을 무시할 때 공이 지면에 닿을 때까지 걸리는 시간과 수평거리를 구하라."
    )
    report = validate_solve_response(result)
    assert report.passed, report.errors
    assert result.answer.display == result.answers[0].display


@pytest.mark.regression
def test_requested_outputs_are_all_present_in_answers():
    from engine.services import solve_problem
    result = solve_problem("m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도와 장력은?")
    report = validate_solve_response(result)
    assert report.passed, report.errors
    symbols = {a.symbol for a in result.answers}
    assert {"a", "T"}.issubset(symbols)


@pytest.mark.regression
def test_no_primary_answer_without_unit():
    from engine.services import solve_problem
    result = solve_problem("질량 0.5kg인 물체에 힘 10N이 작용한다. 가속도는?")
    assert result.ok
    assert all(a.unit for a in result.answers if a.role == "primary")


@pytest.mark.regression
def test_missing_required_answer_is_error_not_warning():
    fake_answer = SimpleNamespace(symbol="t", label="시간", numeric=2.02, unit="s", display="t = 2.02 s", role="primary")
    validation = validate_answer_consistency(
        ok=True,
        answer=fake_answer,
        answers=[fake_answer],
        requested_outputs=["time", "range"],
    )
    assert validation.errors
    assert not validation.warnings or all("requested_outputs" not in w for w in validation.warnings)


@pytest.mark.regression
def test_requested_outputs_all_present_in_answers_runtime_phase28():
    from engine.services import solve_problem
    result = solve_problem("높이 20 m에서 공을 수평 방향으로 36 km/h로 던졌다. 시간과 수평거리는?")
    symbols = {a.symbol for a in result.answers}
    assert result.ok is True, result.unsupported_reason
    assert "t" in symbols
    assert "R" in symbols
    assert not result.verification.errors


@pytest.mark.frontend
def test_frontend_metadata_only_no_build_execution():
    root = Path(__file__).resolve().parents[2]
    assert (root / "frontend" / "package.json").exists()
    assert (root / "frontend" / "package-lock.json").exists()
    assert (root / "frontend" / "next.config.js").exists()
    assert (root / "scripts" / "check_frontend_build.sh").exists()
    wrapper_text = (root / "scripts" / "check_frontend_build.py").read_text(encoding="utf-8")
    timeout_text = (root / "scripts" / "run_with_timeout.py").read_text(encoding="utf-8")
    assert "start_new_session=True" in wrapper_text
    assert "terminate_process_group(" in wrapper_text
    assert "process_group_exists(" in wrapper_text
    assert "os.killpg" in timeout_text


@pytest.mark.unit
def test_bitmyeon_synonym_routes_to_incline():
    # 혼동행렬 하니스가 발견한 동의어 공백 회귀 방지:
    # "빗면"(교과서 표준 표현)이 경사면으로 분류되어야 한다.
    cp = extract_problem("마찰 없는 30도 빗면에서 블록의 가속도를 구하라.")
    assert cp.system_type == "particle_on_incline"
    cp2 = extract_problem("30도 사면 위 물체의 가속도는?")
    assert cp2.system_type == "particle_on_incline"


@pytest.mark.unit
def test_temperature_degrees_not_parsed_as_launch_angle():
    # 교란 하니스 발견: "온도는 20도"의 20도가 theta로 주입되어 사거리 오답 유발.
    cp = extract_problem("높이 20m에서 수평으로 10m/s로 던졌다. 사거리는? 참고로 실험실 온도는 20도였다.")
    theta = cp.knowns.get("theta")
    # "수평으로"가 theta=0을 넣는 것은 정상. 온도 20이 각도로 새면 안 된다.
    assert theta is None or abs(theta.value) < 1e-9, f"온도 20도가 발사각으로 주입됨: {theta.value}"
    assert cp.launch_angle_source == "horizontal_phrase"
    assert cp.system_type == "projectile_motion"
    # 진짜 각도는 여전히 잡혀야 한다.
    cp2 = extract_problem("30도 방향으로 20 m/s로 공을 발사했다. 사거리는?")
    assert "theta" in cp2.knowns and abs(cp2.knowns["theta"].value - 30) < 1e-9


@pytest.mark.unit
def test_standing_in_line_idiom_does_not_trigger_pulley():
    # 교란 하니스 발견: "줄을 서서"(대기열)가 rope로 잡혀 366문항이 ambiguous_pulley로 거절됨.
    cp = extract_problem("마찰 없는 30도 경사면에서 블록의 가속도를 구하라. 학생들이 줄을 서서 실험 차례를 기다렸다.")
    assert cp.system_type == "particle_on_incline"
    # 진짜 줄(rope)은 여전히 pulley 증거여야 한다.
    cp2 = extract_problem("m1=3kg과 m2=5kg이 도르래에 줄로 연결되어 양쪽에 매달려 있다. 가속도는?")
    assert cp2.system_type == "pulley_atwood"


@pytest.mark.unit
def test_gyesan_verb_preserves_requested_outputs():
    # 교란 하니스 발견: "계산하라"를 몰라 requested_outputs가 비어 answer 검증이 무력화됨.
    cp = extract_problem("마찰 없는 10도 경사면에서 블록의 가속도를 계산하라.")
    assert "acceleration" in cp.requested_outputs


@pytest.mark.unit
def test_yongsucheol_synonym_routes_to_spring():
    # 교란 하니스 발견: "용수철"(스프링의 표준 한국어) 미탐으로 spring 문제 전멸.
    cp = extract_problem("용수철 상수 k=100N/m, 압축 0.2m, 질량 2kg일 때 속도는?")
    assert cp.system_type in ("spring_energy", "spring_mass_vibration")
