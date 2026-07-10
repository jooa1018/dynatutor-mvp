"""차원 검증 — 답의 단위가 (a) 파싱되고 (b) 심볼의 기대 차원과 일치하는지.

'검증됨' 배지가 의미를 갖게 하는 첫 번째 층:
탄젠트 대신 각도를 내놓거나, 속도 자리에 가속도 단위를 붙이는 류의
구현 실수를 답이 사용자에게 나가기 전에 잡는다.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.physics_core.units import ureg, _unit  # noqa: F401 (shared registry)

Q_ = ureg.Quantity

# 심볼 → 기대 단위 예시(차원 비교 기준). 값이 ""이면 무차원.
EXPECTED_UNIT_BY_SYMBOL: dict[str, str] = {
    "t": "s",
    "R": "m", "h": "m", "s": "m", "x": "m", "d": "m", "r": "m",
    "v": "m/s", "vf": "m/s", "v_f": "m/s", "v0": "m/s",
    "v1": "m/s", "v2": "m/s", "v1'": "m/s", "v2'": "m/s",
    "vB": "m/s", "v_B": "m/s", "v_max": "m/s",
    "a": "m/s^2", "aB": "m/s^2", "a_B": "m/s^2",
    "T": "N",  # 이 코드베이스에서 T는 (대개) 장력. 문맥별 예외는 아래 참조.
    "F": "N", "N": "N", "f": "N",
    "W": "J", "E": "J", "KE": "J", "PE": "J",
    "J": "N*s",
    "tau": "N*m",
    "alpha": "rad/s^2",
    "omega": "rad/s",
    "I": "kg*m^2",
    "k": "N/m",
    "mu": "", "beta": "", "e": "",
    "theta": "deg",
    "v_r": "m/s", "v_theta": "m/s", "v_Bx": "m/s", "v_By": "m/s",
    "a_r": "m/s^2", "a_theta": "m/s^2", "a_t": "m/s^2", "a_n": "m/s^2",
    "a_C": "m/s^2", "a_Bx": "m/s^2", "a_By": "m/s^2",
    "omega_f": "rad/s",
}

# 심볼 의미가 문맥에 따라 다른 경우 (system_type, symbol) → 단위.
# 예: 진동 문제의 T는 장력(N)이 아니라 주기(s)다.
EXPECTED_UNIT_BY_CONTEXT: dict[tuple[str, str], str] = {
    ("spring_mass_vibration", "T"): "s",
    ("spring_mass_vibration", "f"): "Hz",
    ("fixed_axis_rotation", "T"): "s",  # 회전 주기로 쓰일 때
}

_SUPERSCRIPT_FIX = str.maketrans({"²": None, "³": None})


def _normalize_unit(unit: str | None) -> str:
    """solver가 쓰는 표기(², ·)를 파서가 아는 형태로."""
    if not unit:
        return ""
    u = unit.replace("²", "^2").replace("³", "^3").replace("·", "*").strip()
    return _unit(u)


@dataclass
class DimensionIssue:
    kind: str  # "error" | "warning"
    message: str


def _dims_of(unit: str):
    return Q_(1, _normalize_unit(unit)).dimensionality


def check_answer_dimension(symbol: str | None, unit: str | None, label: str = "", system_type: str | None = None) -> tuple[DimensionIssue | None, str | None]:
    """(issue, passed_check_description)"""
    name = symbol or label or "?"

    def _expected_unit() -> str | None:
        if system_type is not None and (system_type, symbol) in EXPECTED_UNIT_BY_CONTEXT:
            return EXPECTED_UNIT_BY_CONTEXT[(system_type, symbol)]
        return EXPECTED_UNIT_BY_SYMBOL.get(symbol or "")

    if unit is None or unit == "":
        expected = _expected_unit()
        if expected == "":
            return None, f"차원: {name} 무차원 ✓"
        # 단위 누락 자체는 answer_validators가 error 처리 — 여기선 검증 불가만 표시
        return DimensionIssue("warning", f"차원: {name}의 단위가 없어 차원 검증 불가"), None
    try:
        actual = _dims_of(unit)
    except Exception:
        return DimensionIssue("warning", f"차원: {name}의 단위 '{unit}'를 해석할 수 없음"), None

    expected_unit = _expected_unit()
    if expected_unit is None:
        return None, f"차원: {name} 단위 '{unit}' 해석 가능 ✓ (기대 차원 미등록 심볼)"
    try:
        expected = _dims_of(expected_unit) if expected_unit else Q_(1, "").dimensionality
    except Exception:
        return None, None
    if actual != expected:
        return DimensionIssue(
            "error",
            f"차원 불일치: {name} 단위 '{unit}' (기대: {expected_unit or '무차원'})",
        ), None
    return None, f"차원: {name} [{unit}] ✓"
