
from __future__ import annotations

import json

from app.schemas.llm import LockedFacts
from app.schemas.solution import SolveResponse


def build_llm_prompt(problem_text: str, student_solution: str | None, solution: SolveResponse, locked: LockedFacts, level: str, style: str) -> str:
    knowns = "\n".join(f"- {k}: {v}" for k, v in locked.known_values.items()) or "- 없음"
    equations = "\n".join(f"- {eq}" for eq in locked.equations) or "- 없음"
    not_applicable = "\n".join(f"- {eq}" for eq in locked.not_applicable_equations) or "- 없음"
    steps = "\n".join(f"- {s}" for s in locked.steps) or "- 없음"
    checks = "\n".join(f"- {c}" for c in locked.checks) or "- 없음"
    mistakes = "\n".join(f"- {m}" for m in solution.common_mistakes) or "- 없음"
    student = student_solution.strip() if student_solution and student_solution.strip() else "학생 풀이 없음"
    locked_json = json.dumps(locked.model_dump(), ensure_ascii=False, sort_keys=True, indent=2)

    return f"""
너는 기계공학과 학생을 돕는 동역학 튜터다. 아래의 '잠긴 사실'만 사용해서 한국어로 설명하라.

절대 규칙:
1. 최종 답, 숫자, 단위, 공식, solver 결과를 바꾸지 마라.
2. LOCKED_FACTS_JSON에 없는 새 숫자, 새 조건, 새 물체, 새 공식은 만들지 마라.
3. 문제에 없는 조건을 새로 가정하지 마라.
4. '쓰면 안 되는 식'을 풀이에 사용하지 마라.
5. 계산을 새로 하지 말고, 검산된 결과를 이해하기 쉽게 설명만 하라.
6. 지원하지 않는 문제라면 수치 답을 만들지 말고 추가 조건이 필요하다고 말하라.
7. 마지막 확인 구역에서 LOCKED_FACTS_JSON의 answers 배열에 있는 모든 최종 답을 같은 숫자/단위로 다시 말하라.
8. 출력에는 LOCKED_FACTS_JSON 내용을 수정해서 쓰지 말고, 설명문만 작성하라.

[사용자 문제]
{problem_text}

[학생 풀이]
{student}

[설명 난이도]
{level}

[말투]
{style}

[잠긴 사실 요약]
- locked_hash: {locked.locked_hash}
- 문제 유형: {locked.problem_type}
- 선택 solver: {locked.selected_solver}
- solver_ok: {locked.solver_ok}
- 대표 최종 답: {locked.answer_display}\n- 복수 최종 답: {json.dumps(locked.answers, ensure_ascii=False)}
- 지원 불가 이유: {locked.unsupported_reason}

[LOCKED_FACTS_JSON]
{locked_json}

[추출된 값]
{knowns}

[사용 가능한 공식]
{equations}

[쓰면 안 되는 식]
{not_applicable}

[검산된 풀이 단계]
{steps}

[검산 포인트]
{checks}

[자주 하는 실수]
{mistakes}

출력 형식:
### 한눈에 보기
2~3문장으로 핵심 설명

### 왜 이 식을 쓰는가
좌표축/힘/에너지/운동학 관점 중 해당되는 이유 설명

### 단계별 설명
짧은 번호 목록

### 실수 방지
이번 문제에서 특히 조심할 점

### 마지막 확인
최종 답과 단위를 answer_display와 같은 숫자/단위로 다시 말하기
""".strip()
