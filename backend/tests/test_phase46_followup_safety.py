from __future__ import annotations


from engine.canonical.adapter import attach_canonical_v2
from engine.models import CanonicalProblem, Quantity
from engine.routing.config import ROUTING_CONFIG
from engine.services import solve_problem
from engine.solvers.registry import SolverRegistry


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def test_low_confidence_single_candidate_fails_closed_below_threshold():
    problem = CanonicalProblem(
        system_type="single_particle_newton",
        raw_text="질량 2kg 물체에 알짜힘 6N이 작용한다. 가속도는?",
        knowns={"m": q("m", 2.0, "kg"), "F": q("F", 6.0, "N")},
        requested_outputs=["acceleration"],
        unknowns=["acceleration"],
        confidence="낮음",
    )
    attach_canonical_v2(problem)

    decision = SolverRegistry().route(problem)

    assert 0.0 < ROUTING_CONFIG.minimum_selection_score < 1.0
    assert decision.status == "clarify"
    assert decision.selected_solver_id is None
    assert decision.reason is not None
    assert "threshold" in decision.reason


def test_generic_and_specific_solvers_compete_before_specific_selection():
    problem = CanonicalProblem(
        system_type="particle_on_incline",
        subtype="no_friction",
        raw_text=(
            "마찰 없는 30도 경사면의 질량 2kg 물체에 알짜힘 6N이 "
            "주어졌을 때 경사면 가속도는?"
        ),
        knowns={
            "m": q("m", 2.0, "kg"),
            "F": q("F", 6.0, "N"),
            "theta": q("theta", 30.0, "deg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration"],
        unknowns=["acceleration"],
        flags={"incline": True, "no_friction": True},
        friction_type="none",
        confidence="높음",
    )
    attach_canonical_v2(problem)

    decision = SolverRegistry().route(problem)
    candidate_ids = {candidate.solver_id for candidate in decision.candidates}

    assert "incline_no_friction" in candidate_ids
    assert "single_particle_newton" in candidate_ids
    assert decision.status == "select"
    assert decision.selected_solver_id == "incline_no_friction"


def test_mixed_family_evidence_is_retained_after_legacy_type_selection():
    problem = CanonicalProblem(
        system_type="pulley_incline_hanging",
        raw_text=(
            "마찰 없는 30도 경사면의 m1=2kg 물체와 m2=3kg 매달린 "
            "물체가 도르래로 연결되어 있다. 가속도는?"
        ),
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 3.0, "kg"),
            "theta": q("theta", 30.0, "deg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration"],
        unknowns=["acceleration"],
        flags={"incline": True, "pulley": True, "no_friction": True},
        friction_type="none",
        confidence="높음",
    )
    attach_canonical_v2(problem)

    decision = SolverRegistry().route(problem)
    candidate_ids = {candidate.solver_id for candidate in decision.candidates}

    assert "pulley_incline_hanging" in candidate_ids
    assert "incline_no_friction" in candidate_ids
    assert decision.status == "select"
    assert decision.selected_solver_id == "pulley_incline_hanging"


def test_unsupported_route_never_returns_a_clarification_question():
    response = solve_problem("3차원에서 알짜힘 4N이 작용할 때 가속도는?")

    assert response.ok is False
    assert response.route_decision is not None
    assert response.route_decision.status == "unsupported"
    assert response.clarification is None
    assert response.unsupported_reason is not None
    assert "3D" in response.unsupported_reason

def test_banked_curve_wording_does_not_create_incline_family_competition():
    response = solve_problem(
        "마찰 없는 경사진 커브 반지름 R=80m, 뱅크각 20도일 때 설계속도를 구하라."
    )

    assert response.ok is True
    assert response.route_decision is not None
    assert response.route_decision.status == "select"
    assert response.route_decision.selected_solver_id == "banked_curve_no_friction"
    assert "incline_no_friction" not in {
        candidate.solver_id for candidate in response.route_decision.candidates
    }

