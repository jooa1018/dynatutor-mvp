"""Bounded, typed, transactional complete-profile closure planning.

A law in the mechanics catalogue does not fire because *some* structure is
present.  It fires when an exact profile is present: a frame with declared axes,
a point with a typed role, an interaction bound to that frame and interval, the
interaction's own quantities, the unknown symbols those quantities carry, the
state conditions that pin the regime, and the assumption authorities that
license the whole thing.  Adding one of those at a time never reaches a law and,
worse, produces runtime-visible half-built free bodies — a weight with no normal,
a rope pulling on one side only.

This module is the *planning* half of the answer, and it is deliberately the
only half that runs first.  Given one profile and one Draft it reports, without
touching either, exactly which prerequisites the source already grounds, which a
closed server policy could derive, which would have to be generated as unknowns,
and which are missing, ambiguous, or outside what the engine supports.  The plan
is immutable and its disposition is a single closed verdict.

Three properties are load-bearing:

* **Planning never mutates.**  ``plan_complete_profile`` takes a Draft and
  returns a plan; it holds no reference that could write back, and the plan
  records the Draft fingerprint it was computed against so a caller can prove
  the Draft is unchanged.
* **A value is never derived.**  A prerequisite may be classified
  ``generated_unknown``, which asserts only that the symbol must *exist*.  Its
  value stays unknown and is decided by the solver, never by the planner.
* **Nothing here reads identity.**  No case ID, family, split, chapter,
  difficulty, tag, expected system type, expected terminal, expected answer,
  gold graph, filename, or problem text participates in any decision.  Every
  input is typed Draft structure.

The census built on top of these plans reports counts only.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import Enum
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from pydantic import Field

from evaluation.phase56_stage7.contracts import FrozenStrictModel, VersionToken

COMPLETE_PROFILE_PLANNER_VERSION = "phase56-stage7-complete-profile-planner-v3"
COMPLETE_PROFILE_CENSUS_VERSION = "phase56-stage7-complete-profile-census-v1"
COMPLETE_PROFILE_PLAN_SCHEMA = "dynatutor.phase56_stage7.complete_profile_plan"
COMPLETE_PROFILE_PLAN_VERSION = "1.0"


class ProfileId(str, Enum):
    """The bounded set of profiles the census measures.

    A profile is a *shape a law needs*, not a problem family.  Two sources with
    different families reach the same profile when their typed structure agrees,
    and one family can reach different profiles case by case.
    """

    signed_constant_acceleration_1d = "signed_constant_acceleration_1d"
    free_flight_gravity = "free_flight_gravity"
    explicit_resultant_force = "explicit_resultant_force"
    collision_restitution = "collision_restitution"
    fixed_pulley = "fixed_pulley"
    incline_hanging_pulley = "incline_hanging_pulley"
    table_pulley_two_body = "table_pulley_two_body"
    rolling_energy = "rolling_energy"
    particle_work_energy_speed = "particle_work_energy_speed"
    direct_constant_force_work = "direct_constant_force_work"
    polar_kinematics_state = "polar_kinematics_state"
    work_energy = "work_energy"
    impulse_momentum = "impulse_momentum"
    horizontal_contact = "horizontal_contact"
    incline_contact = "incline_contact"
    incline_kinetic_sliding = "incline_kinetic_sliding"
    rigid_fixed_axis = "rigid_fixed_axis"
    rigid_two_point_speed = "rigid_two_point_speed"
    vertical_circle_top_speed = "vertical_circle_top_speed"
    rolling_incline_energy_speed = "rolling_incline_energy_speed"
    # Declared in the order the closure step considers them, so the enum and the
    # signature table cannot drift apart.
    slot_pin_relative_frame = "slot_pin_relative_frame"
    rotating_relative_frame = "rotating_relative_frame"
    relative_translating_frame = "relative_translating_frame"
    spring_vibration_deferred = "spring_vibration_deferred"


class PrerequisiteKind(str, Enum):
    """What kind of record a prerequisite would become if the profile applied."""

    reference_frame = "reference_frame"
    axis = "axis"
    point = "point"
    geometry = "geometry"
    interaction = "interaction"
    interaction_quantity = "interaction_quantity"
    unknown_symbol = "unknown_symbol"
    state_condition = "state_condition"
    constraint = "constraint"
    authority = "authority"
    # Not a record to create: a statement about what the engine declares it can
    # do with the records once they exist.  Kept separate so "the model is
    # complete" and "the engine will answer" never get confused for each other.
    capability = "capability"


class PrerequisiteDisposition(str, Enum):
    """How one prerequisite stands against the Draft as it is."""

    # The source itself states it; it is already in the Draft.
    explicit_source = "explicit_source"
    # A closed server policy can derive it from structure the source states.
    server_derivable = "server_derivable"
    # It must exist as an unknown symbol.  Its *value* stays unknown.
    generated_unknown = "generated_unknown"
    # The source does not state it and no closed policy derives it.
    missing = "missing"
    # More than one reading is equally consistent with the source.
    ambiguous = "ambiguous"
    # The engine declares no capability that could ever consume it.
    unsupported = "unsupported"


class PlanDisposition(str, Enum):
    """The single verdict a plan carries."""

    complete = "complete"
    needs_confirmation = "needs_confirmation"
    insufficient_information = "insufficient_information"
    unsupported = "unsupported"
    not_applicable = "not_applicable"


# A disposition that still lets the profile close.
_CLOSING_DISPOSITIONS: frozenset[PrerequisiteDisposition] = frozenset(
    {
        PrerequisiteDisposition.explicit_source,
        PrerequisiteDisposition.server_derivable,
        PrerequisiteDisposition.generated_unknown,
    }
)

# Precedence when several prerequisites fail differently: the least recoverable
# verdict wins, so an unsupported capability is never reported as a mere gap.
_FAILURE_PRECEDENCE: tuple[PrerequisiteDisposition, ...] = (
    PrerequisiteDisposition.unsupported,
    PrerequisiteDisposition.ambiguous,
    PrerequisiteDisposition.missing,
)
_FAILURE_VERDICT: dict[PrerequisiteDisposition, PlanDisposition] = {
    PrerequisiteDisposition.unsupported: PlanDisposition.unsupported,
    PrerequisiteDisposition.ambiguous: PlanDisposition.needs_confirmation,
    PrerequisiteDisposition.missing: PlanDisposition.insufficient_information,
}

DiagnosticCode = VersionToken


class CompleteProfilePrerequisiteV1(FrozenStrictModel):
    """One typed prerequisite of one profile, and how the Draft answers it."""

    prerequisite_id: DiagnosticCode
    kind: PrerequisiteKind
    disposition: PrerequisiteDisposition


class CompleteProfilePlanV1(FrozenStrictModel):
    """An immutable, non-mutating decision about one profile on one Draft.

    The plan is the contract every later step must clear.  Nothing may create a
    frame, point, interaction, quantity, symbol, state condition, or constraint
    until a plan says `complete`, and then everything the plan names is created
    together or nothing is.
    """

    schema: Literal["dynatutor.phase56_stage7.complete_profile_plan"] = (
        COMPLETE_PROFILE_PLAN_SCHEMA
    )
    version: Literal["1.0"] = COMPLETE_PROFILE_PLAN_VERSION
    planner_version: VersionToken = COMPLETE_PROFILE_PLANNER_VERSION
    profile_id: ProfileId
    disposition: PlanDisposition
    prerequisites: tuple[CompleteProfilePrerequisiteV1, ...] = Field(max_length=64)
    # The exact Draft the plan was computed against.  A caller that re-fingerprints
    # the Draft afterwards proves planning changed nothing.
    draft_fingerprint: str = Field(min_length=64, max_length=64)

    @property
    def complete(self) -> bool:
        return self.disposition is PlanDisposition.complete

    @property
    def structurally_complete(self) -> bool:
        """Every record the profile needs resolves, whatever the engine then does.

        A profile can be fully modelled and still be one the engine declines —
        a deferred readout is exactly that.  Building the structure anyway is
        safe *because* it cannot produce an answer: it only turns a vague
        `underdetermined` into the precise refusal the engine already knows how
        to make.  This property is what separates the two questions.
        """

        return bool(self.prerequisites) and all(
            item.disposition in _CLOSING_DISPOSITIONS
            for item in self.prerequisites
            if item.kind is not PrerequisiteKind.capability
        )

    @property
    def uses_server_derivation(self) -> bool:
        return any(
            item.disposition is PrerequisiteDisposition.server_derivable
            for item in self.prerequisites
        )

    def counts(self) -> dict[str, int]:
        return dict(
            Counter(item.disposition.value for item in self.prerequisites)
        )


def draft_structure_fingerprint(draft: Any) -> str:
    """SHA-256 over the Draft's full typed payload.

    Used only to *prove* the planner did not write.  It carries no corpus text
    onward: the digest is one-way and only ever compared with another digest.
    """

    payload = draft.model_dump(mode="json", warnings="none")
    material = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Typed readers over a Draft.  Every one of these reads structure, never text.
# --------------------------------------------------------------------------


def _roles(draft: Any) -> Counter[str]:
    return Counter(item.role.value for item in draft.quantities)


def _approved_kinds(draft: Any, approved: Iterable[str]) -> set[str]:
    approved_ids = set(approved)
    return {
        item.kind
        for item in draft.assumptions
        if item.assumption_id in approved_ids
        and item.disposition.value == "approved"
    }


def _interaction_kinds(draft: Any) -> Counter[str]:
    return Counter(item.kind.value for item in draft.interactions)


def _geometry_kinds(draft: Any) -> Counter[str]:
    return Counter(item.kind.value for item in draft.geometry)


def _primitives(draft: Any) -> Counter[str]:
    return Counter(item.primitive.value for item in draft.entities)


def _bounded_intervals(draft: Any) -> tuple[Any, ...]:
    return tuple(
        item
        for item in draft.motion_intervals
        if item.start_event_id and item.end_event_id
    )


def _query_role(draft: Any) -> str | None:
    if not draft.queries:
        return None
    return draft.queries[0].target.role.value


def _blocking_ambiguity(draft: Any) -> bool:
    return any(item.blocking for item in draft.ambiguities)


# A source that says "left" and "right" has named the two signs of one
# horizontal axis; "upward" and "downward" name the two signs of one vertical
# axis.  Deriving the axis from that pair is a closed server policy: it decides
# only which axis the source was already talking about, never a number and never
# a sign the source did not state.  Directions that name no spatial axis —
# `along_motion`, `radial`, `clockwise` — are deliberately absent, because they
# need a motion, a centre, or a plane the profile has not established.
_SEMANTIC_AXIS_FAMILIES: Mapping[str, str] = {
    "right": "x",
    "left": "x",
    "upward": "y",
    "downward": "y",
}


def _directed_axis_families(draft: Any) -> frozenset[str]:
    """The spatial axes the source's own stated directions name."""

    families: set[str] = set()
    for quantity in draft.quantities:
        direction = quantity.direction
        if direction is None or getattr(direction, "kind", None) != "semantic":
            continue
        family = _SEMANTIC_AXIS_FAMILIES.get(
            getattr(getattr(direction, "direction", None), "value", "")
        )
        if family is not None:
            families.add(family)
    return frozenset(families)


def _semantic_directions(draft: Any) -> frozenset[str]:
    """Every source-stated semantic direction carried by a quantity."""

    out: set[str] = set()
    for quantity in draft.quantities:
        direction = quantity.direction
        if direction is None or getattr(direction, "kind", None) != "semantic":
            continue
        value = getattr(getattr(direction, "direction", None), "value", None)
        if value is not None:
            out.add(value)
    return frozenset(out)


def _rest_boundary_count(draft: Any) -> int:
    return sum(
        1
        for item in draft.state_conditions
        if item.state.value == "at_rest"
        and item.interval_id is not None
        and item.event_id is not None
        and item.evidence_refs
    )


def _observer_entities(draft: Any) -> tuple[str, ...]:
    """Entities the source itself declares to be reference frames."""

    return tuple(
        sorted(
            item.entity_id
            for item in draft.entities
            if item.primitive.value == "reference_frame"
        )
    )


def _query_component(draft: Any) -> str | None:
    if not draft.queries:
        return None
    return draft.queries[0].target.component.value


def _rotating_relative_profile_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact source-grounded rotating-relative frame shape.

    The source must already identify a moving point-like subject, a rigid
    carrier, one relative-motion topology edge between them, the carrier's
    signed angular velocity, the subject's radial/transverse relative velocity,
    and a radius.  The evaluator may then write down the frame records and the
    otherwise unnamed rotation point; it creates no value and no equation.

    ``None`` means this is not the profile.  Ambiguous carriers, observers,
    motion quantities, or topology edges are represented explicitly so no
    near-miss receives a frame.
    """

    if len(draft.queries) != 1:
        return None
    query = draft.queries[0]
    target = query.target
    if (
        query.shape.value != "scalar"
        or target.role.value != "acceleration"
        or target.component.value not in {"magnitude", "unspecified"}
        or target.frame_id is not None
        or target.direction is not None
        or target.target_quantity_id is None
        or target.interval_id is None
        or target.point_id is not None
    ):
        return None

    targets = tuple(
        item for item in draft.quantities
        if item.quantity_id == target.target_quantity_id
    )
    if len(targets) != 1:
        return None
    target_quantity = targets[0]
    if (
        target_quantity.role is not target.role
        or target_quantity.subject_id != target.subject_id
        or target_quantity.point_id is not None
        or target_quantity.interval_id != target.interval_id
        or target_quantity.event_id != target.event_id
        or target_quantity.component is not target.component
        or target_quantity.shape.value != "scalar"
        or target_quantity.frame_id is not None
        or target_quantity.direction is not None
        or target_quantity.raw_value is not None
        or target_quantity.raw_unit is not None
        or target_quantity.provenance.value != "unknown"
        or target_quantity.symbol_id is None
    ):
        return None

    entities = {item.entity_id: item for item in draft.entities}
    moving = entities.get(target.subject_id)
    if moving is None or moving.primitive.value not in {
        "joint", "particle", "body_component"
    }:
        return None
    if draft.reference_frames or draft.points:
        return None

    interval = next(
        (item for item in draft.motion_intervals if item.interval_id == target.interval_id),
        None,
    )
    if interval is None or target.subject_id not in interval.subject_ids:
        return None

    observers = tuple(
        item.entity_id for item in draft.entities
        if item.primitive.value == "reference_frame"
    )
    if len(observers) != 1:
        disposition = (
            PrerequisiteDisposition.missing
            if not observers else PrerequisiteDisposition.ambiguous
        )
        return {
            "relation": disposition,
            "observer": disposition,
            "point": disposition,
            "frame": disposition,
            "binding": disposition,
        }

    angular = tuple(
        item for item in draft.quantities
        if item.role.value == "angular_velocity"
        and item.interval_id == target.interval_id
        and item.event_id == target.event_id
        and item.raw_value is not None
        and item.raw_unit is not None
        and item.symbol_id is not None
        and item.frame_id is None
        and item.shape.value == "scalar"
        and item.subject_id in entities
        and entities[item.subject_id].primitive.value == "rigid_body"
        and getattr(getattr(item.direction, "direction", None), "value", None)
        in {"clockwise", "counterclockwise"}
    )
    relatives = tuple(
        item for item in draft.quantities
        if item.role.value in {"velocity", "speed"}
        and item.subject_id == target.subject_id
        and item.point_id is None
        and item.interval_id == target.interval_id
        and item.event_id == target.event_id
        and item.raw_value is not None
        and item.raw_unit is not None
        and item.symbol_id is not None
        and item.frame_id is None
        and item.shape.value == "scalar"
        and item.component.value in {"radial", "transverse"}
        and getattr(getattr(item.direction, "direction", None), "value", None)
        == item.component.value
    )
    radii = tuple(
        item for item in draft.quantities
        if item.role.value == "radius"
        and item.subject_id == target.subject_id
        and item.interval_id == target.interval_id
        and item.event_id == target.event_id
        and item.raw_value is not None
        and item.raw_unit is not None
        and item.symbol_id is not None
        and item.shape.value == "scalar"
    )
    if len(angular) != 1 or len(relatives) != 1 or len(radii) != 1:
        disposition = (
            PrerequisiteDisposition.missing
            if not angular or not relatives or not radii
            else PrerequisiteDisposition.ambiguous
        )
        return {
            "relation": disposition,
            "observer": PrerequisiteDisposition.explicit_source,
            "point": disposition,
            "frame": disposition,
            "binding": disposition,
        }
    carrier_id = angular[0].subject_id
    if carrier_id == target.subject_id or carrier_id not in interval.subject_ids:
        return None

    matching_relations = tuple(
        item for item in draft.geometry
        if item.kind.value == "topology_connects"
        and item.interval_id in {None, target.interval_id}
        and not item.quantity_ids
        and item.expression is None
        and len(item.participant_ids) == 2
        and set(item.participant_ids) == {target.subject_id, carrier_id}
    )
    if len(matching_relations) != 1:
        disposition = (
            PrerequisiteDisposition.missing
            if not matching_relations else PrerequisiteDisposition.ambiguous
        )
        return {
            "relation": disposition,
            "observer": PrerequisiteDisposition.explicit_source,
            "point": disposition,
            "frame": disposition,
            "binding": disposition,
        }
    return {
        "relation": PrerequisiteDisposition.explicit_source,
        "observer": PrerequisiteDisposition.explicit_source,
        "point": PrerequisiteDisposition.server_derivable,
        "frame": PrerequisiteDisposition.server_derivable,
        "binding": PrerequisiteDisposition.server_derivable,
    }


def _polar_kinematics_state_profile_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact source-typed instantaneous polar state.

    The projected source carries five scalar state quantities at one explicit
    occurrence inside one otherwise artificial start/finish wrapper.  This
    reader authorises only structural closure: removing that evidence-free
    wrapper, writing the polar frame and radius topology, and creating the six
    value-free component unknowns the existing polar laws require.

    No value, equation, assumption, solver choice, answer metadata, text, or
    corpus identity is read here.  A real boundary/event distinction, competing
    subject or interval, missing direction, or extra typed authority refuses.
    """

    if (
        len(draft.entities) != 1
        or draft.entities[0].primitive.value != "particle"
        or len(draft.motion_intervals) != 1
        or len(draft.queries) != 1
        or draft.reference_frames
        or draft.points
        or draft.geometry
        or draft.interactions
        or draft.constraints
        or draft.state_conditions
        or draft.principle_hints
        or draft.ambiguities
        or draft.unsupported_features
        or draft.figure_dependency.level.value != "none"
        or draft.figure_dependency.missing_information
        or draft.figure_dependency.evidence_refs
    ):
        return None

    particle_id = draft.entities[0].entity_id
    interval = draft.motion_intervals[0]
    interval_id = interval.interval_id
    if (
        tuple(interval.subject_ids) != (particle_id,)
        or interval.frame_id is not None
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
    ):
        return None

    evidence_ids = {item.evidence_id for item in draft.source_evidence}

    def evidenced(item: Any) -> bool:
        refs = set(item.evidence_refs)
        return bool(refs) and refs.issubset(evidence_ids)

    if any(
        item.subject_id != particle_id
        or item.interval_id not in {None, interval_id}
        or item.proposed_role is not None
        or item.proposed_value is not None
        or item.proposed_unit is not None
        or not evidenced(item)
        for item in draft.assumptions
    ):
        return None

    events = {item.event_id: item for item in draft.events}
    if len(events) != 3 or len(events) != len(draft.events):
        return None
    start = events.get(interval.start_event_id)
    finish = events.get(interval.end_event_id)
    occurrences = tuple(
        item
        for item in draft.events
        if item.event_id not in {interval.start_event_id, interval.end_event_id}
    )
    event_shape_exact = (
        start is not None
        and finish is not None
        and len(occurrences) == 1
        and start.kind.value == "start"
        and finish.kind.value == "finish"
        and occurrences[0].kind.value == "other"
        and all(
            tuple(item.subject_ids) == (particle_id,)
            and item.time_quantity_id is None
            and not item.evidence_refs
            for item in draft.events
        )
        and tuple(start.interval_ids) == (interval_id,)
        and tuple(finish.interval_ids) == (interval_id,)
        and not start.occurs_in_interval_ids
        and not finish.occurs_in_interval_ids
        and not occurrences[0].interval_ids
        and tuple(occurrences[0].occurs_in_interval_ids) == (interval_id,)
    )
    instant_id = occurrences[0].event_id if len(occurrences) == 1 else None

    query = draft.queries[0]
    target = query.target
    target_quantity = next(
        (
            item
            for item in draft.quantities
            if item.quantity_id == target.target_quantity_id
        ),
        None,
    )
    query_key = (target.role.value, target.component.value)
    allowed_query_keys = {
        ("velocity", "radial"),
        ("velocity", "transverse"),
        ("velocity", "magnitude"),
        ("speed", "magnitude"),
        ("acceleration", "radial"),
        ("acceleration", "transverse"),
        ("acceleration", "magnitude"),
    }
    query_exact = (
        query.shape.value == "scalar"
        and query_key in allowed_query_keys
        and target.subject_id == particle_id
        and target.point_id is None
        and target.frame_id is None
        and target.interval_id == interval_id
        and target.event_id == instant_id
        and target.direction is None
        and target_quantity is not None
        and target_quantity.subject_id == particle_id
        and target_quantity.point_id is None
        and target_quantity.frame_id is None
        and target_quantity.interval_id == interval_id
        and target_quantity.event_id == instant_id
        and target_quantity.role is target.role
        and target_quantity.component is target.component
        and target_quantity.direction is None
        and target_quantity.shape.value == "scalar"
        and target_quantity.raw_value is None
        and target_quantity.raw_unit is None
        and target_quantity.provenance.value == "unknown"
        and target_quantity.symbol_id is not None
        and not target_quantity.evidence_refs
        and query.output_dimension == target_quantity.dimension
        and not query.evidence_refs
    )
    if not query_exact:
        return None

    symbols_by_quantity: Counter[str | None] = Counter(
        item.quantity_id for item in draft.symbols
    )
    reciprocal_symbols = (
        len(draft.symbols) == len(draft.quantities)
        and all(
            item.symbol_id is not None
            and symbols_by_quantity[item.quantity_id] == 1
            for item in draft.quantities
        )
    )
    if not reciprocal_symbols:
        return None

    known = tuple(
        item
        for item in draft.quantities
        if item.quantity_id != target_quantity.quantity_id
    )
    temporal_exact = (
        event_shape_exact
        and set(interval.evidence_refs).issubset(evidence_ids)
        and instant_id is not None
        and all(
            item.subject_id == particle_id
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id == interval_id
            and item.event_id == instant_id
            and item.shape.value == "scalar"
            for item in known
        )
    )

    expected: Mapping[str, tuple[str, str, frozenset[str]]] = {
        "radius": ("radius", "radial", frozenset({"radial"})),
        "radial_rate": ("velocity", "radial", frozenset({"radial"})),
        "radial_acceleration": (
            "acceleration",
            "radial",
            frozenset({"radial"}),
        ),
        "omega": (
            "angular_velocity",
            "",
            frozenset({"clockwise", "counterclockwise"}),
        ),
        "alpha": (
            "angular_acceleration",
            "",
            frozenset({"clockwise", "counterclockwise"}),
        ),
    }
    dispositions: dict[str, PrerequisiteDisposition] = {}
    selected: dict[str, Any] = {}
    for name, (role, component, directions) in expected.items():
        matches = tuple(
            item
            for item in known
            if item.role.value == role
            and (not component or item.component.value == component)
            and getattr(
                getattr(item.direction, "direction", None), "value", None
            )
            in directions
        )
        if len(matches) != 1:
            dispositions[name] = (
                PrerequisiteDisposition.missing
                if not matches else PrerequisiteDisposition.ambiguous
            )
            continue
        item = matches[0]
        direction = getattr(
            getattr(item.direction, "direction", None), "value", None
        )
        exact_component = (
            item.component.value == (
                direction if role.startswith("angular_") else component
            )
        )
        exact_source = (
            temporal_exact
            and exact_component
            and item.raw_value is not None
            and item.raw_unit is not None
            and item.provenance.value == "explicit_source"
            and item.symbol_id is not None
            and evidenced(item)
        )
        dispositions[name] = (
            PrerequisiteDisposition.explicit_source
            if exact_source else PrerequisiteDisposition.missing
        )
        selected[name] = item

    accounted = {
        item.quantity_id for item in selected.values()
    } | {target_quantity.quantity_id}
    if len(accounted) != len(draft.quantities):
        for name in dispositions:
            if dispositions[name] is PrerequisiteDisposition.explicit_source:
                dispositions[name] = PrerequisiteDisposition.ambiguous

    angular_directions = {
        getattr(
            getattr(selected.get(name), "direction", None),
            "direction",
            None,
        )
        for name in ("omega", "alpha")
        if name in selected
    }
    angular_direction_values = {
        getattr(item, "value", None) for item in angular_directions
    }
    direction_exact = (
        len(angular_direction_values) == 1
        and angular_direction_values
        <= {"clockwise", "counterclockwise"}
        and all(
            dispositions.get(name)
            is PrerequisiteDisposition.explicit_source
            for name in ("radius", "radial_rate", "radial_acceleration", "omega", "alpha")
        )
    )
    dispositions.update(
        temporal_scope=(
            PrerequisiteDisposition.server_derivable
            if temporal_exact else PrerequisiteDisposition.ambiguous
        ),
        direction_binding=(
            PrerequisiteDisposition.server_derivable
            if direction_exact else PrerequisiteDisposition.ambiguous
        ),
        coordinate_entity=PrerequisiteDisposition.server_derivable,
        frame=PrerequisiteDisposition.server_derivable,
        radius_relation=PrerequisiteDisposition.server_derivable,
        query_binding=PrerequisiteDisposition.server_derivable,
        derived_components=PrerequisiteDisposition.generated_unknown,
        capability=PrerequisiteDisposition.explicit_source,
    )
    return dispositions



def _rigid_fixed_axis_point_speed_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact source-typed fixed-axis point-speed topology.

    The projected source carries one rigid body, one point-primitive entity,
    a source-declared point-on-body relation, a source-declared rotates-about
    relation, one valued angular velocity on the body, one valued radius on
    the point, and one value-free speed/velocity magnitude query on the point.
    This reader authorises only structural closure: materialising the typed
    point record, rebinding the radius and the query unknown onto the body's
    fixed-axis scope, and normalising a scalar velocity magnitude into the
    equivalent speed magnitude the existing ``fixed_axis_speed`` law reads.

    No value, equation, assumption, solver choice, answer metadata, text, or
    corpus identity is read here.  Extra bodies, duplicate or missing
    topology, signed component queries, mixed scopes, value-bearing points,
    or unevidenced facts refuse.
    """

    if (
        len(draft.entities) != 2
        or len(draft.motion_intervals) != 1
        or len(draft.queries) != 1
        or draft.reference_frames
        or draft.points
        or draft.interactions
        or draft.constraints
        or draft.state_conditions
        or draft.principle_hints
        or draft.ambiguities
        or draft.unsupported_features
        or draft.figure_dependency.level.value != "none"
        or draft.figure_dependency.missing_information
        or draft.figure_dependency.evidence_refs
    ):
        return None

    bodies = tuple(
        item for item in draft.entities if item.primitive.value == "rigid_body"
    )
    point_entities = tuple(
        item for item in draft.entities if item.primitive.value == "point"
    )
    if len(bodies) != 1 or len(point_entities) != 1:
        return None
    body_id = bodies[0].entity_id
    point_id = point_entities[0].entity_id
    subject_ids = {body_id, point_id}

    interval = draft.motion_intervals[0]
    interval_id = interval.interval_id
    if (
        set(interval.subject_ids) != subject_ids
        or len(interval.subject_ids) != 2
        or interval.frame_id is not None
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
    ):
        return None

    evidence_ids = {item.evidence_id for item in draft.source_evidence}

    def evidenced(item: Any) -> bool:
        refs = set(item.evidence_refs)
        return bool(refs) and refs.issubset(evidence_ids)

    if any(
        item.subject_id not in subject_ids
        or item.interval_id not in {None, interval_id}
        or item.proposed_role is not None
        or item.proposed_value is not None
        or item.proposed_unit is not None
        or not evidenced(item)
        for item in draft.assumptions
    ):
        return None

    events = {item.event_id: item for item in draft.events}
    if len(draft.events) != 2 or len(events) != 2:
        return None
    start = events.get(interval.start_event_id)
    finish = events.get(interval.end_event_id)
    if (
        start is None
        or finish is None
        or start.kind.value != "start"
        or finish.kind.value != "finish"
        or any(
            set(item.subject_ids) != subject_ids
            or item.time_quantity_id is not None
            or tuple(item.interval_ids) != (interval_id,)
            or item.occurs_in_interval_ids
            for item in draft.events
        )
    ):
        return None

    lies_on = tuple(
        item for item in draft.geometry if item.kind.value == "lies_on"
    )
    coincident = tuple(
        item for item in draft.geometry if item.kind.value == "coincident"
    )
    if len(draft.geometry) != 2 or any(
        set(item.participant_ids) != subject_ids
        or len(item.participant_ids) != 2
        or item.interval_id not in {None, interval_id}
        or item.quantity_ids
        or item.expression is not None
        for item in draft.geometry
    ):
        return None
    topology = {
        "point_topology": (
            PrerequisiteDisposition.explicit_source
            if len(lies_on) == 1
            else (
                PrerequisiteDisposition.ambiguous
                if lies_on
                else PrerequisiteDisposition.missing
            )
        ),
        "fixed_axis_topology": (
            PrerequisiteDisposition.explicit_source
            if len(coincident) == 1
            else (
                PrerequisiteDisposition.ambiguous
                if coincident
                else PrerequisiteDisposition.missing
            )
        ),
    }

    query = draft.queries[0]
    target = query.target
    target_quantity = next(
        (
            item
            for item in draft.quantities
            if item.quantity_id == target.target_quantity_id
        ),
        None,
    )
    query_exact = (
        query.shape.value == "scalar"
        and (target.role.value, target.component.value)
        in {("velocity", "magnitude"), ("speed", "magnitude")}
        and target.subject_id == point_id
        and target.point_id is None
        and target.frame_id is None
        and target.interval_id == interval_id
        and target.event_id is None
        and target.direction is None
        and target_quantity is not None
        and target_quantity.subject_id == point_id
        and target_quantity.point_id is None
        and target_quantity.frame_id is None
        and target_quantity.interval_id == interval_id
        and target_quantity.event_id is None
        and target_quantity.role is target.role
        and target_quantity.component is target.component
        and target_quantity.direction is None
        and target_quantity.shape.value == "scalar"
        and target_quantity.raw_value is None
        and target_quantity.raw_unit is None
        and target_quantity.provenance.value == "unknown"
        and target_quantity.symbol_id is not None
        and not target_quantity.evidence_refs
        and query.output_dimension == target_quantity.dimension
        and not query.evidence_refs
    )
    if not query_exact:
        return None

    symbols_by_quantity: Counter[str | None] = Counter(
        item.quantity_id for item in draft.symbols
    )
    if len(draft.symbols) != len(draft.quantities) or any(
        item.symbol_id is None or symbols_by_quantity[item.quantity_id] != 1
        for item in draft.quantities
    ):
        return None

    known = tuple(
        item
        for item in draft.quantities
        if item.quantity_id != target_quantity.quantity_id
    )

    def scoped(item: Any) -> bool:
        return (
            item.point_id is None
            and item.frame_id is None
            and item.interval_id in {None, interval_id}
            and item.event_id is None
            and item.shape.value == "scalar"
        )

    def valued_source(item: Any) -> bool:
        return (
            item.raw_value is not None
            and item.raw_unit is not None
            and item.provenance.value == "explicit_source"
            and item.symbol_id is not None
            and evidenced(item)
        )

    dispositions: dict[str, PrerequisiteDisposition] = dict(topology)
    selected: dict[str, Any] = {}

    angular = tuple(
        item for item in known if item.role.value == "angular_velocity"
    )
    angular_exact = None
    if len(angular) == 1:
        item = angular[0]
        direction = getattr(
            getattr(item.direction, "direction", None), "value", None
        )
        angular_exact = (
            item.subject_id == body_id
            and scoped(item)
            and item.interval_id == interval_id
            and valued_source(item)
            and (
                (
                    direction is None
                    and item.component.value in {"unspecified", "magnitude"}
                )
                or (
                    direction in {"clockwise", "counterclockwise"}
                    and item.component.value == direction
                )
            )
        )
    dispositions["angular_velocity"] = (
        PrerequisiteDisposition.explicit_source
        if angular_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(angular) > 1
            else PrerequisiteDisposition.missing
        )
    )
    if len(angular) == 1:
        selected["angular_velocity"] = angular[0]

    radii = tuple(item for item in known if item.role.value == "radius")
    radius_exact = None
    if len(radii) == 1:
        item = radii[0]
        radius_exact = (
            item.subject_id == point_id
            and scoped(item)
            and item.component.value == "unspecified"
            and item.direction is None
            and valued_source(item)
        )
    dispositions["radius"] = (
        PrerequisiteDisposition.explicit_source
        if radius_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(radii) > 1
            else PrerequisiteDisposition.missing
        )
    )
    if len(radii) == 1:
        selected["radius"] = radii[0]

    # An unrelated valued mass on the body is tolerated but never consumed.
    masses = tuple(item for item in known if item.role.value == "mass")
    if any(
        item.subject_id != body_id or not scoped(item) or not valued_source(item)
        for item in masses
    ) or len(masses) > 1:
        return None

    accounted = {
        item.quantity_id for item in (*selected.values(), *masses)
    } | {target_quantity.quantity_id}
    if len(accounted) != len(draft.quantities):
        return None

    dispositions.update(
        material_point=PrerequisiteDisposition.server_derivable,
        speed_normalization=PrerequisiteDisposition.server_derivable,
        query_binding=PrerequisiteDisposition.server_derivable,
        point_speed_symbol=PrerequisiteDisposition.generated_unknown,
        capability=PrerequisiteDisposition.explicit_source,
    )
    return dispositions


def _rigid_two_point_speed_transfer_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact source-typed two-point speed-transfer topology.

    One rigid body rotates about one source-declared fixed centre point —
    stated by the source's own rotates-about relation, which projects as the
    single ``coincident`` geometry record between the body and the centre —
    and carries exactly two source-declared on-body points, each with its
    own source-valued rotation radius, every quantity bound to the same
    source-declared instant of the single motion interval.  The source
    states one point's scalar undirected speed and asks for the other
    point's scalar speed/velocity magnitude at that same instant.

    The shared centre is what licenses reading both radii against one
    angular speed: ``v = |omega| r`` holds for both points only when both
    rotation radii are measured from the same fixed centre, and the only
    typed proof of that identity is the body's sole rotation-centre
    relation.  A centre that is merely a floating context entity, a centre
    with no typed rotation relation, a centre named only by a label or by
    the problem text, or two candidate centres never license the coupling:
    without exactly one typed centre this reader refuses, whatever the two
    radii would happen to compute.  The centre itself must stay motionless
    context — it may not be an interval actor, an event subject, a query
    subject, or the subject of any quantity or assumption.

    This reader authorises only structural closure: materialising the two
    typed material points the point-on-body relations already state,
    rebinding both radii and both scalar speed magnitudes onto the body's
    scope, and generating the single value-free shared angular-speed unknown
    through which the existing ``fixed_axis_speed`` law couples the two
    points.  No value, equation, assumption, solver choice, answer metadata,
    text, or corpus identity is read here.
    """

    if (
        len(draft.motion_intervals) != 1
        or len(draft.queries) != 1
        or len(draft.events) != 3
        or draft.reference_frames
        or draft.points
        or draft.interactions
        or draft.constraints
        or draft.state_conditions
        or draft.principle_hints
        or draft.ambiguities
        or draft.unsupported_features
        or draft.figure_dependency.level.value != "none"
        or draft.figure_dependency.missing_information
        or draft.figure_dependency.evidence_refs
    ):
        return None

    bodies = tuple(
        item for item in draft.entities if item.primitive.value == "rigid_body"
    )
    point_entities = tuple(
        item for item in draft.entities if item.primitive.value == "point"
    )
    if (
        len(bodies) != 1
        or len(point_entities) != 3
        or len(draft.entities) != 1 + len(point_entities)
    ):
        return None
    body_id = bodies[0].entity_id
    point_ids = {item.entity_id for item in point_entities}

    lies_on = tuple(
        item for item in draft.geometry if item.kind.value == "lies_on"
    )
    centre_relations = tuple(
        item for item in draft.geometry if item.kind.value == "coincident"
    )
    if len(draft.geometry) != len(lies_on) + len(centre_relations):
        return None
    interval = draft.motion_intervals[0]
    interval_id = interval.interval_id
    if any(
        len(item.participant_ids) != 2
        or body_id not in item.participant_ids
        or not (set(item.participant_ids) - {body_id}) <= point_ids
        or item.interval_id not in {None, interval_id}
        or item.quantity_ids
        or item.expression is not None
        for item in (*lies_on, *centre_relations)
    ):
        return None
    bound_ids = tuple(
        sorted(
            {
                participant
                for item in lies_on
                for participant in item.participant_ids
                if participant != body_id
            }
        )
    )
    topology = (
        PrerequisiteDisposition.explicit_source
        if len(lies_on) == 2 and len(bound_ids) == 2
        else (
            PrerequisiteDisposition.ambiguous
            if len(lies_on) > 2 or len(lies_on) != len(bound_ids)
            else PrerequisiteDisposition.missing
        )
    )
    if topology is not PrerequisiteDisposition.explicit_source:
        return None
    floating_ids = point_ids - set(bound_ids)
    if len(floating_ids) != 1:
        return None
    centre_id = next(iter(floating_ids))
    centre_bound_ids = {
        participant
        for item in centre_relations
        for participant in item.participant_ids
        if participant != body_id
    }
    centre_authority = (
        PrerequisiteDisposition.explicit_source
        if len(centre_relations) == 1 and centre_bound_ids == {centre_id}
        else (
            PrerequisiteDisposition.ambiguous
            if len(centre_relations) > 1
            or (centre_relations and centre_bound_ids != {centre_id})
            else PrerequisiteDisposition.missing
        )
    )
    if centre_authority is not PrerequisiteDisposition.explicit_source:
        return None
    subject_ids = {body_id, *bound_ids}

    if (
        set(interval.subject_ids) != subject_ids
        or len(interval.subject_ids) != 3
        or interval.frame_id is not None
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
    ):
        return None

    events = {item.event_id: item for item in draft.events}
    if len(events) != 3:
        return None
    start = events.get(interval.start_event_id)
    finish = events.get(interval.end_event_id)
    instants = tuple(
        item
        for item in draft.events
        if item.event_id
        not in {interval.start_event_id, interval.end_event_id}
    )
    if (
        start is None
        or finish is None
        or len(instants) != 1
        or start.kind.value != "start"
        or finish.kind.value != "finish"
        or instants[0].kind.value != "other"
        or any(
            set(item.subject_ids) != subject_ids
            or item.time_quantity_id is not None
            for item in draft.events
        )
        or tuple(start.interval_ids) != (interval_id,)
        or tuple(finish.interval_ids) != (interval_id,)
        or start.occurs_in_interval_ids
        or finish.occurs_in_interval_ids
        or instants[0].interval_ids
        or tuple(instants[0].occurs_in_interval_ids) != (interval_id,)
    ):
        return None
    instant_id = instants[0].event_id

    evidence_ids = {item.evidence_id for item in draft.source_evidence}

    def evidenced(item: Any) -> bool:
        refs = set(item.evidence_refs)
        return bool(refs) and refs.issubset(evidence_ids)

    if any(
        item.subject_id not in subject_ids
        or item.interval_id not in {None, interval_id}
        or item.proposed_role is not None
        or item.proposed_value is not None
        or item.proposed_unit is not None
        or not evidenced(item)
        for item in draft.assumptions
    ):
        return None

    def scoped(item: Any) -> bool:
        return (
            item.point_id is None
            and item.frame_id is None
            and item.interval_id == interval_id
            and item.event_id == instant_id
            and item.shape.value == "scalar"
        )

    def valued_source(item: Any) -> bool:
        return (
            item.raw_value is not None
            and item.raw_unit is not None
            and item.provenance.value == "explicit_source"
            and item.symbol_id is not None
            and evidenced(item)
        )

    query = draft.queries[0]
    target = query.target
    target_quantity = next(
        (
            item
            for item in draft.quantities
            if item.quantity_id == target.target_quantity_id
        ),
        None,
    )
    query_exact = (
        query.shape.value == "scalar"
        and (target.role.value, target.component.value)
        in {("velocity", "magnitude"), ("speed", "magnitude")}
        and target.subject_id in bound_ids
        and target.point_id is None
        and target.frame_id is None
        and target.interval_id == interval_id
        and target.event_id == instant_id
        and target.direction is None
        and target_quantity is not None
        and target_quantity.subject_id == target.subject_id
        and scoped(target_quantity)
        and target_quantity.role is target.role
        and target_quantity.component is target.component
        and target_quantity.direction is None
        and target_quantity.raw_value is None
        and target_quantity.raw_unit is None
        and target_quantity.provenance.value == "unknown"
        and target_quantity.symbol_id is not None
        and not target_quantity.evidence_refs
        and query.output_dimension == target_quantity.dimension
        and not query.evidence_refs
    )
    if not query_exact:
        return None
    query_point_id = target.subject_id
    known_point_id = next(
        item for item in bound_ids if item != query_point_id
    )

    symbols_by_quantity: Counter[str | None] = Counter(
        item.quantity_id for item in draft.symbols
    )
    if len(draft.symbols) != len(draft.quantities) or any(
        item.symbol_id is None or symbols_by_quantity[item.quantity_id] != 1
        for item in draft.quantities
    ):
        return None

    known = tuple(
        item
        for item in draft.quantities
        if item.quantity_id != target_quantity.quantity_id
    )

    dispositions: dict[str, PrerequisiteDisposition] = {
        "two_point_topology": topology,
        "rotation_centre_authority": centre_authority,
    }

    radii = tuple(item for item in known if item.role.value == "radius")
    radii_by_subject = {item.subject_id: item for item in radii}
    radius_exact = (
        len(radii) == 2
        and set(radii_by_subject) == set(bound_ids)
        and all(
            scoped(item)
            and item.component.value == "unspecified"
            and item.direction is None
            and valued_source(item)
            for item in radii
        )
    )
    dispositions["radius_pair"] = (
        PrerequisiteDisposition.explicit_source
        if radius_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(radii) > 2
            else PrerequisiteDisposition.missing
        )
    )

    speeds = tuple(
        item for item in known if item.role.value in {"velocity", "speed"}
    )
    speed_exact = (
        len(speeds) == 1
        and speeds[0].subject_id == known_point_id
        and scoped(speeds[0])
        and speeds[0].component.value in {"unspecified", "magnitude"}
        and speeds[0].direction is None
        and valued_source(speeds[0])
    )
    dispositions["known_point_speed"] = (
        PrerequisiteDisposition.explicit_source
        if speed_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(speeds) > 1
            else PrerequisiteDisposition.missing
        )
    )

    accounted = {item.quantity_id for item in (*radii, *speeds)} | {
        target_quantity.quantity_id
    }
    if len(accounted) != len(draft.quantities):
        return None

    dispositions.update(
        material_points=PrerequisiteDisposition.server_derivable,
        speed_normalization=PrerequisiteDisposition.server_derivable,
        query_binding=PrerequisiteDisposition.server_derivable,
        shared_angular_speed_symbol=PrerequisiteDisposition.generated_unknown,
        point_speed_symbol=PrerequisiteDisposition.generated_unknown,
        capability=PrerequisiteDisposition.explicit_source,
    )
    return dispositions


def _rigid_two_point_speed_prerequisite(name: str) -> "_Resolver":
    def resolve(facts: "_DraftFacts") -> PrerequisiteDisposition:
        if facts.rigid_two_point_speed_profile is None:
            return PrerequisiteDisposition.missing
        return facts.rigid_two_point_speed_profile[name]

    return resolve


def _collision_restitution_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact source-typed 1D restitution-impact topology.

    Exactly two closed bodies collide: one source-declared collision
    interaction spans one motion interval whose own boundary events are the
    typed ``collision_start`` and ``collision_end`` of exactly those two
    bodies.  Each body carries one source-valued mass and one source-valued
    approach speed read at the collision start, stated along the horizontal
    line of impact by its own semantic direction (left or right); one
    source-valued restitution coefficient binds the impact; and the source
    asks for exactly one body's signed x-component separation velocity at
    the collision end — the compiler's Lane B contract is one query per
    run, so a two-question impact stays out of reach rather than half
    answered.  The partner's separation velocity is the transaction's
    single generated value-free unknown.

    The conservation authority is the projection's own closed-policy
    ``external_impulse_negligible`` derivation — a statement of the typed
    model's completeness (the collision is the entire interaction system
    over its own interval), never a guess — and this reader requires both
    per-body authorities verbatim.  A third entity, a second interaction,
    any geometry, a gravity authority, an unpaired mass or velocity, a
    magnitude query, or a coefficient stated twice all refuse.

    This reader authorises only structural closure: materialising the world
    frame, binding each stated approach direction onto that frame's signed
    axis, linking the impact's own quantities into the collision record,
    and generating the partner's value-free separation unknown when only
    one body's velocity is asked.  The existing
    ``system_momentum_conservation`` and ``direct_restitution`` generic
    laws do all solving.  No value, equation, solver choice, answer
    metadata, text, or corpus identity is read here.
    """

    if (
        len(draft.motion_intervals) != 1
        or len(draft.queries) != 1
        or len(draft.events) != 2
        or len(draft.interactions) != 1
        or len(draft.assumptions) != 2
        or len(draft.entities) != 2
        or draft.reference_frames
        or draft.points
        or draft.geometry
        or draft.constraints
        or draft.state_conditions
        or draft.principle_hints
        or draft.ambiguities
        or draft.unsupported_features
        or draft.figure_dependency.level.value != "none"
        or draft.figure_dependency.missing_information
        or draft.figure_dependency.evidence_refs
    ):
        return None

    if any(
        item.primitive.value not in {"particle", "rigid_body"}
        for item in draft.entities
    ):
        return None
    body_ids = {item.entity_id for item in draft.entities}

    interval = draft.motion_intervals[0]
    interval_id = interval.interval_id
    if (
        set(interval.subject_ids) != body_ids
        or len(interval.subject_ids) != 2
        or interval.frame_id is not None
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
    ):
        return None

    events = {item.event_id: item for item in draft.events}
    start = events.get(interval.start_event_id)
    end = events.get(interval.end_event_id)
    if (
        len(events) != 2
        or start is None
        or end is None
        or start.kind.value != "collision_start"
        or end.kind.value != "collision_end"
        or any(
            set(item.subject_ids) != body_ids
            or item.time_quantity_id is not None
            or tuple(item.interval_ids) != (interval_id,)
            or item.occurs_in_interval_ids
            for item in draft.events
        )
    ):
        return None
    start_id, end_id = start.event_id, end.event_id

    impact = draft.interactions[0]
    if (
        impact.kind.value != "collision"
        or set(impact.participant_ids) != body_ids
        or len(impact.participant_ids) != 2
        or impact.point_ids
        or impact.frame_id is not None
        or impact.interval_id != interval_id
        or impact.event_id is not None
        or impact.quantity_ids
    ):
        return None

    evidence_ids = {item.evidence_id for item in draft.source_evidence}

    def evidenced(item: Any) -> bool:
        refs = set(item.evidence_refs)
        return bool(refs) and refs.issubset(evidence_ids)

    authority_subjects = set()
    for authority in draft.assumptions:
        if (
            authority.kind != "external_impulse_negligible"
            or getattr(authority.disposition, "value", authority.disposition)
            != "approved"
            or authority.subject_id not in body_ids
            or authority.interval_id != interval_id
            or authority.proposed_role is not None
            or authority.proposed_value is not None
            or authority.proposed_unit is not None
            or not evidenced(authority)
        ):
            return None
        authority_subjects.add(authority.subject_id)
    if authority_subjects != body_ids:
        return None

    def valued_source(item: Any) -> bool:
        return (
            item.raw_value is not None
            and item.raw_unit is not None
            and item.provenance.value == "explicit_source"
            and item.symbol_id is not None
            and evidenced(item)
        )

    query = draft.queries[0]
    target = query.target
    target_quantity = next(
        (
            item
            for item in draft.quantities
            if item.quantity_id == target.target_quantity_id
        ),
        None,
    )
    query_exact = (
        query.shape.value == "scalar"
        and getattr(query, "objective", None) is None
        and target.role.value == "velocity"
        and target.component.value == "x"
        and target.subject_id in body_ids
        and target.point_id is None
        and target.frame_id is None
        and target.interval_id == interval_id
        and target.event_id == end_id
        and target.direction is None
        and target_quantity is not None
        and target_quantity.subject_id == target.subject_id
        and target_quantity.point_id is None
        and target_quantity.frame_id is None
        and target_quantity.interval_id == interval_id
        and target_quantity.event_id == end_id
        and target_quantity.role is target.role
        and target_quantity.component is target.component
        and target_quantity.direction is None
        and target_quantity.shape.value == "scalar"
        and target_quantity.raw_value is None
        and target_quantity.raw_unit is None
        and target_quantity.provenance.value == "unknown"
        and target_quantity.symbol_id is not None
        and not target_quantity.evidence_refs
        and query.output_dimension == target_quantity.dimension
        and not query.evidence_refs
    )
    if not query_exact:
        return None

    symbols_by_quantity: Counter[str | None] = Counter(
        item.quantity_id for item in draft.symbols
    )
    if len(draft.symbols) != len(draft.quantities) or any(
        item.symbol_id is None or symbols_by_quantity[item.quantity_id] != 1
        for item in draft.quantities
    ):
        return None

    unknown_ids = {
        query.target.target_quantity_id for query in draft.queries
    }
    known = tuple(
        item
        for item in draft.quantities
        if item.quantity_id not in unknown_ids
    )

    dispositions: dict[str, PrerequisiteDisposition] = {
        "collision_topology": PrerequisiteDisposition.explicit_source,
        "impact_boundary_events": PrerequisiteDisposition.explicit_source,
        "isolated_impact_authority": PrerequisiteDisposition.explicit_source,
    }

    masses = tuple(item for item in known if item.role.value == "mass")
    masses_by_subject = {item.subject_id: item for item in masses}
    mass_exact = (
        len(masses) == 2
        and set(masses_by_subject) == body_ids
        and all(
            item.point_id is None
            and item.frame_id is None
            and item.interval_id in {None, interval_id}
            and item.event_id is None
            and item.shape.value == "scalar"
            and item.component.value == "unspecified"
            and item.direction is None
            and valued_source(item)
            for item in masses
        )
    )
    dispositions["mass_pair"] = (
        PrerequisiteDisposition.explicit_source
        if mass_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(masses) > 2
            else PrerequisiteDisposition.missing
        )
    )

    approach = tuple(
        item for item in known if item.role.value in {"velocity", "speed"}
    )
    approach_by_subject = {item.subject_id: item for item in approach}

    def approach_exact(item: Any) -> bool:
        direction = getattr(
            getattr(item.direction, "direction", None), "value", None
        )
        return (
            item.role.value == "velocity"
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id == interval_id
            and item.event_id == start_id
            and item.shape.value == "scalar"
            and item.component.value == "unspecified"
            and direction in {"left", "right"}
            and valued_source(item)
        )

    approach_ok = (
        len(approach) == 2
        and set(approach_by_subject) == body_ids
        and all(approach_exact(item) for item in approach)
    )
    dispositions["approach_velocities"] = (
        PrerequisiteDisposition.explicit_source
        if approach_ok
        else (
            PrerequisiteDisposition.ambiguous
            if len(approach) > 2
            else PrerequisiteDisposition.missing
        )
    )

    coefficients = tuple(
        item for item in known if item.role.value == "coefficient_restitution"
    )
    coefficient_exact = (
        len(coefficients) == 1
        and coefficients[0].subject_id in body_ids
        and coefficients[0].point_id is None
        and coefficients[0].frame_id is None
        and coefficients[0].interval_id in {None, interval_id}
        and coefficients[0].event_id is None
        and coefficients[0].shape.value == "scalar"
        and coefficients[0].component.value == "unspecified"
        and coefficients[0].direction is None
        and valued_source(coefficients[0])
    )
    dispositions["restitution_coefficient"] = (
        PrerequisiteDisposition.explicit_source
        if coefficient_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(coefficients) > 1
            else PrerequisiteDisposition.missing
        )
    )

    accounted = {
        item.quantity_id for item in (*masses, *approach, *coefficients)
    } | unknown_ids
    if len(accounted) != len(draft.quantities):
        return None

    dispositions.update(
        world_frame=PrerequisiteDisposition.server_derivable,
        axis_binding=PrerequisiteDisposition.server_derivable,
        query_binding=PrerequisiteDisposition.server_derivable,
        partner_post_velocity_symbol=PrerequisiteDisposition.generated_unknown,
        capability=PrerequisiteDisposition.explicit_source,
    )
    return dispositions


def _collision_restitution_prerequisite(name: str) -> "_Resolver":
    def resolve(facts: "_DraftFacts") -> PrerequisiteDisposition:
        if facts.collision_restitution_profile is None:
            return PrerequisiteDisposition.missing
        return facts.collision_restitution_profile[name]

    return resolve


def _vertical_circle_top_speed_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact vertical-circle limiting-contact minimum topology.

    One particle on one circular track, one source-valued rotation radius,
    an approved server-valued uniform-gravity authority, and a value-free
    scalar speed-magnitude query at the source-declared highest point —
    where the *question itself* is typed as a minimum and the *boundary it
    asks about* is typed as well.  Four typed authorities must all be
    present, and each one carries load:

    * the query's own ``minimum`` objective — a plain speed question at the
      top of a circle has no boundary reading, and answering it with one
      would answer a question the source never asked;
    * the contact's ``inward`` side — only an inside track's push toward
      the centre makes ``v^2 >= g r`` the admissible set whose minimum is
      the boundary; an outside or unstated orientation bounds the other
      way and refuses;
    * a ``contact``/``touching`` state condition on the particle over the
      motion interval — the typed statement that contact is maintained;
    * a ``boundary``/``active`` state condition on the particle at the
      highest-point instant — the typed statement that the question sits
      exactly on the contact-maintenance boundary (N = 0).

    Only with all four does the existing
    ``vertical_circle_top_minimum_speed`` law's equality ``v^2 = g r``
    state the asked-for boundary.  Any extra quantity, a missing or
    outward orientation, a missing objective, or missing boundary states
    make the question a different one and refuse.

    The transaction materialises only the gravity magnitude the approved
    authority already carries; the law does all solving.  No value beyond
    that authority, no equation, solver choice, answer metadata, text, or
    corpus identity is read here.
    """

    if (
        len(draft.entities) != 2
        or len(draft.motion_intervals) != 1
        or len(draft.queries) != 1
        or len(draft.events) != 3
        or len(draft.interactions) != 1
        or len(draft.assumptions) != 1
        or len(draft.state_conditions) != 2
        or draft.reference_frames
        or draft.points
        or draft.geometry
        or draft.constraints
        or draft.principle_hints
        or draft.ambiguities
        or draft.unsupported_features
        or draft.figure_dependency.level.value != "none"
        or draft.figure_dependency.missing_information
        or draft.figure_dependency.evidence_refs
    ):
        return None

    particles = tuple(
        item for item in draft.entities if item.primitive.value == "particle"
    )
    surfaces = tuple(
        item for item in draft.entities if item.primitive.value == "surface"
    )
    if len(particles) != 1 or len(surfaces) != 1:
        return None
    particle_id = particles[0].entity_id
    surface_id = surfaces[0].entity_id

    interval = draft.motion_intervals[0]
    interval_id = interval.interval_id
    if (
        tuple(interval.subject_ids) != (particle_id,)
        or interval.frame_id is not None
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
    ):
        return None

    contact = draft.interactions[0]
    if (
        contact.kind.value != "contact"
        or set(contact.participant_ids) != {particle_id, surface_id}
        or len(contact.participant_ids) != 2
        or contact.point_ids
        or contact.frame_id is not None
        or contact.interval_id not in {None, interval_id}
        or contact.event_id is not None
        or contact.quantity_ids
    ):
        return None
    side = getattr(getattr(contact, "contact_side", None), "value", None)
    if side == "outward":
        # A stated outside track bounds the speed the other way: there is no
        # minimum-to-maintain-contact boundary at the top.  Different
        # physics, not a missing slot — this profile simply does not apply.
        return None
    orientation = (
        PrerequisiteDisposition.explicit_source
        if side == "inward"
        else PrerequisiteDisposition.missing
    )
    if orientation is not PrerequisiteDisposition.explicit_source:
        return None

    events = {item.event_id: item for item in draft.events}
    if len(events) != 3:
        return None
    start = events.get(interval.start_event_id)
    finish = events.get(interval.end_event_id)
    instants = tuple(
        item
        for item in draft.events
        if item.event_id
        not in {interval.start_event_id, interval.end_event_id}
    )
    if (
        start is None
        or finish is None
        or len(instants) != 1
        or start.kind.value != "start"
        or finish.kind.value != "finish"
        or instants[0].kind.value != "highest_point"
        or any(
            tuple(item.subject_ids) != (particle_id,)
            or item.time_quantity_id is not None
            for item in draft.events
        )
        or tuple(start.interval_ids) != (interval_id,)
        or tuple(finish.interval_ids) != (interval_id,)
        or start.occurs_in_interval_ids
        or finish.occurs_in_interval_ids
        or instants[0].interval_ids
        or tuple(instants[0].occurs_in_interval_ids) != (interval_id,)
    ):
        return None
    top_id = instants[0].event_id

    evidence_ids = {item.evidence_id for item in draft.source_evidence}

    def evidenced(item: Any) -> bool:
        refs = set(item.evidence_refs)
        return bool(refs) and refs.issubset(evidence_ids)

    authority = draft.assumptions[0]
    authority_exact = (
        authority.kind == "constant_gravity"
        and getattr(authority.disposition, "value", authority.disposition)
        == "approved"
        and authority.subject_id == particle_id
        and authority.interval_id == interval_id
        and str(getattr(authority.proposed_role, "value", authority.proposed_role))
        == "gravity"
        and authority.proposed_value is not None
        and authority.proposed_unit is not None
        and evidenced(authority)
    )
    if not authority_exact:
        return None

    touching_states = tuple(
        item
        for item in draft.state_conditions
        if item.kind.value == "contact" and item.state.value == "touching"
    )
    boundary_states = tuple(
        item
        for item in draft.state_conditions
        if item.kind.value == "boundary" and item.state.value == "active"
    )
    if len(touching_states) + len(boundary_states) != len(
        draft.state_conditions
    ):
        return None
    touching_exact = (
        len(touching_states) == 1
        and touching_states[0].subject_id == particle_id
        and touching_states[0].interval_id == interval_id
        and touching_states[0].event_id is None
        and touching_states[0].expression is None
        and not touching_states[0].quantity_ids
        and evidenced(touching_states[0])
    )
    boundary_exact = (
        len(boundary_states) == 1
        and boundary_states[0].subject_id == particle_id
        and boundary_states[0].interval_id == interval_id
        and boundary_states[0].event_id == top_id
        and boundary_states[0].expression is None
        and not boundary_states[0].quantity_ids
        and evidenced(boundary_states[0])
    )
    if not (touching_exact and boundary_exact):
        return None

    def valued_source(item: Any) -> bool:
        return (
            item.raw_value is not None
            and item.raw_unit is not None
            and item.provenance.value == "explicit_source"
            and item.symbol_id is not None
            and evidenced(item)
        )

    query = draft.queries[0]
    target = query.target
    target_quantity = next(
        (
            item
            for item in draft.quantities
            if item.quantity_id == target.target_quantity_id
        ),
        None,
    )
    query_exact = (
        query.shape.value == "scalar"
        and getattr(getattr(query, "objective", None), "value", None)
        == "minimum"
        and target.role.value == "speed"
        and target.component.value == "magnitude"
        and target.subject_id == particle_id
        and target.point_id is None
        and target.frame_id is None
        and target.interval_id == interval_id
        and target.event_id == top_id
        and target.direction is None
        and target_quantity is not None
        and target_quantity.subject_id == particle_id
        and target_quantity.point_id is None
        and target_quantity.frame_id is None
        and target_quantity.interval_id == interval_id
        and target_quantity.event_id == top_id
        and target_quantity.role is target.role
        and target_quantity.component is target.component
        and target_quantity.direction is None
        and target_quantity.shape.value == "scalar"
        and target_quantity.raw_value is None
        and target_quantity.raw_unit is None
        and target_quantity.provenance.value == "unknown"
        and target_quantity.symbol_id is not None
        and not target_quantity.evidence_refs
        and query.output_dimension == target_quantity.dimension
        and not query.evidence_refs
    )
    if not query_exact:
        return None

    symbols_by_quantity: Counter[str | None] = Counter(
        item.quantity_id for item in draft.symbols
    )
    if len(draft.symbols) != len(draft.quantities) or any(
        item.symbol_id is None or symbols_by_quantity[item.quantity_id] != 1
        for item in draft.quantities
    ):
        return None

    known = tuple(
        item
        for item in draft.quantities
        if item.quantity_id != target_quantity.quantity_id
    )
    radii = tuple(item for item in known if item.role.value == "radius")
    radius_exact = (
        len(radii) == 1
        and radii[0].subject_id == particle_id
        and radii[0].point_id is None
        and radii[0].frame_id is None
        and radii[0].interval_id == interval_id
        and radii[0].event_id is None
        and radii[0].shape.value == "scalar"
        and radii[0].component.value == "unspecified"
        and radii[0].direction is None
        and valued_source(radii[0])
    )
    dispositions: dict[str, PrerequisiteDisposition] = {
        "circular_contact": PrerequisiteDisposition.explicit_source,
        "contact_orientation": orientation,
        "minimum_objective": PrerequisiteDisposition.explicit_source,
        "maintained_contact_state": PrerequisiteDisposition.explicit_source,
        "limiting_boundary_state": PrerequisiteDisposition.explicit_source,
        "highest_point_boundary": PrerequisiteDisposition.explicit_source,
        "radius": (
            PrerequisiteDisposition.explicit_source
            if radius_exact
            else (
                PrerequisiteDisposition.ambiguous
                if len(radii) > 1
                else PrerequisiteDisposition.missing
            )
        ),
        "gravity_authority": PrerequisiteDisposition.explicit_source,
    }

    accounted = {item.quantity_id for item in radii} | {
        target_quantity.quantity_id
    }
    if len(accounted) != len(draft.quantities):
        return None

    dispositions.update(
        gravity_quantity=PrerequisiteDisposition.server_derivable,
        capability=PrerequisiteDisposition.explicit_source,
    )
    return dispositions


def _vertical_circle_top_speed_prerequisite(name: str) -> "_Resolver":
    def resolve(facts: "_DraftFacts") -> PrerequisiteDisposition:
        if facts.vertical_circle_top_speed_profile is None:
            return PrerequisiteDisposition.missing
        return facts.vertical_circle_top_speed_profile[name]

    return resolve


def _rolling_incline_energy_speed_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact pure-rolling incline energy-endpoint topology.

    One rigid body rolling on one incline it is tangent to, with approved
    pure-rolling and server-valued uniform-gravity authorities, source-valued
    mass, rotation radius, and central moment of inertia, and one value-free
    scalar speed-magnitude query at the interval's end — in exactly one of
    the two source-declared endpoint sub-shapes:

    * descent: the interval starts at a typed ``release`` event with an
      approved server-valued rest authority, and the source states the
      descended height on the whole interval;
    * climb: the interval starts at a plain ``start`` event with a
      source-valued start speed, ends at a typed ``reaches_condition``
      event, and the source binds the reached height to that end event.

    Under pure rolling the contact force does no work, so the energy
    endpoint balance the existing ``rolling_general_principal_energy`` law
    states closes the shape; the sub-shape decides the height term's sign.
    Any mixture of the two sub-shapes, extra quantity, second body, or
    missing authority refuses.
    """

    if (
        len(draft.entities) != 2
        or len(draft.motion_intervals) != 1
        or len(draft.queries) != 1
        or len(draft.events) != 2
        or len(draft.geometry) != 1
        or len(draft.assumptions) not in {2, 3}
        or len(draft.state_conditions) > 1
        or draft.reference_frames
        or draft.points
        or draft.interactions
        or draft.constraints
        or draft.principle_hints
        or draft.ambiguities
        or draft.unsupported_features
        or draft.figure_dependency.level.value != "none"
        or draft.figure_dependency.missing_information
        or draft.figure_dependency.evidence_refs
    ):
        return None

    bodies = tuple(
        item for item in draft.entities if item.primitive.value == "rigid_body"
    )
    inclines = tuple(
        item for item in draft.entities if item.primitive.value == "incline"
    )
    if len(bodies) != 1 or len(inclines) != 1:
        return None
    body_id = bodies[0].entity_id
    incline_id = inclines[0].entity_id

    interval = draft.motion_intervals[0]
    interval_id = interval.interval_id
    if (
        tuple(interval.subject_ids) != (body_id,)
        or interval.frame_id is not None
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
    ):
        return None

    tangent = draft.geometry[0]
    if (
        tangent.kind.value != "tangent"
        or set(tangent.participant_ids) != {body_id, incline_id}
        or len(tangent.participant_ids) != 2
        or tangent.interval_id not in {None, interval_id}
        or tangent.quantity_ids
        or tangent.expression is not None
    ):
        return None

    events = {item.event_id: item for item in draft.events}
    start = events.get(interval.start_event_id)
    finish = events.get(interval.end_event_id)
    if (
        len(events) != 2
        or start is None
        or finish is None
        or any(
            tuple(item.subject_ids) != (body_id,)
            or item.time_quantity_id is not None
            or tuple(item.interval_ids) != (interval_id,)
            or item.occurs_in_interval_ids
            for item in draft.events
        )
    ):
        return None
    descent = (
        start.kind.value == "release" and finish.kind.value == "finish"
    )
    climb = (
        start.kind.value == "start"
        and finish.kind.value == "reaches_condition"
    )
    if descent == climb:
        return None

    evidence_ids = {item.evidence_id for item in draft.source_evidence}

    def evidenced(item: Any) -> bool:
        refs = set(item.evidence_refs)
        return bool(refs) and refs.issubset(evidence_ids)

    def approved(item: Any) -> bool:
        return (
            getattr(item.disposition, "value", item.disposition) == "approved"
            and item.subject_id == body_id
            and item.interval_id == interval_id
            and evidenced(item)
        )

    by_kind: dict[str, Any] = {}
    for item in draft.assumptions:
        if item.kind in by_kind:
            return None
        by_kind[item.kind] = item
    rolling = by_kind.get("pure_rolling")
    gravity_authority = by_kind.get("constant_gravity")
    rest_authority = by_kind.get("starts_from_rest")
    if (
        rolling is None
        or gravity_authority is None
        or not approved(rolling)
        or rolling.proposed_role is not None
        or rolling.proposed_value is not None
        or rolling.proposed_unit is not None
        or not approved(gravity_authority)
        or str(
            getattr(
                gravity_authority.proposed_role,
                "value",
                gravity_authority.proposed_role,
            )
        )
        != "gravity"
        or gravity_authority.proposed_value is None
        or gravity_authority.proposed_unit is None
        or set(by_kind)
        != (
            {"pure_rolling", "constant_gravity", "starts_from_rest"}
            if descent
            else {"pure_rolling", "constant_gravity"}
        )
    ):
        return None
    if descent and (
        rest_authority is None
        or not approved(rest_authority)
        or str(
            getattr(
                rest_authority.proposed_role,
                "value",
                rest_authority.proposed_role,
            )
        )
        != "velocity"
        or rest_authority.proposed_value is None
        or rest_authority.proposed_unit is None
    ):
        return None

    def scalar_scoped(item: Any) -> bool:
        return (
            item.point_id is None
            and item.frame_id is None
            and item.interval_id == interval_id
            and item.shape.value == "scalar"
        )

    def valued_source(item: Any) -> bool:
        return (
            item.raw_value is not None
            and item.raw_unit is not None
            and item.provenance.value == "explicit_source"
            and item.symbol_id is not None
            and evidenced(item)
        )

    query = draft.queries[0]
    target = query.target
    target_quantity = next(
        (
            item
            for item in draft.quantities
            if item.quantity_id == target.target_quantity_id
        ),
        None,
    )
    query_exact = (
        query.shape.value == "scalar"
        and target.role.value == "velocity"
        and target.component.value == "magnitude"
        and target.subject_id == body_id
        and target.point_id is None
        and target.frame_id is None
        and target.interval_id == interval_id
        and target.event_id == interval.end_event_id
        and target.direction is None
        and target_quantity is not None
        and target_quantity.subject_id == body_id
        and scalar_scoped(target_quantity)
        and target_quantity.event_id == interval.end_event_id
        and target_quantity.role is target.role
        and target_quantity.component is target.component
        and target_quantity.direction is None
        and target_quantity.raw_value is None
        and target_quantity.raw_unit is None
        and target_quantity.provenance.value == "unknown"
        and target_quantity.symbol_id is not None
        and not target_quantity.evidence_refs
        and query.output_dimension == target_quantity.dimension
        and not query.evidence_refs
    )
    if not query_exact:
        return None

    symbols_by_quantity: Counter[str | None] = Counter(
        item.quantity_id for item in draft.symbols
    )
    if len(draft.symbols) != len(draft.quantities) or any(
        item.symbol_id is None or symbols_by_quantity[item.quantity_id] != 1
        for item in draft.quantities
    ):
        return None

    known = tuple(
        item
        for item in draft.quantities
        if item.quantity_id != target_quantity.quantity_id
    )

    def one_plain(role: str) -> Any | None:
        matches = tuple(item for item in known if item.role.value == role)
        if len(matches) != 1:
            return None
        item = matches[0]
        if (
            item.subject_id == body_id
            and scalar_scoped(item)
            and item.event_id is None
            and item.component.value == "unspecified"
            and item.direction is None
            and valued_source(item)
        ):
            return item
        return None

    mass = one_plain("mass")
    radius = one_plain("radius")
    inertia = one_plain("moment_of_inertia")
    if mass is None or radius is None or inertia is None:
        return None

    heights = tuple(item for item in known if item.role.value == "height")
    starts = tuple(
        item
        for item in known
        if item.role.value == "velocity"
        and item.event_id == interval.start_event_id
    )
    if len(heights) != 1 or len(starts) != 1:
        return None
    height = heights[0]
    start_speed = starts[0]
    height_direction = getattr(
        getattr(height.direction, "direction", None), "value", None
    )
    height_exact = (
        height.subject_id == body_id
        and scalar_scoped(height)
        and height.component.value == "unspecified"
        # The height may carry the sub-shape's own sense — a descended
        # height downward, a reached height upward — and nothing else.
        and height_direction in ({None, "downward"} if descent else {None, "upward"})
        and valued_source(height)
        and (
            height.event_id is None
            if descent
            else height.event_id == interval.end_event_id
        )
    )
    if descent:
        start_exact = (
            start_speed.subject_id == body_id
            and scalar_scoped(start_speed)
            and start_speed.component.value == "magnitude"
            and start_speed.direction is None
            and start_speed.raw_value is None
            and start_speed.raw_unit is None
            and start_speed.provenance.value == "unknown"
            and start_speed.symbol_id is not None
        )
    else:
        start_direction = getattr(
            getattr(start_speed.direction, "direction", None), "value", None
        )
        start_exact = (
            start_speed.subject_id == body_id
            and scalar_scoped(start_speed)
            and start_speed.component.value in {"unspecified", "magnitude"}
            # A start speed stated along the motion is exactly the scalar
            # the energy endpoint reads; any other stated direction refuses.
            and start_direction in {None, "along_motion"}
            and valued_source(start_speed)
        )
    if not height_exact or not start_exact:
        return None

    # The rest release projects exactly one typed at_rest state on the start
    # boundary, carrying the reserved rest quantity; the climb sub-shape
    # projects none.
    if descent:
        if len(draft.state_conditions) != 1:
            return None
        rest_state = draft.state_conditions[0]
        if (
            rest_state.kind.value != "initial"
            or rest_state.state.value != "at_rest"
            or rest_state.subject_id != body_id
            or rest_state.interval_id != interval_id
            or rest_state.event_id != interval.start_event_id
            or rest_state.expression is not None
            or tuple(rest_state.quantity_ids)
            != (start_speed.quantity_id,)
            or not evidenced(rest_state)
        ):
            return None
    elif draft.state_conditions:
        return None

    accounted = {
        item.quantity_id
        for item in (mass, radius, inertia, height, start_speed)
    } | {target_quantity.quantity_id}
    if len(accounted) != len(draft.quantities):
        return None

    dispositions: dict[str, PrerequisiteDisposition] = {
        "rolling_tangency": PrerequisiteDisposition.explicit_source,
        "endpoint_shape": PrerequisiteDisposition.explicit_source,
        "inertia_triplet": PrerequisiteDisposition.explicit_source,
        "endpoint_height": PrerequisiteDisposition.explicit_source,
        "start_speed": (
            PrerequisiteDisposition.server_derivable
            if descent
            else PrerequisiteDisposition.explicit_source
        ),
        "pure_rolling_authority": PrerequisiteDisposition.explicit_source,
        "gravity_authority": PrerequisiteDisposition.explicit_source,
        "gravity_quantity": PrerequisiteDisposition.server_derivable,
        "capability": PrerequisiteDisposition.explicit_source,
    }
    return dispositions


def _rolling_incline_energy_speed_prerequisite(name: str) -> "_Resolver":
    def resolve(facts: "_DraftFacts") -> PrerequisiteDisposition:
        if facts.rolling_incline_energy_speed_profile is None:
            return PrerequisiteDisposition.missing
        return facts.rolling_incline_energy_speed_profile[name]

    return resolve


def _rigid_fixed_axis_prerequisite(name: str) -> "_Resolver":
    def resolve(facts: "_DraftFacts") -> PrerequisiteDisposition:
        if facts.rigid_fixed_axis_profile is None:
            return PrerequisiteDisposition.missing
        return facts.rigid_fixed_axis_profile[name]

    return resolve


class _DraftFacts:
    """One pass of typed readings, shared by every profile signature."""

    __slots__ = (
        "approved",
        "axis_families",
        "bounded_intervals",
        "collision_restitution_profile",
        "explicit_resultant_force_profile",
        "geometry",
        "has_blocking_ambiguity",
        "has_query_objective",
        "interactions",
        "observer_count",
        "polar_kinematics_state_profile",
        "primitives",
        "query_component",
        "query_role",
        "roles",
        "rest_boundary_count",
        "rigid_fixed_axis_profile",
        "rigid_two_point_speed_profile",
        "horizontal_support_orientation",
        "rolling_incline_energy_speed_profile",
        "rotating_relative_profile",
        "semantic_directions",
        "vertical_circle_top_speed_profile",
    )

    def __init__(self, draft: Any, approved_assumption_ids: Iterable[str]) -> None:
        self.has_query_objective = any(
            getattr(item, "objective", None) is not None
            for item in draft.queries
        )
        self.roles = _roles(draft)
        self.approved = _approved_kinds(draft, approved_assumption_ids)
        self.interactions = _interaction_kinds(draft)
        self.geometry = _geometry_kinds(draft)
        self.primitives = _primitives(draft)
        self.bounded_intervals = _bounded_intervals(draft)
        self.query_role = _query_role(draft)
        self.query_component = _query_component(draft)
        self.axis_families = _directed_axis_families(draft)
        self.semantic_directions = _semantic_directions(draft)
        self.rest_boundary_count = _rest_boundary_count(draft)
        self.observer_count = len(_observer_entities(draft))
        self.has_blocking_ambiguity = _blocking_ambiguity(draft)
        self.rotating_relative_profile = _rotating_relative_profile_evidence(draft)
        self.polar_kinematics_state_profile = (
            _polar_kinematics_state_profile_evidence(draft)
        )
        self.rigid_fixed_axis_profile = (
            _rigid_fixed_axis_point_speed_evidence(draft)
        )
        self.rigid_two_point_speed_profile = (
            _rigid_two_point_speed_transfer_evidence(draft)
        )
        self.collision_restitution_profile = (
            _collision_restitution_evidence(draft)
        )
        self.explicit_resultant_force_profile = (
            _explicit_resultant_force_evidence(draft)
        )
        self.vertical_circle_top_speed_profile = (
            _vertical_circle_top_speed_evidence(draft)
        )
        self.rolling_incline_energy_speed_profile = (
            _rolling_incline_energy_speed_evidence(draft)
        )
        self.horizontal_support_orientation = (
            _horizontal_support_orientation(draft)
        )


def _exact_source_zero(raw_value: Any) -> bool:
    """True only for a source number that is exactly zero.

    Zero is the one angle whose value does not depend on the unit it was
    stated in, so the reading needs no unit policy.  A value that is absent,
    non-numeric, non-finite, or merely small is not zero.
    """

    if type(raw_value) is not str:
        return False
    try:
        value = float(raw_value)
    except ValueError:
        return False
    return value == 0.0


def _horizontal_support_orientation(draft: Any) -> bool:
    """True only when the source itself states that its support is horizontal.

    ``EntityPrimitive.surface`` is a *generic* support.  The same primitive
    carries a banked road, a vertical circular track, and a level floor, so
    the primitive alone can never stand for a horizontal one.  The absence of
    an incline primitive and the absence of an angle are equally silent:
    information that was never stated is not evidence of a zero, and an
    entity label that reads "table" or "floor" is not physics authority.

    The one reading admitted here is the source's *own* support-angle
    statement whose value is exactly zero — stated, owned by the support
    entity, evidenced, and numerically zero.  Anything else leaves the
    support's orientation unstated and the profile fails closed.
    """

    surface_ids = {
        item.entity_id
        for item in draft.entities
        if item.primitive.value == "surface"
    }
    if not surface_ids:
        return False
    return any(
        item.role.value == "angle"
        and item.subject_id in surface_ids
        and item.evidence_refs
        and _exact_source_zero(item.raw_value)
        for item in draft.quantities
    )


def _needs_horizontal_support(facts: "_DraftFacts") -> "PrerequisiteDisposition":
    """The typed horizontal-support orientation, stated by the source or not.

    There is no derivable fallback: an unstated orientation stays missing so
    the plan reports an incomplete profile instead of closing a graph whose
    world axes nothing licenses.
    """

    return (
        PrerequisiteDisposition.explicit_source
        if facts.horizontal_support_orientation
        else PrerequisiteDisposition.missing
    )


# --------------------------------------------------------------------------
# Profile signatures
# --------------------------------------------------------------------------

_Resolver = Callable[[_DraftFacts], PrerequisiteDisposition]


def _needs_role(role: str) -> _Resolver:
    def resolve(facts: _DraftFacts) -> PrerequisiteDisposition:
        return (
            PrerequisiteDisposition.explicit_source
            if facts.roles.get(role)
            else PrerequisiteDisposition.missing
        )

    return resolve


def _needs_authority(kind: str) -> _Resolver:
    def resolve(facts: _DraftFacts) -> PrerequisiteDisposition:
        return (
            PrerequisiteDisposition.explicit_source
            if kind in facts.approved
            else PrerequisiteDisposition.missing
        )

    return resolve


def _needs_interaction(kind: str) -> _Resolver:
    def resolve(facts: _DraftFacts) -> PrerequisiteDisposition:
        return (
            PrerequisiteDisposition.explicit_source
            if facts.interactions.get(kind)
            else PrerequisiteDisposition.missing
        )

    return resolve


def _needs_geometry(kind: str) -> _Resolver:
    def resolve(facts: _DraftFacts) -> PrerequisiteDisposition:
        return (
            PrerequisiteDisposition.explicit_source
            if facts.geometry.get(kind)
            else PrerequisiteDisposition.missing
        )

    return resolve


def _derivable_from_authority(kind: str) -> _Resolver:
    """A record a closed server policy builds once an authority licenses it.

    The authority must already be approved from source-grounded structure; the
    policy only decides the record's *shape*, never a number.
    """

    def resolve(facts: _DraftFacts) -> PrerequisiteDisposition:
        return (
            PrerequisiteDisposition.server_derivable
            if kind in facts.approved
            else PrerequisiteDisposition.missing
        )

    return resolve


def _generated_unknown(facts: _DraftFacts) -> PrerequisiteDisposition:
    """A symbol that must exist.  Its value stays unknown."""

    return PrerequisiteDisposition.generated_unknown


def _bounded_interval(facts: _DraftFacts) -> PrerequisiteDisposition:
    return (
        PrerequisiteDisposition.explicit_source
        if facts.bounded_intervals
        else PrerequisiteDisposition.missing
    )


def _resultant_force_authority(facts: _DraftFacts) -> PrerequisiteDisposition:
    """A lone force on a *constrained* body needs a typed resultant authority.

    The engine's free-body completeness contract accepts one narrow shape
    without it: a free particle whose typed model carries a single applied
    force and no constraint-bearing interaction at all is already closed —
    the stated force is the model's entire force system.  That exact shape
    is what `_explicit_resultant_force_evidence` reads.  Anything with a
    contact, rope, joint, spring, gear, or second force still requires the
    authority no Draft can currently state, so it stays `missing` here.
    """

    return (
        PrerequisiteDisposition.explicit_source
        if facts.explicit_resultant_force_profile is not None
        else PrerequisiteDisposition.missing
    )


def _explicit_resultant_force_evidence(
    draft: Any,
) -> Mapping[str, PrerequisiteDisposition] | None:
    """Classify one exact free-particle single-applied-force topology.

    One particle, one source-valued mass, one source-valued force whose
    semantic direction names the horizontal axis, and one value-free signed
    x-component acceleration query on the same interval.  The typed model
    carries no other entity, interaction, relation, or force of any kind, so
    by the engine's free-body completeness contract the stated force is the
    model's entire force system and Newton's second law closes on it.  The
    transaction materialises only the world frame, the axis bindings, and
    the applied-force interaction record the source's force statement
    already is; the existing ``particle_newton_second`` generic law does all
    solving.  No value, equation, assumption, solver choice, answer
    metadata, text, or corpus identity is read here.
    """

    if (
        len(draft.entities) != 1
        or len(draft.motion_intervals) != 1
        or len(draft.queries) != 1
        or len(draft.events) != 2
        or draft.reference_frames
        or draft.points
        or draft.interactions
        or draft.constraints
        or draft.state_conditions
        or draft.principle_hints
        or draft.ambiguities
        or draft.unsupported_features
        or draft.geometry
        or draft.figure_dependency.level.value != "none"
        or draft.figure_dependency.missing_information
        or draft.figure_dependency.evidence_refs
    ):
        return None

    particle = draft.entities[0]
    if particle.primitive.value != "particle":
        return None
    particle_id = particle.entity_id

    interval = draft.motion_intervals[0]
    interval_id = interval.interval_id
    if (
        tuple(interval.subject_ids) != (particle_id,)
        or interval.frame_id is not None
        or interval.start_event_id is None
        or interval.end_event_id is None
        or interval.start_event_id == interval.end_event_id
    ):
        return None

    events = {item.event_id: item for item in draft.events}
    start = events.get(interval.start_event_id)
    finish = events.get(interval.end_event_id)
    if (
        len(events) != 2
        or start is None
        or finish is None
        or start.kind.value != "start"
        or finish.kind.value != "finish"
        or any(
            tuple(item.subject_ids) != (particle_id,)
            or item.time_quantity_id is not None
            or tuple(item.interval_ids) != (interval_id,)
            or item.occurs_in_interval_ids
            for item in draft.events
        )
    ):
        return None

    evidence_ids = {item.evidence_id for item in draft.source_evidence}

    def evidenced(item: Any) -> bool:
        refs = set(item.evidence_refs)
        return bool(refs) and refs.issubset(evidence_ids)

    if any(
        item.subject_id != particle_id
        or item.interval_id not in {None, interval_id}
        or item.proposed_role is not None
        or item.proposed_value is not None
        or item.proposed_unit is not None
        or not evidenced(item)
        for item in draft.assumptions
    ):
        return None

    def valued_source(item: Any) -> bool:
        return (
            item.raw_value is not None
            and item.raw_unit is not None
            and item.provenance.value == "explicit_source"
            and item.symbol_id is not None
            and evidenced(item)
        )

    query = draft.queries[0]
    target = query.target
    target_quantity = next(
        (
            item
            for item in draft.quantities
            if item.quantity_id == target.target_quantity_id
        ),
        None,
    )
    query_exact = (
        query.shape.value == "scalar"
        and target.role.value == "acceleration"
        and target.component.value == "x"
        and target.subject_id == particle_id
        and target.point_id is None
        and target.frame_id is None
        and target.interval_id == interval_id
        and target.event_id is None
        and target.direction is None
        and target_quantity is not None
        and target_quantity.subject_id == particle_id
        and target_quantity.point_id is None
        and target_quantity.frame_id is None
        and target_quantity.interval_id == interval_id
        and target_quantity.event_id is None
        and target_quantity.role is target.role
        and target_quantity.component is target.component
        and target_quantity.direction is None
        and target_quantity.shape.value == "scalar"
        and target_quantity.raw_value is None
        and target_quantity.raw_unit is None
        and target_quantity.provenance.value == "unknown"
        and target_quantity.symbol_id is not None
        and not target_quantity.evidence_refs
        and query.output_dimension == target_quantity.dimension
        and not query.evidence_refs
    )
    if not query_exact:
        return None

    symbols_by_quantity: Counter[str | None] = Counter(
        item.quantity_id for item in draft.symbols
    )
    if len(draft.symbols) != len(draft.quantities) or any(
        item.symbol_id is None or symbols_by_quantity[item.quantity_id] != 1
        for item in draft.quantities
    ):
        return None

    known = tuple(
        item
        for item in draft.quantities
        if item.quantity_id != target_quantity.quantity_id
    )

    dispositions: dict[str, PrerequisiteDisposition] = {}

    masses = tuple(item for item in known if item.role.value == "mass")
    mass_exact = (
        len(masses) == 1
        and masses[0].subject_id == particle_id
        and masses[0].point_id is None
        and masses[0].frame_id is None
        and masses[0].interval_id in {None, interval_id}
        and masses[0].event_id is None
        and masses[0].shape.value == "scalar"
        and masses[0].component.value == "unspecified"
        and masses[0].direction is None
        and valued_source(masses[0])
    )
    dispositions["mass"] = (
        PrerequisiteDisposition.explicit_source
        if mass_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(masses) > 1
            else PrerequisiteDisposition.missing
        )
    )

    forces = tuple(item for item in known if item.role.value == "force")
    force_exact = None
    if len(forces) == 1:
        item = forces[0]
        direction = getattr(
            getattr(item.direction, "direction", None), "value", None
        )
        force_exact = (
            item.subject_id == particle_id
            and item.point_id is None
            and item.frame_id is None
            and item.interval_id == interval_id
            and item.event_id is None
            and item.shape.value == "scalar"
            and item.component.value == "unspecified"
            and direction in {"right", "left"}
            and getattr(item.direction, "kind", None) is not None
            and valued_source(item)
        )
    dispositions["horizontal_applied_force"] = (
        PrerequisiteDisposition.explicit_source
        if force_exact
        else (
            PrerequisiteDisposition.ambiguous
            if len(forces) > 1
            else PrerequisiteDisposition.missing
        )
    )

    accounted = {item.quantity_id for item in (*masses, *forces)} | {
        target_quantity.quantity_id
    }
    if len(accounted) != len(draft.quantities):
        return None

    dispositions.update(
        world_frame=PrerequisiteDisposition.server_derivable,
        applied_force_interaction=PrerequisiteDisposition.server_derivable,
        axis_bindings=PrerequisiteDisposition.server_derivable,
        query_binding=PrerequisiteDisposition.server_derivable,
        capability=PrerequisiteDisposition.explicit_source,
    )
    return dispositions


def _explicit_resultant_force_prerequisite(name: str) -> "_Resolver":
    def resolve(facts: "_DraftFacts") -> PrerequisiteDisposition:
        if facts.explicit_resultant_force_profile is None:
            return PrerequisiteDisposition.missing
        return facts.explicit_resultant_force_profile[name]

    return resolve


def _catalogue_has_no_capability(facts: _DraftFacts) -> PrerequisiteDisposition:
    return PrerequisiteDisposition.unsupported


def _observer_frame_entity(facts: _DraftFacts) -> PrerequisiteDisposition:
    """A `moves_relative_to` whose counterpart the source calls a frame.

    The corpus states the observer as an entity of primitive `reference_frame`
    and ties it to the moving body with a `topology_connects` geometry relation.
    Both halves are the source's own; deriving the typed *frame record* from them
    is the closed part.  Two observers, or none, is not a derivation.
    """

    if facts.observer_count == 1:
        return PrerequisiteDisposition.server_derivable
    if facts.observer_count > 1:
        return PrerequisiteDisposition.ambiguous
    return PrerequisiteDisposition.missing


def _slot_pin_frame_derivable(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """The source's exact pin-on-slot topology names a radial frame shape.

    This grants no equation and no answer authority.  It only writes the
    radial/transverse frame record that lets the compiler reach its existing
    precise out-of-scope terminal.  The transaction performs the exact
    one-pin/one-slot/one-relation scope checks before creating anything.
    """

    return PrerequisiteDisposition.server_derivable


def _relative_acceleration_capability(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """Relative-acceleration readouts are declared out of the course scope.

    The compiler carries the deferral code itself.  Building the frame does not
    produce an answer — it makes the engine's refusal precise instead of leaving
    the case as an undifferentiated underdetermined graph.
    """

    return PrerequisiteDisposition.unsupported


def _event_scoped_solve_plan(facts: _DraftFacts) -> PrerequisiteDisposition:
    """Whether the solver will accept a plan whose unknowns are event-scoped.

    A velocity at an interval's start and a velocity at its end are two states,
    not two instants in a timed simulation, but the solver cannot tell those
    apart from the plan alone: it refuses any plan carrying event IDs unless the
    graph matches one of its exact static-boundary waivers.  The impulse waiver
    recognises the three-law shape — `linear_impulse`, `linear_impulse_momentum`
    and `elapsed_time_positive` together — which needs a force, a duration, and
    the authorities that license both.

    A source that states the impulse outright and asks for the velocity after it
    is a two-known, one-unknown algebraic problem that never reaches that shape.
    Manufacturing a force and a duration to satisfy the waiver would be
    inventing structure the source does not state, so this reports the honest
    verdict instead: the engine declares no capability for this plan.
    """

    has_shape = (
        bool(facts.roles.get("force"))
        and bool(facts.roles.get("duration"))
        and "constant_force" in facts.approved
        and "strictly_positive_duration" in facts.approved
    )
    return (
        PrerequisiteDisposition.explicit_source
        if has_shape
        else PrerequisiteDisposition.unsupported
    )


def _rotating_relative_prerequisite(name: str) -> _Resolver:
    def resolve(facts: _DraftFacts) -> PrerequisiteDisposition:
        if facts.rotating_relative_profile is None:
            return PrerequisiteDisposition.missing
        return facts.rotating_relative_profile[name]

    return resolve


def _polar_kinematics_state_prerequisite(name: str) -> _Resolver:
    def resolve(facts: _DraftFacts) -> PrerequisiteDisposition:
        if facts.polar_kinematics_state_profile is None:
            return PrerequisiteDisposition.missing
        return facts.polar_kinematics_state_profile[name]

    return resolve


def _rotating_relative_readout_capability(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """The compiler intentionally owns this rotating-frame deferral."""

    return PrerequisiteDisposition.unsupported


def _signed_axis_frame(facts: _DraftFacts) -> PrerequisiteDisposition:
    """The frame and axis a source's own stated directions imply.

    Every emitter that pairs quantities by component needs them expressed on one
    named axis of one frame.  A source that states `left` and `right` has
    already named that axis; the server only has to write it down.  Two
    different axis families in one context is a real ambiguity — the source has
    not said which plane the answer lives in — and no stated direction at all
    means the axis is simply not there to derive.
    """

    if not facts.axis_families:
        return PrerequisiteDisposition.missing
    if len(facts.axis_families) > 1:
        return PrerequisiteDisposition.ambiguous
    axis = next(iter(facts.axis_families))
    if facts.query_component in {"x", "y", "z"} and facts.query_component != axis:
        # The query asks for a component on an axis the source never spoke about.
        return PrerequisiteDisposition.ambiguous
    return PrerequisiteDisposition.server_derivable


def _intrinsic_motion_axis(facts: _DraftFacts) -> PrerequisiteDisposition:
    """The signed axis explicitly named by along/opposite-motion directions.

    ``along_motion`` defines the positive direction and ``opposite_motion`` the
    negative direction of one intrinsic 1-D axis.  The policy writes that axis
    down only when both signs are present and no unrelated semantic direction
    competes with them.  It chooses no physical value and reads no text.
    """

    required = {"along_motion", "opposite_motion"}
    if not required.issubset(facts.semantic_directions):
        return PrerequisiteDisposition.missing
    if facts.semantic_directions - required:
        return PrerequisiteDisposition.ambiguous
    return PrerequisiteDisposition.server_derivable


def _one_evidenced_rest_boundary(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    if facts.rest_boundary_count == 1:
        return PrerequisiteDisposition.explicit_source
    if facts.rest_boundary_count > 1:
        return PrerequisiteDisposition.ambiguous
    return PrerequisiteDisposition.missing


def _static_stop_time_capability(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """The engine carries an exact graph-only waiver for this algebraic shape."""

    return PrerequisiteDisposition.explicit_source


def _scalar_speed_frame(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """A magnitude query plus one along-motion start value defines speed.

    The source has already said that the known scalar is along the motion and
    that the requested endpoint is a magnitude.  Re-expressing those two
    scalars as nonnegative speeds in one named 1-D frame changes no value and
    chooses no sign.  Any competing semantic direction makes the derivation
    ambiguous instead of guessed.
    """

    if facts.query_component != "magnitude":
        return PrerequisiteDisposition.missing
    if facts.semantic_directions == {"along_motion"}:
        return PrerequisiteDisposition.server_derivable
    if facts.semantic_directions:
        return PrerequisiteDisposition.ambiguous
    return PrerequisiteDisposition.missing


def _static_particle_work_energy_capability(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """The solver has an exact graph recognizer for this endpoint balance."""

    return PrerequisiteDisposition.explicit_source


def _direct_constant_force_work_axis(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """One intrinsic path axis already named by the source's force direction.

    ``along_motion`` says the force and the whole-interval path increment share
    the positive sense of one one-dimensional work coordinate.  Writing that
    coordinate down chooses no value and no sign the source did not state.
    Any competing semantic direction is ambiguous and therefore refuses.
    """

    if facts.query_component != "magnitude":
        return PrerequisiteDisposition.missing
    if facts.semantic_directions == {"along_motion"}:
        return PrerequisiteDisposition.server_derivable
    if facts.semantic_directions:
        return PrerequisiteDisposition.ambiguous
    return PrerequisiteDisposition.missing


def _direct_constant_force_work_capability(
    facts: _DraftFacts,
) -> PrerequisiteDisposition:
    """The existing force-work law and linear solver own this scalar balance."""

    return PrerequisiteDisposition.explicit_source


class _ProfileSignature:
    """One profile: when it applies, and what it would need to close."""

    __slots__ = ("applies", "prerequisites", "profile_id")

    def __init__(
        self,
        profile_id: ProfileId,
        applies: Callable[[_DraftFacts], bool],
        prerequisites: Sequence[tuple[str, PrerequisiteKind, _Resolver]],
    ) -> None:
        self.profile_id = profile_id
        self.applies = applies
        self.prerequisites = tuple(prerequisites)


_PROFILES: tuple[_ProfileSignature, ...] = (
    # A bounded one-dimensional braking interval.  The source itself states
    # the positive motion direction, the opposite acceleration direction, and
    # the final rest boundary.  The transaction merely gives those statements
    # one named axis so the existing constant-acceleration velocity law can be
    # used; it creates no numerical value.
    _ProfileSignature(
        ProfileId.signed_constant_acceleration_1d,
        lambda facts: (
            "constant_acceleration" in facts.approved
            and facts.query_role == "duration"
            and facts.roles.get("velocity") == 2
            and facts.roles.get("acceleration") == 1
            and facts.roles.get("duration") == 1
            and len(facts.bounded_intervals) == 1
            and not facts.interactions
            and not facts.geometry
        ),
        (
            ("authority_constant_acceleration", PrerequisiteKind.authority,
             _needs_authority("constant_acceleration")),
            ("interval_bounded", PrerequisiteKind.state_condition,
             _bounded_interval),
            ("state_final_rest", PrerequisiteKind.state_condition,
             _one_evidenced_rest_boundary),
            ("quantity_velocity", PrerequisiteKind.interaction_quantity,
             _needs_role("velocity")),
            ("quantity_acceleration", PrerequisiteKind.interaction_quantity,
             _needs_role("acceleration")),
            ("quantity_duration", PrerequisiteKind.interaction_quantity,
             _needs_role("duration")),
            ("frame_intrinsic_motion_axis", PrerequisiteKind.reference_frame,
             _intrinsic_motion_axis),
            ("capability_static_stop_time", PrerequisiteKind.capability,
             _static_stop_time_capability),
        ),
    ),
    # Free flight under gravity alone.  Recognised by an approved uniform-gravity
    # authority on an interval with no force-bearing contact, rope, spring, or
    # collision interaction.  The frame and the gravity interaction are both
    # server-derivable, and they are exactly the pair that must be created
    # together: neither alone unlocks a law, which is why a frame-only
    # counterfactual measures zero.
    _ProfileSignature(
        ProfileId.free_flight_gravity,
        lambda facts: (
            "constant_gravity" in facts.approved
            and not (
                facts.interactions.get("contact")
                or facts.interactions.get("rope_tension")
                or facts.interactions.get("spring")
                or facts.interactions.get("collision")
            )
            # A body supported by, or rolling on, something is not in free
            # flight, however uniform the gravity acting on it is.
            and not (
                facts.geometry.get("lies_on") or facts.geometry.get("tangent")
            )
        ),
        (
            ("frame_cartesian_2d", PrerequisiteKind.reference_frame,
             _derivable_from_authority("constant_gravity")),
            ("axis_vertical", PrerequisiteKind.axis,
             _derivable_from_authority("constant_gravity")),
            ("interaction_gravity", PrerequisiteKind.interaction,
             _derivable_from_authority("constant_gravity")),
            # The gravitational field strength is the closed server default the
            # approved authority already carries; the profile does not invent it.
            ("quantity_gravity", PrerequisiteKind.interaction_quantity,
             _derivable_from_authority("constant_gravity")),
            ("symbol_vertical_acceleration", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
            ("authority_constant_acceleration", PrerequisiteKind.authority,
             _needs_authority("constant_acceleration")),
            ("interval_bounded", PrerequisiteKind.state_condition, _bounded_interval),
        ),
    ),
    # One free particle whose typed model carries a single applied force and
    # nothing else.  The engine's free-body completeness contract accepts
    # exactly this shape as already closed, so the profile closes it; every
    # constrained shape still reports the missing resultant authority.
    _ProfileSignature(
        ProfileId.explicit_resultant_force,
        lambda facts: (
            bool(facts.roles.get("force"))
            and bool(facts.roles.get("mass"))
            and not facts.interactions
        ),
        (
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _explicit_resultant_force_prerequisite("mass")),
            ("quantity_horizontal_applied_force", PrerequisiteKind.interaction_quantity,
             _explicit_resultant_force_prerequisite("horizontal_applied_force")),
            ("authority_force_is_resultant", PrerequisiteKind.authority,
             _resultant_force_authority),
            ("frame_world_axes", PrerequisiteKind.reference_frame,
             _explicit_resultant_force_prerequisite("world_frame")),
            ("interaction_applied_force", PrerequisiteKind.interaction,
             _explicit_resultant_force_prerequisite("applied_force_interaction")),
            ("axis_bindings", PrerequisiteKind.capability,
             _explicit_resultant_force_prerequisite("axis_bindings")),
            ("query_binding", PrerequisiteKind.capability,
             _explicit_resultant_force_prerequisite("query_binding")),
            ("capability_particle_newton_second", PrerequisiteKind.capability,
             _explicit_resultant_force_prerequisite("capability")),
        ),
    ),
    # Exactly two closed bodies, one source-declared collision spanning its
    # own collision_start/collision_end-bounded interval, per-body masses
    # and semantically-directed approach velocities, one restitution
    # coefficient, signed x-component separation queries, and the
    # projection's own per-body impulse-isolation authority.  The
    # exact-shape reader owns applicability; the existing
    # system_momentum_conservation and direct_restitution laws do all
    # solving.
    _ProfileSignature(
        ProfileId.collision_restitution,
        lambda facts: facts.collision_restitution_profile is not None,
        (
            ("interaction_collision_topology", PrerequisiteKind.interaction,
             _collision_restitution_prerequisite("collision_topology")),
            ("event_impact_boundaries", PrerequisiteKind.state_condition,
             _collision_restitution_prerequisite("impact_boundary_events")),
            ("authority_isolated_impact", PrerequisiteKind.authority,
             _collision_restitution_prerequisite("isolated_impact_authority")),
            ("quantity_mass_pair", PrerequisiteKind.interaction_quantity,
             _collision_restitution_prerequisite("mass_pair")),
            ("quantity_approach_velocities", PrerequisiteKind.interaction_quantity,
             _collision_restitution_prerequisite("approach_velocities")),
            ("quantity_restitution", PrerequisiteKind.interaction_quantity,
             _collision_restitution_prerequisite("restitution_coefficient")),
            ("frame_world", PrerequisiteKind.reference_frame,
             _collision_restitution_prerequisite("world_frame")),
            ("axis_bindings", PrerequisiteKind.capability,
             _collision_restitution_prerequisite("axis_binding")),
            ("query_binding", PrerequisiteKind.capability,
             _collision_restitution_prerequisite("query_binding")),
            ("symbol_partner_post_velocity", PrerequisiteKind.unknown_symbol,
             _collision_restitution_prerequisite("partner_post_velocity_symbol")),
            ("capability_momentum_restitution", PrerequisiteKind.capability,
             _collision_restitution_prerequisite("capability")),
        ),
    ),
    _ProfileSignature(
        ProfileId.fixed_pulley,
        lambda facts: (
            bool(facts.geometry.get("wraps"))
            and not facts.geometry.get("lies_on")
        ),
        (
            ("geometry_wraps", PrerequisiteKind.geometry, _needs_geometry("wraps")),
            ("geometry_rope", PrerequisiteKind.geometry,
             _needs_geometry("topology_connects")),
            ("interaction_rope_tension", PrerequisiteKind.interaction,
             _derivable_from_authority("massless_rope")),
            ("authority_massless_rope", PrerequisiteKind.authority,
             _needs_authority("massless_rope")),
            ("authority_inextensible_rope", PrerequisiteKind.authority,
             _needs_authority("inextensible_rope")),
            ("authority_fixed_pulley", PrerequisiteKind.authority,
             _needs_authority("massless_pulley")),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("symbol_tension", PrerequisiteKind.unknown_symbol, _generated_unknown),
            ("symbol_acceleration", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
            ("frame_cartesian", PrerequisiteKind.reference_frame,
             _derivable_from_authority("massless_rope")),
            ("point_contact", PrerequisiteKind.point,
             _derivable_from_authority("massless_pulley")),
        ),
    ),
    _ProfileSignature(
        ProfileId.incline_hanging_pulley,
        lambda facts: (
            bool(facts.geometry.get("wraps"))
            and bool(facts.geometry.get("lies_on"))
            and bool(facts.primitives.get("incline"))
        ),
        (
            ("geometry_wraps", PrerequisiteKind.geometry, _needs_geometry("wraps")),
            ("geometry_support", PrerequisiteKind.geometry,
             _needs_geometry("lies_on")),
            ("interaction_rope_tension", PrerequisiteKind.interaction,
             _derivable_from_authority("massless_rope")),
            ("interaction_contact", PrerequisiteKind.interaction,
             _derivable_from_authority("frictionless")),
            ("authority_massless_rope", PrerequisiteKind.authority,
             _needs_authority("massless_rope")),
            ("authority_inextensible_rope", PrerequisiteKind.authority,
             _needs_authority("inextensible_rope")),
            ("quantity_angle", PrerequisiteKind.interaction_quantity,
             _needs_role("angle")),
            ("frame_tangential_normal", PrerequisiteKind.reference_frame,
             _derivable_from_authority("frictionless")),
            ("state_contact_regime", PrerequisiteKind.state_condition,
             _derivable_from_authority("frictionless")),
            ("symbol_tension", PrerequisiteKind.unknown_symbol, _generated_unknown),
            ("symbol_normal_force", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    # A body on a horizontal table tied over a fixed ideal pulley to a hanging
    # body.  The horizontal orientation is the source's own zero-valued
    # support angle and nothing else: the generic `surface` primitive, a
    # missing incline primitive, and a missing angle are all silence, and
    # silence is never a stated zero.  With the orientation stated, the
    # transaction derives only frames, force-bearing interactions, contact and
    # rope states, and value-free unknowns; the existing weight, Newton,
    # contact, and rope laws do all solving.
    _ProfileSignature(
        ProfileId.table_pulley_two_body,
        lambda facts: (
            bool(facts.geometry.get("wraps"))
            and bool(facts.geometry.get("lies_on"))
            and bool(facts.primitives.get("surface"))
            and not facts.primitives.get("incline")
            and facts.horizontal_support_orientation
        ),
        (
            ("orientation_horizontal_support", PrerequisiteKind.geometry,
             _needs_horizontal_support),
            ("geometry_wraps", PrerequisiteKind.geometry, _needs_geometry("wraps")),
            ("geometry_rope", PrerequisiteKind.geometry,
             _needs_geometry("topology_connects")),
            ("geometry_support", PrerequisiteKind.geometry,
             _needs_geometry("lies_on")),
            ("interaction_rope_tension", PrerequisiteKind.interaction,
             _derivable_from_authority("massless_rope")),
            ("interaction_contact", PrerequisiteKind.interaction,
             _derivable_from_authority("frictionless")),
            ("interaction_gravity", PrerequisiteKind.interaction,
             _derivable_from_authority("constant_gravity")),
            ("authority_massless_rope", PrerequisiteKind.authority,
             _needs_authority("massless_rope")),
            ("authority_inextensible_rope", PrerequisiteKind.authority,
             _needs_authority("inextensible_rope")),
            ("authority_fixed_pulley", PrerequisiteKind.authority,
             _needs_authority("massless_pulley")),
            ("authority_frictionless_support", PrerequisiteKind.authority,
             _needs_authority("frictionless")),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("frame_world_cartesian", PrerequisiteKind.reference_frame,
             _derivable_from_authority("frictionless")),
            ("state_contact_regime", PrerequisiteKind.state_condition,
             _derivable_from_authority("frictionless")),
            ("symbol_tension", PrerequisiteKind.unknown_symbol, _generated_unknown),
            ("symbol_normal_force", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
            ("symbol_acceleration", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    _ProfileSignature(
        ProfileId.rolling_energy,
        lambda facts: "pure_rolling" in facts.approved
        or bool(facts.geometry.get("tangent")),
        (
            ("authority_pure_rolling", PrerequisiteKind.authority,
             _needs_authority("pure_rolling")),
            ("geometry_rolling_contact", PrerequisiteKind.geometry,
             _needs_geometry("tangent")),
            ("quantity_radius", PrerequisiteKind.interaction_quantity,
             _needs_role("radius")),
            ("quantity_height", PrerequisiteKind.interaction_quantity,
             _needs_role("height")),
            ("quantity_gravity", PrerequisiteKind.interaction_quantity,
             _needs_role("gravity")),
            ("quantity_moment_of_inertia", PrerequisiteKind.interaction_quantity,
             _needs_role("moment_of_inertia")),
            ("symbol_speed", PrerequisiteKind.unknown_symbol, _generated_unknown),
        ),
    ),
    # One body, one bounded interval, one stated net work, and scalar endpoint
    # speed magnitudes.  The transaction only gives those quantities the exact
    # `speed` identity and one intrinsic 1-D frame required by the existing
    # particle-work-energy law and its graph-only solver waiver.
    _ProfileSignature(
        ProfileId.particle_work_energy_speed,
        lambda facts: (
            facts.query_role == "velocity"
            and facts.query_component == "magnitude"
            and facts.roles.get("mass") == 1
            and facts.roles.get("work") == 1
            and facts.roles.get("velocity") == 2
            and len(facts.bounded_intervals) == 1
            and not facts.interactions
            and not facts.geometry
            and sum(facts.primitives.values()) == 1
            and (
                facts.primitives.get("particle") == 1
                or facts.primitives.get("rigid_body") == 1
            )
        ),
        (
            ("interval_bounded", PrerequisiteKind.state_condition,
             _bounded_interval),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_work", PrerequisiteKind.interaction_quantity,
             _needs_role("work")),
            ("quantity_endpoint_speeds", PrerequisiteKind.interaction_quantity,
             _needs_role("velocity")),
            ("frame_scalar_speed", PrerequisiteKind.reference_frame,
             _scalar_speed_frame),
            ("capability_static_particle_work_energy",
             PrerequisiteKind.capability,
             _static_particle_work_energy_capability),
            ("symbol_final_speed", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    # One body, one bounded energy interval, one source-stated force value
    # scoped over that whole interval, and one whole-interval path length.  The
    # projection's closed policy authorises ``constant_force`` only for this
    # exact typed shape; the transaction then writes the intrinsic motion axis,
    # retypes the path increment as displacement on that axis, and links the
    # three existing quantities through one applied-force interaction.
    _ProfileSignature(
        ProfileId.direct_constant_force_work,
        lambda facts: (
            facts.query_role == "work"
            and facts.query_component == "magnitude"
            and facts.roles.get("force") == 1
            and facts.roles.get("distance") == 1
            and facts.roles.get("work") == 1
            and sum(facts.roles.values()) == 3
            and "constant_force" in facts.approved
            and len(facts.bounded_intervals) == 1
            and not facts.interactions
            and not facts.geometry
            and sum(facts.primitives.values()) == 1
            and (
                facts.primitives.get("particle") == 1
                or facts.primitives.get("rigid_body") == 1
                or facts.primitives.get("body_component") == 1
            )
        ),
        (
            ("interval_bounded", PrerequisiteKind.state_condition,
             _bounded_interval),
            ("quantity_force", PrerequisiteKind.interaction_quantity,
             _needs_role("force")),
            ("quantity_path_length", PrerequisiteKind.interaction_quantity,
             _needs_role("distance")),
            ("authority_constant_force", PrerequisiteKind.authority,
             _needs_authority("constant_force")),
            ("frame_intrinsic_work_axis", PrerequisiteKind.reference_frame,
             _direct_constant_force_work_axis),
            ("interaction_applied_force", PrerequisiteKind.interaction,
             _derivable_from_authority("constant_force")),
            ("capability_direct_force_work", PrerequisiteKind.capability,
             _direct_constant_force_work_capability),
            ("symbol_work", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    # Five source-backed scalar polar state quantities at one occurrence inside
    # an evidence-free artificial start/finish wrapper.  The transaction
    # removes only that wrapper, writes one radial/transverse coordinate and
    # radius topology, and creates value-free component unknowns.  The existing
    # polar laws, compiler, solver, and verifier remain the sole answer authority.
    _ProfileSignature(
        ProfileId.polar_kinematics_state,
        lambda facts: facts.polar_kinematics_state_profile is not None,
        (
            ("quantity_radius", PrerequisiteKind.interaction_quantity,
             _polar_kinematics_state_prerequisite("radius")),
            ("quantity_radial_rate", PrerequisiteKind.interaction_quantity,
             _polar_kinematics_state_prerequisite("radial_rate")),
            ("quantity_radial_acceleration", PrerequisiteKind.interaction_quantity,
             _polar_kinematics_state_prerequisite("radial_acceleration")),
            ("quantity_angular_velocity", PrerequisiteKind.interaction_quantity,
             _polar_kinematics_state_prerequisite("omega")),
            ("quantity_angular_acceleration", PrerequisiteKind.interaction_quantity,
             _polar_kinematics_state_prerequisite("alpha")),
            ("scope_single_instant", PrerequisiteKind.state_condition,
             _polar_kinematics_state_prerequisite("temporal_scope")),
            ("direction_polar_axes", PrerequisiteKind.axis,
             _polar_kinematics_state_prerequisite("direction_binding")),
            ("entity_polar_coordinate", PrerequisiteKind.reference_frame,
             _polar_kinematics_state_prerequisite("coordinate_entity")),
            ("frame_radial_transverse", PrerequisiteKind.reference_frame,
             _polar_kinematics_state_prerequisite("frame")),
            ("geometry_radius", PrerequisiteKind.geometry,
             _polar_kinematics_state_prerequisite("radius_relation")),
            ("query_component_binding", PrerequisiteKind.constraint,
             _polar_kinematics_state_prerequisite("query_binding")),
            ("symbols_polar_components", PrerequisiteKind.unknown_symbol,
             _polar_kinematics_state_prerequisite("derived_components")),
            ("capability_verified_polar_kinematics", PrerequisiteKind.capability,
             _polar_kinematics_state_prerequisite("capability")),
        ),
    ),
    _ProfileSignature(
        ProfileId.work_energy,
        lambda facts: facts.query_role in {"work", "energy"}
        or bool(facts.roles.get("work")),
        (
            ("interval_bounded", PrerequisiteKind.state_condition, _bounded_interval),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_force", PrerequisiteKind.interaction_quantity,
             _needs_role("force")),
            ("quantity_displacement", PrerequisiteKind.interaction_quantity,
             _needs_role("displacement")),
            ("authority_constant_force", PrerequisiteKind.authority,
             _needs_authority("constant_force")),
            ("symbol_work", PrerequisiteKind.unknown_symbol, _generated_unknown),
        ),
    ),
    _ProfileSignature(
        ProfileId.impulse_momentum,
        lambda facts: facts.query_role == "impulse"
        or bool(facts.roles.get("impulse")),
        (
            ("interval_bounded", PrerequisiteKind.state_condition, _bounded_interval),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_velocity", PrerequisiteKind.interaction_quantity,
             _needs_role("velocity")),
            ("quantity_impulse", PrerequisiteKind.interaction_quantity,
             _needs_role("impulse")),
            # `linear_impulse_momentum` pairs its four quantities by component,
            # so a source that states directions semantically does not reach it
            # until those directions become signed components of one named axis.
            # The frame, the axis, and the component binding are one indivisible
            # step: any of them alone leaves the emitter exactly as blocked.
            ("frame_signed_axis", PrerequisiteKind.reference_frame,
             _signed_axis_frame),
            ("axis_signed", PrerequisiteKind.axis, _signed_axis_frame),
            ("component_binding", PrerequisiteKind.constraint, _signed_axis_frame),
            # The endpoint velocities are event-scoped, and the solver accepts
            # such a plan only in its exact static-boundary shape.
            ("capability_event_scoped_solve_plan", PrerequisiteKind.capability,
             _event_scoped_solve_plan),
            ("symbol_final_velocity", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    _ProfileSignature(
        ProfileId.horizontal_contact,
        lambda facts: (
            bool(facts.geometry.get("lies_on"))
            and not facts.geometry.get("wraps")
            and not facts.roles.get("angle")
            and bool(facts.primitives.get("surface"))
        ),
        (
            ("geometry_support", PrerequisiteKind.geometry,
             _needs_geometry("lies_on")),
            ("capability_horizontal_surface_profile", PrerequisiteKind.capability,
             _catalogue_has_no_capability),
            ("interaction_contact", PrerequisiteKind.interaction,
             _derivable_from_authority("constant_gravity")),
            ("interaction_gravity", PrerequisiteKind.interaction,
             _derivable_from_authority("constant_gravity")),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_coefficient_friction", PrerequisiteKind.interaction_quantity,
             _needs_role("coefficient_friction")),
            ("frame_tangential_normal", PrerequisiteKind.reference_frame,
             _derivable_from_authority("constant_gravity")),
            ("point_contact", PrerequisiteKind.point,
             _derivable_from_authority("constant_gravity")),
            ("state_friction_regime", PrerequisiteKind.state_condition,
             _derivable_from_authority("constant_gravity")),
            ("symbol_normal_force", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
            ("symbol_friction_force", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    _ProfileSignature(
        ProfileId.incline_contact,
        lambda facts: (
            bool(facts.geometry.get("lies_on"))
            and not facts.geometry.get("wraps")
            and bool(facts.roles.get("angle"))
            and bool(facts.primitives.get("incline"))
        ),
        (
            ("geometry_support", PrerequisiteKind.geometry,
             _needs_geometry("lies_on")),
            ("geometry_angle", PrerequisiteKind.geometry,
             _derivable_from_authority("constant_gravity")),
            ("interaction_contact", PrerequisiteKind.interaction,
             _derivable_from_authority("constant_gravity")),
            ("interaction_gravity", PrerequisiteKind.interaction,
             _derivable_from_authority("constant_gravity")),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_angle", PrerequisiteKind.interaction_quantity,
             _needs_role("angle")),
            ("quantity_gravity", PrerequisiteKind.interaction_quantity,
             _needs_role("gravity")),
            ("frame_tangential_normal", PrerequisiteKind.reference_frame,
             _derivable_from_authority("constant_gravity")),
            ("point_contact", PrerequisiteKind.point,
             _derivable_from_authority("constant_gravity")),
            ("state_contact_regime", PrerequisiteKind.state_condition,
             _derivable_from_authority("frictionless")),
            ("symbol_normal_force", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
            ("symbol_tangential_acceleration", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    # One free body in a source-declared kinetic slide down one incline with a
    # source-valued angle and friction coefficient.  The projection's own
    # closed policy has already read the down-slope direction from the
    # complete typed model — gravity as the entire driving system — so the
    # profile requires that authority and never re-derives it.  The
    # transaction supplies only frames, the contact record, regime states,
    # and the value-free tangential unknown; the sliding-regime law does all
    # solving.
    _ProfileSignature(
        ProfileId.incline_kinetic_sliding,
        lambda facts: (
            bool(facts.geometry.get("lies_on"))
            and not facts.geometry.get("wraps")
            and bool(facts.roles.get("angle"))
            and bool(facts.roles.get("coefficient_friction"))
            and bool(facts.primitives.get("incline"))
            and "typed_incline_slide_motion" in facts.approved
        ),
        (
            ("geometry_support", PrerequisiteKind.geometry,
             _needs_geometry("lies_on")),
            ("geometry_angle", PrerequisiteKind.geometry,
             _derivable_from_authority("constant_gravity")),
            ("interaction_contact", PrerequisiteKind.interaction,
             _derivable_from_authority("typed_incline_slide_motion")),
            ("quantity_angle", PrerequisiteKind.interaction_quantity,
             _needs_role("angle")),
            ("quantity_coefficient_friction", PrerequisiteKind.interaction_quantity,
             _needs_role("coefficient_friction")),
            ("authority_constant_gravity", PrerequisiteKind.authority,
             _needs_authority("constant_gravity")),
            ("authority_downslope_sliding", PrerequisiteKind.authority,
             _needs_authority("typed_incline_slide_motion")),
            ("frame_tangential_normal", PrerequisiteKind.reference_frame,
             _derivable_from_authority("constant_gravity")),
            ("state_friction_regime", PrerequisiteKind.state_condition,
             _derivable_from_authority("typed_incline_slide_motion")),
            ("symbol_tangential_acceleration", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
        ),
    ),
    # One rigid body about a fixed axis, one source-declared on-body point at a
    # source-declared radius, one scalar speed-magnitude readout of that point.
    # The exact-shape reader owns applicability; the existing fixed_axis_speed
    # law does all solving.
    _ProfileSignature(
        ProfileId.rigid_fixed_axis,
        lambda facts: facts.rigid_fixed_axis_profile is not None,
        (
            ("quantity_angular_velocity", PrerequisiteKind.interaction_quantity,
             _rigid_fixed_axis_prerequisite("angular_velocity")),
            ("quantity_radius", PrerequisiteKind.interaction_quantity,
             _rigid_fixed_axis_prerequisite("radius")),
            ("geometry_point_on_body", PrerequisiteKind.geometry,
             _rigid_fixed_axis_prerequisite("point_topology")),
            ("geometry_fixed_axis", PrerequisiteKind.geometry,
             _rigid_fixed_axis_prerequisite("fixed_axis_topology")),
            ("point_material_binding", PrerequisiteKind.point,
             _rigid_fixed_axis_prerequisite("material_point")),
            ("query_speed_normalization", PrerequisiteKind.capability,
             _rigid_fixed_axis_prerequisite("speed_normalization")),
            ("query_binding", PrerequisiteKind.capability,
             _rigid_fixed_axis_prerequisite("query_binding")),
            ("symbol_point_speed", PrerequisiteKind.unknown_symbol,
             _rigid_fixed_axis_prerequisite("point_speed_symbol")),
            ("capability_fixed_axis_speed", PrerequisiteKind.capability,
             _rigid_fixed_axis_prerequisite("capability")),
        ),
    ),
    # One rigid body, two source-declared on-body points each at its own
    # source-valued radius, one source-valued point speed, one scalar
    # speed-magnitude readout of the other point, all at the same source
    # instant.  The exact-shape reader owns applicability; the existing
    # fixed_axis_speed law couples the two points through one generated
    # value-free shared angular-speed unknown.
    _ProfileSignature(
        ProfileId.rigid_two_point_speed,
        lambda facts: facts.rigid_two_point_speed_profile is not None,
        (
            ("geometry_two_points_on_body", PrerequisiteKind.geometry,
             _rigid_two_point_speed_prerequisite("two_point_topology")),
            ("geometry_rotation_centre", PrerequisiteKind.geometry,
             _rigid_two_point_speed_prerequisite("rotation_centre_authority")),
            ("quantity_radius_pair", PrerequisiteKind.interaction_quantity,
             _rigid_two_point_speed_prerequisite("radius_pair")),
            ("quantity_known_point_speed", PrerequisiteKind.interaction_quantity,
             _rigid_two_point_speed_prerequisite("known_point_speed")),
            ("point_material_bindings", PrerequisiteKind.point,
             _rigid_two_point_speed_prerequisite("material_points")),
            ("query_speed_normalization", PrerequisiteKind.capability,
             _rigid_two_point_speed_prerequisite("speed_normalization")),
            ("query_binding", PrerequisiteKind.capability,
             _rigid_two_point_speed_prerequisite("query_binding")),
            ("symbol_shared_angular_speed", PrerequisiteKind.unknown_symbol,
             _rigid_two_point_speed_prerequisite("shared_angular_speed_symbol")),
            ("symbol_point_speed", PrerequisiteKind.unknown_symbol,
             _rigid_two_point_speed_prerequisite("point_speed_symbol")),
            ("capability_fixed_axis_speed", PrerequisiteKind.capability,
             _rigid_two_point_speed_prerequisite("capability")),
        ),
    ),
    # One particle on one circular track, one source-valued radius, an
    # approved server-valued gravity authority, and one value-free scalar
    # minimum-speed query at the source-declared highest point, with the
    # limiting contact typed in full: inward contact side, a maintained
    # contact state over the interval, and an active boundary state at the
    # top instant — nothing else.  The exact-shape reader owns
    # applicability; the existing vertical_circle_top_minimum_speed law
    # does all solving.
    _ProfileSignature(
        ProfileId.vertical_circle_top_speed,
        lambda facts: facts.vertical_circle_top_speed_profile is not None,
        (
            ("interaction_circular_contact", PrerequisiteKind.interaction,
             _vertical_circle_top_speed_prerequisite("circular_contact")),
            ("interaction_contact_orientation", PrerequisiteKind.interaction,
             _vertical_circle_top_speed_prerequisite("contact_orientation")),
            ("query_minimum_objective", PrerequisiteKind.capability,
             _vertical_circle_top_speed_prerequisite("minimum_objective")),
            ("state_maintained_contact", PrerequisiteKind.state_condition,
             _vertical_circle_top_speed_prerequisite("maintained_contact_state")),
            ("state_limiting_boundary", PrerequisiteKind.state_condition,
             _vertical_circle_top_speed_prerequisite("limiting_boundary_state")),
            ("event_highest_point_boundary", PrerequisiteKind.state_condition,
             _vertical_circle_top_speed_prerequisite("highest_point_boundary")),
            ("quantity_radius", PrerequisiteKind.interaction_quantity,
             _vertical_circle_top_speed_prerequisite("radius")),
            ("authority_constant_gravity", PrerequisiteKind.authority,
             _vertical_circle_top_speed_prerequisite("gravity_authority")),
            ("quantity_gravity", PrerequisiteKind.interaction_quantity,
             _vertical_circle_top_speed_prerequisite("gravity_quantity")),
            ("capability_top_minimum_speed", PrerequisiteKind.capability,
             _vertical_circle_top_speed_prerequisite("capability")),
        ),
    ),
    # One rigid body rolling on one incline it is tangent to, approved
    # pure-rolling and gravity authorities, source-valued mass/radius/inertia,
    # and one of the two exact endpoint sub-shapes (rest-release descent with
    # an interval height, or valued-start climb to an event-bound height).
    # The exact-shape reader owns applicability; the existing
    # rolling_general_principal_energy law does all solving.
    _ProfileSignature(
        ProfileId.rolling_incline_energy_speed,
        lambda facts: facts.rolling_incline_energy_speed_profile is not None,
        (
            ("geometry_rolling_tangency", PrerequisiteKind.geometry,
             _rolling_incline_energy_speed_prerequisite("rolling_tangency")),
            ("event_endpoint_shape", PrerequisiteKind.state_condition,
             _rolling_incline_energy_speed_prerequisite("endpoint_shape")),
            ("quantity_inertia_triplet", PrerequisiteKind.interaction_quantity,
             _rolling_incline_energy_speed_prerequisite("inertia_triplet")),
            ("quantity_endpoint_height", PrerequisiteKind.interaction_quantity,
             _rolling_incline_energy_speed_prerequisite("endpoint_height")),
            ("quantity_start_speed", PrerequisiteKind.interaction_quantity,
             _rolling_incline_energy_speed_prerequisite("start_speed")),
            ("authority_pure_rolling", PrerequisiteKind.authority,
             _rolling_incline_energy_speed_prerequisite("pure_rolling_authority")),
            ("authority_constant_gravity", PrerequisiteKind.authority,
             _rolling_incline_energy_speed_prerequisite("gravity_authority")),
            ("quantity_gravity", PrerequisiteKind.interaction_quantity,
             _rolling_incline_energy_speed_prerequisite("gravity_quantity")),
            ("capability_rolling_energy", PrerequisiteKind.capability,
             _rolling_incline_energy_speed_prerequisite("capability")),
        ),
    ),
    # The one profile the engine answers by *declining*: a free undamped linear
    # spring period/frequency readout is outside the declared course scope.
    # A pin constrained to one source-declared slot, with a radial or
    # transverse component query.  The frame is derivable from the exact typed
    # topology, but the readout remains outside the declared course scope.
    _ProfileSignature(
        ProfileId.slot_pin_relative_frame,
        lambda facts: (
            bool(facts.geometry.get("lies_on"))
            and bool(facts.primitives.get("slot"))
            and bool(
                facts.primitives.get("joint")
                or facts.primitives.get("particle")
                or facts.primitives.get("body_component")
            )
            and facts.query_role in {"velocity", "acceleration"}
            and facts.query_component in {"radial", "transverse"}
        ),
        (
            ("geometry_pin_slot", PrerequisiteKind.geometry,
             _needs_geometry("lies_on")),
            ("frame_radial_transverse", PrerequisiteKind.reference_frame,
             _slot_pin_frame_derivable),
            ("component_radial_transverse", PrerequisiteKind.axis,
             lambda facts: PrerequisiteDisposition.explicit_source),
            ("capability_slot_pin_relative_motion", PrerequisiteKind.capability,
             _catalogue_has_no_capability),
        ),
    ),
    # One point-like subject moving radially/transversely relative to one
    # rotating carrier already names a rotating coordinate frame.  The
    # transaction writes down only the frame pair and rotation point so the
    # compiler can issue its existing precise course-scope deferral.
    _ProfileSignature(
        ProfileId.rotating_relative_frame,
        lambda facts: facts.rotating_relative_profile is not None,
        (
            ("geometry_relative_rotation", PrerequisiteKind.geometry,
             _rotating_relative_prerequisite("relation")),
            ("entity_rotating_observer", PrerequisiteKind.reference_frame,
             _rotating_relative_prerequisite("observer")),
            ("point_rotation_origin", PrerequisiteKind.point,
             _rotating_relative_prerequisite("point")),
            ("frame_world_and_rotating", PrerequisiteKind.reference_frame,
             _rotating_relative_prerequisite("frame")),
            ("component_binding", PrerequisiteKind.constraint,
             _rotating_relative_prerequisite("binding")),
            ("capability_rotating_relative_acceleration",
             PrerequisiteKind.capability,
             _rotating_relative_readout_capability),
        ),
    ),
    # A body whose motion the source states relative to a declared observer.
    # The typed frame record is derivable; the readout itself is deferred, and
    # building the frame is what lets the engine say so precisely.
    _ProfileSignature(
        ProfileId.relative_translating_frame,
        lambda facts: (
            facts.observer_count >= 1
            and facts.query_role == "acceleration"
            and bool(facts.roles.get("acceleration"))
        ),
        (
            ("entity_observer_frame", PrerequisiteKind.reference_frame,
             _observer_frame_entity),
            ("frame_parent_world", PrerequisiteKind.reference_frame,
             _observer_frame_entity),
            ("axis_signed", PrerequisiteKind.axis, _signed_axis_frame),
            ("quantity_relative_acceleration", PrerequisiteKind.interaction_quantity,
             _needs_role("acceleration")),
            ("component_binding", PrerequisiteKind.constraint, _signed_axis_frame),
            ("symbol_absolute_acceleration", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
            ("capability_relative_acceleration_readout", PrerequisiteKind.capability,
             _relative_acceleration_capability),
        ),
    ),
    _ProfileSignature(
        ProfileId.spring_vibration_deferred,
        lambda facts: (
            "angular_natural_frequency" in facts.approved
            and facts.query_role in {"period", "frequency"}
        ),
        (
            ("authority_angular_natural_frequency", PrerequisiteKind.authority,
             _needs_authority("angular_natural_frequency")),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_stiffness", PrerequisiteKind.interaction_quantity,
             _needs_role("stiffness")),
            ("capability_period_readout", PrerequisiteKind.capability,
             _catalogue_has_no_capability),
        ),
    ),
)

_PROFILES_BY_ID: Mapping[ProfileId, _ProfileSignature] = {
    item.profile_id: item for item in _PROFILES
}

# The profiles that understand an extremal query objective.  Everything else
# refuses an objective-bearing draft outright: an exact-value reader answering
# a minimum question would be answering a question the source never asked.
_OBJECTIVE_AWARE_PROFILES: frozenset[ProfileId] = frozenset(
    {ProfileId.vertical_circle_top_speed}
)


def plan_complete_profile(
    profile_id: ProfileId,
    draft: Any,
    *,
    approved_assumption_ids: Iterable[str] = (),
) -> CompleteProfilePlanV1:
    """Decide one profile against one Draft without touching either.

    The Draft is read, never written.  The returned plan is frozen and records
    the fingerprint of the Draft it saw, so a caller can prove no mutation
    occurred by re-fingerprinting afterwards.
    """

    signature = _PROFILES_BY_ID[profile_id]
    fingerprint = draft_structure_fingerprint(draft)
    facts = _DraftFacts(draft, approved_assumption_ids)

    # A query that states an extremal objective is a different question from
    # the exact-value one, and only a profile that explicitly understands the
    # objective may even consider the draft.  Every other profile refuses
    # here, structurally, so a minimum question can never be closed by an
    # exact-value reader that happens to match the rest of the shape.
    if facts.has_query_objective and profile_id not in _OBJECTIVE_AWARE_PROFILES:
        return CompleteProfilePlanV1(
            profile_id=profile_id,
            disposition=PlanDisposition.not_applicable,
            prerequisites=(),
            draft_fingerprint=fingerprint,
        )

    if not signature.applies(facts):
        return CompleteProfilePlanV1(
            profile_id=profile_id,
            disposition=PlanDisposition.not_applicable,
            prerequisites=(),
            draft_fingerprint=fingerprint,
        )

    prerequisites = tuple(
        CompleteProfilePrerequisiteV1(
            prerequisite_id=name, kind=kind, disposition=resolve(facts)
        )
        for name, kind, resolve in signature.prerequisites
    )
    observed = {item.disposition for item in prerequisites}

    disposition = PlanDisposition.complete
    for failure in _FAILURE_PRECEDENCE:
        if failure in observed:
            disposition = _FAILURE_VERDICT[failure]
            break
    else:
        # A Draft whose own typed structure already asks a reader to decide can
        # never be `complete`, however well the profile's own slots resolve.
        if facts.has_blocking_ambiguity:
            disposition = PlanDisposition.needs_confirmation

    if disposition is PlanDisposition.complete and facts.has_blocking_ambiguity:
        disposition = PlanDisposition.needs_confirmation

    return CompleteProfilePlanV1(
        profile_id=profile_id,
        disposition=disposition,
        prerequisites=prerequisites,
        draft_fingerprint=fingerprint,
    )


def plan_every_profile(
    draft: Any, *, approved_assumption_ids: Iterable[str] = ()
) -> tuple[CompleteProfilePlanV1, ...]:
    """Plan every profile against one Draft, in a stable order."""

    approved = tuple(approved_assumption_ids)
    return tuple(
        plan_complete_profile(
            item.profile_id, draft, approved_assumption_ids=approved
        )
        for item in _PROFILES
    )


# --------------------------------------------------------------------------
# Census: counts only
# --------------------------------------------------------------------------


class CompleteProfileFeasibilityV1(FrozenStrictModel):
    """Aggregate feasibility of one profile over every reachable context.

    Counts only.  No case ID, family, split, problem text, expected answer,
    expected terminal, or gold graph reaches this record, and no field can carry
    one: every field is an integer.
    """

    profile_id: ProfileId
    complete_source_grounded: int = Field(ge=0)
    complete_with_closed_server_derivations: int = Field(ge=0)
    needs_confirmation: int = Field(ge=0)
    insufficient_information: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    not_applicable: int = Field(ge=0)

    @property
    def complete(self) -> int:
        return (
            self.complete_source_grounded
            + self.complete_with_closed_server_derivations
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id.value,
            "complete_source_grounded": self.complete_source_grounded,
            "complete_with_closed_server_derivations": (
                self.complete_with_closed_server_derivations
            ),
            "needs_confirmation": self.needs_confirmation,
            "insufficient_information": self.insufficient_information,
            "unsupported": self.unsupported,
            "not_applicable": self.not_applicable,
        }


class CompleteProfileCensusV1(FrozenStrictModel):
    """The whole census: one feasibility row per profile, and nothing else."""

    version: VersionToken = COMPLETE_PROFILE_CENSUS_VERSION
    context_count: int = Field(ge=0)
    profiles: tuple[CompleteProfileFeasibilityV1, ...] = Field(max_length=64)

    def highest_yield(self) -> CompleteProfileFeasibilityV1 | None:
        """The profile with the largest nonzero complete population.

        Ties break on the profile ID so the choice is deterministic and is never
        influenced by corpus order.
        """

        ranked = sorted(
            (item for item in self.profiles if item.complete),
            key=lambda item: (-item.complete, item.profile_id.value),
        )
        return ranked[0] if ranked else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "context_count": self.context_count,
            "profiles": [item.as_dict() for item in self.profiles],
            "highest_yield_profile": (
                self.highest_yield().profile_id.value
                if self.highest_yield() is not None
                else None
            ),
        }


def build_complete_profile_census(
    plan_sets: Iterable[Sequence[CompleteProfilePlanV1]],
) -> CompleteProfileCensusV1:
    """Aggregate per-context plans into per-profile counts.

    The input is one plan set per reachable context.  Only counts survive.
    """

    tally: dict[ProfileId, Counter[str]] = {
        item.profile_id: Counter() for item in _PROFILES
    }
    contexts = 0
    for plans in plan_sets:
        contexts += 1
        for plan in plans:
            bucket = tally[plan.profile_id]
            if plan.disposition is PlanDisposition.complete:
                key = (
                    "complete_with_closed_server_derivations"
                    if plan.uses_server_derivation
                    else "complete_source_grounded"
                )
            else:
                key = plan.disposition.value
            bucket[key] += 1

    return CompleteProfileCensusV1(
        context_count=contexts,
        profiles=tuple(
            CompleteProfileFeasibilityV1(
                profile_id=item.profile_id,
                complete_source_grounded=tally[item.profile_id][
                    "complete_source_grounded"
                ],
                complete_with_closed_server_derivations=tally[item.profile_id][
                    "complete_with_closed_server_derivations"
                ],
                needs_confirmation=tally[item.profile_id]["needs_confirmation"],
                insufficient_information=tally[item.profile_id][
                    "insufficient_information"
                ],
                unsupported=tally[item.profile_id]["unsupported"],
                not_applicable=tally[item.profile_id]["not_applicable"],
            )
            for item in _PROFILES
        ),
    )


__all__ = [
    "COMPLETE_PROFILE_CENSUS_VERSION",
    "COMPLETE_PROFILE_PLANNER_VERSION",
    "CompleteProfileCensusV1",
    "CompleteProfileFeasibilityV1",
    "CompleteProfilePlanV1",
    "CompleteProfilePrerequisiteV1",
    "PlanDisposition",
    "PrerequisiteDisposition",
    "PrerequisiteKind",
    "ProfileId",
    "build_complete_profile_census",
    "draft_structure_fingerprint",
    "plan_complete_profile",
    "plan_every_profile",
]
