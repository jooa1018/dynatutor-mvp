from __future__ import annotations

import json
import math

import pytest
import sympy as sp

from app.schemas.solution import SolveResponse
import engine.services as services_module
from engine.models import (
    Answer,
    AnswerItem,
    CanonicalProblem,
    Quantity,
    SolverResult,
    VerificationReport,
)
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.validators import (
    CandidateValidationCheck,
    ModelConstraint,
    SelectionDecision,
    ValidationContext,
    VariableConstraint,
    candidate_from_mapping,
    candidate_from_solver_result,
    validate_and_select,
)
from engine.services import solve_problem
from engine.solvers.kinematics import ConstantAcceleration1DSolver
from engine.solvers.projectile import ProjectileMotionSolver
from engine.solvers.pulley.atwood import AtwoodPulleySolver
from engine.solvers.registry import RouteCandidate, RouteDecision


def _candidate(candidate_id: str, mapping: dict, **kwargs):
    return candidate_from_mapping(
        mapping,
        candidate_id=candidate_id,
        **kwargs,
    )


def _selected_value(decision: SelectionDecision, symbol) -> float:
    assert decision.selected_candidate is not None
    return decision.selected_candidate.numerical_mapping[str(symbol)]


def _failed_ids(decision: SelectionDecision) -> set[str]:
    return {
        check.check_id
        for rejected in decision.rejected_candidates
        for check in rejected.checks
        if not check.passed
    }


def test_symbol_rename_invariance() -> None:
    def run(symbol):
        context = ValidationContext(
            equations=[sp.Eq(symbol**2, 4)],
            constraints=[
                VariableConstraint(
                    symbol,
                    lower_bound=0,
                    lower_inclusive=False,
                    reason="explicit positive domain",
                )
            ],
            requested_symbols=[symbol],
        )
        return validate_and_select(
            [
                _candidate("negative", {symbol: -2}),
                _candidate("positive", {symbol: 2}),
            ],
            context,
        )

    x = sp.Symbol("x")
    renamed = sp.Symbol("not_a_physics_name")
    first = run(x)
    second = run(renamed)

    assert first.status == second.status == "selected"
    assert _selected_value(first, x) == pytest.approx(2)
    assert _selected_value(second, renamed) == pytest.approx(2)
    assert len(first.rejected_candidates) == len(second.rejected_candidates) == 1
    assert {
        check.category
        for check in first.rejected_candidates[0].checks
        if not check.passed
    } == {
        check.category
        for check in second.rejected_candidates[0].checks
        if not check.passed
    }


def test_plus_minus_roots_use_explicit_bounds() -> None:
    root = sp.Symbol("root")
    decision = validate_and_select(
        [
            _candidate("minus", {root: -3}),
            _candidate("plus", {root: 3}),
        ],
        ValidationContext(
            equations=[sp.Eq(root**2, 9)],
            constraints=[VariableConstraint(root, lower_bound=0)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "selected"
    assert _selected_value(decision, root) == pytest.approx(3)
    assert [item.candidate.candidate_id for item in decision.rejected_candidates] == [
        "minus"
    ]


def test_two_positive_roots_are_ambiguous() -> None:
    root = sp.Symbol("root")
    decision = validate_and_select(
        [
            _candidate("one", {root: 1}),
            _candidate("two", {root: 2}),
        ],
        ValidationContext(
            equations=[sp.Eq((root - 1) * (root - 2), 0)],
            constraints=[
                VariableConstraint(root, lower_bound=0, lower_inclusive=False)
            ],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "ambiguous"
    assert decision.selected_candidate is None
    assert {item.candidate_id for item in decision.valid_alternatives} == {
        "one",
        "two",
    }


def test_complex_candidate_is_rejected() -> None:
    root = sp.Symbol("root")
    decision = validate_and_select(
        [_candidate("complex", {root: 2 + sp.I})],
        ValidationContext(
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "no_valid_solution"
    assert "real_finite" in _failed_ids(decision)


@pytest.mark.parametrize("value", [sp.nan, sp.oo, -sp.oo])
def test_nan_and_infinite_candidates_are_numerical_failures(value) -> None:
    root = sp.Symbol("root")
    decision = validate_and_select(
        [_candidate("bad-number", {root: value})],
        ValidationContext(
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "numerical_failure"
    assert "real_finite" in _failed_ids(decision)


def test_denominator_zero_is_rejected() -> None:
    root = sp.Symbol("root")
    decision = validate_and_select(
        [
            _candidate(
                "singular",
                {root: 0},
                denominator_conditions=[root],
            )
        ],
        ValidationContext(
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "no_valid_solution"
    assert "nonzero_denominator" in _failed_ids(decision)


def test_piecewise_with_unresolved_condition_is_rejected() -> None:
    root = sp.Symbol("root")
    condition = sp.Symbol("condition", real=True)
    value = sp.Piecewise((1, condition > 0), (2, True), evaluate=False)
    decision = validate_and_select(
        [_candidate("conditional", {root: value})],
        ValidationContext(
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "no_valid_solution"
    assert "resolved_symbols" in _failed_ids(decision)


def test_unresolved_symbol_is_rejected() -> None:
    root, parameter = sp.symbols("root parameter")
    decision = validate_and_select(
        [_candidate("unresolved", {root: 2 * parameter})],
        ValidationContext(
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "no_valid_solution"
    assert "resolved_symbols" in _failed_ids(decision)


def test_large_equation_residual_rejects_approximation() -> None:
    root = sp.Symbol("root")
    decision = validate_and_select(
        [_candidate("poor", {root: 1.4})],
        ValidationContext(
            equations=[sp.Eq(root**2, 2)],
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
            residual_tolerance=1e-10,
        ),
    )

    assert decision.status == "no_valid_solution"
    assert any(item.startswith("residual:") for item in _failed_ids(decision))


def test_time_interval_selects_only_candidate_inside_interval() -> None:
    time = sp.Symbol("renamed_time")
    decision = validate_and_select(
        [
            _candidate("inside", {time: 1}),
            _candidate("outside", {time: 4}),
        ],
        ValidationContext(
            equations=[sp.Eq((time - 1) * (time - 4), 0)],
            constraints=[VariableConstraint(time, allowed_interval=(0, 3))],
            requested_symbols=[time],
        ),
    )

    assert decision.status == "selected"
    assert _selected_value(decision, time) == pytest.approx(1)


def test_explicit_event_predicate_selects_matching_candidate() -> None:
    time = sp.Symbol("t")
    decision = validate_and_select(
        [
            _candidate("early", {time: 1}),
            _candidate("return", {time: 4}),
        ],
        ValidationContext(
            equations=[sp.Eq((time - 1) * (time - 4), 0)],
            constraints=[VariableConstraint(time, allowed_interval=(0, 5))],
            requested_symbols=[time],
            event_predicate=lambda candidate: math.isclose(
                float(candidate.symbolic_mapping[time]),
                4.0,
            ),
            event_description="return event after the turning point",
            selection_policy="explicit-event",
        ),
    )

    assert decision.status == "selected"
    assert _selected_value(decision, time) == pytest.approx(4)
    assert decision.selection_policy == "explicit-event"


def test_preferred_candidate_is_order_independent() -> None:
    time = sp.Symbol("t")
    candidates = [
        _candidate("early", {time: 1}),
        _candidate("later", {time: 4}),
    ]
    context = ValidationContext(
        constraints=[VariableConstraint(time, lower_bound=0)],
        requested_symbols=[time],
        preferred_candidate_id="later",
        event_description="the statement explicitly requests the later event",
        selection_policy="explicit-later-event",
    )

    forward = validate_and_select(candidates, context)
    reverse = validate_and_select(reversed(candidates), context)

    assert forward.status == reverse.status == "selected"
    assert forward.selected_candidate.candidate_id == "later"
    assert reverse.selected_candidate.candidate_id == "later"


def test_collision_constraint_rejects_nonconserving_candidate() -> None:
    v1f, v2f = sp.symbols("v1f v2f")
    decision = validate_and_select(
        [
            _candidate("conserving", {v1f: 0, v2f: 3}),
            _candidate("wrong", {v1f: 0, v2f: 0}),
        ],
        ValidationContext(
            constraints=[VariableConstraint(v1f), VariableConstraint(v2f)],
            model_constraints=[
                ModelConstraint(
                    "collision_momentum",
                    3 - v1f - v2f,
                    tolerance=1e-10,
                )
            ],
            requested_symbols=[v1f, v2f],
        ),
    )

    assert decision.status == "selected"
    assert decision.selected_candidate.candidate_id == "conserving"
    assert "model:collision_momentum" in _failed_ids(decision)


def test_rolling_constraint_rejects_slipping_candidate() -> None:
    speed, omega = sp.symbols("speed omega")
    decision = validate_and_select(
        [
            _candidate("rolling", {speed: 2, omega: 4}),
            _candidate("slipping", {speed: 2, omega: 3}),
        ],
        ValidationContext(
            constraints=[VariableConstraint(speed), VariableConstraint(omega)],
            model_constraints=[
                ModelConstraint("rolling_no_slip", speed - sp.Rational(1, 2) * omega)
            ],
            requested_symbols=[speed, omega],
        ),
    )

    assert decision.status == "selected"
    assert decision.selected_candidate.candidate_id == "rolling"
    assert "model:rolling_no_slip" in _failed_ids(decision)


def test_missing_requested_symbol_fails_closed() -> None:
    returned, requested = sp.symbols("returned requested")
    decision = validate_and_select(
        [_candidate("missing-output", {returned: 1})],
        ValidationContext(requested_symbols=[requested]),
    )

    assert decision.status == "no_valid_solution"
    assert "requested_symbols" in _failed_ids(decision)


def test_rejection_reason_and_branch_information_serialize() -> None:
    root = sp.Symbol("root")
    candidate = _candidate(
        "negative",
        {root: -1},
        branch_info={"root_index": 0, "source": "negative branch"},
    )
    decision = validate_and_select(
        [candidate],
        ValidationContext(
            constraints=[
                VariableConstraint(
                    root,
                    lower_bound=0,
                    reason="explicit non-negative domain",
                )
            ],
            requested_symbols=[root],
        ),
    )
    payload = decision.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)

    assert payload["status"] == "no_valid_solution"
    assert payload["rejected_candidates"][0]["branch_information"] == {
        "root_index": 0,
        "source": "negative branch",
    }
    assert "explicit non-negative domain" in encoded
    assert all(
        isinstance(check, CandidateValidationCheck)
        for check in decision.rejected_candidates[0].checks
    )


def test_equation_system_never_selects_first_root() -> None:
    root = sp.Symbol("root")
    system = EquationSystem([sp.Eq(root**2, 4)], [root])
    context = ValidationContext(
        constraints=[VariableConstraint(root)],
        requested_symbols=[root],
    )

    decision = system.solve_candidates(context)
    assert decision.status == "ambiguous"
    assert {_selected for _selected in (
        candidate.numerical_mapping[str(root)]
        for candidate in decision.valid_alternatives
    )} == {-2.0, 2.0}
    assert system.solve(context) == []


def test_equation_system_wrapper_returns_only_selected_mapping() -> None:
    root = sp.Symbol("arbitrary_name")
    system = EquationSystem([sp.Eq(root**2, 4)], [root])
    context = ValidationContext(
        constraints=[
            VariableConstraint(root, lower_bound=0, lower_inclusive=False)
        ],
        requested_symbols=[root],
    )

    decision = system.solve_candidates(context)
    result = system.solve(context)

    assert decision.status == "selected"
    assert len(result) == 1
    assert float(result[0][root]) == pytest.approx(2)


def _kinematics_problem(raw_text: str) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns={
            "v0": Quantity("v0", 10.0, "m/s"),
            "a": Quantity("a", -10.0, "m/s^2"),
            "s": Quantity("s", 0.0, "m"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        raw_text=raw_text,
    )


def test_constant_acceleration_ambiguous_and_event_selection() -> None:
    solver = ConstantAcceleration1DSolver()

    ambiguous = solver.solve(
        _kinematics_problem("초속도 10m/s, 가속도 -10m/s², 변위 0m일 때 시간은?")
    )
    later = solver.solve(
        _kinematics_problem(
            "초속도 10m/s, 가속도 -10m/s²인 물체가 다시 출발점으로 돌아오는 시간은?"
        )
    )

    assert ambiguous.ok is False
    assert ambiguous.selection_decision.status == "ambiguous"
    assert later.ok is True
    assert later.selection_decision.status == "selected"
    assert later.answer.numeric == pytest.approx(2.0)


def _projectile_problem(raw_text: str) -> CanonicalProblem:
    return CanonicalProblem(
        system_type="projectile_motion",
        knowns={
            "v0": Quantity("v0", 20.0, "m/s"),
            "theta": Quantity("theta", 60.0, "deg"),
            "g": Quantity("g", 9.81, "m/s^2"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        launch_height=0.0,
        landing_height=10.0,
        raw_text=raw_text,
    )


def test_projectile_two_events_are_not_order_selected() -> None:
    solver = ProjectileMotionSolver()

    ambiguous = solver.solve(_projectile_problem("높이 10m에 도달하는 시간은?"))
    first = solver.solve(
        _projectile_problem("처음으로 높이 10m에 도달하는 시간은?")
    )

    assert ambiguous.ok is False
    assert ambiguous.selection_decision.status == "ambiguous"
    assert first.ok is True
    assert first.selection_decision.status == "selected"
    assert first.answer.numeric == pytest.approx(0.727, abs=0.002)


def test_selection_decision_is_additive_in_schema_and_result() -> None:
    assert SolverResult(ok=False).selection_decision is None
    field = SolveResponse.model_fields["selection_decision"]
    assert not field.is_required()
    assert field.default is None
    assert "selection_decision" in SolveResponse.model_json_schema()["properties"]


def test_service_exposes_ambiguous_candidate_without_answer() -> None:
    response = solve_problem(
        "초속도 v0=10m/s, 가속도 a=-10m/s², 변위 s=0m인 "
        "등가속도 운동에서 시간은?"
    )

    assert response.ok is False
    assert response.answer is None
    assert response.answers == []
    assert response.selection_decision is not None
    assert response.selection_decision.status == "ambiguous"



def test_rejected_preferred_candidate_does_not_fallback() -> None:
    time = sp.Symbol("t")
    decision = validate_and_select(
        [
            _candidate("early", {time: 1}),
            _candidate("later", {time: 4}),
        ],
        ValidationContext(
            constraints=[
                VariableConstraint(time, allowed_interval=(0, 3))
            ],
            requested_symbols=[time],
            preferred_candidate_id="later",
            event_description="the later event was explicitly requested",
        ),
    )

    assert decision.status == "no_valid_solution"
    assert decision.selected_candidate is None
    assert [item.candidate_id for item in decision.valid_alternatives] == ["early"]


def test_parameterized_residual_applies_candidate_before_context_substitution() -> None:
    root, parameter = sp.symbols("root parameter")
    decision = validate_and_select(
        [
            _candidate(
                "parameterized",
                {root: parameter},
                substitutions={parameter: 2},
            )
        ],
        ValidationContext(
            equations=[sp.Eq(root, parameter)],
            substitutions={parameter: 2},
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "selected"


def test_parameterized_zero_denominator_is_rejected() -> None:
    root, parameter = sp.symbols("root parameter")
    decision = validate_and_select(
        [
            _candidate(
                "singular",
                {root: parameter},
                substitutions={parameter: 0},
                denominator_conditions=[root],
            )
        ],
        ValidationContext(
            substitutions={parameter: 0},
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "no_valid_solution"
    assert "nonzero_denominator" in _failed_ids(decision)


def test_unresolved_denominator_fails_closed() -> None:
    root, parameter = sp.symbols("root parameter")
    decision = validate_and_select(
        [
            _candidate(
                "unresolved-denominator",
                {root: 1},
                denominator_conditions=[parameter],
            )
        ],
        ValidationContext(
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "no_valid_solution"
    assert "nonzero_denominator" in _failed_ids(decision)


def test_single_legacy_primary_answer_adapts_to_routed_output() -> None:
    result = SolverResult(
        ok=True,
        answer=Answer(numeric=3.0, unit="m/s²", display="a = 3.0 m/s²"),
    )

    candidate = candidate_from_solver_result(
        result,
        candidate_id="legacy",
        requested_outputs=["acceleration"],
    )

    assert candidate.rank_metadata["output_keys"] == ["acceleration"]
    assert candidate.numerical_mapping["acceleration"] == pytest.approx(3.0)


def test_service_output_contract_fails_closed_and_skips_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = CanonicalProblem(
        system_type="single_particle_newton",
        knowns={
            "m": Quantity("m", 2.0, "kg"),
            "F": Quantity("F", 6.0, "N"),
        },
        unknowns=["a"],
        requested_outputs=["acceleration"],
        raw_text="test problem",
    )

    class WrongOutputSolver:
        name = "wrong_output"
        reason = "test-only routed solver"

        def solve(self, _canonical):
            internal = _candidate(
                "internally-selected",
                {sp.Symbol("internal_force"): 9.0},
            )
            return SolverResult(
                ok=True,
                answer=Answer(numeric=9.0, unit="N", display="T = 9 N"),
                answers=[
                    AnswerItem(
                        "장력",
                        "T",
                        9.0,
                        "N",
                        "장력 T = 9 N",
                        output_key="tension",
                    )
                ],
                verification=VerificationReport(passed=True),
                selection_decision=SelectionDecision(
                    status="selected",
                    selected_candidate=internal,
                    selection_policy="test-internal-selection",
                ),
            )

    class FakeRegistry:
        def __init__(self):
            self.solver = WrongOutputSolver()
            self.candidate = RouteCandidate(
                solver_id=self.solver.name,
                family="test",
                raw_score=100,
                normalized_score=1.0,
                evidence=["test-only route"],
                solver=self.solver,
            )
            self.decision = RouteDecision(
                status="select",
                candidates=[self.candidate],
                selected_solver_id=self.solver.name,
            )

        def route(self, _canonical):
            return self.decision

        def select(self, _canonical, decision=None):
            return self.solver

    verification_called = False

    def unexpected_verification(*_args, **_kwargs):
        nonlocal verification_called
        verification_called = True
        raise AssertionError("unselected candidates must not enter verification")

    monkeypatch.setattr(services_module, "extract_problem", lambda _text: canonical)
    monkeypatch.setattr(services_module, "SolverRegistry", FakeRegistry)
    monkeypatch.setattr(services_module, "verify_result", unexpected_verification)

    response = services_module.solve_problem("test problem")

    assert verification_called is False
    assert response.ok is False
    assert response.selection_decision is not None
    assert response.selection_decision.status == "no_valid_solution"
    assert response.answer is None
    assert response.answers == []


def test_particle_newton_decision_reaches_solver_result() -> None:
    canonical = CanonicalProblem(
        system_type="pulley_atwood",
        knowns={
            "m1": Quantity("m1", 2.0, "kg"),
            "m2": Quantity("m2", 5.0, "kg"),
            "g": Quantity("g", 9.81, "m/s^2"),
        },
        unknowns=["a"],
        requested_outputs=["acceleration"],
        raw_text="m1=2 kg, m2=5 kg인 Atwood 계의 가속도",
    )

    result = AtwoodPulleySolver().solve(canonical)

    assert result.ok is True
    assert result.selection_decision is not None
    assert result.selection_decision.status == "selected"
    assert (
        result.selection_decision.selection_policy
        == "particle-newton-explicit-constraints"
    )



def test_semantic_output_compatibility_accepts_force_and_minimum_speed() -> None:
    result = SolverResult(
        ok=True,
        answer=Answer(numeric=3.0, unit="m/s", display="v_min = 3 m/s"),
        answers=[
            AnswerItem(
                "최소 속도",
                "v_min",
                3.0,
                "m/s",
                "v_min = 3 m/s",
            ),
            AnswerItem(
                "한계 장력",
                "T",
                0.0,
                "N",
                "T = 0 N",
                output_key="tension",
            ),
        ],
    )
    candidate = candidate_from_solver_result(
        result,
        candidate_id="vertical-circle",
        requested_outputs=["minimum_speed", "force"],
    )

    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["minimum_speed", "force"]),
    )

    assert decision.status == "selected"


def test_collision_outputs_have_distinct_semantic_keys() -> None:
    result = SolverResult(
        ok=True,
        answer=Answer(unit="m/s", display="v1' = 1 m/s, v2' = 2 m/s"),
        answers=[
            AnswerItem("m1 충돌 후 속도", "v1'", 1.0, "m/s", "v1' = 1 m/s"),
            AnswerItem("m2 충돌 후 속도", "v2'", 2.0, "m/s", "v2' = 2 m/s"),
        ],
    )
    candidate = candidate_from_solver_result(
        result,
        candidate_id="collision",
        requested_outputs=["v1_after", "v2_after"],
    )

    assert candidate.rank_metadata["output_keys"] == ["v1_after", "v2_after"]
    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["v1_after", "v2_after"]),
    )
    assert decision.status == "selected"



def test_equation_system_merges_internal_substitutions_for_custom_residuals() -> None:
    root, parameter = sp.symbols("root parameter")
    system = EquationSystem(
        equations=[sp.Eq(root, parameter)],
        unknowns=[root],
        substitutions={parameter: 2},
    )
    decision = system.solve_candidates(
        ValidationContext(
            equations=[sp.Eq(root, parameter)],
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
        )
    )

    assert decision.status == "selected"
    assert decision.selected_candidate is not None
    assert decision.selected_candidate.numerical_mapping[str(root)] == pytest.approx(2)


def test_callable_model_constraint_applies_context_substitutions() -> None:
    root, parameter = sp.symbols("root parameter")
    candidate = _candidate(
        "parameterized",
        {root: parameter},
        substitutions={parameter: 2},
    )
    decision = validate_and_select(
        [candidate],
        ValidationContext(
            substitutions={parameter: 2},
            constraints=[VariableConstraint(root)],
            requested_symbols=[root],
            model_constraints=[
                ModelConstraint(
                    "callable-parameter",
                    lambda item: item.symbolic_mapping[root] - 2,
                )
            ],
        ),
    )

    assert decision.status == "selected"


def test_collision_service_output_contract_passes_for_both_bodies() -> None:
    response = solve_problem(
        "충돌에서 m1=2kg, m2=3kg, v1=4m/s, v2=0m/s, "
        "반발계수 e=0.5이다. 충돌 후 두 물체의 속도를 구하라."
    )

    assert response.ok is True
    assert response.verification.passed is True
    assert response.selection_decision is not None
    assert response.selection_decision.status == "selected"
    assert {item.output_key for item in response.answers} >= {
        "v1_after",
        "v2_after",
    }



@pytest.mark.parametrize(
    "requested_output",
    ["minimum_speed", "post_collision_velocity"],
)
def test_generic_final_velocity_does_not_claim_more_specific_output(
    requested_output: str,
) -> None:
    result = SolverResult(
        ok=True,
        answer=Answer(numeric=4.0, unit="m/s", display="v_f = 4 m/s"),
        answers=[
            AnswerItem("최종 속도", "v_f", 4.0, "m/s", "v_f = 4 m/s")
        ],
    )
    candidate = candidate_from_solver_result(
        result,
        candidate_id="generic-final-velocity",
        requested_outputs=[requested_output],
    )

    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=[requested_output]),
    )

    assert candidate.rank_metadata["output_keys"] == ["final_velocity"]
    assert decision.status == "no_valid_solution"



def test_perfectly_inelastic_service_exposes_both_body_outputs() -> None:
    response = solve_problem(
        "m1=2kg, m2=3kg, v1=4m/s, v2=0m/s, 완전비탄성 충돌이다. "
        "충돌 후 두 물체의 속도는?"
    )

    assert response.ok is True
    assert response.verification.passed is True
    assert response.selection_decision is not None
    assert response.selection_decision.status == "selected"
    keys = {item.output_key for item in response.answers}
    assert {
        "post_collision_velocity",
        "v1_after",
        "v2_after",
    } <= keys
