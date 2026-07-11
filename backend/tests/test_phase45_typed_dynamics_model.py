from __future__ import annotations

import math

import pytest
import sympy as sp

from engine.canonical.models import CanonicalProblemV2, ExtractedFact
from engine.equation_generators.particle_newton import build_particle_newton_system
from engine.model_builder import build_physical_model
from engine.model_builder.typed_model import (
    Body,
    CoordinateFrame,
    Dimension,
    Force,
    QuantityValue,
    TypedDynamicsModel,
    Vector2,
    rolling_no_slip_constraint,
    string_length_constraint,
)
from engine.models import CanonicalProblem, Quantity
from engine.physics_core.units import angle_to_radians, radians_to_degrees
from engine.solvers.collision import Collision1DSolver
from engine.solvers.incline import InclineWithFrictionSolver
from engine.solvers.pulley.massive_pulley import MassivePulleyAtwoodSolver


def _q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit, source_text=f"{value} {unit}")


def _incline() -> CanonicalProblem:
    return CanonicalProblem(
        system_type="particle_on_incline",
        subtype="with_friction",
        friction_type="kinetic",
        flags={"friction": True},
        knowns={
            "m": _q("m", 2.0, "kg"),
            "g": _q("g", 9.81, "m/s^2"),
            "theta": _q("theta", 30.0, "deg"),
            "mu": _q("mu", 0.2, None),
        },
        requested_outputs=["acceleration"],
    )


def _collision() -> CanonicalProblem:
    return CanonicalProblem(
        system_type="collision_1d",
        flags={"elastic": False},
        knowns={
            "m1": _q("m1", 2.0, "kg"),
            "m2": _q("m2", 3.0, "kg"),
            "v1": _q("v1", 4.0, "m/s"),
            "v2": _q("v2", 0.0, "m/s"),
            "e": _q("e", 0.5, None),
        },
        requested_outputs=["post_collision_velocity"],
    )


def _massive_pulley() -> CanonicalProblem:
    return CanonicalProblem(
        system_type="massive_pulley_atwood",
        knowns={
            "m1": _q("m1", 2.0, "kg"),
            "m2": _q("m2", 4.0, "kg"),
            "I": _q("I", 0.5, "kg*m^2"),
            "R": _q("R", 0.5, "m"),
            "g": _q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration", "tension"],
    )


def test_frame_transform_round_trip_and_axis_reversal():
    model = TypedDynamicsModel(
        system_type="frame_test",
        frames={
            "world": CoordinateFrame(id="world"),
            "reversed": CoordinateFrame(
                id="reversed",
                basis_x=(-1, 0),
                basis_y=(0, -1),
                parent_frame="world",
            ),
        },
    )
    local = Vector2(3.0, -2.0, "reversed", Dimension.VELOCITY)

    world = model.vector_in_frame(local, "world")
    restored = model.vector_in_frame(world, "reversed")

    assert float(world.x) == pytest.approx(-3.0)
    assert float(world.y) == pytest.approx(2.0)
    assert float(restored.x) == pytest.approx(3.0)
    assert float(restored.y) == pytest.approx(-2.0)
    assert model.frames["reversed"].transform is not None


def test_vector_rejects_frame_and_dimension_mismatch():
    force = Vector2(1, 0, "world", Dimension.FORCE)

    with pytest.raises(ValueError, match="Dimension mismatch"):
        _ = force + Vector2(1, 0, "world", Dimension.VELOCITY)
    with pytest.raises(ValueError, match="Frame mismatch"):
        _ = force + Vector2(1, 0, "other", Dimension.FORCE)


def test_force_sum_and_moment_are_computed_from_typed_vectors():
    model = TypedDynamicsModel(
        system_type="force_test",
        frames={"world": CoordinateFrame(id="world")},
        bodies={
            "body": Body(
                id="body",
                kind="rigid_body_2d",
                frame_id="world",
                center_of_mass=Vector2(0, 0, "world", Dimension.LENGTH),
            )
        },
        forces=[
            Force(
                id="fx",
                kind="applied",
                body_id="body",
                application_point=Vector2(0, 0, "world", Dimension.LENGTH),
                vector=Vector2(3, 0, "world", Dimension.FORCE),
            ),
            Force(
                id="fy",
                kind="applied",
                body_id="body",
                application_point=Vector2(2, 0, "world", Dimension.LENGTH),
                vector=Vector2(0, 4, "world", Dimension.FORCE),
            ),
        ],
    )
    model.validate()

    total = model.sum_forces("body")
    moment = model.moment_about(
        "body",
        Vector2(0, 0, "world", Dimension.LENGTH),
    )

    assert tuple(float(value) for value in total.as_tuple()) == pytest.approx((3, 4))
    assert float(moment) == pytest.approx(8.0)


def test_degree_radian_conversion_is_explicit():
    angle = _q("theta", 180.0, "deg")

    radians = angle_to_radians(angle)

    assert radians == pytest.approx(math.pi)
    assert radians_to_degrees(radians) == pytest.approx(180.0)


def test_quantity_value_rejects_dimension_mismatch():
    with pytest.raises(ValueError, match="Expected"):
        QuantityValue.from_quantity(
            _q("m", 2.0, "kg"),
            dimension=Dimension.LENGTH,
            si_unit="m",
        )


def test_string_length_constraint_residual():
    q1, q2, length = sp.symbols("q1 q2 L")
    constraint = string_length_constraint(
        frame_id="world",
        first=q1,
        second=q2,
        total_length=length,
        related_bodies=["body_1", "body_2"],
    )

    assert constraint.frame_id == "world"
    assert constraint.dimension == Dimension.LENGTH
    assert constraint.residual({"q1": 1.25, "q2": 2.75, "L": 4.0}) == pytest.approx(0.0)


def test_rolling_constraint_v_minus_r_omega():
    velocity, radius, omega = sp.symbols("v R omega")
    constraint = rolling_no_slip_constraint(
        frame_id="world",
        velocity=velocity,
        radius=radius,
        angular_velocity=omega,
        body_id="wheel",
    )

    assert constraint.dimension == Dimension.VELOCITY
    assert constraint.residual({"v": 3.0, "R": 0.5, "omega": 6.0}) == pytest.approx(0.0)
    assert constraint.residual({"v": 3.1, "R": 0.5, "omega": 6.0}) == pytest.approx(0.1)


def test_incline_equation_generator_consumes_typed_force_sum():
    canonical = _incline()
    model = build_physical_model(canonical)

    system = build_particle_newton_system(canonical, model)

    assert model.typed_model is not None
    assert "m" in system.equations[-1].sympy_repr
    assert model.typed_model.sum_forces("body", "incline").frame_id == "incline"


def test_incline_vertical_slice_preserves_answer():
    result = InclineWithFrictionSolver().solve(_incline())

    expected = 9.81 * (math.sin(math.radians(30)) - 0.2 * math.cos(math.radians(30)))
    assert result.ok is True
    assert result.answer.numeric == pytest.approx(expected, abs=1e-5)


def test_restitution_collision_vertical_slice_preserves_answers():
    result = Collision1DSolver().solve(_collision())

    assert result.ok is True
    assert [answer.numeric for answer in result.answers] == pytest.approx([0.4, 2.4])
    assert result.verification.passed is True


def test_massive_pulley_vertical_slice_preserves_answers():
    result = MassivePulleyAtwoodSolver().solve(_massive_pulley())

    assert result.ok is True
    assert result.answers[0].numeric == pytest.approx(2.4525)
    assert result.answers[1].numeric == pytest.approx(4.905)
    assert result.answers[2].numeric == pytest.approx(24.525)
    assert result.answers[3].numeric == pytest.approx(29.43)


@pytest.mark.parametrize(
    "canonical,expected_constraints",
    [
        (_incline(), {"contact"}),
        (_collision(), {"linear_momentum", "restitution"}),
        (_massive_pulley(), {"string_length", "no_slip_pulley"}),
    ],
)
def test_vertical_slices_have_typed_frame_and_dimension_metadata(
    canonical,
    expected_constraints,
):
    model = build_physical_model(canonical)
    typed = model.typed_model

    assert typed is not None
    typed.validate()
    assert all(force.vector.frame_id for force in typed.forces)
    assert all(force.vector.dimension == Dimension.FORCE for force in typed.forces)
    assert expected_constraints.issubset(
        {constraint.kind for constraint in typed.constraints}
    )
    assert all(constraint.frame_id for constraint in typed.constraints)
    assert all(constraint.dimension for constraint in typed.constraints)


def test_typed_to_legacy_serialization_preserves_contract():
    model = build_physical_model(_incline())
    typed = model.typed_model

    payload = typed.to_legacy_dict(model)

    assert payload == model.to_dict()
    assert "typed_model" not in payload
    assert payload["forces"][0]["direction"] == "경사면 아래쪽"
    assert payload["coordinates"]["positive_directions"]["x"] == "경사면 아래쪽"



def test_typed_quantity_preserves_phase43_source_fact_id():
    canonical = _incline()
    raw = "m=2kg"
    fact = ExtractedFact(
        fact_id="fact-mass-1",
        kind="quantity",
        subject_id="body",
        symbol="m",
        value=2.0,
        unit="kg",
        dimension="mass",
        direction=None,
        source_text=raw,
        source_span=(0, len(raw)),
        provenance="explicit_text",
        confidence=0.9,
        status="explicit",
        compatibility_key="m",
        extraction_evidence={"matched_raw_text": raw},
    )
    canonical.raw_text = raw
    canonical.canonical_v2 = CanonicalProblemV2(
        schema_version="2.0",
        raw_text=raw,
        normalized_text=raw,
        language="ko",
        system_type=canonical.system_type,
        subtype=canonical.subtype,
        facts=[fact],
        assumptions=[],
        parse_candidates=[],
        requested_outputs=canonical.requested_outputs,
        flags=canonical.flags,
        objects=[],
        missing_info=[],
        conflicts=[],
        warnings=[],
        legacy_view={},
    )

    typed = build_physical_model(canonical).typed_model

    assert typed.quantities["m"].source_fact_id == "fact-mass-1"
    assert typed.quantities["m"].uncertainty == pytest.approx(0.1)
