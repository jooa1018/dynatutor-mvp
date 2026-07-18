from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
import sys
from typing import Callable

from engine.textbook_parser.benchmark import (
    BenchmarkManifest,
    Prediction,
    core_contract_failure_codes,
    evaluate_predictions,
    harness_integrity_report,
    semantic_graph_from_labels,
)
from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.contracts import RelationKind
from engine.textbook_parser.orchestrator import ParseOutcome, parse_textbook_problem
from engine.textbook_parser.recorded_benchmark import (
    prediction_from_recorded_seed,
    recorded_seed_payload,
)
from engine.textbook_parser.relation_policy import (
    RELATION_PARTICIPANT_POLICIES,
    relation_policy_defined,
)
from engine.textbook_parser.seed_corpus import repository_safe_seed_manifest
from tools.run_phase55_live_smoke import (
    COST_LIMIT_USD,
    _DisabledCache,
    _case_summary,
    _prediction,
    _stratified_cases,
)


TARGETED_CASE_IDS = (
    "kinematics_001",
    "figure_001",
    "insufficient_001",
    "rigid_001",
    "pulley_001",
    "work_energy_001",
    "collision_001",
    "newton_001",
)
TARGETED_SYSTEM_TYPES = {
    "rigid_001": "fixed_axis_rotation",
    "pulley_001": "pulley_atwood",
    "work_energy_001": "constant_force_work",
    "collision_001": "impulse_momentum",
    "newton_001": "single_particle_newton",
}


@dataclass(frozen=True)
class StagedRunResult:
    exit_code: int
    stage_1_passed: bool
    full_passed: bool
    outcomes: dict[str, ParseOutcome]
    predictions: dict[str, Prediction]
    measured_cost_usd: float
    conservative_cost_upper_bound_usd: float
    failures: tuple[dict[str, str], ...]


def _projectile_contract_matches(case, payload: dict[str, object]) -> bool:
    if case.category != "포물선·곡선·극좌표":
        return True
    facts = payload.get("explicit_facts", [])
    segments = payload.get("motion_segments", [])
    candidates = payload.get("interpretation_candidates", [])
    entities = payload.get("entities", [])
    background = next(
        (
            item
            for item in facts
            if isinstance(item, dict)
            and item.get("semantic_key") == "background_height"
        ),
        None,
    )
    return bool(
        case.gold.entities == ["ball", "sign"]
        and list(case.gold.fact_entity_binding.values()) == ["ball", "ball", "sign"]
        and list(case.gold.fact_segment_binding.values())
        == ["motion_1", "motion_1", None]
        and case.gold.queries == ["max_height:ball:motion_1"]
        and [
            (item.get("entity_id"), item.get("kind"))
            for item in entities
            if isinstance(item, dict)
        ]
        == [("ball", "particle"), ("sign", "other")]
        and len(segments) == 1
        and isinstance(segments[0], dict)
        and segments[0].get("actor_ids") == ["ball"]
        and isinstance(background, dict)
        and background.get("subject_id") == "sign"
        and background.get("segment_id") is None
        and background.get("relevance") == "context_only"
        and len(candidates) == 1
        and isinstance(candidates[0], dict)
        and background.get("fact_id") not in candidates[0].get("fact_ids", [])
    )


def preflight_staged_cases(selected, targeted, remaining) -> tuple[dict[str, str], ...]:
    failures: list[dict[str, str]] = []
    selected_ids = [item.case_id for item in selected]
    targeted_ids = [item.case_id for item in targeted]
    remaining_ids = [item.case_id for item in remaining]
    if len(selected) != 20 or len(set(selected_ids)) != 20:
        failures.append({"case_id": "aggregate", "failure_code": "selected_case_count"})
    if targeted_ids != list(TARGETED_CASE_IDS):
        failures.append({"case_id": "aggregate", "failure_code": "targeted_composition"})
    if (
        len(remaining) != 12
        or set(targeted_ids) & set(remaining_ids)
        or set(targeted_ids) | set(remaining_ids) != set(selected_ids)
    ):
        failures.append({"case_id": "aggregate", "failure_code": "remaining_composition"})
    if set(RELATION_PARTICIPANT_POLICIES) != {item.value for item in RelationKind}:
        failures.append({"case_id": "aggregate", "failure_code": "relation_policy_incomplete"})
    if not all(harness_integrity_report().values()):
        failures.append({"case_id": "aggregate", "failure_code": "harness_integrity"})

    for case in selected:
        try:
            payload = recorded_seed_payload(case)
            prediction = prediction_from_recorded_seed(case)
        except Exception:
            failures.append(
                {"case_id": case.case_id, "failure_code": "recorded_graph_invalid"}
            )
            continue
        expected_graph = semantic_graph_from_labels(case.gold)
        actual_graph = semantic_graph_from_labels(prediction.labels)
        failures.extend(
            {"case_id": case.case_id, "failure_code": code}
            for code in core_contract_failure_codes(expected_graph, actual_graph)
        )
        if (
            prediction.labels.expected_system_type
            != case.gold.expected_system_type
        ):
            failures.append(
                {"case_id": case.case_id, "failure_code": "expected_system_type"}
            )
        if (
            prediction.labels.expected_terminal_status
            != case.gold.expected_terminal_status
        ):
            failures.append(
                {"case_id": case.case_id, "failure_code": "expected_terminal"}
            )
        if any(
            not relation_policy_defined(item.kind)
            for graph in (expected_graph, actual_graph)
            for item in graph.relations
        ):
            failures.append(
                {"case_id": case.case_id, "failure_code": "relation_policy_undefined"}
            )
        if not _projectile_contract_matches(case, payload):
            failures.append(
                {"case_id": case.case_id, "failure_code": "projectile_context_binding"}
            )

    unique = {
        (item["case_id"], item["failure_code"]): item for item in failures
    }
    return tuple(unique[key] for key in sorted(unique))


def _hard_safety_failures(cases_by_id, outcomes, predictions) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for case_id, outcome in outcomes.items():
        if outcome.status.value in {"parser_error", "parser_unavailable"}:
            failures.append(
                {"case_id": case_id, "failure_code": outcome.failure_code or outcome.status.value}
            )
        if outcome.validated and any(
            issue.code.value in {
                "invented_explicit_number",
                "answer_authority_field",
                "authoritative_patch_rejected",
            }
            for issue in outcome.validated.issues
        ):
            failures.append({"case_id": case_id, "failure_code": "hard_safety"})
        prediction = predictions[case_id]
        answer_wrong = (
            cases_by_id[case_id].gold.expected_end_to_end_answer is not None
            and prediction.labels.expected_end_to_end_answer
            != cases_by_id[case_id].gold.expected_end_to_end_answer
        )
        if prediction.confident_solve and answer_wrong:
            failures.append({"case_id": case_id, "failure_code": "confident_wrong_solve"})
        if (
            prediction.invented_explicit_fact
            or prediction.answer_authority_violation
            or prediction.unsafe_patch_bypass
        ):
            failures.append({"case_id": case_id, "failure_code": "hard_safety"})
    return failures


def _targeted_failures(cases_by_id, outcomes, predictions) -> list[dict[str, str]]:
    failures = _hard_safety_failures(cases_by_id, outcomes, predictions)
    expected_terminals = {
        "figure_001": "needs_figure",
        "insufficient_001": "insufficient_information",
        "rigid_001": "solver_gap",
        "pulley_001": "solver_gap",
        "work_energy_001": "solver_gap",
        "collision_001": "solver_gap",
        "newton_001": "solver_gap",
    }
    kinematics = outcomes["kinematics_001"]
    if kinematics.status.value not in {"accepted", "accepted_with_visible_assumptions"}:
        failures.append({"case_id": "kinematics_001", "failure_code": "not_accepted"})
    prediction = predictions["kinematics_001"]
    if prediction.labels.expected_end_to_end_answer != cases_by_id[
        "kinematics_001"
    ].gold.expected_end_to_end_answer:
        failures.append({"case_id": "kinematics_001", "failure_code": "deterministic_answer_mismatch"})
    for case_id, terminal in expected_terminals.items():
        if outcomes[case_id].status.value != terminal:
            failures.append({"case_id": case_id, "failure_code": f"terminal:{outcomes[case_id].status.value}"})
    for case_id, system_type in TARGETED_SYSTEM_TYPES.items():
        if outcomes[case_id].diagnostic_context()["selected_system_type"] != system_type:
            failures.append({"case_id": case_id, "failure_code": "system_type_mismatch"})
    return failures


def _full_gate_failures(manifest, predictions) -> list[dict[str, str]]:
    metrics = evaluate_predictions(manifest, predictions)
    failures: list[dict[str, str]] = []
    required_perfect = (
        metrics.entity_accuracy,
        metrics.explicit_fact_precision,
        metrics.explicit_fact_recall,
        metrics.unit_accuracy,
        metrics.entity_binding_accuracy,
        metrics.segment_binding_accuracy,
        metrics.segment_accuracy,
        metrics.relation_accuracy,
        metrics.query_accuracy,
        metrics.clarification_accuracy,
        metrics.figure_dependency_accuracy,
        metrics.route_accuracy,
        metrics.terminal_accuracy,
        metrics.end_to_end_solve_success,
        metrics.safe_abstention,
    )
    if not all(harness_integrity_report().values()):
        failures.append({"case_id": "harness", "failure_code": "harness_integrity_gate"})
    if any(
        (
            metrics.confident_wrong_solve != 0.0,
            metrics.invented_explicit_fact_rate != 0.0,
            metrics.answer_authority_violation_rate != 0.0,
            metrics.unsafe_patch_bypass_rate != 0.0,
        )
    ):
        failures.append({"case_id": "aggregate", "failure_code": "hard_safety_gate"})
    if any(value != 1.0 for value in required_perfect):
        failures.append({"case_id": "aggregate", "failure_code": "full_gold_gate"})
    return failures


def run_staged(
    *,
    config: TextbookParserConfig,
    parse_case: Callable[..., ParseOutcome] = parse_textbook_problem,
    emit: Callable[[str], None] = print,
) -> StagedRunResult:
    source = repository_safe_seed_manifest()
    selected = _stratified_cases(source.cases)
    cases_by_id = {item.case_id: item for item in selected}
    targeted = [cases_by_id[item] for item in TARGETED_CASE_IDS]
    remaining = [item for item in selected if item.case_id not in TARGETED_CASE_IDS]
    preflight_failures = preflight_staged_cases(selected, targeted, remaining)
    if preflight_failures:
        emit(
            "HARNESS_CONTRACT_FAILURE="
            + json.dumps({"failures": preflight_failures}, sort_keys=True)
        )
        return StagedRunResult(
            2,
            False,
            False,
            {},
            {},
            0.0,
            0.0,
            preflight_failures,
        )
    emit(
        "HARNESS_PREFLIGHT="
        + json.dumps({"passed": True, "case_count": len(selected)}, sort_keys=True)
    )

    outcomes: dict[str, ParseOutcome] = {}
    predictions: dict[str, Prediction] = {}
    outcome_by_problem_text: dict[str, ParseOutcome] = {}
    measured = 0.0
    conservative = 0.0

    def execute(case) -> None:
        nonlocal measured, conservative
        outcome = outcome_by_problem_text.get(case.problem_text)
        reused = outcome is not None
        if outcome is None:
            remaining_budget = COST_LIMIT_USD - conservative
            if remaining_budget <= 0:
                raise RuntimeError("conservative cost budget exhausted before request")
            outcome = parse_case(
                case.problem_text,
                config=config,
                cache=_DisabledCache(),
                cost_budget_usd=remaining_budget,
            )
            outcome_by_problem_text[case.problem_text] = outcome
            measured += outcome.usage.estimated_cost_usd
            conservative += outcome.conservative_cost_upper_bound_usd
        outcomes[case.case_id] = outcome
        predictions[case.case_id] = _prediction(case, outcome)
        summary = _case_summary(case, outcome, predictions[case.case_id])
        summary["staged_reused_parse"] = reused
        emit("CASE_SUMMARY=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))

    for case in targeted:
        execute(case)
    stage_failures = _targeted_failures(cases_by_id, outcomes, predictions)
    if conservative > COST_LIMIT_USD:
        stage_failures.append({"case_id": "aggregate", "failure_code": "cost_limit"})
    emit("TARGETED_STAGE=" + json.dumps({"passed": not stage_failures, "case_ids": list(TARGETED_CASE_IDS), "failures": stage_failures}, sort_keys=True))
    if stage_failures:
        return StagedRunResult(1, False, False, outcomes, predictions, measured, conservative, tuple(stage_failures))

    for case in remaining:
        execute(case)
    ordered_predictions = [predictions[item.case_id] for item in selected]
    live_manifest = BenchmarkManifest(
        schema_version=source.schema_version,
        corpus_kind="live_staged_cache_disabled",
        copyright_status=source.copyright_status,
        cases=selected,
    )
    full_failures = _full_gate_failures(live_manifest, ordered_predictions)
    if conservative > COST_LIMIT_USD:
        full_failures.append({"case_id": "aggregate", "failure_code": "cost_limit"})
    emit("FULL_STAGE=" + json.dumps({"passed": not full_failures, "case_count": len(outcomes), "failures": full_failures, "measured_cost_usd": round(measured, 9), "conservative_cost_upper_bound_usd": round(conservative, 9)}, sort_keys=True))
    return StagedRunResult(
        0 if not full_failures else 1,
        True,
        not full_failures,
        outcomes,
        predictions,
        measured,
        conservative,
        tuple(full_failures),
    )


def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("NOT RUN: OPENAI_API_KEY is not configured; no live PASS is claimed.")
        return 2
    config = replace(
        TextbookParserConfig.from_env(),
        enabled=True,
        mode=ParserMode.required,
    )
    return run_staged(config=config).exit_code


if __name__ == "__main__":
    sys.exit(main())
