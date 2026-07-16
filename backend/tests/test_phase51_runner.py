from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from tools.chrono_validation import chrono_compat
from tools.chrono_validation import phase51_runner


def _missing_import(name: str):
    raise ModuleNotFoundError(
        f"No module named {name!r}",
        name="pychrono",
    )


@pytest.mark.unit
def test_phase51_runner_missing_dependency_is_honest_and_deterministic(monkeypatch):
    monkeypatch.setattr(chrono_compat.importlib, "import_module", _missing_import)
    first = phase51_runner.run_phase51_suite()
    second = phase51_runner.run_phase51_suite()

    assert first["status"] == "skipped"
    assert first["passed"] is False
    assert first["summary"]["case_count"] == 6
    assert first["summary"]["product_comparison_count"] == 5
    assert first["summary"]["chrono_statuses"] == {
        "passed": 0,
        "failed": 0,
        "skipped": 6,
        "error": 0,
    }
    assert first["product_answer_overwrite"] is False
    assert first["cross_checks"]["normal_solve_imported_pychrono"] is False
    assert first["normal_runtime_dependency"] is False
    assert phase51_runner.json_report_text(first) == phase51_runner.json_report_text(second)
    assert phase51_runner.markdown_report_text(first) == phase51_runner.markdown_report_text(second)
    assert "manual_required" not in phase51_runner.json_report_text(first)
    assert json.loads(phase51_runner.json_report_text(first)) == first


@pytest.mark.unit
def test_phase51_strict_rejects_skipped_results(monkeypatch, capsys):
    monkeypatch.setattr(chrono_compat.importlib, "import_module", _missing_import)
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase51_runner.py", "--mode", "chrono", "--strict", "--no-write"],
    )
    assert phase51_runner.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "skipped"
    assert payload["passed"] is False


@pytest.mark.unit
def test_phase51_non_strict_missing_dependency_can_report_without_breaking_app(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(chrono_compat.importlib, "import_module", _missing_import)
    monkeypatch.setattr(
        sys,
        "argv",
        ["phase51_runner.py", "--mode", "auto", "--no-write"],
    )
    assert phase51_runner.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["chrono_statuses"]["skipped"] == 6


@pytest.mark.unit
def test_phase51_report_writer_is_byte_deterministic(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(chrono_compat.importlib, "import_module", _missing_import)
    payload = phase51_runner.run_phase51_suite()
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    phase51_runner.write_reports(
        payload,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    first_json = json_path.read_bytes()
    first_markdown = markdown_path.read_bytes()
    phase51_runner.write_reports(
        payload,
        json_path=json_path,
        markdown_path=markdown_path,
    )

    assert json_path.read_bytes() == first_json
    assert markdown_path.read_bytes() == first_markdown
    assert json.loads(first_json.decode("utf-8"))["passed"] is False
