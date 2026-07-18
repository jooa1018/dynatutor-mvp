from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from engine.textbook_parser.ontology import ExplicitSemanticKey, ParserSystemType


SCHEMA_NAME = "dynatutor.textbook_parse"
SCHEMA_VERSION = "2.0"

Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
    ),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
EvidenceQuote = Annotated[str, StringConstraints(min_length=1, max_length=500)]
OptionalEvidenceQuote = Annotated[str, StringConstraints(max_length=500)] | None
ReasonText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
RawValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
RawUnit = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ParseStatus(str, Enum):
    complete = "complete"
    ambiguous = "ambiguous"
    insufficient_information = "insufficient_information"
    needs_figure = "needs_figure"
    unsupported = "unsupported"


class EntityKind(str, Enum):
    particle = "particle"
    rigid_body = "rigid_body"
    point = "point"
    system = "system"
    block = "block"
    disk = "disk"
    sphere = "sphere"
    cylinder = "cylinder"
    rod = "rod"
    pulley = "pulley"
    rope = "rope"
    spring = "spring"
    surface = "surface"
    incline = "incline"
    slot = "slot"
    pin = "pin"
    vehicle = "vehicle"
    person = "person"
    reference_frame = "reference_frame"
    other = "other"


class MotionModel(str, Enum):
    constant_velocity_1d = "constant_velocity_1d"
    constant_acceleration_1d = "constant_acceleration_1d"
    projectile_free_flight = "projectile_free_flight"
    sliding_on_incline = "sliding_on_incline"
    rolling_without_slipping = "rolling_without_slipping"
    rolling_with_slip = "rolling_with_slip"
    collision_contact = "collision_contact"
    post_collision_motion = "post_collision_motion"
    fixed_axis_rotation = "fixed_axis_rotation"
    general_plane_motion = "general_plane_motion"
    relative_motion = "relative_motion"
    spring_oscillation = "spring_oscillation"
    energy_interval = "energy_interval"
    impulse_interval = "impulse_interval"
    unknown = "unknown"


class SegmentRelevance(str, Enum):
    target = "target"
    required_context = "required_context"
    context_only = "context_only"
    unused = "unused"


class EventKind(str, Enum):
    start = "start"
    release = "release"
    just_before_collision = "just_before_collision"
    collision_start = "collision_start"
    collision_end = "collision_end"
    just_after_collision = "just_after_collision"
    reaches_position = "reaches_position"
    reaches_height = "reaches_height"
    highest_point = "highest_point"
    lowest_point = "lowest_point"
    comes_to_rest = "comes_to_rest"
    turnaround = "turnaround"
    contact_lost = "contact_lost"
    rope_taut = "rope_taut"
    rope_slack = "rope_slack"
    spring_max_compression = "spring_max_compression"
    finish = "finish"
    other = "other"


class FactKind(str, Enum):
    scalar = "scalar"
    vector_component = "vector_component"
    dimensionless = "dimensionless"
    count = "count"


class TemporalRole(str, Enum):
    initial = "initial"
    during = "during"
    final = "final"
    before_event = "before_event"
    at_event = "at_event"
    after_event = "after_event"
    interval = "interval"
    timeless = "timeless"


class Direction(str, Enum):
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
    tangential = "tangential"
    unspecified = "unspecified"
    not_applicable = "not_applicable"


class FactRelevance(str, Enum):
    solver_input = "solver_input"
    constraint = "constraint"
    context_only = "context_only"
    unused = "unused"


class RelationKind(str, Enum):
    connected_by_rope = "connected_by_rope"
    passes_over_pulley = "passes_over_pulley"
    attached_to_spring = "attached_to_spring"
    contact_with = "contact_with"
    slides_on = "slides_on"
    rolls_on = "rolls_on"
    fixed_to = "fixed_to"
    hinged_at = "hinged_at"
    point_on_body = "point_on_body"
    moves_in_slot = "moves_in_slot"
    moves_relative_to = "moves_relative_to"
    rotates_about = "rotates_about"
    collides_with = "collides_with"
    shares_velocity_constraint = "shares_velocity_constraint"
    shares_acceleration_constraint = "shares_acceleration_constraint"


class QueryOutputKey(str, Enum):
    acceleration = "acceleration"
    angular_acceleration = "angular_acceleration"
    angular_frequency = "angular_frequency"
    angular_velocity = "angular_velocity"
    centripetal_acceleration = "centripetal_acceleration"
    distance = "distance"
    elastic_energy = "elastic_energy"
    final_velocity = "final_velocity"
    force = "force"
    frequency = "frequency"
    friction_force = "friction_force"
    initial_velocity = "initial_velocity"
    impulse = "impulse"
    kinetic_energy = "kinetic_energy"
    mass = "mass"
    max_height = "max_height"
    minimum_speed = "minimum_speed"
    normal_force = "normal_force"
    period = "period"
    post_collision_velocity = "post_collision_velocity"
    potential_energy = "potential_energy"
    range = "range"
    tangential_velocity = "tangential_velocity"
    tension = "tension"
    time = "time"
    v1_after = "v1_after"
    v2_after = "v2_after"
    work = "work"


class QueryComponent(str, Enum):
    magnitude = "magnitude"
    x = "x"
    y = "y"
    radial = "radial"
    transverse = "transverse"
    tangential = "tangential"
    normal = "normal"
    clockwise = "clockwise"
    counterclockwise = "counterclockwise"
    unspecified = "unspecified"


class AssumptionKind(str, Enum):
    starts_from_rest = "starts_from_rest"
    ends_at_rest = "ends_at_rest"
    constant_gravity = "constant_gravity"
    no_air_resistance = "no_air_resistance"
    frictionless = "frictionless"
    massless_rope = "massless_rope"
    inextensible_rope = "inextensible_rope"
    massless_pulley = "massless_pulley"
    pure_rolling = "pure_rolling"
    fixed_point = "fixed_point"
    direction_choice = "direction_choice"
    other = "other"


class FigureDependencyLevel(str, Enum):
    none = "none"
    helpful = "helpful"
    required = "required"


class AmbiguityKind(str, Enum):
    entity_binding = "entity_binding"
    segment_binding = "segment_binding"
    event_binding = "event_binding"
    relation = "relation"
    direction = "direction"
    occurrence = "occurrence"
    query = "query"
    assumption = "assumption"
    interpretation = "interpretation"
    other = "other"


class Entity(StrictModel):
    entity_id: Identifier
    kind: EntityKind
    label: ShortText
    aliases: list[ShortText] = Field(default_factory=list, max_length=8)
    evidence_quote: OptionalEvidenceQuote = None


class MotionSegment(StrictModel):
    segment_id: Identifier
    order: int = Field(ge=1, le=8)
    actor_ids: list[Identifier] = Field(min_length=1, max_length=12)
    motion_model_candidates: list[MotionModel] = Field(min_length=1, max_length=3)
    start_event_id: Identifier | None = None
    end_event_id: Identifier | None = None
    relevance: SegmentRelevance
    evidence_quote: OptionalEvidenceQuote = None


class Event(StrictModel):
    event_id: Identifier
    kind: EventKind
    subject_ids: list[Identifier] = Field(min_length=1, max_length=12)
    segment_id: Identifier | None = None
    evidence_quote: OptionalEvidenceQuote = None


class ExplicitFactBase(StrictModel):
    fact_id: Identifier
    kind: FactKind
    semantic_key: ExplicitSemanticKey
    symbol_hint: ShortText | None = None
    raw_value: RawValue
    raw_unit: RawUnit
    subject_id: Identifier
    segment_id: Identifier | None = None
    event_id: Identifier | None = None
    temporal_role: TemporalRole
    direction: Direction
    evidence_quote: EvidenceQuote
    relevance: FactRelevance


class ExplicitFact(ExplicitFactBase):
    occurrence_index: int = Field(ge=0, le=99)
    quantity_occurrence_index: int = Field(ge=0, le=99)


class ExplicitFactWire(ExplicitFactBase):
    occurrence_index: int | None = Field(default=None, ge=0, le=99)
    quantity_occurrence_index: int | None = Field(default=None, ge=0, le=99)


class Relation(StrictModel):
    relation_id: Identifier
    kind: RelationKind
    entity_ids: list[Identifier] = Field(min_length=2, max_length=6)
    segment_id: Identifier | None = None
    evidence_quote: OptionalEvidenceQuote = None


class Query(StrictModel):
    query_id: Identifier
    output_key: QueryOutputKey
    subject_id: Identifier
    segment_id: Identifier | None = None
    event_id: Identifier | None = None
    component: QueryComponent
    evidence_quote: OptionalEvidenceQuote = None


class AssumptionProposal(StrictModel):
    assumption_id: Identifier
    kind: AssumptionKind
    subject_id: Identifier
    segment_id: Identifier | None = None
    proposed_semantic_key: ExplicitSemanticKey
    proposed_value: RawValue
    proposed_unit: RawUnit
    reason: ReasonText
    supporting_quote: OptionalEvidenceQuote = None
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class InterpretationCandidate(StrictModel):
    candidate_id: Identifier
    system_type: ParserSystemType
    subtype: Identifier | None = None
    target_segment_ids: list[Identifier] = Field(min_length=1, max_length=8)
    fact_ids: list[Identifier] = Field(default_factory=list, max_length=32)
    query_ids: list[Identifier] = Field(min_length=1, max_length=8)
    assumption_ids: list[Identifier] = Field(default_factory=list, max_length=16)
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_code: Identifier


class Ambiguity(StrictModel):
    ambiguity_id: Identifier
    kind: AmbiguityKind
    referenced_ids: list[Identifier] = Field(default_factory=list, max_length=12)
    description: ReasonText
    evidence_quote: OptionalEvidenceQuote = None


class FigureDependency(StrictModel):
    level: FigureDependencyLevel
    missing_information: list[ShortText] = Field(default_factory=list, max_length=12)
    evidence_quote: OptionalEvidenceQuote = None


class UnsupportedFeature(StrictModel):
    feature_code: Identifier
    description: ReasonText
    evidence_quote: OptionalEvidenceQuote = None


class _TextbookProblemParseBase(StrictModel):
    schema: Literal[SCHEMA_NAME]
    version: Literal[SCHEMA_VERSION]
    language: Literal["ko", "en", "mixed"]
    parse_status: ParseStatus
    entities: list[Entity] = Field(min_length=1, max_length=12)
    motion_segments: list[MotionSegment] = Field(default_factory=list, max_length=8)
    events: list[Event] = Field(default_factory=list, max_length=16)
    relations: list[Relation] = Field(default_factory=list, max_length=24)
    queries: list[Query] = Field(default_factory=list, max_length=8)
    assumption_proposals: list[AssumptionProposal] = Field(default_factory=list, max_length=16)
    interpretation_candidates: list[InterpretationCandidate] = Field(default_factory=list, max_length=3)
    ambiguities: list[Ambiguity] = Field(default_factory=list, max_length=16)
    figure_dependency: FigureDependency
    unsupported_features: list[UnsupportedFeature] = Field(default_factory=list, max_length=16)


class TextbookProblemParseV2(_TextbookProblemParseBase):
    explicit_facts: list[ExplicitFact] = Field(default_factory=list, max_length=32)


class TextbookProblemParseWireV2(_TextbookProblemParseBase):
    explicit_facts: list[ExplicitFactWire] = Field(default_factory=list, max_length=32)


class TextbookProblemParseV1(TextbookProblemParseV2):
    """Strict compatibility view used by pre-V2 internal callers.

    The model-facing wire contract deliberately leaves graph closure to the
    field-addressable server validator.  Existing internal callers historically
    relied on ``model_validate`` rejecting a broken graph, so this compatibility
    class preserves that fail-closed behavior without putting the monolithic
    graph validator back into Structured Outputs.
    """

    @model_validator(mode="after")
    def validate_legacy_graph_closure(self) -> Self:
        # Late import avoids a contracts <-> graph_validation import cycle.
        from engine.textbook_parser.graph_validation import validate_graph_contract

        issues = validate_graph_contract(self)
        if issues:
            raise ValueError(issues[0].message)
        return self


ANSWER_AUTHORITY_FORBIDDEN_FIELDS = frozenset(
    {
        "answer",
        "answers",
        "calculated_value",
        "candidate_selection",
        "equation_solution",
        "final_answer",
        "final_solver_result",
        "grade",
        "grading",
        "solver_result",
        "verification_passed",
    }
)


__all__ = [
    "ANSWER_AUTHORITY_FORBIDDEN_FIELDS",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "Ambiguity",
    "AmbiguityKind",
    "AssumptionKind",
    "AssumptionProposal",
    "Direction",
    "Entity",
    "EntityKind",
    "Event",
    "EventKind",
    "ExplicitFact",
    "ExplicitFactWire",
    "FactKind",
    "FactRelevance",
    "FigureDependency",
    "FigureDependencyLevel",
    "InterpretationCandidate",
    "MotionModel",
    "MotionSegment",
    "ParseStatus",
    "Query",
    "QueryComponent",
    "QueryOutputKey",
    "Relation",
    "RelationKind",
    "SegmentRelevance",
    "TemporalRole",
    "TextbookProblemParseV1",
    "TextbookProblemParseV2",
    "TextbookProblemParseWireV2",
    "UnsupportedFeature",
]
