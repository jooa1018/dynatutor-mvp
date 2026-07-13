from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from engine.verification.consistency import PRIMARY_OUTPUT_CONTRACT
from engine.verification.oracles import load_oracle_suite
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY
from tools.run_phase49_consistency import (
    DEFAULT_METAMORPHIC_PATH,
    DEFAULT_ORACLE_PATH,
    load_metamorphic_fixture,
    run_product_case,
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


def test_phase49_oracle_fixture_has_exact_independent_coverage():
    suite = _suite()
    counts = Counter(case.family for case in suite.cases)

    assert len(suite.cases) == 60
    assert counts == Counter(
        {family: 10 for family in PRIMARY_OUTPUT_CONTRACT}
    )
    assert sum(len(case.expected_outputs) for case in suite.cases) == 70
    assert suite.policy_version == (
        DEFAULT_TOLERANCE_POLICY.policy_version
    )
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
    assert all(
        output.root_values == (output.numeric,)
        and output.root_count == 1
        and output.multiplicity == (1,)
        for case in suite.cases
        for output in case.expected_outputs
    )


def test_phase49_metamorphic_fixture_has_exact_relation_and_mutation_coverage():
    raw = load_metamorphic_fixture(DEFAULT_METAMORPHIC_PATH)

    assert len(raw["relations"]) == 21
    assert len({item["relation_id"] for item in raw["relations"]}) == 21
    assert len({item["relation_kind"] for item in raw["relations"]}) == 21
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
    assert tuple(execution.observation.output_by_key) == (
        PRIMARY_OUTPUT_CONTRACT[case.family]
    )
    assert execution.observation.policy_version == (
        DEFAULT_TOLERANCE_POLICY.policy_version
    )
    assert not execution.observation.metadata["missing_equation_roles"]
    assert execution.observation.metadata["answer_source"] in {
        "SolverResult.answer.numeric/unit",
        "SolverResult.answers[].output_key",
    }


def test_phase49_runner_is_offline_only_and_not_in_engine_import_graph():
    runner = Path(__file__).resolve().parents[1] / "tools" / (
        "run_phase49_consistency.py"
    )
    source = runner.read_text(encoding="utf-8")
    assert "def main(" in source
    assert "student_answer_overwrite" in source
    assert "engine.equation_generators" not in source
