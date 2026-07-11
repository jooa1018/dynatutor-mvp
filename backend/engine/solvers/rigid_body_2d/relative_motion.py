from __future__ import annotations

from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, StepCard, VerificationReport
from engine.physics_core.units import magnitude_si
from engine.solvers.base import BaseSolver, SolverMatch
from engine.verification.checks import merge_reports, require_no_missing


class RelativeAccelerationTranslationSolver(BaseSolver):
    name = "relative_acceleration_translation"

    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        if c.system_type == "relative_acceleration_translation":
            return SolverMatch(self, 86, "병진 기준계 상대가속도 a_B=a_A+a_B/A")
        return None

    def solve(self, c: CanonicalProblem) -> SolverResult:
        pre = require_no_missing(c)
        if not pre.passed:
            return SolverResult(ok=False, verification=pre, unsupported_reason="상대가속도 기본형에는 aA와 a_rel이 필요합니다.")
        a_a = magnitude_si(c.knowns["aA"], "m/s^2")
        a_rel = magnitude_si(c.knowns["arel"], "m/s^2")
        compact = (c.raw_text or "").lower().replace(" ", "")
        same_direction = (
            "같은방향" in compact
            or any(compact.count(word) >= 2 for word in ("오른쪽", "왼쪽", "위쪽", "아래쪽", "right", "left", "upward", "downward"))
        )
        opposite_direction = "반대방향" in compact or "opposite" in compact
        if not (same_direction or opposite_direction):
            return SolverResult(
                ok=False,
                verification=VerificationReport(
                    passed=False,
                    errors=["a_A와 a_rel의 방향 또는 벡터 성분이 필요합니다."],
                ),
                unsupported_reason="상대가속도는 방향 없는 스칼라 크기를 임의로 더하지 않습니다.",
            )
        sign = -1.0 if opposite_direction else 1.0
        a_b = a_a + sign * a_rel
        verification = VerificationReport(
            passed=True,
            dimension_summary="가속도 성분 합의 단위는 m/s²입니다.",
            checks=["a_rel=0이면 B의 가속도는 A와 같습니다.", "방향각이 있는 문제는 벡터 성분으로 확장해야 합니다."],
        )
        return SolverResult(
            ok=True,
            answer=Answer(symbolic="a_B = a_A + a_{B/A}", numeric=round(a_b, 6), unit="m/s²", display=f"a_B = {a_b:.3f} m/s²"),
            answers=[AnswerItem(label="B점 가속도", symbol="a_B", numeric=round(a_b, 6), unit="m/s²", display=f"a_B = {a_b:.3f} m/s²", role="primary")],
            steps=[
                StepCard("상대가속도 관계", "병진 기준계라면 기준점 가속도와 상대가속도를 더합니다.", r"\vec a_B=\vec a_A+\vec a_{B/A}"),
                StepCard("계산", f"a_A={a_a:g}, a_B/A={sign * a_rel:g} → a_B={a_b:.3f} m/s²"),
            ],
            verification=merge_reports(pre, verification),
            used_equations=["a_B=a_A+a_B/A"],
        )
