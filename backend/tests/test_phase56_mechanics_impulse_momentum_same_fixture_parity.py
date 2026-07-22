from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import DimensionVector, Equality, Inequality, Multiply, Subtract
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.solver.contracts import _graph_event_ids, _graph_plan_event_ids
from engine.mechanics.verification import MechanicsSolveTerminal
from engine.models import CanonicalProblem, Quantity
from engine.solvers.work_rotation_impulse import ImpulseMomentumSolver
from test_phase56_mechanics_compiler import (
    FORCE,
    MASS,
    TIME,
    VELOCITY,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


IMPULSE = DimensionVector(length=1, mass=1, time=-1)


@dataclass(frozen=True)
class ImpulseCase:
    case_id: str
    query_quantity_id: str
    auxiliary_unknown_quantity_id: str
    expected_si: float
    force: tuple[float, str] = (10.0, "N")
    duration: tuple[float, str] = (2.0, "s")
    impulse: tuple[float, str] = (20.0, "N*s")
    mass: tuple[float, str] = (4.0, "kg")
    velocity_start: tuple[float, str] = (1.0, "m/s")
    velocity_end: tuple[float, str] = (6.0, "m/s")


QUERY_IMPULSE = ImpulseCase("query-impulse", "impulseQ", "velocityEndQ", 20.0)
QUERY_FINAL_VELOCITY = ImpulseCase("query-final-velocity", "velocityEndQ", "impulseQ", 6.0)
QUERY_INITIAL_VELOCITY = ImpulseCase("query-initial-velocity", "velocityStartQ", "impulseQ", 1.0)
QUERY_MASS = ImpulseCase("query-mass", "massQ", "impulseQ", 4.0)
QUERY_FORCE = ImpulseCase("query-force", "forceQ", "impulseQ", 10.0)
QUERY_DURATION = ImpulseCase("query-duration", "durationQ", "impulseQ", 2.0)
ZERO_IMPULSE = ImpulseCase(
    "zero-impulse", "velocityEndQ", "impulseQ", 3.0,
    force=(0.0, "N"), impulse=(0.0, "N*s"),
    velocity_start=(3.0, "m/s"), velocity_end=(3.0, "m/s"),
)
DIRECTION_REVERSAL = ImpulseCase(
    "direction-reversal", "velocityEndQ", "impulseQ", -1.0,
    force=(-8.0, "N"), impulse=(-16.0, "N*s"),
    velocity_start=(3.0, "m/s"), velocity_end=(-1.0, "m/s"),
)
MIXED_UNITS = ImpulseCase(
    "mixed-units", "velocityEndQ", "impulseQ", 5.0,
    force=(-20.0, "N"), duration=(500.0, "ms"), impulse=(-10.0, "N*s"),
    mass=(2000.0, "g"), velocity_start=(36.0, "km/h"),
    velocity_end=(5.0, "m/s"),
)

QUERY_CASES = (
    QUERY_IMPULSE,
    QUERY_FINAL_VELOCITY,
    QUERY_INITIAL_VELOCITY,
    QUERY_MASS,
    QUERY_FORCE,
    QUERY_DURATION,
)

_SPEC = {
    "forceQ": ("force", "force", FORCE, "N", None),
    "durationQ": ("duration", "duration", TIME, "s", None),
    "impulseQ": ("impulse", "impulse", IMPULSE, "N*s", None),
    "massQ": ("mass", "mass", MASS, "kg", None),
    "velocityStartQ": ("velocityStart", "velocity", VELOCITY, "m/s", "impulseStart"),
    "velocityEndQ": ("velocityEnd", "velocity", VELOCITY, "m/s", "impulseEnd"),
}


def _quantity_for(
    quantity_id: str,
    value: tuple[float, str],
    *,
    unknown: bool,
) -> dict[str, object]:
    symbol_id, role, dimension, _, event_id = _SPEC[quantity_id]
    scoped = quantity_id != "massQ"
    item = _quantity(
        quantity_id,
        symbol_id,
        role,
        "body",
        dimension,
        value=None if unknown else value[0],
        unit=value[1],
        frame_id=None if quantity_id == "massQ" else "impulseFrame",
        interval_id="impulseInterval" if scoped else None,
        event_id=event_id,
        component="x" if quantity_id not in {"massQ", "durationQ"} else "unspecified",
        sign=1 if quantity_id not in {"massQ", "durationQ"} else None,
    )
    return item


def _payload(case: ImpulseCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticImpulse",
        subtype="diagnosticMomentum",
        model_id="sameFixtureImpulse",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["entities"] = [
        {
            "entity_id": "body", "primitive": "particle", "label": "body",
            "aliases": [], "component_of_entity_id": None,
            "evidence_refs": [], "model_confidence": None,
        }
    ]
    payload["reference_frames"] = [
        {
            "frame_id": "impulseFrame", "frame_type": "cartesian_1d",
            "origin": {"kind": "world"},
            "axes": [{
                "axis": "x",
                "direction": {"kind": "axis", "frame_id": "impulseFrame", "axis": "x", "sign": 1},
            }],
            "parent_frame_id": None, "translating_with_entity_id": None,
            "rotating_about_point_id": None,
            "generalized_coordinate_symbol_ids": [], "evidence_refs": [],
        }
    ]
    payload["motion_intervals"] = [
        {
            "interval_id": "impulseInterval", "order": 1,
            "subject_ids": ["body"], "frame_id": "impulseFrame",
            "start_event_id": "impulseStart", "end_event_id": "impulseEnd",
            "evidence_refs": [],
        }
    ]
    payload["events"] = [
        {
            "event_id": "impulseStart", "kind": "start", "subject_ids": ["body"],
            "interval_ids": ["impulseInterval"], "time_quantity_id": None,
            "evidence_refs": [],
        },
        {
            "event_id": "impulseEnd", "kind": "finish", "subject_ids": ["body"],
            "interval_ids": ["impulseInterval"], "time_quantity_id": None,
            "evidence_refs": [],
        },
    ]
    values = {
        "forceQ": case.force,
        "durationQ": case.duration,
        "impulseQ": case.impulse,
        "massQ": case.mass,
        "velocityStartQ": case.velocity_start,
        "velocityEndQ": case.velocity_end,
    }
    unknown_ids = {case.query_quantity_id, case.auxiliary_unknown_quantity_id}
    payload["symbols"] = [
        _symbol(_SPEC[quantity_id][0], quantity_id, _SPEC[quantity_id][2])
        for quantity_id in values
    ]
    payload["quantities"] = [
        _quantity_for(quantity_id, value, unknown=quantity_id in unknown_ids)
        for quantity_id, value in values.items()
    ]
    payload["interactions"] = []
    payload["constraints"] = []
    payload["state_conditions"] = []
    payload["geometry"] = []
    payload["points"] = []
    payload["assumptions"] = [
        {
            "assumption_id": "constantForce", "kind": "constant_force",
            "subject_id": "body", "interval_id": "impulseInterval",
            "disposition": "approved", "proposed_role": None,
            "proposed_value": None, "proposed_unit": None,
            "reason": "The force is constant over the stated interval.",
            "evidence_refs": [],
        },
        {
            "assumption_id": "positiveDuration", "kind": "strictly_positive_duration",
            "subject_id": "body", "interval_id": "impulseInterval",
            "disposition": "approved", "proposed_role": None,
            "proposed_value": None, "proposed_unit": None,
            "reason": "The end state follows the start state.",
            "evidence_refs": [],
        },
    ]
    symbol_id, role, dimension, output_unit, event_id = _SPEC[case.query_quantity_id]
    payload["queries"] = [
        {
            "query_id": "impulseQuery",
            "target": {
                "role": role, "subject_id": "body", "point_id": None,
                "frame_id": None if case.query_quantity_id == "massQ" else "impulseFrame",
                "interval_id": None if case.query_quantity_id == "massQ" else "impulseInterval",
                "event_id": event_id,
                "component": "unspecified" if case.query_quantity_id in {"massQ", "durationQ"} else "x",
                "direction": None,
                "target_quantity_id": case.query_quantity_id,
            },
            "output_unit": output_unit,
            "output_dimension": dimension.model_dump(mode="json"),
            "shape": "scalar", "evidence_refs": [],
        }
    ]
    return payload


def _compile(case: ImpulseCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: ImpulseCase):
    compiled = _compile(case)
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


@pytest.mark.parametrize("case", QUERY_CASES, ids=lambda item: item.case_id)
def test_impulse_momentum_each_requested_quantity_uses_same_typed_graph(case: ImpulseCase) -> None:
    graph, result, value = _solve(case)
    assert {item.law_id for item in graph.equations} == {
        "linear_impulse", "linear_impulse_momentum", "elapsed_time_positive",
    }
    assert _graph_event_ids(graph) == ("impulseEnd", "impulseStart")
    assert _graph_plan_event_ids(graph) == ()
    assert result.plan.event_ids == ()
    assert result.plan.primary_backend in {
        SolveBackendKind.linear_symbolic, SolveBackendKind.polynomial_symbolic,
    }
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)


@pytest.mark.parametrize(
    "case", (ZERO_IMPULSE, DIRECTION_REVERSAL, MIXED_UNITS),
    ids=lambda item: item.case_id,
)
def test_impulse_momentum_sign_reversal_zero_and_units(case: ImpulseCase) -> None:
    graph, _, value = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    by_law = {item.law_id: item for item in graph.equations}
    assert isinstance(by_law["linear_impulse"].expression, Equality)
    assert isinstance(by_law["linear_impulse"].expression.right, Multiply)
    assert isinstance(by_law["linear_impulse_momentum"].expression, Equality)
    assert isinstance(by_law["linear_impulse_momentum"].expression.right, Multiply)
    assert any(
        isinstance(item, Subtract)
        for item in by_law["linear_impulse_momentum"].expression.right.factors
    )


def test_nonpositive_duration_and_nonpositive_mass_fail_closed() -> None:
    zero_duration = _payload(QUERY_FINAL_VELOCITY)
    duration = next(item for item in zero_duration["quantities"] if item["quantity_id"] == "durationQ")
    duration.update(raw_value="0.0", si_value=0.0)
    compiled = compile_mechanics_ir(_ir(zero_duration))
    assert compiled.status is CompilerStatus.ready and compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is not MechanicsSolveTerminal.solved
    assert result.selected_candidate_id is None

    zero_mass = _payload(QUERY_FINAL_VELOCITY)
    mass = next(item for item in zero_mass["quantities"] if item["quantity_id"] == "massQ")
    mass.update(raw_value="0.0", si_value=0.0)
    compiled = compile_mechanics_ir(_ir(zero_mass))
    if compiled.status is CompilerStatus.ready:
        assert compiled.graph is not None
        result = solve_verified_equation_graph(compiled.graph)
        assert result.terminal is not MechanicsSolveTerminal.solved
    else:
        assert compiled.graph is None


def test_malformed_interval_and_query_binding_fail_closed() -> None:
    malformed = _payload(QUERY_FINAL_VELOCITY)
    malformed["events"] = malformed["events"][:-1]
    malformed_result = compile_mechanics_ir(_ir(malformed))
    assert malformed_result.status is not CompilerStatus.ready
    assert malformed_result.graph is None

    wrong_query = _payload(QUERY_FINAL_VELOCITY)
    wrong_query["queries"][0]["target"]["target_quantity_id"] = "velocityStartQ"
    assert compile_mechanics_ir(_ir(wrong_query)).status is not CompilerStatus.ready


def test_impulse_metadata_has_no_calculation_authority_and_spoofs_keep_events() -> None:
    first = _compile(QUERY_FINAL_VELOCITY)
    changed = _payload(QUERY_FINAL_VELOCITY)
    changed["metadata"].update(
        system_type="projectile_motion", subtype="unrelated",
        model_id="different", source_text_sha256="f" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint

    graph = first.graph
    impulse_equation = next(item for item in graph.equations if item.law_id == "linear_impulse")
    spoofed = graph.model_copy(
        update={
            "equations": tuple(
                item.model_copy(update={"complexity_cost": item.complexity_cost + 1})
                if item.equation_id == impulse_equation.equation_id else item
                for item in graph.equations
            )
        }
    )
    assert _graph_event_ids(spoofed) == ("impulseEnd", "impulseStart")
    assert _graph_plan_event_ids(spoofed) == ("impulseEnd", "impulseStart")


@pytest.mark.slow
@pytest.mark.parametrize(
    "case", (QUERY_IMPULSE, QUERY_FINAL_VELOCITY, ZERO_IMPULSE, DIRECTION_REVERSAL, MIXED_UNITS),
    ids=lambda item: item.case_id,
)
def test_impulse_momentum_same_fixture_numeric_parity(case: ImpulseCase) -> None:
    _, _, generic = _solve(case)
    knowns = {
        "F": Quantity("F", case.force[0], case.force[1]),
        "t": Quantity("t", case.duration[0], case.duration[1]),
    }
    requested = ["impulse"]
    if case.query_quantity_id == "velocityEndQ":
        knowns.update(
            m=Quantity("m", case.mass[0], case.mass[1]),
            v0=Quantity("v0", case.velocity_start[0], case.velocity_start[1]),
        )
        requested = ["final_velocity"]
    legacy = ImpulseMomentumSolver().solve(
        CanonicalProblem(
            system_type="impulse_momentum", knowns=knowns,
            unknowns=requested, requested_outputs=requested,
            force_direction=(
                None
                if case.query_quantity_id != "velocityEndQ"
                else "opposite" if case.force[0] < 0.0 else "same"
            ),
        )
    )
    assert legacy.ok is True
    if case.query_quantity_id == "velocityEndQ":
        answer = next(item for item in legacy.answers if item.output_key == "final_velocity")
        assert answer.numeric == pytest.approx(generic, abs=1.0e-5)
    else:
        assert legacy.answer is not None
        assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
