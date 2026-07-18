from __future__ import annotations

from dataclasses import dataclass

from engine.textbook_parser.contracts import (
    EventKind,
    ExplicitFact,
    MotionModel,
    TemporalRole,
    TextbookProblemParseV1,
)
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.ontology import canonical_symbol


TEMPORAL_BINDING_POLICY_VERSION = "temporal-boundary-policy-v2"

_VELOCITY_KEYS = frozenset(
    {"velocity", "velocity_before", "velocity_after", "initial_velocity", "final_velocity"}
)
_COLLISION_SYSTEM_TYPES = frozenset({"impulse_momentum", "collision_1d"})
_COLLISION_START_KINDS = frozenset(
    {EventKind.collision_start, EventKind.just_before_collision}
)
_COLLISION_END_KINDS = frozenset(
    {EventKind.collision_end, EventKind.just_after_collision, EventKind.comes_to_rest}
)


@dataclass(frozen=True)
class TemporalBindingResolution:
    symbol: str | None
    issue: ValidationIssue | None = None
    boundary_role: str | None = None


def _ambiguous(
    fact: ExplicitFact, message: str, **metadata
) -> TemporalBindingResolution:
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


def _endpoint_symbol(
    fact: ExplicitFact,
    boundary: str,
    *,
    role: int | None,
    role_count: int,
) -> TemporalBindingResolution:
    if fact.semantic_key == "initial_velocity" and boundary != "initial":
        return _ambiguous(
            fact,
            "initial_velocity conflicts with the resolved boundary",
            event_boundary_role=boundary,
        )
    if fact.semantic_key == "final_velocity" and boundary != "final":
        return _ambiguous(
            fact,
            "final_velocity conflicts with the resolved boundary",
            event_boundary_role=boundary,
        )
    if fact.semantic_key == "velocity_before" and boundary != "initial":
        return _ambiguous(
            fact,
            "velocity_before must resolve to the solver interval initial state",
            event_boundary_role=boundary,
        )
    if fact.semantic_key == "velocity_after" and boundary != "final":
        return _ambiguous(
            fact,
            "velocity_after must resolve to the solver interval final state",
            event_boundary_role=boundary,
        )
    if role_count > 1:
        if role is None:
            return _ambiguous(fact, "multi-body velocity has no deterministic semantic role")
        symbol = f"v{role}" if boundary == "initial" else f"v{role}_after"
    else:
        symbol = "v0" if boundary == "initial" else "vf"
    return TemporalBindingResolution(symbol, boundary_role=boundary)


def resolve_fact_symbol(
    parse: TextbookProblemParseV1,
    fact: ExplicitFact,
    *,
    target_segment_ids: set[str],
    role: int | None,
    role_count: int,
    system_type: str | None = None,
    effective_target_segment_id: str | None = None,
) -> TemporalBindingResolution:
    """Resolve state symbols through the versioned physics boundary policy.

    A validated adjacent-boundary import passes its target segment through
    ``effective_target_segment_id``; arbitrary context facts never do.
    """

    semantic_key = (
        fact.semantic_key.value
        if hasattr(fact.semantic_key, "value")
        else str(fact.semantic_key)
    )
    base_symbol = canonical_symbol(fact.semantic_key)
    if semantic_key not in _VELOCITY_KEYS:
        return TemporalBindingResolution(base_symbol)

    target_segment_id = effective_target_segment_id or fact.segment_id
    if target_segment_id is None or target_segment_id not in target_segment_ids:
        return _ambiguous(
            fact,
            "velocity fact is not bound to a target or validated adjacent boundary",
            target_segment_id=target_segment_id,
        )
    segment_by_id = {item.segment_id: item for item in parse.motion_segments}
    event_by_id = {item.event_id: item for item in parse.events}
    segment = segment_by_id[target_segment_id]
    event = event_by_id.get(fact.event_id) if fact.event_id is not None else None
    is_start = event is not None and segment.start_event_id == event.event_id
    is_end = event is not None and segment.end_event_id == event.event_id
    imported_adjacent = fact.segment_id != target_segment_id
    system_value = system_type.value if hasattr(system_type, "value") else system_type
    collision_interval = (
        system_value in _COLLISION_SYSTEM_TYPES
        or bool(
            set(segment.motion_model_candidates)
            & {MotionModel.collision_contact, MotionModel.impulse_interval}
        )
    )

    if fact.temporal_role in {
        TemporalRole.during,
        TemporalRole.interval,
        TemporalRole.timeless,
    }:
        if semantic_key == "velocity" and fact.event_id is None and role_count == 1:
            return TemporalBindingResolution("v", boundary_role="ordinary")
        return _ambiguous(
            fact,
            "non-endpoint velocity cannot be promoted to a solver boundary",
            target_segment_id=target_segment_id,
        )

    boundary: str | None = None
    if collision_interval:
        if fact.temporal_role == TemporalRole.initial and (event is None or is_start):
            boundary = "initial"
        elif fact.temporal_role == TemporalRole.final and (event is None or is_end):
            boundary = "final"
        elif (
            fact.temporal_role == TemporalRole.before_event
            and is_start
            and event is not None
            and (event.kind in _COLLISION_START_KINDS or imported_adjacent)
        ):
            boundary = "initial"
        elif (
            fact.temporal_role == TemporalRole.after_event
            and is_end
            and event is not None
            and event.kind in _COLLISION_END_KINDS
        ):
            boundary = "final"
        else:
            return _ambiguous(
                fact,
                "collision pre/post state does not match the target interval boundary",
                target_segment_id=target_segment_id,
                event_boundary_role=(
                    "start" if is_start else "end" if is_end else "non_boundary"
                ),
            )
    else:
        if fact.temporal_role == TemporalRole.initial and (event is None or is_start):
            boundary = "initial"
        elif fact.temporal_role == TemporalRole.after_event and is_start:
            boundary = "initial"
        elif fact.temporal_role == TemporalRole.final and (event is None or is_end):
            boundary = "final"
        elif fact.temporal_role == TemporalRole.before_event and is_end:
            boundary = "final"
        else:
            return _ambiguous(
                fact,
                "continuous-motion state does not match an allowed endpoint rule",
                target_segment_id=target_segment_id,
                event_boundary_role=(
                    "start" if is_start else "end" if is_end else "non_boundary"
                ),
            )

    return _endpoint_symbol(fact, boundary, role=role, role_count=role_count)


__all__ = [
    "TEMPORAL_BINDING_POLICY_VERSION",
    "TemporalBindingResolution",
    "resolve_fact_symbol",
]
