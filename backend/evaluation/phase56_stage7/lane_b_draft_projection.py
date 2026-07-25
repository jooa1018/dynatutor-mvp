"""Lane B: evaluator-only direct corpus-structure to Draft projection.

The projection reads only source-grounded corpus structure — problem text,
entities, motion segments, events, explicit facts with their evidence quotes,
relations, assumption proposals, queries, and figure dependency — and emits a
`MechanicsProblemDraftV1` for the product pipeline:

    validate_draft → normalize_draft → authorize_validated_mechanics_ir
    → MechanicsCompiler → solve_verified_equation_graph → verification

`case_id`, `family`, `split`, `chapter`, `expected_system_type`, either
expected terminal, `answers`, `expected_failure_codes`, and tolerance are never
read.  The whitelist is enforced in code and proven by tampering tests.

Two corpus structures are preserved rather than flattened:

* **Segment-internal event** — an event carries interval membership through
  `Event.interval_ids` without being disguised as the interval's start or end
  boundary, and a query keeps its subject, interval, and event bindings intact.
* **Relation-scoped timeless environment fact** — an environment entity is
  never promoted to an interval subject.  Its quantity keeps the environment
  entity as `subject_id` and the target interval as `interval_id`, and is only
  admitted when exactly one interval-scoped relation links it to a moving actor
  of that interval.  Ambiguous or cross-interval links are rejected.

Values without exact source evidence never enter the Draft, so an ungrounded
number fails closed as `invented_explicit_number` in `validate_draft`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.textbook_parser.evidence_alignment import (
    _normalized_number,
    _unit_dimension,
    quantity_occurrences,
    quote_occurrences,
)

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1


DRAFT_PROJECTION_VERSION = "phase56-stage7-lane-b-draft-projection-v1"

PERMITTED_CASE_MEMBERS: frozenset[str] = frozenset({"problem_text", "gold"})
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
FORBIDDEN_MEMBERS: frozenset[str] = frozenset(
    {
        "case_id",
        "family",
        "split",
        "chapter",
        "difficulty",
        "tags",
        "source_provenance",
        "problem_hash",
        "parse_status",
        "expected_system_type",
        "phase55_expected_terminal",
        "future_expected_terminal",
        "answers",
        "expected_failure_codes",
    }
)

_M, _L, _T = "mass", "length", "time"


def _dim(mass: int = 0, length: int = 0, time: int = 0) -> dict[str, int]:
    out: dict[str, int] = {}
    if mass:
        out[_M] = mass
    if length:
        out[_L] = length
    if time:
        out[_T] = time
    return out


# corpus semantic key -> (draft quantity role, dimension)
_FACT_ROLES: dict[str, tuple[str, dict[str, int]]] = {
    "acceleration": ("acceleration", _dim(length=1, time=-2)),
    "angle": ("angle", _dim()),
    "angular_acceleration": ("angular_acceleration", _dim(time=-2)),
    "angular_velocity": ("angular_velocity", _dim(time=-1)),
    "background_height": ("height", _dim(length=1)),
    "coefficient_of_friction": ("coefficient_friction", _dim()),
    "displacement": ("displacement", _dim(length=1)),
    "distance": ("distance", _dim(length=1)),
    "duration": ("duration", _dim(time=1)),
    "energy": ("energy", _dim(mass=1, length=2, time=-2)),
    "final_velocity": ("velocity", _dim(length=1, time=-1)),
    "force": ("force", _dim(mass=1, length=1, time=-2)),
    "frequency": ("frequency", _dim(time=-1)),
    "height": ("height", _dim(length=1)),
    "impulse": ("impulse", _dim(mass=1, length=1, time=-1)),
    "initial_velocity": ("velocity", _dim(length=1, time=-1)),
    "mass": ("mass", _dim(mass=1)),
    "mass_1": ("mass", _dim(mass=1)),
    "mass_2": ("mass", _dim(mass=1)),
    "moment_of_inertia": ("moment_of_inertia", _dim(mass=1, length=2)),
    "period": ("period", _dim(time=1)),
    "radius": ("radius", _dim(length=1)),
    "restitution_coefficient": ("coefficient_restitution", _dim()),
    "spring_constant": ("stiffness", _dim(mass=1, time=-2)),
    "time": ("time", _dim(time=1)),
    "torque": ("torque", _dim(mass=1, length=2, time=-2)),
    "velocity": ("velocity", _dim(length=1, time=-1)),
    "velocity_after": ("velocity", _dim(length=1, time=-1)),
    "velocity_before": ("velocity", _dim(length=1, time=-1)),
    "work": ("work", _dim(mass=1, length=2, time=-2)),
}

# corpus query output key -> (draft quantity role, output unit, dimension)
_QUERY_ROLES: dict[str, tuple[str, str, dict[str, int]]] = {
    "acceleration": ("acceleration", "m/s^2", _dim(length=1, time=-2)),
    "angular_acceleration": ("angular_acceleration", "rad/s^2", _dim(time=-2)),
    "angular_frequency": ("angular_velocity", "rad/s", _dim(time=-1)),
    "angular_velocity": ("angular_velocity", "rad/s", _dim(time=-1)),
    "centripetal_acceleration": ("acceleration", "m/s^2", _dim(length=1, time=-2)),
    "distance": ("distance", "m", _dim(length=1)),
    "elastic_energy": ("energy", "J", _dim(mass=1, length=2, time=-2)),
    "final_velocity": ("velocity", "m/s", _dim(length=1, time=-1)),
    "force": ("force", "N", _dim(mass=1, length=1, time=-2)),
    "frequency": ("frequency", "Hz", _dim(time=-1)),
    "friction_force": ("force", "N", _dim(mass=1, length=1, time=-2)),
    "impulse": ("impulse", "N*s", _dim(mass=1, length=1, time=-1)),
    "initial_velocity": ("velocity", "m/s", _dim(length=1, time=-1)),
    "kinetic_energy": ("energy", "J", _dim(mass=1, length=2, time=-2)),
    "mass": ("mass", "kg", _dim(mass=1)),
    "max_height": ("height", "m", _dim(length=1)),
    "minimum_speed": ("speed", "m/s", _dim(length=1, time=-1)),
    "normal_force": ("force", "N", _dim(mass=1, length=1, time=-2)),
    "period": ("period", "s", _dim(time=1)),
    "post_collision_velocity": ("velocity", "m/s", _dim(length=1, time=-1)),
    "potential_energy": ("energy", "J", _dim(mass=1, length=2, time=-2)),
    "range": ("distance", "m", _dim(length=1)),
    "tangential_velocity": ("velocity", "m/s", _dim(length=1, time=-1)),
    "tension": ("force", "N", _dim(mass=1, length=1, time=-2)),
    "time": ("time", "s", _dim(time=1)),
    "v1_after": ("velocity", "m/s", _dim(length=1, time=-1)),
    "v2_after": ("velocity", "m/s", _dim(length=1, time=-1)),
    "work": ("work", "J", _dim(mass=1, length=2, time=-2)),
}

_ENTITY_PRIMITIVES: dict[str, str] = {
    "particle": "particle",
    "rigid_body": "rigid_body",
    "point": "point",
    "system": "system",
    "block": "rigid_body",
    "disk": "rigid_body",
    "sphere": "rigid_body",
    "cylinder": "rigid_body",
    "rod": "rigid_body",
    "pulley": "pulley",
    "rope": "rope",
    "spring": "spring",
    "surface": "surface",
    "incline": "incline",
    "slot": "slot",
    "pin": "joint",
    "vehicle": "rigid_body",
    "person": "particle",
    "reference_frame": "reference_frame",
    "other": "environment",
}

_EVENT_KINDS: dict[str, str] = {
    "start": "start",
    "release": "release",
    "just_before_collision": "other",
    "collision_start": "collision_start",
    "collision_end": "collision_end",
    "just_after_collision": "other",
    "reaches_position": "reaches_condition",
    "reaches_height": "reaches_condition",
    "highest_point": "reaches_condition",
    "lowest_point": "reaches_condition",
    "comes_to_rest": "comes_to_rest",
    "turnaround": "turnaround",
    "contact_lost": "contact_end",
    "rope_taut": "rope_taut",
    "rope_slack": "rope_slack",
    "spring_max_compression": "reaches_condition",
    "finish": "finish",
    "other": "other",
}

_INTERACTION_KINDS: dict[str, str] = {
    "connected_by_rope": "rope_tension",
    "passes_over_pulley": "rope_tension",
    "attached_to_spring": "spring",
    "contact_with": "contact",
    "slides_on": "contact",
    "rolls_on": "contact",
    "fixed_to": "joint_reaction",
    "hinged_at": "joint_reaction",
    "point_on_body": "other",
    "moves_in_slot": "joint_reaction",
    "moves_relative_to": "other",
    "rotates_about": "joint_reaction",
    "collides_with": "collision",
    "shares_velocity_constraint": "other",
    "shares_acceleration_constraint": "other",
}

# Only a physical contact-type coupling can scope an environment property to a
# moving actor's interval.  A rope, collision, or bookkeeping relation cannot.
# 6-A. Closed corpus-direction mapping.  Direction is only carried when the
# source states one: it is never inferred from problem-text keywords, from the
# sign of a number, from a family default, from an expected answer, or from a
# system type.  ``not_applicable`` and ``unspecified`` stay absent.
_SEMANTIC_DIRECTIONS: frozenset[str] = frozenset(
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
# A direction that is also a component of a vector quantity.
_DIRECTION_COMPONENTS: dict[str, str] = {
    "radial": "radial",
    "tangential": "tangential",
    "clockwise": "clockwise",
    "counterclockwise": "counterclockwise",
}

# 6-B. Closed relation split.  Topology and kinematic coupling are geometry;
# only genuine force interactions are interactions.
_GEOMETRY_KINDS: dict[str, str] = {
    "connected_by_rope": "topology_connects",
    "passes_over_pulley": "wraps",
    "slides_on": "lies_on",
    "rolls_on": "tangent",
    "fixed_to": "attached",
    "hinged_at": "coincident",
    "point_on_body": "lies_on",
    "moves_in_slot": "lies_on",
    "moves_relative_to": "topology_connects",
    "rotates_about": "coincident",
}
_INTERACTION_ONLY_KINDS: dict[str, str] = {
    "attached_to_spring": "spring",
    "contact_with": "contact",
    "collides_with": "collision",
}
# No typed constraint contract covers these, so they are reported as a precise
# projection-neutral diagnostic instead of being forced into a generic `other`.
_UNMAPPED_RELATION_KINDS: frozenset[str] = frozenset(
    {"shares_velocity_constraint", "shares_acceleration_constraint"}
)

_ENVIRONMENT_LINK_RELATION_KINDS: frozenset[str] = frozenset(
    {"contact_with", "slides_on", "rolls_on", "moves_in_slot", "rotates_about"}
)

# The closed set of assumption kinds this evaluator may authorise at all.
_CLOSED_ASSUMPTION_KINDS: frozenset[str] = frozenset(
    {
        "constant_gravity",
        "starts_from_rest",
        "ends_at_rest",
        "frictionless",
        "no_air_resistance",
        "massless_rope",
        "inextensible_rope",
        "massless_pulley",
        "pure_rolling",
    }
)

# Kinds whose value is a server default rather than a reader-visible choice.
_SERVER_DEFAULT_ASSUMPTIONS: frozenset[str] = frozenset({"constant_gravity"})

_ASSUMPTION_PROPOSALS: dict[str, tuple[str, str, str]] = {
    "constant_gravity": ("gravity", "9.81", "m/s^2"),
    "starts_from_rest": ("velocity", "0", "m/s"),
    "ends_at_rest": ("velocity", "0", "m/s"),
    "frictionless": ("coefficient_friction", "0", ""),
}

_WHITESPACE = re.compile(r"\s+")


class DraftProjectionTerminal(str, Enum):
    """Neutral pre-runtime terminals; none of them is an engine result."""

    projected = "projected"
    needs_figure = "needs_figure"
    insufficient_information = "insufficient_information"
    projection_rejected = "projection_rejected"


class DraftProjectionReason(str, Enum):
    """Closed, privacy-safe projection rejection catalogue."""

    forbidden_member_read = "forbidden_member_read"
    unmapped_semantic_key = "unmapped_semantic_key"
    unmapped_query_output_key = "unmapped_query_output_key"
    unmapped_entity_kind = "unmapped_entity_kind"
    unmapped_event_kind = "unmapped_event_kind"
    unmapped_relation_kind = "unmapped_relation_kind"
    relation_kind_has_no_typed_contract = "relation_kind_has_no_typed_contract"
    assumption_not_authorized = "assumption_not_authorized"
    evidence_quote_not_found = "evidence_quote_not_found"
    evidence_value_not_in_quote = "evidence_value_not_in_quote"
    evidence_quote_occurrence_ambiguous = "evidence_quote_occurrence_ambiguous"
    evidence_quantity_occurrence_ambiguous = "evidence_quantity_occurrence_ambiguous"
    evidence_unit_dimension_mismatch = "evidence_unit_dimension_mismatch"
    missing_evidence_for_explicit_value = "missing_evidence_for_explicit_value"
    environment_relation_ambiguous = "environment_relation_ambiguous"
    environment_relation_absent = "environment_relation_absent"
    environment_relation_kind_not_contact = "environment_relation_kind_not_contact"
    environment_relation_cross_interval = "environment_relation_cross_interval"
    dangling_entity_reference = "dangling_entity_reference"
    dangling_interval_reference = "dangling_interval_reference"
    dangling_event_reference = "dangling_event_reference"
    draft_contract_rejected = "draft_contract_rejected"


class DraftProjectionError(ValueError):
    """Fail-closed projection rejection carrying no corpus content."""

    def __init__(self, reason: DraftProjectionReason, *, detail: str | None = None) -> None:
        message = reason.value if detail is None else f"{reason.value}[{detail}]"
        super().__init__(message)
        self.reason = reason

    @property
    def sanitized_reason(self) -> str:
        return str(self)


@dataclass(frozen=True, slots=True)
class DraftProjection:
    terminal: DraftProjectionTerminal
    problem_text: str
    draft: MechanicsProblemDraftV1 | None = None
    sanitized_reason: str | None = None
    environment_scoped_quantity_ids: tuple[str, ...] = ()
    segment_internal_event_ids: tuple[str, ...] = ()
    approvable_assumption_ids: tuple[str, ...] = ()

    @property
    def projected(self) -> bool:
        return self.terminal is DraftProjectionTerminal.projected


def _normalize(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


_ASSUMPTION_REASONS: dict[str, str] = {
    "approved": "closed server policy: source-grounded, uncontested, exact value",
    "visible": "server-valued default made visible to the reader",
    "proposed": "reader confirmation required before this assumption may close",
    "rejected": "no closed server policy authorises this assumption",
}


def _authorize_assumption(
    *,
    assumption: Any,
    problem_text: str,
    proposal: tuple[str, str, str] | None,
    explicit_roles: "Counter[str]",
) -> tuple[str, str]:
    """Classify one corpus assumption under a closed evaluator-only policy.

    Approval requires a closed kind plus either an explicitly permitted server
    default or a supporting quote that actually occurs in the source.  A
    competing explicit fact for the same role outranks the assumption.  A
    structural idealisation carries no proposed value; it is still authorised
    on the same grounds, it simply contributes no quantity.  Anything
    ungrounded stays `proposed`, which means reader confirmation is required
    and the assumption may not close the graph.
    """

    assumption_id = f"asm_{assumption.role}"
    if assumption.kind not in _CLOSED_ASSUMPTION_KINDS:
        return ("rejected", assumption_id)
    if proposal is not None and explicit_roles.get(proposal[0], 0) > 0:
        # An explicit source fact outranks the assumption for this role.
        return ("rejected", assumption_id)
    if assumption.kind in _SERVER_DEFAULT_ASSUMPTIONS:
        return ("approved", assumption_id)
    quote = assumption.supporting_quote
    if quote and quote in problem_text:
        return ("approved", assumption_id)
    return ("proposed", assumption_id)


def _direction_fields(direction: str | None) -> dict[str, Any]:
    """Carry a source-stated direction into the typed Draft fields.

    A quantity whose source states no direction receives none: the absence is
    preserved rather than filled with a default.
    """

    if direction is None or direction not in _SEMANTIC_DIRECTIONS:
        return {}
    fields: dict[str, Any] = {
        "direction": {"kind": "semantic", "direction": direction}
    }
    component = _DIRECTION_COMPONENTS.get(direction)
    if component is not None:
        fields["component"] = component
    return fields


@dataclass(frozen=True, slots=True)
class _FactAlignment:
    """Immutable alignment result; the resolved indices are authoritative."""

    quote_span: tuple[int, int]
    quantity_span: tuple[int, int]
    written_value: str
    written_unit: str
    resolved_quote_index: int
    resolved_quantity_index: int


def _align_fact_evidence(problem_text: str, fact: Any) -> _FactAlignment:
    """Align one corpus fact onto the source using Phase 55 evidence alignment.

    Reuses the product ``quote_occurrences`` / ``quantity_occurrences`` grammar
    rather than a second, looser parser.  The corpus records a canonical unit
    name while the sentence writes a symbol or a Korean word, so the value/unit
    pair that enters the Draft is the one *written in the source*, and the
    corpus unit is only used to require dimensional agreement.
    """

    quote = fact.evidence_quote
    occurrences = quote_occurrences(problem_text, quote)
    if not occurrences:
        raise DraftProjectionError(DraftProjectionReason.evidence_quote_not_found)
    index = fact.occurrence_index
    if not isinstance(index, int) or not 0 <= index < len(occurrences):
        if len(occurrences) != 1:
            raise DraftProjectionError(
                DraftProjectionReason.evidence_quote_occurrence_ambiguous
            )
        index = 0
    occurrence = occurrences[index]

    candidates = [
        item
        for item in quantity_occurrences(quote)
        if _normalized_number(item.raw_value) == _normalized_number(fact.raw_value)
    ]
    if not candidates:
        raise DraftProjectionError(DraftProjectionReason.evidence_value_not_in_quote)

    # The corpus unit is only a cross-check, and only when the shared alias
    # table actually knows it.  An unknown corpus spelling must not reject a
    # correctly written source unit: the Draft still declares an explicit
    # dimension vector, and validate_draft enforces it independently.
    declared_dimension = _unit_dimension(fact.raw_unit or "")
    if fact.raw_unit and declared_dimension is not None:
        dimensioned = [
            item
            for item in candidates
            if _unit_dimension(item.raw_unit) == declared_dimension
        ]
        if not dimensioned:
            raise DraftProjectionError(
                DraftProjectionReason.evidence_unit_dimension_mismatch
            )
        pool = dimensioned
    else:
        pool = candidates

    quantity_index = fact.quantity_occurrence_index
    if not isinstance(quantity_index, int) or not 0 <= quantity_index < len(pool):
        if len(pool) != 1:
            raise DraftProjectionError(
                DraftProjectionReason.evidence_quantity_occurrence_ambiguous
            )
        quantity_index = 0
    quantity = pool[quantity_index]

    return _FactAlignment(
        quote_span=(occurrence.start, occurrence.end),
        quantity_span=(
            occurrence.start + quantity.start,
            occurrence.start + quantity.end,
        ),
        written_value=quantity.raw_value,
        written_unit=quantity.raw_unit,
        resolved_quote_index=index,
        resolved_quantity_index=quantity_index,
    )


def _assert_whitelist(case: PublicCorpusCaseV1) -> None:
    if PERMITTED_CASE_MEMBERS & FORBIDDEN_MEMBERS:
        raise DraftProjectionError(DraftProjectionReason.forbidden_member_read)
    if PERMITTED_GOLD_MEMBERS & FORBIDDEN_MEMBERS:
        raise DraftProjectionError(DraftProjectionReason.forbidden_member_read)


def project_case_to_draft(case: PublicCorpusCaseV1) -> DraftProjection:
    """Project one corpus case's source-grounded structure into a Draft."""

    _assert_whitelist(case)
    gold = case.gold
    problem_text = case.problem_text

    if gold.figure_dependency.level.casefold() == "required":
        return DraftProjection(
            terminal=DraftProjectionTerminal.needs_figure, problem_text=problem_text
        )
    if not gold.queries:
        return DraftProjection(
            terminal=DraftProjectionTerminal.insufficient_information,
            problem_text=problem_text,
        )

    try:
        payload, environment_ids, internal_events, assumption_ids = _build_payload(
            gold, problem_text
        )
    except DraftProjectionError as exc:
        return DraftProjection(
            terminal=DraftProjectionTerminal.projection_rejected,
            problem_text=problem_text,
            sanitized_reason=exc.sanitized_reason,
        )

    try:
        draft = MechanicsProblemDraftV1.model_validate(payload)
    except Exception as exc:
        return DraftProjection(
            terminal=DraftProjectionTerminal.projection_rejected,
            problem_text=problem_text,
            sanitized_reason=DraftProjectionError(
                DraftProjectionReason.draft_contract_rejected,
                detail=type(exc).__name__,
            ).sanitized_reason,
        )

    return DraftProjection(
        terminal=DraftProjectionTerminal.projected,
        problem_text=problem_text,
        draft=draft,
        environment_scoped_quantity_ids=environment_ids,
        segment_internal_event_ids=internal_events,
        approvable_assumption_ids=assumption_ids,
    )


def _build_payload(
    gold: Any, problem_text: str
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    entity_ids = {entity.role for entity in gold.entities}
    interval_ids = {segment.role for segment in gold.motion_segments}
    event_ids = {event.role for event in gold.events}

    entities: list[dict[str, Any]] = []
    for entity in gold.entities:
        primitive = _ENTITY_PRIMITIVES.get(entity.kind)
        if primitive is None:
            raise DraftProjectionError(DraftProjectionReason.unmapped_entity_kind)
        entities.append(
            {
                "entity_id": entity.role,
                "primitive": primitive,
                "label": entity.label or entity.role,
                "aliases": [],
                "evidence_refs": [],
            }
        )

    intervals: list[dict[str, Any]] = []
    actors_by_interval: dict[str, set[str]] = {}
    for segment in gold.motion_segments:
        for actor in segment.actor_roles:
            if actor not in entity_ids:
                raise DraftProjectionError(
                    DraftProjectionReason.dangling_entity_reference
                )
        actors_by_interval[segment.role] = set(segment.actor_roles)
        intervals.append(
            {
                "interval_id": segment.role,
                "order": segment.order,
                "subject_ids": list(segment.actor_roles),
                # Boundaries are only declared when the corpus materialises the
                # event; a missing boundary stays absent rather than being
                # invented from a mid-interval event.
                "start_event_id": segment.start_event_role
                if segment.start_event_role in event_ids
                else None,
                "end_event_id": segment.end_event_role
                if segment.end_event_role in event_ids
                else None,
                "evidence_refs": [],
            }
        )

    # Segment-internal events keep interval membership without being promoted
    # to boundaries.
    boundary_ids: set[str] = set()
    for segment in gold.motion_segments:
        for role in (segment.start_event_role, segment.end_event_role):
            if role in event_ids:
                boundary_ids.add(role)

    events: list[dict[str, Any]] = []
    segment_internal: list[str] = []
    for event in gold.events:
        kind = _EVENT_KINDS.get(event.kind)
        if kind is None:
            raise DraftProjectionError(DraftProjectionReason.unmapped_event_kind)
        for subject in event.subject_roles:
            if subject not in entity_ids:
                raise DraftProjectionError(
                    DraftProjectionReason.dangling_entity_reference
                )
        membership: list[str] = []
        if event.segment_role is not None:
            if event.segment_role not in interval_ids:
                raise DraftProjectionError(
                    DraftProjectionReason.dangling_interval_reference
                )
            membership.append(event.segment_role)
            if event.role not in boundary_ids:
                segment_internal.append(event.role)
        events.append(
            {
                "event_id": event.role,
                "kind": kind,
                "subject_ids": list(event.subject_roles),
                "interval_ids": membership,
                "evidence_refs": [],
            }
        )

    source_evidence: list[dict[str, Any]] = []
    quantities: list[dict[str, Any]] = []
    environment_scoped: list[str] = []
    relations_by_pair = _interval_scoped_relations(gold, interval_ids, entity_ids)

    for index, fact in enumerate(gold.explicit_facts):
        mapped = _FACT_ROLES.get(fact.semantic_key)
        if mapped is None:
            raise DraftProjectionError(DraftProjectionReason.unmapped_semantic_key)
        role, dimension = mapped
        if fact.subject_role not in entity_ids:
            raise DraftProjectionError(DraftProjectionReason.dangling_entity_reference)
        if fact.segment_role is not None and fact.segment_role not in interval_ids:
            raise DraftProjectionError(
                DraftProjectionReason.dangling_interval_reference
            )
        if fact.event_role is not None and fact.event_role not in event_ids:
            raise DraftProjectionError(DraftProjectionReason.dangling_event_reference)
        if fact.evidence_quote is None:
            raise DraftProjectionError(
                DraftProjectionReason.missing_evidence_for_explicit_value
            )

        interval_id = fact.segment_role
        if interval_id is not None:
            actors = actors_by_interval.get(interval_id, set())
            if fact.subject_role not in actors:
                _assert_environment_link(
                    subject=fact.subject_role,
                    interval_id=interval_id,
                    actors=actors,
                    relations_by_pair=relations_by_pair,
                )
                environment_scoped.append(f"qty_{fact.role}")

        alignment = _align_fact_evidence(problem_text, fact)
        quote_span = alignment.quote_span
        value_span = alignment.quantity_span
        written_value = alignment.written_value
        written_unit = alignment.written_unit
        evidence_id = f"ev_{index}_{fact.role}"
        source_evidence.append(
            {
                "evidence_id": evidence_id,
                "kind": "text",
                "quote": problem_text[quote_span[0] : quote_span[1]],
                # The resolved index is recorded, never the original one that
                # alignment may have had to correct.
                "occurrence_index": alignment.resolved_quote_index,
                "source_span": {"start": quote_span[0], "end": quote_span[1]},
                "quantity_span": {"start": value_span[0], "end": value_span[1]},
            }
        )
        quantities.append(
            {
                "quantity_id": f"qty_{fact.role}",
                "role": role,
                "subject_id": fact.subject_role,
                "interval_id": interval_id,
                "event_id": fact.event_role,
                "shape": "scalar",
                "dimension": dimension,
                "provenance": "explicit_source",
                "raw_value": written_value,
                "raw_unit": written_unit,
                "evidence_refs": [evidence_id],
                **_direction_fields(fact.direction),
            }
        )

    interactions: list[dict[str, Any]] = []
    geometry: list[dict[str, Any]] = []
    for relation in gold.relations:
        if relation.kind in _UNMAPPED_RELATION_KINDS:
            raise DraftProjectionError(
                DraftProjectionReason.relation_kind_has_no_typed_contract
            )
        for participant in relation.participant_roles:
            if participant not in entity_ids:
                raise DraftProjectionError(
                    DraftProjectionReason.dangling_entity_reference
                )
        if relation.segment_role is not None and relation.segment_role not in interval_ids:
            raise DraftProjectionError(
                DraftProjectionReason.dangling_interval_reference
            )
        # Participant order and role are preserved exactly as authored, so a
        # pulley stays the pulley and a rope topology keeps its endpoints.
        if relation.kind in _GEOMETRY_KINDS:
            geometry.append(
                {
                    "relation_id": f"geo_{relation.role}",
                    "kind": _GEOMETRY_KINDS[relation.kind],
                    "participant_ids": list(relation.participant_roles),
                    "interval_id": relation.segment_role,
                    "evidence_refs": [],
                }
            )
            continue
        kind = _INTERACTION_ONLY_KINDS.get(relation.kind)
        if kind is None:
            raise DraftProjectionError(DraftProjectionReason.unmapped_relation_kind)
        interactions.append(
            {
                "interaction_id": f"rel_{relation.role}",
                "kind": kind,
                "participant_ids": list(relation.participant_roles),
                "interval_id": relation.segment_role,
                "evidence_refs": [],
            }
        )

    # 6-C. An assumption is authorised only by the closed policy below.  The
    # mere presence of a corpus proposal never approves it.
    explicit_roles_by_subject: dict[str, Counter[str]] = {}
    for item in quantities:
        explicit_roles_by_subject.setdefault(item["subject_id"], Counter())[
            item["role"]
        ] += 1

    assumptions: list[dict[str, Any]] = []
    approved: list[str] = []
    for assumption in gold.assumption_proposals:
        subject = assumption.subject_role or entities[0]["entity_id"]
        if subject not in entity_ids:
            raise DraftProjectionError(DraftProjectionReason.dangling_entity_reference)
        interval_id = (
            assumption.segment_role if assumption.segment_role in interval_ids else None
        )
        if assumption.segment_role is not None and interval_id is None:
            raise DraftProjectionError(
                DraftProjectionReason.dangling_interval_reference
            )
        proposal = _ASSUMPTION_PROPOSALS.get(assumption.kind)
        disposition, assumption_id = _authorize_assumption(
            assumption=assumption,
            problem_text=problem_text,
            proposal=proposal,
            explicit_roles=explicit_roles_by_subject.get(subject, Counter()),
        )
        entry: dict[str, Any] = {
            "assumption_id": assumption_id,
            "kind": assumption.kind,
            "subject_id": subject,
            "interval_id": interval_id,
            "disposition": disposition,
            "reason": _ASSUMPTION_REASONS[disposition],
            "evidence_refs": [],
        }
        if proposal is not None and disposition != "rejected":
            role, value, unit = proposal
            entry["proposed_role"] = role
            entry["proposed_value"] = value
            entry["proposed_unit"] = unit
        assumptions.append(entry)
        if disposition == "approved":
            approved.append(assumption_id)

    queries: list[dict[str, Any]] = []
    for query in gold.queries:
        mapped_query = _QUERY_ROLES.get(query.output_key)
        if mapped_query is None:
            raise DraftProjectionError(
                DraftProjectionReason.unmapped_query_output_key
            )
        role, unit, dimension = mapped_query
        if query.subject_role not in entity_ids:
            raise DraftProjectionError(DraftProjectionReason.dangling_entity_reference)
        if query.segment_role is not None and query.segment_role not in interval_ids:
            raise DraftProjectionError(
                DraftProjectionReason.dangling_interval_reference
            )
        if query.event_role is not None and query.event_role not in event_ids:
            raise DraftProjectionError(DraftProjectionReason.dangling_event_reference)
        queries.append(
            {
                "query_id": f"qry_{query.role}",
                "output_unit": unit,
                "output_dimension": dimension,
                "shape": "scalar",
                "target": {
                    "role": role,
                    "subject_id": query.subject_role,
                    "interval_id": query.segment_role,
                    "event_id": query.event_role,
                    "component": query.component or "unspecified",
                },
                "evidence_refs": [],
            }
        )

    payload = {
        "schema": DRAFT_SCHEMA_NAME,
        "version": DRAFT_SCHEMA_VERSION,
        "metadata": {"language": "ko", "correction_revision": 0},
        "source_assets": [],
        "source_evidence": source_evidence,
        "entities": entities,
        "points": [],
        "reference_frames": [],
        "motion_intervals": intervals,
        "events": events,
        "quantities": quantities,
        "symbols": [],
        "geometry": geometry,
        "interactions": interactions,
        "constraints": [],
        "state_conditions": [],
        "queries": queries,
        "principle_hints": [],
        "assumptions": assumptions,
        "ambiguities": [],
        "figure_dependency": {
            "level": gold.figure_dependency.level,
            "missing_information": list(gold.figure_dependency.missing_information),
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }
    return (
        payload,
        tuple(environment_scoped),
        tuple(segment_internal),
        tuple(approved),
    )


def _interval_scoped_relations(
    gold: Any, interval_ids: set[str], entity_ids: set[str]
) -> dict[tuple[str, str], list[str]]:
    """Index interval-scoped relations by unordered participant pair."""

    index: dict[tuple[str, str], list[str]] = {}
    for relation in gold.relations:
        if relation.segment_role is None or relation.segment_role not in interval_ids:
            continue
        if relation.kind not in _ENVIRONMENT_LINK_RELATION_KINDS:
            continue
        participants = [p for p in relation.participant_roles if p in entity_ids]
        for first in participants:
            for second in participants:
                if first == second:
                    continue
                index.setdefault((first, second), []).append(relation.segment_role)
    return index


def _assert_environment_link(
    *,
    subject: str,
    interval_id: str,
    actors: set[str],
    relations_by_pair: Mapping[tuple[str, str], list[str]],
) -> None:
    """Admit an environment-scoped fact only on one unambiguous interval link.

    The environment entity is never added to the interval's subjects.  It is
    admitted only when exactly one interval-scoped relation ties it to a moving
    actor of that same interval.
    """

    matching: list[str] = []
    cross_interval = False
    for actor in actors:
        scopes = relations_by_pair.get((subject, actor), [])
        for scope in scopes:
            if scope == interval_id:
                matching.append(actor)
            else:
                cross_interval = True
    if not matching:
        if cross_interval:
            raise DraftProjectionError(
                DraftProjectionReason.environment_relation_cross_interval
            )
        raise DraftProjectionError(DraftProjectionReason.environment_relation_absent)
    if len(matching) > 1:
        raise DraftProjectionError(
            DraftProjectionReason.environment_relation_ambiguous
        )
