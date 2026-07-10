#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python - <<'PY'
import json
from pathlib import Path

root = Path.cwd()
frontend = root / "frontend"
pkg_path = frontend / "package.json"
lock_path = frontend / "package-lock.json"
build_script = root / "scripts" / "check_frontend_build.sh"
build_wrapper = root / "scripts" / "check_frontend_build.py"
timeout_wrapper = root / "scripts" / "run_with_timeout.py"
next_config = frontend / "next.config.js"

assert pkg_path.exists(), "frontend/package.json missing"
assert lock_path.exists(), "frontend/package-lock.json missing"
assert build_script.exists(), "scripts/check_frontend_build.sh missing"
assert build_wrapper.exists(), "scripts/check_frontend_build.py missing"
assert timeout_wrapper.exists(), "scripts/run_with_timeout.py missing"
assert next_config.exists(), "frontend/next.config.js missing"

pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
assert "build" in pkg.get("scripts", {}), "frontend build script missing"

deps = {}
deps.update(pkg.get("dependencies", {}))
deps.update(pkg.get("devDependencies", {}))
for name, version in deps.items():
    assert version != "latest", f"{name} uses latest"
    assert not version.startswith("^"), f"{name} is not exact: {version}"
    assert not version.startswith("~"), f"{name} is not exact: {version}"

script_text = build_script.read_text(encoding="utf-8")
wrapper_text = build_wrapper.read_text(encoding="utf-8")
timeout_text = timeout_wrapper.read_text(encoding="utf-8")
config_text = next_config.read_text(encoding="utf-8")
assert "check_frontend_build.py" in script_text, "build Python wrapper missing from shell script"
assert "timeout --kill-after" not in script_text, "shell script must not wrap Python build wrapper with GNU timeout"
assert "start_new_session=True" in wrapper_text, "process-group session start missing"
assert "terminate_process_group(" in wrapper_text, "shared process-group termination missing"
assert "process_group_exists(" in wrapper_text, "shared process-group liveness check missing"
assert "os.killpg" in timeout_text, "process-group kill missing from shared helper"
assert "subprocess.run" not in wrapper_text, "subprocess.run must not be used for frontend build wrapper"
assert "standalone" not in config_text, "standalone output tracing must stay disabled"
print("frontend metadata check passed")
PY
