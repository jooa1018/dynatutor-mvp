from __future__ import annotations

import json

import pytest

from tools.run_phase49_consistency import (
    render_json,
    render_markdown,
    run_suite,
    write_reports,
)


pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
def phase49_report():
    return run_suite()


def test_full_phase49_oracle_and_metamorphic_suite(
    tmp_path, phase49_report
):
    report = phase49_report

    assert report["passed"]
    assert report["status"] == "passed"
    assert report["summary"]["oracle_cases"] == 60
    assert report["summary"]["scalar_expected_outputs"] == 70
    assert report["summary"]["product_path_passed"] == 60
    assert report["summary"]["secondary_path_passed"] == 60
    assert report["summary"]["distinct_metamorphic_relations"] == 21
    assert report["summary"]["metamorphic_passed"] == 21
    assert report["summary"]["mutation_controls"] == 4
    assert report["summary"]["mutations_killed"] == 4
    assert len(report["path_roles"]) == 6
    assert not report["disagreements"]

    first_json = render_json(report)
    assert first_json == render_json(report)
    parsed = json.loads(first_json)
    assert parsed["policy_version"] == "phase48-tolerance-policy-v1"
    assert "Phase 49 Solver Consistency Report" in render_markdown(report)

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


def test_all_relations_anchor_real_base_and_transformed_product_paths(
    phase49_report,
):
    assert all(
        item["product_base_report"]["passed"]
        and item["product_transformed_report"]["passed"]
        and item["secondary_base_report"]["passed"]
        and item["secondary_transformed_report"]["passed"]
        and item["relation_assertion"]["passed"]
        for item in phase49_report["metamorphic_relations"]
    )
