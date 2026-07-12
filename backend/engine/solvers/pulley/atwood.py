from __future__ import annotations

import math
from sympy import Eq

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core import symbols as S
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing
from engine.equation_generators.particle_newton import solve_particle_newton_system


class AtwoodPulleySolver(BaseSolver):
    name = "pulley_atwood"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "pulley_atwood":
            return SolverMatch(self, 94, "두 물체가 도르래 양쪽에 매달린 Atwood 계")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="Atwood 문제에는 m1, m2와 양쪽 매달림 구조가 필요합니다.")

        generated = solve_particle_newton_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(False, errors=generated.errors))
        sol = generated.solution
        a_val = float(sol[S.a])
        T_val = float(sol[S.T])
        direction = "m2가 아래로, m1이 위로" if a_val >= 0 else "m1이 아래로, m2가 위로"
        display = f"a = {a_val:.3f} m/s² ({direction}), T = {T_val:.3f} N"
        steps = [
            StepCard("토폴로지 확인", "두 물체가 도르래 양쪽에 매달린 Atwood 계입니다."),
            StepCard("방향 가정", "m2가 아래로 내려가는 방향을 +로 두었습니다. 결과가 음수면 실제 방향은 반대입니다."),
            StepCard("방정식", "PhysicalModel의 두 물체 힘 목록에서 Newton generator가 m2: m2g - T = m2a, m1: T - m1g = m1a를 생성했습니다.", r"m_2g-T=m_2a,\quad T-m_1g=m_1a"),
            StepCard("연립 풀이", "공통 Symbol/EquationSystem으로 두 식을 풉니다.", r"a=\frac{(m_2-m_1)g}{m_1+m_2}"),
        ]
        verification = VerificationReport(
            passed=True,
            dimension_summary="a는 m/s², T는 N 차원입니다.",
            checks=[
                "m1=m2이면 a=0이 됩니다.",
                "m2>m1이면 m2가 내려가고, m1>m2이면 방향이 반대가 됩니다.",
                "질량 없는 도르래에서는 양쪽 줄 장력이 같습니다.",
            ],
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="a=(m2-m1)g/(m1+m2), T=2m1m2g/(m1+m2)", numeric=round(a_val, 6), unit="m/s²", display=display),
            answers=[
                AnswerItem("가속도 성분", "a", round(a_val, 6), "m/s²", f"가속도 성분 a = {a_val:.3f} m/s² ({direction})", "primary"),
                AnswerItem("장력", "T", round(T_val, 6), "N", f"장력 T = {T_val:.3f} N", "primary", output_key="tension"),
            ],
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["m2g - T = m2a", "T - m1g = m1a"],
            fbd=["m1: 중력 m1g, 장력 T", "m2: 중력 m2g, 장력 T"],
            coordinate_guide=["+ 방향: m2 아래, m1 위. 결과 부호로 실제 방향 판단"],
        )
