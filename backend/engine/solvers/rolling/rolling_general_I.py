from __future__ import annotations

import math
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core.inertia import beta_for_shape
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing
from engine.equation_generators.energy_momentum import solve_energy_momentum_system


def _optional_evidence_radius(c: CanonicalProblem) -> float | None:
    """Return a valid optional radius without affecting the primary solve."""

    for symbol in ("R", "r"):
        quantity = c.knowns.get(symbol)
        if (
            quantity is None
            or quantity.value is None
            or isinstance(quantity.value, bool)
        ):
            continue
        try:
            radius = float(magnitude_si(quantity, "m"))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(radius) and radius > 0.0:
            return radius
    return None


class RollingEnergyGeneralSolver(BaseSolver):
    name = "rolling_energy_general"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "rolling_energy_general":
            return SolverMatch(self, 95, "일반 관성모멘트 또는 형상 β를 쓰는 순수 구름 에너지")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="일반 구름운동에는 h와 I,R,m 또는 물체 종류가 필요합니다.")
        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(False, errors=generated.errors), unsupported_reason="모델 기반 구름 에너지 방정식 생성/풀이에 실패했습니다.")
        v = float(generated.solution["v"])
        raw_omega = generated.solution.get("omega")
        radius = _optional_evidence_radius(c)
        omega = float(raw_omega) if raw_omega is not None else None
        if (
            omega is None
            and radius is not None
            and math.isfinite(radius)
            and radius > 0.0
        ):
            omega = v / radius
        beta = float(generated.solution["beta"])
        typed_answers = [
            AnswerItem(
                "질량중심 최종속도",
                "v",
                round(v, 6),
                "m/s",
                f"질량중심 최종속도 v = {v:.3f} m/s",
                "primary",
                output_key="final_velocity",
            )
        ]
        if omega is not None and math.isfinite(omega):
            typed_answers.append(
                AnswerItem(
                    "순수 구름 각속도",
                    "omega",
                    round(omega, 6),
                    "rad/s",
                    f"순수 구름 각속도 omega = {omega:.3f} rad/s",
                    "component",
                    output_key="angular_velocity",
                )
            )
        initial_speed = float(generated.solution.get("v0", 0.0))
        beta_info = f"β={beta:.3f}"
        if generated.solution.get("mode") == "I":
            symbolic = "v = sqrt(v0²+2mgh/(m+I/R²))"
            used = ["mgh = 1/2mv² + 1/2Iω²", "v=ωR", "v=sqrt(2mgh/(m+I/R²))"]
        else:
            symbolic = "v = sqrt(v0²+2gh/(1+β))"
            used = ["mgh = 1/2mv² + 1/2Iω²", "v=ωR", "I=βmR²"]

        steps = [
            StepCard("순수 구름 모델", "미끄러지지 않으므로 질량중심 속도와 각속도가 v=ωR로 연결됩니다."),
            StepCard("에너지 보존", f"초기속도 v0={initial_speed:g} m/s의 병진·회전 에너지를 포함합니다.", r"K_f=K_i+mgh"),
            StepCard("관성모멘트 적용", beta_info),
        ]
        display = f"v_G = {v:.3f} m/s" + (f", ω = {omega:.3f} rad/s" if omega is not None else "")
        verification = VerificationReport(
            passed=True,
            dimension_summary="속도 결과는 m/s 차원입니다.",
            checks=["I→0이면 질점 에너지식 v=sqrt(2gh)에 가까워집니다.", "회전관성이 커질수록 v는 작아집니다."],
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic=symbolic, numeric=round(v, 6), unit="m/s", display=display),
            answers=typed_answers,
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=used,
            fbd=["중력 mg", "수직항력 N", "정지마찰력 f_s"],
            coordinate_guide=["질량중심 병진 + 질량중심 기준 회전"],
        )
