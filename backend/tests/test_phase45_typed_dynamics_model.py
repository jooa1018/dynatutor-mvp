from __future__ import annotations

import copy
import math

import pytest
import sympy as sp

from engine.canonical.models import CanonicalProblemV2, ExtractedFact
from engine.equation_generators import energy_momentum, particle_newton
from engine.equation_generators.energy_momentum import build_energy_momentum_system
from engine.equation_generators.particle_newton import (
    build_particle_newton_system,
    solve_particle_newton_system,
)
from engine.extraction.extractor import extract_problem
from engine.model_builder import build_physical_model
from engine.model_builder import typed_builder
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
from engine import services
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




def _pulley_incline(coefficient: str) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="pulley_incline_hanging",
        friction_type="kinetic",
        knowns={
            "m1": _q("m1", 2.0, "kg"),
            "m2": _q("m2", 4.0, "kg"),
            "g": _q("g", 9.81, "m/s^2"),
            "theta": _q("theta", 30.0, "deg"),
            coefficient: _q(coefficient, 0.2, None),
        },
        requested_outputs=["acceleration"],
    )


def _legacy_generator_view(canonical: CanonicalProblem) -> dict:
    model = build_physical_model(canonical)
    legacy_newton = build_particle_newton_system(canonical)
    model.generated_equation_system = (
        legacy_newton if legacy_newton.equations else None
    )
    legacy_energy = build_energy_momentum_system(canonical)
    model.generated_energy_momentum_system = (
        legacy_energy if legacy_energy.equations else None
    )
    return model.to_dict()


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



def test_vector_add_and_scale_do_not_call_general_simplify(monkeypatch):
    def fail_simplify(*args, **kwargs):
        raise AssertionError("basic vector arithmetic must not call sp.simplify")

    monkeypatch.setattr(sp, "simplify", fail_simplify)
    x, y, scalar = sp.symbols("x y scalar")
    left = Vector2(x, y, "world", Dimension.FORCE)
    right = Vector2(y, x, "world", Dimension.FORCE)

    added = left + right
    scaled = added.scaled(scalar)

    assert added.x == x + y
    assert scaled.x == scalar * (x + y)


def test_incline_solve_reuses_prebuilt_typed_model_and_equations(monkeypatch):
    canonical = _incline()
    model = build_physical_model(canonical)

    def fail_build(*args, **kwargs):
        raise AssertionError("prebuilt generated equation system was not reused")

    monkeypatch.setattr(
        particle_newton,
        "build_particle_newton_system",
        fail_build,
    )

    result = InclineWithFrictionSolver().solve(canonical, model)

    assert result.ok is True
    assert result.answer.numeric == pytest.approx(
        9.81 * (math.sin(math.radians(30)) - 0.2 * math.cos(math.radians(30))),
        abs=1e-5,
    )


def test_user_facing_incline_request_builds_typed_model_and_equations_once(
    monkeypatch,
):
    canonical = _incline()
    counts = {"model": 0, "typed": 0, "newton": 0, "energy": 0}

    original_model = services.build_physical_model
    original_typed = typed_builder.build_typed_dynamics_model
    original_newton = particle_newton.build_particle_newton_system
    original_energy = energy_momentum.build_energy_momentum_system

    def counted_model(*args, **kwargs):
        counts["model"] += 1
        return original_model(*args, **kwargs)

    def counted_typed(*args, **kwargs):
        counts["typed"] += 1
        return original_typed(*args, **kwargs)

    def counted_newton(*args, **kwargs):
        counts["newton"] += 1
        return original_newton(*args, **kwargs)

    def counted_energy(*args, **kwargs):
        counts["energy"] += 1
        return original_energy(*args, **kwargs)

    monkeypatch.setattr(services, "extract_problem", lambda _: canonical)
    monkeypatch.setattr(services, "build_physical_model", counted_model)
    monkeypatch.setattr(typed_builder, "build_typed_dynamics_model", counted_typed)
    monkeypatch.setattr(
        particle_newton,
        "build_particle_newton_system",
        counted_newton,
    )
    monkeypatch.setattr(
        energy_momentum,
        "build_energy_momentum_system",
        counted_energy,
    )

    response = services.solve_problem("phase45 counted request")

    assert response.ok is True
    assert counts == {"model": 1, "typed": 1, "newton": 1, "energy": 1}


@pytest.mark.parametrize(
    "canonical",
    [_incline(), _collision(), _massive_pulley()],
)
def test_three_vertical_slices_match_complete_legacy_view(canonical):
    actual = build_physical_model(copy.deepcopy(canonical)).to_dict()
    expected = _legacy_generator_view(copy.deepcopy(canonical))

    assert actual == expected


def test_incline_legacy_sympy_repr_is_base_compatible():
    model = build_physical_model(_incline())

    assert model.generated_equation_system.equations[-1].sympy_repr == (
        "Eq(-g*mu*cos(theta) + g*sin(theta), a)"
    )


def test_phase45_friction_incline_supports_mu_k_locally():
    canonical = _incline()
    canonical.knowns["mu_k"] = canonical.knowns.pop("mu")
    canonical.knowns["mu_k"].symbol = "mu_k"

    result = InclineWithFrictionSolver().solve(canonical)

    assert result.ok is True
    assert result.answer.numeric == pytest.approx(
        9.81 * (math.sin(math.radians(30)) - 0.2 * math.cos(math.radians(30))),
        abs=1e-5,
    )


def test_pulley_mu_k_alias_matches_legacy_mu_solution():
    result = solve_particle_newton_system(_pulley_incline("mu_k"))
    expected = solve_particle_newton_system(_pulley_incline("mu"))

    assert result.ok is True
    assert expected.ok is True
    assert set(result.solution) == set(expected.solution)
    for symbol, value in expected.solution.items():
        assert float(result.solution[symbol]) == pytest.approx(float(value))


def test_out_of_scope_pulley_existing_mu_still_solves():
    result = solve_particle_newton_system(_pulley_incline("mu"))

    assert result.ok is True
    assert result.solution


@pytest.mark.parametrize("mass", [0.0, -1.0])
def test_incline_rejects_nonpositive_mass_explicitly(mass):
    canonical = _incline()
    canonical.knowns["m"] = _q("m", mass, "kg")

    result = InclineWithFrictionSolver().solve(canonical)

    assert result.ok is False
    assert result.unsupported_reason == "질량 m은 양수여야 합니다."
    assert result.verification.errors == [
        "잘못된 물리 입력: 질량 m은 0보다 커야 합니다."
    ]


def test_phase44_subject_binding_and_conflict_contracts_remain_intact():
    subject = extract_problem(
        "트럭은 v0=20 m/s이다. 자동차는 v0=15 m/s이다. "
        "자동차는 2 m/s²로 5초 가속한다. 자동차의 최종 속도는?"
    )
    conflict = services.solve_problem(
        "v0=0m/s라고 했지만 v0=5m/s라고도 적혀 있다. "
        "a=2m/s^2, t=3s일 때 최종속도는?"
    )

    assert subject.knowns["v0"].value == pytest.approx(15.0)
    assert subject.canonical_v2.conflicts == []
    assert conflict.ok is False
    assert conflict.answer is None
    assert conflict.clarification.rule == "contradictory_input"
