"""Exact static-boundary waiver for a one-dimensional stopping interval.

The interval start/end labels identify two algebraic velocity states.  They are
not timed root events when the immutable graph is exactly one signed
constant-acceleration velocity balance plus one evidenced final-rest equation.
Every structural near miss keeps the ordinary event guard.
"""
from __future__ import annotations

import math
from typing import Any

from engine.mechanics.math_ast import (
    Add,
    Equality,
    LiteralNode,
    Multiply,
    Negate,
    SymbolRef,
)

CONSTANT_ACCELERATION_STOP_BOUNDARY_VERSION = (
    "constant-acceleration-stop-boundary-v1"
)

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


def is_static_constant_acceleration_stop_boundary_graph(graph: Any) -> bool:
    """Return true only for the exact signed stop-time algebraic graph."""

    from engine.mechanics.solver import contracts

    event_ids = contracts._graph_event_ids(graph)
    velocity_law = "particle_constant_acceleration_velocity"
    state_law = "state_at_rest"
    laws = {velocity_law, state_law}
    if (
        len(event_ids) != 2
        or len(graph.constraints) != 1
        or graph.initial_conditions
        or graph.alternative_closed_sets
        or len(graph.equations) != 2
        or len(graph.applications) != 2
        or {item.law_id for item in graph.equations} != laws
        or {item.law_id for item in graph.applications} != laws
        or set(graph.selected_equation_ids)
        != {item.equation_id for item in graph.equations}
        or graph.rank.equality_count != 2
        or graph.rank.inequality_count != 0
        or graph.rank.unknown_count != 2
        or graph.rank.structural_rank != 2
        or graph.rank.underdetermined
        or graph.rank.overdetermined
        or graph.rank.conflicting
    ):
        return False

    equations_by_law = {item.law_id: item for item in graph.equations}
    if not _applications_mirror(graph, equations_by_law):
        return False

    by_role: dict[str, list[Any]] = {}
    for item in graph.symbols:
        if item.generated or item.point_id is not None or item.quantity_role is None:
            return False
        if item.known_si_value is not None and (
            type(item.known_si_value) is not float
            or not math.isfinite(item.known_si_value)
        ):
            return False
        by_role.setdefault(item.quantity_role, []).append(item)
    if (
        set(by_role) != {"acceleration", "duration", "velocity"}
        or len(by_role["acceleration"]) != 1
        or len(by_role["duration"]) != 1
        or len(by_role["velocity"]) != 2
        or len(graph.symbols) != 4
    ):
        return False

    acceleration = by_role["acceleration"][0]
    duration = by_role["duration"][0]
    velocities = tuple(by_role["velocity"])
    subject_ids = {item.subject_id for item in (acceleration, duration, *velocities)}
    interval_ids = {item.interval_id for item in (acceleration, duration, *velocities)}
    if (
        len(subject_ids) != 1
        or None in subject_ids
        or len(interval_ids) != 1
        or None in interval_ids
        or acceleration.event_id is not None
        or duration.event_id is not None
        or {item.event_id for item in velocities} != set(event_ids)
        or any(item.event_id is None for item in velocities)
        or acceleration.frame_id is None
        or any(item.frame_id != acceleration.frame_id for item in velocities)
        or duration.frame_id not in {None, acceleration.frame_id}
        or acceleration.known_si_value is None
        or duration.known_si_value is not None
    ):
        return False
    subject_id = next(iter(subject_ids))
    interval_id = next(iter(interval_ids))
    frame_id = acceleration.frame_id

    state = equations_by_law[state_law]
    velocity = equations_by_law[velocity_law]
    constraint = graph.constraints[0]
    if (
        constraint.constraint_kind != "state_final"
        or constraint.equation_id != state.equation_id
        or constraint.scope != state.scope
        or state.constraint_ids != (constraint.constraint_id,)
        or state.assumption_ids
        or len(velocity.assumption_ids) != 1
        or velocity.constraint_ids
        or not state.source_evidence_ids
        or state.scope.entity_ids != (subject_id,)
        or state.scope.point_ids
        or state.scope.frame_id != frame_id
        or state.scope.interval_id != interval_id
        or state.scope.event_id is None
        or state.scope.event_ids != (state.scope.event_id,)
        or state.scope.event_id not in event_ids
        or velocity.scope.entity_ids != (subject_id,)
        or velocity.scope.point_ids
        or velocity.scope.frame_id != frame_id
        or velocity.scope.interval_id != interval_id
        or velocity.scope.event_id is not None
        or velocity.scope.event_ids != event_ids
    ):
        return False

    velocity_by_event = {item.event_id: item for item in velocities}
    end_velocity = velocity_by_event.get(state.scope.event_id)
    other_events = tuple(item for item in event_ids if item != state.scope.event_id)
    if end_velocity is None or len(other_events) != 1:
        return False
    start_velocity = velocity_by_event.get(other_events[0])
    if (
        start_velocity is None
        or start_velocity.known_si_value is None
        or end_velocity.known_si_value is not None
        or graph.query_symbol_id != duration.symbol.symbol_id
    ):
        return False

    if state.source_quantity_ids != (end_velocity.quantity_id,) or (
        velocity.source_quantity_ids
        != tuple(
            sorted(
                {
                    acceleration.quantity_id,
                    duration.quantity_id,
                    start_velocity.quantity_id,
                    end_velocity.quantity_id,
                }
            )
        )
    ):
        return False

    if not isinstance(state.expression, Equality):
        return False
    state_left = _signed_ref(state.expression.left)
    if (
        state_left is None
        or state_left[0] != end_velocity.symbol.symbol_id
        or not isinstance(state.expression.right, LiteralNode)
        or state.expression.right.value != 0.0
        or state.expression.right.dimension != end_velocity.symbol.dimension
    ):
        return False

    if not isinstance(velocity.expression, Equality):
        return False
    velocity_left = _signed_ref(velocity.expression.left)
    right = velocity.expression.right
    if (
        velocity_left is None
        or velocity_left[0] != end_velocity.symbol.symbol_id
        or not isinstance(right, Add)
        or len(right.terms) != 2
    ):
        return False
    start_terms = tuple(
        item
        for item in right.terms
        if (_signed_ref(item) or (None, 0))[0] == start_velocity.symbol.symbol_id
    )
    products = tuple(item for item in right.terms if isinstance(item, Multiply))
    if len(start_terms) != 1 or len(products) != 1 or len(products[0].factors) != 2:
        return False
    acceleration_terms = tuple(
        item
        for item in products[0].factors
        if (_signed_ref(item) or (None, 0))[0] == acceleration.symbol.symbol_id
    )
    duration_terms = tuple(
        item
        for item in products[0].factors
        if isinstance(item, SymbolRef)
        and item.symbol_id == duration.symbol.symbol_id
    )
    if len(acceleration_terms) != 1 or len(duration_terms) != 1:
        return False

    # The profile defines +x as along-motion and binds the acceleration to the
    # opposite sign.  This exact sign relationship distinguishes a stopping
    # interval from an arbitrary two-event kinematics graph.
    start_sign = _signed_ref(start_terms[0])
    acceleration_sign = _signed_ref(acceleration_terms[0])
    if (
        start_sign is None
        or acceleration_sign is None
        or start_sign[1] != 1
        or acceleration_sign[1] != -1
    ):
        return False
    return True


def install_constant_acceleration_stop_boundary_waiver() -> None:
    """Extend the existing rest-boundary recognizer once, fail-closed."""

    global _installed, _original
    if _installed:
        return
    from engine.mechanics.solver import contracts

    if contracts.SOLVER_CONTRACT_VERSION != "mechanics-solver-contract-v1":
        raise RuntimeError(
            "constant-acceleration stop waiver requires reviewed solver contract v1"
        )
    current = contracts._is_static_rest_boundary_constant_acceleration_graph
    if getattr(current, "_constant_acceleration_stop_v1", False):
        _installed = True
        return
    _original = current

    def extended(graph: Any) -> bool:
        assert _original is not None
        return _original(graph) or is_static_constant_acceleration_stop_boundary_graph(
            graph
        )

    extended._constant_acceleration_stop_v1 = True  # type: ignore[attr-defined]
    contracts._is_static_rest_boundary_constant_acceleration_graph = extended
    _installed = True


__all__ = [
    "CONSTANT_ACCELERATION_STOP_BOUNDARY_VERSION",
    "install_constant_acceleration_stop_boundary_waiver",
    "is_static_constant_acceleration_stop_boundary_graph",
]
