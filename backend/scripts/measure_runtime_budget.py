from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
import time


def _max_rss_mb() -> float | None:
    try:
        import resource
    except ModuleNotFoundError:
        return None
    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB; macOS reports bytes.
    if sys.platform == "darwin":
        return raw / (1024 * 1024)
    return raw / 1024


def measure_runtime_import() -> dict:
    started = time.perf_counter()
    importlib.import_module("engine.services")
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "schema_version": 1,
        "import": "engine.services",
        "cold_import_ms": round(elapsed_ms, 6),
        "max_rss_mb": (
            round(rss_mb, 3) if (rss_mb := _max_rss_mb()) is not None else None
        ),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure DynaTutor cold import time and process RSS."
    )
    parser.add_argument("--max-import-ms", type=float)
    parser.add_argument("--max-rss-mb", type=float)
    args = parser.parse_args()

    result = measure_runtime_import()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    violations: list[str] = []
    if (
        args.max_import_ms is not None
        and result["cold_import_ms"] > args.max_import_ms
    ):
        violations.append(
            f"cold import {result['cold_import_ms']:.3f}ms > "
            f"budget {args.max_import_ms:.3f}ms"
        )
    if (
        args.max_rss_mb is not None
        and result["max_rss_mb"] is not None
        and result["max_rss_mb"] > args.max_rss_mb
    ):
        violations.append(
            f"RSS {result['max_rss_mb']:.3f}MB > budget {args.max_rss_mb:.3f}MB"
        )
    if violations:
        raise SystemExit("runtime budget exceeded: " + "; ".join(violations))


if __name__ == "__main__":
    main()
