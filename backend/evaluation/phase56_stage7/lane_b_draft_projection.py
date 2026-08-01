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

* **Segment-internal event** — an event that occurs inside a segment without
  bounding it is never promoted to that segment's start or end boundary.
  `Event.interval_ids` is the typed reciprocal of an interval's own boundary
  declaration, so a segment-internal event declares none there; its provable
  occupancy is preserved separately in `Event.occurs_in_interval_ids`, and
  records that reference the event keep both the precise instant scope and
  the occupied interval without ever restating a boundary the source never
  declared.
* **Relation-scoped timeless environment fact** — an environment entity is
  never promoted to an interval subject.  Its quantity keeps the environment
  entity as `subject_id` and stays timeless, and is only admitted when exactly
  one interval-scoped relation links it to a moving actor of the interval the
  corpus scoped it to.  Ambiguous or cross-interval links are rejected.

Values without exact source evidence never enter the Draft, so an ungrounded
number fails closed as `invented_explicit_number` in `validate_draft`.

Every quantity carries a typed `SymbolDefinition` whose identity is the
*canonical physical identity* of that quantity — role, subject, point, frame,
interval, event, component, direction, shape, and dimension — and never its
value, its corpus ID, its position in an array, or anything from the gold
domain.  `quantity.symbol_id` and `symbol.quantity_id` are reciprocated and
one-to-one, so the Equation Graph can bind a symbol per quantity.  The query
target additionally receives its own *unknown* symbol, separate from every
known symbol, which is what the graph has to solve for.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from engine.mechanics.contracts import (
    DRAFT_SCHEMA_NAME,
    DRAFT_SCHEMA_VERSION,
    MechanicsProblemDraftV1,
)
from engine.mechanics.laws.event_boundary import NUMERIC_LICENSING_EVENT_KINDS
from engine.textbook_parser.evidence_alignment import (
    _normalized_number,
    _unit_dimension,
    quantity_occurrences,
    quote_occurrences,
)

from evaluation.phase56_stage7.corpus_records import PublicCorpusCaseV1
from evaluation.phase56_stage7.query_objective_sources import (
    QUERY_OBJECTIVE_OUTPUT_KEYS,
)


DRAFT_PROJECTION_VERSION = "phase56-stage7-lane-b-draft-projection-v9"

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

# A `time` fact the corpus scopes to a whole segment is an *elapsed* time, and
# the typed IR names that `duration`.  The distinction comes from the corpus's
# own `temporal_role`, never from the sentence and never from a family.
_INTERVAL_TEMPORAL_ROLES: frozenset[str] = frozenset({"interval", "during"})

# A source that says *initial* or *final* has named an instant, not the whole
# interval.  Collapsing both onto the bare interval would make "the speed it
# started with" and "the speed it ended with" the same physical quantity, so the
# stated endpoint is bound to the boundary the interval itself declares.  The
# signal is the corpus's own temporal_role for a fact and its own output key for
# a query; neither reads problem text, a family, or an expected answer.
_ENDPOINT_TEMPORAL_ROLES: dict[str, str] = {
    "initial": "start_event_id",
    "final": "end_event_id",
}
_ENDPOINT_QUERY_KEYS: dict[str, str] = {
    "initial_velocity": "start_event_id",
    "final_velocity": "end_event_id",
}
_ELAPSED_ROLES: dict[str, tuple[str, dict[str, int]]] = {
    "time": ("duration", _dim(time=1)),
}
# The query-side mirror of `_ELAPSED_ROLES`.  A `time` question is an elapsed
# duration exactly when the typed structure proves it: the queried segment's
# interval declares both boundaries, they are distinct physical events, and
# the question names either no event or precisely that interval's own end.
# The duration is defined *relationally* by the two boundary events — no
# epoch, no invented t0 — which is the same object the constant-acceleration
# laws multiply and the same rule the fact side already applies.
_ELAPSED_QUERY_KEYS: dict[str, tuple[str, str, dict[str, int]]] = {
    "time": ("duration", "s", _dim(time=1)),
}

# 6-B/7. Closed corpus motion-model mapping.  A motion model is source-declared
# segment structure, so the typed assumption it implies is a structural
# derivation rather than an invention.  Only models whose kinematic meaning is
# unambiguous appear here; anything else contributes no assumption and stays
# precisely unsupported instead of being guessed.
_MOTION_MODEL_ASSUMPTIONS: dict[str, str] = {
    "constant_acceleration_1d": "constant_acceleration",
    "constant_velocity_1d": "constant_velocity",
    "projectile_free_flight": "constant_acceleration",
    # A source-declared oscillation names the regime whose typed readout
    # authority the engine already carries.  It supplies no number: the
    # authority only says which regime the segment is in, and the engine then
    # decides from its own capability whether that readout is in scope.
    "spring_oscillation": "angular_natural_frequency",
}

# An authority that licenses one readout is emitted only when that readout is
# what the source asks for.  `angular_natural_frequency` is the case in point:
# it is what lets the engine relate a natural frequency to a mass and a
# stiffness, so a question about anything else has no business carrying it.
# Without this the authority would sit in every oscillation Draft and could
# combine with an unrelated frequency quantity to write an equation the source
# never asked for.
_QUERY_SCOPED_MOTION_MODEL_ASSUMPTIONS: dict[str, frozenset[str]] = {
    # assumption kind -> query roles that may carry it
    "angular_natural_frequency": frozenset({"period", "frequency"}),
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

# A query output key that states an extremal objective keeps it.  The corpus's
# own `minimum_speed` asks for an admissible-set boundary, not an exact value;
# collapsing it onto a plain speed question silently changed what was asked,
# which is how a boundary equality once fired for a question that never proved
# the boundary.  The typed objective travels on the Draft query so every
# downstream reader either honours it or declines.  No problem text, family,
# case identity, or expected answer participates.  The table itself lives in
# `query_objective_sources` so the semantic-preservation audit classifies the
# exact vocabulary this projection consumes rather than a copy of it.
_QUERY_OBJECTIVES: Mapping[str, str] = QUERY_OBJECTIVE_OUTPUT_KEYS

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
    # The extremum kinds are preserved, not collapsed: `highest_point` and
    # `lowest_point` carry boundary physics (vertical velocity component zero
    # at a smooth extremum) that a generic `reaches_condition` cannot state.
    "highest_point": "highest_point",
    "lowest_point": "lowest_point",
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

# A source that says a quantity's direction is *not applicable* has said which
# component it stated: the magnitude.  That is a different statement from
# `unspecified`, which says the direction exists but the source did not give it,
# and which therefore stays uncommitted.  The distinction matters because the
# typed laws pair a quantity only with another of the same component: an
# uncommitted scalar and a magnitude are not interchangeable.
_DIRECTIONLESS_COMPONENT = "magnitude"
# The roles for which a component is part of the physical identity.  A role that
# carries no component at all (mass, radius, duration, ...) is left untouched:
# stamping a component on a scalar invariant would invent identity.
_COMPONENT_ROLES: frozenset[str] = frozenset(
    {
        "acceleration",
        "angular_acceleration",
        "angular_momentum",
        "angular_position",
        "angular_velocity",
        "displacement",
        "force",
        "impulse",
        "moment",
        "momentum",
        "position",
        "speed",
        "torque",
        "velocity",
    }
)

# 7. A path length measured over a whole interval is that interval's
# displacement magnitude exactly when the interval's own typed model forbids a
# direction reversal inside it.  Two typed proofs are available, and nothing
# else counts:
#
#   * an approved `constant_velocity` interval never reverses at all; and
#   * an approved `constant_acceleration` interval that a boundary condition
#     pins to rest at its start cannot reverse either, because v(t) = a*t keeps
#     one sign for the whole interval.
#
# Absent one of those proofs the path length stays a `distance`, which no law
# reads, so an interval that may double back fails closed instead of answering
# with a displacement it cannot justify.
_PATH_LENGTH_ROLE = "distance"
_REVERSAL_FREE_ASSUMPTIONS: frozenset[str] = frozenset(
    {"constant_velocity", "constant_acceleration"}
)
_REST_PINNED_ASSUMPTIONS: frozenset[str] = frozenset({"constant_acceleration"})
# A path length carries no component of its own, but it is a magnitude by
# construction, so an undirected one records that component and keeps it if it
# later takes its typed home as a displacement.  A path length the source *did*
# give a direction keeps that direction and never claims to be a magnitude.
_MAGNITUDE_WHEN_DIRECTIONLESS: frozenset[str] = _COMPONENT_ROLES | {_PATH_LENGTH_ROLE}

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

# A constitutive parameter the source states on the *passive* side of a typed
# interaction belongs, under the engine's own accepted convention, to the body
# that interaction acts on: the accepted engine fixtures subject a spring's
# stiffness to the oscillating body, never to the spring entity.  The binding
# is admitted only when exactly one typed interaction of an owning kind ties the
# stated subject to exactly one body-like counterpart.  Nothing is invented —
# the value, unit, evidence, and interval are the source's own; only the typed
# owner the engine requires is resolved.  Anything ambiguous fails closed.
_INTERACTION_OWNED_CONSTITUTIVE_ROLES: dict[str, frozenset[str]] = {
    # corpus relation kind -> quantity roles that relation owns
    "attached_to_spring": frozenset({"stiffness"}),
    # A friction coefficient stated on the support surface belongs, under the
    # same accepted engine convention, to the body that slides on it.
    "slides_on": frozenset({"coefficient_friction"}),
}
# Primitives that can carry a constitutive parameter as their own property.
_CONSTITUTIVE_OWNER_PRIMITIVES: frozenset[str] = frozenset(
    {"particle", "rigid_body", "mass_center", "body_component", "system"}
)
# Primitives a body can slide along.  A point on a body or a pin in a slot also
# `lies_on` something, but neither is a support contact with a friction regime.
_SUPPORT_PRIMITIVES: frozenset[str] = frozenset({"surface", "incline"})
_SLIDING_SUPPORT_GEOMETRY_KIND = "lies_on"
# Assumption kinds that settle a sliding contact's friction regime outright.
_FRICTION_REGIME_ASSUMPTIONS: frozenset[str] = frozenset(
    {"frictionless", "pure_rolling"}
)
# Components whose answer is a signed number rather than a magnitude.
_SIGNED_AXIS_COMPONENTS: frozenset[str] = frozenset({"x", "y", "z"})

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
        "fixed_pulley",
        "ideal_massless_frictionless_pulley",
        "pure_rolling",
    }
)

# Kinds whose value is a server default rather than a reader-visible choice.
_SERVER_DEFAULT_ASSUMPTIONS: frozenset[str] = frozenset({"constant_gravity"})

# A rest assumption is a *boundary condition*, not a supplied number.  The typed
# IR expresses it as a StateCondition at the interval boundary the corpus names,
# which pins that instant's own unknown velocity to zero through the reusable
# `state_at_rest` law.  Nothing is fabricated as a known value: the constraint
# carries the authority and the solver derives the number.
_REST_STATE_CONDITIONS: dict[str, tuple[str, str]] = {
    # corpus assumption kind -> (typed state kind, interval boundary slot)
    "starts_from_rest": ("initial", "start_event_id"),
    "ends_at_rest": ("final", "end_event_id"),
}
_VELOCITY_DIMENSION: dict[str, int] = _dim(length=1, time=-1)

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
    interaction_owner_ambiguous = "interaction_owner_ambiguous"
    environment_relation_absent = "environment_relation_absent"
    environment_relation_kind_not_contact = "environment_relation_kind_not_contact"
    environment_relation_cross_interval = "environment_relation_cross_interval"
    dangling_entity_reference = "dangling_entity_reference"
    dangling_interval_reference = "dangling_interval_reference"
    dangling_event_reference = "dangling_event_reference"
    boundary_event_subject_not_in_interval = "boundary_event_subject_not_in_interval"
    duplicate_motion_model_assumption = "duplicate_motion_model_assumption"
    duplicate_canonical_symbol = "duplicate_canonical_symbol"
    symbol_binding_not_reciprocal = "symbol_binding_not_reciprocal"
    unknown_symbol_collides_with_known = "unknown_symbol_collides_with_known"
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
    known_symbol_ids: tuple[str, ...] = ()
    unknown_symbol_ids: tuple[str, ...] = ()
    # Licensing events whose source authority could not be proven, as
    # `(event_id, reason)` pairs over a closed reason vocabulary
    # (`missing_quote`, `quote_not_found`, `quote_ambiguous`).  The events
    # themselves stay in the Draft; only their equation licence is withheld.
    event_authority_gaps: tuple[tuple[str, str], ...] = ()

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


def _locate_quote(problem_text: str, quote: str | None) -> tuple[int, int] | None:
    """Resolve one supporting quote to its exact, unambiguous source span.

    Reuses the same Phase 55 occurrence grammar the fact path uses.  An absent
    or ambiguous quote yields no span, and the caller then emits no evidence and
    no state condition rather than guessing which occurrence was meant.
    """

    if not quote:
        return None
    occurrences = quote_occurrences(problem_text, quote)
    if len(occurrences) != 1:
        return None
    occurrence = occurrences[0]
    return (occurrence.start, occurrence.end)


_DIRECT_CONSTANT_FORCE_WORK_ASSUMPTION_ID = (
    "asm_closure_direct_constant_force_work"
)


def _derive_direct_constant_force_work_assumption(
    *,
    gold: Any,
    entities: list[dict[str, Any]],
    motion_intervals: list[dict[str, Any]],
    quantities: list[dict[str, Any]],
    assumptions: list[dict[str, Any]],
    approved: list[str],
) -> None:
    """Authorise one force value over one exact source-declared energy interval.

    The policy consumes only source-side typed structure: one actor, one bounded
    ``energy_interval``, one force fact whose temporal scope is ``during`` and
    whose direction is ``along_motion``, one whole-interval distance fact, and
    one magnitude work query for that same actor and interval.  That structure
    states one force value for the whole interval; no sentence keyword, case
    identity, family, expected terminal, reference result, or numeric answer is
    read.

    The assumption contributes no value.  It only licenses the existing
    ``force_work`` law to consume the source's own force and path-length values.
    Any extra force, path value, relation, event, proposal, actor, or query makes
    the shape inexact and the derivation refuses.
    """

    if (
        len(entities) != 1
        or len(motion_intervals) != 1
        or len(gold.motion_segments) != 1
        or gold.relations
        or gold.assumption_proposals
        or len(gold.queries) != 1
        or len(gold.explicit_facts) != 2
    ):
        return
    entity_id = entities[0]["entity_id"]
    if entities[0]["primitive"] not in {"particle", "rigid_body", "body_component"}:
        return
    segment = gold.motion_segments[0]
    interval = motion_intervals[0]
    boundary_events = {item.role: item for item in gold.events}
    if (
        len(boundary_events) != 2
        or set(boundary_events)
        != {segment.start_event_role, segment.end_event_role}
    ):
        return
    start_event = boundary_events[segment.start_event_role]
    end_event = boundary_events[segment.end_event_role]
    if (
        start_event.kind != "start"
        or end_event.kind != "finish"
        or start_event.segment_role != segment.role
        or end_event.segment_role != segment.role
        or tuple(start_event.subject_roles) != tuple(segment.actor_roles)
        or tuple(end_event.subject_roles) != tuple(segment.actor_roles)
    ):
        return
    if (
        segment.motion_model != "energy_interval"
        or tuple(segment.actor_roles) != (entity_id,)
        or segment.role != interval["interval_id"]
        or interval["subject_ids"] != [entity_id]
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval["start_event_id"] == interval["end_event_id"]
    ):
        return
    query = gold.queries[0]
    if (
        query.output_key != "work"
        or query.subject_role != entity_id
        or query.segment_role != interval["interval_id"]
        or query.component != "magnitude"
        or query.event_role is not None
    ):
        return

    force_facts = tuple(
        fact
        for fact in gold.explicit_facts
        if fact.semantic_key == "force"
        and fact.subject_role == entity_id
        and fact.segment_role == interval["interval_id"]
        and fact.event_role is None
        and fact.temporal_role == "during"
        and fact.direction == "along_motion"
    )
    distance_facts = tuple(
        fact
        for fact in gold.explicit_facts
        if fact.semantic_key == "distance"
        and fact.subject_role == entity_id
        and fact.segment_role == interval["interval_id"]
        and fact.event_role is None
        and fact.temporal_role == "interval"
        and fact.direction == "not_applicable"
    )
    if len(force_facts) != 1 or len(distance_facts) != 1:
        return
    force_id = f"qty_{force_facts[0].role}"
    distance_id = f"qty_{distance_facts[0].role}"
    by_id = {item["quantity_id"]: item for item in quantities}
    force = by_id.get(force_id)
    distance = by_id.get(distance_id)
    if (
        force is None
        or distance is None
        or force.get("role") != "force"
        or force.get("subject_id") != entity_id
        or force.get("interval_id") != interval["interval_id"]
        or force.get("event_id") is not None
        or force.get("direction")
        != {"kind": "semantic", "direction": "along_motion"}
        or force.get("raw_value") is None
        or force.get("raw_unit") is None
        or not force.get("evidence_refs")
        or distance.get("role") != "distance"
        or distance.get("subject_id") != entity_id
        or distance.get("interval_id") != interval["interval_id"]
        or distance.get("event_id") is not None
        or distance.get("component") != "magnitude"
        or distance.get("direction") is not None
        or distance.get("raw_value") is None
        or distance.get("raw_unit") is None
        or not distance.get("evidence_refs")
    ):
        return
    if any(
        item["assumption_id"] == _DIRECT_CONSTANT_FORCE_WORK_ASSUMPTION_ID
        or (
            item["kind"] == "constant_force"
            and item["subject_id"] == entity_id
            and item["interval_id"] in {None, interval["interval_id"]}
        )
        for item in assumptions
    ):
        return

    assumptions.append(
        {
            "assumption_id": _DIRECT_CONSTANT_FORCE_WORK_ASSUMPTION_ID,
            "kind": "constant_force",
            "subject_id": entity_id,
            "interval_id": interval["interval_id"],
            "disposition": "approved",
            "reason": (
                "closed server policy: one source-valued force fact owns the "
                "whole source-declared energy interval"
            ),
            "evidence_refs": sorted(
                set(force["evidence_refs"]) | set(distance["evidence_refs"])
            ),
        }
    )
    approved.append(_DIRECT_CONSTANT_FORCE_WORK_ASSUMPTION_ID)


_INCLINE_SLIDE_MOTION_ASSUMPTION_ID = "asm_closure_incline_slide_motion"
# A body typed as sliding on an incline has its velocity along the slope
# tangent, so a source that states the velocity points downward has stated the
# down-slope sense and one that states upward has stated the up-slope sense.
# No direction the corpus can state resolves a slope sense.  `downward` and
# `upward` are *world* senses: a body constrained to a slope moves along the
# slope tangent, which is world-downward only if the slope's facing says so,
# and the corpus types no facing.  Reading `downward` as "down-slope" is a
# reinterpretation of the word, not a reading of it, and it is the reason this
# mapping is now empty rather than absent — the emptiness is the policy.
# `left`, `right`, `along_motion`, `opposite_motion`, `unspecified`, and
# `not_applicable` resolve no slope sense either.
_INCLINE_SLIDE_MOTION_SENSES: dict[str, str] = {}
# The instant a slide starts is not the interval it runs over.  An
# `initial_velocity` states one moment's direction, and a body that turns
# around later was moving the other way for part of the same interval, so it
# can never carry an interval-wide kinetic-friction sense.  Only a
# whole-interval `velocity` is even a candidate.
_INCLINE_SLIDE_VELOCITY_KEYS: frozenset[str] = frozenset({"velocity"})
# One authority kind, whichever way the slide goes.  The *sense* is not a
# label on the authority: it stays on the source velocity quantity, whose
# typed direction the closure binds to the slope tangent, so a law reads the
# direction from the physics record rather than from a string.
_INCLINE_SLIDE_MOTION_KIND = "typed_incline_slide_motion"


def _derive_incline_slide_motion_authority(
    *,
    gold: Any,
    entities: list[dict[str, Any]],
    motion_intervals: list[dict[str, Any]],
    geometry: list[dict[str, Any]],
    quantities: list[dict[str, Any]],
    assumptions: list[dict[str, Any]],
    approved: list[str],
) -> None:
    """Carry the source's own statement of which way the slide is going.

    ``sliding_on_incline`` says a body slides; it does not say *which way*.
    The same typed structure describes a block sliding down and a block
    coasting up, and those are different physics: with the down-slope tangent
    positive, a down-slope slide obeys ``a = g(sin θ − μ cos θ)`` and an
    up-slope slide obeys ``a = g(sin θ + μ cos θ)``, because kinetic friction
    opposes the motion that exists rather than the motion gravity would start.
    Neither can be recovered from what the source leaves out: no stated
    velocity is silence, not proof of a down-slope slide, and ``μ tan θ``
    comparisons decide nothing about the current direction either.

    So the sense must be *stated*, and stated in the slope's own terms.  Two
    things this derivation used to accept do not state it.

    A **world** direction does not.  ``downward`` says the velocity points
    down; a body constrained to a slope moves along the slope tangent, which
    points down only if the slope's facing says so, and no facing is typed
    anywhere in this corpus.  Reading ``downward`` as "down-slope" reinterprets
    the word rather than reading it, and the reinterpretation silently supplies
    the facing.  ``_INCLINE_SLIDE_MOTION_SENSES`` is empty for that reason.

    An **instant** does not.  A slide's opening moment is not the interval it
    runs over: a body that turns around later spent part of the same interval
    going the other way, and kinetic friction opposes the motion that exists at
    each moment.  So the carrier must be a whole-interval ``velocity`` with no
    ``event_role``, never an ``initial_velocity``.

    What would state it is a velocity bound to a source-authored slope frame's
    tangent axis, sign and all — the closure's own requirement. The public
    corpus cannot express that: ``project_case_to_draft`` emits
    ``reference_frames: []`` for every case, so there is no slope frame for a
    direction to name, and this derivation consequently never fires for a
    public case.  It is kept, and kept exact, because it is the statement of
    what the source would have to say.

    Every other model-completeness requirement stays: one free body, one
    incline, one ``slides_on`` support, one source angle, one source
    coefficient, an approved constant-gravity authority, and nothing else.  No
    sentence keyword, entity label, case identity, family, expected terminal,
    or numeric answer is read.
    """

    if (
        len(entities) != 2
        or len(motion_intervals) != 1
        or len(gold.motion_segments) != 1
        or len(gold.relations) != 1
        or len(gold.queries) != 1
        or len(gold.events) != len({item.role for item in gold.events})
    ):
        return
    primitive_by_id = {
        item["entity_id"]: item["primitive"] for item in entities
    }
    body_ids = tuple(
        entity_id
        for entity_id, primitive in primitive_by_id.items()
        if primitive in {"particle", "rigid_body", "body_component"}
    )
    incline_ids = tuple(
        entity_id
        for entity_id, primitive in primitive_by_id.items()
        if primitive == "incline"
    )
    if len(body_ids) != 1 or len(incline_ids) != 1:
        return
    body_id = body_ids[0]
    incline_id = incline_ids[0]

    segment = gold.motion_segments[0]
    interval = motion_intervals[0]
    interval_id = interval["interval_id"]
    if (
        segment.motion_model != "sliding_on_incline"
        or tuple(segment.actor_roles) != (body_id,)
        or segment.role != interval_id
        or interval["subject_ids"] != [body_id]
    ):
        return
    relation = gold.relations[0]
    if (
        relation.kind != "slides_on"
        or set(relation.participant_roles) != {body_id, incline_id}
        or len(relation.participant_roles) != 2
        or relation.segment_role not in {None, interval_id}
    ):
        return
    supports = tuple(
        item
        for item in geometry
        if item["kind"] == "lies_on" and item["interval_id"] == interval_id
    )
    if len(supports) != 1 or len(geometry) != 1 or set(
        supports[0]["participant_ids"]
    ) != {body_id, incline_id}:
        return

    query = gold.queries[0]
    if (
        query.output_key != "acceleration"
        or query.subject_role != body_id
        or query.segment_role != interval_id
        or query.component != "tangential"
        or query.event_role is not None
    ):
        return

    angle_facts = tuple(
        fact
        for fact in gold.explicit_facts
        if fact.semantic_key == "angle"
        and fact.subject_role == incline_id
        and fact.event_role is None
        and fact.temporal_role == "timeless"
    )
    coefficient_facts = tuple(
        fact
        for fact in gold.explicit_facts
        if fact.semantic_key == "coefficient_of_friction"
        and fact.subject_role == incline_id
        and fact.event_role is None
        and fact.temporal_role == "timeless"
    )
    mass_facts = tuple(
        fact
        for fact in gold.explicit_facts
        if fact.semantic_key == "mass"
        and fact.subject_role == body_id
        and fact.event_role is None
        and fact.temporal_role == "timeless"
    )
    # The one carrier of the slide's direction: a whole-interval velocity of
    # the sliding body whose stated direction is slope-relative.  A fact
    # pinned to an event states an instant, and an instant's direction is not
    # the interval's, so `event_role` must be absent rather than merely
    # inside the segment.
    motion_facts = tuple(
        fact
        for fact in gold.explicit_facts
        if fact.semantic_key in _INCLINE_SLIDE_VELOCITY_KEYS
        and fact.subject_role == body_id
        and fact.segment_role == interval_id
        and fact.event_role is None
        and fact.direction in _INCLINE_SLIDE_MOTION_SENSES
    )
    if (
        len(angle_facts) != 1
        or len(coefficient_facts) != 1
        or len(mass_facts) > 1
        or len(motion_facts) != 1
        or len(gold.explicit_facts)
        != len(angle_facts)
        + len(coefficient_facts)
        + len(mass_facts)
        + len(motion_facts)
    ):
        return
    motion_fact = motion_facts[0]

    by_id = {item["quantity_id"]: item for item in quantities}
    angle = by_id.get(f"qty_{angle_facts[0].role}")
    coefficient = by_id.get(f"qty_{coefficient_facts[0].role}")
    motion = by_id.get(f"qty_{motion_fact.role}")
    if (
        angle is None
        or coefficient is None
        or motion is None
        or angle.get("role") != "angle"
        or angle.get("raw_value") is None
        or not angle.get("evidence_refs")
        or coefficient.get("role") != "coefficient_friction"
        or coefficient.get("raw_value") is None
        or not coefficient.get("evidence_refs")
        or motion.get("role") != "velocity"
        or motion.get("raw_value") is None
        or not motion.get("evidence_refs")
        or motion.get("subject_id") != body_id
        or motion.get("direction")
        != {"kind": "semantic", "direction": motion_fact.direction}
    ):
        return

    gravity_records = tuple(
        item
        for item in assumptions
        if item["kind"] == "constant_gravity"
        and item["disposition"] == "approved"
        and item["assumption_id"] in set(approved)
        and item["subject_id"] == body_id
        and item["interval_id"] in {None, interval_id}
        and item["evidence_refs"]
    )
    # Any authority beyond the single gravity policy — a rest boundary, a
    # frictionless statement, a motion-model kinematic authority — is typed
    # evidence this is a different regime, and the derivation refuses.
    if len(gravity_records) != 1 or len(assumptions) != 1:
        return
    if any(
        item["assumption_id"] == _INCLINE_SLIDE_MOTION_ASSUMPTION_ID
        or item["kind"] == _INCLINE_SLIDE_MOTION_KIND
        for item in assumptions
    ):
        return

    assumptions.append(
        {
            "assumption_id": _INCLINE_SLIDE_MOTION_ASSUMPTION_ID,
            "kind": _INCLINE_SLIDE_MOTION_KIND,
            "subject_id": body_id,
            "interval_id": interval_id,
            "disposition": "approved",
            "reason": (
                "source-stated slide direction: the velocity of the sliding "
                "body carries a typed slope-tangent sense"
            ),
            "evidence_refs": sorted(
                set(motion["evidence_refs"])
                | set(angle["evidence_refs"])
                | set(coefficient["evidence_refs"])
                | set(gravity_records[0]["evidence_refs"])
            ),
        }
    )
    approved.append(_INCLINE_SLIDE_MOTION_ASSUMPTION_ID)


_ISOLATED_IMPACT_ASSUMPTION_PREFIX = "asm_closure_isolated_impact_"


def _derive_isolated_impact_assumption(
    *,
    entities: list[dict[str, Any]],
    motion_intervals: list[dict[str, Any]],
    events: list[dict[str, Any]],
    geometry: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
    quantities: list[dict[str, Any]],
    assumptions: list[dict[str, Any]],
    approved: list[str],
) -> None:
    """Authorise impulse isolation over one exact source-declared impact.

    The policy consumes only source-side typed structure: exactly two closed
    bodies, exactly one source-declared collision between them, and a motion
    interval whose own boundary events are the typed ``collision_start`` and
    ``collision_end`` of exactly those two bodies.  In that model the
    collision is the entire typed interaction system over its own interval —
    there is no other typed carrier of impulse — so the conservation law's
    existing ``external_impulse_negligible`` authority is a statement of the
    model's completeness, not a guess about the world.  No sentence keyword,
    case identity, family, expected terminal, or numeric answer is read.

    Anything beyond the exact impact shape refuses the derivation outright:
    a third entity, any geometry, any second interaction, any other
    assumption (a gravity authority would put a finite external impulse in
    play), or any quantity that is not one of the impact's own masses,
    velocities, and restitution coefficient — a stated force, impulse, or
    spring constant is typed evidence of external mechanics.
    """

    if (
        len(entities) != 2
        or len(motion_intervals) != 1
        or len(interactions) != 1
        or geometry
        or assumptions
    ):
        return
    if any(
        item["primitive"] not in {"particle", "rigid_body"}
        for item in entities
    ):
        return
    body_ids = {item["entity_id"] for item in entities}
    interval = motion_intervals[0]
    interval_id = interval["interval_id"]
    impact = interactions[0]
    if (
        impact["kind"] != "collision"
        or set(impact["participant_ids"]) != body_ids
        or len(impact["participant_ids"]) != 2
        or impact["interval_id"] != interval_id
        or impact.get("quantity_ids")
    ):
        return
    if (
        set(interval["subject_ids"]) != body_ids
        or len(interval["subject_ids"]) != 2
        or interval.get("start_event_id") is None
        or interval.get("end_event_id") is None
        or interval["start_event_id"] == interval["end_event_id"]
    ):
        return
    events_by_id = {item["event_id"]: item for item in events}
    start = events_by_id.get(interval["start_event_id"])
    end = events_by_id.get(interval["end_event_id"])
    if (
        len(events) != 2
        or len(events_by_id) != 2
        or start is None
        or end is None
        or start["kind"] != "collision_start"
        or end["kind"] != "collision_end"
        or set(start["subject_ids"]) != body_ids
        or set(end["subject_ids"]) != body_ids
    ):
        return

    allowed_roles = {"mass", "velocity", "coefficient_restitution"}
    if any(
        item["subject_id"] not in body_ids
        or item["role"] not in allowed_roles
        for item in quantities
    ):
        return
    masses_by_subject: dict[str, dict[str, Any]] = {}
    for item in quantities:
        if item["role"] != "mass":
            continue
        if item["subject_id"] in masses_by_subject:
            return
        masses_by_subject[item["subject_id"]] = item
    if set(masses_by_subject) != body_ids or any(
        item.get("raw_value") is None or not item.get("evidence_refs")
        for item in masses_by_subject.values()
    ):
        return

    evidence = sorted(
        {
            evidence_id
            for item in masses_by_subject.values()
            for evidence_id in item["evidence_refs"]
        }
    )
    declared = {item["assumption_id"] for item in assumptions}
    for body_id in sorted(body_ids):
        assumption_id = f"{_ISOLATED_IMPACT_ASSUMPTION_PREFIX}{body_id}"
        if assumption_id in declared:
            return
        assumptions.append(
            {
                "assumption_id": assumption_id,
                "kind": "external_impulse_negligible",
                "subject_id": body_id,
                "interval_id": interval_id,
                "disposition": "approved",
                "reason": (
                    "closed server policy: the source-declared collision is "
                    "the model's entire typed interaction system over its "
                    "own collision interval"
                ),
                "evidence_refs": list(evidence),
            }
        )
        approved.append(assumption_id)


_FIXED_PULLEY_IMPLICIT_ROPE_ID = "entity_closure_fixed_pulley_rope"

_FIXED_PULLEY_DERIVED_ASSUMPTIONS: tuple[
    tuple[str, str, str], ...
] = (
    (
        "asm_closure_fixed_pulley_massless_rope",
        "massless_rope",
        "rope",
    ),
    (
        "asm_closure_fixed_pulley_inextensible_rope",
        "inextensible_rope",
        "rope",
    ),
    (
        "asm_closure_fixed_pulley_fixed",
        "fixed_pulley",
        "pulley",
    ),
    (
        "asm_closure_fixed_pulley_ideal",
        "ideal_massless_frictionless_pulley",
        "pulley",
    ),
)


def _derive_fixed_pulley_assumptions(
    *,
    entities: list[dict[str, Any]],
    motion_intervals: list[dict[str, Any]],
    geometry: list[dict[str, Any]],
    quantities: list[dict[str, Any]],
    assumptions: list[dict[str, Any]],
    approved: list[str],
) -> None:
    """Scope aggregate idealisations to one exact fixed-pulley topology.

    ``connected_by_rope`` is itself typed source evidence that one rope exists,
    even when the parser represents that rope only as a relation instead of an
    entity.  For one unambiguous two-body wrap/connect topology this adapter may
    therefore materialise one value-free rope entity and scope the source's
    massless/inextensible authority to it.  One optional ``lies_on`` relation is
    admitted for the supported-body variants — an incline support or a
    horizontal table support, each a typed support primitive — and no other
    overlapping geometry is.

    A pulley that is an interval actor or carries rotational/inertial data is
    never treated as fixed.  No value, equation, answer, family, terminal, or
    corpus identity participates.
    """

    if len(motion_intervals) != 1:
        return
    interval = motion_intervals[0]
    interval_id = interval["interval_id"]
    primitive_by_id = {
        item["entity_id"]: item["primitive"] for item in entities
    }
    pulley_ids = tuple(
        sorted(
            entity_id
            for entity_id, primitive in primitive_by_id.items()
            if primitive == "pulley"
        )
    )
    if len(pulley_ids) != 1:
        return
    pulley_id = pulley_ids[0]

    masses = tuple(
        item
        for item in quantities
        if item["role"] == "mass"
        and primitive_by_id.get(item["subject_id"])
        in {"particle", "rigid_body", "body_component"}
        and item.get("raw_value") is not None
        and item.get("evidence_refs")
    )
    moving_ids = tuple(sorted({item["subject_id"] for item in masses}))
    if len(masses) != 2 or len(moving_ids) != 2:
        return
    if not set(moving_ids).issubset(interval["subject_ids"]):
        return
    if pulley_id in interval["subject_ids"]:
        return
    if any(
        item["subject_id"] == pulley_id
        and item["role"]
        in {
            "moment_of_inertia",
            "angular_position",
            "angular_velocity",
            "angular_acceleration",
            "torque",
            "moment",
        }
        for item in quantities
    ):
        return

    wraps = tuple(
        item
        for item in geometry
        if item["kind"] == "wraps" and item["interval_id"] == interval_id
    )
    connects = tuple(
        item
        for item in geometry
        if item["kind"] == "topology_connects"
        and item["interval_id"] == interval_id
    )
    lies_on = tuple(
        item
        for item in geometry
        if item["kind"] == "lies_on" and item["interval_id"] == interval_id
    )
    if len(wraps) != 1 or len(connects) != 1 or len(lies_on) > 1:
        return
    if (
        set(connects[0]["participant_ids"]) != set(moving_ids)
        or len(connects[0]["participant_ids"]) != 2
        or set(wraps[0]["participant_ids"]) != {*moving_ids, pulley_id}
        or len(wraps[0]["participant_ids"]) != 3
    ):
        return
    support_ids = tuple(
        sorted(
            entity_id
            for entity_id, primitive in primitive_by_id.items()
            if primitive in _SUPPORT_PRIMITIVES
        )
    )
    if lies_on:
        if len(support_ids) != 1:
            return
        if (
            len(lies_on[0]["participant_ids"]) != 2
            or set(lies_on[0]["participant_ids"])
            != {support_ids[0], next((item for item in moving_ids if item in lies_on[0]["participant_ids"]), "")}
            or len(set(lies_on[0]["participant_ids"]) & set(moving_ids)) != 1
        ):
            return
    allowed_geometry_ids = {
        wraps[0]["relation_id"],
        connects[0]["relation_id"],
        *(item["relation_id"] for item in lies_on),
    }
    topology_ids = {*moving_ids, pulley_id, *support_ids}
    if any(
        item["interval_id"] == interval_id
        and set(item["participant_ids"]) & topology_ids
        and item["relation_id"] not in allowed_geometry_ids
        for item in geometry
    ):
        return

    approved_set = set(approved)

    def _approved_source(kind: str) -> dict[str, Any] | None:
        matches = tuple(
            item
            for item in assumptions
            if item["kind"] == kind
            and item["disposition"] == "approved"
            and item["assumption_id"] in approved_set
            and item["interval_id"] in {None, interval_id}
            and item["evidence_refs"]
        )
        return matches[0] if len(matches) == 1 else None

    massless_rope = _approved_source("massless_rope")
    inextensible_rope = _approved_source("inextensible_rope")
    massless_pulley = _approved_source("massless_pulley")
    frictionless = _approved_source("frictionless")
    if any(
        item is None
        for item in (
            massless_rope,
            inextensible_rope,
            massless_pulley,
            frictionless,
        )
    ):
        return
    assert massless_rope is not None
    assert inextensible_rope is not None
    assert massless_pulley is not None
    assert frictionless is not None

    rope_ids = tuple(
        sorted(
            entity_id
            for entity_id, primitive in primitive_by_id.items()
            if primitive == "rope"
        )
    )
    if not rope_ids:
        if any(item["entity_id"] == _FIXED_PULLEY_IMPLICIT_ROPE_ID for item in entities):
            return
        rope_evidence = sorted(
            set(massless_rope["evidence_refs"])
            | set(inextensible_rope["evidence_refs"])
        )
        entities.append(
            {
                "entity_id": _FIXED_PULLEY_IMPLICIT_ROPE_ID,
                "primitive": "rope",
                "evidence_refs": rope_evidence,
            }
        )
        rope_ids = (_FIXED_PULLEY_IMPLICIT_ROPE_ID,)
    if len(rope_ids) != 1:
        return
    rope_id = rope_ids[0]

    authored_ids = {item["assumption_id"] for item in assumptions}
    derived_ids = {item[0] for item in _FIXED_PULLEY_DERIVED_ASSUMPTIONS}
    if authored_ids & derived_ids:
        return

    evidence_by_kind = {
        "massless_rope": tuple(massless_rope["evidence_refs"]),
        "inextensible_rope": tuple(inextensible_rope["evidence_refs"]),
        "fixed_pulley": tuple(
            sorted(
                set(massless_pulley["evidence_refs"])
                | set(frictionless["evidence_refs"])
            )
        ),
        "ideal_massless_frictionless_pulley": tuple(
            sorted(
                set(massless_pulley["evidence_refs"])
                | set(frictionless["evidence_refs"])
            )
        ),
    }
    subject_by_marker = {"rope": rope_id, "pulley": pulley_id}
    for assumption_id, kind, subject_marker in _FIXED_PULLEY_DERIVED_ASSUMPTIONS:
        assumptions.append(
            {
                "assumption_id": assumption_id,
                "kind": kind,
                "subject_id": subject_by_marker[subject_marker],
                "interval_id": interval_id,
                "disposition": "approved",
                "reason": (
                    "closed server policy: unique source-declared ideal "
                    "fixed-pulley topology"
                ),
                "evidence_refs": list(evidence_by_kind[kind]),
            }
        )
        approved.append(assumption_id)

def _direction_fields(direction: str | None, role: str) -> dict[str, Any]:
    """Carry a source-stated direction into the typed Draft fields.

    A quantity whose source states no direction receives none: the absence is
    preserved rather than filled with a default.  ``not_applicable`` is not that
    absence — it is the source stating that this quantity has no direction, so
    the component it named is the magnitude.
    """

    if direction == "not_applicable" and role in _MAGNITUDE_WHEN_DIRECTIONLESS:
        return {"component": _DIRECTIONLESS_COMPONENT}
    if direction is None or direction not in _SEMANTIC_DIRECTIONS:
        return {}
    fields: dict[str, Any] = {
        "direction": {"kind": "semantic", "direction": direction}
    }
    component = _DIRECTION_COMPONENTS.get(direction)
    if component is not None:
        fields["component"] = component
    return fields


def _reversal_free_scopes(
    assumptions: list[dict[str, Any]],
    approved: set[str],
    state_conditions: list[dict[str, Any]],
) -> frozenset[tuple[str, str]]:
    """The ``(subject, interval)`` scopes whose typed model forbids a reversal.

    Derived from approved assumptions and boundary conditions only.  A family, a
    case ID, an expected system type, an expected answer, and the problem text
    have no say.
    """

    rest_at_start = {
        (state["subject_id"], state["interval_id"])
        for state in state_conditions
        if state["kind"] == "initial"
        and state["state"] == "at_rest"
        and state["interval_id"] is not None
    }
    scopes: set[tuple[str, str]] = set()
    for assumption in assumptions:
        if assumption["assumption_id"] not in approved:
            continue
        kind = assumption["kind"]
        interval_id = assumption["interval_id"]
        if kind not in _REVERSAL_FREE_ASSUMPTIONS or interval_id is None:
            continue
        scope = (assumption["subject_id"], interval_id)
        if kind in _REST_PINNED_ASSUMPTIONS and scope not in rest_at_start:
            continue
        scopes.add(scope)
    return frozenset(scopes)


def _retype_path_lengths(
    quantities: list[dict[str, Any]],
    reversal_free: frozenset[tuple[str, str]],
) -> None:
    """Retype a whole-interval path length as that interval's displacement.

    Only a quantity the source scoped to a whole interval qualifies: one pinned
    to an instant measures something else and is left alone.  The rewrite keeps
    every other identity field — subject, interval, component, direction,
    evidence — so the canonical symbol still names the same physical thing.
    """

    for item in quantities:
        if item["role"] != _PATH_LENGTH_ROLE:
            continue
        if item.get("event_id") is not None or item.get("interval_id") is None:
            continue
        if (item["subject_id"], item["interval_id"]) not in reversal_free:
            continue
        item["role"] = "displacement"


def _interval_aggregate_event_role(
    fact: Any,
    intervals_by_id: Mapping[str, dict[str, Any]],
) -> str | None:
    """Return the event that truly belongs to a fact's physical identity.

    A path length can name the interval's terminal event merely to say *how far
    the actor had travelled by that boundary*.  When the corpus also types the
    fact as an interval aggregate, the quantity is owned by the whole interval,
    not by the zero-duration instant at its end.  Keeping that endpoint on the
    quantity prevented the already-reviewed reversal-free path-length theorem
    from retyping it as displacement.

    Only the exact typed shape is narrowed here: ``distance`` + interval
    temporal scope + the same interval's own end event.  An internal event, the
    start event, an instant-scoped fact, or any other quantity keeps its event.
    No text, family, expected terminal, or reference answer participates.
    """

    event_role = fact.event_role
    if (
        fact.semantic_key != _PATH_LENGTH_ROLE
        or fact.segment_role is None
        or event_role is None
        or (fact.temporal_role or "") not in _INTERVAL_TEMPORAL_ROLES
    ):
        return event_role
    interval = intervals_by_id.get(fact.segment_role)
    if interval is None or interval.get("end_event_id") != event_role:
        return event_role
    return None


# The physical identity a symbol names.  A value, a raw unit, an evidence
# reference, a corpus ID, an array position, and every gold member are excluded
# by construction: two quantities that describe the same physical thing must
# collide here, and two that describe different things must not.
_SYMBOL_IDENTITY_FIELDS: tuple[str, ...] = (
    "role",
    "subject_id",
    "point_id",
    "frame_id",
    "interval_id",
    "event_id",
    "component",
    "direction",
    "shape",
    "dimension",
)

# Draft shapes that the scalar/vector math AST symbol table can express.
_SYMBOL_SHAPES: dict[str, str] = {"scalar": "scalar", "vector": "vector"}


def _canonical_symbol_identity(item: Mapping[str, Any]) -> str:
    """Serialise one quantity's physical identity canonically and totally."""

    payload: dict[str, Any] = {}
    for name in _SYMBOL_IDENTITY_FIELDS:
        value = item.get(name)
        if name == "component" and value is None:
            value = "unspecified"
        if name == "dimension":
            value = dict(sorted((value or {}).items()))
        payload[name] = value
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_symbol_id(identity: str) -> str:
    """Derive a stable symbol ID from physical identity alone."""

    return "sym_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _symbol_for(item: Mapping[str, Any], symbol_id: str) -> dict[str, Any]:
    shape = _SYMBOL_SHAPES.get(str(item.get("shape")))
    if shape is None:
        # A tensor quantity cannot enter the scalar/vector symbol table; it is
        # rejected here rather than silently narrowed to a scalar.
        raise DraftProjectionError(DraftProjectionReason.symbol_binding_not_reciprocal)
    return {
        "symbol_id": symbol_id,
        "quantity_id": item["quantity_id"],
        "dimension": dict(item["dimension"]),
        "shape": shape,
    }


def _bind_reciprocal_symbols(quantities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give every quantity exactly one canonical symbol, both ways.

    A second quantity claiming the same canonical physical identity is a
    collision, not a merge: it is rejected so that two different source facts
    can never be silently fused into one graph unknown.
    """

    symbols: list[dict[str, Any]] = []
    claimed_by_symbol: dict[str, str] = {}
    claimed_by_quantity: dict[str, str] = {}
    for item in quantities:
        symbol_id = _canonical_symbol_id(_canonical_symbol_identity(item))
        if symbol_id in claimed_by_symbol:
            raise DraftProjectionError(
                DraftProjectionReason.duplicate_canonical_symbol
            )
        quantity_id = item["quantity_id"]
        if quantity_id in claimed_by_quantity:
            raise DraftProjectionError(
                DraftProjectionReason.duplicate_canonical_symbol
            )
        claimed_by_symbol[symbol_id] = quantity_id
        claimed_by_quantity[quantity_id] = symbol_id
        item["symbol_id"] = symbol_id
        symbols.append(_symbol_for(item, symbol_id))
    return symbols


def _assert_symbols_are_reciprocal(
    quantities: list[dict[str, Any]], symbols: list[dict[str, Any]]
) -> None:
    """Fail closed unless the binding is reciprocal, one-to-one, and typed."""

    by_symbol = {symbol["symbol_id"]: symbol for symbol in symbols}
    if len(by_symbol) != len(symbols):
        raise DraftProjectionError(DraftProjectionReason.duplicate_canonical_symbol)
    if len({symbol["quantity_id"] for symbol in symbols}) != len(symbols):
        raise DraftProjectionError(DraftProjectionReason.duplicate_canonical_symbol)
    if len(quantities) != len(symbols):
        raise DraftProjectionError(
            DraftProjectionReason.symbol_binding_not_reciprocal
        )
    for item in quantities:
        symbol = by_symbol.get(item.get("symbol_id") or "")
        if (
            symbol is None
            or symbol["quantity_id"] != item["quantity_id"]
            or symbol["dimension"] != item["dimension"]
            or symbol["shape"] != _SYMBOL_SHAPES.get(str(item.get("shape")))
        ):
            raise DraftProjectionError(
                DraftProjectionReason.symbol_binding_not_reciprocal
            )


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
        projected = _build_payload(gold, problem_text)
    except DraftProjectionError as exc:
        return DraftProjection(
            terminal=DraftProjectionTerminal.projection_rejected,
            problem_text=problem_text,
            sanitized_reason=exc.sanitized_reason,
        )

    try:
        draft = MechanicsProblemDraftV1.model_validate(projected.payload)
    except Exception as exc:
        return DraftProjection(
            terminal=DraftProjectionTerminal.projection_rejected,
            problem_text=problem_text,
            sanitized_reason=DraftProjectionError(
                DraftProjectionReason.draft_contract_rejected,
                detail=type(exc).__name__,
            ).sanitized_reason,
        )

    if _has_no_relational_structure(draft):
        return DraftProjection(
            terminal=DraftProjectionTerminal.insufficient_information,
            problem_text=problem_text,
        )

    return DraftProjection(
        terminal=DraftProjectionTerminal.projected,
        problem_text=problem_text,
        draft=draft,
        environment_scoped_quantity_ids=projected.environment_scoped_quantity_ids,
        segment_internal_event_ids=projected.segment_internal_event_ids,
        approvable_assumption_ids=projected.approvable_assumption_ids,
        known_symbol_ids=projected.known_symbol_ids,
        unknown_symbol_ids=projected.unknown_symbol_ids,
        event_authority_gaps=projected.event_authority_gaps,
    )


def _has_no_relational_structure(draft: MechanicsProblemDraftV1) -> bool:
    """True when the Draft states quantities but relates none of them.

    Every law in the catalogue relates quantities *through* structure — an
    interval, an event, a geometry relation, an interaction, a constraint, a
    state condition, or an approved assumption.  A Draft that carries none of
    those has nothing a law could bind, so no amount of solving reaches the
    query and no single reader decision would change that: unlike an ambiguity,
    there is no enumerable alternative to confirm.  That is exactly
    `insufficient_information`, and it is a structural fact about the Draft, not
    a judgement about the sentence.
    """

    if not draft.queries:
        return True
    return not (
        draft.motion_intervals
        or draft.events
        or draft.geometry
        or draft.interactions
        or draft.constraints
        or draft.state_conditions
        or draft.assumptions
    )


@dataclass(frozen=True, slots=True)
class _PayloadProjection:
    payload: dict[str, Any]
    environment_scoped_quantity_ids: tuple[str, ...]
    segment_internal_event_ids: tuple[str, ...]
    approvable_assumption_ids: tuple[str, ...]
    known_symbol_ids: tuple[str, ...]
    unknown_symbol_ids: tuple[str, ...]
    event_authority_gaps: tuple[tuple[str, str], ...]


def _build_payload(gold: Any, problem_text: str) -> _PayloadProjection:
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
                "start_event_id": segment.start_event_role,
                "end_event_id": segment.end_event_role,
                "evidence_refs": [],
            }
        )

    intervals_by_id = {item["interval_id"]: item for item in intervals}

    # A boundary is declared from the *interval* side, and `interval_ids` is the
    # typed reciprocal of that declaration — not a general "this event happens
    # during that interval" field.  Indexing the declarations first keeps both
    # directions derived from one source, so a shared boundary lists every
    # interval it bounds and a segment-internal event lists none.
    boundary_slots: dict[str, list[tuple[str, str]]] = {}
    for segment in gold.motion_segments:
        for role, slot in (
            (segment.start_event_role, "start"),
            (segment.end_event_role, "finish"),
        ):
            if role is None:
                continue
            boundary_slots.setdefault(role, []).append((segment.role, slot))
    for role, slots in boundary_slots.items():
        for interval_id, _slot in slots:
            if interval_id not in interval_ids:
                raise DraftProjectionError(
                    DraftProjectionReason.dangling_interval_reference
                )

    events: list[dict[str, Any]] = []
    segment_internal: list[str] = []
    source_evidence: list[dict[str, Any]] = []
    event_authority_gaps: list[tuple[str, str]] = []
    for event in gold.events:
        kind = _EVENT_KINDS.get(event.kind)
        if kind is None:
            raise DraftProjectionError(DraftProjectionReason.unmapped_event_kind)
        for subject in event.subject_roles:
            if subject not in entity_ids:
                raise DraftProjectionError(
                    DraftProjectionReason.dangling_entity_reference
                )
        if event.segment_role is not None and event.segment_role not in interval_ids:
            raise DraftProjectionError(
                DraftProjectionReason.dangling_interval_reference
            )
        membership = _bounded_intervals(
            event.role,
            event.subject_roles,
            boundary_slots=boundary_slots,
            actors_by_interval=actors_by_interval,
        )
        occurrence: list[str] = []
        if event.segment_role is not None and not membership:
            # The event occurs inside the segment without bounding it.  The
            # occurrence is preserved as a typed scope of its own —
            # `occurs_in_interval_ids` — and is never restated as a boundary.
            # The claim is only made when the event's subjects provably
            # belong to the occupying interval; otherwise the event stays,
            # scopeless, rather than carrying an unproven occupancy.
            segment_internal.append(event.role)
            if set(event.subject_roles) <= actors_by_interval[event.segment_role]:
                occurrence = [event.segment_role]
        # A numeric-licensing event kind (a vertical extremum, a turnaround,
        # a comes-to-rest) needs its own source authority: the corpus event's
        # stated evidence quote, resolved to the exact, unique span of the
        # problem text and linked through `evidence_refs`.  Missing,
        # unresolvable, or ambiguous evidence fails closed — the event itself
        # is preserved, but it carries no authority and no boundary law will
        # consume it.  No keyword or regex routing participates: the quote is
        # the modeler's own statement, matched exactly.
        event_refs: list[str] = []
        if kind in NUMERIC_LICENSING_EVENT_KINDS:
            quote = event.evidence_quote
            if not quote:
                event_authority_gaps.append((event.role, "missing_quote"))
            else:
                occurrences = quote_occurrences(problem_text, quote)
                if not occurrences:
                    event_authority_gaps.append((event.role, "quote_not_found"))
                elif len(occurrences) > 1:
                    event_authority_gaps.append((event.role, "quote_ambiguous"))
                else:
                    span = occurrences[0]
                    digest = hashlib.sha256(
                        event.role.encode("utf-8")
                    ).hexdigest()[:16]
                    evidence_id = f"ev_evt_{digest}"
                    source_evidence.append(
                        {
                            "evidence_id": evidence_id,
                            "kind": "text",
                            "quote": problem_text[span.start : span.end],
                            "occurrence_index": 0,
                            "source_span": {
                                "start": span.start,
                                "end": span.end,
                            },
                        }
                    )
                    event_refs = [evidence_id]
        events.append(
            {
                "event_id": event.role,
                "kind": kind,
                "subject_ids": list(event.subject_roles),
                "interval_ids": membership,
                "occurs_in_interval_ids": occurrence,
                "evidence_refs": event_refs,
            }
        )

    # A boundary the corpus references but does not materialise as an event
    # object is completed here.  The kind comes from the *slot* the reference
    # occupies — start slot means start, end slot means finish — never from the
    # role string, and the subjects are the declaring intervals' own actors.
    for role in sorted(set(boundary_slots) - event_ids):
        slots = boundary_slots[role]
        subjects = set.intersection(
            *(actors_by_interval[interval_id] for interval_id, _slot in slots)
        )
        if not subjects:
            raise DraftProjectionError(
                DraftProjectionReason.boundary_event_subject_not_in_interval
            )
        ordered_subjects = sorted(subjects)
        events.append(
            {
                "event_id": role,
                "kind": "finish" if any(slot == "finish" for _, slot in slots) else "start",
                "subject_ids": ordered_subjects,
                "interval_ids": _bounded_intervals(
                    role,
                    ordered_subjects,
                    boundary_slots=boundary_slots,
                    actors_by_interval=actors_by_interval,
                ),
                # A synthesized event exists only because an interval names
                # it as a boundary; it occupies nothing.
                "occurs_in_interval_ids": [],
                "evidence_refs": [],
            }
        )
    event_ids = {item["event_id"] for item in events}
    # An event's typed interval reach: the intervals it bounds plus the
    # intervals it provably occurs within.  Records scoped to a
    # (segment, internal event) pair keep both dimensions — the occurrence
    # scope makes that legal without ever claiming a boundary.
    interval_reach_by_event = {
        item["event_id"]: frozenset(item["interval_ids"])
        | frozenset(item["occurs_in_interval_ids"])
        for item in events
    }

    quantities: list[dict[str, Any]] = []
    environment_scoped: list[str] = []
    interaction_owned: dict[str, list[str]] = {}
    primitives_by_entity = {
        entity["entity_id"]: entity["primitive"] for entity in entities
    }
    relations_by_pair = _interval_scoped_relations(gold, interval_ids, entity_ids)

    for index, fact in enumerate(gold.explicit_facts):
        mapped = _FACT_ROLES.get(fact.semantic_key)
        if mapped is None:
            raise DraftProjectionError(DraftProjectionReason.unmapped_semantic_key)
        elapsed = _ELAPSED_ROLES.get(fact.semantic_key)
        if (
            elapsed is not None
            and fact.event_role is None
            and fact.segment_role is not None
            and (fact.temporal_role or "") in _INTERVAL_TEMPORAL_ROLES
        ):
            mapped = elapsed
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

        fact_event_role = _stated_endpoint(
            _ENDPOINT_TEMPORAL_ROLES.get(fact.temporal_role or ""),
            fact.segment_role,
            _interval_aggregate_event_role(fact, intervals_by_id),
            intervals_by_id,
        )
        interval_id, event_id = _typed_scope(
            fact.segment_role, fact_event_role, interval_reach_by_event
        )
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
                # An environment property is timeless and its owner is
                # deliberately not one of the interval's moving actors, so it
                # cannot claim that interval as its own scope.  The verified
                # relation above is what couples it to the actor's interval; the
                # environment entity is never promoted to an interval subject.
                interval_id = None

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
        # A constitutive parameter stated on an interaction's passive side takes
        # the typed owner the engine's own convention requires, and records that
        # it is owned by the interaction that licensed the binding.
        owner = _interaction_owned_binding(
            subject=fact.subject_role,
            role=role,
            interval_id=interval_id,
            gold=gold,
            primitives_by_entity=primitives_by_entity,
        )
        subject_id = fact.subject_role
        if owner is not None:
            subject_id, relation_role = owner
            interaction_owned.setdefault(relation_role, []).append(f"qty_{fact.role}")
        quantities.append(
            {
                "quantity_id": f"qty_{fact.role}",
                "role": role,
                "subject_id": subject_id,
                "interval_id": interval_id,
                "event_id": event_id,
                "shape": "scalar",
                "dimension": dimension,
                "provenance": "explicit_source",
                "raw_value": written_value,
                "raw_unit": written_unit,
                "evidence_refs": [evidence_id],
                **_direction_fields(fact.direction, role),
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
                "interval_id": _interaction_interval(
                    relation.segment_role,
                    relation.participant_roles,
                    actors_by_interval,
                ),
                # An interaction owns the constitutive parameters the source
                # states through it, so the typed link is reciprocal: the
                # quantity names its owner and the interaction names the
                # quantity.
                "quantity_ids": sorted(interaction_owned.get(relation.role, ())),
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
    state_conditions: list[dict[str, Any]] = []
    boundary_unknowns: list[dict[str, Any]] = []
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
        # An approved assumption that a source quote grounds records that quote
        # as real evidence, so anything it later authorises is traceable to the
        # sentence that licensed it.
        quote_span = (
            _locate_quote(problem_text, assumption.supporting_quote)
            if disposition == "approved"
            else None
        )
        if quote_span is not None:
            evidence_id = f"ev_asm_{assumption.role}"
            source_evidence.append(
                {
                    "evidence_id": evidence_id,
                    "kind": "text",
                    "quote": problem_text[quote_span[0] : quote_span[1]],
                    "occurrence_index": 0,
                    "source_span": {"start": quote_span[0], "end": quote_span[1]},
                }
            )
            entry["evidence_refs"] = [evidence_id]
        assumptions.append(entry)
        if disposition == "approved":
            approved.append(assumption_id)
            state_condition = _rest_state_condition(
                kind=assumption.kind,
                assumption_id=assumption_id,
                subject_id=subject,
                interval_id=interval_id,
                intervals_by_id=intervals_by_id,
                evidence_refs=entry["evidence_refs"],
            )
            if state_condition is not None:
                state_conditions.append(state_condition["state"])
                boundary_unknowns.append(state_condition["quantity"])

    _derive_direct_constant_force_work_assumption(
        gold=gold,
        entities=entities,
        motion_intervals=intervals,
        quantities=quantities,
        assumptions=assumptions,
        approved=approved,
    )

    _derive_fixed_pulley_assumptions(
        entities=entities,
        motion_intervals=intervals,
        geometry=geometry,
        quantities=quantities,
        assumptions=assumptions,
        approved=approved,
    )

    _derive_incline_slide_motion_authority(
        gold=gold,
        entities=entities,
        motion_intervals=intervals,
        geometry=geometry,
        quantities=quantities,
        assumptions=assumptions,
        approved=approved,
    )

    _derive_isolated_impact_assumption(
        entities=entities,
        motion_intervals=intervals,
        events=events,
        geometry=geometry,
        interactions=interactions,
        quantities=quantities,
        assumptions=assumptions,
        approved=approved,
    )

    # A motion model the corpus declares on a segment is source-grounded
    # structure, so the typed kinematic assumption it implies is authorised on
    # the same footing as a quoted one.  It applies to that segment's own actors
    # and to nothing else, and it carries no proposed value: it constrains how
    # the interval behaves, it does not supply a number.
    declared_assumption_ids = {entry["assumption_id"] for entry in assumptions}
    queried_roles = {
        _QUERY_ROLES[query.output_key][0]
        for query in gold.queries
        if query.output_key in _QUERY_ROLES
    }
    for segment in gold.motion_segments:
        kind = _MOTION_MODEL_ASSUMPTIONS.get(segment.motion_model or "")
        if kind is None:
            continue
        licensed = _QUERY_SCOPED_MOTION_MODEL_ASSUMPTIONS.get(kind)
        if licensed is not None and not (queried_roles & licensed):
            # The authority licenses a readout this source does not ask for.
            continue
        for actor in sorted(segment.actor_roles):
            assumption_id = f"asm_{kind}_{segment.role}_{actor}"
            if assumption_id in declared_assumption_ids:
                raise DraftProjectionError(
                    DraftProjectionReason.duplicate_motion_model_assumption
                )
            declared_assumption_ids.add(assumption_id)
            assumptions.append(
                {
                    "assumption_id": assumption_id,
                    "kind": kind,
                    "subject_id": actor,
                    "interval_id": segment.role,
                    "disposition": "approved",
                    "reason": (
                        "closed server policy: the source declares this segment's "
                        "motion model"
                    ),
                    "evidence_refs": [],
                }
            )
            approved.append(assumption_id)

    # The authorised assumptions and boundary conditions are settled, so the
    # intervals that cannot reverse are now known and a whole-interval path
    # length can take its typed home.  This runs before the symbols are bound so
    # each quantity's canonical identity is computed from its final role.
    _retype_path_lengths(
        quantities,
        _reversal_free_scopes(assumptions, set(approved), state_conditions),
    )

    # Every source-grounded quantity now owns one canonical symbol.  This runs
    # before the queries so a query unknown can never take a known symbol's
    # identity.
    known_symbols = _bind_reciprocal_symbols(quantities)
    _assert_symbols_are_reciprocal(quantities, known_symbols)
    known_symbol_ids = frozenset(symbol["symbol_id"] for symbol in known_symbols)

    queries: list[dict[str, Any]] = []
    # Boundary-condition unknowns are bound in the same pool as the query
    # unknown, so a rest boundary that lands on the question's own identity
    # collides and fails closed instead of silently answering it.
    unknown_quantities: list[dict[str, Any]] = list(boundary_unknowns)
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
        elapsed_binding = _elapsed_duration_binding(query, intervals_by_id)
        if elapsed_binding is not None:
            # The proven elapsed-duration question: the unknown is the
            # interval's own duration, scoped to the interval alone.  The two
            # boundary identities stay carried by the interval record itself
            # — an event-scoped duration is a shape the solver contract
            # rejects, and restating the end event here would claim an
            # absolute instant no source states.  Only the role, unit,
            # dimension, and event scope change; subject and component are
            # the question's own.
            role, unit, dimension = elapsed_binding
            query_interval_id, query_event_id = query.segment_role, None
        else:
            query_event_role = _stated_endpoint(
                _ENDPOINT_QUERY_KEYS.get(query.output_key),
                query.segment_role,
                query.event_role,
                intervals_by_id,
            )
            query_interval_id, query_event_id = _typed_scope(
                query.segment_role, query_event_role, interval_reach_by_event
            )
        # The query target is a quantity the source does *not* state.  It keeps
        # the full subject/interval/event/component identity of the question and
        # carries no value, no unit token, and no evidence: it is exactly the
        # unknown the Equation Graph has to determine.
        unknown_quantities.append(
            {
                "quantity_id": f"qty_unknown_{query.role}",
                "role": role,
                "subject_id": query.subject_role,
                "interval_id": query_interval_id,
                "event_id": query_event_id,
                "component": query.component or "unspecified",
                "shape": "scalar",
                "dimension": dimension,
                "provenance": "unknown",
                "evidence_refs": [],
            }
        )
        projected_query: dict[str, Any] = {
            "query_id": f"qry_{query.role}",
            "output_unit": unit,
            "output_dimension": dimension,
            "shape": "scalar",
            "target": {
                "role": role,
                "subject_id": query.subject_role,
                "interval_id": query_interval_id,
                "event_id": query_event_id,
                "component": query.component or "unspecified",
                "target_quantity_id": f"qty_unknown_{query.role}",
            },
            "evidence_refs": [],
        }
        objective = _QUERY_OBJECTIVES.get(query.output_key)
        if objective is not None:
            projected_query["objective"] = objective
        queries.append(projected_query)

    unknown_symbols = _bind_reciprocal_symbols(unknown_quantities)
    _assert_symbols_are_reciprocal(unknown_quantities, unknown_symbols)
    unknown_symbol_ids = frozenset(symbol["symbol_id"] for symbol in unknown_symbols)
    # An unknown that lands on a known symbol's identity would mean the source
    # already states the answer; it is rejected rather than silently reused.
    if known_symbol_ids & unknown_symbol_ids:
        raise DraftProjectionError(
            DraftProjectionReason.unknown_symbol_collides_with_known
        )
    quantities.extend(unknown_quantities)
    symbols = [*known_symbols, *unknown_symbols]
    _assert_symbols_are_reciprocal(quantities, symbols)

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
        "symbols": symbols,
        "geometry": geometry,
        "interactions": interactions,
        "constraints": [],
        "state_conditions": state_conditions,
        "queries": queries,
        "principle_hints": [],
        "assumptions": assumptions,
        "ambiguities": _unresolved_typed_ambiguities(
            entities=entities,
            quantities=quantities,
            geometry=geometry,
            assumptions=assumptions,
            queries=queries,
        ),
        "figure_dependency": {
            "level": gold.figure_dependency.level,
            "missing_information": list(gold.figure_dependency.missing_information),
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }
    return _PayloadProjection(
        payload=payload,
        environment_scoped_quantity_ids=tuple(environment_scoped),
        segment_internal_event_ids=tuple(segment_internal),
        approvable_assumption_ids=tuple(approved),
        known_symbol_ids=tuple(symbol["symbol_id"] for symbol in known_symbols),
        unknown_symbol_ids=tuple(symbol["symbol_id"] for symbol in unknown_symbols),
        event_authority_gaps=tuple(sorted(event_authority_gaps)),
    )


def _stated_endpoint(
    boundary_field: str | None,
    interval_id: str | None,
    event_id: str | None,
    intervals_by_id: Mapping[str, dict[str, Any]],
) -> str | None:
    """Resolve a stated initial/final endpoint to the interval's own boundary.

    An explicit event in the source always wins; the endpoint is only filled in
    where the source left it implicit and the interval actually declares that
    boundary.  A boundary the source never declared is never invented.
    """

    if event_id is not None or boundary_field is None or interval_id is None:
        return event_id
    interval = intervals_by_id.get(interval_id)
    if interval is None:
        return None
    return interval.get(boundary_field)


def _rest_state_condition(
    *,
    kind: str,
    assumption_id: str,
    subject_id: str,
    interval_id: str | None,
    intervals_by_id: Mapping[str, dict[str, Any]],
    evidence_refs: list[str],
) -> dict[str, dict[str, Any]] | None:
    """Express an approved rest assumption as a typed boundary constraint.

    The assumption names an instant — the start or the end of the interval the
    corpus scoped it to — so the typed IR states it as a `StateCondition` at
    that boundary over that instant's own unknown velocity.  Nothing becomes a
    known value: the constraint is what pins the unknown to zero, and the solver
    derives it.

    Returns nothing, rather than guessing, when the assumption has no interval,
    no source evidence, or a boundary the corpus never declared.
    """

    mapped = _REST_STATE_CONDITIONS.get(kind)
    if mapped is None or interval_id is None or not evidence_refs:
        return None
    state_kind, boundary_field = mapped
    interval = intervals_by_id.get(interval_id)
    if interval is None or subject_id not in interval["subject_ids"]:
        return None
    event_id = interval.get(boundary_field)
    if event_id is None:
        return None
    quantity_id = f"qty_rest_{assumption_id}"
    return {
        "quantity": {
            "quantity_id": quantity_id,
            "role": "velocity",
            "subject_id": subject_id,
            "interval_id": interval_id,
            "event_id": event_id,
            # At rest the speed is zero and no direction applies, so the
            # component the condition names is the magnitude — the same
            # component an undirected source quantity carries, which is what
            # lets an endpoint law pair the two.
            "component": _DIRECTIONLESS_COMPONENT,
            "shape": "scalar",
            "dimension": dict(_VELOCITY_DIMENSION),
            "provenance": "unknown",
            "evidence_refs": [],
        },
        "state": {
            "state_condition_id": f"st_{assumption_id}",
            "kind": state_kind,
            "state": "at_rest",
            "subject_id": subject_id,
            "interval_id": interval_id,
            "event_id": event_id,
            "quantity_ids": [quantity_id],
            "evidence_refs": list(evidence_refs),
        },
    }


def _bounded_intervals(
    event_role: str,
    subject_roles: Any,
    *,
    boundary_slots: Mapping[str, list[tuple[str, str]]],
    actors_by_interval: Mapping[str, set[str]],
) -> list[str]:
    """List every interval this event bounds, reciprocally and in order.

    An interval may only name an event as its boundary when the event's own
    subjects are among that interval's actors; otherwise the declaration is
    rejected rather than quietly widened.
    """

    subjects = set(subject_roles)
    bounded: list[str] = []
    for interval_id, _slot in boundary_slots.get(event_role, ()):
        if not subjects <= actors_by_interval[interval_id]:
            raise DraftProjectionError(
                DraftProjectionReason.boundary_event_subject_not_in_interval
            )
        if interval_id not in bounded:
            bounded.append(interval_id)
    return bounded


def _interaction_interval(
    interval_id: str | None,
    participant_roles: Any,
    actors_by_interval: Mapping[str, set[str]],
) -> str | None:
    """Scope an interaction to an interval only when the IR admits it.

    The typed contract requires every participant of an interval-scoped
    interaction to be a subject of that interval.  A coupling to a static
    environment entity therefore stays timeless — which is what it physically
    is — instead of promoting the environment entity to a moving actor.
    """

    if interval_id is None:
        return None
    if set(participant_roles) <= actors_by_interval.get(interval_id, set()):
        return interval_id
    return None


def _elapsed_duration_binding(
    query: Any, intervals_by_id: Mapping[str, dict[str, Any]]
) -> tuple[str, str, dict[str, int]] | None:
    """Prove a query's elapsed-duration semantics from typed fields, or decline.

    The proof reads exactly four typed inputs: the query's own output key,
    its segment, its event, and the queried interval's declared boundaries.
    It holds when the interval declares both boundaries, they are distinct
    physical events, and the question names either no event or precisely the
    interval's own end — the elapsed time from start to end.  Everything
    else declines and keeps the plain time binding: a start-event question
    would need an epoch no source states, a segment-internal instant would
    need a sub-interval the source never declared, a one-sided or degenerate
    span has nothing to elapse over, and a `period` is a property of a
    regime, never an interval's duration.  No raw text, family, or expected
    answer participates.
    """

    mapped = _ELAPSED_QUERY_KEYS.get(query.output_key)
    if mapped is None or query.segment_role is None:
        return None
    interval = intervals_by_id.get(query.segment_role)
    if interval is None:
        return None
    start_event = interval.get("start_event_id")
    end_event = interval.get("end_event_id")
    if start_event is None or end_event is None or start_event == end_event:
        return None
    if query.event_role not in (None, end_event):
        return None
    return mapped


def _typed_scope(
    interval_id: str | None,
    event_id: str | None,
    interval_reach_by_event: Mapping[str, frozenset[str]],
) -> tuple[str | None, str | None]:
    """Reduce a corpus (segment, event) pair to the scope the IR can express.

    The typed IR admits an interval *and* an event on one record when the
    event either bounds that interval or provably occurs within it — the
    same reach the compiler's reciprocity checks accept.  Occurrence never
    claims a boundary: `MotionInterval.start_event_id`/`end_event_id` stay
    the sole boundary authority, and a record scoped to an internal instant
    keeps its interval through `occurs_in_interval_ids` alone.  An event
    with neither claim keeps the instant and drops the unproven interval.
    """

    if event_id is None:
        return interval_id, None
    if interval_id is not None and interval_id in interval_reach_by_event.get(
        event_id, frozenset()
    ):
        return interval_id, event_id
    return None, event_id


def _unresolved_typed_ambiguities(
    *,
    entities: Sequence[Mapping[str, Any]],
    quantities: Sequence[Mapping[str, Any]],
    geometry: Sequence[Mapping[str, Any]],
    assumptions: Sequence[Mapping[str, Any]],
    queries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Report the typed ambiguities a reader — not the server — must resolve.

    Both detectors read only typed Draft structure that is already built: a
    primitive, a geometry kind, a quantity role, a component, an assumption
    kind.  Neither reads problem text, a family, a case ID, an expected
    terminal, or an expected answer, and neither picks a resolution.  A blocking
    ambiguity is the engine's own contract for "a reader must decide", and
    `validate_draft` already turns it into `needs_confirmation`.
    """

    primitives = {entity["entity_id"]: entity["primitive"] for entity in entities}
    found: list[dict[str, Any]] = []

    # A sliding support contact has a friction regime.  The source resolves it
    # either by stating a coefficient or by declaring the contact frictionless.
    # With neither, two physically different closures — frictionless, and rough
    # with an unstated coefficient — are equally consistent with the source, and
    # choosing one silently would be a confident wrong answer.
    frictionless_subjects = {
        assumption["subject_id"]
        for assumption in assumptions
        if assumption["kind"] in _FRICTION_REGIME_ASSUMPTIONS
        and assumption["disposition"] == "approved"
    }
    # A `system` is the aggregate of the bodies it contains, so a friction
    # regime the source declares on the system resolves the regime for each of
    # them.  The reading is typed — it turns on the subject's primitive — and it
    # only ever *resolves* a regime the source did state, never invents one.
    system_wide_regime = any(
        primitives.get(subject) == "system" for subject in frictionless_subjects
    )
    has_coefficient = any(
        quantity["role"] == "coefficient_friction" for quantity in quantities
    )
    for relation in geometry:
        if relation["kind"] != _SLIDING_SUPPORT_GEOMETRY_KIND:
            continue
        participants = list(relation["participant_ids"])
        bodies = [
            item
            for item in participants
            if primitives.get(item) in _CONSTITUTIVE_OWNER_PRIMITIVES
        ]
        supports = [
            item
            for item in participants
            if primitives.get(item) in _SUPPORT_PRIMITIVES
        ]
        if len(bodies) != 1 or len(supports) != 1:
            continue
        if has_coefficient or system_wide_regime or bodies[0] in frictionless_subjects:
            continue
        found.append(
            {
                "ambiguity_id": f"amb_friction_{relation['relation_id']}",
                "kind": "assumption",
                "description": (
                    "a sliding support contact states neither a friction "
                    "coefficient nor a frictionless regime, so the friction "
                    "regime must be confirmed before this contact can close"
                ),
                "blocking": True,
                "referenced_ids": [relation["relation_id"], bodies[0]],
                "evidence_refs": [],
            }
        )

    # A query for a signed axis component is answered by a sign, and a source
    # quantity whose direction the source left uncommitted cannot supply one.
    # The magnitude is not a substitute: it answers a different question.
    for query in queries:
        target = query["target"]
        if target.get("component") not in _SIGNED_AXIS_COMPONENTS:
            continue
        for quantity in quantities:
            if quantity["subject_id"] != target["subject_id"]:
                continue
            if quantity["role"] not in _COMPONENT_ROLES:
                continue
            if quantity.get("provenance") != "explicit_source":
                continue
            if quantity.get("component") is not None or quantity.get("direction"):
                continue
            found.append(
                {
                    "ambiguity_id": f"amb_direction_{quantity['quantity_id']}",
                    "kind": "direction",
                    "description": (
                        "a signed component is queried while a source quantity "
                        "it depends on leaves its direction uncommitted, so the "
                        "direction must be confirmed before a signed answer "
                        "can be delivered"
                    ),
                    "blocking": True,
                    "referenced_ids": [quantity["quantity_id"], query["query_id"]],
                    "evidence_refs": [],
                }
            )
    return found


def _interaction_owned_binding(
    *,
    subject: str,
    role: str,
    interval_id: str | None,
    gold: Any,
    primitives_by_entity: Mapping[str, str],
) -> tuple[str, str] | None:
    """Resolve the typed owner of one interaction-owned constitutive parameter.

    Returns ``(owner_entity_id, relation_role)`` when exactly one typed
    interaction of an owning kind ties the stated subject to exactly one
    body-like counterpart, and ``None`` when no owning relation mentions this
    role at all.  Two candidate owners, or an owning relation whose counterpart
    is not a body, fail closed: guessing which body a stiffness belongs to would
    invent structure the source never stated.
    """

    # A parameter the source already states on a body-like subject has its
    # typed owner; only a passive-side statement needs the resolution.
    if primitives_by_entity.get(subject) in _CONSTITUTIVE_OWNER_PRIMITIVES:
        return None
    owners: set[str] = set()
    relation_roles: set[str] = set()
    for relation in gold.relations:
        owned = _INTERACTION_OWNED_CONSTITUTIVE_ROLES.get(relation.kind)
        if owned is None or role not in owned:
            continue
        if subject not in relation.participant_roles:
            continue
        if (
            interval_id is not None
            and relation.segment_role is not None
            and relation.segment_role != interval_id
        ):
            continue
        counterparts = {
            participant
            for participant in relation.participant_roles
            if participant != subject
        }
        if len(counterparts) != 1:
            raise DraftProjectionError(
                DraftProjectionReason.interaction_owner_ambiguous
            )
        counterpart = next(iter(counterparts))
        if primitives_by_entity.get(counterpart) not in _CONSTITUTIVE_OWNER_PRIMITIVES:
            raise DraftProjectionError(
                DraftProjectionReason.interaction_owner_ambiguous
            )
        owners.add(counterpart)
        relation_roles.add(relation.role)
    if not owners:
        return None
    if len(owners) != 1 or len(relation_roles) != 1:
        raise DraftProjectionError(DraftProjectionReason.interaction_owner_ambiguous)
    return next(iter(owners)), next(iter(relation_roles))


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
