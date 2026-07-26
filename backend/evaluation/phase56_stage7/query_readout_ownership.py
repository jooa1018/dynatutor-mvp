"""Does query-readout ownership actually block anything?  Measure, don't assume.

The structural blocker census reports how many contexts ask for a quantity
owned by an entity outside the engine's free-body set.  That number is a
**count of a property**, not evidence that the property is what stops the
answer.  A context can carry a non-free-body query subject and be blocked
several layers earlier — no frame, no interaction, no applicable law at all —
in which case binding the readout to a carrier changes nothing and building an
ownership capability would buy nothing.

This module settles that by experiment.  For each such context it constructs a
counterfactual that adds **only** a typed query-readout binding — the source
Draft is not modified, no entity primitive is changed, nothing is added to the
engine's free-body set — and asks the real `apply_core_laws` whether the queried
unknown is now written about.  When it is not, the frame rung of the existing
blocked-law ladder is added on top, which separates "ownership is the wall" from
"ownership is one of several walls" from "ownership is not a wall here".

Diagnosis only.  A counterfactual context never becomes a Draft, never reaches
normalization, compilation, solving, or verification, and never contributes to a
runtime result or an answer.  A test holds the production path free of any
import of this module.

Every field of every record is a count over a closed vocabulary.  Nothing here
reads or stores a case ID, family, split, chapter, difficulty, tag, expected
system type, expected terminal, expected answer, gold graph, filename, or
problem text.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from enum import Enum
from typing import Any, Iterable, Sequence

from engine.mechanics.contracts import (
    AssumptionDisposition,
    Entity as IREntity,
    EntityPrimitive,
    GeometryRelationKind,
    Interaction as IRInteraction,
    InteractionKind,
    Point as IRPoint,
    PointRole,
    QuantityComponent,
    QuantityRole,
    QuantityShape,
)
from engine.mechanics.laws.base import BoundQuantity, LawContext
from engine.mechanics.laws.core import (
    CORE_LAW_CATALOG,
    apply_core_laws,
    free_body_primitive_names,
)
from engine.mechanics.math_ast import DimensionVector, SymbolRef

from evaluation.phase56_stage7.blocked_law_diagnosis import (
    context_with_counterfactual_frame,
    law_is_semantically_applicable,
)
from evaluation.phase56_stage7.contracts import FrozenStrictModel

QUERY_READOUT_OWNERSHIP_DIAGNOSIS_VERSION = (
    "phase56-stage7-query-readout-ownership-diagnosis-v1"
)


class ReadoutBindingKind(str, Enum):
    """How a queried readout could be carried by something that has one.

    `direct` is the case that needs no binding at all and never appears in this
    diagnosis; it is named so the vocabulary is the whole space rather than only
    its remainder.
    """

    direct = "direct"
    aggregate_member_equivalence = "aggregate_member_equivalence"
    aggregate_common_magnitude = "aggregate_common_magnitude"
    point_on_body_readout = "point_on_body_readout"
    joint_point_readout = "joint_point_readout"
    joint_reaction_readout = "joint_reaction_readout"


class OwnershipCausalOutcome(str, Enum):
    """What the counterfactual actually showed.

    Each name states exactly which counterfactual produced it, because an
    outcome named after a stronger counterfactual than the one that ran is a
    measurement error waiting to be quoted.  An earlier revision of this module
    named the frame rung `binding_plus_profile_required` while only ever adding
    a frame; the rung is now named for the frame, and a real complete-profile
    rung exists beside it.

    `binding_not_formable` is the honest outcome for a context where no carrier
    is provable from typed structure at all.  It is deliberately *not* folded
    into `binding_does_not_close`: those are contexts where a binding was formed
    and did not help, which is a different fact about a different capability.
    Merging them would reproduce exactly the overclaim this module exists to
    prevent.
    """

    # A single carrier, bound by subject alone.
    single_carrier_binding_alone_unlocks = "single_carrier_binding_alone_unlocks"
    # A carrier *set* whose members typed structure proves share one magnitude.
    aggregate_multi_carrier_binding_unlocks = "aggregate_multi_carrier_binding_unlocks"
    # The point kept as a point: owner body, `point_id`, and its geometry.
    point_scoped_binding_unlocks = "point_scoped_binding_unlocks"
    # The joint kept as a joint, with the requested readout identified.
    joint_scoped_binding_unlocks = "joint_scoped_binding_unlocks"
    # The binding plus a frame — and nothing else.  Named for what it is.
    binding_plus_frame_unlocks = "binding_plus_frame_unlocks"
    # The binding plus the profile structure a law actually needs.
    binding_plus_complete_profile_unlocks = "binding_plus_complete_profile_unlocks"
    binding_not_formable = "binding_not_formable"
    binding_ambiguous = "binding_ambiguous"
    binding_does_not_close = "binding_does_not_close"
    law_not_semantically_applicable = "law_not_semantically_applicable"


# Which "binding alone" outcome each subject primitive reports.  A `system` is
# never reported through the single-carrier outcome even when only one member is
# provable: an aggregate readout is an aggregate readout, and collapsing it to
# the single-carrier name would hide that the aggregate path was what ran.
_SCOPED_UNLOCK_OUTCOME: dict[EntityPrimitive, OwnershipCausalOutcome] = {
    EntityPrimitive.system: OwnershipCausalOutcome.aggregate_multi_carrier_binding_unlocks,
    EntityPrimitive.point: OwnershipCausalOutcome.point_scoped_binding_unlocks,
    EntityPrimitive.joint: OwnershipCausalOutcome.joint_scoped_binding_unlocks,
}

# Geometry that can name the body a point belongs to.  `lies_on` is the kind the
# corpus's `point_on_body` relation projects to; `coincident` and `attached`
# state the same ownership a different way.  Nothing else is read: a `distance`
# or an `angle` mentioning a point says where it is, not whose it is.
_POINT_OWNERSHIP_GEOMETRY: frozenset[GeometryRelationKind] = frozenset(
    {
        GeometryRelationKind.lies_on,
        GeometryRelationKind.coincident,
        GeometryRelationKind.attached,
    }
)
# Geometry and interactions that can name the bodies a joint connects.
_JOINT_OWNERSHIP_GEOMETRY: frozenset[GeometryRelationKind] = frozenset(
    {
        GeometryRelationKind.lies_on,
        GeometryRelationKind.attached,
        GeometryRelationKind.topology_connects,
    }
)
_JOINT_OWNERSHIP_INTERACTIONS: frozenset[InteractionKind] = frozenset(
    {InteractionKind.joint_reaction, InteractionKind.contact}
)
# Geometry and interactions that can name a system's members.  A system is an
# aggregate, so only a record that names the system *itself* alongside a body
# states membership.  Sharing a motion interval is co-scoping, not membership,
# and is measured separately rather than treated as proof.
_AGGREGATE_OWNERSHIP_GEOMETRY: frozenset[GeometryRelationKind] = frozenset(
    {
        GeometryRelationKind.attached,
        GeometryRelationKind.topology_connects,
        GeometryRelationKind.wraps,
        GeometryRelationKind.lies_on,
    }
)
# Geometry that names members of one rope topology together.  This is the
# relation an aggregate common-magnitude proof rests on, so it is deliberately
# narrower than `_AGGREGATE_OWNERSHIP_GEOMETRY`: `lies_on` states support, not
# a shared inextensible path.
_ROPE_TOPOLOGY_GEOMETRY: frozenset[GeometryRelationKind] = frozenset(
    {GeometryRelationKind.topology_connects, GeometryRelationKind.wraps}
)
_INEXTENSIBLE_ROPE_AUTHORITY = "inextensible_rope"

# Roles whose joint readout is a kinematic property of the joint point itself.
# Two bodies meeting at one pin share these exactly, so two connected bodies are
# not an ambiguity for them.
_JOINT_POINT_KINEMATIC_ROLES: frozenset[QuantityRole] = frozenset(
    {
        QuantityRole.position,
        QuantityRole.displacement,
        QuantityRole.velocity,
        QuantityRole.speed,
        QuantityRole.acceleration,
    }
)
# Roles that are a force one body exerts on another *through* the joint.  These
# have a side, and a side the source has not stated is a real ambiguity.
_JOINT_REACTION_ROLES: frozenset[QuantityRole] = frozenset(
    {QuantityRole.force, QuantityRole.moment, QuantityRole.torque}
)

# Identifiers for the evaluator-only counterfactual structures.  They exist for
# the duration of one classification and are discarded with it.
_CF_PREFIX = "cfown"
_CF_EVIDENCE_ID = f"{_CF_PREFIX}_evidence"
_CF_FIELD_ENTITY_ID = f"{_CF_PREFIX}_field"
_FORCE_DIMENSION = DimensionVector(mass=1, length=1, time=-2)


def joint_readout_kind(
    context: LawContext, quantity: BoundQuantity
) -> ReadoutBindingKind | None:
    """Which joint readout the question is actually asking for.

    A joint carries two different kinds of answer and they do not have the same
    ambiguity.  The pin's own motion is one motion whichever body you read it
    from; the reaction through the pin is one body's action on another and has a
    side.  Returning `None` means the role names neither, and nothing is bound.
    """

    if quantity.role in _JOINT_POINT_KINEMATIC_ROLES:
        return ReadoutBindingKind.joint_point_readout
    if quantity.role in _JOINT_REACTION_ROLES:
        return ReadoutBindingKind.joint_reaction_readout
    return None


class OwnershipCausalDiagnosis(FrozenStrictModel):
    """Counts only.  One row per query-subject primitive, plus the totals."""

    version: str = QUERY_READOUT_OWNERSHIP_DIAGNOSIS_VERSION
    context_count: int = 0
    examined_contexts: int = 0
    outcome_counts: tuple[tuple[str, int], ...] = ()
    outcome_by_primitive: tuple[tuple[str, str, int], ...] = ()
    candidate_carrier_counts: tuple[tuple[str, int], ...] = ()
    # Co-scoping is what a system query has instead of a membership relation.
    # Recorded so the absence of a membership route is visible as a measurement
    # rather than inferred from a zero elsewhere.
    aggregate_contexts_with_membership_relation: int = 0
    aggregate_contexts_with_interval_co_subjects_only: int = 0
    # Treating an interval's subject list as membership would be a contract
    # decision, and it has not been made.  This counts what that decision would
    # actually buy, so the decision can be declined or taken on evidence rather
    # than argued.  It never forms a binding used by any other count.
    aggregate_co_subject_route_unlocks: int = 0
    aggregate_co_subject_route_unique_carrier: int = 0
    contexts_with_typed_point_record: int = 0
    # Why an aggregate proof refused, when it did.  Recorded because "not
    # formable" has several causes with entirely different remedies, and a bare
    # total hides which one is actually operating.
    aggregate_refusal_counts: tuple[tuple[str, int], ...] = ()
    free_body_primitives: tuple[str, ...] = ()

    @property
    def causally_blocked_on_ownership(self) -> int:
        """Contexts where a formable binding is what actually moves the engine."""

        unlocking = {
            OwnershipCausalOutcome.single_carrier_binding_alone_unlocks.value,
            OwnershipCausalOutcome.aggregate_multi_carrier_binding_unlocks.value,
            OwnershipCausalOutcome.point_scoped_binding_unlocks.value,
            OwnershipCausalOutcome.joint_scoped_binding_unlocks.value,
            OwnershipCausalOutcome.binding_plus_frame_unlocks.value,
            OwnershipCausalOutcome.binding_plus_complete_profile_unlocks.value,
        }
        return sum(count for key, count in self.outcome_counts if key in unlocking)


def _query_quantity(context: LawContext, query_quantity_id: str) -> BoundQuantity | None:
    for quantity in context.quantities:
        if quantity.quantity_id == query_quantity_id:
            return quantity
    return None


def _writes_about(context: LawContext, quantity_id: str) -> bool:
    """Whether any law actually writes an equation naming this quantity.

    Emission *count* is the wrong measure here: a law that fires about some
    other quantity has not made the question answerable.  Asked of the real
    `apply_core_laws`, never of a restatement of it.
    """

    try:
        return any(
            quantity_id in emission.source_quantity_ids
            for emission in apply_core_laws(context)
        )
    except Exception:
        # A counterfactual the engine rejects has not unlocked anything.
        return False


def _free_body_entity_ids(context: LawContext) -> frozenset[str]:
    free_body = frozenset(free_body_primitive_names())
    return frozenset(
        item.entity_id
        for item in context.entities
        if item.primitive.value in free_body
    )


def _carriers_via_records(
    context: LawContext,
    subject_id: str,
    *,
    geometry_kinds: frozenset[GeometryRelationKind],
    interaction_kinds: frozenset[InteractionKind] = frozenset(),
) -> frozenset[str]:
    """Free-body entities a typed record names alongside this subject."""

    bodies = _free_body_entity_ids(context)
    carriers: set[str] = set()
    for relation in context.geometry:
        if relation.kind not in geometry_kinds:
            continue
        participants = set(relation.participant_ids)
        if subject_id in participants:
            carriers |= participants & bodies
    for interaction in context.interactions:
        if interaction.kind not in interaction_kinds:
            continue
        participants = set(interaction.participant_ids)
        if subject_id in participants:
            carriers |= participants & bodies
    return frozenset(carriers)


def candidate_carriers(
    context: LawContext, subject_id: str, primitive: EntityPrimitive
) -> frozenset[str]:
    """The free-body entities typed structure proves could carry this readout.

    Membership is read from records that name the subject.  Sharing an interval
    is not membership and is not read here.
    """

    if primitive is EntityPrimitive.point:
        return _carriers_via_records(
            context, subject_id, geometry_kinds=_POINT_OWNERSHIP_GEOMETRY
        )
    if primitive is EntityPrimitive.joint:
        return _carriers_via_records(
            context,
            subject_id,
            geometry_kinds=_JOINT_OWNERSHIP_GEOMETRY,
            interaction_kinds=_JOINT_OWNERSHIP_INTERACTIONS,
        )
    if primitive is EntityPrimitive.system:
        return _carriers_via_records(
            context, subject_id, geometry_kinds=_AGGREGATE_OWNERSHIP_GEOMETRY
        )
    return frozenset()


def _interval_co_subject_bodies(
    context: LawContext, subject_id: str
) -> frozenset[str]:
    """Free bodies that merely share an interval with the subject.

    This is *not* a membership proof and is never used to form a binding.  It is
    measured so that "no membership relation exists" is a recorded observation
    rather than an inference from a zero.
    """

    bodies = _free_body_entity_ids(context)
    co_subjects: set[str] = set()
    for interval in context.motion_intervals:
        subjects = set(interval.subject_ids)
        if subject_id in subjects:
            co_subjects |= subjects & bodies
    return frozenset(co_subjects)


def _bind_readout(
    context: LawContext, quantity: BoundQuantity, carrier_id: str
) -> LawContext:
    """The counterfactual: the queried readout, carried by the carrier.

    Exactly one field of exactly one quantity changes.  No entity primitive is
    rewritten, no entity is added to the free-body set, no record is created,
    and the source Draft this context came from is not touched at all.
    """

    rebound = tuple(
        replace(item, subject_id=carrier_id)
        if item.quantity_id == quantity.quantity_id
        else item
        for item in context.quantities
    )
    return replace(context, quantities=rebound)


def co_subject_route_would_unlock(
    context: LawContext, query_quantity_id: str
) -> tuple[bool, bool]:
    """What treating interval co-scoping as membership would buy, if anything.

    Returns `(unique_carrier, unlocks)`.  This route is **not** used to form any
    binding that any other count depends on; it exists so the contract question
    "should an interval's subject list count as membership?" can be answered
    from evidence.  If it unlocks nothing, the question does not have to be
    settled at all.
    """

    quantity = _query_quantity(context, query_quantity_id)
    if quantity is None:
        return False, False
    carriers = _interval_co_subject_bodies(context, quantity.subject_id)
    if len(carriers) != 1:
        return False, False
    bound = _bind_readout(context, quantity, next(iter(carriers)))
    if _writes_about(bound, query_quantity_id):
        return True, True
    with_profile = context_with_counterfactual_frame(bound)
    return True, _writes_about(with_profile, query_quantity_id)


def _any_law_applies(context: LawContext) -> bool:
    return any(
        law_is_semantically_applicable(context, rule) for rule in CORE_LAW_CATALOG
    )


def aggregate_common_magnitude_carriers(
    context: LawContext, subject_id: str, quantity: BoundQuantity
) -> tuple[frozenset[str], str | None]:
    """The member set whose readouts an aggregate query is the common magnitude of.

    An aggregate readout is not "pick a member".  It is only well posed when
    typed structure proves every member shares one magnitude, and here that
    proof is exactly the one an inextensible rope over a pulley makes:

    * a rope topology names the members together;
    * an approved `inextensible_rope` authority holds over the query's interval;
    * every named member is a free body with its own readout of the queried role
      in that interval; and
    * the question asks for a **magnitude**.

    The magnitude requirement is not a formality.  Two bodies on opposite sides
    of a pulley accelerate in opposite directions, so a signed system readout
    does not exist to be bound: fabricating one would hand the solver a sign no
    member has.  A signed query therefore fails closed.

    Returns `(members, refusal)` — an empty set with a bounded refusal code when
    the proof does not hold.
    """

    if quantity.component is not QuantityComponent.magnitude:
        return frozenset(), "signed_component_has_no_common_readout"

    bodies = _free_body_entity_ids(context)
    members: set[str] = set()
    for relation in context.geometry:
        if relation.kind not in _ROPE_TOPOLOGY_GEOMETRY:
            continue
        named = set(relation.participant_ids) & bodies
        if len(named) >= 2:
            members |= named
    if len(members) < 2:
        # One member is not an aggregate, and none is not a member set.
        return frozenset(), "no_multi_member_topology"

    inextensible = any(
        assumption.kind == _INEXTENSIBLE_ROPE_AUTHORITY
        and assumption.disposition is AssumptionDisposition.approved
        and assumption.assumption_id in context.approved_assumption_ids
        and assumption.interval_id in (None, quantity.interval_id)
        for assumption in context.assumptions
    )
    if not inextensible:
        # Unconstrained members share nothing; their magnitudes are independent.
        return frozenset(), "members_not_magnitude_constrained"

    # Every member must actually carry the readout being asked for, in scope.
    carried = {
        member
        for member in members
        if any(
            item.subject_id == member
            and item.role is quantity.role
            and item.interval_id == quantity.interval_id
            and item.event_id == quantity.event_id
            for item in context.quantities
        )
    }
    if carried != members:
        return frozenset(), "member_readout_missing"
    return frozenset(members), None


def _bind_point_scoped_readout(
    context: LawContext,
    quantity: BoundQuantity,
    owner_id: str,
    *,
    role: PointRole = PointRole.material,
) -> LawContext:
    """The readout as the owner body's, *at the point the source named*.

    The point entity survives untouched and keeps its geometry; what changes is
    that the quantity now says whose point it is.  Rewriting the point into a
    body would be a different counterfactual measuring a different claim.
    """

    rebound = tuple(
        replace(item, subject_id=owner_id, point_id=quantity.subject_id)
        if item.quantity_id == quantity.quantity_id
        else item
        for item in context.quantities
    )
    points = context.points
    if not any(item.point_id == quantity.subject_id for item in points):
        points = (
            *points,
            IRPoint(
                point_id=quantity.subject_id,
                role=role,
                owner_entity_id=owner_id,
                frame_id=quantity.frame_id,
                evidence_refs=(_CF_EVIDENCE_ID,),
            ),
        )
    return replace(context, quantities=rebound, points=points)


def _with_member_readouts(
    context: LawContext, quantity: BoundQuantity
) -> LawContext:
    """Give every free body a readout of the queried role, as an unknown.

    An aggregate readout cannot be proven when its members carry nothing to be
    the common magnitude *of*, and on this corpus that is the usual refusal.
    Whether a profile that supplies those readouts would then close the
    aggregate is a separate question from whether the source states them, so it
    gets its own rung rather than being assumed either way.

    Values stay unknown; only existence is supplied.
    """

    quantities = list(context.quantities)
    existing = {
        (item.subject_id, item.role, item.interval_id, item.event_id)
        for item in context.quantities
    }
    for index, body in enumerate(sorted(_free_body_entity_ids(context))):
        key = (body, quantity.role, quantity.interval_id, quantity.event_id)
        if key in existing:
            continue
        symbol_id = f"{_CF_PREFIX}_member_sym_{index}"
        quantities.append(
            BoundQuantity(
                quantity_id=f"{_CF_PREFIX}_member_{index}",
                symbol_id=symbol_id,
                role=quantity.role,
                subject_id=body,
                point_id=None,
                frame_id=quantity.frame_id,
                interval_id=quantity.interval_id,
                event_id=quantity.event_id,
                component=QuantityComponent.y,
                shape=quantity.shape,
                dimension=quantity.dimension,
                expression=SymbolRef(
                    symbol_id=symbol_id, dimension=quantity.dimension
                ),
                evidence_ids=(_CF_EVIDENCE_ID,),
                direction_sign=1 if index % 2 == 0 else -1,
            )
        )
    return replace(context, quantities=tuple(quantities))


def _context_with_minimal_complete_profile(context: LawContext) -> LawContext:
    """Frame, axes, component topology — **and** the interaction a law needs.

    This is the rung the frame rung is not.  75 of 97 public contexts carry no
    interaction at all, so a free-body law has no force to sum however complete
    the kinematics are; adding a frame alone can never reach one.  Here every
    free body also gains a gravity interaction owning a force on it, which is
    the smallest structure that makes `_newton_emissions` reachable.

    Counterfactual only.  It is discarded with the diagnosis and never becomes
    a Draft.
    """

    framed = context_with_counterfactual_frame(context)
    bodies = sorted(_free_body_entity_ids(framed))
    if not bodies:
        return framed
    interval_id = framed.motion_intervals[0].interval_id if framed.motion_intervals else None
    field_id = _CF_FIELD_ENTITY_ID
    entities = framed.entities
    if not any(item.entity_id == field_id for item in entities):
        entities = (
            *entities,
            IREntity(
                entity_id=field_id,
                primitive=EntityPrimitive.field,
                label=field_id,
                evidence_refs=(_CF_EVIDENCE_ID,),
            ),
        )
    frame_id = framed.reference_frames[-1].frame_id if framed.reference_frames else None

    quantities = list(framed.quantities)
    interactions = list(framed.interactions)
    for index, body in enumerate(bodies):
        force_id = f"{_CF_PREFIX}_force_{index}"
        symbol_id = f"{_CF_PREFIX}_forcesym_{index}"
        quantities.append(
            BoundQuantity(
                quantity_id=force_id,
                symbol_id=symbol_id,
                role=QuantityRole.force,
                subject_id=body,
                point_id=None,
                frame_id=frame_id,
                interval_id=interval_id,
                event_id=None,
                component=QuantityComponent.y,
                shape=QuantityShape.scalar,
                dimension=_FORCE_DIMENSION,
                expression=SymbolRef(symbol_id=symbol_id, dimension=_FORCE_DIMENSION),
                evidence_ids=(_CF_EVIDENCE_ID,),
            )
        )
        interactions.append(
            IRInteraction(
                interaction_id=f"{_CF_PREFIX}_gravity_{index}",
                kind=InteractionKind.gravity,
                participant_ids=(body, field_id),
                frame_id=frame_id,
                interval_id=interval_id,
                quantity_ids=(force_id,),
                evidence_refs=(_CF_EVIDENCE_ID,),
            )
        )
    return replace(
        framed,
        entities=entities,
        quantities=tuple(quantities),
        interactions=tuple(interactions),
    )


def _ladder(
    context: LawContext,
    bound: LawContext,
    query_quantity_id: str,
    scoped_outcome: OwnershipCausalOutcome,
    carriers: int,
) -> tuple[OwnershipCausalOutcome, int]:
    """Binding, then binding plus a frame, then binding plus a whole profile.

    Each rung is reported under its own name, so a result reached by the third
    is never quoted as a result of the first.
    """

    if _writes_about(bound, query_quantity_id):
        return scoped_outcome, carriers
    if _writes_about(context_with_counterfactual_frame(bound), query_quantity_id):
        return OwnershipCausalOutcome.binding_plus_frame_unlocks, carriers
    if _writes_about(
        _context_with_minimal_complete_profile(bound), query_quantity_id
    ):
        return OwnershipCausalOutcome.binding_plus_complete_profile_unlocks, carriers
    return OwnershipCausalOutcome.binding_does_not_close, carriers


def classify_ownership_blocker(
    context: LawContext,
    query_quantity_id: str,
    primitive: EntityPrimitive,
) -> tuple[OwnershipCausalOutcome, int]:
    """Classify one context, and report how many carriers were provable.

    The order of the checks is the order of the claims they license.  A context
    no law is about is reported as such before any binding is tried, because a
    binding that "does not close" such a context would read as evidence about
    ownership when it is evidence about applicability.

    Each primitive gets the binding its readout actually needs: an aggregate is
    bound to a proven member set, a point keeps its identity and gains an owner
    and a `point_id`, and a joint is bound only for the readout the query names.
    """

    quantity = _query_quantity(context, query_quantity_id)
    if quantity is None:
        return OwnershipCausalOutcome.binding_not_formable, 0
    if not _any_law_applies(context):
        return OwnershipCausalOutcome.law_not_semantically_applicable, 0
    if _writes_about(context, query_quantity_id):
        # Already written about without any binding; ownership is not the wall.
        return OwnershipCausalOutcome.binding_does_not_close, 0

    if primitive is EntityPrimitive.system:
        members, refusal = aggregate_common_magnitude_carriers(
            context, quantity.subject_id, quantity
        )
        if not members and refusal == "member_readout_missing":
            # The members are there and the rope constrains them; what is absent
            # is a readout for the aggregate to be the common magnitude *of*.
            # A profile supplies those as unknowns, so ask whether the aggregate
            # closes once it has — a different question from whether the source
            # states them.
            supplied = _with_member_readouts(context, quantity)
            members, refusal = aggregate_common_magnitude_carriers(
                supplied, quantity.subject_id, quantity
            )
            if members:
                bound = _bind_readout(supplied, quantity, sorted(members)[0])
                if _writes_about(
                    _context_with_minimal_complete_profile(bound), query_quantity_id
                ):
                    return (
                        OwnershipCausalOutcome.binding_plus_complete_profile_unlocks,
                        len(members),
                    )
                return OwnershipCausalOutcome.binding_does_not_close, len(members)
        if not members:
            single = candidate_carriers(context, quantity.subject_id, primitive)
            if not single:
                return OwnershipCausalOutcome.binding_not_formable, 0
            if len(single) > 1:
                return OwnershipCausalOutcome.binding_ambiguous, len(single)
            bound = _bind_readout(context, quantity, next(iter(single)))
            return _ladder(
                context,
                bound,
                query_quantity_id,
                OwnershipCausalOutcome.single_carrier_binding_alone_unlocks,
                1,
            )
        # Proven equal magnitudes: the readout is every member's, so binding it
        # to the stable-first is equivalent *because of the proof*, not instead
        # of it.  Without the proof this path is never taken.
        bound = _bind_readout(context, quantity, sorted(members)[0])
        return _ladder(
            context,
            bound,
            query_quantity_id,
            OwnershipCausalOutcome.aggregate_multi_carrier_binding_unlocks,
            len(members),
        )

    carriers = candidate_carriers(context, quantity.subject_id, primitive)
    if not carriers:
        return OwnershipCausalOutcome.binding_not_formable, 0
    if primitive is EntityPrimitive.joint:
        readout = joint_readout_kind(context, quantity)
        if readout is None:
            return OwnershipCausalOutcome.binding_ambiguous, len(carriers)
        if readout is ReadoutBindingKind.joint_reaction_readout and len(carriers) > 1:
            # A reaction has a side.  Two connected bodies and no stated side is
            # a real ambiguity, unlike a joint-point kinematic quantity which is
            # the same for both.
            return OwnershipCausalOutcome.binding_ambiguous, len(carriers)
        bound = _bind_point_scoped_readout(
            context, quantity, sorted(carriers)[0], role=PointRole.joint
        )
        return _ladder(
            context,
            bound,
            query_quantity_id,
            OwnershipCausalOutcome.joint_scoped_binding_unlocks,
            len(carriers),
        )

    if len(carriers) > 1:
        # More than one body could own the point and typed structure does not
        # choose between them.  Choosing one here would invent the answer.
        return OwnershipCausalOutcome.binding_ambiguous, len(carriers)
    bound = _bind_point_scoped_readout(context, quantity, next(iter(carriers)))
    return _ladder(
        context,
        bound,
        query_quantity_id,
        OwnershipCausalOutcome.point_scoped_binding_unlocks,
        1,
    )

    return OwnershipCausalOutcome.binding_does_not_close, 1


def diagnose_query_readout_ownership(
    contexts: Iterable[tuple[LawContext, str]],
) -> OwnershipCausalDiagnosis:
    """Classify every context whose queried readout is not directly owned.

    Each input is one law context and the quantity ID its question asks for.
    A context whose query subject is already a free body is counted and skipped:
    it has no ownership question to answer.
    """

    free_body = frozenset(free_body_primitive_names())
    outcomes: Counter[str] = Counter()
    by_primitive: Counter[tuple[str, str]] = Counter()
    carrier_counts: Counter[str] = Counter()
    total = 0
    examined = 0
    membership = 0
    co_subject_only = 0
    co_subject_unique = 0
    co_subject_unlocks = 0
    typed_points = 0
    aggregate_refusals: Counter[str] = Counter()

    for context, query_quantity_id in contexts:
        total += 1
        quantity = _query_quantity(context, query_quantity_id)
        if quantity is None:
            continue
        primitive_by_entity = {
            item.entity_id: item.primitive for item in context.entities
        }
        primitive = primitive_by_entity.get(quantity.subject_id)
        if primitive is None or primitive.value in free_body:
            continue
        examined += 1
        if context.points:
            typed_points += 1
        if primitive is EntityPrimitive.system:
            _members, refusal = aggregate_common_magnitude_carriers(
                context, quantity.subject_id, quantity
            )
            if refusal is not None:
                aggregate_refusals[refusal] += 1
            if candidate_carriers(context, quantity.subject_id, primitive):
                membership += 1
            elif _interval_co_subject_bodies(context, quantity.subject_id):
                co_subject_only += 1
                unique, unlocks = co_subject_route_would_unlock(
                    context, query_quantity_id
                )
                co_subject_unique += int(unique)
                co_subject_unlocks += int(unlocks)

        outcome, carriers = classify_ownership_blocker(
            context, query_quantity_id, primitive
        )
        outcomes[outcome.value] += 1
        by_primitive[(primitive.value, outcome.value)] += 1
        carrier_counts[str(carriers)] += 1

    return OwnershipCausalDiagnosis(
        context_count=total,
        examined_contexts=examined,
        outcome_counts=tuple(sorted(outcomes.items())),
        outcome_by_primitive=tuple(
            (primitive, outcome, count)
            for (primitive, outcome), count in sorted(by_primitive.items())
        ),
        candidate_carrier_counts=tuple(sorted(carrier_counts.items())),
        aggregate_contexts_with_membership_relation=membership,
        aggregate_contexts_with_interval_co_subjects_only=co_subject_only,
        aggregate_co_subject_route_unlocks=co_subject_unlocks,
        aggregate_co_subject_route_unique_carrier=co_subject_unique,
        contexts_with_typed_point_record=typed_points,
        aggregate_refusal_counts=tuple(sorted(aggregate_refusals.items())),
        free_body_primitives=tuple(sorted(free_body)),
    )


def diagnosis_as_dict(diagnosis: OwnershipCausalDiagnosis) -> dict[str, Any]:
    """The diagnosis as plain JSON for the redacted aggregate artifact."""

    return {
        "version": diagnosis.version,
        "context_count": diagnosis.context_count,
        "examined_contexts": diagnosis.examined_contexts,
        "causally_blocked_on_ownership": diagnosis.causally_blocked_on_ownership,
        "aggregate_contexts_with_membership_relation": (
            diagnosis.aggregate_contexts_with_membership_relation
        ),
        "aggregate_contexts_with_interval_co_subjects_only": (
            diagnosis.aggregate_contexts_with_interval_co_subjects_only
        ),
        "aggregate_co_subject_route_unlocks": (
            diagnosis.aggregate_co_subject_route_unlocks
        ),
        "aggregate_co_subject_route_unique_carrier": (
            diagnosis.aggregate_co_subject_route_unique_carrier
        ),
        "contexts_with_typed_point_record": diagnosis.contexts_with_typed_point_record,
        "aggregate_refusal_counts": [
            {"refusal": key, "count": value}
            for key, value in diagnosis.aggregate_refusal_counts
        ],
        "free_body_primitives": list(diagnosis.free_body_primitives),
        "outcome_counts": [
            {"outcome": key, "count": value} for key, value in diagnosis.outcome_counts
        ],
        "outcome_by_primitive": [
            {"primitive": primitive, "outcome": outcome, "count": count}
            for primitive, outcome, count in diagnosis.outcome_by_primitive
        ],
        "candidate_carrier_counts": [
            {"carriers": key, "count": value}
            for key, value in diagnosis.candidate_carrier_counts
        ],
    }


__all__ = [
    "QUERY_READOUT_OWNERSHIP_DIAGNOSIS_VERSION",
    "OwnershipCausalDiagnosis",
    "OwnershipCausalOutcome",
    "ReadoutBindingKind",
    "aggregate_common_magnitude_carriers",
    "candidate_carriers",
    "classify_ownership_blocker",
    "co_subject_route_would_unlock",
    "diagnose_query_readout_ownership",
    "diagnosis_as_dict",
    "joint_readout_kind",
]
