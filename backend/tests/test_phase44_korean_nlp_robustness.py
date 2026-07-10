from __future__ import annotations

from collections import Counter

import pytest

from engine.extraction.extractor import extract_problem
from engine.nlp.evaluation import evaluate_fixture, load_fixture
from engine.services import solve_problem


@pytest.fixture(scope="module")
def fixture():
    return load_fixture()


@pytest.fixture(scope="module")
def report():
    return evaluate_fixture()


def test_curated_fixture_has_independent_intermediate_oracles(fixture):
    cases = fixture["cases"]
    assert len(cases) >= 300
    categories = Counter(case["category"] for case in cases)
    assert categories == {
        "paraphrase": 80,
        "subject_context": 30,
        "unit_symbol": 40,
        "typo_colloquial": 20,
        "irrelevant_background": 25,
        "multi_object": 30,
        "ambiguity": 30,
        "missing_information": 25,
        "contradiction": 20,
        "unsupported": 20,
    }
    assert "no expected value was copied" in fixture["review_policy"].lower()
    required = {"status", "system_type", "knowns", "requested_outputs", "subjects", "conditions"}
    for case in cases:
        assert case["oracle_basis"]
        assert required.issubset(case["expected"])


def test_curated_report_passes_phase44_release_gates(report):
    assert report["case_count"] >= 300
    assert report["llm_used"] is False
    assert report["metrics"]["false_solve_rate"] == 0.0
    assert report["metrics"]["high_confidence_false_solves"] == 0
    assert report["gates"]["passed"], report["gates"]["results"]


def test_intermediate_parse_handles_background_typos_and_candidates():
    background = extract_problem(
        "참고로 관찰자의 질량은 99kg이었다. "
        "정지 상태 물체가 a=2m/s²로 t=5s 움직인다. 최종속도는?"
    )
    assert "m" not in background.knowns
    assert background.system_type == "constant_acceleration_1d"
    assert background.requested_outputs == ["final_velocity"]

    typo = extract_problem("마찰 업는 30도 경사면에서 가속도 얼마야?")
    assert typo.system_type == "particle_on_incline"
    assert typo.subtype == "no_friction"
    assert typo.requested_outputs == ["acceleration"]
    conditions = {
        fact.symbol: fact.status
        for fact in typo.canonical_v2.facts
        if fact.kind == "condition"
    }
    assert conditions["no_friction"] == "explicit"

    ambiguous = extract_problem("도르래에 연결된 m1=2kg, m2=3kg 두 물체의 가속도는?")
    candidate_types = {
        candidate.system_type
        for parse in ambiguous.canonical_v2.parse_candidates
        for candidate in parse.system_type_candidates
    }
    assert {
        "pulley_atwood",
        "pulley_table_hanging",
        "pulley_incline_hanging",
    }.issubset(candidate_types)


def test_contradictions_never_reach_a_solver_answer():
    response = solve_problem(
        "v0=0m/s라고 했지만 v0=5m/s라고도 적혀 있다. "
        "a=2m/s^2, t=3s일 때 최종속도는?"
    )
    assert response.ok is False
    assert response.answer is None
    assert response.answers == []
    assert response.clarification is not None
    assert response.clarification.rule == "contradictory_input"
    assert response.verification.passed is False
    assert response.verification.errors


def test_explicit_out_of_scope_domain_is_unsupported_without_false_solve():
    response = solve_problem(
        "3차원 공간에서 공을 v0=20m/s, theta=30도로 발사하고 "
        "방위각 40도를 준다. 3D 궤적과 사거리는?"
    )
    assert response.ok is False
    assert response.answer is None
    assert response.diagnosis.canonical.system_type == "unsupported"
    assert response.diagnosis.canonical.subtype == "three_dimensional"
    assert response.diagnosis.selected_solver is None


def test_student_api_shape_is_preserved_for_new_failure_states():
    response = solve_problem(
        "질량 m=2kg이며 동시에 m=3kg라고 주어졌다. "
        "힘 F=10N일 때 가속도는?"
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()
    assert {
        "ok",
        "diagnosis",
        "answer",
        "answers",
        "steps",
        "verification",
        "unsupported_reason",
        "clarification",
        "physical_model",
    }.issubset(payload)
    assert "canonical_v2" not in payload["diagnosis"]["canonical"]
