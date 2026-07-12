"""유형 패밀리 증거 점수기.

캐스케이드가 system_type을 하나로 확정하기 전에 텍스트에 어떤 유형
'증거'들이 공존했는지를 계량한다. 되묻기 라우터의 일반 혼합 규칙이
"어떤 모형들이 경합했는가"를 알기 위해 사용한다.

점수 규칙 (보수적으로):
  - 패밀리 전용 flag 적중: +2 (복수 flag여도 패밀리당 최대 +2)
  - 패밀리 시그니처 known 존재: +1 (패밀리당 최대 +1)
발동 floor는 호출 측에서 2 이상을 요구한다 — flag 없이 knowns만으로는
후보가 되지 않는다 (m, v 같은 흔한 심볼의 오발동 방지).
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.models import CanonicalProblem


@dataclass(frozen=True)
class FamilyEvidence:
    family: str
    label: str            # 사용자에게 보여줄 이름
    rep_type: str         # 대표 모형 system_type (clarify patch 대상)
    score: int
    reasons: list[str]


# family → (라벨, 대표 system_type, flag 증거, knowns 증거)
_FAMILIES: dict[str, tuple[str, str, tuple[str, ...], tuple[str, ...]]] = {
    "incline": ("경사면", "particle_on_incline", ("incline",), ("theta",)),
    "pulley": ("도르래", "pulley_atwood", ("pulley",), ()),
    "spring": ("용수철", "spring_energy", ("spring", "vibration"), ("k",)),
    "collision": ("충돌", "collision_1d", ("collision", "elastic", "perfectly_inelastic"), ("e",)),
    "projectile": ("포물선 운동", "projectile_motion", ("projectile",), ()),
    "work_energy": ("일-에너지", "work_energy_speed", ("work",), ("W",)),
    "rotation": ("고정축 회전", "fixed_axis_rotation", ("rotation_fixed_axis",), ("tau", "I")),
    "impulse": ("충격량-운동량", "impulse_momentum", ("impulse",), ()),
    "curve": ("커브 주행", "flat_curve_friction", ("curve", "flat_curve", "banked"), ()),
    "rolling": ("순수 구름", "pure_rolling_energy", ("rolling", "no_slip"), ()),
    "kinematics": ("등가속도 직선운동", "constant_acceleration_1d", ("kinematics",), ()),
}

# system_type → 소속 패밀리 (현재 해석이 어느 패밀리인지 판정용)
TYPE_TO_FAMILY: dict[str, str] = {
    "single_particle_newton": "newton",
    "horizontal_friction_force": "friction",
    "vertical_circle": "circular_motion",
    "relative_acceleration_translation": "relative_motion",
    "coriolis_relative_motion": "relative_motion",
    "plane_rigid_body_velocity": "rigid_body",
    "plane_rigid_body_acceleration": "rigid_body",
    "instant_center_velocity": "rigid_body",
    "polar_kinematics": "advanced_motion",
    "slot_pin_relative_motion": "advanced_motion",
    "particle_on_incline": "incline",
    "pulley_atwood": "pulley", "pulley_table_hanging": "pulley",
    "pulley_incline_hanging": "pulley", "massive_pulley_atwood": "pulley",
    "ambiguous_pulley": "pulley",
    "spring_energy": "spring", "spring_energy_speed": "spring", "spring_mass_vibration": "spring",
    "collision_1d": "collision",
    "projectile_motion": "projectile",
    "work_energy_speed": "work_energy", "constant_force_work": "work_energy",
    "fixed_axis_rotation": "rotation",
    "impulse_momentum": "impulse",
    "flat_curve_friction": "curve", "banked_curve_no_friction": "curve",
    "pure_rolling_energy": "rolling", "rolling_energy_general": "rolling",
    "constant_acceleration_1d": "kinematics",
}


def rank_type_evidence(cp: CanonicalProblem, floor: int = 2) -> list[FamilyEvidence]:
    """floor 이상 점수의 패밀리를 점수 내림차순으로."""
    flags = cp.flags or {}
    knowns = cp.knowns or {}
    out: list[FamilyEvidence] = []
    for family, (label, rep_type, flag_keys, known_keys) in _FAMILIES.items():
        # "경사진 커브/뱅크각"의 경사 cue는 경사면 위 입자 모형이 아니다.
        # Curve evidence가 명시되면 incline family의 substring 오탐을 억제한다.
        if family == "incline" and flags.get("curve"):
            continue
        score = 0
        reasons: list[str] = []
        hit_flags = [k for k in flag_keys if flags.get(k)]
        if hit_flags:
            score += 2
            reasons.append(f"키워드: {', '.join(hit_flags)}")
        hit_knowns = [k for k in known_keys if k in knowns]
        if hit_knowns:
            score += 1
            reasons.append(f"값: {', '.join(hit_knowns)}")
        if score >= floor:
            out.append(FamilyEvidence(family, label, rep_type, score, reasons))
    out.sort(key=lambda e: -e.score)
    return out
