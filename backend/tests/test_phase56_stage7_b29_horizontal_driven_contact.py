"""B29: driven horizontal kinetic friction through the real Lane B flow.

The fixtures are independently authored and deliberately vary their numbers.
The package is selected from typed Draft structure only; no assertion or helper
passes a family, case identity, expected answer, or solver choice into closure.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ApplicationOutcome,
    apply_complete_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.corpus_v2.projection import project_augmentation
from evaluation.phase56_stage7.corpus_v2.records import CorpusV2AugmentationV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.horizontal_driven_contact import (
    read_horizontal_driven_sliding_source,
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
from support.phase56_stage7_corpus_fixtures import build_case


def _fact(
    role: str,
    semantic_key: str,
    raw_value: str,
    raw_unit: str,
    quote: str,
    *,
    direction: str = "not_applicable",
) -> dict:
    return {
        "role": role,
        "semantic_key": semantic_key,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "evidence_quote": quote,
        "subject_role": "object" if role != "mu" else "surface",
        "segment_role": "motion_1",
        "event_role": None,
        "temporal_role": "during" if role == "force" else "timeless",
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _gold(
    *, mass: str, force: str, coefficient: str, ambiguous: bool = False,
    redundant_angle: bool = False,
) -> dict:
    explicit = [
        _fact("mass", "mass", mass, "kg", f"질량은 {mass} kg"),
        _fact(
            "force",
            "force",
            force,
            "N",
            f"수평 힘 {force} N",
            direction="right",
        ),
    ]
    assumptions = []
    if not ambiguous:
        explicit.append(
            _fact(
                "mu",
                "coefficient_of_friction",
                coefficient,
                "",
                f"운동마찰계수는 {coefficient}",
            )
        )
        if redundant_angle:
            explicit.append(
                {
                    "role": "support_angle",
                    "semantic_key": "angle",
                    "raw_value": "0",
                    "raw_unit": "deg",
                    "evidence_quote": "바닥 각도는 0 deg",
                    "subject_role": "surface",
                    "segment_role": "motion_1",
                    "event_role": None,
                    "temporal_role": "timeless",
                    "direction": "not_applicable",
                    "relevance": "solver_input",
                    "occurrence_index": 0,
                    "quantity_occurrence_index": 0,
                }
            )
        assumptions.append(
            {
                "role": "gravity",
                "kind": "constant_gravity",
                "subject_role": "object",
                "segment_role": "motion_1",
                "supporting_quote": "중력가속도는 9.81 m/s²로 사용한다",
                "server_value_only": True,
            }
        )
    return {
        "parse_status": "ambiguous" if ambiguous else "complete",
        "expected_system_type": "horizontal_friction_force",
        "phase55_expected_terminal": (
            "needs_confirmation" if ambiguous else "solver_gap"
        ),
        "future_expected_terminal": (
            "needs_confirmation" if ambiguous else "accepted"
        ),
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": [
            {"role": "object", "kind": "block", "label": "실험 상자"},
            {"role": "surface", "kind": "surface", "label": "수평 바닥"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["object"],
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": (
            []
            if ambiguous
            else [
                {
                    "role": "start",
                    "kind": "start",
                    "subject_roles": ["object"],
                    "segment_role": "motion_1",
                    "evidence_quote": None,
                }
            ]
        ),
        "explicit_facts": explicit,
        "relations": [
            {
                "role": "contact",
                "kind": "slides_on",
                "participant_roles": ["object", "surface"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": assumptions,
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "object",
                "segment_role": "motion_1",
                "component": "x",
                "event_role": None,
            }
        ],
        "answers": [],
        "expected_failure_codes": (
            ["missing_friction_state_or_coefficient"] if ambiguous else []
        ),
    }


def _case(
    *, mass: str = "12", force: str = "70", coefficient: str = "0.2",
    motion_word: str = "오른쪽", ambiguous: bool = False,
    redundant_angle: bool = False,
) -> PublicCorpusCaseV1:
    record = build_case(
        index=29,
        split="public_dev",
        family="horizontal_friction_force",
        future_terminal="accepted",
        with_answer=False,
    )
    record["split"] = PublicSplit.public_dev
    if ambiguous:
        record["problem_text"] = (
            f"질량은 {mass} kg인 상자가 거친 수평면 위에서 오른쪽으로 "
            f"수평 힘 {force} N을 받는다. 가속도를 구하여라. "
            "마찰계수나 마찰력은 주어지지 않았다."
        )
    else:
        record["problem_text"] = (
            f"실험 상자가 수평 바닥 위에서 {motion_word}으로 움직이고 있다. "
            f"실험 상자의 질량은 {mass} kg이고 오른쪽으로 수평 힘 {force} N이 "
            f"작용한다. 운동마찰계수는 {coefficient}이다. "
            + ("바닥 각도는 0 deg이다. " if redundant_angle else "")
            + "중력가속도는 9.81 m/s²로 사용한다. 가속도 x성분을 구하여라."
        )
    record["gold"] = {
        **record["gold"],
        **_gold(
            mass=mass,
            force=force,
            coefficient=coefficient,
            ambiguous=ambiguous,
            redundant_angle=redundant_angle,
        ),
    }
    return PublicCorpusCaseV1(**record)


def _augmentation(
    *, motion_word: str, motion_sign: int, tangent_world_sign: int = 1,
    with_motion: bool = True,
):
    payload = {
        "source_quotes": [
            {
                "evidence_id": "v2_ev_horizontal",
                "quote": "수평 바닥",
                "occurrence_index": 0,
            },
            *(
                [
                    {
                        "evidence_id": "v2_ev_motion",
                        "quote": f"{motion_word}으로 움직이고 있다",
                        "occurrence_index": 0,
                    }
                ]
                if with_motion
                else []
            ),
        ],
        "reference_frames": [
            {
                "frame_id": "v2_world",
                "frame_type": "world_cartesian",
                "origin_kind": "world",
                "subject_id": "surface",
                "axes": [
                    {
                        "axis": "x",
                        "sense": "along_surface_forward",
                        "bound_frame_id": "v2_world",
                        "bound_axis": "x",
                        "bound_sign": 1,
                        "evidence_refs": ["v2_ev_horizontal"],
                    },
                    {
                        "axis": "y",
                        "sense": "up_the_page",
                        "bound_frame_id": "v2_world",
                        "bound_axis": "y",
                        "bound_sign": 1,
                        "evidence_refs": ["v2_ev_horizontal"],
                    },
                ],
                "evidence_refs": ["v2_ev_horizontal"],
            },
            {
                "frame_id": "v2_support",
                "frame_type": "surface_tangent_normal",
                "origin_kind": "entity",
                "subject_id": "surface",
                "parent_frame_id": "v2_world",
                "axes": [
                    {
                        "axis": "tangent",
                        "sense": "along_surface_forward",
                        "anchor_entity_id": "surface",
                        "bound_frame_id": "v2_world",
                        "bound_axis": "x",
                        "bound_sign": tangent_world_sign,
                        "evidence_refs": ["v2_ev_horizontal"],
                    },
                    {
                        "axis": "normal",
                        "sense": "away_from_surface",
                        "anchor_entity_id": "surface",
                        "bound_frame_id": "v2_world",
                        "bound_axis": "y",
                        "bound_sign": 1,
                        "evidence_refs": ["v2_ev_horizontal"],
                    },
                ],
                "evidence_refs": ["v2_ev_horizontal"],
            },
        ],
        "motion_senses": (
            [
                {
                    "sense_id": "v2_motion",
                    # ``sign`` is the binding authority; keep the descriptive
                    # sense neutral so the projection applies it exactly once.
                    "sense": "along_axis_positive",
                    "subject_id": "object",
                    "interval_id": "motion_1",
                    "frame_id": "v2_support",
                    "axis": "tangent",
                    "sign": motion_sign,
                    "evidence_refs": ["v2_ev_motion"],
                }
            ]
            if with_motion
            else []
        ),
    }
    return CorpusV2AugmentationV1.model_validate_json(json.dumps(payload))


def _projection(
    *, mass: str = "12", force: str = "70", coefficient: str = "0.2",
    motion_word: str = "오른쪽", motion_sign: int = 1, with_motion: bool = True,
    tangent_world_sign: int = 1, redundant_angle: bool = False,
):
    case = _case(
        mass=mass,
        force=force,
        coefficient=coefficient,
        motion_word=motion_word,
        redundant_angle=redundant_angle,
    )
    baseline = project_case_to_draft(case)
    assert baseline.terminal is DraftProjectionTerminal.projected
    payload = project_augmentation(
        baseline.draft.model_dump(mode="json", warnings="none"),
        _augmentation(
            motion_word=motion_word,
            motion_sign=motion_sign,
            tangent_world_sign=tangent_world_sign,
            with_motion=with_motion,
        ),
        problem_text=case.problem_text,
    )
    return replace(
        baseline,
        draft=MechanicsProblemDraftV1.model_validate(payload),
    )


@pytest.mark.parametrize(
    ("mass", "force", "coefficient", "expected"),
    [
        ("12", "70", "0.2", 3.8713333333333333),
        ("25", "160", "0.25", 3.9475),
        ("8", "50", "0.15", 4.7785),
    ],
)
def test_driven_horizontal_slide_solves_through_real_lane_b(
    mass: str, force: str, coefficient: str, expected: float
) -> None:
    projection = _projection(mass=mass, force=force, coefficient=coefficient)

    plan = plan_complete_profile(
        ProfileId.horizontal_contact,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete

    result = run_lane_b_case(
        projection, execution_token=deterministic_token(int(mass))
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, abs=1e-12)
    assert result.verified_candidate_count == 1
    assert {
        "horizontal_stated_frame_gravity_normal_projection",
        "contact_sliding_friction",
        "particle_newton_second",
    } <= set(result.applied_law_ids)


def test_friction_opposes_motion_not_the_applied_force_or_query() -> None:
    projection = _projection(motion_word="왼쪽", motion_sign=-1)
    application, result = run_lane_b_case_with_selected_profile(
        projection,
        ProfileId.horizontal_contact,
        execution_token=deterministic_token(41),
    )
    assert application is not None and application.applied
    by_id = {item.quantity_id: item for item in application.draft.quantities}
    # Applied force is +tangent; leftward motion makes friction +tangent too.
    assert by_id["qty_force"].direction.sign == 1
    assert by_id["qty_closure_horizontal_contact_friction"].direction.sign == 1
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx((70 + 0.2 * 12 * 9.81) / 12)


def test_a_redundant_source_zero_angle_is_a_deterministic_no_op() -> None:
    without = run_lane_b_case(
        _projection(), execution_token=deterministic_token(44)
    )
    with_zero = run_lane_b_case(
        _projection(redundant_angle=True),
        execution_token=deterministic_token(45),
    )
    assert without.terminal is with_zero.terminal is LaneBTerminal.solved
    assert with_zero.answer_value_si == pytest.approx(without.answer_value_si)
    assert with_zero.applied_law_ids == without.applied_law_ids


def test_reversing_the_tangent_binding_preserves_world_x_physics() -> None:
    canonical = run_lane_b_case(
        _projection(), execution_token=deterministic_token(46)
    )
    mirrored_projection = _projection(tangent_world_sign=-1, motion_sign=-1)
    application, mirrored = run_lane_b_case_with_selected_profile(
        mirrored_projection,
        ProfileId.horizontal_contact,
        execution_token=deterministic_token(47),
    )
    assert application is not None and application.applied
    quantities = {item.quantity_id: item for item in application.draft.quantities}
    assert quantities["qty_force"].direction.sign == -1
    assert quantities["qty_unknown_q1"].direction.sign == -1
    assert quantities["v2_motion_state"].direction.sign == -1
    assert canonical.terminal is mirrored.terminal is LaneBTerminal.solved
    assert mirrored.answer_value_si == pytest.approx(canonical.answer_value_si)


def test_query_axis_cannot_substitute_for_an_unstated_motion_direction() -> None:
    projection = _projection(with_motion=False)
    plan = plan_complete_profile(
        ProfileId.horizontal_contact,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.not_applicable
    result = run_lane_b_case(projection, execution_token=deterministic_token(42))
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_an_extra_force_refuses_the_exact_free_body() -> None:
    projection = _projection()
    payload = projection.draft.model_dump(mode="json", warnings="none")
    extra = deepcopy(next(item for item in payload["quantities"] if item["role"] == "force"))
    extra["quantity_id"] = "qty_extra_force"
    extra["symbol_id"] = "sym_extra_force"
    symbol = deepcopy(
        next(item for item in payload["symbols"] if item["quantity_id"] == "qty_force")
    )
    symbol["quantity_id"] = "qty_extra_force"
    symbol["symbol_id"] = "sym_extra_force"
    payload["quantities"].append(extra)
    payload["symbols"].append(symbol)
    draft = MechanicsProblemDraftV1.model_validate(payload)

    plan = plan_complete_profile(
        ProfileId.horizontal_contact,
        draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.not_applicable


_B29_READER_ATTACKS = (
    "01_missing_friction_regime",
    "02_static_kinetic_ambiguity",
    "03_missing_kinetic_coefficient",
    "04_missing_motion_sense",
    "05_other_interval_motion_sense",
    "06_other_body_motion_sense",
    "07_missing_frame",
    "08_partial_frame_binding",
    "09_unknown_tangent",
    "10_reversed_normal",
    "11_dangling_frame",
    "12_frame_cycle",
    "13_missing_contact_topology",
    "14_coefficient_owned_by_other_contact",
    "15_applied_force_owned_by_other_body",
    "16_missing_force_direction_binding",
    "17_oblique_force_component",
    "18_missing_evidence",
    "19_mixed_invalid_evidence",
    "20_unknown_extra_force",
    "21_query_sign_friction_mutation",
    "22_static_law_injection",
    "23_dummy_numeric_velocity",
    "24_generated_numeric_force",
    "25_family_case_text_routing",
    "26_cross_event_authority",
    "27_cross_interval_authority",
    "28_frameless_angle_zero_bypass",
    "32_incomplete_inventory_complete_profile",
)


def _attack_payload(attack: str) -> dict:
    projection = _projection(redundant_angle=attack.startswith("28_"))
    payload = projection.draft.model_dump(mode="json", warnings="none")

    def quantity(role: str) -> dict:
        return next(item for item in payload["quantities"] if item["role"] == role)

    def remove_quantity(role: str) -> None:
        item = quantity(role)
        payload["quantities"].remove(item)
        payload["symbols"] = [
            symbol
            for symbol in payload["symbols"]
            if symbol["quantity_id"] != item["quantity_id"]
        ]

    support = payload["reference_frames"][1]
    support_axes = {item["axis"]: item for item in support["axes"]}
    if attack == "01_missing_friction_regime":
        payload["geometry"][0]["kind"] = "coincident"
    elif attack == "02_static_kinetic_ambiguity":
        payload["state_conditions"].extend(
            [
                {
                    "state_condition_id": "attack_static",
                    "kind": "friction",
                    "state": "sticking",
                    "subject_id": "object",
                    "interval_id": "motion_1",
                },
                {
                    "state_condition_id": "attack_kinetic",
                    "kind": "friction",
                    "state": "sliding",
                    "subject_id": "object",
                    "interval_id": "motion_1",
                },
            ]
        )
    elif attack == "03_missing_kinetic_coefficient":
        remove_quantity("coefficient_friction")
    elif attack == "04_missing_motion_sense":
        remove_quantity("velocity")
    elif attack == "05_other_interval_motion_sense":
        quantity("velocity")["interval_id"] = "v2_other_interval"
    elif attack == "06_other_body_motion_sense":
        quantity("velocity")["subject_id"] = "surface"
    elif attack == "07_missing_frame":
        payload["reference_frames"] = []
    elif attack == "08_partial_frame_binding":
        support_axes["tangent"]["direction"].pop("sign")
    elif attack == "09_unknown_tangent":
        support_axes["tangent"]["axis"] = "unknown"
    elif attack == "10_reversed_normal":
        support_axes["normal"]["direction"]["sign"] = -1
    elif attack == "11_dangling_frame":
        support["parent_frame_id"] = "v2_dangling"
    elif attack == "12_frame_cycle":
        support["parent_frame_id"] = support["frame_id"]
    elif attack == "13_missing_contact_topology":
        payload["geometry"] = []
    elif attack == "14_coefficient_owned_by_other_contact":
        quantity("coefficient_friction")["subject_id"] = "surface"
    elif attack == "15_applied_force_owned_by_other_body":
        quantity("force")["subject_id"] = "surface"
    elif attack == "16_missing_force_direction_binding":
        quantity("force")["direction"] = None
    elif attack == "17_oblique_force_component":
        quantity("force")["direction"] = {
            "kind": "axis",
            "frame_id": "v2_support",
            "axis": "normal",
            "sign": 1,
        }
    elif attack == "18_missing_evidence":
        quantity("force")["evidence_refs"] = []
    elif attack == "19_mixed_invalid_evidence":
        quantity("force")["evidence_refs"].append("v2_unknown_evidence")
    elif attack == "20_unknown_extra_force":
        extra = deepcopy(quantity("force"))
        extra["quantity_id"] = "v2_attack_extra_force"
        extra["symbol_id"] = "v2_attack_extra_force_symbol"
        symbol = deepcopy(
            next(
                item
                for item in payload["symbols"]
                if item["quantity_id"] == "qty_force"
            )
        )
        symbol["quantity_id"] = extra["quantity_id"]
        symbol["symbol_id"] = extra["symbol_id"]
        payload["quantities"].append(extra)
        payload["symbols"].append(symbol)
    elif attack == "21_query_sign_friction_mutation":
        payload["queries"][0]["target"]["direction"] = {
            "kind": "axis",
            "frame_id": "v2_support",
            "axis": "tangent",
            "sign": -1,
        }
    elif attack == "22_static_law_injection":
        payload["principle_hints"].append(
            {"principle_hint_id": "v2_attack_static_law", "principle": "statics"}
        )
    elif attack == "23_dummy_numeric_velocity":
        quantity("velocity").update(raw_value="1", raw_unit="m/s")
    elif attack == "24_generated_numeric_force":
        quantity("force")["provenance"] = "generated_closure"
    elif attack == "25_family_case_text_routing":
        remove_quantity("velocity")
        payload.update(
            case_id="B29_ATTACK",
            family="horizontal_friction_force",
            problem_text="rightward rough horizontal block",
        )
    elif attack == "26_cross_event_authority":
        quantity("velocity")["event_id"] = "start"
    elif attack == "27_cross_interval_authority":
        payload["assumptions"][0]["interval_id"] = "v2_other_interval"
    elif attack == "28_frameless_angle_zero_bypass":
        payload["reference_frames"] = []
    elif attack == "32_incomplete_inventory_complete_profile":
        payload["interactions"].append(
            {
                "interaction_id": "v2_attack_partial_free_body",
                "kind": "applied_force",
                "participant_ids": ["object"],
                "quantity_ids": ["qty_force"],
            }
        )
        payload["profile_disposition"] = "complete"
    else:  # pragma: no cover - the parameter table is the closed mutation set.
        raise AssertionError(attack)
    return payload


@pytest.mark.parametrize(
    ("attack", "expected_gate"),
    [
        (attack, "horizontal_contact_exact_source_shape_refusal")
        for attack in _B29_READER_ATTACKS
    ],
    ids=_B29_READER_ATTACKS,
)
def test_horizontal_contact_attack_matrix_fails_closed(
    attack: str, expected_gate: str
) -> None:
    payload = _attack_payload(attack)
    actual_gate = (
        "horizontal_contact_exact_source_shape_refusal"
        if read_horizontal_driven_sliding_source(payload) is None
        else "horizontal_contact_complete"
    )
    assert actual_gate == expected_gate


def test_attack_29_b30_typed_frame_without_angle_is_complete() -> None:
    projection = _projection()
    source = read_horizontal_driven_sliding_source(
        projection.draft.model_dump(mode="json", warnings="none")
    )
    assert source is not None and source.support_angle_quantity_id is None
    plan = plan_complete_profile(
        ProfileId.horizontal_contact,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete


def test_attack_30_b31_value_free_motion_state_is_the_only_friction_carrier() -> None:
    projection = _projection(motion_sign=-1, motion_word="왼쪽")
    payload = projection.draft.model_dump(mode="json", warnings="none")
    source = read_horizontal_driven_sliding_source(payload)
    motion = next(item for item in payload["quantities"] if item["role"] == "velocity")
    assert source is not None and source.motion_sign == -1
    assert motion["raw_value"] is motion["raw_unit"] is None
    assert motion["interval_id"] == source.interval_id


def test_attack_31_unaugmented_official_v1_shape_cannot_leak_into_b29() -> None:
    projection = project_case_to_draft(_case())
    assert projection.terminal is DraftProjectionTerminal.projected
    assert read_horizontal_driven_sliding_source(
        projection.draft.model_dump(mode="json", warnings="none")
    ) is None
    plan = plan_complete_profile(
        ProfileId.horizontal_contact,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.not_applicable


def test_gravity_authority_cannot_be_minted_by_the_profile_transaction() -> None:
    projection = _projection()
    plan = plan_complete_profile(
        ProfileId.horizontal_contact,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    application = apply_complete_profile(plan, projection.draft)
    assert application.outcome is ApplicationOutcome.rejected
    assert application.draft == projection.draft
    assert application.sanitized_reason == "profile_shape_not_closable"


def test_ambiguous_public_shape_stays_needs_confirmation() -> None:
    projection = project_case_to_draft(_case(ambiguous=True))
    result = run_lane_b_case(
        projection, execution_token=deterministic_token(43)
    )
    assert result.terminal is LaneBTerminal.needs_confirmation
    assert result.answer_value_si is None
