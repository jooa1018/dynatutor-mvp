from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from engine.textbook_parser.assumption_policy import (
    AssumptionDisposition,
    AssumptionEvaluation,
    evaluate_assumptions,
)
from engine.textbook_parser.capabilities import CapabilityCheck, check_capability
from engine.textbook_parser.confidence import CandidateScore, TIE_MARGIN, score_candidate
from engine.textbook_parser.contracts import (
    FigureDependencyLevel,
    ParseStatus,
    TextbookProblemParseV1,
)
from engine.textbook_parser.evidence_alignment import EvidenceValidation, validate_evidence
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.validators.semantic import validate_semantics


VALIDATOR_POLICY_VERSION = "textbook-validator-v1"


class ParseDecisionStatus(str, Enum):
    accepted = "accepted"
    accepted_with_visible_assumptions = "accepted_with_visible_assumptions"
    needs_confirmation = "needs_confirmation"
    needs_figure = "needs_figure"
    insufficient_information = "insufficient_information"
    solver_gap = "solver_gap"
    parser_unavailable = "parser_unavailable"
    parser_error = "parser_error"


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
    capability: CapabilityCheck
    score: CandidateScore

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "capability": self.capability.to_dict(),
            "score": self.score.to_dict(),
        }


@dataclass(frozen=True)
class ValidatedParse:
    parse: TextbookProblemParseV1
    status: ParseDecisionStatus
    selected_candidate_id: str | None
    evidence: EvidenceValidation
    assumptions: tuple[AssumptionEvaluation, ...]
    candidates: tuple[CandidateEvaluation, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def accepted(self) -> bool:
        return self.status in {
            ParseDecisionStatus.accepted,
            ParseDecisionStatus.accepted_with_visible_assumptions,
        }

    @property
    def selected_candidate(self):
        if self.selected_candidate_id is None:
            return None
        return next(
            item
            for item in self.parse.interpretation_candidates
            if item.candidate_id == self.selected_candidate_id
        )

    def to_summary(self) -> dict[str, object]:
        accepted_ids = {
            item.assumption_id
            for item in self.assumptions
            if item.disposition in {
                AssumptionDisposition.accepted_default,
                AssumptionDisposition.accepted_visible,
            }
        }
        return {
            "status": self.status.value,
            "selected_candidate_id": self.selected_candidate_id,
            "validator_policy_version": VALIDATOR_POLICY_VERSION,
            "accepted_assumption_ids": sorted(accepted_ids),
            "assumption_evaluations": [item.to_dict() for item in self.assumptions],
            "candidate_evaluations": [item.to_dict() for item in self.candidates],
            "issues": [item.to_dict() for item in self.issues],
        }


def _candidate_related_issues(
    issues: tuple[ValidationIssue, ...], candidate_ids: set[str]
) -> tuple[ValidationIssue, ...]:
    global_safety_codes = {
        ErrorCode.answer_authority_field,
        ErrorCode.evidence_quote_missing,
        ErrorCode.evidence_occurrence_missing,
        ErrorCode.invented_explicit_number,
        ErrorCode.raw_value_mismatch,
        ErrorCode.raw_unit_mismatch,
        ErrorCode.contradictory_fact,
    }
    return tuple(
        issue
        for issue in issues
        if issue.code in global_safety_codes
        or issue.referenced_id is None
        or issue.referenced_id in candidate_ids
    )


def validate_parse(problem_text: str, parse: TextbookProblemParseV1) -> ValidatedParse:
    evidence = validate_evidence(problem_text, parse)
    assumptions = evaluate_assumptions(problem_text, parse)
    issues: list[ValidationIssue] = list(evidence.issues)
    issues.extend(validate_semantics(parse))

    evaluations: list[CandidateEvaluation] = []
    for candidate in parse.interpretation_candidates:
        capability = check_capability(parse, candidate, assumptions)
        issues.extend(capability.issues)
        related_ids = (
            set(candidate.fact_ids)
            | set(candidate.query_ids)
            | set(candidate.assumption_ids)
            | {candidate.candidate_id}
        )
        score = score_candidate(
            parse,
            candidate,
            issues=_candidate_related_issues(tuple(issues), related_ids),
            assumptions=assumptions,
            capability=capability,
        )
        evaluations.append(CandidateEvaluation(candidate.candidate_id, capability, score))

    if parse.figure_dependency.level == FigureDependencyLevel.required:
        status = ParseDecisionStatus.needs_figure
        selected = None
    elif parse.parse_status == ParseStatus.insufficient_information:
        status = ParseDecisionStatus.insufficient_information
        selected = None
    elif not evaluations:
        status = (
            ParseDecisionStatus.solver_gap
            if parse.parse_status == ParseStatus.unsupported or parse.unsupported_features
            else ParseDecisionStatus.needs_confirmation
        )
        selected = None
    else:
        ranked = sorted(evaluations, key=lambda item: (-item.score.total, item.candidate_id))
        best = ranked[0]
        selected = best.candidate_id
        if best.score.veto_codes:
            status = ParseDecisionStatus.needs_confirmation
            selected = None
        elif not best.capability.supported or not best.capability.textbook_parser_safe:
            status = ParseDecisionStatus.solver_gap
            selected = None
        elif len(ranked) > 1 and ranked[1].score.total >= best.score.total - TIE_MARGIN:
            issues.append(
                ValidationIssue(
                    ErrorCode.candidate_tie,
                    Severity.error,
                    "multiple validated interpretations remain within the deterministic tie margin",
                    path="interpretation_candidates",
                    metadata={
                        "candidate_ids": [best.candidate_id, ranked[1].candidate_id],
                        "tie_margin": TIE_MARGIN,
                    },
                )
            )
            status = ParseDecisionStatus.needs_confirmation
            selected = None
        else:
            by_id = {item.assumption_id: item for item in assumptions}
            candidate = next(
                item for item in parse.interpretation_candidates if item.candidate_id == selected
            )
            candidate_assumptions = [by_id[item] for item in candidate.assumption_ids]
            if any(
                item.disposition
                in {AssumptionDisposition.needs_confirmation, AssumptionDisposition.rejected}
                for item in candidate_assumptions
            ):
                status = ParseDecisionStatus.needs_confirmation
                selected = None
            elif parse.ambiguities or parse.parse_status == ParseStatus.ambiguous:
                status = ParseDecisionStatus.needs_confirmation
                selected = None
            elif any(
                item.disposition == AssumptionDisposition.accepted_visible
                for item in candidate_assumptions
            ):
                status = ParseDecisionStatus.accepted_with_visible_assumptions
            else:
                status = ParseDecisionStatus.accepted

    return ValidatedParse(
        parse=parse,
        status=status,
        selected_candidate_id=selected,
        evidence=evidence,
        assumptions=assumptions,
        candidates=tuple(evaluations),
        issues=tuple(issues),
    )


__all__ = [
    "VALIDATOR_POLICY_VERSION",
    "CandidateEvaluation",
    "ParseDecisionStatus",
    "ValidatedParse",
    "validate_parse",
]
