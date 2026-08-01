"""Typed carriers the v1 public corpus contract has no field for.

B22's corrected measurement counts six of them: a reference frame, an axis
direction, an angle datum, a motion sense, a contact side, and a frame binding
for a quantity.  (The first published count said seven; the query objective
was misclassified — v1's controlled `query.output_key = minimum_speed` already
states `minimum`, so v2 *refines* that carrier rather than introducing it.)
Every revoked closure in this evaluator's history needed one of the missing
carriers and, finding none, made one up.  This module is the place to state
them.

Three rules shape every record here, and each exists because a revoked package
broke it.

*A carrier without evidence is an assertion.*  Every record carries
`evidence_refs` into the source's own evidence, and the validator rejects an
empty one.  B15 minted a tangent/world-x binding out of a bare zero and then
read that binding back as evidence the orientation had been stated.

*A carrier without scope is a carrier applied everywhere.*  Every record names
the subject it is about and the interval or event it holds over.  B16 promoted
an `initial_velocity` instant to a whole interval, which is true only of a body
that never turns around.

*A missing carrier is refused, never defaulted.*  There is no default
orientation, no default contact side, no default endpoint, and no default
motion sense.  A `None` here means the source did not say, and the reader has
to fail closed rather than choose.

None of this is inferred at runtime.  These records are authored, migrated in
from an explicit manifest, and read — never derived from problem text, from a
label, from a family, or from an expected answer.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from evaluation.phase56_stage7.contracts import FrozenStrictModel


CORPUS_V2_SCHEMA_VERSION = "dynatutor-ko-corpus-v2.0-candidate"
CORPUS_V2_RECORD_BINDING_VERSION = "phase56-stage7-corpus-v2-record-binding-v2"

# Identifiers authored inside a v2 augmentation.  The prefix is reserved and
# enforced: an augmentation may not mint an identifier that could collide with
# one the v1 source already authored, because a collision would let a migrated
# record silently rebind a source relation.
V2_IDENTIFIER_PREFIX = "v2_"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    ),
]
EvidenceRef = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]


class FrameType(str, Enum):
    """Every frame the v2 contract can state."""

    world_cartesian = "world_cartesian"
    surface_tangent_normal = "surface_tangent_normal"
    incline_tangent_normal = "incline_tangent_normal"
    polar_radial_transverse = "polar_radial_transverse"
    body_fixed = "body_fixed"
    translating = "translating"
    rotating = "rotating"
    line_of_impact = "line_of_impact"


class AxisSense(str, Enum):
    """Which way a named axis points, relative to what it is anchored on."""

    up_the_page = "up_the_page"
    down_the_page = "down_the_page"
    along_surface_forward = "along_surface_forward"
    along_surface_backward = "along_surface_backward"
    away_from_surface = "away_from_surface"
    into_surface = "into_surface"
    up_slope = "up_slope"
    down_slope = "down_slope"
    outward_from_centre = "outward_from_centre"
    inward_to_centre = "inward_to_centre"
    along_line_of_impact = "along_line_of_impact"


class OrientationConvention(str, Enum):
    clockwise_positive = "clockwise_positive"
    counterclockwise_positive = "counterclockwise_positive"


class FrameOriginKind(str, Enum):
    """Where a stated frame's origin is anchored.

    ``world`` is its own member because the engine's `WorldOrigin` is its own
    type: a world frame anchored to a pseudo entity is a different — wrong —
    statement, and the first frame projection made exactly that mistake.
    """

    world = "world"
    entity = "entity"
    point = "point"


class MotionSense(str, Enum):
    """The vocabulary a source may use to say which way a body is going."""

    along_axis_positive = "along_axis_positive"
    along_axis_negative = "along_axis_negative"
    up_slope = "up_slope"
    down_slope = "down_slope"
    inward = "inward"
    outward = "outward"
    clockwise = "clockwise"
    counterclockwise = "counterclockwise"
    approaching = "approaching"
    separating = "separating"


class ContactSide(str, Enum):
    """Which side of a one-sided contact the body is on."""

    inward = "inward"
    outward = "outward"
    inside_track = "inside_track"
    outside_track = "outside_track"
    bilateral = "bilateral"
    unilateral_positive_normal = "unilateral_positive_normal"
    unilateral_negative_normal = "unilateral_negative_normal"


class EndpointCondition(str, Enum):
    """What holds at the moment an interval ends."""

    reaches_natural_length = "reaches_natural_length"
    zero_spring_deformation = "zero_spring_deformation"
    highest_point = "highest_point"
    returns_to_height = "returns_to_height"
    reaches_position = "reaches_position"
    comes_to_rest = "comes_to_rest"
    contact_loss = "contact_loss"
    collision_start = "collision_start"
    collision_end = "collision_end"
    specified_time = "specified_time"
    specified_displacement = "specified_displacement"


class ConstraintAuthority(str, Enum):
    """A constraint the source states rather than one a closure assumes."""

    no_slip = "no_slip"
    inextensible = "inextensible"
    massless_rope = "massless_rope"
    fixed_axis = "fixed_axis"
    frictionless_axle = "frictionless_axle"
    fixed_pulley = "fixed_pulley"
    rolling_without_slipping = "rolling_without_slipping"
    contact_maintained = "contact_maintained"
    contact_limit = "contact_limit"
    instantaneous_center = "instantaneous_center"
    common_rotation_center = "common_rotation_center"


class InteractionSide(str, Enum):
    action = "action"
    reaction = "reaction"


class ForceComponentKind(str, Enum):
    force = "force"
    moment = "moment"


class QueryObjective(str, Enum):
    minimum = "minimum"
    maximum = "maximum"


class ScalarEncoding(str, Enum):
    """How a source expressed a signed quantity.

    `contradictory_double_sign` exists so a validator can name the B18 defect
    instead of silently picking one of two mirror-image readings.
    """

    magnitude_with_direction = "magnitude_with_direction"
    signed_component = "signed_component"
    directionless_zero = "directionless_zero"
    contradictory_double_sign = "contradictory_double_sign"


class _Evidenced(FrozenStrictModel):
    """Every v2 carrier is evidenced.  An unevidenced one is an assertion."""

    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1, max_length=16)


class _Scoped(_Evidenced):
    """Every v2 carrier names what it is about and when it holds.

    `interval_id` and `event_id` are both optional and both meaningful: a
    carrier with neither is timeless, one with an interval holds across it, and
    one with an event holds at that instant only.  Carrying both is refused by
    the validator, because a statement that is simultaneously about an instant
    and about a span is two statements.
    """

    subject_id: Identifier
    interval_id: Identifier | None = None
    event_id: Identifier | None = None


class FrameAxisV2(_Evidenced):
    """One named axis of one frame: its identity binding, and which way it points.

    The *binding* is the projection authority: a typed ``axis(frame, name,
    sign)`` triple, exactly what the engine's `AxisDirection` holds and what
    the B15/B16 hardening consumes.  A self-referential binding states an
    identity (this frame's tangent is its own tangential direction); a binding
    into another frame states a coincidence (this support's tangent *is* the
    world's x).  The sign is part of the statement — ``along_surface_forward``
    and ``along_surface_backward`` are opposite directions, and a projection
    that collapses them has changed the physics.

    `sense` remains as descriptive vocabulary and is **not** projection
    authority: an axis whose binding is incomplete is refused, never inferred
    from its sense's spelling.
    """

    axis: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    sense: AxisSense
    # What the sense is measured against: a surface, an incline, a centre.
    anchor_entity_id: Identifier | None = None
    # The typed identity binding.  All three travel together; a partial
    # binding is refused by the validator rather than completed by a default.
    bound_frame_id: Identifier | None = None
    bound_axis: Annotated[
        str, StringConstraints(min_length=1, max_length=16)
    ] | None = None
    bound_sign: Literal[-1, 1] | None = None

    @property
    def binding_complete(self) -> bool:
        return (
            self.bound_frame_id is not None
            and self.bound_axis is not None
            and self.bound_sign is not None
        )


class ReferenceFrameV2(_Scoped):
    """A frame the source states, with every axis bound to a direction."""

    frame_id: Identifier
    frame_type: FrameType
    origin_kind: FrameOriginKind | None = None
    origin_point_id: Identifier | None = None
    parent_frame_id: Identifier | None = None
    axes: tuple[FrameAxisV2, ...] = Field(min_length=1, max_length=3)
    translating_with_entity_id: Identifier | None = None
    rotating_about_point_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_frame(self) -> "ReferenceFrameV2":
        if self.parent_frame_id == self.frame_id:
            raise ValueError("a frame cannot be its own parent")
        names = [axis.axis for axis in self.axes]
        if len(names) != len(set(names)):
            raise ValueError("frame axes must be distinctly named")
        if self.frame_type is FrameType.translating and not self.translating_with_entity_id:
            raise ValueError("a translating frame must name what it translates with")
        if self.frame_type is FrameType.rotating and not self.rotating_about_point_id:
            raise ValueError("a rotating frame must name what it rotates about")
        if self.origin_kind is FrameOriginKind.point and not self.origin_point_id:
            raise ValueError("a point origin must name its point")
        if self.origin_kind is FrameOriginKind.world and self.origin_point_id:
            raise ValueError("a world origin carries no point identifier")
        if self.origin_kind is FrameOriginKind.entity and self.origin_point_id:
            raise ValueError("an entity origin carries no point identifier")
        return self

    @property
    def resolved_origin_kind(self) -> FrameOriginKind:
        """The stated origin kind, or the deterministic typed reading.

        A world frame is anchored at the world; a frame with a point is
        anchored at that point; everything else is anchored at its subject
        entity.  This resolves *shape*, never physics: it decides which typed
        engine origin holds the anchor the record already names.
        """

        if self.origin_kind is not None:
            return self.origin_kind
        if self.frame_type is FrameType.world_cartesian:
            return FrameOriginKind.world
        if self.origin_point_id is not None:
            return FrameOriginKind.point
        return FrameOriginKind.entity


class AngleDatumV2(_Scoped):
    """What an angle is measured from, and to.

    An angle's number means nothing without both.  B15's zero was equally
    consistent with a plane level to the world, a plane measured from the
    vertical, and a plane measured from a second surface.
    """

    datum_id: Identifier
    quantity_id: Identifier
    measured_from_frame_id: Identifier
    measured_from_axis: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    measured_to_frame_id: Identifier | None = None
    measured_to_axis: Annotated[
        str, StringConstraints(min_length=1, max_length=16)
    ] | None = None
    measured_to_entity_tangent_id: Identifier | None = None
    orientation: OrientationConvention
    signed: bool

    @model_validator(mode="after")
    def validate_datum(self) -> "AngleDatumV2":
        to_axis = self.measured_to_axis is not None and self.measured_to_frame_id
        to_tangent = self.measured_to_entity_tangent_id is not None
        if to_axis and to_tangent:
            raise ValueError("an angle datum names one second reference, not two")
        if not to_axis and not to_tangent:
            raise ValueError("an angle datum must name what it is measured to")
        return self


class MotionSenseV2(_Scoped):
    """Which way a body is going, bound to an axis of a stated frame."""

    sense_id: Identifier
    sense: MotionSense
    frame_id: Identifier
    axis: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    sign: Literal[-1, 1]
    quantity_id: Identifier | None = None


class ContactSideV2(_Scoped):
    """Which side of a contact a body is on, and over what span."""

    contact_id: Identifier
    interaction_id: Identifier
    side: ContactSide
    normal_frame_id: Identifier
    normal_axis: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    contact_loss_event_id: Identifier | None = None


class EndpointConditionV2(_Scoped):
    """What holds at an interval boundary, beyond naming when it is."""

    endpoint_id: Identifier
    condition: EndpointCondition
    boundary_event_id: Identifier
    condition_quantity_id: Identifier | None = None
    condition_expression: Annotated[
        str, StringConstraints(min_length=1, max_length=240)
    ] | None = None


class ConstraintAuthorityV2(_Scoped):
    """A constraint with its participants named."""

    constraint_id: Identifier
    authority: ConstraintAuthority
    participant_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=8)


class InteractionTargetV2(_Scoped):
    """Which force a system-level force query is asking about."""

    target_id: Identifier
    interaction_id: Identifier
    participant_id: Identifier
    side: InteractionSide
    component_kind: ForceComponentKind
    point_id: Identifier | None = None
    frame_id: Identifier | None = None


class QueryObjectiveV2(_Evidenced):
    """An extremum the source asks for, rather than an output name that sounds like one."""

    objective_id: Identifier
    query_id: Identifier
    objective: QueryObjective


class ScalarEncodingV2(_Scoped):
    """How one quantity's sign is meant, stated rather than guessed."""

    encoding_id: Identifier
    quantity_id: Identifier
    encoding: ScalarEncoding
    frame_id: Identifier | None = None
    axis: Annotated[str, StringConstraints(min_length=1, max_length=16)] | None = None


class CorpusV2AugmentationV1(FrozenStrictModel):
    """Everything a v2 record adds to its v1 original.

    The v1 record is not edited.  It is carried through byte-identical and
    fingerprinted, and everything below sits beside it — so a v2 record can
    always be reduced back to exactly the v1 record it came from.
    """

    schema_version: Literal[CORPUS_V2_SCHEMA_VERSION] = CORPUS_V2_SCHEMA_VERSION
    binding_version: Literal[CORPUS_V2_RECORD_BINDING_VERSION] = (
        CORPUS_V2_RECORD_BINDING_VERSION
    )
    reference_frames: tuple[ReferenceFrameV2, ...] = Field(default=(), max_length=16)
    angle_datums: tuple[AngleDatumV2, ...] = Field(default=(), max_length=16)
    motion_senses: tuple[MotionSenseV2, ...] = Field(default=(), max_length=16)
    contact_sides: tuple[ContactSideV2, ...] = Field(default=(), max_length=16)
    endpoint_conditions: tuple[EndpointConditionV2, ...] = Field(
        default=(), max_length=16
    )
    constraint_authorities: tuple[ConstraintAuthorityV2, ...] = Field(
        default=(), max_length=16
    )
    interaction_targets: tuple[InteractionTargetV2, ...] = Field(
        default=(), max_length=16
    )
    query_objectives: tuple[QueryObjectiveV2, ...] = Field(default=(), max_length=8)
    scalar_encodings: tuple[ScalarEncodingV2, ...] = Field(default=(), max_length=16)

    @property
    def is_empty(self) -> bool:
        """True when the augmentation states nothing.

        An empty augmentation is legal and meaningful: it says this context was
        looked at and nothing could be added from the source.  It is not the
        same as a context nobody examined, which has no manifest entry at all.
        """

        return not any(
            (
                self.reference_frames,
                self.angle_datums,
                self.motion_senses,
                self.contact_sides,
                self.endpoint_conditions,
                self.constraint_authorities,
                self.interaction_targets,
                self.query_objectives,
                self.scalar_encodings,
            )
        )

    def carrier_counts(self) -> tuple[tuple[str, int], ...]:
        return (
            ("angle_datum", len(self.angle_datums)),
            ("constraint_authority", len(self.constraint_authorities)),
            ("contact_side", len(self.contact_sides)),
            ("endpoint_condition", len(self.endpoint_conditions)),
            ("interaction_target", len(self.interaction_targets)),
            ("motion_sense", len(self.motion_senses)),
            ("query_objective", len(self.query_objectives)),
            ("reference_frame", len(self.reference_frames)),
            ("scalar_encoding", len(self.scalar_encodings)),
        )


__all__ = [
    "CORPUS_V2_RECORD_BINDING_VERSION",
    "CORPUS_V2_SCHEMA_VERSION",
    "V2_IDENTIFIER_PREFIX",
    "AngleDatumV2",
    "AxisSense",
    "ConstraintAuthority",
    "ConstraintAuthorityV2",
    "ContactSide",
    "ContactSideV2",
    "CorpusV2AugmentationV1",
    "EndpointCondition",
    "EndpointConditionV2",
    "ForceComponentKind",
    "FrameAxisV2",
    "FrameOriginKind",
    "FrameType",
    "InteractionSide",
    "InteractionTargetV2",
    "MotionSense",
    "MotionSenseV2",
    "OrientationConvention",
    "QueryObjective",
    "QueryObjectiveV2",
    "ReferenceFrameV2",
    "ScalarEncoding",
    "ScalarEncodingV2",
]
