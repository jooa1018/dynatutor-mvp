from __future__ import annotations

"""Validated, process-cached loader for the dynamics capability matrix."""

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping


CORE_VALIDATOR_IDS = frozenset(
    {
        "answer_consistency",
        "dimension",
        "plausibility",
        "provenance",
    }
)

INVARIANT_VALIDATOR_IDS = frozenset(
    {
        "equation_residual",
        "string_constraint",
        "pure_rolling",
        "collision_momentum",
        "collision_restitution",
        "work_energy",
        "contact_normal",
        "tension_slack",
        "friction_regime",
        "pulley_no_slip",
        "rigid_relative_velocity",
        "rigid_relative_acceleration",
    }
)

SUPPORTED_VALIDATOR_IDS = CORE_VALIDATOR_IDS | INVARIANT_VALIDATOR_IDS
DEFAULT_CAPABILITY_PATH = Path(__file__).with_name("dynamics_capabilities.json")
SOLVER_PATH_FAMILIES = frozenset(
    {
        "incline",
        "pulley",
        "collision",
        "rolling",
        "work_energy",
        "fixed_axis_rotation",
    }
)
SOLVER_PATH_ROLE_KEYS = frozenset(
    {
        "student_answer_path",
        "secondary_analytic_path",
        "numeric_validation_path",
        "external_validation_path",
        "fallback_path",
    }
)
SECONDARY_ANALYTIC_PREFIX = "phase49.secondary."



class CapabilityConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityMatrix:
    schema_version: int
    source_commit: str | None
    capabilities: tuple[Mapping[str, Any], ...]
    by_solver: Mapping[str, Mapping[str, Any]]
    validator_ids: frozenset[str]
    source_path: str
    solver_path_roles: Mapping[str, Mapping[str, Any]]

    def path_roles_for_family(self, family: str) -> Mapping[str, Any] | None:
        return self.solver_path_roles.get(family)

    def for_solver(self, solver_id: str) -> Mapping[str, Any] | None:
        return self.by_solver.get(solver_id)

    def for_problem(
        self,
        system_type: str,
        subtype: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Resolve a capability when the caller has no concrete solver ID.

        The fallback is deterministic and subtype-aware.  An explicit subtype
        is never silently replaced by a different, non-generic subtype.  This
        keeps direct ``verify_result(canonical, result)`` calls aligned with the
        same capability contract used by the routed service path.
        """

        direct = self.by_solver.get(system_type)
        if direct is not None and direct.get("system_type") == system_type:
            direct_subtypes = tuple(direct.get("subtypes") or ())
            if subtype is None or not direct_subtypes or subtype in direct_subtypes:
                return direct

        matches = sorted(
            (
                entry
                for entry in self.capabilities
                if entry.get("system_type") == system_type
            ),
            key=lambda entry: str(entry.get("analytic_solver", "")),
        )
        if not matches:
            return None

        if subtype is not None:
            exact = [entry for entry in matches if subtype in (entry.get("subtypes") or ())]
            if exact:
                return exact[0]
            generic = [entry for entry in matches if not (entry.get("subtypes") or ())]
            return generic[0] if generic else None

        generic = [entry for entry in matches if not (entry.get("subtypes") or ())]
        if generic:
            return generic[0]
        return matches[0] if len(matches) == 1 else None


def _validate_string_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CapabilityConfigError(f"{field_name} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise CapabilityConfigError(f"{field_name} contains duplicate values")
    return list(value)


def _validate_required_inputs(value: Any, *, solver_id: str) -> None:
    expected = {"all_of", "any_of", "conditional"}
    if not isinstance(value, dict) or set(value) != expected:
        raise CapabilityConfigError(
            f"{solver_id}.required_inputs must contain exactly {sorted(expected)}"
        )
    _validate_string_list(value["all_of"], field_name=f"{solver_id}.required_inputs.all_of")
    _validate_string_list(value["any_of"], field_name=f"{solver_id}.required_inputs.any_of")
    if not isinstance(value["conditional"], list):
        raise CapabilityConfigError(f"{solver_id}.required_inputs.conditional must be a list")


def _validate_solver_path_roles(
    value: Any,
    *,
    solver_ids: frozenset[str],
) -> Mapping[str, Mapping[str, Any]]:
    # The field is additive for compatibility with small legacy test fixtures.
    # When present it is a strict, complete Phase 49 contract.
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, dict) or set(value) != SOLVER_PATH_FAMILIES:
        raise CapabilityConfigError(
            "solver_path_roles must contain exactly "
            f"{sorted(SOLVER_PATH_FAMILIES)}"
        )
    frozen: dict[str, Mapping[str, Any]] = {}
    secondary_ids: set[str] = set()
    for family in sorted(SOLVER_PATH_FAMILIES):
        raw_roles = value[family]
        if not isinstance(raw_roles, dict) or set(raw_roles) != SOLVER_PATH_ROLE_KEYS:
            raise CapabilityConfigError(
                f"solver_path_roles.{family} must contain exactly "
                f"{sorted(SOLVER_PATH_ROLE_KEYS)}"
            )
        students = _validate_string_list(
            raw_roles["student_answer_path"],
            field_name=f"solver_path_roles.{family}.student_answer_path",
        )
        if not students:
            raise CapabilityConfigError(
                f"solver_path_roles.{family}.student_answer_path must not be empty"
            )
        unknown_solvers = sorted(set(students) - solver_ids)
        if unknown_solvers:
            raise CapabilityConfigError(
                f"solver_path_roles.{family} references unknown solver IDs: "
                + ", ".join(unknown_solvers)
            )
        secondary = raw_roles["secondary_analytic_path"]
        expected_secondary = f"{SECONDARY_ANALYTIC_PREFIX}{family}"
        if secondary != expected_secondary:
            raise CapabilityConfigError(
                f"solver_path_roles.{family}.secondary_analytic_path must be "
                f"{expected_secondary!r}"
            )
        if secondary in secondary_ids:
            raise CapabilityConfigError("duplicate secondary analytic path")
        secondary_ids.add(secondary)
        for unavailable in (
            "numeric_validation_path",
            "external_validation_path",
        ):
            if raw_roles[unavailable] is not None:
                raise CapabilityConfigError(
                    f"solver_path_roles.{family}.{unavailable} must be null "
                    "until its optional engine is implemented"
                )
        fallback = raw_roles["fallback_path"]
        if fallback is not None:
            if not isinstance(fallback, str) or not fallback:
                raise CapabilityConfigError(
                    f"solver_path_roles.{family}.fallback_path must be a solver ID or null"
                )
            if fallback not in solver_ids:
                raise CapabilityConfigError(
                    f"solver_path_roles.{family}.fallback_path references "
                    f"unknown solver ID {fallback!r}"
                )
        frozen[family] = MappingProxyType(
            {
                "student_answer_path": tuple(students),
                "secondary_analytic_path": secondary,
                "numeric_validation_path": None,
                "external_validation_path": None,
                "fallback_path": fallback,
            }
        )
    return MappingProxyType(frozen)


def _validated_matrix(
    raw: Any,
    *,
    source_path: str,
    supported_validator_ids: frozenset[str],
) -> CapabilityMatrix:
    if not isinstance(raw, dict):
        raise CapabilityConfigError(f"capability file at {source_path} must contain an object")
    if raw.get("schema_version") != 1:
        raise CapabilityConfigError("capability schema_version must be 1")
    entries = raw.get("capabilities")
    if not isinstance(entries, list):
        raise CapabilityConfigError("capabilities must be a list")

    copied_entries: list[Mapping[str, Any]] = []
    by_solver: dict[str, Mapping[str, Any]] = {}
    used_validator_ids: set[str] = set()
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            raise CapabilityConfigError(f"capabilities[{index}] must be an object")
        entry = deepcopy(raw_entry)
        solver_id = entry.get("analytic_solver")
        if not isinstance(solver_id, str) or not solver_id:
            raise CapabilityConfigError(f"capabilities[{index}].analytic_solver is required")
        if solver_id in by_solver:
            raise CapabilityConfigError(f"duplicate analytic_solver capability: {solver_id}")
        system_type = entry.get("system_type")
        if not isinstance(system_type, str) or not system_type:
            raise CapabilityConfigError(f"{solver_id}.system_type is required")
        _validate_string_list(entry.get("subtypes"), field_name=f"{solver_id}.subtypes")
        _validate_required_inputs(entry.get("required_inputs"), solver_id=solver_id)
        _validate_string_list(entry.get("requested_outputs"), field_name=f"{solver_id}.requested_outputs")
        validators = _validate_string_list(entry.get("validators"), field_name=f"{solver_id}.validators")
        unknown = sorted(set(validators) - supported_validator_ids)
        if unknown:
            raise CapabilityConfigError(
                f"{solver_id} references unknown validator IDs: {', '.join(unknown)}"
            )
        used_validator_ids.update(validators)
        frozen_entry = MappingProxyType(entry)
        copied_entries.append(frozen_entry)
        by_solver[solver_id] = frozen_entry

    solver_path_roles = _validate_solver_path_roles(
        raw.get("solver_path_roles"),
        solver_ids=frozenset(by_solver),
    )

    return CapabilityMatrix(
        schema_version=1,
        source_commit=(
            str(raw["source_commit"])
            if raw.get("source_commit") is not None
            else None
        ),
        capabilities=tuple(copied_entries),
        by_solver=MappingProxyType(by_solver),
        validator_ids=frozenset(used_validator_ids),
        source_path=source_path,
        solver_path_roles=solver_path_roles,
    )


@lru_cache(maxsize=16)
def _load_cached(
    resolved_path: str,
    supported_validator_ids: tuple[str, ...],
) -> CapabilityMatrix:
    path = Path(resolved_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityConfigError(f"cannot load capability matrix at {path}: {exc}") from exc
    return _validated_matrix(
        raw,
        source_path=resolved_path,
        supported_validator_ids=frozenset(supported_validator_ids),
    )


def load_capability_matrix(
    path: str | Path | None = None,
    *,
    supported_validator_ids: Iterable[str] = SUPPORTED_VALIDATOR_IDS,
) -> CapabilityMatrix:
    resolved = str(Path(path or DEFAULT_CAPABILITY_PATH).resolve())
    supported = tuple(sorted(set(supported_validator_ids)))
    return _load_cached(resolved, supported)


def clear_capability_cache() -> None:
    _load_cached.cache_clear()


def validate_capability_validator_ids(
    data: Mapping[str, Any],
    *,
    supported_validator_ids: Iterable[str] = SUPPORTED_VALIDATOR_IDS,
    source: str = "<memory>",
) -> None:
    _validated_matrix(
        deepcopy(dict(data)),
        source_path=source,
        supported_validator_ids=frozenset(supported_validator_ids),
    )


__all__ = [
    "CORE_VALIDATOR_IDS",
    "INVARIANT_VALIDATOR_IDS",
    "SUPPORTED_VALIDATOR_IDS",
    "SECONDARY_ANALYTIC_PREFIX",
    "SOLVER_PATH_FAMILIES",
    "SOLVER_PATH_ROLE_KEYS",
    "CapabilityConfigError",
    "CapabilityMatrix",
    "clear_capability_cache",
    "load_capability_matrix",
    "validate_capability_validator_ids",
]
