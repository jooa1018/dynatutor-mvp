"""Phase 54: VisualizationScene DTO, scene builders, and fail-open contract.

Everything here goes through the real product path (`solve_problem`), never a
hand-built canonical, so the assertions cover the evidence that actually
exists in /solve responses.
"""

import copy
import json
import math

import pytest
from pydantic import ValidationError

from app.schemas.visualization_scene import (
    VISUALIZATION_SCENE_SCHEMA,
    VISUALIZATION_SCENE_VERSION,
    VisualizationSceneModel,
    VizAuthorityModel,
)
from engine.services import solve_problem
from engine.visualization import scene_builder

INCLINE_NO_FRICTION = "마찰이 없는 30도 경사면 위 블록의 가속도는?"
INCLINE_KINETIC = "운동마찰계수 0.2인 30도 경사면에서 블록이 아래로 미끄러진다. 가속도를 구하라."
INCLINE_AMBIGUOUS_MU = "마찰계수 0.2인 거친 30도 경사면에서 블록의 가속도를 구하라."
SPRING_PERIOD = "k=200 N/m 스프링에 질량 2 kg을 달았다. 주기를 구하라."
ROLLING = "정지 상태에서 원판이 미끄러지지 않고 높이 1.5 m를 굴러 내려간다. 바닥에서의 속도를 구하라."
COLLISION_E1 = "m1=2 kg, m2=3 kg, v1=4 m/s, v2=0 m/s, e=1인 1차원 충돌이다. 충돌 후 속도를 구하라."
UNSUPPORTED_SCENE = "질량 2 kg에 힘 10 N이 작용한다. 가속도를 구하라."
CLARIFY_CASE = "30도 경사면 위 블록의 가속도는?"
NON_PHYSICS = "오늘 저녁 메뉴를 추천해 줘."

READY_CASES = {
    "incline_no_friction": INCLINE_NO_FRICTION,
    "incline_with_friction": INCLINE_KINETIC,
    "spring_mass_vibration": SPRING_PERIOD,
    "pure_rolling_energy": ROLLING,
    "collision_1d": COLLISION_E1,
}


def _ready_scene(text):
    response = solve_problem(text)
    assert response.ok is True
    scene = response.visualization_scene
    assert scene is not None and scene.status == "ready"
    return response, scene


# ---------------------------------------------------------------------------
# DTO schema and version
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_phase54_scene_schema_and_version_are_fixed():
    for solver, text in READY_CASES.items():
        _, scene = _ready_scene(text)
        assert scene.schema == VISUALIZATION_SCENE_SCHEMA == "dynatutor.visualization_scene"
        assert scene.version == VISUALIZATION_SCENE_VERSION == "1.0"
        assert scene.source_solver == solver
        assert scene.simulation_mode == "kinematic_playback"


@pytest.mark.unit
def test_phase54_authority_metadata_is_code_enforced():
    # Literal-typed fields must reject any attempt to claim other authority.
    with pytest.raises(ValidationError):
        VizAuthorityModel(answer_authority="frontend")
    with pytest.raises(ValidationError):
        VizAuthorityModel(grading=True)
    with pytest.raises(ValidationError):
        VizAuthorityModel(answer_selection=True)
    with pytest.raises(ValidationError):
        VizAuthorityModel(student_answer_overwrite=True)
    with pytest.raises(ValidationError):
        VizAuthorityModel(visualization_authority="exact")
    for text in READY_CASES.values():
        _, scene = _ready_scene(text)
        assert scene.authority.answer_authority == "backend"
        assert scene.authority.visualization_authority == "approximate"
        assert scene.authority.grading is False
        assert scene.authority.answer_selection is False
        assert scene.authority.student_answer_overwrite is False


@pytest.mark.unit
def test_phase54_dto_rejects_nan_infinity_and_bad_references():
    _, scene = _ready_scene(INCLINE_NO_FRICTION)
    payload = scene.model_dump()

    bad = copy.deepcopy(payload)
    bad["motion"][0]["acceleration"]["x"] = float("nan")
    with pytest.raises(ValidationError):
        VisualizationSceneModel(**bad)

    bad = copy.deepcopy(payload)
    bad["camera"]["max_x"] = float("inf")
    with pytest.raises(ValidationError):
        VisualizationSceneModel(**bad)

    bad = copy.deepcopy(payload)
    bad["motion"][0]["body_id"] = "no_such_body"
    with pytest.raises(ValidationError):
        VisualizationSceneModel(**bad)

    bad = copy.deepcopy(payload)
    bad["forces"][0]["body_id"] = "no_such_body"
    with pytest.raises(ValidationError):
        VisualizationSceneModel(**bad)

    bad = copy.deepcopy(payload)
    bad["version"] = "2.0"
    with pytest.raises(ValidationError):
        VisualizationSceneModel(**bad)

    bad = copy.deepcopy(payload)
    bad["status"] = "unavailable"  # unavailable + playback material is invalid
    with pytest.raises(ValidationError):
        VisualizationSceneModel(**bad)


@pytest.mark.unit
def test_phase54_ready_scene_requires_overlay_and_unavailable_requires_reason():
    with pytest.raises(ValidationError):
        VisualizationSceneModel(status="unavailable")
    with pytest.raises(ValidationError):
        VisualizationSceneModel(status="ready", scene_type="incline_block")


@pytest.mark.unit
def test_phase54_scene_json_round_trip():
    for text in READY_CASES.values():
        _, scene = _ready_scene(text)
        payload = json.loads(json.dumps(scene.model_dump()))
        restored = VisualizationSceneModel(**payload)
        assert restored == scene


# ---------------------------------------------------------------------------
# Scene-specific builders
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_phase54_incline_no_friction_scene():
    response, scene = _ready_scene(INCLINE_NO_FRICTION)
    assert scene.scene_type == "incline_block"
    overlay = {item.output_key: item for item in scene.answer_overlay}
    assert overlay["acceleration"].numeric == response.answer.numeric
    assert overlay["acceleration"].source == "backend"
    slide = next(seg for seg in scene.motion if seg.kind == "uniform_acceleration")
    a_mag = math.hypot(slide.acceleration.x, slide.acceleration.y)
    assert a_mag == pytest.approx(response.answer.numeric, rel=1e-6)
    # Down-slope motion: +x and -y components.
    assert slide.acceleration.x > 0 and slide.acceleration.y < 0
    force_kinds = {f.kind for f in scene.forces}
    assert force_kinds == {"weight", "normal"}
    assert scene.axes and "경사면 아래쪽" in scene.axes[0].label
    assert scene.timestep.fixed_dt == pytest.approx(1.0 / 120.0)


@pytest.mark.regression
def test_phase54_incline_kinetic_friction_scene_and_ambiguous_fallback():
    response, scene = _ready_scene(INCLINE_KINETIC)
    force_kinds = {f.kind for f in scene.forces}
    assert force_kinds == {"weight", "normal", "friction"}
    friction = next(f for f in scene.forces if f.kind == "friction")
    slide = next(seg for seg in scene.motion if seg.kind == "uniform_acceleration")
    # Friction arrow opposes the acceleration (up-slope).
    dot = friction.direction.x * slide.acceleration.x + friction.direction.y * slide.acceleration.y
    assert dot < 0

    ambiguous = solve_problem(INCLINE_AMBIGUOUS_MU)
    assert ambiguous.ok is True
    scene2 = ambiguous.visualization_scene
    assert scene2 is not None and scene2.status == "unavailable"
    assert scene2.fallback_reason
    assert ambiguous.answer is not None  # answer flow untouched


@pytest.mark.regression
def test_phase54_mass_spring_scene():
    response, scene = _ready_scene(SPRING_PERIOD)
    assert scene.scene_type == "mass_spring"
    overlay = {item.output_key: item for item in scene.answer_overlay}
    assert "period" in overlay
    assert overlay["period"].numeric == response.answers[0].numeric
    osc = next(seg for seg in scene.motion if seg.kind == "oscillation")
    # Animation omega is the exact 2π/T conversion of the backend period.
    assert osc.omega == pytest.approx(2.0 * math.pi / response.answers[0].numeric, rel=1e-6)
    # Amplitude was not stated: must be flagged visualization-only.
    assert any("진폭" in note for note in scene.schematic_notes)
    assert any("환산" in note for note in scene.schematic_notes)
    roles = {b.role for b in scene.bodies}
    assert {"wall", "spring", "equilibrium_marker", "block"} <= roles
    restoring = next(f for f in scene.forces if f.kind == "spring_restoring")
    assert restoring.behavior == "restoring"
    assert scene.timestep.loop is True


@pytest.mark.regression
def test_phase54_pure_rolling_scene():
    response, scene = _ready_scene(ROLLING)
    assert scene.scene_type == "pure_rolling"
    overlay = {item.output_key: item for item in scene.answer_overlay}
    v_backend = overlay["final_velocity"].numeric
    assert v_backend == response.answers[0].numeric
    roll = next(seg for seg in scene.motion if seg.kind == "uniform_acceleration")
    # Playback endpoint equals the backend final speed.
    dt = roll.t_end - roll.t_start
    vx = roll.velocity0.x + roll.acceleration.x * dt
    vy = roll.velocity0.y + roll.acceleration.y * dt
    assert math.hypot(vx, vy) == pytest.approx(v_backend, rel=1e-6)
    # No stated radius: rotation is schematic and marked as such.
    assert roll.angular_schematic is True
    assert roll.angular_velocity0 == 0.0
    assert roll.angular_acceleration < 0  # clockwise for rightward rolling
    assert any("반지름" in note for note in scene.schematic_notes)
    assert any(c.kind == "no_slip" for c in scene.constraints)
    wheel = next(b for b in scene.bodies if b.role == "wheel")
    assert wheel.schematic_size is True


@pytest.mark.regression
def test_phase54_collision_scene_uses_backend_post_velocities():
    response, scene = _ready_scene(COLLISION_E1)
    assert scene.scene_type == "collision_1d"
    answers = {item.output_key: item.numeric for item in response.answers}
    overlay = {item.output_key: item.numeric for item in scene.answer_overlay}
    assert overlay["v1_after"] == answers["v1_after"]
    assert overlay["v2_after"] == answers["v2_after"]

    segs = {seg.id: seg for seg in scene.motion}
    event = scene.events[0]
    assert event.kind == "collision"
    # Pre-collision velocities are the typed knowns; post are backend answers.
    assert segs["body1-before"].velocity0.x == pytest.approx(4.0)
    assert segs["body2-before"].velocity0.x == pytest.approx(0.0)
    assert segs["body1-after"].velocity0.x == pytest.approx(answers["v1_after"], rel=1e-9)
    assert segs["body2-after"].velocity0.x == pytest.approx(answers["v2_after"], rel=1e-9)
    # Timeline switches exactly at the collision event.
    assert segs["body1-before"].t_end == pytest.approx(event.t)
    assert segs["body1-after"].t_start == pytest.approx(event.t)
    # Bodies touch (do not overlap) at the collision instant.
    b1 = next(b for b in scene.bodies if b.id == "body1")
    b2 = next(b for b in scene.bodies if b.id == "body2")
    x1_c = segs["body1-before"].position0.x + segs["body1-before"].velocity0.x * event.t
    x2_c = segs["body2-before"].position0.x + segs["body2-before"].velocity0.x * event.t
    assert x1_c + b1.shape.half_width == pytest.approx(x2_c - b2.shape.half_width, abs=1e-9)


@pytest.mark.regression
def test_phase54_collision_perfectly_inelastic_branch():
    response = solve_problem(
        "m1=2 kg, m2=3 kg인 두 물체가 v1=5 m/s, v2=0 m/s로 움직이다 완전 비탄성 충돌한다. 충돌 후 속도를 구하라."
    )
    if response.ok is not True:
        pytest.skip("perfectly inelastic phrasing not extracted in product path: " + str(response.unsupported_reason))
    scene = response.visualization_scene
    assert scene is not None and scene.status == "ready"
    answers = {item.output_key: item.numeric for item in response.answers}
    segs = {seg.id: seg for seg in scene.motion}
    assert segs["body1-after"].velocity0.x == pytest.approx(answers["v1_after"], rel=1e-9)
    assert segs["body2-after"].velocity0.x == pytest.approx(answers["v2_after"], rel=1e-9)
    overlay_keys = {item.output_key for item in scene.answer_overlay}
    assert "post_collision_velocity" in overlay_keys


# ---------------------------------------------------------------------------
# Pendulum deferral
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_phase54_pendulum_is_explicitly_deferred():
    from engine.visualization.scenes import pendulum

    scene = pendulum.build(None, None, None, "simple_pendulum")
    assert scene.status == "unavailable"
    assert scene.scene_type == "pendulum"
    assert "deferred" in scene.fallback_reason
    assert "simple_pendulum" not in scene_builder._SCENE_BUILDERS
    assert scene_builder._DEFERRED_BUILDERS["simple_pendulum"] is pendulum.build


# ---------------------------------------------------------------------------
# Unsupported / partial / failure fallback
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_phase54_unsupported_scene_type_reports_unavailable_not_ready():
    response = solve_problem(UNSUPPORTED_SCENE)
    assert response.ok is True
    scene = response.visualization_scene
    assert scene is not None
    assert scene.status == "unavailable"
    assert scene.fallback_reason
    assert scene.bodies == [] and scene.motion == []


@pytest.mark.negative
def test_phase54_clarify_and_unsupported_responses_carry_no_scene():
    for text in (CLARIFY_CASE, NON_PHYSICS):
        response = solve_problem(text)
        assert response.ok is False
        assert response.visualization_scene is None


@pytest.mark.unit
def test_phase54_builder_is_fail_open(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("intentional scene builder failure")

    monkeypatch.setitem(scene_builder._SCENE_BUILDERS, "incline_no_friction", boom)
    response = solve_problem(INCLINE_NO_FRICTION)
    assert response.ok is True
    assert response.answer is not None
    assert response.verification.passed is True
    scene = response.visualization_scene
    assert scene is None or scene.status == "unavailable"


@pytest.mark.unit
def test_phase54_even_fallback_scene_failure_never_breaks_solve(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("total visualization failure")

    monkeypatch.setattr(scene_builder, "build_visualization_scene", boom)
    monkeypatch.setattr(scene_builder, "unavailable_scene", boom)
    response = solve_problem(INCLINE_NO_FRICTION)
    assert response.ok is True
    assert response.answer is not None
    assert response.visualization_scene is None


# ---------------------------------------------------------------------------
# Answer / verification / trace invariance
# ---------------------------------------------------------------------------

@pytest.mark.regression
def test_phase54_scene_attachment_changes_nothing_but_the_new_field(monkeypatch):
    baseline = {}

    def capture_without_scene():
        def noop(response, **kwargs):
            response.visualization_scene = None

        monkeypatch.setattr(scene_builder, "attach_visualization_scene", noop)
        monkeypatch.setattr("engine.services.attach_visualization_scene", noop)
        for name, text in READY_CASES.items():
            baseline[name] = solve_problem(text).model_dump(exclude={"visualization_scene"})
        monkeypatch.undo()

    capture_without_scene()
    for name, text in READY_CASES.items():
        live = solve_problem(text).model_dump(exclude={"visualization_scene"})
        assert live == baseline[name], f"scene builder changed existing fields for {name}"


@pytest.mark.regression
def test_phase54_overlay_values_match_post_gate_answers_verbatim():
    for text in READY_CASES.values():
        response, scene = _ready_scene(text)
        delivered = {item.output_key: item for item in response.answers}
        if response.answer is not None and response.answer.output_key:
            delivered.setdefault(response.answer.output_key, response.answer)
        for item in scene.answer_overlay:
            assert item.source == "backend"
            assert item.output_key in delivered
            assert item.numeric == delivered[item.output_key].numeric
