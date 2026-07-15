from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.simulation.contracts import (
    DEFAULT_NUMERIC_SAFETY_POLICY,
    NumericEventSpec,
    NumericSimulationResult,
    NumericSimulationSpec,
)
from engine.simulation.symbolic import (
    MASS_SPRING_DAMPER_VERSION,
    SIMPLE_PENDULUM_VERSION,
)


VALIDATION_SUITE_VERSION = "phase50-numeric-validation-suite-v1"


@dataclass(frozen=True)
class NumericValidationCase:
    case_id: str
    spec: NumericSimulationSpec
    require_analytic_agreement: bool = True
    require_large_angle_difference: bool = False
    required_event_id: str | None = None


def _evaluation_grid(start: float, end: float, count: int) -> tuple[float, ...]:
    if count < 2:
        raise ValueError("count must be at least two")
    step = (float(end) - float(start)) / (count - 1)
    values = [float(start) + index * step for index in range(count)]
    values[0] = float(start)
    values[-1] = float(end)
    return tuple(values)


def _pendulum_spec(
    *,
    theta: float,
    theta_dot: float,
    end: float,
    samples: int,
    event: bool = False,
) -> NumericSimulationSpec:
    events = (
        NumericEventSpec(
            event_id="theta_downward_zero",
            state_variable="theta",
            threshold=0.0,
            direction=-1,
            terminal=False,
        ),
    ) if event else ()
    return NumericSimulationSpec(
        model_id="simple_pendulum",
        model_version=SIMPLE_PENDULUM_VERSION,
        state_variables=("theta", "theta_dot"),
        state_units={"theta": "rad", "theta_dot": "rad/s"},
        parameters={"m": 1.25, "L": 0.8, "g": 9.81},
        parameter_units={"m": "kg", "L": "m", "g": "m/s^2"},
        initial_state=(theta, theta_dot),
        t_start=0.0,
        t_end=end,
        evaluation_grid=_evaluation_grid(0.0, end, samples),
        integration_method="DOP853",
        rtol=1e-10,
        atol=1e-12,
        max_step=0.02,
        events=events,
        random_seed=5001,
    )


def _spring_spec(
    *,
    case_seed: int,
    mass: float,
    stiffness: float,
    damping: float,
    position: float,
    speed: float,
    end: float,
    samples: int,
) -> NumericSimulationSpec:
    return NumericSimulationSpec(
        model_id="mass_spring_damper",
        model_version=MASS_SPRING_DAMPER_VERSION,
        state_variables=("x", "x_dot"),
        state_units={"x": "m", "x_dot": "m/s"},
        parameters={"m": mass, "k": stiffness, "c": damping},
        parameter_units={"m": "kg", "k": "N/m", "c": "N*s/m"},
        initial_state=(position, speed),
        t_start=0.0,
        t_end=end,
        evaluation_grid=_evaluation_grid(0.0, end, samples),
        integration_method="DOP853",
        rtol=1e-10,
        atol=1e-12,
        max_step=0.02,
        random_seed=case_seed,
    )


def smoke_validation_cases() -> tuple[NumericValidationCase, ...]:
    return (
        NumericValidationCase(
            case_id="pendulum_small_angle_smoke",
            spec=_pendulum_spec(
                theta=0.04,
                theta_dot=0.0,
                end=1.0,
                samples=51,
                event=True,
            ),
            required_event_id="theta_downward_zero",
        ),
        NumericValidationCase(
            case_id="spring_undamped_smoke",
            spec=_spring_spec(
                case_seed=5002,
                mass=1.5,
                stiffness=12.0,
                damping=0.0,
                position=0.2,
                speed=-0.1,
                end=1.0,
                samples=51,
            ),
        ),
    )


def accuracy_validation_cases() -> tuple[NumericValidationCase, ...]:
    return (
        NumericValidationCase(
            case_id="pendulum_small_angle_accuracy",
            spec=_pendulum_spec(
                theta=0.04,
                theta_dot=0.0,
                end=4.0,
                samples=401,
                event=True,
            ),
            required_event_id="theta_downward_zero",
        ),
        NumericValidationCase(
            case_id="pendulum_large_angle_expected_difference",
            spec=_pendulum_spec(
                theta=1.0,
                theta_dot=0.0,
                end=8.0,
                samples=801,
            ),
            require_analytic_agreement=False,
            require_large_angle_difference=True,
        ),
        NumericValidationCase(
            case_id="spring_undamped_accuracy",
            spec=_spring_spec(
                case_seed=5003,
                mass=1.5,
                stiffness=12.0,
                damping=0.0,
                position=0.2,
                speed=-0.1,
                end=4.0,
                samples=401,
            ),
        ),
        NumericValidationCase(
            case_id="spring_underdamped_accuracy",
            spec=_spring_spec(
                case_seed=5004,
                mass=1.0,
                stiffness=9.0,
                damping=0.8,
                position=0.3,
                speed=-0.2,
                end=5.0,
                samples=501,
            ),
        ),
        NumericValidationCase(
            case_id="spring_critical_accuracy",
            spec=_spring_spec(
                case_seed=5005,
                mass=1.0,
                stiffness=4.0,
                damping=4.0,
                position=0.25,
                speed=0.1,
                end=4.0,
                samples=401,
            ),
        ),
        NumericValidationCase(
            case_id="spring_overdamped_accuracy",
            spec=_spring_spec(
                case_seed=5006,
                mass=1.0,
                stiffness=4.0,
                damping=6.0,
                position=-0.25,
                speed=0.15,
                end=4.0,
                samples=401,
            ),
        ),
    )


def evaluate_validation_case(
    case: NumericValidationCase,
    result: NumericSimulationResult,
) -> dict[str, Any]:
    policy = DEFAULT_NUMERIC_SAFETY_POLICY
    trajectory = result.trajectory
    analytic_error = result.analytic_error
    max_abs_error = analytic_error.get("max_abs_error")
    analytic_agreement = (
        bool(analytic_error.get("applicable"))
        and isinstance(max_abs_error, (int, float))
        and float(max_abs_error) <= policy.analytic_absolute_warning
    )
    large_angle_difference = (
        bool(analytic_error.get("expected_large_angle_difference"))
        and not bool(analytic_error.get("applicable"))
        and isinstance(max_abs_error, (int, float))
        and float(max_abs_error) > policy.analytic_absolute_warning
    )
    event_passed = True
    if case.required_event_id is not None:
        event_passed = (
            int(result.events.get(case.required_event_id, {}).get("count", 0))
            >= 1
        )
    checks = {
        "simulation_completed": result.passed,
        "trajectory_complete": (
            trajectory is not None
            and len(trajectory.time) == len(case.spec.evaluation_grid)
        ),
        "energy_policy_passed": bool(result.invariant_drift.get("passed")),
        "constraint_policy_passed": bool(
            result.constraint_violation.get("passed")
        ),
        "analytic_contract_passed": (
            analytic_agreement
            if case.require_analytic_agreement
            else large_angle_difference
            if case.require_large_angle_difference
            else True
        ),
        "required_event_observed": event_passed,
        "offline_only": (
            result.solver_diagnostics.get("offline_only") is True
        ),
        "student_answer_preserved": (
            result.solver_diagnostics.get("student_answer_overwrite") is False
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "analytic_agreement": analytic_agreement,
        "large_angle_difference": large_angle_difference,
    }


__all__ = [
    "VALIDATION_SUITE_VERSION",
    "NumericValidationCase",
    "accuracy_validation_cases",
    "evaluate_validation_case",
    "smoke_validation_cases",
]
