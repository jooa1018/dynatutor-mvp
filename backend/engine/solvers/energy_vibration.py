from __future__ import annotations

import math
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.units.dimensions import attach_unit_check, unit_hint_for_equation
from engine.equation_generators.energy_momentum import solve_energy_momentum_system


class SpringMassVibrationSolver(BaseSolver):
    name = "spring_mass_vibration"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "spring_mass_vibration":
            return SolverMatch(self, 90, "스프링 상수 k와 질량 m이 있는 1자유도 진동 문제")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        kq, mq = c.knowns.get("k"), c.knowns.get("m")
        if not kq or not mq:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["진동 계산에는 스프링 상수 k와 질량 m이 필요합니다."]))
        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=generated.errors), unsupported_reason="모델 기반 진동 방정식 생성/풀이에 실패했습니다.")
        k, m = kq.value, mq.value
        omega = float(generated.solution["omega_n"])
        period = float(generated.solution["T"])
        freq = float(generated.solution["f"])
        # Unknown selection: if period/frequency asked, report that; otherwise natural angular frequency.
        if "period" in c.unknowns:
            ans = Answer(symbolic="T = 2π√(m/k)", numeric=round(period, 5), unit="s", display=f"T = {period:.3f} s")
            expected = "period"
        elif "angular_frequency" in c.unknowns or "frequency" not in c.unknowns:
            ans = Answer(symbolic="ω_n = √(k/m)", numeric=round(omega, 5), unit="rad/s", display=f"ω_n = {omega:.3f} rad/s")
            expected = "angular_frequency"
        else:
            ans = Answer(symbolic="f = (1/2π)√(k/m)", numeric=round(freq, 5), unit="Hz", display=f"f = {freq:.3f} Hz")
            expected = "frequency"

        steps = [
            StepCard("모델링", "질량 m이 스프링 k에 연결된 1자유도 자유진동으로 봅니다. 감쇠와 외력은 없는 기본 모델입니다."),
            StepCard("운동방정식", "Energy/Momentum generator가 1자유도 스프링-질량 운동방정식을 생성합니다. 평형 위치 기준 변위 x를 잡으면 복원력은 -kx입니다.", r"m\ddot{x}+kx=0"),
            StepCard("고유각진동수", "위 식을 표준형 x¨+ωₙ²x=0과 비교합니다.", r"\omega_n=\sqrt{k/m}"),
            StepCard("주기와 진동수", "필요하면 T=2π/ωₙ, f=1/T로 바꿉니다.", r"T=2\pi/\omega_n,\quad f=1/T"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=[
                unit_hint_for_equation("vibration"),
                "스프링이 딱딱해져 k가 커지면 더 빨리 진동하므로 ωₙ이 커집니다.",
                "질량 m이 커지면 더 천천히 진동하므로 ωₙ이 작아집니다.",
            ],
        )
        attach_unit_check(verification, expected_unknown=expected, actual_unit=ans.unit)
        symbol = {"period": "T", "frequency": "f", "angular_frequency": "omega_n"}[expected]
        label = {"period": "주기", "frequency": "진동수", "angular_frequency": "고유각진동수"}[expected]
        return SolverResult(
            ok=True,
            answer=ans,
            answers=[
                AnswerItem(
                    label=label,
                    symbol=symbol,
                    numeric=ans.numeric,
                    unit=ans.unit,
                    display=ans.display or "",
                    role="primary",
                )
            ],
            steps=steps,
            verification=verification,
            used_equations=["m x¨ + kx = 0", "ω_n = √(k/m)"],
        )


class SpringEnergySpeedSolver(BaseSolver):
    name = "spring_energy_speed"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "spring_energy":
            return SolverMatch(self, 88, "스프링 탄성에너지가 운동에너지로 바뀌는 문제")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        kq, xq, mq = c.knowns.get("k"), c.knowns.get("x") or c.knowns.get("A"), c.knowns.get("m")
        # Phase 39: "저장된/탄성 에너지는?" 직접 질문 — 질량 없이 E = ½kx².
        if kq and xq and ("elastic_energy" in (c.requested_outputs or []) or (not mq and "에너지" in c.raw_text)):
            k, x = kq.value, xq.value
            E = 0.5 * k * x * x
            steps = [
                StepCard("문제 유형", "용수철을 x만큼 늘이거나 압축하면 탄성 퍼텐셜 에너지가 저장됩니다."),
                StepCard("공식", "저장 에너지는 변형량의 제곱에 비례합니다.", r"E=\frac12 kx^2"),
                StepCard("계산", f"E = ½ × {k:g} × ({x:g})² = {E:.5g} J"),
            ]
            verification = VerificationReport(passed=True, checks=[
                "단위: (N/m)×m² = N·m = J.",
                "x의 부호와 무관하게 (제곱이므로) 에너지는 0 이상입니다.",
            ])
            return SolverResult(
                ok=True,
                answer=Answer(symbolic="E = ½kx²", numeric=round(E, 6), unit="J", display=f"E = {E:.3f} J"),
                answers=[AnswerItem(label="탄성 퍼텐셜 에너지", symbol="E", numeric=round(E, 6), unit="J", display=f"E = {E:.3f} J", role="primary")],
                steps=steps,
                verification=verification,
                used_equations=["E = ½kx²"],
            )
        if not kq or not xq or not mq:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["스프링 에너지 속도 계산에는 k, 압축/변위 x, 질량 m이 필요합니다."]))
        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=generated.errors), unsupported_reason="모델 기반 스프링 에너지 방정식 생성/풀이에 실패했습니다.")
        k, x, m = kq.value, xq.value, mq.value
        v = float(generated.solution["v"])
        steps = [
            StepCard("에너지 관점", "마찰이 없고 수평 스프링이라면 스프링 탄성에너지가 물체의 운동에너지로 바뀝니다."),
            StepCard("에너지 보존", "Energy/Momentum generator가 스프링 에너지와 운동에너지를 같게 두는 식을 생성합니다.", "\frac12kx^2=\frac12mv^2"),
            StepCard("속도 정리", "양변의 1/2를 지우고 v에 대해 풀면 됩니다.", r"v=x\sqrt{k/m}"),
            StepCard("계산", f"v = {x:g} × √({k:g}/{m:g}) = {v:.5g} m/s"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=[
                unit_hint_for_equation("spring_energy"),
                "x가 0이면 저장된 스프링 에너지도 0이므로 v=0입니다.",
                "k가 클수록 같은 압축량에서 저장 에너지가 커져 속도가 증가합니다.",
            ],
        )
        attach_unit_check(verification, expected_unknown="velocity", actual_unit="m/s")
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="v = x√(k/m)", numeric=round(v, 5), unit="m/s", display=f"v = {v:.3f} m/s"),
            steps=steps,
            verification=verification,
            used_equations=["1/2 kx² = 1/2 mv²", "v = x√(k/m)"],
        )


class WorkEnergySpeedSolver(BaseSolver):
    name = "work_energy_speed"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "work_energy_speed":
            return SolverMatch(self, 82, "일-운동에너지 정리로 속도 변화 계산")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        mq = c.knowns.get("m")
        Wq = c.knowns.get("W")
        Fq, sq = c.knowns.get("F"), c.knowns.get("s")
        v0q = c.knowns.get("v0") or c.knowns.get("v")
        starts_from_rest = any(
            phrase in (c.raw_text or "").lower()
            for phrase in (
                "정지 상태에서",
            "처음에 정지한",
            "정지한 물체",
                "정지 상태로부터",
                "정지에서",
                "처음에는 정지",
                "초기에는 정지",
                "가만히 있다가",
                "starts from rest",
                "initially at rest",
            )
        )
        if not mq or not (Wq or (Fq and sq)):
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["일-에너지 속도 계산에는 질량 m과 일 W 또는 힘 F, 거리 s가 필요합니다."]))
        if not v0q and not starts_from_rest:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["초기속도 v_i 또는 정지 상태에서 출발한다는 조건이 필요합니다."],
                ),
                unsupported_reason="초기 운동 상태를 명시해 주세요.",
            )
        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=generated.errors), unsupported_reason="모델 기반 일-에너지 방정식 생성/풀이에 실패했습니다.")
        m = mq.value
        W = float(generated.solution["W"])
        work_text = f"W_net={W:.5g} J"
        v0 = float(generated.solution["v_i"])
        vf = float(generated.solution["v_f"])
        steps = [
            StepCard("일-운동에너지 정리", "Energy/Momentum generator가 W_net=ΔK를 생성합니다. 알짜일은 운동에너지 변화량과 같습니다.", r"W_{net}=\Delta K"),
            StepCard("식 세우기", "문제에 주어진 초기속도(또는 명시된 정지 출발 조건)를 사용합니다.", "W=\frac12m v_f^2-\frac12m v_i^2"),
            StepCard("계산", f"{work_text}, v_i={v0:g} m/s 이므로 v_f = {vf:.5g} m/s"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=[
                "양의 알짜일이면 물체의 속도가 증가합니다.",
                "W=0이면 v_f=v_i가 되어야 합니다.",
                unit_hint_for_equation("work"),
            ],
        )
        attach_unit_check(verification, expected_unknown="velocity", actual_unit="m/s")
        return SolverResult(ok=True, answer=Answer(symbolic="v_f = √(v_i² + 2W/m)", numeric=round(vf, 5), unit="m/s", display=f"v_f = {vf:.3f} m/s"), steps=steps, verification=verification, used_equations=["W=ΔK", "v_f = √(v_i² + 2W/m)"])


class HorizontalFrictionForceSolver(BaseSolver):
    """수평면에서 미끄러지는 물체의 운동마찰력 f = μN = μmg (Phase 39).

    "μ=0.2, m=2kg, 마찰력은?" 같은 직접 질문 유형. 수직항력도 함께 제시한다.
    """

    name = "horizontal_friction_force"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "horizontal_friction_force":
            return SolverMatch(self, 80, "수평면 운동마찰력 f = μmg")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        muq = c.knowns.get("mu") or c.knowns.get("mu_k")
        # 단일 물체 문맥에서 m₁ 표기로 들어온 질량도 허용
        mq = c.knowns.get("m") or (c.knowns.get("m1") if "m2" not in c.knowns else None)
        gq = c.knowns.get("g")
        if not muq or not mq or not gq:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["마찰력 계산에는 마찰계수 μ와 질량 m이 필요합니다."]))
        mu, m, g = muq.value, mq.value, gq.value
        N = m * g
        f = mu * N
        steps = [
            StepCard("문제 유형", "수평면에서는 수직항력이 무게와 같습니다: N = mg."),
            StepCard("마찰력 공식", "운동마찰력은 수직항력에 비례합니다.", r"f=\mu N=\mu m g"),
            StepCard("계산", f"N = {m:g}×{g:g} = {N:.5g} N,  f = {mu:g}×{N:.5g} = {f:.5g} N"),
        ]
        verification = VerificationReport(passed=True, checks=[
            "단위: μ(무차원)×kg×m/s² = N.",
            "μ=0이면 마찰력도 0입니다.",
            "경사면이라면 N=mg·cosθ로 달라지므로 이 공식은 수평면 전용입니다.",
        ])
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="f = μmg", numeric=round(f, 6), unit="N", display=f"f = {f:.3f} N"),
            answers=[
                AnswerItem(label="운동마찰력", symbol="f", numeric=round(f, 6), unit="N", display=f"f = {f:.3f} N", role="primary"),
                AnswerItem(label="수직항력", symbol="N", numeric=round(N, 6), unit="N", display=f"N = {N:.3f} N", role="component"),
            ],
            steps=steps,
            verification=verification,
            used_equations=["N = mg", "f = μN"],
        )
