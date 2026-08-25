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
from engine.mechanics.solver.contracts import _graph_event_ids, _graph_plan_event_ids
from engine.mechanics.verification import MechanicsSolveTerminal, VerificationCheckStatus
from test_phase56_mechanics_compiler import (
    ACCELERATION,
    LENGTH,
    TIME,
    VELOCITY,
    _constant_acceleration_payload,
    _ir,
    _quantity,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class ProjectileCase:
    case_id: str
    vx0: float
    vy0: float
    h0: float
    hf: float | None
    query_quantity_id: str
    expected_si: float | None
    event_kind: str = "contact_start"
    gravity: float = 9.81
    metadata_label: str = "projectile_motion"


SAME_HEIGHT_TIME = ProjectileCase(
    "same-height-time", 10.0, 10.0, 0.0, 0.0, "durationQ", 20.0 / 9.81
)
SAME_HEIGHT_RANGE = ProjectileCase(
    "same-height-range", 10.0, 10.0, 0.0, 0.0, "displacementXQ", 200.0 / 9.81
)
SAME_HEIGHT_IMPACT_Y = ProjectileCase(
    "same-height-impact-y", 10.0, 10.0, 0.0, 0.0, "endVelocityYQ", -10.0
)
HORIZONTAL_FROM_HEIGHT = ProjectileCase(
    "horizontal-from-height", 12.0, 0.0, 20.0, 0.0, "durationQ", math.sqrt(40.0 / 9.81)
)
VERTICAL_LAUNCH_TIME = ProjectileCase(
    "vertical-launch-time", 0.0, 15.0, 2.0, 0.0, "durationQ",
    (15.0 + math.sqrt(15.0**2 + 2.0 * 9.81 * 2.0)) / 9.81,
)
DIFFERENT_HEIGHT_RANGE = ProjectileCase(
    "different-height-range", 8.0, 12.0, 5.0, 1.0, "displacementXQ",
    8.0 * ((12.0 + math.sqrt(12.0**2 + 2.0 * 9.81 * 4.0)) / 9.81),
)
INTERMEDIATE_HEIGHT_AMBIGUOUS = ProjectileCase(
    "intermediate-height-ambiguous", 6.0, 12.0, 0.0, 5.0, "durationQ", None,
    event_kind="reaches_condition",
)
MAXIMUM_HEIGHT = ProjectileCase(
    "maximum-height", 7.0, 14.0, 3.0, None, "endHeightQ",
    3.0 + 14.0**2 / (2.0 * 9.81), event_kind="turnaround",
)

LANDING_CASES = (
    SAME_HEIGHT_TIME,
    SAME_HEIGHT_RANGE,
    SAME_HEIGHT_IMPACT_Y,
    HORIZONTAL_FROM_HEIGHT,
    VERTICAL_LAUNCH_TIME,
    DIFFERENT_HEIGHT_RANGE,
)


def _replace_quantity(payload: dict[str, object], quantity_id: str, item: dict[str, object]) -> None:
    quantities = payload["quantities"]
    assert isinstance(quantities, list)
    index = next(
        index
        for index, quantity in enumerate(quantities)
        if quantity["quantity_id"] == quantity_id
    )
    quantities[index] = item


def _q(
    quantity_id: str,
    symbol_id: str,
    role: str,
    dimension: DimensionVector,
    *,
    value: float | None = None,
    unit: str = "1",
    frame_id: str | None = None,
    interval_id: str | None = "flightInterval",
    event_id: str | None = None,
    component: str = "unspecified",
    subject_id: str = "projectile",
) -> dict[str, object]:
    return _quantity(
        quantity_id,
        symbol_id,
        role,
        subject_id,
        dimension,
        value=value,
        unit=unit,
        frame_id=frame_id,
        interval_id=interval_id,
        event_id=event_id,
        component=component,
    )


def _payload(case: ProjectileCase) -> dict[str, object]:
    payload = _constant_acceleration_payload("x")
    payload["metadata"].update(
        system_type=case.metadata_label,
        subtype="typedTwoComponentEndpoint",
        model_id="projectileSameFixture",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["entities"] = [
        {
            "entity_id": "projectile",
            "primitive": "particle",
            "label": "ball",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": [],
            "model_confidence": None,
        },
        {
            "entity_id": "world",
            "primitive": "environment",
            "label": "world",
            "aliases": [],
            "component_of_entity_id": None,
            "evidence_refs": [],
            "model_confidence": None,
        },
    ]
    payload["reference_frames"] = [
        {
            "frame_id": "flightFrame",
            "frame_type": "cartesian_2d",
            "origin": {"kind": "world"},
            "axes": [
                {
                    "axis": "x",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "flightFrame",
                        "axis": "x",
                        "sign": 1,
                    },
                },
                {
                    "axis": "y",
                    "direction": {
                        "kind": "axis",
                        "frame_id": "flightFrame",
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
    ]
    payload["motion_intervals"] = [
        {
            "interval_id": "flightInterval",
            "order": 1,
            "subject_ids": ["projectile", "world"],
            "frame_id": "flightFrame",
            "start_event_id": "launchEvent",
            "end_event_id": "endEvent",
            "evidence_refs": [],
        }
    ]
    payload["events"] = [
        {
            "event_id": "launchEvent",
            "kind": "release",
            "subject_ids": ["projectile"],
            "interval_ids": ["flightInterval"],
            "time_quantity_id": None,
            "evidence_refs": [],
        },
        {
            "event_id": "endEvent",
            "kind": case.event_kind,
            "subject_ids": ["projectile"],
            "interval_ids": ["flightInterval"],
            "time_quantity_id": None,
            "evidence_refs": [],
        },
    ]
    payload["symbols"] = [
        _symbol("deltaX", "displacementXQ", LENGTH),
        _symbol("deltaY", "displacementYQ", LENGTH),
        _symbol("vxStart", "startVelocityXQ", VELOCITY),
        _symbol("vyStart", "startVelocityYQ", VELOCITY),
        _symbol("vxEnd", "endVelocityXQ", VELOCITY),
        _symbol("vyEnd", "endVelocityYQ", VELOCITY),
        _symbol("ax", "accelerationXQ", ACCELERATION),
        _symbol("ay", "accelerationYQ", ACCELERATION),
        _symbol("duration", "durationQ", TIME),
        _symbol("gravity", "gravityQ", ACCELERATION),
        _symbol("heightStart", "startHeightQ", LENGTH),
        _symbol("heightEnd", "endHeightQ", LENGTH),
    ]

    maximum_height = case.hf is None
    delta_y = None if maximum_height else float(case.hf) - case.h0
    payload["quantities"] = [
        _q(
            "displacementXQ", "deltaX", "displacement", LENGTH,
            frame_id="flightFrame", component="x",
        ),
        _q(
            "displacementYQ", "deltaY", "displacement", LENGTH,
            value=delta_y, unit="m", frame_id="flightFrame", component="y",
        ),
        _q(
            "startVelocityXQ", "vxStart", "velocity", VELOCITY,
            value=case.vx0, unit="m/s", frame_id="flightFrame",
            event_id="launchEvent", component="x",
        ),
        _q(
            "startVelocityYQ", "vyStart", "velocity", VELOCITY,
            value=case.vy0, unit="m/s", frame_id="flightFrame",
            event_id="launchEvent", component="y",
        ),
        _q(
            "endVelocityXQ", "vxEnd", "velocity", VELOCITY,
            frame_id="flightFrame", event_id="endEvent", component="x",
        ),
        _q(
            "endVelocityYQ", "vyEnd", "velocity", VELOCITY,
            value=0.0 if maximum_height else None,
            unit="m/s", frame_id="flightFrame", event_id="endEvent", component="y",
        ),
        _q(
            "accelerationXQ", "ax", "acceleration", ACCELERATION,
            value=0.0, unit="m/s^2", frame_id="flightFrame", component="x",
        ),
        _q(
            "accelerationYQ", "ay", "acceleration", ACCELERATION,
            value=-case.gravity, unit="m/s^2", frame_id="flightFrame", component="y",
        ),
        _q("durationQ", "duration", "duration", TIME),
        _q(
            "gravityQ", "gravity", "gravity", ACCELERATION,
            value=case.gravity, unit="m/s^2", interval_id=None,
            subject_id="world",
        ),
        _q(
            "startHeightQ", "heightStart", "height", LENGTH,
            value=case.h0, unit="m", frame_id="flightFrame",
            event_id="launchEvent", component="y",
        ),
        _q(
            "endHeightQ", "heightEnd", "height", LENGTH,
            value=case.hf, unit="m", frame_id="flightFrame",
            event_id="endEvent", component="y",
        ),
    ]
    payload["interactions"] = [
        {
            "interaction_id": "gravityInteraction",
            "kind": "gravity",
            "participant_ids": ["projectile", "world"],
            "point_ids": [],
            "frame_id": "flightFrame",
            "interval_id": "flightInterval",
            "event_id": None,
            "quantity_ids": ["accelerationYQ", "gravityQ"],
            "evidence_refs": [],
        }
    ]
    payload["constraints"] = []
    payload["state_conditions"] = []
    payload["assumptions"] = [
        {
            "assumption_id": "constantAcceleration",
            "kind": "constant_acceleration",
            "subject_id": "projectile",
            "interval_id": "flightInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "Gravity is uniform over the flight interval.",
            "evidence_refs": [],
        },
        {
            "assumption_id": "positiveDuration",
            "kind": "strictly_positive_duration",
            "subject_id": "projectile",
            "interval_id": "flightInterval",
            "disposition": "approved",
            "proposed_role": None,
            "proposed_value": None,
            "proposed_unit": None,
            "reason": "The queried boundary follows the launch boundary.",
            "evidence_refs": [],
        },
    ]
    query_spec = {
        "durationQ": ("duration", None, None, "unspecified", "s", TIME),
        "displacementXQ": ("displacement", "flightFrame", None, "x", "m", LENGTH),
        "endVelocityXQ": ("velocity", "flightFrame", "endEvent", "x", "m/s", VELOCITY),
        "endVelocityYQ": ("velocity", "flightFrame", "endEvent", "y", "m/s", VELOCITY),
        "endHeightQ": ("height", "flightFrame", "endEvent", "y", "m", LENGTH),
    }
    role, frame_id, event_id, component, output_unit, dimension = query_spec[
        case.query_quantity_id
    ]
    payload["queries"][0]["target"].update(
        role=role,
        subject_id="projectile",
        point_id=None,
        frame_id=frame_id,
        interval_id="flightInterval",
        event_id=event_id,
        component=component,
        direction=None,
        target_quantity_id=case.query_quantity_id,
    )
    payload["queries"][0]["output_unit"] = output_unit
    payload["queries"][0]["output_dimension"] = dimension.model_dump(mode="json")
    return payload


def _compile(case: ProjectileCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: ProjectileCase):
    compiled = _compile(case)
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    return compiled.graph, result


def _selected_value(result) -> float:
    selected = next(
        item
        for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    assert isinstance(selected.candidate.query_value_si, float)
    return selected.candidate.query_value_si


@pytest.mark.parametrize("case", LANDING_CASES, ids=lambda item: item.case_id)
def test_projectile_landing_time_range_and_impact_component(case: ProjectileCase) -> None:
    graph, result = _solve(case)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    assert result.plan.primary_backend is SolveBackendKind.polynomial_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert _graph_event_ids(graph) == ("endEvent", "launchEvent")
    assert _graph_plan_event_ids(graph) == ()
    assert result.plan.event_ids == ()
    assert {item.law_id for item in graph.equations} == {
        "particle_constant_acceleration_velocity",
        "particle_constant_acceleration_position",
        "uniform_gravity_acceleration",
        "particle_height_displacement",
        "elapsed_time_positive",
    }
    assert _selected_value(result) == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)


def test_same_height_launch_root_is_retained_then_rejected() -> None:
    _, result = _solve(SAME_HEIGHT_TIME)
    assert result.terminal is MechanicsSolveTerminal.solved
    assert len(result.candidate_set.candidates) == 2
    times = sorted(
        float(next(value.value_si for value in candidate.values if value.symbol_id == "duration"))
        for candidate in result.candidate_set.candidates
    )
    assert times == pytest.approx([0.0, 20.0 / 9.81])
    assert len(result.verified_candidates) == 1
    rejected = next(item for item in result.verification_outcomes if not item.passed)
    assert any(
        check.status is VerificationCheckStatus.failed
        for check in rejected.checks
    )


def test_projectile_maximum_height_uses_turnaround_event_and_zero_vertical_velocity() -> None:
    graph, result = _solve(MAXIMUM_HEIGHT)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    assert _graph_plan_event_ids(graph) == ()
    assert len(result.candidate_set.candidates) == 1
    assert _selected_value(result) == pytest.approx(MAXIMUM_HEIGHT.expected_si, rel=1.0e-9)
    selected = result.verified_candidates[0].candidate
    values = {item.symbol_id: item.value_si for item in selected.values}
    known = {item.symbol.symbol_id: item.known_si_value for item in graph.symbols}
    assert known["vyEnd"] == pytest.approx(0.0)
    assert values["duration"] == pytest.approx(14.0 / 9.81)


def test_two_positive_event_roots_require_confirmation_instead_of_first_root_selection() -> None:
    _, result = _solve(INTERMEDIATE_HEIGHT_AMBIGUOUS)
    assert result.terminal in {
        MechanicsSolveTerminal.ambiguity,
        MechanicsSolveTerminal.needs_confirmation,
    }
    assert result.selected_candidate_id is None
    assert len(result.verified_candidates) == 2
    times = sorted(float(item.candidate.query_value_si) for item in result.verified_candidates)
    expected = sorted(
        (
            (12.0 - math.sqrt(12.0**2 - 2.0 * 9.81 * 5.0)) / 9.81,
            (12.0 + math.sqrt(12.0**2 - 2.0 * 9.81 * 5.0)) / 9.81,
        )
    )
    assert times == pytest.approx(expected)


def test_projectile_metadata_does_not_author_equations_or_root_selection() -> None:
    baseline = _ir(_payload(SAME_HEIGHT_RANGE))
    changed_payload = baseline.model_dump(mode="python", warnings="none")
    changed_payload["metadata"] = baseline.metadata.model_copy(
        update={
            "system_type": "collision_1d",
            "subtype": "adversarialLabel",
            "model_id": "differentModel",
            "source_text_sha256": "f" * 64,
        }
    )
    changed = type(baseline).model_validate(changed_payload)
    first = compile_mechanics_ir(baseline)
    second = compile_mechanics_ir(changed)
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint
    assert _graph_plan_event_ids(first.graph) == _graph_plan_event_ids(second.graph) == ()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload["interactions"].clear(),
        lambda payload: payload["assumptions"].pop(),
        lambda payload: payload["events"].pop(),
        lambda payload: payload["quantities"].__setitem__(
            next(i for i, item in enumerate(payload["quantities"]) if item["quantity_id"] == "accelerationYQ"),
            _q(
                "accelerationYQ", "ay", "acceleration", ACCELERATION,
                value=9.81, unit="m/s^2", frame_id="flightFrame", component="y",
            ),
        ),
    ),
)
def test_projectile_missing_or_contradictory_typed_authority_fails_closed(mutation) -> None:
    payload = _payload(SAME_HEIGHT_TIME)
    mutation(payload)
    try:
        compiled = compile_mechanics_ir(_ir(payload))
    except Exception:
        return
    if compiled.status is CompilerStatus.ready and compiled.graph is not None:
        assert _graph_plan_event_ids(compiled.graph) == ("endEvent", "launchEvent")
        assert solve_verified_equation_graph(compiled.graph).terminal is MechanicsSolveTerminal.unsupported
    else:
        assert compiled.status is not CompilerStatus.ready or compiled.graph is None


def test_projectile_event_waiver_rejects_graph_spoof() -> None:
    graph = _compile(SAME_HEIGHT_TIME).graph
    assert graph is not None and _graph_plan_event_ids(graph) == ()
    equation = next(
        item for item in graph.equations
        if item.law_id == "uniform_gravity_acceleration"
    )
    changed = tuple(
        item.model_copy(update={"complexity_cost": item.complexity_cost + 1})
        if item.equation_id == equation.equation_id
        else item
        for item in graph.equations
    )
    spoofed = graph.model_copy(update={"equations": changed})
    assert _graph_event_ids(spoofed) == ("endEvent", "launchEvent")
    assert _graph_plan_event_ids(spoofed) == ("endEvent", "launchEvent")


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    (SAME_HEIGHT_TIME, HORIZONTAL_FROM_HEIGHT, VERTICAL_LAUNCH_TIME, DIFFERENT_HEIGHT_RANGE),
    ids=lambda item: item.case_id,
)
def test_projectile_same_fixture_numeric_parity(case: ProjectileCase) -> None:
    graph, result = _solve(case)
    assert result.terminal is MechanicsSolveTerminal.solved
    frozen = graph.fingerprint
    value = _selected_value(result)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    assert graph.fingerprint == frozen
