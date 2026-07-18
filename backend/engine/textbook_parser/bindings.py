from __future__ import annotations

from dataclasses import asdict, dataclass

from engine.textbook_parser.contracts import (
    Direction,
    FactRelevance,
    InterpretationCandidate,
    MotionModel,
    RelationKind,
    TextbookProblemParseV1,
)
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.ontology import canonical_symbol
from engine.textbook_parser.temporal_bindings import resolve_fact_symbol


BINDING_POLICY_VERSION = "candidate-binding-v2"


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

_SYSTEM_RELATION_KINDS: dict[str, frozenset[RelationKind]] = {
    "impulse_momentum": frozenset({RelationKind.collides_with, RelationKind.contact_with}),
    "pulley_atwood": frozenset({RelationKind.connected_by_rope, RelationKind.passes_over_pulley}),
    "pulley_table_hanging": frozenset({RelationKind.connected_by_rope, RelationKind.passes_over_pulley}),
    "pulley_incline_hanging": frozenset({RelationKind.connected_by_rope, RelationKind.passes_over_pulley}),
    "massive_pulley_atwood": frozenset({RelationKind.connected_by_rope, RelationKind.passes_over_pulley}),
}


@dataclass(frozen=True)
class RoleResolution:
    roles: tuple[str, ...]
    relevant_entities: frozenset[str]
    system_query_subjects: frozenset[str]
    relation_ids: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]


def _ordered_roles(
    parse: TextbookProblemParseV1,
    candidate: InterpretationCandidate,
    target_segments: set[str],
) -> RoleResolution:
    """Assign roles from query/fact semantics, never input array order or IDs."""

    segment_by_id = {item.segment_id: item for item in parse.motion_segments}
    fact_by_id = {item.fact_id: item for item in parse.explicit_facts}
    query_by_id = {item.query_id: item for item in parse.queries}
    assumption_by_id = {item.assumption_id: item for item in parse.assumption_proposals}
    target_actors = {
        entity_id
        for segment_id in target_segments
        for entity_id in segment_by_id[segment_id].actor_ids
    }
    solver_facts = [
        fact_by_id[item]
        for item in candidate.fact_ids
        if fact_by_id[item].relevance in {FactRelevance.solver_input, FactRelevance.constraint}
    ]
    query_subjects = {query_by_id[item].subject_id for item in candidate.query_ids}
    fact_subjects = {item.subject_id for item in solver_facts}
    system_query_subjects = (
        query_subjects - fact_subjects
        if candidate.system_type in _SYSTEM_RELATION_KINDS and len(fact_subjects) >= 2
        else set()
    )
    role_query_subjects = query_subjects - system_query_subjects
    assumption_subjects = {
        assumption_by_id[item].subject_id for item in candidate.assumption_ids
    }
    relevant_entities = (
        role_query_subjects
        | fact_subjects
        | (assumption_subjects - system_query_subjects)
    ) & target_actors
    allowed_kinds = _SYSTEM_RELATION_KINDS.get(candidate.system_type, frozenset())
    relevant_relations = []
    for relation in parse.relations:
        if relation.segment_id is not None and relation.segment_id not in target_segments:
            continue
        participants = set(relation.entity_ids) & relevant_entities
        if len(participants) < 2 or relation.kind not in allowed_kinds:
            continue
        relevant_relations.append(relation)

    issues: list[ValidationIssue] = []
    roles_are_closed = True
    if len(relevant_entities) > 1:
        connected: set[str] = set()
        if relevant_relations:
            seed_candidates = role_query_subjects & relevant_entities
            seed = (
                next(iter(seed_candidates))
                if len(seed_candidates) == 1
                else sorted(relevant_entities)[0]
            )
            connected.add(seed)
            changed = True
            while changed:
                changed = False
                for relation in relevant_relations:
                    participants = set(relation.entity_ids) & relevant_entities
                    if participants & connected and not participants <= connected:
                        connected.update(participants)
                        changed = True
        if connected != relevant_entities:
            roles_are_closed = False
            issues.append(
                ValidationIssue(
                    ErrorCode.relation_binding_missing,
                    Severity.error,
                    "multi-entity solver inputs lack an explicit allowed relation closure",
                    path=f"interpretation_candidates.{candidate.candidate_id}",
                    referenced_id=candidate.candidate_id,
                )
            )

    def signature(entity_id: str) -> tuple[object, ...]:
        fact_signature = tuple(
            sorted(
                (
                    item.semantic_key,
                    item.temporal_role.value,
                    item.direction.value,
                    segment_by_id[item.segment_id].order if item.segment_id else 0,
                )
                for item in solver_facts
                if item.subject_id == entity_id
            )
        )
        query_signature = tuple(
            sorted(
                (
                    query_by_id[item].output_key.value,
                    query_by_id[item].component.value,
                    segment_by_id[query_by_id[item].segment_id].order,
                )
                for item in candidate.query_ids
                if query_by_id[item].subject_id == entity_id
            )
        )
        assumption_signature = tuple(
            sorted(
                assumption_by_id[item].kind.value
                for item in candidate.assumption_ids
                if assumption_by_id[item].subject_id == entity_id
            )
        )
        relation_signature = tuple(
            sorted(
                relation.kind.value
                for relation in relevant_relations
                if entity_id in relation.entity_ids
            )
        )
        entity = next(item for item in parse.entities if item.entity_id == entity_id)
        return (
            0 if entity_id in role_query_subjects else 1,
            query_signature,
            fact_signature,
            assumption_signature,
            relation_signature,
            entity.kind.value,
        )

    by_signature: dict[tuple[object, ...], list[str]] = {}
    for entity_id in relevant_entities:
        by_signature.setdefault(signature(entity_id), []).append(entity_id)
    if any(len(items) > 1 for items in by_signature.values()):
        roles_are_closed = False
        issues.append(
            ValidationIssue(
                ErrorCode.relation_binding_missing,
                Severity.error,
                "symmetric multi-body roles are not distinguishable from typed query/fact semantics",
                path=f"interpretation_candidates.{candidate.candidate_id}",
                referenced_id=candidate.candidate_id,
            )
        )
    if roles_are_closed:
        roles = tuple(
            entity_ids[0]
            for _, entity_ids in sorted(by_signature.items(), key=lambda item: item[0])
        )
    else:
        roles = ()
    relation_ids = tuple(
        item.relation_id
        for item in sorted(
            relevant_relations,
            key=lambda item: (
                item.kind.value,
                segment_by_id[item.segment_id].order if item.segment_id else 0,
                item.relation_id,
            ),
        )
    )
    return RoleResolution(
        roles,
        frozenset(relevant_entities),
        frozenset(system_query_subjects),
        relation_ids,
        tuple(issues),
    )


def _fact_symbol(fact, role_by_entity: dict[str, int], role_count: int) -> str | None:
    symbol = canonical_symbol(fact.semantic_key)
    role = role_by_entity.get(fact.subject_id)
    if symbol == "m" and role is not None and role_count > 1:
        return f"m{role}"
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
    role_resolution = _ordered_roles(parse, candidate, target_segments)
    roles = role_resolution.roles
    role_by_entity = {entity_id: index for index, entity_id in enumerate(roles, start=1)}
    relevant_entities = set(role_resolution.relevant_entities)
    system_query_subjects = set(role_resolution.system_query_subjects)
    relation_ids = role_resolution.relation_ids
    issues: list[ValidationIssue] = list(role_resolution.issues)
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
    for segment_id in sorted(target_segments, key=lambda item: segment_by_id[item].order):
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
        valid_subject = query.subject_id in relevant_entities or (
            query.subject_id in system_query_subjects and bool(relation_ids)
        )
        valid = query.segment_id in target_segments and valid_subject
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
        valid_subject = assumption.subject_id in relevant_entities or (
            assumption.subject_id in system_query_subjects and bool(relation_ids)
        )
        valid = (
            assumption.segment_id in target_segments
            and valid_subject
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
    ordered_fact_ids = sorted(
        candidate.fact_ids,
        key=lambda item: (
            role_by_entity.get(fact_by_id[item].subject_id, 0),
            fact_by_id[item].semantic_key,
            fact_by_id[item].temporal_role.value,
            fact_by_id[item].direction.value,
        ),
    )
    for fact_id in ordered_fact_ids:
        fact = fact_by_id[fact_id]
        temporal = resolve_fact_symbol(
            parse,
            fact,
            target_segment_ids=target_segments,
            role=role_by_entity.get(fact.subject_id),
            role_count=len(relevant_entities),
        )
        symbol = (
            temporal.symbol
            if fact.semantic_key
            in {"velocity", "velocity_before", "velocity_after", "initial_velocity", "final_velocity"}
            else _fact_symbol(fact, role_by_entity, len(relevant_entities))
        )
        if temporal.issue is not None:
            issues.append(temporal.issue)
        valid = (
            fact.relevance in {FactRelevance.solver_input, FactRelevance.constraint}
            and fact.segment_id in target_segments
            and fact.subject_id in relevant_entities
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
        if (
            len(relevant_entities) > 1
            and role_by_entity.get(fact.subject_id) is None
        ):
            issues.append(
                ValidationIssue(
                    ErrorCode.relation_binding_missing,
                    Severity.error,
                    "multi-body fact has no deterministic closed semantic role",
                    path=f"interpretation_candidates.{candidate.candidate_id}.fact_ids",
                    referenced_id=fact_id,
                )
            )
            continue
        # An ontology gap is a capability-completeness problem, not proof that
        # the graph identity binding is wrong. It remains unsupplied and cannot
        # enter canonical projection; the deterministic capability gate abstains.
        if symbol is None:
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
