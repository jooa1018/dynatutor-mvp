from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import inspect

from engine.mechanics.errors import MechanicsIssueCode
import engine.mechanics.phase55_adapter as adapter
from engine.mechanics.phase55_adapter import adapt_validated_phase55
from engine.mechanics.validation import ValidationTerminal
from engine.textbook_parser.contracts import TextbookProblemParseV1
from engine.textbook_parser.errors import ErrorCode, Severity, ValidationIssue
from engine.textbook_parser.validation import validate_parse


_TEXT = (
    "A particle has initial velocity 1 m/s, acceleration 2 m/s^2, "
    "and moves for 3 s. Find its final velocity."
)


def _parse_payload(*, identifier_suffix: str = "") -> dict[str, object]:
    suffix = identifier_suffix
    return {
        "schema": "dynatutor.textbook_parse",
        "version": "2.0",
        "language": "en",
        "parse_status": "complete",
        "entities": [{"entity_id": f"body{suffix}", "kind": "particle", "label": "particle"}],
        "motion_segments": [{
            "segment_id": f"seg{suffix}", "order": 1, "actor_ids": [f"body{suffix}"],
            "motion_model_candidates": ["constant_acceleration_1d"], "relevance": "target",
        }],
        "events": [], "relations": [],
        "explicit_facts": [
            {
                "fact_id": f"fact_v0{suffix}", "kind": "scalar",
                "semantic_key": "initial_velocity", "raw_value": "1", "raw_unit": "m/s",
                "subject_id": f"body{suffix}", "segment_id": f"seg{suffix}",
                "temporal_role": "initial", "direction": "unspecified",
                "evidence_quote": "initial velocity 1 m/s", "relevance": "solver_input",
                "occurrence_index": 0, "quantity_occurrence_index": 0,
            },
            {
                "fact_id": f"fact_a{suffix}", "kind": "scalar",
                "semantic_key": "acceleration", "raw_value": "2", "raw_unit": "m/s^2",
                "subject_id": f"body{suffix}", "segment_id": f"seg{suffix}",
                "temporal_role": "during", "direction": "unspecified",
                "evidence_quote": "acceleration 2 m/s^2", "relevance": "solver_input",
                "occurrence_index": 0, "quantity_occurrence_index": 0,
            },
            {
                "fact_id": f"fact_t{suffix}", "kind": "scalar", "semantic_key": "duration",
                "raw_value": "3", "raw_unit": "s", "subject_id": f"body{suffix}",
                "segment_id": f"seg{suffix}", "temporal_role": "interval",
                "direction": "not_applicable", "evidence_quote": "for 3 s",
                "relevance": "solver_input", "occurrence_index": 0,
                "quantity_occurrence_index": 0,
            },
        ],
        "queries": [{
            "query_id": f"query{suffix}", "output_key": "final_velocity", "subject_id": f"body{suffix}",
            "segment_id": f"seg{suffix}", "component": "unspecified",
        }],
        "assumption_proposals": [],
        "interpretation_candidates": [{
            "candidate_id": f"candidate{suffix}", "system_type": "constant_acceleration_1d",
            "target_segment_ids": [f"seg{suffix}"],
            "fact_ids": [f"fact_v0{suffix}", f"fact_a{suffix}", f"fact_t{suffix}"],
            "query_ids": [f"query{suffix}"], "reason_code": "explicit_kinematics",
        }],
        "ambiguities": [],
        "figure_dependency": {"level": "none"},
        "unsupported_features": [],
    }


def _validated():
    parsed = TextbookProblemParseV1.model_validate(_parse_payload())
    validated = validate_parse(_TEXT, parsed)
    assert validated.accepted
    return validated


def _validated_with_gravity():
    payload = _parse_payload()
    payload["assumption_proposals"] = [{
        "assumption_id": "gravity_default", "kind": "constant_gravity",
        "subject_id": "body", "segment_id": "seg",
        "proposed_semantic_key": "acceleration", "proposed_value": "9.81",
        "proposed_unit": "m/s^2", "reason": "Use the server gravity policy.",
    }]
    payload["interpretation_candidates"][0]["assumption_ids"] = ["gravity_default"]
    validated = validate_parse(_TEXT, TextbookProblemParseV1.model_validate(payload))
    assert validated.accepted
    return validated


def test_accepted_parse_maps_exact_evidence_without_invented_mechanics():
    result = adapt_validated_phase55(_TEXT, _validated())

    assert result.terminal is ValidationTerminal.accepted
    assert result.draft is not None
    draft = result.draft
    assert len(draft.source_evidence) == len(draft.quantities) == 3
    evidence = next(
        item for item in draft.source_evidence
        if item.quote == "acceleration 2 m/s^2"
    )
    assert evidence.quote == "acceleration 2 m/s^2"
    assert _TEXT[evidence.source_span.start:evidence.source_span.end] == evidence.quote
    assert _TEXT[evidence.quantity_span.start:evidence.quantity_span.end] == "2 m/s^2"
    assert draft.metadata.language.value == "en"
    assert draft.entities[0].primitive.value == "particle"
    assert draft.motion_intervals and draft.queries
    assert not draft.reference_frames and not draft.points and not draft.constraints
    assert not draft.state_conditions and not draft.principle_hints


def test_raw_or_nonaccepted_phase55_inputs_are_rejected():
    parsed = TextbookProblemParseV1.model_validate(_parse_payload())
    raw = adapt_validated_phase55(_TEXT, parsed)  # type: ignore[arg-type]
    assert raw.terminal is ValidationTerminal.invalid
    assert raw.issues[0].code is MechanicsIssueCode.phase55_validation_required

    invalid = replace(_validated(), status=type(_validated().status).needs_confirmation)
    blocked = adapt_validated_phase55(_TEXT, invalid)
    assert blocked.terminal is ValidationTerminal.invalid
    assert blocked.issues[0].code is MechanicsIssueCode.phase55_validation_required


def test_mutated_fact_or_authoritative_span_fails_closed():
    mutated = deepcopy(_validated())
    mutated.parse.explicit_facts[0].raw_value = "3"
    result = adapt_validated_phase55(_TEXT, mutated)
    assert result.terminal is ValidationTerminal.invalid
    assert result.issues[0].code is MechanicsIssueCode.phase55_validation_required

    bad_span = deepcopy(_validated())
    span = bad_span.evidence.fact_spans["fact_a"]
    bad_span.evidence.fact_spans["fact_a"] = type(span)(span.start, span.end - 1, span.quote)
    result = adapt_validated_phase55(_TEXT, bad_span)
    assert result.terminal is ValidationTerminal.invalid


def test_forged_query_candidate_assumption_and_issue_authority_is_rejected():
    query = deepcopy(_validated())
    query.parse.queries[0].output_key = type(query.parse.queries[0].output_key).time
    query_result = adapt_validated_phase55(_TEXT, query)
    # A semantically valid mutation may be recovered only through the fresh
    # validator; it must never retain the stale final-velocity calculation.
    assert (
        not query_result.accepted
        or query_result.draft.queries[0].target.role.value == "time"
    )

    candidate = deepcopy(_validated())
    candidate.candidates[0].effective_candidate.fact_ids.pop()
    assert adapt_validated_phase55(_TEXT, candidate).terminal is ValidationTerminal.invalid

    assumptions = _validated_with_gravity()
    forged_evaluation = replace(assumptions.assumptions[0], resolved_value="7")
    forged = replace(assumptions, assumptions=(forged_evaluation,))
    assert adapt_validated_phase55(_TEXT, forged).terminal is ValidationTerminal.invalid

    issue = ValidationIssue(
        ErrorCode.raw_value_mismatch, Severity.error, "forged issue"
    )
    forged_issues = replace(_validated(), issues=(issue,))
    assert adapt_validated_phase55(_TEXT, forged_issues).terminal is ValidationTerminal.invalid


def test_server_default_uses_fresh_resolution_and_exact_authorization():
    validated = _validated_with_gravity()
    result = adapt_validated_phase55(_TEXT, validated)
    assert result.accepted and result.draft is not None
    assert len(result.approved_assumption_ids) == 1
    assumption_id = result.approved_assumption_ids[0]
    authorization = result.authorized_assumptions[assumption_id]
    default = next(
        item for item in result.draft.quantities
        if item.provenance.value == "server_default"
    )
    assert (default.raw_value, default.raw_unit) == ("9.81", "m/s^2")
    assert authorization.assumption_id == assumption_id
    assert authorization.raw_value == default.raw_value
    assert authorization.raw_unit == default.raw_unit
    assert authorization.subject_id == default.subject_id
    assert authorization.interval_id == default.interval_id

    tampered = deepcopy(validated)
    tampered.parse.assumption_proposals[0].proposed_value = "8"
    assert adapt_validated_phase55(_TEXT, tampered).terminal is ValidationTerminal.invalid


def test_system_diagnostic_does_not_change_calculation_graph():
    first = adapt_validated_phase55(_TEXT, _validated())
    changed = deepcopy(_validated())
    # A no-assumption Phase55 evaluation may alias its effective candidate to
    # the candidate stored in ``parse``.  Replace it with an isolated diagnostic
    # copy so this test changes only non-authoritative validated output rather
    # than silently forging the parse that must be freshly revalidated.
    diagnostic = changed.candidates[0].effective_candidate.model_copy(deep=True)
    diagnostic.system_type = type(diagnostic.system_type).single_particle_newton
    diagnostic.subtype = "diagnostic_revision"
    changed = replace(
        changed,
        candidates=(
            replace(changed.candidates[0], effective_candidate=diagnostic),
            *changed.candidates[1:],
        ),
    )
    assert (
        changed.parse.interpretation_candidates[0].system_type.value
        == "constant_acceleration_1d"
    )
    second = adapt_validated_phase55(_TEXT, changed)

    assert first.draft is not None and second.draft is not None
    left, right = first.draft.model_dump(), second.draft.model_dump()
    assert left["metadata"].pop("system_type") != right["metadata"].pop("system_type")
    assert left["metadata"].pop("subtype") != right["metadata"].pop("subtype")
    assert left == right


def test_all_phase55_event_kinds_have_explicit_conservative_mappings():
    expected = {
        "start": "start", "release": "release",
        "just_before_collision": "collision_start",
        "collision_start": "collision_start", "collision_end": "collision_end",
        "just_after_collision": "collision_end",
        "reaches_position": "reaches_condition", "reaches_height": "reaches_condition",
        "highest_point": "reaches_condition", "lowest_point": "reaches_condition",
        "comes_to_rest": "comes_to_rest", "turnaround": "turnaround",
        "contact_lost": "contact_end", "rope_taut": "rope_taut",
        "rope_slack": "rope_slack", "spring_max_compression": "reaches_condition",
        "finish": "finish", "other": "other",
    }
    assert {key: value.value for key, value in adapter._EVENTS.items()} == expected


def test_relation_closure_is_order_invariant_and_rope_is_only_topology():
    def with_relations(reverse: bool):
        payload = _parse_payload()
        payload["entities"].extend([
            {"entity_id": "body_b", "kind": "particle", "label": "B"},
            {"entity_id": "body_c", "kind": "particle", "label": "C"},
        ])
        relations = [
            {"relation_id": "link_ab", "kind": "connected_by_rope", "entity_ids": ["body", "body_b"]},
            {"relation_id": "link_bc", "kind": "connected_by_rope", "entity_ids": ["body_b", "body_c"]},
        ]
        payload["relations"] = list(reversed(relations)) if reverse else relations
        validated = validate_parse(_TEXT, TextbookProblemParseV1.model_validate(payload))
        assert validated.accepted
        return adapt_validated_phase55(_TEXT, validated)

    left, right = with_relations(False), with_relations(True)
    assert left.accepted and right.accepted
    assert left.draft is not None and right.draft is not None
    assert left.draft.entities == right.draft.entities
    assert left.draft.geometry == right.draft.geometry
    assert not left.draft.interactions and not right.draft.interactions
    assert {item.kind.value for item in left.draft.geometry} == {"topology_connects"}


def test_adjacent_boundary_fact_closes_source_interval_event_and_actor():
    boundary_text = _TEXT + " At the shared boundary its mass is 1 kg."
    payload = _parse_payload()
    payload["motion_segments"] = [
        {
            "segment_id": "prior", "order": 1, "actor_ids": ["body"],
            "motion_model_candidates": ["constant_acceleration_1d"],
            "end_event_id": "boundary", "relevance": "required_context",
        },
        {
            "segment_id": "seg", "order": 2, "actor_ids": ["body"],
            "motion_model_candidates": ["constant_acceleration_1d"],
            "start_event_id": "boundary", "relevance": "target",
        },
    ]
    payload["events"] = [{
        "event_id": "boundary", "kind": "start", "subject_ids": ["body"],
        "segment_id": "seg",
    }]
    payload["explicit_facts"].append({
        "fact_id": "fact_boundary_mass", "kind": "scalar",
        "semantic_key": "mass", "raw_value": "1", "raw_unit": "kg",
        "subject_id": "body", "segment_id": "prior",
        "event_id": "boundary", "temporal_role": "final",
        "direction": "not_applicable", "evidence_quote": "mass is 1 kg",
        "relevance": "constraint", "occurrence_index": 0,
        "quantity_occurrence_index": 0,
    })
    payload["interpretation_candidates"][0]["fact_ids"].append("fact_boundary_mass")
    validated = validate_parse(
        boundary_text, TextbookProblemParseV1.model_validate(payload)
    )
    assert validated.accepted
    result = adapt_validated_phase55(boundary_text, validated)
    assert result.accepted and result.draft is not None
    assert len(result.draft.motion_intervals) == 2
    assert len(result.draft.events) == 1
    assert len(result.draft.entities) == 1
    prior_interval = next(
        item for item in result.draft.motion_intervals if item.order == 1
    )
    boundary_event = result.draft.events[0]
    boundary_quantity = next(
        item for item in result.draft.quantities if item.role.value == "mass"
    )
    assert boundary_quantity.interval_id == prior_interval.interval_id
    assert boundary_quantity.event_id == boundary_event.event_id


def test_constraint_like_relation_and_reused_quantity_are_nonaccepted():
    constraint = _parse_payload()
    constraint["relations"] = [{
        "relation_id": "velocity_link", "kind": "shares_velocity_constraint",
        "entity_ids": ["body", "body"], "segment_id": "seg",
    }]
    # Duplicate participants may be rejected even before adapter mapping; use a
    # second real entity so the Phase55 graph itself remains meaningful.
    constraint["entities"].append(
        {"entity_id": "body_b", "kind": "particle", "label": "B"}
    )
    constraint["relations"][0]["entity_ids"] = ["body", "body_b"]
    validated = validate_parse(_TEXT, TextbookProblemParseV1.model_validate(constraint))
    assert validated.accepted
    assert not adapt_validated_phase55(_TEXT, validated).accepted

    reused = deepcopy(_validated())
    duplicate = deepcopy(reused.parse.explicit_facts[0])
    duplicate.fact_id = "duplicate_fact"
    reused.parse.explicit_facts.append(duplicate)
    reused.parse.interpretation_candidates[0].fact_ids.append("duplicate_fact")
    reused.candidates[0].effective_candidate.fact_ids.append("duplicate_fact")
    result = adapt_validated_phase55(_TEXT, reused)
    assert result.terminal is ValidationTerminal.invalid


def test_namespace_ids_are_bounded_and_distinct_for_long_source_ids():
    first = _parse_payload(identifier_suffix="A" * 50)
    second = _parse_payload(identifier_suffix="B" * 50)
    first_id = adapt_validated_phase55(_TEXT, validate_parse(_TEXT, TextbookProblemParseV1.model_validate(first))).draft.entities[0].entity_id
    second_id = adapt_validated_phase55(_TEXT, validate_parse(_TEXT, TextbookProblemParseV1.model_validate(second))).draft.entities[0].entity_id
    assert first_id != second_id and len(first_id) <= 64 and len(second_id) <= 64


def test_adapter_has_no_solver_or_answer_authority_route():
    source = inspect.getsource(adapter).lower()
    assert not any(token in source for token in ("corpus", "family", "case", "expected_answer", "solver"))
    assert "eval(" not in source and "exec(" not in source and "sympify" not in source
