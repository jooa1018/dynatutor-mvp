"""Simple pendulum scene: explicitly deferred in Phase 54.

There is no product pendulum solver, typed model, or answer contract in the
current registry/capability set, and Phase 50 offline pendulum validation
data is not a product solve.  Until a real product contract exists this
module only reports a deferred, unavailable scene.
"""

from __future__ import annotations

from app.schemas.visualization_scene import VisualizationSceneModel

from .common import unavailable_scene

DEFERRED_REASON = (
    "단진자는 아직 product solver/typed model/answer 계약이 없어 Phase 54에서 "
    "명시적으로 보류(deferred)되었습니다. 시각화는 product 풀이 경로가 생긴 뒤 추가됩니다."
)


def build(response, canonical, physical_model, selected_solver: str) -> VisualizationSceneModel:
    return unavailable_scene(DEFERRED_REASON, scene_type="pendulum", source_solver=selected_solver)
