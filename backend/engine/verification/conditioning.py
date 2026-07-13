from __future__ import annotations

"""Non-blocking numerical conditioning and sensitivity diagnostics."""

import math
import sys
from typing import Any, Iterable, Sequence

from engine.verification.policy import (
    DEFAULT_TOLERANCE_POLICY,
    TolerancePolicy,
)
from engine.verification.types import (
    VerificationApplicability,
    VerificationCheck,
    VerificationStatus,
)


def _diagnostic(
    *,
    check_id: str,
    category: str,
    status: VerificationStatus,
    applicability: VerificationApplicability,
    message: str,
    observed: Any = None,
    expected: Any = None,
    absolute_error: float | None = None,
    relative_error: float | None = None,
    tolerance: float | None = None,
    evidence: Iterable[str] = (),
    source_equation_ids: Iterable[str] = (),
    metadata: dict[str, Any] | None = None,
) -> VerificationCheck:
    details = {"diagnostic_only": True}
    if metadata:
        details.update(metadata)
    return VerificationCheck(
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
        evidence=tuple(evidence),
        source_equation_ids=tuple(source_equation_ids),
        metadata=details,
    )


def diagnose_jacobian_condition(
    jacobian: Any,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    engine_id: str | None = None,
    check_id: str = "conditioning:jacobian",
    source_equation_ids: Sequence[str] = (),
) -> VerificationCheck:
    """Estimate Jacobian condition and rank without changing root selection."""

    effective = policy.for_engine(engine_id)
    threshold = effective.condition_warning_threshold
    if jacobian is None:
        return _diagnostic(
            check_id=check_id,
            category="conditioning",
            status=VerificationStatus.NOT_APPLICABLE,
            applicability=VerificationApplicability.NOT_APPLICABLE,
            message="no Jacobian was supplied for conditioning analysis",
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )
    try:
        import numpy as np
    except ImportError:
        return _diagnostic(
            check_id=check_id,
            category="conditioning",
            status=VerificationStatus.SKIPPED,
            applicability=VerificationApplicability.UNDETERMINED,
            message="NumPy is unavailable; Jacobian conditioning was skipped",
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )

    try:
        matrix = np.asarray(jacobian, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        return _diagnostic(
            check_id=check_id,
            category="conditioning",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="Jacobian entries are not a finite numeric matrix",
            observed=type(exc).__name__,
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )
    if matrix.ndim != 2 or matrix.size == 0 or not np.isfinite(matrix).all():
        return _diagnostic(
            check_id=check_id,
            category="conditioning",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="Jacobian must be a non-empty finite two-dimensional matrix",
            observed={"shape": list(matrix.shape), "finite": bool(np.isfinite(matrix).all())},
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )

    try:
        condition_number = float(np.linalg.cond(matrix))
        rank = int(np.linalg.matrix_rank(matrix))
    except (TypeError, ValueError, np.linalg.LinAlgError) as exc:
        return _diagnostic(
            check_id=check_id,
            category="conditioning",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="Jacobian condition number could not be evaluated",
            observed=type(exc).__name__,
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )

    ill_conditioned = (
        not math.isfinite(condition_number) or condition_number >= threshold
    )
    status = (
        VerificationStatus.PASSED_WITH_WARNING
        if ill_conditioned
        else VerificationStatus.PASSED
    )
    message = (
        "Jacobian is ill-conditioned; candidate roots may be numerically sensitive"
        if ill_conditioned
        else "Jacobian conditioning is within the configured warning threshold"
    )
    excess = (
        math.inf
        if not math.isfinite(condition_number)
        else max(condition_number - threshold, 0.0)
    )
    return _diagnostic(
        check_id=check_id,
        category="conditioning",
        status=status,
        applicability=VerificationApplicability.APPLICABLE,
        message=message,
        observed={
            "condition_number": condition_number,
            "rank": rank,
            "shape": list(matrix.shape),
        },
        expected={"condition_number_below": threshold},
        absolute_error=excess,
        tolerance=threshold,
        evidence=(f"rank={rank}", f"shape={tuple(matrix.shape)}"),
        source_equation_ids=source_equation_ids,
        metadata={"ill_conditioned": ill_conditioned},
    )


def diagnose_root_separation(
    roots: Sequence[Any] | None,
    *,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    engine_id: str | None = None,
    check_id: str = "conditioning:root_separation",
    source_equation_ids: Sequence[str] = (),
) -> VerificationCheck:
    """Warn when distinct candidate roots are numerically indistinguishable."""

    effective = policy.for_engine(engine_id)
    threshold = effective.root_separation_tol
    if roots is None or len(roots) < 2:
        return _diagnostic(
            check_id=check_id,
            category="root_separation",
            status=VerificationStatus.NOT_APPLICABLE,
            applicability=VerificationApplicability.NOT_APPLICABLE,
            message="at least two roots are required for separation analysis",
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )

    numeric_roots: list[complex] = []
    try:
        for root in roots:
            if isinstance(root, bool):
                raise TypeError("boolean root")
            value = complex(root)
            if not math.isfinite(value.real) or not math.isfinite(value.imag):
                raise ValueError("non-finite root")
            numeric_roots.append(value)
    except (TypeError, ValueError, OverflowError) as exc:
        return _diagnostic(
            check_id=check_id,
            category="root_separation",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="root separation requires finite numeric roots",
            observed=type(exc).__name__,
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )

    closest: tuple[int, int, float, float] | None = None
    for left_index in range(len(numeric_roots)):
        for right_index in range(left_index + 1, len(numeric_roots)):
            left = numeric_roots[left_index]
            right = numeric_roots[right_index]
            absolute = abs(left - right)
            normalized = absolute / max(abs(left), abs(right), 1.0)
            if closest is None or normalized < closest[3]:
                closest = (left_index, right_index, absolute, normalized)
    assert closest is not None
    left_index, right_index, absolute, normalized = closest
    close = normalized <= threshold
    return _diagnostic(
        check_id=check_id,
        category="root_separation",
        status=(
            VerificationStatus.PASSED_WITH_WARNING
            if close
            else VerificationStatus.PASSED
        ),
        applicability=VerificationApplicability.APPLICABLE,
        message=(
            "candidate roots are closer than the configured separation threshold"
            if close
            else "candidate roots are well separated"
        ),
        observed={
            "left_index": left_index,
            "right_index": right_index,
            "absolute_separation": absolute,
            "normalized_separation": normalized,
        },
        expected={"normalized_separation_above": threshold},
        absolute_error=max(threshold - normalized, 0.0),
        relative_error=normalized,
        tolerance=threshold,
        evidence=(f"root[{left_index}]", f"root[{right_index}]"),
        source_equation_ids=source_equation_ids,
        metadata={"close_roots": close},
    )


def diagnose_tolerance_sensitivity(
    residual: float | None,
    *,
    scale: float = 1.0,
    category: str = "residual",
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    engine_id: str | None = None,
    tightening_factor: float = 0.5,
    loosening_factor: float = 2.0,
    check_id: str = "conditioning:tolerance_sensitivity",
    source_equation_ids: Sequence[str] = (),
) -> VerificationCheck:
    """Report whether a residual lies dangerously close to a policy boundary."""

    try:
        numeric_residual = float(residual) if residual is not None else math.nan
        numeric_scale = abs(float(scale))
        tightening_factor = float(tightening_factor)
        loosening_factor = float(loosening_factor)
    except (TypeError, ValueError, OverflowError):
        numeric_residual = math.nan
        numeric_scale = math.nan
    if (
        not math.isfinite(numeric_residual)
        or not math.isfinite(numeric_scale)
        or numeric_scale < 0
    ):
        return _diagnostic(
            check_id=check_id,
            category="sensitivity",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="tolerance sensitivity requires a finite residual and scale",
            observed=residual,
            source_equation_ids=source_equation_ids,
        )
    if not (0 < tightening_factor < 1):
        raise ValueError("tightening_factor must be between zero and one")
    if loosening_factor <= 1:
        raise ValueError("loosening_factor must be greater than one")

    effective = policy.for_engine(engine_id)
    tolerance = effective.tolerance(category, scale=numeric_scale)
    absolute_error = abs(numeric_residual)
    tight_tolerance = tolerance * tightening_factor
    loose_tolerance = tolerance * loosening_factor
    distance = abs(absolute_error - tolerance)
    denominator = max(
        distance,
        sys.float_info.epsilon * max(tolerance, 1.0),
    )
    sensitivity_score = tolerance / denominator
    warning = sensitivity_score >= effective.sensitivity_warning_threshold
    return _diagnostic(
        check_id=check_id,
        category="sensitivity",
        status=(
            VerificationStatus.PASSED_WITH_WARNING
            if warning
            else VerificationStatus.PASSED
        ),
        applicability=VerificationApplicability.APPLICABLE,
        message=(
            "verification outcome is sensitive to a small tolerance change"
            if warning
            else "verification outcome is stable under tolerance perturbation"
        ),
        observed={
            "absolute_residual": absolute_error,
            "nominal_passed": absolute_error <= tolerance,
            "tightened_passed": absolute_error <= tight_tolerance,
            "loosened_passed": absolute_error <= loose_tolerance,
            "sensitivity_score": sensitivity_score,
        },
        expected={
            "sensitivity_score_below": effective.sensitivity_warning_threshold
        },
        absolute_error=max(
            sensitivity_score - effective.sensitivity_warning_threshold, 0.0
        ),
        relative_error=absolute_error / max(tolerance, 1.0),
        tolerance=tolerance,
        evidence=(
            f"tightening_factor={tightening_factor}",
            f"loosening_factor={loosening_factor}",
        ),
        source_equation_ids=source_equation_ids,
        metadata={
            "sensitivity_score": sensitivity_score,
            "warning_threshold": effective.sensitivity_warning_threshold,
        },
    )


check_jacobian_condition = diagnose_jacobian_condition
check_root_separation = diagnose_root_separation
check_tolerance_sensitivity = diagnose_tolerance_sensitivity


__all__ = [
    "check_jacobian_condition",
    "check_root_separation",
    "check_tolerance_sensitivity",
    "diagnose_jacobian_condition",
    "diagnose_root_separation",
    "diagnose_tolerance_sensitivity",
]
