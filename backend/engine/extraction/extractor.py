import re
from engine.models import CanonicalProblem, Quantity
from engine.extraction.normalizer import lower_for_match, normalize
from engine.extraction.quantity import extract_quantities
from engine.physics_core.direction_parser import infer_angle_between_force_and_displacement, infer_direction_label
from engine.physics_core.inertia import infer_body_shape
from engine.physics_core.coordinate_parser import parse_coordinate_data_from_text


def _has_any(t: str, words: list[str]) -> bool:
    return any(w in t for w in words)


WORK_PATTERNS = [
    r"한\s*일",
    r"일을\s*구",
    r"일은\s*\?",
    r"일의\s*(크기|양)",
    r"(마찰력|중력|알짜힘|힘)이\s*한\s*일",
    r"알짜일",
    r"총\s*일",
    r"work",
    r"\bW\s*=",
    r"일\s*\d+(?:\.\d+)?\s*J",
    r"일\s*\d+(?:\.\d+)?\s*줄",
]

WORK_NEGATIVE_PATTERNS = [
    r"일\s*때",
    r"\d+\s*일",
    r"동일",
    r"일정",
    r"일반",
    r"일어나",
    r"일직선",
    r"일단",
]


def _has_work_phrase(t: str) -> bool:
    if any(re.search(p, t, re.IGNORECASE) for p in WORK_NEGATIVE_PATTERNS):
        # Negative context wins only for the single ambiguous token "일".
        # Still allow explicit positive phrases such as "마찰력이 한 일".
        return any(re.search(p, t, re.IGNORECASE) for p in WORK_PATTERNS)
    return any(re.search(p, t, re.IGNORECASE) for p in WORK_PATTERNS)




def _rope_mentioned(t: str) -> bool:
    """물리적 '줄'(rope) 언급 여부. '줄을 서다'(대기열) 관용구는 제외."""
    return bool(re.search(r"줄(?!\s*을?\s*서)", t))


def _has_spring_phrase(t: str) -> bool:
    """용수철/스프링 단서만 spring flag로 잡는다.

    '완전탄성충돌', '탄성충돌'의 '탄성'은 충돌의 성질이지
    용수철이 아니므로 여기서는 제외한다.
    """
    return _has_any(t, [
        "스프링", "용수철", "spring",
        "탄성 위치에너지", "탄성위치에너지", "탄성 에너지", "탄성에너지",
        "elastic potential energy", "elastic potential",
    ])


def _has_table_surface_phrase(t: str) -> bool:
    return _has_any(t, [
        "수평면", "수평면 위", "수평면의 물체",
        "테이블", "테이블 위", "수평 테이블",
        "책상", "책상 위",
        "table", "horizontal surface", "horizontal table", "horizontal",
    ])


def _has_string_connection_phrase(t: str) -> bool:
    """줄/실/끈 또는 도르래 연결 단서.

    주의: 한국어의 bare "실"은 "실험실"에도 들어가므로 단독 매칭하지 않는다.
    또한 "용수철에 연결"은 spring 문제이지 pulley가 아니므로 단순 "연결"만으로
    pulley flag를 켜지 않는다.
    """
    return (
        _has_any(t, [
            "도르래", "pulley", "장력", "tension",
            "끈", "string", "rope",
            "실로 연결", "실이 연결", "실과 연결", "실에 연결",
            "줄로 연결", "줄이 연결", "줄과 연결", "줄에 연결",
            "끈으로 연결", "끈이 연결", "끈과 연결", "끈에 연결",
            "가벼운 실", "가벼운 줄", "가벼운 끈",
        ])
        or _rope_mentioned(t)
    )


def _has_hanging_mass_phrase(t: str) -> bool:
    return _has_any(t, [
        "매달", "매달려", "매달린", "아래로 매달", "수직으로 매달",
        "hanging", "hangs", "suspended",
    ])


def _infer_requested_outputs(t: str) -> list[str]:
    """사용자가 실제로 '구하라/얼마인가/?'로 요청한 출력만 잡는다.

    한국어 문제는 "3 m 이동하는 동안", "변위와 같은 방향"처럼
    물리량 단어가 조건으로 자주 등장한다. 단어 존재만으로 requested_outputs에
    넣으면 계산은 맞아도 answer validator가 "거리 답이 없다"고 강등한다.
    """
    t = re.sub(r"계산하(라|시오|여라|시\S*)", "구하라", t)
    outs: list[str] = []
    compact = t.replace(" ", "")

    def add(key: str):
        if key not in outs:
            outs.append(key)

    def has_query(*patterns: str) -> bool:
        return any(re.search(p, t, re.IGNORECASE) for p in patterns)

    # 시간: "4초 동안"은 조건, "걸리는 시간/시간은?/몇 초?"만 요청.
    if has_query(
        r"걸리는\s*시간", r"도달\s*시간", r"비행\s*시간", r"소요\s*시간",
        r"시간\s*(?:을|를)\s*(?:구|계산|찾)", r"시간\s*(?:은|는)\s*\?",
        r"시간\s*(?:과|와|및|그리고)[^\.\n?]{0,40}\?",
        r"몇\s*초", r"time\s*\?", r"find\s+time", r"calculate\s+time",
    ) or "걸리는시간" in compact:
        add("time")

    if has_query(r"수평\s*거리", r"사거리", r"range\s*\?", r"find\s+range"):
        add("range")
    elif has_query(
        r"(?:이동\s*거리|이동거리|변위|거리)\s*(?:을|를)\s*(?:구|계산|찾)",
        r"(?:이동\s*거리|이동거리|변위|거리)\s*(?:은|는)\s*\?",
        r"얼마나\s*(?:이동|움직)",
        r"(?:몇\s*m|몇\s*미터)[^\.\n?]{0,20}(?:이동|움직|갔|갔다)",
        r"(?:최종\s*속도|나중\s*속도|마지막\s*속도)[^\.\n?]{0,35}(?:와|과|및|그리고)[^\.\n?]{0,35}(?:이동\s*거리|이동거리|변위|거리)[^\.\n?]{0,30}(?:구|계산|\?)",
        r"(?:이동\s*거리|이동거리|변위|거리)[^\.\n?]{0,35}(?:와|과|및|그리고)[^\.\n?]{0,35}(?:최종\s*속도|나중\s*속도|마지막\s*속도)[^\.\n?]{0,30}(?:구|계산|\?)",
        r"distance\s*\?", r"displacement\s*\?", r"find\s+(distance|displacement)", r"calculate\s+(distance|displacement)",
    ):
        add("distance")

    if has_query(r"최대\s*높이", r"최고점\s*높이", r"max\s+height", r"maximum\s+height"):
        add("max_height")
    if has_query(
        r"(?:최종\s*속도|나중\s*속도|마지막\s*속도)\s*(?:을|를)?\s*(?:구|계산|찾)",
        r"(?:최종\s*속도|나중\s*속도|마지막\s*속도)\s*(?:은|는)\s*\?",
        r"(?<![가각])속도\s*(?:은|는)\s*\?",
        r"final\s+(velocity|speed)",
        r"(?:최종\s*속도|나중\s*속도|마지막\s*속도)[^\.\n?]{0,35}(?:와|과|및|그리고)[^\.\n?]{0,35}(?:이동\s*거리|이동거리|변위|거리)[^\.\n?]{0,30}(?:구|계산|\?)",
        r"(?:이동\s*거리|이동거리|변위|거리)[^\.\n?]{0,35}(?:와|과|및|그리고)[^\.\n?]{0,35}(?:최종\s*속도|나중\s*속도|마지막\s*속도)[^\.\n?]{0,30}(?:구|계산|\?)",
    ):
        add("final_velocity")
    if has_query(r"(?:초기\s*속도|처음\s*속도)\s*(?:을|를)?\s*(?:구|계산|찾)", r"(?:초기\s*속도|처음\s*속도)\s*(?:은|는)\s*\?", r"initial\s+(velocity|speed)"):
        add("initial_velocity")
    if any(w in compact for w in ["가속도는", "가속도와", "가속도를구", "가속도구", "가속도?"]) and not any(w in compact for w in ["각가속도는", "각가속도와", "각가속도를구", "각가속도?", "각가속도구"]):
        add("acceleration")
    elif "acceleration?" in t or "find acceleration" in t:
        add("acceleration")
    if any(w in compact for w in ["장력은", "장력을", "장력?", "장력구"]) or "tension?" in t or "find tension" in t:
        add("tension")
    if any(w in t for w in ["필요한 힘", "필요한 알짜힘", "힘을 구", "force?"]) or any(w in compact for w in ["힘은?", "힘을구", "알짜힘은?", "합력은?"]):
        add("force")
    if any(w in compact for w in ["질량은?", "질량을구", "질량구"]) or "mass?" in t or "find mass" in t:
        add("mass")
    if has_query(r"운동에너지", r"kinetic\s+energy"):
        add("kinetic_energy")
    if has_query(r"마찰력[은을이]?", r"friction\s+force"):
        add("friction_force")
    if has_query(r"(?:저장된|탄성)\s*(?:퍼텐셜\s*)?에너지", r"elastic\s+(?:potential\s+)?energy", r"stored\s+energy"):
        add("elastic_energy")
    if has_query(r"위치에너지", r"potential\s+energy"):
        add("potential_energy")
    if has_query(r"한\s*일\s*(?:은|는|을|를)?\s*\?", r"한\s*일\s*(?:을|를)?\s*(?:구|계산|찾)", r"일을\s*(?:구|계산|찾)", r"일은\s*\?", r"일의\s*(크기|양)", r"work\s*\?", r"find\s+work", r"calculate\s+work"):
        add("work")
    if "충돌 후" in t and "속도" in t:
        add("post_collision_velocity")
        add("v1_after")
        add("v2_after")
    if has_query(r"각속도\s*(?:을|를)?\s*(?:구|계산|찾)", r"각속도\s*(?:은|는)\s*\?", r"angular\s+velocity\s*\?"):
        add("angular_velocity")
    if has_query(r"각가속도\s*(?:을|를)?\s*(?:구|계산|찾)", r"각가속도\s*(?:은|는)\s*\?", r"angular\s+acceleration\s*\?"):
        add("angular_acceleration")
    if has_query(r"접선속도\s*(?:을|를)?\s*(?:구|계산|찾)", r"접선속도\s*(?:은|는)\s*\?", r"tangential\s+velocity\s*\?"):
        add("tangential_velocity")
    if has_query(r"구심가속도\s*(?:을|를)?\s*(?:구|계산|찾)", r"구심가속도\s*(?:은|는)\s*\?", r"centripetal\s+acceleration\s*\?"):
        add("centripetal_acceleration")
    return outs


def _infer_launch_angle(knowns: dict, t: str) -> tuple[float | None, str | None]:
    if "theta" in knowns and knowns["theta"].value is not None:
        return float(knowns["theta"].value), "explicit_angle"
    if any(w in t for w in ["수평 방향", "수평방향", "수평으로", "horizontal"]):
        return 0.0, "horizontal_phrase"
    if any(w in t for w in ["수직 위로", "위로 던", "수직으로", "vertical"]):
        return 90.0, "vertical_phrase"
    return None, None


def extract_problem(problem_text: str) -> CanonicalProblem:
    normalized = normalize(problem_text)
    t = lower_for_match(problem_text)
    knowns = extract_quantities(normalized)

    flags = {
        "incline": _has_any(t, ["경사", "incline", "slope", "비탈", "빗면", "사면"]),
        "no_friction": _has_any(t, ["마찰 없는", "마찰이 없는", "마찰은 없는", "마찰이 없", "마찰 없음", "마찰없", "마찰 없", "마찰을 무시", "마찰은 무시", "마찰 무시", "frictionless", "smooth", "매끈", "매끄러운"]),
        "friction": _has_any(t, ["마찰", "friction", "rough", "거친"]),
        "pulley": _has_string_connection_phrase(t),
        "rolling": _has_any(t, ["구름", "굴러", "구르", "rolling", "rolls"]),
        "no_slip": _has_any(t, ["미끄러지지", "미끄럼 없이", "no slip", "without slipping", "순수 구름", "pure rolling"]),
        "slipping": _has_any(t, ["미끄러지며", "미끄러짐", "slipping", "with slipping"]),
        "vertical_circle": _has_any(t, ["수직 원운동", "vertical circle", "loop", "최고점", "최저점"]),
        "top": _has_any(t, ["최고점", "top"]),
        "bottom": _has_any(t, ["최저점", "bottom"]),
        "collision": _has_any(t, ["충돌", "collision", "impact"]),
        "perfectly_inelastic": _has_any(t, ["완전비탄성", "붙어서", "함께 움직", "한 덩어리", "stick together", "perfectly inelastic"]),
        "elastic": _has_any(t, ["완전탄성", "elastic collision", "탄성충돌"]),
        "energy": _has_any(t, ["에너지", "energy", "높이", "height"]),
        "table": _has_table_surface_phrase(t),
        "hanging": _has_hanging_mass_phrase(t),
        "string": _has_string_connection_phrase(t),
        "kinematics": _has_any(t, ["등가속도", "직선 운동", "constant acceleration", "kinematics", "변위", "이동거리"]),
        "projectile": _has_any(t, ["포물선", "투사", "발사", "projectile", "포탄", "수평거리", "사거리", "던졌", "던져", "던진"]),
        "work": _has_work_phrase(t) or (("F" in knowns or "force" in knowns) and ("s" in knowns or "distance" in knowns) and _has_any(t, ["거리", "변위", "이동", "displacement"])),
        "impulse": _has_any(t, ["충격량", "impulse"]),
        "rotation_fixed_axis": _has_any(t, ["고정축", "각가속도", "각속도", "토크", "관성모멘트", "fixed axis", "angular acceleration", "rad/s"]),
        "spring": _has_spring_phrase(t),
        "vibration": _has_any(t, ["진동", "고유진동수", "주기", "frequency", "period", "vibration", "oscillation"]),
        "curve": _has_any(t, ["커브", "곡선", "원형 도로", "curve", "turn"]),
        "banked": _has_any(t, ["경사진 커브", "뱅크", "banked"]),
        "flat_curve": _has_any(t, ["평평한 커브", "flat curve", "수평 커브"]),
        "polar": _has_any(t, ["극좌표", "polar", "radial", "transverse", "방사", "횡방향", "r_dot", "rdot", "theta_dot", "thetadot"]),
        "instant_center": _has_any(t, ["순간중심", "instant center", "instantaneous center", "ic에서", " ic ", "ic법", "ic method"]) or ("순간 중심" in t and "도달하는 순간 중심" not in t),
        "slot_pin": _has_any(t, ["슬롯", " slot", "핀", " pin ", "홈", "relative motion in slot"]),
        "relative_motion": _has_any(t, ["상대운동", "상대 운동", "relative motion", "상대속도", "relative velocity"]),
        "plane_rigid_body": _has_any(t, ["평면강체", "평면 강체", "plane rigid body", "general plane motion", "강체 평면운동", "강체의 평면운동", "점 b의 속도", "v_b", "vB", "점 b의 가속도", "a_b", "aB"]),
        "plane_acceleration": _has_any(t, ["평면강체 가속도", "강체 가속도", "점 b의 가속도", "a_b", "aB", "normal acceleration", "tangential acceleration"]),
        "coriolis": _has_any(t, ["코리올리", "coriolis", "회전좌표계", "rotating frame", "회전 기준계", "relative motion rotating"]),
        "relative_acceleration": _has_any(t, ["상대가속도", "상대 가속도", "relative acceleration", "a_rel", "arel"]),
        "massive_pulley": _has_any(t, ["질량 있는 도르래", "질량있는 도르래", "도르래 관성", "도르래의 관성", "pulley inertia", "massive pulley", "도르래 질량"]),
        "general_inertia": _has_any(t, ["관성모멘트", "moment of inertia", "I=", "I ="]),
    }
    # "완전탄성/완전비탄성"만 있어도 충돌 문제로 봅니다.
    if flags.get("perfectly_inelastic") or flags.get("elastic"):
        flags["collision"] = True

    # 마찰 없음은 마찰 flag를 덮어쓴다.
    if flags["no_friction"]:
        flags["friction"] = False

    unknowns: list[str] = []
    if _has_any(t, ["가속도", "acceleration", " a "]):
        unknowns.append("acceleration")
    if _has_any(t, ["속도", "속력", "speed", "velocity", " v ", "최종속도", "나중 속도", "최대속도", "설계속도"]):
        unknowns.append("velocity")
    if _has_any(t, ["장력", "tension"]):
        unknowns.append("tension")
    if _has_any(t, ["알짜힘", "합력", "필요한 힘", "힘은", "힘을 구", "net force", "resultant force"]):
        unknowns.append("force")
    if _has_any(t, ["질량은", "질량을 구", "mass"]):
        unknowns.append("mass")
    if _has_any(t, ["최소속도", "minimum speed"]):
        unknowns.append("minimum_speed")
    if _has_any(t, ["시간", "걸리는 시간", "소요시간", "time", "비행시간"]):
        unknowns.append("time")
    if _has_any(t, ["거리", "변위", "사거리", "수평거리", "도달거리", "range", "distance", "displacement"]):
        unknowns.append("distance")
    if _has_any(t, ["최대높이", "최대 높이", "max height", "maximum height"]):
        unknowns.append("max_height")
    if _has_work_phrase(t):
        unknowns.append("work")
    if _has_any(t, ["충격량", "impulse"]):
        unknowns.append("impulse")
    if _has_any(t, ["각가속도", "angular acceleration"]):
        unknowns.append("angular_acceleration")
    if _has_any(t, ["고유진동수", "각진동수", "natural frequency", "angular frequency"]):
        unknowns.append("angular_frequency")
    if _has_any(t, ["주기", "period"]):
        unknowns.append("period")
    if _has_any(t, ["진동수", "frequency"]):
        unknowns.append("frequency")
    if _has_any(t, ["방사방향 가속도", "방사 가속도", "radial acceleration", "a_r"]):
        unknowns.append("radial_acceleration")
    if _has_any(t, ["횡방향 가속도", "transverse acceleration", "a_theta", "a_θ"]):
        unknowns.append("transverse_acceleration")
    if _has_any(t, ["가속도 성분", "acceleration components", "극좌표 가속도"]):
        unknowns.extend(["radial_acceleration", "transverse_acceleration"])
    if _has_any(t, ["각속도", "angular velocity", "omega", "ω"]):
        unknowns.append("angular_velocity")
    if _has_any(t, ["코리올리", "coriolis"]):
        unknowns.append("coriolis_acceleration")
    if _has_any(t, ["법선가속도", "normal acceleration"]):
        unknowns.append("normal_acceleration")
    if _has_any(t, ["접선가속도", "tangential acceleration"]):
        unknowns.append("tangential_acceleration")
    if not unknowns:
        unknowns.append("auto")


    pulley_topology = _infer_pulley_topology(t, knowns, flags)
    friction_type = _infer_friction_type(t, flags)
    body_shape = infer_body_shape(problem_text)
    force_dir = infer_direction_label(problem_text)
    surface_type = "incline" if flags["incline"] else "table" if flags["table"] else None
    launch_height = _infer_launch_height(knowns, t)
    landing_height = _infer_landing_height(knowns, t)
    coordinate_data = _infer_coordinate_data(knowns, t)
    requested_outputs = _infer_requested_outputs(t)
    launch_angle_deg, launch_angle_source = _infer_launch_angle(knowns, t)
    if launch_angle_deg is not None and "theta" not in knowns:
        knowns["theta"] = Quantity("theta", launch_angle_deg, "deg", launch_angle_source or "inferred launch angle")

    c = CanonicalProblem(
        knowns=knowns,
        flags=flags,
        unknowns=_uniq(unknowns),
        raw_text=problem_text,
        surface_type=surface_type,
        pulley_topology=pulley_topology,
        friction_type=friction_type,
        body_shape=body_shape,
        launch_height=launch_height,
        landing_height=landing_height,
        force_direction=force_dir,
        displacement_direction="motion" if force_dir else None,
        coordinate_data=coordinate_data,
        requested_outputs=requested_outputs,
        launch_angle_deg=launch_angle_deg,
        launch_angle_source=launch_angle_source,
    )

    # Phase 41: 충돌 문맥에서 익명 진행 물체의 속도("2kg 물체가 4m/s로 …와 충돌")는
    # 일반 속도(v0)로 잡히므로 v1 별칭을 canonical에 심는다 — solver 지역 처리가 아니라
    # 여기서 해야 방정식 generator·검증·출처 추적이 전부 같은 값을 본다.
    if flags["collision"] and "v1" not in knowns and "v0" in knowns:
        v0q = knowns["v0"]
        knowns["v1"] = Quantity("v1", v0q.value, v0q.unit or "m/s", (v0q.source_text or "") + " (충돌 진행 물체 → v1)")

    if pulley_topology == "incline_hanging_candidate":
        c.system_type = "incline_hanging_candidate"
    elif pulley_topology == "ambiguous_pulley":
        c.system_type = "ambiguous_pulley"
    elif pulley_topology == "massive_pulley_atwood":
        c.system_type = "massive_pulley_atwood"
    elif pulley_topology == "incline_hanging":
        c.system_type = "pulley_incline_hanging"
    elif pulley_topology == "table_hanging":
        c.system_type = "pulley_table_hanging"
    elif pulley_topology == "atwood":
        c.system_type = "pulley_atwood"
    elif flags["coriolis"] or (flags["slot_pin"] and flags["relative_acceleration"]):
        c.system_type = "coriolis_relative_motion"
    elif flags["relative_acceleration"] and not flags["polar"]:
        c.system_type = "relative_acceleration_translation"
    elif flags["instant_center"]:
        c.system_type = "instant_center_velocity"
    elif flags["slot_pin"] or (flags["relative_motion"] and flags["polar"]):
        c.system_type = "slot_pin_relative_motion"
    elif flags["plane_rigid_body"] and flags["plane_acceleration"]:
        c.system_type = "plane_rigid_body_acceleration"
    elif flags["plane_rigid_body"]:
        c.system_type = "plane_rigid_body_velocity"
    elif flags["polar"]:
        c.system_type = "polar_kinematics"
    elif flags["spring"] and flags["vibration"]:
        c.system_type = "spring_mass_vibration"
    elif flags["spring"] and ("x" in knowns or "A" in knowns) and "m" in knowns and "k" in knowns and _has_any(t, ["속도", "speed", "velocity"]):
        c.system_type = "spring_energy"
    elif flags["spring"] and ("x" in knowns or "A" in knowns) and "k" in knowns and _has_any(t, ["저장된 에너지", "탄성 에너지", "탄성에너지", "탄성 퍼텐셜", "elastic"]):
        # E = ½kx² 직접 질문 — 질량 불필요 (Phase 39)
        c.system_type = "spring_energy"
    elif (flags["friction"] or "mu" in knowns) and not flags["incline"] and not flags["pulley"] and "mu" in knowns and ("m" in knowns or ("m1" in knowns and "m2" not in knowns)) and _has_any(t, ["마찰력은", "마찰력을", "마찰력이 얼마", "friction force"]):
        # 수평면 운동마찰력 f = μmg 직접 질문 (Phase 39)
        c.system_type = "horizontal_friction_force"
    elif flags["curve"] and flags["banked"] and flags["no_friction"]:
        c.system_type = "banked_curve_no_friction"
    elif flags["curve"] and (flags["flat_curve"] or flags["friction"] or "mu" in knowns):
        c.system_type = "flat_curve_friction"
    elif flags["rolling"] and flags["no_slip"] and ("h" in knowns or c.launch_height is not None):
        if ("I" in knowns) or ("R" in knowns and body_shape):
            c.system_type = "rolling_energy_general"
        else:
            c.system_type = "pure_rolling_energy"
        c.subtype = "rolling_on_incline"
    elif flags["incline"]:
        c.system_type = "particle_on_incline"
        c.subtype = "no_friction" if flags["no_friction"] else "with_friction" if flags["friction"] else "unknown_friction"
    elif flags["vertical_circle"]:
        c.system_type = "vertical_circle"
        c.subtype = "top" if flags["top"] else "bottom" if flags["bottom"] else None
    elif flags["projectile"]:
        c.system_type = "projectile_motion"
        c.subtype = "same_level" if _has_any(t, ["같은 높이", "same level"]) else "general"
    elif (flags["work"] or ("F" in knowns and "s" in knowns)) and _has_any(t, ["속도", "speed", "velocity"]) and "m" in knowns and ("W" in knowns or ("F" in knowns and "s" in knowns)):
        c.system_type = "work_energy_speed"
    elif flags["collision"]:
        c.system_type = "collision_1d"
    elif flags["impulse"] or ("F" in knowns and "t" in knowns and "m" in knowns and _has_any(t, ["최종속도", "나중 속도", "속도"])):
        c.system_type = "impulse_momentum"
    elif _looks_like_single_particle_newton(knowns, t, flags):
        c.system_type = "single_particle_newton"
    elif flags["work"] and "F" in knowns and "s" in knowns:
        c.system_type = "constant_force_work"
    elif flags["kinematics"] or _looks_like_kinematics(knowns, t):
        c.system_type = "constant_acceleration_1d"
    elif flags["rotation_fixed_axis"]:
        c.system_type = "fixed_axis_rotation"
    elif flags["rolling"]:
        c.system_type = "rolling"
    else:
        c.system_type = "unknown"

    c.objects = _objects_from_knowns(c)
    c.assumptions = _default_assumptions(c)
    c.missing_info = _missing_info(c)
    c.confidence = "높음" if not c.missing_info and c.system_type != "unknown" else "보통" if c.system_type != "unknown" else "낮음"
    return c



def _infer_pulley_topology(t: str, knowns: dict, flags: dict) -> str | None:
    if flags.get("vertical_circle"):
        return None
    # Phase 25: 경사면 위 물체 + 매달린 물체가 있지만 줄/도르래가
    # 명시되지 않으면 바로 풀지 않고 후보로 진단합니다.
    if (not flags.get("pulley")) and flags.get("incline") and flags.get("hanging") and ("m1" in knowns and "m2" in knowns):
        if any(w in t for w in ["m2가 아래", "m2가 내려", "m1이 경사면 아래", "m1가 경사면 아래", "경사면 아래로 내려"]):
            return "incline_hanging"
        if any(w in t for w in ["가속도", "장력", "운동", "마찰", "acceleration", "tension"]):
            return "incline_hanging_candidate"
    # 한국어 표준 표현: "수평 테이블/책상 위 물체 + 실/줄로 연결 + 매달린 물체"는
    # 도르래라는 단어가 없어도 table-hanging pulley 후보로 본다.
    # 단, 도르래가 명시되어 있으면 아래 정식 topology 판정(양쪽 매달림=Atwood 우선)에
    # 맡긴다 — 방해문("책상 위에서 준비했다")의 table flag가 Atwood를 가로채는 것 방지.
    if (not flags.get("pulley")) and flags.get("table") and flags.get("hanging") and flags.get("string") and ("m1" in knowns and "m2" in knowns):
        return "table_hanging"
    if not flags.get("pulley"):
        return None
    if flags.get("massive_pulley") or ("I" in knowns and ("R" in knowns or "Rp" in knowns) and ("m1" in knowns and "m2" in knowns)):
        return "massive_pulley_atwood"
    if _has_any(t, ["양쪽", "두 물체가 양쪽에 매달", "m1과m2가양쪽", "m1과 m2가 양쪽", "양쪽에 매달려", "both hanging", "atwood"]):
        return "atwood"
    if flags.get("incline") and flags.get("hanging"):
        return "incline_hanging"
    if (flags.get("table") or _has_table_surface_phrase(t)) and flags.get("hanging"):
        return "table_hanging"
    if flags.get("hanging") and _has_any(t, ["하나는 매달", "하나가 매달", "매달린 물체"]):
        return "table_hanging"
    if "m1" in knowns and "m2" in knowns:
        return "ambiguous_pulley"
    return "ambiguous_pulley"


def _infer_friction_type(t: str, flags: dict) -> str | None:
    if flags.get("no_friction"):
        return "none"
    if _has_any(t, ["정지마찰", "정지 마찰", "최대정지마찰", "mu_s", "μs", "static friction"]):
        return "static"
    if _has_any(t, ["운동마찰", "운동 마찰", "mu_k", "μk", "kinetic friction"]):
        return "kinetic"
    if flags.get("friction"):
        return "unspecified"
    return None


def _infer_launch_height(knowns: dict, t: str) -> float | None:
    if "h0" in knowns:
        return knowns["h0"].value
    if _has_any(t, ["절벽", "높이"]) and "h" in knowns:
        return knowns["h"].value
    # "X m 아래(지점)에 떨어졌다" — 추출기가 h=X로 기록 (Δy=-h → 발사 높이 h)
    if "h" in knowns and getattr(knowns["h"], "source_text", None) and "발사점 아래 착지" in knowns["h"].source_text:
        return knowns["h"].value
    return 0.0 if _has_any(t, ["같은 높이", "지면에서", "ground level"]) else None


def _infer_landing_height(knowns: dict, t: str) -> float | None:
    if "yf" in knowns:
        return knowns["yf"].value
    if _has_any(t, ["지면", "바닥", "ground"]):
        return 0.0
    if _has_any(t, ["같은 높이", "same level"]):
        return _infer_launch_height(knowns, t) or 0.0
    if _has_any(t, ["사거리", "수평거리", "range"]) and _infer_launch_height(knowns, t) is not None:
        return 0.0
    # Phase 41: "비행시간은?" = 착지까지의 시간 — 발사 높이가 있으면 지면 착지로 본다.
    if _has_any(t, ["비행시간", "떨어질 때까지", "착지할 때까지", "time of flight"]) and _infer_launch_height(knowns, t) is not None:
        return 0.0
    above = re.search(r"(\d+(?:\.\d+)?)\s*m\s*(?:위|높은\s*곳|높은\s*지점)[^.]{0,10}(?:떨어|착지|도달)", t)
    if above:
        return float(above.group(1))
    return None


def _infer_coordinate_data(knowns: dict, t: str) -> dict:
    data = {}
    # Explicit component grammar: vAx=, vAy=, rBAx=, rBAy= style inputs.
    for key in ["vAx", "vAy", "aAx", "aAy", "rBAx", "rBAy"]:
        if key in knowns:
            data[key] = knowns[key].value
    parsed = parse_coordinate_data_from_text(t).to_dict()
    # Natural-language vectors override scalar fallback but not explicit components.
    for key, value in parsed.items():
        if key not in data:
            data[key] = value
    return data




def _looks_like_single_particle_newton(knowns: dict, t: str, flags: dict) -> bool:
    if any(flags.get(k) for k in ["incline", "pulley", "projectile", "collision", "spring", "rolling", "curve", "rotation_fixed_axis", "polar", "plane_rigid_body"]):
        return False
    keys = {"m", "F", "a"}.intersection(knowns.keys())
    asks = any(w in t for w in ["가속도", "필요한 알짜힘", "필요한 힘", "합력", "알짜힘", "힘은", "힘을 구", "질량은", "질량을", "acceleration", "net force", "mass"])
    multiple_forces = len(re.findall(r"-?\d+(?:\.\d+)?\s*N", t, flags=re.IGNORECASE)) >= 2
    return asks and (len(keys) >= 2 or multiple_forces)


def _looks_like_kinematics(knowns: dict, t: str) -> bool:
    kin_keys = {"v0", "vf", "v", "a", "t", "s"}
    if len(kin_keys.intersection(knowns.keys())) >= 3:
        return True
    return any(w in t for w in ["초속도", "최종속도", "등가속도", "몇 초", "몇초"])


def _objects_from_knowns(c: CanonicalProblem) -> list[dict]:
    objs = []
    if "m1" in c.knowns:
        objs.append({"name": "object_1", "mass": c.knowns["m1"].value, "unit": "kg"})
    if "m2" in c.knowns:
        objs.append({"name": "object_2", "mass": c.knowns["m2"].value, "unit": "kg"})
    if not objs and "m" in c.knowns:
        objs.append({"name": "body", "mass": c.knowns["m"].value, "unit": "kg"})
    return objs


def _default_assumptions(c: CanonicalProblem) -> list[str]:
    a = ["중력가속도 g = 9.81 m/s² 기본값 사용"]
    if c.system_type == "particle_on_incline":
        a.append("블록을 질점으로 모델링")
        if c.subtype == "no_friction":
            a.append("마찰력 없음")
    if c.system_type == "pulley_table_hanging":
        a.extend(["줄은 질량이 없고 늘어나지 않음", "도르래는 질량과 마찰을 무시", "수평면 위 물체 + 매달린 물체"])
    if c.system_type == "pulley_atwood":
        a.extend(["질량 없는 줄과 도르래", "두 물체가 도르래 양쪽에 매달린 Atwood 계"])
    if c.system_type == "pulley_incline_hanging":
        a.extend(["경사면 위 물체와 매달린 물체가 줄로 연결됨", "마찰 방향은 운동 가정에 따라 검토"])
    if c.system_type == "ambiguous_pulley":
        a.append("도르래 구조가 모호하여 추가 조건 필요")
    if c.system_type == "incline_hanging_candidate":
        a.append("경사면 위 물체와 매달린 물체가 함께 등장하지만 줄/도르래 연결 여부가 명시되지 않음")
    if c.system_type == "single_particle_newton":
        a.append("물체를 단일 질점으로 보고 알짜힘 F=ma 적용")
    if c.system_type == "pure_rolling_energy":
        a.extend(["미끄러지지 않는 순수 구름", "정지마찰은 일을 하지 않는 이상적 조건", "강체 종류 또는 관성모멘트가 필요함"])
    if c.system_type == "constant_acceleration_1d":
        a.extend(["직선 운동", "가속도는 일정"])
    if c.system_type == "projectile_motion":
        a.extend(["공기저항 무시", "수평방향 가속도 0", "수직방향 가속도 -g"])
    if c.system_type == "fixed_axis_rotation":
        a.append("고정축 주위 회전")
    if c.system_type == "spring_mass_vibration":
        a.extend(["감쇠 없음", "외력 없음", "평형 위치 기준 1자유도 운동"])
    if c.system_type == "spring_energy":
        a.extend(["마찰 없음", "스프링 탄성에너지가 운동에너지로 전환"])
    if c.system_type in {"flat_curve_friction", "banked_curve_no_friction"}:
        a.append("등속 원운동으로 모델링")
    if c.system_type == "relative_acceleration_translation":
        a.extend(["A에 대한 B의 상대가속도를 병진 기준계에서 더함", "방향각이 없으면 기본형은 같은 직선상 성분으로 계산"])
    if c.system_type == "coriolis_relative_motion":
        a.extend(["회전 기준계에서 관찰한 상대운동", "Coriolis 항 2ωv_rel은 상대속도와 회전에 의해 생김"])
    if c.system_type == "plane_rigid_body_acceleration":
        a.extend(["평면강체의 두 점 가속도 관계", "접선 성분 αr과 법선 성분 ω²r을 분리"])
    if c.system_type == "massive_pulley_atwood":
        a.extend(["줄은 미끄러지지 않아 a=αR", "도르래 관성모멘트가 등가질량 I/R²로 작용"])
    if c.system_type == "rolling_energy_general":
        a.extend(["미끄러지지 않는 순수 구름", "문제에 주어진 I를 사용해 병진+회전 에너지를 계산"])
    if c.system_type == "polar_kinematics":
        a.extend(["평면 운동을 극좌표 r-θ 성분으로 분해", "e_r, e_θ 방향은 위치에 따라 회전함"])
    if c.system_type == "instant_center_velocity":
        a.extend(["평면강체의 순간중심을 기준으로 그 순간만 순수 회전처럼 해석", "거리 r은 순간중심에서 해당 점까지의 수직거리"])
    if c.system_type == "slot_pin_relative_motion":
        a.extend(["슬롯을 따라 미끄러지는 핀을 회전 좌표계의 극좌표 운동으로 모델링", "r 방향 상대속도와 θ 방향 회전속도를 동시에 고려"])
    if c.system_type == "plane_rigid_body_velocity":
        a.extend(["평면강체 속도 관계 v_B = v_A + ω×r_B/A 사용", "이번 MVP는 속도 크기 기본형부터 지원"])

    return a


def _missing_info(c: CanonicalProblem) -> list[str]:
    missing = []
    if c.system_type == "particle_on_incline":
        if "theta" not in c.knowns:
            missing.append("경사각 θ")
        if c.subtype == "with_friction" and "mu" not in c.knowns:
            missing.append("마찰계수 μ")
        if c.subtype == "unknown_friction":
            missing.append("마찰 유무")
    elif c.system_type in {"pulley_table_hanging", "pulley_atwood", "pulley_incline_hanging"}:
        if "m1" not in c.knowns or "m2" not in c.knowns:
            missing.append("두 물체의 질량 m1, m2")
        if c.system_type == "pulley_table_hanging" and c.friction_type is None and not (c.flags.get("no_friction") or "mu" in c.knowns or "mu_k" in c.knowns or "mu_s" in c.knowns):
            missing.append("수평면 마찰 유무")
        if c.system_type == "pulley_incline_hanging" and "theta" not in c.knowns:
            missing.append("경사면 각도 θ")
    elif c.system_type == "ambiguous_pulley":
        missing.append("도르래 구조: 양쪽 매달림/수평면-매달림/경사면-매달림 중 하나")
    elif c.system_type == "incline_hanging_candidate":
        missing.append("줄/도르래 연결 여부")
        missing.append("두 물체가 같은 줄로 연결되어 있는지")
    elif c.system_type == "single_particle_newton":
        if len({"m", "F", "a"}.intersection(c.knowns.keys())) < 2:
            missing.append("m, F, a 중 두 개")
    elif c.system_type == "pure_rolling_energy":
        if "h" not in c.knowns and c.launch_height is None:
            missing.append("높이 변화 h")
        if "I" not in c.knowns and not c.body_shape:
            missing.append("물체 종류 또는 관성모멘트 I")
    elif c.system_type == "vertical_circle":
        if "R" not in c.knowns:
            missing.append("반지름 R")
        if "v" not in c.knowns and "minimum_speed" not in c.unknowns:
            missing.append("해당 지점의 속도 v 또는 최소속도 조건")
        if c.subtype is None:
            missing.append("최고점/최저점 위치")
    elif c.system_type == "collision_1d":
        if "m1" not in c.knowns or "m2" not in c.knowns:
            missing.append("두 물체의 질량")
        if "v1" not in c.knowns or "v2" not in c.knowns:
            missing.append("충돌 전 속도 v1, v2")
        if not (c.flags.get("perfectly_inelastic") or c.flags.get("elastic") or "e" in c.knowns):
            missing.append("완전비탄성/완전탄성/반발계수 e 중 하나")
    elif c.system_type == "constant_acceleration_1d":
        if len({"v0", "vf", "a", "t", "s"}.intersection(c.knowns.keys())) < 3:
            missing.append("등가속도 변수 3개 이상: v0, vf, a, t, s")
    elif c.system_type == "projectile_motion":
        # 수평 발사의 time-only 답은 연직 운동만으로 결정된다. canonical에
        # stale v0 누락을 남기면 풀이 성공 뒤에도 UI가 불필요한 입력을 요구한다.
        requested = set(c.requested_outputs or [])
        if (
            requested.intersection({"range", "distance"})
            and "v0" not in c.knowns
            and "v" not in c.knowns
        ):
            missing.append("초속도 v0")
        if "theta" not in c.knowns and c.launch_angle_deg is None:
            missing.append("발사각 θ 또는 발사 방향")
    elif c.system_type == "constant_force_work":
        if "F" not in c.knowns:
            missing.append("힘 F")
        if "s" not in c.knowns:
            missing.append("이동거리 s")
        if c.force_direction is None:
            missing.append("힘과 변위 사이 방향 또는 각도")
    elif c.system_type == "fixed_axis_rotation":
        # Phase 40: 회전 kinematics(ω=ω₀+αt, v=ωr)로 풀리는 조합이면 τ·I는 필요 없다.
        kin_omega = ("alpha" in c.knowns and "t" in c.knowns and "angular_velocity" in (c.requested_outputs or []))
        kin_speed = ("omega" in c.knowns and ("r" in c.knowns or "R" in c.knowns) and "alpha" not in c.knowns)
        if not (kin_omega or kin_speed):
            if "tau" not in c.knowns:
                missing.append("토크 τ")
            if "I" not in c.knowns:
                missing.append("관성모멘트 I")
    elif c.system_type == "spring_mass_vibration":
        if "k" not in c.knowns:
            missing.append("스프링 상수 k")
        if "m" not in c.knowns:
            missing.append("질량 m")
    elif c.system_type == "spring_energy":
        if "k" not in c.knowns:
            missing.append("스프링 상수 k")
        # Phase 40: E=½kx²만 묻는 경우 질량은 필요 없다.
        if "m" not in c.knowns and "elastic_energy" not in (c.requested_outputs or []):
            missing.append("질량 m")
        if "x" not in c.knowns and "A" not in c.knowns:
            missing.append("압축량/변위 x")
    elif c.system_type == "flat_curve_friction":
        if "R" not in c.knowns:
            missing.append("커브 반지름 R")
        if "mu" not in c.knowns:
            missing.append("마찰계수 μ")
    elif c.system_type == "banked_curve_no_friction":
        if "R" not in c.knowns:
            missing.append("커브 반지름 R")
        if "theta" not in c.knowns:
            missing.append("뱅크각 θ")
    elif c.system_type == "work_energy_speed":
        if "m" not in c.knowns:
            missing.append("질량 m")
        if "W" not in c.knowns and not ("F" in c.knowns and "s" in c.knowns):
            missing.append("일 W 또는 힘 F와 거리 s")
    elif c.system_type == "relative_acceleration_translation":
        if "aA" not in c.knowns:
            missing.append("기준점 A의 가속도 aA")
        if "arel" not in c.knowns:
            missing.append("A에 대한 B의 상대가속도 a_rel")
    elif c.system_type == "coriolis_relative_motion":
        if "omega" not in c.knowns:
            missing.append("회전 기준계 각속도 ω")
        if "vrel" not in c.knowns and "rdot" not in c.knowns:
            missing.append("상대속도 v_rel 또는 r_dot")
    elif c.system_type == "plane_rigid_body_acceleration":
        if "R" not in c.knowns and "r" not in c.knowns and not ("rBAx" in c.coordinate_data and "rBAy" in c.coordinate_data):
            missing.append("두 점 사이 거리 r_B/A")
        if "omega" not in c.knowns:
            missing.append("강체 각속도 ω")
        if "alpha" not in c.knowns:
            missing.append("강체 각가속도 α")
    elif c.system_type == "massive_pulley_atwood":
        if "m1" not in c.knowns or "m2" not in c.knowns:
            missing.append("두 물체의 질량 m1, m2")
        if "I" not in c.knowns and "Ip" not in c.knowns:
            missing.append("도르래 관성모멘트 I")
        if "R" not in c.knowns and "Rp" not in c.knowns:
            missing.append("도르래 반지름 R")
    elif c.system_type == "rolling_energy_general":
        if "h" not in c.knowns and c.launch_height is None:
            missing.append("높이 변화 h")
        if "I" in c.knowns:
            if "m" not in c.knowns:
                missing.append("질량 m")
            if "R" not in c.knowns:
                missing.append("구름 반지름 R")
        elif not c.body_shape:
            missing.append("물체 종류 또는 관성모멘트 I")
    elif c.system_type == "polar_kinematics":
        if "R" not in c.knowns and "r" not in c.knowns:
            missing.append("극좌표 반지름 r")
        if "omega" not in c.knowns and "thetadot" not in c.knowns:
            missing.append("각속도 θ_dot 또는 ω")
        # rdot, rddot, alpha는 없으면 0으로 둘 수 있게 solver에서 보완합니다.
    elif c.system_type == "instant_center_velocity":
        if "R" not in c.knowns and "r" not in c.knowns:
            missing.append("순간중심에서 점까지 거리 r")
        if "omega" not in c.knowns and "v" not in c.knowns and "vB" not in c.knowns:
            missing.append("각속도 ω 또는 점의 속도 v")
    elif c.system_type == "slot_pin_relative_motion":
        if "R" not in c.knowns and "r" not in c.knowns:
            missing.append("슬롯 내 핀의 위치 r")
        if "omega" not in c.knowns:
            missing.append("슬롯/막대의 각속도 ω")
        if "rdot" not in c.knowns:
            missing.append("슬롯을 따라 미끄러지는 상대속도 r_dot")
    elif c.system_type == "plane_rigid_body_velocity":
        if "R" not in c.knowns and "r" not in c.knowns and not ("rBAx" in c.coordinate_data and "rBAy" in c.coordinate_data):
            missing.append("두 점 사이 거리 r_B/A")
        if "omega" not in c.knowns:
            missing.append("강체 각속도 ω")
        if "vA" not in c.knowns and "vAx" not in c.knowns and "vAy" not in c.knowns and "vAx" not in c.coordinate_data and "vAy" not in c.coordinate_data and not any(phrase in c.raw_text for phrase in ["고정점", "A점이 고정", "A점은 고정", "A점 고정", "A is fixed"]):
            missing.append("A점 속도 벡터 또는 A점 고정 조건")
    elif c.system_type == "unknown":
        missing.append("문제 유형을 판별할 핵심 단서")
    return missing


def _uniq(items):
    out = []
    seen = set()
    for x in items:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out
