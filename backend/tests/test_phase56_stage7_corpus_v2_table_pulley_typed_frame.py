"""B30: the table-pulley cohort closes from a stated frame, and from nothing else.

The B15 revocation was right about what a generic `surface` primitive proves —
nothing — and right that a support-owned angle of zero fixes no reference. But
the contract it left required the source to state the orientation *twice*: once
as the frame binding that says this support's tangent **is** the world's x axis
and its normal **is** the world's y, and again as a numeric zero. The binding is
the complete statement; that is exactly why the compiler, the law and the
closure all make it mandatory. The second copy was a restatement in a form the
public v1 record has no field for, so a source that stated the orientation
completely was refused for not repeating itself.

Three places asked that duplicated question — `complete_profile`'s planner,
`complete_profile_application`'s closure, and both the compiler contract and the
law recognizer. All four now read the same one reading, `stated_support_orientation`,
and the numeric zero is an optional *second* statement that must agree when
present.

Nothing is widened. This suite pins that: the frame binding is still mandatory
everywhere, a wrong axis or a reversed normal is still refused, a vertical or
inclined support is still refused, and the frame-less v1 shape — the one the
public corpus actually has — still fails closed exactly as B15 left it.

Everything here is synthetic. No public archive is read.
"""

from __future__ import annotations

import pytest

from evaluation.phase56_stage7.typed_support_frames import (
    stated_support_orientation,
)


WORLD = "v2_frame_world"
SUPPORT = "v2_frame_support"
SURFACE = "surface"


def _axis(name: str, frame_id: str, axis: str, sign: int = 1) -> dict:
    return {
        "axis": name,
        "direction": {"kind": "axis", "frame_id": frame_id, "axis": axis, "sign": sign},
    }


def _world(**overrides) -> dict:
    frame = {
        "frame_id": WORLD,
        "frame_type": "cartesian_2d",
        "origin": {"kind": "world"},
        "parent_frame_id": None,
        "axes": [_axis("x", WORLD, "x"), _axis("y", WORLD, "y")],
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": ["ev_level"],
    }
    frame.update(overrides)
    return frame


def _support(
    *,
    tangent_axis: str = "x",
    tangent_sign: int = 1,
    normal_axis: str = "y",
    normal_sign: int = 1,
    **overrides,
) -> dict:
    frame = {
        "frame_id": SUPPORT,
        "frame_type": "cartesian_2d",
        "origin": {"kind": "entity", "entity_id": SURFACE},
        "parent_frame_id": WORLD,
        "axes": [
            _axis("tangent", WORLD, tangent_axis, tangent_sign),
            _axis("normal", WORLD, normal_axis, normal_sign),
        ],
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": ["ev_level"],
    }
    frame.update(overrides)
    return frame


def _payload(*frames: dict) -> dict:
    return {
        "entities": [{"entity_id": SURFACE, "primitive": "surface"}],
        "reference_frames": list(frames),
    }


def _reads(*frames: dict) -> bool:
    return stated_support_orientation(_payload(*frames), support_id=SURFACE) is not None


# --------------------------------------------------------------------------
# The one shape that is a stated horizontal support
# --------------------------------------------------------------------------
def test_a_support_bound_to_world_x_and_y_states_its_orientation() -> None:
    assert _reads(_world(), _support())


def test_the_reading_carries_both_frames_back() -> None:
    read = stated_support_orientation(_payload(_world(), _support()), support_id=SURFACE)

    assert read is not None
    world, support = read
    assert world["frame_id"] == WORLD
    assert support["frame_id"] == SUPPORT


# --------------------------------------------------------------------------
# Every way the statement can be wrong
# --------------------------------------------------------------------------
def test_no_frame_at_all_is_not_a_statement() -> None:
    """The public v1 shape.  B15's revocation, unchanged."""

    assert not _reads()


def test_a_world_frame_alone_is_not_a_statement() -> None:
    assert not _reads(_world())


def test_a_tangent_bound_to_world_y_states_a_vertical_support() -> None:
    assert not _reads(_world(), _support(tangent_axis="y", normal_axis="x"))


def test_a_reversed_normal_is_a_different_statement() -> None:
    assert not _reads(_world(), _support(normal_sign=-1))


def test_a_reversed_tangent_is_a_different_statement() -> None:
    assert not _reads(_world(), _support(tangent_sign=-1))


def test_a_support_anchored_on_something_else_states_nothing_about_this_one() -> None:
    assert not _reads(
        _world(), _support(origin={"kind": "entity", "entity_id": "other"})
    )


def test_a_support_parented_to_an_unstated_frame_is_refused() -> None:
    assert not _reads(_world(), _support(parent_frame_id="v2_frame_elsewhere"))


def test_a_support_with_no_parent_is_refused() -> None:
    assert not _reads(_world(), _support(parent_frame_id=None))


def test_a_world_frame_with_a_parent_is_refused() -> None:
    assert not _reads(_world(parent_frame_id="v2_frame_other"), _support())


def test_a_world_frame_whose_axes_are_not_its_own_is_refused() -> None:
    assert not _reads(
        _world(axes=[_axis("x", SUPPORT, "tangent"), _axis("y", SUPPORT, "normal")]),
        _support(),
    )


def test_an_unevidenced_frame_is_refused() -> None:
    assert not _reads(_world(evidence_refs=[]), _support())
    assert not _reads(_world(), _support(evidence_refs=[]))


def test_a_translating_or_rotating_frame_is_refused() -> None:
    assert not _reads(_world(), _support(translating_with_entity_id="cart"))
    assert not _reads(_world(), _support(rotating_about_point_id="pt"))


def test_a_third_frame_makes_the_pair_ambiguous() -> None:
    third = _support(frame_id="v2_frame_third")
    assert not _reads(_world(), _support(), third)


def test_two_world_frames_are_refused() -> None:
    assert not _reads(_world(), _world(frame_id="v2_frame_world_b"))


def test_a_non_cartesian_frame_type_is_refused() -> None:
    assert not _reads(_world(), _support(frame_type="tangential_normal"))


def test_a_support_frame_with_one_axis_is_refused() -> None:
    assert not _reads(_world(), _support(axes=[_axis("tangent", WORLD, "x")]))


def test_a_semantic_direction_is_not_an_axis_binding() -> None:
    assert not _reads(
        _world(),
        _support(
            axes=[
                {"axis": "tangent", "direction": {"kind": "semantic", "direction": "right"}},
                _axis("normal", WORLD, "y"),
            ]
        ),
    )


# --------------------------------------------------------------------------
# The planner and the closure ask one question with one function
# --------------------------------------------------------------------------
def test_the_planner_and_the_closure_share_the_reading() -> None:
    """Not a style point: two readings of one question is how a gate drifts.

    Before this package the planner had its own narrower rule — a numeric zero —
    so it reported the profile incomplete while the closure stood ready to build
    it from the frame the source had actually stated.
    """

    from evaluation.phase56_stage7 import complete_profile
    from evaluation.phase56_stage7 import complete_profile_application

    assert (
        complete_profile.stated_support_orientation
        is complete_profile_application._stated_support_orientation
        is stated_support_orientation
    )


@pytest.mark.parametrize(
    "primitive",
    ["incline", "rigid_body", "pulley", "rope"],
)
def test_only_a_surface_entity_can_carry_a_support_orientation(primitive: str) -> None:
    from evaluation.phase56_stage7.typed_support_frames import (
        payload_states_horizontal_support,
    )

    payload = {
        "entities": [{"entity_id": SURFACE, "primitive": primitive}],
        "reference_frames": [_world(), _support()],
    }

    assert payload_states_horizontal_support(payload) is False


def test_a_surface_entity_with_the_frames_states_the_support() -> None:
    from evaluation.phase56_stage7.typed_support_frames import (
        payload_states_horizontal_support,
    )

    assert payload_states_horizontal_support(_payload(_world(), _support())) is True
