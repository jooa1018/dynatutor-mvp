"""Stage 7: applying a complete profile is one transaction or nothing.

The hazard this guards is not a crash.  It is a Draft that reaches the runtime
carrying half a free body — a weight with no normal, a rope pulling on one side
— because records were attached one at a time.  Such a Draft still compiles and
still produces an answer, and the answer is wrong.

So the applier builds a whole new Draft and swaps it in only once it validates.
On any failure the caller keeps the exact Draft it passed in, and no record from
the attempt survives anywhere.  A plan computed against a different Draft is
refused rather than re-planned, because re-planning inside the applier would
make planning a mutation.

Fixtures are independently authored.
"""

from __future__ import annotations

import pytest

from evaluation.phase56_stage7.complete_profile import (
    CompleteProfilePlanV1,
    CompleteProfilePrerequisiteV1,
    PlanDisposition,
    PrerequisiteDisposition,
    PrerequisiteKind,
    ProfileId,
    draft_structure_fingerprint,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    DERIVED_FRAME_ID,
    OBSERVER_FRAME_ID,
    WORLD_FRAME_ID,
    ApplicationOutcome,
    apply_complete_profile,
    close_projected_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionTerminal,
    project_case_to_draft,
)
from support.phase56_stage7_corpus_fixtures import build_case


IMPULSE_TEXT = (
    "운반대의 질량은 3 kg 이고 처음 속도는 오른쪽으로 5 m/s 이다. "
    "짧은 시간 동안 왼쪽으로 9 N*s 의 충격량을 받았다. "
    "오른쪽을 양으로 볼 때 x 방향 나중 속도를 구하시오."
)


def _fact(role, key, value, unit, quote, subject, **overrides) -> dict:
    fact = {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": "motion_1",
        "event_role": None,
        "temporal_role": "timeless",
        "direction": "not_applicable",
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }
    fact.update(overrides)
    return fact


def _impulse_gold(**overrides) -> dict:
    gold = {
        "entities": [{"role": "cart", "kind": "block", "label": "운반대"}],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["cart"],
                "motion_model": "impulse_interval",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["cart"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            },
            {
                "role": "finish",
                "kind": "finish",
                "subject_roles": ["cart"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            },
        ],
        "explicit_facts": [
            _fact("mass", "mass", "3", "kg", "질량은 3 kg", "cart"),
            _fact(
                "v0",
                "initial_velocity",
                "5",
                "m/s",
                "처음 속도는 오른쪽으로 5 m/s",
                "cart",
                temporal_role="initial",
                direction="right",
            ),
            _fact(
                "j",
                "impulse",
                "9",
                "N*s",
                "왼쪽으로 9 N*s 의 충격량",
                "cart",
                temporal_role="interval",
                direction="left",
            ),
        ],
        "relations": [],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "final_velocity",
                "subject_role": "cart",
                "segment_role": "motion_1",
                "component": "x",
                "event_role": "finish",
            }
        ],
        "expected_failure_codes": [],
    }
    gold.update(overrides)
    return gold


def _case(problem_text: str, gold: dict) -> PublicCorpusCaseV1:
    record = build_case(
        index=9,
        split="public_dev",
        family="constant_acceleration_1d",
        future_terminal="accepted",
        with_answer=False,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = problem_text
    record["gold"] = {**record["gold"], **gold, "answers": []}
    return PublicCorpusCaseV1(**record)


def _draft(**overrides):
    projection = project_case_to_draft(_case(IMPULSE_TEXT, _impulse_gold(**overrides)))
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection.draft


def _complete_plan(draft, profile_id: ProfileId = ProfileId.impulse_momentum):
    """A plan whose verdict is `complete`, so the transaction is authorised.

    Built directly rather than measured, because the point under test is the
    transaction, not the census verdict.
    """

    return CompleteProfilePlanV1(
        profile_id=profile_id,
        disposition=PlanDisposition.complete,
        prerequisites=(
            CompleteProfilePrerequisiteV1(
                prerequisite_id="frame_signed_axis",
                kind=PrerequisiteKind.reference_frame,
                disposition=PrerequisiteDisposition.server_derivable,
            ),
        ),
        draft_fingerprint=draft_structure_fingerprint(draft),
    )


# --------------------------------------------------------------------------
# The transaction
# --------------------------------------------------------------------------


def test_a_complete_plan_creates_every_record_together():
    draft = _draft()
    assert draft.reference_frames == []

    result = apply_complete_profile(_complete_plan(draft), draft)
    assert result.outcome is ApplicationOutcome.applied

    closed = result.draft
    frames = [item for item in closed.reference_frames if item.frame_id == DERIVED_FRAME_ID]
    assert len(frames) == 1
    assert {item.axis.value for item in frames[0].axes} == {"x", "y"}

    bound = {
        item.quantity_id: item
        for item in closed.quantities
        if item.quantity_id in set(result.rebound_quantity_ids)
    }
    # The frame, the axis, and every component binding arrive as one step.
    assert set(bound) == set(result.rebound_quantity_ids)
    for quantity in bound.values():
        assert quantity.component.value == "x"
        assert quantity.frame_id == DERIVED_FRAME_ID
    assert closed.queries[0].target.component.value == "x"
    assert closed.queries[0].target.frame_id == DERIVED_FRAME_ID


def test_the_applier_never_changes_a_value():
    draft = _draft()
    before = {
        item.quantity_id: (item.raw_value, item.raw_unit) for item in draft.quantities
    }
    closed = apply_complete_profile(_complete_plan(draft), draft).draft
    after = {
        item.quantity_id: (item.raw_value, item.raw_unit) for item in closed.quantities
    }
    assert after == before


def test_a_stated_direction_keeps_its_sign_on_the_derived_axis():
    draft = _draft()
    closed = apply_complete_profile(_complete_plan(draft), draft).draft
    signs = {
        item.quantity_id: item.direction.sign
        for item in closed.quantities
        if item.direction is not None and item.direction.kind == "axis"
    }
    # `right` is the positive sense of the axis it named; `left` is the negative.
    assert signs["qty_v0"] == 1
    assert signs["qty_j"] == -1


def test_the_generated_unknown_stays_unknown():
    draft = _draft()
    closed = apply_complete_profile(_complete_plan(draft), draft).draft
    unknown = [item for item in closed.quantities if item.raw_value is None]
    assert unknown
    for item in unknown:
        assert item.raw_value is None
        assert item.raw_unit is None
        # Existence is derived; the direction the solver must find is not.
        assert item.direction is None


def test_the_source_draft_is_never_mutated():
    draft = _draft()
    before = draft.model_dump(mode="json", warnings="none")
    apply_complete_profile(_complete_plan(draft), draft)
    assert draft.model_dump(mode="json", warnings="none") == before


# --------------------------------------------------------------------------
# Refusals: nothing partial ever escapes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "disposition",
    [
        PlanDisposition.needs_confirmation,
        PlanDisposition.insufficient_information,
        PlanDisposition.unsupported,
        PlanDisposition.not_applicable,
    ],
)
def test_a_plan_that_did_not_complete_creates_nothing(disposition):
    draft = _draft()
    plan = _complete_plan(draft).model_copy(update={"disposition": disposition})
    result = apply_complete_profile(plan, draft)
    assert result.outcome is ApplicationOutcome.not_applied
    assert result.draft is draft
    assert result.draft.reference_frames == []
    assert result.created_record_ids == ()


def test_a_plan_from_another_draft_is_refused_not_replanned():
    draft = _draft()
    other = _draft(
        entities=[{"role": "cart", "kind": "particle", "label": "운반대"}]
    )
    plan = _complete_plan(other)
    result = apply_complete_profile(plan, draft)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.sanitized_reason == "plan_draft_mismatch"
    assert result.draft is draft
    assert result.draft.reference_frames == []


def test_a_profile_without_an_enabled_transaction_creates_nothing():
    """A profile whose partial-attachment hazards have no controls yet."""

    draft = _draft()
    plan = _complete_plan(draft, ProfileId.spring_vibration_deferred)
    result = apply_complete_profile(plan, draft)
    assert result.outcome is ApplicationOutcome.not_applied
    assert result.sanitized_reason == "profile_not_enabled"
    assert result.draft.reference_frames == []


def test_two_axis_families_abandon_the_whole_transaction():
    gold = _impulse_gold()
    gold["explicit_facts"][2]["direction"] = "upward"
    gold["explicit_facts"][2]["evidence_quote"] = "위쪽으로 9 N*s 의 충격량"
    text = IMPULSE_TEXT.replace("왼쪽으로 9 N*s", "위쪽으로 9 N*s")
    draft = project_case_to_draft(_case(text, gold)).draft
    result = apply_complete_profile(_complete_plan(draft), draft)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft is draft
    # No frame, no rebinding, nothing half-applied.
    assert result.draft.reference_frames == []
    assert result.rebound_quantity_ids == ()
    assert all(
        item.direction is None or item.direction.kind == "semantic"
        for item in result.draft.quantities
    )


def test_no_stated_direction_abandons_the_whole_transaction():
    gold = _impulse_gold()
    for fact in gold["explicit_facts"]:
        fact["direction"] = "not_applicable"
    gold["queries"][0]["component"] = "magnitude"
    draft = project_case_to_draft(_case(IMPULSE_TEXT, gold)).draft
    result = apply_complete_profile(_complete_plan(draft), draft)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft.reference_frames == []


def test_the_applier_is_deterministic():
    draft = _draft()
    first = apply_complete_profile(_complete_plan(draft), draft).draft
    second = apply_complete_profile(_complete_plan(draft), draft).draft
    assert draft_structure_fingerprint(first) == draft_structure_fingerprint(second)


def test_the_measured_plan_for_this_shape_does_not_authorise_a_transaction():
    """The census verdict, not the hand-built plan, is what gates production.

    The endpoint velocities are event-scoped and the solver's static-boundary
    waiver does not recognise this graph, so the measured plan is `unsupported`
    and the transaction never runs on a real corpus context.
    """

    projection = project_case_to_draft(_case(IMPULSE_TEXT, _impulse_gold()))
    measured = plan_complete_profile(
        ProfileId.impulse_momentum,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert measured.disposition is PlanDisposition.unsupported
    result = apply_complete_profile(measured, projection.draft)
    assert result.outcome is ApplicationOutcome.not_applied
    assert result.draft.reference_frames == []


# --------------------------------------------------------------------------
# A deferral-only profile: build the frame so the refusal becomes precise
# --------------------------------------------------------------------------


RELATIVE_TEXT = (
    "관측 대차가 오른쪽으로 1.4 m/s^2 로 가속한다. "
    "대차에서 보면 부품은 오른쪽으로 0.6 m/s^2 로 가속한다. "
    "지면 기준 부품의 x 방향 가속도를 구하시오."
)


def _relative_gold(**overrides) -> dict:
    gold = {
        "entities": [
            {"role": "observer", "kind": "reference_frame", "label": "관측 대차"},
            {"role": "part", "kind": "particle", "label": "부품"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["observer", "part"],
                "motion_model": "relative_motion",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": None,
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["observer", "part"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact(
                "carrier",
                "acceleration",
                "1.4",
                "m/s^2",
                "오른쪽으로 1.4 m/s^2",
                "observer",
                direction="right",
            ),
            _fact(
                "relative",
                "acceleration",
                "0.6",
                "m/s^2",
                "오른쪽으로 0.6 m/s^2",
                "part",
                direction="right",
            ),
        ],
        "relations": [
            {
                "role": "observed",
                "kind": "moves_relative_to",
                "participant_roles": ["part", "observer"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "part",
                "segment_role": "motion_1",
                "component": "x",
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }
    gold.update(overrides)
    return gold


def _relative_projection(**overrides):
    projection = project_case_to_draft(
        _case(RELATIVE_TEXT, _relative_gold(**overrides))
    )
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


def test_a_declared_observer_becomes_a_parented_translating_frame_pair():
    projection = _relative_projection()
    plan = plan_complete_profile(
        ProfileId.relative_translating_frame,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    # The readout is deferred, but every record the model needs resolves.
    assert plan.disposition is PlanDisposition.unsupported
    assert plan.structurally_complete

    result = apply_complete_profile(plan, projection.draft)
    assert result.outcome is ApplicationOutcome.applied
    frames = {item.frame_id: item for item in result.draft.reference_frames}
    assert set(frames) == {WORLD_FRAME_ID, OBSERVER_FRAME_ID}
    # Neither frame alone is recognised: the pair is the unit of work.
    world, moving = frames[WORLD_FRAME_ID], frames[OBSERVER_FRAME_ID]
    assert world.frame_type.value == "cartesian_2d"
    assert world.parent_frame_id is None
    assert moving.frame_type.value == "translating"
    assert moving.parent_frame_id == WORLD_FRAME_ID
    assert moving.translating_with_entity_id == "observer"
    assert moving.rotating_about_point_id is None


def test_relative_and_carrier_motion_land_in_different_frames():
    projection = _relative_projection()
    plan = plan_complete_profile(
        ProfileId.relative_translating_frame,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    closed = apply_complete_profile(plan, projection.draft).draft
    by_id = {item.quantity_id: item for item in closed.quantities}
    # What the source states about the body is relative to the observer it named.
    assert by_id["qty_relative"].frame_id == OBSERVER_FRAME_ID
    # What it states about the observer is that observer's own motion.
    assert by_id["qty_carrier"].frame_id == WORLD_FRAME_ID
    # The question is the body's motion as the world sees it.
    assert by_id["qty_unknown_q1"].frame_id == WORLD_FRAME_ID
    assert by_id["qty_unknown_q1"].direction is None
    assert by_id["qty_unknown_q1"].raw_value is None


def test_a_deferral_only_profile_never_delivers_an_answer():
    """Building the frame makes the refusal precise; it cannot produce a value."""

    projection = _relative_projection()
    result = run_lane_b_case(projection, execution_token=deterministic_token(0))
    assert result.terminal is LaneBTerminal.verified_unsupported
    assert "translating_frame_relative_acceleration_deferred" in result.compiler_codes
    assert result.answer_value_si is None
    assert result.candidate_count == 0
    assert result.verified_candidate_count == 0


def test_two_declared_observers_build_nothing():
    gold = _relative_gold()
    gold["entities"] = [
        *gold["entities"],
        {"role": "observer_2", "kind": "reference_frame", "label": "다른 관측계"},
    ]
    gold["motion_segments"][0]["actor_roles"] = ["observer", "part", "observer_2"]
    gold["events"][0]["subject_roles"] = ["observer", "part", "observer_2"]
    projection = project_case_to_draft(_case(RELATIVE_TEXT, gold))
    plan = plan_complete_profile(
        ProfileId.relative_translating_frame,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert not plan.structurally_complete
    result = apply_complete_profile(plan, projection.draft)
    assert result.outcome is ApplicationOutcome.not_applied
    assert result.draft.reference_frames == []


def test_closure_applies_at_most_one_profile():
    projection = _relative_projection()
    first = close_projected_draft(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert first.applied
    assert first.profile_id is ProfileId.relative_translating_frame
    # Closing an already-closed Draft must not stack a second frame pair.
    second = close_projected_draft(
        first.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert len(second.draft.reference_frames) == len(first.draft.reference_frames)


def test_closure_leaves_an_unclosable_draft_exactly_as_projected():
    draft = _draft()
    before = draft.model_dump(mode="json", warnings="none")
    result = close_projected_draft(draft)
    assert not result.applied
    assert result.draft.model_dump(mode="json", warnings="none") == before


# --------------------------------------------------------------------------
# A magnitude is not a signed component
# --------------------------------------------------------------------------


def test_a_source_stated_magnitude_is_never_restamped_onto_an_axis():
    """A directionless statement carries no sign, and must not acquire one.

    The source said this speed has no direction, which is a statement about a
    magnitude.  Binding it to `+x` would hand the solver a sign the source never
    gave, so the quantity keeps exactly what the source wrote.
    """

    gold = _impulse_gold()
    gold["explicit_facts"] = [
        *gold["explicit_facts"],
        _fact(
            "speed",
            "velocity",
            "4",
            "m/s",
            "속력은 4 m/s",
            "cart",
            direction="not_applicable",
        ),
    ]
    text = IMPULSE_TEXT.replace("x 방향 나중 속도를", "속력은 4 m/s 이다. x 방향 나중 속도를")
    draft = project_case_to_draft(_case(text, gold)).draft
    magnitude_before = [
        item
        for item in draft.quantities
        if item.component.value == "magnitude" and item.raw_value is not None
    ]
    assert magnitude_before

    closed = apply_complete_profile(_complete_plan(draft), draft).draft
    by_id = {item.quantity_id: item for item in closed.quantities}
    for original in magnitude_before:
        after = by_id[original.quantity_id]
        assert after.component.value == "magnitude"
        assert after.direction is None
        assert after.frame_id == original.frame_id


def test_a_magnitude_question_is_never_rewritten_into_a_signed_one():
    """Changing the query's component would change what was asked."""

    gold = _impulse_gold()
    gold["queries"][0]["component"] = "magnitude"
    draft = project_case_to_draft(_case(IMPULSE_TEXT, gold)).draft
    result = apply_complete_profile(_complete_plan(draft), draft)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft.queries[0].target.component.value == "magnitude"
    assert result.draft.reference_frames == []


def test_a_relative_magnitude_question_is_never_rewritten_either():
    gold = _relative_gold()
    gold["queries"][0]["component"] = "magnitude"
    projection = project_case_to_draft(_case(RELATIVE_TEXT, gold))
    plan = plan_complete_profile(
        ProfileId.relative_translating_frame,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    result = apply_complete_profile(plan, projection.draft)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft.queries[0].target.component.value == "magnitude"
    assert result.draft.reference_frames == []


# --------------------------------------------------------------------------
# Generated IDs collide against every Draft namespace, in every transaction
# --------------------------------------------------------------------------


def test_an_impulse_frame_id_colliding_outside_its_own_namespace_abandons():
    """The derived frame ID against an authored *entity* ID, not a frame."""

    draft = _draft()
    tampered = draft.model_copy(
        update={
            "entities": [
                *draft.entities,
                draft.entities[0].model_copy(
                    update={"entity_id": DERIVED_FRAME_ID}
                ),
            ]
        }
    )
    result = apply_complete_profile(_complete_plan(tampered), tampered)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft is tampered
    assert result.draft.reference_frames == []
    assert result.created_record_ids == ()


def test_a_relative_frame_id_colliding_outside_its_own_namespace_abandons():
    """The observer frame ID against an authored *event* ID, not a frame."""

    projection = _relative_projection()
    draft = projection.draft
    tampered = draft.model_copy(
        update={
            "events": [
                *draft.events,
                draft.events[0].model_copy(
                    update={"event_id": OBSERVER_FRAME_ID}
                ),
            ]
        }
    )
    plan = plan_complete_profile(
        ProfileId.relative_translating_frame,
        tampered,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    result = apply_complete_profile(plan, tampered)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft is tampered
    assert result.draft.reference_frames == []
    assert result.created_record_ids == ()
