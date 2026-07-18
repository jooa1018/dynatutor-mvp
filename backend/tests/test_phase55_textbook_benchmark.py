from __future__ import annotations

from collections import Counter

from engine.textbook_parser.benchmark import Prediction, evaluate_predictions
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


def test_benchmark_metric_calculator_passes_exact_recorded_gold_projection():
    manifest = repository_safe_seed_manifest()
    predictions = [
        Prediction(
            case_id=item.case_id,
            labels=item.gold,
            confident_solve=item.gold.supported_status == "supported",
        )
        for item in manifest.cases
    ]
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
