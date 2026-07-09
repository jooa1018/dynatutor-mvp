from dataclasses import dataclass
from abc import ABC, abstractmethod
from engine.models import CanonicalProblem, SolverResult


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
