from __future__ import annotations

import math
from typing import Any, Callable, Mapping

try:
    from .chrono_compat import (
        COLLISION_ENVELOPE_M,
        COLLISION_SAFE_MARGIN_M,
        ChronoAdapter,
        ChronoImport,
        import_chrono,
    )
    from .contracts import (
        ChronoResult,
        DEFAULT_CHRONO_POLICY,
        comparison_errors,
        comparison_passed,
        error_result,
        unavailable_result,
    )
except ImportError:  # direct script execution from tools/chrono_validation
    from chrono_compat import (
        COLLISION_ENVELOPE_M,
        COLLISION_SAFE_MARGIN_M,
        ChronoAdapter,
        ChronoImport,
        import_chrono,
    )
    from contracts import (
        ChronoResult,
        DEFAULT_CHRONO_POLICY,
        comparison_errors,
        comparison_passed,
        error_result,
        unavailable_result,
    )


G = 9.81
ROLLING_ANGLE_DEG = 20.0
ROLLING_RADIUS_M = 0.1
ROLLING_DISK_WIDTH_M = 0.06
BLOCK_SIZE_M = 0.2
COLLISION_RADIUS_M = 0.1


def simulate_rolling_down_ramp(*, height_m: float, body: str) -> ChronoResult:
    raw_inputs = {"height_m": repr(height_m), "body": str(body)}
    try:
        height = _positive(height_m, name="height_m")
        body_key = str(body).strip().lower()
        if body_key not in {"sphere", "disk"}:
            raise ValueError("body must be 'sphere' or 'disk'")
    except (TypeError, ValueError) as exc:
        return error_result(
            case_id=f"rolling_{str(body)}",
            observable="final_center_of_mass_speed",
            unit="m/s",
            time_step=DEFAULT_CHRONO_POLICY.rolling_step_s,
            duration=DEFAULT_CHRONO_POLICY.rolling_max_duration_s,
            message=f"invalid rolling scene input: {exc}",
            initial_conditions={"raw_inputs": raw_inputs},
        )

    initial = {
        "height_m": height,
        "body": body_key,
        "radius_m": ROLLING_RADIUS_M,
        "incline_angle_deg": ROLLING_ANGLE_DEG,
        "initial_center_of_mass_velocity_m_s": [0.0, 0.0, 0.0],
        "initial_angular_velocity_rad_s": [0.0, 0.0, 0.0],
        "gravity_m_s2": G,
        "friction_coefficient": 0.8,
        "collision_envelope_m": COLLISION_ENVELOPE_M,
        "collision_safe_margin_m": COLLISION_SAFE_MARGIN_M,
        "target_along_ramp_distance_m": height / math.sin(math.radians(ROLLING_ANGLE_DEG)),
        "maximum_duration_s": DEFAULT_CHRONO_POLICY.rolling_max_duration_s,
    }
    return _dispatch_scene(
        import_state=import_chrono(),
        case_id=f"rolling_{body_key}",
        observable="final_center_of_mass_speed",
        unit="m/s",
        time_step=DEFAULT_CHRONO_POLICY.rolling_step_s,
        duration=DEFAULT_CHRONO_POLICY.rolling_max_duration_s,
        initial_conditions=initial,
        scene=lambda adapter: _simulate_rolling(adapter, initial),
    )


def _simulate_rolling(adapter: ChronoAdapter, initial: Mapping[str, Any]) -> ChronoResult:
    policy = DEFAULT_CHRONO_POLICY
    body_key = str(initial["body"])
    height = float(initial["height_m"])
    radius = float(initial["radius_m"])
    angle = math.radians(float(initial["incline_angle_deg"]))
    target_distance = float(initial["target_along_ramp_distance_m"])
    gx = G * math.sin(angle)
    gy = -G * math.cos(angle)
    system, solver = adapter.new_nsc_system(gravity=(gx, gy, 0.0))
    material = adapter.contact_material_nsc(friction=0.8)

    ground = adapter.easy_box(
        size_x=target_distance + 2.0,
        size_y=0.2,
        size_z=1.0,
        density=1000.0,
        material=material,
    )
    adapter.set_fixed(ground, True)
    adapter.set_position(ground, (target_distance / 2.0, -0.1, 0.0))
    adapter.add(system, ground)

    if body_key == "sphere":
        rolling_body = adapter.easy_sphere(
            radius=radius,
            density=1000.0,
            material=material,
        )
        expected_inertia_ratio = 2.0 / 5.0
    else:
        rolling_body = adapter.easy_cylinder_z(
            radius=radius,
            height=ROLLING_DISK_WIDTH_M,
            density=1000.0,
            material=material,
        )
        expected_inertia_ratio = 1.0 / 2.0
    adapter.disable_sleeping(rolling_body)
    adapter.set_position(rolling_body, (0.0, radius, 0.0))
    adapter.set_linear_velocity(rolling_body, (0.0, 0.0, 0.0))
    adapter.add(system, rolling_body)
    planar_guide = None
    if body_key == "disk":
        planar_guide = adapter.new_planar_guide(rolling_body, ground)
        adapter.add(system, planar_guide)

    initial_position = adapter.position(rolling_body)
    body_collision_geometry = adapter.collision_geometry(rolling_body)
    positions: list[tuple[float, float, float]] = [initial_position]
    height_samples: list[tuple[float, float, float, float]] = [
        (0.0, initial_position[1], 0.0, 0.0)
    ]
    elapsed = 0.0
    reached_target = False
    step = policy.rolling_step_s
    max_duration = policy.rolling_max_duration_s
    while elapsed + step / 2.0 <= max_duration:
        adapter.step(system, step)
        elapsed = adapter.time(system)
        position = adapter.position(rolling_body)
        positions.append(position)
        current_velocity = adapter.linear_velocity(rolling_body)
        current_contact_force = adapter.contact_force(rolling_body)
        height_samples.append(
            (elapsed, position[1], current_velocity[1], current_contact_force[1])
        )
        if position[0] - initial_position[0] >= target_distance:
            reached_target = True
            break

    final_position = adapter.position(rolling_body)
    velocity = adapter.linear_velocity(rolling_body)
    angular_velocity = adapter.angular_velocity_parent(rolling_body)
    contact_force = adapter.contact_force(rolling_body)
    mass = adapter.mass(rolling_body)
    inertias = {
        axis: adapter.inertia_axis(rolling_body, axis)
        for axis in "xyz"
    }
    axis_inertia = inertias["z"]
    inertia_ratio = axis_inertia / (mass * radius * radius)
    observed_speed = velocity[0]
    analytic_speed = math.sqrt(2.0 * G * height / (1.0 + expected_inertia_ratio))
    abs_error, rel_error = comparison_errors(observed_speed, analytic_speed)

    signed_no_slip = abs(velocity[0] + radius * angular_velocity[2])
    maximum_height_sample = max(height_samples, key=lambda sample: sample[1])
    minimum_height_sample = min(height_samples, key=lambda sample: sample[1])
    maximum_height_error_sample = max(
        height_samples,
        key=lambda sample: abs(sample[1] - radius),
    )
    contact_height_error = abs(maximum_height_error_sample[1] - radius)
    contact_active_samples = [
        sample for sample in height_samples if abs(sample[3]) > 1e-9
    ]
    first_contact_time = (
        contact_active_samples[0][0] if contact_active_samples else None
    )
    samples_outside_height_limit = sum(
        abs(sample[1] - radius) > policy.rolling_contact_abs_tolerance
        for sample in height_samples
    )
    displacement = tuple(final_position[i] - initial_position[i] for i in range(3))
    gravitational_work = mass * (gx * displacement[0] + gy * displacement[1])
    translational_ke = 0.5 * mass * sum(component * component for component in velocity)
    rotational_ke = 0.5 * sum(
        inertias[axis] * angular_velocity[index] * angular_velocity[index]
        for index, axis in enumerate("xyz")
    )
    kinetic_energy = translational_ke + rotational_ke
    energy_relative_error = abs(kinetic_energy - gravitational_work) / max(
        abs(gravitational_work),
        1e-12,
    )
    inertia_ratio_error = abs(inertia_ratio - expected_inertia_ratio)

    checks = {
        "target_reached": reached_target,
        "observable_agreement": comparison_passed(
            observed_speed,
            analytic_speed,
            absolute_tolerance=policy.rolling_speed_abs_tolerance,
            relative_tolerance=policy.rolling_speed_rel_tolerance,
        ),
        "signed_no_slip": signed_no_slip <= policy.rolling_no_slip_abs_tolerance,
        "contact_maintained": contact_height_error <= policy.rolling_contact_abs_tolerance,
        "energy_balance": energy_relative_error <= policy.rolling_energy_rel_tolerance,
        "body_inertia": inertia_ratio_error <= policy.rolling_inertia_ratio_abs_tolerance,
        "forward_motion": observed_speed > 0.0,
        "rolling_direction": angular_velocity[2] < 0.0,
    }
    status = "passed" if all(checks.values()) else "failed"
    return ChronoResult(
        case_id=f"rolling_{body_key}",
        status=status,
        observable="final_center_of_mass_speed",
        value=observed_speed,
        unit="m/s",
        analytic_value=analytic_speed,
        abs_error=abs_error,
        relative_error=rel_error,
        chrono_version=adapter.version,
        solver=solver,
        contact_method="NSC:Coulomb",
        time_step=step,
        duration=elapsed,
        initial_conditions=initial,
        final_state={
            "center_of_mass_position_m": list(final_position),
            "center_of_mass_velocity_m_s": list(velocity),
            "angular_velocity_parent_rad_s": list(angular_velocity),
            "contact_force_N": list(contact_force),
            "mass_kg": mass,
            "principal_inertia_kg_m2": inertias,
            "inertia_ratio_I_over_mR2": inertia_ratio,
            "target_reached": reached_target,
            "planar_guide": (
                type(planar_guide).__name__
                if planar_guide is not None
                else None
            ),
        },
        constraint_errors={
            "signed_no_slip_abs_m_s": signed_no_slip,
            "signed_no_slip_limit_m_s": policy.rolling_no_slip_abs_tolerance,
            "max_contact_height_abs_m": contact_height_error,
            "contact_height_limit_m": policy.rolling_contact_abs_tolerance,
            "collision_geometry": body_collision_geometry,
            "center_height_range_m": [
                minimum_height_sample[1],
                maximum_height_sample[1],
            ],
            "maximum_height_time_s": maximum_height_sample[0],
            "maximum_height_normal_velocity_m_s": maximum_height_sample[2],
            "maximum_height_normal_contact_force_N": maximum_height_sample[3],
            "minimum_height_time_s": minimum_height_sample[0],
            "maximum_height_error_time_s": maximum_height_error_sample[0],
            "contact_active_sample_count": len(contact_active_samples),
            "first_contact_time_s": first_contact_time,
            "samples_outside_height_limit": samples_outside_height_limit,
            "trajectory_sample_count": len(height_samples),
            "checks": {
                "signed_no_slip": checks["signed_no_slip"],
                "contact_maintained": checks["contact_maintained"],
                "rolling_direction": checks["rolling_direction"],
            },
        },
        invariant_errors={
            "energy_balance_relative": energy_relative_error,
            "energy_balance_relative_limit": policy.rolling_energy_rel_tolerance,
            "inertia_ratio_absolute": inertia_ratio_error,
            "inertia_ratio_absolute_limit": policy.rolling_inertia_ratio_abs_tolerance,
            "gravitational_work_J": gravitational_work,
            "kinetic_energy_J": kinetic_energy,
            "checks": checks,
        },
        warnings=(
            "NSC uses a discretized Coulomb contact law; endpoint and contact residuals are reported separately from observable agreement.",
        ),
        artifacts=(
            {
                "kind": "in_memory_trajectory_summary",
                "sample_count": len(positions),
                "target_distance_m": target_distance,
                "planar_guide_count": 1 if planar_guide is not None else 0,
            },
        ),
        modeling_assumptions=(
            "The incline is represented in a ramp-fixed frame by resolving gravity into tangent and normal components.",
            "The body starts from rest in geometric contact with a fixed rigid plane.",
            "Static Coulomb contact supplies the rolling constraint; no analytic velocity is prescribed.",
            (
                "The disk uses a ChLinkMatePlanar guide that constrains only out-of-plane translation and tilt; in-plane translation, normal contact, and rotation about the disk axis remain engine-solved."
                if planar_guide is not None
                else "The sphere is fully unconstrained apart from rigid contact with the plane."
            ),
        ),
    )


def simulate_incline_friction(*, theta_deg: float, mu: float) -> ChronoResult:
    raw_inputs = {"theta_deg": repr(theta_deg), "mu": repr(mu)}
    try:
        theta = _bounded(theta_deg, name="theta_deg", lower=0.0, upper=90.0)
        coefficient = _nonnegative(mu, name="mu")
    except (TypeError, ValueError) as exc:
        return error_result(
            case_id="incline_friction",
            observable="trajectory_acceleration",
            unit="m/s^2",
            time_step=DEFAULT_CHRONO_POLICY.incline_step_s,
            duration=DEFAULT_CHRONO_POLICY.incline_duration_s,
            message=f"invalid incline scene input: {exc}",
            initial_conditions={"raw_inputs": raw_inputs},
        )
    angle = math.radians(theta)
    expected_regime = "slip" if math.tan(angle) > coefficient else "stick"
    initial = {
        "theta_deg": theta,
        "friction_coefficient": coefficient,
        "gravity_m_s2": G,
        "block_size_m": BLOCK_SIZE_M,
        "collision_envelope_m": COLLISION_ENVELOPE_M,
        "collision_safe_margin_m": COLLISION_SAFE_MARGIN_M,
        "initial_center_of_mass_velocity_m_s": [0.0, 0.0, 0.0],
        "expected_regime": expected_regime,
        "duration_s": DEFAULT_CHRONO_POLICY.incline_duration_s,
    }
    return _dispatch_scene(
        import_state=import_chrono(),
        case_id=f"incline_friction_{expected_regime}",
        observable="trajectory_acceleration",
        unit="m/s^2",
        time_step=DEFAULT_CHRONO_POLICY.incline_step_s,
        duration=DEFAULT_CHRONO_POLICY.incline_duration_s,
        initial_conditions=initial,
        scene=lambda adapter: _simulate_incline(adapter, initial),
    )


def _simulate_incline(adapter: ChronoAdapter, initial: Mapping[str, Any]) -> ChronoResult:
    policy = DEFAULT_CHRONO_POLICY
    theta = math.radians(float(initial["theta_deg"]))
    mu = float(initial["friction_coefficient"])
    expected_regime = str(initial["expected_regime"])
    gx = G * math.sin(theta)
    gy = -G * math.cos(theta)
    system, solver = adapter.new_nsc_system(gravity=(gx, gy, 0.0))
    material = adapter.contact_material_nsc(friction=mu)

    ground = adapter.easy_box(
        size_x=8.0,
        size_y=0.2,
        size_z=1.0,
        density=1000.0,
        material=material,
    )
    adapter.set_fixed(ground, True)
    adapter.set_position(ground, (2.0, -0.1, 0.0))
    adapter.add(system, ground)

    block = adapter.easy_box(
        size_x=BLOCK_SIZE_M,
        size_y=BLOCK_SIZE_M,
        size_z=BLOCK_SIZE_M,
        density=1000.0,
        material=material,
    )
    adapter.disable_sleeping(block)
    adapter.set_position(block, (0.0, BLOCK_SIZE_M / 2.0, 0.0))
    adapter.set_linear_velocity(block, (0.0, 0.0, 0.0))
    adapter.add(system, block)

    samples: list[tuple[float, float, float]] = [(0.0, 0.0, BLOCK_SIZE_M / 2.0)]
    step = policy.incline_step_s
    duration = policy.incline_duration_s
    while adapter.time(system) + step / 2.0 <= duration:
        adapter.step(system, step)
        position = adapter.position(block)
        velocity = adapter.linear_velocity(block)
        samples.append((adapter.time(system), velocity[0], position[1]))

    fit_samples = samples[max(1, len(samples) // 5):]
    acceleration, intercept, fit_residual = _linear_fit(
        [(sample[0], sample[1]) for sample in fit_samples]
    )
    final_position = adapter.position(block)
    final_velocity = adapter.linear_velocity(block)
    contact_force = adapter.contact_force(block)
    mass = adapter.mass(block)
    expected_acceleration = (
        G * (math.sin(theta) - mu * math.cos(theta))
        if expected_regime == "slip"
        else 0.0
    )
    abs_error, rel_error = comparison_errors(acceleration, expected_acceleration)
    contact_height_error = max(
        abs(sample[2] - BLOCK_SIZE_M / 2.0)
        for sample in samples
    )
    normal_expected = mass * G * math.cos(theta)
    normal_relative_error = abs(abs(contact_force[1]) - normal_expected) / max(
        normal_expected,
        1e-12,
    )
    if expected_regime == "slip":
        friction_direction_violation = max(
            0.0,
            contact_force[0] * final_velocity[0],
        ) / max(abs(contact_force[0] * final_velocity[0]), 1e-12)
        regime_observed = abs(final_velocity[0]) > 0.02
        friction_check = (
            contact_force[0] * final_velocity[0] <= 1e-9
            and abs(contact_force[0]) > 1e-6
        )
        friction_balance_relative = None
    else:
        tangential_gravity = mass * gx
        friction_balance_relative = abs(contact_force[0] + tangential_gravity) / max(
            abs(tangential_gravity),
            1e-12,
        )
        friction_direction_violation = 0.0
        regime_observed = abs(final_velocity[0]) <= 0.01
        friction_check = friction_balance_relative <= 0.05

    checks = {
        "observable_agreement": comparison_passed(
            acceleration,
            expected_acceleration,
            absolute_tolerance=policy.incline_acceleration_abs_tolerance,
            relative_tolerance=policy.incline_acceleration_rel_tolerance,
        ),
        "contact_maintained": contact_height_error <= policy.incline_contact_abs_tolerance,
        "normal_force": normal_relative_error <= policy.incline_normal_force_rel_tolerance,
        "trajectory_linear_after_transient": fit_residual <= policy.incline_fit_residual_abs_tolerance,
        "friction_direction_or_balance": friction_check,
        "friction_regime": regime_observed,
    }
    status = "passed" if all(checks.values()) else "failed"
    return ChronoResult(
        case_id=f"incline_friction_{expected_regime}",
        status=status,
        observable="trajectory_acceleration",
        value=acceleration,
        unit="m/s^2",
        analytic_value=expected_acceleration,
        abs_error=abs_error,
        relative_error=rel_error,
        chrono_version=adapter.version,
        solver=solver,
        contact_method="NSC:Coulomb",
        time_step=step,
        duration=adapter.time(system),
        initial_conditions=initial,
        final_state={
            "center_of_mass_position_m": list(final_position),
            "center_of_mass_velocity_m_s": list(final_velocity),
            "contact_force_N": list(contact_force),
            "mass_kg": mass,
            "trajectory_fit_intercept_m_s": intercept,
            "expected_regime": expected_regime,
            "observed_regime": "slip" if abs(final_velocity[0]) > 0.02 else "stick",
        },
        constraint_errors={
            "max_contact_height_abs_m": contact_height_error,
            "contact_height_limit_m": policy.incline_contact_abs_tolerance,
            "normal_force_relative": normal_relative_error,
            "normal_force_relative_limit": policy.incline_normal_force_rel_tolerance,
            "friction_direction_violation": friction_direction_violation,
            "friction_balance_relative": friction_balance_relative,
            "checks": {
                "contact_maintained": checks["contact_maintained"],
                "normal_force": checks["normal_force"],
                "friction_direction_or_balance": checks["friction_direction_or_balance"],
                "friction_regime": checks["friction_regime"],
            },
        },
        invariant_errors={
            "trajectory_fit_max_abs_m_s": fit_residual,
            "trajectory_fit_limit_m_s": policy.incline_fit_residual_abs_tolerance,
            "acceleration_abs_m_s2": abs_error,
            "acceleration_rel": rel_error,
            "checks": checks,
        },
        warnings=(
            "Chrono NSC uses one Coulomb coefficient for the contact cone; the textbook target treats the supplied coefficient as kinetic in slip and as an available static bound in stick.",
        ),
        artifacts=(
            {
                "kind": "in_memory_velocity_trajectory",
                "sample_count": len(samples),
                "fit_sample_count": len(fit_samples),
            },
        ),
        modeling_assumptions=(
            "The block and plane are finite rigid bodies in a ramp-fixed frame.",
            "Acceleration is estimated from Chrono velocity samples after the first 20 percent transient; it is not prescribed.",
            "Contact force, regime, and friction direction/balance are read from the simulated state.",
        ),
    )


def simulate_collision_restitution(
    *,
    m1: float,
    m2: float,
    v1: float,
    v2: float,
    restitution: float,
) -> ChronoResult:
    raw_inputs = {
        "m1": repr(m1),
        "m2": repr(m2),
        "v1": repr(v1),
        "v2": repr(v2),
        "restitution": repr(restitution),
    }
    try:
        mass_1 = _positive(m1, name="m1")
        mass_2 = _positive(m2, name="m2")
        velocity_1 = _finite(v1, name="v1")
        velocity_2 = _finite(v2, name="v2")
        coefficient = _bounded(restitution, name="restitution", lower=0.0, upper=1.0, inclusive=True)
        if velocity_1 <= velocity_2:
            raise ValueError("v1 must exceed v2 so the two bodies approach")
    except (TypeError, ValueError) as exc:
        return error_result(
            case_id="collision_restitution",
            observable="post_impact_v1",
            unit="m/s",
            time_step=DEFAULT_CHRONO_POLICY.collision_step_s,
            duration=DEFAULT_CHRONO_POLICY.collision_duration_s,
            message=f"invalid collision scene input: {exc}",
            initial_conditions={"raw_inputs": raw_inputs},
        )
    initial = {
        "m1_kg": mass_1,
        "m2_kg": mass_2,
        "v1_m_s": velocity_1,
        "v2_m_s": velocity_2,
        "target_restitution": coefficient,
        "radius_m": COLLISION_RADIUS_M,
        "initial_x1_m": -0.3,
        "initial_x2_m": 0.3,
        "gravity_m_s2": [0.0, 0.0, 0.0],
        "collision_envelope_m": COLLISION_ENVELOPE_M,
        "collision_safe_margin_m": COLLISION_SAFE_MARGIN_M,
        "duration_s": DEFAULT_CHRONO_POLICY.collision_duration_s,
    }
    return _dispatch_scene(
        import_state=import_chrono(),
        case_id="collision_restitution",
        observable="post_impact_v1",
        unit="m/s",
        time_step=DEFAULT_CHRONO_POLICY.collision_step_s,
        duration=DEFAULT_CHRONO_POLICY.collision_duration_s,
        initial_conditions=initial,
        scene=lambda adapter: _simulate_collision(adapter, initial),
    )


def _simulate_collision(adapter: ChronoAdapter, initial: Mapping[str, Any]) -> ChronoResult:
    policy = DEFAULT_CHRONO_POLICY
    m1 = float(initial["m1_kg"])
    m2 = float(initial["m2_kg"])
    v1 = float(initial["v1_m_s"])
    v2 = float(initial["v2_m_s"])
    restitution = float(initial["target_restitution"])
    radius = float(initial["radius_m"])
    x1 = float(initial["initial_x1_m"])
    x2 = float(initial["initial_x2_m"])
    system, solver = adapter.new_nsc_system(gravity=(0.0, 0.0, 0.0))
    material = adapter.contact_material_nsc(friction=0.0, restitution=restitution)

    volume = (4.0 / 3.0) * math.pi * radius ** 3
    body_1 = adapter.easy_sphere(radius=radius, density=m1 / volume, material=material)
    body_2 = adapter.easy_sphere(radius=radius, density=m2 / volume, material=material)
    for body in (body_1, body_2):
        adapter.disable_sleeping(body)
    adapter.set_position(body_1, (x1, 0.0, 0.0))
    adapter.set_position(body_2, (x2, 0.0, 0.0))
    adapter.set_linear_velocity(body_1, (v1, 0.0, 0.0))
    adapter.set_linear_velocity(body_2, (v2, 0.0, 0.0))
    adapter.add(system, body_1)
    adapter.add(system, body_2)

    step = policy.collision_step_s
    contact_start: float | None = None
    separation_time: float | None = None
    sample_count = 1
    while adapter.time(system) + step / 2.0 <= policy.collision_duration_s:
        adapter.step(system, step)
        sample_count += 1
        current_time = adapter.time(system)
        pos_1 = adapter.position(body_1)
        pos_2 = adapter.position(body_2)
        vel_1 = adapter.linear_velocity(body_1)[0]
        vel_2 = adapter.linear_velocity(body_2)[0]
        separation = pos_2[0] - pos_1[0]
        velocities_changed = abs(vel_1 - v1) > 1e-6 or abs(vel_2 - v2) > 1e-6
        if contact_start is None and (
            separation <= 2.0 * radius + 2.0 * step * (v1 - v2)
            or velocities_changed
        ):
            contact_start = current_time
        if (
            contact_start is not None
            and separation_time is None
            and separation > 2.0 * radius + 0.001
            and vel_2 > vel_1
        ):
            separation_time = current_time

    final_position_1 = adapter.position(body_1)
    final_position_2 = adapter.position(body_2)
    final_velocity_1 = adapter.linear_velocity(body_1)
    final_velocity_2 = adapter.linear_velocity(body_2)
    observed_v1 = final_velocity_1[0]
    observed_v2 = final_velocity_2[0]
    expected_v1 = (
        m1 * v1 + m2 * v2 - m2 * restitution * (v1 - v2)
    ) / (m1 + m2)
    expected_v2 = expected_v1 + restitution * (v1 - v2)
    abs_error, rel_error = comparison_errors(observed_v1, expected_v1)
    v2_abs_error, v2_rel_error = comparison_errors(observed_v2, expected_v2)
    initial_momentum = m1 * v1 + m2 * v2
    final_momentum = m1 * observed_v1 + m2 * observed_v2
    momentum_relative_error = abs(final_momentum - initial_momentum) / max(
        abs(initial_momentum),
        m1 * abs(v1) + m2 * abs(v2),
        1e-12,
    )
    realized_restitution = (observed_v2 - observed_v1) / (v1 - v2)
    restitution_error = abs(realized_restitution - restitution)
    expected_event_time = (
        (x2 - x1 - 2.0 * radius) / (v1 - v2)
    )
    event_time_error = (
        abs(contact_start - expected_event_time)
        if contact_start is not None
        else policy.collision_duration_s
    )
    initial_ke = 0.5 * m1 * v1 * v1 + 0.5 * m2 * v2 * v2
    final_ke = 0.5 * m1 * observed_v1 * observed_v1 + 0.5 * m2 * observed_v2 * observed_v2
    expected_ke = 0.5 * m1 * expected_v1 * expected_v1 + 0.5 * m2 * expected_v2 * expected_v2
    kinetic_energy_relative_error = abs(final_ke - expected_ke) / max(expected_ke, initial_ke, 1e-12)
    mass_error = max(
        abs(adapter.mass(body_1) - m1),
        abs(adapter.mass(body_2) - m2),
    )
    checks = {
        "contact_started": contact_start is not None,
        "bodies_separated": separation_time is not None,
        "v1_agreement": comparison_passed(
            observed_v1,
            expected_v1,
            absolute_tolerance=policy.collision_velocity_abs_tolerance,
            relative_tolerance=policy.collision_velocity_rel_tolerance,
        ),
        "v2_agreement": comparison_passed(
            observed_v2,
            expected_v2,
            absolute_tolerance=policy.collision_velocity_abs_tolerance,
            relative_tolerance=policy.collision_velocity_rel_tolerance,
        ),
        "momentum": momentum_relative_error <= policy.collision_momentum_rel_tolerance,
        "signed_restitution": restitution_error <= policy.collision_restitution_abs_tolerance,
        "event_timing": event_time_error <= policy.collision_event_time_abs_tolerance,
        "mass_realization": mass_error <= 1e-9,
    }
    status = "passed" if all(checks.values()) else "failed"
    return ChronoResult(
        case_id="collision_restitution",
        status=status,
        observable="post_impact_v1",
        value=observed_v1,
        unit="m/s",
        analytic_value=expected_v1,
        abs_error=abs_error,
        relative_error=rel_error,
        chrono_version=adapter.version,
        solver=solver,
        contact_method="NSC:frictionless_restitution",
        time_step=step,
        duration=adapter.time(system),
        initial_conditions=initial,
        final_state={
            "body_1_position_m": list(final_position_1),
            "body_2_position_m": list(final_position_2),
            "body_1_velocity_m_s": list(final_velocity_1),
            "body_2_velocity_m_s": list(final_velocity_2),
            "expected_v2_m_s": expected_v2,
            "realized_restitution": realized_restitution,
            "contact_start_s": contact_start,
            "separation_time_s": separation_time,
            "contact_duration_s": (
                separation_time - contact_start
                if separation_time is not None and contact_start is not None
                else None
            ),
        },
        constraint_errors={
            "momentum_relative": momentum_relative_error,
            "momentum_relative_limit": policy.collision_momentum_rel_tolerance,
            "signed_restitution_absolute": restitution_error,
            "signed_restitution_absolute_limit": policy.collision_restitution_abs_tolerance,
            "event_time_absolute_s": event_time_error,
            "event_time_absolute_limit_s": policy.collision_event_time_abs_tolerance,
            "mass_realization_absolute_kg": mass_error,
            "checks": {
                "contact_started": checks["contact_started"],
                "bodies_separated": checks["bodies_separated"],
                "momentum": checks["momentum"],
                "signed_restitution": checks["signed_restitution"],
                "event_timing": checks["event_timing"],
            },
        },
        invariant_errors={
            "v1_absolute_m_s": abs_error,
            "v1_relative": rel_error,
            "v2_absolute_m_s": v2_abs_error,
            "v2_relative": v2_rel_error,
            "kinetic_energy_relative": kinetic_energy_relative_error,
            "initial_kinetic_energy_J": initial_ke,
            "final_kinetic_energy_J": final_ke,
            "checks": checks,
        },
        warnings=(
            "Target restitution is a contact-material input; realized signed restitution is measured independently from the two final velocities.",
        ),
        artifacts=(
            {
                "kind": "in_memory_contact_event_summary",
                "sample_count": sample_count,
                "contact_detected": contact_start is not None,
                "separation_detected": separation_time is not None,
            },
        ),
        modeling_assumptions=(
            "Two finite rigid spheres collide collinearly in zero gravity with zero friction.",
            "Post-impact state is accepted only after both contact start and later separation are observed.",
            "No analytic post-impact velocity is used to initialize or overwrite either Chrono body.",
        ),
    )


def simulate_massive_pulley(
    *,
    m1: float,
    m2: float,
    inertia: float,
    radius: float,
) -> ChronoResult:
    raw_inputs = {
        "m1": repr(m1),
        "m2": repr(m2),
        "inertia": repr(inertia),
        "radius": repr(radius),
    }
    try:
        mass_1 = _positive(m1, name="m1")
        mass_2 = _positive(m2, name="m2")
        pulley_inertia = _positive(inertia, name="inertia")
        pulley_radius = _positive(radius, name="radius")
        if mass_1 == mass_2:
            raise ValueError("m1 and m2 must differ for the Phase 51 dynamic scene")
    except (TypeError, ValueError) as exc:
        return error_result(
            case_id="massive_pulley",
            observable="heavier_mass_downward_acceleration",
            unit="m/s^2",
            time_step=DEFAULT_CHRONO_POLICY.pulley_step_s,
            duration=DEFAULT_CHRONO_POLICY.pulley_duration_s,
            message=f"invalid massive-pulley scene input: {exc}",
            initial_conditions={"raw_inputs": raw_inputs},
            contact_method="constraint_driveline:no_contact",
        )
    initial = {
        "m1_kg": mass_1,
        "m2_kg": mass_2,
        "pulley_inertia_kg_m2": pulley_inertia,
        "pulley_radius_m": pulley_radius,
        "gravity_m_s2": G,
        "mass_1_applied_gravity_load_Nm": mass_1 * G * pulley_radius,
        "mass_2_applied_gravity_load_Nm": mass_2 * G * pulley_radius,
        "initial_shaft_speeds_rad_s": [0.0, 0.0, 0.0],
        "duration_s": DEFAULT_CHRONO_POLICY.pulley_duration_s,
    }
    return _dispatch_scene(
        import_state=import_chrono(),
        case_id="massive_pulley",
        observable="heavier_mass_downward_acceleration",
        unit="m/s^2",
        time_step=DEFAULT_CHRONO_POLICY.pulley_step_s,
        duration=DEFAULT_CHRONO_POLICY.pulley_duration_s,
        initial_conditions=initial,
        contact_method="constraint_driveline:no_contact",
        scene=lambda adapter: _simulate_massive_pulley(adapter, initial),
    )


def _simulate_massive_pulley(adapter: ChronoAdapter, initial: Mapping[str, Any]) -> ChronoResult:
    policy = DEFAULT_CHRONO_POLICY
    m1 = float(initial["m1_kg"])
    m2 = float(initial["m2_kg"])
    inertia = float(initial["pulley_inertia_kg_m2"])
    radius = float(initial["pulley_radius_m"])
    tau1 = float(initial["mass_1_applied_gravity_load_Nm"])
    tau2 = float(initial["mass_2_applied_gravity_load_Nm"])
    system, solver = adapter.new_nsc_system(gravity=(0.0, 0.0, 0.0))

    shaft_1 = adapter.new_shaft(inertia=m1 * radius * radius, applied_load=tau1)
    shaft_2 = adapter.new_shaft(inertia=m2 * radius * radius, applied_load=tau2)
    pulley = adapter.new_shaft(inertia=inertia, applied_load=0.0)
    for shaft in (shaft_1, shaft_2, pulley):
        adapter.add(system, shaft, shaft=True)

    gear_1 = adapter.new_gear(shaft_1, pulley, ratio=1.0)
    gear_2 = adapter.new_gear(shaft_2, pulley, ratio=-1.0)
    adapter.add(system, gear_1)
    adapter.add(system, gear_2)

    step = policy.pulley_step_s
    previous_time = adapter.time(system)
    previous_w1 = adapter.shaft_speed(shaft_1)
    previous_w2 = adapter.shaft_speed(shaft_2)
    gravitational_work = 0.0
    work_sample_count = 0
    while adapter.time(system) + step / 2.0 <= policy.pulley_duration_s:
        adapter.step(system, step)
        current_time = adapter.time(system)
        current_w1 = adapter.shaft_speed(shaft_1)
        current_w2 = adapter.shaft_speed(shaft_2)
        delta_time = current_time - previous_time
        if delta_time <= 0.0:
            raise ValueError("PyChrono shaft time did not advance")
        gravitational_work += (
            tau1 * 0.5 * (previous_w1 + current_w1) * delta_time
            + tau2 * 0.5 * (previous_w2 + current_w2) * delta_time
        )
        previous_time = current_time
        previous_w1 = current_w1
        previous_w2 = current_w2
        work_sample_count += 1

    elapsed = adapter.time(system)
    q1 = adapter.shaft_position(shaft_1)
    q2 = adapter.shaft_position(shaft_2)
    qp = adapter.shaft_position(pulley)
    w1 = adapter.shaft_speed(shaft_1)
    w2 = adapter.shaft_speed(shaft_2)
    wp = adapter.shaft_speed(pulley)
    alpha1 = adapter.shaft_acceleration(shaft_1)
    alpha2 = adapter.shaft_acceleration(shaft_2)
    alpha_p = adapter.shaft_acceleration(pulley)
    reaction_1 = adapter.gear_reaction_1(gear_1)
    reaction_2 = adapter.gear_reaction_1(gear_2)
    direct_violation_1 = adapter.gear_constraint_violation(gear_1)
    direct_violation_2 = adapter.gear_constraint_violation(gear_2)

    heavier_is_2 = m2 > m1
    measured_mass_2_downward_acceleration = -wp * radius / max(elapsed, 1e-12)
    observed_acceleration = (
        measured_mass_2_downward_acceleration
        if heavier_is_2
        else -measured_mass_2_downward_acceleration
    )
    direct_acceleration = (
        -alpha_p * radius
        if heavier_is_2
        else alpha_p * radius
    )
    expected_acceleration = abs(m2 - m1) * G / (
        m1 + m2 + inertia / (radius * radius)
    )
    abs_error, rel_error = comparison_errors(observed_acceleration, expected_acceleration)
    acceleration_consistency = abs(observed_acceleration - direct_acceleration)

    speed_constraint_1 = abs(w1 - wp)
    speed_constraint_2 = abs(w2 + wp)
    position_constraint_1 = abs(q1 - qp)
    position_constraint_2 = abs(q2 + qp)
    maximum_constraint = max(
        speed_constraint_1,
        speed_constraint_2,
        position_constraint_1,
        position_constraint_2,
    )

    coordinate_gravitational_work = tau1 * q1 + tau2 * q2
    kinetic_energy = (
        0.5 * m1 * radius * radius * w1 * w1
        + 0.5 * m2 * radius * radius * w2 * w2
        + 0.5 * inertia * wp * wp
    )
    energy_relative_error = abs(kinetic_energy - gravitational_work) / max(
        abs(gravitational_work),
        1e-12,
    )
    coordinate_integration_bias = coordinate_gravitational_work - gravitational_work
    tension_1 = abs(reaction_1) / radius
    tension_2 = abs(reaction_2) / radius
    tension_difference = abs(tension_2 - tension_1)
    pulley_required_tension_difference = inertia * abs(alpha_p) / radius
    tension_difference_error = abs(
        tension_difference - pulley_required_tension_difference
    )
    free_body_residual_1 = abs(
        m1 * radius * radius * alpha1 - (tau1 + reaction_1)
    ) / max(abs(tau1), abs(reaction_1), 1e-12)
    free_body_residual_2 = abs(
        m2 * radius * radius * alpha2 - (tau2 + reaction_2)
    ) / max(abs(tau2), abs(reaction_2), 1e-12)

    checks = {
        "observable_agreement": comparison_passed(
            observed_acceleration,
            expected_acceleration,
            absolute_tolerance=policy.pulley_acceleration_abs_tolerance,
            relative_tolerance=policy.pulley_acceleration_rel_tolerance,
        ),
        "acceleration_state_consistency": acceleration_consistency <= policy.pulley_acceleration_abs_tolerance,
        "signed_no_slip": maximum_constraint <= policy.pulley_constraint_abs_tolerance,
        "energy_balance": energy_relative_error <= policy.pulley_energy_rel_tolerance,
        "tension_difference": tension_difference_error <= policy.pulley_tension_abs_tolerance,
        "mass_1_free_body": free_body_residual_1 <= policy.pulley_energy_rel_tolerance,
        "mass_2_free_body": free_body_residual_2 <= policy.pulley_energy_rel_tolerance,
        "heavier_mass_direction": observed_acceleration > 0.0,
    }
    status = "passed" if all(checks.values()) else "failed"
    return ChronoResult(
        case_id="massive_pulley",
        status=status,
        observable="heavier_mass_downward_acceleration",
        value=observed_acceleration,
        unit="m/s^2",
        analytic_value=expected_acceleration,
        abs_error=abs_error,
        relative_error=rel_error,
        chrono_version=adapter.version,
        solver=solver,
        contact_method="constraint_driveline:no_contact",
        time_step=step,
        duration=elapsed,
        initial_conditions=initial,
        final_state={
            "shaft_positions_rad": {"mass_1": q1, "mass_2": q2, "pulley": qp},
            "shaft_speeds_rad_s": {"mass_1": w1, "mass_2": w2, "pulley": wp},
            "shaft_accelerations_rad_s2": {
                "mass_1": alpha1,
                "mass_2": alpha2,
                "pulley": alpha_p,
            },
            "gear_reactions_Nm": {"mass_1": reaction_1, "mass_2": reaction_2},
            "tensions_N": {"mass_1": tension_1, "mass_2": tension_2},
            "direct_acceleration_m_s2": direct_acceleration,
            "heavier_mass": "m2" if heavier_is_2 else "m1",
        },
        constraint_errors={
            "mass_1_speed_no_slip_abs_rad_s": speed_constraint_1,
            "mass_2_speed_no_slip_abs_rad_s": speed_constraint_2,
            "mass_1_position_no_slip_abs_rad": position_constraint_1,
            "mass_2_position_no_slip_abs_rad": position_constraint_2,
            "constraint_limit": policy.pulley_constraint_abs_tolerance,
            "chrono_direct_constraint_violations": {
                "gear_1": direct_violation_1,
                "gear_2": direct_violation_2,
            },
            "checks": {
                "signed_no_slip": checks["signed_no_slip"],
                "heavier_mass_direction": checks["heavier_mass_direction"],
            },
        },
        invariant_errors={
            "energy_balance_relative": energy_relative_error,
            "energy_balance_relative_limit": policy.pulley_energy_rel_tolerance,
            "tension_difference_absolute_N": tension_difference_error,
            "tension_difference_absolute_limit_N": policy.pulley_tension_abs_tolerance,
            "mass_1_free_body_relative": free_body_residual_1,
            "mass_2_free_body_relative": free_body_residual_2,
            "acceleration_state_consistency_abs_m_s2": acceleration_consistency,
            "gravitational_work_J": gravitational_work,
            "coordinate_gravitational_work_J": coordinate_gravitational_work,
            "coordinate_integration_bias_J": coordinate_integration_bias,
            "work_quadrature": "trapezoidal_from_engine_shaft_speeds",
            "work_sample_count": work_sample_count,
            "kinetic_energy_J": kinetic_energy,
            "checks": checks,
        },
        warnings=(
            "This is Chrono's reduced-coordinate driveline model: ChShaft inertias and ChShaftsGear constraints are stepped by the real ChSystem solver rather than represented by decorative 3-D bodies.",
        ),
        artifacts=(
            {
                "kind": "chrono_constraint_state",
                "shaft_count": 3,
                "gear_constraint_count": 2,
            },
        ),
        modeling_assumptions=(
            "Each translating mass is mapped to a shaft inertia m*R^2 and an absolute gravity load m*g*R.",
            "Two signed ChShaftsGear constraints impose w_mass1=w_pulley and w_mass2=-w_pulley.",
            "Acceleration is measured from stepped shaft state; tension is measured from gear reactions; the analytic target is comparison-only.",
            "Applied-load work is integrated by trapezoidal quadrature over consecutive engine shaft-speed states; the raw coordinate work and semi-implicit integration bias are reported separately.",
        ),
    )


def _dispatch_scene(
    *,
    import_state: ChronoImport,
    case_id: str,
    observable: str,
    unit: str,
    time_step: float,
    duration: float,
    initial_conditions: Mapping[str, Any],
    scene: Callable[[ChronoAdapter], ChronoResult],
    contact_method: str | None = None,
) -> ChronoResult:
    if import_state.status == "unavailable":
        return unavailable_result(
            case_id=case_id,
            observable=observable,
            unit=unit,
            time_step=time_step,
            duration=duration,
            message=import_state.message,
            initial_conditions=initial_conditions,
            contact_method=contact_method,
        )
    if import_state.status != "available" or import_state.module is None:
        return error_result(
            case_id=case_id,
            observable=observable,
            unit=unit,
            time_step=time_step,
            duration=duration,
            message=import_state.message,
            initial_conditions=initial_conditions,
            contact_method=contact_method,
        )
    adapter = ChronoAdapter(import_state.module)
    try:
        return scene(adapter)
    except Exception as exc:
        return error_result(
            case_id=case_id,
            observable=observable,
            unit=unit,
            time_step=time_step,
            duration=duration,
            message=f"PyChrono scene failed closed: {type(exc).__name__}: {exc}",
            initial_conditions=initial_conditions,
            chrono_version=adapter.version,
            contact_method=contact_method,
        )


def _linear_fit(samples: list[tuple[float, float]]) -> tuple[float, float, float]:
    if len(samples) < 2:
        raise ValueError("at least two trajectory samples are required")
    mean_t = sum(item[0] for item in samples) / len(samples)
    mean_v = sum(item[1] for item in samples) / len(samples)
    denominator = sum((item[0] - mean_t) ** 2 for item in samples)
    if denominator <= 0.0:
        raise ValueError("trajectory sample times are degenerate")
    slope = sum(
        (item[0] - mean_t) * (item[1] - mean_v)
        for item in samples
    ) / denominator
    intercept = mean_v - slope * mean_t
    residual = max(
        abs(item[1] - (intercept + slope * item[0]))
        for item in samples
    )
    return slope, intercept, residual


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not bool")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _positive(value: Any, *, name: str) -> float:
    parsed = _finite(value, name=name)
    if parsed <= 0.0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _nonnegative(value: Any, *, name: str) -> float:
    parsed = _finite(value, name=name)
    if parsed < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _bounded(
    value: Any,
    *,
    name: str,
    lower: float,
    upper: float,
    inclusive: bool = False,
) -> float:
    parsed = _finite(value, name=name)
    if inclusive:
        valid = lower <= parsed <= upper
    else:
        valid = lower < parsed < upper
    if not valid:
        bracket = "[" if inclusive else "("
        close = "]" if inclusive else ")"
        raise ValueError(f"{name} must be in {bracket}{lower}, {upper}{close}")
    return parsed


__all__ = [
    "ChronoResult",
    "simulate_collision_restitution",
    "simulate_incline_friction",
    "simulate_massive_pulley",
    "simulate_rolling_down_ramp",
]
