"""Shared event-boundary eligibility contract.

The engine's event boundary laws (``event_vertical_extremum_velocity``,
``event_turnaround_axis_velocity``, ``event_comes_to_rest_velocity``) and the
Stage 7 evaluator's event-boundary derivation must agree, exactly, on which
typed events are eligible to license a boundary zero.  Before this module the
guard tables lived as hand-maintained copies in both places, held equal only
by a comment.  This module is the single source: both consumers import these
tables and predicates, so the eligibility contract cannot drift.

Everything here is pure data and pure predicates over plain strings and
sizes.  Nothing reads a Draft, an IR, raw problem text, a source identity,
or a reference result.
"""

from __future__ import annotations

from typing import Sized

# Event kinds that license a numeric boundary equation (a velocity zero) on
# their typed semantics.  Such a licence additionally requires source
# authority — see ``has_event_source_authority``.
NUMERIC_LICENSING_EVENT_KINDS: frozenset[str] = frozenset(
    {"highest_point", "lowest_point", "turnaround", "comes_to_rest"}
)

# Vertical position extrema of a smooth trajectory: the vertical velocity
# component is zero at the extremum instant — never the speed, never the
# horizontal component.
VERTICAL_EXTREMUM_EVENT_KINDS: frozenset[str] = frozenset(
    {"highest_point", "lowest_point"}
)

# An impulsive instant — a collision, a contact change, a rope snapping taut
# or slack — breaks the smoothness a velocity zero at an extremum or a
# turnaround relies on, so any such typed structure touching the subject and
# interval fails the emission closed.
IMPULSIVE_EVENT_KINDS: frozenset[str] = frozenset(
    {
        "collision_start",
        "collision_end",
        "contact_start",
        "contact_end",
        "rope_taut",
        "rope_slack",
    }
)

# Interactions a smooth vertical extremum tolerates: free flight, and a
# rope-guided arc (a pendulum's lowest point, a vertical circle's top).  A
# contact cannot join — the surface's own shape at the extremum instant is
# not typed, so its smoothness is unprovable and a kinked crest would break
# the zero.
EXTREMUM_SMOOTH_INTERACTION_KINDS: frozenset[str] = frozenset(
    {"gravity", "rope_tension"}
)

# A turnaround is a smooth reversal along the proven motion axis.  A contact
# or a spring may carry it (a block sliding up an incline, a mass at maximum
# compression); a collision may not — a bounce reverses at nonzero speed and
# is typed as a collision, which the impulsive guard already excludes.
TURNAROUND_SMOOTH_INTERACTION_KINDS: frozenset[str] = frozenset(
    {"gravity", "rope_tension", "contact", "spring"}
)

# Signed axis components a boundary zero may pin, and the kinematic roles
# whose signed components prove a subject's single motion axis.
SIGNED_AXIS_COMPONENTS: frozenset[str] = frozenset({"x", "y", "z"})
AXIS_BEARING_ROLES: frozenset[str] = frozenset(
    {"velocity", "acceleration", "displacement", "position"}
)


def is_numeric_licensing_kind(kind: str) -> bool:
    """True when this typed event kind licenses a boundary velocity zero."""

    return kind in NUMERIC_LICENSING_EVENT_KINDS


def has_event_source_authority(evidence_refs: Sized) -> bool:
    """True when a licensing event carries proven source authority.

    Authority is the event's own linked ``source_evidence`` — for a Draft that
    passed validation, every reference here resolves to an evidence record
    whose quote was exact-matched against the problem text.  An event without
    a reference has stated a label and nothing else, and a label alone is not
    equation authority.
    """

    return len(evidence_refs) > 0


def is_boundary_eligible(kind: str, evidence_refs: Sized) -> bool:
    """The shared entry predicate for every event-boundary consumer.

    A boundary zero needs both the licensing kind and the kind's source
    authority.  Both the engine law emission and the evaluator derivation
    call this exact predicate, so an event one of them accepts is an event
    the other accepts.
    """

    return is_numeric_licensing_kind(kind) and has_event_source_authority(
        evidence_refs
    )


__all__ = [
    "AXIS_BEARING_ROLES",
    "EXTREMUM_SMOOTH_INTERACTION_KINDS",
    "IMPULSIVE_EVENT_KINDS",
    "NUMERIC_LICENSING_EVENT_KINDS",
    "SIGNED_AXIS_COMPONENTS",
    "TURNAROUND_SMOOTH_INTERACTION_KINDS",
    "VERTICAL_EXTREMUM_EVENT_KINDS",
    "has_event_source_authority",
    "is_boundary_eligible",
    "is_numeric_licensing_kind",
]
