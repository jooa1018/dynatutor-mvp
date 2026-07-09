"""물리적 타당성 검증.

원칙: hard error는 물리적으로 불가능한 것만 (시간≤0, 비유한값, 광속 초과,
질량≤0, 음의 마찰계수, 음의 운동에너지). 특이하지만 가능한 값(μ>2,
초대형 가속도)은 warning — 맞는 답을 절대 죽이지 않기 위해서다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

C_LIGHT = 3.0e8

TIME_SYMBOLS = {"t"}
SPEED_SYMBOLS = {"v", "vf", "v_f", "v0", "v1", "v2", "v1'", "v2'", "vB", "v_B", "v_max"}
LENGTH_SYMBOLS = {"R", "h", "s", "x", "d", "r"}
KE_SYMBOLS = {"KE"}
MU_SYMBOLS = {"mu"}
ACCEL_SYMBOLS = {"a", "aB", "a_B"}


@dataclass
class PlausibilityIssue:
    kind: str  # "error" | "warning"
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
            if val <= 0:
                issues.append(PlausibilityIssue("error", f"타당성: 시간 {sym} = {val:.6g} ≤ 0"))
            else:
                passed.append(f"타당성: {sym} > 0 ✓")
        if sym in SPEED_SYMBOLS:
            if abs(val) > C_LIGHT:
                issues.append(PlausibilityIssue("error", f"타당성: 속도 {sym} = {val:.3g} m/s (광속 초과)"))
            elif abs(val) > 2.0e4:
                issues.append(PlausibilityIssue("warning", f"타당성: 속도 {sym} = {val:.3g} m/s (비정상적으로 큼)"))
        if sym in KE_SYMBOLS and val < 0:
            issues.append(PlausibilityIssue("error", f"타당성: 운동에너지 {sym} = {val:.6g} < 0"))
        if sym in MU_SYMBOLS:
            if val < 0:
                issues.append(PlausibilityIssue("error", f"타당성: 마찰계수 {sym} = {val:.6g} < 0"))
            elif val > 2.0:
                issues.append(PlausibilityIssue("warning", f"타당성: 마찰계수 {sym} = {val:.6g} (이례적으로 큼)"))
        if sym in LENGTH_SYMBOLS and val < 0:
            issues.append(PlausibilityIssue("warning", f"타당성: 길이 {sym} = {val:.6g} < 0 (방향 부호인지 확인)"))
        if sym in ACCEL_SYMBOLS and abs(val) > 1.0e6:
            issues.append(PlausibilityIssue("warning", f"타당성: 가속도 {sym} = {val:.3g} m/s² (비정상적으로 큼)"))
    return issues, passed


def check_knowns(knowns: dict) -> list[PlausibilityIssue]:
    issues: list[PlausibilityIssue] = []
    for key in ("m", "m1", "m2"):
        q = knowns.get(key)
        if q is not None and q.value is not None and q.value <= 0:
            issues.append(PlausibilityIssue("error", f"타당성: 질량 {key} = {q.value} ≤ 0"))
    for key in ("mu", "mu_k", "mu_s"):
        q = knowns.get(key)
        if q is not None and q.value is not None:
            if q.value < 0:
                issues.append(PlausibilityIssue("error", f"타당성: 마찰계수 {key} = {q.value} < 0"))
            elif q.value > 2.0:
                issues.append(PlausibilityIssue("warning", f"타당성: 마찰계수 {key} = {q.value} (이례적으로 큼)"))
    g = knowns.get("g")
    if g is not None and g.value is not None and not (9.0 <= float(g.value) <= 10.5):
        issues.append(PlausibilityIssue("warning", f"타당성: g = {g.value} m/s² (지표 기본값과 다름 — 의도인지 확인)"))
    return issues
