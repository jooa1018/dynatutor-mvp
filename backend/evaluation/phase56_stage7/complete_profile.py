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

COMPLETE_PROFILE_PLANNER_VERSION = "phase56-stage7-complete-profile-planner-v1"
COMPLETE_PROFILE_CENSUS_VERSION = "phase56-stage7-complete-profile-census-v1"
COMPLETE_PROFILE_PLAN_SCHEMA = "dynatutor.phase56_stage7.complete_profile_plan"
COMPLETE_PROFILE_PLAN_VERSION = "1.0"


class ProfileId(str, Enum):
    """The bounded set of profiles the census measures.

    A profile is a *shape a law needs*, not a problem family.  Two sources with
    different families reach the same profile when their typed structure agrees,
    and one family can reach different profiles case by case.
    """

    free_flight_gravity = "free_flight_gravity"
    explicit_resultant_force = "explicit_resultant_force"
    collision_restitution = "collision_restitution"
    fixed_pulley = "fixed_pulley"
    incline_hanging_pulley = "incline_hanging_pulley"
    rolling_energy = "rolling_energy"
    work_energy = "work_energy"
    impulse_momentum = "impulse_momentum"
    horizontal_contact = "horizontal_contact"
    incline_contact = "incline_contact"
    rigid_fixed_axis = "rigid_fixed_axis"
    # Declared in the order the closure step considers them, so the enum and the
    # signature table cannot drift apart.
    slot_pin_relative_frame = "slot_pin_relative_frame"
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


class _DraftFacts:
    """One pass of typed readings, shared by every profile signature."""

    __slots__ = (
        "approved",
        "axis_families",
        "bounded_intervals",
        "geometry",
        "has_blocking_ambiguity",
        "interactions",
        "observer_count",
        "primitives",
        "query_component",
        "query_role",
        "roles",
    )

    def __init__(self, draft: Any, approved_assumption_ids: Iterable[str]) -> None:
        self.roles = _roles(draft)
        self.approved = _approved_kinds(draft, approved_assumption_ids)
        self.interactions = _interaction_kinds(draft)
        self.geometry = _geometry_kinds(draft)
        self.primitives = _primitives(draft)
        self.bounded_intervals = _bounded_intervals(draft)
        self.query_role = _query_role(draft)
        self.query_component = _query_component(draft)
        self.axis_families = _directed_axis_families(draft)
        self.observer_count = len(_observer_entities(draft))
        self.has_blocking_ambiguity = _blocking_ambiguity(draft)


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
    """A lone force is a resultant only when a typed authority proves it is.

    No such authority exists in the frozen Draft contract, so a source that
    states one force and no free body cannot be closed as Newton's second law.
    Treating the force as the resultant anyway is exactly the confident-wrong
    solve the hard-safety gate forbids, so this reports `missing` rather than
    guessing — and it will keep reporting `missing` until a real authority
    exists to read.
    """

    return PrerequisiteDisposition.missing


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
    # One stated force treated as the resultant.  Deliberately never closes.
    _ProfileSignature(
        ProfileId.explicit_resultant_force,
        lambda facts: (
            bool(facts.roles.get("force"))
            and bool(facts.roles.get("mass"))
            and not facts.interactions
        ),
        (
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_force", PrerequisiteKind.interaction_quantity,
             _needs_role("force")),
            ("authority_force_is_resultant", PrerequisiteKind.authority,
             _resultant_force_authority),
        ),
    ),
    _ProfileSignature(
        ProfileId.collision_restitution,
        lambda facts: bool(facts.interactions.get("collision")),
        (
            ("interaction_collision", PrerequisiteKind.interaction,
             _needs_interaction("collision")),
            ("quantity_mass", PrerequisiteKind.interaction_quantity,
             _needs_role("mass")),
            ("quantity_velocity", PrerequisiteKind.interaction_quantity,
             _needs_role("velocity")),
            ("quantity_restitution", PrerequisiteKind.interaction_quantity,
             _needs_role("coefficient_restitution")),
            ("interval_bounded", PrerequisiteKind.state_condition, _bounded_interval),
            ("authority_external_impulse_negligible", PrerequisiteKind.authority,
             _needs_authority("external_impulse_negligible")),
            ("symbol_post_velocity", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
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
    _ProfileSignature(
        ProfileId.rigid_fixed_axis,
        lambda facts: (
            bool(facts.primitives.get("rigid_body"))
            and bool(facts.roles.get("angular_velocity"))
        ),
        (
            ("quantity_angular_velocity", PrerequisiteKind.interaction_quantity,
             _needs_role("angular_velocity")),
            ("quantity_radius", PrerequisiteKind.interaction_quantity,
             _needs_role("radius")),
            ("capability_rigid_point_authority", PrerequisiteKind.capability,
             _catalogue_has_no_capability),
            ("geometry_attached", PrerequisiteKind.geometry,
             _needs_geometry("attached")),
            ("capability_body_fixed_frame", PrerequisiteKind.capability,
             _catalogue_has_no_capability),
            ("symbol_point_speed", PrerequisiteKind.unknown_symbol,
             _generated_unknown),
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
