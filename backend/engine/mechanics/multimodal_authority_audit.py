"""Read-only authority audit for Stage 6 modeling envelopes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "final_answer",
        "executable_equation",
        "equation_graph",
        "selected_solver",
        "solver_candidate",
        "selected_root",
        "verification_result",
        "verified_candidate",
        "legacy_route",
        "legacy_solver",
        "runtime_delivery",
    }
)


@dataclass(frozen=True, slots=True)
class AuthorityFinding:
    path: str
    field: str


@dataclass(frozen=True, slots=True)
class AuthorityAudit:
    passed: bool
    findings: tuple[AuthorityFinding, ...]


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return value


def audit_modeling_payload(value: Any) -> AuthorityAudit:
    findings: list[AuthorityFinding] = []

    def visit(node: Any, path: str) -> None:
        node = _plain(node)
        if isinstance(node, Mapping):
            for raw_key, child in node.items():
                key = str(raw_key)
                child_path = f"{path}.{key}" if path else key
                if key in FORBIDDEN_AUTHORITY_FIELDS and child not in (None, "", [], {}, ()):
                    findings.append(AuthorityFinding(path=child_path, field=key))
                visit(child, child_path)
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")

    visit(value, "")
    ordered = tuple(sorted(findings, key=lambda item: (item.path, item.field)))
    return AuthorityAudit(passed=not ordered, findings=ordered)


__all__ = [
    "AuthorityAudit",
    "AuthorityFinding",
    "FORBIDDEN_AUTHORITY_FIELDS",
    "audit_modeling_payload",
]
