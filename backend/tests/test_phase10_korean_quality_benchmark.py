import json

import pytest

from engine.qa.korean_benchmark import KOREAN_BENCHMARK_CASES
from engine.services import solve_problem


@pytest.mark.parametrize(
    ("case_index", "problem_text", "expected_solver"),
    [
        (index, problem_text, expected_solver)
        for index, (problem_text, expected_solver) in enumerate(
            KOREAN_BENCHMARK_CASES, start=1
        )
    ],
    ids=lambda value: str(value) if isinstance(value, int) else None,
)
def test_phase10_korean_quality_benchmark_all_supported_cases_solve(
    case_index, problem_text, expected_solver
):
    result = solve_problem(problem_text)
    canonical = result.diagnosis.canonical
    if result.diagnosis.selected_solver != expected_solver:
        print(json.dumps({
            "index": case_index,
            "problem": problem_text,
            "expected_solver": expected_solver,
            "got_solver": result.diagnosis.selected_solver,
            "canonical_knowns": sorted(canonical.knowns),
            "requested_outputs": canonical.requested_outputs,
            "missing_info": canonical.missing_info,
            "route": result.route_decision.model_dump() if result.route_decision else None,
        }, ensure_ascii=False, indent=2))
    assert result.diagnosis.selected_solver == expected_solver
    assert result.ok, {
        "index": case_index,
        "problem": problem_text,
        "unsupported_reason": result.unsupported_reason,
        "verification_errors": result.verification.errors,
    }
    assert canonical.missing_info == [], {
        "index": case_index,
        "problem": problem_text,
        "missing": canonical.missing_info,
    }
    assert result.answer is not None


def test_phase10_benchmark_size_and_domain_coverage():
    assert len(KOREAN_BENCHMARK_CASES) == 100
    solvers = {expected for _, expected in KOREAN_BENCHMARK_CASES}
    required = {
        "incline_no_friction",
        "incline_with_friction",
        "pulley_table_hanging",
        "vertical_circle",
        "pure_rolling_energy",
        "constant_acceleration_1d",
        "projectile_motion",
        "constant_force_work",
        "fixed_axis_rotation",
        "impulse_momentum",
        "collision_1d",
        "spring_mass_vibration",
        "spring_energy_speed",
        "flat_curve_friction",
        "banked_curve_no_friction",
        "polar_kinematics",
        "instant_center_velocity",
        "slot_pin_relative_motion",
        "plane_rigid_body_velocity",
        "work_energy_speed",
        "relative_acceleration_translation",
        "coriolis_relative_motion",
        "plane_rigid_body_acceleration",
        "massive_pulley_atwood",
        "rolling_energy_general",
    }
    assert required.issubset(solvers)
