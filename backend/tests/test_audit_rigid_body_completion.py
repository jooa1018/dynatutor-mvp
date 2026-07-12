from __future__ import annotations

from engine.models import CanonicalProblem, Quantity
from engine.solvers.rigid_body_2d.acceleration import PlaneRigidBodyAccelerationSolver


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def test_relative_to_a_wording_does_not_assume_a_is_fixed():
    problem = CanonicalProblem(
        system_type="plane_rigid_body_acceleration",
        raw_text="B점은 A점에 대한 위치벡터를 가진다. B점 가속도는?",
        knowns={
            "omega": q("omega", 2.0, "rad/s"),
            "alpha": q("alpha", 1.0, "rad/s^2"),
        },
        coordinate_data={
            "rBAx": 1.0,
            "rBAy": 0.0,
            "omega_sign": 1.0,
            "alpha_sign": 1.0,
        },
        requested_outputs=["acceleration"],
    )

    result = PlaneRigidBodyAccelerationSolver().solve(problem)

    assert not result.ok
    assert any("A점 가속도" in error for error in result.verification.errors)


def test_fixed_a_allows_direction_free_acceleration_magnitude():
    problem = CanonicalProblem(
        system_type="plane_rigid_body_acceleration",
        raw_text="A점이 고정된 강체에서 r=1m, omega=2rad/s, alpha=1rad/s²이다. B점 가속도 크기는?",
        knowns={
            "r": q("r", 1.0, "m"),
            "omega": q("omega", 2.0, "rad/s"),
            "alpha": q("alpha", 1.0, "rad/s^2"),
        },
        requested_outputs=["acceleration"],
    )

    result = PlaneRigidBodyAccelerationSolver().solve(problem)

    assert result.ok
    assert result.answer is not None
