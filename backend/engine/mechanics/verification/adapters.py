"""Additive evidence projections for independently verified mechanics results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json

from engine.mechanics.compiler.contracts import EquationGraph
from engine.mechanics.solver.contracts import CandidateRejection, SIValue
from engine.mechanics.verification.contracts import (
    EVIDENCE_ADAPTER_VERSION,
    EvidenceAdapterV2,
    EvidenceOutput,
    EvidenceSubstitution,
    MechanicsSolveResult,
    MechanicsSolveTerminal,
    VerificationCheckStatus,
    render_canonical_si_unit,
)
from engine.models import (
    EquationEvidence,
    OutputEvidenceLink,
    SolverExplanationEvidence,
    SubstitutionEvidence,
    VerificationReport,
)
from engine.verification.types import (
    VerificationApplicability,
    VerificationCheck as LegacyVerificationCheck,
    VerificationStatus,
)


class LegacyProjectionStatus(str, Enum):
    projected = "projected"
    unsupported = "unsupported"


class LegacyProjectionLimitation(str, Enum):
    vector_output_not_representable = "vector_output_not_representable"


@dataclass(frozen=True)
class RejectedCandidateProjection:
    candidate_id: str
    generation_index: int
    root_index: int
    root_multiplicity: int
    rejections: tuple[CandidateRejection, ...]


@dataclass(frozen=True)
class LegacyEvidenceProjection:
    """Closed wrapper preserving fields absent from pre-Phase-56 targets."""

    status: LegacyProjectionStatus
    adapter: EvidenceAdapterV2
    selected_generation_index: int
    selected_root_index: int
    selected_root_multiplicity: int
    rejected_candidates: tuple[RejectedCandidateProjection, ...]
    verification_checks: tuple[LegacyVerificationCheck, ...] = ()
    verification_report: VerificationReport | None = None
    equations: tuple[EquationEvidence, ...] = ()
    substitutions: tuple[SubstitutionEvidence, ...] = ()
    outputs: tuple[OutputEvidenceLink, ...] = ()
    explanation_evidence: SolverExplanationEvidence | None = None
    limitation: LegacyProjectionLimitation | None = None

    def __post_init__(self) -> None:
        if self.status is LegacyProjectionStatus.projected:
            if (
                self.limitation is not None
                or self.verification_report is None
                or self.explanation_evidence is None
                or not self.verification_checks
                or not self.equations
                or not self.substitutions
                or len(self.outputs) != 1
            ):
                raise ValueError("projected legacy evidence must be complete")
        elif (
            self.limitation is None
            or self.verification_checks
            or self.verification_report is not None
            or self.equations
            or self.substitutions
            or self.outputs
            or self.explanation_evidence is not None
        ):
            raise ValueError("unsupported legacy evidence must return no partial projection")


def _selected(result: MechanicsSolveResult):
    if (
        result.terminal is not MechanicsSolveTerminal.solved
        or result.selected_candidate_id is None
    ):
        raise ValueError("evidence requires one independently verified solved result")
    selected = tuple(
        item
        for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    if len(selected) != 1:
        raise ValueError("solved result must contain its one selected verified candidate")
    return selected[0]


def _source_union(
    result: MechanicsSolveResult,
    equation_ids: tuple[str, ...],
    checks: tuple[object, ...],
) -> tuple[str, ...]:
    graph = result.plan.graph
    equation_by_id = {item.equation_id: item for item in graph.equations}
    constraint_by_id = {item.constraint_id: item for item in graph.constraints}
    constraints = {
        identifier
        for check in checks
        for identifier in check.constraint_ids
    }
    constraints.update(
        identifier
        for equation_id in equation_ids
        for identifier in equation_by_id[equation_id].constraint_ids
    )
    sources = {
        identifier
        for check in checks
        for identifier in check.source_evidence_ids
    }
    sources.update(
        identifier
        for equation_id in equation_ids
        for identifier in equation_by_id[equation_id].source_evidence_ids
    )
    sources.update(
        identifier
        for constraint_id in constraints
        for identifier in constraint_by_id[constraint_id].source_evidence_ids
    )
    sources.update(
        identifier
        for condition in graph.initial_conditions
        if condition.condition_id in result.plan.initial_condition_ids
        for identifier in condition.source_evidence_ids
    )
    sources.update(
        identifier
        for application in graph.applications
        if set(application.equation_ids) & set(equation_ids)
        for identifier in application.source_evidence_ids
    )
    return tuple(sorted(sources))


def build_evidence_adapter(result: MechanicsSolveResult) -> EvidenceAdapterV2:
    """Bind the concrete solved candidate and its exact passing evidence."""

    verified = _selected(result)
    candidate = verified.candidate
    checks = verified.outcome.checks
    equation_ids = tuple(sorted({
        *candidate.equation_ids,
        *(
            identifier
            for check in checks
            for identifier in check.equation_ids
        ),
    }))
    query_nodes = tuple(
        item
        for item in result.plan.graph.symbols
        if item.symbol.symbol_id == result.plan.query_symbol_id
    )
    if len(query_nodes) != 1:
        raise ValueError("evidence query must resolve exactly once")
    return EvidenceAdapterV2(
        adapter_version=EVIDENCE_ADAPTER_VERSION,
        result=result,
        candidate_id=candidate.candidate_id,
        query_id=result.plan.query_id,
        equation_ids=equation_ids,
        source_evidence_ids=_source_union(result, equation_ids, checks),
        substitutions=tuple(
            EvidenceSubstitution(symbol_id=item.symbol_id, value_si=item.value_si)
            for item in candidate.values
        ),
        output=EvidenceOutput(
            query_symbol_id=result.plan.query_symbol_id,
            value_si=verified.query_value_si,
            si_unit=render_canonical_si_unit(query_nodes[0].symbol.dimension),
        ),
        checks=checks,
    )


def _legacy_status(status: VerificationCheckStatus) -> VerificationStatus:
    if status is VerificationCheckStatus.passed:
        return VerificationStatus.PASSED
    if status is VerificationCheckStatus.failed:
        return VerificationStatus.FAILED
    return VerificationStatus.INCONCLUSIVE


def to_legacy_verification_checks(
    result: MechanicsSolveResult,
) -> tuple[LegacyVerificationCheck, ...]:
    """Project all outcomes with selected/rejected state kept as typed metadata."""

    _selected(result)
    candidate_by_id = {
        item.candidate_id: item
        for item in result.candidate_set.candidates
    }
    projected: list[LegacyVerificationCheck] = []
    for outcome in result.verification_outcomes:
        candidate = candidate_by_id[outcome.candidate_id]
        rejection_by_check = {
            item.check_id: item
            for item in outcome.rejections
        }
        for check in outcome.checks:
            rejection = rejection_by_check.get(check.check_id)
            projected.append(LegacyVerificationCheck(
                check_id=f"{candidate.candidate_id}:{check.check_id}",
                category=check.kind.value,
                status=_legacy_status(check.status),
                applicability=VerificationApplicability.APPLICABLE,
                observed=check.measured_error,
                expected=check.tolerance,
                absolute_error=check.measured_error,
                tolerance=check.tolerance,
                evidence=check.source_evidence_ids,
                source_equation_ids=check.equation_ids,
                metadata={
                    "mechanics_check_id": check.check_id,
                    "graph_fingerprint": result.plan.graph_fingerprint,
                    "plan_fingerprint": result.plan.plan_fingerprint,
                    "candidate_id": candidate.candidate_id,
                    "selected": candidate.candidate_id == result.selected_candidate_id,
                    "passed": outcome.passed,
                    "generation_index": candidate.generation_index,
                    "root_index": candidate.root_index,
                    "root_multiplicity": candidate.root_multiplicity,
                    "backend": candidate.backend.value,
                    "approximate": candidate.approximate,
                    "constraint_ids": check.constraint_ids,
                    "event_ids": check.event_ids,
                    "symbol_ids": check.symbol_ids,
                    "initial_condition_ids": check.initial_condition_ids,
                    "source_evidence_ids": check.source_evidence_ids,
                    "rejection_reason": rejection.reason.value if rejection else None,
                },
            ))
    return tuple(projected)


def build_legacy_verification_report(
    adapter: EvidenceAdapterV2,
    checks: tuple[LegacyVerificationCheck, ...] | None = None,
) -> VerificationReport:
    """Build the additive legacy report without text-based answer authority."""

    canonical = to_legacy_verification_checks(adapter.result)
    if checks is not None and checks != canonical:
        raise ValueError("legacy verification checks must exactly match the solved result")
    selected_checks = tuple(
        item
        for item in canonical
        if item.metadata.get("selected") is True
    )
    if not selected_checks:
        raise ValueError("legacy verification report requires selected candidate checks")
    return VerificationReport(
        passed=all(item.passed for item in selected_checks),
        dimension_summary=adapter.output.si_unit,
        checks=[],
        warnings=[],
        errors=[],
        structured_checks=[item.to_dict() for item in canonical],
        policy_version=adapter.result.verification_outcomes[0].policy_version,
    )


def _canonical_ast_text(expression: object) -> str:
    return json.dumps(
        expression.model_dump(mode="json", warnings="none"),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_value_text(symbol_id: str, value: SIValue) -> str:
    return json.dumps(
        {"symbol_id": symbol_id, "value_si": value},
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _equation_source_ids(graph: EquationGraph, equation_id: str) -> tuple[str, ...]:
    """Return only source provenance explicitly attached to one equation."""

    equation_by_id = {item.equation_id: item for item in graph.equations}
    constraint_by_id = {item.constraint_id: item for item in graph.constraints}
    equation = equation_by_id[equation_id]
    applications = tuple(
        item
        for item in graph.applications
        if equation_id in item.equation_ids
    )
    constraint_ids = {
        *equation.constraint_ids,
        *(
            item.constraint_id
            for item in graph.constraints
            if item.equation_id == equation_id
        ),
    }
    for application in applications:
        for constraint_id in application.constraint_ids:
            constraint = constraint_by_id[constraint_id]
            if constraint.equation_id == equation_id or application.equation_ids == (equation_id,):
                constraint_ids.add(constraint_id)
    return tuple(sorted({
        *equation.source_evidence_ids,
        *(
            source_id
            for application in applications
            for source_id in application.source_evidence_ids
        ),
        *(
            source_id
            for constraint_id in constraint_ids
            for source_id in constraint_by_id[constraint_id].source_evidence_ids
        ),
    }))


def _legacy_evidence_parts(
    adapter: EvidenceAdapterV2,
) -> tuple[
    tuple[EquationEvidence, ...],
    tuple[SubstitutionEvidence, ...],
    tuple[OutputEvidenceLink, ...],
    SolverExplanationEvidence,
]:
    result = adapter.result
    verified = adapter.verified_candidate
    candidate = verified.candidate
    if not isinstance(adapter.output.value_si, float):
        raise ValueError(LegacyProjectionLimitation.vector_output_not_representable.value)
    graph = result.plan.graph
    equation_by_id = {item.equation_id: item for item in graph.equations}
    sources_by_equation = {
        identifier: _equation_source_ids(graph, identifier)
        for identifier in adapter.equation_ids
    }
    output_id = f"mechanics_output_{candidate.candidate_id}_{result.plan.query_symbol_id}"
    equations = tuple(
        EquationEvidence(
            equation_id=identifier,
            expression=_canonical_ast_text(equation_by_id[identifier].expression),
            source="mechanics_equation_graph",
            provenance=f"equation_graph:{result.plan.graph_fingerprint}",
            fact_ids=sources_by_equation[identifier],
            input_output_ids=(),
            output_ids=(output_id,),
        )
        for identifier in adapter.equation_ids
    )
    substitutions = tuple(
        SubstitutionEvidence(
            substitution_id=(
                f"substitution_{candidate.candidate_id}_{equation_id}_{item.symbol_id}"
            ),
            equation_id=equation_id,
            expression=_canonical_value_text(item.symbol_id, item.value_si),
            output_id=output_id,
            fact_ids=sources_by_equation[equation_id],
            input_output_ids=(),
            source="mechanics_verified_candidate",
        )
        for equation_id in adapter.equation_ids
        for item in adapter.substitutions
    )
    output = OutputEvidenceLink(
        output_id=output_id,
        output_key=result.plan.query_id,
        candidate_id=candidate.candidate_id,
        numeric=adapter.output.value_si,
        unit=adapter.output.si_unit,
        symbol=result.plan.query_symbol_id,
        role="primary",
        response_index=0,
        equation_ids=adapter.equation_ids,
        substitution_ids=tuple(item.substitution_id for item in substitutions),
        candidate_key=result.plan.query_symbol_id,
        candidate_numeric=adapter.output.value_si,
        delivery_candidate_id=candidate.candidate_id,
        delivery_candidate_key=result.plan.query_symbol_id,
        delivery_transform="identity",
    )
    outputs = (output,)
    explanation = SolverExplanationEvidence(
        equations=equations,
        substitutions=substitutions,
        outputs=outputs,
    )
    return equations, substitutions, outputs, explanation


def build_solver_explanation_evidence(
    adapter: EvidenceAdapterV2,
) -> SolverExplanationEvidence:
    """Project one scalar solved adapter to the existing explanation contract."""

    return _legacy_evidence_parts(adapter)[3]


def _rejected_candidates(result: MechanicsSolveResult) -> tuple[RejectedCandidateProjection, ...]:
    outcome_by_id = {
        item.candidate_id: item
        for item in result.verification_outcomes
    }
    return tuple(
        RejectedCandidateProjection(
            candidate_id=candidate.candidate_id,
            generation_index=candidate.generation_index,
            root_index=candidate.root_index,
            root_multiplicity=candidate.root_multiplicity,
            rejections=outcome_by_id[candidate.candidate_id].rejections,
        )
        for candidate in result.candidate_set.candidates
        if candidate.candidate_id != result.selected_candidate_id
    )


def build_legacy_evidence_projection(
    result: MechanicsSolveResult,
) -> LegacyEvidenceProjection:
    """Return either a complete scalar projection or an explicit closed limit."""

    adapter = build_evidence_adapter(result)
    selected = adapter.verified_candidate.candidate
    rejected = _rejected_candidates(result)
    if not isinstance(adapter.output.value_si, float):
        return LegacyEvidenceProjection(
            status=LegacyProjectionStatus.unsupported,
            adapter=adapter,
            selected_generation_index=selected.generation_index,
            selected_root_index=selected.root_index,
            selected_root_multiplicity=selected.root_multiplicity,
            rejected_candidates=rejected,
            limitation=LegacyProjectionLimitation.vector_output_not_representable,
        )
    checks = to_legacy_verification_checks(result)
    report = build_legacy_verification_report(adapter, checks)
    equations, substitutions, outputs, explanation = _legacy_evidence_parts(adapter)
    return LegacyEvidenceProjection(
        status=LegacyProjectionStatus.projected,
        adapter=adapter,
        selected_generation_index=selected.generation_index,
        selected_root_index=selected.root_index,
        selected_root_multiplicity=selected.root_multiplicity,
        rejected_candidates=rejected,
        verification_checks=checks,
        verification_report=report,
        equations=equations,
        substitutions=substitutions,
        outputs=outputs,
        explanation_evidence=explanation,
    )


adapt_solver_explanation_evidence = build_solver_explanation_evidence


__all__ = [
    "LegacyEvidenceProjection",
    "LegacyProjectionLimitation",
    "LegacyProjectionStatus",
    "RejectedCandidateProjection",
    "adapt_solver_explanation_evidence",
    "build_evidence_adapter",
    "build_legacy_evidence_projection",
    "build_legacy_verification_report",
    "build_solver_explanation_evidence",
    "to_legacy_verification_checks",
]
