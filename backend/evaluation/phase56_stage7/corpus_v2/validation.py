"""The v2 validator: every way an augmentation can be wrong, named and refused.

A carrier contract is only worth having if a bad carrier is rejected rather
than half-read.  The rejection catalogue below is closed, so a failure reports
a reason code and never a fragment of source text, and every reason exists
because leaving it unchecked would let a v2 record express something the source
does not say — which is the exact failure v2 exists to prevent.

Two rules run through all of it.

*Ambiguity fails closed.*  Two frames with one identifier, two contact sides
for one interaction, two endpoint conditions on one boundary: each is two
statements where the reader needs one, and picking either is picking.

*Nothing is defaulted.*  A missing normal axis is not "probably the y axis", a
missing datum is not "probably the horizontal", and a missing sign is not
"probably positive".
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Iterable, Sequence

from evaluation.phase56_stage7.corpus_v2.merge import ENGINE_AXIS_NAMES
from evaluation.phase56_stage7.corpus_v2.records import (
    V2_IDENTIFIER_PREFIX,
    AxisSense,
    CorpusV2AugmentationV1,
    MotionSense,
    FrameOriginKind,
    FrameType,
    ScalarEncoding,
)


CORPUS_V2_VALIDATION_VERSION = "phase56-stage7-corpus-v2-validation-v3"

# `AxisSense` is descriptive vocabulary, never projection authority.  The typed
# `axis(frame, name, sign)` binding decides what an axis is; the sense only says
# what the source called it, and no missing sign, frame or axis is ever inferred
# from a sense's spelling.
#
# The one thing a sense is good for is catching a statement that contradicts
# itself.  Two senses are comparable exactly when they are the two directions of
# one opposition — `up_slope` against `down_slope`, `away_from_surface` against
# `into_surface`.  Within such a pair, a cross-frame binding that says "this
# axis points up the slope and *is* the axis that points down the slope, with
# sign +1" is not a coincidence anyone stated; it is two readings of one arrow.
#
# Senses drawn from different oppositions — `up_the_page` against
# `away_from_surface` — are not comparable at all: a surface normal genuinely
# may or may not point up the page, and that depends on geometry this contract
# does not carry.  For those the binding is the only authority and the sense is
# not consulted, because a guess here would be the invented premise v2 exists to
# refuse.
_SENSE_OPPOSITIONS: tuple[tuple[AxisSense, AxisSense], ...] = (
    (AxisSense.up_the_page, AxisSense.down_the_page),
    (AxisSense.along_surface_forward, AxisSense.along_surface_backward),
    (AxisSense.away_from_surface, AxisSense.into_surface),
    (AxisSense.up_slope, AxisSense.down_slope),
    (AxisSense.outward_from_centre, AxisSense.inward_to_centre),
)
_SENSE_FAMILY: dict[AxisSense, int] = {
    sense: index
    for index, pair in enumerate(_SENSE_OPPOSITIONS)
    for sense in pair
}


# The one axis of an incline frame whose direction a slide sense can name.
_INCLINE_TANGENT_AXIS = "tangent"

# The motion senses whose meaning is fixed by the axis binding alone.
_AXIS_RELATIVE_MOTION_SENSES: frozenset[MotionSense] = frozenset(
    {MotionSense.along_axis_positive, MotionSense.along_axis_negative}
)


def _senses_are_comparable(left: AxisSense, right: AxisSense) -> bool:
    family = _SENSE_FAMILY.get(left)
    return family is not None and family == _SENSE_FAMILY.get(right)


def _sense_agreement_sign(left: AxisSense, right: AxisSense) -> int:
    """+1 when two comparable senses point the same way, -1 when opposite."""

    return 1 if left is right else -1


class V2ValidationReason(str, Enum):
    """Closed, privacy-safe rejection catalogue."""

    duplicate_frame_id = "duplicate_frame_id"
    dangling_frame_parent = "dangling_frame_parent"
    frame_axis_self_reference = "frame_axis_self_reference"
    duplicate_axis_name = "duplicate_axis_name"
    # Typed axis-identity binding (B15/B16 parity).  A frame axis without a
    # complete axis(frame, name, sign) binding cannot be projected, and its
    # `sense` spelling is never read in its place.
    axis_binding_missing = "axis_binding_missing"
    axis_binding_frame_unknown = "axis_binding_frame_unknown"
    axis_binding_axis_unknown = "axis_binding_axis_unknown"
    # A cross-frame binding whose two axes carry directly opposed senses and a
    # sign that agrees with neither reading.  Refused, never resolved: picking
    # one of two mirror-image statements is picking.
    axis_sense_contradicts_binding = "axis_sense_contradicts_binding"
    axis_name_unknown = "axis_name_unknown"
    frame_cycle = "frame_cycle"
    frame_origin_invalid = "frame_origin_invalid"
    world_frame_parent_forbidden = "world_frame_parent_forbidden"
    angle_datum_frame_unknown = "angle_datum_frame_unknown"
    angle_datum_axis_unknown = "angle_datum_axis_unknown"
    ambiguous_angle_datum = "ambiguous_angle_datum"
    motion_sense_frame_unknown = "motion_sense_frame_unknown"
    motion_sense_axis_unknown = "motion_sense_axis_unknown"
    # A slope-relative sense on a slope tangent assumes which way that tangent
    # points, and a self-referential binding states no such thing.
    slope_sense_requires_axis_relative_statement = (
        "slope_sense_requires_axis_relative_statement"
    )
    event_scoped_sense_used_interval_wide = "event_scoped_sense_used_interval_wide"
    contact_side_frame_unknown = "contact_side_frame_unknown"
    contact_side_axis_unknown = "contact_side_axis_unknown"
    conflicting_contact_sides = "conflicting_contact_sides"
    duplicate_source_quote = "duplicate_source_quote"
    endpoint_without_event = "endpoint_without_event"
    duplicate_endpoint = "duplicate_endpoint"
    constraint_without_participants = "constraint_without_participants"
    interaction_target_without_interaction = "interaction_target_without_interaction"
    duplicate_query_objective = "duplicate_query_objective"
    contradictory_scalar_encoding = "contradictory_scalar_encoding"
    scalar_encoding_without_axis = "scalar_encoding_without_axis"
    cross_interval_scope = "cross_interval_scope"
    cross_event_scope = "cross_event_scope"
    scope_is_both_interval_and_event = "scope_is_both_interval_and_event"
    generated_id_collides_with_authored_id = "generated_id_collides_with_authored_id"
    generated_id_missing_prefix = "generated_id_missing_prefix"
    evidence_quote_not_in_source = "evidence_quote_not_in_source"
    duplicate_carrier_id = "duplicate_carrier_id"
    subject_unknown = "subject_unknown"
    evidence_ref_unknown = "evidence_ref_unknown"


class V2ValidationError(ValueError):
    """A typed rejection.  Carries a reason code and never source content."""

    def __init__(self, reason: V2ValidationReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _fail(reason: V2ValidationReason) -> V2ValidationError:
    return V2ValidationError(reason)


def _duplicates(values: Iterable[str]) -> bool:
    counted = Counter(values)
    return any(count > 1 for count in counted.values())


def validate_augmentation(
    augmentation: CorpusV2AugmentationV1,
    *,
    known_entity_ids: Sequence[str] = (),
    known_interval_ids: Sequence[str] = (),
    known_event_ids: Sequence[str] = (),
    known_evidence_ids: Sequence[str] = (),
    known_interaction_ids: Sequence[str] = (),
    known_query_ids: Sequence[str] = (),
    authored_ids: Sequence[str] = (),
) -> None:
    """Raise `V2ValidationError` on the first thing that is wrong.

    The `known_*` sequences come from the v1 record the augmentation is bound
    to.  An augmentation that references something the source does not contain
    is refused: a carrier scoped to an interval nobody declared holds over
    nothing, and one whose evidence points nowhere is unevidenced.
    """

    entities = frozenset(known_entity_ids)
    intervals = frozenset(known_interval_ids)
    events = frozenset(known_event_ids)
    interactions = frozenset(known_interaction_ids)
    queries = frozenset(known_query_ids)
    authored = frozenset(authored_ids)
    # A carrier may cite the source's own evidence records or an authored
    # verbatim quote of the source's own text — the quote is re-verified
    # against the problem text at projection, so it cannot be minted.
    quote_ids = frozenset(item.evidence_id for item in augmentation.source_quotes)
    evidence = frozenset(known_evidence_ids) | quote_ids
    if _duplicates(
        (item.quote, item.occurrence_index) for item in augmentation.source_quotes
    ):
        raise _fail(V2ValidationReason.duplicate_source_quote)

    frames = augmentation.reference_frames
    frame_ids = [frame.frame_id for frame in frames]
    if _duplicates(frame_ids):
        raise _fail(V2ValidationReason.duplicate_frame_id)
    frame_by_id = {frame.frame_id: frame for frame in frames}

    # --- every authored identifier is namespaced and collision-free ---------
    carrier_ids: list[str] = [
        *frame_ids,
        *(item.evidence_id for item in augmentation.source_quotes),
        *(item.datum_id for item in augmentation.angle_datums),
        *(item.sense_id for item in augmentation.motion_senses),
        *(item.contact_id for item in augmentation.contact_sides),
        *(item.endpoint_id for item in augmentation.endpoint_conditions),
        *(item.constraint_id for item in augmentation.constraint_authorities),
        *(item.target_id for item in augmentation.interaction_targets),
        *(item.objective_id for item in augmentation.query_objectives),
        *(item.encoding_id for item in augmentation.scalar_encodings),
    ]
    if _duplicates(carrier_ids):
        raise _fail(V2ValidationReason.duplicate_carrier_id)
    for identifier in carrier_ids:
        if not identifier.startswith(V2_IDENTIFIER_PREFIX):
            raise _fail(V2ValidationReason.generated_id_missing_prefix)
        if identifier in authored:
            raise _fail(V2ValidationReason.generated_id_collides_with_authored_id)

    # --- scope, subject and evidence, for every carrier alike --------------
    scoped = (
        *frames,
        *augmentation.angle_datums,
        *augmentation.motion_senses,
        *augmentation.contact_sides,
        *augmentation.endpoint_conditions,
        *augmentation.constraint_authorities,
        *augmentation.interaction_targets,
        *augmentation.scalar_encodings,
    )
    for carrier in scoped:
        if carrier.interval_id is not None and carrier.event_id is not None:
            # An instant and a span are two different statements.
            raise _fail(V2ValidationReason.scope_is_both_interval_and_event)
        if entities and carrier.subject_id not in entities:
            raise _fail(V2ValidationReason.subject_unknown)
        if carrier.interval_id is not None and intervals and (
            carrier.interval_id not in intervals
        ):
            raise _fail(V2ValidationReason.cross_interval_scope)
        if carrier.event_id is not None and events and carrier.event_id not in events:
            raise _fail(V2ValidationReason.cross_event_scope)
    for carrier in (*scoped, *augmentation.query_objectives):
        # Not `if evidence and ...`.  Guarding the membership test on a
        # non-empty universe made the check fail *open* in exactly the case it
        # exists for: a context whose v1 record declares no source evidence and
        # whose augmentation authors no quote has an empty universe, so every
        # `evidence_refs` entry — including one naming nothing at all — passed
        # unexamined.  A carrier cites evidence or it is an assertion; an
        # unknown reference is unknown whether or not anything else is known.
        if any(ref not in evidence for ref in carrier.evidence_refs):
            raise _fail(V2ValidationReason.evidence_ref_unknown)

    # --- frames -------------------------------------------------------------
    for frame in frames:
        if frame.parent_frame_id is not None and frame.parent_frame_id not in frame_by_id:
            raise _fail(V2ValidationReason.dangling_frame_parent)
        axis_names = [axis.axis for axis in frame.axes]
        if _duplicates(axis_names):
            raise _fail(V2ValidationReason.duplicate_axis_name)
        for axis in frame.axes:
            if axis.anchor_entity_id == frame.frame_id:
                raise _fail(V2ValidationReason.frame_axis_self_reference)

    # --- frame origins and the world frame's special shape ------------------
    for frame in frames:
        resolved = frame.resolved_origin_kind
        is_world = frame.frame_type is FrameType.world_cartesian
        if is_world:
            # A world frame is anchored at the world, parents nothing above
            # it, and never rides on a pseudo entity.
            if resolved is not FrameOriginKind.world or frame.origin_point_id:
                raise _fail(V2ValidationReason.frame_origin_invalid)
            if frame.parent_frame_id is not None:
                raise _fail(V2ValidationReason.world_frame_parent_forbidden)
        else:
            # Only the world frame may claim the world anchor; every other
            # frame states an entity or point origin the source contains.
            if resolved is FrameOriginKind.world:
                raise _fail(V2ValidationReason.frame_origin_invalid)
            if resolved is FrameOriginKind.point and not frame.origin_point_id:
                raise _fail(V2ValidationReason.frame_origin_invalid)

    # --- typed axis-identity bindings ---------------------------------------
    # Every axis must carry a complete axis(frame, name, sign) binding whose
    # names the engine's closed `AxisName` vocabulary can hold and whose
    # referenced frame and axis exist among the stated frames.  The `sense`
    # spelling never substitutes for a missing binding.
    for frame in frames:
        for axis in frame.axes:
            if axis.axis not in ENGINE_AXIS_NAMES:
                raise _fail(V2ValidationReason.axis_name_unknown)
            if not axis.binding_complete:
                raise _fail(V2ValidationReason.axis_binding_missing)
            if axis.bound_axis not in ENGINE_AXIS_NAMES:
                raise _fail(V2ValidationReason.axis_name_unknown)
            bound = frame_by_id.get(axis.bound_frame_id)
            if bound is None:
                raise _fail(V2ValidationReason.axis_binding_frame_unknown)
            target = next(
                (item for item in bound.axes if item.axis == axis.bound_axis), None
            )
            if target is None:
                raise _fail(V2ValidationReason.axis_binding_axis_unknown)
            # Sense is consulted here and nowhere else, and only to refuse.  It
            # cannot supply a sign, a frame or an axis — those are already
            # required above — and two senses from different oppositions are
            # left alone entirely.
            if axis.bound_frame_id == frame.frame_id:
                continue
            if not _senses_are_comparable(axis.sense, target.sense):
                continue
            if _sense_agreement_sign(axis.sense, target.sense) != axis.bound_sign:
                raise _fail(V2ValidationReason.axis_sense_contradicts_binding)

    # --- no cycles through parents or cross-frame bindings ------------------
    edges: dict[str, set[str]] = {frame.frame_id: set() for frame in frames}
    for frame in frames:
        if frame.parent_frame_id is not None:
            edges[frame.frame_id].add(frame.parent_frame_id)
        for axis in frame.axes:
            if axis.bound_frame_id and axis.bound_frame_id != frame.frame_id:
                edges[frame.frame_id].add(axis.bound_frame_id)

    def _reaches(start: str, target: str, seen: set[str]) -> bool:
        if start == target:
            return True
        if start in seen:
            return False
        seen.add(start)
        return any(
            _reaches(next_id, target, seen) for next_id in edges.get(start, ())
        )

    for frame_id, nexts in edges.items():
        for next_id in nexts:
            if _reaches(next_id, frame_id, set()):
                raise _fail(V2ValidationReason.frame_cycle)

    def _axis_exists(frame_id: str, axis: str) -> bool:
        frame = frame_by_id.get(frame_id)
        return frame is not None and any(item.axis == axis for item in frame.axes)

    # --- angle datums -------------------------------------------------------
    for datum in augmentation.angle_datums:
        if datum.measured_from_frame_id not in frame_by_id:
            raise _fail(V2ValidationReason.angle_datum_frame_unknown)
        if not _axis_exists(datum.measured_from_frame_id, datum.measured_from_axis):
            raise _fail(V2ValidationReason.angle_datum_axis_unknown)
        if datum.measured_to_frame_id is not None:
            if datum.measured_to_frame_id not in frame_by_id:
                raise _fail(V2ValidationReason.angle_datum_frame_unknown)
            if datum.measured_to_axis is not None and not _axis_exists(
                datum.measured_to_frame_id, datum.measured_to_axis
            ):
                raise _fail(V2ValidationReason.angle_datum_axis_unknown)
    if _duplicates(item.quantity_id for item in augmentation.angle_datums):
        # Two datums for one angle are two readings of the same number.
        raise _fail(V2ValidationReason.ambiguous_angle_datum)

    # --- motion senses ------------------------------------------------------
    for sense in augmentation.motion_senses:
        if sense.frame_id not in frame_by_id:
            raise _fail(V2ValidationReason.motion_sense_frame_unknown)
        if not _axis_exists(sense.frame_id, sense.axis):
            raise _fail(V2ValidationReason.motion_sense_axis_unknown)
    # An event-scoped sense states one moment.  A second sense over the whole
    # interval for the same subject would be that instant promoted to a span,
    # which is the B16 defect exactly.
    event_scoped = {
        sense.subject_id
        for sense in augmentation.motion_senses
        if sense.event_id is not None
    }
    for sense in augmentation.motion_senses:
        if sense.interval_id is not None and sense.subject_id in event_scoped:
            raise _fail(V2ValidationReason.event_scoped_sense_used_interval_wide)

    for sense in augmentation.motion_senses:
        # `up_slope` and `down_slope` name a direction relative to the hill, and
        # turning that into a sign on a tangent axis requires knowing which way
        # the tangent points.  A self-referential tangent binding — the only
        # kind an incline frame carries — states an identity and no orientation,
        # so the sign would come from a convention rather than from the source.
        #
        # This is not hypothetical.  `SENSE_SIGN` maps `down_slope` to -1, which
        # assumes an up-slope-positive tangent; the engine's own kinetic-slide
        # law resolves the same axis down-slope-positive and drives `+g sin θ`
        # along it.  A slide authored with the slope-relative member therefore
        # reached the *up-slope* formula and produced a confidently wrong
        # number — the gold-scored shadow caught it as three wrong answers.
        #
        # The axis-relative members carry no such assumption: `along_axis_positive`
        # means the +tangent direction the frame declares, whatever that is.  So a
        # sense on a slope tangent must be stated that way, and the ambiguous
        # spelling is refused rather than silently resolved.
        frame = frame_by_id[sense.frame_id]
        if (
            frame.frame_type is FrameType.incline_tangent_normal
            and sense.axis == _INCLINE_TANGENT_AXIS
            and sense.sense not in _AXIS_RELATIVE_MOTION_SENSES
        ):
            raise _fail(
                V2ValidationReason.slope_sense_requires_axis_relative_statement
            )

    # --- contact sides ------------------------------------------------------
    for contact in augmentation.contact_sides:
        # An axis-relative side carries its normal binding (enforced at the
        # record); a centre- or track-relative side names its reference in its
        # own meaning and may omit the binding.  A binding, once stated, must
        # resolve.
        if contact.normal_frame_id is not None:
            if contact.normal_frame_id not in frame_by_id:
                raise _fail(V2ValidationReason.contact_side_frame_unknown)
            if not _axis_exists(contact.normal_frame_id, contact.normal_axis):
                raise _fail(V2ValidationReason.contact_side_axis_unknown)
        if interactions and contact.interaction_id not in interactions:
            raise _fail(V2ValidationReason.interaction_target_without_interaction)
        if contact.contact_loss_event_id is not None and events and (
            contact.contact_loss_event_id not in events
        ):
            raise _fail(V2ValidationReason.cross_event_scope)
    by_interaction: dict[str, set[str]] = {}
    for contact in augmentation.contact_sides:
        by_interaction.setdefault(contact.interaction_id, set()).add(contact.side.value)
    if any(len(sides) > 1 for sides in by_interaction.values()):
        raise _fail(V2ValidationReason.conflicting_contact_sides)

    # --- endpoints ----------------------------------------------------------
    for endpoint in augmentation.endpoint_conditions:
        if events and endpoint.boundary_event_id not in events:
            raise _fail(V2ValidationReason.endpoint_without_event)
    if _duplicates(
        item.boundary_event_id for item in augmentation.endpoint_conditions
    ):
        raise _fail(V2ValidationReason.duplicate_endpoint)

    # --- constraints and interaction targets --------------------------------
    for constraint in augmentation.constraint_authorities:
        if entities and any(
            participant not in entities for participant in constraint.participant_ids
        ):
            raise _fail(V2ValidationReason.constraint_without_participants)
    for target in augmentation.interaction_targets:
        if interactions and target.interaction_id not in interactions:
            raise _fail(V2ValidationReason.interaction_target_without_interaction)
        if entities and target.participant_id not in entities:
            raise _fail(V2ValidationReason.subject_unknown)
        if target.frame_id is not None and target.frame_id not in frame_by_id:
            raise _fail(V2ValidationReason.motion_sense_frame_unknown)

    # --- objectives ---------------------------------------------------------
    for objective in augmentation.query_objectives:
        if queries and objective.query_id not in queries:
            raise _fail(V2ValidationReason.duplicate_query_objective)
    if _duplicates(item.query_id for item in augmentation.query_objectives):
        raise _fail(V2ValidationReason.duplicate_query_objective)

    # --- signed scalars -----------------------------------------------------
    for encoding in augmentation.scalar_encodings:
        if encoding.encoding is ScalarEncoding.contradictory_double_sign:
            # Naming the contradiction is allowed; using it is not.  The two
            # readings are mirror-image physics and neither may be chosen.
            raise _fail(V2ValidationReason.contradictory_scalar_encoding)
        if encoding.encoding is ScalarEncoding.signed_component:
            if encoding.frame_id is None or encoding.axis is None:
                raise _fail(V2ValidationReason.scalar_encoding_without_axis)
            if encoding.frame_id not in frame_by_id:
                raise _fail(V2ValidationReason.motion_sense_frame_unknown)
            if not _axis_exists(encoding.frame_id, encoding.axis):
                raise _fail(V2ValidationReason.scalar_encoding_without_axis)
    if _duplicates(item.quantity_id for item in augmentation.scalar_encodings):
        raise _fail(V2ValidationReason.contradictory_scalar_encoding)


def augmentation_is_valid(
    augmentation: CorpusV2AugmentationV1, **known: Sequence[str]
) -> bool:
    """Convenience predicate.  Prefer `validate_augmentation` for the reason."""

    try:
        validate_augmentation(augmentation, **known)
    except V2ValidationError:
        return False
    return True


__all__ = [
    "CORPUS_V2_VALIDATION_VERSION",
    "V2ValidationError",
    "V2ValidationReason",
    "augmentation_is_valid",
    "validate_augmentation",
]
