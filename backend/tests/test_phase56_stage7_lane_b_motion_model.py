"""Stage 7 Lane B: source-declared motion model and elapsed-time typing.

Two corpus fields the projection previously discarded are structural, not
decorative:

* `motion_segments[].motion_model` is what tells the typed IR *how* an interval
  behaves.  The kinematics laws gate on an approved assumption kind, and this
  field is the only source-grounded origin for one.
* a `time` fact the corpus scopes to a whole segment is an elapsed time, which
  the typed IR names `duration`.  The distinction comes from the corpus's own
  `temporal_role`, never from the sentence and never from a family.

Neither derivation may read a family, an expected system type, an expected
terminal, or an answer, and an unmapped motion model must contribute nothing
rather than a guess.
"""

from __future__ import annotations

import pytest

from engine.mechanics.validation import validate_draft
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    _MOTION_MODEL_ASSUMPTIONS,
    _QUERY_SCOPED_MOTION_MODEL_ASSUMPTIONS,
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


def _with_model(case: PublicCorpusCaseV1, motion_model: str) -> PublicCorpusCaseV1:
    return _with_gold(
        case,
        motion_segments=(
            case.gold.motion_segments[0].model_copy(
                update={"motion_model": motion_model}
            ),
        ),
    )


def _projected(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


def _assumptions(projection, kind: str):
    return [item for item in projection.draft.assumptions if item.kind == kind]


# --------------------------------------------------------------------------
# Motion model -> typed assumption
# --------------------------------------------------------------------------


# The base fixture asks for a force.  An authority that licenses one specific
# readout is only carried when that readout is what the source asks for, so the
# licensing table decides which query this case must use.
_LICENSING_QUERY_KEY: dict[str, str] = {"period": "period", "frequency": "frequency"}


def _with_licensing_query(case: PublicCorpusCaseV1, kind: str) -> PublicCorpusCaseV1:
    """Give the case a query that licenses `kind`, if `kind` needs one."""

    licensed = _QUERY_SCOPED_MOTION_MODEL_ASSUMPTIONS.get(kind)
    if licensed is None:
        return case
    output_key = next(
        _LICENSING_QUERY_KEY[role] for role in sorted(licensed)
        if role in _LICENSING_QUERY_KEY
    )
    return _with_gold(
        case,
        queries=(
            case.gold.queries[0].model_copy(update={"output_key": output_key}),
        ),
    )


@pytest.mark.parametrize("motion_model, kind", sorted(_MOTION_MODEL_ASSUMPTIONS.items()))
def test_a_declared_motion_model_becomes_one_approved_assumption(
    motion_model, kind
) -> None:
    case = _with_licensing_query(_with_model(_case(), motion_model), kind)
    projection = _projected(case)
    derived = _assumptions(projection, kind)
    assert len(derived) == 1
    assumption = derived[0]
    assert assumption.disposition.value == "approved"
    assert assumption.subject_id == "box"
    assert assumption.interval_id == "motion_1"
    assert assumption.assumption_id in projection.approvable_assumption_ids


@pytest.mark.parametrize(
    "motion_model, kind",
    sorted(
        (model, kind)
        for model, kind in _MOTION_MODEL_ASSUMPTIONS.items()
        if kind in _QUERY_SCOPED_MOTION_MODEL_ASSUMPTIONS
    ),
)
def test_a_query_scoped_authority_is_withheld_when_its_readout_is_not_asked_for(
    motion_model, kind
) -> None:
    """An authority licenses one readout, so an unrelated question never carries it.

    Left unscoped it would sit in every Draft of that motion model and could
    combine with an unrelated quantity to write an equation the source never
    asked for.
    """

    projection = _projected(_with_model(_case(), motion_model))
    assert _assumptions(projection, kind) == []


def test_a_motion_model_assumption_carries_no_proposed_value() -> None:
    projection = _projected(_with_model(_case(), "constant_acceleration_1d"))
    assumption = _assumptions(projection, "constant_acceleration")[0]
    assert assumption.proposed_role is None
    assert assumption.proposed_value is None
    assert assumption.proposed_unit is None


def test_an_unmapped_motion_model_contributes_nothing() -> None:
    projection = _projected(_with_model(_case(), "unknown"))
    kinds = {item.kind for item in projection.draft.assumptions}
    assert not kinds & set(_MOTION_MODEL_ASSUMPTIONS.values())


def test_a_motion_model_assumption_binds_only_that_segment_and_its_actors() -> None:
    case = _case()
    second = case.gold.motion_segments[0].model_copy(
        update={
            "role": "motion_2",
            "order": 2,
            "motion_model": "unknown",
            "start_event_role": None,
            "end_event_role": None,
        }
    )
    first = case.gold.motion_segments[0].model_copy(
        update={"motion_model": "constant_acceleration_1d"}
    )
    projection = _projected(_with_gold(case, motion_segments=(first, second)))
    derived = _assumptions(projection, "constant_acceleration")
    assert [item.interval_id for item in derived] == ["motion_1"]
    assert {item.subject_id for item in derived} == {"box"}
    # The surface is not an actor of that segment, so it gains no assumption.
    assert all(item.subject_id != "surface" for item in projection.draft.assumptions)


def test_the_projected_draft_with_motion_assumptions_still_validates() -> None:
    projection = _projected(_with_model(_case(), "constant_acceleration_1d"))
    result = validate_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert result.accepted, [issue.code.value for issue in result.issues]


@pytest.mark.parametrize(
    "field, value",
    [
        ("family", "coriolis_relative_motion"),
        ("case_id", "fx_public_dev_9999"),
    ],
)
def test_gold_metadata_never_changes_the_derived_assumptions(field, value) -> None:
    case = _with_model(_case(), "constant_acceleration_1d")
    baseline = _projected(case).approvable_assumption_ids
    tampered = case.model_copy(update={field: value})
    assert _projected(tampered).approvable_assumption_ids == baseline


def test_the_expected_system_type_never_changes_the_derived_assumptions() -> None:
    case = _with_model(_case(), "constant_acceleration_1d")
    baseline = _projected(case).approvable_assumption_ids
    tampered = _with_gold(case, expected_system_type="slot_pin_relative_motion")
    assert _projected(tampered).approvable_assumption_ids == baseline


def test_changing_the_motion_model_changes_the_authorised_assumptions() -> None:
    constant = _projected(_with_model(_case(), "constant_acceleration_1d"))
    uniform = _projected(_with_model(_case(), "constant_velocity_1d"))
    assert constant.approvable_assumption_ids != uniform.approvable_assumption_ids
    assert _assumptions(constant, "constant_acceleration")
    assert _assumptions(uniform, "constant_velocity")


# --------------------------------------------------------------------------
# Elapsed time -> duration
# --------------------------------------------------------------------------


def _with_time_fact(
    case: PublicCorpusCaseV1, *, temporal_role: str, event_role: str | None = None
) -> PublicCorpusCaseV1:
    base = case.gold.explicit_facts[1]
    quote = f"걸린 시간은 {base.raw_value} s"
    fact = base.model_copy(
        update={
            "role": "elapsed",
            "semantic_key": "time",
            "raw_unit": "s",
            "evidence_quote": quote,
            "temporal_role": temporal_role,
            "event_role": event_role,
        }
    )
    updated = case.model_copy(
        update={"problem_text": case.problem_text + f" {quote} 이다."}
    )
    return _with_gold(
        updated,
        explicit_facts=case.gold.explicit_facts + (fact,),
    )


def _role_of(projection, quantity_id: str) -> str:
    return next(
        item.role.value
        for item in projection.draft.quantities
        if item.quantity_id == quantity_id
    )


@pytest.mark.parametrize("temporal_role", ["interval", "during"])
def test_a_segment_scoped_time_is_typed_as_a_duration(temporal_role) -> None:
    projection = _projected(_with_time_fact(_case(), temporal_role=temporal_role))
    assert _role_of(projection, "qty_elapsed") == "duration"


def test_an_instant_time_stays_a_time_not_a_duration() -> None:
    projection = _projected(
        _with_time_fact(_case(), temporal_role="at_event", event_role="start")
    )
    assert _role_of(projection, "qty_elapsed") == "time"


def test_a_time_bound_to_an_event_is_never_reinterpreted_as_elapsed() -> None:
    projection = _projected(
        _with_time_fact(_case(), temporal_role="interval", event_role="start")
    )
    # The corpus contradicts itself; the event binding wins and no elapsed
    # meaning is invented.
    assert _role_of(projection, "qty_elapsed") == "time"


def test_a_timeless_time_stays_a_time() -> None:
    projection = _projected(_with_time_fact(_case(), temporal_role="timeless"))
    assert _role_of(projection, "qty_elapsed") == "time"


def test_the_duration_keeps_its_own_reciprocal_symbol() -> None:
    projection = _projected(_with_time_fact(_case(), temporal_role="interval"))
    quantity = next(
        item
        for item in projection.draft.quantities
        if item.quantity_id == "qty_elapsed"
    )
    symbol = next(
        item
        for item in projection.draft.symbols
        if item.symbol_id == quantity.symbol_id
    )
    assert symbol.quantity_id == "qty_elapsed"
    assert symbol.dimension == quantity.dimension
