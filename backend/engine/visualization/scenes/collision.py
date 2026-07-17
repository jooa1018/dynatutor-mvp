"""1D collision scene: collision_1d.

The timeline is built entirely from backend values: typed pre-collision
knowns (m1, m2, v1, v2) and the post-gate delivered post-collision answers
(v1_after, v2_after, and the common velocity when perfectly inelastic).
Rapier never resolves the contact; the collision instant is a segment
boundary where velocities switch to the backend post values verbatim.
Only branches whose typed evidence is complete are supported.
"""

from __future__ import annotations

from app.schemas.visualization_scene import (
    VISUALIZATION_SCENE_SCHEMA,
    VISUALIZATION_SCENE_VERSION,
    VisualizationSceneModel,
    VizAxisModel,
    VizBodyModel,
    VizCameraModel,
    VizConstraintModel,
    VizEventMarkerModel,
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

_POST_DURATION_S = 2.2
_IMPULSE_WINDOW_S = 0.14


def _collision_branch(canonical) -> str:
    """Typed branch label; raises when no typed collision type exists."""

    flags = canonical.flags or {}
    if flags.get("perfectly_inelastic"):
        return "완전 비탄성 충돌 (한 덩어리로 이동)"
    if flags.get("elastic"):
        return "탄성 충돌 (e = 1)"
    e = known_value(canonical, "e")
    if e is not None:
        return f"반발계수 e = {e:g}인 충돌"
    raise SceneUnavailable(
        "충돌 유형(탄성/완전 비탄성/반발계수)이 typed 근거로 확정되지 않았습니다.",
        "collision_1d",
    )


def build(response, canonical, physical_model, selected_solver: str) -> VisualizationSceneModel:
    branch_label = _collision_branch(canonical)

    m1 = known_value(canonical, "m1", units=("kg",))
    m2 = known_value(canonical, "m2", units=("kg",))
    v1 = known_value(canonical, "v1", units=("m/s",))
    v2 = known_value(canonical, "v2", units=("m/s",))
    if m1 is None or m2 is None or m1 <= 0 or m2 <= 0:
        raise SceneUnavailable("두 질량이 kg 단위 수치로 확정되지 않았습니다.", "collision_1d")
    if v1 is None or v2 is None:
        raise SceneUnavailable("충돌 전 속도 v1, v2가 typed 값으로 확정되지 않았습니다.", "collision_1d")
    if v1 <= v2:
        raise SceneUnavailable("두 물체가 서로 다가가는 조건(v1 > v2)이 아니어서 시각화하지 않습니다.", "collision_1d")

    answers = answers_by_output_key(response)
    v1_after_item = answers.get("v1_after")
    v2_after_item = answers.get("v2_after")
    v1_after = answer_numeric(v1_after_item) if v1_after_item is not None else None
    v2_after = answer_numeric(v2_after_item) if v2_after_item is not None else None
    if v1_after is None or v2_after is None:
        raise SceneUnavailable("backend 충돌 후 속도(v1', v2')가 없어 timeline을 만들 수 없습니다.", "collision_1d")

    overlay = [overlay_item(v1_after_item), overlay_item(v2_after_item)]
    common_item = answers.get("post_collision_velocity")
    if common_item is not None:
        overlay.insert(0, overlay_item(common_item))

    # Schematic sizes: readable boxes whose relative size hints at mass.
    m_min = min(m1, m2)
    half_w1 = clamp(0.38 * (m1 / m_min) ** (1.0 / 3.0), 0.3, 0.75)
    half_w2 = clamp(0.38 * (m2 / m_min) ** (1.0 / 3.0), 0.3, 0.75)
    half_h = 0.35

    closing_speed = v1 - v2
    gap = clamp(closing_speed * 2.0, 1.2, 8.0)
    t_c = gap / closing_speed
    duration = t_c + _POST_DURATION_S

    # Contact happens at x = 0 exactly at t_c.
    x1_0 = -half_w1 - v1 * t_c
    x2_0 = half_w2 - v2 * t_c
    y = half_h

    # Camera covers every segment endpoint of both bodies (positions are
    # piecewise linear, so extremes occur at t=0, the collision, or the end),
    # keeping the contact point and the full post-collision travel on screen
    # for any velocity signs.
    x1_c = x1_0 + v1 * t_c
    x2_c = x2_0 + v2 * t_c
    x1_end = x1_c + v1_after * _POST_DURATION_S
    x2_end = x2_c + v2_after * _POST_DURATION_S
    x_min = min(x1_0 - half_w1, x1_c - half_w1, x1_end - half_w1,
                x2_0 - half_w2, x2_c - half_w2, x2_end - half_w2)
    x_max = max(x1_0 + half_w1, x1_c + half_w1, x1_end + half_w1,
                x2_0 + half_w2, x2_c + half_w2, x2_end + half_w2)
    ground_center = (x_min + x_max) / 2.0
    ground_half = (x_max - x_min) / 2.0 + 2.0

    def _segments(body_id: str, x0: float, v_pre: float, v_post: float) -> list[VizMotionSegmentModel]:
        x_c = x0 + v_pre * t_c
        return [
            VizMotionSegmentModel(
                id=f"{body_id}-before",
                body_id=body_id,
                kind="uniform_acceleration",
                t_start=0.0,
                t_end=t_c,
                position0=VizVec2(x=x0, y=y),
                velocity0=VizVec2(x=v_pre, y=0.0),
                acceleration=VizVec2(x=0.0, y=0.0),
            ),
            VizMotionSegmentModel(
                id=f"{body_id}-after",
                body_id=body_id,
                kind="uniform_acceleration",
                t_start=t_c,
                t_end=duration,
                position0=VizVec2(x=x_c, y=y),
                velocity0=VizVec2(x=v_post, y=0.0),
                acceleration=VizVec2(x=0.0, y=0.0),
            ),
        ]

    bodies = [
        VizBodyModel(
            id="ground",
            label="바닥",
            role="ground",
            shape=VizShapeModel(kind="ground_line", half_width=ground_half),
            body_type="fixed",
            initial_position=VizVec2(x=ground_center, y=0.0),
            schematic_size=True,
        ),
        VizBodyModel(
            id="body1",
            label=f"물체 1 (m₁ = {m1:g} kg)",
            role="cart",
            shape=VizShapeModel(kind="rect", half_width=half_w1, half_height=half_h),
            body_type="kinematic",
            initial_position=VizVec2(x=x1_0, y=y),
            schematic_size=True,
        ),
        VizBodyModel(
            id="body2",
            label=f"물체 2 (m₂ = {m2:g} kg)",
            role="cart",
            shape=VizShapeModel(kind="rect", half_width=half_w2, half_height=half_h),
            body_type="kinematic",
            initial_position=VizVec2(x=x2_0, y=y),
            schematic_size=True,
        ),
    ]

    motion = _segments("body1", x1_0, v1, v1_after) + _segments("body2", x2_0, v2, v2_after)

    forces = [
        VizForceModel(
            id="impulse1",
            body_id="body1",
            kind="impulse",
            label="충격량 (물체 2가 물체 1에)",
            symbol="J",
            direction=VizVec2(x=-1.0, y=0.0),
            magnitude_display="J",
            visible_t_start=max(0.0, t_c - _IMPULSE_WINDOW_S),
            visible_t_end=t_c + _IMPULSE_WINDOW_S,
        ),
        VizForceModel(
            id="impulse2",
            body_id="body2",
            kind="impulse",
            label="충격량 (물체 1이 물체 2에)",
            symbol="J",
            direction=VizVec2(x=1.0, y=0.0),
            magnitude_display="J",
            visible_t_start=max(0.0, t_c - _IMPULSE_WINDOW_S),
            visible_t_end=t_c + _IMPULSE_WINDOW_S,
        ),
    ]

    camera = VizCameraModel(
        min_x=x_min - 1.0,
        min_y=-1.2,
        max_x=x_max + 1.0,
        max_y=2.6,
    )

    return VisualizationSceneModel(
        schema=VISUALIZATION_SCENE_SCHEMA,
        version=VISUALIZATION_SCENE_VERSION,
        status="ready",
        scene_type="collision_1d",
        scene_label=f"1차원 충돌 — {branch_label}",
        source_solver=selected_solver,
        coordinate_frame=scene_coordinate_frame(response, physical_model),
        bodies=bodies,
        motion=motion,
        forces=forces,
        constraints=[
            VizConstraintModel(kind="linear_momentum", description="운동량 보존: m₁v₁ + m₂v₂ = m₁v₁' + m₂v₂'"),
            VizConstraintModel(kind="collision_branch", description=branch_label),
        ],
        axes=[
            VizAxisModel(
                kind="positive_x",
                origin=VizVec2(x=x_min + 0.4, y=1.9),
                direction=VizVec2(x=1.0, y=0.0),
                label="+x: 문제에서 정한 양의 방향(오른쪽)",
            )
        ],
        events=[VizEventMarkerModel(t=t_c, kind="collision", label="충돌")],
        camera=camera,
        timestep=VizTimestepModel(fixed_dt=FIXED_DT, duration=duration, loop=False),
        answer_overlay=overlay,
        scene_description=(
            f"물체 1(v₁ = {v1:g} m/s)과 물체 2(v₂ = {v2:g} m/s)가 한 직선 위에서 다가와 충돌하고, "
            "충돌 후에는 backend가 계산한 속도로 움직이는 장면입니다. 충돌 전 속도는 문제의 조건이며 "
            "충돌 후 속도는 backend 답입니다."
        ),
        assumptions=[
            "1차원 정면 충돌이며 외부 충격량은 무시합니다.",
            "충돌 지속 시간은 표시를 위해 순간으로 그립니다.",
        ],
        warnings=[],
        schematic_notes=[
            "물체 크기·초기 간격·충돌 위치는 화면 표시용 값입니다.",
            "충돌 순간의 상세 접촉/변형 과정은 표시하지 않습니다.",
        ],
    )
