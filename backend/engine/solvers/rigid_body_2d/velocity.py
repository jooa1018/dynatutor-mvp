from __future__ import annotations

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core.units import magnitude_si
from engine.physics_core.vectors import Vec2, rigid_body_velocity
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing


def _get_r_vector(c: CanonicalProblem) -> Vec2 | None:
    cd = c.coordinate_data
    if "rBAx" in cd and "rBAy" in cd:
        return Vec2(float(cd["rBAx"]), float(cd["rBAy"]))
    if "rBAx" in c.knowns and "rBAy" in c.knowns:
        return Vec2(
            magnitude_si(c.knowns["rBAx"], "m"),
            magnitude_si(c.knowns["rBAy"], "m"),
        )
    return None


def _has_fixed_A(c: CanonicalProblem) -> bool:
    return any(phrase in c.raw_text for phrase in ["고정점", "A점이 고정", "A점은 고정", "A점 고정", "A is fixed"])


def _scalar_radius(c: CanonicalProblem) -> float | None:
    q = c.knowns.get("r") or c.knowns.get("R")
    if q is None:
        return None
    return magnitude_si(q, "m")


def _get_vA(c: CanonicalProblem) -> Vec2 | None:
    cd = c.coordinate_data
    if "vAx" in cd and "vAy" in cd:
        return Vec2(float(cd["vAx"]), float(cd["vAy"]))
    if "vAx" in c.knowns and "vAy" in c.knowns:
        return Vec2(
            magnitude_si(c.knowns["vAx"], "m/s"),
            magnitude_si(c.knowns["vAy"], "m/s"),
        )
    # A zero scalar has no direction ambiguity and is a valid fixed-point vector.
    if "vA" in c.knowns and c.knowns["vA"].value is not None:
        vA = magnitude_si(c.knowns["vA"], "m/s")
        if abs(vA) <= 1e-12:
            return Vec2(0.0, 0.0)
    if _has_fixed_A(c):
        return Vec2(0.0, 0.0)
    return None


class PlaneRigidBodyVelocitySolver(BaseSolver):
    name = "plane_rigid_body_velocity"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "plane_rigid_body_velocity":
            return SolverMatch(self, 88, "평면강체 벡터 속도식 vB=vA+ω×rBA")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        vA = _get_vA(c)
        rBA = _get_r_vector(c)
        omega_sign = c.coordinate_data.get(
            "omega_sign", c.coordinate_data.get("angular_sign")
        )
        compact_raw = (c.raw_text or "").replace(" ", "").lower()
        requested = set(c.requested_outputs or c.unknowns or [])
        cartesian_requested = (
            any(
                token in compact_raw
                for token in ("x성분", "y성분", "x-component", "y-component")
            )
            or bool(
                requested
                & {"velocity_x", "velocity_y", "v_bx", "v_by"}
            )
        )
        if (
            pre.passed
            and vA is not None
            and vA.magnitude() <= 1e-12
            and not cartesian_requested
            and (rBA is None or omega_sign is None)
        ):
            r_scalar = (
                rBA.magnitude()
                if rBA is not None
                else _scalar_radius(c)
            )
            if r_scalar is not None and "omega" in c.knowns:
                omega_abs = abs(magnitude_si(c.knowns["omega"], "rad/s"))
                speed = omega_abs * r_scalar
                steps = [
                    StepCard("속력은 계산 가능", "A점이 고정이면 B점은 A를 중심으로 순간적으로 원운동합니다. 방향 성분은 r_B/A의 방향이 있어야 하지만, 속력 크기는 ωr로 바로 구할 수 있습니다.", r"|v_B|=\omega r"),
                    StepCard("계산", f"|v_B| = {omega_abs:g} × {r_scalar:g} = {speed:.5g} m/s"),
                    StepCard("성분 안내", "v_Bx, v_By 같은 벡터 성분을 계산하려면 B가 A의 오른쪽/위쪽 등 r_B/A 방향 정보가 추가로 필요합니다."),
                ]
                verification = VerificationReport(
                    passed=True,
                    dimension_summary="ωr의 단위는 m/s입니다.",
                    checks=["A점이 고정된 순수 회전이면 점 B의 속도 크기는 중심에서의 거리 r에 비례합니다."],
                    warnings=["r_B/A 방향 정보가 없어 벡터 성분은 제공하지 않고 속력 |v_B|만 계산했습니다."],
                )
                return SolverResult(
                    ok=True,
                    answer=Answer(symbolic="|vB| = ωr", numeric=round(speed, 6), unit="m/s", display=f"|v_B| = {speed:.3f} m/s"),
                    answers=[AnswerItem(label="B점 속도 크기", symbol="v_B", numeric=round(speed, 6), unit="m/s", display=f"|v_B| = {speed:.3f} m/s", role="primary")],
                    steps=steps,
                    verification=merge_reports(pre, verification),
                    used_equations=["|v_B| = ωr"],
                    coordinate_guide=["속도 방향/성분은 r_B/A 방향을 정한 뒤 오른손 법칙으로 구합니다."],
                )
        if not pre.passed or vA is None or rBA is None:
            errs = list(pre.errors)
            if vA is None:
                errs.append("A점 속도 벡터 또는 A점 고정 조건")
            if rBA is None:
                errs.append("r_B/A 벡터 또는 길이+방향 정보")
            return SolverResult(ok=False, verification=VerificationReport(False, errors=errs), unsupported_reason="평면강체 속도는 vA와 r_B/A 방향 정보가 필요합니다.")
        if omega_sign is None:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["속도 벡터 성분을 계산하려면 각속도의 시계/반시계 방향이 필요합니다."],
                ),
                unsupported_reason="각속도 ω의 회전 방향을 명시해 주세요.",
            )
        omega = float(omega_sign) * magnitude_si(c.knowns["omega"], "rad/s")
        vB = rigid_body_velocity(vA, omega, rBA)
        warning = []
        if c.coordinate_data.get("parse_notes"):
            warning.extend(c.coordinate_data.get("parse_notes", []))
        steps = [
            StepCard("벡터 속도식", "평면강체에서는 한 점의 속도와 상대 위치벡터로 다른 점 속도를 구합니다.", r"\vec v_B=\vec v_A+\vec\omega\times\vec r_{B/A}"),
            StepCard("외적항", "2D에서 ωk×(x,y)=(-ωy,ωx)입니다."),
            StepCard("계산", f"vA=({vA.x:.3g},{vA.y:.3g}), rBA=({rBA.x:.3g},{rBA.y:.3g}), signed ω={omega:.3g} → vB=({vB.x:.3f},{vB.y:.3f}) m/s"),
        ]
        verification = VerificationReport(
            passed=True,
            dimension_summary="ωr의 단위는 m/s입니다.",
            checks=["ω=0이면 회전에 의한 속도항은 0입니다.", "r=0이면 B점과 A점은 같은 속도입니다."],
            warnings=warning,
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="vB = vA + ω×rBA", numeric=round(vB.magnitude(), 6), unit="m/s", display=f"v_B = ({vB.x:.3f}, {vB.y:.3f}) m/s, |v_B| = {vB.magnitude():.3f} m/s"),
            answers=[
                AnswerItem(label="B점 속도 크기", symbol="v_B", numeric=round(vB.magnitude(), 6), unit="m/s", display=f"|v_B| = {vB.magnitude():.3f} m/s", role="primary"),
                AnswerItem(label="x 성분", symbol="v_Bx", numeric=round(vB.x, 6), unit="m/s", display=f"v_Bx = {vB.x:.3f} m/s", role="component"),
                AnswerItem(label="y 성분", symbol="v_By", numeric=round(vB.y, 6), unit="m/s", display=f"v_By = {vB.y:.3f} m/s", role="component"),
            ],
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["v_B = v_A + ω × r_B/A"],
            coordinate_guide=["오른손 법칙: +ω는 반시계방향"],
        )
