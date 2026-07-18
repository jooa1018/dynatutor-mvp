from __future__ import annotations

from collections import Counter

from engine.textbook_parser.benchmark import evaluate_predictions, metamorphic_problem_variants
from engine.textbook_parser.recorded_benchmark import (
    recorded_seed_payload,
    validate_recorded_seed_manifest,
)
from engine.textbook_parser.orchestrator import validate_recorded_payload
from engine.textbook_parser.seed_corpus import repository_safe_seed_manifest


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
    assert metrics.entity_binding_accuracy == 1.0
    assert metrics.segment_binding_accuracy == 1.0
    assert metrics.route_accuracy == 1.0
    assert metrics.end_to_end_solve_success == 1.0
    assert metrics.safe_abstention == 1.0
    assert metrics.confident_wrong_solve == 0.0
    assert metrics.invented_explicit_fact_rate == 0.0


def test_recorded_benchmark_adapter_never_projects_gold_labels():
    import inspect
    import engine.textbook_parser.recorded_benchmark as recorded

    source = inspect.getsource(recorded.recorded_seed_payload)
    assert ".gold" not in source
    manifest = repository_safe_seed_manifest()
    payload = recorded_seed_payload(manifest.cases[0])
    assert payload["explicit_facts"]
    assert payload["interpretation_candidates"]


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
