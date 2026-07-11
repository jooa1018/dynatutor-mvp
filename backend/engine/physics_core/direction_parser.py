from __future__ import annotations

import re

DIRECTION_PATTERNS = {
    "same": ["같은 방향", "동일한 방향", "이동 방향으로", "힘 방향으로", "힘의 방향으로", "힘 방향을 따라", "힘의 방향을 따라", "나란히", "along the motion", "in the direction of motion", "밀었다", "당겼다", "끌었다", "이동시켰다", "이동시킨"],
    "opposite": ["반대 방향", "이동 방향 반대로", "거슬러", "마찰력", "저항력", "opposite"],
    "perpendicular": ["수직", "직각", "perpendicular", "normal to"],
}


def infer_angle_between_force_and_displacement(text: str) -> float | None:
    t = text.lower().replace(" ", "")
    spaced = text.lower()
    if any(p.replace(" ", "") in t for p in DIRECTION_PATTERNS["opposite"]):
        return 180.0
    if any(p.replace(" ", "") in t for p in DIRECTION_PATTERNS["same"]):
        return 0.0
    if any(p.replace(" ", "") in t for p in DIRECTION_PATTERNS["perpendicular"]):
        return 90.0

    # "이동 방향과 60도", "힘과 변위 사이 각도 60도" etc.
    patterns = [
        r"(?:이동\s*방향|변위|displacement|motion)[^.\n]{0,20}?(\d+(?:\.\d+)?)\s*(?:도|deg)",
        r"(?:사이\s*각|각도|angle)[^.\n]{0,20}?(\d+(?:\.\d+)?)\s*(?:도|deg)",
        r"(\d+(?:\.\d+)?)\s*(?:도|deg)[^.\n]{0,15}?(?:방향|각)",
    ]
    for pat in patterns:
        m = re.search(pat, spaced, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


def infer_direction_label(text: str) -> str | None:
    angle = infer_angle_between_force_and_displacement(text)
    if angle is None:
        return None
    if abs(angle) < 1e-9:
        return "same"
    if abs(angle - 180.0) < 1e-9:
        return "opposite"
    if abs(angle - 90.0) < 1e-9:
        return "perpendicular"
    return f"angle_{angle:g}_deg"



def infer_force_motion_relation(text: str) -> str | None:
    """Infer a 1-D force direction relative to the current motion."""

    compact = re.sub(r"\s+", "", (text or "").lower())
    if not any(token in compact for token in ("힘", "force")):
        return None

    opposite = (
        "운동방향과반대" in compact
        or "운동방향의반대" in compact
        or "속도방향과반대" in compact
        or "움직이는방향과반대" in compact
        or "againstthemotion" in compact
        or "oppositetothemotion" in compact
    )
    same = (
        "운동방향과같은" in compact
        or "운동방향과동일" in compact
        or "속도방향과같은" in compact
        or "움직이는방향과같은" in compact
        or "alongthemotion" in compact
        or "sameasthemotion" in compact
    )
    if opposite and not same:
        return "opposite"
    if same and not opposite:
        return "same"

    if any(
        phrase in compact
        for phrase in ("힘이왼쪽", "힘은왼쪽", "힘이-x", "forcetotheleft")
    ):
        return "negative"
    if any(
        phrase in compact
        for phrase in ("힘이오른쪽", "힘은오른쪽", "힘이+x", "forcetotheright")
    ):
        return "positive"
    return None


def resolve_impulse_force_component(
    force_value: float,
    relation: str | None,
    initial_velocity: float | None,
    *,
    magnitude_only: bool,
) -> float | None:
    """Resolve the signed 1-D force component used by impulse-momentum."""

    force = float(force_value)
    if force < 0:
        return force
    if relation == "positive":
        return abs(force)
    if relation == "negative":
        return -abs(force)
    if relation in {"same", "opposite"}:
        if initial_velocity is None or abs(float(initial_velocity)) <= 1e-12:
            return None
        motion_sign = 1.0 if float(initial_velocity) > 0 else -1.0
        relation_sign = 1.0 if relation == "same" else -1.0
        return abs(force) * motion_sign * relation_sign
    if magnitude_only:
        return abs(force)
    return None
