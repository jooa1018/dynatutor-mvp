from __future__ import annotations

from app.schemas.llm import LockedFacts
from app.schemas.solution import SolveResponse


def build_fallback_explanation(solution: SolveResponse, locked: LockedFacts, level: str = "beginner") -> str:
    lines: list[str] = []
    lines.append("### AI 없이 생성한 안전 설명")
    lines.append("")
    lines.append(f"이 문제는 **{locked.problem_type}** 유형으로 분류됐습니다.")
    if locked.selected_solver:
        lines.append(f"계산은 `{locked.selected_solver}` solver가 맡았습니다.")
    if locked.answers:
        lines.append("최종 답은 다음과 같습니다.")
        for ans in locked.answers:
            lines.append(f"- **{ans.get('display')}**")
    elif locked.answer_display:
        lines.append(f"최종 답은 **{locked.answer_display}** 입니다.")
    else:
        lines.append("아직 이 유형은 최종 계산까지 지원하지 않아서 진단 결과를 먼저 확인해야 합니다.")
        if locked.unsupported_reason:
            lines.append(f"지원 불가 이유: {locked.unsupported_reason}")
    lines.append("")
    if locked.equations:
        lines.append("#### 핵심 공식")
        for eq in locked.equations[:5]:
            lines.append(f"- `{eq}`")
        lines.append("")
    if solution.steps:
        lines.append("#### 풀이 흐름")
        for i, step in enumerate(solution.steps[:5], start=1):
            math = f" `{step.math}`" if step.math else ""
            lines.append(f"{i}. **{step.title}**: {step.body}{math}")
        lines.append("")
    if solution.verification.checks:
        lines.append("#### 검산")
        for check in solution.verification.checks[:4]:
            lines.append(f"- {check}")
    if solution.common_mistakes:
        lines.append("")
        lines.append("#### 조심할 점")
        for mistake in solution.common_mistakes[:4]:
            lines.append(f"- {mistake}")
    return "\n".join(lines)


def append_final_check_if_needed(explanation: str, locked: LockedFacts) -> str:
    """Ensure template/fallback explanations always close with locked answer."""
    if locked.answers:
        final = "\n".join(f"- **{ans.get('display')}**" for ans in locked.answers)
        if "### 마지막 확인" in explanation and all((ans.get("display") or "") in explanation for ans in locked.answers):
            return explanation
        return explanation.rstrip() + "\n\n### 마지막 확인\n" + final
    if not locked.answer_display:
        return explanation
    if "### 마지막 확인" in explanation and locked.answer_display in explanation:
        return explanation
    return explanation.rstrip() + "\n\n### 마지막 확인\n최종 답은 **" + locked.answer_display + "** 입니다."
