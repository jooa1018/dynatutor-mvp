"""B12 vertical-circle limiting-contact minimum: v^2 = g r only when typed.

The equality ``v^2 = g r`` at a circular track's highest point is the
N = 0 contact-maintenance boundary, not a property of the shape: it answers
the question only when the source asks for that boundary.  Four typed
authorities must all be present before anything closes —

* the query's own ``minimum`` objective (projected from the corpus's
  ``minimum_speed`` output key, and preserved end-to-end);
* the contact's ``inward`` side — an inside track pushes toward the centre,
  so contact maintenance bounds the speed from below;
* a ``contact``/``touching`` state condition over the motion interval;
* a ``boundary``/``active`` state condition at the highest-point instant.

The Lane B corpus projection can prove the first (the corpus's own typed
output key) but none of the others — the corpus schema has no typed contact
orientation and no typed boundary-condition record — so every corpus-shaped
fixture in this file now fails closed, exactly as the public cases must.
The positive controls state the full authority at the Draft level, which is
the contract a richer source-side schema (or the product modeler) has to
meet before this family may solve again.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID,
    VERTICAL_CIRCLE_GRAVITY_SYMBOL_ID,
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

EXPECTED_LAWS = (
    "translational_speed_nonnegative",
    "vertical_circle_top_minimum_speed",
)

_LIMIT_QUOTE = "접촉을 유지하기 위한 최소 속력"


def _case(
    *,
    radius: str = "2",
    radius_unit: str = "m",
    ball_role: str = "ball",
    track_role: str = "track",
    top_event_kind: str = "highest_point",
    drop_contact: bool = False,
    duplicate_contact: bool = False,
    drop_gravity_assumption: bool = False,
    gravity_on_track: bool = False,
    include_mass: bool = False,
    include_height: bool = False,
    include_initial_speed: bool = False,
    second_radius: bool = False,
    radius_on_track: bool = False,
    radius_at_event: bool = False,
    query_at_interval: bool = False,
    query_component: str = "magnitude",
    query_output: str = "minimum_speed",
    extra_entity: bool = False,
    collision_id: str | None = None,
    strip_radius_quote: bool = False,
    reverse: bool = False,
    family: str = "independent_vertical_circle_fixture",
    case_id: str = "fx_public_dev_0955",
    text_variant: bool = False,
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    r_quote = f"원형 궤도의 반지름은 {radius} {radius_unit}"
    g_quote = "중력 가속도는 일정하다"
    text = (
        f"질점이 매끄러운 원형 궤도 안쪽을 따라 돈다. {r_quote}. {g_quote}. "
        f"궤도 최고점에서 {_LIMIT_QUOTE}을 구하여라."
    )
    if text_variant:
        text = (
            f"질점이 매끄러운 원형 궤도 안쪽을 돈다! {r_quote}! {g_quote}! "
            f"이때 궤도 최고점에서 {_LIMIT_QUOTE}을 구하여라!"
        )

    entities = [
        {"role": ball_role, "kind": "particle", "label": "질점"},
        {"role": track_role, "kind": "surface", "label": "궤도"},
    ]
    if extra_entity:
        entities.append({"role": "second_ball", "kind": "particle", "label": "추가 질점"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})

    def _fact(role, key, value, unit, quote, subject, *, event_role=None,
              temporal="timeless"):
        return {
            "role": role, "semantic_key": key, "raw_value": value,
            "raw_unit": unit, "evidence_quote": quote, "subject_role": subject,
            "segment_role": "motion_1", "event_role": event_role,
            "temporal_role": temporal, "direction": "not_applicable",
            "relevance": "solver_input", "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        }

    facts = [
        _fact("r", "radius", radius, radius_unit, r_quote,
              track_role if radius_on_track else ball_role,
              event_role="top" if radius_at_event else None,
              temporal="at_event" if radius_at_event else "timeless"),
    ]
    if strip_radius_quote:
        facts[0]["evidence_quote"] = None
    if second_radius:
        second_quote = "다른 반지름은 3 m"
        text += f" {second_quote}."
        facts.append(_fact("r2", "radius", "3", "m", second_quote, ball_role))
    if include_mass:
        m_quote = "질점의 질량은 2 kg"
        text += f" {m_quote}."
        facts.append(_fact("m", "mass", "2", "kg", m_quote, ball_role))
    if include_height:
        h_quote = "궤도 최고점의 높이는 4 m"
        text += f" {h_quote}."
        facts.append(_fact("h", "height", "4", "m", h_quote, ball_role))
    if include_initial_speed:
        v_quote = "출발 속력은 12 m/s"
        text += f" {v_quote}."
        facts.append(_fact("v0", "velocity", "12", "m/s", v_quote, ball_role))

    relations = []
    if not drop_contact:
        relations.append(
            {"role": "on_track", "kind": "contact_with",
             "participant_roles": [ball_role, track_role],
             "segment_role": "motion_1"}
        )
    if duplicate_contact:
        relations.append(
            {"role": "on_track_again", "kind": "contact_with",
             "participant_roles": [ball_role, track_role],
             "segment_role": "motion_1"}
        )

    assumptions = []
    if not drop_gravity_assumption:
        assumptions.append(
            {"role": "g_const", "kind": "constant_gravity",
             "subject_role": track_role if gravity_on_track else ball_role,
             "segment_role": "motion_1", "supporting_quote": g_quote,
             "server_value_only": True}
        )

    gold = {
        "parse_status": "complete",
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": [
            {"role": "motion_1", "order": 1, "actor_roles": [ball_role],
             "motion_model": "unknown", "relevance": "target",
             "start_event_role": "start", "end_event_role": "finish"}
        ],
        "events": [
            {"role": "start", "kind": "start", "subject_roles": [ball_role],
             "segment_role": "motion_1", "evidence_quote": None},
            {"role": "finish", "kind": "finish", "subject_roles": [ball_role],
             "segment_role": "motion_1", "evidence_quote": None},
            {"role": "top", "kind": top_event_kind, "subject_roles": [ball_role],
             "segment_role": "motion_1", "evidence_quote": None},
        ],
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions,
        "queries": [
            {"role": "q1", "output_key": query_output,
             "subject_role": ball_role, "segment_role": "motion_1",
             "component": query_component,
             "event_role": None if query_at_interval else "top"}
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
        gold["relations"] = list(reversed(gold["relations"]))
    record = build_case(
        index=955,
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
    return run_lane_b_case(_projection(case), execution_token="b12-test-token")


def _authorised(
    case: PublicCorpusCaseV1,
    *,
    side: str | None = "inward",
    with_touching: bool = True,
    with_boundary: bool = True,
    boundary_event: str | None = None,
    state_subject: str | None = None,
    evidence_free_states: bool = False,
    strip_objective: bool = False,
):
    """The corpus projection plus the Draft-level typed limiting authority.

    Only the four typed authorities are added — contact side, the touching
    and boundary state conditions, and one text-evidence record for the
    source's own limiting phrase.  Nothing else in the projection changes,
    so what these controls measure is exactly the authority contract.
    """

    projection = _projection(case)
    payload = projection.draft.model_dump(mode="python")
    subject = state_subject or payload["motion_intervals"][0]["subject_ids"][0]
    interval_id = payload["motion_intervals"][0]["interval_id"]
    top_ids = [
        item["event_id"]
        for item in payload["events"]
        if item["kind"] == "highest_point"
    ]
    top_id = boundary_event or (top_ids[0] if top_ids else "top")
    quote = _LIMIT_QUOTE
    start = projection.problem_text.index(quote)
    payload["source_evidence"] = [
        *payload["source_evidence"],
        {
            "kind": "text",
            "evidence_id": "ev_contact_limit",
            "quote": quote,
            "source_span": {"start": start, "end": start + len(quote)},
            "occurrence_index": 0,
        },
    ]
    state_evidence = [] if evidence_free_states else ["ev_contact_limit"]
    states = []
    if with_touching:
        states.append(
            {
                "state_condition_id": "st_maintained_contact",
                "kind": "contact",
                "state": "touching",
                "subject_id": subject,
                "interval_id": interval_id,
                "event_id": None,
                "quantity_ids": [],
                "evidence_refs": list(state_evidence),
            }
        )
    if with_boundary:
        states.append(
            {
                "state_condition_id": "st_limiting_boundary",
                "kind": "boundary",
                "state": "active",
                "subject_id": subject,
                "interval_id": interval_id,
                "event_id": top_id,
                "quantity_ids": [],
                "evidence_refs": list(state_evidence),
            }
        )
    payload["state_conditions"] = states
    if side is not None:
        for interaction in payload["interactions"]:
            if interaction["kind"] == "contact":
                interaction["contact_side"] = side
    if strip_objective:
        for query in payload["queries"]:
            query["objective"] = None
    draft = MechanicsProblemDraftV1.model_validate(payload)
    return replace(projection, draft=draft)


def _run_authorised(case: PublicCorpusCaseV1, **kwargs):
    return run_lane_b_case(
        _authorised(case, **kwargs), execution_token="b12-test-token"
    )


def _expected(radius: float, gravity: float = 9.81) -> float:
    return (gravity * radius) ** 0.5


# --- the projection preserves the question ----------------------------------


def test_the_minimum_objective_survives_projection() -> None:
    draft = _projection(_case()).draft
    assert draft.queries[0].objective is not None
    assert draft.queries[0].objective.value == "minimum"
    assert draft.queries[0].target.role.value == "speed"


def test_a_plain_speed_query_carries_no_objective() -> None:
    draft = _projection(_case(query_output="tangential_velocity")).draft
    assert draft.queries[0].objective is None


# --- positive controls (full typed authority, Draft level) ------------------


def test_typed_limiting_contact_solves_with_existing_generic_law() -> None:
    result = _run_authorised(_case())
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == EXPECTED_LAWS
    assert result.verified_candidate_count == 1
    assert result.candidate_count == 2
    assert result.rejected_candidate_count == 1
    assert result.answer_value_si == pytest.approx(_expected(2.0))
    assert result.answer_unit == "m/s"


def test_centimetre_radius_converts_exactly() -> None:
    result = _run_authorised(_case(radius="200", radius_unit="cm"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(_expected(2.0))


def test_entity_ids_order_and_metadata_are_not_authority() -> None:
    baseline = _run_authorised(_case())
    for variant in (
        _case(ball_role="bead_q", track_role="loop_z"),
        _case(reverse=True),
        _case(
            family="renamed_family_for_metadata_control",
            case_id="fx_public_dev_0999",
            fake_answer=999999.0,
        ),
        _case(text_variant=True),
    ):
        result = _run_authorised(variant)
        assert result.terminal is LaneBTerminal.solved
        assert result.applied_law_ids == EXPECTED_LAWS
        assert result.answer_value_si == pytest.approx(baseline.answer_value_si)
        assert result.candidate_count == baseline.candidate_count
        assert result.verified_candidate_count == baseline.verified_candidate_count


def test_physics_change_changes_the_answer_exactly() -> None:
    assert _run_authorised(_case(radius="8")).answer_value_si == pytest.approx(
        _expected(8.0)
    )
    assert _run_authorised(_case(radius="0.5")).answer_value_si == pytest.approx(
        _expected(0.5)
    )


def test_transaction_adds_only_the_authorised_gravity_value() -> None:
    projection = _authorised(_case())
    draft = projection.draft
    plan = plan_complete_profile(ProfileId.vertical_circle_top_speed, draft)
    assert plan.disposition is PlanDisposition.complete
    bundle = build_lane_b_authority_bundle(projection)
    application = close_projected_draft(
        draft,
        approved_assumption_ids=tuple(bundle.approved_assumption_ids),
        authorized_assumptions=dict(bundle.authorization_map()),
    )
    assert application.applied
    assert application.profile_id is ProfileId.vertical_circle_top_speed
    closed = application.draft
    assert len(closed.quantities) == len(draft.quantities) + 1
    assert len(closed.symbols) == len(draft.symbols) + 1
    assert not closed.reference_frames
    assert not closed.points
    # The typed limiting authority rides through the closure unchanged.
    assert closed.interactions[0].contact_side is not None
    assert closed.interactions[0].contact_side.value == "inward"
    assert len(closed.state_conditions) == 2
    assert closed.queries[0].objective is not None
    assert closed.queries[0].objective.value == "minimum"
    gravity = next(
        item
        for item in closed.quantities
        if item.quantity_id == VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID
    )
    assert gravity.symbol_id == VERTICAL_CIRCLE_GRAVITY_SYMBOL_ID
    assert gravity.provenance.value == "server_default"
    assert gravity.assumption_policy_ref is not None
    assert gravity.raw_value is not None
    target = next(
        item for item in closed.quantities if item.role.value == "speed"
    )
    assert target.raw_value is None
    assert closed.queries[0].target.role.value == "speed"


# --- the public corpus shape fails closed -----------------------------------


def test_the_corpus_shape_alone_refuses_the_boundary_equality() -> None:
    # The exact public structure: minimum_speed query, contact, radius,
    # gravity, highest point — and no typed contact orientation, no typed
    # boundary condition, because the corpus schema cannot state them.  The
    # projected objective survives, but the missing authorities keep the
    # boundary equality unlicensed: the case must not solve, whatever the
    # correct-looking number would have been.
    for variant in (
        _case(),
        _case(text_variant=True),
        _case(
            family="renamed_family_for_metadata_control",
            case_id="fx_public_dev_0999",
            fake_answer=4.4294469180700204,
        ),
    ):
        result = _run(variant)
        assert result.terminal is not LaneBTerminal.solved
        assert result.answer_value_si is None
        assert result.verified_candidate_count == 0
        assert "vertical_circle_top_minimum_speed" not in result.applied_law_ids


def test_no_other_profile_may_touch_an_objective_bearing_query() -> None:
    # The planner-level guard: an extremal question is a different question,
    # so a profile that does not understand objectives refuses the draft
    # outright — before any shape matching.  Only the vertical-circle
    # profile may even consider it, and on the bare corpus shape it still
    # refuses on its missing typed authorities.
    draft = _projection(_case()).draft
    assert draft.queries[0].objective is not None
    for profile_id in ProfileId:
        plan = plan_complete_profile(profile_id, draft)
        assert plan.disposition is not PlanDisposition.complete
        if profile_id is not ProfileId.vertical_circle_top_speed:
            assert plan.disposition is PlanDisposition.not_applicable


# --- fail-closed controls (corpus-shaped near misses) -----------------------


@pytest.mark.parametrize(
    "case",
    (
        _case(query_output="tangential_velocity"),
        _case(query_output="final_velocity"),
        _case(drop_contact=True),
        _case(duplicate_contact=True),
        _case(drop_gravity_assumption=True),
        _case(gravity_on_track=True),
        _case(include_mass=True),
        _case(include_height=True),
        _case(include_initial_speed=True),
        _case(second_radius=True),
        _case(radius_on_track=True),
        _case(radius_at_event=True),
        _case(query_at_interval=True),
        _case(query_component="x"),
        _case(top_event_kind="lowest_point"),
        _case(extra_entity=True),
        _case(collision_id=VERTICAL_CIRCLE_GRAVITY_QUANTITY_ID),
        _case(strip_radius_quote=True),
    ),
    ids=(
        "plain-top-speed-query",
        "exact-final-speed-query",
        "missing-contact",
        "duplicate-contact",
        "missing-gravity-authority",
        "gravity-authorised-for-track",
        "unconsumed-mass",
        "unconsumed-height",
        "unconsumed-initial-speed",
        "two-radii",
        "radius-on-track-not-particle",
        "radius-bound-to-the-event",
        "query-not-at-the-event",
        "signed-component-query",
        "lowest-point-event",
        "second-particle",
        "generated-gravity-id-collision",
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
    result = run_lane_b_case(projection, execution_token="b12-test-token")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0
    assert "vertical_circle_top_minimum_speed" not in result.applied_law_ids


def test_a_maximum_speed_question_has_no_projection_at_all() -> None:
    # The corpus query vocabulary has no maximum_speed key, so an
    # outside-track maximum question cannot even reach the engine — and it
    # must reach nothing rather than be silently reinterpreted.
    projection = project_case_to_draft(_case(query_output="maximum_speed"))
    assert projection.draft is None
    assert projection.terminal.value == "projection_rejected"


# --- fail-closed controls (authority variations, Draft level) ---------------


@pytest.mark.parametrize(
    "kwargs",
    (
        dict(side=None),
        dict(side="outward"),
        dict(with_touching=False),
        dict(with_boundary=False),
        dict(with_touching=False, with_boundary=False),
        dict(boundary_event="start"),
        dict(state_subject="track"),
        dict(evidence_free_states=True),
        dict(strip_objective=True),
    ),
    ids=(
        "orientation-unstated",
        "outside-track-contact",
        "no-maintained-contact-state",
        "no-limiting-boundary-state",
        "no-states-at-all",
        "boundary-at-the-wrong-event",
        "states-on-the-track-not-the-particle",
        "evidence-free-states",
        "exact-question-despite-the-boundary-states",
    ),
)
def test_authority_variations_fail_closed_without_numeric_output(kwargs) -> None:
    result = _run_authorised(_case(), **kwargs)
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0
    assert "vertical_circle_top_minimum_speed" not in result.applied_law_ids


def test_gold_answer_tampering_cannot_change_runtime() -> None:
    baseline = _run_authorised(_case())
    tampered = _run_authorised(_case(fake_answer=123456.0))
    assert tampered.terminal is LaneBTerminal.solved
    assert tampered.answer_value_si == pytest.approx(baseline.answer_value_si)
