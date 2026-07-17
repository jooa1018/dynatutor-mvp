from __future__ import annotations

import math

import pytest

from engine.extraction.extractor import extract_problem
from engine.model_builder import build_physical_model
from engine.observability.contracts import (
    LEGACY_MODEL_SCHEMA_VERSION,
    STATUS_VALUES,
    TYPED_MODEL_SCHEMA_VERSION,
    StableSnapshot,
    stable_json_dumps,
)
from engine.observability.trace import (
    SolveTraceCollector,
    legacy_model_fingerprint,
    project_equation_set,
    project_legacy_model,
    project_typed_model,
    typed_model_fingerprint,
)


@pytest.mark.unit
def test_phase52_status_contract_is_exact_and_ordered():
    assert STATUS_VALUES == (
        "passed",
        "passed_with_warning",
        "disagreement",
        "inconclusive",
        "skipped",
        "unsupported",
        "error",
    )


@pytest.mark.unit
def test_stable_snapshot_owns_bytes_and_returns_fresh_objects():
    source = {"z": [{"value": 3}], "a": {"values": [2, 1]}}
    snapshot = StableSnapshot.from_payload(source)
    before = snapshot.canonical_json
    digest = snapshot.digest

    source["z"][0]["value"] = 999
    first = snapshot.to_dict()
    first["z"][0]["value"] = -1

    assert snapshot.canonical_json == before
    assert snapshot.digest == digest
    assert snapshot.to_dict()["z"][0]["value"] == 3
    assert snapshot.canonical_json == '{"a":{"values":[2,1]},"z":[{"value":3}]}'


@pytest.mark.unit
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_deterministic_json_rejects_non_finite_numbers_recursively(value):
    with pytest.raises(ValueError, match="non-finite"):
        stable_json_dumps({"outer": [{"value": value}]})
    with pytest.raises(ValueError, match="non-finite"):
        StableSnapshot.from_payload({"outer": {"value": value}})


@pytest.mark.unit
@pytest.mark.parametrize(
    "forbidden",
    [
        "raw_text",
        "normalized_text",
        "source_text",
        "matched_raw_text",
        "student_solution",
    ],
)
def test_trace_snapshot_rejects_recursive_privacy_keys(forbidden):
    with pytest.raises(ValueError, match="forbidden trace key"):
        StableSnapshot.from_payload({"safe": [{"nested": {forbidden: "secret"}}]})


@pytest.mark.unit
def test_model_fingerprints_are_versioned_stable_and_separate():
    canonical = extract_problem(
        "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라."
    )
    model = build_physical_model(canonical)

    legacy = project_legacy_model(model)
    typed = project_typed_model(model)
    equations = project_equation_set(model)

    assert legacy["schema_version"] == LEGACY_MODEL_SCHEMA_VERSION
    assert typed is not None
    assert typed["schema_version"] == TYPED_MODEL_SCHEMA_VERSION
    assert project_typed_model(model.typed_model)["schema_version"] == TYPED_MODEL_SCHEMA_VERSION
    assert {item["id"] for item in typed["frames"]} >= {"world", "incline"}
    assert {item["id"] for item in typed["bodies"]} == {"body"}
    assert all(item["dimension"] for item in typed["constraints"])
    assert all(item["expression"] is not None for item in typed["constraints"])
    assert typed["generated_equation_set"]["equation_ids"]
    assert equations["equation_ids"]
    assert all(item["expression"] is not None for item in equations["equations"])

    legacy_digest = legacy_model_fingerprint(model)
    typed_digest = typed_model_fingerprint(model)
    assert legacy_digest == legacy_model_fingerprint(model)
    assert typed_digest == typed_model_fingerprint(model)
    assert typed_digest is not None
    assert legacy_digest != typed_digest


@pytest.mark.unit
def test_legacy_only_model_keeps_legacy_and_equation_evidence_without_typed_digest():
    canonical = extract_problem(
        "질량 5kg인 블록이 마찰 없는 30도 경사면에서 미끄러진다. 가속도를 구하라."
    )
    model = build_physical_model(canonical)
    model.typed_model = None
    values = iter(float(index) for index in range(8))
    collector = SolveTraceCollector("phase52-legacy-only", clock=lambda: next(values))

    collector.begin()
    collector.capture_models(model)
    for stage in ("parse", "route", "solve", "verify"):
        collector.start_stage(stage)
        collector.finish_stage(stage)
    collector.finalize("unsupported")
    core = collector.snapshot.to_dict()

    assert core["model_fingerprints"]["legacy"]["fingerprint"]
    assert core["model_fingerprints"]["typed"] == {
        "schema_version": TYPED_MODEL_SCHEMA_VERSION,
        "fingerprint": None,
        "present": False,
    }
    assert core["equation_set"]["equation_ids"]
    assert project_typed_model({"typed_model": None}) is None


@pytest.mark.unit
def test_collector_has_no_generic_record_privacy_bypass():
    collector = SolveTraceCollector("phase52-no-generic-record")
    with pytest.raises(AttributeError):
        collector.record("student_answer", {"hash": "not-a-projection"})
