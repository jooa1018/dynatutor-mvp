"""Stable public imports for independent Stage 4 verification and evidence."""

from engine.mechanics.verification.contracts import *
from engine.mechanics.verification.contracts import __all__ as _verification_contract_exports
from engine.mechanics.verification.adapters import (
    LegacyEvidenceProjection,
    LegacyProjectionLimitation,
    LegacyProjectionStatus,
    RejectedCandidateProjection,
    adapt_solver_explanation_evidence,
    build_evidence_adapter,
    build_legacy_evidence_projection,
    build_legacy_verification_report,
    build_solver_explanation_evidence,
    to_legacy_verification_checks,
)
from engine.mechanics.verification.evaluator import (
    EvaluationErrorCode,
    EvaluationResult,
    EvaluationStatus,
    RelationResult,
    evaluate_expression,
    evaluate_relation,
)
from engine.mechanics.verification.verifier import (
    verify_candidates,
    verify_solver_candidates,
)


__all__ = [
    *_verification_contract_exports,
    "EvaluationErrorCode",
    "EvaluationResult",
    "EvaluationStatus",
    "LegacyEvidenceProjection",
    "LegacyProjectionLimitation",
    "LegacyProjectionStatus",
    "RejectedCandidateProjection",
    "RelationResult",
    "adapt_solver_explanation_evidence",
    "build_evidence_adapter",
    "build_legacy_evidence_projection",
    "build_legacy_verification_report",
    "build_solver_explanation_evidence",
    "evaluate_expression",
    "evaluate_relation",
    "to_legacy_verification_checks",
    "verify_candidates",
    "verify_solver_candidates",
]
