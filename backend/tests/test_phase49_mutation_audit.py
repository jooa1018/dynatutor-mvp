from __future__ import annotations

import json

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


def test_four_isolated_copy_mutations_are_killed_without_identity_confounders():
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
    oracle_bytes_before = DEFAULT_ORACLE_PATH.read_bytes()
    suite_before = json.dumps(
        suite.to_dict(), ensure_ascii=False, sort_keys=True
    )

    results = [
        run_mutation_control(control, suite)
        for control in controls
    ]

    assert len({item["mutation_id"] for item in results}) == 4
    assert {item["kind"] for item in results} == {
        "sign",
        "coefficient",
        "unit",
        "constraint_equation",
    }
    assert all(item["baseline_passed"] for item in results)
    assert all(not item["mutant_passed"] for item in results)
    assert all(item["passed"] for item in results)
    assert all(item["mutation_isolated"] for item in results)
    assert all(item["source_observation_unchanged"] for item in results)
    assert all(item["oracle_unchanged"] for item in results)
    assert all(item["product_result_unchanged"] for item in results)
    assert all(not item["unrelated_failed_categories"] for item in results)
    assert all(
        set(item["expected_failed_categories"])
        <= set(item["actual_failed_categories"])
        for item in results
    )
    assert all(
        "path_identity" not in item["actual_failed_categories"]
        and "solver_identity" not in item["actual_failed_categories"]
        and "policy" not in item["actual_failed_categories"]
        for item in results
    )
    assert DEFAULT_ORACLE_PATH.read_bytes() == oracle_bytes_before
    assert json.dumps(
        suite.to_dict(), ensure_ascii=False, sort_keys=True
    ) == suite_before
