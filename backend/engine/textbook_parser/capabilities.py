from __future__ import annotations

from dataclasses import dataclass

from engine.capabilities.loader import CapabilityMatrix, load_capability_matrix
from engine.textbook_parser.assumption_policy import AssumptionDisposition, AssumptionEvaluation
from engine.textbook_parser.bindings import BindingReport, evaluate_candidate_bindings
from engine.textbook_parser.contracts import InterpretationCandidate, TextbookProblemParseV1
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue


CAPABILITY_POLICY_VERSION = "textbook-capability-v3"


@dataclass(frozen=True)
class CapabilityCheck:
    candidate_id: str
    solver_id: str | None
    supported: bool
    textbook_parser_safe: bool
    supplied_symbols: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    binding: BindingReport
    issues: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "solver_id": self.solver_id,
            "supported": self.supported,
            "textbook_parser_safe": self.textbook_parser_safe,
            "supplied_symbols": list(self.supplied_symbols),
            "missing_inputs": list(self.missing_inputs),
            "binding": self.binding.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _accepted_assumption_symbols(
    parse: TextbookProblemParseV1,
    evaluations: tuple[AssumptionEvaluation, ...],
    candidate: InterpretationCandidate,
) -> tuple[set[str], tuple[ValidationIssue, ...]]:
    out: set[str] = set()
    issues: list[ValidationIssue] = []
    proposal_by_id = {
        item.assumption_id: item for item in parse.assumption_proposals
    }
    query_subjects = {
        item.subject_id for item in parse.queries if item.query_id in candidate.query_ids
    }
    for evaluation in evaluations:
        if (
            evaluation.assumption_id in set(candidate.assumption_ids)
            and evaluation.disposition
            in {
                AssumptionDisposition.accepted_default,
                AssumptionDisposition.accepted_visible,
            }
            and evaluation.resolved_symbol is not None
        ):
            proposal = proposal_by_id[evaluation.assumption_id]
            if (
                candidate.system_type == "constant_acceleration_1d"
                and proposal.subject_id not in query_subjects
            ):
                issues.append(
                    ValidationIssue(
                        ErrorCode.candidate_binding_mismatch,
                        Severity.error,
                        "candidate assumption subject does not match the solver query subject",
                        path=f"interpretation_candidates.{candidate.candidate_id}.assumption_ids",
                        referenced_id=evaluation.assumption_id,
                    )
                )
                continue
            out.add(evaluation.resolved_symbol)
    return out, tuple(issues)


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
    binding = evaluate_candidate_bindings(parse, candidate)
    issues.extend(binding.issues)
    symbols = {item.symbol for item in binding.bindings}
    assumption_symbols, assumption_binding_issues = _accepted_assumption_symbols(
        parse, evaluations, candidate
    )
    symbols |= assumption_symbols
    issues.extend(assumption_binding_issues)
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
            binding,
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
        binding,
        tuple(issues),
    )


__all__ = ["CAPABILITY_POLICY_VERSION", "CapabilityCheck", "check_capability"]
