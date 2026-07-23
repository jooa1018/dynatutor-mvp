from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class MechanicsIssueSeverity(str, Enum):
    warning = "warning"
    error = "error"
    critical = "critical"


class MechanicsIssueCode(str, Enum):
    schema_error = "schema_error"
    answer_authority_field = "answer_authority_field"
    duplicate_id = "duplicate_id"
    invalid_reference = "invalid_reference"
    evidence_quote_missing = "evidence_quote_missing"
    evidence_span_mismatch = "evidence_span_mismatch"
    evidence_occurrence_mismatch = "evidence_occurrence_mismatch"
    quantity_span_mismatch = "quantity_span_mismatch"
    quantity_occurrence_reused = "quantity_occurrence_reused"
    invented_explicit_number = "invented_explicit_number"
    raw_value_mismatch = "raw_value_mismatch"
    raw_unit_mismatch = "raw_unit_mismatch"
    provenance_violation = "provenance_violation"
    assumption_not_approved = "assumption_not_approved"
    figure_asset_missing = "figure_asset_missing"
    figure_asset_invalid = "figure_asset_invalid"
    figure_page_mismatch = "figure_page_mismatch"
    figure_region_invalid = "figure_region_invalid"
    figure_evidence_unconfirmed = "figure_evidence_unconfirmed"
    numeric_sequence_unconfirmed = "numeric_sequence_unconfirmed"
    symbol_quantity_mismatch = "symbol_quantity_mismatch"
    ast_unsupported = "ast_unsupported"
    ast_resource_limit = "ast_resource_limit"
    ast_symbol_missing = "ast_symbol_missing"
    ast_dimension_mismatch = "ast_dimension_mismatch"
    ast_shape_mismatch = "ast_shape_mismatch"
    unit_parse_error = "unit_parse_error"
    unit_dimension_mismatch = "unit_dimension_mismatch"
    non_finite_value = "non_finite_value"
    query_binding_invalid = "query_binding_invalid"
    interval_event_invalid = "interval_event_invalid"
    phase55_validation_required = "phase55_validation_required"


@dataclass(frozen=True)
class MechanicsValidationIssue:
    code: MechanicsIssueCode
    severity: MechanicsIssueSeverity
    message: str
    path: str = ""
    referenced_id: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["code"] = self.code.value
        payload["severity"] = self.severity.value
        return payload


__all__ = [
    "MechanicsIssueCode",
    "MechanicsIssueSeverity",
    "MechanicsValidationIssue",
]
