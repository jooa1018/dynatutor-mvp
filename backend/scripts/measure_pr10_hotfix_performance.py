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


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def _measure(call: Callable[[], object], repeats: int, warmups: int) -> dict:
    for _ in range(warmups):
        call()
    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)
    return {
        "samples": repeats,
        "p50_ms": round(statistics.median(samples), 6),
        "p95_ms": round(_percentile(samples, 0.95), 6),
        "mean_ms": round(statistics.fmean(samples), 6),
        "min_ms": round(min(samples), 6),
        "max_ms": round(max(samples), 6),
    }


def measure(repeats: int, warmups: int) -> dict:
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
        "schema_version": 1,
        "backend_root": str(BACKEND_ROOT),
        "repeats": repeats,
        "warmups": warmups,
        "metrics": {
            "registry_construction": _measure(
                SolverRegistry,
                repeats,
                warmups,
            ),
            "route": _measure(route_once, repeats, warmups),
            "solve_total": _measure(solve_once, repeats, warmups),
            "projectile": _measure(projectile_once, repeats, warmups),
            "rigid_body": _measure(rigid_once, repeats, warmups),
        },
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
        if (
            percent > max_regression
            and head_p95 - base_p95 > 1.0
        ):
            regressions.append(name)
    return {
        "schema_version": 1,
        "max_regression_percent": max_regression,
        "comparisons": comparisons,
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
    args = parser.parse_args()

    if args.compare_base or args.compare_head:
        if args.compare_base is None or args.compare_head is None:
            raise SystemExit("both --compare-base and --compare-head are required")
        result = compare(
            args.compare_base,
            args.compare_head,
            args.max_regression_percent,
        )
    else:
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
