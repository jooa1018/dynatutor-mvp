"""Stable public imports for the bounded Stage 4 mechanics solver."""

from engine.mechanics.solver.contracts import *
from engine.mechanics.solver.contracts import __all__ as _solver_contract_exports
from engine.mechanics.solver.engine import (
    SolverExecutionError,
    SolverExecutionStatus,
    SolverRun,
    execute_solve_plan,
    solve_equation_graph,
    solve_graph,
    solve_plan,
)
from engine.mechanics.solver.planner import (
    PlanningFailureCode,
    SolvePlanningError,
    create_solve_plan,
    plan_equation_graph,
)
from engine.mechanics.verification.contracts import (
    EvidenceAdapterV2,
    MechanicsSolveResult,
    MechanicsSolveTerminal,
    VerificationOutcome,
    VerifiedCandidate,
)

__all__ = [
    *_solver_contract_exports,
    "EvidenceAdapterV2",
    "MechanicsSolveResult",
    "MechanicsSolveTerminal",
    "VerificationOutcome",
    "VerifiedCandidate",
    "PlanningFailureCode",
    "SolvePlanningError",
    "SolverExecutionError",
    "SolverExecutionStatus",
    "SolverRun",
    "create_solve_plan",
    "execute_solve_plan",
    "plan_equation_graph",
    "solve_equation_graph",
    "solve_graph",
    "solve_plan",
]
