"""Stage 7 slot-pin frame closure is exact, transactional, and deferral-only."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from engine.mechanics.contracts import MechanicsProblemDraftV1
from engine.mechanics.compiler import CompilerIssueCode
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    SLOT_PIN_FRAME_ID,
    ApplicationOutcome,
    apply_selected_profile,
)
from evaluation.phase56_stage7.lane_b_authority import build_lane_b_authority_bundle
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionTerminal,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)
from test_phase56_stage7_profile_application import _case, _fact


SLOT_TEXT = (
    "회전 슬롯 안에서 핀 P가 움직인다. 한 순간 r=0.6 m 이고 "
    "슬롯의 각속도는 1.8 rad/s 이다. 핀의 슬롯에 대한 상대속도는 "
    "반지름 방향으로 0.25 m/s 이고 슬롯의 각가속도는 0.5 rad/s² 이다. "
    "그 순간 핀의 가로방향 가속도 성분을 구하시오."
)


def _slot_gold(*, component: str = "transverse", relations=None) -> dict:
    return {
        "entities": [
            {"role": "slot", "kind": "slot", "label": "회전 슬롯"},
            {"role": "pin", "kind": "pin", "label": "핀 P"},
            {"role": "frame", "kind": "reference_frame", "label": "슬롯 좌표계"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["slot", "pin"],
                "motion_model": "relative_motion",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "instant",
                "kind": "other",
                "subject_roles": ["slot", "pin"],
                "segment_role": "motion_1",
                "evidence_quote": "한 순간",
            }
        ],
        "explicit_facts": [
            _fact(
                "r", "radius", "0.6", "m", "r=0.6 m", "pin",
                event_role="instant", temporal_role="at_event", direction="radial",
            ),
            _fact(
                "omega", "angular_velocity", "1.8", "rad/s",
                "슬롯의 각속도는 1.8 rad/s", "slot",
                event_role="instant", temporal_role="at_event",
                direction="counterclockwise",
            ),
            _fact(
                "rdot", "velocity", "0.25", "m/s",
                "상대속도는 반지름 방향으로 0.25 m/s", "pin",
                event_role="instant", temporal_role="at_event", direction="radial",
            ),
            _fact(
                "alpha", "angular_acceleration", "0.5", "rad/s^2",
                "슬롯의 각가속도는 0.5 rad/s²", "slot",
                event_role="instant", temporal_role="at_event",
                direction="counterclockwise",
            ),
        ],
        "relations": relations if relations is not None else [
            {
                "role": "slot_rel",
                "kind": "moves_in_slot",
                "participant_roles": ["pin", "slot"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "pin",
                "segment_role": "motion_1",
                "component": component,
                "event_role": "instant",
            }
        ],
        "expected_failure_codes": [],
    }


def _projection(*, component: str = "transverse", relations=None):
    result = project_case_to_draft(
        _case(SLOT_TEXT, _slot_gold(component=component, relations=relations))
    )
    assert result.terminal is DraftProjectionTerminal.projected, result.sanitized_reason
    assert result.draft is not None
    return result


def _apply(projection):
    bundle = build_lane_b_authority_bundle(projection)
    return apply_selected_profile(
        projection.draft,
        ProfileId.slot_pin_relative_frame,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )


def test_exact_slot_pin_structure_forms_a_structurally_complete_deferred_plan() -> None:
    projection = _projection()
    plan = plan_complete_profile(
        ProfileId.slot_pin_relative_frame,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.unsupported
    assert plan.structurally_complete
    assert plan.uses_server_derivation


def test_transaction_creates_only_the_frame_and_rebinds_only_the_query_unknown() -> None:
    projection = _projection()
    before = {
        item.quantity_id: (item.raw_value, item.raw_unit, item.frame_id)
        for item in projection.draft.quantities
    }
    result = _apply(projection)
    assert result.outcome is ApplicationOutcome.applied
    assert result.created_record_ids == (SLOT_PIN_FRAME_ID,)
    assert result.rebound_quantity_ids == ("qty_unknown_q1",)

    closed = result.draft
    frames = [item for item in closed.reference_frames if item.frame_id == SLOT_PIN_FRAME_ID]
    assert len(frames) == 1
    assert frames[0].frame_type.value == "radial_transverse"
    assert frames[0].origin.kind == "entity"
    assert frames[0].origin.entity_id == "slot"
    assert {item.axis.value for item in frames[0].axes} == {"radial", "transverse"}
    after = {
        item.quantity_id: (item.raw_value, item.raw_unit, item.frame_id)
        for item in closed.quantities
    }
    for quantity_id, (raw_value, raw_unit, frame_id) in before.items():
        assert after[quantity_id][:2] == (raw_value, raw_unit)
        if quantity_id == "qty_unknown_q1":
            assert after[quantity_id][2] == SLOT_PIN_FRAME_ID
        else:
            assert after[quantity_id][2] == frame_id
    assert closed.queries[0].target.frame_id == SLOT_PIN_FRAME_ID


def test_exact_slot_pin_structure_reaches_only_the_typed_deferred_terminal() -> None:
    projection = _projection()
    result = run_lane_b_case(projection, execution_token=deterministic_token(0))
    assert result.terminal is LaneBTerminal.verified_unsupported
    assert result.compiler_codes == (
        CompilerIssueCode.slot_pin_relative_motion_deferred.value,
    )
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_missing_or_ambiguous_slot_relation_never_applies() -> None:
    missing = _projection(relations=[])
    assert _apply(missing).outcome is ApplicationOutcome.not_applied

    relation = {
        "role": "slot_rel",
        "kind": "moves_in_slot",
        "participant_roles": ["pin", "slot"],
        "segment_role": "motion_1",
    }
    ambiguous = _projection(relations=[relation, {**relation, "role": "slot_rel_2"}])
    result = _apply(ambiguous)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft == ambiguous.draft


def test_magnitude_query_and_prebound_query_are_not_rewritten() -> None:
    magnitude = _projection(component="magnitude")
    assert _apply(magnitude).outcome is ApplicationOutcome.not_applied

    projection = _projection()
    payload = projection.draft.model_dump(mode="json", warnings="none")
    payload["reference_frames"] = [
        {
            "frame_id": "already_bound",
            "frame_type": "radial_transverse",
            "origin": {"kind": "entity", "entity_id": "slot"},
            "axes": [
                {
                    "axis": axis,
                    "direction": {
                        "kind": "axis", "frame_id": "already_bound",
                        "axis": axis, "sign": 1,
                    },
                }
                for axis in ("radial", "transverse")
            ],
            "parent_frame_id": None,
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": [],
        }
    ]
    for item in payload["quantities"]:
        if item["quantity_id"] == "qty_unknown_q1":
            item["frame_id"] = "already_bound"
    payload["queries"][0]["target"]["frame_id"] = "already_bound"
    bound = replace(projection, draft=MechanicsProblemDraftV1.model_validate(payload))
    assert _apply(bound).outcome is ApplicationOutcome.rejected


def test_generated_frame_id_collision_abandons_the_whole_transaction() -> None:
    projection = _projection()
    payload = projection.draft.model_dump(mode="json", warnings="none")
    payload["entities"].append(
        {
            "entity_id": SLOT_PIN_FRAME_ID,
            "primitive": "environment",
            "label": "collision sentinel",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": [],
            "model_confidence": None,
        }
    )
    collided = replace(projection, draft=MechanicsProblemDraftV1.model_validate(payload))
    result = _apply(collided)
    assert result.outcome is ApplicationOutcome.rejected
    assert result.draft == collided.draft


def test_entity_fact_and_relation_order_do_not_change_the_terminal() -> None:
    gold = _slot_gold()
    reordered = deepcopy(gold)
    reordered["entities"] = list(reversed(reordered["entities"]))
    reordered["explicit_facts"] = list(reversed(reordered["explicit_facts"]))
    reordered["relations"][0]["participant_roles"] = ["slot", "pin"]
    first = project_case_to_draft(_case(SLOT_TEXT, gold))
    second = project_case_to_draft(_case(SLOT_TEXT, reordered))
    first_result = run_lane_b_case(first, execution_token=deterministic_token(0))
    second_result = run_lane_b_case(second, execution_token=deterministic_token(0))
    assert first_result.terminal is second_result.terminal is LaneBTerminal.verified_unsupported
    assert first_result.compiler_codes == second_result.compiler_codes
    assert first_result.answer_value_si is second_result.answer_value_si is None
