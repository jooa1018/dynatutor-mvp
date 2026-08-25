"""Deterministic bounded solver operations executed in isolated workers."""

from __future__ import annotations

from collections import Counter
from enum import Enum
import math
from typing import Any, Iterable
import warnings

import numpy as np
from scipy import optimize
import sympy as sp

from .contracts import SolveBackendKind, SolvePlan
from .translation import (
    TranslatedSystem,
    TranslationStatus,
    translate_solve_plan,
)


COMPLETENESS_CERTIFICATE_VERSION = "mechanics-completeness-certificate-v1"


class WorkerStatus(str, Enum):
    success = "success"
    unsupported = "unsupported"
    backend_failure = "backend_failure"
    resource_limit = "resource_limit"


class CompletenessProofKind(str, Enum):
    linear_rank = "linear_rank"
    univariate_polynomial_root_count = "univariate_polynomial_root_count"
    multivariate_polynomial_differential = "multivariate_polynomial_differential"
    bounded_numeric_starts = "bounded_numeric_starts"


def _backend_is_approximate(backend: SolveBackendKind) -> bool:
    return backend in {
        SolveBackendKind.numeric_root,
        SolveBackendKind.ode_ivp,
        SolveBackendKind.event_root,
        SolveBackendKind.constrained_optimization,
    }


def _response(
    status: WorkerStatus,
    *,
    complete: bool = False,
    approximate: bool = False,
    roots: list[dict[str, Any]] | None = None,
    overflow: bool = False,
    certificate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "complete": complete,
        "approximate": approximate,
        "roots": roots or [],
        "overflow": overflow,
        "certificate": certificate,
    }


def _certificate(
    plan: SolvePlan,
    backend: SolveBackendKind,
    proof_kind: CompletenessProofKind,
    *,
    solver_unknown_count: int,
    solution_count: int,
    total_multiplicity: int,
    coefficient_rank: int | None = None,
    augmented_rank: int | None = None,
    polynomial_degree: int | None = None,
    independent_solution_count: int | None = None,
    independent_total_multiplicity: int | None = None,
    simple_solution_count: int | None = None,
    numeric_start_count: int | None = None,
) -> dict[str, Any]:
    return {
        "certificate_version": COMPLETENESS_CERTIFICATE_VERSION,
        "backend": backend.value,
        "graph_fingerprint": plan.graph_fingerprint,
        "plan_fingerprint": plan.plan_fingerprint,
        "proof_kind": proof_kind.value,
        "selected_equation_count": len(plan.selected_equality_ids),
        "logical_unknown_count": len(plan.unknown_symbol_ids),
        "solver_unknown_count": solver_unknown_count,
        "solution_count": solution_count,
        "total_multiplicity": total_multiplicity,
        "coefficient_rank": coefficient_rank,
        "augmented_rank": augmented_rank,
        "polynomial_degree": polynomial_degree,
        "independent_solution_count": independent_solution_count,
        "independent_total_multiplicity": independent_total_multiplicity,
        "simple_solution_count": simple_solution_count,
        "numeric_start_count": numeric_start_count,
    }


def _flatten_expression(expression: Any) -> tuple[Any, ...]:
    if isinstance(expression, sp.MatrixBase):
        return tuple(expression[index, 0] for index in range(expression.rows))
    return (expression,)


def _equation_expressions(system: TranslatedSystem) -> tuple[Any, ...]:
    return tuple(
        scalar
        for _, expression in system.equations
        for scalar in _flatten_expression(expression)
    )


def _finite_real_value(expression: Any) -> float | None:
    if getattr(expression, "free_symbols", set()):
        return None
    if expression.has(sp.nan, sp.zoo, sp.oo, -sp.oo):
        return None
    if expression.is_real is False:
        return None
    try:
        numeric = sp.N(expression, 30)
        value = complex(numeric)
    except Exception:
        return None
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        return None
    if abs(value.imag) > 1.0e-12 * max(1.0, abs(value.real)):
        return None
    return float(value.real)


def _pack_solution(
    system: TranslatedSystem,
    atom_values: tuple[Any, ...],
    multiplicity: int,
) -> dict[str, Any] | None:
    if len(atom_values) != len(system.solver_atoms):
        return None
    by_atom = dict(zip(system.solver_atoms, atom_values))
    values: list[dict[str, Any]] = []
    for binding in system.unknowns:
        converted = tuple(_finite_real_value(by_atom[atom]) for atom in binding.atoms)
        if any(item is None for item in converted):
            return None
        value_si: float | list[float]
        if len(converted) == 1:
            value_si = float(converted[0])
        else:
            value_si = [float(item) for item in converted if item is not None]
        values.append({"symbol_id": binding.symbol_id, "value_si": value_si})
    return {"values": values, "root_multiplicity": multiplicity}


def _solution_sort_key(solution: tuple[Any, ...]) -> tuple[tuple[float, str], ...]:
    key: list[tuple[float, str]] = []
    for value in solution:
        real_value = _finite_real_value(value)
        key.append((real_value if real_value is not None else math.inf, sp.srepr(value)))
    return tuple(key)


def _bounded_packed_roots(
    plan: SolvePlan,
    system: TranslatedSystem,
    solutions: Iterable[tuple[tuple[Any, ...], int]],
) -> tuple[list[dict[str, Any]], bool]:
    roots: list[dict[str, Any]] = []
    overflow = False
    for solution, multiplicity in solutions:
        packed = _pack_solution(system, solution, multiplicity)
        if packed is None:
            continue
        if len(roots) >= plan.budget.max_candidates:
            overflow = True
            break
        roots.append(packed)
    return roots, overflow


def _linear_backend(plan: SolvePlan, system: TranslatedSystem) -> dict[str, Any]:
    equations = _equation_expressions(system)
    atoms = system.solver_atoms
    if not equations or not atoms:
        return _response(WorkerStatus.backend_failure)
    try:
        matrix, vector = sp.linear_eq_to_matrix(equations, atoms)
        coefficient_rank = int(matrix.rank())
        augmented_rank = int(matrix.row_join(vector).rank())
        solution_set = sp.linsolve((matrix, vector), atoms)
    except Exception:
        return _response(WorkerStatus.backend_failure)

    if coefficient_rank < augmented_rank:
        if solution_set != sp.EmptySet:
            return _response(WorkerStatus.backend_failure)
        roots: list[dict[str, Any]] = []
        solution_count = 0
    elif coefficient_rank == augmented_rank == len(atoms):
        if not isinstance(solution_set, sp.FiniteSet) or len(solution_set) != 1:
            return _response(WorkerStatus.backend_failure)
        solution = tuple(next(iter(solution_set)))
        if len(solution) != len(atoms) or any(value.free_symbols for value in solution):
            return _response(WorkerStatus.backend_failure)
        packed = _pack_solution(system, solution, 1)
        if packed is None:
            return _response(WorkerStatus.backend_failure)
        roots = [packed]
        solution_count = 1
    else:
        return _response(WorkerStatus.backend_failure)

    certificate = _certificate(
        plan,
        SolveBackendKind.linear_symbolic,
        CompletenessProofKind.linear_rank,
        solver_unknown_count=len(atoms),
        solution_count=solution_count,
        total_multiplicity=solution_count,
        coefficient_rank=coefficient_rank,
        augmented_rank=augmented_rank,
    )
    return _response(
        WorkerStatus.success,
        complete=True,
        roots=roots,
        certificate=certificate,
    )


def _univariate_polynomial_proof(
    equations: tuple[Any, ...],
    atom: Any,
) -> tuple[tuple[tuple[Any, ...], int], ...] | None:
    polynomials: list[sp.Poly] = []
    for expression in equations:
        try:
            polynomial = sp.Poly(expression, atom)
        except Exception:
            return None
        if not polynomial.is_zero:
            polynomials.append(polynomial)
    if not polynomials:
        return None
    try:
        common = polynomials[0]
        for polynomial in polynomials[1:]:
            common = sp.gcd(common, polynomial)
        common = common.monic()
        all_roots = tuple(common.all_roots(multiple=True)) if common.degree() > 0 else ()
        counts = Counter(all_roots)
        emitted = tuple(
            ((root,), multiplicity)
            for root, multiplicity in sorted(
                counts.items(), key=lambda item: _solution_sort_key((item[0],))
            )
            if _finite_real_value(root) is not None
        )
        independent_distinct = 0
        independent_total = 0
        if common.degree() > 0:
            _, factors = common.sqf_list()
            for factor, multiplicity in factors:
                real_count = int(factor.count_roots(-sp.oo, sp.oo))
                independent_distinct += real_count
                independent_total += real_count * int(multiplicity)
    except Exception:
        return None
    if (
        len(emitted) != independent_distinct
        or sum(item[1] for item in emitted) != independent_total
    ):
        return None
    return emitted


def _univariate_polynomial_backend(
    plan: SolvePlan,
    system: TranslatedSystem,
    equations: tuple[Any, ...],
) -> dict[str, Any]:
    atoms = system.solver_atoms
    solutions = _univariate_polynomial_proof(equations, atoms[0])
    if solutions is None:
        return _response(WorkerStatus.backend_failure)
    roots, overflow = _bounded_packed_roots(plan, system, solutions)
    if overflow:
        return _response(
            WorkerStatus.resource_limit,
            roots=roots,
            overflow=True,
        )
    try:
        polynomials = tuple(
            sp.Poly(expression, atoms[0])
            for expression in equations
            if not sp.Poly(expression, atoms[0]).is_zero
        )
        common = polynomials[0]
        for polynomial in polynomials[1:]:
            common = sp.gcd(common, polynomial)
        degree = max(0, int(common.degree()))
    except Exception:
        return _response(WorkerStatus.backend_failure)
    solution_count = len(solutions)
    total_multiplicity = sum(item[1] for item in solutions)
    certificate = _certificate(
        plan,
        SolveBackendKind.polynomial_symbolic,
        CompletenessProofKind.univariate_polynomial_root_count,
        solver_unknown_count=1,
        solution_count=solution_count,
        total_multiplicity=total_multiplicity,
        polynomial_degree=degree,
        independent_solution_count=solution_count,
        independent_total_multiplicity=total_multiplicity,
    )
    return _response(
        WorkerStatus.success,
        complete=True,
        roots=roots,
        certificate=certificate,
    )


def _finite_solution_tuples(
    solution_set: Any,
    atom_count: int,
) -> tuple[tuple[Any, ...], ...] | None:
    if solution_set == sp.EmptySet:
        return ()
    if not isinstance(solution_set, (sp.FiniteSet, tuple, list)):
        return None
    values = tuple(tuple(item) for item in solution_set)
    if any(
        len(item) != atom_count
        or any(getattr(value, "free_symbols", set()) for value in item)
        for item in values
    ):
        return None
    return values


def _tuple_equal(left: tuple[Any, ...], right: tuple[Any, ...]) -> bool:
    try:
        return all(a == b or sp.simplify(a - b) == 0 for a, b in zip(left, right))
    except Exception:
        return False


def _solution_sets_agree(
    left: tuple[tuple[Any, ...], ...],
    right: tuple[tuple[Any, ...], ...],
) -> bool:
    if len(left) != len(right):
        return False
    unmatched = list(right)
    for solution in left:
        matched_index = next(
            (index for index, other in enumerate(unmatched) if _tuple_equal(solution, other)),
            None,
        )
        if matched_index is None:
            return False
        unmatched.pop(matched_index)
    return not unmatched


def _multivariate_polynomial_backend(
    plan: SolvePlan,
    system: TranslatedSystem,
    equations: tuple[Any, ...],
) -> dict[str, Any]:
    atoms = system.solver_atoms
    try:
        polynomials = tuple(sp.Poly(item, *atoms).as_expr() for item in equations)
        primary = _finite_solution_tuples(
            sp.solve_poly_system(polynomials, *atoms), len(atoms)
        )
        secondary = _finite_solution_tuples(
            sp.nonlinsolve(polynomials, atoms), len(atoms)
        )
    except Exception:
        return _response(WorkerStatus.unsupported)
    if primary is None or secondary is None or not _solution_sets_agree(primary, secondary):
        return _response(WorkerStatus.unsupported)

    real_solutions = tuple(
        item
        for item in primary
        if all(_finite_real_value(value) is not None for value in item)
    )
    real_solutions = tuple(sorted(real_solutions, key=_solution_sort_key))
    try:
        jacobian = sp.Matrix(equations).jacobian(atoms)
        simple_count = sum(
            int(jacobian.subs(dict(zip(atoms, solution))).rank() == len(atoms))
            for solution in real_solutions
        )
    except Exception:
        return _response(WorkerStatus.unsupported)
    if simple_count != len(real_solutions):
        return _response(WorkerStatus.unsupported)

    solutions = tuple((item, 1) for item in real_solutions)
    roots, overflow = _bounded_packed_roots(plan, system, solutions)
    if overflow:
        return _response(
            WorkerStatus.resource_limit,
            roots=roots,
            overflow=True,
        )
    solution_count = len(solutions)
    certificate = _certificate(
        plan,
        SolveBackendKind.polynomial_symbolic,
        CompletenessProofKind.multivariate_polynomial_differential,
        solver_unknown_count=len(atoms),
        solution_count=solution_count,
        total_multiplicity=solution_count,
        independent_solution_count=len(tuple(
            item
            for item in secondary
            if all(_finite_real_value(value) is not None for value in item)
        )),
        independent_total_multiplicity=solution_count,
        simple_solution_count=simple_count,
    )
    return _response(
        WorkerStatus.success,
        complete=True,
        roots=roots,
        certificate=certificate,
    )


def _polynomial_backend(plan: SolvePlan, system: TranslatedSystem) -> dict[str, Any]:
    equations = _equation_expressions(system)
    atoms = system.solver_atoms
    if not equations or not atoms:
        return _response(WorkerStatus.backend_failure)
    if len(atoms) == 1:
        return _univariate_polynomial_backend(plan, system, equations)
    return _multivariate_polynomial_backend(plan, system, equations)


def _nonlinear_symbolic_backend(
    plan: SolvePlan,
    system: TranslatedSystem,
) -> dict[str, Any]:
    equations = _equation_expressions(system)
    if any(item.has(sp.Derivative, sp.Integral) for item in equations):
        return _response(WorkerStatus.unsupported)
    # A finite result from one symbolic routine is not an independent proof of
    # completeness or multiplicity. The authorized bounded numeric path must
    # handle these systems until a differential proof is available.
    return _response(WorkerStatus.success, complete=False)


def _numeric_starts(count: int, width: int) -> tuple[tuple[float, ...], ...]:
    starts: list[tuple[float, ...]] = [tuple(0.0 for _ in range(width))]
    for index in range(1, count):
        scale = 10.0 ** (((index - 1) // max(1, 4 * width)) % 5 - 2)
        values = tuple(
            scale
            * (((index * (2 * component + 3) + component) % 17) - 8)
            / 2.0
            for component in range(width)
        )
        starts.append(values)
    return tuple(starts[:count])


_NUMERIC_FUNCTIONS = {
    sp.sin: math.sin,
    sp.cos: math.cos,
    sp.tan: math.tan,
}


def _numeric_expression_supported(
    expression: Any,
    atoms: set[Any],
    *,
    max_nodes: int,
    max_depth: int,
) -> bool:
    stack = [(expression, 1)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > max_nodes or depth > max_depth:
            return False
        if isinstance(node, sp.Symbol):
            if node not in atoms:
                return False
            continue
        if getattr(node, "is_Number", False):
            continue
        if node.func not in {sp.Add, sp.Mul, sp.Pow, *tuple(_NUMERIC_FUNCTIONS)}:
            return False
        stack.extend((argument, depth + 1) for argument in node.args)
    return True


def _numeric_expression_value(
    expression: Any,
    bindings: dict[Any, float],
    *,
    max_nodes: int,
    max_depth: int,
) -> float | None:
    remaining = [max_nodes]

    def finite(value: float) -> float:
        if not math.isfinite(value):
            raise ArithmeticError
        return value

    def visit(node: Any, depth: int) -> float:
        remaining[0] -= 1
        if remaining[0] < 0 or depth > max_depth:
            raise ArithmeticError
        if isinstance(node, sp.Symbol):
            if node not in bindings:
                raise ArithmeticError
            return finite(float(bindings[node]))
        if getattr(node, "is_Number", False):
            return finite(float(node))
        values = tuple(visit(argument, depth + 1) for argument in node.args)
        if node.func is sp.Add:
            result = 0.0
            for value in values:
                result = finite(result + value)
            return result
        if node.func is sp.Mul:
            result = 1.0
            for value in values:
                result = finite(result * value)
            return result
        if node.func is sp.Pow and len(values) == 2:
            base, exponent = values
            exponent_node = node.args[1]
            if base < 0.0 and getattr(exponent_node, "is_integer", None) is not True:
                # Python/complex principal powers can leave the real domain and
                # later cancel back to a real residual.  The numeric fallback is
                # intentionally real-only, so a negative base is accepted only
                # when integrality is established from the immutable expression.
                raise ArithmeticError
            if base == 0.0 and exponent < 0.0:
                raise ZeroDivisionError
            return finite(math.pow(base, exponent))
        function = _NUMERIC_FUNCTIONS.get(node.func)
        if function is not None and len(values) == 1:
            return finite(function(values[0]))
        raise ArithmeticError

    try:
        value = visit(expression, 1)
    except (ArithmeticError, OverflowError, TypeError, ValueError, ZeroDivisionError):
        return None
    return value


def _numeric_backend(plan: SolvePlan, system: TranslatedSystem) -> dict[str, Any]:
    equations = _equation_expressions(system)
    atoms = system.solver_atoms
    if not equations or not atoms:
        return _response(WorkerStatus.unsupported, approximate=True)
    atom_set = set(atoms)
    if any(
        not _numeric_expression_supported(
            expression,
            atom_set,
            max_nodes=plan.budget.max_ast_nodes,
            max_depth=plan.budget.max_ast_depth,
        )
        for expression in equations
    ):
        return _response(WorkerStatus.unsupported, approximate=True)

    def residual(values: Any) -> Any:
        try:
            exact_values = tuple(float(item) for item in values)
        except Exception:
            return np.full(len(equations), np.inf)
        bindings = dict(zip(atoms, exact_values))
        result = tuple(
            _numeric_expression_value(
                expression,
                bindings,
                max_nodes=plan.budget.max_ast_nodes,
                max_depth=plan.budget.max_ast_depth,
            )
            for expression in equations
        )
        if any(item is None for item in result):
            return np.full(len(equations), np.inf)
        return np.asarray(result, dtype=float)

    retained: list[tuple[float, ...]] = []
    starts = _numeric_starts(plan.budget.max_numeric_starts, len(atoms))
    attempted_starts = 0
    for start in starts:
        attempted_starts += 1
        try:
            with warnings.catch_warnings(), np.errstate(all="ignore"):
                warnings.simplefilter("ignore", RuntimeWarning)
                result = optimize.least_squares(
                    residual,
                    np.asarray(start, dtype=float),
                    max_nfev=plan.budget.max_numeric_iterations,
                    xtol=plan.budget.relative_tolerance,
                    ftol=plan.budget.relative_tolerance,
                    gtol=plan.budget.relative_tolerance,
                )
            values = tuple(float(item) for item in result.x)
            errors = residual(values)
        except Exception:
            continue
        if (
            not result.success
            or not all(math.isfinite(item) for item in values)
            or not np.all(np.isfinite(errors))
            or float(np.max(np.abs(errors), initial=0.0))
            > plan.budget.residual_tolerance
        ):
            continue
        duplicate = any(
            all(
                math.isclose(
                    left,
                    right,
                    rel_tol=plan.budget.relative_tolerance,
                    abs_tol=plan.budget.absolute_tolerance,
                )
                for left, right in zip(values, existing)
            )
            for existing in retained
        )
        if not duplicate:
            retained.append(values)
        if len(retained) > plan.budget.max_candidates:
            break
    retained.sort()
    overflow = len(retained) > plan.budget.max_candidates
    retained = retained[: plan.budget.max_candidates]
    symbolic_values = tuple(
        (tuple(sp.Float(item, 17) for item in values), 1)
        for values in retained
    )
    roots, packing_overflow = _bounded_packed_roots(plan, system, symbolic_values)
    if overflow or packing_overflow:
        return _response(
            WorkerStatus.resource_limit,
            approximate=True,
            roots=roots,
            overflow=True,
        )
    if attempted_starts != plan.budget.max_numeric_starts:
        return _response(WorkerStatus.backend_failure, approximate=True)
    certificate = _certificate(
        plan,
        SolveBackendKind.numeric_root,
        CompletenessProofKind.bounded_numeric_starts,
        solver_unknown_count=len(atoms),
        solution_count=len(roots),
        total_multiplicity=len(roots),
        numeric_start_count=attempted_starts,
    )
    return _response(
        WorkerStatus.success,
        complete=True,
        approximate=True,
        roots=roots,
        certificate=certificate,
    )


def run_backend(plan: SolvePlan, backend: SolveBackendKind) -> dict[str, Any]:
    """Run one authorized closed backend and return JSON-compatible data."""

    if backend not in {plan.primary_backend, plan.permitted_numeric_fallback}:
        return _response(
            WorkerStatus.unsupported,
            approximate=_backend_is_approximate(backend),
        )
    if plan.event_ids or plan.initial_condition_ids:
        return _response(
            WorkerStatus.unsupported,
            approximate=_backend_is_approximate(backend),
        )
    translated = translate_solve_plan(plan)
    if translated.status is TranslationStatus.resource_limit:
        return _response(
            WorkerStatus.resource_limit,
            approximate=_backend_is_approximate(backend),
        )
    if translated.status is not TranslationStatus.success or translated.system is None:
        return _response(
            WorkerStatus.unsupported,
            approximate=_backend_is_approximate(backend),
        )
    system = translated.system
    try:
        if backend is SolveBackendKind.linear_symbolic:
            return _linear_backend(plan, system)
        if backend is SolveBackendKind.polynomial_symbolic:
            return _polynomial_backend(plan, system)
        if backend is SolveBackendKind.nonlinear_symbolic:
            return _nonlinear_symbolic_backend(plan, system)
        if backend is SolveBackendKind.numeric_root:
            return _numeric_backend(plan, system)
        return _response(
            WorkerStatus.unsupported,
            approximate=_backend_is_approximate(backend),
        )
    except MemoryError:
        return _response(
            WorkerStatus.resource_limit,
            approximate=_backend_is_approximate(backend),
        )
    except Exception:
        return _response(
            WorkerStatus.backend_failure,
            approximate=_backend_is_approximate(backend),
        )


__all__ = [
    "COMPLETENESS_CERTIFICATE_VERSION",
    "CompletenessProofKind",
    "WorkerStatus",
    "run_backend",
]
