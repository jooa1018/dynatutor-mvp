"""Exact source-shape reader for one driven horizontal kinetic slide.

This module is deliberately shared by the complete-profile planner and its
transaction.  A plan may call the package complete only for the same typed
shape the transaction will build; keeping two readers for that question would
let the planner and the mutation boundary drift apart.

The reader uses only Draft structure.  In particular, it never reads a case
identifier, family, split, tag, expected terminal, expected answer, entity
label, problem text, or filename.  Horizontal orientation comes solely from
the source-authored frame binding accepted by ``stated_support_orientation``;
the direction of kinetic friction comes solely from the source-authored motion
carrier.  The query direction is not consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from evaluation.phase56_stage7.typed_support_frames import (
    axis_bindings,
    stated_support_orientation,
)


HORIZONTAL_DRIVEN_CONTACT_READER_VERSION = (
    "phase56-stage7-horizontal-driven-contact-reader-v1"
)

_BODY_PRIMITIVES: frozenset[str] = frozenset(
    {"particle", "rigid_body", "body_component"}
)
_SEMANTIC_X_SIGN: Mapping[str, int] = {"right": 1, "left": -1}


@dataclass(frozen=True, slots=True)
class HorizontalDrivenSlidingSourceV1:
    """Identifiers and signs already fixed by one exact source Draft."""

    body_id: str
    surface_id: str
    interval_id: str
    world_frame_id: str
    support_frame_id: str
    mass_quantity_id: str
    applied_force_quantity_id: str
    coefficient_quantity_id: str
    acceleration_quantity_id: str
    motion_quantity_id: str
    support_angle_quantity_id: str | None
    gravity_assumption_id: str
    tangent_world_x_sign: int
    applied_force_sign: int
    motion_sign: int


def _records(payload: Mapping[str, Any], field: str) -> list[Mapping[str, Any]] | None:
    value = payload.get(field)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        return None
    return value


def _one(items: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return items[0] if len(items) == 1 else None


def _axis_sign(
    quantity: Mapping[str, Any], *, frame_id: str, axis: str
) -> int | None:
    direction = quantity.get("direction")
    if not isinstance(direction, Mapping):
        return None
    sign = direction.get("sign")
    if (
        direction.get("kind") != "axis"
        or direction.get("frame_id") != frame_id
        or direction.get("axis") != axis
        or sign not in {-1, 1}
    ):
        return None
    return int(sign)


def _semantic_x_sign(quantity: Mapping[str, Any]) -> int | None:
    direction = quantity.get("direction")
    if not isinstance(direction, Mapping) or direction.get("kind") != "semantic":
        return None
    return _SEMANTIC_X_SIGN.get(str(direction.get("direction")))


def _evidenced(record: Mapping[str, Any], evidence_ids: set[str]) -> bool:
    refs = record.get("evidence_refs")
    return (
        isinstance(refs, list)
        and bool(refs)
        and all(type(item) is str and item in evidence_ids for item in refs)
    )


def _exact_source_zero(value: Any) -> bool:
    if type(value) is not str:
        return False
    try:
        return float(value) == 0.0
    except ValueError:
        return False


def _world_axis_binding_sign(
    binding: Any, frame_id: str, axis: str
) -> int | None:
    if not (
        isinstance(binding, Mapping)
        and binding.get("kind") == "axis"
        and binding.get("frame_id") == frame_id
        and binding.get("axis") == axis
        and binding.get("sign") in {-1, 1}
    ):
        return None
    return int(binding["sign"])


def _horizontal_orientation_with_tangent_parity(
    payload: Mapping[str, Any], *, support_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], int] | None:
    """Read B29's two equivalent tangent coordinate conventions.

    The shared B30 reader intentionally admits only ``tangent == world +x``.
    B29 additionally requires the coordinate-parity control where the same
    typed tangent binding is reversed and every dependent binding reverses with
    it.  Validate that mirror by changing only the coordinate sign in a private
    validation copy; the returned frames and all source authority remain the
    source-authored originals.
    """

    canonical = stated_support_orientation(payload, support_id=support_id)
    if canonical is not None:
        return canonical[0], canonical[1], 1

    frames = payload.get("reference_frames")
    if not isinstance(frames, list) or len(frames) != 2:
        return None
    support_candidates = [
        item
        for item in frames
        if isinstance(item, Mapping)
        and isinstance(item.get("origin"), Mapping)
        and item["origin"].get("kind") == "entity"
        and item["origin"].get("entity_id") == support_id
    ]
    if len(support_candidates) != 1:
        return None
    source_support = support_candidates[0]
    source_world = next(item for item in frames if item is not source_support)
    if not isinstance(source_world, Mapping):
        return None
    world_id = source_world.get("frame_id")
    if type(world_id) is not str or _world_axis_binding_sign(
        axis_bindings(source_support).get("tangent"), world_id, "x"
    ) != -1:
        return None

    normalized_support = dict(source_support)
    normalized_axes: list[dict[str, Any]] = []
    for axis in source_support.get("axes") or ():
        if not isinstance(axis, Mapping):
            return None
        normalized_axis = dict(axis)
        if axis.get("axis") == "tangent":
            direction = axis.get("direction")
            if not isinstance(direction, Mapping):
                return None
            normalized_axis["direction"] = {**direction, "sign": 1}
        normalized_axes.append(normalized_axis)
    normalized_support["axes"] = normalized_axes
    normalized_payload = dict(payload)
    normalized_payload["reference_frames"] = [
        normalized_support if item is source_support else item for item in frames
    ]
    validated = stated_support_orientation(
        normalized_payload, support_id=support_id
    )
    if validated is None:
        return None
    return source_world, source_support, -1


def read_horizontal_driven_sliding_source(
    payload: Mapping[str, Any],
) -> HorizontalDrivenSlidingSourceV1 | None:
    """Read one exact applied-force, kinetic-friction horizontal topology.

    Absence, surplus structure, ambiguity, an unstated support orientation, or
    an unstated motion direction all return ``None``.  The function does not
    normalize or derive numerical values; the transaction performs those
    checks at the mutation boundary and the solver owns the answer.
    """

    fields = {
        name: _records(payload, name)
        for name in (
            "source_assets",
            "source_evidence",
            "entities",
            "points",
            "reference_frames",
            "motion_intervals",
            "events",
            "symbols",
            "quantities",
            "geometry",
            "interactions",
            "constraints",
            "state_conditions",
            "queries",
            "principle_hints",
            "assumptions",
            "ambiguities",
            "unsupported_features",
        )
    }
    if any(value is None for value in fields.values()):
        return None
    records = {name: value or [] for name, value in fields.items()}
    if (
        records["source_assets"]
        or records["points"]
        or records["interactions"]
        or records["constraints"]
        or records["state_conditions"]
        or records["principle_hints"]
        or records["ambiguities"]
        or records["unsupported_features"]
    ):
        return None
    figure = payload.get("figure_dependency")
    if (
        not isinstance(figure, Mapping)
        or figure.get("level") != "none"
        or figure.get("missing_information") not in ([], ())
        or figure.get("evidence_refs") not in ([], ())
    ):
        return None

    if len(records["entities"]) != 2:
        return None
    bodies = [
        item for item in records["entities"] if item.get("primitive") in _BODY_PRIMITIVES
    ]
    surfaces = [
        item for item in records["entities"] if item.get("primitive") == "surface"
    ]
    body = _one(bodies)
    surface = _one(surfaces)
    if body is None or surface is None:
        return None
    body_id = body.get("entity_id")
    surface_id = surface.get("entity_id")
    if type(body_id) is not str or type(surface_id) is not str:
        return None

    stated_frames = _horizontal_orientation_with_tangent_parity(
        payload, support_id=surface_id
    )
    if stated_frames is None:
        return None
    world_frame, support_frame, tangent_world_x_sign = stated_frames
    world_frame_id = world_frame.get("frame_id")
    support_frame_id = support_frame.get("frame_id")
    if type(world_frame_id) is not str or type(support_frame_id) is not str:
        return None

    interval = _one(records["motion_intervals"])
    if interval is None:
        return None
    interval_id = interval.get("interval_id")
    start_event_id = interval.get("start_event_id")
    finish_event_id = interval.get("end_event_id")
    if (
        type(interval_id) is not str
        or interval.get("subject_ids") != [body_id]
        or interval.get("frame_id") is not None
        or type(start_event_id) is not str
        or type(finish_event_id) is not str
        or start_event_id == finish_event_id
    ):
        return None
    events = {item.get("event_id"): item for item in records["events"]}
    if len(events) != 2 or set(events) != {start_event_id, finish_event_id}:
        return None
    if events[start_event_id].get("kind") != "start" or events[finish_event_id].get("kind") != "finish":
        return None
    if any(
        item.get("subject_ids") != [body_id]
        or item.get("interval_ids") != [interval_id]
        or item.get("occurs_in_interval_ids") not in ([], ())
        or item.get("time_quantity_id") is not None
        for item in events.values()
    ):
        return None

    support = _one(records["geometry"])
    if (
        support is None
        or support.get("kind") != "lies_on"
        or len(support.get("participant_ids") or []) != 2
        or set(support.get("participant_ids") or []) != {body_id, surface_id}
        or support.get("quantity_ids") not in ([], ())
        or support.get("expression") is not None
        or support.get("interval_id") != interval_id
    ):
        return None

    evidence_ids = {
        item.get("evidence_id")
        for item in records["source_evidence"]
        if type(item.get("evidence_id")) is str
    }
    if not evidence_ids:
        return None

    query = _one(records["queries"])
    if query is None or not isinstance(query.get("target"), Mapping):
        return None
    target = query["target"]
    acceleration_quantity_id = target.get("target_quantity_id")
    if (
        query.get("shape") != "scalar"
        or query.get("objective") is not None
        or target.get("role") != "acceleration"
        or target.get("subject_id") != body_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") is not None
        or target.get("component") != "x"
        or target.get("direction") is not None
        or type(acceleration_quantity_id) is not str
    ):
        return None

    by_role: dict[str, list[Mapping[str, Any]]] = {}
    for quantity in records["quantities"]:
        by_role.setdefault(str(quantity.get("role")), []).append(quantity)
    required_roles = {
        "mass",
        "force",
        "coefficient_friction",
        "acceleration",
        "velocity",
    }
    if (
        not required_roles.issubset(by_role)
        or set(by_role) - required_roles != ({"angle"} if "angle" in by_role else set())
        or any(len(by_role[role]) != 1 for role in required_roles)
        or len(by_role.get("angle", ())) > 1
    ):
        return None
    mass = by_role["mass"][0]
    applied = by_role["force"][0]
    coefficient = by_role["coefficient_friction"][0]
    acceleration = by_role["acceleration"][0]
    motion = by_role["velocity"][0]
    support_angle = by_role.get("angle", [None])[0]

    def source_scalar(item: Mapping[str, Any], *, scoped: bool) -> bool:
        return (
            item.get("subject_id") == body_id
            and item.get("point_id") is None
            and item.get("frame_id") is None
            and item.get("interval_id") == (interval_id if scoped else None)
            and item.get("event_id") is None
            and item.get("component") == "unspecified"
            and item.get("shape") == "scalar"
            and item.get("provenance") == "explicit_source"
            and item.get("raw_value") is not None
            and item.get("raw_unit") is not None
            and _evidenced(item, evidence_ids)
        )

    if (
        not source_scalar(mass, scoped=True)
        or mass.get("direction") is not None
        or not source_scalar(applied, scoped=True)
        or not source_scalar(coefficient, scoped=False)
        or coefficient.get("direction") is not None
    ):
        return None

    # A frame is the orientation authority.  One optional source-authored zero
    # angle may repeat that same statement and is a deterministic no-op; a
    # non-zero, unevidenced, differently scoped, or second angle conflicts.
    if support_angle is not None and (
        support_angle.get("subject_id") != surface_id
        or support_angle.get("point_id") is not None
        or support_angle.get("frame_id") is not None
        or support_angle.get("interval_id") not in {None, interval_id}
        or support_angle.get("event_id") is not None
        or support_angle.get("component") not in {"unspecified", "magnitude"}
        or support_angle.get("direction") is not None
        or support_angle.get("shape") != "scalar"
        or support_angle.get("provenance") != "explicit_source"
        or not _exact_source_zero(support_angle.get("raw_value"))
        or support_angle.get("raw_unit") is None
        or not _evidenced(support_angle, evidence_ids)
    ):
        return None
    applied_world_x_sign = _semantic_x_sign(applied)
    if applied_world_x_sign is None:
        return None
    applied_sign = applied_world_x_sign * tangent_world_x_sign

    if (
        acceleration.get("quantity_id") != acceleration_quantity_id
        or acceleration.get("subject_id") != body_id
        or acceleration.get("point_id") is not None
        or acceleration.get("frame_id") is not None
        or acceleration.get("interval_id") != interval_id
        or acceleration.get("event_id") is not None
        or acceleration.get("component") != "x"
        or acceleration.get("direction") is not None
        or acceleration.get("shape") != "scalar"
        or acceleration.get("provenance") != "unknown"
        or acceleration.get("raw_value") is not None
        or acceleration.get("raw_unit") is not None
    ):
        return None

    motion_sign = _axis_sign(motion, frame_id=support_frame_id, axis="tangent")
    if (
        motion_sign is None
        or motion.get("subject_id") != body_id
        or motion.get("point_id") is not None
        or motion.get("frame_id") != support_frame_id
        or motion.get("interval_id") != interval_id
        or motion.get("event_id") is not None
        or motion.get("component") != "tangential"
        or motion.get("shape") != "scalar"
        or motion.get("provenance") != "unknown"
        or motion.get("raw_value") is not None
        or motion.get("raw_unit") is not None
        or not _evidenced(motion, evidence_ids)
    ):
        return None

    quantity_ids = {item.get("quantity_id") for item in records["quantities"]}
    symbols_by_quantity = {
        item.get("quantity_id"): item for item in records["symbols"]
    }
    if (
        len(quantity_ids) != 5 + int(support_angle is not None)
        or len(symbols_by_quantity) != len(quantity_ids)
        or set(symbols_by_quantity) != quantity_ids
        or any(
            item.get("symbol_id")
            != symbols_by_quantity[item.get("quantity_id")].get("symbol_id")
            for item in records["quantities"]
        )
    ):
        return None

    gravity = _one(records["assumptions"])
    if (
        gravity is None
        or gravity.get("kind") != "constant_gravity"
        or gravity.get("subject_id") != body_id
        or gravity.get("interval_id") not in {None, interval_id}
        or gravity.get("disposition") != "approved"
        or gravity.get("proposed_role") != "gravity"
        or gravity.get("proposed_value") is None
        or gravity.get("proposed_unit") is None
        or type(gravity.get("assumption_id")) is not str
        or not _evidenced(gravity, evidence_ids)
    ):
        return None

    return HorizontalDrivenSlidingSourceV1(
        body_id=body_id,
        surface_id=surface_id,
        interval_id=interval_id,
        world_frame_id=world_frame_id,
        support_frame_id=support_frame_id,
        mass_quantity_id=str(mass["quantity_id"]),
        applied_force_quantity_id=str(applied["quantity_id"]),
        coefficient_quantity_id=str(coefficient["quantity_id"]),
        acceleration_quantity_id=str(acceleration["quantity_id"]),
        motion_quantity_id=str(motion["quantity_id"]),
        support_angle_quantity_id=(
            str(support_angle["quantity_id"])
            if support_angle is not None
            else None
        ),
        gravity_assumption_id=str(gravity["assumption_id"]),
        tangent_world_x_sign=tangent_world_x_sign,
        applied_force_sign=applied_sign,
        motion_sign=motion_sign,
    )


__all__ = [
    "HORIZONTAL_DRIVEN_CONTACT_READER_VERSION",
    "HorizontalDrivenSlidingSourceV1",
    "read_horizontal_driven_sliding_source",
]
