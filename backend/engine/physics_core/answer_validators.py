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
    "minimum_speed": {"v_min"},
    "initial_velocity": {"v0", "v_i"},
    "final_velocity": {"vf", "v_f", "v", "vB", "v_B", "v_min", "v_max", "v_r", "v_θ"},
    "acceleration": {"a", "aB", "a_B", "aC", "a_C", "a_r", "a_θ"},
    "tension": {"T", "T1", "T2"},
    "force": {"F", "F_net", "T", "N"},
    "friction_force": {"f", "f_k", "f_s", "f_s,max", "F_f"},
    "normal_force": {"N", "N1", "N2"},
    "mass": {"m"},
    "work": {"W"},
    "impulse": {"J"},
    "kinetic_energy": {"K", "KE", "E_k"},
    "potential_energy": {"U", "PE", "E_p"},
    "elastic_energy": {"E", "U_s", "E_s"},
    "period": {"T"},
    "frequency": {"f"},
    "angular_frequency": {"omega_n", "omega", "ω_n", "ω"},
    "post_collision_velocity": {"v1'", "v2'", "v_f"},
    "v1_after": {"v1'", "v_f"},
    "v2_after": {"v2'", "v_f"},
    "angular_velocity": {"omega", "ω"},
    "angular_acceleration": {"alpha", "α"},
    "tangential_velocity": {"v_t"},
    "centripetal_acceleration": {"a_c"},
}



SEMANTIC_KEY_REQUIRED = {"period", "tension", "frequency", "friction_force"}
AMBIGUOUS_OUTPUT_SYMBOLS = {"T", "f"}
OUTPUT_KEY_COMPATIBILITY: dict[str, set[str]] = {
    "force": {"force", "tension", "friction_force", "normal_force"},
    "distance": {"distance", "range"},
    "final_velocity": {"final_velocity", "minimum_speed", "tangential_velocity"},
    "post_collision_velocity": {"post_collision_velocity", "v1_after", "v2_after"},
}


REQUESTED_OUTPUT_LABEL_HINTS: dict[str, set[str]] = {
    "time": {"시간", "비행"},
    "range": {"수평거리", "사거리"},
    "distance": {"거리", "변위"},
    "max_height": {"최대높이", "높이"},
    "minimum_speed": {"최소 속도", "최소속도"},
    "initial_velocity": {"초기속도", "초속도"},
    "final_velocity": {"최종속도", "속도", "속력", "v_", "|v|"},
    "acceleration": {"가속도"},
    "tension": {"장력"},
    "force": {"힘", "알짜힘", "합력"},
    "friction_force": {"마찰력", "정지마찰력", "운동마찰력", "최대 정지마찰력"},
    "normal_force": {"수직항력", "법선력"},
    "mass": {"질량"},
    "work": {"일"},
    "impulse": {"충격량"},
    "kinetic_energy": {"운동에너지"},
    "potential_energy": {"위치에너지", "퍼텐셜 에너지"},
    "elastic_energy": {"탄성 퍼텐셜 에너지", "탄성에너지", "저장 에너지"},
    "period": {"주기"},
    "frequency": {"진동수", "주파수"},
    "angular_frequency": {"고유각진동수", "각진동수"},
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


def _has_requested_answer(
    req: str,
    answers: list[Any],
    symbols: set[str],
    labels: set[str],
) -> bool:
    accepted_keys = {req} | OUTPUT_KEY_COMPATIBILITY.get(req, set())
    for answer in answers:
        output_key = getattr(answer, "output_key", None)
        if output_key in accepted_keys:
            return True

    expected = REQUESTED_OUTPUT_SYMBOLS.get(req, set())
    # T and f are semantic collisions. They are never accepted without an
    # explicit output_key, regardless of a matching human-readable label.
    unambiguous_symbols = symbols - AMBIGUOUS_OUTPUT_SYMBOLS
    if unambiguous_symbols & expected:
        return True
    if req in SEMANTIC_KEY_REQUIRED:
        return False

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
            output_key = getattr(ans, "output_key", None)
            if output_key is not None and output_key not in REQUESTED_OUTPUT_SYMBOLS:
                errors.append(
                    f"answers[{idx}]에 미등록 output_key `{output_key}`가 있습니다."
                )
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
                errors.append(f"requested_outputs에 미등록 출력 \u0060{req}\u0060가 있습니다.")
                continue
            if not _has_requested_answer(req, answers, symbols, labels):
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
