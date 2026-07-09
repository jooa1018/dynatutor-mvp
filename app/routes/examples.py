from fastapi import APIRouter, Query

from app.schemas.examples import ExampleListResponse, ExampleProblemModel
from engine.examples.library import example_stats, list_examples

router = APIRouter()


@router.get("", response_model=ExampleListResponse)
def examples(
    category: str | None = Query(None),
    difficulty: str | None = Query(None),
) -> ExampleListResponse:
    return ExampleListResponse(
        examples=[ExampleProblemModel(**e) for e in list_examples(category, difficulty)],
        stats=example_stats(),
    )
