from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def magnitude(self) -> float:
        return math.hypot(self.x, self.y)

    def as_tuple(self) -> tuple[float, float]:
        return self.x, self.y


def from_polar(length: float, angle_deg: float) -> Vec2:
    a = math.radians(angle_deg)
    return Vec2(length * math.cos(a), length * math.sin(a))


def rot90(v: Vec2) -> Vec2:
    return Vec2(-v.y, v.x)


def cross_z_scalar_vec(omega: float, r: Vec2) -> Vec2:
    return Vec2(-omega * r.y, omega * r.x)


def rigid_body_velocity(vA: Vec2, omega: float, rBA: Vec2) -> Vec2:
    return vA + cross_z_scalar_vec(omega, rBA)


def rigid_body_acceleration(aA: Vec2, alpha: float, omega: float, rBA: Vec2) -> Vec2:
    tangential = cross_z_scalar_vec(alpha, rBA)
    normal = Vec2(-omega**2 * rBA.x, -omega**2 * rBA.y)
    return aA + tangential + normal
