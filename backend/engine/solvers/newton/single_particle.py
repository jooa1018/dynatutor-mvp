from __future__ import annotations

import re

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing

_FORCE_RE = re.compile(r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*N", re.IGNORECASE)


def _force_mentions(text: str) -> list[float]:
    out = []
    for m in _FORCE_RE.findall(text):
        out.append(float(m.replace(",", "")))
    return out


def _is_net_force_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.lower())
    return any(w in compact for w in ["알짜힘", "합력", "순힘", "netforce", "resultantforce", "resultant"])


def _requested(c: CanonicalProblem) -> str:
    requested_map = {
        "acceleration": "a",
        "force": "F",
        "mass": "m",
    }
    for requested in (c.requested_outputs or c.unknowns or []):
        if requested in requested_map:
            return requested_map[requested]

    compact = re.sub(r"\s+", "", c.raw_text.lower())
    # 질문 의도를 먼저 본다. 본문에 "가속도는 2"가 있어도
    # "필요한 힘"을 묻는 문제라면 F가 미지수다.
    if any(w in compact for w in ["필요한알짜힘", "필요한힘", "힘은?", "힘을구", "force"]):
        return "F"
    if any(w in compact for w in ["질량은?", "질량을구", "mass"]):
        return "m"
    if any(w in compact for w in ["가속도는?", "가속도를구", "acceleration"]):
        return "a"
    # Missing variable fallback.
    if "a" not in c.knowns:
        return "a"
    if "F" not in c.knowns:
        return "F"
    if "m" not in c.knowns:
        return "m"
    return "a"


class SingleParticleNewtonSolver(BaseSolver):
    name = "single_particle_newton"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "single_particle_newton":
            return SolverMatch(self, 90, "단일 질점에 대한 뉴턴 제2법칙 F=ma")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        forces = _force_mentions(c.raw_text)
        if len(forces) >= 2 and not _is_net_force_text(c.raw_text):
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["여러 힘이 주어졌지만 합력인지, 같은 방향/반대 방향인지 명시되지 않았습니다."],
                    warnings=["알짜힘/합력 또는 각 힘의 방향을 알려 주세요."],
                ),
                unsupported_reason="힘 방향 또는 합력 여부가 불명확하여 가속도를 확정할 수 없습니다.",
            )

        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="F=ma 문제에는 m, F, a 중 두 개와 구할 값이 필요합니다.")

        if len(forces) >= 2 and not _is_net_force_text(c.raw_text):
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["여러 힘이 주어졌지만 합력인지, 같은 방향/반대 방향인지 명시되지 않았습니다."],
                    warnings=["알짜힘/합력 또는 각 힘의 방향을 알려 주세요."],
                ),
                unsupported_reason="힘 방향 또는 합력 여부가 불명확하여 가속도를 확정할 수 없습니다.",
            )

        requested = _requested(c)
        steps = [
            StepCard("문제 유형", "단일 질점에 대한 뉴턴 제2법칙 문제입니다."),
            StepCard("기본식", "알짜힘은 질량과 가속도의 곱입니다.", "F=ma"),
        ]

        try:
            if requested == "a":
                F = magnitude_si(c.knowns["F"], "N")
                m = magnitude_si(c.knowns["m"], "kg")
                if m == 0:
                    raise ValueError("질량은 0일 수 없습니다.")
                a = F / m
                steps.append(StepCard("정리", "가속도는 알짜힘을 질량으로 나눈 값입니다.", "a=F/m"))
                return SolverResult(
                    ok=True,
                    answer=Answer(symbolic="a=F/m", numeric=round(a, 6), unit="m/s²", display=f"a = {a:.3f} m/s²"),
                    answers=[AnswerItem("가속도", "a", round(a, 6), "m/s²", f"가속도 a = {a:.3f} m/s²", "primary")],
                    steps=steps + [StepCard("계산", f"F={F:.5g} N, m={m:.5g} kg → a={a:.5g} m/s²")],
                    verification=merge_reports(pre, VerificationReport(passed=True, dimension_summary="N/kg = m/s²", checks=["입력 힘은 알짜힘으로 해석했습니다." if _is_net_force_text(c.raw_text) else "단일 힘만 주어져 알짜힘으로 해석했습니다."])),
                    used_equations=["F=ma", "a=F/m"],
                    fbd=["물체에 작용하는 알짜힘 F"],
                    coordinate_guide=["힘 방향을 +방향으로 잡습니다."],
                )
            if requested == "F":
                m = magnitude_si(c.knowns["m"], "kg")
                a = magnitude_si(c.knowns["a"], "m/s^2")
                F = m * a
                steps.append(StepCard("정리", "필요한 알짜힘은 질량×가속도입니다.", "F=ma"))
                return SolverResult(
                    ok=True,
                    answer=Answer(symbolic="F=ma", numeric=round(F, 6), unit="N", display=f"F = {F:.3f} N"),
                    answers=[AnswerItem("알짜힘", "F", round(F, 6), "N", f"알짜힘 F = {F:.3f} N", "primary")],
                    steps=steps + [StepCard("계산", f"m={m:.5g} kg, a={a:.5g} m/s² → F={F:.5g} N")],
                    verification=merge_reports(pre, VerificationReport(passed=True, dimension_summary="kg·m/s² = N")),
                    used_equations=["F=ma"],
                )
            if requested == "m":
                F = magnitude_si(c.knowns["F"], "N")
                a = magnitude_si(c.knowns["a"], "m/s^2")
                if a == 0:
                    raise ValueError("가속도가 0이면 F/a로 질량을 구할 수 없습니다.")
                m = F / a
                if m <= 0:
                    raise ValueError("계산된 질량은 0보다 커야 합니다. 힘과 가속도의 방향 부호를 확인해 주세요.")
                steps.append(StepCard("정리", "질량은 알짜힘을 가속도로 나눈 값입니다.", "m=F/a"))
                return SolverResult(
                    ok=True,
                    answer=Answer(symbolic="m=F/a", numeric=round(m, 6), unit="kg", display=f"m = {m:.3f} kg"),
                    answers=[AnswerItem("질량", "m", round(m, 6), "kg", f"질량 m = {m:.3f} kg", "primary")],
                    steps=steps + [StepCard("계산", f"F={F:.5g} N, a={a:.5g} m/s² → m={m:.5g} kg")],
                    verification=merge_reports(pre, VerificationReport(passed=True, dimension_summary="N/(m/s²) = kg")),
                    used_equations=["F=ma", "m=F/a"],
                )
        except Exception as exc:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=[str(exc)]), unsupported_reason=str(exc))

        return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["구할 값을 판별하지 못했습니다."]), unsupported_reason="가속도/힘/질량 중 무엇을 구하는지 명시해 주세요.")
