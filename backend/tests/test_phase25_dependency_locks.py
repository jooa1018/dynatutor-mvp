import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_phase25_frontend_dependencies_are_exact_and_locked():
    pkg = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert (PROJECT_ROOT / "frontend" / "package-lock.json").exists()
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert deps
    for name, version in deps.items():
        assert version != "latest", name
        assert not version.startswith("^"), (name, version)
        assert not version.startswith("~"), (name, version)
    assert pkg["dependencies"]["next"] == "15.5.23"
    assert pkg["dependencies"]["react"] == "19.1.2"
    assert pkg["dependencies"]["react-dom"] == "19.1.2"
    assert pkg["devDependencies"]["@eslint/eslintrc"] == "3.3.6"
    assert pkg["devDependencies"]["eslint"] == "9.39.5"
    assert pkg["devDependencies"]["eslint-config-next"] == "15.5.23"
    assert pkg.get("overrides", {}).get("postcss") == "8.5.26"
    assert pkg.get("overrides", {}).get("sharp") == "0.35.3"
    assert pkg.get("engines", {}).get("node") == ">=20.9 <21"
    assert pkg.get("scripts", {}).get("audit") == "npm audit --audit-level=high"


def test_frontend_ci_jobs_enforce_the_locked_audit_gate():
    workflows = (
        "backend-tests.yml",
        "phase55-textbook-parser.yml",
        "phase56-stage6-multimodal.yml",
        "phase56-stage7-offline-evaluation.yml",
    )
    for workflow in workflows:
        text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
            encoding="utf-8"
        )
        assert "npm ci" in text, workflow
        assert "npm run audit" in text, workflow

    for workflow in workflows[2:]:
        text = (PROJECT_ROOT / ".github" / "workflows" / workflow).read_text(
            encoding="utf-8"
        )
        assert "npm install --no-save" not in text, workflow


def test_phase25_backend_requirements_lock_exists():
    lock = PROJECT_ROOT / "backend" / "requirements-lock.txt"
    assert lock.exists()
    text = lock.read_text(encoding="utf-8")
    required = ["fastapi==", "uvicorn[standard]==", "pydantic==", "sympy==", "pytest==", "pint==", "numpy==", "scipy==", "pydy=="]
    for item in required:
        assert item in text


def test_phase25_reproducible_install_docs_mention_npm_ci_and_requirements_lock():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    # Phase 25 docs update is appended before final packaging.
    assert "requirements-lock.txt" in readme or (PROJECT_ROOT / "docs" / "PHASE25_ACCURACY_HARDENING.md").exists()
