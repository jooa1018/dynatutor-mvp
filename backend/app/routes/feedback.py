from fastapi import APIRouter

from app.schemas.problem import FeedbackRequest
from app.schemas.solution import FeedbackResponse
from engine.services import feedback_on_solution

router = APIRouter()


@router.post("", response_model=FeedbackResponse)
def feedback(req: FeedbackRequest) -> FeedbackResponse:
    return feedback_on_solution(req.problem_text, req.student_solution)
