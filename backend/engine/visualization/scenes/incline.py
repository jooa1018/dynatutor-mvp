"""Incline block scene: incline_no_friction / incline_with_friction (kinetic).

Motion is a closed-form playback of the post-gate backend acceleration.
The friction case is supported only on the unambiguous kinetic branch that
the solver itself certifies (friction_type == "kinetic", down-slope motion,
non-negative acceleration); every other branch reports unavailable.
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

_BLOCK_HALF_W = 0.42
_BLOCK_HALF_H = 0.26
_REST_TAIL_S = 0.8


def build(response, canonical, physical_model, selected_solver: str) -> VisualizationSceneModel:
    answers = answers_by_output_key(response)
    acc_item = answers.get("acceleration")
    if acc_item is None and response.answer is not None and getattr(response.answer, "output_key", None) == "acceleration":
        acc_item = response.answer
    if acc_item is None:
        raise SceneUnavailable("backend 가속도 답이 없어 경사면 장면을 만들 수 없습니다.", "incline_block")
    a = answer_numeric(acc_item)
    if a is None:
        raise SceneUnavailable("backend 가속도 답이 수치가 아닙니다.", "incline_block")

    theta_deg = known_value(canonical, "theta", units=("deg",))
    if theta_deg is None or not (0.0 < theta_deg < 90.0):
        raise SceneUnavailable("경사각 θ가 도 단위 수치로 확정되지 않았습니다.", "incline_block")

    with_friction = selected_solver == "incline_with_friction"
    direction_assumed = False
    if with_friction:
        # Clear kinetic branch only: friction_type == "kinetic" is set from an
        # explicit 운동마찰 statement, unlike "unspecified" (bare μ) or
        # "static".  Contrary typed direction evidence rejects the scene.
        if canonical.friction_type != "kinetic":
            raise SceneUnavailable(
                "운동마찰(kinetic) branch가 typed 근거로 확정되지 않아 시각화하지 않습니다.",
                "incline_block",
            )
        if canonical.displacement_direction not in (None, "down_slope"):
            raise SceneUnavailable(
                "경사면 아래 방향 운동이 아닌 것으로 표시된 문제여서 시각화하지 않습니다.",
                "incline_block",
            )
        direction_assumed = canonical.displacement_direction is None
    if a <= 1e-9:
        raise SceneUnavailable(
            "가속도가 0 이하로 계산되어 '아래로 미끄러지는 블록' 장면으로 표시하지 않습니다.",
            "incline_block",
        )

    theta = math.radians(theta_deg)
    # Down-slope unit vector (slope descends to the right) and outward normal.
    u = (math.cos(theta), -math.sin(theta))
    n = (math.sin(theta), math.cos(theta))

    # Slide length is a render-scale choice; the acceleration is the backend
    # value, so only the travelled distance/duration are schematic.
    slide_len = clamp(0.5 * a * 3.0**2, 2.0, 10.0)
    slide_time = math.sqrt(2.0 * slide_len / a)
    if slide_time > 8.0:
        slide_time = 8.0
        slide_len = 0.5 * a * slide_time**2

    margin = 0.6
    slope_len = slide_len + 2.0 * margin
    base = slope_len * math.cos(theta)
    height = slope_len * math.sin(theta)
    top = (0.0, height)

    def on_slope(s: float) -> tuple[float, float]:
        return (top[0] + u[0] * s, top[1] + u[1] * s)

    start_surface = on_slope(margin)
    start_center = (
        start_surface[0] + n[0] * _BLOCK_HALF_H,
        start_surface[1] + n[1] * _BLOCK_HALF_H,
    )

    bodies = [
        VizBodyModel(
            id="incline",
            label=f"경사면 (θ = {theta_deg:g}°)",
            role="incline_surface",
            shape=VizShapeModel(kind="wedge", angle_deg=theta_deg, base_length=base),
            body_type="fixed",
            initial_position=VizVec2(x=0.0, y=0.0),
            schematic_size=True,
        ),
        VizBodyModel(
            id="block",
            label="블록",
            role="block",
            shape=VizShapeModel(kind="rect", half_width=_BLOCK_HALF_W, half_height=_BLOCK_HALF_H),
            body_type="kinematic",
            initial_position=VizVec2(x=start_center[0], y=start_center[1]),
            initial_angle=-theta,
            schematic_size=True,
        ),
    ]

    motion = [
        VizMotionSegmentModel(
            id="slide",
            body_id="block",
            kind="uniform_acceleration",
            t_start=0.0,
            t_end=slide_time,
            position0=VizVec2(x=start_center[0], y=start_center[1]),
            velocity0=VizVec2(x=0.0, y=0.0),
            acceleration=VizVec2(x=a * u[0], y=a * u[1]),
        ),
        VizMotionSegmentModel(
            id="settle",
            body_id="block",
            kind="rest",
            t_start=slide_time,
            t_end=slide_time + _REST_TAIL_S,
            position0=VizVec2(
                x=start_center[0] + u[0] * slide_len,
                y=start_center[1] + u[1] * slide_len,
            ),
        ),
    ]

    forces = [
        VizForceModel(
            id="weight",
            body_id="block",
            kind="weight",
            label="중력",
            symbol="mg",
            direction=VizVec2(x=0.0, y=-1.0),
            magnitude_display="mg",
        ),
        VizForceModel(
            id="normal",
            body_id="block",
            kind="normal",
            label="수직항력",
            symbol="N",
            direction=VizVec2(x=n[0], y=n[1]),
            magnitude_display="N = mg·cosθ",
        ),
    ]
    constraints = [
        VizConstraintModel(kind="contact", description="블록은 경사면 위를 따라서만 움직입니다."),
    ]
    assumptions = [
        "질점(입자) 모델로 단순화한 블록입니다.",
        "시각화는 블록이 t=0에 정지 상태에서 출발한다고 가정합니다.",
    ]
    if with_friction:
        forces.append(
            VizForceModel(
                id="friction",
                body_id="block",
                kind="friction",
                label="운동마찰력 (운동 반대 방향)",
                symbol="f",
                direction=VizVec2(x=-u[0], y=-u[1]),
                magnitude_display="f = μN",
            )
        )
        constraints.append(
            VizConstraintModel(kind="kinetic_friction", description="운동마찰 f = μN이 운동 반대 방향으로 작용합니다.")
        )
        assumptions.append("운동마찰 계수 μ가 일정하다고 가정합니다.")
        if direction_assumed:
            assumptions.append(
                "운동 방향(경사면 아래쪽)은 solver 모델의 가정을 따릅니다. 문제에 방향이 명시되면 더 확실해집니다."
            )
    else:
        assumptions.append("마찰이 없는 경사면입니다.")

    cam_pad = 1.0
    camera = VizCameraModel(
        min_x=-cam_pad,
        min_y=-cam_pad,
        max_x=base + cam_pad,
        max_y=height + cam_pad + 0.8,
    )

    axis_origin = on_slope(margin * 0.4)
    scene_label = "경사면 블록" + (" (운동마찰)" if with_friction else " (마찰 없음)")
    acc_display = getattr(acc_item, "display", "") or ""
    return VisualizationSceneModel(
        schema=VISUALIZATION_SCENE_SCHEMA,
        version=VISUALIZATION_SCENE_VERSION,
        status="ready",
        scene_type="incline_block",
        scene_label=scene_label,
        source_solver=selected_solver,
        coordinate_frame=scene_coordinate_frame(response, physical_model),
        bodies=bodies,
        motion=motion,
        forces=forces,
        constraints=constraints,
        axes=[
            VizAxisModel(
                kind="positive_x",
                origin=VizVec2(x=axis_origin[0] + n[0] * 0.9, y=axis_origin[1] + n[1] * 0.9),
                direction=VizVec2(x=u[0], y=u[1]),
                label="+x: 경사면 아래쪽(양의 방향)",
            )
        ],
        events=[],
        camera=camera,
        timestep=VizTimestepModel(fixed_dt=FIXED_DT, duration=slide_time + _REST_TAIL_S, loop=False),
        answer_overlay=[overlay_item(acc_item)],
        scene_description=(
            f"경사각 {theta_deg:g}도 경사면 위 블록이 backend가 계산한 가속도 {acc_display}로 "
            "경사면 아래(+x) 방향으로 미끄러지는 장면입니다."
        ),
        assumptions=assumptions,
        warnings=[],
        schematic_notes=[
            "경사면 길이·블록 크기·이동 거리는 화면 표시용 값이며 문제의 물리량이 아닙니다.",
            "힘 화살표 길이는 개형(스케일 없음)입니다.",
        ],
    )
