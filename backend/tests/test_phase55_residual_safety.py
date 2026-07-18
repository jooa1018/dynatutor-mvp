from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from engine.solvers.kinematics import ConstantAcceleration1DSolver
from engine.textbook_parser.cache import ParserCache
from engine.textbook_parser.bindings import evaluate_candidate_bindings
from engine.textbook_parser.canonical_projection import project_canonical
from engine.textbook_parser.config import ParserMode, TextbookParserConfig
from engine.textbook_parser.contracts import ExplicitFact, TextbookProblemParseV1
from engine.textbook_parser.corrections import apply_parse_corrections
from engine.textbook_parser.errors import ErrorCode
from engine.textbook_parser.evidence_alignment import align_explicit_fact
from engine.textbook_parser.gateway import parse_problem_gateway
from engine.textbook_parser.openai_client import StructuredParseResponse
from engine.textbook_parser.telemetry import UsageSummary
from engine.textbook_parser.temporal_bindings import resolve_fact_symbol
from engine.textbook_parser.validation import ParseDecisionStatus, validate_parse


FIXTURE = Path(__file__).parent / "fixtures" / "phase55" / "athlete_recorded_parse.json"


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _config(mode: ParserMode) -> TextbookParserConfig:
    return TextbookParserConfig(
        enabled=True,
        mode=mode,
        model="gpt-5.4-mini-2026-03-17",
        reasoning_effort="low",
        max_retries=1,
        timeout_seconds=20.0,
        store=False,
        max_output_tokens=1800,
        max_problem_chars=12000,
        max_inflight=8,
        cache_path=None,
        cache_ttl_seconds=604800,
        cache_l1_entries=16,
        cache_l2_entries=32,
    )


class _RecordedClient:
    def __init__(self, parsed):
        self.parsed = parsed

    def parse(self, problem_text, *, repair_error_codes=()):
        return StructuredParseResponse(
            self.parsed,
            UsageSummary(input_tokens=10, output_tokens=10),
            "recorded-residual-safety",
        )


def _explicit_fact(**updates) -> ExplicitFact:
    payload = deepcopy(_fixture()["parse"]["explicit_facts"][1])
    payload.update(
        {
            "fact_id": "tested_fact",
            "subject_id": "athlete",
            "segment_id": "segment_1",
            "event_id": None,
            "temporal_role": "interval",
            "direction": "not_applicable",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
            **updates,
        }
    )
    return ExplicitFact.model_validate(payload)


@pytest.mark.parametrize(
    ("semantic_key", "raw_value", "raw_unit", "passes"),
    [
        ("distance", "35", "m", True),
        ("time", "5.4", "초", True),
        ("distance", "5.4", "m", False),
        ("time", "35", "초", False),
    ],
)
def test_quantity_span_rejects_value_unit_swaps(semantic_key, raw_value, raw_unit, passes):
    text = "35m를 5.4초 동안 이동했다."
    fact = _explicit_fact(
        semantic_key=semantic_key,
        raw_value=raw_value,
        raw_unit=raw_unit,
        evidence_quote=text,
    )
    span, issues = align_explicit_fact(text, fact)
    assert (span is not None) is passes
    assert any(item.code == ErrorCode.quantity_span_mismatch for item in issues) is (not passes)


@pytest.mark.parametrize(
    ("text", "semantic_key", "raw_value", "raw_unit"),
    [
        ("질량 2kg인 물체가 5m 이동했다.", "mass", "5", "kg"),
        ("질량 2kg인 물체가 5m 이동했다.", "distance", "2", "m"),
        ("속력은 5m/s이고 시간은 3s이다.", "velocity", "3", "m/s"),
        ("속력은 5m/s이고 시간은 3s이다.", "time", "5", "s"),
    ],
)
def test_quantity_span_rejects_cross_quantity_and_compound_unit_swaps(
    text, semantic_key, raw_value, raw_unit
):
    fact = _explicit_fact(
        semantic_key=semantic_key,
        raw_value=raw_value,
        raw_unit=raw_unit,
        evidence_quote=text,
    )
    span, issues = align_explicit_fact(text, fact)
    assert span is None
    assert ErrorCode.quantity_span_mismatch in {item.code for item in issues}


def test_quantity_grammar_supports_scientific_superscript_and_explicit_dimensionless():
    force = _explicit_fact(
        semantic_key="force",
        raw_value="2.5×10³",
        raw_unit="N",
        evidence_quote="힘은 2.5×10³ N이다.",
    )
    dimensionless = _explicit_fact(
        semantic_key="coefficient_of_friction",
        raw_value="0.25",
        raw_unit="",
        evidence_quote="마찰계수는 0.25이다.",
    )
    percent = _explicit_fact(
        semantic_key="coefficient_of_friction",
        raw_value="30",
        raw_unit="%",
        evidence_quote="비율은 30%이다.",
    )
    velocity_after = _explicit_fact(
        semantic_key="velocity_after",
        raw_value="3",
        raw_unit="m/s",
        evidence_quote="직후 속력은 3m/s이다.",
    )
    for text, fact in [
        ("힘은 2.5×10³ N이다.", force),
        ("마찰계수는 0.25이다.", dimensionless),
        ("비율은 30%이다.", percent),
        ("직후 속력은 3m/s이다.", velocity_after),
    ]:
        span, issues = align_explicit_fact(text, fact)
        assert span is not None
        assert not issues


def test_value_and_unit_expressed_as_separate_clauses_are_not_auto_paired():
    text = "값은 5이고, 단위는 m이다."
    fact = _explicit_fact(
        semantic_key="distance",
        raw_value="5",
        raw_unit="m",
        evidence_quote=text,
    )
    span, issues = align_explicit_fact(text, fact)
    assert span is None
    assert ErrorCode.quantity_span_mismatch in {item.code for item in issues}


def _repeated_quantity_parse(second_occurrence: int) -> tuple[str, TextbookProblemParseV1]:
    fixture = _fixture()
    sentence = "물체 A와 B의 질량은 각각 2kg과 2kg이다."
    fixture["problem_text"] = sentence + "\n" + fixture["problem_text"]
    parse = fixture["parse"]
    parse["entities"].extend(
        [
            {"entity_id": "cart_a", "kind": "particle", "label": "A", "aliases": [], "evidence_quote": "A"},
            {"entity_id": "cart_b", "kind": "particle", "label": "B", "aliases": [], "evidence_quote": "B"},
        ]
    )
    template = deepcopy(parse["explicit_facts"][1])
    added = []
    for fact_id, subject_id, quantity_index in [
        ("mass_a", "cart_a", 0),
        ("mass_b", "cart_b", second_occurrence),
    ]:
        fact = deepcopy(template)
        fact.update(
            {
                "fact_id": fact_id,
                "semantic_key": "mass",
                "raw_value": "2",
                "raw_unit": "kg",
                "subject_id": subject_id,
                "segment_id": None,
                "event_id": None,
                "temporal_role": "timeless",
                "direction": "not_applicable",
                "evidence_quote": sentence,
                "occurrence_index": 0,
                "quantity_occurrence_index": quantity_index,
                "relevance": "context_only",
            }
        )
        added.append(fact)
    parse["explicit_facts"].extend(added)
    return fixture["problem_text"], TextbookProblemParseV1.model_validate(parse)


def test_repeated_equal_quantities_require_distinct_source_occurrences():
    text, distinct = _repeated_quantity_parse(1)
    accepted = validate_parse(text, distinct)
    assert accepted.status == ParseDecisionStatus.accepted_with_visible_assumptions
    spans = accepted.evidence.fact_spans
    assert (spans["mass_a"].start, spans["mass_a"].end) != (
        spans["mass_b"].start,
        spans["mass_b"].end,
    )

    text, reused = _repeated_quantity_parse(0)
    blocked = validate_parse(text, reused)
    assert blocked.status == ParseDecisionStatus.needs_confirmation
    assert ErrorCode.quantity_occurrence_reused in {item.code for item in blocked.issues}
    with pytest.raises(ValueError, match="cannot project non-accepted parse"):
        project_canonical(text, blocked)


def _velocity_parse(
    temporal_role: str,
    event_id: str | None,
    *,
    event_kind: str | None = None,
    non_boundary: bool = False,
) -> tuple[str, TextbookProblemParseV1]:
    fixture = _fixture()
    sentence = "속력은 5m/s이다."
    fixture["problem_text"] = sentence + "\n" + fixture["problem_text"]
    parse = fixture["parse"]
    if non_boundary:
        parse["events"].append(
            {
                "event_id": "middle_event",
                "kind": event_kind or "collision_start",
                "subject_ids": ["athlete"],
                "segment_id": "segment_1",
                "evidence_quote": "속력",
            }
        )
        event_id = "middle_event"
    elif event_id is not None and event_kind is not None:
        next(item for item in parse["events"] if item["event_id"] == event_id)["kind"] = event_kind
    fact = deepcopy(parse["explicit_facts"][1])
    fact.update(
        {
            "fact_id": "velocity_edge",
            "semantic_key": "velocity",
            "raw_value": "5",
            "raw_unit": "m/s",
            "event_id": event_id,
            "temporal_role": temporal_role,
            "direction": "along_motion",
            "evidence_quote": "5m/s",
            "occurrence_index": 0,
            "quantity_occurrence_index": 0,
        }
    )
    parse["explicit_facts"].append(fact)
    parse["interpretation_candidates"][0]["fact_ids"].append("velocity_edge")
    return fixture["problem_text"], TextbookProblemParseV1.model_validate(parse)


@pytest.mark.parametrize(
    ("temporal_role", "event_id", "event_kind", "expected_symbol"),
    [
        ("before_event", "acceleration_end", "collision_start", "vf"),
        ("after_event", "race_start", "collision_end", "v0"),
        ("initial", "race_start", "start", "v0"),
        ("final", "acceleration_end", "reaches_position", "vf"),
    ],
)
def test_event_boundary_velocity_resolver_uses_segment_boundary(
    temporal_role, event_id, event_kind, expected_symbol
):
    _, parse = _velocity_parse(temporal_role, event_id, event_kind=event_kind)
    report = evaluate_candidate_bindings(parse, parse.interpretation_candidates[0])
    binding = next(item for item in report.bindings if item.fact_id == "velocity_edge")
    assert binding.symbol == expected_symbol
    if temporal_role == "before_event":
        assert binding.symbol != "v0"
    if temporal_role == "after_event":
        assert binding.symbol != "vf"


def test_event_relative_velocity_without_event_is_schema_error():
    with pytest.raises(ValidationError, match="requires event_id"):
        _velocity_parse("before_event", None)


def test_non_boundary_event_velocity_abstains_and_never_supplies_capability_input():
    text, parse = _velocity_parse(
        "before_event", "middle_event", event_kind="collision_start", non_boundary=True
    )
    validated = validate_parse(text, parse)
    assert validated.status == ParseDecisionStatus.needs_confirmation
    capability = validated.candidates[0].capability
    assert all(item.fact_id != "velocity_edge" for item in capability.binding.bindings)
    assert ErrorCode.temporal_binding_ambiguous in {
        item.code for item in capability.binding.issues
    }


def test_event_boundary_projection_and_solver_are_raw_text_invariant():
    text, parse = _velocity_parse("final", "acceleration_end", event_kind="reaches_position")
    parse_payload = parse.model_dump(mode="json")
    parse_payload["interpretation_candidates"][0]["fact_ids"] = ["segment_time", "velocity_edge"]
    parse = TextbookProblemParseV1.model_validate(parse_payload)
    alternate_text = "표현만 다른 비물리 머리말이다.\n" + text
    first = validate_parse(text, parse)
    second = validate_parse(alternate_text, parse)
    assert first.accepted and second.accepted
    first_canonical = project_canonical(text, first)
    second_canonical = project_canonical(alternate_text, second)
    assert {
        key: (item.value, item.unit) for key, item in first_canonical.knowns.items()
    } == {
        key: (item.value, item.unit) for key, item in second_canonical.knowns.items()
    }
    first_result = ConstantAcceleration1DSolver().solve(first_canonical)
    second_result = ConstantAcceleration1DSolver().solve(second_canonical)
    assert first_result.ok and second_result.ok
    assert math.isclose(first_result.answer.numeric, second_result.answer.numeric)


def test_collision_before_after_speeds_do_not_cross_pre_and_post_segment_endpoints():
    fixture = _fixture()
    sentence = "충돌 직전 속력은 5m/s이고 충돌 직후 속력은 3m/s이다."
    fixture["problem_text"] = sentence + "\n" + fixture["problem_text"]
    parse = fixture["parse"]
    next(item for item in parse["events"] if item["event_id"] == "acceleration_end")["kind"] = "collision_start"
    parse["events"].append(
        {
            "event_id": "collision_end",
            "kind": "collision_end",
            "subject_ids": ["athlete"],
            "segment_id": "segment_2",
            "evidence_quote": "충돌 직후",
        }
    )
    parse["motion_segments"][1]["start_event_id"] = "collision_end"
    template = parse["explicit_facts"][1]
    before = deepcopy(template)
    before.update(
        {
            "fact_id": "pre_collision_speed",
            "semantic_key": "velocity",
            "raw_value": "5",
            "raw_unit": "m/s",
            "segment_id": "segment_1",
            "event_id": "acceleration_end",
            "temporal_role": "before_event",
            "evidence_quote": "5m/s",
            "quantity_occurrence_index": 0,
        }
    )
    after = deepcopy(template)
    after.update(
        {
            "fact_id": "post_collision_speed",
            "semantic_key": "velocity",
            "raw_value": "3",
            "raw_unit": "m/s",
            "segment_id": "segment_2",
            "event_id": "collision_end",
            "temporal_role": "after_event",
            "evidence_quote": "3m/s",
            "quantity_occurrence_index": 0,
            "relevance": "context_only",
        }
    )
    parse["explicit_facts"].extend([before, after])
    typed = TextbookProblemParseV1.model_validate(parse)
    before_resolution = resolve_fact_symbol(
        typed,
        next(item for item in typed.explicit_facts if item.fact_id == "pre_collision_speed"),
        target_segment_ids={"segment_1"},
        role=1,
        role_count=1,
    )
    after_resolution = resolve_fact_symbol(
        typed,
        next(item for item in typed.explicit_facts if item.fact_id == "post_collision_speed"),
        target_segment_ids={"segment_2"},
        role=1,
        role_count=1,
    )
    assert before_resolution.symbol == "vf"
    assert after_resolution.symbol == "v0"


def _collision_binding_parse() -> TextbookProblemParseV1:
    parse = _fixture()["parse"]
    parse["entities"].append(
        {
            "entity_id": "cart_b",
            "kind": "particle",
            "label": "수레 B",
            "aliases": [],
            "evidence_quote": "육상 선수",
        }
    )
    parse["motion_segments"][0]["actor_ids"].append("cart_b")
    parse["motion_segments"][0]["motion_model_candidates"] = ["impulse_interval"]
    parse["events"][0]["kind"] = "collision_end"
    parse["events"][0]["subject_ids"].append("cart_b")
    parse["relations"] = [
        {
            "relation_id": "collision_pair",
            "kind": "collides_with",
            "entity_ids": ["athlete", "cart_b"],
            "segment_id": "segment_1",
            "evidence_quote": "육상 선수",
        },
        {
            "relation_id": "contact_pair",
            "kind": "contact_with",
            "entity_ids": ["athlete", "cart_b"],
            "segment_id": "segment_1",
            "evidence_quote": "육상 선수",
        },
    ]
    template = parse["explicit_facts"][1]
    facts = []
    for fact_id, semantic_key, subject_id, temporal_role, event_id in [
        ("mass_a", "mass", "athlete", "timeless", None),
        ("mass_b", "mass", "cart_b", "timeless", None),
        ("velocity_a", "velocity", "athlete", "after_event", "race_start"),
        ("velocity_b", "velocity", "cart_b", "after_event", "race_start"),
    ]:
        fact = deepcopy(template)
        fact.update(
            {
                "fact_id": fact_id,
                "semantic_key": semantic_key,
                "subject_id": subject_id,
                "temporal_role": temporal_role,
                "event_id": event_id,
            }
        )
        facts.append(fact)
    parse["explicit_facts"] = facts
    candidate = parse["interpretation_candidates"][0]
    candidate.update(
        {
            "system_type": "impulse_momentum",
            "fact_ids": [item["fact_id"] for item in facts],
            "assumption_ids": [],
        }
    )
    return TextbookProblemParseV1.model_validate(parse)


def _symbols_by_subject(parse: TextbookProblemParseV1) -> dict[str, str]:
    report = evaluate_candidate_bindings(parse, parse.interpretation_candidates[0])
    assert not report.issues
    return {f"{item.subject_id}:{item.fact_id.split('_')[0]}": item.symbol for item in report.bindings}


def test_binding_roles_ignore_entity_relation_fact_array_order_and_relation_participant_order():
    baseline = _collision_binding_parse()
    expected = _symbols_by_subject(baseline)
    payload = baseline.model_dump(mode="json")
    payload["entities"].reverse()
    payload["relations"].reverse()
    for relation in payload["relations"]:
        relation["entity_ids"].reverse()
    payload["explicit_facts"].reverse()
    payload["interpretation_candidates"][0]["fact_ids"].reverse()
    assert _symbols_by_subject(TextbookProblemParseV1.model_validate(payload)) == expected


def test_binding_roles_are_id_rename_invariant():
    baseline = _collision_binding_parse()
    expected_values = sorted(_symbols_by_subject(baseline).values())
    replacements = {
        "athlete": "body_x",
        "cart_b": "body_y",
        "segment_1": "phase_x",
        "segment_2": "phase_y",
        "race_start": "event_x",
        "acceleration_end": "event_y",
        "collision_pair": "relation_x",
        "contact_pair": "relation_y",
        "mass_a": "fact_ma",
        "mass_b": "fact_mb",
        "velocity_a": "fact_va",
        "velocity_b": "fact_vb",
        "query_acceleration": "query_x",
        "constant_acceleration_target": "candidate_x",
    }

    def rename(value):
        if isinstance(value, str):
            return replacements.get(value, value)
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, dict):
            return {key: rename(item) for key, item in value.items()}
        return value

    renamed = TextbookProblemParseV1.model_validate(rename(baseline.model_dump(mode="json")))
    assert sorted(item.symbol for item in evaluate_candidate_bindings(
        renamed, renamed.interpretation_candidates[0]
    ).bindings) == expected_values


def test_irrelevant_relation_entity_does_not_turn_single_body_candidate_into_multi_body():
    fixture = _fixture()
    parse = fixture["parse"]
    parse["entities"].append(
        {"entity_id": "spectator", "kind": "person", "label": "관중", "aliases": [], "evidence_quote": "100m"}
    )
    parse["relations"].append(
        {
            "relation_id": "irrelevant_contact",
            "kind": "contact_with",
            "entity_ids": ["athlete", "spectator"],
            "segment_id": "segment_1",
            "evidence_quote": "100m",
        }
    )
    typed = TextbookProblemParseV1.model_validate(parse)
    report = evaluate_candidate_bindings(typed, typed.interpretation_candidates[0])
    assert {item.symbol for item in report.bindings} == {"s", "t"}
    assert report.relation_ids == ()


def _system_query_component_parse(include_relation: bool) -> TextbookProblemParseV1:
    parse = _fixture()["parse"]
    parse["entities"].extend(
        [
            {"entity_id": "cart_a", "kind": "particle", "label": "A", "aliases": [], "evidence_quote": "육상 선수"},
            {"entity_id": "cart_b", "kind": "particle", "label": "B", "aliases": [], "evidence_quote": "육상 선수"},
        ]
    )
    parse["motion_segments"][0]["actor_ids"].extend(["cart_a", "cart_b"])
    parse["relations"] = (
        [
            {
                "relation_id": "rope_pair",
                "kind": "connected_by_rope",
                "entity_ids": ["cart_b", "cart_a"],
                "segment_id": "segment_1",
                "evidence_quote": "육상 선수",
            }
        ]
        if include_relation
        else []
    )
    template = parse["explicit_facts"][1]
    facts = []
    for fact_id, semantic_key, subject_id in [
        ("mass_a", "mass_1", "cart_a"),
        ("mass_b", "mass_2", "cart_b"),
    ]:
        fact = deepcopy(template)
        fact.update(
            {
                "fact_id": fact_id,
                "semantic_key": semantic_key,
                "subject_id": subject_id,
                "event_id": None,
                "temporal_role": "timeless",
                "direction": "not_applicable",
            }
        )
        facts.append(fact)
    parse["explicit_facts"] = facts
    parse["interpretation_candidates"][0].update(
        {
            "system_type": "pulley_atwood",
            "fact_ids": ["mass_a", "mass_b"],
            "assumption_ids": [],
        }
    )
    return TextbookProblemParseV1.model_validate(parse)


def test_system_query_can_use_component_facts_only_through_explicit_allowed_relation():
    related = _system_query_component_parse(True)
    report = evaluate_candidate_bindings(related, related.interpretation_candidates[0])
    assert not report.issues
    assert {item.symbol for item in report.bindings} == {"m1", "m2"}

    with_system_assumption = related.model_dump(mode="json")
    with_system_assumption["interpretation_candidates"][0]["assumption_ids"] = [
        "starts_at_rest"
    ]
    typed_with_assumption = TextbookProblemParseV1.model_validate(with_system_assumption)
    assumption_report = evaluate_candidate_bindings(
        typed_with_assumption, typed_with_assumption.interpretation_candidates[0]
    )
    assert not assumption_report.issues

    unrelated = _system_query_component_parse(False)
    blocked = evaluate_candidate_bindings(unrelated, unrelated.interpretation_candidates[0])
    assert ErrorCode.relation_binding_missing in {item.code for item in blocked.issues}
    assert ErrorCode.candidate_binding_mismatch in {item.code for item in blocked.issues}


def test_relation_presence_alone_does_not_assign_symmetric_multi_body_roles():
    payload = _system_query_component_parse(True).model_dump(mode="json")
    for fact in payload["explicit_facts"]:
        fact["semantic_key"] = "mass"
    parse = TextbookProblemParseV1.model_validate(payload)
    report = evaluate_candidate_bindings(parse, parse.interpretation_candidates[0])
    assert ErrorCode.relation_binding_missing in {item.code for item in report.issues}
    assert report.bindings == ()

    payload["entities"].reverse()
    payload["relations"].reverse()
    payload["relations"][0]["entity_ids"].reverse()
    payload["explicit_facts"].reverse()
    payload["interpretation_candidates"][0]["fact_ids"].reverse()
    permuted = TextbookProblemParseV1.model_validate(payload)
    permuted_report = evaluate_candidate_bindings(
        permuted, permuted.interpretation_candidates[0]
    )
    assert permuted_report.bindings == ()
    assert {item.code for item in permuted_report.issues} == {
        item.code for item in report.issues
    }


def test_context_fact_never_enters_capability_symbols_even_if_candidate_references_it():
    fixture = _fixture()
    fixture["parse"]["interpretation_candidates"][0]["fact_ids"].append("race_distance")
    parse = TextbookProblemParseV1.model_validate(fixture["parse"])
    report = evaluate_candidate_bindings(parse, parse.interpretation_candidates[0])
    assert all(item.fact_id != "race_distance" for item in report.bindings)
    assert ErrorCode.candidate_binding_mismatch in {item.code for item in report.issues}


def test_cache_key_invalidates_quantity_schema_and_temporal_policy_revisions(monkeypatch):
    import engine.textbook_parser.cache as cache_module

    problem = "물체가 5m 이동했다."
    model = "recorded-model"
    baseline = cache_module.build_cache_key(problem, model)
    original_temporal = cache_module.TEMPORAL_BINDING_POLICY_VERSION
    monkeypatch.setattr(
        cache_module,
        "TEMPORAL_BINDING_POLICY_VERSION",
        original_temporal + "-audit",
    )
    assert cache_module.build_cache_key(problem, model) != baseline
    monkeypatch.setattr(
        cache_module, "TEMPORAL_BINDING_POLICY_VERSION", original_temporal
    )
    monkeypatch.setattr(cache_module, "SCHEMA_VERSION", "1.1-audit")
    assert cache_module.build_cache_key(problem, model) != baseline


def test_cumulative_correction_round_trip_and_stale_revision_block(tmp_path):
    fixture = _fixture()
    parsed = TextbookProblemParseV1.model_validate(fixture["parse"])
    cumulative = {
        "operations": [
            {"collection": "queries", "id": "query_acceleration", "set": {"component": "x"}},
            {"collection": "entities", "id": "athlete", "set": {"label": "단거리 선수"}},
        ]
    }
    cache = ParserCache(path=str(tmp_path / "cumulative.sqlite3"))
    first = parse_problem_gateway(
        fixture["problem_text"],
        config=_config(ParserMode.confirm),
        client=_RecordedClient(parsed),
        cache=cache,
        parse_correction=cumulative,
    )
    assert first.blocked and first.approval_fingerprint
    approved = parse_problem_gateway(
        fixture["problem_text"],
        config=_config(ParserMode.confirm),
        client=_RecordedClient(parsed),
        cache=cache,
        approved_fingerprint=first.approval_fingerprint,
        parse_correction=cumulative,
    )
    graph = approved.canonical.textbook_parse["graph"]
    assert graph["queries"][0]["component"] == "x"
    assert graph["entities"][0]["label"] == "단거리 선수"

    changed = deepcopy(cumulative)
    changed["operations"][1]["set"]["label"] = "다른 선수"
    stale = parse_problem_gateway(
        fixture["problem_text"],
        config=_config(ParserMode.confirm),
        client=_RecordedClient(parsed),
        cache=cache,
        approved_fingerprint=first.approval_fingerprint,
        parse_correction=changed,
    )
    assert stale.blocked

    last_wins = apply_parse_corrections(
        parsed,
        {
            "operations": [
                {"collection": "entities", "id": "athlete", "set": {"label": "첫 이름"}},
                {"collection": "entities", "id": "athlete", "set": {"label": "마지막 이름"}},
            ]
        },
    )
    assert last_wins.entities[0].label == "마지막 이름"


def test_blocked_diagnose_api_is_neutral_and_never_constructs_registry(monkeypatch, tmp_path):
    fixture = _fixture()
    parsed = TextbookProblemParseV1.model_validate(fixture["parse"])
    blocked = parse_problem_gateway(
        fixture["problem_text"],
        config=_config(ParserMode.confirm),
        client=_RecordedClient(parsed),
        cache=ParserCache(path=str(tmp_path / "diagnose.sqlite3")),
    )
    assert blocked.blocked
    monkeypatch.setattr("engine.services.parse_problem_gateway", lambda *args, **kwargs: blocked)

    class ForbiddenRegistry:
        def __init__(self, *args, **kwargs):
            raise AssertionError("registry must not be created for blocked diagnose")

    monkeypatch.setattr("engine.services.SolverRegistry", ForbiddenRegistry)
    response = TestClient(app).post(
        "/diagnose", json={"problem_text": fixture["problem_text"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected_solver"] is None
    assert body["solver_reason"] is None
    assert body["route_decision"] is None
    assert body["fbd_diagram_svg"] is None
    assert body["fbd_annotations"] == []
    assert body["fbd"] == []
    assert body["applicable_equations"] == []
    assert body["physical_model"] is None
    assert body["textbook_parse"]["requires_approval"] is True
