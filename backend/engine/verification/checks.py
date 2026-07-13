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
    payload = check.to_dict()
    report.structured_checks.append(payload)
    message = check.message
    if check.status in {CheckStatus.FAILED, CheckStatus.ERROR}:
        report.errors.append(message)
    elif check.status in {
        CheckStatus.PASSED_WITH_WARNING,
        CheckStatus.INCONCLUSIVE,
    }:
        report.warnings.append(message)
    else:
        report.checks.append(message)
    report.passed = not report.errors
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
        str(item.get("message", ""))
        for item in map(_payload, report.structured_checks)
    }
    legacy_groups = (
        ("checks", report.checks, CheckStatus.PASSED),
        ("warnings", report.warnings, CheckStatus.PASSED_WITH_WARNING),
        ("errors", report.errors, CheckStatus.FAILED),
    )
    for bucket, messages, status in legacy_groups:
        for index, message in enumerate(messages):
  if message in existing:
      continue
  check = VerificationCheck(
      check_id=f"{prefix}:legacy:{bucket}:{index}",
      category="legacy_compatibility",
      status=status,
      applicability=CheckApplicability.UNDETERMINED,
      message=message,
      evidence=("legacy compatibility view",),
  )
  report.structured_checks.append(check.to_dict())
  existing.add(message)
    report.passed = not report.errors
    return report


def merge_reports(*reports: VerificationReport) -> VerificationReport:
    out = VerificationReport(
        passed=True,
        policy_version=DEFAULT_TOLERANCE_POLICY.policy_version,
    )
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
        if getattr(report, "dimension_summary", None):
  summaries.append(report.dimension_summary)
        if getattr(report, "policy_version", None):
  versions.append(str(report.policy_version))
    unique_versions = list(dict.fromkeys(versions))
    if len(unique_versions) == 1:
        out.policy_version = unique_versions[0]
    elif len(unique_versions) > 1:
        mismatch = VerificationCheck(
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
