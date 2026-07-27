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
    section = gate._hard_safety_section(report, [])
    assert section["result"] == "FAIL"
    assert section["all_zero"] is False


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
        "hard_safety": {"result": "PASS"},
        "redaction": {"result": "PASS"},
    }


def _strict_outcomes(report: dict[str, Any]) -> dict[str, str]:
    outcomes = gate._strict_requirements(
        report, require_corpus=True, require_full=True
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
