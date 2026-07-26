"""The ownership diagnostic must detect an unlock when there is one.

A diagnostic that reports zero everywhere is worthless unless it is shown to
report non-zero when the thing it measures is really present.  The positive
controls here are the whole point of the module: each is a context that is
complete in every respect *except* that its queried readout sits on an entity no
free-body law writes about, and each must classify as `*_binding_alone_unlocks`.
Only against those does a measured zero mean "ownership is not the wall" rather
than "the instrument is broken".

`state_at_rest` is the law used throughout, because its emission depends on
exactly one thing this module is about: whether the velocity quantity's subject
is the same entity the state condition names.  Nothing else in the context has
to change for the control to isolate ownership.

Every fixture is independently authored.  None is derived from a corpus case,
and none reads a case ID, family, split, expected terminal, or expected answer.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from engine.mechanics.contracts import (
    Entity,
    EntityPrimitive,
    GeometryRelation,
    GeometryRelationKind,
    Interaction,
    InteractionKind,
    IRGeometryRelation,
    IRMotionInterval,
    IRStateCondition,
    QuantityComponent,
    QuantityRole,
    QuantityShape,
    StateCondition,
    StateKind,
    StateValue,
)
from engine.mechanics.laws.base import BoundQuantity, LawContext
from engine.mechanics.laws.core import apply_core_laws, free_body_primitive_names
from engine.mechanics.math_ast import DimensionVector, SymbolDefinition, SymbolRef

from evaluation.phase56_stage7.query_readout_ownership import (
    OwnershipCausalOutcome,
    ReadoutBindingKind,
    candidate_carriers,
    classify_ownership_blocker,
    diagnose_query_readout_ownership,
    diagnosis_as_dict,
)

VELOCITY = DimensionVector(length=1, time=-1)
QUERY_QUANTITY_ID = "qty_v"


def _quantity(subject_id: str) -> BoundQuantity:
    return BoundQuantity(
        quantity_id=QUERY_QUANTITY_ID,
        symbol_id="sym_v",
        role=QuantityRole.velocity,
        subject_id=subject_id,
        point_id=None,
        frame_id=None,
        interval_id="seg",
        event_id=None,
        component=QuantityComponent.magnitude,
        shape=QuantityShape.scalar,
        dimension=VELOCITY,
        expression=SymbolRef(symbol_id="sym_v", dimension=VELOCITY),
        evidence_ids=("ev_v",),
    )


def _entity(entity_id: str, primitive: EntityPrimitive) -> Entity:
    return Entity(
        entity_id=entity_id,
        primitive=primitive,
        label=entity_id,
        evidence_refs=["ev_entity"],
    )


def _context(
    *,
    readout_owner: str,
    owner_primitive: EntityPrimitive | None,
    geometry: tuple[IRGeometryRelation, ...] = (),
    interactions: tuple[Interaction, ...] = (),
    rest_state: bool = True,
    extra_entities: tuple[Entity, ...] = (),
) -> LawContext:
    """One body at rest, and a velocity readout owned by `readout_owner`.

    With `readout_owner` set to the body, `state_at_rest` writes about the
    velocity.  Move the readout onto anything else and it stops, which is the
    isolated ownership effect every control here turns on.
    """

    entities: list[Entity] = [_entity("body", EntityPrimitive.particle)]
    if owner_primitive is not None and readout_owner != "body":
        entities.append(_entity(readout_owner, owner_primitive))
    entities.extend(extra_entities)

    states: tuple[IRStateCondition, ...] = ()
    if rest_state:
        states = (
            IRStateCondition(
                **StateCondition(
                    state_condition_id="st_rest",
                    kind=StateKind.motion,
                    state=StateValue.at_rest,
                    subject_id="body",
                    interval_id="seg",
                    quantity_ids=[],
                    evidence_refs=["ev_rest"],
                ).model_dump()
            ),
        )

    return LawContext(
        quantities=(_quantity(readout_owner),),
        entities=tuple(entities),
        points=(),
        reference_frames=(),
        motion_intervals=(
            IRMotionInterval(
                interval_id="seg",
                order=1,
                subject_ids=[item.entity_id for item in entities],
                evidence_refs=["ev_seg"],
            ),
        ),
        events=(),
        geometry=geometry,
        interactions=interactions,
        state_conditions=states,
        assumptions=(),
        approved_assumption_ids=frozenset(),
        symbols=(
            SymbolDefinition(
                symbol_id="sym_v", quantity_id=QUERY_QUANTITY_ID, dimension=VELOCITY
            ),
        ),
        hinted_principles=(),
    )


def _geometry(
    relation_id: str,
    kind: GeometryRelationKind,
    participants: list[str],
) -> IRGeometryRelation:
    return IRGeometryRelation(
        **GeometryRelation(
            relation_id=relation_id, kind=kind, participant_ids=participants
        ).model_dump()
    )


def _writes_about_query(context: LawContext) -> bool:
    return any(
        QUERY_QUANTITY_ID in emission.source_quantity_ids
        for emission in apply_core_laws(context)
    )


# --------------------------------------------------------------------------
# The fixture itself behaves as the controls assume
# --------------------------------------------------------------------------


def test_the_body_owned_readout_is_written_about():
    """The baseline the controls are built on: ownership on the body works."""

    context = _context(readout_owner="body", owner_primitive=None)
    assert _writes_about_query(context)


def test_moving_the_readout_off_the_body_stops_the_law():
    """And moving it off stops it — so the control isolates ownership alone."""

    context = _context(readout_owner="pt", owner_primitive=EntityPrimitive.point)
    assert not _writes_about_query(context)


# --------------------------------------------------------------------------
# Positive controls: the instrument detects an unlock when there is one
# --------------------------------------------------------------------------


def test_a_point_readout_with_a_unique_owner_unlocks_on_binding_alone():
    context = _context(
        readout_owner="pt",
        owner_primitive=EntityPrimitive.point,
        geometry=(_geometry("g1", GeometryRelationKind.lies_on, ["pt", "body"]),),
    )
    outcome, carriers = classify_ownership_blocker(
        context, QUERY_QUANTITY_ID, EntityPrimitive.point
    )
    assert outcome is OwnershipCausalOutcome.point_binding_alone_unlocks
    assert carriers == 1


def test_a_joint_readout_with_a_unique_connected_body_unlocks_on_binding_alone():
    context = _context(
        readout_owner="jt",
        owner_primitive=EntityPrimitive.joint,
        geometry=(_geometry("g1", GeometryRelationKind.attached, ["jt", "body"]),),
    )
    outcome, carriers = classify_ownership_blocker(
        context, QUERY_QUANTITY_ID, EntityPrimitive.joint
    )
    assert outcome is OwnershipCausalOutcome.joint_binding_alone_unlocks
    assert carriers == 1


def test_a_system_readout_with_a_membership_relation_unlocks_on_binding_alone():
    context = _context(
        readout_owner="sys",
        owner_primitive=EntityPrimitive.system,
        geometry=(
            _geometry("g1", GeometryRelationKind.topology_connects, ["sys", "body"]),
        ),
    )
    outcome, carriers = classify_ownership_blocker(
        context, QUERY_QUANTITY_ID, EntityPrimitive.system
    )
    assert outcome is OwnershipCausalOutcome.aggregate_binding_alone_unlocks
    assert carriers == 1


def test_a_joint_reaction_interaction_also_names_a_carrier():
    context = _context(
        readout_owner="jt",
        owner_primitive=EntityPrimitive.joint,
        interactions=(
            Interaction(
                interaction_id="i1",
                kind=InteractionKind.joint_reaction,
                participant_ids=["jt", "body"],
            ),
        ),
    )
    outcome, _ = classify_ownership_blocker(
        context, QUERY_QUANTITY_ID, EntityPrimitive.joint
    )
    assert outcome is OwnershipCausalOutcome.joint_binding_alone_unlocks


# --------------------------------------------------------------------------
# The classifications that are not an unlock
# --------------------------------------------------------------------------


def test_no_typed_record_naming_the_subject_is_not_formable():
    """Nothing states whose readout this is, so no binding can be formed.

    This is deliberately not `binding_does_not_close`: no binding was formed, so
    the context says nothing about whether a binding would have helped.
    """

    context = _context(readout_owner="sys", owner_primitive=EntityPrimitive.system)
    outcome, carriers = classify_ownership_blocker(
        context, QUERY_QUANTITY_ID, EntityPrimitive.system
    )
    assert outcome is OwnershipCausalOutcome.binding_not_formable
    assert carriers == 0


def test_sharing_an_interval_is_not_membership():
    """Every fixture's interval lists all its subjects, and that proves nothing.

    Co-scoping says the records describe the same stretch of motion.  It does
    not say the aggregate is made of them, and reading it as membership would
    invent the structure this module exists to avoid inventing.
    """

    context = _context(readout_owner="sys", owner_primitive=EntityPrimitive.system)
    assert "body" in context.motion_intervals[0].subject_ids
    assert candidate_carriers(context, "sys", EntityPrimitive.system) == frozenset()


def test_the_co_subject_route_is_measured_but_never_forms_a_binding():
    """A contract question answered with evidence instead of argument.

    Treating an interval's subject list as membership has not been decided, and
    this measurement is what would decide it.  With one co-subject body the
    route is unique and would unlock; with two it is not unique and could not
    form a binding however the contract question were settled.
    """

    from evaluation.phase56_stage7.query_readout_ownership import (
        co_subject_route_would_unlock,
    )

    single = _context(readout_owner="sys", owner_primitive=EntityPrimitive.system)
    unique, unlocks = co_subject_route_would_unlock(single, QUERY_QUANTITY_ID)
    assert (unique, unlocks) == (True, True)

    paired = _context(
        readout_owner="sys",
        owner_primitive=EntityPrimitive.system,
        extra_entities=(_entity("body2", EntityPrimitive.rigid_body),),
    )
    assert co_subject_route_would_unlock(paired, QUERY_QUANTITY_ID) == (False, False)

    # And it stays out of the headline count either way.
    diagnosis = diagnose_query_readout_ownership([(single, QUERY_QUANTITY_ID)])
    assert diagnosis.causally_blocked_on_ownership == 0
    assert diagnosis.aggregate_co_subject_route_unlocks == 1


def test_two_possible_carriers_are_ambiguous_not_chosen():
    context = _context(
        readout_owner="sys",
        owner_primitive=EntityPrimitive.system,
        extra_entities=(_entity("body2", EntityPrimitive.rigid_body),),
        geometry=(
            _geometry(
                "g1",
                GeometryRelationKind.topology_connects,
                ["sys", "body", "body2"],
            ),
        ),
    )
    outcome, carriers = classify_ownership_blocker(
        context, QUERY_QUANTITY_ID, EntityPrimitive.system
    )
    assert outcome is OwnershipCausalOutcome.binding_ambiguous
    assert carriers == 2


def test_a_formable_binding_that_still_emits_nothing_does_not_close():
    """The carrier is unique and the binding is formed — and no law follows.

    Without the rest state there is nothing for `state_at_rest` to write, so
    binding the readout to the body changes nothing.  That is the outcome that
    says ownership is *not* what blocks this context.
    """

    context = _context(
        readout_owner="pt",
        owner_primitive=EntityPrimitive.point,
        geometry=(_geometry("g1", GeometryRelationKind.lies_on, ["pt", "body"]),),
        rest_state=False,
    )
    outcome, carriers = classify_ownership_blocker(
        context, QUERY_QUANTITY_ID, EntityPrimitive.point
    )
    assert outcome is OwnershipCausalOutcome.binding_does_not_close
    assert carriers == 1


def test_geometry_that_locates_a_point_does_not_own_it():
    """A `distance` naming the point says where it is, not whose it is."""

    context = _context(
        readout_owner="pt",
        owner_primitive=EntityPrimitive.point,
        geometry=(_geometry("g1", GeometryRelationKind.distance, ["pt", "body"]),),
    )
    assert candidate_carriers(context, "pt", EntityPrimitive.point) == frozenset()


# --------------------------------------------------------------------------
# The diagnosis over many contexts
# --------------------------------------------------------------------------


def test_a_free_body_query_subject_is_counted_but_not_examined():
    diagnosis = diagnose_query_readout_ownership(
        [(_context(readout_owner="body", owner_primitive=None), QUERY_QUANTITY_ID)]
    )
    assert diagnosis.context_count == 1
    assert diagnosis.examined_contexts == 0
    assert diagnosis.outcome_counts == ()


def test_outcomes_accumulate_by_primitive():
    unlocking = _context(
        readout_owner="pt",
        owner_primitive=EntityPrimitive.point,
        geometry=(_geometry("g1", GeometryRelationKind.lies_on, ["pt", "body"]),),
    )
    unformable = _context(
        readout_owner="sys", owner_primitive=EntityPrimitive.system
    )
    diagnosis = diagnose_query_readout_ownership(
        [
            (unlocking, QUERY_QUANTITY_ID),
            (unlocking, QUERY_QUANTITY_ID),
            (unformable, QUERY_QUANTITY_ID),
        ]
    )
    assert diagnosis.examined_contexts == 3
    assert dict(diagnosis.outcome_counts) == {
        OwnershipCausalOutcome.point_binding_alone_unlocks.value: 2,
        OwnershipCausalOutcome.binding_not_formable.value: 1,
    }
    assert diagnosis.causally_blocked_on_ownership == 2
    assert diagnosis.aggregate_contexts_with_interval_co_subjects_only == 1
    assert diagnosis.aggregate_contexts_with_membership_relation == 0


def test_an_unformable_binding_is_not_counted_as_causally_blocked():
    """The distinction the whole module exists for.

    A context where no carrier is provable is not evidence that an ownership
    capability would unlock it, and must never be added to that total.
    """

    diagnosis = diagnose_query_readout_ownership(
        [(_context(readout_owner="sys", owner_primitive=EntityPrimitive.system), QUERY_QUANTITY_ID)]
    )
    assert diagnosis.outcome_counts == (
        (OwnershipCausalOutcome.binding_not_formable.value, 1),
    )
    assert diagnosis.causally_blocked_on_ownership == 0


# --------------------------------------------------------------------------
# The counterfactual stays a counterfactual
# --------------------------------------------------------------------------


def test_the_diagnosis_does_not_mutate_the_contexts_it_reads():
    context = _context(
        readout_owner="pt",
        owner_primitive=EntityPrimitive.point,
        geometry=(_geometry("g1", GeometryRelationKind.lies_on, ["pt", "body"]),),
    )
    before = context.quantities[0].subject_id
    before_entities = tuple(item.entity_id for item in context.entities)
    diagnose_query_readout_ownership([(context, QUERY_QUANTITY_ID)])
    assert context.quantities[0].subject_id == before
    assert tuple(item.entity_id for item in context.entities) == before_entities


def test_no_entity_primitive_is_rewritten_and_the_free_body_set_is_untouched():
    """The two things the diagnosis is forbidden to do, asserted directly."""

    context = _context(
        readout_owner="pt",
        owner_primitive=EntityPrimitive.point,
        geometry=(_geometry("g1", GeometryRelationKind.lies_on, ["pt", "body"]),),
    )
    before = tuple(item.primitive for item in context.entities)
    free_body_before = free_body_primitive_names()
    classify_ownership_blocker(context, QUERY_QUANTITY_ID, EntityPrimitive.point)
    assert tuple(item.primitive for item in context.entities) == before
    assert free_body_primitive_names() == free_body_before
    assert "system" not in free_body_before
    assert "point" not in free_body_before
    assert "joint" not in free_body_before


def test_the_production_path_does_not_import_the_diagnosis():
    """A counterfactual must never be able to reach a runtime answer."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in (root / "engine").rglob("*.py"):
        if "query_readout_ownership" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(root)))
    for path in (root / "app").rglob("*.py"):
        if "query_readout_ownership" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


# --------------------------------------------------------------------------
# Privacy
# --------------------------------------------------------------------------


def test_the_diagnosis_record_carries_only_counts_and_closed_vocabulary():
    diagnosis = diagnose_query_readout_ownership(
        [
            (
                _context(
                    readout_owner="pt",
                    owner_primitive=EntityPrimitive.point,
                    geometry=(
                        _geometry("g1", GeometryRelationKind.lies_on, ["pt", "body"]),
                    ),
                ),
                QUERY_QUANTITY_ID,
            )
        ]
    )
    payload = diagnosis_as_dict(diagnosis)
    text = json.dumps(payload, ensure_ascii=False)

    outcomes = {item.value for item in OwnershipCausalOutcome}
    primitives = {item.value for item in EntityPrimitive}
    for row in payload["outcome_counts"]:
        assert row["outcome"] in outcomes
        assert isinstance(row["count"], int)
    for row in payload["outcome_by_primitive"]:
        assert row["primitive"] in primitives
        assert row["outcome"] in outcomes

    for token in ("case_id", "family", "problem_text", "answer", "gold", "expected"):
        assert token not in text


def test_the_binding_vocabulary_is_closed_and_names_the_direct_case():
    """`direct` is in the vocabulary so the enum is the whole space.

    A binding kind set that listed only the indirect cases would read as if
    every readout needed one.
    """

    assert ReadoutBindingKind.direct.value == "direct"
    assert {item.value for item in ReadoutBindingKind} == {
        "direct",
        "aggregate_member_equivalence",
        "aggregate_common_magnitude",
        "point_on_body_readout",
        "joint_point_readout",
        "joint_reaction_readout",
    }
