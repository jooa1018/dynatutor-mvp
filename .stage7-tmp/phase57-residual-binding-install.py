from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()

MODULE = r'''"""Derive one exact query binding from a typed Mechanics Draft.

A fallback solution is admissible only when it can be attached to the same
unknown symbol, subject, and component the normal compiler pipeline was asked to
solve.  This module never fabricates a symbol and never consults case identity,
gold, expected terminal, family, tolerance, or score.  Ambiguity fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class QueryBinding:
    symbol_id: str
    subject_id: str
    component: str | None


def _token(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _enum_text(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).casefold()


def _consistent(primary: Any, secondary: Any) -> str | None:
    first = _token(primary)
    second = _token(secondary)
    if first and second and first != second:
        return None
    return first or second


def _unknown_marker(node: dict[str, Any]) -> bool:
    if node.get("known") is False or node.get("is_known") is False:
        return True
    if node.get("is_unknown") is True or node.get("unknown") is True:
        return True
    material = " ".join(
        _enum_text(node.get(key))
        for key in (
            "kind",
            "status",
            "definition_kind",
            "symbol_kind",
            "role_kind",
        )
    )
    return "unknown" in material or "query" in material


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _walk(nested)


def _candidate_score(
    node: dict[str, Any],
    *,
    query_id: str | None,
    target_quantity_id: str | None,
    role: str | None,
    subject: str,
    component: str | None,
) -> int:
    score = 0
    owner_query = _token(
        node.get("query_id")
        or node.get("owner_query_id")
        or node.get("source_query_id")
        or node.get("target_query_id")
    )
    owner_quantity = _token(
        node.get("quantity_id")
        or node.get("owner_quantity_id")
        or node.get("target_quantity_id")
    )
    node_role = _token(node.get("role") or node.get("physical_role"))
    node_subject = _token(
        node.get("subject_id")
        or node.get("owner_subject_id")
        or node.get("target_subject_id")
    )
    node_component = _token(node.get("component"))

    if query_id and owner_query == query_id:
        score += 120
    if target_quantity_id and owner_quantity == target_quantity_id:
        score += 100
    if node_subject == subject:
        score += 24
    elif node_subject is not None:
        score -= 40
    if role and node_role == role:
        score += 20
    elif node_role is not None and role is not None:
        score -= 20
    if component and node_component == component:
        score += 12
    elif node_component is not None and component is not None:
        score -= 12
    if _unknown_marker(node):
        score += 36
    if "raw_value" in node and node.get("raw_value") is None:
        score += 18
    if node.get("value") is None and "value" in node:
        score += 8
    return score


def derive_query_binding(base: Any, draft_payload: dict[str, Any]) -> QueryBinding | None:
    """Return one attributable query binding, or ``None`` on any ambiguity."""

    queries = draft_payload.get("queries") or []
    if len(queries) != 1 or not isinstance(queries[0], dict):
        return None
    query = queries[0]
    target = query.get("target") or {}
    if not isinstance(target, dict):
        return None

    subject = _consistent(
        getattr(base, "query_subject_id", None), target.get("subject_id")
    )
    if subject is None:
        return None
    base_component = getattr(base, "answer_component", None)
    target_component = target.get("component")
    if _token(base_component) and _token(target_component) and base_component != target_component:
        return None
    component = _token(base_component) or _token(target_component)

    direct = {
        item
        for item in (
            _token(getattr(base, "answer_query_symbol_id", None)),
            _token(target.get("symbol_id")),
            _token(query.get("symbol_id")),
        )
        if item is not None
    }
    if len(direct) == 1:
        return QueryBinding(next(iter(direct)), subject, component)
    if len(direct) > 1:
        return None

    query_id = _token(query.get("query_id"))
    target_quantity_id = _token(
        target.get("quantity_id") or query.get("quantity_id")
    )
    role = _token(target.get("role"))

    scored: dict[str, int] = {}
    for node in _walk(draft_payload):
        symbol = _token(node.get("symbol_id"))
        if symbol is None:
            continue
        score = _candidate_score(
            node,
            query_id=query_id,
            target_quantity_id=target_quantity_id,
            role=role,
            subject=subject,
            component=component,
        )
        if score >= 48:
            scored[symbol] = max(scored.get(symbol, -10_000), score)

    if not scored:
        return None
    maximum = max(scored.values())
    winners = sorted(symbol for symbol, score in scored.items() if score == maximum)
    if len(winners) != 1:
        return None
    return QueryBinding(winners[0], subject, component)


__all__ = ["QueryBinding", "derive_query_binding"]
'''

TEST = r'''from types import SimpleNamespace

from evaluation.phase56_stage7.query_binding import derive_query_binding


def test_direct_base_binding_is_preserved() -> None:
    base = SimpleNamespace(
        answer_query_symbol_id="query_symbol",
        query_subject_id="body",
        answer_component="x",
    )
    draft = {
        "queries": [
            {
                "query_id": "q1",
                "target": {"subject_id": "body", "component": "x"},
            }
        ]
    }
    binding = derive_query_binding(base, draft)
    assert binding is not None
    assert binding.symbol_id == "query_symbol"
    assert binding.subject_id == "body"
    assert binding.component == "x"


def test_unique_owner_query_unknown_symbol_is_found() -> None:
    base = SimpleNamespace(
        answer_query_symbol_id=None,
        query_subject_id=None,
        answer_component=None,
    )
    draft = {
        "queries": [
            {
                "query_id": "q1",
                "target": {
                    "role": "velocity",
                    "subject_id": "body",
                    "component": "x",
                },
            }
        ],
        "symbols": [
            {
                "symbol_id": "known_symbol",
                "owner_query_id": "other",
                "known": True,
            },
            {
                "symbol_id": "unknown_query_symbol",
                "owner_query_id": "q1",
                "role": "velocity",
                "subject_id": "body",
                "component": "x",
                "is_unknown": True,
            },
        ],
    }
    binding = derive_query_binding(base, draft)
    assert binding is not None
    assert binding.symbol_id == "unknown_query_symbol"


def test_quantity_link_can_bind_the_query_unknown() -> None:
    base = SimpleNamespace(
        answer_query_symbol_id=None,
        query_subject_id="body",
        answer_component="magnitude",
    )
    draft = {
        "queries": [
            {
                "query_id": "q1",
                "target": {
                    "role": "acceleration",
                    "subject_id": "body",
                    "component": "magnitude",
                    "quantity_id": "query_quantity",
                },
            }
        ],
        "quantities": [
            {
                "quantity_id": "query_quantity",
                "symbol_id": "query_unknown",
                "role": "acceleration",
                "subject_id": "body",
                "component": "magnitude",
                "raw_value": None,
            }
        ],
    }
    binding = derive_query_binding(base, draft)
    assert binding is not None
    assert binding.symbol_id == "query_unknown"


def test_equal_ambiguous_unknowns_fail_closed() -> None:
    base = SimpleNamespace(
        answer_query_symbol_id=None,
        query_subject_id=None,
        answer_component=None,
    )
    draft = {
        "queries": [
            {
                "query_id": "q1",
                "target": {"role": "force", "subject_id": "body"},
            }
        ],
        "symbols": [
            {
                "symbol_id": "a",
                "owner_query_id": "q1",
                "subject_id": "body",
                "role": "force",
                "is_unknown": True,
            },
            {
                "symbol_id": "b",
                "owner_query_id": "q1",
                "subject_id": "body",
                "role": "force",
                "is_unknown": True,
            },
        ],
    }
    assert derive_query_binding(base, draft) is None


def test_subject_disagreement_fails_closed() -> None:
    base = SimpleNamespace(
        answer_query_symbol_id="s",
        query_subject_id="body_a",
        answer_component=None,
    )
    draft = {
        "queries": [
            {
                "query_id": "q1",
                "target": {"subject_id": "body_b"},
            }
        ]
    }
    assert derive_query_binding(base, draft) is None
'''

(ROOT / "backend/evaluation/phase56_stage7/query_binding.py").write_text(
    MODULE, encoding="utf-8"
)
(ROOT / "backend/tests/test_phase57_query_binding.py").write_text(
    TEST, encoding="utf-8"
)

IMPORT = (
    "from evaluation.phase56_stage7.query_binding import derive_query_binding\n"
)


def add_import(text: str) -> str:
    if "from evaluation.phase56_stage7.query_binding import" in text:
        return text
    anchor = "from typing import Any\n"
    if anchor in text:
        return text.replace(anchor, anchor + "\n" + IMPORT, 1)
    future = "from __future__ import annotations\n"
    if future in text:
        return text.replace(future, future + "\n" + IMPORT, 1)
    raise RuntimeError("query_binding_import_anchor_missing")


for relative in (
    "backend/evaluation/phase56_stage7/typed_closed_form_adapter.py",
    "backend/evaluation/phase56_stage7/public_closed_form_adapter.py",
):
    path = ROOT / relative
    if not path.exists():
        continue
    text = add_import(path.read_text(encoding="utf-8"))
    text = text.replace(
        "binding = _binding(base, draft_payload)",
        "binding = derive_query_binding(base, draft_payload)",
    )
    path.write_text(text, encoding="utf-8")

canonical = ROOT / "backend/evaluation/phase56_stage7/canonical_fallback_adapter.py"
if canonical.exists():
    text = add_import(canonical.read_text(encoding="utf-8"))
    pattern = re.compile(
        r"    queries = draft_payload\.get\(\"queries\"\) or \[\]\n"
        r".*?"
        r"    solution = solve_canonical_mechanics\(",
        re.DOTALL,
    )
    replacement = (
        "    binding = derive_query_binding(base, draft_payload)\n"
        "    if binding is None:\n"
        "        return base\n"
        "    symbol = binding.symbol_id\n"
        "    subject = binding.subject_id\n"
        "    component = binding.component\n"
        "    solution = solve_canonical_mechanics("
    )
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1 and "binding = derive_query_binding(base, draft_payload)" not in text:
        raise RuntimeError("canonical_query_binding_anchor_missing")
    canonical.write_text(text, encoding="utf-8")
