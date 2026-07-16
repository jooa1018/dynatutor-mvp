from __future__ import annotations

import argparse
import json

from common import add_common_args, exit_code_for, print_json_report, run_analytic_suite
from analytic_cases import incline_friction_cases
from chrono_simulators import simulate_incline_friction


def main() -> int:
    parser = add_common_args(argparse.ArgumentParser(description="incline_friction validation"))
    args = parser.parse_args()
    if args.mode == "analytic":
        results = run_analytic_suite(incline_friction_cases())
        print_json_report(results, suite="incline_friction", mode=args.mode)
        return exit_code_for(results, args.strict)

    chrono_results = [
        simulate_incline_friction(theta_deg=20.0, mu=0.05),
        simulate_incline_friction(theta_deg=10.0, mu=0.30),
    ]
    payload = _payload("incline_friction", args.mode, chrono_results)
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
