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
    EntityPrimitive,
    GeometryRelationKind,
    InteractionKind,
)
from engine.mechanics.laws.base import BoundQuantity, LawContext
from engine.mechanics.laws.core import (
    CORE_LAW_CATALOG,
    apply_core_laws,
    free_body_primitive_names,
)

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

    `binding_not_formable` is the honest outcome for a context where no carrier
    is provable from typed structure at all.  It is deliberately *not* folded
    into `binding_does_not_close`: those are contexts where a binding was formed
    and did not help, which is a different fact about a different capability.
    Merging them would reproduce exactly the overclaim this module exists to
    prevent.
    """

    aggregate_binding_alone_unlocks = "aggregate_binding_alone_unlocks"
    point_binding_alone_unlocks = "point_binding_alone_unlocks"
    joint_binding_alone_unlocks = "joint_binding_alone_unlocks"
    binding_plus_profile_required = "binding_plus_profile_required"
    binding_does_not_close = "binding_does_not_close"
    binding_ambiguous = "binding_ambiguous"
    binding_not_formable = "binding_not_formable"
    law_not_semantically_applicable = "law_not_semantically_applicable"


_UNLOCK_OUTCOME: dict[EntityPrimitive, OwnershipCausalOutcome] = {
    EntityPrimitive.system: OwnershipCausalOutcome.aggregate_binding_alone_unlocks,
    EntityPrimitive.point: OwnershipCausalOutcome.point_binding_alone_unlocks,
    EntityPrimitive.joint: OwnershipCausalOutcome.joint_binding_alone_unlocks,
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
    free_body_primitives: tuple[str, ...] = ()

    @property
    def causally_blocked_on_ownership(self) -> int:
        """Contexts where a formable binding is what actually moves the engine."""

        unlocking = {
            OwnershipCausalOutcome.aggregate_binding_alone_unlocks.value,
            OwnershipCausalOutcome.point_binding_alone_unlocks.value,
            OwnershipCausalOutcome.joint_binding_alone_unlocks.value,
            OwnershipCausalOutcome.binding_plus_profile_required.value,
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
    """

    quantity = _query_quantity(context, query_quantity_id)
    if quantity is None:
        return OwnershipCausalOutcome.binding_not_formable, 0
    if not _any_law_applies(context):
        return OwnershipCausalOutcome.law_not_semantically_applicable, 0

    carriers = candidate_carriers(context, quantity.subject_id, primitive)
    if not carriers:
        return OwnershipCausalOutcome.binding_not_formable, 0
    if len(carriers) > 1:
        # More than one entity could carry the readout and typed structure does
        # not choose between them.  Choosing one here would invent the answer.
        return OwnershipCausalOutcome.binding_ambiguous, len(carriers)

    carrier_id = next(iter(carriers))
    if _writes_about(context, query_quantity_id):
        # Already written about without any binding; ownership is not the wall.
        return OwnershipCausalOutcome.binding_does_not_close, 1

    bound = _bind_readout(context, quantity, carrier_id)
    if _writes_about(bound, query_quantity_id):
        return _UNLOCK_OUTCOME[primitive], 1

    with_profile = context_with_counterfactual_frame(bound)
    if _writes_about(with_profile, query_quantity_id):
        return OwnershipCausalOutcome.binding_plus_profile_required, 1

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
    "candidate_carriers",
    "classify_ownership_blocker",
    "co_subject_route_would_unlock",
    "diagnose_query_readout_ownership",
    "diagnosis_as_dict",
]
