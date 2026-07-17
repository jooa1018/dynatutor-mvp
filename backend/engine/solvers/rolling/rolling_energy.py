from __future__ import annotations

import math
from engine.models import (
    Answer, AnswerItem, CanonicalProblem, EquationEvidence, SolverResult,
    StepCard, SubstitutionEvidence, VerificationReport,
)
from engine.physics_core.inertia import INERTIA_BETA, beta_for_shape
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing
from engine.equation_generators.energy_momentum import solve_energy_momentum_system
from engine.solvers.explanation_evidence import (
    OutputSpec,
    assumption_fact,
    attach_evidence,
    calculation_frame,
    flag_fact,
    gravity_fact,
    known_fact,
    semantic_fact,
)


_SHAPE_BETA_RELATIONS = {
    "solid_sphere": ("2 / 5", 2 / 5),
    "hollow_sphere": ("2 / 3", 2 / 3),
    "solid_cylinder": ("1 / 2", 1 / 2),
    "disk": ("1 / 2", 1 / 2),
    "hoop": ("1", 1.0),
    "ring": ("1", 1.0),
}


def _optional_evidence_radius(c: CanonicalProblem) -> float | None:
    """Return a valid optional radius without affecting the primary solve."""

    for symbol in ("R", "r"):
        quantity = c.knowns.get(symbol)
        if (
            quantity is None
            or quantity.value is None
            or isinstance(quantity.value, bool)
        ):
            continue
        try:
            radius = float(magnitude_si(quantity, "m"))
        except (AttributeError, TypeError, ValueError, OverflowError):
            # Pint UndefinedUnitError inherits AttributeError; this conversion
            # is optional evidence only and cannot invalidate the primary solve.
            continue
        if math.isfinite(radius) and radius > 0.0:
            return radius
    return None


class PureRollingEnergySolver(BaseSolver):
    name = "pure_rolling_energy"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "pure_rolling_energy":
            return SolverMatch(self, 91, "미끄럼 없는 구름 + 에너지 보존 + 물체 형상 관성모멘트")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="구름운동은 높이 h와 물체 종류 또는 관성모멘트가 필요합니다.")
        h = magnitude_si(c.knowns["h"], "m") if "h" in c.knowns else float(c.launch_height or 0.0)
        g = magnitude_si(c.knowns["g"], "m/s^2")
        beta = beta_for_shape(c.body_shape)
        if beta is None:
            return SolverResult(
                ok=False,
                verification=VerificationReport(passed=False, errors=["물체 종류 또는 관성모멘트 I가 필요합니다."]),
                unsupported_reason="예: 속이 찬 구/원판/고리/원통 중 하나를 알려주세요.",
            )
        generated = solve_energy_momentum_system(c)
        if not generated.ok:
            return SolverResult(ok=False, verification=VerificationReport(False, errors=generated.errors), unsupported_reason="모델 기반 구름 에너지 방정식 생성/풀이에 실패했습니다.")
        v = float(generated.solution["v"])
        beta = float(generated.solution["beta"])
        radius = _optional_evidence_radius(c)
        typed_answers = [
            AnswerItem(
                "질량중심 최종속도",
                "v",
                round(v, 6),
                "m/s",
                f"질량중심 최종속도 v = {v:.3f} m/s",
                "primary",
                output_key="final_velocity",
            )
        ]
        if radius is not None and math.isfinite(radius) and radius > 0.0:
            omega = v / radius
            typed_answers.append(
                AnswerItem(
                    "순수 구름 각속도",
                    "omega",
                    round(omega, 6),
                    "rad/s",
                    f"순수 구름 각속도 omega = {omega:.3f} rad/s",
                    "component",
                    output_key="angular_velocity",
                )
            )
        initial_speed = float(generated.solution.get("v0", 0.0))
        steps = [
            StepCard("형상 확인", f"물체 종류를 {c.body_shape}로 해석했고 β=I/(mR²)={beta:g}를 사용합니다."),
            StepCard("에너지식", "초기 병진·회전 운동에너지를 보존하고 위치에너지 감소를 더합니다.", r"K_f=K_i+mgh,\quad K=\frac12mv^2+\frac12I\omega^2"),
            StepCard("관성모멘트 모델", "I=βmR², v=ωR을 대입합니다.", r"I=\beta mR^2,\quad v=\omega R"),
            StepCard("정리", f"초기속도 v0={initial_speed:g} m/s를 포함합니다.", r"v=\sqrt{v_0^2+\frac{2gh}{1+\beta}}"),
        ]
        verification = VerificationReport(
            passed=True,
            dimension_summary="sqrt(gh)는 m/s 차원입니다.",
            checks=[
                "β가 커질수록 같은 높이에서 속도는 작아집니다.",
                "β=0이면 미끄러지는 질점의 v=sqrt(2gh)와 같아집니다.",
                "미끄러짐이 있으면 v=ωR을 쓰면 안 됩니다.",
            ],
        )
        result = SolverResult(
            ok=True,
            answer=Answer(symbolic="v = sqrt(v0²+2gh/(1+β))", numeric=round(v, 6), unit="m/s", display=f"v = {v:.3f} m/s (β={beta:g})", output_key="final_velocity"),
            answers=typed_answers,
            steps=steps,
            verification=merge_reports(pre, verification),
            used_equations=["mgh = 1/2mv² + 1/2Iω²", "v=ωR", "I=βmR²"],
            fbd=["중력 mg", "수직항력 N", "정지마찰력 f_s"],
            coordinate_guide=["질량중심 병진 + 질량중심 기준 회전"],
        )
        if (
            "h" not in c.knowns
            or c.knowns["h"].unit != "m"
            or len(typed_answers) != 1
            or (
                "g" in c.knowns
                and c.knowns["g"].unit not in {"m/s^2", "m/s²"}
            )
        ):
            return result
        if "v0" in c.knowns:
            if c.knowns["v0"].unit != "m/s":
                return result
            initial = known_fact(c, "v0")
        elif (c.flags or {}).get("starts_from_rest") is True:
            initial = flag_fact(c, "starts_from_rest")
        else:
            return result
        expected_beta = beta_for_shape(c.body_shape)
        shape_relation = _SHAPE_BETA_RELATIONS.get(c.body_shape or "")
        if (
            expected_beta is None
            or shape_relation is None
            or INERTIA_BETA.get(c.body_shape or "") != shape_relation[1]
            or float(expected_beta) != shape_relation[1]
            or beta != shape_relation[1]
            or (c.flags or {}).get("no_slip") is not True
        ):
            return result

        gravity = gravity_fact(c)
        gravity_value = (
            magnitude_si(c.knowns["g"], "m/s^2")
            if "g" in c.knowns and c.knowns["g"].value is not None
            else 9.81
        )
        height = known_fact(c, "h")
        shape = semantic_fact(c, "body_shape")
        no_slip = flag_fact(c, "no_slip")
        no_loss = assumption_fact("energy_loss", "none")
        explicit = [height, shape, initial, no_slip]
        assumptions = [no_loss]
        if gravity.classification == "assumed":
            assumptions.append(gravity)
        else:
            explicit.append(gravity)

        beta_facts = (shape.fact_id,)
        speed_facts = (
            height.fact_id, gravity.fact_id, initial.fact_id,
            no_slip.fact_id, no_loss.fact_id,
        )
        equations = [
            EquationEvidence(
                "rolling.shape-inertia",
                f"beta({c.body_shape}) = {shape_relation[0]}",
                "physics_core",
                "constitutive_law",
                fact_ids=beta_facts,
                output_ids=("shape_beta",),
            ),
            EquationEvidence(
                "rolling.energy-speed",
                "v = sqrt(v0^2 + 2 g h / (1 + beta))",
                "solver_equation",
                "conservation_law",
                fact_ids=speed_facts,
                input_output_ids=("shape_beta",),
                output_ids=("final_velocity",),
            ),
        ]
        substitutions = [
            SubstitutionEvidence(
                "rolling.shape-inertia.values",
                "rolling.shape-inertia",
                f"beta({c.body_shape}) = {shape_relation[0]} = {beta}",
                "shape_beta",
                fact_ids=beta_facts,
            ),
            SubstitutionEvidence(
                "rolling.energy-speed.values",
                "rolling.energy-speed",
                f"v = sqrt({initial_speed}^2 + 2 * {gravity_value} * {h} / (1 + {beta})) = {typed_answers[0].numeric} m/s",
                "final_velocity",
                fact_ids=speed_facts,
                input_output_ids=("shape_beta",),
            ),
        ]
        outputs = [
            OutputSpec(
                "final_velocity", 0, "final_velocity", "final_velocity",
                ("rolling.energy-speed",),
                ("rolling.energy-speed.values",),
            )
        ]
        return attach_evidence(
            result,
            solver_name=self.name,
            coordinate_frame=calculation_frame(
                "pure-rolling.body-frame", "body_fixed_2d",
                ("x", "theta"), ("down_slope", "clockwise"), ("m", "rad"),
            ),
            explicit_facts=explicit,
            assumptions=assumptions,
            equations=equations,
            substitutions=substitutions,
            outputs=outputs,
        )
