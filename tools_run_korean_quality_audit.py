"""Run the Phase 10 Korean quality benchmark and print a compact report.

Usage:
    cd backend
    python tools_run_korean_quality_audit.py
"""
from collections import Counter
from engine.qa.korean_benchmark import KOREAN_BENCHMARK_CASES
from engine.services import solve_problem


def main() -> int:
    failures = []
    counts = Counter(expected for _, expected in KOREAN_BENCHMARK_CASES)
    for idx, (problem_text, expected_solver) in enumerate(KOREAN_BENCHMARK_CASES, start=1):
        result = solve_problem(problem_text)
        got_solver = result.diagnosis.selected_solver
        missing = result.diagnosis.canonical.missing_info
        if got_solver != expected_solver or not result.ok or missing or result.answer is None:
            failures.append((idx, problem_text, expected_solver, got_solver, result.ok, missing))

    print("DynaTutor Phase 10 Korean Quality Benchmark")
    print(f"Total cases: {len(KOREAN_BENCHMARK_CASES)}")
    print(f"Passed: {len(KOREAN_BENCHMARK_CASES) - len(failures)}")
    print(f"Failed: {len(failures)}")
    print("\nDomain coverage:")
    for solver, n in sorted(counts.items()):
        print(f"- {solver}: {n}")

    if failures:
        print("\nFailures:")
        for idx, text, expected, got, ok, missing in failures:
            print(f"[{idx}] expected={expected}, got={got}, ok={ok}, missing={missing}")
            print(f"    {text}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
