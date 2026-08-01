"""Project v2 carriers onto a Draft the existing engine already understands.

The engine's own `MechanicsProblemDraftV1` has held reference frames, axis
directions, contact sides and query objectives all along — B22 measured that
the *corpus* contract, not the engine contract, is what has no field for them.
So v2 needs no new engine: it needs the source records that fill the fields the
engine already reads.

That is all this module does.  It takes a Draft projected from a v1 record by
the existing v1 projection, and attaches the v2 carriers the migration supplied.
It adds nothing that the augmentation does not state, and it never edits a
record the v1 projection produced — a v2 Draft with an empty augmentation is
byte-identical to its v1 Draft, which is what makes the shadow comparison mean
anything.
"""

from __future__ import annotations

from typing import Any, Mapping

from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    ContactSide,
    CorpusV2AugmentationV1,
    FrameType,
    MotionSense,
)


CORPUS_V2_PROJECTION_VERSION = "phase56-stage7-corpus-v2-projection-v1"

# v2 frame types onto the engine's own `ReferenceFrameType` vocabulary.  A v2
# type with no engine counterpart is not projected at all rather than mapped to
# the nearest thing: an approximate frame is a wrong frame.
_ENGINE_FRAME_TYPE: dict[FrameType, str] = {
    FrameType.world_cartesian: "cartesian_2d",
    FrameType.surface_tangent_normal: "tangential_normal",
    FrameType.incline_tangent_normal: "tangential_normal",
    FrameType.polar_radial_transverse: "radial_transverse",
    FrameType.body_fixed: "body_fixed",
    FrameType.translating: "translating",
    FrameType.rotating: "rotating",
    FrameType.line_of_impact: "cartesian_1d",
}

# An axis sense onto the engine's semantic direction vocabulary.  The engine's
# `SemanticDirection` carries a name and no sign, and that is the right shape:
# a frame axis names an *identity* — this is the tangent, that is the normal —
# while the sign of a body's motion along it belongs to the quantity, where
# `AxisDirection` does carry one.  Splitting them this way is what stops a
# frame from silently asserting which way a body is going, which is the B16
# defect.
_ENGINE_AXIS_DIRECTION: dict[AxisSense, str] = {
    AxisSense.up_the_page: "upward",
    AxisSense.down_the_page: "downward",
    AxisSense.along_surface_forward: "tangential",
    AxisSense.along_surface_backward: "tangential",
    AxisSense.away_from_surface: "normal",
    AxisSense.into_surface: "normal",
    AxisSense.up_slope: "tangential",
    AxisSense.down_slope: "tangential",
    AxisSense.outward_from_centre: "radial",
    AxisSense.inward_to_centre: "radial",
    AxisSense.along_line_of_impact: "positive",
}

# v2 endpoint conditions onto the engine's closed `StateValue` vocabulary.  A
# condition with no engine counterpart is deliberately absent and projects only
# through its condition quantity: mapping it onto the nearest available state
# would state something the engine would then read as a different fact.
_ENGINE_STATE_VALUE: dict[str, str] = {
    "comes_to_rest": "at_rest",
    "contact_loss": "separated",
    "reaches_natural_length": "inactive",
    "zero_spring_deformation": "inactive",
}

# Constraint authorities that the engine's `StateValue` vocabulary can hold.
# The rest are not projected: the engine's `Constraint.expression` is a maths
# AST, and synthesising one from a constraint's *name* would be inventing an
# equation the source never wrote.
_ENGINE_CONSTRAINT_STATE: dict[str, tuple[str, str]] = {
    "no_slip": ("rolling", "no_slip"),
    "rolling_without_slipping": ("rolling", "no_slip"),
    "contact_maintained": ("contact", "touching"),
    "contact_limit": ("contact", "touching"),
}

# v2 contact sides onto the engine's own two-member `ContactSide`.  The four v2
# members that have no engine counterpart are deliberately absent: a side the
# engine cannot express must not be flattened onto one it can.
_ENGINE_CONTACT_SIDE: dict[ContactSide, str] = {
    ContactSide.inward: "inward",
    ContactSide.outward: "outward",
    ContactSide.inside_track: "inward",
    ContactSide.outside_track: "outward",
    ContactSide.unilateral_positive_normal: "outward",
    ContactSide.unilateral_negative_normal: "inward",
}

# The engine's `AxisName` is a closed enum.  A v2 axis whose name is outside it
# names an axis the engine has no identity for, and projecting it would produce
# a frame that validates nowhere.  Unmapped names are refused with the frame,
# not silently renamed onto a neighbour.
_ENGINE_AXIS_NAMES: frozenset[str] = frozenset(
    {"x", "y", "z", "tangent", "normal", "radial", "transverse", "generalized"}
)

_SENSE_SIGN: dict[MotionSense, int] = {
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


def project_augmentation(
    draft_payload: Mapping[str, Any], augmentation: CorpusV2AugmentationV1
) -> dict[str, Any]:
    """A new Draft payload with the augmentation's carriers attached.

    Pure: the input payload is not mutated, and an empty augmentation returns an
    equal payload, so "did the carrier change anything" is answerable by
    comparison rather than by belief.
    """

    payload: dict[str, Any] = {
        key: list(value) if isinstance(value, list) else value
        for key, value in draft_payload.items()
    }
    if augmentation.is_empty:
        return payload

    # --- frames -------------------------------------------------------------
    frames = list(payload.get("reference_frames") or [])
    for frame in augmentation.reference_frames:
        engine_type = _ENGINE_FRAME_TYPE.get(frame.frame_type)
        if engine_type is None:
            continue
        axes = [
            {
                "axis": axis.axis,
                "direction": {
                    "kind": "semantic",
                    "direction": _ENGINE_AXIS_DIRECTION[axis.sense],
                },
            }
            for axis in frame.axes
            if axis.sense in _ENGINE_AXIS_DIRECTION
            and axis.axis in _ENGINE_AXIS_NAMES
        ]
        if len(axes) != len(frame.axes):
            # One axis of this frame did not project, so the frame the engine
            # would see is not the frame the source stated.  A partial frame is
            # a different frame, so none of it is projected.
            continue
        frames.append(
            {
                "frame_id": frame.frame_id,
                "frame_type": engine_type,
                "origin": (
                    {"kind": "point", "point_id": frame.origin_point_id}
                    if frame.origin_point_id
                    else {"kind": "entity", "entity_id": frame.subject_id}
                ),
                "parent_frame_id": frame.parent_frame_id,
                "axes": axes,
                "translating_with_entity_id": frame.translating_with_entity_id,
                "rotating_about_point_id": frame.rotating_about_point_id,
                "generalized_coordinate_symbol_ids": [],
                "evidence_refs": list(frame.evidence_refs),
            }
        )
    payload["reference_frames"] = frames

    # --- quantities gain their frame, axis and sign -------------------------
    sense_by_quantity = {
        sense.quantity_id: sense
        for sense in augmentation.motion_senses
        if sense.quantity_id is not None
    }
    encoding_by_quantity = {
        encoding.quantity_id: encoding for encoding in augmentation.scalar_encodings
    }
    quantities = []
    for quantity in payload.get("quantities") or []:
        updated = dict(quantity)
        sense = sense_by_quantity.get(updated.get("quantity_id"))
        if sense is not None:
            updated["frame_id"] = sense.frame_id
            updated["direction"] = {
                "kind": "axis",
                "frame_id": sense.frame_id,
                "axis": sense.axis,
                "sign": sense.sign * _SENSE_SIGN.get(sense.sense, 1),
            }
        encoding = encoding_by_quantity.get(updated.get("quantity_id"))
        if encoding is not None and encoding.frame_id is not None:
            updated["frame_id"] = encoding.frame_id
        quantities.append(updated)
    payload["quantities"] = quantities

    # --- angle datums bind an angle to what it is measured from -------------
    geometry = list(payload.get("geometry") or [])
    for datum in augmentation.angle_datums:
        geometry.append(
            {
                "relation_id": datum.datum_id,
                "kind": "angle",
                "participant_ids": [
                    item
                    for item in (
                        datum.subject_id,
                        datum.measured_to_entity_tangent_id,
                    )
                    if item
                ],
                "quantity_ids": [datum.quantity_id],
                "interval_id": datum.interval_id,
                "evidence_refs": list(datum.evidence_refs),
            }
        )
    payload["geometry"] = geometry

    # --- contact sides on the interactions they belong to -------------------
    sides_by_interaction = {
        contact.interaction_id: contact for contact in augmentation.contact_sides
    }
    interactions = []
    for interaction in payload.get("interactions") or []:
        updated = dict(interaction)
        contact = sides_by_interaction.get(updated.get("interaction_id"))
        if contact is not None:
            engine_side = _ENGINE_CONTACT_SIDE.get(contact.side)
            if engine_side is not None:
                updated["contact_side"] = engine_side
                updated["frame_id"] = contact.normal_frame_id
        interactions.append(updated)
    payload["interactions"] = interactions

    # --- endpoints become stated boundary conditions ------------------------
    conditions = list(payload.get("state_conditions") or [])
    for endpoint in augmentation.endpoint_conditions:
        state = _ENGINE_STATE_VALUE.get(endpoint.condition.value)
        if state is None:
            # No engine state means this endpoint, so it is carried only by its
            # condition quantity if the augmentation supplied one.  Nothing is
            # approximated onto a state that means something else.
            continue
        conditions.append(
            {
                "state_condition_id": endpoint.endpoint_id,
                "kind": "boundary",
                "state": state,
                "subject_id": endpoint.subject_id,
                "interval_id": endpoint.interval_id,
                "event_id": endpoint.boundary_event_id,
                "expression": None,
                "quantity_ids": (
                    [endpoint.condition_quantity_id]
                    if endpoint.condition_quantity_id
                    else []
                ),
                "evidence_refs": list(endpoint.evidence_refs),
            }
        )
    payload["state_conditions"] = conditions

    # --- constraints --------------------------------------------------------
    for constraint in augmentation.constraint_authorities:
        mapped = _ENGINE_CONSTRAINT_STATE.get(constraint.authority.value)
        if mapped is None:
            continue
        kind, state = mapped
        conditions.append(
            {
                "state_condition_id": constraint.constraint_id,
                "kind": kind,
                "state": state,
                "subject_id": constraint.subject_id,
                "interval_id": constraint.interval_id,
                "event_id": constraint.event_id,
                "expression": None,
                "quantity_ids": [],
                "evidence_refs": list(constraint.evidence_refs),
            }
        )
    payload["state_conditions"] = conditions

    # --- query objective ----------------------------------------------------
    objective_by_query = {
        objective.query_id: objective.objective.value
        for objective in augmentation.query_objectives
    }
    queries = []
    for query in payload.get("queries") or []:
        updated = dict(query)
        objective = objective_by_query.get(updated.get("query_id"))
        if objective is not None:
            updated["objective"] = objective
        queries.append(updated)
    payload["queries"] = queries

    return payload


__all__ = [
    "CORPUS_V2_PROJECTION_VERSION",
    "project_augmentation",
]
