"""Spawn-isolated execution with hard plan-budget termination.

Worker lifecycle uses a bounded two-phase protocol so process startup can
never spend solve budget:

``startup phase`` — the parent spawns the worker, the child imports its
backends, revalidates the plan and backend, and reports a structured READY
message on the result pipe.  The parent waits at most
``WORKER_STARTUP_TIME_LIMIT_S`` and fails closed on timeout, crash, or any
message that is not the exact expected READY.

``solve phase`` — only after validating READY does the parent send the START
message and start the existing phase-budget clock.  The solve-phase symbolic,
numeric, and verification limits are unchanged, and a worker that is slow
*after* START still times out against the original budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import multiprocessing
from multiprocessing.connection import Connection
import time
from typing import Any, Callable

from ._audit import audit_solve_plan
from .backends import WorkerStatus, run_backend
from .contracts import (
    SolveBackendKind,
    SolvePhase,
    SolvePlan,
    solver_phase_limit_s,
)


# The worker schema permits 1024 roots, each with 256 logical values, and each
# value can be a 16-component vector.  Identifiers are restricted to 64 ASCII
# bytes and a finite binary64 JSON representation is at most 24 bytes.  The
# fixed JSON spellings below include braces, keys and the maximum multiplicity;
# 16 KiB then bounds the fixed response envelope and certificate (whose strings
# and integers are all independently bounded by their closed schema).
_MAX_ROOTS = 1024
_MAX_VALUES_PER_ROOT = 256
_MAX_VECTOR_COMPONENTS = 16
_MAX_IDENTIFIER_JSON_BYTES = 64
_MAX_FINITE_FLOAT_JSON_BYTES = 24
_MAX_VALUE_JSON_BYTES = (
    len(b'{"symbol_id":"","value_si":[]}')
    + _MAX_IDENTIFIER_JSON_BYTES
    + _MAX_VECTOR_COMPONENTS * _MAX_FINITE_FLOAT_JSON_BYTES
    + (_MAX_VECTOR_COMPONENTS - 1)
)
_MAX_ROOT_JSON_BYTES = (
    len(b'{"root_multiplicity":1024,"values":[]}')
    + _MAX_VALUES_PER_ROOT * _MAX_VALUE_JSON_BYTES
    + (_MAX_VALUES_PER_ROOT - 1)
)
_MAX_CERTIFICATE_AND_ENVELOPE_JSON_BYTES = 16 * 1024
_MAX_SCHEMA_RESPONSE_BYTES = (
    _MAX_CERTIFICATE_AND_ENVELOPE_JSON_BYTES
    + _MAX_ROOTS * _MAX_ROOT_JSON_BYTES
    + (_MAX_ROOTS - 1)
)
_MIB = 1024 * 1024
MAX_WORKER_RESPONSE_BYTES = (
    (_MAX_SCHEMA_RESPONSE_BYTES + _MIB - 1) // _MIB
) * _MIB
_MAX_JSON_SCALAR_TEXT_CHARS = 256
_MAX_JSON_INTEGER_MAGNITUDE = 10_000_000
_MAX_JSON_CONTAINER_ITEMS = 1024
_MAX_JSON_STRUCTURE_DEPTH = 16
_MAX_JSON_STRUCTURE_VISITS = (
    64
    + _MAX_ROOTS
    * (4 + _MAX_VALUES_PER_ROOT * (4 + _MAX_VECTOR_COMPONENTS))
)
_CLOSED_FAILURE_BYTES = (
    b'{"approximate":false,"certificate":null,"complete":false,'
    b'"overflow":false,"roots":[],"status":"backend_failure"}'
)

# Bounded startup allowance for the two-phase worker protocol.  Measured on the
# four-core reference host: spawn + interpreter boot + numpy/scipy/sympy import
# + child-side plan revalidation took 1.8-1.9 s unloaded, 2.4-2.9 s under 4x
# CPU load, and 4-5 s under 8x oversubscription.  The ceiling below bounds the
# same work against CI cold caches and scheduler tail while remaining a hard
# fail-closed limit.  It is infrastructure allowance only: no solve-phase
# budget is extended by it, and a worker that never reports READY inside it is
# terminated and reported as a closed failure, never as a solve result.
WORKER_STARTUP_TIME_LIMIT_S = 20.0

_WORKER_HANDSHAKE_PROTOCOL = "phase56-stage7-solver-worker-handshake-v1"
_WORKER_READY_KIND = "worker_ready"
_WORKER_START_KIND = "worker_start"
_MAX_HANDSHAKE_MESSAGE_BYTES = 4096

# Closed vocabulary for handshake-level failures recorded on the run.
WORKER_HANDSHAKE_FAILURES = (
    "startup_timeout",
    "startup_crash",
    "startup_protocol_violation",
    "start_dispatch_failure",
    "duplicate_handshake_reply",
)


class IsolationStatus(str, Enum):
    completed = "completed"
    timeout = "timeout"


@dataclass(frozen=True)
class IsolatedBackendRun:
    status: IsolationStatus
    payload: dict[str, Any] | None
    elapsed_s: float
    phase: SolvePhase
    backend: SolveBackendKind
    process_reaped: bool
    startup_elapsed_s: float = 0.0
    handshake_failure: str | None = None


def phase_for_backend(backend: SolveBackendKind) -> SolvePhase:
    if backend in {
        SolveBackendKind.numeric_root,
        SolveBackendKind.ode_ivp,
        SolveBackendKind.event_root,
        SolveBackendKind.constrained_optimization,
    }:
        return SolvePhase.numeric
    return SolvePhase.symbolic


def _closed_failure_payload() -> dict[str, Any]:
    return {
        "status": WorkerStatus.backend_failure.value,
        "complete": False,
        "approximate": False,
        "roots": [],
        "overflow": False,
        "certificate": None,
    }


def _audit_failure_payload() -> dict[str, Any]:
    return {"status": WorkerStatus.backend_failure.value}


def _encode_worker_payload(payload: dict[str, Any]) -> bytes:
    """Encode one bounded JSON object without materializing an over-cap body."""

    if type(payload) is not dict or not _bounded_json_structure(payload):
        return _CLOSED_FAILURE_BYTES
    encoder = json.JSONEncoder(
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    encoded = bytearray()
    try:
        for chunk in encoder.iterencode(payload):
            # ensure_ascii=True makes character and encoded-byte counts equal.
            # Check the remaining budget before creating the chunk's bytes.
            if len(chunk) > MAX_WORKER_RESPONSE_BYTES - len(encoded):
                return _CLOSED_FAILURE_BYTES
            encoded.extend(chunk.encode("ascii", errors="strict"))
    except Exception:
        return _CLOSED_FAILURE_BYTES
    return bytes(encoded) if encoded else _CLOSED_FAILURE_BYTES


def _bounded_json_structure(payload: dict[str, Any]) -> bool:
    """Reject oversized scalar/container shapes before JSON escaping begins."""

    stack: list[tuple[Any, int, bool]] = [(payload, 0, False)]
    active_containers: set[int] = set()
    visits = 0
    while stack:
        value, depth, exiting = stack.pop()
        if exiting:
            active_containers.discard(id(value))
            continue
        visits += 1
        if visits > _MAX_JSON_STRUCTURE_VISITS or depth > _MAX_JSON_STRUCTURE_DEPTH:
            return False
        if value is None or type(value) is bool:
            continue
        if type(value) is int:
            if abs(value) > _MAX_JSON_INTEGER_MAGNITUDE:
                return False
            continue
        if type(value) is float:
            if not math.isfinite(value) or abs(value) > 1.0e300:
                return False
            continue
        if type(value) is str:
            if len(value) > _MAX_JSON_SCALAR_TEXT_CHARS:
                return False
            continue
        if type(value) in {list, tuple}:
            if len(value) > _MAX_JSON_CONTAINER_ITEMS:
                return False
            identity = id(value)
            if identity in active_containers:
                return False
            active_containers.add(identity)
            stack.append((value, depth, True))
            stack.extend(
                (item, depth + 1, False)
                for item in reversed(value)
            )
            continue
        if type(value) is dict:
            if len(value) > _MAX_JSON_CONTAINER_ITEMS:
                return False
            identity = id(value)
            if identity in active_containers:
                return False
            active_containers.add(identity)
            stack.append((value, depth, True))
            for key, item in value.items():
                if type(key) is not str or len(key) > _MAX_JSON_SCALAR_TEXT_CHARS:
                    return False
            stack.extend(
                (item, depth + 1, False)
                for item in reversed(tuple(value.values()))
            )
            continue
        return False
    return True


def _decode_worker_payload(encoded: bytes) -> dict[str, Any]:
    if type(encoded) is not bytes or not encoded or len(encoded) > MAX_WORKER_RESPONSE_BYTES:
        return _closed_failure_payload()

    def reject_constant(_: str) -> None:
        raise ValueError

    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        decoded = json.loads(
            encoded.decode("utf-8", errors="strict"),
            object_pairs_hook=closed_object,
            parse_constant=reject_constant,
        )
    except Exception:
        return _closed_failure_payload()
    return decoded if isinstance(decoded, dict) else _closed_failure_payload()


def _plan_digest(plan_json: str) -> str:
    return hashlib.sha256(plan_json.encode("utf-8")).hexdigest()


def _ready_message(plan_digest: str, backend_value: str) -> dict[str, Any]:
    """Exact READY shape; carries protocol identity only, never case metadata."""

    return {
        "kind": _WORKER_READY_KIND,
        "protocol": _WORKER_HANDSHAKE_PROTOCOL,
        "backend": backend_value,
        "plan_sha256": plan_digest,
    }


def _start_message(plan_digest: str) -> dict[str, Any]:
    return {
        "kind": _WORKER_START_KIND,
        "protocol": _WORKER_HANDSHAKE_PROTOCOL,
        "plan_sha256": plan_digest,
    }


def _is_handshake_shaped(payload: dict[str, Any]) -> bool:
    return (
        payload.get("kind") in {_WORKER_READY_KIND, _WORKER_START_KIND}
        or "protocol" in payload
    )


def _receive_handshake_message(
    receiver: Connection,
    limit_s: float,
) -> tuple[str, dict[str, Any] | None]:
    """Bounded wait for one framed handshake message.

    Returns ``("message", payload)`` on a decoded message, ``("timeout", None)``
    when nothing arrived inside the bound, and ``("closed", None)`` on EOF or a
    broken/oversized frame.  The decode never raises; malformed bytes surface
    as a payload that cannot equal any expected handshake message.
    """

    try:
        if limit_s > 0.0 and receiver.poll(limit_s):
            encoded = receiver.recv_bytes(maxlength=_MAX_HANDSHAKE_MESSAGE_BYTES)
        elif receiver.poll(0.0):
            encoded = receiver.recv_bytes(maxlength=_MAX_HANDSHAKE_MESSAGE_BYTES)
        else:
            return ("timeout", None)
    except (EOFError, OSError):
        return ("closed", None)
    return ("message", _decode_worker_payload(encoded))


def _await_worker_start(start_receiver: Connection, plan_digest: str) -> bool:
    """Child-side bounded wait for the exact START message; never unbounded."""

    status, payload = _receive_handshake_message(
        start_receiver, WORKER_STARTUP_TIME_LIMIT_S
    )
    return status == "message" and payload == _start_message(plan_digest)


def _handshaked_worker(
    sender: Connection,
    start_receiver: Connection,
    plan_json: str,
    backend_value: str,
    execute: Callable[[SolvePlan, SolveBackendKind], dict[str, Any]],
    failure_payload: Callable[[], dict[str, Any]],
) -> None:
    """Child body: validate before READY, solve only after START."""

    try:
        try:
            plan = SolvePlan.model_validate_json(plan_json)
            backend = SolveBackendKind(backend_value)
        except Exception:
            # Invalid plan or unsupported backend: refuse to become READY.
            sender.send_bytes(_encode_worker_payload(failure_payload()))
            return
        digest = _plan_digest(plan_json)
        sender.send_bytes(
            _encode_worker_payload(_ready_message(digest, backend.value))
        )
        if not _await_worker_start(start_receiver, digest):
            return
        try:
            payload = execute(plan, backend)
        except Exception:
            payload = failure_payload()
        sender.send_bytes(_encode_worker_payload(payload))
    except Exception:
        pass
    finally:
        for connection in (start_receiver, sender):
            try:
                connection.close()
            except Exception:
                pass


def _worker_main(
    sender: Connection,
    start_receiver: Connection,
    plan_json: str,
    backend_value: str,
) -> None:
    _handshaked_worker(
        sender,
        start_receiver,
        plan_json,
        backend_value,
        run_backend,
        _closed_failure_payload,
    )


def _audit_worker_main(
    sender: Connection,
    start_receiver: Connection,
    plan_json: str,
    backend_value: str,
) -> None:
    _handshaked_worker(
        sender,
        start_receiver,
        plan_json,
        backend_value,
        audit_solve_plan,
        _audit_failure_payload,
    )


def _reap_process(
    process: multiprocessing.Process,
    grace_s: float,
) -> None:
    process.join(grace_s)
    if process.is_alive():
        process.terminate()
        process.join(grace_s)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(grace_s)


def _terminate_process(
    process: multiprocessing.Process,
    grace_s: float,
) -> None:
    if process.is_alive():
        process.terminate()
    process.join(grace_s)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(grace_s)


def _run_handshaked_worker(
    *,
    target: Callable[..., None],
    validated: SolvePlan,
    backend: SolveBackendKind,
    phase: SolvePhase,
    limit_s: float,
    failure_payload_factory: Callable[[], dict[str, Any]],
) -> IsolatedBackendRun:
    """Spawn one worker, run the two-phase protocol, and always reap it."""

    grace = validated.budget.timeout_termination_grace_s
    plan_json = validated.model_dump_json()
    digest = _plan_digest(plan_json)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    start_receiver, start_sender = context.Pipe(duplex=False)
    process = context.Process(
        target=target,
        args=(sender, start_receiver, plan_json, backend.value),
        daemon=False,
    )
    try:
        process.start()
    except Exception:
        for connection in (sender, receiver, start_receiver, start_sender):
            try:
                connection.close()
            except Exception:
                pass
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload=failure_payload_factory(),
            elapsed_s=0.0,
            phase=phase,
            backend=backend,
            process_reaped=True,
        )
    sender.close()
    start_receiver.close()
    reaped = False
    try:
        startup_started = time.monotonic()
        message_status, message = _receive_handshake_message(
            receiver, WORKER_STARTUP_TIME_LIMIT_S
        )
        startup_elapsed = max(0.0, time.monotonic() - startup_started)
        if message_status != "message" or message != _ready_message(
            digest, backend.value
        ):
            if message_status == "timeout":
                failure = "startup_timeout"
            elif message_status == "closed":
                failure = "startup_crash"
            else:
                failure = "startup_protocol_violation"
            _terminate_process(process, grace)
            reaped = True
            return IsolatedBackendRun(
                status=IsolationStatus.completed,
                payload=failure_payload_factory(),
                elapsed_s=0.0,
                phase=phase,
                backend=backend,
                process_reaped=not process.is_alive(),
                startup_elapsed_s=startup_elapsed,
                handshake_failure=failure,
            )
        try:
            start_sender.send_bytes(_encode_worker_payload(_start_message(digest)))
        except Exception:
            _terminate_process(process, grace)
            reaped = True
            return IsolatedBackendRun(
                status=IsolationStatus.completed,
                payload=failure_payload_factory(),
                elapsed_s=0.0,
                phase=phase,
                backend=backend,
                process_reaped=not process.is_alive(),
                startup_elapsed_s=startup_elapsed,
                handshake_failure="start_dispatch_failure",
            )

        # The solve-phase clock starts only now: startup can no longer spend
        # any of the unchanged symbolic/numeric/verification budgets.
        started = time.monotonic()
        encoded: bytes | None = None
        remaining = max(0.0, limit_s - (time.monotonic() - started))
        try:
            if remaining > 0.0 and receiver.poll(remaining):
                encoded = receiver.recv_bytes(maxlength=MAX_WORKER_RESPONSE_BYTES)
            elif receiver.poll(0.0):
                encoded = receiver.recv_bytes(maxlength=MAX_WORKER_RESPONSE_BYTES)
        except (EOFError, OSError):
            encoded = None

        if encoded is not None:
            _reap_process(process, grace)
            reaped = True
            elapsed = min(time.monotonic() - started, limit_s)
            payload = _decode_worker_payload(encoded)
            handshake_failure = None
            if _is_handshake_shaped(payload):
                # A second handshake message is never a solve result.
                payload = failure_payload_factory()
                handshake_failure = "duplicate_handshake_reply"
            return IsolatedBackendRun(
                status=IsolationStatus.completed,
                payload=payload,
                elapsed_s=max(0.0, elapsed),
                phase=phase,
                backend=backend,
                process_reaped=not process.is_alive(),
                startup_elapsed_s=startup_elapsed,
                handshake_failure=handshake_failure,
            )

        elapsed_before_reap = time.monotonic() - started
        ended_before_limit = (
            not process.is_alive() and elapsed_before_reap < limit_s
        )
        _terminate_process(process, grace)
        reaped = True
        if ended_before_limit:
            return IsolatedBackendRun(
                status=IsolationStatus.completed,
                payload=failure_payload_factory(),
                elapsed_s=max(0.0, min(elapsed_before_reap, limit_s)),
                phase=phase,
                backend=backend,
                process_reaped=not process.is_alive(),
                startup_elapsed_s=startup_elapsed,
            )
        elapsed = max(limit_s, time.monotonic() - started)
        elapsed = min(elapsed, limit_s + grace)
        return IsolatedBackendRun(
            status=IsolationStatus.timeout,
            payload=None,
            elapsed_s=elapsed,
            phase=phase,
            backend=backend,
            process_reaped=not process.is_alive(),
            startup_elapsed_s=startup_elapsed,
        )
    finally:
        if not reaped:
            # Parent cancellation or an unexpected error: the child never
            # outlives this call.
            _terminate_process(process, grace)
        for connection in (receiver, start_sender):
            try:
                connection.close()
            except Exception:
                pass


def run_isolated_backend(
    plan: SolvePlan,
    backend: SolveBackendKind,
) -> IsolatedBackendRun:
    """Execute one backend in a fresh spawned process and always reap it."""

    # Revalidation before process creation prevents mutable or forged model state
    # from reaching the worker boundary.
    validated = SolvePlan.model_validate_json(plan.model_dump_json())
    if backend not in {validated.primary_backend, validated.permitted_numeric_fallback}:
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload={
                "status": WorkerStatus.unsupported.value,
                "complete": False,
                "approximate": False,
                "roots": [],
                "overflow": False,
                "certificate": None,
            },
            elapsed_s=0.0,
            phase=phase_for_backend(backend),
            backend=backend,
            process_reaped=True,
        )
    phase = phase_for_backend(backend)
    limit_s = solver_phase_limit_s(phase, backend, validated.budget)
    return _run_handshaked_worker(
        target=_worker_main,
        validated=validated,
        backend=backend,
        phase=phase,
        limit_s=limit_s,
        failure_payload_factory=_closed_failure_payload,
    )


def run_isolated_completeness_audit(
    plan: SolvePlan,
    backend: SolveBackendKind,
) -> IsolatedBackendRun:
    """Audit symbolic completeness in a separate verification-budget process."""

    validated = SolvePlan.model_validate_json(plan.model_dump_json())
    phase = SolvePhase.verification
    if backend is not validated.primary_backend or backend not in {
        SolveBackendKind.linear_symbolic,
        SolveBackendKind.polynomial_symbolic,
    }:
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload={"status": WorkerStatus.unsupported.value},
            elapsed_s=0.0,
            phase=phase,
            backend=backend,
            process_reaped=True,
        )
    limit_s = solver_phase_limit_s(phase, backend, validated.budget)
    return _run_handshaked_worker(
        target=_audit_worker_main,
        validated=validated,
        backend=backend,
        phase=phase,
        limit_s=limit_s,
        failure_payload_factory=_audit_failure_payload,
    )


__all__ = [
    "MAX_WORKER_RESPONSE_BYTES",
    "WORKER_HANDSHAKE_FAILURES",
    "WORKER_STARTUP_TIME_LIMIT_S",
    "IsolatedBackendRun",
    "IsolationStatus",
    "phase_for_backend",
    "run_isolated_backend",
    "run_isolated_completeness_audit",
]
