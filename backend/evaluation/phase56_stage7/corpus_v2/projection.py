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
    ENGINE_CONSTRAINT_STATE,
    ENGINE_CONTACT_SIDE,
    ENGINE_FRAME_TYPE,
    ENGINE_STATE_VALUE,
    assert_fill_only_merge,
    projected_sense_direction,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    _INCLINE_SLIDE_MOTION_ASSUMPTION_ID,
    _INCLINE_SLIDE_MOTION_KIND,
)
from evaluation.phase56_stage7.corpus_v2.records import (
    CorpusV2AugmentationV1,
    FrameOriginKind,
    FrameType,
    ReferenceFrameV2,
)
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
)


CORPUS_V2_PROJECTION_VERSION = "phase56-stage7-corpus-v2-projection-v3"

# The engine axis names that name cartesian identities.  A tangent/normal
# frame whose axes are all *bound onto* another frame's cartesian axes is a
# world-aligned statement — B15's "this support's tangent is the world's x" —
# and the engine holds that statement as a `cartesian_2d` frame.  A frame
# whose axes are self-referential identities stays what its type says it is.
_CARTESIAN_AXIS_NAMES: frozenset[str] = frozenset({"x", "y", "z"})

# The one axis a slope-relative slide sense may name.  A sense along a slope's
# normal is not a slide, and no other axis name resolves one.
_INCLINE_TANGENT_AXIS = "tangent"

_SPEED_DIMENSION: dict[str, int] = {
    "mass": 0, "length": 1, "time": -1, "current": 0,
    "temperature": 0, "amount": 0, "luminous_intensity": 0,
}


def _projected_origin(frame: ReferenceFrameV2) -> dict[str, Any]:
    """The typed engine origin.  A world frame is anchored at the world.

    The first projection anchored every frame — the world frame included — to
    a pseudo entity, which produced a frame shape the B15/B16 hardening had
    never licensed.  The engine's own `WorldOrigin` is the only correct
    projection of a stated world frame.
    """

    resolved = frame.resolved_origin_kind
    if resolved is FrameOriginKind.world:
        return {"kind": "world"}
    if resolved is FrameOriginKind.point:
        return {"kind": "point", "point_id": frame.origin_point_id}
    return {"kind": "entity", "entity_id": frame.subject_id}


def _projected_frame_type(frame: ReferenceFrameV2) -> str:
    """The engine frame type, from the typed binding structure.

    Deterministic over typed structure alone: a tangent/normal frame whose
    every axis binds into another frame's cartesian axes *is* the statement
    that its directions coincide with that frame's — the engine's
    `cartesian_2d` — while self-referential axes keep the tangential-normal
    identity whose world orientation an angle datum states separately.
    """

    engine_type = ENGINE_FRAME_TYPE[frame.frame_type]
    if engine_type == "tangential_normal" and all(
        axis.bound_frame_id != frame.frame_id
        and axis.bound_axis in _CARTESIAN_AXIS_NAMES
        for axis in frame.axes
    ):
        return "cartesian_2d"
    return engine_type


def derived_authority_records(
    augmentation: CorpusV2AugmentationV1,
) -> list[dict[str, Any]]:
    """The typed authorities this augmentation's carriers derive.  Nothing else.

    A slope-relative slide sense — bound to a stated slope frame's tangent axis,
    scoped to an interval, evidenced — derives the typed slide-motion authority
    the kinetic-friction law requires.

    This is not the manifest asserting an authority.  A manifest cannot name
    `typed_incline_slide_motion`: there is no carrier field for it, and this
    function reads only frames, senses and their bindings.  It is the statement
    `_derive_incline_slide_motion_authority` documents as the one the source
    would have to make and the v1 record has no field for — the same rule,
    applied to the structure v2 can finally express.

    Exposed separately so a caller can declare exactly these ids approvable
    before running.  An augmentation that derives an authority the caller did
    not declare is refused by the authority bundle, which is the check that
    stops a carrier from approving itself.
    """

    slope_frames = {
        frame.frame_id
        for frame in augmentation.reference_frames
        if frame.frame_type is FrameType.incline_tangent_normal
    }
    records: list[dict[str, Any]] = []
    for sense in augmentation.motion_senses:
        if (
            sense.quantity_id is not None
            or sense.frame_id not in slope_frames
            or sense.axis != _INCLINE_TANGENT_AXIS
            or sense.interval_id is None
            or sense.event_id is not None
        ):
            continue
        records.append(
            {
                "assumption_id": _INCLINE_SLIDE_MOTION_ASSUMPTION_ID,
                "kind": _INCLINE_SLIDE_MOTION_KIND,
                "subject_id": sense.subject_id,
                "interval_id": sense.interval_id,
                "disposition": "approved",
                "proposed_role": None,
                "proposed_value": None,
                "proposed_unit": None,
                "reason": (
                    "closed server policy: source-stated slope-relative slide "
                    "sense, bound to a stated slope tangent"
                ),
                "evidence_refs": list(sense.evidence_refs),
            }
        )
    return records


def derived_authority_ids(augmentation: CorpusV2AugmentationV1) -> tuple[str, ...]:
    """Just the ids, for a caller declaring its approvable set."""

    return tuple(
        sorted({item["assumption_id"] for item in derived_authority_records(augmentation)})
    )


def project_augmentation(
    draft_payload: Mapping[str, Any],
    augmentation: CorpusV2AugmentationV1,
    *,
    problem_text: str | None = None,
) -> dict[str, Any]:
    """A new Draft payload with the augmentation's carriers attached.

    Pure: the input payload is not mutated, and an empty augmentation returns an
    equal payload, so "did the carrier change anything" is answerable by
    comparison rather than by belief.  Raises `V2MergeConflict` — before any
    merging — when a carrier would restate a source field differently.

    `problem_text` is required exactly when the augmentation states source
    quotes: each quote must occur verbatim in the text at its stated
    occurrence, its span is computed here, and a quote that is not the
    source's own words refuses the whole projection.
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

    # --- authored source quotes become alignable evidence records -----------
    if augmentation.source_quotes:
        evidence = list(payload.get("source_evidence") or [])
        for quote in augmentation.source_quotes:
            if problem_text is None:
                raise V2ValidationError(
                    V2ValidationReason.evidence_quote_not_in_source
                )
            start = -1
            for _ in range(quote.occurrence_index + 1):
                start = problem_text.find(quote.quote, start + 1)
                if start < 0:
                    raise V2ValidationError(
                        V2ValidationReason.evidence_quote_not_in_source
                    )
            evidence.append(
                {
                    "kind": "text",
                    "evidence_id": quote.evidence_id,
                    "quote": quote.quote,
                    "source_span": {
                        "start": start,
                        "end": start + len(quote.quote),
                    },
                    "occurrence_index": quote.occurrence_index,
                }
            )
        payload["source_evidence"] = evidence

    # --- frames -------------------------------------------------------------
    frames = list(payload.get("reference_frames") or [])
    for frame in augmentation.reference_frames:
        axes = []
        for axis in frame.axes:
            if not axis.binding_complete:
                # An axis without its typed identity binding cannot be
                # projected, and its `sense` spelling is never read in its
                # place.  Refused — a partial frame is a different frame, and
                # silently dropping it would make the shadow run measure the
                # drop instead of the carrier.
                raise V2ValidationError(V2ValidationReason.axis_binding_missing)
            axes.append(
                {
                    "axis": axis.axis,
                    "direction": {
                        "kind": "axis",
                        "frame_id": axis.bound_frame_id,
                        "axis": axis.bound_axis,
                        "sign": axis.bound_sign,
                    },
                }
            )
        frames.append(
            {
                "frame_id": frame.frame_id,
                "frame_type": _projected_frame_type(frame),
                "origin": _projected_origin(frame),
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
    symbols = list(payload.get("symbols") or [])
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

    # --- a motion sense with no quantity is a *value-free* directed state ----
    #
    # Kinetic friction opposes the motion that exists, so a closure needs which
    # way the body is going and never how fast.  A source that says "slides down
    # the slope" and states no speed has stated exactly that, and the only
    # honest projection of it is a directed motion record carrying no number.
    #
    # Minting a positive speed to carry the direction — the obvious shortcut —
    # would put a value in the graph the source never gave, and a later reader
    # could not tell an invented 1 m/s from a stated one.  So the projected
    # record has `raw_value: None` and provenance `unknown`: it names the axis,
    # the sign, the subject and the interval, and asserts no magnitude.
    slide_authorities = derived_authority_records(augmentation)
    for sense in augmentation.motion_senses:
        if sense.quantity_id is not None:
            continue
        # The engine requires every relevant unknown to carry a reciprocal
        # symbol binding, so the directed state gets one.  A symbol is an
        # identity, not a value: this record still states no magnitude, and the
        # kinetic law reads only its direction sign.
        state_quantity_id = f"{sense.sense_id}_state"
        state_symbol_id = f"{sense.sense_id}_symbol"
        symbols.append(
            {
                "symbol_id": state_symbol_id,
                "quantity_id": state_quantity_id,
                "dimension": dict(_SPEED_DIMENSION),
                "shape": "scalar",
                "vector_length": None,
            }
        )
        quantities.append(
            {
                "quantity_id": state_quantity_id,
                "symbol_id": state_symbol_id,
                "role": "velocity",
                "subject_id": sense.subject_id,
                "point_id": None,
                "frame_id": sense.frame_id,
                "interval_id": sense.interval_id,
                "event_id": sense.event_id,
                "component": "tangential" if sense.axis == "tangent" else sense.axis,
                "direction": projected_sense_direction(sense),
                "shape": "scalar",
                "dimension": dict(_SPEED_DIMENSION),
                "provenance": "unknown",
                "evidence_refs": list(sense.evidence_refs),
                "assumption_policy_ref": None,
                "correction_id": None,
                "model_confidence": None,
                "raw_value": None,
                "raw_unit": None,
            }
        )
    payload["quantities"] = quantities
    payload["symbols"] = symbols
    if slide_authorities:
        # One authority per subject/interval, however many senses were stated.
        # A second, differing sense over the same span is two statements and the
        # validator has already refused it; a duplicate assumption id here would
        # be a second copy of one statement.
        existing = list(payload.get("assumptions") or [])
        known = {item.get("assumption_id") for item in existing}
        seen: set[tuple[str, str]] = set()
        for item in slide_authorities:
            key = (item["subject_id"], item["interval_id"])
            if item["assumption_id"] in known or key in seen:
                raise V2ValidationError(
                    V2ValidationReason.event_scoped_sense_used_interval_wide
                )
            seen.add(key)
            existing.append(item)
        payload["assumptions"] = existing

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
                if (
                    contact.normal_frame_id is not None
                    and updated.get("frame_id") is None
                ):
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
