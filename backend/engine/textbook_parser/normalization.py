from __future__ import annotations

import re
import unicodedata

from engine.textbook_parser.contracts import (
    TextbookProblemParseV2,
    TextbookProblemParseWireV2,
)
from engine.textbook_parser.errors import (
    ErrorCode,
    RepairIssueV1,
    Severity,
    ValidationIssue,
    repair_issue_from_validation,
)
from engine.textbook_parser.evidence_alignment import (
    quantity_occurrences,
    quote_occurrences,
)


NORMALIZATION_POLICY_VERSION = "model-wire-normalization-v2"


class WireNormalizationError(ValueError):
    def __init__(self, issues: tuple[RepairIssueV1, ...]) -> None:
        super().__init__("model-facing parse requires deterministic normalization repair")
        self.issues = issues


def _normalized_number(value: str) -> str:
    compact = unicodedata.normalize("NFKC", value).replace("−", "-")
    return re.sub(r"\s+", "", compact).lower()


def _normalized_unit(value: str) -> str:
    compact = unicodedata.normalize("NFKC", value).replace(" ", "").lower()
    return compact.replace("^2", "2").replace("^3", "3")


def normalize_wire_parse(
    problem_text: str,
    wire: TextbookProblemParseWireV2,
) -> TextbookProblemParseV2:
    payload = wire.model_dump(mode="python")
    issues: list[ValidationIssue] = []
    for index, (wire_fact, payload_fact) in enumerate(
        zip(wire.explicit_facts, payload["explicit_facts"], strict=True)
    ):
        quote_matches = quote_occurrences(problem_text, wire_fact.evidence_quote)
        if wire_fact.occurrence_index is None:
            if len(quote_matches) == 1:
                payload_fact["occurrence_index"] = 0
            else:
                issues.append(
                    ValidationIssue(
                        ErrorCode.evidence_occurrence_missing,
                        Severity.error,
                        "model omitted an ambiguous evidence occurrence",
                        path=f"explicit_facts.{index}.occurrence_index",
                        referenced_id=wire_fact.fact_id,
                        metadata={"occurrence_count": len(quote_matches)},
                    )
                )

        raw_number = _normalized_number(wire_fact.raw_value)
        raw_unit = _normalized_unit(wire_fact.raw_unit)
        matching_quantities = [
            item
            for item in quantity_occurrences(wire_fact.evidence_quote)
            if _normalized_number(item.raw_value) == raw_number
            and _normalized_unit(item.raw_unit) == raw_unit
        ]
        if wire_fact.quantity_occurrence_index is None:
            if len(matching_quantities) == 1:
                payload_fact["quantity_occurrence_index"] = 0
            else:
                code = (
                    ErrorCode.quantity_occurrence_missing
                    if matching_quantities
                    else ErrorCode.quantity_span_mismatch
                )
                issues.append(
                    ValidationIssue(
                        code,
                        Severity.error,
                        "model omitted an ambiguous source quantity occurrence",
                        path=f"explicit_facts.{index}.quantity_occurrence_index",
                        referenced_id=wire_fact.fact_id,
                        metadata={
                            "quantity_occurrence_count": len(matching_quantities)
                        },
                    )
                )

    if issues:
        raise WireNormalizationError(
            tuple(
                repair_issue_from_validation(item, phase="wire_normalization")
                for item in issues
            )
        )
    return TextbookProblemParseV2.model_validate(payload)


__all__ = [
    "NORMALIZATION_POLICY_VERSION",
    "WireNormalizationError",
    "normalize_wire_parse",
]
