from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class FrictionDecision:
    mode: str
    status: str
    driving_force: float
    max_static: float | None = None
    normal_force: float | None = None
    friction_force: float | None = None
    direction: str | None = None
    equation_note: str | None = None
    notes: list[str] | None = None

    @property
    def holds_static(self) -> bool:
        return self.status == "static_hold"

    @property
    def moves(self) -> bool:
        return self.status == "moves"


def kinetic_friction(mu_k, normal_force):
    return mu_k * normal_force


def max_static_friction(mu_s, normal_force):
    return mu_s * normal_force


def decide_static_or_motion(driving_force, max_static):
    if abs(driving_force) <= max_static:
        return "static_hold"
    return "moves"


def decide_static_friction(driving_force: float, normal_force: float, mu_s: float, *, label: str = "static") -> FrictionDecision:
    max_static = max_static_friction(mu_s, normal_force)
    status = decide_static_or_motion(driving_force, max_static)
    if status == "static_hold":
        return FrictionDecision(
            mode=label,
            status="static_hold",
            driving_force=driving_force,
            max_static=max_static,
            normal_force=normal_force,
            friction_force=abs(driving_force),
            direction="구동력 반대",
            equation_note="|f_s| <= μ_s N 이므로 정지 유지",
            notes=["정지마찰은 필요한 만큼만 생기며 최대정지마찰 이하입니다."],
        )
    return FrictionDecision(
        mode=label,
        status="moves",
        driving_force=driving_force,
        max_static=max_static,
        normal_force=normal_force,
        friction_force=max_static,
        direction="운동경향 반대",
        equation_note="|driving| > μ_s N 이므로 운동 시작",
        notes=["운동이 시작되면 운동마찰 모델 μ_k N으로 전환해야 합니다."],
    )


def decide_incline_static(theta_rad: float, mu_s: float, mass: float | None = None, g: float = 9.81) -> FrictionDecision:
    """Static friction decision for a block on an incline.

    mass is optional because the inequality m g sinθ <= μ_s m g cosθ cancels m.
    """
    m = 1.0 if mass is None else mass
    driving = m * g * math.sin(theta_rad)
    normal = m * g * math.cos(theta_rad)
    decision = decide_static_friction(driving, normal, mu_s, label="incline_static")
    decision.equation_note = "mg sinθ <= μ_s mg cosθ" if decision.holds_static else "mg sinθ > μ_s mg cosθ"
    return decision


def decide_table_hanging_static(m1: float, m2: float, mu_s: float, g: float = 9.81) -> FrictionDecision:
    driving = m2 * g
    normal = m1 * g
    decision = decide_static_friction(driving, normal, mu_s, label="table_hanging_static")
    decision.equation_note = "m2g <= μ_s m1g" if decision.holds_static else "m2g > μ_s m1g"
    return decision


def decide_incline_hanging_static(m1: float, m2: float, theta_rad: float, mu_s: float, g: float = 9.81) -> FrictionDecision:
    """Static decision for m1 on incline + m2 hanging.

    Coordinate convention: positive driving means m2 tends to move down and m1
    tends to move up the slope. Negative means m1 tends to move down the slope.
    """
    driving = m2 * g - m1 * g * math.sin(theta_rad)
    normal = m1 * g * math.cos(theta_rad)
    decision = decide_static_friction(driving, normal, mu_s, label="incline_hanging_static")
    if decision.holds_static:
        decision.direction = "정지마찰이 상대 운동경향을 상쇄"
        decision.equation_note = "|m2g - m1g sinθ| <= μ_s m1g cosθ"
    else:
        decision.direction = "m2 하강 경향 반대" if driving > 0 else "m1 경사면 하강 경향 반대"
        decision.equation_note = "|m2g - m1g sinθ| > μ_s m1g cosθ"
    return decision


def kinetic_direction_from_driving(driving_force: float, *, positive_label: str, negative_label: str) -> str:
    if driving_force >= 0:
        return positive_label
    return negative_label
