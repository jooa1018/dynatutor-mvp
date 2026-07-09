from __future__ import annotations

import math

try:
    from .common import ValidationCase
except ImportError:  # direct script execution from tools/chrono_validation
    from common import ValidationCase

G = 9.81


def rolling_sphere_cases() -> list[ValidationCase]:
    cases = []
    for i, h in enumerate([0.5, 1.0, 1.5, 2.0, 3.0], 1):
        cases.append(ValidationCase(
            case_id=f"rolling_sphere_{i:03d}",
            topic="rolling_sphere",
            problem=f"속이 찬 구가 미끄러지지 않고 높이 {h}m 굴러 내려온다. 속도는?",
            expected_solver="pure_rolling_energy",
            reference_fn=lambda h=h: math.sqrt(2 * G * h / (1 + 2/5)),
            tolerance=2e-3,
            notes=["Reference uses v=sqrt(2gh/(1+beta)), beta=2/5."],
        ))
    return cases


def rolling_disk_cases() -> list[ValidationCase]:
    cases = []
    for i, h in enumerate([0.5, 1.0, 1.5, 2.0, 3.0], 1):
        cases.append(ValidationCase(
            case_id=f"rolling_disk_{i:03d}",
            topic="rolling_disk",
            problem=f"원판이 미끄러지지 않고 높이 {h}m 굴러 내려온다. 속도는?",
            expected_solver="pure_rolling_energy",
            reference_fn=lambda h=h: math.sqrt(2 * G * h / (1 + 1/2)),
            tolerance=2e-3,
            notes=["Reference uses v=sqrt(2gh/(1+beta)), beta=1/2."],
        ))
    return cases


def incline_friction_cases() -> list[ValidationCase]:
    cases = []
    values = [(20, 0.05), (25, 0.10), (30, 0.10), (35, 0.15), (40, 0.20)]
    for i, (theta, mu) in enumerate(values, 1):
        cases.append(ValidationCase(
            case_id=f"incline_friction_{i:03d}",
            topic="incline_friction",
            problem=f"운동마찰계수 {mu}인 {theta}도 경사면에서 블록의 가속도를 구하라.",
            expected_solver="incline_with_friction",
            reference_fn=lambda theta=theta, mu=mu: G * (math.sin(math.radians(theta)) - mu * math.cos(math.radians(theta))),
            tolerance=2e-3,
            notes=["Reference uses a=g(sinθ-μcosθ)."],
        ))
    return cases


def collision_restitution_cases() -> list[ValidationCase]:
    cases = []
    # Current DynaTutor collision parser supports perfectly inelastic and elastic/e.
    values = [
        (2, 3, 4, 0, 1.0),
        (1, 2, 6, 0, 1.0),
        (3, 5, 2, 1, 1.0),
        (4, 6, 5, 0, 1.0),
        (2, 8, 10, 0, 1.0),
    ]
    for i, (m1, m2, v1, v2, e) in enumerate(values, 1):
        v1p = (m1 * v1 + m2 * v2 - m2 * e * (v1 - v2)) / (m1 + m2)
        v2p = v1p + e * (v1 - v2)
        speed_reported = abs(v1p) + abs(v2p)  # not used by the solver; keep a scalar reference? Better: DynaTutor returns v2f currently?
        cases.append(ValidationCase(
            case_id=f"collision_elastic_{i:03d}",
            topic="collision_restitution",
            problem=f"m1={m1}kg, m2={m2}kg, v1={v1}m/s, v2={v2}m/s, 완전탄성 충돌이다. 충돌 후 속도는?",
            expected_solver="collision_1d",
            reference_fn=lambda v1p=v1p: v1p,
            tolerance=3e-3,
            display_reference=v1p,
            display_label="v1'",
            notes=[f"Reference elastic outputs v1f={v1p:.6g}, v2f={v2p:.6g}; validator extracts v1' from display because solver returns two speeds."],
        ))
    return cases


def massive_pulley_cases() -> list[ValidationCase]:
    cases = []
    values = [(2, 5, 0.12, 0.3), (3, 7, 0.2, 0.4), (1, 4, 0.05, 0.2), (4, 9, 0.3, 0.5), (5, 8, 0.15, 0.25)]
    for i, (m1, m2, I, R) in enumerate(values, 1):
        a = (m2 - m1) * G / (m1 + m2 + I / (R * R))
        cases.append(ValidationCase(
            case_id=f"massive_pulley_{i:03d}",
            topic="massive_pulley",
            problem=f"질량 있는 도르래에 m1={m1} kg, m2={m2} kg가 줄로 연결되어 있다. 도르래 관성모멘트 I={I} kgm^2, 도르래 반지름 R={R} m 일 때 가속도를 구하라.",
            expected_solver="massive_pulley_atwood",
            reference_fn=lambda a=a: a,
            tolerance=2e-3,
            notes=["Reference uses a=(m2-m1)g/(m1+m2+I/R^2)."],
        ))
    return cases


def all_phase21_cases() -> list[ValidationCase]:
    return rolling_sphere_cases() + rolling_disk_cases() + incline_friction_cases() + collision_restitution_cases() + massive_pulley_cases()
