from __future__ import annotations

import math
from sympy import Eq

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core import symbols as S
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.units import magnitude_si
from engine.physics_core.friction import decide_incline_hanging_static
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing
from engine.equation_generators.particle_newton import solve_particle_newton_system


def _motion_direction(c: CanonicalProblem) -> str | None:
    raw = c.raw_text.replace(" ", "")
    if any(x in raw for x in ["m2가아래로", "m2가내려", "매달린물체가아래", "매달린물체가내려", "m2down", "hangingmassmovesdown"]):
        return "m2_down"
    if any(x in raw for x in ["m1이경사면아래", "m1가경사면아래", "m1이아래로", "m1가아래로", "경사면아래로내려", "m1down"]):
        return "m1_down"
    return None


def _solve_candidate(m1: float, m2: float, theta: float, mu: float, g: float, direction: str) -> tuple[float, float, str, list[str]]:
    if direction == "m2_down":
        # positive: m2 down, m1 up slope
        a = (m2 * g - m1 * g * math.sin(theta) - mu * m1 * g * math.cos(theta)) / (m1 + m2)
        T = m2 * g - m2 * a
        eqs = ["T - m1g sinθ - μm1g cosθ = m1a", "m2g - T = m2a"]
        label = "m2가 아래로, m1이 경사면 위로"
    elif direction == "m1_down":
        # positive: m1 down slope, m2 up
        a = (m1 * g * math.sin(theta) - mu * m1 * g * math.cos(theta) - m2 * g) / (m1 + m2)
        T = m2 * g + m2 * a
        eqs = ["m1g sinθ - μm1g cosθ - T = m1a", "T - m2g = m2a"]
        label = "m1이 경사면 아래로, m2가 위로"
    else:
        raise ValueError(direction)
    return a, T, label, eqs


class InclineHangingPulleySolver(BaseSolver):
    name = "pulley_incline_hanging"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "pulley_incline_hanging":
            return SolverMatch(self, 91, "경사면 위 물체와 매달린 물체가 연결된 도르래")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="경사면-매달림 도르래에는 m1, m2, 경사각 θ가 필요합니다.")

        friction_type = c.friction_type
        if friction_type is None:
            if "mu_s" in c.knowns:
                friction_type = "static"
            elif "mu_k" in c.knowns or "mu" in c.knowns:
                friction_type = "kinetic"
            elif (c.flags or {}).get("no_friction"):
                friction_type = "none"
            else:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=["경사면의 마찰 유무 또는 마찰계수가 필요합니다."],
                    ),
                    unsupported_reason="경사면이 무마찰인지, 정지/운동마찰이 있는지 알려 주세요.",
                )
        requested = set(c.requested_outputs or c.unknowns or [])
        m1 = magnitude_si(c.knowns["m1"], "kg")
        m2 = magnitude_si(c.knowns["m2"], "kg")
        g = magnitude_si(c.knowns["g"], "m/s^2") if "g" in c.knowns else 9.81
        theta = math.radians(magnitude_si(c.knowns["theta"], "deg"))
        if m1 <= 0 or m2 <= 0 or g <= 0:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["m1, m2, g는 모두 0보다 커야 합니다."],
                ),
            )
        if not 0 <= theta < math.pi / 2:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["기본 경사면 각도 θ는 0도 이상 90도 미만이어야 합니다."],
                ),
            )

        if friction_type == "static":
            mu_s_q = c.knowns.get("mu_s") or c.knowns.get("mu")
            if mu_s_q is None or mu_s_q.value is None:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=["정지마찰 판정에는 정지마찰계수 μ_s가 필요합니다."],
                    ),
                    unsupported_reason="정지마찰계수 μ_s를 알려 주세요.",
                )
            mu_s = float(mu_s_q.value)
            if mu_s < 0:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=["정지마찰계수 μ_s는 0 이상이어야 합니다."],
                    ),
                )
            decision = decide_incline_hanging_static(m1, m2, theta, mu_s, g)
            if decision.holds_static:
                T_static = m2 * g
                verification = VerificationReport(
                    passed=True,
                    dimension_summary="정지마찰 부등식으로 a=0 판정",
                    checks=[
                        decision.equation_note or "|m2g - m1g sinθ| <= μ_s m1g cosθ",
                        f"driving={decision.driving_force:.3f} N, f_s,max={decision.max_static:.3f} N",
                    ],
                )
                return SolverResult(
                    ok=True,
                    answer=Answer(symbolic="a=0, |f_s|<=μ_sN", numeric=0.0, unit="m/s²", display=f"a = 0.000 m/s², T = {T_static:.3f} N, f_s = {decision.friction_force:.3f} N"),
                    answers=[
                        AnswerItem("가속도", "a", 0.0, "m/s²", "가속도 a = 0.000 m/s²", "primary"),
                        AnswerItem("장력", "T", round(T_static, 6), "N", f"장력 T = {T_static:.3f} N", "primary"),
                        AnswerItem("정지마찰력", "f_s", round(decision.friction_force, 6), "N", f"정지마찰력 f_s = {decision.friction_force:.3f} N", "primary"),
                    ],
                    steps=[
                        StepCard("정지마찰 판정", "경사면-매달림 계도 먼저 운동 경향을 정지마찰이 버틸 수 있는지 확인합니다.", r"|m_2g-m_1g\sin\theta| \le \mu_s m_1g\cos\theta"),
                        StepCard("판정", f"구동력={decision.driving_force:.3f} N, 최대정지마찰={decision.max_static:.3f} N → 정지 유지"),
                    ],
                    verification=merge_reports(pre, verification),
                    used_equations=["|m2g - m1g sinθ| <= μ_s m1g cosθ → a=0"],
                    fbd=["m1: T, m1g sinθ, N, f_s", "m2: m2g, T"],
                    coordinate_guide=["정지 상태에서는 운동 방향을 가정하지 않고 힘 평형을 봅니다."],
                )

        mu_q = (
            c.knowns.get("mu_k")
            if friction_type == "static"
            else c.knowns.get("mu_k") or c.knowns.get("mu")
        )
        if friction_type in {"static", "kinetic", "unspecified"} and (
            mu_q is None or mu_q.value is None
        ):
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["운동마찰을 포함한 후속 운동에는 운동마찰계수 μ_k가 필요합니다."],
                ),
                unsupported_reason="정지마찰계수와 별도로 운동마찰계수 μ_k를 알려 주세요.",
            )
        mu = float(mu_q.value) if mu_q and mu_q.value is not None else 0.0
        if mu < 0:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["운동마찰계수 μ_k는 0 이상이어야 합니다."],
                ),
            )
        direction_hint = _motion_direction(c)

        if friction_type in {"kinetic", "unspecified"} and mu > 0 and direction_hint is None:
            cand_down = _solve_candidate(m1, m2, theta, mu, g, "m2_down")
            cand_up = _solve_candidate(m1, m2, theta, mu, g, "m1_down")
            verification = VerificationReport(
                passed=False,
                errors=["운동마찰 방향을 확정하려면 실제 운동 방향이 필요합니다."],
                warnings=[
                    "m2가 아래로 내려가는 경우와 m1이 경사면 아래로 내려가는 경우의 마찰 방향이 서로 다릅니다.",
                    f"m2 하강 가정: a={cand_down[0]:.3f} m/s², T={cand_down[1]:.3f} N",
                    f"m1 하강 가정: a={cand_up[0]:.3f} m/s², T={cand_up[1]:.3f} N",
                ],
            )
            return SolverResult(
                ok=False,
                verification=merge_reports(pre, verification),
                unsupported_reason="운동 방향이 주어지지 않아 운동마찰 방향을 확정할 수 없습니다. m2가 아래로 내려가는지, m1이 경사면 아래로 내려가는지 명시해 주세요.",
                steps=[
                    StepCard("운동마찰 방향 확인", "운동마찰은 실제 운동 방향의 반대로 작용합니다."),
                    StepCard("가능한 해석", f"1. m2가 아래로 내려가는 경우: a={cand_down[0]:.3f} m/s²\n2. m1이 경사면 아래로 내려가는 경우: a={cand_up[0]:.3f} m/s²"),
                ],
                used_equations=["운동 방향 명시 필요"],
                coordinate_guide=["m2 하강 또는 m1 경사면 하강 중 실제 운동 방향을 문제에 추가하세요."],
            )

        if friction_type == "static":
            # If static friction cannot hold, do not silently switch to a kinetic
            # answer unless the problem also gives motion direction and kinetic μ.
            if direction_hint is None:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=["정지마찰이 버티지 못하는 경우 실제 운동 방향과 운동마찰계수가 필요합니다."],
                    ),
                    unsupported_reason="정지마찰 이후 운동 방향/운동마찰계수가 명시되지 않아 최종 가속도를 확정할 수 없습니다.",
                )

        if direction_hint:
            a_val, T_val, direction_label, eqs = _solve_candidate(m1, m2, theta, mu, g, direction_hint)
            f_val = mu * m1 * g * math.cos(theta)
            if a_val < -1e-9:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=[f"문제에 주어진 운동 방향({direction_label})과 힘의 크기가 서로 맞지 않습니다."],
                        warnings=[f"해당 방향 기준 계산값 a={a_val:.3f} m/s²"],
                    ),
                    unsupported_reason="명시된 운동 방향과 계산된 부호가 모순됩니다. 운동 방향 또는 마찰계수를 확인해 주세요.",
                )
            steps = [
                StepCard("운동 방향", f"문제에서 '{direction_label}' 방향이 주어졌으므로 그 방향을 +로 잡습니다."),
                StepCard("마찰 방향", "운동마찰은 실제 운동 방향의 반대방향입니다."),
                StepCard("방정식", "\n".join(eqs)),
                StepCard("계산 결과", f"a={a_val:.5g} m/s², T={T_val:.5g} N"),
            ]
            verification = VerificationReport(
                passed=True,
                dimension_summary="a는 m/s², T는 N입니다.",
                checks=["운동 방향이 명시되어 마찰 방향을 확정했습니다."],
            )
            return SolverResult(
                ok=True,
                answer=Answer(symbolic=", ".join(eqs), numeric=round(a_val, 6), unit="m/s²", display=f"a = {a_val:.3f} m/s² ({direction_label}), T = {T_val:.3f} N"),
                answers=[
                    AnswerItem("가속도", "a", round(a_val, 6), "m/s²", f"가속도 a = {a_val:.3f} m/s²", "primary"),
                    AnswerItem("장력", "T", round(T_val, 6), "N", f"장력 T = {T_val:.3f} N", "primary"),
                ] + (
                    [
                        AnswerItem(
                            "운동마찰력",
                            "f_k",
                            round(f_val, 6),
                            "N",
                            f"운동마찰력 f_k = {f_val:.3f} N",
                            "component",
                        )
                    ]
                    if friction_type in {"static", "kinetic", "unspecified"}
                    else [
                        AnswerItem("마찰력", "f", 0.0, "N", "마찰력 f = 0.000 N", "component")
                    ]
                    if "friction_force" in requested
                    else []
                ),
                steps=steps,
                verification=merge_reports(pre, verification),
                used_equations=eqs,
                fbd=["m1: T, m1g sinθ, N, f_k", "m2: m2g, T"],
                coordinate_guide=[f"+ 방향: {direction_label}"],
            )

        if (friction_type in {None, "none"} or mu == 0) and direction_hint is None:
            # Frictionless case: the sign of a itself determines the actual direction,
            # so no external motion-direction statement is required.
            a_signed = (m2 * g - m1 * g * math.sin(theta)) / (m1 + m2)
            if a_signed >= 0:
                direction_label = "m2가 아래로, m1이 경사면 위로"
                T_val = m2 * g - m2 * a_signed
            else:
                direction_label = "m1이 경사면 아래로, m2가 위로"
                T_val = m2 * g + m2 * abs(a_signed)
            steps = [
                StepCard("마찰 없음", "마찰이 없으면 운동방향을 미리 몰라도 힘의 차이 부호로 실제 방향을 판정할 수 있습니다."),
                StepCard("방정식", "T - m1g sinθ = m1a, m2g - T = m2a"),
                StepCard("부호 해석", f"signed a={a_signed:.5g} m/s² → {direction_label}"),
            ]
            verification = VerificationReport(
                passed=True,
                dimension_summary="a는 m/s², T는 N입니다.",
                checks=["마찰이 없어 운동방향 모호성이 없습니다."],
            )
            return SolverResult(
                ok=True,
                answer=Answer(symbolic="T-m1g sinθ=m1a, m2g-T=m2a", numeric=round(abs(a_signed), 6), unit="m/s²", display=f"a = {abs(a_signed):.3f} m/s² ({direction_label}), T = {T_val:.3f} N"),
                answers=[
                    AnswerItem("가속도", "a", round(abs(a_signed), 6), "m/s²", f"가속도 a = {abs(a_signed):.3f} m/s²", "primary"),
                    AnswerItem("장력", "T", round(T_val, 6), "N", f"장력 T = {T_val:.3f} N", "primary"),
                ] + (
                    [AnswerItem("마찰력", "f", 0.0, "N", "마찰력 f = 0.000 N", "component")]
                    if "friction_force" in requested
                    else []
                ),
                steps=steps,
                verification=merge_reports(pre, verification),
                used_equations=["T - m1g sinθ = m1a", "m2g - T = m2a"],
                fbd=["m1: T, m1g sinθ, N", "m2: m2g, T"],
                coordinate_guide=["+ 방향 부호로 실제 운동 방향을 판정"],
            )

        generated = solve_particle_newton_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(False, errors=generated.errors))
        sol = generated.solution
        a_val = float(sol[S.a])
        T_val = float(sol[S.T])
        f_val = float(sol[S.F]) if S.F in sol else 0.0
        direction = "m2가 내려가고 m1이 경사면 위로" if a_val >= 0 else "m1이 경사면 아래로"
        steps = [
            StepCard("방향 가정", "마찰이 없거나 방향 영향이 없는 경우 m2 아래, m1 경사면 위를 +방향으로 둡니다."),
            StepCard("경사면 물체", "PhysicalModel의 경사면 물체 힘 목록에서 Newton generator가 식을 만들었습니다.", r"T-m_1g\sin\theta=m_1a"),
            StepCard("매달린 물체", "PhysicalModel의 매달린 물체 힘 목록에서 Newton generator가 식을 만들었습니다.", r"m_2g-T=m_2a"),
            StepCard("부호 해석", "a가 음수면 실제 운동 방향은 가정과 반대입니다."),
        ]
        verification = VerificationReport(
            passed=True,
            dimension_summary="a는 m/s², T는 N입니다.",
            checks=[
                "마찰이 없고 θ=0이면 table-hanging 형태와 가까워집니다.",
                "결과 부호로 실제 운동 방향을 확인합니다.",
            ],
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="T-m1g sinθ=m1a, m2g-T=m2a", numeric=round(abs(a_val), 6), unit="m/s²", display=f"a = {abs(a_val):.3f} m/s² ({direction}), T = {T_val:.3f} N"),
            answers=[
                AnswerItem("가속도", "a", round(abs(a_val), 6), "m/s²", f"가속도 a = {abs(a_val):.3f} m/s²", "primary"),
                AnswerItem("장력", "T", round(T_val, 6), "N", f"장력 T = {T_val:.3f} N", "primary"),
            ] + (
                [
                    AnswerItem(
                        "운동마찰력",
                        "f_k",
                        round(f_val, 6),
                        "N",
                        f"운동마찰력 f_k = {f_val:.3f} N",
                        "component",
                    )
                ]
                if friction_type in {"static", "kinetic", "unspecified"}
                else [
                    AnswerItem("마찰력", "f", 0.0, "N", "마찰력 f = 0.000 N", "component")
                ]
                if "friction_force" in requested
                else []
            ),
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["T - m1g sinθ = m1a", "m2g - T = m2a"],
            fbd=["m1: T, m1g sinθ, N", "m2: m2g, T"],
            coordinate_guide=["+ 방향: m1 경사면 위, m2 아래"],
        )
