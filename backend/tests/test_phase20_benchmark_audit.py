import json
import math
from pathlib import Path

from engine.services import solve_problem


BENCHMARK_ROOT = Path(__file__).resolve().parent / "benchmarks"
DERIVED_PATHS = [
    BENCHMARK_ROOT / "phase20_derived" / "openstax_style_derived_050.json",
    BENCHMARK_ROOT / "phase20_derived" / "fossee_style_derived_048.json",
    BENCHMARK_ROOT / "phase20_derived" / "mit_ocw_style_derived_031.json",
]
NEGATIVE_PATH = BENCHMARK_ROOT / "phase20_negative" / "negative_unsupported_060.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase20_benchmark_inventory_counts():
    synthetic = _load(BENCHMARK_ROOT / "generated_300.json")
    derived = [case for path in DERIVED_PATHS for case in _load(path)]
    negative = _load(NEGATIVE_PATH)

    assert len(synthetic) >= 300
    assert len(derived) >= 100
    assert len(negative) >= 50
    assert len(synthetic) + len(derived) + len(negative) >= 450

    assert all(case.get("must_not_use_llm_for_answer") is True for case in derived + negative)
    assert all("license_note" in case and "no original" in case["license_note"] for case in derived)


def test_phase20_derived_benchmark_cases_pass():
    failures = []
    for path in DERIVED_PATHS:
        for case in _load(path):
            out = solve_problem(case["problem_ko"])
            if not out.ok:
                failures.append((case["id"], "not_ok", out.unsupported_reason, out.diagnosis.canonical.missing_info))
                continue
            if out.diagnosis.selected_solver != case["expected_solver"]:
                failures.append((case["id"], "solver", out.diagnosis.selected_solver, case["expected_solver"]))
                continue
            if "expected_numeric" in case:
                if not out.answer or out.answer.numeric is None:
                    failures.append((case["id"], "missing_numeric", out.answer.display if out.answer else None))
                    continue
                tol = case.get("tolerance", 1e-3)
                if not math.isclose(float(out.answer.numeric), float(case["expected_numeric"]), rel_tol=tol, abs_tol=tol):
                    failures.append((case["id"], "numeric", out.answer.numeric, case["expected_numeric"], out.answer.display))
    assert not failures[:12]


def test_phase20_negative_benchmark_cases_refuse_to_hallucinate():
    failures = []
    for case in _load(NEGATIVE_PATH):
        out = solve_problem(case["problem_ko"])
        if out.ok:
            failures.append((case["id"], "unexpected_ok", out.diagnosis.selected_solver, out.answer.display if out.answer else None))
    assert not failures[:12]


def test_phase20_benchmark_source_families_present():
    derived = [case for path in DERIVED_PATHS for case in _load(path)]
    families = {case["source_family"] for case in derived}
    assert any("OpenStax" in f for f in families)
    assert any("FOSSEE" in f for f in families)
    assert any("MIT OCW" in f for f in families)
