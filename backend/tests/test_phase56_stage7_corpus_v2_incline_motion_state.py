"""B31: a slide's direction closes the kinetic cohort, and a speed is never invented.

Kinetic friction opposes the motion that exists, so the closure and the law both
need *which way* the body is going and neither reads *how fast*: the emission
consults `motion_sign` and nothing else. Until this package they demanded a
positive numeric speed anyway, which meant a corpus could only express the
direction by inventing a magnitude — and an invented magnitude is
indistinguishable downstream from a stated one. A value-free directed motion
record is now admitted, and a stated speed is still checked exactly as before.

The second half of this package is a defect the gold-scored shadow found and a
runtime-only measurement could not have. `SENSE_SIGN` maps `down_slope` to −1,
which assumes an up-slope-positive tangent; the engine's kinetic-slide law
resolves the same axis down-slope-positive. A slide authored with the
slope-relative spelling therefore reached the *up-slope* formula — three
contexts solved, verified, and confidently wrong by exactly the friction term.
The three counts caught it as `newly_solved_wrong: 3`; the pre-B28 runner would
have reported `newly solved 3, wrong 0`.

The fix is not a second convention. A self-referential tangent binding — the
only kind an incline frame carries — states an identity and no orientation, so
`up_slope`/`down_slope` on that axis is refused rather than resolved, and the
axis-relative spelling, whose meaning the binding alone fixes, is required.

Everything here is synthetic.
"""

from __future__ import annotations

import pytest

from evaluation.phase56_stage7.corpus_v2.merge import SENSE_SIGN
from evaluation.phase56_stage7.corpus_v2.projection import (
    derived_authority_ids,
    derived_authority_records,
    project_augmentation,
)
from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    CorpusV2AugmentationV1,
    FrameAxisV2,
    FrameOriginKind,
    FrameType,
    MotionSense,
    MotionSenseV2,
    ReferenceFrameV2,
    SourceQuoteEvidenceV2,
)
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
    validate_augmentation,
)


SOURCE = "블록이 경사면을 따라 아래쪽으로 미끄러진다. 운동마찰계수는 0.12이다."
WORLD = "v2_frame_world"
SLOPE = "v2_frame_slope"
EV = "v2_ev_downslope"


def _axis(name: str, sense: AxisSense, frame_id: str, bound_axis: str) -> FrameAxisV2:
    return FrameAxisV2(
        axis=name,
        sense=sense,
        bound_frame_id=frame_id,
        bound_axis=bound_axis,
        bound_sign=1,
        evidence_refs=(EV,),
    )


def _frames(slope_type: FrameType = FrameType.incline_tangent_normal):
    world = ReferenceFrameV2(
        frame_id=WORLD,
        frame_type=FrameType.world_cartesian,
        origin_kind=FrameOriginKind.world,
        subject_id="incline",
        axes=(
            _axis("x", AxisSense.along_surface_forward, WORLD, "x"),
            _axis("y", AxisSense.up_the_page, WORLD, "y"),
        ),
        evidence_refs=(EV,),
    )
    slope = ReferenceFrameV2(
        frame_id=SLOPE,
        frame_type=slope_type,
        origin_kind=FrameOriginKind.entity,
        subject_id="incline",
        parent_frame_id=WORLD,
        axes=(
            _axis("tangent", AxisSense.down_slope, SLOPE, "tangent"),
            _axis("normal", AxisSense.away_from_surface, SLOPE, "normal"),
        ),
        evidence_refs=(EV,),
    )
    return world, slope


def _augmentation(
    *,
    sense: MotionSense = MotionSense.along_axis_positive,
    sign: int = 1,
    axis: str = "tangent",
    interval_id: str | None = "motion_1",
    event_id: str | None = None,
    quantity_id: str | None = None,
    slope_type: FrameType = FrameType.incline_tangent_normal,
    with_sense: bool = True,
) -> CorpusV2AugmentationV1:
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id=EV, quote="아래쪽으로 미끄러진다"),
        ),
        reference_frames=_frames(slope_type),
        motion_senses=(
            (
                MotionSenseV2(
                    sense_id="v2_motion_downslope",
                    sense=sense,
                    frame_id=SLOPE,
                    axis=axis,
                    sign=sign,
                    subject_id="body",
                    interval_id=interval_id,
                    event_id=event_id,
                    quantity_id=quantity_id,
                    evidence_refs=(EV,),
                ),
            )
            if with_sense
            else ()
        ),
    )


def _validate(augmentation: CorpusV2AugmentationV1) -> None:
    validate_augmentation(
        augmentation,
        known_entity_ids=("body", "incline"),
        known_interval_ids=("motion_1",),
        known_event_ids=("start",),
    )


def _reason(augmentation: CorpusV2AugmentationV1) -> V2ValidationReason:
    with pytest.raises(V2ValidationError) as raised:
        _validate(augmentation)
    return raised.value.reason


def _project(augmentation: CorpusV2AugmentationV1) -> dict:
    return project_augmentation(
        {"entities": [], "quantities": [], "symbols": [], "assumptions": []},
        augmentation,
        problem_text=SOURCE,
    )


# --------------------------------------------------------------------------
# The slope-sense ambiguity, refused rather than resolved
# --------------------------------------------------------------------------
def test_the_two_conventions_really_do_disagree() -> None:
    """The premise of the refusal below, pinned so it cannot rot silently.

    `SENSE_SIGN` reads a down-slope slide as −1 along the tangent, which is an
    up-slope-positive tangent.  The engine's kinetic-slide law drives `+g sinθ`
    along the same axis, which is a down-slope-positive one.  Both cannot be
    right about one arrow, and the source states neither convention.
    """

    assert SENSE_SIGN[MotionSense.down_slope] == -1
    assert SENSE_SIGN[MotionSense.up_slope] == 1


@pytest.mark.parametrize(
    "sense", [MotionSense.down_slope, MotionSense.up_slope]
)
def test_a_slope_relative_sense_on_a_slope_tangent_is_refused(
    sense: MotionSense,
) -> None:
    assert (
        _reason(_augmentation(sense=sense))
        is V2ValidationReason.slope_sense_requires_axis_relative_statement
    )


@pytest.mark.parametrize(
    "sense",
    [MotionSense.along_axis_positive, MotionSense.along_axis_negative],
)
def test_an_axis_relative_sense_is_accepted(sense: MotionSense) -> None:
    _validate(_augmentation(sense=sense))


def test_the_refusal_is_specific_to_the_slope_tangent() -> None:
    """A surface frame's tangent carries a world binding, so it is not ambiguous."""

    _validate(
        _augmentation(
            sense=MotionSense.down_slope,
            slope_type=FrameType.surface_tangent_normal,
        )
    )


def test_the_sign_the_source_states_survives_projection() -> None:
    forward = _project(_augmentation(sense=MotionSense.along_axis_positive))
    backward = _project(_augmentation(sense=MotionSense.along_axis_negative))

    assert forward["quantities"][0]["direction"]["sign"] == 1
    assert backward["quantities"][0]["direction"]["sign"] == -1


# --------------------------------------------------------------------------
# The directed motion state carries no magnitude
# --------------------------------------------------------------------------
def test_a_sense_with_no_quantity_projects_a_value_free_directed_state() -> None:
    projected = _project(_augmentation())

    assert len(projected["quantities"]) == 1
    state = projected["quantities"][0]
    assert state["role"] == "velocity"
    assert state["raw_value"] is None
    assert state["raw_unit"] is None
    assert state["provenance"] == "unknown"
    assert state["component"] == "tangential"
    assert state["direction"] == {
        "kind": "axis",
        "frame_id": SLOPE,
        "axis": "tangent",
        "sign": 1,
    }
    assert state["interval_id"] == "motion_1"
    assert state["evidence_refs"] == [EV]


def test_the_directed_state_carries_a_symbol_but_never_a_number() -> None:
    projected = _project(_augmentation())

    assert len(projected["symbols"]) == 1
    symbol = projected["symbols"][0]
    assert symbol["quantity_id"] == projected["quantities"][0]["quantity_id"]
    assert projected["quantities"][0]["symbol_id"] == symbol["symbol_id"]
    assert "value" not in symbol


def test_a_sense_bound_to_an_existing_quantity_creates_no_state() -> None:
    """The valued path is unchanged: the sense fills the quantity's direction."""

    augmentation = _augmentation(quantity_id="qty_velocity")
    projected = project_augmentation(
        {
            "entities": [],
            "symbols": [],
            "assumptions": [],
            "quantities": [
                {
                    "quantity_id": "qty_velocity",
                    "role": "velocity",
                    "subject_id": "body",
                    "interval_id": "motion_1",
                    "event_id": None,
                    "frame_id": None,
                    "direction": None,
                }
            ],
        },
        augmentation,
        problem_text=SOURCE,
    )

    assert len(projected["quantities"]) == 1
    assert projected["quantities"][0]["quantity_id"] == "qty_velocity"
    assert projected["symbols"] == []


# --------------------------------------------------------------------------
# The derived authority: from the carriers, never from the manifest
# --------------------------------------------------------------------------
def test_a_slope_bound_tangent_sense_derives_the_slide_motion_authority() -> None:
    records = derived_authority_records(_augmentation())

    assert len(records) == 1
    assert records[0]["kind"] == "typed_incline_slide_motion"
    assert records[0]["subject_id"] == "body"
    assert records[0]["interval_id"] == "motion_1"
    assert records[0]["proposed_value"] is None
    assert records[0]["evidence_refs"] == [EV]
    assert derived_authority_ids(_augmentation()) == (
        "asm_closure_incline_slide_motion",
    )


def test_a_manifest_cannot_name_the_authority_it_derives() -> None:
    """There is no carrier field for it, so it can only be earned structurally."""

    assert not any(
        "assumption" in name or "authority_kind" in name
        for name in CorpusV2AugmentationV1.model_fields
    )


@pytest.mark.parametrize(
    "knobs",
    [
        pytest.param({"with_sense": False}, id="no_sense"),
        pytest.param({"axis": "normal"}, id="normal_axis"),
        pytest.param({"interval_id": None}, id="timeless"),
        pytest.param(
            {"interval_id": None, "event_id": "start"}, id="event_scoped"
        ),
        pytest.param({"quantity_id": "qty_velocity"}, id="bound_to_a_quantity"),
        pytest.param(
            {"slope_type": FrameType.surface_tangent_normal, "sense": MotionSense.down_slope},
            id="not_a_slope_frame",
        ),
    ],
)
def test_no_authority_is_derived_without_the_exact_statement(knobs: dict) -> None:
    assert derived_authority_records(_augmentation(**knobs)) == []


def test_the_derived_authority_reaches_the_projected_draft() -> None:
    projected = _project(_augmentation())

    assert len(projected["assumptions"]) == 1
    assert projected["assumptions"][0]["kind"] == "typed_incline_slide_motion"
    assert projected["assumptions"][0]["disposition"] == "approved"


def test_an_event_scoped_sense_derives_nothing_interval_wide() -> None:
    """B16's defect: an instant's direction is not the interval's."""

    projected = _project(_augmentation(interval_id=None, event_id="start"))

    assert projected["assumptions"] == []
