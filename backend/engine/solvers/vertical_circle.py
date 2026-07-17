import math

from engine.models import (
    Answer, AnswerItem, CanonicalProblem, EquationEvidence, SolverResult,
    StepCard, SubstitutionEvidence, VerificationReport,
)
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import require_no_missing, merge_reports
from engine.solvers.explanation_evidence import (
    OutputSpec,
    attach_evidence,
    calculation_frame,
    gravity_fact,
    known_fact,
    semantic_fact,
)


class VerticalCircleSolver(BaseSolver):
    name = "vertical_circle"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "vertical_circle":
            return SolverMatch(self, 80, "수직 원운동 최고점/최저점 중심방향 힘 문제")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        requested = set(c.requested_outputs or c.unknowns or [])
        if c.subtype not in {"top", "bottom"}:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["수직 원운동에서 계산 지점이 최고점인지 최저점인지 필요합니다."],
                ),
                unsupported_reason="최고점 또는 최저점을 명시해 주세요.",
            )
        if "minimum_speed" in requested and c.subtype != "top":
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["현재 minimum_speed 한계식 v_min=sqrt(gR)은 최고점 조건 전용입니다."],
                ),
                unsupported_reason="최소속도를 묻는 지점이 최고점인지 확인해 주세요.",
            )
        # 최고점 최소속도는 질량과 무관하므로 R만 있으면 계산할 수 있다.
        if c.subtype == "top" and "minimum_speed" in requested and "R" in c.knowns:
            R = magnitude_si(c.knowns["R"], "m")
            g = magnitude_si(c.knowns["g"], "m/s^2") if "g" in c.knowns else 9.81
            if R <= 0 or g <= 0:
                return SolverResult(
                    ok=False,
                    verification=VerificationReport(
                        passed=False,
                        errors=["반지름 R과 중력가속도 g는 0보다 커야 합니다."],
                    ),
                    unsupported_reason="수직 원운동의 반지름과 중력가속도를 확인해 주세요.",
                )
            vmin = math.sqrt(g * R)
            steps = [
                StepCard("최고점 조건", "최고점에서 중심 방향은 아래쪽입니다."),
                StepCard("최소 속도", "줄이 간신히 팽팽하거나 접촉을 막 유지하는 한계에서는 T=0 또는 N=0입니다."),
                StepCard("원운동식", "mg = mv²/R 이므로 v_min = sqrt(gR)입니다.", "v_{min} = \\sqrt{gR}"),
            ]
            ver = VerificationReport(
                passed=True,
                checks=[
                    "R이 커질수록 필요한 최소속도가 커집니다.",
                    "단위 sqrt((m/s²)m)=m/s입니다.",
                ],
            )
            return SolverResult(
                ok=True,
                answer=Answer(
                    symbolic="v_min = sqrt(gR)",
                    numeric=round(vmin, 5),
                    unit="m/s",
                    display=f"v_min = {vmin:.3f} m/s",
                ),
                answers=[
                    AnswerItem(
                        "최소 속도",
                        "v_min",
                        round(vmin, 5),
                        "m/s",
                        f"v_min = {vmin:.3f} m/s",
                        "primary",
                    )
                ] + (
                    [
                        AnswerItem(
                            "한계 장력/수직항력",
                            "T",
                            0.0,
                            "N",
                            "한계 구속력 T = 0.000 N",
                            "primary", output_key="tension"
                        )
                    ]
                    if requested.intersection({"tension", "force", "normal_force"})
                    else []
                ),
                steps=steps,
                verification=ver,
                used_equations=["mg = mv²/R", "v_min = sqrt(gR)"],
            )

        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(
                ok=False,
                verification=pre,
                unsupported_reason="R, v, 최고점/최저점 정보가 필요합니다.",
            )
        if "m" not in c.knowns or c.knowns["m"].value is None:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["장력/수직항력을 N 단위로 구하려면 질량 m이 필요합니다."],
                ),
                unsupported_reason="최소속도는 질량 없이 구할 수 있지만 힘을 구하려면 질량 m을 알려 주세요.",
            )

        R = magnitude_si(c.knowns["R"], "m")
        v = magnitude_si(c.knowns["v"], "m/s")
        mass = magnitude_si(c.knowns["m"], "kg")
        g = magnitude_si(c.knowns["g"], "m/s^2") if "g" in c.knowns else 9.81
        if R <= 0 or mass <= 0 or g <= 0:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["질량 m, 반지름 R, 중력가속도 g는 0보다 커야 합니다."],
                ),
                unsupported_reason="수직 원운동 입력값의 물리적 범위를 확인해 주세요.",
            )

        if c.subtype == "top":
            T = mass * v * v / R - mass * g
            formula = "T + mg = mv²/R"
        else:
            T = mass * v * v / R + mass * g
            formula = "T - mg = mv²/R"

        if T < -1e-10:
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=[
                        f"계산된 장력 T={T:.6g} N이 음수이므로 줄이 팽팽한 수직 원운동 구속이 성립하지 않습니다."
                    ],
                    warnings=["물체는 그 전에 줄이 느슨해지거나 접촉면에서 이탈합니다."],
                ),
                unsupported_reason="접촉 이탈/줄 느슨해짐 이후의 운동으로 모델을 전환해야 합니다.",
                used_equations=[formula],
            )

        T = max(0.0, T)
        steps = [
            StepCard("중심 방향 설정", "수직 원운동은 항상 중심 방향으로 ΣF_n = mv²/R을 적용합니다."),
            StepCard("해당 지점의 식", f"현재 지점에서는 {formula} 를 사용합니다.", formula.replace("²", "^2")),
        ]
        ver = VerificationReport(
            passed=True,
            checks=[
                "구심력은 별도의 힘이 아니라 실제 힘들의 중심방향 합입니다.",
                "장력이 0 이상이므로 현재 줄 구속과 양립합니다.",
            ],
        )
        result = SolverResult(
            ok=True,
            answer=Answer(
                symbolic=formula,
                numeric=round(T, 5),
                unit="N",
                display=f"T = {T:.3f} N",
            ),
            answers=[
                AnswerItem(
                    "장력",
                    "T",
                    round(T, 5),
                    "N",
                    f"T = {T:.3f} N",
                    "primary", output_key="tension"
                )
            ],
            steps=steps,
            verification=merge_reports(pre, ver),
            used_equations=[formula],
        )
        if (
            c.knowns["m"].unit != "kg"
            or c.knowns["R"].unit != "m"
            or c.knowns["v"].unit != "m/s"
            or (
                "g" in c.knowns
                and c.knowns["g"].unit not in {"m/s^2", "m/s²"}
            )
        ):
            return result
        gravity = gravity_fact(c)
        subtype = semantic_fact(c, "subtype")
        explicit = [
            known_fact(c, "m"), known_fact(c, "R"), known_fact(c, "v"), subtype,
        ]
        assumptions = []
        if gravity.classification == "assumed":
            assumptions.append(gravity)
        else:
            explicit.append(gravity)
        fact_ids = tuple(fact.fact_id for fact in (*explicit, *assumptions))
        sign = "-" if c.subtype == "top" else "+"
        return attach_evidence(
            result,
            solver_name=self.name,
            coordinate_frame=calculation_frame(
                "vertical-circle.path-frame", "path_tangent_normal",
                ("t", "n"), ("tangential_positive", "normal_inward"),
                ("m", "m"),
            ),
            explicit_facts=explicit,
            assumptions=assumptions,
            equations=(
                EquationEvidence(
                    "vertical-circle.tension",
                    f"T = m v^2 / R {sign} m g",
                    "solver_equation", "newton_second_law",
                    fact_ids=fact_ids, output_ids=("tension",),
                ),
            ),
            substitutions=(
                SubstitutionEvidence(
                    "vertical-circle.tension.values",
                    "vertical-circle.tension",
                    f"T = {mass} * {v}^2 / {R} {sign} {mass} * {g} = {result.answers[0].numeric} N",
                    "tension", fact_ids=fact_ids,
                ),
            ),
            outputs=(
                OutputSpec(
                    "tension", 0, "tension", "tension",
                    ("vertical-circle.tension",),
                    ("vertical-circle.tension.values",),
                ),
            ),
        )
