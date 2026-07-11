from __future__ import annotations

import re

# Shared raw unit grammar used by both quantity extraction and explicit-occurrence
# conflict scanning. Keep separators optional so Korean textbook/ASCII variants are
# semantically identical without normalizing the source text first.
TORQUE_UNIT_PATTERN = r"N\s*(?:[·*]\s*)?m"
MOMENT_OF_INERTIA_UNIT_PATTERN = r"kg\s*(?:[·*]\s*)?m\s*(?:\^\s*)?(?:2|²)"

LABELED_UNIT_PATTERN = (
    rf"(?:{MOMENT_OF_INERTIA_UNIT_PATTERN}|"
    r"km\s*/\s*h|km/h|cm/s(?:(?:\^?2|2|²))?|"
    r"m/s(?:(?:\^?2|2|²))?|rad/s(?:(?:\^?2|2|²))?|"
    rf"{TORQUE_UNIT_PATTERN}|N/m|N|J|kg|"
    r"g(?![A-Za-z0-9_/])|cm|m|s|deg|도|°|Hz)"
)


def compact_unit(unit: str | None) -> str:
    if not unit:
        return ""
    return (
        re.sub(r"\s+", "", unit)
        .replace("·", "*")
        .replace("²", "^2")
    )


def normalize_labeled_value(
    value: float,
    unit: str | None,
) -> tuple[float, str | None]:
    normalized_unit = compact_unit(unit).lower()
    if normalized_unit == "km/h":
        return value / 3.6, "m/s"
    if normalized_unit in {"cm/s^2", "cm/s2"}:
        return value / 100.0, "m/s^2"
    if normalized_unit == "cm":
        return value / 100.0, "m"
    if normalized_unit == "g":
        return value / 1000.0, "kg"
    if normalized_unit in {"도", "°", "deg"}:
        return value, "deg"
    if normalized_unit in {"m/s2", "m/s^2"}:
        return value, "m/s^2"
    if normalized_unit in {"rad/s2", "rad/s^2"}:
        return value, "rad/s^2"
    if re.fullmatch(r"kg\*?m\^?2", normalized_unit):
        return value, "kg*m^2"
    if re.fullmatch(r"n\*?m", normalized_unit):
        return value, "N*m"
    return value, compact_unit(unit) if unit else None
