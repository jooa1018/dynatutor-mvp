"""Frozen diagnostics-only contracts for offline or shadow migration checks.

These records can describe differences after independent executions.  They
cannot authorize, select, repair, verify, or replace a generic mechanics
result.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator

from engine.mechanics.solver.contracts import (
    CandidateCoverage,
    CandidateGenerationRecord,
    DiagnosticSeverity,
    Fingerprint,
    FrozenModel,
    Identifier,
    SolveBackendKind,
    SolvePhase,
    SolverDiagnosticCode,
    SolverDiagnosticEntry,
    diagnostic_entry_sort_key,
)
from engine.mechanics.verification.contracts import MechanicsSolveTerminal


MIGRATION_CONTRACT_VERSION = "mechanics-migration-contract-v1"
MIGRATION_PARITY_POLICY_VERSION = "mechanics-migration-parity-policy-v1"
MIGRATION_INVARIANCE_POLICY_VERSION = "mechanics-migration-invariance-policy-v1"
PARITY_ABSOLUTE_TOLERANCE = 1.0e-9
PARITY_RELATIVE_TOLERANCE = 1.0e-9


def _strict_migration_number(value: object) -> float:
    if type(value) not in {int, float}:
        raise ValueError("migration numbers require an exact Python or JSON int/float")
    try:
        normalized = float(value)
    except OverflowError as exc:
        raise ValueError("migration numbers must fit the fixed finite bound") from exc
    if not math.isfinite(normalized) or not -1.0e300 <= normalized <= 1.0e300:
        raise ValueError("migration numbers must be finite and within the fixed bound")
    return normalized


MigrationFiniteFloat = Annotated[
    float,
    BeforeValidator(_strict_migration_number),
    Field(allow_inf_nan=False, ge=-1.0e300, le=1.0e300),
]
MigrationSIValue = MigrationFiniteFloat | Annotated[
    tuple[MigrationFiniteFloat, ...],
    Field(min_length=1, max_length=16),
]
FixedParityTolerance = Annotated[
    Literal[1.0e-9],
    BeforeValidator(_strict_migration_number),
]

CanonicalSIUnit = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=(
            r"^(?:1|(?:kg|m|s|A|K|mol|cd)(?:\^-?[0-9]+)?"
            r"(?:\*(?:kg|m|s|A|K|mol|cd)(?:\^-?[0-9]+)?)*)$"
        ),
    ),
]


class LegacyTerminal(str, Enum):
    """Closed terminal vocabulary exposed by one diagnostic observation."""

    solved = "solved"
    needs_confirmation = "needs_confirmation"
    ambiguity = "ambiguity"
    insufficient_conditions = "insufficient_conditions"
    solver_error = "solver_error"
    timeout = "timeout"
    resource_limit = "resource_limit"
    unsupported = "unsupported"
    not_comparable = "not_comparable"


class LegacyCandidateScalar(FrozenModel):
    """One unique scalar and its exact positive multiplicity."""

    value_si: MigrationFiniteFloat
    multiplicity: StrictInt = Field(ge=1, le=1024)


class LegacyObservation(FrozenModel):
    """Immutable data handed in after an independent diagnostic execution."""

    contract_version: Literal[MIGRATION_CONTRACT_VERSION] = MIGRATION_CONTRACT_VERSION
    case_id: Identifier
    diagnostic_kernel_id: Identifier
    terminal: LegacyTerminal
    query_symbol_id: Identifier | None = None
    si_unit: CanonicalSIUnit | None = None
    selected_scalar_si: MigrationFiniteFloat | None = None
    complete_candidate_scalars_si: tuple[LegacyCandidateScalar, ...] | None = Field(
        default=None,
        max_length=1024,
    )
    residual_passed: StrictBool | None = None

    @field_validator("si_unit")
    @classmethod
    def require_canonical_si_order(cls, value: str | None) -> str | None:
        if value is None or value == "1":
            return value
        base_order = ("kg", "m", "s", "A", "K", "mol", "cd")
        previous = -1
        for factor in value.split("*"):
            pieces = factor.split("^", maxsplit=1)
            base = pieces[0]
            index = base_order.index(base)
            if index <= previous:
                raise ValueError("SI unit factors must use canonical base order without duplicates")
            previous = index
            if len(pieces) == 2:
                exponent = int(pieces[1])
                if pieces[1] != str(exponent):
                    raise ValueError("canonical SI unit powers cannot contain leading zeros")
                if exponent in {0, 1}:
                    raise ValueError("canonical SI units omit zero powers and explicit first powers")
        return value

    @model_validator(mode="after")
    def enforce_observation_shape(self) -> "LegacyObservation":
        comparable = self.terminal is not LegacyTerminal.not_comparable
        if comparable and (self.query_symbol_id is None or self.si_unit is None):
            raise ValueError("comparable observations require both canonical query and SI unit")
        if not comparable and (self.query_symbol_id is not None or self.si_unit is not None):
            raise ValueError("not-comparable observations cannot claim comparable query metadata")
        if not comparable and any(
            item is not None
            for item in (
                self.selected_scalar_si,
                self.complete_candidate_scalars_si,
                self.residual_passed,
            )
        ):
            raise ValueError("not-comparable observations cannot expose result data")
        if (self.terminal is LegacyTerminal.solved) != (self.selected_scalar_si is not None):
            raise ValueError("exactly a solved observation requires a selected scalar")
        candidates = self.complete_candidate_scalars_si
        if candidates is not None:
            values = tuple(item.value_si for item in candidates)
            if len(set(values)) != len(values):
                raise ValueError("candidate scalar entries must be unique; use multiplicity")
            if sum(item.multiplicity for item in candidates) > 1024:
                raise ValueError("candidate scalar multiplicities exceed the observation bound")
        return self


class DifferentialStatus(str, Enum):
    full_parity = "full_parity"
    selected_output_only_match = "selected_output_only_match"
    mismatch = "mismatch"
    not_comparable = "not_comparable"


class DiscrepancyCode(str, Enum):
    observation_not_comparable = "observation_not_comparable"
    query_symbol_mismatch = "query_symbol_mismatch"
    canonical_si_unit_mismatch = "canonical_si_unit_mismatch"
    terminal_mismatch = "terminal_mismatch"
    selected_scalar_mismatch = "selected_scalar_mismatch"
    generic_nonsolved_result = "generic_nonsolved_result"
    generic_query_not_scalar = "generic_query_not_scalar"
    candidate_multiplicity_bound_exceeded = "candidate_multiplicity_bound_exceeded"
    generic_candidates_not_exhaustive = "generic_candidates_not_exhaustive"
    exhaustive_candidates_not_exposed = "exhaustive_candidates_not_exposed"
    candidate_multiset_mismatch = "candidate_multiset_mismatch"
    residual_failed = "residual_failed"
    generic_nonsolved_promotion_forbidden = "generic_nonsolved_promotion_forbidden"


_DISCREPANCY_ORDER = {item: index for index, item in enumerate(DiscrepancyCode)}


class LegacyDifferentialReport(FrozenModel):
    """Diagnostics-only report with no answer-authorizing adapter or check."""

    contract_version: Literal[MIGRATION_CONTRACT_VERSION] = MIGRATION_CONTRACT_VERSION
    policy_version: Literal[MIGRATION_PARITY_POLICY_VERSION] = MIGRATION_PARITY_POLICY_VERSION
    absolute_tolerance: FixedParityTolerance = PARITY_ABSOLUTE_TOLERANCE
    relative_tolerance: FixedParityTolerance = PARITY_RELATIVE_TOLERANCE
    generic_invariance_signature: GenericResultInvarianceSignature
    graph_fingerprint: Fingerprint
    plan_fingerprint: Fingerprint
    primary_backend: SolveBackendKind
    permitted_numeric_fallback: SolveBackendKind | None = None
    generic_terminal: MechanicsSolveTerminal
    generic_candidate_coverage: CandidateCoverage
    generic_generation_complete: StrictBool
    generic_candidate_manifest: tuple[CandidateGenerationRecord, ...] = Field(max_length=1024)
    generic_candidate_ids: tuple[Identifier, ...] = Field(max_length=1024)
    generic_verification_outcomes: tuple[VerificationOutcomeInvarianceRecord, ...] = Field(max_length=1024)
    generic_rejection_authoritative_sha256: tuple[Fingerprint, ...] = Field(max_length=1024)
    generic_verified_candidate_ids: tuple[Identifier, ...] = Field(max_length=1024)
    generic_selected_candidate_id: Identifier | None = None
    observation_case_id: Identifier
    observation_kernel_id: Identifier
    observation_terminal: LegacyTerminal
    observation_sha256: Fingerprint
    status: DifferentialStatus
    discrepancies: tuple[DiscrepancyCode, ...] = Field(max_length=len(DiscrepancyCode))

    @model_validator(mode="after")
    def bind_report_shape(self) -> "LegacyDifferentialReport":
        signature = self.generic_invariance_signature
        duplicated_authority = (
            (self.graph_fingerprint, signature.graph_fingerprint),
            (self.plan_fingerprint, signature.plan_fingerprint),
            (self.primary_backend, signature.primary_backend),
            (self.permitted_numeric_fallback, signature.permitted_numeric_fallback),
            (self.generic_terminal, signature.terminal),
            (self.generic_candidate_coverage, signature.candidate_coverage),
            (self.generic_generation_complete, signature.generation_complete),
            (self.generic_verification_outcomes, signature.verification_outcomes),
            (
                self.generic_rejection_authoritative_sha256,
                signature.rejection_authoritative_sha256,
            ),
            (self.generic_verified_candidate_ids, signature.verified_candidate_ids),
            (self.generic_selected_candidate_id, signature.selected_candidate_id),
        )
        if any(actual != exact for actual, exact in duplicated_authority):
            raise ValueError("duplicated generic report authority must exactly match its signature")
        manifest_ids = tuple(item.candidate_id for item in self.generic_candidate_manifest)
        manifest_indices = tuple(item.generation_index for item in self.generic_candidate_manifest)
        if manifest_indices != tuple(range(len(self.generic_candidate_manifest))):
            raise ValueError("generic candidate manifest order must be contiguous from zero")
        if self.generic_candidate_ids != manifest_ids:
            raise ValueError("generic candidate IDs must exactly follow the bound manifest")
        signature_manifest = tuple(
            (
                item.generation_index,
                item.candidate_id,
                item.backend,
                item.root_index,
                item.branch_ids,
                item.authoritative_sha256,
            )
            for item in signature.candidate_records
        )
        report_manifest = tuple(
            (
                item.generation_index,
                item.candidate_id,
                item.backend,
                item.root_index,
                item.branch_ids,
                item.authoritative_sha256,
            )
            for item in self.generic_candidate_manifest
        )
        if report_manifest != signature_manifest:
            raise ValueError("generic candidate manifest must exactly match its signature")
        if len(set(self.generic_candidate_ids)) != len(self.generic_candidate_ids):
            raise ValueError("generic candidate IDs must be unique")
        if self.generic_selected_candidate_id is not None and self.generic_selected_candidate_id not in self.generic_candidate_ids:
            raise ValueError("generic selected candidate must occur in the bound manifest")
        if (self.generic_terminal is MechanicsSolveTerminal.solved) != (
            self.generic_selected_candidate_id is not None
        ):
            raise ValueError("report selected ID must exactly follow generic solved semantics")
        if self.generic_generation_complete != (
            self.generic_candidate_coverage is not CandidateCoverage.incomplete
        ):
            raise ValueError("generic candidate coverage and completeness must agree")
        if self.discrepancies != tuple(
            sorted(set(self.discrepancies), key=_DISCREPANCY_ORDER.__getitem__)
        ):
            raise ValueError("discrepancies must be unique and canonically ordered")
        discrepancy_set = set(self.discrepancies)
        observation_is_not_comparable = self.observation_terminal is LegacyTerminal.not_comparable
        generic_is_nonsolved = self.generic_terminal is not MechanicsSolveTerminal.solved
        terminals_mismatch = (
            not observation_is_not_comparable
            and self.observation_terminal.value != self.generic_terminal.value
        )
        promotion_forbidden = (
            generic_is_nonsolved
            and self.observation_terminal is LegacyTerminal.solved
        )
        exact_terminal_discrepancies = (
            (
                DiscrepancyCode.observation_not_comparable,
                observation_is_not_comparable,
            ),
            (
                DiscrepancyCode.generic_nonsolved_result,
                generic_is_nonsolved,
            ),
            (
                DiscrepancyCode.terminal_mismatch,
                terminals_mismatch,
            ),
            (
                DiscrepancyCode.generic_nonsolved_promotion_forbidden,
                promotion_forbidden,
            ),
        )
        if any(
            (code in discrepancy_set) != expected
            for code, expected in exact_terminal_discrepancies
        ):
            raise ValueError("terminal discrepancy codes must exactly follow bound terminal semantics")
        if self.status is DifferentialStatus.full_parity and self.discrepancies:
            raise ValueError("full parity cannot contain discrepancies")
        if self.status is DifferentialStatus.full_parity and (
            self.generic_terminal is not MechanicsSolveTerminal.solved
            or self.observation_terminal is not LegacyTerminal.solved
            or not self.generic_generation_complete
            or self.generic_candidate_coverage is not CandidateCoverage.exhaustive_symbolic
        ):
            raise ValueError("full parity requires solved terminals and exhaustive generic authority")
        if self.status is DifferentialStatus.selected_output_only_match and self.discrepancies != (
            DiscrepancyCode.exhaustive_candidates_not_exposed,
        ):
            raise ValueError("selected-output-only match has one exact insufficiency")
        if self.status is DifferentialStatus.selected_output_only_match and (
            self.generic_terminal is not MechanicsSolveTerminal.solved
            or self.observation_terminal is not LegacyTerminal.solved
            or not self.generic_generation_complete
            or self.generic_candidate_coverage is not CandidateCoverage.exhaustive_symbolic
        ):
            raise ValueError("selected-output-only match requires solved terminals and exhaustive generic authority")
        if self.status is DifferentialStatus.mismatch and not self.discrepancies:
            raise ValueError("mismatch requires canonical discrepancy codes")
        not_comparable = {
            DiscrepancyCode.observation_not_comparable,
            DiscrepancyCode.generic_query_not_scalar,
            DiscrepancyCode.generic_nonsolved_result,
            DiscrepancyCode.candidate_multiplicity_bound_exceeded,
        }
        has_comparability_discrepancy = bool(set(self.discrepancies) & not_comparable)
        if (self.status is DifferentialStatus.not_comparable) != has_comparability_discrepancy:
            raise ValueError("not-comparable status must exactly follow comparability discrepancies")
        return self


class CandidateInvarianceRecord(FrozenModel):
    generation_index: StrictInt = Field(ge=0, le=1023)
    candidate_id: Identifier
    backend: SolveBackendKind
    root_index: StrictInt = Field(ge=0, le=1023)
    branch_ids: tuple[Identifier, ...] = Field(default_factory=tuple, max_length=64)
    authoritative_sha256: Fingerprint
    query_value_si: MigrationSIValue
    root_multiplicity: StrictInt = Field(ge=1, le=1024)

    @model_validator(mode="after")
    def bind_candidate_hash(self) -> "CandidateInvarianceRecord":
        if self.candidate_id != f"candidate_{self.authoritative_sha256[:32]}":
            raise ValueError("candidate invariance ID must derive from its authoritative hash")
        if self.branch_ids != tuple(sorted(set(self.branch_ids))):
            raise ValueError("candidate invariance branch IDs must be sorted and unique")
        return self


class VerificationOutcomeInvarianceRecord(FrozenModel):
    candidate_id: Identifier
    passed: StrictBool
    authoritative_sha256: Fingerprint
    rejection_authoritative_sha256: tuple[Fingerprint, ...] = Field(max_length=512)

    @model_validator(mode="after")
    def bind_outcome_shape(self) -> "VerificationOutcomeInvarianceRecord":
        if self.passed == bool(self.rejection_authoritative_sha256):
            raise ValueError("passing outcomes have no rejections; non-passing outcomes require them")
        return self


class DiagnosticEntryInvarianceRecord(FrozenModel):
    code: SolverDiagnosticCode
    severity: DiagnosticSeverity
    phase: SolvePhase
    backend: SolveBackendKind
    referenced_id: Identifier | None = None

    @model_validator(mode="after")
    def bind_entry_semantics(self) -> "DiagnosticEntryInvarianceRecord":
        SolverDiagnosticEntry(
            code=self.code,
            severity=self.severity,
            phase=self.phase,
            backend=self.backend,
            referenced_id=self.referenced_id,
        )
        return self


class DiagnosticAttemptInvarianceRecord(FrozenModel):
    attempt_index: StrictInt = Field(ge=0, le=2047)
    backend: SolveBackendKind
    phase: SolvePhase
    completed: StrictBool


class DiagnosticTimeoutInvarianceRecord(FrozenModel):
    phase: SolvePhase
    backend: SolveBackendKind
    limit_s: MigrationFiniteFloat = Field(gt=0.0, le=1.0e12)


class GenericResultInvarianceSignature(FrozenModel):
    """Deterministic authoritative projection excluding diagnostic timing."""

    contract_version: Literal[MIGRATION_CONTRACT_VERSION] = MIGRATION_CONTRACT_VERSION
    policy_version: Literal[MIGRATION_INVARIANCE_POLICY_VERSION] = MIGRATION_INVARIANCE_POLICY_VERSION
    graph_fingerprint: Fingerprint
    plan_fingerprint: Fingerprint
    primary_backend: SolveBackendKind
    permitted_numeric_fallback: SolveBackendKind | None = None
    candidate_coverage: CandidateCoverage
    generation_complete: StrictBool
    candidate_records: tuple[CandidateInvarianceRecord, ...] = Field(max_length=1024)
    verification_outcomes: tuple[VerificationOutcomeInvarianceRecord, ...] = Field(max_length=1024)
    rejection_authoritative_sha256: tuple[Fingerprint, ...] = Field(max_length=1024)
    verified_candidate_ids: tuple[Identifier, ...] = Field(max_length=1024)
    diagnostic_entries: tuple[DiagnosticEntryInvarianceRecord, ...] = Field(max_length=256)
    diagnostic_attempts: tuple[DiagnosticAttemptInvarianceRecord, ...] = Field(max_length=2048)
    diagnostic_timeout: DiagnosticTimeoutInvarianceRecord | None = None
    terminal: MechanicsSolveTerminal
    selected_candidate_id: Identifier | None = None
    signature_sha256: Fingerprint | None = None

    @model_validator(mode="after")
    def bind_authoritative_projection(self) -> "GenericResultInvarianceSignature":
        indices = tuple(item.generation_index for item in self.candidate_records)
        if indices != tuple(range(len(self.candidate_records))):
            raise ValueError("candidate invariance order must be contiguous from zero")
        candidate_ids = tuple(item.candidate_id for item in self.candidate_records)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate invariance IDs must be unique")
        outcome_ids = tuple(item.candidate_id for item in self.verification_outcomes)
        verified_ids = self.verified_candidate_ids
        if len(set(outcome_ids)) != len(outcome_ids) or len(set(verified_ids)) != len(verified_ids):
            raise ValueError("verification and verified candidate IDs must be unique")
        if outcome_ids != tuple(item for item in candidate_ids if item in set(outcome_ids)):
            raise ValueError("verification outcome invariance must follow candidate order")
        if verified_ids != tuple(item for item in candidate_ids if item in set(verified_ids)):
            raise ValueError("verified candidate invariance must follow candidate order")
        passing_ids = tuple(item.candidate_id for item in self.verification_outcomes if item.passed)
        if verified_ids != passing_ids:
            raise ValueError("verified candidate IDs must be every and only passing outcome")
        aggregate_rejections = tuple(
            rejection_hash
            for item in self.verification_outcomes
            for rejection_hash in item.rejection_authoritative_sha256
        )
        if self.rejection_authoritative_sha256 != aggregate_rejections:
            raise ValueError("top-level rejection hashes must exactly aggregate outcome rejections")
        if self.selected_candidate_id is not None and self.selected_candidate_id not in verified_ids:
            raise ValueError("selected candidate ID must be verified")
        if (self.terminal is MechanicsSolveTerminal.solved) != (self.selected_candidate_id is not None):
            raise ValueError("signature selected ID must exactly follow solved semantics")
        auto_selectable = (
            self.generation_complete
            and self.candidate_coverage is CandidateCoverage.exhaustive_symbolic
        )
        if self.generation_complete != (self.candidate_coverage is not CandidateCoverage.incomplete):
            raise ValueError("signature candidate coverage and completeness must agree")
        if self.terminal is MechanicsSolveTerminal.solved and (
            not auto_selectable
            or len(verified_ids) != 1
            or self.selected_candidate_id != verified_ids[0]
        ):
            raise ValueError("solved signature requires one auto-selectable verified selection")
        if self.terminal is MechanicsSolveTerminal.ambiguity and (
            not auto_selectable or len(verified_ids) < 2
        ):
            raise ValueError("ambiguity signature requires at least two auto-selectable candidates")
        if self.terminal is MechanicsSolveTerminal.needs_confirmation and (
            auto_selectable or not verified_ids
        ):
            raise ValueError("confirmation signature requires non-auto coverage and verified candidates")
        zero_verified_terminals = {
            MechanicsSolveTerminal.insufficient_conditions,
            MechanicsSolveTerminal.solver_error,
            MechanicsSolveTerminal.timeout,
            MechanicsSolveTerminal.resource_limit,
            MechanicsSolveTerminal.unsupported,
        }
        if self.terminal in zero_verified_terminals and verified_ids:
            raise ValueError("closed non-answer signature terminals forbid verified candidates")
        entry_keys = tuple(
            (item.code, item.phase, item.backend, item.referenced_id)
            for item in self.diagnostic_entries
        )
        if len(set(entry_keys)) != len(entry_keys):
            raise ValueError("diagnostic invariance entries must be unique")
        if self.diagnostic_entries != tuple(
            sorted(self.diagnostic_entries, key=diagnostic_entry_sort_key)
        ):
            raise ValueError("diagnostic invariance entries must use canonical order")
        attempt_indices = tuple(item.attempt_index for item in self.diagnostic_attempts)
        if attempt_indices != tuple(range(len(self.diagnostic_attempts))):
            raise ValueError("diagnostic invariance attempt indices must be contiguous")
        timeout_entries = tuple(
            item for item in self.diagnostic_entries
            if item.code is SolverDiagnosticCode.timeout
        )
        if (self.diagnostic_timeout is None) != (len(timeout_entries) == 0):
            raise ValueError("diagnostic timeout entry and provenance are bidirectional")
        if len(timeout_entries) > 1:
            raise ValueError("diagnostic timeout invariance entry must be unique")
        if self.diagnostic_timeout is not None:
            entry = timeout_entries[0]
            if (
                entry.phase is not self.diagnostic_timeout.phase
                or entry.backend is not self.diagnostic_timeout.backend
            ):
                raise ValueError("diagnostic timeout entry must match timeout provenance")
            matching_attempts = tuple(
                item for item in self.diagnostic_attempts
                if item.phase is self.diagnostic_timeout.phase
                and item.backend is self.diagnostic_timeout.backend
                and not item.completed
            )
            if len(matching_attempts) != 1 or matching_attempts[0].attempt_index != len(self.diagnostic_attempts) - 1:
                raise ValueError("diagnostic timeout requires one final matching incomplete attempt")
            if any(not item.completed for item in self.diagnostic_attempts[:-1]):
                raise ValueError("every diagnostic attempt before timeout must be complete")
        expected_hash = _canonical_model_hash(self, exclude_signature=True)
        if "signature_sha256" in self.model_fields_set:
            if self.signature_sha256 is None or self.signature_sha256 != expected_hash:
                raise ValueError("signature SHA-256 must match the authoritative projection")
        else:
            object.__setattr__(self, "signature_sha256", expected_hash)
        return self


class InvarianceVariantKind(str, Enum):
    raw_text_paraphrase = "raw_text_paraphrase"
    system_type_changed = "system_type_changed"
    system_type_removed = "system_type_removed"
    unit_equivalent = "unit_equivalent"


class LabelledInvarianceVariant(FrozenModel):
    label: Identifier
    kind: InvarianceVariantKind
    signature: GenericResultInvarianceSignature


class InvarianceField(str, Enum):
    graph_fingerprint = "graph_fingerprint"
    plan_fingerprint = "plan_fingerprint"
    primary_backend = "primary_backend"
    permitted_numeric_fallback = "permitted_numeric_fallback"
    candidate_coverage = "candidate_coverage"
    generation_complete = "generation_complete"
    candidate_records = "candidate_records"
    verification_outcomes = "verification_outcomes"
    rejection_authoritative_sha256 = "rejection_authoritative_sha256"
    verified_candidate_ids = "verified_candidate_ids"
    diagnostic_entries = "diagnostic_entries"
    diagnostic_attempts = "diagnostic_attempts"
    diagnostic_timeout = "diagnostic_timeout"
    terminal = "terminal"
    selected_candidate_id = "selected_candidate_id"


class InvarianceVariantComparison(FrozenModel):
    label: Identifier
    kind: InvarianceVariantKind
    variant_signature_sha256: Fingerprint
    matches_baseline: StrictBool
    differing_fields: tuple[InvarianceField, ...] = Field(max_length=len(InvarianceField))

    @model_validator(mode="after")
    def bind_comparison(self) -> "InvarianceVariantComparison":
        expected_match = not self.differing_fields
        if self.matches_baseline != expected_match:
            raise ValueError("match flag must exactly reflect differing signature fields")
        if self.differing_fields != tuple(
            item for item in InvarianceField if item in set(self.differing_fields)
        ):
            raise ValueError("differing fields must be unique and canonically ordered")
        return self


class InvarianceComparison(FrozenModel):
    """Bounded field-level comparison; it carries no numeric answer authority."""

    contract_version: Literal[MIGRATION_CONTRACT_VERSION] = MIGRATION_CONTRACT_VERSION
    policy_version: Literal[MIGRATION_INVARIANCE_POLICY_VERSION] = MIGRATION_INVARIANCE_POLICY_VERSION
    baseline_signature_sha256: Fingerprint
    variants: tuple[InvarianceVariantComparison, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def unique_variant_labels(self) -> "InvarianceComparison":
        labels = tuple(item.label for item in self.variants)
        if len(set(labels)) != len(labels):
            raise ValueError("invariance variant labels must be unique")
        return self


def _canonical_model_hash(model: FrozenModel, *, exclude_signature: bool = False) -> str:
    excluded = {"signature_sha256"} if exclude_signature else None
    canonical = json.dumps(
        model.model_dump(mode="json", exclude=excluded),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


LegacyDifferentialReport.model_rebuild()


__all__ = [
    "MIGRATION_CONTRACT_VERSION",
    "MIGRATION_INVARIANCE_POLICY_VERSION",
    "MIGRATION_PARITY_POLICY_VERSION",
    "PARITY_ABSOLUTE_TOLERANCE",
    "PARITY_RELATIVE_TOLERANCE",
    "CandidateInvarianceRecord",
    "CanonicalSIUnit",
    "DiagnosticAttemptInvarianceRecord",
    "DiagnosticEntryInvarianceRecord",
    "DiagnosticTimeoutInvarianceRecord",
    "DifferentialStatus",
    "DiscrepancyCode",
    "GenericResultInvarianceSignature",
    "InvarianceComparison",
    "InvarianceField",
    "InvarianceVariantComparison",
    "InvarianceVariantKind",
    "LabelledInvarianceVariant",
    "LegacyCandidateScalar",
    "LegacyDifferentialReport",
    "LegacyObservation",
    "LegacyTerminal",
    "MigrationFiniteFloat",
    "MigrationSIValue",
    "VerificationOutcomeInvarianceRecord",
]
