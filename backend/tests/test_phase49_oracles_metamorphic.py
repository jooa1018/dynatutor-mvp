from __future__ import annotations

import json

import pytest

from tools.run_phase49_consistency import (
    DEFAULT_JSON_REPORT,
    DEFAULT_MARKDOWN_REPORT,
    FIXTURE_SHA256,
    SEMANTIC_SELECTION_EVIDENCE_SOURCE,
    build_implemented_not_executed_report,
    render_json,
    render_markdown,
    run_suite,
    write_reports,
)


pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
def phase49_report():
    return run_suite()


def test_full_phase49_suite_retains_all_five_fixed_case_counts(
    tmp_path, phase49_report
):
    report = phase49_report
    summary = report["summary"]

    assert report["passed"]
    assert report["status"] == "passed"
    assert report["fixture_sha256"] == FIXTURE_SHA256
    assert summary["oracle_cases"] == 60
    assert summary["scalar_expected_outputs"] == 70
    for prefix in (
        "product_verified",
        "oracle_product",
        "oracle_secondary",
        "product_secondary",
        "three_way",
    ):
        assert summary[f"{prefix}_total"] == 60
        assert summary[f"{prefix}_executed"] == 60
        assert summary[f"{prefix}_passed"] == 60
    assert summary["distinct_metamorphic_relations"] == 21
    assert summary["metamorphic_total"] == 21
    assert summary["metamorphic_executed"] == 21
    assert summary["metamorphic_passed"] == 21
    assert summary["mutation_controls"] == 4
    assert summary["mutation_controls_executed"] == 4
    assert summary["mutations_killed"] == 4
    assert len(report["path_roles"]) == 6
    assert not report["disagreements"]

    assert all(item["product_verified"] for item in report["cases"])
    assert all(
        item["output_selection_status"] == "selected"
        and item["semantic_selection_evidence_source"]
        == SEMANTIC_SELECTION_EVIDENCE_SOURCE
        for item in report["cases"]
    )
    assert all(item["three_way"]["passed"] for item in report["cases"])
    assert all(
        set(item["three_way"]["legs"])
        == {"oracle_product", "oracle_secondary", "product_secondary"}
        for item in report["cases"]
    )
    assert all(
        set(item["leg_evidence"])
        == {"oracle_product", "oracle_secondary", "product_secondary"}
        for item in report["cases"]
    )

    first_json = render_json(report)
    assert first_json == render_json(report)
    parsed = json.loads(first_json)
    assert parsed["schema_version"] == 2
    assert parsed["report_version"] == (
        "phase49-solver-consistency-report-v2"
    )
    assert parsed["policy_version"] == "phase48-tolerance-policy-v1"
    assert parsed["selection_evidence_contract"][
        "semantic_selection_evidence_source"
    ] == SEMANTIC_SELECTION_EVIDENCE_SOURCE
    assert "Product-secondary direct legs" in render_markdown(report)

    json_path = tmp_path / "phase49.json"
    markdown_path = tmp_path / "phase49.md"
    write_reports(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    assert json_path.read_text(encoding="utf-8") == first_json
    assert markdown_path.read_text(encoding="utf-8") == (
        render_markdown(report)
    )


def test_all_relations_execute_four_paths_and_assert_actual_values(
    phase49_report,
):
    relations = phase49_report["metamorphic_relations"]

    assert len(relations) == 21
    assert all(item["required_path_call_count"] == 4 for item in relations)
    assert all(
        set(item["actual_calls"])
        == {
            "product_base",
            "product_transformed",
            "secondary_base",
            "secondary_transformed",
        }
        for item in relations
    )
    assert all(
        item["relation_assertion"]["product"]["passed"]
        and item["relation_assertion"]["secondary"]["passed"]
        and item["relation_assertion"]["analytic_anchor_present"]
        for item in relations
    )
    assert all(item["direct_base_report"]["passed"] for item in relations)
    assert all(
        item["paths"]["transformed"][
            "expected_disagreements_observed"
        ]
        for item in relations
    )
    assert all(item["passed"] for item in relations)

    covariance = next(
        item
        for item in relations
        if item["relation_kind"] == "coordinate_sign_covariance"
    )
    assert not covariance["direct_transformed_report"]["passed"]
    assert covariance["paths"]["transformed"][
        "expected_direct_disagreement_categories"
    ] == ["positive_direction"]
    assert covariance["paths"]["transformed"][
        "observed_direct_disagreement_categories"
    ] == ["positive_direction"]
    assert not covariance["three_way_transformed_report"]["passed"]
    assert covariance["passed"]

    paraphrase = next(
        item
        for item in relations
        if item["relation_kind"] == "end_to_end_paraphrase_invariance"
    )
    assert paraphrase["additional_text_product_call_count"] == 2
    assert paraphrase["total_actual_call_count"] == 6
    assert paraphrase["actual_text_evidence"]["passed"]
    assert paraphrase["actual_text_evidence"]["relation"]["passed"]
    assert all(
        item["additional_text_product_call_count"] == 0
        and item["total_actual_call_count"] == 4
        for item in relations
        if item is not paraphrase
    )


def test_committed_report_is_exact_pending_or_passed_render(
    phase49_report,
):
    committed_json = DEFAULT_JSON_REPORT.read_text(encoding="utf-8")
    committed = json.loads(committed_json)
    if committed["status"] == "implemented_not_executed":
        expected = build_implemented_not_executed_report()
        assert expected["passed"] is False
        assert expected["summary"]["product_secondary_executed"] == 0
        assert len(expected["configured_evidence"]["cases"]) == 60
        assert len(
            expected["configured_evidence"]["metamorphic_relations"]
        ) == 21
        assert len(
            expected["configured_evidence"]["mutation_controls"]
        ) == 4
    elif committed["status"] == "passed":
        expected = phase49_report
        assert expected["passed"]
        assert not expected["disagreements"]
    else:
        pytest.fail(
            f"unsupported committed report status {committed['status']!r}"
        )

    assert committed_json == render_json(expected)
    assert DEFAULT_MARKDOWN_REPORT.read_text(
        encoding="utf-8"
    ) == render_markdown(expected)
