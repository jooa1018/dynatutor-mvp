"""Run the strict Stage 7 gate under the declared dependency lock.

This wraps `run_phase56_stage7_offline_gate.py` with the three things a strict
report needs in order to be reproducible rather than merely produced:

1. **A pinned interpreter.**  Every distribution in
   ``backend/requirements-lock.txt`` is installed at its exact version into a
   dedicated virtual environment, and the resolved versions are compared back
   against the lock before anything is measured.  A mismatch aborts; it never
   downgrades to a warning.
2. **A pinned source tree.**  The gate spawns pytest subprocesses, so a run
   against a working tree measures whatever is currently edited.  Measurement
   happens in a detached git worktree pinned to an exact commit.
3. **A stated environment.**  Credentials and provider base URLs are removed
   from the child environment rather than assumed absent, so the gate's own
   offline assertion is satisfied by construction instead of by luck.

It also runs Lane D twice on the way — once as the single test whose failure
under an unpinned FastAPI is what motivated this tool, and once as the whole
lane — so a Lane D result can be attributed to the engine or to the framework
without re-deriving which.

Read-only with respect to the repository: it creates a worktree and a virtual
environment outside it, writes reports to a caller-named directory, and never
edits, commits, or pushes source.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from evaluation.phase56_stage7.locked_environment import (  # noqa: E402
    ENVIRONMENT_WITNESS_DISTRIBUTIONS,
    build_locked_environment_record,
    offline_environment,
    offline_environment_is_clean,
)

LOCK_FILE = REPOSITORY_ROOT / "backend" / "requirements-lock.txt"

# The single Lane D test that failed under an unpinned FastAPI.  Named as a
# constant so the isolated re-run is part of the tool rather than a step a
# reader has to remember.
LANE_D_ISOLATED_TEST = (
    "tests/test_phase56_stage6_api_runtime_integration.py"
    "::test_openapi_registers_stage6_routes_exactly_once_and_unconfigured_is_typed_503"
)
LANE_D_SUITES: tuple[str, ...] = (
    "tests/test_phase56_stage6_api_runtime_integration.py",
    "tests/test_phase56_stage6_security_hardening.py",
    "tests/test_phase56_stage6_image_security.py",
    "tests/test_phase56_stage6_idempotency_conflicts.py",
    "tests/test_phase56_stage6_observability.py",
)


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    log: Path | None = None,
) -> int:
    printable = " ".join(command)
    print(f"$ {printable}", flush=True)
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    tail = (completed.stdout + completed.stderr).strip().splitlines()[-12:]
    for line in tail:
        print(f"  | {line}", flush=True)
    return completed.returncode


def _resolved_versions(python: Path, names: Sequence[str]) -> dict[str, str | None]:
    program = (
        "import json,importlib.metadata as m\n"
        "out={}\n"
        "for name in %r:\n"
        "    try: out[name]=m.version(name)\n"
        "    except Exception: out[name]=None\n"
        "print(json.dumps(out))\n" % (list(names),)
    )
    completed = subprocess.run(
        [str(python), "-c", program],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _python_version(python: Path) -> str:
    completed = subprocess.run(
        [str(python), "-c", "import platform;print(platform.python_version())"],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _venv_python_path(venv_root: Path, *, platform_name: str = os.name) -> Path:
    """Return the platform-native interpreter path for ``venv_root``."""

    if platform_name == "nt":
        return venv_root / "Scripts" / "python.exe"
    return venv_root / "bin" / "python"


def build_locked_interpreter(venv_root: Path, *, reuse: bool) -> Path:
    """Create (or reuse) a virtual environment holding exactly the lock."""

    python = _venv_python_path(venv_root)
    if python.exists() and reuse:
        print(f"reusing locked interpreter at {python}", flush=True)
        return python
    if venv_root.exists():
        shutil.rmtree(venv_root)
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_root)], check=True
    )
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "-r", str(LOCK_FILE)],
        check=True,
    )
    return python


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        required=True,
        help="exact commit to measure; a detached worktree is pinned to it",
    )
    parser.add_argument(
        "--corpus-archive",
        type=Path,
        required=True,
        help="authorised public corpus zip, outside the repository",
    )
    parser.add_argument(
        "--reports",
        type=Path,
        required=True,
        help="out-of-repository directory for the strict report and logs",
    )
    parser.add_argument(
        "--venv",
        type=Path,
        default=Path("/root/stage7_locked_venv"),
        help="virtual environment root holding the lock",
    )
    parser.add_argument(
        "--worktree",
        type=Path,
        default=Path("/root/stage7_measure"),
        help="detached measurement worktree root",
    )
    parser.add_argument(
        "--reuse-venv",
        action="store_true",
        help="reuse an existing locked interpreter instead of rebuilding it",
    )
    args = parser.parse_args()

    reports: Path = args.reports
    reports.mkdir(parents=True, exist_ok=True)
    logs = reports / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    python = build_locked_interpreter(args.venv, reuse=args.reuse_venv)
    lock_text = LOCK_FILE.read_text(encoding="utf-8")
    wanted = sorted(
        {
            *(
                line.split("==")[0].split("[")[0].strip()
                for line in lock_text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ),
            *ENVIRONMENT_WITNESS_DISTRIBUTIONS,
        }
    )
    record = build_locked_environment_record(
        python_version=_python_version(python),
        lock_file=str(LOCK_FILE.relative_to(REPOSITORY_ROOT)),
        lock_text=lock_text,
        resolved=_resolved_versions(python, wanted),
    )
    environment_path = reports / "stage7_locked_environment.json"
    environment_path.write_text(
        json.dumps(
            record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"locked environment recorded at {environment_path}", flush=True)
    if not record.locked:
        for mismatch in record.mismatches:
            print(
                f"LOCK MISMATCH {mismatch.canonical_name}: "
                f"required {mismatch.required_version}, "
                f"resolved {mismatch.resolved_version or 'MISSING'}",
                flush=True,
            )
        print("STAGE7_LOCKED_STRICT=ABORTED_LOCK_MISMATCH", flush=True)
        return 2

    worktree: Path = args.worktree
    if not (worktree / ".git").exists():
        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--detach",
                str(worktree),
                args.commit,
            ],
            cwd=str(REPOSITORY_ROOT),
            check=True,
        )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not head.startswith(args.commit) and not args.commit.startswith(head):
        print(
            f"worktree at {worktree} is pinned to {head}, not {args.commit}",
            flush=True,
        )
        print("STAGE7_LOCKED_STRICT=ABORTED_WRONG_HEAD", flush=True)
        return 2
    backend = worktree / "backend"

    env = offline_environment(dict(os.environ))
    env["STAGE7_PUBLIC_CORPUS_PATH"] = str(args.corpus_archive.resolve())
    if not offline_environment_is_clean(env):
        print("STAGE7_LOCKED_STRICT=ABORTED_DIRTY_ENVIRONMENT", flush=True)
        return 2

    results: dict[str, Any] = {"exact_head_sha": head}

    print("\n== Lane D, the isolated test ==", flush=True)
    results["lane_d_isolated_returncode"] = _run(
        [str(python), "-m", "pytest", LANE_D_ISOLATED_TEST, "-q", "-p", "no:warnings"],
        cwd=backend,
        env=env,
        log=logs / "lane_d_isolated.log",
    )

    print("\n== Lane D, the whole lane ==", flush=True)
    results["lane_d_suite_returncode"] = _run(
        [str(python), "-m", "pytest", *LANE_D_SUITES, "-q", "-p", "no:warnings"],
        cwd=backend,
        env=env,
        log=logs / "lane_d_suite.log",
    )

    print("\n== strict public-100 ==", flush=True)
    strict_report = reports / "stage7_strict__locked.json"
    results["strict_returncode"] = _run(
        [
            str(python),
            "tools/run_phase56_stage7_offline_gate.py",
            "--output",
            str(strict_report),
            "--require-public-corpus",
            "--require-full-stage7",
        ],
        cwd=backend,
        env=env,
        log=logs / "strict_locked.log",
    )

    summary_path = reports / "stage7_locked_strict_summary.json"
    summary_path.write_text(
        json.dumps(results, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    lane_d_pass = (
        results["lane_d_isolated_returncode"] == 0
        and results["lane_d_suite_returncode"] == 0
    )
    print(f"\nSTAGE7_LOCKED_HEAD={head}", flush=True)
    print(f"STAGE7_LOCKED_LANE_D={'PASS' if lane_d_pass else 'FAIL'}", flush=True)
    # Strict exits 2 while Stage 7 is incomplete, so its return code is
    # reported rather than converted into this tool's success condition.
    print(f"STAGE7_LOCKED_STRICT_EXIT={results['strict_returncode']}", flush=True)
    print(f"STAGE7_LOCKED_STRICT_REPORT={strict_report}", flush=True)
    return 0 if lane_d_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
