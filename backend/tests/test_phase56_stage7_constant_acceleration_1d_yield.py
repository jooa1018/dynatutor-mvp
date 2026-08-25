"""Supported one-dimensional constant-acceleration closure and endpoint scope."""
from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from engine.mechanics.math_ast import Add, Multiply, Negate
from engine.mechanics.solver.constant_acceleration_stop_boundary import (
    is_static_constant_acceleration_stop_boundary_graph,
)
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ApplicationOutcome,
    MOTION_AXIS_FRAME_ID,
    apply_selected_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
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
from support.phase56_stage7_corpus_fixtures import build_case


def _record(problem_text: str, gold: dict, *, index: int) -> PublicCorpusCaseV1:
    record = build_case(
        index=index,
        split="public_dev",
        family="constant_acceleration_1d",
        future_terminal="accepted",
        with_answer=True,
    )
    record.update(
        split=PublicSplit.public_dev,
        problem_text=problem_text,
        problem_hash=hashlib.sha256(problem_text.encode("utf-8")).hexdigest(),
        family="constant_acceleration_1d",
        gold=gold,
    )
    return PublicCorpusCaseV1(**record)


def _braking_case() -> PublicCorpusCaseV1:
    text = (
        "시험 카트가 진행 방향으로 18 m/s로 움직이다가 진행 반대 방향으로 "
        "3 m/s²의 일정한 가속도로 감속한다. 시험 카트는 완전히 정지한다. "
        "정지할 때까지 걸리는 시간을 구하여라."
    )
    gold = {
        "parse_status": "complete",
        "expected_system_type": "constant_acceleration_1d",
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": [{"role": "cart", "kind": "vehicle", "label": "시험 카트"}],
        "motion_segments": [
            {
                "role": "braking",
                "order": 1,
                "actor_roles": ["cart"],
                "motion_model": "constant_acceleration_1d",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "rest",
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["cart"],
                "segment_role": "braking",
                "evidence_quote": "움직이다가",
            },
            {
                "role": "rest",
                "kind": "comes_to_rest",
                "subject_roles": ["cart"],
                "segment_role": "braking",
                "evidence_quote": "완전히 정지한다",
            },
        ],
        "explicit_facts": [
            {
                "role": "v0",
                "semantic_key": "initial_velocity",
                "raw_value": "18",
                "raw_unit": "m/s",
                "evidence_quote": "18 m/s",
                "subject_role": "cart",
                "segment_role": "braking",
                "event_role": "start",
                "temporal_role": "initial",
                "direction": "along_motion",
                "relevance": "solver_input",
                "occurrence_index": 0,
                "quantity_occurrence_index": 0,
            },
            {
                "role": "a",
                "semantic_key": "acceleration",
                "raw_value": "3",
                "raw_unit": "m/s²",
                "evidence_quote": "3 m/s²",
                "subject_role": "cart",
                "segment_role": "braking",
                "event_role": None,
                "temporal_role": "during",
                "direction": "opposite_motion",
                "relevance": "solver_input",
                "occurrence_index": 0,
                "quantity_occurrence_index": 0,
            },
        ],
        "relations": [],
        "assumption_proposals": [
            {
                "role": "end_rest",
                "kind": "ends_at_rest",
                "subject_role": "cart",
                "segment_role": "braking",
                "supporting_quote": "완전히 정지한다",
                "server_value_only": True,
            }
        ],
        "queries": [
            {
                "role": "q1",
                "output_key": "time",
                "subject_role": "cart",
                "segment_role": "braking",
                "component": "magnitude",
                "event_role": "rest",
            }
        ],
        "answers": [
            {
                "query_role": "q1",
                "numeric": 6.0,
                "unit": "s",
                "tolerance_abs": 1.0e-9,
                "reference_expression": "v0/a",
            }
        ],
        "expected_failure_codes": [],
    }
    return _record(text, gold, index=710)


def _endpoint_path_case() -> PublicCorpusCaseV1:
    text = (
        "시험 로봇은 첫 구간에서 정지 상태로 출발해 일정한 가속도로 24 m를 "
        "이동하며 4초 뒤 전환점에 도달한다. 두 번째 구간에서는 일정한 속도로 "
        "움직인다. 첫 구간의 가속도를 구하여라."
    )
    gold = {
        "parse_status": "complete",
        "expected_system_type": "constant_acceleration_1d",
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": [{"role": "robot", "kind": "vehicle", "label": "시험 로봇"}],
        "motion_segments": [
            {
                "role": "segment_1",
                "order": 1,
                "actor_roles": ["robot"],
                "motion_model": "constant_acceleration_1d",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "transition",
            },
            {
                "role": "segment_2",
                "order": 2,
                "actor_roles": ["robot"],
                "motion_model": "constant_velocity_1d",
                "relevance": "supporting",
                "start_event_role": "transition",
                "end_event_role": "finish",
            },
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["robot"],
                "segment_role": "segment_1",
                "evidence_quote": "출발해",
            },
            {
                "role": "transition",
                "kind": "reaches_position",
                "subject_roles": ["robot"],
                "segment_role": "segment_1",
                "evidence_quote": "전환점에 도달한다",
            },
            {
                "role": "finish",
                "kind": "finish",
                "subject_roles": ["robot"],
                "segment_role": "segment_2",
                "evidence_quote": None,
            },
        ],
        "explicit_facts": [
            {
                "role": "segment_distance",
                "semantic_key": "distance",
                "raw_value": "24",
                "raw_unit": "m",
                "evidence_quote": "24 m",
                "subject_role": "robot",
                "segment_role": "segment_1",
                "event_role": "transition",
                "temporal_role": "interval",
                "direction": "not_applicable",
                "relevance": "solver_input",
                "occurrence_index": 0,
                "quantity_occurrence_index": 0,
            },
            {
                "role": "segment_time",
                "semantic_key": "time",
                "raw_value": "4",
                "raw_unit": "s",
                "evidence_quote": "4초",
                "subject_role": "robot",
                "segment_role": "segment_1",
                "event_role": None,
                "temporal_role": "interval",
                "direction": "not_applicable",
                "relevance": "solver_input",
                "occurrence_index": 0,
                "quantity_occurrence_index": 0,
            },
        ],
        "relations": [],
        "assumption_proposals": [
            {
                "role": "start_rest",
                "kind": "starts_from_rest",
                "subject_role": "robot",
                "segment_role": "segment_1",
                "supporting_quote": "정지 상태로 출발해",
                "server_value_only": True,
            }
        ],
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "robot",
                "segment_role": "segment_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "answers": [
            {
                "query_role": "q1",
                "numeric": 3.0,
                "unit": "m/s^2",
                "tolerance_abs": 1.0e-9,
                "reference_expression": "2*s/t^2",
            }
        ],
        "expected_failure_codes": [],
    }
    return _record(text, gold, index=711)


def _project(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    assert projection.draft is not None
    return projection


def _run(case: PublicCorpusCaseV1, nonce: str):
    return run_lane_b_case(
        _project(case), execution_token=deterministic_token(0, run_nonce=nonce)
    )


def test_signed_braking_time_solves_through_the_real_lane() -> None:
    result = _run(_braking_case(), "braking")
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(6.0)
    assert result.applied_law_ids == (
        "particle_constant_acceleration_velocity",
        "state_at_rest",
    )
    assert result.candidate_count == result.verified_candidate_count == 1
    assert {kind for kind, status in result.verification_checks if status == "passed"} >= {
        "constraint",
        "equation_residual",
        "nonnegative_time",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    }


def test_endpoint_annotated_interval_distance_solves_as_displacement() -> None:
    projection = _project(_endpoint_path_case())
    distance = next(
        item for item in projection.draft.quantities if item.quantity_id == "qty_segment_distance"
    )
    assert distance.role.value == "displacement"
    assert distance.interval_id == "segment_1"
    assert distance.event_id is None
    result = run_lane_b_case(
        projection, execution_token=deterministic_token(1, run_nonce="path")
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(3.0)
    assert result.candidate_count == result.verified_candidate_count == 1


def test_braking_transaction_changes_no_raw_value_or_unit() -> None:
    projection = _project(_braking_case())
    bundle = build_lane_b_authority_bundle(projection)
    plan = plan_complete_profile(
        ProfileId.signed_constant_acceleration_1d,
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    application = apply_selected_profile(
        projection.draft,
        ProfileId.signed_constant_acceleration_1d,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    assert application.created_record_ids == (MOTION_AXIS_FRAME_ID,)
    before = {
        item.quantity_id: (item.raw_value, item.raw_unit)
        for item in projection.draft.quantities
    }
    after = {
        item.quantity_id: (item.raw_value, item.raw_unit)
        for item in application.draft.quantities
    }
    assert after == before


def test_same_direction_acceleration_does_not_solve_as_braking() -> None:
    case = _braking_case()
    facts = list(case.gold.explicit_facts)
    facts[1] = facts[1].model_copy(update={"direction": "along_motion"})
    tampered = case.model_copy(
        update={"gold": case.gold.model_copy(update={"explicit_facts": tuple(facts)})}
    )
    result = _run(tampered, "same-direction")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_missing_rest_evidence_does_not_authorize_the_profile() -> None:
    case = _braking_case()
    assumptions = (
        case.gold.assumption_proposals[0].model_copy(
            update={"supporting_quote": "문제에 없는 정지 문구"}
        ),
    )
    tampered = case.model_copy(
        update={"gold": case.gold.model_copy(update={"assumption_proposals": assumptions})}
    )
    result = _run(tampered, "missing-rest")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_fact_and_event_order_do_not_change_the_result() -> None:
    case = _braking_case()
    reordered = case.model_copy(
        update={
            "gold": case.gold.model_copy(
                update={
                    "events": tuple(reversed(case.gold.events)),
                    "explicit_facts": tuple(reversed(case.gold.explicit_facts)),
                }
            )
        }
    )
    baseline = _run(case, "order-a")
    changed = _run(reordered, "order-b")
    assert changed.terminal is baseline.terminal is LaneBTerminal.solved
    assert changed.answer_value_si == pytest.approx(baseline.answer_value_si)


def test_solver_waiver_is_exact_and_rejects_a_sign_near_miss() -> None:
    projection = _project(_braking_case())
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.signed_constant_acceleration_1d,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    from evaluation.phase56_stage7.event_boundary_derivation import derive_event_boundaries
    from engine.mechanics.validation import validate_draft
    from engine.mechanics.normalization import normalize_draft
    from engine.mechanics.compiler import MechanicsCompiler, authorize_validated_mechanics_ir

    draft = derive_event_boundaries(application.draft).draft
    validation = validate_draft(
        projection.problem_text,
        draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert validation.accepted
    normalized = normalize_draft(
        projection.problem_text,
        draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    authorization = authorize_validated_mechanics_ir(normalized.ir)
    compiled = MechanicsCompiler().compile(
        normalized.ir,
        validated_ir_authorization=authorization,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert compiled.graph is not None
    assert is_static_constant_acceleration_stop_boundary_graph(compiled.graph)
    velocity = next(
        item
        for item in compiled.graph.equations
        if item.law_id == "particle_constant_acceleration_velocity"
    )
    assert isinstance(velocity.expression.right, Add)
    product = next(
        item for item in velocity.expression.right.terms if isinstance(item, Multiply)
    )
    negative = next(item for item in product.factors if isinstance(item, Negate))
    wrong_product = product.model_copy(
        update={
            "factors": tuple(
                negative.operand if item is negative else item for item in product.factors
            )
        }
    )
    wrong_right = velocity.expression.right.model_copy(
        update={
            "terms": tuple(
                wrong_product if item is product else item
                for item in velocity.expression.right.terms
            )
        }
    )
    wrong_equation = velocity.model_copy(
        update={"expression": velocity.expression.model_copy(update={"right": wrong_right})}
    )
    wrong_graph = compiled.graph.model_copy(
        update={
            "equations": tuple(
                wrong_equation if item is velocity else item
                for item in compiled.graph.equations
            )
        }
    )
    assert not is_static_constant_acceleration_stop_boundary_graph(wrong_graph)


def test_reference_answer_and_identity_metadata_never_change_runtime() -> None:
    case = _braking_case()
    answer = case.gold.answers[0]
    tampered = case.model_copy(
        update={
            "case_id": "different-public-looking-id",
            "family": "projectile_motion",
            "gold": case.gold.model_copy(
                update={
                    "expected_system_type": "collision_1d",
                    "answers": (
                        answer.model_copy(update={"numeric": 99999.0}),
                    ),
                }
            ),
        }
    )
    baseline = _run(case, "metadata-a")
    changed = _run(tampered, "metadata-b")
    assert changed.terminal is baseline.terminal is LaneBTerminal.solved
    assert changed.answer_value_si == pytest.approx(baseline.answer_value_si)
