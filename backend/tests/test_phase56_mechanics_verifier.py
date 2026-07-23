from __future__ import annotations

import inspect
import math
from pathlib import Path
import re

import pytest

from engine.mechanics.compiler import (
    ConstraintNode,
    EquationGraph,
    EquationNode,
    EquationScope,
    IncidenceEdge,
    InitialConditionNode,
    LawApplication,
    RankAnalysis,
    SymbolNode,
)
from engine.mechanics.math_ast import (
    Add,
    Derivative,
    DimensionVector,
    Divide,
    Equality,
    Inequality,
    LiteralNode,
    Multiply,
    Piecewise,
    PiecewiseBranch,
    Power,
    Sqrt,
    SymbolDefinition,
    SymbolRef,
    VectorNode,
)
from engine.mechanics.solver import (
    CandidateSet,
    CandidateValue,
    DiagnosticSeverity,
    SolveBackendKind,
    SolvePlan,
    SolverBudget,
    SolverCandidate,
    SolverDiagnosticCode,
    SolverDiagnosticEntry,
    SolverDiagnostics,
    candidate_generation_manifest,
    diagnostic_entry_sort_key,
    make_solver_candidate,
    numeric_fallback_for_structure,
    primary_backend_for_structure,
)
from engine.mechanics.solver.contracts import (
    _graph_event_ids,
    _graph_evidence_ids,
    _graph_structure,
    _graph_unknown_ids,
)
from engine.mechanics.verification.evaluator import (
    EvaluationErrorCode,
    EvaluationStatus,
    evaluate_expression,
    evaluate_relation,
)
from engine.mechanics.verification.verifier import verify_solver_candidates


DIMENSIONLESS = DimensionVector()
TIME = DimensionVector(time=1)


def _symbol(
    identifier: str,
    *,
    known: float | tuple[float, ...] | None,
    role: str,
    dimension: DimensionVector = DIMENSIONLESS,
    shape: str = "scalar",
    vector_length: int | None = None,
    event_id: str | None = None,
    subject_id: str | None = None,
) -> SymbolNode:
    quantity_id = f"quantity_{identifier}"
    return SymbolNode(
        symbol=SymbolDefinition(
            symbol_id=identifier,
            quantity_id=quantity_id,
            dimension=dimension,
            shape=shape,
            vector_length=vector_length,
        ),
        quantity_id=quantity_id,
        quantity_role=role,
        subject_id=subject_id,
        event_id=event_id,
        known_si_value=known,
    )


def _equation(
    identifier: str,
    expression: Equality | Inequality,
    *,
    law_id: str = "generic_law",
    scope: EquationScope | None = None,
    constraints: tuple[str, ...] = (),
    sources: tuple[str, ...] = (),
    dimension: DimensionVector = DIMENSIONLESS,
) -> EquationNode:
    return EquationNode(
        equation_id=identifier,
        expression=expression,
        expression_fingerprint=(identifier[0].lower() if identifier[0].lower() in "abcdef" else "b") * 64,
        law_id=law_id,
        scope=scope or EquationScope(),
        source_evidence_ids=sources,
        constraint_ids=constraints,
        dimension=dimension,
        complexity_cost=8,
    )


def _graph(
    *,
    selected_expression: Equality | None = None,
    x_role: str = "position",
    x_dimension: DimensionVector = DIMENSIONLESS,
    x_shape: str = "scalar",
    x_vector_length: int | None = None,
    g_value: float | tuple[float, ...] = 2.0,
    selected_scope: EquationScope | None = None,
    selected_sources: tuple[str, ...] = (),
    extra_symbols: tuple[SymbolNode, ...] = (),
    extra_equations: tuple[EquationNode, ...] = (),
    constraints: tuple[ConstraintNode, ...] = (),
    initial_conditions: tuple[InitialConditionNode, ...] = (),
    application_law: str = "generic_law",
    alternative_sets: tuple[tuple[str, ...], ...] = (),
) -> EquationGraph:
    x = _symbol(
        "x",
        known=None,
        role=x_role,
        dimension=x_dimension,
        shape=x_shape,
        vector_length=x_vector_length,
    )
    g = _symbol(
        "g",
        known=g_value,
        role="parameter",
        dimension=x_dimension,
        shape=x_shape,
        vector_length=x_vector_length,
    )
    selected = _equation(
        "eq_selected",
        selected_expression or Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="g")),
        law_id=application_law,
        scope=selected_scope,
        sources=selected_sources,
        dimension=x_dimension,
    )
    equations = (selected, *extra_equations)
    application_sources = tuple(sorted({
        source
        for equation in equations
        for source in equation.source_evidence_ids
    }))
    application_constraints = tuple(sorted(item.constraint_id for item in constraints))
    equality_count = sum(isinstance(item.expression, Equality) for item in equations)
    inequality_count = len(equations) - equality_count
    return EquationGraph(
        query_id="query_x",
        query_symbol_id="x",
        symbols=(g, *extra_symbols, x),
        equations=equations,
        constraints=constraints,
        initial_conditions=initial_conditions,
        applications=(LawApplication(
            application_id="application_main",
            law_id=application_law,
            equation_ids=tuple(sorted(item.equation_id for item in equations)),
            scope=selected_scope or EquationScope(),
            source_evidence_ids=application_sources,
            constraint_ids=application_constraints,
            complexity_cost=sum(item.complexity_cost for item in equations),
        ),),
        incidence=(IncidenceEdge(equation_id="eq_selected", symbol_id="x"),),
        rank=RankAnalysis(
            equality_count=equality_count,
            inequality_count=inequality_count,
            unknown_count=1,
            structural_rank=1,
            underdetermined=False,
            overdetermined=equality_count > 1,
            conflicting=False,
        ),
        selected_equation_ids=("eq_selected",),
        alternative_closed_sets=alternative_sets,
        fingerprint="a" * 64,
    )


def _plan(graph: EquationGraph, *, budget: SolverBudget | None = None) -> SolvePlan:
    unknowns = _graph_unknown_ids(graph)
    structure = _graph_structure(graph, unknowns)
    return SolvePlan(
        graph=graph,
        query_id=graph.query_id,
        query_symbol_id=graph.query_symbol_id,
        selected_equality_ids=graph.selected_equation_ids,
        inequality_ids=tuple(sorted(
            item.equation_id
            for item in graph.equations
            if isinstance(item.expression, Inequality)
        )),
        constraint_ids=tuple(sorted(item.constraint_id for item in graph.constraints)),
        initial_condition_ids=tuple(sorted(item.condition_id for item in graph.initial_conditions)),
        event_ids=_graph_event_ids(graph),
        allowed_source_evidence_ids=_graph_evidence_ids(graph),
        unknown_symbol_ids=unknowns,
        known_symbol_ids=tuple(sorted(
            item.symbol.symbol_id
            for item in graph.symbols
            if item.known_si_value is not None
        )),
        structure=structure,
        primary_backend=primary_backend_for_structure(structure),
        permitted_numeric_fallback=numeric_fallback_for_structure(structure),
        budget=budget or SolverBudget(),
    )


def _candidate(
    plan: SolvePlan,
    value: float | tuple[float, ...],
    *,
    generation_index: int = 0,
    root_index: int = 0,
    backend: SolveBackendKind | None = None,
    approximate: bool = False,
) -> SolverCandidate:
    assert plan.unknown_symbol_ids == ("x",)
    return make_solver_candidate(
        generation_index=generation_index,
        root_index=root_index,
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        backend=backend or plan.primary_backend,
        approximate=approximate,
        equation_ids=plan.selected_equality_ids,
        values=(CandidateValue(symbol_id="x", value_si=value),),
        query_symbol_id="x",
        query_value_si=value,
    )


def _candidate_set(
    plan: SolvePlan,
    *candidates: SolverCandidate,
    coverage: str = "exhaustive_symbolic",
    complete: bool = True,
) -> CandidateSet:
    return CandidateSet(
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        coverage=coverage,
        generation_complete=complete,
        generated_count=len(candidates),
        candidates=candidates,
        manifest=candidate_generation_manifest(candidates),
    )


def _diagnostics(
    plan: SolvePlan,
    *extra: SolverDiagnosticEntry,
) -> SolverDiagnostics:
    selected = SolverDiagnosticEntry(
        code=SolverDiagnosticCode.backend_selected,
        severity=DiagnosticSeverity.info,
        phase="planning",
        backend=plan.primary_backend,
    )
    entries = tuple(sorted((selected, *extra), key=diagnostic_entry_sort_key))
    return SolverDiagnostics(entries=entries, total_elapsed_s=0.01)


def _outcome_check(result: object, kind: str):
    return next(
        item
        for item in result.verification_outcomes[0].checks
        if item.kind.value == kind
    )


def test_typed_evaluator_covers_scalar_vector_piecewise_and_relations() -> None:
    expression = Add(terms=(
        Multiply(factors=(LiteralNode(value=2.0), SymbolRef(symbol_id="x"))),
        LiteralNode(value=1.0),
    ))
    assert evaluate_expression(expression, {"x": 3.0}).value == 7.0
    vector = evaluate_expression(
        VectorNode(items=(SymbolRef(symbol_id="x"), LiteralNode(value=4.0))),
        {"x": 3.0},
    )
    assert vector.value == (3.0, 4.0)
    piecewise = Piecewise(
        branches=(PiecewiseBranch(
            condition=Inequality(
                relation="ge",
                left=SymbolRef(symbol_id="x"),
                right=LiteralNode(value=0.0),
            ),
            value=SymbolRef(symbol_id="x"),
        ),),
        otherwise=LiteralNode(value=0.0),
    )
    assert evaluate_expression(piecewise, {"x": -2.0}).value == 0.0
    relation = evaluate_relation(
        Equality(left=SymbolRef(symbol_id="x"), right=LiteralNode(value=3.0)),
        {"x": 3.0},
    )
    assert relation.status is EvaluationStatus.ok and relation.satisfied
    assert relation.measured_error == 0.0


@pytest.mark.parametrize(
    ("expression", "error"),
    [
        (
            Divide(
                numerator=LiteralNode(value=1.0),
                denominator=SymbolRef(symbol_id="x"),
            ),
            EvaluationErrorCode.domain_error,
        ),
        (Sqrt(operand=SymbolRef(symbol_id="x")), EvaluationErrorCode.domain_error),
    ],
)
def test_evaluator_closes_denominator_and_square_root_domains(
    expression: object,
    error: EvaluationErrorCode,
) -> None:
    result = evaluate_expression(expression, {"x": 0.0 if isinstance(expression, Divide) else -1.0})
    assert result.status is EvaluationStatus.error
    assert result.error is error


def test_evaluator_never_asserts_calculus_or_missing_trajectory() -> None:
    derivative = Derivative(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="t")
    result = evaluate_expression(derivative, {"x": 2.0, "t": 0.0})
    assert result.status is EvaluationStatus.inconclusive
    assert result.error is EvaluationErrorCode.unsupported_trajectory
    missing = evaluate_expression(SymbolRef(symbol_id="missing"), {})
    assert missing.error is EvaluationErrorCode.missing_symbol


def test_linear_candidate_is_independently_solved_with_canonical_checks() -> None:
    plan = _plan(_graph())
    candidate = _candidate(plan, 2.0)
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, candidate),
        _diagnostics(plan),
    )
    assert result.terminal.value == "solved"
    assert result.selected_candidate_id == candidate.candidate_id
    outcome = result.verification_outcomes[0]
    assert outcome.passed
    assert tuple(item.check_id for item in outcome.checks) == tuple(sorted(
        item.check_id for item in outcome.checks
    ))
    assert {item.kind.value for item in outcome.checks} == {
        "equation_residual", "query_binding", "unit_consistency",
    }


def test_polynomial_physical_filter_leaves_one_exact_root() -> None:
    graph = _graph(
        selected_expression=Equality(
            left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
            right=LiteralNode(value=4.0),
        ),
        x_role="length",
    )
    plan = _plan(graph)
    negative = _candidate(plan, -2.0, generation_index=0, root_index=0)
    positive = _candidate(plan, 2.0, generation_index=1, root_index=1)
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, negative, positive),
        _diagnostics(plan),
    )
    assert result.terminal.value == "solved"
    assert result.selected_candidate_id == positive.candidate_id
    assert [item.candidate_id for item in result.verification_outcomes] == [
        negative.candidate_id, positive.candidate_id,
    ]
    assert result.verification_outcomes[0].rejections[0].reason.value == "positive_parameter_violation"


def test_two_valid_exact_polynomial_roots_are_ambiguity_without_selection() -> None:
    graph = _graph(selected_expression=Equality(
        left=Power(base=SymbolRef(symbol_id="x"), exponent=LiteralNode(value=2.0)),
        right=LiteralNode(value=4.0),
    ))
    plan = _plan(graph)
    candidates = (
        _candidate(plan, -2.0, generation_index=0, root_index=0),
        _candidate(plan, 2.0, generation_index=1, root_index=1),
    )
    result = verify_solver_candidates(plan, _candidate_set(plan, *candidates), _diagnostics(plan))
    assert result.terminal.value == "ambiguity"
    assert result.selected_candidate_id is None
    assert len(result.verified_candidates) == 2


def test_bounded_numeric_candidate_requires_confirmation_and_cannot_select() -> None:
    plan = _plan(_graph(selected_expression=Equality(
        left=Sqrt(operand=SymbolRef(symbol_id="x")),
        right=SymbolRef(symbol_id="g"),
    )))
    assert plan.permitted_numeric_fallback is SolveBackendKind.numeric_root
    candidate = _candidate(
        plan,
        4.0,
        backend=SolveBackendKind.numeric_root,
        approximate=True,
    )
    fallback = SolverDiagnosticEntry(
        code="numeric_fallback_used",
        severity="warning",
        phase="numeric",
        backend="numeric_root",
    )
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, candidate, coverage="bounded_numeric"),
        _diagnostics(plan, fallback),
    )
    assert result.terminal.value == "needs_confirmation"
    assert result.selected_candidate_id is None
    assert len(result.verified_candidates) == 1


def test_residual_inequality_and_constraint_failures_are_explicit() -> None:
    inequality = _equation(
        "ineq_nonnegative",
        Inequality(
            relation="ge",
            left=SymbolRef(symbol_id="x"),
            right=LiteralNode(value=0.0),
        ),
        constraints=("constraint_nonnegative",),
    )
    constraint = ConstraintNode(
        constraint_id="constraint_nonnegative",
        constraint_kind="nonnegative",
        equation_id="ineq_nonnegative",
        scope=EquationScope(),
    )
    plan = _plan(_graph(
        g_value=-2.0,
        extra_equations=(inequality,),
        constraints=(constraint,),
    ))
    candidate = _candidate(plan, -2.0)
    result = verify_solver_candidates(plan, _candidate_set(plan, candidate), _diagnostics(plan))
    outcome = result.verification_outcomes[0]
    reasons = {item.reason.value for item in outcome.rejections}
    assert {"inequality_violation", "constraint_violation"} <= reasons
    assert _outcome_check(result, "equation_residual").status.value == "passed"


@pytest.mark.parametrize(
    ("role", "value", "kind", "reason"),
    [
        ("time", -1.0, "nonnegative_time", "nonnegative_time_violation"),
        ("duration", -1.0, "nonnegative_time", "nonnegative_time_violation"),
        ("mass", 0.0, "positive_parameter", "positive_parameter_violation"),
        ("radius", 0.0, "positive_parameter", "positive_parameter_violation"),
        ("length", -1.0, "positive_parameter", "positive_parameter_violation"),
    ],
)
def test_physical_scalar_domains_are_exact(
    role: str,
    value: float,
    kind: str,
    reason: str,
) -> None:
    plan = _plan(_graph(x_role=role, g_value=value))
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, _candidate(plan, value)),
        _diagnostics(plan),
    )
    check = _outcome_check(result, kind)
    assert check.status.value == "failed"
    assert next(item for item in result.rejections if item.check_id == check.check_id).reason.value == reason


def test_missing_selected_equation_evidence_fails_source_check() -> None:
    evidenced = _equation(
        "ineq_evidenced",
        Inequality(
            relation="ge",
            left=SymbolRef(symbol_id="x"),
            right=LiteralNode(value=0.0),
        ),
        sources=("evidence_external",),
    )
    graph = _graph(extra_equations=(evidenced,))
    graph = graph.model_copy(update={"applications": (
        LawApplication(
            application_id="application_selected",
            law_id="generic_law",
            equation_ids=("eq_selected",),
            scope=EquationScope(),
            complexity_cost=8,
        ),
        LawApplication(
            application_id="application_evidenced",
            law_id="generic_law",
            equation_ids=("ineq_evidenced",),
            scope=EquationScope(),
            source_evidence_ids=("evidence_external",),
            complexity_cost=8,
        ),
    )})
    plan = _plan(graph)
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, _candidate(plan, 2.0)),
        _diagnostics(plan),
    )
    assert _outcome_check(result, "source_evidence").status.value == "failed"
    assert any(item.reason.value == "source_evidence_mismatch" for item in result.rejections)


def test_event_order_is_inconclusive_without_typed_event_times() -> None:
    scope = EquationScope(event_id="event_a", event_ids=("event_a",))
    plan = _plan(_graph(selected_scope=scope))
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, _candidate(plan, 2.0)),
        _diagnostics(plan),
    )
    check = _outcome_check(result, "event_order")
    assert check.status.value == "inconclusive"
    assert next(item for item in result.rejections if item.check_id == check.check_id).reason.value == "verification_inconclusive"


@pytest.mark.parametrize(("second_time", "expected"), [(2.0, "passed"), (-1.0, "failed")])
def test_event_time_predicate_provides_independent_order_evidence(
    second_time: float,
    expected: str,
) -> None:
    t1 = _symbol("t1", known=0.0, role="time", dimension=TIME, event_id="event_a")
    t2 = _symbol("t2", known=second_time, role="time", dimension=TIME, event_id="event_b")
    ordering = _equation(
        "ineq_event_order",
        Inequality(
            relation="le",
            left=SymbolRef(symbol_id="t1"),
            right=SymbolRef(symbol_id="t2"),
        ),
        scope=EquationScope(event_ids=("event_a", "event_b")),
        dimension=TIME,
    )
    plan = _plan(_graph(extra_symbols=(t1, t2), extra_equations=(ordering,)))
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, _candidate(plan, 2.0)),
        _diagnostics(plan),
    )
    assert _outcome_check(result, "event_order").status.value == expected


def _initial_plan() -> SolvePlan:
    x = _symbol("x", known=None, role="position", subject_id="body")
    x0 = _symbol("x0", known=2.0, role="position", event_id="event_initial", subject_id="body")
    t = _symbol("t", known=0.0, role="time", dimension=TIME, subject_id="body")
    selected = _equation(
        "eq_selected",
        Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="x0")),
        sources=("evidence_initial",),
    )
    condition = InitialConditionNode(
        condition_id="condition_initial",
        target_symbol_id="x",
        value_symbol_id="x0",
        wrt_symbol_id="t",
        derivative_order=0,
        scope=EquationScope(
            entity_ids=("body",),
            event_id="event_initial",
            event_ids=("event_initial",),
        ),
        source_quantity_ids=("quantity_x0",),
        source_evidence_ids=("evidence_initial",),
        source_state_condition_ids=("state_initial",),
    )
    graph = EquationGraph(
        query_id="query_x",
        query_symbol_id="x",
        symbols=(t, x, x0),
        equations=(selected,),
        constraints=(),
        initial_conditions=(condition,),
        applications=(LawApplication(
            application_id="application_main",
            law_id="kinematics",
            equation_ids=("eq_selected",),
            scope=EquationScope(),
            source_evidence_ids=("evidence_initial",),
            complexity_cost=8,
        ),),
        incidence=(IncidenceEdge(equation_id="eq_selected", symbol_id="x"),),
        rank=RankAnalysis(
            equality_count=1,
            inequality_count=0,
            unknown_count=1,
            structural_rank=1,
            underdetermined=False,
            overdetermined=False,
            conflicting=False,
        ),
        selected_equation_ids=("eq_selected",),
        fingerprint="c" * 64,
    )
    return _plan(graph)


@pytest.mark.parametrize(("value", "status"), [(2.0, "passed"), (3.0, "failed")])
def test_initial_condition_checks_exact_target_value_relation(value: float, status: str) -> None:
    plan = _initial_plan()
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, _candidate(plan, value)),
        _diagnostics(plan),
    )
    assert _outcome_check(result, "initial_boundary_condition").status.value == status


def test_physical_regime_requires_explicit_predicate_or_constraint() -> None:
    plan = _plan(_graph(application_law="friction_contact"))
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, _candidate(plan, 2.0)),
        _diagnostics(plan),
    )
    assert _outcome_check(result, "physical_regime").status.value == "inconclusive"


def test_conservation_and_alternative_equations_use_independent_residuals() -> None:
    alternative = _equation(
        "eq_alternative",
        Equality(left=SymbolRef(symbol_id="x"), right=LiteralNode(value=3.0)),
        law_id="system_momentum_conservation",
    )
    graph = _graph(
        extra_equations=(alternative,),
        application_law="system_momentum_conservation",
        alternative_sets=(("eq_alternative",),),
    )
    plan = _plan(graph)
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, _candidate(plan, 2.0)),
        _diagnostics(plan),
    )
    assert _outcome_check(result, "equation_residual").status.value == "passed"
    assert _outcome_check(result, "independent_equation_set").status.value == "failed"
    assert _outcome_check(result, "conserved_quantity").status.value == "failed"


def test_ode_residual_stays_inconclusive_without_typed_trajectory() -> None:
    t = _symbol("t", known=0.0, role="time", dimension=TIME)
    plan = _plan(_graph(
        selected_expression=Equality(
            left=Derivative(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="t"),
            right=SymbolRef(symbol_id="g"),
        ),
        extra_symbols=(t,),
    ))
    result = verify_solver_candidates(
        plan,
        _candidate_set(
            plan,
            _candidate(plan, 2.0, approximate=True),
            coverage="bounded_numeric",
        ),
        _diagnostics(plan),
    )
    assert _outcome_check(result, "equation_residual").status.value == "inconclusive"
    assert _outcome_check(result, "numerical_integration_residual").status.value == "inconclusive"
    assert result.terminal.value == "insufficient_conditions"


@pytest.mark.parametrize(
    ("code", "terminal"),
    [
        (SolverDiagnosticCode.backend_failure, "solver_error"),
        (SolverDiagnosticCode.backend_unsupported, "unsupported"),
        (SolverDiagnosticCode.resource_limit, "resource_limit"),
    ],
)
def test_failure_diagnostics_omit_all_partial_passing_outputs(
    code: SolverDiagnosticCode,
    terminal: str,
) -> None:
    plan = _plan(_graph())
    candidate = _candidate(plan, 2.0)
    incomplete = SolverDiagnosticEntry(
        code="generation_incomplete",
        severity="warning",
        phase="candidate_generation",
        backend=plan.primary_backend,
    )
    failure = SolverDiagnosticEntry(
        code=code,
        severity="error",
        phase="symbolic",
        backend=plan.primary_backend,
    )
    result = verify_solver_candidates(
        plan,
        _candidate_set(plan, candidate, coverage="incomplete", complete=False),
        _diagnostics(plan, failure, incomplete),
    )
    assert result.terminal.value == terminal
    assert not result.verification_outcomes
    assert not result.verified_candidates
    assert not result.rejections
    assert result.selected_candidate_id is None


def test_verifier_sources_have_no_dynamic_expression_or_answer_authority_path() -> None:
    modules = (
        Path(inspect.getsourcefile(evaluate_expression) or ""),
        Path(inspect.getsourcefile(verify_solver_candidates) or ""),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in modules)
    forbidden = (
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\bcompile\s*\(",
        r"\bsympify\b",
        r"\bparse_expr\b",
        r"\blambdify\b",
        r"raw_text",
        r"expected_answer",
        r"legacy_solver",
    )
    assert not [pattern for pattern in forbidden if re.search(pattern, source, re.IGNORECASE)]
    assert math.isfinite(verify_solver_candidates.__code__.co_firstlineno)
