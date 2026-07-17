from __future__ import annotations

import json
import math

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
    assert result.analytic_error["comparison_tolerance"] > 0.0
    if case.require_analytic_agreement:
        assert verdict["analytic_agreement"] is True
    if case.require_large_angle_difference:
        assert verdict["large_angle_difference"] is True
    if case.require_equilibrium_hold:
        assert verdict["equilibrium_max_abs"] == 0.0
        assert result.analytic_error["observed_period"] is None


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


def test_phase50_pendulum_energy_scale_is_equilibrium_zero_and_shift_invariant():
    small_angle, _large_angle, equilibrium = accuracy_validation_cases()[:3]
    small_result = simulate_numeric(small_angle.spec)
    equilibrium_result = simulate_numeric(equilibrium.spec)
    expected_excitation = (
        float(small_angle.spec.parameters["m"])
        * float(small_angle.spec.parameters["g"])
        * float(small_angle.spec.parameters["L"])
        * (1.0 - math.cos(float(small_angle.spec.initial_state[0])))
    )

    assert small_result.invariant_drift["initial"] == pytest.approx(
        expected_excitation
    )
    assert small_result.invariant_drift["reference_scale"] == pytest.approx(
        expected_excitation
    )
    assert equilibrium_result.invariant_drift["initial"] == 0.0
    assert equilibrium_result.invariant_drift["reference_scale"] == 0.0


def test_phase50_runtime_report_is_passed_complete_and_deterministic(tmp_path):
    report = build_report()
    json.dumps(report, allow_nan=False)

    assert report["report_id"] == REPORT_ID
    assert report["status"] == "passed"
    assert report["passed"] is True
    assert report["summary"]["case_count"] == 7
    assert report["summary"]["passed_count"] == 7
    assert report["summary"]["scipy_trajectory_count"] == 7
    assert report["summary"]["model_counts"] == {
        "mass_spring_damper": 4,
        "simple_pendulum": 3,
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
