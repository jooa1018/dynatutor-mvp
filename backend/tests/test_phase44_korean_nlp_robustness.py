from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.extraction.extractor import extract_problem
from engine.nlp.evaluation import (
    TOP_K,
    _topk_candidate_types,
    evaluate_cases,
    evaluate_fixture,
    load_fixture,
)
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


def test_versioned_baseline_report_tracks_safety_improvement():
    report_path = Path(__file__).resolve().parents[1] / "reports" / "phase44_nlp_metrics.json"
    markdown_path = report_path.with_suffix(".md")
    metrics = json.loads(report_path.read_text(encoding="utf-8"))

    assert metrics["fixture"]["case_count"] >= 300
    assert metrics["execution_environment"]["llm_used"] is False
    assert metrics["final"]["gates"]["passed"] is True
    assert metrics["baseline"]["metrics"]["false_solve_rate"] > metrics["final"]["metrics"]["false_solve_rate"]
    assert metrics["baseline"]["metrics"]["high_confidence_false_solves"] > metrics["final"]["metrics"]["high_confidence_false_solves"]
    assert metrics["comparison"]["false_solve_rate_reduction"] > 0
    assert markdown_path.exists()


def _primary_numeric(response):
    assert response.ok is True
    assert response.answer is not None
    assert response.answer.numeric is not None
    return response.answer.numeric


@pytest.mark.parametrize(
    "actor",
    ["운전하는 사람이 탄 트럭", "자전하는 팽이", "도전하는 학생의 수레", "회전하는 물체"],
)
def test_audit_f1_dynamics_words_containing_charge_syllables_are_not_electromagnetism(actor):
    response = solve_problem(
        f"{actor}가 정지 상태에서 3 m/s²로 4초 가속한다. 최종 속도는?"
    )

    assert response.diagnosis.canonical.system_type == "constant_acceleration_1d"
    assert response.diagnosis.canonical.subtype != "electromagnetism"
    assert _primary_numeric(response) == pytest.approx(12.0)


def test_audit_f1_real_charge_and_electric_field_remain_unsupported():
    response = solve_problem("전하량 2 C인 점전하가 전기장 안에 있다. 전기력은?")

    assert response.ok is False
    assert response.diagnosis.canonical.system_type == "unsupported"
    assert response.diagnosis.canonical.subtype == "electromagnetism"


@pytest.mark.parametrize("torque_unit", ["N m", "N*m", "N·m", "Nm"])
@pytest.mark.parametrize("inertia_unit", ["kg m^2", "kg*m^2", "kg·m²", "kgm2"])
def test_audit_f2_compound_unit_variants_do_not_conflict(torque_unit, inertia_unit):
    raw = (
        f"토크 tau = 5 {torque_unit}가 작용한다. "
        f"관성모멘트 I = 2 {inertia_unit}이다. 각가속도는?"
    )
    canonical = extract_problem(raw)
    response = solve_problem(raw)

    assert canonical.canonical_v2.conflicts == []
    assert canonical.knowns["tau"].value == pytest.approx(5.0)
    assert canonical.knowns["I"].value == pytest.approx(2.0)
    assert _primary_numeric(response) == pytest.approx(2.5)


@pytest.mark.parametrize(
    "raw,key,expected",
    [
        ("질량 m=500 g, m=0.5 kg이다. 힘 F=10 N일 때 가속도는?", "m", 0.5),
        (
            "자동차의 v0=36 km/h, v0=10 m/s이고 a=2 m/s²이다. 5 s 후 최종속도는?",
            "v0",
            10.0,
        ),
        (
            "가속도 a=500 cm/s², a=5 m/s²이고 v0=0 m/s이다. 2 s 후 최종속도는?",
            "a",
            5.0,
        ),
    ],
)
def test_audit_f2_equivalent_normalized_values_remain_non_conflicting(raw, key, expected):
    canonical = extract_problem(raw)

    assert canonical.canonical_v2.conflicts == []
    assert canonical.knowns[key].value == pytest.approx(expected)


def test_audit_f2_different_compound_unit_values_still_conflict():
    canonical = extract_problem(
        "토크 tau=5 N·m이고 다른 측정에서는 tau=6 N m이다. "
        "관성모멘트 I=2 kg·m²일 때 각가속도는?"
    )

    assert any("tau has conflicting explicit values" in item for item in canonical.canonical_v2.conflicts)


@pytest.mark.parametrize(
    "raw",
    [
        "실험실 온도는 25도이다. 질량 2 kg 물체에 10 N 힘이 작용한다. 가속도는?",
        "질량 2 kg 물체가 있다. 실험실 온도는 25도이다. 10 N 힘이 작용한다. 가속도는?",
        "참고로 관찰자의 질량은 2 kg이다. 질량 2 kg 물체에 10 N 힘이 작용한다. 가속도는?",
        "실험실 온도는 25도이다.\n질량 2 kg 물체에 10 N 힘이 작용한다.\n가속도는?",
    ],
)
def test_audit_f3_retained_facts_keep_exact_raw_provenance(raw):
    canonical = extract_problem(raw)
    facts = {
        fact.compatibility_key: fact
        for fact in canonical.canonical_v2.facts
        if fact.compatibility_key in {"m", "F"}
    }

    assert set(facts) == {"m", "F"}
    for fact in facts.values():
        assert fact.status == "explicit"
        assert fact.source_span is not None
        start, end = fact.source_span
        assert raw[start:end] == fact.extraction_evidence["matched_raw_text"]
        assert raw[start:end]


def test_audit_f4_same_subject_natural_language_initial_speeds_require_clarification():
    response = solve_problem(
        "물체의 처음 속도는 36 km/h이다. "
        "이후 설명에는 처음 속도가 15 m/s라고 적혀 있다. "
        "가속도는 2 m/s²이고 5초 후 최종 속도를 구하여라."
    )

    assert response.ok is False
    assert response.answer is None
    assert response.clarification is not None
    assert response.clarification.rule == "contradictory_input"


@pytest.mark.parametrize(
    "raw",
    [
        (
            "트럭의 초속도는 20 m/s이다. 자동차의 초속도는 15 m/s이다. "
            "자동차는 2 m/s²로 5초 가속한다. 자동차의 최종 속도는?"
        ),
        (
            "트럭은 v0=20 m/s이다. 자동차는 v0=15 m/s이다. "
            "자동차는 2 m/s²로 5초 가속한다. 자동차의 최종 속도는?"
        ),
    ],
)
def test_audit_f4_requested_subject_selects_its_own_initial_speed(raw):
    canonical = extract_problem(raw)
    response = solve_problem(raw)

    assert canonical.knowns["v0"].value == pytest.approx(15.0)
    assert canonical.canonical_v2.conflicts == []
    assert _primary_numeric(response) == pytest.approx(25.0)


def test_audit_f7_background_markers_do_not_delete_longer_physics_words():
    cart = extract_problem("학생 수레가 2 m/s로 움직인다. 3초 후 속도는?")
    clock = extract_problem("벽시계의 진자가 주기 2초로 진동한다. 진동수는?")

    assert cart.knowns["v0"].value == pytest.approx(2.0)
    assert cart.system_type != "unsupported"
    assert clock.flags["vibration"] is True
    assert "period" in clock.requested_outputs
    assert "frequency" in clock.requested_outputs


def _metric_case(*, include_time_oracle=True, allowed_assumptions=None):
    knowns = {
        "v0": {"value": 0.0, "unit": "m/s"},
        "a": {"value": 2.0, "unit": "m/s^2"},
    }
    if include_time_oracle:
        knowns["t"] = {"value": 3.0, "unit": "s"}
    expected = {
        "status": "solved",
        "system_type": "constant_acceleration_1d",
        "knowns": knowns,
        "requested_outputs": ["final_velocity"],
        "subjects": {},
        "conditions": [],
    }
    if allowed_assumptions is not None:
        expected["allowed_assumption_kinds"] = allowed_assumptions
    return {
        "id": "metric_guard_case",
        "category": "metric_guard",
        "text": "정지 상태에서 a=2 m/s²로 3 s 가속한다. 최종속도는?",
        "expected": expected,
    }


def test_metric_zero_denominator_is_insufficient_and_cannot_auto_pass_gate():
    report = evaluate_cases([_metric_case()])

    assert report["metrics"]["subtype_accuracy"] is None
    assert report["metric_samples"]["subtype_accuracy"]["denominator"] == 0
    assert report["gates"]["results"]["subtype_accuracy"] is False
    assert report["gates"]["details"]["subtype_accuracy"] == "insufficient_samples"


def test_metric_unlisted_extra_quantity_reduces_precision_without_forbidden_knowns():
    report = evaluate_cases([_metric_case(include_time_oracle=False)])

    assert report["metrics"]["quantity_precision"] < 1.0
    assert any(
        item.get("unexpected_symbol") == "t"
        for item in report["failures"]["quantity"]
    )


def test_metric_top_k_uses_exactly_the_declared_number_of_ranked_candidates():
    candidates = [
        SimpleNamespace(
            score=score,
            system_type_candidates=[
                SimpleNamespace(score=score, system_type=f"candidate_{index}")
            ],
        )
        for index, score in enumerate([0.9, 0.8, 0.7, 0.6], start=1)
    ]
    canonical = SimpleNamespace(
        system_type="primary",
        canonical_v2=SimpleNamespace(parse_candidates=candidates),
    )

    ranked = _topk_candidate_types(canonical)
    assert TOP_K == 3
    assert ranked == ["primary", "candidate_1", "candidate_2"]
    assert len(ranked) == TOP_K


def test_metric_empty_confidence_bins_are_na_not_perfect_accuracy():
    report = evaluate_cases([_metric_case()])

    empty_bins = [
        values
        for values in report["confidence_bins"].values()
        if values["count"] == 0
    ]
    assert empty_bins
    assert all(values["accuracy"] is None for values in empty_bins)


def test_metric_real_silent_assumption_case_changes_the_rate():
    report = evaluate_cases([_metric_case(allowed_assumptions=[])])

    assert report["metric_samples"]["silent_assumption_rate"] == {
        "numerator": 1,
        "denominator": 1,
        "minimum_samples": None,
        "sufficient_samples": True,
    }
    assert report["metrics"]["silent_assumption_rate"] == 1.0
    assert report["failures"]["silent_assumption"]


def test_benchmark_reliability_counts_are_reported(report):
    reliability = report["benchmark_reliability"]

    assert reliability["suite_kind"] == "curated_regression_suite"
    assert reliability["identical_sentence_count"] == 81
    assert reliability["numeric_only_duplicate_count"] == 60
    assert reliability["unique_sentence_stimulus_count"] == 179
    assert reliability["category_unique_sentence_counts"]
    assert "external held-out validation set" in " ".join(reliability["limitations"])
