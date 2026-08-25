"""Exact typed-source reader for spring energy at natural length.

The planner and transaction share this reader so they cannot disagree about
what authorises closure.  Applicability is the complete Draft shape: one body,
one spring, one support, one bounded energy interval, the spring/body topology,
an evidenced initial deformation and rest boundary, an evidenced exact
zero-deformation end boundary, and one final-speed query.  Case identity,
family, labels, metadata, problem text and answers are never inspected.

The reader derives no values.  In particular, it never interprets an absolute
length as deformation and never treats finish, inactive, a force value, a text
fragment, or an approximate number as the natural-length endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from engine.mechanics.spring_endpoint import (
    is_exact_zero_deformation_endpoint,
)


SPRING_NATURAL_LENGTH_READER_VERSION = (
    "phase56-stage7-spring-natural-length-reader-v1"
)

_BODY_PRIMITIVES: frozenset[str] = frozenset(
    {"particle", "rigid_body", "body_component"}
)
_SCALAR_SHAPE = "scalar"


@dataclass(frozen=True, slots=True)
class SpringNaturalLengthSourceV1:
    """Identifiers already fixed by one exact source Draft."""

    body_id: str
    spring_id: str
    surface_id: str
    interval_id: str
    start_event_id: str
    end_event_id: str
    spring_interaction_id: str
    support_relation_id: str
    mass_quantity_id: str
    stiffness_quantity_id: str
    deformation_start_quantity_id: str
    speed_start_quantity_id: str
    speed_end_quantity_id: str
    rest_state_id: str
    endpoint_state_id: str
    friction_assumption_id: str
    rest_assumption_id: str


def _records(
    payload: Mapping[str, Any], field: str
) -> list[Mapping[str, Any]] | None:
    value = payload.get(field)
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        return None
    return value


def _one(items: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return items[0] if len(items) == 1 else None


def _enum_token(value: Any) -> Any:
    return getattr(value, "value", value)


def _dimension(**powers: int) -> dict[str, int]:
    names = (
        "mass",
        "length",
        "time",
        "current",
        "temperature",
        "amount",
        "luminous_intensity",
    )
    return {name: powers.get(name, 0) for name in names}


_MASS = _dimension(mass=1)
_STIFFNESS = _dimension(mass=1, time=-2)
_LENGTH = _dimension(length=1)
_SPEED = _dimension(length=1, time=-1)


def _refs_known(record: Mapping[str, Any], evidence_ids: set[str]) -> bool:
    refs = record.get("evidence_refs")
    return isinstance(refs, list) and all(
        type(item) is str and item in evidence_ids for item in refs
    )


def _evidenced(record: Mapping[str, Any], evidence_ids: set[str]) -> bool:
    return _refs_known(record, evidence_ids) and bool(record.get("evidence_refs"))


def _plain_scalar(
    item: Mapping[str, Any],
    *,
    role: str,
    subject_id: str,
    interval_id: str,
    event_id: str | None,
    dimension: Mapping[str, int],
) -> bool:
    return (
        item.get("role") == role
        and item.get("subject_id") == subject_id
        and item.get("point_id") is None
        and item.get("frame_id") is None
        and item.get("interval_id") == interval_id
        and item.get("event_id") == event_id
        and item.get("component") in {"unspecified", "magnitude"}
        and item.get("direction") is None
        and item.get("shape") == _SCALAR_SHAPE
        and item.get("dimension") == dimension
        and type(item.get("symbol_id")) is str
    )


def _source_value(item: Mapping[str, Any], evidence_ids: set[str]) -> bool:
    return (
        item.get("provenance") == "explicit_source"
        and type(item.get("raw_value")) is str
        and type(item.get("raw_unit")) is str
        and _evidenced(item, evidence_ids)
    )


def _unknown_value(item: Mapping[str, Any]) -> bool:
    return (
        item.get("provenance") == "unknown"
        and item.get("raw_value") is None
        and item.get("raw_unit") is None
        and item.get("assumption_policy_ref") is None
        and not item.get("evidence_refs")
    )


def read_spring_natural_length_source(
    payload: Mapping[str, Any],
) -> SpringNaturalLengthSourceV1 | None:
    """Read one complete spring/natural-length energy source shape.

    Any surplus topology, competing spring, missing evidence, mismatched event,
    non-deformation length, already-valued answer, or non-canonical endpoint
    returns ``None``.  Values are checked only at the transaction boundary.
    """

    field_names = (
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
    fields = {name: _records(payload, name) for name in field_names}
    if any(value is None for value in fields.values()):
        return None
    records = {name: value or [] for name, value in fields.items()}
    if any(
        records[name]
        for name in (
            "source_assets",
            "points",
            "reference_frames",
            "constraints",
            "principle_hints",
            "ambiguities",
            "unsupported_features",
        )
    ):
        return None
    figure = payload.get("figure_dependency")
    if not isinstance(figure, Mapping) or (
        figure.get("level") != "none"
        or figure.get("missing_information")
        or figure.get("evidence_refs")
    ):
        return None

    evidence = records["source_evidence"]
    evidence_ids = {
        item.get("evidence_id")
        for item in evidence
        if type(item.get("evidence_id")) is str
    }
    if len(evidence_ids) != len(evidence) or not evidence_ids:
        return None

    entities = records["entities"]
    if len(entities) != 3:
        return None
    bodies = [item for item in entities if item.get("primitive") in _BODY_PRIMITIVES]
    springs = [item for item in entities if item.get("primitive") == "spring"]
    surfaces = [item for item in entities if item.get("primitive") == "surface"]
    if any(len(items) != 1 for items in (bodies, springs, surfaces)):
        return None
    body, spring, surface = bodies[0], springs[0], surfaces[0]
    body_id = body.get("entity_id")
    spring_id = spring.get("entity_id")
    surface_id = surface.get("entity_id")
    if any(type(item) is not str for item in (body_id, spring_id, surface_id)):
        return None
    if len({body_id, spring_id, surface_id}) != 3 or any(
        not _refs_known(item, evidence_ids) for item in entities
    ):
        return None

    interval = _one(records["motion_intervals"])
    if interval is None:
        return None
    interval_id = interval.get("interval_id")
    start_event_id = interval.get("start_event_id")
    end_event_id = interval.get("end_event_id")
    if (
        type(interval_id) is not str
        or type(start_event_id) is not str
        or type(end_event_id) is not str
        or start_event_id == end_event_id
        or set(interval.get("subject_ids") or ()) != {body_id, spring_id}
        or len(interval.get("subject_ids") or ()) != 2
        or interval.get("frame_id") is not None
        or not _refs_known(interval, evidence_ids)
    ):
        return None

    events = records["events"]
    if len(events) != 2:
        return None
    events_by_id = {item.get("event_id"): item for item in events}
    if len(events_by_id) != 2:
        return None
    start = events_by_id.get(start_event_id)
    end = events_by_id.get(end_event_id)
    if start is None or end is None:
        return None
    for event, kind in ((start, "release"), (end, "finish")):
        if (
            event.get("kind") != kind
            or set(event.get("subject_ids") or ()) != {body_id, spring_id}
            or len(event.get("subject_ids") or ()) != 2
            or set(event.get("interval_ids") or ()) != {interval_id}
            or event.get("occurs_in_interval_ids")
            or event.get("time_quantity_id") is not None
            or not _refs_known(event, evidence_ids)
        ):
            return None

    geometry = _one(records["geometry"])
    if (
        geometry is None
        or geometry.get("kind") != "lies_on"
        or set(geometry.get("participant_ids") or ()) != {body_id, surface_id}
        or len(geometry.get("participant_ids") or ()) != 2
        or geometry.get("expression") is not None
        or geometry.get("quantity_ids")
        or geometry.get("interval_id") != interval_id
        or not _refs_known(geometry, evidence_ids)
        or type(geometry.get("relation_id")) is not str
    ):
        return None

    interaction = _one(records["interactions"])
    if (
        interaction is None
        or interaction.get("kind") != "spring"
        or set(interaction.get("participant_ids") or ()) != {body_id, spring_id}
        or len(interaction.get("participant_ids") or ()) != 2
        or interaction.get("point_ids")
        or interaction.get("frame_id") is not None
        or interaction.get("interval_id") != interval_id
        or interaction.get("event_id") is not None
        or interaction.get("contact_side") is not None
        or not _refs_known(interaction, evidence_ids)
        or type(interaction.get("interaction_id")) is not str
    ):
        return None

    quantities = records["quantities"]
    if len(quantities) != 5:
        return None
    by_role: dict[str, list[Mapping[str, Any]]] = {}
    for item in quantities:
        by_role.setdefault(str(item.get("role")), []).append(item)
    if {role: len(items) for role, items in by_role.items()} != {
        "mass": 1,
        "stiffness": 1,
        "displacement": 1,
        "velocity": 2,
    }:
        return None
    mass = by_role["mass"][0]
    stiffness = by_role["stiffness"][0]
    deformation = by_role["displacement"][0]
    velocities = by_role["velocity"]
    if not (
        _plain_scalar(
            mass,
            role="mass",
            subject_id=body_id,
            interval_id=interval_id,
            event_id=None,
            dimension=_MASS,
        )
        and mass.get("component") == "unspecified"
        and _source_value(mass, evidence_ids)
        and _plain_scalar(
            stiffness,
            role="stiffness",
            subject_id=stiffness.get("subject_id"),
            interval_id=interval_id,
            event_id=None,
            dimension=_STIFFNESS,
        )
        and stiffness.get("subject_id") in {body_id, spring_id}
        and stiffness.get("component") == "unspecified"
        and _source_value(stiffness, evidence_ids)
        and _plain_scalar(
            deformation,
            role="displacement",
            subject_id=spring_id,
            interval_id=interval_id,
            event_id=start_event_id,
            dimension=_LENGTH,
        )
        and deformation.get("component") == "unspecified"
        and _source_value(deformation, evidence_ids)
    ):
        return None
    if interaction.get("quantity_ids") != [stiffness.get("quantity_id")]:
        return None
    speed_start = next(
        (item for item in velocities if item.get("event_id") == start_event_id),
        None,
    )
    speed_end = next(
        (item for item in velocities if item.get("event_id") == end_event_id),
        None,
    )
    if (
        speed_start is None
        or speed_end is None
        or speed_start is speed_end
        or not _plain_scalar(
            speed_start,
            role="velocity",
            subject_id=body_id,
            interval_id=interval_id,
            event_id=start_event_id,
            dimension=_SPEED,
        )
        or speed_start.get("component") != "magnitude"
        or not _unknown_value(speed_start)
        or not _plain_scalar(
            speed_end,
            role="velocity",
            subject_id=body_id,
            interval_id=interval_id,
            event_id=end_event_id,
            dimension=_SPEED,
        )
        or speed_end.get("component") != "magnitude"
        or not _unknown_value(speed_end)
    ):
        return None

    quantity_ids = {item.get("quantity_id") for item in quantities}
    if len(quantity_ids) != len(quantities) or None in quantity_ids:
        return None
    symbols = records["symbols"]
    if len(symbols) != len(quantities):
        return None
    symbol_pairs = {(item.get("symbol_id"), item.get("quantity_id")) for item in symbols}
    expected_pairs = {(item.get("symbol_id"), item.get("quantity_id")) for item in quantities}
    if len(symbol_pairs) != len(symbols) or symbol_pairs != expected_pairs:
        return None

    states = records["state_conditions"]
    if len(states) != 2:
        return None
    rest_states = [item for item in states if item.get("state") == "at_rest"]
    endpoint_states = [
        item
        for item in states
        if is_exact_zero_deformation_endpoint(item.get("state"))
    ]
    if len(rest_states) != 1 or len(endpoint_states) != 1:
        return None
    rest_state = rest_states[0]
    endpoint_state = endpoint_states[0]
    if (
        rest_state.get("kind") != "initial"
        or rest_state.get("subject_id") != body_id
        or rest_state.get("interval_id") != interval_id
        or rest_state.get("event_id") != start_event_id
        or rest_state.get("expression") is not None
        or rest_state.get("quantity_ids") != [speed_start.get("quantity_id")]
        or not _evidenced(rest_state, evidence_ids)
        or endpoint_state.get("kind") != "boundary"
        or endpoint_state.get("subject_id") != spring_id
        or endpoint_state.get("interval_id") != interval_id
        or endpoint_state.get("event_id") != end_event_id
        or endpoint_state.get("expression") is not None
        or endpoint_state.get("quantity_ids")
        or not _evidenced(endpoint_state, evidence_ids)
        or type(endpoint_state.get("state_condition_id")) is not str
    ):
        return None

    assumptions = records["assumptions"]
    if len(assumptions) != 2:
        return None
    by_kind = {item.get("kind"): item for item in assumptions}
    if set(by_kind) != {"frictionless", "starts_from_rest"}:
        return None
    friction = by_kind["frictionless"]
    rest = by_kind["starts_from_rest"]
    for assumption, role, value, unit in (
        (friction, "coefficient_friction", "0", ""),
        (rest, "velocity", "0", "m/s"),
    ):
        if (
            assumption.get("subject_id") != body_id
            or assumption.get("interval_id") != interval_id
            or assumption.get("disposition") != "approved"
            or assumption.get("proposed_role") != role
            or assumption.get("proposed_value") != value
            or assumption.get("proposed_unit") != unit
            or type(assumption.get("assumption_id")) is not str
            or not _evidenced(assumption, evidence_ids)
        ):
            return None

    query = _one(records["queries"])
    if query is None or query.get("shape") != "scalar":
        return None
    target = query.get("target")
    if not isinstance(target, Mapping) or (
        target.get("role") != "velocity"
        or target.get("subject_id") != body_id
        or target.get("point_id") is not None
        or target.get("frame_id") is not None
        or target.get("interval_id") != interval_id
        or target.get("event_id") != end_event_id
        or target.get("component") != "magnitude"
        or target.get("direction") is not None
        or target.get("target_quantity_id") != speed_end.get("quantity_id")
        or query.get("output_dimension") != _SPEED
        or not _refs_known(query, evidence_ids)
        or getattr(query.get("objective"), "value", query.get("objective")) is not None
    ):
        return None

    return SpringNaturalLengthSourceV1(
        body_id=body_id,
        spring_id=spring_id,
        surface_id=surface_id,
        interval_id=interval_id,
        start_event_id=start_event_id,
        end_event_id=end_event_id,
        spring_interaction_id=str(interaction["interaction_id"]),
        support_relation_id=str(geometry["relation_id"]),
        mass_quantity_id=str(mass["quantity_id"]),
        stiffness_quantity_id=str(stiffness["quantity_id"]),
        deformation_start_quantity_id=str(deformation["quantity_id"]),
        speed_start_quantity_id=str(speed_start["quantity_id"]),
        speed_end_quantity_id=str(speed_end["quantity_id"]),
        rest_state_id=str(rest_state["state_condition_id"]),
        endpoint_state_id=str(endpoint_state["state_condition_id"]),
        friction_assumption_id=str(friction["assumption_id"]),
        rest_assumption_id=str(rest["assumption_id"]),
    )


__all__ = [
    "SPRING_NATURAL_LENGTH_READER_VERSION",
    "SpringNaturalLengthSourceV1",
    "read_spring_natural_length_source",
]
