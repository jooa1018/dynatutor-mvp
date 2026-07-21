from __future__ import annotations

from collections.abc import Iterable

from engine.mechanics.contracts import (
    EntityPrimitive,
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
    _rule("contact_friction_bound", "newton_second_law", (QuantityRole.coefficient_friction, QuantityRole.force), interactions=(InteractionKind.contact.value,), cost=4, hooks=("friction_regime",)),
    _rule("contact_normal_bound", "newton_second_law", (QuantityRole.force,), interactions=(InteractionKind.contact.value,), cost=2, hooks=("contact_validity",)),
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
    _rule("rope_inextensible_motion", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope",), cost=2, hooks=("constraint_residual",)),
    _rule("rope_fixed_pulley_motion", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope", "fixed_pulley"), cost=3, hooks=("topology_residual",)),
    _rule("rope_moving_pulley_motion", "constraint", (QuantityRole.acceleration,), interactions=(InteractionKind.rope_tension.value,), assumptions=("inextensible_rope",), cost=4, hooks=("topology_residual",)),
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
    initial_conditions: tuple[InitialConditionBinding, ...] = (),
) -> LawEmission:
    rule = _RULES[rule_id]
    return emission_for(
        rule,
        expression,
        quantities,
        assumption_ids=assumption_ids,
        constraint_ids=constraint_ids,
        extra_entity_ids=extra_entity_ids,
        initial_conditions=initial_conditions,
        hint_priority=rule.category in context.hinted_principles,
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
                ):
                    product = Multiply(
                        factors=(masses[0].expression, gravities[0].expression),
                        dimension=force.dimension,
                    )
                    emitted.append(
                        _emit(
                            context,
                            "particle_weight",
                            Equality(left=_signed(force), right=product),
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
                    constraint_ids=(state.state_condition_id,),
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
                            (tangent[0], normal[0], coefficients[0]),
                            constraint_ids=(state.state_condition_id,),
                            extra_entity_ids=tuple(interaction.participant_ids),
                        )
                    )
            elif tangent[0].direction_bound:
                emitted.append(
                    _emit(
                        context,
                        "contact_sliding_friction",
                        Equality(left=tangent[0].expression, right=bound),
                        (tangent[0], normal[0], coefficients[0]),
                        constraint_ids=(state.state_condition_id,),
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


def _topology_constraint_emissions(context: LawContext) -> list[LawEmission]:
    emitted: list[LawEmission] = []
    primitive_by_id = {entity.entity_id: entity.primitive for entity in context.entities}
    for interaction in context.interactions:
        if interaction.kind is InteractionKind.rope_tension:
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
            tension_authority = tuple(sorted(set(massless) | set(ideal_pulley_authority)))
            equal_tension_allowed = bool(massless) and (
                not pulley_ids
                or (
                    not inertial_pulley_ids
                    and approved_ideal_pulley_ids == set(pulley_ids)
                )
            )
            if equal_tension_allowed and len(forces) >= 2:
                reference = forces[0]
                for force in forces[1:]:
                    if not _cross_subject_scope_compatible(reference, force):
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
                        pulley_motion = tuple(
                            q
                            for q in _by_role(context, role)
                            if q.subject_id == pulley_id
                            and q.interval_id == interaction.interval_id
                            and q.shape is QuantityShape.scalar
                        )
                        if fixed and len(body_motion) == 2 and not pulley_motion:
                            if not _component_compatible(body_motion[0], body_motion[1]):
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
