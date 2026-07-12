from __future__ import annotations

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core.units import magnitude_si
from engine.physics_core.vectors import Vec2, rigid_body_acceleration
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing


def _has_fixed_A(c: CanonicalProblem) -> bool:
    return any(
        phrase in (c.raw_text or "")
        for phrase in ("고정점", "A점이 고정", "A점은 고정", "A점 고정", "A is fixed")
    )


def _get_aA(c: CanonicalProblem) -> Vec2 | None:
    cd = c.coordinate_data
    if "aAx" in cd and "aAy" in cd:
        return Vec2(float(cd["aAx"]), float(cd["aAy"]))
    if "aAx" in c.knowns and "aAy" in c.knowns:
        return Vec2(
            magnitude_si(c.knowns["aAx"], "m/s^2"),
            magnitude_si(c.knowns["aAy"], "m/s^2"),
        )
    if "aA" in c.knowns and c.knowns["aA"].value is not None:
        aA = magnitude_si(c.knowns["aA"], "m/s^2")
        if abs(aA) <= 1e-12:
            return Vec2(0.0, 0.0)
    if _has_fixed_A(c):
        return Vec2(0.0, 0.0)
    return None


def _get_rBA(c: CanonicalProblem) -> Vec2 | None:
    cd = c.coordinate_data
    if "rBAx" in cd and "rBAy" in cd:
        return Vec2(float(cd["rBAx"]), float(cd["rBAy"]))
    if "rBAx" in c.knowns and "rBAy" in c.knowns:
        return Vec2(
            magnitude_si(c.knowns["rBAx"], "m"),
            magnitude_si(c.knowns["rBAy"], "m"),
        )
    return None


def _scalar_radius(c: CanonicalProblem) -> float | None:
    q = c.knowns.get("r") or c.knowns.get("R")
    if q is None:
        return None
    return magnitude_si(q, "m")


class PlaneRigidBodyAccelerationSolver(BaseSolver):
    name = "plane_rigid_body_acceleration"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "plane_rigid_body_acceleration":
            return SolverMatch(self, 90, "평면강체 벡터 가속도식 aB=aA+α×r+ω×(ω×r)")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        rBA = _get_rBA(c)
        aA = _get_aA(c)
        omega_magnitude = magnitude_si(c.knowns["omega"], "rad/s") if "omega" in c.knowns else None
        alpha_magnitude = magnitude_si(c.knowns["alpha"], "rad/s^2") if "alpha" in c.knowns else None
        omega_sign = c.coordinate_data.get("omega_sign")
        alpha_sign = c.coordinate_data.get("alpha_sign")
        if omega_sign is None and alpha_sign is None:
            omega_sign = alpha_sign = c.coordinate_data.get("angular_sign")
        compact_raw = (c.raw_text or "").replace(" ", "").lower()
        requested = set(c.requested_outputs or c.unknowns or [])
        cartesian_requested = (
            any(
                token in compact_raw
                for token in ("x성분", "y성분", "x-component", "y-component")
            )
            or bool(
                requested
                & {
                    "acceleration_x",
                    "acceleration_y",
                    "a_bx",
                    "a_by",
                }
            )
        )

        if (
            pre.passed
            and aA is not None
            and aA.magnitude() <= 1e-12
            and not cartesian_requested
            and (
                rBA is None
                or omega_sign is None
                or alpha_sign is None
            )
        ):
            radius = (
                rBA.magnitude()
                if rBA is not None
                else _scalar_radius(c)
            )
            if radius is not None and omega_magnitude is not None and alpha_magnitude is not None:
                if radius < 0:
                    return SolverResult(
                        ok=False,
                        verification=VerificationReport(
                            passed=False,
                            errors=["두 점 사이 거리 r은 0 이상이어야 합니다."],
                        ),
                    )
                a_t = abs(alpha_magnitude) * radius
                a_n = omega_magnitude * omega_magnitude * radius
                magnitude = (a_t * a_t + a_n * a_n) ** 0.5
                verification = VerificationReport(
                    passed=True,
                    dimension_summary="αr, ω²r 모두 m/s²입니다.",
                    checks=[
                        "A점 가속도가 0이면 접선항과 법선항은 서로 수직입니다.",
                        "방향이 없어도 |a_B| = sqrt((αr)² + (ω²r)²)는 결정됩니다.",
                    ],
                    warnings=[
                        "r_B/A 방향 정보가 없어 x, y 성분은 제공하지 않았습니다."
                    ],
                )
                return SolverResult(
                    ok=True,
                    answer=Answer(
                        symbolic="|a_B| = sqrt((αr)² + (ω²r)²)",
                        numeric=round(magnitude, 6),
                        unit="m/s²",
                        display=f"|a_B| = {magnitude:.3f} m/s²",
                    ),
                    answers=[
                        AnswerItem("B점 가속도 크기", "a_B", round(magnitude, 6), "m/s²", f"|a_B| = {magnitude:.3f} m/s²", "primary"),
                        AnswerItem("접선 성분 크기", "a_t", round(a_t, 6), "m/s²", f"a_t = {a_t:.3f} m/s²", "component"),
                        AnswerItem("법선 성분 크기", "a_n", round(a_n, 6), "m/s²", f"a_n = {a_n:.3f} m/s²", "component"),
                    ],
                    steps=[
                        StepCard("고정 기준점", "A점 가속도가 0이므로 B점의 상대 접선·법선 가속도만 고려합니다."),
                        StepCard("성분 크기", f"a_t=|α|r={a_t:.5g}, a_n=ω²r={a_n:.5g} m/s²"),
                        StepCard("합성", "두 성분은 서로 수직이므로 피타고라스 합성으로 크기를 구합니다."),
                    ],
                    verification=merge_reports(pre, verification),
                    used_equations=["a_t = |α|r", "a_n = ω²r", "|a_B| = sqrt(a_t²+a_n²)"],
                    coordinate_guide=["벡터 성분은 r_B/A 방향을 추가로 지정해야 합니다."],
                )

        if not pre.passed or rBA is None or aA is None:
            errs = list(pre.errors)
            if aA is None:
                errs.append("A점 가속도 벡터 또는 A점 고정 조건")
            if rBA is None:
                errs.append("r_B/A 벡터 또는 고정 A에서의 거리")
            return SolverResult(
                ok=False,
                verification=VerificationReport(False, errors=list(dict.fromkeys(errs))),
                unsupported_reason="성분 계산에는 a_A와 r_B/A의 벡터 성분이 필요합니다.",
            )
        if omega_sign is None or alpha_sign is None:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["가속도 벡터 성분에는 각속도와 각가속도의 회전 방향이 각각 필요합니다."],
                ),
                unsupported_reason="ω와 α의 시계/반시계 방향을 명시해 주세요.",
            )
        omega = float(omega_sign) * omega_magnitude
        alpha = float(alpha_sign) * alpha_magnitude
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
