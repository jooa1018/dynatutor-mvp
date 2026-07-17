from __future__ import annotations

import math
from engine.models import (
    Answer, CanonicalProblem, EquationEvidence, SolverResult, StepCard,
    SubstitutionEvidence, VerificationReport,
)
from engine.solvers.base import BaseSolver, SolverMatch
from engine.units.dimensions import attach_unit_check
from engine.solvers.explanation_evidence import (
    OutputSpec,
    assumption_fact,
    attach_evidence,
    calculation_frame,
    gravity_fact,
    known_fact,
)


def _curve_frame(solver_name: str):
    return calculation_frame(
        f"{solver_name}.path-frame", "path_tangent_normal",
        ("t", "n"), ("tangential_positive", "normal_inward"), ("m", "m"),
    )


def _gravity_value(c: CanonicalProblem, fact) -> float:
    quantity = c.knowns.get("g")
    return float(quantity.value) if quantity is not None else 9.81


class FlatCurveFrictionSolver(BaseSolver):
    name = "flat_curve_friction"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "flat_curve_friction":
            return SolverMatch(self, 86, "평평한 커브에서 정지마찰이 구심력을 제공")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        Rq, muq = c.knowns.get("R"), c.knowns.get("mu")
        if not Rq or not muq:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["평평한 커브 최대속도에는 반지름 R과 마찰계수 μ가 필요합니다."]))
        gq = c.knowns.get("g")
        g = gq.value if gq is not None and gq.value is not None else 9.81
        if Rq.value is None or Rq.value <= 0 or muq.value is None or muq.value < 0 or g <= 0:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["반지름 R과 중력가속도 g는 0보다 크고 마찰계수 μ는 0 이상이어야 합니다."],
                ),
                unsupported_reason="커브 입력값의 물리적 범위를 확인해 주세요.",
            )
        v = math.sqrt(muq.value * g * Rq.value)
        steps = [
            StepCard("힘 역할", "평평한 커브에서는 도로가 기울어져 있지 않으므로 정지마찰력이 구심력 역할을 합니다."),
            StepCard("최대 정지마찰", "미끄러지기 직전에는 f_s,max = μN이고, 평평한 도로라서 N=mg입니다.", r"f_s=\mu mg"),
            StepCard("구심력", "구심방향으로 ΣF = mv²/R를 적용합니다.", r"\mu mg=\frac{mv^2}{R}"),
            StepCard("정리", "질량 m이 약분됩니다.", r"v_{max}=\sqrt{\mu gR}"),
        ]
        verification = VerificationReport(passed=True, checks=["μ=0이면 마찰이 없어 커브를 돌 수 있는 최대속도도 0입니다.", "R이 클수록 완만한 커브라서 허용 속도가 커집니다."])
        attach_unit_check(verification, expected_unknown="velocity", actual_unit="m/s")
        result = SolverResult(ok=True, answer=Answer(symbolic="v_max = √(μgR)", numeric=round(v, 5), unit="m/s", display=f"v_max = {v:.3f} m/s", output_key="final_velocity"), steps=steps, verification=verification, used_equations=["f_s ≤ μN", "ΣF_r = mv²/R"])
        if (
            Rq.unit != "m"
            or muq.unit not in {None, "", "1", "dimensionless"}
            or (gq is not None and gq.unit not in {"m/s^2", "m/s²"})
        ):
            return result
        radius, friction = known_fact(c, "R"), known_fact(c, "mu")
        gravity = gravity_fact(c)
        assumptions = [
            assumption_fact("motion_model", "uniform_circular"),
            assumption_fact("friction_regime", "limiting_static"),
        ]
        explicit = [radius, friction]
        if gravity.classification == "assumed":
            assumptions.append(gravity)
        else:
            explicit.append(gravity)
        fact_ids = tuple(f.fact_id for f in (*explicit, *assumptions))
        return attach_evidence(
            result,
            solver_name=self.name,
            coordinate_frame=_curve_frame(self.name),
            explicit_facts=explicit,
            assumptions=assumptions,
            equations=(
                EquationEvidence(
                    "flat-curve.limiting-speed", "v = sqrt(mu g R)",
                    "solver_equation", "newton_second_law",
                    fact_ids=fact_ids, output_ids=("final_velocity",),
                ),
            ),
            substitutions=(
                SubstitutionEvidence(
                    "flat-curve.limiting-speed.values",
                    "flat-curve.limiting-speed",
                    f"v = sqrt({muq.value} * {_gravity_value(c, gravity)} * {Rq.value}) = {result.answer.numeric} m/s",
                    "final_velocity", fact_ids=fact_ids,
                ),
            ),
            outputs=(
                OutputSpec(
                    "final_velocity", 0, "final_velocity", "final_velocity",
                    ("flat-curve.limiting-speed",),
                    ("flat-curve.limiting-speed.values",),
                ),
            ),
        )


class BankedCurveNoFrictionSolver(BaseSolver):
    name = "banked_curve_no_friction"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "banked_curve_no_friction":
            return SolverMatch(self, 84, "마찰 없는 경사진 커브의 설계속도")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        Rq, thq = c.knowns.get("R"), c.knowns.get("theta")
        if not Rq or not thq:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["경사진 커브 설계속도에는 반지름 R과 뱅크각 θ가 필요합니다."]))
        gq = c.knowns.get("g")
        g = gq.value if gq is not None and gq.value is not None else 9.81
        if (
            Rq.value is None
            or Rq.value <= 0
            or thq.value is None
            or not 0 < thq.value < 90
            or g <= 0
        ):
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["반지름 R과 중력가속도 g는 0보다 크고 뱅크각 θ는 0°<θ<90°여야 합니다."],
                ),
                unsupported_reason="경사진 커브 입력값의 물리적 범위를 확인해 주세요.",
            )
        theta = math.radians(thq.value)
        v = math.sqrt(Rq.value * g * math.tan(theta))
        steps = [
            StepCard("힘 역할", "마찰이 없으면 수직항력 N의 수평 성분이 구심력 역할을 합니다."),
            StepCard("수직방향", "수직방향 가속도는 0이므로 Ncosθ=mg입니다.", r"N\cos\theta=mg"),
            StepCard("구심방향", "중심방향으로 Nsinθ=mv²/R입니다.", r"N\sin\theta=\frac{mv^2}{R}"),
            StepCard("두 식 나누기", "두 식을 나누면 tanθ=v²/(gR)이 됩니다.", r"v=\sqrt{gR\tan\theta}"),
        ]
        verification = VerificationReport(passed=True, checks=["θ=0°이면 평평한 마찰 없는 도로라서 설계속도 0이 됩니다.", "R이 커지면 더 완만한 커브라 설계속도가 커집니다."])
        attach_unit_check(verification, expected_unknown="velocity", actual_unit="m/s")
        result = SolverResult(ok=True, answer=Answer(symbolic="v = √(gR tanθ)", numeric=round(v, 5), unit="m/s", display=f"v = {v:.3f} m/s", output_key="final_velocity"), steps=steps, verification=verification, used_equations=["Ncosθ=mg", "Nsinθ=mv²/R"])
        if (
            Rq.unit != "m"
            or thq.unit != "deg"
            or (gq is not None and gq.unit not in {"m/s^2", "m/s²"})
        ):
            return result
        radius, angle = known_fact(c, "R"), known_fact(c, "theta")
        gravity = gravity_fact(c)
        assumptions = [
            assumption_fact("motion_model", "uniform_circular"),
            assumption_fact("friction_regime", "none"),
        ]
        explicit = [radius, angle]
        if gravity.classification == "assumed":
            assumptions.append(gravity)
        else:
            explicit.append(gravity)
        fact_ids = tuple(f.fact_id for f in (*explicit, *assumptions))
        return attach_evidence(
            result,
            solver_name=self.name,
            coordinate_frame=_curve_frame(self.name),
            explicit_facts=explicit,
            assumptions=assumptions,
            equations=(
                EquationEvidence(
                    "banked-curve.design-speed", "v = sqrt(g R tan(theta))",
                    "solver_equation", "newton_second_law",
                    fact_ids=fact_ids, output_ids=("final_velocity",),
                ),
            ),
            substitutions=(
                SubstitutionEvidence(
                    "banked-curve.design-speed.values",
                    "banked-curve.design-speed",
                    f"v = sqrt({_gravity_value(c, gravity)} * {Rq.value} * tan({thq.value} deg)) = {result.answer.numeric} m/s",
                    "final_velocity", fact_ids=fact_ids,
                ),
            ),
            outputs=(
                OutputSpec(
                    "final_velocity", 0, "final_velocity", "final_velocity",
                    ("banked-curve.design-speed",),
                    ("banked-curve.design-speed.values",),
                ),
            ),
        )
