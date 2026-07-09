from __future__ import annotations

import json
import math
from pathlib import Path

from engine.services import solve_problem


BENCHMARK_ROOT = Path(__file__).resolve().parents[1] / "tests" / "benchmarks"
DERIVED_PATHS = [
    BENCHMARK_ROOT / "phase20_derived" / "openstax_style_derived_050.json",
    BENCHMARK_ROOT / "phase20_derived" / "fossee_style_derived_048.json",
    BENCHMARK_ROOT / "phase20_derived" / "mit_ocw_style_derived_031.json",
]
NEGATIVE_PATH = BENCHMARK_ROOT / "phase20_negative" / "negative_unsupported_060.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit() -> dict:
    synthetic = load(BENCHMARK_ROOT / "generated_300.json")
    derived = [case for path in DERIVED_PATHS for case in load(path)]
    negative = load(NEGATIVE_PATH)
    failures = []

    for case in derived:
        out = solve_problem(case["problem_ko"])
        if not out.ok:
            failures.append({"id": case["id"], "kind": "derived_not_ok", "reason": out.unsupported_reason, "missing": out.diagnosis.canonical.missing_info})
            continue
        if out.diagnosis.selected_solver != case["expected_solver"]:
            failures.append({"id": case["id"], "kind": "solver_mismatch", "actual": out.diagnosis.selected_solver, "expected": case["expected_solver"]})
            continue
        if "expected_numeric" in case and out.answer and out.answer.numeric is not None:
            tol = case.get("tolerance", 1e-3)
            if not math.isclose(float(out.answer.numeric), float(case["expected_numeric"]), rel_tol=tol, abs_tol=tol):
                failures.append({"id": case["id"], "kind": "numeric_mismatch", "actual": out.answer.numeric, "expected": case["expected_numeric"]})

    for case in negative:
        out = solve_problem(case["problem_ko"])
        if out.ok:
            failures.append({"id": case["id"], "kind": "negative_unexpected_ok", "solver": out.diagnosis.selected_solver, "answer": out.answer.display if out.answer else None})

    by_family = {}
    for case in derived + negative:
        by_family[case["source_family"]] = by_family.get(case["source_family"], 0) + 1

    return {
        "synthetic_count": len(synthetic),
        "derived_count": len(derived),
        "negative_count": len(negative),
        "total_count": len(synthetic) + len(derived) + len(negative),
        "family_counts": by_family,
        "passed": not failures,
        "failure_count": len(failures),
        "failures": failures[:25],
    }


def main() -> None:
    print(json.dumps(audit(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
