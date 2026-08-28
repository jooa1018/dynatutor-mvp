"""Verify the exact-head identity and privacy boundary of Phase 57 CI artifacts.

The Phase 57 workflow uploads only a small aggregate report and runner status.
This checker re-opens those exact bytes immediately before upload and refuses
unless they describe the checked-out commit, retain the Phase 56 historical
non-acceptance boundary, pass the independently recomputed regression floor,
and contain no per-case/gold/private payload keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evaluation.phase57_reproducible.contracts import (  # noqa: E402
    PHASE56_HISTORICAL_STAGE7_STATUS,
    PHASE56_HISTORICAL_STAGE8_STATUS,
    phase57_public_evaluation_contract,
)
from evaluation.phase57_reproducible.gate import (  # noqa: E402
    Phase57GateReportV1,
    Phase57RunnerStatusV1,
)


_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "case_id",
        "expected_answer",
        "gold",
        "gold_answer",
        "numeric_answer",
        "private_case",
        "private_heldout",
        "private_text",
        "problem_text",
        "scoring_handle",
    }
)


class Phase57ArtifactIdentityFailure(RuntimeError):
    """Named fail-closed artifact refusal."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _git_head(repository_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Phase57ArtifactIdentityFailure(
            "checkout_head_unavailable", type(exc).__name__
        ) from exc
    value = completed.stdout.strip()
    if not _GIT_SHA.fullmatch(value):
        raise Phase57ArtifactIdentityFailure("checkout_head_malformed", repr(value))
    return value


def _read_exact(path: Path, *, kind: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise Phase57ArtifactIdentityFailure(f"{kind}_missing", str(path))
    try:
        return path.read_bytes()
    except OSError as exc:
        raise Phase57ArtifactIdentityFailure(
            f"{kind}_unreadable", type(exc).__name__
        ) from exc


def _verify_raw_sha(raw: bytes, expected: str, *, kind: str) -> str:
    if not _SHA256.fullmatch(expected):
        raise Phase57ArtifactIdentityFailure(
            f"{kind}_expected_raw_sha256_malformed", repr(expected)
        )
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise Phase57ArtifactIdentityFailure(
            f"{kind}_raw_sha256_mismatch", f"{actual} != {expected}"
        )
    return actual


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise Phase57ArtifactIdentityFailure(
                "artifact_duplicate_json_key", key
            )
        output[key] = value
    return output


def _parse_object(raw: bytes, *, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_object_keys
        )
    except Phase57ArtifactIdentityFailure:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase57ArtifactIdentityFailure(
            f"{kind}_malformed_json", type(exc).__name__
        ) from exc
    if not isinstance(payload, dict):
        raise Phase57ArtifactIdentityFailure(
            f"{kind}_not_object", type(payload).__name__
        )
    return payload


def _scan_forbidden_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.casefold() in _FORBIDDEN_KEYS:
                raise Phase57ArtifactIdentityFailure(
                    "artifact_forbidden_key", f"{path}.{key}"
                )
            _scan_forbidden_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden_keys(nested, path=f"{path}[{index}]")


def _parse_report(raw: bytes) -> tuple[Phase57GateReportV1, str]:
    document = _parse_object(raw, kind="gate_report")
    _scan_forbidden_keys(document)
    digest = document.pop("digest", None)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise Phase57ArtifactIdentityFailure("gate_report_digest_malformed")
    try:
        report = Phase57GateReportV1.model_validate_json(
            json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        )
    except ValueError as exc:
        raise Phase57ArtifactIdentityFailure(
            "gate_report_schema_invalid", type(exc).__name__
        ) from exc
    if report.digest != digest:
        raise Phase57ArtifactIdentityFailure(
            "gate_report_content_digest_mismatch", f"{report.digest} != {digest}"
        )
    return report, digest


def _parse_runner_status(raw: bytes) -> Phase57RunnerStatusV1:
    document = _parse_object(raw, kind="runner_status")
    _scan_forbidden_keys(document)
    try:
        return Phase57RunnerStatusV1.model_validate_json(
            json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        )
    except ValueError as exc:
        raise Phase57ArtifactIdentityFailure(
            "runner_status_schema_invalid", type(exc).__name__
        ) from exc


def _recompute_regression_floor(report: Phase57GateReportV1) -> None:
    thresholds = phase57_public_evaluation_contract().thresholds
    failures: list[str] = []
    if report.expected_context_count != thresholds.expected_context_count:
        failures.append("expected_context_count")
    if report.context_count != report.runtime_completed:
        failures.append("context_count")
    if report.runtime_completed != thresholds.expected_runtime_completed:
        failures.append("runtime_completed")
    if report.projection_refused != thresholds.expected_projection_refused:
        failures.append("projection_refused")
    if report.all_shadow_correct < thresholds.minimum_all_shadow_correct:
        failures.append("all_shadow_correct")
    if report.newly_solved_correct < thresholds.minimum_newly_solved_correct:
        failures.append("newly_solved_correct")
    for field, maximum in (
        ("all_shadow_wrong", thresholds.maximum_all_shadow_wrong),
        ("all_shadow_unscored", thresholds.maximum_all_shadow_unscored),
        ("newly_solved_wrong", thresholds.maximum_newly_solved_wrong),
        ("newly_solved_unscored", thresholds.maximum_newly_solved_unscored),
        ("forbidden_class_solve", thresholds.maximum_forbidden_class_solve),
        ("regressed", thresholds.maximum_regressed),
        ("query_binding_mismatch", thresholds.maximum_query_binding_mismatch),
    ):
        if getattr(report, field) > maximum:
            failures.append(field)
    if failures:
        raise Phase57ArtifactIdentityFailure(
            "gate_report_regression_floor_failed", ",".join(sorted(failures))
        )


def _check_quality_disposition(report: Phase57GateReportV1) -> None:
    target = phase57_public_evaluation_contract().quality_targets
    expected = (
        "ACCEPTED"
        if report.all_shadow_correct >= target.required_supported_correct
        else "IN_PROGRESS"
    )
    if report.quality_status != expected:
        raise Phase57ArtifactIdentityFailure(
            "gate_report_quality_status_inconsistent",
            f"{report.quality_status} != {expected}",
        )


def check_phase57_artifact_identity(
    *,
    report_path: Path,
    runner_status_path: Path,
    expected_head_sha: str,
    expected_report_raw_sha256: str,
    expected_runner_status_raw_sha256: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, str]:
    """Return exact identities or raise the first fail-closed refusal."""

    if not _GIT_SHA.fullmatch(expected_head_sha):
        raise Phase57ArtifactIdentityFailure(
            "expected_head_sha_malformed", repr(expected_head_sha)
        )
    checkout_head = _git_head(repository_root)
    if checkout_head != expected_head_sha:
        raise Phase57ArtifactIdentityFailure(
            "checkout_head_mismatch", f"{checkout_head} != {expected_head_sha}"
        )

    report_raw = _read_exact(report_path, kind="gate_report")
    report_raw_sha = _verify_raw_sha(
        report_raw, expected_report_raw_sha256, kind="gate_report"
    )
    report, report_content_digest = _parse_report(report_raw)

    status_raw = _read_exact(runner_status_path, kind="runner_status")
    status_raw_sha = _verify_raw_sha(
        status_raw, expected_runner_status_raw_sha256, kind="runner_status"
    )
    status = _parse_runner_status(status_raw)

    if report.exact_code_head != checkout_head:
        raise Phase57ArtifactIdentityFailure(
            "gate_report_head_mismatch",
            f"{report.exact_code_head} != {checkout_head}",
        )
    if status.exact_code_head != checkout_head:
        raise Phase57ArtifactIdentityFailure(
            "runner_status_head_mismatch",
            f"{status.exact_code_head} != {checkout_head}",
        )
    if report.historical_phase56_stage7_status != PHASE56_HISTORICAL_STAGE7_STATUS:
        raise Phase57ArtifactIdentityFailure("historical_stage7_status_changed")
    if report.historical_phase56_stage8_status != PHASE56_HISTORICAL_STAGE8_STATUS:
        raise Phase57ArtifactIdentityFailure("historical_stage8_status_changed")
    if report.regression_acceptance != "PASS" or report.regression_failures:
        raise Phase57ArtifactIdentityFailure("gate_report_regression_not_pass")
    if status.regression_acceptance != report.regression_acceptance:
        raise Phase57ArtifactIdentityFailure("runner_report_regression_mismatch")
    if status.quality_status != report.quality_status:
        raise Phase57ArtifactIdentityFailure("runner_report_quality_mismatch")
    if status.inner_exit != 0 or status.sanitized_reason is not None:
        raise Phase57ArtifactIdentityFailure("runner_status_not_clean")

    _recompute_regression_floor(report)
    _check_quality_disposition(report)

    return {
        "expected_head_sha": expected_head_sha,
        "checkout_head_sha": checkout_head,
        "report_exact_code_head": report.exact_code_head,
        "report_raw_sha256": report_raw_sha,
        "report_content_digest": report_content_digest,
        "runner_status_raw_sha256": status_raw_sha,
        "regression_acceptance": report.regression_acceptance,
        "quality_status": report.quality_status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--runner-status", type=Path, required=True)
    parser.add_argument("--expect-head-sha", required=True)
    parser.add_argument("--expect-report-raw-sha256", required=True)
    parser.add_argument("--expect-runner-status-raw-sha256", required=True)
    args = parser.parse_args(argv)

    try:
        identity = check_phase57_artifact_identity(
            report_path=args.report,
            runner_status_path=args.runner_status,
            expected_head_sha=args.expect_head_sha,
            expected_report_raw_sha256=args.expect_report_raw_sha256,
            expected_runner_status_raw_sha256=(
                args.expect_runner_status_raw_sha256
            ),
        )
    except Phase57ArtifactIdentityFailure as exc:
        print(f"PHASE57_ARTIFACT_IDENTITY=FAIL:{exc.code}", file=sys.stderr)
        if exc.detail:
            print(f"PHASE57_ARTIFACT_IDENTITY_DETAIL={exc.detail}", file=sys.stderr)
        return 2

    print("PHASE57_ARTIFACT_IDENTITY=PASS")
    for key, value in identity.items():
        print(f"PHASE57_ARTIFACT_{key.upper()}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
