from __future__ import annotations

from typing import Any

from engine.textbook_parser.benchmark import (
    BENCHMARK_SCHEMA_VERSION,
    BenchmarkCase,
    BenchmarkManifest,
    GoldLabels,
)


PROVENANCE = "repository_safe_independently_authored_paraphrase"


def _case(
    case_id: str,
    category: str,
    text: str,
    system_type: str | None,
    solver: str | None,
    facts: list[str],
    answer: dict[str, Any] | None,
    *,
    entity: str = "object",
    entities: list[str] | None = None,
    segments: list[str] | None = None,
    fact_entities: list[str] | None = None,
    fact_segments: list[str | None] | None = None,
    query: str = "requested_output:object:motion_1",
    events: list[str] | None = None,
    relations: list[str] | None = None,
    assumptions: list[str] | None = None,
    status: str = "supported",
    terminal: str | None = None,
    figure: str = "none",
    clarify: bool = False,
) -> BenchmarkCase:
    fact_ids = [f"fact_{index}" for index in range(1, len(facts) + 1)]
    # Only constant_acceleration_1d has completed the typed-canonical
    # raw-text-invariance gate. Other categories deliberately benchmark safe
    # parser/route abstention until their solver capability is promoted.
    effective_status = status
    effective_answer = answer
    effective_terminal = terminal
    if status == "supported" and category != "직선·다구간 운동학":
        effective_status = "solver_gap"
        effective_answer = None
        effective_terminal = "solver_gap"
    return BenchmarkCase(
        case_id=case_id,
        provenance=PROVENANCE,
        category=category,
        problem_text=text,
        gold=GoldLabels(
            entities=entities or [entity],
            segments=["motion_1:target"] if segments is None else segments,
            events=["start"] if events is None else events,
            explicit_facts=facts,
            fact_entity_binding={
                item: (fact_entities[index] if fact_entities else entity)
                for index, item in enumerate(fact_ids)
            },
            fact_segment_binding={
                item: (fact_segments[index] if fact_segments else "motion_1")
                for index, item in enumerate(fact_ids)
            },
            relations=relations or [],
            queries=[query],
            assumptions=assumptions or [],
            required_clarification=clarify,
            figure_dependency=figure,
            expected_system_type=system_type,
            expected_solver=solver,
            supported_status=effective_status,
            expected_end_to_end_answer=effective_answer,
            expected_terminal_status=effective_terminal,
        ),
    )


def repository_safe_seed_manifest() -> BenchmarkManifest:
    """Return 192 independently authored cases; no textbook source is copied."""

    cases: list[BenchmarkCase] = []
    for index in range(1, 31):
        duration = 3 + index % 6
        acceleration = 1 + index % 5
        distance = 0.5 * acceleration * duration**2
        cases.append(
            _case(
                f"kinematics_{index:03d}",
                "직선·다구간 운동학",
                f"물체 K{index}가 정지 상태에서 {duration}초 동안 일정한 가속도로 {distance:g}m를 이동했다. 가속도의 크기를 구하여라.",
                "constant_acceleration_1d",
                "constant_acceleration_1d",
                [f"time:{duration}:초", f"distance:{distance:g}:m"],
                {"numeric": acceleration, "unit": "m/s^2"},
                assumptions=["starts_from_rest"],
                query="acceleration:object:motion_1",
            )
        )
    for index in range(1, 21):
        speed = 10 + index
        angle = 30 + (index % 3) * 15
        distractor = 5 + index % 4
        cases.append(
            _case(
                f"projectile_{index:03d}",
                "포물선·곡선·극좌표",
                f"공기 저항을 무시하고 공 P{index}를 지면에서 {speed}m/s의 속력과 {angle}도 각도로 던졌다. 최고 높이를 구하여라. {distractor}m 표시는 배경 표지판 높이이다.",
                "projectile_motion",
                "projectile_motion",
                [f"initial_velocity:{speed}:m/s", f"angle:{angle}:도", f"background_height:{distractor}:m"],
                {"symbolic": "deterministic_projectile", "unit": "m"},
                assumptions=["no_air_resistance", "constant_gravity"],
                query="max_height:object:motion_1",
            )
        )
    for index in range(1, 26):
        mass = 2 + index % 7
        acceleration = 1 + index % 4
        force = mass * acceleration
        cases.append(
            _case(
                f"newton_{index:03d}",
                "Newton·마찰",
                f"수평면 위 상자 N{index}의 질량은 {mass}kg이고 알짜힘 {force}N이 오른쪽으로 작용한다. 상자의 가속도를 구하여라.",
                "single_particle_newton",
                "single_particle_newton",
                [f"mass:{mass}:kg", f"force:{force}:N"],
                {"numeric": acceleration, "unit": "m/s^2"},
                query="acceleration:object:motion_1",
            )
        )
    for index in range(1, 21):
        mass_1 = 1 + index % 5
        mass_2 = mass_1 + 2
        cases.append(
            _case(
                f"pulley_{index:03d}",
                "도르래·구속조건",
                f"질량 {mass_1}kg인 추 A와 {mass_2}kg인 추 B가 가벼운 줄로 연결되어 마찰 없는 도르래에 걸려 있다. 계의 가속도를 구하여라.",
                "pulley_atwood",
                "pulley_atwood",
                [f"mass_1:{mass_1}:kg", f"mass_2:{mass_2}:kg"],
                {"symbolic": "deterministic_atwood", "unit": "m/s^2"},
                entity="system",
                entities=["system", "mass_a", "mass_b", "pulley"],
                fact_entities=["mass_a", "mass_b"],
                relations=[
                    "connected_by_rope:mass_a:mass_b",
                    "passes_over_pulley:mass_a:mass_b:pulley",
                ],
                assumptions=["massless_rope", "frictionless"],
                query="acceleration:system:motion_1",
            )
        )
    for index in range(1, 21):
        force = 5 + index % 6
        distance = 2 + index % 5
        cases.append(
            _case(
                f"work_energy_{index:03d}",
                "일-에너지",
                f"카트 W{index}에 이동 방향과 나란한 일정한 힘 {force}N을 가하여 {distance}m 옮겼다. 이 힘이 한 일을 구하여라.",
                "constant_force_work",
                "constant_force_work",
                [f"force:{force}:N", f"distance:{distance}:m"],
                {"numeric": force * distance, "unit": "J"},
                query="work:object:motion_1",
            )
        )
    for index in range(1, 16):
        mass = 1 + index % 4
        speed = 2 + index % 7
        cases.append(
            _case(
                f"collision_{index:03d}",
                "충격량·충돌",
                f"질량 {mass}kg인 수레 C{index}가 충돌 직전 오른쪽으로 {speed}m/s로 움직이고 있었다. 정지할 때까지 받은 충격량의 크기를 구하여라.",
                "impulse_momentum",
                "impulse_momentum",
                [f"mass:{mass}:kg", f"velocity_before:{speed}:m/s"],
                {"numeric": mass * speed, "unit": "N*s"},
                events=["just_before_collision", "comes_to_rest"],
                query="impulse:object:motion_1",
            )
        )
    for index in range(1, 21):
        radius = 1 + index % 5
        omega = 2 + index % 6
        cases.append(
            _case(
                f"rigid_{index:03d}",
                "강체 속도·가속도",
                f"강체 R{index}가 고정축 주위로 {omega}rad/s의 각속도로 회전한다. 축에서 {radius}m 떨어진 점의 접선 속력을 구하여라.",
                "fixed_axis_rotation",
                "fixed_axis_rotation",
                [f"angular_velocity:{omega}:rad/s", f"radius:{radius}:m"],
                {"numeric": radius * omega, "unit": "m/s"},
                entity="point",
                entities=["body", "point"],
                fact_entities=["body", "point"],
                relations=["point_on_body:body:point"],
                query="tangential_velocity:point:motion_1",
            )
        )
    for index in range(1, 16):
        radius = 0.2 + (index % 5) * 0.1
        speed = 1 + index % 4
        cases.append(
            _case(
                f"rolling_{index:03d}",
                "구름·회전",
                f"반지름 {radius:.1f}m인 원판 G{index}가 미끄러지지 않고 {speed}m/s로 굴러간다. 원판의 각속도 크기를 구하여라.",
                "pure_rolling_energy",
                "pure_rolling_energy",
                [f"radius:{radius:.1f}:m", f"velocity:{speed}:m/s"],
                {"numeric": round(speed / radius, 6), "unit": "rad/s"},
                assumptions=["pure_rolling"],
                query="angular_velocity:object:motion_1",
            )
        )
    for index in range(1, 16):
        period = 2 + index % 5
        cases.append(
            _case(
                f"vibration_{index:03d}",
                "진동",
                f"진동자 V{index}가 {period}초마다 같은 위치와 운동 상태로 돌아온다. 진동수의 크기를 구하여라.",
                "spring_mass_vibration",
                "spring_mass_vibration",
                [f"period:{period}:초"],
                {"numeric": round(1 / period, 6), "unit": "Hz"},
                query="frequency:object:motion_1",
            )
        )
    for index in range(1, 5):
        cases.append(
            _case(
                f"insufficient_{index:03d}",
                "조건 부족",
                f"물체 U{index}가 어느 순간 움직이고 있다. 이동 시간을 구하여라.",
                None,
                None,
                [],
                None,
                status="insufficient_information",
                terminal="insufficient_information",
                clarify=True,
                segments=[],
                events=[],
                query="time:object:",
            )
        )
        cases.append(
            _case(
                f"figure_{index:03d}",
                "그림 필요",
                f"그림 F{index}에 표시된 링크의 각도와 길이를 이용하여 점 B의 속도를 구하여라. 그림은 제공되지 않았다.",
                None,
                None,
                [],
                None,
                entity="point",
                status="needs_figure",
                terminal="needs_figure",
                clarify=True,
                figure="required",
                segments=[],
                events=[],
                query="final_velocity:point:",
            )
        )
        force = index + 1
        cases.append(
            _case(
                f"solver_gap_{index:03d}",
                "solver gap",
                f"비선형 유체 안에서 물체 S{index}에 작용하는 속도 의존 항력이 {force}N일 때 결합 난류장을 구하여라.",
                "nonlinear_turbulent_flow",
                None,
                [f"force:{force}:N"],
                None,
                status="solver_gap",
                terminal="solver_gap",
                query="force:object:motion_1",
            )
        )
    return BenchmarkManifest(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        corpus_kind="repository_safe_paraphrased_seed",
        copyright_status="independently_authored_no_textbook_source_copied",
        cases=cases,
    )


def binding_stress_manifest() -> BenchmarkManifest:
    """Focused gold cases for identity, segment, temporal, direction, and relation closure."""

    specs = [
        (
            "binding_multi_entity",
            "수레 A와 B가 충돌 직전에 각각 오른쪽 3m/s와 왼쪽 2m/s로 움직인다.",
            ["cart_a", "cart_b"],
            ["collision:target"],
            ["velocity:3:m/s", "velocity:2:m/s"],
            {"fact_1": "cart_a", "fact_2": "cart_b"},
            {"fact_1": "collision", "fact_2": "collision"},
            ["collides_with:cart_a:cart_b"],
            ["just_before_collision"],
        ),
        (
            "binding_multi_segment",
            "물체가 첫 구간에서 4m 이동한 뒤 둘째 구간에서 6m 이동한다.",
            ["object"],
            ["segment_1:required_context", "segment_2:target"],
            ["distance:4:m", "distance:6:m"],
            {"fact_1": "object", "fact_2": "object"},
            {"fact_1": "segment_1", "fact_2": "segment_2"},
            [],
            ["reaches_position"],
        ),
        (
            "binding_before_after",
            "충돌 직전 속력은 5m/s이고 충돌 직후 속력은 1m/s이다.",
            ["object"],
            ["collision:target"],
            ["velocity:5:m/s", "velocity:1:m/s"],
            {"fact_1": "object", "fact_2": "object"},
            {"fact_1": "collision", "fact_2": "collision"},
            [],
            ["just_before_collision", "just_after_collision"],
        ),
        (
            "binding_repeated_symbol_direction",
            "두 물체의 같은 속력 3m/s가 각각 오른쪽과 왼쪽을 향한다.",
            ["object_a", "object_b"],
            ["motion_1:target"],
            ["velocity:3:m/s", "velocity:3:m/s"],
            {"fact_1": "object_a", "fact_2": "object_b"},
            {"fact_1": "motion_1", "fact_2": "motion_1"},
            ["moves_relative_to:object_a:object_b"],
            ["start"],
        ),
        (
            "binding_relation_role",
            "질량 2kg인 추 A와 4kg인 추 B가 한 줄로 연결되어 있다.",
            ["mass_a", "mass_b"],
            ["constraint:target"],
            ["mass:2:kg", "mass:4:kg"],
            {"fact_1": "mass_a", "fact_2": "mass_b"},
            {"fact_1": "constraint", "fact_2": "constraint"},
            ["connected_by_rope:mass_a:mass_b"],
            ["start"],
        ),
    ]
    cases = []
    for case_id, text, entities, segments, facts, entity_binding, segment_binding, relations, events in specs:
        cases.append(
            BenchmarkCase(
                case_id=case_id,
                provenance=PROVENANCE,
                category="binding_closure_stress",
                problem_text=text,
                gold=GoldLabels(
                    entities=entities,
                    segments=segments,
                    events=events,
                    explicit_facts=facts,
                    fact_entity_binding=entity_binding,
                    fact_segment_binding=segment_binding,
                    relations=relations,
                    queries=[f"impulse:{entities[0]}:{segments[-1].split(':')[0]}"],
                    assumptions=[],
                    required_clarification=False,
                    figure_dependency="none",
                    expected_system_type="impulse_momentum",
                    expected_solver=None,
                    supported_status="solver_gap",
                    expected_end_to_end_answer=None,
                    expected_terminal_status="solver_gap",
                ),
            )
        )
    return BenchmarkManifest(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        corpus_kind="repository_safe_binding_stress",
        copyright_status="independently_authored_no_textbook_source_copied",
        cases=cases,
    )


__all__ = ["PROVENANCE", "binding_stress_manifest", "repository_safe_seed_manifest"]
