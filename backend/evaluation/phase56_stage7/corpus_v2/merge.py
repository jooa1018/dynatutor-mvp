"""The v2 merge contract: augmentation is fill-only, and conflict fails closed.

"Additive" cannot mean "the original bytes are archived somewhere".  If a
projected carrier changes what a v1 record *means at runtime* — flips a query
objective, rebinds a quantity to a different frame, turns an inward contact
outward — then the migration edited the source with extra steps, and every
shadow comparison downstream measures the edit rather than the carrier.  So the
merge is governed by one contract, decided **against the original payload
before anything is merged**, never by mutating first and diffing after:

*A. The source states nothing.*  The carrier may fill the empty field or append
its record, subject to the usual evidence and scope validation.

*B. The source states the same thing.*  The original record is kept untouched;
the carrier is a redundant confirmation and merges as a deterministic no-op.
The merged Draft is byte-equal to the original wherever the source spoke.

*C. The source states something different.*  The merge is refused with a
closed, privacy-safe reason code.  No projection runs and no shadow result is
produced for the context.

*D. The scopes differ.*  A narrower or wider statement is not the same
statement.  An event-scoped fact may not arrive interval-wide (the B16
defect), an interval-wide fact may not silently narrow to an instant, and a
carrier for one subject may not land on another's record.  Non-identical scope
is a conflict, never a merge.

This module is the single home of both the conflict vocabulary and the
engine-value mapping tables, so migration-time checking, projection-time
enforcement, and the projection itself all read the same policy and cannot
drift apart.
"""

from __future__ import annotations

from engine.mechanics.spring_endpoint import ZERO_DEFORMATION

from enum import Enum
from typing import Any, Iterable, Mapping

from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    ContactSide,
    CorpusV2AugmentationV1,
    FrameType,
    MotionSense,
    MotionSenseV2,
    ScalarEncoding,
)


CORPUS_V2_MERGE_CONTRACT_VERSION = "phase56-stage7-corpus-v2-merge-contract-v1"

# v2 frame types onto the engine's own `ReferenceFrameType` vocabulary.  A v2
# type with no engine counterpart is not projected at all rather than mapped to
# the nearest thing: an approximate frame is a wrong frame.
ENGINE_FRAME_TYPE: dict[FrameType, str] = {
    FrameType.world_cartesian: "cartesian_2d",
    FrameType.surface_tangent_normal: "tangential_normal",
    FrameType.incline_tangent_normal: "tangential_normal",
    FrameType.polar_radial_transverse: "radial_transverse",
    FrameType.body_fixed: "body_fixed",
    FrameType.translating: "translating",
    FrameType.rotating: "rotating",
    FrameType.line_of_impact: "cartesian_1d",
}

# The engine's `AxisName` is a closed enum.  A v2 axis whose name is outside it
# names an axis the engine has no identity for, and projecting it would produce
# a frame that validates nowhere.  Unmapped names are refused with the frame,
# not silently renamed onto a neighbour.
ENGINE_AXIS_NAMES: frozenset[str] = frozenset(
    {"x", "y", "z", "tangent", "normal", "radial", "transverse", "generalized"}
)

# v2 endpoint conditions onto the engine's closed `StateValue` vocabulary.  A
# condition with no engine counterpart is deliberately absent and projects only
# through its condition quantity: mapping it onto the nearest available state
# would state something the engine would then read as a different fact.
ENGINE_STATE_VALUE: dict[str, str] = {
    "comes_to_rest": "at_rest",
    "contact_loss": "separated",
    "reaches_natural_length": ZERO_DEFORMATION,
    "zero_spring_deformation": ZERO_DEFORMATION,
    # The unilateral contact-maintenance boundary is active at this instant:
    # the typed statement behind "the least speed that just keeps contact".
    # Distinct from `contact_loss` — the contact holds, exactly at N = 0.
    "contact_limit": "active",
}

# Constraint authorities that the engine's `StateValue` vocabulary can hold.
# The rest are not projected: the engine's `Constraint.expression` is a maths
# AST, and synthesising one from a constraint's *name* would be inventing an
# equation the source never wrote.
ENGINE_CONSTRAINT_STATE: dict[str, tuple[str, str]] = {
    "no_slip": ("rolling", "no_slip"),
    "rolling_without_slipping": ("rolling", "no_slip"),
    "contact_maintained": ("contact", "touching"),
    "contact_limit": ("contact", "touching"),
}

# v2 contact sides onto the engine's own two-member `ContactSide`.  The v2
# members with no engine counterpart are deliberately absent: a side the
# engine cannot express must not be flattened onto one it can.
ENGINE_CONTACT_SIDE: dict[ContactSide, str] = {
    ContactSide.inward: "inward",
    ContactSide.outward: "outward",
    ContactSide.inside_track: "inward",
    ContactSide.outside_track: "outward",
    ContactSide.unilateral_positive_normal: "outward",
    ContactSide.unilateral_negative_normal: "inward",
}

# Which way a motion sense points along its bound axis.  The sense's own sign
# multiplies this, so `down_slope` with sign +1 and `up_slope` with sign -1
# state the same direction and are compared as such.
SENSE_SIGN: dict[MotionSense, int] = {
    MotionSense.along_axis_positive: 1,
    MotionSense.along_axis_negative: -1,
    MotionSense.up_slope: 1,
    MotionSense.down_slope: -1,
    MotionSense.outward: 1,
    MotionSense.inward: -1,
    MotionSense.separating: 1,
    MotionSense.approaching: -1,
    MotionSense.counterclockwise: 1,
    MotionSense.clockwise: -1,
}


def projected_sense_direction(sense: MotionSenseV2) -> dict[str, Any]:
    """The exact engine direction a motion sense projects to.

    One function, used by both conflict detection and the projection itself,
    so "would this direction overwrite the source" and "what direction is
    written" can never be answered from two different formulas.
    """

    return {
        "kind": "axis",
        "frame_id": sense.frame_id,
        "axis": sense.axis,
        "sign": sense.sign * SENSE_SIGN.get(sense.sense, 1),
    }


class V2MergeConflictReason(str, Enum):
    """Closed, privacy-safe merge-conflict catalogue.

    Every member names a way an augmentation would restate something the v1
    source already states.  None carries source content.
    """

    objective_conflicts_with_source = "objective_conflicts_with_source"
    contact_side_conflicts_with_source = "contact_side_conflicts_with_source"
    frame_binding_conflicts_with_source = "frame_binding_conflicts_with_source"
    direction_conflicts_with_source = "direction_conflicts_with_source"
    motion_scope_conflicts_with_source = "motion_scope_conflicts_with_source"
    endpoint_conflicts_with_source = "endpoint_conflicts_with_source"
    constraint_conflicts_with_source = "constraint_conflicts_with_source"
    scalar_encoding_conflicts_with_source = "scalar_encoding_conflicts_with_source"
    augmentation_would_overwrite_source = "augmentation_would_overwrite_source"


_REASON_ORDER = {item: index for index, item in enumerate(V2MergeConflictReason)}


class V2MergeConflict(ValueError):
    """A typed merge refusal.  Carries reason codes and never source content."""

    def __init__(self, reasons: Iterable[V2MergeConflictReason]) -> None:
        self.reasons = tuple(reasons)
        super().__init__(",".join(item.value for item in self.reasons))


def _scope_of(record: Mapping[str, Any]) -> tuple[Any, Any]:
    return (record.get("interval_id"), record.get("event_id"))


def detect_merge_conflicts(
    draft_payload: Mapping[str, Any], augmentation: CorpusV2AugmentationV1
) -> tuple[V2MergeConflictReason, ...]:
    """Every way this augmentation would overwrite this Draft, decided up front.

    Pure and read-only over the *original* payload: no merged record is built
    here, so a conflict verdict can never depend on the merge it forbids.
    Returns canonically ordered unique reasons; empty means the augmentation is
    fill-only against this Draft.
    """

    found: set[V2MergeConflictReason] = set()
    if augmentation.is_empty:
        return ()

    quantities = list(draft_payload.get("quantities") or [])
    interactions = list(draft_payload.get("interactions") or [])
    queries = list(draft_payload.get("queries") or [])
    conditions = list(draft_payload.get("state_conditions") or [])
    geometry = list(draft_payload.get("geometry") or [])
    frames = list(draft_payload.get("reference_frames") or [])

    # --- frames: a v2 frame may never claim an identity the source uses -----
    existing_frame_ids = {item.get("frame_id") for item in frames}
    for frame in augmentation.reference_frames:
        if frame.frame_id in existing_frame_ids:
            found.add(V2MergeConflictReason.augmentation_would_overwrite_source)

    # --- source quotes: authored evidence may never shadow a source record --
    existing_evidence_ids = {
        item.get("evidence_id")
        for item in draft_payload.get("source_evidence") or []
    }
    for quote in augmentation.source_quotes:
        if quote.evidence_id in existing_evidence_ids:
            found.add(V2MergeConflictReason.augmentation_would_overwrite_source)

    # --- angle datums: one reading per angle, across the v1/v2 boundary -----
    existing_relation_ids = {item.get("relation_id") for item in geometry}
    for datum in augmentation.angle_datums:
        if datum.datum_id in existing_relation_ids:
            found.add(V2MergeConflictReason.augmentation_would_overwrite_source)
        for relation in geometry:
            if relation.get("kind") == "angle" and datum.quantity_id in (
                relation.get("quantity_ids") or []
            ):
                # The source already binds this angle; a second datum is a
                # second reading of the same number, not an addition.
                found.add(V2MergeConflictReason.augmentation_would_overwrite_source)

    # --- motion senses onto quantities --------------------------------------
    sense_by_quantity = {
        sense.quantity_id: sense
        for sense in augmentation.motion_senses
        if sense.quantity_id is not None
    }
    for quantity in quantities:
        sense = sense_by_quantity.get(quantity.get("quantity_id"))
        if sense is None:
            continue
        if sense.subject_id != quantity.get("subject_id"):
            found.add(V2MergeConflictReason.motion_scope_conflicts_with_source)
        if (sense.interval_id, sense.event_id) != _scope_of(quantity):
            # Wider (event-scoped quantity, interval-wide sense), narrower
            # (interval quantity, instant sense), or simply elsewhere: none of
            # these is the statement the source made.
            found.add(V2MergeConflictReason.motion_scope_conflicts_with_source)
        existing_frame = quantity.get("frame_id")
        if existing_frame is not None and existing_frame != sense.frame_id:
            found.add(V2MergeConflictReason.frame_binding_conflicts_with_source)
        existing_direction = quantity.get("direction")
        if existing_direction is not None and (
            dict(existing_direction) != projected_sense_direction(sense)
        ):
            found.add(V2MergeConflictReason.direction_conflicts_with_source)

    # --- scalar encodings onto quantities -----------------------------------
    encoding_by_quantity = {
        encoding.quantity_id: encoding for encoding in augmentation.scalar_encodings
    }
    for quantity in quantities:
        encoding = encoding_by_quantity.get(quantity.get("quantity_id"))
        if encoding is None:
            continue
        if encoding.subject_id != quantity.get("subject_id"):
            found.add(V2MergeConflictReason.scalar_encoding_conflicts_with_source)
        if encoding.frame_id is not None:
            existing_frame = quantity.get("frame_id")
            if existing_frame is not None and existing_frame != encoding.frame_id:
                found.add(V2MergeConflictReason.frame_binding_conflicts_with_source)
        raw_value = quantity.get("raw_value")
        if (
            encoding.encoding is ScalarEncoding.magnitude_with_direction
            and isinstance(raw_value, (int, float))
            and raw_value < 0
        ):
            # A magnitude is non-negative by definition; the source wrote a
            # signed component and the encoding claims it did not.
            found.add(V2MergeConflictReason.scalar_encoding_conflicts_with_source)
        direction = quantity.get("direction")
        if (
            encoding.encoding is ScalarEncoding.signed_component
            and isinstance(direction, Mapping)
            and direction.get("kind") == "axis"
            and (direction.get("frame_id"), direction.get("axis"))
            != (encoding.frame_id, encoding.axis)
        ):
            found.add(V2MergeConflictReason.scalar_encoding_conflicts_with_source)

    # --- contact sides onto interactions ------------------------------------
    sides_by_interaction = {
        contact.interaction_id: contact for contact in augmentation.contact_sides
    }
    for interaction in interactions:
        contact = sides_by_interaction.get(interaction.get("interaction_id"))
        if contact is None:
            continue
        engine_side = ENGINE_CONTACT_SIDE.get(contact.side)
        existing_side = interaction.get("contact_side")
        if existing_side is not None and existing_side != engine_side:
            found.add(V2MergeConflictReason.contact_side_conflicts_with_source)
        existing_frame = interaction.get("frame_id")
        if (
            contact.normal_frame_id is not None
            and existing_frame is not None
            and existing_frame != contact.normal_frame_id
        ):
            found.add(V2MergeConflictReason.frame_binding_conflicts_with_source)
        if contact.interval_id is not None and interaction.get("event_id") is not None:
            # The source scoped this contact to an instant; an interval-wide
            # side would widen it, which is the B16 defect on a contact.
            found.add(V2MergeConflictReason.contact_side_conflicts_with_source)

    # --- endpoints against stated conditions --------------------------------
    condition_ids = {item.get("state_condition_id") for item in conditions}
    for endpoint in augmentation.endpoint_conditions:
        if endpoint.endpoint_id in condition_ids:
            found.add(V2MergeConflictReason.augmentation_would_overwrite_source)
        state = ENGINE_STATE_VALUE.get(endpoint.condition.value)
        if state is None:
            continue
        for condition in conditions:
            if (
                condition.get("subject_id") == endpoint.subject_id
                and condition.get("event_id") == endpoint.boundary_event_id
            ):
                identical = (
                    condition.get("kind") == "boundary"
                    and condition.get("state") == state
                    and condition.get("interval_id") == endpoint.interval_id
                )
                if not identical:
                    # The source already says what holds at this instant for
                    # this subject, and it is not this.
                    found.add(V2MergeConflictReason.endpoint_conflicts_with_source)

    # --- constraint authorities against stated conditions -------------------
    for constraint in augmentation.constraint_authorities:
        if constraint.constraint_id in condition_ids:
            found.add(V2MergeConflictReason.augmentation_would_overwrite_source)
        mapped = ENGINE_CONSTRAINT_STATE.get(constraint.authority.value)
        if mapped is None:
            continue
        kind, state = mapped
        for condition in conditions:
            if (
                condition.get("subject_id") == constraint.subject_id
                and condition.get("kind") == kind
                and _scope_of(condition)
                == (constraint.interval_id, constraint.event_id)
                and condition.get("state") != state
            ):
                found.add(V2MergeConflictReason.constraint_conflicts_with_source)

    # --- query objectives ----------------------------------------------------
    objective_by_query = {
        objective.query_id: objective.objective.value
        for objective in augmentation.query_objectives
    }
    for query in queries:
        supplied = objective_by_query.get(query.get("query_id"))
        if supplied is None:
            continue
        existing = query.get("objective")
        if existing is not None and existing != supplied:
            # `minimum` versus `maximum` is two different questions; the
            # source asked exactly one of them.
            found.add(V2MergeConflictReason.objective_conflicts_with_source)

    return tuple(sorted(found, key=_REASON_ORDER.__getitem__))


def assert_fill_only_merge(
    draft_payload: Mapping[str, Any], augmentation: CorpusV2AugmentationV1
) -> None:
    """Raise `V2MergeConflict` unless the augmentation is fill-only here."""

    conflicts = detect_merge_conflicts(draft_payload, augmentation)
    if conflicts:
        raise V2MergeConflict(conflicts)


__all__ = [
    "CORPUS_V2_MERGE_CONTRACT_VERSION",
    "ENGINE_AXIS_NAMES",
    "ENGINE_CONSTRAINT_STATE",
    "ENGINE_CONTACT_SIDE",
    "ENGINE_FRAME_TYPE",
    "ENGINE_STATE_VALUE",
    "SENSE_SIGN",
    "V2MergeConflict",
    "V2MergeConflictReason",
    "assert_fill_only_merge",
    "detect_merge_conflicts",
    "projected_sense_direction",
]
