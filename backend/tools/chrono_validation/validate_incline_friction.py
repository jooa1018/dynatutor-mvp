from __future__ import annotations

import argparse
import sys

from common import add_common_args, compare_case, exit_code_for, print_json_report, run_analytic_suite
from analytic_cases import incline_friction_cases



def main() -> int:
    parser = add_common_args(argparse.ArgumentParser(description="incline_friction validation"))
    args = parser.parse_args()
    cases = incline_friction_cases()

    # Phase 21 always produces analytic validation. Chrono mode is optional and
    # recorded in the report when a local PyChrono environment is available.
    results = run_analytic_suite(cases)
    print_json_report(results, suite="incline_friction", mode=args.mode, extra={"chrono_note": "Use simulate_incline_friction(theta_deg=..., mu=...) manually in a PyChrono environment for numerical comparison."})
    return exit_code_for(results, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
