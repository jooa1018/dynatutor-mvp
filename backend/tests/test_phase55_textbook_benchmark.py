from __future__ import annotations

from collections import Counter

from engine.textbook_parser.benchmark import Prediction, evaluate_predictions, metamorphic_problem_variants
from engine.textbook_parser.recorded_benchmark import (
    recorded_seed_payload,
    validate_recorded_seed_manifest,
)
from engine.textbook_parser.orchestrator import validate_recorded_payload
from engine.textbook_parser.seed_corpus import binding_stress_manifest, repository_safe_seed_manifest


def test_repository_safe_seed_corpus_has_required_size_and_distribution():
    manifest = repository_safe_seed_manifest()
    counts = Counter(item.category for item in manifest.cases)
    assert len(manifest.cases) == 192
    assert counts["직선·다구간 운동학"] == 30
    assert counts["포물선·곡선·극좌표"] == 20
    assert counts["Newton·마찰"] == 25
    assert counts["도르래·구속조건"] == 20
    assert counts["일-에너지"] == 20
    assert counts["충격량·충돌"] == 15
    assert counts["강체 속도·가속도"] == 20
    assert counts["구름·회전"] == 15
    assert counts["진동"] == 15
    assert counts["조건 부족"] + counts["그림 필요"] + counts["solver gap"] == 12
    assert all(item.provenance.startswith("repository_safe") for item in manifest.cases)


def test_recorded_outputs_run_full_validator_route_and_solver_benchmark():
    manifest = repository_safe_seed_manifest()
    predictions = validate_recorded_seed_manifest(manifest.cases)
    metrics = evaluate_predictions(manifest, predictions)
    assert metrics.case_count == 192
    assert metrics.explicit_fact_precision == 1.0
    assert metrics.explicit_fact_recall == 1.0
    assert metrics.query_accuracy == 1.0
    assert metrics.segment_accuracy == 1.0
    assert metrics.relation_accuracy == 1.0
    assert metrics.entity_binding_accuracy == 1.0
    assert metrics.segment_binding_accuracy == 1.0
    assert metrics.route_accuracy == 1.0
    assert metrics.clarification_accuracy == 1.0
    assert metrics.figure_dependency_accuracy == 1.0
    assert metrics.terminal_accuracy == 1.0
    assert metrics.end_to_end_solve_success == 1.0
    assert metrics.safe_abstention == 1.0
    assert metrics.confident_wrong_solve == 0.0
    assert metrics.invented_explicit_fact_rate == 0.0


def test_binding_stress_manifest_covers_required_closure_dimensions():
    manifest = binding_stress_manifest()
    ids = {item.case_id for item in manifest.cases}
    assert ids == {
        "binding_multi_entity",
        "binding_multi_segment",
        "binding_before_after",
        "binding_repeated_symbol_direction",
        "binding_relation_role",
    }
    assert any(len(item.gold.entities) > 1 for item in manifest.cases)
    assert any(len(item.gold.segments) > 1 for item in manifest.cases)
    assert any(item.gold.relations for item in manifest.cases)


def test_benchmark_gate_fails_when_an_entity_binding_is_wrong():
    manifest = binding_stress_manifest()
    predictions = [
        Prediction(case_id=item.case_id, labels=item.gold.model_copy(deep=True))
        for item in manifest.cases
    ]
    predictions[0].labels.fact_entity_binding["fact_1"] = "cart_b"
    metrics = evaluate_predictions(manifest, predictions)
    assert metrics.entity_binding_accuracy < 1.0
    assert metrics.route_accuracy == 1.0


def test_benchmark_binding_metrics_ignore_fact_id_spelling_but_not_wrong_bindings():
    manifest = binding_stress_manifest()
    predictions = []
    for item in manifest.cases:
        labels = item.gold.model_copy(deep=True)
        labels.fact_entity_binding = {
            f"model_fact_{index}": value
            for index, value in enumerate(labels.fact_entity_binding.values(), start=1)
        }
        labels.fact_segment_binding = {
            f"model_fact_{index}": value
            for index, value in enumerate(labels.fact_segment_binding.values(), start=1)
        }
        predictions.append(Prediction(case_id=item.case_id, labels=labels))
    metrics = evaluate_predictions(manifest, predictions)
    assert metrics.entity_binding_accuracy == 1.0
    assert metrics.segment_binding_accuracy == 1.0

    first_key = next(iter(predictions[0].labels.fact_entity_binding))
    predictions[0].labels.fact_entity_binding[first_key] = "definitely_wrong_entity"
    assert evaluate_predictions(manifest, predictions).entity_binding_accuracy < 1.0


def test_benchmark_gate_fails_when_segments_or_relations_are_omitted():
    manifest = binding_stress_manifest()
    predictions = [
        Prediction(case_id=item.case_id, labels=item.gold.model_copy(deep=True))
        for item in manifest.cases
    ]
    predictions[1].labels.segments = []
    predictions[0].labels.relations = []
    metrics = evaluate_predictions(manifest, predictions)
    assert metrics.segment_accuracy < 1.0
    assert metrics.relation_accuracy < 1.0


def test_recorded_benchmark_adapter_never_projects_gold_labels():
    import inspect
    import engine.textbook_parser.recorded_benchmark as recorded

    source = inspect.getsource(recorded.recorded_seed_payload)
    assert ".gold" not in source
    manifest = repository_safe_seed_manifest()
    payload = recorded_seed_payload(manifest.cases[0])
    assert payload["explicit_facts"]
    assert payload["interpretation_candidates"]


def test_needs_figure_is_an_explicit_required_clarification_terminal():
    manifest = repository_safe_seed_manifest()
    figure_cases = [item for item in manifest.cases if item.category == "그림 필요"]
    assert figure_cases
    assert all(item.gold.required_clarification for item in figure_cases)
    predictions = validate_recorded_seed_manifest(figure_cases)
    assert all(item.labels.required_clarification for item in predictions)
    assert all(item.labels.expected_terminal_status == "needs_figure" for item in predictions)


def test_metamorphic_seed_variants_remain_grounded_and_safe():
    manifest = repository_safe_seed_manifest()
    for case in manifest.cases[:10]:
        baseline = validate_recorded_payload(
            case.problem_text, recorded_seed_payload(case)
        )
        for variant_text in metamorphic_problem_variants(case.problem_text):
            variant = case.model_copy(update={"problem_text": variant_text})
            validated = validate_recorded_payload(
                variant_text, recorded_seed_payload(variant)
            )
            assert validated.status == baseline.status
            assert not any(
                item.code.value == "invented_explicit_number"
                for item in validated.issues
            )
