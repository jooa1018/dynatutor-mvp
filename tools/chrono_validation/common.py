from __future__ import annotations

import argparse
import importlib
import json
import math
import re
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from engine.services import solve_problem


@dataclass
class ValidationResult:
    case_id: str
    topic: str
    status: str
    passed: bool
    dynatutor_value: float | None
    reference_value: float | None
    reference_source: str
    tolerance: float
    abs_error: float | None
    rel_error: float | None
    problem: str
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationCase:
    case_id: str
    topic: str
    problem: str
    expected_solver: str
    reference_fn: Callable[[], float]
    tolerance: float = 1e-2
    reference_source: str = "analytic_reference"
    notes: list[str] | None = None
    display_reference: float | None = None
    display_label: str | None = None


def try_import_chrono():
    """Try common PyChrono import names.

    Project Chrono Python packaging has varied across setups, so this function
    deliberately tries multiple import styles and returns `(module, message)`.
    """
    candidates = ["pychrono", "pychrono.core"]
    errors = []
    for name in candidates:
        try:
            return importlib.import_module(name), f"imported {name}"
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return None, "; ".join(errors)


def chrono_status() -> dict:
    chrono, message = try_import_chrono()
    if chrono is None:
        return {"available": False, "message": message}
    return {
        "available": True,
        "message": message,
        "module": getattr(chrono, "__name__", "unknown"),
        "version": getattr(chrono, "__version__", None),
    }


def _extract_display_value(display: str, label: str) -> float | None:
    """Extract a numeric value following a label like v1' or v2'."""
    pattern = rf"{re.escape(label)}\s*=\s*(-?\d+(?:\.\d+)?)"
    m = re.search(pattern, display)
    if not m:
        return None
    return float(m.group(1))


def solve_dyntutor_numeric(problem: str, expected_solver: str, *, display_label: str | None = None) -> tuple[float | None, list[str]]:
    out = solve_problem(problem)
    notes: list[str] = []
    if not out.ok:
        return None, [f"DynaTutor did not solve: {out.unsupported_reason}; missing={out.diagnosis.canonical.missing_info}"]
    if out.diagnosis.selected_solver != expected_solver:
        notes.append(f"solver mismatch: selected={out.diagnosis.selected_solver}, expected={expected_solver}")
    if not out.answer:
        return None, notes + ["DynaTutor answer is missing"]
    if out.answer.numeric is not None:
        return float(out.answer.numeric), notes
    if display_label:
        value = _extract_display_value(out.answer.display or "", display_label)
        if value is not None:
            notes.append(f"numeric extracted from display label {display_label}")
            return value, notes
    return None, notes + ["DynaTutor answer has no numeric value"]


def compare_case(case: ValidationCase, *, reference_value: float | None = None, reference_source: str | None = None, extra_notes: list[str] | None = None) -> ValidationResult:
    dyn, notes = solve_dyntutor_numeric(case.problem, case.expected_solver, display_label=case.display_label)
    ref = case.display_reference if case.display_reference is not None else (case.reference_fn() if reference_value is None else reference_value)
    source = reference_source or case.reference_source
    notes.extend(case.notes or [])
    notes.extend(extra_notes or [])

    if dyn is None or ref is None:
        return ValidationResult(
            case_id=case.case_id,
            topic=case.topic,
            status="failed_missing_value",
            passed=False,
            dynatutor_value=dyn,
            reference_value=ref,
            reference_source=source,
            tolerance=case.tolerance,
            abs_error=None,
            rel_error=None,
            problem=case.problem,
            notes=notes,
        )
    abs_error = abs(dyn - ref)
    rel_error = abs_error / max(abs(ref), 1e-12)
    passed = abs_error <= case.tolerance or rel_error <= case.tolerance
    return ValidationResult(
        case_id=case.case_id,
        topic=case.topic,
        status="passed" if passed else "failed_tolerance",
        passed=passed,
        dynatutor_value=dyn,
        reference_value=ref,
        reference_source=source,
        tolerance=case.tolerance,
        abs_error=abs_error,
        rel_error=rel_error,
        problem=case.problem,
        notes=notes,
    )


def run_analytic_suite(cases: Iterable[ValidationCase]) -> list[ValidationResult]:
    return [compare_case(case) for case in cases]


def suite_summary(results: list[ValidationResult]) -> dict:
    return {
        "count": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "statuses": {s: sum(1 for r in results if r.status == s) for s in sorted({r.status for r in results})},
    }


def print_json_report(results: list[ValidationResult], *, suite: str, mode: str, extra: dict | None = None) -> None:
    payload = {
        "suite": suite,
        "mode": mode,
        "summary": suite_summary(results),
        "chrono_status": chrono_status(),
        "extra": extra or {},
        "results": [r.to_dict() for r in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--mode", choices=["analytic", "chrono", "auto"], default="auto", help="analytic always runs; chrono requires PyChrono; auto uses chrono if available, otherwise analytic.")
    parser.add_argument("--strict", action="store_true", help="exit nonzero when any validation result fails")
    return parser


def exit_code_for(results: list[ValidationResult], strict: bool) -> int:
    return 1 if strict and any(not r.passed for r in results) else 0
