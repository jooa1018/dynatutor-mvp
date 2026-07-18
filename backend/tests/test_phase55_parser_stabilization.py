from __future__ import annotations

from dataclasses import replace
import json

import pytest
from pydantic import ValidationError

from engine.capabilities.loader import load_capability_matrix
from engine.textbook_parser.benchmark import semantic_graph_from_parse
from engine.textbook_parser.cache import ParserCache
from engine.textbook_parser.canonical_projection import project_canonical
from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.contracts import (
    MotionModel,
    SegmentRelevance,
    TemporalRole,
    TextbookProblemParseWireV2,
)
from engine.textbook_parser.errors import (
    ErrorCode,
    ParserIncompleteError,
    ParserOutputMissingError,
    ParserRefusalError,
    RepairIssueV1,
)
from engine.textbook_parser.graph_validation import validate_graph_contract
from engine.textbook_parser.legal_fixtures import legal_graph_fixtures
from engine.textbook_parser.normalization import (
    WireNormalizationError,
    normalize_wire_parse,
)
from engine.textbook_parser.ontology import (
    ExplicitSemanticKey,
    PARSER_SYSTEM_TYPE_ONTOLOGY,
    SEMANTIC_DIMENSIONS,
    SOLVER_CAPABILITY_SYSTEM_TYPES,
)
from engine.textbook_parser.openai_client import (
    OpenAITextbookParserClient,
    StructuredParseResponse,
)
from engine.textbook_parser.orchestrator import (
    ParseOutcome,
    _repair_issues_from_exception,
    _validation_repair_issues,
    parse_textbook_problem,
    validate_recorded_payload,
)
from engine.textbook_parser.prompt import generated_examples, generated_vocabulary, load_prompt
from engine.textbook_parser.recorded_benchmark import recorded_seed_payload
from engine.textbook_parser.repair import format_repair_request
from engine.textbook_parser.seed_corpus import repository_safe_seed_manifest
from engine.textbook_parser.telemetry import UsageSummary
from engine.textbook_parser.temporal_bindings import resolve_fact_symbol
from engine.textbook_parser.validation import ParseDecisionStatus, validate_parse
from engine.textbook_parser.validators.safety import validate_payload_authority
from engine.solvers.registry import SolverRegistry
from tools.run_phase55_live_staged import TARGETED_CASE_IDS, run_staged


def _fixtures():
    return {item.fixture_id: item for item in legal_graph_fixtures()}


def test_controlled_ontology_covers_capability_matrix_and_generates_dimensions_and_prompt():
    matrix_types = {item["system_type"] for item in load_capability_matrix().capabilities}
    assert matrix_types == SOLVER_CAPABILITY_SYSTEM_TYPES
    assert matrix_types < PARSER_SYSTEM_TYPE_ONTOLOGY
    vocabulary = generated_vocabulary()
    assert set(vocabulary["system_types"]) == PARSER_SYSTEM_TYPE_ONTOLOGY
    assert set(vocabulary["semantic_keys"]) == set(SEMANTIC_DIMENSIONS)
    assert "kinematics" not in vocabulary["system_types"]
    assert "speed" not in vocabulary["semantic_keys"]


def test_all_legal_graph_fixtures_pass_schema_evidence_graph_temporal_and_route_policy():
    fixtures = _fixtures()
    assert set(fixtures) == {
        "constant_acceleration",
        "newton_particle",
        "fixed_axis_rigid_point",
        "pure_rolling",
        "figure_required",
        "atwood_pulley",
        "constant_force_work",
        "insufficient_information",
        "vibration",
        "collision_impulse",
        "projectile",
        "unsupported_nonlinear_flow",
    }
    for fixture in fixtures.values():
        assert validate_graph_contract(fixture.parse) == (), fixture.fixture_id
        assert not validate_payload_authority(fixture.parse.model_dump(mode="json"))
        validated = validate_parse(fixture.problem_text, fixture.parse)
        assert validated.status.value == fixture.expected_terminal, fixture.fixture_id
        if fixture.expected_system_type is not None:
            evaluation = validated.candidates[0]
            assert evaluation.effective_candidate.system_type.value == fixture.expected_system_type
        assert not any(
            item.code
            in {
                ErrorCode.invented_explicit_number,
                ErrorCode.quantity_occurrence_reused,
                ErrorCode.temporal_binding_ambiguous,
                ErrorCode.invalid_reference,
            }
            for item in validated.issues
        ), fixture.fixture_id


def test_constant_acceleration_fixture_reaches_real_deterministic_solver():
    fixture = _fixtures()["constant_acceleration"]
    validated = validate_parse(fixture.problem_text, fixture.parse)
    canonical = project_canonical(fixture.problem_text, validated)
    registry = SolverRegistry()
    decision = registry.route(canonical)
    result = registry.select(canonical, decision=decision).solve(canonical)
    assert decision.selected_solver_id == "constant_acceleration_1d"
    assert result.ok
    assert result.answer.numeric == pytest.approx(2.0)


def test_prompt_examples_are_schema_derived_and_have_no_answer_authority():
    examples = generated_examples()
    assert len(examples) == 7
    encoded = json.dumps(examples, sort_keys=True)
    assert "raw_value" not in encoded
    assert "final_answer" not in encoded
    assert "solver_result" not in encoded
    prompt = load_prompt()
    assert "TextbookProblemParseWireV2" in prompt
    assert "constant_acceleration_1d" in prompt
    assert "point_on_body" in prompt


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_path"),
    [
        ("system_type", "uniform_acceleration", ("interpretation_candidates", 0, "system_type")),
        ("semantic_key", "speed", ("explicit_facts", 0, "semantic_key")),
    ],
)
def test_free_form_synonyms_fail_at_field_level(field, bad_value, expected_path):
    fixture = _fixtures()["constant_acceleration"]
    payload = fixture.parse.model_dump(mode="json")
    if field == "system_type":
        payload["interpretation_candidates"][0][field] = bad_value
    else:
        payload["explicit_facts"][0][field] = bad_value
    with pytest.raises(ValidationError) as caught:
        TextbookProblemParseWireV2.model_validate(payload)
    assert tuple(caught.value.errors()[0]["loc"]) == expected_path
    issues = _repair_issues_from_exception(caught.value, phase="initial_schema_parse")
    assert issues[0].path == ".".join(str(item) for item in expected_path)
    assert issues[0].code == ErrorCode.invalid_enum.value
    request = format_repair_request(fixture.problem_text, issues)
    assert issues[0].path in request[0]["content"]
    repaired = normalize_wire_parse(
        fixture.problem_text,
        TextbookProblemParseWireV2.model_validate(
            fixture.parse.model_dump(mode="json")
        ),
    )
    assert not _validation_repair_issues(validate_parse(fixture.problem_text, repaired))


def test_missing_query_subject_has_exact_schema_repair_path_and_full_repair_passes():
    fixture = _fixtures()["constant_acceleration"]
    payload = fixture.parse.model_dump(mode="json")
    del payload["queries"][0]["subject_id"]
    with pytest.raises(ValidationError) as caught:
        TextbookProblemParseWireV2.model_validate(payload)
    issues = _repair_issues_from_exception(caught.value, phase="initial_schema_parse")
    assert any(item.path == "queries.0.subject_id" for item in issues)
    repair_request = format_repair_request(fixture.problem_text, issues)
    assert "queries.0.subject_id" in repair_request[0]["content"]

    repaired = normalize_wire_parse(
        fixture.problem_text,
        TextbookProblemParseWireV2.model_validate(
            fixture.parse.model_dump(mode="json")
        ),
    )
    assert not _validation_repair_issues(validate_parse(fixture.problem_text, repaired))


def test_unique_occurrences_are_server_normalized_but_ambiguous_ones_require_repair():
    fixture = _fixtures()["constant_acceleration"]
    payload = fixture.parse.model_dump(mode="json")
    payload["explicit_facts"][0]["occurrence_index"] = None
    payload["explicit_facts"][0]["quantity_occurrence_index"] = None
    normalized = normalize_wire_parse(
        fixture.problem_text, TextbookProblemParseWireV2.model_validate(payload)
    )
    assert normalized.explicit_facts[0].occurrence_index == 0
    assert normalized.explicit_facts[0].quantity_occurrence_index == 0

    duplicated_text = fixture.problem_text + " The same marker is 16 m."
    with pytest.raises(WireNormalizationError) as caught:
        normalize_wire_parse(
            duplicated_text, TextbookProblemParseWireV2.model_validate(payload)
        )
    assert caught.value.issues[0].path == "explicit_facts.0.occurrence_index"


def test_ambiguous_quantity_occurrence_has_exact_repair_path_and_full_repair_passes():
    fixture = _fixtures()["constant_acceleration"]
    payload = fixture.parse.model_dump(mode="json")
    problem_text = fixture.problem_text + " Calibration reads 16 m then 16 m."
    payload["explicit_facts"][0]["evidence_quote"] = "16 m then 16 m"
    payload["explicit_facts"][0]["occurrence_index"] = 0
    payload["explicit_facts"][0]["quantity_occurrence_index"] = None
    with pytest.raises(WireNormalizationError) as caught:
        normalize_wire_parse(
            problem_text, TextbookProblemParseWireV2.model_validate(payload)
        )
    issues = caught.value.issues
    assert issues[0].code == ErrorCode.quantity_occurrence_missing.value
    assert issues[0].path == "explicit_facts.0.quantity_occurrence_index"
    assert issues[0].allowed_metadata == {"quantity_occurrence_count": 2}
    request = format_repair_request(problem_text, issues)
    assert issues[0].path in request[0]["content"]

    repaired = normalize_wire_parse(
        fixture.problem_text,
        TextbookProblemParseWireV2.model_validate(
            fixture.parse.model_dump(mode="json")
        ),
    )
    assert not _validation_repair_issues(validate_parse(fixture.problem_text, repaired))


def test_actor_query_policy_is_identical_for_rigid_point_and_aggregate_system():
    for fixture_id, subject in (
        ("fixed_axis_rigid_point", "point_p"),
        ("atwood_pulley", "system"),
    ):
        parse = _fixtures()[fixture_id].parse.model_copy(deep=True)
        parse.motion_segments[0].actor_ids.remove(subject)
        issues = validate_graph_contract(parse)
        assert any(
            item.path == "queries.0.subject_id"
            and item.metadata
            and item.metadata.get("subject_role") == "target_actor"
            for item in issues
        )


def test_collision_preimpact_start_boundary_resolves_to_initial_state():
    fixture = _fixtures()["collision_impulse"]
    validated = validate_parse(fixture.problem_text, fixture.parse)
    evaluation = validated.candidates[0]
    binding = next(
        item
        for item in evaluation.capability.binding.bindings
        if item.fact_id == "fact_velocity_before"
    )
    assert binding.symbol == "v0"


def test_adjacent_preimpact_boundary_import_is_graph_valid_and_resolves_to_initial_state():
    fixture = _fixtures()["collision_impulse"]
    parse = fixture.parse.model_copy(deep=True)
    target = parse.motion_segments[0]
    prior = target.model_copy(
        update={
            "segment_id": "pre_motion",
            "order": 1,
            "motion_model_candidates": [MotionModel.constant_velocity_1d],
            "start_event_id": None,
            "end_event_id": "collision_start",
            "relevance": SegmentRelevance.required_context,
        }
    )
    target.order = 2
    parse.motion_segments.insert(0, prior)
    velocity = next(
        item for item in parse.explicit_facts if item.fact_id == "fact_velocity_before"
    )
    velocity.segment_id = "pre_motion"

    assert validate_graph_contract(parse) == ()
    validated = validate_parse(fixture.problem_text, parse)
    evaluation = validated.candidates[0]
    binding = next(
        item
        for item in evaluation.capability.binding.bindings
        if item.fact_id == "fact_velocity_before"
    )
    assert binding.symbol == "v0"


def test_collision_postimpact_end_boundary_resolves_to_final_state():
    fixture = _fixtures()["collision_impulse"]
    before = next(
        item
        for item in fixture.parse.explicit_facts
        if item.fact_id == "fact_velocity_before"
    )
    after = before.model_copy(
        update={
            "fact_id": "fact_velocity_after",
            "semantic_key": ExplicitSemanticKey.velocity_after,
            "event_id": "collision_end",
            "temporal_role": TemporalRole.after_event,
        }
    )
    resolved = resolve_fact_symbol(
        fixture.parse,
        after,
        target_segment_ids={"motion"},
        role=None,
        role_count=1,
        system_type="impulse_momentum",
    )
    assert resolved.issue is None
    assert resolved.symbol == "vf"
    assert resolved.boundary_role == "final"


def test_safe_assumption_closure_attaches_omitted_rest_proposal_visibly():
    fixture = _fixtures()["constant_acceleration"]
    parse = fixture.parse.model_copy(deep=True)
    parse.interpretation_candidates[0].assumption_ids = []
    validated = validate_parse(fixture.problem_text, parse)
    assert validated.accepted
    evaluation = validated.candidates[0]
    assert evaluation.auto_attached_assumption_ids == ("assumption_rest",)
    assert "assumption_rest" in evaluation.effective_candidate.assumption_ids
    assert validated.to_summary()["candidate_evaluations"][0][
        "auto_attached_assumption_ids"
    ] == ["assumption_rest"]


def test_safe_assumption_closure_refuses_competing_same_symbol_proposals():
    fixture = _fixtures()["constant_acceleration"]
    parse = fixture.parse.model_copy(deep=True)
    parse.interpretation_candidates[0].assumption_ids = []
    parse.assumption_proposals.append(
        parse.assumption_proposals[0].model_copy(
            update={"assumption_id": "assumption_rest_competing"}
        )
    )
    validated = validate_parse(fixture.problem_text, parse)
    evaluation = validated.candidates[0]
    assert evaluation.auto_attached_assumption_ids == ()
    assert "v0" not in evaluation.capability.supplied_symbols
    assert not validated.accepted


def test_same_typed_graph_with_different_surrounding_raw_text_projects_identically():
    fixture = _fixtures()["constant_acceleration"]
    variant = "Repository-safe preface. " + fixture.problem_text
    first = validate_parse(fixture.problem_text, fixture.parse)
    second = validate_parse(variant, fixture.parse)
    first_canonical = project_canonical(fixture.problem_text, first)
    second_canonical = project_canonical(variant, second)
    assert first_canonical.system_type == second_canonical.system_type
    assert {
        key: (value.value, value.unit) for key, value in first_canonical.knowns.items()
    } == {
        key: (value.value, value.unit) for key, value in second_canonical.knowns.items()
    }


def test_mutation_corpus_emits_field_level_repair_issues_without_raw_payload():
    fixtures = _fixtures()
    mutations = []

    dangling = fixtures["constant_acceleration"].parse.model_copy(deep=True)
    dangling.interpretation_candidates[0].target_segment_ids = ["missing_segment"]
    mutations.append((fixtures["constant_acceleration"].problem_text, dangling, "interpretation_candidates.0.target_segment_ids.0", fixtures["constant_acceleration"].parse))

    missing_assumption_reference = fixtures["constant_acceleration"].parse.model_copy(deep=True)
    missing_assumption_reference.interpretation_candidates[0].assumption_ids = ["missing_assumption"]
    mutations.append((fixtures["constant_acceleration"].problem_text, missing_assumption_reference, "interpretation_candidates.0.assumption_ids.0", fixtures["constant_acceleration"].parse))

    query_not_actor = fixtures["fixed_axis_rigid_point"].parse.model_copy(deep=True)
    query_not_actor.motion_segments[0].actor_ids.remove("point_p")
    mutations.append((fixtures["fixed_axis_rigid_point"].problem_text, query_not_actor, "queries.0.subject_id", fixtures["fixed_axis_rigid_point"].parse))

    missing_relation = fixtures["atwood_pulley"].parse.model_copy(deep=True)
    missing_relation.relations = []
    mutations.append((fixtures["atwood_pulley"].problem_text, missing_relation, "interpretation_candidates.candidate_primary", fixtures["atwood_pulley"].parse))

    wrong_boundary = fixtures["collision_impulse"].parse.model_copy(deep=True)
    velocity = next(item for item in wrong_boundary.explicit_facts if item.fact_id == "fact_velocity_before")
    velocity.event_id = "collision_end"
    mutations.append((fixtures["collision_impulse"].problem_text, wrong_boundary, "explicit_facts.fact_velocity_before", fixtures["collision_impulse"].parse))

    missing_fact = fixtures["constant_acceleration"].parse.model_copy(deep=True)
    missing_fact.interpretation_candidates[0].fact_ids = ["fact_time"]
    mutations.append((fixtures["constant_acceleration"].problem_text, missing_fact, "interpretation_candidates.candidate_primary.fact_ids", fixtures["constant_acceleration"].parse))

    for problem_text, parse, expected_path, repaired_parse in mutations:
        validated = validate_parse(problem_text, parse)
        issues = _validation_repair_issues(validated)
        assert issues
        assert any(item.path == expected_path for item in issues)
        request = format_repair_request("SAFE ORIGINAL", issues)
        content = request[0]["content"]
        assert expected_path in content
        assert "raw model response" not in content.lower()
        assert "stack trace" not in content.lower()
        assert "SAFE ORIGINAL" in content
        assert not _validation_repair_issues(
            validate_parse(problem_text, repaired_parse)
        )


def test_one_quantity_span_cannot_ground_two_facts():
    fixture = _fixtures()["constant_acceleration"]
    parse = fixture.parse.model_copy(deep=True)
    duplicate = parse.explicit_facts[0].model_copy(update={"fact_id": "duplicate_fact"})
    parse.explicit_facts.append(duplicate)
    validated = validate_parse(fixture.problem_text, parse)
    assert any(
        item.code == ErrorCode.quantity_occurrence_reused
        for item in validated.issues
    )


def test_length_finish_reason_is_classified_without_exception_text():
    class LengthFinishReasonError(Exception):
        status_code = 200

    with pytest.raises(ParserIncompleteError) as caught:
        OpenAITextbookParserClient._raise_mapped(LengthFinishReasonError())
    assert caught.value.code == ErrorCode.parser_length_finish
    assert caught.value.incomplete_reason == "max_output_tokens"


def test_sdk_content_filter_exception_is_classified_as_nonrepairable_refusal():
    class ContentFilterRefusalError(Exception):
        status_code = 400

    with pytest.raises(ParserRefusalError):
        OpenAITextbookParserClient._raise_mapped(ContentFilterRefusalError())


def test_sdk_output_parsed_missing_and_incomplete_are_distinct_typed_categories():
    import threading
    from types import SimpleNamespace

    official = object.__new__(OpenAITextbookParserClient)
    official.config = _staged_config()
    official.api_key = "test-only"
    official._semaphore = threading.BoundedSemaphore(1)

    missing = SimpleNamespace(
        status="completed",
        incomplete_details=None,
        output=[],
        output_parsed=None,
        usage=None,
        id="missing-output",
    )
    official._client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **_kwargs: missing)
    )
    with pytest.raises(ParserOutputMissingError) as missing_error:
        official.parse("Repository-safe parser fixture.")
    assert missing_error.value.code == ErrorCode.parser_output_missing

    incomplete = SimpleNamespace(
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output=[],
        output_parsed=None,
        usage=None,
        id="incomplete-output",
    )
    official._client = SimpleNamespace(
        responses=SimpleNamespace(parse=lambda **_kwargs: incomplete)
    )
    with pytest.raises(ParserIncompleteError) as incomplete_error:
        official.parse("Repository-safe parser fixture.")
    assert incomplete_error.value.code == ErrorCode.parser_output_incomplete
    assert incomplete_error.value.incomplete_reason == "max_output_tokens"


@pytest.mark.parametrize(
    ("first_error", "expected_code"),
    [
        (ParserOutputMissingError("missing structured output"), ErrorCode.parser_output_missing),
        (ParserIncompleteError("incomplete structured output"), ErrorCode.parser_output_incomplete),
    ],
)
def test_output_category_gets_one_complete_repair_and_then_full_gate_passes(
    tmp_path, first_error, expected_code
):
    fixture = _fixtures()["constant_acceleration"]

    class OutputFailureThenFull:
        calls = 0

        def parse(
            self,
            problem_text,
            *,
            repair_error_codes=(),
            repair_issues=(),
        ):
            self.calls += 1
            if self.calls == 1:
                raise first_error
            assert repair_error_codes == (expected_code.value,)
            assert repair_issues[0].code == expected_code.value
            assert problem_text == fixture.problem_text
            return StructuredParseResponse(
                fixture.parse, UsageSummary(), "full-repair", usage_available=False
            )

    client = OutputFailureThenFull()
    outcome = parse_textbook_problem(
        fixture.problem_text,
        config=_staged_config(),
        client=client,
        cache=ParserCache(path=str(tmp_path / f"{expected_code.value}.sqlite3")),
    )
    assert outcome.status == ParseDecisionStatus.accepted_with_visible_assumptions
    assert outcome.request_attempt_count == 2
    assert outcome.retry_count == 1
    assert client.calls == 2
    assert not _validation_repair_issues(outcome.validated)


def test_output_missing_repair_failure_is_fail_closed_after_second_call(tmp_path):
    fixture = _fixtures()["constant_acceleration"]

    class AlwaysMissing:
        calls = 0

        def parse(self, problem_text, *, repair_error_codes=(), repair_issues=()):
            self.calls += 1
            raise ParserOutputMissingError("private output omitted")

    client = AlwaysMissing()
    outcome = parse_textbook_problem(
        fixture.problem_text,
        config=_staged_config(),
        client=client,
        cache=ParserCache(path=str(tmp_path / "always-missing.sqlite3")),
    )
    assert outcome.status == ParseDecisionStatus.parser_error
    assert outcome.failure_code == ErrorCode.repair_failed.value
    assert outcome.request_attempt_count == 2
    assert outcome.retry_count == 1
    assert client.calls == 2


def _offline_outcome(case) -> ParseOutcome:
    validated = validate_recorded_payload(case.problem_text, recorded_seed_payload(case))
    return ParseOutcome(
        status=validated.status,
        validated=validated,
        model="gpt-5.4-mini-2026-03-17",
        prompt_version="offline-test",
        usage=UsageSummary(),
        cache_hit=False,
        retry_count=0,
        request_attempt_count=1,
        problem_hash="offline",
        parser_latency_ms=0.0,
        validation_latency_ms=0.0,
        conservative_cost_upper_bound_usd=0.0,
    )


def _staged_config() -> TextbookParserConfig:
    return replace(
        TextbookParserConfig.from_env(),
        enabled=True,
        mode=ParserMode.required,
    )


def test_staged_runner_never_duplicates_targeted_requests():
    manifest = repository_safe_seed_manifest()
    by_text = {item.problem_text: item for item in manifest.cases}
    by_id = {item.case_id: item for item in manifest.cases}
    calls: list[str] = []

    def fake_parse(problem_text, **_kwargs):
        calls.append(problem_text)
        return _offline_outcome(by_text[problem_text])

    result = run_staged(config=_staged_config(), parse_case=fake_parse, emit=lambda _line: None)
    assert result.exit_code == 0
    assert len(result.outcomes) == 20
    assert len(result.predictions) == 20
    assert len(calls) <= 20
    assert len(set(calls)) == len(calls)
    assert all(calls.count(by_id[item].problem_text) == 1 for item in TARGETED_CASE_IDS)


def test_staged_runner_stops_after_eight_when_targeted_gate_fails():
    manifest = repository_safe_seed_manifest()
    by_text = {item.problem_text: item for item in manifest.cases}
    by_id = {item.case_id: item for item in manifest.cases}
    calls: list[str] = []

    def fake_parse(problem_text, **_kwargs):
        case = by_text[problem_text]
        calls.append(problem_text)
        outcome = _offline_outcome(case)
        if case.case_id == "figure_001":
            return replace(
                outcome,
                status=ParseDecisionStatus.parser_error,
                failure_code="forced_target_failure",
            )
        return outcome

    result = run_staged(config=_staged_config(), parse_case=fake_parse, emit=lambda _line: None)
    assert result.exit_code == 1
    assert not result.stage_1_passed
    assert calls == [by_id[item].problem_text for item in TARGETED_CASE_IDS]
