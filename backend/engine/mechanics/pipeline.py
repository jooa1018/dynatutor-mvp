"""Public EquationGraph-only solve and independent-verification pipeline."""

from __future__ import annotations

from engine.mechanics.compiler.contracts import EquationGraph
from engine.mechanics.solver.contracts import SolverBudget
from engine.mechanics.solver.engine import solve_equation_graph
from engine.mechanics.verification.contracts import MechanicsSolveResult
from engine.mechanics.verification.verifier import verify_solver_candidates


def solve_verified_equation_graph(
    graph: EquationGraph,
    budget: SolverBudget | None = None,
) -> MechanicsSolveResult:
    """Generate candidates from one immutable graph, then verify every candidate.

    The embedded graph remains the sole authority.  Planning and backend
    failures are preserved as closed solver diagnostics; no raw text, model
    label, expected answer, or caller-selected backend enters this boundary.
    """

    solver_run = solve_equation_graph(graph, budget)
    return verify_solver_candidates(
        solver_run.plan,
        solver_run.candidate_set,
        solver_run.diagnostics,
    )


solve_verified_graph = solve_verified_equation_graph


__all__ = ["solve_verified_equation_graph", "solve_verified_graph"]
