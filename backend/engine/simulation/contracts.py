from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from types import MappingProxyType
from typing import Any, Mapping


SPEC_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 1
NUMERIC_POLICY_VERSION = "phase50-numeric-safety-v1"


class SimulationStatus:
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    INVALID_SPEC = "invalid_spec"
    UNSUPPORTED_MODEL = "unsupported_model"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    SINGULAR_MASS_MATRIX = "singular_mass_matrix"
    INTEGRATION_FAILED = "integration_failed"
    NONFINITE_OUTPUT = "nonfinite_output"
    RUNAWAY_STATE = "runaway_state"
    INTERNAL_ERROR = "internal_error"


SUCCESS_STATUSES = frozenset(
    {
        SimulationStatus.COMPLETED,
        SimulationStatus.COMPLETED_WITH_WARNINGS,
    }
)


@dataclass(frozen=True)
class NumericSafetyPolicy:
    policy_version: str = NUMERIC_POLICY_VERSION
    energy_relative_drift_warning: float = 1e-5
    constraint_absolute_warning: float = 1e-8
    analytic_absolute_warning: float = 1e-4
    runaway_absolute_limit: float = 1e6
    singular_condition_threshold: float = 1e14
    stiffness_ratio_warning: float = 100.0
    stiffness_nfev_per_sample_warning: float = 50.0
    pendulum_small_angle_limit_rad: float = 0.2

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        for name, raw_value in asdict(self).items():
            if name == "policy_version":
                continue
            value = float(raw_value)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be a positive finite number")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_NUMERIC_SAFETY_POLICY = NumericSafetyPolicy()


@dataclass(frozen=True)
class NumericEventSpec:
    event_id: str
    state_variable: str
    threshold: float = 0.0
    direction: int = 0
    terminal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "state_variable": self.state_variable,
            "threshold": _finite_or_none(self.threshold),
            "direction": self.direction,
            "terminal": self.terminal,
        }


@dataclass(frozen=True)
class NumericSimulationSpec:
    model_id: str
    model_version: str
    state_variables: tuple[str, ...]
    state_units: Mapping[str, str]
    parameters: Mapping[str, float]
    parameter_units: Mapping[str, str]
    initial_state: tuple[float, ...]
    t_start: float
    t_end: float
    evaluation_grid: tuple[float, ...]
    integration_method: str = "DOP853"
    rtol: float = 1e-9
    atol: float = 1e-11
    max_step: float = 0.05
    events: tuple[NumericEventSpec, ...] = ()
    random_seed: int | None = None
    schema_version: int = SPEC_SCHEMA_VERSION
    safety_policy_version: str = NUMERIC_POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_variables", tuple(self.state_variables))
        object.__setattr__(self, "state_units", MappingProxyType(dict(self.state_units)))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(
            self,
            "parameter_units",
            MappingProxyType(dict(self.parameter_units)),
        )
        object.__setattr__(self, "initial_state", tuple(self.initial_state))
        object.__setattr__(self, "evaluation_grid", tuple(self.evaluation_grid))
        object.__setattr__(self, "events", tuple(self.events))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "state_variables": list(self.state_variables),
            "state_units": dict(self.state_units),
            "parameters": {
                key: _finite_or_none(value)
                for key, value in self.parameters.items()
            },
            "parameter_units": dict(self.parameter_units),
            "initial_state": [_finite_or_none(value) for value in self.initial_state],
            "t_start": _finite_or_none(self.t_start),
            "t_end": _finite_or_none(self.t_end),
            "evaluation_grid": [
                _finite_or_none(value) for value in self.evaluation_grid
            ],
            "integration_method": self.integration_method,
            "rtol": _finite_or_none(self.rtol),
            "atol": _finite_or_none(self.atol),
            "max_step": _finite_or_none(self.max_step),
            "events": [event.to_dict() for event in self.events],
            "random_seed": self.random_seed,
            "safety_policy_version": self.safety_policy_version,
        }


@dataclass(frozen=True)
class NumericTrajectory:
    time: tuple[float, ...]
    states: Mapping[str, tuple[float, ...]]
    state_units: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "time", tuple(float(value) for value in self.time))
        object.__setattr__(
            self,
            "states",
            MappingProxyType(
                {
                    key: tuple(float(value) for value in values)
                    for key, values in self.states.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "state_units",
            MappingProxyType(dict(self.state_units)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": [_finite_or_none(value) for value in self.time],
            "states": {
                key: [_finite_or_none(value) for value in values]
                for key, values in self.states.items()
            },
            "state_units": dict(self.state_units),
        }


@dataclass(frozen=True)
class NumericSimulationResult:
    model_id: str
    model_version: str
    status: str
    trajectory: NumericTrajectory | None = None
    observables: Mapping[str, Any] = field(default_factory=dict)
    solver_diagnostics: Mapping[str, Any] = field(default_factory=dict)
    invariant_drift: Mapping[str, Any] = field(default_factory=dict)
    constraint_violation: Mapping[str, Any] = field(default_factory=dict)
    analytic_error: Mapping[str, Any] = field(default_factory=dict)
    events: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    schema_version: int = RESULT_SCHEMA_VERSION
    safety_policy_version: str = NUMERIC_POLICY_VERSION

    @property
    def passed(self) -> bool:
        return self.status in SUCCESS_STATUSES

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "status": self.status,
            "passed": self.passed,
            "trajectory": self.trajectory.to_dict() if self.trajectory else None,
            "observables": _json_safe(self.observables),
            "solver_diagnostics": _json_safe(self.solver_diagnostics),
            "invariant_drift": _json_safe(self.invariant_drift),
            "constraint_violation": _json_safe(self.constraint_violation),
            "analytic_error": _json_safe(self.analytic_error),
            "events": _json_safe(self.events),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "safety_policy_version": self.safety_policy_version,
        }
        return _json_safe(payload)


def _finite_or_none(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return _finite_or_none(value)


__all__ = [
    "DEFAULT_NUMERIC_SAFETY_POLICY",
    "NUMERIC_POLICY_VERSION",
    "NumericEventSpec",
    "NumericSafetyPolicy",
    "NumericSimulationResult",
    "NumericSimulationSpec",
    "NumericTrajectory",
    "RESULT_SCHEMA_VERSION",
    "SPEC_SCHEMA_VERSION",
    "SUCCESS_STATUSES",
    "SimulationStatus",
]
