from __future__ import annotations

import math
from typing import TYPE_CHECKING

import sympy as sp

from engine.models import CanonicalProblem, Quantity
from engine.physics_core import symbols as S
from engine.physics_core.units import angle_to_radians
from .typed_model import (
    Body,
    Constraint,
    CoordinateFrame,
    Dimension,
    Force,
    QuantityValue,
    TypedDynamicsModel,
    Vector2,
    string_length_constraint,
)

if TYPE_CHECKING:
    from .model_types import PhysicalModel


def _source_metadata(
    canonical: CanonicalProblem,
    key: str,
) -> tuple[str | None, float | None]:
    if canonical.canonical_v2 is None:
        return None, None
    for fact in canonical.canonical_v2.facts:
        if fact.compatibility_key == key or fact.symbol == key:
            uncertainty = None
            if fact.confidence is not None:
                uncertainty = max(0.0, min(1.0, 1.0 - float(fact.confidence)))
            return fact.fact_id, uncertainty
    return None, None


def _quantity(
    canonical: CanonicalProblem,
    key: str,
    *,
    dimension: str,
    si_unit: str,
    aliases: tuple[str, ...] = (),
) -> QuantityValue | None:
    selected_key = next(
        (candidate for candidate in (key, *aliases) if candidate in canonical.knowns),
        None,
    )
    if selected_key is None:
        return None
    source_fact_id, uncertainty = _source_metadata(canonical, selected_key)
    return QuantityValue.from_quantity(
        canonical.knowns[selected_key],
        dimension=dimension,
        si_unit=si_unit,
        source_fact_id=source_fact_id,
        uncertainty=uncertainty,
    )


def _point(frame_id: str, x=0, y=0) -> Vector2:
    return Vector2(x, y, frame_id, Dimension.LENGTH)


def _force(
    *,
    force_id: str,
    kind: str,
    body_id: str,
    frame_id: str,
    x,
    y,
    point: Vector2 | None = None,
    relation=None,
    state: str | None = None,
    source_fact_id: str | None = None,
) -> Force:
    return Force(
        id=force_id,
        kind=kind,
        body_id=body_id,
        application_point=point or _point(frame_id),
        vector=Vector2(x, y, frame_id, Dimension.FORCE),
        constitutive_relation=relation,
        active_state=state,
        source_fact_id=source_fact_id,
    )


def _incline_model(canonical: CanonicalProblem) -> TypedDynamicsModel:
    theta_quantity = canonical.knowns.get("theta")
    theta_radians = angle_to_radians(theta_quantity) if theta_quantity else 0.0
    model = TypedDynamicsModel(
        system_type=canonical.system_type,
        frames={
            "world": CoordinateFrame(id="world"),
            "incline": CoordinateFrame(
                id="incline",
                basis_x=(math.cos(theta_radians), -math.sin(theta_radians)),
                basis_y=(math.sin(theta_radians), math.cos(theta_radians)),
                angular_positive=1,
                parent_frame="world",
            ),
        },
        display_metadata={
            "positive_x": "경사면 아래쪽",
            "positive_y": "경사면 바깥쪽",
        },
    )
    mass = _quantity(
        canonical,
        "m",
        dimension=Dimension.MASS,
        si_unit="kg",
    )
    theta = _quantity(
        canonical,
        "theta",
        dimension=Dimension.DIMENSIONLESS,
        si_unit="deg",
    )
    gravity = _quantity(
        canonical,
        "g",
        dimension=Dimension.ACCELERATION,
        si_unit="m/s^2",
    )
    for key, value in (("m", mass), ("theta", theta), ("g", gravity)):
        if value is not None:
            model.quantities[key] = value
    model.bodies["body"] = Body(
        id="body",
        kind="particle",
        frame_id="incline",
        mass=mass,
        center_of_mass=_point("incline"),
        geometry={"surface": "incline"},
    )
    model.forces.extend(
        [
            _force(
                force_id="body_weight",
                kind="weight",
                body_id="body",
                frame_id="incline",
                x=S.m * S.g * sp.sin(S.theta),
                y=-S.m * S.g * sp.cos(S.theta),
                source_fact_id=mass.source_fact_id if mass else None,
            ),
            _force(
                force_id="body_normal",
                kind="normal",
                body_id="body",
                frame_id="incline",
                x=0,
                y=S.T,
                relation=sp.Eq(S.T, S.m * S.g * sp.cos(S.theta)),
                state="contact",
            ),
        ]
    )
    if canonical.subtype == "with_friction" or canonical.flags.get("friction"):
        coefficient_key = (
            "mu_k"
            if canonical.friction_type == "static" and "mu_k" in canonical.knowns
            else "mu"
            if "mu" in canonical.knowns
            else "mu_k"
        )
        coefficient = _quantity(
            canonical,
            coefficient_key,
            dimension=Dimension.DIMENSIONLESS,
            si_unit="",
        )
        if coefficient is not None:
            model.quantities[coefficient_key] = coefficient
        model.forces.append(
            _force(
                force_id="body_friction",
                kind="friction",
                body_id="body",
                frame_id="incline",
                x=-S.mu * S.m * S.g * sp.cos(S.theta),
                y=0,
                relation=sp.Eq(S.F, S.mu * S.T),
                state="opposes_positive_down_slope_motion",
                source_fact_id=coefficient.source_fact_id if coefficient else None,
            )
        )
    model.constraints.append(
        Constraint(
            id="incline_contact",
            kind="contact",
            frame_id="incline",
            dimension=Dimension.FORCE,
            expression=S.T - S.m * S.g * sp.cos(S.theta),
            display="N - m*g*cos(theta) = 0",
            related_bodies=["body"],
        )
    )
    model.validate()
    return model


def _collision_model(canonical: CanonicalProblem) -> TypedDynamicsModel:
    v1, v2, v1f, v2f = sp.symbols("v1 v2 v1f v2f", real=True)
    restitution = sp.Symbol("e", real=True)
    model = TypedDynamicsModel(
        system_type=canonical.system_type,
        frames={
            "collision": CoordinateFrame(id="collision"),
        },
        display_metadata={"positive_x": "충돌선의 양의 방향"},
    )
    mass1 = _quantity(
        canonical,
        "m1",
        dimension=Dimension.MASS,
        si_unit="kg",
    )
    mass2 = _quantity(
        canonical,
        "m2",
        dimension=Dimension.MASS,
        si_unit="kg",
    )
    for key, dimension, unit in (
        ("v1", Dimension.VELOCITY, "m/s"),
        ("v2", Dimension.VELOCITY, "m/s"),
        ("e", Dimension.DIMENSIONLESS, ""),
    ):
        value = _quantity(canonical, key, dimension=dimension, si_unit=unit)
        if value is not None:
            model.quantities[key] = value
    if mass1 is not None:
        model.quantities["m1"] = mass1
    if mass2 is not None:
        model.quantities["m2"] = mass2
    model.bodies = {
        "body_1": Body(
            id="body_1",
            kind="particle",
            frame_id="collision",
            mass=mass1,
            center_of_mass=_point("collision"),
        ),
        "body_2": Body(
            id="body_2",
            kind="particle",
            frame_id="collision",
            mass=mass2,
            center_of_mass=_point("collision"),
        ),
    }
    model.constraints.append(
        Constraint(
            id="linear_momentum",
            kind="linear_momentum",
            frame_id="collision",
            dimension="momentum",
            expression=S.m1 * v1 + S.m2 * v2 - S.m1 * v1f - S.m2 * v2f,
            display="m1*v1 + m2*v2 - m1*v1f - m2*v2f = 0",
            related_bodies=["body_1", "body_2"],
        )
    )
    if canonical.flags.get("perfectly_inelastic"):
        model.constraints.append(
            Constraint(
                id="common_final_velocity",
                kind="common_final_velocity",
                frame_id="collision",
                dimension=Dimension.VELOCITY,
                expression=v1f - v2f,
                display="v1f - v2f = 0",
                related_bodies=["body_1", "body_2"],
            )
        )
    elif canonical.flags.get("elastic") or "e" in canonical.knowns:
        model.constraints.append(
            Constraint(
                id="restitution",
                kind="restitution",
                frame_id="collision",
                dimension=Dimension.VELOCITY,
                expression=v2f - v1f - restitution * (v1 - v2),
                display="v2f - v1f - e*(v1-v2) = 0",
                related_bodies=["body_1", "body_2"],
            )
        )
    model.validate()
    return model


def _massive_pulley_model(canonical: CanonicalProblem) -> TypedDynamicsModel:
    model = TypedDynamicsModel(
        system_type=canonical.system_type,
        frames={
            "world": CoordinateFrame(id="world"),
            "body_1_up": CoordinateFrame(
                id="body_1_up",
                basis_x=(0, 1),
                basis_y=(-1, 0),
                parent_frame="world",
            ),
            "body_2_down": CoordinateFrame(
                id="body_2_down",
                basis_x=(0, -1),
                basis_y=(1, 0),
                parent_frame="world",
            ),
            "pulley": CoordinateFrame(
                id="pulley",
                angular_positive=-1,
                parent_frame="world",
            ),
        },
        display_metadata={
            "body_1_positive": "위쪽",
            "body_2_positive": "아래쪽",
            "angular_positive": "m2 하강에 대응하는 시계방향",
        },
    )
    mass1 = _quantity(
        canonical,
        "m1",
        dimension=Dimension.MASS,
        si_unit="kg",
    )
    mass2 = _quantity(
        canonical,
        "m2",
        dimension=Dimension.MASS,
        si_unit="kg",
    )
    inertia = _quantity(
        canonical,
        "I",
        aliases=("Ip",),
        dimension=Dimension.INERTIA,
        si_unit="kg*m^2",
    )
    radius = _quantity(
        canonical,
        "R",
        aliases=("Rp",),
        dimension=Dimension.LENGTH,
        si_unit="m",
    )
    gravity = _quantity(
        canonical,
        "g",
        dimension=Dimension.ACCELERATION,
        si_unit="m/s^2",
    )
    for key, value in (
        ("m1", mass1),
        ("m2", mass2),
        ("I", inertia),
        ("R", radius),
        ("g", gravity),
    ):
        if value is not None:
            model.quantities[key] = value
    model.bodies = {
        "body_1": Body(
            id="body_1",
            kind="particle",
            frame_id="body_1_up",
            mass=mass1,
            center_of_mass=_point("body_1_up"),
        ),
        "body_2": Body(
            id="body_2",
            kind="particle",
            frame_id="body_2_down",
            mass=mass2,
            center_of_mass=_point("body_2_down"),
        ),
        "pulley": Body(
            id="pulley",
            kind="rigid_body_2d",
            frame_id="pulley",
            center_of_mass=_point("pulley"),
            inertia_about_com=inertia,
            geometry={"radius": radius.magnitude if radius else None},
        ),
    }
    model.forces.extend(
        [
            _force(
                force_id="body_1_tension",
                kind="tension",
                body_id="body_1",
                frame_id="body_1_up",
                x=S.T1,
                y=0,
            ),
            _force(
                force_id="body_1_weight",
                kind="weight",
                body_id="body_1",
                frame_id="body_1_up",
                x=-S.m1 * S.g,
                y=0,
            ),
            _force(
                force_id="body_2_weight",
                kind="weight",
                body_id="body_2",
                frame_id="body_2_down",
                x=S.m2 * S.g,
                y=0,
            ),
            _force(
                force_id="body_2_tension",
                kind="tension",
                body_id="body_2",
                frame_id="body_2_down",
                x=-S.T2,
                y=0,
            ),
            _force(
                force_id="pulley_left_tension",
                kind="tension",
                body_id="pulley",
                frame_id="pulley",
                x=0,
                y=-S.T1,
                point=_point("pulley", -S.R, 0),
            ),
            _force(
                force_id="pulley_right_tension",
                kind="tension",
                body_id="pulley",
                frame_id="pulley",
                x=0,
                y=-S.T2,
                point=_point("pulley", S.R, 0),
            ),
        ]
    )
    q1, q2, total_length = sp.symbols("q1 q2 L", real=True)
    model.constraints.extend(
        [
            string_length_constraint(
                frame_id="world",
                first=q1,
                second=q2,
                total_length=total_length,
                related_bodies=["body_1", "body_2"],
            ),
            Constraint(
                id="pulley_no_slip",
                kind="no_slip_pulley",
                frame_id="pulley",
                dimension=Dimension.ACCELERATION,
                expression=S.a - S.alpha * S.R,
                display="a - alpha*R = 0",
                related_bodies=["body_1", "body_2", "pulley"],
            ),
        ]
    )
    model.validate()
    return model


def build_typed_dynamics_model(
    canonical: CanonicalProblem,
    legacy_model: "PhysicalModel | None" = None,
) -> TypedDynamicsModel | None:
    """Build only the three Phase 45 vertical slices.

    legacy_model is accepted to make the compatibility adapter explicit; typed
    construction does not depend on legacy direction strings or external-engine
    data structures.
    """

    del legacy_model
    if canonical.system_type == "particle_on_incline":
        return _incline_model(canonical)
    if canonical.system_type == "collision_1d":
        return _collision_model(canonical)
    if canonical.system_type == "massive_pulley_atwood":
        return _massive_pulley_model(canonical)
    return None
