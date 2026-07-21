"""Fail-closed independent verification for Stage 4 mechanics candidates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math

from engine.mechanics.math_ast import (
    Equality,
    Inequality,
    InequalityRelation,
    SymbolRef,
    SymbolShape,
    validate_math_expression,
)
from engine.mechanics.solver.contracts import (
    CandidateRejection,
    CandidateRejectionReason,
    CandidateSet,
    SIValue,
    SolvePlan,
    SolverCandidate,
    SolverDiagnostics,
)
from engine.mechanics.verification.contracts import (
    MechanicsSolveResult,
    MechanicsSolveTerminal,
    VerificationCheck,
    VerificationCheckKind,
    VerificationCheckStatus,
    VerificationOutcome,
    VerifiedCandidate,
    _FAILED_REASON_BY_KIND,
    _TERMINAL_CODE,
    _expected_check_provenance,
)
from engine.mechanics.verification.evaluator import (
    EvaluationStatus,
    RelationResult,
    evaluate_relation,
)


@dataclass(frozen=True)
class _CheckDecision:
    status: VerificationCheckStatus
    measured_error: float | None = None
    tolerance: float | None = None

    def __post_init__(self) -> None:
        if (self.measured_error is None) != (self.tolerance is None):
            raise ValueError("check measurements must be paired")


def _finite_scalar(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _finite_vector(value: object, length: int | None = None) -> tuple[float, ...] | None:
    if not isinstance(value, tuple) or not value or (length is not None and len(value) != length):
        return None
    converted: list[float] = []
    for item in value:
        scalar = _finite_scalar(item)
        if scalar is None:
            return None
        converted.append(scalar)
    return tuple(converted)


def _shape_valid(symbol_node: object, value: object) -> bool:
    symbol = symbol_node.symbol
    if symbol.shape is SymbolShape.scalar:
        return _finite_scalar(value) is not None
    return _finite_vector(value, symbol.vector_length) is not None


def _environment(plan: SolvePlan, candidate: SolverCandidate) -> dict[str, SIValue]:
    values: dict[str, SIValue] = {
        item.symbol.symbol_id: item.known_si_value
        for item in plan.graph.symbols
        if item.known_si_value is not None
    }
    for item in candidate.values:
        values[item.symbol_id] = item.value_si
    return values


def _relation_result(
    plan: SolvePlan,
    relation: Equality | Inequality,
    values: dict[str, SIValue],
) -> RelationResult:
    return evaluate_relation(
        relation,
        values,
        absolute_tolerance=plan.budget.absolute_tolerance,
        relative_tolerance=plan.budget.relative_tolerance,
        constraint_tolerance=plan.budget.constraint_tolerance,
        max_nodes=plan.budget.max_ast_nodes,
        max_depth=plan.budget.max_ast_depth,
    )


def _residual_tolerance(plan: SolvePlan, relation: RelationResult) -> float:
    return min(
        1.0,
        max(
            plan.budget.residual_tolerance,
            plan.budget.relative_tolerance,
            relation.tolerance or plan.budget.absolute_tolerance,
        ),
    )


def _aggregate_relations(
    plan: SolvePlan,
    candidate: SolverCandidate,
    equation_ids: Iterable[str],
    *,
    require_predicate: bool = False,
) -> _CheckDecision:
    equation_by_id = {item.equation_id: item for item in plan.graph.equations}
    identifiers = tuple(equation_ids)
    if not identifiers or any(identifier not in equation_by_id for identifier in identifiers):
        return _CheckDecision(VerificationCheckStatus.inconclusive)
    equations = tuple(equation_by_id[identifier] for identifier in identifiers)
    if require_predicate and not any(isinstance(item.expression, Inequality) for item in equations):
        return _CheckDecision(VerificationCheckStatus.inconclusive)

    values = _environment(plan, candidate)
    saw_inconclusive = False
    saw_failure = False
    equality_errors: list[float] = []
    equality_tolerances: list[float] = []
    only_equalities = True
    for equation in equations:
        relation = _relation_result(plan, equation.expression, values)
        if relation.status is EvaluationStatus.inconclusive:
            saw_inconclusive = True
            continue
        if relation.status is EvaluationStatus.error:
            saw_failure = True
            continue
        assert relation.satisfied is not None
        if isinstance(equation.expression, Equality):
            assert relation.measured_error is not None
            tolerance = _residual_tolerance(plan, relation)
            equality_errors.append(relation.measured_error)
            equality_tolerances.append(tolerance)
            if relation.measured_error > tolerance:
                saw_failure = True
        else:
            only_equalities = False
            if not relation.satisfied:
                saw_failure = True
    status = (
        VerificationCheckStatus.failed
        if saw_failure
        else VerificationCheckStatus.inconclusive
        if saw_inconclusive
        else VerificationCheckStatus.passed
    )
    if only_equalities and equality_errors and not saw_inconclusive:
        measured = max(equality_errors)
        tolerance = min(equality_tolerances)
        # VerificationCheck's invariant binds measurement and status.  A
        # definitive error without a numeric residual (for example division by
        # zero) is represented without a fabricated measurement.
        if not (saw_failure and measured <= tolerance):
            return _CheckDecision(status, measured, tolerance)
    return _CheckDecision(status)


def _unit_consistency(plan: SolvePlan, candidate: SolverCandidate) -> _CheckDecision:
    symbols = {item.symbol.symbol_id: item for item in plan.graph.symbols}
    values = _environment(plan, candidate)
    for identifier in (*plan.known_symbol_ids, *plan.unknown_symbol_ids):
        symbol = symbols.get(identifier)
        if symbol is None or identifier not in values or not _shape_valid(symbol, values[identifier]):
            return _CheckDecision(VerificationCheckStatus.failed)
    for equation in plan.graph.equations:
        issues = validate_math_expression(
            equation.expression,
            {identifier: item.symbol for identifier, item in symbols.items()},
            path=f"equation.{equation.equation_id}",
        )
        if issues:
            return _CheckDecision(VerificationCheckStatus.failed)
    return _CheckDecision(VerificationCheckStatus.passed)


def _query_binding(plan: SolvePlan, candidate: SolverCandidate) -> _CheckDecision:
    matches = tuple(
        item
        for item in candidate.values
        if item.symbol_id == plan.query_symbol_id
    )
    if (
        candidate.query_symbol_id != plan.query_symbol_id
        or len(matches) != 1
        or matches[0].value_si != candidate.query_value_si
    ):
        return _CheckDecision(VerificationCheckStatus.failed)
    return _CheckDecision(VerificationCheckStatus.passed)


def _source_evidence(plan: SolvePlan, candidate: SolverCandidate) -> _CheckDecision:
    graph = plan.graph
    equation_by_id = {item.equation_id: item for item in graph.equations}
    applications_by_equation: dict[str, list[object]] = {}
    for application in graph.applications:
        for equation_id in application.equation_ids:
            applications_by_equation.setdefault(equation_id, []).append(application)
    constraints_by_equation: dict[str, list[object]] = {}
    for constraint in graph.constraints:
        constraints_by_equation.setdefault(constraint.equation_id, []).append(constraint)

    required_equations = tuple(sorted({
        *candidate.equation_ids,
        *plan.inequality_ids,
        *(
            constraint.equation_id
            for constraint in graph.constraints
            if constraint.constraint_id in set(plan.constraint_ids)
        ),
    }))
    for equation_id in required_equations:
        equation = equation_by_id.get(equation_id)
        if equation is None:
            return _CheckDecision(VerificationCheckStatus.failed)
        sources = {
            *equation.source_evidence_ids,
            *(
                source
                for application in applications_by_equation.get(equation_id, ())
                for source in application.source_evidence_ids
            ),
            *(
                source
                for constraint in constraints_by_equation.get(equation_id, ())
                for source in constraint.source_evidence_ids
            ),
        }
        if not sources:
            return _CheckDecision(VerificationCheckStatus.failed)
    if any(
        not condition.source_evidence_ids
        for condition in graph.initial_conditions
        if condition.condition_id in set(plan.initial_condition_ids)
    ):
        return _CheckDecision(VerificationCheckStatus.failed)
    actual_union = {
        source
        for item in (*graph.equations, *graph.constraints, *graph.initial_conditions, *graph.applications)
        for source in item.source_evidence_ids
    }
    if actual_union != set(plan.allowed_source_evidence_ids):
        return _CheckDecision(VerificationCheckStatus.failed)
    return _CheckDecision(VerificationCheckStatus.passed)


def _domain_symbols(
    plan: SolvePlan,
    candidate: SolverCandidate,
    symbol_ids: tuple[str, ...],
    *,
    positive: bool,
) -> _CheckDecision:
    values = _environment(plan, candidate)
    for identifier in symbol_ids:
        scalar = _finite_scalar(values.get(identifier))
        if scalar is None or (scalar <= 0.0 if positive else scalar < 0.0):
            return _CheckDecision(VerificationCheckStatus.failed)
    return _CheckDecision(VerificationCheckStatus.passed)


def _event_order(plan: SolvePlan, candidate: SolverCandidate) -> _CheckDecision:
    values = _environment(plan, candidate)
    event_ids = plan.event_ids
    time_symbols: dict[str, list[str]] = {identifier: [] for identifier in event_ids}
    for item in plan.graph.symbols:
        if (
            item.event_id in time_symbols
            and (item.quantity_role or "").lower() in {"time", "duration"}
        ):
            time_symbols[item.event_id].append(item.symbol.symbol_id)
    if any(len(items) != 1 for items in time_symbols.values()):
        return _CheckDecision(VerificationCheckStatus.inconclusive)
    event_by_symbol = {
        symbols[0]: event_id
        for event_id, symbols in time_symbols.items()
    }
    if any(_finite_scalar(values.get(symbol_id)) is None for symbol_id in event_by_symbol):
        return _CheckDecision(VerificationCheckStatus.inconclusive)
    if any(float(values[symbol_id]) < 0.0 for symbol_id in event_by_symbol):
        return _CheckDecision(VerificationCheckStatus.failed)
    if len(event_ids) <= 1:
        return _CheckDecision(VerificationCheckStatus.passed)

    edges: dict[str, set[str]] = {identifier: set() for identifier in event_ids}
    saw_relation = False
    for equation in plan.graph.equations:
        expression = equation.expression
        if not isinstance(expression.left, SymbolRef) or not isinstance(expression.right, SymbolRef):
            continue
        left_event = event_by_symbol.get(expression.left.symbol_id)
        right_event = event_by_symbol.get(expression.right.symbol_id)
        if left_event is None or right_event is None or left_event == right_event:
            continue
        saw_relation = True
        relation = _relation_result(plan, expression, values)
        if relation.status is EvaluationStatus.inconclusive:
            return _CheckDecision(VerificationCheckStatus.inconclusive)
        if relation.status is EvaluationStatus.error or not relation.satisfied:
            return _CheckDecision(VerificationCheckStatus.failed)
        if isinstance(expression, Equality):
            edges[left_event].add(right_event)
            edges[right_event].add(left_event)
        elif expression.relation in {InequalityRelation.lt, InequalityRelation.le}:
            edges[left_event].add(right_event)
        else:
            edges[right_event].add(left_event)
    if not saw_relation:
        return _CheckDecision(VerificationCheckStatus.inconclusive)
    closure = {identifier: set(targets) for identifier, targets in edges.items()}
    for pivot in event_ids:
        for origin in event_ids:
            if pivot in closure[origin]:
                closure[origin].update(closure[pivot])
    for index, left in enumerate(event_ids):
        for right in event_ids[index + 1:]:
            if right not in closure[left] and left not in closure[right]:
                return _CheckDecision(VerificationCheckStatus.inconclusive)
    return _CheckDecision(VerificationCheckStatus.passed)


def _initial_conditions(plan: SolvePlan, candidate: SolverCandidate) -> _CheckDecision:
    values = _environment(plan, candidate)
    conditions = tuple(
        item
        for item in plan.graph.initial_conditions
        if item.condition_id in set(plan.initial_condition_ids)
    )
    saw_inconclusive = False
    saw_failure = False
    errors: list[float] = []
    tolerances: list[float] = []
    for condition in conditions:
        if _finite_scalar(values.get(condition.wrt_symbol_id)) is None:
            saw_inconclusive = True
            continue
        if condition.derivative_order != 0:
            saw_inconclusive = True
            continue
        relation = _relation_result(
            plan,
            Equality(
                left=SymbolRef(symbol_id=condition.target_symbol_id),
                right=SymbolRef(symbol_id=condition.value_symbol_id),
            ),
            values,
        )
        if relation.status is EvaluationStatus.inconclusive:
            saw_inconclusive = True
        elif relation.status is EvaluationStatus.error:
            saw_failure = True
        else:
            assert relation.measured_error is not None
            tolerance = _residual_tolerance(plan, relation)
            errors.append(relation.measured_error)
            tolerances.append(tolerance)
            if relation.measured_error > tolerance:
                saw_failure = True
    status = (
        VerificationCheckStatus.failed
        if saw_failure
        else VerificationCheckStatus.inconclusive
        if saw_inconclusive
        else VerificationCheckStatus.passed
    )
    if errors and not saw_inconclusive:
        measured = max(errors)
        tolerance = min(tolerances)
        if not (saw_failure and measured <= tolerance):
            return _CheckDecision(status, measured, tolerance)
    return _CheckDecision(status)


def _physical_regime(
    plan: SolvePlan,
    candidate: SolverCandidate,
    equation_ids: tuple[str, ...],
    constraint_ids: tuple[str, ...],
) -> _CheckDecision:
    constraints = {
        item.constraint_id: item
        for item in plan.graph.constraints
    }
    if not constraint_ids:
        equation_by_id = {item.equation_id: item for item in plan.graph.equations}
        if not any(
            isinstance(equation_by_id[identifier].expression, Inequality)
            for identifier in equation_ids
            if identifier in equation_by_id
        ):
            return _CheckDecision(VerificationCheckStatus.inconclusive)
    related = tuple(sorted({
        *equation_ids,
        *(
            constraints[identifier].equation_id
            for identifier in constraint_ids
            if identifier in constraints
        ),
    }))
    return _aggregate_relations(plan, candidate, related)


def _decision_for_kind(
    plan: SolvePlan,
    candidate: SolverCandidate,
    kind: VerificationCheckKind,
    provenance: object,
) -> _CheckDecision:
    if kind is VerificationCheckKind.unit_consistency:
        return _unit_consistency(plan, candidate)
    if kind is VerificationCheckKind.query_binding:
        return _query_binding(plan, candidate)
    if kind is VerificationCheckKind.equation_residual:
        return _aggregate_relations(plan, candidate, provenance.equation_ids)
    if kind is VerificationCheckKind.independent_equation_set:
        return _aggregate_relations(plan, candidate, provenance.equation_ids)
    if kind is VerificationCheckKind.inequality:
        return _aggregate_relations(plan, candidate, provenance.equation_ids)
    if kind is VerificationCheckKind.constraint:
        constraint_by_id = {item.constraint_id: item for item in plan.graph.constraints}
        equation_ids = tuple(sorted({
            constraint_by_id[identifier].equation_id
            for identifier in provenance.constraint_ids
            if identifier in constraint_by_id
        }))
        return _aggregate_relations(plan, candidate, equation_ids)
    if kind is VerificationCheckKind.source_evidence:
        return _source_evidence(plan, candidate)
    if kind is VerificationCheckKind.nonnegative_time:
        return _domain_symbols(plan, candidate, provenance.symbol_ids, positive=False)
    if kind is VerificationCheckKind.positive_parameter:
        return _domain_symbols(plan, candidate, provenance.symbol_ids, positive=True)
    if kind is VerificationCheckKind.event_order:
        return _event_order(plan, candidate)
    if kind is VerificationCheckKind.initial_boundary_condition:
        return _initial_conditions(plan, candidate)
    if kind is VerificationCheckKind.physical_regime:
        return _physical_regime(
            plan,
            candidate,
            provenance.equation_ids,
            provenance.constraint_ids,
        )
    if kind is VerificationCheckKind.conserved_quantity:
        return _aggregate_relations(plan, candidate, provenance.equation_ids)
    if kind is VerificationCheckKind.numerical_integration_residual:
        # SIValue has no trajectory, time-grid, or derivative samples.  An ODE
        # backend claim cannot substitute for independent integration evidence.
        return _CheckDecision(VerificationCheckStatus.inconclusive)
    return _CheckDecision(VerificationCheckStatus.inconclusive)


def _verification_check(
    plan: SolvePlan,
    candidate: SolverCandidate,
    kind: VerificationCheckKind,
    provenance: object,
) -> VerificationCheck:
    decision = _decision_for_kind(plan, candidate, kind, provenance)
    return VerificationCheck(
        check_id=f"check_{kind.value}",
        kind=kind,
        status=decision.status,
        equation_ids=provenance.equation_ids,
        constraint_ids=provenance.constraint_ids,
        event_ids=provenance.event_ids,
        symbol_ids=provenance.symbol_ids,
        initial_condition_ids=provenance.initial_condition_ids,
        source_evidence_ids=provenance.source_evidence_ids,
        measured_error=decision.measured_error,
        tolerance=decision.tolerance,
    )


def _candidate_outcome(plan: SolvePlan, candidate: SolverCandidate) -> VerificationOutcome:
    expected = _expected_check_provenance(plan, candidate)
    checks = tuple(sorted(
        (
            _verification_check(plan, candidate, kind, provenance)
            for kind, provenance in expected.items()
        ),
        key=lambda item: item.check_id,
    ))
    rejections = tuple(sorted(
        (
            CandidateRejection(
                candidate_id=candidate.candidate_id,
                reason=(
                    CandidateRejectionReason.verification_inconclusive
                    if check.status is VerificationCheckStatus.inconclusive
                    else _FAILED_REASON_BY_KIND[check.kind]
                ),
                check_id=check.check_id,
                equation_ids=check.equation_ids,
                constraint_ids=check.constraint_ids,
                event_ids=check.event_ids,
                symbol_ids=check.symbol_ids,
                initial_condition_ids=check.initial_condition_ids,
                source_evidence_ids=check.source_evidence_ids,
            )
            for check in checks
            if check.status is not VerificationCheckStatus.passed
        ),
        key=lambda item: (
            item.check_id,
            item.reason.value,
            item.equation_ids,
            item.constraint_ids,
            item.event_ids,
            item.symbol_ids,
            item.initial_condition_ids,
            item.source_evidence_ids,
        ),
    ))
    return VerificationOutcome(
        candidate_id=candidate.candidate_id,
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        passed=not rejections,
        checks=checks,
        rejections=rejections,
    )


def _diagnostic_failure(diagnostics: SolverDiagnostics) -> MechanicsSolveTerminal | None:
    terminals = tuple(
        _TERMINAL_CODE[item.code]
        for item in diagnostics.entries
        if item.code in _TERMINAL_CODE
    )
    if len(terminals) > 1 or len(set(terminals)) > 1:
        raise ValueError("solver diagnostics contain contradictory terminal failures")
    return terminals[0] if terminals else None


def verify_solver_candidates(
    plan: SolvePlan,
    candidate_set: CandidateSet,
    diagnostics: SolverDiagnostics,
) -> MechanicsSolveResult:
    """Verify every retained candidate once and apply the closed terminal policy."""

    failure = _diagnostic_failure(diagnostics)
    if failure is not None:
        return MechanicsSolveResult(
            terminal=failure,
            plan=plan,
            candidate_set=candidate_set,
            verification_outcomes=(),
            verified_candidates=(),
            rejections=(),
            selected_candidate_id=None,
            diagnostics=diagnostics,
        )

    outcomes = tuple(
        _candidate_outcome(plan, candidate)
        for candidate in candidate_set.candidates
    )
    verified = tuple(
        VerifiedCandidate(
            candidate=candidate,
            outcome=outcome,
            query_symbol_id=candidate.query_symbol_id,
            query_value_si=candidate.query_value_si,
        )
        for candidate, outcome in zip(candidate_set.candidates, outcomes)
        if outcome.passed
    )
    if candidate_set.auto_selectable:
        terminal = (
            MechanicsSolveTerminal.solved
            if len(verified) == 1
            else MechanicsSolveTerminal.ambiguity
            if len(verified) >= 2
            else MechanicsSolveTerminal.insufficient_conditions
        )
    else:
        terminal = (
            MechanicsSolveTerminal.needs_confirmation
            if verified
            else MechanicsSolveTerminal.insufficient_conditions
        )
    selected = verified[0].candidate.candidate_id if terminal is MechanicsSolveTerminal.solved else None
    return MechanicsSolveResult(
        terminal=terminal,
        plan=plan,
        candidate_set=candidate_set,
        verification_outcomes=outcomes,
        verified_candidates=verified,
        rejections=tuple(
            rejection
            for outcome in outcomes
            for rejection in outcome.rejections
        ),
        selected_candidate_id=selected,
        diagnostics=diagnostics,
    )


# Concise call-site alias retained for service integration in a later stage.
verify_candidates = verify_solver_candidates


__all__ = ["verify_candidates", "verify_solver_candidates"]
