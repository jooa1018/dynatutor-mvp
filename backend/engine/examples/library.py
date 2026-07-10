from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ExampleProblem:
    id: str
    title: str
    category: str
    difficulty: str
    problem_text: str
    learning_goal: str
    tags: list[str]
    expected_solver: str


EXAMPLES: list[ExampleProblem] = [
    ExampleProblem(
        id="incline-no-friction-01",
        title="마찰 없는 경사면 가속도",
        category="입자 동역학",
        difficulty="입문",
        problem_text="질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
        learning_goal="경사면 방향으로 중력 성분 mg sinθ를 쓰는 연습",
        tags=["경사면", "F=ma", "힘 분해"],
        expected_solver="incline_no_friction",
    ),
    ExampleProblem(
        id="incline-friction-01",
        title="마찰 있는 경사면 가속도",
        category="입자 동역학",
        difficulty="입문",
        problem_text="마찰계수 0.2인 거친 30도 경사면에서 블록의 가속도를 구하라.",
        learning_goal="마찰력 μN을 경사면 반대방향으로 넣는 연습",
        tags=["경사면", "마찰", "F=ma"],
        expected_solver="incline_with_friction",
    ),
    ExampleProblem(
        id="constant-accel-01",
        title="등가속도 최종속도",
        category="운동학",
        difficulty="입문",
        problem_text="정지한 물체가 등가속도 a=2 m/s^2 로 시간 5 s 동안 직선 운동한다. 최종속도를 구하라.",
        learning_goal="v = v0 + at의 의미와 단위 확인",
        tags=["등가속도", "운동학"],
        expected_solver="constant_acceleration_1d",
    ),
    ExampleProblem(
        id="projectile-range-01",
        title="포물선 운동 사거리",
        category="운동학",
        difficulty="입문",
        problem_text="초속도 20 m/s, 발사각 30도인 포물선 운동에서 같은 높이에 착지할 때 사거리를 구하라.",
        learning_goal="수평/수직 운동을 분리해서 생각하기",
        tags=["포물선", "사거리", "성분 분해"],
        expected_solver="projectile_motion",
    ),
    ExampleProblem(
        id="pulley-table-01",
        title="수평면-매달린 블록 도르래",
        category="입자 동역학",
        difficulty="중급",
        problem_text="수평면 위 블록 m1=3 kg와 매달린 블록 m2=2 kg가 도르래와 줄로 연결되어 있다. 가속도를 구하라.",
        learning_goal="두 물체의 운동방정식을 같은 가속도로 연결하기",
        tags=["도르래", "장력", "연립방정식"],
        expected_solver="pulley_table_hanging",
    ),
    ExampleProblem(
        id="rolling-energy-01",
        title="순수 구름 에너지",
        category="강체 운동",
        difficulty="중급",
        problem_text="원판이 미끄러지지 않고 경사면을 높이 1.5 m만큼 굴러 내려간다. 속도를 구하라.",
        learning_goal="병진 운동에너지와 회전 운동에너지를 함께 넣기",
        tags=["순수 구름", "에너지", "강체"],
        expected_solver="pure_rolling_energy",
    ),
    ExampleProblem(
        id="vertical-circle-01",
        title="수직 원운동 최고점 최소속도",
        category="원운동",
        difficulty="중급",
        problem_text="반지름 2 m인 수직 원운동 최고점에서 최소속도를 구하라.",
        learning_goal="최고점에서 중심방향 힘과 최소 장력 조건 이해",
        tags=["수직 원운동", "구심력", "최소속도"],
        expected_solver="vertical_circle",
    ),
    ExampleProblem(
        id="work-energy-01",
        title="일-운동에너지로 최종속도",
        category="일과 에너지",
        difficulty="입문",
        problem_text="질량 2 kg 물체에 일 W=16 J가 작용하고 처음 속도 v0=0 m/s 이다. 최종 속도를 구하라.",
        learning_goal="W = ΔT로 속도 변화를 구하기",
        tags=["일", "에너지", "속도"],
        expected_solver="work_energy_speed",
    ),
    ExampleProblem(
        id="spring-vibration-01",
        title="스프링-질량 고유진동수",
        category="진동",
        difficulty="중급",
        problem_text="스프링 상수 k=200 N/m, 질량 2 kg인 스프링-질량계의 고유진동수를 구하라.",
        learning_goal="ω_n = sqrt(k/m)의 물리적 의미 이해",
        tags=["스프링", "진동", "고유진동수"],
        expected_solver="spring_mass_vibration",
    ),
    ExampleProblem(
        id="flat-curve-01",
        title="평평한 커브 최대속도",
        category="원운동",
        difficulty="중급",
        problem_text="평평한 커브 반지름 R=50 m, 마찰계수 0.4일 때 미끄러지지 않는 최대속도를 구하라.",
        learning_goal="정지마찰의 한계가 구심력을 제공하는 구조 이해",
        tags=["커브", "마찰", "구심력"],
        expected_solver="flat_curve_friction",
    ),
    ExampleProblem(
        id="polar-kinematics-01",
        title="극좌표 가속도 성분",
        category="고급 운동학",
        difficulty="상급",
        problem_text="극좌표에서 r=2 m, r_dot=0.5 m/s, r_ddot=0.1 m/s^2, theta_dot=3 rad/s, theta_ddot=0.2 rad/s^2 일 때 가속도 성분을 구하라.",
        learning_goal="a_r와 a_θ의 항들이 왜 생기는지 확인",
        tags=["극좌표", "가속도 성분", "고급"],
        expected_solver="polar_kinematics",
    ),
    ExampleProblem(
        id="instant-center-01",
        title="순간중심 속도해석",
        category="강체 운동",
        difficulty="상급",
        problem_text="순간중심 IC에서 점 P까지 거리 r=0.8 m, 각속도 omega=5 rad/s 이다. 점 P의 속도를 구하라.",
        learning_goal="그 순간에는 IC 기준 순수 회전처럼 속도를 계산하는 감각 익히기",
        tags=["순간중심", "강체", "속도해석"],
        expected_solver="instant_center_velocity",
    ),
    ExampleProblem(
        id="relative-acceleration-01",
        title="병진 기준계 상대가속도",
        category="고급 운동학",
        difficulty="상급",
        problem_text="A점 가속도 aA=1.2 m/s^2 이고 A에 대한 B의 상대가속도 a_rel=0.8 m/s^2 이다. B점 가속도를 구하라.",
        learning_goal="a_B = a_A + a_B/A 기본형을 이해하기",
        tags=["상대가속도", "벡터합", "고급"],
        expected_solver="relative_acceleration_translation",
    ),
    ExampleProblem(
        id="coriolis-slot-01",
        title="회전 슬롯 코리올리 가속도",
        category="고급 운동학",
        difficulty="상급",
        problem_text="회전좌표계에서 r=0.5 m, 상대속도 v_rel=0.4 m/s, 상대가속도 a_rel=0.1 m/s^2, 각속도 omega=6 rad/s, 각가속도 alpha=2 rad/s^2 이다. 코리올리 가속도와 절대가속도 성분을 구하라.",
        learning_goal="2ωv_rel 코리올리 항과 rω² 법선항을 함께 보기",
        tags=["코리올리", "회전좌표계", "상대운동"],
        expected_solver="coriolis_relative_motion",
    ),
    ExampleProblem(
        id="plane-rigid-accel-01",
        title="평면강체 가속도 기본형",
        category="강체 운동",
        difficulty="상급",
        problem_text="평면강체 가속도 문제에서 거리 r=0.6 m, 각속도 omega=4 rad/s, 각가속도 alpha=3 rad/s^2 이다. B점의 A에 대한 가속도 성분을 구하라.",
        learning_goal="접선가속도 αr과 법선가속도 ω²r을 분리하기",
        tags=["평면강체", "가속도", "법선성분"],
        expected_solver="plane_rigid_body_acceleration",
    ),
    ExampleProblem(
        id="massive-pulley-01",
        title="질량 있는 도르래 Atwood",
        category="강체 운동",
        difficulty="상급",
        problem_text="질량 있는 도르래에 m1=2 kg, m2=5 kg가 줄로 연결되어 있다. 도르래 관성모멘트 I=0.12 kgm^2, 도르래 반지름 R=0.3 m 일 때 가속도를 구하라.",
        learning_goal="도르래 관성 I/R²가 가속도를 줄이는 효과 이해",
        tags=["도르래", "관성모멘트", "장력"],
        expected_solver="massive_pulley_atwood",
    ),
    ExampleProblem(
        id="rolling-general-01",
        title="일반 관성모멘트 순수 구름",
        category="강체 운동",
        difficulty="상급",
        problem_text="질량 3 kg, 반지름 R=0.4 m, 관성모멘트 I=0.18 kgm^2 인 강체가 미끄러지지 않고 경사면을 높이 h=1.2 m만큼 굴러 내려간다. 속도를 구하라.",
        learning_goal="물체 종류 대신 주어진 I를 에너지식에 넣기",
        tags=["순수 구름", "관성모멘트", "에너지"],
        expected_solver="rolling_energy_general",
    ),

    ExampleProblem(
        id="ko-rest-start-01",
        title="한국어 정지 출발 등가속도",
        category="한국어 파서 강화",
        difficulty="입문",
        problem_text="정지 상태에서 출발한 물체가 가속도 2m/s²로 5초 동안 직선 운동한다. 최종속도를 구하라.",
        learning_goal="정지 상태에서 출발을 v0=0으로 해석하기",
        tags=["한국어", "정지", "등가속도"],
        expected_solver="constant_acceleration_1d",
    ),
    ExampleProblem(
        id="ko-stop-time-01",
        title="한국어 멈춤 시간",
        category="한국어 파서 강화",
        difficulty="입문",
        problem_text="최종적으로 정지할 때까지 가속도 -2m/s^2로 움직인다. 초속도 10m/s일 때 걸리는 시간은?",
        learning_goal="멈출 때까지를 vf=0으로 해석하고 시간 구하기",
        tags=["한국어", "멈춤", "시간"],
        expected_solver="constant_acceleration_1d",
    ),
    ExampleProblem(
        id="ko-projectile-kmh-01",
        title="한국어 km/h 포물선",
        category="한국어 파서 강화",
        difficulty="입문",
        problem_text="발사속도 72 km/h, 발사각 30도인 포물선 운동에서 같은 높이에 착지할 때 사거리를 구하라.",
        learning_goal="km/h를 m/s로 바꾸고 포물선 사거리 계산하기",
        tags=["한국어", "단위변환", "포물선"],
        expected_solver="projectile_motion",
    ),
    ExampleProblem(
        id="ko-spring-grams-01",
        title="한국어 g 단위 스프링 주기",
        category="한국어 파서 강화",
        difficulty="입문",
        problem_text="스프링 상수 200N/m, 질량 500g인 스프링-질량계의 주기를 구하라.",
        learning_goal="g를 kg로 변환하고 주기 T 계산하기",
        tags=["한국어", "단위변환", "진동"],
        expected_solver="spring_mass_vibration",
    ),
    ExampleProblem(
        id="ko-work-cm-01",
        title="한국어 cm 이동거리 일",
        category="한국어 파서 강화",
        difficulty="입문",
        problem_text="힘 10N이 물체를 30cm 이동시켰다. 한 일을 구하라.",
        learning_goal="cm를 m로 변환하고 W=Fs 적용하기",
        tags=["한국어", "단위변환", "일"],
        expected_solver="constant_force_work",
    ),
    ExampleProblem(
        id="ko-incline-frictionless-variant-01",
        title="한국어 마찰 없음 표현 경사면",
        category="한국어 파서 강화",
        difficulty="입문",
        problem_text="질량 500g인 블록이 마찰이 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
        learning_goal="마찰이 없는/마찰 없음 표현을 frictionless로 해석하기",
        tags=["한국어", "경사면", "마찰 없음"],
        expected_solver="incline_no_friction",
    ),
    ExampleProblem(
        id="ko-massive-pulley-cm-01",
        title="한국어 질량 있는 도르래 cm 반지름",
        category="한국어 파서 강화",
        difficulty="상급",
        problem_text="도르래 관성모멘트 I=0.12 kgm^2, 도르래 반지름 30cm, m1=2kg, m2=5kg인 질량 있는 도르래에서 가속도를 구하라.",
        learning_goal="도르래 반지름 cm를 m로 바꾸고 I/R² 효과 보기",
        tags=["한국어", "도르래", "강체"],
        expected_solver="massive_pulley_atwood",
    ),
    ExampleProblem(
        id="ko-polar-cm-01",
        title="한국어 극좌표 cm 반지름",
        category="한국어 파서 강화",
        difficulty="상급",
        problem_text="극좌표에서 r=200cm, r_dot=0.5m/s, r_ddot=0.1m/s^2, theta_dot=3rad/s, theta_ddot=0.2rad/s^2 일 때 가속도 성분을 구하라.",
        learning_goal="극좌표 반지름 단위 변환과 가속도 성분 계산",
        tags=["한국어", "극좌표", "단위변환"],
        expected_solver="polar_kinematics",
    ),

    ExampleProblem(
        id="personal-drill-incline-02",
        title="개인훈련: 매끄러운 경사면 kg/g 혼합",
        category="개인 학습 드릴",
        difficulty="입문",
        problem_text="질량 750g인 작은 블록이 매끄러운 25도 비탈면을 따라 내려간다. 가속도를 구하라.",
        learning_goal="한국어 표현 '매끄러운 비탈면'을 마찰 없음 경사면으로 해석하기",
        tags=["개인훈련", "경사면", "한국어"],
        expected_solver="incline_no_friction",
    ),
    ExampleProblem(
        id="personal-drill-work-02",
        title="개인훈련: 일-거리 단위 변환",
        category="개인 학습 드릴",
        difficulty="입문",
        problem_text="수평 방향 힘 15N이 물체를 80cm 이동시켰다. 이 힘이 한 일을 구하라.",
        learning_goal="cm를 m로 바꾸고 W=Fs를 적용하기",
        tags=["개인훈련", "일", "단위변환"],
        expected_solver="constant_force_work",
    ),
    ExampleProblem(
        id="personal-drill-stop-02",
        title="개인훈련: 감속 후 정지",
        category="개인 학습 드릴",
        difficulty="입문",
        problem_text="처음 속도 12m/s인 물체가 가속도 -3m/s^2로 감속하여 멈출 때까지 걸리는 시간을 구하라.",
        learning_goal="최종 정지를 vf=0으로 두고 등가속도식을 고르기",
        tags=["개인훈련", "등가속도", "감속"],
        expected_solver="constant_acceleration_1d",
    ),
    ExampleProblem(
        id="personal-drill-curve-02",
        title="개인훈련: 평평한 커브",
        category="개인 학습 드릴",
        difficulty="중급",
        problem_text="평평한 도로의 커브 반지름이 40m이고 마찰계수가 0.35이다. 자동차가 미끄러지지 않는 최대속도를 구하라.",
        learning_goal="정지마찰 한계가 구심력 역할을 하는 구조 이해",
        tags=["개인훈련", "원운동", "마찰"],
        expected_solver="flat_curve_friction",
    ),
    ExampleProblem(
        id="personal-drill-rolling-02",
        title="개인훈련: 일반 관성모멘트 구름",
        category="개인 학습 드릴",
        difficulty="상급",
        problem_text="질량 2kg, 반지름 0.25m, 관성모멘트 I=0.04 kgm^2인 강체가 미끄러지지 않고 높이 0.8m를 굴러 내려간다. 속도를 구하라.",
        learning_goal="주어진 I를 에너지식에 직접 넣는 연습",
        tags=["개인훈련", "순수구름", "강체"],
        expected_solver="rolling_energy_general",
    ),
    ExampleProblem(
        id="personal-drill-coriolis-02",
        title="개인훈련: 코리올리 기본",
        category="개인 학습 드릴",
        difficulty="상급",
        problem_text="회전좌표계에서 r=0.4m, 상대속도 v_rel=0.2m/s, 상대가속도 a_rel=0.05m/s^2, 각속도 omega=5rad/s, 각가속도 alpha=1rad/s^2이다. 코리올리 가속도와 절대가속도 성분을 구하라.",
        learning_goal="2ωv_rel 항을 빠뜨리지 않는 연습",
        tags=["개인훈련", "코리올리", "고급"],
        expected_solver="coriolis_relative_motion",
    ),

]


def list_examples(category: str | None = None, difficulty: str | None = None) -> list[dict]:
    examples = EXAMPLES
    if category:
        examples = [e for e in examples if e.category == category]
    if difficulty:
        examples = [e for e in examples if e.difficulty == difficulty]
    return [asdict(e) for e in examples]


def example_stats() -> dict:
    categories: dict[str, int] = {}
    difficulties: dict[str, int] = {}
    for e in EXAMPLES:
        categories[e.category] = categories.get(e.category, 0) + 1
        difficulties[e.difficulty] = difficulties.get(e.difficulty, 0) + 1
    return {
        "total": len(EXAMPLES),
        "categories": categories,
        "difficulties": difficulties,
    }



def all_categories() -> list[str]:
    return sorted({e.category for e in EXAMPLES})


def find_examples_by_solver(solver: str | None, limit: int = 5) -> list[dict]:
    if not solver:
        return []
    out = [e for e in EXAMPLES if e.expected_solver == solver]
    return [asdict(e) for e in out[:limit]]


def recommended_examples_for_types(problem_types: list[str], limit: int = 6) -> list[dict]:
    # record problem_type은 system_type이고 example은 expected_solver 중심이라 간단한 매핑을 둔다.
    type_to_solver = {
        "particle_on_incline": ["incline_no_friction", "incline_with_friction"],
        "constant_acceleration_1d": ["constant_acceleration_1d"],
        "projectile_motion": ["projectile_motion"],
        "pulley_table_hanging": ["pulley_table_hanging"],
        "pure_rolling_energy": ["pure_rolling_energy", "rolling_energy_general"],
        "rolling_energy_general": ["rolling_energy_general"],
        "flat_curve_friction": ["flat_curve_friction"],
        "coriolis_relative_motion": ["coriolis_relative_motion"],
        "plane_rigid_body_acceleration": ["plane_rigid_body_acceleration"],
        "massive_pulley_atwood": ["massive_pulley_atwood"],
    }
    chosen: list[ExampleProblem] = []
    for ptype in problem_types:
        for solver in type_to_solver.get(ptype, [ptype]):
            chosen.extend([e for e in EXAMPLES if e.expected_solver == solver])
    if not chosen:
        chosen = [e for e in EXAMPLES if e.category in {"개인 학습 드릴", "한국어 파서 강화"}]
    # deduplicate, keep order
    seen = set()
    out = []
    for e in chosen:
        if e.id not in seen:
            out.append(e)
            seen.add(e.id)
        if len(out) >= limit:
            break
    return [asdict(e) for e in out]


def pick_practice_examples(category: str | None = None, difficulty: str | None = None, count: int = 6) -> list[dict]:
    examples = EXAMPLES
    if category and category != "전체":
        examples = [e for e in examples if e.category == category]
    if difficulty and difficulty != "전체":
        examples = [e for e in examples if e.difficulty == difficulty]
    # deterministic rotation-friendly order: personal drills first, then others
    examples = sorted(examples, key=lambda e: (0 if e.category == "개인 학습 드릴" else 1, e.difficulty, e.id))
    return [asdict(e) for e in examples[:count]]
