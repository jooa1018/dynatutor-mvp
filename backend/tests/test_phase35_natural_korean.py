"""Phase 35: 학생식 자연어 한국어 문장 회귀 테스트.

요구서의 예문들이 그대로 케이스다 — "이미 풀 수 있는 문제를 더 자연스러운
한국어 입력에서도 정확히 이해"가 목표. 각 케이스는 (a) 올바른 라우팅,
(b) 수치 정답 또는 (c) 올바른 되묻기 중 하나를 단언한다.
"""
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


# ------------------------------------------------------------ 정지/멈춤 표현
@pytest.mark.regression
def test_jeongji_variants_set_v0_zero():
    for prob in [
        "정지해 있는 물체가 3 m/s²로 5초 동안 움직였다. 최종속도는?",
        "처음 정지 상태의 물체가 3 m/s²로 움직인다. 5초 후 속도는?",
    ]:
        cp, r = _solve(prob)
        assert cp.knowns["v0"].value == 0.0, prob
        assert r is not None and r.ok and math.isclose(r.answer.numeric, 15.0, rel_tol=1e-6), prob


@pytest.mark.regression
def test_meomchunda_sets_vf_zero():
    cp, r = _solve("물체가 5초 뒤 멈춘다. 초속도 10m/s. 가속도는?")
    assert cp.knowns["vf"].value == 0.0
    assert r.ok and math.isclose(r.answer.numeric, -2.0, rel_tol=1e-6)
    cp, r = _solve("물체가 5초 뒤 정지한다. 초속도 10m/s. 가속도는?")
    assert r.ok and math.isclose(r.answer.numeric, -2.0, rel_tol=1e-6)


# ------------------------------------------------------------ 포물선 높이 표현
@pytest.mark.regression
def test_below_landing_phrase_sets_drop_height():
    cp, r = _solve("공을 수평으로 10m/s로 던져 10m 아래 지점에 떨어졌다. 사거리는?")
    assert cp.knowns["h"].value == 10.0
    expected = 10.0 * math.sqrt(2 * 10.0 / 9.81)
    assert r.ok and math.isclose(r.answer.numeric, expected, rel_tol=1e-4)


@pytest.mark.regression
def test_above_landing_phrase_sets_landing_height():
    cp, r = _solve("10m 위 지점에 떨어졌다. 초속도 20m/s, 발사각 60도. 사거리는?")
    assert cp.landing_height == 10.0
    assert r is not None and r.ok


# ------------------------------------------------------------ 일-에너지 방향
@pytest.mark.regression
def test_force_direction_phrase_solves_work_directly():
    cp, r = _solve("힘 10N의 힘 방향으로 5m 이동했다. 한 일은?")
    assert r.ok and math.isclose(r.answer.numeric, 50.0, rel_tol=1e-6)


@pytest.mark.regression
def test_work_direction_clarify_and_opposite_resolve():
    import copy
    from engine.routing.clarify import apply_clarify_patch, build_clarification
    from engine.solvers.registry import SolverRegistry

    cp, r = _solve("힘 10N이 물체에 작용해 5m 이동했다. 힘이 한 일은?")
    assert r is not None and not r.ok
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "work_direction_unknown"
    assert {o.id for o in clar.options} == {"dir_same", "dir_opposite", "dir_perp", "dir_angle"}
    opp = next(o for o in clar.options if o.id == "dir_opposite")
    cp2 = apply_clarify_patch(copy.deepcopy(cp), opp.patch)
    r2 = SolverRegistry().select(cp2).solve(cp2)
    assert r2.ok and math.isclose(r2.answer.numeric, -50.0, rel_tol=1e-6)


@pytest.mark.regression
def test_textbook_long_modifier_force_still_extracted():
    # 회귀: 전역 창 제한이 "힘은 변위와 같은 방향이며 크기는 10N"의 F를 놓쳤던 건
    cp, r = _solve("물체에 작용한 힘은 변위와 같은 방향이며 크기는 10N이다. 물체가 3m 이동하는 동안 이 힘이 한 일은?")
    assert cp.knowns["F"].value == 10.0
    assert r.ok and math.isclose(r.answer.numeric, 30.0, rel_tol=1e-6)


# ------------------------------------------------------------ 충돌 자연어
@pytest.mark.regression
def test_ab_object_collision_natural_korean():
    cp, r = _solve("A 물체 2kg와 B 물체 3kg가 정면 충돌한다. A는 4m/s, B는 정지. 충돌 후 함께 움직일 때 속도는?")
    ks = {k: q.value for k, q in cp.knowns.items()}
    assert ks["m1"] == 2.0 and ks["m2"] == 3.0 and ks["v1"] == 4.0 and ks["v2"] == 0.0
    assert r.ok and math.isclose(r.answer.numeric, 1.6, rel_tol=1e-6)


@pytest.mark.regression
def test_ordinal_object_collision_with_own_mass_before_speed():
    # 회귀: "첫 번째 물체 2kg가 3m/s" — 자기 질량이 속도보다 앞에 와도 v1을 잡는다
    cp, r = _solve("두 번째 물체는 처음에 가만히 있었다. 첫 번째 물체 2kg가 3m/s로 와서 두 번째 물체 1kg와 충돌해 붙어서 움직인다. 속도는?")
    ks = {k: q.value for k, q in cp.knowns.items()}
    assert ks["m1"] == 2.0 and ks["m2"] == 1.0 and ks["v2"] == 0.0
    assert r.ok and math.isclose(r.answer.numeric, 2.0, rel_tol=1e-6)


@pytest.mark.regression
def test_moving_together_means_perfectly_inelastic():
    cp, _ = _solve("2kg 물체가 4m/s로 3kg 정지 물체와 충돌해 함께 움직인다. 속도는?")
    assert cp.flags.get("perfectly_inelastic") is True


# ------------------------------------------------------------ 등가속도 / 뉴턴
@pytest.mark.regression
def test_bare_acceleration_with_josa_extracted():
    cp, r = _solve("질량 2kg 물체가 3 m/s²로 움직인다. 힘은?")
    assert cp.knowns["a"].value == 3.0
    assert cp.system_type == "single_particle_newton"
    assert r.ok and math.isclose(r.answer.numeric, 6.0, rel_tol=1e-6)


# ------------------------------------------------------------ 마찰/도르래 관용구
@pytest.mark.regression
def test_machal_eun_musi_sets_no_friction():
    cp, r = _solve("마찰은 무시한다. 30도 경사면 위 블록의 가속도는?")
    assert cp.subtype == "no_friction"
    assert r.ok and math.isclose(r.answer.numeric, 9.81 * 0.5, rel_tol=1e-4)


@pytest.mark.regression
def test_light_string_frictionless_pulley_preamble():
    cp, r = _solve("실이 가볍고 도르래는 마찰이 없다. m1=2kg, m2=3kg가 도르래 양쪽에 매달려 있다. 가속도는?")
    assert cp.system_type == "pulley_atwood"
    assert r.ok and math.isclose(r.answer.numeric, 9.81 / 5.0, rel_tol=1e-4)


# ------------------------------------------------------------ whitelist
@pytest.mark.unit
def test_clarify_whitelist_includes_a():
    from engine.routing.clarify import ALLOWED_KNOWN_SYMBOLS

    assert "a" in ALLOWED_KNOWN_SYMBOLS


# ------------------------------------------------------------ P4: patch 후 diagnosis 갱신
@pytest.mark.regression
def test_diagnosis_reflects_clarify_patch():
    from engine.services import solve_problem

    prob = "30도 경사면 위 블록의 가속도를 구하라."
    before = solve_problem(prob)
    assert not before.ok and before.clarification is not None
    patch = next(o for o in before.clarification.options if o.id == "no_friction").patch
    after = solve_problem(prob, clarify_patch=patch)
    assert after.ok
    assert after.diagnosis.canonical.subtype == "no_friction"
    assert after.diagnosis.selected_solver == "incline_no_friction"
    # physical_model도 patched canonical 기준 (response와 diagnosis 일치)
    assert after.physical_model == after.diagnosis.physical_model


# ------------------------------------------------------------ Phase 36 보강: 자연어 충돌/일/평면강체 부분답
@pytest.mark.regression
def test_collision_sentence_extracts_equal_masses_elastic_rest_body():
    cp, r = _solve("질량 2kg 물체가 4m/s로 가다가 정지해 있는 질량 2kg 물체와 완전탄성충돌한다. 충돌 후 속도는?")
    ks = {k: q.value for k, q in cp.knowns.items()}
    assert ks["m1"] == 2.0 and ks["m2"] == 2.0 and ks["v1"] == 4.0 and ks["v2"] == 0.0
    assert cp.flags.get("elastic") is True
    assert r.ok
    assert any(a.symbol == "v1'" for a in r.answers)
    assert any(a.symbol == "v2'" for a in r.answers)


@pytest.mark.regression
def test_collision_sentence_extracts_inelastic_rest_body():
    cp, r = _solve("2kg 물체가 4m/s로 3kg 정지 물체와 충돌해 함께 움직인다. 속도는?")
    ks = {k: q.value for k, q in cp.knowns.items()}
    assert ks["m1"] == 2.0 and ks["m2"] == 3.0 and ks["v1"] == 4.0 and ks["v2"] == 0.0
    assert cp.flags.get("perfectly_inelastic") is True
    assert r.ok and math.isclose(r.answer.numeric, 1.6, rel_tol=1e-6)


@pytest.mark.regression
def test_force_direction_acts_for_distance_sets_theta_zero():
    cp, r = _solve("힘 10N이 힘 방향으로 5m 동안 작용한다. 한 일은?")
    assert cp.knowns["theta"].value == 0.0
    assert r.ok and math.isclose(r.answer.numeric, 50.0, rel_tol=1e-6)


@pytest.mark.regression
def test_fixed_a_rigid_body_scalar_speed_without_components():
    cp, r = _solve("평면강체에서 A점 고정, AB 거리 0.5m, 각속도 4rad/s이다. B점 속도는?")
    assert cp.system_type == "plane_rigid_body_velocity"
    assert r.ok and math.isclose(r.answer.numeric, 2.0, rel_tol=1e-6)
    assert len(r.answers) == 1
    assert r.answers[0].symbol == "v_B"
    assert any("방향 정보" in w for w in r.verification.warnings)
