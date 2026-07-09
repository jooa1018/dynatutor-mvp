from __future__ import annotations

import argparse
import sys

from common import add_common_args, compare_case, exit_code_for, print_json_report, run_analytic_suite
from analytic_cases import collision_restitution_cases



def main() -> int:
    parser = add_common_args(argparse.ArgumentParser(description="collision_restitution validation"))
    args = parser.parse_args()
    cases = collision_restitution_cases()

    # Phase 21 always produces analytic validation. Chrono mode is optional and
    # recorded in the report when a local PyChrono environment is available.
    results = run_analytic_suite(cases)
    print_json_report(results, suite="collision_restitution", mode=args.mode, extra={"chrono_note": "Use simulate_collision_restitution(...) manually in a PyChrono environment for numerical comparison."})
    return exit_code_for(results, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
