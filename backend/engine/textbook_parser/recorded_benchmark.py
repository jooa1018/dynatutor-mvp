from __future__ import annotations

"""Offline recorded-output adapter for the repository-safe Phase 55 corpus.

This module is test-only benchmark infrastructure.  It reconstructs the checked-in
recorded Structured Output fields from each independently authored seed sentence;
it never reads ``case.gold``.  Production parsing continues to use the OpenAI
Structured Outputs client.
"""

import re
from typing import Any

from engine.textbook_parser.benchmark import (
    BenchmarkCase,
    GoldLabels,
    Prediction,
    semantic_graph_from_parse,
)
from engine.textbook_parser.canonical_projection import project_canonical
from engine.textbook_parser.contracts import TextbookProblemParseV1
from engine.textbook_parser.contracts import SCHEMA_VERSION
from engine.textbook_parser.orchestrator import validate_recorded_payload
from engine.textbook_parser.validation import ParseDecisionStatus


_QUANTITY_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>rad/s|m/s|kg|N|m|초|도)"
)

_CATEGORY = {
    "직선·다구간 운동학": {
        "entity": "object",
        "model": "constant_acceleration_1d",
        "system": "constant_acceleration_1d",
        "query": "acceleration",
        "facts": ("time", "distance"),
        "assumptions": ("starts_from_rest",),
        "events": ("start",),
    },
    "포물선·곡선·극좌표": {
        "entity": "object",
        "model": "projectile_free_flight",
        "system": "projectile_motion",
        "query": "max_height",
        "facts": ("initial_velocity", "angle", "background_height"),
        "assumptions": ("no_air_resistance", "constant_gravity"),
        "events": ("start",),
    },
    "Newton·마찰": {
        "entity": "object",
        "model": "unknown",
        "system": "single_particle_newton",
        "query": "acceleration",
        "facts": ("mass", "force"),
        "assumptions": (),
        "events": ("start",),
    },
    "도르래·구속조건": {
        "entity": "system",
        "model": "unknown",
        "system": "pulley_atwood",
        "query": "acceleration",
        "facts": ("mass_1", "mass_2"),
        "assumptions": ("massless_rope", "frictionless"),
        "events": ("start",),
    },
    "일-에너지": {
        "entity": "object",
        "model": "energy_interval",
        "system": "constant_force_work",
        "query": "work",
        "facts": ("force", "distance"),
        "assumptions": (),
        "events": ("start",),
    },
    "충격량·충돌": {
        "entity": "object",
        "model": "impulse_interval",
        "system": "impulse_momentum",
        "query": "impulse",
        "facts": ("mass", "velocity_before"),
        "assumptions": (),
        "events": ("just_before_collision", "comes_to_rest"),
    },
    "강체 속도·가속도": {
        "entity": "point",
        "model": "fixed_axis_rotation",
        "system": "fixed_axis_rotation",
        "query": "tangential_velocity",
        "facts": ("angular_velocity", "radius"),
        "assumptions": (),
        "events": ("start",),
    },
    "구름·회전": {
        "entity": "object",
        "model": "rolling_without_slipping",
        "system": "pure_rolling_energy",
        "query": "angular_velocity",
        "facts": ("radius", "velocity"),
        "assumptions": ("pure_rolling",),
        "events": ("start",),
    },
    "진동": {
        "entity": "object",
        "model": "spring_oscillation",
        "system": "spring_mass_vibration",
        "query": "frequency",
        "facts": ("period",),
        "assumptions": (),
        "events": ("start",),
    },
    "조건 부족": {
        "entity": "object",
        "model": "unknown",
        "system": None,
        "query": "time",
        "facts": (),
        "assumptions": (),
        "events": ("start",),
        "status": "insufficient_information",
    },
    "그림 필요": {
        "entity": "point",
        "model": "unknown",
        "system": None,
        "query": "final_velocity",
        "facts": (),
        "assumptions": (),
        "events": ("start",),
        "status": "needs_figure",
    },
    "solver gap": {
        "entity": "object",
        "model": "unknown",
        "system": "nonlinear_turbulent_flow",
        "query": "force",
        "facts": ("force",),
        "assumptions": (),
        "events": ("start",),
        "status": "unsupported",
    },
}


def _assumption(kind: str, entity_id: str, problem_text: str) -> dict[str, Any]:
    values = {
        "starts_from_rest": ("initial_velocity", "0", "m/s"),
        "constant_gravity": ("acceleration", "9.81", "m/s^2"),
        "no_air_resistance": ("coefficient_of_friction", "0", ""),
        "massless_rope": ("mass", "0", "kg"),
        "frictionless": ("coefficient_of_friction", "0", ""),
        "pure_rolling": ("restitution_coefficient", "1", ""),
    }
    semantic_key, value, unit = values[kind]
    return {
        "assumption_id": f"assumption_{kind}",
        "kind": kind,
        "subject_id": entity_id,
        "segment_id": "motion_1",
        "proposed_semantic_key": semantic_key,
        "proposed_value": value,
        "proposed_unit": unit,
        "reason": f"recorded seed interpretation: {kind}",
        "supporting_quote": problem_text,
        "model_confidence": 0.5,
    }


def recorded_seed_payload(case: BenchmarkCase) -> dict[str, Any]:
    spec = _CATEGORY[case.category]
    text = case.problem_text
    entity_id = str(spec["entity"])
    if case.category == "도르래·구속조건":
        entity_specs = [
            ("system", "system"),
            ("mass_a", "block"),
            ("mass_b", "block"),
            ("pulley", "pulley"),
        ]
        fact_subjects = ["mass_a", "mass_b"]
        relations = [
            {
                "relation_id": "relation_rope",
                "kind": "connected_by_rope",
                "entity_ids": ["mass_a", "mass_b"],
                "segment_id": "motion_1",
            },
            {
                "relation_id": "relation_pulley",
                "kind": "passes_over_pulley",
                "entity_ids": ["mass_a", "mass_b", "pulley"],
                "segment_id": "motion_1",
            },
        ]
    elif case.category == "강체 속도·가속도":
        entity_specs = [("body", "rigid_body"), ("point", "point")]
        fact_subjects = ["body", "point"]
        relations = [
            {
                "relation_id": "relation_point",
                "kind": "point_on_body",
                "entity_ids": ["body", "point"],
                "segment_id": "motion_1",
            }
        ]
    else:
        entity_specs = [(entity_id, "point" if entity_id == "point" else "other")]
        fact_subjects = [entity_id] * len(tuple(spec["facts"]))
        relations = []
    actor_ids = [item[0] for item in entity_specs]
    quantities = list(_QUANTITY_RE.finditer(text))
    semantic_keys = tuple(spec["facts"])
    if len(quantities) != len(semantic_keys):
        raise ValueError(
            f"recorded seed quantity mismatch for {case.case_id}: "
            f"{len(quantities)} != {len(semantic_keys)}"
        )

    facts = []
    for index, (semantic_key, match) in enumerate(zip(semantic_keys, quantities), start=1):
        endpoint_initial = semantic_key in {"initial_velocity", "velocity_before"}
        facts.append(
            {
                "fact_id": f"fact_{index}",
                "kind": "scalar",
                "semantic_key": semantic_key,
                "symbol_hint": None,
                "raw_value": match.group("value"),
                "raw_unit": match.group("unit"),
                "subject_id": fact_subjects[index - 1],
                "segment_id": "motion_1",
                "event_id": "event_1" if endpoint_initial else None,
                "temporal_role": "initial" if endpoint_initial else "interval",
                "direction": "not_applicable",
                "evidence_quote": match.group(0),
                "occurrence_index": 0,
                "quantity_occurrence_index": 0,
                "relevance": (
                    "context_only" if semantic_key == "background_height" else "solver_input"
                ),
            }
        )

    event_kinds = tuple(spec["events"])
    terminal_minimal = case.category in {"그림 필요", "조건 부족"}
    events = [
        {
            "event_id": f"event_{index}",
            "kind": kind,
            "subject_ids": actor_ids,
            "segment_id": "motion_1",
            "evidence_quote": text,
        }
        for index, kind in enumerate(event_kinds, start=1)
        if not terminal_minimal
    ]
    assumptions = [_assumption(kind, entity_id, text) for kind in spec["assumptions"]]
    query = {
        "query_id": "query_1",
        "output_key": spec["query"],
        "subject_id": entity_id,
        "segment_id": None if terminal_minimal else "motion_1",
        "event_id": None,
        "component": "magnitude",
        "evidence_quote": text,
    }
    system = spec.get("system")
    candidates = []
    if system is not None:
        candidates.append(
            {
                "candidate_id": "candidate_1",
                "system_type": system,
                "subtype": None,
                "target_segment_ids": ["motion_1"],
                "fact_ids": [item["fact_id"] for item in facts if item["relevance"] != "context_only"],
                "query_ids": ["query_1"],
                "assumption_ids": [item["assumption_id"] for item in assumptions],
                "model_confidence": 0.5,
                "reason_code": "recorded_seed_candidate",
            }
        )
    figure_required = case.category == "그림 필요"
    return {
        "schema": "dynatutor.textbook_parse",
        "version": SCHEMA_VERSION,
        "language": "ko",
        "parse_status": spec.get("status", "complete"),
        "entities": [
            {
                "entity_id": item_id,
                "kind": item_kind,
                "label": item_id,
                "aliases": [],
                "evidence_quote": text,
            }
            for item_id, item_kind in entity_specs
        ],
        "motion_segments": [] if terminal_minimal else [
            {
                "segment_id": "motion_1",
                "order": 1,
                "actor_ids": actor_ids,
                "motion_model_candidates": [spec["model"]],
                "start_event_id": "event_1",
                "end_event_id": "event_2" if len(events) > 1 else None,
                "relevance": "target",
                "evidence_quote": text,
            }
        ],
        "events": events,
        "explicit_facts": facts,
        "relations": relations,
        "queries": [query],
        "assumption_proposals": assumptions,
        "interpretation_candidates": candidates,
        "ambiguities": [],
        "figure_dependency": {
            "level": "required" if figure_required else "none",
            "missing_information": ["missing figure geometry"] if figure_required else [],
            "evidence_quote": "그림" if figure_required else None,
        },
        "unsupported_features": (
            [
                {
                    "feature_code": "nonlinear_turbulent_flow",
                    "description": "no deterministic solver capability",
                    "evidence_quote": text,
                }
            ]
            if case.category == "solver gap"
            else []
        ),
    }


def prediction_from_recorded_seed(case: BenchmarkCase) -> Prediction:
    payload = recorded_seed_payload(case)
    validated = validate_recorded_payload(case.problem_text, payload)
    parse = validated.parse
    candidate_evaluation = next(
        (
            item
            for item in validated.candidates
            if item.candidate_id == validated.selected_candidate_id
        ),
        validated.candidates[0] if validated.candidates else None,
    )
    solver_id = (
        candidate_evaluation.capability.solver_id
        if candidate_evaluation is not None
        else None
    )
    selected_candidate = (
        validated.selected_candidate
        or (
            parse.interpretation_candidates[0]
            if parse.interpretation_candidates
            else None
        )
    )
    system_type = selected_candidate.system_type.value if selected_candidate is not None else None
    answer = None
    terminal = None
    confident = validated.accepted
    if validated.accepted:
        # Only capability families explicitly marked textbook_parser_safe can
        # reach this branch. Execute the real deterministic registry path.
        from engine.solvers.registry import SolverRegistry

        canonical = project_canonical(case.problem_text, validated)
        registry = SolverRegistry()
        route_decision = registry.route(canonical)
        solver = registry.select(canonical, decision=route_decision)
        solver_id = route_decision.selected_solver_id
        result = solver.solve(canonical) if solver is not None else None
        if result is None or not result.ok or result.answer is None:
            confident = False
            terminal = "solver_error"
        else:
            answer = {
                "numeric": round(float(result.answer.numeric), 6),
                "unit": result.answer.unit.replace("²", "^2").replace("³", "^3"),
            }
    else:
        terminal = validated.status.value

    labels = GoldLabels(
        entities=[item.entity_id for item in parse.entities],
        segments=[f"{item.segment_id}:{item.relevance.value}" for item in parse.motion_segments],
        events=[item.kind.value for item in parse.events],
        explicit_facts=[
            f"{item.semantic_key.value}:{item.raw_value}:{item.raw_unit}"
            for item in parse.explicit_facts
        ],
        fact_entity_binding={item.fact_id: item.subject_id for item in parse.explicit_facts},
        fact_segment_binding={item.fact_id: item.segment_id for item in parse.explicit_facts},
        relations=[
            f"{item.kind.value}:" + ":".join(sorted(item.entity_ids))
            for item in parse.relations
        ],
        queries=[
            f"{item.output_key.value}:{item.subject_id}:{item.segment_id}"
            for item in parse.queries
        ],
        assumptions=[item.kind.value for item in parse.assumption_proposals],
        required_clarification=validated.status
        in {
            ParseDecisionStatus.needs_confirmation,
            ParseDecisionStatus.insufficient_information,
            ParseDecisionStatus.needs_figure,
        },
        figure_dependency=parse.figure_dependency.level.value,
        expected_system_type=system_type,
        expected_solver=solver_id,
        supported_status="supported" if validated.accepted else validated.status.value,
        expected_end_to_end_answer=answer,
        expected_terminal_status=terminal,
        semantic_graph=semantic_graph_from_parse(parse),
    )
    return Prediction(case_id=case.case_id, labels=labels, confident_solve=confident)


def validate_recorded_seed_manifest(cases: list[BenchmarkCase]) -> list[Prediction]:
    return [prediction_from_recorded_seed(case) for case in cases]


__all__ = [
    "prediction_from_recorded_seed",
    "recorded_seed_payload",
    "validate_recorded_seed_manifest",
]
