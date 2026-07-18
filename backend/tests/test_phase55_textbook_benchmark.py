from __future__ import annotations

from collections import Counter

from engine.textbook_parser.benchmark import (
    BenchmarkCase,
    BenchmarkManifest,
    GoldLabels,
    Prediction,
    SemanticEntity,
    SemanticEvent,
    SemanticFact,
    SemanticGraph,
    SemanticQuery,
    SemanticRelation,
    SemanticSegment,
    evaluate_predictions,
    metamorphic_problem_variants,
    semantic_signature_diff,
)
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


def _semantic_graph() -> SemanticGraph:
    return SemanticGraph(
        entities=[
            SemanticEntity(entity_id="body", kind="block"),
            SemanticEntity(entity_id="counterweight", kind="pulley"),
        ],
        segments=[
            SemanticSegment(
                segment_id="motion",
                order=1,
                relevance="target",
                motion_models=("constant_acceleration_1d",),
                actor_ids=("body", "counterweight"),
                start_event_id="start",
                end_event_id="finish",
            )
        ],
        events=[
            SemanticEvent(
                event_id="start",
                kind="start",
                subject_ids=("body", "counterweight"),
                segment_id="motion",
            ),
            SemanticEvent(
                event_id="finish",
                kind="finish",
                subject_ids=("body", "counterweight"),
                segment_id="motion",
            ),
        ],
        facts=[
            SemanticFact(
                fact_id="mass_a",
                semantic_key="mass",
                raw_value="2",
                raw_unit="kg",
                subject_id="body",
                segment_id="motion",
                temporal_role="timeless",
                direction="not_applicable",
                quantity_occurrence_index=0,
                relevance="solver_input",
            ),
            SemanticFact(
                fact_id="mass_b",
                semantic_key="mass",
                raw_value="2",
                raw_unit="kg",
                subject_id="counterweight",
                segment_id="motion",
                temporal_role="timeless",
                direction="not_applicable",
                quantity_occurrence_index=1,
                relevance="solver_input",
            ),
        ],
        queries=[
            SemanticQuery(
                query_id="target",
                output_key="acceleration",
                component="magnitude",
                subject_id="body",
                segment_id="motion",
                event_id="finish",
            )
        ],
        relations=[
            SemanticRelation(
                relation_id="rope",
                kind="connected_by_rope",
                participant_ids=("body", "counterweight"),
                segment_id="motion",
            )
        ],
    )


def _renamed_and_reordered(graph: SemanticGraph) -> SemanticGraph:
    entity = {"body": "model_x", "counterweight": "model_y"}
    segment = {"motion": "model_segment"}
    event = {"start": "model_start", "finish": "model_finish"}
    return SemanticGraph(
        entities=[
            SemanticEntity(entity_id="model_y", kind="pulley"),
            SemanticEntity(entity_id="model_x", kind="block"),
        ],
        segments=[
            SemanticSegment(
                segment_id="model_segment",
                order=1,
                relevance="target",
                motion_models=("constant_acceleration_1d",),
                actor_ids=tuple(entity[item] for item in graph.segments[0].actor_ids),
                start_event_id=event["start"],
                end_event_id=event["finish"],
            )
        ],
        events=[
            SemanticEvent(
                event_id=event[item.event_id],
                kind=item.kind,
                subject_ids=tuple(entity[value] for value in item.subject_ids),
                segment_id=segment[item.segment_id],
            )
            for item in reversed(graph.events)
        ],
        facts=[
            SemanticFact(
                **{
                    **item.model_dump(),
                    "fact_id": f"model_{item.fact_id}",
                    "subject_id": entity[item.subject_id],
                    "segment_id": segment[item.segment_id],
                    "event_id": (
                        event[item.event_id] if item.event_id is not None else None
                    ),
                }
            )
            for item in reversed(graph.facts)
        ],
        queries=[
            SemanticQuery(
                **{
                    **item.model_dump(),
                    "query_id": "model_query",
                    "subject_id": entity[item.subject_id],
                    "segment_id": segment[item.segment_id],
                    "event_id": event[item.event_id],
                }
            )
            for item in reversed(graph.queries)
        ],
        relations=[
            SemanticRelation(
                relation_id="model_relation",
                kind=item.kind,
                participant_ids=tuple(
                    entity[value] for value in item.participant_ids
                ),
                segment_id=segment[item.segment_id],
            )
            for item in reversed(graph.relations)
        ],
    )


def _labels(graph: SemanticGraph) -> GoldLabels:
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
        required_clarification=True,
        figure_dependency="none",
        expected_system_type=None,
        expected_solver=None,
        supported_status="needs_confirmation",
        expected_end_to_end_answer=None,
        expected_terminal_status="needs_confirmation",
        semantic_graph=graph,
    )


def _evaluate_pair(expected: SemanticGraph, actual: SemanticGraph):
    case = BenchmarkCase(
        case_id="semantic_graph_case",
        provenance="repository_safe_generated",
        category="harness",
        problem_text="Repository-safe semantic graph harness case.",
        gold=_labels(expected),
    )
    return evaluate_predictions(
        BenchmarkManifest(
            schema_version="phase55-benchmark-v4-semantic-graph",
            corpus_kind="harness",
            copyright_status="repository_safe_generated",
            cases=[case],
        ),
        [Prediction(case_id=case.case_id, labels=_labels(actual))],
    )


def test_semantic_graph_metrics_ignore_all_node_id_spelling_and_array_order():
    expected = _semantic_graph()
    actual = _renamed_and_reordered(expected)
    metrics = _evaluate_pair(expected, actual)
    for field in (
        "entity_accuracy",
        "segment_accuracy",
        "event_accuracy",
        "explicit_fact_precision",
        "explicit_fact_recall",
        "unit_accuracy",
        "entity_binding_accuracy",
        "segment_binding_accuracy",
        "relation_accuracy",
        "query_accuracy",
    ):
        assert getattr(metrics, field) == 1.0
    diff = semantic_signature_diff(expected, actual)
    assert diff["missing_fact_signatures"] == []
    assert diff["unexpected_fact_signatures"] == []


def test_semantic_graph_metrics_ignore_array_order_by_itself():
    expected = _semantic_graph()
    actual = expected.model_copy(deep=True)
    actual.entities.reverse()
    actual.events.reverse()
    actual.facts.reverse()
    actual.queries.reverse()
    actual.relations.reverse()
    metrics = _evaluate_pair(expected, actual)
    assert metrics.entity_accuracy == 1.0
    assert metrics.event_accuracy == 1.0
    assert metrics.explicit_fact_recall == 1.0
    assert metrics.query_accuracy == 1.0


def test_semantic_entity_binding_change_reduces_only_real_binding_score():
    actual = _renamed_and_reordered(_semantic_graph())
    actual.facts[0].subject_id = "model_x"
    assert _evaluate_pair(_semantic_graph(), actual).entity_binding_accuracy < 1.0


def test_semantic_segment_binding_change_reduces_binding_score():
    actual = _renamed_and_reordered(_semantic_graph())
    actual.facts[0].segment_id = None
    assert _evaluate_pair(_semantic_graph(), actual).segment_binding_accuracy < 1.0


def test_semantic_relation_participant_role_change_reduces_relation_accuracy():
    actual = _renamed_and_reordered(_semantic_graph())
    actual.relations[0].participant_ids = tuple(
        reversed(actual.relations[0].participant_ids)
    )
    assert _evaluate_pair(_semantic_graph(), actual).relation_accuracy < 1.0


def test_semantic_query_subject_or_segment_change_reduces_query_accuracy():
    wrong_subject = _renamed_and_reordered(_semantic_graph())
    wrong_subject.queries[0].subject_id = "model_y"
    assert _evaluate_pair(_semantic_graph(), wrong_subject).query_accuracy < 1.0

    wrong_segment = _renamed_and_reordered(_semantic_graph())
    wrong_segment.queries[0].segment_id = None
    assert _evaluate_pair(_semantic_graph(), wrong_segment).query_accuracy < 1.0


def test_repeated_fact_scoring_uses_counter_not_set_semantics():
    actual = _renamed_and_reordered(_semantic_graph())
    actual.facts.pop()
    metrics = _evaluate_pair(_semantic_graph(), actual)
    assert metrics.explicit_fact_recall == 0.5
    assert metrics.entity_binding_accuracy == 0.5


def test_graph_quality_mismatch_is_not_mislabeled_as_invented_fact():
    expected = _semantic_graph()
    actual = _renamed_and_reordered(expected)
    actual.facts[0].semantic_key = "different_but_source_grounded_key"
    metrics = _evaluate_pair(expected, actual)
    assert metrics.explicit_fact_precision < 1.0
    assert metrics.invented_explicit_fact_rate == 0.0


def test_invented_fact_safety_metric_uses_validator_signal():
    graph = _semantic_graph()
    case = BenchmarkCase(
        case_id="invented_fact_signal",
        provenance="repository_safe_generated",
        category="harness",
        problem_text="Repository-safe invented fact signal harness.",
        gold=_labels(graph),
    )
    metrics = evaluate_predictions(
        BenchmarkManifest(
            schema_version="phase55-benchmark-v4-semantic-graph",
            corpus_kind="harness",
            copyright_status="repository_safe_generated",
            cases=[case],
        ),
        [
            Prediction(
                case_id=case.case_id,
                labels=_labels(graph.model_copy(deep=True)),
                invented_explicit_fact=True,
            )
        ],
    )
    assert metrics.explicit_fact_precision == 1.0
    assert metrics.invented_explicit_fact_rate == 1.0
