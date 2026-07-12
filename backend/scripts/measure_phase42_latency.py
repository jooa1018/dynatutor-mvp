from __future__ import annotations

import argparse
import importlib.abc
import json
import math
import platform
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


BLOCKED_OPTIONAL_ROOTS = frozenset({"chrono", "pychrono", "pydy", "scipy"})
BACKEND_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = BACKEND_ROOT / "tests" / "golden" / "phase42_dynamics_cases.json"


class _BlockOptionalDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        root = fullname.partition(".")[0]
        if root in BLOCKED_OPTIONAL_ROOTS:
            raise ModuleNotFoundError(
                f"{fullname!r} is intentionally blocked for the Phase 42 optional-dependency-free baseline",
                name=fullname,
            )
        return None


def _percentile_nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def measure(*, repeats: int, warmups: int, block_optional_dependencies: bool) -> dict:
    if repeats < 1 or warmups < 0:
        raise ValueError("repeats must be >= 1 and warmups must be >= 0")
    if block_optional_dependencies:
        sys.meta_path.insert(0, _BlockOptionalDependencies())

    # Import only after the optional-dependency gate is installed.
    from engine.services import solve_problem

    fixture = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    cases = fixture["cases"]

    for _ in range(warmups):
        for case in cases:
            solve_problem(case["problem_text"])

    samples_ms: list[float] = []
    statuses: Counter[str] = Counter()
    for _ in range(repeats):
        for case in cases:
            started = time.perf_counter()
            response = solve_problem(case["problem_text"])
            samples_ms.append((time.perf_counter() - started) * 1000)
            if response.ok:
                statuses["solved"] += 1
            elif response.clarification is not None:
                statuses["needs_clarification"] += 1
            else:
                statuses["unsupported"] += 1

    return {
        "schema_version": 1,
        "fixture": str(GOLDEN_PATH.relative_to(BACKEND_ROOT.parent)).replace("\\", "/"),
        "case_count": len(cases),
        "repeats": repeats,
        "warmups": warmups,
        "sample_count": len(samples_ms),
        "mean_ms": round(statistics.fmean(samples_ms), 6),
        "p95_ms": round(_percentile_nearest_rank(samples_ms, 0.95), 6),
        "min_ms": round(min(samples_ms), 6),
        "max_ms": round(max(samples_ms), 6),
        "status_counts": dict(sorted(statuses.items())),
        "optional_dependencies_blocked": (
            sorted(BLOCKED_OPTIONAL_ROOTS) if block_optional_dependencies else []
        ),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the Phase 42 golden solve latency baseline.")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--block-optional-dependencies", action="store_true")
    parser.add_argument("--max-mean-ms", type=float)
    parser.add_argument("--max-p95-ms", type=float)
    args = parser.parse_args()
    result = measure(
        repeats=args.repeats,
        warmups=args.warmups,
        block_optional_dependencies=args.block_optional_dependencies,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    violations: list[str] = []
    if args.max_mean_ms is not None and result["mean_ms"] > args.max_mean_ms:
        violations.append(
            f"mean {result['mean_ms']:.3f}ms > budget {args.max_mean_ms:.3f}ms"
        )
    if args.max_p95_ms is not None and result["p95_ms"] > args.max_p95_ms:
        violations.append(
            f"p95 {result['p95_ms']:.3f}ms > budget {args.max_p95_ms:.3f}ms"
        )
    if violations:
        raise SystemExit("latency budget exceeded: " + "; ".join(violations))


if __name__ == "__main__":
    main()
