from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib

import pytest

from engine.mechanics.compiler import CompilerStatus
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver import CandidateCoverage, SolveBackendKind
from engine.mechanics.solver.contracts import (
    _graph_event_ids,
    _graph_plan_event_ids,
)
from engine.mechanics.verification import (
    MechanicsSolveTerminal,
    VerificationCheckKind,
    VerificationCheckStatus,
)
from engine.models import CanonicalProblem, Quantity
from engine.solvers.kinematics import ConstantAcceleration1DSolver
from test_phase56_mechanics_compiler import (
    ACCELERATION,
    LENGTH,
    TIME,
    VELOCITY,
    _constant_acceleration_payload,
    _ir,
    _quantity,
    compile_mechanics_ir,
)


@dataclass(frozen=True)
class KinematicsCase:
    case_id: str
    values: dict[str, tuple[float, str]]
    query_quantity_id: str
    auxiliary_unknown_quantity_id: str
    expected_si: float


_SPEC = {
    "displacementQ": ("deltaX", "displacement", LENGTH, "m", None),
    "startVelocityQ": ("vStart", "velocity", VELOCITY, "m/s", "motionStart"),
    "endVelocityQ": ("vEnd", "velocity", VELOCITY, "m/s", "motionEnd"),
    "accelerationQ": ("accel", "acceleration", ACCELERATION, "m/s^2", None),
    "durationQ": ("duration", "duration", TIME, "s", None),
}


def _case(
    case_id: str,
    *,
    displacement: tuple[float, str] = (12.0, "m"),
    start_velocity: tuple[float, str] = (1.0, "m/s"),
    end_velocity: tuple[float, str] = (7.0, "m/s"),
    acceleration: tuple[float, str] = (2.0, "m/s^2"),
    duration: tuple[float, str] = (3.0, "s"),
    query: str,
    auxiliary: str,
    expected: float,
) -> KinematicsCase:
    return KinematicsCase(
        case_id=case_id,
        values={
            "displacementQ": displacement,
            "startVelocityQ": start_velocity,
            "endVelocityQ": end_velocity,
            "accelerationQ": acceleration,
            "durationQ": duration,
        },
        query_quantity_id=query,
        auxiliary_unknown_quantity_id=auxiliary,
        expected_si=expected,
    )


QUERY_DISPLACEMENT = _case(
    "query-displacement", query="displacementQ", auxiliary="endVelocityQ", expected=12.0
)
QUERY_INITIAL_VELOCITY = _case(
    "query-initial-velocity", query="startVelocityQ", auxiliary="displacementQ", expected=1.0
)
QUERY_FINAL_VELOCITY = _case(
    "query-final-velocity", query="endVelocityQ", auxiliary="displacementQ", expected=7.0
)
QUERY_ACCELERATION = _case(
    "query-acceleration", query="accelerationQ", auxiliary="displacementQ", expected=2.0
)
QUERY_DURATION_TWO_ROOTS = _case(
    "query-duration-two-roots", query="durationQ", auxiliary="endVelocityQ", expected=3.0
)
ZERO_ACCELERATION = _case(
    "zero-acceleration",
    displacement=(12.0, "m"),
    start_velocity=(3.0, "m/s"),
    end_velocity=(3.0, "m/s"),
    acceleration=(0.0, "m/s^2"),
    duration=(4.0, "s"),
    query="displacementQ",
    auxiliary="endVelocityQ",
    expected=12.0,
)
ZERO_INITIAL_VELOCITY = _case(
    "zero-initial-velocity",
    displacement=(9.0, "m"),
    start_velocity=(0.0, "m/s"),
    end_velocity=(6.0, "m/s"),
    acceleration=(2.0, "m/s^2"),
    duration=(3.0, "s"),
    query="endVelocityQ",
    auxiliary="displacementQ",
    expected=6.0,
)
SIGNED_NEGATIVE_MOTION = _case(
    "signed-negative-motion",
    displacement=(-6.0, "m"),
    start_velocity=(-5.0, "m/s"),
    end_velocity=(-1.0, "m/s"),
    acceleration=(2.0, "m/s^2"),
    duration=(2.0, "s"),
    query="displacementQ",
    auxiliary="endVelocityQ",
    expected=-6.0,
)
DIRECTION_REVERSAL = _case(
    "direction-reversal",
    displacement=(-2.0, "m"),
    start_velocity=(-5.0, "m/s"),
    end_velocity=(3.0, "m/s"),
    acceleration=(4.0, "m/s^2"),
    duration=(2.0, "s"),
    query="endVelocityQ",
    auxiliary="displacementQ",
    expected=3.0,
)
MIXED_UNITS = _case(
    "mixed-units",
    displacement=(25.0, "m"),
    start_velocity=(36.0, "km/h"),
    end_velocity=(0.0, "m/s"),
    acceleration=(-200.0, "cm/s^2"),
    duration=(5.0, "s"),
    query="displacementQ",
    auxiliary="endVelocityQ",
    expected=25.0,
)

ALL_QUERY_CASES = (
    QUERY_DISPLACEMENT,
    QUERY_INITIAL_VELOCITY,
    QUERY_FINAL_VELOCITY,
    QUERY_ACCELERATION,
    QUERY_DURATION_TWO_ROOTS,
)
SLOW_CASES = (
    QUERY_DISPLACEMENT,
    QUERY_INITIAL_VELOCITY,
    QUERY_FINAL_VELOCITY,
    QUERY_ACCELERATION,
    ZERO_ACCELERATION,
    DIRECTION_REVERSAL,
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


def _payload(case: KinematicsCase) -> dict[str, object]:
    payload = _constant_acceleration_payload("x")
    unknowns = {case.query_quantity_id, case.auxiliary_unknown_quantity_id}
    for quantity_id, (symbol_id, role, dimension, default_unit, event_id) in _SPEC.items():
        value, unit = case.values[quantity_id]
        _replace_quantity(
            payload,
            quantity_id,
            _quantity(
                quantity_id,
                symbol_id,
                role,
                "bodyA",
                dimension,
                value=None if quantity_id in unknowns else value,
                unit=unit or default_unit,
                frame_id=None if quantity_id == "durationQ" else "motionFrame",
                interval_id="motionInterval",
                event_id=event_id,
                component="unspecified" if quantity_id == "durationQ" else "x",
            ),
        )
    symbol_id, role, dimension, output_unit, event_id = _SPEC[case.query_quantity_id]
    payload["queries"][0]["target"].update(
        role=role,
        frame_id=None if case.query_quantity_id == "durationQ" else "motionFrame",
        interval_id="motionInterval",
        event_id=event_id,
        component="unspecified" if case.query_quantity_id == "durationQ" else "x",
        target_quantity_id=case.query_quantity_id,
    )
    payload["queries"][0]["output_unit"] = output_unit
    payload["queries"][0]["output_dimension"] = dimension.model_dump(mode="json")
    payload["metadata"].update(
        system_type="diagnosticConstantAcceleration",
        subtype="diagnosticOneDimensionalMotion",
        model_id="sameFixtureKinematics",
        source_text_sha256=hashlib.sha256(case.case_id.encode()).hexdigest(),
    )
    return payload


def _compile(case: KinematicsCase):
    return compile_mechanics_ir(_ir(_payload(case)))


def _solve(case: KinematicsCase):
    compiled = _compile(case)
    assert compiled.status is CompilerStatus.ready, compiled.issues
    assert compiled.graph is not None
    result = solve_verified_equation_graph(compiled.graph)
    assert result.terminal is MechanicsSolveTerminal.solved, result.diagnostics
    assert result.selected_candidate_id is not None
    return compiled.graph, result


def _selected_value(result) -> float:
    selected = next(
        item
        for item in result.verified_candidates
        if item.candidate.candidate_id == result.selected_candidate_id
    )
    value = selected.candidate.query_value_si
    assert isinstance(value, float)
    return value


@pytest.mark.parametrize("case", ALL_QUERY_CASES, ids=lambda item: item.case_id)
def test_constant_acceleration_each_unknown_is_solved_from_the_same_graph(case: KinematicsCase) -> None:
    graph, result = _solve(case)
    assert {item.law_id for item in graph.equations} == {
        "particle_constant_acceleration_velocity",
        "particle_constant_acceleration_position",
    }
    assert graph.rank.unknown_count == 2
    assert graph.rank.structural_rank == 2
    assert _graph_event_ids(graph) == ("motionEnd", "motionStart")
    assert _graph_plan_event_ids(graph) == ()
    assert result.plan.event_ids == ()
    assert result.plan.structure.has_event_condition is True
    assert _selected_value(result) == pytest.approx(case.expected_si, abs=1.0e-10)


@pytest.mark.parametrize(
    "case",
    (ZERO_ACCELERATION, ZERO_INITIAL_VELOCITY, SIGNED_NEGATIVE_MOTION, DIRECTION_REVERSAL, MIXED_UNITS),
    ids=lambda item: item.case_id,
)
def test_constant_acceleration_limits_signs_reversal_and_units(case: KinematicsCase) -> None:
    _, result = _solve(case)
    assert _selected_value(result) == pytest.approx(case.expected_si, abs=1.0e-9)
    assert all(
        check.status is VerificationCheckStatus.passed
        for item in result.verified_candidates
        for check in item.outcome.checks
    )


def test_constant_acceleration_time_roots_are_all_retained_before_domain_filtering() -> None:
    _, result = _solve(QUERY_DURATION_TWO_ROOTS)
    assert result.plan.primary_backend is SolveBackendKind.polynomial_symbolic
    assert result.candidate_set.coverage is CandidateCoverage.exhaustive_symbolic
    assert len(result.candidate_set.candidates) == 2
    times = sorted(
        float(next(value.value_si for value in item.values if value.symbol_id == "duration"))
        for item in result.candidate_set.candidates
    )
    assert times == pytest.approx([-4.0, 3.0])
    assert len(result.verified_candidates) == 1
    assert _selected_value(result) == pytest.approx(3.0)
    rejected = next(item for item in result.verification_outcomes if not item.passed)
    nonnegative = next(
        check for check in rejected.checks if check.kind is VerificationCheckKind.nonnegative_time
    )
    assert nonnegative.status is VerificationCheckStatus.failed


def test_constant_acceleration_metadata_and_source_digest_do_not_author_physics() -> None:
    baseline = _ir(_payload(QUERY_DISPLACEMENT))
    variant_payload = baseline.model_dump(mode="python", warnings="none")
    variant_payload["metadata"] = baseline.metadata.model_copy(
        update={
            "system_type": "projectile_motion",
            "subtype": "adversarialMetadata",
            "model_id": "differentModel",
            "source_text_sha256": "f" * 64,
        }
    )
    variant = type(baseline).model_validate(variant_payload)
    original = compile_mechanics_ir(baseline)
    changed = compile_mechanics_ir(variant)
    assert original.status is changed.status is CompilerStatus.ready
    assert original.graph is not None and changed.graph is not None
    assert original.graph.fingerprint == changed.graph.fingerprint
    assert _graph_plan_event_ids(original.graph) == ()
    assert _graph_plan_event_ids(changed.graph) == ()


def test_negative_known_duration_rejects_before_solving() -> None:
    case = _case(
        "negative-duration",
        displacement=(0.0, "m"),
        start_velocity=(1.0, "m/s"),
        end_velocity=(-1.0, "m/s"),
        acceleration=(2.0, "m/s^2"),
        duration=(-1.0, "s"),
        query="displacementQ",
        auxiliary="endVelocityQ",
        expected=0.0,
    )
    compiled = _compile(case)
    assert compiled.status is CompilerStatus.invalid
    assert compiled.graph is None


def test_inconsistent_redundant_fact_fails_closed() -> None:
    payload = _payload(QUERY_FINAL_VELOCITY)
    # Make displacement a contradictory known fact, leaving only the queried
    # final velocity unknown.  The compiler must not discard the redundant
    # position equation merely to produce an answer.
    _replace_quantity(
        payload,
        "displacementQ",
        _quantity(
            "displacementQ", "deltaX", "displacement", "bodyA", LENGTH,
            value=99.0, unit="m", frame_id="motionFrame",
            interval_id="motionInterval", component="x",
        ),
    )
    compiled = compile_mechanics_ir(_ir(payload))
    assert compiled.status in {CompilerStatus.conflicting, CompilerStatus.unsupported}
    assert compiled.graph is not None
    assert not compiled.graph.selected_equation_ids


def test_static_endpoint_waiver_rejects_graph_spoofs_and_keeps_timed_events() -> None:
    graph = _compile(QUERY_DISPLACEMENT).graph
    assert graph is not None and _graph_plan_event_ids(graph) == ()
    velocity = next(
        item for item in graph.equations
        if item.law_id == "particle_constant_acceleration_velocity"
    )
    changed_equations = tuple(
        item.model_copy(update={"scope": item.scope.model_copy(update={"event_ids": ("motionStart",)})})
        if item.equation_id == velocity.equation_id else item
        for item in graph.equations
    )
    spoofed = graph.model_copy(update={"equations": changed_equations})
    assert _graph_event_ids(spoofed) == ("motionEnd", "motionStart")
    assert _graph_plan_event_ids(spoofed) == ("motionEnd", "motionStart")
    result = solve_verified_equation_graph(spoofed)
    assert result.terminal is MechanicsSolveTerminal.unsupported


def _legacy_problem(case: KinematicsCase) -> CanonicalProblem:
    key_by_quantity = {
        "displacementQ": "s",
        "startVelocityQ": "v0",
        "endVelocityQ": "vf",
        "accelerationQ": "a",
        "durationQ": "t",
    }
    unit_by_key = {"s": "m", "v0": "m/s", "vf": "m/s", "a": "m/s^2", "t": "s"}
    unknowns = {case.query_quantity_id, case.auxiliary_unknown_quantity_id}
    knowns = {
        key_by_quantity[quantity_id]: Quantity(
            key_by_quantity[quantity_id], value, unit
        )
        for quantity_id, (value, unit) in case.values.items()
        if quantity_id not in unknowns
    }
    requested = key_by_quantity[case.query_quantity_id]
    requested_output = {
        "s": "distance",
        "v0": "initial_velocity",
        "vf": "final_velocity",
        "a": "acceleration",
        "t": "time",
    }[requested]
    return CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns=knowns,
        unknowns=[key_by_quantity[item] for item in sorted(unknowns)],
        requested_outputs=[requested_output],
        textbook_parse={"authoritative": True},
    )


@pytest.mark.slow
@pytest.mark.parametrize("case", SLOW_CASES, ids=lambda item: item.case_id)
def test_constant_acceleration_same_fixture_diagnostic_parity(case: KinematicsCase) -> None:
    graph, generic = _solve(case)
    frozen_fingerprint = graph.fingerprint
    frozen_candidates = tuple(
        tuple((value.symbol_id, value.value_si) for value in candidate.values)
        for candidate in generic.candidate_set.candidates
    )
    legacy = ConstantAcceleration1DSolver().solve(_legacy_problem(case))
    assert legacy.ok is True, legacy.unsupported_reason
    assert legacy.answer is not None and legacy.answer.numeric is not None
    assert _selected_value(generic) == pytest.approx(float(legacy.answer.numeric), abs=1.0e-5)
    assert graph.fingerprint == frozen_fingerprint
    assert tuple(
        tuple((value.symbol_id, value.value_si) for value in candidate.values)
        for candidate in generic.candidate_set.candidates
    ) == frozen_candidates
