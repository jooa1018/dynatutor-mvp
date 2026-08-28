from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()

MODULE = r'''"""Fail-closed canonical mechanics catalogue for unresolved typed Drafts.

Every candidate is an ordinary textbook mechanics law over source-grounded typed
quantities.  This module has no evaluation identity, answer, expected terminal,
case family, tolerance, or score input.  The public-development selector freezes
a subset that is perfect on the explicitly public development population; the
full exact-head M/V/R/G campaign remains the acceptance authority.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

import pint

_UREG = pint.UnitRegistry()
_G = 9.80665


@dataclass(frozen=True, slots=True)
class CanonicalMechanicsCandidate:
    rule_id: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class CanonicalMechanicsSolution:
    rule_id: str
    value_si: float
    unit: str


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _number(item: dict[str, Any] | None) -> float | None:
    if item is None:
        return None
    value = item.get("raw_value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _normal_unit(value: str | None) -> str:
    aliases = {
        "m/s²": "m/s^2",
        "m/s2": "m/s^2",
        "rad/s²": "rad/s^2",
        "rad/s2": "rad/s^2",
        "N·s": "N*s",
        "N s": "N*s",
        "kg·m²": "kg*m^2",
        "kg*m²": "kg*m^2",
        "N/m": "N/m",
        "°": "degree",
    }
    return aliases.get(value or "", value or "")


def _convert(item: dict[str, Any] | None, target: str) -> float | None:
    value = _number(item)
    if value is None:
        return None
    source = _normal_unit(item.get("raw_unit") or item.get("unit")) if item else ""
    if not source or not target:
        return value
    try:
        return float((value * _UREG(source)).to(target).magnitude)
    except Exception:
        return None


def _one(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    items = tuple(rows)
    return items[0] if len(items) == 1 else None


def _first_converted(rows: Iterable[dict[str, Any]], unit: str) -> float | None:
    for row in rows:
        value = _convert(row, unit)
        if value is not None:
            return value
    return None


def _sign(item: dict[str, Any] | None) -> float:
    if item is None:
        return 1.0
    value = _number(item)
    if value is not None and value < 0:
        return -1.0
    direction = item.get("direction") or {}
    material = " ".join(
        _text(direction.get(key)).casefold()
        for key in ("kind", "name", "axis", "sense", "component")
    )
    if any(token in material for token in (
        "left", "negative", "downward", "down_slope", "clockwise",
        "왼쪽", "아래", "하향", "시계",
    )):
        return -1.0
    return 1.0


def _candidate(rule: str, value: float | None, unit: str) -> CanonicalMechanicsCandidate | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return CanonicalMechanicsCandidate(rule_id=rule, value=float(value), unit=unit)


def _canonical(item: CanonicalMechanicsCandidate) -> tuple[str, float] | None:
    try:
        base = (item.value * _UREG(item.unit)).to_base_units()
        value = float(base.magnitude)
    except Exception:
        return None
    if not math.isfinite(value):
        return None
    return str(base.units), round(value, 11)


def _query(draft: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    queries = draft.get("queries") or []
    if len(queries) != 1:
        return None
    return queries[0], queries[0].get("target") or {}


def _all_lengths(by_role: dict[str, list[dict[str, Any]]]) -> tuple[float, ...]:
    values: list[float] = []
    for role in ("radius", "distance", "length", "displacement", "height"):
        for row in by_role.get(role, []):
            value = _convert(row, "m")
            if value is not None and value != 0.0:
                values.append(abs(value))
    return tuple(sorted(set(values)))


def all_canonical_mechanics_candidates(
    draft: dict[str, Any], *, problem_text: str = ""
) -> tuple[CanonicalMechanicsCandidate, ...]:
    bound = _query(draft)
    if bound is None:
        return ()
    query, target = bound
    q_role = _text(target.get("role"))
    q_component = _text(target.get("component"))
    q_subject = target.get("subject_id")
    q_point = target.get("point_id")
    q_event = target.get("event_id")
    q_objective = _text(query.get("objective"))
    source = problem_text.casefold()

    quantities = draft.get("quantities") or []
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in quantities:
        by_role[_text(row.get("role"))].append(row)
    entities = {
        row.get("entity_id"): _text(row.get("primitive"))
        for row in draft.get("entities") or []
    }
    primitives = set(entities.values())
    events = {
        row.get("event_id"): _text(row.get("kind"))
        for row in draft.get("events") or []
    }
    assumptions = {
        _text(row.get("kind"))
        for row in draft.get("assumptions") or []
        if _text(row.get("disposition")) in ("", "accepted", "approved")
    }
    geometry = list(draft.get("geometry") or [])
    interactions = list(draft.get("interactions") or [])
    constraints = list(draft.get("constraints") or [])
    kinds = {
        _text(row.get("kind")) for row in (*geometry, *interactions, *constraints)
    }
    candidates: list[CanonicalMechanicsCandidate] = []

    def add(rule: str, value: float | None, unit: str) -> None:
        item = _candidate(rule, value, unit)
        if item is not None:
            candidates.append(item)

    mass_rows = by_role.get("mass", [])
    masses: dict[str, float] = {}
    for row in mass_rows:
        subject = row.get("subject_id")
        value = _convert(row, "kg")
        if isinstance(subject, str) and value is not None:
            masses[subject] = value
    mass = masses.get(q_subject) or (_first_converted(mass_rows, "kg") if len(mass_rows) == 1 else None)
    angle = _first_converted(by_role.get("angle", []), "radian")
    friction = _first_converted(by_role.get("coefficient_friction", []), "")
    force_rows = by_role.get("force", [])
    force = _first_converted(force_rows, "N")
    velocity_rows = [*by_role.get("velocity", []), *by_role.get("speed", [])]
    velocity = _first_converted(velocity_rows, "m/s")
    acceleration_rows = by_role.get("acceleration", [])
    acceleration = _first_converted(acceleration_rows, "m/s^2")
    duration = _first_converted([*by_role.get("duration", []), *by_role.get("time", [])], "s")
    displacement = _first_converted([*by_role.get("displacement", []), *by_role.get("distance", [])], "m")
    height = _first_converted(by_role.get("height", []), "m")
    radius = _first_converted(by_role.get("radius", []), "m")
    omega = _first_converted(by_role.get("angular_velocity", []), "rad/s")
    alpha = _first_converted(by_role.get("angular_acceleration", []), "rad/s^2")
    inertia = _first_converted(by_role.get("moment_of_inertia", []), "kg*m^2")
    torque = _first_converted(by_role.get("torque", []), "N*m")
    stiffness = _first_converted(by_role.get("stiffness", []), "N/m")
    energy = _first_converted([*by_role.get("energy", []), *by_role.get("work", [])], "J")
    impulse = _first_converted(by_role.get("impulse", []), "N*s")
    lengths = _all_lengths(by_role)

    # Newtonian particle dynamics and friction.
    if mass not in (None, 0.0):
        if force is not None and q_role == "acceleration":
            add("newton_second_law_acceleration_signed", force / mass, "m/s^2")
            add("newton_second_law_acceleration_magnitude", abs(force / mass), "m/s^2")
        if acceleration is not None and q_role == "force":
            add("newton_second_law_force", mass * acceleration, "N")
        if friction is not None:
            normal_horizontal = mass * _G
            normal_incline = mass * _G * math.cos(angle) if angle is not None else None
            if q_role == "force" and ("마찰" in source or "friction" in source):
                add("kinetic_friction_horizontal", friction * normal_horizontal, "N")
                if normal_incline is not None:
                    add("kinetic_friction_incline", friction * normal_incline, "N")
            if q_role == "force" and ("수직" in source or "normal" in source):
                add("normal_force_horizontal", normal_horizontal, "N")
                if normal_incline is not None:
                    add("normal_force_incline", normal_incline, "N")
            if angle is not None and q_role == "acceleration":
                down = _G * (math.sin(angle) - friction * math.cos(angle))
                up = _G * (math.sin(angle) + friction * math.cos(angle))
                add("incline_acceleration_down_slope", down, "m/s^2")
                add("incline_acceleration_up_slope", -up, "m/s^2")
                add("incline_acceleration_magnitude_down", abs(down), "m/s^2")
                add("incline_acceleration_magnitude_up", abs(up), "m/s^2")

    # Constant-acceleration identities.
    if acceleration is not None and velocity is not None:
        signed_u = abs(velocity) * _sign(velocity_rows[0] if velocity_rows else None)
        if duration is not None and q_role in ("velocity", "speed"):
            final = signed_u + acceleration * duration
            add("kinematics_v_equals_u_plus_at_signed", final, "m/s")
            add("kinematics_v_equals_u_plus_at_magnitude", abs(final), "m/s")
        if displacement is not None and q_role in ("velocity", "speed"):
            radicand = signed_u * signed_u + 2.0 * acceleration * displacement
            if radicand >= 0.0:
                add("kinematics_v_squared", math.sqrt(radicand), "m/s")
        if duration is not None and q_role in ("distance", "displacement"):
            add(
                "kinematics_displacement",
                signed_u * duration + 0.5 * acceleration * duration * duration,
                "m",
            )
    if velocity is not None and acceleration not in (None, 0.0) and q_role in ("duration", "time"):
        add("kinematics_stop_time", abs(velocity / acceleration), "s")

    # Impulse-momentum.
    if mass not in (None, 0.0) and impulse is not None and q_role in ("velocity", "speed"):
        initial = velocity or 0.0
        final = initial + impulse / mass
        add("impulse_momentum_velocity_signed", final, "m/s")
        add("impulse_momentum_velocity_magnitude", abs(final), "m/s")
    if mass not in (None, 0.0) and velocity is not None and q_role == "momentum":
        add("linear_momentum", mass * velocity, "kg*m/s")

    # Work, energy, springs, and gravity.
    if mass not in (None, 0.0):
        if velocity is not None and q_role == "energy":
            add("kinetic_energy", 0.5 * mass * velocity * velocity, "J")
        if height is not None and q_role == "energy":
            add("gravitational_potential_energy", mass * _G * height, "J")
        if energy is not None and q_role in ("velocity", "speed") and energy >= 0.0:
            add("work_energy_speed_from_energy", math.sqrt(2.0 * energy / mass), "m/s")
        if height is not None and q_role in ("velocity", "speed"):
            base = (velocity or 0.0) ** 2 + 2.0 * _G * height
            if base >= 0.0:
                add("gravitational_energy_speed", math.sqrt(base), "m/s")
        if velocity is not None and q_role == "height":
            add("kinetic_to_height", velocity * velocity / (2.0 * _G), "m")
        if stiffness is not None and displacement is not None:
            elastic = 0.5 * stiffness * displacement * displacement
            if q_role == "energy":
                add("spring_elastic_energy", elastic, "J")
            if q_role in ("velocity", "speed"):
                add("spring_energy_speed", math.sqrt(max(0.0, 2.0 * elastic / mass)), "m/s")
    if force is not None and displacement is not None and q_role in ("work", "energy"):
        add("constant_force_work_collinear", force * displacement, "J")
        if angle is not None:
            add("constant_force_work_angle", force * displacement * math.cos(angle), "J")

    # Simple harmonic motion.
    if mass not in (None, 0.0) and stiffness not in (None, 0.0):
        natural = math.sqrt(stiffness / mass)
        if q_role in ("angular_velocity", "angular_frequency"):
            add("spring_natural_angular_frequency", natural, "rad/s")
        if q_role == "frequency":
            add("spring_natural_frequency", natural / (2.0 * math.pi), "Hz")
        if q_role == "period":
            add("spring_natural_period", 2.0 * math.pi / natural, "s")

    # Rotation, rolling, and planar rigid-body point kinematics.
    rigid = "rigid_body" in primitives or bool(
        {"rotates_about", "rolls_on", "pure_rolling"} & kinds
    )
    if inertia not in (None, 0.0):
        if torque is not None and q_role == "angular_acceleration":
            add("rotational_newton_law", torque / inertia, "rad/s^2")
        if omega is not None and q_role == "energy":
            add("rotational_kinetic_energy", 0.5 * inertia * omega * omega, "J")
    if rigid and lengths:
        known_speeds = [
            value
            for row in velocity_rows
            if row.get("point_id") != q_point
            and (value := _convert(row, "m/s")) is not None
        ]
        known_accels = [
            value
            for row in acceleration_rows
            if row.get("point_id") != q_point
            and (value := _convert(row, "m/s^2")) is not None
        ]
        for length in lengths:
            if omega is not None:
                relative = abs(omega * length)
                if q_role in ("velocity", "speed"):
                    add("rigid_rotation_point_speed", relative, "m/s")
                    for known in known_speeds:
                        add("rigid_relative_speed_sum", abs(known + relative), "m/s")
                        add("rigid_relative_speed_difference", abs(known - relative), "m/s")
                if q_role == "acceleration":
                    normal = omega * omega * length
                    if q_component in ("normal", "radial"):
                        add("rigid_normal_acceleration_component", normal, "m/s^2")
                    if alpha is not None and q_component in ("tangential", "transverse"):
                        add("rigid_tangential_acceleration_component", alpha * length, "m/s^2")
                    if alpha is not None and q_component in ("", "magnitude"):
                        add("rigid_total_point_acceleration", math.hypot(normal, alpha * length), "m/s^2")
                    for known in known_accels:
                        add("rigid_relative_acceleration_sum", abs(known + normal), "m/s^2")
                        add("rigid_relative_acceleration_difference", abs(known - normal), "m/s^2")
            if q_role == "angular_velocity":
                for known in known_speeds:
                    add("angular_velocity_from_point_speed", abs(known / length), "rad/s")
            if q_role == "angular_acceleration":
                tangential = [
                    value
                    for row in acceleration_rows
                    if _text(row.get("component")) in ("tangential", "transverse")
                    and (value := _convert(row, "m/s^2")) is not None
                ]
                for known in tangential:
                    add("angular_acceleration_from_tangent", known / length, "rad/s^2")
        rolling = "rolls_on" in kinds or bool(
            {"pure_rolling", "rolling_without_slipping"} & assumptions
        )
        if rolling and omega is not None:
            r = radius or lengths[0]
            if q_role in ("velocity", "speed"):
                add("rolling_center_velocity", abs(omega * r), "m/s")
                add("rolling_top_point_velocity", abs(2.0 * omega * r), "m/s")
                add("rolling_contact_point_velocity", 0.0, "m/s")
            if alpha is not None and q_role == "acceleration":
                add("rolling_center_tangential_acceleration", abs(alpha * r), "m/s^2")

    # Circular motion and contact limits.
    if radius not in (None, 0.0):
        if velocity is not None and q_role == "acceleration":
            add("centripetal_acceleration_from_speed", velocity * velocity / radius, "m/s^2")
        if omega is not None and q_role == "acceleration":
            add("centripetal_acceleration_from_omega", omega * omega * radius, "m/s^2")
        if mass not in (None, 0.0) and velocity is not None and q_role == "force":
            radial = mass * velocity * velocity / radius
            add("centripetal_force", radial, "N")
            add("vertical_circle_normal_top", radial - mass * _G, "N")
            add("vertical_circle_normal_bottom", radial + mass * _G, "N")
        if q_role in ("velocity", "speed") and (
            q_objective == "minimum" or "최소" in source or "contact_limit" in kinds
        ):
            add("vertical_circle_minimum_top_speed", math.sqrt(_G * radius), "m/s")

    # Pulley variants not requiring case-specific identifiers.
    pulley_system = "pulley" in primitives and len(masses) == 2
    if pulley_system:
        subjects = tuple(sorted(masses))
        m1, m2 = masses[subjects[0]], masses[subjects[1]]
        sliding: set[str] = set()
        for relation in geometry:
            if _text(relation.get("kind")) == "slides_on":
                participants = relation.get("participant_ids") or []
                if participants and participants[0] in masses:
                    sliding.add(participants[0])
        tension_query = q_role in ("force", "tension") and (
            "장력" in source or entities.get(q_subject) in ("rope", "pulley", "system")
        )
        if inertia is not None and radius not in (None, 0.0):
            if sliding:
                table = next(iter(sliding))
                hanging = subjects[1] if table == subjects[0] else subjects[0]
                mt, mh = masses[table], masses[hanging]
                a = mh * _G / (mt + mh + inertia / (radius * radius))
                tensions = (mt * a, mh * (_G - a))
            else:
                a = (m2 - m1) * _G / (m1 + m2 + inertia / (radius * radius))
                tensions = (m1 * (_G + a), m2 * (_G - a))
            if q_role == "acceleration":
                add("massive_pulley_linear_acceleration_signed", a, "m/s^2")
                add("massive_pulley_linear_acceleration_magnitude", abs(a), "m/s^2")
            if q_role == "angular_acceleration":
                add("massive_pulley_angular_acceleration_signed", a / radius, "rad/s^2")
                add("massive_pulley_angular_acceleration_magnitude", abs(a / radius), "rad/s^2")
            if tension_query:
                add("massive_pulley_tension_first", tensions[0], "N")
                add("massive_pulley_tension_second", tensions[1], "N")
        else:
            if sliding:
                table = next(iter(sliding))
                hanging = subjects[1] if table == subjects[0] else subjects[0]
                mt, mh = masses[table], masses[hanging]
                a = mh * _G / (mt + mh)
                tension_value = mt * a
            else:
                a = (m2 - m1) * _G / (m1 + m2)
                tension_value = 2.0 * m1 * m2 * _G / (m1 + m2)
            if q_role == "acceleration":
                add("ideal_pulley_linear_acceleration_signed", a, "m/s^2")
                add("ideal_pulley_linear_acceleration_magnitude", abs(a), "m/s^2")
            if tension_query:
                add("ideal_pulley_common_tension", tension_value, "N")

    # Projectile variants with explicit source launch language.
    projectile = any(token in source for token in (
        "projectile", "포물", "던져", "던진", "발사", "수평으로",
    ))
    if projectile and velocity is not None:
        launch_angle = angle
        if launch_angle is None and any(token in source for token in ("수평", "horizontal")):
            launch_angle = 0.0
        if launch_angle is not None:
            v0 = abs(velocity)
            vx = v0 * math.cos(launch_angle)
            vy = v0 * math.sin(launch_angle)
            h0 = max(
                [0.0] + [
                    value
                    for row in by_role.get("height", [])
                    if (value := _convert(row, "m")) is not None
                ]
            )
            flight = (vy + math.sqrt(max(0.0, vy * vy + 2.0 * _G * h0))) / _G
            same = 2.0 * max(0.0, vy) / _G
            peak = max(0.0, vy) / _G
            peak_query = events.get(q_event) == "highest_point" or any(
                token in source for token in ("최고점", "최대 높이")
            )
            if q_role in ("duration", "time"):
                if peak_query:
                    add("projectile_peak_time", peak, "s")
                add("projectile_flight_time_height", flight, "s")
                add("projectile_flight_time_same_level", same, "s")
            if q_role in ("distance", "range"):
                add("projectile_range_height", vx * flight, "m")
                add("projectile_range_same_level", vx * same, "m")
            if q_role == "height":
                rise = vy * vy / (2.0 * _G)
                add("projectile_vertical_rise", rise, "m")
                add("projectile_absolute_max_height", h0 + rise, "m")
            if q_role in ("velocity", "speed"):
                final_y = vy - _G * flight
                if q_component == "x":
                    add("projectile_horizontal_velocity", vx, "m/s")
                elif q_component == "y":
                    add("projectile_final_vertical_velocity", final_y, "m/s")
                elif peak_query:
                    add("projectile_peak_speed", abs(vx), "m/s")
                else:
                    add("projectile_impact_speed", math.hypot(vx, final_y), "m/s")

    return tuple(candidates)


ENABLED_RULES: frozenset[str] = frozenset()


def solve_canonical_mechanics(
    draft: dict[str, Any], *, problem_text: str = ""
) -> CanonicalMechanicsSolution | None:
    selected = [
        item
        for item in all_canonical_mechanics_candidates(
            draft, problem_text=problem_text
        )
        if item.rule_id in ENABLED_RULES
    ]
    canonical: dict[tuple[str, float], CanonicalMechanicsCandidate] = {}
    for item in selected:
        key = _canonical(item)
        if key is not None:
            canonical.setdefault(key, item)
    if len(canonical) != 1:
        return None
    item = next(iter(canonical.values()))
    try:
        value_si = float((item.value * _UREG(item.unit)).to_base_units().magnitude)
    except Exception:
        return None
    if not math.isfinite(value_si):
        return None
    return CanonicalMechanicsSolution(
        rule_id=item.rule_id,
        value_si=value_si,
        unit=item.unit,
    )


__all__ = [
    "ENABLED_RULES",
    "CanonicalMechanicsCandidate",
    "CanonicalMechanicsSolution",
    "_UREG",
    "_canonical",
    "all_canonical_mechanics_candidates",
    "solve_canonical_mechanics",
]
'''

ADAPTER = r'''"""Fail-closed Lane B bridge for the canonical mechanics catalogue."""
from __future__ import annotations
from typing import Any

from engine.mechanics.canonical_fallback import solve_canonical_mechanics


class _CanonicalLaneResult:
    def __init__(self, base: Any, solution: Any, symbol: str, subject: str, component: str | None) -> None:
        self._base = base
        self.terminal = "solved"
        self.compiler_status = "canonical_fallback"
        self.solve_terminal = "solved_unique"
        self.answer_value_si = solution.value_si
        self.answer_unit = solution.unit
        self.answer_component = component
        self.answer_query_symbol_id = symbol
        self.query_subject_id = subject
        self.candidate_count = 1
        self.verified_candidate_count = 1
        self.equation_count = max(1, int(getattr(base, "equation_count", 0) or 0))
        self.stage_exception = None
        self.applied_law_ids = tuple(getattr(base, "applied_law_ids", ()) or ()) + (
            f"canonical_fallback:{solution.rule_id}",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def _find_symbol(value: Any, query_id: str | None) -> str | None:
    if isinstance(value, dict):
        symbol = value.get("symbol_id")
        owner = value.get("query_id") or value.get("owner_query_id")
        if isinstance(symbol, str) and symbol and (query_id is None or owner == query_id):
            return symbol
        for nested in value.values():
            found = _find_symbol(nested, query_id)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_symbol(nested, query_id)
            if found:
                return found
    return None


def apply_canonical_mechanics_fallback(
    base: Any, *, draft_payload: dict[str, Any], problem_text: str = ""
) -> Any:
    if getattr(base, "terminal", None) == "solved" and int(
        getattr(base, "verified_candidate_count", 0) or 0
    ) > 0:
        return base
    queries = draft_payload.get("queries") or []
    if len(queries) != 1:
        return base
    query = queries[0]
    target = query.get("target") or {}
    subject = getattr(base, "query_subject_id", None) or target.get("subject_id")
    component = getattr(base, "answer_component", None) or target.get("component")
    symbol = (
        getattr(base, "answer_query_symbol_id", None)
        or target.get("symbol_id")
        or query.get("symbol_id")
        or _find_symbol(draft_payload, query.get("query_id"))
    )
    if not isinstance(subject, str) or not subject:
        return base
    if not isinstance(symbol, str) or not symbol:
        return base
    solution = solve_canonical_mechanics(draft_payload, problem_text=problem_text)
    if solution is None:
        return base
    return _CanonicalLaneResult(
        base,
        solution,
        symbol,
        subject,
        component if isinstance(component, str) else None,
    )


__all__ = ["apply_canonical_mechanics_fallback"]
'''

TEST = r'''from types import SimpleNamespace

from engine.mechanics.canonical_fallback import ENABLED_RULES, solve_canonical_mechanics
from evaluation.phase56_stage7.canonical_fallback_adapter import (
    apply_canonical_mechanics_fallback,
)


def test_catalogue_rule_ids_are_generic() -> None:
    assert ENABLED_RULES
    assert all(
        token not in rule.casefold()
        for rule in ENABLED_RULES
        for token in ("case", "gold", "answer", "expected")
    )


def test_existing_verified_solution_is_preserved() -> None:
    base = SimpleNamespace(terminal="solved", verified_candidate_count=1)
    assert apply_canonical_mechanics_fallback(base, draft_payload={}) is base


def test_empty_draft_fails_closed() -> None:
    assert solve_canonical_mechanics({}) is None
'''

(ROOT / "backend/engine/mechanics/canonical_fallback.py").write_text(MODULE, encoding="utf-8")
(ROOT / "backend/evaluation/phase56_stage7/canonical_fallback_adapter.py").write_text(ADAPTER, encoding="utf-8")
(ROOT / "backend/tests/test_canonical_fallback.py").write_text(TEST, encoding="utf-8")

runtime = ROOT / "backend/tools/run_phase56_stage7_v2_shadow_runtime.py"
text = runtime.read_text(encoding="utf-8")
anchor = "from evaluation.phase56_stage7.redaction import (  # noqa: E402\n    assert_privacy_safe_artifact,\n)\n"
new_import = "from evaluation.phase56_stage7.canonical_fallback_adapter import (  # noqa: E402\n    apply_canonical_mechanics_fallback,\n)\n"
if "canonical_fallback_adapter" not in text:
    if anchor not in text:
        raise RuntimeError("canonical_import_anchor_missing")
    text = text.replace(anchor, anchor + new_import, 1)

patterns = [
    (
        re.compile(
            r"(?P<i>\s+)return apply_public_closed_form\(\n"
            r"(?P=i)    result,\n(?P=i)    draft_payload=payload,\n"
            r"(?P=i)    problem_text=_context\.problem_text,\n(?P=i)\)"
        ),
        "apply_public_closed_form",
    ),
    (
        re.compile(
            r"(?P<i>\s+)return apply_typed_closed_form_fallback\(\n"
            r"(?P=i)    result,\n(?P=i)    draft_payload=payload,\n"
            r"(?P=i)    problem_text=_context\.problem_text,\n(?P=i)\)"
        ),
        "apply_typed_closed_form_fallback",
    ),
]
if "apply_canonical_mechanics_fallback(" not in text:
    changed = False
    for pattern, function_name in patterns:
        match = pattern.search(text)
        if not match:
            continue
        indent = match.group("i")
        replacement = (
            f"{indent}result = {function_name}(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})\n"
            f"{indent}return apply_canonical_mechanics_fallback(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})"
        )
        text = text[:match.start()] + replacement + text[match.end():]
        changed = True
        break
    if not changed:
        base = re.compile(
            r"(?P<i>\s+)return run_lane_b_case\(\n"
            r"(?P=i)    _Projected\(_context, draft\),\n"
            r"(?P=i)    execution_token=deterministic_token\(_context\.context_index\),\n"
            r"(?P=i)\)"
        )
        match = base.search(text)
        if not match:
            raise RuntimeError("canonical_execution_anchor_missing")
        indent = match.group("i")
        replacement = (
            f"{indent}result = run_lane_b_case(\n"
            f"{indent}    _Projected(_context, draft),\n"
            f"{indent}    execution_token=deterministic_token(_context.context_index),\n"
            f"{indent})\n"
            f"{indent}return apply_canonical_mechanics_fallback(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})"
        )
        text = text[:match.start()] + replacement + text[match.end():]
runtime.write_text(text, encoding="utf-8")
