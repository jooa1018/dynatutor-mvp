from __future__ import annotations

import copy

import pytest

from engine.extraction.extractor import extract_problem
from engine.models import CanonicalProblem
from engine.routing.clarify import (
    ALLOWED_KNOWN_SYMBOLS,
    ALLOWED_SYSTEM_TYPES,
    apply_clarify_patch,
    build_clarification,
)
from engine.routing.evidence import TYPE_TO_FAMILY, rank_type_evidence


def _solve(cp):
    from engine.solvers.registry import SolverRegistry

    s = SolverRegistry().select(cp)
    return s.solve(cp) if s else None


# ------------------------------------------------------------ evidence scorer
@pytest.mark.unit
def test_evidence_scorer_ranks_families_from_flags_and_knowns():
    cp = extract_problem("30도 경사면 위에서 블록이 용수철에 연결되어 있다. 속도는?")
    ranked = rank_type_evidence(cp)
    families = {e.family for e in ranked}
    assert {"incline", "spring"} <= families
    # flag 없는 패밀리는 knowns만으로 후보가 되지 않는다 (floor=2)
    cp2 = extract_problem("질량 2kg 물체가 있다. 힘을 구하라.")
    assert all(e.score >= 2 for e in rank_type_evidence(cp2))


@pytest.mark.unit
def test_type_to_family_covers_allowed_system_types():
    # clarify가 제시하는 대표 모형은 전부 패밀리 매핑을 가져야 한다.
    for st in ALLOWED_SYSTEM_TYPES:
        assert st in TYPE_TO_FAMILY, st


# ------------------------------------------------------------ rigid vA rule
@pytest.mark.regression
def test_rigid_missing_reference_roundtrip():
    """negatives 5건 클래스: vA 부재 거절 → 되묻기 → 'A 고정' 원탭 → 정답."""
    cp = extract_problem("평면강체에서 A와 B 사이 거리는 0.5m, 각속도는 4rad/s이다. B점 속도는?")
    r = _solve(cp)
    assert r is not None and not r.ok  # 전제: solver 거절
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "rigid_missing_reference"
    fix = next(o for o in clar.options if o.id == "fix_A")
    cp2 = apply_clarify_patch(copy.deepcopy(cp), fix.patch)
    r2 = _solve(cp2)
    assert r2.ok and abs(r2.answer.numeric - 2.0) < 1e-9  # 0.5 × 4


@pytest.mark.regression
def test_rigid_rule_skips_when_A_fixed_in_text():
    cp = extract_problem("평면강체에서 A점은 고정되어 있고 B는 A에서 오른쪽으로 0.5m 떨어져 있다. 각속도는 반시계방향 4rad/s이다. B점 속도는?")
    r = _solve(cp)
    assert r is not None and r.ok  # 고정 문구가 있으면 애초에 풀린다
    # build_clarification은 실패 시에만 호출되지만, 규칙 자체도 스킵해야 한다.
    from engine.routing.clarify import _rule_rigid_missing_reference

    assert _rule_rigid_missing_reference(cp) is None


# ------------------------------------------------------------ unknown + evidence
@pytest.mark.regression
def test_unknown_with_evidence_three_step_chain():
    """유형 질문 → 모형 확정 → 값 질문(missing_values)으로 연쇄되는 3단 흐름."""
    cp = extract_problem("용수철 장치가 있다. 무엇을 구할 수 있을까?")
    assert cp.system_type == "unknown"
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "unknown_with_evidence"
    assert any(o.id == "as_spring" for o in clar.options)
    cp2 = apply_clarify_patch(copy.deepcopy(cp), clar.options[0].patch)
    assert cp2.system_type in ALLOWED_SYSTEM_TYPES
    nxt = build_clarification(cp2)
    assert nxt is not None and nxt.rule == "missing_values"


@pytest.mark.unit
def test_unknown_without_any_evidence_stays_silent():
    cp = extract_problem("어떤 물체가 움직인다. 상황을 구하라.")
    assert cp.system_type == "unknown"
    assert build_clarification(cp) is None  # 근거 없는 되묻기는 하지 않는다


# ------------------------------------------------------------ fallback
@pytest.mark.regression
def test_evidence_confirm_for_solverless_intermediate_type():
    """'rolling' 같은 solver 미연결 중간 타입 — 무질문 거절 대신 확인형 질문."""
    cp = extract_problem("물체가 구르는 상황이다. 설명하라.")
    assert _solve(cp) is None  # 전제: solver 미매치
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "evidence_confirm"
    cp2 = apply_clarify_patch(copy.deepcopy(cp), clar.options[0].patch)
    nxt = build_clarification(cp2)
    assert nxt is not None and nxt.rule == "missing_values"  # 값 질문으로 연쇄


@pytest.mark.unit
def test_evidence_conflict_synthetic_mixed_witness():
    """합성 witness: 유형 확정 + missing 매핑 불가 + 타 패밀리 증거 → 모형 질문.
    (자연 발동은 희소한 최후 안전망 — 로직만 합성으로 검증한다.)"""
    from engine.routing.clarify import _rule_evidence_conflict_fallback

    cp = extract_problem("질량 2kg 물체가 충돌한다. 30도 경사면이 있다. 결과는?")
    cp.system_type = "vertical_circle"  # 매핑에 없는 유형으로 강제
    cp.missing_info = ["특수 조건 X"]  # missing_values가 못 받는 문자열
    clar = _rule_evidence_conflict_fallback(cp)
    assert clar is not None and clar.rule == "evidence_conflict"
    ids = {o.id for o in clar.options}
    assert {"as_collision", "as_incline"} <= ids


# ------------------------------------------------------------ missing_values 확장
@pytest.mark.regression
def test_const_acc_missing_offers_multiple_value_options():
    cp = extract_problem("등가속도 상황이다. 무엇을 구할 수 있는가?")
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "missing_values"
    symbols = {o.needs_value for o in clar.options}
    assert len(symbols) >= 2  # v0/a/t 중 복수 옵션


# ------------------------------------------------------------ 안전장치
@pytest.mark.unit
def test_new_patch_symbols_are_whitelisted_and_others_rejected():
    from engine.routing.clarify import ClarifyPatchError

    assert {"vA", "aA", "omega", "alpha"} <= ALLOWED_KNOWN_SYMBOLS
    cp = extract_problem("평면강체에서 A와 B 사이 거리는 0.5m, 각속도는 4rad/s이다. B점 속도는?")
    with pytest.raises(ClarifyPatchError):
        apply_clarify_patch(cp, {"set_known": {"symbol": "__evil__", "value": 1}})
    with pytest.raises(ClarifyPatchError):
        apply_clarify_patch(cp, {"system_type": "not_a_type"})


@pytest.mark.regression
def test_clarify_never_fires_on_solvable_benchmark_samples():
    # FP 가드의 축약판 (전수는 하니스가 담당)
    for prob in [
        "마찰 없는 30도 경사면에서 블록의 가속도를 구하라.",
        "m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도와 장력은?",
        "높이 20m에서 수평으로 10m/s로 던졌다. 사거리는?",
    ]:
        cp = extract_problem(prob)
        r = _solve(cp)
        assert r is not None and r.ok  # 풀리는 문제에선 build_clarification 자체가 호출되지 않는다
