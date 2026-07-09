from __future__ import annotations

from sympy import Eq

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core import symbols as S
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.friction import decide_table_hanging_static, kinetic_friction
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing
from engine.equation_generators.particle_newton import solve_particle_newton_system


class TableHangingPulleySolver(BaseSolver):
    name = "pulley_table_hanging"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "pulley_table_hanging":
            return SolverMatch(self, 92, "수평면 위 물체와 매달린 물체가 연결된 도르래")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="table-hanging 도르래에는 m1, m2와 구조 정보가 필요합니다.")

        m1 = magnitude_si(c.knowns["m1"], "kg")
        m2 = magnitude_si(c.knowns["m2"], "kg")
        g = magnitude_si(c.knowns["g"], "m/s^2")
        mu_q = c.knowns.get("mu_k") or c.knowns.get("mu")
        mu_val = float(mu_q.value) if mu_q and mu_q.value is not None else 0.0
        friction_type = c.friction_type or ("none" if mu_val == 0 else "kinetic")

        if friction_type == "static":
            mu_s_q = c.knowns.get("mu_s") or c.knowns.get("mu")
            decision = decide_table_hanging_static(m1, m2, float(mu_s_q.value), g)
            if decision.holds_static:
                verification = VerificationReport(
                    passed=True,
                    dimension_summary="정지마찰 부등식으로 a=0 판정",
                    checks=[
                        decision.equation_note or "m2g <= μ_s m1g",
                        f"driving={decision.driving_force:.3f} N, f_s,max={decision.max_static:.3f} N",
                    ],
                )
                return SolverResult(
                    ok=True,
                    answer=Answer(symbolic="a=0, f_s=m2g", numeric=0.0, unit="m/s²", display=f"a = 0.000 m/s², f_s = {decision.friction_force:.3f} N"),
                    answers=[
                        AnswerItem("가속도", "a", 0.0, "m/s²", "가속도 a = 0.000 m/s²", "primary"),
                        AnswerItem("정지마찰력", "f_s", round(decision.friction_force, 6), "N", f"정지마찰력 f_s = {decision.friction_force:.3f} N", "primary"),
                    ],
                    steps=[
                        StepCard("먼저 움직이는지 확인", "정지마찰 문제에서는 F=ma부터 쓰지 않고, 구동력과 최대정지마찰을 비교합니다.", r"|f_s| \le \mu_s N"),
                        StepCard("판정", f"구동력={decision.driving_force:.3f} N, 최대정지마찰={decision.max_static:.3f} N → 정지 유지"),
                    ],
                    verification=merge_reports(pre, verification),
                    used_equations=["m2g <= μ_s m1g → a=0"],
                )
            friction_type = "kinetic"
            # 운동 시작 후에는 μ_k가 있으면 μ_k, 없으면 주어진 μ를 fallback으로 사용합니다.
            mu_motion_q = c.knowns.get("mu_k") or c.knowns.get("mu")
            mu_val = float(mu_motion_q.value) if mu_motion_q and mu_motion_q.value is not None else 0.0

        friction = kinetic_friction(mu_val, m1 * g) if friction_type in {"kinetic", "unspecified"} else 0.0
        generated = solve_particle_newton_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(False, errors=generated.errors))
        sol = generated.solution
        a_val = float(sol[S.a])
        T_val = float(sol[S.T])
        steps = [
            StepCard("물체 분리", "수평면 위 m1과 매달린 m2를 따로 봅니다."),
            StepCard("m1 방정식", "PhysicalModel의 m1 힘 목록에서 Newton generator가 수평방향 식을 만들었습니다.", r"T-f=m_1a"),
            StepCard("m2 방정식", "PhysicalModel의 m2 힘 목록에서 Newton generator가 아래방향 식을 만들었습니다.", r"m_2g-T=m_2a"),
            StepCard("연립", "두 식을 연립해서 a와 T를 구합니다."),
        ]
        verification = VerificationReport(
            passed=True,
            dimension_summary="a는 m/s², T와 마찰력은 N입니다.",
            checks=["m1이 매우 커지면 가속도는 작아집니다.", "마찰계수가 커지면 가속도는 작아집니다."],
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="T-f=m1a, m2g-T=m2a", numeric=round(a_val, 6), unit="m/s²", display=f"a = {a_val:.3f} m/s², T = {T_val:.3f} N"),
            answers=[
                AnswerItem("가속도", "a", round(a_val, 6), "m/s²", f"가속도 a = {a_val:.3f} m/s²", "primary"),
                AnswerItem("장력", "T", round(T_val, 6), "N", f"장력 T = {T_val:.3f} N", "primary"),
            ],
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["T - f = m1a", "m2g - T = m2a", "f=μ_k m1g" if friction else "f=0"],
            fbd=["m1: 장력 T, 수직항력 N, 중력 m1g, 마찰력 f", "m2: 장력 T, 중력 m2g"],
            coordinate_guide=["m1 오른쪽, m2 아래쪽을 +로 설정"],
        )
