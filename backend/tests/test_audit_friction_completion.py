from __future__ import annotations

import math

from engine.models import CanonicalProblem, Quantity
from engine.solvers.energy_vibration import HorizontalFrictionForceSolver


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def _static_problem(raw_text: str, *, force: float | None = None) -> CanonicalProblem:
    knowns = {
        "m": q("m", 2.0, "kg"),
        "mu_s": q("mu_s", 0.5, ""),
        "g": q("g", 9.81, "m/s^2"),
    }
    if force is not None:
        knowns["F"] = q("F", force, "N")
    return CanonicalProblem(
        system_type="horizontal_friction_force",
        raw_text=raw_text,
        knowns=knowns,
        friction_type="static",
        requested_outputs=["friction_force"],
    )


def test_unloaded_stationary_body_has_zero_actual_static_friction():
    result = HorizontalFrictionForceSolver().solve(
        _static_problem("수평면에 그냥 정지한 2kg 물체의 실제 정지마찰력은?")
    )

    assert result.ok
    assert result.answer is not None
    assert result.answer.numeric == 0.0
    maximum = next(item for item in result.answers if item.symbol == "f_s,max")
    assert math.isclose(maximum.numeric, 9.81)


def test_maximum_static_friction_is_reported_only_when_asked():
    result = HorizontalFrictionForceSolver().solve(
        _static_problem("최대 정지마찰력은?")
    )

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 9.81)
    assert result.answers[0].symbol == "f_s,max"


def test_actual_static_friction_matches_subthreshold_applied_force():
    result = HorizontalFrictionForceSolver().solve(
        _static_problem("수평 외력 3N을 받아 정지한 물체의 마찰력은?", force=3.0)
    )

    assert result.ok
    assert result.answer is not None
    assert math.isclose(result.answer.numeric, 3.0)


def test_static_model_rejects_force_above_limit_without_kinetic_coefficient():
    result = HorizontalFrictionForceSolver().solve(
        _static_problem("수평 외력 12N을 받는다. 정지마찰력은?", force=12.0)
    )

    assert not result.ok
    assert result.unsupported_reason is not None
    assert "운동마찰계수" in result.unsupported_reason
