from __future__ import annotations

from pathlib import Path

import pytest

from engine.extraction.extractor import extract_problem
from engine.physics_core.answer_validators import validate_solve_response
from engine.services import solve_problem


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


@pytest.mark.regression
def test_answer_and_answers_are_consistent_for_projectile():
    result = solve_problem(
        "높이 20 m인 절벽 위에서 공을 수평 방향으로 36 km/h의 속력으로 던졌다. "
        "공기저항을 무시할 때 공이 지면에 닿을 때까지 걸리는 시간과 수평거리를 구하라."
    )
    report = validate_solve_response(result)
    assert report.passed, report.errors
    assert result.answer.display == result.answers[0].display


@pytest.mark.regression
def test_requested_outputs_are_all_present_in_answers():
    result = solve_problem("m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도와 장력은?")
    report = validate_solve_response(result)
    assert report.passed, report.errors
    symbols = {a.symbol for a in result.answers}
    assert {"a", "T"}.issubset(symbols)


@pytest.mark.regression
def test_no_primary_answer_without_unit():
    result = solve_problem("질량 0.5kg인 물체에 힘 10N이 작용한다. 가속도는?")
    assert result.ok
    assert all(a.unit for a in result.answers if a.role == "primary")


@pytest.mark.frontend
def test_frontend_metadata_only_no_build_execution():
    root = Path(__file__).resolve().parents[2]
    assert (root / "frontend" / "package.json").exists()
    assert (root / "frontend" / "package-lock.json").exists()
    assert (root / "scripts" / "check_frontend_build.sh").exists()
    wrapper_text = (root / "scripts" / "check_frontend_build.py").read_text(encoding="utf-8")
    timeout_text = (root / "scripts" / "run_with_timeout.py").read_text(encoding="utf-8")
    assert "start_new_session=True" in wrapper_text
    assert "terminate_process_group(" in wrapper_text
    assert "process_group_exists(" in wrapper_text
    assert "os.killpg" in timeout_text
