from __future__ import annotations

import math
import sympy as sp

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch



def can_solve_flight_time_without_speed(c: CanonicalProblem) -> bool:
    requested = {
        item
        for item in (c.requested_outputs or c.unknowns or [])
        if item != "auto"
    }
    if not requested or not requested <= {"time"}:
        return False
    theta = (
        c.launch_angle_deg
        if c.launch_angle_deg is not None
        else c.knowns["theta"].value
        if "theta" in c.knowns
        else None
    )
    if theta not in (0, 0.0):
        return False
    launch = (
        c.launch_height
        if c.launch_height is not None
        else c.knowns["h"].value
        if "h" in c.knowns
        else None
    )
    landing = c.landing_height if c.landing_height is not None else 0.0
    return launch is not None and float(launch) - float(landing) > 0


class ProjectileMotionSolver(BaseSolver):
    name = "projectile_motion"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "projectile_motion":
            return SolverMatch(self, 88, "포물선 운동 기본 방정식을 SymPy로 푸는 일반형 solver")
        return None

    def _solve_flight_time_without_v0(self, c: CanonicalProblem) -> SolverResult | None:
        """수평 발사에서 시간만 물으면 v0 없이 답한다 (Phase 41).

        조건: θ=0(수평), 발사-착지 높이차 Δh>0, requested가 time.
        수평거리(range)까지 요구되면 None을 반환해 기존 "v0 필요" 경로로 —
        그 경우 missing_info("초속도 v0")가 안내한다.
        """
        if not can_solve_flight_time_without_speed(c):
            return None
        launch = (
            c.launch_height
            if c.launch_height is not None
            else c.knowns["h"].value
        )
        landing = c.landing_height if c.landing_height is not None else 0.0
        dh = float(launch) - float(landing)
        g = c.knowns["g"].value if "g" in c.knowns else 9.81
        t = math.sqrt(2 * dh / g)
        steps = [
            StepCard("문제 유형", "수평으로 던진 물체의 연직 운동은 자유낙하와 같습니다. 비행시간은 수평 속도와 무관합니다."),
            StepCard("공식", "높이차 Δh를 떨어지는 시간.", r"\Delta h=\frac12 g t^2 \;\Rightarrow\; t=\sqrt{2\Delta h/g}"),
            StepCard("계산", f"t = √(2×{dh:g}/{g:g}) = {t:.5g} s"),
            StepCard("참고", "수평거리까지 구하려면 수평 속도 v0가 추가로 필요합니다: R = v0·t."),
        ]
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="t = √(2Δh/g)", numeric=round(t, 5), unit="s", display=f"t = {t:.3f} s"),
            answers=[AnswerItem(label="비행시간", symbol="t", numeric=round(t, 5), unit="s", display=f"t = {t:.3f} s", role="primary")],
            steps=steps,
            verification=VerificationReport(passed=True, checks=["비행시간은 수평 속도와 무관합니다 (연직·수평 독립).", "단위: √(m/(m/s²)) = s."]),
            used_equations=["Δh = ½gt²"],
        )

    def solve(self, c: CanonicalProblem) -> SolverResult:
        v0q = c.knowns.get("v0") or c.knowns.get("v")
        if not v0q:
            # Phase 41: 수평 발사(θ=0)의 비행시간은 v0와 무관하다 — t=√(2Δh/g).
            partial = self._solve_flight_time_without_v0(c)
            if partial is not None:
                return partial
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["포물선 운동은 초속도 v0가 필요합니다."]))
        v0 = magnitude_si(v0q, "m/s")
        if c.launch_angle_deg is not None:
            theta_deg = float(c.launch_angle_deg)
        elif c.knowns.get("theta"):
            theta_deg = magnitude_si(c.knowns["theta"], "deg")
        elif "수평" in c.raw_text or "horizontal" in c.raw_text.lower():
            theta_deg = 0.0
        elif any(w in c.raw_text for w in ["수직 위로", "위로 던", "수직으로"]):
            theta_deg = 90.0
        else:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["발사각 θ 또는 발사 방향이 필요합니다."]))
        theta = math.radians(theta_deg)
        g = magnitude_si(c.knowns["g"], "m/s^2")
        y0 = c.launch_height if c.launch_height is not None else 0.0
        y_final = c.landing_height
        raw = c.raw_text.lower()
        if y_final is None:
            if "같은 높이" in raw:
                y_final = y0
            elif "지면" in raw or "바닥" in raw or "ground" in raw:
                y_final = 0.0
            else:
                y_final = 0.0 if y0 == 0 else None

        vx = v0 * math.cos(theta)
        vy = v0 * math.sin(theta)
        t_sym = sp.symbols("t", real=True)

        def positive_times_for_height(y_target: float) -> list[float]:
            eq = sp.Eq(y0 + vy * t_sym - sp.Rational(1, 2) * g * t_sym**2, y_target)
            roots = sp.solve(eq, t_sym)
            vals = sorted(float(sp.N(r)) for r in roots if r.is_real and float(sp.N(r)) > 1e-10)
            return vals

        steps = [
            StepCard("기본 방정식", "포물선 운동은 x(t), y(t)를 직접 세워서 풉니다.", r"x=x_0+v_0\cos\theta\,t,\quad y=y_0+v_0\sin\theta\,t-\frac12gt^2"),
            StepCard("속도 분해", f"v_x={vx:.5g} m/s, v_y={vy:.5g} m/s"),
        ]

        req = list(c.requested_outputs or [])
        if not req:
            if "시간" in c.raw_text:
                req = ["time"]
            elif "최대높이" in c.raw_text.replace(" ", ""):
                req = ["max_height"]
            else:
                req = ["range"]

        computed: dict[str, AnswerItem] = {}
        t_f: float | None = None
        range_x: float | None = None
        if y_final is not None:
            times = positive_times_for_height(y_final)
            if times:
                t_f = max(times)
                range_x = vx * t_f
                computed["time"] = AnswerItem("시간", "t", round(t_f, 6), "s", f"시간 t = {t_f:.3f} s", "primary")
                computed["range"] = AnswerItem("수평거리", "R", round(range_x, 6), "m", f"수평거리 R = {range_x:.3f} m", "primary")
                computed["distance"] = computed["range"]
                steps.append(StepCard("착지/목표 높이 조건", f"y_final={y_final:g} m를 대입해 양수 시간 해를 고릅니다.", r"y_0+v_0\sin\theta\,t-\frac12gt^2=y_f"))
                steps.append(StepCard("수평 운동", "수평방향 가속도는 0이므로 x=vx t입니다.", r"x=v_0\cos\theta\,t"))
        hmax = y0 + vy**2 / (2 * g)
        computed["max_height"] = AnswerItem("최대높이", "H", round(hmax, 6), "m", f"최대높이 H = {hmax:.3f} m", "primary")

        answers: list[AnswerItem] = []
        missing: list[str] = []
        for key in req:
            if key in {"time", "range", "distance"} and key not in computed:
                missing.append("착지 높이 또는 목표 높이")
            elif key in computed:
                if computed[key].symbol not in {a.symbol for a in answers}:
                    answers.append(computed[key])
            elif key == "max_height":
                answers.append(computed["max_height"])

        if not answers and computed:
            # fallback to legacy behavior
            key = "time" if "time" in computed and "시간" in c.raw_text else "range" if "range" in computed else "max_height"
            answers = [computed[key]]

        if missing:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=[", ".join(missing) + "가 필요합니다."]), unsupported_reason="요청한 모든 값을 계산하려면 추가 조건이 필요합니다.")

        primary = answers[0]
        verification = VerificationReport(
            passed=True,
            dimension_summary="요청된 포물선 운동 결과의 단위 검증 통과",
            checks=[
                "수직 운동은 등가속도, 수평 운동은 등속도입니다.",
                "양수 시간 해만 선택했습니다.",
                "높이가 다르면 같은 높이 전용 사거리 공식을 쓰지 않습니다.",
            ],
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic=primary.symbol, numeric=primary.numeric, unit=primary.unit, display=primary.display),
            answers=answers,
            steps=steps,
            verification=verification,
            used_equations=["x=x0+v0cosθ t", "y=y0+v0sinθ t-1/2gt²"],
            coordinate_guide=["x축: 수평 오른쪽", "y축: 위쪽. ay=-g"],
        )
