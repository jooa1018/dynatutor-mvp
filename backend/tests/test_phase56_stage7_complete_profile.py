"""Stage 7: the complete-profile plan contract and the feasibility census.

The plan is the gate every closure step must clear.  These tests pin the three
properties that make it safe to build on:

* planning reads and never writes — the Draft is byte-identical afterwards;
* a generated unknown asserts only that a *symbol* must exist, never a value;
* the verdict is a single closed disposition, and the least recoverable failure
  wins so an unsupported capability is never reported as a mere gap.

The census on top of it reports counts only.  A test asserts that its records
are structurally incapable of carrying a case ID, family, split, problem text,
expected terminal, expected answer, or gold graph.

Every fixture here is independently authored.
"""

from __future__ import annotations

import pytest

from evaluation.phase56_stage7.complete_profile import (
    CompleteProfileCensusV1,
    CompleteProfileFeasibilityV1,
    CompleteProfilePlanV1,
    PlanDisposition,
    PrerequisiteDisposition,
    ProfileId,
    build_complete_profile_census,
    draft_structure_fingerprint,
    plan_complete_profile,
    plan_every_profile,
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
        index=7,
        split="public_dev",
        family="constant_acceleration_1d",
        future_terminal="accepted",
        with_answer=False,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = problem_text
    record["gold"] = {**record["gold"], **gold, "answers": []}
    return PublicCorpusCaseV1(**record)


def _impulse_draft(**overrides):
    projection = project_case_to_draft(_case(IMPULSE_TEXT, _impulse_gold(**overrides)))
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


# --------------------------------------------------------------------------
# The plan never writes
# --------------------------------------------------------------------------


def test_planning_leaves_the_draft_byte_identical():
    projection = _impulse_draft()
    before = draft_structure_fingerprint(projection.draft)
    before_payload = projection.draft.model_dump(mode="json", warnings="none")
    plans = plan_every_profile(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert draft_structure_fingerprint(projection.draft) == before
    assert projection.draft.model_dump(mode="json", warnings="none") == before_payload
    # Every plan records the Draft it actually saw.
    assert {plan.draft_fingerprint for plan in plans} == {before}


def test_a_plan_is_immutable():
    projection = _impulse_draft()
    plan = plan_complete_profile(
        ProfileId.impulse_momentum,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    with pytest.raises(Exception):
        plan.disposition = PlanDisposition.complete  # type: ignore[misc]
    with pytest.raises(Exception):
        plan.prerequisites = ()  # type: ignore[misc]


def test_every_profile_is_planned_exactly_once():
    projection = _impulse_draft()
    plans = plan_every_profile(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert [plan.profile_id for plan in plans] == list(ProfileId)


# --------------------------------------------------------------------------
# Dispositions
# --------------------------------------------------------------------------


def test_a_recognised_impulse_profile_closes_through_server_derivation():
    projection = _impulse_draft()
    plan = plan_complete_profile(
        ProfileId.impulse_momentum,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    # The axis is derived, not stated, so this is not a source-grounded close.
    assert plan.uses_server_derivation
    dispositions = {item.disposition for item in plan.prerequisites}
    assert PrerequisiteDisposition.missing not in dispositions
    assert PrerequisiteDisposition.ambiguous not in dispositions
    assert PrerequisiteDisposition.unsupported not in dispositions
    # A generated unknown asserts existence only.
    generated = [
        item
        for item in plan.prerequisites
        if item.disposition is PrerequisiteDisposition.generated_unknown
    ]
    assert generated
    assert all(item.kind.value == "unknown_symbol" for item in generated)


def test_a_profile_whose_shape_is_absent_is_not_applicable():
    projection = _impulse_draft()
    plan = plan_complete_profile(
        ProfileId.collision_restitution,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.not_applicable
    assert plan.prerequisites == ()


def test_two_axis_families_are_an_ambiguity_not_a_gap():
    gold = _impulse_gold()
    gold["explicit_facts"][2]["direction"] = "upward"
    gold["explicit_facts"][2]["evidence_quote"] = "위쪽으로 9 N*s 의 충격량"
    text = IMPULSE_TEXT.replace("왼쪽으로 9 N*s", "위쪽으로 9 N*s")
    projection = project_case_to_draft(_case(text, gold))
    plan = plan_complete_profile(
        ProfileId.impulse_momentum,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.needs_confirmation


def test_no_stated_direction_is_a_gap_not_an_ambiguity():
    gold = _impulse_gold()
    for fact in gold["explicit_facts"]:
        fact["direction"] = "not_applicable"
    gold["explicit_facts"][1]["evidence_quote"] = "처음 속도는 오른쪽으로 5 m/s"
    gold["queries"][0]["component"] = "magnitude"
    projection = project_case_to_draft(_case(IMPULSE_TEXT, gold))
    plan = plan_complete_profile(
        ProfileId.impulse_momentum,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.insufficient_information


def test_an_unsupported_capability_outranks_a_missing_prerequisite():
    """A deferred readout must never be reported as merely incomplete."""

    text = (
        "부품의 질량은 4 kg 이고 용수철 상수는 400 N/m 이다. "
        "마찰은 없다고 본다. 진동 주기를 구하시오."
    )
    gold = {
        "entities": [
            {"role": "part", "kind": "block", "label": "부품"},
            {"role": "coil", "kind": "spring", "label": "용수철"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["part", "coil"],
                "motion_model": "spring_oscillation",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "release",
                "subject_roles": ["part", "coil"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact("mass", "mass", "4", "kg", "질량은 4 kg", "part"),
            _fact(
                "k", "spring_constant", "400", "N/m", "용수철 상수는 400 N/m", "coil"
            ),
        ],
        "relations": [
            {
                "role": "spring_link",
                "kind": "attached_to_spring",
                "participant_roles": ["part", "coil"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": [
            {
                "role": "no_friction",
                "kind": "frictionless",
                "subject_role": "part",
                "segment_role": "motion_1",
                "supporting_quote": "마찰은 없다고 본다",
                "server_value_only": True,
            }
        ],
        "queries": [
            {
                "role": "q1",
                "output_key": "period",
                "subject_role": "part",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }
    projection = project_case_to_draft(_case(text, gold))
    plan = plan_complete_profile(
        ProfileId.spring_vibration_deferred,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.unsupported


def test_a_lone_force_is_never_a_resultant_without_a_typed_authority():
    """The corpus contract carries no resultant authority, so this never closes."""

    text = "부품의 질량은 5 kg 이고 힘의 크기는 30 N 이다. 가속도의 크기를 구하시오."
    gold = {
        "entities": [{"role": "part", "kind": "particle", "label": "부품"}],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["part"],
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": None,
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["part"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact("mass", "mass", "5", "kg", "질량은 5 kg", "part"),
            _fact("f", "force", "30", "N", "힘의 크기는 30 N", "part"),
        ],
        "relations": [],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "part",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }
    projection = project_case_to_draft(_case(text, gold))
    plan = plan_complete_profile(
        ProfileId.explicit_resultant_force,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is not PlanDisposition.complete
    authority = [
        item
        for item in plan.prerequisites
        if item.prerequisite_id == "authority_force_is_resultant"
    ]
    assert len(authority) == 1
    assert authority[0].disposition is PrerequisiteDisposition.missing


def test_a_blocking_ambiguity_blocks_every_profile_from_completing():
    gold = _impulse_gold()
    gold["explicit_facts"][2]["direction"] = "unspecified"
    projection = project_case_to_draft(_case(IMPULSE_TEXT, gold))
    plans = plan_every_profile(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert not [plan for plan in plans if plan.complete]


# --------------------------------------------------------------------------
# Census: counts only
# --------------------------------------------------------------------------


def test_the_census_reports_one_row_per_profile_and_sums_to_the_context_count():
    projection = _impulse_draft()
    plans = plan_every_profile(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    census = build_complete_profile_census([plans, plans, plans])
    assert census.context_count == 3
    assert [row.profile_id for row in census.profiles] == list(ProfileId)
    for row in census.profiles:
        total = (
            row.complete_source_grounded
            + row.complete_with_closed_server_derivations
            + row.needs_confirmation
            + row.insufficient_information
            + row.unsupported
            + row.not_applicable
        )
        assert total == census.context_count


def test_the_highest_yield_profile_is_the_largest_nonzero_complete_population():
    projection = _impulse_draft()
    plans = plan_every_profile(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    census = build_complete_profile_census([plans])
    winner = census.highest_yield()
    assert winner is not None
    assert winner.complete > 0
    assert winner.complete == max(row.complete for row in census.profiles)


def test_an_empty_census_has_no_highest_yield_profile():
    census = build_complete_profile_census([])
    assert census.context_count == 0
    assert census.highest_yield() is None


@pytest.mark.parametrize(
    "forbidden",
    [
        "case_id",
        "family",
        "split",
        "problem_text",
        "expected_answer",
        "expected_terminal",
        "gold",
        "gold_graph",
        "answer",
        "chapter",
        "difficulty",
        "tags",
    ],
)
def test_a_census_row_cannot_carry_case_identity(forbidden):
    assert forbidden not in CompleteProfileFeasibilityV1.model_fields
    assert forbidden not in CompleteProfileCensusV1.model_fields
    assert forbidden not in CompleteProfilePlanV1.model_fields


def test_every_census_field_is_a_count():
    """No census field may hold anything but an integer or a profile ID."""

    projection = _impulse_draft()
    plans = plan_every_profile(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    payload = build_complete_profile_census([plans]).as_dict()
    for row in payload["profiles"]:
        for key, value in row.items():
            if key == "profile_id":
                assert value in {item.value for item in ProfileId}
                continue
            assert isinstance(value, int)
