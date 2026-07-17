from __future__ import annotations
from app.schemas.solution import SolveResponse, StepCard as StepCardSchema


_CONCEPTS: dict[str, list[str]] = {
    "particle_on_incline": [
        "경사면 문제의 핵심은 중력 mg를 경사면 방향 mg sinθ와 수직 방향 mg cosθ로 나누는 것입니다.",
        "가속도를 구할 때는 보통 경사면을 따라가는 x축에 ΣF=ma를 적용합니다.",
    ],
    "pulley_table_hanging": [
        "도르래 문제는 물체마다 식을 따로 세우고, 줄 조건으로 같은 가속도를 연결합니다.",
        "장력 T는 내부 연결 힘이므로 물체별 FBD에는 나타나지만 전체 계로 보면 상쇄될 수 있습니다.",
    ],
    "projectile_motion": [
        "포물선 운동은 수평 운동과 수직 운동을 분리해서 보면 단순해집니다.",
        "공기저항을 무시하면 수평방향 가속도는 0이고, 수직방향 가속도는 -g입니다.",
    ],
    "pure_rolling_energy": [
        "순수 구름은 병진 운동과 회전 운동이 함께 있는 강체 운동입니다.",
        "미끄러지지 않는 조건이 있을 때만 v_G=ωR을 쓸 수 있습니다.",
    ],
    "spring_mass_vibration": [
        "스프링-질량 기본 진동은 복원력 F=-kx 때문에 생기는 1자유도 운동입니다.",
        "고유각진동수는 질량이 커질수록 작아지고, 스프링이 강할수록 커집니다.",
    ],
    "polar_kinematics": [
        "극좌표에서는 단위벡터 e_r, e_θ 자체가 회전하므로 직교좌표보다 가속도 항이 많아집니다.",
        "a_r = r_ddot - rθ_dot²는 안쪽/바깥쪽 성분, a_θ = rθ_ddot + 2r_dotθ_dot는 접선 성분입니다.",
    ],
    "instant_center_velocity": [
        "순간중심 방법은 그 순간의 속도해석을 순수 회전처럼 바꿔보는 도구입니다.",
        "점의 속도 방향은 순간중심과 그 점을 잇는 선에 수직입니다.",
    ],
    "plane_rigid_body_velocity": [
        "평면강체 속도 관계는 기준점 속도에 회전 때문에 생기는 상대속도를 더하는 방식입니다.",
        "v_B = v_A + ω×r_B/A에서 ω×r 항은 r_B/A에 수직입니다.",
    ],
    "relative_acceleration_translation": [
        "상대가속도 기본형은 기준점 A의 가속도에 A에 대한 B의 상대가속도를 더하는 것입니다.",
        "방향이 주어진 문제는 반드시 성분을 나누어 벡터로 더해야 합니다.",
    ],
    "coriolis_relative_motion": [
        "회전 기준계에서 상대속도가 있으면 코리올리 가속도 2ωv_rel이 생깁니다.",
        "이 항은 '움직이는 점'과 '회전하는 좌표축'이 동시에 있을 때 나타나는 고급 상대운동 항입니다.",
    ],
    "plane_rigid_body_acceleration": [
        "평면강체 가속도는 기준점 가속도, 접선성분 αr, 법선성분 ω²r로 나눠 생각합니다.",
        "속도식보다 가속도식이 더 어렵습니다. 특히 법선성분은 항상 두 점을 잇는 선을 따라 기준점 쪽을 향합니다.",
    ],
    "massive_pulley_atwood": [
        "질량 있는 도르래에서는 회전 관성 때문에 양쪽 장력이 서로 다를 수 있습니다.",
        "도르래 관성은 I/R²라는 등가질량처럼 작용하여 가속도를 줄입니다.",
    ],
    "rolling_energy_general": [
        "일반 순수 구름 에너지 문제는 병진 에너지와 주어진 관성모멘트 I의 회전 에너지를 함께 넣습니다.",
        "원판/고리 같은 물체 종류를 외우기보다, 주어진 I를 식에 정확히 넣는 것이 중요합니다.",
    ],
}

_COMMON_MISTAKES: dict[str, list[str]] = {
    "particle_on_incline": [
        "mg 전체를 경사면 방향 힘으로 두는 실수",
        "N = mg라고 두는 실수. 경사면에서는 보통 N = mg cosθ입니다.",
        "마찰 없음 조건인데 f=μN을 넣는 실수",
    ],
    "pure_rolling_energy": [
        "회전 운동에너지 1/2 Iω²를 빼먹는 실수",
        "미끄러짐이 있는데 v=ωR을 쓰는 실수",
    ],
    "projectile_motion": [
        "수평방향에도 중력가속도 g를 넣는 실수",
        "각도를 degree가 아니라 radian처럼 계산하는 실수",
    ],
    "polar_kinematics": [
        "a_r에서 -rθ_dot² 항을 빼먹는 실수",
        "a_θ에서 2r_dotθ_dot 항을 빼먹는 실수",
    ],
    "instant_center_velocity": [
        "속도 방향이 IC-P 선 방향이라고 착각하는 실수",
        "순간중심은 속도해석 도구인데 모든 가속도해석에 그대로 적용하는 실수",
    ],
    "spring_mass_vibration": [
        "ω_n와 일반 주파수 f를 혼동하는 실수",
        "k/m 대신 m/k를 넣는 실수",
    ],
    "coriolis_relative_motion": [
        "코리올리 항 2ωv_rel을 빼먹는 실수",
        "코리올리 항 방향을 상대속도 방향과 같다고 착각하는 실수",
    ],
    "plane_rigid_body_acceleration": [
        "법선 성분 ω²r의 방향을 반대로 잡는 실수",
        "속도식 v_B=v_A+ω×r을 가속도식에도 그대로 쓰는 실수",
    ],
    "massive_pulley_atwood": [
        "질량 있는 도르래에서도 T1=T2라고 두는 실수",
        "a=αR 구속조건을 빼먹는 실수",
    ],
    "rolling_energy_general": [
        "I가 주어졌는데 원판 I=1/2mR²를 임의로 쓰는 실수",
        "회전 운동에너지 1/2Iω²를 빼먹는 실수",
    ],
}

_STUDY_TIPS: dict[str, list[str]] = {
    "particle_on_incline": ["먼저 경사면 방향 축을 그린 뒤, mg를 두 성분으로 나누는 연습을 반복하세요."],
    "projectile_motion": ["표를 만들어 x방향과 y방향의 v0, a, t, s를 따로 적어보세요."],
    "pure_rolling_energy": ["에너지식에 병진항과 회전항이 둘 다 있는지 마지막에 체크하세요."],
    "polar_kinematics": ["공식 암기보다 각 항의 방향을 그림으로 표시하는 연습이 중요합니다."],
    "instant_center_velocity": ["IC에서 각 점까지 선을 긋고, 속도는 그 선에 수직으로 그려보세요."],
    "plane_rigid_body_velocity": ["기준점 A를 먼저 정하고, B의 상대속도 방향이 r_B/A에 수직인지 확인하세요."],
    "coriolis_relative_motion": ["회전 기준계 문제에서는 먼저 상대속도 v_rel이 있는지 확인하고, 있으면 2ωv_rel 항을 표시하세요."],
    "plane_rigid_body_acceleration": ["속도해석처럼 한 줄로 끝내지 말고, 접선 αr과 법선 ω²r을 별도 화살표로 그려보세요."],
    "massive_pulley_atwood": ["양쪽 장력을 T 하나로 두지 말고 T1, T2로 분리한 뒤 도르래 회전식을 쓰세요."],
    "rolling_energy_general": ["에너지식에 I/R²가 등가질량처럼 들어간다는 관점으로 정리해보세요."],
}

_EQUATION_SHEETS: dict[str, list[str]] = {
    "particle_on_incline": ["ΣF_x = ma", "mg sinθ - f = ma", "N = mg cosθ", "f = μN, 단 마찰이 있을 때만"],
    "constant_acceleration_1d": ["v = v0 + at", "s = v0t + 1/2 at²", "v² = v0² + 2as"],
    "projectile_motion": ["v0x = v0 cosθ", "v0y = v0 sinθ", "R = v0² sin(2θ) / g", "H = v0² sin²θ / (2g)"],
    "pulley_table_hanging": ["T = m1 a", "m2 g - T = m2 a", "a = m2 g / (m1 + m2)"],
    "pure_rolling_energy": ["mgh = 1/2 mv_G² + 1/2 I_Gω²", "v_G = ωR", "I_disk = 1/2 mR²"],
    "vertical_circle": ["ΣF_center = mv²/R", "top 최소속도: v_min = sqrt(gR)"],
    "work_energy_speed": ["W_net = ΔT", "W = 1/2 m(v_f² - v_0²)"],
    "spring_mass_vibration": ["ω_n = sqrt(k/m)", "f_n = ω_n / 2π", "T = 2π / ω_n"],
    "spring_energy": ["1/2 kx² = 1/2 mv²", "v = x sqrt(k/m)"],
    "flat_curve_friction": ["f_s,max = μ_s N", "mv²/R ≤ μ_s mg", "v_max = sqrt(μ_s gR)"],
    "banked_curve_no_friction": ["tanθ = v²/(gR)", "v = sqrt(gR tanθ)"],
    "polar_kinematics": ["v = r_dot e_r + rθ_dot e_θ", "a_r = r_ddot - rθ_dot²", "a_θ = rθ_ddot + 2r_dotθ_dot"],
    "instant_center_velocity": ["v = ωr", "ω = v/r"],
    "slot_pin_relative_motion": ["v_r = r_dot", "v_θ = rω", "|v| = sqrt(r_dot² + (rω)²)"],
    "plane_rigid_body_velocity": ["v_B = v_A + ω×r_B/A", "|v_B/A| = ωr"],
    "relative_acceleration_translation": ["a_B = a_A + a_B/A"],
    "coriolis_relative_motion": ["a_C = 2ωv_rel", "a = a_O + α×r + ω×(ω×r) + 2ω×v_rel + a_rel", "a_r = a_rel - rω²", "a_θ = rα + 2ωv_rel"],
    "plane_rigid_body_acceleration": ["a_B = a_A + α×r_B/A + ω×(ω×r_B/A)", "a_t = αr", "a_n = ω²r"],
    "massive_pulley_atwood": ["a = αR", "(T2 - T1)R = Iα", "a = (m2-m1)g / (m1+m2+I/R²)"],
    "rolling_energy_general": ["mgh = 1/2mv_G² + 1/2I_Gω²", "v_G = ωR", "v_G = sqrt(2mgh/(m+I_G/R²))"],
}


def build_teacher_summary(response: SolveResponse) -> list[str]:
    """Project a deterministic summary exclusively from the finalized trace."""

    trace = response.explanation_trace
    if trace is None or trace.status != "fully_grounded":
        return ["현재 근거로는 계산 과정을 확정해 제시할 수 없습니다."]
    summary = ["조건, 좌표계, 관계식, 대입과 검산이 연결된 풀이입니다."]
    summary.extend(
        f"최종 결과: {derivation.display}"
        for derivation in trace.answer_derivation
    )
    return summary


def build_concept_summary(response: SolveResponse) -> list[str]:
    trace = response.explanation_trace
    if trace is None or trace.status != "fully_grounded":
        return ["모형, 사건 조건과 필요한 입력이 확인되기 전에는 특정 계산식을 확정하지 않습니다."]
    out: list[str] = []
    if trace.coordinate_frame is not None:
        directions = ", ".join(
            f"{axis}: {direction}"
            for axis, direction in zip(
                trace.coordinate_frame.axes,
                trace.coordinate_frame.positive_directions,
            )
        )
        coordinate = trace.coordinate_frame.coordinate_system
        out.append(f"좌표계: {coordinate}" + (f" ({directions})" if directions else ""))
    out.extend(f"사용한 관계식: {equation.expression}" for equation in trace.equations)
    if trace.assumptions:
        out.append("분리해 둔 가정: " + "; ".join(str(fact.value) for fact in trace.assumptions))
    return out


def build_common_mistakes(response: SolveResponse) -> list[str]:
    trace = response.explanation_trace
    if trace is None or trace.status != "fully_grounded":
        return ["확정되지 않은 조건이나 후보 값을 최종 계산처럼 사용하지 마세요."]
    mistakes = ["명시된 조건과 풀이 가정을 서로 섞지 마세요."]
    if trace.coordinate_frame is not None:
        mistakes.append("추적된 좌표계의 양의 방향과 반대로 부호를 바꾸지 마세요.")
    if trace.equations:
        mistakes.append("근거가 연결되지 않은 식이나 값을 풀이에 추가하지 마세요.")
    return mistakes


def build_study_tips(response: SolveResponse) -> list[str]:
    return [
        "조건, 가정, 좌표계, 관계식, 대입, 검산을 서로 연결해 적는 연습을 하세요.",
        "근거가 없는 값이나 식이 추가되지 않았는지 마지막에 확인하세요.",
    ]


def build_equation_sheet(response: SolveResponse) -> list[str]:
    trace = response.explanation_trace
    if trace is None or trace.status != "fully_grounded":
        return []
    return [equation.expression for equation in trace.equations]


def project_explanation_from_trace(response: SolveResponse) -> None:
    """Replace every physics-bearing student projection from one finalized trace."""

    trace = response.explanation_trace
    diagnosis = response.diagnosis

    # Phase 53 Wave 1 has no trace representation for FBD geometry or the full
    # physical-model payload.  Clear every legacy/generic student projection
    # before rebuilding the small coordinate/equation view that v1 can prove.
    diagnosis.fbd_diagram_svg = None
    diagnosis.fbd_annotations = []
    diagnosis.fbd = []
    diagnosis.coordinate_guide = []
    diagnosis.applicable_equations = []
    diagnosis.not_applicable_equations = []
    diagnosis.cautions = []
    diagnosis.next_questions = []
    diagnosis.physical_model = None
    diagnosis.legacy_hints.problem_type_candidates = []
    diagnosis.legacy_hints.applicable_equations = []
    diagnosis.legacy_hints.not_applicable_equations = []
    diagnosis.legacy_hints.cautions = []
    diagnosis.legacy_hints.detected_cues = []
    response.physical_model = None

    if trace is not None and trace.status == "fully_grounded":
        if trace.coordinate_frame is not None:
            diagnosis.coordinate_guide = [trace.coordinate_frame.coordinate_system]
            diagnosis.coordinate_guide.extend(
                f"{axis}: {direction}"
                for axis, direction in zip(
                    trace.coordinate_frame.axes,
                    trace.coordinate_frame.positive_directions,
                )
            )
        diagnosis.applicable_equations = [
            equation.expression for equation in trace.equations
        ]

    if trace is None:
        response.steps = [
            StepCardSchema(
                title="풀이 상태",
                body="현재 구조화된 근거만으로 계산 과정을 확정할 수 없습니다.",
            )
        ]
    else:
        response.steps = [
            StepCardSchema(title=step.title, body=step.body, math=step.math)
            for step in trace.student_steps
        ]
    response.teacher_summary = build_teacher_summary(response)
    response.concept_summary = build_concept_summary(response)
    response.common_mistakes = build_common_mistakes(response)
    response.study_tips = build_study_tips(response)
    response.equation_sheet = build_equation_sheet(response)
