from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def _exists(rel: str) -> bool:
    return (PROJECT_ROOT / rel).exists()


def _read(rel: str) -> str:
    path = PROJECT_ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _frontend_state() -> dict[str, Any]:
    package_json = _read("frontend/package.json")
    api_ts = _read("frontend/lib/api.ts")
    env_example = _read("frontend/.env.example")
    manifest = _read("frontend/public/manifest.webmanifest")

    return {
        "package_json_exists": _exists("frontend/package.json"),
        "package_lock_exists": _exists("frontend/package-lock.json"),
        "node_modules_exists": (FRONTEND_ROOT / "node_modules").exists(),
        "build_script_present": '"build"' in package_json and "scripts/build-static.js" in package_json,
        "supports_documented_api_env": "NEXT_PUBLIC_DYNATUTOR_API_BASE" in api_ts,
        "supports_legacy_api_env": "NEXT_PUBLIC_API_BASE" in api_ts,
        "env_example_documents_documented_api_env": "NEXT_PUBLIC_DYNATUTOR_API_BASE" in env_example,
        "does_not_expose_public_access_token": "NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN" not in env_example and "NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN" not in api_ts,
        "token_uses_local_storage": "localStorage" in api_ts and "x-dynatutor-token" in api_ts,
        "vercel_json_exists": _exists("frontend/vercel.json"),
        "vercel_output_is_out": "\"outputDirectory\": \"out\"" in _read("frontend/vercel.json"),
        "manifest_exists": _exists("frontend/public/manifest.webmanifest"),
        "manifest_standalone": '"display": "standalone"' in manifest,
        "icons_exist": _exists("frontend/public/icons/icon-192.png") and _exists("frontend/public/icons/icon-512.png") and _exists("frontend/public/icons/apple-touch-icon.png"),
    }


def _backend_state() -> dict[str, Any]:
    env_example = _read("backend/.env.example")
    return {
        "dockerfile_exists": _exists("backend/Dockerfile"),
        "procfile_exists": _exists("backend/Procfile"),
        "render_yaml_exists": _exists("render.yaml"),
        "backend_env_example_exists": _exists("backend/.env.example"),
        "access_token_documented": "DYNATUTOR_ACCESS_TOKEN" in env_example,
        "cors_documented": "DYNATUTOR_CORS_ORIGINS" in env_example,
        "llm_documented": "LLM_ENABLED" in env_example and "OPENAI_API_KEY" in env_example,
        "requirements_exist": _exists("backend/requirements.txt"),
        "requirements_dev_exist": _exists("backend/requirements-dev.txt"),
    }


def _docs_state() -> dict[str, Any]:
    required_docs = [
        "docs/PHASE24_FINAL_POLISH_DEPLOYMENT.md",
        "docs/DEPLOYMENT_GUIDE_PERSONAL.md",
        "docs/FINAL_LOCAL_RUNBOOK.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/KNOWN_LIMITATIONS.md",
    ]
    return {
        "required_docs": required_docs,
        "missing_docs": [d for d in required_docs if not _exists(d)],
        "release_manifest_exists": _exists("release_manifest_phase24.json"),
    }


def _scripts_state() -> dict[str, Any]:
    required_scripts = [
        "scripts/check_frontend_build.sh",
        "scripts/check_frontend_build_windows.bat",
        "scripts/final_local_check.sh",
        "scripts/final_local_check_windows.bat",
    ]
    return {
        "required_scripts": required_scripts,
        "missing_scripts": [s for s in required_scripts if not _exists(s)],
    }


def _try_frontend_build_check() -> dict[str, Any]:
    script = PROJECT_ROOT / "scripts" / "check_frontend_build.sh"
    if not script.exists():
        return {"attempted": False, "passed": False, "reason": "script missing"}
    proc = subprocess.run(["bash", str(script)], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=180)
    return {
        "attempted": True,
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "skipped_missing_dependencies": proc.returncode == 2,
        "stdout_tail": proc.stdout[-800:],
        "stderr_tail": proc.stderr[-800:],
    }


def audit(attempt_frontend_build: bool = False) -> dict[str, Any]:
    frontend = _frontend_state()
    backend = _backend_state()
    docs = _docs_state()
    scripts = _scripts_state()
    frontend_build = _try_frontend_build_check() if attempt_frontend_build else {"attempted": False, "passed": None, "reason": "not requested"}

    checks = {
        "frontend_package_ready": frontend["package_json_exists"] and frontend["build_script_present"] and frontend["vercel_output_is_out"],
        "frontend_env_compatible": frontend["supports_documented_api_env"] and frontend["env_example_documents_documented_api_env"] and frontend["does_not_expose_public_access_token"] and frontend["token_uses_local_storage"],
        "pwa_assets_ready": frontend["manifest_exists"] and frontend["manifest_standalone"] and frontend["icons_exist"],
        "backend_deploy_files_ready": backend["dockerfile_exists"] and backend["procfile_exists"] and backend["render_yaml_exists"],
        "backend_env_documented": backend["backend_env_example_exists"] and backend["access_token_documented"] and backend["cors_documented"],
        "docs_ready": not docs["missing_docs"] and docs["release_manifest_exists"],
        "scripts_ready": not scripts["missing_scripts"],
    }

    if attempt_frontend_build:
        # Missing node_modules is a known acceptable skip in this container, but
        # an actual build failure after dependencies are installed is not.
        checks["frontend_build_passed_or_dependency_skip"] = frontend_build["passed"] or frontend_build.get("skipped_missing_dependencies", False)

    return {
        "phase": "phase24",
        "overall_passed": all(checks.values()),
        "checks": checks,
        "frontend": frontend,
        "backend": backend,
        "docs": docs,
        "scripts": scripts,
        "frontend_build": frontend_build,
        "next_manual_steps": [
            "cd frontend && npm ci && npm run build",
            "Deploy backend with DYNATUTOR_ACCESS_TOKEN set",
            "Deploy frontend with NEXT_PUBLIC_DYNATUTOR_API_BASE set",
            "Open the frontend on iPhone Safari, enter token, Add to Home Screen",
        ],
    }


def main() -> int:
    attempt_frontend_build = "--attempt-frontend-build" in sys.argv
    report = audit(attempt_frontend_build=attempt_frontend_build)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
