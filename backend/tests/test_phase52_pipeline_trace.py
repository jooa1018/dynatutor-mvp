from __future__ import annotations

import json

import pytest

from engine import services
from engine.observability.contracts import FORBIDDEN_TRACE_KEYS
from engine.observability.trace import SolveTraceCollector
from engine.routing.clarify import ClarifyPatchError
from engine.solvers.registry import SolverRegistry


SOLVED = "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라."
CLARIFY = "30도 경사면 위 블록의 가속도를 구하라."
UNSUPPORTED = "3차원에서 알짜힘 4N이 작용할 때 가속도는?"


class StepClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        value = self.value
        self.value += 0.25
        return value


class RaisingCollector:
    @property
    def current_stage(self):
        raise RuntimeError("collector current stage failure")

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise RuntimeError(f"collector {name} failure")

        return fail


def _json(response):
    return response.model_dump(mode="json")


def _assert_complete_core(core):
    assert {
        "input",
        "student_answer",
        "normalization",
        "parse_candidates",
        "canonical_fingerprint",
        "clarification_decision",
        "route_candidates",
        "model_fingerprints",
        "equation_set",
        "solution_candidates",
        "validation_decision",
        "numeric_validations",
        "final_answer",
        "stages",
        "status",
        "error",
    } <= core.keys()
    assert [item["name"] for item in core["stages"]] == [
        "parse",
        "route",
        "solve",
        "verify",
    ]


def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


@pytest.mark.unit
def test_trace_on_and_off_return_identical_solve_response():
    baseline = services.solve_problem(SOLVED)
    collector = SolveTraceCollector("phase52-solved", clock=StepClock())
    traced = services.solve_problem(SOLVED, trace_collector=collector)

    assert _json(traced) == _json(baseline)
    core = collector.snapshot.to_dict()
    _assert_complete_core(core)
    assert all(item["status"] == "completed" for item in core["stages"])
    assert set(collector.stage_durations) == {"parse", "route", "solve", "verify"}
    assert "duration" not in collector.snapshot.canonical_json
    assert core["input"]["raw_text_hash"]
    assert core["canonical_fingerprint"]
    assert core["model_fingerprints"]["legacy"]["fingerprint"]
    assert core["model_fingerprints"]["typed"]["fingerprint"]


@pytest.mark.unit
def test_trace_none_does_not_invoke_hash_clock_or_projection(monkeypatch):
    import engine.observability.trace as trace_module

    def forbidden(*args, **kwargs):
        raise AssertionError("optional trace path was invoked")

    monkeypatch.setattr(trace_module, "sha256_text", forbidden)
    monkeypatch.setattr(trace_module, "project_legacy_model", forbidden)
    response = services.solve_problem(SOLVED)
    assert response.ok is True


@pytest.mark.unit
def test_collector_failures_are_product_fail_open():
    baseline = services.solve_problem(SOLVED)
    traced = services.solve_problem(SOLVED, trace_collector=RaisingCollector())
    assert _json(traced) == _json(baseline)


@pytest.mark.unit
def test_trace_does_not_add_pipeline_calls(monkeypatch):
    counts = {"extract": 0, "model": 0, "route": 0, "select": 0, "solver": 0, "verify": 0}
    original_extract = services.extract_problem
    original_model = services.build_physical_model
    original_route = SolverRegistry.route
    original_select = SolverRegistry.select
    original_verify = services.verify_result

    def extract(*args, **kwargs):
        counts["extract"] += 1
        return original_extract(*args, **kwargs)

    def model(*args, **kwargs):
        counts["model"] += 1
        return original_model(*args, **kwargs)

    def route(*args, **kwargs):
        counts["route"] += 1
        return original_route(*args, **kwargs)

    def select(*args, **kwargs):
        counts["select"] += 1
        solver = original_select(*args, **kwargs)
        if solver is not None and not getattr(solver, "_phase52_counted", False):
            method_name = "solve_candidates" if hasattr(solver, "solve_candidates") else "solve"
            original_solver = getattr(solver, method_name)

            def counted_solver(*solver_args, **solver_kwargs):
                counts["solver"] += 1
                return original_solver(*solver_args, **solver_kwargs)

            setattr(solver, method_name, counted_solver)
            setattr(solver, "_phase52_counted", True)
        return solver

    def verify(*args, **kwargs):
        counts["verify"] += 1
        return original_verify(*args, **kwargs)

    monkeypatch.setattr(services, "extract_problem", extract)
    monkeypatch.setattr(services, "build_physical_model", model)
    monkeypatch.setattr(SolverRegistry, "route", route)
    monkeypatch.setattr(SolverRegistry, "select", select)
    monkeypatch.setattr(services, "verify_result", verify)

    services.solve_problem(SOLVED)
    baseline_counts = dict(counts)
    collector = SolveTraceCollector("phase52-counts", clock=StepClock())
    services.solve_problem(SOLVED, trace_collector=collector)
    traced_counts = {key: counts[key] - baseline_counts[key] for key in counts}

    assert traced_counts == baseline_counts
    assert baseline_counts["extract"] == 1
    assert baseline_counts["model"] == 1
    assert baseline_counts["solver"] == 1


@pytest.mark.unit
def test_clarification_snapshot_keeps_complete_stage_lifecycle():
    collector = SolveTraceCollector("phase52-clarify", clock=StepClock())
    response = services.solve_problem(CLARIFY, trace_collector=collector)
    core = collector.snapshot.to_dict()

    assert response.ok is False
    assert response.clarification is not None
    _assert_complete_core(core)
    assert core["status"] == "inconclusive"
    assert core["clarification_decision"]["status"] == "clarify"
    assert all(item["status"] == "completed" for item in core["stages"])
    assert core["solution_candidates"] == []


@pytest.mark.unit
def test_unsupported_snapshot_has_explicit_empty_outcome():
    collector = SolveTraceCollector("phase52-unsupported", clock=StepClock())
    response = services.solve_problem(UNSUPPORTED, trace_collector=collector)
    core = collector.snapshot.to_dict()

    assert response.ok is False
    assert response.route_decision.status == "unsupported"
    assert response.clarification is None
    _assert_complete_core(core)
    assert core["status"] == "unsupported"
    assert core["solution_candidates"] == []
    assert core["final_answer"] == {"ok": False, "answers": []}
    assert all(item["status"] == "completed" for item in core["stages"])


@pytest.mark.unit
def test_stage_boundaries_reject_overlap_and_out_of_order_start():
    collector = SolveTraceCollector("phase52-exclusive-stages", clock=StepClock())
    collector.begin()
    collector.start_stage("parse")
    with pytest.raises(RuntimeError, match="may not overlap"):
        collector.start_stage("route")
    collector.finish_stage("parse")
    with pytest.raises(RuntimeError, match="requires route before solve"):
        collector.start_stage("solve")
    collector.start_stage("route")
    collector.finish_stage("route")


@pytest.mark.unit
def test_error_snapshot_preserves_invalid_patch_exception_type_and_message():
    patch = {"system_type": "__evil__"}
    with pytest.raises(ClarifyPatchError) as baseline:
        services.solve_problem(CLARIFY, clarify_patch=patch)

    collector = SolveTraceCollector("phase52-invalid-patch", clock=StepClock())
    with pytest.raises(ClarifyPatchError) as traced:
        services.solve_problem(CLARIFY, clarify_patch=patch, trace_collector=collector)

    assert str(traced.value) == str(baseline.value)
    core = collector.snapshot.to_dict()
    _assert_complete_core(core)
    assert core["status"] == "error"
    assert core["error"] == {"stage": "parse", "exception_type": "ClarifyPatchError"}
    assert core["stages"][0]["status"] == "error"


@pytest.mark.unit
def test_injected_parser_exception_is_unchanged(monkeypatch):
    class ParserBoom(RuntimeError):
        pass

    def parser_boom(_):
        raise ParserBoom("parser exact message")

    monkeypatch.setattr(services, "extract_problem", parser_boom)
    parser_collector = SolveTraceCollector("phase52-parser-error", clock=StepClock())
    with pytest.raises(ParserBoom, match="^parser exact message$"):
        services.solve_problem(SOLVED, trace_collector=parser_collector)
    assert parser_collector.snapshot.to_dict()["error"] == {
        "stage": "parse",
        "exception_type": "ParserBoom",
    }


@pytest.mark.unit
def test_injected_solver_exception_is_unchanged(monkeypatch):
    class SolverBoom(RuntimeError):
        pass

    class BoomSolver:
        name = "phase52_injected_solver"
        reason = "test double"

        def solve_candidates(self, canonical):
            raise SolverBoom("solver exact message")

    monkeypatch.setattr(SolverRegistry, "select", lambda self, canonical, decision=None: BoomSolver())
    collector = SolveTraceCollector("phase52-solver-error", clock=StepClock())
    with pytest.raises(SolverBoom, match="^solver exact message$"):
        services.solve_problem(SOLVED, trace_collector=collector)
    assert collector.snapshot.to_dict()["error"] == {
        "stage": "solve",
        "exception_type": "SolverBoom",
    }


@pytest.mark.unit
def test_raw_and_student_sentinels_never_appear_in_snapshot_json():
    raw_sentinel = "RAW_SENTINEL_52_981bc970"
    student_sentinel = "STUDENT_SENTINEL_52_631cfab1"
    collector = SolveTraceCollector("phase52-privacy", clock=StepClock())
    services.solve_problem(
        f"{raw_sentinel} 지원되지 않는 문제",
        student_solution=student_sentinel,
        trace_collector=collector,
    )

    rendered = collector.snapshot.canonical_json
    core = json.loads(rendered)
    assert raw_sentinel not in rendered
    assert student_sentinel not in rendered
    assert core["student_answer"]["present"] is True
    assert core["student_answer"]["length"] == len(student_sentinel)
    assert not (set(_walk_keys(core)) & FORBIDDEN_TRACE_KEYS)
