"""Exact static-boundary waiver for a directly stated impulse.

Endpoint event IDs label algebraic before/after states. They are not timed root
events when the immutable equation graph is exactly one signed-axis
impulse--momentum balance, optionally plus one evidenced rest equation. Any
extra law, symbol, scope, constraint, alternative set, generated value, or AST
shape leaves the normal event guard in force.
"""
from __future__ import annotations

import math
from typing import Any

from engine.mechanics.math_ast import (
    Equality,
    LiteralNode,
    Multiply,
    Negate,
    Subtract,
    SymbolRef,
)

DIRECT_IMPULSE_BOUNDARY_VERSION = "direct-impulse-boundary-v2"

_installed = False
_original = None


def _signed_ref(node: object) -> tuple[str, int] | None:
    if isinstance(node, SymbolRef):
        return node.symbol_id, 1
    if isinstance(node, Negate) and isinstance(node.operand, SymbolRef):
        return node.operand.symbol_id, -1
    return None


def _applications_mirror(graph: Any, equations_by_law: dict[str, Any]) -> bool:
    applications_by_law = {item.law_id: item for item in graph.applications}
    if set(applications_by_law) != set(equations_by_law):
        return False
    return all(
        application.equation_ids == (equation.equation_id,)
        and application.source_quantity_ids == equation.source_quantity_ids
        and application.source_evidence_ids == equation.source_evidence_ids
        and application.assumption_ids == equation.assumption_ids
        and application.constraint_ids == equation.constraint_ids
        and application.generated_unknown_symbol_ids
        == equation.generated_unknown_symbol_ids
        and application.complexity_cost == equation.complexity_cost
        and application.scope == equation.scope
        for law_id, application in applications_by_law.items()
        for equation in (equations_by_law[law_id],)
    )


def is_direct_impulse_momentum_boundary_graph(graph: Any) -> bool:
    """Return true only for the exact algebraic direct-impulse graph."""
    from engine.mechanics.solver import contracts

    event_ids = contracts._graph_event_ids(graph)
    laws = {item.law_id for item in graph.equations}
    allowed = (
        {"linear_impulse_momentum"},
        {"linear_impulse_momentum", "state_at_rest"},
    )
    if laws not in allowed:
        return False
    with_rest = "state_at_rest" in laws
    expected_count = 2 if with_rest else 1
    expected_unknowns = 2 if with_rest else 1
    if (
        len(event_ids) != 2
        or len(graph.constraints) != (1 if with_rest else 0)
        or graph.initial_conditions
        or graph.alternative_closed_sets
        or len(graph.equations) != expected_count
        or len(graph.applications) != expected_count
        or {item.law_id for item in graph.applications} != laws
        or graph.rank.equality_count != expected_count
        or graph.rank.inequality_count != 0
        or graph.rank.unknown_count != expected_unknowns
        or graph.rank.structural_rank != expected_unknowns
        or graph.rank.underdetermined
        or graph.rank.overdetermined
        or graph.rank.conflicting
    ):
        return False

    equations_by_law = {item.law_id: item for item in graph.equations}
    if (
        set(graph.selected_equation_ids)
        != {item.equation_id for item in graph.equations}
        or not _applications_mirror(graph, equations_by_law)
    ):
        return False

    by_role: dict[str, list[Any]] = {}
    for item in graph.symbols:
        if item.generated or item.quantity_role is None:
            return False
        if item.known_si_value is not None and (
            type(item.known_si_value) is not float
            or not math.isfinite(item.known_si_value)
        ):
            return False
        by_role.setdefault(item.quantity_role, []).append(item)
    if (
        set(by_role) != {"impulse", "mass", "velocity"}
        or len(by_role["impulse"]) != 1
        or len(by_role["mass"]) != 1
        or len(by_role["velocity"]) != 2
        or len(graph.symbols) != 4
    ):
        return False

    impulse = by_role["impulse"][0]
    mass = by_role["mass"][0]
    velocities = tuple(by_role["velocity"])
    if len({item.subject_id for item in (impulse, mass, *velocities)}) != 1:
        return False
    subject_id = impulse.subject_id
    if subject_id is None:
        return False
    interval_ids = {item.interval_id for item in (impulse, *velocities)}
    frame_ids = {item.frame_id for item in (impulse, *velocities)}
    if (
        len(interval_ids) != 1
        or None in interval_ids
        or len(frame_ids) != 1
        or None in frame_ids
        or mass.event_id is not None
        or mass.frame_id is not None
        or mass.interval_id not in {None, next(iter(interval_ids))}
        or {item.event_id for item in velocities} != set(event_ids)
        or any(item.event_id is None for item in velocities)
        or (mass.known_si_value is not None and mass.known_si_value <= 0.0)
    ):
        return False
    interval_id = next(iter(interval_ids))
    frame_id = next(iter(frame_ids))

    unknowns = tuple(item for item in graph.symbols if item.known_si_value is None)
    query_allowed = {
        impulse.symbol.symbol_id,
        *(item.symbol.symbol_id for item in velocities),
    }
    if (
        len(unknowns) != expected_unknowns
        or graph.query_symbol_id not in {item.symbol.symbol_id for item in unknowns}
        or graph.query_symbol_id not in query_allowed
    ):
        return False

    momentum = equations_by_law["linear_impulse_momentum"]
    if (
        not isinstance(momentum.expression, Equality)
        or momentum.assumption_ids
        or momentum.constraint_ids
        or momentum.generated_unknown_symbol_ids
        or momentum.scope.entity_ids != (subject_id,)
        or momentum.scope.point_ids
        or momentum.scope.frame_id != frame_id
        or momentum.scope.interval_id != interval_id
        or momentum.scope.event_id is not None
        or momentum.scope.event_ids != event_ids
        or momentum.dimension != impulse.symbol.dimension
        or momentum.source_quantity_ids
        != tuple(
            sorted(
                {
                    impulse.quantity_id,
                    mass.quantity_id,
                    *(item.quantity_id for item in velocities),
                }
            )
        )
    ):
        return False

    left = _signed_ref(momentum.expression.left)
    right = momentum.expression.right
    if (
        left is None
        or left[0] != impulse.symbol.symbol_id
        or not isinstance(right, Multiply)
        or len(right.factors) != 2
    ):
        return False
    mass_refs = tuple(
        item
        for item in right.factors
        if isinstance(item, SymbolRef)
        and item.symbol_id == mass.symbol.symbol_id
    )
    differences = tuple(item for item in right.factors if isinstance(item, Subtract))
    if len(mass_refs) != 1 or len(differences) != 1:
        return False
    end_ref = _signed_ref(differences[0].left)
    start_ref = _signed_ref(differences[0].right)
    velocity_by_symbol = {item.symbol.symbol_id: item for item in velocities}
    if end_ref is None or start_ref is None:
        return False
    end_velocity = velocity_by_symbol.get(end_ref[0])
    start_velocity = velocity_by_symbol.get(start_ref[0])
    if (
        end_velocity is None
        or start_velocity is None
        or end_velocity is start_velocity
        or end_velocity.event_id == start_velocity.event_id
        or {end_velocity.event_id, start_velocity.event_id} != set(event_ids)
    ):
        return False

    # A stated impulse belongs to the whole interval.  The one safe event-scoped
    # exception is an *unknown queried impulse* at the evidenced final rest
    # boundary: it names the quantity the interval balance must determine, not a
    # second impulse acting at an arbitrary instant.
    if impulse.event_id is not None and (
        not with_rest
        or impulse.known_si_value is not None
        or graph.query_symbol_id != impulse.symbol.symbol_id
        or impulse.event_id != end_velocity.event_id
    ):
        return False

    if not with_rest:
        return True

    rest = equations_by_law["state_at_rest"]
    constraint = graph.constraints[0]
    rest_left = _signed_ref(rest.expression.left) if isinstance(rest.expression, Equality) else None
    if (
        not isinstance(rest.expression, Equality)
        or rest.assumption_ids
        or len(rest.constraint_ids) != 1
        or rest.generated_unknown_symbol_ids
        or rest.scope.entity_ids != (subject_id,)
        or rest.scope.point_ids
        or rest.scope.frame_id != frame_id
        or rest.scope.interval_id != interval_id
        or rest.scope.event_id != end_velocity.event_id
        or set(rest.scope.event_ids) != {rest.scope.event_id}
        or (impulse.event_id is not None and impulse.event_id != rest.scope.event_id)
        or rest.dimension != end_velocity.symbol.dimension
        or rest.source_quantity_ids != (end_velocity.quantity_id,)
        or constraint.constraint_id != rest.constraint_ids[0]
        or constraint.equation_id != rest.equation_id
        or constraint.scope != rest.scope
        or constraint.constraint_kind != "state_final"
        or rest_left is None
        or rest_left[0] != end_velocity.symbol.symbol_id
        or not isinstance(rest.expression.right, LiteralNode)
        or rest.expression.right.value != 0.0
        or rest.expression.right.dimension != end_velocity.symbol.dimension
    ):
        return False
    return True


def install_direct_impulse_boundary_waiver() -> None:
    """Extend the existing exact impulse recognizer without weakening it."""
    global _installed, _original
    if _installed:
        return
    from engine.mechanics.solver import contracts

    if contracts.SOLVER_CONTRACT_VERSION != "mechanics-solver-contract-v1":
        raise RuntimeError("direct impulse waiver requires reviewed solver contract v1")
    current = contracts._is_static_impulse_momentum_boundary_graph
    if getattr(current, "_direct_impulse_v1", False):
        _installed = True
        return
    _original = current

    def extended(graph: Any) -> bool:
        assert _original is not None
        return _original(graph) or is_direct_impulse_momentum_boundary_graph(graph)

    extended._direct_impulse_v1 = True  # type: ignore[attr-defined]
    contracts._is_static_impulse_momentum_boundary_graph = extended
    _installed = True


__all__ = [
    "DIRECT_IMPULSE_BOUNDARY_VERSION",
    "install_direct_impulse_boundary_waiver",
    "is_direct_impulse_momentum_boundary_graph",
]
