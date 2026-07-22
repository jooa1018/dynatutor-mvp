"""Immutable, data-only contracts for the Stage 4 mechanics solver boundary.

Nothing in this module executes expressions or chooses a backend.  A future
planner must derive these records exclusively from the embedded immutable
``EquationGraph``.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
from typing import Annotated, Iterable, Literal, TypeAlias, Union

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

from engine.mechanics.compiler.contracts import EquationGraph
from engine.mechanics.math_ast import (
    Add,
    Cross,
    Derivative,
    Divide,
    Dot,
    DimensionVector,
    Equality,
    Inequality,
    Integral,
    LiteralNode,
    MathNode,
    Multiply,
    Negate,
    Norm,
    Power,
    Sqrt,
    Subtract,
    SymbolRef,
    VectorNode,
)


SOLVER_CONTRACT_VERSION = "mechanics-solver-contract-v1"
SOLVER_POLICY_VERSION = "mechanics-solver-policy-v1"

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
DisplayOnlyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]


def _finite_not_bool(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("boolean is not a finite number")
    return value


FiniteFloat = Annotated[float, BeforeValidator(_finite_not_bool), Field(allow_inf_nan=False, ge=-1.0e300, le=1.0e300)]
PositiveFiniteFloat = Annotated[float, BeforeValidator(_finite_not_bool), Field(allow_inf_nan=False, gt=0.0, le=1.0e12)]
SIValue: TypeAlias = Union[FiniteFloat, Annotated[tuple[FiniteFloat, ...], Field(min_length=1, max_length=16)]]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always", str_strip_whitespace=True)


def _is_sorted_unique(values: tuple[str, ...]) -> bool:
    return values == tuple(sorted(set(values)))


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _direct_math_children(node: MathNode) -> tuple[MathNode, ...]:
    """Inspect only typed AST models; strings are never interpreted."""

    children: list[MathNode] = []

    def collect(value: object) -> None:
        if isinstance(value, MathNode):
            children.append(value)
        elif isinstance(value, BaseModel):
            for field_name in type(value).model_fields:
                collect(getattr(value, field_name))
        elif isinstance(value, tuple):
            for item in value:
                collect(item)

    for name in type(node).model_fields:
        if name != "dimension":
            collect(getattr(node, name))
    return tuple(children)


def _walk_math_nodes(expression: MathNode) -> tuple[tuple[MathNode, int], ...]:
    stack: list[tuple[MathNode, int]] = [(expression, 1)]
    result: list[tuple[MathNode, int]] = []
    while stack:
        node, depth = stack.pop()
        result.append((node, depth))
        if len(result) > 4096 or depth > 64:
            raise ValueError("equation AST exceeds the solver-contract inspection bound")
        stack.extend((child, depth + 1) for child in reversed(_direct_math_children(node)))
    return tuple(result)


def _ordinary_symbol_ids(expression: MathNode) -> set[str]:
    return {
        node.symbol_id
        for node, _ in _walk_math_nodes(expression)
        if isinstance(node, SymbolRef)
    }


def _polynomial_degree(expression: MathNode, unknowns: set[str]) -> int | None:
    """Return a bounded syntactic degree, or ``None`` when not certifiable."""

    if isinstance(expression, SymbolRef):
        return 1 if expression.symbol_id in unknowns else 0
    if isinstance(expression, LiteralNode):
        return 0
    if isinstance(expression, (VectorNode, Dot, Cross, Norm, Integral)):
        return None
    if isinstance(expression, Add):
        values = tuple(_polynomial_degree(item, unknowns) for item in expression.terms)
        return None if any(item is None for item in values) else max((item for item in values if item is not None), default=0)
    if isinstance(expression, Subtract):
        left = _polynomial_degree(expression.left, unknowns)
        right = _polynomial_degree(expression.right, unknowns)
        return None if left is None or right is None else max(left, right)
    if isinstance(expression, Multiply):
        values = tuple(_polynomial_degree(item, unknowns) for item in expression.factors)
        if any(item is None for item in values):
            return None
        degree = sum(item for item in values if item is not None)
        return degree if degree <= 64 else None
    if isinstance(expression, Divide):
        numerator = _polynomial_degree(expression.numerator, unknowns)
        denominator = _polynomial_degree(expression.denominator, unknowns)
        return numerator if numerator is not None and denominator == 0 else None
    if isinstance(expression, Power):
        base = _polynomial_degree(expression.base, unknowns)
        exponent = expression.exponent
        if base is None or not isinstance(exponent, LiteralNode):
            return None
        rounded = round(exponent.value)
        if exponent.value != rounded or rounded < 0:
            return None
        degree = base * int(rounded)
        return degree if degree <= 64 else None
    if isinstance(expression, Negate):
        return _polynomial_degree(expression.operand, unknowns)
    if isinstance(expression, Sqrt):
        # A principal root of an unknown-free radicand is an exact coefficient,
        # not a nonlinear solve branch.  Unknown-dependent roots remain outside
        # the polynomial planner and therefore keep the nonlinear fail-closed
        # path.
        operand = _polynomial_degree(expression.operand, unknowns)
        return 0 if operand == 0 else None
    if isinstance(expression, Derivative):
        return _polynomial_degree(expression.expression, unknowns)
    if isinstance(expression, (Equality, Inequality)):
        left = _polynomial_degree(expression.left, unknowns)
        right = _polynomial_degree(expression.right, unknowns)
        return None if left is None or right is None else max(left, right)
    return None


def _graph_event_ids(graph: EquationGraph) -> tuple[str, ...]:
    ids: list[str] = []
    for item in (*graph.equations, *graph.constraints, *graph.initial_conditions):
        scope = item.scope
        if scope.event_id is not None:
            ids.append(scope.event_id)
        ids.extend(scope.event_ids)
    for application in graph.applications:
        if application.scope.event_id is not None:
            ids.append(application.scope.event_id)
        ids.extend(application.scope.event_ids)
    ids.extend(item.event_id for item in graph.symbols if item.event_id is not None)
    return _sorted_unique(ids)


def _is_static_collision_boundary_graph(graph: EquationGraph) -> bool:
    """Recognize only the closed algebraic before/after impact boundary graph.

    Collision boundary labels are provenance, not timed root events.  This
    predicate is intentionally graph-only and exact: every near miss retains
    the ordinary timed-event fail-closed behavior.
    """

    event_ids = _graph_event_ids(graph)
    expected_laws = {
        "system_momentum_conservation",
        "direct_restitution",
    }
    if (
        len(event_ids) != 2
        or graph.constraints
        or graph.initial_conditions
        or graph.alternative_closed_sets
        or len(graph.equations) != 2
        or len(graph.applications) != 2
        or {item.law_id for item in graph.equations} != expected_laws
        or {item.law_id for item in graph.applications} != expected_laws
        or any(not isinstance(item.expression, Equality) for item in graph.equations)
        or set(graph.selected_equation_ids)
        != {item.equation_id for item in graph.equations}
        or graph.rank.equality_count != 2
        or graph.rank.inequality_count != 0
        or graph.rank.unknown_count != 2
        or graph.rank.structural_rank != 2
        or graph.rank.underdetermined
        or graph.rank.conflicting
    ):
        return False

    scoped = (*graph.equations, *graph.applications)
    scope_pairs = {
        (item.scope.frame_id, item.scope.interval_id) for item in scoped
    }
    if (
        len(scope_pairs) != 1
        or next(iter(scope_pairs))[0] is None
        or next(iter(scope_pairs))[1] is None
        or any(
            item.scope.event_id is not None
            or item.scope.event_ids != event_ids
            for item in scoped
        )
    ):
        return False
    frame_id, interval_id = next(iter(scope_pairs))

    equations_by_law = {item.law_id: item for item in graph.equations}
    applications_by_law = {item.law_id: item for item in graph.applications}
    if any(
        application.equation_ids != (equations_by_law[law_id].equation_id,)
        or application.source_quantity_ids
        != equations_by_law[law_id].source_quantity_ids
        or application.assumption_ids != equations_by_law[law_id].assumption_ids
        or application.constraint_ids
        or equations_by_law[law_id].constraint_ids
        or application.generated_unknown_symbol_ids
        or equations_by_law[law_id].generated_unknown_symbol_ids
        or not application.source_evidence_ids
        or not equations_by_law[law_id].source_evidence_ids
        for law_id, application in applications_by_law.items()
    ):
        return False
    momentum = equations_by_law["system_momentum_conservation"]
    restitution = equations_by_law["direct_restitution"]
    if (
        len(momentum.assumption_ids) != 1
        or restitution.assumption_ids
        or momentum.complexity_cost != 6
        or restitution.complexity_cost != 5
        or momentum.dimension != DimensionVector(mass=1, length=1, time=-1)
        or restitution.dimension != DimensionVector(length=1, time=-1)
    ):
        return False

    roles = [item.quantity_role for item in graph.symbols]
    if (
        len(graph.symbols) != 7
        or roles.count("mass") != 2
        or roles.count("velocity") != 4
        or roles.count("coefficient_restitution") != 1
        or any(role in {"time", "duration"} for role in roles)
        or any(item.generated or item.quantity_id is None for item in graph.symbols)
    ):
        return False
    masses = tuple(item for item in graph.symbols if item.quantity_role == "mass")
    velocities = tuple(
        item for item in graph.symbols if item.quantity_role == "velocity"
    )
    coefficients = tuple(
        item
        for item in graph.symbols
        if item.quantity_role == "coefficient_restitution"
    )
    participant_ids = {item.subject_id for item in masses}
    if (
        None in participant_ids
        or len(participant_ids) != 2
        or any(
            item.known_si_value is None
            or item.event_id is not None
            or item.frame_id is not None
            or item.interval_id is not None
            for item in masses
        )
        or len(coefficients) != 1
        or coefficients[0].known_si_value is None
        or coefficients[0].event_id is not None
        or coefficients[0].frame_id != frame_id
        or coefficients[0].interval_id != interval_id
        or any(
            item.subject_id not in participant_ids
            or item.frame_id != frame_id
            or item.interval_id != interval_id
            or item.event_id not in event_ids
            for item in velocities
        )
    ):
        return False
    velocity_by_event = {
        event_id: tuple(item for item in velocities if item.event_id == event_id)
        for event_id in event_ids
    }
    if any(
        len(items) != 2
        or {item.subject_id for item in items} != participant_ids
        for items in velocity_by_event.values()
    ):
        return False
    known_events = tuple(
        event_id
        for event_id, items in velocity_by_event.items()
        if all(item.known_si_value is not None for item in items)
    )
    unknown_events = tuple(
        event_id
        for event_id, items in velocity_by_event.items()
        if all(item.known_si_value is None for item in items)
    )
    if len(known_events) != 1 or len(unknown_events) != 1:
        return False
    unknown_symbols = {
        item.symbol.symbol_id for item in velocity_by_event[unknown_events[0]]
    }
    if (
        graph.query_symbol_id not in unknown_symbols
        or _graph_unknown_ids(graph) != tuple(sorted(unknown_symbols))
    ):
        return False

    mass_quantity_ids = {item.quantity_id for item in masses}
    velocity_quantity_ids = {item.quantity_id for item in velocities}
    coefficient_quantity_id = coefficients[0].quantity_id
    if (
        set(momentum.source_quantity_ids)
        != mass_quantity_ids | velocity_quantity_ids
        or len(momentum.source_quantity_ids) != 6
        or set(restitution.source_quantity_ids)
        != velocity_quantity_ids | {coefficient_quantity_id}
        or len(restitution.source_quantity_ids) != 5
        or _ordinary_symbol_ids(momentum.expression)
        != {
            item.symbol.symbol_id for item in (*masses, *velocities)
        }
        or _ordinary_symbol_ids(restitution.expression)
        != {
            item.symbol.symbol_id for item in (*velocities, *coefficients)
        }
    ):
        return False

    if not (
        isinstance(momentum.expression.left, Add)
        and isinstance(momentum.expression.right, Add)
        and len(momentum.expression.left.terms) == 2
        and len(momentum.expression.right.terms) == 2
        and all(
            isinstance(term, Multiply) and len(term.factors) == 2
            for term in (
                *momentum.expression.left.terms,
                *momentum.expression.right.terms,
            )
        )
        and isinstance(restitution.expression.left, Subtract)
        and isinstance(restitution.expression.right, Negate)
        and isinstance(restitution.expression.right.operand, Multiply)
        and len(restitution.expression.right.operand.factors) == 2
        and any(
            isinstance(item, Subtract)
            for item in restitution.expression.right.operand.factors
        )
        and any(
            isinstance(item, SymbolRef)
            and item.symbol_id == coefficients[0].symbol.symbol_id
            for item in restitution.expression.right.operand.factors
        )
    ):
        return False

    # Exact compiler-generated topology and provenance mirror.  Law labels and
    # symbol-set equality are not sufficient authority for this waiver.
    entity_ids = momentum.scope.entity_ids
    if (
        len(entity_ids) != 3
        or momentum.scope.point_ids
        or restitution.scope != momentum.scope
        or any(
            application.scope != equations_by_law[law_id].scope
            or application.source_evidence_ids
            != equations_by_law[law_id].source_evidence_ids
            or application.complexity_cost
            != equations_by_law[law_id].complexity_cost
            for law_id, application in applications_by_law.items()
        )
        or graph.rank.overdetermined
    ):
        return False

    mass_dimension = DimensionVector(mass=1)
    velocity_dimension = DimensionVector(length=1, time=-1)
    scalar_nodes = all(
        item.symbol.shape.value == "scalar"
        and item.point_id is None
        and item.symbol.vector_length is None
        for item in graph.symbols
    )
    coefficient = coefficients[0]
    system_ids = set(entity_ids) - participant_ids
    if (
        not scalar_nodes
        or len(system_ids) != 1
        or coefficient.subject_id not in system_ids
        or coefficient.symbol.dimension != DimensionVector()
        or type(coefficient.known_si_value) is not float
        or not math.isfinite(coefficient.known_si_value)
        or not 0.0 <= coefficient.known_si_value <= 1.0
        or any(
            item.symbol.dimension != mass_dimension
            or type(item.known_si_value) is not float
            or not math.isfinite(item.known_si_value)
            or item.known_si_value <= 0.0
            for item in masses
        )
        or any(item.symbol.dimension != velocity_dimension for item in velocities)
        or any(
            type(item.known_si_value) is not float
            or not math.isfinite(item.known_si_value)
            or item.known_si_value < 0.0
            for item in velocity_by_event[known_events[0]]
        )
    ):
        return False

    exact_incidence = {
        (equation.equation_id, symbol_id)
        for equation in graph.equations
        for symbol_id in unknown_symbols
    }
    if {
        (edge.equation_id, edge.symbol_id) for edge in graph.incidence
    } != exact_incidence or len(graph.incidence) != 4:
        return False

    symbol_nodes = {
        item.symbol.symbol_id: item for item in graph.symbols
    }

    def signed_symbol(node: MathNode) -> tuple[str, int] | None:
        sign = 1
        if isinstance(node, Negate):
            sign = -1
            node = node.operand
            if isinstance(node, Negate):
                return None
        if not isinstance(node, SymbolRef):
            return None
        symbol_node = symbol_nodes.get(node.symbol_id)
        if symbol_node is None or node.dimension != symbol_node.symbol.dimension:
            return None
        return node.symbol_id, sign

    def momentum_side(
        expression: MathNode,
        event_id: str,
    ) -> dict[str, tuple[str, str, int]] | None:
        if not isinstance(expression, Add) or len(expression.terms) != 2:
            return None
        result: dict[str, tuple[str, str, int]] = {}
        for term in expression.terms:
            if not isinstance(term, Multiply) or len(term.factors) != 2:
                return None
            direct = tuple(
                item for item in term.factors if isinstance(item, SymbolRef)
            )
            mass_refs = tuple(
                item
                for item in direct
                if symbol_nodes.get(item.symbol_id) in masses
            )
            if len(mass_refs) != 1:
                return None
            mass_node = symbol_nodes[mass_refs[0].symbol_id]
            velocity_factor = next(
                (item for item in term.factors if item is not mass_refs[0]),
                None,
            )
            signed = signed_symbol(velocity_factor) if velocity_factor is not None else None
            if signed is None:
                return None
            velocity_node = symbol_nodes.get(signed[0])
            if (
                velocity_node not in velocities
                or velocity_node.event_id != event_id
                or velocity_node.subject_id != mass_node.subject_id
                or mass_node.subject_id in result
            ):
                return None
            result[mass_node.subject_id] = (
                mass_refs[0].symbol_id,
                signed[0],
                signed[1],
            )
        return result

    known_side = momentum_side(momentum.expression.left, known_events[0])
    unknown_side = momentum_side(momentum.expression.right, unknown_events[0])
    if (
        known_side is None
        or unknown_side is None
        or set(known_side) != participant_ids
        or set(unknown_side) != participant_ids
        or any(
            known_side[subject_id][0] != unknown_side[subject_id][0]
            or unknown_side[subject_id][2] != 1
            for subject_id in participant_ids
        )
    ):
        return False

    def velocity_difference(
        expression: MathNode,
        event_id: str,
    ) -> tuple[tuple[str, int], tuple[str, int]] | None:
        if not isinstance(expression, Subtract):
            return None
        left = signed_symbol(expression.left)
        right = signed_symbol(expression.right)
        if left is None or right is None:
            return None
        left_node = symbol_nodes.get(left[0])
        right_node = symbol_nodes.get(right[0])
        if (
            left_node not in velocities
            or right_node not in velocities
            or left_node.event_id != event_id
            or right_node.event_id != event_id
            or left_node.subject_id == right_node.subject_id
        ):
            return None
        # The signs are part of the compiler-emitted physical components and
        # must agree subject-by-subject across the two boundary differences.
        return (
            (left_node.subject_id, left[1]),
            (right_node.subject_id, right[1]),
        )

    left_order = velocity_difference(
        restitution.expression.left,
        unknown_events[0],
    )
    right = restitution.expression.right
    if not isinstance(right, Negate) or not isinstance(right.operand, Multiply):
        return False
    factors = right.operand.factors
    if len(factors) != 2:
        return False
    coefficient_factors = tuple(
        item
        for item in factors
        if isinstance(item, SymbolRef)
        and item.symbol_id == coefficient.symbol.symbol_id
    )
    difference_factors = tuple(item for item in factors if isinstance(item, Subtract))
    if len(coefficient_factors) != 1 or len(difference_factors) != 1:
        return False
    right_order = velocity_difference(difference_factors[0], known_events[0])
    if left_order is None or right_order is None:
        return False
    if (
        tuple(item[0] for item in left_order)
        != tuple(item[0] for item in right_order)
        or any(
            sign != unknown_side[subject_id][2]
            for subject_id, sign in left_order
        )
        or any(
            sign != known_side[subject_id][2]
            for subject_id, sign in right_order
        )
    ):
        return False
    return True


def _is_static_constant_acceleration_boundary_graph(graph: EquationGraph) -> bool:
    """Recognize the exact closed 1D constant-acceleration endpoint graph.

    Start/end labels in this graph identify state boundaries; they are not
    timed root events.  The recognition is intentionally graph-only and exact:
    it does not inspect problem text, metadata, family labels, fixture IDs, or
    legacy output, and every structural near miss retains ordinary timed-event
    fail-closed behavior.
    """

    event_ids = _graph_event_ids(graph)
    velocity_law = "particle_constant_acceleration_velocity"
    position_law = "particle_constant_acceleration_position"
    expected_laws = {velocity_law, position_law}
    if (
        len(event_ids) != 2
        or graph.constraints
        or graph.initial_conditions
        or graph.alternative_closed_sets
        or len(graph.equations) != 2
        or len(graph.applications) != 2
        or {item.law_id for item in graph.equations} != expected_laws
        or {item.law_id for item in graph.applications} != expected_laws
        or any(not isinstance(item.expression, Equality) for item in graph.equations)
        or set(graph.selected_equation_ids)
        != {item.equation_id for item in graph.equations}
        or graph.rank.equality_count != 2
        or graph.rank.inequality_count != 0
        or graph.rank.unknown_count != 2
        or graph.rank.structural_rank != 2
        or graph.rank.underdetermined
        or graph.rank.conflicting
    ):
        return False

    symbols_by_role: dict[str, list[object]] = {}
    for item in graph.symbols:
        if item.generated or item.point_id is not None or item.quantity_role is None:
            return False
        symbols_by_role.setdefault(item.quantity_role, []).append(item)
    if set(symbols_by_role) != {
        "acceleration",
        "displacement",
        "duration",
        "velocity",
    }:
        return False
    if (
        len(symbols_by_role["acceleration"]) != 1
        or len(symbols_by_role["displacement"]) != 1
        or len(symbols_by_role["duration"]) != 1
        or len(symbols_by_role["velocity"]) != 2
        or len(graph.symbols) != 5
    ):
        return False

    acceleration = symbols_by_role["acceleration"][0]
    displacement = symbols_by_role["displacement"][0]
    duration = symbols_by_role["duration"][0]
    velocities = tuple(symbols_by_role["velocity"])
    subjects = {
        item.subject_id
        for item in (acceleration, displacement, duration, *velocities)
    }
    intervals = {
        item.interval_id
        for item in (acceleration, displacement, duration, *velocities)
    }
    if (
        len(subjects) != 1
        or None in subjects
        or len(intervals) != 1
        or None in intervals
        or acceleration.event_id is not None
        or displacement.event_id is not None
        or duration.event_id is not None
        or {item.event_id for item in velocities} != set(event_ids)
        or any(item.event_id is None for item in velocities)
        or acceleration.frame_id is None
        or displacement.frame_id != acceleration.frame_id
        or any(item.frame_id != acceleration.frame_id for item in velocities)
        or duration.frame_id not in {None, acceleration.frame_id}
    ):
        return False
    subject_id = next(iter(subjects))
    interval_id = next(iter(intervals))
    frame_id = acceleration.frame_id
    velocity_by_event = {item.event_id: item for item in velocities}

    equations_by_law = {item.law_id: item for item in graph.equations}
    applications_by_law = {item.law_id: item for item in graph.applications}
    if any(
        application.equation_ids != (equations_by_law[law_id].equation_id,)
        or application.source_quantity_ids
        != equations_by_law[law_id].source_quantity_ids
        or application.assumption_ids != equations_by_law[law_id].assumption_ids
        or application.constraint_ids
        or equations_by_law[law_id].constraint_ids
        or application.generated_unknown_symbol_ids
        or equations_by_law[law_id].generated_unknown_symbol_ids
        or application.source_evidence_ids
        != equations_by_law[law_id].source_evidence_ids
        or application.complexity_cost != equations_by_law[law_id].complexity_cost
        or application.scope != equations_by_law[law_id].scope
        for law_id, application in applications_by_law.items()
    ):
        return False

    velocity = equations_by_law[velocity_law]
    position = equations_by_law[position_law]
    assumption_ids = velocity.assumption_ids
    if (
        len(assumption_ids) != 1
        or position.assumption_ids != assumption_ids
        or velocity.scope.entity_ids != (subject_id,)
        or velocity.scope.point_ids
        or velocity.scope.frame_id != frame_id
        or velocity.scope.interval_id != interval_id
        or velocity.scope.event_id is not None
        or velocity.scope.event_ids != event_ids
        or position.scope.entity_ids != (subject_id,)
        or position.scope.point_ids
        or position.scope.frame_id != frame_id
        or position.scope.interval_id != interval_id
        or position.scope.event_id is None
        or position.scope.event_ids != (position.scope.event_id,)
        or position.scope.event_id not in event_ids
    ):
        return False

    end_event_id = next(
        (
            identifier
            for identifier in event_ids
            if identifier != position.scope.event_id
        ),
        None,
    )
    if end_event_id is None:
        return False
    start_velocity = velocity_by_event.get(position.scope.event_id)
    end_velocity = velocity_by_event.get(end_event_id)
    if start_velocity is None or end_velocity is None:
        return False

    def ref(item: object) -> str:
        return item.symbol.symbol_id

    expected_velocity_sources = tuple(sorted({
        acceleration.quantity_id,
        duration.quantity_id,
        start_velocity.quantity_id,
        end_velocity.quantity_id,
    }))
    expected_position_sources = tuple(sorted({
        acceleration.quantity_id,
        displacement.quantity_id,
        duration.quantity_id,
        start_velocity.quantity_id,
    }))
    if (
        velocity.source_quantity_ids != expected_velocity_sources
        or position.source_quantity_ids != expected_position_sources
    ):
        return False

    velocity_expression = velocity.expression
    if (
        not isinstance(velocity_expression.left, SymbolRef)
        or velocity_expression.left.symbol_id != ref(end_velocity)
        or not isinstance(velocity_expression.right, Add)
        or len(velocity_expression.right.terms) != 2
    ):
        return False
    velocity_terms = velocity_expression.right.terms
    start_terms = tuple(
        item
        for item in velocity_terms
        if isinstance(item, SymbolRef)
        and item.symbol_id == ref(start_velocity)
    )
    product_terms = tuple(
        item for item in velocity_terms if isinstance(item, Multiply)
    )
    if len(start_terms) != 1 or len(product_terms) != 1:
        return False
    velocity_product = product_terms[0]
    if {
        item.symbol_id
        for item in velocity_product.factors
        if isinstance(item, SymbolRef)
    } != {ref(acceleration), ref(duration)} or len(velocity_product.factors) != 2:
        return False

    position_expression = position.expression
    if (
        not isinstance(position_expression.left, SymbolRef)
        or position_expression.left.symbol_id != ref(displacement)
        or not isinstance(position_expression.right, Add)
        or len(position_expression.right.terms) != 2
    ):
        return False
    position_products = tuple(
        item
        for item in position_expression.right.terms
        if isinstance(item, Multiply)
    )
    if len(position_products) != 2:
        return False

    linear_products = tuple(
        item
        for item in position_products
        if len(item.factors) == 2
        and {
            factor.symbol_id
            for factor in item.factors
            if isinstance(factor, SymbolRef)
        } == {ref(start_velocity), ref(duration)}
    )
    quadratic_products = tuple(
        item for item in position_products if item not in linear_products
    )
    if len(linear_products) != 1 or len(quadratic_products) != 1:
        return False
    quadratic = quadratic_products[0]
    literals = tuple(
        item for item in quadratic.factors if isinstance(item, LiteralNode)
    )
    acceleration_refs = tuple(
        item
        for item in quadratic.factors
        if isinstance(item, SymbolRef)
        and item.symbol_id == ref(acceleration)
    )
    powers = tuple(item for item in quadratic.factors if isinstance(item, Power))
    if (
        len(quadratic.factors) != 3
        or len(literals) != 1
        or literals[0].value != 0.5
        or len(acceleration_refs) != 1
        or len(powers) != 1
        or not isinstance(powers[0].base, SymbolRef)
        or powers[0].base.symbol_id != ref(duration)
        or not isinstance(powers[0].exponent, LiteralNode)
        or powers[0].exponent.value != 2.0
    ):
        return False
    return graph.query_symbol_id in {
        ref(acceleration),
        ref(displacement),
        ref(duration),
        ref(start_velocity),
        ref(end_velocity),
    }


def _is_static_projectile_boundary_graph(graph: EquationGraph) -> bool:
    """Recognize one exact algebraic 2-D projectile endpoint graph.

    Launch/landing or launch/turnaround labels remain immutable provenance.  The
    waiver is granted only when the complete graph mirrors the compiler's typed
    x/y constant-acceleration, gravity, height, and positive-duration laws.
    Every structural near miss keeps ordinary timed-event fail-closed behavior.
    """

    event_ids = _graph_event_ids(graph)
    velocity_law = "particle_constant_acceleration_velocity"
    position_law = "particle_constant_acceleration_position"
    gravity_law = "uniform_gravity_acceleration"
    height_law = "particle_height_displacement"
    time_law = "elapsed_time_positive"
    expected_counts = {
        velocity_law: 2,
        position_law: 2,
        gravity_law: 1,
        height_law: 1,
        time_law: 1,
    }
    equation_counts = {
        law_id: sum(item.law_id == law_id for item in graph.equations)
        for law_id in expected_counts
    }
    application_counts = {
        law_id: sum(item.law_id == law_id for item in graph.applications)
        for law_id in expected_counts
    }
    if (
        len(event_ids) != 2
        or graph.constraints
        or graph.initial_conditions
        or graph.alternative_closed_sets
        or len(graph.equations) != 7
        or len(graph.applications) != 7
        or equation_counts != expected_counts
        or application_counts != expected_counts
        or any(
            item.law_id not in expected_counts for item in graph.equations
        )
        or any(
            item.law_id not in expected_counts for item in graph.applications
        )
        or graph.rank.equality_count != 6
        or graph.rank.inequality_count != 1
        or graph.rank.unknown_count not in {4, 5}
        or graph.rank.structural_rank != graph.rank.unknown_count
        or graph.rank.underdetermined
        or graph.rank.overdetermined
        or graph.rank.conflicting
    ):
        return False

    equations_by_law = {
        law_id: tuple(
            item for item in graph.equations if item.law_id == law_id
        )
        for law_id in expected_counts
    }
    applications_by_law = {
        law_id: tuple(
            item for item in graph.applications if item.law_id == law_id
        )
        for law_id in expected_counts
    }
    equation_by_id = {item.equation_id: item for item in graph.equations}
    for law_id, applications in applications_by_law.items():
        for application in applications:
            if len(application.equation_ids) != 1:
                return False
            equation = equation_by_id.get(application.equation_ids[0])
            if (
                equation is None
                or equation.law_id != law_id
                or application.source_quantity_ids != equation.source_quantity_ids
                or application.assumption_ids != equation.assumption_ids
                or application.constraint_ids != equation.constraint_ids
                or application.generated_unknown_symbol_ids
                != equation.generated_unknown_symbol_ids
                or application.source_evidence_ids
                != equation.source_evidence_ids
                or application.complexity_cost != equation.complexity_cost
                or application.scope != equation.scope
            ):
                return False

    by_role: dict[str, tuple[object, ...]] = {
        role: tuple(item for item in graph.symbols if item.quantity_role == role)
        for role in {
            "acceleration",
            "displacement",
            "duration",
            "velocity",
            "gravity",
            "height",
        }
    }
    if (
        any(item.generated or item.point_id is not None for item in graph.symbols)
        or set(item.quantity_role for item in graph.symbols)
        != set(by_role)
        or len(graph.symbols) != 12
        or len(by_role["acceleration"]) != 2
        or len(by_role["displacement"]) != 2
        or len(by_role["duration"]) != 1
        or len(by_role["velocity"]) != 4
        or len(by_role["gravity"]) != 1
        or len(by_role["height"]) != 2
    ):
        return False

    duration = by_role["duration"][0]
    gravity = by_role["gravity"][0]
    accelerations = by_role["acceleration"]
    displacements = by_role["displacement"]
    velocities = by_role["velocity"]
    heights = by_role["height"]
    projectile_subjects = {
        item.subject_id
        for item in (*accelerations, *displacements, duration, *velocities, *heights)
    }
    intervals = {
        item.interval_id
        for item in (*accelerations, *displacements, duration, *velocities, *heights)
    }
    frames = {
        item.frame_id
        for item in (*accelerations, *displacements, *velocities, *heights)
    }
    if (
        len(projectile_subjects) != 1
        or None in projectile_subjects
        or len(intervals) != 1
        or None in intervals
        or len(frames) != 1
        or None in frames
        or duration.frame_id is not None
        or duration.event_id is not None
        or gravity.subject_id in projectile_subjects
        or gravity.event_id is not None
        or gravity.known_si_value is None
        or any(item.known_si_value is None for item in accelerations)
        or sum(item.known_si_value is None for item in displacements) not in {1, 2}
        or {item.event_id for item in heights} != set(event_ids)
        or sum(item.known_si_value is None for item in heights) not in {0, 1}
    ):
        return False
    subject_id = next(iter(projectile_subjects))
    interval_id = next(iter(intervals))
    frame_id = next(iter(frames))
    velocity_by_event = {
        event_id: tuple(item for item in velocities if item.event_id == event_id)
        for event_id in event_ids
    }
    known_events = tuple(
        event_id
        for event_id, items in velocity_by_event.items()
        if len(items) == 2 and all(item.known_si_value is not None for item in items)
    )
    if len(known_events) != 1:
        return False
    start_event_id = known_events[0]
    end_event_id = next((item for item in event_ids if item != start_event_id), None)
    if end_event_id is None or len(velocity_by_event[end_event_id]) != 2:
        return False
    end_unknown_count = sum(
        item.known_si_value is None for item in velocity_by_event[end_event_id]
    )
    if end_unknown_count not in {1, 2}:
        return False

    gravity_equation = equations_by_law[gravity_law][0]
    height_equation = equations_by_law[height_law][0]
    time_equation = equations_by_law[time_law][0]
    if (
        not isinstance(gravity_equation.expression, Equality)
        or not isinstance(gravity_equation.expression.left, SymbolRef)
        or not isinstance(gravity_equation.expression.right, Negate)
        or not isinstance(gravity_equation.expression.right.operand, SymbolRef)
        or gravity_equation.expression.right.operand.symbol_id
        != gravity.symbol.symbol_id
        or gravity_equation.source_quantity_ids
        != tuple(sorted({
            gravity.quantity_id,
            next(
                (
                    item.quantity_id
                    for item in accelerations
                    if item.symbol.symbol_id
                    == gravity_equation.expression.left.symbol_id
                ),
                "",
            ),
        }))
        or gravity_equation.scope.frame_id != frame_id
        or gravity_equation.scope.interval_id != interval_id
        or subject_id not in gravity_equation.scope.entity_ids
    ):
        return False
    vertical_acceleration = next(
        (
            item
            for item in accelerations
            if item.symbol.symbol_id == gravity_equation.expression.left.symbol_id
        ),
        None,
    )
    if vertical_acceleration is None:
        return False

    if (
        not isinstance(height_equation.expression, Equality)
        or not isinstance(height_equation.expression.left, SymbolRef)
        or not isinstance(height_equation.expression.right, Subtract)
        or not isinstance(height_equation.expression.right.left, SymbolRef)
        or not isinstance(height_equation.expression.right.right, SymbolRef)
        or height_equation.scope.entity_ids != (subject_id,)
        or height_equation.scope.frame_id != frame_id
        or height_equation.scope.interval_id != interval_id
        or height_equation.scope.event_id is not None
        or height_equation.scope.event_ids != event_ids
    ):
        return False
    vertical_displacement = next(
        (
            item
            for item in displacements
            if item.symbol.symbol_id == height_equation.expression.left.symbol_id
        ),
        None,
    )
    height_by_symbol = {item.symbol.symbol_id: item for item in heights}
    end_height = height_by_symbol.get(height_equation.expression.right.left.symbol_id)
    start_height = height_by_symbol.get(height_equation.expression.right.right.symbol_id)
    if (
        vertical_displacement is None
        or end_height is None
        or start_height is None
        or end_height.event_id != end_event_id
        or start_height.event_id != start_event_id
        or height_equation.source_quantity_ids
        != tuple(sorted({
            vertical_displacement.quantity_id,
            start_height.quantity_id,
            end_height.quantity_id,
        }))
    ):
        return False

    vertical_velocity_equation = next(
        (
            item
            for item in equations_by_law[velocity_law]
            if vertical_acceleration.quantity_id in item.source_quantity_ids
        ),
        None,
    )
    if (
        vertical_velocity_equation is None
        or not isinstance(vertical_velocity_equation.expression, Equality)
        or not isinstance(vertical_velocity_equation.expression.left, SymbolRef)
    ):
        return False
    vertical_end_velocity = next(
        (
            item
            for item in velocity_by_event[end_event_id]
            if item.symbol.symbol_id
            == vertical_velocity_equation.expression.left.symbol_id
        ),
        None,
    )
    if vertical_end_velocity is None:
        return False
    horizontal_end_velocities = tuple(
        item
        for item in velocity_by_event[end_event_id]
        if item is not vertical_end_velocity
    )
    horizontal_displacements = tuple(
        item for item in displacements if item is not vertical_displacement
    )
    if len(horizontal_end_velocities) != 1 or len(horizontal_displacements) != 1:
        return False
    horizontal_end_velocity = horizontal_end_velocities[0]
    horizontal_displacement = horizontal_displacements[0]
    landing_mode = (
        vertical_displacement.known_si_value is not None
        and start_height.known_si_value is not None
        and end_height.known_si_value is not None
        and vertical_end_velocity.known_si_value is None
        and horizontal_end_velocity.known_si_value is None
        and horizontal_displacement.known_si_value is None
        and end_unknown_count == 2
    )
    turnaround_mode = (
        vertical_displacement.known_si_value is None
        and start_height.known_si_value is not None
        and end_height.known_si_value is None
        and vertical_end_velocity.known_si_value == 0.0
        and horizontal_end_velocity.known_si_value is None
        and horizontal_displacement.known_si_value is None
        and end_unknown_count == 1
    )
    if not (landing_mode or turnaround_mode):
        return False

    if (
        not isinstance(time_equation.expression, Inequality)
        or time_equation.expression.relation.value != "gt"
        or not isinstance(time_equation.expression.left, SymbolRef)
        or time_equation.expression.left.symbol_id != duration.symbol.symbol_id
        or not isinstance(time_equation.expression.right, LiteralNode)
        or time_equation.expression.right.value != 0.0
        or time_equation.source_quantity_ids != (duration.quantity_id,)
        or len(time_equation.assumption_ids) != 1
        or time_equation.scope.entity_ids != (subject_id,)
        or time_equation.scope.interval_id != interval_id
    ):
        return False

    def exact_velocity_expression(equation: object, acceleration: object) -> bool:
        expression = equation.expression
        if (
            not isinstance(expression, Equality)
            or not isinstance(expression.left, SymbolRef)
            or not isinstance(expression.right, Add)
            or len(expression.right.terms) != 2
        ):
            return False
        end_velocity = next(
            (
                item
                for item in velocity_by_event[end_event_id]
                if item.symbol.symbol_id == expression.left.symbol_id
            ),
            None,
        )
        if end_velocity is None:
            return False
        start_refs = tuple(
            item
            for item in expression.right.terms
            if isinstance(item, SymbolRef)
        )
        products = tuple(
            item for item in expression.right.terms if isinstance(item, Multiply)
        )
        if len(start_refs) != 1 or len(products) != 1:
            return False
        start_velocity = next(
            (
                item
                for item in velocity_by_event[start_event_id]
                if item.symbol.symbol_id == start_refs[0].symbol_id
            ),
            None,
        )
        product = products[0]
        if (
            start_velocity is None
            or len(product.factors) != 2
            or {
                item.symbol_id
                for item in product.factors
                if isinstance(item, SymbolRef)
            }
            != {acceleration.symbol.symbol_id, duration.symbol.symbol_id}
            or equation.source_quantity_ids
            != tuple(sorted({
                acceleration.quantity_id,
                duration.quantity_id,
                start_velocity.quantity_id,
                end_velocity.quantity_id,
            }))
            or equation.scope.entity_ids != (subject_id,)
            or equation.scope.frame_id != frame_id
            or equation.scope.interval_id != interval_id
            or equation.scope.event_id is not None
            or equation.scope.event_ids != event_ids
        ):
            return False
        return True

    def exact_position_expression(equation: object, acceleration: object) -> bool:
        expression = equation.expression
        if (
            not isinstance(expression, Equality)
            or not isinstance(expression.left, SymbolRef)
            or not isinstance(expression.right, Add)
            or len(expression.right.terms) != 2
        ):
            return False
        displacement = next(
            (
                item
                for item in displacements
                if item.symbol.symbol_id == expression.left.symbol_id
            ),
            None,
        )
        if displacement is None:
            return False
        products = tuple(
            item for item in expression.right.terms if isinstance(item, Multiply)
        )
        if len(products) != 2:
            return False
        linear = tuple(
            item
            for item in products
            if len(item.factors) == 2
            and any(
                isinstance(factor, SymbolRef)
                and factor.symbol_id == duration.symbol.symbol_id
                for factor in item.factors
            )
            and any(
                isinstance(factor, SymbolRef)
                and factor.symbol_id
                in {
                    velocity.symbol.symbol_id
                    for velocity in velocity_by_event[start_event_id]
                }
                for factor in item.factors
            )
        )
        quadratic = tuple(item for item in products if item not in linear)
        if len(linear) != 1 or len(quadratic) != 1:
            return False
        start_velocity = next(
            (
                velocity
                for velocity in velocity_by_event[start_event_id]
                if any(
                    isinstance(factor, SymbolRef)
                    and factor.symbol_id == velocity.symbol.symbol_id
                    for factor in linear[0].factors
                )
            ),
            None,
        )
        q = quadratic[0]
        literals = tuple(item for item in q.factors if isinstance(item, LiteralNode))
        acceleration_refs = tuple(
            item
            for item in q.factors
            if isinstance(item, SymbolRef)
            and item.symbol_id == acceleration.symbol.symbol_id
        )
        powers = tuple(item for item in q.factors if isinstance(item, Power))
        if (
            start_velocity is None
            or len(q.factors) != 3
            or len(literals) != 1
            or literals[0].value != 0.5
            or len(acceleration_refs) != 1
            or len(powers) != 1
            or not isinstance(powers[0].base, SymbolRef)
            or powers[0].base.symbol_id != duration.symbol.symbol_id
            or not isinstance(powers[0].exponent, LiteralNode)
            or powers[0].exponent.value != 2.0
            or equation.source_quantity_ids
            != tuple(sorted({
                acceleration.quantity_id,
                displacement.quantity_id,
                duration.quantity_id,
                start_velocity.quantity_id,
            }))
            or equation.scope.entity_ids != (subject_id,)
            or equation.scope.frame_id != frame_id
            or equation.scope.interval_id != interval_id
            or equation.scope.event_id != start_event_id
            or equation.scope.event_ids != (start_event_id,)
        ):
            return False
        return True

    velocity_equations = equations_by_law[velocity_law]
    position_equations = equations_by_law[position_law]
    for acceleration in accelerations:
        matching_velocity = tuple(
            item
            for item in velocity_equations
            if acceleration.quantity_id in item.source_quantity_ids
        )
        matching_position = tuple(
            item
            for item in position_equations
            if acceleration.quantity_id in item.source_quantity_ids
        )
        if (
            len(matching_velocity) != 1
            or len(matching_position) != 1
            or not exact_velocity_expression(matching_velocity[0], acceleration)
            or not exact_position_expression(matching_position[0], acceleration)
            or matching_velocity[0].assumption_ids
            != matching_position[0].assumption_ids
            or len(matching_velocity[0].assumption_ids) != 1
        ):
            return False

    selected_expected = {
        item.equation_id
        for law_id in (velocity_law, position_law)
        for item in equations_by_law[law_id]
        if any(
            symbol_id
            in {
                symbol.symbol.symbol_id
                for symbol in graph.symbols
                if symbol.known_si_value is None
            }
            for symbol_id in _ordinary_symbol_ids(item.expression)
        )
    }
    if turnaround_mode:
        selected_expected.add(height_equation.equation_id)
    unknown_symbols = {
        item.symbol.symbol_id
        for item in graph.symbols
        if item.known_si_value is None
    }
    expected_unknowns = {
        duration.symbol.symbol_id,
        horizontal_displacement.symbol.symbol_id,
        horizontal_end_velocity.symbol.symbol_id,
    }
    if landing_mode:
        expected_unknowns.add(vertical_end_velocity.symbol.symbol_id)
    else:
        expected_unknowns.update(
            {
                vertical_displacement.symbol.symbol_id,
                end_height.symbol.symbol_id,
            }
        )
    return (
        set(graph.selected_equation_ids) == selected_expected
        and graph.query_symbol_id in unknown_symbols
        and unknown_symbols == expected_unknowns
    )

def _graph_plan_event_ids(graph: EquationGraph) -> tuple[str, ...]:
    """Return timed plan events while retaining raw graph boundary scopes."""

    return (
        ()
        if (
            _is_static_collision_boundary_graph(graph)
            or _is_static_constant_acceleration_boundary_graph(graph)
            or _is_static_projectile_boundary_graph(graph)
        )
        else _graph_event_ids(graph)
    )


def _graph_evidence_ids(graph: EquationGraph) -> tuple[str, ...]:
    return _sorted_unique(
        evidence_id
        for item in (*graph.equations, *graph.constraints, *graph.initial_conditions, *graph.applications)
        for evidence_id in item.source_evidence_ids
    )


def _graph_unknown_ids(graph: EquationGraph) -> tuple[str, ...]:
    ordinary = {
        symbol_id
        for equation in graph.equations
        for symbol_id in _ordinary_symbol_ids(equation.expression)
    }
    return tuple(
        sorted(
            item.symbol.symbol_id
            for item in graph.symbols
            if item.known_si_value is None
            and (
                item.symbol.symbol_id == graph.query_symbol_id
                or item.quantity_role != "time"
                or item.symbol.symbol_id in ordinary
            )
        )
    )


def _selected_structural_rank(
    graph: EquationGraph,
    selected_equation_ids: tuple[str, ...],
    unknown_symbol_ids: tuple[str, ...],
) -> int:
    """Compute a bounded bipartite matching over selected graph incidence."""

    unknowns = set(unknown_symbol_ids)
    adjacency = {
        equation_id: tuple(sorted({
            edge.symbol_id
            for edge in graph.incidence
            if edge.equation_id == equation_id and edge.symbol_id in unknowns
        }))
        for equation_id in selected_equation_ids
    }
    matched_by_symbol: dict[str, str] = {}

    def augment(equation_id: str, seen: set[str]) -> bool:
        for symbol_id in adjacency[equation_id]:
            if symbol_id in seen:
                continue
            seen.add(symbol_id)
            owner = matched_by_symbol.get(symbol_id)
            if owner is None or augment(owner, seen):
                matched_by_symbol[symbol_id] = equation_id
                return True
        return False

    return sum(augment(equation_id, set()) for equation_id in selected_equation_ids)


class SolveBackendKind(str, Enum):
    linear_symbolic = "linear_symbolic"
    polynomial_symbolic = "polynomial_symbolic"
    nonlinear_symbolic = "nonlinear_symbolic"
    numeric_root = "numeric_root"
    ode_ivp = "ode_ivp"
    event_root = "event_root"
    constrained_optimization = "constrained_optimization"
    piecewise = "piecewise"


class SolvePhase(str, Enum):
    planning = "planning"
    translation = "translation"
    symbolic = "symbolic"
    numeric = "numeric"
    candidate_generation = "candidate_generation"
    verification = "verification"


class SolverBudget(FrozenModel):
    max_equations: StrictInt = Field(default=128, ge=1, le=512)
    max_unknowns: StrictInt = Field(default=64, ge=1, le=256)
    max_candidates: StrictInt = Field(default=128, ge=1, le=1024)
    max_ast_nodes: StrictInt = Field(default=4096, ge=1, le=65_536)
    max_ast_depth: StrictInt = Field(default=24, ge=1, le=64)
    max_operation_cost: StrictInt = Field(default=100_000, ge=1, le=10_000_000)
    symbolic_time_limit_s: PositiveFiniteFloat = 5.0
    numeric_time_limit_s: PositiveFiniteFloat = 10.0
    verification_time_limit_s: PositiveFiniteFloat = 5.0
    timeout_termination_grace_s: PositiveFiniteFloat = Field(default=0.5, le=5.0)
    max_numeric_starts: StrictInt = Field(default=32, ge=1, le=1024)
    max_numeric_iterations: StrictInt = Field(default=1000, ge=1, le=1_000_000)
    absolute_tolerance: PositiveFiniteFloat = 1.0e-10
    relative_tolerance: PositiveFiniteFloat = 1.0e-9
    residual_tolerance: PositiveFiniteFloat = 1.0e-8
    constraint_tolerance: PositiveFiniteFloat = 1.0e-9


class SolverTimeout(FrozenModel):
    phase: SolvePhase
    backend: SolveBackendKind
    limit_s: PositiveFiniteFloat
    elapsed_s: PositiveFiniteFloat

    @model_validator(mode="after")
    def elapsed_reached_limit(self) -> "SolverTimeout":
        if self.elapsed_s < self.limit_s:
            raise ValueError("timeout elapsed time must reach the configured limit")
        return self


class GraphStructureFeatures(FrozenModel):
    equality_count: StrictInt = Field(ge=0, le=512)
    inequality_count: StrictInt = Field(ge=0, le=512)
    constraint_count: StrictInt = Field(ge=0, le=512)
    initial_condition_count: StrictInt = Field(ge=0, le=128)
    unknown_count: StrictInt = Field(ge=0, le=256)
    max_ast_nodes_per_equation: StrictInt = Field(ge=0, le=65_536)
    total_ast_nodes: StrictInt = Field(ge=0, le=65_536)
    max_ast_depth: StrictInt = Field(ge=0, le=64)
    total_operation_cost: StrictInt = Field(ge=0, le=10_000_000)
    polynomial_degree: StrictInt | None = Field(default=None, ge=0, le=64)
    has_derivative: StrictBool = False
    has_integral: StrictBool = False
    has_vector_operation: StrictBool = False
    has_piecewise: StrictBool = False
    has_event_condition: StrictBool = False
    has_nonlinear_operation: StrictBool = False


def primary_backend_for_structure(structure: GraphStructureFeatures) -> SolveBackendKind:
    """Return the one closed, graph-structure-only primary backend."""

    if structure.has_piecewise:
        return SolveBackendKind.piecewise
    if structure.has_derivative:
        return SolveBackendKind.ode_ivp
    if structure.has_integral or structure.has_vector_operation:
        return SolveBackendKind.nonlinear_symbolic
    if structure.polynomial_degree is None:
        return SolveBackendKind.nonlinear_symbolic
    if structure.polynomial_degree <= 1:
        return SolveBackendKind.linear_symbolic
    return SolveBackendKind.polynomial_symbolic


def numeric_fallback_for_structure(structure: GraphStructureFeatures) -> SolveBackendKind | None:
    """Return the sole deterministic fallback, if this structure has one."""

    if primary_backend_for_structure(structure) is SolveBackendKind.nonlinear_symbolic:
        return SolveBackendKind.numeric_root
    return None


# Descriptive aliases retained as a small public planner-facing vocabulary.
derive_primary_backend = primary_backend_for_structure
derive_numeric_fallback = numeric_fallback_for_structure


def _graph_structure(graph: EquationGraph, unknown_ids: tuple[str, ...]) -> GraphStructureFeatures:
    metrics = tuple(_walk_math_nodes(item.expression) for item in graph.equations)
    degrees = tuple(_polynomial_degree(item.expression, set(unknown_ids)) for item in graph.equations)
    polynomial_degree = None if any(item is None for item in degrees) else max(degrees, default=0)
    nodes = tuple(node for expression in metrics for node, _ in expression)
    return GraphStructureFeatures(
        equality_count=sum(isinstance(item.expression, Equality) for item in graph.equations),
        inequality_count=sum(isinstance(item.expression, Inequality) for item in graph.equations),
        constraint_count=len(graph.constraints),
        initial_condition_count=len(graph.initial_conditions),
        unknown_count=len(unknown_ids),
        max_ast_nodes_per_equation=max((len(item) for item in metrics), default=0),
        total_ast_nodes=sum(len(item) for item in metrics),
        max_ast_depth=max((depth for item in metrics for _, depth in item), default=0),
        total_operation_cost=sum(item.complexity_cost for item in graph.equations),
        polynomial_degree=polynomial_degree,
        has_derivative=any(isinstance(item, Derivative) for item in nodes),
        has_integral=any(isinstance(item, Integral) for item in nodes),
        has_vector_operation=any(isinstance(item, (VectorNode, Dot, Cross, Norm)) for item in nodes),
        has_piecewise=any(getattr(item, "op", None) == "piecewise" for item in nodes),
        has_event_condition=bool(_graph_event_ids(graph)),
        # Unknown-dependent syntax whose degree is not certified is treated
        # conservatively as nonlinear rather than allowing a false linear flag.
        has_nonlinear_operation=any(
            degree is None and bool(_ordinary_symbol_ids(equation.expression) & set(unknown_ids))
            or degree is not None and degree > 1
            for equation, degree in zip(graph.equations, degrees)
        ),
    )


class SolvePlan(FrozenModel):
    contract_version: Literal[SOLVER_CONTRACT_VERSION] = SOLVER_CONTRACT_VERSION
    policy_version: Literal[SOLVER_POLICY_VERSION] = SOLVER_POLICY_VERSION
    graph: EquationGraph
    graph_fingerprint: Fingerprint | None = None
    plan_fingerprint: Fingerprint | None = None
    query_id: Identifier
    query_symbol_id: Identifier
    selected_equality_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=512)
    inequality_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    constraint_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    initial_condition_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    event_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    allowed_source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    unknown_symbol_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    known_symbol_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    structure: GraphStructureFeatures
    primary_backend: SolveBackendKind
    permitted_numeric_fallback: SolveBackendKind | None = None
    budget: SolverBudget

    @model_validator(mode="after")
    def validate_plan_sets(self) -> "SolvePlan":
        if "graph_fingerprint" in self.model_fields_set:
            if self.graph_fingerprint is None or self.graph_fingerprint != self.graph.fingerprint:
                raise ValueError("graph fingerprint must exactly match the embedded graph")
        else:
            object.__setattr__(self, "graph_fingerprint", self.graph.fingerprint)

        collections = (
            self.selected_equality_ids, self.inequality_ids, self.constraint_ids,
            self.initial_condition_ids, self.event_ids, self.allowed_source_evidence_ids,
            self.unknown_symbol_ids, self.known_symbol_ids,
        )
        if not all(_is_sorted_unique(values) for values in collections):
            raise ValueError("plan ID collections must be sorted and unique")

        equation_ids = tuple(item.equation_id for item in self.graph.equations)
        constraint_ids = tuple(item.constraint_id for item in self.graph.constraints)
        condition_ids = tuple(item.condition_id for item in self.graph.initial_conditions)
        symbol_ids = tuple(item.symbol.symbol_id for item in self.graph.symbols)
        if any(len(set(values)) != len(values) for values in (equation_ids, constraint_ids, condition_ids, symbol_ids)):
            raise ValueError("embedded graph authority must have unique node IDs")
        equations = {item.equation_id: item for item in self.graph.equations}
        if not _is_sorted_unique(self.graph.selected_equation_ids):
            raise ValueError("embedded graph selected equation IDs must be canonical")
        if any(
            identifier not in equations
            or not isinstance(equations[identifier].expression, Equality)
            for identifier in self.graph.selected_equation_ids
        ):
            raise ValueError("embedded graph selected set must contain only existing equalities")
        for closed_set in self.graph.alternative_closed_sets:
            if not _is_sorted_unique(closed_set) or any(
                identifier not in equations
                or not isinstance(equations[identifier].expression, Equality)
                for identifier in closed_set
            ):
                raise ValueError("embedded graph alternative sets must be canonical existing equalities")
        constraint_id_set = set(constraint_ids)
        if any(not set(item.constraint_ids) <= constraint_id_set for item in self.graph.equations):
            raise ValueError("embedded graph equation constraint provenance must resolve")
        if any(item.equation_id not in equations for item in self.graph.constraints):
            raise ValueError("embedded graph constraint equations must resolve")
        if any(not set(item.equation_ids) <= set(equations) for item in self.graph.applications):
            raise ValueError("embedded graph application equations must resolve")
        if any(not set(item.constraint_ids) <= constraint_id_set for item in self.graph.applications):
            raise ValueError("embedded graph application constraint provenance must resolve")

        expected_equalities = tuple(self.graph.selected_equation_ids)
        expected_inequalities = _sorted_unique(
            item.equation_id for item in self.graph.equations if isinstance(item.expression, Inequality)
        )
        expected_constraints = _sorted_unique(constraint_ids)
        expected_conditions = _sorted_unique(condition_ids)
        expected_events = _graph_plan_event_ids(self.graph)
        expected_evidence = _graph_evidence_ids(self.graph)
        expected_unknowns = _graph_unknown_ids(self.graph)
        expected_known = _sorted_unique(
            item.symbol.symbol_id for item in self.graph.symbols if item.known_si_value is not None
        )
        if self.query_id != self.graph.query_id or self.query_symbol_id != self.graph.query_symbol_id:
            raise ValueError("plan query must exactly match the embedded graph")
        expected = (
            expected_equalities, expected_inequalities, expected_constraints,
            expected_conditions, expected_events, expected_evidence,
            expected_unknowns, expected_known,
        )
        if collections != expected:
            raise ValueError("plan-derived ID collections must exactly match the embedded graph")
        if self.query_symbol_id not in self.unknown_symbol_ids:
            raise ValueError("query symbol must be one of the graph-derived unknown symbols")
        if set(self.unknown_symbol_ids) & set(self.known_symbol_ids):
            raise ValueError("known and unknown symbols must be disjoint")

        exact_structure = _graph_structure(self.graph, expected_unknowns)
        if self.structure != exact_structure:
            raise ValueError("declared structure must exactly match bounded graph-derived features")
        if (
            self.graph.rank.equality_count != exact_structure.equality_count
            or self.graph.rank.inequality_count != exact_structure.inequality_count
            or self.graph.rank.unknown_count != exact_structure.unknown_count
            or self.graph.rank.structural_rank
            > min(exact_structure.equality_count, exact_structure.unknown_count)
        ):
            raise ValueError("embedded graph rank counts or structural rank contradict graph content")
        if (
            self.graph.rank.underdetermined
            or self.graph.rank.conflicting
            or self.graph.rank.structural_rank < exact_structure.unknown_count
            or len(self.selected_equality_ids) < exact_structure.unknown_count
        ):
            raise ValueError("a solve plan requires sufficient non-conflicting structural rank")
        if _selected_structural_rank(
            self.graph,
            self.selected_equality_ids,
            expected_unknowns,
        ) < exact_structure.unknown_count:
            raise ValueError("selected equality set must structurally cover every unknown symbol")
        exact_primary = primary_backend_for_structure(exact_structure)
        exact_fallback = numeric_fallback_for_structure(exact_structure)
        if self.primary_backend is not exact_primary:
            raise ValueError("primary backend must exactly match graph-only routing policy")
        if self.permitted_numeric_fallback is not exact_fallback:
            raise ValueError("numeric fallback must exactly match graph-only routing policy")
        if exact_structure.equality_count + exact_structure.inequality_count > self.budget.max_equations:
            raise ValueError("graph exceeds equation budget")
        if exact_structure.unknown_count > self.budget.max_unknowns:
            raise ValueError("graph exceeds unknown budget")
        if exact_structure.total_ast_nodes > self.budget.max_ast_nodes or exact_structure.max_ast_depth > self.budget.max_ast_depth:
            raise ValueError("graph exceeds AST budget")
        if exact_structure.total_operation_cost > self.budget.max_operation_cost:
            raise ValueError("graph exceeds operation budget")

        canonical = json.dumps(
            self.model_dump(mode="json", exclude={"plan_fingerprint"}),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        expected_fingerprint = hashlib.sha256(canonical).hexdigest()
        if "plan_fingerprint" in self.model_fields_set:
            if self.plan_fingerprint is None or self.plan_fingerprint != expected_fingerprint:
                raise ValueError("plan fingerprint must exactly match canonical plan data")
        else:
            object.__setattr__(self, "plan_fingerprint", expected_fingerprint)
        return self


class CandidateValue(FrozenModel):
    symbol_id: Identifier
    value_si: SIValue


class SolverCandidate(FrozenModel):
    candidate_id: Identifier | None = None
    generation_index: StrictInt = Field(ge=0, le=1023)
    root_index: StrictInt = Field(ge=0, le=1023)
    root_multiplicity: StrictInt = Field(default=1, ge=1, le=1024)
    graph_fingerprint: Fingerprint
    plan_fingerprint: Fingerprint
    backend: SolveBackendKind
    approximate: StrictBool
    equation_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=512)
    branch_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    values: tuple[CandidateValue, ...] = Field(min_length=1, max_length=256)
    query_symbol_id: Identifier
    query_value_si: SIValue
    symbolic_display_only: DisplayOnlyText | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "SolverCandidate":
        if not _is_sorted_unique(self.equation_ids) or not _is_sorted_unique(self.branch_ids):
            raise ValueError("candidate provenance IDs must be sorted and unique")
        symbols = tuple(item.symbol_id for item in self.values)
        if not _is_sorted_unique(symbols):
            raise ValueError("candidate values must have sorted unique symbol IDs")
        by_symbol = {item.symbol_id: item.value_si for item in self.values}
        if by_symbol.get(self.query_symbol_id) != self.query_value_si:
            raise ValueError("candidate query value must exactly match its typed symbol value")
        expected_candidate_id = canonical_candidate_id(self)
        if "candidate_id" in self.model_fields_set:
            if self.candidate_id is None or self.candidate_id != expected_candidate_id:
                raise ValueError("candidate ID must be the canonical authoritative-data ID")
        else:
            object.__setattr__(self, "candidate_id", expected_candidate_id)
        return self


def canonical_candidate_sha256(candidate: SolverCandidate) -> str:
    """Hash every authoritative candidate field except its self-derived ID."""

    canonical = json.dumps(
        candidate.model_dump(mode="json", exclude={"candidate_id"}),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def canonical_candidate_id(candidate: SolverCandidate) -> str:
    """Render the bounded deterministic ID for one candidate record."""

    return f"candidate_{canonical_candidate_sha256(candidate)[:32]}"


def make_solver_candidate(**authoritative_data: object) -> SolverCandidate:
    """Validated constructor that derives, rather than trusts, candidate ID."""

    return SolverCandidate(**authoritative_data)


# A factory spelling that reads naturally at backend call sites.
create_solver_candidate = make_solver_candidate


class CandidateGenerationRecord(FrozenModel):
    generation_index: StrictInt = Field(ge=0, le=1023)
    candidate_id: Identifier
    backend: SolveBackendKind
    root_index: StrictInt = Field(ge=0, le=1023)
    branch_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    authoritative_sha256: Fingerprint

    @model_validator(mode="after")
    def validate_record(self) -> "CandidateGenerationRecord":
        if not _is_sorted_unique(self.branch_ids):
            raise ValueError("manifest branch IDs must be sorted and unique")
        if self.candidate_id != f"candidate_{self.authoritative_sha256[:32]}":
            raise ValueError("manifest candidate ID must derive from its authoritative SHA-256")
        return self


def candidate_generation_manifest(
    candidates: Iterable[SolverCandidate],
) -> tuple[CandidateGenerationRecord, ...]:
    """Build the exact ordered manifest for already validated candidates."""

    return tuple(
        CandidateGenerationRecord(
            generation_index=item.generation_index,
            candidate_id=item.candidate_id,
            backend=item.backend,
            root_index=item.root_index,
            branch_ids=item.branch_ids,
            authoritative_sha256=canonical_candidate_sha256(item),
        )
        for item in candidates
    )


class CandidateCoverage(str, Enum):
    exhaustive_symbolic = "exhaustive_symbolic"
    bounded_numeric = "bounded_numeric"
    incomplete = "incomplete"


class CandidateSet(FrozenModel):
    graph_fingerprint: Fingerprint
    plan_fingerprint: Fingerprint
    coverage: CandidateCoverage
    generation_complete: StrictBool
    generated_count: StrictInt = Field(ge=0, le=1024)
    candidates: tuple[SolverCandidate, ...] = Field(default_factory=tuple, max_length=1024)
    manifest: tuple[CandidateGenerationRecord, ...] = Field(max_length=1024)

    @property
    def auto_selectable(self) -> bool:
        return self.generation_complete and self.coverage is CandidateCoverage.exhaustive_symbolic

    @model_validator(mode="after")
    def validate_candidates(self) -> "CandidateSet":
        if self.generated_count != len(self.candidates) or self.generated_count != len(self.manifest):
            raise ValueError("generated count, manifest, and retained candidates must exactly agree")
        if self.coverage is CandidateCoverage.incomplete and self.generation_complete:
            raise ValueError("incomplete coverage cannot claim generation completion")
        if self.coverage is not CandidateCoverage.incomplete and not self.generation_complete:
            raise ValueError("non-complete generation must use incomplete coverage")
        ids = tuple(item.candidate_id for item in self.candidates)
        indices = tuple(item.generation_index for item in self.candidates)
        slots = tuple((item.backend, item.root_index, item.branch_ids) for item in self.candidates)
        if len(set(ids)) != len(ids) or len(set(indices)) != len(indices) or len(set(slots)) != len(slots):
            raise ValueError("candidate IDs, generation indices, and root slots must be unique")
        if indices != tuple(range(len(self.candidates))):
            raise ValueError("candidate generation indices must be contiguous from zero in retained order")
        group_counts: dict[tuple[SolveBackendKind, tuple[str, ...]], int] = {}
        for candidate in self.candidates:
            group = (candidate.backend, candidate.branch_ids)
            expected_root_index = group_counts.get(group, 0)
            if candidate.root_index != expected_root_index:
                raise ValueError("root indices must be contiguous from zero within each backend/branch group")
            group_counts[group] = expected_root_index + 1
        exact_manifest = candidate_generation_manifest(self.candidates)
        if self.manifest != exact_manifest:
            raise ValueError("candidate manifest must exactly bind every retained candidate in order")
        if any(item.graph_fingerprint != self.graph_fingerprint or item.plan_fingerprint != self.plan_fingerprint for item in self.candidates):
            raise ValueError("all candidates must bind to this graph and plan")
        symbolic_backends = {
            SolveBackendKind.linear_symbolic,
            SolveBackendKind.polynomial_symbolic,
            SolveBackendKind.nonlinear_symbolic,
            SolveBackendKind.piecewise,
        }
        if self.coverage is CandidateCoverage.exhaustive_symbolic:
            if any(item.backend not in symbolic_backends or item.approximate for item in self.candidates):
                raise ValueError("exhaustive symbolic coverage accepts only exact symbolic candidates")
        if self.coverage is CandidateCoverage.bounded_numeric:
            numeric_backends = {
                SolveBackendKind.numeric_root,
                SolveBackendKind.ode_ivp,
                SolveBackendKind.event_root,
                SolveBackendKind.constrained_optimization,
            }
            if any(item.backend not in numeric_backends or not item.approximate for item in self.candidates):
                raise ValueError("bounded numeric coverage accepts only approximate numeric candidates")
        return self


class CandidateRejectionReason(str, Enum):
    equation_residual = "equation_residual"
    numerical_integration_residual = "numerical_integration_residual"
    independent_equation_mismatch = "independent_equation_mismatch"
    inequality_violation = "inequality_violation"
    constraint_violation = "constraint_violation"
    event_order_violation = "event_order_violation"
    initial_boundary_violation = "initial_boundary_violation"
    conservation_violation = "conservation_violation"
    source_evidence_mismatch = "source_evidence_mismatch"
    nonfinite_value = "nonfinite_value"
    unit_mismatch = "unit_mismatch"
    query_unbound = "query_unbound"
    physical_domain_violation = "physical_domain_violation"
    nonnegative_time_violation = "nonnegative_time_violation"
    positive_parameter_violation = "positive_parameter_violation"
    physical_regime_violation = "physical_regime_violation"
    duplicate_root = "duplicate_root"
    verification_inconclusive = "verification_inconclusive"


class CandidateRejection(FrozenModel):
    candidate_id: Identifier
    reason: CandidateRejectionReason
    check_id: Identifier
    equation_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    constraint_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    event_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    symbol_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)
    initial_condition_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=128)
    source_evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=512)

    @model_validator(mode="after")
    def ordered_provenance(self) -> "CandidateRejection":
        provenance = (
            self.equation_ids,
            self.constraint_ids,
            self.event_ids,
            self.symbol_ids,
            self.initial_condition_ids,
            self.source_evidence_ids,
        )
        if not all(_is_sorted_unique(values) for values in provenance):
            raise ValueError("rejection provenance must be sorted and unique")
        if not any(provenance) and self.reason not in {
            CandidateRejectionReason.nonfinite_value,
            CandidateRejectionReason.unit_mismatch,
            CandidateRejectionReason.query_unbound,
            CandidateRejectionReason.duplicate_root,
            CandidateRejectionReason.verification_inconclusive,
        }:
            raise ValueError("rejection reason requires precise graph provenance")
        return self


class SolverDiagnosticCode(str, Enum):
    backend_selected = "backend_selected"
    numeric_fallback_used = "numeric_fallback_used"
    candidate_limit_reached = "candidate_limit_reached"
    generation_incomplete = "generation_incomplete"
    backend_unsupported = "backend_unsupported"
    backend_failure = "backend_failure"
    resource_limit = "resource_limit"
    timeout = "timeout"


class DiagnosticSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


_DIAGNOSTIC_SEVERITY = {
    SolverDiagnosticCode.backend_selected: DiagnosticSeverity.info,
    SolverDiagnosticCode.numeric_fallback_used: DiagnosticSeverity.warning,
    SolverDiagnosticCode.generation_incomplete: DiagnosticSeverity.warning,
    SolverDiagnosticCode.candidate_limit_reached: DiagnosticSeverity.error,
    SolverDiagnosticCode.backend_unsupported: DiagnosticSeverity.error,
    SolverDiagnosticCode.backend_failure: DiagnosticSeverity.error,
    SolverDiagnosticCode.resource_limit: DiagnosticSeverity.error,
    SolverDiagnosticCode.timeout: DiagnosticSeverity.error,
}

_SOLVE_PHASE_ORDER = {item: index for index, item in enumerate(SolvePhase)}
_DIAGNOSTIC_CODE_ORDER = {item: index for index, item in enumerate(SolverDiagnosticCode)}
_NUMERIC_BACKENDS = {
    SolveBackendKind.numeric_root,
    SolveBackendKind.ode_ivp,
    SolveBackendKind.event_root,
    SolveBackendKind.constrained_optimization,
}


def solver_phase_limit_s(
    phase: SolvePhase,
    backend: SolveBackendKind,
    budget: SolverBudget,
) -> float:
    """Map a plan phase/backend pair to its one configured elapsed-time limit."""

    if phase is SolvePhase.verification:
        return budget.verification_time_limit_s
    if phase is SolvePhase.numeric:
        return budget.numeric_time_limit_s
    if phase is SolvePhase.symbolic:
        return budget.symbolic_time_limit_s
    if backend in _NUMERIC_BACKENDS:
        return budget.numeric_time_limit_s
    return budget.symbolic_time_limit_s


class SolverDiagnosticEntry(FrozenModel):
    code: SolverDiagnosticCode
    severity: DiagnosticSeverity
    phase: SolvePhase
    backend: SolveBackendKind
    referenced_id: Identifier | None = None

    @model_validator(mode="after")
    def fixed_code_semantics(self) -> "SolverDiagnosticEntry":
        if self.severity is not _DIAGNOSTIC_SEVERITY[self.code]:
            raise ValueError("diagnostic code has one fixed severity")
        if self.code is SolverDiagnosticCode.backend_selected and self.phase is not SolvePhase.planning:
            raise ValueError("backend selection is a planning diagnostic")
        return self


class SolverAttempt(FrozenModel):
    attempt_index: StrictInt = Field(ge=0, le=2047)
    backend: SolveBackendKind
    phase: SolvePhase
    elapsed_s: FiniteFloat = Field(ge=0.0, le=1.0e12)
    completed: StrictBool


def diagnostic_entry_sort_key(
    item: SolverDiagnosticEntry,
) -> tuple[int, str, int, str]:
    """Canonical, deterministic diagnostics ordering key."""

    return (
        _SOLVE_PHASE_ORDER[item.phase],
        item.backend.value,
        _DIAGNOSTIC_CODE_ORDER[item.code],
        item.referenced_id or "",
    )


class SolverDiagnostics(FrozenModel):
    entries: tuple[SolverDiagnosticEntry, ...] = Field(default_factory=tuple, max_length=256)
    attempts: tuple[SolverAttempt, ...] = Field(default_factory=tuple, max_length=2048)
    total_elapsed_s: FiniteFloat = Field(ge=0.0, le=1.0e12)
    timeout: SolverTimeout | None = None

    @model_validator(mode="after")
    def validate_attempts(self) -> "SolverDiagnostics":
        indices = tuple(item.attempt_index for item in self.attempts)
        if indices != tuple(range(len(self.attempts))):
            raise ValueError("solver attempt indices must be contiguous from zero in recorded order")
        entry_keys = tuple(
            (item.code, item.phase, item.backend, item.referenced_id)
            for item in self.entries
        )
        if len(set(entry_keys)) != len(entry_keys):
            raise ValueError("solver diagnostic entries must be unique")
        if self.entries != tuple(sorted(self.entries, key=diagnostic_entry_sort_key)):
            raise ValueError("solver diagnostic entries must be in canonical deterministic order")
        if sum(item.elapsed_s for item in self.attempts) > self.total_elapsed_s + 1.0e-12:
            raise ValueError("attempt timing cannot exceed total timing")
        timeout_entries = tuple(item for item in self.entries if item.code is SolverDiagnosticCode.timeout)
        if (self.timeout is None) != (len(timeout_entries) == 0):
            raise ValueError("timeout diagnostic code and exact timeout details are required together")
        if len(timeout_entries) > 1:
            raise ValueError("timeout diagnostics must be unique")
        if self.timeout is not None:
            entry = timeout_entries[0]
            if entry.phase is not self.timeout.phase or entry.backend is not self.timeout.backend:
                raise ValueError("timeout diagnostic must exactly match timeout phase and backend")
            matching_attempts = tuple(
                item
                for item in self.attempts
                if item.phase is self.timeout.phase
                and item.backend is self.timeout.backend
                and not item.completed
            )
            if len(matching_attempts) != 1:
                raise ValueError("timeout requires exactly one matching incomplete solver attempt")
            timeout_attempt = matching_attempts[0]
            if timeout_attempt.attempt_index != len(self.attempts) - 1:
                raise ValueError("timeout attempt must be the final solver attempt")
            if any(not item.completed for item in self.attempts[:-1]):
                raise ValueError("every attempt before a timeout must be completed")
            if timeout_attempt.elapsed_s != self.timeout.elapsed_s:
                raise ValueError("timeout attempt elapsed time must exactly match timeout details")
            if self.timeout.elapsed_s > self.total_elapsed_s:
                raise ValueError("timeout elapsed time cannot exceed total diagnostics time")
        return self


__all__ = [
    "SOLVER_CONTRACT_VERSION", "SOLVER_POLICY_VERSION", "CandidateCoverage",
    "CandidateGenerationRecord", "CandidateRejection", "CandidateRejectionReason", "CandidateSet", "CandidateValue",
    "DiagnosticSeverity", "EquationGraph", "GraphStructureFeatures", "SolveBackendKind", "SolvePhase",
    "SolvePlan", "SolverAttempt", "SolverBudget", "SolverCandidate", "SolverDiagnosticCode",
    "SolverDiagnosticEntry", "SolverDiagnostics", "SolverTimeout", "candidate_generation_manifest",
    "canonical_candidate_id", "canonical_candidate_sha256", "create_solver_candidate",
    "derive_numeric_fallback", "derive_primary_backend", "diagnostic_entry_sort_key",
    "make_solver_candidate", "numeric_fallback_for_structure", "primary_backend_for_structure",
    "solver_phase_limit_s",
]
