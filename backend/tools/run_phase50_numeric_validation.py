from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any, Sequence


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from engine.simulation.contracts import (  # noqa: E402
    DEFAULT_NUMERIC_SAFETY_POLICY,
    RESULT_SCHEMA_VERSION,
    SPEC_SCHEMA_VERSION,
)
from engine.simulation.scenarios import (  # noqa: E402
    VALIDATION_SUITE_VERSION,
    NumericValidationCase,
    accuracy_validation_cases,
    evaluate_validation_case,
)
from engine.simulation.sympy_scipy import simulate_numeric  # noqa: E402


REPORT_SCHEMA_VERSION = 1
REPORT_ID = "phase50-sympy-scipy-numeric-validation-v1"
DEFAULT_JSON_REPORT = BACKEND_ROOT / "reports" / "phase50_numeric_validation.json"
DEFAULT_MARKDOWN_REPORT = BACKEND_ROOT / "reports" / "phase50_numeric_validation.md"


def _case_record(case: NumericValidationCase) -> dict[str, Any]:
    result = simulate_numeric(case.spec)
    verdict = evaluate_validation_case(case, result)
    diagnostics = result.solver_diagnostics
    trajectory = result.trajectory
    final_state = (
        {
            name: values[-1]
            for name, values in trajectory.states.items()
            if values
        }
        if trajectory is not None
        else {}
    )
    return {
        "case_id": case.case_id,
        "model_id": case.spec.model_id,
        "model_version": case.spec.model_version,
        "status": result.status,
        "passed": bool(verdict["passed"]),
        "checks": verdict["checks"],
        "spec": case.spec.to_dict(),
        "result_schema_version": result.schema_version,
        "safety_policy_version": result.safety_policy_version,
        "sample_count": len(trajectory.time) if trajectory else 0,
        "final_state": final_state,
        "integration": {
            "method": diagnostics.get("integration_method"),
            "rtol": diagnostics.get("rtol"),
            "atol": diagnostics.get("atol"),
            "max_step": diagnostics.get("max_step"),
            "nfev": diagnostics.get("nfev"),
            "njev": diagnostics.get("njev"),
            "nlu": diagnostics.get("nlu"),
            "mass_matrix_condition_max": diagnostics.get(
                "mass_matrix_condition_max"
            ),
        },
        "runtime_versions": {
            "sympy": diagnostics.get("sympy_version"),
            "scipy": diagnostics.get("scipy_version"),
            "numpy": diagnostics.get("numpy_version"),
        },
        "invariant_drift": dict(result.invariant_drift),
        "constraint_violation": dict(result.constraint_violation),
        "analytic_error": dict(result.analytic_error),
        "events": dict(result.events),
        "warnings": list(result.warnings),
        "errors": list(result.errors),
        "offline_only": diagnostics.get("offline_only") is True,
        "student_answer_overwrite": diagnostics.get(
            "student_answer_overwrite"
        ),
    }


def build_report(
    cases: Sequence[NumericValidationCase] | None = None,
) -> dict[str, Any]:
    selected_cases = tuple(cases or accuracy_validation_cases())
    records = [_case_record(case) for case in selected_cases]
    model_counts = {
        model_id: sum(record["model_id"] == model_id for record in records)
        for model_id in sorted({record["model_id"] for record in records})
    }
    passed_count = sum(bool(record["passed"]) for record in records)
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_id": REPORT_ID,
        "validation_suite_version": VALIDATION_SUITE_VERSION,
        "spec_schema_version": SPEC_SCHEMA_VERSION,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "safety_policy": DEFAULT_NUMERIC_SAFETY_POLICY.to_dict(),
        "status": "passed" if passed_count == len(records) else "failed",
        "passed": passed_count == len(records),
        "summary": {
            "case_count": len(records),
            "passed_count": passed_count,
            "failed_count": len(records) - passed_count,
            "scipy_trajectory_count": sum(
                record["sample_count"] >= 2 for record in records
            ),
            "model_counts": model_counts,
            "energy_policy_passed": sum(
                bool(record["checks"]["energy_policy_passed"])
                for record in records
            ),
            "constraint_policy_passed": sum(
                bool(record["checks"]["constraint_policy_passed"])
                for record in records
            ),
            "analytic_contract_passed": sum(
                bool(record["checks"]["analytic_contract_passed"])
                for record in records
            ),
            "offline_only": all(record["offline_only"] for record in records),
            "student_answer_overwrite": any(
                record["student_answer_overwrite"] is not False
                for record in records
            ),
            "pydy_required": False,
            "normal_solve_path_changed": False,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "cases": records,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Phase 50 SymPy Mechanics + SciPy validation",
        "",
        f"- Report: `{report['report_id']}`",
        f"- Suite: `{report['validation_suite_version']}`",
        f"- Status: **{report['status']}**",
        f"- Passed: `{str(report['passed']).lower()}`",
        (
            "- Cases: "
            f"{summary['passed_count']}/{summary['case_count']} passed"
        ),
        (
            "- SciPy trajectories: "
            f"{summary['scipy_trajectory_count']}/{summary['case_count']}"
        ),
        (
            "- Offline only / answer overwrite / PyDy required: "
            f"{str(summary['offline_only']).lower()} / "
            f"{str(summary['student_answer_overwrite']).lower()} / "
            f"{str(summary['pydy_required']).lower()}"
        ),
        "",
        "| Case | Model | Status | Samples | Analytic | Energy | Constraint |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for record in report["cases"]:
        checks = record["checks"]
        lines.append(
            "| "
            f"{record['case_id']} | {record['model_id']} | "
            f"{record['status']} | {record['sample_count']} | "
            f"{str(checks['analytic_contract_passed']).lower()} | "
            f"{str(checks['energy_policy_passed']).lower()} | "
            f"{str(checks['constraint_policy_passed']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Contract",
            "",
            "This runner is offline validation evidence. It does not alter the ",
            "production `/solve` path or overwrite a student answer. SciPy is the ",
            "required numeric runtime; PyDy remains optional.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_reports(
    report: dict[str, Any],
    *,
    json_path: Path = DEFAULT_JSON_REPORT,
    markdown_path: Path = DEFAULT_MARKDOWN_REPORT,
) -> None:
    json_content = json.dumps(
        report,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    _atomic_write(json_path, json_content)
    _atomic_write(markdown_path, render_markdown(report))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase 50 offline SymPy/SciPy numeric validation."
    )
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=DEFAULT_MARKDOWN_REPORT,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_report()
    write_reports(
        report,
        json_path=args.json_report,
        markdown_path=args.markdown_report,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "passed": report["passed"],
                "summary": report["summary"],
            },
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_JSON_REPORT",
    "DEFAULT_MARKDOWN_REPORT",
    "REPORT_ID",
    "REPORT_SCHEMA_VERSION",
    "build_report",
    "main",
    "render_markdown",
    "write_reports",
]
