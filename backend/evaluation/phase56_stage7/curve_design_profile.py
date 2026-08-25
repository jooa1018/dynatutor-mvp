"""Exact source-shape reader for mass-cancelled circular-road design speeds.

The two supported shapes are physical invariants, not corpus families:

* a frictionless bank with stated radius, bank angle and gravity; and
* a stated-horizontal road with radius, static-friction coefficient, gravity,
  and an explicitly evidenced maximum-speed objective.

The reader consumes only typed Draft structure.  It never reads text, labels,
metadata, identifiers as semantics, expected answers, or solver output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection, Mapping

from evaluation.phase56_stage7.typed_support_frames import (
    stated_support_orientation,
)


CURVE_DESIGN_PROFILE_VERSION = "phase56-stage7-curve-design-profile-v1"


@dataclass(frozen=True, slots=True)
class CurveDesignSource:
    kind: str
    body_id: str
    road_id: str
    interval_id: str
    finish_event_id: str
    contact_id: str
    query_id: str
    target_quantity_id: str
    radius_quantity_id: str
    design_quantity_id: str
    gravity_assumption_id: str
    frictionless_assumption_id: str | None


def _items(payload: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    value = payload.get(name)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        return []
    return value


def read_curve_design_source(
    payload: Mapping[str, Any],
    *,
    approved_assumption_ids: Collection[str],
) -> CurveDesignSource | None:
    """Return the exact typed invariant source, or ``None`` on any near miss."""

    if any(
        _items(payload, name)
        for name in (
            "points",
            "geometry",
            "constraints",
            "state_conditions",
            "principle_hints",
            "ambiguities",
            "unsupported_features",
        )
    ):
        return None
    figure = payload.get("figure_dependency")
    if figure != {"level": "none", "missing_information": [], "evidence_refs": []}:
        return None

    entities = _items(payload, "entities")
    bodies = [
        item
        for item in entities
        if item.get("primitive") in {"particle", "rigid_body", "body_component"}
    ]
    roads = [item for item in entities if item.get("primitive") == "surface"]
    if len(entities) != 2 or len(bodies) != 1 or len(roads) != 1:
        return None
    body_id = bodies[0].get("entity_id")
    road_id = roads[0].get("entity_id")
    if type(body_id) is not str or type(road_id) is not str:
        return None

    intervals = _items(payload, "motion_intervals")
    events = _items(payload, "events")
    if len(intervals) != 1 or len(events) != 2:
        return None
    interval = intervals[0]
    interval_id = interval.get("interval_id")
    start_id = interval.get("start_event_id")
    finish_id = interval.get("end_event_id")
    by_event = {item.get("event_id"): item for item in events}
    if (
        type(interval_id) is not str
        or interval.get("subject_ids") != [body_id]
        or interval.get("frame_id") is not None
        or type(start_id) is not str
        or type(finish_id) is not str
        or start_id == finish_id
        or len(by_event) != 2
        or by_event.get(start_id, {}).get("kind") != "start"
        or by_event.get(finish_id, {}).get("kind") != "finish"
        or any(
            item.get("subject_ids") != [body_id]
            or item.get("time_quantity_id") is not None
            or item.get("interval_ids") != [interval_id]
            or item.get("occurs_in_interval_ids")
            for item in events
        )
    ):
        return None

    interactions = _items(payload, "interactions")
    if len(interactions) != 1:
        return None
    contact = interactions[0]
    if (
        contact.get("kind") != "contact"
        or set(contact.get("participant_ids", ())) != {body_id, road_id}
        or len(contact.get("participant_ids", ())) != 2
        or contact.get("point_ids")
        or contact.get("frame_id") is not None
        or contact.get("interval_id") is not None
        or contact.get("event_id") is not None
        or contact.get("quantity_ids")
        or contact.get("contact_side") is not None
    ):
        return None

    source_evidence = {
        item.get("evidence_id") for item in _items(payload, "source_evidence")
    }

    def evidenced(item: Mapping[str, Any], *, allow_empty: bool = False) -> bool:
        refs = set(item.get("evidence_refs", ()))
        return (allow_empty or bool(refs)) and refs <= source_evidence

    queries = _items(payload, "queries")
    quantities = _items(payload, "quantities")
    symbols = _items(payload, "symbols")
    if len(queries) != 1 or len(quantities) != 3 or len(symbols) != 3:
        return None
    query = queries[0]
    target = query.get("target")
    if not isinstance(target, Mapping):
        return None
    target_id = target.get("target_quantity_id")
    quantity_by_id = {item.get("quantity_id"): item for item in quantities}
    target_quantity = quantity_by_id.get(target_id)
    if (
        len(quantity_by_id) != 3
        or target_quantity is None
        or query.get("shape") != "scalar"
        or (target.get("role"), target.get("component"))
        not in {("velocity", "magnitude"), ("speed", "magnitude")}
        or target.get("subject_id") != body_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") != finish_id
        or target.get("direction") is not None
        or target_quantity.get("role") != target.get("role")
        or target_quantity.get("component") != target.get("component")
        or target_quantity.get("subject_id") != body_id
        or target_quantity.get("point_id") is not None
        or target_quantity.get("frame_id") is not None
        or target_quantity.get("interval_id") != interval_id
        or target_quantity.get("event_id") != finish_id
        or target_quantity.get("direction") is not None
        or target_quantity.get("shape") != "scalar"
        or target_quantity.get("provenance") != "unknown"
        or target_quantity.get("raw_value") is not None
        or target_quantity.get("raw_unit") is not None
        or type(target_quantity.get("symbol_id")) is not str
        or target_quantity.get("evidence_refs")
        or query.get("output_dimension") != target_quantity.get("dimension")
    ):
        return None

    known = [item for item in quantities if item is not target_quantity]
    radii = [item for item in known if item.get("role") == "radius"]
    design = [
        item
        for item in known
        if item.get("role") in {"angle", "coefficient_friction"}
    ]
    if len(radii) != 1 or len(design) != 1:
        return None
    radius = radii[0]
    design_quantity = design[0]

    def valued_source(item: Mapping[str, Any]) -> bool:
        return (
            type(item.get("raw_value")) is str
            and type(item.get("raw_unit")) is str
            and item.get("provenance") == "explicit_source"
            and type(item.get("symbol_id")) is str
            and item.get("shape") == "scalar"
            and item.get("component") == "unspecified"
            and item.get("direction") is None
            and evidenced(item)
        )

    if (
        radius.get("subject_id") != body_id
        or radius.get("point_id") is not None
        or radius.get("frame_id") is not None
        or radius.get("interval_id") != interval_id
        or radius.get("event_id") is not None
        or not valued_source(radius)
        or design_quantity.get("subject_id") != road_id
        or design_quantity.get("point_id") is not None
        or design_quantity.get("frame_id") is not None
        or design_quantity.get("interval_id") is not None
        or design_quantity.get("event_id") is not None
        or not valued_source(design_quantity)
    ):
        return None

    symbol_quantity_ids = [item.get("quantity_id") for item in symbols]
    if len(set(symbol_quantity_ids)) != 3 or set(symbol_quantity_ids) != set(quantity_by_id):
        return None

    assumptions = _items(payload, "assumptions")
    by_kind = {item.get("kind"): item for item in assumptions}
    kind = (
        "flat"
        if design_quantity.get("role") == "coefficient_friction"
        else "banked"
    )
    expected_kinds = {"constant_gravity"} | (
        {"frictionless"} if kind == "banked" else set()
    )
    if len(by_kind) != len(assumptions) or set(by_kind) != expected_kinds:
        return None
    for assumption_kind, assumption in by_kind.items():
        if (
            assumption.get("disposition") != "approved"
            or assumption.get("assumption_id") not in approved_assumption_ids
            or assumption.get("subject_id") != body_id
            or assumption.get("interval_id") != interval_id
            or not evidenced(assumption)
        ):
            return None
        if assumption_kind == "constant_gravity" and (
            assumption.get("proposed_role") != "gravity"
            or type(assumption.get("proposed_value")) is not str
            or type(assumption.get("proposed_unit")) is not str
        ):
            return None
        if assumption_kind == "frictionless" and (
            assumption.get("proposed_role") != "coefficient_friction"
            or assumption.get("proposed_value") != "0"
            or assumption.get("proposed_unit") != ""
        ):
            return None

    if kind == "flat":
        if (
            query.get("objective") != "maximum"
            or not evidenced(query)
            or stated_support_orientation(payload, support_id=road_id) is None
        ):
            return None
    elif query.get("objective") is not None or query.get("evidence_refs"):
        return None
    if kind == "banked" and _items(payload, "reference_frames"):
        return None

    return CurveDesignSource(
        kind=kind,
        body_id=body_id,
        road_id=road_id,
        interval_id=interval_id,
        finish_event_id=finish_id,
        contact_id=str(contact.get("interaction_id")),
        query_id=str(query.get("query_id")),
        target_quantity_id=str(target_id),
        radius_quantity_id=str(radius.get("quantity_id")),
        design_quantity_id=str(design_quantity.get("quantity_id")),
        gravity_assumption_id=str(by_kind["constant_gravity"].get("assumption_id")),
        frictionless_assumption_id=(
            str(by_kind["frictionless"].get("assumption_id"))
            if kind == "banked"
            else None
        ),
    )


__all__ = [
    "CURVE_DESIGN_PROFILE_VERSION",
    "CurveDesignSource",
    "read_curve_design_source",
]
