from __future__ import annotations

import argparse
import json
import math
import platform
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
METRIC_ORDER = (
    "registry_construction",
    "route",
    "solve_total",
    "projectile",
    "rigid_body",
)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def _measure(
    call: Callable[[], object], repeats: int, warmups: int
) -> dict[str, object]:
    for _ in range(warmups):
        call()

    samples: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        call()
        samples.append((time.perf_counter() - started) * 1000)

    return {
        "samples": repeats,
        "raw_samples_ms": samples,
        "p50_ms": round(statistics.median(samples), 6),
        "p95_ms": round(_percentile(samples, 0.95), 6),
        "mean_ms": round(statistics.fmean(samples), 6),
        "min_ms": round(min(samples), 6),
        "max_ms": round(max(samples), 6),
    }


def measure(
    repeats: int,
    warmups: int,
    *,
    label: str,
    round_number: int,
    order: str,
) -> dict[str, object]:
    from engine.extraction.extractor import extract_problem
    from engine.services import solve_problem
    from engine.solvers.registry import SolverRegistry

    route_problem = extract_problem(ROUTE_TEXT)
    route_registry = SolverRegistry()

    def route_once() -> object:
        return route_registry.route(route_problem)

    def projectile_once() -> object:
        result = solve_problem(PROJECTILE)
        if not result.ok or not result.verification.passed:
            raise RuntimeError(
                "projectile performance case did not pass verification"
            )
        return result

    def rigid_once() -> object:
        result = solve_problem(RIGID_BODY)
        if not result.ok or not result.verification.passed:
            raise RuntimeError(
                "rigid-body performance case did not pass verification"
            )
        return result

    solve_cases = [projectile_once, rigid_once]
    solve_index = 0

    def solve_once() -> object:
        nonlocal solve_index
        call = solve_cases[solve_index % len(solve_cases)]
        solve_index += 1
        return call()

    first_label, second_label = order.split("-then-")
    position = 1 if label == first_label else 2
    if label not in {first_label, second_label}:
        raise ValueError(f"label {label!r} is not represented by order {order!r}")

    return {
        "schema_version": 1,
        "backend_root": str(BACKEND_ROOT),
        "environment": {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
        },
        "label": label,
        "metric_order": list(METRIC_ORDER),
        "order": order,
        "position": position,
        "repeats": repeats,
        "round": round_number,
        "warmups": warmups,
        "metrics": {
            "registry_construction": _measure(
                SolverRegistry, repeats, warmups
            ),
            "route": _measure(route_once, repeats, warmups),
            "solve_total": _measure(solve_once, repeats, warmups),
            "projectile": _measure(projectile_once, repeats, warmups),
            "rigid_body": _measure(rigid_once, repeats, warmups),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=60)
    parser.add_argument("--warmups", type=int, default=10)
    parser.add_argument("--label", required=True, choices=("head", "base"))
    parser.add_argument("--round", required=True, type=int, dest="round_number")
    parser.add_argument(
        "--order",
        required=True,
        choices=("head-then-base", "base-then-head"),
    )
    args = parser.parse_args()

    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    if args.warmups < 0:
        parser.error("--warmups must be non-negative")
    if args.round_number <= 0:
        parser.error("--round must be positive")

    result = measure(
        args.repeats,
        args.warmups,
        label=args.label,
        round_number=args.round_number,
        order=args.order,
    )
    rendered = json.dumps(
        result, ensure_ascii=False, indent=2, sort_keys=True
    )
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
