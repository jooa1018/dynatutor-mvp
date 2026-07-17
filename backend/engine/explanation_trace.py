"""Deterministic construction of the public ExplanationTrace v1.

The builder consumes the already-selected solver result and the *post-gate*
response.  It never parses, routes, solves, verifies, selects, or mutates answer
fields.  Structured solver evidence is authoritative; legacy equation strings
are retained only as explicitly partial machine evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import math
import re
from typing import Any

from engine.models import (
    EquationEvidence,
    SemanticFactEvidence,
    SolverExplanationEvidence,
    SolverResult,
)
from engine.physics_core.answer_validators import OUTPUT_KEY_COMPATIBILITY


TRACE_SCHEMA = "dynatutor.explanation_trace"
TRACE_VERSION = "1.0"

_RESOLVED_STATUSES = {"resolved", "explicit"}
_DEFAULT_SOURCES = {
    "default",
    "fallback",
    "generic",
    "model_default",
    "physical_model_default",
    "unknown",
    "unresolved",
}
_ALLOWLISTED_SEMANTIC_ATTRIBUTES = (
    "subtype",
    "surface_type",
    "pulley_topology",
    "friction_type",
    "body_shape",
    "launch_height",
    "landing_height",
    "force_direction",
    "displacement_direction",
    "launch_angle_deg",
)
_ALLOWLISTED_FLAGS = {
    "air_resistance_ignored",
    "at_rest",
    "elastic_collision",
    "has_friction",
    "horizontal",
    "ideal_pulley",
    "massless_rope",
    "no_friction",
    "no_slip",
    "perfectly_inelastic",
    "pure_rolling",
    "starts_from_rest",
    "vertical",
}
_ALLOWLISTED_BRANCH_KEYS = {
    "branch_condition",
    "collision_branch",
    "contact_state",
    "direction_branch",
    "event_condition",
    "event_phase",
    "motion_direction",
    "motion_state",
    "root_selection",
    "time_branch",
    "time_interval",
}
_ALLOWLISTED_ASSUMPTION_KEYS = {
    "air_resistance",
    "constraint_model",
    "damping",
    "deformation",
    "energy_loss",
    "external_forcing",
    "friction_regime",
    "gravity_acceleration",
    "gravity_uniform",
    "ideal_constraint",
    "motion_model",
    "no_slip",
    "particle_model",
    "pulley_friction",
    "rope_mass",
    "small_angle",
    "spring_law",
}
_SEMANTIC_ENUM_VALUES = {
    "body_shape": {
        "solid_sphere", "hollow_sphere", "solid_cylinder", "disk", "hoop", "ring",
    },
    "displacement_direction": {
        "+x", "+y", "+z", "-x", "-y", "-z", "down", "down_slope",
        "forward", "left", "right", "up", "up_slope",
    },
    "force_direction": {
        "+x", "+y", "+z", "-x", "-y", "-z", "down", "down_slope",
        "left", "radial_inward", "radial_outward", "right", "tangential",
        "up", "up_slope",
    },
    "friction_type": {"kinetic", "none", "static", "unknown"},
    "pulley_topology": {"atwood", "compound", "fixed", "movable", "table_hanging"},
    "surface_type": {"curved", "flat", "horizontal", "incline", "rough", "smooth", "vertical"},
}
# This mapping is copied from the checked-in Phase 52 capability registry.  A
# subtype is meaningful only together with its canonical system type; accepting
# a globally "normalized" token here would turn solver-authored evidence into a
# carrier for arbitrary text.
_SUBTYPE_VALUES_BY_SYSTEM = {
    "particle_on_incline": {"no_friction", "with_friction"},
    "projectile_motion": {"general", "same_level"},
    "pure_rolling_energy": {"rolling_on_incline"},
    "rolling_energy_general": {"rolling_on_incline"},
    "vertical_circle": {"bottom", "top"},
}
_SEMANTIC_NUMERIC_CONTRACTS = {
    # Bounds are representation/privacy bounds, not solver tolerances.  They
    # prevent oversized scalar payloads while retaining the supported dynamics
    # domain.  Canonical/evidence values must still agree exactly below.
    "launch_height": (-1_000_000_000.0, 1_000_000_000.0, "m"),
    "landing_height": (-1_000_000_000.0, 1_000_000_000.0, "m"),
    "launch_angle_deg": (-360.0, 360.0, "deg"),
}
_BRANCH_ENUM_VALUES = {
    "branch_condition": {"active", "inactive", "satisfied"},
    "collision_branch": {"after_impact", "approaching", "before_impact", "during_impact", "separating"},
    "contact_state": {"contact", "detached", "impending"},
    "direction_branch": {"backward", "clockwise", "counterclockwise", "forward", "negative", "positive"},
    "event_condition": {"after_event", "approaching", "ascending", "at_event", "before_event", "descending", "separating"},
    "event_phase": {"after_impact", "before_impact", "during_impact", "final", "initial", "intermediate"},
    "motion_direction": {"backward", "clockwise", "counterclockwise", "down", "forward", "left", "right", "up"},
    "motion_state": {"at_rest", "moving", "rolling", "sliding"},
    "root_selection": {"earliest_nonnegative", "latest_nonnegative", "negative_root", "positive_root"},
    "time_branch": {"earliest_nonnegative", "latest_nonnegative", "negative_time", "positive_time"},
    "time_interval": {"after_event", "before_event", "during_event", "nonnegative_time"},
}
_ASSUMPTION_ENUM_VALUES = {
    "air_resistance": {"ignored", "included", "negligible"},
    "constraint_model": {"rotating_slot"},
    "damping": {"ignored"},
    "deformation": {"ignored", "included", "rigid"},
    "energy_loss": {"none"},
    "external_forcing": {"absent"},
    "friction_regime": {"limiting_static", "none"},
    "gravity_uniform": {"uniform"},
    "ideal_constraint": {"enforced", "ideal"},
    "motion_model": {"one_degree_of_freedom", "planar_polar", "uniform_circular"},
    "no_slip": {"enforced"},
    "particle_model": {"point_mass"},
    "pulley_friction": {"ignored", "included", "negligible"},
    "rope_mass": {"included", "massless", "negligible"},
    "small_angle": {"enforced", "valid"},
    "spring_law": {"linear"},
}
_ASSUMPTION_NUMERIC_CONTRACTS = {
    "gravity_acceleration": (9.81, "m/s^2"),
}
_FREE_FORM_ASSUMPTION_WARNING = (
    "free-form canonical assumptions were omitted; typed solver assumptions are required"
)
# The legacy diagnosis field remains byte-compatible.  For migrated solvers,
# these exact historical strings are acknowledged only when their calculation
# dependency is present as typed evidence.  Unknown/free-form text still fails
# closed and never becomes student-facing content.
_LEGACY_ASSUMPTION_REQUIREMENTS = {
    "incline_no_friction": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (("known:g", "assumption:gravity_acceleration"),),
        "블록을 질점으로 모델링": (("assumption:particle_model",),),
        "마찰력 없음": (("semantic:subtype",),),
    },
    "incline_with_friction": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (("known:g", "assumption:gravity_acceleration"),),
        "블록을 질점으로 모델링": (("assumption:particle_model",),),
    },
    "pure_rolling_energy": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (("known:g", "assumption:gravity_acceleration"),),
        "미끄러지지 않는 순수 구름": (("assumption:no_slip",),),
        "정지마찰은 일을 하지 않는 이상적 조건": (("assumption:energy_loss",),),
        "강체 종류 또는 관성모멘트가 필요함": (("semantic:body_shape",),),
    },
    "vertical_circle": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (("known:g", "assumption:gravity_acceleration"),),
    },
    "spring_mass_vibration": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (),
        "감쇠 없음": (("assumption:damping",),),
        "외력 없음": (("assumption:external_forcing",),),
        "평형 위치 기준 1자유도 운동": (("assumption:motion_model",),),
    },
    "spring_energy_speed": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (),
        "마찰 없음": (("assumption:energy_loss",),),
        "스프링 탄성에너지가 운동에너지로 전환": (("assumption:spring_law",),),
    },
    "work_energy_speed": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (),
    },
    "flat_curve_friction": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (("known:g", "assumption:gravity_acceleration"),),
        "등속 원운동으로 모델링": (("assumption:motion_model",),),
    },
    "banked_curve_no_friction": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (("known:g", "assumption:gravity_acceleration"),),
        "등속 원운동으로 모델링": (("assumption:motion_model",),),
    },
    "slot_pin_relative_motion": {
        "중력가속도 g = 9.81 m/s² 기본값 사용": (),
        "슬롯을 따라 미끄러지는 핀을 회전 좌표계의 극좌표 운동으로 모델링": (("assumption:constraint_model",),),
        "r 방향 상대속도와 θ 방향 회전속도를 동시에 고려": (("assumption:motion_model",),),
    },
}
_ALLOWED_FACT_SOURCES = {
    "assumption": {
        "canonical_assumption_typed",
        "solver_assumption",
        "solver_calculation",
    },
    "branch": {"solver_branch_explicit", "solver_calculation"},
    "flag": {"canonical_flag", "solver_input"},
    "known": {"canonical", "canonical_known", "solver_calculation", "solver_input"},
    "semantic": {"canonical_semantic", "solver_calculation", "solver_input"},
}
_ALLOWED_EQUATION_SOURCES = {"physics_core", "solver_calculation", "solver_equation"}
_ALLOWED_EQUATION_PROVENANCE = {
    "conservation_law",
    "constraint",
    "constitutive_law",
    "definition",
    "geometry",
    "governing_law",
    "kinematic_identity",
    "newton_second_law",
    "solver_derived",
}
_ALLOWED_SUBSTITUTION_SOURCES = {"physics_core", "solver_calculation"}
_ALLOWED_COORDINATE_SOURCES = {
    "canonical_coordinate",
    "physics_core",
    "solver_calculation",
}
_ALLOWED_MODEL_COORDINATE_SOURCES = _ALLOWED_COORDINATE_SOURCES | {
    "canonical_explicit",
    "physical_model_resolved",
}
_COORDINATE_SYSTEMS = {
    "body_fixed_2d",
    "body_fixed_3d",
    "cartesian_1d",
    "cartesian_2d",
    "cartesian_3d",
    "cylindrical_3d",
    "path_tangent_normal",
    "polar_2d",
    "spherical_3d",
}
_COORDINATE_AXIS_TOKENS = {
    "+x", "+y", "+z", "-x", "-y", "-z",
    "axial", "e_n", "e_phi", "e_r", "e_t", "e_theta",
    "n", "normal", "phi", "r", "radial", "t", "tangent", "theta",
    "x", "x/y", "x/z", "y", "y/z", "z",
}
_COORDINATE_DIRECTION_TOKENS = {
    "+x", "+y", "+z", "-x", "-y", "-z",
    "along_applied_force", "along_motion", "backward", "clockwise",
    "counterclockwise", "down", "down_slope", "forward", "increasing_r",
    "increasing_theta", "left", "normal_inward", "normal_outward",
    "opposite_applied_force", "opposite_motion", "radial_inward",
    "radial_outward", "right", "tangential_positive", "up", "up_slope",
}
_COORDINATE_UNIT_TOKENS = {
    "1", "N", "cm", "deg", "kg", "km", "m", "m/s", "m/s^2", "mm",
    "rad", "rad/s", "rad/s^2", "s",
}
# Code-owned physical unit vocabulary.  This mirrors the aliases accepted by
# engine.physics_core.units at the Phase 52 base, plus the existing vibration
# solver's Hz output and explicit dimensionless spellings.  New solver units
# must be added here deliberately; a syntactically plausible token is not
# trusted evidence.
_ALLOWED_PHYSICAL_UNITS = {
    None,
    "",
    "1",
    "dimensionless",
    "m/s²",
    "m/s^2",
    "m/s2",
    "m/s",
    "cm/s2",
    "cm/s²",
    "cm/s^2",
    "km/hr",
    "kmph",
    "km/h",
    "kg",
    "g",
    "m",
    "cm",
    "mm",
    "km",
    "s",
    "min",
    "N",
    "J",
    "Hz",
    "N*m",
    "Nm",
    "N/m",
    "kg*m^2",
    "kgm^2",
    "rad/s",
    "rad/s^2",
    "rad/s²",
    "rad/s2",
    "N·s",
    "N*s",
    "N·m",
    "kg·m^2",
    "kg·m²",
    "kg*m²",
    "deg",
    "rad",
}
_FORBIDDEN_SEMANTIC_TOKENS = {
    "problem",
    "problem_text",
    "raw",
    "raw_text",
    "solution",
    "source",
    "source_text",
    "student",
    "student_solution",
    "text",
}
_NORMALIZED_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,47}$")
_NORMALIZED_ENUM_VALUE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_NUMERIC_LITERAL = re.compile(r"(?<![A-Za-z_])[-+]?(?:\d+(?:\.\d*)?|\.\d+)")

# Candidate-key meaning is code-owned.  Equal numeric values are never enough
# to connect a raw solver variable to a delivered product field.
_OUTPUT_SEMANTICS_BY_CANDIDATE_KEY = {
    "t": {"time"},
    "time": {"time"},
    "s": {"distance"},
    "distance": {"distance"},
    "R": {"range", "distance"},
    "delta_x": {"distance"},
    "H": {"max_height"},
    "max_height": {"max_height"},
    "vf": {"final_velocity"},
    "v_f": {"final_velocity", "post_collision_velocity"},
    "v": {"final_velocity"},
    "final_velocity": {"final_velocity"},
    "a": {"acceleration"},
    "acceleration": {"acceleration"},
    "v0": {"initial_velocity"},
    "initial_velocity": {"initial_velocity"},
    "omega": {"angular_velocity"},
    "ω": {"angular_velocity"},
    "angular_velocity": {"angular_velocity"},
    "v_min": {"minimum_speed"},
    "minimum_speed": {"minimum_speed"},
    "T": {"tension"},
    "tension": {"tension"},
    "v1'": {"v1_after"},
    "v1_after": {"v1_after"},
    "v2'": {"v2_after"},
    "v2_after": {"v2_after"},
    "post_collision_velocity": {"post_collision_velocity"},
    "f_k": {"friction_force"},
    "f_s": {"friction_force"},
    "f_s,max": {"friction_force"},
    "friction_force": {"friction_force"},
    "N": {"normal_force"},
    "normal_force": {"normal_force"},
    "alpha": {"angular_acceleration"},
    "α": {"angular_acceleration"},
    "T1": {"tension"},
    "T2": {"tension"},
    "F": {"force"},
    "F_net": {"force"},
    "force": {"force"},
    "E_s": {"elastic_energy"},
    "elastic_energy": {"elastic_energy"},
}

_SOLVER_OUTPUT_SEMANTICS = {
    ("spring_mass_vibration", "T"): {"period"},
    ("spring_mass_vibration", "f"): {"frequency"},
    ("spring_mass_vibration", "omega_n"): {"angular_frequency"},
}
_KNOWN_OUTPUT_KEYS = (
    set(OUTPUT_KEY_COMPATIBILITY)
    | {item for values in OUTPUT_KEY_COMPATIBILITY.values() for item in values}
    | {
        item
        for values in _OUTPUT_SEMANTICS_BY_CANDIDATE_KEY.values()
        for item in values
    }
    | {item for values in _SOLVER_OUTPUT_SEMANTICS.values() for item in values}
)

# Explicit raw-to-delivery transforms.  The policy ID carries branch identity
# where a solver uses different rounding in different code paths; the builder
# never accepts an arbitrary ndigits value or infers policy from candidate IDs.
_DELIVERY_TRANSFORM_POLICIES = {
    "kinematics.time.round6": ("constant_acceleration_1d", "t", "time", "python_builtin_round", 6),
    "kinematics.distance.round6": ("constant_acceleration_1d", "s", "distance", "python_builtin_round", 6),
    "kinematics.final_velocity.round6": ("constant_acceleration_1d", "vf", "final_velocity", "python_builtin_round", 6),
    "kinematics.acceleration.round6": ("constant_acceleration_1d", "a", "acceleration", "python_builtin_round", 6),
    "kinematics.initial_velocity.round6": ("constant_acceleration_1d", "v0", "initial_velocity", "python_builtin_round", 6),
    "projectile.general.time.round6": ("projectile_motion", "t", "time", "python_builtin_round", 6),
    "projectile.general.range.round6": ("projectile_motion", "R", "range", "python_builtin_round", 6),
    "projectile.general.distance.round6": ("projectile_motion", "R", "distance", "python_builtin_round", 6),
    "projectile.general.delta_x.round6": ("projectile_motion", "delta_x", "distance", "python_builtin_round", 6),
    "incline.no_friction.acceleration.round5": ("incline_no_friction", "a", "acceleration", "python_builtin_round", 5),
    "incline.with_friction.moving.round5": ("incline_with_friction", "a", "acceleration", "python_builtin_round", 5),
}


def _stable_unique(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _warning_list(*groups: Iterable[str]) -> list[str]:
    values: list[str] = []
    for group in groups:
        for value in group:
            if isinstance(value, str) and value:
                values.append(value)
    return _stable_unique(values)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _contains_forbidden_semantic_token(value: str) -> bool:
    lowered = value.strip().lower()
    return any(token in lowered for token in _FORBIDDEN_SEMANTIC_TOKENS)


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _valid_semantic_attribute_value(
    key: str,
    value: Any,
    *,
    system_type: str | None,
) -> bool:
    numeric_contract = _SEMANTIC_NUMERIC_CONTRACTS.get(key)
    if numeric_contract is not None:
        minimum, maximum, _unit = numeric_contract
        return _is_finite_number(value) and minimum <= float(value) <= maximum
    if key == "subtype":
        return (
            isinstance(value, str)
            and value in _SUBTYPE_VALUES_BY_SYSTEM.get(system_type or "", set())
        )
    return (
        isinstance(value, str)
        and value in _SEMANTIC_ENUM_VALUES.get(key, set())
    )


def _valid_bounded_enum_value(
    key: str,
    value: Any,
    enum_values: dict[str, set[str]],
) -> bool:
    return isinstance(value, str) and value in enum_values.get(key, set())


def _valid_unit(unit: Any) -> bool:
    return unit is None or (
        isinstance(unit, str) and unit in _ALLOWED_PHYSICAL_UNITS
    )


def _valid_fact_unit(expected_group: str, semantic_key: str, unit: Any) -> bool:
    if not _valid_unit(unit):
        return False
    if expected_group == "known":
        return True
    if expected_group == "semantic":
        numeric_contract = _SEMANTIC_NUMERIC_CONTRACTS.get(semantic_key)
        expected_unit = numeric_contract[2] if numeric_contract is not None else None
        return unit == expected_unit
    if expected_group == "assumption":
        numeric_contract = _ASSUMPTION_NUMERIC_CONTRACTS.get(semantic_key)
        expected_unit = numeric_contract[1] if numeric_contract is not None else None
        return unit == expected_unit
    # Flags, branch conditions, and typed enum assumptions are dimensionless
    # state declarations and therefore never carry a unit string.
    return unit is None


def _validate_structured_fact(
    fact: SemanticFactEvidence,
    *,
    expected_group: str,
    system_type: str | None,
) -> str | None:
    if (
        not fact.fact_id
        or not fact.semantic_key
        or _contains_forbidden_semantic_token(fact.fact_id)
        or _contains_forbidden_semantic_token(fact.semantic_key)
    ):
        return "uses a forbidden or missing semantic identity"
    if fact.source not in _ALLOWED_FACT_SOURCES[expected_group]:
        return "uses an unapproved source"
    if fact.status not in _RESOLVED_STATUSES:
        return "is not resolved"
    if not _valid_fact_unit(expected_group, fact.semantic_key, fact.unit):
        return "uses a unit outside its code-owned physical contract"

    if expected_group == "known":
        expected_id = f"known:{fact.semantic_key}"
        if (
            fact.fact_id != expected_id
            or not _NORMALIZED_KEY.fullmatch(fact.semantic_key)
            or not _is_finite_number(fact.value)
            or fact.classification != "explicit"
        ):
            return "does not satisfy the normalized known-quantity contract"
        return None

    if expected_group == "semantic":
        expected_id = f"semantic:{fact.semantic_key}"
        if (
            fact.fact_id != expected_id
            or fact.semantic_key not in _ALLOWLISTED_SEMANTIC_ATTRIBUTES
            or not _valid_semantic_attribute_value(
                fact.semantic_key,
                fact.value,
                system_type=system_type,
            )
            or fact.classification != "explicit"
        ):
            return "does not satisfy the code-owned semantic-fact contract"
        return None

    if expected_group == "flag":
        expected_id = f"flag:{fact.semantic_key}"
        if (
            fact.fact_id != expected_id
            or fact.semantic_key not in _ALLOWLISTED_FLAGS
            or not isinstance(fact.value, bool)
            or fact.classification != "explicit"
        ):
            return "does not satisfy the allowlisted flag contract"
        return None

    if expected_group == "branch":
        expected_id = f"branch:{fact.semantic_key}"
        if (
            fact.fact_id != expected_id
            or fact.semantic_key not in _ALLOWLISTED_BRANCH_KEYS
            or not _valid_bounded_enum_value(
                fact.semantic_key, fact.value, _BRANCH_ENUM_VALUES
            )
            or fact.classification != "branch_condition"
        ):
            return "does not satisfy the bounded branch-condition contract"
        return None

    expected_id = f"assumption:{fact.semantic_key}"
    numeric_contract = _ASSUMPTION_NUMERIC_CONTRACTS.get(fact.semantic_key)
    if numeric_contract is not None:
        expected_value, _expected_unit = numeric_contract
        if (
            fact.fact_id != expected_id
            or fact.source != "solver_assumption"
            or fact.classification != "assumed"
            or not _is_finite_number(fact.value)
            or not _same_signed_number(fact.value, expected_value)
        ):
            return "does not satisfy the typed numeric assumption contract"
        return None
    if (
        fact.fact_id != expected_id
        or fact.semantic_key not in _ALLOWLISTED_ASSUMPTION_KEYS
        or not _valid_bounded_enum_value(
            fact.semantic_key, fact.value, _ASSUMPTION_ENUM_VALUES
        )
        or fact.classification != "assumed"
    ):
        return "does not satisfy the typed assumption contract"
    return None


def _looks_like_equation(expression: str) -> bool:
    return bool(expression.strip()) and any(
        operator in expression for operator in ("=", "≤", "≥", "<", ">")
    )


def _same_signed_number(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False
    left_value = float(left)
    right_value = float(right)
    if not math.isfinite(left_value) or not math.isfinite(right_value):
        return False
    if left_value != right_value:
        return False
    if left_value == 0.0:
        return math.copysign(1.0, left_value) == math.copysign(1.0, right_value)
    return True


def _substitution_finishes_with_output(
    expression: str,
    numeric: float | int,
    unit: str | None,
) -> bool:
    comparable = expression.strip().replace("−", "-")
    if unit and comparable.endswith(unit):
        comparable = comparable[: -len(unit)].rstrip()
    matches = _NUMERIC_LITERAL.findall(comparable)
    if not matches:
        return False
    try:
        return _same_signed_number(float(matches[-1]), numeric)
    except ValueError:
        return False


def _fact_payload(fact: SemanticFactEvidence) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "semantic_key": fact.semantic_key,
        "value": fact.value,
        "unit": fact.unit,
        "source": fact.source,
        "classification": fact.classification,
        "status": fact.status,
    }


def _legacy_assumptions_are_typed(
    canonical: Any,
    selected_solver: str | None,
    evidence: SolverExplanationEvidence | None,
) -> bool:
    values = list(getattr(canonical, "assumptions", []) or [])
    if not values:
        return True
    requirements = _LEGACY_ASSUMPTION_REQUIREMENTS.get(selected_solver or "")
    if evidence is None or requirements is None or any(
        not isinstance(value, str) or value not in requirements for value in values
    ):
        return False
    declared = {
        fact.fact_id for fact in (*evidence.explicit_facts, *evidence.assumptions)
    }
    return all(
        all(any(candidate in declared for candidate in alternatives) for alternatives in requirements[value])
        for value in values
    )


def _canonical_fact_inventory(
    canonical: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    explicit: dict[str, dict[str, Any]] = {}
    assumptions: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for key in sorted(getattr(canonical, "knowns", {}) or {}):
        quantity = canonical.knowns[key]
        value = getattr(quantity, "value", None)
        unit = getattr(quantity, "unit", None)
        if (
            not isinstance(key, str)
            or not _NORMALIZED_KEY.fullmatch(key)
            or _contains_forbidden_semantic_token(key)
            or not _is_finite_number(value)
            or not _valid_unit(unit)
        ):
            warnings.append("a canonical known quantity was omitted by the normalized fact allowlist")
            continue
        fact_id = f"known:{key}"
        explicit[fact_id] = {
            "fact_id": fact_id,
            "semantic_key": key,
            "value": value,
            "unit": unit,
            "source": "canonical_known",
            "classification": "explicit",
            "status": "resolved",
        }

    for attribute in _ALLOWLISTED_SEMANTIC_ATTRIBUTES:
        value = getattr(canonical, attribute, None)
        if value is None:
            continue
        if not _valid_semantic_attribute_value(
            attribute,
            value,
            system_type=getattr(canonical, "system_type", None),
        ):
            warnings.append(f"canonical semantic fact {attribute} was omitted by its value allowlist")
            continue
        fact_id = f"semantic:{attribute}"
        explicit[fact_id] = {
            "fact_id": fact_id,
            "semantic_key": attribute,
            "value": value,
            "unit": (
                _SEMANTIC_NUMERIC_CONTRACTS[attribute][2]
                if attribute in _SEMANTIC_NUMERIC_CONTRACTS
                else None
            ),
            "source": "canonical_semantic",
            "classification": "explicit",
            "status": "resolved",
        }

    for key, value in sorted((getattr(canonical, "flags", {}) or {}).items()):
        if key not in _ALLOWLISTED_FLAGS or not isinstance(value, bool):
            continue
        fact_id = f"flag:{key}"
        explicit[fact_id] = {
            "fact_id": fact_id,
            "semantic_key": key,
            "value": value,
            "unit": None,
            "source": "canonical_flag",
            "classification": "explicit",
            "status": "resolved",
        }

    if getattr(canonical, "assumptions", []) or []:
        warnings.append(_FREE_FORM_ASSUMPTION_WARNING)

    return explicit, assumptions, warnings


def _merge_structured_facts(
    explicit: dict[str, dict[str, Any]],
    assumptions: dict[str, dict[str, Any]],
    evidence: SolverExplanationEvidence,
    warnings: list[str],
    *,
    system_type: str | None,
) -> tuple[set[str], set[str], bool]:
    evidence_explicit_ids: set[str] = set()
    evidence_assumption_ids: set[str] = set()
    valid = True

    def merge(
        fact: SemanticFactEvidence,
        destination: dict[str, dict[str, Any]],
        expected_group: str,
        evidence_ids: set[str],
    ) -> None:
        nonlocal valid
        error = _validate_structured_fact(
            fact,
            expected_group=expected_group,
            system_type=system_type,
        )
        if error is not None:
            warnings.append(f"a structured fact was rejected because it {error}")
            valid = False
            return
        payload = _fact_payload(fact)
        existing = explicit.get(fact.fact_id) or assumptions.get(fact.fact_id)
        if expected_group in {"known", "semantic", "flag"} and existing is None:
            warnings.append(
                "a structured canonical fact has no exact canonical counterpart"
            )
            valid = False
            return
        if existing is not None:
            comparable_keys = ("semantic_key", "value", "unit", "classification", "status")
            if any(existing[key] != payload[key] for key in comparable_keys):
                warnings.append("a structured fact conflicts with canonical evidence")
                valid = False
                return
            evidence_ids.add(fact.fact_id)
            return
        destination[fact.fact_id] = payload
        evidence_ids.add(fact.fact_id)

    for fact in evidence.explicit_facts:
        if fact.classification == "branch_condition":
            group = "branch"
        elif fact.fact_id.startswith("known:"):
            group = "known"
        elif fact.fact_id.startswith("semantic:"):
            group = "semantic"
        elif fact.fact_id.startswith("flag:"):
            group = "flag"
        else:
            warnings.append("a structured fact uses an unapproved namespace")
            valid = False
            continue
        merge(fact, explicit, group, evidence_explicit_ids)
    for fact in evidence.assumptions:
        merge(fact, assumptions, "assumption", evidence_assumption_ids)
    return evidence_explicit_ids, evidence_assumption_ids, valid


def _valid_coordinate_components(
    *,
    coordinate_system: Any,
    axes: Any,
    positive_directions: Any,
    units: Any,
    source: Any,
    status: Any,
    model_source: bool = False,
) -> bool:
    allowed_sources = (
        _ALLOWED_MODEL_COORDINATE_SOURCES if model_source else _ALLOWED_COORDINATE_SOURCES
    )
    if source not in allowed_sources or status not in _RESOLVED_STATUSES:
        return False
    if coordinate_system not in _COORDINATE_SYSTEMS:
        return False
    if not isinstance(axes, (list, tuple)) or not axes:
        return False
    if (
        any(not isinstance(axis, str) or axis not in _COORDINATE_AXIS_TOKENS for axis in axes)
        or len(set(axes)) != len(axes)
    ):
        return False
    if (
        not isinstance(positive_directions, (list, tuple))
        or len(positive_directions) != len(axes)
        or any(
            not isinstance(direction, str)
            or direction not in _COORDINATE_DIRECTION_TOKENS
            for direction in positive_directions
        )
    ):
        return False
    if (
        not isinstance(units, (list, tuple))
        or len(units) not in {0, 1, len(axes)}
        or any(not isinstance(unit, str) or unit not in _COORDINATE_UNIT_TOKENS for unit in units)
    ):
        return False
    return True


def _frame_payload(frame: Any) -> dict[str, Any] | None:
    if frame is None:
        return None
    if (
        not isinstance(frame.frame_id, str)
        or not _NORMALIZED_ENUM_VALUE.fullmatch(frame.frame_id)
        or _contains_forbidden_semantic_token(frame.frame_id)
        or not _valid_coordinate_components(
            coordinate_system=frame.coordinate_system,
            axes=frame.axes,
            positive_directions=frame.positive_directions,
            units=frame.units,
            source=frame.source,
            status=frame.status,
        )
    ):
        return None
    return {
        "frame_id": frame.frame_id,
        "coordinate_system": frame.coordinate_system,
        "axes": list(frame.axes),
        "positive_directions": list(frame.positive_directions),
        "units": list(frame.units),
        "source": frame.source,
        "status": frame.status,
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        return payload if isinstance(payload, dict) else {}
    return {}


def _model_coordinate_frame(physical_model: Any) -> dict[str, Any] | None:
    """Return only a provenance-bearing, non-default model coordinate frame."""

    payload = _as_mapping(physical_model)
    candidates: list[Any] = []
    for key in ("calculation_coordinate_frame", "coordinate_frame", "coordinates", "coordinate_data"):
        if key in payload:
            candidates.append(payload[key])
    for key in ("kinematics", "dynamics", "model"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            for frame_key in ("calculation_coordinate_frame", "coordinate_frame", "coordinates"):
                if frame_key in nested:
                    candidates.append(nested[frame_key])

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source = candidate.get("source")
        status = candidate.get("status")
        coordinate_system = candidate.get("coordinate_system") or candidate.get("system")
        axes = candidate.get("axes") or []
        positive_directions = candidate.get("positive_directions") or []
        units = candidate.get("units") or []
        if not _valid_coordinate_components(
            coordinate_system=coordinate_system,
            axes=axes,
            positive_directions=positive_directions,
            units=units,
            source=source,
            status=status,
            model_source=True,
        ):
            continue
        return {
            "coordinate_system": coordinate_system,
            "axes": list(axes),
            "positive_directions": list(positive_directions),
            "units": list(units),
        }
    return None


def _normalized_sequence(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(str(value).strip().lower() for value in values)


def _coordinate_mismatch(
    evidence_frame: dict[str, Any] | None,
    physical_model: Any,
) -> bool:
    model_frame = _model_coordinate_frame(physical_model)
    if evidence_frame is None or model_frame is None:
        return False
    if str(evidence_frame["coordinate_system"]).strip().lower() != str(
        model_frame["coordinate_system"]
    ).strip().lower():
        return True
    for key in ("axes", "positive_directions", "units"):
        left = _normalized_sequence(evidence_frame.get(key) or [])
        right = _normalized_sequence(model_frame.get(key) or [])
        if left and right and left != right:
            return True
    return False


def _equation_payload(equation: EquationEvidence) -> dict[str, Any]:
    return {
        "equation_id": equation.equation_id,
        "expression": equation.expression,
        "source": equation.source,
        "provenance": equation.provenance,
        "fact_ids": list(equation.fact_ids),
        "input_output_ids": list(equation.input_output_ids),
        "output_ids": list(equation.output_ids),
    }


def _legacy_equations(result: SolverResult | None, legacy_steps: Sequence[Any]) -> list[dict[str, Any]]:
    expressions: list[str] = []
    if result is not None:
        expressions.extend(
            value for value in (result.used_equations or []) if isinstance(value, str)
        )
    expressions.extend(
        math_text
        for step in legacy_steps
        if isinstance((math_text := getattr(step, "math", None)), str)
    )
    equations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for expression in expressions:
        normalized = expression.strip()
        if not _looks_like_equation(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        equations.append(
            {
                "equation_id": f"legacy:eq:{len(equations):03d}",
                "expression": normalized,
                "source": "legacy_unverified",
                "provenance": "legacy_partial",
                "fact_ids": [],
                "input_output_ids": [],
                "output_ids": [],
            }
        )
    return equations


def _delivered_answers(response: Any) -> list[dict[str, Any]]:
    answers = list(getattr(response, "answers", []) or [])
    if answers:
        return [
            {
                "index": index,
                "label": answer.label,
                "symbol": answer.symbol,
                "numeric": answer.numeric,
                "unit": answer.unit,
                "display": answer.display,
                "role": answer.role,
                "output_key": answer.output_key,
            }
            for index, answer in enumerate(answers)
        ]
    answer = getattr(response, "answer", None)
    if answer is None:
        return []
    return [
        {
            "index": 0,
            "label": "최종 답",
            "symbol": None,
            "numeric": answer.numeric,
            "unit": answer.unit,
            "display": answer.display or "",
            "role": "primary",
            "output_key": answer.output_key,
        }
    ]


def _top_level_answer_matches_primary(
    response: Any,
    delivered: list[dict[str, Any]],
    warnings: list[str],
) -> bool:
    """Close the compatibility edge without changing either public answer view."""

    answer = getattr(response, "answer", None)
    answers = list(getattr(response, "answers", []) or [])
    if answer is None or not answers:
        return True
    primary = [item for item in delivered if item.get("role") == "primary"]
    if not primary:
        warnings.append("top-level answer has no primary delivered output authority")
        return False
    first = primary[0]
    primary_key = first.get("output_key")
    if (
        not isinstance(primary_key, str)
        or not primary_key
        or primary_key not in _KNOWN_OUTPUT_KEYS
        or sum(item.get("output_key") == primary_key for item in primary) != 1
    ):
        warnings.append("first primary delivered output has no unique semantic key")
        return False
    if not _same_signed_number(getattr(answer, "numeric", None), first.get("numeric")):
        warnings.append("top-level answer numeric does not exactly match the first primary output")
        return False
    if getattr(answer, "unit", None) != first.get("unit"):
        warnings.append("top-level answer unit does not exactly match the first primary output")
        return False
    answer_key = getattr(answer, "output_key", None)
    if answer_key is None:
        return True
    if (
        not isinstance(answer_key, str)
        or not answer_key
        or answer_key not in _KNOWN_OUTPUT_KEYS
        or primary_key
        not in ({answer_key} | OUTPUT_KEY_COMPATIBILITY.get(answer_key, set()))
    ):
        warnings.append("top-level answer semantic key is incompatible with the first primary output")
        return False
    return True


def _selected_candidate_summary(
    response: Any,
    *,
    raw_selection_decision: Any = None,
    delivery_decision: Any = None,
) -> tuple[dict[str, Any], Any]:
    decision = getattr(response, "selection_decision", None)
    if (
        getattr(raw_selection_decision, "status", None) == "selected"
        and getattr(delivery_decision, "status", None) == "selected"
    ):
        decision = raw_selection_decision
    status = getattr(decision, "status", None) or "not_available"
    selected = getattr(decision, "selected_candidate", None)
    alternatives = list(getattr(decision, "valid_alternatives", []) or [])
    rejected = list(getattr(decision, "rejected_candidates", []) or [])
    return (
        {
            "status": status,
            "selected_candidate_id": getattr(selected, "candidate_id", None),
            "selection_policy": getattr(decision, "selection_policy", None),
            "alternative_count": len(alternatives),
            "rejected_count": len(rejected),
            "branch_fact_ids": [],
        },
        selected,
    )


def _candidate_value(selected: Any, key: str) -> tuple[bool, Any]:
    mapping = getattr(selected, "numerical_mapping", None)
    if not isinstance(mapping, dict) or not isinstance(key, str) or not key:
        return False, None
    if key not in mapping:
        return False, None
    value = mapping[key]
    if not _is_finite_number(value):
        return False, None
    return True, value


def _candidate_key_matches_output(
    candidate_key: str,
    output_key: Any,
    *,
    selected_solver: str | None,
) -> bool:
    if not isinstance(candidate_key, str) or not isinstance(output_key, str):
        return False
    solver_semantics = _SOLVER_OUTPUT_SEMANTICS.get(
        (selected_solver, candidate_key)
    )
    if solver_semantics is not None:
        return output_key in solver_semantics
    return output_key in _OUTPUT_SEMANTICS_BY_CANDIDATE_KEY.get(
        candidate_key, set()
    )


def _delivery_mapping_is_exact(
    delivered: list[dict[str, Any]], delivery_candidate: Any
) -> bool:
    mapping = getattr(delivery_candidate, "numerical_mapping", None)
    if not isinstance(mapping, dict):
        return False
    expected_keys = {
        str(key)
        for item in delivered
        for key in (item.get("output_key"), item.get("symbol"))
        if isinstance(key, str) and key
    }
    # candidate_from_solver_result deliberately retains this code-owned
    # representative alias for one-answer legacy results before also adding the
    # semantic output key.  It is expected only when the delivered item has no
    # symbol and can never be selected as explanation evidence.
    if any(item.get("symbol") is None for item in delivered):
        expected_keys.add("answer")
    return set(mapping) == expected_keys and all(
        _is_finite_number(value) for value in mapping.values()
    )


def _delivery_transform_is_exact(
    link: Any,
    *,
    selected_solver: str | None,
    raw_is_delivery_authority: bool,
) -> bool:
    raw = link.candidate_numeric
    delivered = link.numeric
    if not _is_finite_number(raw) or not _is_finite_number(delivered):
        return False
    if isinstance(link.decimal_places, bool):
        return False

    # A direct/legacy solver has one identity *decision object*.  Candidate-ID
    # equality is not used to infer this relationship.
    if raw_is_delivery_authority:
        return (
            not link.delivery_policy_id
            and link.candidate_id == link.delivery_candidate_id
            and link.candidate_key == link.delivery_candidate_key
            and link.delivery_transform == "identity"
            and link.decimal_places is None
            and _same_signed_number(raw, delivered)
        )

    policy = _DELIVERY_TRANSFORM_POLICIES.get(link.delivery_policy_id)
    if policy is None:
        return False
    expected = (
        selected_solver,
        link.candidate_key,
        link.output_key,
        link.delivery_transform,
        link.decimal_places,
    )
    if policy != expected:
        return False
    if link.delivery_transform == "identity":
        return link.decimal_places is None and _same_signed_number(raw, delivered)
    if link.delivery_transform != "python_builtin_round":
        return False
    if not isinstance(link.decimal_places, int):
        return False
    rounded = round(raw, link.decimal_places)
    return _same_signed_number(rounded, delivered)


def _match_output_links(
    delivered: list[dict[str, Any]],
    evidence: SolverExplanationEvidence,
    selected_candidate: Any,
    candidate_summary: dict[str, Any],
    delivery_decision: Any,
    selected_solver: str | None,
    raw_is_delivery_authority: bool,
    equations_by_id: dict[str, dict[str, Any]],
    substitutions_by_id: dict[str, dict[str, Any]],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], bool]:
    links = list(evidence.outputs)
    if len(links) != len(delivered):
        warnings.append("delivered outputs do not have exactly one structured output link each")
        return [], False
    output_ids = [link.output_id for link in links]
    if any(not output_id for output_id in output_ids) or len(set(output_ids)) != len(output_ids):
        warnings.append("delivered output evidence IDs must be nonempty and unique")
        return [], False
    explicit_indices = [
        link.response_index for link in links if link.response_index is not None
    ]
    if len(set(explicit_indices)) != len(explicit_indices):
        warnings.append("structured output links reuse a delivered response index")
        return [], False

    selected_candidate_id = candidate_summary["selected_candidate_id"]
    if candidate_summary["status"] != "selected" or selected_candidate_id is None:
        warnings.append("selected candidate evidence is unavailable")
        return [], False

    delivery_status = getattr(delivery_decision, "status", None)
    delivery_candidate = getattr(delivery_decision, "selected_candidate", None)
    delivery_candidate_id = getattr(delivery_candidate, "candidate_id", None)
    if delivery_status != "selected" or delivery_candidate_id is None:
        warnings.append("delivered-output candidate evidence is unavailable")
        return [], False
    if not _delivery_mapping_is_exact(delivered, delivery_candidate):
        warnings.append("delivered-output candidate keys are missing, ambiguous, or surplus")
        return [], False

    output_key_counts: dict[Any, int] = {}
    for delivered_item in delivered:
        output_key = delivered_item["output_key"]
        output_key_counts[output_key] = output_key_counts.get(output_key, 0) + 1

    matched_links: dict[int, Any] = {}
    unused = set(range(len(links)))
    for delivered_item in delivered:
        index = delivered_item["index"]
        explicit = [
            link_index
            for link_index in unused
            if links[link_index].response_index == index
        ]
        if explicit:
            candidates = explicit
        else:
            candidates = [
                link_index
                for link_index in unused
                if links[link_index].response_index is None
                and links[link_index].output_key == delivered_item["output_key"]
                and (
                    links[link_index].symbol is None
                    or links[link_index].symbol == delivered_item["symbol"]
                )
                and (
                    links[link_index].role is None
                    or links[link_index].role == delivered_item["role"]
                )
            ]
        if len(candidates) != 1:
            warnings.append(f"delivered output index {index} has an ambiguous evidence link")
            return [], False
        link_index = candidates[0]
        matched_links[index] = links[link_index]
        unused.remove(link_index)
    if unused:
        warnings.append("surplus structured output link identities were not consumed")
        return [], False

    for output_key, count in output_key_counts.items():
        if count <= 1:
            continue
        keys = [
            matched_links[item["index"]].delivery_candidate_key
            for item in delivered
            if item["output_key"] == output_key
        ]
        if (
            any(not isinstance(key, str) or not key for key in keys)
            or len(keys) != count
            or len(set(keys)) != count
        ):
            warnings.append(
                f"duplicated output_key {output_key!r} must use globally unique delivery keys"
            )
            return [], False

    derivations: list[dict[str, Any]] = []
    valid = True
    substitution_owners: dict[str, str] = {}
    for delivered_item in delivered:
        link = matched_links[delivered_item["index"]]
        prefix = f"output {link.output_id}"
        if not link.output_key or link.output_key != delivered_item["output_key"]:
            warnings.append(f"{prefix} output_key does not match the delivered response")
            valid = False
        if link.symbol is not None and link.symbol != delivered_item["symbol"]:
            warnings.append(f"{prefix} symbol does not match the delivered response")
            valid = False
        if link.role is not None and link.role != delivered_item["role"]:
            warnings.append(f"{prefix} role does not match the delivered response")
            valid = False
        if link.candidate_id != selected_candidate_id:
            warnings.append(f"{prefix} is not linked to the selected candidate")
            valid = False
        if not _candidate_key_matches_output(
            link.candidate_key,
            link.output_key,
            selected_solver=selected_solver,
        ):
            warnings.append(f"{prefix} raw candidate key has the wrong physical meaning")
            valid = False
        found_candidate_value, candidate_value = _candidate_value(
            selected_candidate, link.candidate_key
        )
        if (
            not found_candidate_value
            or not _same_signed_number(link.candidate_numeric, candidate_value)
        ):
            warnings.append(f"{prefix} raw candidate key/value is not exact")
            valid = False

        if link.delivery_candidate_id != delivery_candidate_id:
            warnings.append(f"{prefix} is not linked to the delivered-output candidate")
            valid = False
        if not _candidate_key_matches_output(
            link.delivery_candidate_key,
            link.output_key,
            selected_solver=selected_solver,
        ):
            warnings.append(f"{prefix} delivery candidate key has the wrong physical meaning")
            valid = False
        if (
            output_key_counts.get(delivered_item["output_key"], 0) > 1
            and link.delivery_candidate_key != delivered_item["symbol"]
        ):
            warnings.append(
                f"{prefix} must use its unique symbol key for a duplicated output_key"
            )
            valid = False
        found_delivery_value, delivery_value = _candidate_value(
            delivery_candidate, link.delivery_candidate_key
        )
        if (
            not found_delivery_value
            or not _same_signed_number(link.numeric, delivery_value)
        ):
            warnings.append(f"{prefix} delivery candidate key/value is not exact")
            valid = False
        if not _delivery_transform_is_exact(
            link,
            selected_solver=selected_solver,
            raw_is_delivery_authority=raw_is_delivery_authority,
        ):
            warnings.append(f"{prefix} raw-to-delivery transform is not code-owned and exact")
            valid = False
        if not _same_signed_number(link.numeric, delivered_item["numeric"]):
            warnings.append(f"{prefix} signed numeric value does not match the delivered response")
            valid = False
        if link.unit != delivered_item["unit"]:
            warnings.append(f"{prefix} unit does not match the delivered response")
            valid = False
        if not _valid_unit(link.unit) or not _valid_unit(delivered_item["unit"]):
            warnings.append(f"{prefix} unit is outside the code-owned physical vocabulary")
            valid = False

        if (
            not link.equation_ids
            or len(set(link.equation_ids)) != len(link.equation_ids)
            or any(
                equation_id not in equations_by_id
                for equation_id in link.equation_ids
            )
        ):
            warnings.append(f"{prefix} has an invalid equation link")
            valid = False
        if (
            not link.substitution_ids
            or len(set(link.substitution_ids)) != len(link.substitution_ids)
            or any(
                substitution_id not in substitutions_by_id
                for substitution_id in link.substitution_ids
            )
        ):
            warnings.append(f"{prefix} has an invalid substitution link")
            valid = False
        linked_substitutions = [
            substitutions_by_id[substitution_id]
            for substitution_id in link.substitution_ids
            if substitution_id in substitutions_by_id
        ]
        for substitution_id in link.substitution_ids:
            owner = substitution_owners.get(substitution_id)
            if owner is not None and owner != link.output_id:
                warnings.append(f"{prefix} reuses a substitution owned by another output")
                valid = False
            else:
                substitution_owners[substitution_id] = link.output_id
        if not linked_substitutions or any(
            substitution["output_id"] != link.output_id
            for substitution in linked_substitutions
        ):
            warnings.append(f"{prefix} is not produced by every linked substitution")
            valid = False
        elif not all(
            _substitution_finishes_with_output(
                substitution["expression"], link.numeric, link.unit
            )
            for substitution in linked_substitutions
        ):
            warnings.append(f"{prefix} does not match its final substitution value")
            valid = False
        linked_equation_ids = set(link.equation_ids)
        substitution_equation_ids = {
            substitution["equation_id"] for substitution in linked_substitutions
        }
        if linked_equation_ids != substitution_equation_ids:
            warnings.append(f"{prefix} has swapped or surplus equation/substitution links")
            valid = False
        if any(
            link.output_id not in equations_by_id[equation_id]["output_ids"]
            for equation_id in link.equation_ids
            if equation_id in equations_by_id
        ):
            warnings.append(f"{prefix} is not declared by every linked equation")
            valid = False

        derivations.append(
            {
                "output_id": link.output_id,
                "output_key": link.output_key,
                "label": delivered_item["label"],
                "symbol": delivered_item["symbol"],
                "role": delivered_item["role"],
                "numeric": link.numeric,
                "unit": link.unit,
                "display": delivered_item["display"],
                "candidate_id": link.candidate_id,
                "equation_ids": list(link.equation_ids),
                "substitution_ids": list(link.substitution_ids),
            }
        )
    return (derivations if valid else []), valid


def _validation_summary(response: Any) -> dict[str, Any]:
    verification = getattr(response, "verification", None)
    structured = list(getattr(verification, "structured_checks", []) or [])
    legacy = list(getattr(verification, "checks", []) or [])
    warnings = list(getattr(verification, "warnings", []) or [])
    errors = list(getattr(verification, "errors", []) or [])
    return {
        "passed": bool(getattr(verification, "passed", False)),
        "policy_version": getattr(verification, "policy_version", None),
        "check_count": len(structured) if structured else len(legacy),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }


def _terminal_status(response: Any, canonical: Any, route_decision: Any) -> str | None:
    conflicts = list(getattr(getattr(canonical, "canonical_v2", None), "conflicts", []) or [])
    errors = list(getattr(getattr(response, "verification", None), "errors", []) or [])
    if conflicts or any("contradict" in str(error).lower() for error in errors):
        return "contradictory"
    selection_status = getattr(getattr(response, "selection_decision", None), "status", None)
    route_status = getattr(route_decision, "status", None)
    if selection_status == "ambiguous" or route_status == "clarify":
        return "ambiguous"
    if route_status == "unsupported":
        return "unsupported"
    return None


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _full_student_steps(
    coordinate_frame: dict[str, Any],
    explicit_facts: list[dict[str, Any]],
    assumptions: list[dict[str, Any]],
    equations: list[dict[str, Any]],
    substitutions: list[dict[str, Any]],
    derivations: list[dict[str, Any]],
    referenced_fact_ids: set[str],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    used_facts = [fact for fact in explicit_facts if fact["fact_id"] in referenced_fact_ids]
    if used_facts:
        lines = []
        for fact in used_facts:
            unit = f" {fact['unit']}" if fact["unit"] else ""
            lines.append(f"{fact['semantic_key']} = {_format_scalar(fact['value'])}{unit}")
        steps.append({"kind": "facts", "title": "주어진 조건", "body": "\n".join(lines), "math": None})

    coordinate_lines = [coordinate_frame["coordinate_system"]]
    for axis, direction in zip(
        coordinate_frame["axes"], coordinate_frame["positive_directions"]
    ):
        coordinate_lines.append(f"{axis}: {direction}")
    steps.append(
        {
            "kind": "coordinate_frame",
            "title": "좌표계와 부호",
            "body": "\n".join(coordinate_lines),
            "math": None,
        }
    )

    used_assumptions = [
        fact for fact in assumptions if fact["fact_id"] in referenced_fact_ids
    ]
    if used_assumptions:
        steps.append(
            {
                "kind": "assumptions",
                "title": "가정",
                "body": "\n".join(_format_scalar(fact["value"]) for fact in used_assumptions),
                "math": None,
            }
        )

    for equation in equations:
        steps.append(
            {
                "kind": "equation",
                "title": "관계식",
                "body": "근거가 연결된 관계식을 적용합니다.",
                "math": equation["expression"],
            }
        )
    for substitution in substitutions:
        steps.append(
            {
                "kind": "substitution",
                "title": "값 대입",
                "body": "연결된 조건을 대입합니다.",
                "math": substitution["expression"],
            }
        )
    steps.append(
        {
            "kind": "answer",
            "title": "최종 답",
            "body": "\n".join(
                f"{derivation['label']}: {derivation['display']}"
                for derivation in derivations
            ),
            "math": None,
        }
    )
    steps.append(
        {
            "kind": "validation",
            "title": "검산",
            "body": "선택된 해와 최종 응답의 값, 부호, 단위가 일치합니다.",
            "math": None,
        }
    )
    return steps


def _neutral_student_steps(status: str) -> list[dict[str, Any]]:
    guidance = {
        "ambiguous": "가능한 해를 하나로 고르려면 사건, 방향 또는 시간 구간을 더 지정해 주세요.",
        "unsupported": "지원되는 물리 모형인지와 계산에 필요한 입력을 확인해 주세요.",
        "contradictory": "서로 충돌하는 입력 조건을 먼저 정정해 주세요.",
    }.get(status, "문제의 사건 조건, 방향, 단위와 필요한 값을 확인해 주세요.")
    return [
        {
            "kind": "status",
            "title": "풀이 상태",
            "body": "현재 구조화된 근거만으로 계산 과정을 확정할 수 없습니다.",
            "math": None,
        },
        {
            "kind": "required_input",
            "title": "다음 확인",
            "body": guidance,
            "math": None,
        },
    ]


def neutral_explanation_trace_payload(
    *,
    selected_solver: str | None,
    route_reason: str | None,
    status: str = "withheld",
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Fail-open trace used when construction itself fails.

    This function does not inspect or mutate a product answer.
    """

    return {
        "schema": TRACE_SCHEMA,
        "version": TRACE_VERSION,
        "status": status,
        "selected_solver": selected_solver,
        "route_reason": route_reason,
        "coordinate_frame": None,
        "explicit_facts": [],
        "assumptions": [],
        "equation_ids": [],
        "equations": [],
        "substitutions": [],
        "candidate_summary": {
            "status": "not_available",
            "selected_candidate_id": None,
            "selection_policy": None,
            "alternative_count": 0,
            "rejected_count": 0,
            "branch_fact_ids": [],
        },
        "validation_summary": {
            "passed": False,
            "policy_version": None,
            "check_count": 0,
            "warning_count": 0,
            "error_count": 0,
        },
        "answer_derivation": [],
        "warnings": _warning_list(warnings),
        "student_steps": _neutral_student_steps(status),
    }


def build_explanation_trace_payload(
    *,
    response: Any,
    canonical: Any,
    physical_model: Any,
    result: SolverResult | None,
    selected_solver: str | None,
    route_reason: str | None,
    route_decision: Any = None,
    legacy_steps: Sequence[Any] = (),
    delivery_decision: Any = None,
    raw_selection_decision: Any = None,
) -> dict[str, Any]:
    """Build ExplanationTrace v1 from one completed pipeline pass.

    ``response`` must already reflect ``apply_result_gate``.  No answer field is
    written here, including on grounding failure.
    """

    evidence = result.explanation_evidence if result is not None else None
    explicit, assumptions, canonical_fact_warnings = _canonical_fact_inventory(canonical)
    if _legacy_assumptions_are_typed(canonical, selected_solver, evidence):
        canonical_fact_warnings = [
            warning
            for warning in canonical_fact_warnings
            if warning != _FREE_FORM_ASSUMPTION_WARNING
        ]
    grounding_warnings: list[str] = list(canonical_fact_warnings)
    grounding_valid = evidence is not None and not canonical_fact_warnings
    evidence_explicit_ids: set[str] = set()
    evidence_assumption_ids: set[str] = set()
    if evidence is not None:
        evidence_explicit_ids, evidence_assumption_ids, structured_facts_valid = _merge_structured_facts(
            explicit,
            assumptions,
            evidence,
            grounding_warnings,
            system_type=getattr(canonical, "system_type", None),
        )
        grounding_valid = grounding_valid and structured_facts_valid

    coordinate_frame = _frame_payload(evidence.coordinate_frame) if evidence else None
    coordinate_critical = False
    if coordinate_frame is None:
        grounding_warnings.append("resolved solver calculation coordinates are unavailable")
        grounding_valid = False
    else:
        status = str(coordinate_frame["status"]).strip().lower()
        source = str(coordinate_frame["source"]).strip().lower()
        if (
            status not in _RESOLVED_STATUSES
            or source in _DEFAULT_SOURCES
            or not coordinate_frame["coordinate_system"]
            or not coordinate_frame["axes"]
            or not coordinate_frame["positive_directions"]
            or len(coordinate_frame["axes"]) != len(coordinate_frame["positive_directions"])
        ):
            grounding_warnings.append("default or unresolved coordinate dimensions were omitted")
            coordinate_frame = None
            grounding_valid = False
        elif _coordinate_mismatch(coordinate_frame, physical_model):
            grounding_warnings.append("solver and physical-model coordinate frames disagree")
            coordinate_critical = True
            grounding_valid = False

    if evidence is None:
        equations = _legacy_equations(result, legacy_steps)
        substitutions: list[dict[str, Any]] = []
    else:
        equations = [_equation_payload(item) for item in evidence.equations]
        substitutions = [
            {
                "substitution_id": item.substitution_id,
                "equation_id": item.equation_id,
                "expression": item.expression,
                "output_id": item.output_id,
                "fact_ids": list(item.fact_ids),
                "input_output_ids": list(item.input_output_ids),
                "source": item.source,
            }
            for item in evidence.substitutions
        ]

    equations_by_id: dict[str, dict[str, Any]] = {}
    for equation in equations:
        equation_id = equation["equation_id"]
        if not equation_id or equation_id in equations_by_id:
            grounding_warnings.append("equation IDs must be nonempty and unique")
            grounding_valid = False
            continue
        equations_by_id[equation_id] = equation

    substitutions_by_id: dict[str, dict[str, Any]] = {}
    for substitution in substitutions:
        substitution_id = substitution["substitution_id"]
        if not substitution_id or substitution_id in substitutions_by_id:
            grounding_warnings.append("substitution IDs must be nonempty and unique")
            grounding_valid = False
            continue
        substitutions_by_id[substitution_id] = substitution

    known_fact_ids = set(explicit) | set(assumptions)
    declared_output_ids = {
        substitution["output_id"] for substitution in substitutions if substitution["output_id"]
    }
    if evidence is not None:
        declared_output_ids.update(link.output_id for link in evidence.outputs if link.output_id)

    referenced_fact_ids: set[str] = set()
    used_equation_ids: set[str] = set()
    for equation in equations_by_id.values():
        referenced_fact_ids.update(equation["fact_ids"])
        if not _looks_like_equation(equation["expression"]):
            grounding_warnings.append(f"equation {equation['equation_id']} is not an actual equation")
            grounding_valid = False
        if (
            equation["source"] not in _ALLOWED_EQUATION_SOURCES
            or equation["provenance"] not in _ALLOWED_EQUATION_PROVENANCE
        ):
            grounding_warnings.append(f"equation {equation['equation_id']} uses unapproved source or provenance")
            grounding_valid = False
        if not equation["fact_ids"] and not equation["input_output_ids"]:
            grounding_warnings.append(f"equation {equation['equation_id']} has no input links")
            grounding_valid = False
        if set(equation["fact_ids"]) - known_fact_ids:
            grounding_warnings.append(f"equation {equation['equation_id']} references an unknown fact")
            grounding_valid = False
        if set(equation["input_output_ids"]) - declared_output_ids:
            grounding_warnings.append(f"equation {equation['equation_id']} references an unknown derived output")
            grounding_valid = False
        if set(equation["output_ids"]) - declared_output_ids:
            grounding_warnings.append(f"equation {equation['equation_id']} declares an unknown output")
            grounding_valid = False

    for substitution in substitutions_by_id.values():
        referenced_fact_ids.update(substitution["fact_ids"])
        used_equation_ids.add(substitution["equation_id"])
        if substitution["equation_id"] not in equations_by_id:
            grounding_warnings.append(f"substitution {substitution['substitution_id']} references an unknown equation")
            grounding_valid = False
        if not _looks_like_equation(substitution["expression"]):
            grounding_warnings.append(f"substitution {substitution['substitution_id']} is not an actual substitution")
            grounding_valid = False
        if _NUMERIC_LITERAL.search(substitution["expression"]) is None:
            grounding_warnings.append(f"substitution {substitution['substitution_id']} has no substituted numeric value")
            grounding_valid = False
        if substitution["source"] not in _ALLOWED_SUBSTITUTION_SOURCES:
            grounding_warnings.append(f"substitution {substitution['substitution_id']} uses an unapproved source")
            grounding_valid = False
        if not substitution["fact_ids"] and not substitution["input_output_ids"]:
            grounding_warnings.append(f"substitution {substitution['substitution_id']} has no input links")
            grounding_valid = False
        if set(substitution["fact_ids"]) - known_fact_ids:
            grounding_warnings.append(f"substitution {substitution['substitution_id']} references an unknown fact")
            grounding_valid = False
        if set(substitution["input_output_ids"]) - declared_output_ids:
            grounding_warnings.append(f"substitution {substitution['substitution_id']} references an unknown derived output")
            grounding_valid = False

    if set(equations_by_id) - used_equation_ids:
        grounding_warnings.append("one or more structured equations are not linked to a substitution")
        grounding_valid = False

    structured_fact_ids = evidence_explicit_ids | evidence_assumption_ids
    if structured_fact_ids - referenced_fact_ids:
        grounding_warnings.append("one or more solver facts are not linked to an equation or substitution")
        grounding_valid = False
    branch_fact_ids = {
        fact_id
        for fact_id, fact in explicit.items()
        if fact["classification"] == "branch_condition"
    }
    if branch_fact_ids - referenced_fact_ids:
        grounding_warnings.append("a branch condition is not explicitly linked")
        grounding_valid = False

    candidate_summary, selected_candidate = _selected_candidate_summary(
        response,
        raw_selection_decision=raw_selection_decision,
        delivery_decision=delivery_decision,
    )
    raw_authority = raw_selection_decision or getattr(
        response, "selection_decision", None
    )
    raw_is_delivery_authority = raw_authority is delivery_decision
    candidate_summary["branch_fact_ids"] = sorted(branch_fact_ids)
    delivered = _delivered_answers(response)
    derivations: list[dict[str, Any]] = []
    outputs_valid = False
    if evidence is not None and delivered:
        derivations, outputs_valid = _match_output_links(
            delivered,
            evidence,
            selected_candidate,
            candidate_summary,
            delivery_decision,
            selected_solver,
            raw_is_delivery_authority,
            equations_by_id,
            substitutions_by_id,
            grounding_warnings,
        )
        if outputs_valid:
            outputs_valid = _top_level_answer_matches_primary(
                response, delivered, grounding_warnings
            )
            if not outputs_valid:
                derivations = []
        grounding_valid = grounding_valid and outputs_valid
    elif delivered:
        grounding_warnings.append("structured output derivation evidence is unavailable")
        grounding_valid = False
    elif evidence is not None and evidence.outputs:
        grounding_warnings.append("solver output evidence has no post-gate delivered answer")
        grounding_valid = False

    if evidence is not None and substitutions_by_id:
        reachable: set[str] = set()
        pending = [
            substitution_id
            for link in evidence.outputs
            for substitution_id in link.substitution_ids
            if substitution_id in substitutions_by_id
        ]
        producer_by_output = {
            substitution["output_id"]: substitution_id
            for substitution_id, substitution in substitutions_by_id.items()
        }
        while pending:
            substitution_id = pending.pop()
            if substitution_id in reachable:
                continue
            reachable.add(substitution_id)
            for input_output_id in substitutions_by_id[substitution_id]["input_output_ids"]:
                producer = producer_by_output.get(input_output_id)
                if producer is not None:
                    pending.append(producer)
        if set(substitutions_by_id) - reachable:
            grounding_warnings.append("one or more substitutions are not linked to a delivered output")
            grounding_valid = False

    validation = _validation_summary(response)
    external_warnings = list(getattr(getattr(response, "verification", None), "warnings", []) or [])
    validation_errors = list(getattr(getattr(response, "verification", None), "errors", []) or [])
    route_warnings = list(getattr(route_decision, "warnings", []) or [])
    evidence_warnings = list(evidence.warnings) if evidence is not None else []
    warnings = _warning_list(
        external_warnings,
        (f"validation error: {error}" for error in validation_errors),
        route_warnings,
        evidence_warnings,
        grounding_warnings,
    )

    terminal_status = _terminal_status(response, canonical, route_decision)
    if terminal_status is not None:
        status = terminal_status
    elif not delivered:
        status = "withheld"
    elif coordinate_critical or not outputs_valid:
        status = "withheld" if evidence is not None else "partial"
    elif not grounding_valid or not bool(getattr(response, "ok", False)) or not validation["passed"]:
        status = "partial"
    else:
        status = "fully_grounded"

    explicit_payload = [explicit[key] for key in sorted(explicit)]
    # Canonical assumptions are exposed only when the calculation actually
    # references them.  This prevents an unused generic assumption from becoming
    # student-facing explanatory evidence.
    assumption_payload = [
        assumptions[key]
        for key in sorted(assumptions)
        if key in referenced_fact_ids or key in evidence_assumption_ids
    ]
    equations_payload = [equations_by_id[key] for key in sorted(equations_by_id)]
    substitutions_payload = [
        substitutions_by_id[key] for key in sorted(substitutions_by_id)
    ]
    if status != "fully_grounded":
        derivations = []
        student_steps = _neutral_student_steps(status)
    else:
        student_steps = _full_student_steps(
            coordinate_frame,
            explicit_payload,
            assumption_payload,
            equations_payload,
            substitutions_payload,
            derivations,
            referenced_fact_ids,
        )
        internal_ids = {
            *explicit.keys(),
            *assumptions.keys(),
            *equations_by_id.keys(),
            *substitutions_by_id.keys(),
            *declared_output_ids,
            candidate_summary["selected_candidate_id"],
            coordinate_frame["frame_id"],
            selected_solver,
        }
        rendered_student_text = "\n".join(
            str(step.get(key) or "")
            for step in student_steps
            for key in ("title", "body", "math")
        )
        if any(
            internal_id and str(internal_id) in rendered_student_text
            for internal_id in internal_ids
        ):
            status = "withheld"
            derivations = []
            warnings = _warning_list(
                warnings,
                ("internal machine identifiers were withheld from student text",),
            )
            student_steps = _neutral_student_steps(status)

    return {
        "schema": TRACE_SCHEMA,
        "version": TRACE_VERSION,
        "status": status,
        "selected_solver": selected_solver,
        "route_reason": route_reason,
        "coordinate_frame": coordinate_frame,
        "explicit_facts": explicit_payload,
        "assumptions": assumption_payload,
        "equation_ids": [item["equation_id"] for item in equations_payload],
        "equations": equations_payload,
        "substitutions": substitutions_payload,
        "candidate_summary": candidate_summary,
        "validation_summary": validation,
        "answer_derivation": derivations,
        "warnings": warnings,
        "student_steps": student_steps,
    }
