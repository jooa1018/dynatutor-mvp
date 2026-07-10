from engine.models import CanonicalProblem, LegacyHint


def make_legacy_hints(c: CanonicalProblem) -> LegacyHint:
    """기존 앱의 좋은 아이디어를 '정답'이 아니라 힌트 후보로만 제공한다."""
    h = LegacyHint()
    flags = c.flags

    if c.system_type == "particle_on_incline":
        h.problem_type_candidates.append("경사면 위 질점 운동")
        h.detected_cues.extend(["경사면", "힘 분해", "뉴턴 제2법칙"])
        h.applicable_equations.extend(["ΣF_x = ma", "ΣF_y = 0", "mg sinθ", "mg cosθ"])
        h.cautions.append("좌표축을 경사면 방향/수직 방향으로 잡으면 힘 분해가 단순해집니다.")
        if c.subtype == "no_friction":
            h.applicable_equations.append("a = g sinθ")
            h.not_applicable_equations.append("f = μN : 마찰 없음 조건에서는 사용하지 않음")
        elif c.subtype == "with_friction":
            h.applicable_equations.extend(["f_k = μN", "a = g(sinθ - μcosθ)"])
            h.cautions.append("마찰 방향은 실제 운동 또는 운동하려는 경향을 방해하는 방향입니다.")

    if c.system_type == "pulley_table_hanging":
        h.problem_type_candidates.append("수평면 블록-도르래 연결계")
        h.detected_cues.extend(["도르래", "줄 장력", "공통 가속도"])
        h.applicable_equations.extend(["T = m1 a", "m2 g - T = m2 a"])
        h.not_applicable_equations.append("두 물체를 하나의 질점처럼 mg = ma로 처리하지 않음")
        h.cautions.append("물체별 FBD를 따로 그리고 줄의 가속도 구속조건을 확인하세요.")

    if c.system_type == "pure_rolling_energy":
        h.problem_type_candidates.append("미끄럼 없는 순수 구름 운동")
        h.detected_cues.extend(["구름", "미끄러지지 않음", "병진+회전 에너지"])
        h.applicable_equations.extend(["v_G = ωR", "a_G = αR", "mgh = 1/2 m v_G² + 1/2 I_G ω²"])
        h.not_applicable_equations.append("f_k = μ_kN : 순수 구름에서는 보통 운동마찰이 아니라 정지마찰")
        h.cautions.append("v=ωR은 미끄러지지 않는 조건이 명확할 때만 사용하세요.")

    if c.system_type == "rolling" and flags.get("slipping"):
        h.problem_type_candidates.append("미끄럼 동반 회전")
        h.applicable_equations.extend(["ΣF = ma_G", "ΣM_G = I_Gα", "f_k = μ_kN"])
        h.not_applicable_equations.extend(["v_G = ωR", "a_G = αR"])
        h.cautions.append("미끄러짐이 있으면 순수 구름 구속조건을 적용하면 안 됩니다.")

    if c.system_type == "vertical_circle":
        h.problem_type_candidates.append("수직 원운동")
        h.detected_cues.extend(["중심방향", "ΣF_n = mv²/R"])
        if c.subtype == "top":
            h.applicable_equations.extend(["T + mg = mv²/R", "최소 조건: T=0", "v_min = √(gR)"])
            h.not_applicable_equations.append("T - mg = mv²/R : 최저점 식")
        elif c.subtype == "bottom":
            h.applicable_equations.extend(["T - mg = mv²/R", "T = mg + mv²/R"])
            h.not_applicable_equations.append("v_min = √(gR) : 최고점 최소속도 조건")
        h.cautions.append("구심력은 새 힘이 아니라 중심 방향 실제 힘들의 합입니다.")


    if c.system_type == "constant_acceleration_1d":
        h.problem_type_candidates.append("등가속도 직선 운동")
        h.detected_cues.extend(["v0/vf/a/t/s", "가속도 일정", "운동학 공식"])
        h.applicable_equations.extend(["v_f = v_0 + at", "s = v_0t + 1/2 at²", "v_f² = v_0² + 2as", "s = (v_0+v_f)t/2"])
        h.cautions.append("부호를 포함해서 운동방향을 먼저 정해야 합니다.")

    if c.system_type == "projectile_motion":
        h.problem_type_candidates.append("포물선 운동")
        h.detected_cues.extend(["x/y 성분 분해", "수평 가속도 0", "수직 가속도 -g"])
        h.applicable_equations.extend(["v_x = v_0 cosθ", "v_y = v_0 sinθ", "x = v_x t", "y = v_y t - 1/2gt²"])
        h.cautions.append("시작점과 착지점의 높이가 같은지 확인해야 사거리 공식 R=v0²sin2θ/g를 바로 쓸 수 있습니다.")

    if c.system_type == "constant_force_work":
        h.problem_type_candidates.append("일-에너지 기초: 일정한 힘의 일")
        h.applicable_equations.append("W = F s cosθ")
        h.cautions.append("힘과 이동방향 사이 각도가 0°가 아니면 cosθ를 반드시 곱해야 합니다.")

    if c.system_type == "fixed_axis_rotation":
        h.problem_type_candidates.append("고정축 회전 동역학")
        h.applicable_equations.extend(["ΣM_O = I_O α", "τ = Iα"])
        h.cautions.append("토크와 관성모멘트는 같은 축 기준이어야 합니다.")

    if c.system_type == "impulse_momentum":
        h.problem_type_candidates.append("충격량-운동량")
        h.applicable_equations.extend(["J = FΔt", "J = Δp = m(v_f-v_i)"])
        h.cautions.append("힘의 방향과 속도의 부호를 같은 좌표축에서 정해야 합니다.")


    if c.system_type == "work_energy_speed":
        h.problem_type_candidates.append("일-운동에너지 정리")
        h.detected_cues.extend(["일", "운동에너지", "속도 변화"])
        h.applicable_equations.extend(["W_net = ΔK", "W = 1/2 m v_f² - 1/2 m v_i²", "v_f = √(v_i² + 2W/m)"])
        h.cautions.append("일 W는 알짜일이어야 합니다. 한 힘의 일만 주어진 경우 다른 힘들이 일을 하는지 확인하세요.")

    if c.system_type == "spring_mass_vibration":
        h.problem_type_candidates.append("스프링-질량 자유진동")
        h.detected_cues.extend(["스프링 상수 k", "질량 m", "고유진동수/주기"])
        h.applicable_equations.extend(["m x¨ + kx = 0", "ω_n = √(k/m)", "T = 2π/ω_n", "f = 1/T"])
        h.cautions.append("감쇠나 외력이 있으면 기본 자유진동 공식만으로는 부족합니다.")

    if c.system_type == "spring_energy":
        h.problem_type_candidates.append("스프링 에너지-속도")
        h.detected_cues.extend(["탄성에너지", "운동에너지", "압축량"])
        h.applicable_equations.extend(["1/2 kx² = 1/2 mv²", "v = x√(k/m)"])
        h.not_applicable_equations.append("F = kx를 일정한 힘처럼 보고 W=Fx로 처리하지 않음")
        h.cautions.append("스프링 힘은 변위에 따라 변하므로 일은 1/2kx²입니다.")

    if c.system_type == "flat_curve_friction":
        h.problem_type_candidates.append("평평한 커브 최대속도")
        h.detected_cues.extend(["구심력", "정지마찰", "커브 반지름"])
        h.applicable_equations.extend(["f_s,max = μN", "μmg = mv²/R", "v_max = √(μgR)"])
        h.not_applicable_equations.append("마찰 없음 조건에서는 평평한 커브 구심력을 만들 수 없음")
        h.cautions.append("정지마찰이 구심력 역할을 하므로 실제로 미끄러지는 마찰이 아닙니다.")

    if c.system_type == "banked_curve_no_friction":
        h.problem_type_candidates.append("마찰 없는 경사진 커브")
        h.detected_cues.extend(["뱅크각", "수직항력 성분", "구심력"])
        h.applicable_equations.extend(["Ncosθ=mg", "Nsinθ=mv²/R", "v=√(gRtanθ)"])
        h.not_applicable_equations.append("f=μN : 마찰 없는 경사진 커브에서는 사용하지 않음")
        h.cautions.append("수직항력의 수평 성분이 구심력 역할을 합니다.")

    if c.system_type == "collision_1d":
        h.problem_type_candidates.append("1차원 충돌")
        h.applicable_equations.append("m1 v1 + m2 v2 = m1 v1' + m2 v2'")
        h.not_applicable_equations.append("운동에너지 보존 : 완전탄성 조건이 없으면 단정 금지")
        h.cautions.append("충돌에서는 먼저 외부 충격량 무시 가능 여부와 반발계수/탄성 조건을 확인하세요.")

    h.problem_type_candidates = _uniq(h.problem_type_candidates)
    h.applicable_equations = _uniq(h.applicable_equations)
    h.not_applicable_equations = _uniq(h.not_applicable_equations)
    h.cautions = _uniq(h.cautions)
    h.detected_cues = _uniq(h.detected_cues)


    if c.system_type == "polar_kinematics":
        h.problem_type_candidates.append("극좌표 운동학")
        h.detected_cues.extend(["r-θ 성분", "방사방향", "횡방향", "회전하는 단위벡터"])
        h.applicable_equations.extend(["v = r_dot e_r + r theta_dot e_theta", "a_r = r_ddot - r theta_dot²", "a_theta = r theta_ddot + 2 r_dot theta_dot"])
        h.not_applicable_equations.append("a = rα 만으로 전체 가속도를 처리하지 않음")
        h.cautions.append("극좌표에서는 단위벡터가 회전하므로 -rω²와 2r_dotω 항을 빠뜨리기 쉽습니다.")

    if c.system_type == "instant_center_velocity":
        h.problem_type_candidates.append("순간중심 속도해석")
        h.detected_cues.extend(["순간중심", "평면강체", "v=ωr"])
        h.applicable_equations.extend(["v_P = ω r_{P/IC}", "속도 방향은 IC-P에 수직"])
        h.not_applicable_equations.append("순간중심을 고정축처럼 장시간 운동에 그대로 적용하지 않음")
        h.cautions.append("순간중심법은 '그 순간의 속도' 해석 도구입니다. 가속도까지 바로 같은 방식으로 구하면 위험합니다.")

    if c.system_type == "slot_pin_relative_motion":
        h.problem_type_candidates.append("슬롯-핀 상대운동")
        h.detected_cues.extend(["상대속도", "회전 슬롯", "극좌표"])
        h.applicable_equations.extend(["v_r = r_dot", "v_theta = rω", "a_r = r_ddot - rω²", "a_theta = rα + 2r_dotω"])
        h.cautions.append("슬롯을 따라 미끄러지는 속도와 막대 회전으로 생기는 접선속도는 서로 다른 성분입니다.")

    if c.system_type == "plane_rigid_body_velocity":
        h.problem_type_candidates.append("평면강체 속도 관계")
        h.detected_cues.extend(["두 점 속도 관계", "각속도", "강체"])
        h.applicable_equations.extend(["v_B = v_A + ω × r_B/A", "|v_B/A| = ω r_B/A"])
        h.cautions.append("속도 관계는 벡터식입니다. 방향각이 주어지면 x-y 성분으로 나눠야 합니다.")

    if c.system_type == "relative_acceleration_translation":
        h.problem_type_candidates.append("상대가속도 기본형")
        h.detected_cues.extend(["상대가속도", "기준점", "벡터합"])
        h.applicable_equations.extend(["a_B = a_A + a_B/A"])
        h.cautions.append("방향이 주어지면 스칼라 덧셈이 아니라 성분별 벡터합을 해야 합니다.")

    if c.system_type == "coriolis_relative_motion":
        h.problem_type_candidates.append("회전 기준계 상대운동 / 코리올리")
        h.detected_cues.extend(["회전 기준계", "상대속도", "Coriolis", "2ωv_rel"])
        h.applicable_equations.extend(["a_C = 2ωv_rel", "a = a_O + α×r + ω×(ω×r) + 2ω×v_rel + a_rel"])
        h.not_applicable_equations.append("a = rα 또는 a = v²/R 하나만으로 전체 가속도를 처리하지 않음")
        h.cautions.append("코리올리 항 방향은 상대속도 방향과 회전축 방향의 벡터곱으로 정합니다.")

    if c.system_type == "plane_rigid_body_acceleration":
        h.problem_type_candidates.append("평면강체 가속도 관계")
        h.detected_cues.extend(["αr 접선성분", "ω²r 법선성분", "두 점 가속도 관계"])
        h.applicable_equations.extend(["a_B = a_A + α×r_B/A + ω×(ω×r_B/A)", "a_t=αr", "a_n=ω²r"])
        h.cautions.append("법선가속도는 항상 B에서 A 방향입니다. 방향 실수가 매우 잦습니다.")

    if c.system_type == "massive_pulley_atwood":
        h.problem_type_candidates.append("질량 있는 도르래 Atwood")
        h.detected_cues.extend(["도르래 관성", "T1≠T2", "a=αR"])
        h.applicable_equations.extend(["a=αR", "(T2-T1)R=Iα", "a=(m2-m1)g/(m1+m2+I/R²)"])
        h.not_applicable_equations.append("T1 = T2 : 질량 있는 도르래에서는 일반적으로 성립하지 않음")
        h.cautions.append("도르래 관성은 I/R² 등가질량처럼 분모에 더해져 가속도를 줄입니다.")

    if c.system_type == "rolling_energy_general":
        h.problem_type_candidates.append("일반 관성모멘트 순수 구름")
        h.detected_cues.extend(["순수 구름", "주어진 관성모멘트 I", "병진+회전 에너지"])
        h.applicable_equations.extend(["mgh=1/2mv²+1/2Iω²", "v=ωR", "v=sqrt(2mgh/(m+I/R²))"])
        h.not_applicable_equations.append("I를 무시한 mgh=1/2mv² 단독식")
        h.cautions.append("I가 주어지면 원판/고리 가정을 임의로 덮어쓰지 말고 주어진 I를 사용하세요.")

    h.problem_type_candidates = _uniq(h.problem_type_candidates)
    h.applicable_equations = _uniq(h.applicable_equations)
    h.not_applicable_equations = _uniq(h.not_applicable_equations)
    h.cautions = _uniq(h.cautions)
    h.detected_cues = _uniq(h.detected_cues)
    return h


def _uniq(items):
    out = []
    seen = set()
    for x in items:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out
