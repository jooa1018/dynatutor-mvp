from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

import sympy as sp

from engine.physics_core.validators import (
    SelectionDecision,
    ValidationContext,
    VariableConstraint,
    candidate_from_mapping,
    filter_physical_solutions,
    numerical_failure_decision,
    validate_and_select,
)


@dataclass
class EquationSystem:
    equations: list
    unknowns: list
    substitutions: dict = field(default_factory=dict)
    constraints: dict[Any, VariableConstraint] | list[VariableConstraint] = field(
        default_factory=dict
    )

    def solve_candidates(
        self, context: ValidationContext | None = None
    ) -> SelectionDecision:
        equations = [
            equation.subs(self.substitutions)
            if hasattr(equation, "subs")
            else equation
            for equation in self.equations
        ]
        base = context or ValidationContext()
        effective = replace(
            base,
            equations=list(base.equations or equations),
            substitutions={
                **dict(self.substitutions),
                **dict(base.substitutions),
            },
            constraints=base.constraints or self.constraints,
        )
        try:
            raw = sp.solve(equations, self.unknowns, dict=True)
        except Exception as exc:
            return numerical_failure_decision(exc, effective)
        candidates = [
            candidate_from_mapping(
                mapping,
                substitutions=effective.substitutions,
                candidate_id=f"candidate-{index}",
                rank_metadata={
                    "solver": "sympy.solve",
                    "unknowns": [str(symbol) for symbol in self.unknowns],
                },
            )
            for index, mapping in enumerate(raw)
        ]
        return validate_and_select(candidates, effective)

    def solve(self, context: ValidationContext | None = None) -> list[dict]:
        """Compatibility wrapper returning a mapping only after explicit selection."""

        decision = self.solve_candidates(context)
        if decision.status != "selected" or decision.selected_candidate is None:
            return []
        return [decision.selected_candidate.symbolic_mapping]


def _physical_value(value: Any) -> float | None:
    try:
        if getattr(value, "is_real", None) is False:
            return None
        numeric = float(sp.N(value))
    except Exception:
        return None
    return numeric if sp.Float(numeric).is_finite else None


__all__ = [
    "EquationSystem",
    "filter_physical_solutions",
]
