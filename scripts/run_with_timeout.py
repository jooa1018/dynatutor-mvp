#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_CHILD: subprocess.Popen[bytes] | None = None
_KILL_AFTER_SECONDS = int(os.environ.get("DYNATUTOR_RUN_KILL_AFTER", "10"))


def process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _wait_for_process_group_exit(
    proc: subprocess.Popen[bytes],
    timeout_seconds: float,
) -> bool:
    """Wait for the whole session to disappear, reaping its leader as it exits."""
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while True:
        # poll() reaps the group leader. Without this, a dead leader may remain a
        # zombie and make killpg(pgid, 0) look alive for the full grace period.
        proc.poll()
        if not process_group_exists(proc.pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def terminate_process_group(
    proc: subprocess.Popen[bytes],
    *,
    reason: str,
    kill_after_seconds: float,
    log_prefix: str = "[run_with_timeout]",
) -> None:
    """Terminate every process in the child's session within a bounded grace period."""
    print(f"{log_prefix} {reason}; terminating process group", file=sys.stderr, flush=True)
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        proc.poll()
        return
    except Exception as exc:
        print(f"{log_prefix} SIGTERM failed: {exc}", file=sys.stderr, flush=True)

    if _wait_for_process_group_exit(proc, kill_after_seconds):
        print(f"{log_prefix} process group terminated with SIGTERM", flush=True)
        return

    print(
        f"{log_prefix} SIGTERM grace period expired; sending SIGKILL",
        file=sys.stderr,
        flush=True,
    )
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        proc.poll()
        return
    except Exception as exc:
        print(f"{log_prefix} SIGKILL failed: {exc}", file=sys.stderr, flush=True)
        return

    # SIGKILL cannot be caught. Keep this final wait short and bounded so a
    # pathological uninterruptible process can never pin the validation wrapper.
    final_wait = min(max(kill_after_seconds, 0.1), 1.0)
    if _wait_for_process_group_exit(proc, final_wait):
        print(f"{log_prefix} process group terminated with SIGKILL", flush=True)
    else:
        print(
            f"{log_prefix} process group still visible after SIGKILL; returning without waiting",
            file=sys.stderr,
            flush=True,
        )


def _handle_parent_signal(signum: int, _frame: object) -> None:
    proc = _CHILD
    if proc is not None and process_group_exists(proc.pid):
        terminate_process_group(
            proc,
            reason=f"received signal {signum}",
            kill_after_seconds=_KILL_AFTER_SECONDS,
        )
    raise SystemExit(128 + signum)


def main() -> int:
    global _CHILD

    if len(sys.argv) < 4 or sys.argv[2] != "--":
        print(
            "Usage: python scripts/run_with_timeout.py <timeout_seconds> -- <command...>",
            file=sys.stderr,
        )
        return 2

    try:
        timeout_seconds = int(sys.argv[1])
    except ValueError:
        print("timeout_seconds must be an integer", file=sys.stderr)
        return 2

    if timeout_seconds <= 0:
        print("timeout_seconds must be positive", file=sys.stderr)
        return 2

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _handle_parent_signal)
        except Exception:
            pass

    cmd = sys.argv[3:]
    root = Path(__file__).resolve().parents[1]
    run_cwd = Path(os.environ.get("DYNATUTOR_RUN_CWD", str(root))).resolve()
    print(f"[run_with_timeout] timeout={timeout_seconds}s", flush=True)
    print(f"[run_with_timeout] cwd={run_cwd}", flush=True)
    print(f"[run_with_timeout] command={' '.join(cmd)}", flush=True)

    proc = subprocess.Popen(
        cmd,
        cwd=str(run_cwd),
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    _CHILD = proc
    start = time.monotonic()

    try:
        while True:
            rc = proc.poll()
            if rc is not None:
                if process_group_exists(proc.pid):
                    # 자식이 정상 종료해도 손자(pytest 플러그인, esbuild service 등)가
                    # 프로세스 그룹에 남아 있으면 터미널/외부 timeout이 매달린다 (Phase 41).
                    terminate_process_group(
                        proc,
                        reason="command exited but process group is still alive",
                        kill_after_seconds=_KILL_AFTER_SECONDS,
                    )
                print(f"[run_with_timeout] command exited with code {rc}", flush=True)
                return int(rc)

            elapsed = time.monotonic() - start
            if elapsed > timeout_seconds:
                raise subprocess.TimeoutExpired(cmd, timeout_seconds)
            time.sleep(0.2)
    except subprocess.TimeoutExpired:
        terminate_process_group(
            proc,
            reason=f"timed out after {timeout_seconds}s",
            kill_after_seconds=_KILL_AFTER_SECONDS,
        )
        return 124
    finally:
        _CHILD = None


if __name__ == "__main__":
    sys.exit(main())
