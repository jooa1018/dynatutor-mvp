from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.observability.contracts import StableSnapshot
from engine.observability.reporting import (
    PHASE50_CASE_IDS,
    PHASE51_CASE_IDS,
    build_cross_engine_core,
    build_performance_artifact,
)
from engine.observability.trace import SolveTraceCollector
from tools import run_phase52_observability as runner


SHA = "b" * 40


def _routing():
    return {
        "routing": {"correct": 2, "total": 2},
        "numeric": {"checked": 2},
        "negative": {"checked": 2, "false_positives": []},
        "clarify": {
            "crafted": [{}, {}],
            "crafted_fired": 2,
            "crafted_rule_ok": 2,
            "fp": [],
        },
    }


def _golden():
    return {
        "cases": [
            {
                "id": "case-a",
                "domain": "kinematics",
                "problem_text": "RAW_SENTINEL_A",
                "expected_status": "solved",
                "expected_answers": [{"numeric": 2.0}],
                "tolerance": {"absolute": 1e-6, "relative": 1e-6},
            },
            {
                "id": "case-b",
                "domain": "energy",
                "problem_text": "RAW_SENTINEL_B",
                "expected_status": "solved",
                "expected_answers": [{"numeric": 2.0}],
                "tolerance": {"absolute": 1e-6, "relative": 1e-6},
            },
        ]
    }


class FakeCollector:
    def __init__(self, request_id: str, duration: float):
        self.snapshot = _trace_snapshot(request_id)
        self.stage_durations = {
            "parse": duration,
            "route": duration * 2,
            "solve": duration * 3,
            "verify": duration * 4,
        }


def _collector_factory(duration: float):
    return lambda request_id: FakeCollector(request_id, duration)


def _solve(_problem, *, trace_collector):
    return {"ok": True, "answer": {"numeric": 2.0}}


def _trace_snapshot(request_id: str) -> StableSnapshot:
    values = iter(float(index) for index in range(8))
    collector = SolveTraceCollector(request_id, clock=lambda: next(values))
    collector.begin()
    for stage in ("parse", "route", "solve", "verify"):
        collector.start_stage(stage)
        collector.finish_stage(stage)
    return collector.finalize("passed")


def _phase50_builder():
    return {
        "cases": [
            {
                "case_id": case_id,
                "status": "completed",
                "passed": True,
                "checks": {
                    "analytic_contract_passed": True,
                    "constraint_policy_passed": True,
                    "energy_policy_passed": True,
                },
                "final_state": {"x": index},
                "analytic_error": {"passed": True},
                "constraint_violation": {"passed": True},
                "invariant_drift": {"passed": True},
                "runtime_versions": {"sympy": "1.14", "scipy": "1.17"},
            }
            for index, case_id in enumerate(sorted(PHASE50_CASE_IDS))
        ]
    }


def _phase51_builder():
    return {
        "schema_version": 1,
        "report_version": "phase51-pychrono-report-v1",
        "environment": {"chrono_versions": []},
        "cases": [
            {
                "case_id": case_id,
                "analytic_value": 2.0,
                "passed": False,
                "product": {"required": True, "status": "solved", "value": 2.0, "unit": "m/s"},
                "chrono": {
                    "status": "skipped",
                    "value": None,
                    "unit": "m/s",
                    "chrono_version": "unavailable",
                    "solver": "not_initialized:PSOR_requested",
                    "contact_method": "SMC",
                    "time_step": 0.0005,
                    "initial_conditions": {
                        "time_step_s": 0.0005,
                        "solver_max_iterations": 200,
                        "collision_envelope_m": 0.001,
                        "collision_safe_margin_m": 0.0005,
                    },
                    "modeling_assumptions": ["offline optional dependency"],
                },
                "comparisons": {},
            }
            for case_id in sorted(PHASE51_CASE_IDS)
        ],
    }


def _minimal_snapshots():
    core = build_cross_engine_core(
        source_commit=SHA,
        tier="fast",
        traces=[_trace_snapshot("fixture").to_dict()],
        phase50_payload={},
        phase51_payload={},
        dashboard_sources={
            "golden": {"passed": 1, "total": 1},
            "false_solve": {"false": 0, "total": 1},
            "clarification": {"true_positive": 1, "false_positive": 0, "fired": 1, "total": 1, "precision_denominator": 1},
            "routing": {"correct": 1, "total": 1},
            "residual_invariant_failures": 0,
            "numeric_checked": 1,
        },
        runtime_versions={"sympy": "1", "scipy": "1", "pychrono": None},
    )
    performance = build_performance_artifact(
        source_commit=SHA,
        tier="fast",
        case_samples={
            "fixture": [
                {"parse": 1.0, "route": 1.0, "solve": 1.0, "verify": 1.0, "end_to_end": 4.0}
            ]
        },
        repeats=1,
    )
    return core, performance


@pytest.mark.unit
def test_collect_requires_exact_source_commit():
    with pytest.raises(ValueError, match="source_commit"):
        runner.collect_evidence(
            source_commit="",
            tier="fast",
            repeats=1,
            golden_payload=_golden(),
            routing_payload=_routing(),
            solve=_solve,
            collector_factory=_collector_factory(0.001),
        )


@pytest.mark.unit
def test_independent_collection_keeps_core_equal_and_timings_separate():
    common = dict(
        source_commit=SHA,
        tier="extended",
        repeats=2,
        golden_payload=_golden(),
        routing_payload=_routing(),
        solve=_solve,
        phase50_builder=_phase50_builder,
        phase51_builder=_phase51_builder,
    )
    first_core, first_performance = runner.collect_evidence(
        **common,
        collector_factory=_collector_factory(0.001),
    )
    second_core, second_performance = runner.collect_evidence(
        **common,
        collector_factory=_collector_factory(0.002),
    )
    assert first_core.canonical_bytes == second_core.canonical_bytes
    assert first_performance.canonical_bytes != second_performance.canonical_bytes
    assert "duration" not in first_core.canonical_json
    assert "RAW_SENTINEL" not in first_core.canonical_json
    assert len(first_core.to_dict()["cross_engine_cases"]) == 13


@pytest.mark.unit
def test_collect_rejects_nondeterministic_trace_core():
    counter = iter(("first", "second"))

    class ChangingCollector(FakeCollector):
        def __init__(self, request_id):
            super().__init__(request_id + next(counter), 0.001)

    with pytest.raises(ValueError, match="nondeterministic trace core"):
        runner.collect_evidence(
            source_commit=SHA,
            tier="fast",
            repeats=2,
            golden_payload={"cases": [_golden()["cases"][0]]},
            routing_payload=_routing(),
            solve=_solve,
            collector_factory=ChangingCollector,
        )


@pytest.mark.unit
def test_pure_render_and_validate_are_byte_deterministic():
    core, performance = _minimal_snapshots()
    performance_content = performance.canonical_json + "\n"
    first_json, first_md, first_report = runner.render_evidence(
        core_payload=core.to_dict(),
        performance_payload=performance.to_dict(),
        performance_filename="performance.json",
        performance_content=performance_content,
        pooled_performance_gate="passed",
        flaky_test_count=0,
        strict=False,
    )
    second_json, second_md, _ = runner.render_evidence(
        core_payload=core.to_dict(),
        performance_payload=performance.to_dict(),
        performance_filename="performance.json",
        performance_content=performance_content,
        pooled_performance_gate="passed",
        flaky_test_count=0,
        strict=False,
    )
    assert first_json == second_json
    assert first_md == second_md
    runner.validate_evidence(
        core_payload=core.to_dict(),
        performance_payload=performance.to_dict(),
        performance_filename="performance.json",
        performance_content=performance_content,
        report_payload=first_report,
        pooled_performance_gate="passed",
        flaky_test_count=0,
        strict=False,
    )


@pytest.mark.unit
def test_cli_collect_render_validate_use_injected_fixture_without_heavy_runtime(monkeypatch, tmp_path: Path):
    core, performance = _minimal_snapshots()
    monkeypatch.setattr(runner, "collect_evidence", lambda **_kwargs: (core, performance))
    golden = tmp_path / "golden.json"
    routing = tmp_path / "routing.json"
    golden.write_text(json.dumps(_golden()), encoding="utf-8")
    routing.write_text(json.dumps(_routing()), encoding="utf-8")
    core_path = tmp_path / "core.json"
    performance_path = tmp_path / "performance.json"
    report_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    assert runner.main([
        "collect",
        "--source-commit", SHA,
        "--tier", "fast",
        "--core-out", str(core_path),
        "--performance-out", str(performance_path),
        "--golden", str(golden),
        "--routing-report", str(routing),
    ]) == 0
    assert core_path.read_text(encoding="utf-8").endswith("\n")
    assert performance_path.read_text(encoding="utf-8").endswith("\n")

    render_args = [
        "render",
        "--core", str(core_path),
        "--performance", str(performance_path),
        "--json-out", str(report_path),
        "--markdown-out", str(markdown_path),
        "--pooled-performance-gate", "passed",
    ]
    assert runner.main(render_args) == 0
    first_json = report_path.read_bytes()
    first_md = markdown_path.read_bytes()
    assert runner.main(render_args) == 0
    assert report_path.read_bytes() == first_json
    assert markdown_path.read_bytes() == first_md
    assert runner.main([
        "validate",
        "--core", str(core_path),
        "--performance", str(performance_path),
        "--json-report", str(report_path),
        "--pooled-performance-gate", "passed",
    ]) == 0


@pytest.mark.unit
def test_cli_validate_detects_performance_artifact_tamper(tmp_path: Path):
    core, performance = _minimal_snapshots()
    performance_content = performance.canonical_json + "\n"
    report_json, _, _ = runner.render_evidence(
        core_payload=core.to_dict(),
        performance_payload=performance.to_dict(),
        performance_filename="performance.json",
        performance_content=performance_content,
        pooled_performance_gate="passed",
        flaky_test_count=0,
        strict=False,
    )
    core_path = tmp_path / "core.json"
    performance_path = tmp_path / "performance.json"
    report_path = tmp_path / "report.json"
    core_path.write_text(core.canonical_json + "\n", encoding="utf-8")
    performance_path.write_text(
        performance_content.replace('"mean_ms":4', '"mean_ms":5'),
        encoding="utf-8",
    )
    report_path.write_text(report_json, encoding="utf-8")
    with pytest.raises(ValueError):
        runner.main([
            "validate",
            "--core", str(core_path),
            "--performance", str(performance_path),
            "--json-report", str(report_path),
            "--pooled-performance-gate", "passed",
        ])


@pytest.mark.unit
def test_nightly_external_pooled_evidence_accepts_only_successful_pull_request_release_step():
    repository_root = Path(__file__).resolve().parents[2]
    workflow = (
        repository_root / ".github" / "workflows" / "phase52-quality.yml"
    ).read_text(encoding="utf-8")
    evidence_block = workflow.split(
        "- name: Verify external Release exact-HEAD pooled gate evidence", 1
    )[1].split("- name: Render the same evidence twice", 1)[0]
    assert "head_sha=${PHASE52_SHA}" in evidence_block
    assert '.event == "pull_request"' in evidence_block
    assert '.conclusion == "success"' in evidence_block
    assert '.name == "test"' in evidence_block
    assert '.name == "Compare pooled PR10 hotfix performance"' in evidence_block
    assert "workflow_dispatch" not in evidence_block
    assert '.event == "push"' not in evidence_block
