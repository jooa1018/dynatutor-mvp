"""Semantic preservation, including every meaning this evaluator has lost before.

The audit's job is to be believed when it says a meaning survived and when it
says one did not, so the tests come in three groups:

* the classifier's own contract — what each `PreservationStatus` means, and in
  particular that a meaning carried by a *different* record is not a loss;
* the source-contract omissions — the carriers the v1 corpus has no field for,
  each pinned so that adding one becomes a deliberate change;
* the historical regressions — one per meaning a revoked package manufactured,
  asserting the source still cannot supply it, so a future closure that
  produces it is producing it from nowhere.

Everything is synthetic.  No test reads the public archive.
"""

from __future__ import annotations

from typing import Any

import pytest

from evaluation.phase56_stage7.semantic_preservation import (
    CARRIER_SOURCE_FIELDS,
    FIELD_SPECS,
    SEMANTIC_PRESERVATION_VERSION,
    CarrierShape,
    ConsumptionStatus,
    EngineCarrier,
    PipelineStage,
    PreservationStatus,
    SourceFieldCategory,
    build_carrier_omissions,
    build_semantic_preservation_report,
    report_as_dict,
    trace_context,
)


# ---------------------------------------------------------------------------
# Synthetic source records, shaped like the corpus's own
# ---------------------------------------------------------------------------


class _Record:
    def __init__(self, **fields: Any) -> None:
        for name, value in fields.items():
            setattr(self, name, value)

    def __getattr__(self, name: str) -> Any:  # unset optional fields read as None
        return None


def _gold(**overrides: Any) -> _Record:
    base: dict[str, Any] = {
        "entities": [
            _Record(role="카트알파", kind="카트알파", label="A"),
            _Record(role="램프베타", kind="incline", label="B"),
        ],
        "motion_segments": [
            _Record(
                role="seg1",
                order=1,
                actor_roles=["카트알파"],
                motion_model="sliding_on_incline",
                start_event_role="ev_start",
                end_event_role="ev_end",
            )
        ],
        "events": [
            _Record(role="ev_start", kind="start", subject_roles=["카트알파"], segment_role="seg1"),
            _Record(role="ev_end", kind="finish", subject_roles=["카트알파"], segment_role="seg1"),
        ],
        "explicit_facts": [
            _Record(
                role="v0",
                semantic_key="velocity",
                raw_value=3.0,
                raw_unit="m/s",
                subject_role="카트알파",
                segment_role="seg1",
                event_role=None,
                temporal_role="initial",
                direction="downward",
                occurrence_index=0,
            )
        ],
        "relations": [
            _Record(role="r1", kind="slides_on", participant_roles=["카트알파", "램프베타"], segment_role="seg1")
        ],
        "assumption_proposals": [
            _Record(
                role="a1",
                kind="constant_gravity",
                subject_role="카트알파",
                segment_role="seg1",
                server_value_only=True,
            )
        ],
        "queries": [
            _Record(
                role="q1",
                output_key="final_velocity",
                subject_role="카트알파",
                segment_role="seg1",
                component="magnitude",
                event_role=None,
            )
        ],
    }
    base.update(overrides)
    return _Record(**base)


def _draft(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "entities": [
            {"entity_id": "e1", "primitive": "rigid_body"},
            {"entity_id": "e2", "primitive": "incline"},
        ],
        "reference_frames": [],
        "motion_intervals": [
            {
                "interval_id": "i1",
                "order": 1,
                "subject_ids": ["e1"],
                "start_event_id": "v1",
                "end_event_id": "v2",
            }
        ],
        "events": [
            {"event_id": "v1", "kind": "start", "subject_ids": ["e1"]},
            {"event_id": "v2", "kind": "finish", "subject_ids": ["e1"]},
        ],
        "quantities": [
            {
                "quantity_id": "q1",
                "role": "velocity",
                "subject_id": "e1",
                "interval_id": "i1",
                "raw_value": 3.0,
                "raw_unit": "m/s",
                "direction": {"kind": "semantic", "direction": "downward"},
            }
        ],
        "geometry": [
            {"relation_id": "g1", "kind": "slides_on", "participant_ids": ["e1", "e2"], "interval_id": "i1"}
        ],
        "interactions": [],
        "assumptions": [
            {
                "assumption_id": "a1",
                "kind": "constant_gravity",
                "subject_id": "e1",
                "interval_id": "i1",
                "disposition": "accepted",
            }
        ],
        "queries": [
            {
                "query_id": "y1",
                "target": {
                    "role": "velocity",
                    "subject_id": "e1",
                    "interval_id": "i1",
                    "component": "magnitude",
                },
            }
        ],
    }
    base.update(overrides)
    return base


def _status_of(trace: Any, category: SourceFieldCategory) -> PreservationStatus:
    for item in trace:
        if item.category is category:
            return item.status
    raise AssertionError(f"{category} not traced")


def _traced(trace: Any, category: SourceFieldCategory):
    for item in trace:
        if item.category is category:
            return item
    raise AssertionError(f"{category} not traced")


# ---------------------------------------------------------------------------
# The classifier's contract
# ---------------------------------------------------------------------------


def test_every_source_field_category_is_traced() -> None:
    trace = trace_context(_gold(), _draft())

    assert {item.category for item in trace} == set(SourceFieldCategory)
    assert len(FIELD_SPECS) == len(SourceFieldCategory)


def test_a_field_carried_one_for_one_is_preserved() -> None:
    trace = trace_context(_gold(), _draft())

    assert _status_of(trace, SourceFieldCategory.relation_kind) is (
        PreservationStatus.preserved_normalized
    )
    assert _status_of(trace, SourceFieldCategory.fact_raw_value) is (
        PreservationStatus.preserved_normalized
    )


def test_a_stated_direction_is_read_from_the_binding_the_contract_uses() -> None:
    # `DirectionBinding.direction`, not a `name` field the contract lacks.
    # Reading the wrong field reported every stated direction as dropped.
    trace = trace_context(_gold(), _draft())
    traced = _traced(trace, SourceFieldCategory.fact_direction)

    assert traced.occurrences == 1
    assert traced.carried_to_draft == 1
    assert traced.status is PreservationStatus.preserved_normalized


def test_a_direction_the_source_declines_to_state_is_not_counted_as_lost() -> None:
    gold = _gold(
        explicit_facts=[
            _Record(
                role="m",
                semantic_key="mass",
                raw_value=2.0,
                raw_unit="kg",
                subject_role="카트알파",
                segment_role="seg1",
                temporal_role="timeless",
                direction="not_applicable",
                occurrence_index=0,
            )
        ]
    )
    draft = _draft(
        quantities=[
            {
                "quantity_id": "q1",
                "role": "mass",
                "subject_id": "e1",
                "raw_value": 2.0,
                "raw_unit": "kg",
            }
        ]
    )

    traced = _traced(trace_context(gold, draft), SourceFieldCategory.fact_direction)

    assert traced.occurrences == 0
    assert traced.status is not PreservationStatus.dropped_unsafely


def test_a_meaning_another_record_carries_is_not_a_drop() -> None:
    # An event's segment is carried by the interval's boundary fields, and a
    # motion model selects a profile rather than being carried at all.
    trace = trace_context(_gold(), _draft())

    for category in (
        SourceFieldCategory.event_segment_role,
        SourceFieldCategory.segment_motion_model,
        SourceFieldCategory.fact_temporal_role,
    ):
        assert _status_of(trace, category) is (
            PreservationStatus.preserved_with_scope_change
        ), category
        assert _traced(trace, category).contexts_with_loss == 0


def test_a_field_that_is_genuinely_short_is_a_drop() -> None:
    gold = _gold(
        relations=[
            _Record(role="r1", kind="slides_on", participant_roles=["카트알파", "램프베타"], segment_role="seg1"),
            _Record(role="r2", kind="contact_with", participant_roles=["카트알파", "램프베타"], segment_role="seg1"),
        ]
    )

    traced = _traced(trace_context(gold, _draft()), SourceFieldCategory.relation_kind)

    assert traced.status is PreservationStatus.dropped_unsafely
    assert traced.first_failing_stage is PipelineStage.draft_projection
    assert traced.contexts_with_loss == 1


def test_a_field_nothing_holds_and_nothing_reads_is_a_contract_omission() -> None:
    traced = _traced(
        trace_context(_gold(), _draft()), SourceFieldCategory.fact_occurrence_index
    )

    assert traced.status is PreservationStatus.omitted_because_v1_has_no_carrier
    assert traced.first_failing_stage is PipelineStage.source_contract
    assert traced.consumption is ConsumptionStatus.not_consumed
    # An omission is not a projection defect, so it is not a context loss.
    assert traced.contexts_with_loss == 0


def test_a_policy_that_creates_records_is_not_a_loss() -> None:
    draft = _draft(
        events=[
            {"event_id": "v1", "kind": "start", "subject_ids": ["e1"]},
            {"event_id": "v2", "kind": "finish", "subject_ids": ["e1"]},
            {"event_id": "v3", "kind": "reaches_condition", "subject_ids": ["e1"]},
        ]
    )

    traced = _traced(trace_context(_gold(), draft), SourceFieldCategory.event_kind)

    assert traced.status is PreservationStatus.derived_by_approved_policy
    assert traced.contexts_with_loss == 0


def test_a_rejected_projection_is_refused_rather_than_traced_as_total_loss() -> None:
    with pytest.raises(ValueError):
        trace_context(_gold(), None)


# ---------------------------------------------------------------------------
# The source-contract omissions
# ---------------------------------------------------------------------------


def test_the_v1_source_contract_cannot_state_a_reference_frame() -> None:
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.reference_frame] == ()

    (omission,) = [
        item
        for item in build_carrier_omissions()
        if item.carrier is EngineCarrier.reference_frame
    ]

    assert omission.status is PreservationStatus.omitted_because_v1_has_no_carrier
    assert omission.has_source_carrier is False


@pytest.mark.parametrize(
    "carrier",
    [
        EngineCarrier.reference_frame,
        EngineCarrier.frame_axis_direction,
        EngineCarrier.angle_reference_datum,
        EngineCarrier.motion_sense,
        EngineCarrier.contact_side,
        EngineCarrier.query_objective,
        EngineCarrier.quantity_frame_binding,
    ],
)
def test_each_missing_carrier_is_pinned(carrier: EngineCarrier) -> None:
    # Adding a source field for any of these is a corpus-contract change and
    # must be a deliberate one, so each is asserted rather than assumed.
    assert CARRIER_SOURCE_FIELDS[carrier] == ()


def test_the_carriers_the_contract_does_state_are_recorded_as_such() -> None:
    for carrier in (
        EngineCarrier.constraint_record,
        EngineCarrier.interaction_participant,
        EngineCarrier.quantity_point_binding,
        EngineCarrier.state_condition,
        EngineCarrier.endpoint_condition,
    ):
        assert CARRIER_SOURCE_FIELDS[carrier], carrier
        (record,) = [
            item for item in build_carrier_omissions() if item.carrier is carrier
        ]
        assert record.status is not PreservationStatus.omitted_because_v1_has_no_carrier


def test_the_endpoint_vocabulary_is_recorded_as_partial_not_absent() -> None:
    # `comes_to_rest` and `highest_point` are sayable; natural length is not.
    # Recording the carrier as wholly absent would have overstated the gap.
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.endpoint_condition] == (
        SourceFieldCategory.event_kind,
    )


# ---------------------------------------------------------------------------
# Historical regressions — one per meaning a revoked package manufactured
# ---------------------------------------------------------------------------


def test_b15_a_generic_surface_still_cannot_be_stated_horizontal() -> None:
    # B15 read `surface` + no incline + no angle as a stated zero slope, then
    # wrote world axes from it.  The source has no frame field, so there is
    # nothing a closure could read instead of inventing one.
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.reference_frame] == ()
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.frame_axis_direction] == ()


def test_b16_a_world_direction_still_cannot_become_a_slope_sense() -> None:
    # B16 converted a world `downward` into a slope-tangent sign.  A sense
    # needs an axis of a stated frame, and the source can state neither.
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.motion_sense] == ()
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.quantity_frame_binding] == ()


def test_b16_an_instant_still_cannot_widen_to_an_interval_by_itself() -> None:
    # A fact scoped to an event must not arrive scoped to the whole interval.
    gold = _gold(
        explicit_facts=[
            _Record(
                role="v0",
                semantic_key="velocity",
                raw_value=3.0,
                raw_unit="m/s",
                subject_role="카트알파",
                segment_role=None,
                event_role="ev_start",
                temporal_role="initial",
                direction="downward",
                occurrence_index=0,
            )
        ]
    )
    widened = _draft(
        quantities=[
            {
                "quantity_id": "q1",
                "role": "velocity",
                "subject_id": "e1",
                "interval_id": "i1",
                "raw_value": 3.0,
                "raw_unit": "m/s",
                "direction": {"kind": "semantic", "direction": "downward"},
            }
        ]
    )

    trace = trace_context(gold, widened)

    # The event binding the source stated did not arrive, and the audit says so
    # rather than reporting the interval binding as if it were the same thing.
    assert _traced(trace, SourceFieldCategory.fact_event_role).carried_to_draft == 0
    assert _status_of(trace, SourceFieldCategory.fact_event_role) is (
        PreservationStatus.preserved_with_scope_change
    )


def test_b12_a_contact_side_still_cannot_be_stated() -> None:
    # B12 needed inside-track versus outside-track and the source has no field
    # for it, so the side could only ever have come from somewhere else.
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.contact_side] == ()


def test_b12_a_minimum_speed_objective_still_cannot_be_stated() -> None:
    # The corpus names an output `minimum_speed`; a name is not an objective.
    # `Query.objective` exists in the engine and has no source field, so
    # reading the output name as an objective is reading a label as physics.
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.query_objective] == ()
    assert SourceFieldCategory.query_output_key in set(SourceFieldCategory)
    output_key_spec = [
        spec
        for spec in FIELD_SPECS
        if spec.category is SourceFieldCategory.query_output_key
    ][0]
    # It is traced as a query *role*, never as an objective.
    assert output_key_spec.shape is CarrierShape.carried


def test_b17_a_natural_length_endpoint_still_cannot_be_stated() -> None:
    # The event-kind vocabulary has `comes_to_rest` and `highest_point` and no
    # member for a spring at natural length, so B17's endpoint has no carrier.
    from evaluation.phase56_stage7.semantic_preservation import (
        CARRIER_SOURCE_FIELDS as table,
    )

    assert table[EngineCarrier.endpoint_condition] == (SourceFieldCategory.event_kind,)
    gold = _gold(
        events=[
            _Record(role="ev_start", kind="start", subject_roles=["카트알파"], segment_role="seg1"),
            _Record(role="ev_end", kind="finish", subject_roles=["카트알파"], segment_role="seg1"),
        ]
    )
    # A generic `finish` says when, never what holds there.
    kinds = [event.kind for event in gold.events]
    assert "finish" in kinds
    assert not {"reaches_natural_length", "zero_spring_deformation"} & set(kinds)


def test_b10_a_common_rotation_centre_still_has_no_constraint_of_its_own() -> None:
    # The source states constraints only through the assumption vocabulary, and
    # that vocabulary has no member naming a shared instantaneous centre.
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.constraint_record] == (
        SourceFieldCategory.assumption_kind,
    )


def test_b18_a_signed_scalar_still_needs_an_axis_the_source_cannot_state() -> None:
    # Which encoding wins depends on an axis orientation, and the source can
    # state neither a frame nor an axis binding for a quantity.
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.quantity_frame_binding] == ()
    assert CARRIER_SOURCE_FIELDS[EngineCarrier.frame_axis_direction] == ()


# ---------------------------------------------------------------------------
# The aggregate
# ---------------------------------------------------------------------------


def test_the_report_totals_agree_with_its_traces() -> None:
    report = build_semantic_preservation_report(
        [trace_context(_gold(), _draft()), trace_context(_gold(), _draft())]
    )

    assert report.context_count == 2
    assert report.version == SEMANTIC_PRESERVATION_VERSION
    assert len(report.fields) == len(SourceFieldCategory)
    assert sum(count for _, count in report.status_counts) == len(report.fields)
    assert report.source_contract_omission_count == sum(
        1 for carrier in report.carriers if not carrier.source_fields
    )


def test_one_context_losing_a_field_turns_the_category_red_and_says_how_many() -> None:
    lossy_gold = _gold(
        relations=[
            _Record(role="r1", kind="slides_on", participant_roles=["카트알파", "램프베타"], segment_role="seg1"),
            _Record(role="r2", kind="contact_with", participant_roles=["카트알파", "램프베타"], segment_role="seg1"),
        ]
    )

    report = build_semantic_preservation_report(
        [
            trace_context(_gold(), _draft()),
            trace_context(_gold(), _draft()),
            trace_context(lossy_gold, _draft()),
        ]
    )
    traced = [
        item
        for item in report.fields
        if item.category is SourceFieldCategory.relation_kind
    ][0]

    assert traced.status is PreservationStatus.dropped_unsafely
    assert traced.contexts_with_loss == 1
    assert report.projection_loss_count >= 1


def test_the_report_digest_is_deterministic_and_content_sensitive() -> None:
    one = build_semantic_preservation_report([trace_context(_gold(), _draft())])
    same = build_semantic_preservation_report([trace_context(_gold(), _draft())])
    two = build_semantic_preservation_report(
        [trace_context(_gold(), _draft()), trace_context(_gold(), _draft())]
    )

    assert one.digest == same.digest
    assert one.digest != two.digest


def test_the_published_report_carries_no_case_material() -> None:
    from evaluation.phase56_stage7.redaction import assert_privacy_safe_artifact

    payload = report_as_dict(
        build_semantic_preservation_report([trace_context(_gold(), _draft())])
    )

    assert_privacy_safe_artifact(payload)
    text = repr(payload)
    for forbidden in ("카트알파", "램프베타", "3.0", "m/s", "case_id", "expected_answer"):
        assert forbidden not in text


def test_no_report_field_can_hold_a_source_string() -> None:
    from evaluation.phase56_stage7.semantic_preservation import (
        FieldPreservationV1,
        SemanticPreservationReportV1,
    )

    for model in (SemanticPreservationReportV1, FieldPreservationV1):
        for name in model.model_fields:
            for part in ("problem", "quote", "answer", "case_id", "family", "label"):
                assert part not in name, f"{model.__name__}.{name}"


def test_an_empty_audit_is_a_report_rather_than_an_error() -> None:
    report = build_semantic_preservation_report([])

    assert report.context_count == 0
    assert report.fields == ()
    # The contract omissions do not depend on having traced anything.
    assert report.source_contract_omission_count == 7
