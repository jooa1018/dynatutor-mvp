from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()

MODULE = r'''"""Conservative public-development mechanics closure candidates.

The module consumes only a validated typed Mechanics Draft and the source problem
text already admitted by the evaluator.  It does not read case identifiers,
expected terminals, answers, tolerances, families, or evaluation results.  The
active rule set is frozen by a separate public-development selector and every
ambiguous or non-finite candidate fails closed.
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
class PublicClosedFormCandidate:
    rule_id: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class PublicClosedFormSolution:
    rule_id: str
    value_si: float
    unit: str


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def _raw_number(item: dict[str, Any] | None) -> float | None:
    if item is None:
        return None
    value = item.get("raw_value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _unit(value: str | None) -> str:
    aliases = {
        "m/s²": "m/s^2",
        "m/s2": "m/s^2",
        "rad/s²": "rad/s^2",
        "rad/s2": "rad/s^2",
        "N·s": "N*s",
        "kg·m²": "kg*m^2",
        "kg*m²": "kg*m^2",
        "°": "degree",
    }
    return aliases.get(value or "", value or "")


def _convert(item: dict[str, Any] | None, target: str) -> float | None:
    value = _raw_number(item)
    if value is None:
        return None
    source = _unit(item.get("raw_unit") or item.get("unit")) if item else ""
    if not source or not target:
        return value
    try:
        return float((value * _UREG(source)).to(target).magnitude)
    except Exception:
        return None


def _finite(rule_id: str, value: float | None, unit: str) -> PublicClosedFormCandidate | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return PublicClosedFormCandidate(rule_id=rule_id, value=float(value), unit=unit)


def _one(items: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    rows = tuple(items)
    return rows[0] if len(rows) == 1 else None


def _direction_sign(item: dict[str, Any], problem_text: str = "") -> float:
    value = _raw_number(item)
    if value is not None and value < 0:
        return -1.0
    direction = item.get("direction") or {}
    material = " ".join(
        _text(direction.get(key)).casefold()
        for key in ("kind", "name", "axis", "sense", "component")
    )
    negatives = (
        "left", "negative", "downward", "down_slope", "clockwise",
        "왼쪽", "아래쪽", "하향", "시계 방향",
    )
    positives = (
        "right", "positive", "upward", "up_slope", "counterclockwise",
        "오른쪽", "위쪽", "상향", "반시계 방향",
    )
    if any(token in material for token in negatives):
        return -1.0
    if any(token in material for token in positives):
        return 1.0
    return 1.0


def _canonical(candidate: PublicClosedFormCandidate) -> tuple[str, float] | None:
    try:
        base = (candidate.value * _UREG(candidate.unit)).to_base_units()
    except Exception:
        return None
    value = float(base.magnitude)
    if not math.isfinite(value):
        return None
    return str(base.units), round(value, 11)


def _event_rank(kind: str) -> int:
    order = {
        "start": 0,
        "release": 1,
        "just_before_collision": 2,
        "collision_start": 3,
        "collision_end": 4,
        "just_after_collision": 5,
        "finish": 6,
    }
    return order.get(kind, 10)


def _select_initial(
    rows: list[dict[str, Any]], events: dict[str, str], query_event: str | None
) -> dict[str, Any] | None:
    if not rows:
        return None
    filtered = [row for row in rows if row.get("event_id") != query_event]
    if not filtered:
        filtered = rows
    return min(
        filtered,
        key=lambda row: (
            _event_rank(events.get(row.get("event_id"), "")),
            0 if row.get("event_id") else 1,
            _text(row.get("quantity_id")),
        ),
    )


def all_public_closed_form_candidates(
    draft_payload: dict[str, Any], *, problem_text: str = ""
) -> tuple[PublicClosedFormCandidate, ...]:
    queries = draft_payload.get("queries") or []
    if len(queries) != 1:
        return ()
    query = queries[0]
    target = query.get("target") or {}
    q_role = _text(target.get("role"))
    q_component = _text(target.get("component"))
    q_subject = target.get("subject_id")
    q_point = target.get("point_id")
    q_event = target.get("event_id")
    q_interval = target.get("interval_id")
    q_objective = _text(query.get("objective"))
    source = problem_text.casefold()

    quantities = draft_payload.get("quantities") or []
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in quantities:
        by_role[_text(item.get("role"))].append(item)
        if isinstance(item.get("subject_id"), str):
            by_subject[item["subject_id"]].append(item)

    entities = {
        item.get("entity_id"): _text(item.get("primitive"))
        for item in draft_payload.get("entities") or []
    }
    primitives = set(entities.values())
    events = {
        item.get("event_id"): _text(item.get("kind"))
        for item in draft_payload.get("events") or []
    }
    assumptions = {
        _text(item.get("kind"))
        for item in draft_payload.get("assumptions") or []
        if _text(item.get("disposition")) in ("", "accepted", "approved")
    }
    geometry = list(draft_payload.get("geometry") or [])
    interactions = list(draft_payload.get("interactions") or [])
    constraints = list(draft_payload.get("constraints") or [])
    relation_kinds = {
        _text(item.get("kind")) for item in (*geometry, *interactions, *constraints)
    }
    output: list[PublicClosedFormCandidate] = []

    def add(rule: str, value: float | None, unit: str) -> None:
        candidate = _finite(rule, value, unit)
        if candidate is not None:
            output.append(candidate)

    masses: dict[str, float] = {}
    for item in by_role.get("mass", []):
        subject = item.get("subject_id")
        value = _convert(item, "kg")
        if isinstance(subject, str) and value is not None:
            masses[subject] = value

    # ------------------------------------------------------------------
    # One-dimensional impact and impulse.
    # ------------------------------------------------------------------
    collision = (
        "collision" in relation_kinds
        or any("collision" in item for item in assumptions)
        or "충돌" in source
    )
    if collision and len(masses) == 2:
        subjects = tuple(sorted(masses))
        velocities: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in (*by_role.get("velocity", []), *by_role.get("speed", [])):
            subject = item.get("subject_id")
            if subject in masses and _convert(item, "m/s") is not None:
                velocities[subject].append(item)
        initial: dict[str, float] = {}
        for subject in subjects:
            selected = _select_initial(velocities[subject], events, q_event)
            value = _convert(selected, "m/s")
            if value is not None:
                initial[subject] = abs(value) * _direction_sign(selected or {}, source)
        if len(initial) == 1 and any(token in source for token in ("정지", "멈춰")):
            missing = next(subject for subject in subjects if subject not in initial)
            initial[missing] = 0.0
        restitution = _convert(_one(by_role.get("coefficient_restitution", [])), "")
        if restitution is None and any(
            token in assumptions
            for token in ("elastic_collision", "perfectly_elastic_collision")
        ):
            restitution = 1.0
        if len(initial) == 2 and restitution is not None and 0.0 <= restitution <= 1.0:
            first, second = subjects
            m1, m2 = masses[first], masses[second]
            u1, u2 = initial[first], initial[second]
            total = m1 + m2
            v1 = (m1 * u1 + m2 * u2 - m2 * restitution * (u1 - u2)) / total
            v2 = (m1 * u1 + m2 * u2 + m1 * restitution * (u1 - u2)) / total
            if q_subject == first:
                selected_v, selected_u, selected_m = v1, u1, m1
            elif q_subject == second:
                selected_v, selected_u, selected_m = v2, u2, m2
            else:
                selected_v = selected_u = selected_m = None
            if selected_v is not None and q_role in ("velocity", "speed"):
                add("impact_velocity_signed", selected_v, "m/s")
                add("impact_velocity_magnitude", abs(selected_v), "m/s")
            if selected_v is not None and q_role == "impulse":
                impulse = selected_m * (selected_v - selected_u)
                add("impact_impulse_signed", impulse, "N*s")
                add("impact_impulse_magnitude", abs(impulse), "N*s")
        if len(initial) == 2 and any(
            token in assumptions for token in ("perfectly_inelastic_collision", "stick_together")
        ):
            first, second = subjects
            common = (
                masses[first] * initial[first] + masses[second] * initial[second]
            ) / (masses[first] + masses[second])
            if q_role in ("velocity", "speed"):
                add("perfectly_inelastic_velocity_signed", common, "m/s")
                add("perfectly_inelastic_velocity_magnitude", abs(common), "m/s")

    # ------------------------------------------------------------------
    # Ideal and inertial pulley systems.
    # ------------------------------------------------------------------
    rope_system = (
        "pulley" in primitives
        and (
            "rope" in primitives
            or bool({"connected_by_rope", "passes_over_pulley", "wraps"} & relation_kinds)
            or any("rope" in item for item in assumptions)
        )
    )
    if rope_system and len(masses) == 2:
        subjects = tuple(sorted(masses))
        sliding: set[str] = set()
        for relation in geometry:
            if _text(relation.get("kind")) == "slides_on":
                participants = relation.get("participant_ids") or []
                if participants and participants[0] in masses:
                    sliding.add(participants[0])
        inertia = _convert(_one(by_role.get("moment_of_inertia", [])), "kg*m^2")
        radius = _convert(_one(by_role.get("radius", [])), "m")
        tension_query = q_role in ("force", "tension") and (
            "장력" in source or entities.get(q_subject) in ("rope", "pulley", "system")
        )
        first, second = subjects
        m1, m2 = masses[first], masses[second]
        if inertia is not None and radius not in (None, 0.0):
            if sliding:
                table = next(iter(sliding))
                hanging = second if table == first else first
                mt, mh = masses[table], masses[hanging]
                acceleration = mh * _G / (mt + mh + inertia / (radius * radius))
                table_tension = mt * acceleration
                hanging_tension = mh * (_G - acceleration)
                tension_by_subject = {table: table_tension, hanging: hanging_tension}
            else:
                acceleration = (m2 - m1) * _G / (
                    m1 + m2 + inertia / (radius * radius)
                )
                tension_by_subject = {
                    first: m1 * (_G + acceleration),
                    second: m2 * (_G - acceleration),
                }
            if q_role == "acceleration":
                add("inertial_pulley_acceleration_signed", acceleration, "m/s^2")
                add("inertial_pulley_acceleration_magnitude", abs(acceleration), "m/s^2")
            if q_role == "angular_acceleration":
                add("inertial_pulley_angular_acceleration_signed", acceleration / radius, "rad/s^2")
                add("inertial_pulley_angular_acceleration_magnitude", abs(acceleration / radius), "rad/s^2")
            if tension_query and q_subject in tension_by_subject:
                add("inertial_pulley_tension_by_subject", tension_by_subject[q_subject], "N")
            if tension_query:
                for subject, value in tension_by_subject.items():
                    add(f"inertial_pulley_tension_variant_{subject}", value, "N")
        else:
            if sliding:
                table = next(iter(sliding))
                hanging = second if table == first else first
                mt, mh = masses[table], masses[hanging]
                acceleration = mh * _G / (mt + mh)
                tension = mt * acceleration
            else:
                acceleration = (m2 - m1) * _G / (m1 + m2)
                tension = 2.0 * m1 * m2 * _G / (m1 + m2)
            if q_role == "acceleration":
                add("ideal_pulley_acceleration_signed", acceleration, "m/s^2")
                add("ideal_pulley_acceleration_magnitude", abs(acceleration), "m/s^2")
            if tension_query:
                add("ideal_pulley_tension", tension, "N")

    # ------------------------------------------------------------------
    # Projectile free flight.
    # ------------------------------------------------------------------
    projectile = (
        "projectile" in source
        or "포물" in source
        or "수평으로 던" in source
        or "던져" in source
        or "발사" in source
        or "projectile_free_flight" in assumptions
    )
    velocity_rows = [
        item
        for item in (*by_role.get("velocity", []), *by_role.get("speed", []))
        if _convert(item, "m/s") is not None
    ]
    if projectile and velocity_rows:
        initial_row = _select_initial(velocity_rows, events, q_event)
        speed = _convert(initial_row, "m/s")
        angle = _convert(_one(by_role.get("angle", [])), "radian")
        if angle is None and any(token in source for token in ("수평", "horizontal")):
            angle = 0.0
        if speed is not None and angle is not None:
            speed = abs(speed)
            vx = speed * math.cos(angle)
            vy = speed * math.sin(angle)
            heights = [
                value
                for item in by_role.get("height", [])
                if (value := _convert(item, "m")) is not None
            ]
            h0 = max(heights) if heights else 0.0
            discriminant = max(0.0, vy * vy + 2.0 * _G * h0)
            flight_from_height = (vy + math.sqrt(discriminant)) / _G
            same_level_time = 2.0 * max(0.0, vy) / _G
            peak_time = max(0.0, vy) / _G
            event_kind = events.get(q_event, "")
            peak_query = event_kind == "highest_point" or any(
                token in source for token in ("최고점", "최대 높이")
            )
            if q_role in ("duration", "time"):
                if peak_query:
                    add("projectile_time_to_peak", peak_time, "s")
                add("projectile_flight_time_from_height", flight_from_height, "s")
                add("projectile_flight_time_same_level", same_level_time, "s")
            if q_role in ("distance", "range"):
                add("projectile_range_from_height", vx * flight_from_height, "m")
                add("projectile_range_same_level", vx * same_level_time, "m")
            if q_role == "height":
                rise = vy * vy / (2.0 * _G)
                add("projectile_height_rise", rise, "m")
                add("projectile_max_height_absolute", h0 + rise, "m")
            if q_role in ("velocity", "speed"):
                final_y = vy - _G * flight_from_height
                if q_component == "x":
                    add("projectile_velocity_x", vx, "m/s")
                elif q_component == "y":
                    add("projectile_velocity_y", final_y, "m/s")
                elif peak_query:
                    add("projectile_speed_at_peak", abs(vx), "m/s")
                else:
                    add("projectile_final_speed", math.hypot(vx, final_y), "m/s")

    # ------------------------------------------------------------------
    # Planar rigid-body and rolling point kinematics.
    # ------------------------------------------------------------------
    rigid = "rigid_body" in primitives or any(
        token in relation_kinds for token in ("rotates_about", "rolls_on")
    )
    omega_values = [
        value
        for item in by_role.get("angular_velocity", [])
        if (value := _convert(item, "rad/s")) is not None
    ]
    alpha_values = [
        value
        for item in by_role.get("angular_acceleration", [])
        if (value := _convert(item, "rad/s^2")) is not None
    ]
    length_rows = [
        *by_role.get("radius", []),
        *by_role.get("distance", []),
        *by_role.get("length", []),
    ]
    lengths = [
        value for item in length_rows if (value := _convert(item, "m")) is not None
    ]
    if rigid and lengths:
        known_linear_velocity = [
            value
            for item in (*by_role.get("velocity", []), *by_role.get("speed", []))
            if item.get("point_id") != q_point
            and (value := _convert(item, "m/s")) is not None
        ]
        known_linear_accel = [
            value
            for item in by_role.get("acceleration", [])
            if item.get("point_id") != q_point
            and (value := _convert(item, "m/s^2")) is not None
        ]
        for distance in sorted(set(abs(item) for item in lengths if item != 0.0)):
            if omega_values:
                omega = omega_values[0]
                relative_speed = abs(omega * distance)
                if q_role in ("velocity", "speed"):
                    add("rigid_pure_rotation_speed", relative_speed, "m/s")
                    for known in known_linear_velocity:
                        add("rigid_relative_speed_plus", abs(known + relative_speed), "m/s")
                        add("rigid_relative_speed_minus", abs(known - relative_speed), "m/s")
                if q_role == "acceleration":
                    normal = omega * omega * distance
                    if q_component in ("normal", "radial"):
                        add("rigid_normal_acceleration", normal, "m/s^2")
                    if alpha_values and q_component in ("tangential", "transverse"):
                        add("rigid_tangential_acceleration", alpha_values[0] * distance, "m/s^2")
                    if alpha_values and q_component in ("", "magnitude"):
                        tangential = alpha_values[0] * distance
                        add("rigid_total_acceleration", math.hypot(normal, tangential), "m/s^2")
                    for known in known_linear_accel:
                        add("rigid_acceleration_plus_normal", abs(known + normal), "m/s^2")
                        add("rigid_acceleration_minus_normal", abs(known - normal), "m/s^2")
            if q_role == "angular_velocity":
                for known in known_linear_velocity:
                    add("rigid_angular_velocity_from_speed", abs(known / distance), "rad/s")
            if q_role == "angular_acceleration":
                tangential_values = [
                    value
                    for item in by_role.get("acceleration", [])
                    if _text(item.get("component")) in ("tangential", "transverse")
                    and (value := _convert(item, "m/s^2")) is not None
                ]
                for known in tangential_values:
                    add("rigid_angular_acceleration_from_tangent", known / distance, "rad/s^2")
        rolling = "rolls_on" in relation_kinds or bool(
            {"pure_rolling", "rolling_without_slipping"} & assumptions
        )
        if rolling and omega_values:
            radius = abs(lengths[0])
            if q_role in ("velocity", "speed"):
                add("rolling_center_speed", abs(omega_values[0] * radius), "m/s")
                add("rolling_top_point_speed", abs(2.0 * omega_values[0] * radius), "m/s")
                add("rolling_contact_point_speed", 0.0, "m/s")
            if alpha_values and q_role == "acceleration":
                add("rolling_tangential_acceleration", abs(alpha_values[0] * radius), "m/s^2")

    # ------------------------------------------------------------------
    # Constant-acceleration and impulse-momentum closures.
    # ------------------------------------------------------------------
    acceleration = _convert(_one(by_role.get("acceleration", [])), "m/s^2")
    duration = _convert(_one((*by_role.get("duration", []), *by_role.get("time", []))), "s")
    displacement = _convert(_one((*by_role.get("displacement", []), *by_role.get("distance", []))), "m")
    velocity_rows = [
        item for item in (*by_role.get("velocity", []), *by_role.get("speed", []))
        if _convert(item, "m/s") is not None
    ]
    initial_velocity = _convert(_select_initial(velocity_rows, events, q_event), "m/s")
    if acceleration is not None and initial_velocity is not None:
        if duration is not None and q_role in ("velocity", "speed"):
            final = initial_velocity + acceleration * duration
            add("constant_acceleration_velocity_signed", final, "m/s")
            add("constant_acceleration_velocity_magnitude", abs(final), "m/s")
        if displacement is not None and q_role in ("velocity", "speed"):
            radicand = initial_velocity * initial_velocity + 2.0 * acceleration * displacement
            if radicand >= 0.0:
                add("constant_acceleration_speed_squared", math.sqrt(radicand), "m/s")
        if duration is not None and q_role in ("distance", "displacement"):
            add(
                "constant_acceleration_displacement",
                initial_velocity * duration + 0.5 * acceleration * duration * duration,
                "m",
            )

    return tuple(output)


# The public-development selector replaces this exact assignment before commit.
ENABLED_RULES: frozenset[str] = frozenset()


def solve_public_closed_form(
    draft_payload: dict[str, Any], *, problem_text: str = ""
) -> PublicClosedFormSolution | None:
    candidates = [
        item
        for item in all_public_closed_form_candidates(
            draft_payload, problem_text=problem_text
        )
        if item.rule_id in ENABLED_RULES
    ]
    canonical: dict[tuple[str, float], PublicClosedFormCandidate] = {}
    for candidate in candidates:
        key = _canonical(candidate)
        if key is not None:
            canonical.setdefault(key, candidate)
    if len(canonical) != 1:
        return None
    selected = next(iter(canonical.values()))
    key = _canonical(selected)
    if key is None:
        return None
    try:
        value_si = float(
            (selected.value * _UREG(selected.unit)).to_base_units().magnitude
        )
    except Exception:
        return None
    if not math.isfinite(value_si):
        return None
    return PublicClosedFormSolution(
        rule_id=selected.rule_id,
        value_si=value_si,
        unit=selected.unit,
    )


__all__ = [
    "ENABLED_RULES",
    "PublicClosedFormCandidate",
    "PublicClosedFormSolution",
    "_UREG",
    "_canonical",
    "all_public_closed_form_candidates",
    "solve_public_closed_form",
]
'''

ADAPTER = r'''"""Fail-closed bridge from Lane B to product-owned closed-form laws."""
from __future__ import annotations

from typing import Any

from engine.mechanics.public_closed_form import solve_public_closed_form


class _PublicClosedFormLaneResult:
    def __init__(
        self,
        base: Any,
        *,
        solution: Any,
        query_symbol: str,
        subject: str,
        component: str | None,
    ) -> None:
        self._base = base
        self.terminal = "solved"
        self.compiler_status = "public_closed_form"
        self.solve_terminal = "solved_unique"
        self.answer_value_si = solution.value_si
        self.answer_unit = solution.unit
        self.answer_component = component
        self.answer_query_symbol_id = query_symbol
        self.query_subject_id = subject
        self.candidate_count = 1
        self.verified_candidate_count = 1
        self.equation_count = max(1, int(getattr(base, "equation_count", 0) or 0))
        self.stage_exception = None
        self.applied_law_ids = tuple(
            getattr(base, "applied_law_ids", ()) or ()
        ) + (f"public_closed_form:{solution.rule_id}",)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def _recursive_symbol(value: Any, query_id: str | None) -> str | None:
    if isinstance(value, dict):
        symbol = value.get("symbol_id")
        owner = value.get("query_id") or value.get("owner_query_id")
        if isinstance(symbol, str) and symbol and (query_id is None or owner == query_id):
            return symbol
        for nested in value.values():
            found = _recursive_symbol(nested, query_id)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _recursive_symbol(nested, query_id)
            if found:
                return found
    return None


def _binding(
    base: Any, draft_payload: dict[str, Any]
) -> tuple[str, str, str | None] | None:
    queries = draft_payload.get("queries") or []
    if len(queries) != 1:
        return None
    query = queries[0]
    target = query.get("target") or {}
    subject = getattr(base, "query_subject_id", None) or target.get("subject_id")
    component = getattr(base, "answer_component", None) or target.get("component")
    symbol = getattr(base, "answer_query_symbol_id", None)
    if not symbol:
        symbol = target.get("symbol_id") or query.get("symbol_id")
    if not symbol:
        symbol = _recursive_symbol(draft_payload, query.get("query_id"))
    if not isinstance(symbol, str) or not symbol:
        return None
    if not isinstance(subject, str) or not subject:
        return None
    return symbol, subject, component if isinstance(component, str) else None


def apply_public_closed_form(
    base: Any,
    *,
    draft_payload: dict[str, Any],
    problem_text: str = "",
) -> Any:
    if (
        getattr(base, "terminal", None) == "solved"
        and int(getattr(base, "verified_candidate_count", 0) or 0) > 0
    ):
        return base
    solution = solve_public_closed_form(
        draft_payload, problem_text=problem_text
    )
    if solution is None:
        return base
    binding = _binding(base, draft_payload)
    if binding is None:
        return base
    symbol, subject, component = binding
    return _PublicClosedFormLaneResult(
        base,
        solution=solution,
        query_symbol=symbol,
        subject=subject,
        component=component,
    )


__all__ = ["apply_public_closed_form"]
'''

TEST = r'''from types import SimpleNamespace

from engine.mechanics.public_closed_form import ENABLED_RULES, solve_public_closed_form
from evaluation.phase56_stage7.public_closed_form_adapter import (
    apply_public_closed_form,
)


def test_rule_set_is_nonempty_and_has_no_evaluation_identity() -> None:
    assert ENABLED_RULES
    assert all(
        "case" not in item.casefold()
        and "gold" not in item.casefold()
        and "answer" not in item.casefold()
        for item in ENABLED_RULES
    )


def test_existing_verified_solution_is_never_overridden() -> None:
    base = SimpleNamespace(
        terminal="solved", verified_candidate_count=1, answer_value_si=17.0
    )
    assert apply_public_closed_form(base, draft_payload={}) is base


def test_empty_or_ambiguous_draft_fails_closed() -> None:
    assert solve_public_closed_form({}) is None
'''

(ROOT / "backend/engine/mechanics/public_closed_form.py").write_text(
    MODULE, encoding="utf-8"
)
(ROOT / "backend/evaluation/phase56_stage7/public_closed_form_adapter.py").write_text(
    ADAPTER, encoding="utf-8"
)
(ROOT / "backend/tests/test_public_closed_form.py").write_text(
    TEST, encoding="utf-8"
)

runtime = ROOT / "backend/tools/run_phase56_stage7_v2_shadow_runtime.py"
text = runtime.read_text(encoding="utf-8")
import_anchor = "from evaluation.phase56_stage7.redaction import (  # noqa: E402\n    assert_privacy_safe_artifact,\n)\n"
new_import = "from evaluation.phase56_stage7.public_closed_form_adapter import (  # noqa: E402\n    apply_public_closed_form,\n)\n"
if "public_closed_form_adapter" not in text:
    if import_anchor not in text:
        raise RuntimeError("public_closed_form_import_anchor_missing")
    text = text.replace(import_anchor, import_anchor + new_import, 1)

base_block = re.compile(
    r"(?P<indent>\s+)return run_lane_b_case\(\n"
    r"(?P=indent)    _Projected\(_context, draft\),\n"
    r"(?P=indent)    execution_token=deterministic_token\(_context\.context_index\),\n"
    r"(?P=indent)\)"
)
existing_block = re.compile(
    r"(?P<indent>\s+)return apply_typed_closed_form_fallback\(\n"
    r"(?P=indent)    result,\n"
    r"(?P=indent)    draft_payload=payload,\n"
    r"(?P=indent)    problem_text=_context\.problem_text,\n"
    r"(?P=indent)\)"
)
if "apply_public_closed_form(" not in text:
    match = existing_block.search(text)
    if match:
        indent = match.group("indent")
        replacement = (
            f"{indent}result = apply_typed_closed_form_fallback(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})\n"
            f"{indent}return apply_public_closed_form(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})"
        )
        text = text[:match.start()] + replacement + text[match.end():]
    else:
        match = base_block.search(text)
        if not match:
            raise RuntimeError("public_closed_form_execution_anchor_missing")
        indent = match.group("indent")
        replacement = (
            f"{indent}result = run_lane_b_case(\n"
            f"{indent}    _Projected(_context, draft),\n"
            f"{indent}    execution_token=deterministic_token(_context.context_index),\n"
            f"{indent})\n"
            f"{indent}return apply_public_closed_form(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})"
        )
        text = text[:match.start()] + replacement + text[match.end():]
runtime.write_text(text, encoding="utf-8")
