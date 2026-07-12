from dataclasses import dataclass
from abc import ABC, abstractmethod

from engine.models import CanonicalProblem, SolverResult
from engine.physics_core.validators import (
    CandidateSolveBatch,
    candidate_from_solver_result,
)


@dataclass
class SolverMatch:
    solver: "BaseSolver"
    score: int
    reason: str


class BaseSolver(ABC):
    name: str = "base"
    reason: str = ""

    @abstractmethod
    def match(self, c: CanonicalProblem) -> SolverMatch | None:
        pass

    @abstractmethod
    def solve(self, c: CanonicalProblem) -> SolverResult:
        pass

    def solve_candidates(self, c: CanonicalProblem, *args, **kwargs) -> CandidateSolveBatch:
        """Run a legacy solver and expose its result through the common candidate path.

        Solvers that produce multiple mathematical branches override this method.
        Direct-formula solvers naturally contribute one candidate.
        """

        result = self.solve(c, *args, **kwargs)
        candidate = candidate_from_solver_result(
            result,
            candidate_id=f"{self.name}-candidate-0",
            requested_outputs=c.requested_outputs,
        )
        return CandidateSolveBatch(result=result, candidates=[candidate])
