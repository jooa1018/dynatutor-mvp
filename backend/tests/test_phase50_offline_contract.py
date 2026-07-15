from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = pytest.mark.regression


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def test_phase50_numeric_layer_is_not_imported_by_production_solve_path():
    production_files = (
        BACKEND_ROOT / "app" / "main.py",
        BACKEND_ROOT / "app" / "routes" / "solve.py",
        BACKEND_ROOT / "engine" / "__init__.py",
    )

    for path in production_files:
        source = path.read_text(encoding="utf-8")
        assert "engine.simulation" not in source, path
        assert "solve_ivp" not in source, path


def test_phase50_runtime_runner_declares_offline_and_no_answer_overwrite():
    runner = (
        BACKEND_ROOT / "tools" / "run_phase50_numeric_validation.py"
    ).read_text(encoding="utf-8")
    numeric_core = (
        BACKEND_ROOT / "engine" / "simulation" / "sympy_scipy.py"
    ).read_text(encoding="utf-8")

    assert '"offline_only": True' in numeric_core
    assert '"student_answer_overwrite": False' in numeric_core
    assert '"normal_solve_path_changed": False' in runner
    assert '"pydy_required": False' in runner
    assert "from app." not in runner
    assert "import pydy" not in runner


def test_phase50_scipy_is_locked_but_pydy_remains_optional():
    runtime_requirements = (
        BACKEND_ROOT / "requirements.txt"
    ).read_text(encoding="utf-8")
    locked_requirements = (
        BACKEND_ROOT / "requirements-lock.txt"
    ).read_text(encoding="utf-8")

    assert "scipy>=" in runtime_requirements
    assert "scipy==" in locked_requirements
    assert "pydy" not in (
        BACKEND_ROOT / "engine" / "simulation" / "sympy_scipy.py"
    ).read_text(encoding="utf-8")


def test_phase50_has_no_network_or_generated_report_in_fast_path():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(
            (BACKEND_ROOT / "engine" / "simulation").glob("*.py")
        )
    )

    assert "requests." not in sources
    assert "httpx." not in sources
    assert "urllib." not in sources
    assert "backend/reports" not in sources
    assert "subprocess" not in sources


def test_phase50_committed_report_is_runtime_generated_and_passed():
    report = json.loads(
        (
            BACKEND_ROOT / "reports" / "phase50_numeric_validation.json"
        ).read_text(encoding="utf-8")
    )

    assert report["status"] == "passed"
    assert report["passed"] is True
    assert report["summary"]["case_count"] == 7
    assert report["summary"]["passed_count"] == 7
    assert report["summary"]["scipy_trajectory_count"] == 7
    assert report["summary"]["offline_only"] is True
    assert report["summary"]["student_answer_overwrite"] is False
