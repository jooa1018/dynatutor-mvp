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


def _process_group_exists(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _kill_process_group(proc: subprocess.Popen[bytes], *, reason: str) -> None:
    print(f"[run_with_timeout] {reason}; killing process group", file=sys.stderr, flush=True)
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=_KILL_AFTER_SECONDS)
        print("[run_with_timeout] process group terminated with SIGTERM", flush=True)
        return
    except ProcessLookupError:
        return
    except Exception:
        print(
            "[run_with_timeout] SIGTERM did not finish; sending SIGKILL",
            file=sys.stderr,
            flush=True,
        )

    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception as exc:
        print(f"[run_with_timeout] SIGKILL failed: {exc}", file=sys.stderr, flush=True)
        return

    try:
        proc.wait(timeout=_KILL_AFTER_SECONDS)
    except Exception:
        pass


def _handle_parent_signal(signum: int, _frame: object) -> None:
    proc = _CHILD
    if proc is not None and proc.poll() is None:
        _kill_process_group(proc, reason=f"received signal {signum}")
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
                if _process_group_exists(proc.pid):
                    # 자식이 정상 종료해도 손자(pytest 플러그인, esbuild service 등)가
                    # 프로세스 그룹에 남아 있으면 터미널/외부 timeout이 매달린다 (Phase 41).
                    _kill_process_group(proc, reason="command exited but process group is still alive")
                print(f"[run_with_timeout] command exited with code {rc}", flush=True)
                return int(rc)

            elapsed = time.monotonic() - start
            if elapsed > timeout_seconds:
                raise subprocess.TimeoutExpired(cmd, timeout_seconds)
            time.sleep(0.2)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc, reason=f"timed out after {timeout_seconds}s")
        return 124
    finally:
        _CHILD = None


if __name__ == "__main__":
    sys.exit(main())
