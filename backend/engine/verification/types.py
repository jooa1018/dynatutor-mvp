from __future__ import annotations

"""Typed verification check contracts shared by the engine and API layer."""

from dataclasses import dataclass, field
from enum import Enum
import math
from types import MappingProxyType
from typing import Any, Mapping


class VerificationStatus(str, Enum):
    PASSED = "passed"
    PASSED_WITH_WARNING = "passed_with_warning"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"
    ERROR = "error"


class VerificationApplicability(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    CONDITIONAL = "conditional"
    UNDETERMINED = "undetermined"


def _json_safe(value: Any) -> Any:
    """Convert diagnostic values to JSON-safe, deterministic primitives."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except (TypeError, ValueError):
            pass
    return str(value)


@dataclass(frozen=True)
class VerificationCheck:
    check_id: str
    category: str
    status: VerificationStatus
    applicability: VerificationApplicability
    observed: Any = None
    expected: Any = None
    absolute_error: float | None = None
    relative_error: float | None = None
    tolerance: float | None = None
    message: str = ""
    evidence: tuple[str, ...] = ()
    source_equation_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not self.check_id.strip():
            raise ValueError("check_id must be a non-empty string")
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("category must be a non-empty string")
        if not isinstance(self.status, VerificationStatus):
            object.__setattr__(self, "status", VerificationStatus(self.status))
        if not isinstance(self.applicability, VerificationApplicability):
            object.__setattr__(
                self,
                "applicability",
                VerificationApplicability(self.applicability),
            )
        for name in ("absolute_error", "relative_error", "tolerance"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number or None")
            object.__setattr__(self, name, float(value))
        object.__setattr__(self, "evidence", tuple(str(v) for v in self.evidence))
        object.__setattr__(
            self,
            "source_equation_ids",
            tuple(str(v) for v in self.source_equation_ids),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def passed(self) -> bool:
        return self.status in {
            VerificationStatus.PASSED,
            VerificationStatus.PASSED_WITH_WARNING,
        }

    @property
    def is_warning(self) -> bool:
        return self.status is VerificationStatus.PASSED_WITH_WARNING

    @property
    def is_blocking(self) -> bool:
        return self.status in {
            VerificationStatus.FAILED,
            VerificationStatus.ERROR,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "status": self.status.value,
            "applicability": self.applicability.value,
            "observed": _json_safe(self.observed),
            "expected": _json_safe(self.expected),
            "absolute_error": _json_safe(self.absolute_error),
            "relative_error": _json_safe(self.relative_error),
            "tolerance": _json_safe(self.tolerance),
            "message": self.message,
            "evidence": list(self.evidence),
            "source_equation_ids": list(self.source_equation_ids),
            "metadata": _json_safe(self.metadata),
        }


CheckStatus = VerificationStatus
CheckApplicability = VerificationApplicability


__all__ = [
    "CheckApplicability",
    "CheckStatus",
    "VerificationApplicability",
    "VerificationCheck",
    "VerificationStatus",
]
