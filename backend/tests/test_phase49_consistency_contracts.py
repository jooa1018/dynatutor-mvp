from __future__ import annotations
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import pytest
from engine.capabilities.loader import (
    SOLVER_PATH_FAMILIES, SOLVER_PATH_ROLE_KEYS, CapabilityConfigError,
    load_capability_matrix,
)
from engine.models import Answer, AnswerItem, CanonicalProblem, SolverResult, VerificationReport
from engine.physics_core.validators import CandidateSolution, SelectionDecision
from engine.verification.consistency import (
    EQUATION_ROLE_CONTRACT, PRIMARY_OUTPUT_CONTRACT, ConsistencyContractError,
    ObservedSemanticOutput, SolverPathObservation,
    compare_oracle_observation, compare_path_observations, compare_three_way, evaluate_secondary_analytic, observation_from_solver_result,
)
from engine.verification.oracles import (
    INDEPENDENT_PROVENANCE, ORACLE_SCHEMA_VERSION, OracleCase,
    OracleContractError, load_oracle_suite,
)
from engine.verification.policy import DEFAULT_TOLERANCE_POLICY
from engine.verification.types import VerificationApplicability
ORACLE_FIXTURE = Path(__file__).parent / "benchmarks" / "phase49_dynamics_oracles_v1.json"
POLICY_VERSION = DEFAULT_TOLERANCE_POLICY.policy_version
SYMBOL_BY_OUTPUT = {"acceleration": "a", "v1_after": "v1'", "v2_after": "v2'",
                    "final_velocity": "vf", "angular_acceleration": "alpha"}
def _output(**overrides):
    raw = {
        "output_key": "acceleration", "numeric": 2.0, "unit": "m/s^2",
        "sign": "positive", "frame": "incline_tangent",
        "positive_direction": "down_slope",
        "assumptions": ["frictionless", "constant_gravity"],
        "root_count": 1, "root_values": [2.0], "multiplicity": [1],
        "ambiguity": False,
        "equation_ids": ["newton_second_law_tangent"],
    }
    raw.update(overrides)
    return raw
def _case(**overrides):
    raw = {
        "oracle_id": "p49.unit.incline.solved", "family": "incline",
        "problem": "A hand-derived incline contract case.",
        "canonical_inputs": {"gravity": 10.0, "angle_deg": 30.0,
                             "friction_mode": "frictionless"},
        "solver_id": "incline_no_friction",
        "expected_outputs": [_output()],
        "source": "Hand derivation from Newton's second law.",
        "derivation": "Resolve weight along the incline and divide by mass.",
        "independence_note": "Hand-derived expectation; not generated from current engine output.",
        "provenance_kind": INDEPENDENT_PROVENANCE,
        "expected_outcome": "solved", "expected_applicability": "applicable",
    }
    raw.update(overrides)
    return raw
def _suite(cases):
    return {
        "schema_version": ORACLE_SCHEMA_VERSION,
        "oracle_version": "phase49-oracle-v1", "benchmark_version": "phase49-benchmark-v1",
        "policy_version": POLICY_VERSION, "cases": cases,
    }
def _collision_checks():
    evidence = (
        ("collision_momentum:linear", "collision_momentum",
         "m1*v1+m2*v2=m1*v1_after+m2*v2_after"),
        ("collision_restitution:relative_velocity", "collision_restitution",
         "v2_after-v1_after=e*(v1-v2)"),
    )
    return [
        {
            "check_id": check_id,
            "category": category,
            "status": "passed", "applicability": "applicable",
            "source_equation_ids": [equation],
            "metadata": {"policy_version": POLICY_VERSION},
        }
        for check_id, category, equation in evidence
    ]
def _raw_equations(case: OracleCase):
    inputs = case.canonical_inputs
    if case.family == "incline":
        mode = inputs.get("friction_mode", "frictionless")
        if mode == "static":
            return ["mg sin theta <= mu_s mg cos theta -> a=0"]
        if mode == "kinetic":
            return ["N=mg cos theta", "f=mu N", "mg sin theta-f=ma"]
        return ["sum F_x=ma", "mg sin theta=ma", "a=g sin theta"]
    if case.family == "pulley":
        if "pulley_inertia" in inputs:
            return [
                "T1-m1g=m1a",
                "m2g-T2=m2a",
                "(T2-T1)R=I(a/R)",
            ]
        return ["m2g-T=m2a", "T-m1g=m1a"]
    if case.family == "rolling":
        return ["mgh=1/2mv^2+1/2I omega^2", "v=omega R", "I=beta mR^2"]
    if case.family == "work_energy":
        return ["W=delta K", "vf=sqrt(vi^2+2W/m)"]
    if case.family == "fixed_axis_rotation":
        return ["sum M=I alpha"]
    return []
def _actual_sources(case: OracleCase):
    answers = []
    numerical_mapping = {}
    symbolic_mapping = {}
    for output in case.expected_outputs:
        symbol = SYMBOL_BY_OUTPUT[output.output_key]
        answers.append(
            AnswerItem(
                label=output.output_key,
                symbol=symbol,
                numeric=output.numeric,
                unit=output.unit,
                display="deliberately unrelated display text",
                role="primary",
                output_key=output.output_key,
            )
        )
        numerical_mapping[output.output_key] = output.numeric
        numerical_mapping[symbol] = output.numeric
        symbolic_mapping[symbol] = output.numeric
    selected = CandidateSolution(
        candidate_id=f"{case.oracle_id}:selected",
        symbolic_mapping=symbolic_mapping,
        numerical_mapping=numerical_mapping,
        branch_info={"root_index": 0, "multiplicity": 1},
    )
    decision = SelectionDecision(
        status="selected",
        selected_candidate=selected,
        valid_alternatives=[],
        rejected_candidates=[],
        selection_policy="all-valid-candidates",
        policy_version=POLICY_VERSION,
        tolerances={
            "absolute": DEFAULT_TOLERANCE_POLICY.abs_tol,
            "relative": DEFAULT_TOLERANCE_POLICY.rel_tol,
            "residual": DEFAULT_TOLERANCE_POLICY.residual_tol,
        },
    )
    first = case.expected_outputs[0]
    verification = VerificationReport(
        passed=True,
        structured_checks=(
            _collision_checks() if case.family == "collision" else []
        ),
        policy_version=POLICY_VERSION,
    )
    result = SolverResult(
        ok=True,
        answer=Answer(
            symbolic=SYMBOL_BY_OUTPUT[first.output_key],
            numeric=first.numeric,
            unit=first.unit,
            display="not parsed",
            output_key=first.output_key,
        ),
        answers=answers,
        verification=verification,
        used_equations=_raw_equations(case),
        selection_decision=decision,
    )
    canonical = CanonicalProblem(
        system_type=case.family,
        assumptions=list(first.assumptions),
        coordinate_data={
            "coordinate_frame": first.frame,
            "positive_direction": first.positive_direction,
        },
    )
    return result, canonical
def _product_observation(case: OracleCase):
    result, canonical = _actual_sources(case)
    observed = observation_from_solver_result(
        result,
        canonical=canonical,
        family=case.family,
        path_id=f"student.{case.solver_id}",
        solver_id=case.solver_id,
        semantic_output_keys=PRIMARY_OUTPUT_CONTRACT[case.family],
    )
    return result, canonical, observed
@pytest.fixture(scope="module")
def actual_suite():
    return load_oracle_suite(
        ORACLE_FIXTURE,
        minimum_cases=60,
        minimum_per_family={family: 10 for family in PRIMARY_OUTPUT_CONTRACT},
    )
def test_actual_schema2_fixture_has_exact_immutable_coverage(actual_suite):
    counts = Counter(case.family for case in actual_suite.cases)
    assert actual_suite.oracle_version == "phase49-oracle-v1"
    assert actual_suite.benchmark_version == "phase49-benchmark-v1"
    assert actual_suite.policy_version == POLICY_VERSION
    assert len(actual_suite.cases) == 60
    assert counts == Counter({family: 10 for family in PRIMARY_OUTPUT_CONTRACT})
    assert sum(len(case.expected_outputs) for case in actual_suite.cases) == 70
    assert all(case.expected_outcome == "solved" for case in actual_suite.cases)
    assert all(case.expected_applicability == "applicable" for case in actual_suite.cases)
    assert all(
        output.root_values == (output.numeric,)
        for case in actual_suite.cases
        for output in case.expected_outputs
    )
    first = actual_suite.cases[0]
    with pytest.raises(TypeError):
        first.canonical_inputs["gravity"] = 1.0
    with pytest.raises(TypeError):
        actual_suite.by_id["replacement"] = first
    thawed = actual_suite.to_dict()
    thawed["cases"][0]["canonical_inputs"]["gravity"] = -999
    assert first.canonical_inputs["gravity"] != -999
def test_accepted_capability_matrix_has_exact_phase49_roles():
    matrix = load_capability_matrix()
    assert len(matrix.capabilities) == 29
    assert len(matrix.by_solver) == 29
    assert len(matrix.validator_ids) == 16
    assert set(matrix.solver_path_roles) == set(SOLVER_PATH_FAMILIES)
    assert sum(len(roles) for roles in matrix.solver_path_roles.values()) == 6 * 5
    for family, roles in matrix.solver_path_roles.items():
        assert set(roles) == set(SOLVER_PATH_ROLE_KEYS)
        assert roles["student_answer_path"]
        assert roles["secondary_analytic_path"] == f"phase49.secondary.{family}"
        assert roles["numeric_validation_path"] is None
        assert roles["external_validation_path"] is None
        assert roles["fallback_path"] is None
def test_roleless_legacy_capability_fixture_remains_compatible(tmp_path):
    raw = {
        "schema_version": 1,
        "source_commit": "legacy-test",
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
    path = tmp_path / "legacy-capabilities.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    matrix = load_capability_matrix(path)
    assert len(matrix.capabilities) == 1
    assert matrix.solver_path_roles == {}
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
def test_six_secondary_adapters_return_expected_typed_outputs(actual_suite, oracle_id):
    case = actual_suite.by_id[oracle_id]
    observed = evaluate_secondary_analytic(case.family, case.canonical_inputs)
    assert isinstance(observed, SolverPathObservation)
    assert observed.path_id == f"phase49.secondary.{case.family}"
    assert observed.solver_id == observed.path_id
    assert observed.policy_version == POLICY_VERSION
    assert observed.outcome == "solved"
    assert observed.applicability is VerificationApplicability.APPLICABLE
    assert tuple(observed.output_by_key) == PRIMARY_OUTPUT_CONTRACT[case.family]
    assert all(isinstance(output, ObservedSemanticOutput) for output in observed.outputs)
    assert all(output.equation_ids == EQUATION_ROLE_CONTRACT[case.family] for output in observed.outputs)
    assert observed.metadata["independent"] is True
    assert observed.metadata["offline_only"] is True
    assert compare_oracle_observation(case, observed).passed
def test_all_60_cases_pass_all_three_independent_legs(actual_suite):
    for case in actual_suite.cases:
        result, canonical, product = _product_observation(case)
        secondary = evaluate_secondary_analytic(case.family, case.canonical_inputs)
        oracle_product = compare_oracle_observation(case, product)
        oracle_secondary = compare_oracle_observation(case, secondary)
        product_secondary = compare_path_observations(case, product, secondary)
        three_way = compare_three_way(case, product, secondary)
        assert result.ok is True, case.oracle_id
        assert result.selection_decision.status == "selected", case.oracle_id
        assert result.selection_decision.selection_policy == "all-valid-candidates"
        assert result.selection_decision.policy_version == POLICY_VERSION
        assert product.outcome == "solved", case.oracle_id
        assert oracle_product.passed, case.oracle_id
        assert oracle_secondary.passed, case.oracle_id
        assert product_secondary.passed, case.oracle_id
        assert three_way.passed, case.oracle_id
        assert not three_way.disagreements, case.oracle_id
        json.loads(three_way.to_json())
        if case.family == "collision":
            assert product.metadata["equation_evidence_source"] == (
                "VerificationReport.structured_checks"
            )
        assert canonical.assumptions == list(case.expected_outputs[0].assumptions)
def test_solved_ambiguous_and_no_valid_solution_contracts_are_explicit():
    ambiguous_output = _output(
        numeric=1.0,
        root_count=2,
        root_values=[1.0, 3.0],
        multiplicity=[1, 1],
        ambiguity=True,
    )
    raw_cases = [
        _case(),
        _case(
            oracle_id="p49.unit.incline.ambiguous",
            canonical_inputs={"gravity": 10.0, "angle_deg": 31.0, "friction_mode": "frictionless"},
            expected_outputs=[ambiguous_output],
            expected_outcome="ambiguous",
        ),
        _case(
            oracle_id="p49.unit.incline.none",
            canonical_inputs={"gravity": 10.0, "angle_deg": 32.0, "friction_mode": "frictionless"},
            expected_outputs=[],
            expected_outcome="no_valid_solution",
            expected_applicability="not_applicable",
        ),
    ]
    suite = load_oracle_suite(_suite(raw_cases))
    solved_case, ambiguous_case, none_case = suite.cases
    solved_output = ObservedSemanticOutput(**solved_case.expected_outputs[0].to_dict())
    ambiguous = ObservedSemanticOutput(**ambiguous_case.expected_outputs[0].to_dict())
    solved = SolverPathObservation(
        path_id="student.incline_no_friction",
        family="incline",
        solver_id="incline_no_friction",
        outputs=(solved_output,),
        policy_version=POLICY_VERSION,
        outcome="solved",
    )
    ambiguous_observation = SolverPathObservation(
        path_id="student.incline_no_friction",
        family="incline",
        solver_id="incline_no_friction",
        outputs=(ambiguous,),
        policy_version=POLICY_VERSION,
        outcome="ambiguous",
    )
    no_valid = SolverPathObservation(
        path_id="student.incline_no_friction",
        family="incline",
        solver_id="incline_no_friction",
        outputs=(),
        policy_version=POLICY_VERSION,
        outcome="no_valid_solution",
        applicability=VerificationApplicability.NOT_APPLICABLE,
    )
    assert compare_oracle_observation(solved_case, solved).passed
    assert compare_oracle_observation(ambiguous_case, ambiguous_observation).passed
    assert compare_oracle_observation(none_case, no_valid).passed
    assert ambiguous_observation.outputs[0].root_values == (1.0, 3.0)
    assert no_valid.outputs == ()


def _unit_case():
    return load_oracle_suite(_suite([_case()])).cases[0]

def _observe_product(case, result, canonical):
    return observation_from_solver_result(
        result, canonical=canonical, family=case.family,
        path_id=f"student.{case.solver_id}",
        solver_id=case.solver_id, semantic_output_keys=PRIMARY_OUTPUT_CONTRACT[case.family],
    )

@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("cross_family_reuse", "must contain exactly"), ("missing_family", "must contain exactly"),
        ("duplicate_solver", "duplicate analytic_solver capability"),
        ("fallback", "fallback_path must be null"),
    ],
)
def test_capability_roles_reject_cross_family_reuse_omission_and_fallback(
    tmp_path, mutation, message
):
    matrix = load_capability_matrix()
    raw = json.loads(Path(matrix.source_path).read_text(encoding="utf-8"))
    roles = raw["solver_path_roles"]
    if mutation == "cross_family_reuse":
        roles["incline"]["student_answer_path"][0] = "pulley_atwood"
    elif mutation == "missing_family":
        roles.pop("incline")
    elif mutation == "duplicate_solver":
        raw["capabilities"].append(dict(raw["capabilities"][0]))
    else:
        roles["incline"]["fallback_path"] = "phase49.fallback.incline"
    path = tmp_path / f"{mutation}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CapabilityConfigError, match=message):
        load_capability_matrix(path)

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source", "Captured from current engine output.", "implementation output"),
        ("derivation", "Copied from the system under test.", "implementation output"),
        ("independence_note", "Independent derivation.", "explicitly attest"),
    ],
)
def test_oracle_provenance_rejects_product_derived_or_unattested_text(field, value, message):
    with pytest.raises(OracleContractError, match=message):
        load_oracle_suite(_suite([_case(**{field: value})]))

def test_oracle_provenance_accepts_explicit_negative_attestation():
    case = _case(
        independence_note="Expectations were not generated from current engine output."
    )
    suite = load_oracle_suite(_suite([case]))
    assert suite.cases[0].provenance_kind == INDEPENDENT_PROVENANCE

INVALID_ROOT_OUTPUTS = [
    ({"numeric": float("inf"), "root_values": [float("inf")]}, "finite"),
    ({"root_count": 2}, "root_values"),
    ({"root_values": [3.0]}, "numeric must identify"),
    ({"multiplicity": [1, 1]}, "multiplicity"),
    ({"root_count": 2, "root_values": [2.0, 2.0], "multiplicity": [1, 1]},
     "distinct roots"),
    ({"root_count": 2,
      "root_values": [2.0, 2.0 + DEFAULT_TOLERANCE_POLICY.root_separation_tol],
      "multiplicity": [1, 1]}, "distinct roots"),
]

@pytest.mark.parametrize(("overrides", "message"), INVALID_ROOT_OUTPUTS)
def test_oracle_roots_reject_nonfinite_mismatch_and_duplicate_values(overrides, message):
    with pytest.raises(OracleContractError, match=message):
        load_oracle_suite(_suite([_case(expected_outputs=[_output(**overrides)])]))

@pytest.mark.parametrize(("overrides", "message"), INVALID_ROOT_OUTPUTS)
def test_observed_roots_reject_nonfinite_mismatch_and_duplicate_values(overrides, message):
    with pytest.raises(ConsistencyContractError, match=message):
        ObservedSemanticOutput(**_output(**overrides))

def test_repeated_algebraic_root_is_one_value_with_multiplicity_two():
    raw = _output(multiplicity=[2])
    expected = load_oracle_suite(_suite([_case(expected_outputs=[raw])])).cases[0]
    observed = ObservedSemanticOutput(**raw)
    assert expected.expected_outputs[0].root_values == (2.0,)
    assert observed.root_count == 1
    assert observed.multiplicity == (2,)

def test_ambiguity_requires_at_least_two_distinct_roots_in_both_contracts():
    with pytest.raises(OracleContractError, match="complete multi-root"):
        case = _case(
            expected_outputs=[_output(ambiguity=True)], expected_outcome="ambiguous"
        )
        load_oracle_suite(_suite([case]))
    with pytest.raises(ConsistencyContractError, match="at least two roots"):
        ObservedSemanticOutput(**_output(ambiguity=True))

@pytest.mark.parametrize(
    ("cases", "message"),
    [
        ([_case(), _case()], "duplicate oracle_id"),
        ([_case(), _case(oracle_id="p49.unit.incline.same-signature")], "duplicate eligible case"),
    ],
)
def test_oracle_suite_rejects_duplicate_ids_and_eligible_signatures(cases, message):
    with pytest.raises(OracleContractError, match=message):
        load_oracle_suite(_suite(cases))

def test_product_observation_requires_selection_decision():
    case = _unit_case()
    result, canonical = _actual_sources(case)
    result.selection_decision = None
    with pytest.raises(ConsistencyContractError, match="selection_decision is required"):
        _observe_product(case, result, canonical)

@pytest.mark.parametrize("policy_version", [None, "", "not-the-central-policy"])
def test_product_observation_requires_explicit_central_decision_policy(policy_version):
    case = _unit_case()
    result, canonical = _actual_sources(case)
    result.selection_decision.policy_version = policy_version
    with pytest.raises(ConsistencyContractError, match="policy_version does not match"):
        _observe_product(case, result, canonical)

@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("selected_missing", "requires selected_candidate"),
        ("selected_value_mismatch", "disagrees with typed answer"),
        ("duplicate_id", "duplicate candidate_id"),
        ("incomplete", "lacks root value"),
    ],
)
def test_product_observation_rejects_invalid_selected_candidate_evidence(mutation, message):
    case = _unit_case()
    result, canonical = _actual_sources(case)
    decision = result.selection_decision
    selected = decision.selected_candidate
    if mutation == "selected_missing":
        decision.selected_candidate = None
    elif mutation == "selected_value_mismatch":
        selected.numerical_mapping.update({"acceleration": 3.0, "a": 3.0})
    elif mutation == "duplicate_id":
        decision.valid_alternatives = [selected]
    else:
        selected.numerical_mapping = {"unrelated": 2.0}
    with pytest.raises(ConsistencyContractError, match=message):
        _observe_product(case, result, canonical)

def test_unrelated_typed_numeric_coincidence_cannot_map_semantic_output():
    case = _unit_case()
    result, canonical = _actual_sources(case)
    result.answers = [AnswerItem(
        label="unrelated", symbol="x", numeric=2.0, unit="m/s^2",
        output_key="velocity",
    )]
    with pytest.raises(ConsistencyContractError, match="require typed outputs"):
        _observe_product(case, result, canonical)

@pytest.mark.parametrize("typed_source", ["explicit_key", "typed_symbol"])
def test_direct_semantic_key_and_typed_symbol_remain_accepted(typed_source):
    case = _unit_case()
    result, canonical = _actual_sources(case)
    if typed_source == "typed_symbol":
        result.answers = [
            AnswerItem(label="acceleration", symbol="a", numeric=2.0, unit="m/s^2")
        ]
        assert result.answers[0].output_key == "acceleration"
    assert compare_oracle_observation(case, _observe_product(case, result, canonical)).passed

def test_same_version_widened_tolerance_policy_is_rejected():
    case = _unit_case()
    _, _, observed = _product_observation(case)
    widened = replace(DEFAULT_TOLERANCE_POLICY,
                      abs_tol=DEFAULT_TOLERANCE_POLICY.abs_tol * 10)
    with pytest.raises(ConsistencyContractError, match="exactly match"):
        compare_oracle_observation(case, observed, policy=widened)

def test_wrong_outcome_and_undetermined_applicability_are_attributed():
    case = _unit_case()
    inconclusive = SolverPathObservation(
        path_id=f"student.{case.solver_id}", family=case.family,
        solver_id=case.solver_id, outputs=(), policy_version=POLICY_VERSION,
        outcome="no_valid_solution",
        applicability=VerificationApplicability.UNDETERMINED,
        message="independent path could not conclude",
    )
    report = compare_oracle_observation(case, inconclusive)
    categories = {item["category"] for item in report.disagreements}
    assert not report.passed
    assert {"outcome", "applicability"} <= categories

@pytest.mark.parametrize(
    ("field", "value", "category"),
    [
        ("unit", "kg", "unit_dimension"),
        ("frame", "laboratory", "coordinate_frame"),
        ("positive_direction", "up_slope", "positive_direction"),
        ("assumptions", ("frictionless",), "assumptions"),
        ("equation_ids", ("unrelated_equation",), "equation_ids"),
    ],
)
def test_semantic_metadata_mismatches_have_attributable_failed_checks(field, value, category):
    case = _unit_case()
    _, _, product = _product_observation(case)
    output = replace(product.outputs[0], **{field: value})
    report = compare_oracle_observation(case, replace(product, outputs=(output,)))
    assert not report.passed
    assert category in {item["category"] for item in report.disagreements}

@pytest.mark.parametrize(
    "mutation",
    [
        "report_policy", "check_policy", "applicability", "check_id",
        "category", "equation_signature", "incomplete", "duplicate",
    ],
)
def test_collision_requires_complete_unambiguous_phase48_equation_evidence(actual_suite, mutation):
    case = actual_suite.by_id["p49.collision.001"]
    result, canonical = _actual_sources(case)
    checks = result.verification.structured_checks
    if mutation == "report_policy":
        result.verification.policy_version = "wrong-policy"
    elif mutation == "check_policy":
        checks[0]["metadata"]["policy_version"] = "wrong-policy"
    elif mutation == "applicability":
        checks[0]["applicability"] = "not_applicable"
    elif mutation == "check_id":
        checks[0]["check_id"] = "fake:check"
    elif mutation == "category":
        checks[0]["category"] = "fake_category"
    elif mutation == "equation_signature":
        checks[0]["source_equation_ids"] = ["m1*v1=m2*v2"]
    elif mutation == "incomplete":
        checks.pop()
    else:
        checks.append({**checks[0], "metadata": dict(checks[0]["metadata"])})
    observed = _observe_product(case, result, canonical)
    report = compare_oracle_observation(case, observed)
    assert observed.metadata["equation_signature_valid"] is False
    assert observed.metadata["missing_equation_roles"]
    assert not report.passed
    assert "equation_ids" in {item["category"] for item in report.disagreements}

@pytest.mark.parametrize(
    ("mutation", "leg"),
    [
        ("oracle_product", "oracle_product"),
        ("oracle_secondary", "oracle_secondary"),
        ("product_secondary", "product_secondary"),
    ],
)
def test_three_way_mutations_fail_with_leg_specific_attribution(
    actual_suite, mutation, leg
):
    case = actual_suite.by_id["p49.incline.001"]
    _, _, product = _product_observation(case)
    secondary = evaluate_secondary_analytic(case.family, case.canonical_inputs)
    if mutation == "oracle_product":
        product = replace(product, policy_version="wrong-policy")
    elif mutation == "oracle_secondary":
        secondary = replace(secondary, policy_version="wrong-policy")
    else:
        product, secondary = secondary, product
    report = compare_three_way(case, product, secondary)
    assert not report.passed
    assert leg in {item["leg"] for item in report.disagreements}
    if mutation == "oracle_product":
        assert report.oracle_secondary_report.passed
        assert any(item["status"] == "error" for item in report.oracle_product_report.disagreements)
    elif mutation == "oracle_secondary":
        assert report.oracle_product_report.passed
    else:
        assert report.oracle_product_report.passed
        assert report.oracle_secondary_report.passed
        assert not report.product_secondary_report.passed

def test_three_way_undetermined_leg_cannot_pass():
    case = _unit_case()
    _, _, product = _product_observation(case)
    secondary = evaluate_secondary_analytic(case.family, case.canonical_inputs)
    inconclusive = replace(
        product,
        outputs=(),
        outcome="no_valid_solution",
        applicability=VerificationApplicability.UNDETERMINED,
        message="independent path inconclusive",
    )
    report = compare_three_way(case, inconclusive, secondary)
    assert not report.passed
    assert any(
        item["leg"] == "oracle_product" and item["category"] == "applicability"
        for item in report.disagreements
    )
