"""Two-phase solver worker protocol: bounded startup, READY/START, fail-closed.

Startup (spawn + imports + child-side plan/backend revalidation) must never
spend solve budget; the solve clock starts only after the parent validates the
exact READY message and dispatches START.  Every protocol deviation fails
closed without a numeric result and without an orphan process.
"""

from __future__ import annotations

import multiprocessing
import time

import pytest

from engine.mechanics.compiler.contracts import (
    EquationGraph,
    EquationNode,
    EquationScope,
    IncidenceEdge,
    LawApplication,
    RankAnalysis,
    SymbolNode,
)
from engine.mechanics.math_ast import (
    DimensionVector,
    Equality,
    SymbolDefinition,
    SymbolRef,
)
from engine.mechanics.solver.contracts import SolvePhase, SolverBudget
from engine.mechanics.solver import isolation as solver_isolation
from engine.mechanics.solver.isolation import (
    WORKER_HANDSHAKE_FAILURES,
    IsolationStatus,
    _await_worker_start,
    _decode_worker_payload,
    _encode_worker_payload,
    _handshaked_worker,
    _is_handshake_shaped,
    _plan_digest,
    _ready_message,
    _receive_handshake_message,
    _run_handshaked_worker,
    _start_message,
    _worker_main,
    run_isolated_backend,
    run_isolated_completeness_audit,
)
from engine.mechanics.solver.planner import plan_equation_graph


DIMENSIONLESS = DimensionVector()
SCOPE = EquationScope()


def _symbol(symbol_id: str, known: float | None = None) -> SymbolNode:
    quantity_id = f"quantity_{symbol_id}"
    return SymbolNode(
        symbol=SymbolDefinition(
            symbol_id=symbol_id,
            quantity_id=quantity_id,
            dimension=DIMENSIONLESS,
        ),
        quantity_id=quantity_id,
        quantity_role="parameter" if known is not None else "position",
        known_si_value=known,
    )


def _trivial_graph() -> EquationGraph:
    equation = EquationNode(
        equation_id="eq1",
        expression=Equality(
            left=SymbolRef(symbol_id="x"), right=SymbolRef(symbol_id="two")
        ),
        expression_fingerprint=f"{101:064x}",
        law_id="law1",
        scope=SCOPE,
        dimension=DIMENSIONLESS,
        complexity_cost=5,
    )
    return EquationGraph(
        query_id="query1",
        query_symbol_id="x",
        symbols=(_symbol("two", 2.0), _symbol("x")),
        equations=(equation,),
        constraints=(),
        applications=(
            LawApplication(
                application_id="application1",
                law_id="law1",
                equation_ids=("eq1",),
                scope=SCOPE,
                complexity_cost=5,
            ),
        ),
        incidence=(IncidenceEdge(equation_id="eq1", symbol_id="x"),),
        rank=RankAnalysis(
            equality_count=1,
            inequality_count=0,
            unknown_count=1,
            structural_rank=1,
            underdetermined=False,
            overdetermined=False,
            conflicting=False,
        ),
        selected_equation_ids=("eq1",),
        fingerprint="d" * 64,
    )


def _trivial_plan(budget: SolverBudget | None = None):
    return plan_equation_graph(_trivial_graph(), budget)


def _assert_no_worker_children() -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not multiprocessing.active_children():
            return
        time.sleep(0.05)
    assert multiprocessing.active_children() == []


class _RecordingSender:
    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.closed = False

    def send_bytes(self, encoded: bytes) -> None:
        self.frames.append(encoded)

    def close(self) -> None:
        self.closed = True


class _UnusedStartReceiver:
    def __init__(self) -> None:
        self.polled = False
        self.closed = False

    def poll(self, _timeout: float = 0.0) -> bool:
        self.polled = True
        return False

    def recv_bytes(self, maxlength: int | None = None) -> bytes:
        self.polled = True
        raise EOFError

    def close(self) -> None:
        self.closed = True


# --- spawn targets (must be module top-level for the spawn context) ---------


def _slow_start_worker(sender, start_receiver, plan_json, backend_value) -> None:
    """Startup slower than the whole solve budget, then a normal worker."""

    time.sleep(1.2)
    _worker_main(sender, start_receiver, plan_json, backend_value)


def _hang_after_start_worker(sender, start_receiver, plan_json, backend_value) -> None:
    """Valid handshake, then a solve that never returns."""

    digest = _plan_digest(plan_json)
    sender.send_bytes(_encode_worker_payload(_ready_message(digest, backend_value)))
    if not _await_worker_start(start_receiver, digest):
        return
    time.sleep(3600.0)


def _double_ready_worker(sender, start_receiver, plan_json, backend_value) -> None:
    """Valid handshake, then a duplicate READY where the result belongs."""

    digest = _plan_digest(plan_json)
    ready = _encode_worker_payload(_ready_message(digest, backend_value))
    sender.send_bytes(ready)
    if not _await_worker_start(start_receiver, digest):
        return
    sender.send_bytes(ready)


def _silent_exit_worker(sender, start_receiver, plan_json, backend_value) -> None:
    """Crash before READY: exit without sending anything."""

    sender.close()
    start_receiver.close()


def _broken_start_pipe_worker(sender, start_receiver, plan_json, backend_value) -> None:
    """Close the START channel before READY so parent dispatch must fail."""

    start_receiver.close()
    digest = _plan_digest(plan_json)
    sender.send_bytes(_encode_worker_payload(_ready_message(digest, backend_value)))
    time.sleep(30.0)


# --- protocol message shape -------------------------------------------------


def test_handshake_messages_carry_only_protocol_identity() -> None:
    ready = _ready_message("a" * 64, "linear_symbolic")
    start = _start_message("a" * 64)
    assert set(ready) == {"kind", "protocol", "backend", "plan_sha256"}
    assert set(start) == {"kind", "protocol", "plan_sha256"}
    forbidden = {
        "case_id",
        "family",
        "split",
        "expected_answer",
        "expected_terminal",
        "answer",
        "gold",
    }
    assert forbidden.isdisjoint(ready)
    assert forbidden.isdisjoint(start)
    assert tuple(WORKER_HANDSHAKE_FAILURES) == (
        "startup_timeout",
        "startup_crash",
        "startup_protocol_violation",
        "start_dispatch_failure",
        "duplicate_handshake_reply",
    )


def test_handshake_shape_detector_flags_both_message_kinds() -> None:
    assert _is_handshake_shaped(_ready_message("a" * 64, "linear_symbolic"))
    assert _is_handshake_shaped(_start_message("a" * 64))
    assert _is_handshake_shaped({"protocol": "anything"})
    assert not _is_handshake_shaped({"status": "backend_failure"})
    assert not _is_handshake_shaped({"status": "success", "roots": []})


def test_receive_handshake_times_out_closes_and_survives_malformed_bytes() -> None:
    receiver, sender = multiprocessing.get_context("spawn").Pipe(duplex=False)
    try:
        assert _receive_handshake_message(receiver, 0.01) == ("timeout", None)
        sender.send_bytes(b"not json at all")
        status, payload = _receive_handshake_message(receiver, 1.0)
        assert status == "message"
        assert payload is not None
        assert payload != _ready_message(_plan_digest("{}"), "linear_symbolic")
        sender.send_bytes(b"x" * 8192)  # over the handshake frame cap
        assert _receive_handshake_message(receiver, 1.0) == ("closed", None)
    finally:
        sender.close()
        receiver.close()


def test_receive_handshake_reports_eof_as_closed() -> None:
    receiver, sender = multiprocessing.get_context("spawn").Pipe(duplex=False)
    sender.close()
    try:
        assert _receive_handshake_message(receiver, 0.5) == ("closed", None)
    finally:
        receiver.close()


def test_wrong_protocol_version_and_mutated_ready_fields_are_rejected() -> None:
    digest = _plan_digest("{}")
    expected = _ready_message(digest, "linear_symbolic")
    for mutation in (
        {**expected, "protocol": "phase56-stage7-solver-worker-handshake-v0"},
        {**expected, "kind": "worker_start"},
        {**expected, "backend": "numeric_root"},
        {**expected, "plan_sha256": "b" * 64},
        {**expected, "extra": True},
        {"status": "success"},
    ):
        assert mutation != expected


def test_await_worker_start_accepts_only_the_exact_start_message() -> None:
    digest = _plan_digest("{}")
    cases = (
        (_encode_worker_payload(_start_message(digest)), True),
        (_encode_worker_payload(_start_message("c" * 64)), False),
        (_encode_worker_payload(_ready_message(digest, "linear_symbolic")), False),
        (b"garbage", False),
    )
    for frame, expected in cases:
        receiver, sender = multiprocessing.get_context("spawn").Pipe(duplex=False)
        try:
            sender.send_bytes(frame)
            assert _await_worker_start(receiver, digest) is expected
        finally:
            sender.close()
            receiver.close()


# --- child-side validation before READY -------------------------------------


def test_invalid_plan_is_rejected_before_ready() -> None:
    sender = _RecordingSender()
    start_receiver = _UnusedStartReceiver()
    _worker_main(sender, start_receiver, "{}", "linear_symbolic")
    assert len(sender.frames) == 1
    payload = _decode_worker_payload(sender.frames[0])
    assert payload["status"] == "backend_failure"
    assert not _is_handshake_shaped(payload)
    assert not start_receiver.polled
    assert sender.closed and start_receiver.closed


def test_unsupported_backend_is_rejected_before_ready() -> None:
    plan_json = _trivial_plan().model_dump_json()
    sender = _RecordingSender()
    start_receiver = _UnusedStartReceiver()
    _worker_main(sender, start_receiver, plan_json, "no_such_backend")
    assert len(sender.frames) == 1
    payload = _decode_worker_payload(sender.frames[0])
    assert payload["status"] == "backend_failure"
    assert not _is_handshake_shaped(payload)
    assert not start_receiver.polled


def test_child_sends_ready_then_refuses_to_solve_without_valid_start() -> None:
    plan = _trivial_plan()
    plan_json = plan.model_dump_json()
    sender = _RecordingSender()
    start_receiver = _UnusedStartReceiver()  # poll() is False: no START arrives
    _handshaked_worker(
        sender,
        start_receiver,
        plan_json,
        plan.primary_backend.value,
        execute=lambda *_: pytest.fail("solve must not run without START"),
        failure_payload=dict,
    )
    assert len(sender.frames) == 1
    assert _decode_worker_payload(sender.frames[0]) == _ready_message(
        _plan_digest(plan_json), plan.primary_backend.value
    )
    assert start_receiver.polled


# --- parent-side protocol enforcement (real spawned children) ---------------


def test_slow_startup_does_not_consume_solve_budget() -> None:
    plan = _trivial_plan()
    run = _run_handshaked_worker(
        target=_slow_start_worker,
        validated=plan,
        backend=plan.primary_backend,
        phase=SolvePhase.symbolic,
        limit_s=0.8,
        failure_payload_factory=solver_isolation._closed_failure_payload,
    )
    assert run.status is IsolationStatus.completed
    assert run.payload is not None and run.payload["status"] == "success"
    assert run.handshake_failure is None
    assert run.startup_elapsed_s > 0.8  # startup alone exceeded the whole budget
    assert run.elapsed_s < 0.8
    assert run.process_reaped
    _assert_no_worker_children()


def test_startup_timeout_before_ready_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(solver_isolation, "WORKER_STARTUP_TIME_LIMIT_S", 1.0e-9)
    plan = _trivial_plan()
    run = run_isolated_backend(plan, plan.primary_backend)
    assert run.status is IsolationStatus.completed
    assert run.handshake_failure == "startup_timeout"
    assert run.payload is not None
    assert run.payload["status"] == "backend_failure"
    assert run.payload["roots"] == []
    assert run.elapsed_s == 0.0
    assert run.process_reaped
    _assert_no_worker_children()


def test_child_crash_before_ready_fails_closed() -> None:
    plan = _trivial_plan()
    run = _run_handshaked_worker(
        target=_silent_exit_worker,
        validated=plan,
        backend=plan.primary_backend,
        phase=SolvePhase.symbolic,
        limit_s=5.0,
        failure_payload_factory=solver_isolation._closed_failure_payload,
    )
    assert run.status is IsolationStatus.completed
    assert run.handshake_failure == "startup_crash"
    assert run.payload is not None and run.payload["status"] == "backend_failure"
    assert run.elapsed_s == 0.0
    assert run.process_reaped
    _assert_no_worker_children()


def test_duplicate_ready_reply_is_never_a_solve_result() -> None:
    plan = _trivial_plan()
    run = _run_handshaked_worker(
        target=_double_ready_worker,
        validated=plan,
        backend=plan.primary_backend,
        phase=SolvePhase.symbolic,
        limit_s=5.0,
        failure_payload_factory=solver_isolation._closed_failure_payload,
    )
    assert run.status is IsolationStatus.completed
    assert run.handshake_failure == "duplicate_handshake_reply"
    assert run.payload is not None and run.payload["status"] == "backend_failure"
    assert run.payload["roots"] == []
    assert run.process_reaped
    _assert_no_worker_children()


def test_start_dispatch_failure_fails_closed() -> None:
    plan = _trivial_plan()
    run = _run_handshaked_worker(
        target=_broken_start_pipe_worker,
        validated=plan,
        backend=plan.primary_backend,
        phase=SolvePhase.symbolic,
        limit_s=5.0,
        failure_payload_factory=solver_isolation._closed_failure_payload,
    )
    assert run.status is IsolationStatus.completed
    assert run.handshake_failure == "start_dispatch_failure"
    assert run.payload is not None and run.payload["status"] == "backend_failure"
    assert run.process_reaped
    _assert_no_worker_children()


@pytest.mark.parametrize("phase", (SolvePhase.symbolic, SolvePhase.numeric))
def test_hung_solve_after_ready_times_out_under_the_original_budget(
    phase: SolvePhase,
) -> None:
    plan = _trivial_plan()
    limit_s = 0.4
    started = time.monotonic()
    run = _run_handshaked_worker(
        target=_hang_after_start_worker,
        validated=plan,
        backend=plan.primary_backend,
        phase=phase,
        limit_s=limit_s,
        failure_payload_factory=solver_isolation._closed_failure_payload,
    )
    wall = time.monotonic() - started
    grace = plan.budget.timeout_termination_grace_s
    assert run.status is IsolationStatus.timeout
    assert run.payload is None
    assert run.phase is phase
    assert limit_s <= run.elapsed_s <= limit_s + grace
    assert run.startup_elapsed_s > 0.0
    # Wall time may include startup, but the accounted solve window may not.
    assert wall >= run.elapsed_s
    assert run.process_reaped
    _assert_no_worker_children()


def test_parent_cancellation_terminates_the_child(monkeypatch) -> None:
    plan = _trivial_plan()

    def _cancelled(receiver, limit_s):
        raise RuntimeError("parent cancelled")

    monkeypatch.setattr(solver_isolation, "_receive_handshake_message", _cancelled)
    with pytest.raises(RuntimeError, match="parent cancelled"):
        run_isolated_backend(plan, plan.primary_backend)
    _assert_no_worker_children()


def test_repeated_solves_are_deterministic_and_leak_no_processes() -> None:
    plan = _trivial_plan()
    payloads = []
    for _ in range(3):
        run = run_isolated_backend(plan, plan.primary_backend)
        assert run.status is IsolationStatus.completed
        assert run.handshake_failure is None
        assert run.payload is not None and run.payload["status"] == "success"
        assert run.process_reaped
        payloads.append(run.payload)
        _assert_no_worker_children()
    assert payloads[0] == payloads[1] == payloads[2]


def test_audit_worker_shares_the_same_bounded_startup_protocol(monkeypatch) -> None:
    plan = _trivial_plan()
    baseline = run_isolated_completeness_audit(plan, plan.primary_backend)
    assert baseline.status is IsolationStatus.completed
    assert baseline.handshake_failure is None
    _assert_no_worker_children()

    monkeypatch.setattr(solver_isolation, "WORKER_STARTUP_TIME_LIMIT_S", 1.0e-9)
    run = run_isolated_completeness_audit(plan, plan.primary_backend)
    assert run.status is IsolationStatus.completed
    assert run.handshake_failure == "startup_timeout"
    assert run.payload == {"status": "backend_failure"}
    assert run.elapsed_s == 0.0
    assert run.process_reaped
    _assert_no_worker_children()
