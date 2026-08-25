"""Stage 7: the neutral terminals a source-grounded Draft must be able to reach.

Four outcomes are *not* engine failures.  They are decisions the engine is
entitled to make and must make from typed structure alone:

* `verified_unsupported` — the engine proved from its own declared capability
  that a readout is outside the course scope.  The proof is a compiler issue
  code, never a family label, a case ID, or a corpus split.
* `needs_confirmation` — the source leaves a typed choice open that a *reader*
  must settle.  Two are covered here: an unresolved friction regime on a
  sliding support contact, and a signed-component query whose supporting
  quantity leaves its direction uncommitted.
* `insufficient_information` — the source relates nothing at all, so no reader
  decision would help either.
* `needs_figure` — already covered by the projection contract suite.

Every fixture in this file is independently authored.  No public-corpus or
held-out sentence, number, quote, or answer is copied, and nothing here is used
as a prompt example.
"""

from __future__ import annotations

import pytest

from engine.mechanics.compiler.contracts import (
    COURSE_SCOPE_DEFERRED_ISSUE_CODES,
    CompilerIssueCode,
)
from engine.mechanics.validation import ValidationTerminal, validate_draft
from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import (
    DraftProjectionReason,
    DraftProjectionTerminal,
    project_case_to_draft,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
)
from support.phase56_stage7_corpus_fixtures import build_case


# --------------------------------------------------------------------------
# Independently authored fixtures
# --------------------------------------------------------------------------


def _case(problem_text: str, gold: dict) -> PublicCorpusCaseV1:
    record = build_case(
        index=5,
        split="public_dev",
        family="constant_acceleration_1d",
        future_terminal="accepted",
        with_answer=False,
    )
    record["split"] = PublicSplit.public_dev
    record["problem_text"] = problem_text
    record["gold"] = {**record["gold"], **gold, "answers": []}
    return PublicCorpusCaseV1(**record)


def _fact(role, key, value, unit, quote, subject, **overrides) -> dict:
    fact = {
        "role": role,
        "semantic_key": key,
        "raw_value": value,
        "raw_unit": unit,
        "evidence_quote": quote,
        "subject_role": subject,
        "segment_role": "motion_1",
        "event_role": None,
        "temporal_role": "timeless",
        "direction": "not_applicable",
        "relevance": "solver_input",
        "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    }
    fact.update(overrides)
    return fact


SPRING_TEXT = (
    "받침대 위 미끄럼 없는 판에서 진동하는 부품이 있다. "
    "부품의 질량은 4 kg 이고 용수철 상수는 400 N/m 이다. "
    "마찰은 없다고 본다. 진동 주기를 구하시오."
)


def _spring_gold(**overrides) -> dict:
    gold = {
        "entities": [
            {"role": "part", "kind": "block", "label": "부품"},
            {"role": "coil", "kind": "spring", "label": "용수철"},
            {"role": "deck", "kind": "surface", "label": "판"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["part", "coil"],
                "motion_model": "spring_oscillation",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "release",
                "subject_roles": ["part", "coil"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact("mass", "mass", "4", "kg", "질량은 4 kg", "part"),
            _fact(
                "k", "spring_constant", "400", "N/m", "용수철 상수는 400 N/m", "coil"
            ),
        ],
        "relations": [
            {
                "role": "spring_link",
                "kind": "attached_to_spring",
                "participant_roles": ["part", "coil"],
                "segment_role": "motion_1",
            },
            {
                "role": "deck_link",
                "kind": "slides_on",
                "participant_roles": ["part", "deck"],
                "segment_role": "motion_1",
            },
        ],
        "assumption_proposals": [
            {
                "role": "no_friction",
                "kind": "frictionless",
                "subject_role": "part",
                "segment_role": "motion_1",
                "supporting_quote": "마찰은 없다고 본다",
                "server_value_only": True,
            }
        ],
        "queries": [
            {
                "role": "q1",
                "output_key": "period",
                "subject_role": "part",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }
    gold.update(overrides)
    return gold


def _spring_case(**overrides) -> PublicCorpusCaseV1:
    return _case(SPRING_TEXT, _spring_gold(**overrides))


def _projected(case: PublicCorpusCaseV1):
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projected, (
        projection.sanitized_reason
    )
    return projection


def _run(case: PublicCorpusCaseV1):
    return run_lane_b_case(
        project_case_to_draft(case), execution_token=deterministic_token(0)
    )


# --------------------------------------------------------------------------
# A. Deferred capability: the engine's own proof, not a label
# --------------------------------------------------------------------------


def test_a_declared_oscillation_yields_one_approved_readout_authority():
    projection = _projected(_spring_case())
    authorities = [
        item
        for item in projection.draft.assumptions
        if item.kind == "angular_natural_frequency"
        and item.subject_id == "part"
    ]
    assert len(authorities) == 1
    assert authorities[0].assumption_id in projection.approvable_assumption_ids
    # The authority names a regime; it never supplies a number.
    assert authorities[0].proposed_value is None
    assert authorities[0].proposed_unit is None


def test_a_stiffness_binds_to_the_body_the_spring_acts_on():
    projection = _projected(_spring_case())
    stiffness = [
        item for item in projection.draft.quantities if item.role.value == "stiffness"
    ]
    assert len(stiffness) == 1
    # The engine's accepted convention subjects a spring constant to the
    # oscillating body, and the interaction that licensed the binding owns it.
    assert stiffness[0].subject_id == "part"
    assert stiffness[0].raw_value == "400"
    springs = [
        item
        for item in projection.draft.interactions
        if item.kind.value == "spring"
    ]
    assert len(springs) == 1
    assert stiffness[0].quantity_id in springs[0].quantity_ids


def test_a_stiffness_with_two_candidate_owners_fails_closed():
    case = _spring_case(
        relations=[
            {
                "role": "spring_link",
                "kind": "attached_to_spring",
                "participant_roles": ["part", "coil"],
                "segment_role": "motion_1",
            },
            {
                "role": "spring_link_2",
                "kind": "attached_to_spring",
                "participant_roles": ["deck", "coil"],
                "segment_role": "motion_1",
            },
        ],
    )
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert (
        DraftProjectionReason.interaction_owner_ambiguous.value
        in (projection.sanitized_reason or "")
    )


def test_a_stiffness_whose_only_counterpart_is_not_a_body_fails_closed():
    case = _spring_case(
        relations=[
            {
                "role": "spring_link",
                "kind": "attached_to_spring",
                "participant_roles": ["deck", "coil"],
                "segment_role": "motion_1",
            },
        ],
    )
    projection = project_case_to_draft(case)
    assert projection.terminal is DraftProjectionTerminal.projection_rejected
    assert (
        DraftProjectionReason.interaction_owner_ambiguous.value
        in (projection.sanitized_reason or "")
    )


def test_a_complete_spring_readout_is_verified_unsupported_with_a_typed_code():
    result = _run(_spring_case())
    assert result.terminal is LaneBTerminal.verified_unsupported
    codes = {CompilerIssueCode(code) for code in result.compiler_codes}
    assert codes & COURSE_SCOPE_DEFERRED_ISSUE_CODES
    assert (
        CompilerIssueCode.free_linear_vibration_readout_deferred
        in codes
    )
    # A deferred readout delivers nothing: no answer, no candidate, no root.
    assert result.answer_value_si is None
    assert result.candidate_count == 0
    assert result.verified_candidate_count == 0
    assert result.equation_count == 0


@pytest.mark.parametrize(
    "field, value",
    [
        ("family", "constant_acceleration_1d"),
        ("family", None),
        ("case_id", "zz_tampered_0001"),
    ],
)
def test_a_deferred_terminal_is_invariant_to_family_and_case_id(field, value):
    baseline = _run(_spring_case())
    tampered = _run(_spring_case().model_copy(update={field: value}))
    assert tampered.terminal is baseline.terminal
    assert tampered.compiler_codes == baseline.compiler_codes


# --------------------------------------------------------------------------
# B. Needs confirmation: an unresolved friction regime
# --------------------------------------------------------------------------


FRICTION_TEXT = (
    "거친 수평 바닥 위의 짐칸이 오른쪽으로 밀린다. "
    "짐칸의 질량은 12 kg 이고 미는 힘은 60 N 이다. "
    "가속도의 크기를 구하시오."
)


def _friction_gold(**overrides) -> dict:
    gold = {
        "entities": [
            {"role": "crate", "kind": "block", "label": "짐칸"},
            {"role": "floor", "kind": "surface", "label": "바닥"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["crate"],
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": None,
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["crate"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact("mass", "mass", "12", "kg", "질량은 12 kg", "crate"),
            _fact(
                "push",
                "force",
                "60",
                "N",
                "미는 힘은 60 N",
                "crate",
                direction="right",
            ),
        ],
        "relations": [
            {
                "role": "floor_link",
                "kind": "slides_on",
                "participant_roles": ["crate", "floor"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "crate",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }
    gold.update(overrides)
    return gold


def _friction_case(**overrides) -> PublicCorpusCaseV1:
    return _case(FRICTION_TEXT, _friction_gold(**overrides))


def test_b_unresolved_sliding_friction_regime_is_a_blocking_ambiguity():
    projection = _projected(_friction_case())
    blocking = [item for item in projection.draft.ambiguities if item.blocking]
    assert len(blocking) == 1
    assert blocking[0].kind.value == "assumption"
    validation = validate_draft(
        projection.problem_text,
        projection.draft,
        approved_assumption_ids=projection.approvable_assumption_ids,
    )
    assert validation.terminal is ValidationTerminal.needs_confirmation


def test_b_unresolved_friction_regime_reaches_needs_confirmation_with_no_answer():
    result = _run(_friction_case())
    assert result.terminal is LaneBTerminal.needs_confirmation
    assert result.answer_value_si is None
    assert result.candidate_count == 0
    assert result.verified_candidate_count == 0


def test_b_a_stated_coefficient_resolves_the_regime():
    text = FRICTION_TEXT.replace(
        "가속도의 크기를", "운동마찰계수는 0.25 이다. 가속도의 크기를"
    )
    gold = _friction_gold()
    gold["explicit_facts"] = [
        *gold["explicit_facts"],
        _fact(
            "mu",
            "coefficient_of_friction",
            "0.25",
            "",
            "운동마찰계수는 0.25",
            "crate",
        ),
    ]
    projection = _projected(_case(text, gold))
    assert not [item for item in projection.draft.ambiguities if item.blocking]


def test_b_a_declared_frictionless_regime_resolves_the_contact():
    text = FRICTION_TEXT.replace(
        "가속도의 크기를", "마찰은 무시한다. 가속도의 크기를"
    )
    gold = _friction_gold(
        assumption_proposals=[
            {
                "role": "no_friction",
                "kind": "frictionless",
                "subject_role": "crate",
                "segment_role": "motion_1",
                "supporting_quote": "마찰은 무시한다",
                "server_value_only": True,
            }
        ]
    )
    projection = _projected(_case(text, gold))
    assert not [item for item in projection.draft.ambiguities if item.blocking]


def test_b_a_system_scoped_frictionless_regime_resolves_its_bodies():
    text = FRICTION_TEXT.replace(
        "가속도의 크기를", "전체 계에서 마찰은 무시한다. 가속도의 크기를"
    )
    gold = _friction_gold()
    gold["entities"] = [
        *gold["entities"],
        {"role": "whole", "kind": "system", "label": "전체 계"},
    ]
    gold["assumption_proposals"] = [
        {
            "role": "no_friction",
            "kind": "frictionless",
            "subject_role": "whole",
            "segment_role": None,
            "supporting_quote": "전체 계에서 마찰은 무시한다",
            "server_value_only": True,
        }
    ]
    projection = _projected(_case(text, gold))
    assert not [item for item in projection.draft.ambiguities if item.blocking]


def test_b_a_point_lying_on_a_body_is_not_a_support_contact():
    """Negative control: `lies_on` alone must not imply a friction regime."""

    text = (
        "회전하는 팔의 끝점 P 를 살펴본다. 팔의 반지름은 0.4 m 이고 "
        "각속도는 3 rad/s 이다. 점 P 의 접선속도 크기를 구하시오."
    )
    gold = {
        "entities": [
            {"role": "arm", "kind": "rigid_body", "label": "팔"},
            {"role": "tip", "kind": "point", "label": "끝점 P"},
        ],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["arm"],
                "motion_model": "fixed_axis_rotation",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": None,
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["arm"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact("radius", "radius", "0.4", "m", "반지름은 0.4 m", "arm"),
            _fact(
                "omega",
                "angular_velocity",
                "3",
                "rad/s",
                "각속도는 3 rad/s",
                "arm",
            ),
        ],
        "relations": [
            {
                "role": "tip_link",
                "kind": "point_on_body",
                "participant_roles": ["tip", "arm"],
                "segment_role": "motion_1",
            }
        ],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "tangential_velocity",
                "subject_role": "arm",
                "segment_role": "motion_1",
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }
    projection = _projected(_case(text, gold))
    assert not [item for item in projection.draft.ambiguities if item.blocking]


# --------------------------------------------------------------------------
# C. Needs confirmation: an uncommitted direction under a signed query
# --------------------------------------------------------------------------


DIRECTION_TEXT = (
    "어떤 부품에 크기 30 N 의 알짜힘이 작용한다. 힘의 방향은 적혀 있지 않다. "
    "부품의 질량은 5 kg 이다. x 방향 가속도를 구하시오."
)


def _direction_gold(*, force_direction: str, component: str) -> dict:
    return {
        "entities": [{"role": "part", "kind": "particle", "label": "부품"}],
        "motion_segments": [
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["part"],
                "motion_model": "unknown",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": None,
            }
        ],
        "events": [
            {
                "role": "start",
                "kind": "start",
                "subject_roles": ["part"],
                "segment_role": "motion_1",
                "evidence_quote": None,
            }
        ],
        "explicit_facts": [
            _fact("mass", "mass", "5", "kg", "질량은 5 kg", "part"),
            _fact(
                "net",
                "force",
                "30",
                "N",
                "크기 30 N 의 알짜힘",
                "part",
                direction=force_direction,
            ),
        ],
        "relations": [],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "acceleration",
                "subject_role": "part",
                "segment_role": "motion_1",
                "component": component,
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }


def test_c_a_signed_query_over_an_uncommitted_direction_is_a_blocking_ambiguity():
    case = _case(
        DIRECTION_TEXT,
        _direction_gold(force_direction="unspecified", component="x"),
    )
    projection = _projected(case)
    blocking = [item for item in projection.draft.ambiguities if item.blocking]
    assert len(blocking) == 1
    assert blocking[0].kind.value == "direction"
    result = _run(case)
    assert result.terminal is LaneBTerminal.needs_confirmation
    assert result.answer_value_si is None


def test_c_a_stated_direction_needs_no_confirmation():
    case = _case(
        DIRECTION_TEXT.replace("적혀 있지 않다", "오른쪽이다"),
        _direction_gold(force_direction="right", component="x"),
    )
    projection = _projected(case)
    assert not [item for item in projection.draft.ambiguities if item.blocking]


def test_c_a_magnitude_query_needs_no_direction_confirmation():
    case = _case(
        DIRECTION_TEXT.replace("x 방향 가속도", "가속도의 크기"),
        _direction_gold(force_direction="unspecified", component="magnitude"),
    )
    projection = _projected(case)
    assert not [item for item in projection.draft.ambiguities if item.blocking]


def test_c_an_unrelated_subject_cannot_raise_a_direction_ambiguity():
    """A quantity belonging to another subject must not block this query."""

    text = (
        "두 부품이 있다. 첫 부품의 질량은 5 kg 이고 오른쪽으로 30 N 을 받는다. "
        "둘째 부품에는 크기 8 N 의 힘이 작용하며 방향은 적혀 있지 않다. "
        "첫 부품의 x 방향 가속도를 구하시오."
    )
    gold = _direction_gold(force_direction="right", component="x")
    gold["entities"] = [
        {"role": "part", "kind": "particle", "label": "첫 부품"},
        {"role": "other", "kind": "particle", "label": "둘째 부품"},
    ]
    gold["explicit_facts"] = [
        _fact("mass", "mass", "5", "kg", "질량은 5 kg", "part"),
        _fact(
            "net",
            "force",
            "30",
            "N",
            "오른쪽으로 30 N",
            "part",
            direction="right",
        ),
        _fact(
            "stray",
            "force",
            "8",
            "N",
            "크기 8 N 의 힘",
            "other",
            direction="unspecified",
            segment_role=None,
            relevance="context_only",
        ),
    ]
    gold["motion_segments"][0]["actor_roles"] = ["part", "other"]
    gold["events"][0]["subject_roles"] = ["part", "other"]
    projection = _projected(_case(text, gold))
    assert not [item for item in projection.draft.ambiguities if item.blocking]


# --------------------------------------------------------------------------
# D. Insufficient information: nothing is related at all
# --------------------------------------------------------------------------


EMPTY_TEXT = "어떤 물체가 직선 위를 지난다. 이동 거리는 18 m 이다. 걸린 시간을 구하시오."


def _empty_gold(**overrides) -> dict:
    gold = {
        "entities": [{"role": "thing", "kind": "particle", "label": "물체"}],
        "motion_segments": [],
        "events": [],
        "explicit_facts": [
            _fact(
                "distance",
                "distance",
                "18",
                "m",
                "이동 거리는 18 m",
                "thing",
                segment_role=None,
            )
        ],
        "relations": [],
        "assumption_proposals": [],
        "queries": [
            {
                "role": "q1",
                "output_key": "time",
                "subject_role": "thing",
                "segment_role": None,
                "component": "magnitude",
                "event_role": None,
            }
        ],
        "expected_failure_codes": [],
    }
    gold.update(overrides)
    return gold


def test_d_a_draft_that_relates_nothing_is_insufficient_information():
    projection = project_case_to_draft(_case(EMPTY_TEXT, _empty_gold()))
    assert projection.terminal is DraftProjectionTerminal.insufficient_information
    # A blocked pre-runtime terminal carries no Draft into the runtime.
    assert projection.draft is None
    result = _run(_case(EMPTY_TEXT, _empty_gold()))
    assert result.terminal is LaneBTerminal.insufficient_information
    assert result.answer_value_si is None
    assert result.equation_count == 0


def test_d_one_related_interval_is_enough_to_leave_insufficient_information():
    text = EMPTY_TEXT.replace("걸린 시간을", "일정한 속력으로 지난다. 걸린 시간을")
    gold = _empty_gold(
        motion_segments=[
            {
                "role": "motion_1",
                "order": 1,
                "actor_roles": ["thing"],
                "motion_model": "constant_velocity_1d",
                "relevance": "target",
                "start_event_role": "start",
                "end_event_role": "finish",
            }
        ],
    )
    gold["queries"][0]["segment_role"] = "motion_1"
    gold["explicit_facts"][0]["segment_role"] = "motion_1"
    projection = project_case_to_draft(_case(text, gold))
    assert projection.terminal is DraftProjectionTerminal.projected


def test_d_insufficient_information_is_invariant_to_family_and_case_id():
    baseline = _run(_case(EMPTY_TEXT, _empty_gold()))
    for field, value in (
        ("family", "spring_mass_vibration"),
        ("case_id", "zz_other_0002"),
    ):
        tampered = _run(
            _case(EMPTY_TEXT, _empty_gold()).model_copy(update={field: value})
        )
        assert tampered.terminal is baseline.terminal
