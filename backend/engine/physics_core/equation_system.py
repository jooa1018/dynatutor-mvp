from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
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
from engine.verification.conditioning import (
    diagnose_jacobian_condition,
    diagnose_local_perturbation,
    diagnose_near_cancellation,
)
from engine.verification.policy import CANDIDATE_ENGINE_ID


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
        _attach_equation_diagnostics(
            equations,
            self.unknowns,
            candidates,
            effective,
        )
        return validate_and_select(candidates, effective)

    def solve(self, context: ValidationContext | None = None) -> list[dict]:
        """Compatibility wrapper returning a mapping only after explicit selection."""

        decision = self.solve_candidates(context)
        if decision.status != "selected" or decision.selected_candidate is None:
            return []
        return [decision.selected_candidate.symbolic_mapping]



def _equation_expression(equation: Any) -> Any:
    return equation.lhs - equation.rhs if isinstance(equation, sp.Equality) else equation



def _evaluated_signed_terms(
    equation: Any,
    substitutions: Mapping[Any, Any],
) -> tuple[float | None, list[float]]:
    """Return an actual residual and signed terms evaluated at one candidate."""

    try:
        if isinstance(equation, sp.Equality):
            left = float(sp.N(equation.lhs.subs(substitutions)))
            right = float(sp.N(equation.rhs.subs(substitutions)))
            values = [left, -right]
            residual = left - right
        else:
            expression = sp.expand(_equation_expression(equation))
            values = [
                float(sp.N(term.subs(substitutions)))
                for term in sp.Add.make_args(expression)
            ]
            residual = sum(values)
    except (TypeError, ValueError, OverflowError):
        return None, []
    if (
        not math.isfinite(residual)
        or any(not math.isfinite(value) for value in values)
    ):
        return None, []
    return residual, values

def _attach_equation_diagnostics(
    equations: Iterable[Any],
    unknowns: Iterable[Any],
    candidates: Iterable[Any],
    context: ValidationContext,
) -> None:
    """Attach actual equation Jacobian evidence without affecting selection."""

    equation_items = list(equations)
    unknown_items = list(unknowns)
    source_ids = tuple(f"equation:{index}" for index in range(len(equation_items)))
    policy = context.tolerance_policy
    try:
        jacobian = sp.Matrix(
            [_equation_expression(equation) for equation in equation_items]
        ).jacobian(unknown_items)
        construction_error: Exception | None = None
    except (TypeError, ValueError, sp.SympifyError) as exc:
        jacobian = [["unavailable"]]
        construction_error = exc

    for candidate in candidates:
        substitutions = {
            **dict(context.substitutions),
            **dict(candidate.symbolic_mapping),
        }
        evaluated = (
            jacobian.subs(substitutions)
            if hasattr(jacobian, "subs")
            else jacobian
        )
        jacobian_check = diagnose_jacobian_condition(
            evaluated,
            policy=policy,
            engine_id=CANDIDATE_ENGINE_ID,
            check_id=f"{candidate.candidate_id}:jacobian_condition",
            source_equation_ids=source_ids,
        )
        payload = jacobian_check.to_dict()
        if construction_error is not None:
            payload["metadata"]["construction_error"] = (
                f"{type(construction_error).__name__}: {construction_error}"
            )

        solution_values = [
            candidate.numerical_mapping.get(str(symbol))
            for symbol in unknown_items
        ]
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in solution_values
        ):
            solution_values = []
        perturbation_check = diagnose_local_perturbation(
            evaluated,
            solution_values=solution_values,
            policy=policy,
            engine_id=CANDIDATE_ENGINE_ID,
            check_id=f"{candidate.candidate_id}:local_perturbation",
            source_equation_ids=source_ids,
        )
        cancellation_checks = []
        for index, equation in enumerate(equation_items):
            residual, signed_terms = _evaluated_signed_terms(
                equation,
                substitutions,
            )
            cancellation_checks.append(
                diagnose_near_cancellation(
                    residual,
                    scale=sum(abs(value) for value in signed_terms)
                    if signed_terms
                    else None,
                    signed_terms=signed_terms,
                    policy=policy,
                    engine_id=CANDIDATE_ENGINE_ID,
                    check_id=(
                        f"{candidate.candidate_id}:equation:{index}:"
                        "near_cancellation"
                    ),
                    source_equation_ids=(f"equation:{index}",),
                ).to_dict()
            )

        candidate.rank_metadata.setdefault(
            "numerical_diagnostics", []
        ).extend(
            [
                payload,
                perturbation_check.to_dict(),
                *cancellation_checks,
            ]
        )

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
