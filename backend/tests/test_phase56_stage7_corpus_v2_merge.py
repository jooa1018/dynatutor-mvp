"""The v2 merge contract: fill-only, no-op on identity, fail-closed on conflict.

"Additive" is enforced here, not assumed: an augmentation may fill a field the
source left empty, must merge as a deterministic no-op when it restates the
source exactly, and must be refused with a closed reason code when it would
restate the source differently — including restating it at a different scope,
which is how B16 turned an instant into an interval.

Every attack in this file is one way a carrier could have silently rewritten
v1 runtime meaning before the contract existed.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from evaluation.phase56_stage7.corpus_v2.merge import (
    V2MergeConflict,
    V2MergeConflictReason,
    assert_fill_only_merge,
    detect_merge_conflicts,
    projected_sense_direction,
)
from evaluation.phase56_stage7.corpus_v2.migration import (
    AugmentationEntryV1,
    AugmentationManifestV1,
    MigrationError,
    MigrationReason,
    build_candidate_archive,
    migrate_record,
    record_fingerprint,
)
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import (
    AxisSense,
    ContactSide,
    ContactSideV2,
    CorpusV2AugmentationV1,
    EndpointCondition,
    EndpointConditionV2,
    ConstraintAuthority,
    ConstraintAuthorityV2,
    FrameAxisV2,
    FrameType,
    MotionSense,
    MotionSenseV2,
    QueryObjective,
    QueryObjectiveV2,
    ReferenceFrameV2,
    ScalarEncoding,
    ScalarEncodingV2,
)

EV = ("ev_1",)


def _payload(**overrides: Any) -> dict[str, Any]:
    """A representative projected v1 Draft payload, silent where v1 is silent."""

    base: dict[str, Any] = {
        "entities": [
            {"entity_id": "body", "primitive": "particle"},
            {"entity_id": "ramp", "primitive": "incline"},
        ],
        "reference_frames": [],
        "quantities": [
            {
                "quantity_id": "q1",
                "role": "velocity",
                "subject_id": "body",
                "interval_id": "i1",
                "event_id": None,
                "frame_id": None,
                "direction": None,
                "raw_value": 3.0,
            }
        ],
        "interactions": [
            {
                "interaction_id": "x1",
                "kind": "contact",
                "participant_ids": ["body", "ramp"],
                "frame_id": None,
                "interval_id": "i1",
                "event_id": None,
                "contact_side": None,
            }
        ],
        "state_conditions": [],
        "geometry": [],
        "queries": [{"query_id": "y1", "objective": None}],
    }
    base.update(overrides)
    return base


def _sense(**overrides: Any) -> MotionSenseV2:
    base: dict[str, Any] = dict(
        sense_id="v2_sense",
        sense=MotionSense.along_axis_positive,
        frame_id="v2_slope",
        axis="tangent",
        sign=1,
        quantity_id="q1",
        subject_id="body",
        interval_id="i1",
        evidence_refs=EV,
    )
    base.update(overrides)
    return MotionSenseV2(**base)


def _contact(**overrides: Any) -> ContactSideV2:
    base: dict[str, Any] = dict(
        contact_id="v2_contact",
        interaction_id="x1",
        side=ContactSide.inward,
        normal_frame_id="v2_slope",
        normal_axis="normal",
        subject_id="body",
        evidence_refs=EV,
    )
    base.update(overrides)
    return ContactSideV2(**base)


def _objective(**overrides: Any) -> QueryObjectiveV2:
    base: dict[str, Any] = dict(
        objective_id="v2_objective",
        query_id="y1",
        objective=QueryObjective.minimum,
        evidence_refs=EV,
    )
    base.update(overrides)
    return QueryObjectiveV2(**base)


def _endpoint(**overrides: Any) -> EndpointConditionV2:
    base: dict[str, Any] = dict(
        endpoint_id="v2_endpoint",
        condition=EndpointCondition.comes_to_rest,
        boundary_event_id="e_end",
        subject_id="body",
        evidence_refs=EV,
    )
    base.update(overrides)
    return EndpointConditionV2(**base)


def _expect_conflict(
    reason: V2MergeConflictReason,
    payload: dict[str, Any],
    augmentation: CorpusV2AugmentationV1,
) -> None:
    conflicts = detect_merge_conflicts(payload, augmentation)
    assert reason in conflicts
    with pytest.raises(V2MergeConflict) as caught:
        assert_fill_only_merge(payload, augmentation)
    assert reason in caught.value.reasons
    with pytest.raises(V2MergeConflict):
        # And the projection itself refuses before merging anything.
        project_augmentation(payload, augmentation)


# ---------------------------------------------------------------------------
# Attack 1/2 — query objective
# ---------------------------------------------------------------------------


def test_a_v2_maximum_may_not_overwrite_a_source_minimum() -> None:
    payload = _payload(queries=[{"query_id": "y1", "objective": "minimum"}])
    _expect_conflict(
        V2MergeConflictReason.objective_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            query_objectives=(_objective(objective=QueryObjective.maximum),)
        ),
    )


def test_a_v2_minimum_over_a_source_minimum_is_a_no_op() -> None:
    payload = _payload(queries=[{"query_id": "y1", "objective": "minimum"}])
    augmentation = CorpusV2AugmentationV1(query_objectives=(_objective(),))

    assert detect_merge_conflicts(payload, augmentation) == ()
    merged = project_augmentation(payload, augmentation)

    assert merged["queries"] == payload["queries"]
    # Deterministically: twice gives the same bytes.
    again = project_augmentation(payload, augmentation)
    assert json.dumps(merged, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_a_v2_objective_fills_an_empty_query_and_only_an_empty_query() -> None:
    payload = _payload()
    merged = project_augmentation(
        payload, CorpusV2AugmentationV1(query_objectives=(_objective(),))
    )
    assert merged["queries"][0]["objective"] == "minimum"
    assert payload["queries"][0]["objective"] is None  # input untouched


# ---------------------------------------------------------------------------
# Attack 3 — contact side
# ---------------------------------------------------------------------------


def test_a_v2_outward_may_not_overwrite_a_source_inward() -> None:
    payload = _payload()
    payload["interactions"][0]["contact_side"] = "inward"
    _expect_conflict(
        V2MergeConflictReason.contact_side_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            contact_sides=(_contact(side=ContactSide.outward),)
        ),
    )


def test_an_identical_contact_side_is_a_no_op_that_keeps_the_original() -> None:
    payload = _payload()
    payload["interactions"][0]["contact_side"] = "inward"
    payload["interactions"][0]["frame_id"] = "v2_slope"
    augmentation = CorpusV2AugmentationV1(contact_sides=(_contact(),))

    assert detect_merge_conflicts(payload, augmentation) == ()
    merged = project_augmentation(payload, augmentation)
    assert merged["interactions"] == payload["interactions"]


def test_an_unprojectable_v2_side_conflicts_with_a_stated_engine_side() -> None:
    # `bilateral` has no engine counterpart; over a stated `inward` it is a
    # different statement, not a refinement.
    payload = _payload()
    payload["interactions"][0]["contact_side"] = "inward"
    _expect_conflict(
        V2MergeConflictReason.contact_side_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            contact_sides=(_contact(side=ContactSide.bilateral),)
        ),
    )


# ---------------------------------------------------------------------------
# Attack 4/5/6 — frame binding, direction sign, scope widening
# ---------------------------------------------------------------------------


def test_a_v2_frame_binding_may_not_rebind_a_source_bound_quantity() -> None:
    payload = _payload()
    payload["quantities"][0]["frame_id"] = "frame_a"
    _expect_conflict(
        V2MergeConflictReason.frame_binding_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(motion_senses=(_sense(frame_id="v2_slope"),)),
    )


def test_a_v2_sign_flip_on_a_source_direction_is_refused() -> None:
    payload = _payload()
    payload["quantities"][0]["frame_id"] = "v2_slope"
    payload["quantities"][0]["direction"] = {
        "kind": "axis",
        "frame_id": "v2_slope",
        "axis": "tangent",
        "sign": 1,
    }
    _expect_conflict(
        V2MergeConflictReason.direction_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(motion_senses=(_sense(sign=-1),)),
    )


def test_an_identical_direction_is_a_no_op_that_keeps_the_original() -> None:
    payload = _payload()
    payload["quantities"][0]["frame_id"] = "v2_slope"
    payload["quantities"][0]["direction"] = {
        "kind": "axis",
        "frame_id": "v2_slope",
        "axis": "tangent",
        "sign": 1,
    }
    augmentation = CorpusV2AugmentationV1(motion_senses=(_sense(),))

    assert detect_merge_conflicts(payload, augmentation) == ()
    merged = project_augmentation(payload, augmentation)
    assert merged["quantities"] == payload["quantities"]


def test_an_event_scoped_source_direction_may_not_widen_to_an_interval() -> None:
    payload = _payload()
    payload["quantities"][0]["interval_id"] = None
    payload["quantities"][0]["event_id"] = "e_start"
    _expect_conflict(
        V2MergeConflictReason.motion_scope_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(motion_senses=(_sense(interval_id="i1"),)),
    )


def test_an_interval_scoped_source_direction_may_not_narrow_to_an_event() -> None:
    payload = _payload()  # quantity scoped to interval i1
    _expect_conflict(
        V2MergeConflictReason.motion_scope_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            motion_senses=(_sense(interval_id=None, event_id="e_start"),)
        ),
    )


def test_a_sense_about_a_different_subject_may_not_land_on_this_quantity() -> None:
    payload = _payload()
    _expect_conflict(
        V2MergeConflictReason.motion_scope_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(motion_senses=(_sense(subject_id="ramp"),)),
    )


# ---------------------------------------------------------------------------
# Attack 7/8 — endpoints
# ---------------------------------------------------------------------------


def test_a_v2_condition_differing_at_a_stated_boundary_is_refused() -> None:
    payload = _payload(
        state_conditions=[
            {
                "state_condition_id": "st_1",
                "kind": "boundary",
                "state": "at_rest",
                "subject_id": "body",
                "interval_id": None,
                "event_id": "e_end",
            }
        ]
    )
    _expect_conflict(
        V2MergeConflictReason.endpoint_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            endpoint_conditions=(
                _endpoint(condition=EndpointCondition.contact_loss),
            )
        ),
    )


def test_a_duplicate_identical_endpoint_is_a_deterministic_no_op() -> None:
    payload = _payload(
        state_conditions=[
            {
                "state_condition_id": "st_1",
                "kind": "boundary",
                "state": "at_rest",
                "subject_id": "body",
                "interval_id": None,
                "event_id": "e_end",
            }
        ]
    )
    augmentation = CorpusV2AugmentationV1(endpoint_conditions=(_endpoint(),))

    assert detect_merge_conflicts(payload, augmentation) == ()
    merged = project_augmentation(payload, augmentation)
    assert merged["state_conditions"] == payload["state_conditions"]
    again = project_augmentation(payload, augmentation)
    assert json.dumps(merged, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_a_constraint_restating_a_stated_state_differently_is_refused() -> None:
    payload = _payload(
        state_conditions=[
            {
                "state_condition_id": "st_1",
                "kind": "contact",
                "state": "separated",
                "subject_id": "body",
                "interval_id": "i1",
                "event_id": None,
            }
        ]
    )
    _expect_conflict(
        V2MergeConflictReason.constraint_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            constraint_authorities=(
                ConstraintAuthorityV2(
                    constraint_id="v2_constraint",
                    authority=ConstraintAuthority.contact_maintained,
                    participant_ids=("body", "ramp"),
                    subject_id="body",
                    interval_id="i1",
                    evidence_refs=EV,
                ),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Attack 9 — scalar encodings
# ---------------------------------------------------------------------------


def test_a_magnitude_claim_over_a_signed_source_component_is_refused() -> None:
    payload = _payload()
    payload["quantities"][0]["raw_value"] = -3.0
    _expect_conflict(
        V2MergeConflictReason.scalar_encoding_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            scalar_encodings=(
                ScalarEncodingV2(
                    encoding_id="v2_encoding",
                    quantity_id="q1",
                    encoding=ScalarEncoding.magnitude_with_direction,
                    subject_id="body",
                    evidence_refs=EV,
                ),
            )
        ),
    )


def test_a_signed_component_claim_on_a_different_axis_is_refused() -> None:
    payload = _payload()
    payload["quantities"][0]["direction"] = {
        "kind": "axis",
        "frame_id": "frame_a",
        "axis": "x",
        "sign": 1,
    }
    _expect_conflict(
        V2MergeConflictReason.scalar_encoding_conflicts_with_source,
        payload,
        CorpusV2AugmentationV1(
            scalar_encodings=(
                ScalarEncodingV2(
                    encoding_id="v2_encoding",
                    quantity_id="q1",
                    encoding=ScalarEncoding.signed_component,
                    frame_id="v2_slope",
                    axis="tangent",
                    subject_id="body",
                    evidence_refs=EV,
                ),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Attack 10/11 — identity and preservation
# ---------------------------------------------------------------------------


def test_an_empty_augmentation_is_byte_identical() -> None:
    payload = _payload()
    merged = project_augmentation(payload, CorpusV2AugmentationV1())
    assert json.dumps(merged, sort_keys=True) == json.dumps(payload, sort_keys=True)


def test_every_accepted_augmentation_leaves_v1_meaning_unchanged() -> None:
    # A composite fill: frame appended, objective filled, contact side filled,
    # endpoint appended.  Every field the source stated must survive verbatim;
    # only fields the source left empty may now hold the carrier's value.
    payload = _payload()
    augmentation = CorpusV2AugmentationV1(
        reference_frames=(
            ReferenceFrameV2(
                frame_id="v2_slope",
                frame_type=FrameType.incline_tangent_normal,
                subject_id="ramp",
                axes=(
                    FrameAxisV2(
                        axis="tangent", sense=AxisSense.down_slope, evidence_refs=EV
                    ),
                    FrameAxisV2(
                        axis="normal",
                        sense=AxisSense.away_from_surface,
                        evidence_refs=EV,
                    ),
                ),
                evidence_refs=EV,
            ),
        ),
        query_objectives=(_objective(),),
        contact_sides=(_contact(),),
        endpoint_conditions=(_endpoint(),),
    )

    assert detect_merge_conflicts(payload, augmentation) == ()
    merged = project_augmentation(payload, augmentation)

    for key, original_records in payload.items():
        if not isinstance(original_records, list):
            continue
        merged_records = merged[key]
        assert len(merged_records) >= len(original_records)
        for original, now in zip(original_records, merged_records):
            for field, value in original.items():
                if value is None:
                    continue  # empty in v1; the carrier may have filled it
                assert now[field] == value, (key, field)


def test_conflict_detection_is_decided_before_any_merge() -> None:
    # The conflicting payload is not mutated by the refusal.
    payload = _payload(queries=[{"query_id": "y1", "objective": "minimum"}])
    before = json.dumps(payload, sort_keys=True)
    with pytest.raises(V2MergeConflict):
        project_augmentation(
            payload,
            CorpusV2AugmentationV1(
                query_objectives=(_objective(objective=QueryObjective.maximum),)
            ),
        )
    assert json.dumps(payload, sort_keys=True) == before


def test_conflict_reasons_are_unique_and_canonically_ordered() -> None:
    payload = _payload(queries=[{"query_id": "y1", "objective": "minimum"}])
    payload["interactions"][0]["contact_side"] = "inward"
    conflicts = detect_merge_conflicts(
        payload,
        CorpusV2AugmentationV1(
            query_objectives=(_objective(objective=QueryObjective.maximum),),
            contact_sides=(_contact(side=ContactSide.outward),),
        ),
    )
    assert conflicts == (
        V2MergeConflictReason.objective_conflicts_with_source,
        V2MergeConflictReason.contact_side_conflicts_with_source,
    )
    assert len(set(conflicts)) == len(conflicts)


def test_a_v2_frame_may_not_claim_a_source_frame_identity() -> None:
    payload = _payload(
        reference_frames=[
            {
                "frame_id": "v2_slope",
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [],
            }
        ]
    )
    _expect_conflict(
        V2MergeConflictReason.augmentation_would_overwrite_source,
        payload,
        CorpusV2AugmentationV1(
            reference_frames=(
                ReferenceFrameV2(
                    frame_id="v2_slope",
                    frame_type=FrameType.world_cartesian,
                    subject_id="ramp",
                    axes=(
                        FrameAxisV2(
                            axis="x", sense=AxisSense.up_the_page, evidence_refs=EV
                        ),
                    ),
                    evidence_refs=EV,
                ),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Attack 12 + migration-time enforcement
# ---------------------------------------------------------------------------


def test_migration_refuses_a_conflicting_entry_before_any_archive_exists() -> None:
    record = {"case": "anything"}
    fingerprint = record_fingerprint(record)
    manifest = AugmentationManifestV1(
        entries=(
            AugmentationEntryV1(
                original_fingerprint=fingerprint,
                authoring_provenance="test",
                augmentation=CorpusV2AugmentationV1(
                    query_objectives=(
                        _objective(objective=QueryObjective.maximum),
                    )
                ),
            ),
        )
    )
    payload = _payload(queries=[{"query_id": "y1", "objective": "minimum"}])

    with pytest.raises(MigrationError) as caught:
        migrate_record(record, manifest, draft_payload=payload)
    assert caught.value.reason is MigrationReason.augmentation_conflicts_with_source
    assert caught.value.detail == (
        V2MergeConflictReason.objective_conflicts_with_source,
    )

    with pytest.raises(MigrationError):
        build_candidate_archive(
            [record], manifest, draft_payloads={fingerprint: payload}
        )


def test_a_non_conflicting_entry_still_migrates_with_the_payload_supplied() -> None:
    record = {"case": "anything"}
    fingerprint = record_fingerprint(record)
    manifest = AugmentationManifestV1(
        entries=(
            AugmentationEntryV1(
                original_fingerprint=fingerprint,
                authoring_provenance="test",
                augmentation=CorpusV2AugmentationV1(
                    query_objectives=(_objective(),)
                ),
            ),
        )
    )

    migrated = migrate_record(record, manifest, draft_payload=_payload())
    assert migrated.augmented is True


def test_answer_bearing_manifest_fields_are_still_refused() -> None:
    record = {"case": "anything"}
    manifest_payload = {
        "entries": [
            {
                "original_fingerprint": record_fingerprint(record),
                "authoring_provenance": "test",
                "augmentation": {},
                "expected_answer": 4.43,
            }
        ]
    }
    from evaluation.phase56_stage7.corpus_v2.migration import (
        assert_manifest_has_no_answer_authority,
    )

    with pytest.raises(MigrationError) as caught:
        assert_manifest_has_no_answer_authority(manifest_payload)
    assert caught.value.reason is MigrationReason.manifest_contains_answer_field


def test_the_projected_sense_direction_formula_is_the_merge_formula() -> None:
    # One formula answers both "would this overwrite" and "what is written":
    # `down_slope` with sign +1 and `up_slope` with sign -1 are the same
    # direction, and both compare equal to what the projection writes.
    down = _sense(sense=MotionSense.down_slope, sign=1)
    up_negated = _sense(sense=MotionSense.up_slope, sign=-1)
    assert projected_sense_direction(down) == projected_sense_direction(up_negated)

    payload = _payload()
    merged = project_augmentation(
        payload, CorpusV2AugmentationV1(motion_senses=(down,))
    )
    assert merged["quantities"][0]["direction"] == projected_sense_direction(down)
