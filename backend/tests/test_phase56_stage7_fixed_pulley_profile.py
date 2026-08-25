"""Stage 7: exact ideal fixed-pulley closure and aggregate readout."""
from __future__ import annotations

from copy import deepcopy

import pytest

from evaluation.phase56_stage7.complete_profile import ProfileId, plan_complete_profile
from evaluation.phase56_stage7.complete_profile_application import (
    FIXED_PULLEY_FRAME_ID,
    ApplicationOutcome,
    apply_selected_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionTerminal,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_authority import build_lane_b_authority_bundle
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)
from support.phase56_stage7_corpus_fixtures import build_case


TEXT = (
    "추 A와 추 B가 가볍고 늘어나지 않는 줄로 연결되어 마찰 없는 질량 무시 "
    "도르래에 걸려 있다. A의 질량은 2 kg이고 B의 질량은 5 kg이다. "
    "중력가속도는 9.81 m/s²로 사용한다. 계를 놓았을 때 두 물체의 "
    "가속도 크기를 구하여라."
)


def _fact(role: str, key: str, value: str, unit: str, quote: str, subject: str):
    return {
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


def _assumption(role: str, kind: str, quote: str):
    return {
        "role": role,
        "kind": kind,
        "subject_role": "system",
        "segment_role": "motion_1",
        "supporting_quote": quote,
        "server_value_only": True,
    }


def _gold(
    *,
    mass_a: str = "2",
    mass_b: str = "5",
    query_key: str = "acceleration",
    component: str = "magnitude",
    pulley_actor: bool = False,
    include_inertia: bool = False,
    include_frictionless: bool = True,
    extra_pulley: bool = False,
) -> dict:
    entities = [
        {"role": "system", "kind": "system", "label": "아트우드 계"},
        {"role": "mass_a", "kind": "block", "label": "추 A"},
        {"role": "mass_b", "kind": "block", "label": "추 B"},
        {"role": "pulley", "kind": "pulley", "label": "도르래"},
        {"role": "rope", "kind": "rope", "label": "줄"},
    ]
    if extra_pulley:
        entities.append({"role": "pulley_2", "kind": "pulley", "label": "보조 도르래"})
    actors = ["system", "mass_a", "mass_b"]
    if pulley_actor:
        actors.append("pulley")
    facts = [
        _fact("m1", "mass_1", mass_a, "kg", f"A의 질량은 {mass_a} kg", "mass_a"),
        _fact("m2", "mass_2", mass_b, "kg", f"B의 질량은 {mass_b} kg", "mass_b"),
    ]
    if include_inertia:
        facts.extend(
            [
                _fact("I", "moment_of_inertia", "0.12", "kg·m²", "관성모멘트는 0.12 kg·m²", "pulley"),
                _fact("R", "radius", "0.2", "m", "반지름은 0.2 m", "pulley"),
            ]
        )
    assumptions = [
        _assumption("rope_mass", "massless_rope", "가볍고 늘어나지 않는 줄"),
        _assumption("rope_length", "inextensible_rope", "가볍고 늘어나지 않는 줄"),
        _assumption("pulley_mass", "massless_pulley", "질량 무시 도르래"),
        _assumption("gravity", "constant_gravity", "중력가속도는 9.81 m/s²로 사용한다"),
    ]
    if include_frictionless:
        assumptions.insert(3, _assumption("friction", "frictionless", "마찰 없는"))
    return {
        "entities": entities,
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": actors,
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "release",
                "kind": "release",
                "subject_roles": ["system", "mass_a", "mass_b"],
                "segment_role": "motion_1",
                "evidence_quote": "계를 놓았을 때",
            }
        ],
        "explicit_facts": facts,
        "relations": [
            {
                "role": "rope_conn",
                "kind": "connected_by_rope",
                "participant_roles": ["mass_a", "mass_b"],
                "segment_role": "motion_1",
            },
            {
                "role": "over",
                "kind": "passes_over_pulley",
                "participant_roles": ["mass_a", "mass_b", "pulley"],
                "segment_role": "motion_1",
            },
        ],
        "assumption_proposals": assumptions,
        "queries": [
            {
                "role": "q1",
                "output_key": query_key,
                "subject_role": "system",
                "segment_role": "motion_1",
                "component": component,
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }


def _case(text: str = TEXT, **gold_overrides) -> PublicCorpusCaseV1:
    mass_a = str(gold_overrides.get("mass_a", "2"))
    mass_b = str(gold_overrides.get("mass_b", "5"))
    text = text.replace("A의 질량은 2 kg", f"A의 질량은 {mass_a} kg")
    text = text.replace("B의 질량은 5 kg", f"B의 질량은 {mass_b} kg")
    if gold_overrides.get("include_inertia"):
        text += " 도르래의 관성모멘트는 0.12 kg·m²이고 반지름은 0.2 m이다."
    record = build_case(
        index=48,
        split="public_dev",
        family="pulley_atwood",
        future_terminal="accepted",
        with_answer=False,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = text
    record["gold"] = {**record["gold"], **_gold(**gold_overrides), "answers": []}
    return PublicCorpusCaseV1(**record)


def _project(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, projection.sanitized_reason
    assert projection.draft is not None
    return projection


def _run(case: PublicCorpusCaseV1, index: int = 48):
    projection = _project(case)
    return projection, run_lane_b_case(
        projection,
        execution_token=deterministic_token(index),
    )


def test_projection_scopes_only_the_exact_ideal_fixed_pulley_authority() -> None:
    projection = _project(_case())
    scoped = {
        (item.kind, item.subject_id)
        for item in projection.draft.assumptions
        if item.assumption_id.startswith("asm_closure_fixed_pulley_")
    }
    assert scoped == {
        ("massless_rope", "rope"),
        ("inextensible_rope", "rope"),
        ("fixed_pulley", "pulley"),
        ("ideal_massless_frictionless_pulley", "pulley"),
    }
    assert all(item.evidence_refs for item in projection.draft.assumptions if item.assumption_id.startswith("asm_closure_fixed_pulley_"))


@pytest.mark.parametrize(
    ("mass_a", "mass_b", "expected"),
    (("2", "5", 4.204285714285714), ("4", "7", 2.6754545454545453)),
)
def test_fixed_pulley_acceleration_uses_existing_generic_laws(
    mass_a: str, mass_b: str, expected: float
) -> None:
    _, result = _run(_case(mass_a=mass_a, mass_b=mass_b))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)
    assert result.candidate_count == result.verified_candidate_count == 1
    assert set(result.applied_law_ids) == {
        "particle_weight",
        "particle_newton_second",
        "rope_massless_tension",
        "rope_fixed_pulley_motion",
        "fixed_pulley_common_acceleration_readout",
    }
    assert result.equation_count == 7
    assert {kind for kind, outcome in result.verification_checks if outcome == "passed"} >= {
        "equation_residual",
        "unit_consistency",
        "query_binding",
        "source_evidence",
        "constraint",
    }


def test_transaction_is_complete_and_preserves_primitives_and_query() -> None:
    projection = _project(_case())
    before = projection.draft.model_dump(mode="json", warnings="none")
    authority = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.fixed_pulley,
        approved_assumption_ids=authority.approved_assumption_ids,
        authorized_assumptions=authority.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    after = application.draft
    assert {item.entity_id: item.primitive.value for item in after.entities} == {
        item["entity_id"]: item["primitive"] for item in before["entities"]
    }
    assert after.queries[0].target.subject_id == "system"
    assert after.queries[0].target.component.value == "magnitude"
    assert after.queries[0].target.frame_id is None
    assert {item.frame_id for item in after.reference_frames} == {FIXED_PULLEY_FRAME_ID}
    assert len(after.interactions) == 3
    assert len(after.geometry) == 3
    assert len(after.state_conditions) == 2


def test_tension_query_is_not_relabelled_from_generic_force() -> None:
    _, result = _run(_case(query_key="tension"), 49)
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.candidate_count == 0


@pytest.mark.parametrize(
    "overrides",
    (
        {"pulley_actor": True, "include_inertia": True},
        {"include_frictionless": False},
        {"extra_pulley": True},
        {"mass_a": "5", "mass_b": "5"},
        {"component": "x"},
    ),
)
def test_near_misses_fail_closed_without_numeric_output(overrides: dict) -> None:
    projection, result = _run(_case(**overrides), 30)
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.candidate_count == 0
    if overrides.get("pulley_actor") or overrides.get("include_frictionless") is False or overrides.get("extra_pulley"):
        assert not any(
            item.assumption_id.startswith("asm_closure_fixed_pulley_")
            for item in projection.draft.assumptions
        )


def test_generated_id_collision_abandons_the_whole_transaction() -> None:
    case = _case()
    gold = case.gold.model_dump(mode="json")
    gold["entities"].append(
        {"role": FIXED_PULLEY_FRAME_ID, "kind": "other", "label": "unrelated"}
    )
    record = case.model_dump(mode="json")
    record["gold"] = gold
    collision = PublicCorpusCaseV1(**record)
    projection = _project(collision)
    before = projection.draft.model_dump(mode="json", warnings="none")
    authority = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.fixed_pulley,
        approved_assumption_ids=authority.approved_assumption_ids,
        authorized_assumptions=authority.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.rejected
    assert application.draft.model_dump(mode="json", warnings="none") == before


def test_entity_fact_relation_and_participant_order_do_not_change_the_answer() -> None:
    baseline_case = _case()
    baseline = _run(baseline_case)[1]
    record = baseline_case.model_dump(mode="json")
    gold = deepcopy(record["gold"])
    for field in ("entities", "explicit_facts", "relations", "assumption_proposals"):
        gold[field] = list(reversed(gold[field]))
    for relation in gold["relations"]:
        relation["participant_roles"] = list(reversed(relation["participant_roles"]))
    record["gold"] = gold
    permuted = PublicCorpusCaseV1(**record)
    result = _run(permuted)[1]
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == baseline.answer_value_si
    assert result.calculation_fingerprint == baseline.calculation_fingerprint
