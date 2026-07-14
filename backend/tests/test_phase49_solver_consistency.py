from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from engine.verification.consistency import (
    PRIMARY_OUTPUT_CONTRACT,
    compare_oracle_observation,
    compare_path_observations,
    compare_three_way,
    evaluate_secondary_analytic,
)
from engine.verification.oracles import load_oracle_suite
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY
from tools.run_phase49_consistency import (
    DEFAULT_METAMORPHIC_PATH,
    DEFAULT_ORACLE_PATH,
    FIXTURE_SHA256,
    _case_evidence_from_paths,
    load_metamorphic_fixture,
    run_product_case,
    suite_verdict,
)


pytestmark = pytest.mark.regression


def _suite():
    return load_oracle_suite(
        DEFAULT_ORACLE_PATH,
        minimum_cases=60,
        minimum_per_family={
            family: 10 for family in PRIMARY_OUTPUT_CONTRACT
        },
    )


def test_phase49_oracle_fixture_has_exact_independent_coverage_and_hash():
    suite = _suite()
    counts = Counter(case.family for case in suite.cases)
    signatures = {
        json.dumps(
            {
                "family": case.family,
                "solver_id": case.solver_id,
                "canonical_inputs": dict(case.canonical_inputs),
                "outputs": sorted(case.output_by_key),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for case in suite.cases
    }

    assert hashlib.sha256(DEFAULT_ORACLE_PATH.read_bytes()).hexdigest() == (
        FIXTURE_SHA256[DEFAULT_ORACLE_PATH.name]
    )
    assert len(suite.cases) == len({case.oracle_id for case in suite.cases}) == 60
    assert len(signatures) == 60
    assert counts == Counter(
        {family: 10 for family in PRIMARY_OUTPUT_CONTRACT}
    )
    assert sum(len(case.expected_outputs) for case in suite.cases) == 70
    assert suite.policy_version == DEFAULT_TOLERANCE_POLICY.policy_version
    assert all(
        tuple(case.output_by_key) == PRIMARY_OUTPUT_CONTRACT[case.family]
        for case in suite.cases
    )
    assert all(
        case.provenance_kind == "independent_derivation"
        for case in suite.cases
    )
    assert all(
        case.expected_outcome == "solved"
        and case.expected_applicability == "applicable"
        for case in suite.cases
    )


def test_phase49_metamorphic_fixture_has_unique_21_and_four_controls():
    raw = load_metamorphic_fixture(DEFAULT_METAMORPHIC_PATH)
    transformations = {
        json.dumps(
            item["transformation"],
            sort_keys=True,
            separators=(",", ":"),
        )
        for item in raw["relations"]
    }

    assert hashlib.sha256(
        DEFAULT_METAMORPHIC_PATH.read_bytes()
    ).hexdigest() == FIXTURE_SHA256[DEFAULT_METAMORPHIC_PATH.name]
    assert len(raw["relations"]) == 21
    assert len({item["relation_id"] for item in raw["relations"]}) == 21
    assert len({item["relation_kind"] for item in raw["relations"]}) == 21
    assert len(transformations) == 21
    assert len(
        {item["mutation_id"] for item in raw["mutation_controls"]}
    ) == 4
    assert {item["kind"] for item in raw["mutation_controls"]} == {
        "sign",
        "coefficient",
        "unit",
        "constraint_equation",
    }


@pytest.mark.parametrize(
    "oracle_id",
    [
        "p49.incline.001",
        "p49.pulley.001",
        "p49.collision.001",
        "p49.rolling.001",
        "p49.work_energy.001",
        "p49.fixed_axis_rotation.001",
    ],
)
def test_six_actual_product_families_reach_phase48_observation_path(
    oracle_id,
):
    case = _suite().by_id[oracle_id]
    execution = run_product_case(case)

    assert execution.solver_id == case.solver_id
    assert execution.selection_status == "selected"
    assert execution.result.verification.passed
    assert tuple(execution.observation.output_by_key) == (
        PRIMARY_OUTPUT_CONTRACT[case.family]
    )
    assert execution.observation.policy_version == (
        DEFAULT_TOLERANCE_POLICY.policy_version
    )
    assert not execution.observation.metadata["missing_equation_roles"]


def test_direct_only_disagreement_fails_case_and_strict_suite():
    case = _suite().by_id["p49.incline.001"]
    execution = run_product_case(case)
    secondary = evaluate_secondary_analytic(
        case.family, case.canonical_inputs
    )
    baseline = case.expected_outputs[0].numeric
    tolerance = DEFAULT_TOLERANCE_POLICY.tolerance(
        "absolute",
        scale=max(abs(baseline), 1.0),
        engine_id=case.solver_id,
    )
    delta = tolerance * 0.75

    product_item = execution.observation.outputs[0]
    secondary_item = secondary.outputs[0]
    shifted_product_item = replace(
        product_item,
        numeric=baseline + delta,
        root_values=(baseline + delta,),
    )
    shifted_secondary_item = replace(
        secondary_item,
        numeric=baseline - delta,
        root_values=(baseline - delta,),
    )
    shifted_product = replace(
        execution.observation, outputs=(shifted_product_item,)
    )
    shifted_secondary = replace(
        secondary, outputs=(shifted_secondary_item,)
    )

    assert compare_oracle_observation(case, shifted_product).passed
    assert compare_oracle_observation(case, shifted_secondary).passed
    assert not compare_path_observations(
        case, shifted_product, shifted_secondary
    ).passed
    assert not compare_three_way(
        case, shifted_product, shifted_secondary
    ).passed

    evidence = _case_evidence_from_paths(
        case,
        replace(execution, observation=shifted_product),
        shifted_secondary,
    )
    assert not evidence["passed"]
    assert not evidence["leg_evidence"]["product_secondary"]["passed"]
    assert any(
        item["leg"] == "product_secondary"
        for item in evidence["disagreements"]
    )

    summary = {
        "oracle_cases": 60,
        "product_verified_total": 60,
        "product_verified_executed": 60,
        "product_verified_passed": 60,
        "oracle_product_total": 60,
        "oracle_product_executed": 60,
        "oracle_product_passed": 60,
        "oracle_secondary_total": 60,
        "oracle_secondary_executed": 60,
        "oracle_secondary_passed": 60,
        "product_secondary_total": 60,
        "product_secondary_executed": 60,
        "product_secondary_passed": 59,
        "three_way_total": 60,
        "three_way_executed": 60,
        "three_way_passed": 59,
        "distinct_metamorphic_relations": 21,
        "metamorphic_total": 21,
        "metamorphic_passed": 21,
        "mutation_controls": 4,
        "mutations_killed": 4,
    }
    assert not suite_verdict(summary, [])


def test_phase49_runner_is_offline_only_and_calls_all_four_comparisons():
    runner = Path(__file__).resolve().parents[1] / "tools" / (
        "run_phase49_consistency.py"
    )
    source = runner.read_text(encoding="utf-8")

    assert "def main(" in source
    assert "compare_oracle_observation(" in source
    assert "compare_path_observations(" in source
    assert "compare_three_way(" in source
    assert "product_verified" in source
    assert "student_answer_overwrite" in source
    assert "engine.equation_generators" not in source
