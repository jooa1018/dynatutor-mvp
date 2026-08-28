"""Phase 57 generation-two source-only continuation manifest contracts."""

from __future__ import annotations

import hashlib

import pytest

from evaluation.phase56_stage7.corpus_v2.campaign_seal import (
    PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_NAME_V1,
    PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V1,
    PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V2,
    resolve_campaign_seal,
)
from evaluation.phase56_stage7.corpus_v2.records import (
    ConstraintAuthority,
    ContactSide,
    EndpointCondition,
    FrameType,
    MotionSense,
)
from evaluation.phase56_stage7.corpus_v2.supplemental_campaign import (
    build_supplemental_manifest,
    source_only_case,
    supplemental_manifest_body,
)
from evaluation.phase57_reproducible.continuation_manifest import (
    EXPECTED_COHORT_SIZE,
    EXPECTED_SELECTED_CONTEXTS,
    Phase57ContinuationCohort,
    Phase57ContinuationManifestReason,
    Phase57ContinuationManifestRefused,
    build_phase57_continuation_manifest,
    discover_phase57_continuation_cohorts,
    phase57_continuation_manifest_body,
)
from evaluation.phase57_reproducible.contracts import (
    PHASE57_CAMPAIGN_SEAL_NAME,
    PHASE57_CONTINUATION_MANIFEST_DIGEST,
    PHASE57_CONTINUATION_MANIFEST_FILE_SHA256,
    PHASE57_CONTINUATION_SELECTION_DIGEST,
)
from evaluation.phase57_reproducible.fixtures import load_public_fixture_cases


EXPECTED_POSITIONS = (
    0,
    1,
    2,
    18,
    19,
    20,
    21,
    22,
    23,
    27,
    28,
    29,
    33,
    34,
    35,
    54,
    55,
    56,
    72,
    73,
    74,
    78,
    79,
    80,
)


def _entry_by_position():
    cases = load_public_fixture_cases()
    built = build_phase57_continuation_manifest(cases)
    return built, dict(
        zip(built.selection.selected_positions, built.manifest.entries, strict=True)
    )


def test_generation_one_manifest_and_seal_remain_exactly_frozen() -> None:
    cases = load_public_fixture_cases()
    baseline = build_supplemental_manifest(cases)
    body = supplemental_manifest_body(baseline.manifest)

    assert len(baseline.manifest.entries) == 9
    assert baseline.manifest.digest == (
        "32aa3ce51e3006e533913b2f822251d22dccba2a379a35008f19e7a7e1aef7cd"
    )
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == (
        "946cd6364669c123341d54999a87a468bc22f7260ea2b8500ddee267878bcd3a"
    )
    assert resolve_campaign_seal(PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_NAME_V1) == (
        PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V1
    )


def test_generation_two_selects_eight_exact_three_case_cohorts() -> None:
    cases = load_public_fixture_cases()
    built = build_phase57_continuation_manifest(cases)

    assert built.selection.selected_positions == EXPECTED_POSITIONS
    assert len(built.selection.selected_positions) == EXPECTED_SELECTED_CONTEXTS
    assert tuple(cohort for cohort, _ in built.selection.by_cohort) == tuple(
        Phase57ContinuationCohort
    )
    assert all(
        len(positions) == EXPECTED_COHORT_SIZE
        for _, positions in built.selection.by_cohort
    )


def test_generation_two_discovery_refuses_source_population_drift() -> None:
    cases = load_public_fixture_cases()
    baseline = build_supplemental_manifest(cases)
    source = tuple(source_only_case(case) for case in cases)

    with pytest.raises(Phase57ContinuationManifestRefused) as raised:
        discover_phase57_continuation_cohorts(
            (*source, source[21]),
            baseline_positions=baseline.selection.selected_positions,
        )

    assert raised.value.reason is (
        Phase57ContinuationManifestReason.cohort_cardinality_mismatch
    )


def test_generation_two_manifest_identity_is_frozen_and_answer_free() -> None:
    cases = load_public_fixture_cases()
    built = build_phase57_continuation_manifest(cases)
    body = phase57_continuation_manifest_body(built.manifest)

    assert len(built.manifest.entries) == EXPECTED_SELECTED_CONTEXTS
    assert built.manifest.digest == PHASE57_CONTINUATION_MANIFEST_DIGEST
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == (
        PHASE57_CONTINUATION_MANIFEST_FILE_SHA256
    )
    assert built.selection_identity_digest == PHASE57_CONTINUATION_SELECTION_DIGEST
    assert "answer" not in body.casefold()
    assert "case_id" not in body.casefold()
    assert body.endswith("\n") and not body.endswith("\n\n")


def test_new_source_carriers_are_exactly_evidenced_and_scoped() -> None:
    _, entries = _entry_by_position()

    horizontal = entries[21].augmentation
    assert len(horizontal.source_quotes) == 2
    assert tuple(frame.frame_type for frame in horizontal.reference_frames) == (
        FrameType.world_cartesian,
        FrameType.surface_tangent_normal,
    )
    assert len(horizontal.motion_senses) == 1
    assert horizontal.motion_senses[0].sense is MotionSense.along_axis_positive
    assert horizontal.motion_senses[0].subject_id == "object"
    assert horizontal.motion_senses[0].interval_id == "motion_1"

    table = entries[54].augmentation
    assert len(table.source_quotes) == 1
    assert tuple(frame.frame_type for frame in table.reference_frames) == (
        FrameType.world_cartesian,
        FrameType.surface_tangent_normal,
    )
    assert table.motion_senses == ()

    incline = entries[33].augmentation
    assert len(incline.source_quotes) == 1
    assert tuple(frame.frame_type for frame in incline.reference_frames) == (
        FrameType.world_cartesian,
        FrameType.incline_tangent_normal,
    )
    assert len(incline.motion_senses) == 1
    assert incline.motion_senses[0].subject_id == "object"
    assert incline.motion_senses[0].interval_id == "motion_1"
    assert incline.motion_senses[0].quantity_id is None

    spring = entries[72].augmentation
    assert len(spring.endpoint_conditions) == 1
    endpoint = spring.endpoint_conditions[0]
    assert endpoint.condition is EndpointCondition.reaches_natural_length
    assert endpoint.subject_id == "spring"
    assert endpoint.interval_id == "motion_1"
    assert endpoint.boundary_event_id == "finish"

    vertical = entries[78].augmentation
    assert len(vertical.contact_sides) == 1
    assert vertical.contact_sides[0].side is ContactSide.inside_track
    assert vertical.contact_sides[0].interaction_id == "rel_contact"
    assert len(vertical.constraint_authorities) == 1
    authority = vertical.constraint_authorities[0]
    assert authority.authority is ConstraintAuthority.contact_maintained
    assert authority.interval_id == "motion_1"
    assert set(authority.participant_ids) == {"object", "track"}
    assert len(vertical.endpoint_conditions) == 1
    assert vertical.endpoint_conditions[0].condition is EndpointCondition.contact_limit
    assert vertical.endpoint_conditions[0].boundary_event_id == "top"


def test_active_phase57_seal_is_generation_two_and_v1_remains_resolvable() -> None:
    assert PHASE57_CAMPAIGN_SEAL_NAME.endswith("-v2")
    assert resolve_campaign_seal(PHASE57_CAMPAIGN_SEAL_NAME) == (
        PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V2
    )
    assert PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V2.augmentation_manifest_digest == (
        PHASE57_CONTINUATION_MANIFEST_DIGEST
    )
    assert PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V2.augmentation_manifest_file_sha256 == (
        PHASE57_CONTINUATION_MANIFEST_FILE_SHA256
    )
    assert PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V1.name != (
        PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V2.name
    )
