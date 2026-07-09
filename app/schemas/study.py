from pydantic import BaseModel, Field
from app.schemas.examples import ExampleProblemModel
from app.schemas.records import RecordItem, RecordStats


class DailyTask(BaseModel):
    title: str
    body: str
    action: str
    priority: int = 3


class StudyDashboardResponse(BaseModel):
    ok: bool = True
    stats: RecordStats
    due_records: list[RecordItem] = Field(default_factory=list)
    recommended_examples: list[ExampleProblemModel] = Field(default_factory=list)
    daily_plan: list[DailyTask] = Field(default_factory=list)
    weak_types: list[str] = Field(default_factory=list)


class PracticeSetResponse(BaseModel):
    ok: bool = True
    title: str
    category: str | None = None
    difficulty: str | None = None
    examples: list[ExampleProblemModel] = Field(default_factory=list)
