"""Privacy-safe, low-cardinality telemetry for Stage 6."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MultimodalMetricEvent:
    terminal: str
    image_count: int
    observation_count: int
    conflict_count: int
    confirmation_count: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "terminal": self.terminal,
            "image_count": self.image_count,
            "observation_count": self.observation_count,
            "conflict_count": self.conflict_count,
            "confirmation_count": self.confirmation_count,
        }


def build_multimodal_metric_event(
    *,
    terminal: Any,
    image_count: int,
    observation_count: int,
    conflict_count: int,
    confirmation_count: int,
) -> MultimodalMetricEvent:
    label = getattr(terminal, "value", terminal)
    if label not in {"ready", "confirmation_required", "blocked"}:
        label = "blocked"
    counts = (image_count, observation_count, conflict_count, confirmation_count)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts):
        raise ValueError("Metric counts must be non-negative integers.")
    return MultimodalMetricEvent(
        terminal=str(label),
        image_count=image_count,
        observation_count=observation_count,
        conflict_count=conflict_count,
        confirmation_count=confirmation_count,
    )


def audit_metric_payload(payload: Mapping[str, Any]) -> bool:
    """Reject accidental high-cardinality or source-bearing telemetry fields."""

    return set(payload) <= {
        "terminal",
        "image_count",
        "observation_count",
        "conflict_count",
        "confirmation_count",
    }


__all__ = ["MultimodalMetricEvent", "audit_metric_payload", "build_multimodal_metric_event"]
