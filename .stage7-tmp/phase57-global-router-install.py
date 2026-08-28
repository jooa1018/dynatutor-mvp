from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()

MODULE = r'''"""Route globally validated mechanics rules by typed structure.

A rule enters this router only when it is correct on every supported public case
where it fires, never fires on a blocked public class, and has at least two
independent correct public firings.  Runtime keys contain typed physical
structure only; they exclude identifiers, numeric values, case labels, families,
answers, expected terminals, tolerances, and scores.

This is public-development evidence and does not establish hidden-set
generalization.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from engine.mechanics import canonical_fallback, public_closed_form
from engine.mechanics.cohort_formula import StructuralSignature, structural_signature


@dataclass(frozen=True, slots=True)
class RoutedFormulaSolution:
    provider: str
    rule_id: str
    value_si: float
    unit: str


# Replaced by the guarded globally validated selector before commit.
ROUTER: dict[StructuralSignature, tuple[str, str]] = {}


def _provider_candidates(provider: str, draft: dict[str, Any], problem_text: str):
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


def solve_globally_validated_rule(
    draft: dict[str, Any], *, problem_text: str = ""
) -> RoutedFormulaSolution | None:
    selected = ROUTER.get(structural_signature(draft))
    if selected is None:
        return None
    provider, rule_id = selected
    canonical: dict[tuple[str, float], Any] = {}
    for candidate in _provider_candidates(provider, draft, problem_text):
        if candidate.rule_id != rule_id:
            continue
        key = _canonical(provider, candidate)
        if key is not None:
            canonical.setdefault(key, candidate)
    if len(canonical) != 1:
        return None
    candidate = next(iter(canonical.values()))
    try:
        registry = (
            public_closed_form._UREG
            if provider == "public_closed_form"
            else canonical_fallback._UREG
        )
        value_si = float(
            (candidate.value * registry(candidate.unit)).to_base_units().magnitude
        )
    except Exception:
        return None
    if not math.isfinite(value_si):
        return None
    return RoutedFormulaSolution(
        provider=provider,
        rule_id=rule_id,
        value_si=value_si,
        unit=candidate.unit,
    )


__all__ = [
    "ROUTER",
    "RoutedFormulaSolution",
    "solve_globally_validated_rule",
]
'''

ADAPTER = r'''"""Fail-closed Lane B bridge for globally validated rules."""
from __future__ import annotations
from typing import Any

from engine.mechanics.global_rule_router import solve_globally_validated_rule
from evaluation.phase56_stage7.query_binding import derive_query_binding


class _GloballyRoutedLaneResult:
    def __init__(self, base: Any, solution: Any, binding: Any) -> None:
        self._base = base
        self.terminal = "solved"
        self.compiler_status = "globally_validated_rule"
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
            f"globally_validated_rule:{solution.provider}:{solution.rule_id}",
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def apply_globally_validated_rule(
    base: Any, *, draft_payload: dict[str, Any], problem_text: str = ""
) -> Any:
    if getattr(base, "terminal", None) == "solved" and int(
        getattr(base, "verified_candidate_count", 0) or 0
    ) > 0:
        return base
    binding = derive_query_binding(base, draft_payload)
    if binding is None:
        return base
    solution = solve_globally_validated_rule(
        draft_payload, problem_text=problem_text
    )
    if solution is None:
        return base
    return _GloballyRoutedLaneResult(base, solution, binding)


__all__ = ["apply_globally_validated_rule"]
'''

TEST = r'''from types import SimpleNamespace

from engine.mechanics.global_rule_router import ROUTER
from evaluation.phase56_stage7.global_rule_router_adapter import (
    apply_globally_validated_rule,
)


def test_router_is_nonempty_and_contains_no_evaluation_identity() -> None:
    assert ROUTER
    encoded = repr(ROUTER).casefold()
    for token in (
        "case_id", "gold", "answer", "expected_terminal", "tolerance", "family"
    ):
        assert token not in encoded


def test_verified_solution_is_never_overridden() -> None:
    base = SimpleNamespace(terminal="solved", verified_candidate_count=1)
    assert apply_globally_validated_rule(base, draft_payload={}) is base
'''

(ROOT / "backend/engine/mechanics/global_rule_router.py").write_text(MODULE, encoding="utf-8")
(ROOT / "backend/evaluation/phase56_stage7/global_rule_router_adapter.py").write_text(ADAPTER, encoding="utf-8")
(ROOT / "backend/tests/test_phase57_global_rule_router.py").write_text(TEST, encoding="utf-8")

runtime = ROOT / "backend/tools/run_phase56_stage7_v2_shadow_runtime.py"
text = runtime.read_text(encoding="utf-8")
anchor = "from evaluation.phase56_stage7.redaction import (  # noqa: E402\n    assert_privacy_safe_artifact,\n)\n"
new_import = "from evaluation.phase56_stage7.global_rule_router_adapter import (  # noqa: E402\n    apply_globally_validated_rule,\n)\n"
if "global_rule_router_adapter" not in text:
    if anchor not in text:
        raise RuntimeError("global_router_import_anchor_missing")
    text = text.replace(anchor, anchor + new_import, 1)

chain = (
    "apply_structural_cohort_formula",
    "apply_canonical_mechanics_fallback",
    "apply_public_closed_form",
    "apply_typed_closed_form_fallback",
)
if "apply_globally_validated_rule(" not in text:
    changed = False
    for function_name in chain:
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
            f"{indent}return apply_globally_validated_rule(\n"
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
            raise RuntimeError("global_router_execution_anchor_missing")
        indent = match.group("i")
        replacement = (
            f"{indent}result = run_lane_b_case(\n"
            f"{indent}    _Projected(_context, draft),\n"
            f"{indent}    execution_token=deterministic_token(_context.context_index),\n"
            f"{indent})\n"
            f"{indent}return apply_globally_validated_rule(\n"
            f"{indent}    result,\n"
            f"{indent}    draft_payload=payload,\n"
            f"{indent}    problem_text=_context.problem_text,\n"
            f"{indent})"
        )
        text = text[:match.start()] + replacement + text[match.end():]
runtime.write_text(text, encoding="utf-8")
