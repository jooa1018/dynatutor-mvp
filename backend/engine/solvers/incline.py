import math
from sympy import Eq, Symbol, sin, pi, solve

from engine.models import (
    Answer, CanonicalProblem, EquationEvidence, SolverResult, StepCard,
    SubstitutionEvidence, VerificationReport,
)
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import require_no_missing, merge_reports
from engine.equation_generators.particle_newton import solve_particle_newton_system
from engine.model_builder import build_physical_model
from engine.model_builder.model_types import PhysicalModel
from engine.physics_core import symbols as S
from engine.physics_core.friction import decide_incline_static
from engine.physics_core.units import magnitude_si
from engine.solvers.explanation_evidence import (
    OutputSpec,
    assumption_fact,
    attach_evidence,
    calculation_frame,
    gravity_fact,
    known_fact,
    semantic_fact,
)


def _incline_frame(solver_name: str):
    return calculation_frame(
        f"{solver_name}.slope-frame",
        "cartesian_2d",
        ("x", "y"),
        ("down_slope", "normal_outward"),
        ("m", "m"),
    )


def _gravity_parts(c: CanonicalProblem):
    fact = gravity_fact(c)
    value = (
        magnitude_si(c.knowns["g"], "m/s^2")
        if fact.fact_id == "known:g"
        else 9.81
    )
    return fact, value



def _invalid_mass_result(c: CanonicalProblem) -> SolverResult | None:
    mass = c.knowns.get("m")
    if mass is not None and mass.value is not None and float(mass.value) <= 0:
        return SolverResult(
            ok=False,
            verification=VerificationReport(
                passed=False,
                errors=["잘못된 물리 입력: 질량 m은 0보다 커야 합니다."],
            ),
            unsupported_reason="질량 m은 양수여야 합니다.",
        )
    return None


class InclineNoFrictionSolver(BaseSolver):
    uses_prebuilt_physical_model = True
    name = "incline_no_friction"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "particle_on_incline" and c.subtype == "no_friction":
            return SolverMatch(self, 100, "경사면 + 마찰 없음 + 가속도 문제")
        return None

    def solve(self, c: CanonicalProblem, model: PhysicalModel | None = None) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="필수 조건이 부족합니다.")
        invalid_mass = _invalid_mass_result(c)
        if invalid_mass is not None:
            return invalid_mass

        model = model or build_physical_model(c)
        generated = solve_particle_newton_system(c, model)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=generated.errors), unsupported_reason="모델 기반 Newton 방정식 생성/풀이에 실패했습니다.", selection_decision=generated.decision)
        a_val = float(generated.solution[S.a])
        symbolic = "g*sin(theta)"

        steps = [
            StepCard("문제 유형", "마찰이 없으므로 경사면 방향으로 중력 성분만 가속도를 만듭니다."),
            StepCard("좌표축", "x축을 경사면 아래 방향, y축을 경사면 수직 방향으로 잡습니다."),
            StepCard("힘 분해", "중력 mg를 경사면 방향 mg sinθ와 수직 방향 mg cosθ로 나눕니다."),
            StepCard("운동방정식", "Phase 15 Newton generator가 PhysicalModel의 힘 목록에서 ΣF=ma 식을 생성했습니다.", "mg\\sin\\theta = ma"),
            StepCard("정리", "질량 m이 약분되어 가속도는 질량과 무관합니다.", "a = g\\sin\\theta"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=[
                "단위: g가 m/s²이고 sinθ는 무차원이므로 a의 단위는 m/s²입니다.",
                "θ=0°이면 a=0이 되어 평평한 바닥과 일치합니다.",
                "θ=90°이면 a=g가 되어 자유낙하와 일치합니다.",
            ],
        )
        result = SolverResult(
            ok=True,
            answer=Answer(symbolic=f"a = {symbolic}", numeric=round(a_val, 5), unit="m/s²", display=f"a = {a_val:.3f} m/s²", output_key="acceleration"),
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["ΣF_x = ma", "mg sinθ = ma", "a = g sinθ"],
            fbd=["중력 mg", "수직항력 N"],
            selection_decision=generated.decision,
            coordinate_guide=["x축: 경사면 아래 방향", "y축: 경사면 수직 방향"],
        )
        gravity, gravity_value = _gravity_parts(c)
        subtype = semantic_fact(c, "subtype")
        theta = known_fact(c, "theta")
        particle = assumption_fact("particle_model", "point_mass")
        fact_ids = (subtype.fact_id, theta.fact_id, gravity.fact_id, particle.fact_id)
        selected = generated.decision.selected_candidate
        return attach_evidence(
            result,
            solver_name=self.name,
            coordinate_frame=_incline_frame(self.name),
            explicit_facts=(subtype, theta) + (() if gravity.classification == "assumed" else (gravity,)),
            assumptions=(particle,) + ((gravity,) if gravity.classification == "assumed" else ()),
            equations=(
                EquationEvidence(
                    "incline-no-friction.acceleration",
                    "a = g sin(theta)",
                    "solver_equation",
                    "newton_second_law",
                    fact_ids=fact_ids,
                    output_ids=("acceleration",),
                ),
            ),
            substitutions=(
                SubstitutionEvidence(
                    "incline-no-friction.acceleration.values",
                    "incline-no-friction.acceleration",
                    f"a = {gravity_value} sin({c.knowns['theta'].value} deg) = {result.answer.numeric} m/s²",
                    "acceleration",
                    fact_ids=fact_ids,
                ),
            ),
            outputs=(
                OutputSpec(
                    "acceleration", 0, "acceleration", "a",
                    ("incline-no-friction.acceleration",),
                    ("incline-no-friction.acceleration.values",),
                    candidate_id=selected.candidate_id,
                    candidate_numeric=selected.numerical_mapping["a"],
                    delivery_candidate_key="acceleration",
                    delivery_transform="python_builtin_round",
                    decimal_places=5,
                    delivery_policy_id="incline.no_friction.acceleration.round5",
                ),
            ),
        )


class InclineWithFrictionSolver(BaseSolver):
    uses_prebuilt_physical_model = True
    name = "incline_with_friction"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "particle_on_incline" and c.subtype == "with_friction":
            return SolverMatch(self, 95, "경사면 + 마찰계수 + 미끄럼 가속도 문제")
        return None

    def solve(self, c: CanonicalProblem, model: PhysicalModel | None = None) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="필수 조건이 부족합니다.")
        invalid_mass = _invalid_mass_result(c)
        if invalid_mass is not None:
            return invalid_mass
        if c.friction_type == "static":
            theta = math.radians(magnitude_si(c.knowns["theta"], "deg"))
            g_val = magnitude_si(c.knowns["g"], "m/s^2")
            mu_s_q = c.knowns.get("mu_s") or c.knowns.get("mu")
            mu_s = float(mu_s_q.value)
            mass = magnitude_si(c.knowns["m"], "kg") if "m" in c.knowns else None
            decision = decide_incline_static(theta, mu_s, mass=mass, g=g_val)
            if decision.holds_static:
                verification = VerificationReport(
                    passed=True,
                    dimension_summary="정지마찰 부등식으로 a=0 판정",
                    checks=[
                        decision.equation_note or "mg sinθ <= μ_s mg cosθ",
                        f"driving={decision.driving_force:.3f} N, f_s,max={decision.max_static:.3f} N",
                    ],
                )
                return SolverResult(
                    ok=True,
                    answer=Answer(symbolic="a = 0, |f_s| <= μ_s N", numeric=0.0, unit="m/s²", display=f"a = 0.000 m/s², f_s = {decision.friction_force:.3f} N", output_key="acceleration"),
                    steps=[
                        StepCard("정지마찰 판정", "정지마찰 문제는 먼저 움직이는지 확인합니다.", r"|f_s| \le \mu_s N"),
                        StepCard("부등식 비교", f"구동력={decision.driving_force:.3f} N, 최대정지마찰={decision.max_static:.3f} N → 정지 유지"),
                    ],
                    verification=merge_reports(pre, verification),
                    used_equations=["mg sinθ <= μ_s mg cosθ → a=0"],
                    fbd=["중력 mg", "수직항력 N", "정지마찰 f_s"],
                    coordinate_guide=["x축: 경사면 아래 방향", "y축: 경사면 수직 방향"],
                )

        model = model or build_physical_model(c)
        generated = solve_particle_newton_system(c, model)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(passed=False, errors=generated.errors), unsupported_reason="모델 기반 Newton 방정식 생성/풀이에 실패했습니다.", selection_decision=generated.decision)
        a_val = float(generated.solution[S.a])
        warnings = []
        if a_val < 0:
            warnings.append("계산된 a가 음수입니다. 아래로 미끄러진다는 가정이 실제로는 성립하지 않을 수 있습니다.")

        steps = [
            StepCard("문제 유형", "마찰이 있으므로 경사면 방향 중력 성분에서 마찰력을 빼야 합니다."),
            StepCard("수직 방향", "수직 방향 가속도는 0이므로 N = mg cosθ입니다.", "N = mg\\cos\\theta"),
            StepCard("마찰력", "운동마찰력은 f = μN = μmg cosθ입니다.", "f = \\mu mg\\cos\\theta"),
            StepCard("경사면 방향", "아래 방향을 +로 잡으면 mg sinθ - f = ma입니다.", "mg\\sin\\theta - \\mu mg\\cos\\theta = ma"),
            StepCard("정리", "m을 약분합니다.", "a = g(\\sin\\theta - \\mu\\cos\\theta)"),
        ]
        verification = VerificationReport(
            passed=True,
            checks=[
                "μ=0으로 두면 마찰 없는 경사면 공식 a=g sinθ로 돌아갑니다.",
                "마찰항 μg cosθ도 단위가 m/s²입니다.",
            ],
            warnings=warnings,
        )
        result = SolverResult(
            ok=True,
            answer=Answer(symbolic="a = g(sinθ - μcosθ)", numeric=round(a_val, 5), unit="m/s²", display=f"a = {a_val:.3f} m/s²", output_key="acceleration"),
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["N = mg cosθ", "f = μN", "mg sinθ - f = ma"],
            fbd=["중력 mg", "수직항력 N", "마찰력 f"],
            selection_decision=generated.decision,
            coordinate_guide=["x축: 경사면 아래 방향", "y축: 경사면 수직 방향"],
        )
        mu_key = "mu" if "mu" in c.knowns else "mu_k" if "mu_k" in c.knowns else None
        if mu_key is None:
            return result
        gravity, gravity_value = _gravity_parts(c)
        subtype = semantic_fact(c, "subtype")
        theta = known_fact(c, "theta")
        friction = known_fact(c, mu_key)
        particle = assumption_fact("particle_model", "point_mass")
        fact_ids = (
            subtype.fact_id, theta.fact_id, friction.fact_id,
            gravity.fact_id, particle.fact_id,
        )
        selected = generated.decision.selected_candidate
        return attach_evidence(
            result,
            solver_name=self.name,
            coordinate_frame=_incline_frame(self.name),
            explicit_facts=(subtype, theta, friction) + (() if gravity.classification == "assumed" else (gravity,)),
            assumptions=(particle,) + ((gravity,) if gravity.classification == "assumed" else ()),
            equations=(
                EquationEvidence(
                    "incline-with-friction.acceleration",
                    "a = g (sin(theta) - mu cos(theta))",
                    "solver_equation",
                    "newton_second_law",
                    fact_ids=fact_ids,
                    output_ids=("acceleration",),
                ),
            ),
            substitutions=(
                SubstitutionEvidence(
                    "incline-with-friction.acceleration.values",
                    "incline-with-friction.acceleration",
                    f"a = {gravity_value} (sin({c.knowns['theta'].value} deg) - {c.knowns[mu_key].value} cos({c.knowns['theta'].value} deg)) = {result.answer.numeric} m/s²",
                    "acceleration",
                    fact_ids=fact_ids,
                ),
            ),
            outputs=(
                OutputSpec(
                    "acceleration", 0, "acceleration", "a",
                    ("incline-with-friction.acceleration",),
                    ("incline-with-friction.acceleration.values",),
                    candidate_id=selected.candidate_id,
                    candidate_numeric=selected.numerical_mapping["a"],
                    delivery_candidate_key="acceleration",
                    delivery_transform="python_builtin_round",
                    decimal_places=5,
                    delivery_policy_id="incline.with_friction.moving.round5",
                ),
            ),
        )
