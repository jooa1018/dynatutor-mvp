"""The v2 candidate contract: what it can state, and what it refuses.

A carrier contract earns trust by rejecting, so most of what follows is
rejection: an unevidenced carrier, an angle with no datum, a sense with no
frame, a contact with no side, an endpoint with no event, two readings of one
number, an identifier that could shadow one the source authored.  Each is a way
a v2 record could say something the source does not, which is the one thing v2
exists to prevent.

The rest holds the line between v1 and v2 — an empty augmentation must change
nothing, a migration must preserve the original byte-for-byte and roll back
deterministically, and a shadow score must be structurally incapable of being
quoted as the official one.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from evaluation.phase56_stage7.corpus_v2.migration import (
    FORBIDDEN_MANIFEST_FIELDS,
    AugmentationEntryV1,
    AugmentationManifestV1,
    MigrationError,
    MigrationReason,
    ReviewStatus,
    archive_digest,
    assert_manifest_has_no_answer_authority,
    build_candidate_archive,
    migrate_record,
    record_fingerprint,
    rollback_to_v1,
)
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import (
    CORPUS_V2_SCHEMA_VERSION,
    V2_IDENTIFIER_PREFIX,
    AngleDatumV2,
    AxisSense,
    ConstraintAuthority,
    ConstraintAuthorityV2,
    ContactSide,
    ContactSideV2,
    CorpusV2AugmentationV1,
    EndpointCondition,
    EndpointConditionV2,
    ForceComponentKind,
    FrameAxisV2,
    FrameType,
    InteractionSide,
    InteractionTargetV2,
    MotionSense,
    MotionSenseV2,
    OrientationConvention,
    QueryObjective,
    QueryObjectiveV2,
    ReferenceFrameV2,
    ScalarEncoding,
    ScalarEncodingV2,
)
from evaluation.phase56_stage7.corpus_v2.reporting import (
    OFFICIAL_SCORE_CLASS,
    SCORE_CLASS,
    ShadowContextResultV1,
    assert_scores_are_separated,
    build_shadow_scorecard,
    scorecard_as_dict,
)
from evaluation.phase56_stage7.corpus_v2.shadow_runner import (
    ShadowRunRefused,
    assert_no_regression,
    assert_no_unaugmented_movement,
    rung_delta,
    run_shadow_context,
)
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
    validate_augmentation,
)

EV = ("ev_1",)
KNOWN = {
    "known_entity_ids": ("body", "ramp"),
    "known_interval_ids": ("i1",),
    "known_event_ids": ("v1", "v2"),
    "known_evidence_ids": ("ev_1",),
    "known_interaction_ids": ("x1",),
    "known_query_ids": ("y1",),
    "authored_ids": ("body", "ramp", "i1", "v1", "v2", "x1", "y1", "q1"),
}


def _frame(**overrides: Any) -> ReferenceFrameV2:
    base: dict[str, Any] = dict(
        frame_id="v2_slope",
        frame_type=FrameType.incline_tangent_normal,
        subject_id="ramp",
        axes=(
            FrameAxisV2(axis="tangent", sense=AxisSense.down_slope, evidence_refs=EV),
            FrameAxisV2(
                axis="normal", sense=AxisSense.away_from_surface, evidence_refs=EV
            ),
        ),
        evidence_refs=EV,
    )
    base.update(overrides)
    return ReferenceFrameV2(**base)


def _augmentation(**overrides: Any) -> CorpusV2AugmentationV1:
    return CorpusV2AugmentationV1(**overrides)


def _expect(reason: V2ValidationReason, augmentation: CorpusV2AugmentationV1) -> None:
    with pytest.raises(V2ValidationError) as caught:
        validate_augmentation(augmentation, **KNOWN)
    assert caught.value.reason is reason


# ---------------------------------------------------------------------------
# What a carrier must carry
# ---------------------------------------------------------------------------


def test_a_carrier_with_no_evidence_is_not_constructible() -> None:
    with pytest.raises(ValidationError):
        ReferenceFrameV2(
            frame_id="v2_f",
            frame_type=FrameType.world_cartesian,
            subject_id="ramp",
            axes=(
                FrameAxisV2(axis="x", sense=AxisSense.up_the_page, evidence_refs=EV),
            ),
            evidence_refs=(),
        )


def test_a_carrier_scoped_to_both_an_instant_and_a_span_is_refused() -> None:
    _expect(
        V2ValidationReason.scope_is_both_interval_and_event,
        _augmentation(
            reference_frames=(_frame(interval_id="i1", event_id="v1"),)
        ),
    )


def test_an_evidence_reference_the_source_does_not_have_is_refused() -> None:
    _expect(
        V2ValidationReason.evidence_ref_unknown,
        _augmentation(reference_frames=(_frame(evidence_refs=("ev_invented",)),)),
    )


def test_a_carrier_about_an_entity_the_source_does_not_have_is_refused() -> None:
    _expect(
        V2ValidationReason.subject_unknown,
        _augmentation(reference_frames=(_frame(subject_id="ghost"),)),
    )


def test_a_carrier_scoped_to_an_interval_the_source_does_not_have_is_refused() -> None:
    _expect(
        V2ValidationReason.cross_interval_scope,
        _augmentation(reference_frames=(_frame(interval_id="i_other"),)),
    )


def test_a_carrier_scoped_to_an_event_the_source_does_not_have_is_refused() -> None:
    _expect(
        V2ValidationReason.cross_event_scope,
        _augmentation(reference_frames=(_frame(event_id="v_other"),)),
    )


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------


def test_two_frames_with_one_identifier_are_refused() -> None:
    _expect(
        V2ValidationReason.duplicate_frame_id,
        _augmentation(reference_frames=(_frame(), _frame())),
    )


def test_a_frame_parented_to_nothing_is_refused() -> None:
    _expect(
        V2ValidationReason.dangling_frame_parent,
        _augmentation(reference_frames=(_frame(parent_frame_id="v2_missing"),)),
    )


def test_a_frame_that_is_its_own_parent_is_not_constructible() -> None:
    with pytest.raises(ValidationError):
        _frame(parent_frame_id="v2_slope")


def test_two_axes_with_one_name_are_not_constructible() -> None:
    with pytest.raises(ValidationError):
        _frame(
            axes=(
                FrameAxisV2(axis="x", sense=AxisSense.up_the_page, evidence_refs=EV),
                FrameAxisV2(axis="x", sense=AxisSense.down_the_page, evidence_refs=EV),
            )
        )


def test_a_translating_frame_must_name_what_it_translates_with() -> None:
    with pytest.raises(ValidationError):
        _frame(frame_type=FrameType.translating)


def test_a_rotating_frame_must_name_what_it_rotates_about() -> None:
    with pytest.raises(ValidationError):
        _frame(frame_type=FrameType.rotating)


# ---------------------------------------------------------------------------
# Angle datums
# ---------------------------------------------------------------------------


def _datum(**overrides: Any) -> AngleDatumV2:
    base: dict[str, Any] = dict(
        datum_id="v2_datum",
        quantity_id="q1",
        subject_id="ramp",
        measured_from_frame_id="v2_slope",
        measured_from_axis="tangent",
        measured_to_frame_id="v2_slope",
        measured_to_axis="normal",
        orientation=OrientationConvention.counterclockwise_positive,
        signed=False,
        evidence_refs=EV,
    )
    base.update(overrides)
    return AngleDatumV2(**base)


def test_an_angle_that_names_no_second_reference_is_not_constructible() -> None:
    with pytest.raises(ValidationError):
        _datum(measured_to_frame_id=None, measured_to_axis=None)


def test_an_angle_that_names_two_second_references_is_not_constructible() -> None:
    with pytest.raises(ValidationError):
        _datum(measured_to_entity_tangent_id="ramp")


def test_an_angle_measured_from_a_frame_nobody_stated_is_refused() -> None:
    _expect(
        V2ValidationReason.angle_datum_frame_unknown,
        _augmentation(
            reference_frames=(_frame(),),
            angle_datums=(_datum(measured_from_frame_id="v2_absent"),),
        ),
    )


def test_an_angle_measured_from_an_axis_the_frame_lacks_is_refused() -> None:
    _expect(
        V2ValidationReason.angle_datum_axis_unknown,
        _augmentation(
            reference_frames=(_frame(),),
            angle_datums=(_datum(measured_from_axis="z"),),
        ),
    )


def test_two_datums_for_one_angle_are_refused() -> None:
    _expect(
        V2ValidationReason.ambiguous_angle_datum,
        _augmentation(
            reference_frames=(_frame(),),
            angle_datums=(_datum(), _datum(datum_id="v2_datum_b")),
        ),
    )


# ---------------------------------------------------------------------------
# Motion senses
# ---------------------------------------------------------------------------


def _sense(**overrides: Any) -> MotionSenseV2:
    base: dict[str, Any] = dict(
        sense_id="v2_sense",
        sense=MotionSense.down_slope,
        frame_id="v2_slope",
        axis="tangent",
        sign=1,
        subject_id="body",
        interval_id="i1",
        evidence_refs=EV,
    )
    base.update(overrides)
    return MotionSenseV2(**base)


def test_a_sense_with_no_frame_is_refused() -> None:
    _expect(
        V2ValidationReason.motion_sense_frame_unknown,
        _augmentation(motion_senses=(_sense(),)),
    )


def test_a_sense_on_an_axis_the_frame_lacks_is_refused() -> None:
    _expect(
        V2ValidationReason.motion_sense_axis_unknown,
        _augmentation(reference_frames=(_frame(),), motion_senses=(_sense(axis="z"),)),
    )


def test_an_instant_sense_may_not_also_be_stated_interval_wide() -> None:
    # B16 exactly: a body that turns around spent part of the same interval
    # going the other way, so one moment does not license the whole span.
    _expect(
        V2ValidationReason.event_scoped_sense_used_interval_wide,
        _augmentation(
            reference_frames=(_frame(),),
            motion_senses=(
                _sense(sense_id="v2_a", interval_id=None, event_id="v1"),
                _sense(sense_id="v2_b", interval_id="i1"),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Contact sides, endpoints, constraints, targets, objectives, signs
# ---------------------------------------------------------------------------


def _contact(**overrides: Any) -> ContactSideV2:
    base: dict[str, Any] = dict(
        contact_id="v2_contact",
        interaction_id="x1",
        side=ContactSide.inside_track,
        normal_frame_id="v2_slope",
        normal_axis="normal",
        subject_id="body",
        evidence_refs=EV,
    )
    base.update(overrides)
    return ContactSideV2(**base)


def test_a_contact_side_with_no_normal_frame_is_refused() -> None:
    _expect(
        V2ValidationReason.contact_side_frame_unknown,
        _augmentation(contact_sides=(_contact(),)),
    )


def test_a_contact_side_on_an_axis_the_frame_lacks_is_refused() -> None:
    _expect(
        V2ValidationReason.contact_side_axis_unknown,
        _augmentation(
            reference_frames=(_frame(),), contact_sides=(_contact(normal_axis="z"),)
        ),
    )


def test_two_sides_for_one_contact_are_refused() -> None:
    _expect(
        V2ValidationReason.conflicting_contact_sides,
        _augmentation(
            reference_frames=(_frame(),),
            contact_sides=(
                _contact(),
                _contact(contact_id="v2_contact_b", side=ContactSide.outside_track),
            ),
        ),
    )


def test_an_endpoint_on_an_event_nobody_stated_is_refused() -> None:
    _expect(
        V2ValidationReason.endpoint_without_event,
        _augmentation(
            endpoint_conditions=(
                EndpointConditionV2(
                    endpoint_id="v2_end",
                    condition=EndpointCondition.reaches_natural_length,
                    boundary_event_id="v_absent",
                    subject_id="body",
                    evidence_refs=EV,
                ),
            )
        ),
    )


def test_two_endpoints_on_one_boundary_are_refused() -> None:
    def endpoint(identifier: str, condition: EndpointCondition) -> EndpointConditionV2:
        return EndpointConditionV2(
            endpoint_id=identifier,
            condition=condition,
            boundary_event_id="v2",
            subject_id="body",
            evidence_refs=EV,
        )

    _expect(
        V2ValidationReason.duplicate_endpoint,
        _augmentation(
            endpoint_conditions=(
                endpoint("v2_a", EndpointCondition.comes_to_rest),
                endpoint("v2_b", EndpointCondition.highest_point),
            )
        ),
    )


def test_a_constraint_naming_a_participant_the_source_lacks_is_refused() -> None:
    _expect(
        V2ValidationReason.constraint_without_participants,
        _augmentation(
            constraint_authorities=(
                ConstraintAuthorityV2(
                    constraint_id="v2_c",
                    authority=ConstraintAuthority.no_slip,
                    participant_ids=("ghost",),
                    subject_id="body",
                    evidence_refs=EV,
                ),
            )
        ),
    )


def test_a_constraint_with_no_participant_is_not_constructible() -> None:
    with pytest.raises(ValidationError):
        ConstraintAuthorityV2(
            constraint_id="v2_c",
            authority=ConstraintAuthority.no_slip,
            participant_ids=(),
            subject_id="body",
            evidence_refs=EV,
        )


def test_a_system_force_target_on_no_interaction_is_refused() -> None:
    _expect(
        V2ValidationReason.interaction_target_without_interaction,
        _augmentation(
            interaction_targets=(
                InteractionTargetV2(
                    target_id="v2_t",
                    interaction_id="x_absent",
                    participant_id="body",
                    side=InteractionSide.action,
                    component_kind=ForceComponentKind.force,
                    subject_id="body",
                    evidence_refs=EV,
                ),
            )
        ),
    )


def test_two_objectives_for_one_query_are_refused() -> None:
    def objective(identifier: str, value: QueryObjective) -> QueryObjectiveV2:
        return QueryObjectiveV2(
            objective_id=identifier,
            query_id="y1",
            objective=value,
            evidence_refs=EV,
        )

    _expect(
        V2ValidationReason.duplicate_query_objective,
        _augmentation(
            query_objectives=(
                objective("v2_o", QueryObjective.minimum),
                objective("v2_p", QueryObjective.maximum),
            )
        ),
    )


def test_a_contradictory_double_sign_is_refused_rather_than_resolved() -> None:
    # B18: the two readings are mirror-image physics and neither may be chosen.
    _expect(
        V2ValidationReason.contradictory_scalar_encoding,
        _augmentation(
            scalar_encodings=(
                ScalarEncodingV2(
                    encoding_id="v2_e",
                    quantity_id="q1",
                    encoding=ScalarEncoding.contradictory_double_sign,
                    subject_id="body",
                    evidence_refs=EV,
                ),
            )
        ),
    )


def test_a_signed_component_with_no_axis_is_refused() -> None:
    _expect(
        V2ValidationReason.scalar_encoding_without_axis,
        _augmentation(
            reference_frames=(_frame(),),
            scalar_encodings=(
                ScalarEncodingV2(
                    encoding_id="v2_e",
                    quantity_id="q1",
                    encoding=ScalarEncoding.signed_component,
                    subject_id="body",
                    evidence_refs=EV,
                ),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Identifier namespacing
# ---------------------------------------------------------------------------


def test_an_authored_identifier_must_be_namespaced() -> None:
    _expect(
        V2ValidationReason.generated_id_missing_prefix,
        _augmentation(reference_frames=(_frame(frame_id="slope"),)),
    )


def test_an_authored_identifier_may_not_shadow_a_source_one() -> None:
    # The prefix is reserved, so a collision can only happen when the source
    # itself authored a `v2_`-prefixed identifier.  Rare, and refused anyway:
    # a rebinding that silently shadows a source relation is the worst kind.
    with pytest.raises(V2ValidationError) as caught:
        validate_augmentation(
            _augmentation(reference_frames=(_frame(frame_id="v2_slope"),)),
            **{**KNOWN, "authored_ids": ("v2_slope",)},
        )
    assert caught.value.reason is (
        V2ValidationReason.generated_id_collides_with_authored_id
    )


def test_the_reserved_prefix_is_what_the_records_module_declares() -> None:
    assert V2_IDENTIFIER_PREFIX == "v2_"


# ---------------------------------------------------------------------------
# v1 compatibility
# ---------------------------------------------------------------------------


def test_an_empty_augmentation_validates_and_changes_no_draft() -> None:
    empty = CorpusV2AugmentationV1()
    payload = {
        "reference_frames": [],
        "quantities": [{"quantity_id": "q1", "role": "angle"}],
        "queries": [{"query_id": "y1"}],
        "interactions": [],
        "state_conditions": [],
        "geometry": [],
    }

    validate_augmentation(empty)

    assert empty.is_empty is True
    assert project_augmentation(payload, empty) == payload


def test_projection_does_not_mutate_its_input() -> None:
    payload = {"reference_frames": [], "quantities": [], "queries": []}
    before = json.dumps(payload, sort_keys=True)

    project_augmentation(payload, _augmentation(reference_frames=(_frame(),)))

    assert json.dumps(payload, sort_keys=True) == before


def test_a_v1_record_with_no_manifest_entry_is_not_upgraded() -> None:
    record = {"case": "anything", "gold": {"entities": []}}

    migrated = migrate_record(record, AugmentationManifestV1())

    assert migrated.review_status is ReviewStatus.unresolved
    assert migrated.augmented is False
    assert migrated.original_fingerprint == record_fingerprint(record)


def test_an_unresolved_entry_stays_unresolved() -> None:
    record = {"case": "anything"}
    manifest = AugmentationManifestV1(
        entries=(
            AugmentationEntryV1(
                original_fingerprint=record_fingerprint(record),
                review_status=ReviewStatus.unresolved,
                unresolved_reason="the source states no carrier",
                authoring_provenance="test",
            ),
        )
    )

    assert migrate_record(record, manifest).augmented is False


def test_an_unresolved_entry_may_not_carry_a_carrier() -> None:
    with pytest.raises(ValidationError):
        AugmentationEntryV1(
            original_fingerprint="a" * 64,
            review_status=ReviewStatus.unresolved,
            unresolved_reason="nothing stated",
            authoring_provenance="test",
            augmentation=_augmentation(reference_frames=(_frame(),)),
        )


def test_a_manifest_may_bind_one_original_record_once() -> None:
    entry = AugmentationEntryV1(
        original_fingerprint="a" * 64, authoring_provenance="test"
    )

    with pytest.raises(ValidationError):
        AugmentationManifestV1(entries=(entry, entry))


def test_the_original_fingerprint_survives_migration_and_rolls_back() -> None:
    record = {"case": "anything", "gold": {"entities": [{"role": "body"}]}}
    fingerprint = record_fingerprint(record)
    manifest = AugmentationManifestV1(
        entries=(
            AugmentationEntryV1(
                original_fingerprint=fingerprint,
                authoring_provenance="test",
                augmentation=_augmentation(reference_frames=(_frame(),)),
            ),
        )
    )

    migrated = migrate_record(record, manifest)

    assert migrated.original_fingerprint == fingerprint
    assert migrated.augmentation_fingerprint != fingerprint
    assert rollback_to_v1(migrated, {fingerprint: record}) == record


def test_a_mutated_original_is_caught_on_rollback() -> None:
    record = {"case": "anything"}
    fingerprint = record_fingerprint(record)
    migrated = migrate_record(record, AugmentationManifestV1())

    with pytest.raises(MigrationError) as caught:
        rollback_to_v1(migrated, {fingerprint: {"case": "edited"}})

    assert caught.value.reason is MigrationReason.original_record_mutated


def test_key_order_does_not_change_a_records_fingerprint() -> None:
    assert record_fingerprint({"a": 1, "b": 2}) == record_fingerprint({"b": 2, "a": 1})


def test_rebuilding_an_archive_yields_an_identical_digest() -> None:
    records = [{"case": "one"}, {"case": "two"}]
    manifest = AugmentationManifestV1(
        entries=(
            AugmentationEntryV1(
                original_fingerprint=record_fingerprint(records[0]),
                authoring_provenance="test",
                augmentation=_augmentation(reference_frames=(_frame(),)),
            ),
        )
    )

    first = build_candidate_archive(records, manifest)
    second = build_candidate_archive(records, manifest)

    assert archive_digest(first) == archive_digest(second)
    assert first[1].review_status is ReviewStatus.unresolved


# ---------------------------------------------------------------------------
# The manifest cannot see an answer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "answers",
        "expected_answer",
        "numeric",
        "tolerance_abs",
        "reference_expression",
        "future_expected_terminal",
        "expected_failure_codes",
        "sign_convention",
        "solver_output",
    ],
)
def test_a_manifest_naming_an_answer_field_is_refused(field: str) -> None:
    with pytest.raises(MigrationError) as caught:
        assert_manifest_has_no_answer_authority({"entries": [{field: 3.0}]})

    assert caught.value.reason is MigrationReason.manifest_contains_answer_field


def test_the_answer_field_catalogue_is_normalised() -> None:
    # `tolerance_abs` and `toleranceAbs` are one field, not two.
    assert "toleranceabs" in FORBIDDEN_MANIFEST_FIELDS
    with pytest.raises(MigrationError):
        assert_manifest_has_no_answer_authority({"toleranceAbs": 1})


def test_an_answer_field_nested_deep_is_still_refused() -> None:
    with pytest.raises(MigrationError):
        assert_manifest_has_no_answer_authority(
            {"a": [{"b": {"c": [{"numeric": 1.0}]}}]}
        )


def test_a_clean_manifest_passes() -> None:
    manifest = AugmentationManifestV1(
        entries=(
            AugmentationEntryV1(
                original_fingerprint="a" * 64,
                authoring_provenance="test",
                augmentation=_augmentation(reference_frames=(_frame(),)),
            ),
        )
    )

    assert_manifest_has_no_answer_authority(manifest.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Shadow evaluation and score separation
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, terminal: str, verified: int = 0, equations: int = 0) -> None:
        self.terminal = terminal
        self.verified_candidate_count = verified
        self.equation_count = equations
        self.applied_law_ids = ()


def _shadow(baseline: str, shadow: str, augmented: bool = True):
    outcomes = {"blocked": _Result("compiler_failure"), "solved": _Result("solved", 1)}
    payload = {
        "entities": [{"entity_id": "body", "primitive": "particle"}],
        "queries": [
            {
                "query_id": "y1",
                "target": {"role": "velocity", "subject_id": "body"},
            }
        ],
        "quantities": [],
        "reference_frames": [],
        "interactions": [],
        "state_conditions": [],
        "geometry": [],
        "motion_intervals": [],
        "events": [],
        "assumptions": [],
        "constraints": [],
    }
    calls = iter((outcomes[baseline], outcomes[shadow]))
    augmentation = (
        _augmentation(reference_frames=(_frame(),))
        if augmented
        else CorpusV2AugmentationV1()
    )
    return run_shadow_context(
        draft_payload=payload,
        augmentation=augmentation,
        run=lambda _: next(calls),
    )


def test_a_carrier_that_unlocks_a_context_is_reported_as_newly_solved() -> None:
    result = _shadow("blocked", "solved")

    assert result.newly_solved is True
    assert result.regressed is False
    assert rung_delta(result) > 0


def test_a_carrier_that_takes_a_solve_away_is_a_refusal_by_default() -> None:
    result = _shadow("solved", "blocked")

    assert result.regressed is True
    with pytest.raises(ShadowRunRefused):
        assert_no_regression([result])


def test_an_unaugmented_context_that_moves_invalidates_the_run() -> None:
    moved = _shadow("blocked", "solved", augmented=False)

    with pytest.raises(ShadowRunRefused):
        assert_no_unaugmented_movement([moved])


def test_an_unaugmented_context_that_stays_put_is_fine() -> None:
    still = _shadow("blocked", "blocked", augmented=False)

    assert_no_unaugmented_movement([still])
    assert still.augmented is False


def test_a_solved_context_nobody_could_compare_is_neither_correct_nor_wrong() -> None:
    result = _shadow("blocked", "solved")

    assert result.shadow_solved is True
    assert result.shadow_correct is False
    assert result.shadow_wrong is False


def test_the_shadow_scorecard_is_stamped_and_cannot_be_read_as_official() -> None:
    scorecard = build_shadow_scorecard(
        [],
        candidate_archive_sha256="a" * 64,
        augmentation_manifest_sha256="b" * 64,
        original_v1_archive_sha256="c" * 64,
    )
    payload = scorecard_as_dict(scorecard)

    assert payload["score_class"] == SCORE_CLASS
    assert payload["is_official_score"] is False
    assert SCORE_CLASS != OFFICIAL_SCORE_CLASS
    for official_only in (
        "observed_public_score",
        "authority_accepted_score",
        "supported",
        "terminal_mapping",
    ):
        assert official_only not in payload


def test_a_report_that_merges_the_two_classes_is_refused() -> None:
    shadow = scorecard_as_dict(
        build_shadow_scorecard(
            [],
            candidate_archive_sha256="a" * 64,
            augmentation_manifest_sha256="b" * 64,
            original_v1_archive_sha256="c" * 64,
        )
    )

    assert_scores_are_separated({"observed_public_score": "41/81"}, shadow)

    with pytest.raises(ValueError):
        assert_scores_are_separated(
            {"observed_public_score": "41/81", "shadow_correct": 6}, shadow
        )
    with pytest.raises(ValueError):
        assert_scores_are_separated({}, {**shadow, "is_official_score": True})
    with pytest.raises(ValueError):
        assert_scores_are_separated({}, {**shadow, "score_class": "OFFICIAL_V1"})


def test_the_scorecard_carries_every_hash_that_identifies_the_run() -> None:
    scorecard = build_shadow_scorecard(
        [
            ShadowContextResultV1(
                cohort_digest="d" * 64,
                augmented=True,
                carriers_supplied=("reference_frame",),
                baseline_rung="law_not_emitted",
                shadow_rung="solved_and_verified",
                shadow_solved=True,
                shadow_correct=True,
            )
        ],
        candidate_archive_sha256="a" * 64,
        augmentation_manifest_sha256="b" * 64,
        original_v1_archive_sha256="c" * 64,
    )

    assert scorecard.candidate_archive_sha256 == "a" * 64
    assert scorecard.augmentation_manifest_sha256 == "b" * 64
    assert scorecard.original_v1_archive_sha256 == "c" * 64
    assert scorecard.newly_solved == 1
    assert scorecard.cohort_yield_count == 1
    assert scorecard.carrier_coverage == (("reference_frame", 1),)


def test_the_schema_version_names_the_candidate_it_is() -> None:
    assert CORPUS_V2_SCHEMA_VERSION == "dynatutor-ko-corpus-v2.0-candidate"
    assert "candidate" in CORPUS_V2_SCHEMA_VERSION
