from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
import json
import math

from engine.mechanics.contracts import (
    AxisName,
    EntityPrimitive,
    GeometryRelationKind,
    InteractionKind,
    PointRole,
    QuantityComponent,
    QuantityRole,
    QuantityShape,
    ReferenceFrameType,
    StateKind,
    StateValue,
)
from engine.mechanics.laws.base import (
    BoundQuantity,
    InitialConditionBinding,
    LawContext,
    LawEmission,
    LawRule,
    emission_for,
)
from engine.mechanics.math_ast import (
    Add,
    Derivative,
    DimensionVector,
    Divide,
    Dot,
    Equality,
    Inequality,
    InequalityRelation,
    LiteralNode,
    Multiply,
    Negate,
    Power,
    Subtract,
)


def _rule(
    law_id: str,
    category: str,
    roles: tuple[QuantityRole, ...],
    *,
    interactions: tuple[str, ...] = (),
    assumptions: tuple[str, ...] = (),
    generated: tuple[QuantityRole, ...] = (),
    cost: int = 10,
    hooks: tuple[str, ...] = (),
) -> LawRule:
    return LawRule(
        law_id=law_id,
        category=category,
        required_roles=roles,
        required_interactions=interactions,
        approved_assumption_kinds=assumptions,
        generated_roles=generated,
        complexity_cost=cost,
        verification_hooks=hooks,
    )


CORE_LAW_CATALOG: tuple[LawRule, ...] = (
    _rule("particle_position_derivative", "kinematics", (QuantityRole.position, QuantityRole.velocity, QuantityRole.time), cost=4, hooks=("derivative_residual",)),
    _rule("particle_velocity_derivative", "kinematics", (QuantityRole.velocity, QuantityRole.acceleration, QuantityRole.time), cost=4, hooks=("derivative_residual",)),
    _rule("particle_constant_velocity", "kinematics", (QuantityRole.displacement, QuantityRole.velocity, QuantityRole.duration), assumptions=("constant_velocity",), cost=3, hooks=("endpoint_residual",)),
    _rule("particle_constant_acceleration_velocity", "kinematics", (QuantityRole.velocity, QuantityRole.acceleration, QuantityRole.duration), assumptions=("constant_acceleration",), cost=4, hooks=("endpoint_residual",)),
    _rule("particle_constant_acceleration_position", "kinematics", (QuantityRole.displacement, QuantityRole.velocity, QuantityRole.acceleration, QuantityRole.duration), assumptions=("constant_acceleration",), cost=4, hooks=("endpoint_residual",)),
    _rule("particle_chain_acceleration", "kinematics", (QuantityRole.position, QuantityRole.velocity, QuantityRole.acceleration), cost=5, hooks=("derivative_residual",)),
    _rule("particle_normal_acceleration", "kinematics", (QuantityRole.speed, QuantityRole.radius, QuantityRole.acceleration), cost=3, hooks=("kinematic_residual",)),
    _rule("particle_newton_second", "newton_second_law", (QuantityRole.mass, QuantityRole.force, QuantityRole.acceleration), generated=(QuantityRole.acceleration,), cost=5, hooks=("force_balance",)),
    _rule("particle_weight", "newton_second_law", (QuantityRole.mass, QuantityRole.gravity, QuantityRole.force), interactions=(InteractionKind.gravity.value,), cost=3, hooks=("force_dimension",)),
    _rule("incline_gravity_tangent_projection", "newton_second_law", (QuantityRole.mass, QuantityRole.gravity, QuantityRole.angle, QuantityRole.force), interactions=(InteractionKind.gravity.value, InteractionKind.contact.value), cost=3, hooks=("force_dimension", "direction_residual", "contact_validity")),
    _rule("incline_gravity_normal_projection", "newton_second_law", (QuantityRole.mass, QuantityRole.gravity, QuantityRole.angle, QuantityRole.force), interactions=(InteractionKind.gravity.value, InteractionKind.contact.value), cost=3, hooks=("force_dimension", "direction_residual", "contact_validity")),
    _rule("contact_friction_bound", "newton_second_law", (QuantityRole.coefficient_friction, QuantityRole.force), interactions=(InteractionKind.contact.value,), cost=4, hooks=("friction_regime",)),
    _rule("contact_normal_bound", "newton_second_law", (QuantityRole.force,), interactions=(InteractionKind.contact.value,), cost=2, hooks=("contact_validity",)),
    _rule("fixed_contact_no_penetration", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.contact.value,), cost=2, hooks=("contact_validity", "constraint_residual")),
    _rule("incline_sticking_static_acceleration", "constraint", (QuantityRole.acceleration, QuantityRole.force, QuantityRole.coefficient_friction), interactions=(InteractionKind.contact.value,), cost=2, hooks=("friction_regime", "constraint_residual")),
    _rule("contact_sticking_static_acceleration", "constraint", (QuantityRole.acceleration, QuantityRole.force, QuantityRole.coefficient_friction), interactions=(InteractionKind.contact.value,), cost=2, hooks=("friction_regime", "constraint_residual")),
    _rule("contact_sliding_friction", "newton_second_law", (QuantityRole.coefficient_friction, QuantityRole.force), interactions=(InteractionKind.contact.value,), cost=4, hooks=("friction_regime", "direction_residual")),
    _rule("spring_force", "newton_second_law", (QuantityRole.stiffness, QuantityRole.displacement, QuantityRole.force), interactions=(InteractionKind.spring.value,), cost=3, hooks=("constitutive_residual",)),
    _rule("damper_force", "vibration", (QuantityRole.damping, QuantityRole.velocity, QuantityRole.force), interactions=(InteractionKind.damping.value,), cost=3, hooks=("constitutive_residual",)),
    _rule("force_work", "work_energy", (QuantityRole.force, QuantityRole.displacement, QuantityRole.work), cost=4, hooks=("energy_residual",)),
    _rule("particle_work_energy", "work_energy", (QuantityRole.mass, QuantityRole.velocity, QuantityRole.work), cost=4, hooks=("energy_residual",)),
    _rule("mechanical_power", "work_energy", (QuantityRole.force, QuantityRole.velocity, QuantityRole.power), cost=3, hooks=("power_residual",)),
    _rule("average_power", "work_energy", (QuantityRole.work, QuantityRole.duration, QuantityRole.power), cost=3, hooks=("power_residual",)),
    _rule("kinetic_energy", "work_energy", (QuantityRole.mass, QuantityRole.velocity, QuantityRole.energy), cost=3, hooks=("energy_residual",)),
    _rule("gravity_potential", "work_energy", (QuantityRole.mass, QuantityRole.gravity, QuantityRole.height, QuantityRole.energy), interactions=(InteractionKind.gravity.value,), cost=3, hooks=("energy_residual",)),
    _rule("spring_potential", "work_energy", (QuantityRole.stiffness, QuantityRole.displacement, QuantityRole.energy), interactions=(InteractionKind.spring.value,), cost=3, hooks=("energy_residual",)),
    _rule("linear_momentum", "impulse_momentum", (QuantityRole.mass, QuantityRole.velocity, QuantityRole.momentum), cost=3, hooks=("momentum_residual",)),
    _rule("linear_impulse", "impulse_momentum", (QuantityRole.force, QuantityRole.duration, QuantityRole.impulse), cost=4, hooks=("impulse_residual",)),
    _rule("linear_impulse_momentum", "impulse_momentum", (QuantityRole.mass, QuantityRole.velocity, QuantityRole.impulse), cost=4, hooks=("momentum_residual",)),
    _rule("system_momentum_conservation", "impulse_momentum", (QuantityRole.mass, QuantityRole.velocity), assumptions=("external_impulse_negligible",), cost=6, hooks=("momentum_residual",)),
    _rule("direct_restitution", "impulse_momentum", (QuantityRole.velocity, QuantityRole.coefficient_restitution), interactions=(InteractionKind.collision.value,), cost=5, hooks=("impact_residual",)),
    _rule("rope_massless_tension", "constraint", (QuantityRole.force,), interactions=(InteractionKind.rope_tension.value,), assumptions=("massless_rope",), cost=2, hooks=("constraint_residual",)),
    _rule("rope_attachment_side_tension_transfer", "constraint", (QuantityRole.force,), interactions=(InteractionKind.rope_tension.value,), assumptions=("massless_rope",), cost=3, hooks=("constraint_residual", "topology_residual")),
    _rule("rope_attachment_tension_transfer", "constraint", (QuantityRole.force,), interactions=(InteractionKind.rope_tension.value,), assumptions=("massless_rope", "ideal_massless_frictionless_pulley"), cost=3, hooks=("constraint_residual", "topology_residual")),
    _rule("rope_attachment_acceleration_transfer", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope", "fixed_pulley"), cost=3, hooks=("constraint_residual", "topology_residual")),
    _rule("rope_inextensible_motion", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope",), cost=2, hooks=("constraint_residual",)),
    _rule("rope_fixed_pulley_motion", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope", "fixed_pulley"), cost=3, hooks=("topology_residual",)),
    _rule("rope_moving_pulley_motion", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope",), cost=4, hooks=("topology_residual",)),
    _rule("incline_hanging_sliding_direction_consistency", "constraint", (QuantityRole.acceleration, QuantityRole.velocity), interactions=(InteractionKind.contact.value,), assumptions=("acceleration_not_opposite_motion",), cost=2, hooks=("direction_residual", "friction_regime")),
    _rule("pulley_no_slip_acceleration", "constraint", (QuantityRole.acceleration, QuantityRole.radius, QuantityRole.angular_acceleration), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope", "fixed_pulley"), cost=3, hooks=("constraint_residual", "topology_residual")),
    _rule("pulley_newton_euler", "newton_second_law", (QuantityRole.force, QuantityRole.radius, QuantityRole.moment_of_inertia, QuantityRole.angular_acceleration), interactions=(InteractionKind.rope_tension.value,), cost=5, hooks=("moment_balance",)),
    _rule("rolling_no_slip", "constraint", (QuantityRole.velocity, QuantityRole.angular_velocity, QuantityRole.radius), cost=3, hooks=("constraint_residual",)),
    _rule("gear_pitch_velocity", "constraint", (QuantityRole.angular_velocity, QuantityRole.radius), interactions=(InteractionKind.gear_contact.value,), cost=3, hooks=("constraint_residual",)),
    _rule("state_at_rest", "constraint", (QuantityRole.velocity,), cost=1, hooks=("boundary_residual",)),
    _rule("angular_position_derivative", "rigid_body_kinematics", (QuantityRole.angular_position, QuantityRole.angular_velocity, QuantityRole.time), cost=4, hooks=("derivative_residual",)),
    _rule("angular_velocity_derivative", "rigid_body_kinematics", (QuantityRole.angular_velocity, QuantityRole.angular_acceleration, QuantityRole.time), cost=4, hooks=("derivative_residual",)),
    _rule("fixed_axis_speed", "rigid_body_kinematics", (QuantityRole.angular_velocity, QuantityRole.radius, QuantityRole.speed), cost=3, hooks=("kinematic_residual",)),
    _rule("rigid_point_velocity", "rigid_body_kinematics", (QuantityRole.velocity, QuantityRole.angular_velocity, QuantityRole.radius), cost=5, hooks=("point_kinematic_residual",)),
    _rule("rigid_point_tangential_acceleration", "rigid_body_kinematics", (QuantityRole.acceleration, QuantityRole.angular_acceleration, QuantityRole.radius), cost=5, hooks=("point_kinematic_residual",)),
    _rule("rigid_point_normal_acceleration", "rigid_body_kinematics", (QuantityRole.acceleration, QuantityRole.angular_velocity, QuantityRole.radius), cost=5, hooks=("point_kinematic_residual",)),
    _rule("rigid_newton_euler", "newton_second_law", (QuantityRole.moment_of_inertia, QuantityRole.angular_acceleration, QuantityRole.moment), generated=(QuantityRole.angular_acceleration,), cost=5, hooks=("moment_balance",)),
    _rule("rigid_kinetic_energy", "work_energy", (QuantityRole.mass, QuantityRole.velocity, QuantityRole.moment_of_inertia, QuantityRole.angular_velocity, QuantityRole.energy), assumptions=("kinetic_energy",), cost=5, hooks=("energy_residual",)),
    _rule("rigid_angular_momentum", "impulse_momentum", (QuantityRole.moment_of_inertia, QuantityRole.angular_velocity, QuantityRole.angular_momentum), cost=4, hooks=("momentum_residual",)),
    _rule("rigid_angular_impulse_momentum", "impulse_momentum", (QuantityRole.moment_of_inertia, QuantityRole.angular_velocity, QuantityRole.impulse), cost=5, hooks=("angular_impulse_residual",)),
    _rule("linear_vibration", "vibration", (QuantityRole.mass, QuantityRole.stiffness, QuantityRole.displacement, QuantityRole.time), cost=7, hooks=("ode_residual", "initial_conditions")),
    _rule("vibration_natural_frequency", "vibration", (QuantityRole.mass, QuantityRole.stiffness, QuantityRole.frequency), cost=3, hooks=("frequency_residual",)),
)

_RULES = {rule.law_id: rule for rule in CORE_LAW_CATALOG}
_GLOBAL_ROLES = frozenset(
    {
        QuantityRole.mass,
        QuantityRole.gravity,
        QuantityRole.stiffness,
        QuantityRole.damping,
        QuantityRole.coefficient_friction,
        QuantityRole.coefficient_restitution,
        QuantityRole.radius,
        QuantityRole.length,
        QuantityRole.moment_of_inertia,
    }
)
_COMPONENT_ROLES = frozenset(
    {
        QuantityRole.position,
        QuantityRole.displacement,
        QuantityRole.velocity,
        QuantityRole.speed,
        QuantityRole.acceleration,
        QuantityRole.force,
        QuantityRole.moment,
        QuantityRole.torque,
        QuantityRole.momentum,
        QuantityRole.angular_momentum,
        QuantityRole.impulse,
        QuantityRole.angular_position,
        QuantityRole.angular_velocity,
        QuantityRole.angular_acceleration,
        QuantityRole.generalized_coordinate,
        QuantityRole.generalized_speed,
    }
)


def core_law_catalog() -> tuple[LawRule, ...]:
    return CORE_LAW_CATALOG


def _by_role(context: LawContext, role: QuantityRole) -> tuple[BoundQuantity, ...]:
    return tuple(sorted((q for q in context.quantities if q.role is role), key=lambda q: q.stable_key))


def _component_compatible(anchor: BoundQuantity, other: BoundQuantity) -> bool:
    if anchor.role not in _COMPONENT_ROLES or other.role not in _COMPONENT_ROLES:
        return True
    if anchor.component is not other.component:
        return False
    return not (
        anchor.direction_key is not None
        and other.direction_key is not None
        and anchor.direction_key != other.direction_key
    )


def _scope_compatible(anchor: BoundQuantity, other: BoundQuantity) -> bool:
    if anchor.subject_id != other.subject_id and other.role not in {QuantityRole.gravity}:
        return False
    for left, right in (
        (anchor.frame_id, other.frame_id),
        (anchor.interval_id, other.interval_id),
        (anchor.event_id, other.event_id),
    ):
        if left == right:
            continue
        if other.role in _GLOBAL_ROLES and right is None:
            continue
        if anchor.role in _GLOBAL_ROLES and left is None:
            continue
        return False
    return _component_compatible(anchor, other)


def _cross_subject_scope_compatible(anchor: BoundQuantity, other: BoundQuantity) -> bool:
    return (
        anchor.frame_id == other.frame_id
        and anchor.interval_id == other.interval_id
        and anchor.event_id == other.event_id
        and anchor.shape is other.shape
        and _component_compatible(anchor, other)
    )


def _shape_compatible(*quantities: BoundQuantity) -> bool:
    shaped = [q.shape for q in quantities if q.role not in _GLOBAL_ROLES]
    return not shaped or all(item is shaped[0] for item in shaped)


def _scope_compatible_without_component(
    anchor: BoundQuantity,
    other: BoundQuantity,
) -> bool:
    if anchor.subject_id != other.subject_id and other.role not in {QuantityRole.gravity}:
        return False
    for left, right in (
        (anchor.frame_id, other.frame_id),
        (anchor.interval_id, other.interval_id),
        (anchor.event_id, other.event_id),
    ):
        if left == right:
            continue
        if other.role in _GLOBAL_ROLES and right is None:
            continue
        if anchor.role in _GLOBAL_ROLES and left is None:
            continue
        return False
    return True


def _is_full_translational_speed(
    quantity: BoundQuantity,
    frame_types: dict[str, ReferenceFrameType],
) -> bool:
    if quantity.role is QuantityRole.speed:
        return (
            quantity.shape is QuantityShape.scalar
            and quantity.component in {
                QuantityComponent.magnitude,
                QuantityComponent.unspecified,
            }
        )
    if quantity.role is not QuantityRole.velocity:
        return False
    if quantity.shape is QuantityShape.vector:
        return True
    return (
        quantity.shape is QuantityShape.scalar
        and frame_types.get(quantity.frame_id) is ReferenceFrameType.cartesian_1d
        and quantity.component in {
            QuantityComponent.x,
            QuantityComponent.unspecified,
        }
    )


def _signed(quantity: BoundQuantity):
    if quantity.direction_sign < 0:
        return Negate(operand=quantity.expression, dimension=quantity.dimension)
    return quantity.expression


def _sum_terms(quantities: Iterable[BoundQuantity]):
    ordered = tuple(quantities)
    terms = tuple(_signed(q) for q in ordered)
    if len(terms) == 1:
        return terms[0]
    return Add(terms=terms, dimension=ordered[0].dimension)


def _emit(
    context: LawContext,
    rule_id: str,
    expression,
    quantities: tuple[BoundQuantity, ...],
    *,
    assumption_ids: tuple[str, ...] = (),
    constraint_ids: tuple[str, ...] = (),
    extra_entity_ids: tuple[str, ...] = (),
    extra_evidence_ids: tuple[str, ...] = (),
    initial_conditions: tuple[InitialConditionBinding, ...] = (),
) -> LawEmission:
    rule = _RULES[rule_id]
    emission = emission_for(
        rule,
        expression,
        quantities,
        assumption_ids=assumption_ids,
        constraint_ids=constraint_ids,
        extra_entity_ids=extra_entity_ids,
        initial_conditions=initial_conditions,
        hint_priority=rule.category in context.hinted_principles,
    )
    if not extra_evidence_ids:
        return emission
    return replace(
        emission,
        source_evidence_ids=tuple(
            sorted(set(emission.source_evidence_ids) | set(extra_evidence_ids))
        ),
    )


def _derivative_emissions(
    context: LawContext,
    source_role: QuantityRole,
    target_role: QuantityRole,
    rule_id: str,
) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    times = _by_role(context, QuantityRole.time)
    global_time_subjects = {
        entity.entity_id
        for entity in context.entities
        if entity.primitive in {EntityPrimitive.environment, EntityPrimitive.reference_frame}
    }
    for target in _by_role(context, target_role):
        for source in _by_role(context, source_role):
            if not _scope_compatible(target, source) or not _shape_compatible(target, source):
                continue
            for time in times:
                if time.symbol_id is None or time.shape is not QuantityShape.scalar:
                    continue
                if time.subject_id != target.subject_id and time.subject_id not in global_time_subjects:
                    continue
                derivative = Derivative(
                    expression=source.expression,
                    wrt_symbol_id=time.symbol_id,
                    dimension=target.dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        rule_id,
                        Equality(left=target.expression, right=derivative),
                        (target, source, time),
                    )
                )
    return emitted


def _constant_velocity_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    for displacement in _by_role(context, QuantityRole.displacement):
        assumptions = context.approved_assumptions(
            "constant_velocity", displacement.subject_id, displacement.interval_id
        )
        if not assumptions:
            continue
        for velocity in _by_role(context, QuantityRole.velocity):
            if not _scope_compatible(displacement, velocity) or not _shape_compatible(displacement, velocity):
                continue
            for duration in _by_role(context, QuantityRole.duration):
                if not _scope_compatible(displacement, duration) or duration.shape is not QuantityShape.scalar:
                    continue
                product = Multiply(
                    factors=(velocity.expression, duration.expression),
                    dimension=displacement.dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "particle_constant_velocity",
                        Equality(left=displacement.expression, right=product),
                        (displacement, velocity, duration),
                        assumption_ids=assumptions,
                    )
                )
    return emitted


def _constant_acceleration_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    half = LiteralNode(value=0.5)
    for interval in context.motion_intervals:
        if interval.start_event_id is None or interval.end_event_id is None:
            continue
        for subject_id in interval.subject_ids:
            assumptions = context.approved_assumptions(
                "constant_acceleration", subject_id, interval.interval_id
            )
            if not assumptions:
                continue
            starts = tuple(
                q
                for q in _by_role(context, QuantityRole.velocity)
                if q.subject_id == subject_id
                and q.interval_id == interval.interval_id
                and q.event_id == interval.start_event_id
            )
            ends = tuple(
                q
                for q in _by_role(context, QuantityRole.velocity)
                if q.subject_id == subject_id
                and q.interval_id == interval.interval_id
                and q.event_id == interval.end_event_id
            )
            accelerations = tuple(
                q
                for q in _by_role(context, QuantityRole.acceleration)
                if q.subject_id == subject_id
                and q.interval_id == interval.interval_id
                and q.event_id is None
            )
            durations = tuple(
                q
                for q in _by_role(context, QuantityRole.duration)
                if q.subject_id == subject_id
                and q.interval_id == interval.interval_id
                and q.shape is QuantityShape.scalar
            )
            if not (len(starts) == len(ends) == len(accelerations) == len(durations) == 1):
                continue
            start, end, acceleration, duration = starts[0], ends[0], accelerations[0], durations[0]
            if not _shape_compatible(start, end, acceleration) or not all(
                _component_compatible(start, item) for item in (end, acceleration)
            ) or not (
                start.frame_id == end.frame_id == acceleration.frame_id
                and start.point_id == end.point_id == acceleration.point_id
            ):
                continue
            velocity_change = Add(
                terms=(
                    start.expression,
                    Multiply(
                        factors=(acceleration.expression, duration.expression),
                        dimension=end.dimension,
                    ),
                ),
                dimension=end.dimension,
            )
            emitted.append(
                _emit(
                    context,
                    "particle_constant_acceleration_velocity",
                    Equality(left=end.expression, right=velocity_change),
                    (start, end, acceleration, duration),
                    assumption_ids=assumptions,
                )
            )
            displacements = tuple(
                q
                for q in _by_role(context, QuantityRole.displacement)
                if q.subject_id == subject_id
                and q.interval_id == interval.interval_id
                and q.event_id is None
                and q.shape is start.shape
            )
            if len(displacements) == 1:
                displacement = displacements[0]
                if not (
                    displacement.frame_id == start.frame_id == acceleration.frame_id
                    and displacement.point_id == start.point_id == acceleration.point_id
                    and _component_compatible(displacement, start)
                    and _component_compatible(displacement, acceleration)
                ):
                    continue
                duration_squared = Power(
                    base=duration.expression,
                    exponent=LiteralNode(value=2.0),
                )
                position_change = Add(
                    terms=(
                        Multiply(
                            factors=(start.expression, duration.expression),
                            dimension=displacement.dimension,
                        ),
                        Multiply(
                            factors=(half, acceleration.expression, duration_squared),
                            dimension=displacement.dimension,
                        ),
                    ),
                    dimension=displacement.dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "particle_constant_acceleration_position",
                        Equality(left=displacement.expression, right=position_change),
                        (displacement, start, acceleration, duration),
                        assumption_ids=assumptions,
                    )
                )
    return emitted


def _chain_kinematics_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    for acceleration in _by_role(context, QuantityRole.acceleration):
        if acceleration.shape is not QuantityShape.scalar:
            continue
        for velocity in _by_role(context, QuantityRole.velocity):
            if velocity.shape is not QuantityShape.scalar or not _scope_compatible(acceleration, velocity):
                continue
            for position in _by_role(context, QuantityRole.position):
                if (
                    position.shape is not QuantityShape.scalar
                    or position.symbol_id is None
                    or not _scope_compatible(acceleration, position)
                ):
                    continue
                derivative = Derivative(
                    expression=velocity.expression,
                    wrt_symbol_id=position.symbol_id,
                )
                chain = Multiply(
                    factors=(velocity.expression, derivative),
                    dimension=acceleration.dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "particle_chain_acceleration",
                        Equality(left=acceleration.expression, right=chain),
                        (acceleration, velocity, position),
                    )
                )
    for acceleration in _by_role(context, QuantityRole.acceleration):
        if acceleration.component is not QuantityComponent.normal or acceleration.shape is not QuantityShape.scalar:
            continue
        speeds = tuple(
            q
            for q in _by_role(context, QuantityRole.speed)
            if q.shape is QuantityShape.scalar
            and q.component in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            and _scope_compatible_without_component(acceleration, q)
        )
        radii = tuple(
            q
            for q in _by_role(context, QuantityRole.radius)
            if q.shape is QuantityShape.scalar and _scope_compatible(acceleration, q)
        )
        if len(speeds) == len(radii) == 1:
            normal = Divide(
                numerator=Power(
                    base=speeds[0].expression,
                    exponent=LiteralNode(value=2.0),
                ),
                denominator=radii[0].expression,
                dimension=acceleration.dimension,
            )
            emitted.append(
                _emit(
                    context,
                    "particle_normal_acceleration",
                    Equality(left=acceleration.expression, right=normal),
                    (acceleration, speeds[0], radii[0]),
                )
            )
    return emitted


def _interaction_quantities(context: LawContext, interaction_id: str) -> tuple[BoundQuantity, ...]:
    interaction = next(item for item in context.interactions if item.interaction_id == interaction_id)
    ids = set(interaction.quantity_ids)
    return tuple(q for q in context.quantities if q.quantity_id in ids)


def _one(values):
    items = tuple(values)
    return items[0] if len(items) == 1 else None


def _axis_bound(
    quantity: BoundQuantity,
    frame_id: str,
    component: QuantityComponent,
    sign: int,
) -> bool:
    axis = (
        AxisName.tangent.value
        if component is QuantityComponent.tangential
        else component.value
    )
    try:
        direction = json.loads(quantity.direction_key or "")
    except (TypeError, ValueError):
        return False
    return (
        quantity.shape is QuantityShape.scalar
        and quantity.frame_id == frame_id
        and quantity.component is component
        and quantity.direction_bound
        and quantity.direction_sign == sign
        and direction == {"axis": axis, "frame_id": frame_id, "kind": "axis"}
    )


@dataclass(frozen=True)
class _FixedPulleyHorizontalContactLawProfile:
    rope_interaction_id: str
    table_id: str
    hanging_id: str
    surface_id: str
    rope_id: str
    pulley_id: str
    frame_id: str
    interval_id: str
    regime: str
    normal: BoundQuantity
    normal_acceleration: BoundQuantity
    table_acceleration: BoundQuantity
    hanging_acceleration: BoundQuantity
    table_tension: BoundQuantity
    hanging_tension: BoundQuantity
    friction: BoundQuantity | None
    coefficient: BoundQuantity | None
    carrier: BoundQuantity | None
    contact_state_ids: tuple[str, ...]

    @property
    def rope_tensions(self) -> tuple[BoundQuantity, BoundQuantity]:
        return (self.table_tension, self.hanging_tension)

    @property
    def rope_accelerations(self) -> tuple[BoundQuantity, BoundQuantity]:
        return (self.table_acceleration, self.hanging_acceleration)


def _fixed_pulley_horizontal_contact_profile(
    context: LawContext,
    rope_interaction_id: str | None = None,
    *,
    require_rope_authority: bool = True,
) -> _FixedPulleyHorizontalContactLawProfile | None:
    """Recognize one exact surface-contact, cross-axis fixed-pulley graph."""

    entities = {item.entity_id: item for item in context.entities}
    primitive_ids = {
        primitive: tuple(
            item.entity_id
            for item in context.entities
            if item.primitive is primitive
        )
        for primitive in (
            EntityPrimitive.particle,
            EntityPrimitive.surface,
            EntityPrimitive.rope,
            EntityPrimitive.pulley,
            EntityPrimitive.environment,
        )
    }
    if (
        len(context.entities) != 6
        or {key: len(value) for key, value in primitive_ids.items()}
        != {
            EntityPrimitive.particle: 2,
            EntityPrimitive.surface: 1,
            EntityPrimitive.rope: 1,
            EntityPrimitive.pulley: 1,
            EntityPrimitive.environment: 1,
        }
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in context.entities
        )
    ):
        return None
    particle_ids = set(primitive_ids[EntityPrimitive.particle])
    surface_id = primitive_ids[EntityPrimitive.surface][0]
    rope_id = primitive_ids[EntityPrimitive.rope][0]
    pulley_id = primitive_ids[EntityPrimitive.pulley][0]
    environment_id = primitive_ids[EntityPrimitive.environment][0]

    if len(context.reference_frames) != 1:
        return None
    frame = context.reference_frames[0]
    axis_signature = {
        (
            item.axis,
            getattr(item.direction, "kind", None),
            getattr(item.direction, "frame_id", None),
            getattr(item.direction, "axis", None),
            getattr(item.direction, "sign", None),
        )
        for item in frame.axes
    }
    if (
        frame.frame_type is not ReferenceFrameType.cartesian_2d
        or getattr(frame.origin, "kind", None) != "world"
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id is not None
        or frame.generalized_coordinate_symbol_ids
        or not frame.evidence_refs
        or len(frame.axes) != 2
        or axis_signature
        != {
            (AxisName.x, "axis", frame.frame_id, AxisName.x, 1),
            (AxisName.y, "axis", frame.frame_id, AxisName.y, 1),
        }
    ):
        return None

    if len(context.motion_intervals) != 1 or context.events:
        return None
    interval = context.motion_intervals[0]
    if (
        interval.frame_id != frame.frame_id
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or set(interval.subject_ids) != set(entities)
        or len(interval.subject_ids) != len(entities)
        or not interval.evidence_refs
    ):
        return None

    contacts = tuple(
        item for item in context.interactions if item.kind is InteractionKind.contact
    )
    rope_interactions = tuple(
        item
        for item in context.interactions
        if item.kind is InteractionKind.rope_tension
    )
    gravity_interactions = tuple(
        item for item in context.interactions if item.kind is InteractionKind.gravity
    )
    if (
        len(context.interactions) != 4
        or len(contacts) != 1
        or len(rope_interactions) != 1
        or len(gravity_interactions) != 2
    ):
        return None
    rope_interaction = rope_interactions[0]
    if (
        rope_interaction_id is not None
        and rope_interaction.interaction_id != rope_interaction_id
    ):
        return None
    contact = contacts[0]
    table_ids = set(contact.participant_ids) & particle_ids
    if (
        len(contact.participant_ids) != 2
        or len(set(contact.participant_ids)) != 2
        or surface_id not in contact.participant_ids
        or len(table_ids) != 1
        or len(contact.point_ids) != 1
        or contact.frame_id != frame.frame_id
        or contact.interval_id != interval.interval_id
        or contact.event_id is not None
        or not contact.evidence_refs
    ):
        return None
    table_id = next(iter(table_ids))
    hanging_id = next(iter(particle_ids - {table_id}))
    if (
        len(rope_interaction.participant_ids) != 4
        or len(set(rope_interaction.participant_ids)) != 4
        or set(rope_interaction.participant_ids)
        != particle_ids | {rope_id, pulley_id}
        or rope_interaction.point_ids
        or rope_interaction.frame_id != frame.frame_id
        or rope_interaction.interval_id != interval.interval_id
        or rope_interaction.event_id is not None
        or len(rope_interaction.quantity_ids) != 2
        or len(set(rope_interaction.quantity_ids)) != 2
        or not rope_interaction.evidence_refs
        or {next(iter(set(item.participant_ids) & particle_ids), None) for item in gravity_interactions}
        != particle_ids
        or any(
            len(item.participant_ids) != 2
            or len(set(item.participant_ids)) != 2
            or environment_id not in item.participant_ids
            or item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.point_ids
            or len(item.quantity_ids) != 3
            or len(set(item.quantity_ids)) != 3
            or not item.evidence_refs
            for item in gravity_interactions
        )
    ):
        return None

    if len(context.points) != 1:
        return None
    point = context.points[0]
    if (
        point.point_id != contact.point_ids[0]
        or point.role is not PointRole.contact
        or point.owner_entity_id != table_id
        or point.frame_id != frame.frame_id
        or not point.evidence_refs
    ):
        return None

    wraps = tuple(
        item for item in context.geometry if item.kind is GeometryRelationKind.wraps
    )
    attached = tuple(
        item for item in context.geometry if item.kind is GeometryRelationKind.attached
    )
    if (
        len(context.geometry) != 3
        or len(wraps) != 1
        or len(attached) != 2
        or any(
            item.interval_id != interval.interval_id
            or item.expression is not None
            or item.quantity_ids
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            for item in context.geometry
        )
        or set(wraps[0].participant_ids) != {rope_id, pulley_id}
        or len(wraps[0].participant_ids) != 2
        or {frozenset(item.participant_ids) for item in attached}
        != {frozenset((rope_id, item)) for item in particle_ids}
    ):
        return None

    states = context.state_conditions
    if any(
        item.interval_id != interval.interval_id
        or item.event_id is not None
        or item.expression is not None
        or not item.evidence_refs
        for item in states
    ):
        return None
    rope_states = tuple(
        item for item in states
        if item.subject_id == rope_id and item.kind is StateKind.rope
    )
    pulley_states = tuple(
        item for item in states
        if item.subject_id == pulley_id and item.kind is StateKind.motion
    )
    touching = tuple(
        item for item in states
        if item.subject_id == table_id and item.kind is StateKind.contact
    )
    surface_states = tuple(
        item for item in states
        if item.subject_id == surface_id and item.kind is StateKind.motion
    )
    friction_states = tuple(
        item for item in states
        if item.subject_id == table_id and item.kind is StateKind.friction
    )
    table_motion = tuple(
        item for item in states
        if item.subject_id == table_id and item.kind is StateKind.motion
    )
    if (
        len(rope_states) != 1
        or rope_states[0].state is not StateValue.taut
        or rope_states[0].quantity_ids
        or len(pulley_states) != 1
        or pulley_states[0].state is not StateValue.at_rest
        or pulley_states[0].quantity_ids
        or len(touching) != 1
        or touching[0].state is not StateValue.touching
        or len(surface_states) != 1
        or surface_states[0].state is not StateValue.at_rest
        or surface_states[0].quantity_ids
        or len(friction_states) != 1
        or friction_states[0].state
        not in {StateValue.inactive, StateValue.sticking, StateValue.sliding}
    ):
        return None
    friction_state = friction_states[0]
    regime = friction_state.state.value
    if (
        len(states) != (5 if regime == "inactive" else 6)
        or (regime == "inactive" and table_motion)
        or (regime != "inactive" and len(table_motion) != 1)
    ):
        return None

    required_assumptions = {
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("ideal_massless_frictionless_pulley", pulley_id),
        ("fixed_pulley", pulley_id),
    }
    approved_ids = {
        assumption_id
        for kind, subject_id in required_assumptions
        for assumption_id in context.approved_assumptions(
            kind, subject_id, interval.interval_id
        )
    }
    if (
        len(context.assumptions) != 4
        or {(item.kind, item.subject_id) for item in context.assumptions}
        != required_assumptions
        or any(
            item.interval_id != interval.interval_id
            or item.proposed_role is not None
            or item.proposed_value is not None
            or item.proposed_unit is not None
            or not item.evidence_refs
            for item in context.assumptions
        )
        or (
            require_rope_authority
            and {item.assumption_id for item in context.assumptions} != approved_ids
        )
    ):
        return None

    quantities = {item.quantity_id: item for item in context.quantities}
    if None in quantities:
        return None
    masses: dict[str, BoundQuantity] = {}
    weights: dict[str, BoundQuantity] = {}
    gravities: list[BoundQuantity] = []
    for interaction in gravity_interactions:
        body_id = next(iter(set(interaction.participant_ids) & particle_ids))
        linked = tuple(quantities.get(item) for item in interaction.quantity_ids)
        mass = tuple(
            item for item in linked
            if item is not None
            and item.role is QuantityRole.mass
            and item.subject_id == body_id
        )
        gravity = tuple(
            item for item in linked
            if item is not None
            and item.role is QuantityRole.gravity
            and item.subject_id == environment_id
        )
        weight = tuple(
            item for item in linked
            if item is not None
            and item.role is QuantityRole.force
            and item.subject_id == body_id
        )
        if not all(len(items) == 1 for items in (mass, gravity, weight)):
            return None
        masses[body_id] = mass[0]
        gravities.append(gravity[0])
        weights[body_id] = weight[0]
    if len({item.quantity_id for item in gravities}) != 1:
        return None
    gravity = gravities[0]

    def exact_known(item: BoundQuantity, *, positive: bool) -> bool:
        value = item.known_si_value
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and bool(item.evidence_ids)
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and item.component
            in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            and not item.direction_bound
            and type(value) is float
            and math.isfinite(value)
            and (value > 0.0 if positive else value >= 0.0)
        )

    if any(not exact_known(item, positive=True) for item in (*masses.values(), gravity)):
        return None

    def exact_unknown_axis(
        item: BoundQuantity,
        *,
        subject_id: str,
        point_id: str | None,
        component: QuantityComponent,
        sign: int | None,
    ) -> bool:
        observed_sign = item.direction_sign
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.known_si_value is None
            and bool(item.evidence_ids)
            and item.subject_id == subject_id
            and item.point_id == point_id
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component is component
            and observed_sign in {-1, 1}
            and (sign is None or observed_sign == sign)
            and _axis_bound(
                item,
                frame.frame_id,
                component,
                observed_sign,
            )
        )

    if any(
        not exact_unknown_axis(
            item,
            subject_id=body_id,
            point_id=None,
            component=QuantityComponent.y,
            sign=-1,
        )
        for body_id, item in weights.items()
    ):
        return None
    tensions = tuple(quantities.get(item) for item in rope_interaction.quantity_ids)
    if any(item is None for item in tensions):
        return None
    table_tensions = tuple(
        item for item in tensions
        if item.role is QuantityRole.force and item.subject_id == table_id
    )
    hanging_tensions = tuple(
        item for item in tensions
        if item.role is QuantityRole.force and item.subject_id == hanging_id
    )
    if len(table_tensions) != 1 or len(hanging_tensions) != 1:
        return None
    table_tension = table_tensions[0]
    hanging_tension = hanging_tensions[0]
    if (
        not exact_unknown_axis(
            table_tension,
            subject_id=table_id,
            point_id=None,
            component=QuantityComponent.x,
            sign=1,
        )
        or not exact_unknown_axis(
            hanging_tension,
            subject_id=hanging_id,
            point_id=None,
            component=QuantityComponent.y,
            sign=1,
        )
    ):
        return None

    linked_contact = tuple(quantities.get(item) for item in contact.quantity_ids)
    if any(item is None for item in linked_contact):
        return None
    normal_values = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.force
        and item.subject_id == table_id
        and item.component is QuantityComponent.y
        and item.direction_sign == 1
    )
    normal_accelerations = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.acceleration
        and item.subject_id == table_id
        and item.component is QuantityComponent.y
    )
    friction_values = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.force
        and item.subject_id == table_id
        and item.component is QuantityComponent.x
    )
    coefficients = tuple(
        item for item in linked_contact
        if item.role is QuantityRole.coefficient_friction
        and item.subject_id == table_id
    )
    accelerations = tuple(
        item for item in context.quantities
        if item.role is QuantityRole.acceleration
        and item.subject_id in particle_ids
    )
    table_x = tuple(
        item for item in accelerations
        if item.subject_id == table_id and item.component is QuantityComponent.x
    )
    table_y = tuple(
        item for item in accelerations
        if item.subject_id == table_id and item.component is QuantityComponent.y
    )
    hanging_y = tuple(
        item for item in accelerations
        if item.subject_id == hanging_id and item.component is QuantityComponent.y
    )
    if (
        len(normal_values) != 1
        or len(normal_accelerations) != 1
        or len(accelerations) != 3
        or len(table_x) != 1
        or len(table_y) != 1
        or len(hanging_y) != 1
    ):
        return None
    normal = normal_values[0]
    normal_acceleration = normal_accelerations[0]
    table_acceleration = table_x[0]
    hanging_acceleration = hanging_y[0]
    if (
        not exact_unknown_axis(
            normal,
            subject_id=table_id,
            point_id=point.point_id,
            component=QuantityComponent.y,
            sign=1,
        )
        or not exact_unknown_axis(
            normal_acceleration,
            subject_id=table_id,
            point_id=None,
            component=QuantityComponent.y,
            sign=1,
        )
        or not exact_unknown_axis(
            table_acceleration,
            subject_id=table_id,
            point_id=None,
            component=QuantityComponent.x,
            sign=None,
        )
        or not exact_unknown_axis(
            hanging_acceleration,
            subject_id=hanging_id,
            point_id=None,
            component=QuantityComponent.y,
            sign=None,
        )
    ):
        return None

    friction = friction_values[0] if len(friction_values) == 1 else None
    coefficient = coefficients[0] if len(coefficients) == 1 else None
    carrier = None
    if regime == "inactive":
        if (
            len(linked_contact) != 2
            or friction is not None
            or coefficient is not None
            or friction_state.quantity_ids
        ):
            return None
    else:
        if (
            len(linked_contact) != 4
            or friction is None
            or coefficient is None
            or not exact_known(coefficient, positive=False)
            or any(coefficient.dimension.model_dump(mode="python").values())
            or set(friction_state.quantity_ids)
            != {friction.quantity_id, normal.quantity_id, coefficient.quantity_id}
            or len(friction_state.quantity_ids) != 3
        ):
            return None
        motion_state = table_motion[0]
        if regime == "sticking":
            if (
                motion_state.state is not StateValue.at_rest
                or motion_state.quantity_ids
                or not exact_unknown_axis(
                    friction,
                    subject_id=table_id,
                    point_id=point.point_id,
                    component=QuantityComponent.x,
                    sign=-1,
                )
            ):
                return None
        else:
            if motion_state.state is not StateValue.moving or len(motion_state.quantity_ids) != 1:
                return None
            carrier = quantities.get(motion_state.quantity_ids[0])
            if (
                carrier is None
                or carrier.role is not QuantityRole.velocity
                or carrier.shape is not QuantityShape.scalar
                or carrier.dimension != DimensionVector(length=1, time=-1)
                or carrier.symbol_id is None
                or carrier.subject_id != table_id
                or carrier.point_id is not None
                or carrier.frame_id != frame.frame_id
                or carrier.interval_id != interval.interval_id
                or carrier.event_id is not None
                or carrier.component is not QuantityComponent.x
                or type(carrier.known_si_value) is not float
                or not math.isfinite(carrier.known_si_value)
                or carrier.known_si_value <= 0.0
                or not carrier.evidence_ids
                or not _axis_bound(
                    carrier,
                    frame.frame_id,
                    QuantityComponent.x,
                    1,
                )
                or not exact_unknown_axis(
                    friction,
                    subject_id=table_id,
                    point_id=point.point_id,
                    component=QuantityComponent.x,
                    sign=-1,
                )
            ):
                return None

    if (
        set(touching[0].quantity_ids)
        != {normal.quantity_id, normal_acceleration.quantity_id}
        or len(touching[0].quantity_ids) != 2
        or any(
            item.dimension != weights[table_id].dimension
            for item in (*weights.values(), *tensions, normal)
        )
        or masses[table_id].dimension.plus(gravity.dimension)
        != weights[table_id].dimension
        or masses[hanging_id].dimension.plus(gravity.dimension)
        != weights[hanging_id].dimension
        or masses[table_id].dimension.plus(table_acceleration.dimension)
        != weights[table_id].dimension
        or masses[table_id].dimension.plus(normal_acceleration.dimension)
        != weights[table_id].dimension
        or masses[hanging_id].dimension.plus(hanging_acceleration.dimension)
        != weights[hanging_id].dimension
        or table_acceleration.dimension != gravity.dimension
        or normal_acceleration.dimension != gravity.dimension
        or hanging_acceleration.dimension != gravity.dimension
        or (friction is not None and friction.dimension != normal.dimension)
    ):
        return None

    expected_quantities = {
        item.quantity_id
        for item in (
            *masses.values(),
            gravity,
            *weights.values(),
            *tensions,
            table_acceleration,
            normal_acceleration,
            hanging_acceleration,
            normal,
            *(() if friction is None else (friction,)),
            *(() if coefficient is None else (coefficient,)),
            *(() if carrier is None else (carrier,)),
        )
    }
    if set(quantities) != expected_quantities:
        return None

    contact_state_ids = tuple(
        sorted(
            {
                touching[0].state_condition_id,
                surface_states[0].state_condition_id,
                friction_state.state_condition_id,
                *(
                    ()
                    if regime == "inactive"
                    else (table_motion[0].state_condition_id,)
                ),
            }
        )
    )
    return _FixedPulleyHorizontalContactLawProfile(
        rope_interaction_id=rope_interaction.interaction_id,
        table_id=table_id,
        hanging_id=hanging_id,
        surface_id=surface_id,
        rope_id=rope_id,
        pulley_id=pulley_id,
        frame_id=frame.frame_id,
        interval_id=interval.interval_id,
        regime=regime,
        normal=normal,
        normal_acceleration=normal_acceleration,
        table_acceleration=table_acceleration,
        hanging_acceleration=hanging_acceleration,
        table_tension=table_tension,
        hanging_tension=hanging_tension,
        friction=friction,
        coefficient=coefficient,
        carrier=carrier,
        contact_state_ids=contact_state_ids,
    )


def _horizontal_fixed_contact_emissions(context: LawContext) -> list[LawEmission]:
    profile = _fixed_pulley_horizontal_contact_profile(
        context,
        require_rope_authority=False,
    )
    if profile is None:
        return []
    emitted = [
        _emit(
            context,
            "fixed_contact_no_penetration",
            Equality(
                left=profile.normal_acceleration.expression,
                right=LiteralNode(
                    value=0.0,
                    dimension=profile.normal_acceleration.dimension,
                ),
            ),
            (profile.normal_acceleration, profile.normal),
            constraint_ids=profile.contact_state_ids,
            extra_entity_ids=(profile.surface_id,),
        ),
        _emit(
            context,
            "contact_normal_bound",
            Inequality(
                relation=InequalityRelation.ge,
                left=profile.normal.expression,
                right=LiteralNode(value=0.0, dimension=profile.normal.dimension),
            ),
            (profile.normal,),
            constraint_ids=profile.contact_state_ids,
            extra_entity_ids=(profile.surface_id,),
        ),
    ]
    if profile.regime == "inactive":
        return emitted
    friction = profile.friction
    coefficient = profile.coefficient
    if friction is None or coefficient is None:
        return []
    bound = Multiply(
        factors=(coefficient.expression, profile.normal.expression),
        dimension=friction.dimension,
    )
    friction_quantities = (friction, profile.normal, coefficient)
    if profile.regime == "sticking":
        for left in (
            _signed(friction),
            Negate(operand=_signed(friction), dimension=friction.dimension),
        ):
            emitted.append(
                _emit(
                    context,
                    "contact_friction_bound",
                    Inequality(
                        relation=InequalityRelation.le,
                        left=left,
                        right=bound,
                    ),
                    friction_quantities,
                    constraint_ids=profile.contact_state_ids,
                    extra_entity_ids=(profile.surface_id,),
                )
            )
        emitted.append(
            _emit(
                context,
                "contact_sticking_static_acceleration",
                Equality(
                    left=_signed(profile.table_acceleration),
                    right=LiteralNode(
                        value=0.0,
                        dimension=profile.table_acceleration.dimension,
                    ),
                ),
                (
                    profile.table_acceleration,
                    friction,
                    profile.normal,
                    coefficient,
                ),
                constraint_ids=profile.contact_state_ids,
                extra_entity_ids=(profile.surface_id,),
            )
        )
    else:
        friction_quantities = (
            *friction_quantities,
            *((profile.carrier,) if profile.carrier is not None else ()),
        )
        emitted.append(
            _emit(
                context,
                "contact_sliding_friction",
                Equality(left=friction.expression, right=bound),
                friction_quantities,
                constraint_ids=profile.contact_state_ids,
                extra_entity_ids=(profile.surface_id,),
            )
        )
    return emitted


@dataclass(frozen=True)
class _FixedPulleyInclineContactLawProfile:
    incline_body_id: str
    hanging_body_id: str
    incline_id: str
    rope_id: str
    pulley_id: str
    interval_id: str
    wrap_id: str
    incline_attachment_id: str
    hanging_attachment_id: str
    rope_taut_state_id: str
    pulley_fixed_state_id: str
    friction_state_id: str
    body_motion_state_id: str | None
    motion_direction_assumption_id: str | None
    tension_incline: BoundQuantity
    tension_hanging: BoundQuantity
    rope_tension: BoundQuantity
    acceleration_incline: BoundQuantity
    acceleration_hanging: BoundQuantity
    rope_acceleration: BoundQuantity
    motion_carrier: BoundQuantity | None


def _fixed_pulley_incline_contact_profile(
    context: LawContext,
    interaction_id: str | None = None,
) -> _FixedPulleyInclineContactLawProfile | None:
    """Recognize only the closed two-frame incline/hanging rope contract."""

    primitive_ids = {
        primitive: tuple(
            item.entity_id
            for item in context.entities
            if item.primitive is primitive
        )
        for primitive in (
            EntityPrimitive.particle,
            EntityPrimitive.incline,
            EntityPrimitive.rope,
            EntityPrimitive.pulley,
            EntityPrimitive.environment,
        )
    }
    if (
        {key: len(value) for key, value in primitive_ids.items()}
        != {
            EntityPrimitive.particle: 2,
            EntityPrimitive.incline: 1,
            EntityPrimitive.rope: 1,
            EntityPrimitive.pulley: 1,
            EntityPrimitive.environment: 1,
        }
        or len(context.entities) != 6
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in context.entities
        )
    ):
        return None
    particle_ids = set(primitive_ids[EntityPrimitive.particle])
    incline_id = primitive_ids[EntityPrimitive.incline][0]
    rope_id = primitive_ids[EntityPrimitive.rope][0]
    pulley_id = primitive_ids[EntityPrimitive.pulley][0]
    environment_id = primitive_ids[EntityPrimitive.environment][0]

    world_frames = tuple(
        item
        for item in context.reference_frames
        if item.frame_type is ReferenceFrameType.cartesian_2d
    )
    incline_frames = tuple(
        item
        for item in context.reference_frames
        if item.frame_type is ReferenceFrameType.tangential_normal
    )
    if (
        len(context.reference_frames) != 2
        or len(world_frames) != 1
        or len(incline_frames) != 1
    ):
        return None
    world_frame = world_frames[0]
    incline_frame = incline_frames[0]

    def axis_signature(frame: object) -> set[tuple[object, ...]]:
        return {
            (
                item.axis.value,
                item.direction.kind,
                getattr(item.direction, "frame_id", None),
                getattr(getattr(item.direction, "axis", None), "value", None),
                getattr(item.direction, "sign", None),
            )
            for item in getattr(frame, "axes", ())
        }

    if (
        getattr(world_frame.origin, "kind", None) != "world"
        or world_frame.parent_frame_id is not None
        or world_frame.translating_with_entity_id is not None
        or world_frame.rotating_about_point_id is not None
        or world_frame.generalized_coordinate_symbol_ids
        or not world_frame.evidence_refs
        or len(world_frame.axes) != 2
        or axis_signature(world_frame)
        != {
            ("x", "axis", world_frame.frame_id, "x", 1),
            ("y", "axis", world_frame.frame_id, "y", 1),
        }
        or getattr(incline_frame.origin, "kind", None) != "entity"
        or getattr(incline_frame.origin, "entity_id", None) != incline_id
        or incline_frame.parent_frame_id != world_frame.frame_id
        or incline_frame.translating_with_entity_id is not None
        or incline_frame.rotating_about_point_id is not None
        or incline_frame.generalized_coordinate_symbol_ids
        or not incline_frame.evidence_refs
        or len(incline_frame.axes) != 2
        or axis_signature(incline_frame)
        != {
            ("tangent", "axis", incline_frame.frame_id, "tangent", 1),
            ("normal", "axis", incline_frame.frame_id, "normal", 1),
        }
    ):
        return None

    if len(context.motion_intervals) != 1 or context.events:
        return None
    interval = context.motion_intervals[0]
    if (
        interval.frame_id is not None
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or len(interval.subject_ids) != len(context.entities)
        or set(interval.subject_ids)
        != {item.entity_id for item in context.entities}
        or not interval.evidence_refs
    ):
        return None

    contacts = tuple(
        item
        for item in context.interactions
        if item.kind is InteractionKind.contact
    )
    rope_interactions = tuple(
        item
        for item in context.interactions
        if item.kind is InteractionKind.rope_tension
        and (interaction_id is None or item.interaction_id == interaction_id)
    )
    gravity_interactions = tuple(
        item
        for item in context.interactions
        if item.kind is InteractionKind.gravity
    )
    if (
        len(context.interactions) != 4
        or len(contacts) != 1
        or len(rope_interactions) != 1
        or len(gravity_interactions) != 2
    ):
        return None
    contact = contacts[0]
    rope_interaction = rope_interactions[0]
    incline_body_ids = set(contact.participant_ids) & particle_ids
    if (
        len(incline_body_ids) != 1
        or len(contact.participant_ids) != 2
        or set(contact.participant_ids)
        != {next(iter(incline_body_ids), ""), incline_id}
        or len(contact.point_ids) != 1
        or contact.frame_id != incline_frame.frame_id
        or contact.interval_id != interval.interval_id
        or contact.event_id is not None
        or not contact.evidence_refs
    ):
        return None
    incline_body_id = next(iter(incline_body_ids))
    hanging_body_id = next(iter(particle_ids - {incline_body_id}))
    if len(context.points) != 1:
        return None
    point = context.points[0]
    if (
        point.point_id != contact.point_ids[0]
        or point.role is not PointRole.contact
        or point.owner_entity_id != incline_body_id
        or point.frame_id != incline_frame.frame_id
        or not point.evidence_refs
    ):
        return None

    incline_gravity = tuple(
        item
        for item in gravity_interactions
        if set(item.participant_ids) == {incline_body_id, environment_id}
    )
    hanging_gravity = tuple(
        item
        for item in gravity_interactions
        if set(item.participant_ids) == {hanging_body_id, environment_id}
    )
    if (
        len(incline_gravity) != 1
        or len(hanging_gravity) != 1
        or incline_gravity[0].frame_id != incline_frame.frame_id
        or len(incline_gravity[0].quantity_ids) != 4
        or hanging_gravity[0].frame_id != world_frame.frame_id
        or len(hanging_gravity[0].quantity_ids) != 3
        or any(
            len(item.participant_ids) != 2
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.point_ids
            or len(item.quantity_ids) != len(set(item.quantity_ids))
            or not item.evidence_refs
            for item in gravity_interactions
        )
        or len(rope_interaction.participant_ids) != 4
        or set(rope_interaction.participant_ids)
        != particle_ids | {rope_id, pulley_id}
        or rope_interaction.point_ids
        or rope_interaction.frame_id is not None
        or rope_interaction.interval_id != interval.interval_id
        or rope_interaction.event_id is not None
        or len(rope_interaction.quantity_ids) != 6
        or len(set(rope_interaction.quantity_ids)) != 6
        or not rope_interaction.evidence_refs
    ):
        return None

    angles = tuple(
        item
        for item in context.geometry
        if item.kind is GeometryRelationKind.angle
    )
    wraps = tuple(
        item
        for item in context.geometry
        if item.kind is GeometryRelationKind.wraps
    )
    attached = tuple(
        item
        for item in context.geometry
        if item.kind is GeometryRelationKind.attached
    )
    if (
        len(context.geometry) != 4
        or len(angles) != 1
        or len(wraps) != 1
        or len(attached) != 2
        or any(
            item.expression is not None
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            for item in context.geometry
        )
        or set(angles[0].participant_ids) != {incline_id, environment_id}
        or len(angles[0].quantity_ids) != 1
        or angles[0].interval_id is not None
        or set(wraps[0].participant_ids) != {rope_id, pulley_id}
        or len(wraps[0].quantity_ids) != 2
        or wraps[0].interval_id != interval.interval_id
        or {frozenset(item.participant_ids) for item in attached}
        != {
            frozenset((rope_id, incline_body_id)),
            frozenset((rope_id, hanging_body_id)),
        }
        or any(
            len(item.quantity_ids) != 4
            or item.interval_id != interval.interval_id
            for item in attached
        )
    ):
        return None

    quantities = {
        item.quantity_id: item
        for item in context.quantities
        if item.quantity_id is not None
    }
    if len(quantities) != len(context.quantities):
        return None

    def linked(interaction: object) -> tuple[BoundQuantity, ...]:
        return tuple(quantities.get(item) for item in interaction.quantity_ids)

    incline_linked = linked(incline_gravity[0])
    hanging_linked = linked(hanging_gravity[0])
    contact_linked = linked(contact)
    rope_linked = linked(rope_interaction)
    if any(
        item is None
        for item in (*incline_linked, *hanging_linked, *contact_linked, *rope_linked)
    ):
        return None

    def one_quantity(
        values: tuple[BoundQuantity, ...],
        *,
        role: QuantityRole,
        subject_id: str,
        component: QuantityComponent | None = None,
    ) -> BoundQuantity | None:
        matches = tuple(
            item
            for item in values
            if item.role is role
            and item.subject_id == subject_id
            and (component is None or item.component is component)
        )
        return matches[0] if len(matches) == 1 else None

    mass_incline = one_quantity(
        incline_linked, role=QuantityRole.mass, subject_id=incline_body_id
    )
    mass_hanging = one_quantity(
        hanging_linked, role=QuantityRole.mass, subject_id=hanging_body_id
    )
    gravity_a = one_quantity(
        incline_linked, role=QuantityRole.gravity, subject_id=environment_id
    )
    gravity_b = one_quantity(
        hanging_linked, role=QuantityRole.gravity, subject_id=environment_id
    )
    angle = quantities.get(angles[0].quantity_ids[0])
    gravity_tangent = one_quantity(
        incline_linked,
        role=QuantityRole.force,
        subject_id=incline_body_id,
        component=QuantityComponent.tangential,
    )
    gravity_normal = one_quantity(
        incline_linked,
        role=QuantityRole.force,
        subject_id=incline_body_id,
        component=QuantityComponent.normal,
    )
    hanging_weight = one_quantity(
        hanging_linked,
        role=QuantityRole.force,
        subject_id=hanging_body_id,
        component=QuantityComponent.y,
    )
    tension_incline = one_quantity(
        rope_linked,
        role=QuantityRole.force,
        subject_id=incline_body_id,
        component=QuantityComponent.tangential,
    )
    tension_hanging = one_quantity(
        rope_linked,
        role=QuantityRole.force,
        subject_id=hanging_body_id,
        component=QuantityComponent.y,
    )
    rope_tension = one_quantity(
        rope_linked, role=QuantityRole.force, subject_id=rope_id
    )
    acceleration_incline = one_quantity(
        rope_linked,
        role=QuantityRole.acceleration,
        subject_id=incline_body_id,
        component=QuantityComponent.tangential,
    )
    acceleration_hanging = one_quantity(
        rope_linked,
        role=QuantityRole.acceleration,
        subject_id=hanging_body_id,
        component=QuantityComponent.y,
    )
    rope_acceleration = one_quantity(
        rope_linked, role=QuantityRole.acceleration, subject_id=rope_id
    )
    normal = one_quantity(
        contact_linked,
        role=QuantityRole.force,
        subject_id=incline_body_id,
        component=QuantityComponent.normal,
    )
    normal_acceleration = one_quantity(
        contact_linked,
        role=QuantityRole.acceleration,
        subject_id=incline_body_id,
        component=QuantityComponent.normal,
    )
    required = (
        mass_incline,
        mass_hanging,
        gravity_a,
        gravity_b,
        angle,
        gravity_tangent,
        gravity_normal,
        hanging_weight,
        tension_incline,
        tension_hanging,
        rope_tension,
        acceleration_incline,
        acceleration_hanging,
        rope_acceleration,
        normal,
        normal_acceleration,
    )
    if any(item is None for item in required) or gravity_b is not gravity_a:
        return None

    def exact_known(item: BoundQuantity, *, positive: bool) -> bool:
        value = item.known_si_value
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.evidence_ids
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and not item.direction_bound
            and item.component
            in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            and type(value) is float
            and math.isfinite(value)
            and (value > 0.0 if positive else value >= 0.0)
        )

    if (
        not exact_known(mass_incline, positive=True)
        or not exact_known(mass_hanging, positive=True)
        or not exact_known(gravity_a, positive=True)
        or angle.role is not QuantityRole.angle
        or angle.subject_id != incline_id
        or not exact_known(angle, positive=False)
        or angle.dimension != DimensionVector.dimensionless()
        or not 0.0 <= angle.known_si_value < math.pi / 2.0
    ):
        return None

    def exact_unknown_axis(
        item: BoundQuantity,
        *,
        role: QuantityRole,
        subject_id: str,
        point_id: str | None,
        frame_id: str,
        component: QuantityComponent,
        sign: int | None,
    ) -> bool:
        observed_sign = item.direction_sign
        return (
            item.role is role
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.known_si_value is None
            and item.evidence_ids
            and item.subject_id == subject_id
            and item.point_id == point_id
            and item.frame_id == frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component is component
            and item.direction_bound
            and observed_sign in {-1, 1}
            and (sign is None or observed_sign == sign)
            and _axis_bound(item, frame_id, component, observed_sign)
        )

    if (
        not exact_unknown_axis(
            gravity_tangent,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component=QuantityComponent.tangential,
            sign=1,
        )
        or not exact_unknown_axis(
            gravity_normal,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component=QuantityComponent.normal,
            sign=-1,
        )
        or not exact_unknown_axis(
            hanging_weight,
            role=QuantityRole.force,
            subject_id=hanging_body_id,
            point_id=None,
            frame_id=world_frame.frame_id,
            component=QuantityComponent.y,
            sign=1,
        )
        or not exact_unknown_axis(
            tension_incline,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component=QuantityComponent.tangential,
            sign=-1,
        )
        or not exact_unknown_axis(
            tension_hanging,
            role=QuantityRole.force,
            subject_id=hanging_body_id,
            point_id=None,
            frame_id=world_frame.frame_id,
            component=QuantityComponent.y,
            sign=-1,
        )
        or not exact_unknown_axis(
            normal,
            role=QuantityRole.force,
            subject_id=incline_body_id,
            point_id=point.point_id,
            frame_id=incline_frame.frame_id,
            component=QuantityComponent.normal,
            sign=1,
        )
        or not exact_unknown_axis(
            normal_acceleration,
            role=QuantityRole.acceleration,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component=QuantityComponent.normal,
            sign=1,
        )
        or not exact_unknown_axis(
            acceleration_incline,
            role=QuantityRole.acceleration,
            subject_id=incline_body_id,
            point_id=None,
            frame_id=incline_frame.frame_id,
            component=QuantityComponent.tangential,
            sign=None,
        )
        or not exact_unknown_axis(
            acceleration_hanging,
            role=QuantityRole.acceleration,
            subject_id=hanging_body_id,
            point_id=None,
            frame_id=world_frame.frame_id,
            component=QuantityComponent.y,
            sign=None,
        )
        or acceleration_incline.direction_sign
        != -acceleration_hanging.direction_sign
    ):
        return None

    def exact_rope_coordinate(
        item: BoundQuantity,
        role: QuantityRole,
        dimension: DimensionVector,
    ) -> bool:
        return (
            item.role is role
            and item.subject_id == rope_id
            and item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.known_si_value is None
            and item.evidence_ids
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and item.component
            in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            and not item.direction_bound
            and item.dimension == dimension
        )

    if (
        not exact_rope_coordinate(
            rope_tension, QuantityRole.force, tension_incline.dimension
        )
        or not exact_rope_coordinate(
            rope_acceleration,
            QuantityRole.acceleration,
            acceleration_incline.dimension,
        )
        or set(rope_interaction.quantity_ids)
        != {
            tension_incline.quantity_id,
            tension_hanging.quantity_id,
            rope_tension.quantity_id,
            acceleration_incline.quantity_id,
            acceleration_hanging.quantity_id,
            rope_acceleration.quantity_id,
        }
        or set(wraps[0].quantity_ids)
        != {rope_tension.quantity_id, rope_acceleration.quantity_id}
    ):
        return None
    incline_attachment = _one(
        item for item in attached if incline_body_id in item.participant_ids
    )
    hanging_attachment = _one(
        item for item in attached if hanging_body_id in item.participant_ids
    )
    if (
        incline_attachment is None
        or hanging_attachment is None
        or set(incline_attachment.quantity_ids)
        != {
            tension_incline.quantity_id,
            acceleration_incline.quantity_id,
            rope_tension.quantity_id,
            rope_acceleration.quantity_id,
        }
        or set(hanging_attachment.quantity_ids)
        != {
            tension_hanging.quantity_id,
            acceleration_hanging.quantity_id,
            rope_tension.quantity_id,
            rope_acceleration.quantity_id,
        }
    ):
        return None

    states = tuple(context.state_conditions)
    if any(
        item.interval_id != interval.interval_id
        or item.event_id is not None
        or item.expression is not None
        or not item.evidence_refs
        or len(item.quantity_ids) != len(set(item.quantity_ids))
        for item in states
    ):
        return None
    rope_state = _one(
        item for item in states
        if item.subject_id == rope_id
        and item.kind is StateKind.rope
        and item.state is StateValue.taut
        and not item.quantity_ids
    )
    pulley_state = _one(
        item for item in states
        if item.subject_id == pulley_id
        and item.kind is StateKind.motion
        and item.state is StateValue.at_rest
        and not item.quantity_ids
    )
    contact_state = _one(
        item for item in states
        if item.subject_id == incline_body_id
        and item.kind is StateKind.contact
        and item.state is StateValue.touching
    )
    incline_state = _one(
        item for item in states
        if item.subject_id == incline_id
        and item.kind is StateKind.motion
        and item.state is StateValue.at_rest
        and not item.quantity_ids
    )
    friction_state = _one(
        item for item in states
        if item.subject_id == incline_body_id
        and item.kind is StateKind.friction
        and item.state
        in {StateValue.inactive, StateValue.sticking, StateValue.sliding}
    )
    if any(
        item is None
        for item in (
            rope_state,
            pulley_state,
            contact_state,
            incline_state,
            friction_state,
        )
    ):
        return None
    if (
        set(contact_state.quantity_ids)
        != {normal.quantity_id, normal_acceleration.quantity_id}
        or len(contact_state.quantity_ids) != 2
    ):
        return None

    friction_values = tuple(
        item
        for item in contact_linked
        if item.role is QuantityRole.force
        and item.component is QuantityComponent.tangential
    )
    coefficient_values = tuple(
        item
        for item in contact_linked
        if item.role is QuantityRole.coefficient_friction
    )
    friction = friction_values[0] if len(friction_values) == 1 else None
    coefficient = coefficient_values[0] if len(coefficient_values) == 1 else None
    body_motion = _one(
        item for item in states
        if item.subject_id == incline_body_id
        and item.kind is StateKind.motion
    )
    carrier = None
    if friction_state.state is StateValue.inactive:
        if (
            len(states) != 5
            or len(contact_linked) != 2
            or friction is not None
            or coefficient is not None
            or friction_state.quantity_ids
            or body_motion is not None
        ):
            return None
    else:
        if (
            len(states) != 6
            or len(contact_linked) != 4
            or friction is None
            or coefficient is None
            or body_motion is None
            or not exact_unknown_axis(
                friction,
                role=QuantityRole.force,
                subject_id=incline_body_id,
                point_id=point.point_id,
                frame_id=incline_frame.frame_id,
                component=QuantityComponent.tangential,
                sign=None,
            )
            or coefficient.role is not QuantityRole.coefficient_friction
            or coefficient.subject_id != incline_body_id
            or coefficient.dimension != DimensionVector.dimensionless()
            or not exact_known(coefficient, positive=False)
            or set(friction_state.quantity_ids)
            != {friction.quantity_id, normal.quantity_id, coefficient.quantity_id}
        ):
            return None
        if friction_state.state is StateValue.sticking:
            hanging_drive = mass_hanging.known_si_value * gravity_a.known_si_value
            incline_drive = (
                mass_incline.known_si_value
                * gravity_a.known_si_value
                * math.sin(angle.known_si_value)
            )
            static_drive = hanging_drive - incline_drive
            static_drive_is_zero = math.isclose(
                static_drive,
                0.0,
                rel_tol=1.0e-12,
                abs_tol=1.0e-12 * max(1.0, abs(hanging_drive), abs(incline_drive)),
            )
            expected_sign = (
                None
                if static_drive_is_zero
                else 1 if static_drive > 0.0 else -1
            )
            if (
                body_motion.state is not StateValue.at_rest
                or body_motion.quantity_ids
                or (
                    expected_sign is not None
                    and friction.direction_sign != expected_sign
                )
            ):
                return None
        else:
            if body_motion.state is not StateValue.moving or len(body_motion.quantity_ids) != 1:
                return None
            carrier = quantities.get(body_motion.quantity_ids[0])
            if (
                carrier is None
                or carrier.role is not QuantityRole.velocity
                or carrier.subject_id != incline_body_id
                or carrier.shape is not QuantityShape.scalar
                or carrier.symbol_id is None
                or carrier.dimension != DimensionVector(length=1, time=-1)
                or carrier.point_id is not None
                or carrier.frame_id != incline_frame.frame_id
                or carrier.interval_id != interval.interval_id
                or carrier.event_id is not None
                or carrier.component is not QuantityComponent.tangential
                or type(carrier.known_si_value) is not float
                or not math.isfinite(carrier.known_si_value)
                or carrier.known_si_value <= 0.0
                or not carrier.evidence_ids
                or not carrier.direction_bound
                or carrier.direction_sign not in {-1, 1}
                or not _axis_bound(
                    carrier,
                    incline_frame.frame_id,
                    QuantityComponent.tangential,
                    carrier.direction_sign,
                )
                or friction.direction_sign != -carrier.direction_sign
            ):
                return None

    required_assumptions = {
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("ideal_massless_frictionless_pulley", pulley_id),
        ("fixed_pulley", pulley_id),
        *((
            ("acceleration_not_opposite_motion", incline_body_id),
        ) if friction_state.state is StateValue.sliding else ()),
    }
    approved_ids = frozenset(
        assumption_id
        for kind, subject_id in required_assumptions
        for assumption_id in context.approved_assumptions(
            kind, subject_id, interval.interval_id
        )
    )
    approved_records = tuple(
        item for item in context.assumptions if item.assumption_id in approved_ids
    )
    if (
        len(context.assumptions) != len(required_assumptions)
        or len(approved_records) != len(required_assumptions)
        or approved_ids != frozenset(item.assumption_id for item in context.assumptions)
        or {(item.kind, item.subject_id) for item in approved_records}
        != required_assumptions
        or any(
            item.interval_id != interval.interval_id or not item.evidence_refs
            for item in approved_records
        )
    ):
        return None
    motion_direction_assumption = _one(
        item
        for item in approved_records
        if item.kind == "acceleration_not_opposite_motion"
        and item.subject_id == incline_body_id
    )
    if (motion_direction_assumption is not None) != (
        friction_state.state is StateValue.sliding
    ):
        return None

    expected_quantities = {
        item.quantity_id
        for item in (
            mass_incline,
            mass_hanging,
            gravity_a,
            angle,
            gravity_tangent,
            gravity_normal,
            hanging_weight,
            tension_incline,
            tension_hanging,
            rope_tension,
            acceleration_incline,
            acceleration_hanging,
            rope_acceleration,
            normal,
            normal_acceleration,
            *(() if friction is None else (friction,)),
            *(() if coefficient is None else (coefficient,)),
            *(() if carrier is None else (carrier,)),
        )
    }
    if (
        set(quantities) != expected_quantities
        or mass_incline.dimension.plus(gravity_a.dimension)
        != gravity_tangent.dimension
        or gravity_tangent.dimension
        != gravity_normal.dimension
        or gravity_tangent.dimension
        != hanging_weight.dimension
        or gravity_tangent.dimension
        != tension_incline.dimension
        or gravity_tangent.dimension
        != tension_hanging.dimension
        or gravity_tangent.dimension != rope_tension.dimension
        or gravity_tangent.dimension != normal.dimension
        or mass_incline.dimension.plus(acceleration_incline.dimension)
        != gravity_tangent.dimension
        or mass_incline.dimension.plus(normal_acceleration.dimension)
        != normal.dimension
        or mass_hanging.dimension.plus(acceleration_hanging.dimension)
        != hanging_weight.dimension
        or acceleration_incline.dimension != acceleration_hanging.dimension
        or acceleration_incline.dimension != rope_acceleration.dimension
        or acceleration_incline.dimension != gravity_a.dimension
        or normal_acceleration.dimension != gravity_a.dimension
        or (friction is not None and friction.dimension != normal.dimension)
    ):
        return None

    return _FixedPulleyInclineContactLawProfile(
        incline_body_id=incline_body_id,
        hanging_body_id=hanging_body_id,
        incline_id=incline_id,
        rope_id=rope_id,
        pulley_id=pulley_id,
        interval_id=interval.interval_id,
        wrap_id=wraps[0].relation_id,
        incline_attachment_id=incline_attachment.relation_id,
        hanging_attachment_id=hanging_attachment.relation_id,
        rope_taut_state_id=rope_state.state_condition_id,
        pulley_fixed_state_id=pulley_state.state_condition_id,
        friction_state_id=friction_state.state_condition_id,
        body_motion_state_id=(
            None if body_motion is None else body_motion.state_condition_id
        ),
        motion_direction_assumption_id=(
            None
            if motion_direction_assumption is None
            else motion_direction_assumption.assumption_id
        ),
        tension_incline=tension_incline,
        tension_hanging=tension_hanging,
        rope_tension=rope_tension,
        acceleration_incline=acceleration_incline,
        acceleration_hanging=acceleration_hanging,
        rope_acceleration=rope_acceleration,
        motion_carrier=carrier,
    )


def _incline_hanging_rope_emissions(context: LawContext) -> list[LawEmission]:
    profile = _fixed_pulley_incline_contact_profile(context)
    if profile is None:
        return []
    massless = context.approved_assumptions(
        "massless_rope", profile.rope_id, profile.interval_id
    )
    ideal = context.approved_assumptions(
        "ideal_massless_frictionless_pulley",
        profile.pulley_id,
        profile.interval_id,
    )
    inextensible = context.approved_assumptions(
        "inextensible_rope", profile.rope_id, profile.interval_id
    )
    fixed = context.approved_assumptions(
        "fixed_pulley", profile.pulley_id, profile.interval_id
    )
    emitted: list[LawEmission] = []
    for local, attachment_id in (
        (profile.tension_incline, profile.incline_attachment_id),
        (profile.tension_hanging, profile.hanging_attachment_id),
    ):
        emitted.append(
            _emit(
                context,
                "rope_attachment_tension_transfer",
                Equality(
                    left=local.expression,
                    right=profile.rope_tension.expression,
                ),
                (local, profile.rope_tension),
                assumption_ids=tuple(sorted(set(massless) | set(ideal))),
                constraint_ids=tuple(
                    sorted(
                        {
                            attachment_id,
                            profile.wrap_id,
                            profile.rope_taut_state_id,
                        }
                    )
                ),
                extra_entity_ids=(profile.rope_id, profile.pulley_id),
            )
        )
    acceleration_transfers = (
        (
            profile.acceleration_incline,
            profile.rope_acceleration.expression,
            profile.incline_attachment_id,
        ),
        (
            profile.acceleration_hanging,
            Negate(
                operand=profile.rope_acceleration.expression,
                dimension=profile.rope_acceleration.dimension,
            ),
            profile.hanging_attachment_id,
        ),
    )
    for local, rope_side, attachment_id in acceleration_transfers:
        emitted.append(
            _emit(
                context,
                "rope_attachment_acceleration_transfer",
                Equality(left=_signed(local), right=rope_side),
                (local, profile.rope_acceleration),
                assumption_ids=tuple(sorted(set(inextensible) | set(fixed))),
                constraint_ids=tuple(
                    sorted(
                        {
                            attachment_id,
                            profile.wrap_id,
                            profile.rope_taut_state_id,
                            profile.pulley_fixed_state_id,
                        }
                    )
                ),
                extra_entity_ids=(profile.rope_id, profile.pulley_id),
            )
        )
    if profile.motion_carrier is not None:
        if profile.motion_direction_assumption_id is None:
            return []
        physical_acceleration = _signed(profile.acceleration_incline)
        motion_projection = (
            physical_acceleration
            if profile.motion_carrier.direction_sign > 0
            else Negate(
                operand=physical_acceleration,
                dimension=profile.acceleration_incline.dimension,
            )
        )
        emitted.append(
            _emit(
                context,
                "incline_hanging_sliding_direction_consistency",
                Inequality(
                    relation=InequalityRelation.ge,
                    left=motion_projection,
                    right=LiteralNode(
                        value=0.0,
                        dimension=profile.acceleration_incline.dimension,
                    ),
                ),
                (profile.acceleration_incline, profile.motion_carrier),
                assumption_ids=(profile.motion_direction_assumption_id,),
                constraint_ids=tuple(
                    item
                    for item in (
                        profile.friction_state_id,
                        profile.body_motion_state_id,
                    )
                    if item is not None
                ),
                extra_entity_ids=(profile.incline_id,),
            )
        )
    return emitted


def _incline_gravity_contact_emissions(context: LawContext) -> list[LawEmission]:
    """Project gravity only for an exact source-backed fixed-contact contract."""

    emitted: list[LawEmission] = []
    incline_hanging_profile = _fixed_pulley_incline_contact_profile(context)
    kinds = {item.entity_id: item.primitive for item in context.entities}
    quantities = {item.quantity_id: item for item in context.quantities if item.quantity_id}
    frames = {item.frame_id: item for item in context.reference_frames}
    for gravity_link in (
        item for item in context.interactions if item.kind is InteractionKind.gravity
    ):
        body_id = _one(
            item for item in gravity_link.participant_ids
            if kinds.get(item) is EntityPrimitive.particle
        )
        environment_id = _one(
            item for item in gravity_link.participant_ids
            if kinds.get(item) is EntityPrimitive.environment
        )
        linked = tuple(quantities.get(item) for item in gravity_link.quantity_ids)
        if (
            body_id is None
            or environment_id is None
            or len(gravity_link.participant_ids) != 2
            or len(linked) != 4
            or any(item is None for item in linked)
            or gravity_link.frame_id is None
            or gravity_link.interval_id is None
            or gravity_link.event_id is not None
            or gravity_link.point_ids
            or not gravity_link.evidence_refs
        ):
            continue
        mass = _one(
            item for item in linked
            if item.role is QuantityRole.mass and item.subject_id == body_id
        )
        gravity = _one(
            item for item in linked
            if item.role is QuantityRole.gravity and item.subject_id == environment_id
        )
        gravity_tangent = _one(
            item for item in linked
            if item.role is QuantityRole.force
            and item.subject_id == body_id
            and item.point_id is None
            and item.interval_id == gravity_link.interval_id
            and _axis_bound(item, gravity_link.frame_id, QuantityComponent.tangential, 1)
        )
        gravity_normal = _one(
            item for item in linked
            if item.role is QuantityRole.force
            and item.subject_id == body_id
            and item.point_id is None
            and item.interval_id == gravity_link.interval_id
            and _axis_bound(item, gravity_link.frame_id, QuantityComponent.normal, -1)
        )
        relation = _one(
            item for item in context.geometry
            if item.kind is GeometryRelationKind.angle
            and item.expression is None
            and item.interval_id is None
            and len(item.participant_ids) == 2
            and environment_id in item.participant_ids
            and len(item.quantity_ids) == 1
            and item.evidence_refs
        )
        if any(item is None for item in (mass, gravity, gravity_tangent, gravity_normal, relation)):
            continue
        incline_id = _one(
            item for item in relation.participant_ids
            if kinds.get(item) is EntityPrimitive.incline
        )
        angle = quantities.get(relation.quantity_ids[0])
        frame = frames.get(gravity_link.frame_id)
        parent = frames.get(frame.parent_frame_id) if frame is not None else None
        contact = _one(
            item for item in context.interactions
            if item.kind is InteractionKind.contact
            and set(item.participant_ids) == {body_id, incline_id}
            and len(item.participant_ids) == 2
            and len(item.point_ids) == 1
            and item.frame_id == gravity_link.frame_id
            and item.interval_id == gravity_link.interval_id
            and item.event_id is None
            and len(item.quantity_ids) in {2, 4}
            and item.evidence_refs
        )
        if incline_id is None or angle is None or frame is None or parent is None or contact is None:
            continue
        body_entity = _one(
            item for item in context.entities if item.entity_id == body_id
        )
        incline_entity = _one(
            item for item in context.entities if item.entity_id == incline_id
        )
        motion_interval = _one(
            item for item in context.motion_intervals
            if item.interval_id == gravity_link.interval_id
        )
        if (
            body_entity is None
            or body_entity.primitive is not EntityPrimitive.particle
            or not body_entity.evidence_refs
            or incline_entity is None
            or incline_entity.primitive is not EntityPrimitive.incline
            or not incline_entity.evidence_refs
            or motion_interval is None
            or not motion_interval.evidence_refs
        ):
            continue
        interval_subject_ids = set(motion_interval.subject_ids)
        endpoint_events = tuple(
            _one(
                item for item in context.events
                if item.event_id == event_id
            )
            for event_id in (
                motion_interval.start_event_id,
                motion_interval.end_event_id,
            )
            if event_id is not None
        )
        if (
            motion_interval.interval_id != contact.interval_id
            or (
                motion_interval.frame_id != gravity_link.frame_id
                and not (
                    motion_interval.frame_id is None
                    and incline_hanging_profile is not None
                    and incline_hanging_profile.incline_body_id == body_id
                )
            )
            or (
                motion_interval.frame_id != contact.frame_id
                and not (
                    motion_interval.frame_id is None
                    and incline_hanging_profile is not None
                    and incline_hanging_profile.incline_body_id == body_id
                )
            )
            or len(motion_interval.subject_ids)
            != len(interval_subject_ids)
            or not (
                set(gravity_link.participant_ids)
                | set(contact.participant_ids)
            ).issubset(interval_subject_ids)
            or (
                motion_interval.start_event_id is not None
                and motion_interval.start_event_id
                == motion_interval.end_event_id
            )
            or any(
                event is None
                or motion_interval.interval_id not in event.interval_ids
                or not set(event.subject_ids).issubset(interval_subject_ids)
                for event in endpoint_events
            )
        ):
            continue
        contact_quantities = tuple(quantities.get(item) for item in contact.quantity_ids)
        normal_force = _one(
            item for item in contact_quantities
            if item is not None
            and item.role is QuantityRole.force
            and item.subject_id == body_id
            and item.point_id == contact.point_ids[0]
            and item.interval_id == contact.interval_id
            and _axis_bound(item, contact.frame_id, QuantityComponent.normal, 1)
        )
        normal_acceleration = _one(
            item for item in contact_quantities
            if item is not None
            and item.role is QuantityRole.acceleration
            and item.subject_id == body_id
            and item.point_id is None
            and item.interval_id == contact.interval_id
            and _axis_bound(item, contact.frame_id, QuantityComponent.normal, 1)
        )
        friction_force = _one(
            item for item in contact_quantities
            if item is not None
            and item.role is QuantityRole.force
            and item.subject_id == body_id
            and item.point_id == contact.point_ids[0]
            and item.interval_id == contact.interval_id
            and item.event_id is None
            and (
                _axis_bound(item, contact.frame_id, QuantityComponent.tangential, 1)
                or _axis_bound(item, contact.frame_id, QuantityComponent.tangential, -1)
            )
        )
        coefficient = _one(
            item for item in contact_quantities
            if item is not None
            and item.role is QuantityRole.coefficient_friction
            and item.subject_id == body_id
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and item.shape is QuantityShape.scalar
            and item.component in {
                QuantityComponent.magnitude,
                QuantityComponent.unspecified,
            }
            and not item.direction_bound
        )
        tangent_accelerations = tuple(
            item for item in _by_role(context, QuantityRole.acceleration)
            if item.subject_id == body_id
            and item.point_id is None
            and item.interval_id == contact.interval_id
            and item.event_id is None
            and item.symbol_id is not None
            and item.known_si_value is None
            and item.evidence_ids
            and (
                _axis_bound(item, contact.frame_id, QuantityComponent.tangential, 1)
                or _axis_bound(item, contact.frame_id, QuantityComponent.tangential, -1)
            )
        )
        states = tuple(
            item for item in context.state_conditions
            if item.interval_id == contact.interval_id
            and item.event_id is None
            and item.subject_id in {body_id, incline_id}
            and item.kind in {StateKind.contact, StateKind.friction, StateKind.motion}
        )
        frictionless_states = {
            (StateKind.contact, StateValue.touching, body_id,
             frozenset({getattr(normal_force, "quantity_id", None),
                        getattr(normal_acceleration, "quantity_id", None)})),
            (StateKind.friction, StateValue.inactive, body_id, frozenset()),
            (StateKind.motion, StateValue.at_rest, incline_id, frozenset()),
        }
        state_signatures = {
            (item.kind, item.state, item.subject_id, frozenset(item.quantity_ids))
            for item in states
        }
        exact_state_quantity_cardinality = all(
            len(item.quantity_ids) == len(set(item.quantity_ids))
            for item in states
        )
        friction_state = _one(
            item for item in states
            if item.kind is StateKind.friction
            and item.state in {StateValue.sticking, StateValue.sliding}
            and item.subject_id == body_id
        )
        body_motion = _one(
            item for item in states
            if item.kind is StateKind.motion
            and item.subject_id == body_id
            and item.state in {StateValue.at_rest, StateValue.moving}
        )
        motion_carrier = (
            quantities.get(body_motion.quantity_ids[0])
            if body_motion is not None and len(body_motion.quantity_ids) == 1
            else None
        )
        frictionless_profile = (
            len(contact_quantities) == 2
            and friction_force is None
            and coefficient is None
            and len(states) == 3
            and exact_state_quantity_cardinality
            and state_signatures == frictionless_states
        )
        frictional_contact = (
            len(contact_quantities) == 4
            and normal_force is not None
            and normal_acceleration is not None
            and friction_force is not None
            and coefficient is not None
            and {
                item.quantity_id
                for item in (normal_force, normal_acceleration, friction_force, coefficient)
                if item is not None
            }
            == set(contact.quantity_ids)
            and friction_force.shape is QuantityShape.scalar
            and friction_force.symbol_id is not None
            and friction_force.known_si_value is None
            and bool(friction_force.evidence_ids)
            and coefficient.symbol_id is not None
            and isinstance(coefficient.known_si_value, float)
            and math.isfinite(coefficient.known_si_value)
            and coefficient.known_si_value >= 0.0
            and bool(coefficient.evidence_ids)
            and not any(coefficient.dimension.model_dump(mode="python").values())
            and friction_force.dimension == normal_force.dimension
        )
        friction_quantity_ids = frozenset(
            getattr(item, "quantity_id", None)
            for item in (friction_force, normal_force, coefficient)
        )
        touching_signature = (
            StateKind.contact,
            StateValue.touching,
            body_id,
            frozenset({
                getattr(normal_force, "quantity_id", None),
                getattr(normal_acceleration, "quantity_id", None),
            }),
        )
        fixed_signature = (
            StateKind.motion,
            StateValue.at_rest,
            incline_id,
            frozenset(),
        )
        sticking_profile = (
            frictional_contact
            and friction_state is not None
            and friction_state.state is StateValue.sticking
            and body_motion is not None
            and body_motion.state is StateValue.at_rest
            and not body_motion.quantity_ids
            and (
                _axis_bound(
                    friction_force,
                    contact.frame_id,
                    QuantityComponent.tangential,
                    -1,
                )
                or (
                    incline_hanging_profile is not None
                    and incline_hanging_profile.incline_body_id == body_id
                    and friction_force.direction_sign in {-1, 1}
                    and _axis_bound(
                        friction_force,
                        contact.frame_id,
                        QuantityComponent.tangential,
                        friction_force.direction_sign,
                    )
                )
            )
            and len(states) == 4
            and exact_state_quantity_cardinality
            and state_signatures == {
                touching_signature,
                (StateKind.friction, StateValue.sticking, body_id, friction_quantity_ids),
                fixed_signature,
                (StateKind.motion, StateValue.at_rest, body_id, frozenset()),
            }
        )
        carrier_valid = (
            motion_carrier is not None
            and motion_carrier.role is QuantityRole.velocity
            and motion_carrier.dimension == DimensionVector(length=1, time=-1)
            and motion_carrier.subject_id == body_id
            and motion_carrier.point_id is None
            and motion_carrier.frame_id == contact.frame_id
            and motion_carrier.interval_id == contact.interval_id
            and motion_carrier.event_id is None
            and motion_carrier.shape is QuantityShape.scalar
            and motion_carrier.symbol_id is not None
            and isinstance(motion_carrier.known_si_value, float)
            and math.isfinite(motion_carrier.known_si_value)
            and motion_carrier.known_si_value > 0.0
            and bool(motion_carrier.evidence_ids)
            and (
                _axis_bound(
                    motion_carrier,
                    contact.frame_id,
                    QuantityComponent.tangential,
                    1,
                )
                or _axis_bound(
                    motion_carrier,
                    contact.frame_id,
                    QuantityComponent.tangential,
                    -1,
                )
            )
        )
        sliding_profile = (
            frictional_contact
            and friction_state is not None
            and friction_state.state is StateValue.sliding
            and body_motion is not None
            and body_motion.state is StateValue.moving
            and carrier_valid
            and _axis_bound(
                friction_force,
                contact.frame_id,
                QuantityComponent.tangential,
                -motion_carrier.direction_sign,
            )
            and len(states) == 4
            and exact_state_quantity_cardinality
            and state_signatures == {
                touching_signature,
                (StateKind.friction, StateValue.sliding, body_id, friction_quantity_ids),
                fixed_signature,
                (
                    StateKind.motion,
                    StateValue.moving,
                    body_id,
                    frozenset({motion_carrier.quantity_id}),
                ),
            }
        )
        axis_signature = lambda value: {
            (item.axis, item.direction.kind, getattr(item.direction, "frame_id", None),
             getattr(item.direction, "axis", None), getattr(item.direction, "sign", None))
            for item in value.axes
        }
        known = (
            getattr(mass, "known_si_value", None),
            getattr(gravity, "known_si_value", None),
            getattr(angle, "known_si_value", None),
        )
        projected = (gravity_tangent, gravity_normal, normal_force, normal_acceleration)
        if (
            normal_force is None
            or normal_acceleration is None
            or len(tangent_accelerations) != 1
            or not (frictionless_profile or sticking_profile or sliding_profile)
            or any(item.expression is not None or not item.evidence_refs for item in states)
            or frame.frame_type is not ReferenceFrameType.tangential_normal
            or getattr(frame.origin, "entity_id", None) != incline_id
            or frame.translating_with_entity_id is not None
            or frame.rotating_about_point_id is not None
            or not frame.evidence_refs
            or len(frame.axes) != 2
            or axis_signature(frame) != {
                (AxisName.tangent, "axis", frame.frame_id, AxisName.tangent, 1),
                (AxisName.normal, "axis", frame.frame_id, AxisName.normal, 1),
            }
            or parent.frame_type is not ReferenceFrameType.cartesian_2d
            or getattr(parent.origin, "kind", None) != "world"
            or parent.parent_frame_id is not None
            or parent.translating_with_entity_id is not None
            or parent.rotating_about_point_id is not None
            or len(parent.axes) != 2
            or axis_signature(parent) != {
                (AxisName.x, "axis", parent.frame_id, AxisName.x, 1),
                (AxisName.y, "axis", parent.frame_id, AxisName.y, 1),
            }
            or angle.role is not QuantityRole.angle
            or angle.subject_id != incline_id
            or any(
                item.shape is not QuantityShape.scalar
                for item in (mass, gravity, angle)
            )
            or any(
                item.point_id is not None
                or item.frame_id is not None
                or item.interval_id is not None
                or item.event_id is not None
                for item in (mass, gravity, angle)
            )
            or mass.component not in {
                QuantityComponent.magnitude,
                QuantityComponent.unspecified,
            }
            or mass.direction_bound
            or angle.component not in {
                QuantityComponent.magnitude,
                QuantityComponent.unspecified,
            }
            or angle.direction_bound
            or gravity.component not in {
                QuantityComponent.magnitude,
                QuantityComponent.unspecified,
            }
            or gravity.direction_bound
            or any(not item.evidence_ids for item in (mass, gravity, angle, *projected))
            or any(
                item.symbol_id is None
                or item.known_si_value is not None
                or item.event_id is not None
                for item in projected
            )
            or any(not isinstance(value, float) or not math.isfinite(value) for value in known)
            or mass.known_si_value <= 0.0
            or gravity.known_si_value <= 0.0
            or not 0.0 <= angle.known_si_value <= math.pi / 2.0
            or any(angle.dimension.model_dump(mode="python").values())
            or mass.dimension.plus(gravity.dimension) != gravity_tangent.dimension
            or not (
                gravity_tangent.dimension
                == gravity_normal.dimension
                == normal_force.dimension
            )
            or mass.dimension.plus(normal_acceleration.dimension) != normal_force.dimension
            or mass.dimension.plus(tangent_accelerations[0].dimension)
            != gravity_tangent.dimension
        ):
            continue
        state_ids = tuple(item.state_condition_id for item in states)
        for rule_id, force, trig_value in (
            (
                "incline_gravity_tangent_projection",
                gravity_tangent,
                math.sin(angle.known_si_value),
            ),
            (
                "incline_gravity_normal_projection",
                gravity_normal,
                math.cos(angle.known_si_value),
            ),
        ):
            projection = Multiply(
                factors=(
                    mass.expression,
                    gravity.expression,
                    LiteralNode(value=trig_value, dimension=angle.dimension),
                ),
                dimension=force.dimension,
            )
            emitted.append(_emit(
                context, rule_id, Equality(left=force.expression, right=projection),
                (force, mass, gravity, angle),
                extra_entity_ids=tuple(gravity_link.participant_ids),
            ))
        emitted.append(_emit(
            context,
            "fixed_contact_no_penetration",
            Equality(
                left=normal_acceleration.expression,
                right=LiteralNode(value=0.0, dimension=normal_acceleration.dimension),
            ),
            (normal_acceleration, normal_force),
            constraint_ids=state_ids,
            extra_entity_ids=tuple(contact.participant_ids),
        ))
        if sticking_profile:
            emitted.append(_emit(
                context,
                "incline_sticking_static_acceleration",
                Equality(
                    left=_signed(tangent_accelerations[0]),
                    right=LiteralNode(
                        value=0.0,
                        dimension=tangent_accelerations[0].dimension,
                    ),
                ),
                (
                    tangent_accelerations[0],
                    friction_force,
                    normal_force,
                    coefficient,
                ),
                constraint_ids=state_ids,
                extra_entity_ids=tuple(contact.participant_ids),
            ))
        if frictionless_profile:
            emitted.append(_emit(
                context,
                "contact_normal_bound",
                Inequality(
                    relation=InequalityRelation.ge,
                    left=normal_force.expression,
                    right=LiteralNode(value=0.0, dimension=normal_force.dimension),
                ),
                (normal_force,),
                constraint_ids=state_ids,
                extra_entity_ids=tuple(contact.participant_ids),
            ))
    return emitted


def _newton_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    entity_kinds = {entity.entity_id: entity.primitive for entity in context.entities}
    linked_force_ids = {
        quantity_id
        for interaction in context.interactions
        for quantity_id in interaction.quantity_ids
        if interaction.kind
        in {
            InteractionKind.contact,
            InteractionKind.gravity,
            InteractionKind.spring,
            InteractionKind.damping,
            InteractionKind.rope_tension,
            InteractionKind.joint_reaction,
            InteractionKind.applied_force,
            InteractionKind.field,
            InteractionKind.gear_contact,
        }
    }
    for acceleration in _by_role(context, QuantityRole.acceleration):
        if entity_kinds.get(acceleration.subject_id) not in {
            EntityPrimitive.particle,
            EntityPrimitive.rigid_body,
            EntityPrimitive.mass_center,
            EntityPrimitive.body_component,
        }:
            continue
        masses = tuple(
            q
            for q in _by_role(context, QuantityRole.mass)
            if _scope_compatible(acceleration, q) and q.shape is QuantityShape.scalar
        )
        forces = tuple(
            q
            for q in _by_role(context, QuantityRole.force)
            if q.subject_id == acceleration.subject_id
            and q.quantity_id in linked_force_ids
            and _scope_compatible(acceleration, q)
            and _shape_compatible(acceleration, q)
        )
        if len(masses) != 1 or not forces:
            continue
        if len(forces) > 1 and (
            not all(force.direction_bound for force in forces)
            or any(
                not _component_compatible(forces[0], force)
                for force in forces[1:]
            )
        ):
            continue
        mass = masses[0]
        force_sum = _sum_terms(forces)
        inertial = Multiply(
            factors=(mass.expression, _signed(acceleration)),
            dimension=forces[0].dimension,
        )
        emitted.append(
            _emit(
                context,
                "particle_newton_second",
                Equality(left=force_sum, right=inertial),
                (acceleration, mass, *forces),
            )
        )
    return emitted


def _primitive_interaction_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    incline_hanging_profile = _fixed_pulley_incline_contact_profile(context)
    entity_kinds = {item.entity_id: item.primitive for item in context.entities}
    for interaction in sorted(context.interactions, key=lambda item: item.interaction_id):
        linked = _interaction_quantities(context, interaction.interaction_id)
        by_role = {role: tuple(q for q in linked if q.role is role) for role in QuantityRole}
        if interaction.kind is InteractionKind.gravity:
            for force in by_role[QuantityRole.force]:
                masses = tuple(q for q in by_role[QuantityRole.mass] if q.subject_id == force.subject_id)
                gravities = by_role[QuantityRole.gravity]
                if (
                    len(masses) == len(gravities) == 1
                    and masses[0].shape is QuantityShape.scalar
                    and force.shape is gravities[0].shape
                    and force.component
                    not in {
                        QuantityComponent.tangential,
                        QuantityComponent.normal,
                    }
                ):
                    product = Multiply(
                        factors=(masses[0].expression, gravities[0].expression),
                        dimension=force.dimension,
                    )
                    emitted.append(
                        _emit(
                            context,
                            "particle_weight",
                            # The force symbol is a magnitude.  Its axis sign is
                            # applied once, when Newton sums force components.
                            Equality(left=force.expression, right=product),
                            (force, masses[0], gravities[0]),
                            extra_entity_ids=tuple(interaction.participant_ids),
                        )
                    )
            energies = by_role[QuantityRole.energy]
            masses = by_role[QuantityRole.mass]
            gravities = by_role[QuantityRole.gravity]
            heights = by_role[QuantityRole.height]
            if (
                len(energies) == len(masses) == len(gravities) == len(heights) == 1
                and all(
                    item.shape is QuantityShape.scalar
                    for item in (energies[0], masses[0], gravities[0], heights[0])
                )
            ):
                potential = Multiply(
                    factors=(masses[0].expression, gravities[0].expression, heights[0].expression),
                    dimension=energies[0].dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "gravity_potential",
                        Equality(left=energies[0].expression, right=potential),
                        (energies[0], masses[0], gravities[0], heights[0]),
                        extra_entity_ids=tuple(interaction.participant_ids),
                    )
                )
        elif interaction.kind is InteractionKind.spring:
            for force in by_role[QuantityRole.force]:
                stiffness = by_role[QuantityRole.stiffness]
                displacement = by_role[QuantityRole.displacement]
                if (
                    len(stiffness) == len(displacement) == 1
                    and stiffness[0].shape is QuantityShape.scalar
                    and _shape_compatible(force, displacement[0])
                    and _scope_compatible(force, displacement[0])
                ):
                    restoring = Negate(
                        operand=Multiply(
                            factors=(stiffness[0].expression, displacement[0].expression),
                            dimension=force.dimension,
                        ),
                        dimension=force.dimension,
                    )
                    emitted.append(
                        _emit(
                            context,
                            "spring_force",
                            Equality(left=_signed(force), right=restoring),
                            (force, stiffness[0], displacement[0]),
                            extra_entity_ids=tuple(interaction.participant_ids),
                        )
                    )
            energies = by_role[QuantityRole.energy]
            stiffness = by_role[QuantityRole.stiffness]
            displacement = by_role[QuantityRole.displacement]
            if (
                len(energies) == len(stiffness) == len(displacement) == 1
                and all(
                    item.shape is QuantityShape.scalar
                    for item in (energies[0], stiffness[0], displacement[0])
                )
            ):
                squared = Power(
                    base=displacement[0].expression,
                    exponent=LiteralNode(value=2.0),
                )
                potential = Multiply(
                    factors=(LiteralNode(value=0.5), stiffness[0].expression, squared),
                    dimension=energies[0].dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "spring_potential",
                        Equality(left=energies[0].expression, right=potential),
                        (energies[0], stiffness[0], displacement[0]),
                        extra_entity_ids=tuple(interaction.participant_ids),
                    )
                )
        elif interaction.kind is InteractionKind.damping:
            for force in by_role[QuantityRole.force]:
                damping = by_role[QuantityRole.damping]
                velocity = by_role[QuantityRole.velocity]
                if (
                    len(damping) == len(velocity) == 1
                    and damping[0].shape is QuantityShape.scalar
                    and _shape_compatible(force, velocity[0])
                    and _scope_compatible(force, velocity[0])
                ):
                    resisting = Negate(
                        operand=Multiply(
                            factors=(damping[0].expression, velocity[0].expression),
                            dimension=force.dimension,
                        ),
                        dimension=force.dimension,
                    )
                    emitted.append(
                        _emit(
                            context,
                            "damper_force",
                            Equality(left=_signed(force), right=resisting),
                            (force, damping[0], velocity[0]),
                            extra_entity_ids=tuple(interaction.participant_ids),
                        )
                    )
        elif interaction.kind is InteractionKind.contact:
            if (
                len(interaction.participant_ids) != 2
                or not interaction.point_ids
                or interaction.frame_id is None
            ):
                continue
            coefficients = by_role[QuantityRole.coefficient_friction]
            normal = tuple(q for q in by_role[QuantityRole.force] if q.component is QuantityComponent.normal)
            tangent = tuple(q for q in by_role[QuantityRole.force] if q.component is QuantityComponent.tangential)
            normal_accelerations = tuple(
                q
                for q in by_role[QuantityRole.acceleration]
                if q.component is QuantityComponent.normal
            )
            incline_body_id = _one(
                item
                for item in interaction.participant_ids
                if entity_kinds.get(item) is EntityPrimitive.particle
            )
            incline_id = _one(
                item
                for item in interaction.participant_ids
                if entity_kinds.get(item) is EntityPrimitive.incline
            )
            incline_contact = incline_body_id is not None and incline_id is not None
            states = tuple(
                state
                for state in context.state_conditions
                if state.kind is StateKind.friction
                and state.state in {StateValue.sticking, StateValue.sliding}
                and state.subject_id in interaction.participant_ids
                and state.interval_id == interaction.interval_id
                and state.event_id == interaction.event_id
                and state.evidence_refs
            )
            if not (
                len(coefficients) == len(normal) == len(tangent) == len(states) == 1
                and all(item.shape is QuantityShape.scalar for item in (coefficients[0], normal[0], tangent[0]))
                and normal[0].frame_id == tangent[0].frame_id == interaction.frame_id
                and normal[0].interval_id == tangent[0].interval_id == interaction.interval_id
                and normal[0].event_id == tangent[0].event_id == interaction.event_id
                and normal[0].point_id in interaction.point_ids
                and tangent[0].point_id in interaction.point_ids
            ):
                continue
            state = states[0]
            scoped_ids = set(state.quantity_ids)
            used_ids = {item.quantity_id for item in (coefficients[0], normal[0], tangent[0])}
            if scoped_ids and not used_ids.issubset(scoped_ids):
                continue
            state_ids = (state.state_condition_id,)
            friction_quantities: tuple[BoundQuantity, ...] = (
                tangent[0],
                normal[0],
                coefficients[0],
            )
            if incline_contact:
                touching = tuple(
                    item
                    for item in context.state_conditions
                    if item.kind is StateKind.contact
                    and item.state is StateValue.touching
                    and item.subject_id == incline_body_id
                    and item.interval_id == interaction.interval_id
                    and item.event_id == interaction.event_id
                    and set(item.quantity_ids)
                    == {normal[0].quantity_id, normal_accelerations[0].quantity_id}
                    and len(item.quantity_ids) == 2
                    and item.expression is None
                    and item.evidence_refs
                ) if len(normal_accelerations) == 1 else ()
                fixed = tuple(
                    item
                    for item in context.state_conditions
                    if item.kind is StateKind.motion
                    and item.state is StateValue.at_rest
                    and item.subject_id == incline_id
                    and item.interval_id == interaction.interval_id
                    and item.event_id == interaction.event_id
                    and not item.quantity_ids
                    and item.expression is None
                    and item.evidence_refs
                )
                body_motion = tuple(
                    item
                    for item in context.state_conditions
                    if item.kind is StateKind.motion
                    and item.subject_id == incline_body_id
                    and item.interval_id == interaction.interval_id
                    and item.event_id == interaction.event_id
                    and item.state
                    in {
                        StateValue.at_rest,
                        StateValue.moving,
                    }
                    and item.expression is None
                    and item.evidence_refs
                )
                incline_states = tuple(
                    item
                    for item in context.state_conditions
                    if item.interval_id == interaction.interval_id
                    and item.event_id == interaction.event_id
                    and item.subject_id in {incline_body_id, incline_id}
                    and item.kind
                    in {
                        StateKind.contact,
                        StateKind.friction,
                        StateKind.motion,
                    }
                )
                coefficient = coefficients[0]
                exact_contact = (
                    len(interaction.point_ids) == 1
                    and bool(interaction.evidence_refs)
                    and len(interaction.quantity_ids) == 4
                    and len(normal_accelerations) == 1
                    and set(interaction.quantity_ids)
                    == {
                        tangent[0].quantity_id,
                        normal[0].quantity_id,
                        normal_accelerations[0].quantity_id,
                        coefficient.quantity_id,
                    }
                    and len(touching) == len(fixed) == len(body_motion) == 1
                    and len(incline_states) == 4
                    and {
                        item.state_condition_id for item in incline_states
                    }
                    == {
                        state.state_condition_id,
                        touching[0].state_condition_id,
                        fixed[0].state_condition_id,
                        body_motion[0].state_condition_id,
                    }
                    and scoped_ids == used_ids
                    and len(state.quantity_ids) == len(used_ids) == 3
                    and state.expression is None
                    and state.subject_id == incline_body_id
                    and normal[0].subject_id == tangent[0].subject_id == incline_body_id
                    and normal[0].point_id == tangent[0].point_id == interaction.point_ids[0]
                    and normal[0].symbol_id is not None
                    and normal[0].known_si_value is None
                    and bool(normal[0].evidence_ids)
                    and _axis_bound(
                        normal[0],
                        interaction.frame_id,
                        QuantityComponent.normal,
                        1,
                    )
                    and normal_accelerations[0].subject_id == incline_body_id
                    and normal_accelerations[0].point_id is None
                    and normal_accelerations[0].interval_id == interaction.interval_id
                    and normal_accelerations[0].event_id == interaction.event_id
                    and normal_accelerations[0].symbol_id is not None
                    and normal_accelerations[0].known_si_value is None
                    and bool(normal_accelerations[0].evidence_ids)
                    and _axis_bound(
                        normal_accelerations[0],
                        interaction.frame_id,
                        QuantityComponent.normal,
                        1,
                    )
                    and coefficient.subject_id == incline_body_id
                    and coefficient.point_id is None
                    and coefficient.frame_id is None
                    and coefficient.interval_id is None
                    and coefficient.event_id is None
                    and coefficient.shape is QuantityShape.scalar
                    and coefficient.component
                    in {
                        QuantityComponent.magnitude,
                        QuantityComponent.unspecified,
                    }
                    and not coefficient.direction_bound
                    and coefficient.symbol_id is not None
                    and isinstance(coefficient.known_si_value, float)
                    and math.isfinite(coefficient.known_si_value)
                    and coefficient.known_si_value >= 0.0
                    and bool(coefficient.evidence_ids)
                    and not any(
                        coefficient.dimension.model_dump(mode="python").values()
                    )
                    and tangent[0].symbol_id is not None
                    and tangent[0].known_si_value is None
                    and bool(tangent[0].evidence_ids)
                    and tangent[0].dimension == normal[0].dimension
                )
                motion = body_motion[0] if len(body_motion) == 1 else None
                if state.state is StateValue.sticking:
                    regime_valid = (
                        motion is not None
                        and motion.state is StateValue.at_rest
                        and not motion.quantity_ids
                        and (
                            _axis_bound(
                                tangent[0],
                                interaction.frame_id,
                                QuantityComponent.tangential,
                                -1,
                            )
                            or (
                                incline_hanging_profile is not None
                                and incline_hanging_profile.incline_body_id
                                == incline_body_id
                                and tangent[0].direction_sign in {-1, 1}
                                and _axis_bound(
                                    tangent[0],
                                    interaction.frame_id,
                                    QuantityComponent.tangential,
                                    tangent[0].direction_sign,
                                )
                            )
                        )
                    )
                else:
                    carrier = (
                        next(
                            (
                                item
                                for item in context.quantities
                                if item.quantity_id == motion.quantity_ids[0]
                            ),
                            None,
                        )
                        if motion is not None and len(motion.quantity_ids) == 1
                        else None
                    )
                    carrier_valid = (
                        carrier is not None
                        and carrier.role is QuantityRole.velocity
                        and carrier.dimension == DimensionVector(length=1, time=-1)
                        and carrier.subject_id == incline_body_id
                        and carrier.point_id is None
                        and carrier.frame_id == interaction.frame_id
                        and carrier.interval_id == interaction.interval_id
                        and carrier.event_id == interaction.event_id
                        and carrier.shape is QuantityShape.scalar
                        and carrier.symbol_id is not None
                        and isinstance(carrier.known_si_value, float)
                        and math.isfinite(carrier.known_si_value)
                        and carrier.known_si_value > 0.0
                        and bool(carrier.evidence_ids)
                        and (
                            _axis_bound(
                                carrier,
                                interaction.frame_id,
                                QuantityComponent.tangential,
                                1,
                            )
                            or _axis_bound(
                                carrier,
                                interaction.frame_id,
                                QuantityComponent.tangential,
                                -1,
                            )
                        )
                    )
                    regime_valid = (
                        motion is not None
                        and motion.state is StateValue.moving
                        and carrier_valid
                        and _axis_bound(
                            tangent[0],
                            interaction.frame_id,
                            QuantityComponent.tangential,
                            -carrier.direction_sign,
                        )
                    )
                    if carrier_valid:
                        friction_quantities = (*friction_quantities, carrier)
                if not exact_contact or not regime_valid:
                    continue
                state_ids = tuple(sorted({
                    state.state_condition_id,
                    touching[0].state_condition_id,
                    fixed[0].state_condition_id,
                    motion.state_condition_id,
                }))
            bound = Multiply(
                factors=(coefficients[0].expression, normal[0].expression),
                dimension=tangent[0].dimension,
            )
            emitted.append(
                _emit(
                    context,
                    "contact_normal_bound",
                    Inequality(
                        relation=InequalityRelation.ge,
                        left=normal[0].expression,
                        right=LiteralNode(value=0.0, dimension=normal[0].dimension),
                    ),
                    (normal[0],),
                    constraint_ids=state_ids,
                    extra_entity_ids=tuple(interaction.participant_ids),
                )
            )
            if state.state is StateValue.sticking:
                for left in (
                    _signed(tangent[0]),
                    Negate(operand=_signed(tangent[0]), dimension=tangent[0].dimension),
                ):
                    emitted.append(
                        _emit(
                            context,
                            "contact_friction_bound",
                            Inequality(
                                relation=InequalityRelation.le,
                                left=left,
                                right=bound,
                            ),
                            friction_quantities,
                            constraint_ids=state_ids,
                            extra_entity_ids=tuple(interaction.participant_ids),
                        )
                    )
            elif tangent[0].direction_bound:
                emitted.append(
                    _emit(
                        context,
                        "contact_sliding_friction",
                        Equality(left=tangent[0].expression, right=bound),
                        friction_quantities,
                        constraint_ids=state_ids,
                        extra_entity_ids=tuple(interaction.participant_ids),
                    )
                )
    return emitted


def _work_energy_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    half = LiteralNode(value=0.5)
    rigid_ids = {
        entity.entity_id
        for entity in context.entities
        if entity.primitive in {EntityPrimitive.rigid_body, EntityPrimitive.pulley}
    }
    frame_types = {frame.frame_id: frame.frame_type for frame in context.reference_frames}
    work_links = tuple(
        set(interaction.quantity_ids)
        for interaction in context.interactions
        if interaction.kind
        in {
            InteractionKind.applied_force,
            InteractionKind.contact,
            InteractionKind.field,
            InteractionKind.spring,
        }
    )
    power_links = tuple(
        set(interaction.quantity_ids)
        for interaction in context.interactions
        if interaction.kind
        in {
            InteractionKind.applied_force,
            InteractionKind.contact,
            InteractionKind.field,
            InteractionKind.spring,
            InteractionKind.damping,
        }
    )
    for work in _by_role(context, QuantityRole.work):
        if work.shape is not QuantityShape.scalar:
            continue
        for force in _by_role(context, QuantityRole.force):
            if not _scope_compatible(work, force):
                continue
            for displacement in _by_role(context, QuantityRole.displacement):
                if (
                    not _scope_compatible(work, displacement)
                    or not _scope_compatible(force, displacement)
                    or not _shape_compatible(force, displacement)
                ):
                    continue
                if (
                    work.quantity_id is None
                    or force.quantity_id is None
                    or displacement.quantity_id is None
                    or not any(
                        {work.quantity_id, force.quantity_id, displacement.quantity_id}.issubset(link)
                        for link in work_links
                    )
                ):
                    continue
                constant_authority = context.approved_assumptions(
                    "constant_force", force.subject_id, work.interval_id
                )
                if not constant_authority:
                    continue
                product = (
                    Dot(left=force.expression, right=displacement.expression, dimension=work.dimension)
                    if force.shape is QuantityShape.vector
                    else Multiply(factors=(force.expression, displacement.expression), dimension=work.dimension)
                )
                emitted.append(
                    _emit(
                        context,
                        "force_work",
                        Equality(left=work.expression, right=product),
                        (work, force, displacement),
                        assumption_ids=constant_authority,
                    )
                )
    for interval in context.motion_intervals:
        if interval.start_event_id is None or interval.end_event_id is None:
            continue
        for subject_id in interval.subject_ids:
            masses = tuple(q for q in _by_role(context, QuantityRole.mass) if q.subject_id == subject_id and q.shape is QuantityShape.scalar)
            starts = tuple(
                q
                for role in (QuantityRole.velocity, QuantityRole.speed)
                for q in _by_role(context, role)
                if q.subject_id == subject_id
                and q.event_id == interval.start_event_id
                and _is_full_translational_speed(q, frame_types)
            )
            ends = tuple(
                q
                for role in (QuantityRole.velocity, QuantityRole.speed)
                for q in _by_role(context, role)
                if q.subject_id == subject_id
                and q.event_id == interval.end_event_id
                and _is_full_translational_speed(q, frame_types)
            )
            works = tuple(q for q in _by_role(context, QuantityRole.work) if q.subject_id == subject_id and q.interval_id == interval.interval_id and q.shape is QuantityShape.scalar)
            if (
                len(masses) == len(starts) == len(ends) == len(works) == 1
                and starts[0].shape is ends[0].shape
                and _component_compatible(starts[0], ends[0])
            ):
                start_squared = (
                    Dot(left=starts[0].expression, right=starts[0].expression)
                    if starts[0].shape is QuantityShape.vector
                    else Power(base=starts[0].expression, exponent=LiteralNode(value=2.0))
                )
                end_squared = (
                    Dot(left=ends[0].expression, right=ends[0].expression)
                    if ends[0].shape is QuantityShape.vector
                    else Power(base=ends[0].expression, exponent=LiteralNode(value=2.0))
                )
                energy_change = Multiply(
                    factors=(
                        LiteralNode(value=0.5),
                        masses[0].expression,
                        Subtract(left=end_squared, right=start_squared),
                    ),
                    dimension=works[0].dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "particle_work_energy",
                        Equality(left=works[0].expression, right=energy_change),
                        (works[0], masses[0], starts[0], ends[0]),
                    )
                )
    for power in _by_role(context, QuantityRole.power):
        if power.shape is not QuantityShape.scalar:
            continue
        for force in _by_role(context, QuantityRole.force):
            if not _scope_compatible(power, force):
                continue
            if (
                power.quantity_id is None
                or force.quantity_id is None
                or not any({power.quantity_id, force.quantity_id}.issubset(link) for link in power_links)
            ):
                continue
            for velocity in _by_role(context, QuantityRole.velocity):
                if (
                    not _scope_compatible(power, velocity)
                    or not _scope_compatible(force, velocity)
                    or force.shape is not velocity.shape
                ):
                    continue
                instantaneous = (
                    Dot(left=force.expression, right=velocity.expression, dimension=power.dimension)
                    if force.shape is QuantityShape.vector
                    else Multiply(factors=(force.expression, velocity.expression), dimension=power.dimension)
                )
                emitted.append(
                    _emit(
                        context,
                        "mechanical_power",
                        Equality(left=power.expression, right=instantaneous),
                        (power, force, velocity),
                    )
                )
        for work in _by_role(context, QuantityRole.work):
            if not _scope_compatible(power, work):
                continue
            durations = tuple(q for q in _by_role(context, QuantityRole.duration) if _scope_compatible(power, q) and q.shape is QuantityShape.scalar)
            if len(durations) == 1:
                emitted.append(
                    _emit(
                        context,
                        "average_power",
                        Equality(
                            left=power.expression,
                            right=Divide(
                                numerator=work.expression,
                                denominator=durations[0].expression,
                                dimension=power.dimension,
                            ),
                        ),
                        (power, work, durations[0]),
                    )
                )
    for energy in _by_role(context, QuantityRole.energy):
        if energy.shape is not QuantityShape.scalar or energy.subject_id in rigid_ids:
            continue
        kinetic_authority = context.approved_assumptions(
            "kinetic_energy", energy.subject_id, energy.interval_id
        )
        if not kinetic_authority:
            continue
        for mass in _by_role(context, QuantityRole.mass):
            if not _scope_compatible(energy, mass) or mass.shape is not QuantityShape.scalar:
                continue
            velocities = tuple(
                q
                for role in (QuantityRole.velocity, QuantityRole.speed)
                for q in _by_role(context, role)
                if _scope_compatible(energy, q)
                and _is_full_translational_speed(q, frame_types)
            )
            if len(velocities) != 1:
                continue
            velocity = velocities[0]
            squared = (
                Dot(left=velocity.expression, right=velocity.expression)
                if velocity.shape is QuantityShape.vector
                else Power(base=velocity.expression, exponent=LiteralNode(value=2.0))
            )
            kinetic = Multiply(factors=(half, mass.expression, squared), dimension=energy.dimension)
            emitted.append(
                _emit(
                    context,
                    "kinetic_energy",
                    Equality(left=energy.expression, right=kinetic),
                    (energy, mass, velocity),
                    assumption_ids=kinetic_authority,
                )
            )
    return emitted


def _momentum_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    for momentum in _by_role(context, QuantityRole.momentum):
        for mass in _by_role(context, QuantityRole.mass):
            if not _scope_compatible(momentum, mass) or mass.shape is not QuantityShape.scalar:
                continue
            for velocity in _by_role(context, QuantityRole.velocity):
                if not _scope_compatible(momentum, velocity) or not _shape_compatible(momentum, velocity):
                    continue
                product = Multiply(factors=(mass.expression, velocity.expression), dimension=momentum.dimension)
                emitted.append(_emit(context, "linear_momentum", Equality(left=momentum.expression, right=product), (momentum, mass, velocity)))
    for impulse in _by_role(context, QuantityRole.impulse):
        constant_force = context.approved_assumptions(
            "constant_force", impulse.subject_id, impulse.interval_id
        )
        if not constant_force:
            continue
        for force in _by_role(context, QuantityRole.force):
            if not _scope_compatible(impulse, force) or not _shape_compatible(impulse, force):
                continue
            for duration in _by_role(context, QuantityRole.duration):
                if not _scope_compatible(impulse, duration) or duration.shape is not QuantityShape.scalar:
                    continue
                product = Multiply(factors=(force.expression, duration.expression), dimension=impulse.dimension)
                emitted.append(
                    _emit(
                        context,
                        "linear_impulse",
                        Equality(left=impulse.expression, right=product),
                        (impulse, force, duration),
                        assumption_ids=constant_force,
                    )
                )
    for interval in context.motion_intervals:
        if interval.start_event_id is None or interval.end_event_id is None:
            continue
        for subject_id in interval.subject_ids:
            masses = tuple(
                q
                for q in _by_role(context, QuantityRole.mass)
                if q.subject_id == subject_id and q.shape is QuantityShape.scalar
            )
            starts = tuple(
                q
                for q in _by_role(context, QuantityRole.velocity)
                if q.subject_id == subject_id and q.event_id == interval.start_event_id
            )
            ends = tuple(
                q
                for q in _by_role(context, QuantityRole.velocity)
                if q.subject_id == subject_id and q.event_id == interval.end_event_id
            )
            impulses = tuple(
                q
                for q in _by_role(context, QuantityRole.impulse)
                if q.subject_id == subject_id and q.interval_id == interval.interval_id
            )
            if (
                len(masses) == len(starts) == len(ends) == len(impulses) == 1
                and _shape_compatible(starts[0], ends[0], impulses[0])
                and _component_compatible(starts[0], ends[0])
                and _component_compatible(starts[0], impulses[0])
            ):
                change = Multiply(
                    factors=(
                        masses[0].expression,
                        Subtract(left=ends[0].expression, right=starts[0].expression),
                    ),
                    dimension=impulses[0].dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "linear_impulse_momentum",
                        Equality(left=impulses[0].expression, right=change),
                        (impulses[0], masses[0], starts[0], ends[0]),
                    )
                )
    for interaction in context.interactions:
        if (
            interaction.kind is not InteractionKind.collision
            or len(interaction.participant_ids) != 2
            or interaction.interval_id is None
            or interaction.frame_id is None
        ):
            continue
        participants = tuple(interaction.participant_ids)
        interval = next(
            (item for item in context.motion_intervals if item.interval_id == interaction.interval_id),
            None,
        )
        if interval is None or interval.start_event_id is None or interval.end_event_id is None:
            continue
        start_events = tuple(
            event.event_id
            for event in context.events
            if event.event_id == interval.start_event_id
            and event.kind.value == "collision_start"
            and set(event.subject_ids) == set(participants)
            and event.interval_ids == (interaction.interval_id,)
        )
        end_events = tuple(
            event.event_id
            for event in context.events
            if event.event_id == interval.end_event_id
            and event.kind.value == "collision_end"
            and set(event.subject_ids) == set(participants)
            and event.interval_ids == (interaction.interval_id,)
        )
        if len(start_events) != 1 or len(end_events) != 1:
            continue
        before: list[BoundQuantity] = []
        after: list[BoundQuantity] = []
        masses: list[BoundQuantity] = []
        for participant in participants:
            before_items = tuple(
                q
                for q in _by_role(context, QuantityRole.velocity)
                if q.subject_id == participant
                and q.event_id == start_events[0]
                and q.interval_id == interaction.interval_id
                and q.frame_id == interaction.frame_id
                and q.quantity_id in interaction.quantity_ids
                and q.shape is QuantityShape.scalar
                and q.component not in {QuantityComponent.unspecified, QuantityComponent.magnitude}
            )
            after_items = tuple(
                q
                for q in _by_role(context, QuantityRole.velocity)
                if q.subject_id == participant
                and q.event_id == end_events[0]
                and q.interval_id == interaction.interval_id
                and q.frame_id == interaction.frame_id
                and q.quantity_id in interaction.quantity_ids
                and q.shape is QuantityShape.scalar
            )
            mass_items = tuple(
                q
                for q in _by_role(context, QuantityRole.mass)
                if q.subject_id == participant
                and q.shape is QuantityShape.scalar
                and q.quantity_id in interaction.quantity_ids
            )
            if len(before_items) != 1 or len(after_items) != 1 or len(mass_items) != 1:
                break
            before.append(before_items[0])
            after.append(after_items[0])
            masses.append(mass_items[0])
        if len(before) != 2:
            continue
        if not (
            _component_compatible(before[0], before[1])
            and _component_compatible(before[0], after[0])
            and _component_compatible(before[0], after[1])
        ):
            continue
        conservation_authority = tuple(
            sorted(
                {
                    assumption_id
                    for participant_id in participants
                    for assumption_id in context.approved_assumptions(
                        "external_impulse_negligible",
                        participant_id,
                        interaction.interval_id,
                    )
                }
            )
        )
        if conservation_authority:
            before_sum = Add(
                terms=tuple(
                    Multiply(factors=(mass.expression, velocity.expression))
                    for mass, velocity in zip(masses, before)
                )
            )
            after_sum = Add(
                terms=tuple(
                    Multiply(factors=(mass.expression, velocity.expression))
                    for mass, velocity in zip(masses, after)
                )
            )
            emitted.append(
                _emit(
                    context,
                    "system_momentum_conservation",
                    Equality(left=before_sum, right=after_sum),
                    tuple((*masses, *before, *after)),
                    assumption_ids=conservation_authority,
                    extra_entity_ids=participants,
                )
            )
        coefficients = tuple(
            q
            for q in _by_role(context, QuantityRole.coefficient_restitution)
            if q.quantity_id in interaction.quantity_ids
            and q.shape is QuantityShape.scalar
            and q.frame_id in {None, interaction.frame_id}
            and q.interval_id in {None, interaction.interval_id}
        )
        if len(coefficients) == 1:
            separation = Subtract(left=after[1].expression, right=after[0].expression)
            approach = Subtract(left=before[1].expression, right=before[0].expression)
            restitution = Negate(
                operand=Multiply(factors=(coefficients[0].expression, approach)),
            )
            emitted.append(
                _emit(
                    context,
                    "direct_restitution",
                    Equality(left=separation, right=restitution),
                    tuple((*before, *after, coefficients[0])),
                    extra_entity_ids=participants,
                )
            )
    return emitted


def _rigid_point_radius_authority(
    context: LawContext,
    rigid_id: str,
    point_id: str,
    frame_id: str | None,
    interval_id: str | None,
    event_id: str | None,
) -> tuple[BoundQuantity, object] | None:
    compatible_pairs: list[tuple[BoundQuantity, object]] = []
    for radius in _by_role(context, QuantityRole.radius):
        if (
            radius.subject_id != rigid_id
            or radius.point_id != point_id
            or radius.frame_id != frame_id
            or radius.shape is not QuantityShape.scalar
            or radius.quantity_id is None
            or not radius.evidence_ids
            or (
                (radius.interval_id, radius.event_id) != (None, None)
                and (radius.interval_id, radius.event_id) != (interval_id, event_id)
            )
        ):
            continue
        relations = tuple(
            relation
            for relation in context.geometry
            if relation.kind.value == "attached"
            and {rigid_id, point_id}.issubset(relation.participant_ids)
            and radius.quantity_id in relation.quantity_ids
            and relation.interval_id in {None, interval_id}
            and relation.evidence_refs
        )
        compatible_pairs.extend((radius, relation) for relation in relations)
    if len(compatible_pairs) != 1:
        return None
    return compatible_pairs[0]


def _rigid_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    rigid_ids = {
        entity.entity_id
        for entity in context.entities
        if entity.primitive in {EntityPrimitive.rigid_body, EntityPrimitive.pulley}
    }
    frame_types = {frame.frame_id: frame.frame_type for frame in context.reference_frames}
    for rigid_id in sorted(rigid_ids):
        centers = tuple(
            point
            for point in context.points
            if point.owner_entity_id == rigid_id and point.role is PointRole.mass_center
        )
        if len(centers) != 1:
            continue
        center_id = centers[0].point_id
        for point in context.points:
            if point.owner_entity_id != rigid_id or point.point_id == center_id:
                continue
            velocity_groups = {
                (q.frame_id, q.interval_id, q.event_id)
                for q in _by_role(context, QuantityRole.velocity)
                if q.subject_id == rigid_id
                and q.point_id == point.point_id
                and q.component is QuantityComponent.tangential
                and q.shape is QuantityShape.scalar
            }
            for frame_id, interval_id, event_id in sorted(
                velocity_groups,
                key=lambda item: tuple(value or "" for value in item),
            ):
                if frame_types.get(frame_id) not in {
                    ReferenceFrameType.cartesian_2d,
                    ReferenceFrameType.tangential_normal,
                }:
                    continue
                scoped_point_velocities = tuple(
                    q
                    for q in _by_role(context, QuantityRole.velocity)
                    if q.subject_id == rigid_id
                    and q.point_id == point.point_id
                    and q.component is QuantityComponent.tangential
                    and q.shape is QuantityShape.scalar
                    and q.frame_id == frame_id
                    and q.interval_id == interval_id
                    and q.event_id == event_id
                )
                center_velocities = tuple(
                    q
                    for q in _by_role(context, QuantityRole.velocity)
                    if q.subject_id == rigid_id
                    and q.point_id == center_id
                    and q.component is QuantityComponent.tangential
                    and q.shape is QuantityShape.scalar
                    and q.frame_id == frame_id
                    and q.interval_id == interval_id
                    and q.event_id == event_id
                )
                angular_velocities = tuple(
                    q
                    for q in _by_role(context, QuantityRole.angular_velocity)
                    if q.subject_id == rigid_id
                    and q.point_id == center_id
                    and q.shape is QuantityShape.scalar
                    and q.frame_id == frame_id
                    and q.interval_id == interval_id
                    and q.event_id == event_id
                )
                radius_authority = _rigid_point_radius_authority(
                    context,
                    rigid_id,
                    point.point_id,
                    frame_id,
                    interval_id,
                    event_id,
                )
                if not (
                    len(scoped_point_velocities)
                    == len(center_velocities)
                    == len(angular_velocities)
                    == 1
                ) or radius_authority is None:
                    continue
                radius, attached = radius_authority
                point_velocity = scoped_point_velocities[0]
                relative = Multiply(
                    factors=(_signed(angular_velocities[0]), radius.expression),
                    dimension=point_velocity.dimension,
                )
                emitted.append(
                    _emit(
                        context,
                        "rigid_point_velocity",
                        Equality(
                            left=_signed(point_velocity),
                            right=Add(
                                terms=(_signed(center_velocities[0]), relative),
                                dimension=point_velocity.dimension,
                            ),
                        ),
                        (point_velocity, center_velocities[0], angular_velocities[0], radius),
                        constraint_ids=(attached.relation_id,),
                        extra_entity_ids=(rigid_id,),
                    )
                )
            for component, law_id, angular_role in (
                (QuantityComponent.tangential, "rigid_point_tangential_acceleration", QuantityRole.angular_acceleration),
                (QuantityComponent.normal, "rigid_point_normal_acceleration", QuantityRole.angular_velocity),
            ):
                acceleration_groups = {
                    (q.frame_id, q.interval_id, q.event_id)
                    for q in _by_role(context, QuantityRole.acceleration)
                    if q.subject_id == rigid_id
                    and q.point_id == point.point_id
                    and q.component is component
                    and q.shape is QuantityShape.scalar
                }
                for frame_id, interval_id, event_id in sorted(
                    acceleration_groups,
                    key=lambda item: tuple(value or "" for value in item),
                ):
                    if frame_types.get(frame_id) not in {
                        ReferenceFrameType.cartesian_2d,
                        ReferenceFrameType.tangential_normal,
                    }:
                        continue
                    scoped_point_accelerations = tuple(
                        q
                        for q in _by_role(context, QuantityRole.acceleration)
                        if q.subject_id == rigid_id
                        and q.point_id == point.point_id
                        and q.component is component
                        and q.shape is QuantityShape.scalar
                        and q.frame_id == frame_id
                        and q.interval_id == interval_id
                        and q.event_id == event_id
                    )
                    center_accelerations = tuple(
                        q
                        for q in _by_role(context, QuantityRole.acceleration)
                        if q.subject_id == rigid_id
                        and q.point_id == center_id
                        and q.component is component
                        and q.shape is QuantityShape.scalar
                        and q.frame_id == frame_id
                        and q.interval_id == interval_id
                        and q.event_id == event_id
                    )
                    angular_items = tuple(
                        q
                        for q in _by_role(context, angular_role)
                        if q.subject_id == rigid_id
                        and q.point_id == center_id
                        and q.shape is QuantityShape.scalar
                        and q.frame_id == frame_id
                        and q.interval_id == interval_id
                        and q.event_id == event_id
                    )
                    radius_authority = _rigid_point_radius_authority(
                        context,
                        rigid_id,
                        point.point_id,
                        frame_id,
                        interval_id,
                        event_id,
                    )
                    if (
                        len(scoped_point_accelerations) != 1
                        or len(center_accelerations) != 1
                        or len(angular_items) != 1
                        or radius_authority is None
                    ):
                        continue
                    radius, attached = radius_authority
                    point_acceleration = scoped_point_accelerations[0]
                    angular_expression = _signed(angular_items[0])
                    if component is QuantityComponent.normal:
                        angular_expression = Power(
                            base=angular_items[0].expression,
                            exponent=LiteralNode(value=2.0),
                        )
                    relative = Multiply(
                        factors=(angular_expression, radius.expression),
                        dimension=point_acceleration.dimension,
                    )
                    emitted.append(
                        _emit(
                            context,
                            law_id,
                            Equality(
                                left=_signed(point_acceleration),
                                right=Add(
                                    terms=(_signed(center_accelerations[0]), relative),
                                    dimension=point_acceleration.dimension,
                                ),
                            ),
                            (
                                point_acceleration,
                                center_accelerations[0],
                                angular_items[0],
                                radius,
                            ),
                            constraint_ids=(attached.relation_id,),
                            extra_entity_ids=(rigid_id,),
                        )
                    )
    for speed in _by_role(context, QuantityRole.speed):
        if speed.subject_id not in rigid_ids or speed.shape is not QuantityShape.scalar:
            continue
        for angular in _by_role(context, QuantityRole.angular_velocity):
            if not _scope_compatible(speed, angular):
                continue
            for radius in _by_role(context, QuantityRole.radius):
                if not _scope_compatible(speed, radius) or any(
                    item.shape is not QuantityShape.scalar for item in (angular, radius)
                ):
                    continue
                product = Multiply(factors=(angular.expression, radius.expression), dimension=speed.dimension)
                emitted.append(_emit(context, "fixed_axis_speed", Equality(left=speed.expression, right=product), (speed, angular, radius)))
    linked_moments = {
        qid
        for interaction in context.interactions
        for qid in interaction.quantity_ids
        if interaction.kind in {InteractionKind.applied_force, InteractionKind.contact, InteractionKind.joint_reaction}
    }
    for angular_acceleration in _by_role(context, QuantityRole.angular_acceleration):
        if angular_acceleration.subject_id not in rigid_ids:
            continue
        inertias = tuple(
            q
            for q in _by_role(context, QuantityRole.moment_of_inertia)
            if _scope_compatible(angular_acceleration, q)
            and q.point_id is not None
            and q.shape is QuantityShape.scalar
        )
        moments = tuple(
            q
            for role in (QuantityRole.moment, QuantityRole.torque)
            for q in _by_role(context, role)
            if q.quantity_id in linked_moments
            and _scope_compatible(angular_acceleration, q)
            and q.point_id is not None
        )
        if len(inertias) != 1 or not moments or any(item.point_id != inertias[0].point_id for item in moments):
            continue
        if inertias[0].shape is not QuantityShape.scalar or any(
            item.shape is not QuantityShape.scalar for item in (angular_acceleration, *moments)
        ):
            continue
        moment_sum = _sum_terms(moments)
        inertial = Multiply(factors=(inertias[0].expression, _signed(angular_acceleration)), dimension=moments[0].dimension)
        emitted.append(_emit(context, "rigid_newton_euler", Equality(left=moment_sum, right=inertial), (angular_acceleration, inertias[0], *moments)))
    for angular_momentum in _by_role(context, QuantityRole.angular_momentum):
        if angular_momentum.subject_id not in rigid_ids or angular_momentum.shape is not QuantityShape.scalar:
            continue
        inertias = tuple(
            q
            for q in _by_role(context, QuantityRole.moment_of_inertia)
            if _scope_compatible(angular_momentum, q)
            and q.shape is QuantityShape.scalar
            and q.point_id is not None
            and q.point_id == angular_momentum.point_id
        )
        angular = tuple(
            q
            for q in _by_role(context, QuantityRole.angular_velocity)
            if _scope_compatible(angular_momentum, q)
            and q.shape is QuantityShape.scalar
            and q.point_id == angular_momentum.point_id
        )
        if len(inertias) == len(angular) == 1:
            emitted.append(
                _emit(
                    context,
                    "rigid_angular_momentum",
                    Equality(
                        left=_signed(angular_momentum),
                        right=Multiply(
                            factors=(inertias[0].expression, _signed(angular[0])),
                            dimension=angular_momentum.dimension,
                        ),
                    ),
                    (angular_momentum, inertias[0], angular[0]),
                )
            )
    for interval in context.motion_intervals:
        if interval.start_event_id is None or interval.end_event_id is None:
            continue
        for rigid_id in sorted(rigid_ids.intersection(interval.subject_ids)):
            starts = tuple(
                q
                for q in _by_role(context, QuantityRole.angular_velocity)
                if q.subject_id == rigid_id
                and q.interval_id == interval.interval_id
                and q.event_id == interval.start_event_id
                and q.shape is QuantityShape.scalar
            )
            ends = tuple(
                q
                for q in _by_role(context, QuantityRole.angular_velocity)
                if q.subject_id == rigid_id
                and q.interval_id == interval.interval_id
                and q.event_id == interval.end_event_id
                and q.shape is QuantityShape.scalar
            )
            inertias = tuple(
                q
                for q in _by_role(context, QuantityRole.moment_of_inertia)
                if q.subject_id == rigid_id and q.shape is QuantityShape.scalar and q.point_id is not None
            )
            impulses = tuple(
                q
                for q in _by_role(context, QuantityRole.impulse)
                if q.subject_id == rigid_id
                and q.interval_id == interval.interval_id
                and q.shape is QuantityShape.scalar
            )
            if not (len(starts) == len(ends) == len(inertias) == len(impulses) == 1):
                continue
            if not (
                _component_compatible(starts[0], ends[0])
                and starts[0].point_id == ends[0].point_id == inertias[0].point_id == impulses[0].point_id
            ):
                continue
            angular_dimension = inertias[0].dimension.plus(starts[0].dimension)
            if angular_dimension is None or impulses[0].dimension != angular_dimension:
                continue
            change = Multiply(
                factors=(
                    inertias[0].expression,
                    Subtract(left=_signed(ends[0]), right=_signed(starts[0])),
                ),
                dimension=angular_dimension,
            )
            emitted.append(
                _emit(
                    context,
                    "rigid_angular_impulse_momentum",
                    Equality(left=impulses[0].expression, right=change),
                    (impulses[0], inertias[0], starts[0], ends[0]),
                )
            )
    for energy in _by_role(context, QuantityRole.energy):
        if energy.subject_id not in rigid_ids or energy.shape is not QuantityShape.scalar:
            continue
        authority = context.approved_assumptions(
            "kinetic_energy", energy.subject_id, energy.interval_id
        )
        if not authority:
            continue
        centers = tuple(
            point.point_id
            for point in context.points
            if point.owner_entity_id == energy.subject_id and point.role is PointRole.mass_center
        )
        if len(centers) != 1:
            continue
        center_id = centers[0]
        masses = tuple(q for q in _by_role(context, QuantityRole.mass) if _scope_compatible(energy, q) and q.shape is QuantityShape.scalar)
        velocities = tuple(
            q
            for role in (QuantityRole.velocity, QuantityRole.speed)
            for q in _by_role(context, role)
            if _scope_compatible(energy, q)
            and q.point_id == center_id
            and _is_full_translational_speed(q, frame_types)
        )
        inertias = tuple(q for q in _by_role(context, QuantityRole.moment_of_inertia) if _scope_compatible(energy, q) and q.shape is QuantityShape.scalar and q.point_id == center_id)
        angular = tuple(q for q in _by_role(context, QuantityRole.angular_velocity) if _scope_compatible(energy, q) and q.shape is QuantityShape.scalar and q.point_id == center_id)
        if not (len(masses) == len(velocities) == len(inertias) == len(angular) == 1):
            continue
        translational_squared = (
            Dot(left=velocities[0].expression, right=velocities[0].expression)
            if velocities[0].shape is QuantityShape.vector
            else Power(base=velocities[0].expression, exponent=LiteralNode(value=2.0))
        )
        translational = Multiply(
            factors=(
                LiteralNode(value=0.5),
                masses[0].expression,
                translational_squared,
            ),
            dimension=energy.dimension,
        )
        rotational = Multiply(
            factors=(
                LiteralNode(value=0.5),
                inertias[0].expression,
                Power(base=angular[0].expression, exponent=LiteralNode(value=2.0)),
            ),
            dimension=energy.dimension,
        )
        emitted.append(
            _emit(
                context,
                "rigid_kinetic_energy",
                Equality(
                    left=energy.expression,
                    right=Add(terms=(translational, rotational), dimension=energy.dimension),
                ),
                (energy, masses[0], velocities[0], inertias[0], angular[0]),
                assumption_ids=authority,
            )
        )
    return emitted


@dataclass(frozen=True)
class _MassivePulleyAtwoodSide:
    sign: int
    point_id: str
    attachment_relation_id: str
    radius_relation_id: str
    tangent_relation_id: str
    radius: BoundQuantity
    local_tension: BoundQuantity
    rim_tension: BoundQuantity
    local_acceleration: BoundQuantity
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class _MassivePulleyAtwoodLawProfile:
    rope_interaction_id: str
    rope_id: str
    pulley_id: str
    frame_id: str
    interval_id: str
    sides: tuple[_MassivePulleyAtwoodSide, _MassivePulleyAtwoodSide]
    rope_acceleration: BoundQuantity
    inertia: BoundQuantity
    alpha: BoundQuantity
    wrap_relation_id: str
    taut_state_id: str
    no_slip_state_id: str
    massless_assumption_ids: tuple[str, ...]
    inextensible_assumption_ids: tuple[str, ...]
    fixed_assumption_ids: tuple[str, ...]
    axle_assumption_ids: tuple[str, ...]
    wrap_evidence_ids: tuple[str, ...]
    taut_evidence_ids: tuple[str, ...]
    no_slip_evidence_ids: tuple[str, ...]
    massless_evidence_ids: tuple[str, ...]
    inextensible_evidence_ids: tuple[str, ...]
    fixed_evidence_ids: tuple[str, ...]
    axle_evidence_ids: tuple[str, ...]


def _massive_pulley_atwood_profile(
    context: LawContext,
) -> _MassivePulleyAtwoodLawProfile | None:
    """Recognize the closed fixed-axis inertial-pulley graph."""

    primitive_ids = {
        primitive: tuple(
            item.entity_id
            for item in context.entities
            if item.primitive is primitive
        )
        for primitive in (
            EntityPrimitive.particle,
            EntityPrimitive.rope,
            EntityPrimitive.pulley,
            EntityPrimitive.environment,
        )
    }
    if (
        len(context.entities) != 5
        or {key: len(value) for key, value in primitive_ids.items()}
        != {
            EntityPrimitive.particle: 2,
            EntityPrimitive.rope: 1,
            EntityPrimitive.pulley: 1,
            EntityPrimitive.environment: 1,
        }
        or any(
            not item.evidence_refs or item.component_of_entity_id is not None
            for item in context.entities
        )
    ):
        return None
    particle_ids = set(primitive_ids[EntityPrimitive.particle])
    rope_id = primitive_ids[EntityPrimitive.rope][0]
    pulley_id = primitive_ids[EntityPrimitive.pulley][0]
    environment_id = primitive_ids[EntityPrimitive.environment][0]

    if len(context.reference_frames) != 1:
        return None
    frame = context.reference_frames[0]
    axis_signature = {
        (
            item.axis,
            getattr(item.direction, "kind", None),
            getattr(item.direction, "frame_id", None),
            getattr(item.direction, "axis", None),
            getattr(item.direction, "sign", None),
        )
        for item in frame.axes
    }
    if (
        frame.frame_type is not ReferenceFrameType.cartesian_3d
        or getattr(frame.origin, "kind", None) != "world"
        or frame.parent_frame_id is not None
        or frame.translating_with_entity_id is not None
        or frame.rotating_about_point_id is not None
        or frame.generalized_coordinate_symbol_ids
        or not frame.evidence_refs
        or len(frame.axes) != 3
        or axis_signature
        != {
            (AxisName.x, "axis", frame.frame_id, AxisName.x, 1),
            (AxisName.y, "axis", frame.frame_id, AxisName.y, 1),
            (AxisName.z, "axis", frame.frame_id, AxisName.z, 1),
        }
    ):
        return None

    if len(context.motion_intervals) != 1 or context.events:
        return None
    interval = context.motion_intervals[0]
    if (
        interval.frame_id != frame.frame_id
        or interval.start_event_id is not None
        or interval.end_event_id is not None
        or set(interval.subject_ids)
        != {item.entity_id for item in context.entities}
        or len(interval.subject_ids) != len(context.entities)
        or not interval.evidence_refs
    ):
        return None

    if len(context.points) != 2:
        return None
    points = {item.point_id: item for item in context.points}
    if any(
        item.role is not PointRole.contact
        or item.owner_entity_id != pulley_id
        or item.frame_id != frame.frame_id
        or not item.evidence_refs
        for item in points.values()
    ):
        return None
    point_ids = set(points)

    radius_relations = tuple(
        item
        for item in context.geometry
        if item.kind is GeometryRelationKind.radius
    )
    tangent_relations = tuple(
        item
        for item in context.geometry
        if item.kind is GeometryRelationKind.tangent
    )
    wraps = tuple(
        item
        for item in context.geometry
        if item.kind is GeometryRelationKind.wraps
    )
    attachments = tuple(
        item
        for item in context.geometry
        if item.kind is GeometryRelationKind.attached
    )
    if (
        len(context.geometry) != 7
        or len(radius_relations) != 2
        or len(tangent_relations) != 2
        or len(wraps) != 1
        or len(attachments) != 2
        or any(
            item.interval_id != interval.interval_id
            or item.expression is not None
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            or len(item.quantity_ids) != len(set(item.quantity_ids))
            for item in context.geometry
        )
        or {frozenset(item.participant_ids) for item in radius_relations}
        != {frozenset((pulley_id, point_id)) for point_id in point_ids}
        or any(len(item.quantity_ids) != 1 for item in radius_relations)
        or {frozenset(item.participant_ids) for item in tangent_relations}
        != {
            frozenset((rope_id, pulley_id, point_id))
            for point_id in point_ids
        }
        or any(len(item.quantity_ids) != 2 for item in tangent_relations)
        or set(wraps[0].participant_ids)
        != {rope_id, pulley_id, *point_ids}
        or len(wraps[0].participant_ids) != 4
    ):
        return None
    wrap = wraps[0]

    gravity_interactions = tuple(
        item
        for item in context.interactions
        if item.kind is InteractionKind.gravity
    )
    rope_interactions = tuple(
        item
        for item in context.interactions
        if item.kind is InteractionKind.rope_tension
    )
    if (
        len(context.interactions) != 3
        or len(gravity_interactions) != 2
        or len(rope_interactions) != 1
    ):
        return None
    rope_interaction = rope_interactions[0]
    if (
        set(rope_interaction.participant_ids)
        != particle_ids | {rope_id, pulley_id}
        or len(rope_interaction.participant_ids) != 4
        or set(rope_interaction.point_ids) != point_ids
        or len(rope_interaction.point_ids) != 2
        or rope_interaction.frame_id != frame.frame_id
        or rope_interaction.interval_id != interval.interval_id
        or rope_interaction.event_id is not None
        or len(rope_interaction.quantity_ids) != 4
        or len(set(rope_interaction.quantity_ids)) != 4
        or not rope_interaction.evidence_refs
        or {
            next(iter(set(item.participant_ids) & particle_ids), None)
            for item in gravity_interactions
        }
        != particle_ids
        or any(
            len(item.participant_ids) != 2
            or len(set(item.participant_ids)) != 2
            or environment_id not in item.participant_ids
            or item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.point_ids
            or len(item.quantity_ids) != 3
            or len(set(item.quantity_ids)) != 3
            or not item.evidence_refs
            for item in gravity_interactions
        )
    ):
        return None

    taut_states = tuple(
        item
        for item in context.state_conditions
        if item.subject_id == rope_id and item.kind is StateKind.rope
    )
    no_slip_states = tuple(
        item
        for item in context.state_conditions
        if item.subject_id == pulley_id and item.kind is StateKind.rolling
    )
    if (
        len(context.state_conditions) != 2
        or len(taut_states) != 1
        or taut_states[0].state is not StateValue.taut
        or taut_states[0].quantity_ids
        or len(no_slip_states) != 1
        or no_slip_states[0].state is not StateValue.no_slip
        or any(
            item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.expression is not None
            or not item.evidence_refs
            for item in context.state_conditions
        )
    ):
        return None
    taut_state = taut_states[0]
    no_slip_state = no_slip_states[0]

    required_assumptions = {
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("fixed_pulley", pulley_id),
        ("frictionless_axle", pulley_id),
    }
    if (
        len(context.assumptions) != 4
        or {(item.kind, item.subject_id) for item in context.assumptions}
        != required_assumptions
        or any(
            item.interval_id != interval.interval_id
            or item.proposed_role is not None
            or item.proposed_value is not None
            or item.proposed_unit is not None
            or not item.evidence_refs
            for item in context.assumptions
        )
    ):
        return None
    assumption_by_kind = {item.kind: item for item in context.assumptions}
    approved_by_kind = {
        kind: context.approved_assumptions(
            kind,
            assumption.subject_id,
            interval.interval_id,
        )
        for kind, assumption in assumption_by_kind.items()
    }
    if any(
        ids != (assumption_by_kind[kind].assumption_id,)
        for kind, ids in approved_by_kind.items()
    ):
        return None

    quantities = {
        item.quantity_id: item
        for item in context.quantities
        if item.quantity_id is not None
    }
    if len(quantities) != len(context.quantities):
        return None
    masses: dict[str, BoundQuantity] = {}
    weights: dict[str, BoundQuantity] = {}
    gravities: list[BoundQuantity] = []
    for interaction in gravity_interactions:
        body_id = next(iter(set(interaction.participant_ids) & particle_ids))
        linked = tuple(quantities.get(item) for item in interaction.quantity_ids)
        local_masses = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.mass
            and item.subject_id == body_id
        )
        local_gravities = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.gravity
            and item.subject_id == environment_id
        )
        local_weights = tuple(
            item
            for item in linked
            if item is not None
            and item.role is QuantityRole.force
            and item.subject_id == body_id
        )
        if not all(
            len(items) == 1
            for items in (local_masses, local_gravities, local_weights)
        ):
            return None
        masses[body_id] = local_masses[0]
        gravities.append(local_gravities[0])
        weights[body_id] = local_weights[0]
    if len({item.quantity_id for item in gravities}) != 1:
        return None
    gravity = gravities[0]

    inertia_values = tuple(
        item
        for item in context.quantities
        if item.role is QuantityRole.moment_of_inertia
        and item.subject_id == pulley_id
    )
    radii = tuple(
        item
        for item in context.quantities
        if item.role is QuantityRole.radius and item.subject_id == pulley_id
    )
    angular = tuple(
        item
        for item in context.quantities
        if item.role is QuantityRole.angular_acceleration
        and item.subject_id == pulley_id
    )
    rope_accelerations = tuple(
        item
        for item in context.quantities
        if item.role is QuantityRole.acceleration
        and item.subject_id == rope_id
        and item.frame_id is None
    )
    if not (
        len(inertia_values) == len(angular) == len(rope_accelerations) == 1
        and len(radii) == 2
    ):
        return None
    inertia = inertia_values[0]
    alpha = angular[0]
    rope_acceleration = rope_accelerations[0]

    def exact_known_unscoped(item: BoundQuantity, subject_id: str) -> bool:
        value = item.known_si_value
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.subject_id == subject_id
            and item.evidence_ids
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id is None
            and item.event_id is None
            and item.component
            in {QuantityComponent.magnitude, QuantityComponent.unspecified}
            and not item.direction_bound
            and type(value) is float
            and math.isfinite(value)
            and value > 0.0
        )

    if (
        any(
            not exact_known_unscoped(item, body_id)
            for body_id, item in masses.items()
        )
        or not exact_known_unscoped(gravity, environment_id)
        or not exact_known_unscoped(inertia, pulley_id)
    ):
        return None

    radius_by_sign: dict[int, BoundQuantity] = {}
    point_by_sign: dict[int, str] = {}
    for radius in radii:
        value = radius.known_si_value
        if (
            radius.shape is not QuantityShape.scalar
            or radius.symbol_id is None
            or not radius.evidence_ids
            or radius.point_id not in point_ids
            or radius.frame_id != frame.frame_id
            or radius.interval_id != interval.interval_id
            or radius.event_id is not None
            or radius.component is not QuantityComponent.x
            or radius.direction_sign not in {-1, 1}
            or not _axis_bound(
                radius,
                frame.frame_id,
                QuantityComponent.x,
                radius.direction_sign,
            )
            or type(value) is not float
            or not math.isfinite(value)
            or value <= 0.0
        ):
            return None
        radius_by_sign[radius.direction_sign] = radius
        point_by_sign[radius.direction_sign] = radius.point_id
    if (
        set(radius_by_sign) != {-1, 1}
        or set(point_by_sign.values()) != point_ids
        or radius_by_sign[-1].known_si_value != radius_by_sign[1].known_si_value
    ):
        return None

    radius_relation_by_point = {
        next(iter(set(item.participant_ids) & point_ids)): item
        for item in radius_relations
    }
    for point_id, relation in radius_relation_by_point.items():
        radius = next(item for item in radii if item.point_id == point_id)
        if tuple(relation.quantity_ids) != (radius.quantity_id,):
            return None

    def exact_unknown_axis(
        item: BoundQuantity,
        *,
        subject_id: str,
        point_id: str | None,
        component: QuantityComponent,
        sign: int,
    ) -> bool:
        return (
            item.shape is QuantityShape.scalar
            and item.symbol_id is not None
            and item.known_si_value is None
            and item.evidence_ids
            and item.subject_id == subject_id
            and item.point_id == point_id
            and item.frame_id == frame.frame_id
            and item.interval_id == interval.interval_id
            and item.event_id is None
            and _axis_bound(item, frame.frame_id, component, sign)
        )

    if any(
        not exact_unknown_axis(
            item,
            subject_id=body_id,
            point_id=None,
            component=QuantityComponent.y,
            sign=1,
        )
        for body_id, item in weights.items()
    ):
        return None
    rope_linked = tuple(
        quantities.get(item) for item in rope_interaction.quantity_ids
    )
    if any(item is None for item in rope_linked):
        return None
    local_tensions = tuple(
        item
        for item in rope_linked
        if item.role is QuantityRole.force and item.subject_id in particle_ids
    )
    rim_tensions = tuple(
        item
        for item in rope_linked
        if item.role is QuantityRole.force
        and item.subject_id == pulley_id
        and item.point_id in point_ids
    )
    if (
        len(local_tensions) != 2
        or {item.subject_id for item in local_tensions} != particle_ids
        or len(rim_tensions) != 2
        or {item.point_id for item in rim_tensions} != point_ids
        or any(
            not exact_unknown_axis(
                item,
                subject_id=item.subject_id,
                point_id=None,
                component=QuantityComponent.y,
                sign=-1,
            )
            for item in local_tensions
        )
        or any(
            not exact_unknown_axis(
                item,
                subject_id=pulley_id,
                point_id=item.point_id,
                component=QuantityComponent.y,
                sign=1,
            )
            for item in rim_tensions
        )
    ):
        return None
    body_accelerations = tuple(
        item
        for item in context.quantities
        if item.role is QuantityRole.acceleration
        and item.subject_id in particle_ids
    )
    if (
        len(body_accelerations) != 2
        or {item.subject_id for item in body_accelerations} != particle_ids
        or any(
            item.shape is not QuantityShape.scalar
            or item.symbol_id is None
            or item.known_si_value is not None
            or not item.evidence_ids
            or item.point_id is not None
            or item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.component is not QuantityComponent.y
            or item.direction_sign not in {-1, 1}
            or not _axis_bound(
                item,
                frame.frame_id,
                QuantityComponent.y,
                item.direction_sign,
            )
            for item in body_accelerations
        )
        or rope_acceleration.shape is not QuantityShape.scalar
        or rope_acceleration.symbol_id is None
        or rope_acceleration.known_si_value is not None
        or not rope_acceleration.evidence_ids
        or rope_acceleration.point_id is not None
        or rope_acceleration.frame_id is not None
        or rope_acceleration.interval_id != interval.interval_id
        or rope_acceleration.event_id is not None
        or rope_acceleration.component is not QuantityComponent.unspecified
        or rope_acceleration.direction_bound
        or alpha.shape is not QuantityShape.scalar
        or alpha.symbol_id is None
        or alpha.known_si_value is not None
        or not alpha.evidence_ids
        or alpha.point_id is not None
        or alpha.frame_id != frame.frame_id
        or alpha.interval_id != interval.interval_id
        or alpha.event_id is not None
        or not _axis_bound(
            alpha,
            frame.frame_id,
            QuantityComponent.z,
            1,
        )
    ):
        return None

    local_tension_by_body = {item.subject_id: item for item in local_tensions}
    rim_tension_by_point = {item.point_id: item for item in rim_tensions}
    acceleration_by_body = {
        item.subject_id: item for item in body_accelerations
    }
    tangent_relation_by_point = {
        next(iter(set(item.participant_ids) & point_ids)): item
        for item in tangent_relations
    }
    side_values: list[_MassivePulleyAtwoodSide] = []
    attached_bodies: set[str] = set()
    attached_points: set[str] = set()
    for attachment in attachments:
        body_matches = set(attachment.participant_ids) & particle_ids
        point_matches = set(attachment.participant_ids) & point_ids
        if len(body_matches) != 1 or len(point_matches) != 1:
            return None
        body_id = next(iter(body_matches))
        point_id = next(iter(point_matches))
        sign = next(
            key for key, value in point_by_sign.items() if value == point_id
        )
        local_acceleration = acceleration_by_body[body_id]
        radius = radius_by_sign[sign]
        rim_tension = rim_tension_by_point[point_id]
        tangent = tangent_relation_by_point[point_id]
        radius_relation = radius_relation_by_point[point_id]
        if (
            set(attachment.participant_ids)
            != {rope_id, pulley_id, body_id, point_id}
            or set(attachment.quantity_ids)
            != {
                local_tension_by_body[body_id].quantity_id,
                rim_tension.quantity_id,
                local_acceleration.quantity_id,
                rope_acceleration.quantity_id,
            }
            or len(attachment.quantity_ids) != 4
            or local_acceleration.direction_sign != sign
            or set(tangent.quantity_ids)
            != {radius.quantity_id, rim_tension.quantity_id}
        ):
            return None
        side_values.append(
            _MassivePulleyAtwoodSide(
                sign=sign,
                point_id=point_id,
                attachment_relation_id=attachment.relation_id,
                radius_relation_id=radius_relation.relation_id,
                tangent_relation_id=tangent.relation_id,
                radius=radius,
                local_tension=local_tension_by_body[body_id],
                rim_tension=rim_tension,
                local_acceleration=local_acceleration,
                evidence_ids=tuple(
                    sorted(
                        set(attachment.evidence_refs)
                        | set(radius_relation.evidence_refs)
                        | set(tangent.evidence_refs)
                    )
                ),
            )
        )
        attached_bodies.add(body_id)
        attached_points.add(point_id)
    if attached_bodies != particle_ids or attached_points != point_ids:
        return None
    sides = tuple(sorted(side_values, key=lambda item: item.sign))
    if len(sides) != 2 or sides[0].sign != -1 or sides[1].sign != 1:
        return None

    expected_wrap_quantities = {
        *(item.quantity_id for item in radii),
        *(item.quantity_id for item in rim_tensions),
        rope_acceleration.quantity_id,
        alpha.quantity_id,
    }
    if (
        set(wrap.quantity_ids) != expected_wrap_quantities
        or len(wrap.quantity_ids) != 6
        or set(no_slip_state.quantity_ids)
        != {
            *(item.quantity_id for item in radii),
            alpha.quantity_id,
        }
        or len(no_slip_state.quantity_ids) != 3
    ):
        return None

    force_dimension = next(iter(weights.values())).dimension
    acceleration_dimension = body_accelerations[0].dimension
    if (
        any(
            item.dimension != force_dimension
            for item in (*weights.values(), *local_tensions, *rim_tensions)
        )
        or any(
            item.dimension != acceleration_dimension
            for item in (*body_accelerations, rope_acceleration)
        )
        or radii[0].dimension != radii[1].dimension
        or any(
            item.dimension.plus(gravity.dimension) != force_dimension
            for item in masses.values()
        )
        or any(
            item.dimension.plus(acceleration_dimension) != force_dimension
            for item in masses.values()
        )
        or radii[0].dimension.plus(alpha.dimension) != acceleration_dimension
        or radii[0].dimension.plus(force_dimension)
        != inertia.dimension.plus(alpha.dimension)
    ):
        return None
    expected_quantity_ids = {
        *(item.quantity_id for item in masses.values()),
        gravity.quantity_id,
        *(item.quantity_id for item in weights.values()),
        *(item.quantity_id for item in local_tensions),
        *(item.quantity_id for item in rim_tensions),
        *(item.quantity_id for item in body_accelerations),
        rope_acceleration.quantity_id,
        inertia.quantity_id,
        *(item.quantity_id for item in radii),
        alpha.quantity_id,
    }
    if set(quantities) != expected_quantity_ids:
        return None

    def record_evidence(record: object) -> tuple[str, ...]:
        return tuple(sorted(set(getattr(record, "evidence_refs", ()))))

    return _MassivePulleyAtwoodLawProfile(
        rope_interaction_id=rope_interaction.interaction_id,
        rope_id=rope_id,
        pulley_id=pulley_id,
        frame_id=frame.frame_id,
        interval_id=interval.interval_id,
        sides=sides,
        rope_acceleration=rope_acceleration,
        inertia=inertia,
        alpha=alpha,
        wrap_relation_id=wrap.relation_id,
        taut_state_id=taut_state.state_condition_id,
        no_slip_state_id=no_slip_state.state_condition_id,
        massless_assumption_ids=approved_by_kind["massless_rope"],
        inextensible_assumption_ids=approved_by_kind["inextensible_rope"],
        fixed_assumption_ids=approved_by_kind["fixed_pulley"],
        axle_assumption_ids=approved_by_kind["frictionless_axle"],
        wrap_evidence_ids=record_evidence(wrap),
        taut_evidence_ids=record_evidence(taut_state),
        no_slip_evidence_ids=record_evidence(no_slip_state),
        massless_evidence_ids=record_evidence(
            assumption_by_kind["massless_rope"]
        ),
        inextensible_evidence_ids=record_evidence(
            assumption_by_kind["inextensible_rope"]
        ),
        fixed_evidence_ids=record_evidence(
            assumption_by_kind["fixed_pulley"]
        ),
        axle_evidence_ids=record_evidence(
            assumption_by_kind["frictionless_axle"]
        ),
    )


def _massive_pulley_atwood_emissions(
    context: LawContext,
) -> list[LawEmission]:
    profile = _massive_pulley_atwood_profile(context)
    if profile is None:
        return []
    emitted: list[LawEmission] = []
    transfer_entities = (profile.rope_id, profile.pulley_id)
    for side in profile.sides:
        emitted.append(
            _emit(
                context,
                "rope_attachment_side_tension_transfer",
                Equality(
                    left=side.local_tension.expression,
                    right=side.rim_tension.expression,
                ),
                (side.local_tension, side.rim_tension),
                assumption_ids=profile.massless_assumption_ids,
                constraint_ids=(
                    side.attachment_relation_id,
                    profile.taut_state_id,
                ),
                extra_entity_ids=transfer_entities,
                extra_evidence_ids=tuple(
                    sorted(
                        set(side.evidence_ids)
                        | set(profile.taut_evidence_ids)
                        | set(profile.massless_evidence_ids)
                    )
                ),
            )
        )
        emitted.append(
            _emit(
                context,
                "rope_attachment_acceleration_transfer",
                Equality(
                    left=side.local_acceleration.expression,
                    right=profile.rope_acceleration.expression,
                ),
                (side.local_acceleration, profile.rope_acceleration),
                assumption_ids=tuple(
                    sorted(
                        set(profile.inextensible_assumption_ids)
                        | set(profile.fixed_assumption_ids)
                    )
                ),
                constraint_ids=(
                    side.attachment_relation_id,
                    profile.taut_state_id,
                ),
                extra_entity_ids=transfer_entities,
                extra_evidence_ids=tuple(
                    sorted(
                        set(side.evidence_ids)
                        | set(profile.taut_evidence_ids)
                        | set(profile.inextensible_evidence_ids)
                        | set(profile.fixed_evidence_ids)
                    )
                ),
            )
        )

    left, right = profile.sides
    topology_relation_ids = tuple(
        sorted(
            {
                profile.wrap_relation_id,
                left.radius_relation_id,
                right.radius_relation_id,
                left.tangent_relation_id,
                right.tangent_relation_id,
            }
        )
    )
    topology_evidence_ids = tuple(
        sorted(
            set(profile.wrap_evidence_ids)
            | set(left.evidence_ids)
            | set(right.evidence_ids)
        )
    )
    no_slip_product = Multiply(
        factors=(right.radius.expression, profile.alpha.expression),
        dimension=profile.rope_acceleration.dimension,
    )
    emitted.append(
        _emit(
            context,
            "pulley_no_slip_acceleration",
            Equality(
                left=profile.rope_acceleration.expression,
                right=no_slip_product,
            ),
            (
                profile.rope_acceleration,
                left.radius,
                right.radius,
                profile.alpha,
            ),
            assumption_ids=tuple(
                sorted(
                    set(profile.inextensible_assumption_ids)
                    | set(profile.fixed_assumption_ids)
                )
            ),
            constraint_ids=tuple(
                sorted(
                    set(topology_relation_ids)
                    | {profile.no_slip_state_id, profile.taut_state_id}
                )
            ),
            extra_entity_ids=transfer_entities,
            extra_evidence_ids=tuple(
                sorted(
                    set(topology_evidence_ids)
                    | set(profile.no_slip_evidence_ids)
                    | set(profile.taut_evidence_ids)
                    | set(profile.inextensible_evidence_ids)
                    | set(profile.fixed_evidence_ids)
                )
            ),
        )
    )

    tension_difference = Subtract(
        left=right.rim_tension.expression,
        right=left.rim_tension.expression,
        dimension=right.rim_tension.dimension,
    )
    torque_dimension = right.radius.dimension.plus(right.rim_tension.dimension)
    if torque_dimension is None:
        return []
    rope_moment = Multiply(
        factors=(right.radius.expression, tension_difference),
        dimension=torque_dimension,
    )
    inertia_moment = Multiply(
        factors=(profile.inertia.expression, profile.alpha.expression),
        dimension=torque_dimension,
    )
    emitted.append(
        _emit(
            context,
            "pulley_newton_euler",
            Equality(left=rope_moment, right=inertia_moment),
            (
                left.radius,
                right.radius,
                left.rim_tension,
                right.rim_tension,
                profile.inertia,
                profile.alpha,
            ),
            assumption_ids=tuple(
                sorted(
                    set(profile.fixed_assumption_ids)
                    | set(profile.axle_assumption_ids)
                )
            ),
            constraint_ids=topology_relation_ids,
            extra_entity_ids=transfer_entities,
            extra_evidence_ids=tuple(
                sorted(
                    set(topology_evidence_ids)
                    | set(profile.fixed_evidence_ids)
                    | set(profile.axle_evidence_ids)
                )
            ),
        )
    )
    return emitted


def _fixed_ideal_pulley_topology(
    context: LawContext,
    interaction,
    *,
    rope_id: str,
    pulley_id: str,
    moving_ids: tuple[str, ...],
    forces: tuple[BoundQuantity, ...],
) -> bool:
    """Validate only the evidenced topology needed by ideal fixed-pulley laws."""

    if len(moving_ids) != 2 or len(set(moving_ids)) != 2:
        return False
    entities = {item.entity_id: item for item in context.entities}
    topology_ids = {*moving_ids, rope_id, pulley_id}
    if (
        len(interaction.participant_ids) != 4
        or set(interaction.participant_ids) != topology_ids
        or len(set(interaction.participant_ids)) != 4
        or interaction.frame_id is None
        or interaction.interval_id is None
        or interaction.event_id is not None
        or interaction.point_ids
        or not interaction.evidence_refs
        or any(
            entities.get(item) is None or not entities[item].evidence_refs
            for item in topology_ids
        )
        or any(
            entities[item].primitive is not EntityPrimitive.particle
            for item in moving_ids
        )
        or entities[rope_id].primitive is not EntityPrimitive.rope
        or entities[pulley_id].primitive is not EntityPrimitive.pulley
    ):
        return False

    frame = next(
        (
            item
            for item in context.reference_frames
            if item.frame_id == interaction.frame_id
        ),
        None,
    )
    interval = next(
        (
            item
            for item in context.motion_intervals
            if item.interval_id == interaction.interval_id
        ),
        None,
    )
    axis = frame.axes[0] if frame is not None and len(frame.axes) == 1 else None
    if (
        frame is None
        or frame.frame_type is not ReferenceFrameType.cartesian_1d
        or getattr(frame.origin, "kind", None) != "world"
        or not frame.evidence_refs
        or axis is None
        or getattr(axis.direction, "kind", None) != "axis"
        or getattr(axis.direction, "frame_id", None) != frame.frame_id
        or getattr(axis.direction, "axis", None) is not axis.axis
        or getattr(axis.direction, "sign", None) != 1
        or interval is None
        or interval.frame_id != frame.frame_id
        or not topology_ids.issubset(interval.subject_ids)
        or len(interval.subject_ids) != len(set(interval.subject_ids))
        or not interval.evidence_refs
    ):
        return False

    if (
        len(forces) != 2
        or len(interaction.quantity_ids) != 2
        or len(set(interaction.quantity_ids)) != 2
        or {item.quantity_id for item in forces} != set(interaction.quantity_ids)
        or {item.subject_id for item in forces} != set(moving_ids)
        or any(
            item.frame_id != frame.frame_id
            or item.interval_id != interval.interval_id
            or item.event_id is not None
            or item.shape is not QuantityShape.scalar
            or not item.evidence_ids
            for item in forces
        )
    ):
        return False

    related_geometry = tuple(
        item
        for item in context.geometry
        if set(item.participant_ids) & topology_ids
    )
    wraps = tuple(
        item for item in related_geometry if item.kind is GeometryRelationKind.wraps
    )
    attachments = tuple(
        item
        for item in related_geometry
        if item.kind is GeometryRelationKind.attached
    )
    if (
        len(related_geometry) != 3
        or len(wraps) != 1
        or len(attachments) != 2
        or any(
            item.interval_id != interval.interval_id
            or item.expression is not None
            or item.quantity_ids
            or not item.evidence_refs
            or len(item.participant_ids) != len(set(item.participant_ids))
            for item in related_geometry
        )
        or set(wraps[0].participant_ids) != {rope_id, pulley_id}
        or len(wraps[0].participant_ids) != 2
        or {frozenset(item.participant_ids) for item in attachments}
        != {frozenset((rope_id, item)) for item in moving_ids}
    ):
        return False

    topology_states = tuple(
        item
        for item in context.state_conditions
        if item.subject_id in {rope_id, pulley_id}
        and item.interval_id == interval.interval_id
    )
    if (
        len(topology_states) != 2
        or not any(
            item.subject_id == rope_id
            and item.kind is StateKind.rope
            and item.state is StateValue.taut
            for item in topology_states
        )
        or not any(
            item.subject_id == pulley_id
            and item.kind is StateKind.motion
            and item.state is StateValue.at_rest
            for item in topology_states
        )
        or any(
            item.event_id is not None
            or item.expression is not None
            or item.quantity_ids
            or not item.evidence_refs
            for item in topology_states
        )
    ):
        return False

    required = (
        ("massless_rope", rope_id),
        ("inextensible_rope", rope_id),
        ("ideal_massless_frictionless_pulley", pulley_id),
        ("fixed_pulley", pulley_id),
    )
    approved_ids = {
        assumption_id
        for kind, subject_id in required
        for assumption_id in context.approved_assumptions(
            kind, subject_id, interval.interval_id
        )
    }
    approved_records = tuple(
        item for item in context.assumptions if item.assumption_id in approved_ids
    )
    return (
        len(approved_ids) == len(required)
        and len(approved_records) == len(required)
        and {(item.kind, item.subject_id) for item in approved_records}
        == set(required)
        and all(
            item.interval_id == interval.interval_id and item.evidence_refs
            for item in approved_records
        )
        and not any(
            item.subject_id == pulley_id
            and item.role
            in {
                QuantityRole.moment_of_inertia,
                QuantityRole.angular_position,
                QuantityRole.angular_velocity,
                QuantityRole.angular_acceleration,
            }
            for item in context.quantities
        )
    )


def _topology_constraint_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    primitive_by_id = {entity.entity_id: entity.primitive for entity in context.entities}
    massive_pulley_profile = _massive_pulley_atwood_profile(context)
    for interaction in context.interactions:
        if interaction.kind is InteractionKind.rope_tension:
            if (
                massive_pulley_profile is not None
                and interaction.interaction_id
                == massive_pulley_profile.rope_interaction_id
            ):
                continue
            rope_ids = tuple(
                item
                for item in interaction.participant_ids
                if primitive_by_id.get(item) is EntityPrimitive.rope
            )
            pulley_ids = tuple(
                item
                for item in interaction.participant_ids
                if primitive_by_id.get(item) is EntityPrimitive.pulley
            )
            moving_ids = tuple(
                item
                for item in interaction.participant_ids
                if primitive_by_id.get(item)
                in {EntityPrimitive.particle, EntityPrimitive.rigid_body, EntityPrimitive.body_component}
            )
            if len(rope_ids) != 1:
                continue
            rope_id = rope_ids[0]
            massless = context.approved_assumptions(
                "massless_rope", rope_id, interaction.interval_id
            )
            forces = tuple(
                q
                for q in _by_role(context, QuantityRole.force)
                if q.quantity_id in interaction.quantity_ids
                and q.subject_id in {*moving_ids, *pulley_ids}
                and q.shape is QuantityShape.scalar
            )
            inertial_pulley_ids = {
                pulley_id
                for pulley_id in pulley_ids
                if any(
                    q.subject_id == pulley_id
                    and q.interval_id in {None, interaction.interval_id}
                    and q.shape is QuantityShape.scalar
                    for q in _by_role(context, QuantityRole.moment_of_inertia)
                )
            }
            ideal_pulley_authority_by_subject = {
                pulley_id: context.approved_assumptions(
                    "ideal_massless_frictionless_pulley",
                    pulley_id,
                    interaction.interval_id,
                )
                for pulley_id in pulley_ids
            }
            approved_ideal_pulley_ids = {
                pulley_id
                for pulley_id, assumption_ids in ideal_pulley_authority_by_subject.items()
                if assumption_ids
            }
            ideal_pulley_authority = tuple(
                sorted(
                    {
                        assumption_id
                        for assumption_ids in ideal_pulley_authority_by_subject.values()
                        for assumption_id in assumption_ids
                    }
                )
            )
            hanging_gravity_topology_signal = (
                any(
                    item.primitive is EntityPrimitive.environment
                    for item in context.entities
                )
                or any(
                    item.kind is InteractionKind.gravity
                    for item in context.interactions
                )
                or any(
                    item.kind is GeometryRelationKind.attached
                    and rope_id in item.participant_ids
                    for item in context.geometry
                )
                or any(
                    item.subject_id == rope_id
                    and item.kind is StateKind.rope
                    and item.state is StateValue.taut
                    for item in context.state_conditions
                )
            )
            strict_fixed_particle_profile = (
                hanging_gravity_topology_signal
                and len(pulley_ids) == 1
                and len(moving_ids) == 2
                and all(
                    primitive_by_id.get(item) is EntityPrimitive.particle
                    for item in moving_ids
                )
                and not inertial_pulley_ids
            )
            horizontal_contact_profile = (
                _fixed_pulley_horizontal_contact_profile(
                    context,
                    interaction.interaction_id,
                )
                if strict_fixed_particle_profile
                else None
            )
            fixed_ideal_topology = (
                strict_fixed_particle_profile
                and (
                    horizontal_contact_profile is not None
                    or _fixed_ideal_pulley_topology(
                        context,
                        interaction,
                        rope_id=rope_id,
                        pulley_id=pulley_ids[0],
                        moving_ids=moving_ids,
                        forces=forces,
                    )
                )
            )
            tension_authority = tuple(sorted(set(massless) | set(ideal_pulley_authority)))
            equal_tension_allowed = bool(massless) and (
                not pulley_ids
                or (
                    not inertial_pulley_ids
                    and approved_ideal_pulley_ids == set(pulley_ids)
                    and (not strict_fixed_particle_profile or fixed_ideal_topology)
                )
            )
            if equal_tension_allowed and len(forces) >= 2:
                reference = forces[0]
                for force in forces[1:]:
                    horizontal_tension_pair = (
                        horizontal_contact_profile is not None
                        and {reference.quantity_id, force.quantity_id}
                        == {
                            item.quantity_id
                            for item in horizontal_contact_profile.rope_tensions
                        }
                    )
                    if (
                        not _cross_subject_scope_compatible(reference, force)
                        and not horizontal_tension_pair
                    ):
                        continue
                    emitted.append(
                        _emit(
                            context,
                            "rope_massless_tension",
                            Equality(left=reference.expression, right=force.expression),
                            (reference, force),
                            assumption_ids=tension_authority,
                            extra_entity_ids=(rope_id,),
                        )
                    )
            inextensible = context.approved_assumptions(
                "inextensible_rope", rope_id, interaction.interval_id
            )
            if inextensible and not pulley_ids and len(moving_ids) == 2:
                for role in (
                    QuantityRole.displacement,
                    QuantityRole.velocity,
                    QuantityRole.acceleration,
                ):
                    motion = tuple(
                        q
                        for q in _by_role(context, role)
                        if q.subject_id in moving_ids
                        and q.interval_id == interaction.interval_id
                        and q.shape is QuantityShape.scalar
                    )
                    if len(motion) != 2 or {q.subject_id for q in motion} != set(moving_ids):
                        continue
                    if motion[0].frame_id != motion[1].frame_id:
                        continue
                    zero = LiteralNode(value=0.0, dimension=motion[0].dimension)
                    emitted.append(
                        _emit(
                            context,
                            "rope_inextensible_motion",
                            Equality(left=_sum_terms(motion), right=zero),
                            motion,
                            assumption_ids=inextensible,
                            extra_entity_ids=(rope_id,),
                        )
                    )
            if inextensible and len(pulley_ids) == 1:
                pulley_id = pulley_ids[0]
                wraps = tuple(
                    relation
                    for relation in context.geometry
                    if relation.kind.value == "wraps"
                    and relation.interval_id in {None, interaction.interval_id}
                    and {rope_id, pulley_id}.issubset(relation.participant_ids)
                    and relation.evidence_refs
                )
                fixed_assumptions = context.approved_assumptions(
                    "fixed_pulley", pulley_id, interaction.interval_id
                )
                fixed_states = tuple(
                    sorted(
                        state.state_condition_id
                        for state in context.state_conditions
                        if state.subject_id == pulley_id
                        and state.state is StateValue.at_rest
                        and state.interval_id == interaction.interval_id
                        and state.evidence_refs
                    )
                )
                fixed = bool(fixed_assumptions or fixed_states)
                if len(wraps) == 1:
                    for role in (
                        QuantityRole.displacement,
                        QuantityRole.velocity,
                        QuantityRole.acceleration,
                    ):
                        body_motion = tuple(
                            q
                            for q in _by_role(context, role)
                            if q.subject_id in moving_ids
                            and q.interval_id == interaction.interval_id
                            and q.shape is QuantityShape.scalar
                        )
                        horizontal_motion_pair = (
                            horizontal_contact_profile is not None
                            and role is QuantityRole.acceleration
                        )
                        if horizontal_motion_pair:
                            body_motion = horizontal_contact_profile.rope_accelerations
                        pulley_motion = tuple(
                            q
                            for q in _by_role(context, role)
                            if q.subject_id == pulley_id
                            and q.interval_id == interaction.interval_id
                            and q.shape is QuantityShape.scalar
                        )
                        if (
                            fixed
                            and len(body_motion) == 2
                            and not pulley_motion
                            and (
                                not strict_fixed_particle_profile
                                or fixed_ideal_topology
                            )
                        ):
                            if (
                                not _component_compatible(body_motion[0], body_motion[1])
                                and not horizontal_motion_pair
                            ):
                                continue
                            zero = LiteralNode(value=0.0, dimension=body_motion[0].dimension)
                            emitted.append(
                                _emit(
                                    context,
                                    "rope_fixed_pulley_motion",
                                    Equality(left=_sum_terms(body_motion), right=zero),
                                    body_motion,
                                    assumption_ids=tuple(sorted(set(inextensible) | set(fixed_assumptions))),
                                    constraint_ids=tuple(sorted(set(fixed_states) | {wraps[0].relation_id})),
                                    extra_entity_ids=(rope_id, pulley_id),
                                )
                            )
                        elif not fixed and len(body_motion) == len(pulley_motion) == 1:
                            if not _component_compatible(body_motion[0], pulley_motion[0]):
                                continue
                            doubled = Multiply(
                                factors=(LiteralNode(value=2.0), _signed(pulley_motion[0])),
                                dimension=body_motion[0].dimension,
                            )
                            relation = Add(
                                terms=(_signed(body_motion[0]), doubled),
                                dimension=body_motion[0].dimension,
                            )
                            emitted.append(
                                _emit(
                                    context,
                                    "rope_moving_pulley_motion",
                                    Equality(
                                        left=relation,
                                        right=LiteralNode(value=0.0, dimension=body_motion[0].dimension),
                                    ),
                                    (body_motion[0], pulley_motion[0]),
                                    assumption_ids=inextensible,
                                    constraint_ids=(wraps[0].relation_id,),
                                    extra_entity_ids=(rope_id, pulley_id),
                                )
                            )
                    inertias = tuple(
                        q
                        for q in _by_role(context, QuantityRole.moment_of_inertia)
                        if q.subject_id == pulley_id
                        and q.interval_id in {None, interaction.interval_id}
                        and q.shape is QuantityShape.scalar
                    )
                    angular_accelerations = tuple(
                        q
                        for q in _by_role(context, QuantityRole.angular_acceleration)
                        if q.subject_id == pulley_id
                        and q.interval_id == interaction.interval_id
                        and q.shape is QuantityShape.scalar
                    )
                    radii = tuple(
                        q
                        for q in _by_role(context, QuantityRole.radius)
                        if q.subject_id == pulley_id
                        and q.interval_id in {None, interaction.interval_id}
                        and q.shape is QuantityShape.scalar
                    )
                    if (
                        len(inertias) == len(angular_accelerations) == len(radii) == 1
                        and len(forces) == 2
                        and all(force.direction_bound for force in forces)
                        and _component_compatible(forces[0], forces[1])
                    ):
                        torque_dimension = forces[0].dimension.plus(radii[0].dimension)
                        if torque_dimension is not None:
                            rope_moment = Multiply(
                                factors=(radii[0].expression, _sum_terms(forces)),
                                dimension=torque_dimension,
                            )
                            inertia_moment = Multiply(
                                factors=(inertias[0].expression, _signed(angular_accelerations[0])),
                                dimension=torque_dimension,
                            )
                            emitted.append(
                                _emit(
                                    context,
                                    "pulley_newton_euler",
                                    Equality(left=rope_moment, right=inertia_moment),
                                    (radii[0], inertias[0], angular_accelerations[0], *forces),
                                    constraint_ids=(wraps[0].relation_id,),
                                    extra_entity_ids=(rope_id, pulley_id),
                                )
                            )
        elif interaction.kind is InteractionKind.gear_contact:
            if not interaction.evidence_refs or len(interaction.participant_ids) != 2:
                continue
            participants = tuple(interaction.participant_ids)
            if any(primitive_by_id.get(item) is not EntityPrimitive.gear for item in participants):
                continue
            terms = []
            used: list[BoundQuantity] = []
            for participant in participants:
                angular = tuple(
                    q
                    for q in _by_role(context, QuantityRole.angular_velocity)
                    if q.subject_id == participant and q.shape is QuantityShape.scalar
                )
                radius = tuple(
                    q
                    for q in _by_role(context, QuantityRole.radius)
                    if q.subject_id == participant and q.shape is QuantityShape.scalar
                )
                if len(angular) != 1 or len(radius) != 1:
                    break
                terms.append(
                    Multiply(
                        factors=(angular[0].expression, radius[0].expression),
                    )
                )
                used.extend((angular[0], radius[0]))
            if len(terms) == 2:
                pitch_dimension = used[0].dimension.plus(used[1].dimension)
                if pitch_dimension is None:
                    continue
                emitted.append(
                    _emit(
                        context,
                        "gear_pitch_velocity",
                        Equality(
                            left=Add(terms=tuple(terms)),
                            right=LiteralNode(value=0.0, dimension=pitch_dimension),
                        ),
                        tuple(used),
                        extra_entity_ids=participants,
                    )
                )
    for state in context.state_conditions:
        if not state.evidence_refs:
            continue
        if state.state is StateValue.at_rest:
            scoped_ids = set(state.quantity_ids)
            resting = tuple(
                q
                for q in context.quantities
                if q.subject_id == state.subject_id
                and q.role
                in {
                    QuantityRole.velocity,
                    QuantityRole.speed,
                    QuantityRole.angular_velocity,
                    QuantityRole.generalized_speed,
                }
                and (not scoped_ids or q.quantity_id in scoped_ids)
                and (state.interval_id is None or q.interval_id == state.interval_id)
                and (state.event_id is None or q.event_id == state.event_id)
            )
            for quantity in resting:
                emitted.append(
                    _emit(
                        context,
                        "state_at_rest",
                        Equality(
                            left=quantity.expression,
                            right=LiteralNode(value=0.0, dimension=quantity.dimension),
                        ),
                        (quantity,),
                        constraint_ids=(state.state_condition_id,),
                    )
                )
            continue
        if state.state is not StateValue.no_slip:
            continue
        subject = state.subject_id
        if primitive_by_id.get(subject) not in {
            EntityPrimitive.rigid_body,
            EntityPrimitive.pulley,
            EntityPrimitive.gear,
        }:
            continue
        scoped_ids = set(state.quantity_ids)
        linear = tuple(
            q
            for q in context.quantities
            if q.subject_id == subject
            and q.role in {QuantityRole.velocity, QuantityRole.speed}
            and q.shape is QuantityShape.scalar
            and (not scoped_ids or q.quantity_id in scoped_ids)
        )
        angular = tuple(
            q
            for q in _by_role(context, QuantityRole.angular_velocity)
            if q.subject_id == subject
            and q.shape is QuantityShape.scalar
            and (not scoped_ids or q.quantity_id in scoped_ids)
        )
        radii = tuple(
            q
            for q in _by_role(context, QuantityRole.radius)
            if q.subject_id == subject
            and q.shape is QuantityShape.scalar
            and (not scoped_ids or q.quantity_id in scoped_ids)
        )
        if len(linear) == len(angular) == len(radii) == 1:
            rolling = Multiply(
                factors=(angular[0].expression, radii[0].expression),
                dimension=linear[0].dimension,
            )
            emitted.append(
                _emit(
                    context,
                    "rolling_no_slip",
                    Equality(left=linear[0].expression, right=rolling),
                    (linear[0], angular[0], radii[0]),
                    constraint_ids=(state.state_condition_id,),
                )
            )
    return emitted


def _vibration_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    spring_links = tuple(
        set(interaction.quantity_ids)
        for interaction in context.interactions
        if interaction.kind is InteractionKind.spring
    )
    damper_links = {
        quantity_id
        for interaction in context.interactions
        if interaction.kind is InteractionKind.damping
        for quantity_id in interaction.quantity_ids
    }
    force_links = {
        quantity_id
        for interaction in context.interactions
        if interaction.kind is InteractionKind.applied_force
        for quantity_id in interaction.quantity_ids
    }
    for displacement in tuple(
        q
        for q in context.quantities
        if q.role in {QuantityRole.displacement, QuantityRole.generalized_coordinate}
        and q.shape is QuantityShape.scalar
        and q.symbol_id is not None
        and q.event_id is None
    ):
        linear_authority = context.approved_assumptions(
            "linear_vibration", displacement.subject_id, displacement.interval_id
        )
        damped_authority = context.approved_assumptions(
            "damped", displacement.subject_id, displacement.interval_id
        )
        undamped_authority = context.approved_assumptions(
            "undamped", displacement.subject_id, displacement.interval_id
        )
        forced_authority = context.approved_assumptions(
            "forced_vibration", displacement.subject_id, displacement.interval_id
        )
        free_authority = context.approved_assumptions(
            "free_vibration", displacement.subject_id, displacement.interval_id
        )
        if (
            not linear_authority
            or bool(damped_authority) == bool(undamped_authority)
            or bool(forced_authority) == bool(free_authority)
        ):
            continue
        interval = next(
            (item for item in context.motion_intervals if item.interval_id == displacement.interval_id),
            None,
        )
        if interval is None or interval.start_event_id is None:
            continue
        initial_states = tuple(
            state
            for state in context.state_conditions
            if state.kind is StateKind.initial
            and state.subject_id == displacement.subject_id
            and state.interval_id == displacement.interval_id
            and state.event_id == interval.start_event_id
            and state.evidence_refs
        )
        if len(initial_states) != 1:
            continue
        initial_ids = {quantity_id for state in initial_states for quantity_id in state.quantity_ids}
        initial_position_role = displacement.role
        initial_velocity_role = (
            QuantityRole.velocity
            if displacement.role is QuantityRole.displacement
            else QuantityRole.generalized_speed
        )
        initial_values = tuple(
            q
            for q in context.quantities
            if q.quantity_id in initial_ids
            and q.subject_id == displacement.subject_id
            and q.interval_id == displacement.interval_id
            and q.event_id == interval.start_event_id
            and q.role in {initial_position_role, initial_velocity_role}
            and q.known_si_value is not None
            and q.evidence_ids
            and q.symbol_id is not None
            and q.point_id == displacement.point_id
            and q.frame_id == displacement.frame_id
            and q.component is displacement.component
            and _component_compatible(displacement, q)
            and set(q.evidence_ids).issubset(set(initial_states[0].evidence_refs))
        )
        if (
            {item.role for item in initial_values}
            != {initial_position_role, initial_velocity_role}
            or len(initial_values) != 2
        ):
            continue
        times = tuple(
            q
            for q in _by_role(context, QuantityRole.time)
            if q.subject_id == displacement.subject_id
            and q.point_id is None
            and q.frame_id == displacement.frame_id
            and q.interval_id == displacement.interval_id
            and q.event_id is None
            and q.shape is QuantityShape.scalar
            and q.symbol_id is not None
        )
        if len(times) != 1:
            continue
        time = times[0]
        masses = tuple(q for q in _by_role(context, QuantityRole.mass) if _scope_compatible(displacement, q))
        stiffness = tuple(
            q
            for q in _by_role(context, QuantityRole.stiffness)
            if _scope_compatible(displacement, q)
            and q.quantity_id is not None
            and displacement.quantity_id is not None
            and any({q.quantity_id, displacement.quantity_id}.issubset(link) for link in spring_links)
        )
        if len(masses) != 1 or len(stiffness) != 1:
            continue
        velocity_dimension = displacement.dimension.minus(time.dimension)
        acceleration_dimension = (
            velocity_dimension.minus(time.dimension)
            if velocity_dimension is not None
            else None
        )
        force_dimension = (
            masses[0].dimension.plus(acceleration_dimension)
            if acceleration_dimension is not None
            else None
        )
        spring_force_dimension = stiffness[0].dimension.plus(displacement.dimension)
        if force_dimension is None or spring_force_dimension != force_dimension:
            continue
        velocity_derivative = Derivative(
            expression=displacement.expression,
            wrt_symbol_id=time.symbol_id,
            order=1,
            dimension=velocity_dimension,
        )
        acceleration_derivative = Derivative(
            expression=displacement.expression,
            wrt_symbol_id=time.symbol_id,
            order=2,
            dimension=acceleration_dimension,
        )
        terms = [
            Multiply(
                factors=(masses[0].expression, acceleration_derivative),
                dimension=force_dimension,
            ),
            Multiply(factors=(stiffness[0].expression, displacement.expression), dimension=force_dimension),
        ]
        used: list[BoundQuantity] = [displacement, masses[0], stiffness[0], time]
        assumption_ids: tuple[str, ...] = tuple(
            sorted(
                set(linear_authority)
                | set(damped_authority)
                | set(undamped_authority)
                | set(forced_authority)
                | set(free_authority)
            )
        )
        damping = tuple(
            q
            for q in _by_role(context, QuantityRole.damping)
            if _scope_compatible(displacement, q) and q.quantity_id in damper_links
        )
        if (
            damped_authority
            and len(damping) == 1
            and damping[0].dimension.plus(velocity_dimension) == force_dimension
        ):
            terms.insert(
                1,
                Multiply(
                    factors=(damping[0].expression, velocity_derivative),
                    dimension=force_dimension,
                ),
            )
            used.append(damping[0])
        elif damped_authority or damping:
            continue
        forces = tuple(
            q
            for q in _by_role(context, QuantityRole.force)
            if _scope_compatible(displacement, q)
            and q.shape is QuantityShape.scalar
            and q.quantity_id in force_links
        )
        if forced_authority and len(forces) == 1 and forces[0].known_si_value is not None:
            right = _sum_terms(forces)
        elif free_authority and not forces:
            right = LiteralNode(value=0.0, dimension=force_dimension)
        else:
            continue
        used.extend(forces)
        position_value = next(
            item for item in initial_values if item.role is initial_position_role
        )
        velocity_value = next(
            item for item in initial_values if item.role is initial_velocity_role
        )
        state_ids = tuple(state.state_condition_id for state in initial_states)
        initial_conditions = (
            InitialConditionBinding(
                target_symbol_id=displacement.symbol_id,
                value_symbol_id=position_value.symbol_id,
                wrt_symbol_id=time.symbol_id,
                derivative_order=0,
                subject_id=displacement.subject_id,
                point_id=displacement.point_id,
                frame_id=displacement.frame_id,
                interval_id=displacement.interval_id,
                event_id=interval.start_event_id,
                source_quantity_ids=(position_value.quantity_id,),
                source_evidence_ids=tuple(sorted(set(position_value.evidence_ids))),
                source_state_condition_ids=state_ids,
            ),
            InitialConditionBinding(
                target_symbol_id=displacement.symbol_id,
                value_symbol_id=velocity_value.symbol_id,
                wrt_symbol_id=time.symbol_id,
                derivative_order=1,
                subject_id=displacement.subject_id,
                point_id=displacement.point_id,
                frame_id=displacement.frame_id,
                interval_id=displacement.interval_id,
                event_id=interval.start_event_id,
                source_quantity_ids=(velocity_value.quantity_id,),
                source_evidence_ids=tuple(sorted(set(velocity_value.evidence_ids))),
                source_state_condition_ids=state_ids,
            ),
        )
        emitted.append(
            _emit(
                context,
                "linear_vibration",
                Equality(left=Add(terms=tuple(terms), dimension=terms[0].dimension), right=right),
                tuple(used),
                assumption_ids=assumption_ids,
                constraint_ids=state_ids,
                initial_conditions=initial_conditions,
            )
        )
    for frequency in _by_role(context, QuantityRole.frequency):
        if frequency.shape is not QuantityShape.scalar:
            continue
        authority = context.approved_assumptions(
            "angular_natural_frequency", frequency.subject_id, frequency.interval_id
        )
        if not authority:
            continue
        masses = tuple(q for q in _by_role(context, QuantityRole.mass) if _scope_compatible(frequency, q) and q.shape is QuantityShape.scalar)
        stiffness = tuple(q for q in _by_role(context, QuantityRole.stiffness) if _scope_compatible(frequency, q) and q.shape is QuantityShape.scalar)
        if len(masses) == len(stiffness) == 1:
            emitted.append(
                _emit(
                    context,
                    "vibration_natural_frequency",
                    Equality(
                        left=Power(
                            base=frequency.expression,
                            exponent=LiteralNode(value=2.0),
                        ),
                        right=Divide(
                            numerator=stiffness[0].expression,
                            denominator=masses[0].expression,
                        ),
                    ),
                    (frequency, masses[0], stiffness[0]),
                    assumption_ids=authority,
                )
            )
    return emitted


def apply_core_laws(context: LawContext) -> tuple[LawEmission, ...]:
    emitted: list[LawEmission] = []
    emitted.extend(_derivative_emissions(context, QuantityRole.position, QuantityRole.velocity, "particle_position_derivative"))
    emitted.extend(_derivative_emissions(context, QuantityRole.velocity, QuantityRole.acceleration, "particle_velocity_derivative"))
    emitted.extend(_derivative_emissions(context, QuantityRole.angular_position, QuantityRole.angular_velocity, "angular_position_derivative"))
    emitted.extend(_derivative_emissions(context, QuantityRole.angular_velocity, QuantityRole.angular_acceleration, "angular_velocity_derivative"))
    emitted.extend(_constant_velocity_emissions(context))
    emitted.extend(_constant_acceleration_emissions(context))
    emitted.extend(_chain_kinematics_emissions(context))
    emitted.extend(_incline_gravity_contact_emissions(context))
    emitted.extend(_horizontal_fixed_contact_emissions(context))
    emitted.extend(_incline_hanging_rope_emissions(context))
    emitted.extend(_massive_pulley_atwood_emissions(context))
    emitted.extend(_newton_emissions(context))
    emitted.extend(_primitive_interaction_emissions(context))
    emitted.extend(_work_energy_emissions(context))
    emitted.extend(_momentum_emissions(context))
    emitted.extend(_rigid_emissions(context))
    emitted.extend(_topology_constraint_emissions(context))
    emitted.extend(_vibration_emissions(context))
    return tuple(
        sorted(
            emitted,
            key=lambda item: (
                item.effective_cost,
                item.rule.law_id,
                item.entity_ids,
                item.interval_id or "",
                item.event_id or "",
                item.source_quantity_ids,
            ),
        )
    )


__all__ = ["CORE_LAW_CATALOG", "apply_core_laws", "core_law_catalog"]
