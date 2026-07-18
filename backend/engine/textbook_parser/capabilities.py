from __future__ import annotations

from dataclasses import dataclass

from engine.capabilities.loader import CapabilityMatrix, load_capability_matrix
from engine.textbook_parser.assumption_policy import AssumptionDisposition, AssumptionEvaluation
from engine.textbook_parser.contracts import InterpretationCandidate, TextbookProblemParseV1
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.ontology import canonical_symbol


CAPABILITY_POLICY_VERSION = "textbook-capability-v1"


@dataclass(frozen=True)
class CapabilityCheck:
    candidate_id: str
    solver_id: str | None
    supported: bool
    textbook_parser_safe: bool
    supplied_symbols: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "solver_id": self.solver_id,
            "supported": self.supported,
            "textbook_parser_safe": self.textbook_parser_safe,
            "supplied_symbols": list(self.supplied_symbols),
            "missing_inputs": list(self.missing_inputs),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _accepted_assumption_symbols(
    parse: TextbookProblemParseV1,
    evaluations: tuple[AssumptionEvaluation, ...],
    candidate_assumption_ids: set[str],
) -> set[str]:
    accepted = {
        item.assumption_id
        for item in evaluations
        if item.assumption_id in candidate_assumption_ids
        and item.disposition in {
            AssumptionDisposition.accepted_default,
            AssumptionDisposition.accepted_visible,
        }
    }
    out: set[str] = set()
    for proposal in parse.assumption_proposals:
        if proposal.assumption_id in accepted:
            symbol = canonical_symbol(proposal.proposed_semantic_key)
            if symbol:
                out.add(symbol)
    return out


def check_capability(
    parse: TextbookProblemParseV1,
    candidate: InterpretationCandidate,
    evaluations: tuple[AssumptionEvaluation, ...],
    *,
    matrix: CapabilityMatrix | None = None,
) -> CapabilityCheck:
    matrix = matrix or load_capability_matrix()
    entry = matrix.for_problem(candidate.system_type, candidate.subtype)
    issues: list[ValidationIssue] = []
    symbols = {
        symbol
        for fact in parse.explicit_facts
        if fact.fact_id in candidate.fact_ids
        if (symbol := canonical_symbol(fact.semantic_key)) is not None
    }
    symbols |= _accepted_assumption_symbols(
        parse, evaluations, set(candidate.assumption_ids)
    )
    if entry is None:
        issues.append(
            ValidationIssue(
                ErrorCode.capability_missing,
                Severity.error,
                "no deterministic solver capability matches the interpretation",
                path=f"interpretation_candidates.{candidate.candidate_id}",
                referenced_id=candidate.candidate_id,
            )
        )
        return CapabilityCheck(
            candidate.candidate_id,
            None,
            False,
            False,
            tuple(sorted(symbols)),
            (),
            tuple(issues),
        )

    requirements = entry.get("required_inputs") or {}
    missing: list[str] = []
    for symbol in requirements.get("all_of") or []:
        if symbol not in symbols:
            missing.append(symbol)
    any_of = list(requirements.get("any_of") or [])
    if any_of and not (set(any_of) & symbols):
        missing.append("one_of:" + "|".join(any_of))
    for rule in requirements.get("conditional") or []:
        conditional_symbols = list(rule.get("symbols") or [])
        minimum = int(rule.get("minimum_present") or 0)
        if len(set(conditional_symbols) & symbols) < minimum:
            missing.append(f"{minimum}_of:" + "|".join(conditional_symbols))

    queries = [query for query in parse.queries if query.query_id in candidate.query_ids]
    allowed_outputs = set(entry.get("requested_outputs") or [])
    unsupported_outputs = sorted(
        {query.output_key.value for query in queries} - allowed_outputs
    )
    if unsupported_outputs:
        issues.append(
            ValidationIssue(
                ErrorCode.unsupported_query,
                Severity.error,
                "interpretation query is not supported by the deterministic solver",
                path=f"interpretation_candidates.{candidate.candidate_id}.query_ids",
                referenced_id=candidate.candidate_id,
                metadata={"unsupported_outputs": unsupported_outputs},
            )
        )
    if missing:
        issues.append(
            ValidationIssue(
                ErrorCode.capability_missing,
                Severity.error,
                "deterministic solver inputs are incomplete",
                path=f"interpretation_candidates.{candidate.candidate_id}.fact_ids",
                referenced_id=candidate.candidate_id,
                metadata={"missing_inputs": missing},
            )
        )
    safe = bool(entry.get("textbook_parser_safe", False))
    if not safe:
        issues.append(
            ValidationIssue(
                ErrorCode.solver_not_textbook_safe,
                Severity.warning,
                "solver family has not passed the typed-canonical raw-text invariance gate",
                path=f"interpretation_candidates.{candidate.candidate_id}",
                referenced_id=candidate.candidate_id,
            )
        )
    return CapabilityCheck(
        candidate.candidate_id,
        str(entry.get("analytic_solver")),
        not missing and not unsupported_outputs,
        safe,
        tuple(sorted(symbols)),
        tuple(missing),
        tuple(issues),
    )


__all__ = ["CAPABILITY_POLICY_VERSION", "CapabilityCheck", "check_capability"]
