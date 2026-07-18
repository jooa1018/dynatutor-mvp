from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.textbook_parser.contracts import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    TextbookProblemParseV2,
    TextbookProblemParseWireV2,
)
from engine.textbook_parser.normalization import normalize_wire_parse


@dataclass(frozen=True)
class LegalGraphFixture:
    fixture_id: str
    problem_text: str
    parse: TextbookProblemParseV2
    expected_terminal: str
    expected_system_type: str | None


def _entity(entity_id: str, kind: str, label: str) -> dict[str, Any]:
    return {"entity_id": entity_id, "kind": kind, "label": label}


def _event(event_id: str, kind: str, subjects: list[str], segment: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "kind": kind,
        "subject_ids": subjects,
        "segment_id": segment,
    }


def _segment(
    segment_id: str,
    actors: list[str],
    model: str,
    *,
    start: str | None = None,
    end: str | None = None,
    relevance: str = "target",
    order: int = 1,
) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "order": order,
        "actor_ids": actors,
        "motion_model_candidates": [model],
        "start_event_id": start,
        "end_event_id": end,
        "relevance": relevance,
    }


def _fact(
    fact_id: str,
    semantic_key: str,
    value: str,
    unit: str,
    subject: str,
    segment: str | None,
    quote: str,
    *,
    event: str | None = None,
    temporal: str = "timeless",
    direction: str = "not_applicable",
    relevance: str = "solver_input",
    kind: str = "scalar",
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "kind": kind,
        "semantic_key": semantic_key,
        "raw_value": value,
        "raw_unit": unit,
        "subject_id": subject,
        "segment_id": segment,
        "event_id": event,
        "temporal_role": temporal,
        "direction": direction,
        "evidence_quote": quote,
        "relevance": relevance,
    }


def _query(
    output: str,
    subject: str,
    segment: str | None,
    *,
    component: str = "magnitude",
    event: str | None = None,
) -> dict[str, Any]:
    return {
        "query_id": "query_target",
        "output_key": output,
        "subject_id": subject,
        "segment_id": segment,
        "event_id": event,
        "component": component,
    }


def _candidate(
    system_type: str,
    facts: list[str],
    *,
    assumptions: list[str] | None = None,
    segment: str = "motion",
) -> dict[str, Any]:
    return {
        "candidate_id": "candidate_primary",
        "system_type": system_type,
        "target_segment_ids": [segment],
        "fact_ids": facts,
        "query_ids": ["query_target"],
        "assumption_ids": assumptions or [],
        "reason_code": "typed_source_graph",
    }


def _base(
    *,
    status: str,
    entities: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    events: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    relations: list[dict[str, Any]] | None = None,
    assumptions: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    figure_level: str = "none",
    missing_figure: list[str] | None = None,
    ambiguities: list[dict[str, Any]] | None = None,
    unsupported: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_NAME,
        "version": SCHEMA_VERSION,
        "language": "en",
        "parse_status": status,
        "entities": entities,
        "motion_segments": segments,
        "events": events,
        "explicit_facts": facts,
        "relations": relations or [],
        "queries": queries,
        "assumption_proposals": assumptions or [],
        "interpretation_candidates": candidates or [],
        "ambiguities": ambiguities or [],
        "figure_dependency": {
            "level": figure_level,
            "missing_information": missing_figure or [],
        },
        "unsupported_features": unsupported or [],
    }


def _fixture(
    fixture_id: str,
    problem_text: str,
    payload: dict[str, Any],
    terminal: str,
    system_type: str | None,
) -> LegalGraphFixture:
    wire = TextbookProblemParseWireV2.model_validate(payload)
    return LegalGraphFixture(
        fixture_id,
        problem_text,
        normalize_wire_parse(problem_text, wire),
        terminal,
        system_type,
    )


def legal_graph_fixtures() -> tuple[LegalGraphFixture, ...]:
    fixtures: list[LegalGraphFixture] = []

    text = "A cart starts from rest and travels 16 m in 4 s with constant acceleration. Find its acceleration."
    fixtures.append(
        _fixture(
            "constant_acceleration",
            text,
            _base(
                status="complete",
                entities=[_entity("cart", "particle", "cart")],
                segments=[_segment("motion", ["cart"], "constant_acceleration_1d", start="start", end="finish")],
                events=[_event("start", "start", ["cart"], "motion"), _event("finish", "finish", ["cart"], "motion")],
                facts=[
                    _fact("fact_distance", "distance", "16", "m", "cart", "motion", "16 m", temporal="interval"),
                    _fact("fact_time", "time", "4", "s", "cart", "motion", "4 s", temporal="interval"),
                ],
                queries=[_query("acceleration", "cart", "motion")],
                assumptions=[{
                    "assumption_id": "assumption_rest",
                    "kind": "starts_from_rest",
                    "subject_id": "cart",
                    "segment_id": "motion",
                    "proposed_semantic_key": "initial_velocity",
                    "proposed_value": "0",
                    "proposed_unit": "m/s",
                    "reason": "The source explicitly starts from rest.",
                    "supporting_quote": "starts from rest",
                }],
                candidates=[_candidate("constant_acceleration_1d", ["fact_distance", "fact_time"], assumptions=["assumption_rest"])],
            ),
            "accepted_with_visible_assumptions",
            "constant_acceleration_1d",
        )
    )

    text = "A 3 kg particle has a net force of 6 N to the right. Find its acceleration."
    fixtures.append(
        _fixture(
            "newton_particle",
            text,
            _base(
                status="complete",
                entities=[_entity("particle", "particle", "particle")],
                segments=[_segment("motion", ["particle"], "unknown", start="start")],
                events=[_event("start", "start", ["particle"], "motion")],
                facts=[
                    _fact("fact_mass", "mass", "3", "kg", "particle", "motion", "3 kg"),
                    _fact("fact_force", "force", "6", "N", "particle", "motion", "6 N", direction="right", kind="vector_component"),
                ],
                queries=[_query("acceleration", "particle", "motion", component="x")],
                candidates=[_candidate("single_particle_newton", ["fact_mass", "fact_force"])],
            ),
            "solver_gap",
            "single_particle_newton",
        )
    )

    text = "A rigid body rotates about a fixed axis at 3 rad/s. Point P is 2 m from the axis. Find the tangential velocity of P."
    fixtures.append(
        _fixture(
            "fixed_axis_rigid_point",
            text,
            _base(
                status="complete",
                entities=[_entity("body", "rigid_body", "rigid body"), _entity("point_p", "point", "point P")],
                segments=[_segment("motion", ["body", "point_p"], "fixed_axis_rotation", start="start")],
                events=[_event("start", "start", ["body", "point_p"], "motion")],
                facts=[
                    _fact("fact_omega", "angular_velocity", "3", "rad/s", "body", "motion", "3 rad/s", direction="counterclockwise"),
                    _fact("fact_radius", "radius", "2", "m", "point_p", "motion", "2 m"),
                ],
                relations=[{"relation_id": "point_attachment", "kind": "point_on_body", "entity_ids": ["body", "point_p"], "segment_id": "motion"}],
                queries=[_query("tangential_velocity", "point_p", "motion", component="tangential")],
                candidates=[_candidate("fixed_axis_rotation", ["fact_omega", "fact_radius"])],
            ),
            "solver_gap",
            "fixed_axis_rotation",
        )
    )

    text = "A disk of radius 0.3 m rolls without slipping at 2 m/s. Find its angular velocity."
    fixtures.append(
        _fixture(
            "pure_rolling",
            text,
            _base(
                status="complete",
                entities=[_entity("disk", "disk", "disk")],
                segments=[_segment("motion", ["disk"], "rolling_without_slipping", start="start")],
                events=[_event("start", "start", ["disk"], "motion")],
                facts=[
                    _fact("fact_radius", "radius", "0.3", "m", "disk", "motion", "0.3 m"),
                    _fact("fact_velocity", "velocity", "2", "m/s", "disk", "motion", "2 m/s"),
                ],
                queries=[_query("angular_velocity", "disk", "motion")],
                assumptions=[{
                    "assumption_id": "assumption_rolling",
                    "kind": "pure_rolling",
                    "subject_id": "disk",
                    "segment_id": "motion",
                    "proposed_semantic_key": "restitution_coefficient",
                    "proposed_value": "1",
                    "proposed_unit": "",
                    "reason": "The source explicitly says without slipping.",
                    "supporting_quote": "without slipping",
                }],
                candidates=[_candidate("pure_rolling_energy", ["fact_radius", "fact_velocity"], assumptions=["assumption_rolling"])],
            ),
            "solver_gap",
            "pure_rolling_energy",
        )
    )

    text = "Use the missing figure's angle and link length to find the velocity of point B."
    fixtures.append(
        _fixture(
            "figure_required",
            text,
            _base(
                status="needs_figure",
                entities=[_entity("point_b", "point", "point B")],
                segments=[],
                events=[],
                facts=[],
                queries=[_query("final_velocity", "point_b", None)],
                figure_level="required",
                missing_figure=["angle", "link length"],
            ),
            "needs_figure",
            None,
        )
    )

    text = "Mass A is 2 kg and mass B is 4 kg on a massless rope over a frictionless pulley. Find the system acceleration."
    fixtures.append(
        _fixture(
            "atwood_pulley",
            text,
            _base(
                status="complete",
                entities=[
                    _entity("system", "system", "Atwood system"),
                    _entity("mass_a", "block", "mass A"),
                    _entity("mass_b", "block", "mass B"),
                    _entity("pulley", "pulley", "pulley"),
                ],
                segments=[_segment("motion", ["system", "mass_a", "mass_b", "pulley"], "unknown", start="start")],
                events=[_event("start", "start", ["system", "mass_a", "mass_b", "pulley"], "motion")],
                facts=[
                    _fact("fact_mass_1", "mass_1", "2", "kg", "mass_a", "motion", "2 kg"),
                    _fact("fact_mass_2", "mass_2", "4", "kg", "mass_b", "motion", "4 kg"),
                ],
                relations=[
                    {"relation_id": "rope_connection", "kind": "connected_by_rope", "entity_ids": ["mass_a", "mass_b"], "segment_id": "motion"},
                    {"relation_id": "pulley_constraint", "kind": "passes_over_pulley", "entity_ids": ["mass_a", "mass_b", "pulley"], "segment_id": "motion"},
                ],
                queries=[_query("acceleration", "system", "motion")],
                assumptions=[
                    {"assumption_id": "assumption_rope", "kind": "massless_rope", "subject_id": "system", "segment_id": "motion", "proposed_semantic_key": "mass", "proposed_value": "0", "proposed_unit": "kg", "reason": "The rope is explicitly massless.", "supporting_quote": "massless rope"},
                    {"assumption_id": "assumption_friction", "kind": "frictionless", "subject_id": "system", "segment_id": "motion", "proposed_semantic_key": "coefficient_of_friction", "proposed_value": "0", "proposed_unit": "", "reason": "The pulley is explicitly frictionless.", "supporting_quote": "frictionless pulley"},
                ],
                candidates=[_candidate("pulley_atwood", ["fact_mass_1", "fact_mass_2"], assumptions=["assumption_rope", "assumption_friction"])],
            ),
            "solver_gap",
            "pulley_atwood",
        )
    )

    text = "A constant force of 6 N moves a cart 3 m along the force. Find the work done by this force."
    fixtures.append(
        _fixture(
            "constant_force_work",
            text,
            _base(
                status="complete",
                entities=[_entity("cart", "particle", "cart")],
                segments=[_segment("motion", ["cart"], "energy_interval", start="start", end="finish")],
                events=[_event("start", "start", ["cart"], "motion"), _event("finish", "finish", ["cart"], "motion")],
                facts=[
                    _fact("fact_force", "force", "6", "N", "cart", "motion", "6 N", temporal="interval", direction="along_motion", kind="vector_component"),
                    _fact("fact_distance", "distance", "3", "m", "cart", "motion", "3 m", temporal="interval", direction="along_motion"),
                ],
                queries=[_query("work", "cart", "motion")],
                candidates=[_candidate("constant_force_work", ["fact_force", "fact_distance"])],
            ),
            "solver_gap",
            "constant_force_work",
        )
    )

    text = "An object is moving. Find how long it has traveled. No speed or distance is given."
    fixtures.append(
        _fixture(
            "insufficient_information",
            text,
            _base(
                status="insufficient_information",
                entities=[_entity("object", "particle", "object")],
                segments=[],
                events=[],
                facts=[],
                queries=[_query("time", "object", None)],
                ambiguities=[{"ambiguity_id": "missing_motion_data", "kind": "interpretation", "referenced_ids": ["object"], "description": "No source quantities determine elapsed time."}],
            ),
            "insufficient_information",
            None,
        )
    )

    text = "An oscillator repeats its state every 3 s. Find its frequency."
    fixtures.append(
        _fixture(
            "vibration",
            text,
            _base(
                status="complete",
                entities=[_entity("oscillator", "spring", "oscillator")],
                segments=[_segment("motion", ["oscillator"], "spring_oscillation", start="start")],
                events=[_event("start", "start", ["oscillator"], "motion")],
                facts=[_fact("fact_period", "period", "3", "s", "oscillator", "motion", "3 s", temporal="interval")],
                queries=[_query("frequency", "oscillator", "motion")],
                candidates=[_candidate("spring_mass_vibration", ["fact_period"])],
            ),
            "solver_gap",
            "spring_mass_vibration",
        )
    )

    text = "A 2 kg cart moves right at 3 m/s just before collision and comes to rest after the collision. Find the impulse magnitude."
    fixtures.append(
        _fixture(
            "collision_impulse",
            text,
            _base(
                status="complete",
                entities=[_entity("cart", "particle", "cart")],
                segments=[_segment("motion", ["cart"], "collision_contact", start="collision_start", end="collision_end")],
                events=[_event("collision_start", "collision_start", ["cart"], "motion"), _event("collision_end", "collision_end", ["cart"], "motion")],
                facts=[
                    _fact("fact_mass", "mass", "2", "kg", "cart", "motion", "2 kg"),
                    _fact("fact_velocity_before", "velocity_before", "3", "m/s", "cart", "motion", "3 m/s", event="collision_start", temporal="before_event", direction="right", kind="vector_component"),
                ],
                queries=[_query("impulse", "cart", "motion")],
                assumptions=[{"assumption_id": "assumption_rest", "kind": "ends_at_rest", "subject_id": "cart", "segment_id": "motion", "proposed_semantic_key": "final_velocity", "proposed_value": "0", "proposed_unit": "m/s", "reason": "The source says the cart comes to rest.", "supporting_quote": "comes to rest"}],
                candidates=[_candidate("impulse_momentum", ["fact_mass", "fact_velocity_before"], assumptions=["assumption_rest"])],
            ),
            "solver_gap",
            "impulse_momentum",
        )
    )

    text = "Ignoring air resistance, a ball is launched at 11 m/s and 45 deg. A 6 m sign is background context. Find maximum height."
    fixtures.append(
        _fixture(
            "projectile",
            text,
            _base(
                status="complete",
                entities=[_entity("ball", "particle", "ball"), _entity("sign", "other", "background sign")],
                segments=[_segment("motion", ["ball"], "projectile_free_flight", start="start")],
                events=[_event("start", "start", ["ball"], "motion")],
                facts=[
                    _fact("fact_speed", "initial_velocity", "11", "m/s", "ball", "motion", "11 m/s", event="start", temporal="initial"),
                    _fact("fact_angle", "angle", "45", "deg", "ball", "motion", "45 deg", event="start", temporal="initial"),
                    _fact("fact_background", "background_height", "6", "m", "sign", None, "6 m", relevance="context_only"),
                ],
                queries=[_query("max_height", "ball", "motion")],
                assumptions=[
                    {"assumption_id": "assumption_air", "kind": "no_air_resistance", "subject_id": "ball", "segment_id": "motion", "proposed_semantic_key": "coefficient_of_friction", "proposed_value": "0", "proposed_unit": "", "reason": "Air resistance is explicitly ignored.", "supporting_quote": "Ignoring air resistance"},
                    {"assumption_id": "assumption_gravity", "kind": "constant_gravity", "subject_id": "ball", "segment_id": "motion", "proposed_semantic_key": "acceleration", "proposed_value": "9.81", "proposed_unit": "m/s^2", "reason": "Use the server near-Earth gravity policy."},
                ],
                candidates=[_candidate("projectile_motion", ["fact_speed", "fact_angle"], assumptions=["assumption_air", "assumption_gravity"])],
            ),
            "solver_gap",
            "projectile_motion",
        )
    )

    text = "An object in nonlinear turbulent flow has an explicit drag force of 2 N. Find the coupled turbulent field force."
    fixtures.append(
        _fixture(
            "unsupported_nonlinear_flow",
            text,
            _base(
                status="unsupported",
                entities=[_entity("object", "particle", "object")],
                segments=[_segment("motion", ["object"], "unknown", start="start")],
                events=[_event("start", "start", ["object"], "motion")],
                facts=[_fact("fact_force", "force", "2", "N", "object", "motion", "2 N", relevance="context_only")],
                queries=[_query("force", "object", "motion")],
                candidates=[_candidate("nonlinear_turbulent_flow", [])],
                unsupported=[{"feature_code": "nonlinear_turbulent_field", "description": "The deterministic textbook-safe solver does not support this nonlinear field model."}],
            ),
            "solver_gap",
            "nonlinear_turbulent_flow",
        )
    )

    return tuple(fixtures)


PROMPT_EXAMPLE_FIXTURE_IDS = (
    "constant_acceleration",
    "figure_required",
    "fixed_axis_rigid_point",
    "atwood_pulley",
    "constant_force_work",
    "collision_impulse",
    "insufficient_information",
)


__all__ = [
    "LegalGraphFixture",
    "PROMPT_EXAMPLE_FIXTURE_IDS",
    "legal_graph_fixtures",
]
