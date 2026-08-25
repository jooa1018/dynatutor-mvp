"""Deterministic execution of one server-held multimodal revision."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from engine.mechanics.compiler import MechanicsCompiler, authorize_validated_mechanics_ir
from engine.mechanics.multimodal_revision import ModelingRevision
from engine.mechanics.normalization import normalize_draft
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.verification.contracts import MechanicsSolveTerminal

MULTIMODAL_RUNTIME_VERSION = "mechanics-multimodal-runtime-v1"


class MultimodalRuntimeTerminal(StrEnum):
    reconciliation_required = "reconciliation_required"
    validation_rejected = "validation_rejected"
    authorization_failed = "authorization_failed"
    compiler_rejected = "compiler_rejected"
    solve_rejected = "solve_rejected"
    solved = "solved"
    failed = "failed"


@dataclass(frozen=True, slots=True)
class MultimodalRuntimeResult:
    terminal: MultimodalRuntimeTerminal
    normalization_terminal: str | None = None
    validation_issue_codes: tuple[str, ...] = ()
    compiler_status: str | None = None
    compiler_issue_codes: tuple[str, ...] = ()
    solve_terminal: str | None = None
    solve_diagnostic_codes: tuple[str, ...] = ()
    authorized_ir_fingerprint: str | None = None
    applied_law_ids: tuple[str, ...] = ()
    equation_count: int = 0
    candidate_count: int = 0
    rejected_candidate_count: int = 0
    verification_checks: tuple[dict[str, str], ...] = ()
    verified_answer: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": MULTIMODAL_RUNTIME_VERSION, "terminal": self.terminal.value,
            "normalization_terminal": self.normalization_terminal,
            "validation_issue_codes": list(self.validation_issue_codes),
            "compiler_status": self.compiler_status, "compiler_issue_codes": list(self.compiler_issue_codes),
            "solve_terminal": self.solve_terminal, "solve_diagnostic_codes": list(self.solve_diagnostic_codes),
            "authorized_ir_fingerprint": self.authorized_ir_fingerprint,
            "applied_law_ids": list(self.applied_law_ids), "equation_count": self.equation_count,
            "candidate_count": self.candidate_count, "rejected_candidate_count": self.rejected_candidate_count,
            "verification_checks": list(self.verification_checks), "verified_answer": self.verified_answer,
        }


def _text(value: object) -> str:
    return str(getattr(value, "value", value))


def _confirmed_figure_evidence_ids(revision: ModelingRevision) -> tuple[str, ...]:
    rejected=set(revision.rejected_evidence_ids); accepted=set(revision.accepted_evidence_ids)
    for observation in revision.envelope.figure_observations:
        evidence_id=observation.evidence_id
        if evidence_id is None or evidence_id in rejected: continue
        if observation.policy_eligibility.value == "automatic": accepted.add(evidence_id)
    return tuple(sorted(accepted))


def execute_multimodal_revision(revision: ModelingRevision) -> MultimodalRuntimeResult:
    if revision.reconciliation.status.value != "ready":
        return MultimodalRuntimeResult(MultimodalRuntimeTerminal.reconciliation_required)
    try:
        normalization=normalize_draft(
            revision.problem_text, revision.envelope.draft,
            approved_assumption_ids=revision.approved_assumption_ids,
            authorized_corrections=revision.authorization_map(),
            confirmed_figure_evidence_ids=_confirmed_figure_evidence_ids(revision),
        )
    except Exception:
        return MultimodalRuntimeResult(MultimodalRuntimeTerminal.failed)
    validation_codes=tuple(sorted({_text(issue.code) for issue in normalization.validation.issues}))
    if not normalization.accepted or normalization.ir is None:
        return MultimodalRuntimeResult(MultimodalRuntimeTerminal.validation_rejected,_text(normalization.terminal),validation_codes)
    try: authorization=authorize_validated_mechanics_ir(normalization.ir)
    except Exception:
        return MultimodalRuntimeResult(MultimodalRuntimeTerminal.authorization_failed,_text(normalization.terminal),validation_codes)
    try:
        compiled=MechanicsCompiler().compile(
            normalization.ir, validated_ir_authorization=authorization,
            approved_assumption_ids=revision.approved_assumption_ids,
            authorized_corrections=revision.authorization_map(),
        )
    except Exception:
        return MultimodalRuntimeResult(MultimodalRuntimeTerminal.failed,_text(normalization.terminal),validation_codes,authorized_ir_fingerprint=normalization.calculation_fingerprint)
    compiler_codes=tuple(sorted({_text(issue.code) for issue in compiled.issues})); graph=compiled.graph
    if not compiled.compilable or graph is None:
        return MultimodalRuntimeResult(MultimodalRuntimeTerminal.compiler_rejected,_text(normalization.terminal),validation_codes,_text(compiled.status),compiler_codes,authorized_ir_fingerprint=normalization.calculation_fingerprint)
    law_ids=tuple(sorted({item.law_id for item in graph.applications}))
    try: solved=solve_verified_equation_graph(graph)
    except Exception:
        return MultimodalRuntimeResult(MultimodalRuntimeTerminal.failed,_text(normalization.terminal),validation_codes,_text(compiled.status),compiler_codes,authorized_ir_fingerprint=normalization.calculation_fingerprint,applied_law_ids=law_ids,equation_count=len(graph.equations))
    diagnostic_codes=tuple(sorted({_text(item.code) for item in solved.diagnostics.entries}))
    common=dict(
        normalization_terminal=_text(normalization.terminal), validation_issue_codes=validation_codes,
        compiler_status=_text(compiled.status), compiler_issue_codes=compiler_codes,
        solve_terminal=_text(solved.terminal), solve_diagnostic_codes=diagnostic_codes,
        authorized_ir_fingerprint=normalization.calculation_fingerprint, applied_law_ids=law_ids,
        equation_count=len(graph.equations), candidate_count=len(solved.candidate_set.candidates),
        rejected_candidate_count=len(solved.rejections),
    )
    if solved.terminal is not MechanicsSolveTerminal.solved or len(solved.verified_candidates) != 1:
        return MultimodalRuntimeResult(terminal=MultimodalRuntimeTerminal.solve_rejected,**common)
    verified=solved.verified_candidates[0]
    checks=tuple({"kind":_text(item.kind),"status":_text(item.status)} for item in verified.outcome.checks)
    answer={"candidate_id":verified.candidate.candidate_id,"query_symbol_id":verified.query_symbol_id,"value_si":verified.query_value_si,"backend":_text(verified.candidate.backend),"approximate":verified.candidate.approximate}
    return MultimodalRuntimeResult(terminal=MultimodalRuntimeTerminal.solved,verification_checks=checks,verified_answer=answer,**common)


__all__=["MULTIMODAL_RUNTIME_VERSION","MultimodalRuntimeResult","MultimodalRuntimeTerminal","execute_multimodal_revision"]
