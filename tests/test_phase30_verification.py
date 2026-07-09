from __future__ import annotations

import copy

import pytest

from engine.extraction.extractor import extract_problem
from engine.models import Answer, AnswerItem, SolverResult, VerificationReport
from engine.verification.dimensions import check_answer_dimension
from engine.verification.plausibility import check_pool
from engine.verification.residuals import run_residual_checks
from engine.verification.suite import build_answer_pool, verify_result


def _solve(problem: str):
    from engine.solvers.registry import SolverRegistry

    cp = extract_problem(problem)
    matches = sorted([m for s in SolverRegistry().solvers if (m := s.match(cp))], key=lambda m: -m.score)
    assert matches, f"no solver matched: {cp.system_type}"
    return cp, matches[0].solver.solve(cp)


# ------------------------------------------------------------ dimensions
@pytest.mark.unit
def test_dimension_check_passes_correct_unit():
    issue, desc = check_answer_dimension("a", "m/s²")
    assert issue is None and desc


@pytest.mark.unit
def test_dimension_check_rejects_wrong_dimension():
    issue, _ = check_answer_dimension("a", "m/s")
    assert issue is not None and issue.kind == "error"
    issue, _ = check_answer_dimension("t", "m")
    assert issue is not None and issue.kind == "error"


@pytest.mark.unit
def test_dimension_check_unparseable_unit_is_warning_not_error():
    issue, _ = check_answer_dimension("a", "banana/s")
    assert issue is not None and issue.kind == "warning"


# ------------------------------------------------------------ plausibility
@pytest.mark.unit
def test_plausibility_negative_time_is_error():
    issues, _ = check_pool({"t": -2.0})
    assert any(i.kind == "error" for i in issues)


@pytest.mark.unit
def test_plausibility_superluminal_speed_is_error():
    issues, _ = check_pool({"v": 4.0e8})
    assert any(i.kind == "error" for i in issues)


@pytest.mark.unit
def test_plausibility_nan_is_error():
    issues, _ = check_pool({"a": float("nan")})
    assert any(i.kind == "error" for i in issues)


@pytest.mark.unit
def test_plausibility_unusual_mu_is_warning_only():
    issues, _ = check_pool({"mu": 1.8})
    assert not any(i.kind == "error" for i in issues)


# ------------------------------------------------------------ residuals
@pytest.mark.regression
def test_incline_residual_passes_correct_and_catches_corrupted():
    cp, result = _solve("마찰 없는 30도 경사면에서 블록의 가속도를 구하라.")
    pool, _ = build_answer_pool(result)
    checks, supported = run_residual_checks(cp, pool)
    assert supported and checks and all(c.passed for c in checks)
    corrupted = {k: v * 1.1 for k, v in pool.items()}
    checks, _ = run_residual_checks(cp, corrupted)
    assert any(not c.passed for c in checks), "10% 오염이 역대입에서 잡혀야 함"


@pytest.mark.regression
def test_atwood_residual_requires_both_equations():
    cp, result = _solve("m1=2kg, m2=3kg 두 물체가 도르래 양쪽에 매달려 있다. 가속도와 장력은?")
    pool, _ = build_answer_pool(result)
    assert "a" in pool and "T" in pool
    checks, supported = run_residual_checks(cp, pool)
    assert supported and len(checks) == 2 and all(c.passed for c in checks)
    # a만 오염 → 두 물체 방정식이 동시에 성립할 수 없어 반드시 검출
    bad = dict(pool)
    bad["a"] = bad["a"] * 1.1
    checks, _ = run_residual_checks(cp, bad)
    assert any(not c.passed for c in checks)


@pytest.mark.regression
def test_projectile_joint_identity_catches_theta_injection():
    # 온도 버그 시나리오 재현: 답은 수평 발사(θ=0)로 계산됐는데
    # knowns의 theta가 오염(20도)되면 역대입이 잡아야 한다.
    cp, result = _solve("높이 20m에서 수평으로 10m/s로 던졌다. 사거리는?")
    pool, _ = build_answer_pool(result)
    checks, supported = run_residual_checks(cp, pool)
    assert supported and checks and all(c.passed for c in checks)
    from engine.models import Quantity

    cp_bad = copy.deepcopy(cp)
    cp_bad.launch_angle_deg = 20.0  # 오염된 각도
    checks, _ = run_residual_checks(cp_bad, pool)
    assert any(not c.passed for c in checks), "오염된 θ로는 y-항등식이 깨져야 함"


# ------------------------------------------------------------ suite
@pytest.mark.regression
def test_suite_zero_false_positive_on_correct_result():
    cp, result = _solve("높이 20 m인 절벽 위에서 공을 수평 방향으로 36 km/h의 속력으로 던졌다. 시간과 수평거리를 구하라.")
    report = verify_result(cp, result)
    assert report.passed and not report.errors
    assert any(c.startswith("역대입:") for c in report.checks)


@pytest.mark.regression
def test_suite_catches_corrupted_numeric_as_error():
    cp, result = _solve("마찰 없는 30도 경사면에서 블록의 가속도를 구하라.")
    bad = copy.deepcopy(result)
    bad.answer.numeric = bad.answer.numeric * 1.1
    report = verify_result(cp, bad)
    assert report.errors and not report.passed


@pytest.mark.regression
def test_suite_catches_wrong_unit_as_error():
    cp, result = _solve("마찰 없는 30도 경사면에서 블록의 가속도를 구하라.")
    bad = copy.deepcopy(result)
    bad.answer.unit = "m/s"  # 가속도에 속도 단위
    report = verify_result(cp, bad)
    assert any("차원" in e for e in report.errors)


@pytest.mark.regression
def test_suite_reports_uncovered_type_honestly():
    # polar 등은 Phase 33에서 커버됨 — 아직 미커버인 유형으로 정직 보고를 검증.
    cp, result = _solve("순간중심에서 1 m 떨어진 점이 있고 각속도 ω=4 rad/s이다. 그 점의 속도는?")
    report = verify_result(cp, result)
    assert not report.errors
    assert any("미지원" in c for c in report.checks) or any("생략" in c for c in report.checks)


@pytest.mark.regression
def test_service_demotes_ok_on_verification_failure(monkeypatch):
    """서비스 레벨: solver가 오염된 답을 내면 ok=False + 검증 error."""
    from engine.solvers.registry import SolverRegistry
    import engine.services as services

    real_select = SolverRegistry.select

    class _CorruptingSolver:
        def __init__(self, inner):
            self._inner = inner
            self.name = inner.name
            self.reason = getattr(inner, "reason", None)

        def solve(self, canonical):
            result = self._inner.solve(canonical)
            if result.answer and result.answer.numeric is not None:
                result.answer.numeric = result.answer.numeric * 1.1
            for a in result.answers or []:
                if a.numeric is not None:
                    a.numeric = a.numeric * 1.1
            return result

    def fake_select(self, canonical):
        inner = real_select(self, canonical)
        return _CorruptingSolver(inner) if inner else None

    monkeypatch.setattr(SolverRegistry, "select", fake_select)
    result = services.solve_problem("마찰 없는 30도 경사면에서 블록의 가속도를 구하라.")
    assert result.ok is False
    assert any("역대입" in e for e in result.verification.errors)
    assert result.unsupported_reason


# --- 회귀: 전체 테스트 스윕(Phase 32)에서 검증 스위트의 무고 오탐으로 발견/수정 ---

@pytest.mark.regression
def test_vibration_period_T_not_flagged_as_tension_dimension():
    # T는 진동 문맥에서 주기(s)지 장력(N)이 아니다. 문맥 인식 차원 검사 회귀.
    cp, result = _solve("스프링 상수 200N/m, 질량 500g인 스프링-질량계의 주기를 구하라.")
    report = verify_result(cp, result)
    assert report.passed and not report.errors, report.errors


@pytest.mark.regression
def test_negative_friction_work_passes_verification():
    # 마찰일 -30 J은 정답. 부호를 W에 인코딩하는 solver를 차원/역대입이 죽이면 안 됨.
    cp, result = _solve("마찰력 10N이 이동 방향 반대로 3m 작용했다. 한 일은?")
    report = verify_result(cp, result)
    assert report.passed and not report.errors, report.errors
    # 하지만 크기 오염은 여전히 잡아야 한다.
    bad = copy.deepcopy(result)
    bad.answer.numeric = bad.answer.numeric * 1.2
    assert not verify_result(cp, bad).passed


@pytest.mark.regression
def test_incline_static_hold_zero_acceleration_passes():
    # 정지마찰이 버텨 a=0인 경우, 미끄러짐 방정식 잔차로 오탐하면 안 됨.
    cp, result = _solve("정지마찰계수 0.8인 30도 경사면 위 블록이 있다. 가속도는?")
    report = verify_result(cp, result)
    assert report.passed and not report.errors, report.errors


@pytest.mark.regression
def test_incline_hanging_direction_variants_pass():
    # m1 하강 / m2 하강 / 정지(a=0) 세 방향 모두 무고 오탐 없이 통과해야 함.
    for prob in [
        "m1=10kg가 30도 경사면 아래로 내려가고 m2=1kg가 매달려 있다. 운동마찰계수 0.2일 때 가속도는?",
        "m1=2kg가 30도 경사면 위에 있고 m2=8kg가 도르래에 매달려 아래로 내려간다. 가속도는?",
    ]:
        cp, result = _solve(prob)
        report = verify_result(cp, result)
        assert report.passed and not report.errors, (prob, report.errors)
