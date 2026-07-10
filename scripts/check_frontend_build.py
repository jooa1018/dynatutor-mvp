#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from scripts.run_with_timeout import process_group_exists, terminate_process_group
except ModuleNotFoundError:
    # When invoked as `python scripts/check_frontend_build.py`, scripts/ is sys.path[0].
    from run_with_timeout import process_group_exists, terminate_process_group

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
timeout_seconds = int(os.environ.get("DYNATUTOR_FRONTEND_BUILD_TIMEOUT", "180"))
kill_after_seconds = int(os.environ.get("DYNATUTOR_FRONTEND_BUILD_KILL_AFTER", "10"))



def main() -> int:
    print(f"[frontend_build] cwd={FRONTEND}", flush=True)
    print(f"[frontend_build] timeout={timeout_seconds}s", flush=True)
    for stale_dir in (FRONTEND / ".next", FRONTEND / "out"):
        if stale_dir.exists():
            print(f"[frontend_build] removing stale build directory: {stale_dir.name}", flush=True)
            shutil.rmtree(stale_dir)

    # Inherit stdout/stderr instead of piping them through the parent. This still
    # streams frontend build output in real time and avoids pipe back-pressure hangs.
    env = os.environ.copy()
    env.setdefault("NEXT_TELEMETRY_DISABLED", "1")
    env.setdefault("CI", "1")
    proc = subprocess.Popen(
        ["npm", "run", "build"],
        cwd=str(FRONTEND),
        env=env,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    start = time.monotonic()
    try:
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            if time.monotonic() - start > timeout_seconds:
                raise subprocess.TimeoutExpired(proc.args, timeout_seconds)
            time.sleep(0.1)

        rc = proc.wait()
        if process_group_exists(proc.pid):
            # npm이 끝났는데 자식(esbuild service 등)이 살아 있으면 여기서 정리해야
            # 터미널/CI가 매달리지 않는다.
            terminate_process_group(
                proc,
                reason="npm exited but build process group is still alive",
                kill_after_seconds=kill_after_seconds,
                log_prefix="[frontend_build]",
            )
        print(f"[frontend_build] npm run build exited with code {rc}", flush=True)
        if rc == 0:
            # Phase 40: 종료 코드만 믿지 않고 산출물을 검증한다.
            expected = [FRONTEND / "out" / "index.html", FRONTEND / "out" / "assets" / "app.js"]
            missing = [str(f.relative_to(FRONTEND)) for f in expected if not f.exists()]
            if missing:
                print(f"[frontend_build] FAIL: build exited 0 but outputs missing: {missing}", file=sys.stderr, flush=True)
                return 1
            print("[frontend_build] outputs verified: out/index.html, out/assets/app.js", flush=True)
        return int(rc)
    except subprocess.TimeoutExpired:
        print(
            f"\n[frontend_build] timed out after {timeout_seconds}s",
            file=sys.stderr,
            flush=True,
        )
        terminate_process_group(
            proc,
            reason="timeout reached",
            kill_after_seconds=kill_after_seconds,
            log_prefix="[frontend_build]",
        )
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
