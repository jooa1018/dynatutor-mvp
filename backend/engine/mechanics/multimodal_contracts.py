"""Stage 6 multimodal evidence, conflict, confirmation, and correction contracts."""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from engine.mechanics.contracts import (
    Confidence,
    DirectionBinding,
    DraftQuantity,
    GeometryRelation,
    Identifier,
    MechanicsProblemDraftV1,
    NormalizedBBox,
    NormalizedPoint,
    Query,
    RawUnit,
    RawValue,
    ReferenceFrame,
    Sha256,
    ShortText,
)

FIGURE_OBSERVATION_SCHEMA = "dynatutor.figure_observation"
FIGURE_OBSERVATION_VERSION = "1.0"
MECHANICS_MODELING_ENVELOPE_SCHEMA = "dynatutor.mechanics_modeling_envelope"
MECHANICS_MODELING_ENVELOPE_VERSION = "1.0"
EVIDENCE_CONFLICT_SCHEMA = "dynatutor.evidence_conflict"
EVIDENCE_CONFLICT_VERSION = "1.0"
EVIDENCE_RECONCILIATION_SCHEMA = "dynatutor.evidence_reconciliation"
EVIDENCE_RECONCILIATION_VERSION = "1.0"
CORRECTION_REQUEST_SCHEMA = "dynatutor.mechanics_correction_request"
CORRECTION_REQUEST_VERSION = "1.0"
CORRECTION_REVISION_SCHEMA = "dynatutor.mechanics_correction_revision"
CORRECTION_REVISION_VERSION = "1.0"
MULTIMODAL_EVIDENCE_POLICY_VERSION = "mechanics-multimodal-evidence-v1"
CORRECTION_POLICY_VERSION = "mechanics-correction-revision-v1"

DiagnosticCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
SafeSummary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
]
SourceVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    ),
]


class FrozenStage6Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class InputModality(str, Enum):
    text_only = "text_only"
    text_image = "text_image"
    image_only = "image_only"


class EvidenceSourceType(str, Enum):
    text_explicit = "TEXT_EXPLICIT"
    figure_explicit_label = "FIGURE_EXPLICIT_LABEL"
    figure_explicit_geometry = "FIGURE_EXPLICIT_GEOMETRY"
    figure_convention = "FIGURE_CONVENTION"
    user_confirmed = "USER_CONFIRMED"
    user_corrected = "USER_CORRECTED"
    server_derived = "SERVER_DERIVED"


class ObservationKind(str, Enum):
    entity_label = "entity_label"
    point_label = "point_label"
    quantity_label = "quantity_label"
    unit_label = "unit_label"
    dimension_annotation = "dimension_annotation"
    angle_annotation = "angle_annotation"
    directed_arrow = "directed_arrow"
    force_arrow = "force_arrow"
    velocity_arrow = "velocity_arrow"
    acceleration_arrow = "acceleration_arrow"
    axis = "axis"
    coordinate_frame = "coordinate_frame"
    line_segment = "line_segment"
    circular_path = "circular_path"
    incline_surface = "incline_surface"
    contact = "contact"
    attachment = "attachment"
    rope_path = "rope_path"
    pulley = "pulley"
    rigid_link = "rigid_link"
    spring = "spring"
    slot_or_guide = "slot_or_guide"
    motion_path = "motion_path"
    right_angle_marker = "right_angle_marker"
    fixed_support = "fixed_support"
    event_marker = "event_marker"
    explicit_query_marker = "explicit_query_marker"
    unknown_or_ambiguous = "unknown_or_ambiguous"


class VisibilityState(str, Enum):
    visible = "visible"
    partially_occluded = "partially_occluded"
    occluded = "occluded"
    low_contrast = "low_contrast"
    unknown = "unknown"


class ObservationAmbiguity(str, Enum):
    resolved = "resolved"
    ambiguous = "ambiguous"
    alternatives = "alternatives"
    insufficient_visibility = "insufficient_visibility"


class PolicyEligibility(str, Enum):
    automatic = "automatic"
    confirmation_required = "confirmation_required"
    convention_only = "convention_only"
    rejected = "rejected"


class SemanticTargetKind(str, Enum):
    entity = "entity"
    point = "point"
    quantity = "quantity"
    geometry = "geometry"
    interaction = "interaction"
    constraint = "constraint"
    state_condition = "state_condition"
    query = "query"
    frame = "frame"
    event = "event"
    unknown = "unknown"


class SemanticTargetCandidateV1(FrozenStage6Model):
    kind: SemanticTargetKind
    target_id: Identifier | None = None
    role: Identifier | None = None
    component: Identifier | None = None
    relation_kind: Identifier | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "SemanticTargetCandidateV1":
        if self.kind is not SemanticTargetKind.unknown and self.target_id is None:
            raise ValueError("a resolved semantic target requires target_id")
        return self


class BBoxRegionV1(FrozenStage6Model):
    kind: Literal["bbox"] = "bbox"
    bbox: NormalizedBBox


class PolygonRegionV1(FrozenStage6Model):
    kind: Literal["polygon"] = "polygon"
    points: tuple[NormalizedPoint, ...] = Field(min_length=3, max_length=32)


class LineRegionV1(FrozenStage6Model):
    kind: Literal["line"] = "line"
    start: NormalizedPoint
    end: NormalizedPoint

    @model_validator(mode="after")
    def validate_length(self) -> "LineRegionV1":
        if self.start.x == self.end.x and self.start.y == self.end.y:
            raise ValueError("line endpoints must be distinct")
        return self


ObservationRegionV1: TypeAlias = Annotated[
    Union[BBoxRegionV1, PolygonRegionV1, LineRegionV1], Field(discriminator="kind")
]


class AlternativeInterpretationV1(FrozenStage6Model):
    alternative_id: Identifier
    label: ShortText
    semantic_target: SemanticTargetCandidateV1
    observed_value: RawValue | None = None
    unit_candidate: RawUnit | None = None
    direction_candidate: DirectionBinding | None = None


class FigureObservationV1(FrozenStage6Model):
    schema: Literal[FIGURE_OBSERVATION_SCHEMA] = FIGURE_OBSERVATION_SCHEMA
    version: Literal[FIGURE_OBSERVATION_VERSION] = FIGURE_OBSERVATION_VERSION
    image_id: Identifier
    image_index: int = Field(ge=0, le=7)
    sanitized_content_sha256: Sha256
    width: int = Field(ge=1, le=20_000)
    height: int = Field(ge=1, le=20_000)
    observation_id: Identifier
    observation_kind: ObservationKind
    semantic_target: SemanticTargetCandidateV1
    region: ObservationRegionV1
    observed_label: ShortText | None = None
    observed_value: RawValue | None = None
    unit_candidate: RawUnit | None = None
    direction_candidate: DirectionBinding | None = None
    relation_participant_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=16
    )
    ambiguity_status: ObservationAmbiguity
    alternatives: tuple[AlternativeInterpretationV1, ...] = Field(
        default_factory=tuple, max_length=8
    )
    visibility: VisibilityState
    evidence_origin: EvidenceSourceType
    provenance: EvidenceSourceType
    diagnostic_confidence: Confidence
    policy_eligibility: PolicyEligibility
    source_digest: Sha256
    source_version: SourceVersion
    evidence_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> "FigureObservationV1":
        figure_origins = {
            EvidenceSourceType.figure_explicit_label,
            EvidenceSourceType.figure_explicit_geometry,
            EvidenceSourceType.figure_convention,
        }
        if self.evidence_origin not in figure_origins:
            raise ValueError(
                "figure observation evidence_origin must be figure-scoped"
            )
        if self.provenance not in figure_origins:
            raise ValueError("model observation provenance must be figure-scoped")
        if (
            self.ambiguity_status is ObservationAmbiguity.alternatives
            and len(self.alternatives) < 2
        ):
            raise ValueError("alternative ambiguity requires at least two alternatives")
        if (
            self.ambiguity_status is not ObservationAmbiguity.alternatives
            and self.alternatives
        ):
            raise ValueError("alternatives are allowed only for alternative ambiguity")
        if self.policy_eligibility is PolicyEligibility.automatic:
            if self.ambiguity_status is not ObservationAmbiguity.resolved:
                raise ValueError("automatic evidence must be unambiguous")
            if self.visibility not in {
                VisibilityState.visible,
                VisibilityState.partially_occluded,
            }:
                raise ValueError("automatic evidence must be visibly grounded")
            if self.evidence_origin is EvidenceSourceType.figure_convention:
                raise ValueError("figure convention cannot be silently promoted")
            if self.diagnostic_confidence < 0.80:
                raise ValueError("low-confidence observation requires confirmation")
            if self.semantic_target.kind is SemanticTargetKind.unknown:
                raise ValueError(
                    "automatic evidence requires a resolved semantic target"
                )
        if (
            self.evidence_origin is EvidenceSourceType.figure_convention
            and self.policy_eligibility is not PolicyEligibility.convention_only
        ):
            raise ValueError(
                "figure convention must retain convention-only policy"
            )
        value_like = self.observation_kind in {
            ObservationKind.quantity_label,
            ObservationKind.dimension_annotation,
            ObservationKind.angle_annotation,
        }
        if value_like and self.observed_value is None and self.observed_label is None:
            raise ValueError(
                "value-like observation requires an explicit value or label"
            )
        return self


class TextEvidenceRecordV1(FrozenStage6Model):
    evidence_id: Identifier
    semantic_target: SemanticTargetCandidateV1
    source_type: Literal[EvidenceSourceType.text_explicit] = (
        EvidenceSourceType.text_explicit
    )


class BindingKind(str, Enum):
    corroborates = "corroborates"
    supplies_value = "supplies_value"
    supplies_geometry = "supplies_geometry"
    supplies_direction = "supplies_direction"
    supplies_relation = "supplies_relation"
    supplies_query = "supplies_query"


class EvidenceBindingProposalV1(FrozenStage6Model):
    binding_id: Identifier
    observation_id: Identifier
    evidence_id: Identifier
    semantic_fact_id: Identifier
    semantic_target: SemanticTargetCandidateV1
    binding_kind: BindingKind


class EnvelopeAmbiguityV1(FrozenStage6Model):
    ambiguity_id: Identifier
    summary: SafeSummary
    observation_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=32
    )
    evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=32)


class ModelDiagnosticSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class ModelDiagnosticV1(FrozenStage6Model):
    code: DiagnosticCode
    severity: ModelDiagnosticSeverity
    summary: SafeSummary
    observation_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=32
    )


_FORBIDDEN_ENVELOPE_FIELDS = frozenset(
    {
        "answer",
        "answers",
        "calculated_value",
        "candidate",
        "candidate_selection",
        "confidence_as_authority",
        "equation_solution",
        "executable_equation",
        "expected_answer",
        "expected_value",
        "final_answer",
        "final_value",
        "legacy_route",
        "selected_backend",
        "selected_equation_set",
        "selected_root",
        "selected_solver",
        "solver_result",
        "verification_passed",
        "verification_result",
        "verified",
    }
)


def find_forbidden_multimodal_fields(value: Any) -> tuple[str, ...]:
    """Boundedly reject answer, graph, solver, and verification authority."""

    hits: list[str] = []
    stack: list[tuple[Any, str, int]] = [(value, "", 0)]
    visited = 0
    while stack:
        current, path, depth = stack.pop()
        visited += 1
        if visited > 25_000 or depth > 64:
            raise ValueError("multimodal envelope pre-scan resource limit exceeded")
        if isinstance(current, dict):
            if len(current) > 5_000:
                raise ValueError("multimodal envelope mapping is too large")
            for key, child in current.items():
                if type(key) is not str or len(key) > 256:
                    raise ValueError(
                        "multimodal envelope keys must be bounded strings"
                    )
                normalized = key.strip().lower().replace("-", "_")
                child_path = f"{path}.{key}" if path else key
                if normalized in _FORBIDDEN_ENVELOPE_FIELDS:
                    hits.append(child_path)
                    if len(hits) >= 64:
                        return tuple(hits)
                stack.append((child, child_path, depth + 1))
        elif isinstance(current, (list, tuple)):
            if len(current) > 10_000:
                raise ValueError("multimodal envelope sequence is too large")
            for index, child in enumerate(current):
                child_path = f"{path}.{index}" if path else str(index)
                stack.append((child, child_path, depth + 1))
    return tuple(hits)


class MechanicsModelingEnvelopeV1(FrozenStage6Model):
    schema: Literal[MECHANICS_MODELING_ENVELOPE_SCHEMA] = (
        MECHANICS_MODELING_ENVELOPE_SCHEMA
    )
    version: Literal[MECHANICS_MODELING_ENVELOPE_VERSION] = (
        MECHANICS_MODELING_ENVELOPE_VERSION
    )
    draft: MechanicsProblemDraftV1
    figure_observations: tuple[FigureObservationV1, ...] = Field(
        default_factory=tuple, max_length=512
    )
    text_evidence: tuple[TextEvidenceRecordV1, ...] = Field(
        default_factory=tuple, max_length=512
    )
    proposed_bindings: tuple[EvidenceBindingProposalV1, ...] = Field(
        default_factory=tuple, max_length=512
    )
    unresolved_ambiguities: tuple[EnvelopeAmbiguityV1, ...] = Field(
        default_factory=tuple, max_length=128
    )
    model_diagnostics: tuple[ModelDiagnosticV1, ...] = Field(
        default_factory=tuple, max_length=128
    )

    @model_validator(mode="before")
    @classmethod
    def reject_authority_fields(cls, value: Any) -> Any:
        hits = find_forbidden_multimodal_fields(value)
        if hits:
            raise ValueError(
                "forbidden answer or execution authority in multimodal envelope: "
                + ", ".join(hits[:8])
            )
        return value

    @model_validator(mode="after")
    def validate_cross_references(self) -> "MechanicsModelingEnvelopeV1":
        observation_ids = tuple(
            item.observation_id for item in self.figure_observations
        )
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("figure observation IDs must be unique")
        binding_ids = tuple(item.binding_id for item in self.proposed_bindings)
        if len(set(binding_ids)) != len(binding_ids):
            raise ValueError("proposed binding IDs must be unique")
        evidence_ids = {item.evidence_id for item in self.draft.source_evidence}
        asset_by_id = {item.asset_id: item for item in self.draft.source_assets}
        if len(asset_by_id) != len(self.draft.source_assets):
            raise ValueError("draft source asset IDs must be unique")
        observations = {
            item.observation_id: item for item in self.figure_observations
        }
        for observation in self.figure_observations:
            asset = asset_by_id.get(observation.image_id)
            if asset is None:
                raise ValueError(
                    "figure observation image_id must resolve to a draft source asset"
                )
            if asset.content_sha256 != observation.sanitized_content_sha256:
                raise ValueError(
                    "figure observation digest must match its sanitized source asset"
                )
            if (
                observation.evidence_id is not None
                and observation.evidence_id not in evidence_ids
            ):
                raise ValueError(
                    "figure observation evidence_id must resolve in the draft"
                )
        text_ids = tuple(item.evidence_id for item in self.text_evidence)
        if len(set(text_ids)) != len(text_ids):
            raise ValueError("text evidence records must be unique")
        if any(identifier not in evidence_ids for identifier in text_ids):
            raise ValueError("text evidence record must resolve in the draft")
        for binding in self.proposed_bindings:
            if binding.observation_id not in observations:
                raise ValueError("proposed binding observation_id must resolve")
            if binding.evidence_id not in evidence_ids:
                raise ValueError("proposed binding evidence_id must resolve")
            observation = observations[binding.observation_id]
            if (
                observation.evidence_id is not None
                and observation.evidence_id != binding.evidence_id
            ):
                raise ValueError("binding evidence must agree with its observation")
        for ambiguity in self.unresolved_ambiguities:
            if any(
                identifier not in observations
                for identifier in ambiguity.observation_ids
            ):
                raise ValueError("ambiguity observation references must resolve")
            if any(
                identifier not in evidence_ids
                for identifier in ambiguity.evidence_ids
            ):
                raise ValueError("ambiguity evidence references must resolve")
        return self


class EvidenceConflictKind(str, Enum):
    value_mismatch = "value_mismatch"
    unit_mismatch = "unit_mismatch"
    direction_mismatch = "direction_mismatch"
    entity_binding_mismatch = "entity_binding_mismatch"
    relation_mismatch = "relation_mismatch"
    geometry_mismatch = "geometry_mismatch"
    frame_mismatch = "frame_mismatch"
    event_mismatch = "event_mismatch"
    query_mismatch = "query_mismatch"
    assumption_mismatch = "assumption_mismatch"
    visibility_insufficient = "visibility_insufficient"
    alternative_interpretations = "alternative_interpretations"


class ConflictImpact(str, Enum):
    blocks_compilation = "blocks_compilation"
    blocks_promotion = "blocks_promotion"
    informational = "informational"


class ResolutionAction(str, Enum):
    use_text = "use_text"
    use_figure = "use_figure"
    enter_value = "enter_value"
    choose_alternative = "choose_alternative"
    exclude_fact = "exclude_fact"
    replace_image = "replace_image"
    confirm = "confirm"
    reject = "reject"


class NormalizedEvidenceValueV1(FrozenStage6Model):
    source_id: Identifier
    source_type: EvidenceSourceType
    semantic_target: SemanticTargetCandidateV1
    raw_value: RawValue | None = None
    raw_unit: RawUnit | None = None
    normalized_value: SafeSummary | None = None
    normalized_unit: RawUnit | None = None
    direction_candidate: DirectionBinding | None = None


class EvidenceConflictV1(FrozenStage6Model):
    schema: Literal[EVIDENCE_CONFLICT_SCHEMA] = EVIDENCE_CONFLICT_SCHEMA
    version: Literal[EVIDENCE_CONFLICT_VERSION] = EVIDENCE_CONFLICT_VERSION
    conflict_id: Identifier
    semantic_target: SemanticTargetCandidateV1
    competing_evidence_ids: tuple[Identifier, ...] = Field(
        min_length=2, max_length=8
    )
    conflict_kind: EvidenceConflictKind
    competing_values: tuple[NormalizedEvidenceValueV1, ...] = Field(
        min_length=2, max_length=8
    )
    impact_on_compilation: ConflictImpact
    allowed_resolution_actions: tuple[ResolutionAction, ...] = Field(
        min_length=1, max_length=8
    )
    safe_user_summary: SafeSummary
    revision_fingerprint: Sha256

    @model_validator(mode="after")
    def validate_competitors(self) -> "EvidenceConflictV1":
        if (
            tuple(item.source_id for item in self.competing_values)
            != self.competing_evidence_ids
        ):
            raise ValueError(
                "conflict values must follow competing evidence order"
            )
        if len(set(self.competing_evidence_ids)) != len(
            self.competing_evidence_ids
        ):
            raise ValueError("conflict evidence IDs must be unique")
        if len(set(self.allowed_resolution_actions)) != len(
            self.allowed_resolution_actions
        ):
            raise ValueError("conflict actions must be unique")
        return self


class ConfirmationOptionV1(FrozenStage6Model):
    option_id: Identifier
    label: ShortText
    action: ResolutionAction
    evidence_id: Identifier | None = None
    alternative_id: Identifier | None = None
    requires_user_value: bool = False


class ConfirmationRequestV1(FrozenStage6Model):
    confirmation_id: Identifier
    semantic_target: SemanticTargetCandidateV1
    summary: SafeSummary
    evidence_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=8)
    observation_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=8
    )
    options: tuple[ConfirmationOptionV1, ...] = Field(min_length=1, max_length=8)
    revision_fingerprint: Sha256

    @model_validator(mode="after")
    def validate_options(self) -> "ConfirmationRequestV1":
        option_ids = tuple(item.option_id for item in self.options)
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("confirmation option IDs must be unique")
        return self


class EvidenceReconciliationStatus(str, Enum):
    accepted = "accepted"
    confirmation_required = "confirmation_required"
    insufficient_evidence = "insufficient_evidence"
    correction_required = "correction_required"
    invalid = "invalid"


class EvidenceReconciliationV1(FrozenStage6Model):
    schema: Literal[EVIDENCE_RECONCILIATION_SCHEMA] = (
        EVIDENCE_RECONCILIATION_SCHEMA
    )
    version: Literal[EVIDENCE_RECONCILIATION_VERSION] = (
        EVIDENCE_RECONCILIATION_VERSION
    )
    policy_version: Literal[MULTIMODAL_EVIDENCE_POLICY_VERSION] = (
        MULTIMODAL_EVIDENCE_POLICY_VERSION
    )
    status: EvidenceReconciliationStatus
    accepted_evidence_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=512
    )
    corroborating_evidence_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=512
    )
    duplicate_evidence_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=512
    )
    ambiguous_evidence_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=512
    )
    insufficient_evidence_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=512
    )
    rejected_evidence_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=512
    )
    accepted_figure_evidence_ids: tuple[Identifier, ...] = Field(
        default_factory=tuple, max_length=512
    )
    conflicts: tuple[EvidenceConflictV1, ...] = Field(
        default_factory=tuple, max_length=128
    )
    confirmations: tuple[ConfirmationRequestV1, ...] = Field(
        default_factory=tuple, max_length=128
    )
    revision_fingerprint: Sha256

    @model_validator(mode="after")
    def validate_status(self) -> "EvidenceReconciliationV1":
        collections = (
            self.accepted_evidence_ids,
            self.corroborating_evidence_ids,
            self.duplicate_evidence_ids,
            self.ambiguous_evidence_ids,
            self.insufficient_evidence_ids,
            self.rejected_evidence_ids,
            self.accepted_figure_evidence_ids,
        )
        if any(values != tuple(sorted(set(values))) for values in collections):
            raise ValueError("evidence outcome IDs must be sorted and unique")
        if self.conflicts and self.status not in {
            EvidenceReconciliationStatus.correction_required,
            EvidenceReconciliationStatus.confirmation_required,
        }:
            raise ValueError("unresolved conflicts must block acceptance")
        if (
            self.confirmations
            and self.status is EvidenceReconciliationStatus.accepted
        ):
            raise ValueError("unresolved confirmation must block acceptance")
        if self.status is EvidenceReconciliationStatus.accepted and (
            self.conflicts
            or self.confirmations
            or self.ambiguous_evidence_ids
            or self.insufficient_evidence_ids
        ):
            raise ValueError(
                "accepted reconciliation cannot retain unresolved evidence"
            )
        return self


class CorrectionOperationKind(str, Enum):
    accept_evidence = "accept_evidence"
    reject_evidence = "reject_evidence"
    replace_quantity_value = "replace_quantity_value"
    replace_unit = "replace_unit"
    replace_direction = "replace_direction"
    bind_label_to_entity = "bind_label_to_entity"
    replace_relation = "replace_relation"
    choose_alternative = "choose_alternative"
    add_user_fact = "add_user_fact"
    remove_fact = "remove_fact"
    replace_query = "replace_query"
    replace_frame_or_axis = "replace_frame_or_axis"
    confirm_assumption = "confirm_assumption"
    reject_assumption = "reject_assumption"


class AcceptEvidenceCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.accept_evidence] = (
        CorrectionOperationKind.accept_evidence
    )
    operation_id: Identifier
    evidence_id: Identifier


class RejectEvidenceCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.reject_evidence] = (
        CorrectionOperationKind.reject_evidence
    )
    operation_id: Identifier
    evidence_id: Identifier


class ReplaceQuantityValueCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.replace_quantity_value] = (
        CorrectionOperationKind.replace_quantity_value
    )
    operation_id: Identifier
    quantity_id: Identifier
    raw_value: RawValue
    raw_unit: RawUnit


class ReplaceUnitCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.replace_unit] = (
        CorrectionOperationKind.replace_unit
    )
    operation_id: Identifier
    quantity_id: Identifier
    raw_unit: RawUnit


class ReplaceDirectionCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.replace_direction] = (
        CorrectionOperationKind.replace_direction
    )
    operation_id: Identifier
    quantity_id: Identifier
    direction: DirectionBinding


class BindLabelToEntityCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.bind_label_to_entity] = (
        CorrectionOperationKind.bind_label_to_entity
    )
    operation_id: Identifier
    observation_id: Identifier
    entity_id: Identifier


class ReplaceRelationCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.replace_relation] = (
        CorrectionOperationKind.replace_relation
    )
    operation_id: Identifier
    relation: GeometryRelation


class ChooseAlternativeCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.choose_alternative] = (
        CorrectionOperationKind.choose_alternative
    )
    operation_id: Identifier
    observation_id: Identifier
    alternative_id: Identifier


class AddUserFactCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.add_user_fact] = (
        CorrectionOperationKind.add_user_fact
    )
    operation_id: Identifier
    quantity: DraftQuantity


class RemoveFactCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.remove_fact] = (
        CorrectionOperationKind.remove_fact
    )
    operation_id: Identifier
    fact_id: Identifier


class ReplaceQueryCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.replace_query] = (
        CorrectionOperationKind.replace_query
    )
    operation_id: Identifier
    query: Query


class ReplaceFrameOrAxisCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.replace_frame_or_axis] = (
        CorrectionOperationKind.replace_frame_or_axis
    )
    operation_id: Identifier
    frame: ReferenceFrame


class ConfirmAssumptionCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.confirm_assumption] = (
        CorrectionOperationKind.confirm_assumption
    )
    operation_id: Identifier
    assumption_id: Identifier


class RejectAssumptionCorrectionV1(FrozenStage6Model):
    kind: Literal[CorrectionOperationKind.reject_assumption] = (
        CorrectionOperationKind.reject_assumption
    )
    operation_id: Identifier
    assumption_id: Identifier


CorrectionOperationV1: TypeAlias = Annotated[
    Union[
        AcceptEvidenceCorrectionV1,
        RejectEvidenceCorrectionV1,
        ReplaceQuantityValueCorrectionV1,
        ReplaceUnitCorrectionV1,
        ReplaceDirectionCorrectionV1,
        BindLabelToEntityCorrectionV1,
        ReplaceRelationCorrectionV1,
        ChooseAlternativeCorrectionV1,
        AddUserFactCorrectionV1,
        RemoveFactCorrectionV1,
        ReplaceQueryCorrectionV1,
        ReplaceFrameOrAxisCorrectionV1,
        ConfirmAssumptionCorrectionV1,
        RejectAssumptionCorrectionV1,
    ],
    Field(discriminator="kind"),
]


class MechanicsCorrectionRequestV1(FrozenStage6Model):
    schema: Literal[CORRECTION_REQUEST_SCHEMA] = CORRECTION_REQUEST_SCHEMA
    version: Literal[CORRECTION_REQUEST_VERSION] = CORRECTION_REQUEST_VERSION
    request_id: Identifier
    base_revision_id: Identifier
    base_revision_fingerprint: Sha256
    operations: tuple[CorrectionOperationV1, ...] = Field(
        min_length=1, max_length=64
    )
    client_request_id: Identifier | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_direct_answer_patch(cls, value: Any) -> Any:
        hits = find_forbidden_multimodal_fields(value)
        if hits:
            raise ValueError(
                "correction cannot patch answer, graph, solver, or verification authority"
            )
        return value

    @model_validator(mode="after")
    def validate_operations(self) -> "MechanicsCorrectionRequestV1":
        operation_ids = tuple(item.operation_id for item in self.operations)
        if len(set(operation_ids)) != len(operation_ids):
            raise ValueError("correction operation IDs must be unique")
        return self


class MechanicsCorrectionRevisionV1(FrozenStage6Model):
    schema: Literal[CORRECTION_REVISION_SCHEMA] = CORRECTION_REVISION_SCHEMA
    version: Literal[CORRECTION_REVISION_VERSION] = CORRECTION_REVISION_VERSION
    policy_version: Literal[CORRECTION_POLICY_VERSION] = CORRECTION_POLICY_VERSION
    revision_id: Identifier
    parent_revision_id: Identifier
    revision_number: int = Field(ge=1, le=1_000_000)
    revision_fingerprint: Sha256
    parent_calculation_fingerprint: Sha256
    request_id: Identifier
    operations: tuple[CorrectionOperationV1, ...] = Field(
        min_length=1, max_length=64
    )
    provenance: Literal[EvidenceSourceType.user_corrected] = (
        EvidenceSourceType.user_corrected
    )


__all__ = [
    "AcceptEvidenceCorrectionV1",
    "AddUserFactCorrectionV1",
    "AlternativeInterpretationV1",
    "BBoxRegionV1",
    "BindLabelToEntityCorrectionV1",
    "BindingKind",
    "ChooseAlternativeCorrectionV1",
    "ConflictImpact",
    "ConfirmationOptionV1",
    "ConfirmationRequestV1",
    "CorrectionOperationKind",
    "CorrectionOperationV1",
    "EvidenceBindingProposalV1",
    "EvidenceConflictKind",
    "EvidenceConflictV1",
    "EvidenceReconciliationStatus",
    "EvidenceReconciliationV1",
    "EvidenceSourceType",
    "EnvelopeAmbiguityV1",
    "FigureObservationV1",
    "InputModality",
    "LineRegionV1",
    "MechanicsCorrectionRequestV1",
    "MechanicsCorrectionRevisionV1",
    "MechanicsModelingEnvelopeV1",
    "ModelDiagnosticSeverity",
    "ModelDiagnosticV1",
    "NormalizedEvidenceValueV1",
    "ObservationAmbiguity",
    "ObservationKind",
    "ObservationRegionV1",
    "PolicyEligibility",
    "PolygonRegionV1",
    "RejectAssumptionCorrectionV1",
    "RejectEvidenceCorrectionV1",
    "RemoveFactCorrectionV1",
    "ReplaceDirectionCorrectionV1",
    "ReplaceFrameOrAxisCorrectionV1",
    "ReplaceQuantityValueCorrectionV1",
    "ReplaceQueryCorrectionV1",
    "ReplaceRelationCorrectionV1",
    "ReplaceUnitCorrectionV1",
    "ResolutionAction",
    "SemanticTargetCandidateV1",
    "SemanticTargetKind",
    "TextEvidenceRecordV1",
    "VisibilityState",
    "find_forbidden_multimodal_fields",
]
