"""B32: exact spring natural-length energy closure through real Lane B.

The corpus fixtures are independently authored and contain no answers.  The
profile is selected from typed Draft structure only; case identity, family,
problem text, labels and expected values never enter planning or closure.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from engine.mechanics.spring_endpoint import (
    is_exact_zero_deformation_endpoint,
)
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ApplicationOutcome,
    TransactionAuthority,
    apply_complete_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import (
    CorpusV2AugmentationV1,
    EndpointCondition,
    EndpointConditionV2,
    SourceQuoteEvidenceV2,
)
from evaluation.phase56_stage7.corpus_v2.validation import (
    V2ValidationError,
    V2ValidationReason,
    validate_augmentation,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_authority import (
    build_lane_b_authority_bundle,
)
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
from evaluation.phase56_stage7.spring_natural_length import (
    read_spring_natural_length_source,
)
from support.phase56_stage7_corpus_fixtures import build_case


def _fact(
    role: str,
    semantic_key: str,
    raw_value: str,
    raw_unit: str,
    quote: str,
    subject_role: str,
    *,
    event_role: str | None = None,
) -> dict:
    return {
        "role": role,
        "semantic_key": semantic_key,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "evidence_quote": quote,
        "subject_role": subject_role,
        "segment_role": "motion_1",
        "event_role": event_role,
        "temporal_role": "initial" if event_role else "timeless",
        "direction": "unspecified" if role == "x" else "not_applicable",
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _gold(*, mass: str, stiffness: str, deformation: str) -> dict:
    mass_quote = f"질량은 {mass} kg"
    stiffness_quote = f"용수철 상수는 {stiffness} N/m"
    deformation_quote = f"용수철 변형량은 {deformation} m"
    return {
        "parse_status": "complete",
        "expected_system_type": "spring_energy",
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": [
            {"role": "object", "kind": "block", "label": "실험 블록"},
            {"role": "spring", "kind": "spring", "label": "실험 용수철"},
            {"role": "surface", "kind": "surface", "label": "실험 수평면"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["object", "spring"],
                "motion_model": "energy_interval",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "release",
                "subject_roles": ["object", "spring"],
                "segment_role": "motion_1",
                "evidence_quote": "정지 상태로 놓는다",
            },
            {
                "role": "finish",
                "kind": "finish",
                "subject_roles": ["object", "spring"],
                "segment_role": "motion_1",
                "evidence_quote": "자연길이가 되는 순간",
            },
        ],
        "explicit_facts": [
            _fact("mass", "mass", mass, "kg", mass_quote, "object"),
            _fact(
                "k",
                "spring_constant",
                stiffness,
                "N/m",
                stiffness_quote,
                "spring",
            ),
            _fact(
                "x",
                "displacement",
                deformation,
                "m",
                deformation_quote,
                "spring",
                event_role="start",
            ),
        ],
        "relations": [
            {
                "role": "spring_rel",
                "kind": "attached_to_spring",
                "participant_roles": ["object", "spring"],
                "segment_role": "motion_1",
            },
            {
                "role": "surface_rel",
                "kind": "slides_on",
                "participant_roles": ["object", "surface"],
                "segment_role": "motion_1",
            },
        ],
        "assumption_proposals": [
            {
                "role": "friction",
                "kind": "frictionless",
                "subject_role": "object",
                "segment_role": "motion_1",
                "supporting_quote": "마찰 없는 수평면",
                "server_value_only": True,
            },
            {
                "role": "rest",
                "kind": "starts_from_rest",
                "subject_role": "object",
                "segment_role": "motion_1",
                "supporting_quote": "정지 상태로 놓는다",
                "server_value_only": True,
            },
        ],
        "queries": [
            {
                "role": "q1",
                "output_key": "final_velocity",
                "subject_role": "object",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": "finish",
            }
        ],
        "answers": [],
        "expected_failure_codes": [],
    }


def _case(
    *,
    mass: str = "3",
    stiffness: str = "240",
    deformation: str = "0.18",
) -> PublicCorpusCaseV1:
    record = build_case(
        index=32,
        split="public_dev",
        family="spring_energy",
        future_terminal="accepted",
        with_answer=False,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = (
        "실험 블록이 마찰 없는 수평면에서 실험 용수철에 연결되어 있다. "
        f"질량은 {mass} kg이고 용수철 상수는 {stiffness} N/m이다. "
        f"용수철 변형량은 {deformation} m이다. 정지 상태로 놓는다. "
        "자연길이가 되는 순간 실험 블록의 속력을 구하여라."
    )
    record["gold"] = {
        **record["gold"],
        **_gold(mass=mass, stiffness=stiffness, deformation=deformation),
    }
    return PublicCorpusCaseV1(**record)


def _endpoint(
    identifier: str,
    condition: EndpointCondition,
    *,
    evidence_id: str = "v2_natural_quote",
) -> EndpointConditionV2:
    return EndpointConditionV2(
        endpoint_id=identifier,
        condition=condition,
        boundary_event_id="finish",
        subject_id="spring",
        interval_id="motion_1",
        evidence_refs=(evidence_id,),
    )


def _augmentation(
    *conditions: tuple[str, EndpointCondition],
    quote: str = "자연길이가 되는 순간",
    evidence_id: str = "v2_natural_quote",
) -> CorpusV2AugmentationV1:
    selected = conditions or (
        ("v2_natural_endpoint", EndpointCondition.reaches_natural_length),
    )
    return CorpusV2AugmentationV1(
        source_quotes=(
            SourceQuoteEvidenceV2(evidence_id=evidence_id, quote=quote),
        ),
        endpoint_conditions=tuple(
            _endpoint(identifier, condition, evidence_id=evidence_id)
            for identifier, condition in selected
        ),
    )


def _validation_kwargs(draft: MechanicsProblemDraftV1) -> dict:
    return {
        "known_entity_ids": [item.entity_id for item in draft.entities],
        "known_interval_ids": [
            item.interval_id for item in draft.motion_intervals
        ],
        "known_event_ids": [item.event_id for item in draft.events],
        "known_evidence_ids": [
            item.evidence_id for item in draft.source_evidence
        ],
        "known_interaction_ids": [
            item.interaction_id for item in draft.interactions
        ],
        "known_query_ids": [item.query_id for item in draft.queries],
    }


def _projection(
    *,
    mass: str = "3",
    stiffness: str = "240",
    deformation: str = "0.18",
    conditions: tuple[tuple[str, EndpointCondition], ...] = (),
):
    case = _case(mass=mass, stiffness=stiffness, deformation=deformation)
    baseline = project_case_to_draft(case)
    assert baseline.terminal is DraftProjectionTerminal.projected
    augmentation = _augmentation(*conditions)
    validate_augmentation(augmentation, **_validation_kwargs(baseline.draft))
    payload = project_augmentation(
        baseline.draft.model_dump(mode="json", warnings="none"),
        augmentation,
        problem_text=case.problem_text,
    )
    return replace(
        baseline,
        draft=MechanicsProblemDraftV1.model_validate(payload),
    )


def _application(projection):
    bundle = build_lane_b_authority_bundle(projection)
    plan = plan_complete_profile(
        ProfileId.spring_energy_natural_length,
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    authority = TransactionAuthority(
        approved_assumption_ids=frozenset(bundle.approved_assumption_ids),
        authorized_assumptions=bundle.authorization_map(),
    )
    application = apply_complete_profile(plan, projection.draft, authority)
    assert application.outcome is ApplicationOutcome.applied
    return application


@pytest.mark.parametrize(
    ("index", "mass", "stiffness", "deformation", "expected"),
    [
        (1, "3", "240", "0.18", 1.6099689438),
        (2, "5", "300", "0.22", 1.7041126723),
        (3, "2.5", "180", "0.15", 1.2727922061),
    ],
)
def test_exact_natural_length_solves_three_public_equivalent_shapes(
    index: int,
    mass: str,
    stiffness: str,
    deformation: str,
    expected: float,
) -> None:
    projection = _projection(
        mass=mass,
        stiffness=stiffness,
        deformation=deformation,
    )
    assert read_spring_natural_length_source(
        projection.draft.model_dump(mode="json", warnings="none")
    ) is not None
    plan = plan_complete_profile(
        ProfileId.spring_energy_natural_length,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete

    result = run_lane_b_case(
        projection,
        execution_token=deterministic_token(320 + index),
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, abs=1e-10)
    assert result.verified_candidate_count == 1
    assert {
        "kinetic_energy",
        "mechanical_energy_conservation",
        "spring_potential",
        "spring_zero_deformation_endpoint",
        "state_at_rest",
    } <= set(result.applied_law_ids)


def test_exact_zero_deformation_has_natural_length_parity() -> None:
    natural = _projection()
    zero = _projection(
        conditions=(
            ("v2_zero_endpoint", EndpointCondition.zero_spring_deformation),
        )
    )
    natural_result = run_lane_b_case(
        natural, execution_token=deterministic_token(324)
    )
    zero_result = run_lane_b_case(
        zero, execution_token=deterministic_token(325)
    )
    assert natural_result.terminal is zero_result.terminal is LaneBTerminal.solved
    assert zero_result.answer_value_si == pytest.approx(
        natural_result.answer_value_si, abs=1e-12
    )
    assert zero_result.applied_law_ids == natural_result.applied_law_ids


@pytest.mark.parametrize(
    ("deformation", "expected"),
    [("0.14", 0.14 * (240.0 / 3.0) ** 0.5),
     ("-0.12", 0.12 * (240.0 / 3.0) ** 0.5)],
    ids=("initially_extended", "initially_compressed_signed"),
)
def test_initial_deformation_sign_is_preserved_before_energy_squaring(
    deformation: str, expected: float
) -> None:
    projection = _projection(deformation=deformation)
    application, result = run_lane_b_case_with_selected_profile(
        projection,
        ProfileId.spring_energy_natural_length,
        execution_token=deterministic_token(326 if deformation[0] != "-" else 327),
    )
    assert application is not None and application.applied
    initial = next(
        item
        for item in application.draft.quantities
        if item.quantity_id == "qty_x"
    )
    assert initial.raw_value == deformation
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, abs=1e-12)


def test_redundant_endpoint_spellings_are_an_order_independent_no_op() -> None:
    forward = _projection(
        conditions=(
            ("v2_natural_endpoint", EndpointCondition.reaches_natural_length),
            ("v2_zero_endpoint", EndpointCondition.zero_spring_deformation),
        )
    )
    reverse = _projection(
        conditions=(
            ("v2_zero_endpoint", EndpointCondition.zero_spring_deformation),
            ("v2_natural_endpoint", EndpointCondition.reaches_natural_length),
        )
    )
    assert forward.draft.model_dump(mode="json", warnings="none") == (
        reverse.draft.model_dump(mode="json", warnings="none")
    )
    endpoints = [
        item
        for item in forward.draft.state_conditions
        if is_exact_zero_deformation_endpoint(item.state)
    ]
    assert len(endpoints) == 1


def test_complete_transaction_includes_all_four_interval_energy_terms() -> None:
    projection = _projection()
    application, result = run_lane_b_case_with_selected_profile(
        projection,
        ProfileId.spring_energy_natural_length,
        execution_token=deterministic_token(328),
    )
    assert application is not None and application.applied
    energies = [
        item for item in application.draft.quantities if item.role.value == "energy"
    ]
    assert len(energies) == 4
    assert {item.subject_id for item in energies} == {"object", "spring"}
    assert {item.event_id for item in energies} == {"start", "finish"}
    assert {item.interval_id for item in energies} == {"motion_1"}
    assert all(item.raw_value is item.raw_unit is None for item in energies)
    assert result.terminal is LaneBTerminal.solved
    assert "mechanical_energy_conservation" in result.applied_law_ids


def test_transaction_creates_no_numeric_answer_force_energy_or_length() -> None:
    projection = _projection()
    application = _application(projection)
    created = set(application.created_record_ids)
    created_quantities = [
        item for item in application.draft.quantities if item.quantity_id in created
    ]
    assert len(created_quantities) == 5
    assert all(
        item.raw_value is None and item.raw_unit is None
        for item in created_quantities
    )
    final_speed = next(
        item
        for item in application.draft.quantities
        if item.quantity_id == "qty_unknown_q1"
    )
    final_deformation = next(
        item
        for item in application.draft.quantities
        if item.quantity_id == "qty_closure_spring_deformation_end"
    )
    assert final_speed.raw_value is final_speed.raw_unit is None
    assert final_deformation.raw_value is final_deformation.raw_unit is None
    assert all(item.role.value != "force" for item in application.draft.quantities)
    derived = next(
        item
        for item in application.draft.assumptions
        if item.assumption_id == "asm_closure_spring_no_energy_loss"
    )
    assert derived.proposed_role is None
    assert derived.proposed_value is None
    assert derived.proposed_unit is None


def test_transaction_cannot_mint_or_widen_assumption_authority() -> None:
    projection = _projection()
    plan = plan_complete_profile(
        ProfileId.spring_energy_natural_length,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    without_authority = apply_complete_profile(plan, projection.draft)
    assert without_authority.outcome is ApplicationOutcome.rejected
    assert without_authority.draft is projection.draft
    assert without_authority.created_record_ids == ()

    bundle = build_lane_b_authority_bundle(projection)
    incomplete_map = dict(bundle.authorization_map())
    incomplete_map.pop("asm_rest")
    incomplete = apply_complete_profile(
        plan,
        projection.draft,
        TransactionAuthority(
            approved_assumption_ids=frozenset(bundle.approved_assumption_ids),
            authorized_assumptions=incomplete_map,
        ),
    )
    assert incomplete.outcome is ApplicationOutcome.rejected
    assert incomplete.draft is projection.draft
    assert incomplete.created_record_ids == ()


def test_reader_ignores_family_case_text_labels_metadata_and_answers() -> None:
    projection = _projection()
    payload = projection.draft.model_dump(mode="json", warnings="none")
    expected = read_spring_natural_length_source(payload)
    assert expected is not None
    routed = deepcopy(payload)
    routed.update(
        case_id="B32_ROUTING_ATTACK",
        family="non_spring_energy",
        problem_text="relaxed finish natural length answer 999",
        answers=[{"numeric": 999.0, "unit": "m/s"}],
    )
    routed["metadata"].update(system_type="other", subtype="spring_energy")
    for index, entity in enumerate(routed["entities"]):
        entity["label"] = f"routing label {index}"
    assert read_spring_natural_length_source(routed) == expected


def test_record_order_does_not_change_the_real_solution() -> None:
    canonical = _projection()
    payload = canonical.draft.model_dump(mode="json", warnings="none")
    for field in (
        "source_evidence",
        "entities",
        "events",
        "symbols",
        "quantities",
        "state_conditions",
        "assumptions",
    ):
        payload[field].reverse()
    reordered = replace(
        canonical,
        draft=MechanicsProblemDraftV1.model_validate(payload),
    )
    first = run_lane_b_case(
        canonical, execution_token=deterministic_token(329)
    )
    second = run_lane_b_case(
        reordered, execution_token=deterministic_token(330)
    )
    assert first.terminal is second.terminal is LaneBTerminal.solved
    assert second.answer_value_si == pytest.approx(first.answer_value_si, abs=1e-12)
    assert second.applied_law_ids == first.applied_law_ids
    assert second.calculation_fingerprint == first.calculation_fingerprint


_B32_ATTACKS = (
    "01_generic_finish_only",
    "02_inactive_only",
    "03_raw_relaxed_substring_only",
    "04_missing_spring_subject",
    "05_other_spring_endpoint",
    "06_other_body_event_endpoint",
    "07_interval_mismatch",
    "08_missing_initial_deformation",
    "09_absolute_length_only",
    "10_natural_length_datum_without_current_relation",
    "11_missing_evidence",
    "12_quote_absent_from_source",
    "13_mixed_invalid_evidence",
    "14_event_to_interval_widening",
    "15_interval_to_endpoint_narrowing",
    "16_multiple_spring_ambiguity",
    "17_missing_spring_body_relation",
    "18_endpoint_axis_direction_ambiguity",
    "19_numeric_final_speed",
    "20_answer_based_deformation",
    "21_natural_length_zero_assumption",
    "22_force_zero_only_inference",
    "23_inactive_only_inference",
    "24_family_case_text_routing",
    "25_cross_energy_interval_authority",
    "26_generic_energy_profile_widening",
    "27_raw_text_order_endpoint_guess",
    "28_b26_endpoint_conflict_regression",
    "29_other_spring_ownership",
    "30_missing_endpoint_evidence",
    "31_approximate_zero_promotion",
    "32_non_spring_energy_family_leakage",
)


def _attack_payload(attack: str) -> dict:
    payload = _projection().draft.model_dump(mode="json", warnings="none")

    def quantity(role: str, event_id: str | None = None) -> dict:
        return next(
            item
            for item in payload["quantities"]
            if item["role"] == role
            and (event_id is None or item["event_id"] == event_id)
        )

    def endpoint() -> dict:
        return next(
            item
            for item in payload["state_conditions"]
            if item["kind"] == "boundary"
        )

    def remove_endpoint() -> None:
        payload["state_conditions"] = [
            item for item in payload["state_conditions"] if item["kind"] != "boundary"
        ]

    def remove_quantity(item: dict) -> None:
        payload["quantities"].remove(item)
        payload["symbols"] = [
            symbol
            for symbol in payload["symbols"]
            if symbol["quantity_id"] != item["quantity_id"]
        ]

    if attack == "01_generic_finish_only":
        remove_endpoint()
    elif attack == "02_inactive_only":
        endpoint()["state"] = "inactive"
    elif attack == "03_raw_relaxed_substring_only":
        remove_endpoint()
        payload["problem_text"] = "the spring is relaxed at finish"
    elif attack == "04_missing_spring_subject":
        endpoint()["subject_id"] = None
    elif attack == "05_other_spring_endpoint":
        other = deepcopy(next(item for item in payload["entities"] if item["entity_id"] == "spring"))
        other["entity_id"] = "spring_other"
        payload["entities"].append(other)
        endpoint()["subject_id"] = "spring_other"
    elif attack == "06_other_body_event_endpoint":
        endpoint().update(subject_id="object", event_id="start")
    elif attack == "07_interval_mismatch":
        endpoint()["interval_id"] = "motion_other"
    elif attack == "08_missing_initial_deformation":
        remove_quantity(quantity("displacement"))
    elif attack == "09_absolute_length_only":
        quantity("displacement")["role"] = "length"
    elif attack == "10_natural_length_datum_without_current_relation":
        quantity("displacement")["event_id"] = None
        payload["natural_length_datum"] = "0.18 m"
    elif attack == "11_missing_evidence":
        quantity("stiffness")["evidence_refs"] = []
    elif attack == "13_mixed_invalid_evidence":
        endpoint()["evidence_refs"].append("v2_unknown_evidence")
    elif attack == "14_event_to_interval_widening":
        endpoint()["event_id"] = None
    elif attack == "15_interval_to_endpoint_narrowing":
        quantity("displacement")["interval_id"] = None
    elif attack == "16_multiple_spring_ambiguity":
        other = deepcopy(next(item for item in payload["entities"] if item["entity_id"] == "spring"))
        other["entity_id"] = "spring_other"
        payload["entities"].append(other)
    elif attack == "17_missing_spring_body_relation":
        payload["interactions"] = []
    elif attack == "18_endpoint_axis_direction_ambiguity":
        endpoint()["expression"] = {"axis": "x", "direction": "unknown"}
    elif attack == "19_numeric_final_speed":
        final = quantity("velocity", "finish")
        final.update(
            raw_value="1.6",
            raw_unit="m/s",
            provenance="explicit_source",
            evidence_refs=["v2_natural_quote"],
        )
    elif attack == "20_answer_based_deformation":
        quantity("displacement")["provenance"] = "inferred"
        payload["answers"] = [{"numeric": 1.6099689438, "unit": "m/s"}]
    elif attack == "21_natural_length_zero_assumption":
        payload["assumptions"].append(
            {
                "assumption_id": "attack_natural_length_zero",
                "kind": "natural_length_zero",
                "subject_id": "spring",
                "interval_id": "motion_1",
                "disposition": "approved",
                "proposed_role": "displacement",
                "proposed_value": "0",
                "proposed_unit": "m",
                "evidence_refs": ["v2_natural_quote"],
            }
        )
    elif attack == "22_force_zero_only_inference":
        remove_endpoint()
        force = deepcopy(quantity("mass"))
        force.update(
            quantity_id="attack_force",
            symbol_id="attack_force_symbol",
            role="force",
            subject_id="spring",
            raw_value="0",
            raw_unit="N",
        )
        symbol = deepcopy(payload["symbols"][0])
        symbol.update(
            quantity_id="attack_force",
            symbol_id="attack_force_symbol",
        )
        payload["quantities"].append(force)
        payload["symbols"].append(symbol)
    elif attack == "23_inactive_only_inference":
        endpoint()["state"] = "inactive"
        payload["problem_text"] = "spring no longer acts"
    elif attack == "24_family_case_text_routing":
        remove_endpoint()
        payload.update(
            case_id="B32_ATTACK",
            family="spring_energy",
            problem_text="natural length relaxed final speed",
        )
    elif attack == "25_cross_energy_interval_authority":
        payload["assumptions"][0]["interval_id"] = "motion_other"
    elif attack == "26_generic_energy_profile_widening":
        remove_endpoint()
        payload["principle_hints"].append(
            {"principle_hint_id": "attack_energy", "principle": "energy"}
        )
    elif attack == "27_raw_text_order_endpoint_guess":
        remove_endpoint()
        payload["events"].reverse()
        payload["source_evidence"].reverse()
        payload["problem_text"] = "finish then release; relaxed appears first"
    elif attack == "29_other_spring_ownership":
        quantity("stiffness")["subject_id"] = "surface"
    elif attack == "30_missing_endpoint_evidence":
        endpoint()["evidence_refs"] = []
    elif attack == "31_approximate_zero_promotion":
        endpoint()["expression"] = {
            "relation": "approximately_equal",
            "value": 1.0e-9,
        }
    elif attack == "32_non_spring_energy_family_leakage":
        spring = next(item for item in payload["entities"] if item["entity_id"] == "spring")
        spring["primitive"] = "particle"
        payload["interactions"][0]["kind"] = "applied_force"
    else:  # pragma: no cover - special v2 gates are handled before this helper.
        raise AssertionError(attack)
    return payload


def _attack_gate(attack: str) -> str:
    if attack == "12_quote_absent_from_source":
        case = _case()
        baseline = project_case_to_draft(case)
        bad = _augmentation(
            ("v2_natural_endpoint", EndpointCondition.reaches_natural_length),
            quote="출처에 없는 자연길이 문구",
            evidence_id="v2_absent_quote",
        )
        with pytest.raises(V2ValidationError) as caught:
            project_augmentation(
                baseline.draft.model_dump(mode="json", warnings="none"),
                bad,
                problem_text=case.problem_text,
            )
        return caught.value.reason.value
    if attack == "28_b26_endpoint_conflict_regression":
        baseline = project_case_to_draft(_case())
        conflicting = _augmentation(
            ("v2_natural_endpoint", EndpointCondition.reaches_natural_length),
            ("v2_rest_endpoint", EndpointCondition.comes_to_rest),
        )
        with pytest.raises(V2ValidationError) as caught:
            validate_augmentation(
                conflicting,
                **_validation_kwargs(baseline.draft),
            )
        return caught.value.reason.value
    return (
        "spring_natural_length_exact_source_shape_refusal"
        if read_spring_natural_length_source(_attack_payload(attack)) is None
        else "spring_natural_length_complete"
    )


@pytest.mark.parametrize(
    ("attack", "expected_gate"),
    [
        (
            attack,
            "evidence_quote_not_in_source"
            if attack == "12_quote_absent_from_source"
            else (
                "duplicate_endpoint"
                if attack == "28_b26_endpoint_conflict_regression"
                else "spring_natural_length_exact_source_shape_refusal"
            ),
        )
        for attack in _B32_ATTACKS
    ],
    ids=_B32_ATTACKS,
)
def test_spring_natural_length_attack_matrix_fails_closed(
    attack: str, expected_gate: str
) -> None:
    assert _attack_gate(attack) == expected_gate
