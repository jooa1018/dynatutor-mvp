from __future__ import annotations

"""Typed candidate-solution validation used by analytic and numeric solvers.

The module deliberately receives explicit variable and model constraints.  It
never infers physical meaning from a symbol's spelling.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Iterable, Mapping

import sympy as sp

from engine.physics_core.answer_validators import OUTPUT_KEY_COMPATIBILITY


CandidatePredicate = Callable[["CandidateSolution"], bool]


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    return str(value)


@dataclass(frozen=True)
class VariableConstraint:
    symbol: Any
    real: bool = True
    finite: bool = True
    lower_bound: float | None = None
    upper_bound: float | None = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    allowed_interval: tuple[float | None, float | None] | None = None
    allowed_intervals: tuple[tuple[float | None, float | None], ...] = ()
    integer: bool = False
    predicate: Callable[[float, Mapping[Any, Any]], bool] | None = field(
        default=None, repr=False, compare=False
    )
    custom_predicate_id: str | None = None
    reason: str | None = None
    source: str | None = None

    @property
    def variable_id(self) -> str:
        return str(self.symbol)


@dataclass
class CandidateValidationCheck:
    check_id: str
    category: str
    status: str
    message: str
    observed: Any = None
    expected: Any = None
    absolute_error: float | None = None
    relative_error: float | None = None
    tolerance: float | None = None
    evidence: list[str] = field(default_factory=list)
    source_equation_ids: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status in {"passed", "passed_with_warning", "not_applicable"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "status": self.status,
            "message": self.message,
            "observed": _safe_value(self.observed),
            "expected": _safe_value(self.expected),
            "absolute_error": self.absolute_error,
            "relative_error": self.relative_error,
            "tolerance": self.tolerance,
            "evidence": list(self.evidence),
            "source_equation_ids": list(self.source_equation_ids),
        }


@dataclass
class CandidateSolution:
    candidate_id: str
    symbolic_mapping: dict[Any, Any]
    numerical_mapping: dict[str, float] = field(default_factory=dict)
    unresolved_symbols: list[str] = field(default_factory=list)
    domain_conditions: list[Any] = field(default_factory=list)
    branch_info: dict[str, Any] = field(default_factory=dict)
    approximation_method: str | None = None
    initial_guess: dict[str, float] = field(default_factory=dict)
    validation_checks: list[CandidateValidationCheck] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    rank_metadata: dict[str, Any] = field(default_factory=dict)
    denominator_conditions: list[Any] = field(default_factory=list)

    @property
    def mapping(self) -> dict[Any, Any]:
        return self.symbolic_mapping

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbolic_mapping": {
                str(key): str(value) for key, value in self.symbolic_mapping.items()
            },
            "numerical_mapping": _safe_value(self.numerical_mapping),
            "unresolved_symbols": list(self.unresolved_symbols),
            "domain_conditions": [str(condition) for condition in self.domain_conditions],
            "branch_information": _safe_value(self.branch_info),
            "approximation_method": self.approximation_method,
            "initial_guess": _safe_value(self.initial_guess),
            "validation_checks": [check.to_dict() for check in self.validation_checks],
            "rejection_reasons": list(self.rejection_reasons),
            "rank_metadata": _safe_value(self.rank_metadata),
        }


@dataclass
class ValidatedCandidate:
    candidate: CandidateSolution
    accepted: bool
    checks: list[CandidateValidationCheck] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = self.candidate.to_dict()
        payload.update(
            {
                "accepted": self.accepted,
                "checks": [check.to_dict() for check in self.checks],
                "rejection_reasons": list(self.rejection_reasons),
            }
        )
        return payload


@dataclass(frozen=True)
class ModelConstraint:
    constraint_id: str
    evaluator: Any
    tolerance: float | None = None
    message: str = ""
    category: str = "model_constraint"
    source_equation_ids: tuple[str, ...] = ()


@dataclass
class ValidationContext:
    equations: list[Any] = field(default_factory=list)
    substitutions: dict[Any, Any] = field(default_factory=dict)
    constraints: dict[Any, VariableConstraint] | list[VariableConstraint] = field(
        default_factory=dict
    )
    model_constraints: list[ModelConstraint] = field(default_factory=list)
    requested_outputs: list[str] = field(default_factory=list)
    requested_symbols: list[Any] = field(default_factory=list)
    event_predicate: CandidatePredicate | None = None
    event_description: str | None = None
    preferred_candidate_id: str | None = None
    numerical_tolerance: float = 1e-9
    relative_tolerance: float = 1e-7
    residual_tolerance: float | None = None
    selection_policy: str = "all-valid-candidates"
    policy_version: str = "candidate-policy-1"

    def variable_constraints(self) -> list[VariableConstraint]:
        if isinstance(self.constraints, dict):
            return list(self.constraints.values())
        return list(self.constraints)

    @property
    def tolerances(self) -> dict[str, float]:
        return {
            "absolute": self.numerical_tolerance,
            "relative": self.relative_tolerance,
            "residual": (
                self.residual_tolerance
                if self.residual_tolerance is not None
                else self.numerical_tolerance
            ),
        }


@dataclass
class SelectionDecision:
    status: str
    selected_candidate: CandidateSolution | None = None
    valid_alternatives: list[CandidateSolution] = field(default_factory=list)
    rejected_candidates: list[ValidatedCandidate] = field(default_factory=list)
    selection_policy: str = "all-valid-candidates"
    explanation: str = ""
    tolerances: dict[str, float] = field(default_factory=dict)
    policy_version: str = "candidate-policy-1"

    @property
    def alternatives(self) -> list[CandidateSolution]:
        return self.valid_alternatives

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "selected_candidate": (
                self.selected_candidate.to_dict() if self.selected_candidate else None
            ),
            "valid_alternatives": [
                candidate.to_dict() for candidate in self.valid_alternatives
            ],
            "rejected_candidates": [
                candidate.to_dict() for candidate in self.rejected_candidates
            ],
            "selection_policy": self.selection_policy,
            "explanation": self.explanation,
            "tolerances": dict(self.tolerances),
            "policy_version": self.policy_version,
        }


@dataclass
class CandidateSolveBatch:
    result: Any
    candidates: list[CandidateSolution]


def _numeric(expr: Any) -> tuple[float | None, str | None]:
    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        numeric = float(expr)
        return (
            (numeric, None)
            if math.isfinite(numeric)
            else (None, "non_finite")
        )
    try:
        value = sp.N(expr)
        if getattr(value, "free_symbols", set()):
            return None, "unresolved_symbol"
        complex_value = complex(value)
    except Exception:
        return None, "not_numeric"
    if abs(complex_value.imag) > 1e-10:
        return None, "complex"
    if not math.isfinite(complex_value.real):
        return None, "non_finite"
    return float(complex_value.real), None


def candidate_from_mapping(
    mapping: Mapping[Any, Any],
    *,
    substitutions: Mapping[Any, Any] | None = None,
    candidate_id: str | None = None,
    rank_metadata: Mapping[str, Any] | None = None,
    branch_info: Mapping[str, Any] | None = None,
    denominator_conditions: Iterable[Any] | None = None,
    domain_conditions: Iterable[Any] | None = None,
) -> CandidateSolution:
    substitutions = dict(substitutions or {})
    raw = dict(mapping)
    numerical: dict[str, float] = {}
    unresolved: set[str] = set()
    denominators: list[Any] = list(denominator_conditions or [])
    for symbol, expression in raw.items():
        if isinstance(expression, (int, float)) and not isinstance(expression, bool):
            numeric, error = _numeric(expression)
            if error is None and numeric is not None:
                numerical[str(symbol)] = numeric
            continue
        try:
            substituted = sp.sympify(expression).subs(substitutions)
            denominator = sp.denom(sp.together(substituted))
            if denominator != 1:
                denominators.append(denominator)
            if getattr(substituted, "free_symbols", set()):
                unresolved.update(str(item) for item in substituted.free_symbols)
            numeric, error = _numeric(substituted)
            if error is None and numeric is not None:
                numerical[str(symbol)] = numeric
        except Exception:
            unresolved.add(str(symbol))
    return CandidateSolution(
        candidate_id=candidate_id or "candidate-0",
        symbolic_mapping=raw,
        numerical_mapping=numerical,
        unresolved_symbols=sorted(unresolved),
        domain_conditions=list(domain_conditions or []),
        branch_info=dict(branch_info or {}),
        rank_metadata=dict(rank_metadata or {}),
        denominator_conditions=denominators,
    )


def candidate_from_solver_result(
    result: Any,
    *,
    candidate_id: str,
    requested_outputs: Iterable[str] = (),
) -> CandidateSolution:
    mapping: dict[str, Any] = {}
    output_keys: list[str] = []
    symbols: list[str] = []
    # Retain the compatibility argument, but never manufacture provenance from
    # the requested contract.  Availability must come from an actual answer.
    _ = requested_outputs
    for answer in list(getattr(result, "answers", None) or []):
        symbol = getattr(answer, "symbol", None)
        numeric = getattr(answer, "numeric", None)
        output_key = getattr(answer, "output_key", None)
        if symbol is not None and numeric is not None:
            mapping[str(symbol)] = numeric
            symbols.append(str(symbol))
        if output_key:
            output_keys.append(str(output_key))
            if numeric is not None:
                mapping.setdefault(str(output_key), numeric)
    representative = getattr(result, "answer", None)
    if representative is not None:
        numeric = getattr(representative, "numeric", None)
        output_key = getattr(representative, "output_key", None)
        if not mapping and numeric is not None:
            mapping["answer"] = numeric
        if output_key:
            output_keys.append(str(output_key))
            if numeric is not None:
                mapping.setdefault(str(output_key), numeric)
    candidate = candidate_from_mapping(
        mapping,
        candidate_id=candidate_id,
        rank_metadata={
            "solver_ok": bool(getattr(result, "ok", False)),
            "output_keys": sorted(set(output_keys)),
            "symbols": sorted(set(symbols)),
            "solver_errors": list(
                getattr(getattr(result, "verification", None), "errors", None) or []
            ),
        },
    )
    return candidate


def _check(
    *,
    check_id: str,
    category: str,
    passed: bool,
    message: str,
    observed: Any = None,
    expected: Any = None,
    absolute_error: float | None = None,
    relative_error: float | None = None,
    tolerance: float | None = None,
    source_equation_ids: Iterable[str] = (),
) -> CandidateValidationCheck:
    return CandidateValidationCheck(
        check_id=check_id,
        category=category,
        status="passed" if passed else "failed",
        message=message,
        observed=observed,
        expected=expected,
        absolute_error=absolute_error,
        relative_error=relative_error,
        tolerance=tolerance,
        source_equation_ids=list(source_equation_ids),
    )


def _substitute_candidate_then_context(
    expression: Any,
    candidate_mapping: Mapping[Any, Any],
    substitutions: Mapping[Any, Any],
) -> Any:
    """Bind solved unknowns before evaluating their known parameters."""

    if isinstance(expression, (int, float)) and not isinstance(expression, bool):
        return expression
    symbolic_expression = sp.sympify(expression)
    if (
        not getattr(symbolic_expression, "free_symbols", set())
        and all(
            isinstance(key, sp.Symbol)
            for key in candidate_mapping
        )
        and all(
            isinstance(key, sp.Symbol)
            for key in substitutions
        )
    ):
        return symbolic_expression
    return (
        symbolic_expression.subs(candidate_mapping).subs(substitutions)
    )


def _mapping_value(
    mapping: Mapping[Any, Any], symbol: Any, substitutions: Mapping[Any, Any]
) -> Any | None:
    if symbol in mapping:
        return _substitute_candidate_then_context(
            mapping[symbol], mapping, substitutions
        )
    variable_id = str(symbol)
    for key, value in mapping.items():
        if str(key) == variable_id:
            return _substitute_candidate_then_context(
                value, mapping, substitutions
            )
    return None


_SUPPORTED_SYMBOL_ASSUMPTIONS = (
    "real",
    "finite",
    "integer",
    "positive",
    "nonnegative",
    "negative",
    "nonpositive",
    "nonzero",
)


def _complex_characteristics(
    expression: Any,
) -> tuple[complex | None, str | None]:
    if isinstance(expression, (int, float, complex)) and not isinstance(
        expression, bool
    ):
        try:
            return complex(expression), None
        except Exception:
            return None, "not_numeric"
    try:
        value = sp.N(expression)
        if getattr(value, "free_symbols", set()):
            return None, "unresolved_symbol"
        return complex(value), None
    except Exception:
        return None, "not_numeric"


def _assumption_actual(
    assumption: str,
    expression: Any,
    *,
    tolerance: float,
    near_zero_tol: float,
) -> bool | None:
    value, error = _complex_characteristics(expression)
    if error is not None or value is None:
        return None
    finite = math.isfinite(value.real) and math.isfinite(value.imag)
    real = finite and abs(value.imag) <= near_zero_tol
    numeric = value.real if real else None
    if assumption == "real":
        return real
    if assumption == "finite":
        return finite
    if numeric is None:
        return None
    if assumption == "integer":
        return math.isclose(
            numeric,
            round(numeric),
            rel_tol=0.0,
            abs_tol=tolerance,
        )
    if assumption == "positive":
        return numeric > tolerance
    if assumption == "nonnegative":
        return numeric >= -tolerance
    if assumption == "negative":
        return numeric < -tolerance
    if assumption == "nonpositive":
        return numeric <= tolerance
    if assumption == "nonzero":
        return abs(numeric) > tolerance
    return None


def _evaluate_domain_condition(
    condition: Any,
    candidate: CandidateSolution,
    substitutions: Mapping[Any, Any],
) -> tuple[bool, Any, str | None]:
    if isinstance(condition, bool):
        return condition, condition, None if condition else "condition is false"
    if not isinstance(condition, sp.Basic):
        return False, condition, "condition is not a typed SymPy boolean"
    try:
        evaluated = condition.subs(candidate.symbolic_mapping).subs(substitutions)
    except Exception:
        return False, condition, "condition cannot be substituted"
    if getattr(evaluated, "free_symbols", set()):
        return False, evaluated, "condition contains unresolved symbols"
    try:
        evaluated = sp.simplify(evaluated)
    except Exception:
        return False, evaluated, "condition cannot be evaluated"
    if evaluated is sp.true or evaluated == sp.true:
        return True, evaluated, None
    if evaluated is sp.false or evaluated == sp.false:
        return False, evaluated, "condition is false"
    return False, evaluated, "condition did not evaluate to a boolean"


def _within_interval(
    value: float,
    lower: float | None,
    upper: float | None,
    lower_inclusive: bool,
    upper_inclusive: bool,
) -> bool:
    lower_ok = (
        True
        if lower is None
        else value >= lower
        if lower_inclusive
        else value > lower
    )
    upper_ok = (
        True
        if upper is None
        else value <= upper
        if upper_inclusive
        else value < upper
    )
    return lower_ok and upper_ok


def _evaluate_residual(
    evaluator: Any,
    candidate: CandidateSolution,
    substitutions: Mapping[Any, Any],
) -> tuple[float | None, str | None]:
    if callable(evaluator):
        try:
            value = evaluator(candidate)
        except TypeError:
            value = evaluator(candidate.symbolic_mapping)
        try:
            value = _substitute_candidate_then_context(
                value,
                candidate.symbolic_mapping,
                substitutions,
            )
        except Exception:
            return None, "evaluation_error"
        return _numeric(value)
    try:
        expression = evaluator
        if isinstance(expression, sp.Equality):
            expression = expression.lhs - expression.rhs
        value = _substitute_candidate_then_context(
            expression,
            candidate.symbolic_mapping,
            substitutions,
        )
        return _numeric(value)
    except Exception:
        return None, "evaluation_error"


def _requested_output_check(
    candidate: CandidateSolution,
    requested_outputs: Iterable[str],
) -> CandidateValidationCheck:
    available_outputs = set(candidate.rank_metadata.get("output_keys", []))
    requested = [str(output) for output in requested_outputs]
    missing_outputs: list[str] = []
    for output in requested:
        if output == "auto":
            continue
        accepted_outputs = {
            output,
            *OUTPUT_KEY_COMPATIBILITY.get(output, set()),
        }
        if not (accepted_outputs & available_outputs):
            missing_outputs.append(output)
    return _check(
        check_id="requested_outputs",
        category="output_contract",
        passed=not missing_outputs,
        message=(
            "requested outputs are available"
            if not missing_outputs
            else "missing requested outputs: " + ", ".join(missing_outputs)
        ),
        observed=sorted(available_outputs),
        expected=requested,
    )


def validate_candidates(
    candidates: Iterable[CandidateSolution],
    context: ValidationContext | None = None,
) -> list[ValidatedCandidate]:
    context = context or ValidationContext()
    validated: list[ValidatedCandidate] = []
    absolute = context.numerical_tolerance
    near_zero = 1e-10
    relative = context.relative_tolerance
    residual_tolerance = (
        context.residual_tolerance
        if context.residual_tolerance is not None
        else absolute
    )

    for candidate in candidates:
        checks: list[CandidateValidationCheck] = []

        solver_ok = candidate.rank_metadata.get("solver_ok")
        if solver_ok is not None:
            checks.append(
                _check(
                    check_id="solver_result_ok",
                    category="solver",
                    passed=bool(solver_ok),
                    message=(
                        "solver produced a candidate result"
                        if solver_ok
                        else "solver did not produce a successful candidate"
                    ),
                    observed=solver_ok,
                    expected=True,
                )
            )

        checks.append(
            _check(
                check_id="resolved_symbols",
                category="domain",
                passed=not candidate.unresolved_symbols,
                message=(
                    "candidate contains no unresolved symbols"
                    if not candidate.unresolved_symbols
                    else "unresolved symbols: " + ", ".join(candidate.unresolved_symbols)
                ),
                observed=candidate.unresolved_symbols,
                expected=[],
            )
        )

        numeric_errors: list[str] = []
        for symbol, expression in candidate.symbolic_mapping.items():
            try:
                evaluated = _substitute_candidate_then_context(
                    expression,
                    candidate.symbolic_mapping,
                    context.substitutions,
                )
            except Exception:
                numeric_errors.append(f"{symbol}: not_numeric")
                continue
            _, error = _numeric(evaluated)
            if error:
                numeric_errors.append(f"{symbol}: {error}")
        checks.append(
            _check(
                check_id="real_finite",
                category="domain",
                passed=not numeric_errors,
                message=(
                    "all candidate values are real and finite"
                    if not numeric_errors
                    else "; ".join(numeric_errors)
                ),
                observed=numeric_errors,
                expected=[],
            )
        )

        for symbol, expression in candidate.symbolic_mapping.items():
            if not isinstance(symbol, sp.Symbol):
                continue
            expected_assumptions: dict[str, bool] = {}
            observed_assumptions: dict[str, bool | None] = {}
            assumption_errors: list[str] = []
            try:
                evaluated = _substitute_candidate_then_context(
                    expression,
                    candidate.symbolic_mapping,
                    context.substitutions,
                )
            except Exception:
                evaluated = expression
            for assumption in _SUPPORTED_SYMBOL_ASSUMPTIONS:
                expected = getattr(symbol, f"is_{assumption}", None)
                if expected is None:
                    continue
                expected_bool = bool(expected)
                actual = _assumption_actual(
                    assumption,
                    evaluated,
                    tolerance=absolute,
                    near_zero_tol=near_zero,
                )
                expected_assumptions[assumption] = expected_bool
                observed_assumptions[assumption] = actual
                if actual is None or actual is not expected_bool:
                    assumption_errors.append(
                        f"{assumption} expected {expected_bool}, observed {actual}"
                    )
            if expected_assumptions:
                checks.append(
                    _check(
                        check_id=f"assumptions:{symbol}",
                        category="domain",
                        passed=not assumption_errors,
                        message=(
                            f"{symbol} satisfies its SymPy assumptions"
                            if not assumption_errors
                            else f"{symbol} assumption mismatch: "
                            + "; ".join(assumption_errors)
                        ),
                        observed=observed_assumptions,
                        expected=expected_assumptions,
                        tolerance=absolute,
                    )
                )

        for index, condition in enumerate(candidate.domain_conditions):
            passed, observed, error = _evaluate_domain_condition(
                condition,
                candidate,
                context.substitutions,
            )
            checks.append(
                _check(
                    check_id=f"domain_condition:{index}",
                    category="domain",
                    passed=passed,
                    message=(
                        "candidate domain condition is satisfied"
                        if passed
                        else f"candidate domain condition failed: {error}"
                    ),
                    observed=observed,
                    expected=True,
                )
            )

        denominator_errors: list[str] = []
        for denominator in candidate.denominator_conditions:
            try:
                evaluated = _substitute_candidate_then_context(
                    denominator,
                    candidate.symbolic_mapping,
                    context.substitutions,
                )
                numeric, error = _numeric(evaluated)
                if (
                    error is not None
                    or numeric is None
                    or abs(numeric) <= absolute
                ):
                    denominator_errors.append(
                        f"{denominator}: {error or 'zero'}"
                    )
            except Exception:
                denominator_errors.append(str(denominator))
        checks.append(
            _check(
                check_id="nonzero_denominator",
                category="domain",
                passed=not denominator_errors,
                message=(
                    "all evaluated denominators are nonzero"
                    if not denominator_errors
                    else "zero or singular denominator: " + ", ".join(denominator_errors)
                ),
                observed=denominator_errors,
                expected=[],
                tolerance=absolute,
            )
        )

        for constraint in context.variable_constraints():
            value_expression = _mapping_value(
                candidate.symbolic_mapping, constraint.symbol, context.substitutions
            )
            numeric: float | None = None
            observed_value: Any = value_expression
            reasons: list[str] = []
            passed = value_expression is not None
            requires_scalar = bool(
                constraint.allowed_interval is not None
                or constraint.allowed_intervals
                or constraint.lower_bound is not None
                or constraint.upper_bound is not None
                or constraint.integer
                or constraint.predicate is not None
            )
            if value_expression is None:
                passed = False
                reasons.append("missing")
            else:
                complex_value, error = _complex_characteristics(value_expression)
                if error is not None or complex_value is None:
                    passed = False
                    reasons.append(error or "not_numeric")
                else:
                    observed_value = complex_value
                    value_is_finite = (
                        math.isfinite(complex_value.real)
                        and math.isfinite(complex_value.imag)
                    )
                    value_is_real = (
                        value_is_finite
                        and abs(complex_value.imag) <= near_zero
                    )
                    if constraint.real and not value_is_real:
                        passed = False
                        reasons.append("not real")
                    if constraint.finite and not value_is_finite:
                        passed = False
                        reasons.append("not finite")
                    if value_is_real and value_is_finite:
                        numeric = float(complex_value.real)
                        observed_value = numeric
                    elif requires_scalar:
                        passed = False
                        reasons.append("not a finite real scalar")
            if passed and numeric is not None:
                lower, upper = (
                    constraint.allowed_interval
                    if constraint.allowed_interval is not None
                    else (constraint.lower_bound, constraint.upper_bound)
                )
                allowed = _within_interval(
                    numeric,
                    lower,
                    upper,
                    constraint.lower_inclusive,
                    constraint.upper_inclusive,
                )
                if constraint.allowed_intervals:
                    allowed = any(
                        _within_interval(numeric, lo, hi, True, True)
                        for lo, hi in constraint.allowed_intervals
                    )
                if not allowed:
                    passed = False
                    reasons.append("outside allowed interval")
                if constraint.integer and not math.isclose(
                    numeric, round(numeric), rel_tol=0.0, abs_tol=absolute
                ):
                    passed = False
                    reasons.append("not an integer")
                if constraint.predicate is not None:
                    try:
                        predicate_ok = bool(
                            constraint.predicate(numeric, candidate.symbolic_mapping)
                        )
                    except Exception:
                        predicate_ok = False
                    if not predicate_ok:
                        passed = False
                        reasons.append(
                            constraint.custom_predicate_id or "custom predicate failed"
                        )
            checks.append(
                _check(
                    check_id=f"variable:{constraint.variable_id}",
                    category="variable_constraint",
                    passed=passed,
                    message=(
                        constraint.reason
                        or (
                            f"{constraint.variable_id} satisfies its explicit constraint"
                            if passed
                            else f"{constraint.variable_id}: " + ", ".join(reasons)
                        )
                    ),
                    observed=observed_value,
                    expected={
                        "real": constraint.real,
                        "finite": constraint.finite,
                        "lower": constraint.lower_bound,
                        "upper": constraint.upper_bound,
                        "interval": constraint.allowed_interval,
                        "integer": constraint.integer,
                    },
                    tolerance=absolute,
                )
            )

        for index, equation in enumerate(context.equations):
            equation_id = getattr(equation, "id", None) or f"equation-{index}"
            expression = getattr(equation, "expression", equation)
            try:
                if isinstance(expression, sp.Equality):
                    left = _substitute_candidate_then_context(
                        expression.lhs,
                        candidate.symbolic_mapping,
                        context.substitutions,
                    )
                    right = _substitute_candidate_then_context(
                        expression.rhs,
                        candidate.symbolic_mapping,
                        context.substitutions,
                    )
                    left_num, left_error = _numeric(left)
                    right_num, right_error = _numeric(right)
                    if left_error or right_error or left_num is None or right_num is None:
                        raise ValueError(left_error or right_error or "unresolved")
                    residual = left_num - right_num
                    scale = max(abs(left_num), abs(right_num), 1.0)
                else:
                    residual_value, residual_error = _evaluate_residual(
                        expression, candidate, context.substitutions
                    )
                    if residual_error or residual_value is None:
                        raise ValueError(residual_error or "unresolved")
                    residual = residual_value
                    scale = max(abs(residual), 1.0)
                tolerance = max(residual_tolerance, relative * scale)
                passed = abs(residual) <= tolerance
                checks.append(
                    _check(
                        check_id=f"residual:{equation_id}",
                        category="equation_residual",
                        passed=passed,
                        message=(
                            f"{equation_id} residual is within tolerance"
                            if passed
                            else f"{equation_id} residual exceeds tolerance"
                        ),
                        observed=residual,
                        expected=0.0,
                        absolute_error=abs(residual),
                        relative_error=abs(residual) / scale,
                        tolerance=tolerance,
                        source_equation_ids=[str(equation_id)],
                    )
                )
            except Exception as exc:
                checks.append(
                    _check(
                        check_id=f"residual:{equation_id}",
                        category="equation_residual",
                        passed=False,
                        message=f"{equation_id} residual cannot be evaluated: {exc}",
                        observed=None,
                        expected=0.0,
                        tolerance=residual_tolerance,
                        source_equation_ids=[str(equation_id)],
                    )
                )

        for constraint in context.model_constraints:
            residual, error = _evaluate_residual(
                constraint.evaluator, candidate, context.substitutions
            )
            tolerance = (
                constraint.tolerance
                if constraint.tolerance is not None
                else residual_tolerance
            )
            passed = error is None and residual is not None and abs(residual) <= tolerance
            checks.append(
                _check(
                    check_id=f"model:{constraint.constraint_id}",
                    category=constraint.category,
                    passed=passed,
                    message=(
                        constraint.message
                        or (
                            f"{constraint.constraint_id} constraint satisfied"
                            if passed
                            else f"{constraint.constraint_id} constraint failed"
                        )
                    ),
                    observed=residual,
                    expected=0.0,
                    absolute_error=abs(residual) if residual is not None else None,
                    tolerance=tolerance,
                    source_equation_ids=constraint.source_equation_ids,
                )
            )

        if context.requested_symbols:
            available = {
                str(symbol) for symbol in candidate.symbolic_mapping
            }
            missing = [
                str(symbol)
                for symbol in context.requested_symbols
                if str(symbol) not in available
            ]
            checks.append(
                _check(
                    check_id="requested_symbols",
                    category="output_contract",
                    passed=not missing,
                    message=(
                        "requested symbols are available"
                        if not missing
                        else "missing requested symbols: " + ", ".join(missing)
                    ),
                    observed=sorted(available),
                    expected=[str(symbol) for symbol in context.requested_symbols],
                )
            )

        if context.requested_outputs:
            checks.append(
                _requested_output_check(candidate, context.requested_outputs)
            )

        if context.event_predicate is not None:
            try:
                event_ok = bool(context.event_predicate(candidate))
            except Exception:
                event_ok = False
            checks.append(
                _check(
                    check_id="event_condition",
                    category="event",
                    passed=event_ok,
                    message=(
                        context.event_description
                        or (
                            "candidate satisfies the explicit event"
                            if event_ok
                            else "candidate does not satisfy the explicit event"
                        )
                    ),
                    observed=event_ok,
                    expected=True,
                )
            )

        rejected = [check.message for check in checks if check.status == "failed"]
        candidate.validation_checks = list(checks)
        candidate.rejection_reasons = list(rejected)
        validated.append(
            ValidatedCandidate(
                candidate=candidate,
                accepted=not rejected,
                checks=checks,
                rejection_reasons=rejected,
            )
        )
    return validated


def validate_output_candidates(
    candidates: Iterable[CandidateSolution],
    context: ValidationContext | None = None,
) -> SelectionDecision:
    """Validate final solver outputs without repeating a solver branch proof.

    This path is used only when the solver already returned a typed selected
    decision.  It rechecks solver success, finite resolved answer values, and
    the semantic requested-output contract before preserving that decision.
    """

    context = context or ValidationContext()
    validated: list[ValidatedCandidate] = []
    for candidate in candidates:
        checks: list[CandidateValidationCheck] = []
        solver_ok = bool(candidate.rank_metadata.get("solver_ok", False))
        checks.append(
            _check(
                check_id="solver_result_ok",
                category="solver",
                passed=solver_ok,
                message=(
                    "solver produced a candidate result"
                    if solver_ok
                    else "solver did not produce a successful candidate"
                ),
                observed=solver_ok,
                expected=True,
            )
        )
        numeric_errors: list[str] = []
        if candidate.unresolved_symbols:
            numeric_errors.extend(
                f"{symbol}: unresolved_symbol"
                for symbol in candidate.unresolved_symbols
            )
        for symbol, value in candidate.symbolic_mapping.items():
            _, error = _numeric(value)
            if error is not None:
                numeric_errors.append(f"{symbol}: {error}")
        checks.append(
            _check(
                check_id="real_finite",
                category="domain",
                passed=not numeric_errors,
                message=(
                    "all final answer values are real and finite"
                    if not numeric_errors
                    else "; ".join(numeric_errors)
                ),
                observed=numeric_errors,
                expected=[],
            )
        )
        if context.requested_outputs:
            checks.append(
                _requested_output_check(candidate, context.requested_outputs)
            )
        rejected = [check.message for check in checks if check.status == "failed"]
        candidate.validation_checks = list(checks)
        candidate.rejection_reasons = list(rejected)
        validated.append(
            ValidatedCandidate(
                candidate=candidate,
                accepted=not rejected,
                checks=checks,
                rejection_reasons=rejected,
            )
        )
    return select_solution(validated, context)


def select_solution(
    validated: Iterable[ValidatedCandidate],
    context: ValidationContext | None = None,
) -> SelectionDecision:
    context = context or ValidationContext()
    items = list(validated)
    valid = [item.candidate for item in items if item.accepted]
    rejected = [item for item in items if not item.accepted]

    if context.preferred_candidate_id is not None:
        preferred = [
            candidate
            for candidate in valid
            if candidate.candidate_id == context.preferred_candidate_id
        ]
        if len(preferred) == 1:
            return SelectionDecision(
                status="selected",
                selected_candidate=preferred[0],
                valid_alternatives=[
                    item for item in valid if item.candidate_id != preferred[0].candidate_id
                ],
                rejected_candidates=rejected,
                selection_policy=context.selection_policy,
                explanation=context.event_description
                or "an explicit event, direction, or interval selected this candidate",
                tolerances=context.tolerances,
                policy_version=context.policy_version,
            )
        # An explicitly requested event/branch is authoritative.  If it is
        # absent, rejected, or duplicated, selecting another valid branch would
        # silently answer a different question.
        return SelectionDecision(
            status="no_valid_solution",
            selected_candidate=None,
            valid_alternatives=valid,
            rejected_candidates=rejected,
            selection_policy=context.selection_policy,
            explanation=(
                "the explicitly preferred candidate was not uniquely valid; "
                "no alternative was selected"
            ),
            tolerances=context.tolerances,
            policy_version=context.policy_version,
        )

    if len(valid) == 1:
        return SelectionDecision(
            status="selected",
            selected_candidate=valid[0],
            valid_alternatives=[],
            rejected_candidates=rejected,
            selection_policy=context.selection_policy,
            explanation="exactly one candidate satisfied all explicit constraints",
            tolerances=context.tolerances,
            policy_version=context.policy_version,
        )
    if len(valid) > 1:
        return SelectionDecision(
            status="ambiguous",
            selected_candidate=None,
            valid_alternatives=valid,
            rejected_candidates=rejected,
            selection_policy=context.selection_policy,
            explanation="multiple candidates satisfy every explicit constraint",
            tolerances=context.tolerances,
            policy_version=context.policy_version,
        )

    failed_checks = [
        check
        for item in items
        for check in item.checks
        if check.status == "failed"
    ]
    # Non-finite/not-numeric evaluation is distinct from an ordinary physical
    # domain rejection. Cascading explicit-constraint failures do not erase the
    # originating numerical status.
    numerical_failure = any(
        check.check_id == "real_finite"
        and any(
            token in check.message
            for token in ("not_numeric", "non_finite", "cannot be evaluated")
        )
        for check in failed_checks
    )
    return SelectionDecision(
        status="numerical_failure" if numerical_failure else "no_valid_solution",
        selected_candidate=None,
        valid_alternatives=[],
        rejected_candidates=rejected,
        selection_policy=context.selection_policy,
        explanation=(
            "candidate evaluation failed numerically"
            if numerical_failure
            else "no candidate satisfied all explicit constraints"
        ),
        tolerances=context.tolerances,
        policy_version=context.policy_version,
    )


def validate_and_select(
    candidates: Iterable[CandidateSolution],
    context: ValidationContext | None = None,
) -> SelectionDecision:
    context = context or ValidationContext()
    return select_solution(validate_candidates(candidates, context), context)


def numerical_failure_decision(
    error: Exception | str,
    context: ValidationContext | None = None,
) -> SelectionDecision:
    context = context or ValidationContext()
    return SelectionDecision(
        status="numerical_failure",
        explanation=f"candidate solver failed: {error}",
        selection_policy=context.selection_policy,
        tolerances=context.tolerances,
        policy_version=context.policy_version,
    )


def filter_physical_solutions(
    raw: Iterable[Mapping[Any, Any]],
    constraints: dict[Any, VariableConstraint] | list[VariableConstraint] | None = None,
    *,
    equations: Iterable[Any] = (),
    substitutions: Mapping[Any, Any] | None = None,
) -> list[dict[Any, Any]]:
    """Compatibility helper with explicit constraints and no name-based rules."""

    context = ValidationContext(
        equations=list(equations),
        substitutions=dict(substitutions or {}),
        constraints=constraints or {},
    )
    candidates = [
        candidate_from_mapping(
            mapping,
            substitutions=context.substitutions,
            candidate_id=f"candidate-{index}",
        )
        for index, mapping in enumerate(raw)
    ]
    return [
        item.candidate.symbolic_mapping
        for item in validate_candidates(candidates, context)
        if item.accepted
    ]
