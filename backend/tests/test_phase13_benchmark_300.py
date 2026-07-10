import json
from pathlib import Path
from engine.services import solve_problem


BENCHMARK_PATH = Path(__file__).resolve().parent / "benchmarks" / "generated_300.json"


def test_300_generated_benchmark_cases_pass():
    cases = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    assert len(cases) >= 300
    failures = []
    for i, case in enumerate(cases):
        out = solve_problem(case["problem"])
        if not out.ok or out.diagnosis.selected_solver != case["solver"]:
            failures.append((i, case["problem"], out.diagnosis.selected_solver, out.unsupported_reason, out.diagnosis.canonical.missing_info))
    assert not failures[:10]
