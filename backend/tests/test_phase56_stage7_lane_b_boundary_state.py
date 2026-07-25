"""Stage 7 Lane B: an approved rest assumption as a typed boundary constraint.

A rest assumption names an *instant* — the start or the end of the interval the
corpus scoped it to.  The typed IR expresses that as a `StateCondition` at that
boundary over the instant's own unknown velocity, which the reusable
`state_at_rest` law pins to zero.  Nothing becomes a fabricated known value:
the constraint carries the authority and the solver derives the number.

The projection emits nothing at all — rather than guessing — when the
assumption is unapproved, has no interval, has no unambiguous supporting quote,
or names a boundary the source never declared.
"""

from __future__ import annotations

import pytest

from engine.mechanics.compiler import authorize_validated_mechanics_ir
from engine.mechanics.normalization import normalize_draft
from engine.mechanics.validation import validate_draft
from evaluation.phase56_stage7.corpus_records import (
    CorpusAssumptionV1,
    PublicCorpusCaseV1,
)
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionTerminal,
    project_case_to_draft,
)
from support.phase56_stage7_corpus_fixtures import build_case


def _case(**overrides) -> PublicCorpusCaseV1:
    record = build_case(
        index=3,
        split="public_dev",
        family="constant_acceleration_1d",
        future_terminal="accepted",
        with_answer=True,
    )
    record["split"] = PublicSplit.public_dev
    record.update(overrides)
    return PublicCorpusCaseV1(**record)


def _with_gold(case: PublicCorpusCaseV1, **gold_updates) -> PublicCorpusCaseV1:
    return case.model_copy(update={"gold": case.gold.model_copy(update=gold_updates)})


def _bounded(case: PublicCorpusCaseV1) -> PublicCorpusCaseV1:
    """Give the fixture segment both a start and an end boundary."""

    return _with_gold(
        case,
        motion_segments=(
            case.gold.motion_segments[0].model_copy(
                update={"end_event_role": "finish"}
            ),
        ),
    )


def _rest(
    case: PublicCorpusCaseV1,
    *,
    kind: str = "starts_from_rest",
    quote: str | None = None,
    segment_role: str | None = "motion_1",
    subject_role: str = "box",
) -> PublicCorpusCaseV1:
    return _with_gold(
        case,
        assumption_proposals=(
            CorpusAssumptionV1(
                role="rest",
                kind=kind,
                subject_role=subject_role,
                segment_role=segment_role,
                supporting_quote=case.problem_text[:14] if quote is None else quote,
                server_value_only=False,
            ),
        ),
    )


def _projected(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


def _states(projection):
    return list(projection.draft.state_conditions)


# --------------------------------------------------------------------------
# The constraint itself
# --------------------------------------------------------------------------


def test_an_approved_start_rest_becomes_an_initial_boundary_constraint() -> None:
    projection = _projected(_rest(_bounded(_case())))
    states = _states(projection)
    assert len(states) == 1
    state = states[0]
    assert state.kind.value == "initial"
    assert state.state.value == "at_rest"
    assert state.subject_id == "box"
    assert state.interval_id == "motion_1"
    assert state.event_id == "start"


def test_an_approved_end_rest_binds_the_end_boundary() -> None:
    case = _rest(_bounded(_case()), kind="ends_at_rest")
    state = _states(_projected(case))[0]
    assert state.kind.value == "final"
    assert state.event_id == "finish"


def test_the_constraint_owns_an_unknown_velocity_never_a_known_value() -> None:
    projection = _projected(_rest(_bounded(_case())))
    state = _states(projection)[0]
    assert len(state.quantity_ids) == 1
    quantity = next(
        item
        for item in projection.draft.quantities
        if item.quantity_id == state.quantity_ids[0]
    )
    assert quantity.provenance.value == "unknown"
    assert quantity.raw_value is None and quantity.raw_unit is None
    assert quantity.role.value == "velocity"
    assert quantity.subject_id == "box"
    assert quantity.interval_id == "motion_1"
    assert quantity.event_id == "start"


def test_the_boundary_unknown_carries_its_own_reciprocal_symbol() -> None:
    projection = _projected(_rest(_bounded(_case())))
    state = _states(projection)[0]
    quantity = next(
        item
        for item in projection.draft.quantities
        if item.quantity_id == state.quantity_ids[0]
    )
    assert quantity.symbol_id in projection.unknown_symbol_ids
    symbol = next(
        item
        for item in projection.draft.symbols
        if item.symbol_id == quantity.symbol_id
    )
    assert symbol.quantity_id == quantity.quantity_id


def test_the_constraint_is_grounded_by_a_real_source_quote() -> None:
    projection = _projected(_rest(_bounded(_case())))
    state = _states(projection)[0]
    assert state.evidence_refs
    evidence = next(
        item
        for item in projection.draft.source_evidence
        if item.evidence_id == state.evidence_refs[0]
    )
    text = projection.problem_text
    assert text[evidence.source_span.start : evidence.source_span.end] == evidence.quote
    assert evidence.quote in text


# --------------------------------------------------------------------------
# Fail-closed: no guessing
# --------------------------------------------------------------------------


def test_an_unapproved_rest_assumption_emits_no_constraint() -> None:
    projection = _projected(
        _rest(_bounded(_case()), quote="이 문장은 문제에 존재하지 않는다")
    )
    assert projection.approvable_assumption_ids == ()
    assert _states(projection) == []


def test_a_rest_assumption_without_an_interval_emits_no_constraint() -> None:
    projection = _projected(_rest(_bounded(_case()), segment_role=None))
    assert _states(projection) == []


def test_a_rest_assumption_whose_boundary_is_undeclared_emits_no_constraint() -> None:
    case = _with_gold(
        _case(),
        motion_segments=(
            _case().gold.motion_segments[0].model_copy(
                update={"start_event_role": None, "end_event_role": None}
            ),
        ),
    )
    projection = _projected(_rest(case))
    assert _states(projection) == []


def test_a_rest_assumption_for_a_non_actor_emits_no_constraint() -> None:
    projection = _projected(_rest(_bounded(_case()), subject_role="surface"))
    assert _states(projection) == []


def test_an_ambiguous_supporting_quote_emits_no_constraint() -> None:
    case = _bounded(_case())
    repeated = case.model_copy(
        update={"problem_text": case.problem_text + " " + case.problem_text[:14]}
    )
    projection = _projected(_rest(repeated))
    # The quote now occurs twice; the projection refuses to pick an occurrence.
    assert _states(projection) == []


def test_a_non_rest_assumption_emits_no_constraint() -> None:
    projection = _projected(_rest(_bounded(_case()), kind="frictionless"))
    assert _states(projection) == []


# --------------------------------------------------------------------------
# The constraint reaches the real engine
# --------------------------------------------------------------------------


def test_the_projected_draft_with_a_boundary_constraint_validates() -> None:
    projection = _projected(_rest(_bounded(_case())))
    result = validate_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert result.accepted, [issue.code.value for issue in result.issues]


def test_the_boundary_constraint_survives_normalization_and_authorization() -> None:
    projection = _projected(_rest(_bounded(_case())))
    normalization = normalize_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert normalization.accepted and normalization.ir is not None
    states = normalization.ir.state_conditions
    assert len(states) == 1
    assert states[0].state.value == "at_rest"
    # The pinned velocity is still unknown in the IR; nothing invented a value.
    quantity = next(
        item
        for item in normalization.ir.quantities
        if item.quantity_id == states[0].quantity_ids[0]
    )
    assert quantity.si_value is None
    authorize_validated_mechanics_ir(normalization.ir)


def test_the_boundary_constraint_emits_the_state_at_rest_law() -> None:
    from engine.mechanics.compiler import compiler as compiler_module
    from engine.mechanics.compiler import MechanicsCompiler
    from engine.mechanics.laws import apply_core_laws

    projection = _projected(_rest(_bounded(_case())))
    normalization = normalize_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    ir = normalization.ir
    assert ir is not None
    query = ir.queries[0]
    query_quantity, _ = compiler_module._query_quantity(ir, query)
    source_symbols, _ = compiler_module._validate_reciprocal_bindings(ir)
    records = compiler_module._primary_records(ir, query)
    _, edges = compiler_module._graph_edges(records)
    relevant, _ = compiler_module._relevant_ids(
        query, edges, MechanicsCompiler()._limits
    )
    context, _, _, issue = compiler_module._build_law_context(
        ir,
        query,
        query_quantity,
        relevant,
        source_symbols,
        frozenset(projection.approvable_assumption_ids),
    )
    assert context is not None, issue
    emitted = {item.rule.law_id for item in apply_core_laws(context)}
    assert "state_at_rest" in emitted


# --------------------------------------------------------------------------
# No gold authority
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, value",
    [
        ("family", "coriolis_relative_motion"),
        ("case_id", "fx_public_dev_9999"),
    ],
)
def test_gold_metadata_never_changes_the_boundary_constraint(field, value) -> None:
    case = _rest(_bounded(_case()))
    baseline = _states(_projected(case))[0].model_dump(mode="json")
    tampered = case.model_copy(update={field: value})
    assert _states(_projected(tampered))[0].model_dump(mode="json") == baseline


def test_the_reference_answer_never_changes_the_boundary_constraint() -> None:
    case = _rest(_bounded(_case()))
    answer = case.gold.answers[0]
    baseline = _states(_projected(case))[0].model_dump(mode="json")
    tampered = _with_gold(
        case,
        answers=(answer.model_copy(update={"numeric": answer.numeric * 7.0}),),
    )
    assert _states(_projected(tampered))[0].model_dump(mode="json") == baseline
