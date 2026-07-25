"""Stage 7 Lane B: an undirected scalar is a magnitude, and a rest-bounded
path length is a displacement.

Two typed readings the projection previously discarded:

* A source that says a quantity's direction is `not_applicable` has said which
  component it stated — the magnitude.  That is a different statement from
  `unspecified`, which says the direction exists but was not given.  The typed
  laws pair a quantity only with another of the same component, so collapsing
  the two made an undirected fact unusable next to a magnitude question.
* A path length measured over a whole interval *is* that interval's
  displacement magnitude whenever the interval's own typed model forbids a
  direction reversal inside it.  Absent that proof the path length stays a
  `distance`, which no law reads, so a motion that may double back fails closed
  rather than answering with a displacement it cannot justify.

Neither reading may consult a family, a case ID, an expected system type, an
expected terminal, or an answer.
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
                update={"motion_model": motion_model, "end_event_role": "finish"}
            ),
        ),
    )


def _with_rest(case: PublicCorpusCaseV1, kind: str = "starts_from_rest"):
    return _with_gold(
        case,
        assumption_proposals=(
            CorpusAssumptionV1(
                role="rest",
                kind=kind,
                subject_role="box",
                segment_role="motion_1",
                supporting_quote=case.problem_text[:14],
                server_value_only=False,
            ),
        ),
    )


def _with_distance(
    case: PublicCorpusCaseV1,
    *,
    temporal_role: str = "interval",
    direction: str = "not_applicable",
    event_role: str | None = None,
) -> PublicCorpusCaseV1:
    base = case.gold.explicit_facts[1]
    quote = "이동 거리는 8.4 m"
    fact = base.model_copy(
        update={
            "role": "travel",
            "semantic_key": "distance",
            "raw_value": "8.4",
            "raw_unit": "m",
            "evidence_quote": quote,
            "temporal_role": temporal_role,
            "direction": direction,
            "event_role": event_role,
        }
    )
    updated = case.model_copy(
        update={"problem_text": case.problem_text + f" {quote} 이다."}
    )
    return _with_gold(updated, explicit_facts=case.gold.explicit_facts + (fact,))


def _projected(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


def _quantity(projection, quantity_id: str):
    return next(
        item
        for item in projection.draft.quantities
        if item.quantity_id == quantity_id
    )


# --------------------------------------------------------------------------
# `not_applicable` names the magnitude; `unspecified` stays uncommitted
# --------------------------------------------------------------------------


def test_an_undirected_component_quantity_is_a_magnitude() -> None:
    projection = _projected(_case())
    assert _quantity(projection, "qty_acceleration").component.value == "magnitude"


def test_an_unspecified_direction_stays_uncommitted() -> None:
    case = _case()
    fact = case.gold.explicit_facts[1].model_copy(update={"direction": "unspecified"})
    projection = _projected(
        _with_gold(case, explicit_facts=(case.gold.explicit_facts[0], fact))
    )
    assert _quantity(projection, "qty_acceleration").component.value == "unspecified"


def test_a_stated_direction_is_never_overwritten_by_a_magnitude() -> None:
    case = _case()
    fact = case.gold.explicit_facts[1].model_copy(update={"direction": "right"})
    projection = _projected(
        _with_gold(case, explicit_facts=(case.gold.explicit_facts[0], fact))
    )
    quantity = _quantity(projection, "qty_acceleration")
    assert quantity.component.value != "magnitude"
    assert quantity.direction is not None


def test_a_role_that_carries_no_component_gains_none() -> None:
    # Mass is a scalar invariant; stamping a component on it would invent
    # identity that the physics does not have.
    projection = _projected(_case())
    assert _quantity(projection, "qty_mass").component.value == "unspecified"


def test_the_rest_boundary_unknown_is_a_magnitude() -> None:
    projection = _projected(_with_rest(_with_model(_case(), "constant_acceleration_1d")))
    state = projection.draft.state_conditions[0]
    quantity = _quantity(projection, state.quantity_ids[0])
    assert quantity.component.value == "magnitude"


# --------------------------------------------------------------------------
# A reversal-free interval gives a path length its typed home
# --------------------------------------------------------------------------


def test_a_constant_velocity_interval_makes_a_path_length_a_displacement() -> None:
    projection = _projected(
        _with_distance(_with_model(_case(), "constant_velocity_1d"))
    )
    assert _quantity(projection, "qty_travel").role.value == "displacement"


def test_a_rest_started_constant_acceleration_interval_does_too() -> None:
    projection = _projected(
        _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    )
    assert _quantity(projection, "qty_travel").role.value == "displacement"


def test_the_retyped_path_length_keeps_its_magnitude_component() -> None:
    projection = _projected(
        _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    )
    quantity = _quantity(projection, "qty_travel")
    assert quantity.component.value == "magnitude"
    assert quantity.role.value == "displacement"


def test_the_retyped_path_length_keeps_every_other_identity_field() -> None:
    case = _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    quantity = _quantity(_projected(case), "qty_travel")
    assert quantity.subject_id == "box"
    assert quantity.interval_id == "motion_1"
    assert quantity.event_id is None
    assert quantity.raw_value == "8.4"
    assert quantity.raw_unit == "m"
    assert quantity.evidence_refs


def test_the_retyped_path_length_owns_a_reciprocal_symbol_for_its_new_role() -> None:
    projection = _projected(
        _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    )
    quantity = _quantity(projection, "qty_travel")
    symbol = next(
        item
        for item in projection.draft.symbols
        if item.symbol_id == quantity.symbol_id
    )
    assert symbol.quantity_id == "qty_travel"
    assert quantity.symbol_id in projection.known_symbol_ids


def test_a_retyped_path_length_draft_still_validates() -> None:
    projection = _projected(
        _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    )
    result = validate_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert result.accepted, [issue.code.value for issue in result.issues]


# --------------------------------------------------------------------------
# Without the proof, the path length stays a path length
# --------------------------------------------------------------------------


def test_a_constant_acceleration_interval_that_may_reverse_keeps_a_distance() -> None:
    # Constant acceleration alone permits the motion to turn around, so the
    # path length and the displacement are not the same number.
    projection = _projected(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    assert _quantity(projection, "qty_travel").role.value == "distance"


def test_an_interval_with_no_declared_motion_model_keeps_a_distance() -> None:
    projection = _projected(_with_rest(_with_distance(_case())))
    assert _quantity(projection, "qty_travel").role.value == "distance"


def test_an_end_rest_does_not_license_a_start_reversal_proof() -> None:
    projection = _projected(
        _with_rest(
            _with_distance(_with_model(_case(), "constant_acceleration_1d")),
            kind="ends_at_rest",
        )
    )
    assert _quantity(projection, "qty_travel").role.value == "distance"


def test_a_path_length_pinned_to_an_instant_is_never_retyped() -> None:
    projection = _projected(
        _with_rest(
            _with_distance(
                _with_model(_case(), "constant_acceleration_1d"),
                temporal_role="at_event",
                event_role="start",
            )
        )
    )
    assert _quantity(projection, "qty_travel").role.value == "distance"


def test_an_unapproved_rest_assumption_licenses_nothing() -> None:
    case = _with_distance(_with_model(_case(), "constant_acceleration_1d"))
    unapproved = _with_gold(
        case,
        assumption_proposals=(
            CorpusAssumptionV1(
                role="rest",
                kind="starts_from_rest",
                subject_role="box",
                segment_role="motion_1",
                supporting_quote="이 문장은 문제에 존재하지 않는다",
                server_value_only=False,
            ),
        ),
    )
    projection = _projected(unapproved)
    # The motion model is still authorised; the ungrounded rest claim is not,
    # so no boundary condition exists to prove the interval never reverses.
    assert list(projection.draft.state_conditions) == []
    assert _quantity(projection, "qty_travel").role.value == "distance"


def test_a_rest_on_a_different_subject_licenses_nothing() -> None:
    case = _with_distance(_with_model(_case(), "constant_acceleration_1d"))
    other = _with_gold(
        case,
        assumption_proposals=(
            CorpusAssumptionV1(
                role="rest",
                kind="starts_from_rest",
                subject_role="surface",
                segment_role="motion_1",
                supporting_quote=case.problem_text[:14],
                server_value_only=False,
            ),
        ),
    )
    assert _quantity(_projected(other), "qty_travel").role.value == "distance"


# --------------------------------------------------------------------------
# No gold authority
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, value",
    [
        ("family", "coriolis_relative_motion"),
        ("case_id", "fx_public_dev_9999"),
        ("difficulty", 5),
    ],
)
def test_gold_metadata_never_changes_the_typed_role(field, value) -> None:
    case = _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    baseline = _quantity(_projected(case), "qty_travel").role.value
    tampered = case.model_copy(update={field: value})
    assert _quantity(_projected(tampered), "qty_travel").role.value == baseline


def test_the_expected_system_type_never_changes_the_typed_role() -> None:
    case = _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    baseline = _quantity(_projected(case), "qty_travel").role.value
    tampered = _with_gold(case, expected_system_type="slot_pin_relative_motion")
    assert _quantity(_projected(tampered), "qty_travel").role.value == baseline


def test_the_reference_answer_never_changes_the_typed_role() -> None:
    case = _with_rest(_with_distance(_with_model(_case(), "constant_acceleration_1d")))
    answer = case.gold.answers[0]
    baseline = _quantity(_projected(case), "qty_travel").role.value
    tampered = _with_gold(
        case, answers=(answer.model_copy(update={"numeric": answer.numeric * 9.0}),)
    )
    assert _quantity(_projected(tampered), "qty_travel").role.value == baseline
