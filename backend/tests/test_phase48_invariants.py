from __future__ import annotations

import json
import math

import pytest

from engine.capabilities.loader import (
    CapabilityConfigError,
    clear_capability_cache,
    load_capability_matrix,
)
from engine.models import AnswerItem, CanonicalProblem, Quantity, SolverResult
from engine.verification.invariants import (
    INVARIANT_EVALUATORS,
    InvariantStatus,
    evaluate_invariants,
)
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY


def _cp(
    system_type: str,
    knowns: dict[str, tuple[float, str]],
    *,
    requested_outputs: list[str] | None = None,
    flags: dict[str, bool] | None = None,
    friction_type: str | None = None,
    coordinate_data: dict | None = None,
    raw_text: str = "",
) -> CanonicalProblem:
    return CanonicalProblem(
        system_type=system_type,
        knowns={
            symbol: Quantity(symbol=symbol, value=value, unit=unit)
            for symbol, (value, unit) in knowns.items()
        },
        requested_outputs=list(requested_outputs or []),
        flags=dict(flags or {}),
        friction_type=friction_type,
        coordinate_data=dict(coordinate_data or {}),
        raw_text=raw_text,
    )


def _result(*answers: AnswerItem) -> SolverResult:
    return SolverResult(ok=True, answers=list(answers))


def _run(cp: CanonicalProblem, result: SolverResult, validator_id: str):
    return evaluate_invariants(cp, result, validator_ids=[validator_id])


def test_all_required_invariant_evaluators_are_registered():
    assert set(INVARIANT_EVALUATORS) == {
        "equation_residual",
        "string_constraint",
        "pure_rolling",
        "collision_momentum",
        "collision_restitution",
        "work_energy",
        "contact_normal",
        "tension_slack",
        "friction_regime",
        "pulley_no_slip",
        "rigid_relative_velocity",
        "rigid_relative_acceleration",
    }


def test_governing_residual_adapter_passes_actual_newton_answer():
    cp = _cp(
        "single_particle_newton",
        {"m": (2.0, "kg"), "F": (6.0, "N")},
    )
    result = _result(
        AnswerItem("가속도", "a", 3.0, "m/s^2", "a=3", output_key="acceleration")
    )
    checks = _run(cp, result, "equation_residual")
    assert checks and all(check.status is InvariantStatus.PASSED for check in checks)
    assert checks[0].message.startswith("역대입:")
    assert checks[0].message.endswith("✓")
    assert checks[0].tolerance == DEFAULT_TOLERANCE_POLICY.tolerance(
        "residual", scale=6.0
    )


def test_governing_residual_reports_not_applicable_for_unknown_model():
    checks = _run(_cp("unknown", {}), _result(), "equation_residual")
    assert checks[0].status is InvariantStatus.NOT_APPLICABLE


def test_governing_residual_sanitizes_ambiguous_legacy_pool_symbols():
    cp = _cp(
        "vertical_circle",
        {
            "m": (1.0, "kg"),
            "R": (2.0, "m"),
            "v": (5.0, "m/s"),
            "g": (9.81, "m/s^2"),
        },
    )
    period = AnswerItem("period", "T", 2.0, "s", "", output_key="period")
    checks = evaluate_invariants(
        cp,
        _result(period),
        validator_ids=["equation_residual"],
        answer_pool={"T": 2.0},
    )
    assert checks[0].status is InvariantStatus.INCONCLUSIVE


def test_governing_residual_rebuilds_typed_vibration_aliases():
    cp = _cp("spring_mass_vibration", {"k": (4.0, "N/m"), "m": (1.0, "kg")})
    result = _result(
        AnswerItem("주기", "T", math.pi, "s", "", output_key="period"),
        AnswerItem("진동수", "f", 1.0 / math.pi, "Hz", "", output_key="frequency"),
        AnswerItem(
            "각진동수",
            "omega",
            2.0,
            "rad/s",
            "",
            output_key="angular_frequency",
        ),
    )
    checks = _run(cp, result, "equation_residual")
    assert len(checks) == 3
    assert all(check.status is InvariantStatus.PASSED for check in checks)


def test_string_constraint_checks_two_actual_endpoint_accelerations():
    cp = _cp("pulley_atwood", {})
    result = _result(
        AnswerItem("a1", "a1", 2.0, "m/s^2", "a1=2"),
        AnswerItem("a2", "a2", -2.0, "m/s^2", "a2=-2"),
    )
    assert _run(cp, result, "string_constraint")[0].status is InvariantStatus.PASSED


def test_string_constraint_is_inconclusive_without_endpoint_pair():
    cp = _cp("pulley_atwood", {})
    result = _result(AnswerItem("a", "a", 2.0, "m/s^2", "a=2"))
    assert _run(cp, result, "string_constraint")[0].status is InvariantStatus.INCONCLUSIVE


def test_pure_rolling_uses_semantic_angular_velocity():
    cp = _cp("pure_rolling_energy", {"R": (0.5, "m")})
    result = _result(
        AnswerItem("속도", "v", 2.0, "m/s", "v=2", output_key="final_velocity"),
        AnswerItem("각속도", "omega", 4.0, "rad/s", "omega=4", output_key="angular_velocity"),
    )
    assert _run(cp, result, "pure_rolling")[0].status is InvariantStatus.PASSED


def test_bare_omega_does_not_satisfy_pure_rolling_contract():
    cp = _cp("pure_rolling_energy", {"R": (0.5, "m")})
    malformed_legacy_omega = AnswerItem(
        "모호한 omega", "omega", 4.0, "rad/s", "", output_key="angular_velocity"
    )
    # Simulate an untyped legacy payload after construction.  Normal
    # AnswerItem construction promotes omega to angular_velocity; the invariant
    # layer still fails closed if that semantic key is absent at its boundary.
    malformed_legacy_omega.output_key = None
    result = _result(
        AnswerItem("속도", "v", 2.0, "m/s", "v=2", output_key="final_velocity"),
        malformed_legacy_omega,
    )
    assert _run(cp, result, "pure_rolling")[0].status is InvariantStatus.INCONCLUSIVE


def _elastic_collision_result(v1_after: float, v2_after: float) -> SolverResult:
    return _result(
        AnswerItem("v1 after", "v1'", v1_after, "m/s", "", output_key="v1_after"),
        AnswerItem("v2 after", "v2'", v2_after, "m/s", "", output_key="v2_after"),
    )


def test_collision_momentum_and_restitution_pass():
    cp = _cp(
        "collision_1d",
        {
            "m1": (1.0, "kg"),
            "m2": (1.0, "kg"),
            "v1": (3.0, "m/s"),
            "v2": (0.0, "m/s"),
            "e": (1.0, ""),
        },
    )
    result = _elastic_collision_result(0.0, 3.0)
    checks = evaluate_invariants(
        cp,
        result,
        validator_ids=["collision_momentum", "collision_restitution"],
    )
    assert [check.status for check in checks] == [
        InvariantStatus.PASSED,
        InvariantStatus.PASSED,
    ]
    assert checks[0].tolerance == DEFAULT_TOLERANCE_POLICY.tolerance(
        "conservation", scale=3.0
    )


def test_collision_restitution_failure_is_blocking():
    cp = _cp(
        "collision_1d",
        {
            "m1": (1.0, "kg"),
            "m2": (1.0, "kg"),
            "v1": (3.0, "m/s"),
            "v2": (0.0, "m/s"),
            "e": (1.0, ""),
        },
    )
    check = _run(cp, _elastic_collision_result(1.0, 2.0), "collision_restitution")[0]
    assert check.status is InvariantStatus.FAILED
    assert check.blocking is True


def test_work_energy_passes_without_defaulting_initial_speed():
    cp = _cp(
        "work_energy_speed",
        {"m": (2.0, "kg"), "v0": (1.0, "m/s"), "W": (8.0, "J")},
    )
    result = _result(
        AnswerItem("final", "vf", 3.0, "m/s", "", output_key="final_velocity")
    )
    assert _run(cp, result, "work_energy")[0].status is InvariantStatus.PASSED


def test_work_energy_missing_v0_is_inconclusive_not_assumed_zero():
    cp = _cp("work_energy_speed", {"m": (2.0, "kg"), "W": (9.0, "J")})
    result = _result(
        AnswerItem("final", "vf", 3.0, "m/s", "", output_key="final_velocity")
    )
    assert _run(cp, result, "work_energy")[0].status is InvariantStatus.INCONCLUSIVE


def test_negative_normal_force_fails_contact_invariant():
    cp = _cp("particle_on_incline", {})
    result = _result(
        AnswerItem("normal", "N", -1.0, "N", "", output_key="normal_force")
    )
    assert _run(cp, result, "contact_normal")[0].status is InvariantStatus.FAILED


def test_bare_T_is_not_treated_as_tension():
    cp = _cp("vertical_circle", {})
    result = _result(AnswerItem("period", "T", 2.0, "s", "", output_key="period"))
    assert _run(cp, result, "tension_slack")[0].status is InvariantStatus.INCONCLUSIVE


def test_negative_semantic_tension_fails():
    cp = _cp("vertical_circle", {})
    result = _result(AnswerItem("tension", "T", -2.0, "N", "", output_key="tension"))
    assert _run(cp, result, "tension_slack")[0].status is InvariantStatus.FAILED


def test_static_friction_respects_inequality():
    cp = _cp(
        "horizontal_friction_force",
        {"mu_s": (0.5, "")},
        friction_type="static",
    )
    result = _result(
        AnswerItem("friction", "f_s", 4.0, "N", "", output_key="friction_force"),
        AnswerItem("normal", "N", 10.0, "N", "", output_key="normal_force"),
    )
    assert _run(cp, result, "friction_regime")[0].status is InvariantStatus.PASSED


def test_kinetic_friction_checks_equality():
    cp = _cp(
        "horizontal_friction_force",
        {"mu_k": (0.4, "")},
        friction_type="kinetic",
    )
    result = _result(
        AnswerItem("friction", "f_k", 3.0, "N", "", output_key="friction_force"),
        AnswerItem("normal", "N", 10.0, "N", "", output_key="normal_force"),
    )
    assert _run(cp, result, "friction_regime")[0].status is InvariantStatus.FAILED


def test_pulley_no_slip_checks_linear_and_angular_acceleration():
    cp = _cp("massive_pulley_atwood", {"R": (0.25, "m")})
    result = _result(
        AnswerItem("a", "a", 2.0, "m/s^2", "", output_key="acceleration"),
        AnswerItem("alpha", "alpha", 8.0, "rad/s^2", "", output_key="angular_acceleration"),
    )
    assert _run(cp, result, "pulley_no_slip")[0].status is InvariantStatus.PASSED


def test_rigid_relative_velocity_checks_components():
    cp = _cp(
        "plane_rigid_body_velocity",
        {"omega": (2.0, "rad/s")},
        coordinate_data={
            "vAx": 1.0,
            "vAy": 0.0,
            "rBAx": 0.0,
            "rBAy": 2.0,
            "omega_sign": 1,
        },
    )
    result = _result(
        AnswerItem("x", "v_Bx", -3.0, "m/s", ""),
        AnswerItem("y", "v_By", 0.0, "m/s", ""),
    )
    assert all(
        check.status is InvariantStatus.PASSED
        for check in _run(cp, result, "rigid_relative_velocity")
    )


def test_rigid_relative_acceleration_uses_independent_omega_alpha_signs():
    cp = _cp(
        "plane_rigid_body_acceleration",
        {"omega": (2.0, "rad/s"), "alpha": (3.0, "rad/s^2")},
        coordinate_data={
            "aAx": 0.0,
            "aAy": 0.0,
            "rBAx": 1.0,
            "rBAy": 0.0,
            "omega_sign": -1,
            "alpha_sign": 1,
        },
    )
    result = _result(
        AnswerItem("x", "a_Bx", -4.0, "m/s^2", ""),
        AnswerItem("y", "a_By", 3.0, "m/s^2", ""),
    )
    assert all(
        check.status is InvariantStatus.PASSED
        for check in _run(cp, result, "rigid_relative_acceleration")
    )


def _capability_payload(validators: list[str]) -> dict:
    return {
        "schema_version": 1,
        "source_commit": "test",
        "capabilities": [
            {
                "system_type": "single_particle_newton",
                "subtypes": [],
                "required_inputs": {
                    "all_of": [],
                    "any_of": [],
                    "conditional": [],
                },
                "requested_outputs": ["acceleration"],
                "analytic_solver": "single_particle_newton",
                "validators": validators,
            }
        ],
    }


def test_capability_loader_caches_validated_matrix(tmp_path):
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(_capability_payload(["dimension", "equation_residual"])), encoding="utf-8")
    clear_capability_cache()
    first = load_capability_matrix(path)
    second = load_capability_matrix(path)
    assert first is second
    assert first.for_solver("single_particle_newton")["system_type"] == "single_particle_newton"
    assert first.for_problem("single_particle_newton")["analytic_solver"] == "single_particle_newton"


def test_default_capability_matrix_is_loaded_from_capabilities_package():
    clear_capability_cache()
    matrix = load_capability_matrix()
    assert len(matrix.capabilities) == 29
    assert matrix.for_problem("single_particle_newton") is not None


def test_capability_loader_resolves_problem_when_solver_id_is_unavailable(tmp_path):
    payload = _capability_payload(["dimension", "equation_residual"])
    payload["capabilities"][0]["analytic_solver"] = "newton_variant"
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    clear_capability_cache()
    entry = load_capability_matrix(path).for_problem("single_particle_newton")
    assert entry is not None
    assert entry["analytic_solver"] == "newton_variant"


def test_capability_loader_rejects_unknown_validator_id(tmp_path):
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(_capability_payload(["made_up_validator"])), encoding="utf-8")
    clear_capability_cache()
    with pytest.raises(CapabilityConfigError, match="unknown validator IDs"):
        load_capability_matrix(path)


def test_capability_loader_rejects_duplicate_solver(tmp_path):
    payload = _capability_payload(["dimension"])
    payload["capabilities"].append(dict(payload["capabilities"][0]))
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    clear_capability_cache()
    with pytest.raises(CapabilityConfigError, match="duplicate analytic_solver"):
        load_capability_matrix(path)
