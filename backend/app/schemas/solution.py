from pydantic import BaseModel, Field
from typing import Any


class QuantityModel(BaseModel):
    symbol: str
    value: float | None = None
    unit: str | None = None
    source_text: str | None = None


class CanonicalProblemModel(BaseModel):
    system_type: str
    subtype: str | None = None
    language: str = "ko"
    objects: list[dict[str, Any]] = Field(default_factory=list)
    knowns: dict[str, QuantityModel] = Field(default_factory=dict)
    unknowns: list[str] = Field(default_factory=list)
    flags: dict[str, bool] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    confidence: str = "보통"
    surface_type: str | None = None
    pulley_topology: str | None = None
    friction_type: str | None = None
    body_shape: str | None = None
    launch_height: float | None = None
    landing_height: float | None = None
    force_direction: str | None = None
    displacement_direction: str | None = None
    coordinate_data: dict[str, Any] = Field(default_factory=dict)
    requested_outputs: list[str] = Field(default_factory=list)
    launch_angle_deg: float | None = None
    launch_angle_source: str | None = None


class LegacyHintModel(BaseModel):
    problem_type_candidates: list[str] = Field(default_factory=list)
    applicable_equations: list[str] = Field(default_factory=list)
    not_applicable_equations: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    detected_cues: list[str] = Field(default_factory=list)


class RouteCandidateModel(BaseModel):
    solver_id: str
    family: str
    raw_score: int
    normalized_score: float
    evidence: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    supported_outputs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    source_system_type: str | None = None
    source_subtype: str | None = None
    interpretation_score: float = 1.0


class RouteDecisionModel(BaseModel):
    status: str
    candidates: list[RouteCandidateModel] = Field(default_factory=list)
    selected_solver_id: str | None = None
    question: str | None = None
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DiagnosisResponse(BaseModel):
    ok: bool
    fbd_diagram_svg: str | None = None
    fbd_annotations: list[str] = Field(default_factory=list)
    canonical: CanonicalProblemModel
    legacy_hints: LegacyHintModel
    selected_solver: str | None = None
    solver_reason: str | None = None
    fbd: list[str] = Field(default_factory=list)
    coordinate_guide: list[str] = Field(default_factory=list)
    applicable_equations: list[str] = Field(default_factory=list)
    not_applicable_equations: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    physical_model: dict[str, Any] | None = None


class StepCard(BaseModel):
    title: str
    body: str
    math: str | None = None


class AnswerModel(BaseModel):
    symbolic: str | None = None
    numeric: float | None = None
    unit: str | None = None
    display: str | None = None


class AnswerItemModel(BaseModel):
    label: str
    symbol: str | None = None
    numeric: float | None = None
    unit: str | None = None
    display: str
    role: str | None = "primary"


class VerificationReport(BaseModel):
    passed: bool
    dimension_summary: str | None = None
    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ClarificationOptionModel(BaseModel):
    id: str
    label: str
    description: str = ""
    patch: dict = Field(default_factory=dict)
    needs_value: str | None = None


class ClarificationModel(BaseModel):
    rule: str
    question: str
    why: str | None = None
    options: list[ClarificationOptionModel] = Field(default_factory=list)


class SolveResponse(BaseModel):
    ok: bool
    teacher_summary: list[str] = Field(default_factory=list)
    concept_summary: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    study_tips: list[str] = Field(default_factory=list)
    equation_sheet: list[str] = Field(default_factory=list)
    diagnosis: DiagnosisResponse
    answer: AnswerModel | None = None
    answers: list[AnswerItemModel] = Field(default_factory=list)
    steps: list[StepCard] = Field(default_factory=list)
    verification: VerificationReport
    unsupported_reason: str | None = None
    clarification: ClarificationModel | None = None
    route_decision: RouteDecisionModel | None = None
    physical_model: dict[str, Any] | None = None


class FeedbackResponse(BaseModel):
    good_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    corrected_steps: list[str] = Field(default_factory=list)
