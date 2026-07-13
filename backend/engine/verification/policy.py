from __future__ import annotations

"""Central, versioned numerical tolerance policy for verification.

All Phase 48 verification code asks this object for a tolerance instead of
embedding local constants.  Engine overrides are immutable and deliberately
limited to named policy fields so a misspelled override cannot silently change
the verification contract.
"""

from dataclasses import dataclass, field, replace
import math
from types import MappingProxyType
from typing import Any, Mapping


POLICY_VERSION = "phase48-tolerance-policy-v1"
CANDIDATE_ENGINE_ID = "candidate"

_NUMERICAL_FIELDS = frozenset(
    {
        "abs_tol",
        "rel_tol",
        "residual_tol",
        "constraint_tol",
        "conservation_tol",
        "near_zero_tol",
        "root_separation_tol",
        "condition_warning_threshold",
        "sensitivity_warning_threshold",
    }
)


def _default_engine_tolerances() -> Mapping[str, Mapping[str, float]]:
    return {
        CANDIDATE_ENGINE_ID: {
            "abs_tol": 1e-9,
            "rel_tol": 1e-7,
            "residual_tol": 1e-9,
            "constraint_tol": 1e-9,
            "near_zero_tol": 1e-10,
        }
    }


@dataclass(frozen=True)
class TolerancePolicy:
    """One immutable source of truth for verification thresholds."""

    abs_tol: float = 1e-8
    rel_tol: float = 1e-4
    residual_tol: float = 1e-8
    constraint_tol: float = 1e-8
    conservation_tol: float = 1e-8
    near_zero_tol: float = 1e-9
    root_separation_tol: float = 1e-6
    condition_warning_threshold: float = 1e8
    sensitivity_warning_threshold: float = 1e6
    engine_specific_tolerances: Mapping[str, Mapping[str, float]] = field(
        default_factory=_default_engine_tolerances
    )
    policy_version: str = POLICY_VERSION

    def __post_init__(self) -> None:
        for name in _NUMERICAL_FIELDS:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number")
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if name.endswith("_threshold"):
                if value <= 0:
                    raise ValueError(f"{name} must be positive")
            elif value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)

        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")

        frozen_overrides: dict[str, Mapping[str, float]] = {}
        for engine_id, raw_overrides in self.engine_specific_tolerances.items():
            if not isinstance(engine_id, str) or not engine_id.strip():
                raise ValueError("engine override keys must be non-empty strings")
            values: dict[str, float] = {}
            for name, raw_value in raw_overrides.items():
                if name not in _NUMERICAL_FIELDS:
                    raise ValueError(
                        f"unknown tolerance override {name!r} for engine {engine_id!r}"
                    )
                if isinstance(raw_value, bool) or not isinstance(
                    raw_value, (int, float)
                ):
                    raise TypeError(
                        f"override {engine_id}.{name} must be a real number"
                    )
                value = float(raw_value)
                if not math.isfinite(value):
                    raise ValueError(f"override {engine_id}.{name} must be finite")
                if name.endswith("_threshold"):
                    if value <= 0:
                        raise ValueError(
                            f"override {engine_id}.{name} must be positive"
                        )
                elif value < 0:
                    raise ValueError(
                        f"override {engine_id}.{name} must be non-negative"
                    )
                values[name] = value
            frozen_overrides[engine_id] = MappingProxyType(values)
        object.__setattr__(
            self,
            "engine_specific_tolerances",
            MappingProxyType(frozen_overrides),
        )

    def for_engine(self, engine_id: str | None) -> "TolerancePolicy":
        """Return a policy view with the requested engine overrides applied."""

        if not engine_id:
            return self
        overrides = self.engine_specific_tolerances.get(engine_id)
        if not overrides:
            return self
        return replace(self, **dict(overrides))

    def threshold_for(self, category: str) -> float:
        """Return the absolute floor associated with a check category."""

        normalized = str(category).strip().lower()
        field_name = {
            "absolute": "abs_tol",
            "abs": "abs_tol",
            "residual": "residual_tol",
            "equation_residual": "residual_tol",
            "constraint": "constraint_tol",
            "model_constraint": "constraint_tol",
            "conservation": "conservation_tol",
            "near_zero": "near_zero_tol",
            "root_separation": "root_separation_tol",
        }.get(normalized)
        if field_name is None:
            raise ValueError(f"unknown tolerance category: {category!r}")
        return float(getattr(self, field_name))

    def tolerance(
        self,
        category: str,
        *,
        scale: float = 1.0,
        engine_id: str | None = None,
    ) -> float:
        """Return the absolute-plus-relative tolerance for a scaled value."""

        effective = self.for_engine(engine_id)
        try:
            numeric_scale = abs(float(scale))
        except (TypeError, ValueError) as exc:
            raise TypeError("scale must be a finite real number") from exc
        if not math.isfinite(numeric_scale):
            raise ValueError("scale must be finite")
        normalized_scale = max(numeric_scale, 1.0)
        return max(
            effective.threshold_for(category),
            effective.rel_tol * normalized_scale,
        )

    def is_near_zero(
        self,
        value: float,
        *,
        scale: float = 1.0,
        engine_id: str | None = None,
    ) -> bool:
        effective = self.for_engine(engine_id)
        numeric_value = float(value)
        numeric_scale = abs(float(scale))
        if not math.isfinite(numeric_value) or not math.isfinite(numeric_scale):
            return False
        return abs(numeric_value) <= effective.near_zero_tol * max(
            numeric_scale, 1.0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "abs_tol": self.abs_tol,
            "rel_tol": self.rel_tol,
            "residual_tol": self.residual_tol,
            "constraint_tol": self.constraint_tol,
            "conservation_tol": self.conservation_tol,
            "near_zero_tol": self.near_zero_tol,
            "root_separation_tol": self.root_separation_tol,
            "condition_warning_threshold": self.condition_warning_threshold,
            "sensitivity_warning_threshold": self.sensitivity_warning_threshold,
            "engine_specific_tolerances": {
                engine_id: dict(values)
                for engine_id, values in self.engine_specific_tolerances.items()
            },
        }


DEFAULT_TOLERANCE_POLICY = TolerancePolicy()


def get_tolerance_policy() -> TolerancePolicy:
    """Return the process-wide immutable default policy."""

    return DEFAULT_TOLERANCE_POLICY


__all__ = [
    "CANDIDATE_ENGINE_ID",
    "DEFAULT_TOLERANCE_POLICY",
    "POLICY_VERSION",
    "TolerancePolicy",
    "get_tolerance_policy",
]
