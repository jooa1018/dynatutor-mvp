from pydantic import BaseModel, Field


class ExampleProblemModel(BaseModel):
    id: str
    title: str
    category: str
    difficulty: str
    problem_text: str
    learning_goal: str
    tags: list[str] = Field(default_factory=list)
    expected_solver: str


class ExampleListResponse(BaseModel):
    ok: bool = True
    examples: list[ExampleProblemModel] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
