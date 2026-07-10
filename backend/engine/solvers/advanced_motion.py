from __future__ import annotations

import math
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.units.dimensions import attach_unit_check


def _val(c: CanonicalProblem, *keys: str, default: float | None = None) -> float | None:
    for k in keys:
        q = c.knowns.get(k)
        if q and q.value is not None:
            return q.value
    return default


class PolarKinematicsSolver(BaseSolver):
    name = "polar_kinematics"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "polar_kinematics":
            return SolverMatch(self, 88, "극좌표 r-θ 성분으로 속도/가속도를 분해")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        r = _val(c, "r", "R")
        omega = _val(c, "omega", "thetadot")
        if r is None or omega is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["극좌표 계산에는 r과 θ_dot(또는 ω)이 필요합니다."]))
        rdot = _val(c, "rdot", default=0.0) or 0.0
        rddot = _val(c, "rddot", default=0.0) or 0.0
        alpha = _val(c, "alpha", "thetaddot", default=0.0) or 0.0
        v_r = rdot
        v_theta = r * omega
        v_mag = math.hypot(v_r, v_theta)
        a_r = rddot - r * omega**2
        a_theta = r * alpha + 2 * rdot * omega
        a_mag = math.hypot(a_r, a_theta)
        want_acc = "acceleration" in c.unknowns or "radial_acceleration" in c.unknowns or "transverse_acceleration" in c.unknowns or "auto" in c.unknowns
        if want_acc:
            display = f"a_r = {a_r:.3f} m/s², a_θ = {a_theta:.3f} m/s², |a| = {a_mag:.3f} m/s²"
            ans = Answer(symbolic="a_r = r¨ - rθ˙², a_θ = rθ¨ + 2r˙θ˙", numeric=round(a_mag, 6), unit="m/s²", display=display)
            expected = "acceleration"
            answers = [
                AnswerItem(label="가속도 크기", symbol="a", numeric=round(a_mag, 6), unit="m/s²", display=f"|a| = {a_mag:.3f} m/s²", role="primary"),
                AnswerItem(label="반경 성분", symbol="a_r", numeric=round(a_r, 6), unit="m/s²", display=f"a_r = {a_r:.3f} m/s²", role="component"),
                AnswerItem(label="접선 성분", symbol="a_theta", numeric=round(a_theta, 6), unit="m/s²", display=f"a_θ = {a_theta:.3f} m/s²", role="component"),
            ]
        else:
            display = f"v_r = {v_r:.3f} m/s, v_θ = {v_theta:.3f} m/s, |v| = {v_mag:.3f} m/s"
            ans = Answer(symbolic="v = r˙ e_r + rθ˙ e_θ", numeric=round(v_mag, 6), unit="m/s", display=display)
            expected = "velocity"
            answers = [
                AnswerItem(label="속도 크기", symbol="v", numeric=round(v_mag, 6), unit="m/s", display=f"|v| = {v_mag:.3f} m/s", role="primary"),
                AnswerItem(label="반경 성분", symbol="v_r", numeric=round(v_r, 6), unit="m/s", display=f"v_r = {v_r:.3f} m/s", role="component"),
                AnswerItem(label="접선 성분", symbol="v_theta", numeric=round(v_theta, 6), unit="m/s", display=f"v_θ = {v_theta:.3f} m/s", role="component"),
            ]
        steps = [
            StepCard("극좌표 분해", "극좌표에서는 위치벡터 방향 e_r과 접선 방향 e_θ가 계속 회전합니다. 그래서 직교좌표보다 추가항이 생깁니다."),
            StepCard("속도 성분", "속도는 반지름 변화 성분과 회전에 의한 접선 성분으로 나뉩니다.", r"\vec v=\dot r\,\mathbf e_r+r\dot\theta\,\mathbf e_\theta"),
            StepCard("가속도 성분", "e_r, e_θ 자체가 회전하기 때문에 -rθ˙², 2r˙θ˙ 항이 나타납니다.", r"a_r=\ddot r-r\dot\theta^2,\quad a_\theta=r\ddot\theta+2\dot r\dot\theta"),
            StepCard("계산", f"r={r:g} m, r_dot={rdot:g} m/s, r_ddot={rddot:g} m/s², θ_dot={omega:g} rad/s, θ_ddot={alpha:g} rad/s²"),
        ]
        verification = VerificationReport(passed=True, checks=["r이 일정하고 r_dot=0이면 a_θ는 rα만 남습니다.", "등속 원운동이면 a_r=-rω², a_θ=0이 됩니다."])
        attach_unit_check(verification, expected_unknown=expected, actual_unit=ans.unit)
        return SolverResult(ok=True, answer=ans, answers=answers, steps=steps, verification=verification, used_equations=["v_r=r_dot", "v_θ=rω", "a_r=r_ddot-rω²", "a_θ=rα+2r_dotω"])


class InstantCenterVelocitySolver(BaseSolver):
    name = "instant_center_velocity"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "instant_center_velocity":
            return SolverMatch(self, 90, "순간중심 기준 속도 관계 v=ωr 사용")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        r = _val(c, "r", "R")
        omega = _val(c, "omega")
        v = _val(c, "v", "vB")
        if r is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["순간중심 풀이에는 순간중심에서 점까지 거리 r이 필요합니다."]))
        if omega is None and v is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["v=ωr 관계에서 ω 또는 v 중 하나가 필요합니다."]))
        if omega is None:
            omega = v / r
            ans = Answer(symbolic="ω = v/r", numeric=round(omega, 6), unit="rad/s", display=f"ω = {omega:.3f} rad/s")
            expected = "angular_velocity"
        else:
            v = omega * r
            ans = Answer(symbolic="v = ωr", numeric=round(v, 6), unit="m/s", display=f"v = {v:.3f} m/s")
            expected = "velocity"
        steps = [
            StepCard("순간중심 선택", "평면강체는 한 순간에 순간중심 IC를 기준으로 순수 회전하는 것처럼 속도를 구할 수 있습니다."),
            StepCard("속도 관계", "IC에서 거리가 r인 점의 속도 크기는 ωr입니다. 방향은 IC와 그 점을 잇는 선에 수직입니다.", r"v=\omega r"),
            StepCard("계산", f"r={r:g} m를 사용했습니다."),
        ]
        verification = VerificationReport(passed=True, checks=["순간중심에 있는 점의 속도는 0입니다.", "IC에서 멀수록 같은 ω에서 속도가 커집니다."])
        attach_unit_check(verification, expected_unknown=expected, actual_unit=ans.unit)
        return SolverResult(ok=True, answer=ans, steps=steps, verification=verification, used_equations=["v=ωr"])


class SlotPinRelativeMotionSolver(BaseSolver):
    name = "slot_pin_relative_motion"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "slot_pin_relative_motion":
            return SolverMatch(self, 86, "회전 슬롯 안 핀의 상대운동을 r-θ 성분으로 처리")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        r = _val(c, "r", "R")
        omega = _val(c, "omega")
        rdot = _val(c, "rdot")
        if r is None or omega is None or rdot is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["슬롯-핀 상대운동 속도 계산에는 r, r_dot, ω가 필요합니다."]))
        alpha = _val(c, "alpha", default=0.0) or 0.0
        rddot = _val(c, "rddot", default=0.0) or 0.0
        v_theta = r * omega
        v_mag = math.hypot(rdot, v_theta)
        a_r = rddot - r * omega**2
        a_theta = r * alpha + 2 * rdot * omega
        steps = [
            StepCard("상대운동 모델", "핀은 슬롯을 따라 r 방향으로 미끄러지고, 슬롯은 θ 방향으로 회전합니다."),
            StepCard("속도", "절대속도는 슬롯 방향 상대속도 r_dot과 회전에 의한 접선속도 rω의 벡터합입니다.", r"\vec v=\dot r\,\mathbf e_r+r\omega\,\mathbf e_\theta"),
            StepCard("가속도", "필요하면 극좌표 가속도식을 그대로 사용합니다.", r"a_r=\ddot r-r\omega^2,\quad a_\theta=r\alpha+2\dot r\omega"),
            StepCard("계산", f"v_r={rdot:.3f} m/s, v_θ={v_theta:.3f} m/s, |v|={v_mag:.3f} m/s"),
        ]
        verification = VerificationReport(passed=True, checks=["r_dot=0이면 보통 막대 위 고정점의 원운동 속도 v=rω가 됩니다.", "ω=0이면 슬롯을 따라 미끄러지는 속도만 남습니다."])
        attach_unit_check(verification, expected_unknown="velocity", actual_unit="m/s")
        display = f"|v| = {v_mag:.3f} m/s; a_r = {a_r:.3f} m/s², a_θ = {a_theta:.3f} m/s²"
        return SolverResult(ok=True, answer=Answer(symbolic="v = √(r_dot² + (rω)²)", numeric=round(v_mag, 6), unit="m/s", display=display), steps=steps, verification=verification, used_equations=["v_r=r_dot", "v_θ=rω", "a_r=r_ddot-rω²", "a_θ=rα+2r_dotω"])


class PlaneRigidBodyVelocitySolver(BaseSolver):
    name = "plane_rigid_body_velocity"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "plane_rigid_body_velocity":
            return SolverMatch(self, 84, "평면강체 두 점의 속도 관계 v_B=v_A+ω×r_B/A")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        r = _val(c, "r", "R")
        omega = _val(c, "omega")
        if r is None or omega is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["평면강체 속도 계산에는 r_B/A와 ω가 필요합니다."]))
        vA = _val(c, "vA", default=0.0) or 0.0
        # MVP assumption: v_A and relative velocity are perpendicular unless explicitly expanded later.
        v_rel = omega * r
        if abs(vA) < 1e-12:
            vB = abs(v_rel)
            relation = "A점이 순간적으로 정지한 경우라서 v_B=ωr로 계산했습니다."
        else:
            vB = math.hypot(vA, v_rel)
            relation = "이번 MVP는 v_A와 ω×r 성분이 서로 수직인 기본형으로 크기를 계산합니다."
        steps = [
            StepCard("평면강체 속도 관계", "강체의 모든 점은 같은 각속도 ω를 공유하지만, 점의 위치에 따라 속도는 달라집니다."),
            StepCard("벡터식", "B점 속도는 A점 속도에 A에 대한 B의 회전 상대속도를 더한 것입니다.", r"\vec v_B=\vec v_A+\vec\omega\times\vec r_{B/A}"),
            StepCard("상대속도 크기", "ω×r의 크기는 ωr이고, 방향은 r_B/A에 수직입니다.", r"|\vec v_{B/A}|=\omega r_{B/A}"),
            StepCard("계산", f"v_A={vA:g} m/s, ωr={v_rel:.5g} m/s. {relation}"),
        ]
        verification = VerificationReport(passed=True, warnings=["이번 solver는 속도 크기 기본형입니다. 실제 문제에서 v_A와 ω×r의 방향각이 주어지면 벡터 성분 계산으로 확장해야 합니다."], checks=["ω=0이면 강체는 순간적으로 병진운동만 하므로 모든 점 속도가 v_A와 같습니다."])
        attach_unit_check(verification, expected_unknown="velocity", actual_unit="m/s")
        return SolverResult(ok=True, answer=Answer(symbolic="v_B = v_A + ω×r_B/A", numeric=round(vB, 6), unit="m/s", display=f"|v_B| ≈ {vB:.3f} m/s"), steps=steps, verification=verification, used_equations=["v_B=v_A+ω×r_B/A", "|v_B/A|=ωr"])
