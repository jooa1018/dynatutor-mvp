"""Exact static-boundary waiver for a spring natural-length endpoint.

The start/end labels in this profile are immutable state provenance, not timed
root events.  Only the complete compiler-produced energy graph with an exact
initial-rest law and exact zero-deformation endpoint receives an event-free
algebraic solve plan.  Every structural near miss keeps ordinary event handling
closed.
"""
from __future__ import annotations

import math
from typing import Any

from engine.mechanics.math_ast import (
    Add,
    DimensionVector,
    Equality,
    Inequality,
    LiteralNode,
    MathNode,
    Multiply,
    Power,
    SymbolRef,
)

SPRING_NATURAL_LENGTH_BOUNDARY_VERSION = "spring-natural-length-boundary-v1"

_installed = False
_original = None


def _applications_mirror(graph: Any, equations_by_id: dict[str, Any]) -> bool:
    return len(graph.applications) == len(equations_by_id) and all(
        len(application.equation_ids) == 1
        and application.equation_ids[0] in equations_by_id
        and application.law_id
        == equations_by_id[application.equation_ids[0]].law_id
        and application.scope == equations_by_id[application.equation_ids[0]].scope
        and application.source_quantity_ids
        == equations_by_id[application.equation_ids[0]].source_quantity_ids
        and application.source_evidence_ids
        == equations_by_id[application.equation_ids[0]].source_evidence_ids
        and application.assumption_ids
        == equations_by_id[application.equation_ids[0]].assumption_ids
        and application.constraint_ids
        == equations_by_id[application.equation_ids[0]].constraint_ids
        and application.generated_unknown_symbol_ids
        == equations_by_id[application.equation_ids[0]].generated_unknown_symbol_ids
        and application.complexity_cost
        == equations_by_id[application.equation_ids[0]].complexity_cost
        for application in graph.applications
    )


def _is_symbol(node: MathNode, symbol_id: str) -> bool:
    return isinstance(node, SymbolRef) and node.symbol_id == symbol_id


def _is_zero(node: MathNode, dimension: DimensionVector) -> bool:
    return (
        isinstance(node, LiteralNode)
        and node.value == 0.0
        and node.dimension == dimension
    )


def _is_square(node: MathNode, symbol_id: str) -> bool:
    return (
        isinstance(node, Power)
        and _is_symbol(node.base, symbol_id)
        and isinstance(node.exponent, LiteralNode)
        and node.exponent.value == 2.0
    )


def _is_half_product(
    node: MathNode,
    coefficient_id: str,
    squared_id: str,
) -> bool:
    if not isinstance(node, Multiply) or len(node.factors) != 3:
        return False
    return (
        sum(
            isinstance(item, LiteralNode) and item.value == 0.5
            for item in node.factors
        )
        == 1
        and sum(_is_symbol(item, coefficient_id) for item in node.factors) == 1
        and sum(_is_square(item, squared_id) for item in node.factors) == 1
    )


def _is_energy_equation(
    item: Any,
    output_id: str,
    coefficient_id: str,
    squared_id: str,
) -> bool:
    expression = item.expression
    return (
        isinstance(expression, Equality)
        and _is_symbol(expression.left, output_id)
        and _is_half_product(expression.right, coefficient_id, squared_id)
    )


def is_static_spring_natural_length_boundary_graph(graph: Any) -> bool:
    """Return true only for the exact algebraic natural-length energy graph."""

    from engine.mechanics.solver import contracts

    event_ids = contracts._graph_event_ids(graph)
    expected_laws = (
        "kinetic_energy",
        "kinetic_energy",
        "mechanical_energy_conservation",
        "spring_potential",
        "spring_potential",
        "spring_zero_deformation_endpoint",
        "state_at_rest",
        "translational_speed_nonnegative",
    )
    if (
        len(event_ids) != 2
        or graph.initial_conditions
        or graph.alternative_closed_sets
        or len(graph.constraints) != 4
        or len(graph.equations) != 8
        or len(graph.applications) != 8
        or tuple(sorted(item.law_id for item in graph.equations)) != expected_laws
        or tuple(sorted(item.law_id for item in graph.applications)) != expected_laws
        or graph.rank.equality_count != 7
        or graph.rank.inequality_count != 1
        or graph.rank.unknown_count != 7
        or graph.rank.structural_rank != 7
        or graph.rank.underdetermined
        or graph.rank.overdetermined
        or graph.rank.conflicting
    ):
        return False

    equations_by_id = {item.equation_id: item for item in graph.equations}
    if (
        len(equations_by_id) != len(graph.equations)
        or not _applications_mirror(graph, equations_by_id)
    ):
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
        set(by_role)
        != {"displacement", "energy", "mass", "speed", "stiffness", "velocity"}
        or len(by_role["displacement"]) != 2
        or len(by_role["energy"]) != 4
        or len(by_role["mass"]) != 1
        or len(by_role["speed"]) != 1
        or len(by_role["stiffness"]) != 1
        or len(by_role["velocity"]) != 1
        or len(graph.symbols) != 10
    ):
        return False

    mass = by_role["mass"][0]
    stiffness = by_role["stiffness"][0]
    final_speed = by_role["speed"][0]
    start_velocity = by_role["velocity"][0]
    displacements = tuple(by_role["displacement"])
    energies = tuple(by_role["energy"])
    unknowns = tuple(item for item in graph.symbols if item.known_si_value is None)
    if (
        len(unknowns) != 7
        or graph.query_symbol_id != final_speed.symbol.symbol_id
        or final_speed not in unknowns
        or start_velocity not in unknowns
        or mass.known_si_value is None
        or mass.known_si_value <= 0.0
        or stiffness.known_si_value is None
        or stiffness.known_si_value <= 0.0
        or start_velocity.subject_id != final_speed.subject_id
        or mass.subject_id != final_speed.subject_id
        or stiffness.subject_id == final_speed.subject_id
    ):
        return False

    interval_ids = {item.interval_id for item in graph.symbols}
    dynamic = tuple(
        item
        for item in graph.symbols
        if item is not mass and item is not stiffness
    )
    frame_ids = {item.frame_id for item in dynamic}
    if (
        len(interval_ids) != 1
        or None in interval_ids
        or len(frame_ids) != 1
        or None in frame_ids
        or mass.frame_id is not None
        or stiffness.frame_id is not None
        or mass.event_id is not None
        or stiffness.event_id is not None
    ):
        return False
    interval_id = next(iter(interval_ids))
    frame_id = next(iter(frame_ids))
    start_event_id = start_velocity.event_id
    end_event_id = final_speed.event_id
    if (
        start_event_id is None
        or end_event_id is None
        or start_event_id == end_event_id
        or {start_event_id, end_event_id} != set(event_ids)
    ):
        return False

    start_displacements = tuple(
        item for item in displacements if item.event_id == start_event_id
    )
    end_displacements = tuple(
        item for item in displacements if item.event_id == end_event_id
    )
    body_energies = tuple(
        item for item in energies if item.subject_id == final_speed.subject_id
    )
    spring_energies = tuple(
        item for item in energies if item.subject_id == stiffness.subject_id
    )
    if (
        len(start_displacements) != 1
        or len(end_displacements) != 1
        or start_displacements[0].known_si_value is None
        or end_displacements[0].known_si_value is not None
        or any(item.subject_id != stiffness.subject_id for item in displacements)
        or len(body_energies) != 2
        or len(spring_energies) != 2
        or {item.event_id for item in body_energies}
        != {start_event_id, end_event_id}
        or {item.event_id for item in spring_energies}
        != {start_event_id, end_event_id}
        or any(item.known_si_value is not None for item in energies)
    ):
        return False
    start_displacement = start_displacements[0]
    end_displacement = end_displacements[0]
    kinetic_start = next(
        item for item in body_energies if item.event_id == start_event_id
    )
    kinetic_end = next(
        item for item in body_energies if item.event_id == end_event_id
    )
    spring_start = next(
        item for item in spring_energies if item.event_id == start_event_id
    )
    spring_end = next(
        item for item in spring_energies if item.event_id == end_event_id
    )

    def equation(law_id: str, event_id: str | None) -> Any | None:
        matches = tuple(
            item
            for item in graph.equations
            if item.law_id == law_id and item.scope.event_id == event_id
        )
        return matches[0] if len(matches) == 1 else None

    rest = equation("state_at_rest", start_event_id)
    endpoint = equation("spring_zero_deformation_endpoint", end_event_id)
    potential_start = equation("spring_potential", start_event_id)
    potential_end = equation("spring_potential", end_event_id)
    kinetic_start_eq = equation("kinetic_energy", start_event_id)
    kinetic_end_eq = equation("kinetic_energy", end_event_id)
    conservation = equation("mechanical_energy_conservation", None)
    nonnegative = equation("translational_speed_nonnegative", end_event_id)
    exact_equations = (
        rest,
        endpoint,
        potential_start,
        potential_end,
        kinetic_start_eq,
        kinetic_end_eq,
        conservation,
        nonnegative,
    )
    if any(item is None for item in exact_equations):
        return False

    def exact_scope(
        item: Any,
        entity_ids: set[str],
        events: tuple[str, ...],
    ) -> bool:
        return (
            set(item.scope.entity_ids) == entity_ids
            and len(item.scope.entity_ids) == len(entity_ids)
            and not item.scope.point_ids
            and item.scope.frame_id == frame_id
            and item.scope.interval_id == interval_id
            and item.scope.event_ids == tuple(sorted(events))
        )

    body_id = final_speed.subject_id
    spring_id = stiffness.subject_id
    if (
        not exact_scope(rest, {body_id}, (start_event_id,))
        or not exact_scope(endpoint, {body_id, spring_id}, (end_event_id,))
        or not exact_scope(
            potential_start, {body_id, spring_id}, (start_event_id,)
        )
        or not exact_scope(potential_end, {body_id, spring_id}, (end_event_id,))
        or not exact_scope(kinetic_start_eq, {body_id}, (start_event_id,))
        or not exact_scope(kinetic_end_eq, {body_id}, (end_event_id,))
        or not exact_scope(
            conservation,
            {body_id, spring_id},
            (start_event_id, end_event_id),
        )
        or conservation.scope.event_id is not None
        or not exact_scope(nonnegative, {body_id}, (end_event_id,))
    ):
        return False

    rest_expression = rest.expression
    endpoint_expression = endpoint.expression
    nonnegative_expression = nonnegative.expression
    if (
        not isinstance(rest_expression, Equality)
        or not _is_symbol(rest_expression.left, start_velocity.symbol.symbol_id)
        or not _is_zero(rest_expression.right, start_velocity.symbol.dimension)
        or not isinstance(endpoint_expression, Equality)
        or not _is_symbol(endpoint_expression.left, end_displacement.symbol.symbol_id)
        or not _is_zero(endpoint_expression.right, end_displacement.symbol.dimension)
        or not _is_energy_equation(
            potential_start,
            spring_start.symbol.symbol_id,
            stiffness.symbol.symbol_id,
            start_displacement.symbol.symbol_id,
        )
        or not _is_energy_equation(
            potential_end,
            spring_end.symbol.symbol_id,
            stiffness.symbol.symbol_id,
            end_displacement.symbol.symbol_id,
        )
        or not _is_energy_equation(
            kinetic_start_eq,
            kinetic_start.symbol.symbol_id,
            mass.symbol.symbol_id,
            start_velocity.symbol.symbol_id,
        )
        or not _is_energy_equation(
            kinetic_end_eq,
            kinetic_end.symbol.symbol_id,
            mass.symbol.symbol_id,
            final_speed.symbol.symbol_id,
        )
        or not isinstance(nonnegative_expression, Inequality)
        or getattr(
            nonnegative_expression.relation,
            "value",
            nonnegative_expression.relation,
        )
        != "ge"
        or not _is_symbol(
            nonnegative_expression.left, final_speed.symbol.symbol_id
        )
        or not _is_zero(
            nonnegative_expression.right, final_speed.symbol.dimension
        )
    ):
        return False

    conservation_expression = conservation.expression
    if (
        not isinstance(conservation_expression, Equality)
        or not isinstance(conservation_expression.left, Add)
        or not isinstance(conservation_expression.right, Add)
        or len(conservation_expression.left.terms) != 2
        or len(conservation_expression.right.terms) != 2
        or {
            item.symbol_id
            for item in conservation_expression.left.terms
            if isinstance(item, SymbolRef)
        }
        != {kinetic_start.symbol.symbol_id, spring_start.symbol.symbol_id}
        or {
            item.symbol_id
            for item in conservation_expression.right.terms
            if isinstance(item, SymbolRef)
        }
        != {kinetic_end.symbol.symbol_id, spring_end.symbol.symbol_id}
    ):
        return False

    source_ids = {
        rest.equation_id: {start_velocity.quantity_id},
        endpoint.equation_id: {end_displacement.quantity_id},
        potential_start.equation_id: {
            spring_start.quantity_id,
            stiffness.quantity_id,
            start_displacement.quantity_id,
        },
        potential_end.equation_id: {
            spring_end.quantity_id,
            stiffness.quantity_id,
            end_displacement.quantity_id,
        },
        kinetic_start_eq.equation_id: {
            kinetic_start.quantity_id,
            mass.quantity_id,
            start_velocity.quantity_id,
        },
        kinetic_end_eq.equation_id: {
            kinetic_end.quantity_id,
            mass.quantity_id,
            final_speed.quantity_id,
        },
        conservation.equation_id: {
            kinetic_start.quantity_id,
            kinetic_end.quantity_id,
            spring_start.quantity_id,
            spring_end.quantity_id,
        },
        nonnegative.equation_id: {final_speed.quantity_id},
    }
    if any(
        set(item.source_quantity_ids) != source_ids[item.equation_id]
        or len(item.source_quantity_ids) != len(source_ids[item.equation_id])
        or not item.source_evidence_ids
        or item.generated_unknown_symbol_ids
        for item in graph.equations
    ):
        return False
    if (
        len(conservation.assumption_ids) != 1
        or any(
            item.assumption_ids
            for item in graph.equations
            if item is not conservation
        )
    ):
        return False

    constraints = {item.constraint_id: item for item in graph.constraints}
    if (
        len(constraints) != 4
        or sorted(item.constraint_kind for item in graph.constraints)
        != ["state_boundary", "state_final", "state_initial", "state_initial"]
        or any(
            not item.source_evidence_ids
            or item.scope.interval_id != interval_id
            or item.scope.frame_id != frame_id
            or item.scope.event_id not in set(event_ids)
            or item.scope.event_ids != (item.scope.event_id,)
            for item in graph.constraints
        )
    ):
        return False
    boundary_ids = {
        item.constraint_id
        for item in graph.constraints
        if item.constraint_kind == "state_boundary"
    }
    if (
        set(endpoint.constraint_ids) != boundary_ids
        or len(rest.constraint_ids) != 1
        or rest.constraint_ids[0] not in constraints
        or constraints[rest.constraint_ids[0]].constraint_kind != "state_initial"
        or any(
            set(item.constraint_ids) != set(constraints)
            for item in graph.equations
            if item is not rest and item is not endpoint
        )
    ):
        return False

    selected = tuple(
        sorted(
            item.equation_id
            for item in graph.equations
            if isinstance(item.expression, Equality)
        )
    )
    unknown_ids = {item.symbol.symbol_id for item in unknowns}
    expected_incidence = {
        (item.equation_id, symbol_id)
        for item in graph.equations
        if isinstance(item.expression, Equality)
        for symbol_id in contracts._ordinary_symbol_ids(item.expression) & unknown_ids
    }
    actual_incidence = {
        (item.equation_id, item.symbol_id) for item in graph.incidence
    }
    return (
        graph.selected_equation_ids == selected
        and actual_incidence == expected_incidence
        and len(graph.incidence) == len(expected_incidence)
    )


def install_spring_natural_length_boundary_waiver() -> None:
    """Extend the static work-energy recognizer once, fail-closed."""

    global _installed, _original
    if _installed:
        return
    from engine.mechanics.solver import contracts

    if contracts.SOLVER_CONTRACT_VERSION != "mechanics-solver-contract-v1":
        raise RuntimeError(
            "spring natural-length waiver requires reviewed solver contract v1"
        )
    current = contracts._is_static_particle_work_energy_boundary_graph
    if getattr(current, "_spring_natural_length_boundary_v1", False):
        _installed = True
        return
    _original = current

    def extended(graph: Any) -> bool:
        assert _original is not None
        return _original(graph) or is_static_spring_natural_length_boundary_graph(
            graph
        )

    extended._spring_natural_length_boundary_v1 = True  # type: ignore[attr-defined]
    contracts._is_static_particle_work_energy_boundary_graph = extended
    _installed = True


__all__ = [
    "SPRING_NATURAL_LENGTH_BOUNDARY_VERSION",
    "install_spring_natural_length_boundary_waiver",
    "is_static_spring_natural_length_boundary_graph",
]
