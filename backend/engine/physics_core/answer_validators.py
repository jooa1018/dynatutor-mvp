from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnswerValidationReport:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


REQUESTED_OUTPUT_SYMBOLS: dict[str, set[str]] = {
    "time": {"t"},
    "range": {"R"},
    "distance": {"R", "s", "x"},
    "max_height": {"H"},
    "final_velocity": {"vf", "v_f", "v", "vB", "v_B", "v_min", "v_max", "v_r", "v_θ"},
    "acceleration": {"a", "aB", "a_B", "aC", "a_C", "a_r", "a_θ"},
    "tension": {"T", "T1", "T2"},
    "force": {"F", "F_net"},
    "mass": {"m"},
    "work": {"W"},
    "post_collision_velocity": {"v1'", "v2'", "v_f"},
    "v1_after": {"v1'", "v_f"},
    "v2_after": {"v2'", "v_f"},
    "angular_velocity": {"omega", "ω"},
    "angular_acceleration": {"alpha", "α"},
    "tangential_velocity": {"v_t"},
    "centripetal_acceleration": {"a_c"},
}


REQUESTED_OUTPUT_LABEL_HINTS: dict[str, set[str]] = {
    "time": {"시간", "비행"},
    "range": {"수평거리", "사거리"},
    "distance": {"거리", "변위"},
    "max_height": {"최대높이", "높이"},
    "final_velocity": {"최종속도", "속도", "속력", "v_", "|v|"},
    "acceleration": {"가속도"},
    "tension": {"장력"},
    "force": {"힘", "알짜힘", "합력"},
    "mass": {"질량"},
    "work": {"일"},
    "angular_velocity": {"각속도"},
    "angular_acceleration": {"각가속도"},
    "tangential_velocity": {"접선속도"},
    "centripetal_acceleration": {"구심가속도"},
}


def _num_in_display(numeric: float | None, display: str | None) -> bool:
    if numeric is None or not display:
        return True
    nums: list[float] = []
    for token in re.findall(r"[-+]?\d+(?:\.\d+)?", display):
        try:
            nums.append(float(token))
        except ValueError:
            pass
    return any(math.isclose(float(numeric), x, rel_tol=2e-3, abs_tol=2e-3) for x in nums)


def _has_requested_answer(req: str, symbols: set[str], labels: set[str]) -> bool:
    expected = REQUESTED_OUTPUT_SYMBOLS.get(req, set())
    if symbols & expected:
        return True
    label_hints = REQUESTED_OUTPUT_LABEL_HINTS.get(req, set())
    return any(hint in label for hint in label_hints for label in labels)


def validate_answer_consistency(*, ok: bool, answer: Any | None, answers: list[Any], requested_outputs: list[str] | None = None) -> AnswerValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    requested_outputs = requested_outputs or []

    if ok and not answer and not answers:
        errors.append("ok=True인데 answer와 answers가 모두 비어 있습니다.")

    if ok and answer and not getattr(answer, "unit", None):
        errors.append("primary answer에 unit이 없습니다.")

    if ok and not answers and answer:
        errors.append("solver가 계산했다고 주장하지만 answers가 비어 있습니다.")

    if answers:
        first = answers[0]
        if answer and getattr(answer, "display", None) and getattr(first, "display", None):
            if getattr(answer, "numeric", None) is not None and getattr(first, "numeric", None) is not None:
                if not math.isclose(float(answer.numeric), float(first.numeric), rel_tol=2e-3, abs_tol=2e-3):
                    warnings.append("대표 answer.numeric이 answers[0].numeric과 다릅니다.")
        for idx, ans in enumerate(answers):
            role = getattr(ans, "role", None)
            numeric = getattr(ans, "numeric", None)
            display = getattr(ans, "display", None)
            if ok and numeric is None and display:
                errors.append(f"answers[{idx}]에 display만 있고 numeric 값이 없습니다.")
            if role == "primary":
                if ok and not getattr(ans, "unit", None):
                    errors.append(f"primary answers[{idx}]에 unit이 없습니다.")
                if not display:
                    errors.append(f"primary answers[{idx}]에 display가 없습니다.")
            if not _num_in_display(numeric, display):
                warnings.append(f"answers[{idx}] numeric과 display의 숫자가 일치하지 않아 보입니다.")

    symbols = {str(getattr(ans, "symbol", "")) for ans in answers if getattr(ans, "symbol", None)}
    labels = {str(getattr(ans, "label", "")) for ans in answers if getattr(ans, "label", None)}
    for ans in answers:
        display = str(getattr(ans, "display", "") or "")
        if display:
            labels.add(display)
        match = re.match(r"\s*([A-Za-z_]+|[a-zA-Z][a-zA-Z_]*|[ωα])\s*=", display)
        if match:
            symbols.add(match.group(1))
    if ok:
        for req in requested_outputs:
            if req not in REQUESTED_OUTPUT_SYMBOLS:
                continue
            if not _has_requested_answer(req, symbols, labels):
                expected = sorted(REQUESTED_OUTPUT_SYMBOLS.get(req, set()))
                got = sorted(symbols)
                errors.append(f"requested_outputs `{req}`에 해당하는 answer가 없습니다. expected={expected}, got={got}, labels={sorted(labels)}")

    return AnswerValidationReport(passed=not errors, errors=errors, warnings=warnings)


def validate_solve_response(response: Any) -> AnswerValidationReport:
    diagnosis = getattr(response, "diagnosis", None)
    canonical = getattr(diagnosis, "canonical", None)
    requested = getattr(canonical, "requested_outputs", []) if canonical is not None else []
    return validate_answer_consistency(
        ok=bool(getattr(response, "ok", False)),
        answer=getattr(response, "answer", None),
        answers=list(getattr(response, "answers", []) or []),
        requested_outputs=requested,
    )
