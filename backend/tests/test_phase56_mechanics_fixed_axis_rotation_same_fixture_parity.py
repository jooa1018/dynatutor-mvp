from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.math_ast import Add, DimensionVector, Multiply, Sqrt
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.solver.contracts import _graph_event_ids, _graph_plan_event_ids
from engine.mechanics.verification import MechanicsSolveTerminal
from engine.models import CanonicalProblem, Quantity
from engine.solvers.work_rotation_impulse import FixedAxisRotationSolver
from test_phase56_mechanics_compiler import (
    ANGULAR_ACCELERATION,
    ENERGY,
    FREQUENCY,
    LENGTH,
    MOMENT_OF_INERTIA,
    TIME,
    VELOCITY,
    _ir,
    _quantity,
    _single_unknown_payload,
    _symbol,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class RotationCase:
    case_id: str
    query_quantity_id: str
    expected_si: float
    torque: tuple[float, str] = (6.0, "N*m")
    inertia: tuple[float, str] = (2.0, "kg*m^2")
    alpha: tuple[float, str] = (3.0, "rad/s^2")
    omega_start: tuple[float, str] = (2.0, "rad/s")
    omega_end: tuple[float, str] = (14.0, "rad/s")
    duration: tuple[float, str] = (4.0, "s")
    radius: tuple[float, str] = (0.5, "m")
    speed: tuple[float, str] = (7.0, "m/s")


QUERY_ALPHA = RotationCase("query-alpha", "alphaQ", 3.0)
QUERY_OMEGA = RotationCase("query-omega", "omegaEndQ", 14.0)
QUERY_TIME = RotationCase("query-time", "durationQ", 4.0)
QUERY_TORQUE = RotationCase("query-torque", "torqueQ", 6.0)
QUERY_INERTIA = RotationCase("query-inertia", "inertiaQ", 2.0)
QUERY_SPEED = RotationCase("query-speed", "speedQ", 7.0)
ZERO_TORQUE = RotationCase(
    "zero-torque", "alphaQ", 0.0,
    torque=(0.0, "N*m"), alpha=(0.0, "rad/s^2"), omega_end=(2.0, "rad/s"),
)
STARTS_FROM_REST = RotationCase(
    "starts-from-rest", "omegaEndQ", 12.0,
    omega_start=(0.0, "rad/s"), omega_end=(12.0, "rad/s"),
)
SIGNED_ROTATION = RotationCase(
    "signed-rotation", "omegaEndQ", -10.0,
    torque=(-6.0, "N*m"), alpha=(-3.0, "rad/s^2"), omega_end=(-10.0, "rad/s"),
)
MIXED_UNITS = RotationCase(
    "mixed-units", "speedQ", 2.0 * math.pi,
    torque=(6.0, "N*m"), inertia=(2.0, "kg*m^2"),
    alpha=(3.0, "rad/s^2"), omega_start=(0.0, "rad/s"),
    omega_end=(120.0, "rpm"), duration=(2.0 * math.pi / 3.0, "s"),
    radius=(50.0, "cm"), speed=(2.0 * math.pi, "m/s"),
)

QUERY_CASES = (
    QUERY_ALPHA,
    QUERY_OMEGA,
    QUERY_TIME,
    QUERY_TORQUE,
    QUERY_INERTIA,
    QUERY_SPEED,
)

_SPEC = {
    "torqueQ": ("tau", "torque", ENERGY, "N*m", None, "axisPoint", "x"),
    "inertiaQ": ("inertia", "moment_of_inertia", MOMENT_OF_INERTIA, "kg*m^2", None, "axisPoint", "unspecified"),
    "alphaQ": ("alpha", "angular_acceleration", ANGULAR_ACCELERATION, "rad/s^2", None, "axisPoint", "x"),
    "omegaStartQ": ("omegaStart", "angular_velocity", FREQUENCY, "rad/s", "rotationStart", "axisPoint", "x"),
    "omegaEndQ": ("omegaEnd", "angular_velocity", FREQUENCY, "rad/s", "rotationEnd", "axisPoint", "x"),
    "durationQ": ("duration", "duration", TIME, "s", None, None, "unspecified"),
    "radiusQ": ("radius", "radius", LENGTH, "m", None, "materialPoint", "unspecified"),
    "speedQ": ("speed", "speed", VELOCITY, "m/s", "rotationEnd", "materialPoint", "magnitude"),
}


def _q(
    quantity_id: str,
    value: tuple[float, str] | None,
    *,
    unknown: bool,
) -> dict[str, object]:
    symbol_id, role, dimension, _, event_id, point_id, component = _SPEC[quantity_id]
    raw_value, unit = value if value is not None else (0.0, "1")
    return _quantity(
        quantity_id,
        symbol_id,
        role,
        "rotor",
        dimension,
        value=None if unknown else raw_value,
        unit=unit,
        frame_id=None if quantity_id == "durationQ" else "rotationFrame",
        interval_id="rotationInterval" if quantity_id != "radiusQ" else None,
        event_id=event_id,
        point_id=point_id,
        component=component,
    )


def _payload(case: RotationCase) -> dict[str, object]:
    payload = _single_unknown_payload([])
    payload["metadata"].update(
        system_type="diagnosticFixedAxis",
        subtype="diagnosticRotation",
        model_id="sameFixtureRotation",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    payload["entities"] = [
        {
            "entity_id": "rotor", "primitive": "rigid_body", "label": "rotor",
            "aliases": [], "component_of_entity_id": None,
            "evidence_refs": [], "model_confidence": None,
        }
    ]
    payload["reference_frames"] = [
        {
            "frame_id": "rotationFrame", "frame_type": "cartesian_1d",
            "origin": {"kind": "point", "point_id": "axisPoint"},
            "axes": [{"axis": "x", "direction": {"kind": "axis", "frame_id": "rotationFrame", "axis": "x", "sign": 1}}],
            "parent_frame_id": None, "translating_with_entity_id": None,
            "rotating_about_point_id": None, "generalized_coordinate_symbol_ids": [],
            "evidence_refs": [],
        }
    ]
    payload["points"] = [
        {
            "point_id": "axisPoint", "role": "joint", "owner_entity_id": "rotor",
            "frame_id": "rotationFrame", "label": "O", "evidence_refs": [],
        },
        {
            "point_id": "materialPoint", "role": "material", "owner_entity_id": "rotor",
            "frame_id": "rotationFrame", "label": "P", "evidence_refs": [],
        },
    ]

    dynamics_query = case.query_quantity_id in {"torqueQ", "inertiaQ", "alphaQ"}
    kinematics_query = case.query_quantity_id in {"omegaEndQ", "durationQ"}
    speed_query = case.query_quantity_id == "speedQ"
    payload["motion_intervals"] = [
        {
            "interval_id": "rotationInterval", "order": 1,
            "subject_ids": ["rotor"], "frame_id": "rotationFrame",
            "start_event_id": "rotationStart" if kinematics_query else None,
            "end_event_id": "rotationEnd" if kinematics_query else None,
            "evidence_refs": [],
        }
    ]
    payload["events"] = (
        [
            {
                "event_id": "rotationStart", "kind": "start", "subject_ids": ["rotor"],
                "interval_ids": ["rotationInterval"], "time_quantity_id": None,
                "evidence_refs": [],
            },
            {
                "event_id": "rotationEnd", "kind": "finish", "subject_ids": ["rotor"],
                "interval_ids": ["rotationInterval"], "time_quantity_id": None,
                "evidence_refs": [],
            },
        ]
        if kinematics_query
        else []
    )

    if dynamics_query:
        values = {
            "torqueQ": case.torque,
            "inertiaQ": case.inertia,
            "alphaQ": case.alpha,
        }
    elif kinematics_query:
        values = {
            "alphaQ": case.alpha,
            "omegaStartQ": case.omega_start,
            "omegaEndQ": case.omega_end,
            "durationQ": case.duration,
        }
    elif speed_query:
        values = {
            "omegaEndQ": case.omega_end,
            "radiusQ": case.radius,
            "speedQ": case.speed,
        }
    else:
        raise AssertionError("unsupported typed rotation query")

    payload["symbols"] = [
        _symbol(_SPEC[quantity_id][0], quantity_id, _SPEC[quantity_id][2])
        for quantity_id in values
    ]
    payload["quantities"] = [
        _q(quantity_id, value, unknown=quantity_id == case.query_quantity_id)
        for quantity_id, value in values.items()
    ]
    if speed_query:
        for quantity in payload["quantities"]:
            if quantity["quantity_id"] in {"omegaEndQ", "speedQ"}:
                quantity["event_id"] = None

    payload["geometry"] = [
        {
            "relation_id": "axisAttachment", "kind": "attached",
            "participant_ids": ["rotor", "axisPoint"], "expression": None,
            "quantity_ids": [], "interval_id": None, "evidence_refs": [],
        }
    ]
    if speed_query:
        payload["geometry"].append(
            {
                "relation_id": "pointRadius", "kind": "radius",
                "participant_ids": ["rotor", "axisPoint", "materialPoint"],
                "expression": None, "quantity_ids": ["radiusQ"],
                "interval_id": None, "evidence_refs": [],
            }
        )

    payload["interactions"] = (
        [
            {
                "interaction_id": "appliedTorque", "kind": "applied_force",
                "participant_ids": ["rotor"], "point_ids": ["axisPoint"],
                "frame_id": "rotationFrame", "interval_id": "rotationInterval",
                "event_id": None, "quantity_ids": ["torqueQ"], "evidence_refs": [],
            }
        ]
        if dynamics_query
        else []
    )
    payload["constraints"] = []
    payload["state_conditions"] = []
    payload["assumptions"] = (
        [
            {
                "assumption_id": "constantAngular", "kind": "constant_angular_acceleration",
                "subject_id": "rotor", "interval_id": "rotationInterval",
                "disposition": "approved", "proposed_role": None,
                "proposed_value": None, "proposed_unit": None,
                "reason": "Angular acceleration is constant over the interval.",
                "evidence_refs": [],
            },
            {
                "assumption_id": "positiveDuration", "kind": "strictly_positive_duration",
                "subject_id": "rotor", "interval_id": "rotationInterval",
                "disposition": "approved", "proposed_role": None,
                "proposed_value": None, "proposed_unit": None,
                "reason": "The end state occurs after the start state.",
                "evidence_refs": [],
            },
        ]
        if kinematics_query
        else []
    )

    symbol_id, role, dimension, output_unit, _, point_id, component = _SPEC[case.query_quantity_id]
    query_quantity = next(
        item for item in payload["quantities"]
        if item["quantity_id"] == case.query_quantity_id
    )
    payload["queries"] = [
        {
            "query_id": "rotationQuery",
            "target": {
                "role": role, "subject_id": "rotor", "point_id": point_id,
                "frame_id": None if case.query_quantity_id == "durationQ" else "rotationFrame",
                "interval_id": "rotationInterval", "event_id": query_quantity["event_id"],
                "component": component, "direction": None,
                "target_quantity_id": case.query_quantity_id,
            },
            "output_unit": output_unit,
            "output_dimension": dimension.model_dump(mode="json"),
            "shape": "scalar", "evidence_refs": [],
        }
    ]
    return payload


def _compile(case: RotationCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: RotationCase):
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
def test_fixed_axis_rotation_each_requested_quantity_uses_typed_laws(case: RotationCase) -> None:
    graph, result, value = _solve(case)
    laws = {item.law_id for item in graph.equations}
    if case.query_quantity_id in {"torqueQ", "inertiaQ", "alphaQ"}:
        assert laws == {"rigid_newton_euler"}
        assert _graph_event_ids(graph) == ()
        assert _graph_plan_event_ids(graph) == ()
    elif case.query_quantity_id in {"omegaEndQ", "durationQ"}:
        assert laws == {
            "angular_velocity_derivative", "elapsed_time_positive",
        }
        assert _graph_event_ids(graph) == ("rotationEnd", "rotationStart")
        assert _graph_plan_event_ids(graph) == ()
    else:
        assert laws == {"fixed_axis_speed"}
        assert _graph_event_ids(graph) == ()
        assert _graph_plan_event_ids(graph) == ()
    assert result.plan.event_ids == ()
    assert result.plan.primary_backend in {
        SolveBackendKind.linear_symbolic, SolveBackendKind.polynomial_symbolic,
    }
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)


@pytest.mark.parametrize(
    "case",
    (ZERO_TORQUE, STARTS_FROM_REST, SIGNED_ROTATION, MIXED_UNITS),
    ids=lambda item: item.case_id,
)
def test_fixed_axis_rotation_limits_signs_and_units(case: RotationCase) -> None:
    graph, _, value = _solve(case)
    assert value == pytest.approx(case.expected_si, rel=1.0e-9, abs=1.0e-9)
    if case.query_quantity_id == "speedQ":
        speed_equation = next(item for item in graph.equations if item.law_id == "fixed_axis_speed")
        assert isinstance(speed_equation.expression.right, Multiply)
        assert any(isinstance(item, Sqrt) for item in speed_equation.expression.right.factors)


def test_nonpositive_inertia_duration_and_radius_fail_before_delivery() -> None:
    inertia = _payload(QUERY_ALPHA)
    next(item for item in inertia["quantities"] if item["quantity_id"] == "inertiaQ")["si_value"] = 0.0
    next(item for item in inertia["quantities"] if item["quantity_id"] == "inertiaQ")["raw_value"] = "0.0"
    assert compile_mechanics_ir(_ir(inertia)).status is not CompilerStatus.ready

    duration = _payload(QUERY_OMEGA)
    item = next(item for item in duration["quantities"] if item["quantity_id"] == "durationQ")
    item["si_value"] = -1.0
    item["raw_value"] = "-1.0"
    assert compile_mechanics_ir(_ir(duration)).status is not CompilerStatus.ready

    radius = _payload(QUERY_SPEED)
    item = next(item for item in radius["quantities"] if item["quantity_id"] == "radiusQ")
    item["si_value"] = 0.0
    item["raw_value"] = "0.0"
    assert compile_mechanics_ir(_ir(radius)).status is not CompilerStatus.ready


def test_fixed_axis_metadata_and_graph_spoof_do_not_author_event_waiver() -> None:
    payload = _payload(QUERY_OMEGA)
    first = compile_mechanics_ir(_ir(payload))
    changed = deepcopy(payload)
    changed["metadata"].update(
        system_type="collision_1d", subtype="wrong", model_id="other",
        source_text_sha256="f" * 64,
    )
    second = compile_mechanics_ir(_ir(changed))
    assert first.status is second.status is CompilerStatus.ready
    assert first.graph is not None and second.graph is not None
    assert first.graph.fingerprint == second.graph.fingerprint
    assert _graph_plan_event_ids(first.graph) == ()

    equation = next(item for item in first.graph.equations if item.law_id == "angular_velocity_derivative")
    changed_equations = tuple(
        item.model_copy(update={"complexity_cost": item.complexity_cost + 1})
        if item.equation_id == equation.equation_id else item
        for item in first.graph.equations
    )
    spoofed = first.graph.model_copy(update={"equations": changed_equations})
    assert _graph_event_ids(spoofed) == ("rotationEnd", "rotationStart")
    assert _graph_plan_event_ids(spoofed) == ("rotationEnd", "rotationStart")


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    (QUERY_ALPHA, QUERY_OMEGA, QUERY_SPEED, ZERO_TORQUE, SIGNED_ROTATION),
    ids=lambda item: item.case_id,
)
def test_fixed_axis_rotation_same_fixture_numeric_parity(case: RotationCase) -> None:
    _, _, generic = _solve(case)
    if case.query_quantity_id == "alphaQ":
        legacy = FixedAxisRotationSolver().solve(
            CanonicalProblem(
                system_type="fixed_axis_rotation",
                knowns={
                    "tau": Quantity("tau", case.torque[0], case.torque[1]),
                    "I": Quantity("I", case.inertia[0], case.inertia[1]),
                },
                unknowns=["alpha"], requested_outputs=["angular_acceleration"],
            )
        )
        assert legacy.ok is True and legacy.answer is not None
        assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
    elif case.query_quantity_id == "omegaEndQ":
        legacy = FixedAxisRotationSolver().solve(
            CanonicalProblem(
                system_type="fixed_axis_rotation",
                raw_text="angular velocity",
                knowns={
                    "alpha": Quantity("alpha", case.alpha[0], case.alpha[1]),
                    "t": Quantity("t", case.duration[0], case.duration[1]),
                    "omega0": Quantity("omega0", case.omega_start[0], case.omega_start[1]),
                },
                unknowns=["omega"], requested_outputs=["angular_velocity"],
            )
        )
        assert legacy.ok is True and legacy.answer is not None
        assert legacy.answer.numeric == pytest.approx(generic, abs=1.0e-5)
    else:
        # The old implementation is used only as a numeric observation.  It
        # does not select, verify, or alter the Generic candidate.
        omega = case.omega_end[0]
        if case.omega_end[1] == "rpm":
            omega = omega * 2.0 * math.pi / 60.0
        radius = case.radius[0] * (0.01 if case.radius[1] == "cm" else 1.0)
        assert generic == pytest.approx(abs(omega) * radius, rel=1.0e-9)
