"""Stage 7 Lane B runner: per-stage terminals and privacy-safe results."""

from __future__ import annotations

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_draft_projection import project_case_to_draft
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case,
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


def test_tokens_are_opaque_and_carry_no_case_identity() -> None:
    case = _case()
    first = deterministic_token(0)
    second = deterministic_token(1)
    assert first != second
    assert len(first) == 32
    assert case.case_id not in first
    assert (case.family or "") not in first


def test_needs_figure_never_reaches_the_pipeline() -> None:
    case = _case()
    blocked = case.model_copy(
        update={
            "gold": case.gold.model_copy(
                update={
                    "figure_dependency": case.gold.figure_dependency.model_copy(
                        update={"level": "required"}
                    )
                }
            )
        }
    )
    result = run_lane_b_case(
        project_case_to_draft(blocked), execution_token=deterministic_token(0)
    )
    assert result.terminal is LaneBTerminal.needs_figure
    assert result.answer_value_si is None
    assert result.candidate_count == 0


def test_result_is_frozen_and_privacy_safe() -> None:
    case = _case()
    result = run_lane_b_case(
        project_case_to_draft(case), execution_token=deterministic_token(0)
    )
    import dataclasses

    assert dataclasses.is_dataclass(result)
    payload = repr(result)
    assert case.case_id not in payload
    assert case.problem_text[:12] not in payload
    assert (case.family or "zzz") not in payload
    for answer in case.gold.answers:
        assert repr(answer.numeric) not in payload
        assert (answer.reference_expression or "zzz") not in payload


def test_every_stage_has_its_own_terminal_and_none_is_a_catch_all() -> None:
    values = {item.value for item in LaneBTerminal}
    assert "runtime_failure" not in values
    for expected in (
        "validation_rejected",
        "normalization_rejected",
        "authorization_failed",
        "compiler_unsupported",
        "compiler_failure",
        "solve_rejected",
        "verification_rejected",
        "solved",
        "verified_unsupported",
        "needs_figure",
        "needs_confirmation",
        "insufficient_information",
    ):
        assert expected in values


def test_a_solved_result_requires_exactly_one_verified_candidate() -> None:
    result = run_lane_b_case(
        project_case_to_draft(_case()), execution_token=deterministic_token(0)
    )
    if result.terminal is LaneBTerminal.solved:
        assert result.verified_candidate_count == 1
        assert result.answer_value_si is not None
    else:
        assert result.answer_value_si is None
