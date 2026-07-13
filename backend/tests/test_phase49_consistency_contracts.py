from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
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
    EQUATION_ROLE_CONTRACT,
    PRIMARY_OUTPUT_CONTRACT,
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
        "equation_ids": ["newton_second_law_tangent"],
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
                equation_ids=("newton_second_law_tangent",),
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
        used_equations=["ΣF_x = ma", "mg sinθ = ma"],
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
    assert observed.outputs[0].equation_ids == ("newton_second_law_tangent",)
    assert observed.metadata["raw_equation_evidence"] == ("ΣF_x = ma", "mg sinθ = ma")
    assert observed.metadata["equation_evidence_source"] == "SolverResult.used_equations"
    assert observed.outputs[0].assumptions == (
        "frictionless",
        "constant_gravity",
    )
    assert observed.metadata["source"] == "SolverResult.answers[].output_key"
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



@pytest.mark.parametrize(
    "family,solver_id,output_key,unit,frame,direction,equations,roles",
    [
        (
            "incline",
            "incline_no_friction",
            "acceleration",
            "m/s^2",
            "incline_tangent",
            "down_slope",
            ["ΣF_x = ma", "mg sinθ = ma"],
            ("newton_second_law_tangent",),
        ),
        (
            "work_energy",
            "work_energy_speed",
            "final_velocity",
            "m/s",
            "path_tangent",
            "direction_of_motion",
            ["W=ΔK"],
            ("work_energy_theorem",),
        ),
        (
            "fixed_axis_rotation",
            "fixed_axis_rotation",
            "angular_acceleration",
            "rad/s^2",
            "fixed_axis",
            "counterclockwise",
            ["ΣM=Iα"],
            ("fixed_axis_torque_balance",),
        ),
    ],
)
def test_actual_shaped_single_answer_results_use_typed_fallback(
    family, solver_id, output_key, unit, frame, direction, equations, roles
):
    result = SolverResult(
        ok=True,
        answer=Answer(
            numeric=2.5,
            unit=unit,
            display="malicious display = 999; must never be parsed",
        ),
        answers=[],
        used_equations=equations,
    )
    canonical = CanonicalProblem(
        assumptions=["actual solver assumption"],
        coordinate_data={
            "coordinate_frame": frame,
            "positive_direction": direction,
        },
    )

    observed = observation_from_solver_result(
        result,
        canonical=canonical,
        semantic_output_keys=[output_key],
        family=family,
        path_id=f"student.{solver_id}",
        solver_id=solver_id,
    )

    assert observed.output_by_key[output_key].numeric == 2.5
    assert observed.output_by_key[output_key].unit == unit
    assert observed.output_by_key[output_key].equation_ids == roles
    assert observed.metadata["source"] == "SolverResult.answer.numeric/unit"
    assert observed.metadata["legacy_single_output_fallback"] is True
    assert result.answer.display == "malicious display = 999; must never be parsed"
    assert result.answers == []


def test_single_answer_fallback_is_forbidden_for_multi_output_and_partial_paths():
    canonical = CanonicalProblem(
        assumptions=["one_dimensional_impact"],
        coordinate_data={
            "coordinate_frame": "one_dimensional_lab",
            "positive_direction": "right",
        },
    )
    representative = Answer(
        numeric=9.0,
        unit="m/s",
        display="v1=1, v2=8",
    )
    empty_multi = SolverResult(
        ok=True,
        answer=representative,
        answers=[],
        used_equations=["ACTUAL-COLLISION"],
    )
    empty_observation = observation_from_solver_result(
        empty_multi,
        canonical=canonical,
        semantic_output_keys=["v1_after", "v2_after"],
        family="collision",
        path_id="student.collision",
        solver_id="collision_1d",
    )
    partial_multi = SolverResult(
        ok=True,
        answer=representative,
        answers=[
            AnswerItem(
                "v1",
                "v1'",
                1.0,
                "m/s",
                "",
                output_key="v1_after",
            )
        ],
        used_equations=["ACTUAL-COLLISION"],
    )
    partial_observation = observation_from_solver_result(
        partial_multi,
        canonical=canonical,
        semantic_output_keys=["v1_after", "v2_after"],
        family="collision",
        path_id="student.collision",
        solver_id="collision_1d",
    )

    assert empty_observation.outputs == ()
    assert empty_observation.metadata["legacy_single_output_fallback"] is False
    assert empty_observation.metadata["fallback_rejected_reason"] == (
        "multiple_semantic_keys"
    )
    assert set(partial_observation.output_by_key) == {"v1_after"}
    assert partial_observation.metadata["legacy_single_output_fallback"] is False
    assert partial_observation.metadata["fallback_rejected_reason"] == (
        "typed_answer_items_present"
    )


def test_single_answer_fallback_never_parses_display_only_or_nonfinite_values():
    canonical = CanonicalProblem(
        assumptions=[],
        coordinate_data={
            "coordinate_frame": "path_tangent",
            "positive_direction": "direction_of_motion",
        },
    )
    display_only = SolverResult(
        ok=True,
        answer=Answer(
            numeric=None,
            unit="m/s",
            display="vf = 7 m/s",
        ),
        answers=[],
        used_equations=["W=ΔK"],
    )
    observed = observation_from_solver_result(
        display_only,
        canonical=canonical,
        semantic_output_keys=["final_velocity"],
        family="work_energy",
        path_id="student.work_energy",
        solver_id="work_energy_speed",
    )

    assert observed.outputs == ()
    assert observed.metadata["legacy_single_output_fallback"] is False
    assert observed.metadata["fallback_rejected_reason"] == (
        "representative_numeric_missing"
    )

    nonfinite = SolverResult(
        ok=True,
        answer=Answer(
            numeric=math.inf,
            unit="m/s",
            display="vf = finite-looking text",
        ),
        answers=[],
        used_equations=["W=ΔK"],
    )
    with pytest.raises(ConsistencyContractError, match="finite"):
        observation_from_solver_result(
            nonfinite,
            canonical=canonical,
            semantic_output_keys=["final_velocity"],
            family="work_energy",
            path_id="student.work_energy",
            solver_id="work_energy_speed",
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
    assert tuple(observation.output_by_key) == PRIMARY_OUTPUT_CONTRACT[family]
    assert required_key in observation.output_by_key
    assert all(
        output.equation_ids == EQUATION_ROLE_CONTRACT[family]
        for output in observation.outputs
    )
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

@pytest.mark.parametrize(
    "family,equations,outputs",
    [
        (
            "incline",
            ["ΣF_x = ma", "mg sinθ = ma"],
            [("acceleration", "m/s^2", 2.0)],
        ),
        (
            "pulley",
            ["T - m1g = m1a", "m2g - T = m2a"],
            [("acceleration", "m/s^2", 2.0)],
        ),
        (
            "collision",
            [
                "m1*v1+m2*v2=m1*v1_after+m2*v2_after",
                "v2_after-v1_after=e*(v1-v2)",
            ],
            [("v1_after", "m/s", 1.0), ("v2_after", "m/s", 2.0)],
        ),
        (
            "rolling",
            ["mgh = 1/2mv² + 1/2Iω²", "v=ωR", "I=βmR²"],
            [("final_velocity", "m/s", 2.0)],
        ),
        (
            "work_energy",
            ["W=ΔK", "v_f = √(v_i² + 2W/m)"],
            [("final_velocity", "m/s", 2.0)],
        ),
        (
            "fixed_axis_rotation",
            ["ΣM=Iα"],
            [("angular_acceleration", "rad/s^2", 2.0)],
        ),
    ],
)
def test_product_adapter_maps_all_six_raw_equation_shapes_to_semantic_roles(
    family, equations, outputs
):
    answers = [
        AnswerItem(key, key, numeric, unit, "never parsed", output_key=key)
        for key, unit, numeric in outputs
    ]
    result = SolverResult(ok=True, answers=answers, used_equations=equations)
    canonical = CanonicalProblem(
        assumptions=["actual"],
        coordinate_data={
            "coordinate_frame": "actual_frame",
            "positive_direction": "actual_direction",
        },
    )

    observed = observation_from_solver_result(
        result,
        canonical=canonical,
        family=family,
        path_id=f"student.{family}",
        solver_id=f"solver.{family}",
    )

    assert tuple(observed.output_by_key) == PRIMARY_OUTPUT_CONTRACT[family]
    assert all(
        output.equation_ids == EQUATION_ROLE_CONTRACT[family]
        for output in observed.outputs
    )
    assert observed.metadata["missing_equation_roles"] == ()
    assert observed.metadata["raw_equation_evidence"] == tuple(equations)


def test_collision_product_adapter_uses_actual_phase48_structured_fallback():
    answers = [
        AnswerItem("v1", "v1", 1.0, "m/s", "", output_key="v1_after"),
        AnswerItem("v2", "v2", 2.0, "m/s", "", output_key="v2_after"),
    ]
    source_ids = (
        "m1*v1+m2*v2=m1*v1_after+m2*v2_after",
        "v2_after-v1_after=e*(v1-v2)",
    )
    result = SimpleNamespace(
        answer=None,
        answers=answers,
        used_equations=[],
        verification=SimpleNamespace(
            structured_checks=[
                {
                    "category": "collision_momentum",
                    "status": "passed",
                    "source_equation_ids": [source_ids[0]],
                },
                {
                    "category": "collision_restitution",
                    "status": "passed_with_warning",
                    "source_equation_ids": [source_ids[1]],
                },
            ]
        ),
    )
    canonical = CanonicalProblem(
        assumptions=["one_dimensional_impact"],
        coordinate_data={
            "coordinate_frame": "one_dimensional_lab",
            "positive_direction": "right",
        },
    )

    observed = observation_from_solver_result(
        result,
        canonical=canonical,
        family="collision",
        path_id="student.collision",
        solver_id="collision_1d",
    )

    assert all(
        output.equation_ids == EQUATION_ROLE_CONTRACT["collision"]
        for output in observed.outputs
    )
    assert observed.metadata["equation_evidence_source"] == (
        "VerificationReport.structured_checks"
    )
    assert observed.metadata["structured_equation_evidence"] == source_ids


def test_mutated_or_missing_equation_evidence_fails_closed():
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
        used_equations=["a = fixture-shaped-number"],
    )
    canonical = CanonicalProblem(
        assumptions=["frictionless", "constant_gravity"],
        coordinate_data={
            "coordinate_frame": "incline_tangent",
            "positive_direction": "down_slope",
        },
    )
    observed = observation_from_solver_result(
        result,
        canonical=canonical,
        family="incline",
        path_id="student.incline",
        solver_id="incline_no_friction",
    )
    report = compare_oracle_observation(_oracle(), observed)

    assert observed.outputs[0].equation_ids == ()
    assert observed.metadata["missing_equation_roles"] == (
        "newton_second_law_tangent",
    )
    assert not report.passed
    assert "equation_ids" in _failed_categories(report)


@pytest.mark.parametrize(
    "family,requested",
    [
        ("incline", ["final_velocity"]),
        ("collision", ["v1_after"]),
    ],
)
def test_product_adapter_rejects_fixture_specific_primary_output_subset(
    family, requested
):
    result = SolverResult(ok=True, answers=[], used_equations=[])
    canonical = CanonicalProblem(
        assumptions=[],
        coordinate_data={
            "coordinate_frame": "frame",
            "positive_direction": "direction",
        },
    )
    with pytest.raises(ConsistencyContractError, match="central primary-output"):
        observation_from_solver_result(
            result,
            canonical=canonical,
            family=family,
            semantic_output_keys=requested,
            path_id=f"student.{family}",
            solver_id=family,
        )


@pytest.mark.parametrize(
    "expected_unit,observed_unit,passes",
    [
        ("m/s^2", "m/s²", True),
        ("rad/s^2", "rad/s²", True),
        ("m/s^2", "m/s", False),
        ("N", "kg", False),
    ],
)
def test_unit_comparison_normalizes_spelling_only(
    expected_unit, observed_unit, passes
):
    oracle = load_oracle_suite(
        _suite(
            [
                _case(
                    expected_outputs=[
                        _output(unit=expected_unit)
                    ]
                )
            ]
        )
    ).cases[0]
    output = replace(_observation().outputs[0], unit=observed_unit)
    report = compare_oracle_observation(oracle, _observation(output=(output,)))

    assert report.passed is passes
    if not passes:
        assert "unit_dimension" in _failed_categories(report)


def test_assumption_order_is_part_of_exact_semantic_contract():
    output = replace(
        _observation().outputs[0],
        assumptions=("constant_gravity", "frictionless"),
    )
    report = compare_oracle_observation(_oracle(), _observation(output=(output,)))

    assert not report.passed
    assert "assumptions" in _failed_categories(report)


def test_secondary_outputs_never_promote_analytic_extras_to_primary_answers():
    pulley = evaluate_secondary_analytic(
        "pulley",
        {
            "m1": 2.0,
            "m2": 5.0,
            "gravity": 9.81,
            "pulley_inertia": 0.2,
            "pulley_radius": 0.4,
        },
    )
    rolling = evaluate_secondary_analytic(
        "rolling",
        {
            "height": 2.0,
            "gravity": 9.81,
            "inertia_factor": 0.4,
            "radius": 0.5,
        },
    )
    fixed = evaluate_secondary_analytic(
        "fixed_axis_rotation",
        {
            "torque": 6.0,
            "inertia": 2.0,
            "initial_angular_velocity": 1.0,
            "time": 2.0,
            "radius": 0.5,
        },
    )

    assert tuple(pulley.output_by_key) == ("acceleration",)
    assert set(pulley.metadata["analytic_extras"]) == {
        "tension_1",
        "tension_2",
        "angular_acceleration",
    }
    assert tuple(rolling.output_by_key) == ("final_velocity",)
    assert set(rolling.metadata["analytic_extras"]) == {"angular_velocity"}
    assert tuple(fixed.output_by_key) == ("angular_acceleration",)
    assert set(fixed.metadata["analytic_extras"]) == {
        "angular_velocity",
        "tangential_velocity",
    }

