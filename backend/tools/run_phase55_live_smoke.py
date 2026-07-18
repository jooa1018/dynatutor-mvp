from __future__ import annotations

from dataclasses import replace
from collections import defaultdict
import os
import sys

from engine.textbook_parser.benchmark import (
    BenchmarkManifest,
    GoldLabels,
    Prediction,
    evaluate_predictions,
)
from engine.textbook_parser.canonical_projection import project_canonical
from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.seed_corpus import repository_safe_seed_manifest
from engine.textbook_parser.orchestrator import parse_textbook_problem


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


def _prediction(case, outcome):
    if outcome.validated is None:
        return Prediction(
            case_id=case.case_id,
            labels=case.gold.model_copy(
                update={
                    "supported_status": outcome.status.value,
                    "expected_end_to_end_answer": None,
                    "expected_terminal_status": outcome.status.value,
                }
            ),
            confident_solve=False,
        )
    validated = outcome.validated
    parse = validated.parse
    selected = next(
        (item for item in validated.candidates if item.candidate_id == validated.selected_candidate_id),
        None,
    )
    candidate = validated.selected_candidate
    answer = None
    terminal = None if validated.accepted else validated.status.value
    confident = validated.accepted
    if validated.accepted:
        from engine.solvers.kinematics import ConstantAcceleration1DSolver

        result = ConstantAcceleration1DSolver().solve(project_canonical(case.problem_text, validated))
        if result.ok and result.answer is not None:
            answer = {
                "numeric": round(float(result.answer.numeric), 6),
                "unit": result.answer.unit.replace("²", "^2").replace("³", "^3"),
            }
        else:
            confident = False
            terminal = "solver_error"
    fact_entity_binding = {
        f"fact_{index}": item.subject_id
        for index, item in enumerate(parse.explicit_facts, start=1)
    }
    fact_segment_binding = {
        f"fact_{index}": item.segment_id
        for index, item in enumerate(parse.explicit_facts, start=1)
    }
    labels = GoldLabels(
        entities=[item.entity_id for item in parse.entities],
        segments=[f"{item.segment_id}:{item.relevance.value}" for item in parse.motion_segments],
        events=[item.kind.value for item in parse.events],
        explicit_facts=[f"{item.semantic_key}:{item.raw_value}:{item.raw_unit}" for item in parse.explicit_facts],
        fact_entity_binding=fact_entity_binding,
        fact_segment_binding=fact_segment_binding,
        relations=[f"{item.kind.value}:" + ":".join(item.entity_ids) for item in parse.relations],
        queries=[f"{item.output_key.value}:{item.subject_id}:{item.segment_id}" for item in parse.queries],
        assumptions=[item.kind.value for item in parse.assumption_proposals],
        required_clarification=validated.status.value in {"needs_confirmation", "insufficient_information"},
        figure_dependency=parse.figure_dependency.level.value,
        expected_system_type=candidate.system_type if candidate is not None else None,
        expected_solver=selected.capability.solver_id if selected is not None else None,
        supported_status="supported" if validated.accepted else validated.status.value,
        expected_end_to_end_answer=answer,
        expected_terminal_status=terminal,
    )
    return Prediction(case_id=case.case_id, labels=labels, confident_solve=confident)


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("SKIPPED: OPENAI_API_KEY is not configured; no live PASS is claimed.")
        return 2
    config = replace(
        TextbookParserConfig.from_env(),
        enabled=True,
        mode=ParserMode.required,
    )
    source_manifest = repository_safe_seed_manifest()
    cases = _stratified_cases(source_manifest.cases)
    total_cost = 0.0
    failures: list[str] = []
    predictions = []
    for case in cases:
        if total_cost >= COST_LIMIT_USD:
            print(f"ABORTED: cumulative estimated cost reached ${total_cost:.6f}.")
            return 3
        outcome = parse_textbook_problem(
            case.problem_text, config=config, cache=_DisabledCache()
        )
        predictions.append(_prediction(case, outcome))
        total_cost += outcome.usage.estimated_cost_usd
        if outcome.status.value in {"parser_error", "parser_unavailable"}:
            failures.append(f"{case.case_id}:{outcome.failure_code or outcome.status.value}")
        if outcome.validated and any(
            issue.code.value == "invented_explicit_number"
            for issue in outcome.validated.issues
        ):
            failures.append(f"{case.case_id}:invented_explicit_number")
        print(
            f"{case.case_id} status={outcome.status.value} "
            f"tokens={outcome.usage.input_tokens}/{outcome.usage.output_tokens} "
            f"cost=${outcome.usage.estimated_cost_usd:.6f}"
        )
    print(f"Live smoke cases={len(cases)} estimated_cost=${total_cost:.6f}")
    metrics = evaluate_predictions(
        BenchmarkManifest(
            schema_version=source_manifest.schema_version,
            corpus_kind="live_stratified_cache_disabled",
            copyright_status=source_manifest.copyright_status,
            cases=cases,
        ),
        predictions,
    )
    print("Live full-gold metrics=" + str(metrics.to_dict()))
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
    if any(item != 1.0 for item in required_perfect) or metrics.confident_wrong_solve != 0.0:
        failures.append("full_gold_gate")
    if total_cost > COST_LIMIT_USD:
        print("FAILED: cost limit exceeded.")
        return 3
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
