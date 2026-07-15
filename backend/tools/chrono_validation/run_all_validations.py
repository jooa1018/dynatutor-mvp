from __future__ import annotations

import argparse

from common import add_common_args, exit_code_for, print_json_report, run_analytic_suite
from analytic_cases import all_phase21_cases

try:
    from .phase51_runner import json_report_text, run_phase51_suite
except ImportError:  # direct script execution
    from phase51_runner import json_report_text, run_phase51_suite


def main() -> int:
    parser = add_common_args(
        argparse.ArgumentParser(
            description="Run legacy analytic or real Phase 51 PyChrono validation"
        )
    )
    args = parser.parse_args()
    if args.mode == "analytic":
        results = run_analytic_suite(all_phase21_cases())
        print_json_report(
            results,
            suite="phase21_all",
            mode=args.mode,
            extra={
                "validation_layers": [
                    "DynaTutor closed-form vs analytic reference: automated",
                    "Real PyChrono validation is available through --mode chrono.",
                ]
            },
        )
        return exit_code_for(results, args.strict)

    payload = run_phase51_suite()
    print(json_report_text(payload), end="")
    return 1 if args.strict and not payload["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
