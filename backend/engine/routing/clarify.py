"""되묻기(clarification) 라우터.

이 엔진에서 '모호성'은 점수 경합으로 나타나지 않는다 — 캐스케이드가
system_type을 하나로 확정하므로 정상 문제는 solver가 정확히 1개 매치되고,
모호한 문제는 0개 매치된다. 따라서 되묻기는 다음 신호에서 발동한다:

  1. 유형은 잡혔지만 필수 구분이 미확정 (경사면 + 마찰 미명시)
  2. 명시적 모호 마커 (ambiguous_pulley: 도르래 구성 불명)
  3. 유형 특징이 충돌 (경사면+용수철, 충돌+경사면 등 혼합 키워드)
  4. 유형 자체가 unknown이지만 단서 flag는 존재

원칙: 자신 있게 찍는 대신 구체적 해석 선택지를 제시하고, 각 선택지는
원탭 재풀이(clarify_patch)로 이어진다. 선택 결과도 기존 검증·출처
레이어를 그대로 통과한다 — 되묻기는 검증의 우회로가 아니다.

clarify_patch는 API로 노출되므로 화이트리스트 검증을 반드시 거친다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from engine.errors import PhysicsClarificationError
from engine.models import CanonicalProblem, Quantity

# patch로 지정 가능한 값 화이트리스트 (API 노출 지점 — 임의 값 주입 차단)
ALLOWED_SYSTEM_TYPES = {
    "single_particle_newton",
    "particle_on_incline",
    "pulley_atwood",
    "pulley_table_hanging",
    "pulley_incline_hanging",
    "massive_pulley_atwood",
    "pure_rolling_energy",
    "rolling_energy_general",
    "vertical_circle",
    "collision_1d",
    "constant_acceleration_1d",
    "projectile_motion",
    "constant_force_work",
    "fixed_axis_rotation",
    "horizontal_friction_force",
    "impulse_momentum",
    "work_energy_speed",
    "spring_mass_vibration",
    "spring_energy",
    "flat_curve_friction",
    "banked_curve_no_friction",
    "relative_acceleration_translation",
    "coriolis_relative_motion",
    "plane_rigid_body_acceleration",
    "polar_kinematics",
    "instant_center_velocity",
    "slot_pin_relative_motion",
    "plane_rigid_body_velocity",
}
ALLOWED_SUBTYPES = {"no_friction", "with_friction", "top", "bottom", "general", "same_level", "rolling_on_incline", None}
ALLOWED_FRICTION_TYPES = {"none", "kinetic", "static", "unspecified", None}
ALLOWED_REQUESTED_OUTPUTS = {"time", "range", "distance", "max_height", "minimum_speed", "final_velocity", "initial_velocity", "acceleration", "tension", "force", "mass", "work", "impulse", "kinetic_energy", "potential_energy", "post_collision_velocity", "v1_after", "v2_after", "angular_velocity", "angular_acceleration", "angular_frequency", "frequency", "period", "tangential_velocity", "centripetal_acceleration", "friction_force", "normal_force", "elastic_energy"}
ALLOWED_KNOWN_SYMBOLS = {"mu", "mu_k", "mu_s", "m", "m1", "m2", "e", "v0", "v1", "v2", "vf", "theta", "h", "h0", "yf", "k", "x", "F", "s", "t", "tau", "I", "R", "r", "v", "vA", "vAx", "vAy", "vB", "aA", "aAx", "aAy", "aB", "rBAx", "rBAy", "omega", "omega0", "alpha", "vrel", "arel", "a", "W"}


_VALID_SUBTYPES_BY_SYSTEM = {
    "particle_on_incline": {"no_friction", "with_friction", None},
    "pulley_table_hanging": {"no_friction", "with_friction", None},
    "pulley_incline_hanging": {"no_friction", "with_friction", None},
    "projectile_motion": {"general", "same_level", None},
    "vertical_circle": {"top", "bottom", None},
    "pure_rolling_energy": {"rolling_on_incline", None},
    "rolling_energy_general": {"rolling_on_incline", None},
}
_FRICTION_SYSTEM_TYPES = {
    "particle_on_incline",
    "pulley_table_hanging",
    "pulley_incline_hanging",
    "horizontal_friction_force",
}
_UNITS_BY_SYMBOL = {
    "mu": {"", None}, "mu_k": {"", None}, "mu_s": {"", None}, "e": {"", None},
    "m": {"kg", None}, "m1": {"kg", None}, "m2": {"kg", None},
    "v0": {"m/s", None}, "v1": {"m/s", None}, "v2": {"m/s", None},
    "vf": {"m/s", None}, "v": {"m/s", None}, "vA": {"m/s", None},
    "vAx": {"m/s", None}, "vAy": {"m/s", None}, "vB": {"m/s", None},
    "a": {"m/s^2", "m/s²", None}, "aA": {"m/s^2", "m/s²", None},
    "aAx": {"m/s^2", "m/s²", None}, "aAy": {"m/s^2", "m/s²", None},
    "aB": {"m/s^2", "m/s²", None}, "arel": {"m/s^2", "m/s²", None},
    "theta": {"deg", "rad", None},
    "h": {"m", None}, "h0": {"m", None}, "yf": {"m", None},
    "x": {"m", None}, "s": {"m", None}, "R": {"m", None}, "r": {"m", None},
    "rBAx": {"m", None}, "rBAy": {"m", None},
    "F": {"N", None}, "W": {"J", None}, "t": {"s", None},
    "k": {"N/m", None}, "tau": {"N*m", "N·m", "Nm", None},
    "I": {"kg*m^2", "kg·m²", None},
    "omega": {"rad/s", None}, "omega0": {"rad/s", None},
    "alpha": {"rad/s^2", "rad/s²", None},
    "vrel": {"m/s", None},
}

_MULTI_VALUE_CONTRACTS: dict[str, tuple[tuple[str, str], ...]] = {
    "rigid_vA_vector": (("vAx", "m/s"), ("vAy", "m/s")),
    "rigid_aA_vector": (("aAx", "m/s^2"), ("aAy", "m/s^2")),
}


@dataclass(frozen=True)
class ClarifyInputField:
    symbol: str
    label: str
    unit: str
    input_type: str = "number"
    required: bool = True


@dataclass
class ClarifyOption:
    id: str
    label: str
    description: str
    patch: dict
    needs_value: str | None = None  # 예: "mu" — 기존 단일 값 입력 호환 경로
    input_fields: list[ClarifyInputField] = field(default_factory=list)


@dataclass
class Clarification:
    rule: str
    question: str
    options: list[ClarifyOption] = field(default_factory=list)
    why: str | None = None


def _validate_known_spec(spec, *, field_name: str) -> None:
    if not isinstance(spec, dict):
        raise ClarifyPatchError(f"{field_name} 항목은 객체여야 합니다.")
    symbol = spec.get("symbol")
    if symbol not in ALLOWED_KNOWN_SYMBOLS:
        raise ClarifyPatchError(f"clarification으로 설정할 수 없는 값: {symbol}")
    try:
        value = float(spec.get("value"))
    except (TypeError, ValueError):
        raise ClarifyPatchError(f"{symbol} 값이 숫자가 아닙니다.")
    if not math.isfinite(value):
        raise ClarifyPatchError(f"{symbol} 값은 유한한 숫자여야 합니다.")
    unit = spec.get("unit") or None
    allowed_units = _UNITS_BY_SYMBOL.get(symbol, {None})
    if unit not in allowed_units:
        raise ClarifyPatchError(
            f"{symbol}에 허용되지 않는 단위입니다: {unit}. allowed={sorted(str(x) for x in allowed_units)}"
        )


def validate_clarify_patch(cp: CanonicalProblem, patch: dict) -> None:
    if not isinstance(patch, dict):
        raise ClarifyPatchError("clarify_patch는 객체여야 합니다.")
    allowed_keys = {
        "system_type", "subtype", "assume", "set_known", "set_knowns",
        "remove_knowns", "requested_outputs", "friction_type", "input_contract",
    }
    unknown_keys = set(patch) - allowed_keys
    if unknown_keys:
        raise ClarifyPatchError(f"허용되지 않는 patch 키: {sorted(unknown_keys)}")

    target_system = patch.get("system_type", cp.system_type)
    if "system_type" in patch and target_system not in ALLOWED_SYSTEM_TYPES:
        raise ClarifyPatchError(f"허용되지 않는 system_type: {target_system}")

    target_subtype = (
        patch["subtype"]
        if "subtype" in patch
        else None
        if "system_type" in patch
        else cp.subtype
    )
    if "subtype" in patch and target_subtype not in ALLOWED_SUBTYPES:
        raise ClarifyPatchError(f"허용되지 않는 subtype: {target_subtype}")
    if "system_type" in patch or "subtype" in patch:
        if target_system not in ALLOWED_SYSTEM_TYPES:
            raise ClarifyPatchError(
                f"subtype을 설정하기 전에 지원되는 system_type이 필요합니다: {target_system}"
            )
        allowed_subtypes = _VALID_SUBTYPES_BY_SYSTEM.get(target_system, {None})
        if target_subtype not in allowed_subtypes:
            raise ClarifyPatchError(
                f"{target_system}과 양립하지 않는 subtype입니다: {target_subtype}"
            )

    if "friction_type" in patch:
        friction_type = patch.get("friction_type")
        if friction_type not in ALLOWED_FRICTION_TYPES:
            raise ClarifyPatchError(f"허용되지 않는 friction_type: {friction_type}")
        if friction_type is not None and target_system not in _FRICTION_SYSTEM_TYPES:
            raise ClarifyPatchError(
                f"{target_system}에는 friction_type을 설정할 수 없습니다."
            )

    if "assume" in patch and patch["assume"] is not None and not isinstance(patch["assume"], str):
        raise ClarifyPatchError("assume은 문자열이어야 합니다.")
    if "set_known" in patch and patch["set_known"] is not None:
        _validate_known_spec(patch["set_known"], field_name="set_known")
    if "set_knowns" in patch:
        values = patch.get("set_knowns")
        if not isinstance(values, list):
            raise ClarifyPatchError("set_knowns는 리스트여야 합니다.")
        for item in values:
            _validate_known_spec(item, field_name="set_knowns")

    input_contract = patch.get("input_contract")
    if input_contract is not None:
        expected = _MULTI_VALUE_CONTRACTS.get(input_contract)
        if expected is None:
            raise ClarifyPatchError(f"지원하지 않는 다중 입력 계약: {input_contract}")
        values = patch.get("set_knowns")
        if not isinstance(values, list):
            raise ClarifyPatchError(
                f"{input_contract} 계약에는 모든 set_knowns 값이 필요합니다."
            )
        by_symbol: dict[str, dict] = {}
        for item in values:
            symbol = item.get("symbol") if isinstance(item, dict) else None
            if symbol in by_symbol:
                raise ClarifyPatchError(f"{symbol} 값이 중복되었습니다.")
            if isinstance(symbol, str):
                by_symbol[symbol] = item
        required_symbols = {symbol for symbol, _ in expected}
        if set(by_symbol) != required_symbols:
            missing = sorted(required_symbols - set(by_symbol))
            extra = sorted(set(by_symbol) - required_symbols)
            raise ClarifyPatchError(
                f"{input_contract} 성분이 완전하지 않습니다. "
                f"missing={missing}, extra={extra}"
            )
        for symbol, unit in expected:
            if (by_symbol[symbol].get("unit") or None) != unit:
                raise ClarifyPatchError(
                    f"{symbol} 단위는 {unit}이어야 합니다."
                )
    if "remove_knowns" in patch:
        values = patch.get("remove_knowns")
        if not isinstance(values, list):
            raise ClarifyPatchError("remove_knowns는 리스트여야 합니다.")
        bad = [symbol for symbol in values if symbol not in ALLOWED_KNOWN_SYMBOLS]
        if bad:
            raise ClarifyPatchError(f"제거할 수 없는 값: {bad}")
    if "requested_outputs" in patch:
        values = patch.get("requested_outputs")
        if not isinstance(values, list):
            raise ClarifyPatchError("requested_outputs는 리스트여야 합니다.")
        bad = [value for value in values if value not in ALLOWED_REQUESTED_OUTPUTS]
        if bad:
            raise ClarifyPatchError(f"허용되지 않는 requested_outputs: {bad}")


class ClarifyPatchError(PhysicsClarificationError):
    pass


def _apply_one_known(cp: CanonicalProblem, sk: dict) -> None:
    _validate_known_spec(sk, field_name="set_known")
    symbol = sk.get("symbol")
    if symbol not in ALLOWED_KNOWN_SYMBOLS:
        raise ClarifyPatchError(f"clarification으로 설정할 수 없는 값: {symbol}")
    try:
        value = float(sk.get("value"))
    except (TypeError, ValueError):
        raise ClarifyPatchError(f"{symbol} 값이 숫자가 아닙니다.")
    cp.knowns[symbol] = Quantity(
        symbol=symbol,
        value=value,
        unit=sk.get("unit") or None,
        source_text=f"사용자 입력: {sk.get('label', symbol)}",
        provenance_hint="user_confirmation",
        subject_evidence={
            "compatibility_key": symbol,
            "method": "clarification_patch",
        },
    )
    if symbol in {"mu", "mu_k"} and cp.friction_type in (None, "none"):
        cp.friction_type = "kinetic"
        cp.flags["friction"] = True
        cp.flags["no_friction"] = False
    if symbol == "mu_s":
        cp.friction_type = "static"
        cp.flags["friction"] = True
        cp.flags["no_friction"] = False


def _clear_satisfied_input_contract(
    cp: CanonicalProblem,
    input_contract: str | None,
) -> None:
    needles_by_contract = {
        "rigid_vA_vector": (
            "A점 속도",
            "vA",
            "v_A",
            "vAx",
            "vAy",
            "reference velocity",
        ),
        "rigid_aA_vector": (
            "A점 가속도",
            "aA",
            "a_A",
            "aAx",
            "aAy",
            "reference acceleration",
        ),
    }
    needles = needles_by_contract.get(input_contract)
    if needles is None:
        return

    def retain(item: str) -> bool:
        compact = str(item).replace(" ", "")
        return not any(
            needle.replace(" ", "").lower() in compact.lower()
            for needle in needles
        )

    cp.missing_info = [item for item in cp.missing_info if retain(item)]
    if cp.canonical_v2 is not None:
        cp.canonical_v2.missing_info = [
            item for item in cp.canonical_v2.missing_info if retain(item)
        ]


def apply_clarify_patch(cp: CanonicalProblem, patch: dict) -> CanonicalProblem:
    """사용자 선택/수정 patch를 canonical에 반영. 화이트리스트 밖 값은 거부.

    Phase 38부터 clarification뿐 아니라 "앱이 이해한 조건" 카드의 직접 수정도
    같은 안전한 patch 통로를 사용한다.
    """
    validate_clarify_patch(cp, patch)
    cp.flags["_clarify_patch_applied"] = True

    st = patch.get("system_type")
    if st is not None:
        if st not in ALLOWED_SYSTEM_TYPES:
            raise ClarifyPatchError(f"허용되지 않는 system_type: {st}")
        cp.system_type = st
        if "subtype" not in patch:
            cp.subtype = None
        cp.flags["_clarify_model_chosen"] = True
    sub = patch.get("subtype", "__unset__")
    if sub != "__unset__":
        if sub not in ALLOWED_SUBTYPES:
            raise ClarifyPatchError(f"허용되지 않는 subtype: {sub}")
        cp.subtype = sub
        cp.flags["_clarify_model_chosen"] = True
    if "friction_type" in patch:
        ft = patch.get("friction_type")
        if ft not in ALLOWED_FRICTION_TYPES:
            raise ClarifyPatchError(f"허용되지 않는 friction_type: {ft}")
        cp.friction_type = ft
        if ft == "none":
            cp.subtype = "no_friction" if cp.system_type in {"particle_on_incline", "pulley_table_hanging"} else cp.subtype
            cp.flags["no_friction"] = True
            cp.flags["friction"] = False
            for k in ("mu", "mu_k", "mu_s"):
                cp.knowns.pop(k, None)
        elif ft in {"kinetic", "static", "unspecified"}:
            cp.subtype = "with_friction" if cp.system_type in {"particle_on_incline", "pulley_table_hanging"} else cp.subtype
            cp.flags["friction"] = True
            cp.flags["no_friction"] = False
    assume = patch.get("assume")
    user_assumption = None
    if assume:
        user_assumption = f"[사용자 확인] {str(assume)[:120]}"
        cp.assumptions.append(user_assumption)

    sk = patch.get("set_known")
    if sk:
        _apply_one_known(cp, sk)
    for item in patch.get("set_knowns") or []:
        if not isinstance(item, dict):
            raise ClarifyPatchError("set_knowns 항목은 객체여야 합니다.")
        _apply_one_known(cp, item)
    _clear_satisfied_input_contract(cp, patch.get("input_contract"))

    for symbol in patch.get("remove_knowns") or []:
        if symbol not in ALLOWED_KNOWN_SYMBOLS:
            raise ClarifyPatchError(f"제거할 수 없는 값: {symbol}")
        cp.knowns.pop(symbol, None)

    if "requested_outputs" in patch:
        req = patch.get("requested_outputs") or []
        if not isinstance(req, list):
            raise ClarifyPatchError("requested_outputs는 리스트여야 합니다.")
        bad = [x for x in req if x not in ALLOWED_REQUESTED_OUTPUTS]
        if bad:
            raise ClarifyPatchError(f"허용되지 않는 requested_outputs: {bad}")
        cp.requested_outputs = list(dict.fromkeys(req))
        cp.unknowns = list(dict.fromkeys([*cp.unknowns, *cp.requested_outputs]))

    # patch가 해소한 항목이 남지 않도록 canonical 기준으로 재계산.
    if cp.subtype == "no_friction":
        cp.friction_type = "none"
    elif cp.subtype == "with_friction" and cp.friction_type in (None, "none"):
        cp.friction_type = "kinetic"

    from engine.extraction.extractor import _missing_info, _objects_from_knowns, _default_assumptions  # 지연 import (순환 방지)

    cp.objects = _objects_from_knowns(cp)
    prior_user_assumptions = [
        item for item in cp.assumptions if str(item).startswith("[사용자 확인]")
    ]
    base_assumptions = _default_assumptions(cp)
    for item in [*prior_user_assumptions, user_assumption]:
        if item and item not in base_assumptions:
            base_assumptions.append(item)
    cp.assumptions = base_assumptions
    cp.missing_info = _missing_info(cp)
    cp.confidence = "높음" if not cp.missing_info and cp.system_type != "unknown" else "보통" if cp.system_type != "unknown" else "낮음"

    # Phase 43: patches change facts/assumptions, so the v2 fingerprint and
    # provenance view must be rebuilt before routing/verification continues.
    from engine.canonical.adapter import attach_canonical_v2

    attach_canonical_v2(cp)
    return cp


# ------------------------------------------------------------------ rules
def _rule_incline_friction(cp: CanonicalProblem) -> Clarification | None:
    if cp.system_type == "particle_on_incline" and cp.subtype not in ("no_friction", "with_friction"):
        return Clarification(
            rule="incline_friction_unknown",
            question="경사면에 마찰이 있나요? 문제에 마찰 조건이 명시되지 않아 확정할 수 없습니다.",
            why="경사면에서는 중력의 경사방향 성분이 물체를 끌어내리고, 마찰이 있으면 μN이 그 운동을 방해합니다. 그래서 마찰 유무에 따라 가속도 식이 달라집니다.",
            options=[
                ClarifyOption(
                    id="no_friction",
                    label="마찰 없음 (매끄러운 경사면)",
                    description="마찰을 무시하고 a = g·sinθ 모형으로 풉니다.",
                    patch={"subtype": "no_friction", "assume": "마찰 무시"},
                ),
                ClarifyOption(
                    id="with_friction",
                    label="마찰 있음 — 운동마찰계수 입력",
                    description="입력한 μ로 a = g(sinθ − μcosθ) 모형으로 풉니다.",
                    patch={"subtype": "with_friction", "set_known": {"symbol": "mu", "unit": "", "label": "운동마찰계수"}},
                    needs_value="mu",
                ),
            ],
        )
    return None


def _rule_table_hanging_friction(cp: CanonicalProblem) -> Clarification | None:
    if cp.system_type != "pulley_table_hanging":
        return None
    if cp.friction_type is not None or cp.flags.get("no_friction") or any(k in cp.knowns for k in ("mu", "mu_k", "mu_s")):
        return None
    return Clarification(
        rule="table_hanging_friction_unknown",
        question="수평면과 물체 사이에 마찰이 있나요? 문제에 마찰 조건이 명시되지 않아 확정할 수 없습니다.",
        why="테이블 위 물체에는 마찰력이 작용할 수도 있고 없을 수도 있습니다. 마찰이 있으면 μm₁g가 운동을 방해해서 가속도와 장력이 달라집니다.",
        options=[
            ClarifyOption(
                id="no_friction",
                label="마찰 없음",
                description="수평면 마찰을 무시하고 table-hanging 도르래로 풉니다.",
                patch={"subtype": "no_friction", "assume": "수평면 마찰 무시"},
            ),
            ClarifyOption(
                id="with_friction",
                label="마찰 있음 — 운동마찰계수 입력",
                description="입력한 μ로 f = μN을 포함해 풉니다.",
                patch={"subtype": "with_friction", "set_known": {"symbol": "mu", "unit": "", "label": "운동마찰계수"}},
                needs_value="mu",
            ),
        ],
    )


def _rule_incline_hanging_friction(cp: CanonicalProblem) -> Clarification | None:
    if cp.system_type != "pulley_incline_hanging":
        return None
    if (
        cp.friction_type is not None
        or (cp.flags or {}).get("no_friction")
        or any(key in cp.knowns for key in ("mu", "mu_k", "mu_s"))
    ):
        return None
    return Clarification(
        rule="incline_hanging_friction_unknown",
        question=(
            "경사면 위 물체와 경사면 사이에 마찰이 있나요? "
            "마찰 조건에 따라 가속도와 장력이 달라집니다."
        ),
        why=(
            "경사면 위 물체에는 m₁g sinθ와 함께 마찰력이 작용할 수 있습니다. "
            "마찰 유무와 계수를 임의로 가정하지 않습니다."
        ),
        options=[
            ClarifyOption(
                id="no_friction",
                label="마찰 없음",
                description="경사면 마찰을 무시하고 연결된 두 물체를 풉니다.",
                patch={"subtype": "no_friction", "assume": "경사면 마찰 무시"},
            ),
            ClarifyOption(
                id="with_friction",
                label="마찰 있음 — 운동마찰계수 입력",
                description="입력한 μ로 운동마찰력을 포함해 풉니다.",
                patch={
                    "subtype": "with_friction",
                    "set_known": {
                        "symbol": "mu",
                        "unit": "",
                        "label": "운동마찰계수",
                    },
                },
                needs_value="mu",
            ),
        ],
    )


def _rule_ambiguous_pulley(cp: CanonicalProblem) -> Clarification | None:
    if cp.system_type == "ambiguous_pulley":
        return Clarification(
            rule="pulley_topology_unknown",
            question="도르래 구성이 어떻게 되나요? 두 물체의 배치가 문제에서 확정되지 않았습니다.",
            options=[
                ClarifyOption("atwood", "양쪽 모두 매달림 (Atwood)", "두 물체가 도르래 양쪽에 수직으로 매달린 구성.", {"system_type": "pulley_atwood"}),
                ClarifyOption("table", "테이블 + 매달림", "한 물체는 수평면 위, 다른 물체는 도르래 너머로 매달린 구성.", {"system_type": "pulley_table_hanging"}),
                ClarifyOption("incline", "경사면 + 매달림", "한 물체는 경사면 위, 다른 물체는 매달린 구성.", {"system_type": "pulley_incline_hanging"}),
            ],
        )
    return None


def _rule_mixed_spring(cp: CanonicalProblem) -> Clarification | None:
    flags = cp.flags or {}
    if flags.get("_clarify_model_chosen"):
        return None
    if flags.get("spring") and (flags.get("incline") or flags.get("pulley")) and not str(cp.system_type).startswith("spring"):
        other = "경사면" if flags.get("incline") else "도르래"
        return Clarification(
            rule="mixed_spring_conflict",
            question=f"용수철과 {other} 요소가 함께 있어 해석이 갈립니다. 어떤 모형으로 풀까요?",
            options=[
                ClarifyOption(
                    "spring_energy", "용수철 에너지 문제로",
                    f"{other} 효과를 무시하고 탄성에너지 → 운동에너지 변환으로 풉니다. (k, 변형량, 질량 필요)",
                    {"system_type": "spring_energy", "assume": f"{other} 효과 무시, 용수철 에너지 모형"},
                ),
                ClarifyOption(
                    "keep_other", f"{other} 문제로",
                    f"용수철을 무시하고 {other} 모형으로 풉니다. (이 모형은 가속도/장력을 구합니다 — 속도를 물었다면 용수철 에너지 쪽을 고르세요.)",
                    ({"system_type": "particle_on_incline", "assume": "용수철 무시, 경사면 모형"} if flags.get("incline")
                     else {"system_type": "pulley_atwood", "assume": "용수철 무시, 도르래 모형"}),
                ),
            ],
        )
    return None


def _rule_mixed_collision(cp: CanonicalProblem) -> Clarification | None:
    flags = cp.flags or {}
    if flags.get("_clarify_model_chosen"):
        return None
    if flags.get("collision") and flags.get("incline") and cp.system_type not in ("collision_1d",):
        return Clarification(
            rule="mixed_collision_conflict",
            question="충돌과 경사면이 함께 있어 해석이 갈립니다. 지금 구하려는 것은 어느 단계인가요?",
            why="충돌 순간에는 운동량/반발계수 관계를 쓰고, 충돌 뒤 미끄러짐은 힘과 가속도 관계를 씁니다. 어느 단계인지에 따라 식이 달라집니다.",
            options=[
                ClarifyOption("collision", "충돌 직후 속도", "운동량 보존(및 반발계수)으로 충돌 직후 속도를 구합니다.", {"system_type": "collision_1d", "assume": "충돌 단계만 계산"}),
                ClarifyOption("incline", "경사면 위 운동", "충돌 이후 경사면 위 감속/이동을 경사면 모형으로 구합니다.", {"system_type": "particle_on_incline", "assume": "경사면 단계만 계산"}),
            ],
        )
    return None


# missing_info 문자열 → 입력받을 심볼 매핑 (extractor._missing_info의 실제 문자열 기준)
_MISSING_TO_SYMBOL: list[tuple[str, str, str, str]] = [
    # (missing_info 부분문자열, symbol, 라벨, 단위)
    ("경사각", "theta", "경사각 θ", "deg"),
    ("발사각", "theta", "발사각 θ", "deg"),
    ("마찰계수 μ", "mu", "마찰계수 μ", ""),
    ("초속도", "v0", "초속도 v0", "m/s"),
    ("두 물체의 질량", "m1", "첫 번째 질량 m1", "kg"),
    ("스프링 상수", "k", "스프링 상수 k", "N/m"),
    ("질량 m", "m", "질량 m", "kg"),
    ("힘 F", "F", "힘 F", "N"),
    ("이동거리 s", "s", "이동거리 s", "m"),
    ("높이 변화 h", "h", "높이 h", "m"),
    ("토크", "tau", "토크 τ", "N*m"),
    ("관성모멘트", "I", "관성모멘트 I", "kg*m^2"),
    ("반지름 R", "R", "반지름 R", "m"),
    ("반발계수", "e", "반발계수 e", ""),
    ("속도 v ", "v", "속도 v", "m/s"),
    ("초기 각속도", "omega0", "초기 각속도 ω₀", "rad/s"),
    ("각속도", "omega", "각속도 ω", "rad/s"),
    ("각가속도", "alpha", "각가속도 α", "rad/s^2"),
    ("상대속도", "vrel", "상대속도 v_rel", "m/s"),
    ("상대가속도", "arel", "상대가속도 a_rel", "m/s^2"),
    # 등가속도: 변수 3개가 필요 — 아는 값부터 입력받는 옵션 3개 제시
    ("등가속도 변수", "v0", "초속도 v0", "m/s"),
    ("등가속도 변수", "a", "가속도 a", "m/s^2"),
    ("등가속도 변수", "t", "시간 t", "s"),
]


def _rule_missing_values(cp: CanonicalProblem) -> Clarification | None:
    """유형은 확정됐지만 값이 부족해 거절될 상황 → 부족한 값을 콕 집어 입력받는다."""
    if cp.system_type in ("unknown", "ambiguous_pulley") or not cp.missing_info:
        return None
    opts: list[ClarifyOption] = []
    seen: set[str] = set()
    for info in cp.missing_info:
        for needle, symbol, label, unit in _MISSING_TO_SYMBOL:
            if needle in info and symbol not in seen and symbol not in cp.knowns:
                seen.add(symbol)
                opts.append(ClarifyOption(
                    id=f"provide_{symbol}",
                    label=f"{label} 입력",
                    description=f"문제에서 빠진 {label} 값을 입력하면 이어서 계산합니다.",
                    patch={"set_known": {"symbol": symbol, "unit": unit, "label": label}},
                    needs_value=symbol,
                ))
                # break 제거(Phase 34): '등가속도 변수'처럼 한 문자열이 여러 입력
                # 옵션으로 이어질 수 있다. seen 가드와 opts[:3]이 폭주를 막는다.
    if not opts:
        return None
    return Clarification(
        rule="missing_values",
        question="풀이에 필요한 값이 문제에 없습니다: " + ", ".join(cp.missing_info) + ". 아는 값을 입력해 주세요.",
        options=opts[:3],
        why="물리식은 모양만으로는 숫자 답을 만들 수 없습니다. 빠진 값이 들어오면 같은 solver와 검증 절차로 다시 계산합니다.",
    )


def _patch_matches_solver(cp: CanonicalProblem, patch: dict) -> bool:
    """옵션 dry-run: patch를 적용한 사본이 (a) solver에 매치되거나
    (b) 후속 되묻기(마찰 유무, 값 입력 등)로 연쇄되면 유효한 선택지다.
    trial에는 _clarify_model_chosen 플래그가 세팅되므로 혼합 규칙 재발동은
    없고, 세부 규칙(incline_friction/missing_values)만 연쇄된다."""
    import copy

    try:
        trial = apply_clarify_patch(copy.deepcopy(cp), dict(patch))
    except ClarifyPatchError:
        return False
    from engine.solvers.registry import SolverRegistry  # 지연 import (모듈 순환 방지)

    try:
        if SolverRegistry().select(trial) is not None:
            return True
        return build_clarification(trial) is not None
    except Exception:
        return False


def _rule_work_direction(cp: CanonicalProblem) -> Clarification | None:
    """일 문제에서 힘·이동 방향 관계가 없어 실패한 경우 — 방향 원탭 선택.
    ('힘 방향으로 이동' 같은 명시 표현은 추출기가 θ=0으로 처리하므로
    여기 오는 건 정말 방향이 빠진 케이스다.)"""
    if cp.system_type not in ("constant_force_work", "work_energy_speed"):
        return None
    if "theta" in (cp.knowns or {}):
        return None
    if "F" not in (cp.knowns or {}) or "s" not in (cp.knowns or {}):
        return None  # 값 자체가 없으면 missing_values 몫
    return Clarification(
        rule="work_direction_unknown",
        question="힘과 이동 방향의 관계가 문제에 없습니다. 어떤 방향인가요?",
        why="일은 힘의 크기와 이동거리만 곱하는 것이 아니라 W = Fs cosθ입니다. θ가 달라지면 같은 힘과 거리라도 양의 일, 0, 음의 일이 될 수 있습니다.",
        options=[
            ClarifyOption("dir_same", "같은 방향 (θ=0°)", "W = F·s 로 계산합니다.",
                          {"set_known": {"symbol": "theta", "value": 0, "unit": "deg", "label": "힘-이동 각 0°"}, "assume": "힘과 이동 같은 방향"}),
            ClarifyOption("dir_opposite", "반대 방향 (θ=180°)", "W = -F·s (음의 일)로 계산합니다.",
                          {"set_known": {"symbol": "theta", "value": 180, "unit": "deg", "label": "힘-이동 각 180°"}, "assume": "힘과 이동 반대 방향"}),
            ClarifyOption("dir_perp", "수직 (θ=90°)", "W = 0 입니다.",
                          {"set_known": {"symbol": "theta", "value": 90, "unit": "deg", "label": "힘-이동 각 90°"}, "assume": "힘과 이동 수직"}),
            ClarifyOption("dir_angle", "각도 직접 입력", "입력한 θ로 W = F·s·cosθ 를 계산합니다.",
                          {"set_known": {"symbol": "theta", "unit": "deg", "label": "힘-이동 각 θ"}}, needs_value="theta"),
        ],
    )


def _rule_incline_hanging_candidate(cp: CanonicalProblem) -> Clarification | None:
    """경사면 위 m1 + 매달린 m2인데 줄/도르래 언급이 없어 연결이 미확정인 클래스.
    (기존에는 정적 거절 — Phase 34부터 원탭 확정 질문으로 전환.)"""
    if cp.system_type != "incline_hanging_candidate":
        return None
    return Clarification(
        rule="incline_hanging_candidate",
        question="m2가 매달려 있는데 줄/도르래 연결이 명시되지 않았습니다. 두 물체가 연결된 구성인가요?",
        options=[
            ClarifyOption(
                id="connected_pulley",
                label="줄/도르래로 연결됨",
                description="경사면 위 m1과 매달린 m2가 도르래 너머 줄로 연결된 표준 구성으로 풉니다.",
                patch={"system_type": "pulley_incline_hanging", "assume": "줄/도르래 연결"},
            ),
            ClarifyOption(
                id="incline_only",
                label="연결 안 됨 — 경사면 위 m1만",
                description="m2를 무시하고 경사면 위 m1의 운동만 계산합니다.",
                patch={"system_type": "particle_on_incline", "assume": "m2 무관, 경사면 단독"},
            ),
        ],
    )


def _rule_rigid_missing_reference(cp: CanonicalProblem) -> Clarification | None:
    """Require a real reference-point vector instead of inventing a +x direction."""
    if cp.system_type not in {
        "plane_rigid_body_velocity",
        "plane_rigid_body_acceleration",
    }:
        return None
    is_velocity = cp.system_type == "plane_rigid_body_velocity"
    prefix = "v" if is_velocity else "a"
    scalar_key = f"{prefix}A"
    x_key, y_key = f"{prefix}Ax", f"{prefix}Ay"
    unit = "m/s" if is_velocity else "m/s^2"
    quantity_label = "속도" if is_velocity else "가속도"
    cd = getattr(cp, "coordinate_data", {}) or {}
    has_vector = (
        x_key in cd and y_key in cd
    ) or (
        x_key in (cp.knowns or {}) and y_key in (cp.knowns or {})
    )
    scalar = (cp.knowns or {}).get(scalar_key)
    zero_reference = (
        scalar is not None
        and scalar.value is not None
        and abs(float(scalar.value)) <= 1e-12
    )
    raw = cp.raw_text or ""
    fixed = any(
        phrase in raw
        for phrase in ("고정점", "A점이 고정", "A점은 고정", "A점 고정", "A is fixed")
    )
    if has_vector or zero_reference or fixed:
        return None
    return Clarification(
        rule="rigid_missing_reference",
        question=f"기준점 A의 {quantity_label} 방향이 없습니다. A점이 고정인가요, 아니면 벡터 성분을 갖나요?",
        options=[
            ClarifyOption(
                id="fix_A",
                label=f"A점 고정 ({prefix}_A = 0)",
                description=f"A점의 {quantity_label}를 0벡터로 두고 계산합니다.",
                patch={
                    "set_known": {
                        "symbol": scalar_key,
                        "value": 0.0,
                        "unit": unit,
                        "label": f"A점 고정({scalar_key}=0)",
                    },
                    "assume": "A점 고정",
                },
            ),
            ClarifyOption(
                id=f"provide_{prefix}A_vector",
                label=f"A점 {quantity_label} 성분 입력",
                description=f"{x_key}, {y_key} 두 성분을 모두 입력해야 합니다.",
                patch={
                    "input_contract": (
                        "rigid_vA_vector" if is_velocity else "rigid_aA_vector"
                    )
                },
                input_fields=[
                    ClarifyInputField(
                        symbol=x_key,
                        label=f"A점 {quantity_label} x성분",
                        unit=unit,
                    ),
                    ClarifyInputField(
                        symbol=y_key,
                        label=f"A점 {quantity_label} y성분",
                        unit=unit,
                    ),
                ],
            ),
        ],
    )


def _evidence_options(cp: CanonicalProblem, exclude: set[str]) -> list[ClarifyOption]:
    from engine.routing.evidence import rank_type_evidence

    opts: list[ClarifyOption] = []
    for ev in rank_type_evidence(cp)[:4]:
        if ev.family in exclude:
            continue
        patch = {"system_type": ev.rep_type, "assume": f"{ev.label} 모형으로 해석"}
        if ev.rep_type not in ALLOWED_SYSTEM_TYPES or not _patch_matches_solver(cp, patch):
            continue
        opts.append(ClarifyOption(
            id=f"as_{ev.family}",
            label=f"{ev.label} 문제로",
            description=f"{ev.label} 대표 모형으로 풉니다. 단서 — {'; '.join(ev.reasons)}",
            patch=patch,
        ))
        if len(opts) == 3:
            break
    return opts


def _rule_unknown_with_evidence(cp: CanonicalProblem) -> Clarification | None:
    """유형이 unknown인데 유형 단서 flag는 존재 → 후보 모형을 제시.
    (missing_values는 unknown을 스킵하므로 이 규칙이 없으면 무질문 거절이 된다.)"""
    if cp.system_type != "unknown" or (cp.flags or {}).get("_clarify_model_chosen"):
        return None
    opts = _evidence_options(cp, exclude=set())
    if not opts:
        return None
    return Clarification(
        rule="unknown_with_evidence",
        question="문제 유형을 확정하지 못했습니다. 어떤 상황에 가장 가까운가요?",
        options=opts,
    )


# 현재 system_type이 자체적으로 설명하는(=충돌이 아닌) 패밀리들.
_TYPE_EXPLAINS: dict[str, set[str]] = {
    "pulley_incline_hanging": {"pulley", "incline"},
    "pulley_table_hanging": {"pulley"},
    "banked_curve_no_friction": {"curve", "incline"},
    "pure_rolling_energy": {"rolling", "rotation", "work_energy", "incline"},
    "rolling_energy_general": {"rolling", "rotation", "work_energy", "incline"},
    "spring_energy_speed": {"spring", "work_energy"},
    "work_energy_speed": {"work_energy", "kinematics"},
    "constant_force_work": {"work_energy", "kinematics"},
    "projectile_motion": {"projectile", "kinematics"},
    "collision_1d": {"collision", "impulse"},
    "impulse_momentum": {"impulse", "collision"},
    "spring_mass_vibration": {"spring"},
}


def _rule_evidence_conflict_fallback(cp: CanonicalProblem) -> Clarification | None:
    """최후 안전망: 유형은 확정됐지만 풀이가 실패했고, 현재 유형이 설명하지
    못하는 다른 패밀리 단서가 공존할 때 모형 선택지를 제시한다.
    missing_values 뒤에 놓여 '값 입력' 질문을 가로채지 않는다."""
    flags = cp.flags or {}
    if flags.get("_clarify_model_chosen"):
        return None
    st = cp.system_type
    if st in ("unknown", "ambiguous_pulley"):
        return None
    from engine.routing.evidence import TYPE_TO_FAMILY

    explained = _TYPE_EXPLAINS.get(st, {TYPE_TO_FAMILY.get(st)} - {None})
    opts = _evidence_options(cp, exclude=set())
    if not opts:
        return None
    others = [o for o in opts if o.id.removeprefix("as_") not in explained]
    if others and len(opts) >= 2:
        # 진짜 혼합: 서로 다른 패밀리 모형 선택
        return Clarification(
            rule="evidence_conflict",
            question="서로 다른 유형의 단서가 함께 있어 해석이 갈립니다. 어떤 모형으로 풀까요?",
            options=opts,
        )
    # 혼합은 아니지만 여기까지 왔다는 것 = missing_values조차 옵션을 못 만든
    # 무질문 거절 직전 (예: 'rolling' 같은 solver 미연결 중간 타입).
    # 자기 패밀리 대표 모형 확인형이 무질문 거절보다 낫다.
    return Clarification(
        rule="evidence_confirm",
        question="문제 유형은 짐작되지만 이대로는 풀 수 없습니다. 아래 모형으로 풀어볼까요? (선택 후 필요한 값을 이어서 묻습니다.)",
        options=opts[:2],
    )


def _rule_contradictory_input(cp: CanonicalProblem) -> Clarification | None:
    """Do not choose between mutually inconsistent explicit facts."""
    conflicts = list(cp.canonical_v2.conflicts) if cp.canonical_v2 is not None else []
    if not conflicts:
        return None
    details = "; ".join(conflicts)
    return Clarification(
        rule="contradictory_input",
        question="서로 다른 값으로 적힌 조건이 있습니다. 모순되는 값을 확인해 문제를 다시 입력해 주세요.",
        why="명시적 조건이 충돌한 상태에서 한 값을 임의로 선택하면 높은 신뢰도의 오답이 될 수 있습니다. 감지된 충돌: " + details,
        options=[],
    )


_RULES = [
    _rule_contradictory_input,
    _rule_ambiguous_pulley,
    # 혼합 유형(모형 선택)이 마찰 유무(세부 조건)보다 근본적인 질문이므로 먼저.
    # 경사면을 선택하면 다음 턴에 friction 규칙이 자연스럽게 연쇄된다.
    _rule_mixed_spring,
    _rule_mixed_collision,
    _rule_incline_hanging_candidate,
    _rule_work_direction,
    _rule_rigid_missing_reference,
    # unknown은 missing_values가 스킵하므로 그 앞에서 받는다.
    _rule_unknown_with_evidence,
    _rule_incline_friction,
    _rule_table_hanging_friction,
    _rule_incline_hanging_friction,
    _rule_missing_values,
    # 최후 안전망 — '값 입력' 질문(missing_values)을 가로채지 않도록 맨 뒤.
    _rule_evidence_conflict_fallback,
]


def build_clarification(cp: CanonicalProblem) -> Clarification | None:
    """solver가 매치되지 않았을 때만 호출된다 — 정상 풀이를 가로막지 않는다."""
    for rule in _RULES:
        clar = rule(cp)
        if clar is not None:
            return clar
    return None
