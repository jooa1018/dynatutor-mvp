from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Mapping, TypeAlias, Union

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from engine.mechanics.math_ast import (
    DimensionVector,
    MathExpression,
    RelationExpression,
    SymbolDefinition,
)


DRAFT_SCHEMA_NAME = "dynatutor.mechanics_problem_draft"
DRAFT_SCHEMA_VERSION = "1.0"
IR_SCHEMA_NAME = "dynatutor.mechanics_problem_ir"
IR_SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "mechanics-contract-v1"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
    ),
]
DiagnosticLabel = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$",
    ),
]
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
LongText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)
]
EvidenceQuote = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
RawValue = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
RawUnit = Annotated[str, StringConstraints(strip_whitespace=True, max_length=48)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _reject_bool_as_finite_float(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("boolean is not a finite float")
    return value


FiniteFloat = Annotated[
    float,
    BeforeValidator(_reject_bool_as_finite_float),
    Field(allow_inf_nan=False, ge=-1.0e300, le=1.0e300),
]
VectorSIValue: TypeAlias = Annotated[
    tuple[FiniteFloat, ...], Field(min_length=1, max_length=3)
]
TensorSIValueRow: TypeAlias = Annotated[
    tuple[FiniteFloat, ...], Field(min_length=1, max_length=3)
]
TensorSIValue: TypeAlias = Annotated[
    tuple[TensorSIValueRow, ...], Field(min_length=1, max_length=3)
]
SIValue: TypeAlias = Union[FiniteFloat, VectorSIValue, TensorSIValue]
Confidence = Annotated[float, Field(allow_inf_nan=False, ge=0.0, le=1.0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# Accepted IR objects cross the modeler/validator trust boundary and may be
# cached or compiled later.  Every accepted-IR model uses this configuration;
# authoring DraftV1 models deliberately retain the ordinary mutable config.
_IMMUTABLE_IR_CONFIG = ConfigDict(
    extra="forbid",
    str_strip_whitespace=True,
    frozen=True,
    revalidate_instances="always",
)


class ProblemLanguage(str, Enum):
    ko = "ko"
    en = "en"
    mixed = "mixed"
    unknown = "unknown"


class MechanicsMetadata(StrictModel):
    language: ProblemLanguage
    correction_revision: int = Field(ge=0, le=1_000_000)
    system_type: DiagnosticLabel | None = None
    subtype: DiagnosticLabel | None = None
    model_id: DiagnosticLabel | None = None
    model_hash: Sha256 | None = None
    prompt_hash: Sha256 | None = None
    source_text_sha256: Sha256 | None = None
    model_confidence: Confidence | None = None


class SourceAssetKind(str, Enum):
    image = "image"
    page = "page"
    document = "document"


class SourceAsset(StrictModel):
    asset_id: Identifier
    kind: SourceAssetKind
    content_sha256: Sha256
    media_type: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=3,
            max_length=80,
            pattern=r"^[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+$",
        ),
    ]
    page_id: Identifier | None = None
    page_number: int | None = Field(default=None, ge=1, le=100_000)
    parent_asset_id: Identifier | None = None


class SourceSpan(StrictModel):
    start: int = Field(ge=0, le=10_000_000)
    end: int = Field(ge=1, le=10_000_000)

    @model_validator(mode="after")
    def validate_order(self) -> "SourceSpan":
        if self.end <= self.start:
            raise ValueError("source span end must be greater than start")
        return self


class TextEvidence(StrictModel):
    kind: Literal["text"] = "text"
    evidence_id: Identifier
    quote: EvidenceQuote
    source_span: SourceSpan
    quantity_span: SourceSpan | None = None
    occurrence_index: int = Field(ge=0, le=999)


class NormalizedPoint(StrictModel):
    x: float = Field(allow_inf_nan=False, ge=0.0, le=1.0)
    y: float = Field(allow_inf_nan=False, ge=0.0, le=1.0)


class NormalizedBBox(StrictModel):
    left: float = Field(allow_inf_nan=False, ge=0.0, le=1.0)
    top: float = Field(allow_inf_nan=False, ge=0.0, le=1.0)
    right: float = Field(allow_inf_nan=False, ge=0.0, le=1.0)
    bottom: float = Field(allow_inf_nan=False, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_area(self) -> "NormalizedBBox":
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("normalized bbox must have positive area")
        return self


class FigureRegion(StrictModel):
    bbox: NormalizedBBox | None = None
    polygon: list[NormalizedPoint] | None = Field(
        default=None, min_length=3, max_length=32
    )

    @model_validator(mode="after")
    def validate_one_region(self) -> "FigureRegion":
        if (self.bbox is None) == (self.polygon is None):
            raise ValueError("figure region requires exactly one of bbox or polygon")
        return self


class FigureEvidence(StrictModel):
    kind: Literal["figure"] = "figure"
    evidence_id: Identifier
    asset_id: Identifier
    page_id: Identifier | None = None
    region: FigureRegion
    recognized_label: ShortText | None = None
    visual_relation: ShortText | None = None
    confidence: Confidence


SourceEvidence: TypeAlias = Annotated[
    Union[TextEvidence, FigureEvidence], Field(discriminator="kind")
]


class EntityPrimitive(str, Enum):
    particle = "particle"
    rigid_body = "rigid_body"
    body_component = "body_component"
    point = "point"
    mass_center = "mass_center"
    system = "system"
    surface = "surface"
    incline = "incline"
    rope = "rope"
    pulley = "pulley"
    spring = "spring"
    damper = "damper"
    joint = "joint"
    slot = "slot"
    gear = "gear"
    rack = "rack"
    reference_frame = "reference_frame"
    field = "field"
    environment = "environment"


class Entity(StrictModel):
    entity_id: Identifier
    primitive: EntityPrimitive
    label: ShortText | None = None
    aliases: list[ShortText] = Field(default_factory=list, max_length=12)
    component_of_entity_id: Identifier | None = None
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)
    model_confidence: Confidence | None = None


class PointRole(str, Enum):
    material = "material"
    geometric = "geometric"
    mass_center = "mass_center"
    contact = "contact"
    joint = "joint"
    reference = "reference"
    unspecified = "unspecified"


class Point(StrictModel):
    point_id: Identifier
    role: PointRole
    owner_entity_id: Identifier | None = None
    frame_id: Identifier | None = None
    label: ShortText | None = None
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class ReferenceFrameType(str, Enum):
    cartesian_1d = "cartesian_1d"
    cartesian_2d = "cartesian_2d"
    cartesian_3d = "cartesian_3d"
    tangential_normal = "tangential_normal"
    radial_transverse = "radial_transverse"
    body_fixed = "body_fixed"
    translating = "translating"
    rotating = "rotating"
    generalized_coordinate = "generalized_coordinate"


class WorldOrigin(StrictModel):
    kind: Literal["world"] = "world"


class PointOrigin(StrictModel):
    kind: Literal["point"] = "point"
    point_id: Identifier


class EntityOrigin(StrictModel):
    kind: Literal["entity"] = "entity"
    entity_id: Identifier


class FrameOrigin(StrictModel):
    kind: Literal["frame"] = "frame"
    frame_id: Identifier


OriginBinding: TypeAlias = Annotated[
    Union[WorldOrigin, PointOrigin, EntityOrigin, FrameOrigin],
    Field(discriminator="kind"),
]


class AxisName(str, Enum):
    x = "x"
    y = "y"
    z = "z"
    tangent = "tangent"
    normal = "normal"
    radial = "radial"
    transverse = "transverse"
    generalized = "generalized"


class AxisDirection(StrictModel):
    kind: Literal["axis"] = "axis"
    frame_id: Identifier
    axis: AxisName
    sign: Literal[-1, 1] = 1


class VectorDirection(StrictModel):
    kind: Literal["vector"] = "vector"
    frame_id: Identifier
    components: list[FiniteFloat] = Field(min_length=1, max_length=3)


class SymbolDirection(StrictModel):
    kind: Literal["symbol"] = "symbol"
    symbol_id: Identifier
    frame_id: Identifier | None = None


class SemanticDirectionName(str, Enum):
    positive = "positive"
    negative = "negative"
    upward = "upward"
    downward = "downward"
    left = "left"
    right = "right"
    clockwise = "clockwise"
    counterclockwise = "counterclockwise"
    along_motion = "along_motion"
    opposite_motion = "opposite_motion"
    radial = "radial"
    transverse = "transverse"
    tangential = "tangential"
    normal = "normal"
    unspecified = "unspecified"


class SemanticDirection(StrictModel):
    kind: Literal["semantic"] = "semantic"
    direction: SemanticDirectionName


DirectionBinding: TypeAlias = Annotated[
    Union[AxisDirection, VectorDirection, SymbolDirection, SemanticDirection],
    Field(discriminator="kind"),
]


class IRAxisDirection(AxisDirection):
    model_config = _IMMUTABLE_IR_CONFIG


class IRVectorDirection(VectorDirection):
    model_config = _IMMUTABLE_IR_CONFIG

    components: tuple[FiniteFloat, ...] = Field(min_length=1, max_length=3)


class IRSymbolDirection(SymbolDirection):
    model_config = _IMMUTABLE_IR_CONFIG


class IRSemanticDirection(SemanticDirection):
    model_config = _IMMUTABLE_IR_CONFIG


IRDirectionBinding: TypeAlias = Annotated[
    Union[
        IRAxisDirection,
        IRVectorDirection,
        IRSymbolDirection,
        IRSemanticDirection,
    ],
    Field(discriminator="kind"),
]


class AxisBinding(StrictModel):
    axis: AxisName
    direction: DirectionBinding


class ReferenceFrame(StrictModel):
    frame_id: Identifier
    frame_type: ReferenceFrameType
    origin: OriginBinding
    axes: list[AxisBinding] = Field(min_length=1, max_length=3)
    parent_frame_id: Identifier | None = None
    translating_with_entity_id: Identifier | None = None
    rotating_about_point_id: Identifier | None = None
    generalized_coordinate_symbol_ids: list[Identifier] = Field(
        default_factory=list, max_length=16
    )
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class EventKind(str, Enum):
    start = "start"
    release = "release"
    collision_start = "collision_start"
    collision_end = "collision_end"
    contact_start = "contact_start"
    contact_end = "contact_end"
    reaches_condition = "reaches_condition"
    turnaround = "turnaround"
    comes_to_rest = "comes_to_rest"
    rope_taut = "rope_taut"
    rope_slack = "rope_slack"
    finish = "finish"
    other = "other"


class MotionInterval(StrictModel):
    interval_id: Identifier
    order: int = Field(ge=1, le=256)
    subject_ids: list[Identifier] = Field(min_length=1, max_length=64)
    frame_id: Identifier | None = None
    start_event_id: Identifier | None = None
    end_event_id: Identifier | None = None
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class Event(StrictModel):
    event_id: Identifier
    kind: EventKind
    subject_ids: list[Identifier] = Field(default_factory=list, max_length=64)
    interval_ids: list[Identifier] = Field(default_factory=list, max_length=16)
    time_quantity_id: Identifier | None = None
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class QuantityRole(str, Enum):
    mass = "mass"
    position = "position"
    displacement = "displacement"
    distance = "distance"
    height = "height"
    time = "time"
    duration = "duration"
    velocity = "velocity"
    speed = "speed"
    acceleration = "acceleration"
    angle = "angle"
    angular_position = "angular_position"
    angular_velocity = "angular_velocity"
    angular_acceleration = "angular_acceleration"
    force = "force"
    moment = "moment"
    torque = "torque"
    momentum = "momentum"
    angular_momentum = "angular_momentum"
    impulse = "impulse"
    work = "work"
    energy = "energy"
    power = "power"
    stiffness = "stiffness"
    damping = "damping"
    coefficient_friction = "coefficient_friction"
    coefficient_restitution = "coefficient_restitution"
    radius = "radius"
    length = "length"
    area = "area"
    volume = "volume"
    density = "density"
    moment_of_inertia = "moment_of_inertia"
    gravity = "gravity"
    frequency = "frequency"
    period = "period"
    generalized_coordinate = "generalized_coordinate"
    generalized_speed = "generalized_speed"
    count = "count"
    other = "other"


class QuantityShape(str, Enum):
    scalar = "scalar"
    vector = "vector"
    tensor = "tensor"


class QuantityComponent(str, Enum):
    magnitude = "magnitude"
    x = "x"
    y = "y"
    z = "z"
    radial = "radial"
    transverse = "transverse"
    tangential = "tangential"
    normal = "normal"
    clockwise = "clockwise"
    counterclockwise = "counterclockwise"
    unspecified = "unspecified"


class Provenance(str, Enum):
    explicit_source = "explicit_source"
    user_correction = "user_correction"
    inferred = "inferred"
    server_default = "server_default"
    unknown = "unknown"


class QuantityBase(StrictModel):
    quantity_id: Identifier
    symbol_id: Identifier | None = None
    role: QuantityRole
    subject_id: Identifier
    point_id: Identifier | None = None
    frame_id: Identifier | None = None
    interval_id: Identifier | None = None
    event_id: Identifier | None = None
    component: QuantityComponent = QuantityComponent.unspecified
    direction: DirectionBinding | None = None
    shape: QuantityShape
    dimension: DimensionVector
    provenance: Provenance
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)
    assumption_policy_ref: Identifier | None = None
    correction_id: Identifier | None = None
    model_confidence: Confidence | None = None


class DraftQuantity(QuantityBase):
    raw_value: RawValue | None = None
    raw_unit: RawUnit | None = None

    @model_validator(mode="after")
    def validate_raw_pair(self) -> "DraftQuantity":
        if (self.raw_value is None) != (self.raw_unit is None):
            raise ValueError("raw_value and raw_unit must be supplied together")
        return self


class IRQuantity(QuantityBase):
    model_config = _IMMUTABLE_IR_CONFIG

    direction: IRDirectionBinding | None = None
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)
    raw_value: RawValue | None = None
    raw_unit: RawUnit | None = None
    si_value: SIValue | None = None
    si_unit: RawUnit | None = None

    @model_validator(mode="after")
    def validate_normalized_pair(self) -> "IRQuantity":
        if (self.raw_value is None) != (self.raw_unit is None):
            raise ValueError("raw_value and raw_unit must be supplied together")
        if (self.si_value is None) != (self.si_unit is None):
            raise ValueError("si_value and si_unit must be supplied together")
        raw_pair = self.raw_value is not None and self.raw_unit is not None
        si_pair = self.si_value is not None and self.si_unit is not None
        if raw_pair != si_pair:
            raise ValueError("raw and normalized quantity pairs must agree")
        if self.si_value is not None:
            if self.shape is QuantityShape.scalar:
                if not isinstance(self.si_value, float):
                    raise ValueError("scalar quantity requires a scalar si_value")
            elif self.shape is QuantityShape.vector:
                if not (
                    isinstance(self.si_value, tuple)
                    and all(isinstance(component, float) for component in self.si_value)
                ):
                    raise ValueError("vector quantity requires a one-dimensional si_value")
            elif self.shape is QuantityShape.tensor:
                if not (
                    isinstance(self.si_value, tuple)
                    and all(
                        isinstance(row, tuple)
                        and all(isinstance(component, float) for component in row)
                        for row in self.si_value
                    )
                ):
                    raise ValueError("tensor quantity requires a two-dimensional si_value")
                if len({len(row) for row in self.si_value}) != 1:
                    raise ValueError("tensor si_value rows must be rectangular")
        return self


class GeometryRelationKind(str, Enum):
    coincident = "coincident"
    collinear = "collinear"
    parallel = "parallel"
    perpendicular = "perpendicular"
    distance = "distance"
    angle = "angle"
    radius = "radius"
    tangent = "tangent"
    lies_on = "lies_on"
    attached = "attached"
    topology_connects = "topology_connects"
    wraps = "wraps"
    meshed = "meshed"
    ratio = "ratio"


class GeometryRelation(StrictModel):
    relation_id: Identifier
    kind: GeometryRelationKind
    participant_ids: list[Identifier] = Field(min_length=1, max_length=16)
    expression: RelationExpression | None = None
    quantity_ids: list[Identifier] = Field(default_factory=list, max_length=16)
    interval_id: Identifier | None = None
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class InteractionKind(str, Enum):
    contact = "contact"
    gravity = "gravity"
    spring = "spring"
    damping = "damping"
    rope_tension = "rope_tension"
    joint_reaction = "joint_reaction"
    applied_force = "applied_force"
    field = "field"
    gear_contact = "gear_contact"
    collision = "collision"
    other = "other"


class Interaction(StrictModel):
    interaction_id: Identifier
    kind: InteractionKind
    participant_ids: list[Identifier] = Field(min_length=1, max_length=16)
    point_ids: list[Identifier] = Field(default_factory=list, max_length=8)
    frame_id: Identifier | None = None
    interval_id: Identifier | None = None
    event_id: Identifier | None = None
    quantity_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class ConstraintKind(str, Enum):
    kinematic = "kinematic"
    geometric = "geometric"
    dynamic = "dynamic"
    constitutive = "constitutive"
    boundary = "boundary"
    contact = "contact"
    rolling = "rolling"
    rope = "rope"
    joint = "joint"
    other = "other"


class Constraint(StrictModel):
    constraint_id: Identifier
    kind: ConstraintKind
    expression: RelationExpression
    subject_ids: list[Identifier] = Field(default_factory=list, max_length=16)
    interval_id: Identifier | None = None
    event_id: Identifier | None = None
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class StateKind(str, Enum):
    initial = "initial"
    final = "final"
    boundary = "boundary"
    contact = "contact"
    friction = "friction"
    rope = "rope"
    rolling = "rolling"
    motion = "motion"
    regime = "regime"


class StateValue(str, Enum):
    active = "active"
    inactive = "inactive"
    sticking = "sticking"
    sliding = "sliding"
    taut = "taut"
    slack = "slack"
    touching = "touching"
    separated = "separated"
    at_rest = "at_rest"
    moving = "moving"
    rolling = "rolling"
    no_slip = "no_slip"
    unknown = "unknown"


class StateCondition(StrictModel):
    state_condition_id: Identifier
    kind: StateKind
    state: StateValue
    subject_id: Identifier
    interval_id: Identifier | None = None
    event_id: Identifier | None = None
    expression: RelationExpression | None = None
    quantity_ids: list[Identifier] = Field(default_factory=list, max_length=16)
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class QueryTarget(StrictModel):
    role: QuantityRole
    subject_id: Identifier
    point_id: Identifier | None = None
    frame_id: Identifier | None = None
    interval_id: Identifier | None = None
    event_id: Identifier | None = None
    component: QuantityComponent = QuantityComponent.unspecified
    direction: DirectionBinding | None = None
    target_quantity_id: Identifier | None = None


class Query(StrictModel):
    query_id: Identifier
    target: QueryTarget
    output_unit: RawUnit
    output_dimension: DimensionVector
    shape: QuantityShape
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class Principle(str, Enum):
    kinematics = "kinematics"
    newton_second_law = "newton_second_law"
    work_energy = "work_energy"
    impulse_momentum = "impulse_momentum"
    angular_momentum = "angular_momentum"
    conservation_energy = "conservation_energy"
    conservation_momentum = "conservation_momentum"
    rigid_body_kinematics = "rigid_body_kinematics"
    relative_motion = "relative_motion"
    vibration = "vibration"
    other = "other"


class PrincipleHint(StrictModel):
    hint_id: Identifier
    principle: Principle
    scope_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)
    model_confidence: Confidence | None = None


class AssumptionDisposition(str, Enum):
    proposed = "proposed"
    approved = "approved"
    visible = "visible"
    rejected = "rejected"


class Assumption(StrictModel):
    assumption_id: Identifier
    kind: Identifier
    subject_id: Identifier
    interval_id: Identifier | None = None
    disposition: AssumptionDisposition
    proposed_role: QuantityRole | None = None
    proposed_value: RawValue | None = None
    proposed_unit: RawUnit | None = None
    reason: LongText
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_proposal_pair(self) -> "Assumption":
        if (self.proposed_value is None) != (self.proposed_unit is None):
            raise ValueError("assumption proposed_value and proposed_unit must be paired")
        return self


class AmbiguityKind(str, Enum):
    entity_binding = "entity_binding"
    point_binding = "point_binding"
    frame_binding = "frame_binding"
    interval_binding = "interval_binding"
    event_binding = "event_binding"
    quantity_binding = "quantity_binding"
    direction = "direction"
    occurrence = "occurrence"
    query = "query"
    assumption = "assumption"
    interpretation = "interpretation"
    other = "other"


class Ambiguity(StrictModel):
    ambiguity_id: Identifier
    kind: AmbiguityKind
    referenced_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    description: LongText
    blocking: bool
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class FigureDependencyLevel(str, Enum):
    none = "none"
    helpful = "helpful"
    required = "required"


class FigureDependency(StrictModel):
    level: FigureDependencyLevel
    missing_information: list[ShortText] = Field(default_factory=list, max_length=32)
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


class UnsupportedFeature(StrictModel):
    feature_code: Identifier
    description: LongText
    referenced_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=16)


# DraftV1 is an authoring contract and intentionally remains mutable.  The
# following narrow projections are used only by MechanicsProblemIRV1.  Besides
# freezing model attributes, every collection is a tuple and every nested
# mechanics model is another immutable projection.  Math-AST models are already
# frozen and tuple-backed in math_ast.py.
class IRMechanicsMetadata(MechanicsMetadata):
    model_config = _IMMUTABLE_IR_CONFIG


class IRSourceAsset(SourceAsset):
    model_config = _IMMUTABLE_IR_CONFIG


class IRSourceSpan(SourceSpan):
    model_config = _IMMUTABLE_IR_CONFIG


class IRTextEvidence(TextEvidence):
    model_config = _IMMUTABLE_IR_CONFIG

    source_span: IRSourceSpan
    quantity_span: IRSourceSpan | None = None


class IRNormalizedPoint(NormalizedPoint):
    model_config = _IMMUTABLE_IR_CONFIG


class IRNormalizedBBox(NormalizedBBox):
    model_config = _IMMUTABLE_IR_CONFIG


class IRFigureRegion(FigureRegion):
    model_config = _IMMUTABLE_IR_CONFIG

    bbox: IRNormalizedBBox | None = None
    polygon: tuple[IRNormalizedPoint, ...] | None = Field(
        default=None, min_length=3, max_length=32
    )


class IRFigureEvidence(FigureEvidence):
    model_config = _IMMUTABLE_IR_CONFIG

    region: IRFigureRegion


IRSourceEvidence: TypeAlias = Annotated[
    Union[IRTextEvidence, IRFigureEvidence], Field(discriminator="kind")
]


class IREntity(Entity):
    model_config = _IMMUTABLE_IR_CONFIG

    aliases: tuple[ShortText, ...] = Field(default_factory=tuple, max_length=12)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRPoint(Point):
    model_config = _IMMUTABLE_IR_CONFIG

    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRWorldOrigin(WorldOrigin):
    model_config = _IMMUTABLE_IR_CONFIG


class IRPointOrigin(PointOrigin):
    model_config = _IMMUTABLE_IR_CONFIG


class IREntityOrigin(EntityOrigin):
    model_config = _IMMUTABLE_IR_CONFIG


class IRFrameOrigin(FrameOrigin):
    model_config = _IMMUTABLE_IR_CONFIG


IROriginBinding: TypeAlias = Annotated[
    Union[IRWorldOrigin, IRPointOrigin, IREntityOrigin, IRFrameOrigin],
    Field(discriminator="kind"),
]


class IRAxisBinding(AxisBinding):
    model_config = _IMMUTABLE_IR_CONFIG

    direction: IRDirectionBinding


class IRReferenceFrame(ReferenceFrame):
    model_config = _IMMUTABLE_IR_CONFIG

    origin: IROriginBinding
    axes: tuple[IRAxisBinding, ...] = Field(min_length=1, max_length=3)
    generalized_coordinate_symbol_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=16
    )
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRMotionInterval(MotionInterval):
    model_config = _IMMUTABLE_IR_CONFIG

    subject_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IREvent(Event):
    model_config = _IMMUTABLE_IR_CONFIG

    subject_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    interval_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRGeometryRelation(GeometryRelation):
    model_config = _IMMUTABLE_IR_CONFIG

    participant_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    quantity_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRInteraction(Interaction):
    model_config = _IMMUTABLE_IR_CONFIG

    participant_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    point_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=8)
    quantity_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRConstraint(Constraint):
    model_config = _IMMUTABLE_IR_CONFIG

    subject_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRStateCondition(StateCondition):
    model_config = _IMMUTABLE_IR_CONFIG

    quantity_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRQueryTarget(QueryTarget):
    model_config = _IMMUTABLE_IR_CONFIG

    direction: IRDirectionBinding | None = None


class IRQuery(Query):
    model_config = _IMMUTABLE_IR_CONFIG

    target: IRQueryTarget
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRPrincipleHint(PrincipleHint):
    model_config = _IMMUTABLE_IR_CONFIG

    scope_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRAssumption(Assumption):
    model_config = _IMMUTABLE_IR_CONFIG

    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRAmbiguity(Ambiguity):
    model_config = _IMMUTABLE_IR_CONFIG

    referenced_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRFigureDependency(FigureDependency):
    model_config = _IMMUTABLE_IR_CONFIG

    missing_information: tuple[ShortText, ...] = Field(default_factory=tuple, max_length=32)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


class IRUnsupportedFeature(UnsupportedFeature):
    model_config = _IMMUTABLE_IR_CONFIG

    referenced_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)
    evidence_refs: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=16)


ANSWER_AUTHORITY_FORBIDDEN_FIELDS = frozenset(
    {
        "answer",
        "answers",
        "calculated_value",
        "candidate_selection",
        "equation_solution",
        "expected_answer",
        "expected_value",
        "final_answer",
        "final_solver_result",
        "final_value",
        "grade",
        "grading",
        "selected_equation_set",
        "selected_equations",
        "solver_result",
        "verification_passed",
        "verification_result",
        "verified",
    }
)


FORBIDDEN_SCAN_MAX_DEPTH = 64
FORBIDDEN_SCAN_MAX_NODES = 20_000
FORBIDDEN_SCAN_MAX_HITS = 64
FORBIDDEN_SCAN_MAX_KEY_LENGTH = 256


class ForbiddenFieldScanError(ValueError):
    """The answer-authority pre-scan could not safely inspect the payload."""


def find_forbidden_fields(payload: Any, path: str = "") -> tuple[str, ...]:
    """Boundedly scan raw input, rejecting cycles and resource exhaustion."""

    hits: list[str] = []
    active: set[int] = set()
    visited_nodes = 0
    stack: list[tuple[Any, str, int, bool]] = [(payload, path, 0, False)]
    while stack:
        value, value_path, depth, exiting = stack.pop()
        is_container = isinstance(value, (Mapping, list, tuple))
        identity = id(value)
        if exiting:
            active.discard(identity)
            continue
        visited_nodes += 1
        if visited_nodes > FORBIDDEN_SCAN_MAX_NODES:
            raise ForbiddenFieldScanError("forbidden-field scan node limit exceeded")
        if depth > FORBIDDEN_SCAN_MAX_DEPTH:
            raise ForbiddenFieldScanError("forbidden-field scan depth limit exceeded")
        if not is_container:
            continue
        if identity in active:
            raise ForbiddenFieldScanError("cyclic raw payload is not allowed")
        active.add(identity)
        stack.append((value, value_path, depth, True))
        children: list[tuple[Any, str, int, bool]] = []
        try:
            if isinstance(value, Mapping):
                for index, (key, child) in enumerate(value.items()):
                    if index + visited_nodes >= FORBIDDEN_SCAN_MAX_NODES:
                        raise ForbiddenFieldScanError("forbidden-field scan node limit exceeded")
                    if type(key) is not str:
                        raise ForbiddenFieldScanError("raw payload mapping keys must be strings")
                    if len(key) > FORBIDDEN_SCAN_MAX_KEY_LENGTH:
                        raise ForbiddenFieldScanError(
                            "raw payload mapping key length limit exceeded"
                        )
                    normalized = key.strip().lower().replace("-", "_")
                    key_text = key
                    bounded_key = key_text[:80]
                    item_path = f"{value_path}.{bounded_key}" if value_path else bounded_key
                    if normalized in ANSWER_AUTHORITY_FORBIDDEN_FIELDS:
                        hits.append(item_path)
                        if len(hits) > FORBIDDEN_SCAN_MAX_HITS:
                            raise ForbiddenFieldScanError("forbidden-field scan hit limit exceeded")
                    children.append((child, item_path, depth + 1, False))
            else:
                if len(value) + visited_nodes > FORBIDDEN_SCAN_MAX_NODES:
                    raise ForbiddenFieldScanError("forbidden-field scan node limit exceeded")
                for index, child in enumerate(value):
                    item_path = f"{value_path}.{index}" if value_path else str(index)
                    children.append((child, item_path, depth + 1, False))
        except ForbiddenFieldScanError:
            raise
        except Exception as exc:
            raise ForbiddenFieldScanError("raw payload traversal failed") from exc
        stack.extend(reversed(children))
    return tuple(hits)


class _ProblemBase(StrictModel):
    metadata: MechanicsMetadata
    source_assets: list[SourceAsset] = Field(max_length=32)
    source_evidence: list[SourceEvidence] = Field(max_length=512)
    entities: list[Entity] = Field(min_length=1, max_length=128)
    points: list[Point] = Field(max_length=256)
    reference_frames: list[ReferenceFrame] = Field(max_length=64)
    motion_intervals: list[MotionInterval] = Field(max_length=64)
    events: list[Event] = Field(max_length=128)
    symbols: list[SymbolDefinition] = Field(max_length=512)
    geometry: list[GeometryRelation] = Field(max_length=256)
    interactions: list[Interaction] = Field(max_length=256)
    constraints: list[Constraint] = Field(max_length=512)
    state_conditions: list[StateCondition] = Field(max_length=256)
    queries: list[Query] = Field(max_length=64)
    principle_hints: list[PrincipleHint] = Field(max_length=64)
    assumptions: list[Assumption] = Field(max_length=64)
    ambiguities: list[Ambiguity] = Field(max_length=64)
    figure_dependency: FigureDependency
    unsupported_features: list[UnsupportedFeature] = Field(max_length=64)


class MechanicsProblemDraftV1(_ProblemBase):
    schema: Literal[DRAFT_SCHEMA_NAME]
    version: Literal[DRAFT_SCHEMA_VERSION]
    quantities: list[DraftQuantity] = Field(max_length=512)

    @model_validator(mode="before")
    @classmethod
    def reject_answer_authority(cls, value: Any) -> Any:
        try:
            hits = find_forbidden_fields(value)
        except ForbiddenFieldScanError as exc:
            raise ValueError(f"answer-authority scan failed closed: {exc}") from None
        if hits:
            raise ValueError(
                "answer-authority fields are forbidden in mechanics drafts: "
                + ", ".join(hits[:8])
            )
        return value


class MechanicsProblemIRV1(_ProblemBase):
    model_config = _IMMUTABLE_IR_CONFIG

    schema: Literal[IR_SCHEMA_NAME]
    version: Literal[IR_SCHEMA_VERSION]
    validation_policy_version: DiagnosticLabel
    normalization_policy_version: DiagnosticLabel
    metadata: IRMechanicsMetadata
    source_assets: tuple[IRSourceAsset, ...] = Field(max_length=32)
    source_evidence: tuple[IRSourceEvidence, ...] = Field(max_length=512)
    entities: tuple[IREntity, ...] = Field(min_length=1, max_length=128)
    points: tuple[IRPoint, ...] = Field(max_length=256)
    reference_frames: tuple[IRReferenceFrame, ...] = Field(max_length=64)
    motion_intervals: tuple[IRMotionInterval, ...] = Field(max_length=64)
    events: tuple[IREvent, ...] = Field(max_length=128)
    symbols: tuple[SymbolDefinition, ...] = Field(max_length=512)
    quantities: tuple[IRQuantity, ...] = Field(max_length=512)
    geometry: tuple[IRGeometryRelation, ...] = Field(max_length=256)
    interactions: tuple[IRInteraction, ...] = Field(max_length=256)
    constraints: tuple[IRConstraint, ...] = Field(max_length=512)
    state_conditions: tuple[IRStateCondition, ...] = Field(max_length=256)
    queries: tuple[IRQuery, ...] = Field(max_length=64)
    principle_hints: tuple[IRPrincipleHint, ...] = Field(max_length=64)
    assumptions: tuple[IRAssumption, ...] = Field(max_length=64)
    ambiguities: tuple[IRAmbiguity, ...] = Field(max_length=64)
    figure_dependency: IRFigureDependency
    unsupported_features: tuple[IRUnsupportedFeature, ...] = Field(max_length=64)


__all__ = [
    "ANSWER_AUTHORITY_FORBIDDEN_FIELDS",
    "CONTRACT_VERSION",
    "DRAFT_SCHEMA_NAME",
    "DRAFT_SCHEMA_VERSION",
    "FORBIDDEN_SCAN_MAX_DEPTH",
    "FORBIDDEN_SCAN_MAX_HITS",
    "FORBIDDEN_SCAN_MAX_KEY_LENGTH",
    "FORBIDDEN_SCAN_MAX_NODES",
    "IR_SCHEMA_NAME",
    "IR_SCHEMA_VERSION",
    "Ambiguity",
    "AmbiguityKind",
    "Assumption",
    "AssumptionDisposition",
    "AxisBinding",
    "AxisDirection",
    "AxisName",
    "Constraint",
    "ConstraintKind",
    "DirectionBinding",
    "DraftQuantity",
    "Entity",
    "EntityPrimitive",
    "Event",
    "EventKind",
    "FigureDependency",
    "FigureDependencyLevel",
    "FigureEvidence",
    "FigureRegion",
    "ForbiddenFieldScanError",
    "GeometryRelation",
    "GeometryRelationKind",
    "IRAmbiguity",
    "IRAssumption",
    "IRAxisBinding",
    "IRAxisDirection",
    "IRConstraint",
    "IRDirectionBinding",
    "IREntity",
    "IREntityOrigin",
    "IREvent",
    "IRFigureDependency",
    "IRFigureEvidence",
    "IRFigureRegion",
    "IRFrameOrigin",
    "IRGeometryRelation",
    "IRInteraction",
    "IRMechanicsMetadata",
    "IRMotionInterval",
    "IRNormalizedBBox",
    "IRNormalizedPoint",
    "IROriginBinding",
    "IRPoint",
    "IRPointOrigin",
    "IRPrincipleHint",
    "IRQuantity",
    "IRQuery",
    "IRQueryTarget",
    "IRReferenceFrame",
    "IRSemanticDirection",
    "IRSourceAsset",
    "IRSourceEvidence",
    "IRSourceSpan",
    "IRStateCondition",
    "IRSymbolDirection",
    "IRTextEvidence",
    "IRUnsupportedFeature",
    "IRVectorDirection",
    "IRWorldOrigin",
    "Interaction",
    "InteractionKind",
    "MechanicsMetadata",
    "MechanicsProblemDraftV1",
    "MechanicsProblemIRV1",
    "MotionInterval",
    "NormalizedBBox",
    "NormalizedPoint",
    "Point",
    "PointRole",
    "Principle",
    "PrincipleHint",
    "ProblemLanguage",
    "Provenance",
    "QuantityComponent",
    "QuantityRole",
    "QuantityShape",
    "Query",
    "QueryTarget",
    "ReferenceFrame",
    "ReferenceFrameType",
    "SemanticDirection",
    "SemanticDirectionName",
    "SourceAsset",
    "SourceAssetKind",
    "SourceEvidence",
    "SourceSpan",
    "StateCondition",
    "StateKind",
    "StateValue",
    "SymbolDirection",
    "TextEvidence",
    "UnsupportedFeature",
    "VectorDirection",
    "find_forbidden_fields",
]
