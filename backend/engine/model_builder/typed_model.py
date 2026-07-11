from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Mapping

import sympy as sp

from engine.models import Quantity
from engine.physics_core.units import assert_dimension, magnitude_si, to_pint


Scalar = float | int | sp.Expr
Residual = sp.Expr | Callable[[Mapping[str, float]], float]


class Dimension:
    DIMENSIONLESS = "dimensionless"
    MASS = "mass"
    LENGTH = "length"
    TIME = "time"
    VELOCITY = "velocity"
    ACCELERATION = "acceleration"
    FORCE = "force"
    MOMENT = "torque"
    INERTIA = "inertia"


@dataclass(frozen=True)
class QuantityValue:
    """A numeric SI value with traceable source and display-unit metadata."""

    symbol: str
    magnitude: float
    unit: str
    dimension: str
    source_fact_id: str | None = None
    uncertainty: float | None = None
    display_unit: str | None = None

    @classmethod
    def from_quantity(
        cls,
        quantity: Quantity,
        *,
        dimension: str,
        si_unit: str,
        source_fact_id: str | None = None,
        uncertainty: float | None = None,
    ) -> "QuantityValue":
        assert_dimension(to_pint(quantity), dimension)
        return cls(
            symbol=quantity.symbol,
            magnitude=magnitude_si(quantity, si_unit),
            unit=si_unit,
            dimension=dimension,
            source_fact_id=source_fact_id,
            uncertainty=uncertainty,
            display_unit=quantity.unit,
        )


@dataclass(frozen=True)
class Vector2:
    x: Scalar
    y: Scalar
    frame_id: str
    dimension: str

    def _require_compatible(self, other: "Vector2") -> None:
        if self.frame_id != other.frame_id:
            raise ValueError(
                f"Frame mismatch: {self.frame_id!r} != {other.frame_id!r}"
            )
        if self.dimension != other.dimension:
            raise ValueError(
                f"Dimension mismatch: {self.dimension!r} != {other.dimension!r}"
            )

    def __add__(self, other: "Vector2") -> "Vector2":
        self._require_compatible(other)
        return Vector2(
            sp.simplify(self.x + other.x),
            sp.simplify(self.y + other.y),
            self.frame_id,
            self.dimension,
        )

    def __sub__(self, other: "Vector2") -> "Vector2":
        self._require_compatible(other)
        return Vector2(
            sp.simplify(self.x - other.x),
            sp.simplify(self.y - other.y),
            self.frame_id,
            self.dimension,
        )

    def scaled(self, scalar: Scalar, *, dimension: str | None = None) -> "Vector2":
        return Vector2(
            sp.simplify(self.x * scalar),
            sp.simplify(self.y * scalar),
            self.frame_id,
            dimension or self.dimension,
        )

    def as_tuple(self) -> tuple[Scalar, Scalar]:
        return self.x, self.y


@dataclass(frozen=True)
class CoordinateFrame:
    id: str
    origin: tuple[Scalar, Scalar] = (0.0, 0.0)
    basis_x: tuple[Scalar, Scalar] = (1.0, 0.0)
    basis_y: tuple[Scalar, Scalar] = (0.0, 1.0)
    angular_positive: int = 1
    parent_frame: str | None = None
    transform: tuple[
        tuple[Scalar, Scalar, Scalar],
        tuple[Scalar, Scalar, Scalar],
        tuple[Scalar, Scalar, Scalar],
    ] | None = None

    def __post_init__(self) -> None:
        if self.angular_positive not in {-1, 1}:
            raise ValueError("angular_positive must be +1 (CCW) or -1 (CW)")
        determinant = sp.simplify(
            self.basis_x[0] * self.basis_y[1]
            - self.basis_x[1] * self.basis_y[0]
        )
        if determinant == 0:
            raise ValueError(f"Coordinate frame {self.id!r} has a singular basis")
        if self.transform is None:
            object.__setattr__(
                self,
                "transform",
                (
                    (self.basis_x[0], self.basis_y[0], self.origin[0]),
                    (self.basis_x[1], self.basis_y[1], self.origin[1]),
                    (0, 0, 1),
                ),
            )

    def to_parent(self, vector: Vector2) -> Vector2:
        if vector.frame_id != self.id:
            raise ValueError(
                f"Vector is in {vector.frame_id!r}, expected {self.id!r}"
            )
        if self.parent_frame is None:
            return vector
        x = self.basis_x[0] * vector.x + self.basis_y[0] * vector.y
        y = self.basis_x[1] * vector.x + self.basis_y[1] * vector.y
        if vector.dimension == Dimension.LENGTH:
            x += self.origin[0]
            y += self.origin[1]
        return Vector2(sp.simplify(x), sp.simplify(y), self.parent_frame, vector.dimension)

    def from_parent(self, vector: Vector2) -> Vector2:
        if self.parent_frame is None:
            if vector.frame_id != self.id:
                raise ValueError(
                    f"Root vector is in {vector.frame_id!r}, expected {self.id!r}"
                )
            return vector
        if vector.frame_id != self.parent_frame:
            raise ValueError(
                f"Vector is in {vector.frame_id!r}, expected {self.parent_frame!r}"
            )
        x = vector.x
        y = vector.y
        if vector.dimension == Dimension.LENGTH:
            x -= self.origin[0]
            y -= self.origin[1]
        a, c = self.basis_x
        b, d = self.basis_y
        determinant = a * d - b * c
        local_x = (d * x - b * y) / determinant
        local_y = (-c * x + a * y) / determinant
        return Vector2(
            sp.simplify(local_x),
            sp.simplify(local_y),
            self.id,
            vector.dimension,
        )


@dataclass
class Body:
    id: str
    kind: str
    frame_id: str
    mass: QuantityValue | None = None
    center_of_mass: Vector2 | None = None
    inertia_about_com: QuantityValue | None = None
    geometry: dict[str, Any] = field(default_factory=dict)


@dataclass
class Force:
    id: str
    kind: str
    body_id: str
    application_point: Vector2
    vector: Vector2
    constitutive_relation: sp.Expr | sp.Equality | None = None
    active_state: str | None = None
    source_fact_id: str | None = None


@dataclass
class Moment:
    id: str
    kind: str
    body_id: str
    scalar: Scalar
    frame_id: str
    dimension: str = Dimension.MOMENT
    active_state: str | None = None
    source_fact_id: str | None = None


@dataclass
class Constraint:
    id: str
    kind: str
    frame_id: str
    dimension: str
    expression: Residual
    display: str
    related_bodies: list[str] = field(default_factory=list)
    source_fact_id: str | None = None

    def residual(self, values: Mapping[str | sp.Symbol, float] | None = None) -> float | sp.Expr:
        values = values or {}
        if callable(self.expression):
            normalized = {str(key): float(value) for key, value in values.items()}
            return float(self.expression(normalized))
        substitutions: dict[sp.Symbol, float] = {}
        for symbol in self.expression.free_symbols:
            if symbol in values:
                substitutions[symbol] = float(values[symbol])
            elif str(symbol) in values:
                substitutions[symbol] = float(values[str(symbol)])
        result = sp.simplify(self.expression.subs(substitutions))
        if not result.free_symbols:
            return float(result)
        return result


@dataclass
class TypedDynamicsModel:
    system_type: str
    frames: dict[str, CoordinateFrame] = field(default_factory=dict)
    bodies: dict[str, Body] = field(default_factory=dict)
    quantities: dict[str, QuantityValue] = field(default_factory=dict)
    forces: list[Force] = field(default_factory=list)
    moments: list[Moment] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    display_metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.frames:
            raise ValueError("TypedDynamicsModel requires at least one frame")
        for body in self.bodies.values():
            if body.frame_id not in self.frames:
                raise ValueError(f"Unknown body frame: {body.frame_id}")
        for force in self.forces:
            if force.body_id not in self.bodies:
                raise ValueError(f"Unknown force body: {force.body_id}")
            if force.vector.frame_id not in self.frames:
                raise ValueError(f"Unknown force frame: {force.vector.frame_id}")
            if force.application_point.frame_id not in self.frames:
                raise ValueError(
                    f"Unknown application-point frame: {force.application_point.frame_id}"
                )
            if force.vector.dimension != Dimension.FORCE:
                raise ValueError(f"Force {force.id!r} does not have force dimension")
        for constraint in self.constraints:
            if constraint.frame_id not in self.frames:
                raise ValueError(f"Unknown constraint frame: {constraint.frame_id}")

    def _to_root(self, vector: Vector2) -> Vector2:
        current = vector
        visited: set[str] = set()
        while True:
            if current.frame_id in visited:
                raise ValueError("Coordinate frame parent cycle")
            visited.add(current.frame_id)
            frame = self.frames[current.frame_id]
            if frame.parent_frame is None:
                return current
            current = frame.to_parent(current)

    def _from_root(self, vector: Vector2, target_frame: str) -> Vector2:
        chain: list[CoordinateFrame] = []
        current = self.frames[target_frame]
        while current.parent_frame is not None:
            chain.append(current)
            current = self.frames[current.parent_frame]
        if vector.frame_id != current.id:
            raise ValueError(
                f"Frames {vector.frame_id!r} and {target_frame!r} have different roots"
            )
        result = vector
        for frame in reversed(chain):
            result = frame.from_parent(result)
        return result

    def vector_in_frame(self, vector: Vector2, target_frame: str) -> Vector2:
        if target_frame not in self.frames:
            raise ValueError(f"Unknown target frame: {target_frame}")
        if vector.frame_id == target_frame:
            return vector
        return self._from_root(self._to_root(vector), target_frame)

    def sum_forces(self, body_id: str, frame_id: str | None = None) -> Vector2:
        target = frame_id or self.bodies[body_id].frame_id
        total = Vector2(0, 0, target, Dimension.FORCE)
        for force in self.forces:
            if force.body_id == body_id:
                total = total + self.vector_in_frame(force.vector, target)
        return total

    def moment_about(
        self,
        body_id: str,
        point: Vector2,
        *,
        frame_id: str | None = None,
    ) -> Scalar:
        target = frame_id or point.frame_id
        about = self.vector_in_frame(point, target)
        if about.dimension != Dimension.LENGTH:
            raise ValueError("Moment reference point must have length dimension")
        total: Scalar = 0
        for force in self.forces:
            if force.body_id != body_id:
                continue
            application = self.vector_in_frame(force.application_point, target)
            vector = self.vector_in_frame(force.vector, target)
            arm = application - about
            total += arm.x * vector.y - arm.y * vector.x
        for moment in self.moments:
            if moment.body_id == body_id:
                if moment.frame_id != target:
                    raise ValueError("Explicit moment frame conversion is not supported")
                total += moment.scalar
        return sp.simplify(self.frames[target].angular_positive * total)

    def to_legacy_dict(self, legacy_model: Any) -> dict[str, Any]:
        """Serialize through the existing compatibility adapter.

        The typed layer intentionally owns no student-facing schema. Requiring
        an explicit legacy model prevents symbolic expressions from leaking into
        API payloads while preserving the established PhysicalModel contract.
        """

        if getattr(legacy_model, "system_type", None) != self.system_type:
            raise ValueError("Typed and legacy model system types do not match")
        return legacy_model.to_dict()

    def constraint(self, kind_or_id: str) -> Constraint:
        matches = [
            item
            for item in self.constraints
            if item.id == kind_or_id or item.kind == kind_or_id
        ]
        if len(matches) != 1:
            raise KeyError(
                f"Expected one constraint for {kind_or_id!r}, got {len(matches)}"
            )
        return matches[0]


def string_length_constraint(
    *,
    frame_id: str,
    first: sp.Expr,
    second: sp.Expr,
    total_length: sp.Expr,
    related_bodies: list[str] | None = None,
) -> Constraint:
    return Constraint(
        id="string_length",
        kind="string_length",
        frame_id=frame_id,
        dimension=Dimension.LENGTH,
        expression=first + second - total_length,
        display="q1 + q2 - L = 0",
        related_bodies=related_bodies or [],
    )


def rolling_no_slip_constraint(
    *,
    frame_id: str,
    velocity: sp.Expr,
    radius: sp.Expr,
    angular_velocity: sp.Expr,
    body_id: str | None = None,
) -> Constraint:
    return Constraint(
        id="rolling_no_slip",
        kind="rolling_no_slip",
        frame_id=frame_id,
        dimension=Dimension.VELOCITY,
        expression=velocity - radius * angular_velocity,
        display="v - R*omega = 0",
        related_bodies=[body_id] if body_id else [],
    )
