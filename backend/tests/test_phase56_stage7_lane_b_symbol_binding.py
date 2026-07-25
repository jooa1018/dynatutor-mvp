"""Stage 7 Lane B: typed symbol/quantity reciprocal binding invariants.

Every projected quantity owns exactly one `SymbolDefinition`, the binding is
reciprocal in both directions, and the query target owns a *separate* unknown
symbol.  The symbol identity is the quantity's canonical physical identity —
role, subject, point, frame, interval, event, component, direction, shape, and
dimension — so:

* two quantities that describe different physical things get different symbols,
* two that describe the same physical thing collide and fail closed,
* renaming or reordering corpus records leaves the binding structurally
  identical, and
* no value, answer, family, or expected terminal ever reaches a symbol.
"""

from __future__ import annotations

import pytest

from engine.mechanics.validation import validate_draft
from evaluation.phase56_stage7.corpus_records import (
    CorpusAssumptionV1,
    PublicCorpusCaseV1,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionReason,
    DraftProjectionTerminal,
    project_case_to_draft,
)
from support.phase56_stage7_corpus_fixtures import build_case


def _case(**overrides) -> PublicCorpusCaseV1:
    record = build_case(
        index=3,
        split="public_dev",
        family="single_particle_newton",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record.update(overrides)
    return PublicCorpusCaseV1(**record)


def _with_gold(case: PublicCorpusCaseV1, **gold_updates) -> PublicCorpusCaseV1:
    return case.model_copy(update={"gold": case.gold.model_copy(update=gold_updates)})


def _projected(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


def _symbol_map(draft) -> dict[str, object]:
    return {symbol.symbol_id: symbol for symbol in draft.symbols}


# --------------------------------------------------------------------------
# 1. Every known quantity owns one canonical symbol
# --------------------------------------------------------------------------


def test_every_quantity_has_a_reciprocal_symbol() -> None:
    draft = _projected(_case()).draft
    symbols = _symbol_map(draft)
    assert len(symbols) == len(draft.symbols) == len(draft.quantities)
    for quantity in draft.quantities:
        assert quantity.symbol_id is not None
        symbol = symbols[quantity.symbol_id]
        assert symbol.quantity_id == quantity.quantity_id
        assert symbol.dimension == quantity.dimension
        assert symbol.shape.value == quantity.shape.value


def test_symbol_binding_is_one_to_one_in_both_directions() -> None:
    draft = _projected(_case()).draft
    quantity_ids = [symbol.quantity_id for symbol in draft.symbols]
    symbol_ids = [quantity.symbol_id for quantity in draft.quantities]
    assert len(set(quantity_ids)) == len(quantity_ids)
    assert len(set(symbol_ids)) == len(symbol_ids)
    assert set(quantity_ids) == {item.quantity_id for item in draft.quantities}
    assert set(symbol_ids) == {item.symbol_id for item in draft.symbols}


def test_known_symbols_carry_the_source_grounded_value() -> None:
    draft = _projected(_case()).draft
    known = [item for item in draft.quantities if item.raw_value is not None]
    assert known
    for quantity in known:
        assert quantity.provenance.value == "explicit_source"
        assert quantity.symbol_id is not None


# --------------------------------------------------------------------------
# 2. The query owns a separate unknown symbol
# --------------------------------------------------------------------------


def test_query_target_binds_an_unknown_quantity_and_symbol() -> None:
    projection = _projected(_case())
    draft = projection.draft
    query = draft.queries[0]
    target_id = query.target.target_quantity_id
    assert target_id is not None
    unknown = next(
        item for item in draft.quantities if item.quantity_id == target_id
    )
    assert unknown.raw_value is None and unknown.raw_unit is None
    assert unknown.provenance.value == "unknown"
    assert unknown.symbol_id in projection.unknown_symbol_ids


def test_unknown_symbol_is_disjoint_from_every_known_symbol() -> None:
    projection = _projected(_case())
    assert projection.known_symbol_ids
    assert projection.unknown_symbol_ids
    assert not set(projection.known_symbol_ids) & set(projection.unknown_symbol_ids)
    known_quantity_ids = {
        item.quantity_id
        for item in projection.draft.quantities
        if item.raw_value is not None
    }
    unknown_quantity_ids = {
        symbol.quantity_id
        for symbol in projection.draft.symbols
        if symbol.symbol_id in projection.unknown_symbol_ids
    }
    assert not known_quantity_ids & unknown_quantity_ids


def test_unknown_quantity_preserves_the_full_query_identity() -> None:
    projection = _projected(_case())
    draft = projection.draft
    query = draft.queries[0]
    unknown = next(
        item
        for item in draft.quantities
        if item.quantity_id == query.target.target_quantity_id
    )
    assert unknown.role is query.target.role
    assert unknown.subject_id == query.target.subject_id
    assert unknown.interval_id == query.target.interval_id
    assert unknown.event_id == query.target.event_id
    assert unknown.component is query.target.component
    assert unknown.dimension == query.output_dimension
    assert unknown.shape is query.shape


def test_projected_draft_with_symbols_is_accepted_by_validate_draft() -> None:
    projection = _projected(_case())
    result = validate_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert result.accepted, [issue.code.value for issue in result.issues]


# --------------------------------------------------------------------------
# 3. Identity preservation: different physics, different symbol
# --------------------------------------------------------------------------


def _symbol_of(projection, quantity_id: str) -> str:
    return next(
        item.symbol_id
        for item in projection.draft.quantities
        if item.quantity_id == quantity_id
    )


def test_a_different_subject_gets_a_different_symbol() -> None:
    case = _case()
    baseline = _symbol_of(_projected(case), "qty_mass")
    moved = _with_gold(
        case,
        explicit_facts=(
            case.gold.explicit_facts[0].model_copy(update={"subject_role": "surface"}),
        )
        + case.gold.explicit_facts[1:],
    )
    assert _symbol_of(_projected(moved), "qty_mass") != baseline


def test_a_different_interval_gets_a_different_symbol() -> None:
    case = _case()
    baseline = _symbol_of(_projected(case), "qty_mass")
    timeless = _with_gold(
        case,
        explicit_facts=(
            case.gold.explicit_facts[0].model_copy(update={"segment_role": None}),
        )
        + case.gold.explicit_facts[1:],
    )
    assert _symbol_of(_projected(timeless), "qty_mass") != baseline


def test_a_different_event_gets_a_different_symbol() -> None:
    case = _case()
    baseline = _symbol_of(_projected(case), "qty_mass")
    at_event = _with_gold(
        case,
        explicit_facts=(
            case.gold.explicit_facts[0].model_copy(update={"event_role": "start"}),
        )
        + case.gold.explicit_facts[1:],
    )
    assert _symbol_of(_projected(at_event), "qty_mass") != baseline


def test_a_different_direction_gets_a_different_symbol() -> None:
    case = _case()
    left = _with_gold(
        case,
        explicit_facts=(case.gold.explicit_facts[0],)
        + (case.gold.explicit_facts[1].model_copy(update={"direction": "left"}),),
    )
    right = _with_gold(
        case,
        explicit_facts=(case.gold.explicit_facts[0],)
        + (case.gold.explicit_facts[1].model_copy(update={"direction": "right"}),),
    )
    assert _symbol_of(_projected(left), "qty_acceleration") != _symbol_of(
        _projected(right), "qty_acceleration"
    )


def test_a_different_query_component_gets_a_different_unknown_symbol() -> None:
    case = _case()
    baseline = _projected(case).unknown_symbol_ids
    rotated = _with_gold(
        case,
        queries=(case.gold.queries[0].model_copy(update={"component": "x"}),),
    )
    assert _projected(rotated).unknown_symbol_ids != baseline


def test_a_different_query_subject_gets_a_different_unknown_symbol() -> None:
    case = _case()
    baseline = _projected(case).unknown_symbol_ids
    moved = _with_gold(
        case,
        queries=(case.gold.queries[0].model_copy(update={"subject_role": "surface"}),),
    )
    assert _projected(moved).unknown_symbol_ids != baseline


# --------------------------------------------------------------------------
# 4. Collision rejection
# --------------------------------------------------------------------------


def test_two_facts_with_the_same_physical_identity_are_rejected() -> None:
    case = _case()
    twin = case.gold.explicit_facts[0].model_copy(update={"role": "mass_again"})
    collided = _with_gold(
        case, explicit_facts=case.gold.explicit_facts + (twin,)
    )
    projection = project_case_to_draft(collided)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.duplicate_canonical_symbol.value
    )


def test_a_query_that_restates_a_known_fact_is_rejected_not_reused() -> None:
    case = _case()
    # Ask for exactly the acceleration the source already states, at the same
    # scope: the unknown symbol would collide with a known one.
    restated = _with_gold(
        case,
        explicit_facts=(
            case.gold.explicit_facts[0],
            case.gold.explicit_facts[1].model_copy(update={"direction": None}),
        ),
        queries=(
            case.gold.queries[0].model_copy(
                update={"output_key": "acceleration", "component": "unspecified"}
            ),
        ),
    )
    projection = project_case_to_draft(restated)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert projection.sanitized_reason == (
        DraftProjectionReason.unknown_symbol_collides_with_known.value
    )


# --------------------------------------------------------------------------
# 5. Rename / order invariance
# --------------------------------------------------------------------------


def _binding_shape(projection) -> set[tuple[object, ...]]:
    """Structure of the binding with corpus IDs and symbol digests removed."""

    symbols = _symbol_map(projection.draft)
    return {
        (
            item.role.value,
            item.component.value,
            item.interval_id is not None,
            item.event_id is not None,
            item.raw_value,
            item.raw_unit,
            item.provenance.value,
            symbols[item.symbol_id].shape.value,
            tuple(sorted(symbols[item.symbol_id].dimension.model_dump().items())),
        )
        for item in projection.draft.quantities
    }


def test_reordering_facts_leaves_the_binding_structurally_identical() -> None:
    case = _case()
    reordered = _with_gold(
        case, explicit_facts=tuple(reversed(case.gold.explicit_facts))
    )
    assert _binding_shape(_projected(reordered)) == _binding_shape(_projected(case))


def test_reordering_entities_leaves_the_binding_structurally_identical() -> None:
    case = _case()
    reordered = _with_gold(case, entities=tuple(reversed(case.gold.entities)))
    assert _binding_shape(_projected(reordered)) == _binding_shape(_projected(case))


def test_renaming_a_fact_role_leaves_the_binding_structurally_identical() -> None:
    case = _case()
    renamed = _with_gold(
        case,
        explicit_facts=(
            case.gold.explicit_facts[0].model_copy(update={"role": "m_total"}),
        )
        + case.gold.explicit_facts[1:],
    )
    assert _binding_shape(_projected(renamed)) == _binding_shape(_projected(case))


def test_renaming_an_entity_keeps_one_reciprocal_symbol_per_quantity() -> None:
    case = _case()
    gold = case.gold
    renamed = _with_gold(
        case,
        entities=(gold.entities[0].model_copy(update={"role": "crate"}),)
        + gold.entities[1:],
        motion_segments=(
            gold.motion_segments[0].model_copy(update={"actor_roles": ["crate"]}),
        ),
        events=(gold.events[0].model_copy(update={"subject_roles": ["crate"]}),),
        explicit_facts=tuple(
            fact.model_copy(update={"subject_role": "crate"})
            for fact in gold.explicit_facts
        ),
        relations=(
            gold.relations[0].model_copy(
                update={"participant_roles": ["crate", "surface"]}
            ),
        ),
        queries=(gold.queries[0].model_copy(update={"subject_role": "crate"}),),
    )
    projection = _projected(renamed)
    assert _binding_shape(projection) == _binding_shape(_projected(case))
    assert len(projection.draft.symbols) == len(projection.draft.quantities)


# --------------------------------------------------------------------------
# 6. No answer, solver, or gold authority
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, value",
    [
        ("family", "coriolis_relative_motion"),
        ("case_id", "fx_public_dev_9999"),
        ("difficulty", 5),
    ],
)
def test_gold_metadata_never_changes_the_symbol_binding(field, value) -> None:
    case = _case()
    tampered = case.model_copy(update={field: value})
    assert _binding_shape(_projected(tampered)) == _binding_shape(_projected(case))


def test_the_reference_answer_never_changes_the_symbol_binding() -> None:
    case = _case()
    answer = case.gold.answers[0]
    tampered = _with_gold(
        case,
        answers=(
            answer.model_copy(
                update={"numeric": answer.numeric * 3.0, "reference_expression": "m/a"}
            ),
        ),
    )
    baseline = _projected(case)
    assert _binding_shape(_projected(tampered)) == _binding_shape(baseline)
    assert _projected(tampered).unknown_symbol_ids == baseline.unknown_symbol_ids


def test_the_expected_system_type_never_changes_the_symbol_binding() -> None:
    case = _case()
    tampered = _with_gold(case, expected_system_type="slot_pin_relative_motion")
    baseline = _projected(case)
    assert _binding_shape(_projected(tampered)) == _binding_shape(baseline)
    assert _projected(tampered).known_symbol_ids == baseline.known_symbol_ids


def test_no_symbol_id_encodes_a_raw_value() -> None:
    projection = _projected(_case())
    values = {
        item.raw_value
        for item in projection.draft.quantities
        if item.raw_value is not None
    }
    assert values
    for symbol in projection.draft.symbols:
        for value in values:
            assert value not in symbol.symbol_id


# --------------------------------------------------------------------------
# 7. Binding stays consistent with geometry/interaction/assumption authority
# --------------------------------------------------------------------------


def test_a_rejected_assumption_contributes_no_symbol() -> None:
    case = _case()
    with_assumption = _with_gold(
        case,
        assumption_proposals=(
            CorpusAssumptionV1(
                role="dir",
                kind="direction_choice",
                subject_role="box",
                segment_role="motion_1",
                supporting_quote=None,
                server_value_only=True,
            ),
        ),
    )
    projection = _projected(with_assumption)
    assert projection.approvable_assumption_ids == ()
    assert len(projection.draft.symbols) == len(projection.draft.quantities)
    assert all(
        item.assumption_policy_ref is None for item in projection.draft.quantities
    )


def test_relations_contribute_no_symbol_of_their_own() -> None:
    projection = _projected(_case())
    bound_quantity_ids = {symbol.quantity_id for symbol in projection.draft.symbols}
    assert bound_quantity_ids == {
        item.quantity_id for item in projection.draft.quantities
    }
    for relation in (*projection.draft.geometry, *projection.draft.interactions):
        assert not getattr(relation, "quantity_ids", [])
