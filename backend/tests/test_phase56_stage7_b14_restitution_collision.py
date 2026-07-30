"""B14 1D restitution-impact package: momentum + restitution over one impact.

Exactly two closed bodies collide.  The source states both masses, both
approach velocities (each with its own left/right semantic direction at the
typed ``collision_start``), and one restitution coefficient, and asks for
exactly one body's signed x-component separation velocity at the typed
``collision_end``.  The projection's own closed-policy derivation authorises
``external_impulse_negligible`` per body — a statement of the typed model's
completeness (the collision is the entire interaction system over its own
interval), never a guess — and the profile's transaction materialises the
world frame, binds each stated direction onto its signed axis, links the
impact's own quantities into the collision record, and generates the
partner's value-free separation unknown.  The existing
``system_momentum_conservation`` and ``direct_restitution`` generic laws do
all solving, and the solver's collision static-boundary recognizer enforces
the coefficient's own [0, 1] domain: an unphysical coefficient keeps the
ordinary event refusal and no number is produced.
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
    COLLISION_PARTNER_AFTER_QUANTITY_ID,
    COLLISION_PARTNER_AFTER_SYMBOL_ID,
    COLLISION_RESTITUTION_FRAME_ID,
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

EXPECTED_LAWS = ("direct_restitution", "system_momentum_conservation")


def _direction_phrase(direction: str) -> str:
    return {"right": "오른쪽으로", "left": "왼쪽으로", "upward": "위로"}[direction]


def _case(
    *,
    m1: str = "2",
    m1_unit: str = "kg",
    m2: str = "3",
    m2_unit: str = "kg",
    v1: str = "4",
    v1_unit: str = "m/s",
    v1_direction: str = "right",
    v2: str = "1",
    v2_unit: str = "m/s",
    v2_direction: str = "left",
    e: str = "0.5",
    body_a_role: str = "body_a",
    body_b_role: str = "body_b",
    query_subject: str | None = None,
    query_component: str = "x",
    second_query: bool = False,
    start_kind: str = "collision_start",
    end_kind: str = "collision_end",
    drop_collision: bool = False,
    duplicate_collision: bool = False,
    drop_coefficient: bool = False,
    second_coefficient: bool = False,
    drop_v2: bool = False,
    v2_directionless: bool = False,
    v1_at_end: bool = False,
    query_at_start: bool = False,
    third_body: bool = False,
    external_force: bool = False,
    gravity_proposal: bool = False,
    contact_relation: bool = False,
    collision_id: str | None = None,
    strip_mass_quote: bool = False,
    reverse: bool = False,
    swap_participants: bool = False,
    family: str = "independent_restitution_fixture",
    case_id: str = "fx_public_dev_0957",
    text_variant: bool = False,
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    m1_q = f"물체 A의 질량은 {m1} {m1_unit}"
    m2_q = f"물체 B의 질량은 {m2} {m2_unit}"
    v1_q = f"충돌 직전 물체 A의 속도는 {_direction_phrase(v1_direction)} {v1} {v1_unit}"
    v2_q = f"충돌 직전 물체 B의 속도는 {_direction_phrase(v2_direction)} {v2} {v2_unit}"
    e_q = f"반발 계수는 {e}"
    text = (
        f"두 물체가 일직선 위에서 충돌한다. {m1_q}. {m2_q}. {v1_q}. {v2_q}. "
        f"{e_q}. 충돌 직후 물체의 속도를 구하여라."
    )
    if text_variant:
        text = (
            f"두 물체가 일직선 위에서 충돌한다! {m1_q}! {m2_q}! {v1_q}! {v2_q}! "
            f"{e_q}! 이때 충돌 직후 물체의 속도를 구하여라!"
        )

    entities = [
        {"role": body_a_role, "kind": "block", "label": "물체 A"},
        {"role": body_b_role, "kind": "block", "label": "물체 B"},
    ]
    if third_body:
        entities.append({"role": "body_c", "kind": "block", "label": "물체 C"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})

    actors = [body_a_role, body_b_role]

    def fact(role, key, value, unit, quote, subject, *, event=None,
             temporal="timeless", direction="not_applicable"):
        return {
            "role": role, "semantic_key": key, "raw_value": value,
            "raw_unit": unit, "evidence_quote": quote, "subject_role": subject,
            "segment_role": "impact_1", "event_role": event,
            "temporal_role": temporal, "direction": direction,
            "relevance": "solver_input", "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        }

    facts = [
        fact("m1", "mass_1", m1, m1_unit, m1_q, body_a_role),
        fact("m2", "mass_2", m2, m2_unit, m2_q, body_b_role),
        fact("v1b", "velocity_before", v1, v1_unit, v1_q, body_a_role,
             event="impact_end" if v1_at_end else "impact_start",
             temporal="at_event", direction=v1_direction),
    ]
    if strip_mass_quote:
        facts[0]["evidence_quote"] = None
    if not drop_v2:
        facts.append(
            fact("v2b", "velocity_before", v2, v2_unit, v2_q, body_b_role,
                 event="impact_start", temporal="at_event",
                 direction="not_applicable" if v2_directionless else v2_direction)
        )
    if not drop_coefficient:
        facts.append(fact("e", "restitution_coefficient", e, "", e_q, body_a_role))
    if second_coefficient:
        e2_q = "다른 반발 계수는 0.9"
        text += f" {e2_q}."
        facts.append(
            fact("e2", "restitution_coefficient", "0.9", "", e2_q, body_b_role)
        )
    if external_force:
        f_q = "물체 A에는 수평 힘 10 N이 작용한다"
        text += f" {f_q}."
        facts.append(
            fact("f", "force", "10", "N", f_q, body_a_role,
                 temporal="during", direction="right")
        )

    relations = [] if drop_collision else [
        {"role": "impact", "kind": "collides_with",
         "participant_roles": (
             [body_b_role, body_a_role]
             if swap_participants
             else [body_a_role, body_b_role]
         ),
         "segment_role": "impact_1"},
    ]
    if duplicate_collision:
        duplicate = deepcopy(relations[0])
        duplicate["role"] += "_duplicate"
        relations.append(duplicate)
    if contact_relation:
        entities.append({"role": "floor", "kind": "surface", "label": "바닥"})
        relations.append(
            {"role": "support", "kind": "contact_with",
             "participant_roles": [body_a_role, "floor"],
             "segment_role": "impact_1"}
        )

    assumptions = []
    if gravity_proposal:
        g_q = "중력 가속도는 일정하다"
        text += f" {g_q}."
        assumptions.append(
            {"role": "g_const", "kind": "constant_gravity",
             "subject_role": body_a_role, "segment_role": "impact_1",
             "supporting_quote": g_q, "server_value_only": True}
        )

    queries = [
        {"role": "q1", "output_key": "v1_after",
         "subject_role": query_subject or body_a_role,
         "segment_role": "impact_1", "component": query_component,
         "event_role": "impact_start" if query_at_start else "impact_end"}
    ]
    if second_query:
        queries.append(
            {"role": "q2", "output_key": "v2_after", "subject_role": body_b_role,
             "segment_role": "impact_1", "component": "x",
             "event_role": "impact_end"}
        )

    gold = {
        "parse_status": "complete",
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": [
            {"role": "impact_1", "order": 1, "actor_roles": actors,
             "motion_model": "unknown", "relevance": "target",
             "start_event_role": "impact_start", "end_event_role": "impact_end"}
        ],
        "events": [
            {"role": "impact_start", "kind": start_kind,
             "subject_roles": actors, "segment_role": "impact_1",
             "evidence_quote": None},
            {"role": "impact_end", "kind": end_kind,
             "subject_roles": actors, "segment_role": "impact_1",
             "evidence_quote": None},
        ],
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions,
        "queries": queries,
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
        index=957,
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
    return run_lane_b_case(_projection(case), execution_token="b14-test-token")


def _signed(value: str, direction: str) -> float:
    return float(value) * (1.0 if direction == "right" else -1.0)


def _expected_v1_after(
    m1: float, m2: float, v1: float, v2: float, e: float
) -> float:
    # Momentum: m1 v1 + m2 v2 = m1 v1' + m2 v2'; restitution:
    # v2' - v1' = -e (v2 - v1).  Solving for v1':
    return (m1 * v1 + m2 * v2 - m2 * e * (v1 - v2)) / (m1 + m2)


# --- positive controls ------------------------------------------------------


def test_restitution_impact_solves_with_existing_generic_laws() -> None:
    result = _run(_case())
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == EXPECTED_LAWS
    assert result.verified_candidate_count == 1
    assert result.candidate_count == 1
    assert result.answer_value_si == pytest.approx(
        _expected_v1_after(2.0, 3.0, 4.0, -1.0, 0.5)
    )
    assert result.answer_component == "x"
    assert result.answer_unit == "m/s"


def test_perfectly_elastic_and_plastic_limits_solve_exactly() -> None:
    elastic = _run(_case(e="1"))
    assert elastic.terminal is LaneBTerminal.solved
    assert elastic.answer_value_si == pytest.approx(
        _expected_v1_after(2.0, 3.0, 4.0, -1.0, 1.0)
    )
    plastic = _run(_case(e="0"))
    assert plastic.terminal is LaneBTerminal.solved
    # e = 0 gives the common post-impact velocity of the joined pair.
    assert plastic.answer_value_si == pytest.approx(
        (2.0 * 4.0 + 3.0 * -1.0) / 5.0
    )


def test_unit_conversion_is_exact() -> None:
    result = _run(_case(v1="14.4", v1_unit="km/h", m2="3000", m2_unit="g"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(
        _expected_v1_after(2.0, 3.0, 4.0, -1.0, 0.5)
    )


def test_rear_end_impact_with_both_bodies_moving_right_solves() -> None:
    result = _run(_case(v2_direction="right", v2="1"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(
        _expected_v1_after(2.0, 3.0, 4.0, 1.0, 0.5)
    )


def test_partner_separation_velocity_query_solves_too() -> None:
    case = _case()
    gold = case.gold.model_dump()
    gold["queries"] = [
        {"role": "q1", "output_key": "v2_after", "subject_role": "body_b",
         "segment_role": "impact_1", "component": "x",
         "event_role": "impact_end"}
    ]
    case = case.model_copy(update={"gold": type(case.gold)(**gold)})
    result = _run(case)
    assert result.terminal is LaneBTerminal.solved
    v1_after = _expected_v1_after(2.0, 3.0, 4.0, -1.0, 0.5)
    assert result.answer_value_si == pytest.approx(v1_after + 0.5 * (4.0 - -1.0))


def test_entity_ids_order_and_metadata_are_not_authority() -> None:
    baseline = _run(_case())
    for variant in (
        _case(body_a_role="cart_p", body_b_role="cart_q",
              query_subject="cart_p"),
        _case(reverse=True),
        _case(swap_participants=True),
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
    assert _run(_case(m1="4")).answer_value_si == pytest.approx(
        _expected_v1_after(4.0, 3.0, 4.0, -1.0, 0.5)
    )
    assert _run(_case(v1="6")).answer_value_si == pytest.approx(
        _expected_v1_after(2.0, 3.0, 6.0, -1.0, 0.5)
    )
    assert _run(_case(e="0.8")).answer_value_si == pytest.approx(
        _expected_v1_after(2.0, 3.0, 4.0, -1.0, 0.8)
    )
    # Reversing one stated direction is a different impact, not a rename.
    assert _run(_case(v2_direction="right")).answer_value_si == pytest.approx(
        _expected_v1_after(2.0, 3.0, 4.0, 1.0, 0.5)
    )


def test_transaction_adds_only_frame_linkage_and_partner_unknown() -> None:
    projection = _projection(_case())
    draft = projection.draft
    plan = plan_complete_profile(
        ProfileId.collision_restitution,
        draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    bundle = build_lane_b_authority_bundle(projection)
    application = close_projected_draft(
        draft,
        approved_assumption_ids=tuple(bundle.approved_assumption_ids),
        authorized_assumptions=dict(bundle.authorization_map()),
    )
    assert application.applied
    assert application.profile_id is ProfileId.collision_restitution
    closed = application.draft
    assert len(closed.reference_frames) == 1
    assert closed.reference_frames[0].frame_id == COLLISION_RESTITUTION_FRAME_ID
    assert len(closed.quantities) == len(draft.quantities) + 1
    assert len(closed.symbols) == len(draft.symbols) + 1
    assert not closed.points
    partner = next(
        item
        for item in closed.quantities
        if item.quantity_id == COLLISION_PARTNER_AFTER_QUANTITY_ID
    )
    assert partner.raw_value is None
    assert partner.provenance.value == "unknown"
    assert partner.symbol_id == COLLISION_PARTNER_AFTER_SYMBOL_ID
    assert partner.component.value == "x"
    impact = closed.interactions[0]
    assert impact.kind.value == "collision"
    assert impact.frame_id == COLLISION_RESTITUTION_FRAME_ID
    # Two masses, two approach velocities, the coefficient, the query
    # unknown, and the generated partner unknown all belong to the impact.
    assert len(impact.quantity_ids) == 7
    before = [
        item
        for item in closed.quantities
        if item.role.value == "velocity" and item.raw_value is not None
    ]
    assert len(before) == 2
    for item in before:
        assert item.component.value == "x"
        assert item.direction is not None
        assert item.direction.model_dump()["kind"] == "axis"
    # The derived isolation authority is spent, never created, here.
    assert len(closed.assumptions) == 2
    assert {item.kind for item in closed.assumptions} == {
        "external_impulse_negligible"
    }


# --- fail-closed controls ---------------------------------------------------


@pytest.mark.parametrize(
    "case",
    (
        _case(drop_collision=True),
        _case(duplicate_collision=True),
        _case(drop_coefficient=True),
        _case(second_coefficient=True),
        _case(e="1.5"),
        _case(e="-0.2"),
        _case(drop_v2=True),
        _case(v2_directionless=True),
        _case(v2_direction="upward"),
        _case(v1_at_end=True),
        _case(query_at_start=True),
        _case(query_component="magnitude"),
        _case(query_component="unspecified"),
        _case(second_query=True),
        _case(third_body=True),
        _case(external_force=True),
        _case(gravity_proposal=True),
        _case(contact_relation=True),
        _case(start_kind="start"),
        _case(end_kind="finish"),
        _case(start_kind="just_before_collision"),
        _case(collision_id=COLLISION_PARTNER_AFTER_QUANTITY_ID),
        _case(collision_id=COLLISION_RESTITUTION_FRAME_ID),
        _case(strip_mass_quote=True),
    ),
    ids=(
        "missing-collision-relation",
        "duplicate-collision-relation",
        "missing-restitution-coefficient",
        "two-restitution-coefficients",
        "coefficient-above-one",
        "coefficient-below-zero",
        "missing-second-approach-velocity",
        "directionless-approach-velocity",
        "vertical-approach-direction",
        "approach-velocity-bound-to-the-end",
        "query-at-the-collision-start",
        "magnitude-component-query",
        "unspecified-component-query",
        "two-queries-in-one-run",
        "third-body-present",
        "external-force-stated",
        "gravity-authority-present",
        "support-contact-present",
        "start-event-not-collision-start",
        "end-event-not-collision-end",
        "unmapped-before-event-kind",
        "generated-partner-id-collision",
        "generated-frame-id-collision",
        "evidence-free-mass",
    ),
)
def test_structural_near_misses_fail_closed_without_numeric_output(case) -> None:
    projection = project_case_to_draft(case)
    if projection.draft is None:
        # The projection itself already refused the malformed source shape —
        # an even earlier fail-closed layer than the profile.
        assert projection.terminal.value == "projection_rejected"
        return
    result = run_lane_b_case(projection, execution_token="b14-test-token")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_unphysical_coefficients_never_reach_a_number() -> None:
    # The collision recognizer's own [0, 1] domain keeps the event-scoped
    # refusal for an unphysical restitution coefficient: equations may
    # exist, but no solve plan forms and no candidate is produced.
    for bad in ("1.5", "-0.2", "2", "100"):
        result = _run(_case(e=bad))
        assert result.terminal is not LaneBTerminal.solved
        assert result.answer_value_si is None
        assert result.candidate_count == 0


def test_isolation_authority_is_never_derived_beside_other_structure() -> None:
    # The impulse-isolation derivation is completeness-based: any typed
    # carrier of outside mechanics — a support contact, a stated force, a
    # gravity authority, a third body — must leave the Draft with no
    # approved external_impulse_negligible authority at all.
    for variant in (
        _case(contact_relation=True),
        _case(external_force=True),
        _case(gravity_proposal=True),
        _case(third_body=True),
    ):
        projection = _projection(variant)
        assert not any(
            assumption.kind == "external_impulse_negligible"
            for assumption in projection.draft.assumptions
            if getattr(
                assumption.disposition, "value", assumption.disposition
            )
            == "approved"
            and assumption.assumption_id in projection.approvable_assumption_ids
        )


def test_gold_answer_tampering_cannot_change_runtime() -> None:
    baseline = _run(_case())
    tampered = _run(_case(fake_answer=123456.0))
    assert tampered.terminal is LaneBTerminal.solved
    assert tampered.answer_value_si == pytest.approx(baseline.answer_value_si)
