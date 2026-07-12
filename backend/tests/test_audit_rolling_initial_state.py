from __future__ import annotations

import math

from engine.models import CanonicalProblem, Quantity
from engine.solvers.rolling.rolling_energy import PureRollingEnergySolver


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def _problem(raw_text: str) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="pure_rolling_energy",
        raw_text=raw_text,
        knowns={
            "h": q("h", 1.0, "m"),
            "g": q("g", 9.81, "m/s^2"),
        },
        body_shape="solid_sphere",
        requested_outputs=["final_velocity"],
    )


def test_rolling_without_initial_state_is_underdetermined():
    result = PureRollingEnergySolver().solve(
        _problem("속이 찬 구가 미끄러지지 않고 1m 내려온다. 최종속도는?")
    )

    assert not result.ok
    assert any("초기속도" in error for error in result.verification.errors)


def test_explicit_rolling_rest_condition_allows_zero_initial_speed():
    result = PureRollingEnergySolver().solve(
        _problem("속이 찬 구가 정지 상태에서 미끄러지지 않고 1m 내려온다. 최종속도는?")
    )

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, math.sqrt(2 * 9.81 / 1.4), rel_tol=1e-5)
