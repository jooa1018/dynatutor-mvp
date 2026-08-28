"""Run the repository-reproducible Phase 57 public continuation campaign.

The command materializes both inputs from committed public fixtures, invokes
Phase M/V/R/G as separate processes, and evaluates two distinct dispositions:

* the regression gate controls the process exit and protects the 50-correct,
  zero-wrong baseline; and
* the quality gate remains ``IN_PROGRESS`` until all 81 supported contexts are
  correct.

Neither disposition changes historical Phase 56 Stage 7, which remains
``STAGE_7_IN_PROGRESS / NOT_ACCEPTED`` with Stage 8 not started.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
TOOLS_ROOT = BACKEND_ROOT / "tools"
SHADOW_ORCHESTRATOR = TOOLS_ROOT / "run_phase56_stage7_v2_shadow.py"
_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40}$")

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from evaluation.phase57_reproducible.contracts import (  # noqa: E402
    PHASE57_CAMPAIGN_SEAL_NAME,
    PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
)
from evaluation.phase57_reproducible.fixtures import (  # noqa: E402
    DEFAULT_FIXTURE_ROOT,
    Phase57FixtureRefused,
    materialize_campaign_inputs,
)
from evaluation.phase57_reproducible.gate import (  # noqa: E402
    Phase57RunnerStatusV1,
    evaluate_phase57_shadow_report,
    phase57_gate_report_as_dict,
    phase57_runner_status_as_dict,
)


PHASE57_FAILURE_EXIT = 2


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(body)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256(body)


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _assert_output_is_safe(path: Path) -> Path:
    output = path.resolve(strict=False)
    repository = REPOSITORY_ROOT.resolve()
    if output == repository or output.is_relative_to(repository):
        raise Phase57FixtureRefused("output_must_be_outside_repository")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise Phase57FixtureRefused("output_directory_not_empty")
    output.mkdir(parents=True, exist_ok=True)
    return output


def _write_runner_status(
    path: Path,
    *,
    exact_code_head: str,
    regression_acceptance: str,
    quality_status: str,
    inner_exit: int | None,
    reason: str | None,
) -> str:
    status = Phase57RunnerStatusV1(
        exact_code_head=exact_code_head,
        regression_acceptance=regression_acceptance,
        quality_status=quality_status,
        inner_exit=inner_exit,
        sanitized_reason=reason,
    )
    return _write_json(path, phase57_runner_status_as_dict(status))


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Best-effort cleanup of the full M/V/R/G process group after timeout."""

    if process.poll() is not None:
        return
    if os.name == "nt":  # pragma: no cover - hosted gate runs on Linux
        process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":  # pragma: no cover - hosted gate runs on Linux
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    process.wait(timeout=10)


def _run_inner_campaign(
    command: list[str],
    *,
    environment: dict[str, str],
    timeout_seconds: int,
) -> int:
    creationflags = 0
    start_new_session = os.name != "nt"
    if os.name == "nt":  # pragma: no cover - hosted gate runs on Linux
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        command,
        cwd=BACKEND_ROOT,
        env=environment,
        start_new_session=start_new_session,
        creationflags=creationflags,
    )
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--exact-code-head", type=str, required=True)
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
        help="repository public fixture directory; defaults to the frozen path",
    )
    parser.add_argument(
        "--runtime-timeout-seconds",
        type=int,
        default=2_400,
        help="upper bound for the complete M/V/R/G subprocess",
    )
    args = parser.parse_args()

    if not _HEAD_PATTERN.fullmatch(args.exact_code_head):
        parser.error("--exact-code-head must be a lowercase 40-character Git SHA")
    if not 1 <= args.runtime_timeout_seconds <= 3_600:
        parser.error("--runtime-timeout-seconds must be between 1 and 3600")
    try:
        actual_head = _git_head()
    except (OSError, subprocess.CalledProcessError):
        print(
            "PHASE57_REPRODUCIBLE_ACCEPTANCE=FAIL:exact_head_unavailable",
            file=sys.stderr,
        )
        return PHASE57_FAILURE_EXIT
    if actual_head != args.exact_code_head:
        print(
            "PHASE57_REPRODUCIBLE_ACCEPTANCE=FAIL:exact_head_mismatch",
            file=sys.stderr,
        )
        return PHASE57_FAILURE_EXIT

    try:
        output = _assert_output_is_safe(args.output_dir)
    except (OSError, Phase57FixtureRefused) as exc:
        print(f"PHASE57_REPRODUCIBLE_ACCEPTANCE=FAIL:{exc}", file=sys.stderr)
        return PHASE57_FAILURE_EXIT

    inputs_dir = output / "inputs"
    publication_root = output / "publication"
    verification_report = output / "phase57-prepare-verification.json"
    runtime_snapshot = output / "phase57-runtime-snapshot.json"
    redacted_view = output / "phase57-runtime-redacted.json"
    shadow_report = output / "phase57-shadow-report.json"
    scorecard = output / "phase57-scorecard.json"
    gate_report_path = output / "phase57-gate-report.json"
    runner_status_path = output / "phase57-runner-status.json"

    try:
        inputs = materialize_campaign_inputs(
            inputs_dir, fixture_root=args.fixture_root.resolve()
        )
    except (OSError, Phase57FixtureRefused, ValueError) as exc:
        reason = (
            str(exc) if isinstance(exc, Phase57FixtureRefused) else type(exc).__name__
        )
        _write_runner_status(
            runner_status_path,
            exact_code_head=args.exact_code_head,
            regression_acceptance="FAIL",
            quality_status="NOT_RUN",
            inner_exit=None,
            reason=reason,
        )
        print(f"PHASE57_REPRODUCIBLE_ACCEPTANCE=FAIL:{reason}", file=sys.stderr)
        return PHASE57_FAILURE_EXIT

    command = [
        sys.executable,
        str(SHADOW_ORCHESTRATOR),
        "--corpus-archive",
        str(inputs.corpus_archive),
        "--expected-corpus-sha256",
        PHASE57_REPRODUCIBLE_ARCHIVE_SHA256,
        "--manifest",
        str(inputs.manifest),
        "--publication-root",
        str(publication_root),
        "--verification-report",
        str(verification_report),
        "--runtime-snapshot",
        str(runtime_snapshot),
        "--redacted-view",
        str(redacted_view),
        "--shadow-report",
        str(shadow_report),
        "--scorecard",
        str(scorecard),
        "--exact-code-head",
        args.exact_code_head,
        "--campaign-seal",
        PHASE57_CAMPAIGN_SEAL_NAME,
        "--record-regressions",
    ]
    environment = os.environ.copy()
    pythonpath = environment.get("PYTHONPATH")
    environment.update(
        {
            "PYTHONPATH": (
                str(BACKEND_ROOT)
                if not pythonpath
                else os.pathsep.join((str(BACKEND_ROOT), pythonpath))
            ),
            "PYTHONHASHSEED": "0",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_BASE_URL": "",
            "ANTHROPIC_BASE_URL": "",
            "MECHANICS_MODELER_BASE_URL": "",
            "MECHANICS_FIGURE_BASE_URL": "",
        }
    )

    print("PHASE57_REPRODUCIBLE_INNER_COMMAND=" + " ".join(command), flush=True)
    try:
        inner_exit = _run_inner_campaign(
            command,
            environment=environment,
            timeout_seconds=args.runtime_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        _write_runner_status(
            runner_status_path,
            exact_code_head=args.exact_code_head,
            regression_acceptance="FAIL",
            quality_status="NOT_RUN",
            inner_exit=None,
            reason="inner_runtime_timeout",
        )
        print(
            "PHASE57_REPRODUCIBLE_ACCEPTANCE=FAIL:inner_runtime_timeout",
            file=sys.stderr,
        )
        return PHASE57_FAILURE_EXIT

    if inner_exit != 0:
        _write_runner_status(
            runner_status_path,
            exact_code_head=args.exact_code_head,
            regression_acceptance="FAIL",
            quality_status="NOT_RUN",
            inner_exit=inner_exit,
            reason="inner_campaign_failed",
        )
        print(
            f"PHASE57_REPRODUCIBLE_ACCEPTANCE=FAIL:inner_exit_{inner_exit}",
            file=sys.stderr,
        )
        return inner_exit

    try:
        shadow_raw = shadow_report.read_bytes()
        shadow_payload = json.loads(shadow_raw)
        report = evaluate_phase57_shadow_report(
            shadow_payload,
            exact_code_head=args.exact_code_head,
            source_shadow_report_raw_sha256=_sha256(shadow_raw),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _write_runner_status(
            runner_status_path,
            exact_code_head=args.exact_code_head,
            regression_acceptance="FAIL",
            quality_status="NOT_RUN",
            inner_exit=inner_exit,
            reason="phase57_gate_input_unreadable",
        )
        print(
            "PHASE57_REPRODUCIBLE_ACCEPTANCE=FAIL:phase57_gate_input_unreadable",
            file=sys.stderr,
        )
        print(f"PHASE57_REPRODUCIBLE_DETAIL={type(exc).__name__}", file=sys.stderr)
        return PHASE57_FAILURE_EXIT

    gate_payload = phase57_gate_report_as_dict(report)
    gate_report_raw_sha = _write_json(gate_report_path, gate_payload)
    runner_status_raw_sha = _write_runner_status(
        runner_status_path,
        exact_code_head=args.exact_code_head,
        regression_acceptance=report.regression_acceptance,
        quality_status=report.quality_status,
        inner_exit=inner_exit,
        reason=(
            None
            if report.regression_acceptance == "PASS"
            else "aggregate_regression_floor_failed"
        ),
    )

    print(f"PHASE57_REPRODUCIBLE_FIXTURE_SET_DIGEST={inputs.fixture_set_digest}")
    print(f"PHASE57_REPRODUCIBLE_ARCHIVE_SHA256={inputs.corpus_archive_sha256}")
    print(f"PHASE57_REPRODUCIBLE_MANIFEST_DIGEST={inputs.manifest_digest}")
    print(
        "PHASE57_REPRODUCIBLE_MANIFEST_FILE_SHA256="
        f"{inputs.manifest_file_sha256}"
    )
    print(
        "PHASE57_REPRODUCIBLE_SELECTION_DIGEST="
        f"{inputs.selection_identity_digest}"
    )
    print(f"PHASE57_REPRODUCIBLE_GATE_REPORT_DIGEST={report.digest}")
    print(f"PHASE57_REPRODUCIBLE_GATE_REPORT_RAW_SHA256={gate_report_raw_sha}")
    print(f"PHASE57_REPRODUCIBLE_RUNNER_STATUS_RAW_SHA256={runner_status_raw_sha}")
    print(f"PHASE57_REPRODUCIBLE_ALL_CORRECT={report.all_shadow_correct}")
    print(f"PHASE57_REPRODUCIBLE_SUPPORTED_TARGET={report.supported_correct_target}")
    print(f"PHASE57_REPRODUCIBLE_ALL_WRONG={report.all_shadow_wrong}")
    print(f"PHASE57_REPRODUCIBLE_ALL_UNSCORED={report.all_shadow_unscored}")
    print(
        "PHASE57_REPRODUCIBLE_NEWLY_SOLVED_CORRECT="
        f"{report.newly_solved_correct}"
    )
    print(f"PHASE57_REPRODUCIBLE_REGRESSED={report.regressed}")
    print(
        "PHASE57_REPRODUCIBLE_HISTORICAL_STAGE7_STATUS="
        "STAGE_7_IN_PROGRESS / NOT_ACCEPTED"
    )
    print("PHASE57_REPRODUCIBLE_HISTORICAL_STAGE8_STATUS=STAGE_8_NOT_STARTED")
    print("PHASE57_REPRODUCIBLE_HISTORICAL_SUBSTITUTION=false")
    print(f"PHASE57_REPRODUCIBLE_QUALITY={report.quality_status}")
    print(
        "PHASE57_REPRODUCIBLE_ACCEPTANCE="
        + (
            "PASS"
            if report.regression_acceptance == "PASS"
            else "FAIL:" + ",".join(report.regression_failures)
        )
    )
    return 0 if report.regression_acceptance == "PASS" else PHASE57_FAILURE_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
