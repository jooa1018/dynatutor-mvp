"""Allowlisted, content-free one-shot repair instructions."""
from __future__ import annotations

import re
from typing import get_args, get_origin

from pydantic import BaseModel

from engine.mechanics.contracts import MechanicsProblemDraftV1
from engine.mechanics.errors import (
    MechanicsIssueCode,
    MechanicsIssueSeverity,
    MechanicsValidationIssue,
)
from engine.mechanics.modeler_errors import ModelerRepairIssue


MECHANICS_REPAIR_POLICY_VERSION = "mechanics-indexed-structural-repair-v3"
MAX_REPAIR_ISSUES = 24

REPAIRABLE_VALIDATION_CODES = frozenset(
    {
        MechanicsIssueCode.duplicate_id,
        MechanicsIssueCode.invalid_reference,
    }
)
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_.\[\]-]{0,240}$")
_SAFE_REFERENCE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_SAFE_ERROR_TYPE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_CLIENT_REPAIR_CODES = frozenset({"schema_error"})
_REPAIRABLE_PYDANTIC_ERROR_TYPES = frozenset(
    {
        "missing",
        "string_type",
        "string_pattern_mismatch",
        "string_too_short",
        "string_too_long",
    }
)
_MAX_STRUCTURAL_INDEX = 511
_SAFE_REASONS = frozenset(
    {"schema_error"}
) | frozenset(code.value for code in REPAIRABLE_VALIDATION_CODES)

# A repair may only correct graph shape and graph identity/reference wiring.
# Source evidence, quantities, provenance, assumptions, figures, trusted
# metadata, law hints, and result authority are intentionally absent.
_STRUCTURAL_ROOTS = frozenset(
    {
        "entities",
        "points",
        "reference_frames",
        "motion_intervals",
        "events",
        "symbols",
        "geometry",
        "interactions",
        "constraints",
        "state_conditions",
        "queries",
    }
)
_STRUCTURAL_CONTAINERS = frozenset(
    {
        *_STRUCTURAL_ROOTS,
        "origin",
        "target",
    }
)
_STRUCTURAL_SCALAR_LEAVES = frozenset(
    {
        "entity_id",
        "component_of_entity_id",
        "point_id",
        "owner_entity_id",
        "frame_id",
        "parent_frame_id",
        "translating_with_entity_id",
        "rotating_about_point_id",
        "symbol_id",
        "interval_id",
        "start_event_id",
        "end_event_id",
        "event_id",
        "subject_id",
        "query_id",
        "relation_id",
        "interaction_id",
        "constraint_id",
        "state_condition_id",
    }
)
_STRUCTURAL_LIST_FIELDS = frozenset(
    {
        "generalized_coordinate_symbol_ids",
        "subject_ids",
        "participant_ids",
        "point_ids",
        "interval_ids",
    }
)
_FORBIDDEN_REPAIR_FIELDS = frozenset(
    {
        "metadata",
        "source_assets",
        "source_evidence",
        "evidence_refs",
        "quantities",
        "quantity_id",
        "quantity_ids",
        "target_quantity_id",
        "raw_value",
        "raw_unit",
        "provenance",
        "assumption_policy_ref",
        "correction_id",
        "assumptions",
        "ambiguities",
        "figure_dependency",
        "unsupported_features",
        "principle_hints",
        "model_confidence",
        "output_unit",
        "output_dimension",
    }
)


def _contract_path_segments() -> frozenset[str]:
    segments = {"draft", "expressions", "normalization"}
    pending: list[object] = [MechanicsProblemDraftV1]
    visited: set[int] = set()
    while pending:
        annotation = pending.pop()
        marker = id(annotation)
        if marker in visited:
            continue
        visited.add(marker)
        try:
            is_model = isinstance(annotation, type) and issubclass(annotation, BaseModel)
        except TypeError:
            is_model = False
        if is_model:
            for name, field in annotation.model_fields.items():
                segments.add(name)
                pending.append(field.annotation)
            continue
        origin = get_origin(annotation)
        if origin is not None:
            pending.extend(get_args(annotation))
    return frozenset(segments)


_CONTRACT_PATH_SEGMENTS = _contract_path_segments()


def _safe_path(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_PATH.fullmatch(value):
        return ""
    segments = tuple(
        part for part in re.split(r"[.\[\]]+", value) if part
    )
    if any(
        not part.isdigit() and part not in _CONTRACT_PATH_SEGMENTS
        for part in segments
    ):
        return ""
    return value


def is_repairable_structural_path(value: object) -> bool:
    path = _safe_path(value)
    if not path:
        return False
    segments = tuple(part for part in re.split(r"[.\[\]]+", path) if part)
    if not segments or segments[0] not in _STRUCTURAL_ROOTS:
        return False
    numeric = tuple(part for part in segments if part.isdigit())
    if any(
        len(part) > 3
        or (len(part) > 1 and part.startswith("0"))
        or int(part) > _MAX_STRUCTURAL_INDEX
        for part in numeric
    ):
        return False
    named = tuple(part for part in segments if not part.isdigit())
    indexed_list_leaf = (
        segments[-1].isdigit()
        and len(segments) >= 2
        and segments[-2] in _STRUCTURAL_LIST_FIELDS
    )
    scalar_leaf = (
        not segments[-1].isdigit()
        and named[-1] in _STRUCTURAL_SCALAR_LEAVES
    )
    # Whole plural collections are never repairable.  A list reference must
    # identify one bounded numeric element, e.g. ``subject_ids.0``.
    return (
        (scalar_leaf or indexed_list_leaf)
        and not any(part in _FORBIDDEN_REPAIR_FIELDS for part in named)
        and all(
            part in _STRUCTURAL_CONTAINERS
            or part in _STRUCTURAL_SCALAR_LEAVES
            or part in _STRUCTURAL_LIST_FIELDS
            for part in named
        )
    )


def _safe_reference(value: object) -> str | None:
    if not isinstance(value, str) or not _SAFE_REFERENCE.fullmatch(value):
        return None
    return value


def repair_issues_from_validation(
    issues: tuple[MechanicsValidationIssue, ...],
) -> tuple[ModelerRepairIssue, ...]:
    blockers = tuple(
        issue
        for issue in issues
        if issue.severity in {MechanicsIssueSeverity.error, MechanicsIssueSeverity.critical}
    )
    if not blockers or len(blockers) > MAX_REPAIR_ISSUES:
        return ()
    if any(
        issue.code not in REPAIRABLE_VALIDATION_CODES
        or not is_repairable_structural_path(issue.path)
        for issue in blockers
    ):
        return ()
    return tuple(
        ModelerRepairIssue(
            code=issue.code.value,
            path=_safe_path(issue.path),
            referenced_id=_safe_reference(issue.referenced_id),
            reason_code=issue.code.value,
        )
        for issue in blockers
    )


def sanitize_repair_issues(
    issues: tuple[ModelerRepairIssue, ...],
) -> tuple[ModelerRepairIssue, ...]:
    allowed_codes = _CLIENT_REPAIR_CODES | frozenset(
        code.value for code in REPAIRABLE_VALIDATION_CODES
    )
    sanitized: list[ModelerRepairIssue] = []
    for issue in issues[:MAX_REPAIR_ISSUES]:
        if (
            not isinstance(issue, ModelerRepairIssue)
            or not isinstance(issue.code, str)
            or issue.code not in allowed_codes
            or not is_repairable_structural_path(issue.path)
        ):
            continue
        reason = (
            issue.reason_code
            if isinstance(issue.reason_code, str) and issue.reason_code in _SAFE_REASONS
            else issue.code
        )
        error_type = None
        if issue.code == "schema_error":
            if (
                not isinstance(issue.error_type, str)
                or issue.error_type not in _REPAIRABLE_PYDANTIC_ERROR_TYPES
            ):
                continue
            error_type = issue.error_type
        elif isinstance(issue.error_type, str) and _SAFE_ERROR_TYPE.fullmatch(
            issue.error_type
        ):
            error_type = issue.error_type
        sanitized.append(
            ModelerRepairIssue(
                code=issue.code,
                path=_safe_path(issue.path),
                referenced_id=_safe_reference(issue.referenced_id),
                reason_code=reason,
                error_type=error_type,
            )
        )
    return tuple(sanitized)


def format_repair_text(
    problem_text: str,
    issues: tuple[ModelerRepairIssue, ...],
    *,
    asset_manifest: tuple[str, ...],
) -> str:
    issues = sanitize_repair_issues(issues)
    lines = [
        "Return one fresh complete MechanicsProblemDraftV1 for the original source.",
        "Correct only these bounded structural failures:",
    ]
    for index, issue in enumerate(issues[:MAX_REPAIR_ISSUES], start=1):
        lines.append(f"{index}. code={issue.code}; path={_safe_path(issue.path) or '<root>'}")
        if issue.referenced_id:
            lines.append(f"   reference={_safe_reference(issue.referenced_id)}")
        if issue.reason_code:
            lines.append(f"   reason={issue.reason_code}")
        if issue.error_type:
            lines.append(f"   type={issue.error_type}")
    lines.extend(
        (
            "Do not return a patch. Do not copy diagnostics into the output.",
            "Do not calculate a requested result or grant authority to model-proposed values.",
            "Use exactly these source asset descriptors:",
            *asset_manifest,
            "ORIGINAL SOURCE TEXT:",
            problem_text,
        )
    )
    return "\n".join(lines)


__all__ = [
    "MAX_REPAIR_ISSUES",
    "MECHANICS_REPAIR_POLICY_VERSION",
    "REPAIRABLE_VALIDATION_CODES",
    "format_repair_text",
    "is_repairable_structural_path",
    "repair_issues_from_validation",
    "sanitize_repair_issues",
]
