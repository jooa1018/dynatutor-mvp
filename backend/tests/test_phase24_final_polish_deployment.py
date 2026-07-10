from pathlib import Path

from tools.run_phase24_deployment_audit import audit


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_phase24_deployment_audit_passes_without_frontend_build_attempt():
    report = audit(attempt_frontend_build=False)
    assert report["phase"] == "phase24"
    assert report["overall_passed"] is True
    assert report["checks"]["frontend_package_ready"] is True
    assert report["checks"]["frontend_env_compatible"] is True
    assert report["checks"]["pwa_assets_ready"] is True
    assert report["checks"]["backend_deploy_files_ready"] is True
    assert report["checks"]["docs_ready"] is True
    assert report["checks"]["scripts_ready"] is True


def test_phase24_frontend_env_names_are_compatible():
    api_ts = (PROJECT_ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    env_example = (PROJECT_ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_DYNATUTOR_API_BASE" in api_ts
    assert "NEXT_PUBLIC_API_BASE" in api_ts
    assert "NEXT_PUBLIC_DYNATUTOR_API_BASE" in env_example
    assert "NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN" not in env_example
    assert "NEXT_PUBLIC_DYNATUTOR_ACCESS_TOKEN" not in api_ts
    assert "localStorage" in api_ts


def test_phase24_pwa_assets_and_deployment_files_exist():
    required = [
        "frontend/public/manifest.webmanifest",
        "frontend/public/icons/icon-192.png",
        "frontend/public/icons/icon-512.png",
        "frontend/public/icons/apple-touch-icon.png",
        "frontend/vercel.json",
        "backend/Dockerfile",
        "backend/Procfile",
        "render.yaml",
    ]
    missing = [rel for rel in required if not (PROJECT_ROOT / rel).exists()]
    assert not missing


def test_phase24_final_scripts_and_docs_exist():
    required = [
        "scripts/check_frontend_build.sh",
        "scripts/check_frontend_build_windows.bat",
        "scripts/final_local_check.sh",
        "scripts/final_local_check_windows.bat",
        "docs/PHASE24_FINAL_POLISH_DEPLOYMENT.md",
        "docs/DEPLOYMENT_GUIDE_PERSONAL.md",
        "docs/FINAL_LOCAL_RUNBOOK.md",
        "release_manifest_phase24.json",
    ]
    missing = [rel for rel in required if not (PROJECT_ROOT / rel).exists()]
    assert not missing


def test_phase24_frontend_build_is_not_run_inside_pytest():
    # Phase 26 policy: pytest checks build wiring only.
    # The actual npm ci && npm run build runs through scripts/check_frontend_build.sh
    # or CI, with a timeout, so pytest cannot hang on Next.js trace collection.
    report = audit(attempt_frontend_build=False)
    assert report["frontend_build"]["attempted"] is False
    assert report["checks"]["frontend_package_ready"] is True
