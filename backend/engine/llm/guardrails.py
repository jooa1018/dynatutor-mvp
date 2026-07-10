from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.llm import LockedFacts
from app.schemas.solution import SolveResponse

_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
_UNIT_NEAR_RE = re.compile(r"[-+]?\d+(?:\.\d+)?\s*(?:m/s²|m/s\^2|m/s2|m/s|N·s|N\*s|N|J|rad/s²|rad/s\^2|rad/s2|rad/s|kg|m|s|Hz|deg|도|m/s\^2|m/s)")
_HEADING_FINAL_RE = re.compile(r"(?:최종\s*답|정답|마지막\s*확인|answer)", re.IGNORECASE)


def _numbers_from_text(text: str) -> list[float]:
    out: list[float] = []
    for match in _NUMBER_RE.findall(text or ""):
        try:
            out.append(float(match))
        except ValueError:
            pass
    return out


def _close_to_any(value: float, candidates: list[float], tol: float = 1e-2) -> bool:
    return any(abs(value - c) <= tol * max(1.0, abs(c)) for c in candidates)


def _normalize_math(text: str) -> str:
    s = (text or "").lower()
    replacements = {
        "×": "*",
        "·": "*",
        "−": "-",
        "—": "-",
        "–": "-",
        " ": "",
        "\n": "",
        "\\": "",
        "^": "",
        "²": "2",
        "ₙ": "n",
        "θ": "theta",
        "ω": "omega",
        "α": "alpha",
        "μ": "mu",
        "Δ": "delta",
        "Σ": "sum",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    return s


def _facts_payload_for_hash(locked: LockedFacts) -> dict[str, Any]:
    return {
        "problem_type": locked.problem_type,
        "selected_solver": locked.selected_solver,
        "solver_ok": locked.solver_ok,
        "answer_display": locked.answer_display,
        "answer_numbers": locked.answer_numbers,
        "answer_unit": locked.answer_unit,
        "answers": locked.answers,
        "unsupported_reason": locked.unsupported_reason,
        "equations": locked.equations,
        "not_applicable_equations": locked.not_applicable_equations,
        "known_values": locked.known_values,
        "allowed_numbers": locked.allowed_numbers,
    }


def compute_locked_hash(locked: LockedFacts) -> str:
    payload = json.dumps(_facts_payload_for_hash(locked), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_locked_facts(solution: SolveResponse) -> LockedFacts:
    canonical = solution.diagnosis.canonical
    known_values: dict[str, str] = {}
    known_numbers: list[float] = []
    for key, quantity in canonical.knowns.items():
        if quantity.value is None:
            continue
        unit = f" {quantity.unit}" if quantity.unit else ""
        known_values[key] = f"{quantity.value:g}{unit}"
        known_numbers.append(float(quantity.value))

    equations = []
    for eq in solution.equation_sheet or solution.diagnosis.applicable_equations:
        if eq not in equations:
            equations.append(eq)

    not_applicable = []
    for eq in solution.diagnosis.not_applicable_equations:
        if eq not in not_applicable:
            not_applicable.append(eq)

    steps = []
    for s in solution.steps[:10]:
        if s.math:
            steps.append(f"{s.title}: {s.math}")
        else:
            steps.append(s.title)

    answer_display = solution.answer.display if solution.answer else None
    answer_numbers = _numbers_from_text(answer_display or "")
    answer_unit = solution.answer.unit if solution.answer else None
    answer_items = []
    for item in solution.answers or []:
        payload = {
            "label": item.label,
            "symbol": item.symbol,
            "numeric": item.numeric,
            "unit": item.unit,
            "display": item.display,
            "role": item.role,
        }
        answer_items.append(payload)
        if item.numeric is not None:
            answer_numbers.append(float(item.numeric))

    allowed_numbers = []
    allowed_numbers.extend(known_numbers)
    allowed_numbers.extend(answer_numbers)
    for step in steps:
        allowed_numbers.extend(_numbers_from_text(step))
    for eq in equations:
        allowed_numbers.extend(_numbers_from_text(eq))
    for check in solution.verification.checks or []:
        allowed_numbers.extend(_numbers_from_text(check))
    # Common physical/math constants and safe explanation numbers.
    allowed_numbers.extend([0, 1, 2, 3, 4, 5, 9.8, 9.81, 10, 30, 45, 60, 90, 180, 360])

    # Deduplicate while preserving approximate values.
    dedup: list[float] = []
    for n in allowed_numbers:
        if not _close_to_any(n, dedup, tol=1e-9):
            dedup.append(float(n))

    locked = LockedFacts(
        problem_type=canonical.system_type,
        selected_solver=solution.diagnosis.selected_solver,
        solver_ok=solution.ok,
        answer_display=answer_display,
        answer_numbers=answer_numbers,
        answer_unit=answer_unit,
        answers=answer_items,
        unsupported_reason=solution.unsupported_reason,
        equations=equations[:12],
        not_applicable_equations=not_applicable[:12],
        checks=(solution.verification.checks or [])[:10],
        known_values=known_values,
        allowed_numbers=dedup[:80],
        steps=steps,
    )
    locked.locked_hash = compute_locked_hash(locked)
    return locked


@dataclass
class IntegrityResult:
    passed: bool
    warnings: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def _detect_banned_equations(text: str, locked: LockedFacts) -> list[str]:
    normalized_text = _normalize_math(text)
    hits: list[str] = []
    for eq in locked.not_applicable_equations:
        norm = _normalize_math(eq)
        # Skip very short labels, but catch recognizable formula fragments.
        if len(norm) >= 5 and norm in normalized_text:
            hits.append(eq)
    return hits


def _contains_exactish_answer(text: str, locked: LockedFacts) -> bool:
    if not locked.answer_display:
        return True
    text_numbers = _numbers_from_text(text)
    if not locked.answer_numbers:
        return locked.answer_display in text
    return all(_close_to_any(n, text_numbers, tol=2e-2) for n in locked.answer_numbers[:3])


def _has_final_section_or_answer_phrase(text: str) -> bool:
    return bool(_HEADING_FINAL_RE.search(text or ""))


def _detect_unsupported_hallucination(text: str, locked: LockedFacts) -> list[str]:
    warnings: list[str] = []
    if locked.solver_ok:
        return warnings
    if re.search(r"(최종\s*답|정답)\s*(은|:|=)", text or "") and _UNIT_NEAR_RE.search(text or ""):
        warnings.append("지원하지 않는 문제인데 LLM 설명이 최종 수치 답처럼 보이는 값을 제시했습니다.")
    if any(p in (text or "") for p in ["계산하면", "따라서 답은", "정답은"]):
        warnings.append("지원하지 않는 문제에서는 계산 결론 대신 추가 조건을 요구해야 합니다.")
    return warnings


def validate_llm_explanation(text: str, locked: LockedFacts) -> IntegrityResult:
    """Deterministic guardrail for LLM prose.

    This does not prove the prose is pedagogically perfect. It blocks common
    dangerous failures:
    - final numeric answer changed or omitted
    - new unapproved numeric values introduced
    - not-applicable formula used
    - unsupported problem receives fabricated final answer
    - explicit language about changing solver facts
    """
    warnings: list[str] = []
    report: dict[str, Any] = {
        "locked_hash": locked.locked_hash,
        "checked_answer_numbers": locked.answer_numbers,
        "checked_known_values": locked.known_values,
        "new_numbers": [],
        "banned_equation_hits": [],
        "unsupported_checks": [],
    }

    text = text or ""

    if locked.solver_ok and locked.answer_display:
        if not _contains_exactish_answer(text, locked):
            warnings.append(f"LLM 설명에서 잠긴 최종답 `{locked.answer_display}`의 숫자를 명확히 찾지 못했습니다.")
        for ans in locked.answers or []:
            num = ans.get("numeric")
            unit = ans.get("unit")
            label = ans.get("label") or ans.get("symbol") or "answer"
            if num is not None and not _close_to_any(float(num), _numbers_from_text(text), tol=2e-2):
                warnings.append(f"LLM 설명에서 잠긴 복수 정답 `{label}` 숫자를 찾지 못했습니다.")
            if unit and unit not in text and str(unit).replace("^2", "²") not in text:
                warnings.append(f"LLM 설명에서 잠긴 복수 정답 `{label}` 단위 `{unit}`를 찾지 못했습니다.")
        if not _has_final_section_or_answer_phrase(text):
            warnings.append("LLM 설명에 최종 답을 다시 확인하는 구역/문장이 없습니다.")
        if locked.answer_unit and locked.answer_unit not in text and (locked.answer_display or "").split()[-1] not in text:
            warnings.append(f"LLM 설명에서 잠긴 단위 `{locked.answer_unit}`를 찾지 못했습니다.")

    # Known values and final values are the only problem-specific numeric facts
    # LLM may repeat. Step numbers and common constants are allowed.
    allowed = list(locked.allowed_numbers or [])
    suspicious: list[float] = []
    for n in _numbers_from_text(text):
        if abs(n) <= 10 and float(n).is_integer():
            continue
        if not _close_to_any(n, allowed, tol=2e-2):
            suspicious.append(n)
    if suspicious:
        first = ", ".join(f"{x:g}" for x in suspicious[:6])
        warnings.append(f"잠긴 풀이에 없던 숫자가 LLM 설명에 등장했습니다: {first}")
        report["new_numbers"] = suspicious[:20]

    banned_hits = _detect_banned_equations(text, locked)
    if banned_hits:
        warnings.append("LLM 설명이 '쓰면 안 되는 식' 또는 부적절한 공식을 사용했습니다: " + "; ".join(banned_hits[:3]))
        report["banned_equation_hits"] = banned_hits[:10]

    banned_phrases = [
        "정답을 수정",
        "계산을 바꾸",
        "다른 답",
        "새로운 조건을 가정",
        "문제에 없지만",
        "임의로 가정",
        "대신 다음 답",
    ]
    for phrase in banned_phrases:
        if phrase in text:
            warnings.append(f"계산 변경/새 조건 가정처럼 보이는 표현이 있습니다: {phrase}")

    unsupported_warnings = _detect_unsupported_hallucination(text, locked)
    if unsupported_warnings:
        warnings.extend(unsupported_warnings)
        report["unsupported_checks"] = unsupported_warnings

    return IntegrityResult(passed=not warnings, warnings=warnings, report=report)
