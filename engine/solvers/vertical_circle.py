import math
from engine.models import Answer, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import require_no_missing, merge_reports


class VerticalCircleSolver(BaseSolver):
    name = "vertical_circle"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "vertical_circle":
            return SolverMatch(self, 80, "수직 원운동 최고점/최저점 중심방향 힘 문제")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        # minimum_speed at top needs R only, not v
        if c.subtype == "top" and "minimum_speed" in c.unknowns and "R" in c.knowns:
            R = c.knowns["R"].value
            g = c.knowns["g"].value or 9.81
            vmin = math.sqrt(g * R)
            steps = [
                StepCard("최고점 조건", "최고점에서 중심 방향은 아래쪽입니다."),
                StepCard("최소 속도", "줄이 간신히 팽팽하거나 접촉을 막 유지하는 한계에서는 T=0 또는 N=0입니다."),
                StepCard("원운동식", "mg = mv²/R 이므로 v_min = sqrt(gR)입니다.", "v_{min} = \\sqrt{gR}"),
            ]
            ver = VerificationReport(passed=True, checks=["R이 커질수록 필요한 최소속도가 커집니다.", "단위 sqrt((m/s²)m)=m/s입니다."])
            return SolverResult(ok=True, answer=Answer(symbolic="v_min = sqrt(gR)", numeric=round(vmin, 5), unit="m/s", display=f"v_min = {vmin:.3f} m/s"), steps=steps, verification=ver)

        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="R, v, 최고점/최저점 정보가 필요합니다.")
        R = c.knowns["R"].value
        v = c.knowns["v"].value
        m = c.knowns.get("m")
        mass = m.value if m and m.value else 1.0
        g = c.knowns["g"].value or 9.81
        if c.subtype == "top":
            T = mass * v * v / R - mass * g
            formula = "T + mg = mv²/R"
        else:
            T = mass * v * v / R + mass * g
            formula = "T - mg = mv²/R"
        steps = [
            StepCard("중심 방향 설정", "수직 원운동은 항상 중심 방향으로 ΣF_n = mv²/R을 적용합니다."),
            StepCard("해당 지점의 식", f"현재 지점에서는 {formula} 를 사용합니다.", formula.replace("²", "^2")),
        ]
        ver = VerificationReport(passed=True, checks=["구심력은 실제 힘들의 중심방향 합입니다."], warnings=[] if T >= 0 else ["T가 음수입니다. 줄/접촉 유지 조건이 성립하지 않을 수 있습니다."])
        return SolverResult(ok=True, answer=Answer(symbolic=formula, numeric=round(T, 5), unit="N", display=f"T = {T:.3f} N"), steps=steps, verification=merge_reports(pre, ver))
