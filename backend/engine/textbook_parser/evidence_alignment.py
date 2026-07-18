from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from engine.textbook_parser.contracts import ExplicitFact, TextbookProblemParseV1
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue


_NUMBER_RE = re.compile(
    r"(?<![\d.])[+−-]?(?:\d+(?:\.\d+)?|\.\d+)(?:\s*/\s*\d+(?:\.\d+)?)?(?![\d.])"
)


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    quote: str

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "quote": self.quote}


@dataclass(frozen=True)
class EvidenceValidation:
    fact_spans: dict[str, SourceSpan]
    issues: tuple[ValidationIssue, ...]


def _normalized_token(value: str) -> str:
    return unicodedata.normalize("NFKC", value).replace("−", "-").replace(" ", "")


def quote_occurrences(problem_text: str, quote: str) -> list[SourceSpan]:
    if not quote:
        return []
    out: list[SourceSpan] = []
    start = 0
    while True:
        index = problem_text.find(quote, start)
        if index < 0:
            break
        out.append(SourceSpan(index, index + len(quote), quote))
        start = index + 1
    return out


def _numeric_tokens(text: str) -> list[str]:
    return [_normalized_token(match.group(0)) for match in _NUMBER_RE.finditer(text)]


def _unit_occurs(quote: str, unit: str) -> bool:
    if not unit:
        return True
    normalized_quote = unicodedata.normalize("NFKC", quote).replace(" ", "")
    normalized_unit = unicodedata.normalize("NFKC", unit).replace(" ", "")
    return normalized_unit in normalized_quote


def align_explicit_fact(problem_text: str, fact: ExplicitFact) -> tuple[SourceSpan | None, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    occurrences = quote_occurrences(problem_text, fact.evidence_quote)
    if not occurrences:
        issues.append(
            ValidationIssue(
                ErrorCode.evidence_quote_missing,
                Severity.critical,
                "explicit fact evidence quote is not an exact substring of the problem",
                path=f"explicit_facts.{fact.fact_id}.evidence_quote",
                referenced_id=fact.fact_id,
            )
        )
        return None, issues
    if fact.occurrence_index >= len(occurrences):
        issues.append(
            ValidationIssue(
                ErrorCode.evidence_occurrence_missing,
                Severity.critical,
                "explicit fact occurrence_index does not identify a source occurrence",
                path=f"explicit_facts.{fact.fact_id}.occurrence_index",
                referenced_id=fact.fact_id,
                metadata={"occurrence_count": len(occurrences)},
            )
        )
        return None, issues

    source_numbers = _numeric_tokens(problem_text)
    quote_numbers = _numeric_tokens(fact.evidence_quote)
    raw_number = _normalized_token(fact.raw_value)
    if raw_number not in source_numbers:
        issues.append(
            ValidationIssue(
                ErrorCode.invented_explicit_number,
                Severity.critical,
                "explicit numerical value does not occur in the original problem",
                path=f"explicit_facts.{fact.fact_id}.raw_value",
                referenced_id=fact.fact_id,
            )
        )
    if raw_number not in quote_numbers:
        issues.append(
            ValidationIssue(
                ErrorCode.raw_value_mismatch,
                Severity.critical,
                "raw_value does not match a numeric token in its evidence quote",
                path=f"explicit_facts.{fact.fact_id}.raw_value",
                referenced_id=fact.fact_id,
            )
        )
    if not _unit_occurs(fact.evidence_quote, fact.raw_unit):
        issues.append(
            ValidationIssue(
                ErrorCode.raw_unit_mismatch,
                Severity.critical,
                "raw_unit does not occur in its evidence quote",
                path=f"explicit_facts.{fact.fact_id}.raw_unit",
                referenced_id=fact.fact_id,
            )
        )
    return occurrences[fact.occurrence_index], issues


def _quoted_fields(parse: TextbookProblemParseV1):
    for item in parse.entities:
        yield f"entities.{item.entity_id}.evidence_quote", item.evidence_quote
    for item in parse.motion_segments:
        yield f"motion_segments.{item.segment_id}.evidence_quote", item.evidence_quote
    for item in parse.events:
        yield f"events.{item.event_id}.evidence_quote", item.evidence_quote
    for item in parse.relations:
        yield f"relations.{item.relation_id}.evidence_quote", item.evidence_quote
    for item in parse.queries:
        yield f"queries.{item.query_id}.evidence_quote", item.evidence_quote
    for item in parse.assumption_proposals:
        if item.supporting_quote:
            yield f"assumption_proposals.{item.assumption_id}.supporting_quote", item.supporting_quote
    if parse.figure_dependency.evidence_quote:
        yield "figure_dependency.evidence_quote", parse.figure_dependency.evidence_quote
    for item in parse.ambiguities:
        if item.evidence_quote:
            yield f"ambiguities.{item.ambiguity_id}.evidence_quote", item.evidence_quote
    for item in parse.unsupported_features:
        if item.evidence_quote:
            yield f"unsupported_features.{item.feature_code}.evidence_quote", item.evidence_quote


def validate_evidence(problem_text: str, parse: TextbookProblemParseV1) -> EvidenceValidation:
    issues: list[ValidationIssue] = []
    spans: dict[str, SourceSpan] = {}
    for path, quote in _quoted_fields(parse):
        if not quote_occurrences(problem_text, quote):
            issues.append(
                ValidationIssue(
                    ErrorCode.evidence_quote_missing,
                    Severity.error,
                    "evidence quote is not an exact substring of the problem",
                    path=path,
                )
            )
    for fact in parse.explicit_facts:
        span, fact_issues = align_explicit_fact(problem_text, fact)
        issues.extend(fact_issues)
        if span is not None:
            spans[fact.fact_id] = span
    return EvidenceValidation(spans, tuple(issues))


__all__ = [
    "EvidenceValidation",
    "SourceSpan",
    "align_explicit_fact",
    "quote_occurrences",
    "validate_evidence",
]
