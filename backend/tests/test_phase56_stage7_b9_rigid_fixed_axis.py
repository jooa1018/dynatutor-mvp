"""B9 rigid fixed-axis point-speed package: v = |omega| r via fixed_axis_speed.

One rigid body rotating about a fixed axis, one source-declared point on the
body at a source-declared radius, one scalar speed-magnitude query on the
point.  The profile materialises the typed material point, rebinds radius and
the value-free query unknown onto the body scope, and normalises the scalar
velocity magnitude to the equivalent speed magnitude; the existing
``fixed_axis_speed`` generic law does all solving.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib

import pytest

from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    RIGID_AXIS_POINT_ID,
    TransactionAuthority,
    apply_complete_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1, PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    run_lane_b_case,
)
from tests.support.phase56_stage7_corpus_fixtures import build_case

pytestmark = pytest.mark.slow

EXPECTED_LAWS = ("fixed_axis_speed",)


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    subject: str,
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
        "event_role": None,
        "temporal_role": "timeless",
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
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
    omega: str = "4",
    omega_unit: str = "rad/s",
    omega_direction: str = "not_applicable",
    radius: str = "0.3",
    radius_unit: str = "m",
    body_role: str = "disk",
    point_role: str = "rim_point",
    swap_participants: bool = False,
    missing_relation: str | None = None,
    duplicate_relation: str | None = None,
    extra_body: bool = False,
    extra_body_lies_on: bool = False,
    include_body_mass: bool = False,
    include_assumption: bool = False,
    radius_subject: str | None = None,
    second_omega: bool = False,
    second_radius: bool = False,
    drop_omega: bool = False,
    include_alpha: bool = False,
    body_velocity: bool = False,
    omega_segment: str = "motion_1",
    query_output: str = "tangential_velocity",
    query_component: str = "magnitude",
    collision_id: str | None = None,
    reverse: bool = False,
    strip_radius_quote: bool = False,
    family: str = "independent_fixed_axis_fixture",
    case_id: str = "fx_public_dev_0951",
    text_variant: bool = False,
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    omega_quote = f"강체의 각속도는 {omega} {omega_unit}"
    radius_quote = f"축으로부터 점까지의 거리는 {radius} {radius_unit}"
    point_quote = "점 P는 강체 위에 있다"
    axis_quote = "강체는 고정축을 중심으로 회전한다"
    text = (
        f"{axis_quote}. {point_quote}. {omega_quote}. {radius_quote}. "
        "점 P의 속력 크기를 구하여라."
    )
    if text_variant:
        text = (
            f"{axis_quote}! {point_quote}! {omega_quote}! {radius_quote}! "
            "이때 점 P의 속력 크기를 구하여라."
        )

    entities = [
        {"role": body_role, "kind": "disk", "label": "회전 강체"},
        {"role": point_role, "kind": "point", "label": "점 P"},
    ]
    if extra_body:
        entities.append({"role": "second_body", "kind": "block", "label": "추가 강체"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})

    actors = [body_role, point_role]
    if extra_body:
        actors.append("second_body")

    facts = []
    if not drop_omega:
        facts.append(
            _fact(
                "omega",
                "angular_velocity",
                omega,
                omega_unit,
                omega_quote,
                body_role,
                direction=omega_direction,
            )
        )
    facts.append(
        _fact(
            "radius",
            "radius",
            radius,
            radius_unit,
            radius_quote if not strip_radius_quote else radius_quote,
            radius_subject or point_role,
        )
    )
    if strip_radius_quote:
        facts[-1]["evidence_quote"] = None
    if second_omega:
        second_quote = "다른 측정에서 각속도는 6 rad/s"
        text += f" {second_quote}."
        facts.append(
            _fact("omega_2", "angular_velocity", "6", "rad/s", second_quote, body_role)
        )
    if second_radius:
        second_quote = "다른 점까지의 거리는 0.5 m"
        text += f" {second_quote}."
        facts.append(
            _fact("radius_2", "radius", "0.5", "m", second_quote, point_role)
        )
    if include_alpha:
        alpha_quote = "각가속도는 2 rad/s²"
        text += f" {alpha_quote}."
        facts.append(
            _fact("alpha", "angular_acceleration", "2", "rad/s²", alpha_quote, body_role)
        )
    if include_body_mass:
        mass_quote = "강체의 질량은 5 kg"
        text += f" {mass_quote}."
        facts.append(_fact("body_mass", "mass", "5", "kg", mass_quote, body_role))
    if body_velocity:
        drift_quote = "축의 이동 속도는 1 m/s"
        text += f" {drift_quote}."
        facts.append(_fact("drift", "velocity", "1", "m/s", drift_quote, body_role))
    if omega_segment != "motion_1":
        facts[0]["segment_role"] = omega_segment

    lies_participants = [body_role, point_role]
    axis_participants = [body_role, point_role]
    if swap_participants:
        lies_participants = [point_role, body_role]
        axis_participants = [point_role, body_role]
    relations = [
        _relation("point_topology", "point_on_body", lies_participants),
        _relation("axis_topology", "rotates_about", axis_participants),
    ]
    if extra_body_lies_on:
        relations.append(
            _relation("stray_topology", "point_on_body", [point_role, "second_body"])
        )
    if missing_relation is not None:
        relations = [item for item in relations if item["kind"] != missing_relation]
    if duplicate_relation is not None:
        original = next(
            item for item in relations if item["kind"] == duplicate_relation
        )
        duplicate = deepcopy(original)
        duplicate["role"] += "_duplicate"
        relations.append(duplicate)

    assumptions = []
    if include_assumption:
        assumption_quote = "축의 마찰은 무시한다"
        text += f" {assumption_quote}."
        assumptions.append(
            {
                "role": "axis_friction",
                "kind": "frictionless",
                "subject_role": body_role,
                "segment_role": "motion_1",
                "supporting_quote": assumption_quote,
                "server_value_only": True,
            }
        )

    segments = [
        {
            "role": "motion_1",
            "order": 1,
            "actor_roles": actors,
            "motion_model": "rotation_about_fixed_axis",
            "relevance": "target",
            "start_event_role": "start",
            "end_event_role": "finish",
        }
    ]
    if omega_segment != "motion_1":
        segments.append(
            {
                "role": omega_segment,
                "order": 2,
                "actor_roles": actors,
                "motion_model": "rotation_about_fixed_axis",
                "relevance": "context",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        )

    events = [
        {
            "role": "start",
            "kind": "start",
            "subject_roles": actors,
            "segment_role": "motion_1",
            "evidence_quote": None,
        },
        {
            "role": "finish",
            "kind": "finish",
            "subject_roles": actors,
            "segment_role": "motion_1",
            "evidence_quote": None,
        },
    ]

    if reverse:
        entities.reverse()
        facts.reverse()
        relations.reverse()
        events.reverse()

    gold = {
        "parse_status": "complete",
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": segments,
        "events": events,
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions,
        "queries": [
            {
                "role": "q1",
                "output_key": query_output,
                "subject_role": point_role,
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
                    "unit": "m/s",
                    "tolerance_abs": 1.0e-6,
                    "reference_expression": "deliberately non-authoritative",
                }
            ]
        ),
        "expected_failure_codes": [],
    }
    record = build_case(
        index=951,
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
    return run_lane_b_case(_projection(case), execution_token="b9-test-token")


def _expected(omega: float, radius: float) -> float:
    return abs(omega) * radius


# --- positive controls ------------------------------------------------------


def test_fixed_axis_point_speed_solves_with_existing_generic_law() -> None:
    result = _run(_case())
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == EXPECTED_LAWS
    assert result.verified_candidate_count == 1
    assert result.candidate_count == 1
    assert result.answer_value_si == pytest.approx(_expected(4.0, 0.3))
    assert result.answer_unit == "m/s"


@pytest.mark.parametrize("direction", ("clockwise", "counterclockwise"))
def test_signed_rotation_directions_share_the_same_speed(direction: str) -> None:
    result = _run(_case(omega_direction=direction))
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == EXPECTED_LAWS
    assert result.answer_value_si == pytest.approx(_expected(4.0, 0.3))


def test_centimetre_radius_converts_exactly() -> None:
    result = _run(_case(radius="30", radius_unit="cm"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(_expected(4.0, 0.3))


def test_entity_ids_order_and_participant_order_are_not_authority() -> None:
    baseline = _run(_case())
    for variant in (
        _case(body_role="rotor_x", point_role="edge_q"),
        _case(reverse=True),
        _case(swap_participants=True),
        _case(include_body_mass=True),
        _case(
            family="renamed_family_for_metadata_control",
            case_id="fx_public_dev_0999",
            fake_answer=999999.0,
        ),
        _case(text_variant=True),
    ):
        result = _run(variant)
        assert result.terminal is LaneBTerminal.solved
        assert result.applied_law_ids == EXPECTED_LAWS
        assert result.answer_value_si == pytest.approx(baseline.answer_value_si)
        assert result.candidate_count == baseline.candidate_count
        assert result.verified_candidate_count == baseline.verified_candidate_count


def test_physics_change_changes_the_answer_exactly() -> None:
    assert _run(_case(omega="8")).answer_value_si == pytest.approx(_expected(8.0, 0.3))
    assert _run(_case(radius="0.5")).answer_value_si == pytest.approx(
        _expected(4.0, 0.5)
    )


def test_query_subject_remains_the_source_point() -> None:
    case = _case()
    assert case.gold.queries[0].subject_role == "rim_point"
    result = _run(case)
    assert result.terminal is LaneBTerminal.solved
    # The closed readout is normalised onto the body scope while the material
    # point stays the bound carrier of the answer.
    assert result.query_role == "speed"
    assert result.query_subject_id == "disk"
    assert result.answer_component == "magnitude"


def test_transaction_adds_only_typed_point_and_value_free_rebinds() -> None:
    projection = _projection(_case())
    draft = projection.draft
    plan = plan_complete_profile(ProfileId.rigid_fixed_axis, draft)
    assert plan.disposition is PlanDisposition.complete
    application = apply_complete_profile(
        plan,
        draft,
        TransactionAuthority(
            approved_assumption_ids=frozenset(),
            authorized_assumptions=None,
        ),
    )
    assert application.applied
    closed = application.draft
    assert [item.point_id for item in closed.points] == [RIGID_AXIS_POINT_ID]
    assert len(closed.quantities) == len(draft.quantities)
    assert len(closed.symbols) == len(draft.symbols)
    assert not closed.reference_frames
    assert not closed.interactions
    by_role = {item.role.value: item for item in closed.quantities}
    speed = by_role["speed"]
    body_id = next(
        item.entity_id
        for item in closed.entities
        if item.primitive.value == "rigid_body"
    )
    assert speed.subject_id == body_id
    assert speed.point_id == RIGID_AXIS_POINT_ID
    assert speed.raw_value is None
    radius = by_role["radius"]
    assert radius.subject_id == body_id
    assert radius.point_id == RIGID_AXIS_POINT_ID
    assert radius.raw_value is not None
    query = closed.queries[0]
    assert query.target.role.value == "speed"
    assert query.target.subject_id == body_id
    assert query.target.point_id == RIGID_AXIS_POINT_ID


# --- fail-closed controls ---------------------------------------------------


@pytest.mark.parametrize(
    "case",
    (
        _case(missing_relation="point_on_body"),
        _case(missing_relation="rotates_about"),
        _case(duplicate_relation="point_on_body"),
        _case(duplicate_relation="rotates_about"),
        _case(extra_body=True),
        _case(extra_body=True, extra_body_lies_on=True),
        _case(radius_subject="disk"),
        _case(second_omega=True),
        _case(second_radius=True),
        _case(query_component="x"),
        _case(query_component="y"),
        _case(drop_omega=True, include_alpha=True),
        _case(body_velocity=True),
        _case(omega_segment="motion_2"),
        _case(collision_id=RIGID_AXIS_POINT_ID),
        _case(strip_radius_quote=True),
    ),
    ids=(
        "missing-point-on-body",
        "missing-rotates-about",
        "duplicate-point-on-body",
        "duplicate-rotates-about",
        "second-rigid-body",
        "point-shared-with-second-body",
        "radius-on-body-not-point",
        "two-angular-velocities",
        "two-radii",
        "signed-x-component-query",
        "signed-y-component-query",
        "alpha-without-omega",
        "moving-axis-velocity",
        "omega-from-other-segment",
        "generated-id-collision",
        "evidence-free-radius",
    ),
)
def test_structural_near_misses_fail_closed_without_numeric_output(case) -> None:
    projection = project_case_to_draft(case)
    if projection.draft is None:
        # The projection itself already refused the malformed source shape —
        # an even earlier fail-closed layer than the profile.
        assert projection.terminal.value == "projection_rejected"
        return
    result = run_lane_b_case(projection, execution_token="b9-test-token")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0
    assert "fixed_axis_speed" not in result.applied_law_ids


def test_unrelated_approved_assumption_is_not_answer_authority() -> None:
    # A frictionless proposal projects as server-valued authority
    # (coefficient_friction = 0).  The kinematic readout profile never
    # consumes value-bearing authority: it abstains rather than solve
    # alongside unspent authority, so the assumption can never become part
    # of the answer.
    with_assumption = _run(_case(include_assumption=True))
    assert with_assumption.terminal is not LaneBTerminal.solved
    assert with_assumption.answer_value_si is None
    assert with_assumption.verified_candidate_count == 0
    assert "fixed_axis_speed" not in with_assumption.applied_law_ids


def test_gold_answer_tampering_cannot_change_runtime() -> None:
    baseline = _run(_case())
    tampered = _run(_case(fake_answer=123456.0))
    assert tampered.terminal is LaneBTerminal.solved
    assert tampered.answer_value_si == pytest.approx(baseline.answer_value_si)
