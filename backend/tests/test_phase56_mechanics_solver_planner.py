from __future__ import annotations

import inspect

import pytest

from engine.mechanics.compiler.contracts import (
    EquationGraph,
    EquationNode,
    EquationScope,
    IncidenceEdge,
    LawApplication,
    RankAnalysis,
    SymbolNode,
)
from engine.mechanics.math_ast import (
    Derivative,
    DimensionVector,
    Dot,
    Equality,
    Integral,
    LiteralNode,
    Piecewise,
    PiecewiseBranch,
    SymbolDefinition,
    SymbolRef,
    SymbolShape,
    VectorNode,
)
from engine.mechanics.solver.contracts import SolveBackendKind, SolverBudget
from engine.mechanics.solver.planner import (
    SolvePlanningError,
    plan_equation_graph,
)


DIMENSIONLESS = DimensionVector()
SCOPE = EquationScope()


def _symbol(
    symbol_id: str,
    *,
    known: float | tuple[float, ...] | None = None,
    role: str = "position",
    shape: SymbolShape = SymbolShape.scalar,
    length: int | None = None,
) -> SymbolNode:
    quantity_id = f"quantity_{symbol_id}"
    return SymbolNode(
        symbol=SymbolDefinition(
            symbol_id=symbol_id,
            quantity_id=quantity_id,
            dimension=DIMENSIONLESS,
            shape=shape,
            vector_length=length,
        ),
        quantity_id=quantity_id,
        quantity_role=role,
        known_si_value=known,
    )


def _graph(
    expressions: tuple[Equality, ...],
    symbols: tuple[SymbolNode, ...],
    *,
    query_symbol_id: str = "x",
) -> EquationGraph:
    equations = tuple(
        EquationNode(
            equation_id=f"eq{index}",
            expression=expression,
            expression_fingerprint=f"{index + 1:064x}",
            law_id="law1",
            scope=SCOPE,
            dimension=DIMENSIONLESS,
            complexity_cost=4,
        )
        for index, expression in enumerate(expressions, 1)
    )
    unknown_ids = tuple(sorted(
        item.symbol.symbol_id
        for item in symbols
        if item.known_si_value is None and item.quantity_role != "time"
    ))
    incidence = tuple(
        IncidenceEdge(equation_id=equation.equation_id, symbol_id=symbol_id)
        for equation in equations
        for symbol_id in unknown_ids
    )
    equation_ids = tuple(item.equation_id for item in equations)
    return EquationGraph(
        query_id="query1",
        query_symbol_id=query_symbol_id,
        symbols=tuple(sorted(symbols, key=lambda item: item.symbol.symbol_id)),
        equations=equations,
        constraints=(),
        applications=(LawApplication(
            application_id="application1",
            law_id="law1",
            equation_ids=equation_ids,
            scope=SCOPE,
            complexity_cost=4 * len(equations),
        ),),
        incidence=incidence,
        rank=RankAnalysis(
            equality_count=len(equations),
            inequality_count=0,
            unknown_count=len(unknown_ids),
            structural_rank=len(unknown_ids),
            underdetermined=False,
            overdetermined=len(equations) > len(unknown_ids),
            conflicting=False,
        ),
        selected_equation_ids=equation_ids,
        fingerprint="a" * 64,
    )


def test_planner_is_graph_only_deterministic_and_fingerprints_budget() -> None:
    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        (_symbol("x"), _symbol("two", known=2.0, role="parameter")),
    )
    first = plan_equation_graph(graph)
    repeated = plan_equation_graph(graph)
    changed_budget = plan_equation_graph(graph, SolverBudget(max_candidates=7))
    assert first == repeated
    assert first.plan_fingerprint == repeated.plan_fingerprint
    assert changed_budget.plan_fingerprint != first.plan_fingerprint
    assert first.primary_backend is SolveBackendKind.linear_symbolic
    assert tuple(inspect.signature(plan_equation_graph).parameters) == ("graph", "budget")


@pytest.mark.parametrize(
    ("expression", "extra_symbols", "backend", "fallback"),
    [
        (
            Equality(
                left=Derivative(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="t"),
                right=SymbolRef(symbol_id="two"),
            ),
            (_symbol("t", role="time"),),
            SolveBackendKind.ode_ivp,
            None,
        ),
        (
            Equality(
                left=Integral(expression=SymbolRef(symbol_id="x"), wrt_symbol_id="t"),
                right=SymbolRef(symbol_id="two"),
            ),
            (_symbol("t", role="time"),),
            SolveBackendKind.nonlinear_symbolic,
            SolveBackendKind.numeric_root,
        ),
        (
            Equality(
                left=Piecewise(
                    branches=(PiecewiseBranch(
                        condition=Equality(
                            left=SymbolRef(symbol_id="x"),
                            right=LiteralNode(value=0.0),
                        ),
                        value=SymbolRef(symbol_id="x"),
                    ),),
                    otherwise=LiteralNode(value=1.0),
                ),
                right=SymbolRef(symbol_id="two"),
            ),
            (),
            SolveBackendKind.piecewise,
            None,
        ),
    ],
)
def test_planner_routes_advanced_structure_without_descriptive_labels(
    expression: Equality,
    extra_symbols: tuple[SymbolNode, ...],
    backend: SolveBackendKind,
    fallback: SolveBackendKind | None,
) -> None:
    graph = _graph(
        (expression,),
        (_symbol("x"), _symbol("two", known=2.0, role="parameter"), *extra_symbols),
    )
    plan = plan_equation_graph(graph)
    assert plan.primary_backend is backend
    assert plan.permitted_numeric_fallback is fallback


def test_planner_routes_vector_structure_conservatively() -> None:
    graph = _graph(
        (Equality(
            left=Dot(
                left=SymbolRef(symbol_id="v"),
                right=VectorNode(items=(LiteralNode(value=1.0), LiteralNode(value=0.0))),
            ),
            right=SymbolRef(symbol_id="two"),
        ),),
        (
            _symbol("v", shape=SymbolShape.vector, length=2),
            _symbol("two", known=2.0, role="parameter"),
        ),
        query_symbol_id="v",
    )
    plan = plan_equation_graph(graph)
    assert plan.primary_backend is SolveBackendKind.nonlinear_symbolic
    assert plan.permitted_numeric_fallback is SolveBackendKind.numeric_root
    assert plan.structure.has_vector_operation


def test_planner_closes_insufficient_rank_without_validation_details() -> None:
    graph = _graph(
        (Equality(left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")),),
        (
            _symbol("x"),
            _symbol("y"),
            _symbol("two", known=2.0, role="parameter"),
        ),
    )
    with pytest.raises(SolvePlanningError) as captured:
        plan_equation_graph(graph)
    assert str(captured.value) in {"invalid_graph", "insufficient_rank"}
