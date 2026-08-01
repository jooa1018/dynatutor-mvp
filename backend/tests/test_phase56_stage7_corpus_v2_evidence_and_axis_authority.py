"""Two bypasses in the v2 contract, closed and pinned.

*The empty evidence universe.*  The validator's unknown-reference check was
guarded on the universe being non-empty — `if evidence and any(...)`.  A context
whose v1 record declares no source evidence, augmented by a manifest that
authors no quote, has an empty universe, so every `evidence_refs` entry passed
unexamined: the check failed *open* in precisely the case it exists for.  A
carrier cites evidence or it is an assertion, and an unknown reference is
unknown whether or not anything else is known.

*AxisSense as physics authority.*  `sense` is descriptive vocabulary — what the
source called a direction — and the typed `axis(frame, name, sign)` binding is
the projection authority.  A sense may never supply a missing sign, frame or
axis, and changing only a sense must leave projected runtime semantics
identical.  It earns exactly one power: refusing a cross-frame binding whose two
axes carry directly opposed senses and a sign that agrees with neither reading.
Senses from different oppositions — world up against a surface normal — are not
comparable at all and are left alone, because deciding between them would need
geometry this contract does not carry.

Everything here is synthetic.
"""

from __future__ import annotations

import pytest

from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    ContactSide,
    ContactSideV2,
    CorpusV2AugmentationV1,
    FrameAxisV2,
    FrameOriginKind,
    FrameType,
    ReferenceFrameV2,
    SourceQuoteEvidenceV2,
)
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
    validate_augmentation,
)


SOURCE = "블록이 수평면 위에서 오른쪽으로 미끄러진다."


def _contact(evidence_refs: tuple[str, ...]) -> ContactSideV2:
    return ContactSideV2(
        contact_id="v2_contact_a",
        interaction_id="i1",
        side=ContactSide.inside_track,
        subject_id="body",
        evidence_refs=evidence_refs,
    )


def _validate(augmentation: CorpusV2AugmentationV1, **known) -> None:
    validate_augmentation(
        augmentation,
        known_entity_ids=known.get("entities", ("body",)),
        known_interaction_ids=known.get("interactions", ("i1",)),
        known_evidence_ids=known.get("evidence", ()),
    )


def _reason(augmentation: CorpusV2AugmentationV1, **known) -> V2ValidationReason:
    with pytest.raises(V2ValidationError) as raised:
        _validate(augmentation, **known)
    return raised.value.reason


# --------------------------------------------------------------------------
# The empty evidence universe
# --------------------------------------------------------------------------
def test_an_empty_evidence_universe_refuses_an_unknown_reference() -> None:
    """The bypass itself: no source evidence, no quote, a reference to nothing."""

    augmentation = CorpusV2AugmentationV1(contact_sides=(_contact(("nowhere",)),))

    assert _reason(augmentation) is V2ValidationReason.evidence_ref_unknown


def test_a_reference_to_the_sources_own_evidence_is_accepted() -> None:
    augmentation = CorpusV2AugmentationV1(contact_sides=(_contact(("ev_1",)),))

    _validate(augmentation, evidence=("ev_1",))


def test_a_reference_to_an_authored_quote_is_accepted() -> None:
    augmentation = CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_flat", quote="수평면"),
        ),
        contact_sides=(_contact(("v2_ev_flat",)),),
    )

    _validate(augmentation)


def test_one_valid_and_one_invalid_reference_is_still_refused() -> None:
    augmentation = CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_flat", quote="수평면"),
        ),
        contact_sides=(_contact(("v2_ev_flat", "nowhere")),),
    )

    assert _reason(augmentation) is V2ValidationReason.evidence_ref_unknown


def test_a_duplicate_authored_quote_is_refused() -> None:
    augmentation = CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_a", quote="수평면"),
            SourceQuoteEvidenceV2(evidence_id="v2_ev_b", quote="수평면"),
        ),
        contact_sides=(_contact(("v2_ev_a",)),),
    )

    assert _reason(augmentation) is V2ValidationReason.duplicate_source_quote


def test_a_quote_the_source_does_not_contain_is_refused_at_projection() -> None:
    augmentation = CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_x", quote="경사면"),
        ),
        contact_sides=(_contact(("v2_ev_x",)),),
    )

    with pytest.raises(V2ValidationError) as raised:
        project_augmentation({"entities": []}, augmentation, problem_text=SOURCE)
    assert raised.value.reason is V2ValidationReason.evidence_quote_not_in_source


def test_an_aligned_quote_projects() -> None:
    augmentation = CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_flat", quote="수평면"),
        ),
        contact_sides=(_contact(("v2_ev_flat",)),),
    )

    project_augmentation({"entities": []}, augmentation, problem_text=SOURCE)


# --------------------------------------------------------------------------
# AxisSense is not runtime authority
# --------------------------------------------------------------------------
def _axis(
    name: str,
    sense: AxisSense,
    *,
    bound_frame: str,
    bound_axis: str | None = None,
    sign: int = 1,
) -> FrameAxisV2:
    return FrameAxisV2(
        axis=name,
        sense=sense,
        bound_frame_id=bound_frame,
        bound_axis=bound_axis or name,
        bound_sign=sign,
        evidence_refs=("v2_ev_flat",),
    )


def _frames(
    *,
    support_tangent_sense: AxisSense = AxisSense.along_surface_forward,
    world_x_sense: AxisSense = AxisSense.along_surface_forward,
    tangent_sign: int = 1,
) -> tuple[ReferenceFrameV2, ...]:
    world = ReferenceFrameV2(
        frame_id="v2_frame_world",
        frame_type=FrameType.world_cartesian,
        origin_kind=FrameOriginKind.world,
        subject_id="body",
        axes=(
            _axis("x", world_x_sense, bound_frame="v2_frame_world"),
            _axis("y", AxisSense.up_the_page, bound_frame="v2_frame_world"),
        ),
        evidence_refs=("v2_ev_flat",),
    )
    support = ReferenceFrameV2(
        frame_id="v2_frame_support",
        frame_type=FrameType.surface_tangent_normal,
        origin_kind=FrameOriginKind.entity,
        subject_id="body",
        axes=(
            _axis(
                "x",
                support_tangent_sense,
                bound_frame="v2_frame_world",
                bound_axis="x",
                sign=tangent_sign,
            ),
            _axis(
                "y",
                AxisSense.away_from_surface,
                bound_frame="v2_frame_world",
                bound_axis="y",
                sign=1,
            ),
        ),
        evidence_refs=("v2_ev_flat",),
    )
    return (world, support)


def _framed(**knobs) -> CorpusV2AugmentationV1:
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_flat", quote="수평면"),
        ),
        reference_frames=_frames(**knobs),
    )


def test_changing_only_a_sense_leaves_the_projection_identical() -> None:
    """The whole claim, measured: sense is not projection authority."""

    base = project_augmentation({"entities": []}, _framed(), problem_text=SOURCE)
    renamed = project_augmentation(
        {"entities": []},
        _framed(
            support_tangent_sense=AxisSense.along_surface_backward,
            world_x_sense=AxisSense.along_surface_backward,
        ),
        problem_text=SOURCE,
    )

    assert base == renamed


def test_a_sense_never_completes_a_missing_binding() -> None:
    partial = ReferenceFrameV2(
        frame_id="v2_frame_world",
        frame_type=FrameType.world_cartesian,
        origin_kind=FrameOriginKind.world,
        subject_id="body",
        axes=(
            FrameAxisV2(
                axis="x",
                # A sense that names a direction unambiguously, and no binding.
                sense=AxisSense.along_surface_forward,
                bound_frame_id="v2_frame_world",
                bound_axis="x",
                evidence_refs=("v2_ev_flat",),
            ),
        ),
        evidence_refs=("v2_ev_flat",),
    )
    augmentation = CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id="v2_ev_flat", quote="수평면"),
        ),
        reference_frames=(partial,),
    )

    assert _reason(augmentation) is V2ValidationReason.axis_binding_missing


def test_opposed_senses_with_a_positive_sign_are_refused() -> None:
    augmentation = _framed(
        support_tangent_sense=AxisSense.along_surface_backward,
        world_x_sense=AxisSense.along_surface_forward,
        tangent_sign=1,
    )

    assert _reason(augmentation) is V2ValidationReason.axis_sense_contradicts_binding


def test_identical_senses_with_a_negative_sign_are_refused() -> None:
    augmentation = _framed(
        support_tangent_sense=AxisSense.along_surface_forward,
        world_x_sense=AxisSense.along_surface_forward,
        tangent_sign=-1,
    )

    assert _reason(augmentation) is V2ValidationReason.axis_sense_contradicts_binding


def test_opposed_senses_with_a_negative_sign_are_accepted() -> None:
    _validate(
        _framed(
            support_tangent_sense=AxisSense.along_surface_backward,
            world_x_sense=AxisSense.along_surface_forward,
            tangent_sign=-1,
        )
    )


def test_identical_senses_with_a_positive_sign_are_accepted() -> None:
    _validate(_framed())


def test_senses_from_different_oppositions_are_not_compared_at_all() -> None:
    """A surface normal may or may not point up the page.  Binding decides."""

    _validate(
        _framed(
            support_tangent_sense=AxisSense.up_the_page,
            world_x_sense=AxisSense.along_surface_forward,
            tangent_sign=1,
        )
    )
    _validate(
        _framed(
            support_tangent_sense=AxisSense.up_the_page,
            world_x_sense=AxisSense.along_surface_forward,
            tangent_sign=-1,
        )
    )


def test_a_self_bound_axis_is_an_identity_and_its_sense_is_not_consulted() -> None:
    """Self-binding says "this frame's x is its own x"; sense describes it."""

    _validate(
        CorpusV2AugmentationV1(
            source_quotes=(
                SourceQuoteEvidenceV2(evidence_id="v2_ev_flat", quote="수평면"),
            ),
            reference_frames=(
                ReferenceFrameV2(
                    frame_id="v2_frame_world",
                    frame_type=FrameType.world_cartesian,
                    origin_kind=FrameOriginKind.world,
                    subject_id="body",
                    axes=(
                        _axis("x", AxisSense.up_the_page, bound_frame="v2_frame_world"),
                        _axis(
                            "y", AxisSense.down_the_page, bound_frame="v2_frame_world"
                        ),
                    ),
                    evidence_refs=("v2_ev_flat",),
                ),
            ),
        )
    )
