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
    policy_version = DEFAULT_TOLERANCE_POLICY.policy_version
    if c.missing_info:
        return VerificationReport(
            passed=False,
            errors=["필수 조건 부족: " + ", ".join(c.missing_info)],
            policy_version=policy_version,
        )
    return VerificationReport(passed=True, policy_version=policy_version)


def _payload(check: VerificationCheck | dict[str, Any]) -> dict[str, Any]:
    return check.to_dict() if isinstance(check, VerificationCheck) else dict(check)


def record_verification_check(
    report: VerificationReport,
    check: VerificationCheck,
) -> None:
    report.structured_checks.append(check.to_dict())
    if check.status in {CheckStatus.FAILED, CheckStatus.ERROR}:
        report.errors.append(check.message)
        report.passed = False
    elif check.status in {
        CheckStatus.PASSED_WITH_WARNING,
        CheckStatus.INCONCLUSIVE,
    }:
        report.warnings.append(check.message)
    else:
        report.checks.append(check.message)
    if report.policy_version is None:
        report.policy_version = DEFAULT_TOLERANCE_POLICY.policy_version


def ensure_structured_checks(
    report: VerificationReport,
    *,
    prefix: str = "verification",
) -> VerificationReport:
    if report.policy_version is None:
        report.policy_version = DEFAULT_TOLERANCE_POLICY.policy_version
    existing = {
        str(_payload(item).get("message", ""))
        for item in report.structured_checks
    }
    groups = (
        ("checks", report.checks, CheckStatus.PASSED),
        ("warnings", report.warnings, CheckStatus.PASSED_WITH_WARNING),
        ("errors", report.errors, CheckStatus.FAILED),
    )
    for bucket, messages, status in groups:
        for index, message in enumerate(messages):
            if message in existing:
                continue
            compatibility = VerificationCheck(
                check_id=f"{prefix}:legacy:{bucket}:{index}",
                category="legacy_compatibility",
                status=status,
                applicability=CheckApplicability.UNDETERMINED,
                message=message,
                evidence=("legacy compatibility view",),
            )
            report.structured_checks.append(compatibility.to_dict())
            existing.add(message)
    report.passed = report.passed and not report.errors
    return report


def merge_reports(*reports: VerificationReport) -> VerificationReport:
    policy_version = DEFAULT_TOLERANCE_POLICY.policy_version
    out = VerificationReport(passed=True, policy_version=policy_version)
    summaries: list[str] = []
    versions: list[str] = []
    for report in reports:
        out.passed = out.passed and report.passed
        out.checks.extend(report.checks)
        out.warnings.extend(report.warnings)
        out.errors.extend(report.errors)
        out.structured_checks.extend(
            _payload(check)
            for check in getattr(report, "structured_checks", [])
        )
        if report.dimension_summary:
            summaries.append(report.dimension_summary)
        if report.policy_version:
            versions.append(str(report.policy_version))
    unique_versions = list(dict.fromkeys(versions))
    if len(unique_versions) == 1:
        out.policy_version = unique_versions[0]
    elif len(unique_versions) > 1:
        record_verification_check(
            out,
            VerificationCheck(
                check_id="policy:version_mismatch",
                category="policy",
                status=CheckStatus.ERROR,
                applicability=CheckApplicability.APPLICABLE,
                observed=unique_versions,
                expected="one shared policy version",
                message=(
                    "verification reports used different tolerance policy versions: "
                    + ", ".join(unique_versions)
                ),
            ),
        )
    if summaries:
        out.dimension_summary = " / ".join(summaries)
    out.passed = out.passed and not out.errors
    return ensure_structured_checks(out, prefix="merge")


__all__ = [
    "ensure_structured_checks",
    "merge_reports",
    "record_verification_check",
    "require_no_missing",
]
