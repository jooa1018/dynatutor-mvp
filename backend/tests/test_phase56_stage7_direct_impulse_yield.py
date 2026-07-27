"""Stage 7 direct-impulse yield: one typed transaction, exact signed graph.

Fixtures are independently authored. No corpus case identity, family, expected
terminal, expected answer, or raw-text routing participates in the runtime path.
"""
from __future__ import annotations

import pytest

from evaluation.phase56_stage7.complete_profile import PlanDisposition, ProfileId
from evaluation.phase56_stage7.complete_profile_application import (
    ApplicationOutcome,
    close_projected_draft,
)
from evaluation.phase56_stage7.direct_impulse_profile import (
    plan_direct_impulse_profile,
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
from test_phase56_stage7_profile_application import (
    IMPULSE_TEXT,
    _case,
    _fact,
    _impulse_gold,
)


def _projection(problem_text: str = IMPULSE_TEXT, gold: dict | None = None):
    projected = project_case_to_draft(
        _case(problem_text, gold if gold is not None else _impulse_gold())
    )
    assert projected.terminal is DraftProjectionTerminal.projected, (
        projected.sanitized_reason
    )
    return projected


def _run(problem_text: str = IMPULSE_TEXT, gold: dict | None = None):
    projection = _projection(problem_text, gold)
    return run_lane_b_case(projection, execution_token=deterministic_token(0))


def test_direct_impulse_plan_uses_only_the_existing_typed_profile() -> None:
    projection = _projection()
    measured = plan_direct_impulse_profile(projection.draft)
    assert measured is not None
    assert measured.profile_id is ProfileId.impulse_momentum
    assert measured.disposition is PlanDisposition.complete
    assert {
        item.prerequisite_id
        for item in measured.prerequisites
        if item.disposition.value
        not in {"explicit_source", "server_derivable", "generated_unknown"}
    } == set()


def test_direct_impulse_requires_the_verified_authority_stage_to_close() -> None:
    projection = _projection()
    unauthorised = close_projected_draft(projection.draft)
    assert not unauthorised.applied

    bundle = build_lane_b_authority_bundle(projection)
    authorised = close_projected_draft(
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert authorised.outcome is ApplicationOutcome.applied
    assert authorised.profile_id is ProfileId.impulse_momentum


def test_leftward_direct_impulse_solves_the_signed_final_velocity() -> None:
    result = _run()
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(2.0, abs=1.0e-10)
    assert result.verified_candidate_count == 1
    assert "linear_impulse_momentum" in result.applied_law_ids
    assert {
        "equation_residual",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    }.issubset(result.required_check_kinds)


def test_physics_changing_impulse_direction_changes_the_answer() -> None:
    gold = _impulse_gold()
    gold["explicit_facts"][2]["direction"] = "right"
    gold["explicit_facts"][2]["evidence_quote"] = "오른쪽으로 9 N*s 의 충격량"
    text = IMPULSE_TEXT.replace(
        "왼쪽으로 9 N*s 의 충격량", "오른쪽으로 9 N*s 의 충격량"
    )
    result = _run(text, gold)
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(8.0, abs=1.0e-10)


def test_cross_axis_or_magnitude_question_never_borrows_the_profile() -> None:
    vertical = _impulse_gold()
    vertical["explicit_facts"][2]["direction"] = "upward"
    vertical["explicit_facts"][2]["evidence_quote"] = "위쪽으로 9 N*s 의 충격량"
    vertical_text = IMPULSE_TEXT.replace(
        "왼쪽으로 9 N*s 의 충격량", "위쪽으로 9 N*s 의 충격량"
    )
    vertical_projection = _projection(vertical_text, vertical)
    assert plan_direct_impulse_profile(vertical_projection.draft) is None
    assert _run(vertical_text, vertical).terminal is not LaneBTerminal.solved

    magnitude = _impulse_gold()
    magnitude["queries"][0]["component"] = "magnitude"
    magnitude_projection = _projection(IMPULSE_TEXT, magnitude)
    bundle = build_lane_b_authority_bundle(magnitude_projection)
    closed = close_projected_draft(
        magnitude_projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert not closed.applied
    assert _run(IMPULSE_TEXT, magnitude).terminal is not LaneBTerminal.solved


def test_array_order_does_not_change_the_direct_impulse_result() -> None:
    original = _run()
    reordered = _impulse_gold()
    reordered["entities"] = list(reversed(reordered["entities"]))
    reordered["events"] = list(reversed(reordered["events"]))
    reordered["explicit_facts"] = list(reversed(reordered["explicit_facts"]))
    reordered["queries"] = list(reversed(reordered["queries"]))
    changed = _run(IMPULSE_TEXT, reordered)
    assert changed.terminal is original.terminal is LaneBTerminal.solved
    assert changed.answer_value_si == pytest.approx(original.answer_value_si, abs=0.0)


REST_TEXT = (
    "질량 4 kg인 시험 수레가 충격 직전 오른쪽으로 6 m/s로 움직였다. "
    "충격 뒤 시험 수레는 완전히 정지했다. "
    "오른쪽을 양으로 할 때 수레가 받은 충격량의 x성분을 구하시오."
)


def _rest_gold() -> dict:
    return {
        "entities": [{"role": "cart", "kind": "vehicle", "label": "시험 수레"}],
        "motion_segments": [
            {
                "role": "impact",
                "order": 1,
                "actor_roles": ["cart"],
                "motion_model": "impulse_interval",
                "relevance": "target",
                "start_event_role": "impact_start",
                "end_event_role": "rest",
            }
        ],
        "events": [
            {
                "role": "impact_start",
                "kind": "collision_start",
                "subject_roles": ["cart"],
                "segment_role": "impact",
                "evidence_quote": "충격 직전",
            },
            {
                "role": "rest",
                "kind": "comes_to_rest",
                "subject_roles": ["cart"],
                "segment_role": "impact",
                "evidence_quote": "정지했다",
            },
        ],
        "explicit_facts": [
            _fact(
                "mass",
                "mass",
                "4",
                "kg",
                "질량 4 kg",
                "cart",
                segment_role="impact",
            ),
            _fact(
                "v_before",
                "velocity_before",
                "6",
                "m/s",
                "충격 직전 오른쪽으로 6 m/s",
                "cart",
                segment_role="impact",
                event_role="impact_start",
                temporal_role="before_event",
                direction="right",
            ),
        ],
        "relations": [],
        "assumption_proposals": [
            {
                "role": "rest_end",
                "kind": "ends_at_rest",
                "subject_role": "cart",
                "segment_role": "impact",
                "supporting_quote": "시험 수레는 완전히 정지했다",
                "server_value_only": True,
            }
        ],
        "queries": [
            {
                "role": "q1",
                "output_key": "impulse",
                "subject_role": "cart",
                "segment_role": "impact",
                "component": "x",
                "event_role": "rest",
            }
        ],
        "expected_failure_codes": [],
    }


def test_evidenced_rest_boundary_solves_the_unknown_impulse() -> None:
    result = _run(REST_TEXT, _rest_gold())
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(-24.0, abs=1.0e-10)
    assert set(result.applied_law_ids) == {
        "linear_impulse_momentum",
        "state_at_rest",
    }
    assert "constraint" in result.required_check_kinds
    assert "source_evidence" in result.required_check_kinds
