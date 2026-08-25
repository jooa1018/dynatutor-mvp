"""Boundary-scoped rest authority: opposite endpoints differ, same endpoints conflict."""
from __future__ import annotations

from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionTerminal,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)
from test_phase56_stage7_direct_impulse_yield import REST_TEXT, _rest_gold
from test_phase56_stage7_profile_application import _case, _fact


def _projection(text: str, gold: dict):
    result = project_case_to_draft(_case(text, gold))
    assert result.terminal is DraftProjectionTerminal.projected, result.sanitized_reason
    assert result.draft is not None
    return result


def test_initial_velocity_does_not_suppress_a_distinct_final_rest_boundary() -> None:
    projection = _projection(REST_TEXT, _rest_gold())
    rest = tuple(
        item for item in projection.draft.assumptions if item.kind == "ends_at_rest"
    )
    assert len(rest) == 1
    assert rest[0].disposition.value == "approved"
    states = tuple(
        item
        for item in projection.draft.state_conditions
        if item.subject_id == "cart"
        and item.event_id == "rest"
        and item.state.value == "at_rest"
    )
    assert len(states) == 1
    assert states[0].evidence_refs


def test_same_boundary_explicit_velocity_keeps_rest_rejected_and_never_solves() -> None:
    gold = _rest_gold()
    gold["explicit_facts"].append(
        _fact(
            "v_after",
            "velocity_after",
            "3",
            "m/s",
            "충격 뒤 시험 수레는 오른쪽으로 3 m/s",
            "cart",
            segment_role="impact",
            event_role="rest",
            temporal_role="after_event",
            direction="right",
        )
    )
    text = REST_TEXT.replace(
        "충격 뒤 시험 수레는 완전히 정지했다.",
        "충격 뒤 시험 수레는 오른쪽으로 3 m/s로 움직였지만 시험 수레는 완전히 정지했다.",
    )
    projection = _projection(text, gold)
    rest = tuple(
        item for item in projection.draft.assumptions if item.kind == "ends_at_rest"
    )
    assert len(rest) == 1
    assert rest[0].disposition.value == "rejected"
    assert not tuple(
        item
        for item in projection.draft.state_conditions
        if item.subject_id == "cart"
        and item.event_id == "rest"
        and item.state.value == "at_rest"
    )

    result = run_lane_b_case(projection, execution_token=deterministic_token(0))
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
