from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

import pytest

from engine import services
from engine.explanation_trace import _validate_structured_fact
from engine.models import CanonicalProblem, Quantity, SemanticFactEvidence
from engine.physics_core.inertia import INERTIA_BETA, beta_for_shape


_G_DEFAULT = "중력가속도 g = 9.81 m/s² 기본값 사용"


def _q(symbol, value, unit, *, provenance_hint=None):
    return Quantity(
        symbol=symbol,
        value=value,
        unit=unit,
        provenance_hint=provenance_hint,
    )


def _default_g():
    return _q("g", 9.81, "m/s^2", provenance_hint="domain_default")


def _canonical(case: str) -> CanonicalProblem:
    if case == "incline_no_friction":
        return CanonicalProblem(
            system_type="particle_on_incline",
            subtype="no_friction",
            surface_type="incline",
            displacement_direction="down_slope",
            knowns={
                "m": _q("m", 5, "kg"),
                "theta": _q("theta", 30, "deg"),
                "g": _default_g(),
            },
            unknowns=["acceleration"],
            requested_outputs=["acceleration"],
            flags={"no_friction": True},
            assumptions=[_G_DEFAULT, "블록을 질점으로 모델링", "마찰력 없음"],
            raw_text="질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.",
        )
    if case == "incline_with_friction":
        return CanonicalProblem(
            system_type="particle_on_incline",
            subtype="with_friction",
            surface_type="incline",
            friction_type="kinetic",
            displacement_direction="down_slope",
            knowns={
                "theta": _q("theta", 30, "deg"),
                "mu": _q("mu", 0.2, None),
                "m": _q("m", 5, "kg"),
                "g": _default_g(),
            },
            unknowns=["acceleration"],
            requested_outputs=["acceleration"],
            flags={"has_friction": True},
            assumptions=[_G_DEFAULT, "블록을 질점으로 모델링"],
            raw_text="마찰계수 0.2인 거친 30도 경사면에서 블록의 가속도를 구하라.",
        )
    if case == "pure_rolling_energy":
        return CanonicalProblem(
            system_type="pure_rolling_energy",
            subtype="rolling_on_incline",
            surface_type="incline",
            body_shape="disk",
            knowns={"h": _q("h", 1.5, "m"), "g": _default_g()},
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
            flags={"starts_from_rest": True, "pure_rolling": True, "no_slip": True},
            assumptions=[
                _G_DEFAULT,
                "미끄러지지 않는 순수 구름",
                "정지마찰은 일을 하지 않는 이상적 조건",
                "강체 종류 또는 관성모멘트가 필요함",
            ],
            raw_text="정지 상태에서 원판이 미끄러지지 않고 높이 1.5 m를 굴러 내려간다.",
        )
    if case == "spring_mass_vibration":
        return CanonicalProblem(
            system_type="spring_mass_vibration",
            knowns={"k": _q("k", 200, "N/m"), "m": _q("m", 2, "kg")},
            unknowns=["period"],
            requested_outputs=["period"],
            assumptions=[
                _G_DEFAULT, "감쇠 없음", "외력 없음", "평형 위치 기준 1자유도 운동",
            ],
            raw_text="k=200 N/m 스프링에 질량 2 kg을 달았다. 주기를 구하라.",
        )
    if case == "work_energy_speed":
        return CanonicalProblem(
            system_type="work_energy_speed",
            knowns={
                "m": _q("m", 2, "kg"),
                "W": _q("W", 16, "J"),
                "v0": _q("v0", 1, "m/s"),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
            assumptions=[_G_DEFAULT],
            raw_text="질량 2 kg, 초기속도 1 m/s 물체에 알짜일 16 J가 작용한다.",
        )
    if case == "vertical_circle":
        return CanonicalProblem(
            system_type="vertical_circle",
            subtype="top",
            knowns={
                "m": _q("m", 2, "kg"),
                "R": _q("R", 3, "m"),
                "v": _q("v", 8, "m/s"),
                "g": _q("g", 9.81, "m/s^2"),
            },
            unknowns=["tension"],
            requested_outputs=["tension"],
            assumptions=[_G_DEFAULT],
            raw_text="질량 2 kg 물체가 반지름 3 m 수직 원의 최고점에서 8 m/s이다. 장력을 구하라.",
        )
    if case == "spring_energy_speed":
        return CanonicalProblem(
            system_type="spring_energy",
            knowns={"k": _q("k", 200, "N/m"), "x": _q("x", 0.1, "m")},
            unknowns=["elastic_energy"],
            requested_outputs=["elastic_energy"],
            assumptions=[_G_DEFAULT, "마찰 없음", "스프링 탄성에너지가 운동에너지로 전환"],
            raw_text="k=200 N/m 스프링을 0.1 m 압축했다. 탄성에너지를 구하라.",
        )
    if case == "flat_curve_friction":
        return CanonicalProblem(
            system_type="flat_curve_friction",
            knowns={
                "R": _q("R", 50, "m"),
                "mu": _q("mu", 0.4, None),
                "g": _default_g(),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
            assumptions=[_G_DEFAULT, "등속 원운동으로 모델링"],
            raw_text="반지름 50 m 평평한 커브의 정지마찰계수는 0.4이다. 최대속도를 구하라.",
        )
    if case == "banked_curve_no_friction":
        return CanonicalProblem(
            system_type="banked_curve_no_friction",
            knowns={
                "R": _q("R", 50, "m"),
                "theta": _q("theta", 20, "deg"),
                "g": _default_g(),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
            flags={"no_friction": True},
            assumptions=[_G_DEFAULT, "등속 원운동으로 모델링"],
            raw_text="마찰 없는 반지름 50 m, 20도 뱅크 커브의 설계속도를 구하라.",
        )
    if case == "slot_pin_relative_motion":
        return CanonicalProblem(
            system_type="slot_pin_relative_motion",
            knowns={
                "r": _q("r", 2, "m"),
                "omega": _q("omega", 3, "rad/s"),
                "rdot": _q("rdot", 4, "m/s"),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
            assumptions=[
                _G_DEFAULT,
                "슬롯을 따라 미끄러지는 핀을 회전 좌표계의 극좌표 운동으로 모델링",
                "r 방향 상대속도와 θ 방향 회전속도를 동시에 고려",
            ],
            raw_text="r=2 m, omega=3 rad/s, rdot=4 m/s인 회전 슬롯 핀의 속도를 구하라.",
        )
    raise AssertionError(case)


def _solve(monkeypatch, canonical: CanonicalProblem):
    value = deepcopy(canonical)
    monkeypatch.setattr(services, "extract_problem", lambda _text: deepcopy(value))
    return services.solve_problem(value.raw_text)


def _legacy_negative_canonical(case: str) -> CanonicalProblem:
    if case == "projectile":
        return CanonicalProblem(
            system_type="projectile_motion",
            subtype="same_level",
            knowns={"v0": _q("v0", 10, "m/s"), "g": _default_g()},
            launch_angle_deg=45,
            launch_height=0,
            landing_height=0,
            unknowns=["range"],
            requested_outputs=["range"],
            raw_text="같은 높이에서 10 m/s, 45도로 발사한 포물체의 사거리를 구하라.",
        )
    if case == "atwood":
        return CanonicalProblem(
            system_type="pulley_atwood",
            pulley_topology="atwood",
            knowns={
                "m1": _q("m1", 2, "kg"),
                "m2": _q("m2", 3, "kg"),
                "g": _default_g(),
            },
            unknowns=["acceleration", "tension"],
            requested_outputs=["acceleration", "tension"],
            flags={"ideal_pulley": True, "massless_rope": True},
            raw_text="이상적인 Atwood 장치에서 m1=2 kg, m2=3 kg의 가속도와 장력을 구하라.",
        )
    if case == "table_hanging":
        return CanonicalProblem(
            system_type="pulley_table_hanging",
            pulley_topology="table_hanging",
            surface_type="horizontal",
            friction_type="none",
            knowns={
                "m1": _q("m1", 3, "kg"),
                "m2": _q("m2", 2, "kg"),
                "g": _default_g(),
            },
            unknowns=["acceleration", "tension"],
            requested_outputs=["acceleration", "tension"],
            flags={"no_friction": True, "ideal_pulley": True, "massless_rope": True},
            raw_text="마찰 없는 수평면의 3 kg 블록과 2 kg 추의 가속도와 장력을 구하라.",
        )
    if case == "horizontal_friction":
        return CanonicalProblem(
            system_type="horizontal_friction_force",
            surface_type="horizontal",
            friction_type="kinetic",
            knowns={
                "m": _q("m", 5, "kg"),
                "mu_k": _q("mu_k", 0.2, None),
                "g": _default_g(),
            },
            unknowns=["friction_force"],
            requested_outputs=["friction_force"],
            raw_text="5 kg 물체가 운동마찰계수 0.2인 수평면을 미끄러질 때 마찰력을 구하라.",
        )
    if case == "kinematics":
        return CanonicalProblem(
            system_type="constant_acceleration_1d",
            knowns={
                "v0": _q("v0", 1, "m/s"),
                "a": _q("a", 2, "m/s^2"),
                "t": _q("t", 3, "s"),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
            raw_text="초기속도 1 m/s, 가속도 2 m/s²로 3 s 이동한 최종속도를 구하라.",
        )
    if case == "collision":
        return CanonicalProblem(
            system_type="collision_1d",
            knowns={
                "m1": _q("m1", 2, "kg"),
                "m2": _q("m2", 3, "kg"),
                "v1": _q("v1", 4, "m/s"),
                "v2": _q("v2", 0, "m/s"),
                "e": _q("e", 1, None),
            },
            unknowns=["v1_after", "v2_after"],
            requested_outputs=["v1_after", "v2_after"],
            raw_text="m1=2 kg, m2=3 kg, v1=4 m/s, v2=0 m/s, e=1인 1차원 충돌이다.",
        )
    raise AssertionError(case)


def _unmigrated_migrated_solver_branch(case: str) -> CanonicalProblem:
    if case == "vertical-min-speed":
        canonical = _canonical("vertical_circle")
        canonical.knowns.pop("m")
        canonical.knowns.pop("v")
        canonical.unknowns = ["minimum_speed"]
        canonical.requested_outputs = ["minimum_speed"]
        return canonical
    if case in {"spring-speed-only", "spring-mixed"}:
        canonical = _canonical("spring_energy_speed")
        canonical.knowns["m"] = _q("m", 2, "kg")
        canonical.unknowns = ["final_velocity"]
        canonical.requested_outputs = ["final_velocity"]
        if case == "spring-mixed":
            canonical.unknowns.insert(0, "elastic_energy")
            canonical.requested_outputs.insert(0, "elastic_energy")
        return canonical
    if case == "spring-raw-text-only":
        canonical = _canonical("spring_energy_speed")
        canonical.unknowns = []
        canonical.requested_outputs = []
        return canonical
    if case == "work-force-distance":
        canonical = _canonical("work_energy_speed")
        canonical.knowns.pop("W")
        canonical.knowns["F"] = _q("F", 8, "N")
        canonical.knowns["s"] = _q("s", 2, "m")
        return canonical
    if case == "slot-acceleration-mixed":
        canonical = _canonical("slot_pin_relative_motion")
        canonical.knowns["alpha"] = _q("alpha", 1, "rad/s^2")
        canonical.knowns["rddot"] = _q("rddot", 0.5, "m/s^2")
        canonical.unknowns = ["final_velocity", "acceleration"]
        canonical.requested_outputs = list(canonical.unknowns)
        return canonical
    if case == "rolling-omega":
        canonical = _canonical("pure_rolling_energy")
        canonical.knowns["R"] = _q("R", 0.4, "m")
        canonical.unknowns = ["final_velocity", "angular_velocity"]
        canonical.requested_outputs = list(canonical.unknowns)
        return canonical
    raise AssertionError(case)


def _assert_excluded_or_terminal_trace(response, selected_solver: str) -> None:
    trace = response.explanation_trace
    if trace is None:
        assert response.ok is True
        assert response.diagnosis.selected_solver == selected_solver
        return

    assert response.ok is False
    assert response.answer is None
    assert response.answers == []
    assert response.diagnosis.selected_solver in {None, selected_solver}
    assert trace.selected_solver == response.diagnosis.selected_solver
    assert trace.status != "fully_grounded"
    assert trace.answer_derivation == []
    step_kinds = {step.kind for step in trace.student_steps}
    assert step_kinds == {"status", "required_input"}
    assert step_kinds.isdisjoint(
        {"calculation", "equation", "substitution", "answer", "final_answer"}
    )
    assert all(step.math is None for step in trace.student_steps)


_SOLVER_IDS = (
    "incline_no_friction",
    "incline_with_friction",
    "pure_rolling_energy",
    "spring_mass_vibration",
    "work_energy_speed",
    "vertical_circle",
    "spring_energy_speed",
    "flat_curve_friction",
    "banked_curve_no_friction",
    "slot_pin_relative_motion",
)

_SOLVER_CONTRACTS = {
    "incline_no_friction": {
        "frame": ("cartesian_2d", ("x", "y"), ("down_slope", "normal_outward")),
        "equations": {
            "incline-no-friction.acceleration": "a = g sin(theta)",
        },
        "outputs": (("acceleration", "m/s²"),),
    },
    "incline_with_friction": {
        "frame": ("cartesian_2d", ("x", "y"), ("down_slope", "normal_outward")),
        "equations": {
            "incline-with-friction.acceleration": "a = g (sin(theta) - mu cos(theta))",
        },
        "outputs": (("acceleration", "m/s²"),),
    },
    "pure_rolling_energy": {
        "frame": ("body_fixed_2d", ("x", "theta"), ("down_slope", "clockwise")),
        "equations": {
            "rolling.shape-inertia": "beta(disk) = 1 / 2",
            "rolling.energy-speed": "v = sqrt(v0^2 + 2 g h / (1 + beta))",
        },
        "outputs": (("final_velocity", "m/s"),),
    },
    "spring_mass_vibration": {
        "frame": ("cartesian_1d", ("x",), ("right",)),
        "equations": {
            "spring-vibration.period": "T = 2 pi sqrt(m / k)",
        },
        "outputs": (("period", "s"),),
    },
    "work_energy_speed": {
        "frame": ("cartesian_1d", ("x",), ("along_motion",)),
        "equations": {
            "work-energy.final-speed": "v_f = sqrt(v_i^2 + 2 W / m)",
        },
        "outputs": (("final_velocity", "m/s"),),
    },
    "vertical_circle": {
        "frame": ("path_tangent_normal", ("t", "n"), ("tangential_positive", "normal_inward")),
        "equations": {
            "vertical-circle.tension": "T = m v^2 / R - m g",
        },
        "outputs": (("tension", "N"),),
    },
    "spring_energy_speed": {
        "frame": ("cartesian_1d", ("x",), ("right",)),
        "equations": {
            "spring-energy.elastic-energy": "E = 0.5 k x^2",
        },
        "outputs": (("elastic_energy", "J"),),
    },
    "flat_curve_friction": {
        "frame": ("path_tangent_normal", ("t", "n"), ("tangential_positive", "normal_inward")),
        "equations": {
            "flat-curve.limiting-speed": "v = sqrt(mu g R)",
        },
        "outputs": (("final_velocity", "m/s"),),
    },
    "banked_curve_no_friction": {
        "frame": ("path_tangent_normal", ("t", "n"), ("tangential_positive", "normal_inward")),
        "equations": {
            "banked-curve.design-speed": "v = sqrt(g R tan(theta))",
        },
        "outputs": (("final_velocity", "m/s"),),
    },
    "slot_pin_relative_motion": {
        "frame": ("polar_2d", ("e_r", "e_theta"), ("increasing_r", "increasing_theta")),
        "equations": {
            "slot-pin.radial-speed": "v_r = rdot",
            "slot-pin.transverse-speed": "v_theta = r omega",
            "slot-pin.speed-magnitude": "v = sqrt(v_r^2 + v_theta^2)",
        },
        "outputs": (("final_velocity", "m/s"),),
    },
}


@pytest.mark.unit
@pytest.mark.parametrize("solver_id", _SOLVER_IDS)
def test_normal_solver_request_has_closed_deterministic_trace(monkeypatch, solver_id):
    response = _solve(monkeypatch, _canonical(solver_id))

    assert response.ok is True
    assert response.diagnosis.selected_solver == solver_id
    trace = response.explanation_trace
    assert trace is not None
    assert trace.status == "fully_grounded"
    assert trace.selected_solver == solver_id
    assert trace.coordinate_frame is not None
    expected = _SOLVER_CONTRACTS[solver_id]
    assert (
        trace.coordinate_frame.coordinate_system,
        tuple(trace.coordinate_frame.axes),
        tuple(trace.coordinate_frame.positive_directions),
    ) == expected["frame"]
    assert trace.equation_ids == [item.equation_id for item in trace.equations]
    equations = {item.equation_id: item for item in trace.equations}
    assert {
        equation_id: equations[equation_id].expression
        for equation_id in expected["equations"]
    } == expected["equations"]
    substitutions = {item.substitution_id: item for item in trace.substitutions}
    fact_ids = {
        item.fact_id for item in (*trace.explicit_facts, *trace.assumptions)
    }
    assert all(item.provenance for item in trace.equations)
    assert all(set(item.fact_ids) <= fact_ids for item in trace.equations)
    assert all(item.equation_id in equations for item in trace.substitutions)
    assert len(trace.answer_derivation) == len(response.answers)
    assert tuple(
        (item.output_key, item.unit) for item in trace.answer_derivation
    ) == expected["outputs"]
    for item, derivation in zip(response.answers, trace.answer_derivation):
        assert derivation.output_key == item.output_key
        assert derivation.numeric == item.numeric
        assert math.copysign(1.0, derivation.numeric) == math.copysign(
            1.0, item.numeric
        )
        assert derivation.unit == item.unit
        assert set(derivation.equation_ids) <= equations.keys()
        assert set(derivation.substitution_ids) <= substitutions.keys()


@pytest.mark.unit
def test_actual_extractor_spring_energy_request_is_fully_grounded():
    response = services.solve_problem(
        "k=200 N/m 스프링을 0.1 m 압축했다. 탄성에너지를 구하라."
    )

    assert response.ok is True
    assert response.diagnosis.selected_solver == "spring_energy_speed"
    assert response.explanation_trace is not None
    assert response.explanation_trace.status == "fully_grounded"
    assert [item.output_key for item in response.explanation_trace.answer_derivation] == [
        "elastic_energy"
    ]


@pytest.mark.unit
def test_default_and_explicit_gravity_are_mutually_exclusive(monkeypatch):
    default_response = _solve(monkeypatch, _canonical("flat_curve_friction"))
    explicit = _canonical("flat_curve_friction")
    explicit.knowns["g"] = _q(
        "g", 9.81, "m/s^2", provenance_hint="explicit_text"
    )
    explicit_response = _solve(monkeypatch, explicit)

    default_trace = default_response.explanation_trace
    explicit_trace = explicit_response.explanation_trace
    assert {item.fact_id for item in default_trace.assumptions} >= {
        "assumption:gravity_acceleration"
    }
    assert "known:g" not in {item.fact_id for item in default_trace.explicit_facts}
    assert "known:g" in {item.fact_id for item in explicit_trace.explicit_facts}
    assert "assumption:gravity_acceleration" not in {
        item.fact_id for item in explicit_trace.assumptions
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "fraction", "coefficient"),
    (
        ("solid_sphere", "2 / 5", 2 / 5),
        ("hollow_sphere", "2 / 3", 2 / 3),
        ("solid_cylinder", "1 / 2", 1 / 2),
        ("disk", "1 / 2", 1 / 2),
        ("hoop", "1", 1.0),
        ("ring", "1", 1.0),
    ),
)
def test_rolling_beta_is_derived_from_exact_shape_contract(
    monkeypatch, shape, fraction, coefficient
):
    canonical = _canonical("pure_rolling_energy")
    canonical.body_shape = shape
    response = _solve(monkeypatch, canonical)
    trace = response.explanation_trace
    beta_eq = next(item for item in trace.equations if item.output_ids == ["shape_beta"])
    beta_sub = next(
        item for item in trace.substitutions if item.output_id == "shape_beta"
    )

    assert INERTIA_BETA[shape] == coefficient
    assert beta_for_shape(shape) == coefficient
    assert beta_eq.expression == f"beta({shape}) = {fraction}"
    assert beta_eq.fact_ids == ["semantic:body_shape"]
    assert beta_sub.fact_ids == ["semantic:body_shape"]
    assert beta_sub.expression == f"beta({shape}) = {fraction} = {coefficient}"
    explicit_ids = {item.fact_id for item in trace.explicit_facts}
    assumption_ids = {item.fact_id for item in trace.assumptions}
    assert "flag:no_slip" in explicit_ids
    assert "assumption:no_slip" not in assumption_ids
    energy = next(item for item in trace.equations if item.equation_id == "rolling.energy-speed")
    assert "flag:no_slip" in energy.fact_ids
    assert "known:beta" not in {
        item.fact_id for item in trace.explicit_facts
    }


@pytest.mark.unit
def test_rolling_requires_explicit_no_slip_flag_for_evidence(monkeypatch):
    canonical = _canonical("pure_rolling_energy")
    canonical.flags.pop("no_slip")
    response = _solve(monkeypatch, canonical)

    assert response.ok is True
    assert response.explanation_trace is None


@pytest.mark.unit
def test_successful_migration_is_additive_only(monkeypatch):
    canonical = _canonical("incline_no_friction")
    migrated = _solve(monkeypatch, canonical)

    monkeypatch.setattr(
        "engine.solvers.incline.attach_evidence",
        lambda result, **_kwargs: result,
    )
    legacy = _solve(monkeypatch, canonical)
    migrated_payload = migrated.model_dump()
    legacy_payload = legacy.model_dump()
    migrated_payload.pop("explanation_trace")
    legacy_payload.pop("explanation_trace")

    assert migrated.explanation_trace.status == "fully_grounded"
    assert legacy.explanation_trace is None
    assert migrated_payload == legacy_payload
    assert any(
        "f = μN" in item
        for item in migrated.diagnosis.not_applicable_equations
    )


@pytest.mark.unit
def test_llm_switch_cannot_change_trace_physics(monkeypatch):
    canonical = _canonical("banked_curve_no_friction")
    monkeypatch.setenv("DYNATUTOR_USE_LLM", "0")
    off = _solve(monkeypatch, canonical).explanation_trace.model_dump()
    monkeypatch.setenv("DYNATUTOR_USE_LLM", "1")
    on = _solve(monkeypatch, canonical).explanation_trace.model_dump()
    assert on == off


@pytest.mark.unit
def test_incompatible_mixed_branches_remain_unmigrated(monkeypatch):
    slot = _canonical("slot_pin_relative_motion")
    slot.knowns["alpha"] = _q("alpha", 1, "rad/s^2")
    slot.knowns["rddot"] = _q("rddot", 0.5, "m/s^2")
    slot_response = _solve(monkeypatch, slot)

    spring = _canonical("spring_energy_speed")
    spring.knowns["m"] = _q("m", 2, "kg")
    spring.requested_outputs = ["elastic_energy", "final_velocity"]
    spring.unknowns = list(spring.requested_outputs)
    spring_response = _solve(monkeypatch, spring)

    assert slot_response.ok is True
    assert slot_response.explanation_trace is None
    assert spring_response.ok is True
    assert spring_response.explanation_trace is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("case", "selected_solver"),
    (
        ("projectile", "projectile_motion"),
        ("atwood", "pulley_atwood"),
        ("table_hanging", "pulley_table_hanging"),
        ("horizontal_friction", "horizontal_friction_force"),
        ("kinematics", "constant_acceleration_1d"),
        ("collision", "collision_1d"),
    ),
)
def test_unmigrated_legacy_solver_matrix_never_claims_grounding(
    monkeypatch, case, selected_solver
):
    response = _solve(monkeypatch, _legacy_negative_canonical(case))

    _assert_excluded_or_terminal_trace(response, selected_solver)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("case", "selected_solver"),
    (
        ("vertical-min-speed", "vertical_circle"),
        ("spring-speed-only", "spring_energy_speed"),
        ("spring-mixed", "spring_energy_speed"),
        ("spring-raw-text-only", "spring_energy_speed"),
        ("work-force-distance", "work_energy_speed"),
        ("slot-acceleration-mixed", "slot_pin_relative_motion"),
        ("rolling-omega", "pure_rolling_energy"),
    ),
)
def test_migrated_solver_negative_branch_matrix_stays_unmigrated(
    monkeypatch, case, selected_solver
):
    response = _solve(monkeypatch, _unmigrated_migrated_solver_branch(case))

    _assert_excluded_or_terminal_trace(response, selected_solver)


@pytest.mark.unit
def test_unproven_direction_non_si_and_optional_omega_fail_closed(monkeypatch):
    incline = _canonical("incline_with_friction")
    incline.displacement_direction = None
    unbound_direction = _solve(monkeypatch, incline)

    non_si = _canonical("incline_no_friction")
    non_si.knowns["theta"] = _q("theta", math.pi / 6, "rad")
    non_si_response = _solve(monkeypatch, non_si)

    rolling = _canonical("pure_rolling_energy")
    rolling.knowns["R"] = _q("R", 0.4, "m")
    optional_omega = _solve(monkeypatch, rolling)

    assert unbound_direction.ok is True
    assert unbound_direction.explanation_trace is None
    assert non_si_response.ok is True
    assert non_si_response.explanation_trace is None
    assert optional_omega.ok is True
    assert len(optional_omega.answers) == 2
    assert optional_omega.explanation_trace is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "unit"),
    ((9.8, "m/s^2"), (9.81, "m/s²")),
)
def test_forged_domain_default_gravity_never_fully_grounds(
    monkeypatch, value, unit
):
    canonical = _canonical("flat_curve_friction")
    canonical.knowns["g"] = _q(
        "g", value, unit, provenance_hint="domain_default"
    )
    response = _solve(monkeypatch, canonical)

    assert response.ok is True
    assert response.explanation_trace is not None
    assert response.explanation_trace.status != "fully_grounded"


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    (
        {"fact_id": "assumption:g"},
        {"value": 9.8},
        {"unit": "m/s²"},
        {"source": "solver_calculation"},
    ),
)
def test_numeric_gravity_assumption_rejects_forged_contract(mutation):
    fact = SemanticFactEvidence(
        "assumption:gravity_acceleration",
        "gravity_acceleration",
        9.81,
        unit="m/s^2",
        source="solver_assumption",
        classification="assumed",
    )
    assert _validate_structured_fact(
        replace(fact, **mutation),
        expected_group="assumption",
        system_type="flat_curve_friction",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "key,value",
    (
        ("damping", "included"),
        ("external_forcing", "present"),
        ("spring_law", "nonlinear"),
        ("energy_loss", "unknown"),
    ),
)
def test_spring_assumption_enums_reject_forged_values(key, value):
    fact = SemanticFactEvidence(
        f"assumption:{key}",
        key,
        value,
        source="solver_assumption",
        classification="assumed",
    )
    assert _validate_structured_fact(
        fact,
        expected_group="assumption",
        system_type="spring_mass_vibration",
    )


@pytest.mark.unit
@pytest.mark.parametrize("shape", ("block", "sphere", "cylinder"))
def test_rolling_builder_rejects_legacy_shape_aliases_but_keeps_global_union(shape):
    fact = SemanticFactEvidence(
        "semantic:body_shape",
        "body_shape",
        shape,
        source="canonical_semantic",
        classification="explicit",
    )

    assert _validate_structured_fact(
        fact,
        expected_group="semantic",
        system_type="pure_rolling_energy",
    )
    assert _validate_structured_fact(
        fact,
        expected_group="semantic",
        system_type="collision_1d",
    ) is None
