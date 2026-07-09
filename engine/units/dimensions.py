from __future__ import annotations

from dataclasses import dataclass
from engine.models import VerificationReport

# Minimal dimension tags for an educational checker.
# This is not a full unit algebra package; it deliberately checks the common
# outputs produced by the Phase 3 solvers.
_EXPECTED_BY_UNKNOWN = {
    "acceleration": ("m/s²", {"m/s^2", "m/s²"}),
    "velocity": ("m/s", {"m/s"}),
    "minimum_speed": ("m/s", {"m/s"}),
    "distance": ("m", {"m"}),
    "time": ("s", {"s"}),
    "work": ("J", {"J", "N*m"}),
    "impulse": ("N·s", {"N*s", "kg*m/s"}),
    "angular_acceleration": ("rad/s²", {"rad/s^2", "rad/s²"}),
    "angular_frequency": ("rad/s", {"rad/s"}),
    "period": ("s", {"s"}),
    "frequency": ("Hz", {"Hz", "1/s"}),
}


def attach_unit_check(report: VerificationReport, *, expected_unknown: str | None, actual_unit: str | None) -> VerificationReport:
    if not expected_unknown or not actual_unit:
        report.dimension_summary = "단위 검산: 출력 단위 정보가 부족하여 엄격 검사는 생략했습니다."
        report.warnings.append(report.dimension_summary)
        return report
    expected = _EXPECTED_BY_UNKNOWN.get(expected_unknown)
    if not expected:
        report.dimension_summary = "단위 검산: 이 미지수 유형은 아직 간단 검산 목록에 없습니다."
        report.checks.append(report.dimension_summary)
        return report
    label, allowed = expected
    if actual_unit in allowed:
        report.dimension_summary = f"단위 검산 통과: {expected_unknown}의 단위는 {label} 계열이어야 하고, 결과 단위 {actual_unit}가 일치합니다."
        report.checks.append(report.dimension_summary)
    else:
        report.dimension_summary = f"단위 검산 경고: {expected_unknown}의 예상 단위는 {label} 계열인데, 결과 단위가 {actual_unit}입니다."
        report.warnings.append(report.dimension_summary)
        report.passed = False
    return report


def unit_hint_for_equation(equation_name: str) -> str:
    hints = {
        "F=ma": "N = kg·m/s² 이므로 힘과 질량×가속도의 단위가 같습니다.",
        "work": "J = N·m 이므로 힘×거리의 단위가 일과 같습니다.",
        "rotational_dynamics": "N·m = kg·m²·rad/s² 로, τ=Iα의 양변 차원이 맞습니다. rad는 무차원처럼 취급합니다.",
        "spring_energy": "J = N/m·m² = N·m 이므로 1/2kx²는 에너지 단위입니다.",
        "vibration": "k/m의 단위는 (N/m)/kg = 1/s² 이므로 √(k/m)는 1/s, 즉 rad/s입니다.",
    }
    return hints.get(equation_name, "대표 단위 관계를 확인하세요.")
