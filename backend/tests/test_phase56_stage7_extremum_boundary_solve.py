"""The evidenced-extremum boundary: the first applied-profile verified solve.

The typed shape is three equalities over three unknowns with one linear
root: ``v_top = 0`` (the Package A-evidenced vertical extremum), ``a = -g``
(the authorized server-default gravity, citing its approval), and
``v_top = v_start + a·t``.  The solver's static-boundary waiver family gains
the exact recognizer for that graph; the two events are state boundaries,
not timed roots.  The gravity binding's provenance is its one approved
constant-gravity authorization — a server-valued gravity has no source span
to quote — and the independent verifier's provenance-presence rule accepts
an approved-assumption citation exactly where a source span cannot exist,
while an equation citing neither remains as unverifiable as ever.

Every structural near miss below must fail the recognizer closed, which
returns the plan to ordinary timed-event refusal.  Fixtures are
independently authored; nothing reads a case ID, family, split, expected
terminal, or expected answer in any path under test.
"""

from __future__ import annotations

import math

import pytest

from test_phase56_stage7_profile_feasibility import _projection, _throw_case

from engine.mechanics.compiler import MechanicsCompiler
from engine.mechanics.compiler.compiler import authorize_validated_mechanics_ir
from engine.mechanics.math_ast import Equality, LiteralNode
from engine.mechanics.normalization import normalize_draft
from engine.mechanics.pipeline import solve_verified_equation_graph
from engine.mechanics.solver.contracts import (
    _is_static_extremum_boundary_constant_acceleration_graph,
    _is_static_rest_boundary_constant_acceleration_graph,
)
from engine.mechanics.solver.planner import plan_equation_graph
from engine.mechanics.verification import verifier as verifier_module
from evaluation.phase56_stage7.complete_profile import ProfileId
from evaluation.phase56_stage7.complete_profile_application import (
    apply_selected_profile,
)
from evaluation.phase56_stage7.event_boundary_derivation import (
    derive_event_boundaries,
)
from evaluation.phase56_stage7.lane_b_authority import (
    build_lane_b_authority_bundle,
)
from evaluation.phase56_stage7.lane_b_runner import (
    LaneBTerminal,
    deterministic_token,
    run_lane_b_case_with_selected_profile,
)
from evaluation.phase56_stage7.profile_feasibility import (
    ProfileFeasibilityStatus,
    classify_selected_profile_outcome,
)

EXPECTED_ANSWER_SI = 9.0 / 9.81


def _compiled_graph():
    projection = _projection(_throw_case())
    bundle = build_lane_b_authority_bundle(projection)
    application = apply_selected_profile(
        projection.draft,
        ProfileId.free_flight_gravity,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert application.applied
    draft = derive_event_boundaries(application.draft).draft
    normalization = normalize_draft(
        projection.problem_text,
        draft,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert normalization.accepted and normalization.ir is not None
    authorization = authorize_validated_mechanics_ir(normalization.ir)
    compiled = MechanicsCompiler().compile(
        normalization.ir,
        validated_ir_authorization=authorization,
        approved_assumption_ids=bundle.approved_assumption_ids,
        authorized_assumptions=bundle.authorization_map(),
    )
    assert compiled.graph is not None
    return draft, compiled.graph


def _equation(graph, law_id):
    (equation,) = [item for item in graph.equations if item.law_id == law_id]
    return equation


def _replace_equation(graph, target_law_id, **updates):
    equation = _equation(graph, target_law_id)
    replaced = equation.model_copy(update=updates)
    return graph.model_copy(
        update={
            "equations": tuple(
                replaced if item.law_id == target_law_id else item
                for item in graph.equations
            )
        }
    )


def _replace_application(graph, target_law_id, **updates):
    (application,) = [
        item for item in graph.applications if item.law_id == target_law_id
    ]
    replaced = application.model_copy(update=updates)
    return graph.model_copy(
        update={
            "applications": tuple(
                replaced if item.law_id == target_law_id else item
                for item in graph.applications
            )
        }
    )


# --------------------------------------------------------------------------
# The recognized shape solves, and the answer is the fixture's own physics
# --------------------------------------------------------------------------


def test_the_extremum_graph_is_recognized_as_static():
    _, graph = _compiled_graph()
    assert _is_static_extremum_boundary_constant_acceleration_graph(graph)
    assert not _is_static_rest_boundary_constant_acceleration_graph(graph)
    plan = plan_equation_graph(graph)
    assert plan.event_ids == ()


def test_the_full_lane_delivers_the_verified_answer():
    projection = _projection(_throw_case())
    application, result = run_lane_b_case_with_selected_profile(
        projection,
        ProfileId.free_flight_gravity,
        execution_token=deterministic_token(0, run_nonce="free_flight_gravity"),
    )
    assert application.applied
    assert result.terminal is LaneBTerminal.solved
    assert result.candidate_count == 1
    assert result.verified_candidate_count == 1
    assert result.rejected_candidate_count == 0
    assert result.answer_value_si is not None
    assert math.isclose(
        result.answer_value_si, EXPECTED_ANSWER_SI, rel_tol=1.0e-9
    )
    assert result.answer_unit == "s"
    assert result.query_role == "duration"
    checks = dict(result.verification_checks)
    assert checks == {
        "equation_residual": "passed",
        "nonnegative_time": "passed",
        "query_binding": "passed",
        "source_evidence": "passed",
        "unit_consistency": "passed",
    }
    status = classify_selected_profile_outcome(
        ProfileId.free_flight_gravity, application, result
    )
    assert status is ProfileFeasibilityStatus.verified_solve_reachable


def test_the_gravity_equation_cites_its_one_approval():
    draft, graph = _compiled_graph()
    gravity = _equation(graph, "uniform_gravity_acceleration")
    (approved_gravity,) = [
        item
        for item in draft.assumptions
        if getattr(item.kind, "value", item.kind) == "constant_gravity"
    ]
    assert gravity.assumption_ids == (approved_gravity.assumption_id,)
    assert gravity.source_evidence_ids == ()
    extremum = _equation(graph, "event_vertical_extremum_velocity")
    assert extremum.source_evidence_ids
    assert extremum.assumption_ids == ()


# --------------------------------------------------------------------------
# Every structural near miss keeps timed-event fail-closed behavior
# --------------------------------------------------------------------------


def _mutations():
    def nonzero_extremum(graph):
        extremum = _equation(graph, "event_vertical_extremum_velocity")
        expression = extremum.expression
        return _replace_equation(
            graph,
            "event_vertical_extremum_velocity",
            expression=Equality(
                left=expression.left,
                right=LiteralNode(
                    value=1.0, dimension=expression.right.dimension
                ),
            ),
        )

    def unevidenced_extremum(graph):
        graph = _replace_equation(
            graph, "event_vertical_extremum_velocity", source_evidence_ids=()
        )
        return _replace_application(
            graph, "event_vertical_extremum_velocity", source_evidence_ids=()
        )

    def uncited_gravity(graph):
        graph = _replace_equation(
            graph, "uniform_gravity_acceleration", assumption_ids=()
        )
        return _replace_application(
            graph, "uniform_gravity_acceleration", assumption_ids=()
        )

    def renamed_law(graph):
        graph = _replace_equation(
            graph, "event_vertical_extremum_velocity", law_id="renamed-zero"
        )
        return _replace_application(
            graph, "event_vertical_extremum_velocity", law_id="renamed-zero"
        )

    def known_extremum_velocity(graph):
        symbols = tuple(
            item.model_copy(update={"known_si_value": 0.0})
            if item.quantity_role == "velocity" and item.known_si_value is None
            else item
            for item in graph.symbols
        )
        return graph.model_copy(update={"symbols": symbols})

    def known_duration(graph):
        symbols = tuple(
            item.model_copy(update={"known_si_value": 1.0})
            if item.quantity_role == "duration"
            else item
            for item in graph.symbols
        )
        return graph.model_copy(update={"symbols": symbols})

    def foreign_query(graph):
        (start_velocity,) = [
            item
            for item in graph.symbols
            if item.quantity_role == "velocity"
            and item.known_si_value is not None
        ]
        return graph.model_copy(
            update={"query_symbol_id": start_velocity.symbol.symbol_id}
        )

    def duplicated_equation(graph):
        gravity = _equation(graph, "uniform_gravity_acceleration")
        twin = gravity.model_copy(update={"equation_id": "eq_twin_gravity"})
        return graph.model_copy(
            update={"equations": (*graph.equations, twin)}
        )

    def underdetermined_rank(graph):
        return graph.model_copy(
            update={"rank": graph.rank.model_copy(update={"underdetermined": True})}
        )

    return {
        "nonzero_extremum": nonzero_extremum,
        "unevidenced_extremum": unevidenced_extremum,
        "uncited_gravity": uncited_gravity,
        "renamed_law": renamed_law,
        "known_extremum_velocity": known_extremum_velocity,
        "known_duration": known_duration,
        "foreign_query": foreign_query,
        "duplicated_equation": duplicated_equation,
        "underdetermined_rank": underdetermined_rank,
    }


@pytest.mark.parametrize("mutation", sorted(_mutations()))
def test_a_structural_near_miss_keeps_timed_event_fail_closed(mutation):
    _, graph = _compiled_graph()
    mutated = _mutations()[mutation](graph)
    assert not _is_static_extremum_boundary_constant_acceleration_graph(mutated)


# --------------------------------------------------------------------------
# The provenance-presence rule: evidence, or an approved citation — never
# neither
# --------------------------------------------------------------------------


def test_provenance_presence_accepts_the_citation_and_refuses_the_void():
    _, graph = _compiled_graph()
    result = solve_verified_equation_graph(graph)
    assert result.terminal.value == "solved"
    (verified,) = result.verified_candidates
    candidate = verified.candidate

    plan = plan_equation_graph(graph)
    passed = verifier_module._source_evidence(plan, candidate)
    assert passed.status.value == "passed"

    stripped = _mutations()["uncited_gravity"](graph)
    stripped_plan = plan_equation_graph(stripped)
    refused = verifier_module._source_evidence(stripped_plan, candidate)
    assert refused.status.value == "failed"
