"""Stage 7 Lane B: a stated initial/final endpoint names an instant.

"The speed it started with" and "the speed it ended with" are different
physical quantities.  Collapsing both onto the bare interval made them one
identity — one symbol, one unknown, no way for a downstream endpoint law to
tell them apart, and no way for a metamorphic control to detect the swap.

The endpoint is taken from the source's own fields: `temporal_role` for a fact,
the output key for a query.  An event the source states explicitly always wins,
and a boundary the interval never declared is never invented.
"""

from __future__ import annotations

import pytest

from engine.mechanics.validation import validate_draft
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
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
    return _with_gold(
        case,
        motion_segments=(
            case.gold.motion_segments[0].model_copy(
                update={"end_event_role": "finish"}
            ),
        ),
    )


def _projected(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


def _query_of(case: PublicCorpusCaseV1, output_key: str) -> PublicCorpusCaseV1:
    return _with_gold(
        case,
        queries=(
            case.gold.queries[0].model_copy(
                update={"output_key": output_key, "component": "magnitude"}
            ),
        ),
    )


def _velocity_fact(
    case: PublicCorpusCaseV1, *, temporal_role: str, event_role: str | None = None
) -> PublicCorpusCaseV1:
    base = case.gold.explicit_facts[1]
    # A value of its own, so this fact never grounds on another fact's token.
    quote = "속도는 6.75 m/s"
    fact = base.model_copy(
        update={
            "role": "vel",
            "semantic_key": "velocity",
            "raw_value": "6.75",
            "raw_unit": "m/s",
            "evidence_quote": quote,
            "temporal_role": temporal_role,
            "event_role": event_role,
        }
    )
    updated = case.model_copy(
        update={"problem_text": case.problem_text + f" {quote} 이다."}
    )
    return _with_gold(updated, explicit_facts=case.gold.explicit_facts + (fact,))


def _scope_of(projection, quantity_id: str) -> tuple[str | None, str | None]:
    item = next(
        q for q in projection.draft.quantities if q.quantity_id == quantity_id
    )
    return (item.interval_id, item.event_id)


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------


def test_a_final_velocity_query_binds_the_interval_end() -> None:
    target = _projected(_query_of(_bounded(_case()), "final_velocity")).draft.queries[0].target
    assert target.interval_id == "motion_1"
    assert target.event_id == "finish"


def test_an_initial_velocity_query_binds_the_interval_start() -> None:
    target = _projected(_query_of(_bounded(_case()), "initial_velocity")).draft.queries[0].target
    assert target.interval_id == "motion_1"
    assert target.event_id == "start"


def test_initial_and_final_velocity_are_different_unknowns() -> None:
    initial = _projected(_query_of(_bounded(_case()), "initial_velocity"))
    final = _projected(_query_of(_bounded(_case()), "final_velocity"))
    assert initial.unknown_symbol_ids != final.unknown_symbol_ids
    assert (
        initial.draft.queries[0].target.event_id
        != final.draft.queries[0].target.event_id
    )


def test_an_explicit_query_event_wins_over_the_output_key() -> None:
    case = _query_of(_bounded(_case()), "final_velocity")
    explicit = _with_gold(
        case, queries=(case.gold.queries[0].model_copy(update={"event_role": "start"}),)
    )
    assert _projected(explicit).draft.queries[0].target.event_id == "start"


def test_an_undeclared_boundary_is_never_invented_for_a_query() -> None:
    # The fixture segment declares no end boundary.
    target = _projected(_query_of(_case(), "final_velocity")).draft.queries[0].target
    assert target.event_id is None
    assert target.interval_id == "motion_1"


def test_a_non_endpoint_query_key_keeps_the_bare_interval() -> None:
    target = _projected(_query_of(_bounded(_case()), "force")).draft.queries[0].target
    assert target.event_id is None
    assert target.interval_id == "motion_1"


# --------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------


def test_an_initial_fact_binds_the_interval_start() -> None:
    projection = _projected(_velocity_fact(_bounded(_case()), temporal_role="initial"))
    assert _scope_of(projection, "qty_vel") == ("motion_1", "start")


def test_a_final_fact_binds_the_interval_end() -> None:
    projection = _projected(_velocity_fact(_bounded(_case()), temporal_role="final"))
    assert _scope_of(projection, "qty_vel") == ("motion_1", "finish")


def test_initial_and_final_facts_get_different_symbols() -> None:
    initial = _projected(_velocity_fact(_bounded(_case()), temporal_role="initial"))
    final = _projected(_velocity_fact(_bounded(_case()), temporal_role="final"))
    assert _scope_of(initial, "qty_vel") != _scope_of(final, "qty_vel")
    symbol_of = lambda p: next(  # noqa: E731
        q.symbol_id for q in p.draft.quantities if q.quantity_id == "qty_vel"
    )
    assert symbol_of(initial) != symbol_of(final)


def test_an_explicit_fact_event_wins_over_the_temporal_role() -> None:
    projection = _projected(
        _velocity_fact(_bounded(_case()), temporal_role="final", event_role="start")
    )
    assert _scope_of(projection, "qty_vel") == ("motion_1", "start")


def test_an_undeclared_boundary_is_never_invented_for_a_fact() -> None:
    projection = _projected(_velocity_fact(_case(), temporal_role="final"))
    assert _scope_of(projection, "qty_vel") == ("motion_1", None)


@pytest.mark.parametrize("temporal_role", ["timeless", "during", "interval"])
def test_a_non_endpoint_temporal_role_keeps_the_bare_interval(temporal_role) -> None:
    projection = _projected(
        _velocity_fact(_bounded(_case()), temporal_role=temporal_role)
    )
    assert _scope_of(projection, "qty_vel") == ("motion_1", None)


# --------------------------------------------------------------------------
# The endpoint survives the real validator, and gold has no say
# --------------------------------------------------------------------------


def test_the_endpoint_bound_draft_validates() -> None:
    projection = _projected(
        _velocity_fact(
            _query_of(_bounded(_case()), "final_velocity"), temporal_role="initial"
        )
    )
    result = validate_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert result.accepted, [issue.code.value for issue in result.issues]


def test_gold_metadata_never_changes_the_endpoint_binding() -> None:
    case = _query_of(_bounded(_case()), "final_velocity")
    baseline = _projected(case).draft.queries[0].target.event_id
    tampered = case.model_copy(
        update={"family": "coriolis_relative_motion", "difficulty": 5}
    )
    assert _projected(tampered).draft.queries[0].target.event_id == baseline


def test_the_reference_answer_never_changes_the_endpoint_binding() -> None:
    case = _query_of(_bounded(_case()), "final_velocity")
    answer = case.gold.answers[0]
    baseline = _projected(case).unknown_symbol_ids
    tampered = _with_gold(
        case, answers=(answer.model_copy(update={"numeric": answer.numeric * 5.0}),)
    )
    assert _projected(tampered).unknown_symbol_ids == baseline
