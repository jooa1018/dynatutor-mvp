"""Phase 39: 기호 팔레트 대응 파서 + 사용성 수정 회귀 테스트."""
from __future__ import annotations

import math

import pytest

from engine.extraction.extractor import extract_problem


def _solve(problem: str):
    import engine.model_builder  # noqa: F401
    from engine.solvers.registry import SolverRegistry

    cp = extract_problem(problem)
    s = SolverRegistry().select(cp)
    return cp, (s.solve(cp) if s else None)


@pytest.mark.regression
def test_symbol_inputs_round_trip():
    """기호 팔레트가 삽입하는 표기(θ, μ, ω, α, ω₀, Δx, τ, N·m)가 정답까지 왕복."""
    cases = [
        ("질량 5kg 블록이 마찰 없는 θ=30° 경사면에서 미끄러진다. 가속도는?", 9.81 * 0.5),
        ("μ=0.2인 수평면에서 질량 2kg 물체가 미끄러진다. 마찰력은?", 0.2 * 2 * 9.81),
        ("ω=3rad/s로 회전하는 원판 위 반지름 0.5m 지점의 속력은?", 1.5),
        ("α=2rad/s²로 각가속, ω₀=5rad/s에서 4초 후 각속도는?", 13.0),
        ("Δx=0.1m 압축된 용수철 상수 k=200N/m. 저장된 에너지는?", 1.0),
        ("τ=6N·m 토크, I=2kg·m²인 바퀴의 각가속도는?", 3.0),
    ]
    for prob, gold in cases:
        cp, r = _solve(prob)
        assert r is not None and r.ok, (prob, r.unsupported_reason if r else "no match")
        assert math.isclose(r.answer.numeric, gold, rel_tol=1e-4), (prob, r.answer.numeric, gold)


@pytest.mark.regression
def test_subscript_zero_normalized():
    cp = extract_problem("ω₀=5rad/s, v₀=3m/s인 상황.")
    assert cp.knowns["omega0"].value == 5.0
    assert cp.knowns["v0"].value == 3.0


@pytest.mark.regression
def test_rotational_kinematics_with_default_omega0():
    cp, r = _solve("α=2rad/s²로 각가속, ω₀=0에서 4초 후 각속도는?")
    assert r.ok and math.isclose(r.answer.numeric, 8.0, rel_tol=1e-6)


@pytest.mark.regression
def test_table_distractor_does_not_hijack_atwood():
    """스테일 리포트 뒤에 숨어 있던 회귀: '책상 위에서 준비했다' 방해문이
    도르래 명시 Atwood를 table_hanging으로 가로채던 문제 (교란 58건)."""
    cp, r = _solve("m1=1kg, m2=2kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도는? 실험 준비는 수평면이 잘 맞춰진 책상 위에서 했다.")
    assert cp.system_type == "pulley_atwood"
    assert r is not None and r.ok


@pytest.mark.regression
def test_plain_table_hanging_still_routes_without_pulley_word():
    cp, _ = _solve("책상 위 m1=2kg 물체가 실로 연결되어 m2=1kg가 매달려 있다. 마찰이 없을 때 가속도는?")
    assert cp.system_type == "pulley_table_hanging"


@pytest.mark.regression
def test_rolling_disk_word_alone_is_not_rolling():
    cp = extract_problem("ω=3rad/s로 회전하는 원판 위 반지름 0.5m 지점의 속력은?")
    assert cp.flags.get("rolling") is not True
    cp2 = extract_problem("원통이 경사면을 미끄러짐 없이 굴러 내려간다. 높이 2m. 바닥 속력은?")
    assert cp2.flags.get("rolling") is True  # '굴러'가 진짜 증거


@pytest.mark.regression
def test_palette_style_m1_mu_input_without_friction_word():
    """팔레트식 입력: '마찰'이라는 단어 없이 μ 기호만, 질량은 m₁ 표기 —
    μ 존재 자체가 마찰 증거이고 단일 물체 문맥의 m₁은 m으로 통한다."""
    cp, r = _solve("질량 m₁=2kg 물체가 μ=0.3인 수평면에서 미끄러진다. 마찰력은?")
    assert cp.system_type == "horizontal_friction_force"
    assert r.ok and math.isclose(r.answer.numeric, 0.3 * 2 * 9.81, rel_tol=1e-4)


# ------------------------------------------------------------ Phase 40 후속 수정
@pytest.mark.regression
def test_new_requested_outputs_are_patch_whitelisted():
    """friction_force/elastic_energy가 UnderstandingCard patch로 재전달돼도
    ClarifyPatchError가 나지 않아야 한다."""
    import copy
    from engine.routing.clarify import ALLOWED_REQUESTED_OUTPUTS, apply_clarify_patch

    for out in ["friction_force", "normal_force", "elastic_energy"]:
        assert out in ALLOWED_REQUESTED_OUTPUTS, out
    cp = extract_problem("μ=0.2인 수평면에서 질량 2kg 물체가 미끄러진다. 마찰력은?")
    patched = apply_clarify_patch(copy.deepcopy(cp), {"requested_outputs": ["friction_force"]})
    assert patched.requested_outputs == ["friction_force"]


@pytest.mark.regression
def test_solved_kinematics_has_no_stale_missing_info():
    """ok=True인데 '확인 필요(τ, I / 질량 m)'가 남던 stale missing_info."""
    cp, r = _solve("ω=3rad/s로 회전하는 원판 위 반지름 0.5m 지점의 속력은?")
    assert r.ok and cp.missing_info == []
    cp, r = _solve("Δx=0.1m 압축된 용수철 상수 k=200N/m. 저장된 에너지는?")
    assert r.ok and cp.missing_info == []
    # τ·I가 정말 필요한 경우에는 여전히 missing으로 남아야 한다
    cp2 = extract_problem("바퀴의 각가속도를 구하라.")
    if cp2.system_type == "fixed_axis_rotation":
        assert "토크 τ" in cp2.missing_info


@pytest.mark.regression
def test_unitless_symbol_equals_inputs():
    """팔레트식 단위 생략: v₀=0, ω₀=0, θ=30."""
    cp = extract_problem("v₀=0, θ=30인 마찰 없는 경사면에서 물체가 미끄러진다. 가속도는?")
    assert cp.knowns["v0"].value == 0.0 and cp.knowns["v0"].unit == "m/s"
    assert cp.knowns["theta"].value == 30.0 and cp.knowns["theta"].unit == "deg"
    _, r = _solve("θ=30인 마찰 없는 경사면 위 블록. 가속도는?")
    assert r.ok and math.isclose(r.answer.numeric, 9.81 * 0.5, rel_tol=1e-4)
    cp = extract_problem("ω₀=0, α=2rad/s²로 4초 후 각속도는?")
    assert cp.knowns["omega0"].value == 0.0 and cp.knowns["omega0"].unit == "rad/s"
    # 단위가 있으면 기존 해석 유지 (0.5 rad ≠ deg)
    cp = extract_problem("theta=0.5 rad인 경사면.")
    assert cp.knowns.get("theta") is None or cp.knowns["theta"].unit != "deg" or cp.knowns["theta"].value != 0.5


@pytest.mark.regression
def test_a_equals_acceleration_does_not_leak_amplitude():
    cp = extract_problem("v₀=0에서 a=3m/s²로 4초 동안 움직였다. 최종속도는?")
    assert cp.knowns["a"].value == 3.0
    assert "A" not in cp.knowns  # a=3m/s²의 'm'을 진폭으로 오인하지 않는다
    _, r = _solve("v₀=0에서 a=3m/s²로 4초 동안 움직였다. 최종속도는?")
    assert r.ok and math.isclose(r.answer.numeric, 12.0, rel_tol=1e-6)
