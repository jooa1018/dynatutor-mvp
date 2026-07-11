import math
from engine.physics_core.initial_conditions import explicitly_starts_from_angular_rest
from engine.physics_core.units import magnitude_si
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.solvers.base import BaseSolver, SolverMatch
from engine.equation_generators.energy_momentum import solve_energy_momentum_system



class ConstantForceWorkSolver(BaseSolver):
    name = "constant_force_work"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "constant_force_work":
            return SolverMatch(self, 76, "일 = 힘과 변위의 내적 W=Fs cosθ")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        from engine.physics_core.direction_parser import infer_angle_between_force_and_displacement
        from engine.physics_core.units import magnitude_si, Q_
        Fq, sq = c.knowns.get("F"), c.knowns.get("s")
        if not Fq or not sq:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["힘 F와 이동거리 s가 필요합니다."]))
        angle = infer_angle_between_force_and_displacement(c.raw_text)
        if angle is None and ("force" in c.raw_text.lower() and "distance" in c.raw_text.lower()):
            angle = 0.0
        if angle is None and "theta" in c.knowns and c.knowns["theta"].value is not None:
            # 추출기('힘 방향으로 이동'→θ=0) 또는 clarification(set_known theta)이 채운 각도
            angle = float(c.knowns["theta"].value)
        if angle is None:
            return SolverResult(
                ok=False,
                verification=VerificationReport(passed=False, errors=["strict mode: 힘과 변위 사이 방향 또는 각도가 필요합니다."]),
                unsupported_reason="예: 같은 방향/반대 방향/수직/60도 중 하나를 알려주세요.",
            )
        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=generated.errors), unsupported_reason="모델 기반 일 방정식 생성/풀이에 실패했습니다.")
        F, s = magnitude_si(Fq, "N"), magnitude_si(sq, "m")
        W = float(generated.solution["W"])
        angle = float(generated.solution["theta_deg"])
        steps = [
            StepCard("일의 정의", "Energy/Momentum generator가 힘과 변위의 내적식을 생성합니다. 힘의 크기만 곱하면 안 되고 방향이 필요합니다.", r"W=\vec F\cdot \vec s=Fs\cos\theta"),
            StepCard("방향 해석", f"문장에서 힘과 변위 사이 각도를 {angle:g}°로 해석했습니다."),
            StepCard("계산", f"W = {F:g} × {s:g} × cos({angle:g}°) = {W:.5g} J"),
        ]
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="W = F s cosθ", numeric=round(W, 6), unit="J", display=f"W = {W:.3f} J"),
            steps=steps,
            verification=VerificationReport(passed=True, dimension_summary="N·m = J 차원 검증 통과", checks=["힘이 이동방향과 수직이면 cos90°=0이라 일은 0입니다.", "마찰력/저항력처럼 이동 반대방향이면 일은 음수입니다."]),
            used_equations=["W=Fs cosθ"],
        )


class FixedAxisRotationSolver(BaseSolver):
    name = "fixed_axis_rotation"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "fixed_axis_rotation":
            return SolverMatch(self, 76, "고정축 회전: ΣM = Iα")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        tauq, Iq = c.knowns.get("tau"), c.knowns.get("I")
        if not tauq or not Iq:
            # Phase 39: τ·I가 없어도 풀리는 회전 kinematics 두 갈래.
            kin = self._solve_rotational_kinematics(c)
            if kin is not None:
                return kin
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=["토크 τ와 관성모멘트 I가 필요합니다."]))
        alpha = tauq.value / Iq.value
        steps = [
            StepCard("문제 유형", "고정축 주위 회전에서는 병진운동의 F=ma에 대응해서 회전방정식 ΣM=Iα를 씁니다."),
            StepCard("회전방정식", "축에 대한 알짜토크가 관성모멘트×각가속도입니다.", r"\sum M_O=I_O\alpha"),
            StepCard("계산", f"α = τ/I = {tauq.value:g}/{Iq.value:g} = {alpha:.5g} rad/s²"),
        ]
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="α = τ/I", numeric=round(alpha, 5), unit="rad/s²", display=f"α = {alpha:.3f} rad/s²"),
            steps=steps,
            verification=VerificationReport(passed=True, checks=["같은 토크에서 관성모멘트가 커지면 각가속도는 작아집니다.", "단위 (N·m)/(kg·m²)=1/s²이며 rad/s²로 씁니다."]),
            used_equations=["ΣM=Iα"],
            coordinate_guide=["회전축을 먼저 정하고, 그 축에 대한 토크 부호를 통일합니다."],
        )

    def _solve_rotational_kinematics(self, c: CanonicalProblem) -> SolverResult | None:
        """τ·I 없이도 답이 정해지는 회전 kinematics.

        (a) α와 t가 주어지고 각속도를 물으면 ω = ω₀ + αt (ω₀ 기본 0).
        (b) ω와 반지름이 주어지고 점의 속력을 물으면 v = ωr.
        """
        knowns = c.knowns
        asks_omega = "angular_velocity" in (c.requested_outputs or []) or "각속도" in c.raw_text
        asks_speed = any(w in c.raw_text for w in ["속력", "속도는", "speed"])
        alphaq, tq = knowns.get("alpha"), knowns.get("t")
        if alphaq and tq and asks_omega:
            omega0q = knowns.get("omega0") or knowns.get("omega")
            if omega0q is None and not explicitly_starts_from_angular_rest(c):
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=[
                            "각속도 계산에는 초기 각속도 ω₀ 또는 명시적인 회전 정지 조건이 필요합니다."
                        ],
                    ),
                    unsupported_reason="초기 각속도 또는 정지 출발 조건을 알려 주세요.",
                )
            omega0 = (
                magnitude_si(omega0q, "rad/s")
                if omega0q is not None
                else 0.0
            )
            alpha_value = magnitude_si(alphaq, "rad/s^2")
            time_value = magnitude_si(tq, "s")
            omega_f = omega0 + alpha_value * time_value
            steps = [
                StepCard("문제 유형", "토크 없이 각가속도와 시간이 주어졌으므로 회전 kinematics(등각가속도)입니다. 직선운동의 v=v₀+at에 대응합니다."),
                StepCard("공식", "각속도는 초기 각속도에 각가속도×시간을 더합니다.", r"\omega=\omega_0+\alpha t"),
                StepCard("계산", f"ω = {omega0:g} + {alpha_value:g}×{time_value:g} = {omega_f:.5g} rad/s"),
            ]
            return SolverResult(
                ok=True,
                answer=Answer(symbolic="ω = ω₀ + αt", numeric=round(omega_f, 5), unit="rad/s", display=f"ω = {omega_f:.3f} rad/s"),
                answers=[AnswerItem(label="최종 각속도", symbol="omega_f", numeric=round(omega_f, 5), unit="rad/s", display=f"ω = {omega_f:.3f} rad/s", role="primary")],
                steps=steps,
                verification=VerificationReport(passed=True, checks=["단위: rad/s² × s = rad/s.", "α=0이면 각속도가 변하지 않습니다."]),
                used_equations=["ω = ω₀ + αt"],
            )
        omegaq = knowns.get("omega")
        rq = knowns.get("r") or knowns.get("R")
        if omegaq and rq and asks_speed and not alphaq:
            omega_value = magnitude_si(omegaq, "rad/s")
            radius = magnitude_si(rq, "m")
            if radius < 0:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=["회전 반지름 r은 0 이상이어야 합니다."],
                    ),
                )
            v = abs(omega_value) * radius
            steps = [
                StepCard("문제 유형", "고정축 회전체 위 한 점의 속력은 각속도와 회전 반지름의 곱입니다."),
                StepCard("공식", "점의 선속도 크기.", r"v=\omega r"),
                StepCard("계산", f"v = |{omega_value:g}| × {radius:g} = {v:.5g} m/s"),
            ]
            return SolverResult(
                ok=True,
                answer=Answer(symbolic="v_t = ωr", numeric=round(v, 5), unit="m/s", display=f"v_t = {v:.3f} m/s"),
                answers=[AnswerItem(label="점의 접선 속력", symbol="v_t", numeric=round(v, 5), unit="m/s", display=f"v_t = {v:.3f} m/s", role="primary")],
                steps=steps,
                verification=VerificationReport(passed=True, checks=["단위: rad/s × m = m/s (rad는 무차원).", "축(r=0)에서는 속력이 0입니다."]),
                used_equations=["v = ωr"],
            )
        return None


class ImpulseMomentumSolver(BaseSolver):
    name = "impulse_momentum"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "impulse_momentum":
            return SolverMatch(self, 66, "충격량-운동량: J = Δp")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        Fq, tq, mq = (
            c.knowns.get("F"),
            c.knowns.get("t"),
            c.knowns.get("m"),
        )
        v0q = c.knowns.get("v0") or c.knowns.get("v")
        requested = set(c.requested_outputs or c.unknowns or [])
        asks_final_velocity = "final_velocity" in requested
        if not Fq or not tq:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["충격량 계산에는 힘 F와 작용시간 t가 필요합니다."],
                ),
            )
        if asks_final_velocity and (mq is None or v0q is None):
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["최종속도에는 질량 m과 초기속도 v_i가 필요합니다."],
                ),
            )

        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=generated.errors,
                ),
                unsupported_reason="힘 방향과 충격량-운동량 입력을 확인해 주세요.",
            )
        impulse = float(generated.solution["J"])
        force_component = float(generated.solution["force_component"])
        duration = magnitude_si(tq, "s")

        if asks_final_velocity:
            final_velocity = float(generated.solution["v_f"])
            initial_velocity = float(generated.solution["v_i"])
            answers = [
                AnswerItem(
                    "최종속도",
                    "v_f",
                    round(final_velocity, 5),
                    "m/s",
                    f"v_f = {final_velocity:.3f} m/s",
                    "primary",
                )
            ]
            if "impulse" in requested:
                answers.append(
                    AnswerItem(
                        "충격량",
                        "J",
                        round(impulse, 5),
                        "N·s",
                        f"J = {impulse:.3f} N·s",
                        "component",
                    )
                )
            steps = [
                StepCard(
                    "부호 있는 충격량",
                    "초기 운동의 양의 방향을 기준으로 힘 성분의 부호를 정합니다.",
                    r"J=F_{\parallel}\Delta t",
                ),
                StepCard(
                    "운동량 변화",
                    "충격량은 선운동량 변화량과 같습니다.",
                    r"J=m(v_f-v_i)",
                ),
                StepCard(
                    "계산",
                    f"F_parallel={force_component:g} N, Δt={duration:g} s, "
                    f"v_i={initial_velocity:g} m/s → v_f={final_velocity:.5g} m/s",
                ),
            ]
            return SolverResult(
                ok=True,
                answer=Answer(
                    symbolic="v_f = v_i + J/m",
                    numeric=round(final_velocity, 5),
                    unit="m/s",
                    display=f"v_f = {final_velocity:.3f} m/s",
                ),
                answers=answers,
                steps=steps,
                verification=VerificationReport(
                    passed=True,
                    checks=[
                        "힘이 운동 반대방향이면 충격량은 음수가 되어 속도를 감소시킬 수 있습니다."
                    ],
                ),
                used_equations=["J = F_parallel Δt", "J = m(v_f-v_i)"],
            )

        force_magnitude = abs(magnitude_si(Fq, "N"))
        impulse_label = "충격량 크기" if impulse >= 0 else "부호 있는 충격량"
        steps = [
            StepCard(
                "충격량",
                "방향을 묻지 않은 충격량 단독 문제에서는 크기 |J|=|F|Δt를 계산합니다.",
                r"|J|=|F|\Delta t",
            ),
            StepCard(
                "계산",
                f"|J| = {force_magnitude:g} × {duration:g} = {abs(impulse):.5g} N·s",
            ),
        ]
        displayed_impulse = abs(impulse)
        return SolverResult(
            ok=True,
            answer=Answer(
                symbolic="|J| = |F|Δt",
                numeric=round(displayed_impulse, 5),
                unit="N·s",
                display=f"|J| = {displayed_impulse:.3f} N·s",
            ),
            answers=[
                AnswerItem(
                    impulse_label,
                    "J",
                    round(displayed_impulse, 5),
                    "N·s",
                    f"|J| = {displayed_impulse:.3f} N·s",
                    "primary",
                )
            ],
            steps=steps,
            verification=VerificationReport(
                passed=True,
                checks=["단위 N·s는 kg·m/s와 같아 운동량 단위와 일치합니다."],
            ),
            used_equations=["|J| = |F|Δt"],
        )

