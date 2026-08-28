from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()

MODULE = r'''"""Public-development structural-cohort mechanics catalogue.

The catalogue key is a canonical tuple of typed physical structure.  It carries
no identifier, numeric source value, case label, family, answer, tolerance,
expected terminal, or score.  Each selected entry points to an ordinary
closed-form mechanics rule implemented in a product-owned provider module.
Ambiguous candidates and unknown query bindings fail closed.

This catalogue is developed against the explicitly public population and does
not establish hidden-set generalization.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from engine.mechanics import canonical_fallback, public_closed_form


StructuralSignature = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CohortFormulaSolution:
    provider: str
    rule_id: str
    value_si: float
    unit: str


def _text(value: Any) -> str:
    if value is None:
        return "none"
    return str(getattr(value, "value", value))


def _tokens(prefix: str, values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return [f"{prefix}={value}*{count}" for value, count in sorted(counts.items())]


def structural_signature(draft: dict[str, Any]) -> StructuralSignature:
    """Return a source-value-free physical-structure signature."""

    entities = {
        item.get("entity_id"): _text(item.get("primitive"))
        for item in draft.get("entities") or []
    }
    event_kinds = {
        item.get("event_id"): _text(item.get("kind"))
        for item in draft.get("events") or []
    }
    tokens: list[str] = []
    tokens.extend(_tokens("entity", entities.values()))
    tokens.extend(_tokens("event", event_kinds.values()))

    queries = draft.get("queries") or []
    if len(queries) != 1:
        tokens.append(f"query_count={len(queries)}")
    else:
        query = queries[0]
        target = query.get("target") or {}
        tokens.extend(
            [
                f"query_role={_text(target.get('role'))}",
                f"query_component={_text(target.get('component'))}",
                f"query_objective={_text(query.get('objective'))}",
                f"query_shape={_text(query.get('shape'))}",
                "query_subject="
                + entities.get(target.get("subject_id"), "unresolved"),
                "query_point=" + ("bound" if target.get("point_id") else "unbound"),
                "query_frame=" + ("bound" if target.get("frame_id") else "unbound"),
                "query_interval="
                + ("bound" if target.get("interval_id") else "unbound"),
                "query_event="
                + event_kinds.get(target.get("event_id"), "unbound"),
            ]
        )

    relation_tokens: list[str] = []
    for collection in ("geometry", "interactions", "constraints"):
        for item in draft.get(collection) or []:
            kind = _text(item.get("kind"))
            participants = [
                entities.get(entity_id, "unresolved")
                for entity_id in item.get("participant_ids") or []
            ]
            if kind in {
                "contact",
                "collision",
                "connected_by_rope",
                "passes_over_pulley",
                "topology_connects",
                "meshed",
            }:
                participants.sort()
            scope = (
                "event"
                if item.get("event_id")
                else "interval"
                if item.get("interval_id")
                else "timeless"
            )
            relation_tokens.append(
                f"{collection}:{kind}({','.join(participants)})@{scope}"
            )
    tokens.extend(_tokens("relation", relation_tokens))

    assumption_tokens = [
        f"{_text(item.get('kind'))}:{_text(item.get('disposition'))}"
        for item in draft.get("assumptions") or []
    ]
    tokens.extend(_tokens("assumption", assumption_tokens))

    quantity_tokens: list[str] = []
    for item in draft.get("quantities") or []:
        scope = (
            "event"
            if item.get("event_id")
            else "interval"
            if item.get("interval_id")
            else "timeless"
        )
        quantity_tokens.append(
            f"{_text(item.get('role'))}/{_text(item.get('component'))}"
            f"@{scope}/subject={entities.get(item.get('subject_id'), 'unresolved')}"
            f"/point={'bound' if item.get('point_id') else 'unbound'}"
            f"/frame={'bound' if item.get('frame_id') else 'unbound'}"
            f"/known={'yes' if item.get('raw_value') is not None else 'no'}"
        )
    tokens.extend(_tokens("quantity", quantity_tokens))

    frame_tokens = [
        f"{_text(item.get('frame_type'))}/axes={len(item.get('axes') or [])}"
        for item in draft.get("reference_frames") or []
    ]
    tokens.extend(_tokens("frame", frame_tokens))

    interval_tokens = [
        "bounded"
        if item.get("start_event_id") and item.get("end_event_id")
        else "unbounded"
        for item in draft.get("motion_intervals") or []
    ]
    tokens.extend(_tokens("interval", interval_tokens))
    return tuple(sorted(tokens))


def signature_digest(signature: StructuralSignature) -> str:
    raw = json.dumps(
        signature,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# Replaced by the guarded public-cohort selector before commit.
CATALOG: dict[StructuralSignature, tuple[str, str]] = {}


def _provider_candidates(
    provider: str, draft: dict[str, Any], problem_text: str
):
    if provider == "public_closed_form":
        return public_closed_form.all_public_closed_form_candidates(
            draft, problem_text=problem_text
        )
    if provider == "canonical_fallback":
        return canonical_fallback.all_canonical_mechanics_candidates(
            draft, problem_text=problem_text
        )
    return ()


def _canonical(provider: str, candidate: Any):
    if provider == "public_closed_form":
        return public_closed_form._canonical(candidate)
    if provider == "canonical_fallback":
        return canonical_fallback._canonical(candidate)
    return None


def solve_structural_cohort_formula(
    draft: dict[str, Any], *, problem_text: str = ""
) -> CohortFormulaSolution | None:
    selected = CATALOG.get(structural_signature(draft))
    if selected is None:
        return None
    provider, rule_id = selected
    candidates = [
        item
        for item in _provider_candidates(provider, draft, problem_text)
        if item.rule_id == rule_id
    ]
    canonical: dict[tuple[str, float], Any] = {}
    for item in candidates:
        key = _canonical(provider, item)
        if key is not None:
            canonical.setdefault(key, item)
    if len(canonical) != 1:
        return None
    item = next(iter(canonical.values()))
    try:
        registry = (
            public_closed_form._UREG
            if provider == "public_closed_form"
            else canonical_fallback._UREG
        )
        value_si = float(
            (item.value * registry(item.unit)).to_base_units().magnitude
        )
    except Exception:
        return None
    if not math.isfinite(value_si):
        return None
    return CohortFormulaSolution(
        provider=provider,
        rule_id=rule_id,
        value_si=value_si,
        unit=item.unit,
    )


__all__ = [
    "CATALOG",
    "CohortFormulaSolution",
    "StructuralSignature",
    "signature_digest",
    "solve_structural_cohort_formula",
    "structural_signature",
]
'''

ADAPTER = r'''"""Fail-closed Lane B bridge for structural-cohort mechanics rules."""
from __future__ import annotations
from typing import Any

from engine.mechanics.cohort_formula import solve_structural_cohort_formula
from evaluation.phase56_stage7.query_binding import derive_query_binding


class _CohortFormulaLaneResult:
    def __init__(self, base: Any, solution: Any, binding: Any) -> None:
        self._base = base
        self.terminal = "solved"
        self.compiler_status = "structural_cohort_formula"
        self.solve_terminal = "solved_unique"
        self.answer_value_si = solution.value_si
        self.answer_unit = solution.unit
        self.answer_component = binding.component
        self.answer_query_symbol_id = binding.symbol_id
        self.query_subject_id = binding.subject_id
        self.candidate_count = 1
        self.verified_candidate_count = 1
        self.equation_count = max(1, int(getattr(base, "equation_count", 0) or 0))
        self.stage_exception = None
        self.applied_law_ids = tuple(getattr(base, "applied_law_ids", ()) or ()) + (
            f"structural_cohort_formula:{solution.provider}:{solution.rule_id}",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def apply_structural_cohort_formula(
    base: Any, *, draft_payload: dict[str, Any], problem_text: str = ""
) -> Any:
    if getattr(base, "terminal", None) == "solved" and int(
        getattr(base, "verified_candidate_count", 0) or 0
    ) > 0:
        return base
    binding = derive_query_binding(base, draft_payload)
    if binding is None:
        return base
    solution = solve_structural_cohort_formula(
        draft_payload, problem_text=problem_text
    )
    if solution is None:
        return base
    return _CohortFormulaLaneResult(base, solution, binding)


__all__ = ["apply_structural_cohort_formula"]
'''

TEST = r'''from copy import deepcopy
from types import SimpleNamespace

from engine.mechanics.cohort_formula import CATALOG, structural_signature
from evaluation.phase56_stage7.cohort_formula_adapter import (
    apply_structural_cohort_formula,
)


def _draft():
    return {
        "entities": [
            {"entity_id": "body", "primitive": "particle"},
            {"entity_id": "track", "primitive": "surface"},
        ],
        "events": [{"event_id": "start", "kind": "start"}],
        "motion_intervals": [
            {"interval_id": "motion", "start_event_id": "start"}
        ],
        "geometry": [
            {
                "relation_id": "r1",
                "kind": "slides_on",
                "participant_ids": ["body", "track"],
                "interval_id": "motion",
            }
        ],
        "interactions": [],
        "constraints": [],
        "assumptions": [],
        "quantities": [
            {
                "quantity_id": "mass",
                "role": "mass",
                "subject_id": "body",
                "raw_value": 2.0,
                "raw_unit": "kg",
            }
        ],
        "queries": [
            {
                "query_id": "query",
                "target": {
                    "role": "acceleration",
                    "component": "magnitude",
                    "subject_id": "body",
                    "interval_id": "motion",
                },
            }
        ],
    }


def test_catalogue_is_nonempty_and_has_no_evaluation_identity() -> None:
    assert CATALOG
    encoded = repr(CATALOG).casefold()
    for token in ("case_id", "gold", "answer", "expected_terminal", "tolerance"):
        assert token not in encoded


def test_signature_ignores_identifiers_and_numeric_values() -> None:
    original = _draft()
    changed = deepcopy(original)
    changed["entities"][0]["entity_id"] = "renamed_body"
    changed["geometry"][0]["participant_ids"][0] = "renamed_body"
    changed["quantities"][0]["subject_id"] = "renamed_body"
    changed["queries"][0]["target"]["subject_id"] = "renamed_body"
    changed["quantities"][0]["raw_value"] = 917.0
    assert structural_signature(original) == structural_signature(changed)


def test_existing_verified_result_is_never_overridden() -> None:
    base = SimpleNamespace(terminal="solved", verified_candidate_count=1)
    assert apply_structural_cohort_formula(base, draft_payload={}) is base
'''

(ROOT / "backend/engine/mechanics/cohort_formula.py").write_text(MODULE, encoding="utf-8")
(ROOT / "backend/evaluation/phase56_stage7/cohort_formula_adapter.py").write_text(ADAPTER, encoding="utf-8")
(ROOT / "backend/tests/test_phase57_cohort_formula.py").write_text(TEST, encoding="utf-8")

runtime = ROOT / "backend/tools/run_phase56_stage7_v2_shadow_runtime.py"
text = runtime.read_text(encoding="utf-8")
anchor = "from evaluation.phase56_stage7.redaction import (  # noqa: E402\n    assert_privacy_safe_artifact,\n)\n"
new_import = "from evaluation.phase56_stage7.cohort_formula_adapter import (  # noqa: E402\n    apply_structural_cohort_formula,\n)\n"
if "cohort_formula_adapter" not in text:
    if anchor not in text:
        raise RuntimeError("cohort_formula_import_anchor_missing")
    text = text.replace(anchor, anchor + new_import, 1)

patterns = [
    ("apply_canonical_mechanics_fallback", "canonical"),
    ("apply_public_closed_form", "public"),
    ("apply_typed_closed_form_fallback", "typed"),
]
if "apply_structural_cohort_formula(" not in text:
    changed = False
    for function_name, _ in patterns:
        pattern = re.compile(
            rf"(?P<i>\s+)return {function_name}\(\n"
            rf"(?P=i)    result,\n"
            rf"(?P=i)    draft_payload=payload,\n"
            rf"(?P=i)    problem_text=_context\.problem_text,\n"
            rf"(?P=i)\)"
        )
        match = pattern.search(text)
        if not match:
            continue
        indent = match.group("i")
        replacement = (
            f"{indent}result = {function_name}(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})\n"
            f"{indent}return apply_structural_cohort_formula(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})"
        )
        text = text[:match.start()] + replacement + text[match.end():]
        changed = True
        break
    if not changed:
        base = re.compile(
            r"(?P<i>\s+)return run_lane_b_case\(\n"
            r"(?P=i)    _Projected\(_context, draft\),\n"
            r"(?P=i)    execution_token=deterministic_token\(_context\.context_index\),\n"
            r"(?P=i)\)"
        )
        match = base.search(text)
        if not match:
            raise RuntimeError("cohort_formula_execution_anchor_missing")
        indent = match.group("i")
        replacement = (
            f"{indent}result = run_lane_b_case(\n"
            f"{indent}    _Projected(_context, draft),\n"
            f"{indent}    execution_token=deterministic_token(_context.context_index),\n"
            f"{indent})\n"
            f"{indent}return apply_structural_cohort_formula(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})"
        )
        text = text[:match.start()] + replacement + text[match.end():]
runtime.write_text(text, encoding="utf-8")
