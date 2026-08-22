#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_CHILD: subprocess.Popen[bytes] | None = None
_KILL_AFTER_SECONDS = int(os.environ.get("DYNATUTOR_RUN_KILL_AFTER", "10"))
_WINDOWS_JOBS: dict[int, int] = {}


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _JobBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("per_process_user_time_limit", ctypes.c_longlong),
            ("per_job_user_time_limit", ctypes.c_longlong),
            ("limit_flags", wintypes.DWORD),
            ("minimum_working_set_size", ctypes.c_size_t),
            ("maximum_working_set_size", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("read_operation_count", ctypes.c_ulonglong),
            ("write_operation_count", ctypes.c_ulonglong),
            ("other_operation_count", ctypes.c_ulonglong),
            ("read_transfer_count", ctypes.c_ulonglong),
            ("write_transfer_count", ctypes.c_ulonglong),
            ("other_transfer_count", ctypes.c_ulonglong),
        ]

    class _JobExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("basic_limit_information", _JobBasicLimitInformation),
            ("io_info", _IoCounters),
            ("process_memory_limit", ctypes.c_size_t),
            ("job_memory_limit", ctypes.c_size_t),
            ("peak_process_memory_used", ctypes.c_size_t),
            ("peak_job_memory_used", ctypes.c_size_t),
        ]

    class _JobBasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("total_user_time", ctypes.c_longlong),
            ("total_kernel_time", ctypes.c_longlong),
            ("this_period_total_user_time", ctypes.c_longlong),
            ("this_period_total_kernel_time", ctypes.c_longlong),
            ("total_page_fault_count", wintypes.DWORD),
            ("total_processes", wintypes.DWORD),
            ("active_processes", wintypes.DWORD),
            ("total_terminated_processes", wintypes.DWORD),
        ]

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _KERNEL32.CreateJobObjectW.restype = wintypes.HANDLE
    _KERNEL32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _KERNEL32.SetInformationJobObject.restype = wintypes.BOOL
    _KERNEL32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _KERNEL32.AssignProcessToJobObject.restype = wintypes.BOOL
    _KERNEL32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    _KERNEL32.QueryInformationJobObject.restype = wintypes.BOOL
    _KERNEL32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _KERNEL32.TerminateJobObject.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL


def _close_windows_job(pgid: int) -> None:
    handle = _WINDOWS_JOBS.pop(pgid, None)
    if handle is not None:
        _KERNEL32.CloseHandle(handle)


def _windows_job_active_processes(pgid: int) -> int | None:
    handle = _WINDOWS_JOBS.get(pgid)
    if handle is None:
        return None
    info = _JobBasicAccountingInformation()
    if not _KERNEL32.QueryInformationJobObject(
        handle,
        1,  # JobObjectBasicAccountingInformation
        ctypes.byref(info),
        ctypes.sizeof(info),
        None,
    ):
        return None
    return int(info.active_processes)


def attach_process_group(proc: subprocess.Popen[Any]) -> None:
    """Keep a Windows child tree in a kill-on-close job; POSIX uses its session."""
    if os.name != "nt":
        return
    handle = _KERNEL32.CreateJobObjectW(None, None)
    if not handle:
        return
    info = _JobExtendedLimitInformation()
    info.basic_limit_information.limit_flags = 0x00002000  # KILL_ON_JOB_CLOSE
    configured = _KERNEL32.SetInformationJobObject(
        handle,
        9,  # JobObjectExtendedLimitInformation
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    assigned = configured and _KERNEL32.AssignProcessToJobObject(handle, proc._handle)
    if not assigned:
        _KERNEL32.CloseHandle(handle)
        return
    _WINDOWS_JOBS[proc.pid] = int(handle)


def _parent_signals() -> tuple[signal.Signals, ...]:
    """Return the parent signals supported by the current platform."""
    names = ("SIGTERM", "SIGINT", "SIGHUP")
    return tuple(
        candidate
        for name in names
        if isinstance((candidate := getattr(signal, name, None)), signal.Signals)
    )


def process_group_exists(pgid: int) -> bool:
    if os.name == "nt":
        active = _windows_job_active_processes(pgid)
        if active is not None:
            if active == 0:
                _close_windows_job(pgid)
                return False
            return True
        try:
            os.kill(pgid, 0)
            return True
        except OSError:
            return False
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
    if os.name == "nt":
        handle = _WINDOWS_JOBS.get(proc.pid)
        if handle is not None and _KERNEL32.TerminateJobObject(handle, 1):
            proc.poll()
            _close_windows_job(proc.pid)
            print(f"{log_prefix} process tree terminated with Windows Job Object", flush=True)
            return
        completed = subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            text=True,
        )
        proc.poll()
        if completed.returncode == 0:
            print(f"{log_prefix} process tree terminated with taskkill", flush=True)
        else:
            print(
                f"{log_prefix} Windows process-tree termination failed: {completed.stderr.strip()}",
                file=sys.stderr,
                flush=True,
            )
        _close_windows_job(proc.pid)
        return
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

    for sig in _parent_signals():
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
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    attach_process_group(proc)
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
