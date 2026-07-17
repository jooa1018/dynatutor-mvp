from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import measure_pr10_hotfix_performance as performance


HEAD_SHA = "a" * 40
BASE_SHA = "b" * 40
METRICS = ("route", "solve_total")


def _raw_measurement(
    *,
    label: str,
    round_number: int,
    position: int,
    values: dict[str, list[float]],
    repeats: int = 60,
    warmups: int = 10,
    sha: str | None = None,
) -> dict:
    return {
        "schema_version": 2,
        "mode": "raw_measurement",
        "metadata": {
            "revision_label": label,
            "revision_sha": sha or (HEAD_SHA if label == "head" else BASE_SHA),
            "round_number": round_number,
            "position": position,
            "repeats": repeats,
            "warmups": warmups,
        },
        "metrics": {
            name: {
                "samples": repeats,
                "raw_samples_ms": samples,
            }
            for name, samples in values.items()
        },
    }


def _write_balanced_rounds(
    directory: Path,
    *,
    base_values: list[float],
    head_values: list[float],
) -> dict[tuple[int, str], Path]:
    paths: dict[tuple[int, str], Path] = {}
    for round_number in range(1, 5):
        head_position = 1 if round_number % 2 else 2
        for label, position, samples in (
            ("head", head_position, head_values),
            ("base", 3 - head_position, base_values),
        ):
            path = directory / f"round-{round_number}-{label}.json"
            path.write_text(
                json.dumps(
                    _raw_measurement(
                        label=label,
                        round_number=round_number,
                        position=position,
                        values={name: list(samples) for name in METRICS},
                    )
                ),
                encoding="utf-8",
            )
            paths[(round_number, label)] = path
    return paths


def _compare(directory: Path) -> dict:
    return performance.compare_round_dir(
        directory,
        expected_rounds=4,
        expected_head_sha=HEAD_SHA,
        expected_base_sha=BASE_SHA,
        max_regression=15.0,
    )


def _mutate_json(path: Path, mutate) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    ("base_ms", "head_ms", "expected_passed"),
    (
        (10.0, 11.6, False),
        (10.0, 11.5, True),
        (5.0, 6.0, True),
    ),
)
def test_pooled_gate_preserves_percent_and_absolute_boundaries(
    tmp_path: Path,
    base_ms: float,
    head_ms: float,
    expected_passed: bool,
) -> None:
    _write_balanced_rounds(
        tmp_path,
        base_values=[base_ms] * 60,
        head_values=[head_ms] * 60,
    )

    result = _compare(tmp_path)

    assert result["passed"] is expected_passed
    assert bool(result["regressions"]) is not expected_passed
    assert result["comparisons"]["solve_total"]["base_p95_ms"] == base_ms
    assert result["comparisons"]["solve_total"]["head_p95_ms"] == head_ms


def test_one_round_tail_spikes_are_diagnostic_not_a_pooled_false_failure(
    tmp_path: Path,
) -> None:
    paths = _write_balanced_rounds(
        tmp_path,
        base_values=[10.0] * 60,
        head_values=[10.0] * 60,
    )

    def add_four_tail_spikes(data: dict) -> None:
        for metric in data["metrics"].values():
            metric["raw_samples_ms"][-4:] = [20.0] * 4

    _mutate_json(paths[(1, "head")], add_four_tail_spikes)

    result = _compare(tmp_path)

    assert result["passed"] is True
    assert result["comparisons"]["solve_total"]["head_p95_ms"] == 10.0
    first_round = result["round_diagnostics"][0]
    assert "solve_total" in first_round["regressions"]
    assert first_round["comparisons"]["solve_total"]["head_p95_ms"] == 20.0


def test_balanced_alternation_cancels_equal_position_one_penalty(
    tmp_path: Path,
) -> None:
    paths = _write_balanced_rounds(
        tmp_path,
        base_values=[10.0] * 60,
        head_values=[10.0] * 60,
    )
    for (round_number, label), path in paths.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["metadata"]["position"] == 1:
            for metric in data["metrics"].values():
                metric["raw_samples_ms"] = [12.0] * 60
        path.write_text(json.dumps(data), encoding="utf-8")

    result = _compare(tmp_path)

    assert result["passed"] is True
    assert result["schema_version"] == 2
    assert result["mode"] == "pooled_comparison"
    assert result["revision_shas"] == {"head": HEAD_SHA, "base": BASE_SHA}
    assert result["rounds"] == 4
    assert result["repeats_per_round"] == 60
    assert result["warmups_per_round"] == 10
    assert result["sample_counts"]["head"]["solve_total"] == 240
    assert result["sample_counts"]["base"]["solve_total"] == 240
    assert result["comparisons"]["solve_total"]["base_p95_ms"] == 12.0
    assert result["comparisons"]["solve_total"]["head_p95_ms"] == 12.0
    assert result["positions"] == {
        "head": [1, 2, 1, 2],
        "base": [2, 1, 2, 1],
    }


def test_missing_round_pair_fails_closed(tmp_path: Path) -> None:
    paths = _write_balanced_rounds(
        tmp_path,
        base_values=[10.0] * 60,
        head_values=[10.0] * 60,
    )
    paths[(4, "base")].unlink()

    with pytest.raises(performance.PerformanceDataError, match="expected 8"):
        _compare(tmp_path)


def test_duplicate_round_measurement_fails_closed(tmp_path: Path) -> None:
    paths = _write_balanced_rounds(
        tmp_path,
        base_values=[10.0] * 60,
        head_values=[10.0] * 60,
    )
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(paths[(1, "head")].read_text(encoding="utf-8"), encoding="utf-8")
    paths[(4, "base")].unlink()

    with pytest.raises(performance.PerformanceDataError, match="duplicate"):
        _compare(tmp_path)


def test_unbalanced_positions_fail_closed(tmp_path: Path) -> None:
    paths = _write_balanced_rounds(
        tmp_path,
        base_values=[10.0] * 60,
        head_values=[10.0] * 60,
    )
    for round_number in (2, 4):
        _mutate_json(
            paths[(round_number, "head")],
            lambda data: data["metadata"].update(position=1),
        )
        _mutate_json(
            paths[(round_number, "base")],
            lambda data: data["metadata"].update(position=2),
        )

    with pytest.raises(performance.PerformanceDataError, match="not balanced"):
        _compare(tmp_path)


@pytest.mark.parametrize(
    ("case", "expected_message"),
    (
        ("metrics", "mismatched metrics"),
        ("metric_order", "mismatched metrics"),
        ("repeats", "mismatched repeats or warmups"),
        ("warmups", "mismatched repeats or warmups"),
        ("raw_count", "raw count mismatch"),
        ("label", "mixed revision label"),
        ("sha", "unexpected head SHA"),
    ),
)
def test_inconsistent_round_metadata_fails_closed(
    tmp_path: Path,
    case: str,
    expected_message: str,
) -> None:
    paths = _write_balanced_rounds(
        tmp_path,
        base_values=[10.0] * 60,
        head_values=[10.0] * 60,
    )

    def mutate(data: dict) -> None:
        if case == "metrics":
            data["metrics"].pop("route")
        elif case == "metric_order":
            data["metrics"] = {
                name: data["metrics"][name] for name in reversed(METRICS)
            }
        elif case == "repeats":
            data["metadata"]["repeats"] = 58
            for metric in data["metrics"].values():
                metric["samples"] = 58
                metric["raw_samples_ms"] = metric["raw_samples_ms"][:58]
        elif case == "warmups":
            data["metadata"]["warmups"] = 8
        elif case == "raw_count":
            data["metrics"]["route"]["samples"] = 59
        elif case == "label":
            data["metadata"]["revision_label"] = "candidate"
        elif case == "sha":
            data["metadata"]["revision_sha"] = "c" * 40

    _mutate_json(paths[(1, "head")], mutate)

    with pytest.raises(performance.PerformanceDataError, match=expected_message):
        _compare(tmp_path)


@pytest.mark.parametrize("invalid_sample", (float("nan"), float("inf"), 0.0, -1.0))
def test_invalid_raw_samples_fail_closed(
    tmp_path: Path,
    invalid_sample: float,
) -> None:
    paths = _write_balanced_rounds(
        tmp_path,
        base_values=[10.0] * 60,
        head_values=[10.0] * 60,
    )

    def mutate(data: dict) -> None:
        data["metrics"]["solve_total"]["raw_samples_ms"][0] = invalid_sample

    _mutate_json(paths[(1, "head")], mutate)

    with pytest.raises(
        performance.PerformanceDataError,
        match="non-finite or non-positive",
    ):
        _compare(tmp_path)


def test_legacy_summary_compare_schema_and_boundaries_are_preserved(
    tmp_path: Path,
) -> None:
    base = {
        "schema_version": 1,
        "metrics": {
            "solve_total": {"p50_ms": 9.0, "p95_ms": 10.0},
        },
    }
    head = copy.deepcopy(base)
    head["metrics"]["solve_total"] = {"p50_ms": 10.0, "p95_ms": 11.6}
    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    head_path.write_text(json.dumps(head), encoding="utf-8")

    result = performance.compare(base_path, head_path, 15.0)

    assert result == {
        "schema_version": 1,
        "max_regression_percent": 15.0,
        "comparisons": {
            "solve_total": {
                "base_p50_ms": 9.0,
                "base_p95_ms": 10.0,
                "head_p50_ms": 10.0,
                "head_p95_ms": 11.6,
                "p95_change_percent": 16.0,
            }
        },
        "regressions": ["solve_total"],
        "passed": False,
    }


@pytest.mark.parametrize(
    ("head_p95", "expected_code"),
    ((11.5, 0), (11.6, 1)),
)
def test_legacy_cli_success_and_failure_exit_semantics_are_preserved(
    tmp_path: Path,
    head_p95: float,
    expected_code: int,
) -> None:
    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": {"solve_total": {"p50_ms": 9.0, "p95_ms": 10.0}},
            }
        ),
        encoding="utf-8",
    )
    head_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": {
                    "solve_total": {"p50_ms": 10.0, "p95_ms": head_p95}
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(performance.__file__).resolve()),
            "--compare-base",
            str(base_path),
            "--compare-head",
            str(head_path),
            "--max-regression-percent",
            "15",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == expected_code
    rendered = json.loads(completed.stdout)
    assert rendered["schema_version"] == 1
    assert rendered["passed"] is (expected_code == 0)
    if expected_code:
        assert "hotfix performance regression exceeded threshold" in completed.stderr
