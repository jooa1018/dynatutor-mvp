from __future__ import annotations

from typing import Any

from engine.models import CanonicalProblem, VerificationReport
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY
from engine.verification.types import (
    CheckApplicability,
    CheckStatus,
    VerificationCheck,
)


def require_no_missing(c: CanonicalProblem) -> VerificationReport:
    if c.missing_info:
        return VerificationReport(
            passed=False,
            errors=["필수 조건 부족: " + ", ".join(c.missing_info)],
            warnings=[],
            checks=[],
            policy_version=DEFAULT_TOLERANCE_POLICY.policy_version,
        )
    return VerificationReport(
        passed=True,
        policy_version=DEFAULT_TOLERANCE_POLICY.policy_version,
    )


def _payload(check: VerificationCheck | dict[str, Any]) -> dict[str, Any]:
    if isinstance(check, VerificationCheck):
        return check.to_dict()
    return dict(check)


def record_verification_check(
    report: VerificationReport,
    check: VerificationCheck,
) -> None:
    report.structured_checks.append(check.to_dict())
    message = check.message
    if check.status in {CheckStatus.FAILED, CheckStatus.ERROR}:
        report.errors.append(message)
        report.passed = False
    elif check.status in {
        CheckStatus.PASSED_WITH_WARNING,
        CheckStatus.INCONCLUSIVE,
    }:
        report.warnings.append(message)
    else:
        report.checks.append(message)
    if report.policy_version is None:
        report.policy_version = DEFAULT_TOLERANCE_POLICY.policy_version


def ensure_structured_checks(
    report: VerificationReport,
    *,
    prefix: str = "verification",
) -> VerificationReport:
    if report.policy_version is None:
        report.policy_version = DEFAULT_TOLER)
            ),
        )
        record_verification_check(out, mismatch)
    if summaries:
        out.dimension_summary = " / ".join(summaries)
    out.passed = not out.errors
    return ensure_structured_checks(out, prefix="merge")


__all__ = [
    "ensure_structured_checks",
    "merge_reports",
    "record_verification_check",
    "require_no_missing",
]
