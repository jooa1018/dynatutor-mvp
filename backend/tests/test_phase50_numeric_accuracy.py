from __future__ import annotations

import json

import pytest

from engine.simulation.scenarios import (
    accuracy_validation_cases,
    evaluate_validation_case,
)
from engine.simulation.sympy_scipy import simulate_numeric
from tools.run_phase50_numeric_validation import (
    REPORT_ID,
    build_report,
    render_markdown,
    write_reports,
)


pytestmark = [pytest.mark.regression, pytest.mark.benchmark]


@pytest.mark.parametrize(
    "case",
    accuracy_validation_cases(),
    ids=lambda case: case.case_id,
)
def test_phase50_accuracy_and_invariant_contracts(case):
    result = simulate_numeric(case.spec)
    verdict = evaluate_validation_case(case, result)

    assert verdict["passed"], result.to_dict()
    assert result.invariant_drift["passed"] is True
    assert result.constraint_violation["passed"] is True
    if case.require_analytic_agreement:
        assert verdict["analytic_agreement"] is True
    if case.require_large_angle_difference:
        assert verdict["large_angle_difference"] is True


def test_phase50_damped_regimes_and_energy_direction_are_all_covered():
    regimes = {}
    for case in accuracy_validation_cases():
        if case.spec.model_id != "mass_spring_damper":
            continue
        result = simulate_numeric(case.spec)
        regimes[result.analytic_error["damping_regime"]] = result

    assert set(regimes) == {"underdamped", "critical", "overdamped"}
    for regime, result in regimes.items():
        assert result.passed, (regime, result.to_dict())
        assert result.invariant_drift["passed"] is True
        if float(result.solver_diagnostics["spec"]["parameters"]["c"]) > 0.0:
            assert result.invariant_drift["expected_behavior"] == "nonincreasing"


def test_phase50_runtime_report_is_passed_complete_and_deterministic(tmp_path):
    report = build_report()
    json.dumps(report, allow_nan=False)

    assert report["report_id"] == REPORT_ID
    assert report["status"] == "passed"
    assert report["passed"] is True
    assert report["summary"]["case_count"] == 6
    assert report["summary"]["passed_count"] == 6
    assert report["summary"]["scipy_trajectory_count"] == 6
    assert report["summary"]["model_counts"] == {
        "mass_spring_damper": 4,
        "simple_pendulum": 2,
    }
    assert report["summary"]["offline_only"] is True
    assert report["summary"]["student_answer_overwrite"] is False
    assert report["summary"]["pydy_required"] is False
    assert report["summary"]["normal_solve_path_changed"] is False

    first_json = tmp_path / "first.json"
    first_markdown = tmp_path / "first.md"
    second_json = tmp_path / "second.json"
    second_markdown = tmp_path / "second.md"
    write_reports(
        report,
        json_path=first_json,
        markdown_path=first_markdown,
    )
    write_reports(
        report,
        json_path=second_json,
        markdown_path=second_markdown,
    )

    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_markdown.read_bytes() == second_markdown.read_bytes()
    assert first_markdown.read_text(encoding="utf-8") == render_markdown(report)
