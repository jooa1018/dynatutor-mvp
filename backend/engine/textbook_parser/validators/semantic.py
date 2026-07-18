from __future__ import annotations

from collections import defaultdict

from engine.textbook_parser.contracts import (
    FactRelevance,
    FigureDependencyLevel,
    TextbookProblemParseV1,
)
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.graph_validation import adjacent_boundary_target


def validate_semantics(parse: TextbookProblemParseV1) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    grouped: dict[tuple[str, str | None, str | None, str | None], set[tuple[str, str]]] = defaultdict(set)
    for fact in parse.explicit_facts:
        key = (fact.subject_id, fact.segment_id, fact.event_id, fact.semantic_key)
        grouped[key].add((fact.raw_value, fact.raw_unit))
    for key, values in grouped.items():
        if len(values) > 1:
            issues.append(
                ValidationIssue(
                    ErrorCode.contradictory_fact,
                    Severity.critical,
                    "multiple explicit values are bound to the same subject, segment, event, and semantic key",
                    path="explicit_facts",
                    metadata={"binding": list(key), "values": sorted(values)},
                )
            )
    if parse.figure_dependency.level == FigureDependencyLevel.required:
        issues.append(
            ValidationIssue(
                ErrorCode.figure_required,
                Severity.info,
                "the problem requires information from a missing figure",
                path="figure_dependency",
            )
        )
    fact_by_id = {item.fact_id: item for item in parse.explicit_facts}
    query_by_id = {item.query_id: item for item in parse.queries}
    assumption_by_id = {
        item.assumption_id: item for item in parse.assumption_proposals
    }
    event_by_id = {item.event_id: item for item in parse.events}
    for candidate in parse.interpretation_candidates:
        target_segments = set(candidate.target_segment_ids)
        for fact_id in candidate.fact_ids:
            fact = fact_by_id.get(fact_id)
            # The graph validator owns dangling-reference diagnostics.  Keep
            # this semantic pass total so malformed model output can reach the
            # single field-level repair path instead of raising KeyError.
            if fact is None:
                continue
            adjacent_target = adjacent_boundary_target(parse, fact, target_segments)
            if (
                fact.relevance in {FactRelevance.solver_input, FactRelevance.constraint}
                and fact.segment_id is not None
                and fact.segment_id not in target_segments
                and adjacent_target is None
            ):
                issues.append(
                    ValidationIssue(
                        ErrorCode.invalid_reference,
                        Severity.critical,
                        "candidate solver input is bound to a non-target motion segment",
                        path=f"interpretation_candidates.{candidate.candidate_id}.fact_ids",
                        referenced_id=fact_id,
                    )
                )
            if fact.event_id is not None and fact.segment_id is not None:
                event = event_by_id.get(fact.event_id)
                if (
                    event is not None
                    and event.segment_id is not None
                    and event.segment_id != fact.segment_id
                    and adjacent_target is None
                ):
                    issues.append(
                        ValidationIssue(
                            ErrorCode.invalid_reference,
                            Severity.critical,
                            "fact segment and event segment bindings disagree",
                            path=f"explicit_facts.{fact_id}",
                            referenced_id=fact_id,
                        )
                    )
        for query_id in candidate.query_ids:
            query = query_by_id.get(query_id)
            if query is None:
                continue
            if query.segment_id is not None and query.segment_id not in target_segments:
                issues.append(
                    ValidationIssue(
                        ErrorCode.invalid_reference,
                        Severity.critical,
                        "candidate query is not bound to a target motion segment",
                        path=f"interpretation_candidates.{candidate.candidate_id}.query_ids",
                        referenced_id=query_id,
                    )
                )
        for assumption_id in candidate.assumption_ids:
            assumption = assumption_by_id.get(assumption_id)
            if assumption is None:
                continue
            if assumption.segment_id is not None and assumption.segment_id not in target_segments:
                issues.append(
                    ValidationIssue(
                        ErrorCode.invalid_reference,
                        Severity.critical,
                        "candidate assumption is bound to a non-target motion segment",
                        path=f"interpretation_candidates.{candidate.candidate_id}.assumption_ids",
                        referenced_id=assumption_id,
                    )
                )
    return issues


__all__ = ["validate_semantics"]
