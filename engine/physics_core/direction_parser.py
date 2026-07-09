from __future__ import annotations

import re

DIRECTION_PATTERNS = {
    "same": ["같은 방향", "이동 방향으로", "힘 방향으로", "힘의 방향으로", "나란히", "along the motion", "in the direction of motion", "밀었다", "당겼다", "끌었다", "이동시켰다", "이동시킨"],
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
