from __future__ import annotations

from typing import Iterable

from engine.textbook_parser.contracts import RelationKind


RELATION_PARTICIPANT_POLICY_VERSION = "relation-participant-policy-v1"

_UNORDERED = frozenset(
    {
        RelationKind.connected_by_rope.value,
        RelationKind.collides_with.value,
        RelationKind.contact_with.value,
        RelationKind.shares_velocity_constraint.value,
        RelationKind.shares_acceleration_constraint.value,
    }
)
_PULLEY_ROLE = RelationKind.passes_over_pulley.value
_ORDERED = frozenset(item.value for item in RelationKind) - _UNORDERED - {_PULLEY_ROLE}

RELATION_PARTICIPANT_POLICIES = {
    **{kind: "unordered" for kind in _UNORDERED},
    **{kind: "ordered" for kind in _ORDERED},
    _PULLEY_ROLE: "pulley_last",
}


def relation_policy_defined(kind: str) -> bool:
    return kind in RELATION_PARTICIPANT_POLICIES


def normalize_relation_participants(
    kind: str, participant_ids: Iterable[str]
) -> tuple[str, ...]:
    participants = tuple(participant_ids)
    policy = RELATION_PARTICIPANT_POLICIES.get(kind)
    if policy is None:
        raise ValueError(f"undefined relation participant policy: {kind}")
    if policy == "unordered":
        return tuple(sorted(participants))
    if policy == "pulley_last":
        if not participants:
            return participants
        return (*sorted(participants[:-1]), participants[-1])
    return participants


def relation_participant_role(kind: str, index: int, count: int) -> str:
    policy = RELATION_PARTICIPANT_POLICIES.get(kind)
    if policy is None:
        raise ValueError(f"undefined relation participant policy: {kind}")
    if policy == "unordered":
        return "member"
    if policy == "pulley_last":
        return "pulley" if index == count - 1 else "connected_body"
    return f"position:{index}"


__all__ = [
    "RELATION_PARTICIPANT_POLICIES",
    "RELATION_PARTICIPANT_POLICY_VERSION",
    "normalize_relation_participants",
    "relation_participant_role",
    "relation_policy_defined",
]
