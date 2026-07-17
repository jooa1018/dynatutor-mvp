from __future__ import annotations

"""Stable, immutable JSON contracts shared by Phase 52 observability outputs."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any


TRACE_SCHEMA_VERSION = 1
TRACE_VERSION = "phase52-pipeline-trace-v1"
CROSS_ENGINE_REPORT_SCHEMA_VERSION = 1
CROSS_ENGINE_REPORT_VERSION = "phase52-cross-engine-report-v1"
PERFORMANCE_SCHEMA_VERSION = 1
PERFORMANCE_VERSION = "phase52-stage-performance-v1"
CANONICAL_SCHEMA_VERSION = "2.0"
LEGACY_MODEL_SCHEMA_VERSION = "phase14-physical-model-v1"
TYPED_MODEL_SCHEMA_VERSION = "phase45-typed-dynamics-model-v1"
SOLVER_PIPELINE_VERSION = "phase47-validated-candidate-v1"
BENCHMARK_VERSION = "phase52-cross-engine-benchmark-v1"

STATUS_VALUES = (
    "passed",
    "passed_with_warning",
    "disagreement",
    "inconclusive",
    "skipped",
    "unsupported",
    "error",
)

# Trace payloads are intentionally stricter than arbitrary application JSON.
# Besides the required raw fields, reject the other free-form fields that have
# historically carried problem text or human-readable extraction evidence.
FORBIDDEN_TRACE_KEYS = frozenset(
    {
        "raw_text",
        "normalized_text",
        "source_text",
        "matched_raw_text",
        "student_solution",
        "problem_text",
        "evidence",
        "reason",
        "question",
        "message",
        "description",
        "display",
        "label",
        "why",
        "explanation",
        "unsupported_reason",
    }
)


def _canonicalize(value: Any, *, enforce_privacy: bool, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path}")
        return value
    if isinstance(value, Mapping):
        canonical: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object key at {path} must be a string")
            if enforce_privacy and key.casefold() in FORBIDDEN_TRACE_KEYS:
                raise ValueError(f"forbidden trace key at {path}.{key}")
            canonical[key] = _canonicalize(
                item,
                enforce_privacy=enforce_privacy,
                path=f"{path}.{key}",
            )
        return {key: canonical[key] for key in sorted(canonical)}
    if isinstance(value, (list, tuple)):
        return [
            _canonicalize(item, enforce_privacy=enforce_privacy, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, (set, frozenset)):
        items = [
            _canonicalize(item, enforce_privacy=enforce_privacy, path=f"{path}[]")
            for item in value
        ]
        return sorted(
            items,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )
    raise TypeError(f"unsupported JSON value at {path}: {type(value).__name__}")


def stable_json_dumps(value: Any, *, enforce_privacy: bool = False) -> str:
    """Render JSON with stable ordering and strict finite-number validation."""

    canonical = _canonicalize(value, enforce_privacy=enforce_privacy, path="$")
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def deterministic_json(value: Any, *, enforce_privacy: bool = False) -> str:
    """Compatibility name for the Phase 52 deterministic JSON renderer."""

    return stable_json_dumps(value, enforce_privacy=enforce_privacy)


def sha256_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("sha256_text requires a string")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_sha256(value: Any, *, enforce_privacy: bool = False) -> str:
    return sha256_text(stable_json_dumps(value, enforce_privacy=enforce_privacy))


def validate_trace_core(value: Any) -> None:
    """Validate recursively without returning a mutable canonical structure."""

    stable_json_dumps(value, enforce_privacy=True)


@dataclass(frozen=True)
class StableSnapshot:
    """Immutable ownership boundary for a finalized deterministic payload."""

    _canonical_bytes: bytes = field(repr=False)
    digest: str

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        enforce_privacy: bool = True,
    ) -> "StableSnapshot":
        if not isinstance(payload, Mapping):
            raise TypeError("StableSnapshot payload must be a mapping")
        rendered = stable_json_dumps(payload, enforce_privacy=enforce_privacy)
        owned = rendered.encode("utf-8")
        return cls(
            _canonical_bytes=owned,
            digest=hashlib.sha256(owned).hexdigest(),
        )

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes

    @property
    def canonical_json(self) -> str:
        return self._canonical_bytes.decode("utf-8")

    @property
    def json(self) -> str:
        return self.canonical_json

    def render(self) -> str:
        return self.canonical_json

    def to_dict(self) -> dict[str, Any]:
        # json.loads necessarily creates a new object graph on every call.
        return json.loads(self._canonical_bytes)


__all__ = [
    "BENCHMARK_VERSION",
    "CANONICAL_SCHEMA_VERSION",
    "CROSS_ENGINE_REPORT_SCHEMA_VERSION",
    "CROSS_ENGINE_REPORT_VERSION",
    "FORBIDDEN_TRACE_KEYS",
    "LEGACY_MODEL_SCHEMA_VERSION",
    "PERFORMANCE_SCHEMA_VERSION",
    "PERFORMANCE_VERSION",
    "SOLVER_PIPELINE_VERSION",
    "STATUS_VALUES",
    "TRACE_SCHEMA_VERSION",
    "TRACE_VERSION",
    "TYPED_MODEL_SCHEMA_VERSION",
    "StableSnapshot",
    "deterministic_json",
    "sha256_text",
    "stable_json_dumps",
    "stable_sha256",
    "validate_trace_core",
]
