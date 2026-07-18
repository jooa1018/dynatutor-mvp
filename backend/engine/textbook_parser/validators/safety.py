from __future__ import annotations

from typing import Any

from engine.textbook_parser.contracts import ANSWER_AUTHORITY_FORBIDDEN_FIELDS
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue


def validate_payload_authority(payload: Any) -> list[ValidationIssue]:
    """Reject model fields that could carry answer or verification authority."""

    issues: list[ValidationIssue] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if str(key).lower() in ANSWER_AUTHORITY_FORBIDDEN_FIELDS:
                    issues.append(
                        ValidationIssue(
                            ErrorCode.answer_authority_field,
                            Severity.critical,
                            "model payload contains a forbidden answer-authority field",
                            path=child_path,
                        )
                    )
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload, "")
    return issues


__all__ = ["validate_payload_authority"]
