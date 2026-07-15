from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from types import MappingProxyType
from typing import Any, Mapping


CHRONO_RESULT_SCHEMA_VERSION = 1
CHRONO_SUITE_VERSION = "phase51-pychrono-validation-v1"
CHRONO_POLICY_VERSION = "phase51-pychrono-policy-v1"
CHRONO_SUCCESS_STATUS = "passed"
CHRONO_STATUSES = frozenset({"passed", "failed", "skipped", "error"})


@dataclass(frozen=True)
class ChronoValidationPolicy:
    policy_version: str = CHRONO_POLICY_VERSION
    solver: str = "PSOR"
    solver_max_iterations: int = 200
    contact_method: str = "NSC"
    rolling_step_s: float = 0.0005
    rolling_max_duration_s: float = 3.0
    incline_step_s: float = 0.0005
    incline_duration_s: float = 0.8
    collision_step_s: float = 0.0001
    collision_duration_s: float = 0.25
    pulley_step_s: float = 0.001
    pulley_duration_s: float = 0.5
    rolling_speed_abs_tolerance: float = 0.03
    rolling_speed_rel_tolerance: float = 0.01
    rolling_no_slip_abs_tolerance: float = 0.03
    rolling_contact_abs_tolerance: float = 0.004
    rolling_energy_rel_tolerance: float = 0.02
    rolling_inertia_ratio_abs_tolerance: float = 1e-6
    incline_acceleration_abs_tolerance: float = 0.05
    incline_acceleration_rel_tolerance: float = 0.02
    incline_contact_abs_tolerance: float = 0.004
    incline_normal_force_rel_tolerance: float = 0.04
    incline_fit_residual_abs_tolerance: float = 0.03
    collision_velocity_abs_tolerance: float = 0.05
    collision_velocity_rel_tolerance: float = 0.01
    collision_momentum_rel_tolerance: float = 0.001
    collision_restitution_abs_tolerance: float = 0.02
    collision_event_time_abs_tolerance: float = 0.003
    pulley_acceleration_abs_tolerance: float = 0.005
    pulley_acceleration_rel_tolerance: float = 0.005
    pulley_constraint_abs_tolerance: float = 1e-8
    pulley_energy_rel_tolerance: float = 1e-4
    pulley_tension_abs_tolerance: float = 0.01

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.solver != "PSOR":
            raise ValueError("Phase 51 fixes the solver to PSOR")
        if self.contact_method != "NSC":
            raise ValueError("Phase 51 fixes rigid-body contact to NSC")
        if isinstance(self.solver_max_iterations, bool) or self.solver_max_iterations <= 0:
            raise ValueError("solver_max_iterations must be a positive integer")
        for name, raw_value in asdict(self).items():
            if name in {"policy_version", "solver", "contact_method", "solver_max_iterations"}:
                continue
            value = float(raw_value)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be a positive finite number")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CHRONO_POLICY = ChronoValidationPolicy()


@dataclass(frozen=True)
class ChronoResult:
    case_id: str
    status: str
    observable: str
    value: float | None
    unit: str
    chrono_version: str
    solver: str
    contact_method: str
    time_step: float
    duration: float
    initial_conditions: Mapping[str, Any] = field(default_factory=dict)
    final_state: Mapping[str, Any] = field(default_factory=dict)
    constraint_errors: Mapping[str, Any] = field(default_factory=dict)
    invariant_errors: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    artifacts: tuple[Mapping[str, Any], ...] = ()
    analytic_value: float | None = None
    abs_error: float | None = None
    relative_error: float | None = None
    modeling_assumptions: tuple[str, ...] = ()
    policy_version: str = CHRONO_POLICY_VERSION
    suite_version: str = CHRONO_SUITE_VERSION
    schema_version: int = CHRONO_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must be non-empty")
        if self.status not in CHRONO_STATUSES:
            raise ValueError(f"unsupported Chrono status: {self.status}")
        for name in (
            "observable",
            "unit",
            "chrono_version",
            "solver",
            "contact_method",
            "policy_version",
            "suite_version",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.schema_version != CHRONO_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported Chrono result schema version")
        for name in ("time_step", "duration"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, value)
        for name in ("value", "analytic_value", "abs_error", "relative_error"):
            raw = getattr(self, name)
            if raw is None:
                continue
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite when present")
            if name in {"abs_error", "relative_error"} and value < 0.0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        if self.status in {"passed", "failed"} and self.value is None:
            raise ValueError("executed Chrono results require a numeric value")
        if self.status in {"skipped", "error"} and self.value is not None:
            raise ValueError("skipped/error Chrono results cannot claim a value")

        for name in (
            "initial_conditions",
            "final_state",
            "constraint_errors",
            "invariant_errors",
        ):
            raw = _json_safe(dict(getattr(self, name)))
            object.__setattr__(self, name, MappingProxyType(raw))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        object.__setattr__(
            self,
            "artifacts",
            tuple(MappingProxyType(_json_safe(dict(item))) for item in self.artifacts),
        )
        object.__setattr__(
            self,
            "modeling_assumptions",
            tuple(str(item) for item in self.modeling_assumptions),
        )

    @property
    def passed(self) -> bool:
        return self.status == CHRONO_SUCCESS_STATUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_version": self.suite_version,
            "policy_version": self.policy_version,
            "case_id": self.case_id,
            "status": self.status,
            "passed": self.passed,
            "observable": self.observable,
            "value": self.value,
            "unit": self.unit,
            "analytic_value": self.analytic_value,
            "abs_error": self.abs_error,
            "relative_error": self.relative_error,
            "chrono_version": self.chrono_version,
            "solver": self.solver,
            "contact_method": self.contact_method,
            "time_step": self.time_step,
            "duration": self.duration,
            "initial_conditions": dict(self.initial_conditions),
            "final_state": dict(self.final_state),
            "constraint_errors": dict(self.constraint_errors),
            "invariant_errors": dict(self.invariant_errors),
            "modeling_assumptions": list(self.modeling_assumptions),
            "warnings": list(self.warnings),
            "artifacts": [dict(item) for item in self.artifacts],
        }


def comparison_errors(observed: float, expected: float) -> tuple[float, float]:
    observed = _finite_float(observed, name="observed")
    expected = _finite_float(expected, name="expected")
    absolute = abs(observed - expected)
    relative = absolute / max(abs(expected), 1e-12)
    return absolute, relative


def comparison_passed(
    observed: float,
    expected: float,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> bool:
    absolute, relative = comparison_errors(observed, expected)
    return absolute <= float(absolute_tolerance) or relative <= float(relative_tolerance)


def unavailable_result(
    *,
    case_id: str,
    observable: str,
    unit: str,
    time_step: float,
    duration: float,
    message: str,
    initial_conditions: Mapping[str, Any],
    contact_method: str | None = None,
) -> ChronoResult:
    return ChronoResult(
        case_id=case_id,
        status="skipped",
        observable=observable,
        value=None,
        unit=unit,
        chrono_version="unavailable",
        solver="not_initialized:PSOR_requested",
        contact_method=contact_method or DEFAULT_CHRONO_POLICY.contact_method,
        time_step=time_step,
        duration=duration,
        initial_conditions=initial_conditions,
        warnings=(message,),
        artifacts=(),
        modeling_assumptions=(
            "PyChrono is an offline optional dependency and is never substituted with an analytic value.",
        ),
    )


def error_result(
    *,
    case_id: str,
    observable: str,
    unit: str,
    time_step: float,
    duration: float,
    message: str,
    initial_conditions: Mapping[str, Any],
    chrono_version: str = "unknown",
    solver: str | None = None,
    contact_method: str | None = None,
) -> ChronoResult:
    return ChronoResult(
        case_id=case_id,
        status="error",
        observable=observable,
        value=None,
        unit=unit,
        chrono_version=chrono_version,
        solver=solver or DEFAULT_CHRONO_POLICY.solver,
        contact_method=contact_method or DEFAULT_CHRONO_POLICY.contact_method,
        time_step=time_step,
        duration=duration,
        initial_conditions=initial_conditions,
        warnings=(message,),
        artifacts=(),
        modeling_assumptions=(
            "A failed Chrono scene is reported as error and never replaced by the analytic target.",
        ),
    )


def _finite_float(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not bool")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Chrono evidence cannot contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("Chrono evidence cannot contain NaN or infinity")
    return parsed


__all__ = [
    "CHRONO_POLICY_VERSION",
    "CHRONO_RESULT_SCHEMA_VERSION",
    "CHRONO_STATUSES",
    "CHRONO_SUITE_VERSION",
    "ChronoResult",
    "ChronoValidationPolicy",
    "DEFAULT_CHRONO_POLICY",
    "comparison_errors",
    "comparison_passed",
    "error_result",
    "unavailable_result",
]
