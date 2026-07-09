from fastapi import APIRouter

from app.schemas.problem import ProblemRequest
from app.schemas.solution import DiagnosisResponse
from engine.services import diagnose_problem

router = APIRouter()


@router.post("", response_model=DiagnosisResponse)
def diagnose(req: ProblemRequest) -> DiagnosisResponse:
    return diagnose_problem(req.problem_text, req.student_solution)
