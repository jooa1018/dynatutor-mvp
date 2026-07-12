import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.schemas.problem import ProblemRequest
from app.schemas.solution import DiagnosisResponse
from engine.errors import PhysicsUserInputError
from engine.services import diagnose_problem

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=DiagnosisResponse)
def diagnose(req: ProblemRequest) -> DiagnosisResponse:
    try:
        return diagnose_problem(req.problem_text, req.student_solution)
    except PhysicsUserInputError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc) or "입력값의 물리적 범위 또는 조건을 확인해 주세요.",
        ) from exc
    except Exception as exc:
        trace_id = uuid4().hex
        logger.exception("unexpected diagnose failure trace_id=%s", trace_id)
        raise HTTPException(
            status_code=500,
            detail=f"내부 진단 오류가 발생했습니다. trace_id={trace_id}",
        ) from exc
