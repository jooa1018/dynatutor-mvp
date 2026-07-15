from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np
import pytest
import sympy as sp

from engine.simulation.contracts import SimulationStatus
from engine.simulation.scenarios import (
    evaluate_validation_case,
    smoke_validation_cases,
)
from engine.simulation.symbolic import (
    build_numeric_typed_model,
    build_sympy_mechanics_system,
    list_numeric_model_contracts,
)
from engine.simulation.sympy_scipy import (
    run_numeric_system,
    simulate_numeric,
    validate_simulation_spec,
)


pytestmark = pytest.mark.regression


@pytest.mark.parametrize(
    "case",
    smoke_validation_cases(),
    ids=lambda case: case.case_id,
)
def test_phase50_real_sympy_scipy_smoke_paths(case):
    result = simulate_numeric(case.spec)
    verdict = evaluate_validation_case(case, result)

    assert result.status in {
        SimulationStatus.COMPLETED,
        SimulationStatus.COMPLETED_WITH_WARNINGS,
    }
    assert verdict["passed"], result.to_dict()
    assert result.trajectory is not None
    assert len(result.trajectory.time) == len(case.spec.evaluation_grid)
    assert result.solver_diagnostics["typed_model"]["system_type"] == (
        case.spec.model_id
    )
    assert result.solver_diagnostics["symbolic_system"]["derivation_metadata"][
        "engine"
    ] == "sympy.physics.mechanics.LagrangesMethod"
    assert result.solver_diagnostics["scipy_version"] != "unknown"
    assert result.solver_diagnostics["offline_only"] is True
    assert result.solver_diagnostics["student_answer_overwrite"] is False
    json.dumps(result.to_dict(), allow_nan=False)


def test_phase50_symbolic_models_preserve_exact_mechanics_contracts():
    pendulum_case, spring_case = smoke_validation_cases()
    pendulum_typed = build_numeric_typed_model(pendulum_case.spec)
    pendulum = build_sympy_mechanics_system(
        pendulum_case.spec,
        pendulum_typed,
    )
    spring_typed = build_numeric_typed_model(spring_case.spec)
    spring = build_sympy_mechanics_system(spring_case.spec, spring_typed)

    theta, theta_dot = pendulum.coordinate_symbols + pendulum.speed_symbols
    mass, length, gravity = pendulum.parameter_symbols
    assert sp.simplify(pendulum.mass_matrix[0, 0] - mass * length**2) == 0
    assert sp.simplify(
        pendulum.forcing[0] + mass * gravity * length * sp.sin(theta)
    ) == 0
    assert pendulum.state_variables == ("theta", "theta_dot")
    assert theta_dot in pendulum.total_energy.free_symbols
    assert pendulum_typed.constraints[0].kind == "fixed_length"

    position, speed = spring.coordinate_symbols + spring.speed_symbols
    mass, stiffness, damping = spring.parameter_symbols
    assert sp.simplify(spring.mass_matrix[0, 0] - mass) == 0
    assert sp.simplify(
        spring.forcing[0] + stiffness * position + damping * speed
    ) == 0
    assert spring.state_variables == ("x", "x_dot")
    assert spring_typed.forces[0].kind == "spring_damper"
    assert [item["model_id"] for item in list_numeric_model_contracts()] == [
        "mass_spring_damper",
        "simple_pendulum",
    ]


def test_phase50_invalid_specs_fail_closed_before_numeric_execution():
    case = smoke_validation_cases()[0]
    invalid = replace(
        case.spec,
        parameters={"m": 1.0, "L": 0.0, "g": 9.81},
        evaluation_grid=(0.0, 0.5, 0.4, 1.0),
        rtol=-1.0,
    )

    errors = validate_simulation_spec(invalid)
    result = simulate_numeric(invalid)

    assert any("positive" in error for error in errors)
    assert any("strictly increasing" in error for error in errors)
    assert any("rtol" in error for error in errors)
    assert result.status == SimulationStatus.INVALID_SPEC
    assert not result.passed
    assert result.trajectory is None


def test_phase50_missing_scipy_is_an_explicit_dependency_failure(monkeypatch):
    case = smoke_validation_cases()[0]

    def unavailable():
        raise ImportError("controlled missing scipy")

    monkeypatch.setattr(
        "engine.simulation.sympy_scipy._load_numeric_runtime",
        unavailable,
    )
    result = simulate_numeric(case.spec)

    assert result.status == SimulationStatus.DEPENDENCY_UNAVAILABLE
    assert result.errors == (
        "SciPy numeric runtime is unavailable: controlled missing scipy",
    )


def _built_smoke_system():
    case = smoke_validation_cases()[1]
    typed_model = build_numeric_typed_model(case.spec)
    system = build_sympy_mechanics_system(case.spec, typed_model)
    return case, system


def _fake_solution(spec, *, states=None, success=True):
    state_matrix = (
        np.asarray(states, dtype=float)
        if states is not None
        else np.tile(
            np.asarray(spec.initial_state, dtype=float).reshape((-1, 1)),
            (1, len(spec.evaluation_grid)),
        )
    )
    return SimpleNamespace(
        success=success,
        message="controlled solution",
        status=0 if success else -1,
        nfev=1,
        njev=0,
        nlu=0,
        t=np.asarray(spec.evaluation_grid, dtype=float),
        y=state_matrix,
        t_events=[],
    )


def test_phase50_singular_mass_matrix_is_rejected_before_integration():
    case, system = _built_smoke_system()
    singular = replace(system, mass_matrix=sp.zeros(1, 1))

    result = run_numeric_system(
        case.spec,
        singular,
        np_module=np,
        solve_ivp_impl=lambda *args, **kwargs: pytest.fail(
            "solve_ivp must not run for a singular mass matrix"
        ),
        scipy_version="controlled",
    )

    assert result.status == SimulationStatus.SINGULAR_MASS_MATRIX


@pytest.mark.parametrize(
    ("states", "expected_status"),
    [
        ([[float("inf")] * 51, [0.0] * 51], SimulationStatus.NONFINITE_OUTPUT),
        ([[1.0e7] * 51, [0.0] * 51], SimulationStatus.RUNAWAY_STATE),
    ],
)
def test_phase50_nonfinite_and_runaway_trajectories_fail_explicitly(
    states,
    expected_status,
):
    case, system = _built_smoke_system()
    result = run_numeric_system(
        case.spec,
        system,
        np_module=np,
        solve_ivp_impl=lambda *args, **kwargs: _fake_solution(
            case.spec,
            states=states,
        ),
        scipy_version="controlled",
    )

    assert result.status == expected_status
    assert not result.passed


def test_phase50_nonfinite_observable_cannot_escape_postprocessing():
    case, system = _built_smoke_system()
    nonfinite_observable = replace(system, observables={"bad": sp.nan})

    result = run_numeric_system(
        case.spec,
        nonfinite_observable,
        np_module=np,
        solve_ivp_impl=lambda *args, **kwargs: _fake_solution(case.spec),
        scipy_version="controlled",
    )

    assert result.status == SimulationStatus.NONFINITE_OUTPUT
    assert result.errors == ("observable bad became non-finite",)


def test_phase50_solver_reported_failure_is_not_a_trajectory():
    case, system = _built_smoke_system()
    result = run_numeric_system(
        case.spec,
        system,
        np_module=np,
        solve_ivp_impl=lambda *args, **kwargs: _fake_solution(
            case.spec,
            success=False,
        ),
        scipy_version="controlled",
    )

    assert result.status == SimulationStatus.INTEGRATION_FAILED
    assert result.trajectory is None
