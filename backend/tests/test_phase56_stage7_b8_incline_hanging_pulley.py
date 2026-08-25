"""B8: source-typed frictionless incline/hanging fixed-pulley closure."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math

import pytest

from engine.mechanics.contracts import Provenance
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    INCLINE_HANGING_GRAVITY_ID,
    INCLINE_HANGING_INCLINE_FRAME_ID,
    INCLINE_HANGING_ROPE_ID,
    INCLINE_HANGING_WORLD_FRAME_ID,
    INCLINE_HANGING_WORLD_ID,
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


pytestmark = pytest.mark.slow


EXPECTED_LAWS = {
    "contact_normal_bound",
    "fixed_contact_no_penetration",
    "incline_gravity_normal_projection",
    "incline_gravity_tangent_projection",
    "particle_newton_second",
    "particle_weight",
    "rope_attachment_acceleration_transfer",
    "rope_attachment_tension_transfer",
}


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    subject: str,
) -> dict:
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


def _assumption(role: str, kind: str, quote: str) -> dict:
    return {
        "role": role,
        "kind": kind,
        "subject_role": "system",
        "segment_role": "motion_1",
        "supporting_quote": quote,
        "server_value_only": True,
    }


def _relation(role: str, kind: str, participants: list[str]) -> dict:
    return {
        "role": role,
        "kind": kind,
        "participant_roles": participants,
        "segment_role": "motion_1",
    }


def _case(
    *,
    mass_a: str = "4",
    mass_a_unit: str = "kg",
    mass_b: str = "3",
    mass_b_unit: str = "kg",
    angle: str = "25",
    angle_unit: str = "°",
    include_rope_entity: bool = False,
    rope_role: str = "cable_custom",
    missing_relation: str | None = None,
    duplicate_relation: str | None = None,
    missing_assumption: str | None = None,
    pulley_actor: bool = False,
    include_pulley_inertia: bool = False,
    extra_body: bool = False,
    query_output: str = "acceleration",
    query_component: str = "magnitude",
    collision_id: str | None = None,
    reverse: bool = False,
    family: str = "independent_incline_hanging_fixture",
    case_id: str = "fx_public_dev_0851",
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    mass_a_quote = f"경사면 블록의 질량은 {mass_a} {mass_a_unit}"
    mass_b_quote = f"매달린 추의 질량은 {mass_b} {mass_b_unit}"
    angle_quote = f"경사각은 {angle} {angle_unit}"
    friction_quote = "경사면과 도르래의 마찰을 무시한다"
    rope_mass_quote = "줄의 질량을 무시한다"
    rope_length_quote = "줄은 늘어나지 않는다"
    pulley_quote = "도르래의 질량을 무시한다"
    gravity_quote = "중력가속도는 9.81 m/s²로 사용한다"
    text = (
        f"{mass_a_quote}. {mass_b_quote}. {angle_quote}. "
        f"두 물체는 하나의 줄로 연결되어 고정 도르래를 지난다. "
        f"{friction_quote}. {rope_mass_quote}. {rope_length_quote}. "
        f"{pulley_quote}. {gravity_quote}. 계의 가속도 크기를 구하여라."
    )

    entities = [
        {"role": "system", "kind": "system", "label": "경사면 도르래 계"},
        {"role": "mass_a", "kind": "block", "label": "경사면 블록"},
        {"role": "mass_b", "kind": "block", "label": "매달린 추"},
        {"role": "incline", "kind": "incline", "label": "경사면"},
        {"role": "pulley", "kind": "pulley", "label": "고정 도르래"},
    ]
    if include_rope_entity:
        entities.append({"role": rope_role, "kind": "rope", "label": "명시적 줄"})
    if extra_body:
        entities.append({"role": "mass_c", "kind": "block", "label": "추가 물체"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})

    actors = ["system", "mass_a", "mass_b"]
    if pulley_actor:
        actors.append("pulley")
    if extra_body:
        actors.append("mass_c")

    facts = [
        _fact("m1", "mass_1", mass_a, mass_a_unit, mass_a_quote, "mass_a"),
        _fact("m2", "mass_2", mass_b, mass_b_unit, mass_b_quote, "mass_b"),
        _fact("theta", "angle", angle, angle_unit, angle_quote, "incline"),
    ]
    if include_pulley_inertia:
        inertia_quote = "도르래 관성모멘트는 0.12 kg·m²"
        text += f" {inertia_quote}."
        facts.append(
            _fact(
                "pulley_inertia",
                "moment_of_inertia",
                "0.12",
                "kg·m²",
                inertia_quote,
                "pulley",
            )
        )
    if extra_body:
        extra_quote = "추가 물체의 질량은 1 kg"
        text += f" {extra_quote}."
        facts.append(_fact("m3", "mass", "1", "kg", extra_quote, "mass_c"))

    relations = [
        _relation("rope_connection", "connected_by_rope", ["mass_a", "mass_b"]),
        _relation(
            "pulley_wrap",
            "passes_over_pulley",
            ["mass_a", "mass_b", "pulley"],
        ),
        _relation("incline_support", "slides_on", ["mass_a", "incline"]),
    ]
    if missing_relation is not None:
        relations = [item for item in relations if item["kind"] != missing_relation]
    if duplicate_relation is not None:
        original = next(item for item in relations if item["kind"] == duplicate_relation)
        duplicate = deepcopy(original)
        duplicate["role"] += "_duplicate"
        relations.append(duplicate)

    assumptions = [
        _assumption("friction", "frictionless", friction_quote),
        _assumption("rope_mass", "massless_rope", rope_mass_quote),
        _assumption("rope_length", "inextensible_rope", rope_length_quote),
        _assumption("pulley_mass", "massless_pulley", pulley_quote),
        _assumption("gravity", "constant_gravity", gravity_quote),
    ]
    if missing_assumption is not None:
        assumptions = [item for item in assumptions if item["kind"] != missing_assumption]

    events = [
        {
            "role": "start",
            "kind": "start",
            "subject_roles": ["system", "mass_a", "mass_b"],
            "segment_role": "motion_1",
            "evidence_quote": None,
        }
    ]
    if reverse:
        entities.reverse()
        facts.reverse()
        relations.reverse()
        assumptions.reverse()
        events.reverse()

    gold = {
        "parse_status": "complete",
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": actors,
                "motion_model": "sliding_on_incline",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": events,
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions,
        "queries": [
            {
                "role": "q1",
                "output_key": query_output,
                "subject_role": "system",
                "segment_role": "motion_1",
                "component": query_component,
                "event_role": None,
            }
        ],
        "answers": (
            []
            if fake_answer is None
            else [
                {
                    "query_role": "q1",
                    "numeric": fake_answer,
                    "unit": "m/s^2",
                    "tolerance_abs": 1.0e-6,
                    "reference_expression": "deliberately non-authoritative",
                }
            ]
        ),
        "expected_failure_codes": [],
    }
    record = build_case(
        index=851,
        split="public_dev",
        family=family,
        future_terminal="accepted",
        with_answer=False,
    )
    record.update(
        case_id=case_id,
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
    projection = project_case_to_draft(case)
    return run_lane_b_case(
        projection,
        execution_token=deterministic_token(0, run_nonce=nonce),
    )


def _expected(
    mass_a: float,
    mass_b: float,
    angle_radians: float,
    gravity: float = 9.81,
) -> float:
    return abs(mass_a * gravity * math.sin(angle_radians) - mass_b * gravity) / (
        mass_a + mass_b
    )


def test_projection_materializes_only_one_source_evidenced_implicit_rope() -> None:
    projection = _projection(_case())
    ropes = [
        item for item in projection.draft.entities if item.primitive.value == "rope"
    ]
    assert [item.entity_id for item in ropes] == [INCLINE_HANGING_ROPE_ID]
    assert ropes[0].evidence_refs
    scoped = {
        (item.kind, item.subject_id)
        for item in projection.draft.assumptions
        if item.assumption_id.startswith("asm_closure_fixed_pulley_")
    }
    assert scoped == {
        ("massless_rope", INCLINE_HANGING_ROPE_ID),
        ("inextensible_rope", INCLINE_HANGING_ROPE_ID),
        ("fixed_pulley", "pulley"),
        ("ideal_massless_frictionless_pulley", "pulley"),
    }
    plan = plan_complete_profile(
        ProfileId.incline_hanging_pulley,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    assert plan.structurally_complete


@pytest.mark.parametrize(
    ("mass_a", "mass_b", "angle", "expected"),
    (
        ("4", "3", "25", _expected(4.0, 3.0, math.radians(25.0))),
        ("5", "2", "30", _expected(5.0, 2.0, math.radians(30.0))),
        ("3", "2.8", "20", _expected(3.0, 2.8, math.radians(20.0))),
    ),
)
def test_incline_hanging_acceleration_uses_existing_generic_laws(
    mass_a: str, mass_b: str, angle: str, expected: float
) -> None:
    result = _run(
        _case(mass_a=mass_a, mass_b=mass_b, angle=angle),
        f"b8-positive-{mass_a}-{mass_b}-{angle}",
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)
    assert result.candidate_count == result.verified_candidate_count == 1
    assert set(result.applied_law_ids) == EXPECTED_LAWS
    assert {kind for kind, outcome in result.verification_checks if outcome == "passed"} >= {
        "constraint",
        "equation_residual",
        "inequality",
        "physical_regime",
        "positive_parameter",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    }


def test_transaction_adds_only_typed_topology_and_value_free_unknowns() -> None:
    projection = _projection(_case())
    pristine = projection.draft.model_dump(mode="json", warnings="none")
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.incline_hanging_pulley,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    assert projection.draft.model_dump(mode="json", warnings="none") == pristine
    closed = application.draft
    assert {item.frame_id for item in closed.reference_frames} == {
        INCLINE_HANGING_WORLD_FRAME_ID,
        INCLINE_HANGING_INCLINE_FRAME_ID,
    }
    assert {item.entity_id for item in closed.entities if item.primitive.value == "environment"} == {
        INCLINE_HANGING_WORLD_ID
    }
    gravity = next(item for item in closed.quantities if item.quantity_id == INCLINE_HANGING_GRAVITY_ID)
    assert gravity.provenance is Provenance.server_default
    assert gravity.raw_value == "9.81"
    assert gravity.assumption_policy_ref == "asm_gravity"
    created_quantities = [
        item
        for item in closed.quantities
        if item.quantity_id in application.created_record_ids
        and item.quantity_id != INCLINE_HANGING_GRAVITY_ID
    ]
    assert created_quantities
    assert all(item.raw_value is None and item.raw_unit is None for item in created_quantities)
    assert closed.queries[0].target.subject_id in {"mass_a", "mass_b"}
    assert closed.queries[0].target.target_quantity_id == "qty_unknown_q1"
    assert closed.queries[0].target.component.value == "y"
    assert not closed.constraints


def test_opposite_drive_direction_changes_axis_sign_but_preserves_magnitude() -> None:
    hanging_dominant = _projection(_case(mass_a="4", mass_b="3", angle="25"))
    incline_dominant = _projection(_case(mass_a="10", mass_b="2", angle="30"))
    directions = []
    results = []
    for index, projection in enumerate((hanging_dominant, incline_dominant)):
        bundle = build_lane_b_authority_bundle(projection)
        application = apply_selected_profile(
            projection.draft,
            ProfileId.incline_hanging_pulley,
            approved_assumption_ids=bundle.approved_assumption_ids,
            authorized_assumptions=bundle.authorization_map(),
        )
        assert application.outcome is ApplicationOutcome.applied
        directions.append(application.draft.queries[0].target.direction.sign)
        results.append(
            run_lane_b_case(
                projection,
                execution_token=deterministic_token(index, run_nonce="b8-drive"),
            )
        )
    assert directions == [1, -1]
    assert all(item.terminal is LaneBTerminal.solved for item in results)
    assert all(item.answer_value_si is not None and item.answer_value_si > 0.0 for item in results)


def test_units_explicit_rope_ids_and_source_order_are_not_authority() -> None:
    baseline = _run(_case(), "b8-invariance-base")
    equivalent = _run(
        _case(
            mass_a="4000",
            mass_a_unit="g",
            mass_b="3000",
            mass_b_unit="g",
            angle=str(math.radians(25.0)),
            angle_unit="rad",
            include_rope_entity=True,
            rope_role="student_named_cable",
            reverse=True,
            family="renamed_incline_hanging_family",
            case_id="renamed_case_identity",
            fake_answer=999999.0,
        ),
        "b8-invariance-equivalent",
    )
    assert baseline.terminal is equivalent.terminal is LaneBTerminal.solved
    assert equivalent.answer_value_si == pytest.approx(
        baseline.answer_value_si, rel=1.0e-12, abs=1.0e-12
    )
    assert equivalent.applied_law_ids == baseline.applied_law_ids


@pytest.mark.parametrize(
    "overrides",
    (
        {"missing_relation": "connected_by_rope"},
        {"missing_relation": "passes_over_pulley"},
        {"missing_relation": "slides_on"},
        {"duplicate_relation": "passes_over_pulley"},
        {"missing_assumption": "frictionless"},
        {"missing_assumption": "massless_rope"},
        {"missing_assumption": "inextensible_rope"},
        {"missing_assumption": "massless_pulley"},
        {"pulley_actor": True},
        {"include_pulley_inertia": True},
        {"extra_body": True},
        {"mass_a": "2", "mass_b": "1", "angle": "30"},
        {"query_component": "x"},
        {"query_output": "force"},
        {"collision_id": INCLINE_HANGING_WORLD_FRAME_ID},
    ),
)
def test_structural_near_misses_fail_closed_without_numeric_output(
    overrides: dict,
) -> None:
    result = _run(_case(**overrides), f"b8-near-miss-{sorted(overrides)}")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_physics_changing_angle_changes_the_verified_answer() -> None:
    first = _run(_case(angle="15"), "b8-angle-15")
    second = _run(_case(angle="40"), "b8-angle-40")
    assert first.terminal is second.terminal is LaneBTerminal.solved
    assert first.answer_value_si != pytest.approx(second.answer_value_si)
    assert first.applied_law_ids == second.applied_law_ids


def test_closed_graph_never_routes_to_rolling_energy() -> None:
    result = _run(_case(), "b8-no-rolling")
    assert result.terminal is LaneBTerminal.solved
    assert not any("rolling" in law_id for law_id in result.applied_law_ids)
