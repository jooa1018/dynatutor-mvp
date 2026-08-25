"""Newton's second law must never be written over a half-built free body.

Summing a subset of the forces on a body is not a weaker answer than summing
all of them — it is a wrong one, delivered with the same confidence as a right
one.  A block resting on a table whose free body carries only its weight
accelerates downwards at g; a rope that pulls on one side only balances against
nothing; a single stated force is the resultant only if something says it is.

Every case below is an *engine-level* control on `particle_newton_second`.  They
exist so that no closure profile can be enabled while a partially attached free
body still produces an equation, which is why they are written before any
profile creates a force.

All fixtures are independently authored.
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

NEWTON = "particle_newton_second"


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
    frame_id: str | None = None,
    interval_id: str | None = None,
    component: str = "unspecified",
    sign: int | None = None,
) -> dict:
    direction = (
        {"kind": "axis", "frame_id": frame_id, "axis": "y", "sign": sign}
        if sign is not None
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
        "frame_id": frame_id,
        "interval_id": interval_id,
        "event_id": None,
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
    interaction_id: str, kind: str, participants: list[str], quantity_ids: list[str]
) -> dict:
    return {
        "interaction_id": interaction_id,
        "kind": kind,
        "participant_ids": participants,
        "point_ids": [],
        "frame_id": "frame1",
        "interval_id": "interval1",
        "event_id": None,
        "quantity_ids": quantity_ids,
        "evidence_refs": [],
    }


def _contact_state(subject_id: str, quantity_ids: list[str]) -> dict:
    return {
        "state_condition_id": f"state_{subject_id}",
        "kind": "contact",
        "state": "touching",
        "subject_id": subject_id,
        "interval_id": "interval1",
        "event_id": None,
        "expression": None,
        "quantity_ids": quantity_ids,
        "evidence_refs": [],
    }


def _resultant_authority(subject_id: str) -> dict:
    return {
        "assumption_id": "resultantAuthority",
        "kind": "resultant_force",
        "subject_id": subject_id,
        "interval_id": "interval1",
        "disposition": "approved",
        "proposed_role": None,
        "proposed_value": None,
        "proposed_unit": None,
        "reason": "The source states this force is the net force on the body.",
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


def _payload(
    *,
    bodies: list[str],
    forces: list[tuple[str, str, float, int]],
    interactions: list[dict],
    state_conditions: list[dict] | None = None,
    assumptions: list[dict] | None = None,
    extra_entities: list[dict] | None = None,
) -> dict:
    """One or two particles in a vertical plane, with an exact force set.

    `forces` is `(name, subject, value, axis sign)`.
    """

    entities = [_entity(body, "particle") for body in bodies]
    entities.extend(extra_entities or [])
    entities.append(_entity("ground", "surface"))
    entities.append(_entity("field", "environment"))

    symbols = []
    quantities = []
    for body in bodies:
        symbols.append(_symbol(f"m_{body}", f"mass_{body}", MASS))
        symbols.append(_symbol(f"a_{body}", f"accel_{body}", ACCELERATION))
        quantities.append(
            _quantity(f"mass_{body}", f"m_{body}", "mass", body, MASS, value=3.0, unit="kg")
        )
        quantities.append(
            _quantity(
                f"accel_{body}",
                f"a_{body}",
                "acceleration",
                body,
                ACCELERATION,
                frame_id="frame1",
                interval_id="interval1",
                component="y",
                sign=1,
            )
        )
    for name, subject, value, sign in forces:
        symbols.append(_symbol(name, f"{name}Q", FORCE))
        quantities.append(
            _quantity(
                f"{name}Q",
                name,
                "force",
                subject,
                FORCE,
                value=value,
                unit="N",
                frame_id="frame1",
                interval_id="interval1",
                component="y",
                sign=sign,
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
    subjects = [*bodies, "ground", "field"]
    subjects.extend(item["entity_id"] for item in (extra_entities or []))

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
        "reference_frames": [
            {
                "frame_id": "frame1",
                "frame_type": "cartesian_2d",
                "origin": {"kind": "world"},
                "axes": [
                    {
                        "axis": "x",
                        "direction": {
                            "kind": "axis",
                            "frame_id": "frame1",
                            "axis": "x",
                            "sign": 1,
                        },
                    },
                    {
                        "axis": "y",
                        "direction": {
                            "kind": "axis",
                            "frame_id": "frame1",
                            "axis": "y",
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
        ],
        "motion_intervals": [
            {
                "interval_id": "interval1",
                "order": 1,
                "subject_ids": subjects,
                "frame_id": "frame1",
                "start_event_id": None,
                "end_event_id": None,
                "evidence_refs": [],
            }
        ],
        "events": [],
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
                    "subject_id": bodies[0],
                    "point_id": None,
                    "frame_id": "frame1",
                    "interval_id": "interval1",
                    "event_id": None,
                    "component": "y",
                    "direction": None,
                    "target_quantity_id": f"accel_{bodies[0]}",
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
    """No Newton equation, no answer, and no invalid-IR excuse for it."""

    assert NEWTON not in _emitted_laws(result)
    # The refusal must be a *modelling* verdict, not a malformed fixture: an
    # `invalid` status would make this control vacuous.
    assert result.status is not CompilerStatus.invalid, [
        (item.code.value, item.message) for item in result.issues
    ]


# --------------------------------------------------------------------------
# Negative controls: a partially attached free body
# --------------------------------------------------------------------------


def test_contact_plus_gravity_force_only_does_not_emit_newton():
    """The block rests on the table.  Its weight alone is not its free body."""

    result = _compile(
        _payload(
            bodies=["block"],
            forces=[("weight", "block", -29.43, -1)],
            interactions=[
                _interaction("grav", "gravity", ["block", "field"], ["weightQ"]),
                _interaction("cont", "contact", ["block", "ground"], []),
            ],
        )
    )
    _assert_no_newton(result)


def test_contact_plus_normal_only_does_not_emit_newton():
    result = _compile(
        _payload(
            bodies=["block"],
            forces=[("normal", "block", 29.43, 1)],
            interactions=[
                _interaction("cont", "contact", ["block", "ground"], ["normalQ"]),
            ],
            state_conditions=[_contact_state("block", ["normalQ"])],
        )
    )
    _assert_no_newton(result)


def test_gravity_and_contact_with_an_unstated_regime_does_not_emit_newton():
    """Both interactions contribute, but nothing says what the contact *is*.

    Whether the contact contributes a normal alone or a normal and a friction
    force is decided by the friction regime, and no typed state condition states
    one here — so the force set is unproven and the equation is withheld.
    """

    result = _compile(
        _payload(
            bodies=["block"],
            forces=[
                ("weight", "block", -29.43, -1),
                ("normal", "block", 20.0, 1),
            ],
            interactions=[
                _interaction("grav", "gravity", ["block", "field"], ["weightQ"]),
                _interaction("cont", "contact", ["block", "ground"], ["normalQ"]),
            ],
        )
    )
    _assert_no_newton(result)


def test_one_sided_rope_tension_does_not_emit_newton():
    """A rope connects two bodies.  A tension on one side balances nothing."""

    result = _compile(
        _payload(
            bodies=["blockA", "blockB"],
            forces=[
                ("weightA", "blockA", -29.43, -1),
                ("tensionA", "blockA", 12.0, 1),
            ],
            interactions=[
                _interaction("grav", "gravity", ["blockA", "field"], ["weightAQ"]),
                _interaction(
                    "rope",
                    "rope_tension",
                    ["blockA", "blockB", "cord"],
                    ["tensionAQ"],
                ),
            ],
            extra_entities=[_entity("cord", "rope")],
        )
    )
    _assert_no_newton(result)


def test_a_single_force_on_a_constrained_body_is_not_a_resultant():
    """A push on a block that is also resting on something.

    The contact carries a reaction, so the push is not the whole free body.
    Treating it as the resultant is the confident wrong solve; only a typed
    authority stating that this force *is* the net force could license it.
    """

    result = _compile(
        _payload(
            bodies=["block"],
            forces=[("push", "block", 12.0, 1)],
            interactions=[
                _interaction("applied", "applied_force", ["block"], ["pushQ"]),
                _interaction("cont", "contact", ["block", "ground"], ["pushQ"]),
            ],
            state_conditions=[_contact_state("block", ["pushQ"])],
        )
    )
    _assert_no_newton(result)


def test_a_free_particles_single_force_is_its_resultant():
    """The accepted Stage 6 contract, pinned here so the guard cannot erode it.

    Nothing constrains this particle: no contact, rope, joint, spring, damper,
    or gear names it.  The one force the source states is therefore the whole
    free body, and withholding the equation would be wrong in the other
    direction.  The resultant authority is required only where something else
    is acting on the body.
    """

    result = _compile(
        _payload(
            bodies=["part"],
            forces=[("push", "part", 12.0, 1)],
            interactions=[
                _interaction("applied", "applied_force", ["part"], ["pushQ"]),
            ],
        )
    )
    assert NEWTON in _emitted_laws(result)


@pytest.mark.parametrize(
    "kind, subject",
    [
        # Right shape, wrong name: only the exact authority counts.
        ("net_force", "block"),
        ("constant_force", "block"),
        # Right name, wrong body.
        ("resultant_force", "other"),
    ],
)
def test_a_near_miss_authority_does_not_make_a_force_a_resultant(kind, subject):
    authority = _resultant_authority("block")
    authority["kind"] = kind
    authority["subject_id"] = subject
    result = _compile(
        _payload(
            bodies=["block"],
            forces=[("push", "block", 12.0, 1)],
            interactions=[
                _interaction("applied", "applied_force", ["block"], ["pushQ"]),
                _interaction("cont", "contact", ["block", "ground"], ["pushQ"]),
            ],
            state_conditions=[_contact_state("block", ["pushQ"])],
            assumptions=[authority],
            extra_entities=(
                [_entity("other", "particle")] if subject == "other" else None
            ),
        )
    )
    _assert_no_newton(result)


def test_an_unapproved_resultant_authority_does_not_close_the_free_body():
    authority = _resultant_authority("block")
    authority["disposition"] = "proposed"
    result = _compile(
        _payload(
            bodies=["block"],
            forces=[("push", "block", 12.0, 1)],
            interactions=[
                _interaction("applied", "applied_force", ["block"], ["pushQ"]),
                _interaction("cont", "contact", ["block", "ground"], ["pushQ"]),
            ],
            state_conditions=[_contact_state("block", ["pushQ"])],
            assumptions=[authority],
        )
    )
    _assert_no_newton(result)


# --------------------------------------------------------------------------
# Positive controls: a complete free body still emits
# --------------------------------------------------------------------------


def test_a_complete_contact_free_body_emits_newton():
    """Gravity and a contact whose regime is stated: every force is present."""

    result = _compile(
        _payload(
            bodies=["block"],
            forces=[
                ("weight", "block", -29.43, -1),
                ("normal", "block", 29.43, 1),
            ],
            interactions=[
                _interaction("grav", "gravity", ["block", "field"], ["weightQ"]),
                _interaction("cont", "contact", ["block", "ground"], ["normalQ"]),
            ],
            state_conditions=[_contact_state("block", ["normalQ"])],
        )
    )
    assert NEWTON in _emitted_laws(result)


def test_a_two_sided_rope_free_body_emits_newton():
    result = _compile(
        _payload(
            bodies=["blockA", "blockB"],
            forces=[
                ("weightA", "blockA", -29.43, -1),
                ("tensionA", "blockA", 12.0, 1),
                ("tensionB", "blockB", 12.0, 1),
            ],
            interactions=[
                _interaction("grav", "gravity", ["blockA", "field"], ["weightAQ"]),
                _interaction(
                    "rope",
                    "rope_tension",
                    ["blockA", "blockB", "cord"],
                    ["tensionAQ", "tensionBQ"],
                ),
            ],
            extra_entities=[_entity("cord", "rope")],
        )
    )
    assert NEWTON in _emitted_laws(result)


def test_a_single_force_with_an_exact_resultant_authority_emits_newton():
    result = _compile(
        _payload(
            bodies=["block"],
            forces=[("push", "block", 12.0, 1)],
            interactions=[
                _interaction("applied", "applied_force", ["block"], ["pushQ"]),
                _interaction("cont", "contact", ["block", "ground"], ["pushQ"]),
            ],
            state_conditions=[_contact_state("block", ["pushQ"])],
            assumptions=[_resultant_authority("block")],
        )
    )
    assert NEWTON in _emitted_laws(result)
