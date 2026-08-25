"""Exact direct constant-force work closure and authority near misses."""
from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    DIRECT_WORK_ASSUMPTION_ID,
    DIRECT_WORK_FRAME_ID,
    DIRECT_WORK_INTERACTION_ID,
    ApplicationOutcome,
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


def _fact(
    role: str,
    semantic_key: str,
    value: str,
    unit: str,
    quote: str,
    *,
    temporal_role: str,
    direction: str,
    subject_role: str = "object",
    segment_role: str = "motion_1",
    event_role: str | None = None,
) -> dict:
    return {
        "role": role,
        "semantic_key": semantic_key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject_role,
        "segment_role": segment_role,
        "event_role": event_role,
        "temporal_role": temporal_role,
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _work_case(
    *,
    force: str = "45",
    force_unit: str = "N",
    distance: str = "6",
    distance_unit: str = "m",
    force_direction: str = "along_motion",
    force_temporal: str = "during",
    distance_temporal: str = "interval",
    query_component: str = "magnitude",
    query_event: str | None = None,
    extra_fact: dict | None = None,
    extra_entity: bool = False,
    relation: dict | None = None,
    assumption_proposal: dict | None = None,
    reverse: bool = False,
    family: str = "independent_direct_work_fixture",
    text_prefix: str = "일정한 ",
) -> PublicCorpusCaseV1:
    force_quote = f"{force} {force_unit}"
    distance_quote = f"{distance} {distance_unit}"
    text = (
        f"시험 물체에 이동 방향과 나란한 {text_prefix}힘 {force_quote}을 가하여 "
        f"{distance_quote} 이동시켰다. 이 힘이 한 일을 구하여라."
    )
    if extra_fact is not None:
        text += f" 참고로 {extra_fact['evidence_quote']}."
    entities = [{"role": "object", "kind": "block", "label": "시험 물체"}]
    if extra_entity:
        entities.append({"role": "other", "kind": "block", "label": "무관 물체"})
    facts = [
        _fact(
            "force",
            "force",
            force,
            force_unit,
            force_quote,
            temporal_role=force_temporal,
            direction=force_direction,
        ),
        _fact(
            "distance",
            "distance",
            distance,
            distance_unit,
            distance_quote,
            temporal_role=distance_temporal,
            direction="not_applicable",
        ),
    ]
    if extra_fact is not None:
        facts.append(extra_fact)
    if reverse:
        entities.reverse()
        facts.reverse()
    gold = {
        "parse_status": "complete",
        "expected_system_type": "independent_direct_work_fixture",
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["object"],
                "motion_model": "energy_interval",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["object"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            },
            {
                "role": "finish",
                "kind": "finish",
                "subject_roles": ["object"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            },
        ],
        "explicit_facts": facts,
        "relations": [relation] if relation is not None else [],
        "assumption_proposals": (
            [assumption_proposal] if assumption_proposal is not None else []
        ),
        "queries": [
            {
                "role": "q1",
                "output_key": "work",
                "subject_role": "object",
                "segment_role": "motion_1",
                "component": query_component,
                "event_role": query_event,
            }
        ],
        "answers": [],
        "expected_failure_codes": [],
    }
    record = build_case(
        index=782,
        split="public_dev",
        family=family,
        future_terminal="accepted",
        with_answer=False,
    )
    record.update(
        split=PublicSplit.public_dev,
        family=family,
        problem_text=text,
        problem_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        gold=gold,
    )
    return PublicCorpusCaseV1(**record)


def _projection(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    assert projection.draft is not None
    return projection


def _run(case: PublicCorpusCaseV1, nonce: str):
    return run_lane_b_case(
        _projection(case), execution_token=deterministic_token(0, run_nonce=nonce)
    )


def test_projection_derives_only_the_scoped_value_free_force_authority() -> None:
    projection = _projection(_work_case())
    assumptions = tuple(
        item
        for item in projection.draft.assumptions
        if item.assumption_id == DIRECT_WORK_ASSUMPTION_ID
    )
    assert len(assumptions) == 1
    assumption = assumptions[0]
    assert assumption.kind == "constant_force"
    assert assumption.subject_id == "object"
    assert assumption.interval_id == "motion_1"
    assert assumption.disposition.value == "approved"
    assert assumption.proposed_role is None
    assert assumption.proposed_value is None
    assert assumption.proposed_unit is None
    assert assumption.evidence_refs
    bundle = build_lane_b_authority_bundle(projection)
    assert DIRECT_WORK_ASSUMPTION_ID in bundle.approved_assumption_ids


def test_direct_constant_force_work_solves_through_the_real_lane() -> None:
    result = _run(_work_case(), "direct-work-positive")
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(270.0)
    assert result.answer_unit == "J"
    assert result.candidate_count == 1
    assert result.verified_candidate_count == 1
    assert result.applied_law_ids == ("force_work",)
    checks = dict(result.verification_checks)
    for required in (
        "equation_residual",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    ):
        assert checks[required] == "passed"


def test_transaction_preserves_all_source_values_units_evidence_and_primitives() -> None:
    projection = _projection(_work_case())
    bundle = build_lane_b_authority_bundle(projection)
    plan = plan_complete_profile(
        ProfileId.direct_constant_force_work,
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    application = apply_selected_profile(
        projection.draft,
        ProfileId.direct_constant_force_work,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    assert set(application.created_record_ids) == {
        DIRECT_WORK_FRAME_ID,
        DIRECT_WORK_INTERACTION_ID,
    }
    assert set(application.rebound_quantity_ids) == {
        "qty_force",
        "qty_distance",
        "qty_unknown_q1",
    }
    before = {
        item.quantity_id: (
            item.raw_value,
            item.raw_unit,
            tuple(item.evidence_refs),
            item.subject_id,
            item.interval_id,
            item.event_id,
        )
        for item in projection.draft.quantities
    }
    after = {
        item.quantity_id: (
            item.raw_value,
            item.raw_unit,
            tuple(item.evidence_refs),
            item.subject_id,
            item.interval_id,
            item.event_id,
        )
        for item in application.draft.quantities
    }
    assert after == before
    assert application.draft.entities == projection.draft.entities
    by_id = {item.quantity_id: item for item in application.draft.quantities}
    assert by_id["qty_force"].component.value == "x"
    assert by_id["qty_distance"].role.value == "displacement"
    assert by_id["qty_distance"].component.value == "x"
    assert by_id["qty_unknown_q1"].role.value == "work"


def test_physics_changing_force_and_distance_change_the_verified_answer() -> None:
    baseline = _run(_work_case(force="45", distance="6"), "direct-work-270")
    changed_force = _run(_work_case(force="80", distance="6"), "direct-work-480")
    changed_distance = _run(_work_case(force="45", distance="8"), "direct-work-360")
    assert baseline.terminal is changed_force.terminal is changed_distance.terminal is LaneBTerminal.solved
    assert baseline.answer_value_si == pytest.approx(270.0)
    assert changed_force.answer_value_si == pytest.approx(480.0)
    assert changed_distance.answer_value_si == pytest.approx(360.0)


def test_compatible_unit_conversion_is_invariant() -> None:
    baseline = _run(_work_case(force="45", distance="6"), "direct-work-si")
    converted = _run(
        _work_case(force="0.045", force_unit="kN", distance="600", distance_unit="cm"),
        "direct-work-converted",
    )
    assert baseline.terminal is converted.terminal is LaneBTerminal.solved
    assert converted.answer_value_si == pytest.approx(baseline.answer_value_si)


def test_fact_and_entity_order_and_family_metadata_are_not_authority() -> None:
    baseline = _run(_work_case(family="fixture_a"), "direct-work-order-a")
    changed = _run(
        _work_case(reverse=True, family="unrelated_label"),
        "direct-work-order-b",
    )
    assert baseline.terminal is changed.terminal is LaneBTerminal.solved
    assert changed.answer_value_si == pytest.approx(baseline.answer_value_si)


@pytest.mark.parametrize(
    ("case", "nonce"),
    (
        (_work_case(force_direction="opposite_motion"), "opposite-direction"),
        (_work_case(force_direction="not_applicable"), "missing-direction"),
        (_work_case(force_temporal="initial"), "wrong-force-scope"),
        (_work_case(distance_temporal="timeless"), "wrong-distance-scope"),
        (_work_case(query_component="x"), "signed-query"),
        (_work_case(query_event="finish"), "event-query"),
        (_work_case(extra_entity=True), "extra-body"),
    ),
)
def test_near_miss_typed_shapes_never_receive_constant_force_authority(
    case: PublicCorpusCaseV1, nonce: str
) -> None:
    projection = _projection(case)
    assert DIRECT_WORK_ASSUMPTION_ID not in build_lane_b_authority_bundle(projection).approved_assumption_ids
    result = run_lane_b_case(
        projection, execution_token=deterministic_token(0, run_nonce=nonce)
    )
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_unrelated_number_and_extra_relation_refuse_the_exact_shape() -> None:
    extra = _fact(
        "irrelevant_distance",
        "distance",
        "999",
        "m",
        "무관한 표지까지 999 m",
        temporal_role="timeless",
        direction="not_applicable",
    )
    relation = {
        "role": "extra_relation",
        "kind": "connected_to",
        "participant_roles": ["object"],
        "segment_role": "motion_1",
    }
    for case, nonce in (
        (_work_case(extra_fact=extra), "unrelated-number"),
        (_work_case(relation=relation), "extra-relation"),
    ):
        projection = project_case_to_draft(case)
        if projection.terminal is DraftProjectionTerminal.projected:
            assert (
                DIRECT_WORK_ASSUMPTION_ID
                not in build_lane_b_authority_bundle(projection).approved_assumption_ids
            )
        result = run_lane_b_case(
            projection, execution_token=deterministic_token(0, run_nonce=nonce)
        )
        assert result.terminal is not LaneBTerminal.solved
        assert result.answer_value_si is None


def test_raw_text_keyword_cannot_replace_the_typed_interval_scope() -> None:
    # The sentence still says "constant", but the typed source scope is not the
    # whole interval.  A raw-text or keyword route would solve; the typed policy
    # must refuse.
    case = _work_case(force_temporal="initial", text_prefix="일정한 ")
    projection = _projection(case)
    assert DIRECT_WORK_ASSUMPTION_ID not in build_lane_b_authority_bundle(projection).approved_assumption_ids
    result = run_lane_b_case(
        projection,
        execution_token=deterministic_token(0, run_nonce="constant-keyword-attack"),
    )
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_expected_and_failure_metadata_tampering_does_not_change_runtime() -> None:
    baseline_case = _work_case()
    changed_payload = baseline_case.model_dump(mode="json")
    changed_payload["gold"]["future_expected_terminal"] = "verified_unsupported"
    changed_payload["gold"]["expected_failure_codes"] = ["invented_failure"]
    changed = PublicCorpusCaseV1.model_validate(changed_payload)
    baseline = _run(baseline_case, "direct-work-gold-a")
    changed_result = _run(changed, "direct-work-gold-b")
    assert baseline.terminal is changed_result.terminal is LaneBTerminal.solved
    assert changed_result.answer_value_si == pytest.approx(baseline.answer_value_si)


def test_transaction_is_all_or_nothing_under_id_collision() -> None:
    projection = _projection(_work_case())
    payload = projection.draft.model_dump(mode="json")
    payload["principle_hints"] = [
        {
            "hint_id": DIRECT_WORK_FRAME_ID,
            "principle": "other",
            "scope_ids": [],
            "evidence_refs": [],
            "model_confidence": None,
        }
    ]
    colliding = MechanicsProblemDraftV1.model_validate(payload)
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        colliding,
        ProfileId.direct_constant_force_work,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is not ApplicationOutcome.applied
    assert application.draft == colliding
