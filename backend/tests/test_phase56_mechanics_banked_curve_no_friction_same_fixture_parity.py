from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity
from engine.solvers.curves import BankedCurveNoFrictionSolver
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
    _symbol,
    compile_mechanics_ir,
)
from test_phase56_mechanics_flat_curve_friction_same_fixture_parity import (
    _base_payload,
    _direction,
    _q,
    _si,
)


@dataclass(frozen=True)
class BankedCurveCase:
    case_id: str
    radius: tuple[float, str]
    angle: tuple[float, str]
    gravity: tuple[float, str] = (9.81, "m/s^2")
    mass: tuple[float, str] = (1000.0, "kg")

    @property
    def angle_rad(self) -> float:
        return _si(self.angle, DIMENSIONLESS)

    @property
    def expected_si(self) -> float:
        return math.sqrt(
            _si(self.gravity, ACCELERATION)
            * _si(self.radius, LENGTH)
            * math.tan(self.angle_rad)
        )


BASE = BankedCurveCase("base", (80.0, "m"), (15.0, "deg"))
STEEPER = BankedCurveCase("steeper", (80.0, "m"), (30.0, "deg"))
WIDE = BankedCurveCase("wide", (150.0, "m"), (20.0, "deg"))
MASS_SCALED = BankedCurveCase(
    "mass-scaled", (80.0, "m"), (15.0, "deg"), mass=(2800.0, "kg")
)
MIXED_UNITS = BankedCurveCase(
    "mixed-units",
    (8000.0, "cm"),
    (math.pi / 12.0, "rad"),
    gravity=(981.0, "cm/s^2"),
    mass=(1_000_000.0, "g"),
)
VALID_CASES = (BASE, STEEPER, WIDE, MASS_SCALED, MIXED_UNITS)


def _payload(case: BankedCurveCase) -> dict[str, object]:
    payload = _base_payload(banked=True)
    payload["metadata"].update(
        system_type="diagnosticBankedCurve",
        subtype="diagnosticDesignSpeed",
        model_id="sameFixtureBankedCurve",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    quantities = [
        _q("massQ", "mass", "mass", "vehicle", MASS, value=case.mass),
        _q("gravityQ", "gravity", "gravity", "world", ACCELERATION, value=case.gravity),
        _q("radiusQ", "radius", "radius", "vehicle", LENGTH, value=case.radius),
        _q("angleQ", "bankAngle", "angle", "road", DIMENSIONLESS, value=case.angle),
        _q(
            "speedQ",
            "speed",
            "speed",
            "vehicle",
            VELOCITY,
            frame_id="curveFrame",
            interval_id="curveInterval",
            component="magnitude",
        ),
        _q(
            "normalAccelerationQ",
            "normalAcceleration",
            "acceleration",
            "vehicle",
            ACCELERATION,
            frame_id="curveFrame",
            interval_id="curveInterval",
            component="normal",
            axis="normal",
        ),
        _q(
            "normalForceQ",
            "normalForce",
            "force",
            "vehicle",
            FORCE,
            interval_id="curveInterval",
            point_id="contactPoint",
            component="magnitude",
        ),
    ]
    payload["symbols"] = [
        _symbol(
            item["symbol_id"],
            item["quantity_id"],
            DimensionVector.model_validate(item["dimension"]),
        )
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
        {
            "relation_id": "roadBankAngle",
            "kind": "angle",
            "participant_ids": ["vehicle", "road"],
            "expression": None,
            "quantity_ids": ["angleQ"],
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
                "angleQ",
                "speedQ",
                "normalAccelerationQ",
                "normalForceQ",
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
            "state_condition_id": "frictionlessState",
            "kind": "regime",
            "state": "inactive",
            "subject_id": "vehicle",
            "interval_id": "curveInterval",
            "event_id": None,
            "expression": None,
            "quantity_ids": [],
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
            "assumption_id": "frictionlessContact",
            "kind": "frictionless_contact",
            "subject_id": "vehicle",
            "interval_id": "curveInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "The road contact is explicitly frictionless.",
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


def _compile(case: BankedCurveCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: BankedCurveCase):
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
def test_banked_curve_design_speed_units_and_force_residuals(case: BankedCurveCase) -> None:
    graph, result, value, values = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    assert {item.law_id for item in graph.equations} == {
        "particle_normal_acceleration",
        "banked_curve_vertical_balance",
        "banked_curve_inward_balance",
        "contact_normal_bound",
        "translational_speed_nonnegative",
    }
    assert result.plan.primary_backend is SolveBackendKind.polynomial_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    angle = case.angle_rad
    assert values["normalForce"] * math.cos(angle) - values["mass"] * values["gravity"] == pytest.approx(0.0, abs=1.0e-8)
    assert values["normalForce"] * math.sin(angle) - values["mass"] * values["normalAcceleration"] == pytest.approx(0.0, abs=1.0e-8)
    assert values["normalAcceleration"] - value * value / values["radius"] == pytest.approx(0.0, abs=1.0e-8)


def test_banked_curve_mass_cancels_and_negative_root_is_rejected() -> None:
    _, first, first_value, _ = _solve(BASE)
    _, _, second_value, _ = _solve(MASS_SCALED)
    assert first_value == pytest.approx(second_value, abs=1.0e-9)
    roots = sorted(float(item.query_value_si) for item in first.candidate_set.candidates)
    assert roots == pytest.approx([-BASE.expected_si, BASE.expected_si])
    assert len(first.verified_candidates) == 1
    rejected = next(item for item in first.verification_outcomes if not item.passed)
    check = next(item for item in rejected.checks if item.kind is VerificationCheckKind.inequality)
    assert check.status is VerificationCheckStatus.failed


@pytest.mark.parametrize("assumption_id", ("uniformCircle", "frictionlessContact"))
def test_banked_curve_missing_authority_fails_closed(assumption_id: str) -> None:
    payload = _payload(BASE)
    payload["assumptions"] = [
        item for item in payload["assumptions"] if item["assumption_id"] != assumption_id
    ]
    assert compile_mechanics_ir(_ir(payload)).status is not CompilerStatus.ready


def test_banked_curve_invalid_domains_regime_geometry_query_and_extra_force_fail_closed() -> None:
    for quantity_id, value in (("radiusQ", -1.0), ("gravityQ", 0.0)):
        payload = _payload(BASE)
        item = next(item for item in payload["quantities"] if item["quantity_id"] == quantity_id)
        item["raw_value"] = str(value)
        item["si_value"] = value
        assert compile_mechanics_ir(_ir(payload)).status is CompilerStatus.invalid

    for angle in (0.0, math.pi / 2.0, -0.1):
        payload = _payload(BASE)
        item = next(item for item in payload["quantities"] if item["quantity_id"] == "angleQ")
        item["raw_value"] = str(angle)
        item["raw_unit"] = "rad"
        item["si_value"] = angle
        item["si_unit"] = "rad"
        assert compile_mechanics_ir(_ir(payload)).status is CompilerStatus.invalid

    wrong_regime = _payload(BASE)
    next(item for item in wrong_regime["state_conditions"] if item["state_condition_id"] == "frictionlessState")["state"] = "sticking"
    assert compile_mechanics_ir(_ir(wrong_regime)).status is not CompilerStatus.ready

    wrong_geometry = _payload(BASE)
    next(item for item in wrong_geometry["geometry"] if item["relation_id"] == "roadBankAngle")["quantity_ids"] = []
    assert compile_mechanics_ir(_ir(wrong_geometry)).status is not CompilerStatus.ready

    wrong_unit = _payload(BASE)
    wrong_unit["queries"][0]["output_unit"] = "kg"
    assert compile_mechanics_ir(_ir(wrong_unit)).status is CompilerStatus.invalid

    extra_force = _payload(BASE)
    extra = _q(
        "frictionForceQ",
        "frictionForce",
        "force",
        "vehicle",
        FORCE,
        frame_id="curveFrame",
        interval_id="curveInterval",
        point_id="contactPoint",
        component="normal",
        axis="normal",
    )
    extra_force["quantities"].append(extra)
    extra_force["symbols"].append(_symbol("frictionForce", "frictionForceQ", FORCE))
    next(item for item in extra_force["interactions"] if item["interaction_id"] == "contactInteraction")["quantity_ids"].append("frictionForceQ")
    assert compile_mechanics_ir(_ir(extra_force)).status is not CompilerStatus.ready


def test_banked_curve_metadata_has_no_authority() -> None:
    first = _compile(BASE)
    changed = _payload(BASE)
    changed["metadata"].update(
        system_type="flat_curve_friction",
        subtype="unrelated",
        model_id="different",
        source_text_sha256="e" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint


def test_banked_curve_identifier_and_record_order_invariance() -> None:
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
        identifier: f"renamedBankedCurveIdentifier{index}"
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
@pytest.mark.parametrize("case", (BASE, STEEPER, WIDE), ids=lambda item: item.case_id)
def test_banked_curve_same_fixture_legacy_parity(case: BankedCurveCase) -> None:
    _, _, generic, _ = _solve(case)
    angle_deg = math.degrees(case.angle_rad)
    legacy = BankedCurveNoFrictionSolver().solve(
        CanonicalProblem(
            system_type="banked_curve_no_friction",
            raw_text="",
            knowns={
                "R": Quantity("R", _si(case.radius, LENGTH), "m"),
                "theta": Quantity("theta", angle_deg, "deg"),
                "g": Quantity("g", _si(case.gravity, ACCELERATION), "m/s^2"),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
        )
    )
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None
    assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
