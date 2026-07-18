from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import json
import os
import sys

from engine.textbook_parser.benchmark import (
    BenchmarkManifest,
    GoldLabels,
    Prediction,
    SemanticGraph,
    evaluate_predictions,
    harness_integrity_report,
    semantic_graph_from_labels,
    semantic_graph_from_parse,
    semantic_signature_diff,
)
from engine.textbook_parser.canonical_projection import project_canonical
from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.orchestrator import ParseOutcome, parse_textbook_problem
from engine.textbook_parser.seed_corpus import repository_safe_seed_manifest


CASE_LIMIT = 20
COST_LIMIT_USD = 0.25


class _DisabledCache:
    def get(self, _key):
        return None

    def put(self, _key, _entry):
        return None


def _stratified_cases(cases):
    groups = defaultdict(list)
    for case in cases:
        groups[case.category].append(case)
    selected = []
    for category in sorted(groups):
        selected.append(groups[category].pop(0))
    while len(selected) < CASE_LIMIT:
        progressed = False
        for category in sorted(groups):
            if groups[category] and len(selected) < CASE_LIMIT:
                selected.append(groups[category].pop(0))
                progressed = True
        if not progressed:
            break
    return selected[:CASE_LIMIT]


def _empty_labels(outcome: ParseOutcome) -> GoldLabels:
    return GoldLabels(
        entities=[],
        segments=[],
        events=[],
        explicit_facts=[],
        fact_entity_binding={},
        fact_segment_binding={},
        relations=[],
        queries=[],
        assumptions=[],
        required_clarification=outcome.status.value
        in {"needs_confirmation", "insufficient_information", "needs_figure"},
        figure_dependency="unknown",
        expected_system_type=None,
        expected_solver=None,
        supported_status=outcome.status.value,
        expected_end_to_end_answer=None,
        expected_terminal_status=outcome.status.value,
        semantic_graph=SemanticGraph(),
    )


def _prediction(case, outcome: ParseOutcome) -> Prediction:
    if outcome.validated is None:
        return Prediction(
            case_id=case.case_id,
            labels=_empty_labels(outcome),
            confident_solve=False,
        )
    validated = outcome.validated
    parse = validated.parse
    selected = next(
        (
            item
            for item in validated.candidates
            if item.candidate_id == validated.selected_candidate_id
        ),
        validated.candidates[0] if validated.candidates else None,
    )
    candidate = validated.selected_candidate or (
        parse.interpretation_candidates[0]
        if parse.interpretation_candidates
        else None
    )
    answer = None
    terminal = None if validated.accepted else validated.status.value
    confident = validated.accepted
    solver_id = selected.capability.solver_id if selected is not None else None
    if validated.accepted:
        from engine.solvers.registry import SolverRegistry

        canonical = project_canonical(case.problem_text, validated)
        registry = SolverRegistry()
        decision = registry.route(canonical)
        solver = registry.select(canonical, decision=decision)
        solver_id = decision.selected_solver_id
        result = solver.solve(canonical) if solver is not None else None
        if result is not None and result.ok and result.answer is not None:
            answer = {
                "numeric": round(float(result.answer.numeric), 6),
                "unit": result.answer.unit.replace("²", "^2").replace("³", "^3"),
            }
        else:
            confident = False
            terminal = "solver_error"
    labels = GoldLabels(
        entities=[item.entity_id for item in parse.entities],
        segments=[
            f"{item.segment_id}:{item.relevance.value}"
            for item in parse.motion_segments
        ],
        events=[item.kind.value for item in parse.events],
        explicit_facts=[
            f"{item.semantic_key.value}:{item.raw_value}:{item.raw_unit}"
            for item in parse.explicit_facts
        ],
        fact_entity_binding={
            item.fact_id: item.subject_id for item in parse.explicit_facts
        },
        fact_segment_binding={
            item.fact_id: item.segment_id for item in parse.explicit_facts
        },
        relations=[
            f"{item.kind.value}:" + ":".join(item.entity_ids)
            for item in parse.relations
        ],
        queries=[
            f"{item.output_key.value}:{item.subject_id}:{item.segment_id}"
            for item in parse.queries
        ],
        assumptions=[item.kind.value for item in parse.assumption_proposals],
        required_clarification=validated.status.value
        in {"needs_confirmation", "insufficient_information", "needs_figure"},
        figure_dependency=parse.figure_dependency.level.value,
        expected_system_type=(
            candidate.system_type.value if candidate is not None else None
        ),
        expected_solver=solver_id,
        supported_status=(
            "supported" if validated.accepted else validated.status.value
        ),
        expected_end_to_end_answer=answer,
        expected_terminal_status=terminal,
        semantic_graph=semantic_graph_from_parse(parse),
    )
    authority_violation = any(
        issue.code.value == "answer_authority_field"
        for issue in validated.issues
    )
    invented_explicit_fact = any(
        issue.code.value == "invented_explicit_number"
        for issue in validated.issues
    )
    return Prediction(
        case_id=case.case_id,
        labels=labels,
        confident_solve=confident,
        invented_explicit_fact=invented_explicit_fact,
        answer_authority_violation=authority_violation,
        unsafe_patch_bypass=False,
    )


def _case_summary(case, outcome: ParseOutcome, prediction: Prediction) -> dict[str, object]:
    context = outcome.diagnostic_context()
    actual_graph = semantic_graph_from_labels(prediction.labels)
    return {
        "case_id": case.case_id,
        "terminal_status": outcome.status.value,
        "failure_code": outcome.failure_code,
        "request_attempt_count": outcome.request_attempt_count,
        "retry_count": outcome.retry_count,
        **context,
        "repair_error_codes": list(outcome.repair_error_codes),
        "attempt_diagnostics": [
            item.to_dict() for item in outcome.attempt_diagnostics
        ],
        "parser_latency_ms": outcome.parser_latency_ms,
        "validation_latency_ms": outcome.validation_latency_ms,
        "expected_actual_semantic_signature_diff": semantic_signature_diff(
            semantic_graph_from_labels(case.gold), actual_graph
        ),
        "tokens": {
            "input": outcome.usage.input_tokens,
            "cached_input": outcome.usage.cached_input_tokens,
            "output": outcome.usage.output_tokens,
            "reasoning": outcome.usage.reasoning_tokens,
        },
        "measured_cost_usd": outcome.usage.estimated_cost_usd,
        "conservative_cost_upper_bound_usd": (
            outcome.conservative_cost_upper_bound_usd
        ),
        "usage_unavailable": outcome.usage_unavailable,
    }


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print(
            "NOT RUN: OPENAI_API_KEY is not configured; no live PASS is claimed."
        )
        return 2
    config = replace(
        TextbookParserConfig.from_env(),
        enabled=True,
        mode=ParserMode.required,
    )
    source_manifest = repository_safe_seed_manifest()
    cases = _stratified_cases(source_manifest.cases)
    measured_cost = 0.0
    conservative_cost = 0.0
    usage_unavailable_seen = False
    failures: list[dict[str, str]] = []
    predictions: list[Prediction] = []
    for case in cases:
        remaining_budget = COST_LIMIT_USD - conservative_cost
        if remaining_budget <= 0:
            print(
                "FAILED: conservative cost upper bound exhausted before all cases."
            )
            return 3
        outcome = parse_textbook_problem(
            case.problem_text,
            config=config,
            cache=_DisabledCache(),
            cost_budget_usd=remaining_budget,
        )
        prediction = _prediction(case, outcome)
        predictions.append(prediction)
        measured_cost += outcome.usage.estimated_cost_usd
        conservative_cost += outcome.conservative_cost_upper_bound_usd
        usage_unavailable_seen = (
            usage_unavailable_seen or outcome.usage_unavailable
        )
        if outcome.status.value in {"parser_error", "parser_unavailable"}:
            failures.append(
                {
                    "case_id": case.case_id,
                    "failure_code": (
                        outcome.failure_code or outcome.status.value
                    ),
                }
            )
        if outcome.validated and any(
            issue.code.value == "invented_explicit_number"
            for issue in outcome.validated.issues
        ):
            failures.append(
                {
                    "case_id": case.case_id,
                    "failure_code": "invented_explicit_number",
                }
            )
        print(
            "CASE_SUMMARY="
            + json.dumps(
                _case_summary(case, outcome, prediction),
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    print(
        "COST_SUMMARY="
        + json.dumps(
            {
                "case_count": len(cases),
                "measured_cost_usd": round(measured_cost, 9),
                "conservative_cost_upper_bound_usd": round(
                    conservative_cost, 9
                ),
                "exact_total_cost_available": not usage_unavailable_seen,
            },
            sort_keys=True,
        )
    )
    metrics = evaluate_predictions(
        BenchmarkManifest(
            schema_version=source_manifest.schema_version,
            corpus_kind="live_stratified_cache_disabled",
            copyright_status=source_manifest.copyright_status,
            cases=cases,
        ),
        predictions,
    )
    harness = harness_integrity_report()
    hard_safety = {
        "confident_wrong_solve": metrics.confident_wrong_solve,
        "invented_explicit_fact_rate": metrics.invented_explicit_fact_rate,
        "answer_authority_violation_rate": (
            metrics.answer_authority_violation_rate
        ),
        "unsafe_patch_bypass_rate": metrics.unsafe_patch_bypass_rate,
        "cost_limit_exceeded": conservative_cost > COST_LIMIT_USD,
    }
    parser_quality = {
        "entity_accuracy": metrics.entity_accuracy,
        "segment_accuracy": metrics.segment_accuracy,
        "event_accuracy": metrics.event_accuracy,
        "explicit_fact_precision": metrics.explicit_fact_precision,
        "explicit_fact_recall": metrics.explicit_fact_recall,
        "unit_accuracy": metrics.unit_accuracy,
        "entity_binding_accuracy": metrics.entity_binding_accuracy,
        "segment_binding_accuracy": metrics.segment_binding_accuracy,
        "relation_accuracy": metrics.relation_accuracy,
        "query_accuracy": metrics.query_accuracy,
        "route_accuracy": metrics.route_accuracy,
        "terminal_accuracy": metrics.terminal_accuracy,
        "safe_abstention": metrics.safe_abstention,
        "parser_error_rate": metrics.parser_error_rate,
        "end_to_end_solve_success": metrics.end_to_end_solve_success,
    }
    print("HARNESS_INTEGRITY=" + json.dumps(harness, sort_keys=True))
    print("HARD_SAFETY=" + json.dumps(hard_safety, sort_keys=True))
    print("PARSER_QUALITY=" + json.dumps(parser_quality, sort_keys=True))

    required_perfect = (
        metrics.entity_binding_accuracy,
        metrics.segment_binding_accuracy,
        metrics.segment_accuracy,
        metrics.relation_accuracy,
        metrics.clarification_accuracy,
        metrics.figure_dependency_accuracy,
        metrics.route_accuracy,
        metrics.terminal_accuracy,
        metrics.end_to_end_solve_success,
        metrics.safe_abstention,
    )
    if not all(harness.values()):
        failures.append(
            {"case_id": "harness", "failure_code": "harness_integrity_gate"}
        )
    if any(
        (
            metrics.confident_wrong_solve != 0.0,
            metrics.invented_explicit_fact_rate != 0.0,
            metrics.answer_authority_violation_rate != 0.0,
            metrics.unsafe_patch_bypass_rate != 0.0,
            conservative_cost > COST_LIMIT_USD,
        )
    ):
        failures.append(
            {"case_id": "aggregate", "failure_code": "hard_safety_gate"}
        )
    if any(item != 1.0 for item in required_perfect):
        failures.append(
            {"case_id": "aggregate", "failure_code": "full_gold_gate"}
        )
    if conservative_cost > COST_LIMIT_USD:
        print("FAILED: conservative cost upper bound exceeded.")
        return 3
    if failures:
        print(
            "FAILED_CASES="
            + json.dumps(failures, ensure_ascii=False, sort_keys=True)
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
