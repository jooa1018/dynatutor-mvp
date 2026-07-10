from dataclasses import dataclass, field
from typing import Any

from engine.canonical.models import CanonicalProblemV2


@dataclass
class Quantity:
    symbol: str
    value: float | None = None
    unit: str | None = None
    source_text: str | None = None
    # Internal extraction evidence. These additive fields are deliberately absent
    # from the student-facing API and preserve legacy positional construction.
    source_span: tuple[int, int] | None = None
    matched_text: str | None = None
    provenance_hint: str | None = None
    subject_evidence: dict[str, Any] = field(default_factory=dict)
    normalization_evidence: dict[str, Any] | None = None


@dataclass
class CanonicalProblem:
    system_type: str = "unknown"
    subtype: str | None = None
    language: str = "ko"
    objects: list[dict[str, Any]] = field(default_factory=list)
    knowns: dict[str, Quantity] = field(default_factory=dict)
    unknowns: list[str] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    confidence: str = "보통"
    raw_text: str = ""
    surface_type: str | None = None
    pulley_topology: str | None = None
    friction_type: str | None = None
    body_shape: str | None = None
    launch_height: float | None = None
    landing_height: float | None = None
    force_direction: str | None = None
    displacement_direction: str | None = None
    coordinate_data: dict[str, Any] = field(default_factory=dict)
    requested_outputs: list[str] = field(default_factory=list)
    launch_angle_deg: float | None = None
    launch_angle_source: str | None = None
    # Phase 43: provenance-rich internal contract. Legacy solver fields above remain
    # the compatibility view and the student API intentionally does not serialize it.
    canonical_v2: CanonicalProblemV2 | None = None


@dataclass
class LegacyHint:
    problem_type_candidates: list[str] = field(default_factory=list)
    applicable_equations: list[str] = field(default_factory=list)
    not_applicable_equations: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    detected_cues: list[str] = field(default_factory=list)


@dataclass
class TutorDiagnosis:
    canonical: CanonicalProblem
    legacy_hints: LegacyHint
    selected_solver: str | None = None
    solver_reason: str | None = None
    fbd: list[str] = field(default_factory=list)
    coordinate_guide: list[str] = field(default_factory=list)
    applicable_equations: list[str] = field(default_factory=list)
    not_applicable_equations: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    next_questions: list[str] = field(default_factory=list)


@dataclass
class StepCard:
    title: str
    body: str
    math: str | None = None


@dataclass
class Answer:
    symbolic: str | None = None
    numeric: float | None = None
    unit: str | None = None
    display: str | None = None


@dataclass
class AnswerItem:
    label: str
    symbol: str | None = None
    numeric: float | None = None
    unit: str | None = None
    display: str = ""
    role: str | None = "primary"


@dataclass
class VerificationReport:
    passed: bool = True
    dimension_summary: str | None = None
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class SolverResult:
    ok: bool
    answer: Answer | None = None
    answers: list[AnswerItem] = field(default_factory=list)
    steps: list[StepCard] = field(default_factory=list)
    verification: VerificationReport = field(default_factory=VerificationReport)
    unsupported_reason: str | None = None
    used_equations: list[str] = field(default_factory=list)
    fbd: list[str] = field(default_factory=list)
    coordinate_guide: list[str] = field(default_factory=list)
