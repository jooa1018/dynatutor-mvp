from __future__ import annotations

import argparse
import sys

from common import add_common_args, exit_code_for, print_json_report, run_analytic_suite
from analytic_cases import all_phase21_cases


def main() -> int:
    parser = add_common_args(argparse.ArgumentParser(description="Run all Phase 21 Chrono offline validation suites"))
    args = parser.parse_args()
    results = run_analytic_suite(all_phase21_cases())
    print_json_report(
        results,
        suite="phase21_all",
        mode=args.mode,
        extra={
            "validation_layers": [
                "DynaTutor closed-form vs analytic reference: automated",
                "DynaTutor closed-form vs PyChrono numerical simulation: optional local/manual when PyChrono is installed",
            ]
        },
    )
    return exit_code_for(results, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
