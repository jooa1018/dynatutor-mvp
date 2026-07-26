"""Segment-internal event scope: occupancy is typed, boundaries stay owned.

`Event.occurs_in_interval_ids` states that an instant lies strictly inside
an interval.  `MotionInterval.start_event_id`/`end_event_id` remain the sole
boundary authority: an occurrence never becomes an endpoint, an endpoint
never becomes an occurrence, and the contract, the validator, and the
compiler each refuse the promotion independently.

The physics the occurrence scope unlocks is deliberately minimal: by
Fermat's theorem an interior extremum of a differentiable trajectory has a
zero derivative, so a proven-interior `highest_point`/`lowest_point` — with
source authority, exact subject and interval scope, a unique inertial
gravity frame, no impulsive structure, and exactly one candidate unknown —
licenses the vertical velocity component zero.  Turnaround and rest stay
boundary-only.

Every fixture is independently authored.  None reads a case ID, family,
split, expected terminal, or expected answer in any path under test.
"""

from __future__ import annotations

import pytest

from test_phase56_stage7_event_boundary_semantics import (
    PROBLEM_TEXT,
    _closed_draft,
    _emissions,
    _law_context,
    _record,
)

from engine.mechanics.compiler import MechanicsCompiler
from engine.mechanics.compiler.compiler import (
    authorize_validated_mechanics_ir,
)
from engine.mechanics.contracts import Event, MechanicsProblemDraftV1
from engine.mechanics.normalization import normalize_draft
from engine.mechanics.validation import validate_draft
from evaluation.phase56_stage7.complete_profile_application import (
    close_projected_draft,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.event_boundary_derivation import (
    EventBoundaryOutcome,
    derive_event_boundaries,
)
from evaluation.phase56_stage7.lane_b_authority import (
    build_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    project_case_to_draft,
)

BOUNDARY_LAW_IDS = frozenset(
    {
        "event_vertical_extremum_velocity",
        "event_turnaround_axis_velocity",
        "event_comes_to_rest_velocity",
    }
)

APEX_QUOTE = "최고점에 도달"


def _internal_apex_record(
    *,
    top_kind: str = "highest_point",
    top_segment: str = "fall",
    top_subjects: tuple[str, ...] = ("stone",),
    extra_events: tuple[dict, ...] = (),
    **gold_overrides,
) -> dict:
    """The semantics fixture reshaped: `top` occurs inside a closed span.

    The interval's boundaries are `go` and `land`; `top` is the apex strictly
    between them, carrying its own source authority.
    """

    record = _record(**gold_overrides)
    gold = record["gold"]
    gold["motion_segments"] = [
        {
            "role": "fall",
            "order": 1,
            "actor_roles": ["stone"],
            "motion_model": "projectile_free_flight",
            "relevance": "target",
            "start_event_role": "go",
            "end_event_role": "land",
        }
    ]
    gold["events"] = [
        {
            "role": "go",
            "kind": "release",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        },
        {
            "role": "top",
            "kind": top_kind,
            "subject_roles": list(top_subjects),
            "segment_role": top_segment,
            "evidence_quote": APEX_QUOTE,
        },
        {
            "role": "land",
            "kind": "finish",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        },
        *extra_events,
    ]
    return record


def _project(record: dict):
    projection = project_case_to_draft(PublicCorpusCaseV1(**record))
    assert projection.projected, projection.sanitized_reason
    return projection


def _maybe_closed_draft(projection):
    """Close the Draft when a profile forms; keep it as-is when none does.

    Several refusal controls deliberately break the closure profile's
    applicability — the wall under test must hold either way.
    """

    bundle = build_lane_b_authority_bundle(projection)
    result = close_projected_draft(
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    return result.draft


def _boundary_emissions(projection, draft):
    return tuple(
        emission
        for emission in _emissions(projection, draft)
        if emission.rule.law_id in BOUNDARY_LAW_IDS
    )


# --------------------------------------------------------------------------
# Occupancy is projected as typed scope, never as a boundary
# --------------------------------------------------------------------------


def test_an_internal_event_carries_typed_occupancy_and_no_boundary():
    projection = _project(_internal_apex_record())
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    interval = projection.draft.motion_intervals[0]
    assert top.interval_ids == []
    assert top.occurs_in_interval_ids == ["fall"]
    assert interval.start_event_id == "go"
    assert interval.end_event_id == "land"
    assert "top" in projection.segment_internal_event_ids


def test_an_event_with_no_segment_scope_claims_nothing():
    record = _internal_apex_record(top_segment="fall")
    for event in record["gold"]["events"]:
        if event["role"] == "top":
            event["segment_role"] = None
    projection = _project(record)
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.interval_ids == []
    assert top.occurs_in_interval_ids == []
    derived = derive_event_boundaries(_closed_draft(projection)[1])
    assert derived.outcome is EventBoundaryOutcome.not_applied


def test_a_subject_outside_the_interval_earns_no_occupancy():
    record = _internal_apex_record(top_subjects=("ground",))
    projection = _project(record)
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.occurs_in_interval_ids == []
    derived = derive_event_boundaries(_closed_draft(projection)[1])
    assert derived.outcome is EventBoundaryOutcome.not_applied


# --------------------------------------------------------------------------
# The interior extremum, fully proven, licenses exactly the vertical zero
# --------------------------------------------------------------------------


@pytest.mark.parametrize("top_kind", ["highest_point", "lowest_point"])
def test_a_proven_interior_extremum_licenses_the_vertical_zero(top_kind):
    projection = _project(_internal_apex_record(top_kind=top_kind))
    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    assert derived.outcome is EventBoundaryOutcome.applied
    (created,) = derived.created_quantity_ids
    (quantity,) = [
        q for q in derived.draft.quantities if q.quantity_id == created
    ]
    assert quantity.event_id == "top"
    assert quantity.interval_id == "fall"
    assert quantity.component.value == "y"

    emissions = _boundary_emissions(projection, derived.draft)
    assert [e.rule.law_id for e in emissions] == [
        "event_vertical_extremum_velocity"
    ]
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert set(top.evidence_refs) & set(emissions[0].source_evidence_ids)


@pytest.mark.parametrize("top_kind", ["turnaround", "comes_to_rest"])
def test_interior_mode_stays_extremum_only(top_kind):
    projection = _project(_internal_apex_record(top_kind=top_kind))
    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    assert derived.outcome is EventBoundaryOutcome.not_applied
    assert not _boundary_emissions(projection, derived.draft)


def test_an_open_span_licenses_no_interior_zero():
    record = _internal_apex_record()
    record["gold"]["motion_segments"][0]["end_event_role"] = None
    record["gold"]["events"] = [
        event
        for event in record["gold"]["events"]
        if event["role"] != "land"
    ]
    projection = _project(record)
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.occurs_in_interval_ids == ["fall"]
    derived = derive_event_boundaries(_maybe_closed_draft(projection))
    assert derived.outcome is EventBoundaryOutcome.not_applied


def test_an_impulsive_instant_inside_the_span_breaks_the_smooth_zero():
    record = _internal_apex_record(
        extra_events=(
            {
                "role": "hit",
                "kind": "collision_start",
                "subject_roles": ["stone"],
                "segment_role": "fall",
                "evidence_quote": None,
            },
        )
    )
    projection = _project(record)
    derived = derive_event_boundaries(_closed_draft(projection)[1])
    assert derived.outcome is EventBoundaryOutcome.not_applied
    assert not _boundary_emissions(projection, derived.draft)


def test_a_contact_carrying_span_licenses_no_interior_zero():
    record = _internal_apex_record()
    record["gold"]["relations"] = [
        {
            "role": "slide",
            "kind": "slides_on",
            "participant_roles": ["stone", "ground"],
            "segment_role": "fall",
        }
    ]
    projection = _project(record)
    derived = derive_event_boundaries(_maybe_closed_draft(projection))
    # Two independent walls hold: the derivation refuses the contact-carrying
    # span, and the lane itself blocks at a reader-confirmation terminal
    # before any law could run.
    assert derived.outcome is EventBoundaryOutcome.not_applied
    bundle = build_lane_b_authority_bundle(projection)
    normalization = normalize_draft(
        PROBLEM_TEXT,
        derived.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert not normalization.accepted


def test_an_apex_of_another_interval_licenses_nothing_here():
    record = _internal_apex_record()
    gold = record["gold"]
    gold["motion_segments"] = gold["motion_segments"] + [
        {
            "role": "roll",
            "order": 2,
            "actor_roles": ["stone"],
            "motion_model": "constant_acceleration_1d",
            "relevance": "context",
            "start_event_role": "land",
            "end_event_role": None,
        }
    ]
    for event in gold["events"]:
        if event["role"] == "top":
            event["segment_role"] = "roll"
    projection = _project(record)
    (top,) = [e for e in projection.draft.events if e.event_id == "top"]
    assert top.occurs_in_interval_ids == ["roll"]
    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    # The apex occupies `roll`; the closed free-flight structure lives on
    # `fall`.  Nothing may leak across: no unknown, no emission.
    assert derived.outcome is EventBoundaryOutcome.not_applied
    assert not _boundary_emissions(projection, derived.draft)


def test_a_non_inertial_gravity_frame_licenses_no_interior_zero():
    projection = _project(_internal_apex_record())
    _, draft = _closed_draft(projection)
    payload = draft.model_dump(mode="json", warnings="none")
    for frame in payload["reference_frames"]:
        frame["translating_with_entity_id"] = "ground"
    tampered = MechanicsProblemDraftV1.model_validate(payload)
    derived = derive_event_boundaries(tampered)
    assert derived.outcome is EventBoundaryOutcome.not_applied


def test_two_gravity_frames_license_no_interior_zero():
    projection = _project(_internal_apex_record())
    _, draft = _closed_draft(projection)
    payload = draft.model_dump(mode="json", warnings="none")
    (world,) = [
        frame["frame_id"] for frame in payload["reference_frames"]
    ]
    payload["reference_frames"].append(
        {
            **[
                frame
                for frame in payload["reference_frames"]
                if frame["frame_id"] == world
            ][0],
            "frame_id": "frm_second_world",
        }
    )
    gravity = [
        item
        for item in payload["interactions"]
        if item["kind"] == "gravity"
    ][0]
    payload["interactions"].append(
        {
            **gravity,
            "interaction_id": "ixn_second_gravity",
            "frame_id": "frm_second_world",
        }
    )
    tampered = MechanicsProblemDraftV1.model_validate(payload)
    derived = derive_event_boundaries(tampered)
    assert derived.outcome is EventBoundaryOutcome.not_applied


def test_duplicate_candidate_velocities_refuse_the_emission():
    projection = _project(_internal_apex_record())
    _, draft = _closed_draft(projection)
    derived = derive_event_boundaries(draft)
    assert derived.outcome is EventBoundaryOutcome.applied
    payload = derived.draft.model_dump(mode="json", warnings="none")
    (created,) = derived.created_quantity_ids
    twin = [
        dict(item)
        for item in payload["quantities"]
        if item["quantity_id"] == created
    ][0]
    twin["quantity_id"] = "qty_twin_apex"
    twin["symbol_id"] = "sym_twin_apex"
    payload["quantities"].append(twin)
    payload["symbols"].append(
        {
            "symbol_id": "sym_twin_apex",
            "quantity_id": "qty_twin_apex",
            "dimension": dict(twin["dimension"]),
            "shape": "scalar",
        }
    )
    tampered = MechanicsProblemDraftV1.model_validate(payload)
    assert not _boundary_emissions(projection, tampered)


# --------------------------------------------------------------------------
# Promotion is refused at every layer
# --------------------------------------------------------------------------


def test_the_contract_refuses_an_interval_that_is_both_bounded_and_occupied():
    with pytest.raises(ValueError):
        Event(
            event_id="ev",
            kind="highest_point",
            subject_ids=["stone"],
            interval_ids=["fall"],
            occurs_in_interval_ids=["fall"],
        )
    with pytest.raises(ValueError):
        Event(
            event_id="ev",
            kind="highest_point",
            subject_ids=["stone"],
            occurs_in_interval_ids=["fall", "fall"],
        )


def test_the_validator_refuses_a_forged_interiority():
    projection = _project(_internal_apex_record())
    payload = projection.draft.model_dump(mode="json", warnings="none")
    # The attack: the interval adopts the internal apex as its endpoint while
    # the occurrence claim stays — interiority and boundary at once.
    for interval in payload["motion_intervals"]:
        interval["end_event_id"] = "top"
    draft = MechanicsProblemDraftV1.model_validate(payload)
    report = validate_draft(PROBLEM_TEXT, draft)
    assert not report.accepted
    assert any(
        issue.code.value == "interval_event_invalid"
        for issue in report.issues
    )


def test_the_validator_refuses_an_occupancy_by_a_foreign_subject():
    projection = _project(_internal_apex_record())
    payload = projection.draft.model_dump(mode="json", warnings="none")
    for event in payload["events"]:
        if event["event_id"] == "top":
            event["subject_ids"] = ["ground"]
    draft = MechanicsProblemDraftV1.model_validate(payload)
    report = validate_draft(PROBLEM_TEXT, draft)
    assert not report.accepted
    assert any(
        issue.code.value == "interval_event_invalid"
        for issue in report.issues
    )


def test_tampering_an_occurrence_into_a_boundary_fails_the_pipeline_closed():
    projection = _project(_internal_apex_record())
    payload = projection.draft.model_dump(mode="json", warnings="none")
    # The attack: restate the occupancy as boundary membership without the
    # interval declaring the endpoint.
    for event in payload["events"]:
        if event["event_id"] == "top":
            event["interval_ids"] = ["fall"]
            event["occurs_in_interval_ids"] = []
    draft = MechanicsProblemDraftV1.model_validate(payload)
    bundle = build_lane_b_authority_bundle(projection)
    normalization = normalize_draft(
        PROBLEM_TEXT,
        draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert normalization.accepted and normalization.ir is not None
    # Boundary reciprocity is the compiler's wall: a membership claim the
    # interval's own endpoints never declared is a typed invalid binding,
    # not a compilable graph.
    authorization = authorize_validated_mechanics_ir(normalization.ir)
    compiled = MechanicsCompiler().compile(
        normalization.ir,
        validated_ir_authorization=authorization,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert not compiled.compilable
    assert any(
        issue.code.value == "invalid_binding" for issue in compiled.issues
    )


# --------------------------------------------------------------------------
# Scope restoration, order invariance, and the calculation fingerprint
# --------------------------------------------------------------------------


def test_records_scoped_to_the_internal_instant_keep_their_interval():
    projection = _project(_internal_apex_record())
    (query,) = projection.draft.queries
    assert query.target.event_id == "top"
    assert query.target.interval_id == "fall"


def test_occurrence_order_never_changes_the_calculation_fingerprint():
    projection = _project(_internal_apex_record())
    _, draft = _closed_draft(projection)
    bundle = build_lane_b_authority_bundle(projection)
    payload = draft.model_dump(mode="json", warnings="none")
    payload["motion_intervals"] = payload["motion_intervals"] + [
        {
            "interval_id": "hover",
            "order": 2,
            "subject_ids": ["stone"],
            "frame_id": None,
            "start_event_id": None,
            "end_event_id": None,
            "evidence_refs": [],
        }
    ]
    fingerprints = []
    for order in (["fall", "hover"], ["hover", "fall"]):
        variant = dict(payload)
        variant["events"] = [
            {**event, "occurs_in_interval_ids": list(order)}
            if event["event_id"] == "top"
            else event
            for event in payload["events"]
        ]
        draft_variant = MechanicsProblemDraftV1.model_validate(variant)
        normalization = normalize_draft(
            PROBLEM_TEXT,
            draft_variant,
            approved_assumption_ids=bundle.approved_assumption_ids,
            authorized_assumptions=bundle.authorization_map(),
        )
        assert normalization.accepted and normalization.ir is not None
        fingerprints.append(normalization.calculation_fingerprint)
    assert fingerprints[0] == fingerprints[1]


def test_gold_tampering_never_changes_the_occurrence_scope():
    baseline_record = _internal_apex_record()
    tampered_record = _internal_apex_record()
    tampered_record["case_id"] = "renamed_identity"
    tampered_record["family"] = "renamed_family"
    tampered_record["gold"]["answers"] = []
    baseline = _project(baseline_record)
    tampered = _project(tampered_record)
    assert (
        baseline.draft.model_dump_json() == tampered.draft.model_dump_json()
    )
    (top,) = [e for e in baseline.draft.events if e.event_id == "top"]
    assert top.occurs_in_interval_ids == ["fall"]
