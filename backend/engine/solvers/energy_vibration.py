from __future__ import annotations

import math
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.physics_core.units import magnitude_si
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
        requested = list(dict.fromkeys(c.requested_outputs or c.unknowns or []))
        targets = [
            item
            for item in requested
            if item in {"angular_frequency", "frequency", "period"}
        ] or ["angular_frequency"]
        answer_specs = {
            "period": (
                Answer(symbolic="T = 2π√(m/k)", numeric=round(period, 5), unit="s", display=f"T = {period:.3f} s"),
                "T",
                "주기",
            ),
            "frequency": (
                Answer(symbolic="f = (1/2π)√(k/m)", numeric=round(freq, 5), unit="Hz", display=f"f = {freq:.3f} Hz"),
                "f",
                "진동수",
            ),
            "angular_frequency": (
                Answer(symbolic="ω_n = √(k/m)", numeric=round(omega, 5), unit="rad/s", display=f"ω_n = {omega:.3f} rad/s"),
                "omega_n",
                "고유각진동수",
            ),
        }
        expected = targets[0]
        ans = answer_specs[expected][0]
        answer_items = [
            AnswerItem(
                label=answer_specs[target][2],
                symbol=answer_specs[target][1],
                numeric=answer_specs[target][0].numeric,
                unit=answer_specs[target][0].unit,
                display=answer_specs[target][0].display or "",
                role="primary",
            )
            for target in targets
        ]

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
        return SolverResult(
            ok=True,
            answer=ans,
            answers=answer_items,
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
        kq = c.knowns.get("k")
        xq = c.knowns.get("x") or c.knowns.get("A")
        mq = c.knowns.get("m")
        requested = set(c.requested_outputs or c.unknowns or [])
        wants_energy = "elastic_energy" in requested or (
            not mq and "에너지" in (c.raw_text or "")
        )
        wants_speed = bool(
            requested.intersection({"final_velocity", "velocity", "speed"})
        ) or not wants_energy
        energy_item = None
        energy_value = None

        if kq and xq and wants_energy:
            k_si = magnitude_si(kq, "N/m")
            x_si = magnitude_si(xq, "m")
            energy_value = 0.5 * k_si * x_si * x_si
            energy_item = AnswerItem(
                label="탄성 퍼텐셜 에너지",
                symbol="E",
                numeric=round(energy_value, 6),
                unit="J",
                display=f"E = {energy_value:.3f} J",
                role="primary",
            )
            if not wants_speed:
                return SolverResult(
                    ok=True,
                    answer=Answer(
                        symbolic="E = ½kx²",
                        numeric=round(energy_value, 6),
                        unit="J",
                        display=f"E = {energy_value:.3f} J",
                    ),
                    answers=[energy_item],
                    steps=[
                        StepCard("문제 유형", "용수철을 x만큼 늘이거나 압축하면 탄성 퍼텐셜 에너지가 저장됩니다."),
                        StepCard("공식", "저장 에너지는 변형량의 제곱에 비례합니다.", r"E=\frac12 kx^2"),
                        StepCard("계산", f"E = ½ × {k_si:g} × ({x_si:g})² = {energy_value:.5g} J"),
                    ],
                    verification=VerificationReport(
                        passed=True,
                        checks=[
                            "단위: (N/m)×m² = N·m = J.",
                            "x의 부호와 무관하게 에너지는 0 이상입니다.",
                        ],
                    ),
                    used_equations=["E = ½kx²"],
                )

        if not kq or not xq or not mq:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["스프링 속도 계산에는 k, 압축/변위 x, 질량 m이 필요합니다."],
                ),
            )
        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(
                ok=False,
                verification=VerificationReport(passed=False, errors=generated.errors),
                unsupported_reason="모델 기반 스프링 에너지 방정식 생성/풀이에 실패했습니다.",
            )
        k_si = magnitude_si(kq, "N/m")
        x_si = magnitude_si(xq, "m")
        m_si = magnitude_si(mq, "kg")
        v = float(generated.solution["v"])
        velocity_item = AnswerItem(
            label="최종속도",
            symbol="v",
            numeric=round(v, 5),
            unit="m/s",
            display=f"v = {v:.3f} m/s",
            role="primary",
        )
        answers = [velocity_item]
        if energy_item is not None:
            answers.append(energy_item)
        steps = [
            StepCard("에너지 관점", "마찰이 없고 수평 스프링이라면 스프링 탄성에너지가 물체의 운동에너지로 바뀝니다."),
            StepCard("에너지 보존", "스프링 에너지와 운동에너지를 같게 둡니다.", r"\frac12kx^2=\frac12mv^2"),
            StepCard("속력 정리", "에너지식은 방향이 아닌 속력 크기를 정하므로 |x|를 사용합니다.", r"|v|=|x|\sqrt{k/m}"),
            StepCard("계산", f"|v| = |{x_si:g}| × √({k_si:g}/{m_si:g}) = {v:.5g} m/s"),
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
            answer=Answer(
                symbolic="|v| = |x|√(k/m)",
                numeric=round(v, 5),
                unit="m/s",
                display=f"v = {v:.3f} m/s",
            ),
            answers=answers,
            steps=steps,
            verification=verification,
            used_equations=["1/2 kx² = 1/2 mv²", "|v| = |x|√(k/m)"],
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
                "정지 상태의",
                "정지 상태인",
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
    """Resolve kinetic friction, actual static friction, and its limiting value."""

    name = "horizontal_friction_force"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "horizontal_friction_force":
            return SolverMatch(self, 80, "수평면의 실제 마찰력과 최대 정지마찰력을 구분")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        raw = (c.raw_text or "").lower()
        friction_type = c.friction_type
        muq = (
            c.knowns.get("mu_s")
            if friction_type == "static"
            else c.knowns.get("mu_k")
            if friction_type == "kinetic"
            else c.knowns.get("mu")
            or c.knowns.get("mu_k")
            or c.knowns.get("mu_s")
        )
        mq = c.knowns.get("m") or (
            c.knowns.get("m1") if "m2" not in c.knowns else None
        )
        gq = c.knowns.get("g")
        if muq is None or mq is None:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["마찰력 계산에는 해당 상태의 마찰계수와 질량 m이 필요합니다."],
                ),
            )

        mu = float(muq.value)
        mass = magnitude_si(mq, "kg")
        gravity = magnitude_si(gq, "m/s^2") if gq is not None else 9.81
        if mu < 0 or mass <= 0 or gravity <= 0:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["마찰계수는 0 이상, 질량과 중력가속도는 0보다 커야 합니다."],
                ),
                unsupported_reason="마찰 문제 입력값의 물리적 범위를 확인해 주세요.",
            )

        normal = mass * gravity
        if friction_type == "static":
            max_static = mu * normal
            asks_maximum = any(
                phrase in raw
                for phrase in (
                    "최대정지마찰",
                    "최대 정지마찰",
                    "정지마찰력의 최대",
                    "maximum static friction",
                )
            )
            applied_q = c.knowns.get("F")
            explicitly_unloaded = any(
                phrase in raw
                for phrase in (
                    "그냥 정지",
                    "가만히",
                    "수평 외력이 없",
                    "외력이 없",
                    "힘이 작용하지 않",
                    "no horizontal force",
                )
            )

            if asks_maximum:
                friction = max_static
                label = "최대 정지마찰력"
                symbol = "f_s,max"
                explanation = "최대 정지마찰력은 정지 상태가 버틸 수 있는 한계값입니다."
            elif applied_q is not None:
                applied = abs(magnitude_si(applied_q, "N"))
                if applied > max_static + 1e-9:
                    return SolverResult(
                        ok=False,
                        verification=VerificationReport(
                            passed=False,
                            errors=[
                                f"필요한 정지마찰력 {applied:.6g} N이 한계 {max_static:.6g} N을 넘습니다."
                            ],
                        ),
                        unsupported_reason="물체가 움직인 뒤의 답에는 운동마찰계수 μ_k가 필요합니다.",
                    )
                friction = applied
                label = "실제 정지마찰력"
                symbol = "f_s"
                explanation = "정지 중 실제 마찰력은 필요한 수평 외력만큼만 생깁니다."
            elif explicitly_unloaded:
                friction = 0.0
                label = "실제 정지마찰력"
                symbol = "f_s"
                explanation = "수평 외력이 없으므로 정지를 유지하는 데 필요한 마찰력은 0입니다."
            else:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=[
                            "실제 정지마찰력을 구하려면 수평 외력 또는 외력이 없다는 조건이 필요합니다."
                        ],
                    ),
                    unsupported_reason="실제 정지마찰력인지 최대값인지, 수평 외력이 얼마인지 알려 주세요.",
                )

            answers = [
                AnswerItem(
                    label=label,
                    symbol=symbol,
                    numeric=round(friction, 6),
                    unit="N",
                    display=f"{symbol} = {friction:.3f} N",
                    role="primary",
                )
            ]
            if not asks_maximum:
                answers.append(
                    AnswerItem(
                        label="최대 정지마찰력",
                        symbol="f_s,max",
                        numeric=round(max_static, 6),
                        unit="N",
                        display=f"f_s,max = {max_static:.3f} N",
                        role="component",
                    )
                )
            return SolverResult(
                ok=True,
                answer=Answer(
                    symbolic="|f_s| ≤ μ_s N",
                    numeric=round(friction, 6),
                    unit="N",
                    display=f"{symbol} = {friction:.3f} N",
                ),
                answers=answers,
                steps=[
                    StepCard("수직항력", "수평면에서 N=mg입니다.", r"N=mg"),
                    StepCard(
                        "정지마찰 구간",
                        explanation,
                        r"|f_s|\le f_{s,max}=\mu_sN",
                    ),
                    StepCard(
                        "계산",
                        f"실제값={friction:.5g} N, 한계값={max_static:.5g} N",
                    ),
                ],
                verification=VerificationReport(
                    passed=True,
                    checks=[
                        f"|f_s|={abs(friction):.6g} N ≤ f_s,max={max_static:.6g} N",
                        "실제 정지마찰력과 최대 정지마찰력을 구분했습니다.",
                    ],
                ),
                used_equations=["|f_s| ≤ μ_s N", "N=mg"],
            )

        moving = friction_type == "kinetic" or any(
            phrase in raw
            for phrase in (
                "운동마찰",
                "미끄러",
                "운동 중",
                "움직이는",
                "kinetic friction",
            )
        )
        if not moving:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["마찰이 정지마찰인지 운동마찰인지 구분해야 합니다."],
                ),
                unsupported_reason="물체가 정지해 있는지 미끄러지고 있는지 알려 주세요.",
            )

        friction = mu * normal
        steps = [
            StepCard("수직항력", "수평면에서는 수직항력이 무게와 같습니다.", r"N=mg"),
            StepCard("운동마찰력", "미끄러지는 동안 운동마찰력 크기는 μ_kN입니다.", r"f_k=\mu_kN"),
            StepCard(
                "계산",
                f"N={normal:.5g} N, f_k={mu:g}×{normal:.5g}={friction:.5g} N",
            ),
        ]
        return SolverResult(
            ok=True,
            answer=Answer(
                symbolic="f_k = μ_kmg",
                numeric=round(friction, 6),
                unit="N",
                display=f"f_k = {friction:.3f} N",
            ),
            answers=[
                AnswerItem(
                    label="운동마찰력",
                    symbol="f_k",
                    numeric=round(friction, 6),
                    unit="N",
                    display=f"f_k = {friction:.3f} N",
                    role="primary",
                ),
                AnswerItem(
                    label="수직항력",
                    symbol="N",
                    numeric=round(normal, 6),
                    unit="N",
                    display=f"N = {normal:.3f} N",
                    role="component",
                ),
            ],
            steps=steps,
            verification=VerificationReport(
                passed=True,
                checks=[
                    "단위: μ_k(무차원)×kg×m/s² = N.",
                    "이 식은 수평면에서 미끄러지는 상태에만 적용됩니다.",
                ],
            ),
            used_equations=["N=mg", "f_k=μ_kN"],
        )
