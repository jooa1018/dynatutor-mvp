from __future__ import annotations

import json
import math
from dataclasses import fields
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.problem import ProblemRequest
from app.schemas.solution import (
    AnswerItemModel,
    AnswerModel,
    CanonicalProblemModel,
    ClarificationModel,
    ClarificationOptionModel,
    DiagnosisResponse,
    ExplanationAnswerDerivationModel,
    ExplanationCandidateSummaryModel,
    ExplanationCoordinateFrameModel,
    ExplanationEquationModel,
    ExplanationFactModel,
    ExplanationStudentStepModel,
    ExplanationSubstitutionModel,
    ExplanationTraceModel,
    ExplanationValidationSummaryModel,
    SolveResponse,
    VerificationReport as VerificationReportModel,
)
from engine.extraction.extractor import extract_problem
from engine.models import (
    CalculationCoordinateFrame,
    CanonicalProblem,
    EquationEvidence,
    OutputEvidenceLink,
    SemanticFactEvidence,
    SolverExplanationEvidence,
    SolverResult,
    SubstitutionEvidence,
    VerificationReport,
)
from engine.solvers.registry import SolverRegistry
from engine.services import solve_problem
from engine.verification.residuals import CHECKERS


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_PATH = BACKEND_ROOT / "engine" / "capabilities" / "dynamics_capabilities.json"
GOLDEN_PATH = BACKEND_ROOT / "tests" / "golden" / "phase42_dynamics_cases.json"
CONTRACT_PATH = BACKEND_ROOT / "tests" / "contracts" / "phase42_api_schema_contract.json"
BASELINE_PATH = BACKEND_ROOT / "reports" / "phase42_baseline.json"
ROUTING_REPORT_PATH = BACKEND_ROOT / "reports" / "routing_confusion" / "report.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CAPABILITY = _load(CAPABILITY_PATH)
GOLDEN = _load(GOLDEN_PATH)
CONTRACT = _load(CONTRACT_PATH)
BASELINE = _load(BASELINE_PATH)


def _field_names(model) -> list[str]:
    return list(model.model_fields)


def _find_answer(response, expectation: dict):
    if expectation["selector"] == "primary":
        assert response.answer is not None
        return response.answer
    assert expectation["selector"] == "symbol"
    for item in response.answers:
        if item.symbol == expectation["symbol"]:
            return item
    pytest.fail(f"answer symbol {expectation['symbol']!r} not found: {[x.symbol for x in response.answers]}")


def _assert_close(observed: float, expected: float, tolerance: dict) -> None:
    assert math.isclose(
        float(observed),
        float(expected),
        rel_tol=float(tolerance["relative"]),
        abs_tol=float(tolerance["absolute"]),
    ), f"observed={observed}, expected={expected}, tolerance={tolerance}"


@pytest.mark.unit
def test_phase42_capability_matrix_is_complete_and_machine_readable():
    assert CAPABILITY["schema_version"] == 1
    entries = CAPABILITY["capabilities"]
    registry_names = [solver.name for solver in SolverRegistry().solvers]
    assert len(entries) == len(registry_names)
    assert len(registry_names) == len(set(registry_names))
    assert len(entries) == len({entry["analytic_solver"] for entry in entries})
    assert [entry["analytic_solver"] for entry in entries] == registry_names

    required = {
        "system_type",
        "subtypes",
        "required_inputs",
        "optional_inputs",
        "requested_outputs",
        "assumptions",
        "analytic_solver",
        "validators",
        "numeric_support",
        "chrono_support",
        "visualization_support",
        "known_limitations",
    }
    for entry in entries:
        assert set(entry) == required or set(entry) == required | {"textbook_parser_safe"}
        assert entry["system_type"]
        assert isinstance(entry["subtypes"], list)
        assert set(entry["required_inputs"]) == {"all_of", "any_of", "conditional"}
        assert all(isinstance(rule, dict) for rule in entry["required_inputs"]["conditional"])
        assert set(entry["validators"]) >= {"answer_consistency", "dimension", "plausibility", "provenance"}
        assert entry["numeric_support"]["independent_time_integration"] is False
        assert entry["visualization_support"]["dynamic_physics"] is False
        assert entry["known_limitations"]
    assert {
        entry["analytic_solver"]
        for entry in entries
        if entry.get("textbook_parser_safe") is True
    } == {"constant_acceleration_1d"}


@pytest.mark.unit
def test_phase42_capability_validator_claims_match_current_code():
    residual_systems = set(CHECKERS) | {"pure_rolling_energy", "rolling_energy_general"}
    for entry in CAPABILITY["capabilities"]:
        claimed = "equation_residual" in entry["validators"]
        assert claimed == (entry["system_type"] in residual_systems)


@pytest.mark.unit
def test_phase42_chrono_matrix_does_not_overclaim_execution():
    allowed = {"none", "automated_optional"}
    assert {entry["chrono_support"]["status"] for entry in CAPABILITY["capabilities"]} <= allowed
    automated = {
        entry["analytic_solver"]
        for entry in CAPABILITY["capabilities"]
        if entry["chrono_support"]["status"] == "automated_optional"
    }
    assert automated == {
        "incline_with_friction",
        "massive_pulley_atwood",
        "pure_rolling_energy",
        "collision_1d",
    }
    assert next(
        entry for entry in CAPABILITY["capabilities"]
        if entry["analytic_solver"] == "rolling_energy_general"
    )["chrono_support"]["status"] == "none"


@pytest.mark.unit
def test_phase42_golden_inventory_and_independent_oracles():
    cases = GOLDEN["cases"]
    assert len(cases) >= 30
    assert len({case["id"] for case in cases}) == len(cases)
    required_domains = {
        "constant_acceleration",
        "projectile",
        "incline",
        "friction",
        "pulley",
        "collision",
        "work_energy",
        "impulse_momentum",
        "rolling",
        "fixed_axis_rotation",
        "plane_rigid_body",
        "vibration",
    }
    domains = {case["domain"] for case in cases}
    assert required_domains <= domains
    assert {"polar_coordinates", "rotating_frame"} & domains
    for case in cases:
        assert case["oracle"]["basis"] == "independent_physics_law"
        assert case["oracle"]["expression"]
        assert case["oracle"]["derivation"]
        assert case["expected_status"] in {"solved", "needs_clarification", "unsupported"}
        assert case["tolerance"]["absolute"] > 0
        assert case["tolerance"]["relative"] > 0


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["id"])
@pytest.mark.regression
def test_phase42_golden_parser_contract(case):
    canonical = extract_problem(case["problem_text"])
    expected = case["expected_canonical_facts"]
    assert canonical.system_type == expected["system_type"]
    assert canonical.subtype == expected["subtype"]
    for symbol, value in expected["known_values"].items():
        assert symbol in canonical.knowns, f"{case['id']}: missing canonical known {symbol}"
        assert canonical.knowns[symbol].value is not None
        assert math.isclose(float(canonical.knowns[symbol].value), float(value), rel_tol=1e-9, abs_tol=1e-9)
    assert canonical.requested_outputs == case["expected_requested_outputs"]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["id"])
@pytest.mark.regression
def test_phase42_golden_route_contract(case):
    canonical = extract_problem(case["problem_text"])
    solver = SolverRegistry().select(canonical)
    if case["expected_route"] is None:
        assert solver is None
    else:
        assert solver is not None
        assert solver.name == case["expected_route"]


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["id"])
@pytest.mark.regression
def test_phase42_golden_answer_contract(case):
    response = solve_problem(case["problem_text"])
    if case["expected_status"] == "solved":
        assert response.ok, response.unsupported_reason
        assert response.clarification is None
    elif case["expected_status"] == "needs_clarification":
        assert not response.ok
        assert response.clarification is not None
    else:
        assert not response.ok
        assert response.clarification is None

    # A clarification/unsupported response intentionally exposes no student answer.
    # Its independent oracle remains in the fixture for the future regression,
    # while numeric comparison is enforceable only for currently solved cases.
    if case["expected_status"] != "solved":
        return

    for expectation in case["expected_answers"]:
        answer = _find_answer(response, expectation)
        assert answer.numeric is not None
        _assert_close(answer.numeric, expectation["numeric"], case["tolerance"])
        assert answer.unit == expectation["unit"]


@pytest.mark.unit
def test_phase42_engine_dataclass_contract():
    actual = {
        "CanonicalProblem": [field.name for field in fields(CanonicalProblem)],
        "SolverResult": [field.name for field in fields(SolverResult)],
        "VerificationReport": [field.name for field in fields(VerificationReport)],
        "CalculationCoordinateFrame": [field.name for field in fields(CalculationCoordinateFrame)],
        "SemanticFactEvidence": [field.name for field in fields(SemanticFactEvidence)],
        "EquationEvidence": [field.name for field in fields(EquationEvidence)],
        "SubstitutionEvidence": [field.name for field in fields(SubstitutionEvidence)],
        "OutputEvidenceLink": [field.name for field in fields(OutputEvidenceLink)],
        "SolverExplanationEvidence": [field.name for field in fields(SolverExplanationEvidence)],
    }
    assert actual == CONTRACT["engine_dataclasses"]


@pytest.mark.unit
def test_phase42_pydantic_schema_contract():
    actual = {
        "ProblemRequest": _field_names(ProblemRequest),
        "CanonicalProblemModel": _field_names(CanonicalProblemModel),
        "DiagnosisResponse": _field_names(DiagnosisResponse),
        "AnswerModel": _field_names(AnswerModel),
        "AnswerItemModel": _field_names(AnswerItemModel),
        "VerificationReport": _field_names(VerificationReportModel),
        "ClarificationOptionModel": _field_names(ClarificationOptionModel),
        "ClarificationModel": _field_names(ClarificationModel),
        "SolveResponse": _field_names(SolveResponse),
        "ExplanationCoordinateFrameModel": _field_names(ExplanationCoordinateFrameModel),
        "ExplanationFactModel": _field_names(ExplanationFactModel),
        "ExplanationEquationModel": _field_names(ExplanationEquationModel),
        "ExplanationSubstitutionModel": _field_names(ExplanationSubstitutionModel),
        "ExplanationCandidateSummaryModel": _field_names(ExplanationCandidateSummaryModel),
        "ExplanationValidationSummaryModel": _field_names(ExplanationValidationSummaryModel),
        "ExplanationAnswerDerivationModel": _field_names(ExplanationAnswerDerivationModel),
        "ExplanationStudentStepModel": _field_names(ExplanationStudentStepModel),
        "ExplanationTraceModel": _field_names(ExplanationTraceModel),
    }
    assert actual == CONTRACT["api_models"]


@pytest.mark.unit
def test_phase53_schema_migration_is_append_only_and_optional():
    # Phase 54 appended visualization_scene after the Phase 53 field; the
    # Phase 53 guarantees stay intact (explanation_trace immediately before).
    assert CONTRACT["schema_version"] == 8
    assert CONTRACT["engine_dataclasses"]["SolverResult"][-1] == "explanation_evidence"
    assert CONTRACT["api_models"]["SolveResponse"][-3] == "explanation_trace"
    assert SolverResult(ok=False).explanation_evidence is None
    assert SolveResponse.model_fields["explanation_trace"].default is None


@pytest.mark.unit
def test_phase54_schema_migration_is_append_only_and_optional():
    assert CONTRACT["api_models"]["SolveResponse"][-2] == "visualization_scene"
    assert SolveResponse.model_fields["visualization_scene"].default is None


@pytest.mark.unit
def test_phase55_schema_migration_is_append_only_optional_and_non_authoritative():
    assert CONTRACT["api_models"]["SolveResponse"][-1] == "textbook_parse"
    assert CONTRACT["api_models"]["DiagnosisResponse"][-1] == "textbook_parse"
    assert CONTRACT["engine_dataclasses"]["CanonicalProblem"][-1] == "textbook_parse"
    assert SolveResponse.model_fields["textbook_parse"].default is None
    assert CanonicalProblem().textbook_parse is None


@pytest.mark.regression
def test_phase42_solve_api_response_contracts():
    client = TestClient(app)
    top_keys = set(CONTRACT["api_models"]["SolveResponse"])
    diagnosis_keys = set(CONTRACT["api_models"]["DiagnosisResponse"])
    verification_keys = set(CONTRACT["api_models"]["VerificationReport"])

    solved = client.post("/solve", json={"problem_text": "마찰이 없는 30도 경사면 위 블록의 가속도는?"})
    assert solved.status_code == CONTRACT["response_contracts"]["solved"]["http_status"]
    solved_payload = solved.json()
    assert set(solved_payload) == top_keys
    assert set(solved_payload["diagnosis"]) == diagnosis_keys
    assert set(solved_payload["verification"]) == verification_keys
    assert solved_payload["ok"] is True
    assert solved_payload["answer"] is not None
    assert set(solved_payload["answer"]) == set(CONTRACT["api_models"]["AnswerModel"])
    assert solved_payload["clarification"] is None
    assert solved_payload["unsupported_reason"] is None

    clarification = client.post("/solve", json={"problem_text": "30도 경사면 위 블록의 가속도는?"})
    assert clarification.status_code == CONTRACT["response_contracts"]["clarification"]["http_status"]
    clarification_payload = clarification.json()
    assert set(clarification_payload) == top_keys
    assert clarification_payload["ok"] is False
    assert clarification_payload["answer"] is None
    assert clarification_payload["clarification"] is not None
    assert set(clarification_payload["clarification"]) == set(CONTRACT["api_models"]["ClarificationModel"])
    assert clarification_payload["unsupported_reason"]

    unsupported = client.post("/solve", json={"problem_text": "오늘 저녁 메뉴를 추천해 줘."})
    assert unsupported.status_code == CONTRACT["response_contracts"]["unsupported"]["http_status"]
    unsupported_payload = unsupported.json()
    assert set(unsupported_payload) == top_keys
    assert unsupported_payload["ok"] is False
    assert unsupported_payload["answer"] is None
    assert unsupported_payload["clarification"] is None
    assert unsupported_payload["unsupported_reason"]


@pytest.mark.unit
def test_phase42_baseline_report_has_honest_measurement_states():
    assert BASELINE["schema_version"] == 1
    allowed = {"passed", "failed", "not_run", "blocked", "skipped"}
    for result in BASELINE["test_suites"].values():
        assert result["status"] in allowed
        for key in ("passed", "failed", "skipped", "deselected", "duration_seconds"):
            assert key in result
        if result["status"] == "not_run":
            assert result["passed"] is None
            assert result["failed"] is None

    versioned = BASELINE["current_versioned_artifacts"]
    routing_source = _load(ROUTING_REPORT_PATH)
    assert versioned["routing_confusion"]["routing_cases"] == routing_source["routing"]["total"]
    assert versioned["routing_confusion"]["correct"] == routing_source["routing"]["correct"]
    assert versioned["routing_confusion"]["negative_cases"] == routing_source["negative"]["checked"]
    assert versioned["routing_confusion"]["duration_seconds"] == routing_source["meta"]["duration_seconds"]
    assert versioned["routing_confusion"]["false_solve_rate"] == 0.0

    performance = BASELINE["performance_baseline"]
    assert performance["fixture_cases"] == len(GOLDEN["cases"])
    assert performance["samples"] == performance["fixture_cases"] * performance["repeats"]
    assert 0 < performance["mean_ms"] <= performance["p95_ms"] <= performance["max_ms"]
    assert set(performance["optional_dependencies_blocked"]) == {"chrono", "pychrono", "pydy", "scipy"}
    assert performance["result"] == "passed"
    assert BASELINE["metrics_not_currently_measurable"]
