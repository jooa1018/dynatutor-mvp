from __future__ import annotations

"""One-pass, privacy-safe tracing of the established solve pipeline."""

from collections.abc import Mapping
import math
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from engine.simulation.contracts import NUMERIC_POLICY_VERSION
from engine.verification.policy import POLICY_VERSION

from .contracts import (
    BENCHMARK_VERSION,
    CANONICAL_SCHEMA_VERSION,
    LEGACY_MODEL_SCHEMA_VERSION,
    SOLVER_PIPELINE_VERSION,
    STATUS_VALUES,
    TRACE_SCHEMA_VERSION,
    TRACE_VERSION,
    TYPED_MODEL_SCHEMA_VERSION,
    StableSnapshot,
    sha256_text,
    stable_sha256,
)


_STAGES = ("parse", "route", "solve", "verify")
def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _finite(value: Any, *, field: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric, not bool")
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _expression(value: Any) -> str | float | int | None:
    """Return a deterministic expression representation without object reprs."""

    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _finite(value, field="expression")
    if isinstance(value, str):
        return value
    if callable(value):
        module = _identifier(getattr(value, "__module__", None)) or "callable"
        qualname = _identifier(getattr(value, "__qualname__", None)) or type(value).__name__
        return f"callable:{module}.{qualname}"
    try:
        import sympy as sp

        if isinstance(value, sp.Basic):
            return sp.srepr(value)
    except ImportError:
        pass
    # Unknown runtime objects are represented only by a stable type ID. Their
    # repr may include memory addresses or user-controlled display text.
    return f"type:{type(value).__module__}.{type(value).__qualname__}"


def _vector(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "x": _expression(_get(value, "x")),
        "y": _expression(_get(value, "y")),
        "frame_id": _identifier(_get(value, "frame_id")),
        "dimension": _identifier(_get(value, "dimension")),
    }


def _quantity(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "symbol": _identifier(_get(value, "symbol")),
        "magnitude": _finite(_get(value, "magnitude"), field="quantity.magnitude"),
        "unit": _identifier(_get(value, "unit")),
        "dimension": _identifier(_get(value, "dimension")),
        "source_fact_id": _identifier(_get(value, "source_fact_id")),
        "uncertainty": _finite(_get(value, "uncertainty"), field="quantity.uncertainty"),
        "display_unit": _identifier(_get(value, "display_unit")),
    }


def project_legacy_model(model: Any) -> dict[str, Any]:
    """Versioned allowlist for the legacy PhysicalModel fingerprint."""

    coordinates = _get(model, "coordinates")
    positive = dict(_get(coordinates, "positive_directions", {}) or {})
    body_axes = dict(_get(coordinates, "body_axes", {}) or {})
    return {
        "schema_version": LEGACY_MODEL_SCHEMA_VERSION,
        "system_type": _identifier(_get(model, "system_type")),
        "subtype": _identifier(_get(model, "subtype")),
        "bodies": sorted(
            [
                {
                    "id": _identifier(_get(body, "id")),
                    "role": _identifier(_get(body, "role")),
                    "mass_symbol": _identifier(_get(body, "mass_symbol")),
                    "mass_value": _finite(_get(body, "mass_value"), field="body.mass_value"),
                    "mass_unit": _identifier(_get(body, "mass_unit")),
                    "shape": _identifier(_get(body, "shape")),
                    "surface": _identifier(_get(body, "surface")),
                    "state": _identifier(_get(body, "state")),
                }
                for body in (_get(model, "bodies", []) or [])
            ],
            key=lambda item: item["id"] or "",
        ),
        "forces": sorted(
            [
                {
                    "id": _identifier(_get(force, "id")),
                    "body_id": _identifier(_get(force, "body_id")),
                    "kind": _identifier(_get(force, "kind")),
                    "symbol": _identifier(_get(force, "symbol")),
                    "direction": _identifier(_get(force, "direction")),
                    "axis": _identifier(_get(force, "axis")),
                    "magnitude_expression": _expression(_get(force, "magnitude_expr")),
                    "constitutive_expression": _expression(
                        _get(force, "constitutive_equation")
                    ),
                }
                for force in (_get(model, "forces", []) or [])
            ],
            key=lambda item: item["id"] or "",
        ),
        "constraints": sorted(
            [
                {
                    "id": _identifier(_get(constraint, "id")),
                    "kind": _identifier(_get(constraint, "kind")),
                    "expression": _expression(_get(constraint, "equation")),
                    "related_body_ids": sorted(
                        _identifier(item)
                        for item in (_get(constraint, "related_bodies", []) or [])
                        if _identifier(item) is not None
                    ),
                }
                for constraint in (_get(model, "constraints", []) or [])
            ],
            key=lambda item: item["id"] or "",
        ),
        "coordinate_frame": {
            "id": _identifier(_get(coordinates, "id")),
            "positive_directions": {
                str(key): _identifier(value)
                for key, value in sorted(positive.items(), key=lambda item: str(item[0]))
            },
            "body_axes": {
                str(body_id): {
                    str(axis): _identifier(direction)
                    for axis, direction in sorted(
                        dict(axes or {}).items(), key=lambda item: str(item[0])
                    )
                }
                for body_id, axes in sorted(body_axes.items(), key=lambda item: str(item[0]))
            },
            "angular_positive": _identifier(_get(coordinates, "angular_positive")),
        },
        "equations_ready": bool(_get(model, "equations_ready", False)),
        "assumption_count": len(_get(model, "assumptions", []) or []),
        "missing_info_count": len(_get(model, "missing_info", []) or []),
    }


def project_typed_model(model: Any) -> dict[str, Any] | None:
    """Versioned allowlist for typed frames, bodies and symbolic constraints."""

    has_typed_model = (
        "typed_model" in model
        if isinstance(model, Mapping)
        else hasattr(model, "typed_model")
    )
    physical_model = model if has_typed_model else None
    typed_model = _get(model, "typed_model") if has_typed_model else model
    if typed_model is None:
        return None
    frames = dict(_get(typed_model, "frames", {}) or {})
    bodies = dict(_get(typed_model, "bodies", {}) or {})
    quantities = dict(_get(typed_model, "quantities", {}) or {})
    return {
        "schema_version": TYPED_MODEL_SCHEMA_VERSION,
        "system_type": _identifier(_get(typed_model, "system_type")),
        "frames": [
            {
                "id": _identifier(_get(frame, "id")) or str(frame_id),
                "origin": [_expression(item) for item in (_get(frame, "origin", ()) or ())],
                "basis_x": [_expression(item) for item in (_get(frame, "basis_x", ()) or ())],
                "basis_y": [_expression(item) for item in (_get(frame, "basis_y", ()) or ())],
                "angular_positive": _finite(
                    _get(frame, "angular_positive"), field="frame.angular_positive"
                ),
                "parent_frame": _identifier(_get(frame, "parent_frame")),
                "transform": [
                    [_expression(item) for item in row]
                    for row in (_get(frame, "transform", ()) or ())
                ],
            }
            for frame_id, frame in sorted(frames.items(), key=lambda item: str(item[0]))
        ],
        "bodies": [
            {
                "id": _identifier(_get(body, "id")) or str(body_id),
                "kind": _identifier(_get(body, "kind")),
                "frame_id": _identifier(_get(body, "frame_id")),
                "mass": _quantity(_get(body, "mass")),
                "center_of_mass": _vector(_get(body, "center_of_mass")),
                "inertia_about_com": _quantity(_get(body, "inertia_about_com")),
                "geometry": {
                    str(key): _expression(value)
                    for key, value in sorted(
                        dict(_get(body, "geometry", {}) or {}).items(),
                        key=lambda item: str(item[0]),
                    )
                },
            }
            for body_id, body in sorted(bodies.items(), key=lambda item: str(item[0]))
        ],
        "quantities": [
            {"id": str(quantity_id), **(_quantity(quantity) or {})}
            for quantity_id, quantity in sorted(
                quantities.items(), key=lambda item: str(item[0])
            )
        ],
        "forces": sorted(
            [
                {
                    "id": _identifier(_get(force, "id")),
                    "kind": _identifier(_get(force, "kind")),
                    "body_id": _identifier(_get(force, "body_id")),
                    "application_point": _vector(_get(force, "application_point")),
                    "vector": _vector(_get(force, "vector")),
                    "constitutive_expression": _expression(
                        _get(force, "constitutive_relation")
                    ),
                    "active_state": _identifier(_get(force, "active_state")),
                    "source_fact_id": _identifier(_get(force, "source_fact_id")),
                }
                for force in (_get(typed_model, "forces", []) or [])
            ],
            key=lambda item: item["id"] or "",
        ),
        "moments": sorted(
            [
                {
                    "id": _identifier(_get(moment, "id")),
                    "kind": _identifier(_get(moment, "kind")),
                    "body_id": _identifier(_get(moment, "body_id")),
                    "scalar_expression": _expression(_get(moment, "scalar")),
                    "frame_id": _identifier(_get(moment, "frame_id")),
                    "dimension": _identifier(_get(moment, "dimension")),
                    "active_state": _identifier(_get(moment, "active_state")),
                    "source_fact_id": _identifier(_get(moment, "source_fact_id")),
                }
                for moment in (_get(typed_model, "moments", []) or [])
            ],
            key=lambda item: item["id"] or "",
        ),
        "constraints": sorted(
            [
                {
                    "id": _identifier(_get(constraint, "id")),
                    "kind": _identifier(_get(constraint, "kind")),
                    "frame_id": _identifier(_get(constraint, "frame_id")),
                    "dimension": _identifier(_get(constraint, "dimension")),
                    "expression": _expression(_get(constraint, "expression")),
                    "related_body_ids": sorted(
                        _identifier(item)
                        for item in (_get(constraint, "related_bodies", []) or [])
                        if _identifier(item) is not None
                    ),
                    "source_fact_id": _identifier(_get(constraint, "source_fact_id")),
                }
                for constraint in (_get(typed_model, "constraints", []) or [])
            ],
            key=lambda item: item["id"] or "",
        ),
        "generated_equation_set": (
            project_equation_set(physical_model)
            if physical_model is not None
            else {"equation_ids": [], "equations": []}
        ),
    }


def legacy_model_fingerprint(model: Any) -> str:
    return stable_sha256(project_legacy_model(model), enforce_privacy=True)


def typed_model_fingerprint(model: Any) -> str | None:
    projection = project_typed_model(model)
    if projection is None:
        return None
    return stable_sha256(projection, enforce_privacy=True)


def project_equation_set(model: Any) -> dict[str, Any]:
    equations: list[dict[str, Any]] = []
    for system_name, attribute in (
        ("newton", "generated_equation_system"),
        ("energy_momentum", "generated_energy_momentum_system"),
    ):
        system = _get(model, attribute)
        for equation in (_get(system, "equations", []) or []):
            stable_expression = _get(equation, "sympy_repr") or _get(equation, "equation")
            equations.append(
                {
                    "id": _identifier(_get(equation, "id")),
                    "system": system_name,
                    "kind": _identifier(_get(equation, "kind")),
                    "body_id": _identifier(_get(equation, "body_id")),
                    "axis": _identifier(_get(equation, "axis")),
                    "expression": _expression(stable_expression),
                    "source_force_ids": sorted(
                        _identifier(item)
                        for item in (_get(equation, "source_forces", []) or [])
                        if _identifier(item) is not None
                    ),
                    "unknown_ids": sorted(
                        _identifier(item)
                        for item in (_get(equation, "unknowns", []) or [])
                        if _identifier(item) is not None
                    ),
                }
            )
    equations.sort(key=lambda item: ((item["id"] or ""), item["system"]))
    return {
        "equation_ids": [item["id"] for item in equations],
        "equations": equations,
    }


def _empty_core(request_id: str) -> dict[str, Any]:
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_version": TRACE_VERSION,
        "request_id": request_id,
        "versions": {
            "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
            "legacy_model_schema_version": LEGACY_MODEL_SCHEMA_VERSION,
            "typed_model_schema_version": TYPED_MODEL_SCHEMA_VERSION,
            "solver_pipeline_version": SOLVER_PIPELINE_VERSION,
            "tolerance_policy_version": POLICY_VERSION,
            "numeric_policy_version": NUMERIC_POLICY_VERSION,
            "benchmark_version": BENCHMARK_VERSION,
        },
        "input": {
            "raw_text_hash": None,
            "raw_text_length": 0,
        },
        "student_answer": {
            "present": False,
            "length": 0,
            "hash": None,
        },
        "normalization": {
            "normalized_text_hash": None,
            "normalized_text_length": 0,
            "rule_ids": [],
            "rule_count": 0,
        },
        "parse_candidates": [],
        "canonical_fingerprint": None,
        "clarification_decision": {
            "status": "none",
            "rule_id": None,
            "option_ids": [],
        },
        "route_candidates": {
            "status": None,
            "selected_solver_id": None,
            "candidates": [],
            "risk_flag_ids": [],
        },
        "model_fingerprints": {
            "legacy": {
                "schema_version": LEGACY_MODEL_SCHEMA_VERSION,
                "fingerprint": None,
            },
            "typed": {
                "schema_version": TYPED_MODEL_SCHEMA_VERSION,
                "fingerprint": None,
                "present": False,
            },
        },
        "equation_set": {"equation_ids": [], "equations": []},
        "solution_candidates": [],
        "validation_decision": {
            "status": None,
            "selected_candidate_id": None,
            "valid_alternative_ids": [],
            "rejected_candidate_ids": [],
            "selection_policy_id": None,
            "policy_version": POLICY_VERSION,
            "check_ids": [],
            "error_codes": [],
            "error_count": 0,
            "warning_count": 0,
            "tolerances": {},
        },
        "numeric_validations": [],
        "final_answer": {"ok": None, "answers": []},
        "stages": [{"name": name, "status": "pending"} for name in _STAGES],
        "status": None,
        "error": None,
    }


class SolveTraceCollector:
    """Mutable collector whose deterministic core freezes exactly once."""

    def __init__(self, request_id: str, clock: Callable[[], float] = perf_counter):
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id is required")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._core = _empty_core(request_id.strip())
        self._clock = clock
        self._begun = False
        self._active_stage: str | None = None
        self._stage_started_at: float | None = None
        self._stage_durations: dict[str, float] = {}
        self._snapshot: StableSnapshot | None = None

    def _ensure_mutable(self) -> None:
        if self._snapshot is not None:
            raise RuntimeError("trace is already finalized")

    def begin(self) -> None:
        self._ensure_mutable()
        if self._begun:
            raise RuntimeError("trace has already begun")
        self._begun = True

    @property
    def current_stage(self) -> str | None:
        return self._active_stage

    @property
    def stage_durations(self) -> dict[str, float]:
        return dict(self._stage_durations)

    @property
    def snapshot(self) -> StableSnapshot:
        if self._snapshot is None:
            raise RuntimeError("trace has not been finalized")
        return self._snapshot

    def _stage_entry(self, name: str) -> dict[str, Any]:
        return next(item for item in self._core["stages"] if item["name"] == name)

    def start_stage(self, name: str) -> None:
        self._ensure_mutable()
        if not self._begun:
            raise RuntimeError("begin() must be called before starting a stage")
        if name not in _STAGES:
            raise ValueError(f"unsupported trace stage: {name}")
        if self._active_stage is not None:
            raise RuntimeError("trace stages may not overlap")
        entry = self._stage_entry(name)
        if entry["status"] != "pending":
            raise RuntimeError(f"trace stage {name} has already started")
        expected_index = next(
            (index for index, stage in enumerate(self._core["stages"]) if stage["status"] == "pending"),
            len(_STAGES),
        )
        if _STAGES[expected_index] != name:
            raise RuntimeError(f"trace stage order requires {_STAGES[expected_index]} before {name}")
        started = _finite(self._clock(), field=f"{name}.start_time")
        self._active_stage = name
        self._stage_started_at = float(started)
        entry["status"] = "running"

    def finish_stage(self, name: str) -> None:
        self._ensure_mutable()
        if self._active_stage != name or self._stage_started_at is None:
            raise RuntimeError(f"trace stage {name} is not active")
        finished = float(_finite(self._clock(), field=f"{name}.finish_time"))
        duration = finished - self._stage_started_at
        if duration < 0 or not math.isfinite(duration):
            raise ValueError(f"invalid duration for trace stage {name}")
        self._stage_durations[name] = duration
        self._stage_entry(name)["status"] = "completed"
        self._active_stage = None
        self._stage_started_at = None

    def capture_input(self, problem_text: str, student_solution: str | None) -> None:
        self._ensure_mutable()
        if not isinstance(problem_text, str):
            raise TypeError("problem_text must be a string")
        self._core["input"] = {
            "raw_text_hash": sha256_text(problem_text),
            "raw_text_length": len(problem_text),
        }
        present = student_solution is not None
        if present and not isinstance(student_solution, str):
            raise TypeError("student_solution must be a string or None")
        self._core["student_answer"] = {
            "present": present,
            "length": len(student_solution) if student_solution is not None else 0,
            "hash": sha256_text(student_solution) if student_solution is not None else None,
        }

    def capture_canonical(self, canonical: Any) -> None:
        self._ensure_mutable()
        v2 = _get(canonical, "canonical_v2")
        normalized = _get(v2, "normalized_text")
        if normalized is not None and not isinstance(normalized, str):
            raise TypeError("canonical normalized_text must be a string")
        normalized_fact_ids = sorted(
            _identifier(_get(fact, "fact_id"))
            for fact in (_get(v2, "facts", []) or [])
            if (
                _get(fact, "extraction_evidence", {}).get("normalization_evidence")
                if isinstance(_get(fact, "extraction_evidence", {}), Mapping)
                else False
            )
            or "normaliz" in str(_get(fact, "provenance", "")).casefold()
        )
        normalized_fact_ids = [item for item in normalized_fact_ids if item is not None]
        self._core["normalization"] = {
            "normalized_text_hash": sha256_text(normalized) if normalized is not None else None,
            "normalized_text_length": len(normalized) if normalized is not None else 0,
            "rule_ids": normalized_fact_ids,
            "rule_count": len(normalized_fact_ids),
        }

        selected_type = _get(v2, "system_type")
        selected_subtype = _get(v2, "subtype")
        parse_candidates = []
        for candidate in (_get(v2, "parse_candidates", []) or []):
            system_candidates = _get(candidate, "system_type_candidates", []) or []
            selected = any(
                _get(item, "system_type") == selected_type
                and _get(item, "subtype") == selected_subtype
                for item in system_candidates
            )
            parse_candidates.append(
                {
                    "candidate_id": _identifier(_get(candidate, "candidate_id")),
                    "score": _finite(_get(candidate, "score"), field="parse_candidate.score"),
                    "fact_ids": sorted(
                        _identifier(item)
                        for item in (_get(candidate, "facts", []) or [])
                        if _identifier(item) is not None
                    ),
                    "status": "selected" if selected else "retained",
                    "warning_count": len(_get(candidate, "warnings", []) or []),
                    "missing_info_count": len(_get(candidate, "missing_info", []) or []),
                    "conflict_count": len(_get(candidate, "conflicts", []) or []),
                }
            )
        parse_candidates.sort(key=lambda item: item["candidate_id"] or "")
        self._core["parse_candidates"] = parse_candidates
        self._core["canonical_fingerprint"] = _identifier(_get(v2, "fingerprint"))

    def capture_route(self, decision: Any) -> None:
        self._ensure_mutable()
        selected = _identifier(_get(decision, "selected_solver_id"))
        candidates = []
        all_risk_flags: set[str] = set()
        for candidate in (_get(decision, "candidates", []) or []):
            solver_id = _identifier(_get(candidate, "solver_id"))
            risk_flags = sorted(
                _identifier(item)
                for item in (_get(candidate, "risk_flags", []) or [])
                if _identifier(item) is not None
            )
            all_risk_flags.update(risk_flags)
            eligible = bool(_get(candidate, "selection_eligible", True))
            candidates.append(
                {
                    "solver_id": solver_id,
                    "family_id": _identifier(_get(candidate, "family")),
                    "raw_score": _finite(_get(candidate, "raw_score"), field="route.raw_score"),
                    "normalized_score": _finite(
                        _get(candidate, "normalized_score"), field="route.normalized_score"
                    ),
                    "status": (
                        "selected"
                        if solver_id == selected
                        else "eligible"
                        if eligible
                        else "ineligible"
                    ),
                    "risk_flag_ids": risk_flags,
                }
            )
        candidates.sort(key=lambda item: item["solver_id"] or "")
        self._core["route_candidates"] = {
            "status": _identifier(_get(decision, "status")),
            "selected_solver_id": selected,
            "candidates": candidates,
            "risk_flag_ids": sorted(all_risk_flags),
        }

    def capture_models(self, physical_model: Any) -> None:
        self._ensure_mutable()
        typed = _get(physical_model, "typed_model")
        self._core["model_fingerprints"] = {
            "legacy": {
                "schema_version": LEGACY_MODEL_SCHEMA_VERSION,
                "fingerprint": legacy_model_fingerprint(physical_model),
            },
            "typed": {
                "schema_version": TYPED_MODEL_SCHEMA_VERSION,
                "fingerprint": typed_model_fingerprint(physical_model),
                "present": typed is not None,
            },
        }
        self._core["equation_set"] = project_equation_set(physical_model)

    def capture_clarification(self, clarification: Any) -> None:
        self._ensure_mutable()
        if clarification is None:
            self._core["clarification_decision"] = {
                "status": "none",
                "rule_id": None,
                "option_ids": [],
            }
            return
        self._core["clarification_decision"] = {
            "status": "clarify",
            "rule_id": _identifier(_get(clarification, "rule")),
            "option_ids": sorted(
                _identifier(_get(option, "id"))
                for option in (_get(clarification, "options", []) or [])
                if _identifier(_get(option, "id")) is not None
            ),
        }

    def capture_solution_candidates(self, batch: Any, result: Any) -> None:
        self._ensure_mutable()
        decision = _get(result, "selection_decision")
        selected_candidate = _get(decision, "selected_candidate")
        selected_id = _identifier(_get(selected_candidate, "candidate_id"))
        alternative_ids = {
            _identifier(_get(item, "candidate_id"))
            for item in (_get(decision, "valid_alternatives", []) or [])
        }
        rejected_ids = {
            _identifier(_get(_get(item, "candidate"), "candidate_id"))
            for item in (_get(decision, "rejected_candidates", []) or [])
        }
        unit_by_key: dict[str, str | None] = {}
        answers = list(_get(result, "answers", []) or [])
        if _get(result, "answer") is not None:
            answers.append(_get(result, "answer"))
        for answer in answers:
            for key in (
                _identifier(_get(answer, "output_key")),
                _identifier(_get(answer, "symbol")),
            ):
                if key is not None:
                    unit_by_key[key] = _identifier(_get(answer, "unit"))

        projected = []
        for candidate in (_get(batch, "candidates", []) or []):
            candidate_id = _identifier(_get(candidate, "candidate_id"))
            values = []
            invalid_numeric_count = 0
            for key, value in sorted(
                dict(_get(candidate, "numerical_mapping", {}) or {}).items(),
                key=lambda item: str(item[0]),
            ):
                try:
                    numeric = _finite(value, field=f"candidate.{key}")
                except (TypeError, ValueError):
                    # The trace retains only finite candidate values. The
                    # validator status/check IDs still expose the rejection.
                    invalid_numeric_count += 1
                    continue
                values.append(
                    {
                        "key": str(key),
                        "numeric": numeric,
                        "unit": unit_by_key.get(str(key)),
                    }
                )
            checks = [
                {
                    "check_id": _identifier(_get(check, "check_id")),
                    "status": _identifier(_get(check, "status")),
                }
                for check in (_get(candidate, "validation_checks", []) or [])
            ]
            checks.sort(key=lambda item: item["check_id"] or "")
            status = (
                "selected"
                if candidate_id == selected_id
                else "valid_alternative"
                if candidate_id in alternative_ids
                else "rejected"
                if candidate_id in rejected_ids
                else "candidate"
            )
            projected.append(
                {
                    "candidate_id": candidate_id,
                    "status": status,
                    "values": values,
                    "check_ids": [item["check_id"] for item in checks],
                    "checks": checks,
                    "rejection_count": len(_get(candidate, "rejection_reasons", []) or []),
                    "invalid_numeric_count": invalid_numeric_count,
                }
            )
        projected.sort(key=lambda item: item["candidate_id"] or "")
        self._core["solution_candidates"] = projected
        self._capture_selection_decision(decision)

    def _capture_selection_decision(self, decision: Any) -> None:
        if decision is None:
            return
        selected = _get(decision, "selected_candidate")
        rejected = _get(decision, "rejected_candidates", []) or []
        all_checks = []
        for item in rejected:
            all_checks.extend(_get(item, "checks", []) or [])
        check_ids = sorted(
            {
                _identifier(_get(check, "check_id"))
                for check in all_checks
                if _identifier(_get(check, "check_id")) is not None
            }
        )
        error_codes = sorted(
            {
                _identifier(_get(check, "check_id")) or "candidate_validation"
                for check in all_checks
                if _identifier(_get(check, "status"))
                not in {"passed", "passed_with_warning", "not_applicable"}
            }
        )
        tolerances = {
            str(key): _finite(value, field=f"selection.tolerance.{key}")
            for key, value in sorted(
                dict(_get(decision, "tolerances", {}) or {}).items(),
                key=lambda item: str(item[0]),
            )
        }
        current = self._core["validation_decision"]
        current.update(
            {
                "status": _identifier(_get(decision, "status")),
                "selected_candidate_id": _identifier(_get(selected, "candidate_id")),
                "valid_alternative_ids": sorted(
                    _identifier(_get(item, "candidate_id"))
                    for item in (_get(decision, "valid_alternatives", []) or [])
                    if _identifier(_get(item, "candidate_id")) is not None
                ),
                "rejected_candidate_ids": sorted(
                    _identifier(_get(_get(item, "candidate"), "candidate_id"))
                    for item in rejected
                    if _identifier(_get(_get(item, "candidate"), "candidate_id"))
                    is not None
                ),
                "selection_policy_id": _identifier(_get(decision, "selection_policy")),
                "policy_version": _identifier(_get(decision, "policy_version"))
                or POLICY_VERSION,
                "check_ids": check_ids,
                "error_codes": error_codes,
                "error_count": sum(
                    len(_get(item, "rejection_reasons", []) or []) for item in rejected
                ),
                "tolerances": tolerances,
            }
        )

    def capture_validation(self, report: Any) -> None:
        self._ensure_mutable()
        projected = []
        error_codes: set[str] = set(self._core["validation_decision"]["error_codes"])
        for check in (_get(report, "structured_checks", []) or []):
            check_id = _identifier(_get(check, "check_id"))
            status = _identifier(_get(check, "status"))
            category = _identifier(_get(check, "category"))
            item = {
                "check_id": check_id,
                "category_id": category,
                "status": status,
                "absolute_error": _finite(
                    _get(check, "absolute_error"), field="validation.absolute_error"
                ),
                "relative_error": _finite(
                    _get(check, "relative_error"), field="validation.relative_error"
                ),
                "tolerance": _finite(
                    _get(check, "tolerance"), field="validation.tolerance"
                ),
                "source_equation_ids": sorted(
                    _identifier(value)
                    for value in (_get(check, "source_equation_ids", []) or [])
                    if _identifier(value) is not None
                ),
            }
            projected.append(item)
            if status not in {"passed", "passed_with_warning", "not_applicable"}:
                error_codes.add(check_id or category or "numeric_validation")
        projected.sort(key=lambda item: item["check_id"] or "")
        self._core["numeric_validations"] = projected
        decision = self._core["validation_decision"]
        decision["check_ids"] = sorted(
            set(decision["check_ids"])
            | {item["check_id"] for item in projected if item["check_id"] is not None}
        )
        decision["error_codes"] = sorted(error_codes)
        decision["error_count"] = max(
            int(decision["error_count"]), len(_get(report, "errors", []) or [])
        )
        decision["warning_count"] = len(_get(report, "warnings", []) or [])
        if decision["status"] is None:
            decision["status"] = "passed" if bool(_get(report, "passed", False)) else "failed"
        decision["policy_version"] = (
            _identifier(_get(report, "policy_version")) or decision["policy_version"]
        )

    def capture_response(self, response: Any) -> None:
        self._ensure_mutable()
        answers = list(_get(response, "answers", []) or [])
        if not answers and _get(response, "answer") is not None:
            answers = [_get(response, "answer")]
        projected = []
        for answer in answers:
            numeric = _get(answer, "numeric")
            projected.append(
                {
                    "numeric": _finite(numeric, field="answer.numeric")
                    if numeric is not None
                    else None,
                    "unit": _identifier(_get(answer, "unit")),
                    "output_key": _identifier(_get(answer, "output_key")),
                }
            )
        self._core["final_answer"] = {
            "ok": bool(_get(response, "ok", False)),
            "answers": projected,
        }
        self.capture_clarification(_get(response, "clarification"))

    def _freeze(self) -> StableSnapshot:
        self._snapshot = StableSnapshot.from_payload(self._core, enforce_privacy=True)
        return self._snapshot

    def finalize(self, status: str) -> StableSnapshot:
        self._ensure_mutable()
        if not self._begun:
            raise RuntimeError("begin() must be called before finalize()")
        if self._active_stage is not None:
            raise RuntimeError("active trace stage must finish before finalize()")
        if status not in STATUS_VALUES:
            raise ValueError(f"unsupported trace status: {status}")
        for stage in self._core["stages"]:
            if stage["status"] == "pending":
                stage["status"] = "skipped"
        self._core["status"] = status
        return self._freeze()

    def finalize_error(self, stage: str, exception_type: str) -> StableSnapshot:
        self._ensure_mutable()
        if not self._begun:
            self._begun = True
        safe_stage = stage if stage in _STAGES else (self._active_stage or "parse")
        if self._active_stage is not None:
            self._stage_entry(self._active_stage)["status"] = "error"
            self._active_stage = None
            self._stage_started_at = None
        else:
            entry = self._stage_entry(safe_stage)
            if entry["status"] == "pending":
                entry["status"] = "error"
        for item in self._core["stages"]:
            if item["status"] == "pending":
                item["status"] = "skipped"
        self._core["status"] = "error"
        self._core["error"] = {
            "stage": safe_stage,
            "exception_type": _identifier(exception_type) or "Exception",
        }
        return self._freeze()


def new_live_collector(
    request_id: str | None = None,
    *,
    clock: Callable[[], float] = perf_counter,
) -> SolveTraceCollector:
    return SolveTraceCollector(request_id or str(uuid4()), clock=clock)


__all__ = [
    "SolveTraceCollector",
    "legacy_model_fingerprint",
    "new_live_collector",
    "project_equation_set",
    "project_legacy_model",
    "project_typed_model",
    "typed_model_fingerprint",
]
