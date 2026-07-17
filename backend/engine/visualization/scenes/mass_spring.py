"""Mass-spring scene: spring_mass_vibration.

Playback angular frequency comes from the delivered post-gate answer
(angular_frequency directly, or an exact 2π conversion from the delivered
period/frequency).  The amplitude is visualization-only unless an explicit
amplitude A was stated, and that distinction is carried in the DTO.
"""

from __future__ import annotations

import math

from app.schemas.visualization_scene import (
    VISUALIZATION_SCENE_SCHEMA,
    VISUALIZATION_SCENE_VERSION,
    VisualizationSceneModel,
    VizAxisModel,
    VizBodyModel,
    VizCameraModel,
    VizConstraintModel,
    VizForceModel,
    VizMotionSegmentModel,
    VizShapeModel,
    VizTimestepModel,
    VizVec2,
)

from .common import (
    FIXED_DT,
    SceneUnavailable,
    answer_numeric,
    answers_by_output_key,
    clamp,
    known_value,
    overlay_item,
    scene_coordinate_frame,
)

_MASS_HALF = 0.35
_SCHEMATIC_AMPLITUDE = 0.9
_WALL_X = -3.2
_GROUND_Y = 0.0


def build(response, canonical, physical_model, selected_solver: str) -> VisualizationSceneModel:
    answers = answers_by_output_key(response)
    overlay = []
    omega = None
    omega_note = None
    for key in ("angular_frequency", "period", "frequency"):
        item = answers.get(key)
        if item is None:
            continue
        overlay.append(overlay_item(item))
        value = answer_numeric(item)
        if omega is not None or value is None or value <= 0:
            continue
        if key == "angular_frequency":
            omega = value
        elif key == "period":
            omega = 2.0 * math.pi / value
            omega_note = "애니메이션 각진동수는 backend 주기 T에서 ω = 2π/T로 환산한 값입니다."
        else:
            omega = 2.0 * math.pi * value
            omega_note = "애니메이션 각진동수는 backend 진동수 f에서 ω = 2πf로 환산한 값입니다."
    if omega is None or not overlay:
        raise SceneUnavailable(
            "backend가 확정한 진동 답(각진동수/주기/진동수)이 없어 스프링 장면을 만들 수 없습니다.",
            "mass_spring",
        )

    amplitude = known_value(canonical, "A", units=("m",))
    amplitude_schematic = amplitude is None or amplitude <= 0
    if amplitude_schematic:
        amplitude_render = _SCHEMATIC_AMPLITUDE
    else:
        # Real amplitude drives phase truthfully, but keep the drawn extent
        # in a readable band by scaling the world, not the physics.
        amplitude_render = clamp(amplitude, 0.4, 1.6)

    period = 2.0 * math.pi / omega
    duration = clamp(2.0 * period, 2.0, 16.0)

    mass_y = _GROUND_Y + _MASS_HALF
    bodies = [
        VizBodyModel(
            id="wall",
            label="벽",
            role="wall",
            shape=VizShapeModel(kind="wall", half_width=0.18, half_height=1.2),
            body_type="fixed",
            initial_position=VizVec2(x=_WALL_X, y=_GROUND_Y + 1.0),
            schematic_size=True,
        ),
        VizBodyModel(
            id="ground",
            label="바닥",
            role="ground",
            shape=VizShapeModel(kind="ground_line", half_width=6.0),
            body_type="fixed",
            initial_position=VizVec2(x=0.0, y=_GROUND_Y),
            schematic_size=True,
        ),
        VizBodyModel(
            id="spring",
            label="스프링",
            role="spring",
            shape=VizShapeModel(kind="spring_coil", half_height=0.16, half_width=abs(_WALL_X)),
            body_type="fixed",
            initial_position=VizVec2(x=_WALL_X + 0.18, y=mass_y),
            schematic_size=True,
        ),
        VizBodyModel(
            id="equilibrium",
            label="평형 위치 (x = 0)",
            role="equilibrium_marker",
            shape=VizShapeModel(kind="wall", half_width=0.02, half_height=0.9),
            body_type="fixed",
            initial_position=VizVec2(x=0.0, y=_GROUND_Y + 0.7),
            schematic_size=True,
        ),
        VizBodyModel(
            id="mass",
            label="질량 m",
            role="block",
            shape=VizShapeModel(kind="rect", half_width=_MASS_HALF, half_height=_MASS_HALF),
            body_type="kinematic",
            initial_position=VizVec2(x=amplitude_render, y=mass_y),
            schematic_size=True,
        ),
    ]

    motion = [
        VizMotionSegmentModel(
            id="oscillate",
            body_id="mass",
            kind="oscillation",
            t_start=0.0,
            t_end=duration,
            origin=VizVec2(x=0.0, y=mass_y),
            axis=VizVec2(x=1.0, y=0.0),
            amplitude=amplitude_render,
            omega=omega,
            phase=0.0,
        )
    ]

    forces = [
        VizForceModel(
            id="restoring",
            body_id="mass",
            kind="spring_restoring",
            label="복원력 (항상 평형 위치 방향)",
            symbol="F",
            direction=None,
            behavior="restoring",
            magnitude_display="F = -kx",
        )
    ]

    schematic_notes = [
        "벽·바닥·스프링 길이와 질량 크기는 화면 표시용 값입니다.",
        "힘 화살표 길이는 개형(스케일 없음)입니다.",
    ]
    if amplitude_schematic:
        schematic_notes.insert(
            0,
            "진폭은 문제에 주어지지 않아 시각화 전용 값입니다. 공식 물리량이 아닙니다.",
        )
    if omega_note:
        schematic_notes.append(omega_note)

    camera = VizCameraModel(
        min_x=_WALL_X - 0.8,
        min_y=_GROUND_Y - 0.8,
        max_x=amplitude_render + 2.2,
        max_y=_GROUND_Y + 2.6,
    )

    return VisualizationSceneModel(
        schema=VISUALIZATION_SCENE_SCHEMA,
        version=VISUALIZATION_SCENE_VERSION,
        status="ready",
        scene_type="mass_spring",
        scene_label="질량-스프링 진동",
        source_solver=selected_solver,
        coordinate_frame=scene_coordinate_frame(response, physical_model),
        bodies=bodies,
        motion=motion,
        forces=forces,
        constraints=[
            VizConstraintModel(kind="linear_spring", description="훅 법칙 F = -kx를 따르는 이상 스프링입니다."),
        ],
        axes=[
            VizAxisModel(
                kind="positive_x",
                origin=VizVec2(x=0.0, y=_GROUND_Y + 1.9),
                direction=VizVec2(x=1.0, y=0.0),
                label="+x: 평형에서 늘어나는 방향(양의 방향)",
            )
        ],
        events=[],
        camera=camera,
        timestep=VizTimestepModel(fixed_dt=FIXED_DT, duration=duration, loop=True),
        answer_overlay=overlay,
        scene_description=(
            "벽에 연결된 스프링-질량계가 평형 위치를 중심으로 단순 조화 진동하는 장면입니다. "
            "진동의 빠르기는 backend가 계산한 답을 그대로 따릅니다."
        ),
        assumptions=[
            "감쇠와 외력이 없는 1자유도 진동입니다.",
            "시각화는 최대 변위에서 정지 상태로 놓아준 경우(x(0)=A)를 가정합니다.",
        ],
        warnings=[],
        schematic_notes=schematic_notes,
    )
