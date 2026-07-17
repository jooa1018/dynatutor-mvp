from __future__ import annotations

import json
from pathlib import Path
import sys
import types

import pytest

from tools import profile_phase52_rigid_body as profiler


BASE_SHA = "1" * 40
HEAD_SHA = "2" * 40


def _response_with_checks(checks: list[dict[str, object]]):
    return {
        "ok": True,
        "answers": [],
        "verification": {
            "passed": True,
            "policy_version": "test-policy-v1",
            "structured_checks": checks,
        },
    }


def _structured_check(
    check_id: str,
    *,
    status: str = "pass",
    source_equation_ids: list[str] | None = None,
):
    return {
        "check_id": check_id,
        "category": "test",
        "status": status,
        "applicability": "applicable",
        "absolute_error": 0.0,
        "relative_error": 0.0,
        "tolerance": 1e-9,
        "source_equation_ids": source_equation_ids or ["eq-1"],
    }


def test_semantic_fingerprint_treats_structured_checks_as_a_multiset():
    first_check = _structured_check("first")
    second_check = _structured_check("second")

    first_hash, first_ids, first_components = profiler._semantic_fingerprint(
        _response_with_checks([first_check, second_check])
    )
    second_hash, second_ids, second_components = profiler._semantic_fingerprint(
        _response_with_checks([second_check, first_check])
    )

    assert first_hash == second_hash
    assert first_components["verification"] == second_components["verification"]
    assert first_ids == second_ids == ("first", "second")


def test_semantic_fingerprint_detects_projected_check_field_changes():
    baseline = _structured_check("field-change")
    changed = {**baseline, "status": "fail"}

    baseline_hash, _, baseline_components = profiler._semantic_fingerprint(
        _response_with_checks([baseline])
    )
    changed_hash, _, changed_components = profiler._semantic_fingerprint(
        _response_with_checks([changed])
    )

    assert baseline_hash != changed_hash
    assert baseline_components["verification"] != changed_components["verification"]


def test_semantic_fingerprint_detects_check_multiplicity_changes():
    check = _structured_check("duplicate")

    single_hash, single_ids, single_components = profiler._semantic_fingerprint(
        _response_with_checks([check])
    )
    duplicate_result = profiler._semantic_fingerprint(
        _response_with_checks([check, check])
    )
    duplicate_hash, duplicate_ids, duplicate_components = duplicate_result

    assert single_hash != duplicate_hash
    assert single_components["verification"] != duplicate_components["verification"]
    assert single_ids == duplicate_ids == ("duplicate",)


def test_semantic_fingerprint_preserves_source_equation_id_order():
    baseline = _structured_check(
        "equation-order", source_equation_ids=["eq-1", "eq-2"]
    )
    changed = _structured_check(
        "equation-order", source_equation_ids=["eq-2", "eq-1"]
    )

    baseline_hash, _, baseline_components = profiler._semantic_fingerprint(
        _response_with_checks([baseline])
    )
    changed_hash, _, changed_components = profiler._semantic_fingerprint(
        _response_with_checks([changed])
    )

    assert baseline_hash != changed_hash
    assert baseline_components["verification"] != changed_components["verification"]


def _target(target_id: str, *, label: str, self_ms: float = 0.0):
    spec = next(item for item in profiler.TARGET_MANIFEST if item["target_id"] == target_id)
    present = label == "head"
    called = present and self_ms > 0
    calls = 500 if called else 0
    seconds = self_ms * 500 / 1000.0 if called else 0.0
    return {
        "target_id": target_id,
        "module": spec["module"],
        "qualname": spec["qualname"],
        "availability": "called" if called else ("present_not_called" if present else "absent"),
        "repo_relative_filename": "engine/example.py" if present else None,
        "first_line": 10 if present else None,
        "code_name": "example" if present else None,
        "primitive_calls": calls,
        "total_calls": calls,
        "recursive": False,
        "self_seconds": seconds,
        "cumulative_seconds": seconds,
        "self_ms_per_product_solve": self_ms if called else 0.0,
        "cumulative_ms_per_product_solve": self_ms if called else 0.0,
        "self_ms_per_target_call": self_ms if called else 0.0,
        "cumulative_ms_per_target_call": self_ms if called else 0.0,
    }


def _artifact(round_number: int, label: str, case_id: str, position: int):
    sha = HEAD_SHA if label == "head" else BASE_SHA
    rigid = case_id == "rigid_body"
    profiled_ms = 5.0 if label == "head" else 4.0
    unprofiled_ms = 4.0 if label == "head" else 3.0
    targets = []
    for target_id in profiler.TARGET_IDS:
        self_ms = 0.0
        if (
            label == "head"
            and rigid
            and target_id == "invariants.rigid_relative_velocity"
        ):
            self_ms = 0.7
        targets.append(_target(target_id, label=label, self_ms=self_ms))
    return {
        "schema_version": profiler.SCHEMA_VERSION,
        "artifact_kind": profiler.ARTIFACT_KIND,
        "deterministic_report_eligible": False,
        "metadata": {
            "revision_label": label,
            "revision_sha": sha,
            "round_number": round_number,
            "position": position,
        },
        "case": {
            "case_id": case_id,
            "case_version": profiler.CASE_VERSION,
            "input_sha256": profiler._sha256_text(profiler.CASE_INPUTS[case_id]),
        },
        "measurement": {
            "warmups": 200,
            "repeats": 500,
            "profiled_total_seconds": profiled_ms * 500 / 1000.0,
            "profiled_ms_per_product_solve": profiled_ms,
            "unprofiled_total_seconds": unprofiled_ms * 500 / 1000.0,
            "unprofiled_ms_per_product_solve": unprofiled_ms,
            "response_sha256": ("a" if label == "base" else "b") * 64,
            "semantic_component_sha256": {
                name: ("c" if label == "base" else "d") * 64
                for name in profiler.SEMANTIC_COMPONENTS
            },
            "check_ids": ["answer_consistency", "dimension"],
        },
        "targets": targets,
        "top_cumulative": [
            {
                "rank": 1,
                "origin_kind": "builtin",
                "filename": None,
                "module_label": "test_builtin",
                "first_line": 0,
                "code_name": "test_builtin_call",
                "primitive_calls": 500,
                "total_calls": 500,
                "self_seconds": 0.1,
                "cumulative_seconds": 0.2,
                "self_ms_per_product_solve": 0.2,
                "cumulative_ms_per_product_solve": 0.4,
            }
        ],
    }


def _write_evidence(root: Path):
    for round_number in range(1, 5):
        head_position = 1 if round_number % 2 else 2
        for label in profiler.REVISION_LABELS:
            position = head_position if label == "head" else 3 - head_position
            for case_id in profiler.CASE_IDS:
                path = root / f"round-{round_number}-{label}-{case_id}.json"
                path.write_text(
                    json.dumps(_artifact(round_number, label, case_id, position)),
                    encoding="utf-8",
                )


def _compare_args(root: Path, out: Path):
    return type(
        "Args",
        (),
        {
            "evidence_dir": str(root),
            "expected_base_sha": BASE_SHA,
            "expected_head_sha": HEAD_SHA,
            "expected_rounds": 4,
            "expected_warmups": 200,
            "expected_repeats": 500,
            "out": str(out),
        },
    )()


def test_compare_requires_balanced_complete_exact_ref_evidence(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    output = tmp_path / "comparison.json"

    result = profiler.compare(_compare_args(evidence, output))

    assert result["artifact_count"] == 16
    assert result["verdict"] == "CANDIDATE_IDENTIFIED"
    assert result["selected_candidate"] == "duplicate_rigid_invariants"
    assert result["deterministic_report_eligible"] is False
    rendered = output.read_text(encoding="utf-8")
    assert profiler.RIGID_BODY not in rendered
    assert profiler.PROJECTILE not in rendered


def test_compare_rejects_missing_or_extra_evidence(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    one = next(evidence.iterdir())
    one.unlink()
    with pytest.raises(profiler.ProfileDataError, match="exactly 16"):
        profiler.compare(_compare_args(evidence, tmp_path / "out.json"))

    _write_evidence(evidence)
    (evidence / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(profiler.ProfileDataError, match="unexpected files"):
        profiler.compare(_compare_args(evidence, tmp_path / "out.json"))


def test_compare_requires_the_exact_alternating_order(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    for round_number in (2, 3):
        for label in profiler.REVISION_LABELS:
            for case_id in profiler.CASE_IDS:
                path = evidence / f"round-{round_number}-{label}-{case_id}.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["metadata"]["position"] = 3 - payload["metadata"]["position"]
                path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(profiler.ProfileDataError, match="exactly alternating"):
        profiler.compare(_compare_args(evidence, tmp_path / "out.json"))


def test_same_ref_semantics_must_match_across_rounds(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    path = evidence / "round-4-head-rigid_body.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["measurement"]["response_sha256"] = "c" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        profiler.ProfileDataError,
        match=r"same-ref response hash changed.*head/rigid_body/round-4/components-overall",
    ):
        profiler.compare(_compare_args(evidence, tmp_path / "out.json"))


def test_same_ref_target_identity_must_match_across_evidence(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    path = evidence / "round-4-head-projectile.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["targets"][0]["first_line"] = 11
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(profiler.ProfileDataError, match="target identity"):
        profiler.compare(_compare_args(evidence, tmp_path / "out.json"))


def test_same_ref_hash_error_names_only_changed_semantic_components(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    path = evidence / "round-4-base-projectile.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["measurement"]["response_sha256"] = "e" * 64
    payload["measurement"]["semantic_component_sha256"]["route"] = "f" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        profiler.ProfileDataError,
        match=r"base/projectile/round-4/components-route",
    ):
        profiler.compare(_compare_args(evidence, tmp_path / "out.json"))


def test_same_ref_check_id_change_is_reported_before_overall_hash(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    path = evidence / "round-4-head-rigid_body.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["measurement"]["check_ids"].append("new_check")
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        profiler.ProfileDataError,
        match=r"check IDs changed.*head/rigid_body/round-4",
    ):
        profiler.compare(_compare_args(evidence, tmp_path / "out.json"))


def test_strict_json_rejects_nonfinite_duplicate_and_bool_numbers(tmp_path: Path):
    nan_path = tmp_path / "nan.json"
    nan_path.write_text('{"x": NaN}', encoding="utf-8")
    with pytest.raises(profiler.ProfileDataError, match="non-finite"):
        profiler._load_json_strict(nan_path)

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"x": 1, "x": 2}', encoding="utf-8")
    with pytest.raises(profiler.ProfileDataError, match="duplicate"):
        profiler._load_json_strict(duplicate_path)

    artifact = _artifact(1, "head", "rigid_body", 1)
    artifact["measurement"]["repeats"] = True
    with pytest.raises(profiler.ProfileDataError, match="integer"):
        profiler._validate_artifact(artifact)

    artifact = _artifact(1, "head", "rigid_body", 1)
    artifact["schema_version"] = True
    with pytest.raises(profiler.ProfileDataError, match="integer"):
        profiler._validate_artifact(artifact)

    artifact = _artifact(1, "head", "rigid_body", 1)
    artifact["measurement"]["repeats"] = 499
    with pytest.raises(profiler.ProfileDataError, match="sample counts"):
        profiler._validate_artifact(artifact)

    artifact = _artifact(1, "head", "rigid_body", 1)
    artifact["top_cumulative"][0]["primitive_calls"] = True
    with pytest.raises(profiler.ProfileDataError, match="integer"):
        profiler._validate_artifact(artifact)

    artifact = _artifact(1, "head", "rigid_body", 1)
    artifact["top_cumulative"][0]["module_label"] = "C:\\runner\\leak.py"
    with pytest.raises(profiler.ProfileDataError, match="external"):
        profiler._validate_artifact(artifact)


def test_compare_rejects_non_contracted_expected_sample_counts(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    args = _compare_args(evidence, tmp_path / "out.json")
    args.expected_warmups = 1
    args.expected_repeats = 1
    with pytest.raises(profiler.ProfileDataError, match="expected sampling"):
        profiler.compare(args)


def test_target_schema_distinguishes_absent_present_and_called():
    base = _artifact(1, "base", "rigid_body", 2)
    head = _artifact(1, "head", "rigid_body", 1)
    profiler._validate_artifact(base)
    profiler._validate_artifact(head)
    assert {item["availability"] for item in base["targets"]} == {"absent"}
    assert "called" in {item["availability"] for item in head["targets"]}
    assert "present_not_called" in {item["availability"] for item in head["targets"]}


def test_target_and_frontier_self_time_cannot_exceed_profiled_wall():
    artifact = _artifact(1, "head", "rigid_body", 1)
    target = artifact["targets"][0]
    target.update(
        {
            "availability": "called",
            "primitive_calls": 500,
            "total_calls": 500,
            "self_seconds": 3.0,
            "cumulative_seconds": 3.0,
            "self_ms_per_product_solve": 6.0,
            "cumulative_ms_per_product_solve": 6.0,
            "self_ms_per_target_call": 6.0,
            "cumulative_ms_per_target_call": 6.0,
        }
    )
    with pytest.raises(profiler.ProfileDataError, match="target self"):
        profiler._validate_artifact(artifact)

    artifact = _artifact(1, "head", "rigid_body", 1)
    for target_id in profiler.CANDIDATE_FRONTIERS["candidate_validation_chain"][:2]:
        target = next(item for item in artifact["targets"] if item["target_id"] == target_id)
        target.update(
            {
                "availability": "called",
                "primitive_calls": 500,
                "total_calls": 500,
                "self_seconds": 1.5,
                "cumulative_seconds": 1.5,
                "self_ms_per_product_solve": 3.0,
                "cumulative_ms_per_product_solve": 3.0,
                "self_ms_per_target_call": 3.0,
                "cumulative_ms_per_target_call": 3.0,
            }
        )
    with pytest.raises(profiler.ProfileDataError, match="frontier self"):
        profiler._validate_artifact(artifact)


def test_recursive_candidate_is_inconclusive(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    for path in evidence.glob("*-head-rigid_body.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        target = next(
            item
            for item in payload["targets"]
            if item["target_id"] == "invariants.rigid_relative_velocity"
        )
        target["primitive_calls"] = 499
        target["recursive"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")

    result = profiler.compare(_compare_args(evidence, tmp_path / "out.json"))
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["selected_candidate"] is None


@pytest.mark.parametrize("head_ms", [4.0, 2.0])
def test_no_positive_total_regression_is_inconclusive(tmp_path: Path, head_ms: float):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _write_evidence(evidence)
    for path in evidence.glob("*-head-*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["measurement"]["profiled_total_seconds"] = head_ms * 500 / 1000.0
        payload["measurement"]["profiled_ms_per_product_solve"] = head_ms
        payload["measurement"]["unprofiled_total_seconds"] = head_ms * 500 / 1000.0
        payload["measurement"]["unprofiled_ms_per_product_solve"] = head_ms
        path.write_text(json.dumps(payload), encoding="utf-8")

    result = profiler.compare(_compare_args(evidence, tmp_path / "out.json"))
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["selected_candidate"] is None
    assert (
        "the requirement for exactly one rigid-body candidate to meet "
        "the fixed threshold was not satisfied"
        in result["reasons"]
    )


def test_preloaded_engine_module_is_rejected(monkeypatch: pytest.MonkeyPatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setitem(sys.modules, "engine.preloaded_intruder", types.ModuleType("engine.preloaded_intruder"))
    with pytest.raises(profiler.ProfileDataError, match="loaded before"):
        profiler._prepare_engine_imports(root)


def test_loaded_engine_origin_must_stay_under_backend_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = Path(__file__).resolve().parents[1]
    for name in list(sys.modules):
        if name == "engine" or name.startswith("engine."):
            monkeypatch.delitem(sys.modules, name)
    outside = tmp_path / "outside.py"
    outside.write_text("", encoding="utf-8")
    intruder = types.ModuleType("engine.origin_intruder")
    intruder.__file__ = str(outside)
    monkeypatch.setitem(sys.modules, "engine.origin_intruder", intruder)
    with pytest.raises(profiler.ProfileDataError, match="outside backend-root"):
        profiler._validate_loaded_engine_modules(root)


def test_head_manifest_resolves_to_repository_code():
    root = Path(__file__).resolve().parents[1]
    resolved = profiler._resolve_targets(root, "head")
    assert [item["target_id"] for item in resolved] == list(profiler.TARGET_IDS)
    assert all(item["availability"] != "absent" for item in resolved)
    assert all(
        not Path(item["repo_relative_filename"]).is_absolute()
        for item in resolved
        if item["availability"] != "absent"
    )
