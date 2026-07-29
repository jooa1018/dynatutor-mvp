"""B11 explicit resultant-force package: a_x = F_x / m via particle_newton_second.

One free particle whose typed model carries one source-valued mass, one
source-valued horizontally directed applied force, and one value-free signed
x-component acceleration query on the same interval — and nothing else.  By
the engine's free-body completeness contract a free particle acted on only by
applied forces is already closed, so the stated force is the typed model's
entire force system.  The profile materialises the world frame, the axis
bindings, and the applied-force interaction record the source's force
statement already is; the existing ``particle_newton_second`` generic law
does all solving.  Constrained shapes — any contact, rope, spring, second
force, or vertical direction — abstain exactly as before.
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
    RESULTANT_FORCE_FRAME_ID,
    RESULTANT_FORCE_INTERACTION_ID,
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

EXPECTED_LAWS = ("particle_newton_second",)


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    subject: str,
    *,
    temporal: str = "timeless",
    event_role: str | None = None,
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
    mass: str = "4",
    mass_unit: str = "kg",
    force: str = "10",
    force_unit: str = "N",
    force_direction: str = "right",
    particle_role: str = "particle_1",
    particle_kind: str = "particle",
    query_component: str = "x",
    query_output: str = "acceleration",
    second_force: bool = False,
    drop_mass: bool = False,
    second_mass: bool = False,
    include_velocity: bool = False,
    include_gravity_quantity: bool = False,
    extra_entity: bool = False,
    contact_relation: bool = False,
    force_at_event: bool = False,
    strip_force_quote: bool = False,
    include_assumption: bool = False,
    collision_id: str | None = None,
    reverse: bool = False,
    family: str = "independent_resultant_fixture",
    case_id: str = "fx_public_dev_0954",
    text_variant: bool = False,
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    m_quote = f"물체의 질량은 {mass} {mass_unit}"
    direction_word = "오른쪽" if force_direction == "right" else "왼쪽"
    f_quote = f"물체에 {direction_word}으로 {force} {force_unit}의 힘이 작용한다"
    text = (
        f"마찰이 없는 수평면 위의 입자를 생각하자. {m_quote}. {f_quote}. "
        "입자의 가속도의 x 성분을 구하여라."
    )
    if text_variant:
        text = (
            f"마찰이 없는 수평면 위의 입자! {m_quote}! {f_quote}! "
            "이때 입자의 가속도의 x 성분을 구하여라."
        )

    entities = [
        {"role": particle_role, "kind": particle_kind, "label": "입자"},
    ]
    if extra_entity:
        entities.append({"role": "surface_1", "kind": "surface", "label": "수평면"})
    if collision_id is not None:
        entities.append({"role": collision_id, "kind": "other", "label": "무관 항목"})
    actors = [particle_role]

    facts = []
    if not drop_mass:
        facts.append(_fact("m", "mass", mass, mass_unit, m_quote, particle_role))
    if second_mass:
        second_quote = "다른 측정에서 질량은 6 kg"
        text += f" {second_quote}."
        facts.append(_fact("m2", "mass", "6", "kg", second_quote, particle_role))
    facts.append(
        _fact(
            "f",
            "force",
            force,
            force_unit,
            f_quote,
            particle_role,
            temporal="at_event" if force_at_event else "during",
            event_role="start" if force_at_event else None,
            direction=force_direction,
        )
    )
    if strip_force_quote:
        facts[-1]["evidence_quote"] = None
    if second_force:
        second_quote = "또 다른 힘 5 N이 오른쪽으로 작용한다"
        text += f" {second_quote}."
        facts.append(
            _fact("f2", "force", "5", "N", second_quote, particle_role,
                  temporal="during", direction="right")
        )
    if include_velocity:
        v_quote = "입자의 속력은 3 m/s"
        text += f" {v_quote}."
        facts.append(_fact("v", "velocity", "3", "m/s", v_quote, particle_role))
    if include_gravity_quantity:
        g_quote = "중력 가속도는 9.8 m/s²"
        text += f" {g_quote}."
        facts.append(
            _fact("g", "gravitational_acceleration", "9.8", "m/s²", g_quote,
                  particle_role)
        )

    relations = []
    if contact_relation and extra_entity:
        relations.append(
            {
                "role": "on_surface",
                "kind": "slides_on",
                "participant_roles": [particle_role, "surface_1"],
                "segment_role": "motion_1",
            }
        )

    assumptions = []
    if include_assumption:
        assumption_quote = "표면 마찰은 무시한다"
        text += f" {assumption_quote}."
        assumptions.append(
            {
                "role": "no_friction",
                "kind": "frictionless",
                "subject_role": particle_role,
                "segment_role": "motion_1",
                "supporting_quote": assumption_quote,
                "server_value_only": True,
            }
        )

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
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {"role": "start", "kind": "start", "subject_roles": actors,
             "segment_role": "motion_1", "evidence_quote": None},
            {"role": "finish", "kind": "finish", "subject_roles": actors,
             "segment_role": "motion_1", "evidence_quote": None},
        ],
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions,
        "queries": [
            {
                "role": "q1",
                "output_key": query_output,
                "subject_role": particle_role,
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
    if reverse:
        gold["entities"] = list(reversed(gold["entities"]))
        gold["explicit_facts"] = list(reversed(gold["explicit_facts"]))
        gold["events"] = list(reversed(gold["events"]))
    record = build_case(
        index=954,
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
    return run_lane_b_case(_projection(case), execution_token="b11-test-token")


# --- positive controls ------------------------------------------------------


def test_free_particle_single_force_solves_with_newton_second_law() -> None:
    result = _run(_case())
    assert result.terminal is LaneBTerminal.solved
    assert result.applied_law_ids == EXPECTED_LAWS
    assert result.verified_candidate_count == 1
    assert result.candidate_count == 1
    assert result.answer_value_si == pytest.approx(2.5)
    assert result.answer_unit == "m/s^2"


def test_leftward_force_flips_the_signed_answer() -> None:
    result = _run(_case(force_direction="left"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(-2.5)


def test_kilonewton_force_converts_exactly() -> None:
    result = _run(_case(force="0.01", force_unit="kN"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(2.5)


def test_gram_mass_converts_exactly() -> None:
    result = _run(_case(mass="4000", mass_unit="g"))
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(2.5)


def test_entity_ids_order_and_metadata_are_not_authority() -> None:
    baseline = _run(_case())
    for variant in (
        _case(particle_role="body_q"),
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
        assert result.applied_law_ids == EXPECTED_LAWS
        assert result.answer_value_si == pytest.approx(baseline.answer_value_si)
        assert result.candidate_count == baseline.candidate_count
        assert result.verified_candidate_count == baseline.verified_candidate_count


def test_physics_change_changes_the_answer_exactly() -> None:
    assert _run(_case(force="20")).answer_value_si == pytest.approx(5.0)
    assert _run(_case(mass="8")).answer_value_si == pytest.approx(1.25)


def test_transaction_adds_only_frame_interaction_and_axis_bindings() -> None:
    projection = _projection(_case())
    draft = projection.draft
    plan = plan_complete_profile(ProfileId.explicit_resultant_force, draft)
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
    assert [item.frame_id for item in closed.reference_frames] == [
        RESULTANT_FORCE_FRAME_ID
    ]
    assert [item.interaction_id for item in closed.interactions] == [
        RESULTANT_FORCE_INTERACTION_ID
    ]
    assert closed.interactions[0].kind.value == "applied_force"
    assert not closed.points
    assert len(closed.quantities) == len(draft.quantities)
    assert len(closed.symbols) == len(draft.symbols)
    by_role = {item.role.value: item for item in closed.quantities}
    force = by_role["force"]
    assert force.component.value == "x"
    assert force.frame_id == RESULTANT_FORCE_FRAME_ID
    assert force.raw_value is not None
    mass = by_role["mass"]
    assert mass.component.value == "unspecified"
    assert mass.frame_id is None
    target = by_role["acceleration"]
    assert target.raw_value is None
    assert target.frame_id == RESULTANT_FORCE_FRAME_ID
    assert closed.interactions[0].quantity_ids == [force.quantity_id]


# --- fail-closed controls ---------------------------------------------------


@pytest.mark.parametrize(
    "case",
    (
        _case(second_force=True),
        _case(drop_mass=True),
        _case(second_mass=True),
        _case(include_velocity=True),
        _case(include_gravity_quantity=True),
        _case(extra_entity=True),
        _case(extra_entity=True, contact_relation=True),
        _case(force_at_event=True),
        _case(query_component="y"),
        _case(query_component="magnitude"),
        _case(particle_kind="block"),
        _case(collision_id=RESULTANT_FORCE_FRAME_ID),
        _case(collision_id=RESULTANT_FORCE_INTERACTION_ID),
        _case(strip_force_quote=True),
    ),
    ids=(
        "second-applied-force",
        "missing-mass",
        "two-masses",
        "unconsumed-velocity",
        "unconsumed-gravity-quantity",
        "extra-surface-entity",
        "contact-interaction-present",
        "event-scoped-force",
        "cross-axis-query",
        "magnitude-query",
        "rigid-body-not-particle",
        "generated-frame-id-collision",
        "generated-interaction-id-collision",
        "evidence-free-force",
    ),
)
def test_structural_near_misses_fail_closed_without_numeric_output(case) -> None:
    projection = project_case_to_draft(case)
    if projection.draft is None:
        # The projection itself already refused the malformed source shape —
        # an even earlier fail-closed layer than the profile.
        assert projection.terminal.value == "projection_rejected"
        return
    result = run_lane_b_case(projection, execution_token="b11-test-token")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0
    assert "particle_newton_second" not in result.applied_law_ids


def test_unrelated_approved_assumption_is_not_answer_authority() -> None:
    # A frictionless proposal projects as server-valued authority
    # (coefficient_friction = 0).  The closure never consumes value-bearing
    # authority: it abstains rather than solve alongside unspent authority.
    with_assumption = _run(_case(include_assumption=True))
    assert with_assumption.terminal is not LaneBTerminal.solved
    assert with_assumption.answer_value_si is None
    assert with_assumption.verified_candidate_count == 0


def test_gold_answer_tampering_cannot_change_runtime() -> None:
    baseline = _run(_case())
    tampered = _run(_case(fake_answer=123456.0))
    assert tampered.terminal is LaneBTerminal.solved
    assert tampered.answer_value_si == pytest.approx(baseline.answer_value_si)
