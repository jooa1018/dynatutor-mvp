"""The shadow measurement fails closed, and a failed measurement exits non-zero.

Two defects are pinned here, and both were found by independent verification of
a run that had reported itself accepted.

*A context could leave the measurement silently.*  The runner walked the corpus
with two ``continue`` statements — one for a refused projection, one for
``except Exception`` — and each removed the context from the run entirely.  It
left no runtime record, so it was absent from the snapshot; absent from the
snapshot, absent from the scored handle set; absent from the handle set, absent
from the gold index built off that set; and therefore uncountable as wrong,
unscored, forbidden or regressed.  The surviving contexts could carry an
acceptance PASS on their own, and the report's zeroes were zeroes about a
subset nobody had chosen.

*A failed acceptance still exited zero.*  The runner printed
``ACCEPTANCE=FAIL:...`` and then ``return 0``, so every shell and CI step that
read the exit status was told the measurement had succeeded.

The tests are grouped as the attack matrix that found them: completeness,
snapshot integrity, gold isolation, and exit behavior.  Everything here is
synthetic — no public archive is read.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from evaluation.phase56_stage7.corpus_v2.gold_scoring import (
    GoldScoringRefused,
    ShadowGoldCaseV1,
    build_gold_index,
    gold_pairing_failures,
    score_shadow_snapshot,
)
from evaluation.phase56_stage7.corpus_v2.runtime_input import (
    RuntimeContextInputV2,
    RuntimeInputRefused,
    ShadowRuntimeInputV2,
    load_runtime_input,
)
from evaluation.phase56_stage7.corpus_v2.runtime_ledger import (
    BLOCKING_REFUSALS,
    EXPECTED_REFUSALS,
    LedgerState,
    RefusalCode,
    ShadowLedgerEntryV2,
    ledger_completeness_failures,
    refusal_counts,
    state_counts,
)
from evaluation.phase56_stage7.corpus_v2.runtime_snapshot import (
    PublicRedactedRuntimeViewV2,
    RuntimeSnapshotRefused,
    ShadowRuntimeRecordV2,
    freeze_runtime_snapshot,
    load_full_runtime_snapshot,
    redact_runtime_snapshot,
    scoring_handle,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPOSITORY_ROOT / "backend" / "tools"

ARCHIVE = "a" * 64
MANIFEST = "b" * 64
CANDIDATE = "c" * 64


def _handle(index: int) -> str:
    return scoring_handle(original_v1_archive_sha256=ARCHIVE, context_index=index)


def _record(index: int = 0, *, solved: bool = True, value: float = 3.0):
    return ShadowRuntimeRecordV2(
        scoring_handle=_handle(index),
        cohort_digest="d" * 64,
        augmented=True,
        carriers_supplied=("contact_side",),
        baseline_rung="law_emitted_graph_underdetermined",
        shadow_rung=(
            "solved_and_verified" if solved else "law_emitted_graph_underdetermined"
        ),
        baseline_solved=False,
        shadow_solved=solved,
        answer_value_si=value if solved else None,
        answer_unit="m/s^2" if solved else None,
        answer_component="magnitude",
        query_binding_digest="e" * 64,
        query_binding_complete=True,
        candidate_count=1,
        verified_candidate_count=1 if solved else 0,
    )


def _completed(index: int) -> ShadowLedgerEntryV2:
    return ShadowLedgerEntryV2(
        scoring_handle=_handle(index), state=LedgerState.runtime_completed
    )


def _refused(index: int) -> ShadowLedgerEntryV2:
    return ShadowLedgerEntryV2(
        scoring_handle=_handle(index),
        state=LedgerState.projection_refused,
        refusal_code=RefusalCode.projection_refused_no_draft,
    )


def _freeze(records, ledger):
    return freeze_runtime_snapshot(
        records,
        ledger=ledger,
        original_v1_archive_sha256=ARCHIVE,
        augmentation_manifest_sha256=MANIFEST,
        candidate_archive_sha256=CANDIDATE,
        exact_code_head="deadbeef",
    )


def _body(snapshot) -> str:
    return json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)


# --------------------------------------------------------------------------
# 1-5. Context completeness: nothing may leave the run quietly
# --------------------------------------------------------------------------
def test_a_refused_context_keeps_an_explicit_ledger_row() -> None:
    """The anticipated refusal is recorded, not dropped.

    Three contexts, one of which cannot be projected: the snapshot carries two
    records and *three* ledger rows, so the corpus is still fully accounted for
    and the refusal is a number a reader can check rather than an absence.
    """

    snapshot = _freeze(
        [_record(0), _record(1)],
        [_completed(0), _completed(1), _refused(2)],
    )

    assert snapshot.expected_context_count == 3
    assert snapshot.context_count == 2
    assert snapshot.completeness_failures() == ()
    assert dict(state_counts(snapshot.ledger))["projection_refused"] == 1
    assert dict(refusal_counts(snapshot.ledger)) == {
        RefusalCode.projection_refused_no_draft.value: 1
    }


def test_a_runtime_failure_is_recorded_and_blocks_acceptance() -> None:
    """Attack 1: one context raises.

    The context stays in the ledger under a blocking code, so it is visible;
    and because the code is blocking, the run cannot be accepted.  The old
    shape counted ``type(exc).__name__`` into a free-form counter that nothing
    read, and dropped the context.
    """

    ledger = [
        _completed(0),
        ShadowLedgerEntryV2(
            scoring_handle=_handle(1),
            state=LedgerState.runtime_failed,
            refusal_code=RefusalCode.runtime_failed_unexpected_exception,
        ),
    ]

    with pytest.raises(RuntimeSnapshotRefused) as refusal:
        _freeze([_record(0)], ledger)

    assert "shadow_unexpected_runtime_failure" in str(refusal.value)
    assert ledger[1].is_blocking


def test_an_expected_handle_missing_from_the_snapshot_fails() -> None:
    """Attack 2: delete one expected handle.

    The scorer builds its gold index from the corpus, not from the snapshot, so
    a context the snapshot lost is a context the two sets disagree about.
    """

    snapshot = _freeze([_record(0)], [_completed(0)])
    gold = {
        _handle(0): ShadowGoldCaseV1(expected_terminal=_accepted(), gold_answer=None),
        _handle(1): ShadowGoldCaseV1(expected_terminal=_accepted(), gold_answer=None),
    }

    failures = gold_pairing_failures(snapshot, gold)

    assert "shadow_unknown_handle_present" in failures
    assert "shadow_context_count_mismatch" in failures


def test_an_unknown_handle_in_the_snapshot_fails() -> None:
    """Attack 3: add a handle the corpus does not contain."""

    failures = ledger_completeness_failures(
        [_completed(0), _completed(9)],
        expected_handles=[_handle(0)],
        recorded_handles=[_handle(0), _handle(9)],
    )

    assert "shadow_unknown_handle_present" in failures
    assert "shadow_context_count_mismatch" in failures


def test_a_duplicate_handle_fails() -> None:
    """Attack 4: the same context accounted for twice."""

    failures = ledger_completeness_failures(
        [_completed(0), _completed(0)],
        expected_handles=[_handle(0), _handle(1)],
        recorded_handles=[_handle(0)],
    )

    assert "shadow_duplicate_handle" in failures

    with pytest.raises(RuntimeSnapshotRefused):
        _freeze([_record(0), _record(0)], [_completed(0)])


def test_an_empty_record_set_against_a_populated_ledger_fails() -> None:
    """Attack 5: every runtime record removed.

    The most important negative in the set.  A snapshot with no records is
    internally consistent and would previously have scored a clean sweep of
    zeroes — no wrong, no unscored, no regression — which is exactly what an
    accepted run looks like.  It is refused because the ledger says contexts
    completed and no records answer for them.
    """

    with pytest.raises(RuntimeSnapshotRefused) as refusal:
        _freeze([], [_completed(0), _completed(1)])

    assert "shadow_snapshot_incomplete" in str(refusal.value)


# --------------------------------------------------------------------------
# 6-10. Snapshot integrity: the artifact must re-read as what it claims to be
# --------------------------------------------------------------------------
def test_a_frozen_snapshot_reloads_from_its_own_bytes() -> None:
    """The property the stored artifact did not previously have at all.

    What reached disk was the redacted view, and Phase G scored the in-memory
    object.  Nobody holding the file could re-score the run from it.
    """

    snapshot = _freeze([_record(0)], [_completed(0)])

    reloaded = load_full_runtime_snapshot(_body(snapshot))

    assert reloaded == snapshot
    assert reloaded.digest_is_intact()
    assert reloaded.recomputed_digest() == snapshot.runtime_snapshot_digest


def test_a_mutated_snapshot_byte_is_refused() -> None:
    """Attack 6: change one byte of content."""

    snapshot = _freeze([_record(0, value=3.0)], [_completed(0)])
    payload = json.loads(_body(snapshot))
    payload["records"][0]["answer_value_si"] = 99.0

    with pytest.raises(RuntimeSnapshotRefused) as refusal:
        load_full_runtime_snapshot(json.dumps(payload))

    assert "digest" in str(refusal.value)


def test_a_mutated_embedded_digest_is_refused() -> None:
    """Attack 7: change only the digest field."""

    snapshot = _freeze([_record(0)], [_completed(0)])
    payload = json.loads(_body(snapshot))
    payload["runtime_snapshot_digest"] = "0" * 64

    with pytest.raises(RuntimeSnapshotRefused):
        load_full_runtime_snapshot(json.dumps(payload))


def test_the_redacted_view_is_not_a_scoring_input() -> None:
    """Attack 8: hand the published view to the scorer.

    It is a different model with a different version and class, and it has no
    handle field at all — so this is a type refusal, not a policy one.
    """

    snapshot = _freeze([_record(0)], [_completed(0)])
    view = redact_runtime_snapshot(snapshot)
    body = json.dumps(view.model_dump(mode="json"), ensure_ascii=False)

    with pytest.raises(RuntimeSnapshotRefused):
        load_full_runtime_snapshot(body)

    assert "scoring_handle" not in body
    assert view.is_scoring_input is False
    assert view.full_runtime_snapshot_digest == snapshot.runtime_snapshot_digest
    assert set(PublicRedactedRuntimeViewV2.model_fields) & {"records"}
    assert "scoring_handle" not in view.records[0].model_fields


def test_a_snapshot_with_the_handle_stripped_is_refused() -> None:
    """Attack 9: remove `scoring_handle` from a full snapshot record."""

    snapshot = _freeze([_record(0)], [_completed(0)])
    payload = json.loads(_body(snapshot))
    payload["records"][0].pop("scoring_handle")

    with pytest.raises(RuntimeSnapshotRefused):
        load_full_runtime_snapshot(json.dumps(payload))


def test_a_truncated_snapshot_is_refused() -> None:
    """Attack 10: the file was cut off mid-write."""

    snapshot = _freeze([_record(0)], [_completed(0)])

    with pytest.raises(RuntimeSnapshotRefused):
        load_full_runtime_snapshot(_body(snapshot)[: len(_body(snapshot)) // 2])


def test_a_snapshot_of_the_wrong_version_is_refused() -> None:
    snapshot = _freeze([_record(0)], [_completed(0)])
    payload = json.loads(_body(snapshot))
    payload["version"] = "phase56-stage7-corpus-v2-runtime-snapshot-v1"

    with pytest.raises(RuntimeSnapshotRefused):
        load_full_runtime_snapshot(json.dumps(payload))


# --------------------------------------------------------------------------
# 11-15. Gold isolation: the runtime phase cannot reach an expectation
# --------------------------------------------------------------------------
def _accepted():
    from evaluation.phase56_stage7.contracts import Stage7ExpectedTerminal

    return Stage7ExpectedTerminal.accepted


def test_the_runtime_input_type_has_no_field_for_an_expectation() -> None:
    """Attacks 11-13, structurally rather than by experiment.

    Changing an expected answer cannot change the runtime snapshot's bytes
    because the runtime phase is not given the expected answer: its input model
    has nowhere to put one, and pydantic's strict models reject unknown keys.
    """

    fields = set(RuntimeContextInputV2.model_fields) | set(
        ShadowRuntimeInputV2.model_fields
    )
    for forbidden in (
        "gold",
        "answers",
        "expected_terminal",
        "expected_answer",
        "expected_failure_codes",
        "future_expected_terminal",
        "family",
        "case_id",
        "split",
        "reference_expression",
        "tolerance",
    ):
        assert forbidden not in fields

    with pytest.raises(Exception):
        RuntimeContextInputV2(
            scoring_handle=_handle(0),
            context_index=0,
            prepared_state=LedgerState.runtime_completed,
            gold={"answers": [1.0]},
        )


def _imported_names(path: Path) -> set[str]:
    """Every module and name this file imports.

    Read off the AST rather than the text, so a name that appears only in prose
    — explaining the defect this architecture closes, for instance — is not
    mistaken for a dependency.  What matters is what the process can reach.
    """

    tree = ast.parse(path.read_text("utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            names.update((node.module or "").split("."))
            names.update(alias.name for alias in node.names)
    return names


def test_the_runtime_phase_module_does_not_import_the_gold_domain() -> None:
    """Attack 14, as an import-graph property of the Phase R command.

    A scorer, a comparator or a corpus loader in this module's import set would
    make the sequencing claim unprovable again, whatever the code did.
    """

    imported = _imported_names(TOOLS / "run_phase56_stage7_v2_shadow_runtime.py")

    for forbidden in (
        "gold_scoring",
        "compare_answer_to_gold",
        "corpus_preflight",
        "corpus_integrity",
        "read_public_corpus_archive",
        "load_public_cases",
        "scope_adjusted_expected_terminal",
        "PublicCorpusCaseV1",
        "gold_domain",
        "lane_b_scoring",
    ):
        assert forbidden not in imported, forbidden


def test_the_scoring_phase_module_holds_no_pipeline() -> None:
    """Attack 14, the other direction: Phase G cannot re-run anything."""

    imported = _imported_names(TOOLS / "run_phase56_stage7_v2_shadow_score.py")

    for forbidden in (
        "run_lane_b_case",
        "run_shadow_context",
        "project_case_to_draft",
        "project_augmentation",
        "MechanicsProblemDraftV1",
        "build_candidate_archive",
        "shadow_runner",
        "projection",
        "lane_b_runner",
        "lane_b_draft_projection",
    ):
        assert forbidden not in imported, forbidden


def test_scoring_a_reloaded_snapshot_reproduces_the_same_verdicts() -> None:
    """Attack 15: the frozen file alone reproduces the score.

    The scorer is handed a snapshot parsed back from bytes rather than the
    object that was built in memory, and reaches the same verdicts.
    """

    snapshot = _freeze([_record(0)], [_completed(0), _refused(1)])
    reloaded = load_full_runtime_snapshot(_body(snapshot))
    gold = {
        _handle(0): ShadowGoldCaseV1(expected_terminal=_accepted(), gold_answer=None),
        _handle(1): ShadowGoldCaseV1(expected_terminal=_accepted(), gold_answer=None),
    }

    assert gold_pairing_failures(reloaded, gold) == ()
    assert score_shadow_snapshot(reloaded, gold) == score_shadow_snapshot(
        snapshot, gold
    )


def test_the_scorer_refuses_a_snapshot_that_lost_a_context() -> None:
    """A snapshot that cannot be completed is not scored at all."""

    snapshot = _freeze([_record(0)], [_completed(0)])
    broken = snapshot.model_copy(update={"ledger": ()})

    with pytest.raises(GoldScoringRefused):
        score_shadow_snapshot(broken, {})


def test_the_gold_index_covers_the_whole_corpus_by_default(monkeypatch) -> None:
    """The default that makes the two sets independent.

    An index built over only the recorded positions agrees with the snapshot by
    construction — including about a context they both lost — so the pairing
    check could never see a disagreement.  Over the whole corpus it can.

    The expected-class derivation is stubbed because this test is about which
    positions are covered, not about what any of them expects.
    """

    from evaluation.phase56_stage7.corpus_v2 import gold_scoring

    monkeypatch.setattr(
        gold_scoring,
        "scope_adjusted_expected_terminal",
        lambda case, case_index: _accepted(),
    )

    class _Case:
        gold = type("_G", (), {"answers": []})()

    index = build_gold_index(
        [_Case(), _Case(), _Case()], original_v1_archive_sha256=ARCHIVE
    )

    assert set(index) == {_handle(0), _handle(1), _handle(2)}


# --------------------------------------------------------------------------
# The closed vocabulary itself
# --------------------------------------------------------------------------
def test_every_refusal_code_is_either_expected_or_blocking() -> None:
    assert EXPECTED_REFUSALS | BLOCKING_REFUSALS == set(RefusalCode)
    assert not EXPECTED_REFUSALS & BLOCKING_REFUSALS


def test_a_completed_context_may_not_carry_a_refusal_code() -> None:
    with pytest.raises(Exception):
        ShadowLedgerEntryV2(
            scoring_handle=_handle(0),
            state=LedgerState.runtime_completed,
            refusal_code=RefusalCode.projection_refused_no_draft,
        )


def test_a_refused_context_must_say_under_which_code() -> None:
    with pytest.raises(Exception):
        ShadowLedgerEntryV2(
            scoring_handle=_handle(0), state=LedgerState.projection_refused
        )


def test_a_refusal_code_must_match_its_state() -> None:
    with pytest.raises(Exception):
        ShadowLedgerEntryV2(
            scoring_handle=_handle(0),
            state=LedgerState.projection_refused,
            refusal_code=RefusalCode.runtime_failed_unexpected_exception,
        )


def test_state_counts_publish_zeroes() -> None:
    """A published zero is a measurement; a missing key is only an absence."""

    counts = dict(state_counts([_completed(0)]))

    assert counts[LedgerState.runtime_failed.value] == 0
    assert set(counts) == {state.value for state in LedgerState}


def test_a_runtime_input_bundle_reloads_and_refuses_duplicates() -> None:
    bundle = ShadowRuntimeInputV2(
        original_v1_archive_sha256=ARCHIVE,
        augmentation_manifest_sha256=MANIFEST,
        candidate_archive_sha256=CANDIDATE,
        contexts=(
            RuntimeContextInputV2(
                scoring_handle=_handle(0),
                context_index=0,
                prepared_state=LedgerState.projection_refused,
                refusal_code=RefusalCode.projection_refused_no_draft,
            ),
        ),
    )
    body = json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)

    assert load_runtime_input(body) == bundle

    payload = json.loads(body)
    payload["contexts"] = [payload["contexts"][0], payload["contexts"][0]]
    with pytest.raises(RuntimeInputRefused):
        load_runtime_input(json.dumps(payload))


# --------------------------------------------------------------------------
# 16-20. Exit behavior: a printed FAIL and a zero exit cannot coexist
# --------------------------------------------------------------------------
def _score_process(tmp_path: Path, snapshot_body: str, corpus: Path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(snapshot_body, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(TOOLS / "run_phase56_stage7_v2_shadow_score.py"),
            "--corpus-archive",
            str(corpus),
            "--runtime-snapshot",
            str(snapshot),
            "--shadow-report",
            str(tmp_path / "report.json"),
            "--scorecard",
            str(tmp_path / "scorecard.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p["records"].clear(), id="records_deleted"),
        pytest.param(
            lambda p: p.__setitem__("runtime_snapshot_digest", "0" * 64),
            id="digest_corrupted",
        ),
        pytest.param(lambda p: p["ledger"].clear(), id="ledger_deleted"),
    ],
)
def test_a_broken_snapshot_exits_two_before_any_corpus_is_read(
    tmp_path: Path, mutate
) -> None:
    """Attacks 16-19 at the process boundary, with no corpus needed.

    The snapshot is refused before the archive is opened, so these run without
    a public corpus and still prove the exit status: a run that cannot be
    scored honestly exits 2 rather than printing something and returning 0.
    """

    snapshot = _freeze([_record(0)], [_completed(0)])
    payload = json.loads(_body(snapshot))
    mutate(payload)

    completed = _score_process(
        tmp_path, json.dumps(payload), tmp_path / "no-such-corpus.zip"
    )

    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "FAIL" in completed.stdout + completed.stderr


def test_the_score_command_returns_two_whenever_acceptance_fails() -> None:
    """Attack 20's inverse, read off the source.

    The exit status and the printed disposition come from one value.  The
    shape this forbids is literally ``print("...FAIL...")`` followed by
    ``return 0``, which is what the previous runner did.
    """

    source = (TOOLS / "run_phase56_stage7_v2_shadow_score.py").read_text("utf-8")

    assert "return 0 if not failures else SCORE_FAILURE_EXIT" in source
    assert "SCORE_FAILURE_EXIT = 2" in source

    runtime = (TOOLS / "run_phase56_stage7_v2_shadow_runtime.py").read_text("utf-8")
    assert "return 0 if not failures else RUNTIME_FAILURE_EXIT" in runtime
    assert "RUNTIME_FAILURE_EXIT = 2" in runtime


def test_the_orchestrator_invokes_three_separate_processes() -> None:
    """The isolation is process-level, not comment-level."""

    source = (TOOLS / "run_phase56_stage7_v2_shadow.py").read_text("utf-8")

    assert "subprocess.run" in source
    for step in (
        "run_phase56_stage7_v2_shadow_prepare.py",
        "run_phase56_stage7_v2_shadow_runtime.py",
        "run_phase56_stage7_v2_shadow_score.py",
    ):
        assert step in source
        assert (TOOLS / step).exists()
