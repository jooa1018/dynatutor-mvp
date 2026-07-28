"""Why a blocked law does not emit, and what would actually change that.

The law-prerequisite matrix measures one thing: how often a law's *declared*
prerequisites hold while its emission function produces nothing.  That number is
a signal, not an answer.  ``polar_velocity_radial`` declares a single required
role — velocity — so every context carrying a velocity counts as declared
satisfied, including contexts that have nothing to do with polar coordinates.
Reading its gap as "58 cases a polar frame would unlock" would be wrong.

This module answers the two questions the gap cannot.

**What does the emission function block on first?**  An ordered ladder of typed
structural probes, derived from the rule's own declaration and the context's own
typed census, reports the first prerequisite the emitter cannot satisfy.  The
order follows the emitters' own dependency order: a component check is written
as ``frame_id == frame.frame_id``, so a frame must exist before a component can
be judged, and so on down the ladder.

**Would supplying it actually help?**  A counterfactual: the real
``apply_core_laws`` is re-run against the same context augmented with the
minimum typed structure the probe named, and the answer is whatever the engine
says.  A law that stays silent after being handed a complete frame, axes, scope,
and component topology is not blocked by a missing frame, whatever its
declared-prerequisite gap says.

The counterfactual contexts exist only inside this module.  They are never
returned, never projected back into a Draft or IR, and never reach a runtime
answer; the diagnosis carries counts and closed vocabulary codes only.  No case
ID, family, split, problem text, quote, entity name, expected terminal, or
expected answer participates in anything here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable

from engine.mechanics.contracts import (
    AxisName,
    EntityPrimitive,
    GeometryRelationKind,
    IRAxisBinding,
    IRAxisDirection,
    IRReferenceFrame,
    IRWorldOrigin,
    QuantityComponent,
    QuantityRole,
    ReferenceFrameType,
)
from engine.mechanics.laws import apply_core_laws
from engine.mechanics.laws.base import BoundQuantity, LawContext, LawRule
from engine.mechanics.laws.core import _COMPONENT_ROLES, core_law_catalog

from evaluation.phase56_stage7.law_prerequisites import (
    LawTopologyTier,
    topology_tier,
)

BLOCKED_LAW_DIAGNOSIS_VERSION = "stage7-blocked-law-diagnosis-v1"

# Identifiers for the evaluator-only counterfactual structures.  They exist for
# the duration of one diagnosis and are discarded with it.
_CF_PREFIX = "cfdiag"
_CF_FRAME_ID = f"{_CF_PREFIX}_frame"
_CF_EVIDENCE_ID = f"{_CF_PREFIX}_evidence"


class UnmetPrerequisite(str, Enum):
    """The typed structure an emission function needs and does not have.

    Closed vocabulary.  Every blocked (context, law) pair receives exactly one.
    """

    missing_frame = "missing_frame"
    wrong_frame_type = "wrong_frame_type"
    missing_axis = "missing_axis"
    missing_component = "missing_component"
    missing_endpoint = "missing_endpoint"
    missing_point = "missing_point"
    missing_interaction_quantity = "missing_interaction_quantity"
    cardinality_mismatch = "cardinality_mismatch"
    scope_mismatch = "scope_mismatch"
    law_not_semantically_applicable = "law_not_semantically_applicable"


class CounterfactualOutcome(str, Enum):
    """What the real engine does when the named structure is supplied.

    ``*_frame_alone_unlocks`` means the law emitted once a frame of that type
    was added and nothing else changed.  The two ``required``/``does_not``
    members are the honest outcomes when a frame is not the operative blocker.
    """

    cartesian_1d_frame_alone_unlocks = "cartesian_1d_frame_alone_unlocks"
    cartesian_2d_frame_alone_unlocks = "cartesian_2d_frame_alone_unlocks"
    polar_frame_alone_unlocks = "polar_frame_alone_unlocks"
    frame_plus_component_topology_required = "frame_plus_component_topology_required"
    frame_does_not_close_the_law = "frame_does_not_close_the_law"
    law_not_semantically_applicable = "law_not_semantically_applicable"


# The entity primitives each topology tier is about.  A law that needs a rigid
# body's own points is not about a problem whose source declares no rigid body,
# however many velocities that problem carries.  Derived from the tier, which is
# itself derived from the rule, so a new law inherits this rather than needing an
# entry here.
_TIER_SUBJECT_PRIMITIVES: dict[LawTopologyTier, frozenset[EntityPrimitive]] = {
    LawTopologyTier.rigid_body: frozenset(
        {
            EntityPrimitive.rigid_body,
            EntityPrimitive.body_component,
            EntityPrimitive.pulley,
            EntityPrimitive.gear,
        }
    ),
    LawTopologyTier.free_body: frozenset(
        {
            EntityPrimitive.particle,
            EntityPrimitive.rigid_body,
            EntityPrimitive.body_component,
            EntityPrimitive.mass_center,
            EntityPrimitive.system,
        }
    ),
    LawTopologyTier.particle_kinematics: frozenset(
        {
            EntityPrimitive.particle,
            EntityPrimitive.rigid_body,
            EntityPrimitive.body_component,
            EntityPrimitive.mass_center,
            EntityPrimitive.system,
            EntityPrimitive.point,
        }
    ),
    LawTopologyTier.particle_dynamics: frozenset(
        {
            EntityPrimitive.particle,
            EntityPrimitive.rigid_body,
            EntityPrimitive.body_component,
            EntityPrimitive.mass_center,
            EntityPrimitive.system,
        }
    ),
}

# Components that name a direction in a frame, as opposed to a magnitude or an
# unresolved scalar.  A law that relates components needs quantities typed onto
# axes; one that relates magnitudes does not.
_AXIS_COMPONENTS: frozenset[QuantityComponent] = frozenset(
    {
        QuantityComponent.x,
        QuantityComponent.y,
        QuantityComponent.z,
        QuantityComponent.radial,
        QuantityComponent.transverse,
        QuantityComponent.tangential,
        QuantityComponent.normal,
    }
)

# Geometry a polar or plane-rigid profile is built on.  A source that declares
# none of these, and no observer entity, and no directional component, is not
# posing a problem in a rotating or attached-point geometry.
_FRAME_PROJECTION_GEOMETRY: frozenset[GeometryRelationKind] = frozenset(
    {
        GeometryRelationKind.radius,
        GeometryRelationKind.attached,
        GeometryRelationKind.tangent,
    }
)

_FRAME_LADDER: tuple[tuple[ReferenceFrameType, tuple[AxisName, ...], CounterfactualOutcome], ...] = (
    (
        ReferenceFrameType.cartesian_1d,
        (AxisName.x,),
        CounterfactualOutcome.cartesian_1d_frame_alone_unlocks,
    ),
    (
        ReferenceFrameType.cartesian_2d,
        (AxisName.x, AxisName.y),
        CounterfactualOutcome.cartesian_2d_frame_alone_unlocks,
    ),
    (
        ReferenceFrameType.radial_transverse,
        (AxisName.radial, AxisName.transverse),
        CounterfactualOutcome.polar_frame_alone_unlocks,
    ),
)

# Which axis a component belongs to, for the component-topology rung.  Only
# these seven components name an axis; magnitude and unspecified do not.
_COMPONENT_FOR_AXIS: dict[AxisName, QuantityComponent] = {
    AxisName.x: QuantityComponent.x,
    AxisName.y: QuantityComponent.y,
    AxisName.z: QuantityComponent.z,
    AxisName.radial: QuantityComponent.radial,
    AxisName.transverse: QuantityComponent.transverse,
    AxisName.tangent: QuantityComponent.tangential,
    AxisName.normal: QuantityComponent.normal,
}


def _counterfactual_frame(
    frame_type: ReferenceFrameType, axes: tuple[AxisName, ...]
) -> IRReferenceFrame:
    """A world-anchored frame with fully declared axes, for diagnosis only."""

    return IRReferenceFrame(
        frame_id=_CF_FRAME_ID,
        frame_type=frame_type,
        origin=IRWorldOrigin(),
        axes=tuple(
            IRAxisBinding(
                axis=axis,
                direction=IRAxisDirection(frame_id=_CF_FRAME_ID, axis=axis, sign=1),
            )
            for axis in axes
        ),
        evidence_refs=(_CF_EVIDENCE_ID,),
    )


def _with_frame(
    context: LawContext,
    frame_type: ReferenceFrameType,
    axes: tuple[AxisName, ...],
    *,
    scope_quantities: bool = False,
    component_topology: bool = False,
) -> LawContext:
    """Return the same context plus the named typed structure, nothing else.

    ``scope_quantities`` expresses the kinematic description in the new frame:
    every quantity and every motion interval that names *no* frame now names
    this one.  Both matter — the law profiles check ``interval.frame_id`` as
    well as each quantity's, so binding only the quantities leaves the frame
    half-supplied and the counterfactual would under-report what a real frame
    projection achieves.  A record that already names a frame keeps it: filling
    an absent binding is what adding a frame does, overwriting a stated one is
    rewriting the source.

    ``component_topology`` additionally retypes each component-bearing quantity
    onto one of the frame's axes.  That is a further claim about the model — it
    decides which axis each quantity lies along — so it is a separate rung, and
    a law that needs it is not a law a frame alone would close.
    """

    frame = _counterfactual_frame(frame_type, axes)
    quantities = context.quantities
    intervals = context.motion_intervals
    if scope_quantities or component_topology:
        rebound: list[BoundQuantity] = []
        for index, quantity in enumerate(context.quantities):
            update: dict[str, Any] = {}
            if quantity.frame_id is None:
                update["frame_id"] = frame.frame_id
            if component_topology and quantity.role in _COMPONENT_ROLES:
                axis = axes[index % len(axes)]
                update["component"] = _COMPONENT_FOR_AXIS[axis]
            rebound.append(replace(quantity, **update) if update else quantity)
        quantities = tuple(rebound)
        intervals = tuple(
            item.model_copy(update={"frame_id": frame.frame_id})
            if item.frame_id is None
            else item
            for item in context.motion_intervals
        )
    return replace(
        context,
        reference_frames=(*context.reference_frames, frame),
        motion_intervals=intervals,
        quantities=quantities,
    )


def _emits(context: LawContext, law_id: str) -> bool:
    """Ask the real engine, not a restatement of it."""

    try:
        return any(item.rule.law_id == law_id for item in apply_core_laws(context))
    except Exception:
        # A counterfactual context the engine rejects has not unlocked anything.
        return False


def _needs_frame(rule: LawRule) -> bool:
    return any(role in _COMPONENT_ROLES for role in rule.required_roles)


def _needs_point(rule: LawRule) -> bool:
    return topology_tier(rule) is LawTopologyTier.rigid_body


def _needs_endpoint(rule: LawRule) -> bool:
    return any(
        role in {QuantityRole.duration, QuantityRole.time} for role in rule.required_roles
    )


def _subject_primitives(context: LawContext) -> frozenset[EntityPrimitive]:
    return frozenset(item.primitive for item in context.entities)


def _semantically_applicable(context: LawContext, rule: LawRule) -> bool:
    """False when the source never describes what the law is about.

    Two independent reasons, both read from the source's own typed structure.
    A law about a rigid body's points has nothing to say about a problem whose
    source declares no such body.  And a law that exists to relate components in
    a rotating or attached-point geometry has nothing to say about a source that
    declares no observer entity, no such geometry, and no directional component
    anywhere — supplying it a frame would be building a model for nobody.
    """

    tier = topology_tier(rule)
    wanted = _TIER_SUBJECT_PRIMITIVES[tier]
    if not (_subject_primitives(context) & wanted):
        return False
    if tier is LawTopologyTier.rigid_body:
        # Its subject exists, but a point law needs the body's own points.  That
        # is a missing structure, not a missing subject; the ladder reports it.
        return True
    if _needs_frame(rule):
        declares_observer = EntityPrimitive.reference_frame in _subject_primitives(context)
        declares_geometry = any(
            item.kind in _FRAME_PROJECTION_GEOMETRY for item in context.geometry
        )
        declares_component = any(
            item.component in _AXIS_COMPONENTS for item in context.quantities
        )
        if not (declares_observer or declares_geometry or declares_component):
            return False
    return True


def context_with_counterfactual_frame(
    context: LawContext,
    frame_type: ReferenceFrameType = ReferenceFrameType.cartesian_2d,
    axes: tuple[AxisName, ...] = (AxisName.x, AxisName.y),
    *,
    scope_quantities: bool = True,
    component_topology: bool = True,
) -> LawContext:
    """The frame rung of this module's ladder, for another diagnostic to reuse.

    Exposed so a second counterfactual can ask "does this close once the frame
    is also supplied?" against *this* implementation rather than a second copy
    of it that could drift.  Diagnosis only: the returned context never reaches
    a Draft, a runtime result, or an answer.
    """

    return _with_frame(
        context,
        frame_type,
        axes,
        scope_quantities=scope_quantities,
        component_topology=component_topology,
    )


def law_is_semantically_applicable(context: LawContext, rule: LawRule) -> bool:
    """Whether the source describes what this law is about at all.

    Public for the same reason as `context_with_counterfactual_frame`: one
    implementation, read by every diagnostic that needs the distinction between
    "blocked" and "not about this".
    """

    return _semantically_applicable(context, rule)


def _frame_of_admissible_type(context: LawContext) -> bool:
    return any(
        item.frame_type
        in {frame_type for frame_type, _, _ in _FRAME_LADDER}
        for item in context.reference_frames
    )


def _axes_complete(context: LawContext) -> bool:
    """Every frame declares axes that name themselves in their own frame."""

    for frame in context.reference_frames:
        if not frame.axes:
            return False
        for binding in frame.axes:
            direction = binding.direction
            if (
                getattr(direction, "kind", None) != "axis"
                or getattr(direction, "frame_id", None) != frame.frame_id
                or getattr(direction, "axis", None) is not binding.axis
            ):
                return False
    return True


def _required_quantities(context: LawContext, rule: LawRule) -> tuple[BoundQuantity, ...]:
    wanted = set(rule.required_roles)
    return tuple(item for item in context.quantities if item.role in wanted)


def first_unmet_prerequisite(
    context: LawContext, rule: LawRule
) -> UnmetPrerequisite:
    """The first typed structure the emission function cannot satisfy.

    The order is the emitters' own: every component, point, and scope check in
    the catalogue is written relative to a frame, so a missing frame is reached
    before anything expressed in one can be judged.  Nothing here is a claim
    about what supplying it would achieve — that is the counterfactual's job.
    """

    if not _semantically_applicable(context, rule):
        return UnmetPrerequisite.law_not_semantically_applicable

    if _needs_frame(rule):
        if not context.reference_frames:
            return UnmetPrerequisite.missing_frame
        if not _frame_of_admissible_type(context):
            return UnmetPrerequisite.wrong_frame_type
        if not _axes_complete(context):
            return UnmetPrerequisite.missing_axis

    if _needs_point(rule) and not context.points:
        return UnmetPrerequisite.missing_point

    required = _required_quantities(context, rule)
    if _needs_frame(rule) and not any(
        item.component in _AXIS_COMPONENTS for item in required
    ):
        return UnmetPrerequisite.missing_component

    if rule.required_interactions:
        owned_roles = {item.role for item in required}
        if not owned_roles >= set(rule.required_roles):
            return UnmetPrerequisite.missing_interaction_quantity

    if _needs_endpoint(rule) and not any(
        interval.start_event_id is not None or interval.end_event_id is not None
        for interval in context.motion_intervals
    ):
        return UnmetPrerequisite.missing_endpoint

    per_role = Counter(item.role for item in required)
    if any(count > 2 for count in per_role.values()):
        return UnmetPrerequisite.cardinality_mismatch

    return UnmetPrerequisite.scope_mismatch


def counterfactual_outcome(
    context: LawContext, rule: LawRule
) -> CounterfactualOutcome:
    """Run the real engine against the minimally augmented context.

    Each rung adds strictly more typed structure than the one before, so the
    first rung that emits names the least structure that actually closes the
    law.  A law that emits at no rung is not blocked on a frame.
    """

    if not _semantically_applicable(context, rule):
        return CounterfactualOutcome.law_not_semantically_applicable

    for frame_type, axes, outcome in _FRAME_LADDER:
        if _emits(
            _with_frame(context, frame_type, axes, scope_quantities=True), rule.law_id
        ):
            return outcome

    for frame_type, axes, _ in _FRAME_LADDER:
        if _emits(
            _with_frame(
                context, frame_type, axes, scope_quantities=True, component_topology=True
            ),
            rule.law_id,
        ):
            return CounterfactualOutcome.frame_plus_component_topology_required

    return CounterfactualOutcome.frame_does_not_close_the_law


# The emission functions ``apply_core_laws`` dispatches to, in its own order.
# The first five are whole-context templates that return early when they match;
# the rest each contribute independently.  A per-law diagnosis says which law is
# blocked, which turns out to be the wrong question when a whole family is
# unreachable — a family that never fires cannot be unblocked one law at a time.
# A test asserts every name here exists, so a renamed or removed emitter fails
# rather than silently reporting zero.
_TEMPLATE_EMITTERS: tuple[str, ...] = (
    "_vertical_circle_emissions",
    "_rolling_energy_emissions",
    "_spring_energy_speed_emissions",
    "_curve_speed_emissions",
    "_wave_f_emissions",
)

_INCREMENTAL_EMITTERS: tuple[str, ...] = (
    "_constant_velocity_emissions",
    "_constant_acceleration_emissions",
    "_projectile_boundary_emissions",
    "_event_boundary_emissions",
    "_constant_angular_acceleration_emissions",
    "_chain_kinematics_emissions",
    "_incline_gravity_contact_emissions",
    "_horizontal_fixed_contact_emissions",
    "_horizontal_surface_contact_emissions",
    "_incline_hanging_rope_emissions",
    "_massive_pulley_atwood_emissions",
    "_fixed_pulley_common_acceleration_readout_emissions",
    "_newton_emissions",
    "_primitive_interaction_emissions",
    "_work_energy_emissions",
    "_momentum_emissions",
    "_rigid_emissions",
    "_topology_constraint_emissions",
    "_vibration_emissions",
)


def _emitter(name: str):
    from engine.mechanics.laws import core

    return getattr(core, name)


def _family_fires(context: LawContext, name: str) -> bool:
    try:
        return bool(_emitter(name)(context))
    except Exception:
        return False


@dataclass(frozen=True, slots=True)
class EmitterFamilyReach:
    """How many real contexts each emission family fires on."""

    family: str
    kind: str
    contexts_fired: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "kind": self.kind,
            "contexts_fired": self.contexts_fired,
        }


def measure_emitter_family_reach(
    contexts: Iterable[LawContext],
) -> tuple[tuple[EmitterFamilyReach, ...], int]:
    """Measure which emission families are alive, and how many contexts are dead.

    Returns the per-family counts and the number of contexts for which
    ``apply_core_laws`` produces nothing at all.  A dead family is a package
    candidate in a way a blocked law is not: it names a whole body of physics the
    projection currently cannot reach.
    """

    materialised = tuple(contexts)
    reach = [
        EmitterFamilyReach(
            family=name,
            kind=kind,
            contexts_fired=sum(
                1 for context in materialised if _family_fires(context, name)
            ),
        )
        for kind, names in (
            ("template", _TEMPLATE_EMITTERS),
            ("incremental", _INCREMENTAL_EMITTERS),
        )
        for name in names
    ]
    silent = sum(1 for context in materialised if not apply_core_laws(context))
    return tuple(reach), silent


@dataclass(frozen=True, slots=True)
class BlockedLawDiagnosis:
    """One blocked law's measured diagnosis over every context that blocks it."""

    law_id: str
    tier: str
    declared_satisfied: int
    emitted: int
    unmet_counts: tuple[tuple[str, int], ...]
    counterfactual_counts: tuple[tuple[str, int], ...]

    @property
    def blocked_contexts(self) -> int:
        return sum(count for _, count in self.unmet_counts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "law_id": self.law_id,
            "tier": self.tier,
            "declared_satisfied": self.declared_satisfied,
            "emitted": self.emitted,
            "blocked_contexts": self.blocked_contexts,
            "unmet_counts": dict(self.unmet_counts),
            "counterfactual_counts": dict(self.counterfactual_counts),
        }


@dataclass(frozen=True, slots=True)
class BlockedLawDiagnosisReport:
    """The aggregate that decides whether a frame package is worth building."""

    version: str
    context_count: int
    diagnosed_law_count: int
    laws: tuple[BlockedLawDiagnosis, ...]
    unmet_totals: tuple[tuple[str, int], ...]
    counterfactual_totals: tuple[tuple[str, int], ...]
    emitter_families: tuple[EmitterFamilyReach, ...] = ()
    silent_contexts: int = 0

    @property
    def frame_alone_unlocks(self) -> int:
        """Blocked pairs a frame alone would close, across every frame type."""

        totals = dict(self.counterfactual_totals)
        return sum(
            totals.get(outcome.value, 0)
            for outcome in (
                CounterfactualOutcome.cartesian_1d_frame_alone_unlocks,
                CounterfactualOutcome.cartesian_2d_frame_alone_unlocks,
                CounterfactualOutcome.polar_frame_alone_unlocks,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "context_count": self.context_count,
            "diagnosed_law_count": self.diagnosed_law_count,
            "unmet_totals": dict(self.unmet_totals),
            "counterfactual_totals": dict(self.counterfactual_totals),
            "frame_alone_unlocks": self.frame_alone_unlocks,
            "silent_contexts": self.silent_contexts,
            "live_emitter_families": self.live_emitter_families,
            "dead_emitter_families": self.dead_emitter_families,
            "emitter_families": [item.as_dict() for item in self.emitter_families],
            "laws": [item.as_dict() for item in self.laws],
        }

    @property
    def live_emitter_families(self) -> int:
        return sum(1 for item in self.emitter_families if item.contexts_fired)

    @property
    def dead_emitter_families(self) -> int:
        return sum(1 for item in self.emitter_families if not item.contexts_fired)


def diagnose_blocked_laws(
    contexts: Iterable[LawContext],
    *,
    blocked_law_ids: Iterable[str] | None = None,
) -> BlockedLawDiagnosisReport:
    """Diagnose every law that declares itself satisfied and emits nothing.

    ``blocked_law_ids`` restricts the diagnosis to a named set; by default every
    catalogue law is considered and the ones that never block simply report no
    blocked contexts.
    """

    from evaluation.phase56_stage7.law_prerequisites import _declared_satisfied

    materialised = tuple(contexts)
    catalog = core_law_catalog()
    if blocked_law_ids is not None:
        wanted = set(blocked_law_ids)
        catalog = tuple(rule for rule in catalog if rule.law_id in wanted)

    diagnoses: list[BlockedLawDiagnosis] = []
    unmet_totals: Counter[str] = Counter()
    counterfactual_totals: Counter[str] = Counter()

    for rule in catalog:
        declared = 0
        emitted = 0
        unmet: Counter[str] = Counter()
        outcomes: Counter[str] = Counter()
        for context in materialised:
            if not _declared_satisfied(context, rule):
                continue
            declared += 1
            if _emits(context, rule.law_id):
                emitted += 1
                continue
            unmet[first_unmet_prerequisite(context, rule).value] += 1
            outcomes[counterfactual_outcome(context, rule).value] += 1
        if declared == 0 or declared == emitted:
            continue
        diagnoses.append(
            BlockedLawDiagnosis(
                law_id=rule.law_id,
                tier=topology_tier(rule).value,
                declared_satisfied=declared,
                emitted=emitted,
                unmet_counts=tuple(sorted(unmet.items())),
                counterfactual_counts=tuple(sorted(outcomes.items())),
            )
        )
        unmet_totals.update(unmet)
        counterfactual_totals.update(outcomes)

    families, silent = measure_emitter_family_reach(materialised)
    return BlockedLawDiagnosisReport(
        version=BLOCKED_LAW_DIAGNOSIS_VERSION,
        context_count=len(materialised),
        diagnosed_law_count=len(diagnoses),
        laws=tuple(sorted(diagnoses, key=lambda item: (-item.blocked_contexts, item.law_id))),
        unmet_totals=tuple(sorted(unmet_totals.items())),
        counterfactual_totals=tuple(sorted(counterfactual_totals.items())),
        emitter_families=families,
        silent_contexts=silent,
    )


__all__ = [
    "BLOCKED_LAW_DIAGNOSIS_VERSION",
    "BlockedLawDiagnosis",
    "BlockedLawDiagnosisReport",
    "CounterfactualOutcome",
    "EmitterFamilyReach",
    "UnmetPrerequisite",
    "context_with_counterfactual_frame",
    "counterfactual_outcome",
    "diagnose_blocked_laws",
    "first_unmet_prerequisite",
    "law_is_semantically_applicable",
    "measure_emitter_family_reach",
]
