"""Free flight under gravity: one whole transaction, spending issued authority.

The transaction creates together the pieces that only work together — the
world frame, the vertical binding, the gravity interaction, the server-valued
gravity magnitude, and the unknown vertical acceleration — and the gravity
value is admitted only as the exact immutable authorization the Lane B
authority stage issued for the Draft's own approved ``constant_gravity``
assumption.

The negative controls come first in spirit and in count: everything that is
not exactly this shape — no authorization, a forged or mismatched one, an
authority about another subject or no interval, duplicate authorities, gravity
structure already present, a horizontal stated axis, colliding IDs — must
leave the Draft byte-for-byte untouched.  The engine's own two-key wall is
then held from both sides: the closed Draft passes with the exact map and is
refused without it or with a tampered one.

Every fixture is independently authored.  None is derived from a corpus case,
and none reads a case ID, family, split, expected terminal, or expected
answer at any point in the pipeline under test.
"""

from __future__ import annotations

import hashlib

import pytest

from engine.mechanics.compiler import (
    MechanicsCompiler,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.compiler import compiler as compiler_module
from engine.mechanics.laws.core import apply_core_laws
from engine.mechanics.normalization import normalize_draft
from engine.mechanics.validation import AssumptionAuthorization, validate_draft

from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_every_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    GRAVITY_INTERACTION_ID,
    GRAVITY_QUANTITY_ID,
    VERTICAL_ACCELERATION_QUANTITY_ID,
    WORLD_FRAME_ID,
    TransactionAuthority,
    _free_flight_gravity_transaction,
    close_projected_draft,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_authority import (
    build_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjection,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)
from support.phase56_stage7_corpus_fixtures import build_case

PROBLEM_TEXT = (
    "연습 상황: 돌을 지면 위에서 위로 던진다. 처음 속력은 9 m/s 이고 "
    "처음 높이는 2 m 이다. 공기 저항은 무시한다. 돌이 최고점에 "
    "도달할 때까지 걸리는 시간을 구하시오."
)


def _free_flight_record() -> dict:
    record = build_case(
        index=7,
        split="public_dev",
        family="single_particle_newton",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = PROBLEM_TEXT
    record["problem_hash"] = hashlib.sha256(
        PROBLEM_TEXT.encode("utf-8")
    ).hexdigest()
    gold = record["gold"]
    gold["entities"] = [
        {"role": "stone", "kind": "particle", "label": "돌"},
        {"role": "ground", "kind": "surface", "label": "지면"},
    ]
    gold["motion_segments"] = [
        {
            "role": "fall",
            "order": 1,
            "actor_roles": ["stone"],
            "motion_model": "projectile_free_flight",
            "relevance": "target",
            "start_event_role": "go",
            "end_event_role": "top",
        }
    ]
    gold["events"] = [
        {
            "role": "go",
            "kind": "release",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        },
        {
            "role": "top",
            "kind": "highest_point",
            "subject_roles": ["stone"],
            "segment_role": "fall",
            "evidence_quote": None,
        },
    ]
    gold["explicit_facts"] = [
        {
            "role": "v0",
            "semantic_key": "initial_velocity",
            "raw_value": "9",
            "raw_unit": "m/s",
            "evidence_quote": "처음 속력은 9 m/s",
            "subject_role": "stone",
            "segment_role": "fall",
            "event_role": "go",
            "temporal_role": "initial",
            "direction": "upward",
            "relevance": "solver_input",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        },
        {
            "role": "h0",
            "semantic_key": "height",
            "raw_value": "2",
            "raw_unit": "m",
            "evidence_quote": "처음 높이는 2 m",
            "subject_role": "stone",
            "segment_role": "fall",
            "event_role": "go",
            "temporal_role": "initial",
            "direction": "upward",
            "relevance": "solver_input",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        },
    ]
    gold["relations"] = []
    gold["assumption_proposals"] = [
        {
            "role": "air",
            "kind": "no_air_resistance",
            "subject_role": "stone",
            "segment_role": "fall",
            "supporting_quote": "공기 저항은 무시한다",
            "server_value_only": True,
        },
        {
            "role": "grav",
            "kind": "constant_gravity",
            "subject_role": "stone",
            "segment_role": "fall",
            "supporting_quote": None,
            "server_value_only": True,
        },
    ]
    gold["queries"] = [
        {
            "role": "q1",
            "output_key": "time",
            "subject_role": "stone",
            "segment_role": "fall",
            "component": "magnitude",
            "event_role": "top",
        }
    ]
    gold["answers"] = [
        {
            "query_role": "q1",
            "numeric": 0.9174,
            "unit": "s",
            "tolerance_abs": 0.01,
            "reference_expression": "v0/g",
        }
    ]
    return record


def _projection() -> DraftProjection:
    projection = project_case_to_draft(
        PublicCorpusCaseV1(**_free_flight_record())
    )
    assert projection.projected
    return projection


def _closed(projection: DraftProjection):
    bundle = build_lane_b_authority_bundle(projection)
    return bundle, close_projected_draft(
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )


def _payload_and_authority(projection: DraftProjection):
    bundle = build_lane_b_authority_bundle(projection)
    payload = projection.draft.model_dump(mode="json", warnings="none")
    authority = TransactionAuthority(
        approved_assumption_ids=frozenset(bundle.approved_assumption_ids),
        authorized_assumptions=bundle.authorization_map(),
    )
    return payload, authority


# --------------------------------------------------------------------------
# Negative controls: anything not exactly this shape leaves the Draft alone
# --------------------------------------------------------------------------


def test_without_any_authorization_the_draft_is_left_untouched():
    """The fail-closed default: no authority, no closure, no change."""

    projection = _projection()
    result = close_projected_draft(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert not result.applied
    assert result.draft is projection.draft


def test_a_forged_authorization_value_is_refused_by_the_transaction_itself():
    """Closure consumes authority; it never mints or launders one.

    A forged map whose authorization carries a value the Draft's own approved
    assumption does not state is refused before any record is built — and the
    validator and compiler would each refuse it again.
    """

    projection = _projection()
    payload, authority = _payload_and_authority(projection)
    (key, genuine), = tuple(authority.authorized_assumptions.items())
    forged = TransactionAuthority(
        approved_assumption_ids=authority.approved_assumption_ids,
        authorized_assumptions={
            key: AssumptionAuthorization(
                assumption_id=genuine.assumption_id,
                subject_id=genuine.subject_id,
                role=genuine.role,
                raw_value="10",
                raw_unit=genuine.raw_unit,
                interval_id=genuine.interval_id,
            )
        },
    )
    assert _free_flight_gravity_transaction(payload, forged) is None


def test_an_authority_about_another_subject_licenses_nothing():
    projection = _projection()
    payload, authority = _payload_and_authority(projection)
    (key, genuine), = tuple(authority.authorized_assumptions.items())
    other_subject = TransactionAuthority(
        approved_assumption_ids=authority.approved_assumption_ids,
        authorized_assumptions={
            key: AssumptionAuthorization(
                assumption_id=genuine.assumption_id,
                subject_id="ground",
                role=genuine.role,
                raw_value=genuine.raw_value,
                raw_unit=genuine.raw_unit,
                interval_id=genuine.interval_id,
            )
        },
    )
    assert _free_flight_gravity_transaction(payload, other_subject) is None


def test_an_interval_free_authority_names_no_flight():
    projection = _projection()
    payload, authority = _payload_and_authority(projection)
    (key, genuine), = tuple(authority.authorized_assumptions.items())
    unscoped = TransactionAuthority(
        approved_assumption_ids=authority.approved_assumption_ids,
        authorized_assumptions={
            key: AssumptionAuthorization(
                assumption_id=genuine.assumption_id,
                subject_id=genuine.subject_id,
                role=genuine.role,
                raw_value=genuine.raw_value,
                raw_unit=genuine.raw_unit,
                interval_id=None,
            )
        },
    )
    assert _free_flight_gravity_transaction(payload, unscoped) is None


def test_duplicate_gravity_authorities_refuse_the_whole_transaction():
    projection = _projection()
    payload, authority = _payload_and_authority(projection)
    duplicate = dict(payload["assumptions"][0])
    for item in payload["assumptions"]:
        if item["kind"] == "constant_gravity":
            duplicate = dict(item)
    duplicate["assumption_id"] = "asm_grav_second"
    payload["assumptions"] = [*payload["assumptions"], duplicate]
    widened = TransactionAuthority(
        approved_assumption_ids=(
            authority.approved_assumption_ids | {"asm_grav_second"}
        ),
        authorized_assumptions=authority.authorized_assumptions,
    )
    assert _free_flight_gravity_transaction(payload, widened) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["quantities"].append(
            {
                **payload["quantities"][0],
                "quantity_id": "qty_prior_gravity",
                "symbol_id": None,
                "role": "gravity",
            }
        ),
        lambda payload: payload["interactions"].append(
            {
                "interaction_id": "rel_prior_gravity",
                "kind": "gravity",
                "participant_ids": ["stone"],
                "point_ids": [],
                "frame_id": None,
                "interval_id": "fall",
                "event_id": None,
                "quantity_ids": [],
                "evidence_refs": [],
            }
        ),
        lambda payload: payload["quantities"].append(
            {
                **payload["quantities"][0],
                "quantity_id": "qty_prior_accel",
                "symbol_id": None,
                "role": "acceleration",
                "subject_id": "stone",
                "interval_id": "fall",
            }
        ),
    ],
    ids=["existing_gravity_quantity", "existing_gravity_interaction", "existing_acceleration"],
)
def test_existing_gravity_or_acceleration_structure_is_not_this_shape(mutate):
    projection = _projection()
    payload, authority = _payload_and_authority(projection)
    mutate(payload)
    assert _free_flight_gravity_transaction(payload, authority) is None


def test_a_stated_horizontal_axis_is_not_closable_without_decomposition():
    projection = _projection()
    payload, authority = _payload_and_authority(projection)
    for quantity in payload["quantities"]:
        if quantity.get("direction", {}) and quantity["direction"].get("kind") == "semantic":
            quantity["direction"] = {"kind": "semantic", "direction": "left"}
    assert _free_flight_gravity_transaction(payload, authority) is None


def test_an_id_collision_abandons_the_transaction():
    projection = _projection()
    payload, authority = _payload_and_authority(projection)
    payload["quantities"].append(
        {
            **payload["quantities"][0],
            "quantity_id": GRAVITY_QUANTITY_ID,
            "symbol_id": None,
            "role": "length",
        }
    )
    assert _free_flight_gravity_transaction(payload, authority) is None


# --------------------------------------------------------------------------
# The positive control: one whole closure, exactly the issued authority
# --------------------------------------------------------------------------


def test_the_profile_closes_as_one_transaction_with_the_exact_authority():
    projection = _projection()
    bundle, result = _closed(projection)
    assert result.applied
    assert result.profile_id is ProfileId.free_flight_gravity
    closed = result.draft

    frames = {item.frame_id for item in closed.reference_frames}
    assert WORLD_FRAME_ID in frames

    (interaction,) = [
        item
        for item in closed.interactions
        if item.interaction_id == GRAVITY_INTERACTION_ID
    ]
    assert str(getattr(interaction.kind, "value", interaction.kind)) == "gravity"
    assert list(interaction.participant_ids) == ["stone"]
    assert interaction.interval_id == "fall"
    assert interaction.frame_id == WORLD_FRAME_ID
    assert set(interaction.quantity_ids) == {
        GRAVITY_QUANTITY_ID,
        VERTICAL_ACCELERATION_QUANTITY_ID,
    }

    (gravity,) = [
        item
        for item in closed.quantities
        if item.quantity_id == GRAVITY_QUANTITY_ID
    ]
    authorization = bundle.authorization_map()[gravity.assumption_policy_ref]
    assert str(getattr(gravity.provenance, "value", gravity.provenance)) == (
        "server_default"
    )
    assert gravity.raw_value == authorization.raw_value == "9.81"
    assert gravity.raw_unit == authorization.raw_unit == "m/s^2"
    assert gravity.subject_id == authorization.subject_id == "stone"
    assert gravity.interval_id == authorization.interval_id == "fall"
    assert gravity.event_id is None

    (acceleration,) = [
        item
        for item in closed.quantities
        if item.quantity_id == VERTICAL_ACCELERATION_QUANTITY_ID
    ]
    assert str(
        getattr(acceleration.provenance, "value", acceleration.provenance)
    ) == "unknown"
    assert acceleration.raw_value is None
    assert str(
        getattr(acceleration.component, "value", acceleration.component)
    ) == "y"
    assert acceleration.frame_id == WORLD_FRAME_ID
    assert acceleration.interval_id == "fall"

    # The stated upward velocity is the same direction, written on the axis it
    # already named; the height and the question are untouched.
    (v0,) = [item for item in closed.quantities if item.quantity_id == "qty_v0"]
    assert v0.direction is not None
    assert v0.quantity_id in result.rebound_quantity_ids
    (height,) = [
        item for item in closed.quantities if item.quantity_id == "qty_h0"
    ]
    assert str(getattr(height.component, "value", height.component)) != "y" or (
        height.frame_id is None
    )
    query = closed.queries[0]
    assert str(
        getattr(query.target.component, "value", query.target.component)
    ) == "magnitude"


def test_the_closed_draft_passes_the_two_key_wall_and_emits_the_gravity_law():
    projection = _projection()
    bundle, result = _closed(projection)
    assert result.applied
    closed = result.draft

    accepted = validate_draft(
        projection.problem_text,
        closed,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert accepted.accepted

    normalization = normalize_draft(
        projection.problem_text,
        closed,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert normalization.accepted and normalization.ir is not None
    ir = normalization.ir

    compiled = MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    codes = {str(getattr(item.code, "value", item.code)) for item in compiled.issues}
    assert "invalid_binding" not in codes

    query = ir.queries[0]
    query_quantity, _ = compiler_module._query_quantity(ir, query)
    source_symbols, _ = compiler_module._validate_reciprocal_bindings(ir)
    records = compiler_module._primary_records(ir, query)
    _, edges = compiler_module._graph_edges(records)
    relevant, _ = compiler_module._relevant_ids(
        query, edges, MechanicsCompiler()._limits
    )
    context, _, _, _ = compiler_module._build_law_context(
        ir,
        query,
        query_quantity,
        relevant,
        source_symbols,
        frozenset(bundle.approved_assumption_ids),
    )
    law_ids = {emission.rule.law_id for emission in apply_core_laws(context)}
    assert "uniform_gravity_acceleration" in law_ids


def test_the_engine_walls_hold_without_or_against_the_map():
    """The same closed Draft is refused without the map, or with a tampered one."""

    projection = _projection()
    bundle, result = _closed(projection)
    closed = result.draft

    bare = validate_draft(
        projection.problem_text,
        closed,
        approved_assumption_ids=bundle.approved_assumption_ids,
    )
    codes = {str(getattr(item.code, "value", item.code)) for item in bare.issues}
    assert "provenance_violation" in codes

    (key, genuine), = tuple(bundle.authorization_map().items())
    tampered = {
        key: AssumptionAuthorization(
            assumption_id=genuine.assumption_id,
            subject_id=genuine.subject_id,
            role=genuine.role,
            raw_value="9.8",
            raw_unit=genuine.raw_unit,
            interval_id=genuine.interval_id,
        )
    }
    wrong = validate_draft(
        projection.problem_text,
        closed,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=tampered,
    )
    codes = {str(getattr(item.code, "value", item.code)) for item in wrong.issues}
    assert "provenance_violation" in codes


def test_the_full_lane_reaches_a_typed_underdetermined_not_an_answer():
    """End to end through the runner: closure, both walls, and an honest wall.

    The profile completes the structure gravity needs, and the remaining gap —
    the boundary the question's event names, which the source states no value
    for — keeps the graph underdetermined.  The lane must say exactly that:
    no invented answer, no invalid_binding, no stage exception.
    """

    projection = _projection()
    result = run_lane_b_case(projection, execution_token=deterministic_token(0))
    assert result.terminal is LaneBTerminal.compiler_failure
    assert result.compiler_status == "underdetermined"
    assert "invalid_binding" not in result.compiler_codes
    assert result.stage_exception is None
    assert result.answer_value_si is None
    assert result.candidate_count == 0


def test_the_free_flight_plan_still_gates_the_transaction():
    """A Draft whose plan is not complete never reaches the transaction."""

    projection = _projection()
    plans = plan_every_profile(
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    (free_plan,) = [
        plan
        for plan in plans
        if plan.profile_id is ProfileId.free_flight_gravity
    ]
    assert free_plan.disposition is PlanDisposition.complete

    # Withhold the constant_acceleration authority the plan requires: the plan
    # is no longer complete, and closure applies nothing.
    reduced = tuple(
        item
        for item in projection.approvable_assumption_ids
        if "constant_acceleration" not in item
    )
    plans = plan_every_profile(projection.draft, approved_assumption_ids=reduced)
    (free_plan,) = [
        plan
        for plan in plans
        if plan.profile_id is ProfileId.free_flight_gravity
    ]
    assert free_plan.disposition is not PlanDisposition.complete
