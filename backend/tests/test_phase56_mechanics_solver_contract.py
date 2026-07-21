from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from engine.mechanics.compiler import (
    ConstraintNode,
    EquationGraph,
    EquationNode,
    EquationScope,
    IncidenceEdge,
    LawApplication,
    RankAnalysis,
    SymbolNode,
)
from engine.mechanics.math_ast import (
    DimensionVector,
    Dot,
    Equality,
    Inequality,
    Integral,
    LiteralNode,
    SymbolDefinition,
    SymbolRef,
    VectorNode,
)
from engine.mechanics.solver import (
    CandidateGenerationRecord,
    CandidateCoverage,
    CandidateRejection,
    CandidateSet,
    CandidateValue,
    GraphStructureFeatures,
    SolveBackendKind,
    SolvePhase,
    SolvePlan,
    SolverAttempt,
    SolverBudget,
    SolverCandidate,
    SolverDiagnosticCode,
    SolverDiagnosticEntry,
    SolverDiagnostics,
    SolverTimeout,
    candidate_generation_manifest,
    canonical_candidate_id,
    make_solver_candidate,
    numeric_fallback_for_structure,
    primary_backend_for_structure,
    solver_phase_limit_s,
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
        expression_fingerprint="b" * 64,
        law_id="law1",
        scope=SCOPE,
        source_evidence_ids=("evidence1",),
        constraint_ids=("constraint1",),
        dimension=DIMENSIONLESS,
        complexity_cost=3,
    )
    inequality = EquationNode(
        equation_id="ineq1",
        expression=Inequality(relation="ge", left=SymbolRef(symbol_id="x"), right=LiteralNode(value=0.0)),
        expression_fingerprint="c" * 64,
        law_id="law1",
        scope=SCOPE,
        source_evidence_ids=("evidence1",),
        constraint_ids=("constraint1",),
        dimension=DIMENSIONLESS,
        complexity_cost=3,
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


def _graph_with_equality(
    expression: Equality,
    *,
    expression_fingerprint: str,
    complexity_cost: int,
) -> EquationGraph:
    base = _graph()
    equality = EquationNode(
        equation_id="eq1",
        expression=expression,
        expression_fingerprint=expression_fingerprint,
        law_id="law1",
        scope=SCOPE,
        source_evidence_ids=("evidence1",),
        constraint_ids=("constraint1",),
        dimension=DIMENSIONLESS,
        complexity_cost=complexity_cost,
    )
    return _graph(equations=(equality, base.equations[1]))


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
        "primary_backend": SolveBackendKind.linear_symbolic,
        "budget": SolverBudget(),
    }
    data.update(changes)
    return SolvePlan(**data)


PLAN = _plan().plan_fingerprint


def _candidate(**changes: object) -> SolverCandidate:
    data: dict[str, object] = {
        "generation_index": 0,
        "root_index": 0,
        "graph_fingerprint": GRAPH,
        "plan_fingerprint": PLAN,
        "backend": "linear_symbolic",
        "approximate": False,
        "equation_ids": ("eq1",),
        "values": (CandidateValue(symbol_id="x", value_si=2.0),),
        "query_symbol_id": "x",
        "query_value_si": 2.0,
    }
    data.update(changes)
    return make_solver_candidate(**data)


def _candidate_set(
    *candidates: SolverCandidate,
    coverage: CandidateCoverage | str = CandidateCoverage.exhaustive_symbolic,
    generation_complete: bool = True,
    generated_count: int | None = None,
    manifest: tuple[CandidateGenerationRecord, ...] | None = None,
) -> CandidateSet:
    return CandidateSet(
        graph_fingerprint=GRAPH,
        plan_fingerprint=PLAN,
        coverage=coverage,
        generation_complete=generation_complete,
        generated_count=len(candidates) if generated_count is None else generated_count,
        candidates=candidates,
        manifest=candidate_generation_manifest(candidates) if manifest is None else manifest,
    )


def test_required_backends_are_closed_and_models_are_frozen() -> None:
    assert {item.value for item in SolveBackendKind} >= {
        "linear_symbolic", "polynomial_symbolic", "nonlinear_symbolic", "numeric_root",
        "ode_ivp", "event_root", "constrained_optimization", "piecewise",
    }
    plan = _plan()
    with pytest.raises(ValidationError):
        plan.query_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        SolvePlan(**{**plan.model_dump(), "system_type": "projectile"})


@pytest.mark.parametrize("field", ["raw_text", "expected_answer", "solver_name", "expression", "model_output"])
def test_candidate_rejects_banned_authority_and_executable_fields(field: str) -> None:
    base = _candidate().model_dump()
    assert SolverCandidate.model_validate(base) == _candidate()
    with pytest.raises(ValidationError):
        SolverCandidate.model_validate({**base, field: "x + 1"})


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True])
def test_nonfinite_and_boolean_values_are_rejected(bad: object) -> None:
    with pytest.raises(ValidationError):
        _candidate(values=(CandidateValue(symbol_id="x", value_si=bad),), query_value_si=bad)
    with pytest.raises(ValidationError):
        SolverBudget(symbolic_time_limit_s=bad)


def test_plan_embeds_graph_and_round_trips_derived_fingerprints() -> None:
    plan = _plan()
    assert plan.graph_fingerprint == plan.graph.fingerprint == GRAPH
    assert plan.plan_fingerprint == _plan().plan_fingerprint
    assert "graph" in plan.model_dump() and plan.model_dump()["graph_fingerprint"] == GRAPH
    with pytest.raises(ValidationError):
        _plan(graph_fingerprint="f" * 64)
    with pytest.raises(ValidationError):
        _plan(plan_fingerprint="0" * 64)
    with pytest.raises(ValidationError):
        _plan(plan_fingerprint=None)
    assert _plan(graph_fingerprint=GRAPH) == plan
    assert _plan(plan_fingerprint=PLAN) == plan
    assert SolvePlan.model_validate(plan.model_dump()) == plan
    assert SolvePlan.model_validate_json(plan.model_dump_json()) == plan
    changed_grace = _plan(budget=SolverBudget(timeout_termination_grace_s=0.75))
    assert changed_grace.plan_fingerprint != plan.plan_fingerprint
    assert SolvePlan.model_validate_json(changed_grace.model_dump_json()) == changed_grace


def test_changed_concrete_graph_authority_changes_plan_fingerprint() -> None:
    changed_graph = _graph(fingerprint="d" * 64)
    changed = _plan(graph=changed_graph)
    assert changed.graph_fingerprint == "d" * 64
    assert changed.plan_fingerprint != PLAN


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"query_id": "query2"}, "query"),
        ({"selected_equality_ids": ("eq2",)}, "derived"),
        ({"inequality_ids": ()}, "derived"),
        ({"constraint_ids": ()}, "derived"),
        ({"initial_condition_ids": ("condition1",)}, "derived"),
        ({"event_ids": ()}, "derived"),
        ({"allowed_source_evidence_ids": ()}, "derived"),
        ({"unknown_symbol_ids": ("x", "z")}, "derived"),
        ({"known_symbol_ids": ()}, "derived"),
        ({"structure": _structure(total_ast_nodes=5)}, "structure"),
    ],
)
def test_plan_rejects_every_graph_derived_field_mismatch(change: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _plan(**change)


def test_plan_rejects_graph_query_mismatch_and_non_equality_selection() -> None:
    with pytest.raises(ValidationError, match="query"):
        _plan(graph=_graph(query_id="query2"))
    with pytest.raises(ValidationError, match="only existing equalities"):
        _plan(graph=_graph(selected_equation_ids=("ineq1",)), selected_equality_ids=("ineq1",))


def test_plan_budget_cannot_understate_graph_counts_or_ast() -> None:
    with pytest.raises(ValidationError, match="equation budget"):
        _plan(budget=SolverBudget(max_equations=1))
    with pytest.raises(ValidationError, match="AST budget"):
        _plan(budget=SolverBudget(max_ast_nodes=5))


def test_candidate_set_preserves_candidates_and_rejects_mismatch_duplicates() -> None:
    first = _candidate()
    with pytest.raises(ValidationError):
        _candidate_set(first, _candidate(), generated_count=2)
    with pytest.raises(ValidationError):
        _candidate_set(_candidate(graph_fingerprint="c" * 64))
    with pytest.raises(ValidationError):
        _candidate_set(coverage="incomplete", generation_complete=True)


def test_candidate_set_detects_generation_loss_and_false_coverage() -> None:
    with pytest.raises(ValidationError):
        _candidate_set(_candidate(generation_index=7))
    numeric = _candidate(backend="numeric_root", approximate=True)
    with pytest.raises(ValidationError):
        _candidate_set(numeric)
    with pytest.raises(ValidationError):
        _candidate_set(numeric, coverage="certified_unique_ivp")


@pytest.mark.parametrize("backend", ["numeric_root", "ode_ivp", "event_root", "constrained_optimization"])
def test_approximate_coverage_is_never_auto_selectable(backend: str) -> None:
    numeric = _candidate(backend=backend, approximate=True)
    bounded = _candidate_set(numeric, coverage=CandidateCoverage.bounded_numeric)
    assert not bounded.auto_selectable
    assert _candidate_set(_candidate()).auto_selectable


def test_rejection_provenance_and_timeout_are_precise_data_only() -> None:
    with pytest.raises(ValidationError):
        CandidateRejection(candidate_id="candidate1", reason="equation_residual", check_id="check1")
    timeout = SolverTimeout(phase=SolvePhase.symbolic, backend="linear_symbolic", limit_s=1.0, elapsed_s=1.1)
    with pytest.raises(ValidationError):
        SolverTimeout(phase="symbolic", backend="linear_symbolic", limit_s=1.0, elapsed_s=0.9)
    with pytest.raises(ValidationError):
        SolverDiagnostics(
            entries=(SolverDiagnosticEntry(code="timeout", severity="error", phase="symbolic", backend="linear_symbolic"),),
            attempts=(SolverAttempt(attempt_index=0, backend="linear_symbolic", phase="symbolic", elapsed_s=1.1, completed=False),),
            total_elapsed_s=1.0, timeout=timeout,
        )
    diagnostics = SolverDiagnostics(
        entries=(SolverDiagnosticEntry(code=SolverDiagnosticCode.timeout, severity="error", phase="symbolic", backend="linear_symbolic"),),
        attempts=(SolverAttempt(attempt_index=0, backend="linear_symbolic", phase="symbolic", elapsed_s=1.1, completed=False),),
        total_elapsed_s=1.1, timeout=timeout,
    )
    assert diagnostics.timeout == timeout


@pytest.mark.parametrize(
    ("code", "severity"),
    [
        ("backend_selected", "warning"),
        ("numeric_fallback_used", "info"),
        ("generation_incomplete", "error"),
        ("candidate_limit_reached", "warning"),
        ("backend_failure", "warning"),
        ("backend_unsupported", "warning"),
        ("resource_limit", "warning"),
        ("timeout", "warning"),
    ],
)
def test_diagnostic_code_severity_is_fixed_at_construction(code: str, severity: str) -> None:
    with pytest.raises(ValidationError, match="fixed severity"):
        SolverDiagnosticEntry(code=code, severity=severity, phase="planning", backend="linear_symbolic")


def test_attempt_indices_are_contiguous_and_timeout_is_bounded_by_total() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        SolverDiagnostics(
            attempts=(SolverAttempt(attempt_index=1, backend="linear_symbolic", phase="symbolic", elapsed_s=0.1, completed=True),),
            total_elapsed_s=0.1,
        )
    timeout = SolverTimeout(phase="symbolic", backend="linear_symbolic", limit_s=1.0, elapsed_s=1.1)
    with pytest.raises(ValidationError, match="total"):
        SolverDiagnostics(
            entries=(SolverDiagnosticEntry(code="timeout", severity="error", phase="symbolic", backend="linear_symbolic"),),
            attempts=(SolverAttempt(attempt_index=0, backend="linear_symbolic", phase="symbolic", elapsed_s=1.1, completed=False),),
            total_elapsed_s=1.0, timeout=timeout,
        )


@pytest.mark.parametrize(
    ("attempts", "message"),
    [
        ((), "exactly one matching incomplete"),
        (
            (SolverAttempt(attempt_index=0, backend="linear_symbolic", phase="symbolic", elapsed_s=1.1, completed=True),),
            "exactly one matching incomplete",
        ),
        (
            (SolverAttempt(attempt_index=0, backend="numeric_root", phase="numeric", elapsed_s=1.1, completed=False),),
            "exactly one matching incomplete",
        ),
        (
            (
                SolverAttempt(attempt_index=0, backend="linear_symbolic", phase="symbolic", elapsed_s=1.1, completed=False),
                SolverAttempt(attempt_index=1, backend="numeric_root", phase="numeric", elapsed_s=0.1, completed=True),
            ),
            "final",
        ),
        (
            (SolverAttempt(attempt_index=0, backend="linear_symbolic", phase="symbolic", elapsed_s=1.2, completed=False),),
            "exactly match",
        ),
        (
            (
                SolverAttempt(attempt_index=0, backend="linear_symbolic", phase="translation", elapsed_s=0.1, completed=False),
                SolverAttempt(attempt_index=1, backend="linear_symbolic", phase="symbolic", elapsed_s=1.1, completed=False),
            ),
            "before a timeout",
        ),
    ],
)
def test_timeout_requires_exact_final_incomplete_attempt_provenance(
    attempts: tuple[SolverAttempt, ...],
    message: str,
) -> None:
    timeout = SolverTimeout(
        phase="symbolic", backend="linear_symbolic", limit_s=1.0, elapsed_s=1.1,
    )
    with pytest.raises(ValidationError, match=message):
        SolverDiagnostics(
            entries=(
                SolverDiagnosticEntry(
                    code="timeout", severity="error", phase="symbolic", backend="linear_symbolic",
                ),
            ),
            attempts=attempts,
            total_elapsed_s=max(timeout.elapsed_s, sum(item.elapsed_s for item in attempts)),
            timeout=timeout,
        )


def test_timeout_accepts_one_exact_final_incomplete_attempt_and_round_trips() -> None:
    timeout = SolverTimeout(
        phase="symbolic", backend="linear_symbolic", limit_s=1.0, elapsed_s=1.1,
    )
    attempts = (
        SolverAttempt(
            attempt_index=0, backend="linear_symbolic", phase="symbolic",
            elapsed_s=0.1, completed=True,
        ),
        SolverAttempt(
            attempt_index=1, backend="linear_symbolic", phase="symbolic",
            elapsed_s=1.1, completed=False,
        ),
    )
    diagnostics = SolverDiagnostics(
        entries=(
            SolverDiagnosticEntry(
                code="timeout", severity="error", phase="symbolic", backend="linear_symbolic",
            ),
        ),
        attempts=attempts,
        total_elapsed_s=sum(item.elapsed_s for item in attempts),
        timeout=timeout,
    )
    assert diagnostics.attempts[-1].elapsed_s == diagnostics.timeout.elapsed_s
    assert SolverDiagnostics.model_validate_json(diagnostics.model_dump_json()) == diagnostics


def test_symbolic_text_is_explicitly_display_only_and_not_an_expression_field() -> None:
    candidate = _candidate(symbolic_display_only="x = sqrt(4)")
    assert candidate.symbolic_display_only == "x = sqrt(4)"
    assert "expression" not in SolverCandidate.model_fields


def test_candidate_id_and_manifest_are_canonical_and_publicly_round_trippable() -> None:
    candidate = _candidate()
    assert candidate.candidate_id == canonical_candidate_id(candidate)
    assert candidate.candidate_id.startswith("candidate_")
    assert SolverCandidate.model_validate(candidate.model_dump()) == candidate
    assert SolverCandidate.model_validate_json(candidate.model_dump_json()) == candidate
    with pytest.raises(ValidationError, match="canonical authoritative-data ID"):
        SolverCandidate.model_validate({**candidate.model_dump(), "candidate_id": "candidate_forged"})
    with pytest.raises(ValidationError, match="canonical authoritative-data ID"):
        SolverCandidate.model_validate({**candidate.model_dump(), "candidate_id": None})

    candidate_set = _candidate_set(candidate)
    assert CandidateSet.model_validate(candidate_set.model_dump()) == candidate_set
    assert CandidateSet.model_validate_json(candidate_set.model_dump_json()) == candidate_set


def test_manifest_detects_root_gaps_and_record_mismatch() -> None:
    first = _candidate(generation_index=0, root_index=0)
    gap = _candidate(generation_index=1, root_index=2, query_value_si=3.0,
                     values=(CandidateValue(symbol_id="x", value_si=3.0),))
    with pytest.raises(ValidationError, match="root indices"):
        _candidate_set(first, gap)

    exact = candidate_generation_manifest((first,))
    mismatched = (exact[0].model_copy(update={"root_index": 1}),)
    with pytest.raises(ValidationError, match="manifest"):
        _candidate_set(first, manifest=mismatched)
    with pytest.raises(ValidationError, match="manifest"):
        _candidate_set(first, manifest=())
    second = _candidate(
        generation_index=1,
        root_index=1,
        query_value_si=3.0,
        values=(CandidateValue(symbol_id="x", value_si=3.0),),
    )
    reversed_manifest = tuple(reversed(candidate_generation_manifest((first, second))))
    with pytest.raises(ValidationError, match="manifest"):
        _candidate_set(first, second, manifest=reversed_manifest)


@pytest.mark.parametrize(
    ("structure", "primary", "fallback"),
    [
        (_structure(has_piecewise=True, has_derivative=True, has_integral=True, has_vector_operation=True), "piecewise", None),
        (_structure(has_derivative=True, has_integral=True, has_vector_operation=True), "ode_ivp", None),
        (_structure(polynomial_degree=1, has_integral=True), "nonlinear_symbolic", "numeric_root"),
        (_structure(polynomial_degree=1, has_vector_operation=True), "nonlinear_symbolic", "numeric_root"),
        (_structure(polynomial_degree=0), "linear_symbolic", None),
        (_structure(polynomial_degree=1), "linear_symbolic", None),
        (_structure(polynomial_degree=2, has_nonlinear_operation=True), "polynomial_symbolic", None),
        (_structure(polynomial_degree=None, has_nonlinear_operation=True), "nonlinear_symbolic", "numeric_root"),
    ],
)
def test_closed_graph_only_backend_policy(
    structure: GraphStructureFeatures,
    primary: str,
    fallback: str | None,
) -> None:
    assert primary_backend_for_structure(structure).value == primary
    derived_fallback = numeric_fallback_for_structure(structure)
    assert (derived_fallback.value if derived_fallback else None) == fallback


@pytest.mark.parametrize(
    "change",
    [
        {"primary_backend": "polynomial_symbolic"},
        {"primary_backend": "event_root"},
        {"primary_backend": "constrained_optimization"},
        {"permitted_numeric_fallback": "numeric_root"},
    ],
)
def test_plan_rejects_arbitrary_backend_or_fallback(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="routing policy"):
        _plan(**change)


def test_integral_structure_is_exact_and_cannot_plan_as_linear() -> None:
    graph = _graph_with_equality(
        Equality(
            left=Integral(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="g"),
            right=LiteralNode(value=0.0),
        ),
        expression_fingerprint="d" * 64,
        complexity_cost=4,
    )
    exact = _structure(
        max_ast_nodes_per_equation=4,
        total_ast_nodes=7,
        max_ast_depth=3,
        total_operation_cost=7,
        polynomial_degree=None,
        has_integral=True,
        has_nonlinear_operation=True,
    )
    plan = _plan(
        graph=graph,
        structure=exact,
        primary_backend="nonlinear_symbolic",
        permitted_numeric_fallback="numeric_root",
    )
    assert plan.structure.has_integral is True
    assert plan.structure.polynomial_degree is None
    assert plan.primary_backend is SolveBackendKind.nonlinear_symbolic
    assert SolvePlan.model_validate_json(plan.model_dump_json()) == plan
    with pytest.raises(ValidationError, match="routing policy"):
        _plan(
            graph=graph,
            structure=exact,
            primary_backend="linear_symbolic",
            permitted_numeric_fallback="numeric_root",
        )

    wrong = GraphStructureFeatures(**{**exact.model_dump(), "has_integral": False})
    with pytest.raises(ValidationError, match="structure"):
        _plan(
            graph=graph,
            structure=wrong,
            primary_backend="nonlinear_symbolic",
            permitted_numeric_fallback="numeric_root",
        )


def test_vector_operation_structure_is_exact_and_cannot_plan_as_linear() -> None:
    graph = _graph_with_equality(
        Equality(
            left=Dot(
                left=VectorNode(items=(SymbolRef(symbol_id="x"), LiteralNode(value=0.0))),
                right=VectorNode(items=(LiteralNode(value=1.0), LiteralNode(value=1.0))),
            ),
            right=LiteralNode(value=0.0),
        ),
        expression_fingerprint="e" * 64,
        complexity_cost=9,
    )
    exact = _structure(
        max_ast_nodes_per_equation=9,
        total_ast_nodes=12,
        max_ast_depth=4,
        total_operation_cost=12,
        polynomial_degree=None,
        has_vector_operation=True,
        has_nonlinear_operation=True,
    )
    plan = _plan(
        graph=graph,
        structure=exact,
        primary_backend="nonlinear_symbolic",
        permitted_numeric_fallback="numeric_root",
    )
    assert plan.structure.has_vector_operation is True
    assert plan.structure.polynomial_degree is None
    assert plan.primary_backend is SolveBackendKind.nonlinear_symbolic
    assert SolvePlan.model_validate_json(plan.model_dump_json()) == plan
    with pytest.raises(ValidationError, match="routing policy"):
        _plan(
            graph=graph,
            structure=exact,
            primary_backend="linear_symbolic",
            permitted_numeric_fallback="numeric_root",
        )

    wrong = GraphStructureFeatures(**{**exact.model_dump(), "has_vector_operation": False})
    with pytest.raises(ValidationError, match="structure"):
        _plan(
            graph=graph,
            structure=wrong,
            primary_backend="nonlinear_symbolic",
            permitted_numeric_fallback="numeric_root",
        )


@pytest.mark.parametrize("bad", [True, "2"])
def test_resource_and_ordinal_integer_fields_are_strict(bad: object) -> None:
    with pytest.raises(ValidationError):
        SolverBudget(max_equations=bad)
    with pytest.raises(ValidationError):
        GraphStructureFeatures(**{
            **_structure().model_dump(),
            "equality_count": bad,
        })
    with pytest.raises(ValidationError):
        _candidate(generation_index=bad)
    with pytest.raises(ValidationError):
        _candidate(root_multiplicity=bad)
    candidate_set = _candidate_set(_candidate())
    with pytest.raises(ValidationError):
        CandidateSet.model_validate({**candidate_set.model_dump(), "generated_count": bad})
    with pytest.raises(ValidationError):
        SolverAttempt(
            attempt_index=bad,
            backend="linear_symbolic",
            phase="symbolic",
            elapsed_s=0.1,
            completed=True,
        )


@pytest.mark.parametrize("bad", [1, "true"])
def test_semantic_boolean_fields_are_strict(bad: object) -> None:
    for field in ("has_derivative", "has_integral", "has_vector_operation"):
        with pytest.raises(ValidationError):
            GraphStructureFeatures(**{**_structure().model_dump(), field: bad})
    with pytest.raises(ValidationError):
        _candidate(approximate=bad)
    with pytest.raises(ValidationError):
        _candidate_set(_candidate(), generation_complete=bad)
    with pytest.raises(ValidationError):
        SolverAttempt(
            attempt_index=0,
            backend="linear_symbolic",
            phase="symbolic",
            elapsed_s=0.1,
            completed=bad,
        )


@pytest.mark.parametrize("bad", [True, 0.0, -0.1, 5.000001, math.nan, math.inf])
def test_timeout_termination_grace_is_finite_positive_bounded_and_not_boolean(bad: object) -> None:
    with pytest.raises(ValidationError):
        SolverBudget(timeout_termination_grace_s=bad)
    assert 0.0 < SolverBudget().timeout_termination_grace_s <= 1.0
    assert SolverBudget(timeout_termination_grace_s=5.0).timeout_termination_grace_s == 5.0


@pytest.mark.parametrize("authority", ["application", "symbol"])
def test_graph_event_union_includes_application_and_symbol_authority(authority: str) -> None:
    empty_scope = EquationScope()
    base = _graph()
    equations = tuple(item.model_copy(update={"scope": empty_scope}) for item in base.equations)
    constraints = tuple(item.model_copy(update={"scope": empty_scope}) for item in base.constraints)
    application_scope = EquationScope(event_id="eventApp", event_ids=("eventApp",)) if authority == "application" else empty_scope
    applications = tuple(item.model_copy(update={"scope": application_scope}) for item in base.applications)
    symbols = base.symbols
    expected_event = "eventApp"
    if authority == "symbol":
        expected_event = "eventSymbol"
        symbols = (base.symbols[0], base.symbols[1].model_copy(update={"event_id": expected_event}))
    graph = _graph(
        symbols=symbols,
        equations=equations,
        constraints=constraints,
        applications=applications,
    )
    plan = _plan(graph=graph, event_ids=(expected_event,))
    assert plan.event_ids == (expected_event,)
    assert plan.structure.has_event_condition is True


def test_plan_rejects_selected_set_without_unknown_structural_closure() -> None:
    base = _graph()
    z = SymbolNode(
        symbol=SymbolDefinition(symbol_id="z", quantity_id="quantityZ", dimension=DIMENSIONLESS),
        quantity_id="quantityZ", quantity_role="position", known_si_value=None,
    )
    forged_rank = base.rank.model_copy(update={"unknown_count": 2, "structural_rank": 2})
    graph = _graph(symbols=(*base.symbols, z), rank=forged_rank)
    with pytest.raises(ValidationError, match="structural rank"):
        _plan(
            graph=graph,
            unknown_symbol_ids=("x", "z"),
            structure=_structure(unknown_count=2),
        )


def test_solver_phase_limit_policy_is_closed() -> None:
    budget = SolverBudget(
        symbolic_time_limit_s=2.0,
        numeric_time_limit_s=3.0,
        verification_time_limit_s=4.0,
    )
    assert solver_phase_limit_s(SolvePhase.verification, SolveBackendKind.numeric_root, budget) == 4.0
    assert solver_phase_limit_s(SolvePhase.numeric, SolveBackendKind.numeric_root, budget) == 3.0
    assert solver_phase_limit_s(SolvePhase.symbolic, SolveBackendKind.linear_symbolic, budget) == 2.0
    assert solver_phase_limit_s(SolvePhase.candidate_generation, SolveBackendKind.ode_ivp, budget) == 3.0
    assert solver_phase_limit_s(SolvePhase.translation, SolveBackendKind.linear_symbolic, budget) == 2.0
