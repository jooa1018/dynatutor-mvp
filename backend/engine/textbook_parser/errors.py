from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class ErrorCode(str, Enum):
    schema_error = "schema_error"
    invalid_enum = "invalid_enum"
    answer_authority_field = "answer_authority_field"
    evidence_quote_missing = "evidence_quote_missing"
    evidence_occurrence_missing = "evidence_occurrence_missing"
    quantity_occurrence_missing = "quantity_occurrence_missing"
    invented_explicit_number = "invented_explicit_number"
    raw_value_mismatch = "raw_value_mismatch"
    raw_unit_mismatch = "raw_unit_mismatch"
    quantity_span_mismatch = "quantity_span_mismatch"
    quantity_occurrence_reused = "quantity_occurrence_reused"
    invalid_reference = "invalid_reference"
    duplicate_id = "duplicate_id"
    contradictory_fact = "contradictory_fact"
    dangerous_assumption = "dangerous_assumption"
    figure_required = "figure_required"
    capability_missing = "capability_missing"
    unsupported_query = "unsupported_query"
    solver_not_textbook_safe = "solver_not_textbook_safe"
    candidate_tie = "candidate_tie"
    parser_refusal = "parser_refusal"
    parser_output_incomplete = "parser_output_incomplete"
    parser_length_finish = "parser_length_finish"
    parser_output_missing = "parser_output_missing"
    parser_api_status = "parser_api_status"
    parser_timeout = "parser_timeout"
    parser_rate_limited = "parser_rate_limited"
    parser_quota = "parser_quota"
    parser_auth = "parser_auth"
    parser_unavailable = "parser_unavailable"
    parser_budget_exceeded = "parser_budget_exceeded"
    parser_error = "parser_error"
    repair_failed = "repair_failed"
    cache_corrupt = "cache_corrupt"
    stale_approval = "stale_approval"
    candidate_binding_mismatch = "candidate_binding_mismatch"
    canonical_symbol_collision = "canonical_symbol_collision"
    motion_model_mismatch = "motion_model_mismatch"
    relation_binding_missing = "relation_binding_missing"
    temporal_binding_ambiguous = "temporal_binding_ambiguous"
    authoritative_patch_rejected = "authoritative_patch_rejected"


@dataclass(frozen=True)
class ValidationIssue:
    code: ErrorCode
    severity: Severity
    message: str
    path: str = ""
    referenced_id: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["code"] = self.code.value
        payload["severity"] = self.severity.value
        return payload


REPAIR_METADATA_KEYS = frozenset(
    {
        "missing_symbols",
        "expected_enum",
        "target_segment_id",
        "event_boundary_role",
        "occurrence_count",
        "quantity_occurrence_count",
        "subject_role",
    }
)


@dataclass(frozen=True)
class RepairIssueV1:
    phase: str
    code: str
    path: str
    error_type: str | None = None
    referenced_id: str | None = None
    reason_code: str | None = None
    allowed_metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "code": self.code,
            "path": self.path,
            "error_type": self.error_type,
            "referenced_id": self.referenced_id,
            "reason_code": self.reason_code,
            "allowed_metadata": self.allowed_metadata,
        }


def repair_issue_from_validation(
    issue: ValidationIssue, *, phase: str
) -> RepairIssueV1:
    metadata = dict(issue.metadata or {})
    if "missing_inputs" in metadata and "missing_symbols" not in metadata:
        metadata["missing_symbols"] = metadata.pop("missing_inputs")
    allowed = {
        key: value for key, value in metadata.items() if key in REPAIR_METADATA_KEYS
    }
    return RepairIssueV1(
        phase=phase,
        code=issue.code.value,
        path=issue.path,
        referenced_id=issue.referenced_id,
        reason_code=issue.code.value,
        allowed_metadata=allowed or None,
    )


class TextbookParserError(RuntimeError):
    code = ErrorCode.parser_error
    repairable = False
    request_id: str | None = None
    response_status: int | str | None = None
    incomplete_reason: str | None = None
    usage_summary: Any = None


class ParserUnavailableError(TextbookParserError):
    code = ErrorCode.parser_unavailable


class ParserRefusalError(TextbookParserError):
    code = ErrorCode.parser_refusal


class ParserIncompleteError(TextbookParserError):
    code = ErrorCode.parser_output_incomplete
    repairable = True


class ParserOutputMissingError(TextbookParserError):
    code = ErrorCode.parser_output_missing
    repairable = True


class ParserBudgetError(TextbookParserError):
    code = ErrorCode.parser_budget_exceeded


__all__ = [
    "ErrorCode",
    "ParserBudgetError",
    "ParserIncompleteError",
    "ParserOutputMissingError",
    "ParserRefusalError",
    "ParserUnavailableError",
    "REPAIR_METADATA_KEYS",
    "RepairIssueV1",
    "Severity",
    "TextbookParserError",
    "ValidationIssue",
    "repair_issue_from_validation",
]
