"""Project v2 carriers onto a Draft the existing engine already understands.

The engine's own `MechanicsProblemDraftV1` has held reference frames, axis
directions, contact sides and query objectives all along — B22 measured that
the *corpus* contract, not the engine contract, is what has no field for them.
So v2 needs no new engine: it needs the source records that fill the fields the
engine already reads.

That is all this module does.  It takes a Draft projected from a v1 record by
the existing v1 projection, and attaches the v2 carriers the migration supplied.
Two properties are enforced rather than promised:

*Fill-only.*  The merge contract (`corpus_v2.merge`) is checked against the
original payload before anything is attached.  A carrier that would restate a
field the source already states either matches it exactly — and merges as a
deterministic no-op that keeps the original record — or conflicts, in which
case `V2MergeConflict` is raised, no projection happens, and no shadow result
exists for the context.  An augmentation can therefore add meaning and can
never change it.

*Empty is identity.*  A v2 Draft with an empty augmentation is byte-identical
to its v1 Draft, which is what makes the shadow comparison mean anything.
"""

from __future__ import annotations

from typing import Any, Mapping

from evaluation.phase56_stage7.corpus_v2.merge import (
    ENGINE_AXIS_NAMES,
    ENGINE_CONSTRAINT_STATE,
    ENGINE_CONTACT_SIDE,
    ENGINE_FRAME_TYPE,
    ENGINE_STATE_VALUE,
    assert_fill_only_merge,
    projected_sense_direction,
)
from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    CorpusV2AugmentationV1,
)


CORPUS_V2_PROJECTION_VERSION = "phase56-stage7-corpus-v2-projection-v2"

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


def project_augmentation(
    draft_payload: Mapping[str, Any], augmentation: CorpusV2AugmentationV1
) -> dict[str, Any]:
    """A new Draft payload with the augmentation's carriers attached.

    Pure: the input payload is not mutated, and an empty augmentation returns an
    equal payload, so "did the carrier change anything" is answerable by
    comparison rather than by belief.  Raises `V2MergeConflict` — before any
    merging — when a carrier would restate a source field differently.
    """

    payload: dict[str, Any] = {
        key: list(value) if isinstance(value, list) else value
        for key, value in draft_payload.items()
    }
    if augmentation.is_empty:
        return payload

    # The whole conflict decision happens here, against the original payload.
    # Everything below may assume each merged field is either absent or holds
    # exactly the value the carrier states.
    assert_fill_only_merge(draft_payload, augmentation)

    # --- frames -------------------------------------------------------------
    frames = list(payload.get("reference_frames") or [])
    for frame in augmentation.reference_frames:
        engine_type = ENGINE_FRAME_TYPE.get(frame.frame_type)
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
            and axis.axis in ENGINE_AXIS_NAMES
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

    # --- quantities gain their frame, axis and sign — where the source is
    # --- silent; a source-stated identical value keeps the original record ---
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
            if updated.get("frame_id") is None:
                updated["frame_id"] = sense.frame_id
            if updated.get("direction") is None:
                updated["direction"] = projected_sense_direction(sense)
        encoding = encoding_by_quantity.get(updated.get("quantity_id"))
        if encoding is not None and encoding.frame_id is not None:
            if updated.get("frame_id") is None:
                updated["frame_id"] = encoding.frame_id
        quantities.append(updated if updated != quantity else quantity)
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
            engine_side = ENGINE_CONTACT_SIDE.get(contact.side)
            if engine_side is not None:
                if updated.get("contact_side") is None:
                    updated["contact_side"] = engine_side
                if updated.get("frame_id") is None:
                    updated["frame_id"] = contact.normal_frame_id
        interactions.append(updated if updated != interaction else interaction)
    payload["interactions"] = interactions

    # --- endpoints become stated boundary conditions ------------------------
    conditions = list(payload.get("state_conditions") or [])

    def _endpoint_already_stated(endpoint: Any, state: str) -> bool:
        return any(
            condition.get("subject_id") == endpoint.subject_id
            and condition.get("event_id") == endpoint.boundary_event_id
            and condition.get("kind") == "boundary"
            and condition.get("state") == state
            and condition.get("interval_id") == endpoint.interval_id
            for condition in conditions
        )

    for endpoint in augmentation.endpoint_conditions:
        state = ENGINE_STATE_VALUE.get(endpoint.condition.value)
        if state is None:
            # No engine state means this endpoint, so it is carried only by its
            # condition quantity if the augmentation supplied one.  Nothing is
            # approximated onto a state that means something else.
            continue
        if _endpoint_already_stated(endpoint, state):
            # The source already states exactly this; the confirmation merges
            # as a no-op and the original record is the one that survives.
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

    # --- constraints --------------------------------------------------------
    for constraint in augmentation.constraint_authorities:
        mapped = ENGINE_CONSTRAINT_STATE.get(constraint.authority.value)
        if mapped is None:
            continue
        kind, state = mapped
        if any(
            condition.get("subject_id") == constraint.subject_id
            and condition.get("kind") == kind
            and condition.get("state") == state
            and condition.get("interval_id") == constraint.interval_id
            and condition.get("event_id") == constraint.event_id
            for condition in conditions
        ):
            # Redundant confirmation of a stated constraint: no-op.
            continue
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
        if objective is not None and updated.get("objective") is None:
            updated["objective"] = objective
        queries.append(updated if updated != query else query)
    payload["queries"] = queries

    return payload


__all__ = [
    "CORPUS_V2_PROJECTION_VERSION",
    "project_augmentation",
]
