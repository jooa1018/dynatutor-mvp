"""Stable public imports for the bounded Stage 4 mechanics solver."""

from engine.mechanics.solver.contracts import *
from engine.mechanics.solver.contracts import __all__ as _solver_contract_exports
from engine.mechanics.solver.direct_impulse_boundary import (
    install_direct_impulse_boundary_waiver,
    is_direct_impulse_momentum_boundary_graph,
)
from engine.mechanics.solver.constant_acceleration_stop_boundary import (
    install_constant_acceleration_stop_boundary_waiver,
    is_static_constant_acceleration_stop_boundary_graph,
)
from engine.mechanics.solver.spring_natural_length_boundary import (
    install_spring_natural_length_boundary_waiver,
    is_static_spring_natural_length_boundary_graph,
)

# Install before engine/planner imports: both consult the contracts module's
# exact static-boundary recognizer. Each extension admits one reviewed
# algebraic shape and leaves every previously admitted shape intact.
install_direct_impulse_boundary_waiver()
install_constant_acceleration_stop_boundary_waiver()
install_spring_natural_length_boundary_waiver()

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
    "is_direct_impulse_momentum_boundary_graph",
    "is_static_constant_acceleration_stop_boundary_graph",
    "is_static_spring_natural_length_boundary_graph",
    "plan_equation_graph",
    "solve_equation_graph",
    "solve_graph",
    "solve_plan",
]
