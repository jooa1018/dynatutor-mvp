from __future__ import annotations

from sympy import Eq

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core import symbols as S
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing
from engine.equation_generators.particle_newton import solve_particle_newton_system
from engine.model_builder import build_physical_model
from engine.model_builder.model_types import PhysicalModel


class MassivePulleyAtwoodSolver(BaseSolver):
    uses_prebuilt_physical_model = True
    name = "massive_pulley_atwood"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "massive_pulley_atwood":
            return SolverMatch(self, 96, "질량/관성모멘트가 있는 도르래 Atwood 계")
        return None

    def solve(self, c: CanonicalProblem, model: PhysicalModel | None = None) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="질량 있는 도르래에는 m1, m2, I, R이 필요합니다.")
        R = magnitude_si(c.knowns.get("Rp") or c.knowns["R"], "m")
        I = magnitude_si(c.knowns.get("Ip") or c.knowns["I"], "kg*m^2")
        model = model or build_physical_model(c)
        generated = solve_particle_newton_system(c, model)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(False, errors=generated.errors))
        sol = generated.solution
        a_val = float(sol[S.a])
        T1 = float(sol[S.T1])
        T2 = float(sol[S.T2])
        alpha = a_val / R
        verification = VerificationReport(
            passed=True,
            dimension_summary="a는 m/s², α는 rad/s², 장력은 N입니다.",
            checks=[
                "I→0이면 질량 없는 Atwood 식으로 돌아갑니다.",
                "I/R²가 커지면 분모가 커져 가속도는 작아집니다.",
                "m1=m2이면 a=0이어야 합니다.",
                f"등가질량 I/R² = {I/R**2:.3f} kg",
            ],
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="a=(m2-m1)g/(m1+m2+I/R²)", numeric=round(a_val, 6), unit="m/s²", display=f"a = {a_val:.3f} m/s², α = {alpha:.3f} rad/s², T1 = {T1:.3f} N, T2 = {T2:.3f} N"),
            answers=[
                AnswerItem("가속도", "a", round(a_val, 6), "m/s²", f"가속도 a = {a_val:.3f} m/s²", "primary"),
                AnswerItem("각가속도", "alpha", round(alpha, 6), "rad/s²", f"각가속도 α = {alpha:.3f} rad/s²", "primary"),
                AnswerItem("장력 T1", "T1", round(T1, 6), "N", f"장력 T1 = {T1:.3f} N", "primary"),
                AnswerItem("장력 T2", "T2", round(T2, 6), "N", f"장력 T2 = {T2:.3f} N", "primary"),
            ],
            steps=[
                StepCard("질량 있는 도르래", "도르래가 회전하므로 양쪽 장력이 같지 않습니다."),
                StepCard("물체 방정식", "PhysicalModel의 두 물체 힘 목록에서 Newton generator가 F=ma 식을 만들었습니다.", r"T_1-m_1g=m_1a,\quad m_2g-T_2=m_2a"),
                StepCard("도르래 회전", "PhysicalModel의 도르래 제약조건에서 Newton-Euler 회전식을 생성했습니다.", r"(T_2-T_1)R=I(a/R)"),
            ],
            verification=merge_reports(pre, verification),
            used_equations=["T1 - m1g = m1a", "m2g - T2 = m2a", "(T2-T1)R = I(a/R)"],
            fbd=["m1: T1, m1g", "m2: T2, m2g", "도르래: (T2-T1)R"],
            coordinate_guide=["m2 아래쪽을 + 방향으로 가정"],
        )
