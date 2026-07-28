"""B7: exact source-typed polar kinematics state closure."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import math

import pytest

from engine.mechanics.contracts import MechanicsProblemDraftV1
from evaluation.phase56_stage7.complete_profile import (
    PlanDisposition,
    ProfileId,
    plan_complete_profile,
)
from evaluation.phase56_stage7.complete_profile_application import (
    POLAR_COORDINATE_ENTITY_ID,
    POLAR_FRAME_ID,
    POLAR_RADIUS_RELATION_ID,
    ApplicationOutcome,
    apply_selected_profile,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
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


POLAR_LAWS = {
    "polar_velocity_radial",
    "polar_velocity_transverse",
    "planar_velocity_magnitude",
    "polar_acceleration_radial",
    "polar_acceleration_transverse",
    "planar_acceleration_magnitude",
    "translational_speed_nonnegative",
    "acceleration_magnitude_nonnegative",
}


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    direction: str,
    *,
    subject: str,
    event: str = "instant",
    segment: str = "motion",
) -> dict:
    return {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": segment,
        "event_role": event,
        "temporal_role": "at_event",
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _case(
    *,
    radius: tuple[str, str] = ("2", "m"),
    radial_rate: tuple[str, str] = ("0.5", "m/s"),
    radial_acceleration: tuple[str, str] = ("-0.2", "m/s^2"),
    omega: tuple[str, str] = ("3", "rad/s"),
    alpha: tuple[str, str] = ("1.5", "rad/s^2"),
    angular_direction: str = "counterclockwise",
    query_output: str = "acceleration",
    query_component: str = "radial",
    subject: str = "moving_point",
    label: str = "점 R",
    family: str = "synthetic_polar_fixture",
    case_id: str = "fx_public_dev_0901",
    reverse: bool = False,
    missing_key: str | None = None,
    duplicate_key: str | None = None,
    mixed_event_key: str | None = None,
    extra_subject: bool = False,
) -> PublicCorpusCaseV1:
    values = {
        "radius": radius,
        "velocity": radial_rate,
        "acceleration": radial_acceleration,
        "angular_velocity": omega,
        "angular_acceleration": alpha,
    }
    roles = {
        "radius": "r",
        "velocity": "rdot",
        "acceleration": "rddot",
        "angular_velocity": "omega",
        "angular_acceleration": "alpha",
    }
    directions = {
        "radius": "radial",
        "velocity": "radial",
        "acceleration": "radial",
        "angular_velocity": angular_direction,
        "angular_acceleration": angular_direction,
    }
    descriptions = {
        "radius": "반지름",
        "velocity": "반지름 변화율",
        "acceleration": "반지름 이계 변화율",
        "angular_velocity": "각속도",
        "angular_acceleration": "각가속도",
    }
    quotes = {
        key: f"{descriptions[key]} {value} {unit}"
        for key, (value, unit) in values.items()
    }
    text = (
        f"{label}의 그 순간 극좌표 상태는 "
        + ", ".join(quotes.values())
        + "이다. 요청한 성분을 구하여라."
    )
    facts = [
        _fact(
            roles[key],
            key,
            values[key][0],
            values[key][1],
            quotes[key],
            directions[key],
            subject=subject,
            event=("later" if key == mixed_event_key else "instant"),
        )
        for key in values
        if key != missing_key
    ]
    if duplicate_key is not None:
        value, unit = values[duplicate_key]
        duplicate_quote = f"검산용 {descriptions[duplicate_key]} {value} {unit}"
        text += f" {duplicate_quote}."
        facts.append(
            _fact(
                f"{roles[duplicate_key]}_duplicate",
                duplicate_key,
                value,
                unit,
                duplicate_quote,
                directions[duplicate_key],
                subject=subject,
            )
        )
    events = [
        {
            "role": "instant",
            "kind": "other",
            "subject_roles": [subject],
            "segment_role": "motion",
            "evidence_quote": "그 순간",
        }
    ]
    if mixed_event_key is not None:
        text += " 조금 뒤의 상태도 별도로 기록되었다."
        events.append(
            {
                "role": "later",
                "kind": "other",
                "subject_roles": [subject],
                "segment_role": "motion",
                "evidence_quote": "조금 뒤",
            }
        )
    entities = [{"role": subject, "kind": "particle", "label": label}]
    actors = [subject]
    if extra_subject:
        entities.append(
            {"role": "other_point", "kind": "particle", "label": "점 S"}
        )
        actors.append("other_point")
        text += " 점 S도 같은 구간에서 움직인다."
    if reverse:
        entities.reverse()
        facts.reverse()
        events.reverse()
    query_event = "instant"
    gold = {
        "parse_status": "complete",
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": "accepted",
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": [
            {
                "role": "motion",
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
        "relations": [],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": query_output,
                "subject_role": subject,
                "segment_role": "motion",
                "component": query_component,
                "event_role": query_event,
            }
        ],
        "answers": [
            {
                "query_role": "q1",
                "numeric": 123.456,
                "unit": "m/s" if query_output == "tangential_velocity" else "m/s^2",
                "tolerance_abs": 0.0001,
                "reference_expression": "independent synthetic fixture",
            }
        ],
        "expected_failure_codes": [],
    }
    record = build_case(
        index=901,
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
    return run_lane_b_case(
        _projection(case),
        execution_token=deterministic_token(0, run_nonce=nonce),
    )


def _si(value: tuple[str, str], role: str) -> float:
    from engine.mechanics.math_ast import DimensionVector
    from engine.mechanics.units import normalize_quantity

    dimensions = {
        "radius": DimensionVector(length=1),
        "velocity": DimensionVector(length=1, time=-1),
        "acceleration": DimensionVector(length=1, time=-2),
        "angular_velocity": DimensionVector(time=-1),
        "angular_acceleration": DimensionVector(time=-2),
    }
    normalized = normalize_quantity(
        value[0], value[1], "scalar", dimensions[role]
    ).value
    assert isinstance(normalized, float)
    return normalized


def _expected(
    *,
    radius: tuple[str, str] = ("2", "m"),
    radial_rate: tuple[str, str] = ("0.5", "m/s"),
    radial_acceleration: tuple[str, str] = ("-0.2", "m/s^2"),
    omega: tuple[str, str] = ("3", "rad/s"),
    alpha: tuple[str, str] = ("1.5", "rad/s^2"),
    direction: str = "counterclockwise",
) -> dict[str, float]:
    r = _si(radius, "radius")
    rdot = _si(radial_rate, "velocity")
    rddot = _si(radial_acceleration, "acceleration")
    sign = -1.0 if direction == "clockwise" else 1.0
    omega_si = sign * _si(omega, "angular_velocity")
    alpha_si = sign * _si(alpha, "angular_acceleration")
    radial_velocity = rdot
    transverse_velocity = r * omega_si
    radial_acceleration_si = rddot - r * omega_si**2
    transverse_acceleration = r * alpha_si + 2.0 * rdot * omega_si
    return {
        "velocity_radial": radial_velocity,
        "velocity_transverse": transverse_velocity,
        "speed": math.hypot(radial_velocity, transverse_velocity),
        "acceleration_radial": radial_acceleration_si,
        "acceleration_transverse": transverse_acceleration,
        "acceleration_magnitude": math.hypot(
            radial_acceleration_si, transverse_acceleration
        ),
    }


@pytest.mark.parametrize(
    ("query_output", "component", "expected_key"),
    (
        ("tangential_velocity", "magnitude", "speed"),
        ("acceleration", "radial", "acceleration_radial"),
        ("acceleration", "magnitude", "acceleration_magnitude"),
    ),
)
def test_positive_velocity_and_acceleration_readouts_use_existing_verified_graph(
    query_output: str, component: str, expected_key: str
) -> None:
    result = _run(
        _case(query_output=query_output, query_component=component),
        f"b7-positive-{expected_key}",
    )
    assert result.terminal is LaneBTerminal.solved
    assert result.answer_value_si == pytest.approx(_expected()[expected_key])
    assert set(result.applied_law_ids) == POLAR_LAWS
    assert result.candidate_count >= 1
    assert result.verified_candidate_count == 1
    assert result.answer_unit == (
        "m/s" if query_output == "tangential_velocity" else "m/s^2"
    )
    checks = dict(result.verification_checks)
    for required in (
        "equation_residual",
        "query_binding",
        "source_evidence",
        "unit_consistency",
    ):
        assert checks[required] == "passed"


def test_transaction_adds_only_typed_topology_and_value_free_unknowns() -> None:
    projection = _projection(_case())
    before = {
        item.quantity_id: (
            item.raw_value,
            item.raw_unit,
            tuple(item.evidence_refs),
        )
        for item in projection.draft.quantities
        if item.raw_value is not None
    }
    plan = plan_complete_profile(
        ProfileId.polar_kinematics_state, projection.draft
    )
    assert plan.disposition is PlanDisposition.complete
    application = apply_selected_profile(
        projection.draft, ProfileId.polar_kinematics_state
    )
    assert application.outcome is ApplicationOutcome.applied
    closed = application.draft
    assert {item.entity_id for item in closed.entities} == {
        "moving_point",
        POLAR_COORDINATE_ENTITY_ID,
    }
    assert len(closed.reference_frames) == 1
    assert closed.reference_frames[0].frame_id == POLAR_FRAME_ID
    assert closed.reference_frames[0].frame_type.value == "radial_transverse"
    assert {item.axis.value for item in closed.reference_frames[0].axes} == {
        "radial",
        "transverse",
    }
    assert not closed.events
    assert closed.motion_intervals[0].start_event_id is None
    assert closed.motion_intervals[0].end_event_id is None
    assert closed.motion_intervals[0].frame_id == POLAR_FRAME_ID
    assert len(closed.geometry) == 1
    assert closed.geometry[0].relation_id == POLAR_RADIUS_RELATION_ID
    assert closed.geometry[0].kind.value == "radius"
    assert not closed.assumptions
    assert not closed.interactions
    assert len(closed.quantities) == 11
    assert sum(item.raw_value is not None for item in closed.quantities) == 5
    assert sum(item.raw_value is None for item in closed.quantities) == 6
    after = {
        item.quantity_id: (
            item.raw_value,
            item.raw_unit,
            tuple(item.evidence_refs),
        )
        for item in closed.quantities
        if item.quantity_id in before
    }
    assert after == before
    assert all(
        item.raw_value is None and item.raw_unit is None
        for item in closed.quantities
        if item.subject_id == "moving_point"
    )


@pytest.mark.slow
def test_clockwise_reverses_signed_transverse_values_but_not_magnitudes() -> None:
    ccw_component = _run(
        _case(angular_direction="counterclockwise", query_component="transverse"),
        "b7-ccw-component",
    )
    cw_component = _run(
        _case(angular_direction="clockwise", query_component="transverse"),
        "b7-cw-component",
    )
    ccw_magnitude = _run(
        _case(angular_direction="counterclockwise", query_component="magnitude"),
        "b7-ccw-magnitude",
    )
    cw_magnitude = _run(
        _case(angular_direction="clockwise", query_component="magnitude"),
        "b7-cw-magnitude",
    )
    assert all(
        item.terminal is LaneBTerminal.solved
        for item in (ccw_component, cw_component, ccw_magnitude, cw_magnitude)
    )
    assert ccw_component.answer_value_si == pytest.approx(
        _expected(direction="counterclockwise")["acceleration_transverse"]
    )
    assert cw_component.answer_value_si == pytest.approx(
        _expected(direction="clockwise")["acceleration_transverse"]
    )
    assert cw_component.answer_value_si == pytest.approx(
        -ccw_component.answer_value_si
    )
    assert cw_magnitude.answer_value_si == pytest.approx(
        ccw_magnitude.answer_value_si
    )


@pytest.mark.slow
def test_different_numbers_and_units_reuse_the_same_law_graph() -> None:
    baseline = _run(
        _case(query_component="magnitude"), "b7-units-baseline"
    )
    converted_values = {
        "radius": ("200", "cm"),
        "radial_rate": ("1.8", "km/h"),
        "radial_acceleration": ("-0.2", "m/s^2"),
        "omega": ("0.5", "rad/s"),
        "alpha": ("1.5", "rad/s^2"),
    }
    converted = _run(
        _case(query_component="magnitude", **converted_values),
        "b7-units-converted",
    )
    assert baseline.terminal is converted.terminal is LaneBTerminal.solved
    assert set(baseline.applied_law_ids) == set(converted.applied_law_ids) == POLAR_LAWS
    assert converted.answer_value_si == pytest.approx(
        _expected(**converted_values)["acceleration_magnitude"],
        rel=1.0e-9,
    )


@pytest.mark.slow
def test_entity_names_ids_and_source_array_order_are_not_authority() -> None:
    baseline = _run(_case(), "b7-identity-baseline")
    changed = _run(
        _case(
            subject="renamed_dot",
            label="재명명된 점",
            family="unrelated_metadata",
            case_id="fx_public_dev_1901",
            reverse=True,
        ),
        "b7-identity-changed",
    )
    assert baseline.terminal is changed.terminal is LaneBTerminal.solved
    assert changed.answer_value_si == pytest.approx(baseline.answer_value_si)
    assert changed.applied_law_ids == baseline.applied_law_ids


@pytest.mark.slow
def test_projected_quantity_symbol_evidence_and_event_order_are_invariant() -> None:
    projection = _projection(_case())
    payload = projection.draft.model_dump(mode="json")
    for field in ("source_evidence", "events", "symbols", "quantities"):
        payload[field].reverse()
    reordered_projection = replace(
        projection,
        draft=MechanicsProblemDraftV1.model_validate(payload),
    )
    baseline = run_lane_b_case(
        projection,
        execution_token=deterministic_token(0, run_nonce="b7-order-base"),
    )
    reordered = run_lane_b_case(
        reordered_projection,
        execution_token=deterministic_token(0, run_nonce="b7-order-reversed"),
    )
    assert baseline.terminal is reordered.terminal is LaneBTerminal.solved
    assert reordered.answer_value_si == pytest.approx(baseline.answer_value_si)
    assert reordered.applied_law_ids == baseline.applied_law_ids


@pytest.mark.parametrize(
    "missing_key",
    (
        "radius",
        "velocity",
        "acceleration",
        "angular_velocity",
        "angular_acceleration",
    ),
)
def test_missing_required_source_state_never_closes(missing_key: str) -> None:
    result = _run(
        _case(missing_key=missing_key),
        f"b7-missing-{missing_key}",
    )
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_duplicate_role_is_ambiguous_and_never_closes() -> None:
    projection = project_case_to_draft(
        _case(duplicate_key="angular_velocity")
    )
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.draft is None


def test_quantities_from_different_instants_never_close() -> None:
    result = _run(
        _case(mixed_event_key="angular_acceleration"),
        "b7-mixed-instants",
    )
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def _mutated_draft(mutator) -> MechanicsProblemDraftV1:
    payload = _projection(_case()).draft.model_dump(mode="json")
    mutator(payload)
    return MechanicsProblemDraftV1.model_validate(payload)


def _assert_not_applied(draft: MechanicsProblemDraftV1) -> None:
    application = apply_selected_profile(
        draft, ProfileId.polar_kinematics_state
    )
    assert application.outcome is not ApplicationOutcome.applied
    assert application.draft == draft


def test_wrapper_with_source_evidence_is_preserved_fail_closed() -> None:
    def mutate(payload):
        start_id = payload["motion_intervals"][0]["start_event_id"]
        start = next(item for item in payload["events"] if item["event_id"] == start_id)
        start["evidence_refs"] = [payload["source_evidence"][0]["evidence_id"]]

    _assert_not_applied(_mutated_draft(mutate))


def test_query_at_a_different_instant_is_not_normalized() -> None:
    def mutate(payload):
        start_id = payload["motion_intervals"][0]["start_event_id"]
        payload["queries"][0]["target"]["event_id"] = start_id
        target_id = payload["queries"][0]["target"]["target_quantity_id"]
        next(
            item for item in payload["quantities"]
            if item["quantity_id"] == target_id
        )["event_id"] = start_id

    _assert_not_applied(_mutated_draft(mutate))


def test_duration_query_is_not_a_polar_component_query() -> None:
    result = _run(
        _case(query_output="time", query_component="magnitude"),
        "b7-duration-query",
    )
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_preexisting_other_frame_refuses_adapter_authority() -> None:
    def mutate(payload):
        payload["reference_frames"] = [
            {
                "frame_id": "authoredFrame",
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    {
                        "axis": axis,
                        "direction": {
                            "kind": "axis",
                            "frame_id": "authoredFrame",
                            "axis": axis,
                            "sign": 1,
                        },
                    }
                    for axis in ("x", "y")
                ],
                "parent_frame_id": None,
                "translating_with_entity_id": None,
                "rotating_about_point_id": None,
                "generalized_coordinate_symbol_ids": [],
                "evidence_refs": [],
            }
        ]

    _assert_not_applied(_mutated_draft(mutate))


def test_generated_id_collision_rejects_the_whole_transaction() -> None:
    def mutate(payload):
        payload["source_assets"] = [
            {
                "asset_id": POLAR_FRAME_ID,
                "kind": "document",
                "content_sha256": "0" * 64,
                "media_type": "text/plain",
                "page_id": None,
                "page_number": None,
                "parent_asset_id": None,
            }
        ]

    draft = _mutated_draft(mutate)
    plan = plan_complete_profile(ProfileId.polar_kinematics_state, draft)
    assert plan.disposition is PlanDisposition.complete
    _assert_not_applied(draft)


def test_more_than_one_moving_subject_refuses_the_exact_profile() -> None:
    result = _run(_case(extra_subject=True), "b7-extra-subject")
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_quantities_from_another_motion_interval_never_mix() -> None:
    def mutate(payload):
        original = payload["motion_intervals"][0]
        payload["motion_intervals"].append(
            {
                **deepcopy(original),
                "interval_id": "otherMotion",
                "order": 2,
                "start_event_id": None,
                "end_event_id": None,
            }
        )
        next(
            item for item in payload["quantities"]
            if item["role"] == "angular_acceleration"
        )["interval_id"] = "otherMotion"

    _assert_not_applied(_mutated_draft(mutate))


@pytest.mark.parametrize(
    ("omega_direction", "alpha_direction"),
    (
        ("unspecified", "unspecified"),
        ("clockwise", "counterclockwise"),
    ),
)
def test_insufficient_or_conflicting_direction_authority_refuses(
    omega_direction: str, alpha_direction: str
) -> None:
    def mutate(payload):
        for item in payload["quantities"]:
            if item["role"] == "angular_velocity":
                item["component"] = omega_direction
                item["direction"] = {
                    "kind": "semantic",
                    "direction": omega_direction,
                }
            elif item["role"] == "angular_acceleration":
                item["component"] = alpha_direction
                item["direction"] = {
                    "kind": "semantic",
                    "direction": alpha_direction,
                }

    _assert_not_applied(_mutated_draft(mutate))


def test_magnitude_query_cannot_be_restyled_as_a_signed_speed_component() -> None:
    projection = _projection(
        _case(query_output="tangential_velocity", query_component="magnitude")
    )
    payload = projection.draft.model_dump(mode="json")
    payload["queries"][0]["target"]["component"] = "radial"
    payload["queries"][0]["target"]["role"] = "speed"
    target_id = payload["queries"][0]["target"]["target_quantity_id"]
    quantity = next(
        item for item in payload["quantities"]
        if item["quantity_id"] == target_id
    )
    quantity["component"] = "radial"
    quantity["role"] = "speed"
    _assert_not_applied(MechanicsProblemDraftV1.model_validate(payload))


def test_general_curved_motion_without_full_polar_state_stays_closed() -> None:
    result = _run(
        _case(
            missing_key="angular_acceleration",
            query_output="tangential_velocity",
            query_component="transverse",
        ),
        "b7-generic-curved-near-miss",
    )
    assert result.terminal is not LaneBTerminal.solved
    assert result.answer_value_si is None


def test_irrelevant_transaction_authority_does_not_change_the_closed_draft() -> None:
    draft = _projection(_case()).draft
    baseline = apply_selected_profile(draft, ProfileId.polar_kinematics_state)
    with_irrelevant_authority = apply_selected_profile(
        draft,
        ProfileId.polar_kinematics_state,
        approved_assumption_ids=("unrelated_authority",),
    )
    assert baseline.outcome is with_irrelevant_authority.outcome is ApplicationOutcome.applied
    assert baseline.draft == with_irrelevant_authority.draft


@pytest.mark.slow
def test_irrelevant_value_free_source_assumption_does_not_change_the_answer() -> None:
    projection = _projection(_case())
    payload = projection.draft.model_dump(mode="json")
    evidence_id = next(
        item["evidence_refs"][0]
        for item in payload["quantities"]
        if item["role"] == "radius"
    )
    payload["assumptions"] = [
        {
            "assumption_id": "asm_unrelated_note",
            "kind": "unrelated_note",
            "subject_id": "moving_point",
            "interval_id": "motion",
            "disposition": "rejected",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "typed but irrelevant value-free source note",
            "evidence_refs": [evidence_id],
        }
    ]
    changed_projection = replace(
        projection,
        draft=MechanicsProblemDraftV1.model_validate(payload),
    )
    baseline = run_lane_b_case(
        projection,
        execution_token=deterministic_token(
            0, run_nonce="b7-no-assumption"
        ),
    )
    changed = run_lane_b_case(
        changed_projection,
        execution_token=deterministic_token(
            0, run_nonce="b7-irrelevant-assumption"
        ),
    )
    assert baseline.terminal is changed.terminal is LaneBTerminal.solved
    assert changed.answer_value_si == pytest.approx(baseline.answer_value_si)
    assert changed.applied_law_ids == baseline.applied_law_ids


@pytest.mark.slow
def test_gold_expected_answer_tampering_cannot_change_runtime() -> None:
    case = _case()
    payload = case.model_dump(mode="json")
    payload["gold"]["answers"][0]["numeric"] = -987654.321
    payload["gold"]["answers"][0]["reference_expression"] = "tampered"
    changed = PublicCorpusCaseV1.model_validate(payload)
    baseline = _run(case, "b7-gold-baseline")
    tampered = _run(changed, "b7-gold-tampered")
    assert baseline.terminal is tampered.terminal is LaneBTerminal.solved
    assert tampered.answer_value_si == pytest.approx(baseline.answer_value_si)


@pytest.mark.slow
def test_case_family_and_order_metadata_cannot_change_runtime() -> None:
    baseline = _run(_case(), "b7-metadata-baseline")
    changed = _run(
        _case(
            family="opposite_unrelated_family",
            case_id="fx_public_dev_2901",
            reverse=True,
        ),
        "b7-metadata-changed",
    )
    assert baseline.terminal is changed.terminal is LaneBTerminal.solved
    assert changed.answer_value_si == pytest.approx(baseline.answer_value_si)


@pytest.mark.slow
def test_physics_changing_input_changes_the_verified_answer_correctly() -> None:
    changed_values = {
        "radius": ("3.5", "m"),
        "radial_rate": ("-0.75", "m/s"),
        "radial_acceleration": ("0.4", "m/s^2"),
        "omega": ("1.25", "rad/s"),
        "alpha": ("-0.6", "rad/s^2"),
    }
    baseline = _run(
        _case(query_component="magnitude"), "b7-physics-baseline"
    )
    changed = _run(
        _case(query_component="magnitude", **changed_values),
        "b7-physics-changed",
    )
    assert baseline.terminal is changed.terminal is LaneBTerminal.solved
    assert changed.answer_value_si != pytest.approx(baseline.answer_value_si)
    assert changed.answer_value_si == pytest.approx(
        _expected(**changed_values)["acceleration_magnitude"]
    )


@pytest.mark.parametrize("mutation", ("provenance", "evidence"))
def test_malformed_provenance_or_evidence_free_source_fact_is_rejected(
    mutation: str,
) -> None:
    def mutate(payload):
        source = next(
            item for item in payload["quantities"] if item["role"] == "radius"
        )
        if mutation == "provenance":
            source["provenance"] = "inferred"
        else:
            source["evidence_refs"] = []

    _assert_not_applied(_mutated_draft(mutate))
