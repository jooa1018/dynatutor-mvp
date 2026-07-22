from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import DimensionVector
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.verification import MechanicsSolveTerminal
from engine.models import CanonicalProblem, Quantity
from engine.solvers.energy_vibration import HorizontalFrictionForceSolver
from test_phase56_mechanics_compiler import (
    ACCELERATION,
    DIMENSIONLESS,
    FORCE,
    MASS,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


VELOCITY = DimensionVector(length=1, time=-1)


@dataclass(frozen=True)
class FrictionCase:
    case_id: str
    regime: str
    expected_si: float
    mass: tuple[float, str] = (2.0, "kg")
    gravity: tuple[float, str] = (9.81, "m/s^2")
    coefficient: float = 0.2
    driver_sign: int = 1
    driver_magnitude: tuple[float, str] = (1.0, "m/s")

    @property
    def friction_sign(self) -> int:
        return -self.driver_sign


SLIDING = FrictionCase("sliding", "sliding", 3.924)
SLIDING_REVERSED = FrictionCase(
    "sliding-reversed", "sliding", 3.924, driver_sign=-1
)
SLIDING_ZERO_MU = FrictionCase(
    "sliding-zero-mu", "sliding", 0.0, coefficient=0.0
)
SLIDING_MIXED_UNITS = FrictionCase(
    "sliding-mixed-units",
    "sliding",
    4.905,
    mass=(2000.0, "g"),
    gravity=(981.0, "cm/s^2"),
    coefficient=0.25,
    driver_magnitude=(360.0, "cm/s"),
)
STICKING = FrictionCase(
    "sticking", "sticking", 5.0, coefficient=0.5,
    driver_magnitude=(5.0, "N"),
)
STICKING_BOUNDARY = FrictionCase(
    "sticking-boundary", "sticking", 9.81, coefficient=0.5,
    driver_magnitude=(9.81, "N"),
)
STICKING_OVER_LIMIT = FrictionCase(
    "sticking-over-limit", "sticking", 10.0, coefficient=0.5,
    driver_magnitude=(10.0, "N"),
)


def _direction(axis: str, sign: int) -> dict[str, object]:
    return {
        "kind": "axis",
        "frame_id": "contactFrame",
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
    point_id: str | None = None,
    component: str = "unspecified",
    axis: str | None = None,
    sign: int = 1,
    scoped: bool = True,
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
        point_id=point_id,
        frame_id="contactFrame" if scoped else None,
        interval_id="contactInterval" if scoped else None,
        component=component,
        evidence_refs=("contactEvidence",),
    )
    if axis is not None:
        item["direction"] = _direction(axis, sign)
    return item


def _payload(case: FrictionCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticHorizontalFriction",
        subtype="diagnosticRegime",
        model_id="sameFixtureHorizontalContact",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["source_evidence"] = [
        {
            "kind": "text",
            "evidence_id": "contactEvidence",
            "quote": "typed horizontal contact",
            "source_span": {"start": 0, "end": 24},
            "quantity_span": None,
            "occurrence_index": 0,
        }
    ]
    payload["entities"] = [
        {
            "entity_id": "body", "primitive": "particle", "label": "body",
            "aliases": [], "component_of_entity_id": None,
            "evidence_refs": ["contactEvidence"], "model_confidence": None,
        },
        {
            "entity_id": "floor", "primitive": "surface", "label": "floor",
            "aliases": [], "component_of_entity_id": None,
            "evidence_refs": ["contactEvidence"], "model_confidence": None,
        },
        {
            "entity_id": "world", "primitive": "environment", "label": "world",
            "aliases": [], "component_of_entity_id": None,
            "evidence_refs": ["contactEvidence"], "model_confidence": None,
        },
    ]
    payload["points"] = [
        {
            "point_id": "contactPoint", "role": "contact",
            "owner_entity_id": "body", "frame_id": "contactFrame",
            "label": "C", "evidence_refs": ["contactEvidence"],
        }
    ]
    payload["reference_frames"] = [
        {
            "frame_id": "worldFrame", "frame_type": "cartesian_2d",
            "origin": {"kind": "world"},
            "axes": [
                {"axis": "x", "direction": {"kind": "axis", "frame_id": "worldFrame", "axis": "x", "sign": 1}},
                {"axis": "y", "direction": {"kind": "axis", "frame_id": "worldFrame", "axis": "y", "sign": 1}},
            ],
            "parent_frame_id": None, "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": ["contactEvidence"],
        },
        {
            "frame_id": "contactFrame", "frame_type": "tangential_normal",
            "origin": {"kind": "entity", "entity_id": "floor"},
            "axes": [
                {"axis": "tangent", "direction": _direction("tangent", 1)},
                {"axis": "normal", "direction": _direction("normal", 1)},
            ],
            "parent_frame_id": "worldFrame", "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": ["contactEvidence"],
        },
    ]
    payload["motion_intervals"] = [
        {
            "interval_id": "contactInterval", "order": 1,
            "subject_ids": ["body", "floor", "world"],
            "frame_id": "contactFrame", "start_event_id": None,
            "end_event_id": None, "evidence_refs": ["contactEvidence"],
        }
    ]
    payload["events"] = []

    quantities = [
        _q("massQ", "mass", "mass", "body", MASS, value=case.mass, scoped=False),
        _q("gravityQ", "gravity", "gravity", "world", ACCELERATION, value=case.gravity, scoped=False),
        _q("weightQ", "weight", "force", "body", FORCE, component="normal", axis="normal", sign=-1),
        _q("normalQ", "normalForce", "force", "body", FORCE, point_id="contactPoint", component="normal", axis="normal", sign=1),
        _q("frictionQ", "frictionForce", "force", "body", FORCE, point_id="contactPoint", component="tangential", axis="tangent", sign=case.friction_sign),
        _q("coefficientQ", "frictionCoefficient", "coefficient_friction", "body", DIMENSIONLESS, value=(case.coefficient, "1"), scoped=False),
        _q("normalAccelerationQ", "normalAcceleration", "acceleration", "body", ACCELERATION, component="normal", axis="normal", sign=1),
    ]
    if case.regime == "sliding":
        quantities.append(
            _q(
                "driverQ", "driverVelocity", "velocity", "body", VELOCITY,
                value=case.driver_magnitude, component="tangential",
                axis="tangent", sign=case.driver_sign,
            )
        )
    else:
        quantities.extend(
            [
                _q(
                    "driverQ", "driverForce", "force", "body", FORCE,
                    value=case.driver_magnitude, component="tangential",
                    axis="tangent", sign=case.driver_sign,
                ),
                _q(
                    "tangentialAccelerationQ", "tangentialAcceleration",
                    "acceleration", "body", ACCELERATION,
                    component="tangential", axis="tangent",
                    sign=case.driver_sign,
                ),
            ]
        )
    payload["symbols"] = [
        _symbol(item["symbol_id"], item["quantity_id"], DimensionVector.model_validate(item["dimension"]))
        for item in quantities
    ]
    payload["quantities"] = quantities
    payload["geometry"] = []
    contact_quantities = [
        "normalQ", "normalAccelerationQ", "frictionQ", "coefficientQ",
    ]
    if case.regime == "sticking":
        contact_quantities.append("tangentialAccelerationQ")
    payload["interactions"] = [
        {
            "interaction_id": "gravityInteraction", "kind": "gravity",
            "participant_ids": ["body", "world"], "point_ids": [],
            "frame_id": "contactFrame", "interval_id": "contactInterval",
            "event_id": None,
            "quantity_ids": ["massQ", "gravityQ", "weightQ"],
            "evidence_refs": ["contactEvidence"],
        },
        {
            "interaction_id": "contactInteraction", "kind": "contact",
            "participant_ids": ["body", "floor"],
            "point_ids": ["contactPoint"], "frame_id": "contactFrame",
            "interval_id": "contactInterval", "event_id": None,
            "quantity_ids": contact_quantities,
            "evidence_refs": ["contactEvidence"],
        },
    ]
    if case.regime == "sticking":
        payload["interactions"].append(
            {
                "interaction_id": "driverInteraction", "kind": "applied_force",
                "participant_ids": ["body"], "point_ids": [],
                "frame_id": "contactFrame", "interval_id": "contactInterval",
                "event_id": None, "quantity_ids": ["driverQ"],
                "evidence_refs": ["contactEvidence"],
            }
        )
    payload["constraints"] = []
    payload["state_conditions"] = [
        {
            "state_condition_id": "contactState", "kind": "contact",
            "state": "touching", "subject_id": "body",
            "interval_id": "contactInterval", "event_id": None,
            "quantity_ids": ["normalQ", "normalAccelerationQ"],
            "expression": None, "evidence_refs": ["contactEvidence"],
        },
        {
            "state_condition_id": "frictionState", "kind": "friction",
            "state": case.regime, "subject_id": "body",
            "interval_id": "contactInterval", "event_id": None,
            "quantity_ids": ["frictionQ", "normalQ", "coefficientQ"],
            "expression": None, "evidence_refs": ["contactEvidence"],
        },
        {
            "state_condition_id": "surfaceState", "kind": "motion",
            "state": "at_rest", "subject_id": "floor",
            "interval_id": "contactInterval", "event_id": None,
            "quantity_ids": [], "expression": None,
            "evidence_refs": ["contactEvidence"],
        },
        {
            "state_condition_id": "driverState", "kind": "motion",
            "state": "moving" if case.regime == "sliding" else "at_rest",
            "subject_id": "body", "interval_id": "contactInterval",
            "event_id": None,
            "quantity_ids": ["driverQ"] if case.regime == "sliding" else [],
            "expression": None, "evidence_refs": ["contactEvidence"],
        },
    ]
    payload["assumptions"] = [
        {
            "assumption_id": "horizontalSurface", "kind": "horizontal_surface",
            "subject_id": "floor", "interval_id": "contactInterval",
            "disposition": "approved", "proposed_role": None,
            "proposed_value": None, "proposed_unit": None,
            "reason": "The fixed contact plane is horizontal.",
            "evidence_refs": ["contactEvidence"],
        }
    ]
    payload["queries"] = [
        {
            "query_id": "frictionQuery",
            "target": {
                "role": "force", "subject_id": "body",
                "point_id": "contactPoint", "frame_id": "contactFrame",
                "interval_id": "contactInterval", "event_id": None,
                "component": "tangential",
                "direction": _direction("tangent", case.friction_sign),
                "target_quantity_id": "frictionQ",
            },
            "output_unit": "N",
            "output_dimension": FORCE.model_dump(mode="json"),
            "shape": "scalar", "evidence_refs": ["contactEvidence"],
        }
    ]
    return payload


def _compile(case: FrictionCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: FrictionCase):
    compiled = _compile(case)
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    selected = next(
        item for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    values = {
        item.symbol.symbol_id: item.known_si_value
        for item in compiled.graph.symbols
        if item.known_si_value is not None
    }
    values.update(
        {item.symbol_id: item.value_si for item in selected.candidate.values}
    )
    return compiled.graph, result, selected.candidate.query_value_si, values


@pytest.mark.parametrize(
    "case",
    (
        SLIDING,
        SLIDING_REVERSED,
        SLIDING_ZERO_MU,
        SLIDING_MIXED_UNITS,
        STICKING,
        STICKING_BOUNDARY,
    ),
    ids=lambda item: item.case_id,
)
def test_horizontal_friction_regimes_signs_units_and_residuals(case: FrictionCase) -> None:
    graph, result, value, values = _solve(case)
    laws = {item.law_id for item in graph.equations}
    assert {
        "horizontal_gravity_normal_projection",
        "fixed_contact_no_penetration",
        "particle_newton_second",
        "contact_normal_bound",
    }.issubset(laws)
    if case.regime == "sliding":
        assert "contact_sliding_friction" in laws
        assert "contact_friction_bound" not in laws
    else:
        assert "contact_sticking_static_acceleration" in laws
        assert "contact_friction_bound" in laws
    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)

    mass = values["mass"]
    gravity = values["gravity"]
    weight = values["weight"]
    normal = values["normalForce"]
    friction = values["frictionForce"]
    coefficient = values["frictionCoefficient"]
    assert isinstance(mass, float) and isinstance(gravity, float)
    assert isinstance(weight, float) and isinstance(normal, float)
    assert isinstance(friction, float) and isinstance(coefficient, float)
    assert weight - mass * gravity == pytest.approx(0.0, abs=1.0e-9)
    assert normal - weight == pytest.approx(0.0, abs=1.0e-9)
    assert values["normalAcceleration"] == pytest.approx(0.0, abs=1.0e-12)
    if case.regime == "sliding":
        assert friction - coefficient * normal == pytest.approx(0.0, abs=1.0e-9)
    else:
        assert values["tangentialAcceleration"] == pytest.approx(0.0, abs=1.0e-12)
        assert friction <= coefficient * normal + 1.0e-9


def test_static_threshold_is_inclusive_and_excess_force_is_rejected() -> None:
    _, _, boundary, _ = _solve(STICKING_BOUNDARY)
    assert boundary == pytest.approx(9.81, abs=1.0e-9)

    compiled = _compile(STICKING_OVER_LIMIT)
    assert compiled.status is CompilerStatus.ready and compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is not MechanicsSolveTerminal.solved
    assert result.selected_candidate_id is None


def test_missing_or_contradictory_regime_and_motion_fail_closed() -> None:
    missing = _payload(SLIDING)
    missing["state_conditions"] = [
        item for item in missing["state_conditions"]
        if item["state_condition_id"] != "frictionState"
    ]
    assert compile_mechanics_ir(_ir(missing)).status is not CompilerStatus.ready

    contradicted = _payload(SLIDING)
    velocity = next(
        item for item in contradicted["quantities"]
        if item["quantity_id"] == "driverQ"
    )
    velocity["direction"] = _direction("tangent", -1)
    assert compile_mechanics_ir(_ir(contradicted)).status is not CompilerStatus.ready

    wrong_regime = _payload(STICKING)
    motion = next(
        item for item in wrong_regime["state_conditions"]
        if item["state_condition_id"] == "driverState"
    )
    motion["state"] = "moving"
    motion["quantity_ids"] = ["driverQ"]
    assert compile_mechanics_ir(_ir(wrong_regime)).status is not CompilerStatus.ready


def test_negative_coefficient_and_invalid_query_binding_fail_closed() -> None:
    negative = _payload(SLIDING)
    coefficient = next(
        item for item in negative["quantities"]
        if item["quantity_id"] == "coefficientQ"
    )
    coefficient["raw_value"] = "-0.1"
    coefficient["si_value"] = -0.1
    assert compile_mechanics_ir(_ir(negative)).status is not CompilerStatus.ready

    wrong_unit = _payload(SLIDING)
    wrong_unit["queries"][0]["output_unit"] = "m/s"
    wrong_unit["queries"][0]["output_dimension"] = VELOCITY.model_dump(mode="json")
    assert compile_mechanics_ir(_ir(wrong_unit)).status is not CompilerStatus.ready


def test_horizontal_friction_metadata_has_no_calculation_authority() -> None:
    first = _compile(SLIDING)
    changed = _payload(SLIDING)
    changed["metadata"].update(
        system_type="projectile_motion",
        subtype="unrelated",
        model_id="different",
        source_text_sha256="f" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    (SLIDING, SLIDING_REVERSED, SLIDING_ZERO_MU, SLIDING_MIXED_UNITS, STICKING, STICKING_BOUNDARY),
    ids=lambda item: item.case_id,
)
def test_horizontal_friction_same_fixture_numeric_parity(case: FrictionCase) -> None:
    _, _, generic, _ = _solve(case)
    knowns = {
        "m": Quantity("m", case.mass[0], case.mass[1]),
        "g": Quantity("g", case.gravity[0], case.gravity[1]),
    }
    if case.regime == "sliding":
        knowns["mu_k"] = Quantity("mu_k", case.coefficient, None)
        problem = CanonicalProblem(
            system_type="horizontal_friction_force",
            friction_type="kinetic",
            knowns=knowns,
            unknowns=["friction_force"],
            requested_outputs=["friction_force"],
        )
    else:
        knowns["mu_s"] = Quantity("mu_s", case.coefficient, None)
        knowns["F"] = Quantity("F", case.driver_magnitude[0], case.driver_magnitude[1])
        problem = CanonicalProblem(
            system_type="horizontal_friction_force",
            friction_type="static",
            raw_text="actual static friction",
            knowns=knowns,
            unknowns=["friction_force"],
            requested_outputs=["friction_force"],
        )
    legacy = HorizontalFrictionForceSolver().solve(problem)
    assert legacy.ok is True and legacy.answer is not None
    assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
