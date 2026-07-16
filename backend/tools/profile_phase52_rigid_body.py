"""Exact-ref, privacy-safe diagnostic profiler for the Phase 52 rigid-body gate.

This tool intentionally produces a *volatile diagnostic artifact*.  Its timings
are never part of the deterministic Phase 52 JSON/Markdown report and never
replace the balanced Release performance gate.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import pstats
import re
import subprocess
import sys
import sysconfig
import time
from typing import Any


SCHEMA_VERSION = 1
ARTIFACT_KIND = "volatile_diagnostic_profile"
CASE_VERSION = 1
EXPECTED_ROUNDS = 4
EXPECTED_WARMUPS = 200
EXPECTED_REPEATS = 500
TOP_CUMULATIVE_LIMIT = 40
REVISION_LABELS = ("base", "head")
CASE_IDS = ("rigid_body", "projectile")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

PROJECTILE = (
    "지면에서 초속도 20m/s, 발사각 60도로 발사해 "
    "같은 높이에 착지한다. 사거리는?"
)
RIGID_BODY = (
    "평면강체에서 A점은 고정되어 있고 rBA=(1,0)m이다. "
    "omega=2rad/s이며 반시계방향이다. B점 속도를 구하라."
)
CASE_INPUTS = {"rigid_body": RIGID_BODY, "projectile": PROJECTILE}


class ProfileDataError(ValueError):
    """Raised when evidence is incomplete, malformed, or not exact-ref."""


TARGET_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "target_id": "base_solver.solve_candidates",
        "module": "engine.solvers.base",
        "qualname": "BaseSolver.solve_candidates",
    },
    {
        "target_id": "validators.candidate_from_solver_result",
        "module": "engine.physics_core.validators",
        "qualname": "candidate_from_solver_result",
    },
    {
        "target_id": "validators.validate_and_select",
        "module": "engine.physics_core.validators",
        "qualname": "validate_and_select",
    },
    {
        "target_id": "validators.validate_output_candidates",
        "module": "engine.physics_core.validators",
        "qualname": "validate_output_candidates",
    },
    {
        "target_id": "services.selection_decision_model",
        "module": "engine.services",
        "qualname": "_selection_decision_model",
    },
    {
        "target_id": "services.verification_report_model",
        "module": "engine.services",
        "qualname": "_verification_report_model",
    },
    {
        "target_id": "verification.verify_result",
        "module": "engine.verification.suite",
        "qualname": "verify_result",
    },
    {
        "target_id": "invariants.governing_equation_residual",
        "module": "engine.verification.invariants",
        "qualname": "governing_equation_residual",
    },
    {
        "target_id": "invariants.rigid_relative_velocity",
        "module": "engine.verification.invariants",
        "qualname": "rigid_relative_velocity",
    },
    {
        "target_id": "trace.noop_getattr",
        "module": "engine.services",
        "qualname": "_NoopSolveTraceHooks.__getattr__",
    },
    {
        "target_id": "trace.noop_ignore",
        "module": "engine.services",
        "qualname": "_NoopSolveTraceHooks._ignore",
    },
)

TARGET_IDS = tuple(item["target_id"] for item in TARGET_MANIFEST)
HEAD_REQUIRED_TARGETS = frozenset(TARGET_IDS)

# Attribution uses disjoint self-time frontiers.  Parent cumulative times are
# retained as diagnostics but are deliberately excluded from these sums.
CANDIDATE_FRONTIERS: dict[str, tuple[str, ...]] = {
    "candidate_validation_chain": (
        "base_solver.solve_candidates",
        "validators.candidate_from_solver_result",
        "validators.validate_and_select",
        "validators.validate_output_candidates",
        "services.selection_decision_model",
    ),
    "duplicate_rigid_invariants": (
        "invariants.governing_equation_residual",
        "invariants.rigid_relative_velocity",
    ),
    "default_trace_hooks": (
        "trace.noop_getattr",
        "trace.noop_ignore",
    ),
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ProfileDataError(f"{field} must be a lowercase 40-character SHA")
    return value


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ProfileDataError(f"{field} must be an integer >= {minimum}")
    return value


def _require_number(value: Any, field: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileDataError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ProfileDataError(f"{field} must be finite and >= {minimum}")
    return number


def _require_exact_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ProfileDataError(f"{field} keys do not match the diagnostic schema")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ProfileDataError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ProfileDataError(f"non-finite JSON constant: {value}")


def _load_json_strict(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileDataError(f"invalid diagnostic JSON: {path.name}") from exc


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _git_head(backend_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(backend_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProfileDataError("cannot verify backend-root Git HEAD") from exc
    return _require_sha(completed.stdout.strip().lower(), "backend_root_head")


def _under_root(path: Path, root: Path) -> Path:
    try:
        return path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ProfileDataError("resolved code origin is outside backend-root") from exc


def _prepare_engine_imports(backend_root: Path) -> None:
    preloaded = sorted(
        name for name in sys.modules if name == "engine" or name.startswith("engine.")
    )
    if preloaded:
        raise ProfileDataError("engine modules were loaded before backend-root isolation")
    cleaned: list[str] = []
    root = backend_root.resolve(strict=True)
    for entry in sys.path:
        try:
            candidate = Path(entry or os.getcwd()).resolve(strict=True)
        except OSError:
            cleaned.append(entry)
            continue
        if candidate != root and (candidate / "engine").exists():
            continue
        if candidate == root:
            continue
        cleaned.append(entry)
    sys.path[:] = [str(root), *cleaned]


def _validate_loaded_engine_modules(backend_root: Path) -> None:
    for name, module in sorted(sys.modules.items()):
        if module is None or not (name == "engine" or name.startswith("engine.")):
            continue
        module_file = getattr(module, "__file__", None)
        if module_file:
            _under_root(Path(module_file), backend_root)
            continue
        module_paths = list(getattr(module, "__path__", []) or [])
        if not module_paths:
            raise ProfileDataError(f"loaded engine module has no origin: {name}")
        for module_path in module_paths:
            _under_root(Path(module_path), backend_root)


def _resolve_qualname(module: Any, qualname: str) -> Any:
    value = module
    for component in qualname.split("."):
        if not hasattr(value, component):
            raise AttributeError(component)
        value = getattr(value, component)
    return value


def _module_is_really_absent(module_name: str, exc: ModuleNotFoundError) -> bool:
    missing = exc.name or ""
    return missing == module_name or module_name.startswith(missing + ".")


def _resolve_targets(backend_root: Path, revision_label: str) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    module_cache: dict[str, Any | None] = {}
    for spec in TARGET_MANIFEST:
        module_name = spec["module"]
        if module_name not in module_cache:
            try:
                module_cache[module_name] = importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                if not _module_is_really_absent(module_name, exc):
                    raise
                module_cache[module_name] = None
        module = module_cache[module_name]
        if module is None:
            item = {**spec, "availability": "absent", "stats_key": None}
            resolved.append(item)
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise ProfileDataError(f"target module has no file origin: {module_name}")
        _under_root(Path(module_file), backend_root)
        try:
            target = _resolve_qualname(module, spec["qualname"])
        except AttributeError:
            item = {**spec, "availability": "absent", "stats_key": None}
            resolved.append(item)
            continue
        code = getattr(target, "__code__", None)
        if code is None and inspect.ismethod(target):
            code = getattr(target.__func__, "__code__", None)
        if code is None:
            raise ProfileDataError(f"target is not a Python function: {spec['target_id']}")
        relative = _under_root(Path(code.co_filename), backend_root).as_posix()
        item = {
            **spec,
            "availability": "present_not_called",
            "repo_relative_filename": relative,
            "first_line": code.co_firstlineno,
            "code_name": code.co_name,
            "stats_key": (code.co_filename, code.co_firstlineno, code.co_name),
        }
        resolved.append(item)

    if revision_label == "head":
        missing = sorted(
            item["target_id"]
            for item in resolved
            if item["target_id"] in HEAD_REQUIRED_TARGETS
            and item["availability"] == "absent"
        )
        if missing:
            raise ProfileDataError("required head targets are absent: " + ", ".join(missing))
    return resolved


def _model_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _semantic_fingerprint(response: Any) -> tuple[str, tuple[str, ...]]:
    verification = _model_value(response, "verification")
    structured = _model_value(verification, "structured_checks", []) or []
    checks = []
    for check in structured:
        checks.append(
            {
                "check_id": _model_value(check, "check_id"),
                "category": _model_value(check, "category"),
                "status": _model_value(check, "status"),
                "applicability": _model_value(check, "applicability"),
                "absolute_error": _model_value(check, "absolute_error"),
                "relative_error": _model_value(check, "relative_error"),
                "tolerance": _model_value(check, "tolerance"),
                "source_equation_ids": list(
                    _model_value(check, "source_equation_ids", []) or []
                ),
            }
        )
    answers = []
    for answer in _model_value(response, "answers", []) or []:
        answers.append(
            {
                "numeric": _model_value(answer, "numeric"),
                "unit": _model_value(answer, "unit"),
                "role": _model_value(answer, "role"),
                "output_key": _model_value(answer, "output_key"),
            }
        )
    diagnosis = _model_value(response, "diagnosis")
    route = _model_value(response, "route_decision")
    selection = _model_value(response, "selection_decision")
    selected_candidate = _model_value(selection, "selected_candidate")
    payload = {
        "ok": bool(_model_value(response, "ok", False)),
        "answers": answers,
        "verification": {
            "passed": bool(_model_value(verification, "passed", False)),
            "policy_version": _model_value(verification, "policy_version"),
            "structured_checks": checks,
        },
        "selected_solver": _model_value(diagnosis, "selected_solver"),
        "route": {
            "status": _model_value(route, "status"),
            "selected_solver_id": _model_value(route, "selected_solver_id"),
        },
        "selection": {
            "status": _model_value(selection, "status"),
            "selection_policy": _model_value(selection, "selection_policy"),
            "policy_version": _model_value(selection, "policy_version"),
            "selected_candidate_id": _model_value(selected_candidate, "candidate_id"),
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    check_ids = tuple(sorted({str(item["check_id"]) for item in checks}))
    return hashlib.sha256(encoded).hexdigest(), check_ids


def _checked_solve(solve_problem: Any, case_text: str) -> Any:
    try:
        response = solve_problem(case_text)
    except Exception as exc:
        raise ProfileDataError(
            f"profile workload raised exception type {type(exc).__name__}"
        ) from exc
    verification = _model_value(response, "verification")
    if not _model_value(response, "ok", False) or not _model_value(
        verification, "passed", False
    ):
        raise ProfileDataError("profile workload did not return a passing response")
    return response


def _target_evidence(
    resolved: list[dict[str, Any]],
    stats: pstats.Stats,
    repeats: int,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for target in resolved:
        base = {
            "target_id": target["target_id"],
            "module": target["module"],
            "qualname": target["qualname"],
        }
        if target["availability"] == "absent":
            evidence.append(
                {
                    **base,
                    "availability": "absent",
                    "repo_relative_filename": None,
                    "first_line": None,
                    "code_name": None,
                    "primitive_calls": 0,
                    "total_calls": 0,
                    "recursive": False,
                    "self_seconds": 0.0,
                    "cumulative_seconds": 0.0,
                    "self_ms_per_product_solve": 0.0,
                    "cumulative_ms_per_product_solve": 0.0,
                    "self_ms_per_target_call": 0.0,
                    "cumulative_ms_per_target_call": 0.0,
                }
            )
            continue
        raw = stats.stats.get(target["stats_key"])
        if raw is None or raw[1] == 0:
            primitive_calls = total_calls = 0
            self_seconds = cumulative_seconds = 0.0
            availability = "present_not_called"
        else:
            primitive_calls, total_calls, self_seconds, cumulative_seconds, _ = raw
            availability = "called"
        per_target = total_calls or 1
        evidence.append(
            {
                **base,
                "availability": availability,
                "repo_relative_filename": target["repo_relative_filename"],
                "first_line": target["first_line"],
                "code_name": target["code_name"],
                "primitive_calls": primitive_calls,
                "total_calls": total_calls,
                "recursive": total_calls != primitive_calls,
                "self_seconds": self_seconds,
                "cumulative_seconds": cumulative_seconds,
                "self_ms_per_product_solve": self_seconds * 1000.0 / repeats,
                "cumulative_ms_per_product_solve": cumulative_seconds
                * 1000.0
                / repeats,
                "self_ms_per_target_call": (
                    self_seconds * 1000.0 / per_target if total_calls else 0.0
                ),
                "cumulative_ms_per_target_call": (
                    cumulative_seconds * 1000.0 / per_target if total_calls else 0.0
                ),
            }
        )
    return evidence


def _stable_external_label(filename: str, backend_root: Path) -> tuple[str, str | None, str | None]:
    if filename == "~" or filename.startswith("<built-in"):
        return "builtin", None, "python_builtin"
    if filename.startswith("<frozen "):
        label = filename.removeprefix("<frozen ").removesuffix(">").replace("/", ".")
        return "stdlib", None, f"frozen.{label}"
    path = Path(filename)
    try:
        relative = path.resolve(strict=True).relative_to(backend_root.resolve(strict=True))
        return "repo", relative.as_posix(), None
    except (OSError, ValueError):
        pass
    parts = list(path.parts)
    lowered = [part.lower() for part in parts]
    for marker in ("site-packages", "dist-packages"):
        if marker in lowered:
            index = lowered.index(marker)
            package = parts[index + 1] if index + 1 < len(parts) else "python_dependency"
            package = package.split(".", 1)[0].replace("-", "_")
            return "dependency", None, package or "python_dependency"
    try:
        stdlib_root = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
        stdlib_relative = path.resolve(strict=True).relative_to(stdlib_root)
        label = stdlib_relative.with_suffix("").as_posix().replace("/", ".")
        return "stdlib", None, label or "python_stdlib"
    except (OSError, TypeError, ValueError):
        pass
    if path.name == "profile_phase52_rigid_body.py":
        return "dependency", None, "phase52_diagnostic_tool"
    basename = path.stem or "external_python_module"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", basename).strip("_")
    return "dependency", None, safe or "external_python_module"


def _top_cumulative_evidence(
    stats: pstats.Stats,
    backend_root: Path,
    repeats: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, raw in stats.stats.items():
        if not isinstance(key, tuple) or len(key) != 3:
            raise ProfileDataError("unexpected pstats function identity")
        filename, first_line, code_name = key
        primitive_calls, total_calls, self_seconds, cumulative_seconds, _ = raw
        origin_kind, relative_filename, module_label = _stable_external_label(
            str(filename), backend_root
        )
        rows.append(
            {
                "origin_kind": origin_kind,
                "filename": relative_filename,
                "module_label": module_label,
                "first_line": int(first_line),
                "code_name": str(code_name),
                "primitive_calls": int(primitive_calls),
                "total_calls": int(total_calls),
                "self_seconds": float(self_seconds),
                "cumulative_seconds": float(cumulative_seconds),
                "self_ms_per_product_solve": float(self_seconds) * 1000.0 / repeats,
                "cumulative_ms_per_product_solve": float(cumulative_seconds)
                * 1000.0
                / repeats,
            }
        )
    rows.sort(
        key=lambda item: (
            -item["cumulative_seconds"],
            item["origin_kind"],
            item["filename"] or item["module_label"] or "",
            item["first_line"],
            item["code_name"],
        )
    )
    return [
        {"rank": rank, **item}
        for rank, item in enumerate(rows[:TOP_CUMULATIVE_LIMIT], start=1)
    ]


def collect(args: argparse.Namespace) -> dict[str, Any]:
    backend_root = Path(args.backend_root).resolve(strict=True)
    if not backend_root.is_dir():
        raise ProfileDataError("backend-root must be a directory")
    revision_sha = _require_sha(args.revision_sha, "revision_sha")
    if _git_head(backend_root) != revision_sha:
        raise ProfileDataError("backend-root Git HEAD does not match revision_sha")
    if args.revision_label not in REVISION_LABELS:
        raise ProfileDataError("invalid revision label")
    if args.case_id not in CASE_IDS:
        raise ProfileDataError("invalid case ID")
    _require_int(args.round_number, "round_number", minimum=1)
    _require_int(args.position, "position", minimum=1)
    if args.round_number not in range(1, EXPECTED_ROUNDS + 1):
        raise ProfileDataError(f"round_number must be in 1..{EXPECTED_ROUNDS}")
    if args.position not in (1, 2):
        raise ProfileDataError("position must be 1 or 2")
    warmups = _require_int(args.warmups, "warmups", minimum=1)
    repeats = _require_int(args.repeats, "repeats", minimum=1)
    if warmups != EXPECTED_WARMUPS or repeats != EXPECTED_REPEATS:
        raise ProfileDataError(
            f"diagnostic sampling must be exactly {EXPECTED_WARMUPS}/{EXPECTED_REPEATS}"
        )

    _prepare_engine_imports(backend_root)
    resolved = _resolve_targets(backend_root, args.revision_label)
    services = importlib.import_module("engine.services")
    solve_problem = getattr(services, "solve_problem")
    solve_code = getattr(solve_problem, "__code__", None)
    if solve_code is None:
        raise ProfileDataError("solve_problem is not a Python function")
    _under_root(Path(solve_code.co_filename), backend_root)

    case_text = CASE_INPUTS[args.case_id]
    for _ in range(warmups):
        _checked_solve(solve_problem, case_text)
    _validate_loaded_engine_modules(backend_root)

    unprofiled_hashes: set[str] = set()
    unprofiled_total = 0.0
    for _ in range(repeats):
        unprofiled_start = time.perf_counter()
        response = _checked_solve(solve_problem, case_text)
        unprofiled_total += time.perf_counter() - unprofiled_start
        fingerprint, _ = _semantic_fingerprint(response)
        unprofiled_hashes.add(fingerprint)
    if len(unprofiled_hashes) != 1:
        raise ProfileDataError("unprofiled responses are not semantically stable")

    profiler = cProfile.Profile()
    measured_hashes: set[str] = set()
    check_ids_seen: set[tuple[str, ...]] = set()
    profiled_total = 0.0
    for _ in range(repeats):
        profiled_start = time.perf_counter()
        response = profiler.runcall(_checked_solve, solve_problem, case_text)
        profiled_total += time.perf_counter() - profiled_start
        fingerprint, check_ids = _semantic_fingerprint(response)
        measured_hashes.add(fingerprint)
        check_ids_seen.add(check_ids)
    if len(measured_hashes) != 1 or len(check_ids_seen) != 1:
        raise ProfileDataError("measured responses are not semantically stable")
    if measured_hashes != unprofiled_hashes:
        raise ProfileDataError("profiled and unprofiled response hashes differ")
    _validate_loaded_engine_modules(backend_root)

    stats = pstats.Stats(profiler)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": ARTIFACT_KIND,
        "deterministic_report_eligible": False,
        "metadata": {
            "revision_label": args.revision_label,
            "revision_sha": revision_sha,
            "round_number": args.round_number,
            "position": args.position,
        },
        "case": {
            "case_id": args.case_id,
            "case_version": CASE_VERSION,
            "input_sha256": _sha256_text(case_text),
        },
        "measurement": {
            "warmups": warmups,
            "repeats": repeats,
            "profiled_total_seconds": profiled_total,
            "profiled_ms_per_product_solve": profiled_total * 1000.0 / repeats,
            "unprofiled_total_seconds": unprofiled_total,
            "unprofiled_ms_per_product_solve": unprofiled_total
            * 1000.0
            / repeats,
            "response_sha256": next(iter(measured_hashes)),
            "check_ids": list(next(iter(check_ids_seen))),
        },
        "targets": _target_evidence(resolved, stats, repeats),
        "top_cumulative": _top_cumulative_evidence(stats, backend_root, repeats),
    }
    _validate_artifact(payload)
    _write_json_atomic(Path(args.out), payload)
    return payload


ARTIFACT_KEYS = {
    "schema_version",
    "artifact_kind",
    "deterministic_report_eligible",
    "metadata",
    "case",
    "measurement",
    "targets",
    "top_cumulative",
}
METADATA_KEYS = {"revision_label", "revision_sha", "round_number", "position"}
CASE_KEYS = {"case_id", "case_version", "input_sha256"}
MEASUREMENT_KEYS = {
    "warmups",
    "repeats",
    "profiled_total_seconds",
    "profiled_ms_per_product_solve",
    "unprofiled_total_seconds",
    "unprofiled_ms_per_product_solve",
    "response_sha256",
    "check_ids",
}
TARGET_KEYS = {
    "target_id",
    "module",
    "qualname",
    "availability",
    "repo_relative_filename",
    "first_line",
    "code_name",
    "primitive_calls",
    "total_calls",
    "recursive",
    "self_seconds",
    "cumulative_seconds",
    "self_ms_per_product_solve",
    "cumulative_ms_per_product_solve",
    "self_ms_per_target_call",
    "cumulative_ms_per_target_call",
}
TOP_CUMULATIVE_KEYS = {
    "rank",
    "origin_kind",
    "filename",
    "module_label",
    "first_line",
    "code_name",
    "primitive_calls",
    "total_calls",
    "self_seconds",
    "cumulative_seconds",
    "self_ms_per_product_solve",
    "cumulative_ms_per_product_solve",
}


def _validate_artifact(payload: Any) -> dict[str, Any]:
    value = _require_exact_keys(payload, ARTIFACT_KEYS, "artifact")
    if _require_int(value["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise ProfileDataError("unsupported diagnostic schema version")
    if value["artifact_kind"] != ARTIFACT_KIND:
        raise ProfileDataError("wrong diagnostic artifact kind")
    if value["deterministic_report_eligible"] is not False:
        raise ProfileDataError("diagnostic artifact must be excluded from deterministic reports")

    metadata = _require_exact_keys(value["metadata"], METADATA_KEYS, "metadata")
    if metadata["revision_label"] not in REVISION_LABELS:
        raise ProfileDataError("invalid revision label")
    _require_sha(metadata["revision_sha"], "metadata.revision_sha")
    _require_int(metadata["round_number"], "metadata.round_number", minimum=1)
    position = _require_int(metadata["position"], "metadata.position", minimum=1)
    if position not in (1, 2):
        raise ProfileDataError("metadata.position must be 1 or 2")

    case = _require_exact_keys(value["case"], CASE_KEYS, "case")
    if case["case_id"] not in CASE_IDS or (
        _require_int(case["case_version"], "case.case_version") != CASE_VERSION
    ):
        raise ProfileDataError("invalid diagnostic case contract")
    if case["input_sha256"] != _sha256_text(CASE_INPUTS[case["case_id"]]):
        raise ProfileDataError("case input fingerprint mismatch")

    measurement = _require_exact_keys(
        value["measurement"], MEASUREMENT_KEYS, "measurement"
    )
    warmups = _require_int(measurement["warmups"], "measurement.warmups", minimum=1)
    repeats = _require_int(measurement["repeats"], "measurement.repeats", minimum=1)
    if warmups != EXPECTED_WARMUPS or repeats != EXPECTED_REPEATS:
        raise ProfileDataError("diagnostic artifact has non-contracted sample counts")
    profiled_total = _require_number(
        measurement["profiled_total_seconds"], "measurement.profiled_total_seconds"
    )
    unprofiled_total = _require_number(
        measurement["unprofiled_total_seconds"], "measurement.unprofiled_total_seconds"
    )
    profiled_ms = _require_number(
        measurement["profiled_ms_per_product_solve"],
        "measurement.profiled_ms_per_product_solve",
    )
    unprofiled_ms = _require_number(
        measurement["unprofiled_ms_per_product_solve"],
        "measurement.unprofiled_ms_per_product_solve",
    )
    if not math.isclose(profiled_ms, profiled_total * 1000.0 / repeats, rel_tol=1e-9):
        raise ProfileDataError("profiled per-solve time is inconsistent")
    if not math.isclose(
        unprofiled_ms, unprofiled_total * 1000.0 / repeats, rel_tol=1e-9
    ):
        raise ProfileDataError("unprofiled per-solve time is inconsistent")
    if not isinstance(measurement["response_sha256"], str) or not HASH_RE.fullmatch(
        measurement["response_sha256"]
    ):
        raise ProfileDataError("invalid response fingerprint")
    check_ids = measurement["check_ids"]
    if (
        not isinstance(check_ids, list)
        or any(not isinstance(item, str) or not item for item in check_ids)
        or check_ids != sorted(set(check_ids))
    ):
        raise ProfileDataError("check_ids must be sorted unique non-empty strings")

    targets = value["targets"]
    if not isinstance(targets, list) or len(targets) != len(TARGET_MANIFEST):
        raise ProfileDataError("target evidence is incomplete")
    by_id: dict[str, dict[str, Any]] = {}
    manifest = {item["target_id"]: item for item in TARGET_MANIFEST}
    for index, raw_target in enumerate(targets):
        target = _require_exact_keys(raw_target, TARGET_KEYS, f"targets[{index}]")
        target_id = target["target_id"]
        if (
            not isinstance(target_id, str)
            or target_id not in manifest
            or target_id in by_id
        ):
            raise ProfileDataError("target IDs are unknown or duplicated")
        spec = manifest[target_id]
        if target["module"] != spec["module"] or target["qualname"] != spec["qualname"]:
            raise ProfileDataError("target identity does not match manifest")
        availability = target["availability"]
        if availability not in ("absent", "present_not_called", "called"):
            raise ProfileDataError("invalid target availability")
        primitive = _require_int(target["primitive_calls"], "primitive_calls")
        total = _require_int(target["total_calls"], "total_calls")
        if primitive > total:
            raise ProfileDataError("primitive_calls cannot exceed total_calls")
        if not isinstance(target["recursive"], bool) or target["recursive"] != (
            total != primitive
        ):
            raise ProfileDataError("recursive flag is inconsistent with call counts")
        times = {
            name: _require_number(target[name], name)
            for name in (
                "self_seconds",
                "cumulative_seconds",
                "self_ms_per_product_solve",
                "cumulative_ms_per_product_solve",
                "self_ms_per_target_call",
                "cumulative_ms_per_target_call",
            )
        }
        if times["cumulative_seconds"] + 1e-15 < times["self_seconds"]:
            raise ProfileDataError("cumulative time cannot be below self time")
        if times["self_ms_per_product_solve"] > profiled_ms + 1e-9:
            raise ProfileDataError("target self time exceeds profiled wall time")
        if not math.isclose(
            times["self_ms_per_product_solve"],
            times["self_seconds"] * 1000.0 / repeats,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ) or not math.isclose(
            times["cumulative_ms_per_product_solve"],
            times["cumulative_seconds"] * 1000.0 / repeats,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ProfileDataError("target per-product-solve time is inconsistent")
        expected_self_per_target = (
            times["self_seconds"] * 1000.0 / total if total else 0.0
        )
        expected_cumulative_per_target = (
            times["cumulative_seconds"] * 1000.0 / total if total else 0.0
        )
        if not math.isclose(
            times["self_ms_per_target_call"],
            expected_self_per_target,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ) or not math.isclose(
            times["cumulative_ms_per_target_call"],
            expected_cumulative_per_target,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ProfileDataError("target per-call time is inconsistent")
        if availability == "absent":
            if any(
                target[name] is not None
                for name in ("repo_relative_filename", "first_line", "code_name")
            ):
                raise ProfileDataError("absent target must not claim code identity")
            if primitive or total or any(times.values()):
                raise ProfileDataError("absent target must have explicit zero measurements")
        else:
            path = target["repo_relative_filename"]
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                raise ProfileDataError("invalid repo-relative target filename")
            _require_int(target["first_line"], "first_line", minimum=1)
            if not isinstance(target["code_name"], str) or not target["code_name"]:
                raise ProfileDataError("invalid target code name")
            if availability == "present_not_called" and (
                primitive or total or any(times.values())
            ):
                raise ProfileDataError("present_not_called target must have zero measurements")
            if availability == "called" and total == 0:
                raise ProfileDataError("called target must have calls")
        if metadata["revision_label"] == "head" and target_id in HEAD_REQUIRED_TARGETS:
            if availability == "absent":
                raise ProfileDataError("required head target is absent")
        by_id[target_id] = target
    if tuple(item["target_id"] for item in targets) != TARGET_IDS:
        raise ProfileDataError("target evidence order must match the stable manifest")
    for candidate, frontier in CANDIDATE_FRONTIERS.items():
        frontier_self = sum(
            float(by_id[target_id]["self_ms_per_product_solve"])
            for target_id in frontier
        )
        if frontier_self > profiled_ms + 1e-9:
            raise ProfileDataError(
                f"candidate frontier self time exceeds profiled wall time: {candidate}"
            )

    top_cumulative = value["top_cumulative"]
    if (
        not isinstance(top_cumulative, list)
        or not top_cumulative
        or len(top_cumulative) > TOP_CUMULATIVE_LIMIT
    ):
        raise ProfileDataError("top_cumulative must be a non-empty bounded list")
    previous_sort_key: tuple[Any, ...] | None = None
    for index, raw_entry in enumerate(top_cumulative, start=1):
        entry = _require_exact_keys(
            raw_entry, TOP_CUMULATIVE_KEYS, f"top_cumulative[{index - 1}]"
        )
        if _require_int(entry["rank"], "top_cumulative.rank", minimum=1) != index:
            raise ProfileDataError("top_cumulative ranks must be contiguous")
        if entry["origin_kind"] not in ("repo", "dependency", "stdlib", "builtin"):
            raise ProfileDataError("invalid top_cumulative origin kind")
        if entry["origin_kind"] == "repo":
            filename = entry["filename"]
            if (
                not isinstance(filename, str)
                or not filename
                or Path(filename).is_absolute()
                or ".." in Path(filename).parts
                or entry["module_label"] is not None
            ):
                raise ProfileDataError("invalid repo top_cumulative identity")
        else:
            label = entry["module_label"]
            if (
                entry["filename"] is not None
                or not isinstance(label, str)
                or not label
                or len(label) > 160
                or "/" in label
                or "\\" in label
            ):
                raise ProfileDataError("invalid external top_cumulative identity")
        first_line = _require_int(entry["first_line"], "top_cumulative.first_line")
        code_name = entry["code_name"]
        if (
            not isinstance(code_name, str)
            or not code_name
            or len(code_name) > 300
            or "\n" in code_name
            or "\r" in code_name
        ):
            raise ProfileDataError("invalid top_cumulative code name")
        primitive = _require_int(
            entry["primitive_calls"], "top_cumulative.primitive_calls"
        )
        total = _require_int(entry["total_calls"], "top_cumulative.total_calls")
        if primitive > total or total == 0:
            raise ProfileDataError("invalid top_cumulative call counts")
        self_seconds = _require_number(
            entry["self_seconds"], "top_cumulative.self_seconds"
        )
        cumulative_seconds = _require_number(
            entry["cumulative_seconds"], "top_cumulative.cumulative_seconds"
        )
        self_ms = _require_number(
            entry["self_ms_per_product_solve"],
            "top_cumulative.self_ms_per_product_solve",
        )
        cumulative_ms = _require_number(
            entry["cumulative_ms_per_product_solve"],
            "top_cumulative.cumulative_ms_per_product_solve",
        )
        if cumulative_seconds + 1e-15 < self_seconds:
            raise ProfileDataError("top_cumulative cumulative time is below self time")
        if not math.isclose(
            self_ms,
            self_seconds * 1000.0 / repeats,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ) or not math.isclose(
            cumulative_ms,
            cumulative_seconds * 1000.0 / repeats,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ProfileDataError("top_cumulative per-solve arithmetic is inconsistent")
        if cumulative_ms > profiled_ms + 1e-9:
            raise ProfileDataError("top_cumulative time exceeds profiled wall time")
        sort_key = (
            -cumulative_seconds,
            entry["origin_kind"],
            entry["filename"] or entry["module_label"] or "",
            first_line,
            code_name,
        )
        if previous_sort_key is not None and sort_key < previous_sort_key:
            raise ProfileDataError("top_cumulative ordering is not deterministic")
        previous_sort_key = sort_key
    return value


def _candidate_self_ms(artifact: dict[str, Any], candidate: str) -> float:
    targets = {item["target_id"]: item for item in artifact["targets"]}
    return sum(
        float(targets[target_id]["self_ms_per_product_solve"])
        for target_id in CANDIDATE_FRONTIERS[candidate]
    )


def _sign(value: float, epsilon: float = 1e-12) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0


def compare(args: argparse.Namespace) -> dict[str, Any]:
    expected_base = _require_sha(args.expected_base_sha, "expected_base_sha")
    expected_head = _require_sha(args.expected_head_sha, "expected_head_sha")
    if expected_base == expected_head:
        raise ProfileDataError("expected base and head SHAs must differ")
    expected_rounds = _require_int(args.expected_rounds, "expected_rounds", minimum=1)
    expected_warmups = _require_int(args.expected_warmups, "expected_warmups", minimum=1)
    expected_repeats = _require_int(args.expected_repeats, "expected_repeats", minimum=1)
    if expected_rounds != EXPECTED_ROUNDS:
        raise ProfileDataError(f"expected_rounds must be {EXPECTED_ROUNDS}")
    if expected_warmups != EXPECTED_WARMUPS or expected_repeats != EXPECTED_REPEATS:
        raise ProfileDataError(
            f"expected sampling must be exactly {EXPECTED_WARMUPS}/{EXPECTED_REPEATS}"
        )
    evidence_dir = Path(args.evidence_dir).resolve(strict=True)
    entries = list(evidence_dir.iterdir())
    if any(not item.is_file() or item.suffix != ".json" for item in entries):
        raise ProfileDataError("evidence directory contains unexpected files")
    if len(entries) != expected_rounds * len(REVISION_LABELS) * len(CASE_IDS):
        raise ProfileDataError("diagnostic evidence must contain exactly 16 JSON artifacts")

    artifacts: dict[tuple[int, str, str], dict[str, Any]] = {}
    for path in sorted(entries):
        artifact = _validate_artifact(_load_json_strict(path))
        metadata = artifact["metadata"]
        case = artifact["case"]
        label = metadata["revision_label"]
        expected_sha = expected_head if label == "head" else expected_base
        if metadata["revision_sha"] != expected_sha:
            raise ProfileDataError("artifact revision SHA does not match exact expected ref")
        if metadata["round_number"] not in range(1, expected_rounds + 1):
            raise ProfileDataError("artifact round is outside the expected range")
        measurement = artifact["measurement"]
        if measurement["warmups"] != expected_warmups or measurement["repeats"] != expected_repeats:
            raise ProfileDataError("artifact sample counts do not match the contract")
        key = (metadata["round_number"], label, case["case_id"])
        if key in artifacts:
            raise ProfileDataError("duplicate round/revision/case artifact")
        artifacts[key] = artifact

    expected_keys = {
        (round_number, label, case_id)
        for round_number in range(1, expected_rounds + 1)
        for label in REVISION_LABELS
        for case_id in CASE_IDS
    }
    if set(artifacts) != expected_keys:
        raise ProfileDataError("round/revision/case evidence is incomplete")

    head_first = 0
    stability: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {}
    target_identity_stability: dict[tuple[str, str], tuple[Any, ...]] = {}
    for round_number in range(1, expected_rounds + 1):
        positions: dict[str, int] = {}
        for label in REVISION_LABELS:
            case_positions = {
                artifacts[(round_number, label, case_id)]["metadata"]["position"]
                for case_id in CASE_IDS
            }
            if len(case_positions) != 1:
                raise ProfileDataError("cases for one revision do not share a process position")
            positions[label] = next(iter(case_positions))
        if set(positions.values()) != {1, 2}:
            raise ProfileDataError("base/head positions are not complementary")
        expected_head_position = 1 if round_number % 2 == 1 else 2
        if positions["head"] != expected_head_position:
            raise ProfileDataError("base/head execution order is not exactly alternating")
        if positions["head"] == 1:
            head_first += 1
        for label in REVISION_LABELS:
            for case_id in CASE_IDS:
                artifact = artifacts[(round_number, label, case_id)]
                marker = (
                    artifact["measurement"]["response_sha256"],
                    tuple(artifact["measurement"]["check_ids"]),
                )
                stable_key = (label, case_id)
                if stable_key in stability and stability[stable_key] != marker:
                    raise ProfileDataError("same-ref response semantics changed across rounds")
                stability[stable_key] = marker
                for target in artifact["targets"]:
                    presence = (
                        "absent" if target["availability"] == "absent" else "present"
                    )
                    identity = (
                        target["module"],
                        target["qualname"],
                        presence,
                        target["repo_relative_filename"],
                        target["first_line"],
                        target["code_name"],
                    )
                    identity_key = (label, target["target_id"])
                    if (
                        identity_key in target_identity_stability
                        and target_identity_stability[identity_key] != identity
                    ):
                        raise ProfileDataError(
                            "same-ref target identity changed across evidence"
                        )
                    target_identity_stability[identity_key] = identity
    if head_first != expected_rounds // 2:
        raise ProfileDataError("base/head execution positions are not balanced 2:2")

    candidate_results: list[dict[str, Any]] = []
    rigid_winners: list[str] = []
    direction_mismatch = False
    recursive_candidates: set[str] = set()
    for candidate, frontier in CANDIDATE_FRONTIERS.items():
        case_results: dict[str, list[dict[str, Any]]] = {}
        for case_id in CASE_IDS:
            rounds = []
            for round_number in range(1, expected_rounds + 1):
                head = artifacts[(round_number, "head", case_id)]
                base = artifacts[(round_number, "base", case_id)]
                head_total = float(
                    head["measurement"]["profiled_ms_per_product_solve"]
                )
                base_total = float(
                    base["measurement"]["profiled_ms_per_product_solve"]
                )
                profiled_delta = head_total - base_total
                unprofiled_delta = float(
                    head["measurement"]["unprofiled_ms_per_product_solve"]
                ) - float(base["measurement"]["unprofiled_ms_per_product_solve"])
                candidate_delta = _candidate_self_ms(head, candidate) - _candidate_self_ms(
                    base, candidate
                )
                share = candidate_delta / profiled_delta if profiled_delta > 0 else None
                meets = (
                    profiled_delta > 0
                    and unprofiled_delta > 0
                    and candidate_delta > 0
                    and (
                        candidate_delta >= 0.6
                        or (share is not None and share >= 0.60)
                    )
                )
                rounds.append(
                    {
                        "round_number": round_number,
                        "profiled_total_delta_ms_per_product_solve": profiled_delta,
                        "unprofiled_total_delta_ms_per_product_solve": unprofiled_delta,
                        "candidate_self_delta_ms_per_product_solve": candidate_delta,
                        "candidate_share_of_profiled_delta": share,
                        "meets_threshold": meets,
                    }
                )
                if case_id == "rigid_body" and _sign(profiled_delta) != _sign(
                    unprofiled_delta
                ):
                    direction_mismatch = True
                target_map_head = {item["target_id"]: item for item in head["targets"]}
                target_map_base = {item["target_id"]: item for item in base["targets"]}
                if any(
                    target_map_head[target_id]["recursive"]
                    or target_map_base[target_id]["recursive"]
                    for target_id in frontier
                ):
                    recursive_candidates.add(candidate)
            case_results[case_id] = rounds
        rigid_meets = all(item["meets_threshold"] for item in case_results["rigid_body"])
        projectile_meets = all(
            item["meets_threshold"] for item in case_results["projectile"]
        )
        if rigid_meets:
            rigid_winners.append(candidate)
        candidate_results.append(
            {
                "candidate": candidate,
                "frontier_metric": "non_overlapping_self_time",
                "frontier_target_ids": list(frontier),
                "rigid_all_rounds_meet": rigid_meets,
                "projectile_all_rounds_meet": projectile_meets,
                "rounds": case_results,
            }
        )

    reasons: list[str] = []
    verdict = "INCONCLUSIVE"
    selected_candidate = None
    if direction_mismatch:
        reasons.append("profiled and unprofiled rigid-body directions disagree")
    if recursive_candidates:
        reasons.append("candidate frontier contains a recursive target")
    if len(rigid_winners) != 1:
        reasons.append("exactly one rigid-body candidate did not meet the fixed threshold")
    if len(rigid_winners) == 1:
        winner = rigid_winners[0]
        winner_result = next(
            item for item in candidate_results if item["candidate"] == winner
        )
        if winner_result["projectile_all_rounds_meet"]:
            reasons.append("the same candidate increase appears in the projectile control")
        elif not direction_mismatch and not recursive_candidates:
            verdict = "CANDIDATE_IDENTIFIED"
            selected_candidate = winner
    if verdict == "CANDIDATE_IDENTIFIED":
        reasons.append("candidate requires a minimal fix and independent Release revalidation")
    else:
        reasons.append("no product or threshold change is authorized by this evidence")

    top_cumulative_evidence = []
    for key in sorted(artifacts):
        artifact = artifacts[key]
        top_cumulative_evidence.append(
            {
                "round_number": artifact["metadata"]["round_number"],
                "revision_label": artifact["metadata"]["revision_label"],
                "revision_sha": artifact["metadata"]["revision_sha"],
                "case_id": artifact["case"]["case_id"],
                "top_cumulative": artifact["top_cumulative"],
            }
        )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "volatile_diagnostic_profile_comparison",
        "deterministic_report_eligible": False,
        "expected_base_sha": expected_base,
        "expected_head_sha": expected_head,
        "artifact_count": len(artifacts),
        "rounds": expected_rounds,
        "warmups": expected_warmups,
        "repeats": expected_repeats,
        "attribution_unit": "milliseconds_per_product_solve",
        "verdict": verdict,
        "selected_candidate": selected_candidate,
        "reasons": reasons,
        "candidates": candidate_results,
        "top_cumulative_usage": "diagnostic_only_not_candidate_attribution",
        "top_cumulative_evidence": top_cumulative_evidence,
    }
    _write_json_atomic(Path(args.out), summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--backend-root", required=True)
    collect_parser.add_argument("--revision-label", choices=REVISION_LABELS, required=True)
    collect_parser.add_argument("--revision-sha", required=True)
    collect_parser.add_argument("--case", dest="case_id", choices=CASE_IDS, required=True)
    collect_parser.add_argument("--round-number", type=int, required=True)
    collect_parser.add_argument("--position", type=int, required=True)
    collect_parser.add_argument("--warmups", type=int, default=EXPECTED_WARMUPS)
    collect_parser.add_argument("--repeats", type=int, default=EXPECTED_REPEATS)
    collect_parser.add_argument("--out", required=True)
    collect_parser.set_defaults(handler=collect)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--evidence-dir", required=True)
    compare_parser.add_argument("--expected-base-sha", required=True)
    compare_parser.add_argument("--expected-head-sha", required=True)
    compare_parser.add_argument("--expected-rounds", type=int, default=EXPECTED_ROUNDS)
    compare_parser.add_argument(
        "--expected-warmups", type=int, default=EXPECTED_WARMUPS
    )
    compare_parser.add_argument(
        "--expected-repeats", type=int, default=EXPECTED_REPEATS
    )
    compare_parser.add_argument("--out", required=True)
    compare_parser.set_defaults(handler=compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except ProfileDataError as exc:
        print(f"phase52 rigid profile rejected: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
