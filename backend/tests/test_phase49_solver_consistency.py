from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from engine.models import Answer, SolverResult
from engine.physics_core.validators import (
    CandidateSolution,
    CandidateSolveBatch,
    SelectionDecision,
    candidate_from_solver_result,
)
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
    SEMANTIC_SELECTION_EVIDENCE_SOURCE,
    Phase49RunError,
    _case_evidence_from_paths,
    _selection_noncontradiction_checks,
    _solve_validated,
    build_product_canonical,
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


def test_incline_output_validation_is_the_semantic_selection_evidence():
    case = _suite().by_id["p49.incline.001"]
    execution = run_product_case(case)

    generator = execution.solver_selection_evidence
    assert generator is not None
    assert execution.solver_selection_status == "selected"
    assert execution.output_selection_status == "selected"
    assert generator["status"] == "selected"
    assert "a" in generator["selected_candidate_mapping_keys"]
    assert "acceleration" not in generator["selected_candidate_mapping_keys"]
    assert len(generator["semantic_value_checks"]) == 1
    value_check = generator["semantic_value_checks"][0]
    assert value_check["output_key"] == "acceleration"
    assert value_check["solver_symbols"] == ["a"]
    assert value_check["status"] == "matched"
    assert value_check["tolerance"] == pytest.approx(
        DEFAULT_TOLERANCE_POLICY.tolerance(
            "absolute",
            scale=max(abs(execution.result.answer.numeric), 1.0),
        )
    )

    semantic = execution.result.selection_decision.selected_candidate
    assert semantic is not None
    assert semantic.numerical_mapping["acceleration"] == pytest.approx(
        execution.result.answer.numeric
    )
    assert execution.observation.outputs[0].root_values == pytest.approx(
        (execution.result.answer.numeric,)
    )
    assert execution.semantic_selection_evidence_source == (
        SEMANTIC_SELECTION_EVIDENCE_SOURCE
    )
    assert execution.observation.metadata[
        "semantic_selection_evidence_source"
    ] == SEMANTIC_SELECTION_EVIDENCE_SOURCE


class _ContradictingSelectionSolver:
    name = "phase49-contradiction-test"
    uses_prebuilt_physical_model = False

    def __init__(self, result):
        self.result = result

    def solve_candidates(self, canonical):
        return CandidateSolveBatch(
            result=self.result,
            candidates=[
                candidate_from_solver_result(
                    self.result,
                    candidate_id="output-candidate-0",
                    requested_outputs=canonical.requested_outputs,
                )
            ],
        )


def test_singleton_numeric_coincidence_is_not_semantic_alias_evidence():
    value = 4.905
    original = SelectionDecision(
        status="selected",
        selected_candidate=CandidateSolution(
            candidate_id="generator-candidate-0",
            symbolic_mapping={"unrelated": value},
            numerical_mapping={"unrelated": value},
        ),
    )
    output = SelectionDecision(
        status="selected",
        selected_candidate=CandidateSolution(
            candidate_id="output-candidate-0",
            symbolic_mapping={"acceleration": value},
            numerical_mapping={"acceleration": value},
        ),
    )

    assert _selection_noncontradiction_checks(
        original,
        output,
        ["acceleration"],
    ) == [
        {
            "output_key": "acceleration",
            "solver_symbols": [],
            "status": "not_comparable_without_explicit_alias",
            "tolerance": None,
        }
    ]


@pytest.mark.parametrize(
    (
        "solver_status",
        "answer_output_key",
        "generator_delta",
        "message",
    ),
    [
        (
            "ambiguous",
            "acceleration",
            0.0,
            "lower-level selection status",
        ),
        ("selected", "velocity", 0.0, "output validation status"),
        (
            "selected",
            "acceleration",
            1.0,
            "contradicts output validation",
        ),
    ],
)
def test_solver_and_output_selection_must_not_contradict(
    solver_status,
    answer_output_key,
    generator_delta,
    message,
):
    case = _suite().by_id["p49.incline.001"]
    canonical = build_product_canonical(case)
    value = float(case.expected_outputs[0].numeric)
    generator_candidate = CandidateSolution(
        candidate_id="generator-candidate-0",
        symbolic_mapping={"a": value + generator_delta},
        numerical_mapping={"a": value + generator_delta},
    )
    original = SelectionDecision(
        status=solver_status,
        selected_candidate=(
            generator_candidate if solver_status == "selected" else None
        ),
        valid_alternatives=(
            [generator_candidate] if solver_status == "ambiguous" else []
        ),
        selection_policy="generator-explicit-constraints",
    )
    result = SolverResult(
        ok=True,
        answer=Answer(
            numeric=value,
            unit="m/s²",
            output_key=answer_output_key,
        ),
        selection_decision=original,
    )

    with pytest.raises(Phase49RunError, match=message):
        _solve_validated(canonical, _ContradictingSelectionSolver(result))
    assert result.selection_decision is original


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
