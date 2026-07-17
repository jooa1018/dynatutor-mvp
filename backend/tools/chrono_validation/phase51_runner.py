from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import platform
import re
import sys
from typing import Any, Callable

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from engine.services import solve_problem

try:
    from .chrono_simulators import (
        simulate_collision_restitution,
        simulate_incline_friction,
        simulate_massive_pulley,
        simulate_rolling_down_ramp,
    )
    from .contracts import (
        CHRONO_SUITE_VERSION,
        ChronoResult,
        DEFAULT_CHRONO_POLICY,
        comparison_errors,
        comparison_passed,
    )
except ImportError:  # direct script execution
    from chrono_simulators import (
        simulate_collision_restitution,
        simulate_incline_friction,
        simulate_massive_pulley,
        simulate_rolling_down_ramp,
    )
    from contracts import (
        CHRONO_SUITE_VERSION,
        ChronoResult,
        DEFAULT_CHRONO_POLICY,
        comparison_errors,
        comparison_passed,
    )


PHASE51_REPORT_SCHEMA_VERSION = 1
PHASE51_REPORT_VERSION = "phase51-pychrono-report-v1"
DEFAULT_JSON_PATH = _BACKEND_ROOT / "reports" / "phase51_pychrono_validation.json"
DEFAULT_MARKDOWN_PATH = _BACKEND_ROOT / "reports" / "phase51_pychrono_validation.md"


@dataclass(frozen=True)
class Phase51Case:
    case_id: str
    topic: str
    analytic_value: float
    product_problem: str | None
    expected_solver: str | None
    product_display_label: str | None
    product_abs_tolerance: float
    product_rel_tolerance: float
    chrono_product_abs_tolerance: float
    chrono_product_rel_tolerance: float
    simulator: Callable[[], ChronoResult]

    @property
    def product_required(self) -> bool:
        return self.product_problem is not None


def phase51_cases() -> tuple[Phase51Case, ...]:
    g = 9.81
    height = 0.5
    sphere_expected = math.sqrt(2.0 * g * height / (1.0 + 2.0 / 5.0))
    disk_expected = math.sqrt(2.0 * g * height / (1.0 + 1.0 / 2.0))
    incline_expected = g * (
        math.sin(math.radians(20.0))
        - 0.05 * math.cos(math.radians(20.0))
    )
    m1, m2, v1, v2, restitution = 2.0, 3.0, 4.0, 0.0, 1.0
    collision_expected = (
        m1 * v1 + m2 * v2 - m2 * restitution * (v1 - v2)
    ) / (m1 + m2)
    pulley_expected = (5.0 - 2.0) * g / (
        2.0 + 5.0 + 0.12 / (0.3 * 0.3)
    )
    policy = DEFAULT_CHRONO_POLICY
    return (
        Phase51Case(
            case_id="rolling_sphere",
            topic="rolling_sphere",
            analytic_value=sphere_expected,
            product_problem="정지 상태에서 속이 찬 구가 미끄러지지 않고 높이 0.5m 굴러 내려온다. 속도는?",
            expected_solver="pure_rolling_energy",
            product_display_label=None,
            product_abs_tolerance=0.002,
            product_rel_tolerance=0.002,
            chrono_product_abs_tolerance=policy.rolling_speed_abs_tolerance,
            chrono_product_rel_tolerance=policy.rolling_speed_rel_tolerance,
            simulator=lambda: simulate_rolling_down_ramp(height_m=height, body="sphere"),
        ),
        Phase51Case(
            case_id="rolling_disk",
            topic="rolling_disk",
            analytic_value=disk_expected,
            product_problem="정지 상태에서 원판이 미끄러지지 않고 높이 0.5m 굴러 내려온다. 속도는?",
            expected_solver="pure_rolling_energy",
            product_display_label=None,
            product_abs_tolerance=0.002,
            product_rel_tolerance=0.002,
            chrono_product_abs_tolerance=policy.rolling_speed_abs_tolerance,
            chrono_product_rel_tolerance=policy.rolling_speed_rel_tolerance,
            simulator=lambda: simulate_rolling_down_ramp(height_m=height, body="disk"),
        ),
        Phase51Case(
            case_id="incline_friction_slip",
            topic="incline_friction",
            analytic_value=incline_expected,
            product_problem="운동마찰계수 0.05인 20도 경사면에서 블록의 가속도를 구하라.",
            expected_solver="incline_with_friction",
            product_display_label=None,
            product_abs_tolerance=0.002,
            product_rel_tolerance=0.002,
            chrono_product_abs_tolerance=policy.incline_acceleration_abs_tolerance,
            chrono_product_rel_tolerance=policy.incline_acceleration_rel_tolerance,
            simulator=lambda: simulate_incline_friction(theta_deg=20.0, mu=0.05),
        ),
        Phase51Case(
            case_id="incline_friction_stick",
            topic="incline_friction_supplemental_stick",
            analytic_value=0.0,
            product_problem=None,
            expected_solver=None,
            product_display_label=None,
            product_abs_tolerance=0.0,
            product_rel_tolerance=0.0,
            chrono_product_abs_tolerance=policy.incline_acceleration_abs_tolerance,
            chrono_product_rel_tolerance=policy.incline_acceleration_rel_tolerance,
            simulator=lambda: simulate_incline_friction(theta_deg=10.0, mu=0.30),
        ),
        Phase51Case(
            case_id="collision_restitution",
            topic="collision_restitution",
            analytic_value=collision_expected,
            product_problem="m1=2kg, m2=3kg, v1=4m/s, v2=0m/s, 완전탄성 충돌이다. 충돌 후 속도는?",
            expected_solver="collision_1d",
            product_display_label="v1'",
            product_abs_tolerance=0.003,
            product_rel_tolerance=0.003,
            chrono_product_abs_tolerance=policy.collision_velocity_abs_tolerance,
            chrono_product_rel_tolerance=policy.collision_velocity_rel_tolerance,
            simulator=lambda: simulate_collision_restitution(
                m1=m1,
                m2=m2,
                v1=v1,
                v2=v2,
                restitution=restitution,
            ),
        ),
        Phase51Case(
            case_id="massive_pulley",
            topic="massive_pulley",
            analytic_value=pulley_expected,
            product_problem="질량 있는 도르래에 m1=2 kg, m2=5 kg가 줄로 연결되어 있다. 도르래 관성모멘트 I=0.12 kgm^2, 도르래 반지름 R=0.3 m 일 때 가속도를 구하라.",
            expected_solver="massive_pulley_atwood",
            product_display_label=None,
            product_abs_tolerance=0.002,
            product_rel_tolerance=0.002,
            chrono_product_abs_tolerance=policy.pulley_acceleration_abs_tolerance,
            chrono_product_rel_tolerance=policy.pulley_acceleration_rel_tolerance,
            simulator=lambda: simulate_massive_pulley(
                m1=2.0,
                m2=5.0,
                inertia=0.12,
                radius=0.3,
            ),
        ),
    )


def run_phase51_suite() -> dict[str, Any]:
    cases = phase51_cases()
    product_runs: dict[str, dict[str, Any]] = {}
    product_responses: dict[str, Any] = {}
    product_snapshots: dict[str, dict[str, Any]] = {}
    normal_solve_imported_pychrono = False

    for case in cases:
        if not case.product_required:
            product_runs[case.case_id] = {
                "required": False,
                "status": "not_applicable",
                "problem": None,
                "expected_solver": None,
                "selected_solver": None,
                "value": None,
                "unit": None,
                "display": None,
                "solver_matched": True,
                "answer_overwrite": False,
                "pychrono_imported_by_normal_solve": False,
            }
            continue
        before_modules = _pychrono_modules()
        response = solve_problem(str(case.product_problem))
        after_modules = _pychrono_modules()
        imported_by_solve = bool(after_modules - before_modules)
        normal_solve_imported_pychrono = (
            normal_solve_imported_pychrono or imported_by_solve
        )
        snapshot = _response_snapshot(response)
        value = _product_value(response, case.product_display_label)
        selected_solver = response.diagnosis.selected_solver
        product_runs[case.case_id] = {
            "required": True,
            "status": "solved" if response.ok and value is not None else "failed",
            "problem": case.product_problem,
            "expected_solver": case.expected_solver,
            "selected_solver": selected_solver,
            "value": value,
            "unit": response.answer.unit if response.answer is not None else None,
            "display": response.answer.display if response.answer is not None else None,
            "solver_matched": selected_solver == case.expected_solver,
            "answer_overwrite": False,
            "pychrono_imported_by_normal_solve": imported_by_solve,
        }
        product_responses[case.case_id] = response
        product_snapshots[case.case_id] = snapshot

    case_reports: list[dict[str, Any]] = []
    chrono_results: list[ChronoResult] = []
    for case in cases:
        result = case.simulator()
        chrono_results.append(result)
        product = product_runs[case.case_id]
        if case.product_required:
            response = product_responses[case.case_id]
            overwritten = _response_snapshot(response) != product_snapshots[case.case_id]
            product["answer_overwrite"] = overwritten
            product_value = product["value"]
            product_analytic = _comparison(
                product_value,
                case.analytic_value,
                absolute_tolerance=case.product_abs_tolerance,
                relative_tolerance=case.product_rel_tolerance,
            )
            product_chrono = _comparison(
                product_value,
                result.value,
                absolute_tolerance=case.chrono_product_abs_tolerance,
                relative_tolerance=case.chrono_product_rel_tolerance,
            )
            product_passed = (
                product["status"] == "solved"
                and product["solver_matched"]
                and not overwritten
                and product_analytic["passed"]
                and product_chrono["passed"]
            )
        else:
            product_analytic = _not_applicable_comparison()
            product_chrono = _not_applicable_comparison()
            product_passed = True

        chrono_analytic = _comparison(
            result.value,
            case.analytic_value,
            absolute_tolerance=case.chrono_product_abs_tolerance,
            relative_tolerance=case.chrono_product_rel_tolerance,
        )
        case_passed = bool(result.passed and product_passed and chrono_analytic["passed"])
        case_reports.append(
            {
                "case_id": case.case_id,
                "topic": case.topic,
                "passed": case_passed,
                "analytic_value": case.analytic_value,
                "product": product,
                "chrono": result.to_dict(),
                "comparisons": {
                    "product_vs_analytic": product_analytic,
                    "product_vs_chrono": product_chrono,
                    "chrono_vs_analytic": chrono_analytic,
                },
            }
        )

    by_id = {result.case_id: result for result in chrono_results}
    sphere = by_id.get("rolling_sphere")
    disk = by_id.get("rolling_disk")
    sphere_disk_distinct = bool(
        sphere is not None
        and disk is not None
        and sphere.value is not None
        and disk.value is not None
        and sphere.value > disk.value
    )
    product_answer_overwrite = any(
        report["product"]["answer_overwrite"]
        for report in case_reports
    )
    status_counts = {
        status: sum(1 for result in chrono_results if result.status == status)
        for status in ("passed", "failed", "skipped", "error")
    }
    cross_checks = {
        "sphere_speed_exceeds_disk_speed": sphere_disk_distinct,
        "product_answer_overwrite": product_answer_overwrite,
        "normal_solve_imported_pychrono": normal_solve_imported_pychrono,
        "all_chrono_cases_executed": status_counts["skipped"] == 0,
        "all_chrono_cases_passed": status_counts["passed"] == len(chrono_results),
        "all_required_product_comparisons_passed": all(
            (
                not report["product"]["required"]
                or (
                    report["product"]["status"] == "solved"
                    and report["product"]["solver_matched"]
                    and not report["product"]["answer_overwrite"]
                    and report["comparisons"]["product_vs_analytic"]["passed"]
                    and report["comparisons"]["product_vs_chrono"]["passed"]
                )
            )
            for report in case_reports
        ),
    }
    passed = (
        all(report["passed"] for report in case_reports)
        and sphere_disk_distinct
        and not product_answer_overwrite
        and not normal_solve_imported_pychrono
        and status_counts["skipped"] == 0
        and status_counts["error"] == 0
    )
    if passed:
        status = "passed"
    elif status_counts["error"]:
        status = "error"
    elif status_counts["failed"]:
        status = "failed"
    elif status_counts["skipped"]:
        status = "skipped"
    else:
        status = "failed"

    versions = sorted(
        {
            result.chrono_version
            for result in chrono_results
            if result.chrono_version not in {"unavailable", "unknown"}
        }
    )
    solvers = sorted(
        {
            result.solver
            for result in chrono_results
            if result.status in {"passed", "failed"}
        }
    )
    contact_methods = sorted(
        {
            result.contact_method
            for result in chrono_results
            if result.status in {"passed", "failed"}
        }
    )
    return {
        "schema_version": PHASE51_REPORT_SCHEMA_VERSION,
        "report_version": PHASE51_REPORT_VERSION,
        "suite_version": CHRONO_SUITE_VERSION,
        "policy": DEFAULT_CHRONO_POLICY.to_dict(),
        "status": status,
        "passed": passed,
        "offline_only": True,
        "normal_runtime_dependency": False,
        "product_answer_overwrite": product_answer_overwrite,
        "environment": {
            "python_version": platform.python_version(),
            "platform_system": platform.system(),
            "platform_machine": platform.machine(),
            "chrono_versions": versions,
            "actual_solvers": solvers,
            "actual_contact_methods": contact_methods,
        },
        "summary": {
            "case_count": len(case_reports),
            "product_comparison_count": sum(
                1 for report in case_reports if report["product"]["required"]
            ),
            "passed_cases": sum(1 for report in case_reports if report["passed"]),
            "failed_cases": sum(1 for report in case_reports if not report["passed"]),
            "chrono_statuses": status_counts,
        },
        "cross_checks": cross_checks,
        "cases": case_reports,
        "report_artifacts": {
            "json": "backend/reports/phase51_pychrono_validation.json",
            "markdown": "backend/reports/phase51_pychrono_validation.md",
        },
    }


def _comparison(
    left: float | None,
    right: float | None,
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> dict[str, Any]:
    if left is None or right is None:
        return {
            "status": "missing_value",
            "passed": False,
            "left": left,
            "right": right,
            "absolute_error": None,
            "relative_error": None,
            "absolute_tolerance": absolute_tolerance,
            "relative_tolerance": relative_tolerance,
            "policy": "absolute_or_relative_for_observable_only",
        }
    absolute_error, relative_error = comparison_errors(left, right)
    return {
        "status": "passed" if comparison_passed(
            left,
            right,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ) else "failed",
        "passed": comparison_passed(
            left,
            right,
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
        ),
        "left": left,
        "right": right,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "policy": "absolute_or_relative_for_observable_only",
    }


def _not_applicable_comparison() -> dict[str, Any]:
    return {
        "status": "not_applicable",
        "passed": True,
        "left": None,
        "right": None,
        "absolute_error": None,
        "relative_error": None,
        "absolute_tolerance": None,
        "relative_tolerance": None,
        "policy": "supplemental_chrono_invariant_case",
    }


def _response_snapshot(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    return response.dict()


def _product_value(response: Any, display_label: str | None) -> float | None:
    if not response.ok or response.answer is None:
        return None
    if response.answer.numeric is not None:
        return float(response.answer.numeric)
    if display_label is None:
        return None
    pattern = rf"{re.escape(display_label)}\s*=\s*(-?\d+(?:\.\d+)?)"
    match = re.search(pattern, response.answer.display or "")
    return float(match.group(1)) if match else None


def _pychrono_modules() -> frozenset[str]:
    return frozenset(
        name
        for name in sys.modules
        if name == "pychrono" or name.startswith("pychrono.")
    )


def json_report_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def markdown_report_text(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Phase 51 PyChrono independent validation",
        "",
        f"- Report version: `{payload['report_version']}`",
        f"- Suite version: `{payload['suite_version']}`",
        f"- Status: **{payload['status']}**",
        f"- Passed: `{str(payload['passed']).lower()}`",
        f"- Cases: {summary['passed_cases']}/{summary['case_count']} passed",
        f"- Chrono statuses: `{json.dumps(summary['chrono_statuses'], sort_keys=True)}`",
        f"- Product answer overwrite: `{str(payload['product_answer_overwrite']).lower()}`",
        f"- Offline only: `{str(payload['offline_only']).lower()}`",
        "",
        "## Environment",
        "",
        f"- Python: `{payload['environment']['python_version']}`",
        f"- Platform: `{payload['environment']['platform_system']} / {payload['environment']['platform_machine']}`",
        f"- Chrono versions: `{json.dumps(payload['environment']['chrono_versions'])}`",
        f"- Actual solvers: `{json.dumps(payload['environment']['actual_solvers'])}`",
        f"- Actual contact methods: `{json.dumps(payload['environment']['actual_contact_methods'])}`",
        "",
        "## Cases",
        "",
        "| Case | Chrono status | Chrono value | Analytic | Product | Passed |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in payload["cases"]:
        chrono = case["chrono"]
        product = case["product"]
        lines.append(
            "| "
            + " | ".join(
                (
                    case["case_id"],
                    chrono["status"],
                    _format_value(chrono["value"]),
                    _format_value(case["analytic_value"]),
                    _format_value(product["value"]),
                    str(case["passed"]).lower(),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Cross-checks",
            "",
        ]
    )
    for name, value in sorted(payload["cross_checks"].items()):
        lines.append(f"- {name}: `{str(value).lower()}`")
    lines.extend(
        [
            "",
            "The JSON report contains each scene's initial conditions, final state,",
            "constraint errors, invariant errors, modeling assumptions, warnings, and",
            "in-memory artifact summary. No analytic value is used to initialize or",
            "overwrite a Chrono state.",
            "",
        ]
    )
    return "\n".join(lines)


def _format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.12g}"


def write_reports(
    payload: dict[str, Any],
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json_report_text(payload), encoding="utf-8")
    markdown_path.write_text(markdown_report_text(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase 51 real PyChrono independent validation suite"
    )
    parser.add_argument("--mode", choices=("auto", "chrono"), default="auto")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN_PATH)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    payload = run_phase51_suite()
    if not args.no_write:
        write_reports(
            payload,
            json_path=args.json_out,
            markdown_path=args.markdown_out,
        )
    print(json_report_text(payload), end="")
    return 1 if args.strict and not payload["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
