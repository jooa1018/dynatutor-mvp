from __future__ import annotations

"""Collect, render, and validate Phase 52 observability evidence."""

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
import os
from pathlib import Path
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from engine.observability.contracts import StableSnapshot, sha256_text, stable_json_dumps  # noqa: E402
from engine.observability.reporting import (  # noqa: E402
    TIERS,
    build_cross_engine_core,
    build_final_report,
    build_performance_artifact,
    dashboard_sources_from_routing_report,
    normalize_phase50_report,
    normalize_phase51_report,
    render_final_json,
    render_final_markdown,
    validate_core,
    validate_final_report,
    validate_performance,
)
from engine.observability.trace import SolveTraceCollector  # noqa: E402


DEFAULT_GOLDEN = BACKEND_ROOT / "tests" / "golden" / "phase42_dynamics_cases.json"
DEFAULT_ROUTING_REPORT = BACKEND_ROOT / "reports" / "routing_confusion" / "report.json"
DEFAULT_CORE = BACKEND_ROOT / "reports" / "generated" / "phase52_core.json"
DEFAULT_PERFORMANCE = BACKEND_ROOT / "reports" / "generated" / "phase52_performance.json"
DEFAULT_JSON = BACKEND_ROOT / "reports" / "generated" / "phase52_report.json"
DEFAULT_MARKDOWN = BACKEND_ROOT / "reports" / "generated" / "phase52_report.md"
POOLED_GATE_VALUES = ("passed", "failed", "inconclusive")


def _atomic_write(path: Path, content: str) -> None:
    if not content.endswith("\n"):
        raise ValueError("atomic text output must end with one newline")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _snapshot_dict(collector: Any) -> dict[str, Any]:
    snapshot = collector.snapshot
    if isinstance(snapshot, StableSnapshot):
        return snapshot.to_dict()
    if isinstance(snapshot, Mapping):
        return dict(snapshot)
    if hasattr(snapshot, "to_dict"):
        return dict(snapshot.to_dict())
    raise TypeError("collector snapshot must be a StableSnapshot or mapping")


def _response_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    return dict(response) if isinstance(response, Mapping) else {}


def _observed_status(response: Any) -> str:
    payload = _response_dict(response)
    if payload.get("ok") is True:
        return "solved"
    if payload.get("clarification") is not None:
        return "needs_clarification"
    route = payload.get("route_decision")
    if isinstance(route, Mapping) and route.get("status") == "unsupported":
        return "unsupported"
    return "error"


def _answer_values(response: Any) -> list[float]:
    payload = _response_dict(response)
    answer = payload.get("answer")
    if not isinstance(answer, Mapping):
        return []
    values: list[float] = []
    if answer.get("numeric") is not None:
        values.append(float(answer["numeric"]))
    for alternatives in (answer.get("answers"), payload.get("answers")):
        if not isinstance(alternatives, list):
            continue
        for item in alternatives:
            if isinstance(item, Mapping) and item.get("numeric") is not None:
                values.append(float(item["numeric"]))
    return values


def _golden_matches(case: Mapping[str, Any], response: Any) -> bool:
    if _observed_status(response) != case.get("expected_status"):
        return False
    if case.get("expected_status") != "solved":
        return True
    expected = [
        float(item["numeric"])
        for item in case.get("expected_answers", [])
        if isinstance(item, Mapping) and item.get("numeric") is not None
    ]
    if not expected:
        return True
    observed = _answer_values(response)
    if not observed:
        return False
    tolerance = case.get("tolerance", {})
    absolute = float(tolerance.get("absolute", 0.0))
    relative = float(tolerance.get("relative", 0.0))
    return all(
        any(abs(actual - target) <= max(absolute, relative * max(abs(target), 1.0)) for actual in observed)
        for target in expected
    )


def _selected_golden_cases(payload: Mapping[str, Any], tier: str) -> list[dict[str, Any]]:
    cases = [dict(item) for item in payload.get("cases", []) if isinstance(item, Mapping)]
    if tier != "fast":
        return cases
    # Stable representative smoke: the first case from each domain, capped at
    # eight to keep PR-fast bounded while exercising real product traces.
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in cases:
        domain = str(case.get("domain", "unknown"))
        if domain in seen:
            continue
        selected.append(case)
        seen.add(domain)
        if len(selected) == 8:
            break
    return selected


def _default_phase50_builder() -> dict[str, Any]:
    from tools.run_phase50_numeric_validation import build_report

    return build_report()


def _default_phase51_builder() -> dict[str, Any]:
    from tools.chrono_validation.phase51_runner import run_phase51_suite

    return run_phase51_suite()


def _default_solver(problem: str, *, trace_collector: Any) -> Any:
    from engine.services import solve_problem

    return solve_problem(problem, trace_collector=trace_collector)


def collect_evidence(
    *,
    source_commit: str,
    tier: str,
    repeats: int,
    golden_payload: Mapping[str, Any],
    routing_payload: Mapping[str, Any],
    solve: Callable[..., Any] = _default_solver,
    collector_factory: Callable[[str], Any] = SolveTraceCollector,
    phase50_builder: Callable[[], Mapping[str, Any]] = _default_phase50_builder,
    phase51_builder: Callable[[], Mapping[str, Any]] = _default_phase51_builder,
    llm_identifier: str | None = None,
) -> tuple[StableSnapshot, StableSnapshot]:
    """Collect immutable trace/cross-engine core and volatile timings separately."""

    if not source_commit:
        raise ValueError("source_commit is required")
    if tier not in TIERS:
        raise ValueError(f"unsupported tier: {tier}")
    if repeats < 1:
        raise ValueError("repeats must be positive")

    traces: list[dict[str, Any]] = []
    samples: dict[str, list[dict[str, float]]] = {}
    golden_passed = 0
    selected = _selected_golden_cases(golden_payload, tier)
    for case in selected:
        case_id = str(case.get("id", ""))
        if not case_id:
            raise ValueError("golden case id is required")
        request_id = f"phase52-{sha256_text(case_id)[:20]}"
        expected_core: str | None = None
        samples[case_id] = []
        first_response: Any = None
        for repeat in range(repeats):
            collector = collector_factory(request_id)
            response = solve(str(case.get("problem_text", "")), trace_collector=collector)
            core = _snapshot_dict(collector)
            rendered = stable_json_dumps(core, enforce_privacy=True)
            if expected_core is None:
                expected_core = rendered
                traces.append(core)
                first_response = response
            elif rendered != expected_core:
                raise ValueError(f"nondeterministic trace core for {case_id} repeat {repeat + 1}")
            durations = dict(collector.stage_durations)
            if set(durations) != {"parse", "route", "solve", "verify"}:
                raise ValueError(f"incomplete stage timings for {case_id}")
            stage_ms = {name: float(durations[name]) * 1000.0 for name in ("parse", "route", "solve", "verify")}
            stage_ms["end_to_end"] = sum(stage_ms.values())
            samples[case_id].append(stage_ms)
        golden_passed += int(_golden_matches(case, first_response))

    phase50_payload: Mapping[str, Any] = {}
    phase51_payload: Mapping[str, Any] = {}
    runtime_versions: dict[str, Any] = {}
    if tier in {"extended", "nightly"}:
        phase50_payload = phase50_builder()
        phase51_payload = phase51_builder()
        phase50_cases = list(phase50_payload.get("cases", []))
        if phase50_cases:
            runtime_versions.update(dict(phase50_cases[0].get("runtime_versions", {})))
        chrono_versions = list(dict(phase51_payload.get("environment", {})).get("chrono_versions", []))
        if len(chrono_versions) == 1:
            runtime_versions["pychrono"] = chrono_versions[0]

    normalized = normalize_phase50_report(phase50_payload) + normalize_phase51_report(phase51_payload)
    residual_failures = sum(
        check.get("passed") is False
        for case in normalized
        for check in case.get("invariant_checks", [])
        if isinstance(check, Mapping)
    )
    dashboard_sources = dashboard_sources_from_routing_report(
        routing_payload,
        golden_passed=golden_passed,
        golden_total=len(selected),
        residual_invariant_failures=residual_failures,
    )
    core = build_cross_engine_core(
        source_commit=source_commit,
        tier=tier,
        traces=traces,
        phase50_payload=phase50_payload,
        phase51_payload=phase51_payload,
        dashboard_sources=dashboard_sources,
        runtime_versions=runtime_versions,
        llm_identifier=llm_identifier,
    )
    performance = build_performance_artifact(
        source_commit=source_commit,
        tier=tier,
        case_samples=samples,
        repeats=repeats,
    )
    return core, performance


def render_evidence(
    *,
    core_payload: Mapping[str, Any],
    performance_payload: Mapping[str, Any],
    performance_filename: str,
    performance_content: str,
    pooled_performance_gate: str,
    flaky_test_count: int,
    strict: bool,
) -> tuple[str, str, dict[str, Any]]:
    report = build_final_report(
        core=core_payload,
        performance=performance_payload,
        performance_filename=performance_filename,
        performance_content=performance_content,
        pooled_performance_gate=pooled_performance_gate,
        flaky_test_count=flaky_test_count,
        strict=strict,
    )
    return render_final_json(report), render_final_markdown(report), report


def validate_evidence(
    *,
    core_payload: Mapping[str, Any],
    performance_payload: Mapping[str, Any],
    performance_filename: str,
    performance_content: str,
    report_payload: Mapping[str, Any],
    pooled_performance_gate: str,
    flaky_test_count: int,
    strict: bool,
) -> None:
    validate_core(core_payload)
    validate_performance(performance_payload)
    expected_json, _, expected = render_evidence(
        core_payload=core_payload,
        performance_payload=performance_payload,
        performance_filename=performance_filename,
        performance_content=performance_content,
        pooled_performance_gate=pooled_performance_gate,
        flaky_test_count=flaky_test_count,
        strict=strict,
    )
    if stable_json_dumps(report_payload) + "\n" != expected_json:
        raise ValueError("final report does not match immutable evidence inputs")
    validate_final_report(expected, strict=strict)


def _collect_command(args: argparse.Namespace) -> int:
    golden = _read_json(args.golden)
    routing = _read_json(args.routing_report)
    core, performance = collect_evidence(
        source_commit=args.source_commit,
        tier=args.tier,
        repeats=args.repeats,
        golden_payload=golden,
        routing_payload=routing,
        llm_identifier=args.llm_identifier,
    )
    _atomic_write(args.core_out, core.canonical_json + "\n")
    _atomic_write(args.performance_out, performance.canonical_json + "\n")
    return 0


def _render_command(args: argparse.Namespace) -> int:
    core = _read_json(args.core)
    performance_content = args.performance.read_text(encoding="utf-8")
    performance = json.loads(performance_content)
    json_text, markdown_text, _ = render_evidence(
        core_payload=core,
        performance_payload=performance,
        performance_filename=args.performance.name,
        performance_content=performance_content,
        pooled_performance_gate=args.pooled_performance_gate,
        flaky_test_count=args.flaky_test_count,
        strict=args.strict,
    )
    _atomic_write(args.json_out, json_text)
    _atomic_write(args.markdown_out, markdown_text)
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    core = _read_json(args.core)
    performance_content = args.performance.read_text(encoding="utf-8")
    performance = json.loads(performance_content)
    report = _read_json(args.json_report)
    validate_evidence(
        core_payload=core,
        performance_payload=performance,
        performance_filename=args.performance.name,
        performance_content=performance_content,
        report_payload=report,
        pooled_performance_gate=args.pooled_performance_gate,
        flaky_test_count=args.flaky_test_count,
        strict=args.strict,
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 52 deterministic observability evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect")
    collect.add_argument("--source-commit", required=True)
    collect.add_argument("--tier", choices=TIERS, required=True)
    collect.add_argument("--core-out", type=Path, required=True)
    collect.add_argument("--performance-out", type=Path, required=True)
    collect.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    collect.add_argument("--routing-report", type=Path, default=DEFAULT_ROUTING_REPORT)
    collect.add_argument("--seed", type=int, default=5200, help="fixed compatibility seed; collection contains no random sampling")
    collect.add_argument("--repeats", type=int, default=1)
    collect.add_argument("--llm-identifier")
    collect.set_defaults(handler=_collect_command)

    render = subparsers.add_parser("render")
    render.add_argument("--core", type=Path, required=True)
    render.add_argument("--performance", type=Path, required=True)
    render.add_argument("--json-out", type=Path, required=True)
    render.add_argument("--markdown-out", type=Path, required=True)
    render.add_argument("--pooled-performance-gate", choices=POOLED_GATE_VALUES, default="inconclusive")
    render.add_argument("--flaky-test-count", type=int, default=0)
    render.add_argument("--strict", action="store_true")
    render.set_defaults(handler=_render_command)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--core", type=Path, required=True)
    validate.add_argument("--performance", type=Path, required=True)
    validate.add_argument("--json-report", type=Path, required=True)
    validate.add_argument("--pooled-performance-gate", choices=POOLED_GATE_VALUES, default="inconclusive")
    validate.add_argument("--flaky-test-count", type=int, default=0)
    validate.add_argument("--strict", action="store_true")
    validate.set_defaults(handler=_validate_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if getattr(args, "flaky_test_count", 0) < 0:
        raise ValueError("flaky_test_count may not be negative")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "collect_evidence",
    "main",
    "render_evidence",
    "validate_evidence",
]
