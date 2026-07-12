"""Central physical-domain and output plausibility checks."""
from __future__ import annotations

import math
from dataclasses import dataclass

C_LIGHT = 3.0e8

TIME_SYMBOLS = {"t"}
SPEED_SYMBOLS = {"v", "vf", "v_f", "v0", "v1", "v2", "v1'", "v2'", "vB", "v_B", "v_max", "v_t"}
LENGTH_SYMBOLS = {"R", "h", "s", "x", "d", "r"}
STRICT_POSITIVE_LENGTH_SYMBOLS = {"R", "r"}
MASS_SYMBOLS = {"m", "m1", "m2"}
INERTIA_SYMBOLS = {"I", "Ip"}
STIFFNESS_SYMBOLS = {"k"}
UNILATERAL_FORCE_SYMBOLS = {"T", "T1", "T2", "N", "N1", "N2"}
KE_SYMBOLS = {"KE", "K"}
MU_SYMBOLS = {"mu", "mu_k", "mu_s"}
RESTITUTION_SYMBOLS = {"e"}
ACCEL_SYMBOLS = {"a", "aB", "a_B"}


@dataclass
class PlausibilityIssue:
    kind: str
    message: str


def check_pool(pool: dict[str, float]) -> tuple[list[PlausibilityIssue], list[str]]:
    issues: list[PlausibilityIssue] = []
    passed: list[str] = []
    for sym, val in pool.items():
        if val is None:
            continue
        if not math.isfinite(val):
            issues.append(PlausibilityIssue("error", f"타당성: {sym} = {val} (비유한값)"))
            continue
        if sym in TIME_SYMBOLS:
            if val < 0:
                issues.append(PlausibilityIssue("error", f"타당성: 시간 {sym} = {val:.6g} < 0"))
            else:
                passed.append(f"타당성: {sym} ≥ 0 ✓")
        if sym in SPEED_SYMBOLS:
            if abs(val) > C_LIGHT:
                issues.append(PlausibilityIssue("error", f"타당성: 속도 {sym} = {val:.3g} m/s (광속 초과)"))
            elif abs(val) > 2.0e4:
                issues.append(PlausibilityIssue("warning", f"타당성: 속도 {sym} = {val:.3g} m/s (비정상적으로 큼)"))
        if sym in MASS_SYMBOLS and val <= 0:
            issues.append(PlausibilityIssue("error", f"타당성: 질량 {sym} = {val:.6g} ≤ 0"))
        if sym in INERTIA_SYMBOLS and val <= 0:
            issues.append(PlausibilityIssue("error", f"타당성: 관성모멘트 {sym} = {val:.6g} ≤ 0"))
        if sym in STIFFNESS_SYMBOLS and val <= 0:
            issues.append(PlausibilityIssue("error", f"타당성: 스프링 상수 {sym} = {val:.6g} ≤ 0"))
        if sym in UNILATERAL_FORCE_SYMBOLS and val < -1e-10:
            issues.append(PlausibilityIssue("error", f"타당성: 구속력 {sym} = {val:.6g} < 0 (접촉/줄 구속 불성립)"))
        if sym in KE_SYMBOLS and val < 0:
            issues.append(PlausibilityIssue("error", f"타당성: 운동에너지 {sym} = {val:.6g} < 0"))
        if sym in MU_SYMBOLS:
            if val < 0:
                issues.append(PlausibilityIssue("error", f"타당성: 마찰계수 {sym} = {val:.6g} < 0"))
            elif val > 2.0:
                issues.append(PlausibilityIssue("warning", f"타당성: 마찰계수 {sym} = {val:.6g} (이례적으로 큼)"))
        if sym in RESTITUTION_SYMBOLS and not 0 <= val <= 1:
            issues.append(PlausibilityIssue("error", f"타당성: 일반 충돌 반발계수 e = {val:.6g} (허용범위 0≤e≤1)"))
        if sym in STRICT_POSITIVE_LENGTH_SYMBOLS and val <= 0:
            issues.append(PlausibilityIssue("error", f"타당성: 반지름/거리 {sym} = {val:.6g} ≤ 0"))
        elif sym in LENGTH_SYMBOLS and val < 0:
            issues.append(PlausibilityIssue("warning", f"타당성: 길이 {sym} = {val:.6g} < 0 (방향 부호인지 확인)"))
        if sym in ACCEL_SYMBOLS and abs(val) > 1.0e6:
            issues.append(PlausibilityIssue("warning", f"타당성: 가속도 {sym} = {val:.3g} m/s² (비정상적으로 큼)"))
    return issues, passed


def check_knowns(knowns: dict, *, system_type: str | None = None) -> list[PlausibilityIssue]:
    issues: list[PlausibilityIssue] = []

    def value(key: str):
        q = knowns.get(key)
        return None if q is None or q.value is None else float(q.value)

    for key in ("m", "m1", "m2"):
        val = value(key)
        if val is not None and val <= 0:
            issues.append(PlausibilityIssue("error", f"타당성: 질량 {key} = {val} ≤ 0"))
    for key in ("I", "Ip", "k"):
        val = value(key)
        if val is not None and val <= 0:
            label = "관성모멘트" if key in {"I", "Ip"} else "스프링 상수"
            issues.append(PlausibilityIssue("error", f"타당성: {label} {key} = {val} ≤ 0"))
    for key in ("R", "Rp", "r"):
        val = value(key)
        if val is not None and val <= 0:
            issues.append(PlausibilityIssue("error", f"타당성: 반지름/거리 {key} = {val} ≤ 0"))
    duration = value("t")
    if duration is not None and duration < 0:
        issues.append(PlausibilityIssue("error", f"타당성: 작용시간 t = {duration} < 0"))
    restitution = value("e")
    if restitution is not None and not 0 <= restitution <= 1:
        issues.append(PlausibilityIssue("error", f"타당성: 일반 충돌 반발계수 e = {restitution} (허용범위 0≤e≤1)"))
    for key in ("mu", "mu_k", "mu_s"):
        val = value(key)
        if val is not None:
            if val < 0:
                issues.append(PlausibilityIssue("error", f"타당성: 마찰계수 {key} = {val} < 0"))
            elif val > 2.0:
                issues.append(PlausibilityIssue("warning", f"타당성: 마찰계수 {key} = {val} (이례적으로 큼)"))
    gravity = value("g")
    if gravity is not None and gravity <= 0:
        issues.append(PlausibilityIssue("error", f"타당성: 중력가속도 g = {gravity} ≤ 0"))
    elif gravity is not None and not 9.0 <= gravity <= 10.5:
        issues.append(PlausibilityIssue("warning", f"타당성: g = {gravity} m/s² (지표 기본값과 다름 — 의도인지 확인)"))

    theta = value("theta")
    if theta is not None and system_type == "banked_curve_no_friction" and not 0 < theta < 90:
        issues.append(PlausibilityIssue("error", f"타당성: 뱅크각 θ = {theta}° (0°<θ<90° 필요)"))
    if theta is not None and system_type in {"particle_on_incline", "pulley_incline_hanging"} and not 0 <= theta < 90:
        issues.append(PlausibilityIssue("error", f"타당성: 경사각 θ = {theta}° (0°≤θ<90° 필요)"))
    return issues
