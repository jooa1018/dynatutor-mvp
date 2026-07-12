import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.schemas.problem import ProblemRequest
from app.schemas.solution import SolveResponse
from engine.routing.clarify import ClarifyPatchError
from engine.services import solve_problem

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=SolveResponse)
def solve(req: ProblemRequest) -> SolveResponse:
    try:
        return solve_problem(req.problem_text, req.student_solution, clarify_patch=req.clarify_patch, canonical_patch=req.canonical_patch)
    except ClarifyPatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ArithmeticError, ValueError, IndexError) as exc:
        # 잘못된 정의역·수치 조건은 원시 traceback/500 대신 구조화된 422로 반환한다.
        raise HTTPException(
            status_code=422,
            detail="입력값의 물리적 범위 또는 조건 조합을 확인해 주세요.",
        ) from exc
    except Exception as exc:
        trace_id = uuid4().hex
        logger.exception("unexpected solve failure trace_id=%s", trace_id)
        raise HTTPException(
            status_code=500,
            detail=f"내부 계산 오류가 발생했습니다. trace_id={trace_id}",
        ) from exc
