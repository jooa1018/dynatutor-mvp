from engine.qa.korean_benchmark import KOREAN_BENCHMARK_CASES
from engine.services import solve_problem


def test_phase10_korean_quality_benchmark_all_supported_cases_solve():
    failures = []
    for idx, (problem_text, expected_solver) in enumerate(KOREAN_BENCHMARK_CASES, start=1):
        result = solve_problem(problem_text)
        got_solver = result.diagnosis.selected_solver
        missing = result.diagnosis.canonical.missing_info
        if got_solver != expected_solver or not result.ok or missing or result.answer is None:
            failures.append(
                {
                    "index": idx,
                    "problem": problem_text,
                    "expected_solver": expected_solver,
                    "got_solver": got_solver,
                    "ok": result.ok,
                    "missing": missing,
                    "answer": result.answer.display if result.answer else None,
                    "system_type": result.diagnosis.canonical.system_type,
                }
            )
    assert not failures, failures


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
