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
    interpretation_provenance: str = "legacy_primary"
    selection_eligible: bool = True


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
    route_decision: RouteDecisionModel | None = None
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
    output_key: str | None = None


class AnswerItemModel(BaseModel):
    label: str
    symbol: str | None = None
    numeric: float | None = None
    unit: str | None = None
    display: str
    role: str | None = "primary"
    output_key: str | None = None


class VerificationCheckModel(BaseModel):
    check_id: str
    category: str
    status: str
    applicability: str
    observed: Any = None
    expected: Any = None
    absolute_error: float | None = None
    relative_error: float | None = None
    tolerance: float | None = None
    message: str
    evidence: list[str] = Field(default_factory=list)
    source_equation_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationReport(BaseModel):
    passed: bool
    dimension_summary: str | None = None
    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    structured_checks: list[VerificationCheckModel] = Field(default_factory=list)
    policy_version: str | None = None


class CandidateValidationCheckModel(BaseModel):
    check_id: str
    category: str
    status: str
    message: str
    observed: Any = None
    expected: Any = None
    absolute_error: float | None = None
    relative_error: float | None = None
    tolerance: float | None = None
    evidence: list[str] = Field(default_factory=list)
    source_equation_ids: list[str] = Field(default_factory=list)


class CandidateSolutionModel(BaseModel):
    candidate_id: str
    symbolic_mapping: dict[str, str] = Field(default_factory=dict)
    numerical_mapping: dict[str, float | str] = Field(default_factory=dict)
    unresolved_symbols: list[str] = Field(default_factory=list)
    domain_conditions: list[str] = Field(default_factory=list)
    branch_information: dict[str, Any] = Field(default_factory=dict)
    approximation_method: str | None = None
    initial_guess: dict[str, float | str] = Field(default_factory=dict)
    validation_checks: list[CandidateValidationCheckModel] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    rank_metadata: dict[str, Any] = Field(default_factory=dict)


class ValidatedCandidateModel(CandidateSolutionModel):
    accepted: bool
    checks: list[CandidateValidationCheckModel] = Field(default_factory=list)


class SelectionDecisionModel(BaseModel):
    status: str
    selected_candidate: CandidateSolutionModel | None = None
    valid_alternatives: list[CandidateSolutionModel] = Field(default_factory=list)
    rejected_candidates: list[ValidatedCandidateModel] = Field(default_factory=list)
    selection_policy: str
    explanation: str
    tolerances: dict[str, float] = Field(default_factory=dict)
    policy_version: str
    diagnostics: list[VerificationCheckModel] = Field(default_factory=list)


class ClarificationInputFieldModel(BaseModel):
    symbol: str
    label: str
    unit: str
    input_type: str = "number"
    required: bool = True


class ClarificationOptionModel(BaseModel):
    id: str
    label: str
    description: str = ""
    patch: dict = Field(default_factory=dict)
    needs_value: str | None = None
    input_fields: list[ClarificationInputFieldModel] = Field(default_factory=list)


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
    selection_decision: SelectionDecisionModel | None = None


class FeedbackResponse(BaseModel):
    good_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    corrected_steps: list[str] = Field(default_factory=list)
