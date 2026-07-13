from __future__ import annotations

from copy import deepcopy
import math

import pytest
import sympy as sp

from engine.models import (
    AnswerItem,
    CanonicalProblem,
    Quantity,
    SolverResult,
)
from engine.physics_core.equation_system import EquationSystem
from engine.physics_core.validators import (
    ValidationContext,
    candidate_from_mapping,
)
from engine.services import solve_problem
from engine.solvers.pulley import (
    AtwoodPulleySolver,
    InclineHangingPulleySolver,
    MassivePulleyAtwoodSolver,
    TableHangingPulleySolver,
)
from engine.solvers.rolling import (
    PureRollingEnergySolver,
    RollingEnergyGeneralSolver,
)
from engine.verification.invariants import InvariantStatus, evaluate_invariants
from engine.verification.policy import (
    CANDIDATE_ENGINE_ID,
    DEFAULT_TOLERANCE_POLICY,
    TolerancePolicy,
)
from engine.verification.residuals import run_residual_checks
from engine.verification.suite import verify_result


def q(symbol: str, value: float, unit: str) -> Quantity:
    return Quantity(symbol=symbol, value=value, unit=unit)


def _field(check, name: str):
    return check[name] if isinstance(check, dict) else getattr(check, name)


def _status(check) -> str:
    value = _field(check, "status")
    return str(getattr(value, "value", value))


def _category_checks(report, category: str):
    return [
        check
        for check in report.structured_checks
        if _field(check, "category") == category
    ]


def _pulley_cases():
    atwood = CanonicalProblem(
        system_type="pulley_atwood",
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 3.0, "kg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration", "tension"],
    )
    table = CanonicalProblem(
        system_type="pulley_table_hanging",
        friction_type="kinetic",
        knowns={
            "m1": q("m1", 3.0, "kg"),
            "m2": q("m2", 2.0, "kg"),
            "mu": q("mu", 0.1, ""),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration", "tension", "friction_force"],
    )
    incline = CanonicalProblem(
        system_type="pulley_incline_hanging",
        subtype="no_friction",
        friction_type="none",
        raw_text="마찰을 무시한다.",
        knowns={
            "m1": q("m1", 10.0, "kg"),
            "m2": q("m2", 1.0, "kg"),
            "theta": q("theta", 30.0, "deg"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=["acceleration", "tension"],
    )
    massive = CanonicalProblem(
        system_type="massive_pulley_atwood",
        knowns={
            "m1": q("m1", 2.0, "kg"),
            "m2": q("m2", 5.0, "kg"),
            "I": q("I", 0.12, "kg*m^2"),
            "R": q("R", 0.3, "m"),
            "g": q("g", 9.81, "m/s^2"),
        },
        requested_outputs=[
            "acceleration",
            "angular_acceleration",
            "tension",
        ],
    )
    return [
        (AtwoodPulleySolver(), atwood, "T"),
        (TableHangingPulleySolver(), table, "T"),
        (InclineHangingPulleySolver(), incline, "T"),
        (MassivePulleyAtwoodSolver(), massive, "T1"),
    ]


@pytest.mark.parametrize("solver,canonical,mutation_symbol", _pulley_cases())
def test_actual_pulley_solver_string_evidence_passes_and_mutation_fails(
    solver,
    canonical,
    mutation_symbol,
):
    result = solver.solve(canonical)
    assert result.ok, result.verification.errors

    report = verify_result(canonical, result, solver_id=solver.name)
    checks = _category_checks(report, "string_constraint")
    assert checks
    assert all(_status(check) == "passed" for check in checks)
    assert all(_field(check, "evidence") for check in checks)
    assert all(_field(check, "source_equation_ids") for check in checks)

    mutated = deepcopy(result)
    target = next(
        answer for answer in mutated.answers if answer.symbol == mutation_symbol
    )
    target.numeric = float(target.numeric) + 1.0
    mutated_report = verify_result(
        canonical,
        mutated,
        solver_id=solver.name,
    )
    assert any(
        _status(check) == "failed"
        for check in _category_checks(mutated_report, "string_constraint")
    )


@pytest.mark.parametrize(
    "problem_text",
    [
        (
            "질량이 없는 줄과 마찰이 없는 도르래 양쪽에 "
            "m1=1kg, m2=2kg 물체가 매달려 있다. 계의 가속도는?"
        ),
        (
            "질량 있는 도르래에 m1=2kg, m2=5kg가 줄로 연결되어 있다. "
            "도르래 관성모멘트 I=0.12kgm^2, 도르래 반지름 R=0.3m일 때 "
            "가속도를 구하라."
        ),
    ],
)
def test_service_publishes_passed_force_derived_string_evidence(problem_text):
    response = solve_problem(problem_text)
    assert response.ok
    checks = _category_checks(response.verification, "string_constraint")
    assert checks
    assert all(_status(check) == "passed" for check in checks)


@pytest.mark.parametrize(
    "solver,canonical",
    [
        (
            PureRollingEnergySolver(),
            CanonicalProblem(
                system_type="pure_rolling_energy",
                raw_text="정지 상태에서 미끄러지지 않고 굴러 내려간다.",
                body_shape="solid_sphere",
                knowns={
                    "h": q("h", 1.0, "m"),
                    "g": q("g", 9.81, "m/s^2"),
                    "R": q("R", 0.2, "m"),
                },
                requested_outputs=["final_velocity", "angular_velocity"],
            ),
        ),
        (
            RollingEnergyGeneralSolver(),
            CanonicalProblem(
                system_type="rolling_energy_general",
                raw_text="정지 상태에서 미끄러지지 않고 굴러 내려간다.",
                knowns={
                    "m": q("m", 2.0, "kg"),
                    "I": q("I", 0.04, "kg*m^2"),
                    "R": q("R", 0.2, "m"),
                    "h": q("h", 1.0, "m"),
                    "g": q("g", 9.81, "m/s^2"),
                },
                requested_outputs=["final_velocity", "angular_velocity"],
            ),
        ),
    ],
)
def test_actual_rolling_solver_publishes_typed_no_slip_evidence(
    solver,
    canonical,
):
    result = solver.solve(canonical)
    assert result.ok, result.verification.errors
    representative = (
        result.answer.numeric,
        result.answer.unit,
        result.answer.display,
    )
    by_key = {answer.output_key: answer for answer in result.answers}
    assert {"final_velocity", "angular_velocity"} <= set(by_key)
    assert result.answer.numeric == representative[0]
    assert result.answer.unit == representative[1]
    assert result.answer.display == representative[2]

    report = verify_result(canonical, result, solver_id=solver.name)
    checks = _category_checks(report, "pure_rolling")
    assert checks and all(_status(check) == "passed" for check in checks)

    mutated = deepcopy(result)
    angular = next(
        answer
        for answer in mutated.answers
        if answer.output_key == "angular_velocity"
    )
    angular.numeric = float(angular.numeric) + 1.0
    mutated_report = verify_result(
        canonical,
        mutated,
        solver_id=solver.name,
    )
    assert any(
        _status(check) == "failed"
        for check in _category_checks(mutated_report, "pure_rolling")
    )


def test_residual_branch_and_report_use_the_callers_policy():
    theta = math.radians(30.0)
    canonical = CanonicalProblem(
        system_type="particle_on_incline",
        subtype="with_friction",
        knowns={
            "g": q("g", 9.81, "m/s^2"),
            "theta": q("theta", 30.0, "deg"),
            "mu_s": q("mu_s", math.tan(theta), ""),
            "mu": q("mu", math.tan(theta), ""),
        },
        requested_outputs=["acceleration"],
    )
    pool = {"a": 5e-5}
    custom = TolerancePolicy(
        near_zero_tol=1e-4,
        policy_version="phase48-test-policy-v1",
    )

    default_checks, supported = run_residual_checks(
        canonical,
        pool,
        policy=DEFAULT_TOLERANCE_POLICY,
    )
    custom_checks, custom_supported = run_residual_checks(
        canonical,
        pool,
        policy=custom,
    )
    assert supported and custom_supported
    assert "경사면 뉴턴식" in default_checks[0].name
    assert "정지 조건" in custom_checks[0].name
    assert custom_checks[0].policy.policy_version == custom.policy_version

    result = SolverResult(
        ok=True,
        answers=[
            AnswerItem(
                "가속도",
                "a",
                pool["a"],
                "m/s^2",
                "a=0.00005 m/s^2",
                output_key="acceleration",
            )
        ],
    )
    report = verify_result(
        canonical,
        result,
        solver_id="particle_on_incline",
        policy=custom,
    )
    residuals = _category_checks(report, "equation_residual")
    assert report.policy_version == custom.policy_version
    assert residuals
    assert all(
        _field(check, "metadata")["policy_version"] == custom.policy_version
        for check in residuals
    )


def test_rigid_fixed_reference_uses_policy_near_zero_threshold():
    canonical = CanonicalProblem(
        system_type="plane_rigid_body_velocity",
        knowns={
            "omega": q("omega", 2.0, "rad/s"),
            "vA": q("vA", 5e-5, "m/s"),
        },
        coordinate_data={
            "rBAx": 1.0,
            "rBAy": 0.0,
            "omega_sign": 1,
        },
    )
    result = SolverResult(
        ok=True,
        answers=[
            AnswerItem("v_Bx", "v_Bx", 0.0, "m/s", "v_Bx=0"),
            AnswerItem("v_By", "v_By", 2.0, "m/s", "v_By=2"),
        ],
    )
    default_check = evaluate_invariants(
        canonical,
        result,
        validator_ids=["rigid_relative_velocity"],
    )[0]
    custom_checks = evaluate_invariants(
        canonical,
        result,
        validator_ids=["rigid_relative_velocity"],
        policy=TolerancePolicy(
            near_zero_tol=1e-4,
            policy_version="fixed-reference-test-v1",
        ),
    )
    assert default_check.status is InvariantStatus.INCONCLUSIVE
    assert all(
        check.status is InvariantStatus.PASSED for check in custom_checks
    )


def test_equation_diagnostics_use_validation_context_numeric_overrides():
    x = sp.symbols("x")
    context = ValidationContext(
        numerical_tolerance=2e-5,
        relative_tolerance=2e-3,
        residual_tolerance=4e-5,
        policy_version="context-diagnostics-v1",
    )
    decision = EquationSystem(
        [sp.Eq(sp.Integer(1_000_000) * x, sp.Integer(1_000_000))],
        [x],
    ).solve_candidates(context)
    cancellation = next(
        check
        for check in decision.diagnostics
        if str(check["check_id"]).endswith("near_cancellation")
    )
    assert decision.policy_version == context.policy_version
    assert cancellation["metadata"]["policy_version"] == context.policy_version
    assert cancellation["expected"]["large_term_floor"] == pytest.approx(500.0)


def test_candidate_complex_cutoff_remains_central_and_phase47_compatible():
    x = sp.symbols("x")
    effective = DEFAULT_TOLERANCE_POLICY.for_engine(CANDIDATE_ENGINE_ID)
    assert effective.near_zero_tol == pytest.approx(1e-10)

    accepted = candidate_from_mapping(
        {x: sp.Integer(1) + sp.I * sp.Float("5e-11")},
        candidate_id="accepted-imaginary-roundoff",
    )
    rejected = candidate_from_mapping(
        {x: sp.Integer(1) + sp.I * sp.Float("2e-10")},
        candidate_id="rejected-complex",
    )
    assert accepted.numerical_mapping["x"] == pytest.approx(1.0)
    assert "x" not in rejected.numerical_mapping


def _shape_rolling_problem(
    system_type: str,
    *,
    radius_knowns: dict[str, Quantity],
) -> CanonicalProblem:
    return CanonicalProblem(
        system_type=system_type,
        raw_text="정지 상태에서 미끄러지지 않고 굴러 내려간다.",
        body_shape=(
            "solid_sphere"
            if system_type == "pure_rolling_energy"
            else "disk"
        ),
        knowns={
            "h": q("h", 1.0, "m"),
            "g": q("g", 9.81, "m/s^2"),
            **radius_knowns,
        },
        requested_outputs=["final_velocity"],
    )


_OPTIONAL_RADIUS_CASES = [
    pytest.param({}, False, id="absent-radius"),
    pytest.param(
        {"R": Quantity(symbol="R", value=None, unit="m")},
        False,
        id="none-radius",
    ),
    pytest.param(
        {"R": q("R", 2.0, "s")},
        False,
        id="wrong-dimensional-radius",
    ),
    pytest.param(
        {
            "R": q("R", 2.0, "s"),
            "r": q("r", 0.2, "m"),
        },
        True,
        id="invalid-R-valid-r-fallback",
    ),
]


@pytest.mark.parametrize(
    "solver",
    [PureRollingEnergySolver(), RollingEnergyGeneralSolver()],
    ids=["pure-shape", "general-shape"],
)
@pytest.mark.parametrize(
    "radius_knowns,expects_angular",
    _OPTIONAL_RADIUS_CASES,
)
def test_optional_rolling_radius_never_breaks_primary_velocity(
    solver,
    radius_knowns,
    expects_angular,
):
    canonical = _shape_rolling_problem(
        "pure_rolling_energy"
        if isinstance(solver, PureRollingEnergySolver)
        else "rolling_energy_general",
        radius_knowns=radius_knowns,
    )

    result = solver.solve(canonical)

    assert result.ok, result.verification.errors
    assert result.answer is not None
    assert result.answer.numeric is not None
    output_keys = {answer.output_key for answer in result.answers}
    assert "final_velocity" in output_keys
    assert ("angular_velocity" in output_keys) is expects_angular

    report = verify_result(canonical, result, solver_id=solver.name)
    checks = _category_checks(report, "pure_rolling")
    assert checks
    expected_status = "passed" if expects_angular else "inconclusive"
    assert {_status(check) for check in checks} == {expected_status}


@pytest.mark.parametrize(
    "radius_knowns,expects_angular",
    _OPTIONAL_RADIUS_CASES,
)
def test_service_keeps_shape_rolling_solved_with_invalid_optional_radius(
    monkeypatch,
    radius_knowns,
    expects_angular,
):
    canonical = _shape_rolling_problem(
        "pure_rolling_energy",
        radius_knowns=radius_knowns,
    )
    monkeypatch.setattr(
        "engine.services.extract_problem",
        lambda _problem_text: canonical,
    )

    response = solve_problem("optional rolling radius service regression")

    assert response.ok
    assert response.answer is not None
    assert response.answer.numeric is not None
    output_keys = {answer.output_key for answer in response.answers}
    assert "final_velocity" in output_keys
    assert ("angular_velocity" in output_keys) is expects_angular
    checks = _category_checks(response.verification, "pure_rolling")
    assert checks
    expected_status = "passed" if expects_angular else "inconclusive"
    assert {_status(check) for check in checks} == {expected_status}
