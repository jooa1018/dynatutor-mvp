from fastapi import APIRouter

from app.schemas.llm import AIExplainRequest, AIExplainResponse, LLMStatusResponse
from engine.llm.service import explain_with_optional_llm, llm_status

router = APIRouter()


@router.get("/status", response_model=LLMStatusResponse)
def status() -> LLMStatusResponse:
    return llm_status()


@router.post("/ai", response_model=AIExplainResponse)
def ai_explain(req: AIExplainRequest) -> AIExplainResponse:
    return explain_with_optional_llm(
        problem_text=req.problem_text,
        student_solution=req.student_solution,
        level=req.level,
        style=req.style,
        force_template=req.force_template,
    )
