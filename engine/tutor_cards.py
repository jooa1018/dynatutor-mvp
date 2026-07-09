from dataclasses import dataclass, field
from engine.models import CanonicalProblem, LegacyHint


@dataclass
class DiagnosisCards:
    fbd: list[str] = field(default_factory=list)
    coordinate_guide: list[str] = field(default_factory=list)
    applicable_equations: list[str] = field(default_factory=list)
    not_applicable_equations: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    next_questions: list[str] = field(default_factory=list)


def build_diagnosis_cards(c: CanonicalProblem, h: LegacyHint, solver) -> DiagnosisCards:
    cards = DiagnosisCards()
    cards.applicable_equations.extend(h.applicable_equations)
    cards.not_applicable_equations.extend(h.not_applicable_equations)
    cards.cautions.extend(h.cautions)
    cards.next_questions.extend(c.missing_info)

    if c.system_type == "particle_on_incline":
        cards.fbd = ["중력 mg", "수직항력 N"]
        if c.subtype == "with_friction":
            cards.fbd.append("마찰력 f")
        cards.coordinate_guide = ["x축: 경사면을 따라 아래 방향", "y축: 경사면에 수직인 방향"]
    elif c.system_type == "pulley_table_hanging":
        cards.fbd = ["수평면 위 물체: 장력 T", "매달린 물체: 중력 m2g, 장력 T"]
        cards.coordinate_guide = ["두 물체의 가속도 크기는 같다고 둡니다.", "매달린 물체가 내려가는 방향을 양의 방향으로 잡으면 식이 단순합니다."]
    elif c.system_type == "pure_rolling_energy":
        cards.fbd = ["중력 mg", "수직항력 N", "정지마찰력 f_s"]
        cards.coordinate_guide = ["질량중심 G의 병진 운동", "질량중심 기준 회전 운동", "미끄럼 없음: v_G=ωR"]
    elif c.system_type == "vertical_circle":
        cards.fbd = ["중력 mg", "장력 T 또는 수직항력 N"]
        cards.coordinate_guide = ["중심 방향을 양의 방향으로 둡니다.", "최고점과 최저점은 중심 방향이 서로 반대입니다."]
    elif c.system_type == "collision_1d":
        cards.fbd = ["충돌 시간 동안 외부 충격량이 무시 가능한지 확인"]
        cards.coordinate_guide = ["충돌선 방향을 +x로 잡고, 부호가 있는 속도를 사용합니다."]
    elif c.system_type == "constant_acceleration_1d":
        cards.fbd = ["힘 분석이 필요한 문제라면 별도 FBD 필요", "순수 운동학 문제라면 위치-속도-가속도 관계에 집중"]
        cards.coordinate_guide = ["운동 방향을 +x로 정합니다.", "반대 방향 속도/가속도는 음수로 입력합니다."]
    elif c.system_type == "projectile_motion":
        cards.fbd = ["공기저항 무시 시 중력 mg만 작용"]
        cards.coordinate_guide = ["x축: 수평 방향", "y축: 위쪽 양의 방향", "a_x=0, a_y=-g"]
    elif c.system_type == "constant_force_work":
        cards.fbd = ["힘 F", "이동방향 변위 s", "힘과 변위 사이 각도 θ"]
        cards.coordinate_guide = ["변위 방향을 기준으로 힘의 성분 Fcosθ를 사용합니다."]
    elif c.system_type == "fixed_axis_rotation":
        cards.fbd = ["회전축 기준 토크 τ", "축 기준 관성모멘트 I"]
        cards.coordinate_guide = ["반시계방향 또는 시계방향 중 하나를 +로 정합니다."]
    elif c.system_type == "impulse_momentum":
        cards.fbd = ["짧은 시간 작용하는 평균힘 F", "작용시간 Δt", "초기/최종 운동량"]
        cards.coordinate_guide = ["힘과 속도의 방향 부호를 같은 축에서 정합니다."]

    elif c.system_type == "work_energy_speed":
        cards.fbd = ["알짜일을 만드는 힘들", "초기/최종 속도", "질량 m"]
        cards.coordinate_guide = ["운동방향을 +로 정합니다.", "일은 부호가 있으므로 물체를 빠르게 하면 +, 느리게 하면 -로 둡니다."]
    elif c.system_type in {"spring_mass_vibration", "spring_energy"}:
        cards.fbd = ["스프링 복원력 F_s = -kx", "질량 m", "기준 평형 위치"]
        cards.coordinate_guide = ["x=0을 평형 위치로 잡습니다.", "오른쪽 또는 늘어나는 방향을 +x로 정합니다."]
    elif c.system_type == "flat_curve_friction":
        cards.fbd = ["중력 mg", "수직항력 N", "중심방향 정지마찰 f_s"]
        cards.coordinate_guide = ["반지름 안쪽, 즉 중심 방향을 +r로 잡습니다.", "정지마찰의 최대값이 구심력 한계입니다."]
    elif c.system_type == "banked_curve_no_friction":
        cards.fbd = ["중력 mg", "수직항력 N", "수직항력의 수평 성분"]
        cards.coordinate_guide = ["수평 중심방향과 수직방향으로 N을 분해합니다.", "수평 성분은 구심력, 수직 성분은 mg와 평형입니다."]
    elif c.system_type == "polar_kinematics":
        cards.fbd = ["위치 방향 단위벡터 e_r", "접선 방향 단위벡터 e_θ", "r, r_dot, θ_dot"]
        cards.coordinate_guide = ["e_r: 원점에서 입자까지 향하는 방향", "e_θ: θ가 증가하는 접선 방향", "두 단위벡터가 회전하므로 가속도에 추가항이 생깁니다."]
    elif c.system_type == "instant_center_velocity":
        cards.fbd = ["순간중심 IC", "속도를 구할 점 P", "IC에서 P까지 거리 r"]
        cards.coordinate_guide = ["그 순간에는 IC를 중심으로 회전한다고 보고 v=ωr을 씁니다.", "속도 방향은 IC-P 선에 수직입니다."]
    elif c.system_type == "slot_pin_relative_motion":
        cards.fbd = ["회전 슬롯", "슬롯 안 핀", "슬롯 방향 상대속도 r_dot", "회전에 의한 접선속도 rω"]
        cards.coordinate_guide = ["슬롯 방향을 e_r, 그에 수직한 방향을 e_θ로 둡니다.", "절대속도는 상대속도와 회전으로 생기는 속도의 벡터합입니다."]
    elif c.system_type == "plane_rigid_body_velocity":
        cards.fbd = ["기준점 A의 속도 v_A", "A에서 B까지 위치벡터 r_B/A", "강체 각속도 ω"]
        cards.coordinate_guide = ["v_B = v_A + ω×r_B/A를 사용합니다.", "ω×r 성분은 r_B/A에 수직입니다."]
    elif c.system_type == "relative_acceleration_translation":
        cards.fbd = ["기준점 A의 가속도 a_A", "A에 대한 B의 상대가속도 a_B/A", "B점 절대가속도 a_B"]
        cards.coordinate_guide = ["같은 직선 위 기본형은 a_B=a_A+a_B/A입니다.", "방향각이 있으면 x-y 성분으로 나눠 벡터합합니다."]
        cards.applicable_equations.extend(["a_B = a_A + a_B/A"])
    elif c.system_type == "coriolis_relative_motion":
        cards.fbd = ["회전 기준계 각속도 ω", "상대속도 v_rel", "코리올리 가속도 2ωv_rel", "법선항 rω²"]
        cards.coordinate_guide = ["e_r 방향과 e_θ 방향을 먼저 정합니다.", "상대속도가 슬롯 방향이면 코리올리 항은 그에 수직인 접선 방향입니다."]
        cards.applicable_equations.extend(["a_C = 2ωv_rel", "a = a_O + α×r + ω×(ω×r) + 2ω×v_rel + a_rel"])
    elif c.system_type == "plane_rigid_body_acceleration":
        cards.fbd = ["기준점 A의 가속도 a_A", "접선 성분 α×r", "법선 성분 ω²r", "B점 가속도 a_B"]
        cards.coordinate_guide = ["a_t=αr은 r_B/A에 수직입니다.", "a_n=ω²r은 B에서 A를 향합니다."]
        cards.applicable_equations.extend(["a_B = a_A + α×r_B/A + ω×(ω×r_B/A)", "a_t=αr", "a_n=ω²r"])
    elif c.system_type == "massive_pulley_atwood":
        cards.fbd = ["m1: T1, m1g", "m2: T2, m2g", "도르래: (T2-T1)R = Iα"]
        cards.coordinate_guide = ["질량 있는 도르래에서는 T1과 T2가 같지 않습니다.", "줄이 미끄러지지 않으면 a=αR입니다."]
        cards.applicable_equations.extend(["a=αR", "(T2-T1)R=Iα", "a=(m2-m1)g/(m1+m2+I/R²)"])
        cards.not_applicable_equations.append("T1 = T2")
    elif c.system_type == "rolling_energy_general":
        cards.fbd = ["질량중심 속도 v_G", "회전속도 ω", "관성모멘트 I_G", "높이 변화 h"]
        cards.coordinate_guide = ["미끄러지지 않을 때만 v_G=ωR을 씁니다.", "I가 주어지면 원판/고리 가정 대신 주어진 I를 사용합니다."]
        cards.applicable_equations.extend(["mgh=1/2mv_G²+1/2I_Gω²", "v_G=ωR", "v_G=sqrt(2mgh/(m+I_G/R²))"])

    if solver:
        cards.cautions.append(f"선택된 MVP solver: {solver.name} ({solver.reason})")
    else:
        cards.cautions.append("현재는 진단만 가능하고 계산 solver는 아직 연결되지 않은 유형입니다.")

    cards.applicable_equations = _uniq(cards.applicable_equations)
    cards.not_applicable_equations = _uniq(cards.not_applicable_equations)
    cards.cautions = _uniq(cards.cautions)
    return cards


def _uniq(items):
    out = []
    seen = set()
    for x in items:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out
