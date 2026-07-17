"""Shared helpers for Phase 54 scene builders.

Scene builders may consume only typed, already-finalized material:
post-gate ``SolveResponse`` answers, ``CanonicalProblem`` typed fields,
``PhysicalModel`` typed fields, and the fully-grounded ``explanation_trace``.
They never re-parse problem text, never read numbers out of display strings,
and never recompute or reselect an answer.
"""

from __future__ import annotations

import math

from app.schemas.visualization_scene import (
    VISUALIZATION_SCENE_SCHEMA,
    VISUALIZATION_SCENE_VERSION,
    VisualizationSceneModel,
    VizAnswerOverlayItemModel,
    VizCoordinateFrameModel,
)

# One fixed playback timestep for every scene (120 Hz).
FIXED_DT = 1.0 / 120.0


class SceneUnavailable(Exception):
    """Raised by a scene builder when typed evidence is insufficient.

    Carrying a student-readable reason keeps 'unsupported' honest: the scene
    is reported unavailable instead of being guessed into a ready state.
    """

    def __init__(self, reason: str, scene_type: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.scene_type = scene_type


def unavailable_scene(
    reason: str,
    *,
    scene_type: str | None = None,
    source_solver: str | None = None,
) -> VisualizationSceneModel:
    return VisualizationSceneModel(
        schema=VISUALIZATION_SCENE_SCHEMA,
        version=VISUALIZATION_SCENE_VERSION,
        status="unavailable",
        scene_type=scene_type,
        source_solver=source_solver,
        fallback_reason=reason,
    )


def answers_by_output_key(response) -> dict[str, object]:
    """Post-gate delivered answers keyed by output_key (first wins)."""

    table: dict[str, object] = {}
    for item in getattr(response, "answers", []) or []:
        key = getattr(item, "output_key", None)
        if key and key not in table:
            table[key] = item
    return table


def answer_numeric(item) -> float | None:
    numeric = getattr(item, "numeric", None)
    if numeric is None:
        return None
    value = float(numeric)
    if not math.isfinite(value):
        return None
    return value


def overlay_item(item) -> VizAnswerOverlayItemModel:
    """Project one delivered AnswerItemModel verbatim into the overlay."""

    return VizAnswerOverlayItemModel(
        label=getattr(item, "label", "") or "",
        display=getattr(item, "display", "") or "",
        numeric=answer_numeric(item),
        unit=getattr(item, "unit", None),
        output_key=getattr(item, "output_key", None),
    )


def known_value(canonical, symbol: str, units: tuple[str | None, ...] | None = None) -> float | None:
    """Typed known lookup with an optional unit whitelist."""

    quantity = (canonical.knowns or {}).get(symbol)
    if quantity is None or quantity.value is None:
        return None
    if units is not None and quantity.unit not in units:
        return None
    value = float(quantity.value)
    if not math.isfinite(value):
        return None
    return value


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def scene_coordinate_frame(response, physical_model) -> VizCoordinateFrameModel | None:
    """Display frame from the typed PhysicalModel coordinates.

    The typed model frame is built for every solve, so the scene stays
    byte-identical whether or not a solver attached Phase 53 evidence
    (additive-migration invariance).  It shares its vocabulary with the
    fully-grounded trace frame by construction; answer authority itself
    never flows through this display frame.  Never invents a convention:
    without a typed frame it returns None.
    """

    coords = getattr(physical_model, "coordinates", None)
    if coords is not None and coords.positive_directions:
        return VizCoordinateFrameModel(
            axes=list(coords.positive_directions.keys()),
            positive_directions=list(coords.positive_directions.values()),
            description=None,
            source="physical_model",
        )
    return None
