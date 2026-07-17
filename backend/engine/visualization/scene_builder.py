"""Phase 54 VisualizationScene builder: post-gate, additive, fail-open.

Ordering contract: ``attach_visualization_scene`` runs only after
``apply_result_gate`` and the public explanation finalization, so the scene
is a projection of the finished response.  It writes exactly one field —
``response.visualization_scene`` — and swallows every builder error, so a
scene failure can never change or fail an existing /solve result.
"""

from __future__ import annotations

from app.schemas.visualization_scene import VisualizationSceneModel

from .scenes import collision, incline, mass_spring, pendulum, pure_rolling
from .scenes.common import SceneUnavailable, unavailable_scene

_SCENE_BUILDERS = {
    "incline_no_friction": incline.build,
    "incline_with_friction": incline.build,
    "spring_mass_vibration": mass_spring.build,
    "pure_rolling_energy": pure_rolling.build,
    "collision_1d": collision.build,
}

# Documented deferrals: kept out of _SCENE_BUILDERS on purpose.  A pendulum
# solver does not exist in the product registry today; if one ever appears
# under this name the scene stays an explicit deferred fallback instead of
# silently animating unaudited physics.
_DEFERRED_BUILDERS = {
    "simple_pendulum": pendulum.build,
}

UNSUPPORTED_REASON = "이 문제 유형은 아직 동작 시각화를 지원하지 않습니다. 답과 풀이는 위 카드에서 그대로 확인할 수 있습니다."


def build_visualization_scene(
    response,
    *,
    canonical,
    physical_model,
    selected_solver: str | None,
) -> VisualizationSceneModel | None:
    """Project a finalized ok-response into a scene; never mutate anything."""

    if response.ok is not True or selected_solver is None:
        return None
    builder = _SCENE_BUILDERS.get(selected_solver)
    if builder is None:
        builder = _DEFERRED_BUILDERS.get(selected_solver)
        if builder is None:
            return unavailable_scene(UNSUPPORTED_REASON, source_solver=selected_solver)
    try:
        return builder(response, canonical, physical_model, selected_solver)
    except SceneUnavailable as exc:
        return unavailable_scene(exc.reason, scene_type=exc.scene_type, source_solver=selected_solver)


def attach_visualization_scene(
    response,
    *,
    canonical,
    physical_model,
    selected_solver: str | None,
) -> None:
    """Fail-open attachment: only ever assigns response.visualization_scene."""

    try:
        response.visualization_scene = build_visualization_scene(
            response,
            canonical=canonical,
            physical_model=physical_model,
            selected_solver=selected_solver,
        )
    except Exception:
        # A malformed scene or an unexpected builder bug must never surface
        # into the solve result.  Prefer an explicit unavailable scene; if
        # even that fails, leave the additive field empty.
        try:
            response.visualization_scene = unavailable_scene(
                "시각화 장면 생성에 실패했습니다. 답과 풀이에는 영향이 없습니다.",
                source_solver=selected_solver,
            )
        except Exception:
            response.visualization_scene = None
