from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


SCHEMA_NAME = "dynatutor.textbook_parse"
SCHEMA_VERSION = "1.1"

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
    aliases: list[ShortText] = Field(max_length=8)
    evidence_quote: EvidenceQuote


class MotionSegment(StrictModel):
    segment_id: Identifier
    order: int = Field(ge=1, le=8)
    actor_ids: list[Identifier] = Field(min_length=1, max_length=12)
    motion_model_candidates: list[MotionModel] = Field(min_length=1, max_length=3)
    start_event_id: Identifier | None
    end_event_id: Identifier | None
    relevance: SegmentRelevance
    evidence_quote: EvidenceQuote


class Event(StrictModel):
    event_id: Identifier
    kind: EventKind
    subject_ids: list[Identifier] = Field(min_length=1, max_length=12)
    segment_id: Identifier | None
    evidence_quote: EvidenceQuote


class ExplicitFact(StrictModel):
    fact_id: Identifier
    kind: FactKind
    semantic_key: Identifier
    symbol_hint: ShortText | None
    raw_value: RawValue
    raw_unit: RawUnit
    subject_id: Identifier
    segment_id: Identifier | None
    event_id: Identifier | None
    temporal_role: TemporalRole
    direction: Direction
    evidence_quote: EvidenceQuote
    occurrence_index: int = Field(ge=0, le=99)
    quantity_occurrence_index: int = Field(ge=0, le=99)
    relevance: FactRelevance


class Relation(StrictModel):
    relation_id: Identifier
    kind: RelationKind
    entity_ids: list[Identifier] = Field(min_length=2, max_length=6)
    segment_id: Identifier | None
    evidence_quote: EvidenceQuote


class Query(StrictModel):
    query_id: Identifier
    output_key: QueryOutputKey
    subject_id: Identifier
    segment_id: Identifier | None
    event_id: Identifier | None
    component: QueryComponent
    evidence_quote: EvidenceQuote


class AssumptionProposal(StrictModel):
    assumption_id: Identifier
    kind: AssumptionKind
    subject_id: Identifier
    segment_id: Identifier | None
    proposed_semantic_key: Identifier
    proposed_value: RawValue
    proposed_unit: RawUnit
    reason: ReasonText
    supporting_quote: OptionalEvidenceQuote
    model_confidence: float = Field(ge=0.0, le=1.0)


class InterpretationCandidate(StrictModel):
    candidate_id: Identifier
    system_type: Identifier
    subtype: Identifier | None
    target_segment_ids: list[Identifier] = Field(min_length=1, max_length=8)
    fact_ids: list[Identifier] = Field(max_length=32)
    query_ids: list[Identifier] = Field(min_length=1, max_length=8)
    assumption_ids: list[Identifier] = Field(max_length=16)
    model_confidence: float = Field(ge=0.0, le=1.0)
    reason_code: Identifier


class Ambiguity(StrictModel):
    ambiguity_id: Identifier
    kind: AmbiguityKind
    referenced_ids: list[Identifier] = Field(max_length=12)
    description: ReasonText
    evidence_quote: OptionalEvidenceQuote


class FigureDependency(StrictModel):
    level: FigureDependencyLevel
    missing_information: list[ShortText] = Field(max_length=12)
    evidence_quote: OptionalEvidenceQuote


class UnsupportedFeature(StrictModel):
    feature_code: Identifier
    description: ReasonText
    evidence_quote: OptionalEvidenceQuote


class TextbookProblemParseV1(StrictModel):
    schema: Literal[SCHEMA_NAME]
    version: Literal[SCHEMA_VERSION]
    language: Literal["ko", "en", "mixed"]
    parse_status: ParseStatus
    entities: list[Entity] = Field(min_length=1, max_length=12)
    motion_segments: list[MotionSegment] = Field(max_length=8)
    events: list[Event] = Field(max_length=16)
    explicit_facts: list[ExplicitFact] = Field(max_length=32)
    relations: list[Relation] = Field(max_length=24)
    queries: list[Query] = Field(max_length=8)
    assumption_proposals: list[AssumptionProposal] = Field(max_length=16)
    interpretation_candidates: list[InterpretationCandidate] = Field(max_length=3)
    ambiguities: list[Ambiguity] = Field(max_length=16)
    figure_dependency: FigureDependency
    unsupported_features: list[UnsupportedFeature] = Field(max_length=16)

    @model_validator(mode="after")
    def validate_graph_references(self) -> Self:
        entity_ids = self._unique("entity", [item.entity_id for item in self.entities])
        segment_ids = self._unique("segment", [item.segment_id for item in self.motion_segments])
        event_ids = self._unique("event", [item.event_id for item in self.events])
        fact_ids = self._unique("fact", [item.fact_id for item in self.explicit_facts])
        relation_ids = self._unique("relation", [item.relation_id for item in self.relations])
        query_ids = self._unique("query", [item.query_id for item in self.queries])
        assumption_ids = self._unique(
            "assumption", [item.assumption_id for item in self.assumption_proposals]
        )
        self._unique(
            "interpretation candidate",
            [item.candidate_id for item in self.interpretation_candidates],
        )
        self._unique("ambiguity", [item.ambiguity_id for item in self.ambiguities])
        self._unique("segment order", [str(item.order) for item in self.motion_segments])

        segment_by_id = {item.segment_id: item for item in self.motion_segments}
        event_by_id = {item.event_id: item for item in self.events}
        fact_by_id = {item.fact_id: item for item in self.explicit_facts}
        query_by_id = {item.query_id: item for item in self.queries}
        assumption_by_id = {
            item.assumption_id: item for item in self.assumption_proposals
        }

        for segment in self.motion_segments:
            self._require_refs("segment actor", segment.actor_ids, entity_ids)
            self._require_optional_ref("segment start event", segment.start_event_id, event_ids)
            self._require_optional_ref("segment end event", segment.end_event_id, event_ids)
            if segment.start_event_id is not None and segment.start_event_id == segment.end_event_id:
                raise ValueError("segment start_event_id and end_event_id must differ")
        for event in self.events:
            self._require_refs("event subject", event.subject_ids, entity_ids)
            self._require_optional_ref("event segment", event.segment_id, segment_ids)
            if event.segment_id is not None:
                actors = set(segment_by_id[event.segment_id].actor_ids)
                if not set(event.subject_ids).issubset(actors):
                    raise ValueError(
                        f"event subject(s) must be actors of segment: {event.event_id}"
                    )
        for fact in self.explicit_facts:
            self._require_ref("fact subject", fact.subject_id, entity_ids)
            self._require_optional_ref("fact segment", fact.segment_id, segment_ids)
            self._require_optional_ref("fact event", fact.event_id, event_ids)
            self._validate_subject_segment_event_binding(
                "fact", fact.fact_id, fact.subject_id, fact.segment_id, fact.event_id,
                segment_by_id, event_by_id,
            )
            if fact.temporal_role in {
                TemporalRole.before_event,
                TemporalRole.at_event,
                TemporalRole.after_event,
            } and fact.event_id is None:
                raise ValueError(
                    f"fact temporal role requires event_id: {fact.fact_id}"
                )
            if fact.segment_id is not None and fact.event_id is not None:
                segment = segment_by_id[fact.segment_id]
                if fact.temporal_role == TemporalRole.initial and segment.start_event_id != fact.event_id:
                    raise ValueError(
                        f"initial fact must bind the segment start event: {fact.fact_id}"
                    )
                if fact.temporal_role == TemporalRole.final and segment.end_event_id != fact.event_id:
                    raise ValueError(
                        f"final fact must bind the segment end event: {fact.fact_id}"
                    )
        for relation in self.relations:
            self._require_refs("relation entity", relation.entity_ids, entity_ids)
            self._require_optional_ref("relation segment", relation.segment_id, segment_ids)
        for query in self.queries:
            self._require_ref("query subject", query.subject_id, entity_ids)
            self._require_optional_ref("query segment", query.segment_id, segment_ids)
            self._require_optional_ref("query event", query.event_id, event_ids)
            self._validate_subject_segment_event_binding(
                "query", query.query_id, query.subject_id, query.segment_id, query.event_id,
                segment_by_id, event_by_id,
            )
        for assumption in self.assumption_proposals:
            self._require_ref("assumption subject", assumption.subject_id, entity_ids)
            self._require_optional_ref("assumption segment", assumption.segment_id, segment_ids)
            if (
                assumption.segment_id is not None
                and assumption.subject_id not in segment_by_id[assumption.segment_id].actor_ids
            ):
                raise ValueError(
                    f"assumption subject must be an actor of segment: {assumption.assumption_id}"
                )
        for candidate in self.interpretation_candidates:
            self._require_refs("candidate target segment", candidate.target_segment_ids, segment_ids)
            self._require_refs("candidate fact", candidate.fact_ids, fact_ids)
            self._require_refs("candidate query", candidate.query_ids, query_ids)
            self._require_refs("candidate assumption", candidate.assumption_ids, assumption_ids)
            targets = set(candidate.target_segment_ids)
            candidate_queries = [query_by_id[item] for item in candidate.query_ids]
            if any(
                query.segment_id is None or query.segment_id not in targets
                for query in candidate_queries
            ):
                raise ValueError(
                    f"candidate query must bind a target segment: {candidate.candidate_id}"
                )
            if targets - {query.segment_id for query in candidate_queries}:
                raise ValueError(
                    f"every candidate target segment must be query-bound: {candidate.candidate_id}"
                )
            for fact_id in candidate.fact_ids:
                fact = fact_by_id[fact_id]
                if (
                    fact.relevance in {FactRelevance.solver_input, FactRelevance.constraint}
                    and (fact.segment_id is None or fact.segment_id not in targets)
                ):
                    raise ValueError(
                        f"candidate solver fact must bind a target segment: {fact_id}"
                    )
            for assumption_id in candidate.assumption_ids:
                assumption = assumption_by_id[assumption_id]
                if assumption.segment_id is not None and assumption.segment_id not in targets:
                    raise ValueError(
                        f"candidate assumption must bind a target segment: {assumption_id}"
                    )
        for ambiguity in self.ambiguities:
            allowed_ids = (
                entity_ids
                | segment_ids
                | event_ids
                | fact_ids
                | relation_ids
                | query_ids
                | assumption_ids
            )
            self._require_refs("ambiguity", ambiguity.referenced_ids, allowed_ids)

        target_segments = {
            segment.segment_id
            for segment in self.motion_segments
            if segment.relevance == SegmentRelevance.target
        }
        query_segments = {query.segment_id for query in self.queries if query.segment_id is not None}
        if target_segments - query_segments:
            raise ValueError("every target segment must be referenced by a query")

        # A shared boundary event may end an earlier segment and start a later one,
        # but it must never point backwards in the declared segment order.
        for event_id in event_ids:
            starts = [
                item.order for item in self.motion_segments if item.start_event_id == event_id
            ]
            ends = [
                item.order for item in self.motion_segments if item.end_event_id == event_id
            ]
            if starts and ends and max(ends) >= min(starts):
                raise ValueError(
                    f"event boundary reverses segment order: {event_id}"
                )
        for segment in self.motion_segments:
            for role, event_id in (
                ("start", segment.start_event_id),
                ("end", segment.end_event_id),
            ):
                if event_id is None:
                    continue
                event = event_by_id[event_id]
                if not set(event.subject_ids).issubset(set(segment.actor_ids)):
                    raise ValueError(
                        f"segment {role} event subject must be a segment actor: {segment.segment_id}"
                    )
                if event.segment_id is not None:
                    linked = {segment.segment_id}
                    linked.update(
                        item.segment_id
                        for item in self.motion_segments
                        if item.start_event_id == event_id or item.end_event_id == event_id
                    )
                    if event.segment_id not in linked:
                        raise ValueError(
                            f"segment {role} event binding disagrees: {segment.segment_id}"
                        )
        return self

    @staticmethod
    def _validate_subject_segment_event_binding(
        kind: str,
        item_id: str,
        subject_id: str,
        segment_id: str | None,
        event_id: str | None,
        segment_by_id: dict[str, MotionSegment],
        event_by_id: dict[str, Event],
    ) -> None:
        if segment_id is not None and subject_id not in segment_by_id[segment_id].actor_ids:
            raise ValueError(f"{kind} subject must be an actor of segment: {item_id}")
        if event_id is not None:
            event = event_by_id[event_id]
            if subject_id not in event.subject_ids:
                raise ValueError(f"{kind} subject must be a subject of event: {item_id}")
            if (
                segment_id is not None
                and event.segment_id is not None
                and event.segment_id != segment_id
            ):
                raise ValueError(f"{kind} segment and event bindings disagree: {item_id}")

    @staticmethod
    def _unique(kind: str, values: list[str]) -> set[str]:
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {kind} ID")
        return set(values)

    @staticmethod
    def _require_ref(kind: str, value: str, allowed: set[str]) -> None:
        if value not in allowed:
            raise ValueError(f"unknown {kind} reference: {value}")

    @classmethod
    def _require_optional_ref(cls, kind: str, value: str | None, allowed: set[str]) -> None:
        if value is not None:
            cls._require_ref(kind, value, allowed)

    @staticmethod
    def _require_refs(kind: str, values: list[str], allowed: set[str]) -> None:
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"unknown {kind} reference(s): {', '.join(unknown)}")


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
    "AssumptionKind",
    "AssumptionProposal",
    "Direction",
    "Entity",
    "Event",
    "ExplicitFact",
    "FigureDependency",
    "FigureDependencyLevel",
    "InterpretationCandidate",
    "MotionSegment",
    "ParseStatus",
    "Query",
    "QueryOutputKey",
    "Relation",
    "SegmentRelevance",
    "TextbookProblemParseV1",
]
