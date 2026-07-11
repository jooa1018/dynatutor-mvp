from __future__ import annotations

from typing import Any


REST_PHRASES = (
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


def explicitly_starts_from_rest(problem_or_text: Any) -> bool:
    text = (
        getattr(problem_or_text, "raw_text", "")
        if not isinstance(problem_or_text, str)
        else problem_or_text
    )
    normalized = (text or "").lower()
    return any(phrase in normalized for phrase in REST_PHRASES)


ANGULAR_REST_PHRASES = (
    "처음에는 회전하지",
    "초기에는 회전하지",
    "처음에는 돌지 않",
    "초기에는 돌지 않",
    "회전 정지 상태",
    "starts from angular rest",
    "initially not rotating",
)


def explicitly_starts_from_angular_rest(problem_or_text: Any) -> bool:
    text = (
        getattr(problem_or_text, "raw_text", "")
        if not isinstance(problem_or_text, str)
        else problem_or_text
    )
    normalized = (text or "").lower()
    if any(phrase in normalized for phrase in ANGULAR_REST_PHRASES):
        return True
    has_rotation_context = any(
        token in normalized
        for token in ("회전", "각속도", "각가속도", "omega", "alpha", "ω", "α")
    )
    return has_rotation_context and explicitly_starts_from_rest(normalized)
