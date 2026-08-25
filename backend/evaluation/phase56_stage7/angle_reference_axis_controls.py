"""Structural controls for the magnitude-with-angle refusal.

The refusal under audit: without a typed reference axis and orientation, a
stated launch speed magnitude and a bare angle license no signed component
decomposition — no `v·cosθ`/`v·sinθ`, no new signed launch-velocity
quantity, no quadrant or sign decision.  The original pin checked law *IDs*
for marker substrings, which a renamed law slips past, and — because the
engine's own idiom folds trig into numeric literals — a decomposition can
reference the angle through provenance only, invisible to any symbol scan.

These helpers make the pin structural.  A violation is detected on the
emission and compiled-equation surfaces from what an equation actually
touches: its `source_quantity_ids` united with the quantities its
expression's symbols resolve to, its literal values against the exact trig
fingerprint of the stated angle, and its node shapes for sign machinery.
No law ID is read anywhere, so renaming changes nothing.

Everything here is pure, read-only introspection over typed engine
objects.  Nothing reads raw problem text, a source identity, or a
reference result, and nothing in the product path imports this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from engine.mechanics import math_ast
from engine.mechanics.compiler.compiler import _expression_symbol_ids

ANGLE_AXIS_CONTROLS_VERSION = "phase56-stage7-angle-axis-controls-v1"

# Quantity roles whose signed components would constitute the refused
# decomposition when minted for the launch subject at the launch instant.
LAUNCH_VECTOR_ROLES: frozenset[str] = frozenset(
    {"velocity", "speed", "momentum", "impulse"}
)
SIGNED_COMPONENTS: frozenset[str] = frozenset(
    {
        "x",
        "y",
        "z",
        "radial",
        "transverse",
        "tangential",
        "normal",
        "clockwise",
        "counterclockwise",
    }
)
_TRIG_RELATIVE_TOLERANCE = 1.0e-9


def _walk(expression: Any) -> Iterable[Any]:
    stack = [expression]
    seen = 0
    while stack:
        node = stack.pop()
        seen += 1
        if seen > 65536:
            raise ValueError("expression walk exceeded its bound")
        yield node
        stack.extend(math_ast._children(node))


def expression_literals(expression: Any) -> tuple[float, ...]:
    """Every numeric literal value inside one expression, in walk order."""

    return tuple(
        float(node.value)
        for node in _walk(expression)
        if type(node).__name__ == "LiteralNode"
    )


def expression_node_names(expression: Any) -> frozenset[str]:
    """The set of AST node type names inside one expression."""

    return frozenset(type(node).__name__ for node in _walk(expression))


def touched_quantity_ids(
    item: Any, symbol_to_quantity: Mapping[str, str]
) -> frozenset[str]:
    """Every quantity one emission or compiled equation actually touches.

    The union of the item's own provenance (`source_quantity_ids`) and the
    quantities its expression's symbols resolve to.  Both sides are
    required: a literal-folded trig rule leaves the angle out of the symbol
    set, and a provenance-dropping rule leaves it out of
    `source_quantity_ids` — either alone under-reports.
    """

    touched = set(getattr(item, "source_quantity_ids", ()) or ())
    for symbol_id in _expression_symbol_ids(item.expression):
        quantity_id = symbol_to_quantity.get(symbol_id)
        if quantity_id is not None:
            touched.add(quantity_id)
    return frozenset(touched)


def forbidden_trig_values(angle_si_radians: float) -> tuple[float, ...]:
    """The numeric fingerprint a folded decomposition of this angle leaves."""

    values = []
    for value in (
        math.sin(angle_si_radians),
        math.cos(angle_si_radians),
        math.tan(angle_si_radians),
    ):
        if abs(value) > 1.0e-12:
            values.extend((abs(value), 1.0 / abs(value)))
    return tuple(values)


def launch_pair(
    quantities: Iterable[Any], *, subject_id: str, event_id: str
) -> tuple[Any, Any] | None:
    """Resolve the (magnitude velocity, angle) pair by typed identity.

    Resolution is by role + subject + event + component — never by a
    literal quantity ID — so the controls survive projection ID changes.
    Returns ``None`` unless exactly one of each exists.
    """

    magnitudes = [
        q
        for q in quantities
        if getattr(q.role, "value", q.role) in LAUNCH_VECTOR_ROLES
        and q.subject_id == subject_id
        and q.event_id == event_id
        and getattr(q.component, "value", q.component) == "magnitude"
    ]
    angles = [
        q
        for q in quantities
        if getattr(q.role, "value", q.role) == "angle"
        and q.subject_id == subject_id
    ]
    if len(magnitudes) != 1 or len(angles) != 1:
        return None
    return magnitudes[0], angles[0]


def signed_launch_component_quantities(
    quantities: Iterable[Any], *, subject_id: str, event_id: str
) -> tuple[Any, ...]:
    """Signed launch-vector components — the refused decomposition's output."""

    return tuple(
        q
        for q in quantities
        if getattr(q.role, "value", q.role) in LAUNCH_VECTOR_ROLES
        and q.subject_id == subject_id
        and q.event_id == event_id
        and getattr(q.component, "value", q.component) in SIGNED_COMPONENTS
    )


@dataclass(frozen=True, slots=True)
class AngleAxisViolation:
    """One structural violation of the refusal, with a closed kind."""

    kind: str
    detail: str


def angle_axis_violations(
    items: Iterable[Any],
    *,
    symbol_to_quantity: Mapping[str, str],
    magnitude_quantity_id: str,
    angle_quantity_id: str,
    angle_si_radians: float,
) -> tuple[AngleAxisViolation, ...]:
    """Scan emissions or compiled equations for decomposition structure.

    Violation kinds, closed:

    * ``angle_consumed`` — an equation touches the angle quantity at all.
      Reading the angle is a prerequisite of any decomposition and of any
      quadrant or sign decision, so without a typed reference axis the
      angle must participate in nothing.
    * ``magnitude_angle_combined`` — one equation touches both the launch
      magnitude and the angle (implied by the first, stated separately
      because it is the refusal's own words).
    * ``folded_trig_literal`` — an equation touching the launch magnitude
      carries a literal equal to the stated angle's sine, cosine, tangent,
      or their reciprocals: the literal-folded decomposition, provenance
      or not.
    * ``sign_machinery`` — an equation touching the launch magnitude
      carries a negation, a piecewise, or a negative literal: a sign or
      quadrant decision no axis licenses.
    """

    trig_fingerprint = forbidden_trig_values(angle_si_radians)
    violations: list[AngleAxisViolation] = []
    for item in items:
        touched = touched_quantity_ids(item, symbol_to_quantity)
        if angle_quantity_id in touched:
            violations.append(
                AngleAxisViolation("angle_consumed", _label(item))
            )
        if magnitude_quantity_id in touched and angle_quantity_id in touched:
            violations.append(
                AngleAxisViolation("magnitude_angle_combined", _label(item))
            )
        if magnitude_quantity_id in touched:
            literals = expression_literals(item.expression)
            if any(
                math.isclose(
                    abs(value), fingerprint, rel_tol=_TRIG_RELATIVE_TOLERANCE
                )
                for value in literals
                for fingerprint in trig_fingerprint
            ):
                violations.append(
                    AngleAxisViolation("folded_trig_literal", _label(item))
                )
            node_names = expression_node_names(item.expression)
            if (
                "Negate" in node_names
                or "Piecewise" in node_names
                or any(value < 0.0 for value in literals)
            ):
                violations.append(
                    AngleAxisViolation("sign_machinery", _label(item))
                )
    return tuple(violations)


def _label(item: Any) -> str:
    rule = getattr(item, "rule", None)
    if rule is not None:
        return str(getattr(rule, "law_id", "emission"))
    return str(getattr(item, "equation_id", "equation"))


__all__ = [
    "ANGLE_AXIS_CONTROLS_VERSION",
    "AngleAxisViolation",
    "LAUNCH_VECTOR_ROLES",
    "SIGNED_COMPONENTS",
    "angle_axis_violations",
    "expression_literals",
    "expression_node_names",
    "forbidden_trig_values",
    "launch_pair",
    "signed_launch_component_quantities",
    "touched_quantity_ids",
]
