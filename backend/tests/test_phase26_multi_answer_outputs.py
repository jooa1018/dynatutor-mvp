import math

from engine.llm.guardrails import build_locked_facts, validate_llm_explanation
from engine.services import solve_problem


def assert_has_answer(answers, *, symbol=None, label=None, numeric=None, unit=None, tolerance=1e-3):
    candidates = []
    for ans in answers:
        if symbol is not None and ans.symbol == symbol:
            candidates.append(ans)
        if label is not None and label in ans.label:
            candidates.append(ans)
    assert candidates, f"missing answer symbol={symbol!r} label={label!r}; got={answers}"
    ans = candidates[0]
    if numeric is not None:
        assert ans.numeric is not None
        assert math.isclose(float(ans.numeric), float(numeric), rel_tol=tolerance, abs_tol=tolerance), ans
    if unit is not None:
        assert ans.unit == unit, ans
    return ans


def test_projectile_horizontal_launch_returns_time_and_range():
    problem = (
        "높이 20 m인 절벽 위에서 공을 수평 방향으로 36 km/h의 속력으로 던졌다. "
        "공기저항을 무시할 때 공이 지면에 닿을 때까지 걸리는 시간과 수평거리를 구하라."
    )
    result = solve_problem(problem)
    assert result.ok is True
    assert_has_answer(result.answers, symbol="t", numeric=2.019, unit="s", tolerance=0.02)
    assert_has_answer(result.answers, symbol="R", numeric=20.19, unit="m", tolerance=0.05)
    assert "발사각" not in result.diagnosis.canonical.missing_info


def test_projectile_angle_launch_time_and_range():
    problem = (
        "높이 20 m 절벽에서 공을 초속도 10 m/s, 발사각 30도로 던졌다. "
        "지면까지 걸리는 시간과 수평거리를 구하라."
    )
    result = solve_problem(problem)
    assert result.ok is True
    assert_has_answer(result.answers, symbol="t", unit="s")
    assert_has_answer(result.answers, symbol="R", unit="m")


def test_projectile_max_height_and_range():
    problem = "초속도 20 m/s, 발사각 30도로 공을 던졌다. 최대높이와 사거리를 구하라."
    result = solve_problem(problem)
    assert result.ok is True
    assert_has_answer(result.answers, symbol="H", unit="m")
    assert_has_answer(result.answers, symbol="R", unit="m")


def test_atwood_returns_acceleration_and_tension_when_both_requested():
    problem = "m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도와 장력은?"
    result = solve_problem(problem)
    assert result.ok is True
    assert_has_answer(result.answers, symbol="a", numeric=1.962, unit="m/s²", tolerance=0.01)
    assert_has_answer(result.answers, symbol="T", numeric=23.544, unit="N", tolerance=0.05)


def test_elastic_collision_returns_both_velocities():
    problem = "m1=1kg, m2=1kg, v1=5m/s, v2=0m/s이다. 완전탄성 충돌 후 두 물체의 속도는?"
    result = solve_problem(problem)
    assert result.ok is True
    assert_has_answer(result.answers, symbol="v1'", numeric=0.0, unit="m/s", tolerance=0.01)
    assert_has_answer(result.answers, symbol="v2'", numeric=5.0, unit="m/s", tolerance=0.01)


def test_blind_benchmark_fails_when_required_answer_missing():
    class Fake:
        def __init__(self, symbol, label, numeric, unit):
            self.symbol = symbol
            self.label = label
            self.numeric = numeric
            self.unit = unit
            self.display = f"{label} {symbol} = {numeric} {unit}"
    fake_answers = [Fake("t", "시간", 2.019, "s")]
    assert_has_answer(fake_answers, symbol="t", numeric=2.019, unit="s", tolerance=0.02)
    try:
        assert_has_answer(fake_answers, symbol="R", numeric=20.19, unit="m", tolerance=0.05)
    except AssertionError:
        pass
    else:
        raise AssertionError("missing R should fail")


def test_single_particle_newton_physical_model_contains_force():
    problem = "질량 0.5kg인 물체에 힘 10N이 작용한다. 가속도는?"
    result = solve_problem(problem)
    assert result.ok is True
    assert result.physical_model is not None
    assert len(result.physical_model.get("forces", [])) >= 1
    force_symbols = {f.get("symbol") for f in result.physical_model.get("forces", [])}
    assert "F_net" in force_symbols
    assert_has_answer(result.answers, symbol="a", numeric=20.0, unit="m/s²", tolerance=0.01)


def test_llm_locked_facts_include_all_answers_and_guard_missing_answer():
    problem = (
        "높이 20 m인 절벽 위에서 공을 수평 방향으로 36 km/h의 속력으로 던졌다. "
        "공기저항을 무시할 때 공이 지면에 닿을 때까지 걸리는 시간과 수평거리를 구하라."
    )
    result = solve_problem(problem)
    locked = build_locked_facts(result)
    symbols = {a["symbol"] for a in locked.answers}
    assert {"t", "R"}.issubset(symbols)
    bad_explanation = "### 마지막 확인\n최종 답은 시간 t = 2.019 s 입니다."
    integrity = validate_llm_explanation(bad_explanation, locked)
    assert not integrity.passed
    assert any("복수 정답" in w for w in integrity.warnings)


def test_constant_acceleration_returns_final_velocity_and_distance():
    problem = "정지한 물체가 등가속도 a=2 m/s^2 로 시간 5 s 동안 직선 운동한다. 최종 속도와 이동거리를 구하라."
    result = solve_problem(problem)
    assert result.ok is True
    assert_has_answer(result.answers, symbol="vf", numeric=10.0, unit="m/s", tolerance=0.01)
    assert_has_answer(result.answers, symbol="s", numeric=25.0, unit="m", tolerance=0.01)
