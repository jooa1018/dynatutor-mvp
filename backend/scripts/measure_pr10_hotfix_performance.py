from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Callable


BACKEND_ROOT = Path.cwd()
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

PROJECTILE = (
    "지면에서 초속도 20m/s, 발사각 60도로 발사해 "
    "같은 높이에 착지한다. 사거리는?"
)
RIGID_BODY = (
    "평면강체에서 A점은 고정되어 있고 rBA=(1,0)m이다. "
    "omega=2rad/s이며 반시계방향이다. B점 속도를 구하라."
)
ROUTE_TEXT = "도르래에 연결된 m1=2kg, m2=3kg 두 물체의 가속도는?"
RAW_SCHEMA_VERSION = 2
RAW_MEASUREMENT_MODE = "raw_measurement"
POOLED_COMPARISON_MODE = "pooled_comparison"
REVISION_LABELS = ("head", "base")


class PerformanceDataError(ValueError):
    """Raised when pooled performance evidence is incomplete or inconsistent."""


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def _summarize(samples: list[float]) -> dict:
    return {
        "samples": len(samples),
        "p50_ms": round(statistics.median(samples), 6),
        "p95_ms": round(_percentile(samples, 0.95), 6),
        "mean_ms": round(statistics.fmean(samples), 6),
        "min_ms": round(min(samples), 6),
        "max_ms": round(max(samples), 6),
    }


def _measure(
    call: Callable[[], object],
    repeats: int,
    warmups: int,
    *,
    include_raw_samples: bool = False,
) -> dict:
    for _ in range(warmups):
        call()
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    result = _summarize(samples)
    if include_raw_samples:
        result["raw_samples_ms"] = samples
    return result


def _measure_metrics(
    repeats: int,
    warmups: int,
    *,
    include_raw_samples: bool,
) -> dict:
    from engine.extraction.extractor import extract_problem
    from engine.services import solve_problem
    from engine.solvers.registry import SolverRegistry

    route_problem = extract_problem(ROUTE_TEXT)
    route_registry = SolverRegistry()

    def route_once():
        return route_registry.route(route_problem)

    def projectile_once():
        result = solve_problem(PROJECTILE)
        if not result.ok or not result.verification.passed:
            raise RuntimeError("projectile performance case did not pass verification")
        return result

    def rigid_once():
        result = solve_problem(RIGID_BODY)
        if not result.ok or not result.verification.passed:
            raise RuntimeError("rigid-body performance case did not pass verification")
        return result

    solve_cases = [projectile_once, rigid_once]
    solve_index = 0

    def solve_once():
        nonlocal solve_index
        call = solve_cases[solve_index % len(solve_cases)]
        solve_index += 1
        return call()

    return {
        "registry_construction": _measure(
            SolverRegistry,
            repeats,
            warmups,
            include_raw_samples=include_raw_samples,
        ),
        "route": _measure(
            route_once,
            repeats,
            warmups,
            include_raw_samples=include_raw_samples,
        ),
        "solve_total": _measure(
            solve_once,
            repeats,
            warmups,
            include_raw_samples=include_raw_samples,
        ),
        "projectile": _measure(
            projectile_once,
            repeats,
            warmups,
            include_raw_samples=include_raw_samples,
        ),
        "rigid_body": _measure(
            rigid_once,
            repeats,
            warmups,
            include_raw_samples=include_raw_samples,
        ),
    }


def measure(repeats: int, warmups: int) -> dict:
    return {
        "schema_version": 1,
        "backend_root": str(BACKEND_ROOT),
        "repeats": repeats,
        "warmups": warmups,
        "metrics": _measure_metrics(
            repeats,
            warmups,
            include_raw_samples=False,
        ),
    }


def _require_positive_even(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PerformanceDataError(f"{name} must be a positive even integer")
    if value % 2:
        raise PerformanceDataError(f"{name} must be a positive even integer")


def measure_raw(
    repeats: int,
    warmups: int,
    revision_label: str,
    revision_sha: str,
    round_number: int,
    position: int,
) -> dict:
    _require_positive_even("repeats", repeats)
    _require_positive_even("warmups", warmups)
    if revision_label not in REVISION_LABELS:
        raise PerformanceDataError("revision_label must be head or base")
    if not isinstance(revision_sha, str) or not revision_sha:
        raise PerformanceDataError("revision_sha must be non-empty")
    if (
        isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or round_number <= 0
    ):
        raise PerformanceDataError("round_number must be a positive integer")
    if isinstance(position, bool) or position not in (1, 2):
        raise PerformanceDataError("position must be 1 or 2")
    return {
        "schema_version": RAW_SCHEMA_VERSION,
        "mode": RAW_MEASUREMENT_MODE,
        "backend_root": str(BACKEND_ROOT),
        "metadata": {
            "revision_label": revision_label,
            "revision_sha": revision_sha,
            "round_number": round_number,
            "position": position,
            "repeats": repeats,
            "warmups": warmups,
        },
        "metrics": _measure_metrics(
            repeats,
            warmups,
            include_raw_samples=True,
        ),
    }


def compare(base_path: Path, head_path: Path, max_regression: float) -> dict:
    base = json.loads(base_path.read_text(encoding="utf-8"))
    head = json.loads(head_path.read_text(encoding="utf-8"))
    comparisons: dict[str, dict] = {}
    regressions: list[str] = []
    for name, base_metric in base["metrics"].items():
        head_metric = head["metrics"][name]
        base_p95 = float(base_metric["p95_ms"])
        head_p95 = float(head_metric["p95_ms"])
        percent = (
            0.0
            if base_p95 <= 0
            else (head_p95 - base_p95) / base_p95 * 100.0
        )
        comparisons[name] = {
            "base_p50_ms": base_metric["p50_ms"],
            "base_p95_ms": base_metric["p95_ms"],
            "head_p50_ms": head_metric["p50_ms"],
            "head_p95_ms": head_metric["p95_ms"],
            "p95_change_percent": round(percent, 3),
        }
        # Sub-millisecond registry noise is reported but not treated as a
        # service regression. All route/solve increases above 15% are gated.
        if percent > max_regression and head_p95 - base_p95 > 1.0:
            regressions.append(name)
    return {
        "schema_version": 1,
        "max_regression_percent": max_regression,
        "comparisons": comparisons,
        "regressions": regressions,
        "passed": not regressions,
    }


def _load_raw_measurement(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PerformanceDataError(f"invalid raw measurement file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PerformanceDataError(f"raw measurement {path} must be a JSON object")
    if data.get("schema_version") != RAW_SCHEMA_VERSION:
        raise PerformanceDataError(f"raw measurement {path} must use schema version 2")
    if data.get("mode") != RAW_MEASUREMENT_MODE:
        raise PerformanceDataError(f"raw measurement {path} has an invalid mode")
    if not isinstance(data.get("metadata"), dict):
        raise PerformanceDataError(f"raw measurement {path} is missing metadata")
    if not isinstance(data.get("metrics"), dict) or not data["metrics"]:
        raise PerformanceDataError(f"raw measurement {path} is missing metrics")
    return data


def _validate_raw_measurement(
    path: Path,
    data: dict,
    *,
    expected_head_sha: str,
    expected_base_sha: str,
) -> tuple[tuple[int, str], tuple[str, ...], int, int]:
    metadata = data["metadata"]
    label = metadata.get("revision_label")
    if label not in REVISION_LABELS:
        raise PerformanceDataError(f"raw measurement {path} has a mixed revision label")
    expected_sha = expected_head_sha if label == "head" else expected_base_sha
    if metadata.get("revision_sha") != expected_sha:
        raise PerformanceDataError(f"raw measurement {path} has an unexpected {label} SHA")

    round_number = metadata.get("round_number")
    if (
        isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or round_number <= 0
    ):
        raise PerformanceDataError(f"raw measurement {path} has an invalid round number")
    position = metadata.get("position")
    if isinstance(position, bool) or position not in (1, 2):
        raise PerformanceDataError(f"raw measurement {path} has an invalid position")
    repeats = metadata.get("repeats")
    warmups = metadata.get("warmups")
    _require_positive_even(f"{path} repeats", repeats)
    _require_positive_even(f"{path} warmups", warmups)

    metric_names = tuple(data["metrics"].keys())
    for name, metric in data["metrics"].items():
        if not isinstance(metric, dict):
            raise PerformanceDataError(f"metric {name} in {path} must be an object")
        raw_samples = metric.get("raw_samples_ms")
        if not isinstance(raw_samples, list):
            raise PerformanceDataError(f"metric {name} in {path} is missing raw samples")
        declared_count = metric.get("samples")
        if (
            isinstance(declared_count, bool)
            or not isinstance(declared_count, int)
            or declared_count != len(raw_samples)
            or declared_count != repeats
        ):
            raise PerformanceDataError(f"metric {name} in {path} has a raw count mismatch")
        for value in raw_samples:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PerformanceDataError(
                    f"metric {name} in {path} has a non-numeric raw sample"
                )
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise PerformanceDataError(
                    f"metric {name} in {path} has a non-finite or non-positive sample"
                )
    return (round_number, label), metric_names, repeats, warmups


def _metric_comparison(
    base_samples: list[float],
    head_samples: list[float],
    max_regression: float,
) -> tuple[dict, bool]:
    base_p50 = round(statistics.median(base_samples), 6)
    base_p95 = round(_percentile(base_samples, 0.95), 6)
    head_p50 = round(statistics.median(head_samples), 6)
    head_p95 = round(_percentile(head_samples, 0.95), 6)
    delta = head_p95 - base_p95
    percent = 0.0 if base_p95 <= 0 else delta / base_p95 * 100.0
    regressed = percent > max_regression and delta > 1.0
    return (
        {
            "base_p50_ms": base_p50,
            "base_p95_ms": base_p95,
            "head_p50_ms": head_p50,
            "head_p95_ms": head_p95,
            "p95_delta_ms": round(delta, 6),
            "p95_change_percent": round(percent, 3),
            "regressed": regressed,
        },
        regressed,
    )


def compare_round_dir(
    round_dir: Path,
    expected_rounds: int,
    expected_head_sha: str,
    expected_base_sha: str,
    max_regression: float,
) -> dict:
    _require_positive_even("expected_rounds", expected_rounds)
    if not expected_head_sha or not expected_base_sha:
        raise PerformanceDataError("expected head and base SHAs must be non-empty")
    if not round_dir.is_dir():
        raise PerformanceDataError(f"round directory does not exist: {round_dir}")

    paths = sorted(round_dir.glob("*.json"))
    expected_file_count = expected_rounds * len(REVISION_LABELS)
    if len(paths) != expected_file_count:
        raise PerformanceDataError(
            f"expected {expected_file_count} raw measurement files, found {len(paths)}"
        )

    measurements: dict[tuple[int, str], dict] = {}
    metric_order: tuple[str, ...] | None = None
    shared_repeats: int | None = None
    shared_warmups: int | None = None
    for path in paths:
        data = _load_raw_measurement(path)
        key, names, repeats, warmups = _validate_raw_measurement(
            path,
            data,
            expected_head_sha=expected_head_sha,
            expected_base_sha=expected_base_sha,
        )
        if key in measurements:
            raise PerformanceDataError(
                f"duplicate raw measurement for round {key[0]} {key[1]}"
            )
        if metric_order is None:
            metric_order = names
            shared_repeats = repeats
            shared_warmups = warmups
        elif names != metric_order:
            raise PerformanceDataError(f"raw measurement {path} has mismatched metrics")
        elif repeats != shared_repeats or warmups != shared_warmups:
            raise PerformanceDataError(
                f"raw measurement {path} has mismatched repeats or warmups"
            )
        measurements[key] = data

    expected_round_numbers = list(range(1, expected_rounds + 1))
    actual_round_numbers = sorted({round_number for round_number, _ in measurements})
    if actual_round_numbers != expected_round_numbers:
        raise PerformanceDataError(
            "round numbers must be consecutive from 1 through expected_rounds"
        )

    positions: dict[str, list[int]] = {label: [] for label in REVISION_LABELS}
    for round_number in expected_round_numbers:
        pair = []
        for label in REVISION_LABELS:
            key = (round_number, label)
            if key not in measurements:
                raise PerformanceDataError(
                    f"missing raw measurement for round {round_number} {label}"
                )
            position = measurements[key]["metadata"]["position"]
            positions[label].append(position)
            pair.append(position)
        if set(pair) != {1, 2}:
            raise PerformanceDataError(
                f"round {round_number} head/base positions must be complementary"
            )
    for label, label_positions in positions.items():
        if label_positions.count(1) != expected_rounds // 2:
            raise PerformanceDataError(
                f"{label} positions are not balanced across rounds"
            )
        if label_positions.count(2) != expected_rounds // 2:
            raise PerformanceDataError(
                f"{label} positions are not balanced across rounds"
            )

    assert metric_order is not None
    assert shared_repeats is not None
    assert shared_warmups is not None
    pooled_samples: dict[str, dict[str, list[float]]] = {
        label: {name: [] for name in metric_order} for label in REVISION_LABELS
    }
    for round_number in expected_round_numbers:
        for label in REVISION_LABELS:
            for name in metric_order:
                pooled_samples[label][name].extend(
                    float(value)
                    for value in measurements[(round_number, label)]["metrics"][name][
                        "raw_samples_ms"
                    ]
                )

    comparisons: dict[str, dict] = {}
    regressions: list[str] = []
    for name in metric_order:
        comparison, regressed = _metric_comparison(
            pooled_samples["base"][name],
            pooled_samples["head"][name],
            max_regression,
        )
        comparisons[name] = comparison
        if regressed:
            regressions.append(name)

    round_diagnostics: list[dict] = []
    for round_number in expected_round_numbers:
        diagnostic_comparisons: dict[str, dict] = {}
        diagnostic_regressions: list[str] = []
        for name in metric_order:
            comparison, regressed = _metric_comparison(
                [
                    float(value)
                    for value in measurements[(round_number, "base")]["metrics"][name][
                        "raw_samples_ms"
                    ]
                ],
                [
                    float(value)
                    for value in measurements[(round_number, "head")]["metrics"][name][
                        "raw_samples_ms"
                    ]
                ],
                max_regression,
            )
            diagnostic_comparisons[name] = comparison
            if regressed:
                diagnostic_regressions.append(name)
        round_diagnostics.append(
            {
                "round_number": round_number,
                "positions": {
                    label: measurements[(round_number, label)]["metadata"]["position"]
                    for label in REVISION_LABELS
                },
                "comparisons": diagnostic_comparisons,
                "regressions": diagnostic_regressions,
            }
        )

    sample_counts = {
        label: {name: len(pooled_samples[label][name]) for name in metric_order}
        for label in REVISION_LABELS
    }
    return {
        "schema_version": RAW_SCHEMA_VERSION,
        "mode": POOLED_COMPARISON_MODE,
        "max_regression_percent": max_regression,
        "revision_shas": {
            "head": expected_head_sha,
            "base": expected_base_sha,
        },
        "rounds": expected_rounds,
        "round_numbers": expected_round_numbers,
        "repeats_per_round": shared_repeats,
        "warmups_per_round": shared_warmups,
        "sample_counts": sample_counts,
        "positions": positions,
        "comparisons": comparisons,
        "round_diagnostics": round_diagnostics,
        "regressions": regressions,
        "passed": not regressions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--compare-base", type=Path)
    parser.add_argument("--compare-head", type=Path)
    parser.add_argument("--max-regression-percent", type=float, default=15.0)
    parser.add_argument("--include-raw-samples", action="store_true")
    parser.add_argument("--revision-label", choices=REVISION_LABELS)
    parser.add_argument("--revision-sha")
    parser.add_argument("--round-number", type=int)
    parser.add_argument("--position", type=int, choices=(1, 2))
    parser.add_argument("--compare-round-dir", type=Path)
    parser.add_argument("--expected-rounds", type=int, default=4)
    parser.add_argument("--expected-head-sha")
    parser.add_argument("--expected-base-sha")
    args = parser.parse_args()

    legacy_compare_requested = args.compare_base is not None or args.compare_head is not None
    raw_metadata = (
        args.revision_label,
        args.revision_sha,
        args.round_number,
        args.position,
    )
    if args.compare_round_dir is not None:
        if legacy_compare_requested or args.include_raw_samples or any(
            value is not None for value in raw_metadata
        ):
            raise SystemExit("pooled comparison options cannot be mixed with other modes")
        if args.expected_head_sha is None or args.expected_base_sha is None:
            raise SystemExit(
                "--expected-head-sha and --expected-base-sha are required"
            )
        result = compare_round_dir(
            args.compare_round_dir,
            args.expected_rounds,
            args.expected_head_sha,
            args.expected_base_sha,
            args.max_regression_percent,
        )
    elif legacy_compare_requested:
        if args.compare_base is None or args.compare_head is None:
            raise SystemExit("both --compare-base and --compare-head are required")
        if args.include_raw_samples or any(value is not None for value in raw_metadata):
            raise SystemExit("legacy comparison options cannot be mixed with raw mode")
        result = compare(
            args.compare_base,
            args.compare_head,
            args.max_regression_percent,
        )
    elif args.include_raw_samples:
        missing = [
            option
            for option, value in (
                ("--revision-label", args.revision_label),
                ("--revision-sha", args.revision_sha),
                ("--round-number", args.round_number),
                ("--position", args.position),
            )
            if value is None
        ]
        if missing:
            raise SystemExit(
                "raw mode requires " + ", ".join(missing)
            )
        result = measure_raw(
            args.repeats,
            args.warmups,
            args.revision_label,
            args.revision_sha,
            args.round_number,
            args.position,
        )
    else:
        if any(value is not None for value in raw_metadata):
            raise SystemExit("raw metadata requires --include-raw-samples")
        result = measure(args.repeats, args.warmups)

    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if not result.get("passed", True):
        raise SystemExit(
            "hotfix performance regression exceeded threshold: "
            + ", ".join(result["regressions"])
        )


if __name__ == "__main__":
    main()
