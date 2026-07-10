from pydantic import BaseModel, Field
from typing import Any


class RecordCreate(BaseModel):
    problem_text: str = Field(..., min_length=2)
    student_solution: str | None = None
    solver: str | None = None
    answer_display: str | None = None
    problem_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    raw_result: dict[str, Any] | None = None
    difficulty: str | None = None
    favorite: bool = False
    review_due: str | None = None
    source: str | None = None


class RecordUpdate(BaseModel):
    note: str | None = None
    favorite: bool | None = None
    review_due: str | None = None
    difficulty: str | None = None
    tags: list[str] | None = None
    mastery: int | None = None
    source: str | None = None


class ReviewUpdate(BaseModel):
    correct: bool
    note: str | None = None


class RecordItem(BaseModel):
    id: int
    problem_text: str
    student_solution: str | None = None
    solver: str | None = None
    answer_display: str | None = None
    problem_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    created_at: str
    difficulty: str = "미지정"
    favorite: bool = False
    review_due: str | None = None
    review_count: int = 0
    last_reviewed_at: str | None = None
    mastery: int = 0
    source: str = "manual"


class RecordList(BaseModel):
    ok: bool = True
    records: list[RecordItem] = Field(default_factory=list)


class WeakTypeItem(BaseModel):
    problem_type: str
    count: int


class RecordStats(BaseModel):
    ok: bool = True
    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_solver: dict[str, int] = Field(default_factory=dict)
    top_tags: dict[str, int] = Field(default_factory=dict)
    weakest_types: list[WeakTypeItem] = Field(default_factory=list)
    due_today: int = 0
    favorite_count: int = 0
    average_mastery: float = 0.0


class NotebookExport(BaseModel):
    format: str
    exported_at: str
    count: int
    records: list[dict[str, Any]] = Field(default_factory=list)


class NotebookImportResponse(BaseModel):
    ok: bool = True
    imported: int = 0
    total_after_import: int = 0
