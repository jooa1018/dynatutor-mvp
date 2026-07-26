"""The magnitude-with-angle launch: audited, refused, and pinned refused.

The causal audit of the remaining free-flight blocker measured, on the real
public corpus, that the launch context's angle quantity carries **no typed
reference axis**: component `unspecified`, no direction, no frame, no
geometry relation referencing it, no principle hint — and the corpus's own
closed vocabulary has no construct that could state one (the semantic key is
the bare `angle`; no relation kind names an axis or a horizontal).  Whether
`theta` is measured from the horizontal or the vertical is therefore not
provable from source structure, and §5's rule is absolute: do not build
`v_x = v·cos(theta)` / `v_y = v·sin(theta)` on an unproven reference.

The verdict is `CORPUS_CONTRACT_MISMATCH`, recorded in
`docs/PHASE56_STAGE7_STRUCTURAL_BLOCKERS.md`.  No decomposition rule was
implemented.  These controls pin the refused state: the engine must emit no
component decomposition from a bare magnitude-with-angle pair, under the
original shape or any of the attack variants — so a future rule cannot land
without deliberately revisiting this audit and its tests.

Fixtures are independently authored; nothing reads a case ID, family, split,
expected terminal, or expected answer.
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from engine.mechanics.laws.core import apply_core_laws

from evaluation.phase56_stage7.complete_profile_application import (
    close_projected_draft,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.event_boundary_derivation import (
    derive_event_boundaries,
)
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
    run_lane_b_case,
)
from support.phase56_stage7_corpus_fixtures import build_case

PROBLEM_TEXT = (
    "연습 상황: 공을 지면에서 30 ° 방향으로 12 m/s 로 던진다. "
    "공기 저항은 무시한다. 공이 도달하는 최고 높이를 구하시오."
)

# Laws that would constitute a decomposition of a magnitude-with-angle launch
# into signed components.  None exists today; the assertion below keeps the
# absence load-bearing instead of accidental.
_DECOMPOSITION_LAW_MARKERS = ("decomposition", "cos", "sin", "component_projection")


def _record(**gold_overrides) -> dict:
    record = build_case(
        index=13,
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
        {"role": "ball", "kind": "particle", "label": "공"},
        {"role": "ground", "kind": "surface", "label": "지면"},
    ]
    gold["motion_segments"] = [
        {
            "role": "flight",
            "order": 1,
            "actor_roles": ["ball"],
            "motion_model": "projectile_free_flight",
            "relevance": "target",
            "start_event_role": "go",
            "end_event_role": "land",
        }
    ]
    gold["events"] = [
        {
            "role": "go",
            "kind": "release",
            "subject_roles": ["ball"],
            "segment_role": "flight",
            "evidence_quote": None,
        },
        {
            "role": "apex",
            "kind": "highest_point",
            "subject_roles": ["ball"],
            "segment_role": "flight",
            "evidence_quote": None,
        },
        {
            "role": "land",
            "kind": "finish",
            "subject_roles": ["ball"],
            "segment_role": "flight",
            "evidence_quote": None,
        },
    ]
    gold["explicit_facts"] = [
        {
            "role": "v0",
            "semantic_key": "initial_velocity",
            "raw_value": "12",
            "raw_unit": "m/s",
            "evidence_quote": "12 m/s",
            "subject_role": "ball",
            "segment_role": "flight",
            "event_role": "go",
            "temporal_role": "initial",
            "direction": "not_applicable",
            "relevance": "solver_input",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        },
        {
            "role": "theta",
            "semantic_key": "angle",
            "raw_value": "30",
            "raw_unit": "°",
            "evidence_quote": "30 °",
            "subject_role": "ball",
            "segment_role": "flight",
            "event_role": "go",
            "temporal_role": "initial",
            "direction": "not_applicable",
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
            "subject_role": "ball",
            "segment_role": "flight",
            "supporting_quote": "공기 저항은 무시한다",
            "server_value_only": True,
        },
        {
            "role": "grav",
            "kind": "constant_gravity",
            "subject_role": "ball",
            "segment_role": "flight",
            "supporting_quote": None,
            "server_value_only": True,
        },
    ]
    gold["queries"] = [
        {
            "role": "q1",
            "output_key": "max_height",
            "subject_role": "ball",
            "segment_role": "flight",
            "component": "magnitude",
            "event_role": "apex",
        }
    ]
    gold["answers"] = [
        {
            "query_role": "q1",
            "numeric": 1.835,
            "unit": "m",
            "tolerance_abs": 0.01,
            "reference_expression": "(v0*sin(30 deg))^2/(2*g)",
        }
    ]
    gold.update(gold_overrides)
    return record


def _projection(**kwargs) -> DraftProjection:
    projection = project_case_to_draft(PublicCorpusCaseV1(**_record(**kwargs)))
    assert projection.projected, projection.sanitized_reason
    return projection


def _final_draft(projection: DraftProjection):
    bundle = build_lane_b_authority_bundle(projection)
    closed = close_projected_draft(
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    ).draft
    return bundle, derive_event_boundaries(closed).draft


def _law_ids(projection: DraftProjection) -> set[str]:
    from engine.mechanics.compiler import MechanicsCompiler
    from engine.mechanics.compiler import compiler as compiler_module
    from engine.mechanics.normalization import normalize_draft

    bundle, draft = _final_draft(projection)
    normalization = normalize_draft(
        projection.problem_text,
        draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert normalization.accepted and normalization.ir is not None
    ir = normalization.ir
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
    assert context is not None
    return {emission.rule.law_id for emission in apply_core_laws(context)}


# --------------------------------------------------------------------------
# The audit's structural facts, held by the fixture that mirrors the context
# --------------------------------------------------------------------------


def test_the_angle_carries_no_typed_reference_axis():
    projection = _projection()
    _, draft = _final_draft(projection)
    (angle,) = [
        item
        for item in draft.quantities
        if str(getattr(item.role, "value", item.role)) == "angle"
    ]
    assert str(getattr(angle.component, "value", angle.component)) == (
        "unspecified"
    )
    assert angle.direction is None
    assert angle.frame_id is None
    assert all(
        angle.quantity_id not in relation.quantity_ids
        for relation in draft.geometry
    )


def test_the_engine_catalog_carries_no_decomposition_law():
    """The absence of a decomposition rule is deliberate, not accidental."""

    from engine.mechanics.laws.core import CORE_LAW_CATALOG  # type: ignore[attr-defined]

    for rule in CORE_LAW_CATALOG:
        assert not any(
            marker in rule.law_id for marker in _DECOMPOSITION_LAW_MARKERS
        ), rule.law_id


# --------------------------------------------------------------------------
# Attacks: no variant of the unproven shape produces a component equation
# --------------------------------------------------------------------------


def _no_component_velocity_emitted(projection: DraftProjection) -> None:
    law_ids = _law_ids(projection)
    # The gravity law may emit (its structure is proven); nothing may write a
    # signed component of the stated launch speed.
    assert "event_vertical_extremum_velocity" not in law_ids
    assert not any(
        any(marker in law_id for marker in _DECOMPOSITION_LAW_MARKERS)
        for law_id in law_ids
    )


def test_the_original_shape_emits_no_decomposition():
    _no_component_velocity_emitted(_projection())


def test_two_angles_fail_closed_before_any_law_runs():
    """Two competing angles at one physical identity never reach the engine.

    The projection's canonical-symbol collision veto refuses the Draft
    outright — two different source facts can never be silently fused into
    one graph unknown, so no decomposition (or anything else) can pick one.
    """

    extra = {
        "role": "phi",
        "semantic_key": "angle",
        "raw_value": "45",
        "raw_unit": "°",
        "evidence_quote": "45 °",
        "subject_role": "ball",
        "segment_role": "flight",
        "event_role": "go",
        "temporal_role": "initial",
        "direction": "not_applicable",
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }
    record = _record()
    record["problem_text"] = PROBLEM_TEXT + " 45 ° 기울기."
    record["problem_hash"] = hashlib.sha256(
        record["problem_text"].encode("utf-8")
    ).hexdigest()
    record["gold"]["explicit_facts"] = [
        *record["gold"]["explicit_facts"],
        extra,
    ]
    projection = project_case_to_draft(PublicCorpusCaseV1(**record))
    assert not projection.projected
    assert projection.sanitized_reason == "duplicate_canonical_symbol"


def test_an_angle_for_another_subject_changes_nothing():
    projection = _projection()
    draft = projection.draft
    tampered = draft.model_copy(
        update={
            "quantities": [
                item.model_copy(update={"subject_id": "ground"})
                if str(getattr(item.role, "value", item.role)) == "angle"
                else item
                for item in draft.quantities
            ]
        }
    )
    _no_component_velocity_emitted(
        dataclasses.replace(projection, draft=tampered)
    )


def test_removing_or_changing_the_expected_answer_changes_nothing():
    with_answer = _projection()
    without = _record()
    without["gold"]["answers"] = []
    tampered = _record()
    tampered["gold"]["answers"][0]["numeric"] = 99.9
    results = []
    for record in (without, tampered):
        projection = project_case_to_draft(PublicCorpusCaseV1(**record))
        assert projection.projected
        results.append(projection.draft.model_dump_json())
    assert results[0] == results[1] == with_answer.draft.model_dump_json()
    _no_component_velocity_emitted(with_answer)


def test_the_full_lane_stays_a_typed_blocked_terminal_with_no_exception():
    projection = _projection()
    result = run_lane_b_case(projection, execution_token="1" * 32)
    assert result.terminal in {
        LaneBTerminal.compiler_failure,
        LaneBTerminal.compiler_unsupported,
        LaneBTerminal.needs_confirmation,
    }
    assert result.stage_exception is None
    assert result.answer_value_si is None


def test_negative_magnitudes_stay_impossible_by_contract():
    """A magnitude question is never rewritten and no sign is ever invented.

    The projected magnitude quantity keeps its directionless component through
    closure and derivation; nothing anywhere restamps it onto an axis.
    """

    projection = _projection()
    _, draft = _final_draft(projection)
    (speed,) = [
        item
        for item in draft.quantities
        if str(getattr(item.role, "value", item.role)) == "velocity"
        and item.raw_value is not None
    ]
    assert str(getattr(speed.component, "value", speed.component)) == (
        "magnitude"
    )
    assert speed.direction is None
    assert speed.frame_id is None
