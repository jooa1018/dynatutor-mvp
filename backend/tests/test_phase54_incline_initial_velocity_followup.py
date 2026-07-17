"""Regression coverage for typed incline initial-velocity playback."""

import math

import pytest

from engine.extraction.extractor import extract_problem
from engine.model_builder import build_physical_model
from engine.services import solve_problem
from engine.visualization.scene_builder import build_visualization_scene


INCLINE_WITH_V0 = (
    "마찰이 없는 30도 경사면에서 블록의 초기 속도 v0=5 m/s이다. "
    "블록의 가속도를 구하라."
)
INCLINE_EXPLICIT_REST = (
    "마찰이 없는 30도 경사면에서 블록의 초기 속도 v0=0 m/s이다. "
    "블록의 가속도를 구하라."
)


def _typed_scene(direction: str):
    response = solve_problem(INCLINE_WITH_V0)
    assert response.ok is True
    assert response.diagnosis.selected_solver == "incline_no_friction"

    canonical = extract_problem(INCLINE_WITH_V0)
    assert canonical.knowns["v0"].value == pytest.approx(5.0)
    canonical.displacement_direction = direction
    scene = build_visualization_scene(
        response,
        canonical=canonical,
        physical_model=build_physical_model(canonical),
        selected_solver="incline_no_friction",
    )
    assert scene is not None and scene.status == "ready"
    return scene


@pytest.mark.negative
def test_nonzero_incline_v0_without_typed_direction_is_unavailable():
    response = solve_problem(INCLINE_WITH_V0)
    assert response.ok is True
    scene = response.visualization_scene
    assert scene is not None and scene.status == "unavailable"
    assert "초기속도" in scene.fallback_reason
    assert response.answer is not None


@pytest.mark.regression
def test_typed_down_slope_v0_is_used_verbatim():
    scene = _typed_scene("down_slope")
    motion = next(segment for segment in scene.motion if segment.id == "slide")
    axis = scene.axes[0].direction

    v_along = motion.velocity0.x * axis.x + motion.velocity0.y * axis.y
    a_along = motion.acceleration.x * axis.x + motion.acceleration.y * axis.y
    assert v_along == pytest.approx(5.0, rel=1e-9)
    assert a_along > 0.0
    assert not any("초기속도가 주어지지 않아" in item for item in scene.assumptions)
    assert any("경사면 아래쪽" in item for item in scene.assumptions)


@pytest.mark.regression
def test_typed_up_slope_v0_turns_before_moving_down_slope():
    scene = _typed_scene("up_slope")
    motion = next(segment for segment in scene.motion if segment.id == "slide")
    axis = scene.axes[0].direction

    v_along = motion.velocity0.x * axis.x + motion.velocity0.y * axis.y
    a_along = motion.acceleration.x * axis.x + motion.acceleration.y * axis.y
    assert v_along == pytest.approx(-5.0, rel=1e-9)
    assert a_along > 0.0

    turn_time = -v_along / a_along
    assert 0.0 < turn_time < motion.t_end
    assert v_along + a_along * motion.t_end > 0.0

    # The turnaround point and the final point stay within the camera bounds.
    for t in (0.0, turn_time, motion.t_end):
        dt = t - motion.t_start
        x = motion.position0.x + motion.velocity0.x * dt + 0.5 * motion.acceleration.x * dt**2
        y = motion.position0.y + motion.velocity0.y * dt + 0.5 * motion.acceleration.y * dt**2
        assert scene.camera.min_x <= x <= scene.camera.max_x
        assert scene.camera.min_y <= y <= scene.camera.max_y


@pytest.mark.regression
def test_explicit_zero_v0_needs_no_direction_and_remains_ready():
    response = solve_problem(INCLINE_EXPLICIT_REST)
    assert response.ok is True
    scene = response.visualization_scene
    assert scene is not None and scene.status == "ready"
    motion = next(segment for segment in scene.motion if segment.id == "slide")
    assert math.hypot(motion.velocity0.x, motion.velocity0.y) == pytest.approx(0.0)
    assert any("v0 = 0" in item for item in scene.assumptions)
