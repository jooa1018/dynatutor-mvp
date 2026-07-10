from __future__ import annotations

import pytest

from engine.extraction.extractor import extract_problem
from engine.routing.clarify import (
    ClarifyPatchError,
    apply_clarify_patch,
    build_clarification,
)


def _select_and_solve(cp):
    from engine.solvers.registry import SolverRegistry

    ms = sorted([m for s in SolverRegistry().solvers if (m := s.match(cp))], key=lambda m: -m.score)
    return (ms[0].solver.solve(cp) if ms else None)


# ------------------------------------------------------------ rules
@pytest.mark.unit
def test_incline_unknown_friction_fires_friction_question():
    cp = extract_problem("30도 경사면 위 블록의 가속도를 구하라.")
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "incline_friction_unknown"
    ids = {o.id for o in clar.options}
    assert ids == {"no_friction", "with_friction"}
    assert any(o.needs_value == "mu" for o in clar.options)


@pytest.mark.unit
def test_ambiguous_pulley_fires_topology_question():
    cp = extract_problem("두 물체가 줄과 도르래로 연결되어 있다. 가속도를 구하라.")
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "pulley_topology_unknown"
    assert len(clar.options) == 3


@pytest.mark.unit
def test_mixed_spring_beats_friction_question():
    # 혼합(모형 선택)이 마찰(세부)보다 먼저 물어야 한다.
    cp = extract_problem("30도 경사면 위에서 블록이 용수철에 연결되어 있다. 블록을 놓으면 속도는?")
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "mixed_spring_conflict"


@pytest.mark.unit
def test_missing_values_fires_for_v0_less_projectile():
    cp = extract_problem("공을 45도로 발사했다. 사거리는?")
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "missing_values"
    assert any(o.needs_value == "v0" for o in clar.options)


@pytest.mark.unit
def test_solvable_problem_gets_no_clarification():
    # 되묻기는 풀리는 문제를 절대 가로막으면 안 된다.
    for prob in [
        "마찰 없는 30도 경사면에서 블록의 가속도를 구하라.",
        "높이 20m에서 수평으로 10m/s로 던졌다. 사거리는?",
        "m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도와 장력은?",
    ]:
        cp = extract_problem(prob)
        result = _select_and_solve(cp)
        assert result is not None and result.ok, prob


# ------------------------------------------------------------ patch
@pytest.mark.unit
def test_patch_whitelist_rejects_bad_values():
    cp = extract_problem("30도 경사면 위 블록의 가속도를 구하라.")
    with pytest.raises(ClarifyPatchError):
        apply_clarify_patch(cp, {"system_type": "__evil__"})
    with pytest.raises(ClarifyPatchError):
        apply_clarify_patch(cp, {"drop_table": True})
    with pytest.raises(ClarifyPatchError):
        apply_clarify_patch(cp, {"set_known": {"symbol": "g", "value": 1}})
    with pytest.raises(ClarifyPatchError):
        apply_clarify_patch(cp, {"set_known": {"symbol": "mu", "value": "abc"}})


@pytest.mark.unit
def test_patch_resolves_missing_info():
    cp = extract_problem("30도 경사면 위 블록의 가속도를 구하라.")
    assert "마찰 유무" in cp.missing_info
    apply_clarify_patch(cp, {"subtype": "no_friction", "assume": "마찰 무시"})
    assert "마찰 유무" not in cp.missing_info
    assert any("사용자 확인" in a for a in cp.assumptions)
    result = _select_and_solve(cp)
    assert result is not None and result.ok
    assert abs(result.answer.numeric - 4.905) < 1e-3


@pytest.mark.unit
def test_patch_user_value_is_trusted_by_provenance():
    from engine.verification.provenance import analyze

    cp = extract_problem("30도 경사면 위 블록의 가속도를 구하라.")
    apply_clarify_patch(cp, {"subtype": "with_friction", "set_known": {"symbol": "mu", "value": 0.2, "unit": "", "label": "운동마찰계수"}})
    prov = analyze(cp)
    entry = next(e for e in prov.entries if e.symbol == "mu")
    assert not entry.suspicious, "사용자 입력 값이 배경 문장으로 오탐되면 안 됨"


@pytest.mark.unit
def test_model_choice_prevents_mixed_rule_refire():
    prob = "30도 경사면 위에서 블록이 용수철에 연결되어 있다. 블록을 놓으면 속도는?"
    cp = extract_problem(prob)
    apply_clarify_patch(cp, {"system_type": "particle_on_incline", "assume": "용수철 무시"})
    clar = build_clarification(cp)
    assert clar is not None and clar.rule == "incline_friction_unknown", "모형 선택 후엔 마찰 질문으로 연쇄되어야 함"


# ------------------------------------------------------------ service / route
@pytest.mark.regression
def test_service_returns_clarification_and_resolves():
    from engine.services import solve_problem

    out = solve_problem("30도 경사면 위 블록의 가속도를 구하라.")
    assert out.ok is False and out.clarification is not None
    assert out.clarification.rule == "incline_friction_unknown"
    patch = out.clarification.options[0].patch
    out2 = solve_problem("30도 경사면 위 블록의 가속도를 구하라.", clarify_patch=patch)
    assert out2.ok is True
    assert not out2.verification.errors


@pytest.mark.regression
def test_service_missing_value_flow_end_to_end():
    from engine.services import solve_problem

    prob = "스프링 상수 200N/m인 진동계의 주기를 구하라."
    out = solve_problem(prob)
    assert out.clarification is not None and out.clarification.rule == "missing_values"
    opt = next(o for o in out.clarification.options if o.needs_value == "m")
    patch = dict(opt.patch)
    patch["set_known"] = dict(patch["set_known"], value=0.5)
    out2 = solve_problem(prob, clarify_patch=patch)
    assert out2.ok is True and out2.answer.unit == "s"


@pytest.mark.frontend
def test_route_clarify_roundtrip_and_bad_patch_400():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post("/solve", json={"problem_text": "30도 경사면 위 블록의 가속도를 구하라."})
    assert r.status_code == 200
    d = r.json()
    assert d["clarification"]["rule"] == "incline_friction_unknown"
    r2 = client.post("/solve", json={
        "problem_text": "30도 경사면 위 블록의 가속도를 구하라.",
        "clarify_patch": d["clarification"]["options"][0]["patch"],
    })
    assert r2.status_code == 200 and r2.json()["ok"] is True
    r3 = client.post("/solve", json={"problem_text": "아무 문제", "clarify_patch": {"system_type": "__evil__"}})
    assert r3.status_code == 400
