from __future__ import annotations

from fractions import Fraction

from engine.canonical.adapter import attach_canonical_v2
from engine.extraction.units import normalize_labeled_value
from engine.models import CanonicalProblem, Quantity
from engine.textbook_parser.assumption_policy import (
    AssumptionDisposition,
    AssumptionEvaluation,
)
from engine.textbook_parser.contracts import (
    AssumptionKind,
    EventKind,
    FactRelevance,
    TemporalRole,
)
from engine.textbook_parser.ontology import canonical_symbol
from engine.textbook_parser.validation import ValidatedParse


PROJECTION_VERSION = "textbook-canonical-projection-v2"


def _fact_symbol(fact) -> str | None:
    symbol = canonical_symbol(fact.semantic_key)
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


def _raw_number(value: str) -> float:
    compact = value.strip().replace("−", "-").replace(",", "").replace(" ", "")
    if "/" in compact:
        return float(Fraction(compact))
    return float(compact)


def _assumption_quantity(evaluation: AssumptionEvaluation) -> tuple[str, Quantity] | None:
    symbol = evaluation.resolved_symbol
    value = evaluation.resolved_value
    unit = evaluation.resolved_unit
    if symbol is None or value is None or unit is None:
        return None
    normalized_value, normalized_unit = normalize_labeled_value(_raw_number(value), unit or None)
    return (
        symbol,
        Quantity(
            symbol=symbol,
            value=normalized_value,
            unit=normalized_unit,
            source_text="검증된 가시적 가정",
            provenance_hint="domain_rule",
        ),
    )


def project_canonical(problem_text: str, validated: ValidatedParse) -> CanonicalProblem:
    if not validated.accepted or validated.selected_candidate is None:
        raise ValueError(f"cannot project non-accepted parse: {validated.status.value}")

    parse = validated.parse
    candidate = validated.selected_candidate
    fact_by_id = {item.fact_id: item for item in parse.explicit_facts}
    assumption_by_id = {item.assumption_id: item for item in parse.assumption_proposals}
    evaluation_by_id = {item.assumption_id: item for item in validated.assumptions}
    knowns: dict[str, Quantity] = {}
    flags: dict[str, bool] = {}
    assumption_labels: list[str] = []

    for fact_id in candidate.fact_ids:
        fact = fact_by_id[fact_id]
        if fact.relevance not in {FactRelevance.solver_input, FactRelevance.constraint}:
            continue
        symbol = _fact_symbol(fact)
        span = validated.evidence.fact_spans.get(fact.fact_id)
        if symbol is None or span is None:
            continue
        value, unit = normalize_labeled_value(_raw_number(fact.raw_value), fact.raw_unit or None)
        knowns[symbol] = Quantity(
            symbol=symbol,
            value=value,
            unit=unit,
            source_text=fact.evidence_quote,
            source_span=(span.start, span.end),
            matched_text=span.quote,
            provenance_hint="unit_normalization" if (value != _raw_number(fact.raw_value) or unit != (fact.raw_unit or None)) else None,
            subject_evidence={
                "binding_rule": "textbook_parse_v1",
                "resolved_subject_id": fact.subject_id,
                "segment_id": fact.segment_id,
                "event_id": fact.event_id,
                "fact_id": fact.fact_id,
            },
            normalization_evidence={
                "raw_value": fact.raw_value,
                "raw_unit": fact.raw_unit,
                "normalized_value": value,
                "normalized_unit": unit,
            },
        )

    for assumption_id in candidate.assumption_ids:
        evaluation = evaluation_by_id[assumption_id]
        if evaluation.disposition not in {
            AssumptionDisposition.accepted_default,
            AssumptionDisposition.accepted_visible,
        }:
            continue
        proposal = assumption_by_id[assumption_id]
        projected = _assumption_quantity(evaluation)
        if projected is not None:
            symbol, quantity = projected
            knowns.setdefault(symbol, quantity)
        if proposal.kind == AssumptionKind.starts_from_rest:
            flags["starts_from_rest"] = True
        if proposal.kind == AssumptionKind.ends_at_rest:
            flags["ends_at_rest"] = True
        assumption_labels.append(proposal.reason)

    queries = [
        item for item in parse.queries if item.query_id in candidate.query_ids
    ]
    event_by_id = {item.event_id: item for item in parse.events}
    event_selection: dict[str, str] = {}
    for query in queries:
        if query.event_id is not None:
            event = event_by_id[query.event_id]
            if event.kind in {EventKind.start, EventKind.release}:
                event_selection[query.output_key.value] = "first"
            elif event.kind in {EventKind.finish, EventKind.comes_to_rest}:
                event_selection[query.output_key.value] = "last"

    canonical = CanonicalProblem(
        system_type=candidate.system_type,
        subtype=candidate.subtype,
        language=parse.language,
        objects=[
            {
                "id": item.entity_id,
                "type": item.kind.value,
                "label": item.label,
                "aliases": list(item.aliases),
            }
            for item in parse.entities
        ],
        knowns=knowns,
        unknowns=[item.output_key.value for item in queries],
        flags=flags,
        assumptions=assumption_labels,
        confidence="높음",
        raw_text=problem_text,
        requested_outputs=[item.output_key.value for item in queries],
        textbook_parse={
            "source": "gpt_structured_outputs",
            "authoritative": True,
            "projection_version": PROJECTION_VERSION,
            "graph": parse.model_dump(mode="json"),
            "validation": validated.to_summary(),
            "event_selection": event_selection,
        },
    )
    attach_canonical_v2(canonical)
    return canonical


__all__ = ["PROJECTION_VERSION", "project_canonical"]
