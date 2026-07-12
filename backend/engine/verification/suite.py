"""검증 스위트 오케스트레이터.

verify_result(canonical, solver_result) → VerificationReport

세 층을 순서대로:
  1. 차원      — 답 단위가 심볼의 기대 차원과 일치 (불일치 = error)
  2. 타당성    — 물리적으로 불가능한 값 차단 (t≤0, 광속 초과 등 = error)
  3. 역대입    — 지배 방정식 잔차 ≈ 0 (초과 = error)

정책: 맞는 답은 절대 죽이지 않는다(무고 오탐 0 — mutation 하니스로 상시 측정),
잡은 것은 error로 ok=False까지 강등한다(조용한 오답 차단).
역대입 미지원 유형은 '검증 커버리지 밖'임을 체크 목록에 정직하게 남긴다.
"""
from __future__ import annotations

import re

from engine.models import CanonicalProblem, SolverResult, VerificationReport
from engine.verification.dimensions import check_answer_dimension
from engine.verification.plausibility import check_knowns, check_pool
from engine.verification.residuals import RELEVANT_KNOWNS, run_residual_checks
from engine.verification.provenance import analyze as analyze_provenance

# 대표 answer의 display가 라틴 심볼 없이 한국어 라벨로 시작할 때의 매핑
_KOREAN_LABEL_TO_SYMBOL = {
    "최종속도": "vf",
    "나중속도": "vf",
    "이동거리": "s",
    "변위": "s",
    "수평거리": "R",
    "시간": "t",
    "최대높이": "H",
    "주기": "T",
    "가속도": "a",
    "충격량": "J",
}

_GREEK = {"α": "alpha", "ω": "omega", "τ": "tau", "θ": "theta", "μ": "mu"}


def _rep_symbol(display: str | None) -> str | None:
    """대표 answer의 display('a = 1.703 m/s²', '수평거리 R = 6.552 m')에서 심볼 추출."""
    if not display:
        return None
    head = display.split("=", 1)[0].strip().strip("|").strip()
    for g, name in _GREEK.items():
        head = head.replace(g, name)
    m = re.search(r"([A-Za-z][A-Za-z_']*)\s*$", head)
    if m:
        return m.group(1)
    for label, sym in _KOREAN_LABEL_TO_SYMBOL.items():
        if label in head.replace(" ", ""):
            return sym
    return None


def build_answer_pool(result: SolverResult) -> tuple[dict[str, float], list[tuple[str | None, str | None, str]]]:
    """(pool: symbol→numeric, units: [(symbol, unit, label)]) — items 우선, 대표 answer 보강."""
    pool: dict[str, float] = {}
    units: list[tuple[str | None, str | None, str]] = []
    for a in result.answers or []:
        if a.symbol and a.numeric is not None and a.symbol not in pool:
            pool[a.symbol] = float(a.numeric)
        units.append((a.symbol, a.unit, a.label or ""))
    rep = result.answer
    if rep is not None and rep.numeric is not None:
        sym = _rep_symbol(rep.display)
        if sym and sym not in pool:
            pool[sym] = float(rep.numeric)
        # AnswerItem이 이미 단위 계약을 제공한다면, 심볼을 추출하지 못한
        # 대표 display를 별도의 미등록 심볼로 중복 검증하지 않는다.
        if sym is not None or not result.answers:
            units.append((sym, rep.unit, rep.display or ""))
    return pool, units


def verify_result(cp: CanonicalProblem, result: SolverResult) -> VerificationReport:
    report = VerificationReport(passed=True)
    if not result.ok:
        report.checks.append("검증 스위트: 미해결 결과 — 생략")
        return report

    pool, units = build_answer_pool(result)

    # 1) 차원
    seen = set()
    for sym, unit, label in units:
        key = (sym, unit)
        if key in seen:
            continue
        seen.add(key)
        issue, passed_desc = check_answer_dimension(sym, unit, label, system_type=cp.system_type)
        if issue is not None:
            (report.errors if issue.kind == "error" else report.warnings).append(issue.message)
        if passed_desc:
            report.checks.append(passed_desc)

    # 2) 타당성 (답 + knowns)
    issues, passed = check_pool(pool)
    for it in issues:
        (report.errors if it.kind == "error" else report.warnings).append(it.message)
    report.checks.extend(passed)
    for it in check_knowns(cp.knowns, system_type=cp.system_type):
        (report.errors if it.kind == "error" else report.warnings).append(it.message)

    # 3) 출처(provenance) — 배경 문장에서 주입된 known은 답 전체를 보류.
    #    이 클래스(garbage-in, consistent-out)는 역대입이 원리상 못 잡는다.
    prov = analyze_provenance(cp)
    suspicious = prov.suspicious_entries
    for e in prov.ambiguous_entries:
        report.warnings.append(
            f"출처 다의적: {e.symbol} = {e.value} — 동일 표기가 물리·배경 문장에 모두 있어 출처 확정 불가"
        )
    if suspicious:
        relevant = RELEVANT_KNOWNS.get(cp.system_type)
        for e in suspicious:
            msg = f"출처 의심: {e.symbol} = {e.value} ← \"{e.sentence.text}\" (비물리 문맥 문장에서 추출됨)"
            if relevant is not None and e.symbol not in relevant:
                # 이 유형의 계산에 쓰이지 않는 심볼 → 답은 유지하되 주의 표시
                report.warnings.append(msg + " — 이 유형의 계산에는 미사용")
            else:
                # 계산에 쓰이는 값이거나(오답 위험), 역대입 미커버 유형(안전망 없음) → 답 보류
                report.errors.append(msg)
    else:
        located = sum(1 for e in prov.entries if e.origin == "text")
        if located:
            report.checks.append(f"출처: 텍스트 유래 knowns {located}개 모두 물리 문맥 문장 ✓")

    # 4) 역대입 잔차
    rep_display = result.answer.display if result.answer else None
    checks, supported = run_residual_checks(cp, pool, rep_display)
    if not supported:
        report.checks.append(f"역대입 검산: '{cp.system_type}' 유형은 아직 미지원 (검증 커버리지 밖)")
    elif not checks:
        report.checks.append("역대입 검산: 필요한 값이 부족해 생략")
    else:
        for c in checks:
            if c.passed:
                report.checks.append(c.describe())
            else:
                report.errors.append(c.describe())
                # 잔차가 깨졌고 출처 의심 값이 있으면 원인 후보를 명시 (진단 정보)
                for e in suspicious:
                    report.errors.append(f"  ↳ 원인 후보: {e.symbol} ← \"{e.sentence.text}\"")

    report.passed = not report.errors
    if report.errors:
        report.dimension_summary = "물리 검증 실패"
    return report
