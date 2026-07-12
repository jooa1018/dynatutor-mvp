"""결과 게이트 — ok=False 강등이 일어나는 유일한 장소.

Phase 28~31에서 강등 정책이 세 갈래(필수 answer 누락, 물리 검증 실패,
출처 의심)로 services.py 안에 분산되어 있었다. 정책이 한 곳에 있어야
우선순위·문구·의미가 어긋나지 않는다.

정책:
  - response.verification.errors 가 하나라도 있으면 ok=False, passed=False.
  - unsupported_reason 은 error 종류의 우선순위로 결정한다
    (필수 answer 누락 > 출처 의심 > 물리 검증 일반).
  - solver 자체가 이미 ok=False 로 실패한 경우(예: missing_info)의
    기존 reason 은 보존한다 — 게이트는 '성공 주장'을 끌어내리는 장치지
    실패 사유를 덮어쓰는 장치가 아니다.
"""
from __future__ import annotations

# (에러 접두어, 사용자에게 보여줄 보류 사유) — 위가 우선.
_REASON_RULES: list[tuple[str, str]] = [
    ("answer consistency", "필수 정답 항목이 누락되었습니다."),
    ("출처 의심", "문제 본문과 무관해 보이는 문장에서 추출된 값이 계산에 쓰일 수 있어 답을 보류합니다. 해당 문장을 빼고 다시 시도해 주세요."),
]
_DEFAULT_REASON = "물리 검증(차원·타당성·역대입)에 실패했습니다. 계산 결과를 신뢰할 수 없어 답을 보류합니다."


def gate_decision(errors: list[str]) -> tuple[bool, str | None]:
    """(강등 여부, 보류 사유). 순수 함수 — 단위 테스트 대상."""
    if not errors:
        return False, None
    for prefix, reason in _REASON_RULES:
        if any(e.startswith(prefix) or f" {prefix}" in e for e in errors):
            return True, reason
    return True, _DEFAULT_REASON


def apply_result_gate(response) -> None:
    """SolveResponse 를 검사해 필요 시 강등. services.solve_problem 의 유일한 강등 지점."""
    errors = list(getattr(response.verification, "errors", []) or [])
    demote, reason = gate_decision(errors)
    if not demote:
        return
    was_ok = bool(response.ok)
    response.ok = False
    response.verification.passed = False
    # 검증에 실패한 숫자는 일반 응답 계약에서 제거한다. 디버깅 후보값을
    # 사용자용 answer 필드에 남기면 UI나 다른 소비자가 오답을 재사용할 수 있다.
    response.answer = None
    response.answers = []
    # 성공 주장을 끌어내리는 경우에만 사유를 게이트가 결정한다.
    # solver 가 이미 실패 사유를 제시했다면 보존.
    if was_ok or not response.unsupported_reason:
        response.unsupported_reason = reason
