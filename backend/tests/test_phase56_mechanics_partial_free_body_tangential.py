"""A free body is closed per component, not per body.

`test_phase56_mechanics_partial_free_body.py` closed the case where a body's
free body is missing a force outright.  This module closes the one that
survives it: a free body that looks closed *somewhere* and is still open on the
component the equation is actually being written on.

A block pressed onto a surface is the whole of it.  The contact owns a normal
force, so every body-level check finds the contact modelled — but the normal
lies along the surface normal, and Newton's second law along the *tangent* sums
a completely different set.  Whether the contact contributes to that sum is
decided by the friction regime, and nothing in the body-level check ever asks.
Two applied tangential forces then balance against nothing, and the engine
reports an acceleration that omits friction with full confidence.

Closure is therefore decided per subject, per component, per frame, per
interval, per event, per interaction, and per contact regime.  Every fixture
below is independently authored: none is derived from a corpus case, and none
reads a case ID, family, split, expected terminal, or expected answer.
"""

from __future__ import annotations

import pytest

from engine.mechanics.compiler import (
    CompilerStatus,
    MechanicsCompiler,
    authorize_validated_mechanics_ir,
)
from engine.mechanics.contracts import (
    IR_SCHEMA_NAME,
    IR_SCHEMA_VERSION,
    MechanicsProblemIRV1,
)
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.normalization import (
    NORMALIZATION_POLICY_VERSION,
    VALIDATION_POLICY_VERSION,
)
from engine.mechanics.units import normalize_quantity

MASS = DimensionVector(mass=1)
ACCELERATION = DimensionVector(length=1, time=-2)
FORCE = DimensionVector(mass=1, length=1, time=-2)
DIMENSIONLESS = DimensionVector()

NEWTON = "particle_newton_second"

# The tangent/normal pair the whole module is written on.  Naming them once
# keeps every fixture honest about which component it is talking about.
TANGENT = ("tangential", "tangent")
NORMAL = ("normal", "normal")


# --------------------------------------------------------------------------
# Fixture construction
# --------------------------------------------------------------------------


def _symbol(symbol_id: str, quantity_id: str, dimension: DimensionVector) -> dict:
    return {
        "symbol_id": symbol_id,
        "quantity_id": quantity_id,
        "dimension": dimension.model_dump(mode="json"),
        "shape": "scalar",
        "vector_length": None,
    }


def _quantity(
    quantity_id: str,
    symbol_id: str,
    role: str,
    subject_id: str,
    dimension: DimensionVector,
    *,
    value: float | None = None,
    unit: str = "1",
    axis_pair: tuple[str, str] | None = None,
    sign: int = 1,
    interval_id: str | None = "interval1",
    event_id: str | None = None,
) -> dict:
    component, axis = axis_pair if axis_pair is not None else ("unspecified", "x")
    direction = (
        {"kind": "axis", "frame_id": "frame1", "axis": axis, "sign": sign}
        if axis_pair is not None
        else None
    )
    normalized = (
        normalize_quantity(str(value), unit, "scalar", dimension)
        if value is not None
        else None
    )
    return {
        "quantity_id": quantity_id,
        "symbol_id": symbol_id,
        "role": role,
        "subject_id": subject_id,
        "point_id": None,
        "frame_id": "frame1" if axis_pair is not None else None,
        "interval_id": interval_id,
        "event_id": event_id,
        "component": component,
        "direction": direction,
        "shape": "scalar",
        "dimension": dimension.model_dump(mode="json"),
        "provenance": "explicit_source" if value is not None else "inferred",
        "evidence_refs": [f"ev_{quantity_id}"] if value is not None else [],
        "assumption_policy_ref": None,
        "correction_id": None,
        "model_confidence": None,
        "raw_value": str(value) if value is not None else None,
        "raw_unit": unit if value is not None else None,
        "si_value": normalized.value if normalized is not None else None,
        "si_unit": normalized.si_unit if normalized is not None else None,
    }


def _interaction(
    interaction_id: str,
    kind: str,
    participants: list[str],
    quantity_ids: list[str],
    *,
    interval_id: str | None = "interval1",
    event_id: str | None = None,
) -> dict:
    return {
        "interaction_id": interaction_id,
        "kind": kind,
        "participant_ids": participants,
        "point_ids": [],
        "frame_id": "frame1",
        "interval_id": interval_id,
        "event_id": event_id,
        "quantity_ids": quantity_ids,
        "evidence_refs": [],
    }


def _state(
    state_condition_id: str,
    kind: str,
    state: str,
    subject_id: str,
    quantity_ids: list[str],
    *,
    interval_id: str | None = "interval1",
    event_id: str | None = None,
) -> dict:
    return {
        "state_condition_id": state_condition_id,
        "kind": kind,
        "state": state,
        "subject_id": subject_id,
        "interval_id": interval_id,
        "event_id": event_id,
        "expression": None,
        "quantity_ids": quantity_ids,
        "evidence_refs": [],
    }


def _frictionless_authority(
    subject_id: str = "block",
    *,
    kind: str = "frictionless_contact",
    disposition: str = "approved",
    interval_id: str | None = "interval1",
) -> dict:
    return {
        "assumption_id": "frictionlessAuthority",
        "kind": kind,
        "subject_id": subject_id,
        "interval_id": interval_id,
        "disposition": disposition,
        "proposed_role": None,
        "proposed_value": None,
        "proposed_unit": None,
        "reason": "The source states the surface is smooth, so the contact carries no friction.",
        "evidence_refs": [],
    }


def _entity(entity_id: str, primitive: str) -> dict:
    return {
        "entity_id": entity_id,
        "primitive": primitive,
        "label": entity_id,
        "aliases": [],
        "component_of_entity_id": None,
        "evidence_refs": [],
        "model_confidence": None,
    }


def _frame() -> dict:
    return {
        "frame_id": "frame1",
        "frame_type": "tangential_normal",
        "origin": {"kind": "world"},
        "axes": [
            {
                "axis": "tangent",
                "direction": {
                    "kind": "axis",
                    "frame_id": "frame1",
                    "axis": "tangent",
                    "sign": 1,
                },
            },
            {
                "axis": "normal",
                "direction": {
                    "kind": "axis",
                    "frame_id": "frame1",
                    "axis": "normal",
                    "sign": 1,
                },
            },
        ],
        "parent_frame_id": None,
        "translating_with_entity_id": None,
        "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }


def _payload(
    *,
    forces: list[tuple[str, float, tuple[str, str], int]],
    interactions: list[dict],
    state_conditions: list[dict] | None = None,
    assumptions: list[dict] | None = None,
    query_axis: tuple[str, str] = TANGENT,
    accel_interval_id: str | None = "interval1",
    accel_event_id: str | None = None,
    events: list[dict] | None = None,
    coefficient: bool = False,
    contact_interval_id: str | None = "interval1",
    contact_event_id: str | None = None,
) -> dict:
    """One block on a surface, in a tangent/normal frame, with an exact force set.

    `forces` is `(name, value, (component, axis), axis sign)` and every force
    belongs to `block`.  The single acceleration is the one the query asks for,
    so exactly one Newton equation is ever attempted and a control cannot pass
    by emitting the equation for some other component.
    """

    entities = [_entity("block", "particle"), _entity("ground", "surface")]

    symbols = [
        _symbol("m_block", "mass_block", MASS),
        _symbol("a_block", "accel_block", ACCELERATION),
    ]
    quantities = [
        _quantity("mass_block", "m_block", "mass", "block", MASS, value=3.0, unit="kg"),
        _quantity(
            "accel_block",
            "a_block",
            "acceleration",
            "block",
            ACCELERATION,
            axis_pair=query_axis,
            sign=1,
            interval_id=accel_interval_id,
            event_id=accel_event_id,
        ),
    ]
    # The contact's own forces follow the contact's scope, so moving the contact
    # to another interval or on to an event moves everything it owns with it.
    contact_owned = {"normal", "friction"}
    for name, value, axis_pair, sign in forces:
        symbols.append(_symbol(name, f"{name}Q", FORCE))
        owned_by_contact = name in contact_owned
        quantities.append(
            _quantity(
                f"{name}Q",
                name,
                "force",
                "block",
                FORCE,
                value=value,
                unit="N",
                axis_pair=axis_pair,
                sign=sign,
                interval_id=contact_interval_id if owned_by_contact else "interval1",
                event_id=contact_event_id if owned_by_contact else None,
            )
        )
    if coefficient:
        symbols.append(_symbol("mu", "muQ", DIMENSIONLESS))
        quantities.append(
            _quantity(
                "muQ",
                "mu",
                "coefficient_friction",
                "block",
                DIMENSIONLESS,
                value=0.2,
                unit="1",
            )
        )

    evidence = [
        {
            "evidence_id": f"ev_{item['quantity_id']}",
            "kind": "text",
            "quote": f"stated {item['raw_value']} {item['raw_unit']}",
            "source_span": {"start": 0, "end": 6},
            "quantity_span": {"start": 7, "end": 8},
            "occurrence_index": 0,
        }
        for item in quantities
        if item["raw_value"] is not None
    ]

    # An event only exists in the fixtures that need one, and the contract
    # requires its membership to be reciprocal with the interval that opens on
    # it.
    opening_event = next(
        (
            item["event_id"]
            for item in (events or [])
            if "interval1" in item.get("interval_ids", [])
        ),
        None,
    )
    intervals = [
        {
            "interval_id": "interval1",
            "order": 1,
            "subject_ids": ["block", "ground"],
            "frame_id": "frame1",
            "start_event_id": opening_event,
            "end_event_id": None,
            "evidence_refs": [],
        }
    ]
    # A second interval exists only in the fixtures that need somewhere else for
    # a record to belong to.  Declaring it always would change nothing.
    if any(
        item.get("interval_id") == "interval2"
        for item in [*(state_conditions or []), *(assumptions or []), *interactions]
    ) or "interval2" in {accel_interval_id, contact_interval_id}:
        intervals.append(
            {
                "interval_id": "interval2",
                "order": 2,
                "subject_ids": ["block", "ground"],
                "frame_id": "frame1",
                "start_event_id": None,
                "end_event_id": None,
                "evidence_refs": [],
            }
        )

    return {
        "schema": IR_SCHEMA_NAME,
        "version": IR_SCHEMA_VERSION,
        "validation_policy_version": VALIDATION_POLICY_VERSION,
        "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": None,
            "subtype": None,
            "model_id": None,
            "model_hash": None,
            "prompt_hash": None,
            "source_text_sha256": None,
            "model_confidence": None,
        },
        "source_assets": [],
        "source_evidence": evidence,
        "entities": entities,
        "points": [],
        "reference_frames": [_frame()],
        "motion_intervals": intervals,
        "events": events or [],
        "symbols": symbols,
        "quantities": quantities,
        "geometry": [],
        "interactions": interactions,
        "constraints": [],
        "state_conditions": state_conditions or [],
        "queries": [
            {
                "query_id": "q1",
                "target": {
                    "role": "acceleration",
                    "subject_id": "block",
                    "point_id": None,
                    "frame_id": "frame1",
                    "interval_id": accel_interval_id,
                    "event_id": accel_event_id,
                    "component": query_axis[0],
                    "direction": None,
                    "target_quantity_id": "accel_block",
                },
                "output_unit": "m/s^2",
                "output_dimension": ACCELERATION.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": [],
            }
        ],
        "principle_hints": [],
        "assumptions": assumptions or [],
        "ambiguities": [],
        "figure_dependency": {
            "level": "none",
            "missing_information": [],
            "evidence_refs": [],
        },
        "unsupported_features": [],
    }


def _compile(payload: dict):
    ir = MechanicsProblemIRV1.model_validate(payload)
    approved = tuple(
        sorted(
            item.assumption_id
            for item in ir.assumptions
            if item.disposition.value == "approved"
        )
    )
    return MechanicsCompiler().compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=approved,
    )


def _emitted_laws(result) -> set[str]:
    if result.graph is None:
        return set()
    return {item.law_id for item in result.graph.applications}


def _assert_no_newton(result) -> None:
    """No Newton equation, and no malformed-fixture excuse for its absence."""

    assert NEWTON not in _emitted_laws(result)
    assert result.status is not CompilerStatus.invalid, [
        (item.code.value, item.message) for item in result.issues
    ]


def _assert_newton(result) -> None:
    assert NEWTON in _emitted_laws(result), [
        (item.code.value, item.message) for item in result.issues
    ]


# --------------------------------------------------------------------------
# Shared structure: the contact that owns a normal and nothing tangential
# --------------------------------------------------------------------------


def _pressed_block_interactions(
    *,
    friction_force: bool = False,
    contact_interval_id: str | None = "interval1",
    contact_event_id: str | None = None,
) -> list[dict]:
    """Two tangential pushes and one contact, on a block pressed onto a surface.

    With `friction_force`, the contact owns the whole set a stated regime
    implies — a normal, a tangential friction force, and the coefficient that
    relates them — which is what the compiler's closed sticking/sliding profile
    requires before it will accept the regime at all.
    """

    contact_quantities = ["normalQ"]
    if friction_force:
        contact_quantities.extend(["frictionQ", "muQ"])
    return [
        _interaction("iPush", "applied_force", ["block"], ["pushQ"]),
        _interaction("iDrag", "applied_force", ["block"], ["dragQ"]),
        _interaction(
            "iCont",
            "contact",
            ["block", "ground"],
            contact_quantities,
            interval_id=contact_interval_id,
            event_id=contact_event_id,
        ),
    ]


def _pressed_block_forces(*, friction_force: bool = False) -> list:
    forces = [
        ("push", 18.0, TANGENT, 1),
        ("drag", -4.0, TANGENT, -1),
        ("normal", 29.43, NORMAL, 1),
    ]
    if friction_force:
        forces.append(("friction", -6.0, TANGENT, -1))
    return forces


# --------------------------------------------------------------------------
# The negative control this module exists for
# --------------------------------------------------------------------------


def test_two_tangential_forces_over_an_unstated_friction_regime_do_not_emit_newton():
    """The exact partial-free-body shape that survives the body-level check.

    The block is in contact with a support, the contact owns a normal force,
    and a typed touching state exists — so every body-level completeness
    question is answered yes.  Along the tangent, though, the contact owns
    nothing: no friction state says the contact contributes zero there, no
    frictionless authority says it either, and no tangential friction force is
    modelled.  Summing the two applied forces alone would report an
    acceleration that silently omits friction.
    """

    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[_state("st_contact", "contact", "touching", "block", ["normalQ"])],
        )
    )
    _assert_no_newton(result)


# --------------------------------------------------------------------------
# Controls: what does close the tangential free body
# --------------------------------------------------------------------------


def test_an_explicit_frictionless_authority_permits_the_tangential_equation():
    """A stated smooth surface is a typed statement that friction is zero here."""

    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[_state("st_contact", "contact", "touching", "block", ["normalQ"])],
            assumptions=[_frictionless_authority()],
        )
    )
    _assert_newton(result)


@pytest.mark.parametrize("regime", ["sliding", "sticking"])
def test_a_typed_regime_with_the_complete_friction_force_set_permits_it(regime):
    """A stated regime *and* the friction force it implies: nothing is missing.

    The contact now owns the whole set the regime commits it to — a normal, a
    directed tangential friction force, and the coefficient relating them — so
    the tangential sum contains the contact's contribution rather than
    silently dropping it.
    """

    result = _compile(
        _payload(
            forces=_pressed_block_forces(friction_force=True),
            interactions=_pressed_block_interactions(friction_force=True),
            state_conditions=[
                _state("st_contact", "contact", "touching", "block", ["normalQ"]),
                _state("st_friction", "friction", regime, "block", ["frictionQ"]),
            ],
            coefficient=True,
        )
    )
    _assert_newton(result)


@pytest.mark.parametrize("regime", ["sliding", "sticking"])
def test_a_typed_regime_without_its_friction_force_does_not_emit(regime):
    """Naming the regime does not supply the force the regime implies.

    A sliding contact exerts a tangential friction force.  Stating the regime
    and then modelling no such force leaves the sum short by exactly that term,
    which is the same wrong answer as never mentioning friction at all.
    """

    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[
                _state("st_contact", "contact", "touching", "block", ["normalQ"]),
                _state("st_friction", "friction", regime, "block", []),
            ],
        )
    )
    _assert_no_newton(result)


# --------------------------------------------------------------------------
# Controls: authority that belongs somewhere else closes nothing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("regime", ["sliding", "sticking"])
def test_a_friction_regime_from_another_interval_cannot_close_this_free_body(regime):
    """A regime stated for a different phase of the motion.

    An interval is a separate dynamical situation.  A regime stated for
    `interval2` says nothing about the forces acting during `interval1`, and
    borrowing it would let any later phase retroactively license an earlier
    equation.
    """

    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[
                _state("st_contact", "contact", "touching", "block", ["normalQ"]),
                _state(
                    "st_friction",
                    "friction",
                    regime,
                    "block",
                    [],
                    interval_id="interval2",
                ),
            ],
        )
    )
    _assert_no_newton(result)


def test_a_contact_belonging_to_another_interval_cannot_close_this_free_body():
    """The contact, its normal, and its regime all belong to `interval2`.

    Nothing about the surface is stated for `interval1`, so the two applied
    tangential forces are again the whole of a sum that may be missing a
    friction term.  The contact still names the block, so it is still a hole —
    it is simply a hole nothing in this interval fills.
    """

    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(contact_interval_id="interval2"),
            state_conditions=[
                _state(
                    "st_contact",
                    "contact",
                    "touching",
                    "block",
                    ["normalQ"],
                    interval_id="interval2",
                ),
            ],
            contact_interval_id="interval2",
        )
    )
    _assert_no_newton(result)


def test_a_contact_belonging_to_an_event_cannot_close_an_interval_equation():
    """An event is an instant, not the interval that contains it.

    A contact modelled at the moment it is established does not describe the
    whole interval, so it cannot license an equation written over that
    interval.
    """

    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(contact_event_id="event1"),
            state_conditions=[
                _state(
                    "st_contact",
                    "contact",
                    "touching",
                    "block",
                    ["normalQ"],
                    event_id="event1",
                ),
            ],
            contact_event_id="event1",
            events=[
                {
                    "event_id": "event1",
                    "kind": "contact_start",
                    "subject_ids": ["block", "ground"],
                    "interval_ids": ["interval1"],
                    "time_quantity_id": None,
                    "evidence_refs": [],
                }
            ],
        )
    )
    _assert_no_newton(result)


def test_a_frictionless_authority_for_another_body_closes_nothing():
    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[_state("st_contact", "contact", "touching", "block", ["normalQ"])],
            assumptions=[_frictionless_authority("ground")],
        )
    )
    _assert_no_newton(result)


def test_an_unapproved_frictionless_authority_closes_nothing():
    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[_state("st_contact", "contact", "touching", "block", ["normalQ"])],
            assumptions=[_frictionless_authority(disposition="proposed")],
        )
    )
    _assert_no_newton(result)


@pytest.mark.parametrize("kind", ["smooth_contact", "no_friction", "frictionless"])
def test_a_near_miss_frictionless_authority_closes_nothing(kind):
    """Only the exact typed authority counts; a plausible name is not one."""

    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[_state("st_contact", "contact", "touching", "block", ["normalQ"])],
            assumptions=[_frictionless_authority(kind=kind)],
        )
    )
    _assert_no_newton(result)


def test_a_frictionless_authority_from_another_interval_closes_nothing():
    result = _compile(
        _payload(
            forces=_pressed_block_forces(),
            interactions=_pressed_block_interactions(),
            state_conditions=[_state("st_contact", "contact", "touching", "block", ["normalQ"])],
            assumptions=[_frictionless_authority(interval_id="interval2")],
        )
    )
    _assert_no_newton(result)


# --------------------------------------------------------------------------
# Control: the normal component is unaffected
# --------------------------------------------------------------------------


def test_the_normal_component_still_closes_on_the_contacts_own_force():
    """The guard is per component, so it must not spread to the normal one.

    Along the normal the contact owns exactly the force it contributes.  That
    component was never in doubt and must keep emitting, otherwise the repair
    is a blanket refusal rather than a completeness check.
    """

    result = _compile(
        _payload(
            forces=[
                ("normal", 29.43, NORMAL, 1),
                ("weight", -29.43, NORMAL, -1),
            ],
            interactions=[
                _interaction("iCont", "contact", ["block", "ground"], ["normalQ"]),
                _interaction("iGrav", "applied_force", ["block"], ["weightQ"]),
            ],
            state_conditions=[_state("st_contact", "contact", "touching", "block", ["normalQ"])],
            query_axis=NORMAL,
        )
    )
    _assert_newton(result)
