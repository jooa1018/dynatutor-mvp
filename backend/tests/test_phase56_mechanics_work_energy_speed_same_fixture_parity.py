from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import DimensionVector, Equality, Inequality, Multiply, Power, Subtract
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.solver.contracts import _graph_event_ids, _graph_plan_event_ids
from engine.mechanics.units import normalize_quantity
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity
from engine.solvers.energy_vibration import WorkEnergySpeedSolver
from test_phase56_mechanics_compiler import (
    ENERGY,
    MASS,
    VELOCITY,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class WorkEnergyCase:
    case_id: str
    mass: tuple[float, str]
    work: tuple[float, str]
    initial_speed: tuple[float, str]
    expected_si: float


REST_POSITIVE = WorkEnergyCase(
    "rest-positive", (2.0, "kg"), (16.0, "J"), (0.0, "m/s"), 4.0
)
NONZERO_POSITIVE = WorkEnergyCase(
    "nonzero-positive", (4.0, "kg"), (18.0, "J"), (2.0, "m/s"), math.sqrt(13.0)
)
NEGATIVE_VALID = WorkEnergyCase(
    "negative-valid", (2.0, "kg"), (-3.0, "J"), (3.0, "m/s"), math.sqrt(6.0)
)
ZERO_WORK = WorkEnergyCase(
    "zero-work", (5.0, "kg"), (0.0, "J"), (7.0, "m/s"), 7.0
)
MIXED_UNITS = WorkEnergyCase(
    "mixed-units", (2000.0, "g"), (9.0, "N*m"), (36.0, "km/h"), math.sqrt(109.0)
)
IMPOSSIBLE_RADICAND = WorkEnergyCase(
    "impossible-radicand", (2.0, "kg"), (-10.0, "J"), (2.0, "m/s"), math.nan
)

VALID_CASES = (
    REST_POSITIVE,
    NONZERO_POSITIVE,
    NEGATIVE_VALID,
    ZERO_WORK,
    MIXED_UNITS,
)


def _payload(case: WorkEnergyCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticWorkEnergy",
        subtype="diagnosticFinalSpeed",
        model_id="sameFixtureWorkEnergy",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["entities"] = [
        {
            "entity_id": "body",
            "primitive": "particle",
            "label": "body",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": [],
            "model_confidence": None,
        }
    ]
    payload["reference_frames"] = [
        {
            "frame_id": "energyFrame",
            "frame_type": "cartesian_1d",
            "origin": {"kind": "world"},
            "axes": [
                {
                    "axis": "x",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "energyFrame",
                        "axis": "x",
                        "sign": 1,
                    },
                }
            ],
            "parent_frame_id": None,
            "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [],
            "evidence_refs": [],
        }
    ]
    payload["motion_intervals"] = [
        {
            "interval_id": "energyInterval",
            "order": 1,
            "subject_ids": ["body"],
            "frame_id": "energyFrame",
            "start_event_id": "energyStart",
            "end_event_id": "energyEnd",
            "evidence_refs": [],
        }
    ]
    payload["events"] = [
        {
            "event_id": "energyStart",
            "kind": "start",
            "subject_ids": ["body"],
            "interval_ids": ["energyInterval"],
            "time_quantity_id": None,
            "evidence_refs": [],
        },
        {
            "event_id": "energyEnd",
            "kind": "finish",
            "subject_ids": ["body"],
            "interval_ids": ["energyInterval"],
            "time_quantity_id": None,
            "evidence_refs": [],
        },
    ]
    payload["symbols"] = [
        _symbol("mass", "massQ", MASS),
        _symbol("netWork", "workQ", ENERGY),
        _symbol("speedStart", "speedStartQ", VELOCITY),
        _symbol("speedEnd", "speedEndQ", VELOCITY),
    ]
    payload["quantities"] = [
        _quantity(
            "massQ",
            "mass",
            "mass",
            "body",
            MASS,
            value=case.mass[0],
            unit=case.mass[1],
        ),
        _quantity(
            "workQ",
            "netWork",
            "work",
            "body",
            ENERGY,
            value=case.work[0],
            unit=case.work[1],
            frame_id="energyFrame",
            interval_id="energyInterval",
        ),
        _quantity(
            "speedStartQ",
            "speedStart",
            "speed",
            "body",
            VELOCITY,
            value=case.initial_speed[0],
            unit=case.initial_speed[1],
            frame_id="energyFrame",
            interval_id="energyInterval",
            event_id="energyStart",
            component="magnitude",
        ),
        _quantity(
            "speedEndQ",
            "speedEnd",
            "speed",
            "body",
            VELOCITY,
            frame_id="energyFrame",
            interval_id="energyInterval",
            event_id="energyEnd",
            component="magnitude",
        ),
    ]
    payload["points"] = []
    payload["geometry"] = []
    payload["interactions"] = []
    payload["constraints"] = []
    payload["state_conditions"] = []
    payload["assumptions"] = []
    payload["queries"] = [
        {
            "query_id": "finalSpeedQuery",
            "target": {
                "role": "speed",
                "subject_id": "body",
                "point_id": None,
                "frame_id": "energyFrame",
                "interval_id": "energyInterval",
                "event_id": "energyEnd",
                "component": "magnitude",
                "direction": None,
                "target_quantity_id": "speedEndQ",
            },
            "output_unit": "m/s",
            "output_dimension": VELOCITY.model_dump(mode="json"),
            "shape": "scalar",
            "evidence_refs": [],
        }
    ]
    return payload


def _compile(case: WorkEnergyCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: WorkEnergyCase):
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
    assert isinstance(selected.candidate.query_value_si, float)
    return compiled.graph, result, selected.candidate.query_value_si


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_work_energy_speed_limits_signs_zero_and_units(case: WorkEnergyCase) -> None:
    graph, result, value = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    by_law = {item.law_id: item for item in graph.equations}
    assert set(by_law) == {"particle_work_energy", "translational_speed_nonnegative"}
    energy = by_law["particle_work_energy"].expression
    assert isinstance(energy, Equality)
    assert isinstance(energy.right, Multiply)
    assert any(isinstance(item, Subtract) for item in energy.right.factors)
    assert isinstance(by_law["translational_speed_nonnegative"].expression, Inequality)
    assert _graph_event_ids(graph) == ("energyEnd", "energyStart")
    assert _graph_plan_event_ids(graph) == ()
    assert result.plan.event_ids == ()
    assert result.plan.primary_backend is SolveBackendKind.polynomial_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert all(
        check.status is VerificationCheckStatus.passed
        for item in result.verified_candidates
        for check in item.outcome.checks
    )


def test_work_energy_preserves_both_roots_then_selects_nonnegative_speed() -> None:
    _, result, value = _solve(NONZERO_POSITIVE)
    assert len(result.candidate_set.candidates) == 2
    roots = sorted(float(item.query_value_si) for item in result.candidate_set.candidates)
    assert roots == pytest.approx([-NONZERO_POSITIVE.expected_si, NONZERO_POSITIVE.expected_si])
    assert len(result.verification_outcomes) == 2
    assert len(result.verified_candidates) == 1
    assert value == pytest.approx(NONZERO_POSITIVE.expected_si)
    rejected = next(item for item in result.verification_outcomes if not item.passed)
    inequality = next(
        check for check in rejected.checks if check.kind is VerificationCheckKind.inequality
    )
    assert inequality.status is VerificationCheckStatus.failed


def test_impossible_negative_radicand_fails_without_clamp_or_absolute_value() -> None:
    compiled = _compile(IMPOSSIBLE_RADICAND)
    assert compiled.status is CompilerStatus.ready
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is not MechanicsSolveTerminal.solved
    assert result.selected_candidate_id is None
    assert result.verified_candidates == ()


def test_missing_initial_state_does_not_default_to_rest() -> None:
    payload = _payload(REST_POSITIVE)
    payload["quantities"] = [
        item for item in payload["quantities"] if item["quantity_id"] != "speedStartQ"
    ]
    payload["symbols"] = [
        item for item in payload["symbols"] if item["quantity_id"] != "speedStartQ"
    ]
    compiled = compile_mechanics_ir(_ir(payload))
    assert compiled.status is not CompilerStatus.ready
    assert compiled.graph is None or "particle_work_energy" not in {
        item.law_id for item in compiled.graph.equations
    }


def test_signed_velocity_is_not_silently_reinterpreted_as_scalar_speed() -> None:
    payload = _payload(NONZERO_POSITIVE)
    for item in payload["quantities"]:
        if item["quantity_id"] in {"speedStartQ", "speedEndQ"}:
            item["role"] = "velocity"
            item["component"] = "x"
            item["direction"] = {
                "kind": "axis", "frame_id": "energyFrame", "axis": "x", "sign": 1
            }
    payload["queries"][0]["target"].update(role="velocity", component="x")
    compiled = compile_mechanics_ir(_ir(payload))
    assert compiled.status is CompilerStatus.ready
    assert compiled.graph is not None
    assert "translational_speed_nonnegative" not in {
        item.law_id for item in compiled.graph.equations
    }
    assert _graph_plan_event_ids(compiled.graph) == ("energyEnd", "energyStart")
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is not MechanicsSolveTerminal.solved
    assert result.selected_candidate_id is None


def test_negative_mass_and_negative_known_speed_are_rejected_by_role_domain() -> None:
    negative_mass = _payload(NONZERO_POSITIVE)
    mass = next(item for item in negative_mass["quantities"] if item["quantity_id"] == "massQ")
    mass.update(raw_value="-1.0", raw_unit="kg", si_value=-1.0, si_unit="kg")
    assert compile_mechanics_ir(_ir(negative_mass)).status is CompilerStatus.invalid

    negative_speed = _payload(NONZERO_POSITIVE)
    speed = next(
        item for item in negative_speed["quantities"] if item["quantity_id"] == "speedStartQ"
    )
    speed.update(raw_value="-2.0", raw_unit="m/s", si_value=-2.0, si_unit="m*s^-1")
    assert compile_mechanics_ir(_ir(negative_speed)).status is CompilerStatus.invalid


def test_internal_mass_or_work_query_cannot_receive_endpoint_event_waiver() -> None:
    for target_id, target_role, unit, dimension in (
        ("massQ", "mass", "kg", MASS),
        ("workQ", "work", "J", ENERGY),
    ):
        payload = _payload(NONZERO_POSITIVE)
        final = next(item for item in payload["quantities"] if item["quantity_id"] == "speedEndQ")
        final.update(
            raw_value=str(NONZERO_POSITIVE.expected_si),
            raw_unit="m/s",
            si_value=NONZERO_POSITIVE.expected_si,
            si_unit="m*s^-1",
            provenance="user_correction",
            correction_id="corr_speedEndQ",
        )
        target = next(item for item in payload["quantities"] if item["quantity_id"] == target_id)
        target.update(
            raw_value=None,
            raw_unit=None,
            si_value=None,
            si_unit=None,
            provenance="inferred",
            correction_id=None,
        )
        payload["queries"][0] = {
            "query_id": "internalQuery",
            "target": {
                "role": target_role,
                "subject_id": "body",
                "point_id": None,
                "frame_id": None if target_id == "massQ" else "energyFrame",
                "interval_id": None if target_id == "massQ" else "energyInterval",
                "event_id": None,
                "component": "unspecified",
                "direction": None,
                "target_quantity_id": target_id,
            },
            "output_unit": unit,
            "output_dimension": dimension.model_dump(mode="json"),
            "shape": "scalar",
            "evidence_refs": [],
        }
        compiled = compile_mechanics_ir(_ir(payload))
        if compiled.status is CompilerStatus.ready:
            assert compiled.graph is not None
            assert _graph_plan_event_ids(compiled.graph) == ("energyEnd", "energyStart")
            result = solve_verified_equation_graph(compiled.graph)
            assert result.terminal is not MechanicsSolveTerminal.solved
            assert result.selected_candidate_id is None
        else:
            assert compiled.graph is None or compiled.status is not CompilerStatus.ready


def test_wrong_query_binding_invalid_unit_and_malformed_event_fail_closed() -> None:
    wrong_binding = _payload(NONZERO_POSITIVE)
    wrong_binding["queries"][0]["target"]["target_quantity_id"] = "speedStartQ"
    assert compile_mechanics_ir(_ir(wrong_binding)).status is not CompilerStatus.ready

    wrong_unit = _payload(NONZERO_POSITIVE)
    wrong_unit["queries"][0]["output_unit"] = "kg"
    assert compile_mechanics_ir(_ir(wrong_unit)).status is not CompilerStatus.ready

    malformed = _payload(NONZERO_POSITIVE)
    malformed["events"] = malformed["events"][:-1]
    compiled = compile_mechanics_ir(_ir(malformed))
    assert compiled.status is not CompilerStatus.ready
    assert compiled.graph is None


def test_work_energy_metadata_has_no_authority_and_spoofs_keep_events() -> None:
    first = _compile(NONZERO_POSITIVE)
    changed = _payload(NONZERO_POSITIVE)
    changed["metadata"].update(
        system_type="collision_1d",
        subtype="unrelated",
        model_id="different",
        source_text_sha256="f" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint

    graph = first.graph
    energy = next(item for item in graph.equations if item.law_id == "particle_work_energy")
    spoofed = graph.model_copy(
        update={
            "equations": tuple(
                item.model_copy(update={"complexity_cost": item.complexity_cost + 1})
                if item.equation_id == energy.equation_id
                else item
                for item in graph.equations
            )
        }
    )
    assert _graph_event_ids(spoofed) == ("energyEnd", "energyStart")
    assert _graph_plan_event_ids(spoofed) == ("energyEnd", "energyStart")


@pytest.mark.slow
@pytest.mark.parametrize("case", VALID_CASES, ids=lambda item: item.case_id)
def test_work_energy_speed_same_fixture_numeric_parity(case: WorkEnergyCase) -> None:
    _, _, generic = _solve(case)
    mass = normalize_quantity(str(case.mass[0]), case.mass[1], "scalar", MASS)
    work = normalize_quantity(str(case.work[0]), case.work[1], "scalar", ENERGY)
    initial = normalize_quantity(str(case.initial_speed[0]), case.initial_speed[1], "scalar", VELOCITY)
    assert isinstance(mass.value, float)
    assert isinstance(work.value, float)
    assert isinstance(initial.value, float)
    legacy = WorkEnergySpeedSolver().solve(
        CanonicalProblem(
            system_type="work_energy_speed",
            raw_text="",
            knowns={
                "m": Quantity("m", mass.value, "kg"),
                "W": Quantity("W", work.value, "J"),
                "v0": Quantity("v0", initial.value, "m/s"),
            },
            unknowns=["final_velocity"],
            requested_outputs=["final_velocity"],
        )
    )
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None
    assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
