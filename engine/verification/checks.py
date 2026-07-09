from engine.models import CanonicalProblem, VerificationReport


def require_no_missing(c: CanonicalProblem) -> VerificationReport:
    if c.missing_info:
        return VerificationReport(
            passed=False,
            errors=["필수 조건 부족: " + ", ".join(c.missing_info)],
            warnings=[],
            checks=[],
        )
    return VerificationReport(passed=True)


def merge_reports(*reports: VerificationReport) -> VerificationReport:
    out = VerificationReport(passed=True)
    summaries = []
    for r in reports:
        out.passed = out.passed and r.passed
        out.checks.extend(r.checks)
        out.warnings.extend(r.warnings)
        out.errors.extend(r.errors)
        if getattr(r, "dimension_summary", None):
            summaries.append(r.dimension_summary)
    if summaries:
        out.dimension_summary = " / ".join(summaries)
    return out
