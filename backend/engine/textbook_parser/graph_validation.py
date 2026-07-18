from __future__ import annotations

from collections.abc import Iterable

from engine.textbook_parser.contracts import (
    FactRelevance,
    ParseStatus,
    SegmentRelevance,
    TemporalRole,
    TextbookProblemParseV2,
)
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue


GRAPH_POLICY_VERSION = "typed-graph-policy-v2-actor-query"


def _issue(
    message: str,
    *,
    path: str,
    referenced_id: str | None = None,
    metadata: dict[str, object] | None = None,
    code: ErrorCode = ErrorCode.invalid_reference,
) -> ValidationIssue:
    return ValidationIssue(
        code,
        Severity.critical,
        message,
        path=path,
        referenced_id=referenced_id,
        metadata=metadata,
    )


def _unique_issues(kind: str, values: Iterable[str], path: str) -> list[ValidationIssue]:
    seen: set[str] = set()
    out: list[ValidationIssue] = []
    for index, value in enumerate(values):
        if value in seen:
            out.append(
                _issue(
                    f"duplicate {kind} ID",
                    path=f"{path}.{index}",
                    referenced_id=value,
                    code=ErrorCode.duplicate_id,
                )
            )
        seen.add(value)
    return out


def _require_ref(
    value: str | None,
    allowed: set[str],
    *,
    path: str,
    referenced_id: str | None,
) -> list[ValidationIssue]:
    if value is None or value in allowed:
        return []
    return [
        _issue(
            "reference does not exist in the typed graph",
            path=path,
            referenced_id=referenced_id or value,
            metadata={"missing_reference": value},
        )
    ]


def _require_refs(
    values: Iterable[str],
    allowed: set[str],
    *,
    path: str,
    referenced_id: str | None,
) -> list[ValidationIssue]:
    return [
        _issue(
            "reference does not exist in the typed graph",
            path=f"{path}.{index}",
            referenced_id=referenced_id or value,
            metadata={"missing_reference": value},
        )
        for index, value in enumerate(values)
        if value not in allowed
    ]


def adjacent_boundary_target(
    parse: TextbookProblemParseV2,
    fact,
    target_segment_ids: set[str],
):
    """Return the target segment reached through one validated shared boundary."""

    if fact.segment_id is None or fact.event_id is None:
        return None
    source = next(
        (item for item in parse.motion_segments if item.segment_id == fact.segment_id),
        None,
    )
    if source is None or source.segment_id in target_segment_ids:
        return None
    if source.end_event_id != fact.event_id:
        return None
    if fact.temporal_role not in {TemporalRole.final, TemporalRole.before_event}:
        return None
    targets = [
        item
        for item in parse.motion_segments
        if item.segment_id in target_segment_ids
        and item.start_event_id == fact.event_id
        and source.order < item.order
        and fact.subject_id in item.actor_ids
    ]
    return targets[0] if len(targets) == 1 else None


def validate_graph_contract(parse: TextbookProblemParseV2) -> tuple[ValidationIssue, ...]:
    """Validate graph closure with field-level paths instead of root Pydantic errors.

    Query subjects follow one policy for every physics family: a point or aggregate
    system queried on a segment must be present in that segment's ``actor_ids``.
    Relations establish deterministic body roles but never substitute for actor
    participation.
    """

    issues: list[ValidationIssue] = []
    entity_ids = {item.entity_id for item in parse.entities}
    segment_ids = {item.segment_id for item in parse.motion_segments}
    event_ids = {item.event_id for item in parse.events}
    fact_ids = {item.fact_id for item in parse.explicit_facts}
    relation_ids = {item.relation_id for item in parse.relations}
    query_ids = {item.query_id for item in parse.queries}
    assumption_ids = {item.assumption_id for item in parse.assumption_proposals}

    for kind, values, path in (
        ("entity", [item.entity_id for item in parse.entities], "entities"),
        ("segment", [item.segment_id for item in parse.motion_segments], "motion_segments"),
        ("event", [item.event_id for item in parse.events], "events"),
        ("fact", [item.fact_id for item in parse.explicit_facts], "explicit_facts"),
        ("relation", [item.relation_id for item in parse.relations], "relations"),
        ("query", [item.query_id for item in parse.queries], "queries"),
        ("assumption", [item.assumption_id for item in parse.assumption_proposals], "assumption_proposals"),
        ("candidate", [item.candidate_id for item in parse.interpretation_candidates], "interpretation_candidates"),
        ("ambiguity", [item.ambiguity_id for item in parse.ambiguities], "ambiguities"),
        ("segment order", [str(item.order) for item in parse.motion_segments], "motion_segments"),
    ):
        issues.extend(_unique_issues(kind, values, path))

    segment_by_id = {item.segment_id: item for item in parse.motion_segments}
    event_by_id = {item.event_id: item for item in parse.events}
    fact_by_id = {item.fact_id: item for item in parse.explicit_facts}
    query_by_id = {item.query_id: item for item in parse.queries}
    assumption_by_id = {item.assumption_id: item for item in parse.assumption_proposals}

    for index, segment in enumerate(parse.motion_segments):
        base = f"motion_segments.{index}"
        issues.extend(_require_refs(segment.actor_ids, entity_ids, path=f"{base}.actor_ids", referenced_id=segment.segment_id))
        issues.extend(_require_ref(segment.start_event_id, event_ids, path=f"{base}.start_event_id", referenced_id=segment.segment_id))
        issues.extend(_require_ref(segment.end_event_id, event_ids, path=f"{base}.end_event_id", referenced_id=segment.segment_id))
        if segment.start_event_id is not None and segment.start_event_id == segment.end_event_id:
            issues.append(_issue("segment start and end events must differ", path=f"{base}.end_event_id", referenced_id=segment.segment_id))
        for role, event_id in (
            ("start", segment.start_event_id),
            ("end", segment.end_event_id),
        ):
            event = event_by_id.get(event_id) if event_id is not None else None
            if event is None:
                continue
            if not set(event.subject_ids) <= set(segment.actor_ids):
                issues.append(
                    _issue(
                        f"segment {role} event subject must be a segment actor",
                        path=f"{base}.{role}_event_id",
                        referenced_id=segment.segment_id,
                    )
                )
            if event.segment_id is not None:
                boundary_segments = {
                    item.segment_id
                    for item in parse.motion_segments
                    if item.start_event_id == event_id or item.end_event_id == event_id
                }
                if event.segment_id not in boundary_segments:
                    issues.append(
                        _issue(
                            f"segment {role} event binding disagrees",
                            path=f"{base}.{role}_event_id",
                            referenced_id=segment.segment_id,
                        )
                    )

    for index, event in enumerate(parse.events):
        base = f"events.{index}"
        issues.extend(_require_refs(event.subject_ids, entity_ids, path=f"{base}.subject_ids", referenced_id=event.event_id))
        issues.extend(_require_ref(event.segment_id, segment_ids, path=f"{base}.segment_id", referenced_id=event.event_id))
        if event.segment_id in segment_by_id and not set(event.subject_ids) <= set(segment_by_id[event.segment_id].actor_ids):
            issues.append(_issue("event subjects must be actors of its segment", path=f"{base}.subject_ids", referenced_id=event.event_id))

    for index, fact in enumerate(parse.explicit_facts):
        base = f"explicit_facts.{index}"
        issues.extend(_require_ref(fact.subject_id, entity_ids, path=f"{base}.subject_id", referenced_id=fact.fact_id))
        issues.extend(_require_ref(fact.segment_id, segment_ids, path=f"{base}.segment_id", referenced_id=fact.fact_id))
        issues.extend(_require_ref(fact.event_id, event_ids, path=f"{base}.event_id", referenced_id=fact.fact_id))
        if fact.segment_id in segment_by_id and fact.subject_id not in segment_by_id[fact.segment_id].actor_ids:
            issues.append(_issue("fact subject must be an actor of its segment", path=f"{base}.subject_id", referenced_id=fact.fact_id))
        if fact.event_id in event_by_id:
            event = event_by_id[fact.event_id]
            if fact.subject_id not in event.subject_ids:
                issues.append(_issue("fact subject must be a subject of its event", path=f"{base}.subject_id", referenced_id=fact.fact_id))
            if fact.segment_id in segment_by_id and event.segment_id is not None:
                segment = segment_by_id[fact.segment_id]
                linked = {segment.segment_id}
                linked.update(
                    item.segment_id
                    for item in parse.motion_segments
                    if item.start_event_id == event.event_id or item.end_event_id == event.event_id
                )
                if event.segment_id not in linked:
                    issues.append(_issue("fact segment and event bindings disagree", path=f"{base}.event_id", referenced_id=fact.fact_id))
        if fact.temporal_role in {TemporalRole.before_event, TemporalRole.at_event, TemporalRole.after_event} and fact.event_id is None:
            issues.append(_issue("fact temporal role requires event_id", path=f"{base}.event_id", referenced_id=fact.fact_id))
        if fact.segment_id in segment_by_id and fact.event_id is not None:
            segment = segment_by_id[fact.segment_id]
            if fact.temporal_role == TemporalRole.initial and segment.start_event_id != fact.event_id:
                issues.append(_issue("initial fact must bind the segment start event", path=f"{base}.event_id", referenced_id=fact.fact_id))
            if fact.temporal_role == TemporalRole.final and segment.end_event_id != fact.event_id:
                issues.append(_issue("final fact must bind the segment end event", path=f"{base}.event_id", referenced_id=fact.fact_id))

    for index, relation in enumerate(parse.relations):
        base = f"relations.{index}"
        issues.extend(_require_refs(relation.entity_ids, entity_ids, path=f"{base}.entity_ids", referenced_id=relation.relation_id))
        issues.extend(_require_ref(relation.segment_id, segment_ids, path=f"{base}.segment_id", referenced_id=relation.relation_id))

    for index, query in enumerate(parse.queries):
        base = f"queries.{index}"
        issues.extend(_require_ref(query.subject_id, entity_ids, path=f"{base}.subject_id", referenced_id=query.query_id))
        issues.extend(_require_ref(query.segment_id, segment_ids, path=f"{base}.segment_id", referenced_id=query.query_id))
        issues.extend(_require_ref(query.event_id, event_ids, path=f"{base}.event_id", referenced_id=query.query_id))
        if query.segment_id in segment_by_id and query.subject_id not in segment_by_id[query.segment_id].actor_ids:
            issues.append(_issue("query subject must be an actor of segment target", path=f"{base}.subject_id", referenced_id=query.query_id, metadata={"subject_role": "target_actor", "target_segment_id": query.segment_id}))
        if query.event_id in event_by_id and query.subject_id not in event_by_id[query.event_id].subject_ids:
            issues.append(_issue("query subject must be a subject of its event", path=f"{base}.subject_id", referenced_id=query.query_id))
        if query.segment_id in segment_by_id and query.event_id in event_by_id:
            event = event_by_id[query.event_id]
            if event.segment_id is not None:
                boundary_segments = {
                    item.segment_id
                    for item in parse.motion_segments
                    if item.start_event_id == event.event_id
                    or item.end_event_id == event.event_id
                }
                if query.segment_id not in boundary_segments:
                    issues.append(_issue("query segment and event bindings disagree", path=f"{base}.event_id", referenced_id=query.query_id))

    for index, assumption in enumerate(parse.assumption_proposals):
        base = f"assumption_proposals.{index}"
        issues.extend(_require_ref(assumption.subject_id, entity_ids, path=f"{base}.subject_id", referenced_id=assumption.assumption_id))
        issues.extend(_require_ref(assumption.segment_id, segment_ids, path=f"{base}.segment_id", referenced_id=assumption.assumption_id))
        if assumption.segment_id in segment_by_id and assumption.subject_id not in segment_by_id[assumption.segment_id].actor_ids:
            issues.append(_issue("assumption subject must be an actor of its segment", path=f"{base}.subject_id", referenced_id=assumption.assumption_id))

    for index, candidate in enumerate(parse.interpretation_candidates):
        base = f"interpretation_candidates.{index}"
        issues.extend(_require_refs(candidate.target_segment_ids, segment_ids, path=f"{base}.target_segment_ids", referenced_id=candidate.candidate_id))
        issues.extend(_require_refs(candidate.fact_ids, fact_ids, path=f"{base}.fact_ids", referenced_id=candidate.candidate_id))
        issues.extend(_require_refs(candidate.query_ids, query_ids, path=f"{base}.query_ids", referenced_id=candidate.candidate_id))
        issues.extend(_require_refs(candidate.assumption_ids, assumption_ids, path=f"{base}.assumption_ids", referenced_id=candidate.candidate_id))
        targets = set(candidate.target_segment_ids) & segment_ids
        candidate_queries = [query_by_id[item] for item in candidate.query_ids if item in query_by_id]
        for query_index, query in enumerate(candidate_queries):
            if query.segment_id not in targets:
                issues.append(_issue("candidate query must bind a target segment", path=f"{base}.query_ids.{query_index}", referenced_id=query.query_id, metadata={"target_segment_id": query.segment_id}))
        if targets - {query.segment_id for query in candidate_queries}:
            issues.append(_issue("every candidate target segment must be query-bound", path=f"{base}.query_ids", referenced_id=candidate.candidate_id, metadata={"target_segment_ids": sorted(targets)}))
        for fact_index, fact_id in enumerate(candidate.fact_ids):
            fact = fact_by_id.get(fact_id)
            if fact is None or fact.relevance not in {FactRelevance.solver_input, FactRelevance.constraint}:
                continue
            if fact.segment_id not in targets and adjacent_boundary_target(parse, fact, targets) is None:
                issues.append(_issue("candidate solver fact must bind a target segment or adjacent imported boundary", path=f"{base}.fact_ids.{fact_index}", referenced_id=fact_id, metadata={"target_segment_ids": sorted(targets)}))
        for assumption_index, assumption_id in enumerate(candidate.assumption_ids):
            assumption = assumption_by_id.get(assumption_id)
            if assumption is not None and assumption.segment_id not in targets:
                issues.append(_issue("candidate assumption must bind a target segment", path=f"{base}.assumption_ids.{assumption_index}", referenced_id=assumption_id))

    allowed_ambiguity_ids = entity_ids | segment_ids | event_ids | fact_ids | relation_ids | query_ids | assumption_ids
    for index, ambiguity in enumerate(parse.ambiguities):
        issues.extend(_require_refs(ambiguity.referenced_ids, allowed_ambiguity_ids, path=f"ambiguities.{index}.referenced_ids", referenced_id=ambiguity.ambiguity_id))

    target_segments = {
        segment.segment_id
        for segment in parse.motion_segments
        if segment.relevance == SegmentRelevance.target
    }
    query_segments = {query.segment_id for query in parse.queries if query.segment_id is not None}
    if parse.parse_status == ParseStatus.complete and target_segments - query_segments:
        issues.append(_issue("every target segment must be referenced by a query", path="queries", metadata={"target_segment_ids": sorted(target_segments - query_segments)}))

    for event_id in event_ids:
        starts = [item.order for item in parse.motion_segments if item.start_event_id == event_id]
        ends = [item.order for item in parse.motion_segments if item.end_event_id == event_id]
        if starts and ends and max(ends) >= min(starts):
            issues.append(_issue("shared boundary event reverses segment order", path="motion_segments", referenced_id=event_id))

    return tuple(issues)


__all__ = [
    "GRAPH_POLICY_VERSION",
    "adjacent_boundary_target",
    "validate_graph_contract",
]
