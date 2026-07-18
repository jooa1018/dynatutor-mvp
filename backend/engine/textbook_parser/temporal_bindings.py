from __future__ import annotations

from dataclasses import dataclass

from engine.textbook_parser.contracts import (
    EventKind,
    ExplicitFact,
    TemporalRole,
    TextbookProblemParseV1,
)
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.ontology import canonical_symbol


TEMPORAL_BINDING_POLICY_VERSION = "event-boundary-velocity-v1"

_START_KINDS = frozenset(
    {
        EventKind.start,
        EventKind.release,
        EventKind.collision_end,
        EventKind.just_after_collision,
        EventKind.rope_taut,
        EventKind.rope_slack,
    }
)
_END_KINDS = frozenset(
    {
        EventKind.just_before_collision,
        EventKind.collision_start,
        EventKind.reaches_position,
        EventKind.reaches_height,
        EventKind.highest_point,
        EventKind.lowest_point,
        EventKind.comes_to_rest,
        EventKind.turnaround,
        EventKind.contact_lost,
        EventKind.rope_taut,
        EventKind.rope_slack,
        EventKind.spring_max_compression,
        EventKind.finish,
    }
)
_VELOCITY_KEYS = frozenset(
    {"velocity", "velocity_before", "velocity_after", "initial_velocity", "final_velocity"}
)


@dataclass(frozen=True)
class TemporalBindingResolution:
    symbol: str | None
    issue: ValidationIssue | None = None


def _ambiguous(fact: ExplicitFact, message: str, **metadata) -> TemporalBindingResolution:
    return TemporalBindingResolution(
        None,
        ValidationIssue(
            ErrorCode.temporal_binding_ambiguous,
            Severity.critical,
            message,
            path=f"explicit_facts.{fact.fact_id}",
            referenced_id=fact.fact_id,
            metadata=metadata or None,
        ),
    )


def resolve_fact_symbol(
    parse: TextbookProblemParseV1,
    fact: ExplicitFact,
    *,
    target_segment_ids: set[str],
    role: int | None,
    role_count: int,
) -> TemporalBindingResolution:
    """Resolve velocity endpoints only from an explicit target-segment boundary."""

    base_symbol = canonical_symbol(fact.semantic_key)
    if fact.semantic_key not in _VELOCITY_KEYS:
        return TemporalBindingResolution(base_symbol)
    if fact.segment_id is None or fact.segment_id not in target_segment_ids:
        return _ambiguous(fact, "velocity fact is not bound to a target motion segment")

    segment_by_id = {item.segment_id: item for item in parse.motion_segments}
    event_by_id = {item.event_id: item for item in parse.events}
    segment = segment_by_id[fact.segment_id]
    event = event_by_id.get(fact.event_id) if fact.event_id is not None else None
    is_start = event is not None and segment.start_event_id == event.event_id
    is_end = event is not None and segment.end_event_id == event.event_id
    boundary: str | None = None

    if fact.temporal_role == TemporalRole.initial:
        if event is not None and not is_start:
            return _ambiguous(
                fact,
                "initial velocity event is not a compatible target-segment start boundary",
                event_kind=event.kind.value,
                segment_order=segment.order,
            )
        boundary = "initial"
    elif fact.temporal_role == TemporalRole.final:
        if event is not None and not is_end:
            return _ambiguous(
                fact,
                "final velocity event is not a compatible target-segment end boundary",
                event_kind=event.kind.value,
                segment_order=segment.order,
            )
        boundary = "final"
    elif fact.temporal_role == TemporalRole.before_event:
        if event is None:
            return _ambiguous(fact, "before_event velocity requires an event_id")
        if is_end and event.kind in _END_KINDS:
            boundary = "final"
        else:
            return _ambiguous(
                fact,
                "before_event velocity is not a compatible target-segment end boundary",
                event_kind=event.kind.value,
                is_start_boundary=is_start,
                is_end_boundary=is_end,
                segment_order=segment.order,
            )
    elif fact.temporal_role == TemporalRole.after_event:
        if event is None:
            return _ambiguous(fact, "after_event velocity requires an event_id")
        if is_start and event.kind in _START_KINDS:
            boundary = "initial"
        else:
            return _ambiguous(
                fact,
                "after_event velocity is not a compatible target-segment start boundary",
                event_kind=event.kind.value,
                is_start_boundary=is_start,
                is_end_boundary=is_end,
                segment_order=segment.order,
            )
    elif fact.temporal_role == TemporalRole.at_event:
        if event is None:
            return _ambiguous(fact, "at_event velocity requires an event_id")
        if is_start != is_end and is_start:
            boundary = "initial"
        elif is_start != is_end and is_end:
            boundary = "final"
        else:
            return _ambiguous(
                fact,
                "at_event velocity does not identify one compatible target-segment boundary",
                event_kind=event.kind.value,
                is_start_boundary=is_start,
                is_end_boundary=is_end,
                segment_order=segment.order,
            )
    elif (
        fact.temporal_role in {TemporalRole.during, TemporalRole.interval, TemporalRole.timeless}
        and fact.semantic_key == "velocity"
        and fact.event_id is None
        and role_count == 1
    ):
        return TemporalBindingResolution("v")
    else:
        return _ambiguous(
            fact,
            "during, interval, and timeless velocity cannot be promoted to a segment endpoint",
            temporal_role=fact.temporal_role.value,
            segment_order=segment.order,
        )

    if fact.semantic_key == "initial_velocity" and boundary != "initial":
        return _ambiguous(fact, "initial_velocity semantic key conflicts with the resolved boundary")
    if fact.semantic_key == "final_velocity" and boundary != "final":
        return _ambiguous(fact, "final_velocity semantic key conflicts with the resolved boundary")
    if role_count > 1:
        if role is None:
            return _ambiguous(fact, "multi-body velocity has no deterministic semantic role")
        return TemporalBindingResolution(f"v{role}" if boundary == "initial" else f"v{role}_after")
    return TemporalBindingResolution("v0" if boundary == "initial" else "vf")


__all__ = [
    "TEMPORAL_BINDING_POLICY_VERSION",
    "TemporalBindingResolution",
    "resolve_fact_symbol",
]
