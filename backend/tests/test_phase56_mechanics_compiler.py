from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from engine.mechanics.compiler import (
    CompilerIssueCode,
    CompilerLimits,
    CompilerStatus,
    EquationGraph,
    MechanicsCompiler,
    ValidatedIRAuthorization,
    authorize_validated_mechanics_ir,
    compile_mechanics_ir as _compile_mechanics_ir,
)
from engine.mechanics.contracts import (
    IR_SCHEMA_NAME,
    IR_SCHEMA_VERSION,
    MechanicsProblemIRV1,
)
from engine.mechanics.laws import core_law_catalog
from engine.mechanics.math_ast import (
    Add,
    Derivative,
    DimensionVector,
    Divide,
    Dot,
    Equality,
    Inequality,
    InequalityRelation,
    LiteralNode,
    Multiply,
    Negate,
    Power,
    Subtract,
    SymbolRef,
)
from engine.mechanics.normalization import NORMALIZATION_POLICY_VERSION, VALIDATION_POLICY_VERSION
from engine.mechanics.units import normalize_quantity
from engine.mechanics.compiler.compiler import _linear_analysis
from engine.mechanics.validation import AssumptionAuthorization, CorrectionAuthorization


DIMENSIONLESS = DimensionVector()
MASS = DimensionVector(mass=1)
LENGTH = DimensionVector(length=1)
TIME = DimensionVector(time=1)
FREQUENCY = DimensionVector(time=-1)
ANGULAR_ACCELERATION = DimensionVector(time=-2)
VELOCITY = DimensionVector(length=1, time=-1)
ACCELERATION = DimensionVector(length=1, time=-2)
FORCE = DimensionVector(mass=1, length=1, time=-2)
ENERGY = DimensionVector(mass=1, length=2, time=-2)
POWER_DIMENSION = DimensionVector(mass=1, length=2, time=-3)
STIFFNESS = DimensionVector(mass=1, time=-2)
MOMENT_OF_INERTIA = DimensionVector(mass=1, length=2)
ANGULAR_MOMENTUM = DimensionVector(mass=1, length=2, time=-1)


def _symbol(symbol_id: str, quantity_id: str, dimension: DimensionVector) -> dict[str, object]:
    return {
        "symbol_id": symbol_id,
        "quantity_id": quantity_id,
        "dimension": dimension.model_dump(mode="json"),
        "shape": "scalar",
        "vector_length": None,
    }


def _quantity(
    quantity_id: str,
    symbol_id: str | None,
    role: str,
    subject_id: str,
    dimension: DimensionVector,
    *,
    value: float | None = None,
    unit: str = "1",
    frame_id: str | None = None,
    interval_id: str | None = None,
    event_id: str | None = None,
    point_id: str | None = None,
    component: str = "unspecified",
    sign: int | None = None,
    provenance: str | None = None,
    evidence_refs: tuple[str, ...] = (),
    correction_id: str | None = None,
    assumption_policy_ref: str | None = None,
) -> dict[str, object]:
    direction = None
    if sign is not None:
        direction = {"kind": "axis", "frame_id": frame_id, "axis": "x", "sign": sign}
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
        "point_id": point_id,
        "frame_id": frame_id,
        "interval_id": interval_id,
        "event_id": event_id,
        "component": component,
        "direction": direction,
        "shape": "scalar",
        "dimension": dimension.model_dump(mode="json"),
        "provenance": provenance or ("user_correction" if value is not None else "inferred"),
        "evidence_refs": list(evidence_refs),
        "assumption_policy_ref": assumption_policy_ref,
        "correction_id": correction_id if correction_id is not None else (f"corr_{quantity_id}" if value is not None and provenance in {None, "user_correction"} else None),
        "model_confidence": None,
        "raw_value": str(value) if value is not None else None,
        "raw_unit": unit if value is not None else None,
        "si_value": normalized.value if normalized is not None else None,
        "si_unit": normalized.si_unit if normalized is not None else None,
    }


def _constraint(
    constraint_id: str,
    expression: Equality | Inequality,
    *,
    kind: str = "rope",
    subjects: tuple[str, ...] = ("bodyA", "bodyB", "rope1"),
) -> dict[str, object]:
    return {
        "constraint_id": constraint_id,
        "kind": kind,
        "expression": expression,
        "subject_ids": list(subjects),
        "interval_id": "interval1",
        "event_id": None,
        "evidence_refs": [],
    }


def _problem_payload() -> dict[str, object]:
    symbols = [
        _symbol("mA", "massA", MASS),
        _symbol("mB", "massB", MASS),
        _symbol("fA", "forceA", FORCE),
        _symbol("fB", "forceB", FORCE),
        _symbol("tA", "tensionA", FORCE),
        _symbol("tB", "tensionB", FORCE),
        _symbol("aA", "accelerationA", ACCELERATION),
        _symbol("aB", "accelerationB", ACCELERATION),
    ]
    quantities = [
        _quantity("massA", "mA", "mass", "bodyA", MASS, value=2.0, unit="kg"),
        _quantity("massB", "mB", "mass", "bodyB", MASS, value=3.0, unit="kg"),
        _quantity("forceA", "fA", "force", "bodyA", FORCE, value=10.0, unit="N", frame_id="frame1", interval_id="interval1", component="x", sign=1),
        _quantity("forceB", "fB", "force", "bodyB", FORCE, value=-6.0, unit="N", frame_id="frame1", interval_id="interval1", component="x", sign=1),
        _quantity("tensionA", "tA", "force", "bodyA", FORCE, frame_id="frame1", interval_id="interval1", component="x", sign=-1),
        _quantity("tensionB", "tB", "force", "bodyB", FORCE, frame_id="frame1", interval_id="interval1", component="x", sign=-1),
        _quantity("accelerationA", "aA", "acceleration", "bodyA", ACCELERATION, frame_id="frame1", interval_id="interval1", component="x", sign=1),
        _quantity("accelerationB", "aB", "acceleration", "bodyB", ACCELERATION, frame_id="frame1", interval_id="interval1", component="x", sign=1),
    ]
    rope_acceleration = Equality(
        left=Add(
            terms=(
                SymbolRef(symbol_id="aA", dimension=ACCELERATION),
                SymbolRef(symbol_id="aB", dimension=ACCELERATION),
            ),
            dimension=ACCELERATION,
        ),
        right=LiteralNode(value=0.0, dimension=ACCELERATION),
    )
    rope_tension = Equality(
        left=SymbolRef(symbol_id="tA", dimension=FORCE),
        right=SymbolRef(symbol_id="tB", dimension=FORCE),
    )
    return {
        "schema": IR_SCHEMA_NAME,
        "version": IR_SCHEMA_VERSION,
        "validation_policy_version": VALIDATION_POLICY_VERSION,
        "normalization_policy_version": NORMALIZATION_POLICY_VERSION,
        "metadata": {
            "language": "en",
            "correction_revision": 0,
            "system_type": "diagnostic_one",
            "subtype": "diagnostic_two",
            "model_id": "fixture",
            "model_hash": None,
            "prompt_hash": None,
            "source_text_sha256": None,
            "model_confidence": 0.5,
        },
        "source_assets": [],
        "source_evidence": [],
        "entities": [
            {"entity_id": "bodyA", "primitive": "particle", "label": "A", "aliases": [], "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None},
            {"entity_id": "bodyB", "primitive": "particle", "label": "B", "aliases": [], "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None},
            {"entity_id": "rope1", "primitive": "rope", "label": "connector", "aliases": [], "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None},
        ],
        "points": [],
        "reference_frames": [
            {
                "frame_id": "frame1",
                "frame_type": "cartesian_1d",
                "origin": {"kind": "world"},
                "axes": [{"axis": "x", "direction": {"kind": "axis", "frame_id": "frame1", "axis": "x", "sign": 1}}],
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
                "subject_ids": ["bodyA", "bodyB", "rope1"],
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
        "interactions": [
            {"interaction_id": "appliedA", "kind": "applied_force", "participant_ids": ["bodyA"], "point_ids": [], "frame_id": "frame1", "interval_id": "interval1", "event_id": None, "quantity_ids": ["forceA"], "evidence_refs": []},
            {"interaction_id": "appliedB", "kind": "applied_force", "participant_ids": ["bodyB"], "point_ids": [], "frame_id": "frame1", "interval_id": "interval1", "event_id": None, "quantity_ids": ["forceB"], "evidence_refs": []},
            {"interaction_id": "ropeForce", "kind": "rope_tension", "participant_ids": ["bodyA", "bodyB", "rope1"], "point_ids": [], "frame_id": "frame1", "interval_id": "interval1", "event_id": None, "quantity_ids": ["tensionA", "tensionB"], "evidence_refs": []},
        ],
        "constraints": [],
        "state_conditions": [],
        "queries": [
            {
                "query_id": "queryA",
                "target": {
                    "role": "acceleration",
                    "subject_id": "bodyA",
                    "point_id": None,
                    "frame_id": "frame1",
                    "interval_id": "interval1",
                    "event_id": None,
                    "component": "x",
                    "direction": None,
                    "target_quantity_id": "accelerationA",
                },
                "output_unit": "m/s^2",
                "output_dimension": ACCELERATION.model_dump(mode="json"),
                "shape": "scalar",
                "evidence_refs": [],
            }
        ],
        "principle_hints": [],
        "assumptions": [
            {
                "assumption_id": "masslessRope",
                "kind": "massless_rope",
                "subject_id": "rope1",
                "interval_id": "interval1",
                "disposition": "approved",
                "proposed_role": None,
                "proposed_value": None,
                "proposed_unit": None,
                "reason": "The connector mass is neglected.",
                "evidence_refs": [],
            },
            {
                "assumption_id": "fixedLengthRope",
                "kind": "inextensible_rope",
                "subject_id": "rope1",
                "interval_id": "interval1",
                "disposition": "approved",
                "proposed_role": None,
                "proposed_value": None,
                "proposed_unit": None,
                "reason": "The connector length is fixed.",
                "evidence_refs": [],
            },
        ],
        "ambiguities": [],
        "figure_dependency": {"level": "none", "missing_information": [], "evidence_refs": []},
        "unsupported_features": [],
    }


def _ir(payload: dict[str, object] | None = None) -> MechanicsProblemIRV1:
    return MechanicsProblemIRV1.model_validate(payload or _problem_payload())


def _authority_bundle(
    ir: MechanicsProblemIRV1,
) -> tuple[
    tuple[str, ...],
    dict[str, CorrectionAuthorization],
    dict[str, AssumptionAuthorization],
]:
    approved: set[str] = set()
    corrections: dict[str, CorrectionAuthorization] = {}
    assumptions: dict[str, AssumptionAuthorization] = {}
    approved.update(
        assumption.assumption_id
        for assumption in ir.assumptions
        if assumption.disposition.value == "approved"
    )
    for quantity in ir.quantities:
        if quantity.si_value is None:
            continue
        if quantity.provenance.value == "user_correction" and quantity.correction_id is not None:
            corrections[quantity.correction_id] = CorrectionAuthorization(
                correction_id=quantity.correction_id,
                subject_id=quantity.subject_id,
                role=quantity.role.value,
                raw_value=quantity.raw_value,
                raw_unit=quantity.raw_unit,
                interval_id=quantity.interval_id,
                event_id=quantity.event_id,
            )
        elif (
            quantity.provenance.value == "server_default"
            and quantity.assumption_policy_ref is not None
        ):
            assumptions[quantity.assumption_policy_ref] = AssumptionAuthorization(
                assumption_id=quantity.assumption_policy_ref,
                subject_id=quantity.subject_id,
                role=quantity.role.value,
                raw_value=quantity.raw_value,
                raw_unit=quantity.raw_unit,
                interval_id=quantity.interval_id,
            )
    return tuple(sorted(approved)), corrections, assumptions


def compile_mechanics_ir(
    ir: object,
    **kwargs: object,
):
    if type(ir) is not MechanicsProblemIRV1:
        return _compile_mechanics_ir(ir, **kwargs)
    approved, corrections, assumptions = _authority_bundle(ir)
    kwargs.setdefault("approved_assumption_ids", approved)
    kwargs.setdefault("authorized_corrections", corrections)
    kwargs.setdefault("authorized_assumptions", assumptions)
    kwargs.setdefault(
        "validated_ir_authorization", authorize_validated_mechanics_ir(ir)
    )
    return _compile_mechanics_ir(ir, **kwargs)


def _single_unknown_payload(expressions: list[Equality | Inequality]) -> dict[str, object]:
    payload = _problem_payload()
    payload["entities"] = [payload["entities"][0]]
    payload["reference_frames"] = []
    payload["motion_intervals"] = []
    payload["symbols"] = [_symbol("x", "positionX", LENGTH)]
    payload["quantities"] = [_quantity("positionX", "x", "position", "bodyA", LENGTH)]
    payload["interactions"] = []
    payload["assumptions"] = []
    payload["constraints"] = [
        _constraint(f"constraint{index}", expression, kind="boundary", subjects=("bodyA",))
        | {"interval_id": None}
        for index, expression in enumerate(expressions, start=1)
    ]
    payload["queries"] = [
        {
            "query_id": "queryX",
            "target": {
                "role": "position",
                "subject_id": "bodyA",
                "point_id": None,
                "frame_id": None,
                "interval_id": None,
                "event_id": None,
                "component": "unspecified",
                "direction": None,
                "target_quantity_id": "positionX",
            },
            "output_unit": "m",
            "output_dimension": LENGTH.model_dump(mode="json"),
            "shape": "scalar",
            "evidence_refs": [],
        }
    ]
    return payload


def _affine_relation_payload(*, inconsistent: bool) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["source_evidence"] = [
        {
            "kind": "text",
            "evidence_id": "evidence1",
            "quote": "The two coordinates obey the stated boundary relations.",
            "source_span": {"start": 0, "end": 56},
            "quantity_span": None,
            "occurrence_index": 0,
        }
    ]
    payload["symbols"] = [
        _symbol("x", "positionX", LENGTH),
        _symbol("y", "positionY", LENGTH),
        _symbol("c", "knownLength", LENGTH),
        _symbol("k2", "scaleTwo", DIMENSIONLESS),
        _symbol("k3", "scaleThree", DIMENSIONLESS),
    ]
    payload["quantities"] = [
        _quantity("positionX", "x", "position", "bodyA", LENGTH),
        _quantity("positionY", "y", "position", "bodyA", LENGTH),
        _quantity("knownLength", "c", "distance", "bodyA", LENGTH, value=4.0, unit="m"),
        _quantity("scaleTwo", "k2", "count", "bodyA", DIMENSIONLESS, value=2.0),
        _quantity("scaleThree", "k3", "count", "bodyA", DIMENSIONLESS, value=3.0),
    ]
    x = SymbolRef(symbol_id="x", dimension=LENGTH)
    y = SymbolRef(symbol_id="y", dimension=LENGTH)
    c = SymbolRef(symbol_id="c", dimension=LENGTH)
    k2 = SymbolRef(symbol_id="k2", dimension=DIMENSIONLESS)
    scale = SymbolRef(symbol_id="k3" if inconsistent else "k2", dimension=DIMENSIONLESS)
    equations = [
        Equality(left=Add(terms=(x, y), dimension=LENGTH), right=c),
        Equality(left=Subtract(left=x, right=y, dimension=LENGTH), right=c),
        Equality(
            left=Add(
                terms=(
                    Multiply(factors=(k2, x), dimension=LENGTH),
                    Multiply(factors=(k2, y), dimension=LENGTH),
                ),
                dimension=LENGTH,
            ),
            right=Multiply(factors=(scale, c), dimension=LENGTH),
        ),
    ]
    payload["constraints"] = [
        _constraint(f"relation{index}", expression, kind="boundary", subjects=("bodyA",))
        | {"interval_id": None, "evidence_refs": ["evidence1"]}
        for index, expression in enumerate(equations, start=1)
    ]
    return payload


def test_two_body_rope_and_newton_primitives_form_a_closed_graph() -> None:
    result = compile_mechanics_ir(_ir())
    assert result.status is CompilerStatus.ready and result.graph is not None
    assert result.graph.rank.unknown_count == 4
    assert result.graph.rank.structural_rank == 4
    assert len(result.graph.selected_equation_ids) == 4
    law_ids = {equation.law_id for equation in result.graph.equations}
    assert "particle_newton_second" in law_ids
    assert {"rope_massless_tension", "rope_inextensible_motion"}.issubset(law_ids)
    assert all("atwood" not in law_id.lower() for law_id in law_ids)


def test_repeat_permutation_and_diagnostic_changes_preserve_physical_graph() -> None:
    first = compile_mechanics_ir(_ir())
    repeated = compile_mechanics_ir(_ir())
    payload = _problem_payload()
    metadata = dict(payload["metadata"])
    metadata.update({"system_type": "wrong_label", "subtype": None, "model_id": "another_model"})
    payload["metadata"] = metadata
    for field in ("entities", "symbols", "quantities", "interactions", "constraints", "assumptions"):
        payload[field] = list(reversed(payload[field]))
    changed = compile_mechanics_ir(_ir(payload))
    assert first.graph is not None and repeated.graph is not None and changed.graph is not None
    assert first.graph.fingerprint == repeated.graph.fingerprint == changed.graph.fingerprint
    assert first.graph.selected_equation_ids == repeated.graph.selected_equation_ids == changed.graph.selected_equation_ids
    assert tuple(item.equation_id for item in first.graph.equations) == tuple(item.equation_id for item in changed.graph.equations)


def _rename(value: object, mapping: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {key: _rename(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_rename(item, mapping) for item in value]
    if isinstance(value, tuple):
        return tuple(_rename(item, mapping) for item in value)
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def test_consistent_identifier_rename_preserves_equation_identities_and_fingerprint() -> None:
    original = compile_mechanics_ir(_ir())
    mapping = {
        "bodyA": "objectLeft", "bodyB": "objectRight", "rope1": "connectorNew",
        "frame1": "axisFrame", "interval1": "motionWindow", "queryA": "targetQuery",
        "massA": "quantityMassLeft", "massB": "quantityMassRight",
        "forceA": "quantityForceLeft", "forceB": "quantityForceRight",
        "tensionA": "quantityTensionLeft", "tensionB": "quantityTensionRight",
        "accelerationA": "quantityAccelLeft", "accelerationB": "quantityAccelRight",
        "mA": "symbolMassLeft", "mB": "symbolMassRight", "fA": "symbolForceLeft", "fB": "symbolForceRight",
        "tA": "symbolTensionLeft", "tB": "symbolTensionRight", "aA": "symbolAccelLeft", "aB": "symbolAccelRight",
        "appliedA": "interactionLeft", "appliedB": "interactionRight", "ropeForce": "interactionConnector",
        "masslessRope": "assumptionMassless", "fixedLengthRope": "assumptionFixedLength",
    }
    renamed_payload = _rename(_problem_payload(), mapping)
    renamed = compile_mechanics_ir(_ir(renamed_payload))
    assert original.graph is not None and renamed.graph is not None
    assert original.status == renamed.status == CompilerStatus.ready
    assert original.graph.fingerprint == renamed.graph.fingerprint
    assert original.graph.selected_equation_ids == renamed.graph.selected_equation_ids
    assert tuple(item.equation_id for item in original.graph.equations) == tuple(item.equation_id for item in renamed.graph.equations)


def test_irrelevant_unconnected_fact_does_not_change_query_component() -> None:
    original = compile_mechanics_ir(_ir())
    payload = _problem_payload()
    payload["entities"].append({"entity_id": "bodyC", "primitive": "particle", "label": "unused", "aliases": [], "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None})
    payload["symbols"].append(_symbol("mC", "massC", MASS))
    payload["quantities"].append(_quantity("massC", "mC", "mass", "bodyC", MASS, value=99.0, unit="kg"))
    changed = compile_mechanics_ir(_ir(payload))
    assert original.graph is not None and changed.graph is not None
    assert original.graph.fingerprint == changed.graph.fingerprint
    assert original.graph.selected_equation_ids == changed.graph.selected_equation_ids


def test_same_body_inapplicable_fact_does_not_change_equation_identities() -> None:
    original = compile_mechanics_ir(_ir())
    payload = _problem_payload()
    payload["symbols"].append(_symbol("unusedScalar", "unusedQuantity", DIMENSIONLESS))
    payload["quantities"].append(
        _quantity(
            "unusedQuantity",
            "unusedScalar",
            "other",
            "bodyA",
            DIMENSIONLESS,
            value=7.0,
        )
    )
    changed = compile_mechanics_ir(_ir(payload))
    assert original.graph is not None and changed.graph is not None
    assert original.graph.fingerprint == changed.graph.fingerprint
    assert tuple(item.equation_id for item in original.graph.equations) == tuple(
        item.equation_id for item in changed.graph.equations
    )


def test_equivalent_normalized_value_ignores_source_unit_spelling() -> None:
    original = compile_mechanics_ir(_ir())
    payload = _problem_payload()
    mass = next(item for item in payload["quantities"] if item["quantity_id"] == "massA")
    mass["raw_value"] = "2000"
    mass["raw_unit"] = "g"
    changed = compile_mechanics_ir(_ir(payload))
    assert original.graph is not None and changed.graph is not None
    assert original.graph.fingerprint == changed.graph.fingerprint
    assert original.graph.selected_equation_ids == changed.graph.selected_equation_ids


def test_generated_query_symbol_is_dimension_and_shape_bound() -> None:
    payload = _problem_payload()
    payload["entities"] = [payload["entities"][0]]
    payload["symbols"] = [item for item in payload["symbols"] if item["symbol_id"] in {"mA", "fA"}]
    payload["quantities"] = [item for item in payload["quantities"] if item["quantity_id"] in {"massA", "forceA"}]
    payload["interactions"] = [payload["interactions"][0]]
    payload["constraints"] = []
    payload["assumptions"] = []
    payload["motion_intervals"][0]["subject_ids"] = ["bodyA"]
    payload["queries"][0]["target"]["target_quantity_id"] = None
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.ready and result.graph is not None
    query_symbol = next(item for item in result.graph.symbols if item.symbol.symbol_id == result.graph.query_symbol_id)
    assert query_symbol.generated and query_symbol.symbol.dimension == ACCELERATION
    assert query_symbol.symbol.shape.value == "scalar"
    assert query_symbol.symbol.vector_length is None
    assert query_symbol.quantity_role == "acceleration"
    assert len(result.graph.selected_equation_ids) == 1


def test_malformed_symbol_reference_and_dimension_mismatch_fail_closed() -> None:
    missing = Equality(
        left=SymbolRef(symbol_id="missing", dimension=LENGTH),
        right=LiteralNode(value=1.0, dimension=LENGTH),
    )
    missing_result = compile_mechanics_ir(_ir(_single_unknown_payload([missing])))
    assert missing_result.status is CompilerStatus.invalid
    assert missing_result.issues[0].code is CompilerIssueCode.invalid_expression

    mismatch = Equality(
        left=SymbolRef(symbol_id="x", dimension=LENGTH),
        right=LiteralNode(value=1.0, dimension=TIME),
    )
    mismatch_result = compile_mechanics_ir(_ir(_single_unknown_payload([mismatch])))
    assert mismatch_result.status is CompilerStatus.invalid
    assert mismatch_result.issues[0].code is CompilerIssueCode.dimension_mismatch


def test_direct_query_value_injection_is_nonclosing() -> None:
    x = SymbolRef(symbol_id="x", dimension=LENGTH)
    injected = compile_mechanics_ir(
        _ir(
            _single_unknown_payload(
                [Equality(left=x, right=LiteralNode(value=1.0, dimension=LENGTH))]
            )
        )
    )
    assert injected.status is CompilerStatus.underdetermined and injected.graph is not None
    assert injected.graph.rank.equality_count == 0
    assert CompilerIssueCode.constraint_not_authoritative in {item.code for item in injected.issues}


def test_indirect_two_unknown_injection_cannot_borrow_a_server_equation() -> None:
    payload = _single_unknown_payload([])
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "restEvidence",
        "quote": "Only the auxiliary coordinate is at rest.",
        "source_span": {"start": 0, "end": 41}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["symbols"] = [
        _symbol("x", "velocityX", VELOCITY),
        _symbol("y", "velocityY", VELOCITY),
    ]
    payload["quantities"] = [
        _quantity("velocityX", "x", "velocity", "bodyA", VELOCITY),
        _quantity("velocityY", "y", "velocity", "bodyA", VELOCITY),
    ]
    payload["constraints"] = [
        _constraint(
            "injectedRelation",
            Equality(
                left=SymbolRef(symbol_id="x", dimension=VELOCITY),
                right=SymbolRef(symbol_id="y", dimension=VELOCITY),
            ),
            kind="boundary",
            subjects=("bodyA",),
        )
        | {"interval_id": None, "evidence_refs": ["restEvidence"]}
    ]
    payload["state_conditions"] = [{
        "state_condition_id": "auxiliaryRest", "kind": "motion", "state": "at_rest",
        "subject_id": "bodyA", "interval_id": None, "event_id": None,
        "expression": None, "quantity_ids": ["velocityY"], "evidence_refs": ["restEvidence"],
    }]
    payload["queries"][0]["target"].update(
        {"role": "velocity", "target_quantity_id": "velocityX"}
    )
    payload["queries"][0]["output_unit"] = "m/s"
    payload["queries"][0]["output_dimension"] = VELOCITY.model_dump(mode="json")
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.underdetermined and result.graph is not None
    assert result.graph.rank.equality_count == 0
    assert "explicit_constraint" not in {item.law_id for item in result.graph.equations}


def test_explicit_inequality_merges_point_topology_and_rejects_incompatible_scope() -> None:
    payload = _single_unknown_payload([])
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "pointBoundEvidence",
        "quote": "Point P remains on the nonnegative side.",
        "source_span": {"start": 0, "end": 40}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["points"] = [{
        "point_id": "pointP", "role": "material", "owner_entity_id": "bodyA",
        "frame_id": None, "label": "P", "evidence_refs": ["pointBoundEvidence"],
    }]
    payload["quantities"][0]["point_id"] = "pointP"
    payload["queries"][0]["target"]["point_id"] = "pointP"
    inequality = Inequality(
        relation=InequalityRelation.ge,
        left=SymbolRef(symbol_id="x", dimension=LENGTH),
        right=LiteralNode(value=0.0, dimension=LENGTH),
    )
    payload["constraints"] = [
        _constraint("pointBound", inequality, kind="boundary", subjects=("bodyA",))
        | {"interval_id": None, "evidence_refs": ["pointBoundEvidence"]}
    ]
    result = compile_mechanics_ir(_ir(payload))
    assert result.graph is not None
    node = next(item for item in result.graph.constraints if item.constraint_id == "pointBound")
    assert node.scope.entity_ids == ("bodyA",)
    assert node.scope.point_ids == ("pointP",)

    incompatible = deepcopy(payload)
    incompatible["entities"].append({
        "entity_id": "bodyB", "primitive": "particle", "label": "B", "aliases": [],
        "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None,
    })
    incompatible["constraints"][0]["subject_ids"] = ["bodyB"]
    rejected = compile_mechanics_ir(_ir(incompatible))
    assert rejected.status is CompilerStatus.invalid and rejected.graph is None
    assert rejected.issues[0].code is CompilerIssueCode.invalid_binding


def _known_query_payload(provenance: str) -> dict[str, object]:
    payload = _single_unknown_payload([])
    evidence: tuple[str, ...] = ()
    correction_id = None
    policy_id = None
    if provenance == "explicit_source":
        payload["source_evidence"] = [{
            "kind": "text", "evidence_id": "valueEvidence", "quote": "The position is 2 m.",
            "source_span": {"start": 0, "end": 20}, "quantity_span": {"start": 16, "end": 19},
            "occurrence_index": 0,
        }]
        evidence = ("valueEvidence",)
    elif provenance == "user_correction":
        correction_id = "correctionPosition"
    elif provenance in {"server_default", "inferred"}:
        policy_id = "positionPolicy"
        payload["assumptions"] = [{
            "assumption_id": policy_id, "kind": "trusted_position_default",
            "subject_id": "bodyA", "interval_id": None, "disposition": "approved",
            "proposed_role": "position", "proposed_value": "2.0", "proposed_unit": "m",
            "reason": "Server-authorized fixture value.", "evidence_refs": [],
        }]
    payload["quantities"] = [
        _quantity(
            "positionX", "x", "position", "bodyA", LENGTH,
            value=2.0, unit="m", provenance=provenance, evidence_refs=evidence,
            correction_id=correction_id, assumption_policy_ref=policy_id,
        )
    ]
    return payload


@pytest.mark.parametrize("provenance", ["explicit_source", "user_correction", "server_default"])
def test_every_trusted_known_provenance_closes_only_with_its_authority(provenance: str) -> None:
    result = compile_mechanics_ir(_ir(_known_query_payload(provenance)))
    assert result.status is CompilerStatus.ready and result.graph is not None
    assert result.graph.rank.unknown_count == 0


def test_compile_time_authority_rechecks_si_and_exact_external_records() -> None:
    for provenance in ("explicit_source", "user_correction", "server_default"):
        payload = _known_query_payload(provenance)
        payload["quantities"][0]["si_value"] = 9.0
        forged = compile_mechanics_ir(_ir(payload))
        assert forged.status is CompilerStatus.invalid and forged.graph is None
        assert forged.issues[0].code is CompilerIssueCode.invalid_binding

    corrected_ir = _ir(_known_query_payload("user_correction"))
    approved, corrections, assumptions = _authority_bundle(corrected_ir)
    exact = _compile_mechanics_ir(
        corrected_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(corrected_ir),
        approved_assumption_ids=approved,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert exact.status is CompilerStatus.ready and exact.graph is not None

    absent = _compile_mechanics_ir(
        corrected_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(corrected_ir),
    )
    assert absent.status is CompilerStatus.invalid and absent.graph is None
    assert absent.issues[0].code is CompilerIssueCode.invalid_binding

    correction = next(iter(corrections.values()))
    mismatched = _compile_mechanics_ir(
        corrected_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(corrected_ir),
        authorized_corrections={
            correction.correction_id: CorrectionAuthorization(
                correction_id=correction.correction_id,
                subject_id=correction.subject_id,
                role=correction.role,
                raw_value="3.0",
                raw_unit=correction.raw_unit,
                interval_id=correction.interval_id,
                event_id=correction.event_id,
            )
        },
    )
    assert mismatched.status is CompilerStatus.invalid and mismatched.graph is None

    bogus_payload = _known_query_payload("user_correction")
    bogus_payload["quantities"][0]["correction_id"] = "bogusCorrection"
    bogus_ir = _ir(bogus_payload)
    bogus = _compile_mechanics_ir(
        bogus_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(bogus_ir),
        authorized_corrections=corrections,
    )
    assert bogus.status is CompilerStatus.invalid and bogus.graph is None

    default_ir = _ir(_known_query_payload("server_default"))
    approved, corrections, assumptions = _authority_bundle(default_ir)
    exact_default = _compile_mechanics_ir(
        default_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(default_ir),
        approved_assumption_ids=approved,
        authorized_assumptions=assumptions,
    )
    assert exact_default.status is CompilerStatus.ready and exact_default.graph is not None
    missing_default = _compile_mechanics_ir(
        default_ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(default_ir),
        approved_assumption_ids=approved,
    )
    assert missing_default.status is CompilerStatus.invalid and missing_default.graph is None


def test_validated_ir_authorization_is_required_and_binds_the_full_ir_payload() -> None:
    original_ir = _ir(_known_query_payload("explicit_source"))
    original_seal = authorize_validated_mechanics_ir(original_ir)
    approved, corrections, assumptions = _authority_bundle(original_ir)
    exact = _compile_mechanics_ir(
        original_ir,
        validated_ir_authorization=original_seal,
        approved_assumption_ids=approved,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert exact.status is CompilerStatus.ready and exact.graph is not None

    missing = _compile_mechanics_ir(
        original_ir,
        approved_assumption_ids=approved,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert missing.status is CompilerStatus.invalid and missing.graph is None
    assert missing.issues[0].code is CompilerIssueCode.invalid_binding

    mutated_payload = _known_query_payload("explicit_source")
    mutated_quantity = mutated_payload["quantities"][0]
    normalized = normalize_quantity("9.0", "m", "scalar", LENGTH)
    mutated_quantity.update(
        {
            "raw_value": "9.0",
            "raw_unit": "m",
            "si_value": normalized.value,
            "si_unit": normalized.si_unit,
        }
    )
    mutated_ir = _ir(mutated_payload)
    rejected = _compile_mechanics_ir(
        mutated_ir,
        validated_ir_authorization=original_seal,
        approved_assumption_ids=approved,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert rejected.status is CompilerStatus.invalid and rejected.graph is None
    assert rejected.issues[0].code is CompilerIssueCode.invalid_binding

    forged = _compile_mechanics_ir(
        original_ir,
        validated_ir_authorization=ValidatedIRAuthorization(ir_sha256="0" * 64),
        approved_assumption_ids=approved,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert forged.status is CompilerStatus.invalid and forged.graph is None


def test_general_assumptions_require_external_id_approval_for_laws_and_routing() -> None:
    ir = _ir()
    _, corrections, assumptions = _authority_bundle(ir)
    seal = authorize_validated_mechanics_ir(ir)
    missing = _compile_mechanics_ir(
        ir,
        validated_ir_authorization=seal,
        approved_assumption_ids=(),
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert missing.graph is not None
    assert {"rope_massless_tension", "rope_inextensible_motion"}.isdisjoint(
        item.law_id for item in missing.graph.equations
    )
    assert all(not item.assumption_ids for item in missing.graph.equations)

    mismatched = _compile_mechanics_ir(
        ir,
        validated_ir_authorization=seal,
        approved_assumption_ids=("unrelatedAuthority",),
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert mismatched.graph is not None
    assert {"rope_massless_tension", "rope_inextensible_motion"}.isdisjoint(
        item.law_id for item in mismatched.graph.equations
    )

    restored = _compile_mechanics_ir(
        ir,
        validated_ir_authorization=seal,
        approved_assumption_ids=("fixedLengthRope", "masslessRope"),
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert restored.status is CompilerStatus.ready and restored.graph is not None
    assert {"rope_massless_tension", "rope_inextensible_motion"}.issubset(
        item.law_id for item in restored.graph.equations
    )

    variable_payload = _constant_work_payload()
    variable_payload["assumptions"].append(
        variable_payload["assumptions"][0]
        | {"assumption_id": "variableForce", "kind": "force_depends_on_position"}
    )
    variable_ir = _ir(variable_payload)
    variable_seal = authorize_validated_mechanics_ir(variable_ir)
    _, variable_corrections, variable_defaults = _authority_bundle(variable_ir)
    ignored = _compile_mechanics_ir(
        variable_ir,
        validated_ir_authorization=variable_seal,
        approved_assumption_ids=("constantForce",),
        authorized_corrections=variable_corrections,
        authorized_assumptions=variable_defaults,
    )
    assert ignored.status is CompilerStatus.ready and ignored.graph is not None
    assert "force_work" in {item.law_id for item in ignored.graph.equations}
    assert all(
        "variableForce" not in item.assumption_ids for item in ignored.graph.equations
    )

    routed = _compile_mechanics_ir(
        variable_ir,
        validated_ir_authorization=variable_seal,
        approved_assumption_ids=("constantForce", "variableForce"),
        authorized_corrections=variable_corrections,
        authorized_assumptions=variable_defaults,
    )
    assert routed.status is CompilerStatus.unsupported and routed.graph is None
    assert routed.issues[0].code is CompilerIssueCode.requires_specialized_model


@pytest.mark.parametrize("provenance", ["inferred", "unknown"])
def test_inferred_and_unknown_numeric_values_never_gain_known_authority(provenance: str) -> None:
    result = compile_mechanics_ir(_ir(_known_query_payload(provenance)))
    assert result.status is CompilerStatus.invalid and result.graph is None
    assert result.issues[0].code is CompilerIssueCode.invalid_binding


@pytest.mark.parametrize("provenance", ["explicit_source", "user_correction", "server_default", "inferred", "unknown"])
def test_forged_or_evidence_less_known_value_fails_closed(provenance: str) -> None:
    payload = _known_query_payload(provenance)
    quantity = payload["quantities"][0]
    quantity["evidence_refs"] = []
    quantity["correction_id"] = None
    quantity["assumption_policy_ref"] = None
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.invalid and result.graph is None
    assert result.issues[0].code is CompilerIssueCode.invalid_binding


def test_supported_quadratic_is_deferred_but_unknown_denominator_is_rejected() -> None:
    quadratic = _single_unknown_payload([])
    quadratic["symbols"] = [
        _symbol("omega", "frequencyQ", FREQUENCY),
        _symbol("mass", "massQ", MASS),
        _symbol("stiffness", "stiffnessQ", STIFFNESS),
    ]
    quadratic["quantities"] = [
        _quantity("frequencyQ", "omega", "frequency", "bodyA", FREQUENCY),
        _quantity("massQ", "mass", "mass", "bodyA", MASS, value=2.0, unit="kg"),
        _quantity("stiffnessQ", "stiffness", "stiffness", "bodyA", STIFFNESS, value=8.0, unit="N/m"),
    ]
    quadratic["assumptions"] = [{
        "assumption_id": "frequencyAuthority", "kind": "angular_natural_frequency",
        "subject_id": "bodyA", "interval_id": None, "disposition": "approved",
        "proposed_role": None, "proposed_value": None, "proposed_unit": None,
        "reason": "Angular frequency is requested.", "evidence_refs": [],
    }]
    quadratic["queries"][0]["target"].update(
        {"role": "frequency", "target_quantity_id": "frequencyQ"}
    )
    quadratic["queries"][0]["output_unit"] = "1/s"
    quadratic["queries"][0]["output_dimension"] = FREQUENCY.model_dump(mode="json")
    supported = compile_mechanics_ir(_ir(quadratic))
    assert supported.status is CompilerStatus.ready and supported.graph is not None
    assert CompilerIssueCode.nonlinear_verification_deferred in {item.code for item in supported.issues}

    rational = _single_unknown_payload([])
    rational["symbols"] = [
        _symbol("a", "accelerationQ", ACCELERATION),
        _symbol("v", "speedQ", VELOCITY),
        _symbol("r", "radiusQ", LENGTH),
    ]
    rational["quantities"] = [
        _quantity("accelerationQ", "a", "acceleration", "bodyA", ACCELERATION, component="normal"),
        _quantity("speedQ", "v", "speed", "bodyA", VELOCITY, component="magnitude"),
        _quantity("radiusQ", "r", "radius", "bodyA", LENGTH),
    ]
    rational["queries"][0]["target"].update(
        {"role": "acceleration", "component": "normal", "target_quantity_id": "accelerationQ"}
    )
    rational["queries"][0]["output_unit"] = "m/s^2"
    rational["queries"][0]["output_dimension"] = ACCELERATION.model_dump(mode="json")
    unsupported = compile_mechanics_ir(_ir(rational))
    assert unsupported.status is CompilerStatus.unsupported and unsupported.graph is not None
    assert CompilerIssueCode.consistency_inconclusive in {item.code for item in unsupported.issues}

    zero_radius = deepcopy(rational)
    radius = next(item for item in zero_radius["quantities"] if item["quantity_id"] == "radiusQ")
    radius.update(_quantity("radiusQ", "r", "radius", "bodyA", LENGTH, value=0.0, unit="m"))
    zero = compile_mechanics_ir(_ir(zero_radius))
    assert zero.status is CompilerStatus.invalid and zero.graph is None
    assert zero.issues[0].code is CompilerIssueCode.invalid_domain

    wrong_component = deepcopy(rational)
    next(item for item in wrong_component["quantities"] if item["quantity_id"] == "speedQ")["component"] = "x"
    rejected_component = compile_mechanics_ir(_ir(wrong_component))
    assert rejected_component.status is CompilerStatus.underdetermined
    assert rejected_component.graph is not None
    assert "particle_normal_acceleration" not in {
        item.law_id for item in rejected_component.graph.equations
    }

    average_power = _single_unknown_payload([])
    average_power["symbols"] = [
        _symbol("power", "powerQ", POWER_DIMENSION),
        _symbol("work", "workQ", ENERGY),
        _symbol("duration", "durationQ", TIME),
    ]
    average_power["quantities"] = [
        _quantity("powerQ", "power", "power", "bodyA", POWER_DIMENSION),
        _quantity("workQ", "work", "work", "bodyA", ENERGY, value=10.0, unit="J"),
        _quantity("durationQ", "duration", "duration", "bodyA", TIME, value=2.0, unit="s"),
    ]
    average_power["queries"][0]["target"].update(
        {"role": "power", "target_quantity_id": "powerQ"}
    )
    average_power["queries"][0]["output_unit"] = "W"
    average_power["queries"][0]["output_dimension"] = POWER_DIMENSION.model_dump(mode="json")
    safe_power = compile_mechanics_ir(_ir(average_power))
    assert safe_power.status is CompilerStatus.ready and safe_power.graph is not None

    zero_duration = deepcopy(average_power)
    zero_duration["quantities"][-1] = _quantity(
        "durationQ", "duration", "duration", "bodyA", TIME, value=0.0, unit="s"
    )
    zero_power = compile_mechanics_ir(_ir(zero_duration))
    assert zero_power.status is CompilerStatus.invalid and zero_power.graph is None
    assert zero_power.issues[0].code is CompilerIssueCode.invalid_domain

    unknown_duration = deepcopy(average_power)
    unknown_duration["quantities"][-1] = _quantity(
        "durationQ", "duration", "duration", "bodyA", TIME
    )
    unsafe_power = compile_mechanics_ir(_ir(unknown_duration))
    assert unsafe_power.status is CompilerStatus.unsupported and unsafe_power.graph is None
    assert unsafe_power.issues[0].code is CompilerIssueCode.domain_unproven


def _constant_acceleration_payload(displacement_component: str) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["reference_frames"] = [{
        "frame_id": "motionFrame", "frame_type": "cartesian_1d", "origin": {"kind": "world"},
        "axes": [{"axis": "x", "direction": {"kind": "axis", "frame_id": "motionFrame", "axis": "x", "sign": 1}}],
        "parent_frame_id": None, "translating_with_entity_id": None,
        "rotating_about_point_id": None, "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }]
    payload["motion_intervals"] = [{
        "interval_id": "motionInterval", "order": 1, "subject_ids": ["bodyA"],
        "frame_id": "motionFrame", "start_event_id": "motionStart",
        "end_event_id": "motionEnd", "evidence_refs": [],
    }]
    payload["events"] = [
        {"event_id": "motionStart", "kind": "start", "subject_ids": ["bodyA"], "interval_ids": ["motionInterval"], "time_quantity_id": None, "evidence_refs": []},
        {"event_id": "motionEnd", "kind": "finish", "subject_ids": ["bodyA"], "interval_ids": ["motionInterval"], "time_quantity_id": None, "evidence_refs": []},
    ]
    payload["symbols"] = [
        _symbol("deltaX", "displacementQ", LENGTH),
        _symbol("vStart", "startVelocityQ", VELOCITY),
        _symbol("vEnd", "endVelocityQ", VELOCITY),
        _symbol("accel", "accelerationQ", ACCELERATION),
        _symbol("duration", "durationQ", TIME),
    ]
    payload["quantities"] = [
        _quantity("displacementQ", "deltaX", "displacement", "bodyA", LENGTH, frame_id="motionFrame", interval_id="motionInterval", component=displacement_component),
        _quantity("startVelocityQ", "vStart", "velocity", "bodyA", VELOCITY, value=1.0, unit="m/s", frame_id="motionFrame", interval_id="motionInterval", event_id="motionStart", component="x"),
        _quantity("endVelocityQ", "vEnd", "velocity", "bodyA", VELOCITY, frame_id="motionFrame", interval_id="motionInterval", event_id="motionEnd", component="x"),
        _quantity("accelerationQ", "accel", "acceleration", "bodyA", ACCELERATION, value=2.0, unit="m/s^2", frame_id="motionFrame", interval_id="motionInterval", component="x"),
        _quantity("durationQ", "duration", "duration", "bodyA", TIME, value=3.0, unit="s", interval_id="motionInterval"),
    ]
    payload["assumptions"] = [{
        "assumption_id": "constantAcceleration", "kind": "constant_acceleration",
        "subject_id": "bodyA", "interval_id": "motionInterval", "disposition": "approved",
        "proposed_role": None, "proposed_value": None, "proposed_unit": None,
        "reason": "Acceleration is constant over the interval.", "evidence_refs": [],
    }]
    payload["queries"][0]["target"].update({
        "role": "displacement", "frame_id": "motionFrame", "interval_id": "motionInterval",
        "event_id": None, "component": displacement_component, "target_quantity_id": "displacementQ",
    })
    payload["queries"][0]["output_unit"] = "m"
    payload["queries"][0]["output_dimension"] = LENGTH.model_dump(mode="json")
    return payload


def test_constant_acceleration_displacement_requires_exact_component_topology() -> None:
    compatible = compile_mechanics_ir(_ir(_constant_acceleration_payload("x")))
    assert compatible.graph is not None
    equations = [
        item
        for item in compatible.graph.equations
        if item.law_id == "particle_constant_acceleration_position"
    ]
    assert len(equations) == 1 and isinstance(equations[0].expression.right, Add)

    incompatible = compile_mechanics_ir(_ir(_constant_acceleration_payload("y")))
    assert incompatible.status is CompilerStatus.underdetermined
    assert incompatible.graph is not None
    assert "particle_constant_acceleration_position" not in {
        item.law_id for item in incompatible.graph.equations
    }


def _kinetic_payload(mode: str, *, rigid: bool = False) -> dict[str, object]:
    payload = _single_unknown_payload([])
    two_dimensional = mode in {"vector", "components"} or rigid
    payload["entities"][0]["primitive"] = "rigid_body" if rigid else "particle"
    payload["reference_frames"] = [{
        "frame_id": "energyFrame",
        "frame_type": "cartesian_2d" if two_dimensional else "cartesian_1d",
        "origin": {"kind": "world"},
        "axes": [
            {"axis": "x", "direction": {"kind": "axis", "frame_id": "energyFrame", "axis": "x", "sign": 1}},
            *([{"axis": "y", "direction": {"kind": "axis", "frame_id": "energyFrame", "axis": "y", "sign": 1}}] if two_dimensional else []),
        ],
        "parent_frame_id": None, "translating_with_entity_id": None,
        "rotating_about_point_id": None, "generalized_coordinate_symbol_ids": [],
        "evidence_refs": [],
    }]
    payload["points"] = ([{
        "point_id": "centerPoint", "role": "mass_center", "owner_entity_id": "bodyA",
        "frame_id": "energyFrame", "label": "G", "evidence_refs": [],
    }] if rigid else [])
    payload["symbols"] = [
        _symbol("energy", "energyQ", ENERGY),
        _symbol("mass", "massQ", MASS),
    ]
    payload["quantities"] = [
        _quantity("energyQ", "energy", "energy", "bodyA", ENERGY, frame_id="energyFrame"),
        _quantity("massQ", "mass", "mass", "bodyA", MASS, value=2.0, unit="kg"),
    ]
    point_id = "centerPoint" if rigid else None
    if mode == "vector":
        payload["symbols"].append({
            "symbol_id": "velocity", "quantity_id": "velocityQ",
            "dimension": VELOCITY.model_dump(mode="json"), "shape": "vector", "vector_length": 2,
        })
        vector = _quantity("velocityQ", "velocity", "velocity", "bodyA", VELOCITY, value=0.0, unit="m/s", frame_id="energyFrame", point_id=point_id)
        normalized = normalize_quantity("3,4", "m/s", "vector", VELOCITY)
        vector.update({
            "shape": "vector", "raw_value": "3,4", "si_value": normalized.value,
            "si_unit": normalized.si_unit,
        })
        payload["quantities"].append(vector)
    elif mode == "speed":
        payload["symbols"].append(_symbol("speed", "speedQ", VELOCITY))
        payload["quantities"].append(
            _quantity("speedQ", "speed", "speed", "bodyA", VELOCITY, value=5.0, unit="m/s", frame_id="energyFrame", point_id=point_id, component="magnitude")
        )
    elif mode == "scalar1d":
        payload["symbols"].append(_symbol("velocity", "velocityQ", VELOCITY))
        payload["quantities"].append(
            _quantity("velocityQ", "velocity", "velocity", "bodyA", VELOCITY, value=5.0, unit="m/s", frame_id="energyFrame", point_id=point_id, component="x")
        )
    else:
        payload["symbols"].extend([
            _symbol("velocityX", "velocityXQ", VELOCITY),
            _symbol("velocityY", "velocityYQ", VELOCITY),
        ])
        payload["quantities"].extend([
            _quantity("velocityXQ", "velocityX", "velocity", "bodyA", VELOCITY, value=3.0, unit="m/s", frame_id="energyFrame", point_id=point_id, component="x"),
            _quantity("velocityYQ", "velocityY", "velocity", "bodyA", VELOCITY, value=4.0, unit="m/s", frame_id="energyFrame", point_id=point_id, component="y"),
        ])
    if rigid:
        payload["symbols"].extend([
            _symbol("inertia", "inertiaQ", MOMENT_OF_INERTIA),
            _symbol("omega", "omegaQ", FREQUENCY),
        ])
        payload["quantities"].extend([
            _quantity("inertiaQ", "inertia", "moment_of_inertia", "bodyA", MOMENT_OF_INERTIA, value=1.0, unit="kg*m^2", frame_id="energyFrame", point_id="centerPoint"),
            _quantity("omegaQ", "omega", "angular_velocity", "bodyA", FREQUENCY, value=2.0, unit="rad/s", frame_id="energyFrame", point_id="centerPoint"),
        ])
    payload["assumptions"] = [{
        "assumption_id": "kineticAuthority", "kind": "kinetic_energy", "subject_id": "bodyA",
        "interval_id": None, "disposition": "approved", "proposed_role": None,
        "proposed_value": None, "proposed_unit": None, "reason": "Use kinetic energy.",
        "evidence_refs": [],
    }]
    payload["queries"][0]["target"].update({
        "role": "energy", "frame_id": "energyFrame", "component": "unspecified",
        "target_quantity_id": "energyQ",
    })
    payload["queries"][0]["output_unit"] = "J"
    payload["queries"][0]["output_dimension"] = ENERGY.model_dump(mode="json")
    return payload


@pytest.mark.parametrize("mode", ["vector", "speed", "scalar1d"])
def test_particle_kinetic_energy_accepts_one_full_speed_representation(mode: str) -> None:
    result = compile_mechanics_ir(_ir(_kinetic_payload(mode)))
    assert result.status is CompilerStatus.ready and result.graph is not None
    equations = [item for item in result.graph.equations if item.law_id == "kinetic_energy"]
    assert len(equations) == 1
    factors = equations[0].expression.right.factors
    assert any(isinstance(item, Dot) for item in factors) is (mode == "vector")


def test_kinetic_energy_rejects_2d_scalar_components_and_rigid_vector_uses_one_dot() -> None:
    components = compile_mechanics_ir(_ir(_kinetic_payload("components")))
    assert components.status is CompilerStatus.underdetermined and components.graph is not None
    assert "kinetic_energy" not in {item.law_id for item in components.graph.equations}

    rigid = compile_mechanics_ir(_ir(_kinetic_payload("vector", rigid=True)))
    assert rigid.status is CompilerStatus.ready and rigid.graph is not None
    equations = [item for item in rigid.graph.equations if item.law_id == "rigid_kinetic_energy"]
    assert len(equations) == 1
    translational = next(item for item in equations[0].expression.right.terms if isinstance(item, Multiply) and any(isinstance(factor, Dot) for factor in item.factors))
    assert sum(isinstance(item, Dot) for item in translational.factors) == 1


def _constant_work_payload() -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["symbols"] = [
        _symbol("work", "workQ", ENERGY),
        _symbol("force", "forceQ", FORCE),
        _symbol("distance", "distanceQ", LENGTH),
    ]
    payload["quantities"] = [
        _quantity("workQ", "work", "work", "bodyA", ENERGY),
        _quantity("forceQ", "force", "force", "bodyA", FORCE, value=3.0, unit="N", component="x"),
        _quantity("distanceQ", "distance", "displacement", "bodyA", LENGTH, value=4.0, unit="m", component="x"),
    ]
    payload["interactions"] = [{
        "interaction_id": "workInteraction", "kind": "applied_force",
        "participant_ids": ["bodyA"], "point_ids": [], "frame_id": None,
        "interval_id": None, "event_id": None,
        "quantity_ids": ["workQ", "forceQ", "distanceQ"], "evidence_refs": [],
    }]
    payload["assumptions"] = [{
        "assumption_id": "constantForce", "kind": "constant_force", "subject_id": "bodyA",
        "interval_id": None, "disposition": "approved", "proposed_role": None,
        "proposed_value": None, "proposed_unit": None,
        "reason": "The applied force is constant.", "evidence_refs": [],
    }]
    payload["queries"][0]["target"].update(
        {"role": "work", "component": "unspecified", "target_quantity_id": "workQ"}
    )
    payload["queries"][0]["output_unit"] = "J"
    payload["queries"][0]["output_dimension"] = ENERGY.model_dump(mode="json")
    return payload


def test_work_template_requires_exact_constant_authority_and_never_emits_conflicting_forms() -> None:
    constant = compile_mechanics_ir(_ir(_constant_work_payload()))
    assert constant.status is CompilerStatus.ready and constant.graph is not None
    work_equations = [item for item in constant.graph.equations if item.law_id in {"force_work", "variable_force_work"}]
    assert len(work_equations) == 1 and work_equations[0].law_id == "force_work"
    assert work_equations[0].assumption_ids == ("constantForce",)
    assert isinstance(work_equations[0].expression.right, Multiply)

    absent_payload = _constant_work_payload()
    absent_payload["assumptions"] = []
    absent = compile_mechanics_ir(_ir(absent_payload))
    assert absent.status is CompilerStatus.underdetermined and absent.graph is not None
    assert "force_work" not in {item.law_id for item in absent.graph.equations}

    variable_payload = _constant_work_payload()
    variable_payload["assumptions"].append(
        variable_payload["assumptions"][0]
        | {"assumption_id": "variableForce", "kind": "force_depends_on_position"}
    )
    conflicting = compile_mechanics_ir(_ir(variable_payload))
    assert conflicting.status is CompilerStatus.unsupported and conflicting.graph is None
    assert conflicting.issues[0].code is CompilerIssueCode.requires_specialized_model

    variable_only = _constant_work_payload()
    variable_only["assumptions"] = [
        variable_only["assumptions"][0]
        | {"assumption_id": "variableForce", "kind": "force_depends_on_position"}
    ]
    unsupported_variable = compile_mechanics_ir(_ir(variable_only))
    assert unsupported_variable.status is CompilerStatus.unsupported
    assert unsupported_variable.graph is None
    assert unsupported_variable.issues[0].code is CompilerIssueCode.requires_specialized_model
    assert "variable_force_work" not in {rule.law_id for rule in core_law_catalog()}


def _friction_payload(state: str) -> dict[str, object]:
    payload = _problem_payload()
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "contactEvidence", "quote": "The contact sticks.",
        "source_span": {"start": 0, "end": 19}, "quantity_span": None, "occurrence_index": 0,
    }]
    payload["entities"] = payload["entities"][:2]
    payload["motion_intervals"][0]["subject_ids"] = ["bodyA", "bodyB"]
    payload["points"] = [{
        "point_id": "contactPoint", "role": "contact", "owner_entity_id": "bodyA",
        "frame_id": "frame1", "label": None, "evidence_refs": ["contactEvidence"],
    }]
    payload["symbols"] = [
        _symbol("tangentForce", "tangentQ", FORCE),
        _symbol("normalForce", "normalQ", FORCE),
        _symbol("mu", "muQ", DIMENSIONLESS),
    ]
    payload["quantities"] = [
        _quantity("tangentQ", "tangentForce", "force", "bodyA", FORCE, frame_id="frame1", interval_id="interval1", point_id="contactPoint", component="tangential", sign=-1),
        _quantity("normalQ", "normalForce", "force", "bodyA", FORCE, value=10.0, unit="N", frame_id="frame1", interval_id="interval1", point_id="contactPoint", component="normal", sign=1),
        _quantity("muQ", "mu", "coefficient_friction", "bodyA", DIMENSIONLESS, value=0.4),
    ]
    payload["interactions"] = [{
        "interaction_id": "contactInteraction", "kind": "contact",
        "participant_ids": ["bodyA", "bodyB"], "point_ids": ["contactPoint"],
        "frame_id": "frame1", "interval_id": "interval1", "event_id": None,
        "quantity_ids": ["tangentQ", "normalQ", "muQ"], "evidence_refs": ["contactEvidence"],
    }]
    payload["constraints"] = []
    payload["state_conditions"] = [{
        "state_condition_id": "frictionState", "kind": "friction", "state": state,
        "subject_id": "bodyA", "interval_id": "interval1", "event_id": None,
        "expression": None, "quantity_ids": ["tangentQ", "normalQ", "muQ"],
        "evidence_refs": ["contactEvidence"],
    }]
    payload["assumptions"] = []
    payload["queries"][0]["target"].update({
        "role": "force", "subject_id": "bodyA", "point_id": "contactPoint",
        "frame_id": "frame1", "interval_id": "interval1", "component": "tangential",
        "target_quantity_id": "tangentQ",
    })
    payload["queries"][0]["output_unit"] = "N"
    payload["queries"][0]["output_dimension"] = FORCE.model_dump(mode="json")
    return payload


def test_friction_templates_encode_two_sided_static_bound_and_sliding_magnitude() -> None:
    sticking = compile_mechanics_ir(_ir(_friction_payload("sticking")))
    assert sticking.status is CompilerStatus.underdetermined and sticking.graph is not None
    bounds = [item for item in sticking.graph.equations if item.law_id == "contact_friction_bound"]
    assert len(bounds) == 2 and all(isinstance(item.expression, Inequality) for item in bounds)
    assert any(isinstance(item.expression.left, Negate) for item in bounds)
    assert all(item.constraint_ids == ("frictionState",) for item in bounds)

    sliding = compile_mechanics_ir(_ir(_friction_payload("sliding")))
    assert sliding.status is CompilerStatus.ready and sliding.graph is not None
    equation = next(item for item in sliding.graph.equations if item.law_id == "contact_sliding_friction")
    assert isinstance(equation.expression, Equality)
    assert isinstance(equation.expression.right, Multiply)
    assert equation.scope.point_ids == ("contactPoint",)


def _collision_payload() -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["entities"] = [
        payload["entities"][0],
        {"entity_id": "bodyB", "primitive": "particle", "label": "B", "aliases": [], "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None},
    ]
    payload["reference_frames"] = [{
        "frame_id": "impactFrame", "frame_type": "cartesian_1d", "origin": {"kind": "world"},
        "axes": [{"axis": "x", "direction": {"kind": "axis", "frame_id": "impactFrame", "axis": "x", "sign": 1}}],
        "parent_frame_id": None, "translating_with_entity_id": None,
        "rotating_about_point_id": None, "generalized_coordinate_symbol_ids": [], "evidence_refs": [],
    }]
    payload["motion_intervals"] = [{
        "interval_id": "impactInterval", "order": 1, "subject_ids": ["bodyA", "bodyB"],
        "frame_id": "impactFrame", "start_event_id": "impactStart", "end_event_id": "impactEnd",
        "evidence_refs": [],
    }]
    payload["events"] = [
        {"event_id": "impactStart", "kind": "collision_start", "subject_ids": ["bodyA", "bodyB"], "interval_ids": ["impactInterval"], "time_quantity_id": None, "evidence_refs": []},
        {"event_id": "impactEnd", "kind": "collision_end", "subject_ids": ["bodyA", "bodyB"], "interval_ids": ["impactInterval"], "time_quantity_id": None, "evidence_refs": []},
    ]
    payload["symbols"] = [
        _symbol("mA", "massA", MASS), _symbol("mB", "massB", MASS),
        _symbol("uA", "beforeA", VELOCITY), _symbol("uB", "beforeB", VELOCITY),
        _symbol("vA", "afterA", VELOCITY), _symbol("vB", "afterB", VELOCITY),
        _symbol("e", "restitutionQ", DIMENSIONLESS),
    ]
    payload["quantities"] = [
        _quantity("massA", "mA", "mass", "bodyA", MASS, value=2.0, unit="kg"),
        _quantity("massB", "mB", "mass", "bodyB", MASS, value=3.0, unit="kg"),
        _quantity("beforeA", "uA", "velocity", "bodyA", VELOCITY, value=4.0, unit="m/s", frame_id="impactFrame", interval_id="impactInterval", event_id="impactStart", component="x"),
        _quantity("beforeB", "uB", "velocity", "bodyB", VELOCITY, value=0.0, unit="m/s", frame_id="impactFrame", interval_id="impactInterval", event_id="impactStart", component="x"),
        _quantity("afterA", "vA", "velocity", "bodyA", VELOCITY, frame_id="impactFrame", interval_id="impactInterval", event_id="impactEnd", component="x"),
        _quantity("afterB", "vB", "velocity", "bodyB", VELOCITY, frame_id="impactFrame", interval_id="impactInterval", event_id="impactEnd", component="x"),
        _quantity("restitutionQ", "e", "coefficient_restitution", "bodyA", DIMENSIONLESS, value=0.5),
    ]
    all_quantities = [item["quantity_id"] for item in payload["quantities"]]
    payload["interactions"] = [{
        "interaction_id": "collisionInteraction", "kind": "collision",
        "participant_ids": ["bodyA", "bodyB"], "point_ids": [], "frame_id": "impactFrame",
        "interval_id": "impactInterval", "event_id": None,
        "quantity_ids": all_quantities, "evidence_refs": [],
    }]
    payload["assumptions"] = [{
        "assumption_id": "isolatedImpact", "kind": "external_impulse_negligible",
        "subject_id": "bodyA", "interval_id": "impactInterval", "disposition": "approved",
        "proposed_role": None, "proposed_value": None, "proposed_unit": None,
        "reason": "External impulse is negligible during impact.", "evidence_refs": [],
    }]
    payload["queries"][0]["target"].update({
        "role": "velocity", "subject_id": "bodyA", "frame_id": "impactFrame",
        "interval_id": "impactInterval", "event_id": "impactEnd", "component": "x",
        "target_quantity_id": "afterA",
    })
    payload["queries"][0]["output_unit"] = "m/s"
    payload["queries"][0]["output_dimension"] = VELOCITY.model_dump(mode="json")
    return payload


def test_collision_template_requires_one_reciprocal_event_pair_and_preserves_both_events() -> None:
    result = compile_mechanics_ir(_ir(_collision_payload()))
    assert result.status is CompilerStatus.ready and result.graph is not None
    impact = [item for item in result.graph.equations if item.law_id in {"system_momentum_conservation", "direct_restitution"}]
    assert len(impact) == 2
    assert all(item.scope.interval_id == "impactInterval" for item in impact)
    assert all(item.scope.frame_id == "impactFrame" for item in impact)
    assert all(item.scope.event_ids == ("impactEnd", "impactStart") for item in impact)
    conservation = next(
        item for item in impact if item.law_id == "system_momentum_conservation"
    )
    assert conservation.assumption_ids == ("isolatedImpact",)
    restitution = next(item for item in impact if item.law_id == "direct_restitution")
    assert isinstance(restitution.expression.left, Subtract)
    assert isinstance(restitution.expression.right, Negate)

    mispaired_payload = _collision_payload()
    next(item for item in mispaired_payload["quantities"] if item["quantity_id"] == "afterB")["event_id"] = "impactStart"
    mispaired = compile_mechanics_ir(_ir(mispaired_payload))
    assert mispaired.status is CompilerStatus.unsupported and mispaired.graph is None
    assert mispaired.issues[0].code is CompilerIssueCode.requires_specialized_model


def test_collision_conservation_requires_external_assumption_id_authority() -> None:
    ir = _ir(_collision_payload())
    seal = authorize_validated_mechanics_ir(ir)
    _, corrections, defaults = _authority_bundle(ir)
    for approved_ids in ((), ("unrelatedApproval",)):
        rejected = _compile_mechanics_ir(
            ir,
            validated_ir_authorization=seal,
            approved_assumption_ids=approved_ids,
            authorized_corrections=corrections,
            authorized_assumptions=defaults,
        )
        assert rejected.status is CompilerStatus.underdetermined
        assert rejected.graph is not None
        assert "system_momentum_conservation" not in {
            item.law_id for item in rejected.graph.equations
        }
        assert all(not item.assumption_ids for item in rejected.graph.equations)
        assert rejected.graph.rank.unknown_count == 2
        assert rejected.graph.rank.structural_rank == 1
        assert rejected.graph.selected_equation_ids == ()

    restored = _compile_mechanics_ir(
        ir,
        validated_ir_authorization=seal,
        approved_assumption_ids=("isolatedImpact",),
        authorized_corrections=corrections,
        authorized_assumptions=defaults,
    )
    assert restored.status is CompilerStatus.ready and restored.graph is not None
    conservation = next(
        item
        for item in restored.graph.equations
        if item.law_id == "system_momentum_conservation"
    )
    assert conservation.assumption_ids == ("isolatedImpact",)
    assert len(restored.graph.selected_equation_ids) == 2


def test_evidenced_fixed_pulley_uses_server_topology_coefficients_and_incomplete_topology_stops() -> None:
    payload = _problem_payload()
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "wrapEvidence", "quote": "The rope wraps over a fixed pulley.",
        "source_span": {"start": 0, "end": 35}, "quantity_span": None, "occurrence_index": 0,
    }]
    payload["entities"].append({
        "entity_id": "pulley1", "primitive": "pulley", "label": "pulley", "aliases": [],
        "component_of_entity_id": None, "evidence_refs": ["wrapEvidence"], "model_confidence": None,
    })
    payload["motion_intervals"][0]["subject_ids"].append("pulley1")
    rope_interaction = next(item for item in payload["interactions"] if item["interaction_id"] == "ropeForce")
    rope_interaction["participant_ids"].append("pulley1")
    rope_interaction["evidence_refs"] = ["wrapEvidence"]
    payload["geometry"] = [{
        "relation_id": "ropeWrap", "kind": "wraps", "participant_ids": ["rope1", "pulley1"],
        "expression": None, "quantity_ids": [], "interval_id": "interval1",
        "evidence_refs": ["wrapEvidence"],
    }]
    payload["assumptions"].append({
        "assumption_id": "fixedPulley", "kind": "fixed_pulley", "subject_id": "pulley1",
        "interval_id": "interval1", "disposition": "approved", "proposed_role": None,
        "proposed_value": None, "proposed_unit": None, "reason": "The pulley center is fixed.",
        "evidence_refs": ["wrapEvidence"],
    })
    payload["assumptions"].append({
        "assumption_id": "idealPulley", "kind": "ideal_massless_frictionless_pulley",
        "subject_id": "pulley1", "interval_id": "interval1", "disposition": "approved",
        "proposed_role": None, "proposed_value": None, "proposed_unit": None,
        "reason": "The fixed pulley is massless and frictionless.",
        "evidence_refs": ["wrapEvidence"],
    })
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.ready and result.graph is not None
    relation = next(item for item in result.graph.equations if item.law_id == "rope_fixed_pulley_motion")
    assert isinstance(relation.expression.left, Add)
    assert relation.assumption_ids == ("fixedLengthRope", "fixedPulley")
    assert {"bodyA", "bodyB", "pulley1", "rope1"}.issubset(relation.scope.entity_ids)
    assert "rope_massless_tension" in {item.law_id for item in result.graph.equations}

    incomplete = deepcopy(payload)
    incomplete["assumptions"] = [item for item in incomplete["assumptions"] if item["assumption_id"] != "fixedPulley"]
    stopped = compile_mechanics_ir(_ir(incomplete))
    assert stopped.status is CompilerStatus.unsupported and stopped.graph is None
    assert stopped.issues[0].code is CompilerIssueCode.requires_specialized_model


def test_massive_pulley_suppresses_equal_tension_and_emits_signed_newton_euler() -> None:
    payload = _problem_payload()
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "massiveWrapEvidence",
        "quote": "The rope wraps a massive pulley.",
        "source_span": {"start": 0, "end": 32}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["entities"].append({
        "entity_id": "pulley1", "primitive": "pulley", "label": "pulley",
        "aliases": [], "component_of_entity_id": None,
        "evidence_refs": ["massiveWrapEvidence"], "model_confidence": None,
    })
    payload["motion_intervals"][0]["subject_ids"].append("pulley1")
    interaction = next(item for item in payload["interactions"] if item["interaction_id"] == "ropeForce")
    interaction["participant_ids"].append("pulley1")
    interaction["evidence_refs"] = ["massiveWrapEvidence"]
    next(item for item in payload["quantities"] if item["quantity_id"] == "tensionA")["direction"]["sign"] = 1
    payload["symbols"].extend([
        _symbol("pulleyInertia", "pulleyInertiaQ", MOMENT_OF_INERTIA),
        _symbol("pulleyRadius", "pulleyRadiusQ", LENGTH),
        _symbol("pulleyAlpha", "pulleyAlphaQ", ANGULAR_ACCELERATION),
    ])
    payload["quantities"].extend([
        _quantity("pulleyInertiaQ", "pulleyInertia", "moment_of_inertia", "pulley1", MOMENT_OF_INERTIA, value=1.5, unit="kg*m^2", interval_id="interval1"),
        _quantity("pulleyRadiusQ", "pulleyRadius", "radius", "pulley1", LENGTH, value=0.25, unit="m", interval_id="interval1"),
        _quantity("pulleyAlphaQ", "pulleyAlpha", "angular_acceleration", "pulley1", ANGULAR_ACCELERATION, frame_id="frame1", interval_id="interval1", component="x", sign=-1),
    ])
    payload["geometry"] = [{
        "relation_id": "massiveRopeWrap", "kind": "wraps",
        "participant_ids": ["rope1", "pulley1"], "expression": None,
        "quantity_ids": ["pulleyRadiusQ"], "interval_id": "interval1",
        "evidence_refs": ["massiveWrapEvidence"],
    }]
    payload["assumptions"].append({
        "assumption_id": "fixedPulley", "kind": "fixed_pulley", "subject_id": "pulley1",
        "interval_id": "interval1", "disposition": "approved", "proposed_role": None,
        "proposed_value": None, "proposed_unit": None, "reason": "The axle is fixed.",
        "evidence_refs": ["massiveWrapEvidence"],
    })
    payload["assumptions"].append({
        "assumption_id": "idealPulley", "kind": "ideal_massless_frictionless_pulley",
        "subject_id": "pulley1", "interval_id": "interval1", "disposition": "approved",
        "proposed_role": None, "proposed_value": None, "proposed_unit": None,
        "reason": "Adversarial ideal label must not override positive inertia.",
        "evidence_refs": ["massiveWrapEvidence"],
    })
    payload["queries"][0]["target"].update({
        "role": "angular_acceleration", "subject_id": "pulley1", "frame_id": "frame1",
        "interval_id": "interval1", "component": "x", "target_quantity_id": "pulleyAlphaQ",
    })
    payload["queries"][0]["output_unit"] = "rad/s^2"
    payload["queries"][0]["output_dimension"] = ANGULAR_ACCELERATION.model_dump(mode="json")

    result = compile_mechanics_ir(_ir(payload))
    assert result.graph is not None
    assert "rope_massless_tension" not in {item.law_id for item in result.graph.equations}
    equation = next(item for item in result.graph.equations if item.law_id == "pulley_newton_euler")
    assert isinstance(equation.expression.left, Multiply)
    tension_sum = next(item for item in equation.expression.left.factors if isinstance(item, Add))
    assert any(isinstance(item, Negate) for item in tension_sum.terms)
    assert isinstance(equation.expression.right, Multiply)
    assert any(isinstance(item, Negate) for item in equation.expression.right.factors)


def test_equal_tension_requires_exact_approved_subject_coverage_for_every_pulley() -> None:
    duplicated = _problem_payload()
    duplicated["entities"].extend([
        {"entity_id": "pulleyOne", "primitive": "pulley", "label": "P1", "aliases": [], "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None},
        {"entity_id": "pulleyTwo", "primitive": "pulley", "label": "P2", "aliases": [], "component_of_entity_id": None, "evidence_refs": [], "model_confidence": None},
    ])
    duplicated["motion_intervals"][0]["subject_ids"].extend(["pulleyOne", "pulleyTwo"])
    rope_interaction = next(
        item
        for item in duplicated["interactions"]
        if item["interaction_id"] == "ropeForce"
    )
    rope_interaction["participant_ids"].extend(["pulleyOne", "pulleyTwo"])
    duplicated["assumptions"].extend([
        {
            "assumption_id": "idealPulleyOneA",
            "kind": "ideal_massless_frictionless_pulley",
            "subject_id": "pulleyOne",
            "interval_id": "interval1",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "First approval for pulley one.",
            "evidence_refs": [],
        },
        {
            "assumption_id": "idealPulleyOneB",
            "kind": "ideal_massless_frictionless_pulley",
            "subject_id": "pulleyOne",
            "interval_id": "interval1",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "Duplicate approval for pulley one.",
            "evidence_refs": [],
        },
    ])
    rejected = compile_mechanics_ir(_ir(duplicated))
    assert rejected.graph is not None
    assert "rope_massless_tension" not in {
        item.law_id for item in rejected.graph.equations
    }

    exact = deepcopy(duplicated)
    second = next(
        item
        for item in exact["assumptions"]
        if item["assumption_id"] == "idealPulleyOneB"
    )
    second["subject_id"] = "pulleyTwo"
    second["reason"] = "Exact approval for pulley two."
    accepted = compile_mechanics_ir(_ir(exact))
    assert accepted.graph is not None
    equal_tension = [
        item
        for item in accepted.graph.equations
        if item.law_id == "rope_massless_tension"
    ]
    assert len(equal_tension) == 1
    assert {
        "idealPulleyOneA", "idealPulleyOneB", "masslessRope"
    }.issubset(equal_tension[0].assumption_ids)


def test_signed_unknowns_are_applied_on_particle_and_rigid_dynamic_equations() -> None:
    particle_payload = _problem_payload()
    next(
        item
        for item in particle_payload["quantities"]
        if item["quantity_id"] == "accelerationA"
    )["direction"]["sign"] = -1
    particle = compile_mechanics_ir(_ir(particle_payload))
    assert particle.graph is not None
    particle_equation = next(
        item
        for item in particle.graph.equations
        if item.law_id == "particle_newton_second"
        and "accelerationA" in item.source_quantity_ids
    )
    assert isinstance(particle_equation.expression.right, Multiply)
    assert any(
        isinstance(item, Negate)
        and isinstance(item.operand, SymbolRef)
        and item.operand.symbol_id == "aA"
        for item in particle_equation.expression.right.factors
    )

    rigid_payload = _single_unknown_payload([])
    rigid_payload["entities"][0]["primitive"] = "rigid_body"
    rigid_payload["reference_frames"] = deepcopy(_problem_payload()["reference_frames"])
    rigid_payload["motion_intervals"] = deepcopy(_problem_payload()["motion_intervals"][:1])
    rigid_payload["motion_intervals"][0]["subject_ids"] = ["bodyA"]
    rigid_payload["points"] = [{
        "point_id": "rigidCenter", "role": "mass_center", "owner_entity_id": "bodyA",
        "frame_id": "frame1", "label": "G", "evidence_refs": [],
    }]
    rigid_payload["symbols"] = [
        _symbol("rigidInertia", "rigidInertiaQ", MOMENT_OF_INERTIA),
        _symbol("rigidMoment", "rigidMomentQ", ENERGY),
        _symbol("rigidAlpha", "rigidAlphaQ", ANGULAR_ACCELERATION),
    ]
    rigid_payload["quantities"] = [
        _quantity("rigidInertiaQ", "rigidInertia", "moment_of_inertia", "bodyA", MOMENT_OF_INERTIA, value=2.0, unit="kg*m^2", frame_id="frame1", interval_id="interval1", point_id="rigidCenter"),
        _quantity("rigidMomentQ", "rigidMoment", "moment", "bodyA", ENERGY, value=6.0, unit="N*m", frame_id="frame1", interval_id="interval1", point_id="rigidCenter", component="x", sign=1),
        _quantity("rigidAlphaQ", "rigidAlpha", "angular_acceleration", "bodyA", ANGULAR_ACCELERATION, frame_id="frame1", interval_id="interval1", point_id="rigidCenter", component="x", sign=-1),
    ]
    rigid_payload["interactions"] = [{
        "interaction_id": "rigidMomentInteraction", "kind": "applied_force",
        "participant_ids": ["bodyA"], "point_ids": ["rigidCenter"],
        "frame_id": "frame1", "interval_id": "interval1", "event_id": None,
        "quantity_ids": ["rigidMomentQ"], "evidence_refs": [],
    }]
    rigid_payload["queries"][0]["target"].update({
        "role": "angular_acceleration", "point_id": "rigidCenter", "frame_id": "frame1",
        "interval_id": "interval1", "component": "x", "target_quantity_id": "rigidAlphaQ",
    })
    rigid_payload["queries"][0]["output_unit"] = "rad/s^2"
    rigid_payload["queries"][0]["output_dimension"] = ANGULAR_ACCELERATION.model_dump(mode="json")
    rigid = compile_mechanics_ir(_ir(rigid_payload))
    assert rigid.status is CompilerStatus.ready and rigid.graph is not None
    rigid_equation = next(
        item for item in rigid.graph.equations if item.law_id == "rigid_newton_euler"
    )
    assert isinstance(rigid_equation.expression.right, Multiply)
    assert any(
        isinstance(item, Negate)
        and isinstance(item.operand, SymbolRef)
        and item.operand.symbol_id == "rigidAlpha"
        for item in rigid_equation.expression.right.factors
    )

    momentum_payload = deepcopy(rigid_payload)
    momentum_payload["symbols"] = [
        _symbol("rigidInertia", "rigidInertiaQ", MOMENT_OF_INERTIA),
        _symbol("rigidOmega", "rigidOmegaQ", FREQUENCY),
        _symbol("rigidH", "rigidHQ", ANGULAR_MOMENTUM),
    ]
    momentum_payload["quantities"] = [
        _quantity("rigidInertiaQ", "rigidInertia", "moment_of_inertia", "bodyA", MOMENT_OF_INERTIA, value=2.0, unit="kg*m^2", frame_id="frame1", interval_id="interval1", point_id="rigidCenter"),
        _quantity("rigidOmegaQ", "rigidOmega", "angular_velocity", "bodyA", FREQUENCY, value=3.0, unit="rad/s", frame_id="frame1", interval_id="interval1", point_id="rigidCenter", component="x", sign=-1),
        _quantity("rigidHQ", "rigidH", "angular_momentum", "bodyA", ANGULAR_MOMENTUM, frame_id="frame1", interval_id="interval1", point_id="rigidCenter", component="x", sign=-1),
    ]
    momentum_payload["interactions"] = []
    momentum_payload["queries"][0]["target"].update({
        "role": "angular_momentum", "target_quantity_id": "rigidHQ",
    })
    momentum_payload["queries"][0]["output_unit"] = "kg*m^2/s"
    momentum_payload["queries"][0]["output_dimension"] = ANGULAR_MOMENTUM.model_dump(mode="json")
    momentum = compile_mechanics_ir(_ir(momentum_payload))
    assert momentum.status is CompilerStatus.ready and momentum.graph is not None
    momentum_equation = next(
        item for item in momentum.graph.equations if item.law_id == "rigid_angular_momentum"
    )
    assert isinstance(momentum_equation.expression.left, Negate)
    assert isinstance(momentum_equation.expression.right, Multiply)
    assert any(
        isinstance(item, Negate)
        and isinstance(item.operand, SymbolRef)
        and item.operand.symbol_id == "rigidOmega"
        for item in momentum_equation.expression.right.factors
    )


def test_planar_rigid_point_velocity_uses_cm_point_geometry_and_preserves_scope() -> None:
    payload = _single_unknown_payload([])
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "rigidEvidence", "quote": "Point P is fixed to the rigid body at radius 2 m.",
        "source_span": {"start": 0, "end": 49}, "quantity_span": None, "occurrence_index": 0,
    }]
    payload["entities"][0]["primitive"] = "rigid_body"
    payload["reference_frames"] = [{
        "frame_id": "planeFrame", "frame_type": "cartesian_2d", "origin": {"kind": "world"},
        "axes": [
            {"axis": "x", "direction": {"kind": "axis", "frame_id": "planeFrame", "axis": "x", "sign": 1}},
            {"axis": "y", "direction": {"kind": "axis", "frame_id": "planeFrame", "axis": "y", "sign": 1}},
        ],
        "parent_frame_id": None, "translating_with_entity_id": None, "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [], "evidence_refs": [],
    }]
    payload["motion_intervals"] = [{
        "interval_id": "rigidInterval", "order": 1, "subject_ids": ["bodyA"],
        "frame_id": "planeFrame", "start_event_id": None, "end_event_id": None, "evidence_refs": [],
    }]
    payload["points"] = [
        {"point_id": "centerPoint", "role": "mass_center", "owner_entity_id": "bodyA", "frame_id": "planeFrame", "label": "G", "evidence_refs": []},
        {"point_id": "materialPoint", "role": "material", "owner_entity_id": "bodyA", "frame_id": "planeFrame", "label": "P", "evidence_refs": ["rigidEvidence"]},
    ]
    payload["symbols"] = [
        _symbol("vP", "pointVelocity", VELOCITY),
        _symbol("vG", "centerVelocity", VELOCITY),
        _symbol("omega", "angularVelocity", FREQUENCY),
        _symbol("radius", "radiusQ", LENGTH),
    ]
    payload["quantities"] = [
        _quantity("pointVelocity", "vP", "velocity", "bodyA", VELOCITY, frame_id="planeFrame", interval_id="rigidInterval", point_id="materialPoint", component="tangential"),
        _quantity("centerVelocity", "vG", "velocity", "bodyA", VELOCITY, value=1.0, unit="m/s", frame_id="planeFrame", interval_id="rigidInterval", point_id="centerPoint", component="tangential"),
        _quantity("angularVelocity", "omega", "angular_velocity", "bodyA", FREQUENCY, value=3.0, unit="rad/s", frame_id="planeFrame", interval_id="rigidInterval", point_id="centerPoint"),
        _quantity("radiusQ", "radius", "radius", "bodyA", LENGTH, value=2.0, unit="m", frame_id="planeFrame", interval_id="rigidInterval", point_id="materialPoint", evidence_refs=("rigidEvidence",)),
    ]
    payload["geometry"] = [{
        "relation_id": "pointAttachment", "kind": "attached",
        "participant_ids": ["bodyA", "materialPoint"], "expression": None,
        "quantity_ids": ["radiusQ"], "interval_id": "rigidInterval", "evidence_refs": ["rigidEvidence"],
    }]
    payload["queries"][0]["target"].update({
        "role": "velocity", "point_id": "materialPoint", "frame_id": "planeFrame",
        "interval_id": "rigidInterval", "component": "tangential", "target_quantity_id": "pointVelocity",
    })
    payload["queries"][0]["output_unit"] = "m/s"
    payload["queries"][0]["output_dimension"] = VELOCITY.model_dump(mode="json")
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.ready and result.graph is not None
    equation = next(item for item in result.graph.equations if item.law_id == "rigid_point_velocity")
    assert isinstance(equation.expression.right, Add)
    assert equation.scope.point_ids == ("centerPoint", "materialPoint")
    assert equation.scope.frame_id == "planeFrame" and equation.scope.interval_id == "rigidInterval"

    static_radius = deepcopy(payload)
    next(
        item
        for item in static_radius["quantities"]
        if item["quantity_id"] == "radiusQ"
    )["interval_id"] = None
    static_radius["geometry"][0]["interval_id"] = None
    static_result = compile_mechanics_ir(_ir(static_radius))
    assert static_result.status is CompilerStatus.ready and static_result.graph is not None
    static_equation = next(
        item
        for item in static_result.graph.equations
        if item.law_id == "rigid_point_velocity"
    )
    assert static_equation.scope.interval_id == "rigidInterval"

    ambiguous_radius = deepcopy(static_radius)
    ambiguous_relation = deepcopy(ambiguous_radius["geometry"][0])
    ambiguous_relation["relation_id"] = "duplicatePointAttachment"
    ambiguous_radius["geometry"].append(ambiguous_relation)
    ambiguous_result = compile_mechanics_ir(_ir(ambiguous_radius))
    assert ambiguous_result.status is CompilerStatus.underdetermined
    assert ambiguous_result.graph is not None
    assert "rigid_point_velocity" not in {
        item.law_id for item in ambiguous_result.graph.equations
    }

    wrong_relation = deepcopy(static_radius)
    wrong_relation["motion_intervals"].append({
        "interval_id": "otherRigidInterval", "order": 2, "subject_ids": ["bodyA"],
        "frame_id": "planeFrame", "start_event_id": None, "end_event_id": None,
        "evidence_refs": [],
    })
    wrong_relation["geometry"][0]["interval_id"] = "otherRigidInterval"
    wrong_result = compile_mechanics_ir(_ir(wrong_relation))
    assert wrong_result.status is CompilerStatus.underdetermined and wrong_result.graph is not None
    assert "rigid_point_velocity" not in {
        item.law_id for item in wrong_result.graph.equations
    }

    unscoped_dynamics = deepcopy(static_radius)
    unscoped_dynamics["geometry"][0]["interval_id"] = "rigidInterval"
    for quantity in unscoped_dynamics["quantities"]:
        if quantity["quantity_id"] != "radiusQ":
            quantity["interval_id"] = None
    unscoped_dynamics["queries"][0]["target"]["interval_id"] = None
    unscoped_result = compile_mechanics_ir(_ir(unscoped_dynamics))
    assert unscoped_result.status is CompilerStatus.underdetermined
    assert unscoped_result.graph is not None
    assert "rigid_point_velocity" not in {
        item.law_id for item in unscoped_result.graph.equations
    }

    mixed = deepcopy(payload)
    mixed["motion_intervals"][0].update(
        {"start_event_id": "rigidStart", "end_event_id": "rigidEnd"}
    )
    mixed["events"] = [
        {"event_id": "rigidStart", "kind": "start", "subject_ids": ["bodyA"], "interval_ids": ["rigidInterval"], "time_quantity_id": None, "evidence_refs": []},
        {"event_id": "rigidEnd", "kind": "finish", "subject_ids": ["bodyA"], "interval_ids": ["rigidInterval"], "time_quantity_id": None, "evidence_refs": []},
    ]
    next(item for item in mixed["quantities"] if item["quantity_id"] == "pointVelocity")["event_id"] = "rigidStart"
    next(item for item in mixed["quantities"] if item["quantity_id"] == "centerVelocity")["event_id"] = "rigidEnd"
    next(item for item in mixed["quantities"] if item["quantity_id"] == "angularVelocity")["event_id"] = "rigidStart"
    mixed["queries"][0]["target"]["event_id"] = "rigidStart"
    rejected = compile_mechanics_ir(_ir(mixed))
    assert rejected.status is CompilerStatus.underdetermined and rejected.graph is not None
    assert "rigid_point_velocity" not in {item.law_id for item in rejected.graph.equations}

    signed = deepcopy(payload)
    signed["motion_intervals"][0]["start_event_id"] = "rigidStart"
    signed["events"] = [{
        "event_id": "rigidStart", "kind": "start", "subject_ids": ["bodyA"],
        "interval_ids": ["rigidInterval"], "time_quantity_id": None, "evidence_refs": [],
    }]
    signed["symbols"] = [
        _symbol("aP", "pointAcceleration", ACCELERATION),
        _symbol("aG", "centerAcceleration", ACCELERATION),
        _symbol("alpha", "angularAcceleration", ANGULAR_ACCELERATION),
        _symbol("radius", "radiusQ", LENGTH),
    ]
    signed["quantities"] = [
        _quantity("pointAcceleration", "aP", "acceleration", "bodyA", ACCELERATION, frame_id="planeFrame", interval_id="rigidInterval", event_id="rigidStart", point_id="materialPoint", component="tangential", sign=1),
        _quantity("centerAcceleration", "aG", "acceleration", "bodyA", ACCELERATION, value=1.0, unit="m/s^2", frame_id="planeFrame", interval_id="rigidInterval", event_id="rigidStart", point_id="centerPoint", component="tangential", sign=1),
        _quantity("angularAcceleration", "alpha", "angular_acceleration", "bodyA", ANGULAR_ACCELERATION, value=2.0, unit="rad/s^2", frame_id="planeFrame", interval_id="rigidInterval", event_id="rigidStart", point_id="centerPoint", sign=-1),
        _quantity("radiusQ", "radius", "radius", "bodyA", LENGTH, value=2.0, unit="m", frame_id="planeFrame", point_id="materialPoint", evidence_refs=("rigidEvidence",)),
    ]
    signed["geometry"][0]["interval_id"] = None
    signed["queries"][0]["target"].update({
        "role": "acceleration", "event_id": "rigidStart", "component": "tangential",
        "target_quantity_id": "pointAcceleration",
    })
    signed["queries"][0]["output_unit"] = "m/s^2"
    signed["queries"][0]["output_dimension"] = ACCELERATION.model_dump(mode="json")
    signed_result = compile_mechanics_ir(_ir(signed))
    assert signed_result.status is CompilerStatus.ready and signed_result.graph is not None
    signed_equation = next(
        item
        for item in signed_result.graph.equations
        if item.law_id == "rigid_point_tangential_acceleration"
    )
    assert signed_equation.scope.event_id == "rigidStart"
    relative = next(
        item for item in signed_equation.expression.right.terms if isinstance(item, Multiply)
    )
    assert any(isinstance(item, Negate) for item in relative.factors)


def _vibration_payload() -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "initialEvidence",
        "quote": "Initially x is zero and v is zero.", "source_span": {"start": 0, "end": 34},
        "quantity_span": None, "occurrence_index": 0,
    }]
    payload["reference_frames"] = [{
        "frame_id": "vibrationFrame", "frame_type": "cartesian_1d", "origin": {"kind": "world"},
        "axes": [{"axis": "x", "direction": {"kind": "axis", "frame_id": "vibrationFrame", "axis": "x", "sign": 1}}],
        "parent_frame_id": None, "translating_with_entity_id": None, "rotating_about_point_id": None,
        "generalized_coordinate_symbol_ids": [], "evidence_refs": [],
    }]
    payload["motion_intervals"] = [{
        "interval_id": "vibrationInterval", "order": 1, "subject_ids": ["bodyA"],
        "frame_id": "vibrationFrame", "start_event_id": "initialEvent", "end_event_id": None,
        "evidence_refs": [],
    }]
    payload["events"] = [{
        "event_id": "initialEvent", "kind": "start", "subject_ids": ["bodyA"],
        "interval_ids": ["vibrationInterval"], "time_quantity_id": "timeQ",
        "evidence_refs": ["initialEvidence"],
    }]
    payload["symbols"] = [
        _symbol("x", "displacementQ", LENGTH), _symbol("t", "timeQ", TIME),
        _symbol("m", "massQ", MASS), _symbol("k", "stiffnessQ", STIFFNESS),
        _symbol("x0", "initialDisplacement", LENGTH), _symbol("v0", "initialVelocity", VELOCITY),
    ]
    payload["quantities"] = [
        _quantity("displacementQ", "x", "displacement", "bodyA", LENGTH, frame_id="vibrationFrame", interval_id="vibrationInterval", component="x"),
        _quantity("timeQ", "t", "time", "bodyA", TIME, frame_id="vibrationFrame", interval_id="vibrationInterval"),
        _quantity("massQ", "m", "mass", "bodyA", MASS, value=2.0, unit="kg"),
        _quantity("stiffnessQ", "k", "stiffness", "bodyA", STIFFNESS, value=8.0, unit="N/m"),
        _quantity("initialDisplacement", "x0", "displacement", "bodyA", LENGTH, value=0.0, unit="m", frame_id="vibrationFrame", interval_id="vibrationInterval", event_id="initialEvent", component="x", provenance="explicit_source", evidence_refs=("initialEvidence",)),
        _quantity("initialVelocity", "v0", "velocity", "bodyA", VELOCITY, value=0.0, unit="m/s", frame_id="vibrationFrame", interval_id="vibrationInterval", event_id="initialEvent", component="x", provenance="explicit_source", evidence_refs=("initialEvidence",)),
    ]
    payload["interactions"] = [{
        "interaction_id": "springInteraction", "kind": "spring", "participant_ids": ["bodyA"],
        "point_ids": [], "frame_id": "vibrationFrame", "interval_id": "vibrationInterval",
        "event_id": None, "quantity_ids": ["stiffnessQ", "displacementQ"], "evidence_refs": [],
    }]
    payload["state_conditions"] = [{
        "state_condition_id": "initialState", "kind": "initial", "state": "active",
        "subject_id": "bodyA", "interval_id": "vibrationInterval", "event_id": "initialEvent",
        "expression": Equality(
            left=SymbolRef(symbol_id="x0", dimension=LENGTH),
            right=LiteralNode(value=999.0, dimension=LENGTH),
        ),
        "quantity_ids": ["initialDisplacement", "initialVelocity"],
        "evidence_refs": ["initialEvidence"],
    }]
    payload["assumptions"] = [
        {"assumption_id": "linearAuthority", "kind": "linear_vibration", "subject_id": "bodyA", "interval_id": "vibrationInterval", "disposition": "approved", "proposed_role": None, "proposed_value": None, "proposed_unit": None, "reason": "Linear spring motion.", "evidence_refs": []},
        {"assumption_id": "undampedAuthority", "kind": "undamped", "subject_id": "bodyA", "interval_id": "vibrationInterval", "disposition": "approved", "proposed_role": None, "proposed_value": None, "proposed_unit": None, "reason": "No damper.", "evidence_refs": []},
        {"assumption_id": "freeAuthority", "kind": "free_vibration", "subject_id": "bodyA", "interval_id": "vibrationInterval", "disposition": "approved", "proposed_role": None, "proposed_value": None, "proposed_unit": None, "reason": "No external forcing.", "evidence_refs": []},
    ]
    payload["queries"][0]["target"].update({
        "role": "displacement", "frame_id": "vibrationFrame", "interval_id": "vibrationInterval",
        "component": "x", "target_quantity_id": "displacementQ",
    })
    payload["queries"][0]["output_unit"] = "m"
    payload["queries"][0]["output_dimension"] = LENGTH.model_dump(mode="json")
    return payload


def test_vibration_ode_requires_exact_regime_and_source_backed_initial_state() -> None:
    result = compile_mechanics_ir(_ir(_vibration_payload()))
    assert result.status is CompilerStatus.ready and result.graph is not None
    equation = next(item for item in result.graph.equations if item.law_id == "linear_vibration")
    assert isinstance(equation.expression.left, Add)
    assert equation.constraint_ids == ("initialState",)
    assert equation.assumption_ids == ("freeAuthority", "linearAuthority", "undampedAuthority")
    assert not any(
        isinstance(item.expression, Equality)
        and isinstance(item.expression.right, LiteralNode)
        and item.expression.right.value == 999.0
        for item in result.graph.equations
    )
    derivatives = [
        factor
        for term in equation.expression.left.terms
        if isinstance(term, Multiply)
        for factor in term.factors
        if isinstance(factor, Derivative)
    ]
    assert len(derivatives) == 1 and derivatives[0].order == 2
    assert derivatives[0].wrt_symbol_id == "t"
    assert isinstance(derivatives[0].expression, SymbolRef)
    assert derivatives[0].expression.symbol_id == "x"
    assert "a" not in {item.symbol.symbol_id for item in result.graph.symbols}

    conditions = result.graph.initial_conditions
    assert len(conditions) == 2
    assert tuple(item.derivative_order for item in conditions) == (0, 1)
    assert {item.target_symbol_id for item in conditions} == {"x"}
    assert {item.value_symbol_id for item in conditions} == {"x0", "v0"}
    assert {item.wrt_symbol_id for item in conditions} == {"t"}
    assert all(item.scope.event_id == "initialEvent" for item in conditions)
    assert all(item.scope.event_ids == ("initialEvent",) for item in conditions)
    assert all(item.source_evidence_ids == ("initialEvidence",) for item in conditions)
    assert all(item.source_state_condition_ids == ("initialState",) for item in conditions)
    assert {item.source_quantity_ids for item in conditions} == {
        ("initialDisplacement",),
        ("initialVelocity",),
    }
    assert {item.symbol.symbol_id for item in result.graph.symbols}.issuperset({"x", "t", "x0", "v0"})

    changed = _vibration_payload()
    initial = next(item for item in changed["quantities"] if item["quantity_id"] == "initialDisplacement")
    initial.update(_quantity("initialDisplacement", "x0", "displacement", "bodyA", LENGTH, value=1.0, unit="m", frame_id="vibrationFrame", interval_id="vibrationInterval", event_id="initialEvent", component="x", provenance="explicit_source", evidence_refs=("initialEvidence",)))
    changed_result = compile_mechanics_ir(_ir(changed))
    assert changed_result.graph is not None
    assert changed_result.graph.fingerprint != result.graph.fingerprint

    incomplete = _vibration_payload()
    incomplete["assumptions"] = [item for item in incomplete["assumptions"] if item["assumption_id"] != "freeAuthority"]
    stopped = compile_mechanics_ir(_ir(incomplete))
    assert stopped.status is CompilerStatus.unsupported and stopped.graph is None
    assert stopped.issues[0].code is CompilerIssueCode.requires_specialized_model

    mismatched_initial = _vibration_payload()
    mismatched_initial["state_conditions"][0]["quantity_ids"] = ["initialDisplacement"]
    mismatched = compile_mechanics_ir(_ir(mismatched_initial))
    assert mismatched.status is CompilerStatus.unsupported and mismatched.graph is None

    unsafe_forced = _vibration_payload()
    unsafe_forced["assumptions"] = [
        item for item in unsafe_forced["assumptions"] if item["assumption_id"] != "freeAuthority"
    ]
    unsafe_forced["assumptions"].append({
        "assumption_id": "forcedAuthority", "kind": "forced_vibration", "subject_id": "bodyA",
        "interval_id": "vibrationInterval", "disposition": "approved", "proposed_role": None,
        "proposed_value": None, "proposed_unit": None, "reason": "A general input is applied.",
        "evidence_refs": [],
    })
    unsafe_forced["symbols"].append(_symbol("forcing", "forcingQ", FORCE))
    unsafe_forced["quantities"].append(
        _quantity("forcingQ", "forcing", "force", "bodyA", FORCE, frame_id="vibrationFrame", interval_id="vibrationInterval", component="x")
    )
    unsafe_forced["interactions"].append({
        "interaction_id": "forcingInteraction", "kind": "applied_force",
        "participant_ids": ["bodyA"], "point_ids": [], "frame_id": "vibrationFrame",
        "interval_id": "vibrationInterval", "event_id": None,
        "quantity_ids": ["forcingQ"], "evidence_refs": [],
    })
    unsafe = compile_mechanics_ir(_ir(unsafe_forced))
    assert unsafe.status is CompilerStatus.unsupported and unsafe.graph is None


def test_vibration_initial_conditions_are_typed_and_quantity_provenance_is_reciprocal() -> None:
    result = compile_mechanics_ir(_ir(_vibration_payload()))
    assert result.graph is not None

    wrong_dimension = _vibration_payload()
    velocity_symbol = next(
        item for item in wrong_dimension["symbols"] if item["symbol_id"] == "v0"
    )
    velocity_symbol["dimension"] = LENGTH.model_dump(mode="json")
    velocity_quantity = next(
        item
        for item in wrong_dimension["quantities"]
        if item["quantity_id"] == "initialVelocity"
    )
    velocity_quantity.update(
        _quantity(
            "initialVelocity", "v0", "velocity", "bodyA", LENGTH,
            value=0.0, unit="m", frame_id="vibrationFrame",
            interval_id="vibrationInterval", event_id="initialEvent",
            component="x", provenance="explicit_source",
            evidence_refs=("initialEvidence",),
        )
    )
    rejected = compile_mechanics_ir(_ir(wrong_dimension))
    assert rejected.status is CompilerStatus.invalid and rejected.graph is None
    assert rejected.issues[0].code is CompilerIssueCode.dimension_mismatch

    for substituted_quantity_id in ("massQ", "danglingQuantity"):
        graph_payload = result.graph.model_dump(mode="python", warnings="none")
        condition = next(
            item
            for item in graph_payload["initial_conditions"]
            if item["derivative_order"] == 1
        )
        condition["source_quantity_ids"] = (substituted_quantity_id,)
        with pytest.raises(ValidationError, match="exact source quantity"):
            EquationGraph.model_validate(graph_payload)


def test_initial_condition_evidence_changes_identity_but_pure_id_rename_does_not() -> None:
    baseline = compile_mechanics_ir(_ir(_vibration_payload()))
    assert baseline.graph is not None
    baseline_condition_ids = tuple(
        item.condition_id for item in baseline.graph.initial_conditions
    )
    baseline_equation = next(
        item for item in baseline.graph.equations if item.law_id == "linear_vibration"
    )
    baseline_application = next(
        item for item in baseline.graph.applications if item.law_id == "linear_vibration"
    )

    renamed_payload = _rename(
        _vibration_payload(), {"initialEvidence": "renamedInitialEvidence"}
    )
    renamed = compile_mechanics_ir(_ir(renamed_payload))
    assert renamed.graph is not None
    assert renamed.graph.fingerprint == baseline.graph.fingerprint
    assert tuple(item.condition_id for item in renamed.graph.initial_conditions) == baseline_condition_ids
    assert next(
        item for item in renamed.graph.equations if item.law_id == "linear_vibration"
    ).equation_id == baseline_equation.equation_id
    assert next(
        item for item in renamed.graph.applications if item.law_id == "linear_vibration"
    ).application_id == baseline_application.application_id
    assert tuple(item.application_id for item in renamed.graph.applications) == tuple(
        item.application_id for item in baseline.graph.applications
    )

    changed_payload = _vibration_payload()
    changed_payload["source_evidence"][0].update(
        {
            "quote": "At the initial instant the displacement and velocity both vanish.",
            "source_span": {"start": 40, "end": 104},
            "occurrence_index": 1,
        }
    )
    changed = compile_mechanics_ir(_ir(changed_payload))
    assert changed.graph is not None
    assert changed.graph.fingerprint != baseline.graph.fingerprint
    assert tuple(item.condition_id for item in changed.graph.initial_conditions) != baseline_condition_ids
    changed_equation = next(
        item for item in changed.graph.equations if item.law_id == "linear_vibration"
    )
    changed_application = next(
        item for item in changed.graph.applications if item.law_id == "linear_vibration"
    )
    assert changed_equation.equation_id != baseline_equation.equation_id
    assert changed_application.application_id != baseline_application.application_id


def test_affine_redundancy_and_inconsistency_are_distinguished() -> None:
    x = SymbolRef(symbol_id="x", dimension=LENGTH)
    y = SymbolRef(symbol_id="y", dimension=LENGTH)
    two = LiteralNode(value=2.0)
    three = LiteralNode(value=3.0)
    four = LiteralNode(value=4.0, dimension=LENGTH)
    base = (
        Equality(left=Add(terms=(x, y), dimension=LENGTH), right=four),
        Equality(left=Subtract(left=x, right=y, dimension=LENGTH), right=four),
    )
    redundant = Equality(
        left=Add(
            terms=(
                Multiply(factors=(two, x), dimension=LENGTH),
                Multiply(factors=(two, y), dimension=LENGTH),
            ),
            dimension=LENGTH,
        ),
        right=Multiply(factors=(two, four), dimension=LENGTH),
    )
    contradictory = redundant.model_copy(
        update={"right": Multiply(factors=(three, four), dimension=LENGTH)}
    )
    consistent_rank = _linear_analysis(
        tuple(SimpleNamespace(expression=item) for item in (*base, redundant)),
        ("x", "y"),
        {},
    )
    conflicting_rank = _linear_analysis(
        tuple(SimpleNamespace(expression=item) for item in (*base, contradictory)),
        ("x", "y"),
        {},
    )
    assert consistent_rank == (2, 2, True)
    assert conflicting_rank == (2, 3, True)


def test_empty_equation_graph_is_underdetermined() -> None:

    under = compile_mechanics_ir(_ir(_single_unknown_payload([])))
    assert under.status is CompilerStatus.underdetermined and under.graph is not None
    assert under.graph.rank.structural_rank == 0 and under.graph.rank.unknown_count == 1


def test_inequality_is_preserved_but_not_counted_as_a_closing_equality() -> None:
    x = SymbolRef(symbol_id="x", dimension=LENGTH)
    payload = _affine_relation_payload(inconsistent=False)
    payload["constraints"].append(
        _constraint(
            "domainBound",
            Inequality(
                relation=InequalityRelation.ge,
                left=x,
                right=LiteralNode(value=0.0, dimension=LENGTH),
            ),
            kind="boundary",
            subjects=("bodyA",),
        )
        | {"interval_id": None, "evidence_refs": ["evidence1"]}
    )
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.underdetermined and result.graph is not None
    assert result.graph.rank.equality_count == 0
    assert result.graph.rank.inequality_count == 1
    assert len(result.graph.selected_equation_ids) == 0


def test_model_kinematic_equality_is_never_differentiated_into_authority() -> None:
    x = SymbolRef(symbol_id="x", dimension=LENGTH)
    y = SymbolRef(symbol_id="y", dimension=LENGTH)
    payload = _single_unknown_payload([
        Equality(
            left=Add(terms=(x, y), dimension=LENGTH),
            right=LiteralNode(value=0.0, dimension=LENGTH),
        )
    ])
    payload["constraints"][0]["kind"] = "kinematic"
    payload["constraints"][0]["interval_id"] = "interval1"
    payload["constraints"][0]["evidence_refs"] = ["evidence1"]
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "evidence1",
        "quote": "The coordinate sum remains fixed throughout the interval.",
        "source_span": {"start": 0, "end": 58}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["motion_intervals"] = [{
        "interval_id": "interval1", "order": 1, "subject_ids": ["bodyA"],
        "frame_id": None, "start_event_id": None, "end_event_id": None,
        "evidence_refs": ["evidence1"],
    }]
    payload["symbols"].extend([
        _symbol("y", "positionY", LENGTH),
        _symbol("v", "velocityX", VELOCITY),
        _symbol("t", "timeX", TIME),
    ])
    payload["quantities"].extend([
        _quantity("positionY", "y", "position", "bodyA", LENGTH, interval_id="interval1"),
        _quantity("velocityX", "v", "velocity", "bodyA", VELOCITY, interval_id="interval1"),
        _quantity("timeX", "t", "time", "bodyA", TIME, interval_id="interval1"),
    ])
    payload["quantities"][0]["interval_id"] = "interval1"
    payload["queries"][0] = {
        "query_id": "queryV",
        "target": {
            "role": "velocity", "subject_id": "bodyA", "point_id": None,
            "frame_id": None, "interval_id": "interval1", "event_id": None,
            "component": "unspecified", "direction": None,
            "target_quantity_id": "velocityX",
        },
        "output_unit": "m/s",
        "output_dimension": VELOCITY.model_dump(mode="json"),
        "shape": "scalar",
        "evidence_refs": [],
    }
    result = compile_mechanics_ir(_ir(payload))
    assert result.status in {
        CompilerStatus.ready,
        CompilerStatus.overdetermined,
        CompilerStatus.underdetermined,
        CompilerStatus.unsupported,
    }
    assert result.graph is not None
    assert "differentiated_constraint" not in {item.law_id for item in result.graph.equations}
    assert CompilerIssueCode.constraint_not_authoritative in {item.code for item in result.issues}


def test_unknown_time_query_remains_unknown_while_source_known_time_is_ready() -> None:
    unknown_payload = _single_unknown_payload([])
    unknown_payload["symbols"] = [_symbol("t", "timeX", TIME)]
    unknown_payload["quantities"] = [_quantity("timeX", "t", "time", "bodyA", TIME)]
    unknown_payload["queries"][0]["target"].update(
        {"role": "time", "target_quantity_id": "timeX"}
    )
    unknown_payload["queries"][0]["output_unit"] = "s"
    unknown_payload["queries"][0]["output_dimension"] = TIME.model_dump(mode="json")
    unknown = compile_mechanics_ir(_ir(unknown_payload))
    assert unknown.status is CompilerStatus.underdetermined and unknown.graph is not None
    assert unknown.graph.rank.unknown_count == 1

    known_payload = deepcopy(unknown_payload)
    known_payload["quantities"] = [
        _quantity("timeX", "t", "time", "bodyA", TIME, value=2.0, unit="s")
    ]
    known = compile_mechanics_ir(_ir(known_payload))
    assert known.status is CompilerStatus.ready and known.graph is not None
    assert known.graph.rank.unknown_count == 0


def test_state_expression_cannot_override_server_state_rule() -> None:
    payload = _single_unknown_payload([])
    payload["source_evidence"] = [{
        "kind": "text", "evidence_id": "stateEvidence",
        "quote": "The particle is at rest at the stated event.",
        "source_span": {"start": 0, "end": 45}, "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["symbols"] = [_symbol("v", "velocityX", VELOCITY)]
    payload["quantities"] = [_quantity("velocityX", "v", "velocity", "bodyA", VELOCITY)]
    payload["state_conditions"] = [{
        "state_condition_id": "restState",
        "kind": "motion",
        "state": "at_rest",
        "subject_id": "bodyA",
        "interval_id": None,
        "event_id": None,
        "expression": Equality(
            left=SymbolRef(symbol_id="v", dimension=VELOCITY),
            right=LiteralNode(value=123.0, dimension=VELOCITY),
        ),
        "quantity_ids": ["velocityX"],
        "evidence_refs": ["stateEvidence"],
    }]
    payload["queries"][0]["target"].update(
        {"role": "velocity", "target_quantity_id": "velocityX"}
    )
    payload["queries"][0]["output_unit"] = "m/s"
    payload["queries"][0]["output_dimension"] = VELOCITY.model_dump(mode="json")
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.ready and result.graph is not None
    equation = next(item for item in result.graph.equations if item.law_id == "state_at_rest")
    assert isinstance(equation.expression, Equality)
    assert isinstance(equation.expression.right, LiteralNode)
    assert equation.expression.right.value == 0.0
    assert CompilerIssueCode.constraint_not_authoritative in {item.code for item in result.issues}


def test_mixed_frame_explicit_relation_is_rejected() -> None:
    payload = _affine_relation_payload(inconsistent=False)
    payload["reference_frames"] = [
        {
            "frame_id": frame_id,
            "frame_type": "cartesian_1d",
            "origin": {"kind": "world"},
            "axes": [{"axis": "x", "direction": {"kind": "axis", "frame_id": frame_id, "axis": "x", "sign": 1}}],
            "parent_frame_id": None,
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": [],
        }
        for frame_id in ("frameLeft", "frameRight")
    ]
    next(item for item in payload["quantities"] if item["quantity_id"] == "positionX")["frame_id"] = "frameLeft"
    next(item for item in payload["quantities"] if item["quantity_id"] == "positionY")["frame_id"] = "frameRight"
    result = compile_mechanics_ir(_ir(payload))
    assert result.status is CompilerStatus.invalid and result.graph is None
    assert result.issues[0].code is CompilerIssueCode.invalid_binding


def test_scope_reference_gate_rejects_nonreciprocal_events_and_component_mixing() -> None:
    nonreciprocal = _problem_payload()
    nonreciprocal["events"] = [{
        "event_id": "startEvent", "kind": "start", "subject_ids": ["bodyA"],
        "interval_ids": [], "time_quantity_id": None, "evidence_refs": [],
    }]
    nonreciprocal["motion_intervals"][0]["start_event_id"] = "startEvent"
    invalid = compile_mechanics_ir(_ir(nonreciprocal))
    assert invalid.status is CompilerStatus.invalid and invalid.graph is None
    assert invalid.issues[0].code is CompilerIssueCode.invalid_binding

    mixed = _problem_payload()
    next(item for item in mixed["quantities"] if item["quantity_id"] == "tensionB")["component"] = "y"
    direction = next(item for item in mixed["quantities"] if item["quantity_id"] == "tensionB")["direction"]
    direction["axis"] = "y"
    result = compile_mechanics_ir(_ir(mixed))
    assert result.status is CompilerStatus.invalid and result.graph is None
    assert result.issues[0].code is CompilerIssueCode.invalid_binding


def test_blocking_ambiguity_stops_but_diagnostic_feature_label_cannot_route() -> None:
    ambiguous_payload = _problem_payload()
    ambiguous_payload["ambiguities"] = [{
        "ambiguity_id": "ambiguity1", "kind": "direction", "referenced_ids": ["bodyA"],
        "description": "axis sign is unresolved", "blocking": True, "evidence_refs": [],
    }]
    ambiguous = compile_mechanics_ir(_ir(ambiguous_payload))
    assert ambiguous.status is CompilerStatus.blocked and ambiguous.graph is None

    advanced_payload = _problem_payload()
    advanced_payload["unsupported_features"] = [{
        "feature_code": "variable_mass", "description": "mass flow law is not supplied",
        "referenced_ids": ["inventedDiagnosticRef"], "evidence_refs": [],
    }]
    advanced = compile_mechanics_ir(_ir(advanced_payload))
    assert advanced.status is CompilerStatus.ready and advanced.graph is not None
    assert CompilerIssueCode.unsupported_feature in {item.code for item in advanced.issues}

    structural_payload = _problem_payload()
    structural_payload["symbols"].append(_symbol("massLater", "massLaterQ", MASS))
    structural_payload["quantities"].append(
        _quantity(
            "massLaterQ", "massLater", "mass", "bodyA", MASS,
            value=1.5, unit="kg", interval_id="interval1",
        )
    )
    structural = compile_mechanics_ir(_ir(structural_payload))
    assert structural.status is CompilerStatus.unsupported and structural.graph is None
    assert structural.issues[0].code is CompilerIssueCode.requires_specialized_model


def test_resource_budgets_stop_without_truncating_the_graph() -> None:
    ir = _ir()
    approved, corrections, assumptions = _authority_bundle(ir)
    result = MechanicsCompiler(CompilerLimits(max_equations=1, max_applications=1)).compile(
        ir,
        validated_ir_authorization=authorize_validated_mechanics_ir(ir),
        approved_assumption_ids=approved,
        authorized_corrections=corrections,
        authorized_assumptions=assumptions,
    )
    assert result.status is CompilerStatus.resource_limit
    assert result.graph is None
    assert result.issues[0].code is CompilerIssueCode.resource_limit


def test_hint_cannot_create_or_remove_an_applicable_equation() -> None:
    baseline = compile_mechanics_ir(_ir())
    payload = _problem_payload()
    payload["principle_hints"] = [{
        "hint_id": "hint1", "principle": "vibration", "scope_ids": ["bodyA"],
        "evidence_refs": [], "model_confidence": 1.0,
    }]
    hinted = compile_mechanics_ir(_ir(payload))
    assert baseline.graph is not None and hinted.graph is not None
    assert baseline.graph.fingerprint == hinted.graph.fingerprint
    assert baseline.graph.selected_equation_ids == hinted.graph.selected_equation_ids
    assert {item.expression_fingerprint for item in baseline.graph.equations} == {
        item.expression_fingerprint for item in hinted.graph.equations
    }


def test_non_ir_payload_and_ast_like_string_are_never_interpreted() -> None:
    x = SymbolRef(symbol_id="x", dimension=LENGTH)
    payload = _single_unknown_payload(
        [Equality(left=x, right=LiteralNode(value=1.0, dimension=LENGTH))]
    )
    payload["constraints"][0]["expression"] = "__import__('os').system('echo nope')"
    result = compile_mechanics_ir(payload)
    assert result.status is CompilerStatus.invalid and result.graph is None
    with pytest.raises(ValidationError):
        MechanicsProblemIRV1.model_validate(payload)


def test_graph_contract_is_recursively_immutable() -> None:
    result = compile_mechanics_ir(_ir())
    assert result.graph is not None
    with pytest.raises(ValidationError, match="frozen"):
        result.graph.query_id = "changed"
    with pytest.raises(ValidationError, match="frozen"):
        result.graph.rank.structural_rank = 0
    with pytest.raises(AttributeError):
        result.graph.equations.append(result.graph.equations[0])


def test_catalog_is_generic_typed_and_covers_core_principles() -> None:
    catalog = core_law_catalog()
    assert len({item.law_id for item in catalog}) == len(catalog)
    assert {
        "kinematics", "newton_second_law", "work_energy", "impulse_momentum",
        "rigid_body_kinematics", "vibration",
    }.issubset({item.category for item in catalog})
    assert {"particle_newton_second", "rigid_newton_euler", "linear_vibration"}.issubset(
        {item.law_id for item in catalog}
    )


def test_production_compiler_has_no_dynamic_math_or_evaluation_routing_tokens() -> None:
    mechanics_root = Path(__file__).parents[1] / "engine" / "mechanics"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for directory in (mechanics_root / "laws", mechanics_root / "compiler")
        for path in sorted(directory.glob("*.py"))
    )
    forbidden = (
        r"\beval\s*\(", r"\bexec\s*\(", r"\bsympify\b",
        r"\bsystem_type\b", r"\bsubtype\b", r"\braw_text\b",
        r"\bcorpus\b", r"\bfamily\b", r"\bcase\b",
        r"\bexpected_answer\b", r"\bgold\b", r"\bPDF\b",
    )
    assert not [pattern for pattern in forbidden if re.search(pattern, source, re.IGNORECASE)]
