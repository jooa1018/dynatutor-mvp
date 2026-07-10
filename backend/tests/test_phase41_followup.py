"""Phase 41: Phase 40 피드백 후속 — 스크립트 종료성, 포물선 부분 답, 값 추가 왕복."""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from engine.extraction.extractor import extract_problem


def _solve(problem: str):
    import engine.model_builder  # noqa: F401
    from engine.solvers.registry import SolverRegistry

    cp = extract_problem(problem)
    s = SolverRegistry().select(cp)
    return cp, (s.solve(cp) if s else None)


@pytest.mark.regression
def test_flight_time_without_v0():
    """수평 발사의 비행시간은 v0 없이 t=√(2h/g) — unknown 거절 대신 부분 답."""
    cp, r = _solve("높이 10m에서 물체를 수평으로 던졌다. 비행시간은?")
    assert cp.system_type == "projectile_motion"
    assert r is not None and r.ok
    assert math.isclose(r.answer.numeric, math.sqrt(2 * 10 / 9.81), rel_tol=1e-4)


@pytest.mark.regression
def test_range_without_v0_asks_for_v0():
    cp, r = _solve("높이 10m에서 물체를 수평으로 던졌다. 사거리는?")
    assert r is not None and not r.ok
    assert "초속도 v0" in cp.missing_info


@pytest.mark.regression
def test_full_projectile_case_unaffected():
    _, r = _solve("높이 20m에서 수평으로 10m/s로 던졌다. 사거리는?")
    assert r.ok


@pytest.mark.regression
def test_add_missing_known_roundtrip_v2():
    """UnderstandingCard '누락된 값 추가' 경로: v2=0 patch → 정답."""
    import copy
    from engine.routing.clarify import apply_clarify_patch
    from engine.solvers.registry import SolverRegistry

    cp = extract_problem("2kg 물체가 4m/s로 3kg 물체와 충돌해 함께 움직인다. 속도는?")
    patched = apply_clarify_patch(copy.deepcopy(cp), {"set_knowns": [{"symbol": "v2", "value": 0, "unit": "m/s", "label": "충돌 전 속도 v2"}]})
    r = SolverRegistry().select(patched).solve(patched)
    assert r.ok and math.isclose(r.answer.numeric, 1.6, rel_tol=1e-6)


@pytest.mark.regression
def test_anonymous_collision_v0_aliased_to_v1():
    """'2kg 물체가 4m/s로 정지한 물체와 충돌' — 익명 진행 물체 속도(v0)를 v1로."""
    cp, r = _solve("2kg 물체가 4m/s로 정지해 있는 3kg 물체와 충돌해 함께 움직인다. 속도는?")
    assert cp.knowns["v1"].value == 4.0
    assert r.ok and math.isclose(r.answer.numeric, 1.6, rel_tol=1e-6)


@pytest.mark.regression
def test_run_with_timeout_cleans_surviving_process_group():
    """자식이 정상 종료해도 그룹에 남은 손자(sleep)를 정리하고 즉시 반환한다.
    (11 passed 후에도 외부 timeout까지 매달리던 문제의 재현·방지.)"""
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_with_timeout.py"
    proc = subprocess.run(
        [sys.executable, str(script), "30", "--", "bash", "-c", "sleep 300 & echo done"],
        capture_output=True,
        text=True,
        timeout=25,  # 매달리면 여기서 실패
    )
    assert proc.returncode == 0, proc.stderr[-300:]
    assert "process group" in (proc.stderr + proc.stdout)  # 정리 로그 확인
