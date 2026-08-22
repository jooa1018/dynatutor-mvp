"""Direct tests for the Stage 7 offline gate runner and its case-level scorer.

The gate runner decides whether Stage 7 is accepted, so its own decision logic
needs the same scrutiny as the engine it measures.  Until now the runner was
only exercised end-to-end, which meant its summary parsing, its subprocess
failure handling, its scorer error path, and above all *the shape of its strict
acceptance conditions* were never tested directly — and a gate that is wrong
about what "pass" means will happily certify a Stage 7 that has not happened.

Every case here is independently authored.  Nothing reads the authorised public
archive, so the whole file runs in corpus-independent CI.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from evaluation.phase56_stage7.contracts import (
    Stage7ExpectedTerminal,
    stage7_evaluation_contract,
)
from evaluation.phase56_stage7.corpus_records import parse_public_jsonl, parse_schema_document
from evaluation.phase56_stage7.gold_domain import PublicSplit
from evaluation.phase56_stage7.lane_b_runner import LaneBResult, LaneBTerminal
from evaluation.phase56_stage7 import lane_b_scoring
from evaluation.phase56_stage7.lane_b_scoring import (
    ScoringFailure,
    ScoringFailureReason,
    score_lane_b_cases,
)

from tests.support.phase56_stage7_corpus_fixtures import (
    build_public_adversarial_records,
    build_public_dev_records,
    jsonl_bytes,
    schema_bytes,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPOSITORY_ROOT / "backend" / "tools" / "run_phase56_stage7_offline_gate.py"


def _load_gate_module() -> Any:
    """Import the runner as a module so its internals can be tested directly."""

    spec = importlib.util.spec_from_file_location("stage7_offline_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass(slots=True)` rebuilds the class and looks its module up in
    # `sys.modules`, so the entry has to exist before the module body runs.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate_module()


def _measured_registry(
    *, measured: int = 23, unbound: int = 0, nonzero: int = 0
) -> dict[str, Any]:
    """A per-signal registry summary, supplied rather than measured.

    The tests below exercise the *counter* half of hard safety, so they hand in
    a fully-measured registry instead of running the thirty-seven bound attack
    nodes once per assertion.  The registry half has its own tests, which vary
    these numbers and check the gate reacts.
    """

    return {
        "registry_version": "test-supplied",
        "per_signal_instrument_registry": "IMPLEMENTED",
        "signal_count": 23,
        "measured_signal_count": measured,
        "unbound_signal_count": unbound,
        "nonzero_signal_count": nonzero,
        "signals": [],
    }


# ---------------------------------------------------------------------------
# Fixture corpus, in memory only.
# ---------------------------------------------------------------------------


def _fixture_cases() -> tuple[Any, ...]:
    declared = parse_schema_document(schema_bytes())
    dev = parse_public_jsonl(
        jsonl_bytes(build_public_dev_records()),
        split=PublicSplit.public_dev,
        declared_schema=declared,
    )
    adversarial = parse_public_jsonl(
        jsonl_bytes(build_public_adversarial_records()),
        split=PublicSplit.public_adversarial,
        declared_schema=declared,
    )
    return (*dev, *adversarial)


def _expected_terminals(cases: tuple[Any, ...]) -> list[Stage7ExpectedTerminal]:
    from evaluation.phase56_stage7.corpus_semantics import (
        scope_adjusted_expected_terminal,
    )

    return [
        scope_adjusted_expected_terminal(case, case_index=index)
        for index, case in enumerate(cases)
    ]


def _solved_record(case: Any, *, offset: float = 0.0) -> LaneBResult:
    """A perfect solved runtime record for a supported fixture case."""

    answer = case.gold.answers[0]
    return LaneBResult(
        execution_token="t" * 32,
        terminal=LaneBTerminal.solved,
        compiler_status="compiled",
        solve_terminal="solved",
        applied_law_ids=("newton_second_law",),
        equation_count=1,
        candidate_count=1,
        verified_candidate_count=1,
        verification_checks=(
            ("equation_residual", "passed"),
            ("unit_consistency", "passed"),
            ("query_binding", "passed"),
            ("source_evidence", "passed"),
        ),
        answer_value_si=answer.numeric + offset,
        answer_query_symbol_id="q_force",
        answer_unit=answer.unit,
        answer_component="magnitude",
        query_subject_id="e_box",
    )


def _deferred_record() -> LaneBResult:
    return LaneBResult(
        execution_token="t" * 32,
        terminal=LaneBTerminal.verified_unsupported,
        compiler_status="unsupported",
        compiler_codes=("free_linear_vibration_readout_deferred",),
    )


def _unsupported_other_record() -> LaneBResult:
    return LaneBResult(
        execution_token="t" * 32,
        terminal=LaneBTerminal.verified_unsupported,
        compiler_status="unsupported",
        compiler_codes=("requires_specialized_model",),
    )


def _blocked_record(terminal: LaneBTerminal) -> LaneBResult:
    return LaneBResult(execution_token="t" * 32, terminal=terminal)


def _perfect_records(cases: tuple[Any, ...]) -> list[LaneBResult]:
    """The record set a fully accepted Stage 7 would produce."""

    records: list[LaneBResult] = []
    for case, expected in zip(cases, _expected_terminals(cases)):
        if expected is Stage7ExpectedTerminal.accepted:
            records.append(_solved_record(case))
        elif expected is Stage7ExpectedTerminal.deferred_unsupported:
            records.append(_deferred_record())
        elif expected is Stage7ExpectedTerminal.unsupported_other:
            records.append(_unsupported_other_record())
        elif expected is Stage7ExpectedTerminal.needs_figure:
            records.append(_blocked_record(LaneBTerminal.needs_figure))
        elif expected is Stage7ExpectedTerminal.needs_confirmation:
            records.append(_blocked_record(LaneBTerminal.needs_confirmation))
        else:
            records.append(_blocked_record(LaneBTerminal.insufficient_information))
    return records


# ---------------------------------------------------------------------------
# The scorer scores the frozen distribution, not "everything solved".
# ---------------------------------------------------------------------------


def test_perfect_run_matches_the_frozen_distribution() -> None:
    cases = _fixture_cases()
    scorecard = score_lane_b_cases(cases, _perfect_records(cases))
    expected = stage7_evaluation_contract().expected_terminals

    assert scorecard.total_cases == 100
    assert scorecard.supported_expected == expected.supported_accepted == 81
    assert scorecard.supported_correct == 81
    assert scorecard.supported_wrong == 0
    assert scorecard.supported_unscored == 0
    assert scorecard.deferred_matched == expected.deferred_unsupported == 12
    assert scorecard.unsupported_other_matched == expected.unsupported_other == 2
    assert scorecard.needs_figure_matched == expected.needs_figure == 2
    assert scorecard.needs_confirmation_matched == expected.needs_confirmation == 2
    assert (
        scorecard.insufficient_information_matched
        == expected.insufficient_information
        == 1
    )
    assert scorecard.terminal_mapping_accuracy == 1.0
    assert scorecard.answer_accuracy == 1.0
    assert gate._distribution_matched(scorecard) is True


def test_solving_every_case_is_not_acceptance() -> None:
    """The historic defect: demanding every executed case be solved.

    Solving the 19 cases that must stay blocked is a *worse* Stage 7, not a
    better one, and the gate has to say so.
    """

    cases = _fixture_cases()
    records = [_solved_record(case) if case.gold.answers else _solved_record_without_answer() for case in cases]
    scorecard = score_lane_b_cases(cases, records)

    assert scorecard.deferred_silent_solves == 12
    assert gate._distribution_matched(scorecard) is False


def _solved_record_without_answer() -> LaneBResult:
    return LaneBResult(
        execution_token="t" * 32,
        terminal=LaneBTerminal.solved,
        verified_candidate_count=1,
        answer_value_si=1.0,
        answer_unit="N",
    )


def test_one_deferred_case_accidentally_solved_fails() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    deferred_index = next(
        index
        for index, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.deferred_unsupported
    )
    records[deferred_index] = _solved_record(cases[deferred_index])

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.deferred_silent_solves == 1
    assert scorecard.deferred_matched == 11
    assert gate._distribution_matched(scorecard) is False


def test_one_supported_case_accidentally_unsupported_fails() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    supported_index = next(
        index
        for index, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.accepted
    )
    records[supported_index] = _deferred_record()

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.supported_downgraded_to_unsupported == 1
    assert scorecard.supported_correct == 80
    assert scorecard.supported_unscored == 1
    assert gate._distribution_matched(scorecard) is False


def test_unsupported_other_may_not_borrow_deferred_evidence() -> None:
    """The two blocked-unsupported classes are separated by their evidence."""

    cases = _fixture_cases()
    records = _perfect_records(cases)
    other_index = next(
        index
        for index, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.unsupported_other
    )
    records[other_index] = _deferred_record()

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.unsupported_other_matched == 1
    assert dict(scorecard.blocked_defect_counts).get(
        "unsupported_other_used_deferred_evidence"
    ) == 1
    assert gate._distribution_matched(scorecard) is False


def test_deferred_case_needs_typed_capability_evidence() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    deferred_index = next(
        index
        for index, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.deferred_unsupported
    )
    records[deferred_index] = _unsupported_other_record()

    scorecard = score_lane_b_cases(cases, records)
    assert dict(scorecard.blocked_defect_counts).get("deferred_evidence_missing") == 1
    assert gate._distribution_matched(scorecard) is False


# ---------------------------------------------------------------------------
# Tolerance is the corpus's declaration, exactly.
# ---------------------------------------------------------------------------


def test_answer_just_inside_the_declared_tolerance_is_correct() -> None:
    """The declared tolerance is usable up to its edge.

    The edge is approached rather than hit exactly: `(a + t) - a == t` does not
    hold in binary floating point, so an exactly-on-the-boundary assertion
    would test the representation, not the contract.  Fail-closed at the last
    representable step is the behaviour we want and the behaviour asserted.
    """

    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.accepted
    )
    tolerance = cases[index].gold.answers[0].tolerance_abs
    records[index] = _solved_record(cases[index], offset=tolerance * 0.999)

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.supported_correct == 81
    assert scorecard.supported_wrong == 0


def test_answer_just_outside_the_declared_tolerance_is_wrong() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.accepted
    )
    tolerance = cases[index].gold.answers[0].tolerance_abs
    records[index] = _solved_record(cases[index], offset=tolerance * 1.0001)

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.supported_wrong == 1
    assert gate._distribution_matched(scorecard) is False


def test_scorer_does_not_widen_a_tighter_corpus_tolerance() -> None:
    """The removed 1e-6 relative floor must not come back.

    A corpus that declares 1e-9 gets 1e-9.  With the old floor, an error of
    1e-6 * |expected| scored as correct however tight the declaration was.
    """

    cases = list(_fixture_cases())
    records = _perfect_records(tuple(cases))
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(tuple(cases)))
        if expected is Stage7ExpectedTerminal.accepted
    )
    case = cases[index]
    answer = case.gold.answers[0]
    tightened = answer.model_copy(update={"tolerance_abs": 1.0e-9})
    gold = case.gold.model_copy(update={"answers": (tightened,)})
    cases[index] = case.model_copy(update={"gold": gold})

    floor_sized_error = 1.0e-6 * max(1.0, abs(answer.numeric))
    records[index] = _solved_record(cases[index], offset=floor_sized_error)

    scorecard = score_lane_b_cases(tuple(cases), records)
    assert scorecard.supported_wrong == 1


def test_wrong_dimension_is_never_a_correct_answer() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.accepted
    )
    record = _solved_record(cases[index])
    records[index] = LaneBResult(
        **{
            **{
                field: getattr(record, field)
                for field in record.__dataclass_fields__
                if field != "answer_unit"
            },
            "answer_unit": "m/s",
        }
    )

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.supported_wrong == 1
    assert scorecard.unit_dimension_accuracy < 1.0
    assert dict(scorecard.supported_defect_counts).get("unit_dimension_mismatch") == 1


# ---------------------------------------------------------------------------
# Unscored is a failure, not an abstention.
# ---------------------------------------------------------------------------


def test_unscored_supported_output_fails_the_strict_gate() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.accepted
    )
    record = _solved_record(cases[index])
    records[index] = LaneBResult(
        **{
            **{
                field: getattr(record, field)
                for field in record.__dataclass_fields__
                if field != "answer_value_si"
            },
            "answer_value_si": None,
        }
    )

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.supported_unscored == 1
    # It reached `solved` and produced nothing comparable: a safety signal, not
    # a yield gap.
    assert scorecard.supported_solved_unscored == 1
    assert scorecard.supported_wrong == 0

    outcomes = _strict_outcomes(_report_with_scorecard(scorecard))
    assert outcomes["strict_unscored_zero"] == "FAIL"
    assert outcomes["strict_solved_but_unscored_zero"] == "FAIL"


def test_hard_safety_is_not_passed_by_an_unscored_solve() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.accepted
    )
    record = _solved_record(cases[index])
    records[index] = LaneBResult(
        **{
            **{
                field: getattr(record, field)
                for field in record.__dataclass_fields__
                if field != "answer_value_si"
            },
            "answer_value_si": None,
        }
    )
    scorecard = score_lane_b_cases(cases, records)
    report = _report_with_scorecard(scorecard)
    section = gate._hard_safety_section(report, [], registry_summary=_measured_registry())
    assert section["result"] == "FAIL"
    assert section["all_measured_zero"] is False
    # Every catalog signal now carries a named instrument, so the artifact
    # reports full coverage rather than the honest partial count it used to.
    assert section["measured_signal_count"] == 23
    assert section["signal_count"] == 23
    assert section["per_signal_instrument_registry"] == "IMPLEMENTED"


# ---------------------------------------------------------------------------
# Hard safety sees a fabricated answer in EVERY blocked class.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blocked_class",
    [
        Stage7ExpectedTerminal.needs_figure,
        Stage7ExpectedTerminal.needs_confirmation,
        Stage7ExpectedTerminal.insufficient_information,
        Stage7ExpectedTerminal.unsupported_other,
    ],
)
def test_hard_safety_fails_when_any_blocked_class_is_silently_solved(
    blocked_class: Stage7ExpectedTerminal,
) -> None:
    """Inventing a number for a problem that has none is a wrong solve.

    The frozen contract guarantees seven such cases. Measuring only the
    deferred class would let the other five fabricate answers while the
    artifact published `all_measured_zero`.
    """

    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is blocked_class
    )
    records[index] = LaneBResult(
        execution_token="t" * 32,
        terminal=LaneBTerminal.solved,
        verified_candidate_count=1,
        verification_checks=(("equation_residual", "passed"),),
        answer_value_si=42.0,
        answer_unit="m/s",
        answer_query_symbol_id="q",
        query_subject_id="e",
        answer_component="magnitude",
    )

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.blocked_silent_solves == 1
    assert scorecard.deferred_silent_solves == 0

    report = _report_with_scorecard(scorecard)
    section = gate._hard_safety_section(report, [], registry_summary=_measured_registry())
    assert section["result"] == "FAIL"
    assert section["all_measured_zero"] is False

    outcomes = _strict_outcomes(report)
    assert outcomes["strict_blocked_silent_solve_zero"] == "FAIL"


def test_hard_safety_fails_when_a_blocked_case_carries_a_number() -> None:
    """Right terminal, wrong payload — still a fabricated answer."""

    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.needs_figure
    )
    records[index] = LaneBResult(
        execution_token="t" * 32,
        terminal=LaneBTerminal.needs_figure,
        answer_value_si=7.0,
        answer_unit="m",
    )

    scorecard = score_lane_b_cases(cases, records)
    assert scorecard.blocked_numeric_answers == 1

    report = _report_with_scorecard(scorecard)
    assert gate._hard_safety_section(report, [], registry_summary=_measured_registry())["result"] == "FAIL"
    assert _strict_outcomes(report)["strict_blocked_numeric_answer_zero"] == "FAIL"


def test_hard_safety_fails_when_a_supported_case_is_downgraded() -> None:
    cases = _fixture_cases()
    records = _perfect_records(cases)
    index = next(
        i
        for i, expected in enumerate(_expected_terminals(cases))
        if expected is Stage7ExpectedTerminal.accepted
    )
    records[index] = _deferred_record()

    report = _report_with_scorecard(score_lane_b_cases(cases, records))
    assert gate._hard_safety_section(report, [], registry_summary=_measured_registry())["result"] == "FAIL"


def test_hard_safety_passes_on_a_perfect_run() -> None:
    """The negative controls above must not be passing for the wrong reason."""

    cases = _fixture_cases()
    report = _report_with_scorecard(
        score_lane_b_cases(cases, _perfect_records(cases))
    )
    section = gate._hard_safety_section(report, [], registry_summary=_measured_registry())
    assert section["result"] == "PASS"
    assert section["all_measured_zero"] is True


# ---------------------------------------------------------------------------
# The per-signal registry: an unexamined signal is never a zero.
# ---------------------------------------------------------------------------


def _perfect_report() -> dict[str, Any]:
    cases = _fixture_cases()
    return _report_with_scorecard(score_lane_b_cases(cases, _perfect_records(cases)))


def test_an_unmeasured_signal_fails_hard_safety_on_an_otherwise_perfect_run() -> None:
    """The whole point: seventeen unexamined properties are not seventeen zeros."""

    section = gate._hard_safety_section(
        _perfect_report(),
        [],
        registry_summary=_measured_registry(measured=6, unbound=17),
    )
    assert section["result"] == "FAIL"
    assert section["measured_signal_count"] == 6
    assert section["unbound_signal_count"] == 17


def test_a_violated_signal_fails_hard_safety_on_an_otherwise_perfect_run() -> None:
    section = gate._hard_safety_section(
        _perfect_report(), [], registry_summary=_measured_registry(nonzero=1)
    )
    assert section["result"] == "FAIL"
    assert section["nonzero_signal_count"] == 1


def test_the_registry_binds_every_catalog_signal_exactly_once() -> None:
    from evaluation.phase56_stage7.contracts import Stage7HardSafetySignal
    from evaluation.phase56_stage7.hard_safety_registry import REGISTRY

    bound = [item.signal for item in REGISTRY]
    assert len(bound) == len(set(bound)) == len(tuple(Stage7HardSafetySignal))
    assert set(bound) == set(Stage7HardSafetySignal)


def test_a_signal_whose_attack_did_not_run_reports_not_measured() -> None:
    from evaluation.phase56_stage7.hard_safety_registry import (
        bound_node_ids,
        measure_signals,
        summarize,
    )

    counters = {
        "wrong_solves": 0,
        "solved_but_unscored": 0,
        "blocked_numeric_answers": 0,
        "deferred_silent_solves": 0,
        "blocked_silent_solves": 0,
        "private_heldout_accesses": 0,
    }
    all_passed = {node: "PASSED" for node in bound_node_ids()}
    full = summarize(measure_signals(counters=counters, node_outcomes=all_passed))
    assert full["measured_signal_count"] == 23
    assert full["unbound_signal_count"] == 0
    assert full["nonzero_signal_count"] == 0

    # Drop a single attack and the signals resting on it stop being measured.
    starved = dict(all_passed)
    starved[
        "tests/test_phase56_stage7_hard_safety_instruments.py"
        "::test_no_log_record_carries_image_bytes_or_base64"
    ] = "NOT_RUN"
    partial = summarize(measure_signals(counters=counters, node_outcomes=starved))
    assert partial["measured_signal_count"] < 23
    assert partial["unbound_signal_count"] > 0

    # A failing attack is a violation, not a missing measurement.
    broken = dict(all_passed)
    broken[
        "tests/test_phase56_stage7_hard_safety_instruments.py"
        "::test_no_log_record_carries_raw_provider_output"
    ] = "FAILED"
    violated = summarize(measure_signals(counters=counters, node_outcomes=broken))
    assert violated["measured_signal_count"] == 23
    assert violated["nonzero_signal_count"] >= 1


def test_unsupported_other_is_reachable_by_a_correct_engine() -> None:
    """A class only `verified_unsupported` could satisfy was unsatisfiable.

    `verified_unsupported` is produced in the compiler path only when a
    course-scope deferred code is present — and that same code disqualifies
    `unsupported_other`.  An engine that correctly proves a problem out of scope
    at the compiler reaches `compiler_unsupported`, so before this fix the class
    could never match and `terminal_mapping` could never reach 100 %.
    """

    from evaluation.phase56_stage7.lane_b_scoring import _REQUIRED_TERMINALS

    accepted = _REQUIRED_TERMINALS[Stage7ExpectedTerminal.unsupported_other]
    assert LaneBTerminal.compiler_unsupported.value in accepted
    assert LaneBTerminal.verified_unsupported.value in accepted

    # The deferred class must NOT gain the same terminal, or the two classes
    # would stop being separable by evidence.
    deferred = _REQUIRED_TERMINALS[Stage7ExpectedTerminal.deferred_unsupported]
    assert LaneBTerminal.compiler_unsupported.value not in deferred


def test_compiler_unsupported_still_needs_a_typed_reason() -> None:
    """Reaching the terminal is not proving the refusal."""

    from evaluation.phase56_stage7.lane_b_scoring import BlockedDefect, _score_blocked

    defects: Counter[str] = Counter()
    bare = LaneBResult(
        "token", LaneBTerminal.compiler_unsupported, compiler_codes=()
    )
    assert not _score_blocked(
        Stage7ExpectedTerminal.unsupported_other, bare, defects
    )
    assert defects[BlockedDefect.unsupported_reason_missing.value] == 1

    reasoned = LaneBResult(
        "token",
        LaneBTerminal.compiler_unsupported,
        compiler_codes=("requires_specialized_model",),
    )
    assert _score_blocked(
        Stage7ExpectedTerminal.unsupported_other, reasoned, Counter()
    )


def test_compiler_unsupported_may_not_borrow_deferred_evidence() -> None:
    from evaluation.phase56_stage7.lane_b_scoring import (
        _DEFERRED_CODE_VALUES,
        BlockedDefect,
        _score_blocked,
    )

    defects: Counter[str] = Counter()
    borrowed = LaneBResult(
        "token",
        LaneBTerminal.compiler_unsupported,
        compiler_codes=(sorted(_DEFERRED_CODE_VALUES)[0],),
    )
    assert not _score_blocked(
        Stage7ExpectedTerminal.unsupported_other, borrowed, defects
    )
    assert (
        defects[BlockedDefect.unsupported_other_used_deferred_evidence.value] == 1
    )


def test_a_blocked_case_carrying_a_number_still_fails_on_the_new_terminal() -> None:
    from evaluation.phase56_stage7.lane_b_scoring import BlockedDefect, _score_blocked

    defects: Counter[str] = Counter()
    fabricated = LaneBResult(
        "token",
        LaneBTerminal.compiler_unsupported,
        compiler_codes=("requires_specialized_model",),
        answer_value_si=42.0,
    )
    assert not _score_blocked(
        Stage7ExpectedTerminal.unsupported_other, fabricated, defects
    )
    assert defects[BlockedDefect.numeric_answer_present.value] == 1


def test_one_authoritative_distribution_feeds_both_consumers() -> None:
    """The frozen 81/12/2/2/2/1 has exactly one home, and both readers use it.

    The corpus semantic preflight and the strict scorer each check the
    distribution.  If either carried its own hand-written copy the two could
    drift, and the gate would be comparing the corpus against one target while
    reporting acceptance against another.  Both read
    `stage7_evaluation_contract().expected_terminals`; this pins that, and pins
    that the counts cannot be satisfied by an internal sum alone.
    """

    import inspect

    from evaluation.phase56_stage7 import corpus_semantics

    expected = stage7_evaluation_contract().expected_terminals
    assert (
        expected.supported_accepted,
        expected.deferred_unsupported,
        expected.unsupported_other,
        expected.needs_figure,
        expected.needs_confirmation,
        expected.insufficient_information,
        expected.total,
    ) == (81, 12, 2, 2, 2, 1, 100)

    # Both consumers name the contract rather than a literal of their own.
    for module in (corpus_semantics, gate):
        source = inspect.getsource(module)
        assert "expected_terminals" in source, module.__name__

    # A distribution that totals 100 but misplaces a class must still fail: the
    # preflight compares every class, not just the sum.
    preflight = inspect.getsource(corpus_semantics)
    for field in (
        "supported_accepted",
        "deferred_unsupported",
        "unsupported_other",
        "needs_figure",
        "needs_confirmation",
        "insufficient_information",
    ):
        assert f"expected.{field}" in preflight, field


def test_a_missing_counter_is_not_a_zero() -> None:
    from evaluation.phase56_stage7.hard_safety_registry import (
        bound_node_ids,
        measure_signals,
        summarize,
    )

    node_outcomes = {node: "PASSED" for node in bound_node_ids()}
    summary = summarize(
        measure_signals(counters={}, node_outcomes=node_outcomes)
    )
    assert summary["unbound_signal_count"] >= 3
    assert summary["measured_signal_count"] <= 20


# ---------------------------------------------------------------------------
# Tolerance conversion is a true delta, including for offset units.
# ---------------------------------------------------------------------------


def test_offset_unit_tolerance_is_converted_as_a_delta() -> None:
    """A `± 0.1 degC` declaration must not arrive as `± 273.25 K`.

    Converting the tolerance as an absolute quantity adds the unit's offset to
    it, which would accept essentially any answer — the same defect class as
    the removed 1e-6 floor, reached through the unit path.
    """

    registry = lane_b_scoring._registry()

    class _Answer:
        numeric = 20.0
        unit = "degC"
        tolerance_abs = 0.1

    converted = lane_b_scoring._gold_answer_in_si(registry, _Answer())
    assert converted is not None
    assert converted.value == pytest.approx(293.15, abs=1e-9)
    # A delta of 0.1 degC is a delta of 0.1 K — not 273.25 K.
    assert converted.tolerance == pytest.approx(0.1, abs=1e-9)
    assert abs(566.0 - converted.value) > converted.tolerance


def test_multiplicative_unit_tolerance_is_unchanged_by_the_delta_fix() -> None:
    registry = lane_b_scoring._registry()

    class _Answer:
        numeric = 3.6
        unit = "km/hour"
        tolerance_abs = 0.36

    converted = lane_b_scoring._gold_answer_in_si(registry, _Answer())
    assert converted is not None
    assert converted.value == pytest.approx(1.0, abs=1e-12)
    assert converted.tolerance == pytest.approx(0.1, abs=1e-12)


# ---------------------------------------------------------------------------
# Scorer failures are typed, and never a partial pass.
# ---------------------------------------------------------------------------


def test_record_count_mismatch_is_a_typed_scoring_failure() -> None:
    cases = _fixture_cases()
    with pytest.raises(ScoringFailure) as excinfo:
        score_lane_b_cases(cases, _perfect_records(cases)[:-1])
    assert excinfo.value.reason is ScoringFailureReason.record_count_mismatch
    assert excinfo.value.sanitized_reason == "record_count_mismatch"


def test_scorer_exception_becomes_a_typed_gate_failure(monkeypatch) -> None:
    """A raising scorer must fail the gate, not abort the process."""

    class _Boom(Exception):
        pass

    def _explode(*_args: Any, **_kwargs: Any):
        raise _Boom("scorer detonated")

    monkeypatch.setattr(gate, "score_lane_b_cases", _explode)
    monkeypatch.setattr(
        gate, "read_public_corpus_archive", lambda _path: object()
    )
    monkeypatch.setattr(
        gate, "load_public_cases", lambda _inventory: ((), ())
    )
    monkeypatch.setattr(
        gate,
        "build_pipeline_failure_matrix",
        lambda _cases: _StubMatrix(),
    )

    section, outcome = gate._lane_b_section(Path("/nonexistent/archive.zip"))
    assert outcome.result == "FAIL"
    assert outcome.detail == "SCORER_FAILURE"
    assert section["scoring"]["disposition"] == "SCORER_FAILURE"
    # The raw message must never reach the artifact.
    assert "detonated" not in json.dumps(section)


class _StubMatrix:
    terminal_counts = (("solved", 0),)
    case_records: tuple[Any, ...] = ()
    executed_cases = 0

    def as_dict(self) -> dict[str, Any]:
        return {"total_cases": 0, "executed_cases": 0, "terminal_counts": {}}


# ---------------------------------------------------------------------------
# Strict-mode plumbing: NOT_RUN is never a pass.
# ---------------------------------------------------------------------------


def _report_with_scorecard(scorecard: Any) -> dict[str, Any]:
    return {
        "lane_b": {
            "executed": True,
            "total_cases": scorecard.total_cases,
            "executed_cases": scorecard.total_cases,
            "terminal_counts": dict(scorecard.actual_terminal_counts),
            "scoring": scorecard.as_dict(),
            "answer_scoring": scorecard.answer_score.as_dict(),
        },
        "public_corpus": {
            "supplied": True,
            "archive_sha256": stage7_evaluation_contract().corpus.expected_zip_sha256,
            "public_dev": 84,
            "public_adversarial": 16,
            "public_total": 100,
        },
        "external_model_calls": 0,
        "private_heldout_accesses": 0,
        "lane_c": {"result": "PASS"},
        "lane_d": {"result": "PASS"},
        "lane_e": {"result": "PASS"},
        "compositional_12": {"result": "PASS"},
        "synthetic_38": {"result": "PASS"},
        "metamorphic": {"result": "PASS"},
        "physics_changing_controls": {"result": "PASS"},
        "redaction": {"result": "PASS"},
    }


def _with_real_hard_safety(report: dict[str, Any]) -> dict[str, Any]:
    """Fill `hard_safety` from the runner itself, never from a hardcoded PASS.

    Hardcoding it would make the perfect-report test assert nothing about the
    section that actually decides safety.
    """

    return {**report, "hard_safety": gate._hard_safety_section(report, [], registry_summary=_measured_registry())}


def _strict_outcomes(report: dict[str, Any]) -> dict[str, str]:
    outcomes = gate._strict_requirements(
        _with_real_hard_safety(report), require_corpus=True, require_full=True
    )
    return {outcome.name: outcome.result for outcome in outcomes}


def test_a_perfect_report_passes_every_strict_requirement() -> None:
    cases = _fixture_cases()
    scorecard = score_lane_b_cases(cases, _perfect_records(cases))
    outcomes = _strict_outcomes(_report_with_scorecard(scorecard))
    assert set(outcomes.values()) == {"PASS"}, {
        name: result for name, result in outcomes.items() if result != "PASS"
    }
    for name in (
        "strict_supported_81_solved",
        "strict_deferred_12_verified_unsupported",
        "strict_unsupported_other_2",
        "strict_needs_figure_2",
        "strict_needs_confirmation_2",
        "strict_insufficient_information_1",
        "strict_terminal_mapping_100_percent",
        "strict_wrong_solve_zero",
        "strict_unscored_zero",
    ):
        assert outcomes[name] == "PASS"


def test_a_not_run_lane_is_never_promoted_to_pass() -> None:
    cases = _fixture_cases()
    scorecard = score_lane_b_cases(cases, _perfect_records(cases))
    report = _report_with_scorecard(scorecard)
    report["lane_e"] = {"result": "NOT_RUN", "executed": False}
    outcomes = _strict_outcomes(report)
    assert outcomes["strict_lane_e_pass"] == "FAIL"


def test_missing_public_corpus_fails_strict_mode() -> None:
    report = {
        "public_corpus": {"supplied": False, "disposition": "NOT_RUN"},
        "lane_b": {"executed": False, "disposition": "NOT_RUN"},
    }
    outcomes = _strict_outcomes(report)
    assert outcomes["strict_corpus_supplied"] == "FAIL"
    assert outcomes["strict_lane_b_executed"] == "FAIL"
    assert outcomes["strict_supported_81_solved"] == "FAIL"


def test_default_mode_emits_no_strict_requirements() -> None:
    report = {
        "public_corpus": {"supplied": False},
        "lane_b": {"executed": False},
    }
    assert (
        gate._strict_requirements(report, require_corpus=False, require_full=False)
        == []
    )


def test_scorer_failure_blocks_every_distribution_requirement() -> None:
    report = _report_with_scorecard(
        score_lane_b_cases(_fixture_cases(), _perfect_records(_fixture_cases()))
    )
    report["lane_b"]["scoring"] = {
        "result": "FAIL",
        "disposition": "SCORER_FAILURE",
        "reason": "record_count_mismatch",
    }
    outcomes = _strict_outcomes(report)
    assert outcomes["strict_lane_b_scored"] == "FAIL"
    for name in (
        "strict_supported_81_solved",
        "strict_deferred_12_verified_unsupported",
        "strict_wrong_solve_zero",
        "strict_unscored_zero",
    ):
        assert outcomes[name] == "FAIL"


# ---------------------------------------------------------------------------
# Suite-execution plumbing: parsing, exit codes, timeouts, missing toolchains.
# ---------------------------------------------------------------------------


def test_pytest_summary_parsing_reads_every_count(monkeypatch, tmp_path) -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="3 passed, 2 skipped, 7 deselected in 1.20s\n",
        stderr="",
    )
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: completed)
    row = gate._run_pytest_suite("tests/does_not_matter.py")
    assert row["passed"] == 3
    assert row["skipped"] == 2
    assert row["deselected"] == 7
    assert row["failed"] == 0
    assert row["errors"] == 0
    assert row["disposition"] == "PASS"


def test_pytest_failures_and_errors_are_parsed_and_fail(monkeypatch) -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="1 failed, 2 passed, 1 error in 0.30s\n",
        stderr="",
    )
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: completed)
    row = gate._run_pytest_suite("tests/does_not_matter.py")
    assert row["failed"] == 1
    assert row["errors"] == 1
    assert row["disposition"] == "FAIL"


def test_zero_collected_tests_is_not_a_pass(monkeypatch) -> None:
    """A suite that ran nothing has proved nothing."""

    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="no tests ran in 0.01s\n", stderr=""
    )
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: completed)
    assert gate._run_pytest_suite("tests/empty.py")["disposition"] == "FAIL"


def test_nonzero_exit_fails_even_with_a_clean_summary(monkeypatch) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=2, stdout="5 passed in 0.10s\n", stderr=""
    )
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: completed)
    assert gate._run_pytest_suite("tests/x.py")["disposition"] == "FAIL"


def test_suite_timeout_is_a_typed_failure(monkeypatch) -> None:
    def _timeout(*_a: Any, **_k: Any):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1)

    monkeypatch.setattr(gate.subprocess, "run", _timeout)
    row = gate._run_pytest_suite("tests/slow.py")
    assert row["disposition"] == "TIMEOUT"
    assert row["errors"] == 1


def test_lane_e_missing_toolchain_is_not_run_not_pass(monkeypatch, tmp_path) -> None:
    def _missing(*_a: Any, **_k: Any):
        raise FileNotFoundError("npm")

    monkeypatch.setattr(gate, "REPOSITORY_ROOT", tmp_path)
    (tmp_path / "frontend").mkdir()
    monkeypatch.setattr(gate.subprocess, "run", _missing)
    section = gate._lane_e_section(True)
    assert section["result"] == "NOT_RUN"
    assert section["executed"] is False


def test_lane_e_install_failure_is_not_run_not_pass(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(gate, "REPOSITORY_ROOT", tmp_path)
    (tmp_path / "frontend").mkdir()
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
    )
    section = gate._lane_e_section(True)
    assert section["result"] == "NOT_RUN"
    assert section["reason"] == "install_unavailable"


def test_lane_e_reuses_exact_installed_lint_toolchain_without_network_install(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(gate, "REPOSITORY_ROOT", tmp_path)
    frontend = tmp_path / "frontend"
    for package, version in (
        ("eslint", "9.39.5"),
        ("eslint-config-next", "15.5.18"),
    ):
        package_dir = frontend / "node_modules" / package
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "package.json").write_text(
            json.dumps({"name": package, "version": version}),
            encoding="utf-8",
        )

    commands: list[tuple[str, ...]] = []

    def _run(command, **_kwargs):
        commands.append(tuple(command))
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(gate.subprocess, "run", _run)
    section = gate._lane_e_section(True)

    assert section["result"] == "PASS"
    assert section["executed"] is True
    assert {item["step"] for item in section["steps"]} == {
        "lint_toolchain",
        "tests",
        "lint",
        "typecheck",
        "build",
    }
    assert next(
        item for item in section["steps"] if item["step"] == "lint_toolchain"
    )["reason"] == "exact_installed_toolchain"
    assert all(command[:2] != ("npm", "install") for command in commands)
    assert all(command[:2] != ("npm", "ci") for command in commands)


def test_unrequested_lanes_report_not_run(monkeypatch) -> None:
    for builder in (
        gate._lane_c_section,
        gate._lane_d_section,
        gate._compositional_12_section,
        gate._synthetic_38_section,
        gate._metamorphic_section,
        gate._physics_changing_section,
        gate._lane_e_section,
    ):
        section = builder(False)
        assert section["result"] == "NOT_RUN"
        assert section["executed"] is False


# ---------------------------------------------------------------------------
# The artifact stays privacy-safe.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# A corpus-independent run must never read back as a public-100 result.
# ---------------------------------------------------------------------------


def test_corpus_independent_run_names_its_own_scope() -> None:
    """The default CI run prints what it did and did not measure.

    A green corpus-independent run is repository health, not Stage 7
    acceptance.  Without the scope line on stdout the two are indistinguishable
    to anyone reading a workflow log.
    """

    env = {
        **os.environ,
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_BASE_URL": "",
        "ANTHROPIC_BASE_URL": "",
        "MECHANICS_MODELER_BASE_URL": "",
        "MECHANICS_FIGURE_BASE_URL": "",
    }
    env.pop("STAGE7_PUBLIC_CORPUS_PATH", None)
    with tempfile.TemporaryDirectory() as tmp:
        completed = subprocess.run(
            [
                sys.executable,
                str(GATE_PATH),
                "--output",
                str(Path(tmp) / "report.json"),
            ],
            cwd=REPOSITORY_ROOT / "backend",
            capture_output=True,
            text=True,
            env=env,
            timeout=900,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "STAGE7_RUN_SCOPE=CORPUS_INDEPENDENT_REGRESSION" in completed.stdout
        assert "STAGE7_PUBLIC_CORPUS=NOT_RUN" in completed.stdout
        assert "STAGE7_LANE_B=NOT_RUN" in completed.stdout
        assert "NOT_RUN, not PASS" in completed.stdout

        report = json.loads((Path(tmp) / "report.json").read_text(encoding="utf-8"))

    # Every public-corpus-dependent lane must be NOT_RUN, never PASS.
    assert report["run_scope"] == "CORPUS_INDEPENDENT_REGRESSION"
    for lane in (
        "lane_b",
        "lane_c",
        "lane_d",
        "lane_e",
        "compositional_12",
        "synthetic_38",
        "metamorphic",
        "physics_changing_controls",
        "hard_safety",
    ):
        assert report[lane].get("result", "NOT_RUN") != "PASS", lane
    # And it emits no strict verdict at all, so none can be quoted.
    assert "strict_gates" not in report


@pytest.mark.parametrize(
    "partial_flag",
    ("--require-public-corpus", "--require-full-stage7"),
)
def test_partial_strict_mode_fails_before_writing_evidence(
    partial_flag: str,
) -> None:
    """One strict flag cannot create an artifact with a contradictory scope."""

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "report.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(GATE_PATH),
                "--output",
                str(output),
                partial_flag,
            ],
            cwd=REPOSITORY_ROOT / "backend",
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert completed.returncode == 2
        assert (
            "STAGE7_OFFLINE_GATE=FAIL:strict_flags_must_be_used_together"
            in completed.stdout
        )
        assert not output.exists()


def test_scorecard_artifact_is_privacy_safe() -> None:
    from evaluation.phase56_stage7.redaction import assert_privacy_safe_artifact

    cases = _fixture_cases()
    scorecard = score_lane_b_cases(cases, _perfect_records(cases))
    assert_privacy_safe_artifact(scorecard.as_dict())


def test_redaction_failure_blocks_the_artifact() -> None:
    from evaluation.phase56_stage7.redaction import assert_privacy_safe_artifact

    with pytest.raises(ValueError):
        assert_privacy_safe_artifact({"lane_b": {"expected_answer": 1.0}})


def test_case_records_never_reach_the_artifact() -> None:
    """The matrix keeps per-case records in memory; the artifact stays aggregate."""

    from evaluation.phase56_stage7.lane_b_failure_matrix import LaneBPipelineMatrix

    assert "case_records" in LaneBPipelineMatrix.__dataclass_fields__
    matrix = LaneBPipelineMatrix(
        version="v",
        projection_version="p",
        runner_version="r",
        total_cases=1,
        executed_cases=1,
        terminal_counts=(),
        taxonomy_counts=(),
        compiler_status_counts=(),
        normalization_terminal_counts=(),
        solve_terminal_counts=(),
        stage_exception_counts=(),
        validation_code_path_counts=(),
        compiler_code_path_counts=(),
        solve_code_counts=(),
        law_id_counts=(),
        verification_check_counts=(),
        structure_counts=(),
        case_records=(_deferred_record(),),
    )
    assert "case_records" not in matrix.as_dict()
