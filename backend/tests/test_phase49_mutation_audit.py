from __future__ import annotations

import pytest

from engine.verification.consistency import PRIMARY_OUTPUT_CONTRACT
from engine.verification.oracles import load_oracle_suite
from tools.run_phase49_consistency import (
    DEFAULT_METAMORPHIC_PATH,
    DEFAULT_ORACLE_PATH,
    load_metamorphic_fixture,
    run_mutation_control,
)


pytestmark = pytest.mark.audit


def test_sign_coefficient_unit_and_constraint_mutations_are_killed():
    suite = load_oracle_suite(
        DEFAULT_ORACLE_PATH,
        minimum_cases=60,
        minimum_per_family={
            family: 10 for family in PRIMARY_OUTPUT_CONTRACT
        },
    )
    controls = load_metamorphic_fixture(
        DEFAULT_METAMORPHIC_PATH
    )["mutation_controls"]

    results = [
        run_mutation_control(control, suite)
        for control in controls
    ]

    assert {item["kind"] for item in results} == {
        "sign",
        "coefficient",
        "unit",
        "constraint_equation",
    }
    assert all(item["baseline_passed"] for item in results)
    assert all(not item["mutant_passed"] for item in results)
    assert all(item["passed"] for item in results)
    assert all(
        set(item["expected_failed_categories"])
        <= set(item["actual_failed_categories"])
        for item in results
    )
