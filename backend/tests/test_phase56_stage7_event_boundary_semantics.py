"""Typed event boundary semantics: the source's own event kinds, preserved.

A corpus that types an event ``highest_point`` has stated physics: at a smooth
trajectory's vertical position extremum the **vertical velocity component** is
zero — not the speed, not the horizontal component.  ``turnaround`` states the
signed velocity along the *one proven motion axis* is zero.  ``comes_to_rest``
states the velocity magnitude at that event is zero, for that subject at that
event only.

Three walls hold those statements exact:

* the projection preserves the typed source event kind instead of collapsing
  it to a generic ``reaches_condition``;
* the evaluator's event-boundary derivation creates the boundary unknown the
  law will write about — transactionally, with the full-Draft ID collision
  domain, and only where the law's own conditions provably hold; and
* the engine law emits the zero **from the typed event kind**, never from raw
  problem text, an expected answer, or a case identity.

Negative controls outnumber positive ones on purpose: a wrongly-zeroed speed
at an apex is exactly the confident-wrong-solve hazard Stage 7 forbids.

Every fixture is independently authored.  None is derived from a corpus case,
and none reads a case ID, family, split, expected terminal, or expected answer
anywhere in the paths under test.
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from engine.mechanics.contracts import EventKind
from engine.mechanics.laws.core import apply_core_laws

from evaluation.phase56_stage7.complete_profile_application import (
    WORLD_FRAME_ID,
    close_projected_draft,
)
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.event_boundary_derivation import (
    EVENT_BOUNDARY_DERIVATION_VERSION,
    EventBoundaryOutcome,
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
    "연습 상황: 돌을 지면 위에서 위로 던진다. 처음 속력은 9 m/s 이고 "
    "처음 높이는 2 m 이다. 공기 저항은 무시한다. 돌이 최고점에 "
    "도달할 때까지 걸리는 시간을 구하시오."
)


def _record(*, top_kind: str = "highest_point", **gold_overrides) -> dict:
    record = build_case(
        index=11,
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
            "kind": top_kind,
            "subject_roles": ["stone"],
            "segment_role": "fall",
            # A licensing kind carries its own source authority: the quote
            # resolves to the unique `최고점에 도달` span of the problem text.
            "evidence_quote": "최고점에 도달",
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
    gold.update(gold_overrides)
    return record


def _projection(**kwargs) -> DraftProjection:
    projection = project_case_to_draft(PublicCorpusCaseV1(**_record(**kwargs)))
    assert projection.projected, projection.sanitized_reason
    return projection


def _closed_draft(projection: DraftProjection):
    bundle = build_lane_b_authority_bundle(projection)
    result = close_projected_draft(
        projection.draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert result.applied
    return bundle, result.draft


def _law_context(projection: DraftProjection, draft):
    """The compiler's own law context for one Draft, with the issued authority.

    The same construction the free-flight closure suite uses: normalize with
    the bundle's immutable map, then assemble the context through the
    compiler's own steps, so the emissions measured here are the runtime's.
    """

    from engine.mechanics.compiler import MechanicsCompiler
    from engine.mechanics.compiler import compiler as compiler_module
    from engine.mechanics.normalization import normalize_draft

    bundle = build_lane_b_authority_bundle(projection)
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
    return context


def _law_ids(projection: DraftProjection, draft) -> set[str]:
    return {
        emission.rule.law_id
        for emission in apply_core_laws(_law_context(projection, draft))
    }


def _emissions(projection: DraftProjection, draft):
    return apply_core_laws(_law_context(projection, draft))


# --------------------------------------------------------------------------
# The projection preserves the typed source event kind
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("corpus_kind", "draft_kind"),
    [
        ("highest_point", EventKind.highest_point),
        ("lowest_point", EventKind.lowest_point),
        ("turnaround", EventKind.turnaround),
        ("comes_to_rest", EventKind.comes_to_rest),
        ("reaches_height", EventKind.reaches_condition),
        ("reaches_position", EventKind.reaches_condition),
    ],
)
def test_typed_source_event_kinds_survive_projection(corpus_kind, draft_kind):
    projection = _projection(top_kind=corpus_kind)
    (top,) = [item for item in projection.draft.events if item.event_id == "top"]
    assert top.kind is draft_kind


def test_problem_text_keywords_contribute_nothing():
    """The words `최고점` in the text carry no authority; only the typed kind does."""

    projection = _projection(top_kind="reaches_height")
    # The problem text still says 최고점; the typed event kind does not.
    assert "최고점" in projection.problem_text
    (top,) = [item for item in projection.draft.events if item.event_id == "top"]
    assert top.kind is EventKind.reaches_condition
    _, closed = _closed_draft(projection)
    derivation = derive_event_boundaries(closed)
    assert derivation.outcome is EventBoundaryOutcome.not_applied
    assert derivation.draft is closed


# --------------------------------------------------------------------------
# Derivation: the boundary unknown is created transactionally, or not at all
# --------------------------------------------------------------------------


def test_the_apex_boundary_unknown_is_created_exactly_once():
    projection = _projection()
    _, closed = _closed_draft(projection)
    derivation = derive_event_boundaries(closed)
    assert derivation.outcome is EventBoundaryOutcome.applied
    assert derivation.version == EVENT_BOUNDARY_DERIVATION_VERSION
    (created_id,) = derivation.created_quantity_ids
    (created,) = [
        item
        for item in derivation.draft.quantities
        if item.quantity_id == created_id
    ]
    assert str(getattr(created.role, "value", created.role)) == "velocity"
    assert created.subject_id == "stone"
    assert created.interval_id == "fall"
    assert created.event_id == "top"
    assert str(getattr(created.component, "value", created.component)) == "y"
    assert created.frame_id == WORLD_FRAME_ID
    assert str(getattr(created.provenance, "value", created.provenance)) == (
        "unknown"
    )
    assert created.raw_value is None and created.raw_unit is None

    # Deterministic: the same Draft derives the same package.
    again = derive_event_boundaries(closed)
    assert again.created_quantity_ids == derivation.created_quantity_ids
    assert again.draft.model_dump_json() == derivation.draft.model_dump_json()


def test_derivation_without_closure_structure_creates_nothing():
    """No gravity interaction, no proven vertical — the projected Draft alone."""

    projection = _projection()
    derivation = derive_event_boundaries(projection.draft)
    assert derivation.outcome is EventBoundaryOutcome.not_applied
    assert derivation.draft is projection.draft
    assert derivation.created_quantity_ids == ()


def test_an_existing_boundary_quantity_is_never_duplicated():
    projection = _projection()
    _, closed = _closed_draft(projection)
    first = derive_event_boundaries(closed)
    assert first.outcome is EventBoundaryOutcome.applied
    second = derive_event_boundaries(first.draft)
    assert second.outcome is EventBoundaryOutcome.not_applied
    assert second.draft is first.draft


def test_an_id_collision_in_any_namespace_aborts_the_whole_package():
    projection = _projection()
    _, closed = _closed_draft(projection)
    expected = derive_event_boundaries(closed)
    (created_id,) = expected.created_quantity_ids
    colliding = closed.model_copy(
        update={
            "entities": [
                *closed.entities,
                closed.entities[0].model_copy(update={"entity_id": created_id}),
            ]
        }
    )
    derivation = derive_event_boundaries(colliding)
    assert derivation.outcome is EventBoundaryOutcome.rejected
    assert derivation.created_quantity_ids == ()
    assert derivation.draft is colliding
    assert derivation.draft.model_dump_json() == colliding.model_dump_json()


def test_a_segment_internal_event_is_never_promoted_to_a_boundary():
    """An extremum event the source never declared as a boundary stays inert."""

    projection = _projection()
    _, closed = _closed_draft(projection)
    internal_event = closed.events[0].model_copy(
        update={
            "event_id": "mid",
            "kind": "highest_point",
            "interval_ids": [],
        }
    )
    boundary_events_replaced = closed.model_copy(
        update={
            "events": [
                item.model_copy(update={"kind": "reaches_condition"})
                if item.event_id == "top"
                else item
                for item in closed.events
            ]
            + [internal_event]
        }
    )
    derivation = derive_event_boundaries(boundary_events_replaced)
    assert derivation.outcome is EventBoundaryOutcome.not_applied
    assert derivation.created_quantity_ids == ()


def test_another_subjects_event_licenses_nothing_for_this_subject():
    projection = _projection()
    _, closed = _closed_draft(projection)
    other_subject_event = closed.model_copy(
        update={
            "events": [
                item.model_copy(update={"subject_ids": ["ground"]})
                if item.event_id == "top"
                else item
                for item in closed.events
            ]
        }
    )
    derivation = derive_event_boundaries(other_subject_event)
    assert derivation.outcome is EventBoundaryOutcome.not_applied


def test_a_collision_bearing_subject_fails_closed():
    """A bouncing body's `lowest_point` is an impact, not a smooth extremum."""

    projection = _projection()
    _, closed = _closed_draft(projection)
    with_collision = closed.model_copy(
        update={
            "interactions": [
                *closed.interactions,
                closed.interactions[0].model_copy(
                    update={
                        "interaction_id": "rel_bounce",
                        "kind": "collision",
                        "participant_ids": ["stone", "ground"],
                        "quantity_ids": [],
                    }
                ),
            ]
        }
    )
    derivation = derive_event_boundaries(with_collision)
    assert derivation.outcome is EventBoundaryOutcome.not_applied


# --------------------------------------------------------------------------
# Law emissions: the zero is component-exact and scope-exact
# --------------------------------------------------------------------------


def _derived(projection: DraftProjection):
    _, closed = _closed_draft(projection)
    derivation = derive_event_boundaries(closed)
    assert derivation.outcome is EventBoundaryOutcome.applied
    return derivation


@pytest.mark.parametrize("top_kind", ["highest_point", "lowest_point"])
def test_a_vertical_extremum_pins_the_vertical_component_only(top_kind):
    projection = _projection(top_kind=top_kind)
    derivation = _derived(projection)
    emissions = _emissions(projection, derivation.draft)
    pinned = [
        item
        for item in emissions
        if item.rule.law_id == "event_vertical_extremum_velocity"
    ]
    assert len(pinned) == 1
    (created_id,) = derivation.created_quantity_ids
    assert pinned[0].source_quantity_ids == (created_id,)
    assert pinned[0].event_id == "top"
    # The whole speed is never zeroed: no state_at_rest emission appears, and
    # the created quantity is the only one any extremum equation writes about.
    assert all(item.rule.law_id != "state_at_rest" for item in emissions)


def test_the_stated_initial_velocity_is_never_zeroed():
    projection = _projection()
    derivation = _derived(projection)
    emissions = _emissions(projection, derivation.draft)
    for item in emissions:
        if item.rule.law_id == "event_vertical_extremum_velocity":
            assert "qty_v0" not in item.source_quantity_ids


def test_an_unrelated_reaches_condition_emits_no_zero():
    projection = _projection(top_kind="reaches_height")
    _, closed = _closed_draft(projection)
    derivation = derive_event_boundaries(closed)
    assert derivation.outcome is EventBoundaryOutcome.not_applied
    law_ids = _law_ids(projection, closed)
    assert "event_vertical_extremum_velocity" not in law_ids
    assert "event_turnaround_axis_velocity" not in law_ids
    assert "event_comes_to_rest_velocity" not in law_ids


def test_a_turnaround_pins_the_single_proven_axis():
    projection = _projection(top_kind="turnaround")
    derivation = _derived(projection)
    (created_id,) = derivation.created_quantity_ids
    (created,) = [
        item
        for item in derivation.draft.quantities
        if item.quantity_id == created_id
    ]
    assert str(getattr(created.component, "value", created.component)) == "y"
    emissions = _emissions(projection, derivation.draft)
    pinned = [
        item
        for item in emissions
        if item.rule.law_id == "event_turnaround_axis_velocity"
    ]
    assert len(pinned) == 1
    assert pinned[0].source_quantity_ids == (created_id,)


def test_a_comes_to_rest_event_pins_the_magnitude_and_the_proven_axis():
    """`|v| = 0` pins the magnitude, and — as a theorem — the one proven axis.

    The subject's own stated directions bind exactly one signed axis (`y` in
    the closed world frame), so the rest instant carries two boundary
    unknowns: the magnitude and that axis component, each pinned to zero at
    exactly this event.  Nothing propagates to the other event.
    """

    projection = _projection(top_kind="comes_to_rest")
    derivation = _derived(projection)
    created = {
        item.quantity_id: item
        for item in derivation.draft.quantities
        if item.quantity_id in derivation.created_quantity_ids
    }
    components = {
        str(getattr(item.component, "value", item.component))
        for item in created.values()
    }
    assert components == {"magnitude", "y"}
    assert all(item.event_id == "top" for item in created.values())
    emissions = _emissions(projection, derivation.draft)
    pinned = [
        item
        for item in emissions
        if item.rule.law_id == "event_comes_to_rest_velocity"
    ]
    assert len(pinned) == 2
    assert {
        quantity_id
        for item in pinned
        for quantity_id in item.source_quantity_ids
    } == set(created)
    for item in pinned:
        assert item.event_id == "top"


def test_multiple_candidate_boundary_quantities_emit_nothing():
    """Two matching candidates at one event are an ambiguity, not a choice."""

    projection = _projection()
    derivation = _derived(projection)
    (created_id,) = derivation.created_quantity_ids
    (created,) = [
        item
        for item in derivation.draft.quantities
        if item.quantity_id == created_id
    ]
    (created_symbol,) = [
        item
        for item in derivation.draft.symbols
        if item.quantity_id == created_id
    ]
    duplicated = derivation.draft.model_copy(
        update={
            "quantities": [
                *derivation.draft.quantities,
                created.model_copy(
                    update={
                        "quantity_id": "qty_evb_twin",
                        "symbol_id": "sym_evb_twin",
                    }
                ),
            ],
            "symbols": [
                *derivation.draft.symbols,
                created_symbol.model_copy(
                    update={
                        "symbol_id": "sym_evb_twin",
                        "quantity_id": "qty_evb_twin",
                    }
                ),
            ],
        }
    )
    emissions = _emissions(projection, duplicated)
    assert all(
        item.rule.law_id != "event_vertical_extremum_velocity"
        for item in emissions
    )


def test_event_and_quantity_order_do_not_change_the_emissions():
    projection = _projection()
    derivation = _derived(projection)
    reordered = derivation.draft.model_copy(
        update={
            "events": list(reversed(derivation.draft.events)),
            "quantities": list(reversed(derivation.draft.quantities)),
        }
    )
    original_ids = {
        item.rule.law_id for item in _emissions(projection, derivation.draft)
    }
    reordered_ids = {
        item.rule.law_id for item in _emissions(projection, reordered)
    }
    assert original_ids == reordered_ids
    assert "event_vertical_extremum_velocity" in original_ids


def test_gold_metadata_contributes_nothing_to_the_derivation():
    """The same structure under other case labels derives identically."""

    first = _record()
    second = _record()
    second["case_id"] = "fx_other_event_identity"
    second["family"] = "totally_different_family"
    second["tags"] = ["other"]
    second["gold"]["answers"] = []
    first_projection = project_case_to_draft(PublicCorpusCaseV1(**first))
    second_projection = project_case_to_draft(PublicCorpusCaseV1(**second))
    _, first_closed = _closed_draft(first_projection)
    _, second_closed = _closed_draft(second_projection)
    first_derived = derive_event_boundaries(first_closed)
    second_derived = derive_event_boundaries(second_closed)
    assert first_derived.created_quantity_ids == (
        second_derived.created_quantity_ids
    )
    assert first_derived.draft.model_dump_json() == (
        second_derived.draft.model_dump_json()
    )


# --------------------------------------------------------------------------
# The full lane: the boundary law lands, and nothing overclaims
# --------------------------------------------------------------------------


def test_the_full_lane_carries_the_boundary_law_and_stays_honest():
    """The reachable free-flight shape gains its boundary equation.

    The typed law emits on the real compiled path (asserted through the
    compiler's own law-context construction above); the runner's terminal
    stays a typed engine outcome with no stage exception, and nothing is
    solved by a wrong route.  Whether the graph then closes is the compiler's
    and solver's own verdict — this test pins the honesty of the path, not a
    predicted unlock.
    """

    projection = _projection()
    result = run_lane_b_case(projection, execution_token="0" * 32)
    assert result.terminal in {
        LaneBTerminal.compiler_failure,
        LaneBTerminal.solve_rejected,
        LaneBTerminal.solved,
    }
    assert result.stage_exception is None
    # The derived boundary unknown reached the compiled pipeline: the typed
    # law wrote its equation into the emission set the compiler measured.
    derivation = _derived(projection)
    law_ids = _law_ids(projection, derivation.draft)
    assert "event_vertical_extremum_velocity" in law_ids


def test_the_production_path_does_not_import_the_derivation_module():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for base in ("engine", "app"):
        for path in (root / base).rglob("*.py"):
            if "event_boundary_derivation" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []
