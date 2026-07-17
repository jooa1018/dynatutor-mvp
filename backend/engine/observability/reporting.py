from __future__ import annotations

"""Deterministic Phase 52 cross-engine reports and volatile performance evidence."""

from collections.abc import Iterable, Mapping, Sequence
from importlib import metadata
import math
from pathlib import Path
from typing import Any

from engine.simulation.contracts import NUMERIC_POLICY_VERSION
from engine.verification.policy import POLICY_VERSION

from .contracts import (
    BENCHMARK_VERSION,
    CANONICAL_SCHEMA_VERSION,
    CROSS_ENGINE_REPORT_SCHEMA_VERSION,
    CROSS_ENGINE_REPORT_VERSION,
    LEGACY_MODEL_SCHEMA_VERSION,
    PERFORMANCE_SCHEMA_VERSION,
    PERFORMANCE_VERSION,
    SOLVER_PIPELINE_VERSION,
    STATUS_VALUES,
    TRACE_SCHEMA_VERSION,
    TRACE_VERSION,
    TYPED_MODEL_SCHEMA_VERSION,
    StableSnapshot,
    sha256_text,
    stable_json_dumps,
)


STAGES = ("parse", "route", "solve", "verify")
TIERS = ("fast", "extended", "nightly")
CASE_FIELDS = (
    "case_id",
    "reference_path",
    "candidate_paths",
    "values_and_units",
    "absolute_relative_errors",
    "invariant_checks",
    "assumptions",
    "engine_settings",
    "runtime",
    "status",
)
CORE_FIELDS = (
    "schema_version",
    "report_version",
    "source_commit",
    "tier",
    "versions",
    "traces",
    "cross_engine_cases",
    "dashboard_sources",
    "expected_skip_policy",
)
VERSION_FIELDS = (
    "canonical_schema_version",
    "legacy_model_schema_version",
    "typed_model_schema_version",
    "solver_pipeline_version",
    "tolerance_policy_version",
    "numeric_policy_version",
    "benchmark_version",
    "trace_version",
    "cross_engine_report_version",
    "performance_version",
    "sympy",
    "scipy",
    "pychrono",
    "source_commit",
)
STATUS_PRECEDENCE = {
    "error": 7,
    "disagreement": 6,
    "unsupported": 5,
    "skipped": 4,
    "inconclusive": 3,
    "passed_with_warning": 2,
    "passed": 1,
}
PHASE42_MEAN_MS = 9.458354
PHASE42_P95_MS = 32.092011
ABSOLUTE_MEAN_CEILING_MS = 60.0
ABSOLUTE_P95_CEILING_MS = 120.0
PHASE50_CASE_IDS = frozenset(
    {
        "pendulum_small_angle_accuracy",
        "pendulum_large_angle_expected_difference",
        "pendulum_equilibrium_hold",
        "spring_undamped_accuracy",
        "spring_underdamped_accuracy",
        "spring_critical_accuracy",
        "spring_overdamped_accuracy",
    }
)
PHASE51_CASE_IDS = frozenset(
    {
        "rolling_sphere",
        "rolling_disk",
        "incline_friction_slip",
        "incline_friction_stick",
        "collision_restitution",
        "massive_pulley",
    }
)
PHASE51_REPORT_SCHEMA_VERSION = 1
PHASE51_REPORT_VERSION = "phase51-pychrono-report-v1"

# This policy is deliberately code-owned. A result cannot add an entry to it.
# Extended CI may run without the separately pinned PyChrono environment. The
# wildcard is limited to this one engine and tier; nightly has no allowances.
EXPECTED_SKIP_MANIFEST: tuple[tuple[str, str, str], ...] = (
    ("extended", "pychrono", "*"),
)

DASHBOARD_METRIC_IDS = (
    "golden_answer_pass_rate",
    "false_solve_rate",
    "clarification_precision_recall",
    "routing_accuracy",
    "residual_invariant_failure_count",
    "cross_engine_disagreement_count",
    "p95_fast_path_latency_ms",
    "flaky_test_count",
)


def _finite(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric, not bool")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _optional_finite(value: Any, *, field: str) -> float | None:
    return None if value is None else _finite(value, field=field)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _safe_scalar(value: Any, *, field: str) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return _finite(value, field=field)
    return _identifier(value)


def _json_scalar(value: Any, *, field: str) -> None:
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        raise TypeError(f"{field} must be a JSON scalar")
    if isinstance(value, float):
        _finite(value, field=field)


def _nonnegative_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _nonnegative_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be numeric")
    numeric = _finite(value, field=field)
    if numeric < 0:
        raise ValueError(f"{field} may not be negative")
    return numeric


def _source_commit(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    canonical = build_version_evidence(source_commit=value)["source_commit"]
    if value != canonical:
        raise ValueError(f"{field} must be a lowercase 40-character git SHA")
    return canonical


def _validate_versions(value: Any, *, source_commit: str, path: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be an object")
    allowed = frozenset(VERSION_FIELDS) | {"llm_identifier"}
    actual = frozenset(value)
    if not frozenset(VERSION_FIELDS) <= actual or not actual <= allowed:
        added = sorted(actual - allowed)
        missing = sorted(frozenset(VERSION_FIELDS) - actual)
        raise ValueError(f"{path} keys differ; added={added}, missing={missing}")
    for engine in ("sympy", "scipy", "pychrono"):
        runtime_version = value[engine]
        if runtime_version is not None and (
            not isinstance(runtime_version, str)
            or runtime_version != _identifier(runtime_version)
        ):
            raise ValueError(
                f"{path}.{engine} must be null or a nonempty canonical string"
            )
    if "llm_identifier" in value:
        llm_identifier = value["llm_identifier"]
        if (
            not isinstance(llm_identifier, str)
            or llm_identifier != _identifier(llm_identifier)
        ):
            raise ValueError(
                f"{path}.llm_identifier must be a nonempty canonical string"
            )
    expected = build_version_evidence(
        source_commit=source_commit,
        runtime_versions={engine: value[engine] for engine in ("sympy", "scipy", "pychrono")},
    )
    if "llm_identifier" in value:
        expected["llm_identifier"] = value["llm_identifier"]
    if dict(value) != expected:
        raise ValueError(f"{path} does not match code-owned version evidence")


def _version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def build_version_evidence(
    *,
    source_commit: str,
    runtime_versions: Mapping[str, Any] | None = None,
    llm_identifier: str | None = None,
) -> dict[str, Any]:
    """Build version evidence without importing optional numeric engines."""

    commit = _identifier(source_commit)
    if commit is None:
        raise ValueError("source_commit is required")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit.lower()):
        raise ValueError("source_commit must be an exact 40-character git SHA")
    supplied = dict(runtime_versions or {})
    versions: dict[str, Any] = {
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "legacy_model_schema_version": LEGACY_MODEL_SCHEMA_VERSION,
        "typed_model_schema_version": TYPED_MODEL_SCHEMA_VERSION,
        "solver_pipeline_version": SOLVER_PIPELINE_VERSION,
        "tolerance_policy_version": POLICY_VERSION,
        "numeric_policy_version": NUMERIC_POLICY_VERSION,
        "benchmark_version": BENCHMARK_VERSION,
        "trace_version": TRACE_VERSION,
        "cross_engine_report_version": CROSS_ENGINE_REPORT_VERSION,
        "performance_version": PERFORMANCE_VERSION,
        "sympy": supplied.get("sympy", _version("sympy")),
        "scipy": supplied.get("scipy", _version("scipy")),
        "pychrono": supplied.get("pychrono", _version("pychrono")),
        "source_commit": commit.lower(),
    }
    if llm_identifier is not None:
        versions["llm_identifier"] = _identifier(llm_identifier)
    stable_json_dumps(versions)
    return versions


def classify_engine_exception(
    exception: BaseException,
    *,
    declared_module: str,
) -> str:
    """Distinguish a narrow missing dependency from installed runtime failure."""

    if isinstance(exception, ModuleNotFoundError):
        missing = _identifier(getattr(exception, "name", None))
        if missing == declared_module or (missing and missing.startswith(f"{declared_module}.")):
            return "skipped"
    return "error"


def classify_engine_outcome(
    payload: Mapping[str, Any],
    *,
    declared_module: str | None = None,
) -> str:
    """Normalize an engine outcome to the exact seven-status contract."""

    explicit = _identifier(payload.get("status"))
    exception = payload.get("exception")
    if isinstance(exception, BaseException):
        return classify_engine_exception(
            exception,
            declared_module=declared_module or "",
        )
    if explicit == "skipped":
        # A serialized/free-form result is never its own authority for a
        # missing dependency. Accepted Phase 51 provenance is handled only by
        # the dedicated normalizer below.
        return "error"
    if explicit in STATUS_VALUES:
        if explicit == "passed" and payload.get("warnings"):
            return "passed_with_warning"
        return explicit
    if explicit in {"error", "failed_runtime", "initialization_failed"}:
        return "error"
    if explicit in {"unavailable", "missing_dependency"}:
        return "error"
    if explicit in {"unsupported", "not_supported"}:
        return "unsupported"
    if explicit in {"failed", "mismatch", "disagreement"}:
        return "disagreement"
    if explicit in {"warning", "passed_with_warning"}:
        return "passed_with_warning"
    if explicit in {"passed", "completed", "solved"}:
        return "passed_with_warning" if payload.get("warnings") else "passed"
    if payload.get("passed") is False:
        return "disagreement"
    if payload.get("passed") is True:
        return "passed_with_warning" if payload.get("warnings") else "passed"
    return "inconclusive"


def _trusted_phase51_status(
    chrono: Mapping[str, Any],
    *,
    report: Mapping[str, Any],
) -> str:
    """Classify accepted serialized Phase 51 evidence with code-owned provenance."""

    if chrono.get("status") != "skipped":
        return classify_engine_outcome(chrono, declared_module="pychrono")
    exact_report = (
        report.get("schema_version") == PHASE51_REPORT_SCHEMA_VERSION
        and report.get("report_version") == PHASE51_REPORT_VERSION
    )
    unavailable_runtime = chrono.get("chrono_version") == "unavailable"
    solver = _identifier(chrono.get("solver")) or ""
    not_initialized = solver == "not_initialized" or solver.startswith("not_initialized:")
    if exact_report and unavailable_runtime and not_initialized:
        return "skipped"
    return "error"


def _worst_status(statuses: Iterable[str]) -> str:
    normalized = [status for status in statuses if status in STATUS_PRECEDENCE]
    return max(normalized, key=STATUS_PRECEDENCE.__getitem__) if normalized else "inconclusive"


def is_expected_skip(*, tier: str, engine: str, case_id: str) -> bool:
    return any(
        manifest_tier == tier
        and manifest_engine == engine
        and (manifest_case == case_id or manifest_case == "*")
        for manifest_tier, manifest_engine, manifest_case in EXPECTED_SKIP_MANIFEST
    )


def validate_cross_engine_case(case: Mapping[str, Any]) -> None:
    root = _exact_keys(case, CASE_FIELDS, path="$case")
    for field in ("case_id", "reference_path"):
        if not isinstance(root[field], str) or not root[field].strip():
            raise ValueError(f"cross-engine {field} must be a nonempty string")
    if root["status"] not in STATUS_VALUES:
        raise ValueError(f"invalid cross-engine status: {root['status']}")
    candidates = root["candidate_paths"]
    if (
        not isinstance(candidates, list)
        or not candidates
        or not all(isinstance(item, str) and item.strip() for item in candidates)
    ):
        raise TypeError("candidate_paths must be a list of nonempty strings")

    values = root["values_and_units"]
    if not isinstance(values, Mapping):
        raise TypeError("values_and_units must be an object")
    for path_name, path_values in values.items():
        if not isinstance(path_name, str) or not path_name:
            raise ValueError("values_and_units keys must be nonempty strings")
        if not isinstance(path_values, Mapping):
            raise TypeError(f"values_and_units.{path_name} must be an object")
        if frozenset(path_values) == {"value", "unit"}:
            value_items = [(path_name, path_values)]
        else:
            value_items = list(path_values.items())
        for value_name, value_item in value_items:
            if not isinstance(value_name, str) or not value_name:
                raise ValueError("values_and_units measurement keys must be nonempty strings")
            projection = _exact_keys(
                value_item,
                ("value", "unit"),
                path=f"$case.values_and_units.{path_name}.{value_name}",
            )
            _json_scalar(projection["value"], field=f"values_and_units.{path_name}.{value_name}.value")
            if projection["unit"] is not None and not isinstance(projection["unit"], str):
                raise TypeError("values_and_units unit must be a string or null")

    errors = root["absolute_relative_errors"]
    if not isinstance(errors, Mapping):
        raise TypeError("absolute_relative_errors must be an object")
    for comparison_name, comparison in errors.items():
        if not isinstance(comparison_name, str) or not comparison_name:
            raise ValueError("error comparison keys must be nonempty strings")
        projection = _exact_keys(
            comparison,
            (
                "absolute_error",
                "relative_error",
                "absolute_tolerance",
                "relative_tolerance",
            ),
            path=f"$case.absolute_relative_errors.{comparison_name}",
        )
        for field, value in projection.items():
            if value is not None:
                numeric = _finite(value, field=f"absolute_relative_errors.{comparison_name}.{field}")
                if numeric < 0:
                    raise ValueError("errors and tolerances may not be negative")

    checks = _exact_items(
        root["invariant_checks"],
        ("check_id", "passed"),
        path="$case.invariant_checks",
    )
    for check in checks:
        if not isinstance(check["check_id"], str) or not check["check_id"]:
            raise ValueError("invariant check_id must be a nonempty string")
        if not isinstance(check["passed"], bool):
            raise TypeError("invariant passed must be a boolean")
    assumptions = root["assumptions"]
    if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
        raise TypeError("assumptions must be a list of strings")

    runtime = _exact_keys(root["runtime"], ("engine", "versions"), path="$case.runtime") if _mapping(root["runtime"]).get("engine") == "scipy" else _exact_keys(root["runtime"], ("engine", "version"), path="$case.runtime")
    engine = runtime["engine"]
    if engine == "scipy":
        if frozenset(values) != {"analytic", "scipy"}:
            raise ValueError("SciPy values_and_units keys differ")
        if frozenset(errors) != {"analytic_vs_scipy"}:
            raise ValueError("SciPy absolute_relative_errors keys differ")
        if root["reference_path"] != "analytic" or candidates != ["scipy"]:
            raise ValueError("SciPy case paths differ from the Phase 50 contract")
        settings_root = _exact_keys(root["engine_settings"], ("scipy",), path="$case.engine_settings")
        settings = _exact_keys(
            settings_root["scipy"],
            ("method", "rtol", "atol", "max_step"),
            path="$case.engine_settings.scipy",
        )
        for field, value in settings.items():
            _json_scalar(value, field=f"engine_settings.scipy.{field}")
        versions = _exact_keys(
            runtime["versions"],
            ("sympy", "scipy", "numpy"),
            path="$case.runtime.versions",
        )
        for field, value in versions.items():
            if value is not None and (
                not isinstance(value, str) or value != _identifier(value)
            ):
                raise ValueError(
                    f"runtime.versions.{field} must be null or a nonempty "
                    "canonical string"
                )
    elif engine == "pychrono":
        if frozenset(values) != {"analytic", "product", "pychrono"}:
            raise ValueError("PyChrono values_and_units keys differ")
        comparison_names = frozenset(errors)
        allowed_comparisons = {
            "chrono_vs_analytic",
            "product_vs_analytic",
            "product_vs_chrono",
        }
        if not comparison_names or not comparison_names <= allowed_comparisons:
            raise ValueError("PyChrono absolute_relative_errors keys differ")
        if root["reference_path"] != "analytic" or candidates != ["product", "pychrono"]:
            raise ValueError("PyChrono case paths differ from the Phase 51 contract")
        settings_root = _exact_keys(root["engine_settings"], ("pychrono",), path="$case.engine_settings")
        settings = settings_root["pychrono"]
        required_settings = {"time_step", "solver", "contact_method"}
        optional_settings = {
            "time_step_s",
            "solver_max_iterations",
            "collision_envelope_m",
            "collision_safe_margin_m",
        }
        if not isinstance(settings, Mapping):
            raise TypeError("$case.engine_settings.pychrono must be an object")
        actual_settings = set(settings)
        if not required_settings <= actual_settings or not actual_settings <= required_settings | optional_settings:
            raise ValueError("$case.engine_settings.pychrono keys differ")
        for field, value in settings.items():
            _json_scalar(value, field=f"engine_settings.pychrono.{field}")
        runtime_version = runtime["version"]
        if runtime_version is not None and (
            not isinstance(runtime_version, str)
            or runtime_version != _identifier(runtime_version)
        ):
            raise ValueError(
                "runtime.version must be null or a nonempty canonical string"
            )
    else:
        raise ValueError(f"unsupported cross-engine runtime: {engine}")
    stable_json_dumps(root, enforce_privacy=True)


def _exact_keys(value: Any, expected: Iterable[str], *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be an object")
    expected_set = frozenset(expected)
    actual = frozenset(value)
    if actual != expected_set:
        added = sorted(actual - expected_set)
        missing = sorted(expected_set - actual)
        raise ValueError(f"{path} trace keys differ; added={added}, missing={missing}")
    return value


def _exact_items(value: Any, fields: Iterable[str], *, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise TypeError(f"{path} must be a list")
    return [
        _exact_keys(item, fields, path=f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _trace_scalar(value: Any, *, path: str) -> None:
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        raise TypeError(f"{path} must be a scalar")


def _trace_id_list(value: Any, *, path: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{path} must be a list of strings")


def validate_trace_snapshot(trace: Mapping[str, Any]) -> None:
    """Validate the complete Wave 1 trace as a recursive structural allowlist."""

    root = _exact_keys(
        trace,
        (
            "schema_version",
            "trace_version",
            "request_id",
            "versions",
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
        ),
        path="$trace",
    )
    if root.get("schema_version") != TRACE_SCHEMA_VERSION:
        raise ValueError("trace schema version mismatch")
    if root.get("trace_version") != TRACE_VERSION:
        raise ValueError("trace version mismatch")
    if root.get("status") not in STATUS_VALUES:
        raise ValueError("finalized trace status is invalid")
    versions = _exact_keys(
        root["versions"],
        (
            "canonical_schema_version",
            "legacy_model_schema_version",
            "typed_model_schema_version",
            "solver_pipeline_version",
            "tolerance_policy_version",
            "numeric_policy_version",
            "benchmark_version",
        ),
        path="$trace.versions",
    )
    for key, value in versions.items():
        _trace_scalar(value, path=f"$trace.versions.{key}")
    input_projection = _exact_keys(
        root["input"],
        ("raw_text_hash", "raw_text_length"),
        path="$trace.input",
    )
    for key, value in input_projection.items():
        _trace_scalar(value, path=f"$trace.input.{key}")
    student_projection = _exact_keys(
        root["student_answer"],
        ("present", "length", "hash"),
        path="$trace.student_answer",
    )
    for key, value in student_projection.items():
        _trace_scalar(value, path=f"$trace.student_answer.{key}")
    normalization = _exact_keys(
        root["normalization"],
        ("normalized_text_hash", "normalized_text_length", "rule_ids", "rule_count"),
        path="$trace.normalization",
    )
    _trace_id_list(normalization["rule_ids"], path="$trace.normalization.rule_ids")
    for key in ("normalized_text_hash", "normalized_text_length", "rule_count"):
        _trace_scalar(normalization[key], path=f"$trace.normalization.{key}")
    parse_candidates = _exact_items(
        root["parse_candidates"],
        (
            "candidate_id",
            "score",
            "fact_ids",
            "status",
            "warning_count",
            "missing_info_count",
            "conflict_count",
        ),
        path="$trace.parse_candidates",
    )
    for index, candidate in enumerate(parse_candidates):
        _trace_id_list(candidate["fact_ids"], path=f"$trace.parse_candidates[{index}].fact_ids")
        for key, value in candidate.items():
            if key != "fact_ids":
                _trace_scalar(value, path=f"$trace.parse_candidates[{index}].{key}")
    clarification = _exact_keys(
        root["clarification_decision"],
        ("status", "rule_id", "option_ids"),
        path="$trace.clarification_decision",
    )
    if not isinstance(clarification.get("option_ids"), list):
        raise TypeError("$trace.clarification_decision.option_ids must be a list")
    _trace_id_list(
        clarification["option_ids"], path="$trace.clarification_decision.option_ids"
    )
    _trace_scalar(clarification["status"], path="$trace.clarification_decision.status")
    _trace_scalar(clarification["rule_id"], path="$trace.clarification_decision.rule_id")
    route = _exact_keys(
        root["route_candidates"],
        ("status", "selected_solver_id", "candidates", "risk_flag_ids"),
        path="$trace.route_candidates",
    )
    _trace_id_list(route["risk_flag_ids"], path="$trace.route_candidates.risk_flag_ids")
    _trace_scalar(route["status"], path="$trace.route_candidates.status")
    _trace_scalar(
        route["selected_solver_id"], path="$trace.route_candidates.selected_solver_id"
    )
    route_items = _exact_items(
        route["candidates"],
        (
            "solver_id",
            "family_id",
            "raw_score",
            "normalized_score",
            "status",
            "risk_flag_ids",
        ),
        path="$trace.route_candidates.candidates",
    )
    for index, candidate in enumerate(route_items):
        _trace_id_list(candidate["risk_flag_ids"], path=f"$trace.route_candidates.candidates[{index}].risk_flag_ids")
        for key, value in candidate.items():
            if key != "risk_flag_ids":
                _trace_scalar(value, path=f"$trace.route_candidates.candidates[{index}].{key}")
    fingerprints = _exact_keys(
        root["model_fingerprints"],
        ("legacy", "typed"),
        path="$trace.model_fingerprints",
    )
    legacy_fingerprint = _exact_keys(
        fingerprints["legacy"],
        ("schema_version", "fingerprint"),
        path="$trace.model_fingerprints.legacy",
    )
    typed_fingerprint = _exact_keys(
        fingerprints["typed"],
        ("schema_version", "fingerprint", "present"),
        path="$trace.model_fingerprints.typed",
    )
    for name, projection in (("legacy", legacy_fingerprint), ("typed", typed_fingerprint)):
        for key, value in projection.items():
            _trace_scalar(value, path=f"$trace.model_fingerprints.{name}.{key}")
    equations = _exact_keys(
        root["equation_set"],
        ("equation_ids", "equations"),
        path="$trace.equation_set",
    )
    _trace_id_list(equations["equation_ids"], path="$trace.equation_set.equation_ids")
    equation_items = _exact_items(
        equations["equations"],
        (
            "id",
            "system",
            "kind",
            "body_id",
            "axis",
            "expression",
            "source_force_ids",
            "unknown_ids",
        ),
        path="$trace.equation_set.equations",
    )
    for index, equation in enumerate(equation_items):
        for key in ("source_force_ids", "unknown_ids"):
            _trace_id_list(equation[key], path=f"$trace.equation_set.equations[{index}].{key}")
        for key, value in equation.items():
            if key not in {"source_force_ids", "unknown_ids"}:
                _trace_scalar(value, path=f"$trace.equation_set.equations[{index}].{key}")
    solutions = _exact_items(
        root["solution_candidates"],
        (
            "candidate_id",
            "status",
            "values",
            "check_ids",
            "checks",
            "rejection_count",
            "invalid_numeric_count",
        ),
        path="$trace.solution_candidates",
    )
    for index, solution in enumerate(solutions):
        values = _exact_items(
            solution["values"],
            ("key", "numeric", "unit"),
            path=f"$trace.solution_candidates[{index}].values",
        )
        checks = _exact_items(
            solution["checks"],
            ("check_id", "status"),
            path=f"$trace.solution_candidates[{index}].checks",
        )
        _trace_id_list(solution["check_ids"], path=f"$trace.solution_candidates[{index}].check_ids")
        for value_index, value in enumerate(values):
            for key, item in value.items():
                _trace_scalar(item, path=f"$trace.solution_candidates[{index}].values[{value_index}].{key}")
        for check_index, check in enumerate(checks):
            for key, item in check.items():
                _trace_scalar(item, path=f"$trace.solution_candidates[{index}].checks[{check_index}].{key}")
        for key in ("candidate_id", "status", "rejection_count", "invalid_numeric_count"):
            _trace_scalar(solution[key], path=f"$trace.solution_candidates[{index}].{key}")
    decision = _exact_keys(
        root["validation_decision"],
        (
            "status",
            "selected_candidate_id",
            "valid_alternative_ids",
            "rejected_candidate_ids",
            "selection_policy_id",
            "policy_version",
            "check_ids",
            "error_codes",
            "error_count",
            "warning_count",
            "tolerances",
        ),
        path="$trace.validation_decision",
    )
    if not isinstance(decision["tolerances"], Mapping):
        raise TypeError("$trace.validation_decision.tolerances must be an object")
    for key, value in decision["tolerances"].items():
        _finite(value, field=f"$trace.validation_decision.tolerances.{key}")
    for key in ("valid_alternative_ids", "rejected_candidate_ids", "check_ids", "error_codes"):
        _trace_id_list(decision[key], path=f"$trace.validation_decision.{key}")
    for key, value in decision.items():
        if key not in {"valid_alternative_ids", "rejected_candidate_ids", "check_ids", "error_codes", "tolerances"}:
            _trace_scalar(value, path=f"$trace.validation_decision.{key}")
    numeric_items = _exact_items(
        root["numeric_validations"],
        (
            "check_id",
            "category_id",
            "status",
            "absolute_error",
            "relative_error",
            "tolerance",
            "source_equation_ids",
        ),
        path="$trace.numeric_validations",
    )
    for index, item in enumerate(numeric_items):
        _trace_id_list(item["source_equation_ids"], path=f"$trace.numeric_validations[{index}].source_equation_ids")
        for key, value in item.items():
            if key != "source_equation_ids":
                _trace_scalar(value, path=f"$trace.numeric_validations[{index}].{key}")
    final_answer = _exact_keys(
        root["final_answer"],
        ("ok", "answers"),
        path="$trace.final_answer",
    )
    _trace_scalar(final_answer["ok"], path="$trace.final_answer.ok")
    answer_items = _exact_items(
        final_answer["answers"],
        ("numeric", "unit", "output_key"),
        path="$trace.final_answer.answers",
    )
    for index, answer in enumerate(answer_items):
        for key, value in answer.items():
            _trace_scalar(value, path=f"$trace.final_answer.answers[{index}].{key}")
    stages = _exact_items(
        root["stages"],
        ("name", "status"),
        path="$trace.stages",
    )
    if [item.get("name") for item in stages] != list(STAGES):
        raise ValueError("trace stages must be parse, route, solve, verify in order")
    for index, stage in enumerate(stages):
        for key, value in stage.items():
            _trace_scalar(value, path=f"$trace.stages[{index}].{key}")
    error = root["error"]
    if error is not None:
        error_projection = _exact_keys(error, ("stage", "exception_type"), path="$trace.error")
        for key, value in error_projection.items():
            _trace_scalar(value, path=f"$trace.error.{key}")
    for key in ("schema_version", "trace_version", "request_id", "canonical_fingerprint", "status"):
        _trace_scalar(root[key], path=f"$trace.{key}")
    stable_json_dumps(root, enforce_privacy=True)


def _phase50_values(record: Mapping[str, Any]) -> dict[str, Any]:
    final_state = {
        str(key): {"value": _safe_scalar(value, field=f"phase50.final_state.{key}"), "unit": None}
        for key, value in sorted(_mapping(record.get("final_state")).items())
    }
    analytic = _mapping(record.get("analytic_error"))
    references = {
        str(key): {
            "value": _safe_scalar(value, field=f"phase50.analytic.{key}"),
            "unit": None,
        }
        for key, value in sorted(analytic.items())
        if key in {"reference", "analytic_period", "observed_period", "reference_scale"}
    }
    return {"analytic": references, "scipy": final_state}


def _phase50_errors(record: Mapping[str, Any]) -> dict[str, Any]:
    analytic = _mapping(record.get("analytic_error"))
    return {
        "analytic_vs_scipy": {
            "absolute_error": _optional_finite(
                analytic.get("max_abs_error"), field="phase50.max_abs_error"
            ),
            "relative_error": _optional_finite(
                analytic.get("period_relative_error"), field="phase50.period_relative_error"
            ),
            "absolute_tolerance": _optional_finite(
                analytic.get("comparison_tolerance"), field="phase50.comparison_tolerance"
            ),
            "relative_tolerance": None,
        }
    }


def normalize_phase50_report(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Transform Phase 50 analytic/SciPy records without volatile environment data."""

    normalized: list[dict[str, Any]] = []
    for source in sorted(_list(payload.get("cases")), key=lambda item: str(_mapping(item).get("case_id", ""))):
        record = _mapping(source)
        checks = _mapping(record.get("checks"))
        invariants = []
        policy_checks = {
            "invariant_drift": "energy_policy_passed",
            "constraint_violation": "constraint_policy_passed",
            "analytic_error": "analytic_contract_passed",
        }
        for group_name in ("invariant_drift", "constraint_violation", "analytic_error"):
            group = _mapping(record.get(group_name))
            if group:
                invariants.append(
                    {
                        "check_id": group_name,
                        "passed": bool(checks.get(policy_checks[group_name], False)),
                    }
                )
        status = classify_engine_outcome(record, declared_module="scipy")
        if record.get("errors"):
            status = "error"
        elif record.get("passed") is False:
            status = "disagreement"
        elif record.get("warnings") and status == "passed":
            status = "passed_with_warning"
        case = {
            "case_id": str(record.get("case_id", "")),
            "reference_path": "analytic",
            "candidate_paths": ["scipy"],
            "values_and_units": _phase50_values(record),
            "absolute_relative_errors": _phase50_errors(record),
            "invariant_checks": invariants,
            "assumptions": [
                f"require_{key}={str(value).lower()}"
                for key, value in sorted(_mapping(record.get("requirements")).items())
            ],
            "engine_settings": {
                "scipy": {
                    key: _safe_scalar(
                        _mapping(record.get("integration")).get(key),
                        field=f"phase50.integration.{key}",
                    )
                    for key in ("method", "rtol", "atol", "max_step")
                }
            },
            "runtime": {
                "engine": "scipy",
                "versions": {
                    key: _identifier(_mapping(record.get("runtime_versions")).get(key))
                    for key in ("sympy", "scipy", "numpy")
                },
            },
            "status": status,
        }
        validate_cross_engine_case(case)
        normalized.append(case)
    return normalized


def _comparison_projection(comparison: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "absolute_error": _optional_finite(
            comparison.get("absolute_error"), field="phase51.absolute_error"
        ),
        "relative_error": _optional_finite(
            comparison.get("relative_error"), field="phase51.relative_error"
        ),
        "absolute_tolerance": _optional_finite(
            comparison.get("absolute_tolerance"), field="phase51.absolute_tolerance"
        ),
        "relative_tolerance": _optional_finite(
            comparison.get("relative_tolerance"), field="phase51.relative_tolerance"
        ),
    }


def normalize_phase51_report(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Transform Phase 51 analytic/product/PyChrono records."""

    normalized: list[dict[str, Any]] = []
    for source in sorted(_list(payload.get("cases")), key=lambda item: str(_mapping(item).get("case_id", ""))):
        record = _mapping(source)
        chrono = _mapping(record.get("chrono"))
        product = _mapping(record.get("product"))
        comparisons = _mapping(record.get("comparisons"))
        chrono_status = _trusted_phase51_status(chrono, report=payload)
        product_status = (
            classify_engine_outcome(product)
            if product.get("required", True)
            else "passed"
        )
        status = _worst_status((chrono_status, product_status))
        if record.get("passed") is False and status in {"passed", "passed_with_warning"}:
            status = "disagreement"
        elif record.get("warnings") and status == "passed":
            status = "passed_with_warning"
        values = {
            "analytic": {"value": _optional_finite(record.get("analytic_value"), field="phase51.analytic"), "unit": record.get("unit")},
            "product": {"value": _optional_finite(product.get("value"), field="phase51.product"), "unit": product.get("unit")},
            "pychrono": {"value": _optional_finite(chrono.get("value"), field="phase51.pychrono"), "unit": chrono.get("unit")},
        }
        errors = {
            str(name): _comparison_projection(_mapping(value))
            for name, value in sorted(comparisons.items())
        }
        constraints = _mapping(chrono.get("constraint_errors"))
        invariants = _mapping(chrono.get("invariant_errors"))
        checks = [
            {"check_id": f"constraint:{key}", "passed": bool(_mapping(value).get("passed", value is not False))}
            for key, value in sorted(constraints.items())
        ] + [
            {"check_id": f"invariant:{key}", "passed": bool(_mapping(value).get("passed", value is not False))}
            for key, value in sorted(invariants.items())
        ]
        initial = _mapping(chrono.get("initial_conditions"))
        settings = {
            "time_step": _optional_finite(
                chrono.get("time_step"), field="phase51.time_step"
            ),
            "solver": _identifier(chrono.get("solver")),
            "contact_method": _identifier(chrono.get("contact_method")),
        }
        for key in (
            "time_step_s",
            "solver_max_iterations",
            "collision_envelope_m",
            "collision_safe_margin_m",
        ):
            if key in initial:
                settings[key] = _safe_scalar(
                    initial[key], field=f"phase51.initial_conditions.{key}"
                )
        runtime_version = chrono.get("chrono_version")
        if chrono_status == "skipped":
            runtime_version = None
        elif runtime_version in {None, "unknown", "unavailable"}:
            env_versions = _list(_mapping(payload.get("environment")).get("chrono_versions"))
            runtime_version = env_versions[0] if len(env_versions) == 1 else None
        case = {
            "case_id": str(record.get("case_id", "")),
            "reference_path": "analytic",
            "candidate_paths": ["product", "pychrono"],
            "values_and_units": values,
            "absolute_relative_errors": errors,
            "invariant_checks": checks,
            "assumptions": sorted(
                str(item) for item in _list(chrono.get("modeling_assumptions"))
            ),
            "engine_settings": {"pychrono": settings},
            "runtime": {"engine": "pychrono", "version": _identifier(runtime_version)},
            "status": status,
        }
        validate_cross_engine_case(case)
        normalized.append(case)
    return normalized


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("at least one performance sample is required")
    ordered = sorted(_finite(value, field="performance sample") for value in values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _statistics(values: Sequence[float]) -> dict[str, float | int]:
    finite = [_finite(value, field="performance sample") for value in values]
    if not finite:
        raise ValueError("at least one performance sample is required")
    return {
        "sample_count": len(finite),
        "p50_ms": _nearest_rank(finite, 0.50),
        "p95_ms": _nearest_rank(finite, 0.95),
        "worst_ms": max(finite),
    }


def build_performance_artifact(
    *,
    source_commit: str,
    tier: str,
    case_samples: Mapping[str, Sequence[Mapping[str, Any]]],
    repeats: int,
) -> StableSnapshot:
    if tier not in TIERS:
        raise ValueError(f"unsupported tier: {tier}")
    build_version_evidence(source_commit=source_commit)
    if repeats < 1:
        raise ValueError("repeats must be positive")
    cases: list[dict[str, Any]] = []
    all_end_to_end: list[float] = []
    all_stage_samples: dict[str, list[float]] = {stage: [] for stage in STAGES}
    for case_id in sorted(case_samples):
        samples = list(case_samples[case_id])
        if len(samples) != repeats:
            raise ValueError(f"{case_id} requires exactly {repeats} samples")
        stage_samples: dict[str, list[float]] = {stage: [] for stage in STAGES}
        end_to_end: list[float] = []
        for sample in samples:
            current = _mapping(sample)
            for stage in STAGES:
                value = _finite(current.get(stage), field=f"{case_id}.{stage}")
                if value < 0:
                    raise ValueError("performance durations may not be negative")
                stage_samples[stage].append(value)
                all_stage_samples[stage].append(value)
            stage_total = sum(stage_samples[stage][-1] for stage in STAGES)
            total = _optional_finite(current.get("end_to_end"), field=f"{case_id}.end_to_end")
            if total is None:
                total = stage_total
            elif total != stage_total:
                raise ValueError(
                    f"{case_id}.end_to_end must equal the same-sample stage sum"
                )
            if total < 0:
                raise ValueError("end-to-end duration may not be negative")
            end_to_end.append(total)
            all_end_to_end.append(total)
        cases.append(
            {
                "case_id": case_id,
                "stage_samples_ms": stage_samples,
                "stage_statistics": {
                    stage: _statistics(stage_samples[stage]) for stage in STAGES
                },
                "end_to_end_samples_ms": end_to_end,
                "end_to_end_statistics": _statistics(end_to_end),
            }
        )
    if not cases:
        raise ValueError("performance artifact requires at least one case")
    mean = sum(all_end_to_end) / len(all_end_to_end)
    overall = {
        "sample_count": len(all_end_to_end),
        "mean_ms": mean,
        "p50_ms": _nearest_rank(all_end_to_end, 0.50),
        "p95_ms": _nearest_rank(all_end_to_end, 0.95),
        "worst_ms": max(all_end_to_end),
        "stage_statistics": {
            stage: _statistics(all_stage_samples[stage]) for stage in STAGES
        },
    }
    payload = {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "performance_version": PERFORMANCE_VERSION,
        "source_commit": source_commit.lower(),
        "tier": tier,
        "fixed_repeats": repeats,
        "case_ids": sorted(case_samples),
        "cases": cases,
        "overall": overall,
        "baseline": {"phase42_mean_ms": PHASE42_MEAN_MS, "phase42_p95_ms": PHASE42_P95_MS},
        "absolute_ceilings": {"mean_ms": ABSOLUTE_MEAN_CEILING_MS, "p95_ms": ABSOLUTE_P95_CEILING_MS},
    }
    validate_performance(payload)
    return StableSnapshot.from_payload(payload, enforce_privacy=True)


def dashboard_sources_from_routing_report(
    payload: Mapping[str, Any],
    *,
    golden_passed: int,
    golden_total: int,
    residual_invariant_failures: int,
) -> dict[str, Any]:
    routing = _mapping(payload.get("routing"))
    numeric = _mapping(payload.get("numeric"))
    negative = _mapping(payload.get("negative"))
    clarify = _mapping(payload.get("clarify"))
    false_positive_count = len(_list(negative.get("false_positives")))
    negative_total = int(negative.get("checked", 0))
    crafted_total = len(_list(clarify.get("crafted")))
    crafted_fired = int(clarify.get("crafted_fired", 0))
    crafted_rule_ok = int(clarify.get("crafted_rule_ok", 0))
    clarify_fp = len(_list(clarify.get("fp")))
    precision_denominator = crafted_rule_ok + clarify_fp
    return {
        "golden": {"passed": int(golden_passed), "total": int(golden_total)},
        "false_solve": {"false": false_positive_count, "total": negative_total},
        "clarification": {
            "true_positive": crafted_rule_ok,
            "false_positive": clarify_fp,
            "fired": crafted_fired,
            "total": crafted_total,
            "precision_denominator": precision_denominator,
        },
        "routing": {"correct": int(routing.get("correct", 0)), "total": int(routing.get("total", 0))},
        "residual_invariant_failures": int(residual_invariant_failures),
        "numeric_checked": int(numeric.get("checked", 0)),
    }


def build_cross_engine_core(
    *,
    source_commit: str,
    tier: str,
    traces: Sequence[Mapping[str, Any]],
    phase50_payload: Mapping[str, Any] | None,
    phase51_payload: Mapping[str, Any] | None,
    dashboard_sources: Mapping[str, Any],
    runtime_versions: Mapping[str, Any] | None = None,
    llm_identifier: str | None = None,
) -> StableSnapshot:
    if tier not in TIERS:
        raise ValueError(f"unsupported tier: {tier}")
    versions = build_version_evidence(
        source_commit=source_commit,
        runtime_versions=runtime_versions,
        llm_identifier=llm_identifier,
    )
    cases = normalize_phase50_report(phase50_payload or {})
    cases.extend(normalize_phase51_report(phase51_payload or {}))
    cases.sort(key=lambda item: (item["case_id"], item["runtime"]["engine"]))
    for case in cases:
        validate_cross_engine_case(case)
    projected_traces = [dict(trace) for trace in traces]
    for trace in projected_traces:
        validate_trace_snapshot(trace)
    payload = {
        "schema_version": CROSS_ENGINE_REPORT_SCHEMA_VERSION,
        "report_version": CROSS_ENGINE_REPORT_VERSION,
        "source_commit": source_commit.lower(),
        "tier": tier,
        "versions": versions,
        "traces": sorted(
            projected_traces, key=lambda item: str(item.get("request_id", ""))
        ),
        "cross_engine_cases": cases,
        "dashboard_sources": dict(dashboard_sources),
        "expected_skip_policy": [
            {"tier": item[0], "engine": item[1], "case_id": item[2]}
            for item in EXPECTED_SKIP_MANIFEST
        ],
    }
    validate_core(payload)
    return StableSnapshot.from_payload(payload, enforce_privacy=True)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def build_dashboard(
    *,
    core: Mapping[str, Any],
    performance: Mapping[str, Any],
    flaky_test_count: int,
) -> list[dict[str, Any]]:
    sources = _mapping(core.get("dashboard_sources"))
    golden = _mapping(sources.get("golden"))
    false_solve = _mapping(sources.get("false_solve"))
    clarify = _mapping(sources.get("clarification"))
    routing = _mapping(sources.get("routing"))
    cases = _list(core.get("cross_engine_cases"))
    overall = _mapping(performance.get("overall"))
    metrics = [
        {"metric_id": "golden_answer_pass_rate", "value": _ratio(int(golden.get("passed", 0)), int(golden.get("total", 0))), "evidence": golden},
        {"metric_id": "false_solve_rate", "value": _ratio(int(false_solve.get("false", 0)), int(false_solve.get("total", 0))), "evidence": false_solve},
        {
            "metric_id": "clarification_precision_recall",
            "value": {
                "precision": _ratio(int(clarify.get("true_positive", 0)), int(clarify.get("precision_denominator", 0))),
                "recall": _ratio(int(clarify.get("fired", 0)), int(clarify.get("total", 0))),
            },
            "evidence": clarify,
        },
        {"metric_id": "routing_accuracy", "value": _ratio(int(routing.get("correct", 0)), int(routing.get("total", 0))), "evidence": routing},
        {"metric_id": "residual_invariant_failure_count", "value": int(sources.get("residual_invariant_failures", 0)), "evidence": {"source": "normalized invariant checks"}},
        {"metric_id": "cross_engine_disagreement_count", "value": sum(_mapping(case).get("status") == "disagreement" for case in cases), "evidence": {"case_count": len(cases)}},
        {"metric_id": "p95_fast_path_latency_ms", "value": _finite(overall.get("p95_ms"), field="performance.overall.p95_ms"), "evidence": {"sample_count": int(overall.get("sample_count", 0))}},
        {"metric_id": "flaky_test_count", "value": int(flaky_test_count), "evidence": {"scope": "current_run_only"}},
    ]
    if tuple(metric["metric_id"] for metric in metrics) != DASHBOARD_METRIC_IDS:
        raise AssertionError("dashboard metric contract changed")
    stable_json_dumps(metrics)
    return metrics


def _release_gate_from_summary(
    *,
    tier: str,
    cases: Sequence[Mapping[str, Any]],
    mean: float,
    p95: float,
    pooled_performance_gate: str,
    strict: bool,
) -> dict[str, Any]:
    if pooled_performance_gate not in {"passed", "failed", "inconclusive"}:
        raise ValueError("pooled_performance_gate must be passed, failed, or inconclusive")
    reasons: list[str] = []
    for case in cases:
        status = str(case.get("status"))
        engine = str(_mapping(case.get("runtime")).get("engine", ""))
        case_id = str(case.get("case_id", ""))
        if status == "skipped" and is_expected_skip(tier=tier, engine=engine, case_id=case_id):
            continue
        if status in {"error", "disagreement", "unsupported", "skipped"}:
            reasons.append(f"cross_engine:{engine}:{case_id}:{status}")
    if strict and tier == "nightly":
        expected_by_engine = {
            "scipy": PHASE50_CASE_IDS,
            "pychrono": PHASE51_CASE_IDS,
        }
        pair_counts: dict[tuple[str, str], int] = {}
        pair_statuses: dict[tuple[str, str], list[str]] = {}
        for case in cases:
            pair = (
                str(_mapping(case.get("runtime")).get("engine", "")),
                str(case.get("case_id", "")),
            )
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
            pair_statuses.setdefault(pair, []).append(str(case.get("status", "")))
        for (engine, case_id), count in sorted(pair_counts.items()):
            if count != 1:
                reasons.append(f"nightly_duplicate_case:{engine}:{case_id}:{count}")
            if engine not in expected_by_engine:
                reasons.append(f"nightly_unexpected_engine:{engine}:{case_id}")
        for engine, expected_ids in expected_by_engine.items():
            actual_ids = {
                case_id
                for (actual_engine, case_id), _count in pair_counts.items()
                if actual_engine == engine
            }
            missing = sorted(expected_ids - actual_ids)
            extra = sorted(actual_ids - expected_ids)
            if missing:
                reasons.append(f"nightly_missing_cases:{engine}:{','.join(missing)}")
            if extra:
                reasons.append(f"nightly_extra_cases:{engine}:{','.join(extra)}")
            for case_id in sorted(expected_ids):
                statuses = pair_statuses.get((engine, case_id), [])
                if len(statuses) == 1 and statuses[0] not in {
                    "passed",
                    "passed_with_warning",
                }:
                    reasons.append(
                        f"nightly_required_status:{engine}:{case_id}:{statuses[0]}"
                    )
    if mean > ABSOLUTE_MEAN_CEILING_MS:
        reasons.append(f"absolute_mean_ms:{mean}>{ABSOLUTE_MEAN_CEILING_MS}")
    if p95 > ABSOLUTE_P95_CEILING_MS:
        reasons.append(f"absolute_p95_ms:{p95}>{ABSOLUTE_P95_CEILING_MS}")
    if pooled_performance_gate != "passed":
        reasons.append(f"external_pooled_parent_head_gate:{pooled_performance_gate}")
    verdict = "passed" if not reasons else ("inconclusive" if reasons == ["external_pooled_parent_head_gate:inconclusive"] else "failed")
    return {
        "verdict": verdict,
        "reasons": reasons,
        "absolute_performance": {"mean_ms": mean, "p95_ms": p95, "mean_ceiling_ms": ABSOLUTE_MEAN_CEILING_MS, "p95_ceiling_ms": ABSOLUTE_P95_CEILING_MS},
        "external_pooled_parent_head_gate": {"status": pooled_performance_gate, "maximum_regression_percent": 15.0, "evidence_owner": "existing Release exact-HEAD workflow"},
    }


def evaluate_release_gate(
    *,
    core: Mapping[str, Any],
    performance: Mapping[str, Any],
    pooled_performance_gate: str,
    strict: bool,
) -> dict[str, Any]:
    validate_performance(performance)
    overall = _mapping(performance.get("overall"))
    return _release_gate_from_summary(
        tier=str(core.get("tier")),
        cases=[_mapping(case) for case in _list(core.get("cross_engine_cases"))],
        mean=_finite(overall.get("mean_ms"), field="performance.overall.mean_ms"),
        p95=_finite(overall.get("p95_ms"), field="performance.overall.p95_ms"),
        pooled_performance_gate=pooled_performance_gate,
        strict=strict,
    )


def build_final_report(
    *,
    core: Mapping[str, Any],
    performance: Mapping[str, Any],
    performance_filename: str,
    performance_content: str,
    pooled_performance_gate: str,
    flaky_test_count: int,
    strict: bool,
) -> dict[str, Any]:
    validate_core(core)
    validate_performance(performance)
    if core.get("source_commit") != performance.get("source_commit"):
        raise ValueError("core and performance source commits differ")
    if core.get("tier") != performance.get("tier"):
        raise ValueError("core and performance tiers differ")
    if not performance_content.endswith("\n"):
        raise ValueError("performance artifact must be newline-normalized")
    parsed_performance = stable_json_dumps(performance)
    if performance_content != parsed_performance + "\n":
        raise ValueError("performance artifact content is not canonical or was tampered")
    artifact_filename = Path(performance_filename).name
    if not artifact_filename:
        raise ValueError("performance artifact filename is required")
    artifact = {
        "filename": artifact_filename,
        "schema_version": performance.get("schema_version"),
        "content_sha256": sha256_text(performance_content),
    }
    dashboard = build_dashboard(core=core, performance=performance, flaky_test_count=flaky_test_count)
    gate = evaluate_release_gate(
        core=core,
        performance=performance,
        pooled_performance_gate=pooled_performance_gate,
        strict=strict,
    )
    report = {
        "schema_version": CROSS_ENGINE_REPORT_SCHEMA_VERSION,
        "report_version": CROSS_ENGINE_REPORT_VERSION,
        "source_commit": core["source_commit"],
        "tier": core["tier"],
        "versions": core["versions"],
        "cross_engine_cases": core["cross_engine_cases"],
        "status_counts": {status: sum(_mapping(case).get("status") == status for case in _list(core.get("cross_engine_cases"))) for status in STATUS_VALUES},
        "trace_count": len(_list(core.get("traces"))),
        "deterministic_checks": {"core_contains_timing": False, "render_uses_immutable_inputs": True},
        "performance": {"baseline": performance["baseline"], "absolute_ceilings": performance["absolute_ceilings"], "overall": performance["overall"], "artifact": artifact},
        "dashboard": dashboard,
        "expected_skip_policy": core["expected_skip_policy"],
        "release_gate": gate,
    }
    stable_json_dumps(report)
    return report


def render_final_json(report: Mapping[str, Any]) -> str:
    return stable_json_dumps(report) + "\n"


def render_final_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 52 cross-engine observability report",
        "",
        f"- Source commit: `{report['source_commit']}`",
        f"- Tier: `{report['tier']}`",
        f"- Report version: `{report['report_version']}`",
        f"- Gate verdict: **{_mapping(report['release_gate']).get('verdict')}**",
        "",
        "## Versions",
        "",
    ]
    for key, value in sorted(_mapping(report.get("versions")).items()):
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Cross-engine cases", "", "| Case | Reference | Candidates | Engine | Status |", "|---|---|---|---|---|"])
    for case in _list(report.get("cross_engine_cases")):
        item = _mapping(case)
        lines.append(f"| {item.get('case_id')} | {item.get('reference_path')} | {', '.join(_list(item.get('candidate_paths')))} | {_mapping(item.get('runtime')).get('engine')} | {item.get('status')} |")
    lines.extend(["", "## Release dashboard", ""])
    for metric in _list(report.get("dashboard")):
        item = _mapping(metric)
        lines.append(f"- {item.get('metric_id')}: `{stable_json_dumps(item.get('value'))}` (evidence: `{stable_json_dumps(item.get('evidence'))}`)")
    performance = _mapping(report.get("performance"))
    artifact = _mapping(performance.get("artifact"))
    overall = _mapping(performance.get("overall"))
    ceilings = _mapping(performance.get("absolute_ceilings"))
    baseline = _mapping(performance.get("baseline"))
    lines.extend([
        "", "## Performance evidence", "",
        f"- Phase 42 historical mean/P95: `{baseline.get('phase42_mean_ms')} / {baseline.get('phase42_p95_ms')} ms`",
        f"- Current mean/P50/P95/worst: `{overall.get('mean_ms')} / {overall.get('p50_ms')} / {overall.get('p95_ms')} / {overall.get('worst_ms')} ms`",
        f"- Absolute mean/P95 ceilings: `{ceilings.get('mean_ms')} / {ceilings.get('p95_ms')} ms`",
        f"- Artifact: `{artifact.get('filename')}` schema `{artifact.get('schema_version')}` SHA256 `{artifact.get('content_sha256')}`",
        "", "## Gate", "",
    ])
    gate = _mapping(report.get("release_gate"))
    lines.append(f"- Verdict: `{gate.get('verdict')}`")
    for reason in _list(gate.get("reasons")):
        lines.append(f"- Reason: `{reason}`")
    lines.append(f"- External pooled parent-vs-head gate: `{stable_json_dumps(gate.get('external_pooled_parent_head_gate'))}`")
    lines.extend(["", "## Expected skips", ""])
    for item in _list(report.get("expected_skip_policy")):
        lines.append(f"- `{stable_json_dumps(item)}`")
    lines.extend(["", "The deterministic core contains no timing, timestamp, random value, or raw user/student text. Stage timings live only in the referenced performance artifact.", ""])
    return "\n".join(lines)


def _validate_dashboard_sources(value: Any, *, path: str) -> None:
    root = _exact_keys(
        value,
        (
            "golden",
            "false_solve",
            "clarification",
            "routing",
            "residual_invariant_failures",
            "numeric_checked",
        ),
        path=path,
    )
    groups = (
        ("golden", ("passed", "total")),
        ("false_solve", ("false", "total")),
        (
            "clarification",
            (
                "true_positive",
                "false_positive",
                "fired",
                "total",
                "precision_denominator",
            ),
        ),
        ("routing", ("correct", "total")),
    )
    for group_name, fields in groups:
        group = _exact_keys(root[group_name], fields, path=f"{path}.{group_name}")
        for field, count in group.items():
            _nonnegative_integer(count, field=f"{path}.{group_name}.{field}")
    for field in ("residual_invariant_failures", "numeric_checked"):
        _nonnegative_integer(root[field], field=f"{path}.{field}")


def _validate_expected_skip_policy(value: Any, *, path: str) -> None:
    items = _exact_items(value, ("tier", "engine", "case_id"), path=path)
    expected = [
        {"tier": tier, "engine": engine, "case_id": case_id}
        for tier, engine, case_id in EXPECTED_SKIP_MANIFEST
    ]
    if [dict(item) for item in items] != expected:
        raise ValueError(f"{path} does not match the code-owned expected skip policy")


def validate_core(core: Mapping[str, Any]) -> None:
    root = _exact_keys(core, CORE_FIELDS, path="$core")
    if root["schema_version"] != CROSS_ENGINE_REPORT_SCHEMA_VERSION:
        raise ValueError("invalid core schema version")
    if root["report_version"] != CROSS_ENGINE_REPORT_VERSION:
        raise ValueError("invalid core report version")
    source_commit = _source_commit(root["source_commit"], field="core.source_commit")
    _validate_versions(root["versions"], source_commit=source_commit, path="$core.versions")
    if root["tier"] not in TIERS:
        raise ValueError("invalid core tier")
    if not isinstance(root["traces"], list):
        raise TypeError("core traces must be a list")
    for trace in root["traces"]:
        validate_trace_snapshot(trace)
    if not isinstance(root["cross_engine_cases"], list):
        raise TypeError("core cross_engine_cases must be a list")
    for case in root["cross_engine_cases"]:
        validate_cross_engine_case(case)
    _validate_dashboard_sources(root["dashboard_sources"], path="$core.dashboard_sources")
    _validate_expected_skip_policy(root["expected_skip_policy"], path="$core.expected_skip_policy")
    rendered = stable_json_dumps(root, enforce_privacy=True)
    for forbidden in ("duration", "timing", "timestamp", "random"):
        if f'"{forbidden}' in rendered.casefold():
            raise ValueError(f"deterministic core contains volatile field: {forbidden}")


def validate_performance(performance: Mapping[str, Any]) -> None:
    root = _exact_keys(
        performance,
        (
            "schema_version",
            "performance_version",
            "source_commit",
            "tier",
            "fixed_repeats",
            "case_ids",
            "cases",
            "overall",
            "baseline",
            "absolute_ceilings",
        ),
        path="$performance",
    )
    if root.get("schema_version") != PERFORMANCE_SCHEMA_VERSION:
        raise ValueError("invalid performance schema version")
    if root.get("performance_version") != PERFORMANCE_VERSION:
        raise ValueError("invalid performance version")
    if root.get("tier") not in TIERS:
        raise ValueError("invalid performance tier")
    _source_commit(root["source_commit"], field="performance.source_commit")
    stable_json_dumps(root, enforce_privacy=True)
    repeats = root.get("fixed_repeats")
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
        raise ValueError("fixed_repeats must be a positive integer")
    case_ids = root.get("case_ids")
    if not isinstance(case_ids, list) or not all(isinstance(item, str) and item for item in case_ids):
        raise TypeError("performance case_ids must be non-empty strings")
    if case_ids != sorted(set(case_ids)):
        raise ValueError("performance case_ids must be sorted and unique")
    cases = _exact_items(
        root["cases"],
        (
            "case_id",
            "stage_samples_ms",
            "stage_statistics",
            "end_to_end_samples_ms",
            "end_to_end_statistics",
        ),
        path="$performance.cases",
    )
    if [case.get("case_id") for case in cases] != case_ids:
        raise ValueError("performance cases must exactly match ordered case_ids")
    all_stage_samples: dict[str, list[float]] = {stage: [] for stage in STAGES}
    all_end_to_end: list[float] = []
    for case_index, case in enumerate(cases):
        case_id = str(case["case_id"])
        stage_samples = _exact_keys(
            case["stage_samples_ms"], STAGES, path=f"$performance.cases[{case_index}].stage_samples_ms"
        )
        stage_statistics = _exact_keys(
            case["stage_statistics"], STAGES, path=f"$performance.cases[{case_index}].stage_statistics"
        )
        case_stage_samples: dict[str, list[float]] = {}
        for stage in STAGES:
            samples = stage_samples[stage]
            if not isinstance(samples, list) or len(samples) != repeats:
                raise ValueError(f"{case_id}.{stage} must contain exactly fixed_repeats samples")
            finite_samples = [_finite(item, field=f"{case_id}.{stage}") for item in samples]
            if any(item < 0 for item in finite_samples):
                raise ValueError("performance durations may not be negative")
            expected_stats = _statistics(finite_samples)
            actual_stats = _exact_keys(
                stage_statistics[stage],
                ("sample_count", "p50_ms", "p95_ms", "worst_ms"),
                path=f"$performance.cases[{case_index}].stage_statistics.{stage}",
            )
            if dict(actual_stats) != expected_stats:
                raise ValueError(f"{case_id}.{stage} statistics do not match raw samples")
            case_stage_samples[stage] = finite_samples
            all_stage_samples[stage].extend(finite_samples)
        end_samples = case["end_to_end_samples_ms"]
        if not isinstance(end_samples, list) or len(end_samples) != repeats:
            raise ValueError(f"{case_id}.end_to_end must contain exactly fixed_repeats samples")
        finite_end = [_finite(item, field=f"{case_id}.end_to_end") for item in end_samples]
        if any(item < 0 for item in finite_end):
            raise ValueError("end-to-end durations may not be negative")
        for sample_index, actual_total in enumerate(finite_end):
            stage_total = sum(
                case_stage_samples[stage][sample_index] for stage in STAGES
            )
            if actual_total != stage_total:
                raise ValueError(
                    f"{case_id}.end_to_end sample {sample_index} does not equal "
                    "the same-sample stage sum"
                )
        actual_end_stats = _exact_keys(
            case["end_to_end_statistics"],
            ("sample_count", "p50_ms", "p95_ms", "worst_ms"),
            path=f"$performance.cases[{case_index}].end_to_end_statistics",
        )
        if dict(actual_end_stats) != _statistics(finite_end):
            raise ValueError(f"{case_id}.end_to_end statistics do not match raw samples")
        all_end_to_end.extend(finite_end)
    if not all_end_to_end:
        raise ValueError("performance artifact requires samples")
    expected_overall = {
        "sample_count": len(all_end_to_end),
        "mean_ms": sum(all_end_to_end) / len(all_end_to_end),
        "p50_ms": _nearest_rank(all_end_to_end, 0.50),
        "p95_ms": _nearest_rank(all_end_to_end, 0.95),
        "worst_ms": max(all_end_to_end),
        "stage_statistics": {
            stage: _statistics(all_stage_samples[stage]) for stage in STAGES
        },
    }
    overall = _exact_keys(
        root["overall"],
        ("sample_count", "mean_ms", "p50_ms", "p95_ms", "worst_ms", "stage_statistics"),
        path="$performance.overall",
    )
    overall_stage = _exact_keys(
        overall["stage_statistics"], STAGES, path="$performance.overall.stage_statistics"
    )
    for stage in STAGES:
        _exact_keys(
            overall_stage[stage],
            ("sample_count", "p50_ms", "p95_ms", "worst_ms"),
            path=f"$performance.overall.stage_statistics.{stage}",
        )
    if dict(overall) != expected_overall:
        raise ValueError("overall performance statistics do not match raw samples")
    baseline = _exact_keys(
        root["baseline"],
        ("phase42_mean_ms", "phase42_p95_ms"),
        path="$performance.baseline",
    )
    if dict(baseline) != {
        "phase42_mean_ms": PHASE42_MEAN_MS,
        "phase42_p95_ms": PHASE42_P95_MS,
    }:
        raise ValueError("Phase 42 performance baseline was altered")
    ceilings = _exact_keys(
        root["absolute_ceilings"],
        ("mean_ms", "p95_ms"),
        path="$performance.absolute_ceilings",
    )
    if dict(ceilings) != {
        "mean_ms": ABSOLUTE_MEAN_CEILING_MS,
        "p95_ms": ABSOLUTE_P95_CEILING_MS,
    }:
        raise ValueError("absolute performance ceilings were altered")


def _validate_summary_statistics(value: Any, *, path: str) -> Mapping[str, Any]:
    statistics = _exact_keys(
        value,
        ("sample_count", "p50_ms", "p95_ms", "worst_ms"),
        path=path,
    )
    _nonnegative_integer(statistics["sample_count"], field=f"{path}.sample_count")
    for field in ("p50_ms", "p95_ms", "worst_ms"):
        _nonnegative_number(statistics[field], field=f"{path}.{field}")
    if not statistics["p50_ms"] <= statistics["p95_ms"] <= statistics["worst_ms"]:
        raise ValueError(f"{path} percentiles are inconsistent")
    return statistics


def _validate_final_performance(value: Any) -> Mapping[str, Any]:
    performance = _exact_keys(
        value,
        ("baseline", "absolute_ceilings", "overall", "artifact"),
        path="$report.performance",
    )
    baseline = _exact_keys(
        performance["baseline"],
        ("phase42_mean_ms", "phase42_p95_ms"),
        path="$report.performance.baseline",
    )
    if dict(baseline) != {
        "phase42_mean_ms": PHASE42_MEAN_MS,
        "phase42_p95_ms": PHASE42_P95_MS,
    }:
        raise ValueError("Phase 42 performance baseline was altered")
    ceilings = _exact_keys(
        performance["absolute_ceilings"],
        ("mean_ms", "p95_ms"),
        path="$report.performance.absolute_ceilings",
    )
    if dict(ceilings) != {
        "mean_ms": ABSOLUTE_MEAN_CEILING_MS,
        "p95_ms": ABSOLUTE_P95_CEILING_MS,
    }:
        raise ValueError("absolute performance ceilings were altered")
    overall = _exact_keys(
        performance["overall"],
        ("sample_count", "mean_ms", "p50_ms", "p95_ms", "worst_ms", "stage_statistics"),
        path="$report.performance.overall",
    )
    sample_count = _nonnegative_integer(
        overall["sample_count"], field="$report.performance.overall.sample_count"
    )
    if sample_count < 1:
        raise ValueError("final performance summary requires samples")
    for field in ("mean_ms", "p50_ms", "p95_ms", "worst_ms"):
        _nonnegative_number(overall[field], field=f"$report.performance.overall.{field}")
    if not overall["p50_ms"] <= overall["p95_ms"] <= overall["worst_ms"]:
        raise ValueError("final performance percentiles are inconsistent")
    if overall["mean_ms"] > overall["worst_ms"]:
        raise ValueError("final performance mean exceeds the worst sample")
    stage_statistics = _exact_keys(
        overall["stage_statistics"],
        STAGES,
        path="$report.performance.overall.stage_statistics",
    )
    for stage in STAGES:
        stage_summary = _validate_summary_statistics(
            stage_statistics[stage],
            path=f"$report.performance.overall.stage_statistics.{stage}",
        )
        if stage_summary["sample_count"] != sample_count:
            raise ValueError("final performance stage sample_count differs from overall")
    artifact = _exact_keys(
        performance["artifact"],
        ("filename", "schema_version", "content_sha256"),
        path="$report.performance.artifact",
    )
    filename = artifact["filename"]
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        raise ValueError("performance artifact filename must be a basename")
    if artifact["schema_version"] != PERFORMANCE_SCHEMA_VERSION:
        raise ValueError("performance artifact schema version mismatch")
    digest = artifact["content_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("performance artifact digest must be a lowercase SHA256")
    return overall


def _dashboard_counts(value: Any, fields: Iterable[str], *, path: str) -> Mapping[str, Any]:
    counts = _exact_keys(value, fields, path=path)
    for field, count in counts.items():
        _nonnegative_integer(count, field=f"{path}.{field}")
    return counts


def _validate_final_dashboard(
    value: Any,
    *,
    cases: Sequence[Mapping[str, Any]],
    performance_overall: Mapping[str, Any],
) -> None:
    metrics = _exact_items(
        value,
        ("metric_id", "value", "evidence"),
        path="$report.dashboard",
    )
    if tuple(metric["metric_id"] for metric in metrics) != DASHBOARD_METRIC_IDS:
        raise ValueError("dashboard must contain the exact eight metrics")

    golden = _dashboard_counts(
        metrics[0]["evidence"], ("passed", "total"), path="$report.dashboard[0].evidence"
    )
    if metrics[0]["value"] != _ratio(golden["passed"], golden["total"]):
        raise ValueError("golden answer dashboard value differs from evidence")
    false_solve = _dashboard_counts(
        metrics[1]["evidence"], ("false", "total"), path="$report.dashboard[1].evidence"
    )
    if metrics[1]["value"] != _ratio(false_solve["false"], false_solve["total"]):
        raise ValueError("false solve dashboard value differs from evidence")
    clarification = _dashboard_counts(
        metrics[2]["evidence"],
        ("true_positive", "false_positive", "fired", "total", "precision_denominator"),
        path="$report.dashboard[2].evidence",
    )
    clarification_value = _exact_keys(
        metrics[2]["value"],
        ("precision", "recall"),
        path="$report.dashboard[2].value",
    )
    expected_clarification = {
        "precision": _ratio(
            clarification["true_positive"], clarification["precision_denominator"]
        ),
        "recall": _ratio(clarification["fired"], clarification["total"]),
    }
    if dict(clarification_value) != expected_clarification:
        raise ValueError("clarification dashboard value differs from evidence")
    routing = _dashboard_counts(
        metrics[3]["evidence"], ("correct", "total"), path="$report.dashboard[3].evidence"
    )
    if metrics[3]["value"] != _ratio(routing["correct"], routing["total"]):
        raise ValueError("routing dashboard value differs from evidence")
    residual_evidence = _exact_keys(
        metrics[4]["evidence"], ("source",), path="$report.dashboard[4].evidence"
    )
    if dict(residual_evidence) != {"source": "normalized invariant checks"}:
        raise ValueError("residual invariant dashboard evidence was altered")
    _nonnegative_integer(metrics[4]["value"], field="$report.dashboard[4].value")
    disagreement_evidence = _dashboard_counts(
        metrics[5]["evidence"], ("case_count",), path="$report.dashboard[5].evidence"
    )
    if disagreement_evidence["case_count"] != len(cases):
        raise ValueError("cross-engine dashboard case_count differs from cases")
    if metrics[5]["value"] != sum(case["status"] == "disagreement" for case in cases):
        raise ValueError("cross-engine disagreement dashboard value differs from cases")
    latency_evidence = _dashboard_counts(
        metrics[6]["evidence"], ("sample_count",), path="$report.dashboard[6].evidence"
    )
    if latency_evidence["sample_count"] != performance_overall["sample_count"]:
        raise ValueError("latency dashboard sample_count differs from performance")
    if metrics[6]["value"] != performance_overall["p95_ms"]:
        raise ValueError("latency dashboard value differs from performance")
    flaky_evidence = _exact_keys(
        metrics[7]["evidence"], ("scope",), path="$report.dashboard[7].evidence"
    )
    if dict(flaky_evidence) != {"scope": "current_run_only"}:
        raise ValueError("flaky-test dashboard evidence was altered")
    _nonnegative_integer(metrics[7]["value"], field="$report.dashboard[7].value")


def validate_final_report(report: Mapping[str, Any], *, strict: bool) -> None:
    root = _exact_keys(
        report,
        (
            "schema_version",
            "report_version",
            "source_commit",
            "tier",
            "versions",
            "cross_engine_cases",
            "status_counts",
            "trace_count",
            "deterministic_checks",
            "performance",
            "dashboard",
            "expected_skip_policy",
            "release_gate",
        ),
        path="$report",
    )
    if root["schema_version"] != CROSS_ENGINE_REPORT_SCHEMA_VERSION:
        raise ValueError("invalid final report schema version")
    if root["report_version"] != CROSS_ENGINE_REPORT_VERSION:
        raise ValueError("invalid final report version")
    source_commit = _source_commit(root["source_commit"], field="report.source_commit")
    if root["tier"] not in TIERS:
        raise ValueError("invalid final report tier")
    _validate_versions(root["versions"], source_commit=source_commit, path="$report.versions")
    if not isinstance(root["cross_engine_cases"], list):
        raise TypeError("final report cross_engine_cases must be a list")
    cases = root["cross_engine_cases"]
    for case in cases:
        validate_cross_engine_case(case)
    status_counts = _exact_keys(root["status_counts"], STATUS_VALUES, path="$report.status_counts")
    expected_counts = {
        status: sum(case["status"] == status for case in cases)
        for status in STATUS_VALUES
    }
    for status, count in status_counts.items():
        _nonnegative_integer(count, field=f"$report.status_counts.{status}")
    if dict(status_counts) != expected_counts:
        raise ValueError("final report status_counts differ from cross-engine cases")
    _nonnegative_integer(root["trace_count"], field="$report.trace_count")
    deterministic_checks = _exact_keys(
        root["deterministic_checks"],
        ("core_contains_timing", "render_uses_immutable_inputs"),
        path="$report.deterministic_checks",
    )
    if dict(deterministic_checks) != {
        "core_contains_timing": False,
        "render_uses_immutable_inputs": True,
    }:
        raise ValueError("deterministic checks differ from the code-owned contract")
    performance_overall = _validate_final_performance(root["performance"])
    _validate_final_dashboard(
        root["dashboard"], cases=cases, performance_overall=performance_overall
    )
    _validate_expected_skip_policy(root["expected_skip_policy"], path="$report.expected_skip_policy")
    gate = _exact_keys(
        root["release_gate"],
        ("verdict", "reasons", "absolute_performance", "external_pooled_parent_head_gate"),
        path="$report.release_gate",
    )
    if not isinstance(gate["reasons"], list) or not all(
        isinstance(reason, str) for reason in gate["reasons"]
    ):
        raise TypeError("release gate reasons must be a list of strings")
    _exact_keys(
        gate["absolute_performance"],
        ("mean_ms", "p95_ms", "mean_ceiling_ms", "p95_ceiling_ms"),
        path="$report.release_gate.absolute_performance",
    )
    external_gate = _exact_keys(
        gate["external_pooled_parent_head_gate"],
        ("status", "maximum_regression_percent", "evidence_owner"),
        path="$report.release_gate.external_pooled_parent_head_gate",
    )
    expected_gate = _release_gate_from_summary(
        tier=root["tier"],
        cases=cases,
        mean=performance_overall["mean_ms"],
        p95=performance_overall["p95_ms"],
        pooled_performance_gate=external_gate["status"],
        strict=strict,
    )
    if dict(gate) != expected_gate:
        raise ValueError("final report release gate differs from code-owned evaluation")
    if strict and gate["verdict"] != "passed":
        raise ValueError(f"strict release gate did not pass: {gate['verdict']}")
    stable_json_dumps(root)


__all__ = [
    "ABSOLUTE_MEAN_CEILING_MS",
    "ABSOLUTE_P95_CEILING_MS",
    "CASE_FIELDS",
    "DASHBOARD_METRIC_IDS",
    "EXPECTED_SKIP_MANIFEST",
    "PHASE50_CASE_IDS",
    "PHASE51_CASE_IDS",
    "PHASE42_MEAN_MS",
    "PHASE42_P95_MS",
    "STAGES",
    "TIERS",
    "build_cross_engine_core",
    "build_dashboard",
    "build_final_report",
    "build_performance_artifact",
    "build_version_evidence",
    "classify_engine_exception",
    "classify_engine_outcome",
    "dashboard_sources_from_routing_report",
    "evaluate_release_gate",
    "is_expected_skip",
    "normalize_phase50_report",
    "normalize_phase51_report",
    "render_final_json",
    "render_final_markdown",
    "validate_core",
    "validate_cross_engine_case",
    "validate_final_report",
    "validate_performance",
    "validate_trace_snapshot",
]
