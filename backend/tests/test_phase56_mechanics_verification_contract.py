from __future__ import annotations

import pytest
from pydantic import ValidationError

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
    Derivative,
    DimensionVector,
    Equality,
    Inequality,
    LiteralNode,
    SymbolDefinition,
    SymbolRef,
    Sqrt,
)
from engine.mechanics.solver import (
    CandidateRejection,
    CandidateSet,
    CandidateValue,
    GraphStructureFeatures,
    SolvePlan,
    SolverAttempt,
    SolverBudget,
    SolverCandidate,
    SolverDiagnosticEntry,
    SolverDiagnostics,
    SolverTimeout,
    candidate_generation_manifest,
    make_solver_candidate,
)
from engine.mechanics.verification import (
    EvidenceAdapterV2,
    EvidenceOutput,
    EvidenceSubstitution,
    MechanicsSolveResult,
    VerificationCheck,
    VerificationOutcome,
    VerifiedCandidate,
    render_canonical_si_unit,
)


GRAPH = "a" * 64
DIMENSIONLESS = DimensionVector()
SCOPE = EquationScope(event_id="event1", event_ids=("event1",))


def _graph(**changes: object) -> EquationGraph:
    x = SymbolNode(
        symbol=SymbolDefinition(symbol_id="x", quantity_id="quantityX", dimension=DIMENSIONLESS),
        quantity_id="quantityX", quantity_role="position", known_si_value=None,
    )
    g = SymbolNode(
        symbol=SymbolDefinition(symbol_id="g", quantity_id="quantityG", dimension=DIMENSIONLESS),
        quantity_id="quantityG", quantity_role="parameter", known_si_value=2.0,
    )
    equality = EquationNode(
        equation_id="eq1",
        expression=Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="g")),
        expression_fingerprint="b" * 64, law_id="law1", scope=SCOPE,
        source_evidence_ids=("evidence1",), constraint_ids=("constraint1",),
        dimension=DIMENSIONLESS, complexity_cost=3,
    )
    inequality = EquationNode(
        equation_id="ineq1",
        expression=Inequality(relation="ge", left=SymbolRef(symbol_id="x"), right=LiteralNode(value=0.0)),
        expression_fingerprint="c" * 64, law_id="law1", scope=SCOPE,
        source_evidence_ids=("evidence1",), constraint_ids=("constraint1",),
        dimension=DIMENSIONLESS, complexity_cost=3,
    )
    data: dict[str, object] = {
        "query_id": "query1",
        "query_symbol_id": "x",
        "symbols": (g, x),
        "equations": (equality, inequality),
        "constraints": (
            ConstraintNode(
                constraint_id="constraint1", constraint_kind="nonnegative",
                equation_id="ineq1", scope=SCOPE,
                source_evidence_ids=("evidence1",),
            ),
        ),
        "applications": (
            LawApplication(
                application_id="application1", law_id="law1",
                equation_ids=("eq1", "ineq1"), scope=SCOPE,
                source_evidence_ids=("evidence1",),
                constraint_ids=("constraint1",), complexity_cost=6,
            ),
        ),
        "incidence": (IncidenceEdge(equation_id="eq1", symbol_id="x"),),
        "rank": RankAnalysis(
            equality_count=1, inequality_count=1, unknown_count=1,
            structural_rank=1, underdetermined=False, overdetermined=False,
            conflicting=False,
        ),
        "selected_equation_ids": ("eq1",),
        "fingerprint": GRAPH,
    }
    data.update(changes)
    return EquationGraph(**data)


def _structure(**changes: object) -> GraphStructureFeatures:
    data: dict[str, object] = {
        "equality_count": 1,
        "inequality_count": 1,
        "constraint_count": 1,
        "initial_condition_count": 0,
        "unknown_count": 1,
        "max_ast_nodes_per_equation": 3,
        "total_ast_nodes": 6,
        "max_ast_depth": 2,
        "total_operation_cost": 6,
        "polynomial_degree": 1,
        "has_event_condition": True,
    }
    data.update(changes)
    return GraphStructureFeatures(**data)


def _plan(**changes: object) -> SolvePlan:
    data: dict[str, object] = {
        "graph": _graph(),
        "query_id": "query1",
        "query_symbol_id": "x",
        "selected_equality_ids": ("eq1",),
        "inequality_ids": ("ineq1",),
        "constraint_ids": ("constraint1",),
        "event_ids": ("event1",),
        "allowed_source_evidence_ids": ("evidence1",),
        "unknown_symbol_ids": ("x",),
        "known_symbol_ids": ("g",),
        "structure": _structure(),
        "primary_backend": "linear_symbolic",
        "budget": SolverBudget(),
    }
    data.update(changes)
    return SolvePlan(**data)


def _nonlinear_plan(**changes: object) -> SolvePlan:
    base = _graph()
    nonlinear = base.equations[0].model_copy(update={
        "expression": Equality(
            left=Sqrt(operand=SymbolRef(symbol_id="x")),
            right=SymbolRef(symbol_id="g"),
        ),
        "expression_fingerprint": "d" * 64,
    })
    graph = _graph(equations=(nonlinear, base.equations[1]))
    data: dict[str, object] = {
        "graph": graph,
        "structure": _structure().model_copy(update={
            "max_ast_nodes_per_equation": 4,
            "total_ast_nodes": 7,
            "max_ast_depth": 3,
            "polynomial_degree": None,
            "has_nonlinear_operation": True,
        }),
        "primary_backend": "nonlinear_symbolic",
        "permitted_numeric_fallback": "numeric_root",
    }
    data.update(changes)
    return _plan(**data)


def _ode_plan(**changes: object) -> SolvePlan:
    base = _graph()
    time_symbol = SymbolNode(
        symbol=SymbolDefinition(
            symbol_id="t", quantity_id="quantityT", dimension=DimensionVector(time=1),
        ),
        quantity_id="quantityT", quantity_role="time", known_si_value=0.0,
    )
    ode = base.equations[0].model_copy(update={
        "expression": Equality(
            left=Derivative(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="t"),
            right=SymbolRef(symbol_id="g"),
        ),
        "expression_fingerprint": "e" * 64,
    })
    graph = _graph(
        symbols=(base.symbols[0], time_symbol, base.symbols[1]),
        equations=(ode, base.equations[1]),
    )
    data: dict[str, object] = {
        "graph": graph,
        "known_symbol_ids": ("g", "t"),
        "structure": _structure().model_copy(update={
            "max_ast_nodes_per_equation": 4,
            "total_ast_nodes": 7,
            "max_ast_depth": 3,
            "has_derivative": True,
        }),
        "primary_backend": "ode_ivp",
    }
    data.update(changes)
    return _plan(**data)


def _positive_plan() -> SolvePlan:
    base = _graph()
    graph = _graph(symbols=(
        base.symbols[0],
        base.symbols[1].model_copy(update={"quantity_role": "mass"}),
    ))
    return _plan(graph=graph)


def _known_positive_plan() -> SolvePlan:
    base = _graph()
    graph = _graph(symbols=(
        base.symbols[0].model_copy(update={"quantity_role": "radius"}),
        base.symbols[1],
    ))
    return _plan(graph=graph)


def _physical_plan() -> SolvePlan:
    base = _graph()
    application = base.applications[0].model_copy(update={"law_id": "friction_contact"})
    return _plan(graph=_graph(applications=(application,)))


def _conservation_plan() -> SolvePlan:
    base = _graph()
    application = base.applications[0].model_copy(update={"law_id": "system_momentum_conservation"})
    return _plan(graph=_graph(applications=(application,)))


def _initial_plan() -> SolvePlan:
    base = _graph()
    x = SymbolNode(
        symbol=SymbolDefinition(symbol_id="x", quantity_id="quantityX", dimension=DIMENSIONLESS),
        quantity_id="quantityX", quantity_role="position", subject_id="body1", known_si_value=None,
    )
    x0 = SymbolNode(
        symbol=SymbolDefinition(symbol_id="x0", quantity_id="quantityX0", dimension=DIMENSIONLESS),
        quantity_id="quantityX0", quantity_role="position", subject_id="body1",
        event_id="eventIC", known_si_value=2.0,
    )
    time_symbol = SymbolNode(
        symbol=SymbolDefinition(
            symbol_id="t", quantity_id="quantityT", dimension=DimensionVector(time=1),
        ),
        quantity_id="quantityT", quantity_role="time", subject_id="body1", known_si_value=0.0,
    )
    condition = InitialConditionNode(
        condition_id="condition1",
        target_symbol_id="x",
        value_symbol_id="x0",
        wrt_symbol_id="t",
        derivative_order=0,
        scope=EquationScope(
            entity_ids=("body1",), event_id="eventIC", event_ids=("eventIC",),
        ),
        source_quantity_ids=("quantityX0",),
        source_evidence_ids=("evidenceIC",),
        source_state_condition_ids=("stateCondition1",),
    )
    graph = _graph(
        symbols=(base.symbols[0], time_symbol, x, x0),
        initial_conditions=(condition,),
    )
    return _plan(
        graph=graph,
        initial_condition_ids=("condition1",),
        event_ids=("event1", "eventIC"),
        allowed_source_evidence_ids=("evidence1", "evidenceIC"),
        known_symbol_ids=("g", "t", "x0"),
        structure=_structure(initial_condition_count=1),
    )


def _candidate(
    plan: SolvePlan,
    candidate_id: str = "candidate1",
    index: int = 0,
    *,
    backend: str | None = None,
    approximate: bool = False,
) -> SolverCandidate:
    del candidate_id
    return make_solver_candidate(
        generation_index=index, root_index=index,
        graph_fingerprint=plan.graph_fingerprint, plan_fingerprint=plan.plan_fingerprint,
        backend=backend or plan.primary_backend, approximate=approximate,
        equation_ids=("eq1",), values=(CandidateValue(symbol_id="x", value_si=2.0),),
        query_symbol_id="x", query_value_si=2.0,
    )


def _checks(candidate: SolverCandidate, *, fail_kind: str | None = None) -> tuple[VerificationCheck, ...]:
    specs: list[tuple[str, str, dict[str, tuple[str, ...]]]] = [
        ("check00", "equation_residual", {"equation_ids": ("eq1",)}),
        ("check01", "event_order", {"event_ids": ("event1",)}),
        ("check02", "constraint", {"constraint_ids": ("constraint1",)}),
        ("check03", "inequality", {"equation_ids": ("ineq1",)}),
        ("check04", "query_binding", {"symbol_ids": ("x",)}),
        ("check05", "source_evidence", {"source_evidence_ids": ("evidence1",)}),
        ("check06", "unit_consistency", {"symbol_ids": ("x",)}),
    ]
    if candidate.backend == "ode_ivp":
        specs.append(("check07", "numerical_integration_residual", {"equation_ids": ("eq1",)}))
        specs.append(("check08", "nonnegative_time", {"symbol_ids": ("t",)}))
    return tuple(
        VerificationCheck(
            check_id=check_id,
            kind=kind,
            status="failed" if kind == fail_kind else "passed",
            **provenance,
        )
        for check_id, kind, provenance in specs
    )


def _outcome(
    candidate: SolverCandidate,
    passed: bool = True,
    *,
    checks: tuple[VerificationCheck, ...] | None = None,
) -> VerificationOutcome:
    selected_checks = checks or _checks(candidate, fail_kind=None if passed else "equation_residual")
    rejections = tuple(
        CandidateRejection(
            candidate_id=candidate.candidate_id,
            reason="equation_residual" if check.kind.value == "equation_residual" else "verification_inconclusive",
            check_id=check.check_id,
            equation_ids=check.equation_ids,
            constraint_ids=check.constraint_ids,
            event_ids=check.event_ids,
            symbol_ids=check.symbol_ids,
            initial_condition_ids=check.initial_condition_ids,
            source_evidence_ids=check.source_evidence_ids,
        )
        for check in selected_checks
        if check.status.value != "passed"
    )
    return VerificationOutcome(
        candidate_id=candidate.candidate_id,
        graph_fingerprint=candidate.graph_fingerprint,
        plan_fingerprint=candidate.plan_fingerprint,
        passed=passed,
        checks=selected_checks,
        rejections=rejections,
    )


def _verified(candidate: SolverCandidate, outcome: VerificationOutcome | None = None) -> VerifiedCandidate:
    passing = outcome or _outcome(candidate)
    return VerifiedCandidate(candidate=candidate, outcome=passing, query_symbol_id="x", query_value_si=2.0)


def _set(
    plan: SolvePlan,
    *candidates: SolverCandidate,
    coverage: str = "exhaustive_symbolic",
    generation_complete: bool = True,
) -> CandidateSet:
    return CandidateSet(
        graph_fingerprint=plan.graph_fingerprint,
        plan_fingerprint=plan.plan_fingerprint,
        coverage=coverage,
        generation_complete=generation_complete,
        generated_count=len(candidates),
        candidates=candidates,
        manifest=candidate_generation_manifest(candidates),
    )


def _selected_entry(plan: SolvePlan) -> SolverDiagnosticEntry:
    return SolverDiagnosticEntry(
        code="backend_selected", severity="info", phase="planning",
        backend=plan.primary_backend,
    )


def _diagnostics(
    plan: SolvePlan,
    *extra: SolverDiagnosticEntry,
    attempts: tuple[SolverAttempt, ...] = (),
    timeout: SolverTimeout | None = None,
    total_elapsed_s: float = 0.1,
) -> SolverDiagnostics:
    return SolverDiagnostics(
        entries=(_selected_entry(plan), *extra),
        attempts=attempts,
        total_elapsed_s=total_elapsed_s,
        timeout=timeout,
    )


def _solved_result() -> MechanicsSolveResult:
    plan = _plan()
    candidate = _candidate(plan)
    outcome = _outcome(candidate)
    return MechanicsSolveResult(
        terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
        verification_outcomes=(outcome,), verified_candidates=(_verified(candidate, outcome),),
        selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
    )


def _evidence(result: MechanicsSolveResult, *, si_unit: str = "1", **changes: object) -> EvidenceAdapterV2:
    candidate = result.candidate_set.candidates[0]
    data: dict[str, object] = {
        "result": result,
        "candidate_id": candidate.candidate_id,
        "query_id": "query1",
        "equation_ids": ("eq1", "ineq1"),
        "source_evidence_ids": ("evidence1",),
        "substitutions": (EvidenceSubstitution(symbol_id="x", value_si=2.0),),
        "output": EvidenceOutput(query_symbol_id="x", value_si=2.0, si_unit=si_unit),
        "checks": result.verification_outcomes[0].checks,
    }
    data.update(changes)
    return EvidenceAdapterV2(**data)


def test_outcome_and_verified_candidate_require_exact_passing_binding() -> None:
    plan = _plan()
    candidate = _candidate(plan)
    failed_checks = _checks(candidate, fail_kind="unit_consistency")
    with pytest.raises(ValidationError):
        VerificationOutcome(
            candidate_id=candidate.candidate_id, graph_fingerprint=GRAPH,
            plan_fingerprint=plan.plan_fingerprint, passed=True,
            checks=failed_checks,
        )
    with pytest.raises(ValidationError):
        VerifiedCandidate(
            candidate=candidate,
            outcome=_outcome(candidate).model_copy(update={"graph_fingerprint": "c" * 64}),
            query_symbol_id="x", query_value_si=2.0,
        )
    with pytest.raises(ValidationError):
        VerifiedCandidate(candidate=candidate, outcome=_outcome(candidate), query_symbol_id="x", query_value_si=3.0)


def test_solved_requires_exactly_one_retained_verified_auto_selectable_candidate() -> None:
    result = _solved_result()
    assert result.selected_candidate_id == result.candidate_set.candidates[0].candidate_id
    candidate = result.candidate_set.candidates[0]
    with pytest.raises(ValidationError):
        MechanicsSolveResult(
            terminal="solved", plan=result.plan,
            candidate_set=_set(result.plan, candidate, coverage="bounded_numeric"),
            verification_outcomes=result.verification_outcomes,
            verified_candidates=result.verified_candidates,
            selected_candidate_id=candidate.candidate_id, diagnostics=result.diagnostics,
        )
    with pytest.raises(ValidationError):
        MechanicsSolveResult(
            terminal="solved", plan=result.plan, candidate_set=_set(result.plan),
            selected_candidate_id=candidate.candidate_id, diagnostics=result.diagnostics,
        )


@pytest.mark.parametrize(
    "missing_kind",
    [
        "equation_residual",
        "event_order",
        "constraint",
        "inequality",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    ],
)
def test_answer_verdict_requires_graph_derived_check_kind_completeness(missing_kind: str) -> None:
    plan = _plan()
    candidate = _candidate(plan)
    incomplete_checks = tuple(item for item in _checks(candidate) if item.kind.value != missing_kind)
    outcome = _outcome(candidate, checks=incomplete_checks)
    with pytest.raises(ValidationError, match="missing graph-required"):
        MechanicsSolveResult(
            terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
            verification_outcomes=(outcome,), verified_candidates=(_verified(candidate, outcome),),
            selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
        )


def test_answer_verdict_requires_unique_check_kinds() -> None:
    plan = _plan()
    candidate = _candidate(plan)
    duplicate = (*_checks(candidate), VerificationCheck(check_id="check99", kind="unit_consistency", status="passed"))
    duplicate_outcome = _outcome(candidate, checks=duplicate)
    with pytest.raises(ValidationError, match="unique verification check kinds"):
        MechanicsSolveResult(
            terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
            verification_outcomes=(duplicate_outcome,),
            verified_candidates=(_verified(candidate, duplicate_outcome),),
            selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
        )


def test_ode_answer_requires_numerical_integration_residual_kind() -> None:
    plan = _ode_plan()
    candidate = _candidate(plan, backend="ode_ivp", approximate=True)
    checks = tuple(
        item for item in _checks(candidate)
        if item.kind.value != "numerical_integration_residual"
    )
    outcome = _outcome(candidate, checks=checks)
    with pytest.raises(ValidationError, match="missing graph-required"):
        MechanicsSolveResult(
            terminal="needs_confirmation", plan=plan,
            candidate_set=_set(plan, candidate, coverage="bounded_numeric"),
            verification_outcomes=(outcome,),
            verified_candidates=(_verified(candidate, outcome),),
            diagnostics=_diagnostics(plan),
        )


@pytest.mark.parametrize("backend", ["numeric_root", "ode_ivp"])
def test_approximate_candidates_cannot_solve_but_complete_outcomes_can_request_confirmation(backend: str) -> None:
    plan = _nonlinear_plan() if backend == "numeric_root" else _ode_plan()
    candidate = _candidate(plan, backend=backend, approximate=True)
    candidate_set = _set(plan, candidate, coverage="bounded_numeric")
    outcome = _outcome(candidate)
    verified = _verified(candidate, outcome)
    with pytest.raises(ValidationError, match="auto-select"):
        MechanicsSolveResult(
            terminal="solved", plan=plan, candidate_set=candidate_set,
            verification_outcomes=(outcome,), verified_candidates=(verified,),
            selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
        )
    extra = () if backend == "ode_ivp" else (
        SolverDiagnosticEntry(
            code="numeric_fallback_used", severity="warning", phase="numeric", backend="numeric_root",
        ),
    )
    confirmation = MechanicsSolveResult(
        terminal="needs_confirmation", plan=plan, candidate_set=candidate_set,
        verification_outcomes=(outcome,), verified_candidates=(verified,),
        diagnostics=_diagnostics(plan, *extra),
    )
    assert confirmation.selected_candidate_id is None
    with pytest.raises(ValidationError, match="exact retained candidate order"):
        MechanicsSolveResult(
            terminal="needs_confirmation", plan=plan, candidate_set=candidate_set,
            verified_candidates=(), diagnostics=_diagnostics(plan),
        )


def test_zero_or_multiple_verified_candidates_cannot_be_silently_selected() -> None:
    plan = _plan()
    one, two = _candidate(plan), _candidate(plan, "candidate2", 1)
    one_outcome, two_outcome = _outcome(one), _outcome(two)
    ambiguity = MechanicsSolveResult(
        terminal="ambiguity", plan=plan, candidate_set=_set(plan, one, two),
        verification_outcomes=(one_outcome, two_outcome),
        verified_candidates=(_verified(one, one_outcome), _verified(two, two_outcome)),
        diagnostics=_diagnostics(plan),
    )
    assert ambiguity.selected_candidate_id is None
    with pytest.raises(ValidationError):
        MechanicsSolveResult(
            terminal="ambiguity", plan=plan, candidate_set=_set(plan, one, two),
            verification_outcomes=(one_outcome, two_outcome),
            verified_candidates=(_verified(one, one_outcome), _verified(two, two_outcome)),
            selected_candidate_id=one.candidate_id, diagnostics=_diagnostics(plan),
        )


def test_early_candidate_deletion_and_missing_references_fail_closed() -> None:
    plan = _plan()
    candidate = _candidate(plan)
    with pytest.raises(ValidationError):
        MechanicsSolveResult(
            terminal="ambiguity", plan=plan, candidate_set=_set(plan),
            verification_outcomes=(_outcome(candidate),),
            verified_candidates=(_verified(candidate),), diagnostics=_diagnostics(plan),
        )


def test_timeout_never_permits_partial_answer_and_backend_is_authorized() -> None:
    plan = _nonlinear_plan()
    candidate = _candidate(plan, backend="numeric_root", approximate=True)
    candidate_set = _set(plan, candidate, coverage="incomplete", generation_complete=False)
    timeout = SolverTimeout(phase="numeric", backend="numeric_root", limit_s=10.0, elapsed_s=10.1)
    timeout_entry = SolverDiagnosticEntry(code="timeout", severity="error", phase="numeric", backend="numeric_root")
    incomplete_entry = SolverDiagnosticEntry(
        code="generation_incomplete", severity="warning", phase="candidate_generation", backend="numeric_root",
    )
    fallback_entry = SolverDiagnosticEntry(
        code="numeric_fallback_used", severity="warning", phase="numeric", backend="numeric_root",
    )
    diagnostics = _diagnostics(
        plan, fallback_entry, timeout_entry, incomplete_entry,
        attempts=(
            SolverAttempt(
                attempt_index=0, backend="numeric_root", phase="numeric",
                elapsed_s=10.1, completed=False,
            ),
        ),
        timeout=timeout, total_elapsed_s=10.1,
    )
    with pytest.raises(ValidationError):
        MechanicsSolveResult(
            terminal="timeout", plan=plan, candidate_set=candidate_set,
            selected_candidate_id=candidate.candidate_id, diagnostics=diagnostics,
        )
    assert MechanicsSolveResult(
        terminal="timeout", plan=plan, candidate_set=candidate_set,
        diagnostics=diagnostics,
    ).selected_candidate_id is None

    unauthorized = SolverTimeout(phase="numeric", backend="event_root", limit_s=10.0, elapsed_s=10.1)
    bad_diagnostics = SolverDiagnostics(
        entries=(
            _selected_entry(plan),
            SolverDiagnosticEntry(code="timeout", severity="error", phase="numeric", backend="event_root"),
        ),
        attempts=(
            SolverAttempt(
                attempt_index=0, backend="event_root", phase="numeric",
                elapsed_s=10.1, completed=False,
            ),
        ),
        total_elapsed_s=10.1, timeout=unauthorized,
    )
    with pytest.raises(ValidationError, match="not authorized"):
        MechanicsSolveResult(terminal="timeout", plan=plan, candidate_set=candidate_set, diagnostics=bad_diagnostics)


@pytest.mark.parametrize("location", ["entry", "attempt"])
def test_result_rejects_unpermitted_diagnostic_and_attempt_backends(location: str) -> None:
    plan = _plan()
    candidate_set = _set(plan)
    extra: tuple[SolverDiagnosticEntry, ...] = ()
    attempts: tuple[SolverAttempt, ...] = ()
    if location == "entry":
        extra = (SolverDiagnosticEntry(code="generation_incomplete", severity="warning", phase="candidate_generation", backend="event_root"),)
    else:
        attempts = (SolverAttempt(attempt_index=0, backend="event_root", phase="numeric", elapsed_s=0.1, completed=True),)
    diagnostics = _diagnostics(plan, *extra, attempts=attempts)
    with pytest.raises(ValidationError, match="not authorized"):
        MechanicsSolveResult(
            terminal="insufficient_conditions", plan=plan,
            candidate_set=candidate_set, diagnostics=diagnostics,
        )


@pytest.mark.parametrize(
    ("update", "expected_fragment"),
    [
        ({"query_symbol_id": "y", "query_value_si": 3.0, "values": (CandidateValue(symbol_id="y", value_si=3.0),)}, "query"),
        ({"backend": "polynomial_symbolic"}, "backend"),
        ({"equation_ids": ("ineq1",)}, "equations"),
        ({"values": (CandidateValue(symbol_id="x", value_si=2.0), CandidateValue(symbol_id="z", value_si=4.0))}, "unknown"),
    ],
    )
def test_result_rejects_candidate_not_exactly_bound_to_plan(update: dict[str, object], expected_fragment: str) -> None:
    plan = _plan()
    candidate_data = _candidate(plan).model_dump(exclude={"candidate_id"})
    candidate_data.update(update)
    candidate = make_solver_candidate(**candidate_data)
    candidate_set = _set(plan, candidate)
    failed = _outcome(candidate, passed=False)
    with pytest.raises(ValidationError, match=expected_fragment):
        MechanicsSolveResult(
            terminal="insufficient_conditions", plan=plan, candidate_set=candidate_set,
            verification_outcomes=(failed,), rejections=failed.rejections,
            diagnostics=_diagnostics(plan),
        )


@pytest.mark.parametrize(
    ("field", "bad_id", "fragment"),
    [
        ("equation_ids", "eq999", "equation outside"),
        ("constraint_ids", "constraint999", "constraint outside"),
        ("event_ids", "event999", "event outside"),
        ("symbol_ids", "symbol999", "symbol outside"),
        ("initial_condition_ids", "condition999", "initial condition outside"),
        ("source_evidence_ids", "evidence999", "evidence outside"),
    ],
)
def test_result_rejects_mutually_matching_outcome_provenance_outside_graph(field: str, bad_id: str, fragment: str) -> None:
    plan = _plan()
    candidate = _candidate(plan)
    checks = list(_checks(candidate))
    target = checks[0]
    checks[0] = target.model_copy(update={field: (bad_id,)})
    forged = _outcome(candidate, checks=tuple(checks))
    with pytest.raises(ValidationError, match=fragment):
        MechanicsSolveResult(
            terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
            verification_outcomes=(forged,), verified_candidates=(_verified(candidate, forged),),
            selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
        )


def test_failed_and_inconclusive_checks_require_rejections_and_canonical_order() -> None:
    plan = _plan()
    candidate = _candidate(plan)
    failed = VerificationCheck(check_id="check01", kind="equation_residual", status="failed", equation_ids=("eq1",))
    inconclusive = VerificationCheck(check_id="check02", kind="query_binding", status="inconclusive")
    with pytest.raises(ValidationError, match="non-passing"):
        VerificationOutcome(
            candidate_id=candidate.candidate_id, graph_fingerprint=GRAPH,
            plan_fingerprint=plan.plan_fingerprint, passed=False,
            checks=(failed, inconclusive), rejections=(),
        )
    first = CandidateRejection(candidate_id=candidate.candidate_id, reason="equation_residual", check_id="check01", equation_ids=("eq1",))
    second = CandidateRejection(candidate_id=candidate.candidate_id, reason="verification_inconclusive", check_id="check02")
    accepted = VerificationOutcome(
        candidate_id=candidate.candidate_id, graph_fingerprint=GRAPH,
        plan_fingerprint=plan.plan_fingerprint, passed=False,
        checks=(failed, inconclusive), rejections=(first, second),
    )
    assert accepted.rejections == (first, second)
    with pytest.raises(ValidationError, match="canonically ordered"):
        VerificationOutcome(
            candidate_id=candidate.candidate_id, graph_fingerprint=GRAPH,
            plan_fingerprint=plan.plan_fingerprint, passed=False,
            checks=(failed, inconclusive), rejections=(second, first),
        )
    with pytest.raises(ValidationError, match="canonical ascending"):
        VerificationOutcome(
            candidate_id=candidate.candidate_id, graph_fingerprint=GRAPH,
            plan_fingerprint=plan.plan_fingerprint, passed=False,
            checks=(inconclusive, failed), rejections=(first, second),
        )


def test_top_level_rejections_are_exact_and_cannot_reject_selected_candidate() -> None:
    result = _solved_result()
    forged = CandidateRejection(candidate_id=result.candidate_set.candidates[0].candidate_id, reason="query_unbound", check_id="nonexistent")
    with pytest.raises(ValidationError, match="aggregate"):
        MechanicsSolveResult(
            terminal="solved", plan=result.plan, candidate_set=result.candidate_set,
            verification_outcomes=result.verification_outcomes,
            verified_candidates=result.verified_candidates,
            rejections=(forged,), selected_candidate_id=result.candidate_set.candidates[0].candidate_id,
            diagnostics=result.diagnostics,
        )
    candidate = result.candidate_set.candidates[0]
    failed = _outcome(candidate, passed=False)
    closed = MechanicsSolveResult(
        terminal="insufficient_conditions", plan=result.plan,
        candidate_set=result.candidate_set, verification_outcomes=(failed,),
        rejections=failed.rejections, diagnostics=result.diagnostics,
    )
    assert closed.rejections == failed.rejections


def test_failure_terminal_codes_are_bidirectional_and_contradictions_reject() -> None:
    plan = _plan()
    empty = _set(plan, coverage="incomplete", generation_complete=False)
    incomplete = SolverDiagnosticEntry(
        code="generation_incomplete", severity="warning",
        phase="candidate_generation", backend="linear_symbolic",
    )
    for terminal, code in (
        ("resource_limit", "resource_limit"),
        ("unsupported", "backend_unsupported"),
        ("solver_error", "backend_failure"),
    ):
        with pytest.raises(ValidationError, match="matching closed"):
            MechanicsSolveResult(
                terminal=terminal, plan=plan, candidate_set=empty,
                diagnostics=_diagnostics(plan, incomplete),
            )
        entry = SolverDiagnosticEntry(code=code, severity="error", phase="candidate_generation", backend="linear_symbolic")
        assert MechanicsSolveResult(
            terminal=terminal, plan=plan, candidate_set=empty,
            diagnostics=_diagnostics(plan, incomplete, entry),
        ).selected_candidate_id is None

    timeout = SolverTimeout(phase="symbolic", backend="linear_symbolic", limit_s=5.0, elapsed_s=5.0)
    contradictory = SolverDiagnostics(
        entries=(
            _selected_entry(plan),
            SolverDiagnosticEntry(code="backend_failure", severity="error", phase="symbolic", backend="linear_symbolic"),
            SolverDiagnosticEntry(code="timeout", severity="error", phase="symbolic", backend="linear_symbolic"),
        ),
        attempts=(
            SolverAttempt(
                attempt_index=0, backend="linear_symbolic", phase="symbolic",
                elapsed_s=5.0, completed=False,
            ),
        ),
        total_elapsed_s=5.0, timeout=timeout,
    )
    with pytest.raises(ValidationError, match="contradictory"):
        MechanicsSolveResult(terminal="timeout", plan=plan, candidate_set=empty, diagnostics=contradictory)


def test_numeric_fallback_diagnostic_is_exact_and_bidirectional() -> None:
    plan = _nonlinear_plan()
    candidate = _candidate(plan, backend="numeric_root", approximate=True)
    candidate_set = _set(plan, candidate, coverage="bounded_numeric")
    outcome = _outcome(candidate)
    with pytest.raises(ValidationError, match="fallback"):
        MechanicsSolveResult(
            terminal="needs_confirmation", plan=plan, candidate_set=candidate_set,
            verification_outcomes=(outcome,), verified_candidates=(_verified(candidate, outcome),),
            diagnostics=_diagnostics(plan),
        )
    fallback = SolverDiagnosticEntry(
        code="numeric_fallback_used", severity="warning", phase="numeric", backend="numeric_root",
    )
    assert MechanicsSolveResult(
        terminal="needs_confirmation", plan=plan, candidate_set=candidate_set,
        verification_outcomes=(outcome,), verified_candidates=(_verified(candidate, outcome),),
        diagnostics=_diagnostics(plan, fallback),
    ).selected_candidate_id is None


def test_incomplete_generation_has_one_fail_closed_terminal_rule() -> None:
    plan = _plan()
    incomplete_entry = SolverDiagnosticEntry(
        code="generation_incomplete", severity="warning",
        phase="candidate_generation", backend="linear_symbolic",
    )
    empty = _set(plan, coverage="incomplete", generation_complete=False)
    assert MechanicsSolveResult(
        terminal="insufficient_conditions", plan=plan, candidate_set=empty,
        diagnostics=_diagnostics(plan, incomplete_entry),
    ).terminal.value == "insufficient_conditions"
    candidate = _candidate(plan)
    candidate_set = _set(plan, candidate, coverage="incomplete", generation_complete=False)
    outcome = _outcome(candidate)
    confirmation = MechanicsSolveResult(
        terminal="needs_confirmation", plan=plan, candidate_set=candidate_set,
        verification_outcomes=(outcome,), verified_candidates=(_verified(candidate, outcome),),
        diagnostics=_diagnostics(plan, incomplete_entry),
    )
    assert confirmation.selected_candidate_id is None


def test_candidate_limit_closes_as_resource_limit() -> None:
    plan = _plan(budget=SolverBudget(max_candidates=1))
    candidate = _candidate(plan)
    limited = _set(plan, candidate, coverage="incomplete", generation_complete=False)
    limit_entry = SolverDiagnosticEntry(
        code="candidate_limit_reached", severity="error",
        phase="candidate_generation", backend="linear_symbolic",
    )
    result = MechanicsSolveResult(
        terminal="resource_limit", plan=plan, candidate_set=limited,
        diagnostics=_diagnostics(plan, limit_entry),
    )
    assert result.terminal.value == "resource_limit"


def test_evidence_adapter_requires_the_concrete_unique_solved_selection() -> None:
    result = _solved_result()
    evidence = EvidenceAdapterV2(
        result=result, candidate_id=result.candidate_set.candidates[0].candidate_id, query_id="query1",
        equation_ids=("eq1", "ineq1"), source_evidence_ids=("evidence1",),
        substitutions=(EvidenceSubstitution(symbol_id="x", value_si=2.0),),
        output=EvidenceOutput(query_symbol_id="x", value_si=2.0, si_unit="1"),
        checks=result.verification_outcomes[0].checks,
    )
    assert evidence.graph_fingerprint == result.plan.graph_fingerprint
    assert evidence.plan_fingerprint == result.plan.plan_fingerprint
    with pytest.raises(ValidationError):
        evidence.candidate_id = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        EvidenceAdapterV2(**{**evidence.model_dump(), "legacy_solver": object()})

    plan = _plan()
    one, two = _candidate(plan), _candidate(plan, "candidate2", 1)
    one_outcome, two_outcome = _outcome(one), _outcome(two)
    ambiguous = MechanicsSolveResult(
        terminal="ambiguity", plan=plan, candidate_set=_set(plan, one, two),
        verification_outcomes=(one_outcome, two_outcome),
        verified_candidates=(_verified(one, one_outcome), _verified(two, two_outcome)),
        diagnostics=_diagnostics(plan),
    )
    with pytest.raises(ValidationError, match="solved selection"):
        EvidenceAdapterV2(
            result=ambiguous, candidate_id=one.candidate_id, query_id="query1",
            equation_ids=("eq1", "ineq1"), source_evidence_ids=("evidence1",),
            substitutions=(EvidenceSubstitution(symbol_id="x", value_si=2.0),),
            output=EvidenceOutput(query_symbol_id="x", value_si=2.0, si_unit="1"),
            checks=one_outcome.checks,
        )


@pytest.mark.parametrize(
    ("field", "bad_id"),
    [
        ("equation_ids", "eq999"),
        ("constraint_ids", "constraint999"),
        ("event_ids", "event999"),
        ("source_evidence_ids", "evidence999"),
    ],
)
def test_adapter_revalidates_forged_nested_result_even_when_payload_matches(field: str, bad_id: str) -> None:
    result = _solved_result()
    candidate = result.candidate_set.candidates[0]
    checks = list(result.verification_outcomes[0].checks)
    checks[0] = checks[0].model_copy(update={field: (bad_id,)})
    forged_outcome = result.verification_outcomes[0].model_copy(update={"checks": tuple(checks)})
    forged_verified = result.verified_candidates[0].model_copy(update={"outcome": forged_outcome})
    forged_result = result.model_copy(update={
        "verification_outcomes": (forged_outcome,),
        "verified_candidates": (forged_verified,),
    })
    with pytest.raises(ValidationError):
        EvidenceAdapterV2(
            result=forged_result, candidate_id=candidate.candidate_id, query_id="query1",
            equation_ids=tuple(sorted({"eq1", "ineq1", bad_id})) if field == "equation_ids" else ("eq1", "ineq1"),
            source_evidence_ids=("evidence1", bad_id) if field == "source_evidence_ids" else ("evidence1",),
            substitutions=(EvidenceSubstitution(symbol_id="x", value_si=2.0),),
            output=EvidenceOutput(query_symbol_id="x", value_si=2.0, si_unit="1"),
            checks=tuple(checks),
        )


@pytest.mark.parametrize("case", ["positive", "known_positive", "physical", "conservation"])
def test_domain_physical_and_conservation_checks_are_required_with_exact_provenance(case: str) -> None:
    if case == "positive":
        plan = _positive_plan()
        extra = VerificationCheck(
            check_id="check07", kind="positive_parameter", status="passed", symbol_ids=("x",),
        )
    elif case == "known_positive":
        plan = _known_positive_plan()
        extra = VerificationCheck(
            check_id="check07", kind="positive_parameter", status="passed", symbol_ids=("g",),
        )
    elif case == "physical":
        plan = _physical_plan()
        extra = VerificationCheck(
            check_id="check07", kind="physical_regime", status="passed",
            equation_ids=("eq1", "ineq1"), constraint_ids=("constraint1",),
        )
    else:
        plan = _conservation_plan()
        extra = VerificationCheck(
            check_id="check07", kind="conserved_quantity", status="passed",
            equation_ids=("eq1", "ineq1"),
        )
    candidate = _candidate(plan)
    missing = _outcome(candidate, checks=_checks(candidate))
    with pytest.raises(ValidationError, match="missing graph-required"):
        MechanicsSolveResult(
            terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
            verification_outcomes=(missing,), verified_candidates=(_verified(candidate, missing),),
            selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
        )

    complete = _outcome(candidate, checks=(*_checks(candidate), extra))
    accepted = MechanicsSolveResult(
        terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
        verification_outcomes=(complete,), verified_candidates=(_verified(candidate, complete),),
        selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
    )
    assert accepted.terminal.value == "solved"


def test_initial_boundary_check_requires_exact_ids_events_symbols_and_evidence() -> None:
    plan = _initial_plan()
    candidate = _candidate(plan)
    adapted: list[VerificationCheck] = []
    for check in _checks(candidate):
        payload = check.model_dump()
        if check.kind.value == "event_order":
            payload["event_ids"] = ("event1", "eventIC")
        if check.kind.value == "source_evidence":
            payload["source_evidence_ids"] = ("evidence1", "evidenceIC")
        adapted.append(VerificationCheck.model_validate(payload))
    adapted.append(VerificationCheck(
        check_id="check07", kind="nonnegative_time", status="passed", symbol_ids=("t",),
    ))
    missing = _outcome(candidate, checks=tuple(adapted))
    with pytest.raises(ValidationError, match="missing graph-required"):
        MechanicsSolveResult(
            terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
            verification_outcomes=(missing,), verified_candidates=(_verified(candidate, missing),),
            selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
        )

    initial = VerificationCheck(
        check_id="check08",
        kind="initial_boundary_condition",
        status="passed",
        event_ids=("eventIC",),
        symbol_ids=("t", "x", "x0"),
        initial_condition_ids=("condition1",),
        source_evidence_ids=("evidenceIC",),
    )
    complete = _outcome(candidate, checks=(*adapted, initial))
    result = MechanicsSolveResult(
        terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
        verification_outcomes=(complete,), verified_candidates=(_verified(candidate, complete),),
        selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
    )
    assert result.terminal.value == "solved"

    wrong = initial.model_copy(update={"initial_condition_ids": ()})
    wrong_outcome = _outcome(candidate, checks=(*adapted, wrong))
    with pytest.raises(ValidationError, match="exactly match graph-derived"):
        MechanicsSolveResult(
            terminal="solved", plan=plan, candidate_set=_set(plan, candidate),
            verification_outcomes=(wrong_outcome,), verified_candidates=(_verified(candidate, wrong_outcome),),
            selected_candidate_id=candidate.candidate_id, diagnostics=_diagnostics(plan),
        )


def test_rejection_reason_is_deterministically_bound_to_check_kind_and_status() -> None:
    plan = _plan()
    candidate = _candidate(plan)
    failed = VerificationCheck(
        check_id="check01", kind="query_binding", status="failed", symbol_ids=("x",),
    )
    wrong = CandidateRejection(
        candidate_id=candidate.candidate_id,
        reason="equation_residual",
        check_id="check01",
        symbol_ids=("x",),
    )
    with pytest.raises(ValidationError, match="check kind and status"):
        VerificationOutcome(
            candidate_id=candidate.candidate_id,
            graph_fingerprint=plan.graph_fingerprint,
            plan_fingerprint=plan.plan_fingerprint,
            passed=False,
            checks=(failed,),
            rejections=(wrong,),
        )


def test_result_and_evidence_public_round_trip_preserves_fingerprints() -> None:
    result = _solved_result()
    assert MechanicsSolveResult.model_validate(result.model_dump()) == result
    assert MechanicsSolveResult.model_validate_json(result.model_dump_json()) == result

    evidence = _evidence(result)
    assert EvidenceAdapterV2.model_validate(evidence.model_dump()) == evidence
    assert EvidenceAdapterV2.model_validate_json(evidence.model_dump_json()) == evidence
    assert _evidence(
        result,
        graph_fingerprint=result.plan.graph_fingerprint,
        plan_fingerprint=result.plan.plan_fingerprint,
    ) == evidence
    with pytest.raises(ValidationError):
        _evidence(result, graph_fingerprint=None)
    with pytest.raises(ValidationError):
        _evidence(result, graph_fingerprint="0" * 64)
    with pytest.raises(ValidationError):
        _evidence(result, plan_fingerprint=None)
    with pytest.raises(ValidationError):
        _evidence(result, plan_fingerprint="0" * 64)


def test_evidence_unit_is_exact_graph_derived_si_authority() -> None:
    result = _solved_result()
    assert _evidence(result).output.si_unit == "1"
    with pytest.raises(ValidationError, match="graph-derived query dimension"):
        _evidence(result, si_unit="kg")
    assert render_canonical_si_unit(DimensionVector(mass=1, length=1, time=-2)) == "kg*m*s^-2"


def test_evidence_forbidden_field_test_starts_from_round_trippable_payload() -> None:
    evidence = _evidence(_solved_result())
    base = evidence.model_dump()
    assert EvidenceAdapterV2.model_validate(base) == evidence
    with pytest.raises(ValidationError):
        EvidenceAdapterV2.model_validate({**base, "legacy_solver": "forbidden"})


def test_verification_outcome_boolean_is_strict() -> None:
    candidate = _candidate(_plan())
    with pytest.raises(ValidationError):
        VerificationOutcome(
            candidate_id=candidate.candidate_id,
            graph_fingerprint=candidate.graph_fingerprint,
            plan_fingerprint=candidate.plan_fingerprint,
            passed="true",
            checks=_checks(candidate),
        )


def test_failure_terminal_rejects_passing_partial_answer_but_keeps_failed_records() -> None:
    plan = _plan()
    candidate = _candidate(plan)
    candidate_set = _set(plan, candidate)
    passing = _outcome(candidate)
    failure = SolverDiagnosticEntry(
        code="backend_failure", severity="error", phase="verification", backend="linear_symbolic",
    )
    diagnostics = _diagnostics(plan, failure)
    with pytest.raises(ValidationError, match="failure terminals"):
        MechanicsSolveResult(
            terminal="solver_error", plan=plan, candidate_set=candidate_set,
            verification_outcomes=(passing,), verified_candidates=(_verified(candidate, passing),),
            diagnostics=diagnostics,
        )

    failed = _outcome(candidate, passed=False)
    audit = MechanicsSolveResult(
        terminal="solver_error", plan=plan, candidate_set=candidate_set,
        verification_outcomes=(failed,), rejections=failed.rejections,
        diagnostics=diagnostics,
    )
    assert not audit.verified_candidates and audit.rejections


def test_timeout_and_attempt_timings_are_exactly_plan_bound() -> None:
    plan = _plan()
    incomplete = _set(plan, coverage="incomplete", generation_complete=False)
    timeout = SolverTimeout(
        phase="symbolic", backend="linear_symbolic", limit_s=1.0, elapsed_s=1.0,
    )
    diagnostics = _diagnostics(
        plan,
        SolverDiagnosticEntry(
            code="timeout", severity="error", phase="symbolic", backend="linear_symbolic",
        ),
        SolverDiagnosticEntry(
            code="generation_incomplete", severity="warning",
            phase="candidate_generation", backend="linear_symbolic",
        ),
        attempts=(
            SolverAttempt(
                attempt_index=0, backend="linear_symbolic", phase="symbolic",
                elapsed_s=1.0, completed=False,
            ),
        ),
        timeout=timeout,
        total_elapsed_s=1.0,
    )
    with pytest.raises(ValidationError, match="exactly match the plan"):
        MechanicsSolveResult(
            terminal="timeout", plan=plan, candidate_set=incomplete, diagnostics=diagnostics,
        )

    exact_timeout = SolverTimeout(
        phase="symbolic", backend="linear_symbolic", limit_s=5.0, elapsed_s=5.1,
    )
    exact_diagnostics = _diagnostics(
        plan,
        SolverDiagnosticEntry(
            code="timeout", severity="error", phase="symbolic", backend="linear_symbolic",
        ),
        SolverDiagnosticEntry(
            code="generation_incomplete", severity="warning",
            phase="candidate_generation", backend="linear_symbolic",
        ),
        attempts=(
            SolverAttempt(
                attempt_index=0, backend="linear_symbolic", phase="symbolic",
                elapsed_s=5.1, completed=False,
            ),
        ),
        timeout=exact_timeout,
        total_elapsed_s=5.1,
    )
    result = MechanicsSolveResult(
        terminal="timeout", plan=plan, candidate_set=incomplete, diagnostics=exact_diagnostics,
    )
    assert result.diagnostics.attempts[-1].elapsed_s == result.diagnostics.timeout.elapsed_s

    overflow_timeout = SolverTimeout(
        phase="symbolic", backend="linear_symbolic", limit_s=5.0, elapsed_s=999.0,
    )
    overflow_diagnostics = _diagnostics(
        plan,
        SolverDiagnosticEntry(
            code="timeout", severity="error", phase="symbolic", backend="linear_symbolic",
        ),
        SolverDiagnosticEntry(
            code="generation_incomplete", severity="warning",
            phase="candidate_generation", backend="linear_symbolic",
        ),
        attempts=(
            SolverAttempt(
                attempt_index=0, backend="linear_symbolic", phase="symbolic",
                elapsed_s=999.0, completed=False,
            ),
        ),
        timeout=overflow_timeout,
        total_elapsed_s=999.0,
    )
    with pytest.raises(ValidationError, match="termination grace"):
        MechanicsSolveResult(
            terminal="timeout", plan=plan, candidate_set=incomplete, diagnostics=overflow_diagnostics,
        )

    too_long = SolverAttempt(
        attempt_index=0, backend="linear_symbolic", phase="symbolic",
        elapsed_s=999.0, completed=True,
    )
    with pytest.raises(ValidationError, match="exact plan limit"):
        MechanicsSolveResult(
            terminal="insufficient_conditions", plan=plan, candidate_set=_set(plan),
            diagnostics=_diagnostics(plan, attempts=(too_long,), total_elapsed_s=999.0),
        )


def test_numeric_attempt_count_and_diagnostics_order_are_bounded() -> None:
    plan = _nonlinear_plan(budget=SolverBudget(max_numeric_starts=1))
    attempts = (
        SolverAttempt(attempt_index=0, backend="numeric_root", phase="numeric", elapsed_s=0.1, completed=True),
        SolverAttempt(attempt_index=1, backend="numeric_root", phase="numeric", elapsed_s=0.1, completed=True),
    )
    fallback = SolverDiagnosticEntry(
        code="numeric_fallback_used", severity="warning", phase="numeric", backend="numeric_root",
    )
    with pytest.raises(ValidationError, match="attempt count"):
        MechanicsSolveResult(
            terminal="insufficient_conditions", plan=plan, candidate_set=_set(plan),
            diagnostics=_diagnostics(plan, fallback, attempts=attempts, total_elapsed_s=0.2),
        )

    with pytest.raises(ValidationError, match="canonical deterministic order"):
        SolverDiagnostics(
            entries=(
                SolverDiagnosticEntry(
                    code="generation_incomplete", severity="warning",
                    phase="candidate_generation", backend="linear_symbolic",
                ),
                _selected_entry(_plan()),
            ),
            total_elapsed_s=0.0,
        )


def test_terminal_matrix_rejects_wrong_auto_coverage_labels() -> None:
    plan = _plan()
    one, two = _candidate(plan), _candidate(plan, "ignored", 1)
    outcomes = (_outcome(one), _outcome(two))
    verified = (_verified(one, outcomes[0]), _verified(two, outcomes[1]))
    with pytest.raises(ValidationError, match="needs-confirmation"):
        MechanicsSolveResult(
            terminal="needs_confirmation", plan=plan, candidate_set=_set(plan, one, two),
            verification_outcomes=outcomes, verified_candidates=verified,
            diagnostics=_diagnostics(plan),
        )
