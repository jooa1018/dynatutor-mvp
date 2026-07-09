from fastapi import APIRouter, Query
from app.schemas.study import PracticeSetResponse, StudyDashboardResponse
from engine.study import build_practice_set, build_study_dashboard

router = APIRouter()


@router.get("/dashboard", response_model=StudyDashboardResponse)
def dashboard(limit: int = Query(8, ge=1, le=30)) -> StudyDashboardResponse:
    return build_study_dashboard(limit)


@router.get("/practice", response_model=PracticeSetResponse)
def practice(
    category: str | None = Query(None),
    difficulty: str | None = Query(None),
    count: int = Query(6, ge=1, le=20),
) -> PracticeSetResponse:
    return build_practice_set(category, difficulty, count)
