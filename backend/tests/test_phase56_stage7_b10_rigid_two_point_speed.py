"""B10 rigid two-point speed-transfer package: v_B = v_A * r_B / r_A.

One rigid body rotates about one source-declared fixed centre — the source's
own ``rotates_about`` relation, projected as the single ``coincident``
geometry record — and carries two source-declared on-body points, each at
its own source-valued rotation radius, all read at the same source-declared
instant.  The source states one point's scalar undirected speed and asks for
the other point's speed/velocity magnitude at that instant.  The profile
materialises the two typed material points, rebinds both radii and both
speed magnitudes onto the body scope, and adds one value-free shared
angular-speed magnitude; the existing ``fixed_axis_speed`` generic law
couples the two points and the ``angular_speed_nonnegative`` domain
predicate keeps the single admissible branch.

The shared typed centre is the load-bearing authority: two radii licence one
angular speed only when both are measured from the same fixed centre, and
the only typed proof of that identity is the body's sole rotation-centre
relation.  A floating context point — however it is labelled, and whatever
the problem text calls it — is not that proof, so the old general-plane
shape with an inert centre entity now refuses instead of solving.
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
    TWO_POINT_SPEED_KNOWN_POINT_ID,
    TWO_POINT_SPEED_OMEGA_QUANTITY_ID,
    TWO_POINT_SPEED_OMEGA_SYMBOL_ID,
    TWO_POINT_SPEED_QUERY_POINT_ID,
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

EXPECTED_LAWS = ("angular_speed_nonnegative", "fixed_axis_speed")


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    subject: str,
    *,
    event_role: str | None = "instant",
    temporal: str = "at_event",
    direction: str = "not_applicable",
    segment: str = "motion_1",
) -> dict:
    return {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": segment,
        "event_role": event_role,
        "temporal_role": temporal,
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
    v_a: str = "2",
    v_a_unit: str = "m/s",
    r_a: str = "0.2",
    r_a_unit: str = "m",
    r_b: str = "0.5",
    r_b_unit: str = "m",
    body_role: str = "plate",
    known_role: str = "point_a",
    query_role: str = "point_b",
    center_role: str = "center_o",
    center_label: str = "중심 O",
    drop_center: bool = False,
    floating_center: bool = False,
    duplicate_center_relation: bool = False,
    center_relation_to_known: bool = False,
    missing_relation: str | None = None,
    duplicate_relation: bool = False,
    center_bound: bool = False,
    center_radius: bool = False,
    center_speed: bool = False,
    center_actor: bool = False,
    extra_body: bool = False,
    include_interaction: bool = False,
    include_body_mass: bool = False,
    include_body_velocity: bool = False,
    include_source_omega: bool = False,
    include_assumption: bool = False,
    second_velocity: bool = False,
    drop_velocity: bool = False,
    radius_subject_body: bool = False,
    same_subject_query: bool = False,
    query_component: str = "magnitude",
    radius_event: str | None = "instant",
    velocity_event: str | None = "instant",
    strip_radius_quote: bool = False,
    collision_id: str | None = None,
    reverse: bool = False,
    swap_participants: bool = False,
    family: str = "independent_two_point_fixture",
    case_id: str = "fx_public_dev_0952",
    text_variant: bool = False,
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    r_a_quote = f"중심에서 점 A까지의 거리는 {r_a} {r_a_unit}"
    r_b_quote = f"중심에서 점 B까지의 거리는 {r_b} {r_b_unit}"
    v_a_quote = f"이 순간 점 A의 속력은 {v_a} {v_a_unit}"
    typed_center = not (drop_center or floating_center)
    opening = (
        "강체 판이 고정된 중심 O를 지나는 축을 중심으로 회전한다."
        if typed_center
        else "강체 판이 평면 운동을 한다."
    )
    text = (
        f"{opening} 점 A와 점 B는 판 위에 있다. {r_a_quote}. "
        f"{r_b_quote}. {v_a_quote}. 이 순간 점 B의 속력 크기를 구하여라."
    )
    if text_variant:
        text = (
            f"{opening} 점 A와 점 B는 판 위에 있다! {r_a_quote}! "
            f"{r_b_quote}! {v_a_quote}! 이때 점 B의 속력 크기를 구하여라."
        )

    entities = [
        {"role": body_role, "kind": "disk", "label": "강체 판"},
        {"role": known_role, "kind": "point", "label": "점 A"},
        {"role": query_role, "kind": "point", "label": "점 B"},
    ]
    if not drop_center:
        entities.append(
            {"role": center_role, "kind": "point", "label": center_label}
        )
    if extra_body:
        entities.append({"role": "second_body", "kind": "block", "label": "추가 강체"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})

    actors = [body_role, known_role, query_role]
    if center_actor and not drop_center:
        actors.append(center_role)

    facts = [
        _fact("r_a", "radius", r_a, r_a_unit, r_a_quote, known_role,
              event_role=radius_event,
              temporal="at_event" if radius_event else "timeless"),
        _fact("r_b", "radius", r_b, r_b_unit, r_b_quote,
              body_role if radius_subject_body else query_role),
    ]
    if not drop_velocity:
        facts.append(
            _fact("v_a", "velocity", v_a, v_a_unit, v_a_quote,
                  query_role if same_subject_query else known_role,
                  event_role=velocity_event,
                  temporal="at_event" if velocity_event else "timeless")
        )
    if strip_radius_quote:
        facts[0]["evidence_quote"] = None
    if center_radius and not drop_center:
        center_quote = "중심점까지의 거리는 0.1 m"
        text += f" {center_quote}."
        facts.append(_fact("r_o", "radius", "0.1", "m", center_quote, center_role))
    if center_speed and not drop_center:
        center_speed_quote = "중심 O의 속력은 1 m/s"
        text += f" {center_speed_quote}."
        facts.append(
            _fact("v_o", "velocity", "1", "m/s", center_speed_quote, center_role)
        )
    if second_velocity:
        second_quote = "점 B의 속력은 4 m/s"
        text += f" {second_quote}."
        facts.append(_fact("v_b", "velocity", "4", "m/s", second_quote, query_role))
    if include_source_omega:
        omega_quote = "판의 각속도는 10 rad/s"
        text += f" {omega_quote}."
        facts.append(
            _fact("omega", "angular_velocity", "10", "rad/s", omega_quote, body_role)
        )
    if include_body_mass:
        mass_quote = "판의 질량은 5 kg"
        text += f" {mass_quote}."
        facts.append(_fact("m", "mass", "5", "kg", mass_quote, body_role))
    if include_body_velocity:
        drift_quote = "판의 이동 속도는 1 m/s"
        text += f" {drift_quote}."
        facts.append(_fact("drift", "velocity", "1", "m/s", drift_quote, body_role))

    lies_a = [body_role, known_role]
    lies_b = [body_role, query_role]
    axis_participants = [body_role, center_role]
    if swap_participants:
        lies_a = [known_role, body_role]
        lies_b = [query_role, body_role]
        axis_participants = [center_role, body_role]
    relations = [
        _relation("a_on_body", "point_on_body", lies_a),
        _relation("b_on_body", "point_on_body", lies_b),
    ]
    if typed_center and not center_relation_to_known:
        relations.append(
            _relation("axis_topology", "rotates_about", axis_participants)
        )
    if center_relation_to_known and not drop_center:
        # The rotation relation names an on-body rim point, not the inert
        # centre: the typed centre identity is broken, not merely renamed.
        relations.append(
            _relation("axis_topology", "rotates_about", [body_role, known_role])
        )
    if center_bound and not drop_center:
        relations.append(
            _relation("center_on_body", "point_on_body", [body_role, center_role])
        )
    if missing_relation is not None:
        relations = [item for item in relations if item["role"] != missing_relation]
    if duplicate_relation:
        duplicate = deepcopy(relations[0])
        duplicate["role"] += "_duplicate"
        relations.append(duplicate)
    if duplicate_center_relation and typed_center:
        duplicate = deepcopy(
            next(item for item in relations if item["role"] == "axis_topology")
        )
        duplicate["role"] += "_duplicate"
        relations.append(duplicate)
    if include_interaction:
        relations.append(
            _relation("surface_contact", "contact_with", [body_role, "second_body"])
            if extra_body
            else _relation("self_contact", "contact_with", [body_role, known_role])
        )

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
            "motion_model": (
                "rotation_about_fixed_axis"
                if typed_center
                else "general_plane_motion"
            ),
            "relevance": "target",
            "start_event_role": "start",
            "end_event_role": "finish",
        }
    ]

    events = [
        {"role": "start", "kind": "start", "subject_roles": actors,
         "segment_role": "motion_1", "evidence_quote": None},
        {"role": "finish", "kind": "finish", "subject_roles": actors,
         "segment_role": "motion_1", "evidence_quote": None},
        {"role": "instant", "kind": "other", "subject_roles": actors,
         "segment_role": "motion_1", "evidence_quote": None},
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
                "output_key": "tangential_velocity",
                "subject_role": query_role,
                "segment_role": "motion_1",
                "component": query_component,
                "event_role": "instant",
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
        index=952,
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
    return run_lane_b_case(_projection(case), execution_token="b10-test-token")


def _expected(v_a: float, r_a: float, r_b: float) -> float:
    return v_a * r_b / r_a


# --- positive controls ------------------------------------------------------


def test_two_point_speed_transfer_solves_with_existing_generic_law() -> None:
    result = _run(_case())
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == EXPECTED_LAWS
    assert result.verified_candidate_count == 1
    assert result.candidate_count == 1
    assert result.answer_value_si == pytest.approx(_expected(2.0, 0.2, 0.5))
    assert result.answer_unit == "m/s"


def test_smaller_target_radius_scales_the_speed_down() -> None:
    result = _run(_case(r_b="0.1"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(_expected(2.0, 0.2, 0.1))


def test_centimetre_radii_convert_exactly() -> None:
    result = _run(_case(r_a="20", r_a_unit="cm", r_b="50", r_b_unit="cm"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(_expected(2.0, 0.2, 0.5))


def test_kilometre_per_hour_speed_converts_exactly() -> None:
    result = _run(_case(v_a="7.2", v_a_unit="km/h"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(_expected(2.0, 0.2, 0.5))


def test_entity_ids_order_and_participant_order_are_not_authority() -> None:
    baseline = _run(_case())
    for variant in (
        _case(body_role="rotor_x", known_role="edge_p", query_role="edge_q",
              center_role="pivot_z"),
        _case(reverse=True),
        _case(swap_participants=True),
        # The centre's label is not authority in either direction: a typed
        # centre relabelled as anything — even "순간중심" — still solves the
        # same, because the coincident relation, not the word, licenses it.
        _case(center_label="순간중심 I"),
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
    assert _run(_case(v_a="4")).answer_value_si == pytest.approx(
        _expected(4.0, 0.2, 0.5)
    )
    assert _run(_case(r_a="0.4")).answer_value_si == pytest.approx(
        _expected(2.0, 0.4, 0.5)
    )
    assert _run(_case(r_b="0.8")).answer_value_si == pytest.approx(
        _expected(2.0, 0.2, 0.8)
    )


def test_query_subject_remains_the_source_point() -> None:
    case = _case()
    assert case.gold.queries[0].subject_role == "point_b"
    result = _run(case)
    assert result.terminal is LaneBTerminal.solved
    # The closed readout is normalised onto the body scope while the material
    # point stays the bound carrier of the answer.
    assert result.query_role == "speed"
    assert result.query_subject_id == "plate"
    assert result.answer_component == "magnitude"


def test_transaction_adds_only_typed_points_and_value_free_records() -> None:
    projection = _projection(_case())
    draft = projection.draft
    plan = plan_complete_profile(ProfileId.rigid_two_point_speed, draft)
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
    assert sorted(item.point_id for item in closed.points) == sorted(
        (TWO_POINT_SPEED_KNOWN_POINT_ID, TWO_POINT_SPEED_QUERY_POINT_ID)
    )
    assert all(item.role.value == "material" for item in closed.points)
    assert len(closed.quantities) == len(draft.quantities) + 1
    assert len(closed.symbols) == len(draft.symbols) + 1
    assert not closed.reference_frames
    assert not closed.interactions
    body_id = next(
        item.entity_id
        for item in closed.entities
        if item.primitive.value == "rigid_body"
    )
    omega = next(
        item
        for item in closed.quantities
        if item.quantity_id == TWO_POINT_SPEED_OMEGA_QUANTITY_ID
    )
    assert omega.raw_value is None
    assert omega.raw_unit is None
    assert omega.provenance.value == "unknown"
    assert omega.subject_id == body_id
    assert omega.symbol_id == TWO_POINT_SPEED_OMEGA_SYMBOL_ID
    assert omega.component.value == "magnitude"
    speeds = [
        item for item in closed.quantities if item.role.value == "speed"
    ]
    assert len(speeds) == 2
    assert {item.point_id for item in speeds} == {
        TWO_POINT_SPEED_KNOWN_POINT_ID,
        TWO_POINT_SPEED_QUERY_POINT_ID,
    }
    assert all(item.subject_id == body_id for item in speeds)
    radii = [item for item in closed.quantities if item.role.value == "radius"]
    assert len(radii) == 2
    assert {item.point_id for item in radii} == {
        TWO_POINT_SPEED_KNOWN_POINT_ID,
        TWO_POINT_SPEED_QUERY_POINT_ID,
    }
    for speed in speeds:
        radius = next(
            item for item in radii if item.point_id == speed.point_id
        )
        assert radius.subject_id == body_id
        assert radius.raw_value is not None
    query = closed.queries[0]
    assert query.target.role.value == "speed"
    assert query.target.subject_id == body_id
    assert query.target.point_id == TWO_POINT_SPEED_QUERY_POINT_ID


# --- fail-closed controls ---------------------------------------------------


@pytest.mark.parametrize(
    "case",
    (
        _case(drop_center=True),
        _case(floating_center=True),
        _case(duplicate_center_relation=True),
        _case(center_relation_to_known=True),
        _case(missing_relation="axis_topology"),
        _case(missing_relation="a_on_body"),
        _case(missing_relation="b_on_body"),
        _case(duplicate_relation=True),
        _case(center_bound=True),
        _case(center_radius=True),
        _case(center_speed=True),
        _case(center_actor=True),
        _case(extra_body=True),
        _case(include_interaction=True),
        _case(include_body_mass=True),
        _case(include_body_velocity=True),
        _case(include_source_omega=True),
        _case(second_velocity=True),
        _case(drop_velocity=True),
        _case(radius_subject_body=True),
        _case(same_subject_query=True),
        _case(query_component="x"),
        _case(query_component="y"),
        _case(radius_event=None),
        _case(velocity_event=None),
        _case(collision_id=TWO_POINT_SPEED_OMEGA_QUANTITY_ID),
        _case(collision_id=TWO_POINT_SPEED_KNOWN_POINT_ID),
        _case(strip_radius_quote=True),
    ),
    ids=(
        "no-centre-entity",
        "floating-centre-without-rotation-relation",
        "two-rotation-centre-relations",
        "rotation-relation-names-a-rim-point",
        "rotation-relation-missing",
        "missing-known-point-on-body",
        "missing-query-point-on-body",
        "duplicate-point-on-body",
        "centre-also-bound-as-on-body-point",
        "radius-on-the-centre",
        "speed-on-the-centre",
        "centre-as-actor",
        "second-rigid-body",
        "contact-interaction-present",
        "body-mass-present",
        "moving-body-velocity",
        "source-valued-angular-velocity",
        "two-known-point-speeds",
        "no-known-point-speed",
        "radius-on-body-not-point",
        "known-speed-on-query-point",
        "signed-x-component-query",
        "signed-y-component-query",
        "radius-outside-the-instant",
        "speed-outside-the-instant",
        "generated-omega-id-collision",
        "generated-point-id-collision",
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
    result = run_lane_b_case(projection, execution_token="b10-test-token")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_the_old_general_plane_shape_refuses_whatever_the_ratio_says() -> None:
    # The pre-repair public shape: general plane motion, two radii, one
    # speed, and an inert centre entity no typed relation ever names.  The
    # numbers are exactly the ones whose ratio the old profile confidently
    # multiplied; refusing must not depend on them being "wrong", because
    # radii measured from two different reference points can produce any
    # ratio at all — including this one.
    for variant in (
        _case(floating_center=True),
        _case(floating_center=True, r_a="0.1", r_b="0.3", v_a="6"),
        _case(floating_center=True, center_label="순간중심 I"),
        _case(floating_center=True, text_variant=True),
        _case(
            floating_center=True,
            family="renamed_family_for_metadata_control",
            case_id="fx_public_dev_0999",
            fake_answer=5.0,
        ),
    ):
        result = _run(variant)
        assert result.terminal is not LaneBTerminal.solved
        assert result.answer_value_si is None
        assert result.verified_candidate_count == 0


def test_an_instant_centre_label_alone_never_licenses_the_coupling() -> None:
    # Renaming the floating centre "순간중심" (instantaneous centre) — in the
    # entity label and in the problem text — types nothing: there is no
    # approved instantaneous-centre authority in the projected source, so
    # the shape still refuses.  The same words on a typed fixed centre are
    # equally inert in the other direction (see the invariance battery).
    case = _case(floating_center=True, center_label="순간중심 I")
    projection = _projection(case)
    result = run_lane_b_case(projection, execution_token="b10-test-token")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


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


def test_gold_answer_tampering_cannot_change_runtime() -> None:
    baseline = _run(_case())
    tampered = _run(_case(fake_answer=123456.0))
    assert tampered.terminal is LaneBTerminal.solved
    assert tampered.answer_value_si == pytest.approx(baseline.answer_value_si)
