from __future__ import annotations

import pytest

from engine.verification.conditioning import (
    diagnose_jacobian_condition,
    diagnose_root_separation,
    diagnose_tolerance_sensitivity,
)
from engine.verification.policy import (
    CANDIDATE_ENGINE_ID,
    DEFAULT_TOLERANCE_POLICY,
    POLICY_VERSION,
    TolerancePolicy,
    get_tolerance_policy,
)
from engine.verification.types import (
    VerificationApplicability,
    VerificationCheck,
    VerificationStatus,
)


def test_default_policy_is_versioned_and_complete() -> None:
    policy = get_tolerance_policy()

    assert policy is DEFAULT_TOLERANCE_POLICY
    assert policy.policy_version == POLICY_VERSION
    assert policy.to_dict() == {
        "policy_version": POLICY_VERSION,
        "abs_tol": 1e-8,
        "rel_tol": 1e-4,
        "residual_tol": 1e-8,
        "constraint_tol": 1e-8,
        "conservation_tol": 1e-8,
        "near_zero_tol": 1e-9,
        "root_separation_tol": 1e-6,
        "condition_warning_threshold": 1e8,
        "sensitivity_warning_threshold": 1e6,
        "engine_specific_tolerances": {
            CANDIDATE_ENGINE_ID: {
                "abs_tol": 1e-9,
                "rel_tol": 1e-7,
                "residual_tol": 1e-9,
                "constraint_tol": 1e-9,
                "near_zero_tol": 1e-10,
            }
        },
    }


def test_candidate_engine_override_is_explicit() -> None:
    candidate = DEFAULT_TOLERANCE_POLICY.for_engine(CANDIDATE_ENGINE_ID)

    assert candidate.abs_tol == 1e-9
    assert candidate.rel_tol == 1e-7
    assert candidate.residual_tol == 1e-9
    assert candidate.constraint_tol == 1e-9
    assert candidate.near_zero_tol == 1e-10
    assert candidate.conservation_tol == 1e-8
    assert candidate.policy_version == POLICY_VERSION
    assert DEFAULT_TOLERANCE_POLICY.for_engine("unknown") is DEFAULT_TOLERANCE_POLICY


def test_engine_overrides_are_deeply_immutable() -> None:
    policy = DEFAULT_TOLERANCE_POLICY

    with pytest.raises(TypeError):
        policy.engine_specific_tolerances["other"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        policy.engine_specific_tolerances[CANDIDATE_ENGINE_ID]["abs_tol"] = 1.0  # type: ignore[index]


def test_unknown_or_invalid_override_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown tolerance override"):
        TolerancePolicy(engine_specific_tolerances={"candidate": {"typo": 1e-6}})
    with pytest.raises(ValueError, match="must be non-negative"):
        TolerancePolicy(abs_tol=-1.0)
    with pytest.raises(ValueError, match="must be positive"):
        TolerancePolicy(condition_warning_threshold=0.0)


def test_scaled_tolerance_uses_category_floor_and_relative_term() -> None:
    policy = TolerancePolicy(
        abs_tol=1e-12,
        rel_tol=1e-3,
        residual_tol=2e-5,
        engine_specific_tolerances={},
    )

    assert policy.tolerance("residual", scale=0.0) == pytest.approx(1e-3)
    assert policy.tolerance("residual", scale=20.0) == pytest.approx(2e-2)
    assert policy.threshold_for("equation_residual") == pytest.approx(2e-5)
    with pytest.raises(ValueError, match="unknown tolerance category"):
        policy.threshold_for("local_magic_number")


def test_near_zero_is_scaled_and_finite() -> None:
    policy = DEFAULT_TOLERANCE_POLICY

    assert policy.is_near_zero(5e-10)
    assert policy.is_near_zero(5e-7, scale=1_000.0)
    assert not policy.is_near_zero(2e-6, scale=1_000.0)
    assert not policy.is_near_zero(float("nan"))


def test_verification_check_serializes_every_required_field() -> None:
    check = VerificationCheck(
        check_id="energy:balance",
        category="conservation",
        status=VerificationStatus.PASSED_WITH_WARNING,
        applicability=VerificationApplicability.CONDITIONAL,
        observed={"energy": 10.0},
        expected=10.0,
        absolute_error=1e-8,
        relative_error=1e-9,
        tolerance=1e-7,
        message="near the conditioning boundary",
        evidence=("m=2 kg",),
        source_equation_ids=("W=DeltaK",),
        metadata={"diagnostic_only": True},
    )

    assert check.passed is True
    assert check.is_warning is True
    assert check.is_blocking is False
    assert check.to_dict() == {
        "check_id": "energy:balance",
        "category": "conservation",
        "status": "passed_with_warning",
        "applicability": "conditional",
        "observed": {"energy": 10.0},
        "expected": 10.0,
        "absolute_error": 1e-8,
        "relative_error": 1e-9,
        "tolerance": 1e-7,
        "message": "near the conditioning boundary",
        "evidence": ["m=2 kg"],
        "source_equation_ids": ["W=DeltaK"],
        "metadata": {"diagnostic_only": True},
    }


def test_only_failed_and_error_checks_are_blocking() -> None:
    for status in VerificationStatus:
        check = VerificationCheck(
            check_id=f"status:{status.value}",
            category="contract",
            status=status,
            applicability=VerificationApplicability.APPLICABLE,
        )
        assert check.is_blocking is (
            status in {VerificationStatus.FAILED, VerificationStatus.ERROR}
        )


def test_well_conditioned_jacobian_passes() -> None:
    check = diagnose_jacobian_condition([[1.0, 0.0], [0.0, 2.0]])

    assert check.status is VerificationStatus.PASSED
    assert check.applicability is VerificationApplicability.APPLICABLE
    assert check.observed["condition_number"] == pytest.approx(2.0)
    assert check.metadata["diagnostic_only"] is True


def test_ill_conditioned_jacobian_warns_without_blocking() -> None:
    check = diagnose_jacobian_condition([[1.0, 0.0], [0.0, 1e-10]])

    assert check.status is VerificationStatus.PASSED_WITH_WARNING
    assert check.observed["condition_number"] >= 1e8
    assert check.is_blocking is False


def test_singular_jacobian_warns_without_requiring_infinity() -> None:
    check = diagnose_jacobian_condition([[1.0, 1.0], [1.0, 1.0]])

    assert check.status is VerificationStatus.PASSED_WITH_WARNING
    assert check.observed["condition_number"] >= 1e8
    assert check.is_blocking is False


def test_missing_or_malformed_jacobian_is_structured() -> None:
    absent = diagnose_jacobian_condition(None)
    malformed = diagnose_jacobian_condition([1.0, 2.0])

    assert absent.status is VerificationStatus.NOT_APPLICABLE
    assert absent.applicability is VerificationApplicability.NOT_APPLICABLE
    assert malformed.status is VerificationStatus.INCONCLUSIVE
    assert malformed.applicability is VerificationApplicability.UNDETERMINED


def test_close_roots_warn_without_selecting_a_root() -> None:
    check = diagnose_root_separation([1.0, 1.0 + 1e-8, 4.0])

    assert check.status is VerificationStatus.PASSED_WITH_WARNING
    assert check.observed["left_index"] == 0
    assert check.observed["right_index"] == 1
    assert check.metadata["diagnostic_only"] is True
    assert "selected" not in check.metadata


def test_well_separated_roots_pass() -> None:
    check = diagnose_root_separation([-2.0, 3.0])

    assert check.status is VerificationStatus.PASSED
    assert check.observed["normalized_separation"] > check.tolerance


def test_single_or_non_numeric_roots_are_structured() -> None:
    single = diagnose_root_separation([1.0])
    invalid = diagnose_root_separation([1.0, "not-a-root"])

    assert single.status is VerificationStatus.NOT_APPLICABLE
    assert invalid.status is VerificationStatus.INCONCLUSIVE


def test_tolerance_boundary_generates_sensitivity_warning() -> None:
    policy = DEFAULT_TOLERANCE_POLICY
    threshold = policy.tolerance("residual", scale=1.0)

    check = diagnose_tolerance_sensitivity(
        threshold,
        category="residual",
        scale=1.0,
    )

    assert check.status is VerificationStatus.PASSED_WITH_WARNING
    assert check.observed["nominal_passed"] is True
    assert check.observed["tightened_passed"] is False
    assert check.observed["sensitivity_score"] >= 1e6
    assert check.is_blocking is False


def test_residual_far_from_boundary_is_stable() -> None:
    check = diagnose_tolerance_sensitivity(
        1.0,
        category="residual",
        scale=1.0,
    )

    assert check.status is VerificationStatus.PASSED
    assert check.observed["nominal_passed"] is False
    assert check.observed["loosened_passed"] is False


def test_candidate_sensitivity_uses_candidate_policy() -> None:
    threshold = DEFAULT_TOLERANCE_POLICY.tolerance(
        "residual",
        scale=1.0,
        engine_id=CANDIDATE_ENGINE_ID,
    )
    check = diagnose_tolerance_sensitivity(
        threshold,
        category="residual",
        scale=1.0,
        engine_id=CANDIDATE_ENGINE_ID,
    )

    assert threshold == pytest.approx(1e-7)
    assert check.tolerance == pytest.approx(threshold)
    assert check.status is VerificationStatus.PASSED_WITH_WARNING


def test_invalid_sensitivity_inputs_are_inconclusive() -> None:
    check = diagnose_tolerance_sensitivity(float("nan"))

    assert check.status is VerificationStatus.INCONCLUSIVE
    assert check.applicability is VerificationApplicability.UNDETERMINED

