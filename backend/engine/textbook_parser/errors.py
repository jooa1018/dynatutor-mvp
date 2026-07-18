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
    answer_authority_field = "answer_authority_field"
    evidence_quote_missing = "evidence_quote_missing"
    evidence_occurrence_missing = "evidence_occurrence_missing"
    invented_explicit_number = "invented_explicit_number"
    raw_value_mismatch = "raw_value_mismatch"
    raw_unit_mismatch = "raw_unit_mismatch"
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


class TextbookParserError(RuntimeError):
    code = ErrorCode.parser_error


class ParserUnavailableError(TextbookParserError):
    code = ErrorCode.parser_unavailable


class ParserRefusalError(TextbookParserError):
    code = ErrorCode.parser_refusal


class ParserBudgetError(TextbookParserError):
    code = ErrorCode.parser_budget_exceeded


__all__ = [
    "ErrorCode",
    "ParserBudgetError",
    "ParserRefusalError",
    "ParserUnavailableError",
    "Severity",
    "TextbookParserError",
    "ValidationIssue",
]
