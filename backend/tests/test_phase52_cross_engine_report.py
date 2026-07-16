from __future__ import annotations

import copy
import json
import math

import pytest

from engine.observability.contracts import STATUS_VALUES
from engine.observability.reporting import (
    CASE_FIELDS,
    DASHBOARD_METRIC_IDS,
    EXPECTED_SKIP_MANIFEST,
    PHASE50_CASE_IDS,
    PHASE51_CASE_IDS,
    build_cross_engine_core,
    build_final_report,
    build_performance_artifact,
    build_version_evidence,
    classify_engine_exception,
    classify_engine_outcome,
    evaluate_release_gate,
    is_expected_skip,
    normalize_phase50_report,
    normalize_phase51_report,
    render_final_json,
    render_final_markdown,
    validate_final_report,
    validate_performance,
    validate_trace_snapshot,
)
from engine.observability.trace import SolveTraceCollector


SHA = "a" * 40


def _dashboard_sources():
    return {
        "golden": {"passed": 8, "total": 8},
        "false_solve": {"false": 0, "total": 60},
        "clarification": {
            "true_positive": 14,
            "false_positive": 0,
            "fired": 14,
            "total": 14,
            "precision_denominator": 14,
        },
        "routing": {"correct": 432, "total": 432},
        "residual_invariant_failures": 0,
        "numeric_checked": 127,
    }


def _phase50_payload(count=7):
    case_ids = sorted(PHASE50_CASE_IDS)[:count]
    return {
        "cases": [
            {
                "case_id": case_id,
                "status": "completed",
                "passed": True,
                "checks": {
                    "analytic_contract_passed": True,
                    "constraint_policy_passed": True,
                    "energy_policy_passed": True,
                },
                "requirements": {"analytic_agreement": True},
                "final_state": {"x": float(index)},
                "analytic_error": {
                    "passed": True,
                    "max_abs_error": 1e-9,
                    "period_relative_error": 1e-9,
                    "comparison_tolerance": 1e-5,
                },
                "constraint_violation": {"passed": True},
                "invariant_drift": {"passed": True},
                "integration": {
                    "method": "DOP853",
                    "rtol": 1e-10,
                    "atol": 1e-12,
                    "max_step": 0.02,
                },
                "runtime_versions": {"sympy": "1.14", "scipy": "1.17"},
                "warnings": [],
                "errors": [],
            }
            for index, case_id in enumerate(case_ids)
        ]
    }


def _phase51_case(case_id="chrono-0", chrono_status="passed", passed=True):
    missing = chrono_status == "skipped"
    return {
        "case_id": case_id,
        "analytic_value": 2.0,
        "passed": passed,
        "product": {
            "required": True,
            "status": "solved",
            "value": 2.0,
            "unit": "m/s",
            "warnings": [],
        },
        "chrono": {
            "schema_version": 1,
            "suite_version": "phase51-pychrono-suite-v1",
            "policy_version": "phase51-pychrono-policy-v1",
            "case_id": case_id,
            "status": chrono_status,
            "passed": passed,
            "observable": "speed",
            "value": 2.0001 if chrono_status == "passed" else None,
            "unit": "m/s",
            "analytic_value": 2.0,
            "abs_error": 0.0001 if passed else None,
            "relative_error": 0.00005 if passed else None,
            "chrono_version": "unavailable" if missing else "9.0.1",
            "solver": "not_initialized:PSOR_requested" if missing else "PSOR",
            "contact_method": "SMC",
            "time_step": 0.0005,
            "duration": 1.0,
            "initial_conditions": {
                "time_step_s": 0.0005,
                "solver_max_iterations": 200,
                "collision_envelope_m": 0.001,
                "collision_safe_margin_m": 0.0005,
            },
            "constraint_errors": {"contact": {"passed": passed}},
            "invariant_errors": {"energy": {"passed": passed}},
            "modeling_assumptions": ["planar"],
            "warnings": [],
            "artifacts": [],
        },
        "comparisons": {
            "chrono_vs_analytic": {
                "absolute_error": 0.0001 if passed else 1.0,
                "relative_error": 0.00005 if passed else 0.5,
                "absolute_tolerance": 0.01,
                "relative_tolerance": 0.01,
            }
        },
    }


def _phase51_payload(statuses=("passed",) * 6):
    case_ids = sorted(PHASE51_CASE_IDS)
    return {
        "schema_version": 1,
        "report_version": "phase51-pychrono-report-v1",
        "environment": {"chrono_versions": ["9.0.1"]},
        "cases": [
            _phase51_case(case_id, status, status == "passed")
            for case_id, status in zip(case_ids, statuses, strict=True)
        ],
    }


def _trace(request_id="case-derived"):
    values = iter(float(index) for index in range(8))
    collector = SolveTraceCollector(request_id, clock=lambda: next(values))
    collector.begin()
    for stage in ("parse", "route", "solve", "verify"):
        collector.start_stage(stage)
        collector.finish_stage(stage)
    return collector.finalize("passed").to_dict()


def _samples(scale=1.0):
    return {
        "golden-a": [
            {
                "parse": scale * value,
                "route": scale * value,
                "solve": scale * value,
                "verify": scale * value,
                "end_to_end": scale * value * 4,
            }
            for value in range(1, 21)
        ]
    }


def _core(tier="extended", phase51=None):
    return build_cross_engine_core(
        source_commit=SHA,
        tier=tier,
        traces=[_trace()],
        phase50_payload=_phase50_payload(),
        phase51_payload=_phase51_payload() if phase51 is None else phase51,
        dashboard_sources=_dashboard_sources(),
        runtime_versions={"sympy": "1.14", "scipy": "1.17", "pychrono": "9.0.1"},
    )


@pytest.mark.unit
def test_seven_status_values_and_required_case_fields_are_exact():
    assert STATUS_VALUES == (
        "passed",
        "passed_with_warning",
        "disagreement",
        "inconclusive",
        "skipped",
        "unsupported",
        "error",
    )
    cases = normalize_phase50_report(_phase50_payload(1))
    assert tuple(cases[0]) == CASE_FIELDS


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "passed"}, "passed"),
        ({"status": "completed", "warnings": ["bounded warning"]}, "passed_with_warning"),
        ({"status": "failed"}, "disagreement"),
        ({}, "inconclusive"),
        ({"status": "missing_dependency"}, "error"),
        ({"status": "unavailable"}, "error"),
        ({"status": "skipped"}, "error"),
        ({"status": "unsupported"}, "unsupported"),
        ({"status": "initialization_failed"}, "error"),
    ],
)
def test_fake_payloads_map_to_exact_status_contract(payload, expected):
    assert classify_engine_outcome(payload, declared_module="pychrono") == expected


@pytest.mark.unit
def test_missing_dependency_and_installed_runtime_failure_are_adversarially_distinct():
    missing = ModuleNotFoundError("missing pychrono", name="pychrono")
    nested_missing = ModuleNotFoundError("missing pychrono core", name="pychrono.core")
    unrelated = ModuleNotFoundError("missing numpy", name="numpy")
    assert classify_engine_exception(missing, declared_module="pychrono") == "skipped"
    assert classify_engine_exception(nested_missing, declared_module="pychrono") == "skipped"
    assert classify_engine_exception(unrelated, declared_module="pychrono") == "error"
    assert classify_engine_exception(RuntimeError("installed engine boom"), declared_module="pychrono") == "error"


@pytest.mark.unit
def test_phase50_and_phase51_normalization_preserve_case_counts_and_disagreement():
    phase50 = normalize_phase50_report(_phase50_payload())
    phase51 = normalize_phase51_report(_phase51_payload(("passed", "failed", "skipped", "unsupported", "error", "passed")))
    assert len(phase50) == 7
    assert len(phase51) == 6
    assert sorted(case["status"] for case in phase51) == sorted(
        ["passed", "disagreement", "skipped", "unsupported", "error", "passed"]
    )
    actual = next(case for case in phase51 if case["case_id"] == "collision_restitution")
    settings = actual["engine_settings"]["pychrono"]
    assert settings == {
        "time_step": 0.0005,
        "solver": "PSOR",
        "contact_method": "SMC",
        "time_step_s": 0.0005,
        "solver_max_iterations": 200,
        "collision_envelope_m": 0.001,
        "collision_safe_margin_m": 0.0005,
    }
    assert actual["assumptions"] == ["planar"]


@pytest.mark.unit
def test_serialized_skip_requires_exact_accepted_phase51_provenance():
    accepted = _phase51_payload(("skipped",) * 6)
    assert all(case["status"] == "skipped" for case in normalize_phase51_report(accepted))
    wrong_version = copy.deepcopy(accepted)
    wrong_version["report_version"] = "free-form-report"
    assert all(case["status"] == "error" for case in normalize_phase51_report(wrong_version))
    initialized = copy.deepcopy(accepted)
    initialized["cases"][0]["chrono"]["solver"] = "PSOR"
    by_id = {case["case_id"]: case for case in normalize_phase51_report(initialized)}
    assert by_id[initialized["cases"][0]["case_id"]]["status"] == "error"


@pytest.mark.unit
def test_phase50_large_angle_uses_policy_checks_not_raw_analytic_pass():
    payload = _phase50_payload()
    large = next(
        case
        for case in payload["cases"]
        if case["case_id"] == "pendulum_large_angle_expected_difference"
    )
    large["analytic_error"]["passed"] = False
    large["checks"]["analytic_contract_passed"] = True
    normalized = normalize_phase50_report(payload)
    target = next(case for case in normalized if case["case_id"] == large["case_id"])
    assert all(check["passed"] is True for check in target["invariant_checks"])


@pytest.mark.unit
def test_static_expected_skip_manifest_cannot_be_widened_by_result():
    assert EXPECTED_SKIP_MANIFEST == (("extended", "pychrono", "*"),)
    assert is_expected_skip(tier="extended", engine="pychrono", case_id="any")
    assert not is_expected_skip(tier="nightly", engine="pychrono", case_id="any")
    assert not is_expected_skip(tier="extended", engine="scipy", case_id="any")
    fake = _phase51_payload(("skipped",) * 6)
    fake["expected_skip"] = True
    core = _core(tier="nightly", phase51=fake).to_dict()
    performance = build_performance_artifact(source_commit=SHA, tier="nightly", case_samples=_samples(0.1), repeats=20).to_dict()
    gate = evaluate_release_gate(core=core, performance=performance, pooled_performance_gate="passed", strict=True)
    assert gate["verdict"] == "failed"
    assert any("skipped" in reason for reason in gate["reasons"])


@pytest.mark.unit
def test_source_commit_required_and_engine_versions_present():
    with pytest.raises(ValueError, match="source_commit"):
        build_version_evidence(source_commit="")
    evidence = build_version_evidence(
        source_commit=SHA,
        runtime_versions={"sympy": "1", "scipy": "2", "pychrono": "3"},
    )
    assert evidence["source_commit"] == SHA
    assert {"sympy", "scipy", "pychrono"} <= evidence.keys()
    assert evidence["canonical_schema_version"]
    assert evidence["solver_pipeline_version"]
    assert evidence["tolerance_policy_version"]


@pytest.mark.unit
def test_deterministic_core_is_independent_of_performance_and_render_is_repeatable():
    first_core = _core()
    second_core = _core()
    first_performance = build_performance_artifact(source_commit=SHA, tier="extended", case_samples=_samples(0.1), repeats=20)
    second_performance = build_performance_artifact(source_commit=SHA, tier="extended", case_samples=_samples(0.2), repeats=20)
    assert first_core.canonical_bytes == second_core.canonical_bytes
    assert first_performance.canonical_bytes != second_performance.canonical_bytes
    content = first_performance.canonical_json + "\n"
    report = build_final_report(
        core=first_core.to_dict(),
        performance=first_performance.to_dict(),
        performance_filename="performance.json",
        performance_content=content,
        pooled_performance_gate="inconclusive",
        flaky_test_count=0,
        strict=False,
    )
    assert render_final_json(report) == render_final_json(report)
    assert render_final_markdown(report) == render_final_markdown(report)


@pytest.mark.unit
def test_nearest_rank_statistics_and_absolute_60_120_gate():
    artifact = build_performance_artifact(source_commit=SHA, tier="extended", case_samples=_samples(), repeats=20).to_dict()
    stats = artifact["cases"][0]["stage_statistics"]["parse"]
    assert stats == {"sample_count": 20, "p50_ms": 10.0, "p95_ms": 19.0, "worst_ms": 20.0}
    assert artifact["overall"]["p95_ms"] == 76.0
    assert artifact["overall"]["p50_ms"] == 40.0
    gate = evaluate_release_gate(core=_core().to_dict(), performance=artifact, pooled_performance_gate="passed", strict=False)
    assert gate["verdict"] == "passed"
    slow = build_performance_artifact(source_commit=SHA, tier="extended", case_samples=_samples(2.0), repeats=20).to_dict()
    assert evaluate_release_gate(core=_core().to_dict(), performance=slow, pooled_performance_gate="passed", strict=False)["verdict"] == "failed"


@pytest.mark.unit
def test_performance_validation_recomputes_every_summary_from_raw_samples():
    artifact = build_performance_artifact(
        source_commit=SHA,
        tier="nightly",
        case_samples=_samples(2.0),
        repeats=20,
    ).to_dict()
    tampered = copy.deepcopy(artifact)
    tampered["overall"]["mean_ms"] = 1.0
    tampered["overall"]["p50_ms"] = 1.0
    tampered["overall"]["p95_ms"] = 1.0
    tampered["overall"]["worst_ms"] = 1.0
    with pytest.raises(ValueError, match="overall performance statistics"):
        validate_performance(tampered)
    tampered_case = copy.deepcopy(artifact)
    tampered_case["cases"][0]["stage_statistics"]["solve"]["p95_ms"] = 0.1
    with pytest.raises(ValueError, match="statistics do not match raw samples"):
        validate_performance(tampered_case)


@pytest.mark.unit
def test_artifact_digest_schema_filename_and_tamper_validation():
    core = _core()
    performance = build_performance_artifact(source_commit=SHA, tier="extended", case_samples=_samples(0.1), repeats=20)
    content = performance.canonical_json + "\n"
    report = build_final_report(
        core=core.to_dict(),
        performance=performance.to_dict(),
        performance_filename="nested/phase52-performance.json",
        performance_content=content,
        pooled_performance_gate="passed",
        flaky_test_count=0,
        strict=False,
    )
    artifact = report["performance"]["artifact"]
    assert artifact["filename"] == "phase52-performance.json"
    assert artifact["schema_version"] == 1
    assert len(artifact["content_sha256"]) == 64
    with pytest.raises(ValueError, match="tampered"):
        build_final_report(
            core=core.to_dict(),
            performance=performance.to_dict(),
            performance_filename="phase52-performance.json",
            performance_content=content.replace('"tier":"extended"', '"tier":"nightly"'),
            pooled_performance_gate="passed",
            flaky_test_count=0,
            strict=False,
        )


@pytest.mark.unit
def test_dashboard_has_exact_eight_metrics_in_json_and_markdown_and_external_gate_is_explicit():
    core = _core()
    performance = build_performance_artifact(source_commit=SHA, tier="extended", case_samples=_samples(0.1), repeats=20)
    report = build_final_report(
        core=core.to_dict(),
        performance=performance.to_dict(),
        performance_filename="performance.json",
        performance_content=performance.canonical_json + "\n",
        pooled_performance_gate="inconclusive",
        flaky_test_count=3,
        strict=False,
    )
    assert tuple(metric["metric_id"] for metric in report["dashboard"]) == DASHBOARD_METRIC_IDS
    assert report["release_gate"]["external_pooled_parent_head_gate"]["status"] == "inconclusive"
    assert report["dashboard"][-1]["evidence"]["scope"] == "current_run_only"
    rendered_json = render_final_json(report)
    rendered_markdown = render_final_markdown(report)
    for metric_id in DASHBOARD_METRIC_IDS:
        assert metric_id in rendered_json
        assert metric_id in rendered_markdown


@pytest.mark.unit
def test_strict_nightly_rejects_skip_and_nonfinite_inputs():
    skipped_core = _core(tier="nightly", phase51=_phase51_payload(("skipped",) * 6))
    performance = build_performance_artifact(source_commit=SHA, tier="nightly", case_samples=_samples(0.1), repeats=20)
    report = build_final_report(
        core=skipped_core.to_dict(),
        performance=performance.to_dict(),
        performance_filename="performance.json",
        performance_content=performance.canonical_json + "\n",
        pooled_performance_gate="passed",
        flaky_test_count=0,
        strict=True,
    )
    with pytest.raises(ValueError, match="strict release gate"):
        validate_final_report(report, strict=True)
    bad_samples = _samples(0.1)
    bad_samples["golden-a"][0]["solve"] = math.nan
    with pytest.raises(ValueError, match="finite"):
        build_performance_artifact(source_commit=SHA, tier="nightly", case_samples=bad_samples, repeats=20)


@pytest.mark.unit
def test_strict_nightly_requires_exact_unique_phase50_and_phase51_case_sets():
    core = _core(tier="nightly").to_dict()
    performance = build_performance_artifact(
        source_commit=SHA, tier="nightly", case_samples=_samples(0.1), repeats=20
    ).to_dict()
    assert evaluate_release_gate(
        core=core,
        performance=performance,
        pooled_performance_gate="passed",
        strict=True,
    )["verdict"] == "passed"
    missing = copy.deepcopy(core)
    missing["cross_engine_cases"].pop()
    assert any(
        "nightly_missing_cases" in reason
        for reason in evaluate_release_gate(
            core=missing,
            performance=performance,
            pooled_performance_gate="passed",
            strict=True,
        )["reasons"]
    )
    duplicate = copy.deepcopy(core)
    duplicate["cross_engine_cases"].append(copy.deepcopy(duplicate["cross_engine_cases"][0]))
    assert any(
        "nightly_duplicate_case" in reason
        for reason in evaluate_release_gate(
            core=duplicate,
            performance=performance,
            pooled_performance_gate="passed",
            strict=True,
        )["reasons"]
    )
    extra = copy.deepcopy(core)
    unexpected = copy.deepcopy(extra["cross_engine_cases"][0])
    unexpected["case_id"] = "invented-case"
    extra["cross_engine_cases"].append(unexpected)
    assert any(
        "nightly_extra_cases" in reason
        for reason in evaluate_release_gate(
            core=extra,
            performance=performance,
            pooled_performance_gate="passed",
            strict=True,
        )["reasons"]
    )


@pytest.mark.unit
def test_strict_nightly_rejects_all_inconclusive_exact_pairs_deterministically():
    core = _core(tier="nightly").to_dict()
    for case in core["cross_engine_cases"]:
        case["status"] = "inconclusive"
    performance = build_performance_artifact(
        source_commit=SHA, tier="nightly", case_samples=_samples(0.1), repeats=20
    ).to_dict()
    gate = evaluate_release_gate(
        core=core,
        performance=performance,
        pooled_performance_gate="passed",
        strict=True,
    )
    expected = [
        f"nightly_required_status:{engine}:{case_id}:inconclusive"
        for engine, case_ids in (
            ("scipy", PHASE50_CASE_IDS),
            ("pychrono", PHASE51_CASE_IDS),
        )
        for case_id in sorted(case_ids)
    ]
    assert gate["verdict"] == "failed"
    assert [
        reason
        for reason in gate["reasons"]
        if reason.startswith("nightly_required_status:")
    ] == expected


@pytest.mark.unit
def test_strict_nightly_rejects_one_inconclusive_expected_pair():
    core = _core(tier="nightly").to_dict()
    target = next(
        case
        for case in core["cross_engine_cases"]
        if case["runtime"]["engine"] == "pychrono"
        and case["case_id"] == "rolling_disk"
    )
    target["status"] = "inconclusive"
    performance = build_performance_artifact(
        source_commit=SHA, tier="nightly", case_samples=_samples(0.1), repeats=20
    ).to_dict()
    gate = evaluate_release_gate(
        core=core,
        performance=performance,
        pooled_performance_gate="passed",
        strict=True,
    )
    assert gate["verdict"] == "failed"
    assert "nightly_required_status:pychrono:rolling_disk:inconclusive" in gate["reasons"]


@pytest.mark.unit
def test_trace_allowlist_rejects_nested_unknown_key_carrying_raw_student_sentinels():
    raw = "RAW_PHASE52_SENTINEL"
    student = "STUDENT_PHASE52_SENTINEL"
    trace = _trace()
    trace["route_candidates"]["detail"] = {
        "payload": f"{raw}:{student}"
    }
    assert raw in json.dumps(trace)
    assert student in json.dumps(trace)
    with pytest.raises(ValueError, match="trace keys differ"):
        validate_trace_snapshot(trace)
    with pytest.raises(ValueError, match="trace keys differ"):
        build_cross_engine_core(
            source_commit=SHA,
            tier="fast",
            traces=[trace],
            phase50_payload={},
            phase51_payload={},
            dashboard_sources=_dashboard_sources(),
        )
    nested = _trace("nested-list-bypass")
    nested["clarification_decision"]["option_ids"] = [
        {"detail": f"{raw}:{student}"}
    ]
    with pytest.raises(TypeError, match="list of strings"):
        validate_trace_snapshot(nested)


@pytest.mark.unit
def test_source_report_free_text_sentinels_are_discarded_by_projection():
    raw = "RAW_SOURCE_REPORT_SENTINEL"
    student = "STUDENT_SOURCE_REPORT_SENTINEL"
    phase50 = _phase50_payload(1)
    phase50["cases"][0]["errors"] = [raw]
    phase50["cases"][0]["debug_detail"] = student
    rendered = json.dumps(normalize_phase50_report(phase50), sort_keys=True)
    assert raw not in rendered
    assert student not in rendered
    phase51 = _phase51_payload()
    phase51["cases"][0]["chrono"]["warnings"] = [raw]
    phase51["cases"][0]["product"]["problem"] = student
    phase51["cases"][0]["product"]["display"] = f"display:{student}"
    projected = json.dumps(normalize_phase51_report(phase51), sort_keys=True)
    assert raw not in projected
    assert student not in projected
