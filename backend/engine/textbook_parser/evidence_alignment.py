from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from engine.textbook_parser.contracts import ExplicitFact, TextbookProblemParseV1
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue


_NUMBER_PATTERN = (
    r"(?<![A-Za-z\d.^])[+−-]?(?:\d+(?:\.\d+)?|\.\d+)"
    r"(?:[ \t]*/[ \t]*\d+(?:\.\d+)?|"
    r"(?:[ \t]*[eE][ \t]*[+−-]?[ \t]*\d+)|"
    r"(?:[ \t]*[×x][ \t]*10[ \t]*(?:\^[ \t]*[+−-]?[ \t]*\d+|[⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)))?"
    r"(?![\d.])"
)
_NUMBER_RE = re.compile(_NUMBER_PATTERN)

_UNIT_ALIASES = {
    "": "dimensionless",
    "1": "dimensionless",
    "%": "dimensionless",
    "m": "length",
    "cm": "length",
    "mm": "length",
    "km": "length",
    "미터": "length",
    "s": "time",
    "sec": "time",
    "초": "time",
    "min": "time",
    "분": "time",
    "h": "time",
    "시간": "time",
    "m/s": "velocity",
    "m·s^-1": "velocity",
    "m*s^-1": "velocity",
    "km/h": "velocity",
    "m/s^2": "acceleration",
    "m/s2": "acceleration",
    "m/s²": "acceleration",
    "m·s^-2": "acceleration",
    "m*s^-2": "acceleration",
    "kg": "mass",
    "g": "mass",
    "n": "force",
    "kn": "force",
    "deg": "angle",
    "도": "angle",
    "°": "angle",
    "rad": "angle",
    "rad/s": "angular_velocity",
    "rpm": "angular_velocity",
    "rad/s^2": "angular_acceleration",
    "rad/s2": "angular_acceleration",
    "rad/s²": "angular_acceleration",
    "hz": "frequency",
    "j": "energy",
    "n*m": "energy_or_torque",
    "n·m": "energy_or_torque",
    "n*s": "impulse",
    "n·s": "impulse",
    "n/m": "spring_constant",
    "kg*m^2": "moment_of_inertia",
    "kg*m2": "moment_of_inertia",
    "kg·m^2": "moment_of_inertia",
    "kg·m²": "moment_of_inertia",
    "kg·m2": "moment_of_inertia",
}

_SEMANTIC_DIMENSIONS = {
    "acceleration": {"acceleration"},
    "angular_acceleration": {"angular_acceleration"},
    "angular_velocity": {"angular_velocity"},
    "angle": {"angle"},
    "coefficient_of_friction": {"dimensionless"},
    "displacement": {"length"},
    "distance": {"length"},
    "background_height": {"length"},
    "height": {"length"},
    "radius": {"length"},
    "duration": {"time"},
    "period": {"time"},
    "time": {"time"},
    "initial_velocity": {"velocity"},
    "final_velocity": {"velocity"},
    "velocity": {"velocity"},
    "velocity_before": {"velocity"},
    "velocity_after": {"velocity"},
    "mass": {"mass"},
    "mass_1": {"mass"},
    "mass_2": {"mass"},
    "force": {"force"},
    "frequency": {"frequency"},
    "work": {"energy", "energy_or_torque"},
    "energy": {"energy", "energy_or_torque"},
    "torque": {"energy_or_torque"},
    "impulse": {"impulse"},
    "spring_constant": {"spring_constant"},
    "moment_of_inertia": {"moment_of_inertia"},
    "restitution_coefficient": {"dimensionless"},
}

_SOURCE_UNIT_TOKENS = tuple(
    sorted(
        {
            "%", "1", "kg*m^2", "kg*m2", "kg·m^2", "kg·m²", "kg·m2",
            "m/s^2", "m/s2", "m/s²", "m·s^-2", "m*s^-2", "rad/s^2",
            "rad/s2", "rad/s²", "m/s", "m·s^-1", "m*s^-1", "km/h",
            "rad/s", "n*m", "n·m", "n*s", "n·s", "n/m", "rpm", "hz",
            "kn", "kg", "km", "cm", "mm", "sec", "min", "rad", "deg",
            "미터", "시간", "초", "분", "도", "m", "s", "h", "g", "n", "j", "°",
        },
        key=lambda item: (-len(item), item),
    )
)
_UNIT_AFTER_NUMBER_RE = re.compile(
    r"^[ \t]*(?P<unit>" + "|".join(re.escape(item) for item in _SOURCE_UNIT_TOKENS) + r")"
    r"(?![A-Za-z/^*·²³⁰¹⁴⁵⁶⁷⁸⁹])",
    flags=re.IGNORECASE,
)
_SUPERSCRIPT_TRANSLATION = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    quote: str

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "quote": self.quote}


@dataclass(frozen=True)
class SourceQuantity:
    start: int
    end: int
    raw_value: str
    raw_unit: str


@dataclass(frozen=True)
class EvidenceValidation:
    fact_spans: dict[str, SourceSpan]
    issues: tuple[ValidationIssue, ...]


def _normalized_number(value: str) -> str:
    compact = value.translate(_SUPERSCRIPT_TRANSLATION)
    compact = unicodedata.normalize("NFKC", compact).replace("−", "-")
    compact = re.sub(r"\s+", "", compact)
    scientific = re.fullmatch(
        r"(?P<mantissa>[+-]?(?:\d+(?:\.\d+)?|\.\d+))[×x]10\^?(?P<exponent>[+-]?\d+)",
        compact,
        flags=re.IGNORECASE,
    )
    if scientific:
        return f"{scientific.group('mantissa')}e{scientific.group('exponent')}"
    return re.sub(r"E", "e", compact)


def _normalized_unit(unit: str) -> str:
    compact = unicodedata.normalize("NFKC", unit).replace(" ", "").lower()
    return compact.replace("^2", "2").replace("^3", "3")


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
    return [_normalized_number(match.group(0)) for match in _NUMBER_RE.finditer(text)]


def quantity_occurrences(quote: str) -> list[SourceQuantity]:
    """Parse adjacent value-unit grammar spans; naked numbers are dimensionless."""

    out: list[SourceQuantity] = []
    for match in _NUMBER_RE.finditer(quote):
        unit_match = _UNIT_AFTER_NUMBER_RE.match(quote[match.end():])
        if unit_match is None:
            out.append(SourceQuantity(match.start(), match.end(), match.group(0), ""))
            continue
        unit = unit_match.group("unit")
        out.append(
            SourceQuantity(
                match.start(),
                match.end() + unit_match.end(),
                match.group(0),
                unit,
            )
        )
    return out


def _unit_occurs(quote: str, unit: str) -> bool:
    if not unit:
        return True
    normalized_quote = unicodedata.normalize("NFKC", quote).replace(" ", "")
    normalized_unit = unicodedata.normalize("NFKC", unit).replace(" ", "")
    normalized_quote = normalized_quote.replace("^2", "2").replace("^3", "3")
    normalized_unit = normalized_unit.replace("^2", "2").replace("^3", "3")
    # Unit symbols must match as a complete expression. In particular `m`
    # cannot be accepted from `m/s`, and `s` cannot be accepted from `m/s`.
    unit_chars = r"A-Za-z/^*·²³"
    return re.search(
        rf"(?<![{unit_chars}]){re.escape(normalized_unit)}(?![{unit_chars}])",
        normalized_quote,
        flags=re.IGNORECASE,
    ) is not None


def _unit_dimension(unit: str) -> str | None:
    return _UNIT_ALIASES.get(_normalized_unit(unit))


def _dimension_matches(fact: ExplicitFact) -> bool:
    expected = _SEMANTIC_DIMENSIONS.get(fact.semantic_key)
    if expected is None:
        return True
    actual = _unit_dimension(fact.raw_unit)
    return actual in expected


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
    raw_number = _normalized_number(fact.raw_value)
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
    if not _dimension_matches(fact):
        issues.append(
            ValidationIssue(
                ErrorCode.raw_unit_mismatch,
                Severity.critical,
                "raw_unit is dimensionally incompatible with semantic_key",
                path=f"explicit_facts.{fact.fact_id}.raw_unit",
                referenced_id=fact.fact_id,
                metadata={
                    "semantic_key": fact.semantic_key,
                    "raw_unit": fact.raw_unit,
                },
            )
        )

    matching_quantities = [
        item
        for item in quantity_occurrences(fact.evidence_quote)
        if _normalized_number(item.raw_value) == raw_number
        and _normalized_unit(item.raw_unit) == _normalized_unit(fact.raw_unit)
    ]
    if not matching_quantities:
        issues.append(
            ValidationIssue(
                ErrorCode.quantity_span_mismatch,
                Severity.critical,
                "raw_value and raw_unit are not one source quantity expression",
                path=f"explicit_facts.{fact.fact_id}",
                referenced_id=fact.fact_id,
            )
        )
        return None, issues
    if fact.quantity_occurrence_index >= len(matching_quantities):
        issues.append(
            ValidationIssue(
                ErrorCode.quantity_span_mismatch,
                Severity.critical,
                "quantity_occurrence_index does not identify a matching source quantity",
                path=f"explicit_facts.{fact.fact_id}.quantity_occurrence_index",
                referenced_id=fact.fact_id,
                metadata={"quantity_occurrence_count": len(matching_quantities)},
            )
        )
        return None, issues
    quote_span = occurrences[fact.occurrence_index]
    quantity = matching_quantities[fact.quantity_occurrence_index]
    start = quote_span.start + quantity.start
    end = quote_span.start + quantity.end
    return SourceSpan(start, end, problem_text[start:end]), issues


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
    claimed_quantity_spans: dict[tuple[int, int], str] = {}
    for fact in parse.explicit_facts:
        span, fact_issues = align_explicit_fact(problem_text, fact)
        issues.extend(fact_issues)
        if span is not None:
            key = (span.start, span.end)
            previous = claimed_quantity_spans.get(key)
            if previous is not None:
                issues.append(
                    ValidationIssue(
                        ErrorCode.quantity_occurrence_reused,
                        Severity.critical,
                        "one source quantity occurrence cannot ground multiple explicit facts",
                        path=f"explicit_facts.{fact.fact_id}",
                        referenced_id=fact.fact_id,
                        metadata={"fact_ids": [previous, fact.fact_id], "source_span": list(key)},
                    )
                )
            else:
                claimed_quantity_spans[key] = fact.fact_id
            spans[fact.fact_id] = span
    return EvidenceValidation(spans, tuple(issues))


__all__ = [
    "EvidenceValidation",
    "SourceSpan",
    "align_explicit_fact",
    "quantity_occurrences",
    "quote_occurrences",
    "validate_evidence",
]
