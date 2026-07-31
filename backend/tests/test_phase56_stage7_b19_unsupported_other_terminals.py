"""B19: a record that names no mechanism is unsupported, not underdetermined.

``underdetermined`` says the model is short of equations — the force is named
but unvalued, the contact is stated but its coefficient is missing — and one
more number would close it.  A record in which *every* typed place a mechanism
could live is empty is not short of numbers.  It is a body, some quantities,
and nothing that relates them, and no additional value creates a relation the
source never stated.

These tests hold that distinction from both sides: the empty record is refused
on scope with a typed compiler reason and no numeric answer, and the moment
any single mechanism appears the record goes back to being underdetermined.
"""
from __future__ import annotations

import hashlib

import pytest

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
from evaluation.phase56_stage7.lane_b_scoring import score_lane_b_cases
from support.phase56_stage7_corpus_fixtures import build_case


pytestmark = pytest.mark.slow


UNSUPPORTED_REASON = "requires_specialized_model"
# The typed compiler codes that prove a *course-scope deferral*.  An
# unsupported-other refusal must never carry one: the two classes are
# distinguished by evidence, so sharing evidence would make them
# indistinguishable.
DEFERRED_CODES = frozenset(
    {
        "free_linear_vibration_readout_deferred",
        "rotating_frame_relative_acceleration_deferred",
        "slot_pin_relative_motion_deferred",
        "translating_frame_relative_acceleration_deferred",
    }
)


def _fact(
    role: str,
    key: str,
    value: str,
    unit: str,
    quote: str,
    subject: str,
    *,
    temporal: str = "timeless",
    event: str | None = None,
    direction: str = "not_applicable",
) -> dict:
    return {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": "motion_1",
        "event_role": event,
        "temporal_role": temporal,
        "direction": direction,
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }


def _case(
    *,
    shape: str = "rotational",
    mechanism: str | None = None,
    family: str = "independent_no_mechanism_fixture",
    case_id: str = "fx_public_dev_0991",
    parse_status: str = "unsupported",
    future_terminal: str = "unsupported_other",
    expected_failure_codes: list[str] | None = None,
    fake_answer: float | None = None,
    reverse: bool = False,
    text_prefix: str = "",
    body_label: str = "회전체",
) -> PublicCorpusCaseV1:
    """One body, some numbers, and — unless ``mechanism`` says so — nothing else.

    ``shape`` picks which pair of source quantities the record carries; both
    are shapes that describe a specialized model this engine does not
    implement.  ``mechanism`` adds exactly one typed record in which a model
    could live, which is the control the refusal has to respect.
    """

    if shape == "rotational":
        stated_quote = "회전체의 각속력은 12 rad/s"
        facts = [
            _fact(
                "w1", "angular_velocity", "12", "rad/s", stated_quote, "body",
                temporal="during", direction="unspecified",
            )
        ]
        output_key = "angular_velocity"
        entity_kind = "rigid_body"
    else:
        stated_quote = "경과 시간은 6 s"
        facts = [
            _fact("t", "time", "6", "s", stated_quote, "body", temporal="interval")
        ]
        output_key = "final_velocity"
        entity_kind = "vehicle"

    text = f"{text_prefix}{stated_quote}. 나중 값을 구하여라."
    entities = [{"role": "body", "kind": entity_kind, "label": body_label}]
    relations: list[dict] = []
    assumptions: list[dict] = []
    if mechanism == "relation":
        entities.append({"role": "surface", "kind": "surface", "label": "면"})
        relations.append(
            {
                "role": "support",
                "kind": "rests_on",
                "participant_roles": ["body", "surface"],
                "segment_role": "motion_1",
            }
        )
    elif mechanism == "assumption":
        gravity_quote = "중력가속도는 9.81 m/s²로 사용한다"
        text += f" {gravity_quote}."
        assumptions.append(
            {
                "role": "gravity",
                "kind": "constant_gravity",
                "subject_role": "body",
                "segment_role": "motion_1",
                "supporting_quote": gravity_quote,
                "server_value_only": True,
            }
        )

    if reverse:
        entities.reverse()
        facts.reverse()

    gold = {
        "parse_status": parse_status,
        "expected_system_type": family,
        "phase55_expected_terminal": "solver_gap",
        "future_expected_terminal": future_terminal,
        "figure_dependency": {"level": "none", "missing_information": []},
        "entities": entities,
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["body"],
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [],
        "explicit_facts": facts,
        "relations": relations,
        "assumption_proposals": assumptions,
        "queries": [
            {
                "role": "q1",
                "output_key": output_key,
                "subject_role": "body",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "answers": (
            []
            if fake_answer is None
            else [
                {
                    "query_role": "q1",
                    "numeric": fake_answer,
                    "unit": "m/s",
                    "tolerance_abs": 1.0e-6,
                    "reference_expression": "deliberately non-authoritative",
                }
            ]
        ),
        "expected_failure_codes": list(expected_failure_codes or []),
    }
    record = build_case(
        index=991,
        split="public_dev",
        family=family,
        future_terminal=future_terminal,
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
    return PublicCorpusCaseV1.model_validate(record)


def _run(case: PublicCorpusCaseV1, nonce: str):
    projection = project_case_to_draft(case)
    return run_lane_b_case(
        projection, execution_token=deterministic_token(0, run_nonce=nonce)
    )


# ---------------------------------------------------------------------------
# The refusal itself.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ("rotational", "variable_mass"))
def test_a_record_with_no_mechanism_is_refused_on_scope(shape: str) -> None:
    projection = project_case_to_draft(_case(shape=shape))
    assert projection.terminal is DraftProjectionTerminal.projected
    draft = projection.draft
    # Every place a mechanism could live really is empty.
    assert not draft.interactions
    assert not draft.geometry
    assert not draft.constraints
    assert not draft.assumptions
    assert not draft.reference_frames
    assert not draft.points
    assert not draft.state_conditions

    result = _run(_case(shape=shape), f"b19-{shape}")
    assert result.terminal is LaneBTerminal.compiler_unsupported
    assert result.answer_value_si is None
    assert result.verified_candidate_count == 0
    # A typed reason, and specifically not a deferred one.
    assert UNSUPPORTED_REASON in set(result.compiler_codes)
    assert not set(result.compiler_codes) & DEFERRED_CODES


@pytest.mark.parametrize("shape", ("rotational", "variable_mass"))
def test_the_refusal_scores_as_unsupported_other(shape: str) -> None:
    """End to end: the scorer accepts the terminal *and* its evidence."""

    case = _case(shape=shape)
    card = score_lane_b_cases([case], [_run(case, f"b19-score-{shape}")])
    payload = card.as_dict()
    assert payload["unsupported_other"] == {"expected": 1, "matched": 1}
    assert payload["supported"]["wrong"] == 0
    assert payload["supported"]["solved_but_unscored"] == 0
    assert payload["blocked_numeric_answers"] == 0
    assert payload["supported_downgraded_to_unsupported"] == 0


# ---------------------------------------------------------------------------
# The control: any one mechanism, and it is underdetermined again.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mechanism", ("relation", "assumption"))
@pytest.mark.parametrize("shape", ("rotational", "variable_mass"))
def test_one_stated_mechanism_makes_it_underdetermined_again(
    shape: str, mechanism: str
) -> None:
    """The refusal keys on absence, so presence has to undo it.

    This is the guard against downgrading a supported problem: a real
    mechanics problem always writes its mechanism down somewhere, and as soon
    as it does, this record is short of numbers rather than short of a model.
    """

    result = _run(
        _case(shape=shape, mechanism=mechanism), f"b19-mech-{shape}-{mechanism}"
    )
    assert result.terminal is not LaneBTerminal.compiler_unsupported
    assert result.answer_value_si is None


def test_emptiness_alone_refuses_nothing() -> None:
    """The refusal needs *both* halves: no mechanism, and no determination.

    Several supported shapes carry no interaction, geometry, or assumption in
    the projected Draft either — a stated impulse and two velocities, a stated
    work and two speeds — and they reach a solve.  The refusal sits in the
    `underdetermined` branch alone, so a record the graph *can* determine
    never meets it however empty the record is.
    """

    import inspect

    from engine.mechanics.compiler import compiler as compiler_module

    source = inspect.getsource(compiler_module.MechanicsCompiler)
    # The predicate is reachable only as a refinement of `underdetermined`.
    assert "elif underdetermined and _names_no_mechanism(safe_ir):" in source
    assert source.count("_names_no_mechanism(") == 1


def test_the_predicate_reads_only_container_emptiness() -> None:
    """No role, subject, label, value, or identity is consulted."""

    import inspect

    from engine.mechanics.compiler.compiler import (
        _MECHANISM_RECORDS,
        _names_no_mechanism,
    )

    assert set(_MECHANISM_RECORDS) == {
        "interactions",
        "geometry",
        "constraints",
        "assumptions",
        "reference_frames",
        "points",
        "state_conditions",
    }
    body = inspect.getsource(_names_no_mechanism)
    statement = body.split('"""')[-1]
    for forbidden in (
        "role",
        "subject",
        "label",
        "family",
        "case_id",
        "si_value",
        "raw_value",
        "problem_text",
        "expected",
    ):
        assert forbidden not in statement, forbidden

    class _Empty:
        interactions = geometry = constraints = ()
        assumptions = reference_frames = points = state_conditions = ()

    class _One(_Empty):
        interactions = ("anything",)

    assert _names_no_mechanism(_Empty())
    assert not _names_no_mechanism(_One())


# ---------------------------------------------------------------------------
# Nothing outside the typed record is authority.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "why"),
    (
        ({"family": "rocket_propulsion"}, "family is not authority"),
        ({"family": "gyroscope_precession"}, "neither is a different family"),
        ({"case_id": "fx_public_dev_0001"}, "case identity is not authority"),
        ({"parse_status": "complete"}, "parse_status is not authority"),
        (
            {"future_terminal": "accepted"},
            "the expected terminal is not authority",
        ),
        (
            {"expected_failure_codes": ["requires_specialized_model"]},
            "the expected failure code is not authority",
        ),
        ({"fake_answer": 999999.0}, "the expected answer is not authority"),
        (
            {"text_prefix": "로켓이 연료를 분사한다. "},
            "problem text is not authority",
        ),
        (
            {"text_prefix": "이 문제는 지원되지 않는다. "},
            "nor is text that names the outcome",
        ),
        ({"body_label": "로켓"}, "an entity label is not authority"),
        ({"body_label": "팽이"}, "nor is a different label"),
        ({"reverse": True}, "source order is not authority"),
    ),
)
def test_only_the_typed_structure_decides_the_refusal(
    overrides: dict, why: str
) -> None:
    baseline = _run(_case(), "b19-authority-baseline")
    result = _run(_case(**overrides), f"b19-authority-{sorted(overrides)}")
    assert result.terminal is baseline.terminal, why
    assert result.terminal is LaneBTerminal.compiler_unsupported
    assert result.answer_value_si is None
    assert set(result.compiler_codes) == set(baseline.compiler_codes)


@pytest.mark.parametrize("shape", ("rotational", "variable_mass"))
def test_the_refusal_never_emits_a_number(shape: str) -> None:
    """No numeric answer, no candidate, no verified candidate — on either shape."""

    result = _run(_case(shape=shape), f"b19-no-number-{shape}")
    assert result.answer_value_si is None
    assert result.candidate_count == 0
    assert result.verified_candidate_count == 0
    assert result.terminal is LaneBTerminal.compiler_unsupported
