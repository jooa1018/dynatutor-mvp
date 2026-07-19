"""Validation-gated mechanics draft normalization and calculation fingerprints."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Collection, Mapping

from engine.mechanics.contracts import (
    IR_SCHEMA_NAME,
    IR_SCHEMA_VERSION,
    IRQuantity,
    MechanicsProblemDraftV1,
    MechanicsProblemIRV1,
)
from engine.mechanics.errors import (
    MechanicsIssueCode,
    MechanicsIssueSeverity,
    MechanicsValidationIssue,
)
from engine.mechanics.units import (
    UnitDimensionError,
    UnitNonFiniteError,
    UnitNormalizationError,
    normalize_quantity,
)
from engine.mechanics.validation import (
    AssumptionAuthorization,
    CorrectionAuthorization,
    DraftValidationResult,
    ValidationTerminal,
    validate_draft,
)


NORMALIZATION_POLICY_VERSION = "mechanics-normalization-v1"
# This names the fixed validation boundary rather than duplicating validation.
VALIDATION_POLICY_VERSION = "mechanics-validation-v1"
VALIDATION_BOUNDARY_POLICY_VERSION = VALIDATION_POLICY_VERSION


@dataclass(frozen=True)
class NormalizationResult:
    terminal: ValidationTerminal
    validation: DraftValidationResult
    ir: MechanicsProblemIRV1 | None
    calculation_fingerprint: str | None
    correction_revision: int

    @property
    def validation_result(self) -> DraftValidationResult:
        return self.validation

    @property
    def issues(self) -> tuple[MechanicsValidationIssue, ...]:
        return self.validation.issues

    @property
    def accepted(self) -> bool:
        return (
            self.terminal is ValidationTerminal.accepted
            and self.ir is not None
            and self.calculation_fingerprint is not None
        )


class _QuantityNormalizationFailure(UnitNormalizationError):
    def __init__(self, index: int, quantity_id: str | None, cause: UnitNormalizationError):
        super().__init__("quantity normalization failed")
        self.index = index
        self.quantity_id = quantity_id
        self.cause = cause


def _normalization_issue(exc: Exception, path: str, quantity_id: str | None) -> MechanicsValidationIssue:
    if isinstance(exc, UnitDimensionError):
        code = MechanicsIssueCode.unit_dimension_mismatch
        message = "raw unit dimension does not match the declared quantity dimension"
    elif isinstance(exc, UnitNonFiniteError):
        code = MechanicsIssueCode.non_finite_value
        message = "raw quantity cannot be converted to a finite bounded SI value"
    else:
        code = MechanicsIssueCode.unit_parse_error
        message = "raw quantity uses unsupported numeric or unit syntax"
    return MechanicsValidationIssue(code, MechanicsIssueSeverity.error, message, path, quantity_id)


def _invalid_result(
    validation: DraftValidationResult,
    issue: MechanicsValidationIssue,
    revision: int,
) -> NormalizationResult:
    failed = DraftValidationResult(ValidationTerminal.invalid, (*validation.issues, issue))
    return NormalizationResult(ValidationTerminal.invalid, failed, None, None, revision)


def _normalized_quantities(draft: MechanicsProblemDraftV1) -> tuple[IRQuantity, ...]:
    quantities: list[IRQuantity] = []
    for index, quantity in enumerate(draft.quantities):
        payload = quantity.model_dump(mode="python")
        if quantity.raw_value is not None:
            try:
                normalized = normalize_quantity(
                    quantity.raw_value, quantity.raw_unit, quantity.shape, quantity.dimension
                )
            except UnitNormalizationError as exc:
                raise _QuantityNormalizationFailure(index, quantity.quantity_id, exc) from exc
            payload["si_value"] = normalized.value
            payload["si_unit"] = normalized.si_unit
        else:
            payload["si_value"] = None
            payload["si_unit"] = None
        try:
            quantities.append(IRQuantity(**payload))
        except Exception as exc:
            # Kept internal: the public caller turns this into a schema issue.
            raise ValueError(f"quantity {index} could not form IR") from exc
    return tuple(quantities)


_DROP_KEYS = frozenset({
    "schema", "version", "validation_policy_version", "normalization_policy_version",
    "metadata", "source_assets", "source_evidence", "raw_value", "raw_unit",
    "evidence_refs", "label", "aliases", "reason", "principle_hints",
    "description", "missing_information", "figure_dependency", "proposed_role",
    "proposed_value", "proposed_unit", "correction_revision", "model_confidence",
})
# Assumption records are top-level explanatory/approval diagnostics.  Keep this
# separate from _DROP_KEYS so a nested calculation authority such as
# IRQuantity.assumption_policy_ref can never be removed by recursive projection.
_TOP_LEVEL_DIAGNOSTIC_KEYS = frozenset({"assumptions"})
_SET_LIKE_KEYS = frozenset({
    "participant_ids", "point_ids", "quantity_ids", "subject_ids", "interval_ids",
    "scope_ids", "referenced_ids", "generalized_coordinate_symbol_ids",
})


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _projection(value: object, *, key: str | None = None, top_level: bool = False) -> object:
    if isinstance(value, dict):
        return {name: _projection(item, key=name) for name, item in value.items() if name not in _DROP_KEYS}
    if isinstance(value, (list, tuple)):
        projected = [_projection(item, key=key) for item in value]
        if top_level or key in _SET_LIKE_KEYS:
            return sorted(projected, key=_canonical_json)
        return projected
    return value


def calculation_fingerprint(ir: MechanicsProblemIRV1) -> str:
    """Hash only normalized physical/calculation structure, never diagnostics."""
    payload = ir.model_dump(mode="json", warnings="none")
    projection = {
        name: _projection(value, key=name, top_level=isinstance(value, (list, tuple)))
        for name, value in payload.items()
        if name not in _DROP_KEYS and name not in _TOP_LEVEL_DIAGNOSTIC_KEYS
    }
    return hashlib.sha256(_canonical_json(projection).encode("utf-8")).hexdigest()


def normalize_draft(
    problem_text: str,
    draft: MechanicsProblemDraftV1,
    *,
    approved_assumption_ids: Collection[str] = (),
    authorized_corrections: Mapping[str, CorrectionAuthorization] | None = None,
    authorized_assumptions: Mapping[str, AssumptionAuthorization] | None = None,
    confirmed_figure_evidence_ids: Collection[str] = (),
) -> NormalizationResult:
    """Validate first; only an accepted draft can ever produce an IR."""
    revision = getattr(getattr(draft, "metadata", None), "correction_revision", 0)
    corrections = {} if authorized_corrections is None else authorized_corrections
    assumptions = {} if authorized_assumptions is None else authorized_assumptions
    validation = validate_draft(
        problem_text,
        draft,
        approved_assumption_ids=approved_assumption_ids,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
        confirmed_figure_evidence_ids=confirmed_figure_evidence_ids,
    )
    if validation.terminal is not ValidationTerminal.accepted:
        return NormalizationResult(validation.terminal, validation, None, None, revision)
    try:
        quantities = _normalized_quantities(draft)
        payload = draft.model_dump(mode="python")
        payload.update({
            "schema": IR_SCHEMA_NAME,
            "version": IR_SCHEMA_VERSION,
            "validation_policy_version": VALIDATION_POLICY_VERSION,
            "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
            "quantities": quantities,
        })
        ir = MechanicsProblemIRV1(**payload)
    except _QuantityNormalizationFailure as exc:
        # The quantity parser exception carries no raw text and is intentionally
        # rendered as one existing, precise validation issue.
        return _invalid_result(
            validation,
            _normalization_issue(exc.cause, f"quantities.{exc.index}", exc.quantity_id),
            revision,
        )
    except Exception:
        issue = MechanicsValidationIssue(
            MechanicsIssueCode.schema_error,
            MechanicsIssueSeverity.error,
            "accepted draft could not be represented as a normalized mechanics IR",
            "normalization",
        )
        return _invalid_result(validation, issue, revision)
    return NormalizationResult(ValidationTerminal.accepted, validation, ir, calculation_fingerprint(ir), revision)


__all__ = [
    "NORMALIZATION_POLICY_VERSION", "VALIDATION_BOUNDARY_POLICY_VERSION", "VALIDATION_POLICY_VERSION",
    "NormalizationResult", "calculation_fingerprint", "normalize_draft",
]
