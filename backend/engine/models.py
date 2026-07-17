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
    # Explicit semantic provenance for legacy solvers that return one Answer
    # instead of typed AnswerItems.  It must describe the computed quantity,
    # never the caller's requested output.
    output_key: str | None = None


_LEGACY_OUTPUT_KEY_BY_SYMBOL = {
    "t": "time",
    "R": "range",
    "delta_x": "distance",
    "Δx": "distance",
    "s": "distance",
    "x": "distance",
    "H": "max_height",
    "v_min": "minimum_speed",
    "v0": "initial_velocity",
    "v_i": "initial_velocity",
    "vf": "final_velocity",
    "v_f": "final_velocity",
    "v1'": "v1_after",
    "v2'": "v2_after",
    "v": "final_velocity",
    "v_r": "final_velocity",
    "v_θ": "final_velocity",
    "vB": "final_velocity",
    "v_B": "final_velocity",
    "a": "acceleration",
    "aB": "acceleration",
    "a_B": "acceleration",
    "F": "force",
    "F_net": "force",
    "f_k": "friction_force",
    "f_s": "friction_force",
    "f_s,max": "friction_force",
    "F_f": "friction_force",
    "N": "normal_force",
    "N1": "normal_force",
    "N2": "normal_force",
    "m": "mass",
    "W": "work",
    "J": "impulse",
    "K": "kinetic_energy",
    "KE": "kinetic_energy",
    "U": "potential_energy",
    "PE": "potential_energy",
    "E_s": "elastic_energy",
    "omega_n": "angular_frequency",
    "ω_n": "angular_frequency",
    "omega_f": "angular_velocity",
    "omega": "angular_velocity",
    "ω": "angular_velocity",
    "alpha": "angular_acceleration",
    "α": "angular_acceleration",
    "v_t": "tangential_velocity",
    "a_c": "centripetal_acceleration",
    "T1": "tension",
    "T2": "tension",
}


@dataclass
class AnswerItem:
    label: str
    symbol: str | None = None
    numeric: float | None = None
    unit: str | None = None
    display: str = ""
    role: str | None = "primary"
    output_key: str | None = None

    def __post_init__(self) -> None:
        if self.output_key is None and self.symbol is not None:
            self.output_key = _LEGACY_OUTPUT_KEY_BY_SYMBOL.get(self.symbol)


@dataclass
class VerificationReport:
    passed: bool = True
    dimension_summary: str | None = None
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Additive Phase 48 evidence; legacy string views remain stable.
    structured_checks: list[dict[str, Any]] = field(default_factory=list)
    policy_version: str | None = None


@dataclass(frozen=True)
class CalculationCoordinateFrame:
    """Coordinate/sign convention actually used by a solver calculation.

    ``source`` and ``status`` are mandatory provenance.  A physical-model
    default must be represented as ``status="default"`` (or ``"unresolved"``),
    never promoted to a resolved calculation frame by the public trace builder.
    """

    frame_id: str
    coordinate_system: str
    axes: tuple[str, ...] = ()
    positive_directions: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    source: str = "solver_calculation"
    status: str = "resolved"


@dataclass(frozen=True)
class SemanticFactEvidence:
    """A normalized semantic fact; never raw problem/student source text."""

    fact_id: str
    semantic_key: str
    value: str | float | int | bool | None
    unit: str | None = None
    source: str = "canonical"
    classification: str = "explicit"
    status: str = "resolved"


@dataclass(frozen=True)
class EquationEvidence:
    """An equation with explicit provenance and dependency links."""

    equation_id: str
    expression: str
    source: str
    provenance: str
    fact_ids: tuple[str, ...] = ()
    input_output_ids: tuple[str, ...] = ()
    output_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubstitutionEvidence:
    """A numeric/symbolic substitution linked to its equation and output."""

    substitution_id: str
    equation_id: str
    expression: str
    output_id: str
    fact_ids: tuple[str, ...] = ()
    input_output_ids: tuple[str, ...] = ()
    source: str = "solver_calculation"


@dataclass(frozen=True)
class OutputEvidenceLink:
    """Exact selected-candidate link for one delivered response item."""

    output_id: str
    output_key: str
    candidate_id: str
    numeric: float | int
    unit: str | None
    symbol: str | None = None
    role: str | None = None
    response_index: int | None = None
    equation_ids: tuple[str, ...] = ()
    substitution_ids: tuple[str, ...] = ()
    # Phase 53 keeps the solver's selected physics candidate distinct from the
    # service's post-format delivery candidate.  These fields are appended with
    # defaults so legacy positional construction remains source compatible.
    candidate_key: str = ""
    candidate_numeric: float | int | None = None
    delivery_candidate_id: str = ""
    delivery_candidate_key: str = ""
    delivery_transform: str = "identity"
    decimal_places: int | None = None
    delivery_policy_id: str = ""


@dataclass(frozen=True)
class SolverExplanationEvidence:
    """Immutable solver-produced provenance consumed by ExplanationTrace v1."""

    coordinate_frame: CalculationCoordinateFrame | None = None
    explicit_facts: tuple[SemanticFactEvidence, ...] = ()
    assumptions: tuple[SemanticFactEvidence, ...] = ()
    equations: tuple[EquationEvidence, ...] = ()
    substitutions: tuple[SubstitutionEvidence, ...] = ()
    outputs: tuple[OutputEvidenceLink, ...] = ()
    candidate_summary: str | None = None
    validation_summary: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


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
    # Additive Phase 47 diagnostics, serialized through the API adapter.
    selection_decision: Any | None = None
    # Additive Phase 53 provenance.  Legacy solvers intentionally leave this
    # unset until their Wave 2 structured-evidence migration.
    explanation_evidence: SolverExplanationEvidence | None = None
