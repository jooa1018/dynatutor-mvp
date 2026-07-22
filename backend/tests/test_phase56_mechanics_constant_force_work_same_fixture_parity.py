from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import DimensionVector, Dot, LiteralNode, Multiply
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.units import normalize_quantity
from engine.mechanics.verification import MechanicsSolveTerminal
from engine.models import CanonicalProblem, Quantity
from engine.solvers.work_rotation_impulse import ConstantForceWorkSolver
from test_phase56_mechanics_compiler import (
    DIMENSIONLESS,
    ENERGY,
    FORCE,
    LENGTH,
    _constant_work_payload,
    _ir,
    _quantity,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class WorkCase:
    case_id: str
    force: float
    force_unit: str
    displacement: float
    displacement_unit: str
    angle_deg: float
    expected_si: float


CASES = (
    WorkCase("parallel", 10.0, "N", 2.0, "m", 0.0, 20.0),
    WorkCase("perpendicular", 10.0, "N", 2.0, "m", 90.0, 0.0),
    WorkCase("opposite", 10.0, "N", 2.0, "m", 180.0, -20.0),
    WorkCase("acute", 10.0, "N", 2.0, "m", 60.0, 10.0),
    WorkCase("obtuse", 10.0, "N", 2.0, "m", 120.0, -10.0),
    WorkCase("zero-force", 0.0, "N", 8.0, "m", 30.0, 0.0),
    WorkCase("zero-displacement", 7.0, "N", 0.0, "m", 30.0, 0.0),
    WorkCase("mixed-units", 2.0, "kN", 50.0, "cm", 60.0, 500.0),
)


def _replace(payload: dict[str, object], quantity_id: str, value: dict[str, object]) -> None:
    quantities = payload["quantities"]
    assert isinstance(quantities, list)
    index = next(i for i, item in enumerate(quantities) if item["quantity_id"] == quantity_id)
    quantities[index] = value


def _scalar_payload(item: WorkCase) -> dict[str, object]:
    payload = _constant_work_payload()
    _replace(
        payload,
        "forceQ",
        _quantity(
            "forceQ", "force", "force", "bodyA", FORCE,
            value=item.force, unit=item.force_unit, component="x",
        ),
    )
    _replace(
        payload,
        "distanceQ",
        _quantity(
            "distanceQ", "distance", "displacement", "bodyA", LENGTH,
            value=item.displacement, unit=item.displacement_unit, component="x",
        ),
    )
    payload["symbols"].append(_symbol("theta", "thetaQ", DIMENSIONLESS))
    payload["quantities"].append(
        _quantity(
            "thetaQ", "theta", "angle", "bodyA", DIMENSIONLESS,
            value=math.radians(item.angle_deg), unit="rad",
        )
    )
    payload["interactions"][0]["quantity_ids"].append("thetaQ")
    payload["metadata"].update(
        system_type="diagnosticWorkLabel",
        subtype="diagnosticAngleForm",
        model_id="sameFixtureWork",
        source_text_sha256=hashlib.sha256(item.case_id.encode()).hexdigest(),
    )
    return payload


def _vector_quantity(
    quantity_id: str,
    symbol_id: str,
    role: str,
    dimension: DimensionVector,
    raw: str,
    unit: str,
) -> dict[str, object]:
    normalized = normalize_quantity(raw, unit, "vector", dimension)
    return {
        "quantity_id": quantity_id,
        "symbol_id": symbol_id,
        "role": role,
        "subject_id": "bodyA",
        "point_id": None,
        "frame_id": "workFrame",
        "interval_id": None,
        "event_id": None,
        "component": "unspecified",
        "direction": None,
        "shape": "vector",
        "dimension": dimension.model_dump(mode="json"),
        "provenance": "user_correction",
        "evidence_refs": [],
        "assumption_policy_ref": None,
        "correction_id": f"corr_{quantity_id}",
        "model_confidence": None,
        "raw_value": raw,
        "raw_unit": unit,
        "si_value": normalized.value,
        "si_unit": normalized.si_unit,
    }


def _vector_payload(*, include_angle: bool = False) -> dict[str, object]:
    payload = _constant_work_payload()
    payload["reference_frames"] = [
        {
            "frame_id": "workFrame",
            "frame_type": "cartesian_2d",
            "origin": {"kind": "world"},
            "axes": [
                {"axis": "x", "direction": {"kind": "axis", "frame_id": "workFrame", "axis": "x", "sign": 1}},
                {"axis": "y", "direction": {"kind": "axis", "frame_id": "workFrame", "axis": "y", "sign": 1}},
            ],
            "parent_frame_id": None,
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": [],
        }
    ]
    payload["symbols"] = [
        _symbol("work", "workQ", ENERGY),
        {
            "symbol_id": "force",
            "quantity_id": "forceQ",
            "dimension": FORCE.model_dump(mode="json"),
            "shape": "vector",
            "vector_length": 2,
        },
        {
            "symbol_id": "distance",
            "quantity_id": "distanceQ",
            "dimension": LENGTH.model_dump(mode="json"),
            "shape": "vector",
            "vector_length": 2,
        },
    ]
    payload["quantities"] = [
        _quantity("workQ", "work", "work", "bodyA", ENERGY, frame_id="workFrame"),
        _vector_quantity("forceQ", "force", "force", FORCE, "3,4", "N"),
        _vector_quantity("distanceQ", "distance", "displacement", LENGTH, "2,-1", "m"),
    ]
    payload["interactions"][0].update(
        frame_id="workFrame",
        quantity_ids=["workQ", "forceQ", "distanceQ"],
    )
    payload["queries"][0]["target"]["frame_id"] = "workFrame"
    if include_angle:
        payload["symbols"].append(_symbol("theta", "thetaQ", DIMENSIONLESS))
        payload["quantities"].append(
            _quantity("thetaQ", "theta", "angle", "bodyA", DIMENSIONLESS, value=0.0, unit="rad", frame_id="workFrame")
        )
        payload["interactions"][0]["quantity_ids"].append("thetaQ")
    payload["metadata"].update(system_type="wrongLabel", subtype="vectorDot")
    return payload


def _solve(payload: dict[str, object]):
    compiled = compile_mechanics_ir(_ir(payload))
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    selected = next(
        item for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    assert isinstance(selected.candidate.query_value_si, float)
    return compiled.graph, result, selected.candidate.query_value_si


@pytest.mark.parametrize("item", CASES, ids=lambda value: value.case_id)
def test_constant_force_work_angle_form_solves_signed_work(item: WorkCase) -> None:
    graph, result, value = _solve(_scalar_payload(item))
    equation = next(item for item in graph.equations if item.law_id == "force_work")
    assert isinstance(equation.expression.right, Multiply)
    assert any(isinstance(factor, LiteralNode) for factor in equation.expression.right.factors)
    assert equation.assumption_ids == ("constantForce",)
    assert result.plan.primary_backend is SolveBackendKind.linear_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert value == pytest.approx(item.expected_si, rel=1.0e-9, abs=1.0e-9)


def test_vector_dot_and_angle_forms_are_equivalent() -> None:
    graph, _, value = _solve(_vector_payload())
    equation = next(item for item in graph.equations if item.law_id == "force_work")
    assert isinstance(equation.expression.right, Dot)
    assert value == pytest.approx(2.0)

    scalar = WorkCase("equivalent", 5.0, "N", math.sqrt(5.0), "m", math.degrees(math.acos(2.0 / (5.0 * math.sqrt(5.0)))), 2.0)
    _, _, scalar_value = _solve(_scalar_payload(scalar))
    assert scalar_value == pytest.approx(value, rel=1.0e-9, abs=1.0e-9)


def test_competing_vector_and_angle_authority_fails_closed() -> None:
    compiled = compile_mechanics_ir(_ir(_vector_payload(include_angle=True)))
    assert compiled.status is CompilerStatus.underdetermined
    assert compiled.graph is not None
    assert "force_work" not in {item.law_id for item in compiled.graph.equations}


def test_scalar_without_axis_or_included_angle_fails_closed() -> None:
    payload = _constant_work_payload()
    for item in payload["quantities"]:
        if item["quantity_id"] in {"forceQ", "distanceQ"}:
            item["component"] = "unspecified"
    compiled = compile_mechanics_ir(_ir(payload))
    assert compiled.status is CompilerStatus.underdetermined
    assert compiled.graph is not None
    assert "force_work" not in {item.law_id for item in compiled.graph.equations}


def test_work_metadata_does_not_author_the_equation() -> None:
    payload = _scalar_payload(CASES[3])
    first = compile_mechanics_ir(_ir(payload))
    changed = deepcopy(payload)
    changed["metadata"].update(
        system_type="projectile_motion",
        subtype="unrelated",
        model_id="other",
        source_text_sha256="f" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint


@pytest.mark.slow
@pytest.mark.parametrize("item", CASES[:5], ids=lambda value: value.case_id)
def test_constant_force_work_same_fixture_numeric_parity(item: WorkCase) -> None:
    _, _, generic = _solve(_scalar_payload(item))
    legacy = ConstantForceWorkSolver().solve(
        CanonicalProblem(
            system_type="constant_force_work",
            raw_text="",
            knowns={
                "F": Quantity("F", item.force, item.force_unit),
                "s": Quantity("s", item.displacement, item.displacement_unit),
                "theta": Quantity("theta", item.angle_deg, "deg"),
            },
            unknowns=["W"],
            requested_outputs=["work"],
        )
    )
    assert legacy.ok is True and legacy.answer is not None
    assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-6)
