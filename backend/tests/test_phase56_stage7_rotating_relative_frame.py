"""Typed rotating-relative frame closure: precise Coriolis deferral only.

The source names one point-like subject, one rotating rigid carrier, their
relative-motion topology, the carrier angular velocity, a radial relative
velocity, and a radius.  The evaluator may write down the coordinate frames and
rotation point those records already imply.  It may not invent a value,
equation, force, interaction, solver, root, or answer.
"""
from __future__ import annotations

import hashlib

import pytest

from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    draft_structure_fingerprint,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ROTATING_FRAME_ID,
    ROTATING_WORLD_FRAME_ID,
    ROTATION_POINT_ID,
    ApplicationOutcome,
    apply_selected_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionTerminal,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
    run_lane_b_case_with_selected_profile,
)
from support.phase56_stage7_corpus_fixtures import build_case


CORIOLIS_TEXT = (
    "회전 암에 고정된 좌표계에서 핀 P가 암에 대해 움직인다. "
    "암의 각속도는 반시계 방향 2.5 rad/s이고 핀의 반지름 방향 속도는 "
    "0.8 m/s이며 회전 중심에서 핀까지의 반지름은 0.45 m이다. "
    "이 순간 핀 P의 가속도 크기를 구하시오."
)


def _fact(role, key, value, unit, quote, subject, *, direction):
    return {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": "motion_1",
        "event_role": None,
        "temporal_role": "during",
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _gold(
    *,
    relations=None,
    query=None,
    entities=None,
    facts=None,
    assumptions=None,
):
    if relations is None:
        relations = [
            {
                "role": "relative_relation",
                "kind": "moves_relative_to",
                "participant_roles": ["pin", "arm"],
                "segment_role": "motion_1",
            }
        ]
    if query is None:
        query = {
            "role": "q1",
            "output_key": "acceleration",
            "subject_role": "pin",
            "segment_role": "motion_1",
            "component": "magnitude",
            "event_role": None,
        }
    if entities is None:
        entities = [
            {"role": "arm", "kind": "rigid_body", "label": "회전 암"},
            {"role": "pin", "kind": "pin", "label": "핀 P"},
            {"role": "frame", "kind": "reference_frame", "label": "회전좌표계"},
        ]
    if facts is None:
        facts = [
            _fact(
                "omega",
                "angular_velocity",
                "2.5",
                "rad/s",
                "각속도는 반시계 방향 2.5 rad/s",
                "arm",
                direction="counterclockwise",
            ),
            _fact(
                "vrel",
                "velocity",
                "0.8",
                "m/s",
                "반지름 방향 속도는 0.8 m/s",
                "pin",
                direction="radial",
            ),
            _fact(
                "radius",
                "radius",
                "0.45",
                "m",
                "반지름은 0.45 m",
                "pin",
                direction="not_applicable",
            ),
        ]
    return {
        "entities": entities,
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["arm", "pin"],
                "motion_model": "relative_motion",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["arm", "pin"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            },
            {
                "role": "finish",
                "kind": "finish",
                "subject_roles": ["arm", "pin"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            },
        ],
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions or [],
        "queries": [query],
        "answers": [],
        "expected_failure_codes": [],
    }


def _case(**gold_kwargs) -> PublicCorpusCaseV1:
    record = build_case(
        index=18,
        split="public_dev",
        # Intentionally unrelated: no runtime branch may use this label.
        family="constant_acceleration_1d",
        future_terminal="accepted",
        with_answer=False,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = CORIOLIS_TEXT
    record["problem_hash"] = hashlib.sha256(CORIOLIS_TEXT.encode()).hexdigest()
    record["gold"] = {**record["gold"], **_gold(**gold_kwargs)}
    return PublicCorpusCaseV1.model_validate(record)


def _projection(**gold_kwargs):
    projection = project_case_to_draft(_case(**gold_kwargs))
    assert projection.terminal is DraftProjectionTerminal.projected, projection.sanitized_reason
    assert projection.draft is not None
    return projection


def test_exact_rotating_topology_creates_only_frames_point_and_bindings() -> None:
    projection = _projection()
    draft = projection.draft
    before_values = {
        item.quantity_id: (item.raw_value, item.raw_unit)
        for item in draft.quantities
    }
    before_counts = (
        len(draft.interactions),
        len(draft.constraints),
        len(draft.state_conditions),
        len(draft.assumptions),
    )

    result = apply_selected_profile(draft, ProfileId.rotating_relative_frame)
    assert result.outcome is ApplicationOutcome.applied
    assert result.created_record_ids == (
        ROTATING_WORLD_FRAME_ID,
        ROTATING_FRAME_ID,
        ROTATION_POINT_ID,
    )
    assert set(result.rebound_quantity_ids) == {
        "qty_omega", "qty_vrel", "qty_unknown_q1"
    }

    world = next(
        item for item in result.draft.reference_frames
        if item.frame_id == ROTATING_WORLD_FRAME_ID
    )
    rotating = next(
        item for item in result.draft.reference_frames
        if item.frame_id == ROTATING_FRAME_ID
    )
    pivot = next(
        item for item in result.draft.points
        if item.point_id == ROTATION_POINT_ID
    )
    assert world.frame_type.value == "cartesian_3d"
    assert {axis.axis.value for axis in world.axes} == {"x", "y", "z"}
    assert rotating.frame_type.value == "rotating"
    assert rotating.parent_frame_id == ROTATING_WORLD_FRAME_ID
    assert rotating.rotating_about_point_id == ROTATION_POINT_ID
    assert rotating.translating_with_entity_id == "arm"
    assert {axis.axis.value for axis in rotating.axes} == {
        "radial", "transverse", "z"
    }
    assert pivot.owner_entity_id == "arm"
    assert pivot.frame_id == ROTATING_WORLD_FRAME_ID

    by_id = {item.quantity_id: item for item in result.draft.quantities}
    assert by_id["qty_omega"].frame_id == ROTATING_FRAME_ID
    assert by_id["qty_omega"].component.value == "z"
    assert by_id["qty_omega"].direction.axis.value == "z"
    assert by_id["qty_omega"].direction.sign == 1
    assert by_id["qty_vrel"].frame_id == ROTATING_FRAME_ID
    assert by_id["qty_vrel"].component.value == "radial"
    assert by_id["qty_vrel"].direction.axis.value == "radial"
    assert by_id["qty_unknown_q1"].frame_id == ROTATING_FRAME_ID
    assert by_id["qty_unknown_q1"].component.value == "magnitude"
    assert by_id["qty_unknown_q1"].direction is None
    assert result.draft.queries[0].target.frame_id == ROTATING_FRAME_ID
    assert result.draft.motion_intervals[0].frame_id == ROTATING_FRAME_ID
    assert {
        item.quantity_id: (item.raw_value, item.raw_unit)
        for item in result.draft.quantities
    } == before_values
    assert (
        len(result.draft.interactions),
        len(result.draft.constraints),
        len(result.draft.state_conditions),
        len(result.draft.assumptions),
    ) == before_counts


def test_exact_rotating_topology_reaches_only_precise_verified_deferral() -> None:
    result = run_lane_b_case(_projection(), execution_token=deterministic_token(0))
    assert result.terminal is LaneBTerminal.verified_unsupported
    assert result.compiler_codes == (
        "rotating_frame_relative_acceleration_deferred",
    )
    assert result.answer_value_si is None
    assert result.equation_count == 0
    assert result.candidate_count == 0
    assert result.verified_candidate_count == 0


def test_missing_or_duplicate_relative_topology_never_applies() -> None:
    missing = _projection(relations=[])
    missing_plan = plan_complete_profile(
        ProfileId.rotating_relative_frame, missing.draft
    )
    assert missing_plan.disposition is PlanDisposition.unsupported
    assert not missing_plan.structurally_complete
    missing_result = apply_selected_profile(
        missing.draft, ProfileId.rotating_relative_frame
    )
    assert missing_result.outcome is ApplicationOutcome.not_applied

    duplicate_relations = [
        {
            "role": role,
            "kind": "moves_relative_to",
            "participant_roles": participants,
            "segment_role": "motion_1",
        }
        for role, participants in (
            ("relative_a", ["pin", "arm"]),
            ("relative_b", ["arm", "pin"]),
        )
    ]
    duplicate = _projection(relations=duplicate_relations)
    duplicate_plan = plan_complete_profile(
        ProfileId.rotating_relative_frame, duplicate.draft
    )
    assert duplicate_plan.disposition is PlanDisposition.unsupported
    assert not duplicate_plan.structurally_complete
    assert apply_selected_profile(
        duplicate.draft, ProfileId.rotating_relative_frame
    ).outcome is ApplicationOutcome.not_applied


def test_missing_or_duplicate_observer_entity_never_applies() -> None:
    no_observer = _projection(
        entities=[
            {"role": "arm", "kind": "rigid_body", "label": "회전 암"},
            {"role": "pin", "kind": "pin", "label": "핀 P"},
        ]
    )
    assert not plan_complete_profile(
        ProfileId.rotating_relative_frame, no_observer.draft
    ).structurally_complete
    assert apply_selected_profile(
        no_observer.draft, ProfileId.rotating_relative_frame
    ).outcome is ApplicationOutcome.not_applied

    duplicate = _projection(
        entities=[
            {"role": "arm", "kind": "rigid_body", "label": "회전 암"},
            {"role": "pin", "kind": "pin", "label": "핀 P"},
            {"role": "frame_a", "kind": "reference_frame", "label": "좌표계 A"},
            {"role": "frame_b", "kind": "reference_frame", "label": "좌표계 B"},
        ]
    )
    assert not plan_complete_profile(
        ProfileId.rotating_relative_frame, duplicate.draft
    ).structurally_complete
    assert apply_selected_profile(
        duplicate.draft, ProfileId.rotating_relative_frame
    ).outcome is ApplicationOutcome.not_applied


def test_nonradial_relative_velocity_is_a_physics_changing_refusal() -> None:
    facts = _gold()["explicit_facts"]
    changed = [dict(item) for item in facts]
    changed[1]["direction"] = "right"
    projection = _projection(facts=changed)
    plan = plan_complete_profile(ProfileId.rotating_relative_frame, projection.draft)
    assert plan.disposition is PlanDisposition.unsupported
    assert not plan.structurally_complete
    result = run_lane_b_case(projection, execution_token=deterministic_token(1))
    assert result.terminal is not LaneBTerminal.verified_unsupported
    assert "rotating_frame_relative_acceleration_deferred" not in result.compiler_codes
    assert result.answer_value_si is None


@pytest.mark.parametrize("component", ["x", "radial", "transverse"])
def test_a_component_question_is_not_rewritten_as_a_magnitude_readout(
    component: str,
) -> None:
    query = {
        "role": "q1",
        "output_key": "acceleration",
        "subject_role": "pin",
        "segment_role": "motion_1",
        "component": component,
        "event_role": None,
    }
    projection = _projection(query=query)
    plan = plan_complete_profile(ProfileId.rotating_relative_frame, projection.draft)
    assert plan.disposition is PlanDisposition.not_applicable
    assert apply_selected_profile(
        projection.draft, ProfileId.rotating_relative_frame
    ).outcome is ApplicationOutcome.not_applied


def test_two_rotating_carriers_are_ambiguous_and_never_apply() -> None:
    facts = _gold()["explicit_facts"]
    duplicate = [*facts, {
        **facts[0],
        "role": "omega_2",
        "raw_value": "3.0",
        "evidence_quote": "보조 암의 각속도는 반시계 방향 3.0 rad/s",
        "subject_role": "arm_2",
        "quantity_occurrence_index": 0,
    }]
    entities = [
        {"role": "arm", "kind": "rigid_body", "label": "회전 암"},
        {"role": "arm_2", "kind": "rigid_body", "label": "보조 암"},
        {"role": "pin", "kind": "pin", "label": "핀 P"},
        {"role": "frame", "kind": "reference_frame", "label": "회전좌표계"},
    ]
    text = CORIOLIS_TEXT.replace(
        "암의 각속도는 반시계 방향 2.5 rad/s이고",
        "암의 각속도는 반시계 방향 2.5 rad/s이고 "
        "보조 암의 각속도는 반시계 방향 3.0 rad/s이며",
    )
    record = _case(facts=duplicate, entities=entities).model_dump(mode="json")
    record["gold"]["motion_segments"][0]["actor_roles"].append("arm_2")
    record["problem_text"] = text
    record["problem_hash"] = hashlib.sha256(text.encode()).hexdigest()
    projection = project_case_to_draft(PublicCorpusCaseV1.model_validate(record))
    assert projection.terminal is DraftProjectionTerminal.projected
    plan = plan_complete_profile(
        ProfileId.rotating_relative_frame, projection.draft
    )
    assert plan.disposition is PlanDisposition.unsupported
    assert not plan.structurally_complete
    assert apply_selected_profile(
        projection.draft, ProfileId.rotating_relative_frame
    ).outcome is ApplicationOutcome.not_applied


def test_generated_id_collision_abandons_the_whole_transaction() -> None:
    entities = [
        {"role": "arm", "kind": "rigid_body", "label": "회전 암"},
        {"role": "pin", "kind": "pin", "label": "핀 P"},
        {"role": "frame", "kind": "reference_frame", "label": "회전좌표계"},
        {"role": ROTATION_POINT_ID, "kind": "other", "label": "무관한 환경"},
    ]
    projection = _projection(entities=entities)
    fingerprint = draft_structure_fingerprint(projection.draft)
    result = apply_selected_profile(
        projection.draft, ProfileId.rotating_relative_frame
    )
    assert result.outcome is ApplicationOutcome.rejected
    assert result.sanitized_reason == "profile_shape_not_closable"
    assert result.draft is projection.draft
    assert draft_structure_fingerprint(result.draft) == fingerprint


def test_entity_fact_and_relation_order_do_not_change_the_terminal() -> None:
    base_case = _case()
    base_projection = project_case_to_draft(base_case)
    _, base = run_lane_b_case_with_selected_profile(
        base_projection,
        ProfileId.rotating_relative_frame,
        execution_token=deterministic_token(0, run_nonce="base"),
    )

    payload = base_case.model_dump(mode="json")
    payload["gold"]["entities"] = list(reversed(payload["gold"]["entities"]))
    payload["gold"]["explicit_facts"] = list(
        reversed(payload["gold"]["explicit_facts"])
    )
    payload["gold"]["relations"][0]["participant_roles"] = ["arm", "pin"]
    permuted_projection = project_case_to_draft(
        PublicCorpusCaseV1.model_validate(payload)
    )
    _, permuted = run_lane_b_case_with_selected_profile(
        permuted_projection,
        ProfileId.rotating_relative_frame,
        execution_token=deterministic_token(0, run_nonce="permuted"),
    )

    assert base.terminal is permuted.terminal is LaneBTerminal.verified_unsupported
    assert base.compiler_codes == permuted.compiler_codes == (
        "rotating_frame_relative_acceleration_deferred",
    )
    assert base.answer_value_si is permuted.answer_value_si is None


def test_unrelated_authority_id_does_not_change_the_transaction() -> None:
    projection = _projection()
    baseline = apply_selected_profile(
        projection.draft, ProfileId.rotating_relative_frame
    )
    with_irrelevant = apply_selected_profile(
        projection.draft,
        ProfileId.rotating_relative_frame,
        approved_assumption_ids=("unrelated_authority",),
    )
    assert baseline.outcome is with_irrelevant.outcome is ApplicationOutcome.applied
    assert baseline.draft == with_irrelevant.draft
    assert baseline.created_record_ids == with_irrelevant.created_record_ids
    assert baseline.rebound_quantity_ids == with_irrelevant.rebound_quantity_ids
