"""Spawn-isolated execution with hard plan-budget termination."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
import multiprocessing
from multiprocessing.connection import Connection
import time
from typing import Any

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


def _worker_main(
    sender: Connection,
    plan_json: str,
    backend_value: str,
) -> None:
    try:
        plan = SolvePlan.model_validate_json(plan_json)
        backend = SolveBackendKind(backend_value)
        payload = run_backend(plan, backend)
    except Exception:
        payload = _closed_failure_payload()
    encoded = _encode_worker_payload(payload)
    try:
        sender.send_bytes(encoded)
    except Exception:
        pass
    finally:
        sender.close()


def _audit_worker_main(
    sender: Connection,
    plan_json: str,
    backend_value: str,
) -> None:
    try:
        plan = SolvePlan.model_validate_json(plan_json)
        backend = SolveBackendKind(backend_value)
        payload = audit_solve_plan(plan, backend)
    except Exception:
        payload = {"status": WorkerStatus.backend_failure.value}
    encoded = _encode_worker_payload(payload)
    try:
        sender.send_bytes(encoded)
    except Exception:
        pass
    finally:
        sender.close()


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
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker_main,
        args=(sender, validated.model_dump_json(), backend.value),
        daemon=False,
    )
    started = time.monotonic()
    try:
        process.start()
    except Exception:
        sender.close()
        receiver.close()
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload=_closed_failure_payload(),
            elapsed_s=0.0,
            phase=phase,
            backend=backend,
            process_reaped=True,
        )
    sender.close()
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
        _reap_process(process, validated.budget.timeout_termination_grace_s)
        elapsed = min(time.monotonic() - started, limit_s)
        payload = _decode_worker_payload(encoded)
        receiver.close()
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload=payload,
            elapsed_s=max(0.0, elapsed),
            phase=phase,
            backend=backend,
            process_reaped=not process.is_alive(),
        )

    elapsed_before_reap = time.monotonic() - started
    ended_before_limit = not process.is_alive() and elapsed_before_reap < limit_s
    _terminate_process(process, validated.budget.timeout_termination_grace_s)
    receiver.close()
    if ended_before_limit:
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload=_closed_failure_payload(),
            elapsed_s=max(0.0, min(elapsed_before_reap, limit_s)),
            phase=phase,
            backend=backend,
            process_reaped=not process.is_alive(),
        )
    elapsed = max(limit_s, time.monotonic() - started)
    elapsed = min(
        elapsed,
        limit_s + validated.budget.timeout_termination_grace_s,
    )
    return IsolatedBackendRun(
        status=IsolationStatus.timeout,
        payload=None,
        elapsed_s=elapsed,
        phase=phase,
        backend=backend,
        process_reaped=not process.is_alive(),
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
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_audit_worker_main,
        args=(sender, validated.model_dump_json(), backend.value),
        daemon=False,
    )
    started = time.monotonic()
    try:
        process.start()
    except Exception:
        sender.close()
        receiver.close()
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload={"status": WorkerStatus.backend_failure.value},
            elapsed_s=0.0,
            phase=phase,
            backend=backend,
            process_reaped=True,
        )
    sender.close()
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
        _reap_process(process, validated.budget.timeout_termination_grace_s)
        elapsed = min(time.monotonic() - started, limit_s)
        payload = _decode_worker_payload(encoded)
        receiver.close()
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload=payload,
            elapsed_s=max(0.0, elapsed),
            phase=phase,
            backend=backend,
            process_reaped=not process.is_alive(),
        )

    elapsed_before_reap = time.monotonic() - started
    ended_before_limit = not process.is_alive() and elapsed_before_reap < limit_s
    _terminate_process(process, validated.budget.timeout_termination_grace_s)
    receiver.close()
    if ended_before_limit:
        return IsolatedBackendRun(
            status=IsolationStatus.completed,
            payload={"status": WorkerStatus.backend_failure.value},
            elapsed_s=max(0.0, min(elapsed_before_reap, limit_s)),
            phase=phase,
            backend=backend,
            process_reaped=not process.is_alive(),
        )
    elapsed = max(limit_s, time.monotonic() - started)
    elapsed = min(
        elapsed,
        limit_s + validated.budget.timeout_termination_grace_s,
    )
    return IsolatedBackendRun(
        status=IsolationStatus.timeout,
        payload=None,
        elapsed_s=elapsed,
        phase=phase,
        backend=backend,
        process_reaped=not process.is_alive(),
    )


__all__ = [
    "MAX_WORKER_RESPONSE_BYTES",
    "IsolatedBackendRun",
    "IsolationStatus",
    "phase_for_backend",
    "run_isolated_backend",
    "run_isolated_completeness_audit",
]
