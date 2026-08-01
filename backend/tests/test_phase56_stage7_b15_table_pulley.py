"""B15: source-typed frictionless table/hanging fixed-pulley closure."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1, Provenance
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    TABLE_PULLEY_GRAVITY_ID,
    TABLE_PULLEY_ORIENTATION_RELATION_ID,
    TABLE_PULLEY_WORLD_ID,
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
    "particle_newton_second",
    "particle_weight",
    "rope_fixed_pulley_motion",
    "rope_massless_tension",
}

# The frame identities a *fully authored* source Draft supplies.  They are
# fixture-owned on purpose: the closure no longer mints frames, so no product
# constant names them.
AUTHORED_WORLD_FRAME_ID = "frm_source_table_pulley_world"
AUTHORED_SUPPORT_FRAME_ID = "frm_source_table_pulley_support"


def _authored_axis(frame_id: str, axis: str, sign: int = 1) -> dict:
    return {"kind": "axis", "frame_id": frame_id, "axis": axis, "sign": sign}


def _stated_orientation_frames(
    *,
    support_id: str = "surface",
    tangent_axis: str = "x",
    normal_axis: str = "y",
    tangent_sign: int = 1,
    parent_frame_id: str | None = AUTHORED_WORLD_FRAME_ID,
    origin_entity_id: str | None = None,
    evidence: tuple[str, ...] = (),
) -> list[dict]:
    """The two frames a source authors to state a support's orientation.

    The support frame is the whole statement: its tangent names the world
    frame's x axis, so the support-owned angle finally has a reference line to
    be zero *against*.  Every knob here exists so a test can state a different
    orientation — or a broken one — and watch the closure refuse it.
    """

    return [
        {
            "frame_id": AUTHORED_WORLD_FRAME_ID,
            "frame_type": "cartesian_2d",
            "origin": {"kind": "world"},
            "axes": [
                {"axis": "x", "direction": _authored_axis(AUTHORED_WORLD_FRAME_ID, "x")},
                {"axis": "y", "direction": _authored_axis(AUTHORED_WORLD_FRAME_ID, "y")},
            ],
            "evidence_refs": list(evidence),
        },
        {
            "frame_id": AUTHORED_SUPPORT_FRAME_ID,
            "frame_type": "cartesian_2d",
            "origin": {
                "kind": "entity",
                "entity_id": origin_entity_id or support_id,
            },
            "parent_frame_id": parent_frame_id,
            "axes": [
                {
                    "axis": "tangent",
                    "direction": _authored_axis(
                        AUTHORED_WORLD_FRAME_ID, tangent_axis, tangent_sign
                    ),
                },
                {
                    "axis": "normal",
                    "direction": _authored_axis(AUTHORED_WORLD_FRAME_ID, normal_axis),
                },
            ],
            "evidence_refs": list(evidence),
        },
    ]


def _state_orientation(projection, **frame_overrides):
    """Return the same projection with the source's orientation stated.

    The public corpus cannot express an angle's reference axis — the
    projection emits ``reference_frames: []`` for every case — so a stated
    orientation only ever reaches the engine from a fully authored Draft.
    This helper builds exactly that Draft, and nothing else about the case
    changes.
    """

    payload = projection.draft.model_dump(mode="json", warnings="none")
    frame_overrides.setdefault("evidence", _orientation_evidence(payload))
    payload["reference_frames"] = _stated_orientation_frames(**frame_overrides)
    return replace(
        projection, draft=MechanicsProblemDraftV1.model_validate(payload)
    )


def _orientation_evidence(payload: dict) -> tuple[str, ...]:
    """The source evidence a stated orientation cites.

    The support's own angle statement when the case makes one; otherwise the
    first source evidence, so that a case *without* an angle can still author
    a well-formed frame and be refused for the reason under test rather than
    for a dangling evidence reference.
    """

    for quantity in payload["quantities"]:
        if quantity["role"] == "angle" and quantity["subject_id"] == "surface":
            return tuple(quantity["evidence_refs"])
    return (payload["source_evidence"][0]["evidence_id"],)


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
    mass_a: str = "5",
    mass_a_unit: str = "kg",
    mass_b: str = "2",
    mass_b_unit: str = "kg",
    surface_kind: str = "surface",
    support_angle: str | None = "0",
    support_angle_unit: str = "°",
    support_angle_subject: str = "surface",
    duplicate_support_angle: bool = False,
    second_surface: bool = False,
    include_rope_entity: bool = False,
    rope_role: str = "cable_custom",
    missing_relation: str | None = None,
    duplicate_relation: str | None = None,
    missing_assumption: str | None = None,
    friction_only_in_text: bool = False,
    pulley_actor: bool = False,
    include_pulley_inertia: bool = False,
    second_pulley: bool = False,
    extra_body: bool = False,
    table_coefficient: str | None = None,
    query_subject: str = "system",
    query_output: str = "acceleration",
    query_component: str = "magnitude",
    query_event: str | None = None,
    collision_id: str | None = None,
    reverse: bool = False,
    swap_masses: bool = False,
    family: str = "independent_table_pulley_fixture",
    case_id: str = "fx_public_dev_0951",
    fake_answer: float | None = None,
) -> PublicCorpusCaseV1:
    if swap_masses:
        mass_a, mass_b = mass_b, mass_a
        mass_a_unit, mass_b_unit = mass_b_unit, mass_a_unit
    mass_a_quote = f"수평대 블록의 질량은 {mass_a} {mass_a_unit}"
    mass_b_quote = f"매달린 추의 질량은 {mass_b} {mass_b_unit}"
    friction_quote = "수평면은 마찰이 없다"
    rope_mass_quote = "줄의 질량을 무시한다"
    rope_length_quote = "줄은 늘어나지 않는다"
    pulley_quote = "도르래의 질량을 무시한다"
    gravity_quote = "중력가속도는 9.81 m/s²로 사용한다"
    text = (
        f"{mass_a_quote}. {mass_b_quote}. "
        f"두 물체는 하나의 줄로 연결되어 고정 도르래를 지난다. "
        f"{friction_quote}. {rope_mass_quote}. {rope_length_quote}. "
        f"{pulley_quote}. {gravity_quote}. 계의 가속도 크기를 구하여라."
    )

    entities = [
        {"role": "system", "kind": "system", "label": "수평대 도르래 계"},
        {"role": "mass_a", "kind": "block", "label": "수평대 블록"},
        {"role": "mass_b", "kind": "block", "label": "매달린 추"},
        {"role": "surface", "kind": surface_kind, "label": "수평면"},
        {"role": "pulley", "kind": "pulley", "label": "고정 도르래"},
    ]
    if include_rope_entity:
        entities.append({"role": rope_role, "kind": "rope", "label": "명시적 줄"})
    if second_pulley:
        entities.append({"role": "pulley_2", "kind": "pulley", "label": "둘째 도르래"})
    if second_surface:
        entities.append({"role": "surface_2", "kind": "surface", "label": "둘째 면"})
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
    ]
    if support_angle is not None:
        support_angle_quote = f"받침면이 수평과 이루는 각은 {support_angle} {support_angle_unit}"
        text += f" {support_angle_quote}."
        facts.append(
            _fact(
                "theta_support",
                "angle",
                support_angle,
                support_angle_unit,
                support_angle_quote,
                support_angle_subject,
            )
        )
        if duplicate_support_angle:
            second_quote = f"같은 면의 각은 다시 {support_angle} {support_angle_unit}"
            text += f" {second_quote}."
            facts.append(
                _fact(
                    "theta_support_2",
                    "angle",
                    support_angle,
                    support_angle_unit,
                    second_quote,
                    support_angle_subject,
                )
            )
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
    if table_coefficient is not None:
        coefficient_quote = f"수평면의 마찰계수는 {table_coefficient}"
        text += f" {coefficient_quote}."
        facts.append(
            _fact(
                "mu",
                "coefficient_of_friction",
                table_coefficient,
                "",
                coefficient_quote,
                "surface",
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
        _relation("table_support", "slides_on", ["mass_a", "surface"]),
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
    if friction_only_in_text:
        # The words stay in the problem text; the typed proposal is gone.
        assumptions = [item for item in assumptions if item["kind"] != "frictionless"]

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
                "motion_model": "unknown",
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
                "subject_role": query_subject,
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


def _projection(case: PublicCorpusCaseV1, *, stated: bool = False, **frame_overrides):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    assert projection.draft is not None
    return _state_orientation(projection, **frame_overrides) if stated else projection


def _run(case: PublicCorpusCaseV1, nonce: str, *, stated: bool = False, **overrides):
    """Run one case.

    ``stated=False`` is the public corpus exactly as it projects — no frames,
    hence no reference axis, hence no closure.  ``stated=True`` is the fully
    authored Draft in which the source did state the support's orientation.
    """

    projection = project_case_to_draft(case)
    if stated and projection.draft is not None:
        projection = _state_orientation(projection, **overrides)
    return run_lane_b_case(
        projection,
        execution_token=deterministic_token(0, run_nonce=nonce),
    )


def _expected(mass_a: float, mass_b: float, gravity: float = 9.81) -> float:
    return mass_b * gravity / (mass_a + mass_b)


def test_projection_scopes_rope_authority_to_the_table_topology() -> None:
    projection = _projection(_case())
    ropes = [
        item for item in projection.draft.entities if item.primitive.value == "rope"
    ]
    assert len(ropes) == 1
    assert ropes[0].evidence_refs
    scoped = {
        (item.kind, item.subject_id)
        for item in projection.draft.assumptions
        if item.assumption_id.startswith("asm_closure_fixed_pulley_")
    }
    assert scoped == {
        ("massless_rope", ropes[0].entity_id),
        ("inextensible_rope", ropes[0].entity_id),
        ("fixed_pulley", "pulley"),
        ("ideal_massless_frictionless_pulley", "pulley"),
    }
    plan = plan_complete_profile(
        ProfileId.table_pulley_two_body,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.complete
    assert plan.structurally_complete


@pytest.mark.parametrize(
    ("mass_a", "mass_b", "expected"),
    (
        ("5", "2", _expected(5.0, 2.0)),
        ("8", "3", _expected(8.0, 3.0)),
        ("4.5", "1.5", _expected(4.5, 1.5)),
    ),
)
def test_table_pulley_acceleration_uses_existing_generic_laws(
    mass_a: str, mass_b: str, expected: float
) -> None:
    result = _run(
        _case(mass_a=mass_a, mass_b=mass_b),
        f"b15-positive-{mass_a}-{mass_b}",
        stated=True,
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(expected, rel=1.0e-12, abs=1.0e-12)
    assert result.candidate_count == result.verified_candidate_count == 1
    assert set(result.applied_law_ids) == EXPECTED_LAWS
    assert {kind for kind, outcome in result.verification_checks if outcome == "passed"} >= {
        "constraint",
        "equation_residual",
        "inequality",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    }


def test_swapped_masses_stay_solved_with_the_swapped_drive() -> None:
    result = _run(_case(swap_masses=True), "b15-swap", stated=True)
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(
        _expected(2.0, 5.0), rel=1.0e-12, abs=1.0e-12
    )


def test_transaction_adds_only_typed_topology_and_value_free_unknowns() -> None:
    projection = _projection(_case(), stated=True)
    pristine = projection.draft.model_dump(mode="json", warnings="none")
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.table_pulley_two_body,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    assert projection.draft.model_dump(mode="json", warnings="none") == pristine
    closed = application.draft
    # The source authored both frames, so neither is a created record.
    assert {item.frame_id for item in closed.reference_frames} == {
        AUTHORED_WORLD_FRAME_ID,
        AUTHORED_SUPPORT_FRAME_ID,
    }
    assert not {
        AUTHORED_WORLD_FRAME_ID,
        AUTHORED_SUPPORT_FRAME_ID,
    } & set(application.created_record_ids)
    assert {
        item.entity_id
        for item in closed.entities
        if item.primitive.value == "environment"
    } == {TABLE_PULLEY_WORLD_ID}
    gravity = next(
        item for item in closed.quantities if item.quantity_id == TABLE_PULLEY_GRAVITY_ID
    )
    assert gravity.provenance is Provenance.server_default
    assert gravity.raw_value == "9.81"
    assert gravity.assumption_policy_ref == "asm_gravity"
    created_quantities = [
        item
        for item in closed.quantities
        if item.quantity_id in application.created_record_ids
        and item.quantity_id != TABLE_PULLEY_GRAVITY_ID
    ]
    assert created_quantities
    assert all(
        item.raw_value is None and item.raw_unit is None for item in created_quantities
    )
    assert closed.queries[0].target.subject_id == "mass_b"
    assert closed.queries[0].target.component.value == "y"
    assert closed.queries[0].target.direction.sign == -1
    assert not closed.constraints


def test_units_explicit_rope_ids_and_source_order_are_not_authority() -> None:
    baseline = _run(_case(), "b15-invariance-base", stated=True)
    equivalent = _run(
        _case(
            mass_a="5000",
            mass_a_unit="g",
            mass_b="2000",
            mass_b_unit="g",
            include_rope_entity=True,
            rope_role="student_named_cable",
            reverse=True,
            family="renamed_table_pulley_family",
            case_id="renamed_case_identity",
            fake_answer=999999.0,
        ),
        "b15-invariance-equivalent",
        stated=True,
    )
    assert baseline.terminal is equivalent.terminal is LaneBTerminal.solved
    assert equivalent.answer_value_si == pytest.approx(
        baseline.answer_value_si, rel=1.0e-12, abs=1.0e-12
    )
    assert equivalent.applied_law_ids == baseline.applied_law_ids


def test_relation_participant_order_is_not_authority() -> None:
    baseline = _run(_case(), "b15-participants-base", stated=True)
    case = _case(case_id="fx_public_dev_0952")
    gold = case.gold.model_dump(mode="json", warnings="none")
    for relation in gold["relations"]:
        relation["participant_roles"] = list(reversed(relation["participant_roles"]))
    permuted = case.model_copy(update={"gold": type(case.gold)(**gold)})
    result = _run(permuted, "b15-participants-permuted", stated=True)
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(
        baseline.answer_value_si, rel=1.0e-12, abs=1.0e-12
    )


def test_incline_shape_is_never_claimed_by_the_table_profile() -> None:
    incline_case = _case(surface_kind="incline", case_id="fx_public_dev_0953")
    projection = project_case_to_draft(incline_case)
    assert projection.terminal is DraftProjectionTerminal.projected
    plan = plan_complete_profile(
        ProfileId.table_pulley_two_body,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert plan.disposition is PlanDisposition.not_applicable


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
        {"friction_only_in_text": True},
        {"surface_kind": "incline", "support_angle": None},
        {"pulley_actor": True},
        {"include_pulley_inertia": True},
        {"second_pulley": True},
        {"extra_body": True},
        {"table_coefficient": "0.2"},
        {"query_subject": "mass_a"},
        {"query_component": "x"},
        {"query_output": "force"},
        {"query_event": "start"},
        {"collision_id": AUTHORED_WORLD_FRAME_ID},
    ),
)
def test_structural_near_misses_fail_closed_without_numeric_output(
    overrides: dict,
) -> None:
    result = _run(_case(**overrides), f"b15-near-miss-{sorted(overrides)}")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_physics_changing_mass_changes_the_verified_answer() -> None:
    first = _run(_case(mass_b="2"), "b15-mass-2", stated=True)
    second = _run(_case(mass_b="3"), "b15-mass-3", stated=True)
    assert first.terminal is second.terminal is LaneBTerminal.solved
    assert first.answer_value_si != pytest.approx(second.answer_value_si)
    assert first.applied_law_ids == second.applied_law_ids


def test_closed_graph_never_uses_incline_projection_laws() -> None:
    result = _run(_case(), "b15-no-incline-laws", stated=True)
    assert result.terminal is LaneBTerminal.solved
    assert not any("incline" in law_id for law_id in result.applied_law_ids)
    assert not any("rolling" in law_id for law_id in result.applied_law_ids)


# --------------------------------------------------------------------------
# The typed horizontal-support authority
#
# `EntityPrimitive.surface` is a *generic* support.  The corpus contract uses
# the same primitive for a banked road, a vertical circular track, and a level
# floor, so the primitive can never stand for "horizontal".  Neither can the
# absence of an incline primitive, the absence of an angle, an entity label, or
# a sentence in the problem text.  The only authority these tests accept is the
# source's own support-angle statement whose value is exactly zero.
# --------------------------------------------------------------------------


def test_typed_support_normal_and_tangent_are_bound_to_the_world_axes() -> None:
    projection = _projection(_case(), stated=True)
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.table_pulley_two_body,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    closed = application.draft
    support = next(
        item
        for item in closed.reference_frames
        if item.frame_id == AUTHORED_SUPPORT_FRAME_ID
    )
    world = next(
        item
        for item in closed.reference_frames
        if item.frame_id == AUTHORED_WORLD_FRAME_ID
    )
    assert support.parent_frame_id == world.frame_id
    assert support.origin.entity_id == "surface"
    assert support.evidence_refs
    bound = {
        item.axis.value: (
            item.direction.frame_id,
            item.direction.axis.value,
            item.direction.sign,
        )
        for item in support.axes
    }
    # The typed statements the whole profile rests on.
    assert bound["normal"] == (world.frame_id, "y", 1)
    assert bound["tangent"] == (world.frame_id, "x", 1)


def test_typed_horizontal_relation_carries_the_stated_zero_angle() -> None:
    projection = _projection(_case(), stated=True)
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.table_pulley_two_body,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    closed = application.draft
    orientation = next(
        item
        for item in closed.geometry
        if item.relation_id == TABLE_PULLEY_ORIENTATION_RELATION_ID
    )
    assert orientation.kind.value == "angle"
    assert set(orientation.participant_ids) == {"surface", TABLE_PULLEY_WORLD_ID}
    assert len(orientation.quantity_ids) == 1
    assert orientation.evidence_refs
    angle = next(
        item
        for item in closed.quantities
        if item.quantity_id == orientation.quantity_ids[0]
    )
    # Source-stated, never generated, and exactly zero.
    assert angle.role.value == "angle"
    assert angle.subject_id == "surface"
    assert angle.provenance is Provenance.explicit_source
    assert float(angle.raw_value) == 0.0
    assert angle.quantity_id not in application.created_record_ids


@pytest.mark.parametrize(
    ("overrides", "why"),
    (
        # `support_angle: None` is no longer here: with the frames stated, the
        # binding *is* the orientation and needs no numeric restatement.  Its
        # two halves are pinned separately below — frames without an angle
        # close, and no frames at all still refuse.
        ({"support_angle": "30"}, "a stated slope is not a horizontal support"),
        ({"support_angle": "90"}, "a vertical support is not a horizontal one"),
        ({"support_angle": "0.0001"}, "nearly zero is not a stated zero"),
        ({"support_angle": "1e-12"}, "a tiny angle is not a stated zero"),
        (
            {"support_angle": "0", "support_angle_subject": "mass_a"},
            "an angle owned by the block says nothing about the support",
        ),
        (
            {"support_angle": "0", "support_angle_subject": "pulley"},
            "an angle owned by the pulley says nothing about the support",
        ),
        ({"duplicate_support_angle": True}, "a duplicated orientation is ambiguous"),
        ({"second_surface": True}, "two supports leave the contact surface unfixed"),
        (
            {"support_angle": "0", "support_angle_unit": ""},
            "an angle with no angular unit states no angle",
        ),
    ),
)
def test_support_orientation_must_be_stated_exactly_once_and_be_zero(
    overrides: dict, why: str
) -> None:
    result = _run(
        _case(**overrides),
        f"b15-orientation-{sorted(overrides)}-{why}",
        stated=True,
    )
    assert result.terminal is not LaneBTerminal.solved, why
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


@pytest.mark.parametrize(
    "label",
    ("수평면", "horizontal table", "책상 위 수평 바닥", "경사면", "vertical wall"),
)
def test_entity_labels_are_never_the_horizontal_authority(label: str) -> None:
    case = _case(support_angle=None, case_id="fx_public_dev_0954")
    gold = case.gold.model_dump(mode="json", warnings="none")
    for entity in gold["entities"]:
        if entity["role"] == "surface":
            entity["label"] = label
    relabelled = case.model_copy(update={"gold": type(case.gold)(**gold)})
    result = _run(relabelled, f"b15-label-{label}")
    # Every label reads the same: none of them is authority.
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


@pytest.mark.parametrize(
    "replacement",
    (
        "물체가 연직인 벽면 위를 움직인다.",
        "물체가 30도 경사면 위를 움직인다.",
        "The block moves on a vertical surface.",
    ),
)
def test_problem_text_is_never_the_horizontal_authority(replacement: str) -> None:
    baseline = _run(_case(), "b15-text-baseline", stated=True)
    assert baseline.terminal is LaneBTerminal.solved
    case = _case(case_id="fx_public_dev_0955")
    # Same typed structure, contradicting prose: the engine reads structure.
    rewritten = case.model_copy(
        update={
            "problem_text": f"{replacement} {case.problem_text}",
            "problem_hash": hashlib.sha256(
                f"{replacement} {case.problem_text}".encode("utf-8")
            ).hexdigest(),
        }
    )
    result = _run(rewritten, f"b15-text-{replacement[:12]}", stated=True)
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(
        baseline.answer_value_si, rel=1.0e-12, abs=1.0e-12
    )


@pytest.mark.parametrize(
    ("unit", "value"),
    (("°", "0"), ("rad", "0"), ("deg", "0.0"), ("°", "-0"), ("rad", "0.000")),
)
def test_a_stated_zero_reads_the_same_in_every_angular_unit(
    unit: str, value: str
) -> None:
    baseline = _run(_case(), "b15-zero-unit-baseline", stated=True)
    result = _run(
        _case(support_angle=value, support_angle_unit=unit),
        f"b15-zero-unit-{unit}-{value}",
        stated=True,
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(
        baseline.answer_value_si, rel=1.0e-12, abs=1.0e-12
    )


def _compiles_to_a_solved_answer(draft, text: str, approved, authority_map) -> bool:
    """Run the product pipeline on one Draft and report whether it answers."""

    from engine.mechanics.compiler import (
        MechanicsCompiler,
        authorize_validated_mechanics_ir,
    )
    from engine.mechanics.normalization import normalize_draft
    from engine.mechanics.validation import validate_draft

    try:
        validation = validate_draft(
            text,
            draft,
            approved_assumption_ids=approved,
            authorized_assumptions=authority_map,
        )
        if not validation.accepted:
            return False
        normalization = normalize_draft(
            text,
            draft,
            approved_assumption_ids=approved,
            authorized_assumptions=authority_map,
        )
        if not normalization.accepted or normalization.ir is None:
            return False
        authorization = authorize_validated_mechanics_ir(normalization.ir)
        compiled = MechanicsCompiler().compile(
            normalization.ir,
            validated_ir_authorization=authorization,
            approved_assumption_ids=approved,
            authorized_assumptions=authority_map,
        )
    except Exception:
        return False
    return bool(getattr(compiled, "graph", None)) and not compiled.issues


def test_a_support_frame_that_is_not_horizontal_fails_closed() -> None:
    """The world axes must be the ones the stated zero angle licenses.

    A support frame that binds its normal to world x, that declares no
    tangent, that declares an ambiguous one, or that is missing altogether is
    not the horizontal support the source stated, and the pipeline must refuse
    it rather than answer.
    """

    projection = _projection(_case(), stated=True)
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.table_pulley_two_body,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    closed = application.draft.model_dump(mode="json", warnings="none")

    def support_frame(payload: dict) -> dict:
        return next(
            item
            for item in payload["reference_frames"]
            if item["frame_id"] == AUTHORED_SUPPORT_FRAME_ID
        )

    swapped_normal = deepcopy(closed)
    for axis in support_frame(swapped_normal)["axes"]:
        if axis["axis"] == "normal":
            axis["direction"]["axis"] = "x"
    missing_tangent = deepcopy(closed)
    support_frame(missing_tangent)["axes"] = [
        axis
        for axis in support_frame(missing_tangent)["axes"]
        if axis["axis"] != "tangent"
    ]
    ambiguous_tangent = deepcopy(closed)
    tangent_axis = next(
        axis
        for axis in support_frame(ambiguous_tangent)["axes"]
        if axis["axis"] == "tangent"
    )
    support_frame(ambiguous_tangent)["axes"].append(deepcopy(tangent_axis))
    no_support_frame = deepcopy(closed)
    no_support_frame["reference_frames"] = [
        item
        for item in no_support_frame["reference_frames"]
        if item["frame_id"] != AUTHORED_SUPPORT_FRAME_ID
    ]

    text = _case().problem_text
    authority_map = bundle.authorization_map()
    approved = bundle.approved_assumption_ids

    # The unmutated closure is what a compiling graph looks like, so the
    # refusals below are about the mutation and nothing else.
    assert _compiles_to_a_solved_answer(
        application.draft, text, approved, authority_map
    )

    for name, payload in (
        ("normal bound to world x", swapped_normal),
        ("no tangent direction", missing_tangent),
        ("ambiguous tangent", ambiguous_tangent),
        ("no support frame at all", no_support_frame),
    ):
        try:
            mutated = type(application.draft)(**payload)
        except Exception:
            # The Draft contract itself rejects the shape: also fail-closed.
            continue
        assert not _compiles_to_a_solved_answer(
            mutated, text, approved, authority_map
        ), name


# ---------------------------------------------------------------------------
# The reference axis a stated zero is measured *from*.
#
# A support-owned angle of zero is a number until something says which line it
# is zero against.  These tests hold the line that the number alone is never
# enough, and that the only thing that ever is, is the source's own frame
# binding.
# ---------------------------------------------------------------------------


def test_a_stated_zero_angle_without_any_reference_stays_closed() -> None:
    """The public corpus shape: an exact zero, and no reference for it.

    This is what every table-pulley case in the public corpus actually
    projects to — the projection emits no reference frames at all — so this
    test is also the standing proof that the profile cannot answer one.
    """

    projection = _projection(_case())
    assert projection.draft.reference_frames == []
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.table_pulley_two_body,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is not ApplicationOutcome.applied

    result = _run(_case(), "b15-zero-without-reference")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


@pytest.mark.parametrize(
    ("overrides", "why"),
    (
        (
            {"tangent_axis": "y", "normal_axis": "x"},
            "a tangent bound to world y states a vertical support, not a level one",
        ),
        (
            {"tangent_sign": -1},
            "a reversed tangent is a different axis binding, not the stated one",
        ),
        (
            {"normal_axis": "x"},
            "a normal bound to world x contradicts the tangent it accompanies",
        ),
        (
            {"origin_entity_id": "mass_a"},
            "a frame anchored on the block states the block's orientation",
        ),
        (
            {"origin_entity_id": "pulley"},
            "a frame anchored on the pulley states nothing about the support",
        ),
        (
            {"parent_frame_id": None},
            "an unparented support frame names no world to be horizontal in",
        ),
        (
            {"evidence": ()},
            "an unevidenced frame is an assertion, not a source statement",
        ),
    ),
)
def test_only_a_world_horizontal_frame_binding_states_the_orientation(
    overrides: dict, why: str
) -> None:
    result = _run(
        _case(), f"b15-reference-{sorted(overrides)}", stated=True, **overrides
    )
    assert result.terminal is not LaneBTerminal.solved, why
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0


def test_a_second_surface_frame_leaves_the_reference_ambiguous() -> None:
    """Two candidate orientations are no orientation.

    A support frame plus a second, differently-bound frame does not say which
    one the angle is measured from, so the closure refuses rather than picking.
    """

    projection = _projection(_case())
    payload = projection.draft.model_dump(mode="json", warnings="none")
    frames = _stated_orientation_frames(evidence=_orientation_evidence(payload))
    duplicate = deepcopy(frames[1])
    duplicate["frame_id"] = "frm_source_table_pulley_support_2"
    for axis in duplicate["axes"]:
        if axis["axis"] == "tangent":
            axis["direction"]["axis"] = "y"
    payload["reference_frames"] = [*frames, duplicate]
    ambiguous = replace(
        projection, draft=MechanicsProblemDraftV1.model_validate(payload)
    )
    bundle = build_lane_b_authority_bundle(ambiguous)
    application = apply_selected_profile(
        ambiguous.draft,
        ProfileId.table_pulley_two_body,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is not ApplicationOutcome.applied


def test_a_stated_angle_must_agree_with_the_stated_reference() -> None:
    """A second statement of one orientation has to say the same thing.

    The frame binding identifies this support's tangent with the world's x axis
    and its normal with the world's y — that is what "level" means here, and it
    is complete on its own.  A source may also state the angle, and when it does
    it must be an evidenced, support-owned, exactly-zero one: a slope, a
    vertical, or a nearly-zero angle beside a horizontal binding is a
    contradiction, not a shape this closure may resolve either way.

    This used to include `support_angle: None` under the heading "both halves
    are required".  It was wrong about the binding: a frame that says the
    tangent *is* world x leaves no angle to state, which is exactly why the
    binding is mandatory everywhere and why demanding the number as well made a
    complete statement unsayable in the public v1 record.  The angle-less case
    is now pinned in both directions by the test below.
    """

    for overrides, why in (
        ({"support_angle": "30"}, "a slope beside a horizontal reference conflicts"),
        ({"support_angle": "90"}, "a vertical support is not a level one"),
        ({"support_angle": "0.0001"}, "nearly zero is not a stated zero"),
    ):
        result = _run(
            _case(**overrides), f"b15-both-halves-{sorted(overrides)}", stated=True
        )
        assert result.terminal is not LaneBTerminal.solved, why
        assert result.answer_value_si is None


def test_the_frame_binding_alone_states_the_orientation_and_nothing_else_does() -> None:
    """The B30 contract, in both directions, in one place.

    *With* the source's own frames and no angle at all, the support's
    orientation is stated and the cohort closes.  *Without* them, the same case
    refuses exactly as the B15 revocation left it — which is the public v1
    shape, and the reason the revocation stands.
    """

    stated = _run(
        _case(support_angle=None), "b15-frames-only-stated", stated=True
    )
    assert stated.terminal is LaneBTerminal.solved
    assert stated.answer_value_si is not None
    assert stated.verified_candidate_count == 1

    frameless = _run(_case(support_angle=None), "b15-frames-only-absent")
    assert frameless.terminal is not LaneBTerminal.solved
    assert frameless.answer_value_si is None
    assert frameless.verified_candidate_count == 0


def test_the_closure_never_creates_the_orientation_it_reads() -> None:
    """No frame is a created record, and removing the source's frames refuses.

    The defect this replaces was a closure that minted a tangent/world-x
    binding out of a bare zero and then read its own output back as evidence.
    """

    projection = _projection(_case(), stated=True)
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.table_pulley_two_body,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.outcome is ApplicationOutcome.applied
    created = set(application.created_record_ids)
    assert not created & {
        item.frame_id for item in application.draft.reference_frames
    }
    # And the frames that survive are byte-identical to the ones authored.
    authored = projection.draft.model_dump(mode="json", warnings="none")
    closed = application.draft.model_dump(mode="json", warnings="none")
    assert closed["reference_frames"] == authored["reference_frames"]
