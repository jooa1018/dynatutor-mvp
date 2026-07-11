"""Phase 41: Phase 40 피드백 후속 — 스크립트 종료성, 포물선 부분 답, 값 추가 왕복."""
from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
import time
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
    assert "초속도 v0" not in cp.missing_info
    assert r is not None and r.ok
    assert math.isclose(r.answer.numeric, math.sqrt(2 * 10 / 9.81), rel_tol=1e-4)


@pytest.mark.regression
def test_range_without_v0_asks_for_v0():
    cp, r = _solve("높이 10m에서 물체를 수평으로 던졌다. 사거리는?")
    assert r is None  # v0 확인 전에는 projectile solver를 실행하지 않는다.
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
def test_run_with_timeout_kills_term_ignoring_descendant():
    """정상 종료한 리더 뒤에 SIGTERM을 무시하는 손자가 남아도 bounded SIGKILL로 끝낸다."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_with_timeout.py"
    env = os.environ.copy()
    env["DYNATUTOR_RUN_KILL_AFTER"] = "1"
    started = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "30",
            "--",
            "bash",
            "-c",
            "trap '' TERM; while :; do sleep 1; done & echo done",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    elapsed = time.monotonic() - started
    output = proc.stderr + proc.stdout
    assert proc.returncode == 0, output[-500:]
    assert elapsed < 8
    assert "sending SIGKILL" in output
    assert "command exited with code 0" in output


@pytest.mark.regression
def test_frontend_wrapper_cleans_child_on_parent_signal(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root))
    from scripts import check_frontend_build

    child = subprocess.Popen(
        ["bash", "-c", "trap '' TERM; while :; do sleep 1; done"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    monkeypatch.setattr(check_frontend_build, "_CHILD", child)
    monkeypatch.setattr(check_frontend_build, "kill_after_seconds", 1)
    try:
        with pytest.raises(SystemExit) as exited:
            check_frontend_build._handle_parent_signal(signal.SIGTERM, None)
        assert exited.value.code == 128 + signal.SIGTERM
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)


@pytest.mark.regression
def test_backend_benchmark_wrapper_returns_after_real_pytest_summary():
    """sleep 대역이 아니라 실제 benchmark pytest와 wrapper의 종료까지 검증한다."""
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "check_backend_benchmark.sh"
    env = os.environ.copy()
    env["DYNATUTOR_BACKEND_BENCHMARK_TIMEOUT"] = "90"
    env["DYNATUTOR_RUN_KILL_AFTER"] = "1"
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        print(output)  # CI에서 실패한 benchmark case를 잘리지 않게 남긴다.
    assert proc.returncode == 0, output
    assert " passed" in output
    assert "[run_with_timeout] command exited with code 0" in output


@pytest.mark.regression
def test_notebook_export_appends_download_anchor_once():
    api = (
        Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api.ts"
    ).read_text(encoding="utf-8")
    export_body = api.split("export async function downloadNotebookExport()", 1)[1]
    assert export_body.count("document.body.appendChild(a);") == 1
