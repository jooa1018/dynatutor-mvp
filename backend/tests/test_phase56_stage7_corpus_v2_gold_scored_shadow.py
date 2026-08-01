"""The v2 shadow measures answers now, and the measurement is sequenced.

Two claims are pinned here and they are different claims.

*The runtime cannot see the gold.*  Changing an expected answer, an expected
terminal, a family, a case id, a failure code or a reference expression must
leave the runtime snapshot byte-identical — only the score may move.  A runtime
that reacted to any of those would be steering, and a shadow yield produced by
steering is not evidence of anything.

*The scorer cannot run the pipeline.*  It receives a frozen, hashed snapshot,
not a Draft; it holds no compiler, solver or verifier; and a snapshot whose
contents no longer match its digest is refused rather than scored.

And the accounting itself: `correct`, `wrong` and `unscored` are three counts,
never two.  Before this session the public shadow runner passed no comparator at
all and its report said `wrong: 0` — a number that meant "nothing compared" and
read as "nothing wrong".  A newly solved context that cannot be scored now fails
acceptance.

Everything here is synthetic.  No public archive is read.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from evaluation.phase56_stage7.contracts import Stage7ExpectedTerminal
from evaluation.phase56_stage7.corpus_v2.gold_scoring import (
    ContextVerdict,
    GoldScoringRefused,
    ShadowGoldCaseV1,
    score_shadow_snapshot,
    totals,
)
from evaluation.phase56_stage7.corpus_v2.records import CorpusV2AugmentationV1
from evaluation.phase56_stage7.corpus_v2.reporting import (
    SCORED_SCORE_CLASS,
    assert_scores_are_separated,
    build_scored_shadow_scorecard,
    scored_scorecard_as_dict,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    LedgerState,
    ShadowLedgerEntryV2,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
    RuntimeSnapshotRefused,
    ShadowRuntimeRecordV2,
    freeze_runtime_snapshot,
    scoring_handle,
)
from evaluation.phase56_stage7.corpus_v2.shadow_runner import run_shadow_context
from evaluation.phase56_stage7.redaction import assert_privacy_safe_artifact


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = "a" * 64
MANIFEST = "b" * 64
CANDIDATE = "c" * 64


# --------------------------------------------------------------------------
# A synthetic gold answer with the exact shape the strict comparator reads.
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _GoldAnswer:
    numeric: float
    unit: str
    tolerance_abs: float


def _gold(
    numeric: float = 3.43,
    unit: str = "m/s",
    tolerance_abs: float = 0.01,
    terminal: Stage7ExpectedTerminal = Stage7ExpectedTerminal.accepted,
) -> ShadowGoldCaseV1:
    answer = (
        _GoldAnswer(numeric=numeric, unit=unit, tolerance_abs=tolerance_abs)
        if terminal is Stage7ExpectedTerminal.accepted
        else None
    )
    return ShadowGoldCaseV1(expected_terminal=terminal, gold_answer=answer)


def _record(
    *,
    index: int = 0,
    solved: bool = True,
    baseline_solved: bool = False,
    value: float | None = 3.43,
    unit: str | None = "m/s",
    binding: bool = True,
) -> ShadowRuntimeRecordV2:
    return ShadowRuntimeRecordV2(
        scoring_handle=scoring_handle(
            original_v1_archive_sha256=ARCHIVE, context_index=index
        ),
        cohort_digest="d" * 64,
        augmented=True,
        carriers_supplied=("contact_side",),
        baseline_rung=(
            "solved_and_verified" if baseline_solved else "law_emitted_graph_underdetermined"
        ),
        shadow_rung="solved_and_verified" if solved else "law_emitted_graph_underdetermined",
        baseline_solved=baseline_solved,
        shadow_solved=solved,
        answer_value_si=value,
        answer_unit=unit,
        answer_component="magnitude",
        query_binding_digest="e" * 64,
        query_binding_complete=binding,
        candidate_count=1,
        verified_candidate_count=1 if solved else 0,
    )


def _ledger(*records: ShadowRuntimeRecordV2, extra=()):
    """The completeness rows these records are accounted for by.

    Every snapshot now carries one, so the default here is the honest one: a
    `runtime_completed` row per record, and nothing else.  `extra` lets a test
    state a corpus that also contained contexts which did not produce records.
    """

    return (
        *(
            ShadowLedgerEntryV2(
                scoring_handle=record.scoring_handle,
                state=LedgerState.runtime_completed,
            )
            for record in records
        ),
        *extra,
    )


def _snapshot(*records: ShadowRuntimeRecordV2, ledger=None):
    return freeze_runtime_snapshot(
        records,
        ledger=_ledger(*records) if ledger is None else ledger,
        original_v1_archive_sha256=ARCHIVE,
        augmentation_manifest_sha256=MANIFEST,
        candidate_archive_sha256=CANDIDATE,
        exact_code_head="deadbeef",
    )


def _score(records, gold_by_handle):
    snapshot = _snapshot(*records)
    scored = score_shadow_snapshot(snapshot, gold_by_handle)
    return snapshot, scored, totals(scored)


def _index(*golds: ShadowGoldCaseV1) -> dict[str, ShadowGoldCaseV1]:
    return {
        scoring_handle(original_v1_archive_sha256=ARCHIVE, context_index=position): gold
        for position, gold in enumerate(golds)
    }


# --------------------------------------------------------------------------
# The three counts
# --------------------------------------------------------------------------
def test_a_matching_answer_scores_correct() -> None:
    _snap, scored, score = _score([_record()], _index(_gold()))

    assert scored[0].verdict is ContextVerdict.correct
    assert (score.newly_solved, score.newly_solved_correct) == (1, 1)
    assert (score.newly_solved_wrong, score.newly_solved_unscored) == (0, 0)


def test_a_frozen_wrong_number_scores_wrong_not_unscored() -> None:
    """The defect this whole module exists for, stated as a test."""

    _snap, scored, score = _score([_record(value=99.0)], _index(_gold()))

    assert scored[0].verdict is ContextVerdict.wrong
    assert score.newly_solved_wrong == 1
    assert score.newly_solved_correct == 0


def test_a_wrong_unit_scores_wrong() -> None:
    _snap, _scored, score = _score([_record(unit="m")], _index(_gold()))

    assert score.newly_solved_wrong == 1


def test_a_solved_context_with_no_gold_is_unscored_and_never_a_pass() -> None:
    _snap, scored, score = _score([_record()], {})

    assert scored[0].verdict is ContextVerdict.unscored
    assert score.newly_solved_unscored == 1
    assert score.newly_solved_wrong == 0
    assert score.newly_solved_correct == 0


def test_a_solved_context_whose_class_has_no_answer_is_a_forbidden_class_solve() -> None:
    gold = _index(_gold(terminal=Stage7ExpectedTerminal.deferred_unsupported))

    _snap, scored, score = _score([_record()], gold)

    assert scored[0].verdict is ContextVerdict.forbidden_class_solve
    assert score.forbidden_class_solve == 1
    assert score.newly_solved_correct == 0


def test_an_answer_that_is_not_bound_to_the_question_is_not_correct() -> None:
    _snap, scored, score = _score([_record(binding=False)], _index(_gold()))

    assert scored[0].verdict is ContextVerdict.wrong
    assert score.query_binding_mismatch == 1


def test_a_missing_number_on_a_solved_context_is_unscored() -> None:
    _snap, _scored, score = _score([_record(value=None)], _index(_gold()))

    assert score.newly_solved_unscored == 1


def test_an_unsolved_context_scores_none_of_the_three() -> None:
    _snap, _scored, score = _score([_record(solved=False)], _index(_gold()))

    assert (score.newly_solved, score.all_shadow_correct) == (0, 0)
    assert (score.all_shadow_wrong, score.all_shadow_unscored) == (0, 0)


def test_cohort_yield_counts_correct_new_solves_only() -> None:
    _snap, _scored, score = _score(
        [_record(index=0), _record(index=1, value=99.0)],
        _index(_gold(), _gold()),
    )

    assert score.cohort_yield == (("d" * 64, 1),)


# --------------------------------------------------------------------------
# Gold isolation: the runtime snapshot must not move when the gold does
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mutated",
    [
        pytest.param(_gold(numeric=99.0), id="expected_answer"),
        pytest.param(_gold(unit="km/h"), id="answer_unit"),
        pytest.param(_gold(tolerance_abs=50.0), id="tolerance"),
        pytest.param(
            _gold(terminal=Stage7ExpectedTerminal.needs_figure), id="expected_terminal"
        ),
    ],
)
def test_the_runtime_snapshot_is_byte_identical_under_every_gold_change(
    mutated: ShadowGoldCaseV1,
) -> None:
    baseline_snapshot, _s, _baseline = _score([_record()], _index(_gold()))
    mutated_snapshot, _m, _moved = _score([_record()], _index(mutated))

    assert baseline_snapshot.digest_material() == mutated_snapshot.digest_material()
    assert (
        baseline_snapshot.runtime_snapshot_digest
        == mutated_snapshot.runtime_snapshot_digest
    )


def test_a_tampered_tolerance_flips_the_score_and_not_the_snapshot() -> None:
    """The positive control for the test above: the gold change must be real."""

    snapshot_a, _a, tight = _score(
        [_record(value=3.60)], _index(_gold(tolerance_abs=0.01))
    )
    snapshot_b, _b, loose = _score(
        [_record(value=3.60)], _index(_gold(tolerance_abs=1.0))
    )

    assert snapshot_a.digest_material() == snapshot_b.digest_material()
    assert (tight.newly_solved_wrong, loose.newly_solved_correct) == (1, 1)


# --------------------------------------------------------------------------
# Freeze and sequencing
# --------------------------------------------------------------------------
def test_a_frozen_snapshot_refuses_mutation() -> None:
    snapshot = _snapshot(_record())

    with pytest.raises(Exception):
        snapshot.context_count = 99  # type: ignore[misc]
    with pytest.raises(Exception):
        snapshot.records[0].answer_value_si = 1.0  # type: ignore[misc]


def test_a_snapshot_whose_contents_changed_after_freezing_is_refused() -> None:
    snapshot = _snapshot(_record())
    forged = snapshot.model_copy(update={"context_count": 99})

    assert not forged.digest_is_intact()
    with pytest.raises(GoldScoringRefused):
        score_shadow_snapshot(forged, _index(_gold()))


def test_two_records_cannot_share_one_scoring_handle() -> None:
    with pytest.raises(RuntimeSnapshotRefused):
        _snapshot(_record(index=0), _record(index=0))


def test_scoring_does_not_feed_back_into_the_snapshot() -> None:
    snapshot = _snapshot(_record(value=99.0))
    before = snapshot.model_dump(mode="json")

    score_shadow_snapshot(snapshot, _index(_gold()))

    assert snapshot.model_dump(mode="json") == before
    assert snapshot.digest_is_intact()


# --------------------------------------------------------------------------
# Structural isolation, read off the source
# --------------------------------------------------------------------------
def _imported_modules(relative: str) -> set[str]:
    path = REPOSITORY_ROOT / relative
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_the_runtime_snapshot_module_cannot_reach_the_gold() -> None:
    modules = _imported_modules(
        "backend/evaluation/phase56_stage7/corpus_v2/runtime_snapshot.py"
    )

    assert not any(
        fragment in module
        for module in modules
        for fragment in ("gold_domain", "gold_scoring", "lane_b_scoring", "corpus_records")
    )


def test_the_shadow_runner_cannot_reach_the_gold() -> None:
    modules = _imported_modules(
        "backend/evaluation/phase56_stage7/corpus_v2/shadow_runner.py"
    )

    assert not any(
        fragment in module
        for module in modules
        for fragment in ("gold_domain", "gold_scoring", "lane_b_scoring")
    )


def test_the_shadow_runner_takes_no_comparator() -> None:
    """The hook that made `wrong: 0` mean "nothing compared" is gone."""

    path = REPOSITORY_ROOT / "backend/evaluation/phase56_stage7/corpus_v2/shadow_runner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_shadow_context"
    )
    arguments = function.args
    names = {
        argument.arg
        for argument in (*arguments.args, *arguments.kwonlyargs, *arguments.posonlyargs)
    }

    assert "compare_answer" not in names
    assert not any("compar" in name or "gold" in name or "expect" in name for name in names)


def test_the_scorer_cannot_call_the_compiler_solver_or_verifier() -> None:
    modules = _imported_modules(
        "backend/evaluation/phase56_stage7/corpus_v2/gold_scoring.py"
    )

    forbidden = (
        "lane_b_runner",
        "lane_b_adapter",
        "engine.",
        "corpus_v2.projection",
        "corpus_v2.migration",
        "lane_b_draft_projection",
    )
    assert not any(module.startswith(item) or item in module for module in modules for item in forbidden)


def test_the_scorer_reuses_the_official_comparator_rather_than_defining_one() -> None:
    """No second tolerance policy exists to be softened.

    Read off the syntax rather than the prose: the shadow scorer must import
    the strict comparator, and must contain no arithmetic of its own that could
    become a private tolerance — no float literal, no `abs`, no `isclose`, no
    `<=` against a number.
    """

    path = (
        REPOSITORY_ROOT
        / "backend/evaluation/phase56_stage7/corpus_v2/gold_scoring.py"
    )
    modules = _imported_modules(
        "backend/evaluation/phase56_stage7/corpus_v2/gold_scoring.py"
    )
    assert "evaluation.phase56_stage7.lane_b_scoring" in modules

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            raise AssertionError("the shadow scorer carries a float literal")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"abs", "isclose", "round"}
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"isclose", "ulp"}
        if isinstance(node, ast.Compare):
            assert not any(
                isinstance(operator, (ast.LtE, ast.Lt, ast.GtE, ast.Gt))
                for operator in node.ops
            )


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def _scorecard(records, gold_by_handle):
    snapshot, scored, score = _score(records, gold_by_handle)
    return build_scored_shadow_scorecard(scored, score, snapshot=snapshot)


def test_a_scored_report_is_stamped_and_carries_no_official_field() -> None:
    payload = scored_scorecard_as_dict(_scorecard([_record()], _index(_gold())))

    assert payload["score_class"] == SCORED_SCORE_CLASS
    assert payload["is_official_score"] is False
    assert_scores_are_separated({"observed_public_score": "41/81"}, payload)
    assert_privacy_safe_artifact(payload)


def test_a_scored_report_carries_no_case_identity_and_no_handle() -> None:
    payload = scored_scorecard_as_dict(_scorecard([_record()], _index(_gold())))
    body = json.dumps(payload, ensure_ascii=False)

    assert "scoring_handle" not in body
    assert "case_id" not in body
    assert "problem_text" not in body
    assert "family" not in body
    # Every gold expectation, by name.  The blunt "no substring `expected`"
    # check this replaces already had to exempt `unexpected_runtime_failure`,
    # and the completeness accounting adds `expected_context_count` — a count
    # of contexts in the corpus, which identifies nothing and has to be
    # published for the "no context went missing" claim to be checkable at all.
    # Naming the forbidden fields instead of guessing at them by substring is
    # both stricter and stable against further honest uses of the word.
    for forbidden in (
        "expected_answer",
        "expected_terminal",
        "expected_failure",
        "expected_system_type",
        "future_expected_terminal",
        "phase55_expected_terminal",
        "gold_answer",
        "reference_expression",
        "tolerance",
    ):
        assert forbidden not in body
    # And nothing else may use the word: the only survivors are the two
    # completeness names above, so stripping exactly those must leave none.
    assert "expected" not in body.replace("unexpected", "").replace(
        "expected_context_count", ""
    )


def test_acceptance_fails_on_an_unscored_new_solve() -> None:
    card = _scorecard([_record()], {})

    assert "newly_solved_unscored" in card.acceptance_failures


def test_acceptance_fails_on_a_wrong_answer() -> None:
    card = _scorecard([_record(value=99.0)], _index(_gold()))

    assert "newly_solved_wrong" in card.acceptance_failures
    assert "all_shadow_wrong" in card.acceptance_failures


def test_acceptance_fails_on_a_forbidden_class_solve() -> None:
    card = _scorecard(
        [_record()], _index(_gold(terminal=Stage7ExpectedTerminal.unsupported_other))
    )

    assert "forbidden_class_solve" in card.acceptance_failures


def test_a_clean_run_has_no_acceptance_failure() -> None:
    card = _scorecard([_record()], _index(_gold()))

    assert card.acceptance_failures == ()
    assert card.runtime_snapshot_sha256 == _snapshot(_record()).runtime_snapshot_digest


def test_the_report_takes_its_hashes_from_the_snapshot_it_scored() -> None:
    card = _scorecard([_record()], _index(_gold()))

    assert card.original_v1_archive_sha256 == ARCHIVE
    assert card.augmentation_manifest_sha256 == MANIFEST
    assert card.candidate_archive_sha256 == CANDIDATE
    assert card.exact_code_head == "deadbeef"


# --------------------------------------------------------------------------
# The runtime record itself carries no gold
# --------------------------------------------------------------------------
def test_a_runtime_record_has_nowhere_to_put_an_expected_answer() -> None:
    fields = set(ShadowRuntimeRecordV2.model_fields)

    assert not any(
        token in name
        for name in fields
        for token in ("expected", "gold", "family", "case", "split", "correct", "wrong")
    )


def test_the_runner_produces_a_record_with_no_verdict_in_it() -> None:
    payload = {
        "entities": [{"entity_id": "body", "primitive": "particle"}],
        "queries": [{"query_id": "y1", "target": {"role": "velocity", "subject_id": "body"}}],
        "quantities": [],
        "reference_frames": [],
        "interactions": [],
        "state_conditions": [],
        "geometry": [],
        "motion_intervals": [],
        "events": [],
        "assumptions": [],
        "constraints": [],
    }

    class _Result:
        terminal = "solved"
        verified_candidate_count = 1
        candidate_count = 1
        answer_value_si = 1.0
        answer_unit = "m"
        answer_query_symbol_id = "s"
        query_subject_id = "body"
        answer_component = "magnitude"
        applied_law_ids = ()
        equation_count = 1
        stage_exception = None

    record = run_shadow_context(
        draft_payload=payload,
        augmentation=CorpusV2AugmentationV1(),
        run=lambda _: _Result(),
        original_v1_archive_sha256=ARCHIVE,
        context_index=7,
    )

    assert isinstance(record, ShadowRuntimeRecordV2)
    assert record.scoring_handle == scoring_handle(
        original_v1_archive_sha256=ARCHIVE, context_index=7
    )
