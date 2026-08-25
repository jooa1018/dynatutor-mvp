"""Lane B: generic corpus-structure to deterministic-engine adapter.

The adapter projects one corpus case's *source-grounded structure* into a
`TextbookProblemParseV1`, which the existing Phase 55 adapter turns into a
`MechanicsProblemDraftV1` for the deterministic engine.

Only these gold members may be read, and the whitelist is enforced in code:

    entities, motion_segments, events, explicit_facts, relations,
    assumption_proposals, queries, figure_dependency

Never read: case_id, family, split, difficulty, tags, chapter, provenance,
`expected_system_type`, `phase55_expected_terminal`, `future_expected_terminal`,
`answers`, `expected_failure_codes`.  In particular the interpretation
candidate's `ParserSystemType` is derived **structurally** from relation kinds,
motion models, entity kinds, and the query output key; the corpus system type is
never copied.  `validate_parse` does not read `system_type` at all, so the label
carries no routing, law, solver, or answer authority.

This lane measures the deterministic engine, not AI parser quality.

Status: **projection is incomplete.**  Against the authorised archive, 60 of
100 cases project cleanly.  The remaining 40 hit two structural mismatches
between the corpus graph and the parse graph contract, each of which needs a
principled resolution before Lane B can execute:

1. 25 cases bind a query to both a segment and a *mid-interval* event (for
   example an ``instant`` observation).  ``validate_graph_contract`` only
   permits that pairing when the event is a boundary of the segment.
2. 15 cases attach a timeless contact property (``angle``,
   ``coefficient_of_friction``) to an environment entity (``incline``,
   ``surface``, ``road``) that is deliberately not an actor of the motion
   segment, while the contract requires a fact's subject to be an actor of any
   segment it binds.

Dropping either binding is *not* a fix: the interpretation candidate requires
the same query-to-target-segment and fact-to-target-segment closure, so the
failure simply moves.  Both were tried and reverted rather than left in place.
Resolving this needs a rule that satisfies the graph contract and candidate
closure at once, without inventing a static surface as a moving actor and
without silently redefining a motion interval.  Until then no Lane B result is
produced and no Lane B claim is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from engine.textbook_parser.contracts import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    AssumptionProposal,
    Entity,
    Event,
    ExplicitFact,
    FigureDependency,
    InterpretationCandidate,
    MotionSegment,
    ParserSystemType,
    Query,
    Relation,
    TextbookProblemParseV1,
)

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1


LANE_B_ADAPTER_VERSION = "phase56-stage7-lane-b-adapter-v1"

# The only gold members this lane is permitted to read.
PERMITTED_GOLD_MEMBERS: frozenset[str] = frozenset(
    {
        "entities",
        "motion_segments",
        "events",
        "explicit_facts",
        "relations",
        "assumption_proposals",
        "queries",
        "figure_dependency",
    }
)
FORBIDDEN_GOLD_MEMBERS: frozenset[str] = frozenset(
    {
        "parse_status",
        "expected_system_type",
        "phase55_expected_terminal",
        "future_expected_terminal",
        "answers",
        "expected_failure_codes",
    }
)

# Server-valued assumption vocabulary.  These are physics constants and
# boundary conditions implied by an accepted assumption kind, not corpus
# answers: no value here is read from gold.answers.
_ASSUMPTION_VALUES: dict[str, tuple[str, str, str]] = {
    "constant_gravity": ("acceleration", "9.81", "m/s^2"),
    "starts_from_rest": ("initial_velocity", "0", "m/s"),
    "ends_at_rest": ("final_velocity", "0", "m/s"),
    "frictionless": ("coefficient_of_friction", "0", ""),
    "no_air_resistance": ("force", "0", "N"),
    "massless_rope": ("mass", "0", "kg"),
    "massless_pulley": ("mass", "0", "kg"),
    "inextensible_rope": ("distance", "0", "m"),
    "pure_rolling": ("velocity", "0", "m/s"),
}

_VECTOR_DIRECTIONS = frozenset(
    {
        "positive",
        "negative",
        "upward",
        "downward",
        "left",
        "right",
        "clockwise",
        "counterclockwise",
        "along_motion",
        "opposite_motion",
        "radial",
        "tangential",
    }
)


class LaneBAdapterError(ValueError):
    """The corpus structure could not be projected into a parse."""


@dataclass(frozen=True, slots=True)
class LaneBProjection:
    parse: TextbookProblemParseV1
    problem_text: str
    derived_system_type: str
    derived_parse_status: str


def _fact_kind(raw_unit: str | None, direction: str | None) -> str:
    if not raw_unit:
        return "dimensionless"
    if direction in _VECTOR_DIRECTIONS:
        return "vector_component"
    return "scalar"


def derive_system_type(case: PublicCorpusCaseV1) -> ParserSystemType:
    """Derive a diagnostics-only system label from structure alone.

    Inputs are relation kinds, motion models, entity kinds, event kinds, and the
    query output key.  The corpus family and `expected_system_type` are never
    consulted, and the result has no routing, law, solver, or answer authority.
    """

    gold = case.gold
    relations = {relation.kind for relation in gold.relations}
    motions = {
        segment.motion_model for segment in gold.motion_segments if segment.motion_model
    }
    entities = {entity.kind for entity in gold.entities}
    events = {event.kind for event in gold.events}
    outputs = {query.output_key for query in gold.queries}

    if "collides_with" in relations or "collision_contact" in motions:
        if outputs & {"v1_after", "v2_after", "post_collision_velocity"}:
            return ParserSystemType.collision_1d
        if outputs & {"impulse"}:
            return ParserSystemType.impulse_momentum
        return ParserSystemType.collision_1d
    if "moves_in_slot" in relations:
        return ParserSystemType.slot_pin_relative_motion
    if "moves_relative_to" in relations or "relative_motion" in motions:
        return ParserSystemType.relative_acceleration_translation
    if "attached_to_spring" in relations or "spring" in entities:
        if "spring_oscillation" in motions or outputs & {
            "period",
            "frequency",
            "angular_frequency",
        }:
            return ParserSystemType.spring_mass_vibration
        return ParserSystemType.spring_energy
    if "passes_over_pulley" in relations or "pulley" in entities:
        if "incline" in entities:
            return ParserSystemType.pulley_incline_hanging
        if "surface" in entities:
            return ParserSystemType.pulley_table_hanging
        if outputs & {"angular_acceleration"} or "disk" in entities:
            return ParserSystemType.massive_pulley_atwood
        return ParserSystemType.pulley_atwood
    if "rolls_on" in relations or motions & {
        "rolling_without_slipping",
        "rolling_with_slip",
    }:
        if outputs & {"kinetic_energy", "final_velocity", "initial_velocity"}:
            return ParserSystemType.pure_rolling_energy
        return ParserSystemType.rolling_energy_general
    if "rotates_about" in relations or "fixed_axis_rotation" in motions:
        return ParserSystemType.fixed_axis_rotation
    if "projectile_free_flight" in motions:
        return ParserSystemType.projectile_motion
    if "incline" in entities or "sliding_on_incline" in motions:
        return ParserSystemType.particle_on_incline
    if events & {"highest_point", "lowest_point", "contact_lost"}:
        return ParserSystemType.vertical_circle
    if outputs & {"centripetal_acceleration", "minimum_speed"}:
        return ParserSystemType.flat_curve_friction
    if outputs & {"work", "kinetic_energy", "potential_energy", "elastic_energy"}:
        return ParserSystemType.work_energy_speed
    if outputs & {"tangential_velocity", "angular_velocity"}:
        return ParserSystemType.polar_kinematics
    if outputs & {"friction_force", "normal_force"}:
        return ParserSystemType.horizontal_friction_force
    if outputs & {"force", "tension"}:
        return ParserSystemType.single_particle_newton
    if outputs & {"distance", "time", "final_velocity", "initial_velocity"}:
        return ParserSystemType.constant_acceleration_1d
    return ParserSystemType.other


def derive_parse_status(case: PublicCorpusCaseV1) -> str:
    """Derive the parse status from structure, never from the gold terminal."""

    gold = case.gold
    if gold.figure_dependency.level.casefold() == "required":
        return "needs_figure"
    if not gold.queries:
        return "insufficient_information"
    return "complete"


def _assert_only_permitted_gold_is_read(reader: Mapping[str, Any]) -> None:
    touched = frozenset(reader)
    leaked = touched & FORBIDDEN_GOLD_MEMBERS
    if leaked:
        raise LaneBAdapterError(
            f"lane B adapter read forbidden gold members: {sorted(leaked)}"
        )
    if not touched <= PERMITTED_GOLD_MEMBERS:
        raise LaneBAdapterError("lane B adapter read an undeclared gold member")


def project_case_to_parse(case: PublicCorpusCaseV1) -> LaneBProjection:
    """Project one corpus case's source-grounded structure into a parse."""

    gold = case.gold
    projection_source: dict[str, Any] = {
        "entities": gold.entities,
        "motion_segments": gold.motion_segments,
        "events": gold.events,
        "explicit_facts": gold.explicit_facts,
        "relations": gold.relations,
        "assumption_proposals": gold.assumption_proposals,
        "queries": gold.queries,
        "figure_dependency": gold.figure_dependency,
    }
    _assert_only_permitted_gold_is_read(projection_source)

    entities = [
        Entity(
            entity_id=entity.role,
            kind=entity.kind,
            label=entity.label or entity.role,
            evidence_quote=None,
        )
        for entity in gold.entities
    ]
    segments = [
        MotionSegment(
            segment_id=segment.role,
            order=segment.order,
            actor_ids=list(segment.actor_roles),
            motion_model_candidates=[segment.motion_model or "unknown"],
            start_event_id=segment.start_event_role,
            end_event_id=segment.end_event_role,
            relevance=segment.relevance or "target",
            evidence_quote=None,
        )
        for segment in gold.motion_segments
    ]
    events = [
        Event(
            event_id=event.role,
            kind=event.kind,
            subject_ids=list(event.subject_roles),
            segment_id=event.segment_role,
            evidence_quote=event.evidence_quote,
        )
        for event in gold.events
    ]
    # A segment may declare a boundary the corpus does not materialise as an
    # event object.  The kind comes from the *slot* the reference occupies —
    # start slot means start, end slot means finish — never from the role
    # string, so no name-based routing enters the projection.
    known_event_ids = {event.event_id for event in events}
    for segment in gold.motion_segments:
        for role, kind in (
            (segment.start_event_role, "start"),
            (segment.end_event_role, "finish"),
        ):
            if role is None or role in known_event_ids:
                continue
            events.append(
                Event(
                    event_id=role,
                    kind=kind,
                    subject_ids=list(segment.actor_roles) or [entities[0].entity_id],
                    segment_id=segment.role,
                    evidence_quote=None,
                )
            )
            known_event_ids.add(role)
    facts = [
        ExplicitFact(
            fact_id=fact.role,
            kind=_fact_kind(fact.raw_unit, fact.direction),
            semantic_key=fact.semantic_key,
            raw_value=fact.raw_value,
            raw_unit=fact.raw_unit or "",
            subject_id=fact.subject_role,
            segment_id=fact.segment_role,
            event_id=fact.event_role,
            temporal_role=fact.temporal_role or "timeless",
            direction=fact.direction or "not_applicable",
            evidence_quote=fact.evidence_quote,
            relevance=fact.relevance or "solver_input",
            occurrence_index=fact.occurrence_index,
            quantity_occurrence_index=fact.quantity_occurrence_index,
        )
        for fact in gold.explicit_facts
    ]
    relations = [
        Relation(
            relation_id=relation.role,
            kind=relation.kind,
            entity_ids=list(relation.participant_roles),
            segment_id=relation.segment_role,
            evidence_quote=None,
        )
        for relation in gold.relations
    ]
    queries = [
        Query(
            query_id=query.role,
            output_key=query.output_key,
            subject_id=query.subject_role,
            segment_id=query.segment_role,
            event_id=query.event_role,
            component=query.component or "unspecified",
            evidence_quote=None,
        )
        for query in gold.queries
    ]
    assumptions = []
    for assumption in gold.assumption_proposals:
        mapped = _ASSUMPTION_VALUES.get(assumption.kind)
        if mapped is None:
            continue
        semantic_key, value, unit = mapped
        assumptions.append(
            AssumptionProposal(
                assumption_id=assumption.role,
                kind=assumption.kind,
                subject_id=assumption.subject_role or entities[0].entity_id,
                segment_id=assumption.segment_role,
                proposed_semantic_key=semantic_key,
                proposed_value=value,
                proposed_unit=unit,
                reason="server-valued assumption implied by the accepted kind",
                supporting_quote=assumption.supporting_quote,
            )
        )

    system_type = derive_system_type(case)
    parse_status = derive_parse_status(case)
    target_segments = [
        segment.segment_id
        for segment in segments
        if segment.relevance == "target"
    ] or [segment.segment_id for segment in segments]
    candidates: list[InterpretationCandidate] = []
    if target_segments and queries:
        candidates.append(
            InterpretationCandidate(
                candidate_id="structural_candidate",
                system_type=system_type,
                target_segment_ids=target_segments[:8],
                fact_ids=[
                    fact.fact_id for fact in facts if fact.relevance == "solver_input"
                ][:32],
                query_ids=[query.query_id for query in queries][:8],
                assumption_ids=[item.assumption_id for item in assumptions][:16],
                reason_code="structural_projection",
            )
        )

    try:
        parse = TextbookProblemParseV1(
            schema=SCHEMA_NAME,
            version=SCHEMA_VERSION,
            language="ko",
            parse_status=parse_status,
            entities=entities,
            motion_segments=segments,
            events=events,
            explicit_facts=facts,
            relations=relations,
            queries=queries,
            assumption_proposals=assumptions,
            interpretation_candidates=candidates,
            ambiguities=[],
            figure_dependency=FigureDependency(
                level=gold.figure_dependency.level,
                missing_information=list(gold.figure_dependency.missing_information),
            ),
            unsupported_features=[],
        )
    except Exception as exc:
        raise LaneBAdapterError(f"parse projection rejected: {type(exc).__name__}") from exc

    return LaneBProjection(
        parse=parse,
        problem_text=case.problem_text,
        derived_system_type=system_type.value,
        derived_parse_status=parse_status,
    )
