"""Independent, count-oriented completeness checks for parent authorization.

This module deliberately does not call any solve backend.  It receives only the
immutable plan and computes invariants by rank/count algorithms that do not
trust or consume worker roots or worker-reported certificate counts.
"""

from __future__ import annotations

from enum import Enum
from fractions import Fraction
import hashlib
import json
import math
from typing import Any, Iterable

import sympy as sp

from .backends import CompletenessProofKind
from .contracts import SolveBackendKind, SolvePlan
from .translation import TranslatedSystem, TranslationStatus, translate_solve_plan


COMPLETENESS_AUDIT_VERSION = "mechanics-completeness-audit-v1"
_MAX_AUDITED_SOLUTIONS = 1024


class CompletenessAuditStatus(str, Enum):
    success = "success"
    unsupported = "unsupported"
    backend_failure = "backend_failure"
    resource_limit = "resource_limit"


def _closed(status: CompletenessAuditStatus) -> dict[str, Any]:
    return {"status": status.value}


def _success(
    plan: SolvePlan,
    backend: SolveBackendKind,
    proof_kind: CompletenessProofKind,
    *,
    solver_unknown_count: int,
    real_solution_count: int,
    total_multiplicity: int,
    coefficient_rank: int | None = None,
    augmented_rank: int | None = None,
    polynomial_degree: int | None = None,
    canonical_signature: str | None = None,
) -> dict[str, Any]:
    return {
        "status": CompletenessAuditStatus.success.value,
        "audit_version": COMPLETENESS_AUDIT_VERSION,
        "backend": backend.value,
        "graph_fingerprint": plan.graph_fingerprint,
        "plan_fingerprint": plan.plan_fingerprint,
        "proof_kind": proof_kind.value,
        "solver_unknown_count": solver_unknown_count,
        "real_solution_count": real_solution_count,
        "total_multiplicity": total_multiplicity,
        "coefficient_rank": coefficient_rank,
        "augmented_rank": augmented_rank,
        "polynomial_degree": polynomial_degree,
        "canonical_signature": canonical_signature,
    }


def _flatten_expression(expression: Any) -> tuple[Any, ...]:
    if isinstance(expression, sp.MatrixBase):
        return tuple(expression[index, 0] for index in range(expression.rows))
    return (expression,)


def _equations(system: TranslatedSystem) -> tuple[Any, ...]:
    return tuple(
        scalar
        for _, expression in system.equations
        for scalar in _flatten_expression(expression)
    )


def _fraction(value: Any) -> Fraction | None:
    if getattr(value, "is_Rational", None) is not True:
        return None
    try:
        exact = sp.Rational(value)
        return Fraction(int(exact.p), int(exact.q))
    except Exception:
        return None


def _rational_rank(matrix: Any) -> int | None:
    """Exact Gaussian rank, independent from SymPy's backend rank routine."""

    rows: list[list[Fraction]] = []
    for row_index in range(matrix.rows):
        row: list[Fraction] = []
        for column_index in range(matrix.cols):
            value = _fraction(matrix[row_index, column_index])
            if value is None:
                return None
            row.append(value)
        rows.append(row)
    rank = 0
    for column in range(matrix.cols):
        pivot = next(
            (index for index in range(rank, len(rows)) if rows[index][column] != 0),
            None,
        )
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        pivot_value = rows[rank][column]
        rows[rank] = [item / pivot_value for item in rows[rank]]
        for row_index, row in enumerate(rows):
            if row_index == rank or row[column] == 0:
                continue
            factor = row[column]
            rows[row_index] = [
                left - factor * right
                for left, right in zip(row, rows[rank])
            ]
        rank += 1
        if rank == len(rows):
            break
    return rank


def _linear_audit(
    plan: SolvePlan,
    backend: SolveBackendKind,
    system: TranslatedSystem,
) -> dict[str, Any]:
    expressions = _equations(system)
    atoms = system.solver_atoms
    if not expressions or not atoms:
        return _closed(CompletenessAuditStatus.backend_failure)
    try:
        matrix, vector = sp.linear_eq_to_matrix(expressions, atoms)
    except Exception:
        return _closed(CompletenessAuditStatus.unsupported)
    coefficient_rank = _rational_rank(matrix)
    augmented_rank = _rational_rank(matrix.row_join(vector))
    if coefficient_rank is None or augmented_rank is None:
        return _closed(CompletenessAuditStatus.unsupported)
    if coefficient_rank < augmented_rank:
        solution_count = 0
    elif coefficient_rank == augmented_rank == len(atoms):
        solution_count = 1
    else:
        return _closed(CompletenessAuditStatus.unsupported)
    return _success(
        plan,
        backend,
        CompletenessProofKind.linear_rank,
        solver_unknown_count=len(atoms),
        real_solution_count=solution_count,
        total_multiplicity=solution_count,
        coefficient_rank=coefficient_rank,
        augmented_rank=augmented_rank,
    )


def _univariate_audit(
    plan: SolvePlan,
    backend: SolveBackendKind,
    system: TranslatedSystem,
) -> dict[str, Any]:
    expressions = _equations(system)
    atom = system.solver_atoms[0]
    polynomials: list[sp.Poly] = []
    try:
        for expression in expressions:
            polynomial = sp.Poly(expression, atom)
            if not polynomial.is_zero:
                polynomials.append(polynomial)
        if not polynomials:
            return _closed(CompletenessAuditStatus.unsupported)
        common = polynomials[0]
        for polynomial in polynomials[1:]:
            common = sp.gcd(common, polynomial)
        common = common.monic()
        degree = max(0, int(common.degree()))
        distinct_count = 0
        total_multiplicity = 0
        if degree > 0:
            _, square_free_factors = common.sqf_list()
            for factor, multiplicity in square_free_factors:
                # count_roots uses exact interval root counting; unlike the
                # generation worker, this path never constructs any root.
                real_count = int(factor.count_roots(-sp.oo, sp.oo))
                distinct_count += real_count
                total_multiplicity += real_count * int(multiplicity)
    except Exception:
        return _closed(CompletenessAuditStatus.unsupported)
    return _success(
        plan,
        backend,
        CompletenessProofKind.univariate_polynomial_root_count,
        solver_unknown_count=1,
        real_solution_count=distinct_count,
        total_multiplicity=total_multiplicity,
        polynomial_degree=degree,
    )


def _exactly_equal(left: Any, right: Any) -> bool:
    try:
        return left == right or sp.simplify(left - right) == 0
    except Exception:
        return False


def _deduplicate_exact(values: Iterable[Any]) -> tuple[Any, ...]:
    retained: list[Any] = []
    for value in values:
        if not any(_exactly_equal(value, other) for other in retained):
            retained.append(value)
    return tuple(retained)


def _triangular_solutions(
    expressions: tuple[Any, ...],
    atoms: tuple[Any, ...],
) -> tuple[tuple[Any, ...], ...] | None:
    """Enumerate a bounded lexicographic triangular basis, not solve_poly_system."""

    try:
        basis = sp.groebner(expressions, *atoms, order="lex")
    except Exception:
        return None
    if not basis.is_zero_dimensional:
        return None
    basis_expressions = tuple(item.as_expr() for item in basis.polys)

    def descend(index: int, assigned: dict[Any, Any]) -> list[dict[Any, Any]] | None:
        if index < 0:
            for expression in expressions:
                try:
                    residual = sp.simplify(expression.subs(assigned, simultaneous=True))
                except Exception:
                    return None
                if residual != 0 and getattr(residual, "is_zero", None) is not True:
                    return []
            return [dict(assigned)]

        current = atoms[index]
        earlier = set(atoms[:index])
        univariate: list[sp.Poly] = []
        for expression in basis_expressions:
            try:
                specialized = sp.simplify(
                    expression.subs(assigned, simultaneous=True)
                )
            except Exception:
                return None
            free = set(getattr(specialized, "free_symbols", set()))
            if free & earlier:
                continue
            if free - {current}:
                return None
            if current not in free:
                if specialized != 0 and getattr(specialized, "is_zero", None) is not True:
                    return []
                continue
            try:
                univariate.append(sp.Poly(specialized, current, extension=True))
            except Exception:
                return None
        if not univariate:
            return None
        try:
            common = univariate[0]
            for polynomial in univariate[1:]:
                common = sp.gcd(common, polynomial)
            if common.degree() <= 0:
                return []
            roots = _deduplicate_exact(common.all_roots(multiple=True))
        except Exception:
            return None
        results: list[dict[Any, Any]] = []
        for root in roots:
            child = descend(index - 1, {**assigned, current: root})
            if child is None:
                return None
            results.extend(child)
            if len(results) > _MAX_AUDITED_SOLUTIONS:
                return None
        return results

    mappings = descend(len(atoms) - 1, {})
    if mappings is None:
        return None
    solutions = tuple(tuple(mapping[atom] for atom in atoms) for mapping in mappings)
    unique: list[tuple[Any, ...]] = []
    for solution in solutions:
        if not any(
            all(_exactly_equal(left, right) for left, right in zip(solution, other))
            for other in unique
        ):
            unique.append(solution)
    return tuple(unique)


def _finite_real(expression: Any) -> float | None:
    if getattr(expression, "free_symbols", set()):
        return None
    if expression.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
        return None
    if expression.is_real is not True:
        return None
    try:
        value = complex(sp.N(expression, 30))
    except Exception:
        return None
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        return None
    if abs(value.imag) > 1.0e-12 * max(1.0, abs(value.real)):
        return None
    return float(value.real)


def canonical_solution_signature(rows: Iterable[Iterable[float]]) -> str:
    """Hash a canonical finite-real tuple set for cross-process comparison."""

    normalized: list[tuple[str, ...]] = []
    for row in rows:
        exact_row: list[str] = []
        for component in row:
            value = float(component)
            if not math.isfinite(value):
                raise ValueError("solution signatures require finite real values")
            if value == 0.0:
                value = 0.0
            exact_row.append(value.hex())
        normalized.append(tuple(exact_row))
    normalized.sort()
    encoded = json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _multivariate_audit(
    plan: SolvePlan,
    backend: SolveBackendKind,
    system: TranslatedSystem,
) -> dict[str, Any]:
    expressions = _equations(system)
    atoms = system.solver_atoms
    try:
        polynomials = tuple(sp.Poly(item, *atoms).as_expr() for item in expressions)
    except Exception:
        return _closed(CompletenessAuditStatus.unsupported)
    solutions = _triangular_solutions(polynomials, atoms)
    if solutions is None:
        return _closed(CompletenessAuditStatus.unsupported)
    numeric_rows: list[tuple[float, ...]] = []
    exact_real_solutions: list[tuple[Any, ...]] = []
    for solution in solutions:
        reality = tuple(getattr(value, "is_real", None) for value in solution)
        if any(value is None for value in reality):
            return _closed(CompletenessAuditStatus.unsupported)
        if any(value is False for value in reality):
            continue
        row = tuple(_finite_real(value) for value in solution)
        if any(value is None for value in row):
            continue
        numeric_rows.append(tuple(float(value) for value in row if value is not None))
        exact_real_solutions.append(solution)
    try:
        jacobian = sp.Matrix(expressions).jacobian(atoms)
        if any(
            jacobian.subs(dict(zip(atoms, solution))).rank() != len(atoms)
            for solution in exact_real_solutions
        ):
            return _closed(CompletenessAuditStatus.unsupported)
        signature = canonical_solution_signature(numeric_rows)
    except Exception:
        return _closed(CompletenessAuditStatus.unsupported)
    return _success(
        plan,
        backend,
        CompletenessProofKind.multivariate_polynomial_differential,
        solver_unknown_count=len(atoms),
        real_solution_count=len(exact_real_solutions),
        total_multiplicity=len(exact_real_solutions),
        canonical_signature=signature,
    )


def audit_solve_plan(
    plan: SolvePlan,
    backend: SolveBackendKind,
) -> dict[str, Any]:
    """Compute independent completeness invariants from an immutable plan."""

    if backend is not plan.primary_backend or backend not in {
        SolveBackendKind.linear_symbolic,
        SolveBackendKind.polynomial_symbolic,
    }:
        return _closed(CompletenessAuditStatus.unsupported)
    if plan.event_ids or plan.initial_condition_ids:
        return _closed(CompletenessAuditStatus.unsupported)
    translated = translate_solve_plan(plan)
    if translated.status is TranslationStatus.resource_limit:
        return _closed(CompletenessAuditStatus.resource_limit)
    if translated.status is not TranslationStatus.success or translated.system is None:
        return _closed(CompletenessAuditStatus.unsupported)
    system = translated.system
    try:
        if backend is SolveBackendKind.linear_symbolic:
            return _linear_audit(plan, backend, system)
        if len(system.solver_atoms) == 1:
            return _univariate_audit(plan, backend, system)
        return _multivariate_audit(plan, backend, system)
    except MemoryError:
        return _closed(CompletenessAuditStatus.resource_limit)
    except Exception:
        return _closed(CompletenessAuditStatus.backend_failure)


__all__ = [
    "COMPLETENESS_AUDIT_VERSION",
    "CompletenessAuditStatus",
    "audit_solve_plan",
    "canonical_solution_signature",
]
