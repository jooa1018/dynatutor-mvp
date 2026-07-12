from __future__ import annotations

import math

from engine.models import CanonicalProblem, Quantity
from engine.solvers.pulley.atwood import AtwoodPulleySolver


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def _solve_atwood(m1: float, m2: float):
    result = AtwoodPulleySolver().solve(
        CanonicalProblem(
            system_type="pulley_atwood",
            raw_text="m2 아래를 양의 방향으로 잡은 Atwood 계",
            knowns={
                "m1": q("m1", m1, "kg"),
                "m2": q("m2", m2, "kg"),
                "g": q("g", 9.81, "m/s^2"),
            },
            requested_outputs=["acceleration", "tension"],
        )
    )
    assert result.ok
    return result


def test_swapping_atwood_labels_reverses_acceleration_not_magnitude():
    forward = _solve_atwood(5.0, 2.0)
    swapped = _solve_atwood(2.0, 5.0)

    assert forward.answer is not None and swapped.answer is not None
    assert math.isclose(forward.answer.numeric, -swapped.answer.numeric, rel_tol=1e-10)

    forward_tension = next(item.numeric for item in forward.answers if item.symbol == "T")
    swapped_tension = next(item.numeric for item in swapped.answers if item.symbol == "T")
    assert math.isclose(forward_tension, swapped_tension, rel_tol=1e-10)


def test_equal_atwood_masses_keep_zero_signed_acceleration():
    result = _solve_atwood(3.0, 3.0)

    assert result.answer is not None
    assert result.answer.numeric == 0.0
