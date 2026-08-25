"""The rest-start constant-acceleration closure, end to end in the engine.

Two typed defects meet in one shape:

* the displacement equation ``dx = v0*t + a*t^2/2`` does not contain the final
  velocity, so requiring one before emitting it made a whole interval
  unsolvable whenever the question never said where the motion ended up; and
* a graph whose only event label is the boundary a rest condition names is a
  *state* boundary, not a timed root event to be located, so it belongs with the
  other static-boundary shapes the solver already recognises rather than in the
  timed-event fail-closed path.

Every check here is structural.  Nothing reads problem text, a family, a fixture
ID, or an expected answer.
"""

from __future__ import annotations

import pytest

from engine.mechanics.compiler.contracts import CompilerStatus
from engine.mechanics.laws import apply_core_laws
from engine.mechanics.solver.contracts import (
    _graph_plan_event_ids,
    _is_static_constant_acceleration_boundary_graph,
    _is_static_rest_boundary_constant_acceleration_graph,
)
from engine.mechanics.solver.planner import plan_equation_graph

from test_phase56_mechanics_compiler import (
    ACCELERATION,
    compile_mechanics_ir,
    LENGTH,
    TIME,
    VELOCITY,
    _constant_acceleration_payload,
    _ir,
    _quantity,
    _symbol,
)


def _rest_payload(*, keep_end_velocity: bool = False) -> dict[str, object]:
    """The same interval, with the end velocity replaced by a rest boundary.

    The question asks for the acceleration; the source gives the travel and the
    elapsed time and says the motion began at rest.  Nothing states where it
    ended up, which is exactly the shape the old nesting could not emit.
    """

    payload = _constant_acceleration_payload("x")
    payload["symbols"] = [
        _symbol("deltaX", "displacementQ", LENGTH),
        _symbol("vStart", "startVelocityQ", VELOCITY),
        _symbol("accel", "accelerationQ", ACCELERATION),
        _symbol("duration", "durationQ", TIME),
        *(
            [_symbol("vEnd", "endVelocityQ", VELOCITY)]
            if keep_end_velocity
            else []
        ),
    ]
    payload["quantities"] = [
        _quantity(
            "displacementQ", "deltaX", "displacement", "bodyA", LENGTH,
            value=8.0, unit="m", frame_id="motionFrame",
            interval_id="motionInterval", component="x",
        ),
        _quantity(
            "startVelocityQ", "vStart", "velocity", "bodyA", VELOCITY,
            frame_id="motionFrame", interval_id="motionInterval",
            event_id="motionStart", component="x",
        ),
        _quantity(
            "accelerationQ", "accel", "acceleration", "bodyA", ACCELERATION,
            frame_id="motionFrame", interval_id="motionInterval", component="x",
        ),
        _quantity(
            "durationQ", "duration", "duration", "bodyA", TIME,
            value=4.0, unit="s", interval_id="motionInterval",
        ),
        *(
            [
                _quantity(
                    "endVelocityQ", "vEnd", "velocity", "bodyA", VELOCITY,
                    frame_id="motionFrame", interval_id="motionInterval",
                    event_id="motionEnd", component="x",
                )
            ]
            if keep_end_velocity
            else []
        ),
    ]
    payload["source_evidence"] = [{
        "kind": "text",
        "evidence_id": "restEvidence",
        "quote": "The motion begins from rest.",
        "source_span": {"start": 0, "end": 28},
        "quantity_span": None,
        "occurrence_index": 0,
    }]
    payload["state_conditions"] = [
        {
            "state_condition_id": "restAtStart",
            "kind": "initial",
            "state": "at_rest",
            "subject_id": "bodyA",
            "interval_id": "motionInterval",
            "event_id": "motionStart",
            "expression": None,
            "quantity_ids": ["startVelocityQ"],
            "evidence_refs": ["restEvidence"],
        }
    ]
    payload["queries"][0]["target"].update({
        "role": "acceleration",
        "frame_id": "motionFrame",
        "interval_id": "motionInterval",
        "event_id": None,
        "component": "x",
        "target_quantity_id": "accelerationQ",
    })
    payload["queries"][0]["output_unit"] = "m/s^2"
    payload["queries"][0]["output_dimension"] = ACCELERATION.model_dump(mode="json")
    return payload


def _compiled(**kwargs):
    return compile_mechanics_ir(_ir(_rest_payload(**kwargs)))


def _law_ids(result) -> set[str]:
    assert result.graph is not None
    return {item.law_id for item in result.graph.equations}


# --------------------------------------------------------------------------
# The displacement equation stands on its own
# --------------------------------------------------------------------------


def test_the_position_law_is_emitted_without_any_final_velocity() -> None:
    laws = _law_ids(_compiled())
    assert "particle_constant_acceleration_position" in laws
    assert "particle_constant_acceleration_velocity" not in laws


def test_the_endpoint_velocity_law_still_fires_when_both_endpoints_exist() -> None:
    laws = _law_ids(_compiled(keep_end_velocity=True))
    assert "particle_constant_acceleration_velocity" in laws
    assert "particle_constant_acceleration_position" in laws


def test_the_original_two_endpoint_shape_is_unchanged() -> None:
    result = compile_mechanics_ir(_ir(_constant_acceleration_payload("x")))
    assert result.graph is not None
    equations = [
        item
        for item in result.graph.equations
        if item.law_id == "particle_constant_acceleration_position"
    ]
    assert len(equations) == 1


def test_the_position_equation_never_names_a_final_velocity() -> None:
    result = _compiled(keep_end_velocity=True)
    assert result.graph is not None
    positions = [
        item
        for item in result.graph.equations
        if item.law_id == "particle_constant_acceleration_position"
    ]
    assert positions
    for equation in positions:
        assert "endVelocityQ" not in equation.source_quantity_ids


def test_the_position_law_still_requires_its_approved_assumption() -> None:
    payload = _rest_payload()
    payload["assumptions"] = []
    laws = _law_ids(compile_mechanics_ir(_ir(payload)))
    assert "particle_constant_acceleration_position" not in laws


def test_the_position_law_still_requires_a_component_matched_displacement() -> None:
    payload = _rest_payload()
    payload["quantities"][0]["component"] = "y"
    laws = _law_ids(compile_mechanics_ir(_ir(payload)))
    assert "particle_constant_acceleration_position" not in laws


def test_the_position_law_still_requires_exactly_one_duration() -> None:
    payload = _rest_payload()
    payload["symbols"].append(_symbol("duration2", "durationQ2", TIME))
    payload["quantities"].append(
        _quantity(
            "durationQ2", "duration2", "duration", "bodyA", TIME,
            value=6.0, unit="s", interval_id="motionInterval",
        )
    )
    laws = _law_ids(compile_mechanics_ir(_ir(payload)))
    assert "particle_constant_acceleration_position" not in laws


def test_the_emission_is_a_pure_function_of_the_law_context() -> None:
    first = _law_ids(_compiled())
    assert first == _law_ids(_compiled())


# --------------------------------------------------------------------------
# The rest boundary is a state boundary, not a timed root event
# --------------------------------------------------------------------------


def test_the_rest_boundary_graph_is_recognized_as_static() -> None:
    graph = _compiled().graph
    assert graph is not None
    assert _is_static_rest_boundary_constant_acceleration_graph(graph)
    assert _graph_plan_event_ids(graph) == ()


def test_the_recognized_graph_plans_a_linear_backend_with_no_timed_events() -> None:
    result = _compiled()
    assert result.status is CompilerStatus.ready
    plan = plan_equation_graph(result.graph)
    assert plan.event_ids == ()
    assert plan.primary_backend.value == "linear_symbolic"


def test_the_two_endpoint_shape_is_not_this_one() -> None:
    graph = _compiled(keep_end_velocity=True).graph
    assert graph is not None
    assert not _is_static_rest_boundary_constant_acceleration_graph(graph)


def test_the_sibling_recognizer_does_not_claim_the_rest_shape() -> None:
    graph = _compiled().graph
    assert graph is not None
    assert not _is_static_constant_acceleration_boundary_graph(graph)


@pytest.mark.parametrize(
    "mutation",
    ["extra_equation", "extra_symbol", "no_constraint", "no_selection"],
)
def test_a_structural_near_miss_keeps_timed_event_fail_closed(mutation) -> None:
    graph = _compiled().graph
    assert graph is not None
    if mutation == "extra_equation":
        mutated = graph.model_copy(
            update={"equations": graph.equations + (graph.equations[0],)}
        )
    elif mutation == "extra_symbol":
        mutated = graph.model_copy(
            update={"symbols": graph.symbols + (graph.symbols[0],)}
        )
    elif mutation == "no_constraint":
        mutated = graph.model_copy(update={"constraints": ()})
    else:
        mutated = graph.model_copy(update={"selected_equation_ids": ()})
    assert not _is_static_rest_boundary_constant_acceleration_graph(mutated)
    assert _graph_plan_event_ids(mutated) != ()


def test_a_known_start_velocity_is_not_this_shape() -> None:
    # A rest condition over a velocity the source already gave is a restatement,
    # not the closure, so it keeps ordinary fail-closed behaviour.
    payload = _rest_payload()
    payload["quantities"][1] = _quantity(
        "startVelocityQ", "vStart", "velocity", "bodyA", VELOCITY,
        value=0.0, unit="m/s", frame_id="motionFrame",
        interval_id="motionInterval", event_id="motionStart", component="x",
    )
    graph = compile_mechanics_ir(_ir(payload)).graph
    if graph is not None:
        assert not _is_static_rest_boundary_constant_acceleration_graph(graph)
