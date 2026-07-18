from __future__ import annotations

from dataclasses import dataclass

from engine.textbook_parser.assumption_policy import AssumptionDisposition, AssumptionEvaluation
from engine.textbook_parser.capabilities import CapabilityCheck
from engine.textbook_parser.contracts import InterpretationCandidate, TextbookProblemParseV1
from engine.textbook_parser.errors import Severity, ValidationIssue
from engine.textbook_parser.errors import ErrorCode


DECISION_POLICY_VERSION = "textbook-decision-v1"
TIE_MARGIN = 0.08


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    total: float
    factors: dict[str, float]
    veto_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "total": self.total,
            "factors": dict(self.factors),
            "veto_codes": list(self.veto_codes),
            "policy_version": DECISION_POLICY_VERSION,
        }


def score_candidate(
    parse: TextbookProblemParseV1,
    candidate: InterpretationCandidate,
    *,
    issues: tuple[ValidationIssue, ...],
    assumptions: tuple[AssumptionEvaluation, ...],
    capability: CapabilityCheck,
    rule_agreement: bool | None = None,
) -> CandidateScore:
    candidate_ids = set(candidate.fact_ids) | set(candidate.query_ids) | set(candidate.assumption_ids)
    global_safety_codes = {
        ErrorCode.answer_authority_field,
        ErrorCode.evidence_quote_missing,
        ErrorCode.evidence_occurrence_missing,
        ErrorCode.invented_explicit_number,
        ErrorCode.raw_value_mismatch,
        ErrorCode.raw_unit_mismatch,
        ErrorCode.contradictory_fact,
    }
    veto = sorted(
        {
            issue.code.value
            for issue in issues
            if issue.severity in {Severity.error, Severity.critical}
            and (
                issue.code in global_safety_codes
                or issue.referenced_id is None
                or issue.referenced_id in candidate_ids
                or issue.referenced_id == candidate.candidate_id
            )
        }
    )
    assumption_by_id = {item.assumption_id: item for item in assumptions}
    candidate_assumptions = [assumption_by_id[item] for item in candidate.assumption_ids]
    assumption_safety = (
        sum(
            1.0
            if item.disposition in {
                AssumptionDisposition.accepted_default,
                AssumptionDisposition.accepted_visible,
            }
            else 0.0
            for item in candidate_assumptions
        )
        / len(candidate_assumptions)
        if candidate_assumptions
        else 1.0
    )
    evidence_coverage = 1.0 if candidate.fact_ids else 0.0
    binding_completeness = 1.0
    query_match = 1.0 if candidate.query_ids else 0.0
    capability_completeness = 1.0 if capability.supported else 0.0
    rule_score = 0.5 if rule_agreement is None else (1.0 if rule_agreement else 0.0)
    factors = {
        "evidence": 0.25 * evidence_coverage,
        "binding": 0.20 * binding_completeness,
        "query": 0.20 * query_match,
        "assumption": 0.10 * assumption_safety,
        "capability": 0.20 * capability_completeness,
        "rule_agreement": 0.05 * rule_score,
    }
    total = 0.0 if veto else round(sum(factors.values()), 6)
    return CandidateScore(candidate.candidate_id, total, factors, tuple(veto))


__all__ = ["CandidateScore", "DECISION_POLICY_VERSION", "TIE_MARGIN", "score_candidate"]
