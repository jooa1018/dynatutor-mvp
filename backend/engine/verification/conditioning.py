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
    policy_version: str | None = None,
    engine_id: str | None = None,
) -> VerificationCheck:
    details = {"diagnostic_only": True}
    if policy_version is not None:
        details["policy_version"] = policy_version
    if engine_id is not None:
        details["engine_id"] = engine_id
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

    def emit(**kwargs: Any) -> VerificationCheck:
        return _diagnostic(
            policy_version=policy.policy_version,
            engine_id=engine_id,
            **kwargs,
        )

    effective = policy.for_engine(engine_id)
    threshold = effective.condition_warning_threshold
    if jacobian is None:
        return emit(
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
        return emit(
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
        return emit(
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
        return emit(
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
        return emit(
            check_id=check_id,
            category="conditioning",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="Jacobian condition number could not be evaluated",
            observed=type(exc).__name__,
            tolerance=threshold,
            source_equation_ids=source_equation_ids,
        )

    singular = rank < matrix.shape[1] or not math.isfinite(condition_number)
    near_singular = (
        not singular
        and math.isfinite(condition_number)
        and condition_number >= threshold
    )
    ill_conditioned = singular or near_singular
    status = (
        VerificationStatus.PASSED_WITH_WARNING
        if ill_conditioned
        else VerificationStatus.PASSED
    )
    message = (
        "Jacobian is singular; the local solution is not uniquely conditioned"
        if singular
        else (
            "Jacobian is near-singular or ill-conditioned; candidate roots may be numerically sensitive"
            if near_singular
            else "Jacobian conditioning is within the configured warning threshold"
        )
    )
    excess = (
        None
        if not math.isfinite(condition_number)
        else max(condition_number - threshold, 0.0)
    )
    return emit(
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
        metadata={
            "ill_conditioned": ill_conditioned,
            "singular": singular,
            "near_singular": near_singular,
        },
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

    def emit(**kwargs: Any) -> VerificationCheck:
        return _diagnostic(
            policy_version=policy.policy_version,
            engine_id=engine_id,
            **kwargs,
        )

    effective = policy.for_engine(engine_id)
    threshold = effective.root_separation_tol
    if roots is None or len(roots) < 2:
        return emit(
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
        return emit(
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
    return emit(
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

    def emit(**kwargs: Any) -> VerificationCheck:
        return _diagnostic(
            policy_version=policy.policy_version,
            engine_id=engine_id,
            **kwargs,
        )

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
        return emit(
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
    nominal_passed = absolute_error <= tolerance
    tightened_passed = absolute_error <= tight_tolerance
    loosened_passed = absolute_error <= loose_tolerance
    outcome_flip = (
        nominal_passed != tightened_passed
        or nominal_passed != loosened_passed
    )
    warning = (
        outcome_flip
        or sensitivity_score >= effective.sensitivity_warning_threshold
    )
    return emit(
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
            "nominal_passed": nominal_passed,
            "tightened_passed": tightened_passed,
            "loosened_passed": loosened_passed,
            "outcome_flip": outcome_flip,
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
            "outcome_flip": outcome_flip,
        },
    )



def diagnose_near_cancellation(
    residual: float | None,
    *,
    scale: float | None = None,
    signed_terms: Sequence[float] = (),
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    engine_id: str | None = None,
    check_id: str = "conditioning:near_cancellation",
    source_equation_ids: Sequence[str] = (),
) -> VerificationCheck:
    """Warn only from actual opposing signed equation terms."""

    effective = policy.for_engine(engine_id)
    try:
        numeric_residual = abs(float(residual)) if residual is not None else math.nan
        numeric_scale = abs(float(scale)) if scale is not None else math.nan
        finite_terms = [float(value) for value in signed_terms]
    except (TypeError, ValueError, OverflowError):
        numeric_residual = math.nan
        numeric_scale = math.nan
        finite_terms = []
    if (
        not math.isfinite(numeric_residual)
        or any(not math.isfinite(value) for value in finite_terms)
    ):
        return _diagnostic(
            check_id=check_id,
            category="cancellation",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="near-cancellation analysis requires finite residual evidence",
            observed={"residual": residual, "scale": scale},
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )

    has_positive = any(value > 0 for value in finite_terms)
    has_negative = any(value < 0 for value in finite_terms)
    if len(finite_terms) < 2 or not (has_positive and has_negative):
        return _diagnostic(
            check_id=check_id,
            category="cancellation",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message=(
                "signed opposing equation terms are unavailable; a residual "
                "scale proxy is not sufficient to claim cancellation"
            ),
            observed={
                "absolute_residual": numeric_residual,
                "scale_proxy": (
                    numeric_scale if math.isfinite(numeric_scale) else None
                ),
            },
            source_equation_ids=source_equation_ids,
            metadata={"scale_proxy_rejected": True},
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )

    positive_total = sum(value for value in finite_terms if value > 0)
    negative_total = abs(sum(value for value in finite_terms if value < 0))
    term_scale = positive_total + negative_total
    if term_scale <= effective.near_zero_tol:
        return _diagnostic(
            check_id=check_id,
            category="cancellation",
            status=VerificationStatus.NOT_APPLICABLE,
            applicability=VerificationApplicability.NOT_APPLICABLE,
            message="all signed equation terms are near zero",
            observed={
                "absolute_residual": numeric_residual,
                "term_scale": term_scale,
            },
            tolerance=effective.near_zero_tol,
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )

    denominator = max(
        numeric_residual,
        sys.float_info.epsilon * max(term_scale, 1.0),
    )
    cancellation_ratio = term_scale / denominator
    large_term_floor = 1.0 / max(
        effective.rel_tol,
        math.sqrt(sys.float_info.epsilon),
    )
    large_opposing_terms = term_scale >= large_term_floor
    warning = (
        large_opposing_terms
        and cancellation_ratio >= effective.condition_warning_threshold
    )
    return _diagnostic(
        check_id=check_id,
        category="cancellation",
        status=(
            VerificationStatus.PASSED_WITH_WARNING
            if warning
            else VerificationStatus.PASSED
        ),
        applicability=VerificationApplicability.APPLICABLE,
        message=(
            "large opposing equation terms nearly cancel; residual accuracy may lose significant digits"
            if warning
            else "signed equation terms do not show material near-cancellation risk"
        ),
        observed={
            "absolute_residual": numeric_residual,
            "positive_term_total": positive_total,
            "negative_term_total": negative_total,
            "term_scale": term_scale,
            "cancellation_ratio": cancellation_ratio,
        },
        expected={
            "cancellation_ratio_below": effective.condition_warning_threshold,
            "large_term_floor": large_term_floor,
        },
        absolute_error=max(
            cancellation_ratio - effective.condition_warning_threshold,
            0.0,
        ) if large_opposing_terms else 0.0,
        relative_error=numeric_residual / max(term_scale, 1.0),
        tolerance=effective.condition_warning_threshold,
        evidence=("evaluated_signed_equation_terms",),
        source_equation_ids=source_equation_ids,
        metadata={
            "near_cancellation": warning,
            "large_opposing_terms": large_opposing_terms,
            "term_evidence_count": len(finite_terms),
        },
        policy_version=policy.policy_version,
        engine_id=engine_id,
    )


def diagnose_local_perturbation(
    jacobian: Any,
    *,
    solution_values: Sequence[Any] = (),
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    engine_id: str | None = None,
    check_id: str = "conditioning:local_perturbation",
    source_equation_ids: Sequence[str] = (),
) -> VerificationCheck:
    """Estimate local input-to-solution amplification from an actual Jacobian."""

    effective = policy.for_engine(engine_id)
    try:
        import numpy as np
    except ImportError:
        return _diagnostic(
            check_id=check_id,
            category="sensitivity",
            status=VerificationStatus.SKIPPED,
            applicability=VerificationApplicability.UNDETERMINED,
            message="NumPy is unavailable; local perturbation analysis was skipped",
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )
    try:
        matrix = np.asarray(jacobian, dtype=float)
        solution = np.asarray(list(solution_values), dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        return _diagnostic(
            check_id=check_id,
            category="sensitivity",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="local perturbation analysis requires a finite numeric Jacobian",
            observed=type(exc).__name__,
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )
    if (
        matrix.ndim != 2
        or matrix.size == 0
        or not np.isfinite(matrix).all()
        or (solution.size and not np.isfinite(solution).all())
    ):
        return _diagnostic(
            check_id=check_id,
            category="sensitivity",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="local perturbation inputs must be finite and dimensionally consistent",
            observed={"shape": list(matrix.shape), "solution_size": int(solution.size)},
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )
    if solution.size not in {0, matrix.shape[1]}:
        return _diagnostic(
            check_id=check_id,
            category="sensitivity",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="solution vector size does not match the Jacobian column count",
            observed={"shape": list(matrix.shape), "solution_size": int(solution.size)},
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )

    try:
        rank = int(np.linalg.matrix_rank(matrix))
        matrix_norm = float(np.linalg.norm(matrix, ord=np.inf))
        solution_norm = (
            float(np.linalg.norm(solution, ord=np.inf))
            if solution.size
            else 1.0
        )
        input_scale = max(matrix_norm * max(solution_norm, 1.0), 1.0)
        relative_input_change = math.sqrt(sys.float_info.epsilon)
        forcing = np.full(
            matrix.shape[0],
            relative_input_change * input_scale / math.sqrt(matrix.shape[0]),
        )
        delta, _, _, _ = np.linalg.lstsq(matrix, forcing, rcond=None)
        relative_output_change = float(np.linalg.norm(delta)) / max(
            solution_norm,
            1.0,
        )
        amplification = relative_output_change / relative_input_change
    except (TypeError, ValueError, np.linalg.LinAlgError) as exc:
        return _diagnostic(
            check_id=check_id,
            category="sensitivity",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message="local perturbation estimate could not be evaluated",
            observed=type(exc).__name__,
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )

    singular = rank < matrix.shape[1]
    if singular:
        amplification = math.inf
    warning = (
        singular
        or not math.isfinite(amplification)
        or amplification >= effective.sensitivity_warning_threshold
    )
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
            "a small local equation perturbation can cause a large solution change"
            if warning
            else "the local solution response is stable under a small perturbation"
        ),
        observed={
            "relative_input_change": relative_input_change,
            "relative_output_change": relative_output_change,
            "amplification": amplification,
            "rank": rank,
            "shape": list(matrix.shape),
        },
        expected={
            "amplification_below": effective.sensitivity_warning_threshold
        },
        absolute_error=(
            None
            if not math.isfinite(amplification)
            else max(
                amplification - effective.sensitivity_warning_threshold,
                0.0,
            )
        ),
        tolerance=effective.sensitivity_warning_threshold,
        evidence=("deterministic_linearized_rhs_perturbation",),
        source_equation_ids=source_equation_ids,
        metadata={"singular": singular, "local_perturbation": True},
        policy_version=policy.policy_version,
        engine_id=engine_id,
    )


def diagnose_boundary_proximity(
    value: float | None,
    boundary: float | None,
    *,
    scale: float = 1.0,
    boundary_kind: str,
    applicable: bool | None = True,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
    engine_id: str | None = None,
    check_id: str | None = None,
    source_equation_ids: Sequence[str] = (),
) -> VerificationCheck:
    """Record contact/friction regime proximity without changing the solution."""

    resolved_check_id = check_id or f"conditioning:{boundary_kind}_boundary"
    effective = policy.for_engine(engine_id)
    if applicable is False:
        return _diagnostic(
            check_id=resolved_check_id,
            category="boundary",
            status=VerificationStatus.NOT_APPLICABLE,
            applicability=VerificationApplicability.NOT_APPLICABLE,
            message=f"{boundary_kind} boundary is not part of this model",
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )
    try:
        numeric_value = float(value) if value is not None else math.nan
        numeric_boundary = float(boundary) if boundary is not None else math.nan
        numeric_scale = max(abs(float(scale)), 1.0)
    except (TypeError, ValueError, OverflowError):
        numeric_value = numeric_boundary = numeric_scale = math.nan
    if not all(
        math.isfinite(item)
        for item in (numeric_value, numeric_boundary, numeric_scale)
    ):
        return _diagnostic(
            check_id=resolved_check_id,
            category="boundary",
            status=VerificationStatus.INCONCLUSIVE,
            applicability=VerificationApplicability.UNDETERMINED,
            message=(
                f"{boundary_kind} applies, but the state needed to locate its "
                "transition boundary is unavailable"
            ),
            observed={"value": value, "boundary": boundary},
            source_equation_ids=source_equation_ids,
            policy_version=policy.policy_version,
            engine_id=engine_id,
        )

    tolerance = effective.tolerance("constraint", scale=numeric_scale)
    distance = abs(numeric_value - numeric_boundary)
    near_boundary = distance <= tolerance
    return _diagnostic(
        check_id=resolved_check_id,
        category="boundary",
        status=(
            VerificationStatus.PASSED_WITH_WARNING
            if near_boundary
            else VerificationStatus.PASSED
        ),
        applicability=VerificationApplicability.APPLICABLE,
        message=(
            f"state is near the {boundary_kind} transition boundary"
            if near_boundary
            else f"state is separated from the {boundary_kind} transition boundary"
        ),
        observed={
            "value": numeric_value,
            "boundary": numeric_boundary,
            "distance": distance,
        },
        expected={"distance_above": tolerance},
        absolute_error=max(tolerance - distance, 0.0),
        relative_error=distance / numeric_scale,
        tolerance=tolerance,
        evidence=(f"boundary_kind={boundary_kind}",),
        source_equation_ids=source_equation_ids,
        metadata={"near_boundary": near_boundary, "boundary_kind": boundary_kind},
        policy_version=policy.policy_version,
        engine_id=engine_id,
    )

check_boundary_proximity = diagnose_boundary_proximity
check_jacobian_condition = diagnose_jacobian_condition
check_local_perturbation = diagnose_local_perturbation
check_near_cancellation = diagnose_near_cancellation
check_root_separation = diagnose_root_separation
check_tolerance_sensitivity = diagnose_tolerance_sensitivity


__all__ = [
    "check_boundary_proximity",
    "check_jacobian_condition",
    "check_local_perturbation",
    "check_near_cancellation",
    "check_root_separation",
    "check_tolerance_sensitivity",
    "diagnose_boundary_proximity",
    "diagnose_jacobian_condition",
    "diagnose_local_perturbation",
    "diagnose_near_cancellation",
    "diagnose_root_separation",
    "diagnose_tolerance_sensitivity",
]
