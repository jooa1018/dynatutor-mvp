from __future__ import annotations

import math
from typing import Any, Callable

import sympy as sp

from engine.simulation.contracts import (
    DEFAULT_NUMERIC_SAFETY_POLICY,
    NUMERIC_POLICY_VERSION,
    NumericEventSpec,
    NumericSafetyPolicy,
    NumericSimulationResult,
    NumericSimulationSpec,
    NumericTrajectory,
    SPEC_SCHEMA_VERSION,
    SimulationStatus,
)
from engine.simulation.symbolic import (
    SymPyMechanicsSystem,
    build_numeric_typed_model,
    build_sympy_mechanics_system,
    get_numeric_model_contract,
    typed_model_summary,
)


SUPPORTED_INTEGRATION_METHODS = frozenset(
    {"RK23", "RK45", "DOP853", "Radau", "BDF", "LSODA"}
)


class _SingularMassMatrixError(RuntimeError):
    pass


class _NonfiniteNumericError(RuntimeError):
    pass


def _failure_result(
    spec: NumericSimulationSpec,
    status: str,
    *errors: str,
    diagnostics: dict[str, Any] | None = None,
) -> NumericSimulationResult:
    return NumericSimulationResult(
        model_id=spec.model_id,
        model_version=spec.model_version,
        status=status,
        solver_diagnostics=diagnostics or {},
        errors=tuple(str(error) for error in errors),
        safety_policy_version=spec.safety_policy_version,
    )


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def validate_simulation_spec(
    spec: NumericSimulationSpec,
    *,
    policy: NumericSafetyPolicy = DEFAULT_NUMERIC_SAFETY_POLICY,
) -> tuple[str, ...]:
    errors: list[str] = []
    contract = get_numeric_model_contract(spec.model_id)
    if contract is None:
        return (f"unsupported numeric model: {spec.model_id}",)
    if spec.schema_version != SPEC_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SPEC_SCHEMA_VERSION}, got {spec.schema_version}"
        )
    if spec.model_version != contract.model_version:
        errors.append(
            f"model_version must be {contract.model_version!r}"
        )
    if spec.safety_policy_version != policy.policy_version:
        errors.append(
            f"safety_policy_version must be {policy.policy_version!r}"
        )
    if spec.state_variables != contract.state_variables:
        errors.append(
            f"state_variables must be {contract.state_variables!r}"
        )
    if dict(spec.state_units) != dict(contract.state_units):
        errors.append("state_units do not match the model contract")

    parameter_names = set(spec.parameters)
    expected_parameters = set(contract.parameter_names)
    missing_parameters = sorted(expected_parameters - parameter_names)
    extra_parameters = sorted(parameter_names - expected_parameters)
    if missing_parameters:
        errors.append(f"missing parameters: {missing_parameters}")
    if extra_parameters:
        errors.append(f"unexpected parameters: {extra_parameters}")
    if dict(spec.parameter_units) != dict(contract.parameter_units):
        errors.append("parameter_units do not match the model contract")
    for name, value in spec.parameters.items():
        if not _is_finite_number(value):
            errors.append(f"parameter {name!r} must be finite")

    if spec.model_id == "simple_pendulum":
        for name in ("m", "L", "g"):
            if name in spec.parameters and _is_finite_number(spec.parameters[name]):
                if float(spec.parameters[name]) <= 0.0:
                    errors.append(f"parameter {name!r} must be positive")
    elif spec.model_id == "mass_spring_damper":
        for name in ("m", "k"):
            if name in spec.parameters and _is_finite_number(spec.parameters[name]):
                if float(spec.parameters[name]) <= 0.0:
                    errors.append(f"parameter {name!r} must be positive")
        if "c" in spec.parameters and _is_finite_number(spec.parameters["c"]):
            if float(spec.parameters["c"]) < 0.0:
                errors.append("parameter 'c' must be non-negative")

    if len(spec.initial_state) != len(contract.state_variables):
        errors.append(
            f"initial_state must have {len(contract.state_variables)} values"
        )
    for index, value in enumerate(spec.initial_state):
        if not _is_finite_number(value):
            errors.append(f"initial_state[{index}] must be finite")

    if not _is_finite_number(spec.t_start) or not _is_finite_number(spec.t_end):
        errors.append("t_start and t_end must be finite")
    elif float(spec.t_end) <= float(spec.t_start):
        errors.append("t_end must be greater than t_start")

    if len(spec.evaluation_grid) < 2:
        errors.append("evaluation_grid must contain at least two points")
    elif all(_is_finite_number(value) for value in spec.evaluation_grid):
        grid = tuple(float(value) for value in spec.evaluation_grid)
        if any(right <= left for left, right in zip(grid, grid[1:])):
            errors.append("evaluation_grid must be strictly increasing")
        if _is_finite_number(spec.t_start) and not math.isclose(
            grid[0],
            float(spec.t_start),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            errors.append("evaluation_grid must start at t_start")
        if _is_finite_number(spec.t_end) and not math.isclose(
            grid[-1],
            float(spec.t_end),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            errors.append("evaluation_grid must end at t_end")
    else:
        errors.append("evaluation_grid values must be finite")

    if spec.integration_method not in SUPPORTED_INTEGRATION_METHODS:
        errors.append(
            f"unsupported integration_method: {spec.integration_method!r}"
        )
    for name in ("rtol", "atol", "max_step"):
        value = getattr(spec, name)
        if not _is_finite_number(value) or float(value) <= 0.0:
            errors.append(f"{name} must be a positive finite number")
    if spec.random_seed is not None and (
        isinstance(spec.random_seed, bool)
        or not isinstance(spec.random_seed, int)
    ):
        errors.append("random_seed must be an integer or None")

    event_ids: set[str] = set()
    for event in spec.events:
        if not isinstance(event, NumericEventSpec):
            errors.append("events must contain NumericEventSpec values")
            continue
        if not isinstance(event.event_id, str) or not event.event_id.strip():
            errors.append("event_id must be a non-empty string")
        else:
            if event.event_id in event_ids:
                errors.append(f"duplicate event_id: {event.event_id!r}")
            event_ids.add(event.event_id)
        if not isinstance(event.state_variable, str):
            errors.append("event state_variable must be a string")
        elif event.state_variable not in contract.state_variables:
            errors.append(
                f"event {event.event_id!r} references unknown state variable"
            )
        if not _is_finite_number(event.threshold):
            errors.append(f"event {event.event_id!r} threshold must be finite")
        if (
            isinstance(event.direction, bool)
            or not isinstance(event.direction, int)
            or event.direction not in {-1, 0, 1}
        ):
            errors.append(
                f"event {event.event_id!r} direction must be the integer "
                "-1, 0, or 1"
            )
        if not isinstance(event.terminal, bool):
            errors.append(f"event {event.event_id!r} terminal must be boolean")
    return tuple(errors)


def _load_numeric_runtime():
    import numpy as np
    import scipy
    from scipy.integrate import solve_ivp

    return np, solve_ivp, str(scipy.__version__)


def simulate_numeric(
    spec: NumericSimulationSpec,
    *,
    policy: NumericSafetyPolicy = DEFAULT_NUMERIC_SAFETY_POLICY,
) -> NumericSimulationResult:
    contract = get_numeric_model_contract(spec.model_id)
    if contract is None:
        return _failure_result(
            spec,
            SimulationStatus.UNSUPPORTED_MODEL,
            f"unsupported numeric model: {spec.model_id}",
        )
    errors = validate_simulation_spec(spec, policy=policy)
    if errors:
        return _failure_result(
            spec,
            SimulationStatus.INVALID_SPEC,
            *errors,
            diagnostics={"spec": spec.to_dict()},
        )
    try:
        typed_model = build_numeric_typed_model(spec)
        symbolic_system = build_sympy_mechanics_system(spec, typed_model)
    except (KeyError, TypeError, ValueError) as exc:
        return _failure_result(
            spec,
            SimulationStatus.INVALID_SPEC,
            f"cannot build typed/symbolic model: {exc}",
        )
    try:
        np, solve_ivp_impl, scipy_version = _load_numeric_runtime()
    except Exception as exc:
        return _failure_result(
            spec,
            SimulationStatus.DEPENDENCY_UNAVAILABLE,
            f"SciPy numeric runtime is unavailable: {exc}",
        )
    return run_numeric_system(
        spec,
        symbolic_system,
        np_module=np,
        solve_ivp_impl=solve_ivp_impl,
        scipy_version=scipy_version,
        policy=policy,
    )


def run_numeric_system(
    spec: NumericSimulationSpec,
    system: SymPyMechanicsSystem,
    *,
    np_module=None,
    solve_ivp_impl: Callable[..., Any] | None = None,
    scipy_version: str | None = None,
    policy: NumericSafetyPolicy = DEFAULT_NUMERIC_SAFETY_POLICY,
) -> NumericSimulationResult:
    errors = validate_simulation_spec(spec, policy=policy)
    if errors:
        return _failure_result(
            spec,
            SimulationStatus.INVALID_SPEC,
            *errors,
            diagnostics={"spec": spec.to_dict()},
        )
    if system.model_id != spec.model_id:
        return _failure_result(
            spec,
            SimulationStatus.INVALID_SPEC,
            "symbolic system and simulation spec model IDs differ",
        )
    if system.model_version != spec.model_version:
        return _failure_result(
            spec,
            SimulationStatus.INVALID_SPEC,
            "symbolic system and simulation spec versions differ",
        )

    if np_module is None or solve_ivp_impl is None:
        try:
            loaded_np, loaded_solve_ivp, loaded_scipy_version = (
                _load_numeric_runtime()
            )
        except Exception as exc:
            return _failure_result(
                spec,
                SimulationStatus.DEPENDENCY_UNAVAILABLE,
                f"SciPy numeric runtime is unavailable: {exc}",
            )
        np_module = np_module or loaded_np
        solve_ivp_impl = solve_ivp_impl or loaded_solve_ivp
        scipy_version = scipy_version or loaded_scipy_version

    np = np_module
    parameter_values = tuple(
        float(spec.parameters[name]) for name in system.parameter_names
    )
    numeric_args = (
        *system.coordinate_symbols,
        *system.speed_symbols,
        *system.parameter_symbols,
    )
    mass_function = sp.lambdify(numeric_args, system.mass_matrix, modules="numpy")
    forcing_function = sp.lambdify(
        numeric_args,
        system.forcing,
        modules="numpy",
    )
    energy_function = sp.lambdify(
        numeric_args,
        system.total_energy,
        modules="numpy",
    )
    observable_functions = {
        name: sp.lambdify(numeric_args, expression, modules="numpy")
        for name, expression in system.observables.items()
    }
    constraint_functions = {
        name: sp.lambdify(numeric_args, expression, modules="numpy")
        for name, expression in system.constraint_residuals.items()
    }
    coordinate_count = len(system.coordinate_symbols)
    condition_numbers: list[float] = []

    def arguments_for_state(state):
        coordinates = tuple(float(value) for value in state[:coordinate_count])
        speeds = tuple(float(value) for value in state[coordinate_count:])
        return (*coordinates, *speeds, *parameter_values)

    def mass_and_forcing(state):
        arguments = arguments_for_state(state)
        mass = np.asarray(mass_function(*arguments), dtype=float).reshape(
            (coordinate_count, coordinate_count)
        )
        forcing = np.asarray(
            forcing_function(*arguments),
            dtype=float,
        ).reshape((coordinate_count,))
        if not np.all(np.isfinite(mass)) or not np.all(np.isfinite(forcing)):
            raise _NonfiniteNumericError(
                "mass matrix or forcing became non-finite"
            )
        try:
            condition = float(np.linalg.cond(mass))
        except np.linalg.LinAlgError as exc:
            raise _SingularMassMatrixError(
                f"mass matrix conditioning failed: {exc}"
            ) from exc
        condition_numbers.append(condition)
        if (
            not math.isfinite(condition)
            or condition > policy.singular_condition_threshold
        ):
            raise _SingularMassMatrixError(
                f"mass matrix condition {condition!r} exceeds policy"
            )
        return mass, forcing

    def first_order_rhs(_time, state):
        mass, forcing = mass_and_forcing(state)
        try:
            accelerations = np.linalg.solve(mass, forcing)
        except np.linalg.LinAlgError as exc:
            raise _SingularMassMatrixError(
                f"mass matrix solve failed: {exc}"
            ) from exc
        derivative = np.concatenate(
            (
                np.asarray(state[coordinate_count:], dtype=float),
                np.asarray(accelerations, dtype=float),
            )
        )
        if not np.all(np.isfinite(derivative)):
            raise _NonfiniteNumericError(
                "first-order derivative became non-finite"
            )
        return derivative

    try:
        mass_and_forcing(spec.initial_state)
    except _SingularMassMatrixError as exc:
        return _failure_result(
            spec,
            SimulationStatus.SINGULAR_MASS_MATRIX,
            str(exc),
        )
    except _NonfiniteNumericError as exc:
        return _failure_result(
            spec,
            SimulationStatus.NONFINITE_OUTPUT,
            str(exc),
        )

    event_functions = []
    for event in spec.events:
        state_index = system.state_variables.index(event.state_variable)

        def make_event(index, event_spec):
            def event_function(_time, state):
                return float(state[index]) - float(event_spec.threshold)

            event_function.terminal = bool(event_spec.terminal)
            event_function.direction = float(event_spec.direction)
            return event_function

        event_functions.append(make_event(state_index, event))

    try:
        solution = solve_ivp_impl(
            first_order_rhs,
            (float(spec.t_start), float(spec.t_end)),
            np.asarray(spec.initial_state, dtype=float),
            t_eval=np.asarray(spec.evaluation_grid, dtype=float),
            method=spec.integration_method,
            rtol=float(spec.rtol),
            atol=float(spec.atol),
            max_step=float(spec.max_step),
            events=event_functions or None,
        )
    except _SingularMassMatrixError as exc:
        return _failure_result(
            spec,
            SimulationStatus.SINGULAR_MASS_MATRIX,
            str(exc),
        )
    except _NonfiniteNumericError as exc:
        return _failure_result(
            spec,
            SimulationStatus.NONFINITE_OUTPUT,
            str(exc),
        )
    except Exception as exc:
        return _failure_result(
            spec,
            SimulationStatus.INTEGRATION_FAILED,
            f"solve_ivp raised {type(exc).__name__}: {exc}",
        )

    base_diagnostics = {
        "spec": spec.to_dict(),
        "typed_model": typed_model_summary(system.typed_model),
        "symbolic_system": system.summary(),
        "integration_method": spec.integration_method,
        "rtol": float(spec.rtol),
        "atol": float(spec.atol),
        "max_step": float(spec.max_step),
        "random_seed": spec.random_seed,
        "sympy_version": str(sp.__version__),
        "scipy_version": str(scipy_version or "unknown"),
        "numpy_version": str(getattr(np, "__version__", "unknown")),
        "success": bool(getattr(solution, "success", False)),
        "message": str(getattr(solution, "message", "")),
        "solver_status": int(getattr(solution, "status", -1)),
        "nfev": int(getattr(solution, "nfev", 0)),
        "njev": int(getattr(solution, "njev", 0) or 0),
        "nlu": int(getattr(solution, "nlu", 0) or 0),
        "requested_sample_count": len(spec.evaluation_grid),
        "mass_matrix_condition_max": (
            max(condition_numbers) if condition_numbers else None
        ),
        "safety_policy": policy.to_dict(),
        "offline_only": True,
        "student_answer_overwrite": False,
    }
    if not getattr(solution, "success", False):
        return _failure_result(
            spec,
            SimulationStatus.INTEGRATION_FAILED,
            str(getattr(solution, "message", "solve_ivp reported failure")),
            diagnostics=base_diagnostics,
        )

    time_values = np.asarray(solution.t, dtype=float)
    state_matrix = np.asarray(solution.y, dtype=float)
    if (
        time_values.ndim != 1
        or state_matrix.shape
        != (len(system.state_variables), len(time_values))
    ):
        return _failure_result(
            spec,
            SimulationStatus.INTEGRATION_FAILED,
            "solve_ivp returned an unexpected trajectory shape",
            diagnostics=base_diagnostics,
        )
    if not np.all(np.isfinite(time_values)) or not np.all(
        np.isfinite(state_matrix)
    ):
        return _failure_result(
            spec,
            SimulationStatus.NONFINITE_OUTPUT,
            "solve_ivp returned NaN or infinity",
            diagnostics=base_diagnostics,
        )
    if state_matrix.size and float(np.max(np.abs(state_matrix))) > (
        policy.runaway_absolute_limit
    ):
        return _failure_result(
            spec,
            SimulationStatus.RUNAWAY_STATE,
            "trajectory exceeded the runaway state limit",
            diagnostics=base_diagnostics,
        )

    state_series = {
        name: tuple(float(value) for value in state_matrix[index])
        for index, name in enumerate(system.state_variables)
    }
    trajectory = NumericTrajectory(
        time=tuple(float(value) for value in time_values),
        states=state_series,
        state_units=system.state_units,
    )
    vector_arguments = (
        *(
            state_matrix[index]
            for index in range(len(system.state_variables))
        ),
        *parameter_values,
    )
    try:
        observables = {
            name: _as_finite_series(
                function(*vector_arguments),
                len(time_values),
                np,
                f"observable {name}",
            )
            for name, function in observable_functions.items()
        }
        energy_values = _as_finite_series(
            energy_function(*vector_arguments),
            len(time_values),
            np,
            "energy",
        )
        invariant_drift, invariant_warnings = _invariant_diagnostics(
            spec,
            energy_values,
            policy,
            np,
        )
        constraint_violation, constraint_warnings = _constraint_diagnostics(
            constraint_functions,
            vector_arguments,
            len(time_values),
            policy,
            np,
        )
        analytic_error = _analytic_diagnostics(
            spec,
            time_values,
            state_matrix,
            policy,
            np,
        )
    except _NonfiniteNumericError as exc:
        return _failure_result(
            spec,
            SimulationStatus.NONFINITE_OUTPUT,
            str(exc),
            diagnostics=base_diagnostics,
        )
    except Exception as exc:
        return _failure_result(
            spec,
            SimulationStatus.INTERNAL_ERROR,
            f"numeric diagnostics raised {type(exc).__name__}: {exc}",
            diagnostics=base_diagnostics,
        )
    analytic_warnings: list[str] = []
    if (
        analytic_error.get("applicable")
        and not bool(analytic_error.get("passed"))
    ):
        analytic_warnings.append("analytic_error_exceeds_policy")

    event_records: dict[str, Any] = {}
    raw_event_times = list(getattr(solution, "t_events", []) or [])
    for index, event in enumerate(spec.events):
        values = (
            raw_event_times[index]
            if index < len(raw_event_times)
            else ()
        )
        try:
            finite_values = _as_finite_series(
                values,
                len(values),
                np,
                f"event {event.event_id}",
            )
        except _NonfiniteNumericError as exc:
            return _failure_result(
                spec,
                SimulationStatus.NONFINITE_OUTPUT,
                str(exc),
                diagnostics=base_diagnostics,
            )
        event_records[event.event_id] = {
            **event.to_dict(),
            "times": finite_values,
            "count": len(finite_values),
        }

    warnings = [
        *invariant_warnings,
        *constraint_warnings,
        *analytic_warnings,
    ]
    nfev = int(getattr(solution, "nfev", 0))
    samples = max(len(time_values), 1)
    if nfev / samples > policy.stiffness_nfev_per_sample_warning:
        warnings.append("stiffness_warning_high_evaluation_density")
    stiffness_ratio = _stiffness_ratio(spec)
    if stiffness_ratio > policy.stiffness_ratio_warning:
        warnings.append("stiffness_warning_parameter_ratio")

    base_diagnostics.update(
        {
            "returned_sample_count": len(time_values),
            "event_count": sum(
                record["count"] for record in event_records.values()
            ),
            "stiffness_ratio": stiffness_ratio,
        }
    )
    status = (
        SimulationStatus.COMPLETED_WITH_WARNINGS
        if warnings
        else SimulationStatus.COMPLETED
    )
    return NumericSimulationResult(
        model_id=spec.model_id,
        model_version=spec.model_version,
        status=status,
        trajectory=trajectory,
        observables=observables,
        solver_diagnostics=base_diagnostics,
        invariant_drift=invariant_drift,
        constraint_violation=constraint_violation,
        analytic_error=analytic_error,
        events=event_records,
        warnings=tuple(dict.fromkeys(warnings)),
        safety_policy_version=policy.policy_version,
    )


def _as_finite_series(value, count: int, np, label: str) -> list[float]:
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        array = np.full(count, float(array), dtype=float)
    else:
        array = np.ravel(array)
        if len(array) == 1 and count != 1:
            array = np.full(count, float(array[0]), dtype=float)
    if len(array) != count:
        raise _NonfiniteNumericError(
            f"{label} returned {len(array)} values for {count} samples"
        )
    if not np.all(np.isfinite(array)):
        raise _NonfiniteNumericError(f"{label} became non-finite")
    return [float(item) for item in array]


def _finite_scalar(value: Any, label: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _NonfiniteNumericError(
            f"{label} is not a finite numeric value"
        ) from exc
    if not math.isfinite(numeric):
        raise _NonfiniteNumericError(f"{label} became non-finite")
    return numeric


def _finite_rms(values, np, label: str) -> float:
    absolute_max = _finite_scalar(np.max(np.abs(values)), f"{label} maximum")
    if absolute_max == 0.0:
        return 0.0
    normalized = values / absolute_max
    rms = absolute_max * math.sqrt(float(np.mean(normalized**2)))
    return _finite_scalar(rms, f"{label} RMS")


def _invariant_diagnostics(
    spec: NumericSimulationSpec,
    energy_values: list[float],
    policy: NumericSafetyPolicy,
    np,
) -> tuple[dict[str, Any], list[str]]:
    energy = np.asarray(energy_values, dtype=float)
    initial = float(energy[0])
    final = float(energy[-1])
    scale = _finite_scalar(
        max(float(np.max(np.abs(energy))), abs(initial)),
        "energy reference scale",
    )
    with np.errstate(over="ignore", invalid="ignore"):
        drift = energy - initial
    if not np.all(np.isfinite(drift)):
        raise _NonfiniteNumericError("energy drift became non-finite")
    max_abs_drift = _finite_scalar(
        np.max(np.abs(drift)),
        "maximum energy drift",
    )
    combined_tolerance = _finite_scalar(
        policy.energy_absolute_drift_warning
        + policy.energy_relative_drift_warning * scale,
        "energy comparison tolerance",
    )
    relative_drift = _finite_scalar(
        max_abs_drift
        / max(scale, policy.energy_absolute_drift_warning),
        "relative energy drift",
    )
    warnings: list[str] = []
    if (
        spec.model_id == "mass_spring_damper"
        and float(spec.parameters["c"]) > 0.0
    ):
        with np.errstate(over="ignore", invalid="ignore"):
            increments = np.diff(energy)
        if not np.all(np.isfinite(increments)):
            raise _NonfiniteNumericError("energy increments became non-finite")
        max_increase = (
            max(_finite_scalar(np.max(increments), "energy step increase"), 0.0)
            if len(increments)
            else 0.0
        )
        relative_increase = _finite_scalar(
            max_increase
            / max(scale, policy.energy_absolute_drift_warning),
            "relative energy step increase",
        )
        if max_increase > combined_tolerance:
            warnings.append("damped_energy_increase_exceeds_policy")
        return (
            {
                "invariant": "mechanical_energy",
                "expected_behavior": "nonincreasing",
                "initial": initial,
                "final": final,
                "max_abs_drift_from_initial": max_abs_drift,
                "relative_drift_from_initial": relative_drift,
                "max_step_increase": max_increase,
                "relative_step_increase": relative_increase,
                "reference_scale": scale,
                "combined_tolerance": combined_tolerance,
                "passed": max_increase <= combined_tolerance,
            },
            warnings,
        )
    if max_abs_drift > combined_tolerance:
        warnings.append("energy_drift_exceeds_policy")
    return (
        {
            "invariant": "mechanical_energy",
            "expected_behavior": "conserved",
            "initial": initial,
            "final": final,
            "max_abs_drift": max_abs_drift,
            "relative_drift": relative_drift,
            "reference_scale": scale,
            "combined_tolerance": combined_tolerance,
            "passed": max_abs_drift <= combined_tolerance,
        },
        warnings,
    )


def _constraint_diagnostics(
    functions: dict[str, Callable[..., Any]],
    vector_arguments: tuple[Any, ...],
    count: int,
    policy: NumericSafetyPolicy,
    np,
) -> tuple[dict[str, Any], list[str]]:
    if not functions:
        return (
            {
                "applicable": False,
                "checks": {},
                "max_abs_violation": 0.0,
                "passed": True,
            },
            [],
        )
    checks: dict[str, Any] = {}
    maximum = 0.0
    for name, function in functions.items():
        values = _as_finite_series(
            function(*vector_arguments),
            count,
            np,
            f"constraint {name}",
        )
        max_abs = max((abs(value) for value in values), default=0.0)
        maximum = max(maximum, max_abs)
        checks[name] = {
            "max_abs_violation": max_abs,
            "passed": max_abs <= policy.constraint_absolute_warning,
        }
    passed = maximum <= policy.constraint_absolute_warning
    warnings = [] if passed else ["constraint_violation_exceeds_policy"]
    return (
        {
            "applicable": True,
            "checks": checks,
            "max_abs_violation": maximum,
            "passed": passed,
        },
        warnings,
    )


def _analytic_diagnostics(
    spec: NumericSimulationSpec,
    time_values,
    state_matrix,
    policy: NumericSafetyPolicy,
    np,
) -> dict[str, Any]:
    relative_time = time_values - float(spec.t_start)
    position = state_matrix[0]
    initial_position = float(spec.initial_state[0])
    initial_speed = float(spec.initial_state[1])
    if spec.model_id == "simple_pendulum":
        length = float(spec.parameters["L"])
        gravity = float(spec.parameters["g"])
        omega = _finite_scalar(
            math.sqrt(gravity / length),
            "pendulum analytic angular frequency",
        )
        if omega == 0.0:
            raise _NonfiniteNumericError(
                "pendulum analytic angular frequency underflowed to zero"
            )
        with np.errstate(over="ignore", invalid="ignore"):
            analytic = (
                initial_position * np.cos(omega * relative_time)
                + (initial_speed / omega) * np.sin(omega * relative_time)
            )
        analytic = np.asarray(
            _as_finite_series(
                analytic,
                len(time_values),
                np,
                "pendulum analytic reference",
            ),
            dtype=float,
        )
        error = np.asarray(
            _as_finite_series(
                position - analytic,
                len(time_values),
                np,
                "pendulum analytic error",
            ),
            dtype=float,
        )
        max_abs_error = _finite_scalar(
            np.max(np.abs(error)),
            "pendulum maximum analytic error",
        )
        reference_scale = _finite_scalar(
            max(
                float(np.max(np.abs(analytic))),
                float(np.max(np.abs(position))),
            ),
            "pendulum analytic reference scale",
        )
        comparison_tolerance = _finite_scalar(
            policy.analytic_absolute_warning
            + policy.analytic_relative_warning * reference_scale,
            "pendulum analytic comparison tolerance",
        )
        analytic_period = _finite_scalar(
            2.0 * math.pi / omega,
            "pendulum analytic period",
        )
        observed_period = _estimate_period(time_values, position)
        if observed_period is not None:
            observed_period = _finite_scalar(
                observed_period,
                "pendulum observed period",
            )
        period_relative_error = (
            _finite_scalar(
                abs(observed_period - analytic_period) / analytic_period,
                "pendulum period relative error",
            )
            if observed_period is not None
            else None
        )
        max_abs_angle = _finite_scalar(
            np.max(np.abs(position)),
            "pendulum maximum trajectory angle",
        )
        small_angle = max_abs_angle <= policy.pendulum_small_angle_limit_rad
        return {
            "reference": "small_angle_linearized_pendulum",
            "applicable": small_angle,
            "expected_large_angle_difference": not small_angle,
            "max_abs_error": max_abs_error,
            "rms_error": _finite_rms(error, np, "pendulum analytic error"),
            "reference_scale": reference_scale,
            "comparison_tolerance": comparison_tolerance,
            "passed": max_abs_error <= comparison_tolerance,
            "analytic_period": analytic_period,
            "observed_period": observed_period,
            "period_relative_error": period_relative_error,
            "angle_limit_rad": policy.pendulum_small_angle_limit_rad,
            "max_abs_angle": max_abs_angle,
        }

    mass = float(spec.parameters["m"])
    stiffness = float(spec.parameters["k"])
    damping = float(spec.parameters["c"])
    try:
        with np.errstate(
            divide="ignore",
            invalid="ignore",
            over="ignore",
            under="ignore",
        ):
            analytic, regime = _mass_spring_analytic(
                relative_time,
                initial_position,
                initial_speed,
                mass,
                stiffness,
                damping,
                np,
            )
    except ArithmeticError as exc:
        raise _NonfiniteNumericError(
            f"mass-spring analytic reference became non-finite: {exc}"
        ) from exc
    analytic = np.asarray(
        _as_finite_series(
            analytic,
            len(time_values),
            np,
            "mass-spring analytic reference",
        ),
        dtype=float,
    )
    error = np.asarray(
        _as_finite_series(
            position - analytic,
            len(time_values),
            np,
            "mass-spring analytic error",
        ),
        dtype=float,
    )
    max_abs_error = _finite_scalar(
        np.max(np.abs(error)),
        "mass-spring maximum analytic error",
    )
    reference_scale = _finite_scalar(
        max(
            float(np.max(np.abs(analytic))),
            float(np.max(np.abs(position))),
        ),
        "mass-spring analytic reference scale",
    )
    comparison_tolerance = _finite_scalar(
        policy.analytic_absolute_warning
        + policy.analytic_relative_warning * reference_scale,
        "mass-spring analytic comparison tolerance",
    )
    natural_frequency = _finite_scalar(
        math.sqrt(stiffness / mass),
        "mass-spring natural angular frequency",
    )
    damping_ratio = _finite_scalar(
        damping / (2.0 * math.sqrt(stiffness * mass)),
        "mass-spring damping ratio",
    )
    return {
        "reference": "homogeneous_mass_spring_damper",
        "applicable": True,
        "damping_regime": regime,
        "max_abs_error": max_abs_error,
        "rms_error": _finite_rms(error, np, "mass-spring analytic error"),
        "reference_scale": reference_scale,
        "comparison_tolerance": comparison_tolerance,
        "passed": max_abs_error <= comparison_tolerance,
        "natural_angular_frequency": natural_frequency,
        "damping_ratio": damping_ratio,
    }


def _mass_spring_analytic(
    time_values,
    x0: float,
    v0: float,
    mass: float,
    stiffness: float,
    damping: float,
    np,
):
    natural = math.sqrt(stiffness / mass)
    alpha = damping / (2.0 * mass)
    discriminant = damping**2 - 4.0 * mass * stiffness
    threshold = 1e-12 * max(
        damping**2,
        4.0 * mass * stiffness,
        1.0,
    )
    if discriminant < -threshold:
        damped = math.sqrt(natural**2 - alpha**2)
        coefficient = (v0 + alpha * x0) / damped
        values = np.exp(-alpha * time_values) * (
            x0 * np.cos(damped * time_values)
            + coefficient * np.sin(damped * time_values)
        )
        return values, "underdamped"
    if abs(discriminant) <= threshold:
        values = np.exp(-natural * time_values) * (
            x0 + (v0 + natural * x0) * time_values
        )
        return values, "critical"
    root = math.sqrt(discriminant)
    r1 = (-damping + root) / (2.0 * mass)
    r2 = (-damping - root) / (2.0 * mass)
    first = (v0 - r2 * x0) / (r1 - r2)
    second = (r1 * x0 - v0) / (r1 - r2)
    values = first * np.exp(r1 * time_values) + second * np.exp(
        r2 * time_values
    )
    return values, "overdamped"


def _estimate_period(time_values, values) -> float | None:
    if len(values) < 2 or max(abs(float(value)) for value in values) == 0.0:
        return None
    crossings: list[float] = []
    for index in range(len(values) - 1):
        left = float(values[index])
        right = float(values[index + 1])
        if left == 0.0:
            crossings.append(float(time_values[index]))
            continue
        if left * right < 0.0:
            fraction = abs(left) / (abs(left) + abs(right))
            crossings.append(
                float(time_values[index])
                + fraction
                * float(time_values[index + 1] - time_values[index])
            )
    if len(crossings) < 2:
        return None
    half_periods = [
        right - left for left, right in zip(crossings, crossings[1:])
    ]
    return 2.0 * sum(half_periods) / len(half_periods)


def _stiffness_ratio(spec: NumericSimulationSpec) -> float:
    if spec.model_id != "mass_spring_damper":
        return 0.0
    mass = float(spec.parameters["m"])
    stiffness = float(spec.parameters["k"])
    damping = float(spec.parameters["c"])
    return damping**2 / (mass * stiffness)


__all__ = [
    "SUPPORTED_INTEGRATION_METHODS",
    "run_numeric_system",
    "simulate_numeric",
    "validate_simulation_spec",
]
