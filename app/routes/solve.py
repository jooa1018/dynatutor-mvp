from fastapi import APIRouter, HTTPException

from app.schemas.problem import ProblemRequest
from app.schemas.solution import SolveResponse
from engine.routing.clarify import ClarifyPatchError
from engine.services import solve_problem

router = APIRouter()


@router.post("", response_model=SolveResponse)
def solve(req: ProblemRequest) -> SolveResponse:
    try:
        return solve_problem(req.problem_text, req.student_solution, clarify_patch=req.clarify_patch, canonical_patch=req.canonical_patch)
    except ClarifyPatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
