from __future__ import annotations

import math

from engine.models import CanonicalProblem, Quantity
from engine.solvers.kinematics import ConstantAcceleration1DSolver


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def _complete_state(*, displacement: float) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="constant_acceleration_1d",
        raw_text="v0=0m/s, a=2m/s², t=5s, s와 vf 조건을 검사하라.",
        knowns={
            "v0": q("v0", 0.0, "m/s"),
            "a": q("a", 2.0, "m/s^2"),
            "t": q("t", 5.0, "s"),
            "s": q("s", displacement, "m"),
            "vf": q("vf", 10.0, "m/s"),
        },
    )


def test_complete_consistent_kinematics_state_is_checked_without_index_error():
    result = ConstantAcceleration1DSolver().solve(_complete_state(displacement=25.0))

    assert result.ok
    assert result.answer is not None
    assert "일치" in result.answer.display


def test_complete_inconsistent_kinematics_state_is_rejected():
    result = ConstantAcceleration1DSolver().solve(_complete_state(displacement=100.0))

    assert not result.ok
    assert any("동시에 만족하지 않습니다" in error for error in result.verification.errors)


def _return_time_problem(raw_text: str) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="constant_acceleration_1d",
        raw_text=raw_text,
        knowns={
            "v0": q("v0", 10.0, "m/s"),
            "a": q("a", -10.0, "m/s^2"),
            "s": q("s", 0.0, "m"),
        },
        requested_outputs=["time"],
        unknowns=["time"],
    )


def test_return_to_origin_event_selects_nonzero_time_root():
    result = ConstantAcceleration1DSolver().solve(
        _return_time_problem("v0=10m/s, a=-10m/s²이다. 다시 출발점에 돌아오는 시간은?")
    )

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 2.0)


def test_ambiguous_time_roots_are_not_selected_by_magnitude_heuristic():
    result = ConstantAcceleration1DSolver().solve(
        _return_time_problem("v0=10m/s, a=-10m/s², s=0m일 때 시간은?")
    )

    assert not result.ok
    assert result.unsupported_reason is not None
    assert "시간 구간" in result.unsupported_reason
