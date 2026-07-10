from __future__ import annotations

import copy
import json
import re

import pytest

from app.schemas.solution import CanonicalProblemModel
from engine.canonical.adapter import attach_canonical_v2, to_legacy_problem
from engine.canonical.models import CanonicalProblemV2
from engine.extraction.extractor import extract_problem
from engine.routing.clarify import apply_clarify_patch
from engine.solvers.registry import SolverRegistry


def _fact(canonical, compatibility_key: str):
    assert canonical.canonical_v2 is not None
    return next(
        fact
        for fact in canonical.canonical_v2.facts
        if fact.compatibility_key == compatibility_key
    )


@pytest.mark.unit
def test_phase43_major_values_have_provenance_confidence_and_raw_span():
    raw = "질량 m=2kg인 물체에 힘 F=10N이 작용한다. 가속도는?"
    canonical = extract_problem(raw)
    v2 = canonical.canonical_v2

    assert v2 is not None
    assert v2.schema_version == "2.0"
    assert len(v2.fingerprint) == 64
    assert all(0.0 <= fact.confidence <= 1.0 for fact in v2.facts)

    mass = _fact(canonical, "m")
    assert mass.status == "explicit"
    assert mass.provenance == "text_extraction"
    assert mass.dimension == "mass"
    assert mass.source_span is not None
    start, end = mass.source_span
    assert re.sub(r"\s+", "", raw[start:end].lower()) in re.sub(
        r"\s+", "", (mass.source_text or "").lower()
    )


@pytest.mark.unit
def test_phase43_default_value_is_not_marked_explicit():
    canonical = extract_problem("질량 m=2kg인 물체에 힘 F=10N이 작용한다. 가속도는?")
    gravity = _fact(canonical, "g")

    assert gravity.value == pytest.approx(9.81)
    assert gravity.status == "defaulted"
    assert gravity.provenance == "domain_default"
    assert gravity.source_span is None
    assert any(
        assumption.kind == "gravity" and assumption.source == "domain_default"
        for assumption in canonical.canonical_v2.assumptions
    )


@pytest.mark.unit
def test_phase43_explicit_condition_and_model_assumption_are_separate():
    implicit = extract_problem(
        "공을 발사속도 10m/s, 발사각 theta=30도로 발사했다. 사거리는?"
    ).canonical_v2
    explicit = extract_problem(
        "공기저항을 무시하고 공을 발사속도 10m/s, 발사각 theta=30도로 발사했다. 사거리는?"
    ).canonical_v2

    assert implicit is not None and explicit is not None
    assert not any(fact.symbol == "air_resistance_ignored" for fact in implicit.facts)
    assert any(
        assumption.kind == "air_resistance" and assumption.source == "solver_default"
        for assumption in implicit.assumptions
    )

    air_condition = next(
        fact for fact in explicit.facts if fact.symbol == "air_resistance_ignored"
    )
    assert air_condition.status == "explicit"
    assert air_condition.source_span is not None
    assert not any(
        assumption.kind == "air_resistance" for assumption in explicit.assumptions
    )


@pytest.mark.unit
def test_phase43_unit_normalization_preserves_source_representation():
    canonical = extract_problem(
        "자동차가 72km/h에서 출발하여 가속도 a=2m/s^2로 5s 동안 운동한다. 최종속도는?"
    )
    speed = _fact(canonical, "v0")

    assert speed.value == pytest.approx(20.0)
    assert speed.unit == "m/s"
    assert speed.status == "normalized"
    assert speed.provenance == "unit_normalization"
    assert {"value": 72.0, "unit": "km/h", "relation": "source_representation"} in speed.alternatives


@pytest.mark.unit
def test_phase43_equivalent_duplicate_units_do_not_create_a_conflict():
    canonical = extract_problem(
        "자동차의 v0=36km/h, v0=10m/s이고 가속도 a=2m/s^2이다. 5s 후 최종속도는?"
    )
    speed = _fact(canonical, "v0")

    assert canonical.canonical_v2.conflicts == []
    assert speed.value == pytest.approx(10.0)
    assert speed.status == "normalized"
    assert len(speed.alternatives) == 2
    assert [item["normalized_value"] for item in speed.alternatives] == pytest.approx([10.0, 10.0])


@pytest.mark.unit
def test_phase43_same_physical_symbol_is_scoped_to_distinct_subjects():
    canonical = extract_problem(
        "m1=2kg, m2=3kg, v1=4m/s, v2=0m/s인 두 물체가 완전비탄성 충돌한다. 충돌 후 속도는?"
    )
    mass_facts = [
        fact
        for fact in canonical.canonical_v2.facts
        if fact.kind == "quantity" and fact.symbol == "m"
    ]

    assert {(fact.subject_id, fact.compatibility_key) for fact in mass_facts} >= {
        ("object_1", "m1"),
        ("object_2", "m2"),
    }


@pytest.mark.unit
def test_phase43_conflicting_explicit_values_are_retained():
    canonical = extract_problem(
        "질량 m1=2kg이고 다른 문장에는 m1=3kg이라고 적혀 있다. 힘 F=10N일 때 가속도는?"
    )
    mass = _fact(canonical, "m1")

    assert mass.status == "conflicting"
    assert mass.provenance == "conflict_detection"
    assert len(mass.alternatives) == 2
    assert [item["normalized_value"] for item in mass.alternatives] == pytest.approx([2.0, 3.0])
    assert any("m1 has conflicting explicit values" in item for item in canonical.canonical_v2.conflicts)


@pytest.mark.unit
def test_phase43_ambiguous_interpretations_are_preserved_as_parse_candidates():
    canonical = extract_problem(
        "도르래에 연결된 m1=2kg, m2=3kg 두 물체의 가속도는?"
    )
    v2 = canonical.canonical_v2

    assert canonical.system_type == "ambiguous_pulley"
    candidate_types = {
        candidate.system_type_candidates[0].system_type
        for candidate in v2.parse_candidates
    }
    assert {
        "ambiguous_pulley",
        "pulley_atwood",
        "pulley_table_hanging",
        "pulley_incline_hanging",
    } <= candidate_types
    fact_ids = {fact.fact_id for fact in v2.facts}
    assert all(set(candidate.facts) <= fact_ids for candidate in v2.parse_candidates)


@pytest.mark.regression
def test_phase43_v2_to_v1_compatibility_preserves_solver_inputs_and_route():
    original = extract_problem(
        "마찰이 없는 30도 경사면 위 블록의 가속도는?"
    )
    restored = to_legacy_problem(original.canonical_v2)

    assert restored.system_type == original.system_type
    assert restored.subtype == original.subtype
    assert restored.flags == original.flags
    assert restored.requested_outputs == original.requested_outputs
    assert {
        key: (value.value, value.unit, value.source_text)
        for key, value in restored.knowns.items()
    } == {
        key: (value.value, value.unit, value.source_text)
        for key, value in original.knowns.items()
    }
    assert SolverRegistry().select(restored).name == SolverRegistry().select(original).name


@pytest.mark.unit
def test_phase43_fingerprint_is_independent_of_collection_order():
    v2 = extract_problem(
        "m1=2kg, m2=3kg, v1=4m/s, v2=0m/s인 두 물체가 완전비탄성 충돌한다. 충돌 후 속도는?"
    ).canonical_v2
    reordered = copy.deepcopy(v2)
    reordered.facts.reverse()
    reordered.assumptions.reverse()
    reordered.parse_candidates.reverse()
    reordered.requested_outputs.reverse()

    assert reordered.compute_fingerprint() == v2.fingerprint


@pytest.mark.unit
def test_phase43_serialization_round_trip_preserves_fingerprint_and_contract():
    v2 = extract_problem(
        "공기저항을 무시하고 공을 발사속도 15m/s, 발사각 theta=30도로 발사했다. 사거리는?"
    ).canonical_v2
    payload = v2.to_json()
    restored = CanonicalProblemV2.from_json(payload)

    assert json.loads(restored.to_json()) == json.loads(payload)
    assert restored.fingerprint == v2.fingerprint
    assert restored.compute_fingerprint() == v2.fingerprint


@pytest.mark.unit
def test_phase43_fact_ids_and_fingerprint_are_deterministic():
    raw = "질량 m=2kg인 물체에 힘 F=10N이 작용한다. 가속도는?"
    first = extract_problem(raw).canonical_v2
    second = extract_problem(raw).canonical_v2

    assert [fact.fact_id for fact in first.facts] == [fact.fact_id for fact in second.facts]
    assert first.fingerprint == second.fingerprint


@pytest.mark.regression
def test_phase43_clarification_patch_refreshes_assumptions_and_fingerprint():
    canonical = extract_problem("30도 경사면 위 블록의 가속도는?")
    before = canonical.canonical_v2.fingerprint
    patched = apply_clarify_patch(
        canonical,
        {"subtype": "no_friction", "assume": "마찰 무시"},
    )

    assert patched.canonical_v2.fingerprint != before
    assert patched.canonical_v2.subtype == "no_friction"
    assert any(
        assumption.source == "user_confirmation" and assumption.value == "마찰 무시"
        for assumption in patched.canonical_v2.assumptions
    )


@pytest.mark.regression
def test_phase43_user_supplied_known_has_user_confirmation_provenance():
    canonical = extract_problem("30도 경사면 위 블록의 가속도는?")
    patched = apply_clarify_patch(
        canonical,
        {
            "subtype": "with_friction",
            "set_known": {
                "symbol": "mu",
                "value": 0.2,
                "unit": "",
                "label": "운동마찰계수",
            },
        },
    )
    friction = _fact(patched, "mu")

    assert friction.value == pytest.approx(0.2)
    assert friction.status == "inferred"
    assert friction.provenance == "user_confirmation"
    assert friction.confidence == pytest.approx(1.0)
    assert friction.source_span is None


@pytest.mark.unit
def test_phase43_every_explicit_fact_has_valid_raw_extraction_evidence():
    raw = (
        "공기저항을 무시한다. m1=2kg, m2=3kg, v1=4m/s, v2=0m/s인 "
        "두 물체가 완전비탄성 충돌한다."
    )
    v2 = extract_problem(raw).canonical_v2

    explicit = [fact for fact in v2.facts if fact.status == "explicit"]
    assert explicit
    for fact in explicit:
        assert fact.source_span is not None
        start, end = fact.source_span
        assert 0 <= start < end <= len(raw)
        assert raw[start:end] == fact.extraction_evidence["matched_raw_text"]


@pytest.mark.unit
def test_phase43_horizontal_phrase_theta_is_inferred_not_explicit():
    raw = "공을 수평으로 10 m/s로 절벽에서 던졌다. 절벽의 높이는 20 m이다. 비행시간은?"
    theta = _fact(extract_problem(raw), "theta")

    assert theta.value == pytest.approx(0.0)
    assert theta.status == "inferred"
    assert theta.provenance == "domain_rule"
    assert theta.source_span is None
    assert theta.confidence < 1.0


@pytest.mark.parametrize(
    ("raw", "key", "expected"),
    [
        ("공을 속력 v0=15 m/s, 발사각 30도로 던졌다. 사거리는?", "v0", 15.0),
        ("공을 속력 v0=10 m/s, 발사각 30도로 던졌다. 사거리는?", "v0", 10.0),
        ("물체의 속력 v=25 m/s이다. 속도는?", "v", 25.0),
    ],
)
@pytest.mark.unit
def test_phase43_multidigit_velocity_is_not_partially_backtracked(raw, key, expected):
    fact = _fact(extract_problem(raw), key)

    assert fact.value == pytest.approx(expected)
    assert fact.unit == "m/s"
    assert fact.source_span is not None


@pytest.mark.unit
def test_phase43_fact_value_disagreement_with_single_occurrence_is_conflicting():
    canonical = extract_problem(
        "자동차의 v0=10m/s이고 가속도 a=2m/s^2이다. 5s 후 최종속도는?"
    )
    canonical.knowns["v0"].value = 12.0
    attach_canonical_v2(canonical)
    speed = _fact(canonical, "v0")

    assert speed.status == "conflicting"
    assert speed.confidence < 1.0
    assert canonical.canonical_v2.conflicts
    assert [item["normalized_value"] for item in speed.alternatives] == pytest.approx([10.0])


@pytest.mark.regression
def test_phase43_user_confirmation_resolves_and_preserves_raw_conflict():
    canonical = extract_problem(
        "질량 m1=2kg이고 다른 문장에는 m1=3kg이라고 적혀 있다. 힘 F=10N일 때 가속도는?"
    )
    patched = apply_clarify_patch(
        canonical,
        {
            "set_known": {
                "symbol": "m1",
                "value": 2,
                "unit": "kg",
                "label": "첫 번째 물체 질량",
            },
        },
    )
    mass = _fact(patched, "m1")

    assert mass.value == pytest.approx(2.0)
    assert mass.status == "inferred"
    assert mass.provenance == "user_confirmation"
    assert mass.confidence == pytest.approx(1.0)
    assert patched.canonical_v2.conflicts == []
    assert len(patched.canonical_v2.resolved_conflicts) == 1
    assert [item["normalized_value"] for item in mass.alternatives] == pytest.approx([2.0, 3.0])


@pytest.mark.regression
def test_phase43_rebuild_does_not_reintroduce_resolved_clarification():
    canonical = extract_problem(
        "질량 m1=2kg이고 다른 문장에는 m1=3kg이라고 적혀 있다. 힘 F=10N일 때 가속도는?"
    )
    patched = apply_clarify_patch(
        canonical,
        {
            "set_known": {
                "symbol": "m1",
                "value": 3,
                "unit": "kg",
                "label": "첫 번째 물체 질량",
            },
        },
    )

    attach_canonical_v2(patched)
    rebuilt = _fact(patched, "m1")
    assert patched.canonical_v2.conflicts == []
    assert patched.canonical_v2.resolved_conflicts
    assert rebuilt.provenance == "user_confirmation"
    assert rebuilt.status != "conflicting"


@pytest.mark.unit
def test_phase43_identical_numbers_keep_distinct_subject_spans():
    raw = "질량 2kg인 물체와 질량 2kg인 다른 물체가 v1=5m/s, v2=5m/s로 충돌한다."
    canonical = extract_problem(raw)
    mass_1 = _fact(canonical, "m1")
    mass_2 = _fact(canonical, "m2")

    assert mass_1.value == mass_2.value == pytest.approx(2.0)
    assert mass_1.source_span is not None
    assert mass_2.source_span is not None
    assert mass_1.source_span != mass_2.source_span
    assert raw[slice(*mass_1.source_span)] == raw[slice(*mass_2.source_span)] == "2kg"


@pytest.mark.unit
def test_phase43_background_speed_does_not_hijack_labeled_vehicle_fact():
    raw = (
        "참고로 옆 트럭은 36 km/h로 달린다. "
        "자동차는 v0=10 m/s이고 가속도 a=2 m/s^2이다. 5 s 후 최종속도는?"
    )
    speed = _fact(extract_problem(raw), "v0")

    assert speed.value == pytest.approx(10.0)
    assert speed.subject_id == "body"
    assert speed.source_span is not None
    assert "v0=10 m/s" in raw[slice(*speed.source_span)]
    assert "트럭" not in raw[slice(*speed.source_span)]


@pytest.mark.unit
def test_phase43_amplitude_A_is_not_bound_to_point_A():
    canonical = extract_problem(
        "질량 m=2kg, 스프링 상수 k=8N/m, 진폭 A=0.5m인 진동의 주기는?"
    )
    amplitude = _fact(canonical, "A")

    assert amplitude.value == pytest.approx(0.5)
    assert amplitude.subject_id == "oscillator"
    assert amplitude.subject_id != "point_A"


@pytest.mark.unit
def test_phase43_v1_v2_bind_to_their_objects_without_phantom_v0():
    raw = (
        "m1=2kg, m2=3kg인 두 물체의 초기속도는 "
        "v1=5m/s, v2=5m/s이고 서로 충돌한다. 반발계수 e=1이다."
    )
    canonical = extract_problem(raw)
    first = _fact(canonical, "v1")
    second = _fact(canonical, "v2")

    assert (first.subject_id, first.value) == ("object_1", pytest.approx(5.0))
    assert (second.subject_id, second.value) == ("object_2", pytest.approx(5.0))
    assert "v0" not in canonical.knowns
    assert not any(
        fact.compatibility_key == "v0" for fact in canonical.canonical_v2.facts
    )


@pytest.mark.unit
def test_phase43_unknown_quantity_binding_is_unbound_not_body():
    from engine.canonical.adapter import build_canonical_v2
    from engine.models import CanonicalProblem, Quantity

    canonical = CanonicalProblem(
        raw_text="",
        knowns={
            "mystery": Quantity(
                "mystery",
                7.0,
                None,
                provenance_hint="domain_rule",
            ),
        },
    )
    fact = next(
        fact for fact in build_canonical_v2(canonical).facts
        if fact.compatibility_key == "mystery"
    )

    assert fact.subject_id == "unbound"
    assert fact.status == "inferred"


@pytest.mark.unit
def test_phase43_serialization_round_trip_preserves_span_and_provenance_evidence():
    raw = "자동차의 v0=36km/h이고 가속도 a=2m/s^2이다. 5s 후 최종속도는?"
    original = extract_problem(raw).canonical_v2
    restored = CanonicalProblemV2.from_json(original.to_json())
    before = next(fact for fact in original.facts if fact.compatibility_key == "v0")
    after = next(fact for fact in restored.facts if fact.compatibility_key == "v0")

    assert after.source_span == before.source_span
    assert after.provenance == before.provenance == "unit_normalization"
    assert after.status == before.status == "normalized"
    assert after.extraction_evidence == before.extraction_evidence
    assert restored.resolved_conflicts == original.resolved_conflicts


@pytest.mark.regression
def test_phase43_student_api_contract_remains_v1_compatible():
    assert "canonical_v2" not in CanonicalProblemModel.model_fields
