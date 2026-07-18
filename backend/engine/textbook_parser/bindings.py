from __future__ import annotations

from dataclasses import asdict, dataclass

from engine.textbook_parser.contracts import (
    Direction,
    FactRelevance,
    InterpretationCandidate,
    MotionModel,
    TemporalRole,
    TextbookProblemParseV1,
)
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.ontology import canonical_symbol


BINDING_POLICY_VERSION = "candidate-binding-v1"


@dataclass(frozen=True)
class InputBinding:
    fact_id: str
    symbol: str
    subject_id: str
    segment_id: str | None
    event_id: str | None
    temporal_role: str
    direction: str

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class BindingReport:
    candidate_id: str
    bindings: tuple[InputBinding, ...]
    relation_ids: tuple[str, ...]
    completeness: float
    issues: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "bindings": [item.to_dict() for item in self.bindings],
            "relation_ids": list(self.relation_ids),
            "completeness": self.completeness,
            "policy_version": BINDING_POLICY_VERSION,
            "issues": [item.to_dict() for item in self.issues],
        }


_SYSTEM_MOTION_MODELS: dict[str, frozenset[MotionModel]] = {
    "constant_acceleration_1d": frozenset({MotionModel.constant_acceleration_1d}),
    "projectile_motion": frozenset({MotionModel.projectile_free_flight}),
    "particle_on_incline": frozenset({MotionModel.sliding_on_incline}),
    "fixed_axis_rotation": frozenset({MotionModel.fixed_axis_rotation}),
    "pure_rolling_energy": frozenset({MotionModel.rolling_without_slipping}),
    "impulse_momentum": frozenset({MotionModel.impulse_interval, MotionModel.collision_contact}),
    "spring_mass_vibration": frozenset({MotionModel.spring_oscillation}),
    "constant_force_work": frozenset({MotionModel.energy_interval}),
}


def _ordered_roles(parse: TextbookProblemParseV1, target_segments: set[str]) -> tuple[str, ...]:
    """Resolve body roles from declared relations before falling back to actor order."""

    target_actors: list[str] = []
    for segment in sorted(parse.motion_segments, key=lambda item: item.order):
        if segment.segment_id not in target_segments:
            continue
        for entity_id in segment.actor_ids:
            if entity_id not in target_actors:
                target_actors.append(entity_id)
    connected = set(target_actors)
    relevant_relations = []
    changed = True
    while changed:
        changed = False
        for relation in parse.relations:
            if relation.segment_id is not None and relation.segment_id not in target_segments:
                continue
            if not (set(relation.entity_ids) & connected):
                continue
            if relation not in relevant_relations:
                relevant_relations.append(relation)
            before = len(connected)
            connected.update(relation.entity_ids)
            changed = changed or len(connected) != before
    ordered: list[str] = []
    for relation in relevant_relations:
        for entity_id in relation.entity_ids:
            if entity_id in connected and entity_id not in ordered:
                ordered.append(entity_id)
    for entity_id in target_actors:
        if entity_id not in ordered:
            ordered.append(entity_id)
    return tuple(ordered)


def _fact_symbol(fact, role_by_entity: dict[str, int]) -> str | None:
    symbol = canonical_symbol(fact.semantic_key)
    role = role_by_entity.get(fact.subject_id)
    if symbol == "m" and role is not None and len(role_by_entity) > 1:
        return f"m{role}"
    if symbol == "v" and role is not None and len(role_by_entity) > 1:
        if fact.temporal_role in {TemporalRole.final, TemporalRole.after_event}:
            return f"v{role}_after"
        return f"v{role}"
    if symbol == "v" and fact.temporal_role in {
        TemporalRole.initial,
        TemporalRole.before_event,
    }:
        return "v0"
    if symbol == "v" and fact.temporal_role in {
        TemporalRole.final,
        TemporalRole.after_event,
        TemporalRole.at_event,
    }:
        return "vf"
    return symbol


def evaluate_candidate_bindings(
    parse: TextbookProblemParseV1,
    candidate: InterpretationCandidate,
) -> BindingReport:
    target_segments = set(candidate.target_segment_ids)
    segment_by_id = {item.segment_id: item for item in parse.motion_segments}
    event_by_id = {item.event_id: item for item in parse.events}
    fact_by_id = {item.fact_id: item for item in parse.explicit_facts}
    query_by_id = {item.query_id: item for item in parse.queries}
    assumption_by_id = {
        item.assumption_id: item for item in parse.assumption_proposals
    }
    query_subjects = {
        query_by_id[item].subject_id for item in candidate.query_ids
    }
    roles = _ordered_roles(parse, target_segments)
    role_by_entity = {entity_id: index for index, entity_id in enumerate(roles, start=1)}
    relevant_entities = set(roles)
    relation_ids = tuple(
        item.relation_id
        for item in parse.relations
        if item.segment_id is None or item.segment_id in target_segments
        if set(item.entity_ids) & relevant_entities
    )
    issues: list[ValidationIssue] = []
    bindings: list[InputBinding] = []
    completed = 0
    total = (
        len(candidate.fact_ids)
        + len(candidate.query_ids)
        + len(candidate.assumption_ids)
        + len(target_segments)
    )
    if len(relevant_entities) > 1:
        total += 1
        if relation_ids:
            completed += 1
        else:
            issues.append(
                ValidationIssue(
                    ErrorCode.relation_binding_missing,
                    Severity.error,
                    "multi-entity interpretation has no target relation establishing body roles",
                    path=f"interpretation_candidates.{candidate.candidate_id}",
                    referenced_id=candidate.candidate_id,
                )
            )

    allowed_models = _SYSTEM_MOTION_MODELS.get(candidate.system_type)
    for segment_id in target_segments:
        segment = segment_by_id[segment_id]
        compatible = allowed_models is None or bool(
            set(segment.motion_model_candidates) & allowed_models
        )
        if compatible:
            completed += 1
        else:
            issues.append(
                ValidationIssue(
                    ErrorCode.motion_model_mismatch,
                    Severity.error,
                    "candidate system_type is incompatible with the target segment motion model",
                    path=f"interpretation_candidates.{candidate.candidate_id}.target_segment_ids",
                    referenced_id=candidate.candidate_id,
                    metadata={
                        "system_type": candidate.system_type,
                        "segment_id": segment_id,
                        "motion_models": [item.value for item in segment.motion_model_candidates],
                    },
                )
            )

    for query_id in candidate.query_ids:
        query = query_by_id[query_id]
        valid = query.segment_id in target_segments and query.subject_id in relevant_entities
        if query.event_id is not None:
            event = event_by_id[query.event_id]
            valid = valid and event.segment_id in {None, query.segment_id}
        if valid:
            completed += 1
        else:
            issues.append(
                ValidationIssue(
                    ErrorCode.candidate_binding_mismatch,
                    Severity.error,
                    "candidate query does not close over its target segment, subject, and event",
                    path=f"interpretation_candidates.{candidate.candidate_id}.query_ids",
                    referenced_id=query_id,
                )
            )

    for assumption_id in candidate.assumption_ids:
        assumption = assumption_by_id[assumption_id]
        valid = (
            assumption.segment_id in target_segments
            and assumption.subject_id in relevant_entities
        )
        if candidate.system_type == "constant_acceleration_1d":
            valid = valid and assumption.subject_id in query_subjects
        if valid:
            completed += 1
        else:
            issues.append(
                ValidationIssue(
                    ErrorCode.candidate_binding_mismatch,
                    Severity.error,
                    "candidate assumption does not close over the target segment and query subject",
                    path=f"interpretation_candidates.{candidate.candidate_id}.assumption_ids",
                    referenced_id=assumption_id,
                )
            )

    symbol_owner: dict[str, InputBinding] = {}
    for fact_id in candidate.fact_ids:
        fact = fact_by_id[fact_id]
        symbol = _fact_symbol(fact, role_by_entity)
        valid = (
            fact.relevance in {FactRelevance.solver_input, FactRelevance.constraint}
            and fact.segment_id in target_segments
            and fact.subject_id in relevant_entities
            and symbol is not None
        )
        if candidate.system_type == "constant_acceleration_1d":
            valid = valid and fact.subject_id in query_subjects
        if fact.event_id is not None:
            event = event_by_id[fact.event_id]
            valid = valid and event.segment_id in {None, fact.segment_id}
        if fact.kind.value == "vector_component" and fact.direction in {
            Direction.unspecified,
            Direction.not_applicable,
        }:
            valid = False
        if not valid:
            issues.append(
                ValidationIssue(
                    ErrorCode.candidate_binding_mismatch,
                    Severity.error,
                    "candidate fact does not close over the solver target segment, subject, event, temporal role, and direction",
                    path=f"interpretation_candidates.{candidate.candidate_id}.fact_ids",
                    referenced_id=fact_id,
                )
            )
            continue
        binding = InputBinding(
            fact_id=fact.fact_id,
            symbol=symbol,
            subject_id=fact.subject_id,
            segment_id=fact.segment_id,
            event_id=fact.event_id,
            temporal_role=fact.temporal_role.value,
            direction=fact.direction.value,
        )
        previous = symbol_owner.get(symbol)
        if previous is not None:
            issues.append(
                ValidationIssue(
                    ErrorCode.canonical_symbol_collision,
                    Severity.critical,
                    "multiple explicit facts resolve to the same canonical symbol",
                    path=f"interpretation_candidates.{candidate.candidate_id}.fact_ids",
                    referenced_id=candidate.candidate_id,
                    metadata={
                        "symbol": symbol,
                        "fact_ids": [previous.fact_id, fact.fact_id],
                    },
                )
            )
            continue
        symbol_owner[symbol] = binding
        bindings.append(binding)
        completed += 1

    completeness = round(completed / total, 6) if total else 0.0
    return BindingReport(
        candidate.candidate_id,
        tuple(bindings),
        relation_ids,
        completeness,
        tuple(issues),
    )


__all__ = [
    "BINDING_POLICY_VERSION",
    "BindingReport",
    "InputBinding",
    "evaluate_candidate_bindings",
]
