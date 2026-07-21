"""Deterministic graph-only planning for the mechanics solver."""

from __future__ import annotations

from enum import Enum

from pydantic import ValidationError

from engine.mechanics.compiler.contracts import EquationGraph

from .contracts import (
    SolvePlan,
    SolverBudget,
    _graph_evidence_ids,
    _graph_event_ids,
    _graph_structure,
    _graph_unknown_ids,
    numeric_fallback_for_structure,
    primary_backend_for_structure,
)


class PlanningFailureCode(str, Enum):
    """Closed reasons exposed when a graph cannot form an authorized plan."""

    invalid_graph = "invalid_graph"
    insufficient_rank = "insufficient_rank"
    resource_limit = "resource_limit"


class SolvePlanningError(ValueError):
    """A closed planning failure without validation internals or input text."""

    def __init__(self, code: PlanningFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


def _failure_code(error: ValidationError) -> PlanningFailureCode:
    categories = tuple(str(item.get("msg", "")) for item in error.errors())
    if any("budget" in item or "limit" in item for item in categories):
        return PlanningFailureCode.resource_limit
    if any("rank" in item or "unknown" in item or "selected" in item for item in categories):
        return PlanningFailureCode.insufficient_rank
    return PlanningFailureCode.invalid_graph


def plan_equation_graph(
    graph: EquationGraph,
    budget: SolverBudget | None = None,
) -> SolvePlan:
    """Build the sole canonical plan permitted by an immutable equation graph."""

    try:
        exact_budget = budget if budget is not None else SolverBudget()
        unknown_ids = _graph_unknown_ids(graph)
        structure = _graph_structure(graph, unknown_ids)
        return SolvePlan(
            graph=graph,
            query_id=graph.query_id,
            query_symbol_id=graph.query_symbol_id,
            selected_equality_ids=tuple(graph.selected_equation_ids),
            inequality_ids=tuple(sorted(
                item.equation_id
                for item in graph.equations
                if item.expression.op == "inequality"
            )),
            constraint_ids=tuple(sorted(item.constraint_id for item in graph.constraints)),
            initial_condition_ids=tuple(sorted(
                item.condition_id for item in graph.initial_conditions
            )),
            event_ids=_graph_event_ids(graph),
            allowed_source_evidence_ids=_graph_evidence_ids(graph),
            unknown_symbol_ids=unknown_ids,
            known_symbol_ids=tuple(sorted(
                item.symbol.symbol_id
                for item in graph.symbols
                if item.known_si_value is not None
            )),
            structure=structure,
            primary_backend=primary_backend_for_structure(structure),
            permitted_numeric_fallback=numeric_fallback_for_structure(structure),
            budget=exact_budget,
        )
    except ValidationError as error:
        raise SolvePlanningError(_failure_code(error)) from None
    except ValueError as error:
        code = (
            PlanningFailureCode.resource_limit
            if "bound" in str(error) or "limit" in str(error)
            else PlanningFailureCode.invalid_graph
        )
        raise SolvePlanningError(code) from None
    except Exception:
        raise SolvePlanningError(PlanningFailureCode.invalid_graph) from None


# A concise spelling for orchestrators and callers.
create_solve_plan = plan_equation_graph


__all__ = [
    "PlanningFailureCode",
    "SolvePlanningError",
    "create_solve_plan",
    "plan_equation_graph",
]
