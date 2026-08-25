"""Exact one-body work--energy speed closure and verifier authority boundaries."""
from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from engine.mechanics.compiler import MechanicsCompiler, authorize_validated_mechanics_ir
from engine.mechanics.normalization import normalize_draft
from engine.mechanics.solver.planner import plan_equation_graph
from engine.mechanics.verification import verifier as verifier_module
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ENERGY_SPEED_FRAME_ID,
    ApplicationOutcome,
    apply_selected_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.event_boundary_derivation import derive_event_boundaries
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
    event_role: str | None,
    temporal_role: str,
    direction: str,
) -> dict:
    return {
        "role": role,
        "semantic_key": semantic_key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": "object",
        "segment_role": "motion_1",
        "event_role": event_role,
        "temporal_role": temporal_role,
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _energy_case(
    *,
    mass: str = "5",
    mass_unit: str = "kg",
    initial_speed: str = "3",
    speed_unit: str = "m/s",
    work: str = "40",
    work_unit: str = "J",
    initial_direction: str = "along_motion",
    query_component: str = "magnitude",
    query_event: str = "finish",
    extra_fact: dict | None = None,
    extra_entity: bool = False,
    reverse: bool = False,
    family: str = "independent_energy_fixture",
) -> PublicCorpusCaseV1:
    mass_quote = f"질량은 {mass} {mass_unit}"
    speed_quote = f"초기 속력은 {initial_speed} {speed_unit}"
    work_quote = f"알짜일은 {work} {work_unit}"
    text = (
        f"시험 물체의 {mass_quote}이고 {speed_quote}이다. "
        f"이동 구간에서 물체에 한 {work_quote}이다. "
        "구간 끝의 속력 크기를 구하여라."
    )
    if extra_fact is not None:
        text += f" 참고로 {extra_fact['evidence_quote']}."
    entities = [{"role": "object", "kind": "block", "label": "시험 물체"}]
    if extra_entity:
        entities.append({"role": "other", "kind": "block", "label": "무관 물체"})
    events = [
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
    ]
    facts = [
        _fact(
            "mass",
            "mass",
            mass,
            mass_unit,
            mass_quote,
            event_role=None,
            temporal_role="timeless",
            direction="not_applicable",
        ),
        _fact(
            "v0",
            "initial_velocity",
            initial_speed,
            speed_unit,
            speed_quote,
            event_role="start",
            temporal_role="initial",
            direction=initial_direction,
        ),
        _fact(
            "work",
            "work",
            work,
            work_unit,
            work_quote,
            event_role=None,
            temporal_role="interval",
            direction="not_applicable",
        ),
    ]
    if extra_fact is not None:
        facts.append(extra_fact)
    if reverse:
        events.reverse()
        facts.reverse()
        entities.reverse()
    gold = {
        "parse_status": "complete",
        "expected_system_type": "independent_energy_fixture",
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
        "events": events,
        "explicit_facts": facts,
        "relations": [],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "final_velocity",
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
        index=781,
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


def _compile_energy_graph(case: PublicCorpusCaseV1):
    projection = _projection(case)
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.particle_work_energy_speed,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    draft = derive_event_boundaries(application.draft).draft
    normalized = normalize_draft(
        projection.problem_text,
        draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert normalized.accepted and normalized.ir is not None
    authorization = authorize_validated_mechanics_ir(normalized.ir)
    compiled = MechanicsCompiler().compile(
        normalized.ir,
        validated_ir_authorization=authorization,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert compiled.graph is not None
    return compiled.graph, plan_equation_graph(compiled.graph)


def test_particle_work_energy_speed_solves_through_the_real_lane() -> None:
    result = _run(_energy_case(), "energy-positive")
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(5.0)
    assert result.answer_unit == "m/s"
    assert result.candidate_count == 2
    assert result.rejected_candidate_count == 1  # the negative square-root branch
    assert result.verified_candidate_count == 1
    assert set(result.applied_law_ids) == {
        "particle_work_energy",
        "translational_speed_nonnegative",
    }
    checks = dict(result.verification_checks)
    for required in (
        "conserved_quantity",
        "equation_residual",
        "inequality",
        "positive_parameter",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    ):
        assert checks[required] == "passed"


def test_transaction_changes_no_raw_value_unit_or_evidence() -> None:
    projection = _projection(_energy_case())
    plan = plan_complete_profile(
        ProfileId.particle_work_energy_speed, projection.draft
    )
    assert plan.disposition is PlanDisposition.complete
    application = apply_selected_profile(
        projection.draft, ProfileId.particle_work_energy_speed
    )
    assert application.outcome is ApplicationOutcome.applied
    assert application.created_record_ids == (ENERGY_SPEED_FRAME_ID,)
    assert set(application.rebound_quantity_ids) == {
        "qty_mass",
        "qty_v0",
        "qty_unknown_q1",
    }
    before = {
        q.quantity_id: (q.raw_value, q.raw_unit, tuple(q.evidence_refs))
        for q in projection.draft.quantities
    }
    after = {
        q.quantity_id: (q.raw_value, q.raw_unit, tuple(q.evidence_refs))
        for q in application.draft.quantities
    }
    assert after == before
    rebound = {q.quantity_id: q for q in application.draft.quantities}
    assert rebound["qty_v0"].role.value == "speed"
    assert rebound["qty_unknown_q1"].role.value == "speed"
    assert rebound["qty_mass"].interval_id is None


def test_physics_changing_work_changes_the_verified_answer() -> None:
    baseline = _run(_energy_case(work="40"), "energy-work-40")
    changed = _run(_energy_case(work="90"), "energy-work-90")
    assert baseline.terminal is changed.terminal is LaneBTerminal.solved
    assert baseline.answer_value_si == pytest.approx(5.0)
    assert changed.answer_value_si == pytest.approx(45.0**0.5)
    assert changed.answer_value_si != pytest.approx(baseline.answer_value_si)


def test_compatible_unit_conversion_is_invariant() -> None:
    baseline = _run(_energy_case(), "energy-units-si")
    converted = _run(
        _energy_case(
            mass="5000",
            mass_unit="g",
            initial_speed="10.8",
            speed_unit="km/h",
            work="40",
            work_unit="N*m",
        ),
        "energy-units-converted",
    )
    assert baseline.terminal is converted.terminal is LaneBTerminal.solved
    assert converted.answer_value_si == pytest.approx(baseline.answer_value_si)


def test_fact_event_and_entity_order_are_invariant() -> None:
    baseline = _run(_energy_case(), "energy-order-a")
    reordered = _run(_energy_case(reverse=True), "energy-order-b")
    assert baseline.terminal is reordered.terminal is LaneBTerminal.solved
    assert reordered.answer_value_si == pytest.approx(baseline.answer_value_si)


def test_external_family_metadata_does_not_route_the_solver() -> None:
    baseline = _run(_energy_case(family="fixture_a"), "energy-family-a")
    renamed = _run(_energy_case(family="unrelated_label"), "energy-family-b")
    assert baseline.terminal is renamed.terminal is LaneBTerminal.solved
    assert renamed.answer_value_si == pytest.approx(baseline.answer_value_si)


@pytest.mark.parametrize(
    ("case", "nonce"),
    (
        (_energy_case(query_component="x", initial_direction="right"), "signed"),
        (_energy_case(query_event="start"), "wrong-event"),
        (_energy_case(initial_direction="not_applicable"), "no-axis"),
        (_energy_case(extra_entity=True), "extra-body"),
    ),
)
def test_near_miss_shapes_never_solve_as_scalar_work_energy(
    case: PublicCorpusCaseV1, nonce: str
) -> None:
    result = _run(case, nonce)
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_unrelated_number_attack_blocks_the_exact_transaction() -> None:
    extra = _fact(
        "irrelevant_distance",
        "distance",
        "999",
        "m",
        "무관한 표지까지 거리는 999 m",
        event_role=None,
        temporal_role="timeless",
        direction="not_applicable",
    )
    case = _energy_case(extra_fact=extra)
    result = _run(case, "unrelated-number")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_intrinsic_nonnegative_evidence_exception_is_exact_not_relabelable() -> None:
    graph, plan = _compile_energy_graph(_energy_case())
    equation = next(
        item
        for item in graph.equations
        if item.law_id == "translational_speed_nonnegative"
    )
    assert verifier_module._is_intrinsic_nonnegative_quantity_equation(
        plan, equation
    )

    wrong_law = equation.model_copy(update={"law_id": "particle_work_energy"})
    assert not verifier_module._is_intrinsic_nonnegative_quantity_equation(
        plan, wrong_law
    )

    wrong_literal = equation.model_copy(
        update={
            "expression": equation.expression.model_copy(
                update={
                    "right": equation.expression.right.model_copy(
                        update={"value": 1.0}
                    )
                }
            )
        }
    )
    assert not verifier_module._is_intrinsic_nonnegative_quantity_equation(
        plan, wrong_literal
    )

    wrong_source = equation.model_copy(update={"source_quantity_ids": ("qty_mass",)})
    assert not verifier_module._is_intrinsic_nonnegative_quantity_equation(
        plan, wrong_source
    )

    wrong_scope = equation.model_copy(
        update={"scope": equation.scope.model_copy(update={"event_id": "start"})}
    )
    assert not verifier_module._is_intrinsic_nonnegative_quantity_equation(
        plan, wrong_scope
    )
