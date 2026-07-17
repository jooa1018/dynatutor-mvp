from __future__ import annotations

import argparse
import json

from common import add_common_args, exit_code_for, print_json_report, run_analytic_suite
from analytic_cases import rolling_sphere_cases
from chrono_simulators import simulate_rolling_down_ramp


def main() -> int:
    parser = add_common_args(argparse.ArgumentParser(description="rolling_sphere validation"))
    args = parser.parse_args()
    if args.mode == "analytic":
        results = run_analytic_suite(rolling_sphere_cases())
        print_json_report(results, suite="rolling_sphere", mode=args.mode)
        return exit_code_for(results, args.strict)

    chrono_results = [
        simulate_rolling_down_ramp(height_m=height, body="sphere")
        for height in (0.5, 1.0, 1.5, 2.0, 3.0)
    ]
    payload = _payload("rolling_sphere", args.mode, chrono_results)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return 1 if args.strict and not payload["passed"] else 0


def _payload(suite, mode, results):
    return {
        "suite": suite,
        "mode": mode,
        "passed": all(result.passed for result in results),
        "summary": {
            "count": len(results),
            "passed": sum(1 for result in results if result.passed),
            "statuses": {
                status: sum(1 for result in results if result.status == status)
                for status in ("passed", "failed", "skipped", "error")
            },
        },
        "results": [result.to_dict() for result in results],
    }


if __name__ == "__main__":
    raise SystemExit(main())
