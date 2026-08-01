"""One reading of a stated support orientation, shared by the planner and the closure.

The B15 revocation established what a stated horizontal support is *not*: a
support-owned angle of exactly zero fixes no reference — it is equally
consistent with a plane level to the world horizontal, a plane measured from the
vertical, and a plane measured from some second surface — and an entity label
reading "table" or "floor" is not physics authority.  What it *is* was already
written, in `complete_profile_application`: the source itself authored a support
frame, anchored on the support entity and parented to a world frame, whose
tangent binds to that world frame's x axis and whose normal binds to its y.

That reading lived in the closure alone, so the planner had a second, narrower
rule — the numeric zero — and a source that stated its orientation as a frame
was refused by the plan before the closure could read it.  Two rules for one
question is how a contract drifts: the planner would report a profile
incomplete while the closure stood ready to build it.

So the reading moves here, once, and both import it.  There is deliberately no
"planner variant" and no fallback: a support whose orientation the source never
stated is still refused, exactly as the B15 revocation left it.
"""

from __future__ import annotations

from typing import Any, Mapping


TYPED_SUPPORT_FRAME_VERSION = "phase56-stage7-typed-support-frame-v1"


def world_axis_direction(binding: Any, frame_id: str, axis: str) -> bool:
    """True when one axis binding names ``frame_id``'s ``axis`` in the + sense."""

    return (
        isinstance(binding, Mapping)
        and binding.get("kind") == "axis"
        and binding.get("frame_id") == frame_id
        and binding.get("axis") == axis
        and binding.get("sign") == 1
    )


def axis_bindings(frame: Mapping[str, Any]) -> dict[str, Any]:
    """One frame's axis name -> direction binding, or ``{}`` if malformed."""

    axes = frame.get("axes")
    if not isinstance(axes, list) or len(axes) != 2:
        return {}
    bindings = {
        item.get("axis"): item.get("direction")
        for item in axes
        if isinstance(item, Mapping)
    }
    return bindings if len(bindings) == 2 else {}


def frame_is_plain(frame: Mapping[str, Any]) -> bool:
    """True for a static frame carrying no translation, rotation, or coordinate."""

    return (
        frame.get("frame_type") == "cartesian_2d"
        and frame.get("translating_with_entity_id") is None
        and frame.get("rotating_about_point_id") is None
        and not frame.get("generalized_coordinate_symbol_ids")
        and bool(frame.get("evidence_refs"))
    )


def stated_support_orientation(
    payload: Mapping[str, Any], *, support_id: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """The source's own binding of a support's tangent to the world horizontal.

    ``ReferenceFrame.axes[].direction`` is the only place in this contract
    where an axis identity is typed: ``GeometryRelation`` carries no axis and
    ``SemanticDirectionName`` carries no surface-relative member.  So a stated
    support orientation means exactly one thing, and this admits only it.

    No label, sentence, primitive, entity kind, or missing field is read
    anywhere.  Absence returns ``None``: silence is never a stated reference.
    """

    frames = payload.get("reference_frames")
    if not isinstance(frames, list) or len(frames) != 2:
        return None
    world_frames = [
        item
        for item in frames
        if isinstance(item, Mapping)
        and isinstance(item.get("origin"), Mapping)
        and item["origin"].get("kind") == "world"
    ]
    if len(world_frames) != 1:
        return None
    world = world_frames[0]
    support = next(item for item in frames if item is not world)
    if not isinstance(support, Mapping):
        return None
    world_id = world.get("frame_id")
    world_axes = axis_bindings(world)
    support_axes = axis_bindings(support)
    if (
        type(world_id) is not str
        or not frame_is_plain(world)
        or world.get("parent_frame_id") is not None
        or not world_axis_direction(world_axes.get("x"), world_id, "x")
        or not world_axis_direction(world_axes.get("y"), world_id, "y")
        # The support frame is what states the orientation: its tangent is
        # the world horizontal and its normal the world vertical.  A tangent
        # bound to y would state a vertical support, and a binding into any
        # frame other than this world frame states an orientation relative to
        # something whose own orientation is unstated.
        or not frame_is_plain(support)
        or not isinstance(support.get("origin"), Mapping)
        or support["origin"].get("kind") != "entity"
        or support["origin"].get("entity_id") != support_id
        or support.get("parent_frame_id") != world_id
        or not world_axis_direction(support_axes.get("tangent"), world_id, "x")
        or not world_axis_direction(support_axes.get("normal"), world_id, "y")
    ):
        return None
    return dict(world), dict(support)


def payload_states_horizontal_support(payload: Mapping[str, Any]) -> bool:
    """True when the payload's own frames state some surface's orientation.

    The planner asks the question without knowing which entity the closure
    will settle on, so it asks it of every surface the payload declares.  The
    closure then asks it again of the one entity it chose, and the two cannot
    disagree because it is the same function both times.
    """

    entities = payload.get("entities")
    if not isinstance(entities, list):
        return False
    for item in entities:
        if not isinstance(item, Mapping) or item.get("primitive") != "surface":
            continue
        support_id = item.get("entity_id")
        if type(support_id) is not str:
            continue
        if stated_support_orientation(payload, support_id=support_id) is not None:
            return True
    return False


__all__ = [
    "TYPED_SUPPORT_FRAME_VERSION",
    "axis_bindings",
    "frame_is_plain",
    "payload_states_horizontal_support",
    "stated_support_orientation",
    "world_axis_direction",
]
