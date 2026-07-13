from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import inspect
import json
import math

import pytest

from engine.capabilities.loader import (
    DEFAULT_CAPABILITY_PATH,
    SOLVER_PATH_FAMILIES,
    SOLVER_PATH_ROLE_KEYS,
    CapabilityConfigError,
    load_capability_matrix,
    validate_capability_validator_ids,
)
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult
from engine.verification import consistency as consistency_module
from engine.verification import oracles as oracles_module
from engine.verification.consistency import (
    ConsistencyContractError,
    ObservedSemanticOutput,
    SolverPathObservation,
    compare_oracle_observation,
    evaluate_secondary_analytic,
    observation_from_solver_result,
)
from engine.verification.oracles import (
    INDEPENDENT_PROVENANCE,
    OracleContractError,
    load_oracle_suite,
)
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY
from engine.verification.types import VerificationApplicability


def _output(**overrides):
    raw = {
        "output_key": "acceleration",
        "numeric": 2.0,
        "unit": "m/s^2",
        "sign": "positive",
        "frame": "incline_tangent",
        "positive_direction": "down_slope",
        "assumptions": ["frictionless", "constant_gravity"],
        "root_count": 1,
        "multiplicity": [1],
        "ambiguity": False,
        "equation_ids": ["P49-INCLINE-FREE:a=g*sin(theta)"],
    }
    raw.update(overrides)
    return raw


def _case(**overrides):
    raw = {
        "oracle_id": "incline-independent-001",
        "family": "incline",
        "problem": "A frictionless block accelerates down an incline.",
        "canonical_inputs": {
            "gravity": 10.0,
            "angle_deg": 30.0,
            "friction_mode": "frictionless",
        },
        "solver_id": "incline_no_friction",
        "expected_outputs": [_output()],
        "source": "hand derivation from Newton's second law",
        "derivation": "resolve weight parallel to the plane and divide by mass",
        "independence_note": "not generated from current engine output",
        "provenance_kind": INDEPENDENT_PROVENANCE,
    }
    raw.update(overrides)
    return raw


def _suite(cases=None, **overrides):
    raw = {
        "schema_version": 1,
        "oracle_version": "phase49-oracle-v1",
        "benchmark_version": "phase49-benchmark-v1",
        "policy_version": DEFAULT_TOLERANCE_POLICY.policy_version,
        "cases": cases if cases is not None else [_case()],
    }
    raw.update(overrides)
    return raw


def _oracle():
    return load_oracle_suite(_suite()).cases[0]


def _observation(output=None, **overrides):
    semantic_outputs = output
    if semantic_outputs is None:
        semantic_outputs = (
            ObservedSemanticOutput(
                output_key="acceleration",
                numeric=2.0,
                unit="m/s^2",
                sign="positive",
                frame="incline_tangent",
                positive_direction="down_slope",
                assumptions=("frictionless", "constant_gravity"),
                root_count=1,
                multiplicity=(1,),
                ambiguity=False,
                equation_ids=("P49-INCLINE-FREE:a=g*sin(theta)",),
            ),
        )
    raw = {
        "path_id": "student.incline_no_friction",
        "family": "incline",
        "solver_id": "incline_no_friction",
        "outputs": tuple(semantic_outputs),
        "policy_version": DEFAULT_TOLERANCE_POLICY.policy_version,
    }
    raw.update(overrides)
    return SolverPathObservation(**raw)


def _failed_categories(report):
    return {
        check["category"]
        for check in report.verification_report.structured_checks
        if check["status"] in {"failed", "error", "inconclusive", "not_applicable"}
    }


def test_oracle_suite_records_versions_and_is_deeply_immutable():
    suite = load_oracle_suite(
        _suite(),
        minimum_cases=1,
        minimum_per_family={"incline": 1},
        eligible_families=["incline"],
    )
    case = suite.cases[0]

    assert suite.oracle_version == "phase49-oracle-v1"
    assert case.benchmark_version == "phase49-benchmark-v1"
    assert case.policy_version == DEFAULT_TOLERANCE_POLICY.policy_version
    assert suite.by_id[case.oracle_id] is case
    with pytest.raises(TypeError):
        case.canonical_inputs["gravity"] = 1.0
    with pytest.raises(TypeError):
        suite.by_id["new"] = case


def test_oracle_independence_note_negation_is_not_a_false_positive():
    suite = load_oracle_suite(_suite())
    assert suite.cases[0].independence_note == "not generated from current engine output"


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda raw: raw.update(policy_version="wrong"), "central policy"),
        (
            lambda raw: raw["cases"][0].update(
                source="generated from engine output during baseline capture"
            ),
            "implementation output",
        ),
        (
            lambda raw: raw["cases"][0].update(provenance_kind="engine_snapshot"),
            "provenance_kind",
        ),
        (
            lambda raw: raw["cases"][0]["expected_outputs"][0].update(
                numeric=float("nan")
            ),
            "finite",
        ),
        (
            lambda raw: raw["cases"][0]["expected_outputs"][0].update(
                multiplicity=[1, 1]
            ),
            "multiplicity",
        ),
    ],
)
def test_oracle_schema_fails_closed(mutation, match):
    raw = _suite()
    mutation(raw)
    with pytest.raises(OracleContractError, match=match):
        load_oracle_suite(raw)


def test_oracle_loader_rejects_duplicate_signature_and_insufficient_minimum():
    first = _case()
    duplicate = deepcopy(first)
    duplicate["oracle_id"] = "incline-independent-002"
    with pytest.raises(OracleContractError, match="duplicate eligible"):
        load_oracle_suite(_suite([first, duplicate]))
    with pytest.raises(OracleContractError, match="below required"):
        load_oracle_suite(_suite(), minimum_cases=2)


def test_default_capability_roles_are_complete_versioned_and_immutable():
    matrix = load_capability_matrix()

    assert set(matrix.solver_path_roles) == set(SOLVER_PATH_FAMILIES)
    solver_ids = set(matrix.by_solver)
    for family, roles in matrix.solver_path_roles.items():
        assert set(roles) == set(SOLVER_PATH_ROLE_KEYS)
        assert roles["student_answer_path"]
        assert set(roles["student_answer_path"]) <= solver_ids
        assert roles["secondary_analytic_path"] == f"phase49.secondary.{family}"
        assert roles["numeric_validation_path"] is None
        assert roles["external_validation_path"] is None
    with pytest.raises(TypeError):
        matrix.solver_path_roles["incline"]["fallback_path"] = "collision_1d"


def test_capability_role_validation_rejects_unknown_roles_and_solver_ids():
    raw = json.loads(DEFAULT_CAPABILITY_PATH.read_text(encoding="utf-8"))
    unknown_role = deepcopy(raw)
    unknown_role["solver_path_roles"]["incline"]["typo_role"] = None
    with pytest.raises(CapabilityConfigError, match="contain exactly"):
        validate_capability_validator_ids(unknown_role)

    unknown_solver = deepcopy(raw)
    unknown_solver["solver_path_roles"]["incline"]["student_answer_path"] = [
        "not_a_solver"
    ]
    with pytest.raises(CapabilityConfigError, match="unknown solver IDs"):
        validate_capability_validator_ids(unknown_solver)


def test_legacy_minimal_capability_fixture_remains_compatible(tmp_path):
    raw = {
        "schema_version": 1,
        "source_commit": "test",
        "capabilities": [
            {
                "system_type": "example",
                "subtypes": [],
                "required_inputs": {"all_of": [], "any_of": [], "conditional": []},
                "requested_outputs": ["acceleration"],
                "analytic_solver": "example",
                "validators": ["dimension"],
            }
        ],
    }
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert load_capability_matrix(path).solver_path_roles == {}


def test_successful_comparison_wraps_structured_verification_report():
    report = compare_oracle_observation(_oracle(), _observation())

    assert report.passed
    assert report.policy_version == DEFAULT_TOLERANCE_POLICY.policy_version
    assert report.oracle_version == "phase49-oracle-v1"
    assert report.benchmark_version == "phase49-benchmark-v1"
    assert report.verification_report.policy_version == report.policy_version
    assert {
        "numeric",
        "unit_dimension",
        "sign",
        "coordinate_frame",
        "positive_direction",
        "assumptions",
        "root_structure",
        "ambiguity",
        "equation_ids",
        "semantic_outputs",
    } <= {
        item["category"] for item in report.verification_report.structured_checks
    }
    json.loads(report.to_json())


@pytest.mark.parametrize(
    "category,change",
    [
        ("numeric", {"numeric": 3.0}),
        ("unit_dimension", {"unit": "kg"}),
        ("sign", {"sign": "negative"}),
        ("coordinate_frame", {"frame": "world"}),
        ("positive_direction", {"positive_direction": "up_slope"}),
        ("assumptions", {"assumptions": ("other",)}),
        ("root_structure", {"root_count": 2, "multiplicity": (1, 1)}),
        ("ambiguity", {"ambiguity": True}),
        ("equation_ids", {"equation_ids": ("P49-WRONG",)}),
    ],
)
def test_each_comparison_category_detects_deliberate_disagreement(category, change):
    output = replace(_observation().outputs[0], **change)
    report = compare_oracle_observation(_oracle(), _observation(output=(output,)))

    assert not report.passed
    assert category in _failed_categories(report)


def test_missing_and_extra_semantic_outputs_fail():
    replacement = replace(
        _observation().outputs[0],
        output_key="unexpected_output",
    )
    report = compare_oracle_observation(_oracle(), _observation(output=(replacement,)))

    assert not report.passed
    assert "semantic_outputs" in _failed_categories(report)


def test_inconclusive_or_not_applicable_never_counts_as_pass():
    report = compare_oracle_observation(
        _oracle(),
        _observation(
            outputs=(),
            applicability=VerificationApplicability.UNDETERMINED,
            message="missing typed outputs",
        ),
    )

    assert not report.passed
    assert "applicability" in _failed_categories(report)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_observation_fails_closed(value):
    with pytest.raises(ConsistencyContractError, match="finite"):
        replace(_observation().outputs[0], numeric=value)


def test_typed_result_adapter_uses_actual_sources_and_does_not_mutate_source():
    item = AnswerItem(
        "acceleration",
        "a",
        2.0,
        "m/s^2",
        "display text is not parsed",
        output_key="acceleration",
    )
    unrelated = AnswerItem(
        "legacy compatibility",
        None,
        999.0,
        "kg",
        "unrelated",
        output_key=None,
    )
    result = SolverResult(
        ok=True,
        answer=Answer(numeric=999.0, unit="m/s^2", display="wrong representative"),
        answers=[item, unrelated],
        used_equations=["PROD-INCLINE-EQUATION"],
    )
    canonical = CanonicalProblem(
        system_type="particle_on_incline",
        assumptions=["frictionless", "constant_gravity"],
        coordinate_data={
            "coordinate_frame": "incline_tangent",
            "positive_direction": "down_slope",
        },
    )
    before = (
        result.answer.numeric,
        tuple(result.answers),
        tuple(result.used_equations),
        tuple(canonical.assumptions),
        deepcopy(canonical.coordinate_data),
        item.display,
        item.output_key,
    )
    observed = observation_from_solver_result(
        result,
        canonical=canonical,
        semantic_output_keys=["acceleration"],
        family="incline",
        path_id="student.incline_no_friction",
        solver_id="incline_no_friction",
    )

    assert observed.outputs[0].numeric == 2.0
    assert observed.outputs[0].equation_ids == ("PROD-INCLINE-EQUATION",)
    assert observed.outputs[0].assumptions == (
        "frictionless",
        "constant_gravity",
    )
    assert observed.metadata["source"] == "actual_product_evidence"
    assert observed.metadata["ignored_output_keys"] == ("<untyped>",)
    assert before == (
        result.answer.numeric,
        tuple(result.answers),
        tuple(result.used_equations),
        tuple(canonical.assumptions),
        canonical.coordinate_data,
        item.display,
        item.output_key,
    )


def test_product_adapter_rejects_expected_metadata_echo():
    result = SolverResult(
        ok=True,
        answers=[
            AnswerItem(
                "acceleration",
                "a",
                2.0,
                "m/s^2",
                "",
                output_key="acceleration",
            )
        ],
        used_equations=["ACTUAL-EQUATION"],
    )
    canonical = CanonicalProblem(
        assumptions=["actual assumption"],
        coordinate_data={
            "coordinate_frame": "actual_frame",
            "positive_direction": "actual_direction",
        },
    )

    with pytest.raises(ConsistencyContractError, match="caller overrides"):
        observation_from_solver_result(
            result,
            canonical=canonical,
            semantic_output_keys=["acceleration"],
            family="incline",
            path_id="student.incline",
            solver_id="incline_no_friction",
            equation_ids=["ORACLE-EQUATION"],
            assumptions=["oracle assumption"],
            frame="oracle_frame",
            positive_direction="oracle_direction",
        )


def test_typed_result_adapter_filters_unrelated_items_and_preserves_missing_keys():
    result = SolverResult(
        ok=True,
        answers=[
            AnswerItem("legacy", None, 3.0, "kg", "", output_key=None),
            AnswerItem("other", "x", 1.0, "m", "", output_key="distance"),
        ],
        used_equations=[],
    )
    canonical = CanonicalProblem(
        assumptions=[],
        coordinate_data={
            "coordinate_frame": "incline_tangent",
            "positive_direction": "down_slope",
        },
    )
    observed = observation_from_solver_result(
        result,
        canonical=canonical,
        semantic_output_keys=["acceleration"],
        family="incline",
        path_id="student.incline",
        solver_id="incline_no_friction",
    )
    report = compare_oracle_observation(_oracle(), observed)

    assert observed.outputs == ()
    assert observed.metadata["ignored_output_keys"] == ("<untyped>", "distance")
    assert not report.passed
    assert "semantic_outputs" in _failed_categories(report)


def test_typed_result_adapter_rejects_duplicate_selected_semantic_keys():
    duplicate = SolverResult(
        ok=True,
        answers=[
            AnswerItem("a", "a", 1.0, "m/s^2", "", output_key="acceleration"),
            AnswerItem("a2", "a", 2.0, "m/s^2", "", output_key="acceleration"),
        ],
        used_equations=["ACTUAL"],
    )
    canonical = CanonicalProblem(
        assumptions=[],
        coordinate_data={
            "coordinate_frame": "incline_tangent",
            "positive_direction": "down_slope",
        },
    )
    with pytest.raises(ConsistencyContractError, match="duplicate"):
        observation_from_solver_result(
            duplicate,
            canonical=canonical,
            semantic_output_keys=["acceleration"],
            family="incline",
            path_id="student.incline",
            solver_id="incline_no_friction",
        )


@pytest.mark.parametrize(
    "family,inputs,required_key",
    [
        (
            "incline",
            {"gravity": 9.81, "angle_deg": 30.0, "friction_mode": "frictionless"},
            "acceleration",
        ),
        (
            "pulley",
            {"m1": 2.0, "m2": 5.0, "gravity": 9.81},
            "acceleration",
        ),
        (
            "collision",
            {
                "m1": 1.0,
                "m2": 2.0,
                "v1_before": 3.0,
                "v2_before": 0.0,
                "restitution": 0.5,
            },
            "v1_after",
        ),
        (
            "rolling",
            {"height": 2.0, "gravity": 9.81, "inertia_factor": 0.4},
            "final_velocity",
        ),
        (
            "work_energy",
            {"mass": 2.0, "initial_velocity": 1.0, "net_work": 8.0},
            "final_velocity",
        ),
        (
            "fixed_axis_rotation",
            {
                "torque": 6.0,
                "inertia": 2.0,
                "initial_angular_velocity": 1.0,
                "time": 2.0,
            },
            "angular_acceleration",
        ),
    ],
)
def test_six_independent_secondary_adapters_are_typed_and_versioned(
    family, inputs, required_key
):
    observation = evaluate_secondary_analytic(family, inputs)

    assert observation.applicability is VerificationApplicability.APPLICABLE
    assert observation.path_id == f"phase49.secondary.{family}"
    assert observation.policy_version == DEFAULT_TOLERANCE_POLICY.policy_version
    assert required_key in observation.output_by_key
    assert observation.metadata["independent"] is True
    assert observation.metadata["offline_only"] is True


def test_secondary_applicability_and_input_errors_are_explicit():
    static_failure = evaluate_secondary_analytic(
        "incline",
        {
            "gravity": 9.81,
            "angle_deg": 45.0,
            "friction_mode": "static",
            "mu_s": 0.1,
        },
    )
    malformed = evaluate_secondary_analytic(
        "pulley",
        {"m1": 1.0, "m2": 2.0, "gravity": 9.81, "pulley_inertia": 0.1},
    )

    assert static_failure.applicability is VerificationApplicability.NOT_APPLICABLE
    assert not static_failure.outputs
    assert malformed.applicability is VerificationApplicability.UNDETERMINED
    assert "requires inertia and radius" in malformed.message


def test_independent_modules_have_no_production_solver_result_dependencies():
    oracle_source = inspect.getsource(oracles_module)
    consistency_source = inspect.getsource(consistency_module)
    forbidden = (
        "engine.solvers",
        "engine.equation_generators",
        "engine.services",
        "candidate_selection",
    )

    assert all(name not in oracle_source for name in forbidden)
    assert all(name not in consistency_source for name in forbidden)
    assert "DEFAULT_TOLERANCE_POLICY" in oracle_source
    assert "DEFAULT_TOLERANCE_POLICY" in consistency_source
