"""Capability-driven Phase 48 verification-suite orchestrator.

The public ``verify_result`` contract remains compatible with the legacy
string report while every emitted decision is also represented as a typed,
applicability-aware ``VerificationCheck`` tied to the versioned tolerance
policy.  A solver ID is authoritative when provided; direct service/tests may
omit it and fall back deterministically to the canonical family/subtype.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from engine.capabilities.loader import (
    CORE_VALIDATOR_IDS,
    INVARIANT_VALIDATOR_IDS,
    load_capability_matrix,
)
from engine.models import CanonicalProblem, SolverResult, VerificationReport
from engine.verification.checks import (
    ensure_structured_checks,
    record_verification_check,
)
from engine.verification.conditioning import (
    diagnose_boundary_proximity,
    diagnose_near_cancellation,
    diagnose_tolerance_sensitivity,
)
from engine.verification.dimensions import check_answer_dimension
from engine.verification.invariants import (
    INVARIANT_EVALUATORS,
    evaluate_invariants,
)
from engine.verification.plausibility import check_knowns, check_pool
from engine.verification.policy import (
    DEFAULT_TOLERANCE_POLICY,
    TolerancePolicy,
)
from engine.verification.provenance import analyze as analyze_provenance
from engine.verification.residuals import RELEVANT_KNOWNS
from engine.verification.types import (
    CheckApplicability,
    CheckStatus,
    VerificationCheck,
)


# Representative answer display labels used by the compatibility pool.
_KOREAN_LABEL_TO_SYMBOL = {
    "최종속도": "vf",
    "나중속도": "vf",
    "이동거리": "s",
    "변위": "s",
    "수평거리": "R",
    "시간": "t",
    "최대높이": "H",
    "주기": "T",
    "가속도": "a",
    "충격량": "J",
}

_GREEK = {"α": "alpha", "ω": "omega", "τ": "tau", "θ": "theta", "μ": "mu"}


def _rep_symbol(display: str | None) -> str | None:
    """Extract a legacy symbol from a representative answer display."""
    if not display:
        return None
    head = display.split("=", 1)[0].strip().strip("|").strip()
    for greek, name in _GREEK.items():
        head = head.replace(greek, name)
    match = re.search(r"([A-Za-z][A-Za-z_\']*)\s*$", head)
    if match:
        return match.group(1)
    compact = head.replace(" ", "")
    for label, symbol in _KOREAN_LABEL_TO_SYMBOL.items():
        if label in compact:
            return symbol
    return None


def build_answer_pool(
    result: SolverResult,
) -> tuple[dict[str, float], list[tuple[str | None, str | None, str]]]:
    """Build the legacy symbol pool without changing Phase 47 precedence.

    Semantic invariants consume ``AnswerItem.output_key`` directly.  This pool
    intentionally remains symbol-based for existing residual adapters.
    """
    pool: dict[str, float] = {}
    units: list[tuple[str | None, str | None, str]] = []
    for answer in result.answers or []:
        if answer.symbol and answer.numeric is not None and answer.symbol not in pool:
            pool[answer.symbol] = float(answer.numeric)
        units.append((answer.symbol, answer.unit, answer.label or ""))
    representative = result.answer
    if representative is not None and representative.numeric is not None:
        symbol = _rep_symbol(representative.display)
        if symbol and symbol not in pool:
            pool[symbol] = float(representative.numeric)
        if symbol is not None or not result.answers:
            units.append((symbol, representative.unit, representative.display or ""))
    return pool, units


def _new_report(policy: TolerancePolicy) -> VerificationReport:
    report = VerificationReport(passed=True)
    # Assignment keeps the draft compatible with an older in-memory model
    # while the Phase 48 model adds this as a declared dataclass field.
    report.policy_version = policy.policy_version
    if not hasattr(report, "structured_checks"):
        report.structured_checks = []
    return report


def _record_message(
    report: VerificationReport,
    *,
    check_id: str,
    category: str,
    status: CheckStatus,
    message: str,
    applicability: CheckApplicability = CheckApplicability.APPLICABLE,
    observed: Any = None,
    expected: Any = None,
    absolute_error: float | None = None,
    relative_error: float | None = None,
    tolerance: float | None = None,
    evidence: list[str] | None = None,
    source_equation_ids: list[str] | None = None,
) -> None:
    record_verification_check(
        report,
        VerificationCheck(
            check_id=check_id,
            category=category,
            status=status,
            applicability=applicability,
            observed=observed,
            expected=expected,
            absolute_error=absolute_error,
            relative_error=relative_error,
            tolerance=tolerance,
            message=message,
            evidence=list(evidence or []),
            source_equation_ids=list(source_equation_ids or []),
            metadata={"policy_version": report.policy_version},
        ),
    )


def _capability_for_problem(
    canonical: CanonicalProblem,
    solver_id: str | None,
) -> Mapping[str, Any] | None:
    matrix = load_capability_matrix()
    if solver_id is not None:
        return matrix.for_solver(solver_id)

    resolver = getattr(matrix, "for_problem", None)
    if callable(resolver):
        return resolver(canonical.system_type, canonical.subtype)

    # Compatibility with an older loader draft: exact subtype entries beat
    # generic entries; analytic-solver order makes a tie deterministic.
    matching = [
        entry
        for entry in matrix.capabilities
        if entry.get("system_type") == canonical.system_type
    ]
    if canonical.subtype:
        exact = [
            entry
            for entry in matching
            if canonical.subtype in (entry.get("subtypes") or [])
        ]
        if exact:
            matching = exact
        else:
            generic = [entry for entry in matching if not entry.get("subtypes")]
            if generic:
                matching = generic
    if not matching:
        return None
    return sorted(matching, key=lambda item: str(item.get("analytic_solver", "")))[0]


def _validator_ids(
    canonical: CanonicalProblem,
    solver_id: str | None,
) -> tuple[set[str], bool]:
    capability = _capability_for_problem(canonical, solver_id)
    if capability is None:
        # Direct calls for an unknown family retain the historical diagnostic
        # behavior, but a named missing solver is a broken internal contract.
        return set(CORE_VALIDATOR_IDS) | {"equation_residual"}, False
    return set(capability.get("validators") or []), True


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _typed_invariant_check(
    canonical: CanonicalProblem,
    raw: Any,
    *,
    policy: TolerancePolicy,
    engine_id: str | None,
) -> VerificationCheck:
    raw_status = _status_value(getattr(raw, "status", "error"))
    try:
        status = CheckStatus(raw_status)
    except ValueError:
        status = CheckStatus.ERROR

    category = str(
        getattr(raw, "category", None)
        or getattr(raw, "validator_id", None)
        or "invariant"
    )
    raw_applicability = getattr(raw, "applicability", None)
    if raw_applicability is not None:
        try:
            applicability = CheckApplicability(_status_value(raw_applicability))
        except ValueError:
            applicability = CheckApplicability.UNDETERMINED
    elif status is CheckStatus.NOT_APPLICABLE:
        applicability = CheckApplicability.NOT_APPLICABLE
    elif status in {CheckStatus.INCONCLUSIVE, CheckStatus.SKIPPED}:
        applicability = CheckApplicability.UNDETERMINED
    else:
        applicability = CheckApplicability.APPLICABLE

    message = str(getattr(raw, "message", category))
    if category == "equation_residual":
        if status is CheckStatus.NOT_APPLICABLE:
            message = (
                f"역대입 검산: '{canonical.system_type}' 유형은 아직 미지원 "
                "(검증 커버리지 밖)"
            )
        elif status is CheckStatus.INCONCLUSIVE:
            message = "역대입 검산: 필요한 값이 부족해 생략"
        elif not message.startswith("역대입:"):
            icon = "✓" if status in {CheckStatus.PASSED, CheckStatus.PASSED_WITH_WARNING} else "✗"
            absolute_error = getattr(raw, "absolute_error", None)
            detail = "" if absolute_error is None else f" |r|={absolute_error:.3g}"
            message = f"역대입: {message}{detail} {icon}"

    return VerificationCheck(
        check_id=str(getattr(raw, "check_id", f"{category}:unknown")),
        category=category,
        status=status,
        applicability=applicability,
        observed=getattr(raw, "observed", None),
        expected=getattr(raw, "expected", None),
        absolute_error=getattr(raw, "absolute_error", None),
        relative_error=getattr(raw, "relative_error", None),
        tolerance=getattr(raw, "tolerance", None),
        message=message,
        evidence=list(getattr(raw, "evidence", ()) or ()),
        source_equation_ids=list(
            getattr(raw, "source_equation_ids", ()) or ()
        ),
        metadata={
            "policy_version": policy.policy_version,
            **(
                {"engine_id": engine_id}
                if engine_id is not None
                else {}
            ),
            **dict(getattr(raw, "metadata", {}) or {}),
        },
    )


def _residual_scale(check: VerificationCheck) -> float:
    """Recover a stable scale for the non-blocking sensitivity diagnostic."""
    metadata = dict(getattr(check, "metadata", {}) or {})
    supplied = metadata.get("scale")
    if isinstance(supplied, (int, float)) and math.isfinite(float(supplied)):
        return max(abs(float(supplied)), 1.0)
    absolute_error = check.absolute_error
    relative_error = check.relative_error
    if (
        isinstance(absolute_error, (int, float))
        and isinstance(relative_error, (int, float))
        and math.isfinite(float(absolute_error))
        and math.isfinite(float(relative_error))
        and float(relative_error) > 0
    ):
        return max(abs(float(absolute_error) / float(relative_error)), 1.0)
    return 1.0



def _record_selection_diagnostics(
    report: VerificationReport,
    result: SolverResult,
) -> None:
    decision = getattr(result, "selection_decision", None)
    if decision is None:
        return
    for index, payload in enumerate(getattr(decision, "diagnostics", []) or []):
        if not isinstance(payload, Mapping):
            _record_message(
                report,
                check_id=f"selection:diagnostic:{index}",
                category="conditioning",
                status=CheckStatus.INCONCLUSIVE,
                applicability=CheckApplicability.UNDETERMINED,
                message="candidate-selection diagnostic has an invalid payload",
                observed=type(payload).__name__,
            )
            continue
        try:
            check = VerificationCheck(**dict(payload))
        except (KeyError, TypeError, ValueError) as exc:
            _record_message(
                report,
                check_id=f"selection:diagnostic:{index}",
                category="conditioning",
                status=CheckStatus.INCONCLUSIVE,
                applicability=CheckApplicability.UNDETERMINED,
                message=(
                    "candidate-selection diagnostic could not be decoded: "
                    f"{type(exc).__name__}"
                ),
                observed=dict(payload),
            )
            continue
        record_verification_check(report, check)

def verify_result(
    canonical: CanonicalProblem,
    result: SolverResult,
    solver_id: str | None = None,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> VerificationReport:
    """Run configured validators and return legacy plus typed evidence."""
    report = _new_report(policy)
    if not result.ok:
        _record_message(
            report,
            check_id="suite:unresolved",
            category="suite",
            status=CheckStatus.SKIPPED,
            applicability=CheckApplicability.NOT_APPLICABLE,
            message="검증 스위트: 미해결 결과 — 생략",
        )
        return ensure_structured_checks(report, prefix="suite")

    _record_selection_diagnostics(report, result)
    validators, capability_found = _validator_ids(canonical, solver_id)
    if not capability_found:
        status = CheckStatus.FAILED if solver_id is not None else CheckStatus.PASSED_WITH_WARNING
        _record_message(
            report,
            check_id="capability:missing",
            category="capability",
            status=status,
            applicability=CheckApplicability.UNDETERMINED,
            message=(
                f"capability contract not found for solver {solver_id}"
                if solver_id is not None
                else f"capability contract not found for {canonical.system_type}"
            ),
            evidence=[canonical.system_type, canonical.subtype or ""],
        )

    pool, units = build_answer_pool(result)

    if "dimension" in validators:
        seen: set[tuple[str | None, str | None]] = set()
        for index, (symbol, unit, label) in enumerate(units):
            key = (symbol, unit)
            if key in seen:
                continue
            seen.add(key)
            issue, passed_description = check_answer_dimension(
                symbol,
                unit,
                label,
                system_type=canonical.system_type,
            )
            if issue is not None:
                _record_message(
                    report,
                    check_id=f"dimension:{index}",
                    category="dimension",
                    status=(
                        CheckStatus.FAILED
                        if issue.kind == "error"
                        else CheckStatus.PASSED_WITH_WARNING
                    ),
                    message=issue.message,
                    observed=unit,
                    evidence=[label] if label else [],
                )
            if passed_description:
                _record_message(
                    report,
                    check_id=f"dimension:{index}:passed",
                    category="dimension",
                    status=CheckStatus.PASSED,
                    message=passed_description,
                    observed=unit,
                    evidence=[label] if label else [],
                )

    if "plausibility" in validators:
        issues, passed_descriptions = check_pool(pool)
        for index, issue in enumerate(issues):
            _record_message(
                report,
                check_id=f"plausibility:answer:{index}",
                category="plausibility",
                status=(
                    CheckStatus.FAILED
                    if issue.kind == "error"
                    else CheckStatus.PASSED_WITH_WARNING
                ),
                message=issue.message,
            )
        for index, message in enumerate(passed_descriptions):
            _record_message(
                report,
                check_id=f"plausibility:answer:passed:{index}",
                category="plausibility",
                status=CheckStatus.PASSED,
                message=message,
            )
        for index, issue in enumerate(
            check_knowns(canonical.knowns, system_type=canonical.system_type)
        ):
            _record_message(
                report,
                check_id=f"plausibility:known:{index}",
                category="plausibility",
                status=(
                    CheckStatus.FAILED
                    if issue.kind == "error"
                    else CheckStatus.PASSED_WITH_WARNING
                ),
                message=issue.message,
            )

    suspicious = []
    if "provenance" in validators:
        provenance = analyze_provenance(canonical)
        suspicious = provenance.suspicious_entries
        for index, entry in enumerate(provenance.ambiguous_entries):
            _record_message(
                report,
                check_id=f"provenance:ambiguous:{index}",
                category="provenance",
                status=CheckStatus.PASSED_WITH_WARNING,
                message=(
                    f"출처 다의적: {entry.symbol} = {entry.value} — 동일 표기가 "
                    "물리·배경 문장에 모두 있어 출처 확정 불가"
                ),
                observed=entry.value,
                evidence=[entry.sentence.text] if entry.sentence else [],
            )
        relevant = RELEVANT_KNOWNS.get(canonical.system_type)
        for index, entry in enumerate(suspicious):
            message = (
                f"출처 의심: {entry.symbol} = {entry.value} ← "
                f"\"{entry.sentence.text}\" (비물리 문맥 문장에서 추출됨)"
            )
            unused = relevant is not None and entry.symbol not in relevant
            _record_message(
                report,
                check_id=f"provenance:suspicious:{index}",
                category="provenance",
                status=(
                    CheckStatus.PASSED_WITH_WARNING if unused else CheckStatus.FAILED
                ),
                message=message + (" — 이 유형의 계산에는 미사용" if unused else ""),
                observed=entry.value,
                evidence=[entry.sentence.text],
            )
        if not suspicious:
            located = sum(1 for entry in provenance.entries if entry.origin == "text")
            if located:
                _record_message(
                    report,
                    check_id="provenance:located",
                    category="provenance",
                    status=CheckStatus.PASSED,
                    message=f"출처: 텍스트 유래 knowns {located}개 모두 물리 문맥 문장 ✓",
                    observed=located,
                )

    invariant_ids = [
        validator_id
        for validator_id in validators
        if validator_id in INVARIANT_VALIDATOR_IDS
        and validator_id in INVARIANT_EVALUATORS
    ]
    if invariant_ids:
        invariant_checks = evaluate_invariants(
            canonical,
            result,
            validator_ids=invariant_ids,
            answer_pool=pool,
            policy=policy,
            engine_id=solver_id,
        )
        for raw in invariant_checks:
            check = _typed_invariant_check(
                canonical,
                raw,
                policy=policy,
                engine_id=solver_id,
            )
            record_verification_check(report, check)
            if (
                check.category == "equation_residual"
                and check.applicability is CheckApplicability.APPLICABLE
                and isinstance(check.observed, (int, float))
                and math.isfinite(float(check.observed))
            ):
                # This diagnostic describes how close the classification is to
                # the configured boundary.  Its status is informational or
                # warning-only and must never reject an otherwise valid result.
                sensitivity = diagnose_tolerance_sensitivity(
                    float(check.observed),
                    scale=_residual_scale(check),
                    category="residual",
                    policy=policy,
                    engine_id=solver_id,
                    check_id=f"{check.check_id}:sensitivity",
                    source_equation_ids=check.source_equation_ids,
                )
                record_verification_check(report, sensitivity)
                cancellation = diagnose_near_cancellation(
                    float(check.observed),
                    scale=_residual_scale(check),
                    policy=policy,
                    engine_id=solver_id,
                    check_id=f"{check.check_id}:cancellation",
                    source_equation_ids=check.source_equation_ids,
                )
                record_verification_check(report, cancellation)
            if check.category in {"contact_normal", "friction_regime"}:
                metadata = dict(check.metadata)
                boundary_kind = (
                    "contact"
                    if check.category == "contact_normal"
                    else "static_to_kinetic_friction"
                )
                boundary = diagnose_boundary_proximity(
                    metadata.get("boundary_value"),
                    metadata.get("boundary_limit"),
                    scale=metadata.get("boundary_scale", 1.0),
                    boundary_kind=boundary_kind,
                    applicable=(
                        False
                        if check.applicability
                        is CheckApplicability.NOT_APPLICABLE
                        else True
                    ),
                    policy=policy,
                    engine_id=solver_id,
                    check_id=f"{check.check_id}:boundary",
                    source_equation_ids=check.source_equation_ids,
                )
                record_verification_check(report, boundary)
            if (
                check.category == "equation_residual"
                and check.status in {CheckStatus.FAILED, CheckStatus.ERROR}
            ):
                for entry in suspicious:
                    _record_message(
                        report,
                        check_id=f"{check.check_id}:cause:{entry.symbol}",
                        category="provenance",
                        status=CheckStatus.FAILED,
                        message=f"  ↳ 원인 후보: {entry.symbol} ← \"{entry.sentence.text}\"",
                        observed=entry.value,
                        evidence=[entry.sentence.text],
                    )

    report.passed = not report.errors
    if report.errors:
        report.dimension_summary = "물리 검증 실패"
    return ensure_structured_checks(report, prefix="suite")


__all__ = ["build_answer_pool", "verify_result"]
