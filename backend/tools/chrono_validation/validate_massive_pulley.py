from __future__ import annotations

import argparse
import json

from common import add_common_args, exit_code_for, print_json_report, run_analytic_suite
from analytic_cases import massive_pulley_cases
from chrono_simulators import simulate_massive_pulley


def main() -> int:
    parser = add_common_args(argparse.ArgumentParser(description="massive_pulley validation"))
    args = parser.parse_args()
    if args.mode == "analytic":
        results = run_analytic_suite(massive_pulley_cases())
        print_json_report(results, suite="massive_pulley", mode=args.mode)
        return exit_code_for(results, args.strict)

    chrono_results = [
        simulate_massive_pulley(m1=2.0, m2=5.0, inertia=0.12, radius=0.3)
    ]
    payload = _payload("massive_pulley", args.mode, chrono_results)
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
