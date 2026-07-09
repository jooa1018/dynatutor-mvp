from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

from engine.physics_core.vectors import Vec2, from_polar

_NUM = r"(-?\d+(?:,\d{3})*(?:\.\d+)?)"


@dataclass
class ParsedCoordinateData:
    values: dict[str, float]
    notes: list[str]

    def to_dict(self) -> dict:
        data = dict(self.values)
        if self.notes:
            data["parse_notes"] = list(self.notes)
        return data


def _float(s: str) -> float:
    return float(s.replace(",", ""))


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def signed_angular_direction(text: str) -> int:
    """Return +1 for CCW, -1 for clockwise, +1 default.

    Korean warning: "반시계방향" contains "시계방향", so check CCW first.
    """
    t = text.lower()
    c = _compact(text)
    if any(w in c for w in ["반시계방향", "반시계", "counterclockwise", "ccw", "ccw방향"]):
        return +1
    if any(w in c for w in ["시계방향", "clockwise", "cw", "cw방향"]):
        return -1
    return +1


def direction_to_angle_deg(direction_text: str) -> float | None:
    t = direction_text.lower()
    c = _compact(direction_text)
    # longer/compound expressions first
    if any(w in c for w in ["오른쪽위", "우상향"]):
        return 45.0
    if any(w in c for w in ["왼쪽위", "좌상향"]):
        return 135.0
    if any(w in c for w in ["왼쪽아래", "좌하향"]):
        return 225.0
    if any(w in c for w in ["오른쪽아래", "우하향"]):
        return -45.0
    if any(w in c for w in ["오른쪽", "우측", "+x", "x양의", "positive x", "right"]):
        return 0.0
    if any(w in c for w in ["왼쪽", "좌측", "-x", "x음의", "negative x", "left"]):
        return 180.0
    if any(w in c for w in ["위쪽", "위로", "상방", "+y", "y양의", "positive y", "upward", "up"]):
        return 90.0
    if any(w in c for w in ["아래쪽", "아래로", "하방", "-y", "y음의", "negative y", "downward", "down"]):
        return -90.0

    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:도|deg|degree)", direction_text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def vector_from_direction(length: float, direction_text: str) -> Vec2 | None:
    angle = direction_to_angle_deg(direction_text)
    if angle is None:
        return None
    return from_polar(length, angle)


def _first_vec_pair(patterns: list[str], text: str) -> tuple[Vec2, str] | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return Vec2(_float(m.group(1)), _float(m.group(2))), m.group(0)
    return None


def _directional_quantity(prefix_patterns: list[str], text: str, unit_pattern: str) -> tuple[float, str, str] | None:
    """Find directional scalar vectors.

    Supports:
    - A점 속도는 오른쪽 3m/s
    - A점 속도는 3m/s 오른쪽
    The parser intentionally stops at clause boundaries like "이고", comma,
    period, and semicolon so B-position phrases do not leak into vA/aA direction.
    """
    dir_words = r"(오른쪽|왼쪽|위쪽|아래쪽|위로|아래로|우측|좌측|상방|하방|right|left|upward|downward|up|down|\+x|-x|\+y|-y|\d+(?:\.\d+)?\s*(?:도|deg))"
    boundary = r"(?=이고|이며|그리고|,|\.|;|$)"
    for prefix in prefix_patterns:
        # Direction before magnitude.
        pat1 = rf"(?:{prefix})[^,\.;\n]{{0,25}}?(?P<dir>{dir_words})[^,\.;\n\d-]{{0,15}}?(?P<mag>{_NUM})\s*{unit_pattern}{boundary}"
        m = re.search(pat1, text, re.IGNORECASE)
        if m:
            return _float(m.group("mag")), m.group("dir"), m.group(0)

        # Magnitude before direction.
        pat2 = rf"(?:{prefix})[^,\.;\n\d-]{{0,25}}?(?P<mag>{_NUM})\s*{unit_pattern}[^,\.;\n]{{0,12}}?(?P<dir>{dir_words}){boundary}"
        m = re.search(pat2, text, re.IGNORECASE)
        if m:
            return _float(m.group("mag")), m.group("dir"), m.group(0)
    return None


def parse_coordinate_data_from_text(text: str) -> ParsedCoordinateData:
    values: dict[str, float] = {}
    notes: list[str] = []

    # Explicit vector pairs:
    # r_B/A=(0.3,0.4)m, rBA=(0.3, 0.4)m
    pair = _first_vec_pair([
        rf"(?:r\s*[_/]?\s*B\s*/?\s*A|rBA|r_BA|r_B/A)[^\(\d-]*\(\s*{_NUM}\s*,\s*{_NUM}\s*\)\s*m",
        rf"(?:B점?|점\s*B)[^\n.;]{{0,20}}?(?:A점?|점\s*A)[^\n.;]{{0,20}}?(?:대해|기준)[^\(\d-]*\(\s*{_NUM}\s*,\s*{_NUM}\s*\)\s*m",
    ], text)
    if pair:
        vec, src = pair
        values["rBAx"], values["rBAy"] = vec.x, vec.y
        notes.append(f"r_B/A explicit pair: {src}")

    # "B는 A에서 오른쪽으로 0.5m", "A에서 B까지 위쪽 0.4m"
    if "rBAx" not in values or "rBAy" not in values:
        patterns = [
            rf"(?:B(?:점)?(?:은|는)?\s*A(?:점)?에서|A(?:점)?에서\s*B(?:점)?까지|B(?:점)?(?:은|는)?\s*A(?:점)?로부터)[^\n.;]{{0,25}}?(오른쪽|왼쪽|위쪽|아래쪽|위로|아래로|우측|좌측|상방|하방|right|left|up|down|\d+(?:\.\d+)?\s*(?:도|deg))[^\d\n.;]{{0,15}}?{_NUM}\s*m",
            rf"(?:B(?:점)?(?:은|는)?\s*A(?:점)?에서|A(?:점)?에서\s*B(?:점)?까지|B(?:점)?(?:은|는)?\s*A(?:점)?로부터)[^\d\n.;]{{0,25}}?{_NUM}\s*m[^\n.;]{{0,15}}?(오른쪽|왼쪽|위쪽|아래쪽|위로|아래로|우측|좌측|상방|하방|right|left|up|down|\d+(?:\.\d+)?\s*(?:도|deg))",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                groups = m.groups()
                mag = None
                direction = None
                for g in groups:
                    if not g:
                        continue
                    try:
                        mag = _float(g)
                    except Exception:
                        if direction_to_angle_deg(g) is not None:
                            direction = g
                if mag is not None and direction is not None:
                    vec = vector_from_direction(mag, direction)
                    if vec:
                        values["rBAx"], values["rBAy"] = vec.x, vec.y
                        notes.append(f"r_B/A direction parsed: {m.group(0)}")
                        break

    # Directional vA / aA. These override scalar-only vA/aA.
    vA = _directional_quantity([r"A\s*점\s*속도", r"점\s*A\s*속도", r"vA|v_A"], text, r"(?:m/s|mps)")
    if vA:
        mag, direction, src = vA
        vec = vector_from_direction(mag, direction)
        if vec:
            values["vAx"], values["vAy"] = vec.x, vec.y
            notes.append(f"v_A direction parsed: {src}")

    aA = _directional_quantity([r"A\s*점\s*가속도", r"점\s*A\s*가속도", r"aA|a_A"], text, r"(?:m/s\^?2|m/s2|mps2)")
    if aA:
        mag, direction, src = aA
        vec = vector_from_direction(mag, direction)
        if vec:
            values["aAx"], values["aAy"] = vec.x, vec.y
            notes.append(f"a_A direction parsed: {src}")

    # Angular sign.
    sign = signed_angular_direction(text)
    values["angular_sign"] = float(sign)
    if sign < 0:
        notes.append("clockwise angular direction parsed as negative")
    elif any(w in _compact(text) for w in ["반시계", "counterclockwise", "ccw"]):
        notes.append("counterclockwise angular direction parsed as positive")

    return ParsedCoordinateData(values=values, notes=notes)
