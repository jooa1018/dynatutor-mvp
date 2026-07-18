from __future__ import annotations

from collections import defaultdict

from engine.textbook_parser.contracts import FigureDependencyLevel, TextbookProblemParseV1
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue


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
    return issues


__all__ = ["validate_semantics"]
