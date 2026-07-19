"""Fail-closed boundary from the accepted textbook parse to mechanics draft v1.

This module deliberately contains tables, not interpretation.  Phase55 has
already selected a graph; this adapter only preserves that graph and its exact
numeric evidence for Phase56 to validate again.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType

from engine.mechanics.contracts import (
    Assumption,
    AssumptionDisposition as DraftAssumptionDisposition,
    DraftQuantity,
    Entity,
    EntityPrimitive,
    Event,
    EventKind,
    FigureDependency,
    FigureDependencyLevel,
    GeometryRelation,
    GeometryRelationKind,
    Interaction,
    InteractionKind,
    MechanicsMetadata,
    MechanicsProblemDraftV1,
    MotionInterval,
    ProblemLanguage,
    Provenance,
    QuantityComponent,
    QuantityRole,
    QuantityShape,
    Query,
    QueryTarget,
    SemanticDirection,
    SemanticDirectionName,
    SourceSpan,
    TextEvidence,
    UnsupportedFeature,
)
from engine.mechanics.errors import (
    MechanicsIssueCode,
    MechanicsIssueSeverity,
    MechanicsValidationIssue,
)
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.validation import (
    AssumptionAuthorization,
    DraftValidationResult,
    ValidationTerminal,
    validate_draft,
)
from engine.textbook_parser.assumption_policy import AssumptionDisposition
from engine.textbook_parser.contracts import TextbookProblemParseV1
from engine.textbook_parser.evidence_alignment import (
    _normalized_number,
    _normalized_unit,
    quantity_occurrences,
    quote_occurrences,
)
from engine.textbook_parser.validation import ValidatedParse, validate_parse


PHASE55_ADAPTER_VERSION = "phase55-mechanics-adapter-v1"
_MAX_TEXT = 200_000


@dataclass(frozen=True)
class Phase55AdapterResult:
    terminal: ValidationTerminal
    validation: DraftValidationResult
    issues: tuple[MechanicsValidationIssue, ...]
    draft: MechanicsProblemDraftV1 | None
    approved_assumption_ids: tuple[str, ...]
    authorized_assumptions: MappingProxyType

    @property
    def accepted(self) -> bool:
        return self.draft is not None and self.validation.accepted


def _dimension(mass=0, length=0, time=0) -> DimensionVector:
    return DimensionVector(mass=mass, length=length, time=time)


# Every Phase55 semantic key has an explicit mechanical meaning.  No source
# system category, label, or model candidate participates in these tables.
_FACTS = {
    "acceleration": (QuantityRole.acceleration, _dimension(length=1, time=-2)),
    "angle": (QuantityRole.angle, _dimension()),
    "angular_acceleration": (QuantityRole.angular_acceleration, _dimension(time=-2)),
    "angular_velocity": (QuantityRole.angular_velocity, _dimension(time=-1)),
    "background_height": (QuantityRole.height, _dimension(length=1)),
    "coefficient_of_friction": (QuantityRole.coefficient_friction, _dimension()),
    "displacement": (QuantityRole.displacement, _dimension(length=1)),
    "distance": (QuantityRole.distance, _dimension(length=1)),
    "duration": (QuantityRole.duration, _dimension(time=1)),
    "energy": (QuantityRole.energy, _dimension(mass=1, length=2, time=-2)),
    "final_velocity": (QuantityRole.velocity, _dimension(length=1, time=-1)),
    "force": (QuantityRole.force, _dimension(mass=1, length=1, time=-2)),
    "frequency": (QuantityRole.frequency, _dimension(time=-1)),
    "height": (QuantityRole.height, _dimension(length=1)),
    "impulse": (QuantityRole.impulse, _dimension(mass=1, length=1, time=-1)),
    "initial_velocity": (QuantityRole.velocity, _dimension(length=1, time=-1)),
    "mass": (QuantityRole.mass, _dimension(mass=1)),
    "mass_1": (QuantityRole.mass, _dimension(mass=1)),
    "mass_2": (QuantityRole.mass, _dimension(mass=1)),
    "moment_of_inertia": (QuantityRole.moment_of_inertia, _dimension(mass=1, length=2)),
    "period": (QuantityRole.period, _dimension(time=1)),
    "radius": (QuantityRole.radius, _dimension(length=1)),
    "restitution_coefficient": (QuantityRole.coefficient_restitution, _dimension()),
    "spring_constant": (QuantityRole.stiffness, _dimension(mass=1, time=-2)),
    "time": (QuantityRole.time, _dimension(time=1)),
    "torque": (QuantityRole.torque, _dimension(mass=1, length=2, time=-2)),
    "velocity": (QuantityRole.velocity, _dimension(length=1, time=-1)),
    "velocity_after": (QuantityRole.velocity, _dimension(length=1, time=-1)),
    "velocity_before": (QuantityRole.velocity, _dimension(length=1, time=-1)),
    "work": (QuantityRole.work, _dimension(mass=1, length=2, time=-2)),
}

_QUERIES = {
    "acceleration": (QuantityRole.acceleration, _dimension(length=1, time=-2), "m/s^2"),
    "angular_acceleration": (QuantityRole.angular_acceleration, _dimension(time=-2), "rad/s^2"),
    "angular_frequency": (QuantityRole.frequency, _dimension(time=-1), "Hz"),
    "angular_velocity": (QuantityRole.angular_velocity, _dimension(time=-1), "rad/s"),
    "centripetal_acceleration": (QuantityRole.acceleration, _dimension(length=1, time=-2), "m/s^2"),
    "distance": (QuantityRole.distance, _dimension(length=1), "m"),
    "elastic_energy": (QuantityRole.energy, _dimension(mass=1, length=2, time=-2), "J"),
    "final_velocity": (QuantityRole.velocity, _dimension(length=1, time=-1), "m/s"),
    "force": (QuantityRole.force, _dimension(mass=1, length=1, time=-2), "N"),
    "frequency": (QuantityRole.frequency, _dimension(time=-1), "Hz"),
    "friction_force": (QuantityRole.force, _dimension(mass=1, length=1, time=-2), "N"),
    "initial_velocity": (QuantityRole.velocity, _dimension(length=1, time=-1), "m/s"),
    "impulse": (QuantityRole.impulse, _dimension(mass=1, length=1, time=-1), "N*s"),
    "kinetic_energy": (QuantityRole.energy, _dimension(mass=1, length=2, time=-2), "J"),
    "mass": (QuantityRole.mass, _dimension(mass=1), "kg"),
    "max_height": (QuantityRole.height, _dimension(length=1), "m"),
    "minimum_speed": (QuantityRole.speed, _dimension(length=1, time=-1), "m/s"),
    "normal_force": (QuantityRole.force, _dimension(mass=1, length=1, time=-2), "N"),
    "period": (QuantityRole.period, _dimension(time=1), "s"),
    "post_collision_velocity": (QuantityRole.velocity, _dimension(length=1, time=-1), "m/s"),
    "potential_energy": (QuantityRole.energy, _dimension(mass=1, length=2, time=-2), "J"),
    "range": (QuantityRole.distance, _dimension(length=1), "m"),
    "tangential_velocity": (QuantityRole.velocity, _dimension(length=1, time=-1), "m/s"),
    "tension": (QuantityRole.force, _dimension(mass=1, length=1, time=-2), "N"),
    "time": (QuantityRole.time, _dimension(time=1), "s"),
    "v1_after": (QuantityRole.velocity, _dimension(length=1, time=-1), "m/s"),
    "v2_after": (QuantityRole.velocity, _dimension(length=1, time=-1), "m/s"),
    "work": (QuantityRole.work, _dimension(mass=1, length=2, time=-2), "J"),
}

_ENTITY_PRIMITIVES = {
    "particle": EntityPrimitive.particle, "rigid_body": EntityPrimitive.rigid_body,
    "block": EntityPrimitive.rigid_body, "disk": EntityPrimitive.rigid_body,
    "sphere": EntityPrimitive.rigid_body, "cylinder": EntityPrimitive.rigid_body,
    "rod": EntityPrimitive.rigid_body, "vehicle": EntityPrimitive.rigid_body,
    "person": EntityPrimitive.rigid_body, "point": EntityPrimitive.point,
    "system": EntityPrimitive.system, "pulley": EntityPrimitive.pulley,
    "rope": EntityPrimitive.rope, "spring": EntityPrimitive.spring,
    "surface": EntityPrimitive.surface, "incline": EntityPrimitive.incline,
    "slot": EntityPrimitive.slot, "reference_frame": EntityPrimitive.reference_frame,
    "pin": EntityPrimitive.joint, "other": EntityPrimitive.body_component,
}
_EVENTS = {
    "start": EventKind.start,
    "release": EventKind.release,
    "just_before_collision": EventKind.collision_start,
    "collision_start": EventKind.collision_start,
    "collision_end": EventKind.collision_end,
    "just_after_collision": EventKind.collision_end,
    "reaches_position": EventKind.reaches_condition,
    "reaches_height": EventKind.reaches_condition,
    "highest_point": EventKind.reaches_condition,
    "lowest_point": EventKind.reaches_condition,
    "comes_to_rest": EventKind.comes_to_rest,
    "turnaround": EventKind.turnaround,
    "contact_lost": EventKind.contact_end,
    "rope_taut": EventKind.rope_taut,
    "rope_slack": EventKind.rope_slack,
    "spring_max_compression": EventKind.reaches_condition,
    "finish": EventKind.finish,
    "other": EventKind.other,
}
_GEOMETRY = {
    "connected_by_rope": GeometryRelationKind.topology_connects,
    "passes_over_pulley": GeometryRelationKind.wraps,
    "slides_on": GeometryRelationKind.lies_on, "rolls_on": GeometryRelationKind.lies_on,
    "fixed_to": GeometryRelationKind.topology_connects,
    "hinged_at": GeometryRelationKind.topology_connects,
    "point_on_body": GeometryRelationKind.lies_on, "moves_in_slot": GeometryRelationKind.lies_on,
    "moves_relative_to": GeometryRelationKind.topology_connects,
    "rotates_about": GeometryRelationKind.topology_connects,
}
_INTERACTIONS = {
    "attached_to_spring": InteractionKind.spring, "contact_with": InteractionKind.contact,
    "collides_with": InteractionKind.collision,
}
_COMPONENTS = {name: QuantityComponent[name] for name in (
    "magnitude", "x", "y", "radial", "transverse", "tangential", "normal",
    "clockwise", "counterclockwise", "unspecified")}
_DIRECTIONS = {name: SemanticDirectionName[name] for name in SemanticDirectionName.__members__}
_SERVER_RESOLUTIONS = {
    "starts_from_rest": ("initial_velocity", "0", "m/s"),
    "ends_at_rest": ("final_velocity", "0", "m/s"),
    "constant_gravity": ("acceleration", "9.81", "m/s^2"),
}


def _id(prefix: str, source_id: str) -> str:
    return prefix + sha256(source_id.encode("utf-8")).hexdigest()[:48]


def _issue(code: MechanicsIssueCode, message: str, path: str = "") -> MechanicsValidationIssue:
    return MechanicsValidationIssue(code, MechanicsIssueSeverity.error, message, path)


def _failure(issue: MechanicsValidationIssue) -> Phase55AdapterResult:
    validation = DraftValidationResult(ValidationTerminal.invalid, (issue,))
    return Phase55AdapterResult(validation.terminal, validation, validation.issues, None, (), MappingProxyType({}))


def _canonical(value: object, budget: list[int], depth: int = 0) -> object:
    """Create a bounded, ordering-independent authority comparison value."""
    budget[0] -= 1
    if budget[0] < 0 or depth > 48:
        raise ValueError("authority projection exceeds its bound")
    if value is None or type(value) in {str, int, float, bool}:
        return value
    enum_value = getattr(value, "value", None)
    if type(enum_value) in {str, int, float, bool}:
        return enum_value
    if isinstance(value, dict):
        if len(value) > 1_024 or any(type(key) is not str for key in value):
            raise ValueError("authority mapping is not bounded")
        return tuple(
            (key, _canonical(value[key], budget, depth + 1))
            for key in sorted(value)
        )
    if isinstance(value, (list, tuple)):
        if len(value) > 1_024:
            raise ValueError("authority sequence is not bounded")
        return tuple(_canonical(item, budget, depth + 1) for item in value)
    raise ValueError("authority projection contains an unsupported value")


def _authority_projection(validated: ValidatedParse) -> object:
    """Snapshot every calculation-relevant Phase55 validation output."""
    if (
        len(validated.evidence.fact_spans) > 32
        or len(validated.evidence.issues) > 512
        or len(validated.assumptions) > 16
        or len(validated.candidates) > 3
        or len(validated.issues) > 512
    ):
        raise ValueError("Phase55 authority collections exceed their bounds")
    candidates = []
    for evaluation in validated.candidates:
        effective = evaluation.effective_candidate.model_dump(mode="json")
        # These two fields are diagnostics only.  Fresh Phase55 output remains
        # authoritative for every selected reference and graph calculation.
        effective.pop("system_type", None)
        effective.pop("subtype", None)
        candidates.append(
            {
                "candidate_id": evaluation.candidate_id,
                "effective_candidate": effective,
                "auto_attached_assumption_ids": list(
                    evaluation.auto_attached_assumption_ids
                ),
                "capability": evaluation.capability.to_dict(),
                "score": evaluation.score.to_dict(),
            }
        )
    payload = {
        "parse": validated.parse.model_dump(mode="json"),
        "status": validated.status.value,
        "selected_candidate_id": validated.selected_candidate_id,
        "evidence": {
            "fact_spans": {
                key: {
                    "start": span.start,
                    "end": span.end,
                    "quote": span.quote,
                }
                for key, span in validated.evidence.fact_spans.items()
            },
            "issues": [item.to_dict() for item in validated.evidence.issues],
        },
        "assumptions": [item.to_dict() for item in validated.assumptions],
        "candidates": candidates,
        "issues": [item.to_dict() for item in validated.issues],
    }
    return _canonical(payload, [20_000])


def _exact_fact_span(
    problem_text: str, fact: object, stored: object
) -> tuple[SourceSpan, SourceSpan] | None:
    """Rebuild the quote and require its quantity to equal Phase55 authority."""
    try:
        quote = fact.evidence_quote
        quote_index = fact.occurrence_index
        occurrences = quote_occurrences(problem_text, quote)
        if (
            type(quote_index) is not int
            or quote_index < 0
            or quote_index >= len(occurrences)
        ):
            return None
        quote_occurrence = occurrences[quote_index]
        matching = [
            item
            for item in quantity_occurrences(quote)
            if _normalized_number(item.raw_value)
            == _normalized_number(fact.raw_value)
            and _normalized_unit(item.raw_unit)
            == _normalized_unit(fact.raw_unit)
        ]
        quantity_index = fact.quantity_occurrence_index
        if (
            type(quantity_index) is not int
            or quantity_index < 0
            or quantity_index >= len(matching)
        ):
            return None
        quantity = matching[quantity_index]
        quantity_start = quote_occurrence.start + quantity.start
        quantity_end = quote_occurrence.start + quantity.end
        if (
            type(stored.start) is not int
            or type(stored.end) is not int
            or type(stored.quote) is not str
            or stored.start != quantity_start
            or stored.end != quantity_end
            or stored.quote != problem_text[quantity_start:quantity_end]
        ):
            return None
        return (
            SourceSpan(start=quote_occurrence.start, end=quote_occurrence.end),
            SourceSpan(start=stored.start, end=stored.end),
        )
    except Exception:
        return None


def adapt_validated_phase55(
    problem_text: str, validated: ValidatedParse, *, correction_revision: int = 0
) -> Phase55AdapterResult:
    """Adapt only an exact accepted Phase55 validation result, or reject it."""
    if type(problem_text) is not str or len(problem_text) > _MAX_TEXT or type(correction_revision) is not int or isinstance(correction_revision, bool) or not 0 <= correction_revision <= 1_000_000:
        return _failure(_issue(MechanicsIssueCode.schema_error, "adapter inputs must be exact bounded values", "input"))
    if type(validated) is not ValidatedParse:
        return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "an exact accepted ValidatedParse is required", "validated"))
    try:
        if (
            type(validated.parse) is not TextbookProblemParseV1
            or not validated.accepted
            or validated.selected_candidate is None
        ):
            return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "Phase55 acceptance and selected candidate are required", "validated"))
        diagnostic_candidate = validated.selected_candidate
        diagnostic_system_type = diagnostic_candidate.system_type.value
        diagnostic_subtype = diagnostic_candidate.subtype
        rebuilt_parse = TextbookProblemParseV1.model_validate(
            validated.parse.model_dump(mode="json")
        )
        fresh = validate_parse(problem_text, rebuilt_parse)
        if not fresh.accepted or fresh.selected_candidate is None:
            return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "fresh Phase55 validation did not accept the parse", "validated"))
        if _authority_projection(validated) != _authority_projection(fresh):
            return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "passed Phase55 authority differs from fresh validation", "validated"))
        parse = fresh.parse
        candidate = fresh.selected_candidate
    except Exception:
        return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "malformed, forged, or mutated Phase55 validation result", "validated"))

    entities_by_id = {item.entity_id: item for item in parse.entities}
    segments_by_id = {item.segment_id: item for item in parse.motion_segments}
    events_by_id = {item.event_id: item for item in parse.events}
    facts_by_id = {item.fact_id: item for item in parse.explicit_facts}
    queries_by_id = {item.query_id: item for item in parse.queries}
    proposals_by_id = {item.assumption_id: item for item in parse.assumption_proposals}
    selected_segments = set(candidate.target_segment_ids)
    selected_facts = tuple(sorted(candidate.fact_ids))
    selected_queries = tuple(sorted(candidate.query_ids))
    selected_assumptions = tuple(sorted(candidate.assumption_ids))
    if (not all(item in segments_by_id for item in selected_segments)
            or not all(item in facts_by_id for item in selected_facts)
            or not all(item in queries_by_id for item in selected_queries)
            or not all(item in proposals_by_id for item in selected_assumptions)):
        return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "candidate references are not closed", "selected_candidate"))

    selected_events = set()
    included_entities = set()
    selected_relations = set()
    for fact_id_value in selected_facts:
        fact = facts_by_id[fact_id_value]
        included_entities.add(fact.subject_id)
        if fact.segment_id:
            selected_segments.add(fact.segment_id)
        if fact.event_id:
            selected_events.add(fact.event_id)
    for query_id_value in selected_queries:
        query = queries_by_id[query_id_value]
        included_entities.add(query.subject_id)
        if query.segment_id:
            selected_segments.add(query.segment_id)
        if query.event_id:
            selected_events.add(query.event_id)
    for assumption_id_value in selected_assumptions:
        proposal = proposals_by_id[assumption_id_value]
        included_entities.add(proposal.subject_id)
        if proposal.segment_id:
            selected_segments.add(proposal.segment_id)

    # Fixed-point graph closure is deliberately sorted so relation list order
    # cannot change which connected topology is retained.
    changed = True
    while changed:
        changed = False
        if not selected_segments.issubset(segments_by_id) or not selected_events.issubset(events_by_id):
            return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "selected interval or event is unresolved", "selected_candidate"))
        for segment_id_value in sorted(selected_segments):
            segment = segments_by_id[segment_id_value]
            before_entities, before_events = len(included_entities), len(selected_events)
            included_entities.update(segment.actor_ids)
            selected_events.update(
                event_id_value
                for event_id_value in (segment.start_event_id, segment.end_event_id)
                if event_id_value
            )
            selected_events.update(
                event.event_id
                for event in events_by_id.values()
                if event.segment_id == segment_id_value
            )
            changed = changed or len(included_entities) != before_entities or len(selected_events) != before_events
        for event_id_value in sorted(selected_events):
            event = events_by_id[event_id_value]
            before_entities, before_segments = len(included_entities), len(selected_segments)
            included_entities.update(event.subject_ids)
            if event.segment_id:
                selected_segments.add(event.segment_id)
            changed = changed or len(included_entities) != before_entities or len(selected_segments) != before_segments
        for relation in sorted(parse.relations, key=lambda item: item.relation_id):
            relevant = (
                relation.relation_id in selected_relations
                or relation.segment_id in selected_segments
                or bool(set(relation.entity_ids).intersection(included_entities))
            )
            if not relevant:
                continue
            before = (len(selected_relations), len(included_entities), len(selected_segments))
            selected_relations.add(relation.relation_id)
            included_entities.update(relation.entity_ids)
            if relation.segment_id:
                selected_segments.add(relation.segment_id)
            changed = changed or before != (
                len(selected_relations), len(included_entities), len(selected_segments)
            )

    selected_relation_items = [
        relation
        for relation in sorted(parse.relations, key=lambda item: item.relation_id)
        if relation.relation_id in selected_relations
    ]
    if not included_entities or not included_entities.issubset(entities_by_id):
        return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "selected graph entity is missing", "entities"))
    for relation in selected_relation_items:
        if relation.kind.value in {"shares_velocity_constraint", "shares_acceleration_constraint"}:
            return _failure(_issue(MechanicsIssueCode.ast_unsupported, "Phase55 relation requires an equation absent from its contract", f"relations.{relation.relation_id}"))
        if relation.kind.value not in _GEOMETRY and relation.kind.value not in _INTERACTIONS:
            return _failure(_issue(MechanicsIssueCode.schema_error, "Phase55 relation has no conservative mechanics mapping", f"relations.{relation.relation_id}"))

    mapped_entities = []
    for entity_id in sorted(included_entities):
        item = entities_by_id[entity_id]
        primitive = _ENTITY_PRIMITIVES.get(item.kind.value)
        if primitive is None:
            return _failure(_issue(MechanicsIssueCode.schema_error, "entity kind is not safely representable", f"entities.{entity_id}"))
        mapped_entities.append(Entity(entity_id=_id("e", entity_id), primitive=primitive, label=item.label, aliases=list(item.aliases)))
    entity_id = lambda source: _id("e", source)
    interval_id = lambda source: _id("i", source)
    event_id = lambda source: _id("v", source)

    mapped_intervals = [MotionInterval(interval_id=interval_id(item.segment_id), order=item.order, subject_ids=[entity_id(x) for x in item.actor_ids], start_event_id=event_id(item.start_event_id) if item.start_event_id else None, end_event_id=event_id(item.end_event_id) if item.end_event_id else None) for item in sorted((segments_by_id[x] for x in selected_segments), key=lambda x: (x.order, x.segment_id))]
    mapped_events = []
    for source in sorted(selected_events):
        item = events_by_id[source]
        event_kind = _EVENTS.get(item.kind.value)
        if event_kind is None:
            return _failure(_issue(MechanicsIssueCode.schema_error, "event kind has no conservative mapping", f"events.{source}"))
        mapped_events.append(Event(event_id=event_id(source), kind=event_kind, subject_ids=[entity_id(x) for x in item.subject_ids], interval_ids=[interval_id(item.segment_id)] if item.segment_id else []))

    evidence, quantities = [], []
    for source in selected_facts:
        fact = facts_by_id[source]
        stored = fresh.evidence.fact_spans.get(source)
        rebuilt = _exact_fact_span(problem_text, fact, stored)
        if rebuilt is None:
            return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "stored Phase55 fact span does not exactly rebuild", f"explicit_facts.{source}"))
        spec = _FACTS.get(fact.semantic_key.value)
        if spec is None:
            return _failure(_issue(MechanicsIssueCode.schema_error, "explicit fact semantic key is not mapped", f"explicit_facts.{source}"))
        fact_span, quantity_span = rebuilt
        evidence_key, quantity_key = _id("x", source), _id("q", source)
        evidence.append(TextEvidence(evidence_id=evidence_key, quote=problem_text[fact_span.start:fact_span.end], source_span=fact_span, quantity_span=quantity_span, occurrence_index=fact.occurrence_index))
        component = _COMPONENTS.get(fact.direction.value, QuantityComponent.unspecified)
        direction = _DIRECTIONS.get(fact.direction.value)
        quantities.append(DraftQuantity(quantity_id=quantity_key, role=spec[0], subject_id=entity_id(fact.subject_id), interval_id=interval_id(fact.segment_id) if fact.segment_id else None, event_id=event_id(fact.event_id) if fact.event_id else None, component=component, direction=SemanticDirection(direction=direction) if direction else None, shape=QuantityShape.scalar, dimension=spec[1], provenance=Provenance.explicit_source, raw_value=fact.raw_value, raw_unit=fact.raw_unit, evidence_refs=[evidence_key]))

    mapped_geometry, mapped_interactions = [], []
    for relation in selected_relation_items:
        participants = [entity_id(x) for x in relation.entity_ids]
        if relation.kind.value in _GEOMETRY:
            mapped_geometry.append(GeometryRelation(relation_id=_id("g", relation.relation_id), kind=_GEOMETRY[relation.kind.value], participant_ids=participants, interval_id=interval_id(relation.segment_id) if relation.segment_id else None))
        else:
            mapped_interactions.append(Interaction(interaction_id=_id("r", relation.relation_id), kind=_INTERACTIONS[relation.kind.value], participant_ids=participants, interval_id=interval_id(relation.segment_id) if relation.segment_id else None))

    mapped_assumptions, approved, authorizations = [], [], {}
    evaluations = {item.assumption_id: item for item in fresh.assumptions}
    for source in selected_assumptions:
        evaluation, proposal = evaluations.get(source), proposals_by_id[source]
        if evaluation is None or evaluation.disposition not in {AssumptionDisposition.accepted_default, AssumptionDisposition.accepted_visible}:
            return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "selected assumption lacks accepted server evaluation", f"assumptions.{source}"))
        mapped = _id("a", source)
        mapped_assumptions.append(Assumption(assumption_id=mapped, kind=proposal.kind.value, subject_id=entity_id(proposal.subject_id), interval_id=interval_id(proposal.segment_id) if proposal.segment_id else None, disposition=DraftAssumptionDisposition.approved if evaluation.disposition is AssumptionDisposition.accepted_default else DraftAssumptionDisposition.visible, reason=evaluation.reason_code))
        approved.append(mapped)
        if any(value is not None for value in (evaluation.resolved_semantic_key, evaluation.resolved_value, evaluation.resolved_unit)):
            if not all(type(value) is str and value for value in (evaluation.resolved_semantic_key, evaluation.resolved_value, evaluation.resolved_unit)):
                return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "server assumption resolution is incomplete", f"assumptions.{source}"))
            if _SERVER_RESOLUTIONS.get(proposal.kind.value) != (
                evaluation.resolved_semantic_key, evaluation.resolved_value, evaluation.resolved_unit
            ):
                return _failure(_issue(MechanicsIssueCode.phase55_validation_required, "server assumption resolution does not match policy", f"assumptions.{source}"))
            spec = _FACTS.get(evaluation.resolved_semantic_key)
            if spec is None:
                return _failure(_issue(MechanicsIssueCode.schema_error, "server assumption semantic key is not mapped", f"assumptions.{source}"))
            authorizations[mapped] = AssumptionAuthorization(mapped, entity_id(proposal.subject_id), spec[0].value, evaluation.resolved_value, evaluation.resolved_unit, interval_id(proposal.segment_id) if proposal.segment_id else None)
            quantities.append(DraftQuantity(quantity_id=_id("d", source), role=spec[0], subject_id=entity_id(proposal.subject_id), interval_id=interval_id(proposal.segment_id) if proposal.segment_id else None, shape=QuantityShape.scalar, dimension=spec[1], provenance=Provenance.server_default, raw_value=evaluation.resolved_value, raw_unit=evaluation.resolved_unit, assumption_policy_ref=mapped))

    mapped_queries = []
    for source in selected_queries:
        item = queries_by_id[source]
        spec = _QUERIES.get(item.output_key.value)
        if spec is None:
            return _failure(_issue(MechanicsIssueCode.schema_error, "query output key is not mapped", f"queries.{source}"))
        component = _COMPONENTS.get(item.component.value, QuantityComponent.unspecified)
        mapped_queries.append(Query(query_id=_id("u", source), target=QueryTarget(role=spec[0], subject_id=entity_id(item.subject_id), interval_id=interval_id(item.segment_id) if item.segment_id else None, event_id=event_id(item.event_id) if item.event_id else None, component=component), output_unit=spec[2], output_dimension=spec[1], shape=QuantityShape.scalar))

    try:
        metadata = MechanicsMetadata(language=ProblemLanguage(parse.language), correction_revision=correction_revision, system_type=diagnostic_system_type, subtype=diagnostic_subtype, source_text_sha256=sha256(problem_text.encode("utf-8")).hexdigest())
        draft = MechanicsProblemDraftV1(schema="dynatutor.mechanics_problem_draft", version="1.0", metadata=metadata, source_assets=[], source_evidence=evidence, entities=mapped_entities, points=[], reference_frames=[], motion_intervals=mapped_intervals, events=mapped_events, symbols=[], geometry=mapped_geometry, interactions=mapped_interactions, constraints=[], state_conditions=[], quantities=quantities, queries=mapped_queries, principle_hints=[], assumptions=mapped_assumptions, ambiguities=[], figure_dependency=FigureDependency(level=FigureDependencyLevel(parse.figure_dependency.level.value), missing_information=list(parse.figure_dependency.missing_information)), unsupported_features=[UnsupportedFeature(feature_code=_id("z", item.feature_code), description=item.description, referenced_ids=[]) for item in parse.unsupported_features])
    except Exception:
        return _failure(_issue(MechanicsIssueCode.schema_error, "adapter could not construct the Phase56 draft", "draft"))
    validation = validate_draft(problem_text, draft, approved_assumption_ids=tuple(approved), authorized_assumptions=MappingProxyType(authorizations))
    return Phase55AdapterResult(validation.terminal, validation, validation.issues, draft if validation.accepted else None, tuple(approved), MappingProxyType(dict(authorizations)))


__all__ = ["PHASE55_ADAPTER_VERSION", "Phase55AdapterResult", "adapt_validated_phase55"]
