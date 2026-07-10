from pydantic import BaseModel, Field
from typing import Any


class AIExplainRequest(BaseModel):
    problem_text: str = Field(..., min_length=2)
    student_solution: str | None = None
    level: str = Field("beginner", description="beginner, college, concise 등 설명 톤")
    style: str = Field("friendly", description="friendly, concise, socratic")
    force_template: bool = Field(False, description="True이면 실제 LLM 호출 없이 안전 템플릿 설명만 반환")


class LLMStatusResponse(BaseModel):
    enabled: bool
    provider: str
    model: str | None = None
    reason: str | None = None
    base_url: str | None = None


class LockedFacts(BaseModel):
    problem_type: str
    selected_solver: str | None = None
    solver_ok: bool = False
    answer_display: str | None = None
    answer_numbers: list[float] = Field(default_factory=list)
    answer_unit: str | None = None
    answers: list[dict[str, Any]] = Field(default_factory=list)
    unsupported_reason: str | None = None
    equations: list[str] = Field(default_factory=list)
    not_applicable_equations: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    known_values: dict[str, str] = Field(default_factory=dict)
    allowed_numbers: list[float] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    locked_hash: str | None = None
    locked_facts_version: str = "phase22"


class AIExplainResponse(BaseModel):
    ok: bool
    used_llm: bool
    provider: str
    model: str | None = None
    explanation: str
    fallback_explanation: str
    locked_facts: LockedFacts
    integrity_passed: bool
    integrity_warnings: list[str] = Field(default_factory=list)
    integrity_report: dict[str, Any] = Field(default_factory=dict)
    displayed_source: str = "template"
    prompt_preview: str | None = None
    raw_usage: dict[str, Any] | None = None
