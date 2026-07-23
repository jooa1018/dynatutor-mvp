from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import DimensionVector, Equality, Inequality
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity
from engine.solvers.curves import FlatCurveFrictionSolver
from test_phase56_mechanics_incline_hanging_same_fixture_parity import (
    _collect_fixture_identifiers,
    _rename_fixture_identifiers,
)
from test_phase56_mechanics_compiler import (
    ACCELERATION,
    DIMENSIONLESS,
    FORCE,
    LENGTH,
    MASS,
    VELOCITY,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class FlatCurveCase:
    case_id: str
    radius: tuple[float, str]
    coefficient: float
    gravity: tuple[float, str] = (9.81, "m/s^2")
    mass: tuple[float, str] = (1000.0, "kg")

    @property
    def expected_si(self) -> float:
        return math.sqrt(
            self.coefficient
            * _si(self.gravity, ACCELERATION)
            * _si(self.radius, LENGTH)
        )


def _si(raw: tuple[float, str], dimension: DimensionVector) -> float:
    from engine.mechanics.units import normalize_quantity

    value = normalize_quantity(str(raw[0]), raw[1], "scalar", dimension).value
    assert isinstance(value, float)
    return value


BASE = FlatCurveCase("base", (50.0, "m"), 0.3)
ZERO_MU = FlatCurveCase("zero-mu", (50.0, "m"), 0.0)
WIDE_CURVE = FlatCurveCase("wide-curve", (120.0, "m"), 0.4)
MASS_SCALED = FlatCurveCase("mass-scaled", (50.0, "m"), 0.3, mass=(2500.0, "kg"))
MIXED_UNITS = FlatCurveCase(
    "mixed-units", (5000.0, "cm"), 0.25, gravity=(981.0, "cm/s^2"), mass=(2_000_000.0, "g")
)
VALID_CASES = (BASE, ZERO_MU, WIDE_CURVE, MASS_SCALED, MIXED_UNITS)


def _direction(axis: str, sign: int = 1) -> dict[str, object]:
    return {
        "kind": "axis",
        "frame_id": "curveFrame",
        "axis": axis,
        "sign": sign,
    }


def _q(
    quantity_id: str,
    symbol_id: str,
    role: str,
    subject_id: str,
    dimension: DimensionVector,
    *,
    value: tuple[float, str] | None = None,
    frame_id: str | None = None,
    interval_id: str | None = None,
    point_id: str | None = None,
    component: str = "unspecified",
    axis: str | None = None,
    sign: int = 1,
) -> dict[str, object]:
    raw_value, unit = value if value is not None else (None, "1")
    item = _quantity(
        quantity_id,
        symbol_id,
        role,
        subject_id,
        dimension,
        value=raw_value,
        unit=unit,
        frame_id=frame_id,
        interval_id=interval_id,
        point_id=point_id,
        component=component,
        provenance="explicit_source" if value is not None else "inferred",
        evidence_refs=("curveEvidence",),
    )
    if axis is not None:
        item["direction"] = _direction(axis, sign)
    return item


def _base_payload(*, banked: bool = False) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["source_evidence"] = [
        {
            "kind": "text",
            "evidence_id": "curveEvidence",
            "quote": "typed uniform circular road contact",
            "source_span": {"start": 0, "end": 35},
            "quantity_span": None,
            "occurrence_index": 0,
        }
    ]
    road_primitive = "incline" if banked else "surface"
    payload["entities"] = [
        {
            "entity_id": "vehicle",
            "primitive": "particle",
            "label": "vehicle",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": ["curveEvidence"],
            "model_confidence": None,
        },
        {
            "entity_id": "road",
            "primitive": road_primitive,
            "label": "road",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": ["curveEvidence"],
            "model_confidence": None,
        },
        {
            "entity_id": "world",
            "primitive": "environment",
            "label": "world",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": ["curveEvidence"],
            "model_confidence": None,
        },
    ]
    payload["points"] = [
        {
            "point_id": "contactPoint",
            "role": "contact",
            "owner_entity_id": "vehicle",
            "frame_id": "curveFrame",
            "label": "C",
            "evidence_refs": ["curveEvidence"],
        }
    ]
    payload["reference_frames"] = [
        {
            "frame_id": "worldFrame",
            "frame_type": "cartesian_2d",
            "origin": {"kind": "world"},
            "axes": [
                {"axis": "x", "direction": {"kind": "axis", "frame_id": "worldFrame", "axis": "x", "sign": 1}},
                {"axis": "y", "direction": {"kind": "axis", "frame_id": "worldFrame", "axis": "y", "sign": 1}},
            ],
            "parent_frame_id": None,
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": ["curveEvidence"],
        },
        {
            "frame_id": "curveFrame",
            "frame_type": "tangential_normal",
            "origin": {"kind": "entity", "entity_id": "road"},
            "axes": [
                {"axis": "tangent", "direction": _direction("tangent")},
                {"axis": "normal", "direction": _direction("normal")},
            ],
            "parent_frame_id": "worldFrame",
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": ["curveEvidence"],
        },
    ]
    payload["motion_intervals"] = [
        {
            "interval_id": "curveInterval",
            "order": 1,
            "subject_ids": ["vehicle", "road", "world"],
            "frame_id": "curveFrame",
            "start_event_id": None,
            "end_event_id": None,
            "evidence_refs": ["curveEvidence"],
        }
    ]
    payload["events"] = []
    payload["constraints"] = []
    return payload


def _payload(case: FlatCurveCase) -> dict[str, object]:
    payload = _base_payload()
    payload["metadata"].update(
        system_type="diagnosticFlatCurve",
        subtype="diagnosticMaximumSpeed",
        model_id="sameFixtureFlatCurve",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    quantities = [
        _q("massQ", "mass", "mass", "vehicle", MASS, value=case.mass),
        _q("gravityQ", "gravity", "gravity", "world", ACCELERATION, value=case.gravity),
        _q("radiusQ", "radius", "radius", "vehicle", LENGTH, value=case.radius),
        _q("coefficientQ", "coefficient", "coefficient_friction", "vehicle", DIMENSIONLESS, value=(case.coefficient, "1")),
        _q("speedQ", "speed", "speed", "vehicle", VELOCITY, frame_id="curveFrame", interval_id="curveInterval", component="magnitude"),
        _q("normalAccelerationQ", "normalAcceleration", "acceleration", "vehicle", ACCELERATION, frame_id="curveFrame", interval_id="curveInterval", component="normal", axis="normal"),
        _q("normalForceQ", "normalForce", "force", "vehicle", FORCE, interval_id="curveInterval", point_id="contactPoint", component="magnitude"),
        _q("frictionForceQ", "frictionForce", "force", "vehicle", FORCE, frame_id="curveFrame", interval_id="curveInterval", point_id="contactPoint", component="normal", axis="normal"),
    ]
    payload["symbols"] = [
        _symbol(item["symbol_id"], item["quantity_id"], DimensionVector.model_validate(item["dimension"]))
        for item in quantities
    ]
    payload["quantities"] = quantities
    payload["geometry"] = [
        {
            "relation_id": "curveRadius",
            "kind": "radius",
            "participant_ids": ["vehicle", "road"],
            "expression": None,
            "quantity_ids": ["radiusQ"],
            "interval_id": "curveInterval",
            "evidence_refs": ["curveEvidence"],
        },
        {
            "relation_id": "vehicleOnRoad",
            "kind": "lies_on",
            "participant_ids": ["vehicle", "road"],
            "expression": None,
            "quantity_ids": [],
            "interval_id": "curveInterval",
            "evidence_refs": ["curveEvidence"],
        },
    ]
    payload["interactions"] = [
        {
            "interaction_id": "gravityInteraction",
            "kind": "gravity",
            "participant_ids": ["vehicle", "world"],
            "point_ids": [],
            "frame_id": None,
            "interval_id": "curveInterval",
            "event_id": None,
            "quantity_ids": ["massQ", "gravityQ"],
            "evidence_refs": ["curveEvidence"],
        },
        {
            "interaction_id": "contactInteraction",
            "kind": "contact",
            "participant_ids": ["vehicle", "road"],
            "point_ids": ["contactPoint"],
            "frame_id": "curveFrame",
            "interval_id": "curveInterval",
            "event_id": None,
            "quantity_ids": [
                "radiusQ",
                "coefficientQ",
                "speedQ",
                "normalAccelerationQ",
                "normalForceQ",
                "frictionForceQ",
            ],
            "evidence_refs": ["curveEvidence"],
        },
    ]
    payload["state_conditions"] = [
        {
            "state_condition_id": "touchingState",
            "kind": "contact",
            "state": "touching",
            "subject_id": "vehicle",
            "interval_id": "curveInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": ["normalForceQ"],
            "evidence_refs": ["curveEvidence"],
        },
        {
            "state_condition_id": "limitingState",
            "kind": "regime",
            "state": "sticking",
            "subject_id": "vehicle",
            "interval_id": "curveInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": ["frictionForceQ", "normalForceQ", "coefficientQ"],
            "evidence_refs": ["curveEvidence"],
        },
        {
            "state_condition_id": "vehicleMotion",
            "kind": "motion",
            "state": "moving",
            "subject_id": "vehicle",
            "interval_id": "curveInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": ["speedQ"],
            "evidence_refs": ["curveEvidence"],
        },
        {
            "state_condition_id": "roadMotion",
            "kind": "motion",
            "state": "at_rest",
            "subject_id": "road",
            "interval_id": "curveInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": [],
            "evidence_refs": ["curveEvidence"],
        },
    ]
    payload["assumptions"] = [
        {
            "assumption_id": "horizontalRoad",
            "kind": "horizontal_surface",
            "subject_id": "road",
            "interval_id": "curveInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "The fixed road surface is horizontal.",
            "evidence_refs": ["curveEvidence"],
        },
        {
            "assumption_id": "uniformCircle",
            "kind": "uniform_circular_motion",
            "subject_id": "vehicle",
            "interval_id": "curveInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "The speed is evaluated on a uniform circular path.",
            "evidence_refs": ["curveEvidence"],
        },
        {
            "assumption_id": "limitingFriction",
            "kind": "limiting_static_friction",
            "subject_id": "vehicle",
            "interval_id": "curveInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "Static friction is at its evidenced limiting value.",
            "evidence_refs": ["curveEvidence"],
        },
    ]
    payload["queries"] = [
        {
            "query_id": "curveSpeedQuery",
            "target": {
                "role": "speed",
                "subject_id": "vehicle",
                "point_id": None,
                "frame_id": "curveFrame",
                "interval_id": "curveInterval",
                "event_id": None,
                "component": "magnitude",
                "direction": None,
                "target_quantity_id": "speedQ",
            },
            "output_unit": "m/s",
            "output_dimension": VELOCITY.model_dump(mode="json"),
            "shape": "scalar",
            "evidence_refs": ["curveEvidence"],
        }
    ]
    return payload


def _compile(case: FlatCurveCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: FlatCurveCase):
    compiled = _compile(case)
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    selected = next(
        item
        for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    values = {
        item.symbol.symbol_id: item.known_si_value
        for item in compiled.graph.symbols
        if item.known_si_value is not None
    }
    values.update({item.symbol_id: item.value_si for item in selected.candidate.values})
    assert isinstance(selected.candidate.query_value_si, float)
    return compiled.graph, result, selected.candidate.query_value_si, values


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_flat_curve_limits_zero_units_and_residuals(case: FlatCurveCase) -> None:
    graph, result, value, values = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    expected_curve_law = (
        "flat_curve_zero_friction_boundary"
        if case.coefficient == 0.0
        else "particle_normal_acceleration"
    )
    assert {item.law_id for item in graph.equations} == {
        expected_curve_law,
        "horizontal_gravity_normal_projection",
        "particle_newton_second",
        "contact_limiting_static_friction",
        "contact_normal_bound",
        "translational_speed_nonnegative",
    }
    assert result.plan.primary_backend is (
        SolveBackendKind.linear_symbolic
        if case.coefficient == 0.0
        else SolveBackendKind.polynomial_symbolic
    )
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert values["normalForce"] - values["mass"] * values["gravity"] == pytest.approx(0.0, abs=1.0e-8)
    radius_si = values.get("radius", _si(case.radius, LENGTH))
    assert values["normalAcceleration"] - value * value / radius_si == pytest.approx(0.0, abs=1.0e-8)
    assert values["frictionForce"] - values["mass"] * values["normalAcceleration"] == pytest.approx(0.0, abs=1.0e-8)
    assert values["frictionForce"] - values["coefficient"] * values["normalForce"] == pytest.approx(0.0, abs=1.0e-8)


def test_flat_curve_mass_cancels_and_negative_root_is_rejected() -> None:
    _, first, first_value, _ = _solve(BASE)
    _, _, second_value, _ = _solve(MASS_SCALED)
    assert first_value == pytest.approx(second_value, abs=1.0e-9)
    roots = sorted(float(item.query_value_si) for item in first.candidate_set.candidates)
    assert roots == pytest.approx([-BASE.expected_si, BASE.expected_si])
    assert len(first.verified_candidates) == 1
    rejected = next(item for item in first.verification_outcomes if not item.passed)
    check = next(item for item in rejected.checks if item.kind is VerificationCheckKind.inequality)
    assert check.status is VerificationCheckStatus.failed


@pytest.mark.parametrize("assumption_id", ("horizontalRoad", "uniformCircle", "limitingFriction"))
def test_flat_curve_missing_authority_fails_closed(assumption_id: str) -> None:
    payload = _payload(BASE)
    payload["assumptions"] = [
        item for item in payload["assumptions"] if item["assumption_id"] != assumption_id
    ]
    assert compile_mechanics_ir(_ir(payload)).status is not CompilerStatus.ready


def test_flat_curve_invalid_domains_regime_direction_query_and_extra_actor_fail_closed() -> None:
    for quantity_id, value in (("radiusQ", -1.0), ("coefficientQ", -0.1), ("gravityQ", 0.0)):
        payload = _payload(BASE)
        item = next(item for item in payload["quantities"] if item["quantity_id"] == quantity_id)
        item["raw_value"] = str(value)
        item["si_value"] = value
        assert compile_mechanics_ir(_ir(payload)).status is CompilerStatus.invalid

    wrong_regime = _payload(BASE)
    next(item for item in wrong_regime["state_conditions"] if item["state_condition_id"] == "limitingState")["state"] = "sliding"
    assert compile_mechanics_ir(_ir(wrong_regime)).status is not CompilerStatus.ready

    wrong_direction = _payload(BASE)
    next(item for item in wrong_direction["quantities"] if item["quantity_id"] == "frictionForceQ")["direction"] = _direction("normal", -1)
    assert compile_mechanics_ir(_ir(wrong_direction)).status is not CompilerStatus.ready

    wrong_unit = _payload(BASE)
    wrong_unit["queries"][0]["output_unit"] = "kg"
    assert compile_mechanics_ir(_ir(wrong_unit)).status is CompilerStatus.invalid

    extra = _payload(BASE)
    extra["entities"].append(
        {
            "entity_id": "passenger",
            "primitive": "particle",
            "label": "passenger",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": ["curveEvidence"],
            "model_confidence": None,
        }
    )
    assert compile_mechanics_ir(_ir(extra)).status is not CompilerStatus.ready


def test_flat_curve_metadata_has_no_authority() -> None:
    first = _compile(BASE)
    changed = _payload(BASE)
    changed["metadata"].update(
        system_type="banked_curve_no_friction",
        subtype="unrelated",
        model_id="different",
        source_text_sha256="f" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint


def test_flat_curve_identifier_and_record_order_invariance() -> None:
    original_ir = _ir(_payload(BASE))
    original = compile_mechanics_ir(original_ir)
    assert original.status is CompilerStatus.ready, original.issues
    assert original.graph is not None

    reordered_payload = original_ir.model_dump(mode="python", warnings="none")
    for collection_name in (
        'source_evidence',
        'entities',
        'points',
        'reference_frames',
        'motion_intervals',
        'symbols',
        'quantities',
        'geometry',
        'interactions',
        'state_conditions',
        'assumptions',
    ):
        reordered_payload[collection_name] = list(
            reversed(reordered_payload[collection_name])
        )
    reordered = compile_mechanics_ir(_ir(reordered_payload))

    identifiers = sorted(_collect_fixture_identifiers(reordered_payload))
    mapping = {
        identifier: f"renamedFlatCurveIdentifier{index}"
        for index, identifier in enumerate(identifiers, start=1)
    }
    renamed_payload = _rename_fixture_identifiers(reordered_payload, mapping)
    assert isinstance(renamed_payload, dict)
    renamed = compile_mechanics_ir(_ir(renamed_payload))

    for compiled in (reordered, renamed):
        assert compiled.status is CompilerStatus.ready, compiled.issues
        assert compiled.graph is not None
        assert compiled.graph.fingerprint == original.graph.fingerprint
        assert compiled.graph.selected_equation_ids == original.graph.selected_equation_ids
        assert Counter(item.law_id for item in compiled.graph.equations) == Counter(
            item.law_id for item in original.graph.equations
        )


@pytest.mark.slow
@pytest.mark.parametrize("case", (BASE, ZERO_MU, WIDE_CURVE, MIXED_UNITS), ids=lambda item: item.case_id)
def test_flat_curve_same_fixture_legacy_parity(case: FlatCurveCase) -> None:
    _, _, generic, _ = _solve(case)
    legacy = FlatCurveFrictionSolver().solve(
        CanonicalProblem(
            system_type="flat_curve_friction",
            raw_text="",
            knowns={
                "R": Quantity("R", _si(case.radius, LENGTH), "m"),
                "mu": Quantity("mu", case.coefficient, "1"),
                "g": Quantity("g", _si(case.gravity, ACCELERATION), "m/s^2"),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
        )
    )
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None
    assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
