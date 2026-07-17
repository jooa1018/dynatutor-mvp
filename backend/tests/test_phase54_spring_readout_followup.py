"""Regression coverage for the Phase 54 spring visualization follow-up."""

import math

import pytest
from pydantic import ValidationError

from app.schemas.visualization_scene import VisualizationSceneModel
from engine.services import solve_problem
from engine.visualization.scenes.mass_spring import _playback_timing


SPRING_PERIOD = "k=200 N/m 스프링에 질량 2 kg을 달았다. 주기를 구하라."
SPRING_WITH_AMPLITUDE = (
    "k=200 N/m 스프링에 질량 2 kg을 달아 진폭 0.05 m로 진동시킨다. 주기를 구하라."
)


def _spring_scene(text: str):
    response = solve_problem(text)
    assert response.ok is True
    scene = response.visualization_scene
    assert scene is not None and scene.status == "ready"
    assert scene.scene_type == "mass_spring"
    return response, scene


@pytest.mark.regression
def test_schematic_spring_hides_numeric_motion_readout():
    _, scene = _spring_scene(SPRING_PERIOD)
    assert scene.motion_readout_mode == "direction_only"
    assert any("진폭은 문제에 주어지지 않아" in note for note in scene.schematic_notes)

    payload = scene.model_dump()
    payload["motion_readout_mode"] = "invented_numeric_scale"
    with pytest.raises(ValidationError):
        VisualizationSceneModel(**payload)


@pytest.mark.regression
def test_explicit_spring_amplitude_keeps_numeric_motion_readout():
    _, scene = _spring_scene(SPRING_WITH_AMPLITUDE)
    assert scene.motion_readout_mode == "numeric"
    oscillation = next(segment for segment in scene.motion if segment.kind == "oscillation")
    assert oscillation.amplitude == pytest.approx(0.05, abs=1e-12)


@pytest.mark.regression
def test_spring_loop_boundary_returns_to_the_same_phase():
    _, scene = _spring_scene(SPRING_PERIOD)
    oscillation = next(segment for segment in scene.motion if segment.kind == "oscillation")

    assert scene.timestep.loop is True
    assert oscillation.t_end == pytest.approx(scene.timestep.duration, abs=1e-12)

    period = 2.0 * math.pi / oscillation.omega
    cycle_count = scene.timestep.duration / period
    assert cycle_count == pytest.approx(round(cycle_count), abs=1e-10)

    phase_end = oscillation.omega * scene.timestep.duration + (oscillation.phase or 0.0)
    x_start = oscillation.amplitude * math.cos(oscillation.phase or 0.0)
    x_end = oscillation.amplitude * math.cos(phase_end)
    v_end = -oscillation.amplitude * oscillation.omega * math.sin(phase_end)
    assert x_end == pytest.approx(x_start, abs=1e-10)
    assert v_end == pytest.approx(0.0, abs=1e-10)


@pytest.mark.unit
def test_spring_playback_disables_loop_when_one_period_exceeds_budget():
    duration, loop = _playback_timing(20.0)
    assert duration == pytest.approx(16.0)
    assert loop is False
