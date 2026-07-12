from __future__ import annotations

import pytest

from engine.verification.gate import gate_decision


@pytest.mark.unit
def test_gate_no_errors_no_demotion():
    demote, reason = gate_decision([])
    assert demote is False and reason is None


@pytest.mark.unit
def test_gate_reason_priority_answer_over_provenance_over_generic():
    demote, reason = gate_decision(["역대입: x ✗", "출처 의심: theta ...", "answer consistency: range 누락"])
    assert demote and "필수 정답" in reason
    demote, reason = gate_decision(["역대입: x ✗", "출처 의심: theta ..."])
    assert demote and "무관해 보이는 문장" in reason
    demote, reason = gate_decision(["역대입: x ✗"])
    assert demote and "물리 검증" in reason


@pytest.mark.regression
def test_gate_is_single_demotion_site_in_services():
    # 회귀 방지: services.py 안에 인라인 ok=False 강등이 다시 생기면 실패.
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "engine" / "services.py"
    text = src.read_text(encoding="utf-8")
    solve_section = text[text.index("def solve_problem") :]
    assert solve_section.count("ok = False") == 0, "solve_problem 내 인라인 강등 금지 — gate 사용"
    assert "apply_result_gate(response)" in solve_section


@pytest.mark.regression
def test_gate_preserves_solver_failure_reason():
    """solver 자체 실패(missing_info)의 사유는 게이트가 덮어쓰지 않는다."""
    from engine.services import solve_problem

    result = solve_problem("경사면 위 물체가 있다. 가속도는?")  # 각도 등 필수 값 없음 → solver 실패
    assert result.ok is False
    assert result.unsupported_reason  # solver/되묻기 사유 유지
    assert "물리 검증" not in (result.unsupported_reason or "")


@pytest.mark.regression
def test_registry_import_order_has_no_cycle():
    """회귀 방지: equation_generators ↔ model_builder 순환.
    registry를 '가장 먼저' import하는 fresh 프로세스가 성공해야 한다."""
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-c", "import engine.solvers.registry; import engine.equation_generators.particle_newton; import engine.model_builder"],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-400:]


# --- Phase 33 Task 3: 미커버 5개 유형의 answers + 역대입 커버 ---

@pytest.mark.regression
def test_arel_extraction_window_bug_fixed():
    """'상대가속도 문제에서 ... aA=1 ... 상대가속도 a_rel=2'에서
    무제한 창 정규식이 aA의 1을 arel로 오파싱 → a_B가 2.0(오답)이 되던 버그."""
    from engine.extraction.extractor import extract_problem
    from engine.solvers.registry import SolverRegistry

    cp = extract_problem("상대가속도 문제에서 A점 가속도 aA=1m/s2는 오른쪽, 상대가속도 a_rel=2m/s2도 오른쪽이다. B점 가속도는?")
    assert cp.knowns["arel"].value == 2.0
    r = SolverRegistry().select(cp).solve(cp)
    assert abs(r.answer.numeric - 3.0) < 1e-9


@pytest.mark.regression
def test_advanced_types_have_answers_and_residual_coverage():
    """5개 고급 유형: answers 항목 존재 + 역대입 검산 수행 + ×1.1 오염 검출."""
    import copy
    from engine.extraction.extractor import extract_problem
    from engine.solvers.registry import SolverRegistry
    from engine.verification.suite import verify_result

    probs = [
        "극좌표에서 r=2m, rdot=0.5m/s, 각속도 omega=3rad/s일 때 속도는?",
        "회전좌표계에서 r=0.5 m, 상대속도 v_rel=0.4 m/s, 각속도 omega=6 rad/s일 때 코리올리 가속도는?",
        "평면강체에서 A점은 고정되어 있고 B는 A에서 오른쪽으로 0.5m 떨어져 있다. 각속도는 반시계방향 4rad/s이다. B점 속도는?",
        "상대가속도 문제에서 A점 가속도 aA=1m/s2는 오른쪽, 상대가속도 a_rel=2m/s2도 오른쪽이다. B점 가속도는?",
    ]
    reg = SolverRegistry()
    for prob in probs:
        cp = extract_problem(prob)
        r = reg.select(cp).solve(cp)
        assert r.answers, (cp.system_type, "answers 비어 있음")
        rep = verify_result(cp, r)
        assert rep.passed and not rep.errors, (cp.system_type, rep.errors)
        assert any(c.startswith("역대입:") for c in rep.checks), (cp.system_type, "역대입 미수행")
        bad = copy.deepcopy(r)
        if bad.answer and bad.answer.numeric:
            bad.answer.numeric *= 1.1
        for a in bad.answers:
            if a.numeric:
                a.numeric *= 1.1
        assert not verify_result(cp, bad).passed, (cp.system_type, "×1.1 오염 미검출")
