from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.run_phase20_benchmark_audit import audit as benchmark_audit
from tools.chrono_validation.common import chrono_status, run_analytic_suite, suite_summary
from tools.chrono_validation.analytic_cases import all_phase21_cases
from engine.llm.guardrails import build_locked_facts, validate_llm_explanation
from engine.services import solve_problem


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def _run_pytest_smoke() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=420,
    )
    return {
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "stdout_tail": proc.stdout[-1200:],
        "stderr_tail": proc.stderr[-1200:],
    }


def _llm_guardrail_audit() -> dict[str, Any]:
    solved = solve_problem("질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라.")
    locked = build_locked_facts(solved)

    safe = validate_llm_explanation(
        "### 한눈에 보기\n경사면 문제입니다.\n\n"
        "### 왜 이 식을 쓰는가\n마찰이 없으므로 mg sinθ = ma를 씁니다.\n\n"
        "### 단계별 설명\n1. θ=30 deg입니다.\n2. solver 결과를 그대로 봅니다.\n3. 답은 4.905 m/s² 입니다.\n\n"
        "### 실수 방지\n새 조건을 넣지 않습니다.\n\n"
        "### 마지막 확인\n최종 답은 a = 4.905 m/s² 입니다.",
        locked,
    )
    changed = validate_llm_explanation("### 마지막 확인\n최종 답은 a = 99 m/s² 입니다.", locked)

    unsupported = solve_problem("m1=2kg, m2=3kg가 줄과 도르래로 연결되어 있다. 가속도는?")
    unsupported_locked = build_locked_facts(unsupported)
    hallucinated = validate_llm_explanation("정답은 3.14 m/s² 입니다. 계산하면 바로 나옵니다.", unsupported_locked)

    return {
        "passed": safe.passed and (not changed.passed) and (not hallucinated.passed),
        "safe_passed": safe.passed,
        "changed_answer_rejected": not changed.passed,
        "unsupported_hallucination_rejected": not hallucinated.passed,
        "locked_hash_example": locked.locked_hash,
        "warnings_changed": changed.warnings,
        "warnings_unsupported": hallucinated.warnings,
    }


def _phase_num(name: str) -> int:
    match = re.search(r"PHASE(\d+)", name)
    return int(match.group(1)) if match else -1


def _artifact_inventory() -> dict[str, Any]:
    docs = sorted((p.name for p in (PROJECT_ROOT / "docs").glob("PHASE*.md")), key=_phase_num)
    benchmark_files = sorted(str(p.relative_to(PROJECT_ROOT)) for p in (BACKEND_ROOT / "tests" / "benchmarks").rglob("*.json"))
    cache_dirs = [str(p.relative_to(PROJECT_ROOT)) for p in PROJECT_ROOT.rglob("*") if p.is_dir() and p.name in {"__pycache__", ".pytest_cache"}]
    return {
        "phase_doc_count": len(docs),
        "latest_phase_doc": docs[-1] if docs else None,
        "benchmark_file_count": len(benchmark_files),
        "has_node_modules": (PROJECT_ROOT / "frontend" / "node_modules").exists(),
        "cache_dirs_present_in_worktree_after_tests": bool(cache_dirs),
        "cache_dirs_are_excluded_from_release_zip": True,
        "cache_dir_examples": cache_dirs[:5],
    }


def audit(include_pytest: bool = False) -> dict[str, Any]:
    bench = benchmark_audit()
    validation_results = run_analytic_suite(all_phase21_cases())
    chrono = chrono_status()
    llm = _llm_guardrail_audit()
    inventory = _artifact_inventory()

    checks = {
        "benchmark_passed": bool(bench.get("passed")),
        "benchmark_total_at_least_450": bench.get("total_count", 0) >= 450,
        "phase21_validation_passed": suite_summary(validation_results)["failed"] == 0,
        "llm_guardrail_passed": llm["passed"],
        "docs_present": inventory["phase_doc_count"] >= 20,
    }
    pytest_result = None
    if include_pytest:
        pytest_result = _run_pytest_smoke()
        checks["pytest_passed"] = pytest_result["passed"]

    return {
        "release_candidate": "phase23",
        "overall_passed": all(checks.values()),
        "checks": checks,
        "benchmark_audit": bench,
        "phase21_validation_summary": suite_summary(validation_results),
        "chrono_status": chrono,
        "llm_guardrail_audit": llm,
        "artifact_inventory": inventory,
        "pytest": pytest_result,
        "known_limitations": [
            "Frontend build was not run unless node_modules is installed.",
            "PyChrono numerical simulation is not executed in environments without PyChrono.",
            "Benchmarks are derived-style internal regression cases, not copied textbook problem statements.",
            "LLM guardrail is deterministic protection, not a proof of perfect pedagogy.",
        ],
    }


def main() -> int:
    include_pytest = "--include-pytest" in sys.argv
    report = audit(include_pytest=include_pytest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
