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


class RelativeAccelerationTranslationSolver(BaseSolver):
    """Basic relative acceleration in a translating frame.

    Scalar MVP form: a_B = a_A + a_{B/A}. Direction angles are intentionally not
    inferred. If angles are needed later, this becomes a vector solver.
    """

    name = "relative_acceleration_translation"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "relative_acceleration_translation":
            return SolverMatch(self, 86, "병진 기준계 상대가속도 a_B=a_A+a_B/A")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        a_a = _val(c, "aA")
        a_rel = _val(c, "arel")
        if a_a is None or a_rel is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["상대가속도 기본형에는 aA와 a_rel이 필요합니다."]))
        a_b = a_a + a_rel
        steps = [
            StepCard("기준점 선택", "A점을 기준으로 B점의 상대가속도를 더합니다. 이번 MVP는 같은 직선 위 성분으로 해석합니다."),
            StepCard("상대가속도 관계", "병진 기준계라면 회전항 없이 단순히 기준점 가속도와 상대가속도를 더합니다.", r"\vec a_B=\vec a_A+\vec a_{B/A}"),
            StepCard("계산", f"a_A={a_a:g} m/s², a_B/A={a_rel:g} m/s² → a_B={a_b:.3f} m/s²"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=[
                "a_rel=0이면 두 점은 같은 가속도 a_A를 가집니다.",
                "방향각이 있는 문제는 성분을 나눠 벡터합으로 확장해야 합니다.",
            ],
        )
        attach_unit_check(verification, expected_unknown="acceleration", actual_unit="m/s²")
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="a_B = a_A + a_{B/A}", numeric=round(a_b, 6), unit="m/s²", display=f"a_B = {a_b:.3f} m/s²"),
            answers=[AnswerItem(label="B점 가속도", symbol="a_B", numeric=round(a_b, 6), unit="m/s²", display=f"a_B = {a_b:.3f} m/s²", role="primary")],
            steps=steps,
            verification=verification,
            used_equations=["a_B=a_A+a_B/A"],
        )


class CoriolisRelativeMotionSolver(BaseSolver):
    """Rotating-frame relative motion MVP.

    Uses the standard rotating-axis acceleration pieces:
    a_abs = a_O + alpha x r + omega x (omega x r) + 2 omega x v_rel + a_rel.
    For a radial slot, components become a_r=a_rel-rω² and a_θ=rα+2ωv_rel.
    """

    name = "coriolis_relative_motion"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "coriolis_relative_motion":
            return SolverMatch(self, 90, "회전 기준계 상대운동의 코리올리 항 2ωv_rel 포함")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        omega = _val(c, "omega", "thetadot")
        v_rel = _val(c, "vrel", "rdot")
        if omega is None or v_rel is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["코리올리 항 계산에는 ω와 상대속도 v_rel이 필요합니다."]))
        raw = (c.raw_text or "").lower().replace(" ", "")
        coriolis_only = "코리올리" in raw and not any(word in raw for word in ("전체가속도", "절대가속도", "가속도성분"))
        r = _val(c, "r", "R")
        alpha = _val(c, "alpha", "thetaddot")
        a_rel = _val(c, "arel", "rddot")
        a_c = 2 * omega * v_rel
        if not coriolis_only:
            missing = []
            if r is None:
                missing.append("위치 반지름 r")
            if alpha is None:
                missing.append("각가속도 alpha")
            if a_rel is None:
                missing.append("상대가속도 a_rel")
            if missing:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(passed=False, errors=missing),
                    unsupported_reason="전체 회전계 가속도에서는 빠진 항을 0으로 가정하지 않습니다.",
                )
        if not coriolis_only:
            a_radial = a_rel - r * omega**2
            a_transverse = r * alpha + a_c
            a_mag = math.hypot(a_radial, a_transverse)
            display = f"a_C = {a_c:.3f} m/s²; a_r = {a_radial:.3f} m/s², a_θ = {a_transverse:.3f} m/s², |a| = {a_mag:.3f} m/s²"
            numeric = a_mag
            symbolic = "a_r=a_rel-rω², a_θ=rα+2ωv_rel"
            answers = [
                AnswerItem(label="가속도 크기", symbol="a", numeric=round(a_mag, 6), unit="m/s²", display=f"|a| = {a_mag:.3f} m/s²", role="primary"),
                AnswerItem(label="코리올리 항", symbol="a_C", numeric=round(a_c, 6), unit="m/s²", display=f"a_C = {a_c:.3f} m/s²", role="component"),
                AnswerItem(label="반경 성분", symbol="a_r", numeric=round(a_radial, 6), unit="m/s²", display=f"a_r = {a_radial:.3f} m/s²", role="component"),
                AnswerItem(label="접선 성분", symbol="a_theta", numeric=round(a_transverse, 6), unit="m/s²", display=f"a_θ = {a_transverse:.3f} m/s²", role="component"),
            ]
        else:
            r = 0.0 if r is None else r
            alpha = 0.0 if alpha is None else alpha
            a_rel = 0.0 if a_rel is None else a_rel
            display = f"Coriolis 가속도 a_C = 2ωv_rel = {a_c:.3f} m/s²"
            numeric = a_c
            symbolic = "a_C = 2ωv_rel"
            answers = [AnswerItem(label="코리올리 가속도", symbol="a_C", numeric=round(a_c, 6), unit="m/s²", display=f"a_C = {a_c:.3f} m/s²", role="primary")]
        steps = [
            StepCard("회전 기준계 확인", "입자가 회전하는 막대/슬롯 안에서 상대적으로 움직이면 코리올리 항이 생깁니다."),
            StepCard("전체 가속도 구조", "회전 기준계의 절대가속도는 접선항, 법선항, 코리올리항, 상대가속도의 합입니다.", r"\vec a=\vec a_O+\vec\alpha\times\vec r+\vec\omega\times(\vec\omega\times\vec r)+2\vec\omega\times\vec v_{rel}+\vec a_{rel}"),
            StepCard("코리올리 항", "상대속도와 회전이 동시에 있을 때 2ωv_rel 크기의 항이 접선방향으로 나타납니다.", r"a_C=2\omega v_{rel}"),
            StepCard("계산", f"ω={omega:g} rad/s, v_rel={v_rel:g} m/s, r={r:g} m, α={alpha:g} rad/s², a_rel={a_rel:g} m/s²"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=[
                "v_rel=0이면 코리올리 항은 0입니다.",
                "ω=0이면 회전 기준계 항이 사라지고 상대가속도만 남습니다.",
                "방향은 오른손법칙 또는 e_r/e_θ 방향으로 별도 확인해야 합니다.",
            ],
        )
        attach_unit_check(verification, expected_unknown="acceleration", actual_unit="m/s²")
        return SolverResult(
            ok=True,
            answer=Answer(symbolic=symbolic, numeric=round(numeric, 6), unit="m/s²", display=display),
            answers=answers,
            steps=steps,
            verification=verification,
            used_equations=["a_C=2ωv_rel", "a_r=a_rel-rω²", "a_θ=rα+2ωv_rel"],
        )


class PlaneRigidBodyAccelerationSolver(BaseSolver):
    name = "plane_rigid_body_acceleration"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "plane_rigid_body_acceleration":
            return SolverMatch(self, 88, "평면강체 두 점의 가속도 관계 a_B=a_A+α×r-ω²r")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        r = _val(c, "r", "R")
        omega = _val(c, "omega")
        alpha = _val(c, "alpha")
        if r is None or omega is None or alpha is None:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["평면강체 가속도 계산에는 r, ω, α가 필요합니다."]))
        a_a = _val(c, "aA", default=0.0) or 0.0
        a_t = alpha * r
        a_n = omega**2 * r
        rel_mag = math.hypot(a_t, a_n)
        # MVP scalar magnitude: if a_A exists, combine magnitudes orthogonally as a conservative display assumption.
        total = rel_mag if abs(a_a) < 1e-12 else math.hypot(a_a, rel_mag)
        display = f"a_t = {a_t:.3f} m/s², a_n = {a_n:.3f} m/s², |a_B/A| = {rel_mag:.3f} m/s²"
        if abs(a_a) >= 1e-12:
            display += f"; 기본 합성 |a_B| ≈ {total:.3f} m/s²"
        steps = [
            StepCard("두 점 가속도 관계", "평면강체에서 B점 가속도는 A점 가속도에 회전 때문에 생기는 접선/법선 상대가속도를 더합니다."),
            StepCard("벡터식", "α×r은 접선 성분, ω×(ω×r)은 A쪽을 향하는 법선 성분입니다.", r"\vec a_B=\vec a_A+\vec\alpha\times\vec r_{B/A}+\vec\omega\times(\vec\omega\times\vec r_{B/A})"),
            StepCard("성분 크기", "접선 성분은 αr, 법선 성분은 ω²r입니다.", r"a_t=\alpha r,\quad a_n=\omega^2 r"),
            StepCard("계산", f"r={r:g} m, ω={omega:g} rad/s, α={alpha:g} rad/s² → a_t={a_t:.3f}, a_n={a_n:.3f}"),
        ]
        verification = VerificationReport(
            passed=True,
            warnings=["이번 solver는 크기 기본형입니다. 실제 문제의 방향각이 주어지면 x-y 성분 벡터합으로 확장해야 합니다."],
            checks=["ω=0이면 법선성분 ω²r은 0입니다.", "α=0이면 접선성분 αr은 0이고 등속회전의 구심성분만 남습니다."],
        )
        attach_unit_check(verification, expected_unknown="acceleration", actual_unit="m/s²")
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="a_B = a_A + α×r_B/A + ω×(ω×r_B/A)", numeric=round(total, 6), unit="m/s²", display=display),
            steps=steps,
            verification=verification,
            used_equations=["a_B=a_A+α×r+ω×(ω×r)", "a_t=αr", "a_n=ω²r"],
        )


class MassivePulleyAtwoodSolver(BaseSolver):
    name = "massive_pulley_atwood"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "massive_pulley_atwood":
            return SolverMatch(self, 89, "질량/관성이 있는 도르래: 등가질량 I/R² 포함")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        m1 = _val(c, "m1")
        m2 = _val(c, "m2")
        I = _val(c, "Ip", "I")
        R = _val(c, "Rp", "R")
        g = _val(c, "g", default=9.81) or 9.81
        if None in (m1, m2, I, R) or R == 0:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["질량 있는 도르래 문제에는 m1, m2, I, R이 필요합니다."]))
        denom = m1 + m2 + I / R**2
        a = (m2 - m1) * g / denom
        alpha = a / R
        T1 = m1 * (g + a)  # m1 upward positive when m2 moves downward positive
        T2 = m2 * (g - a)
        direction = "m2가 아래로" if a >= 0 else "m1이 아래로"
        steps = [
            StepCard("모델링", "질량 있는 도르래는 회전 관성 때문에 양쪽 장력이 같지 않습니다. 줄은 미끄러지지 않아 a=αR입니다."),
            StepCard("방정식", "두 물체의 병진식과 도르래 회전식을 함께 씁니다.", r"T_1-m_1g=m_1a,\quad m_2g-T_2=m_2a,\quad (T_2-T_1)R=I\alpha"),
            StepCard("정리", "도르래 관성은 I/R²라는 등가질량처럼 분모에 더해집니다.", r"a=\frac{(m_2-m_1)g}{m_1+m_2+I/R^2}"),
            StepCard("계산", f"m1={m1:g} kg, m2={m2:g} kg, I={I:g} kg·m², R={R:g} m → a={a:.3f} m/s²"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=["I=0이면 질량 없는 도르래 Atwood 식으로 돌아갑니다.", "I/R²가 커질수록 같은 질량차에서도 가속도는 작아집니다.", "T2-T1이 0이 아니어야 도르래가 각가속도를 가질 수 있습니다."],
        )
        attach_unit_check(verification, expected_unknown="acceleration", actual_unit="m/s²")
        display = f"a = {a:.3f} m/s² ({direction}); α = {alpha:.3f} rad/s²; T1 = {T1:.3f} N, T2 = {T2:.3f} N"
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="a=(m2-m1)g/(m1+m2+I/R²)", numeric=round(a, 6), unit="m/s²", display=display),
            steps=steps,
            verification=verification,
            used_equations=["a=αR", "(T2-T1)R=Iα", "a=(m2-m1)g/(m1+m2+I/R²)"],
            fbd=["m1g, T1", "m2g, T2", "도르래 회전식: (T2-T1)R=Iα"],
            coordinate_guide=["m2가 아래로 내려가는 방향을 +로 잡았습니다.", "a가 음수이면 실제 운동 방향은 반대입니다."],
        )


class RollingEnergyGeneralSolver(BaseSolver):
    name = "rolling_energy_general"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "rolling_energy_general":
            return SolverMatch(self, 87, "일반 관성모멘트 I를 사용하는 순수 구름 에너지")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        m = _val(c, "m")
        h = _val(c, "h")
        I = _val(c, "I")
        R = _val(c, "R", "r")
        g = _val(c, "g", default=9.81) or 9.81
        if None in (m, h, I, R) or R == 0:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["일반 순수 구름 에너지 계산에는 m, h, I, R이 필요합니다."]))
        denom = m + I / R**2
        v = math.sqrt(max(0.0, 2 * m * g * h / denom))
        omega = v / R
        steps = [
            StepCard("순수 구름 조건", "문제에 미끄러지지 않는다고 했으므로 v_G=ωR을 사용할 수 있습니다."),
            StepCard("에너지식", "위치에너지가 병진 운동에너지와 회전 운동에너지로 나뉩니다.", r"mgh=\frac12mv_G^2+\frac12I_G\omega^2"),
            StepCard("구속조건 대입", "ω=v_G/R을 넣으면 v에 대한 식 하나가 됩니다.", r"v_G=\sqrt{\frac{2mgh}{m+I_G/R^2}}"),
            StepCard("계산", f"m={m:g} kg, h={h:g} m, I={I:g} kg·m², R={R:g} m → v={v:.3f} m/s"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=["I가 0이면 질점이 높이 h만큼 떨어진 v=sqrt(2gh)에 가까워집니다.", "I/R²가 커질수록 같은 높이에서 병진속도 v는 작아집니다.", "미끄러짐이 있으면 v=ωR을 쓰면 안 됩니다."],
        )
        attach_unit_check(verification, expected_unknown="velocity", actual_unit="m/s")
        display = f"v_G = {v:.3f} m/s; ω = {omega:.3f} rad/s"
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="v_G=sqrt(2mgh/(m+I_G/R²))", numeric=round(v, 6), unit="m/s", display=display),
            steps=steps,
            verification=verification,
            used_equations=["mgh=1/2mv²+1/2Iω²", "v=ωR", "v=sqrt(2mgh/(m+I/R²))"],
        )
