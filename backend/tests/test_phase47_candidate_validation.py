from __future__ import annotations

import json
import math

import pytest
import sympy as sp

from app.schemas.solution import SelectionDecisionModel, SolveResponse
import engine.services as services_module
import engine.solvers.kinematics as kinematics_module
import engine.solvers.projectile as projectile_module
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
from engine.solvers.advanced_dynamics import CoriolisRelativeMotionSolver
from engine.solvers.energy_vibration import SpringEnergySpeedSolver
from engine.solvers.kinematics import ConstantAcceleration1DSolver
from engine.solvers.projectile import ProjectileMotionSolver
from engine.solvers.pulley.atwood import AtwoodPulleySolver
from engine.solvers.registry import RouteCandidate, RouteDecision
from engine.solvers.rolling.rolling_energy import PureRollingEnergySolver
from engine.solvers.rolling.rolling_general_I import RollingEnergyGeneralSolver


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


def test_single_legacy_primary_answer_without_provenance_fails_closed() -> None:
    result = SolverResult(
        ok=True,
        answer=Answer(numeric=3.0, unit="m/s²", display="a = 3.0 m/s²"),
    )

    candidate = candidate_from_solver_result(
        result,
        candidate_id="legacy",
        requested_outputs=["acceleration"],
    )

    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["acceleration"]),
    )

    assert candidate.rank_metadata["output_keys"] == []
    assert decision.status == "no_valid_solution"
    assert "requested_outputs" in _failed_ids(decision)


def test_single_legacy_primary_answer_uses_explicit_actual_provenance() -> None:
    result = SolverResult(
        ok=True,
        answer=Answer(
            numeric=3.0,
            unit="m/s²",
            display="a = 3.0 m/s²",
            output_key="acceleration",
        ),
    )

    candidate = candidate_from_solver_result(
        result,
        candidate_id="legacy-explicit",
        requested_outputs=["acceleration"],
    )
    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["acceleration"]),
    )

    assert candidate.rank_metadata["output_keys"] == ["acceleration"]
    assert candidate.numerical_mapping["acceleration"] == pytest.approx(3.0)
    assert decision.status == "selected"


@pytest.mark.parametrize(
    ("solver", "problem"),
    [
        (
            PureRollingEnergySolver(),
            CanonicalProblem(
                system_type="pure_rolling_energy",
                raw_text="속이 찬 구가 정지 상태에서 미끄러지지 않고 1m 내려온다.",
                knowns={
                    "h": Quantity("h", 1.0, "m"),
                    "g": Quantity("g", 9.81, "m/s^2"),
                },
                body_shape="solid_sphere",
                requested_outputs=["final_velocity"],
            ),
        ),
        (
            RollingEnergyGeneralSolver(),
            CanonicalProblem(
                system_type="rolling_energy_general",
                raw_text="정지 상태에서 일반 관성모멘트 물체가 미끄러지지 않고 1m 내려온다.",
                knowns={
                    "m": Quantity("m", 2.0, "kg"),
                    "I": Quantity("I", 0.04, "kg*m^2"),
                    "R": Quantity("R", 0.2, "m"),
                    "h": Quantity("h", 1.0, "m"),
                    "g": Quantity("g", 9.81, "m/s^2"),
                },
                requested_outputs=["final_velocity"],
            ),
        ),
    ],
)
def test_rolling_solver_provenance_selects_requested_final_velocity(
    solver,
    problem: CanonicalProblem,
) -> None:
    result = solver.solve(problem)

    assert result.ok is True
    assert result.answer is not None
    candidate = candidate_from_solver_result(
        result,
        candidate_id=solver.name,
        requested_outputs=["final_velocity"],
    )
    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["final_velocity"]),
    )

    assert "final_velocity" in candidate.rank_metadata["output_keys"]
    assert candidate.numerical_mapping["final_velocity"] == pytest.approx(
        result.answer.numeric
    )
    assert decision.status == "selected"


def test_coriolis_only_primary_answer_declares_acceleration_provenance() -> None:
    problem = CanonicalProblem(
        system_type="coriolis_relative_motion",
        raw_text="각속도 3rad/s인 회전계에서 상대속도 2m/s일 때 코리올리 가속도는?",
        knowns={
            "omega": Quantity("omega", 3.0, "rad/s"),
            "vrel": Quantity("vrel", 2.0, "m/s"),
        },
        requested_outputs=["acceleration"],
    )

    result = CoriolisRelativeMotionSolver().solve(problem)

    assert result.ok is True
    assert result.answer is not None
    assert result.answer.output_key == "acceleration"
    primary = next(item for item in result.answers if item.role == "primary")
    assert primary.symbol == "a_C"
    assert primary.output_key == "acceleration"
    candidate = candidate_from_solver_result(
        result,
        candidate_id="coriolis-only",
        requested_outputs=["acceleration"],
    )
    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["acceleration"]),
    )
    assert decision.status == "selected"


def test_elastic_energy_primary_answer_declares_output_provenance() -> None:
    problem = CanonicalProblem(
        system_type="spring_energy",
        raw_text="용수철 상수 200N/m인 용수철을 0.1m 압축했을 때 탄성 에너지는?",
        knowns={
            "k": Quantity("k", 200.0, "N/m"),
            "x": Quantity("x", 0.1, "m"),
        },
        requested_outputs=["elastic_energy"],
    )

    result = SpringEnergySpeedSolver().solve(problem)

    assert result.ok is True
    assert result.answer is not None
    assert result.answer.output_key == "elastic_energy"
    primary = next(item for item in result.answers if item.role == "primary")
    assert primary.symbol == "E"
    assert primary.output_key == "elastic_energy"
    candidate = candidate_from_solver_result(
        result,
        candidate_id="spring-elastic-energy",
        requested_outputs=["elastic_energy"],
    )
    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["elastic_energy"]),
    )
    assert decision.status == "selected"


def test_explicit_actual_output_provenance_cannot_claim_requested_output() -> None:
    result = SolverResult(
        ok=True,
        answer=Answer(
            numeric=6.0,
            unit="N",
            display="F = 6.0 N",
            output_key="force",
        ),
    )
    candidate = candidate_from_solver_result(
        result,
        candidate_id="actual-force",
        requested_outputs=["acceleration"],
    )

    decision = validate_and_select(
        [candidate],
        ValidationContext(requested_outputs=["acceleration"]),
    )

    assert decision.status == "no_valid_solution"
    requested_check = next(
        check
        for check in decision.rejected_candidates[0].checks
        if check.check_id == "requested_outputs"
    )
    assert requested_check.passed is False
    assert requested_check.observed == ["force"]
    assert requested_check.expected == ["acceleration"]


def test_legacy_answer_output_key_reaches_answer_item_api_end_to_end() -> None:
    response = solve_problem(
        "마찰이 없는 30도 경사면 위 블록의 가속도는?"
    )

    assert response.ok is True
    assert response.answer is not None
    assert response.answer.output_key == "acceleration"
    assert len(response.answers) == 1
    assert response.answers[0].output_key == "acceleration"


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


def test_overdetermined_kinematics_residual_contradiction_is_explained() -> None:
    problem = CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns={
            "v0": Quantity("v0", 0.0, "m/s"),
            "vf": Quantity("vf", 3.0, "m/s"),
            "a": Quantity("a", 2.0, "m/s^2"),
            "s": Quantity("s", 1.0, "m"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        raw_text="초속도 0m/s, 최종속도 3m/s, 가속도 2m/s², 변위 1m인 등가속도 운동의 시간은?",
    )

    result = ConstantAcceleration1DSolver().solve(problem)

    assert result.ok is False
    assert result.selection_decision is not None
    assert result.selection_decision.status == "no_valid_solution"
    assert any("모순" in error for error in result.verification.errors)
    assert "모순" in (result.unsupported_reason or "")

    failed_residuals = [
        check
        for rejected in result.selection_decision.rejected_candidates
        for check in rejected.checks
        if check.category == "equation_residual" and check.status == "failed"
    ]
    assert failed_residuals
    assert all(check.check_id.startswith("residual:") for check in failed_residuals)
    assert all(check.source_equation_ids for check in failed_residuals)
    assert any(
        check.absolute_error is not None
        and check.tolerance is not None
        and check.absolute_error > check.tolerance
        for check in failed_residuals
    )


def test_kinematics_preserves_negative_time_candidate_as_rejected_evidence() -> None:
    problem = CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns={
            "v0": Quantity("v0", 0.0, "m/s"),
            "a": Quantity("a", 2.0, "m/s^2"),
            "s": Quantity("s", 1.0, "m"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        raw_text="초속도 0m/s, 가속도 2m/s², 변위 1m일 때 시간은?",
    )

    result = ConstantAcceleration1DSolver().solve(problem)

    assert result.ok is True
    assert result.selection_decision is not None
    assert result.selection_decision.status == "selected"
    assert result.selection_decision.selected_candidate is not None

    all_candidates = [
        result.selection_decision.selected_candidate,
        *[
            item.candidate
            for item in result.selection_decision.rejected_candidates
        ],
    ]

    def time_value(candidate) -> float:
        return float(
            sp.N(
                next(
                    value
                    for symbol, value in candidate.symbolic_mapping.items()
                    if str(symbol) == "t"
                )
            )
        )

    assert sorted(time_value(candidate) for candidate in all_candidates) == [
        -1.0,
        1.0,
    ]
    negative = next(
        item
        for item in result.selection_decision.rejected_candidates
        if time_value(item.candidate) < 0
    )
    assert any(check.check_id == "variable:t" and not check.passed for check in negative.checks)
    assert negative.candidate.branch_info["raw_mapping"]
    assert any(
        "시간은 명시된 운동 구간에서 0 이상" in reason
        for reason in negative.rejection_reasons
    )


def test_kinematics_raw_invalid_states_reach_common_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raw_states(_equations, unknown_symbols, dict=True):
        assert dict is True
        time = unknown_symbols[0]
        return [
            {time: 1},
            {time: -1},
            {time: sp.I},
            {time: sp.oo},
            {},
        ]

    monkeypatch.setattr(kinematics_module.sp, "solve", raw_states)
    problem = CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns={
            "v0": Quantity("v0", 0.0, "m/s"),
            "vf": Quantity("vf", 2.0, "m/s"),
            "a": Quantity("a", 2.0, "m/s^2"),
            "s": Quantity("s", 1.0, "m"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        raw_text="주어진 등가속도 상태를 만족하는 시간은?",
    )

    result = ConstantAcceleration1DSolver().solve(problem)

    assert result.ok is True
    assert result.selection_decision is not None
    assert result.selection_decision.status == "selected"
    rejected = result.selection_decision.rejected_candidates
    assert len(rejected) == 4
    failed_sets = [
        {check.check_id for check in item.checks if not check.passed}
        for item in rejected
    ]
    assert any("resolved_symbols" in failed for failed in failed_sets)
    assert sum("real_finite" in failed for failed in failed_sets) >= 2
    assert any("variable:t" in failed for failed in failed_sets)
    assert any(
        any(check_id.startswith("residual:") for check_id in failed)
        for failed in failed_sets
    )
    assert all("raw_solution_index" in item.candidate.branch_info for item in rejected)


def test_kinematics_evaluates_all_fallback_subsets_after_partial_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_sizes: list[int] = []

    def sequenced_solve(equations, unknown_symbols, dict=True):
        assert dict is True
        call_index = len(call_sizes)
        call_sizes.append(len(equations))
        if call_index == 0:
            return []
        if call_index == 1:
            return [{}]
        if call_index == 2:
            return [{unknown_symbols[0]: 1}]
        return []

    monkeypatch.setattr(kinematics_module.sp, "solve", sequenced_solve)
    problem = CanonicalProblem(
        system_type="constant_acceleration_1d",
        knowns={
            "v0": Quantity("v0", 0.0, "m/s"),
            "vf": Quantity("vf", 2.0, "m/s"),
            "a": Quantity("a", 2.0, "m/s^2"),
            "s": Quantity("s", 1.0, "m"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        raw_text="주어진 등가속도 상태를 만족하는 시간은?",
    )

    result = ConstantAcceleration1DSolver().solve(problem)

    assert call_sizes == [3, 1, 1, 1]
    assert result.ok is True
    assert result.selection_decision is not None
    assert result.selection_decision.status == "selected"
    selected = result.selection_decision.selected_candidate
    assert selected is not None
    assert selected.branch_info["solve_set_index"] == 2
    assert selected.branch_info["raw_solution_index"] == 1
    assert selected.branch_info["raw_mapping"] == {"t": "1"}

    assert len(result.selection_decision.rejected_candidates) == 1
    partial = result.selection_decision.rejected_candidates[0]
    assert partial.candidate.branch_info["solve_set_index"] == 1
    assert partial.candidate.branch_info["raw_solution_index"] == 0
    assert partial.candidate.branch_info["raw_mapping"] == {}
    failed_ids = {
        check.check_id for check in partial.checks if not check.passed
    }
    assert "resolved_symbols" in failed_ids
    assert any(check_id.startswith("residual:") for check_id in failed_ids)


def test_unreachable_projectile_roots_are_rejected_with_branch_evidence() -> None:
    problem = CanonicalProblem(
        system_type="projectile_motion",
        knowns={
            "v0": Quantity("v0", 10.0, "m/s"),
            "theta": Quantity("theta", 0.0, "deg"),
            "g": Quantity("g", 9.81, "m/s^2"),
        },
        unknowns=["time"],
        requested_outputs=["time"],
        launch_height=0.0,
        landing_height=10.0,
        raw_text="수평 발사한 물체가 높이 10m에 도달하는 시간은?",
    )

    result = ProjectileMotionSolver().solve(problem)

    assert result.ok is False
    assert result.selection_decision is not None
    assert result.selection_decision.status == "no_valid_solution"
    assert len(result.selection_decision.rejected_candidates) == 2
    assert all(
        "real_finite"
        in {
            check.check_id
            for check in rejected.checks
            if not check.passed
        }
        for rejected in result.selection_decision.rejected_candidates
    )
    assert {
        rejected.candidate.branch_info["root_index"]
        for rejected in result.selection_decision.rejected_candidates
    } == {0, 1}
    assert all(
        "raw_root" in rejected.candidate.branch_info
        for rejected in result.selection_decision.rejected_candidates
    )


def test_projectile_no_algebraic_roots_preserves_selection_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(projectile_module.sp, "solve", lambda *_args, **_kwargs: [])

    result = ProjectileMotionSolver().solve(
        _projectile_problem("높이 10m에 도달하는 시간은?")
    )

    assert result.ok is False
    assert result.selection_decision is not None
    assert result.selection_decision.status == "no_valid_solution"
    assert result.selection_decision.selected_candidate is None
    assert "no candidate" in result.selection_decision.explanation


@pytest.mark.parametrize(
    ("symbol", "value"),
    [
        (sp.Symbol("integer_root", integer=True), sp.Rational(3, 2)),
        (sp.Symbol("positive_root", positive=True), -1),
    ],
)
def test_sympy_symbol_assumption_mismatch_fails_closed(symbol, value) -> None:
    decision = validate_and_select(
        [_candidate("assumption-mismatch", {symbol: value})],
        ValidationContext(requested_symbols=[symbol]),
    )

    assert decision.status == "no_valid_solution"
    assert f"assumptions:{symbol}" in _failed_ids(decision)


def test_false_and_unresolved_domain_conditions_fail_closed() -> None:
    root, parameter = sp.symbols("root parameter")
    false_decision = validate_and_select(
        [
            _candidate(
                "false-domain",
                {root: 1},
                domain_conditions=[sp.Gt(root, 2)],
            )
        ],
        ValidationContext(requested_symbols=[root]),
    )
    unresolved_decision = validate_and_select(
        [
            _candidate(
                "unresolved-domain",
                {root: 1},
                domain_conditions=[sp.Gt(parameter, 0)],
            )
        ],
        ValidationContext(requested_symbols=[root]),
    )

    assert false_decision.status == "no_valid_solution"
    assert unresolved_decision.status == "no_valid_solution"
    assert "domain_condition:0" in _failed_ids(false_decision)
    assert "domain_condition:0" in _failed_ids(unresolved_decision)
    assert "unresolved" in unresolved_decision.rejected_candidates[0].rejection_reasons[0]


def test_untyped_domain_condition_is_not_parsed_or_evaluated() -> None:
    root = sp.Symbol("root")
    decision = validate_and_select(
        [
            _candidate(
                "untyped-domain",
                {root: 1},
                domain_conditions=["root > 0"],
            )
        ],
        ValidationContext(requested_symbols=[root]),
    )

    assert decision.status == "no_valid_solution"
    assert "typed SymPy boolean" in decision.rejected_candidates[0].rejection_reasons[0]


def test_variable_constraint_real_and_finite_flags_are_enforced() -> None:
    real_root = sp.Symbol("real_root")
    finite_root = sp.Symbol("finite_root")
    real_decision = validate_and_select(
        [_candidate("complex", {real_root: 1 + sp.I})],
        ValidationContext(
            constraints=[
                VariableConstraint(real_root, real=True, finite=False)
            ]
        ),
    )
    finite_decision = validate_and_select(
        [_candidate("infinite", {finite_root: float("inf")})],
        ValidationContext(
            constraints=[
                VariableConstraint(finite_root, real=False, finite=True)
            ]
        ),
    )

    real_check = next(
        check
        for check in real_decision.rejected_candidates[0].checks
        if check.check_id == "variable:real_root"
    )
    finite_check = next(
        check
        for check in finite_decision.rejected_candidates[0].checks
        if check.check_id == "variable:finite_root"
    )
    assert real_check.passed is False
    assert finite_check.passed is False
    assert "not real" in real_check.message
    assert "not finite" in finite_check.message
    assert real_check.expected["real"] is True
    assert finite_check.expected["finite"] is True


def test_nan_initial_guess_serializes_with_strict_json() -> None:
    root = sp.Symbol("root")
    candidate = _candidate("nan-initial-guess", {root: 1})
    candidate.initial_guess = {"root": math.nan}

    payload = candidate.to_dict()
    encoded = json.dumps(payload, allow_nan=False)

    assert payload["initial_guess"]["root"] == "nan"
    assert '"nan"' in encoded


def test_nonfinite_initial_guesses_are_safe_through_api_json_models() -> None:
    root = sp.Symbol("root")
    selected = _candidate("selected", {root: 1})
    selected.initial_guess = {"root": math.nan}
    rejected_positive = _candidate("rejected-positive-inf", {root: -1})
    rejected_positive.initial_guess = {"root": math.inf}
    rejected_negative = _candidate("rejected-negative-inf", {root: -2})
    rejected_negative.initial_guess = {"root": -math.inf}

    decision = validate_and_select(
        [selected, rejected_positive, rejected_negative],
        ValidationContext(
            constraints=[VariableConstraint(root, lower_bound=0)],
            requested_symbols=[root],
        ),
    )

    assert decision.status == "selected"
    assert len(decision.rejected_candidates) == 2
    payload = decision.to_dict()
    encoded = json.dumps(payload, allow_nan=False)
    assert payload["selected_candidate"]["initial_guess"]["root"] == "nan"
    assert {
        item["initial_guess"]["root"]
        for item in payload["rejected_candidates"]
    } == {"inf", "-inf"}

    decision_model = SelectionDecisionModel(**payload)
    decision_model_json = decision_model.model_dump_json()
    response = solve_problem(
        "마찰이 없는 30도 경사면 위 블록의 가속도는?"
    )
    response.selection_decision = decision_model
    response_json = response.model_dump_json()

    def assert_only_finite_json_numbers(value) -> None:
        if isinstance(value, float):
            assert math.isfinite(value)
        elif isinstance(value, dict):
            for item in value.values():
                assert_only_finite_json_numbers(item)
        elif isinstance(value, list):
            for item in value:
                assert_only_finite_json_numbers(item)

    for serialized in (encoded, decision_model_json, response_json):
        assert "NaN" not in serialized
        assert "Infinity" not in serialized
        assert_only_finite_json_numbers(json.loads(serialized))

    response_payload = json.loads(response_json)
    assert (
        response_payload["selection_decision"]["selected_candidate"]
        ["initial_guess"]["root"]
        == "nan"
    )
    assert {
        item["initial_guess"]["root"]
        for item in response_payload["selection_decision"][
            "rejected_candidates"
        ]
    } == {"inf", "-inf"}
