from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


ONTOLOGY_VERSION = "textbook-ontology-v3-controlled"


class ParserSystemType(str, Enum):
    """Versioned parser ontology, deliberately broader than solver support."""

    banked_curve_no_friction = "banked_curve_no_friction"
    collision_1d = "collision_1d"
    constant_acceleration_1d = "constant_acceleration_1d"
    constant_force_work = "constant_force_work"
    coriolis_relative_motion = "coriolis_relative_motion"
    fixed_axis_rotation = "fixed_axis_rotation"
    flat_curve_friction = "flat_curve_friction"
    horizontal_friction_force = "horizontal_friction_force"
    impulse_momentum = "impulse_momentum"
    instant_center_velocity = "instant_center_velocity"
    massive_pulley_atwood = "massive_pulley_atwood"
    particle_on_incline = "particle_on_incline"
    plane_rigid_body_acceleration = "plane_rigid_body_acceleration"
    plane_rigid_body_velocity = "plane_rigid_body_velocity"
    polar_kinematics = "polar_kinematics"
    projectile_motion = "projectile_motion"
    pulley_atwood = "pulley_atwood"
    pulley_incline_hanging = "pulley_incline_hanging"
    pulley_table_hanging = "pulley_table_hanging"
    pure_rolling_energy = "pure_rolling_energy"
    relative_acceleration_translation = "relative_acceleration_translation"
    rolling_energy_general = "rolling_energy_general"
    single_particle_newton = "single_particle_newton"
    slot_pin_relative_motion = "slot_pin_relative_motion"
    spring_energy = "spring_energy"
    spring_mass_vibration = "spring_mass_vibration"
    vertical_circle = "vertical_circle"
    work_energy_speed = "work_energy_speed"

    # Parser-recognized structures that intentionally have no deterministic
    # textbook-safe solver capability.
    nonlinear_turbulent_flow = "nonlinear_turbulent_flow"
    unsupported_other = "unsupported_other"
    other = "other"


class ExplicitSemanticKey(str, Enum):
    acceleration = "acceleration"
    angle = "angle"
    angular_acceleration = "angular_acceleration"
    angular_velocity = "angular_velocity"
    background_height = "background_height"
    coefficient_of_friction = "coefficient_of_friction"
    displacement = "displacement"
    distance = "distance"
    duration = "duration"
    energy = "energy"
    final_velocity = "final_velocity"
    force = "force"
    frequency = "frequency"
    height = "height"
    impulse = "impulse"
    initial_velocity = "initial_velocity"
    mass = "mass"
    mass_1 = "mass_1"
    mass_2 = "mass_2"
    moment_of_inertia = "moment_of_inertia"
    period = "period"
    radius = "radius"
    restitution_coefficient = "restitution_coefficient"
    spring_constant = "spring_constant"
    time = "time"
    torque = "torque"
    velocity = "velocity"
    velocity_after = "velocity_after"
    velocity_before = "velocity_before"
    work = "work"


@dataclass(frozen=True)
class SemanticQuantitySpec:
    canonical_symbol: str
    dimensions: frozenset[str]


_SPECS = {
    ExplicitSemanticKey.acceleration: SemanticQuantitySpec("a", frozenset({"acceleration"})),
    ExplicitSemanticKey.angle: SemanticQuantitySpec("theta", frozenset({"angle"})),
    ExplicitSemanticKey.angular_acceleration: SemanticQuantitySpec("alpha", frozenset({"angular_acceleration"})),
    ExplicitSemanticKey.angular_velocity: SemanticQuantitySpec("omega", frozenset({"angular_velocity"})),
    ExplicitSemanticKey.background_height: SemanticQuantitySpec("h_background", frozenset({"length"})),
    ExplicitSemanticKey.coefficient_of_friction: SemanticQuantitySpec("mu", frozenset({"dimensionless"})),
    ExplicitSemanticKey.displacement: SemanticQuantitySpec("s", frozenset({"length"})),
    ExplicitSemanticKey.distance: SemanticQuantitySpec("s", frozenset({"length"})),
    ExplicitSemanticKey.duration: SemanticQuantitySpec("t", frozenset({"time"})),
    ExplicitSemanticKey.energy: SemanticQuantitySpec("E", frozenset({"energy", "energy_or_torque"})),
    ExplicitSemanticKey.final_velocity: SemanticQuantitySpec("vf", frozenset({"velocity"})),
    ExplicitSemanticKey.force: SemanticQuantitySpec("F", frozenset({"force"})),
    ExplicitSemanticKey.frequency: SemanticQuantitySpec("f", frozenset({"frequency"})),
    ExplicitSemanticKey.height: SemanticQuantitySpec("h", frozenset({"length"})),
    ExplicitSemanticKey.impulse: SemanticQuantitySpec("J", frozenset({"impulse"})),
    ExplicitSemanticKey.initial_velocity: SemanticQuantitySpec("v0", frozenset({"velocity"})),
    ExplicitSemanticKey.mass: SemanticQuantitySpec("m", frozenset({"mass"})),
    ExplicitSemanticKey.mass_1: SemanticQuantitySpec("m1", frozenset({"mass"})),
    ExplicitSemanticKey.mass_2: SemanticQuantitySpec("m2", frozenset({"mass"})),
    ExplicitSemanticKey.moment_of_inertia: SemanticQuantitySpec("I", frozenset({"moment_of_inertia"})),
    ExplicitSemanticKey.period: SemanticQuantitySpec("T", frozenset({"time"})),
    ExplicitSemanticKey.radius: SemanticQuantitySpec("R", frozenset({"length"})),
    ExplicitSemanticKey.restitution_coefficient: SemanticQuantitySpec("e", frozenset({"dimensionless"})),
    ExplicitSemanticKey.spring_constant: SemanticQuantitySpec("k", frozenset({"spring_constant"})),
    ExplicitSemanticKey.time: SemanticQuantitySpec("t", frozenset({"time"})),
    ExplicitSemanticKey.torque: SemanticQuantitySpec("tau", frozenset({"energy_or_torque"})),
    ExplicitSemanticKey.velocity: SemanticQuantitySpec("v", frozenset({"velocity"})),
    ExplicitSemanticKey.velocity_after: SemanticQuantitySpec("v", frozenset({"velocity"})),
    ExplicitSemanticKey.velocity_before: SemanticQuantitySpec("v", frozenset({"velocity"})),
    ExplicitSemanticKey.work: SemanticQuantitySpec("W", frozenset({"energy", "energy_or_torque"})),
}

SEMANTIC_QUANTITY_SPECS = MappingProxyType(_SPECS)
SEMANTIC_TO_CANONICAL_SYMBOL = MappingProxyType(
    {key.value: spec.canonical_symbol for key, spec in _SPECS.items()}
)
SEMANTIC_DIMENSIONS = MappingProxyType(
    {key.value: spec.dimensions for key, spec in _SPECS.items()}
)

PARSER_SYSTEM_TYPE_ONTOLOGY = frozenset(item.value for item in ParserSystemType)
SOLVER_CAPABILITY_SYSTEM_TYPES = frozenset(
    {
        "banked_curve_no_friction",
        "collision_1d",
        "constant_acceleration_1d",
        "constant_force_work",
        "coriolis_relative_motion",
        "fixed_axis_rotation",
        "flat_curve_friction",
        "horizontal_friction_force",
        "impulse_momentum",
        "instant_center_velocity",
        "massive_pulley_atwood",
        "particle_on_incline",
        "plane_rigid_body_acceleration",
        "plane_rigid_body_velocity",
        "polar_kinematics",
        "projectile_motion",
        "pulley_atwood",
        "pulley_incline_hanging",
        "pulley_table_hanging",
        "pure_rolling_energy",
        "relative_acceleration_translation",
        "rolling_energy_general",
        "single_particle_newton",
        "slot_pin_relative_motion",
        "spring_energy",
        "spring_mass_vibration",
        "vertical_circle",
        "work_energy_speed",
    }
)
TEXTBOOK_PARSER_SAFE_FAMILIES = frozenset({"constant_acceleration_1d"})


def canonical_symbol(semantic_key: str | ExplicitSemanticKey) -> str | None:
    value = semantic_key.value if isinstance(semantic_key, ExplicitSemanticKey) else semantic_key
    return SEMANTIC_TO_CANONICAL_SYMBOL.get(value)


def semantic_dimensions(semantic_key: str | ExplicitSemanticKey) -> frozenset[str] | None:
    value = semantic_key.value if isinstance(semantic_key, ExplicitSemanticKey) else semantic_key
    return SEMANTIC_DIMENSIONS.get(value)


__all__ = [
    "ONTOLOGY_VERSION",
    "ExplicitSemanticKey",
    "PARSER_SYSTEM_TYPE_ONTOLOGY",
    "ParserSystemType",
    "SEMANTIC_DIMENSIONS",
    "SEMANTIC_QUANTITY_SPECS",
    "SEMANTIC_TO_CANONICAL_SYMBOL",
    "SOLVER_CAPABILITY_SYSTEM_TYPES",
    "TEXTBOOK_PARSER_SAFE_FAMILIES",
    "canonical_symbol",
    "semantic_dimensions",
]
