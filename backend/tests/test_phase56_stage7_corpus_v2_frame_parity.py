"""v2 frame projection parity against the fully-authored positive fixtures.

The B15 and B16 packages each carry a *fully authored* Draft fixture — the
frames a richer source would state — and the engine hardening consumes exactly
those shapes: a world frame anchored at the world with typed ``axis`` bindings,
a support frame whose tangent names the world's x, a slope frame whose axes
are their own tangential identities.  The first v2 projection produced none of
that: it anchored world frames on pseudo entities, emitted ``semantic`` axis
directions, and collapsed opposite senses onto one value.

These tests pin the corrected projection to the fixtures.  A v2 source carrier
must project a frame whose *canonical semantics* — frame type, origin, parent,
local axis names, direction kind, referenced frame, referenced axis, sign,
evidence, translating/rotating bindings — equal the fixture's, with only the
generated identifier spellings free to differ.
"""

from __future__ import annotations

from typing import Any

import pytest

from engine.mechanics.contracts import ReferenceFrame
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    CorpusV2AugmentationV1,
    FrameAxisV2,
    FrameOriginKind,
    FrameType,
    ReferenceFrameV2,
)
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
    validate_augmentation,
)
from tests.test_phase56_stage7_b15_table_pulley import (
    _stated_orientation_frames,
)
from tests.test_phase56_stage7_b16_incline_kinetic_friction import (
    _stated_slope_frames,
)

EV = ("ev_orientation",)


# ---------------------------------------------------------------------------
# Canonical semantics: everything but identifier spelling
# ---------------------------------------------------------------------------


def _canonical(frames: list[dict[str, Any]]) -> tuple:
    """One frame list as ID-spelling-free semantics, order preserved."""

    tokens = {frame["frame_id"]: f"F{index}" for index, frame in enumerate(frames)}

    def _token(value: Any) -> Any:
        return tokens.get(value, value)

    out = []
    for frame in frames:
        origin = dict(frame["origin"])
        if "frame_id" in origin:
            origin["frame_id"] = _token(origin["frame_id"])
        out.append(
            (
                frame["frame_type"],
                tuple(sorted(origin.items())),
                _token(frame.get("parent_frame_id")),
                tuple(
                    (
                        axis["axis"],
                        axis["direction"]["kind"],
                        _token(axis["direction"].get("frame_id")),
                        axis["direction"].get("axis"),
                        axis["direction"].get("sign", 1),
                    )
                    for axis in frame["axes"]
                ),
                frame.get("translating_with_entity_id"),
                frame.get("rotating_about_point_id"),
                tuple(sorted(frame.get("evidence_refs") or [])),
            )
        )
    return tuple(out)


def _axis(
    name: str,
    sense: AxisSense,
    bound_frame: str,
    bound_axis: str,
    sign: int = 1,
) -> FrameAxisV2:
    return FrameAxisV2(
        axis=name,
        sense=sense,
        bound_frame_id=bound_frame,
        bound_axis=bound_axis,
        bound_sign=sign,
        evidence_refs=EV,
    )


def _world_frame(frame_id: str = "v2_world") -> ReferenceFrameV2:
    return ReferenceFrameV2(
        frame_id=frame_id,
        frame_type=FrameType.world_cartesian,
        subject_id="surface",
        axes=(
            _axis("x", AxisSense.along_surface_forward, frame_id, "x"),
            _axis("y", AxisSense.up_the_page, frame_id, "y"),
        ),
        evidence_refs=EV,
    )


def _support_frame(
    *,
    tangent_axis: str = "x",
    normal_axis: str = "y",
    tangent_sign: int = 1,
    normal_sign: int = 1,
    subject_id: str = "surface",
    axes: tuple[FrameAxisV2, ...] | None = None,
) -> ReferenceFrameV2:
    return ReferenceFrameV2(
        frame_id="v2_support",
        frame_type=FrameType.surface_tangent_normal,
        subject_id=subject_id,
        parent_frame_id="v2_world",
        axes=axes
        if axes is not None
        else (
            _axis(
                "tangent",
                AxisSense.along_surface_forward,
                "v2_world",
                tangent_axis,
                tangent_sign,
            ),
            _axis(
                "normal",
                AxisSense.away_from_surface,
                "v2_world",
                normal_axis,
                normal_sign,
            ),
        ),
        evidence_refs=EV,
    )


def _slope_frame(
    *,
    self_bound: bool = True,
) -> ReferenceFrameV2:
    frame_id = "v2_slope"
    if self_bound:
        axes = (
            _axis("tangent", AxisSense.down_slope, frame_id, "tangent"),
            _axis("normal", AxisSense.away_from_surface, frame_id, "normal"),
        )
    else:
        # The unstated shortcut: binding the slope tangent to a world axis
        # states the slope is world-aligned, which the source never said.
        axes = (
            _axis("tangent", AxisSense.down_slope, "v2_world", "x"),
            _axis("normal", AxisSense.away_from_surface, "v2_world", "y"),
        )
    return ReferenceFrameV2(
        frame_id=frame_id,
        frame_type=FrameType.incline_tangent_normal,
        subject_id="incline",
        parent_frame_id="v2_world",
        axes=axes,
        evidence_refs=EV,
    )


def _project(*frames: ReferenceFrameV2) -> list[dict[str, Any]]:
    payload = {"reference_frames": []}
    merged = project_augmentation(
        payload, CorpusV2AugmentationV1(reference_frames=tuple(frames))
    )
    return merged["reference_frames"]


# ---------------------------------------------------------------------------
# Positive parity
# ---------------------------------------------------------------------------


def test_a_v2_world_frame_projects_to_the_authored_world_fixture() -> None:
    fixture = _stated_orientation_frames(evidence=EV)[:1]
    projected = _project(_world_frame())

    assert _canonical(projected) == _canonical(fixture)
    assert projected[0]["origin"] == {"kind": "world"}
    ReferenceFrame.model_validate(projected[0])


def test_a_v2_support_frame_projects_to_the_b15_horizontal_fixture() -> None:
    fixture = _stated_orientation_frames(evidence=EV)
    projected = _project(_world_frame(), _support_frame())

    assert _canonical(projected) == _canonical(fixture)
    # The world-aligned statement arrives as the cartesian frame B15 consumes.
    assert projected[1]["frame_type"] == "cartesian_2d"
    for frame in projected:
        ReferenceFrame.model_validate(frame)


def test_a_v2_slope_frame_projects_to_the_b16_slope_fixture() -> None:
    fixture = _stated_slope_frames(evidence=EV)
    projected = _project(_world_frame(), _slope_frame())

    assert _canonical(projected) == _canonical(fixture)
    # Self-referential identities keep the tangential-normal type.
    assert projected[1]["frame_type"] == "tangential_normal"
    for frame in projected:
        ReferenceFrame.model_validate(frame)


def test_the_tangential_normal_fixture_axes_are_typed_axis_bindings() -> None:
    projected = _project(_world_frame(), _slope_frame())
    for frame in projected:
        for axis in frame["axes"]:
            assert axis["direction"]["kind"] == "axis"
            assert axis["direction"]["sign"] in (-1, 1)


def test_opposite_senses_do_not_collapse() -> None:
    forward = _project(
        _world_frame(),
        _support_frame(tangent_sign=1),
    )
    backward = _project(
        _world_frame(),
        _support_frame(tangent_sign=-1),
    )
    assert forward[1]["axes"][0]["direction"]["sign"] == 1
    assert backward[1]["axes"][0]["direction"]["sign"] == -1
    assert _canonical(forward) != _canonical(backward)


def test_validation_accepts_the_parity_shapes() -> None:
    validate_augmentation(
        CorpusV2AugmentationV1(
            reference_frames=(_world_frame(), _support_frame())
        ),
        known_evidence_ids=EV,
    )
    validate_augmentation(
        CorpusV2AugmentationV1(reference_frames=(_world_frame(), _slope_frame())),
        known_evidence_ids=EV,
    )


# ---------------------------------------------------------------------------
# Negative controls — every way the frame can be wrong
# ---------------------------------------------------------------------------


def _expect(reason: V2ValidationReason, *frames: ReferenceFrameV2) -> None:
    with pytest.raises(V2ValidationError) as caught:
        validate_augmentation(
            CorpusV2AugmentationV1(reference_frames=tuple(frames)),
            known_evidence_ids=EV,
        )
    assert caught.value.reason is reason


def test_a_world_frame_with_an_entity_origin_is_refused() -> None:
    world = _world_frame().model_copy(
        update={"origin_kind": FrameOriginKind.entity}
    )
    _expect(V2ValidationReason.frame_origin_invalid, world)


def test_a_non_world_frame_claiming_the_world_anchor_is_refused() -> None:
    support = _support_frame().model_copy(
        update={"origin_kind": FrameOriginKind.world}
    )
    _expect(V2ValidationReason.frame_origin_invalid, _world_frame(), support)


def test_a_world_frame_with_a_parent_is_refused() -> None:
    world = _world_frame().model_copy(update={"parent_frame_id": "v2_support"})
    _expect(
        V2ValidationReason.world_frame_parent_forbidden,
        world,
        _support_frame(),
    )


def test_a_missing_axis_is_a_different_frame() -> None:
    fixture = _stated_orientation_frames(evidence=EV)
    partial = _support_frame(
        axes=(
            _axis("tangent", AxisSense.along_surface_forward, "v2_world", "x"),
        )
    )
    projected = _project(_world_frame(), partial)
    assert _canonical(projected) != _canonical(fixture)


def test_an_axis_without_its_binding_is_refused_not_inferred() -> None:
    unbound = ReferenceFrameV2(
        frame_id="v2_support",
        frame_type=FrameType.surface_tangent_normal,
        subject_id="surface",
        parent_frame_id="v2_world",
        axes=(
            FrameAxisV2(
                axis="tangent",
                sense=AxisSense.along_surface_forward,
                evidence_refs=EV,
            ),
            FrameAxisV2(
                axis="normal",
                sense=AxisSense.away_from_surface,
                evidence_refs=EV,
            ),
        ),
        evidence_refs=EV,
    )
    _expect(V2ValidationReason.axis_binding_missing, _world_frame(), unbound)
    # The projection refuses the same shape rather than reading the sense.
    with pytest.raises(V2ValidationError) as caught:
        _project(_world_frame(), unbound)
    assert caught.value.reason is V2ValidationReason.axis_binding_missing


def test_a_tangent_bound_to_y_is_not_the_b15_statement() -> None:
    fixture = _stated_orientation_frames(evidence=EV)
    projected = _project(
        _world_frame(), _support_frame(tangent_axis="y", normal_axis="x")
    )
    assert _canonical(projected) != _canonical(fixture)


def test_a_reversed_normal_is_not_the_b15_statement() -> None:
    fixture = _stated_orientation_frames(evidence=EV)
    projected = _project(_world_frame(), _support_frame(normal_sign=-1))
    assert _canonical(projected) != _canonical(fixture)


def test_a_dangling_binding_frame_is_refused() -> None:
    dangling = _support_frame(
        axes=(
            _axis("tangent", AxisSense.along_surface_forward, "v2_ghost", "x"),
            _axis("normal", AxisSense.away_from_surface, "v2_world", "y"),
        )
    )
    _expect(
        V2ValidationReason.axis_binding_frame_unknown, _world_frame(), dangling
    )


def test_a_binding_to_an_axis_the_frame_lacks_is_refused() -> None:
    missing_axis = _support_frame(
        axes=(
            _axis("tangent", AxisSense.along_surface_forward, "v2_world", "z"),
            _axis("normal", AxisSense.away_from_surface, "v2_world", "y"),
        )
    )
    _expect(
        V2ValidationReason.axis_binding_axis_unknown, _world_frame(), missing_axis
    )


def test_an_axis_name_outside_the_engine_vocabulary_is_refused() -> None:
    with pytest.raises(V2ValidationError) as caught:
        validate_augmentation(
            CorpusV2AugmentationV1(
                reference_frames=(
                    ReferenceFrameV2(
                        frame_id="v2_world",
                        frame_type=FrameType.world_cartesian,
                        subject_id="surface",
                        axes=(
                            _axis(
                                "sideways",
                                AxisSense.along_surface_forward,
                                "v2_world",
                                "sideways",
                            ),
                        ),
                        evidence_refs=EV,
                    ),
                )
            ),
            known_evidence_ids=EV,
        )
    assert caught.value.reason is V2ValidationReason.axis_name_unknown


def test_a_duplicate_local_axis_is_refused() -> None:
    with pytest.raises(Exception):
        # Two tangents — with agreeing or conflicting signs alike — are two
        # statements about one name and are refused at construction.
        ReferenceFrameV2(
            frame_id="v2_support",
            frame_type=FrameType.surface_tangent_normal,
            subject_id="surface",
            axes=(
                _axis("tangent", AxisSense.along_surface_forward, "v2_world", "x", 1),
                _axis("tangent", AxisSense.along_surface_backward, "v2_world", "x", -1),
            ),
            evidence_refs=EV,
        )


def test_a_slope_bound_to_world_directions_is_not_the_b16_statement() -> None:
    fixture = _stated_slope_frames(evidence=EV)
    projected = _project(_world_frame(), _slope_frame(self_bound=False))
    # Binding the slope tangent to world x states world alignment: the
    # projected frame type is cartesian, which the B16 fixture is not.
    assert projected[1]["frame_type"] == "cartesian_2d"
    assert _canonical(projected) != _canonical(fixture)


def test_an_unevidenced_axis_is_not_constructible() -> None:
    with pytest.raises(Exception):
        FrameAxisV2(
            axis="tangent",
            sense=AxisSense.along_surface_forward,
            bound_frame_id="v2_world",
            bound_axis="x",
            bound_sign=1,
            evidence_refs=(),
        )


def test_a_frame_cycle_is_refused() -> None:
    first = ReferenceFrameV2(
        frame_id="v2_a",
        frame_type=FrameType.surface_tangent_normal,
        subject_id="surface",
        axes=(_axis("tangent", AxisSense.along_surface_forward, "v2_b", "tangent"),),
        evidence_refs=EV,
    )
    second = ReferenceFrameV2(
        frame_id="v2_b",
        frame_type=FrameType.surface_tangent_normal,
        subject_id="surface",
        axes=(_axis("tangent", AxisSense.along_surface_forward, "v2_a", "tangent"),),
        evidence_refs=EV,
    )
    _expect(V2ValidationReason.frame_cycle, first, second)


def test_a_parent_cycle_is_refused() -> None:
    first = ReferenceFrameV2(
        frame_id="v2_a",
        frame_type=FrameType.surface_tangent_normal,
        subject_id="surface",
        parent_frame_id="v2_b",
        axes=(_axis("tangent", AxisSense.along_surface_forward, "v2_a", "tangent"),),
        evidence_refs=EV,
    )
    second = ReferenceFrameV2(
        frame_id="v2_b",
        frame_type=FrameType.surface_tangent_normal,
        subject_id="surface",
        parent_frame_id="v2_a",
        axes=(_axis("tangent", AxisSense.along_surface_forward, "v2_b", "tangent"),),
        evidence_refs=EV,
    )
    _expect(V2ValidationReason.frame_cycle, first, second)
