"""B13 rolling incline energy package: (1/2)(m + I/R^2)(v_f^2 - v_0^2) = ± m g h.

One rigid body rolling on one incline it is tangent to, approved pure-rolling
and server-valued uniform-gravity authorities, source-valued mass, rotation
radius, and central moment of inertia, and one value-free scalar
speed-magnitude query at the interval's end — in exactly one of the two
source-declared endpoint sub-shapes: a rest release descending a stated
interval height, or a source-valued start speed climbing to a height bound to
a typed ``reaches_condition`` end event.  Under pure rolling the contact does
no work, so the existing ``rolling_general_principal_energy`` law closes the
endpoint balance, with the rest boundary stated by the projected at_rest
state itself.  Any mixture of the sub-shapes, contrary height or start-speed
direction, extra quantity, or missing authority abstains without numeric
output.
"""

from __future__ import annotations

import hashlib

import pytest

from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    ROLLING_GRAVITY_QUANTITY_ID,
    ROLLING_GRAVITY_SYMBOL_ID,
    close_projected_draft,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1, PublicSplit
from evaluation.phase56_stage7.lane_b_authority import (
    build_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    run_lane_b_case,
)
from tests.support.phase56_stage7_corpus_fixtures import build_case

pytestmark = pytest.mark.slow

GRAVITY = 9.81


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    subject: str,
    *,
    event_role: str | None = None,
    temporal: str = "timeless",
    direction: str = "not_applicable",
) -> dict:
    return {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": "motion_1",
        "event_role": event_role,
        "temporal_role": temporal,
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _case(
    *,
    mode: str = "descent",
    mass: str = "2",
    radius: str = "0.5",
    radius_unit: str = "m",
    inertia: str = "0.25",
    height: str = "3",
    v0: str = "8",
    body_role: str = "wheel",
    incline_role: str = "slope",
    height_direction: str | None = None,
    v0_direction: str = "along_motion",
    drop_tangent: bool = False,
    duplicate_tangent: bool = False,
    drop_rolling: bool = False,
    drop_gravity: bool = False,
    drop_rest: bool = False,
    include_friction_coefficient: bool = False,
    include_angle: bool = False,
    second_body: bool = False,
    inertia_on_incline: bool = False,
    query_component: str = "magnitude",
    collision_id: str | None = None,
    strip_height_quote: bool = False,
    reverse: bool = False,
    family: str = "independent_rolling_fixture",
    case_id: str = "fx_public_dev_0956",
    text_variant: bool = False,
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    descent = mode == "descent"
    m_q = f"바퀴의 질량은 {mass} kg"
    r_q = f"바퀴의 반지름은 {radius} {radius_unit}"
    i_q = f"질량 중심에 대한 관성 모멘트는 {inertia} kg·m²"
    roll_q = "바퀴는 미끄러짐 없이 구른다"
    g_q = "중력 가속도는 일정하다"
    if descent:
        h_q = f"내려온 높이는 {height} m"
        rest_q = "정지 상태에서 놓는다"
        tail = "경사면 아래에서의 속력을 구하여라."
        extra = f"{rest_q}. "
    else:
        h_q = f"높이 {height} m 지점에 도달한다"
        v0_q = f"출발 속력은 {v0} m/s"
        tail = "그 지점에서의 속력을 구하여라."
        extra = f"{v0_q}. "
    text = f"{roll_q}. {extra}{m_q}. {r_q}. {i_q}. {h_q}. {g_q}. {tail}"
    if include_friction_coefficient:
        mu_q = "마찰 계수는 0.4"
        text += f" {mu_q}."
    if include_angle:
        ang_q = "경사각은 30 deg"
        text += f" {ang_q}."

    if text_variant:
        text = text.replace(". ", "! ", 3)

    entities = [
        {"role": body_role, "kind": "cylinder", "label": "바퀴"},
        {"role": incline_role, "kind": "incline", "label": "경사면"},
    ]
    if second_body:
        entities.append({"role": "second_wheel", "kind": "sphere", "label": "추가 바퀴"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})

    facts = [
        _fact("m", "mass", mass, "kg", m_q, body_role),
        _fact("r", "radius", radius, radius_unit, r_q, body_role),
        _fact("i", "moment_of_inertia", inertia, "kg*m^2", i_q,
              incline_role if inertia_on_incline else body_role),
    ]
    if descent:
        facts.append(
            _fact("h", "height", height, "m", h_q, body_role,
                  direction=height_direction or "downward")
        )
    else:
        facts.append(
            _fact("v0", "velocity", v0, "m/s",
                  f"출발 속력은 {v0} m/s", body_role, event_role="start",
                  temporal="at_event", direction=v0_direction)
        )
        facts.append(
            _fact("h", "height", height, "m", h_q, body_role,
                  event_role="finish", temporal="at_event",
                  direction=height_direction or "upward")
        )
    if strip_height_quote:
        next(f for f in facts if f["role"] == "h")["evidence_quote"] = None
    if include_friction_coefficient:
        facts.append(
            _fact("mu", "coefficient_of_friction", "0.4", "", "마찰 계수는 0.4",
                  incline_role)
        )
    if include_angle:
        facts.append(
            _fact("ang", "incline_angle", "30", "deg", "경사각은 30 deg",
                  incline_role)
        )

    relations = []
    if not drop_tangent:
        relations.append(
            {"role": "on_slope", "kind": "rolls_on",
             "participant_roles": [body_role, incline_role],
             "segment_role": "motion_1"}
        )
    if duplicate_tangent:
        relations.append(
            {"role": "on_slope_again", "kind": "rolls_on",
             "participant_roles": [body_role, incline_role],
             "segment_role": "motion_1"}
        )

    assumptions = []
    if not drop_rolling:
        assumptions.append(
            {"role": "roll", "kind": "pure_rolling", "subject_role": body_role,
             "segment_role": "motion_1", "supporting_quote": roll_q,
             "server_value_only": False}
        )
    if descent and not drop_rest:
        assumptions.append(
            {"role": "rest", "kind": "starts_from_rest",
             "subject_role": body_role, "segment_role": "motion_1",
             "supporting_quote": "정지 상태에서 놓는다",
             "server_value_only": True}
        )
    if not drop_gravity:
        assumptions.append(
            {"role": "g", "kind": "constant_gravity", "subject_role": body_role,
             "segment_role": "motion_1", "supporting_quote": g_q,
             "server_value_only": True}
        )

    events = (
        [
            {"role": "start", "kind": "release", "subject_roles": [body_role],
             "segment_role": "motion_1",
             "evidence_quote": "정지 상태에서 놓는다"},
            {"role": "finish", "kind": "finish", "subject_roles": [body_role],
             "segment_role": "motion_1", "evidence_quote": None},
        ]
        if descent
        else [
            {"role": "start", "kind": "start", "subject_roles": [body_role],
             "segment_role": "motion_1", "evidence_quote": None},
            {"role": "finish", "kind": "reaches_height",
             "subject_roles": [body_role], "segment_role": "motion_1",
             "evidence_quote": h_q},
        ]
    )

    gold = {
        "parse_status": "complete",
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": [
            {"role": "motion_1", "order": 1, "actor_roles": [body_role],
             "motion_model": "rolling_without_slipping", "relevance": "target",
             "start_event_role": "start", "end_event_role": "finish"}
        ],
        "events": events,
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions,
        "queries": [
            {"role": "q1", "output_key": "final_velocity",
             "subject_role": body_role, "segment_role": "motion_1",
             "component": query_component, "event_role": "finish"}
        ],
        "answers": (
            []
            if fake_answer is None
            else [
                {"query_role": "q1", "numeric": fake_answer, "unit": "m/s",
                 "tolerance_abs": 1.0e-6,
                 "reference_expression": "deliberately non-authoritative"}
            ]
        ),
        "expected_failure_codes": [],
    }
    if reverse:
        gold["entities"] = list(reversed(gold["entities"]))
        gold["explicit_facts"] = list(reversed(gold["explicit_facts"]))
        gold["events"] = list(reversed(gold["events"]))
        gold["assumption_proposals"] = list(
            reversed(gold["assumption_proposals"])
        )
    record = build_case(
        index=956,
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
    assert projection.draft is not None
    return projection


def _run(case: PublicCorpusCaseV1):
    return run_lane_b_case(_projection(case), execution_token="b13-test-token")


def _factor(mass: float, inertia: float, radius: float) -> float:
    return 1.0 + inertia / (mass * radius * radius)


def _descent(mass=2.0, inertia=0.25, radius=0.5, height=3.0) -> float:
    return (2.0 * GRAVITY * height / _factor(mass, inertia, radius)) ** 0.5


def _climb(v0=8.0, mass=2.0, inertia=0.25, radius=0.5, height=2.0) -> float:
    return (
        v0 * v0 - 2.0 * GRAVITY * height / _factor(mass, inertia, radius)
    ) ** 0.5


# --- positive controls ------------------------------------------------------


def test_rest_release_descent_solves_with_existing_generic_law() -> None:
    result = _run(_case())
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == (
        "rolling_general_principal_energy",
        "state_at_rest",
        "translational_speed_nonnegative",
    )
    assert result.verified_candidate_count == 1
    assert result.candidate_count == 2
    assert result.answer_value_si == pytest.approx(_descent())
    assert result.answer_unit == "m/s"


def test_valued_start_climb_solves_with_existing_generic_law() -> None:
    result = _run(_case(mode="climb", height="2"))
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == (
        "rolling_general_principal_energy",
        "translational_speed_nonnegative",
    )
    assert result.verified_candidate_count == 1
    assert result.answer_value_si == pytest.approx(_climb(height=2.0))


def test_centimetre_radius_converts_exactly() -> None:
    result = _run(_case(radius="50", radius_unit="cm"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(_descent())


def test_entity_ids_order_and_metadata_are_not_authority() -> None:
    baseline = _run(_case())
    for variant in (
        _case(body_role="hoop_q", incline_role="ramp_z"),
        _case(reverse=True),
        _case(
            family="renamed_family_for_metadata_control",
            case_id="fx_public_dev_0999",
            fake_answer=999999.0,
        ),
        _case(text_variant=True),
    ):
        result = _run(variant)
        assert result.terminal is LaneBTerminal.solved
        assert result.answer_value_si == pytest.approx(baseline.answer_value_si)
        assert result.candidate_count == baseline.candidate_count
        assert result.verified_candidate_count == baseline.verified_candidate_count


def test_physics_change_changes_the_answer_exactly() -> None:
    assert _run(_case(height="6")).answer_value_si == pytest.approx(
        _descent(height=6.0)
    )
    assert _run(_case(inertia="0.5")).answer_value_si == pytest.approx(
        _descent(inertia=0.5)
    )
    assert _run(
        _case(mode="climb", height="2", v0="10")
    ).answer_value_si == pytest.approx(_climb(v0=10.0, height=2.0))


def test_climb_beyond_reach_fails_closed_without_numeric_output() -> None:
    # v0^2 < 2 g h / (1 + I/(m R^2)): no real speed reaches the stated
    # height, so the shape must abstain rather than answer.
    result = _run(_case(mode="climb", height="40"))
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_transaction_adds_only_the_authorised_gravity_value() -> None:
    projection = _projection(_case())
    draft = projection.draft
    plan = plan_complete_profile(
        ProfileId.rolling_incline_energy_speed, draft
    )
    assert plan.disposition is PlanDisposition.complete
    bundle = build_lane_b_authority_bundle(projection)
    application = close_projected_draft(
        draft,
        approved_assumption_ids=tuple(bundle.approved_assumption_ids),
        authorized_assumptions=dict(bundle.authorization_map()),
    )
    assert application.applied
    assert application.profile_id is ProfileId.rolling_incline_energy_speed
    closed = application.draft
    assert len(closed.quantities) == len(draft.quantities) + 1
    assert len(closed.symbols) == len(draft.symbols) + 1
    assert not closed.reference_frames
    assert not closed.points
    assert not closed.interactions
    gravity = next(
        item
        for item in closed.quantities
        if item.quantity_id == ROLLING_GRAVITY_QUANTITY_ID
    )
    assert gravity.symbol_id == ROLLING_GRAVITY_SYMBOL_ID
    assert gravity.provenance.value == "server_default"
    assert gravity.assumption_policy_ref is not None
    speeds = [item for item in closed.quantities if item.role.value == "speed"]
    assert len(speeds) == 2
    assert all(item.raw_value is None for item in speeds)
    assert closed.queries[0].target.role.value == "speed"


# --- fail-closed controls ---------------------------------------------------


@pytest.mark.parametrize(
    "case",
    (
        _case(drop_tangent=True),
        _case(duplicate_tangent=True),
        _case(drop_rolling=True),
        _case(drop_gravity=True),
        _case(drop_rest=True),
        _case(height_direction="upward"),
        _case(mode="climb", height_direction="downward"),
        _case(mode="climb", v0_direction="upward"),
        _case(include_friction_coefficient=True),
        _case(include_angle=True),
        _case(second_body=True),
        _case(inertia_on_incline=True),
        _case(query_component="x"),
        _case(collision_id=ROLLING_GRAVITY_QUANTITY_ID),
        _case(strip_height_quote=True),
    ),
    ids=(
        "missing-tangency",
        "duplicate-tangency",
        "missing-pure-rolling-authority",
        "missing-gravity-authority",
        "release-without-rest-authority",
        "descent-height-stated-upward",
        "climb-height-stated-downward",
        "climb-start-speed-stated-upward",
        "unconsumed-friction-coefficient",
        "unconsumed-incline-angle",
        "second-rolling-body",
        "inertia-on-incline-not-body",
        "signed-component-query",
        "generated-gravity-id-collision",
        "evidence-free-height",
    ),
)
def test_structural_near_misses_fail_closed_without_numeric_output(case) -> None:
    projection = project_case_to_draft(case)
    if projection.draft is None:
        # The projection itself already refused the malformed source shape —
        # an even earlier fail-closed layer than the profile.
        assert projection.terminal.value == "projection_rejected"
        return
    result = run_lane_b_case(projection, execution_token="b13-test-token")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0
    assert "rolling_general_principal_energy" not in result.applied_law_ids


def test_gold_answer_tampering_cannot_change_runtime() -> None:
    baseline = _run(_case())
    tampered = _run(_case(fake_answer=123456.0))
    assert tampered.terminal is LaneBTerminal.solved
    assert tampered.answer_value_si == pytest.approx(baseline.answer_value_si)
