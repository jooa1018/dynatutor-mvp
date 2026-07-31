"""B16: source-typed gravity-driven kinetic slide on an incline."""
from __future__ import annotations

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
    INCLINE_SLIDING_GRAVITY_ID,
    INCLINE_SLIDING_SLOPE_FRAME_ID,
    INCLINE_SLIDING_WORLD_FRAME_ID,
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


EXPECTED_LAWS = {"incline_sliding_kinetic_acceleration"}


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    subject: str,
    *,
    direction: str = "not_applicable",
    temporal: str = "timeless",
    event: str | None = None,
) -> dict:
    return {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": "motion_1",
        "event_role": event,
        "temporal_role": temporal,
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _case(
    *,
    angle: str = "25",
    angle_unit: str = "°",
    coefficient: str | None = "0.12",
    include_mass: bool = False,
    incline_kind: str = "incline",
    motion_model: str = "sliding_on_incline",
    missing_relation: bool = False,
    second_support: bool = False,
    extra_force: bool = False,
    initial_velocity: bool = False,
    motion_direction: str | None = "downward",
    motion_speed: str = "3",
    motion_speed_unit: str = "m/s",
    motion_subject: str = "object",
    motion_segment: str | None = "motion_1",
    duplicate_motion: bool = False,
    conflicting_motion: bool = False,
    motion_event: str | None = None,
    rope_partner: bool = False,
    extra_assumption: str | None = None,
    missing_gravity: bool = False,
    query_component: str = "tangential",
    query_event: str | None = None,
    collision_id: str | None = None,
    reverse: bool = False,
    family: str = "independent_incline_kinetic_fixture",
    case_id: str = "fx_public_dev_0961",
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    angle_quote = f"경사각은 {angle} {angle_unit}"
    coefficient_quote = f"운동마찰계수는 {coefficient}"
    gravity_quote = "중력가속도는 9.81 m/s²로 사용한다"
    text = (
        f"블록이 경사면을 따라 아래쪽으로 미끄러진다. {angle_quote}. "
        f"{coefficient_quote if coefficient is not None else '마찰 조건은 문장에 없다'}. "
        f"{gravity_quote}. 경사면 아래쪽을 양의 방향으로 할 때 블록의 가속도를 구하여라."
    )

    entities = [
        {"role": "object", "kind": "block", "label": "블록"},
        {"role": "incline", "kind": incline_kind, "label": "경사면"},
    ]
    if second_support:
        entities.append({"role": "incline_2", "kind": "incline", "label": "둘째 경사면"})
    if rope_partner:
        entities.append({"role": "rope", "kind": "rope", "label": "줄"})
        entities.append({"role": "mass_b", "kind": "block", "label": "매달린 추"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})

    facts = [
        _fact("theta", "angle", angle, angle_unit, angle_quote, "incline"),
    ]
    if coefficient is not None:
        facts.append(
            _fact("mu", "coefficient_of_friction", coefficient, "", coefficient_quote, "incline")
        )
    if include_mass:
        mass_quote = "블록의 질량은 7 kg"
        text += f" {mass_quote}."
        facts.append(_fact("m", "mass", "7", "kg", mass_quote, "object"))
    if extra_force:
        force_quote = "오른쪽으로 30 N의 힘"
        text += f" {force_quote}."
        facts.append(
            _fact("f", "force", "30", "N", force_quote, "object",
                  direction="right", temporal="during")
        )
    if initial_velocity:
        velocity_quote = "초기 속력은 2 m/s"
        text += f" {velocity_quote}."
        facts.append(
            _fact("v0", "initial_velocity", "2", "m/s", velocity_quote, "object",
                  temporal="initial", event="start")
        )
    if motion_direction is not None:
        motion_quote = f"블록은 {motion_speed} {motion_speed_unit}로 움직이고 있다"
        text += f" {motion_quote}."
        motion_fact = _fact(
            "v", "velocity", motion_speed, motion_speed_unit, motion_quote,
            motion_subject, direction=motion_direction, temporal="during",
        )
        motion_fact["segment_role"] = motion_segment
        motion_fact["event_role"] = motion_event
        facts.append(motion_fact)
        if conflicting_motion:
            opposite = "upward" if motion_direction == "downward" else "downward"
            conflict_quote = f"블록은 반대로 {motion_speed} {motion_speed_unit}로도 움직인다"
            text += f" {conflict_quote}."
            conflict = _fact(
                "v_conflict", "velocity", motion_speed, motion_speed_unit,
                conflict_quote, motion_subject, direction=opposite,
                temporal="during",
            )
            conflict["segment_role"] = motion_segment
            facts.append(conflict)
        if duplicate_motion:
            second_quote = f"블록은 다시 {motion_speed} {motion_speed_unit}로 움직인다"
            text += f" {second_quote}."
            second = _fact(
                "v2", "velocity", motion_speed, motion_speed_unit, second_quote,
                motion_subject, direction=motion_direction, temporal="during",
            )
            second["segment_role"] = motion_segment
            facts.append(second)

    relations = []
    if not missing_relation:
        relations.append({
            "role": "slide",
            "kind": "slides_on",
            "participant_roles": ["object", "incline"],
            "segment_role": "motion_1",
        })
    if second_support:
        relations.append({
            "role": "slide_2",
            "kind": "slides_on",
            "participant_roles": ["object", "incline_2"],
            "segment_role": "motion_1",
        })
    if rope_partner:
        relations.append({
            "role": "rope_link",
            "kind": "connected_by_rope",
            "participant_roles": ["object", "mass_b"],
            "segment_role": "motion_1",
        })

    assumptions = []
    if not missing_gravity:
        assumptions.append({
            "role": "gravity",
            "kind": "constant_gravity",
            "subject_role": "object",
            "segment_role": "motion_1",
            "supporting_quote": gravity_quote,
            "server_value_only": True,
        })
    if extra_assumption is not None:
        extra_quote = "정지 상태에서 놓는다" if extra_assumption == "starts_from_rest" else "마찰을 무시한다"
        text += f" {extra_quote}."
        assumptions.append({
            "role": "extra",
            "kind": extra_assumption,
            "subject_role": "object",
            "segment_role": "motion_1",
            "supporting_quote": extra_quote,
            "server_value_only": True,
        })

    events = [
        {
            "role": "start",
            "kind": "start",
            "subject_roles": ["object"],
            "segment_role": "motion_1",
            "evidence_quote": None,
        }
    ]
    if reverse:
        entities.reverse()
        facts.reverse()
        relations.reverse()
        assumptions.reverse()

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
                "actor_roles": ["object"],
                "motion_model": motion_model,
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
                "output_key": "acceleration",
                "subject_role": "object",
                "segment_role": "motion_1",
                "component": query_component,
                "event_role": query_event,
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
        index=961,
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
    angle_radians: float,
    coefficient: float,
    gravity: float = 9.81,
    *,
    sense: str = "downward",
) -> float:
    """Tangential acceleration on the down-slope-positive slope axis.

    Kinetic friction opposes the motion that exists: it subtracts for a slide
    going down the slope and adds for one coasting up it.
    """

    friction = coefficient * math.cos(angle_radians)
    return gravity * (
        math.sin(angle_radians) - friction
        if sense == "downward"
        else math.sin(angle_radians) + friction
    )


def test_projection_carries_the_source_stated_slide_direction() -> None:
    projection = _projection(_case())
    derived = [
        item
        for item in projection.draft.assumptions
        if item.assumption_id == "asm_closure_incline_slide_motion"
    ]
    assert len(derived) == 1
    assert derived[0].kind == "typed_incline_slide_motion"
    assert derived[0].subject_id == "object"
    assert derived[0].evidence_refs
    # The direction lives on the source's own velocity record, not on a label.
    velocity = next(
        item for item in projection.draft.quantities if item.role.value == "velocity"
    )
    assert velocity.direction.direction.value == "downward"
    assert velocity.evidence_refs
    plan = plan_complete_profile(
        ProfileId.incline_kinetic_sliding,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    assert plan.structurally_complete


@pytest.mark.parametrize(
    ("angle", "coefficient", "sense", "expected"),
    (
        ("25", "0.12", "downward", _expected(math.radians(25.0), 0.12)),
        ("32", "0.18", "downward", _expected(math.radians(32.0), 0.18)),
        ("18", "0.08", "downward", _expected(math.radians(18.0), 0.08)),
        (
            "25",
            "0.12",
            "upward",
            _expected(math.radians(25.0), 0.12, sense="upward"),
        ),
        (
            "32",
            "0.18",
            "upward",
            _expected(math.radians(32.0), 0.18, sense="upward"),
        ),
    ),
)
def test_kinetic_incline_acceleration_follows_the_stated_slide_direction(
    angle: str, coefficient: str, sense: str, expected: float
) -> None:
    result = _run(
        _case(angle=angle, coefficient=coefficient, motion_direction=sense),
        f"b16-positive-{angle}-{coefficient}-{sense}",
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)
    assert result.candidate_count == result.verified_candidate_count == 1
    assert set(result.applied_law_ids) == EXPECTED_LAWS
    assert {kind for kind, outcome in result.verification_checks if outcome == "passed"} >= {
        "equation_residual",
        "inequality",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    }


def test_adding_a_source_mass_does_not_change_the_acceleration() -> None:
    baseline = _run(_case(), "b16-mass-free")
    with_mass = _run(_case(include_mass=True, case_id="fx_public_dev_0962"), "b16-with-mass")
    assert baseline.terminal is with_mass.terminal is LaneBTerminal.solved
    assert with_mass.answer_value_si == pytest.approx(
        baseline.answer_value_si, rel=1.0e-12, abs=1.0e-12
    )
    assert with_mass.applied_law_ids == baseline.applied_law_ids


def test_transaction_adds_only_typed_topology_and_the_value_free_unknown() -> None:
    projection = _projection(_case())
    pristine = projection.draft.model_dump(mode="json", warnings="none")
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.incline_kinetic_sliding,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    assert projection.draft.model_dump(mode="json", warnings="none") == pristine
    closed = application.draft
    assert {item.frame_id for item in closed.reference_frames} == {
        INCLINE_SLIDING_WORLD_FRAME_ID,
        INCLINE_SLIDING_SLOPE_FRAME_ID,
    }
    gravity = next(
        item for item in closed.quantities if item.quantity_id == INCLINE_SLIDING_GRAVITY_ID
    )
    assert gravity.provenance is Provenance.server_default
    assert gravity.raw_value == "9.81"
    created_quantities = [
        item
        for item in closed.quantities
        if item.quantity_id in application.created_record_ids
        and item.quantity_id != INCLINE_SLIDING_GRAVITY_ID
    ]
    assert all(
        item.raw_value is None and item.raw_unit is None for item in created_quantities
    )
    assert closed.queries[0].target.subject_id == "object"
    assert closed.queries[0].target.component.value == "tangential"
    assert closed.queries[0].target.direction.sign == 1
    assert not closed.constraints
    assert not any(item.role.value == "force" for item in closed.quantities)
    # The source's velocity keeps its own value and is bound to the same
    # down-slope-positive tangent the answer is asked on.  The typed motion
    # state carries it, so the friction sign is read from a physics record.
    motion = next(
        item for item in closed.quantities if item.role.value == "velocity"
    )
    assert motion.frame_id == INCLINE_SLIDING_SLOPE_FRAME_ID
    assert motion.component.value == "tangential"
    assert motion.direction.axis.value == "tangent"
    assert motion.direction.sign == 1
    assert motion.raw_value == "3"
    assert motion.quantity_id not in application.created_record_ids
    motion_state = next(
        item
        for item in closed.state_conditions
        if item.kind.value == "motion" and item.subject_id == "object"
    )
    assert motion_state.state.value == "moving"
    assert list(motion_state.quantity_ids) == [motion.quantity_id]


def test_an_up_slope_slide_binds_the_carrier_to_the_negative_tangent() -> None:
    projection = _projection(_case(motion_direction="upward"))
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.incline_kinetic_sliding,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    motion = next(
        item
        for item in application.draft.quantities
        if item.role.value == "velocity"
    )
    # Same down-slope-positive axis, opposite sign: the source said "up".
    assert motion.direction.axis.value == "tangent"
    assert motion.direction.sign == -1
    assert application.draft.queries[0].target.direction.sign == 1


def test_friction_opposes_the_stated_motion_rather_than_gravity() -> None:
    """The friction term flips with the stated direction and nothing else."""

    angle, coefficient = math.radians(25.0), 0.12
    down = _run(_case(), "b16-friction-sign-down")
    up = _run(_case(motion_direction="upward"), "b16-friction-sign-up")
    assert down.terminal is up.terminal is LaneBTerminal.solved
    gravity_only = 9.81 * math.sin(angle)
    friction = 9.81 * coefficient * math.cos(angle)
    assert down.answer_value_si == pytest.approx(
        gravity_only - friction, rel=1.0e-12, abs=1.0e-12
    )
    assert up.answer_value_si == pytest.approx(
        gravity_only + friction, rel=1.0e-12, abs=1.0e-12
    )
    # Both sit symmetrically about the frictionless value: the sign of the
    # friction term is the only thing the direction changed.
    assert (down.answer_value_si + up.answer_value_si) / 2.0 == pytest.approx(
        gravity_only, rel=1.0e-12, abs=1.0e-12
    )


def test_the_declared_sliding_regime_is_what_makes_the_coefficient_kinetic() -> None:
    """A regime the source did not declare as sliding cannot use this law."""

    for motion_model in ("unknown", "energy_interval", "constant_acceleration_1d"):
        result = _run(
            _case(motion_model=motion_model),
            f"b16-regime-{motion_model}",
        )
        assert result.terminal is not LaneBTerminal.solved
        assert result.answer_value_si is None
        assert result.verified_candidate_count == 0
    # A stated rest boundary contradicts a slide in progress.
    at_rest = _run(
        _case(extra_assumption="starts_from_rest"), "b16-regime-starts-from-rest"
    )
    assert at_rest.terminal is not LaneBTerminal.solved
    assert at_rest.verified_candidate_count == 0


def test_b15_horizontal_repair_and_b16_direction_repair_do_not_interfere() -> None:
    """Neither repair's authority can stand in for the other's."""

    from evaluation.phase56_stage7.complete_profile import (
        ProfileId as _ProfileId,
        plan_complete_profile as _plan,
    )

    projection = _projection(_case())
    # A stated slide direction is not a stated horizontal support.
    table_plan = _plan(
        _ProfileId.table_pulley_two_body,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert table_plan.disposition is not PlanDisposition.complete
    # And the incline shape keeps closing on its own authority.
    incline_plan = _plan(
        ProfileId.incline_kinetic_sliding,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert incline_plan.disposition is PlanDisposition.complete


def test_units_ids_and_source_order_are_not_authority() -> None:
    baseline = _run(_case(), "b16-invariance-base")
    equivalent = _run(
        _case(
            angle=str(math.radians(25.0)),
            angle_unit="rad",
            reverse=True,
            family="renamed_incline_kinetic_family",
            case_id="renamed_case_identity",
            fake_answer=999999.0,
        ),
        "b16-invariance-equivalent",
    )
    assert baseline.terminal is equivalent.terminal is LaneBTerminal.solved
    assert equivalent.answer_value_si == pytest.approx(
        baseline.answer_value_si, rel=1.0e-12, abs=1.0e-12
    )
    assert equivalent.applied_law_ids == baseline.applied_law_ids


def test_a_high_friction_down_slope_slide_decelerates_and_still_solves() -> None:
    """tan(10 deg) < 0.4, and that is not a contradiction.

    A block already sliding down a shallow rough slope decelerates: on the
    down-slope-positive axis its tangential acceleration is negative.  The
    stated motion is what makes this well posed, so the engine answers with
    the negative number instead of refusing.  Treating "gravity could not
    start this slide" as "this slide is not happening" was the error this
    test replaces.
    """

    expected = _expected(math.radians(10.0), 0.4)
    assert expected < 0.0
    result = _run(_case(angle="10", coefficient="0.4"), "b16-high-friction-downslope")
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)
    assert result.candidate_count == result.verified_candidate_count == 1


def test_the_same_high_friction_slope_going_up_accelerates_the_other_way() -> None:
    down = _run(_case(angle="10", coefficient="0.4"), "b16-updown-down")
    up = _run(
        _case(angle="10", coefficient="0.4", motion_direction="upward"),
        "b16-updown-up",
    )
    assert down.terminal is up.terminal is LaneBTerminal.solved
    assert down.answer_value_si < 0.0 < up.answer_value_si
    assert up.answer_value_si == pytest.approx(
        _expected(math.radians(10.0), 0.4, sense="upward"), rel=1.0e-12, abs=1.0e-12
    )


def test_missing_coefficient_stays_a_reader_decision() -> None:
    result = _run(_case(coefficient=None), "b16-ambiguous-friction")
    assert result.terminal is LaneBTerminal.needs_confirmation
    assert result.answer_value_si is None


@pytest.mark.parametrize(
    "overrides",
    (
        {"motion_model": "unknown"},
        {"motion_model": "energy_interval"},
        {"missing_relation": True},
        {"incline_kind": "surface"},
        {"second_support": True},
        {"extra_force": True},
        {"initial_velocity": True},
        {"extra_assumption": "starts_from_rest"},
        {"extra_assumption": "frictionless"},
        {"missing_gravity": True},
        {"query_component": "magnitude"},
        {"query_component": "normal"},
        {"query_event": "start"},
        {"collision_id": INCLINE_SLIDING_WORLD_FRAME_ID},
        # A declared slide with no stated direction: `sliding_on_incline` says
        # a body slides, never which way, so the closure has no friction sign.
        {"motion_direction": None},
        # Directions that name no slope sense.
        {"motion_direction": "unspecified"},
        {"motion_direction": "along_motion"},
        {"motion_direction": "opposite_motion"},
        {"motion_direction": "left"},
        {"motion_direction": "right"},
        {"motion_direction": "not_applicable"},
        # Contradictory or duplicated direction statements.
        {"conflicting_motion": True},
        {"duplicate_motion": True},
        # A direction stated about something else, somewhere else, or at an
        # instant rather than across the slide.
        {"motion_subject": "incline"},
        {"motion_segment": None},
        {"motion_event": "start"},
        # A zero or negative speed is not a slide in progress.
        {"motion_speed": "0"},
        {"motion_speed": "-3"},
        # A second body roped to the slider is a different, unclosed model.
        {"rope_partner": True},
    ),
)
def test_structural_near_misses_fail_closed_without_numeric_output(
    overrides: dict,
) -> None:
    result = _run(_case(**overrides), f"b16-near-miss-{sorted(overrides)}")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_physics_changing_angle_and_coefficient_change_the_answer() -> None:
    first = _run(_case(angle="25", coefficient="0.12"), "b16-physics-a")
    second = _run(_case(angle="25", coefficient="0.2"), "b16-physics-b")
    third = _run(_case(angle="30", coefficient="0.12"), "b16-physics-c")
    assert first.terminal is second.terminal is third.terminal is LaneBTerminal.solved
    assert first.answer_value_si != pytest.approx(second.answer_value_si)
    assert first.answer_value_si != pytest.approx(third.answer_value_si)


def test_incline_hanging_shape_is_never_claimed_by_the_sliding_profile() -> None:
    projection = _projection(_case())
    plan = plan_complete_profile(
        ProfileId.incline_contact,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    # The unimplemented census profile still measures the same Draft without
    # claiming it: only the kinetic-sliding profile closes.
    assert plan.disposition is not PlanDisposition.complete
