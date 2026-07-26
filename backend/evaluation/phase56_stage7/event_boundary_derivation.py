"""Event boundary derivation: the unknown a typed boundary law writes about.

The engine's event boundary laws — ``event_vertical_extremum_velocity``,
``event_turnaround_axis_velocity``, ``event_comes_to_rest_velocity`` — state
deterministic boundary physics from typed event kinds alone, but a law can
only write about a quantity that exists.  A source that types its interval's
end event ``highest_point`` has named the instant; nothing in the Draft yet
carries that instant's vertical velocity component.  This stage creates that
unknown — its existence, never its value.

It is the evaluator sibling of the complete-profile closure and runs directly
after it: planning reads the closed Draft without changing it, and application
creates the whole package of missing boundary unknowns transactionally or
creates nothing.  Each candidate mirrors the exact conditions of the law that
will consume it, so no dead unknown is ever added — an unmatched unknown
would only widen the graph, and a widened graph can silently turn a solvable
context into an underdetermined one.

Generated IDs are deterministic, bounded, and collided against every
ID-bearing namespace of the Draft contract — the same one-domain rule the
profile transactions enforce.  A collision, or any candidate that cannot be
built exactly, abandons the whole derivation and the caller keeps the very
Draft object it passed in.

Nothing here runs in the product path, and nothing reads a case ID, family,
split, expected terminal, expected answer, or raw problem text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from engine.mechanics.contracts import MechanicsProblemDraftV1
from engine.mechanics.laws import event_boundary as _event_boundary_contract

from evaluation.phase56_stage7.complete_profile_application import (
    _authored_draft_ids,
)

EVENT_BOUNDARY_DERIVATION_VERSION = (
    "phase56-stage7-event-boundary-derivation-v2"
)

# The engine law tables, imported from the shared eligibility contract in
# ``engine.mechanics.laws.event_boundary``.  The law is the authority, and
# this stage creates only what that authority will provably consume; sharing
# one source makes drift between the two impossible rather than forbidden.
_VERTICAL_EXTREMUM_EVENT_KINDS = (
    _event_boundary_contract.VERTICAL_EXTREMUM_EVENT_KINDS
)
_IMPULSIVE_EVENT_KINDS = _event_boundary_contract.IMPULSIVE_EVENT_KINDS
_EXTREMUM_SMOOTH_INTERACTION_KINDS = (
    _event_boundary_contract.EXTREMUM_SMOOTH_INTERACTION_KINDS
)
_TURNAROUND_SMOOTH_INTERACTION_KINDS = (
    _event_boundary_contract.TURNAROUND_SMOOTH_INTERACTION_KINDS
)
_SIGNED_AXIS_COMPONENTS = _event_boundary_contract.SIGNED_AXIS_COMPONENTS
_AXIS_BEARING_ROLES = _event_boundary_contract.AXIS_BEARING_ROLES
_VELOCITY_DIMENSION: dict[str, int] = {"length": 1, "time": -1}


class EventBoundaryOutcome(str, Enum):
    """What the derivation did.  There is no partial outcome."""

    applied = "applied"
    not_applied = "not_applied"
    rejected = "rejected"


@dataclass(frozen=True, slots=True)
class EventBoundaryDerivation:
    """The result of one derivation: a whole new Draft, or the original."""

    outcome: EventBoundaryOutcome
    draft: MechanicsProblemDraftV1
    created_quantity_ids: tuple[str, ...] = ()
    sanitized_reason: str | None = None
    version: str = EVENT_BOUNDARY_DERIVATION_VERSION


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _boundary_identity_digest(
    event_id: str, subject_id: str, interval_id: str, component: str
) -> str:
    """Deterministic, bounded digest of one boundary unknown's identity.

    Identity — the (event, subject, interval, component) tuple — is hashed so
    the generated IDs stay within the contract's 64-character bound whatever
    the source role names are, while remaining stable across runs and array
    orders.
    """

    material = "\x1f".join((event_id, subject_id, interval_id, component))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _plan_candidates(payload: dict) -> list[dict] | None:
    """Pure planning: every boundary unknown the laws would consume.

    Returns ``None`` when any qualifying candidate is ambiguous in a way that
    must abandon the derivation (never an arbitrary selection); returns an
    empty list when nothing qualifies.
    """

    events = payload["events"]
    intervals = payload["motion_intervals"]
    interactions = payload["interactions"]
    quantities = payload["quantities"]
    state_conditions = payload["state_conditions"]

    def subject_interval_interactions(subject_id: str, interval_id: str):
        return [
            item
            for item in interactions
            if subject_id in item["participant_ids"]
            and item.get("interval_id") in (None, interval_id)
        ]

    def subject_has_collision(subject_id: str) -> bool:
        return any(
            item["kind"] == "collision"
            for item in interactions
            if subject_id in item["participant_ids"]
        )

    def impulsive_instant(subject_id: str, interval: dict) -> bool:
        for other in events:
            if other["kind"] not in _IMPULSIVE_EVENT_KINDS:
                continue
            if subject_id not in other["subject_ids"]:
                continue
            if interval["interval_id"] in other.get("interval_ids", ()) or (
                other["event_id"]
                in (interval.get("start_event_id"), interval.get("end_event_id"))
            ):
                return True
        return False

    def existing_velocities(
        subject_id: str, interval_id: str, event_id: str
    ) -> list[dict]:
        return [
            item
            for item in quantities
            if item["role"] == "velocity"
            and item["subject_id"] == subject_id
            and item.get("interval_id") == interval_id
            and item.get("event_id") == event_id
        ]

    def proven_axis(subject_id: str, interval_id: str) -> tuple[str, str] | None:
        """The single (component, frame) every signed kinematic quantity agrees on."""

        axis_pairs = {
            (item["component"], item.get("frame_id"))
            for item in quantities
            if item["subject_id"] == subject_id
            and item.get("interval_id") == interval_id
            and item["role"] in _AXIS_BEARING_ROLES
            and item["component"] in _SIGNED_AXIS_COMPONENTS
        }
        if len(axis_pairs) != 1:
            return None
        component, frame_id = next(iter(axis_pairs))
        if frame_id is None:
            return None
        return component, frame_id

    candidates: list[dict] = []
    for event in events:
        kind = event["kind"]
        is_extremum = kind in _VERTICAL_EXTREMUM_EVENT_KINDS
        if not is_extremum and kind not in {"turnaround", "comes_to_rest"}:
            continue
        if not _event_boundary_contract.is_boundary_eligible(
            kind, event.get("evidence_refs") or ()
        ):
            # The same shared authority predicate the engine law applies: a
            # licensing kind without linked source evidence licenses nothing,
            # so no unknown is created for it either.
            continue
        for interval in intervals:
            if event["event_id"] not in (
                interval.get("start_event_id"),
                interval.get("end_event_id"),
            ):
                # A segment-internal event is never promoted to a boundary.
                continue
            for subject_id in event["subject_ids"]:
                if subject_id not in interval["subject_ids"]:
                    continue

                if kind == "comes_to_rest":
                    # The law refuses an instant an `at_rest` state condition
                    # already owns; creating a twin unknown there would
                    # double-pin the instant.
                    if any(
                        state["state"] == "at_rest"
                        and state["subject_id"] == subject_id
                        and state.get("event_id") == event["event_id"]
                        for state in state_conditions
                    ):
                        continue
                    # `|v| = 0` pins the magnitude and — as a theorem — every
                    # component with it.  The component unknown is created
                    # only for the single axis the subject's own signed
                    # kinematics prove, mirroring the law exactly.
                    scopes = [("magnitude", None)]
                    axis = proven_axis(subject_id, interval["interval_id"])
                    if axis is not None:
                        scopes.append(axis)
                    for component, frame_id in scopes:
                        existing = existing_velocities(
                            subject_id,
                            interval["interval_id"],
                            event["event_id"],
                        )
                        if any(
                            item["component"] == component for item in existing
                        ):
                            continue
                        digest = _boundary_identity_digest(
                            event["event_id"],
                            subject_id,
                            interval["interval_id"],
                            component,
                        )
                        candidates.append(
                            {
                                "quantity_id": f"qty_evb_{digest}",
                                "symbol_id": f"sym_evb_{digest}",
                                "role": "velocity",
                                "subject_id": subject_id,
                                "interval_id": interval["interval_id"],
                                "event_id": event["event_id"],
                                "component": component,
                                "frame_id": frame_id,
                                "shape": "scalar",
                                "dimension": dict(_VELOCITY_DIMENSION),
                                "provenance": "unknown",
                                "evidence_refs": [],
                            }
                        )
                    continue
                elif is_extremum:
                    if subject_has_collision(subject_id):
                        continue
                    if impulsive_instant(subject_id, interval):
                        continue
                    carried = subject_interval_interactions(
                        subject_id, interval["interval_id"]
                    )
                    if any(
                        item["kind"] not in _EXTREMUM_SMOOTH_INTERACTION_KINDS
                        for item in carried
                    ):
                        continue
                    gravity_frames = {
                        item["frame_id"]
                        for item in carried
                        if item["kind"] == "gravity"
                        and item.get("frame_id") is not None
                    }
                    if len(gravity_frames) != 1:
                        continue
                    component = "y"
                    frame_id = next(iter(gravity_frames))
                else:  # turnaround
                    if subject_has_collision(subject_id):
                        continue
                    if impulsive_instant(subject_id, interval):
                        continue
                    carried = subject_interval_interactions(
                        subject_id, interval["interval_id"]
                    )
                    if any(
                        item["kind"] not in _TURNAROUND_SMOOTH_INTERACTION_KINDS
                        for item in carried
                    ):
                        continue
                    axis_pairs = {
                        (item["component"], item.get("frame_id"))
                        for item in quantities
                        if item["subject_id"] == subject_id
                        and item.get("interval_id") == interval["interval_id"]
                        and item["role"] in _AXIS_BEARING_ROLES
                        and item["component"] in _SIGNED_AXIS_COMPONENTS
                    }
                    if len(axis_pairs) != 1:
                        continue
                    component, frame_id = next(iter(axis_pairs))
                    if frame_id is None:
                        continue

                existing = existing_velocities(
                    subject_id, interval["interval_id"], event["event_id"]
                )
                if any(item["component"] == component for item in existing):
                    # The instant already carries its quantity — stated or
                    # derived earlier.  The law binds that one; nothing to add.
                    continue
                digest = _boundary_identity_digest(
                    event["event_id"],
                    subject_id,
                    interval["interval_id"],
                    component,
                )
                candidates.append(
                    {
                        "quantity_id": f"qty_evb_{digest}",
                        "symbol_id": f"sym_evb_{digest}",
                        "role": "velocity",
                        "subject_id": subject_id,
                        "interval_id": interval["interval_id"],
                        "event_id": event["event_id"],
                        "component": component,
                        "frame_id": frame_id,
                        "shape": "scalar",
                        "dimension": dict(_VELOCITY_DIMENSION),
                        "provenance": "unknown",
                        "evidence_refs": [],
                    }
                )
    return candidates


def derive_event_boundaries(
    draft: MechanicsProblemDraftV1,
) -> EventBoundaryDerivation:
    """Create the whole package of missing boundary unknowns, or nothing.

    Planning never mutates the Draft.  Application builds one new Draft
    payload carrying every planned unknown and validates it whole; any
    failure — an ID collision in any namespace, duplicate planned IDs, a
    contract rejection — returns the exact original Draft object with nothing
    created anywhere.
    """

    payload = draft.model_dump(mode="json", warnings="none")
    try:
        candidates = _plan_candidates(payload)
    except Exception as exc:
        return EventBoundaryDerivation(
            EventBoundaryOutcome.rejected,
            draft,
            sanitized_reason=type(exc).__name__,
        )
    if not candidates:
        return EventBoundaryDerivation(
            EventBoundaryOutcome.not_applied,
            draft,
            sanitized_reason="no_boundary_derivable",
        )

    created_quantity_ids = [item["quantity_id"] for item in candidates]
    created_symbol_ids = [item["symbol_id"] for item in candidates]
    created_ids = [*created_quantity_ids, *created_symbol_ids]
    if len(set(created_ids)) != len(created_ids):
        return EventBoundaryDerivation(
            EventBoundaryOutcome.rejected,
            draft,
            sanitized_reason="duplicate_generated_id",
        )
    if _authored_draft_ids(payload) & set(created_ids):
        return EventBoundaryDerivation(
            EventBoundaryOutcome.rejected,
            draft,
            sanitized_reason="id_collision",
        )

    closed_payload = dict(payload)
    closed_payload["quantities"] = [*payload["quantities"], *candidates]
    closed_payload["symbols"] = [
        *payload["symbols"],
        *(
            {
                "symbol_id": item["symbol_id"],
                "quantity_id": item["quantity_id"],
                "dimension": dict(item["dimension"]),
                "shape": "scalar",
            }
            for item in candidates
        ),
    ]
    try:
        closed = MechanicsProblemDraftV1.model_validate(closed_payload)
    except Exception as exc:
        return EventBoundaryDerivation(
            EventBoundaryOutcome.rejected,
            draft,
            sanitized_reason=type(exc).__name__,
        )
    return EventBoundaryDerivation(
        EventBoundaryOutcome.applied,
        closed,
        created_quantity_ids=tuple(created_quantity_ids),
    )


__all__ = [
    "EVENT_BOUNDARY_DERIVATION_VERSION",
    "EventBoundaryDerivation",
    "EventBoundaryOutcome",
    "derive_event_boundaries",
]
