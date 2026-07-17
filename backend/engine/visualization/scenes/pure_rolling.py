"""Pure rolling scene: pure_rolling_energy.

The playback endpoints are the backend values: start speed from typed knowns
(v0 or explicit rest) and final speed from the post-gate final_velocity
answer.  The animation acceleration is derived only so those endpoints meet
over the drawn slope, and is labeled as visualization-only.  Without a real
radius, the drawn wheel radius is render scale and the displayed spin is
schematic — it is never presented as a physical angular velocity.
"""

from __future__ import annotations

import math

from engine.physics_core.initial_conditions import explicitly_starts_from_rest

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

_SCHEMATIC_THETA_DEG = 30.0
_SCHEMATIC_RADIUS = 0.38
_REST_TAIL_S = 0.8

_SHAPE_LABELS = {
    "solid_sphere": "속이 찬 구",
    "hollow_sphere": "속이 빈 구",
    "solid_cylinder": "속이 찬 원기둥",
    "disk": "원판",
    "hoop": "고리",
    "ring": "고리",
}


def build(response, canonical, physical_model, selected_solver: str) -> VisualizationSceneModel:
    answers = answers_by_output_key(response)
    vf_item = answers.get("final_velocity")
    if vf_item is None:
        raise SceneUnavailable("backend 최종 속도 답이 없어 구름 장면을 만들 수 없습니다.", "pure_rolling")
    v_final = answer_numeric(vf_item)
    if v_final is None or v_final <= 0:
        raise SceneUnavailable("backend 최종 속도 답이 양의 수치가 아닙니다.", "pure_rolling")

    h = known_value(canonical, "h", units=("m",))
    if h is None and canonical.launch_height is not None:
        h = float(canonical.launch_height)
    if h is None or h <= 0:
        raise SceneUnavailable("낙하 높이 h가 typed 값으로 확정되지 않았습니다.", "pure_rolling")

    v0 = known_value(canonical, "v0", units=("m/s",))
    if v0 is None:
        # Same explicit-rest rule the solver/verification path uses
        # (physics_core.initial_conditions) — reused, not reinterpreted.
        if (canonical.flags or {}).get("starts_from_rest") or explicitly_starts_from_rest(canonical):
            v0 = 0.0
        else:
            raise SceneUnavailable(
                "초기 조건(정지 출발 또는 초기 속도)이 typed 근거로 확정되지 않았습니다.",
                "pure_rolling",
            )
    if v0 < 0 or v_final <= v0:
        raise SceneUnavailable("초기/최종 속도 관계가 아래로 구르는 장면과 맞지 않습니다.", "pure_rolling")

    theta_deg = known_value(canonical, "theta", units=("deg",))
    theta_schematic = theta_deg is None or not (0.0 < theta_deg < 90.0)
    if theta_schematic:
        theta_deg = _SCHEMATIC_THETA_DEG
    theta = math.radians(theta_deg)

    radius = known_value(canonical, "R", units=("m",))
    if radius is None:
        radius = known_value(canonical, "r", units=("m",))
    radius_stated = radius is not None and radius > 0
    if radius_stated:
        render_radius = clamp(radius, 0.2, 0.8)
    else:
        render_radius = _SCHEMATIC_RADIUS
    # A stated radius outside the readable band is drawn clamped, so the
    # on-screen spin becomes display-only in that case too.
    radius_schematic = (not radius_stated) or render_radius != radius

    # Real drop height fixes the slope; animation acceleration is chosen so the
    # backend start/final speeds meet exactly at the bottom of that slope.
    slope_len = h / math.sin(theta)
    a_anim = (v_final**2 - v0**2) / (2.0 * slope_len)
    roll_time = (v_final - v0) / a_anim
    if roll_time > 20.0:
        raise SceneUnavailable("구름 시간이 지나치게 길어 애니메이션으로 표시하지 않습니다.", "pure_rolling")

    u = (math.cos(theta), -math.sin(theta))
    n = (math.sin(theta), math.cos(theta))
    margin = 0.5
    total_slope = slope_len + 2.0 * margin
    base = total_slope * math.cos(theta)
    height = total_slope * math.sin(theta)
    top = (0.0, height)

    def on_slope(s: float) -> tuple[float, float]:
        return (top[0] + u[0] * s, top[1] + u[1] * s)

    start_surface = on_slope(margin)
    start_center = (
        start_surface[0] + n[0] * render_radius,
        start_surface[1] + n[1] * render_radius,
    )
    end_center = (
        start_center[0] + u[0] * slope_len,
        start_center[1] + u[1] * slope_len,
    )

    shape_key = canonical.body_shape or ""
    shape_label = _SHAPE_LABELS.get(shape_key, "구르는 물체")

    bodies = [
        VizBodyModel(
            id="incline",
            label=f"경사면 (θ = {theta_deg:g}°{', 표시용 각도' if theta_schematic else ''})",
            role="incline_surface",
            shape=VizShapeModel(kind="wedge", angle_deg=theta_deg, base_length=base),
            body_type="fixed",
            initial_position=VizVec2(x=0.0, y=0.0),
            schematic_size=True,
        ),
        VizBodyModel(
            id="roller",
            label=shape_label,
            role="wheel",
            shape=VizShapeModel(kind="circle", radius=render_radius),
            body_type="kinematic",
            initial_position=VizVec2(x=start_center[0], y=start_center[1]),
            schematic_size=radius_schematic,
        ),
    ]

    # Rolling to the down-slope right means clockwise spin (negative in the
    # CCW-positive world).  With a schematic radius the spin rate is display
    # geometry only; angular_schematic marks it so the UI never quotes it.
    motion = [
        VizMotionSegmentModel(
            id="roll",
            body_id="roller",
            kind="uniform_acceleration",
            t_start=0.0,
            t_end=roll_time,
            position0=VizVec2(x=start_center[0], y=start_center[1]),
            velocity0=VizVec2(x=v0 * u[0], y=v0 * u[1]),
            acceleration=VizVec2(x=a_anim * u[0], y=a_anim * u[1]),
            angle0=0.0,
            angular_velocity0=-v0 / render_radius,
            angular_acceleration=-a_anim / render_radius,
            angular_schematic=radius_schematic,
        ),
        VizMotionSegmentModel(
            id="settle",
            body_id="roller",
            kind="rest",
            t_start=roll_time,
            t_end=roll_time + _REST_TAIL_S,
            position0=VizVec2(x=end_center[0], y=end_center[1]),
        ),
    ]

    forces = [
        VizForceModel(
            id="weight",
            body_id="roller",
            kind="weight",
            label="중력",
            symbol="mg",
            direction=VizVec2(x=0.0, y=-1.0),
            magnitude_display="mg",
        ),
        VizForceModel(
            id="normal",
            body_id="roller",
            kind="normal",
            label="수직항력",
            symbol="N",
            direction=VizVec2(x=n[0], y=n[1]),
            magnitude_display="N",
        ),
        VizForceModel(
            id="static_friction",
            body_id="roller",
            kind="friction",
            label="정지마찰력 (순수 구름 유지, 일 안 함)",
            symbol="f_s",
            direction=VizVec2(x=-u[0], y=-u[1]),
            magnitude_display="f_s",
        ),
    ]

    overlay = [overlay_item(vf_item)]
    omega_item = answers.get("angular_velocity")
    if omega_item is not None:
        overlay.append(overlay_item(omega_item))

    schematic_notes = [
        "애니메이션 가속도는 backend 최종 속도와 경사면 표시 길이에 맞춘 시각화 전용 값입니다.",
        "힘 화살표 길이는 개형(스케일 없음)입니다.",
    ]
    if radius_schematic:
        schematic_notes.insert(
            0,
            (
                "반지름이 화면 표시 범위를 벗어나 표시용 크기로 그립니다. 회전 빠르기도 표시용이며 물리적 각속도가 아닙니다."
                if radius_stated
                else "반지름이 주어지지 않아 바퀴 크기와 회전 빠르기는 화면 표시용입니다. 물리적 각속도로 읽지 마세요."
            ),
        )
    if theta_schematic:
        schematic_notes.append("경사각은 표시용 값이며, 낙하 높이 h만 문제의 값입니다.")

    cam_pad = 1.0
    camera = VizCameraModel(
        min_x=-cam_pad,
        min_y=-cam_pad,
        max_x=base + cam_pad,
        max_y=height + cam_pad + 0.8,
    )

    axis_origin = on_slope(margin * 0.4)
    return VisualizationSceneModel(
        schema=VISUALIZATION_SCENE_SCHEMA,
        version=VISUALIZATION_SCENE_VERSION,
        status="ready",
        scene_type="pure_rolling",
        scene_label=f"순수 구름 ({shape_label})",
        source_solver=selected_solver,
        coordinate_frame=scene_coordinate_frame(response, physical_model),
        bodies=bodies,
        motion=motion,
        forces=forces,
        constraints=[
            VizConstraintModel(kind="no_slip", description="미끄러짐 없음: v = ωR (접촉점 속도 0)"),
            VizConstraintModel(kind="contact", description="물체는 경사면과 접촉을 유지합니다."),
        ],
        axes=[
            VizAxisModel(
                kind="positive_x",
                origin=VizVec2(x=axis_origin[0] + n[0] * (render_radius + 0.7), y=axis_origin[1] + n[1] * (render_radius + 0.7)),
                direction=VizVec2(x=u[0], y=u[1]),
                label="+x: 구름 진행 방향(경사면 아래쪽)",
            )
        ],
        events=[],
        camera=camera,
        timestep=VizTimestepModel(fixed_dt=FIXED_DT, duration=roll_time + _REST_TAIL_S, loop=False),
        answer_overlay=overlay,
        scene_description=(
            f"높이 {h:g} m를 내려오며 미끄러지지 않고 구르는 {shape_label}의 장면입니다. "
            "바닥에 도달할 때의 속도는 backend가 계산한 답과 일치하도록 재생됩니다."
        ),
        assumptions=[
            "순수 구름(미끄러짐 없음)을 유지합니다.",
            "정지마찰은 일을 하지 않으므로 역학적 에너지가 보존됩니다.",
        ],
        warnings=[],
        schematic_notes=schematic_notes,
    )
