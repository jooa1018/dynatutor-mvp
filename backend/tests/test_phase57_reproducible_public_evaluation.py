from __future__ import annotations

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest

from evaluation.phase56_stage7.contracts import Stage7ExpectedTerminal
from evaluation.phase56_stage7.corpus_integrity import read_public_corpus_archive
from evaluation.phase56_stage7.corpus_preflight import (
    assert_raw_corpus_is_not_committed,
    load_public_cases,
)
from evaluation.phase56_stage7.corpus_semantics import (
    scope_adjusted_expected_terminal,
)
from evaluation.phase56_stage7.corpus_v2.campaign_seal import (
    PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V1,
    resolve_campaign_seal,
)
from evaluation.phase56_stage7.corpus_v2.prepare_builder import build_prepared_campaign
from evaluation.phase57_reproducible.contracts import (
    PHASE56_HISTORICAL_STAGE7_STATUS,
    PHASE56_HISTORICAL_STAGE8_STATUS,
    PHASE57_CAMPAIGN_SEAL_NAME,
    PHASE57_CONTINUATION_MANIFEST_DIGEST,
    PHASE57_CONTINUATION_MANIFEST_FILE_SHA256,
    PHASE57_CONTINUATION_SELECTION_DIGEST,
    PHASE57_FIXTURE_SET_DIGEST,
    PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
    phase57_public_evaluation_contract,
)
from evaluation.phase57_reproducible.fixtures import (
    DEFAULT_FIXTURE_ROOT,
    Phase57FixtureRefused,
    build_continuation_manifest,
    build_reproducible_archive_bytes,
    load_public_fixture_cases,
    materialize_campaign_inputs,
    validate_fixture_set,
)
from evaluation.phase57_reproducible.gate import (
    Phase57RunnerStatusV1,
    evaluate_phase57_shadow_report,
    phase57_gate_report_as_dict,
    phase57_runner_status_as_dict,
)
from tools.check_phase57_ci_artifact_identity import (
    Phase57ArtifactIdentityFailure,
    check_phase57_artifact_identity,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _passing_shadow_payload(*, exact_code_head: str = "b" * 40) -> dict[str, object]:
    return {
        "digest": "a" * 64,
        "is_official_score": False,
        "acceptance_failures": [],
        "exact_code_head": exact_code_head,
        "campaign_seal_name": PHASE57_CAMPAIGN_SEAL_NAME,
        "original_v1_archive_sha256": PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
        "augmentation_manifest_sha256": PHASE57_CONTINUATION_MANIFEST_DIGEST,
        "expected_context_count": 100,
        "context_count": 100,
        "ledger_state_counts": [
            ["migration_refused", 0],
            ["projection_refused", 3],
            ["runtime_completed", 97],
            ["runtime_failed", 0],
            ["snapshot_rejected", 0],
        ],
        "all_shadow_correct": 50,
        "all_shadow_wrong": 0,
        "all_shadow_unscored": 0,
        "newly_solved_correct": 6,
        "newly_solved_wrong": 0,
        "newly_solved_unscored": 0,
        "forbidden_class_solve": 0,
        "regressed": 0,
        "query_binding_mismatch": 0,
    }


def _copy_fixture_set(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for source in DEFAULT_FIXTURE_ROOT.iterdir():
        (destination / source.name).write_bytes(source.read_bytes())


def _write_canonical_json(path: Path, payload: Any) -> str:
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_fixture_set_is_exact_public_only_and_reproducible() -> None:
    validate_fixture_set()
    assert {item.name for item in DEFAULT_FIXTURE_ROOT.iterdir()} == {
        "README.md",
        "public_adversarial.jsonl",
        "public_dev.jsonl",
        "sanitized_manifest.json",
        "schema.json",
    }
    assert_raw_corpus_is_not_committed(REPOSITORY_ROOT)

    archive = build_reproducible_archive_bytes()
    assert hashlib.sha256(archive).hexdigest() == PHASE57_REPRODUCIBLE_ARCHIVE_SHA256
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        assert package.namelist() == [
            "public_adversarial.jsonl",
            "public_dev.jsonl",
            "schema.json",
        ]
        assert all(item.compress_type == zipfile.ZIP_STORED for item in package.infolist())
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in package.infolist())


def test_fixture_population_and_source_only_manifest_identity() -> None:
    cases = load_public_fixture_cases()
    assert len(cases) == 100
    body, digest, selection_digest = build_continuation_manifest()
    assert digest == PHASE57_CONTINUATION_MANIFEST_DIGEST
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == (
        PHASE57_CONTINUATION_MANIFEST_FILE_SHA256
    )
    assert selection_digest == PHASE57_CONTINUATION_SELECTION_DIGEST
    payload = json.loads(body)
    assert len(payload["entries"]) == 9
    assert "answer" not in body.casefold()


def test_public_population_has_exactly_81_supported_contexts() -> None:
    cases = load_public_fixture_cases()
    supported = sum(
        scope_adjusted_expected_terminal(case, case_index=index)
        is Stage7ExpectedTerminal.accepted
        for index, case in enumerate(cases)
    )
    assert supported == 81


def test_materialized_archive_passes_existing_integrity_and_builder(tmp_path: Path) -> None:
    inputs = materialize_campaign_inputs(tmp_path)
    inventory = read_public_corpus_archive(
        inputs.corpus_archive,
        expected_sha256=PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
    )
    dev, adversarial = load_public_cases(inventory)
    assert (len(dev), len(adversarial)) == (84, 16)

    prepared = build_prepared_campaign(
        corpus_archive=inputs.corpus_archive,
        manifest=inputs.manifest,
        expected_corpus_sha256=PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
    )
    assert prepared.original_v1_archive_sha256 == PHASE57_REPRODUCIBLE_ARCHIVE_SHA256
    assert prepared.expected_context_count == 100
    assert sum(
        context.prepared_state.value == "runtime_completed"
        for context in prepared.runtime_input.contexts
    ) == 97


def test_campaign_seal_is_distinct_and_exact() -> None:
    seal = resolve_campaign_seal(PHASE57_CAMPAIGN_SEAL_NAME)
    assert seal == PHASE57_REPRODUCIBLE_CAMPAIGN_SEAL_V1
    assert seal is not None
    assert seal.original_v1_archive_sha256 == PHASE57_REPRODUCIBLE_ARCHIVE_SHA256
    assert seal.augmentation_manifest_digest == PHASE57_CONTINUATION_MANIFEST_DIGEST
    assert seal.augmentation_manifest_file_sha256 == (
        PHASE57_CONTINUATION_MANIFEST_FILE_SHA256
    )
    assert seal.expected_handle_set_digest == (
        "3aa6e0673dbddafe086bc9e04365141cbc994fce8f6066e989cb33795c04b025"
    )


def test_contract_never_relabels_historical_stage7_or_starts_stage8() -> None:
    contract = phase57_public_evaluation_contract()
    assert contract.fixture_set_digest == PHASE57_FIXTURE_SET_DIGEST
    assert contract.historical_phase56_stage7_status == (
        PHASE56_HISTORICAL_STAGE7_STATUS
    )
    assert contract.historical_phase56_stage8_status == (
        PHASE56_HISTORICAL_STAGE8_STATUS
    )
    assert contract.historical_manifest_available is False
    assert contract.historical_substitution_allowed is False
    assert contract.historical_acceptance_claimed is False
    assert contract.hidden_generalization_claimed is False
    assert contract.public_regression_measurement is True
    assert contract.thresholds.minimum_all_shadow_correct == 50
    assert contract.quality_targets.required_supported_correct == 81


def test_phase57_regression_floor_passes_while_quality_remains_in_progress() -> None:
    report = evaluate_phase57_shadow_report(
        _passing_shadow_payload(),
        exact_code_head="b" * 40,
        source_shadow_report_raw_sha256="c" * 64,
    )
    assert report.regression_acceptance == "PASS"
    assert report.regression_failures == ()
    assert report.quality_status == "IN_PROGRESS"
    assert "supported_correct:50<81" in report.quality_failures
    assert report.historical_phase56_stage7_status == (
        PHASE56_HISTORICAL_STAGE7_STATUS
    )
    assert report.historical_substitution_used is False


def test_phase57_quality_accepts_only_at_81_supported_correct() -> None:
    payload = _passing_shadow_payload()
    payload["all_shadow_correct"] = 81
    report = evaluate_phase57_shadow_report(
        payload,
        exact_code_head="b" * 40,
        source_shadow_report_raw_sha256="c" * 64,
    )
    assert report.regression_acceptance == "PASS"
    assert report.quality_status == "ACCEPTED"
    assert report.quality_failures == ()


def test_phase57_wrong_result_fails_regression_and_quality() -> None:
    payload = _passing_shadow_payload()
    payload["all_shadow_wrong"] = 1
    payload["acceptance_failures"] = ["all_shadow_wrong"]
    report = evaluate_phase57_shadow_report(
        payload,
        exact_code_head="b" * 40,
        source_shadow_report_raw_sha256="c" * 64,
    )
    assert report.regression_acceptance == "FAIL"
    assert "all_wrong_nonzero" in report.regression_failures
    assert "scorecard_acceptance_failed" in report.regression_failures
    assert report.quality_status == "IN_PROGRESS"


def test_duplicate_ledger_state_is_refused_as_malformed() -> None:
    payload = _passing_shadow_payload()
    payload["ledger_state_counts"] = [
        ["runtime_completed", 97],
        ["runtime_completed", 97],
    ]
    with pytest.raises(ValueError, match="ledger_state_counts_malformed"):
        evaluate_phase57_shadow_report(
            payload,
            exact_code_head="b" * 40,
            source_shadow_report_raw_sha256="c" * 64,
        )


def test_fixture_member_tamper_fails_closed(tmp_path: Path) -> None:
    _copy_fixture_set(tmp_path)
    (tmp_path / "public_dev.jsonl").write_bytes(
        (tmp_path / "public_dev.jsonl").read_bytes() + b"\n"
    )
    with pytest.raises(Phase57FixtureRefused, match="fixture_member_byte_count_mismatch"):
        validate_fixture_set(tmp_path)


def test_extra_directory_and_symlink_are_refused(tmp_path: Path) -> None:
    directory_case = tmp_path / "directory"
    _copy_fixture_set(directory_case)
    (directory_case / "unexpected").mkdir()
    with pytest.raises(Phase57FixtureRefused, match="fixture_member_set_mismatch"):
        validate_fixture_set(directory_case)

    symlink_case = tmp_path / "symlink"
    _copy_fixture_set(symlink_case)
    readme = symlink_case / "README.md"
    readme.unlink()
    try:
        readme.symlink_to(DEFAULT_FIXTURE_ROOT / "README.md")
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(Phase57FixtureRefused, match="fixture_member_not_regular"):
        validate_fixture_set(symlink_case)


def test_sanitized_manifest_raw_bytes_are_canonical(tmp_path: Path) -> None:
    _copy_fixture_set(tmp_path)
    manifest = tmp_path / "sanitized_manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(Phase57FixtureRefused, match="sanitized_manifest_content_mismatch"):
        validate_fixture_set(tmp_path)


def test_gate_report_is_aggregate_only_and_privacy_minimal() -> None:
    report = evaluate_phase57_shadow_report(
        _passing_shadow_payload(),
        exact_code_head="b" * 40,
        source_shadow_report_raw_sha256="c" * 64,
    )
    payload = phase57_gate_report_as_dict(report)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).casefold()
    for forbidden in (
        '"answer"',
        '"case_id"',
        '"expected_answer"',
        '"gold"',
        '"gold_answer"',
        '"problem_text"',
        '"scoring_handle"',
    ):
        assert forbidden not in encoded
    assert payload["external_model_calls"] == 0
    assert payload["private_heldout_text_accesses"] == 0
    assert payload["production_release_claimed"] is False


def test_production_image_does_not_copy_evaluation_or_fixture_inputs() -> None:
    dockerfile = (REPOSITORY_ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    copy_lines = [
        line.strip().casefold()
        for line in dockerfile.splitlines()
        if line.strip().casefold().startswith("copy ")
    ]
    assert copy_lines
    assert all("evaluation" not in line for line in copy_lines)
    assert all("tests" not in line for line in copy_lines)
    assert all("fixture" not in line for line in copy_lines)


def test_artifact_identity_checker_accepts_exact_aggregate_pair(tmp_path: Path) -> None:
    head = _git_head()
    report = evaluate_phase57_shadow_report(
        _passing_shadow_payload(exact_code_head=head),
        exact_code_head=head,
        source_shadow_report_raw_sha256="c" * 64,
    )
    report_path = tmp_path / "phase57-gate-report.json"
    report_raw_sha = _write_canonical_json(
        report_path, phase57_gate_report_as_dict(report)
    )
    status = Phase57RunnerStatusV1(
        exact_code_head=head,
        regression_acceptance="PASS",
        quality_status="IN_PROGRESS",
        inner_exit=0,
        sanitized_reason=None,
    )
    status_path = tmp_path / "phase57-runner-status.json"
    status_raw_sha = _write_canonical_json(
        status_path, phase57_runner_status_as_dict(status)
    )

    identity = check_phase57_artifact_identity(
        report_path=report_path,
        runner_status_path=status_path,
        expected_head_sha=head,
        expected_report_raw_sha256=report_raw_sha,
        expected_runner_status_raw_sha256=status_raw_sha,
        repository_root=REPOSITORY_ROOT,
    )
    assert identity["regression_acceptance"] == "PASS"
    assert identity["quality_status"] == "IN_PROGRESS"
    assert identity["report_exact_code_head"] == head


def test_artifact_identity_checker_rejects_byte_tamper(tmp_path: Path) -> None:
    head = _git_head()
    report = evaluate_phase57_shadow_report(
        _passing_shadow_payload(exact_code_head=head),
        exact_code_head=head,
        source_shadow_report_raw_sha256="c" * 64,
    )
    report_path = tmp_path / "phase57-gate-report.json"
    report_raw_sha = _write_canonical_json(
        report_path, phase57_gate_report_as_dict(report)
    )
    status = Phase57RunnerStatusV1(
        exact_code_head=head,
        regression_acceptance="PASS",
        quality_status="IN_PROGRESS",
        inner_exit=0,
        sanitized_reason=None,
    )
    status_path = tmp_path / "phase57-runner-status.json"
    status_raw_sha = _write_canonical_json(
        status_path, phase57_runner_status_as_dict(status)
    )
    report_path.write_bytes(report_path.read_bytes() + b" ")

    with pytest.raises(
        Phase57ArtifactIdentityFailure, match="gate_report_raw_sha256_mismatch"
    ):
        check_phase57_artifact_identity(
            report_path=report_path,
            runner_status_path=status_path,
            expected_head_sha=head,
            expected_report_raw_sha256=report_raw_sha,
            expected_runner_status_raw_sha256=status_raw_sha,
            repository_root=REPOSITORY_ROOT,
        )
