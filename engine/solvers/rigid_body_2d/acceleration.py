from __future__ import annotations

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core.units import magnitude_si
from engine.physics_core.vectors import Vec2, rigid_body_acceleration
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing


def _get_aA(c: CanonicalProblem) -> Vec2:
    cd = c.coordinate_data
    if "aAx" in cd or "aAy" in cd:
        return Vec2(float(cd.get("aAx", 0.0)), float(cd.get("aAy", 0.0)))
    if "aA" in c.knowns:
        return Vec2(magnitude_si(c.knowns["aA"], "m/s^2"), 0.0)
    return Vec2(0.0, 0.0)


def _get_rBA(c: CanonicalProblem) -> Vec2 | None:
    cd = c.coordinate_data
    if "rBAx" in cd and "rBAy" in cd:
        return Vec2(float(cd["rBAx"]), float(cd["rBAy"]))
    if "r" in c.knowns or "R" in c.knowns:
        return Vec2(magnitude_si(c.knowns.get("r") or c.knowns.get("R"), "m"), 0.0)
    return None


class PlaneRigidBodyAccelerationSolver(BaseSolver):
    name = "plane_rigid_body_acceleration"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "plane_rigid_body_acceleration":
            return SolverMatch(self, 90, "평면강체 벡터 가속도식 aB=aA+α×r+ω×(ω×r)")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        rBA = _get_rBA(c)
        if not pre.passed or rBA is None:
            errs = list(pre.errors)
            if rBA is None:
                errs.append("r_B/A 벡터 또는 길이+방향 정보")
            return SolverResult(ok=False, verification=VerificationReport(False, errors=errs), unsupported_reason="평면강체 가속도는 r_B/A와 각속도/각가속도가 필요합니다.")
        aA = _get_aA(c)
        sign = float(c.coordinate_data.get("angular_sign", 1.0))
        omega = sign * magnitude_si(c.knowns["omega"], "rad/s")
        alpha = sign * magnitude_si(c.knowns["alpha"], "rad/s^2")
        aB = rigid_body_acceleration(aA, alpha, omega, rBA)
        a_t = abs(alpha) * rBA.magnitude()
        a_n = omega**2 * rBA.magnitude()
        steps = [
            StepCard("벡터 가속도식", "접선가속도와 법선가속도 항을 모두 포함합니다.", r"\vec a_B=\vec a_A+\vec\alpha\times\vec r_{B/A}+\vec\omega\times(\vec\omega\times\vec r_{B/A})"),
            StepCard("성분", f"접선 성분 αr={a_t:.3f}, 법선 성분 ω²r={a_n:.3f}"),
            StepCard("계산", f"aA=({aA.x:.3f},{aA.y:.3f}), rBA=({rBA.x:.3f},{rBA.y:.3f}), signed ω={omega:.3g}, signed α={alpha:.3g} → aB=({aB.x:.3f},{aB.y:.3f}) m/s²"),
        ]
        verification = VerificationReport(
            passed=True,
            dimension_summary="αr, ω²r 모두 m/s²입니다.",
            checks=["ω=0이면 법선가속도항은 0입니다.", "α=0이면 접선가속도항은 0입니다.", "r=0이면 B점과 A점은 같은 가속도입니다."],
            warnings=c.coordinate_data.get("parse_notes", []),
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="aB = aA + α×rBA + ω×(ω×rBA)", numeric=round(aB.magnitude(), 6), unit="m/s²", display=f"a_B = ({aB.x:.3f}, {aB.y:.3f}) m/s², |a_B| = {aB.magnitude():.3f} m/s², a_t = {a_t:.3f}, a_n = {a_n:.3f}"),
            answers=[
                AnswerItem(label="B점 가속도 크기", symbol="a_B", numeric=round(aB.magnitude(), 6), unit="m/s²", display=f"|a_B| = {aB.magnitude():.3f} m/s²", role="primary"),
                AnswerItem(label="x 성분", symbol="a_Bx", numeric=round(aB.x, 6), unit="m/s²", display=f"a_Bx = {aB.x:.3f} m/s²", role="component"),
                AnswerItem(label="y 성분", symbol="a_By", numeric=round(aB.y, 6), unit="m/s²", display=f"a_By = {aB.y:.3f} m/s²", role="component"),
                AnswerItem(label="접선 성분", symbol="a_t", numeric=round(a_t, 6), unit="m/s²", display=f"a_t = {a_t:.3f} m/s²", role="component"),
                AnswerItem(label="법선 성분", symbol="a_n", numeric=round(a_n, 6), unit="m/s²", display=f"a_n = {a_n:.3f} m/s²", role="component"),
            ],
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["a_B = a_A + α × r_B/A + ω × (ω × r_B/A)"],
            coordinate_guide=["2D에서 α×r=(-αy, αx), ω×(ω×r)=(-ω²x,-ω²y)"],
        )
